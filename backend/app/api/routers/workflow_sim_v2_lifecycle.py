"""工作流仿真 V2 路由 — register_lifecycle_routes（由 workflow_sim_v2.py 拆分）"""

import asyncio
import logging
import time
from datetime import datetime


from fastapi import APIRouter, BackgroundTasks
from fastapi.responses import StreamingResponse

from app.services.claude_code_driver import claude_driver, ClaudeCodeDriver
from app.services.report_scorer import (
    compute_dimension_scores,
)

from .workflow_sim_v2_helpers import (
    _pipeline_cancel_flags,
    get_or_create_bus as _get_or_create_bus,
    format_sse as _format_sse,
    project_snapshot as _project_snapshot,
    _fill_legacy_logs,
)
from .workflow_sim_v2_drive import (
    ensure_session_task_running as _ensure_session_task_running,
)

logger = logging.getLogger(__name__)


def _ts():
    return datetime.now().strftime("%H:%M:%S")


def register_lifecycle_routes(router: APIRouter, db=None):
    @router.post("/cannbot/workflow-v2/sessions/{session_id}/start")
    async def start_session(session_id: str, gitcode_token: str = ""):
        """启动仿真：标记 running + fire-and-forget 后台执行 Task（与 SSE 解耦）。
        仿真在后端独立跑，前端连 SSE 只做只读订阅；刷新/断开不杀进程。"""
        if not db:
            return {"error": "数据库未连接"}
        session = await db.get_workflow_sim_v2_session(session_id)
        if not session:
            return {"error": "会话未找到"}
        await db.update_workflow_sim_v2_session(session_id, {"status": "running"})
        started = _ensure_session_task_running(session_id, session, db, gitcode_token)
        return {
            "session_id": session_id,
            "status": "running",
            "task_already_running": not started,
        }

    @router.post("/cannbot/workflow-v2/sessions/{session_id}/stop")
    async def stop_session(session_id: str):
        """停止仿真：杀进程 + 标记状态"""
        claude_driver.stop(session_id)
        if db:
            session = await db.get_workflow_sim_v2_session(session_id)
            if session:
                steps = session.get("steps", [])
                for s in steps:
                    if s.get("status") == "running":
                        s["status"] = "failed"
                        s["completed_at"] = datetime.now().isoformat()
                await db.update_workflow_sim_v2_session(
                    session_id,
                    {
                        "status": "stopped",
                        "steps": steps,
                        "completed_at": datetime.now().isoformat(),
                    },
                )
        return {"session_id": session_id, "stopped": True}

    @router.post("/cannbot/workflow-v2/sessions/{session_id}/cancel-pipeline")
    async def cancel_pipeline(session_id: str):
        """取消正在运行的 CI/CD 流水线"""
        _pipeline_cancel_flags[session_id] = True
        # 同时更新 DB 中 pipeline 状态
        if db:
            session = await db.get_workflow_sim_v2_session(session_id)
            if session:
                p = session.get("pipeline", {})
                if p.get("status") == "running":
                    p["status"] = "cancelled"
                    p["completed_at"] = datetime.now().isoformat()
                    steps = p.get("steps", [])
                    for s in steps:
                        if s.get("status") == "running":
                            s["status"] = "cancelled"
                    await db.update_workflow_sim_v2_session(session_id, {"pipeline": p})
        return {"session_id": session_id, "cancelled": True}

    @router.get("/cannbot/workflow-v2/sessions/{session_id}/stream")
    async def stream_session(session_id: str, gitcode_token: str = ""):
        """SSE 实时流：驱动 Claude Code CLI 按步骤执行"""
        if not db:
            return {"error": "数据库未连接"}

        session = await db.get_workflow_sim_v2_session(session_id)
        if not session:
            return {"error": "会话未找到"}

        # 将 gitcode_token 注入到 session 中（不入库，仅 SSE 生命周期内使用）
        if gitcode_token:
            session["_gitcode_token"] = gitcode_token

        async def event_generator():
            """薄订阅器：发 DB 全量快照 + 订阅 EventBus 实时事件。
            与仿真执行解耦——断开只取消订阅，不影响后台 Task/Claude 进程。"""
            # 确保后台 Task 在跑（SSE 重连场景：Task 可能已在跑或已结束）
            _ensure_session_task_running(session_id, session, db, gitcode_token)

            # 1) 发 DB 全量快照（统一首次/重连/重启后重连三条路径）
            snap = await db.get_workflow_sim_v2_session(session_id)
            if snap:
                yield _format_sse(
                    {"event": "session_snapshot", "data": _project_snapshot(snap)}
                )

            # 2) 订阅实时事件
            bus = _get_or_create_bus(session_id)
            q = await bus.subscribe()
            try:
                while True:
                    if bus.finished and q.empty():
                        break
                    try:
                        ev = await asyncio.wait_for(q.get(), timeout=15.0)
                    except asyncio.TimeoutError:
                        yield ": keepalive\n\n"  # 心跳，防代理超时
                        continue
                    if ev.get("event") == "_eof":
                        break
                    yield _format_sse(ev)
            finally:
                await bus.unsubscribe(q)  # 仅取消订阅，不动 Task/进程

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @router.get("/cannbot/workflow-v2/sessions/{session_id}/arbitrator-reports")
    async def get_arbitrator_reports(session_id: str):
        """获取某个 session 的所有裁判报告（结构化断点数据）。"""
        if not db:
            return {"error": "数据库未连接", "reports": []}
        try:
            reports = await db.get_arbitrator_reports(session_id)
            for r in reports:
                r.pop("_id", None)  # 去掉 MongoDB ObjectId
            return {"session_id": session_id, "reports": reports, "count": len(reports)}
        except Exception as e:
            return {"error": str(e), "reports": []}

    @router.get("/cannbot/workflow-v2/sessions/{session_id}/export")
    async def export_session_log(session_id: str, format: str = "md"):
        """导出会话日志为 Markdown 文件"""
        if not db:
            return {"error": "数据库未连接"}

        session = await db.get_workflow_sim_v2_session(session_id)
        if not session:
            return {"error": "会话未找到"}

        from fastapi.responses import Response

        op_name = session.get("op_name", "unknown")
        plugin_name = session.get("plugin_name", "")
        created_at = session.get("created_at", "")
        work_dir = session.get("work_dir", "")
        steps = session.get("steps", [])
        summary = session.get("summary")
        alerts = session.get("breakpoint_alerts", [])
        terminal_log = session.get("terminal_log", [])
        simulation_log = session.get("simulation_log", [])

        # 兼容老会话
        if not terminal_log or not simulation_log:
            session = _fill_legacy_logs(session)
            terminal_log = session.get("terminal_log", terminal_log)
            simulation_log = session.get("simulation_log", simulation_log)

        lines = []
        lines.append(f"# 工作流仿真报告")
        lines.append("")
        lines.append(f"| 字段 | 值 |")
        lines.append(f"|------|-----|")
        lines.append(f"| 会话 ID | `{session_id}` |")
        lines.append(f"| 算子 | {op_name} |")
        lines.append(f"| 插件 | {plugin_name} |")
        lines.append(f"| 工作目录 | `{work_dir}` |")
        lines.append(f"| 创建时间 | {created_at} |")
        lines.append(f"| 完成时间 | {session.get('completed_at', '-')} |")
        if summary:
            lines.append(f"| 总评 | **{summary.get('verdict', '-')}** |")
            lines.append(
                f"| 步骤通过 | {summary.get('passed_steps', 0)}/{summary.get('total_steps', 0)} |"
            )
            lines.append(
                f"| 告警总数 | {summary.get('total_alerts', 0)} ({summary.get('critical_alerts', 0)} CRITICAL) |"
            )
            tokens = summary.get("total_tokens", {})
            lines.append(
                f"| Token | input {tokens.get('input', 0):,} / output {tokens.get('output', 0):,} |"
            )

        # 维度评分（可用性评估核心）
        lines.append("")
        lines.append("## 可用性维度评分")
        lines.append("")
        dim_result = compute_dimension_scores(session)
        lines.append(f"**加权总分：{dim_result['weighted_total']} / 100**")
        lines.append("")
        lines.append("| 维度 | 得分 | 权重 | 说明 |")
        lines.append("|------|------|------|------|")
        dim_names = {
            "design_quality": "设计质量",
            "code_quality": "代码质量",
            "boundary_compliance": "职责边界合规",
            "design_impl_consistency": "设计-实现一致性",
            "skill_compliance": "Skill 遵从度",
            "gate_pass_rate": "门禁通过率",
            "token_efficiency": "Token 效率",
            "cicd_result": "CI/CD 结果",
            "fix_efficiency": "修复效率",
        }
        for dim, info in dim_result["dimensions"].items():
            name = dim_names.get(dim, dim)
            if info["na"]:
                score_str = "N/A"
                note = info.get("reason", "")
            else:
                score_str = f"{info['score']}"
                note = ""
            lines.append(f"| {name} | {score_str} | {info['weight']} | {note} |")
        lines.append("")
        lines.append("")

        # 步骤详情
        lines.append("## 步骤详情")
        lines.append("")
        for i, step in enumerate(steps):
            status = step.get("status", "unknown")
            status_emoji = {
                "completed": "✅",
                "running": "🔄",
                "failed": "❌",
                "pending": "⏳",
            }.get(status, "❓")
            duration = step.get("duration_ms", 0)
            gate = step.get("gate_passed")
            gate_str = "通过" if gate else "未通过" if gate is False else "-"
            lines.append(
                f"### {status_emoji} Step {i + 1}: {step.get('step_name', step.get('step_id', ''))}"
            )
            lines.append("")
            lines.append(f"- **状态**: {status}")
            if duration:
                lines.append(f"- **耗时**: {duration}ms ({duration / 1000:.1f}s)")
            lines.append(f"- **门禁**: {gate_str}")
            proc = step.get("process")
            if proc:
                lines.append(
                    f"- **进程**: PID {proc.get('pid', '-')}, exit code {proc.get('exit_code', '-')}, {proc.get('elapsed_sec', '-')}s"
                )
            ed = step.get("error_detail")
            if ed:
                lines.append(f"- **错误分类**: {ed.get('category', 'UNKNOWN')}")
                lines.append(f"- **根因**: {ed.get('root_cause', '-')}")
                lines.append(f"- **建议**: {ed.get('suggestion', '-')}")
                lines.append(f"- **原始错误**: `{ed.get('original_error', '-')}`")
            sc = step.get("skill_compliance")
            if sc:
                lines.append(
                    f"- **Skill 遵从度**: {sc.get('score', 0) * 100:.0f}% (引用: {', '.join(sc.get('skills_referenced', [])) or '无'}, 缺失: {', '.join(sc.get('skills_missing', [])) or '无'})"
                )
            ga = step.get("gate_artifacts", [])
            if ga:
                for a in ga:
                    lines.append(
                        f"  - {'✅' if a.get('exists') else '❌'} {a.get('name', '')}"
                    )
            lines.append("")

        # 告警
        if alerts:
            lines.append("## 告警列表")
            lines.append("")
            for a in alerts:
                severity = a.get("severity", "UNKNOWN")
                cat = a.get("error_category", a.get("type", ""))
                lines.append(f"### [{severity}] {a.get('message', '')}")
                lines.append("")
                if a.get("root_cause"):
                    lines.append(f"- **根因**: {a['root_cause']}")
                if a.get("suggestion"):
                    lines.append(f"- **建议**: {a['suggestion']}")
                if a.get("step_id"):
                    lines.append(f"- **步骤**: {a['step_id']}")
                if a.get("detected_at"):
                    lines.append(f"- **时间**: {a['detected_at']}")
                lines.append("")

        # 仿真日志
        if simulation_log:
            lines.append("## 仿真日志")
            lines.append("")
            lines.append("```")
            for entry in simulation_log:
                prefix = {
                    "info": "INFO ",
                    "warn": "WARN ",
                    "error": "ERROR",
                    "success": " OK  ",
                }.get(entry.get("type", ""), "     ")
                lines.append(
                    f"[{entry.get('time', '')}] {prefix} {entry.get('text', '')}"
                )
            lines.append("```")
            lines.append("")

        # 终端输出
        if terminal_log:
            lines.append("## 终端输出")
            lines.append("")
            lines.append("```")
            for entry in terminal_log:
                t = entry.get("type", "")
                prefix = {
                    "tool_use": "🔧",
                    "tool_result": "⚙️",
                    "text": "📝",
                    "thinking": "💭",
                    "raw": "📄",
                }.get(t, "  ")
                lines.append(
                    f"[{entry.get('time', '')}] {prefix} [{t}] {entry.get('content', '')}"
                )
            lines.append("```")
            lines.append("")

        md_content = "\n".join(lines)
        filename = f"sim-{session_id}-{op_name}.md"

        return Response(
            content=md_content,
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

