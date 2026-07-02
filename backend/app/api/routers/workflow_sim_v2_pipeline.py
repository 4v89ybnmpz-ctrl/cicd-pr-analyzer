"""工作流仿真 V2 路由 — register_pipeline_routes（由 workflow_sim_v2.py 拆分）"""

import json
import logging
import re
from datetime import datetime


from fastapi import APIRouter, BackgroundTasks
from fastapi.responses import StreamingResponse


from .workflow_sim_v2_helpers import (
    _pipeline_cancel_flags,
    run_git as _run_git,
)

logger = logging.getLogger(__name__)


def _ts():
    return datetime.now().strftime("%H:%M:%S")


def register_pipeline_routes(router: APIRouter, db=None):
    @router.get("/cannbot/workflow-v2/sessions/{session_id}/trigger-pipeline")
    async def trigger_pipeline_sse(session_id: str, gitcode_token: str = ""):
        """手动触发 CI/CD 流水线（SSE 推送）"""
        if not db:
            return {"error": "数据库未连接"}
        if not gitcode_token:
            return {"error": "请提供 GitCode Token"}

        session = await db.get_workflow_sim_v2_session(session_id)
        if not session:
            return {"error": "会话未找到"}

        # 检查仿真是否已完成
        if session.get("status") not in ("completed", "stopped"):
            return {"error": "仿真尚未完成，无法触发流水线"}

        async def pipeline_event_generator():
            from app.services.pipeline_service import GitCodePipelineClient

            work_dir = session.get("work_dir", "")
            op_name = session.get("op_name", "")

            client = GitCodePipelineClient(token=gitcode_token)

            # 解析 fork 仓库：优先 fork_info，其次从 git remote origin 获取
            fork_owner, fork_repo = "", ""
            fork_info = session.get("fork_info") or {}
            fork_path = fork_info.get("fork_path", "")
            if fork_path and "/" in fork_path:
                fork_owner, fork_repo = fork_path.split("/", 1)

            if not fork_owner and work_dir:
                # 从 git remote origin URL 解析
                remote_result = await _run_git(
                    "remote", "get-url", "origin", cwd=work_dir
                )
                if remote_result["returncode"] == 0:
                    origin_url = remote_result["stdout"].strip()
                    match = re.search(r"[:/]([^/]+/[^/]+?)(?:\.git)?$", origin_url)
                    if match:
                        fork_owner, fork_repo = match.group(1).split("/", 1)
                        logger.info(
                            f"[pipeline] 从 origin URL 解析 fork: {fork_owner}/{fork_repo}"
                        )

            # 解析上游仓库：优先 repo_url，其次 upstream remote，最后 API 查 fork parent
            upstream_owner, upstream_repo = "", ""
            repo_url = session.get("repo_url", "")
            if repo_url:
                match = re.search(r"[:/]([^/]+/[^/]+?)(?:\.git)?$", repo_url)
                if match:
                    upstream_owner, upstream_repo = match.group(1).split("/", 1)

            if not upstream_owner and work_dir:
                # 尝试从 upstream remote 获取
                upstream_result = await _run_git(
                    "remote", "get-url", "upstream", cwd=work_dir
                )
                if upstream_result["returncode"] == 0:
                    upstream_url = upstream_result["stdout"].strip()
                    match = re.search(r"[:/]([^/]+/[^/]+?)(?:\.git)?$", upstream_url)
                    if match:
                        upstream_owner, upstream_repo = match.group(1).split("/", 1)
                        logger.info(
                            f"[pipeline] 从 upstream remote 解析: {upstream_owner}/{upstream_repo}"
                        )

            if not upstream_owner and fork_owner:
                # 通过 API 查询 fork 仓库的 parent（源仓库）和默认分支
                try:
                    info = await client.get_repo_info(fork_owner, fork_repo)
                    if info.get("parent_owner"):
                        upstream_owner, upstream_repo = (
                            info["parent_owner"],
                            info["parent_repo"],
                        )
                        logger.info(
                            f"[pipeline] 从 API 查询 fork parent: {upstream_owner}/{upstream_repo}"
                        )
                    if info.get("default_branch"):
                        logger.info(
                            f"[pipeline] fork 默认分支: {info['default_branch']}"
                        )
                except Exception as e:
                    logger.warning(f"[pipeline] 查询 fork info 失败: {e}")

            # 兜底：如果只有一个，互相赋值
            if not fork_owner:
                fork_owner, fork_repo = upstream_owner, upstream_repo
            if not upstream_owner:
                upstream_owner, upstream_repo = fork_owner, fork_repo

            # 检测 upstream 与 fork 相同（说明上游解析失败）
            is_same_repo = (
                f"{upstream_owner}/{upstream_repo}" == f"{fork_owner}/{fork_repo}"
            )
            if is_same_repo:
                logger.warning(
                    f"[pipeline] upstream 与 fork 相同: {fork_owner}/{fork_repo}，上游仓库解析失败"
                )
                err_data = {
                    "status": "failed",
                    "error": "无法确定上游仓库。请在工作目录执行: git remote add upstream <上游仓库URL>",
                    "completed_at": datetime.now().isoformat(),
                }
                yield f"event: pipeline_done\ndata: {json.dumps(err_data, ensure_ascii=False)}\n\n"
                return

            # 获取当前分支
            branch_result = await _run_git(
                "rev-parse", "--abbrev-ref", "HEAD", cwd=work_dir
            )
            source_branch = (
                branch_result["stdout"] if branch_result["returncode"] == 0 else "main"
            )

            # 自动检测上游默认分支（而非硬编码 main）
            target_branch = "main"
            if upstream_owner:
                try:
                    upstream_info = await client.get_repo_info(
                        upstream_owner, upstream_repo
                    )
                    if upstream_info.get("default_branch"):
                        target_branch = upstream_info["default_branch"]
                        logger.info(f"[pipeline] 上游默认分支: {target_branch}")
                except Exception:
                    pass

            # 重置 pipeline 状态
            from app.services.pipeline_service import _new_steps

            pipeline = session.get("pipeline", {})
            pipeline["status"] = "running"
            pipeline["steps"] = _new_steps()
            pipeline["triggered_at"] = None
            pipeline["completed_at"] = None
            pipeline["fix_rounds"] = []

            # 查找已有 PR（复用，避免重复创建）
            existing_mr_iid = (
                pipeline.get("mr_iid")
                or session.get("pipeline", {}).get("mr_iid")
                or ""
            )
            existing_mr_url = (
                pipeline.get("mr_url")
                or session.get("pipeline", {}).get("mr_url")
                or ""
            )
            if not existing_mr_iid and upstream_owner:
                existing_mr = await client.find_open_mr(
                    upstream_owner,
                    upstream_repo,
                    source_branch,
                    fork_owner=fork_owner,
                )
                if existing_mr:
                    existing_mr_iid = existing_mr["mr_iid"]
                    existing_mr_url = existing_mr["mr_url"]
                    logger.info(f"[pipeline] 复用已有 PR: {existing_mr_url}")

            if existing_mr_iid:
                pipeline["mr_iid"] = existing_mr_iid
                pipeline["mr_url"] = existing_mr_url

            await db.update_workflow_sim_v2_session(session_id, {"pipeline": pipeline})

            try:
                async for event in client.run_pipeline_lifecycle(
                    work_dir=work_dir,
                    owner=fork_owner,
                    repo=fork_repo,
                    source_branch=source_branch,
                    target_branch=target_branch,
                    op_name=op_name,
                    op_spec=session.get("op_spec", ""),
                    session_id=session_id,
                    upstream_owner=upstream_owner,
                    upstream_repo=upstream_repo,
                    fork_owner=fork_owner,
                    fork_repo=fork_repo,
                    existing_mr_iid=str(existing_mr_iid),
                    existing_mr_url=existing_mr_url,
                    cancel_check=lambda sid=session_id: _pipeline_cancel_flags.get(
                        sid, False
                    ),
                ):
                    sse_event = event.get("sse_event", "")
                    event_data = event.get("data", {})
                    if sse_event:
                        yield f"event: {sse_event}\ndata: {json.dumps(event_data, ensure_ascii=False)}\n\n"
                        # 取消后清理 flag 并退出
                        if (
                            sse_event == "pipeline_done"
                            and event_data.get("status") == "cancelled"
                        ):
                            _pipeline_cancel_flags.pop(session_id, None)
                            break
                        # 更新 pipeline 到 DB
                        if db:
                            current = await db.get_workflow_sim_v2_session(session_id)
                            if current:
                                p = current.get("pipeline", {})
                                if sse_event == "pipeline_start":
                                    p["status"] = "running"
                                    p["mr_url"] = event_data.get("mr_url")
                                    p["mr_iid"] = event_data.get("mr_iid")
                                    p["triggered_at"] = event_data.get("triggered_at")
                                    p["steps"] = event_data.get(
                                        "steps", p.get("steps", [])
                                    )
                                elif sse_event == "pipeline_step_update":
                                    p["steps"] = event_data.get(
                                        "steps", p.get("steps", [])
                                    )
                                    if event_data.get("mr_url"):
                                        p["mr_url"] = event_data["mr_url"]
                                    if event_data.get("mr_iid"):
                                        p["mr_iid"] = event_data["mr_iid"]
                                elif sse_event == "pipeline_done":
                                    p["status"] = event_data.get("status")
                                    p["completed_at"] = event_data.get("completed_at")
                                    p["steps"] = event_data.get(
                                        "steps", p.get("steps", [])
                                    )
                                elif sse_event == "pipeline_fix_round":
                                    fr = p.get("fix_rounds", [])
                                    fr.append(event_data)
                                    p["fix_rounds"] = fr
                                await db.update_workflow_sim_v2_session(
                                    session_id, {"pipeline": p}
                                )
            except Exception as e:
                logger.error(f"手动触发 Pipeline 异常: {e}", exc_info=True)
                yield f"event: pipeline_done\ndata: {json.dumps({'status': 'failed', 'error': str(e), 'completed_at': datetime.now().isoformat()}, ensure_ascii=False)}\n\n"

        return StreamingResponse(
            pipeline_event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

