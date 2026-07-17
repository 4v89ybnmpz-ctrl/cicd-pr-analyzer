"""工作流仿真 V2 路由 — register_sessions_routes（由 workflow_sim_v2.py 拆分）"""

import asyncio
import logging
import os
import uuid
from datetime import datetime


from fastapi import APIRouter, BackgroundTasks

from app.services.claude_code_driver import claude_driver, ClaudeCodeDriver
from app.services.workflow_parser import build_workflow_definition

from .workflow_sim_v2_helpers import (
    _active_session_tasks,
    CreateSessionRequest,
    DEFAULT_PIPELINE_STAGES,
    find_plugin_dir as _find_plugin_dir,
    _fill_legacy_logs,
    build_pre_external_steps,
    build_post_external_steps,
    build_pre_platform_steps,
    build_post_platform_steps,
)

logger = logging.getLogger(__name__)


def _ts():
    return datetime.now().strftime("%H:%M:%S")


def register_sessions_routes(router: APIRouter, db=None):
    @router.post("/cannbot/workflow-v2/sessions")
    async def create_session(req: CreateSessionRequest):
        """创建 V2 仿真会话"""
        plugin_dir = _find_plugin_dir(req.plugin_id)
        if not plugin_dir:
            return {"error": f"插件 {req.plugin_id} 未找到"}

        wf = build_workflow_definition(plugin_dir)
        if not wf:
            return {"error": f"插件 {req.plugin_id} 工作流解析失败"}

        # work_dir 默认用插件目录（仓库根），prompt 中路径为 operators/<op>/docs/*.md（仓库根相对）
        if req.work_dir:
            work_dir = req.work_dir
        else:
            work_dir = plugin_dir
        os.makedirs(work_dir, exist_ok=True)

        session_id = uuid.uuid4().hex[:12]
        now = datetime.now().isoformat()

        # ===== 自动安装插件到 work_dir =====
        install_result = {"status": "skipped", "skills": [], "agents": []}
        claude_dir = os.path.join(work_dir, ".claude")
        already_installed = os.path.isdir(
            os.path.join(claude_dir, "skills")
        ) and os.path.isdir(os.path.join(claude_dir, "agents"))

        if not already_installed:
            # 优先用 symlink 复用插件已有的 .claude/（秒装，切分支自动更新）
            plugin_claude_dir = os.path.join(plugin_dir, ".claude")
            if os.path.isdir(plugin_claude_dir):
                try:
                    if not os.path.exists(claude_dir):
                        os.symlink(plugin_claude_dir, claude_dir)
                    install_result = {"status": "symlinked"}
                except Exception as e:
                    logger.warning(f"symlink .claude 失败: {e}，回退到 init.sh")
                    already_installed = False

            # symlink 失败则用 init.sh
            if install_result.get("status") != "symlinked":
                init_sh = os.path.join(plugin_dir, "init.sh")
                if os.path.isfile(init_sh):
                    try:
                        proc = await asyncio.create_subprocess_exec(
                            "bash",
                            "init.sh",
                            "project",
                            "claude",
                            work_dir,
                            cwd=plugin_dir,
                            stdout=asyncio.subprocess.PIPE,
                            stderr=asyncio.subprocess.PIPE,
                        )
                        stdout, stderr = await asyncio.wait_for(
                            proc.communicate(), timeout=60
                        )
                        if proc.returncode == 0:
                            install_result = {
                                "status": "installed",
                                "stdout": stdout.decode("utf-8", errors="replace")[
                                    -500:
                                ],
                            }
                        else:
                            install_result = {
                                "status": "failed",
                                "error": stderr.decode("utf-8", errors="replace")[:500],
                            }
                            logger.warning(
                                f"插件安装失败 [{req.plugin_id}]: {install_result['error']}"
                            )
                    except Exception as e:
                        install_result = {"status": "failed", "error": str(e)}
                        logger.warning(f"插件安装异常 [{req.plugin_id}]: {e}")
        else:
            install_result = {"status": "already_installed"}

        # 扫描安装结果：列出 work_dir/.claude/ 下已安装的 skills 和 agents
        installed_skills = []
        installed_agents = []
        skills_dir = os.path.join(work_dir, ".claude", "skills")
        agents_dir = os.path.join(work_dir, ".claude", "agents")
        if os.path.isdir(skills_dir):
            installed_skills = sorted(
                [
                    d
                    for d in os.listdir(skills_dir)
                    if os.path.isdir(os.path.join(skills_dir, d))
                    or os.path.islink(os.path.join(skills_dir, d))
                ]
            )
        if os.path.isdir(agents_dir):
            installed_agents = sorted(
                [
                    f.replace(".md", "")
                    for f in os.listdir(agents_dir)
                    if f.endswith(".md")
                ]
            )
        install_result["skills"] = installed_skills
        install_result["agents"] = installed_agents
        logger.info(
            f"插件安装扫描 [{req.plugin_id}] → {work_dir}: status={install_result['status']}, skills={len(installed_skills)}, agents={len(installed_agents)}"
        )

        steps = []
        plugin_steps_raw = []
        for i, step in enumerate(wf.steps):
            prompt_template = step.prompt_def.prompt_template if step.prompt_def else ""
            required_skills = (
                step.prompt_def.required_skills + step.prompt_def.recommended_skills
                if step.prompt_def
                else []
            )
            artifacts = [
                a.replace("{operator_name}", req.op_name)
                for a in (step.output_artifacts or [])
            ]

            plugin_steps_raw.append(
                {
                    "step_id": step.step_id,
                    "step_name": step.name,
                    "step_index": i,
                    "status": "pending",
                    "prompt_template": prompt_template,
                    "required_skills": required_skills,
                    "output_artifacts": artifacts,
                    "dispatch_target": step.dispatch_target,
                    "fallback": step.fallback,
                    "sub_steps": [
                        {
                            "step_id": ss.step_id,
                            "name": ss.name,
                            "dispatch_target": ss.dispatch_target,
                            "output_artifacts": ss.output_artifacts,
                            "status": "pending",
                        }
                        for ss in (step.sub_steps or [])
                    ],
                    "output": "",
                    "events": [],
                    "duration_ms": 0,
                    "gate_passed": None,
                    "gate_artifacts": [],
                    "skill_compliance": None,
                    "token_usage": {},
                    "started_at": None,
                    "completed_at": None,
                }
            )

        # 初始化流水线编排步骤
        pipeline_steps = [
            {
                **s,
                "status": "pending",
                "log": None,
                "started_at": None,
                "completed_at": None,
                "duration_ms": 0,
            }
            for s in DEFAULT_PIPELINE_STAGES
        ]

        # 组装完整生命周期 steps：前置(clone) → 平台(安装环境) → 插件开发流程 → 平台(上库) → 后置(NPU/CI-CD)
        # - external 步骤仅前端展示、不进 Claude（drive.py 按 step_type=external 跳过）
        # - platform 步骤进 Claude 执行，prompt 由平台写死（非插件 task-prompts.md）
        pre_steps = build_pre_external_steps(start_index=0)
        pre_platform = build_pre_platform_steps(start_index=len(pre_steps))
        _offset = len(pre_steps) + len(pre_platform)
        for ps in plugin_steps_raw:
            ps["step_index"] = ps["step_index"] + _offset
        post_platform = build_post_platform_steps(
            start_index=_offset + len(plugin_steps_raw)
        )
        post_steps = build_post_external_steps(
            start_index=_offset + len(plugin_steps_raw) + len(post_platform)
        )
        steps = pre_steps + pre_platform + plugin_steps_raw + post_platform + post_steps

        session = {
            "session_id": session_id,
            "plugin_id": req.plugin_id,
            "plugin_name": wf.plugin_name,
            "op_name": req.op_name,
            "op_spec": req.op_spec,
            "work_dir": work_dir,
            "install_result": install_result,
            "step_timeout": req.step_timeout,
            "status": "pending",
            "steps": steps,
            "breakpoint_alerts": [],
            "summary": None,
            "pipeline": {
                "status": "pending",
                "mr_url": None,
                "mr_iid": None,
                "steps": pipeline_steps,
                "triggered_at": None,
                "completed_at": None,
                "fix_rounds": [],
            },
            "auto_pipeline": req.auto_pipeline,
            "repo_url": req.repo_url,
            "fork_info": req.fork_info or {},
            "clone_status": req.clone_status,
            "npu_test": {
                "status": "pending",
                "host": None,
                "remote_dir": None,
                "build_cmd": None,
                "test_cmd": None,
                "steps": [],
                "logs": [],
                "summary": None,
                "triggered_at": None,
                "completed_at": None,
                "error": None,
                "error_detail": None,
            },
            "created_at": now,
            "completed_at": None,
            "total_steps": len([s for s in steps if s.get("step_type") != "external"]),
        }

        # gitcode_token 不持久化到 DB，仅用于 pipeline 执行
        session["_gitcode_token"] = req.gitcode_token

        if db:
            # gitcode_token 不入库
            db_data = {k: v for k, v in session.items() if k != "_gitcode_token"}
            await db.save_workflow_sim_v2_session(db_data)

        return session

    @router.get("/cannbot/workflow-v2/sessions")
    async def list_sessions(limit: int = 30):
        """列出 V2 仿真会话"""
        if db:
            sessions = await db.get_workflow_sim_v2_sessions(limit)
            return {"total": len(sessions), "sessions": sessions}
        return {"total": 0, "sessions": []}

    @router.get("/cannbot/workflow-v2/sessions/active")
    async def get_active_session():
        """获取所有正在运行的会话（支持多并发后台跑）。
        返回 {active: 首个或null, sessions: [所有running]}。active 字段兼容旧前端。"""
        if not db:
            return {"active": None, "sessions": []}
        sessions = await db.get_workflow_sim_v2_sessions(limit=100)
        running = [s for s in sessions if s.get("status") == "running"]
        # 标注每个是否有活跃后台 Task（区分真在跑 vs 僵尸）
        for s in running:
            t = _active_session_tasks.get(s.get("session_id"))
            s["task_alive"] = bool(t is not None and not t.done())
        return {"active": running[0] if running else None, "sessions": running}

    @router.get("/cannbot/workflow-v2/sessions/{session_id}")
    async def get_session(session_id: str, full_logs: bool = False):
        """获取 V2 仿真会话详情（full_logs=1 时返回全部日志，否则只返最后 100 条）"""
        if db:
            session = await db.get_workflow_sim_v2_session(session_id, full_logs=full_logs)
            if session:
                return _fill_legacy_logs(session)
        return {"error": "会话未找到"}

    @router.get("/cannbot/workflow-v2/sessions/{session_id}/process")
    async def get_session_process(session_id: str):
        """获取会话的 Claude 进程信息"""
        # 驱动器中的实时状态
        proc_info = claude_driver.get_process_info(session_id)
        # 每个步骤的进程信息
        step_procs = {}
        if db:
            session = await db.get_workflow_sim_v2_session(session_id)
            if session:
                for step in session.get("steps", []):
                    sid = step.get("step_id", "")
                    sp = claude_driver.get_step_process(session_id, sid)
                    if sp:
                        step_procs[sid] = sp
        return {
            "session_id": session_id,
            "process": proc_info,
            "step_processes": step_procs,
        }

    @router.get("/cannbot/workflow-v2/processes")
    async def list_all_processes():
        """列出所有被追踪的 Claude 进程"""
        return {"processes": claude_driver.get_all_processes()}

