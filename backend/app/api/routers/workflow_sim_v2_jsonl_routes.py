"""工作流仿真 V2 路由 — register_jsonl_routes（由 workflow_sim_v2.py 拆分）"""

import asyncio
import json
import logging
import os
import time
from datetime import datetime
from typing import Optional


from fastapi import APIRouter, BackgroundTasks
from fastapi.responses import StreamingResponse


from .workflow_sim_v2_jsonl import (
    claude_project_dir as _claude_project_dir,
    list_subagent_jsonls as _list_subagent_jsonls,
    pick_active_jsonl as _pick_active_jsonl,
    summarize_jsonl_line as _summarize_jsonl_line,
    read_jsonl_lines as _read_jsonl_lines,
    format_jsonl_sse as _format_jsonl_sse,
)

logger = logging.getLogger(__name__)


def _ts():
    return datetime.now().strftime("%H:%M:%S")


def register_jsonl_routes(router: APIRouter, db=None):
    @router.get("/cannbot/workflow-v2/sessions/{session_id}/tail-jsonl")
    async def tail_jsonl(session_id: str):
        """实时 tail 当前仿真 claude 正在写入的 jsonl 工作流水（Claude Code 原生存档）。

        与 stream_session（仿真执行驱动）独立，仅做只读文件 tail，生命周期并行、互不干扰。
        任意时刻只跟踪一个活跃 jsonl，绝不混读多个。
        """

        async def jsonl_generator():
            if not db:
                yield f"event: no_active\ndata: {json.dumps({'reason': '数据库未连接'})}\n\n"
                return
            session = await db.get_workflow_sim_v2_session(session_id)
            if not session:
                yield f"event: no_active\ndata: {json.dumps({'reason': '会话未找到'})}\n\n"
                return
            work_dir = session.get("work_dir", "")
            project_dir = _claude_project_dir(work_dir)
            session_status = session.get("status", "")

            current_path: Optional[str] = None  # 当前 tail 的 jsonl 绝对路径
            offset = 0  # current_path 已推送的行数（按行累计）
            last_growth = time.time()  # current_path 最后一次增长的时间
            seen_files: set = set()  # 已切换过的文件，避免重发历史

            # 仿真已结束也继续 tail 一小段，把残留增量发完；最多再跑 2 轮
            finished_drains = 0
            max_finished_drains = 2

            while True:
                # 仿真是否已结束
                fresh = await db.get_workflow_sim_v2_session(session_id)
                session_status = (fresh or {}).get("status", "")
                session_ended = session_status in ("completed", "stopped", "failed")

                if session_ended:
                    # 首次到达：排完当前文件残留增量 + subagent 最后写入
                    if finished_drains == 0 and current_path:
                        new_lines, offset = _read_jsonl_lines(current_path, offset)
                        for ln_obj in new_lines:
                            yield _format_jsonl_sse(ln_obj)
                    finished_drains += 1
                    if finished_drains >= max_finished_drains:
                        yield f"event: jsonl_done\ndata: {json.dumps({'reason': 'session ended'})}\n\n"
                        return
                    await asyncio.sleep(1.5)
                    continue

                # 仿真仍在跑：检测活跃文件
                active = _pick_active_jsonl(project_dir)

                # 文件切换处理：当前文件和活跃文件不一致时，切换
                if active and active != current_path:
                    current_path = active
                    fname = os.path.basename(active)
                    is_subagent = "/subagents/" in active
                    is_first_seen = active not in seen_files
                    seen_files.add(active)
                    if is_subagent:
                        _, offset = _read_jsonl_lines(current_path, 0)
                    elif is_first_seen:
                        # 首次切到主会话：补发历史 + 发切换事件
                        hist_lines, offset = _read_jsonl_lines(current_path, 0)
                        for ln_obj in hist_lines:
                            yield _format_jsonl_sse(ln_obj)
                        switch_data = {"file": fname, "kind": "main"}
                        yield f"event: jsonl_switch\ndata: {json.dumps(switch_data, ensure_ascii=False)}\n\n"
                    else:
                        # 已见过的文件：静默切换，不发事件，不重发历史
                        _, offset = _read_jsonl_lines(current_path, 0)
                    last_growth = time.time()
                    await asyncio.sleep(0)
                    continue

                if not active:
                    yield f"event: no_active\ndata: {json.dumps({'reason': '等待 claude 会话启动'})}\n\n"
                    await asyncio.sleep(1.5)
                    continue

                # 增量读取 current_path 自 offset 起新行
                new_lines, offset = _read_jsonl_lines(current_path, offset)
                if new_lines:
                    last_growth = time.time()
                    for ln_obj in new_lines:
                        yield _format_jsonl_sse(ln_obj)

                await asyncio.sleep(1.5)

        return StreamingResponse(
            jsonl_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @router.get("/cannbot/workflow-v2/sessions/{session_id}/jsonl-history")
    async def get_jsonl_history(session_id: str):
        """从磁盘回读已完成 session 的 jsonl 工作流水，供历史回看展示。

        读取 ~/.claude/projects/<enc>/ 下所有 jsonl 文件（主会话 + subagents），
        按 mtime 排序，用 _summarize_jsonl_line 解析为前端可渲染的行列表。
        """
        if not db:
            return {"lines": [], "error": "数据库未连接"}
        session = await db.get_workflow_sim_v2_session(session_id)
        if not session:
            return {"lines": [], "error": "会话未找到"}

        work_dir = session.get("work_dir", "")
        project_dir = _claude_project_dir(work_dir)
        if not project_dir or not os.path.isdir(project_dir):
            return {"lines": [], "error": "claude 项目目录不存在"}

        lines = []
        MAX_LINES_PER_FILE = 2000
        MAX_TOTAL_LINES = 8000

        # 收集所有 jsonl 文件：主会话 + subagent，按 mtime 排序
        all_files = []
        try:
            for f in os.listdir(project_dir):
                if f.endswith(".jsonl") and os.path.isfile(
                    os.path.join(project_dir, f)
                ):
                    all_files.append((os.path.join(project_dir, f), "main"))
        except Exception:
            pass
        for sub_path in _list_subagent_jsonls(project_dir):
            all_files.append((sub_path, "subagent"))
        all_files.sort(key=lambda x: os.path.getmtime(x[0]))

        for path, kind_tag in all_files:
            if len(lines) >= MAX_TOTAL_LINES:
                break
            fname = os.path.basename(path)
            is_sub = kind_tag == "subagent"
            label = f"── {'🤖 子Agent' if is_sub else '主会话'}: {fname} ──"
            lines.append(
                {
                    "kind": "subagent_switch" if is_sub else "switch",
                    "summary": label,
                    "ts": "",
                    "type": "",
                }
            )

            objs, _ = _read_jsonl_lines(path, 0)
            for obj in objs[:MAX_LINES_PER_FILE]:
                if len(lines) >= MAX_TOTAL_LINES:
                    break
                k, s = _summarize_jsonl_line(obj)
                if k == "other" and not s:
                    continue
                lines.append(
                    {
                        "ts": obj.get("timestamp", ""),
                        "kind": k,
                        "summary": s,
                        "type": obj.get("type", ""),
                    }
                )

        return {"lines": lines, "total": len(lines)}
