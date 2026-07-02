"""工作流仿真 V2 路由 — register_batch_routes（由 workflow_sim_v2.py 拆分）"""

import logging
import uuid
from datetime import datetime


from fastapi import APIRouter, BackgroundTasks

from app.services.report_scorer import (
    aggregate_project_report,
)

from .workflow_sim_v2_helpers import (
    CreateSessionRequest,
    CreateBatchRequest,
)
from .workflow_sim_v2_drive import (
    execute_session_task as _execute_session_task,
)

logger = logging.getLogger(__name__)


def _ts():
    return datetime.now().strftime("%H:%M:%S")


def register_batch_routes(router: APIRouter, db=None):
    # ==================== 项目级批量可用性评估 ====================

    async def _run_batch(batch_id: str, tasks: list, work_dir_prefix: str):
        """串行执行 batch 内所有任务，逐个创建 session 并驱动完成。"""
        session_ids = []
        for idx, t in enumerate(tasks):
            work_dir = f"{work_dir_prefix}-{batch_id}-{idx}"
            req = CreateSessionRequest(
                plugin_id=t.plugin_id,
                op_name=t.op_name,
                op_spec=t.op_spec,
                work_dir=work_dir,
                step_timeout=t.step_timeout,
                auto_pipeline=False,
            )
            # create_session 是本函数外层闭包内的嵌套函数，直接调用（旧代码误用 self.）
            created = await create_session(req)
            if isinstance(created, dict) and created.get("session_id"):
                sid = created["session_id"]
                session_ids.append(
                    {"session_id": sid, "plugin_id": t.plugin_id, "op_name": t.op_name}
                )
                await db.save_workflow_sim_v2_batch(
                    {
                        "batch_id": batch_id,
                        "status": "running",
                        "session_ids": session_ids,
                        "updated_at": datetime.now().isoformat(),
                    }
                )
                # 直接驱动后台执行 Task（与 SSE 解耦后不再自调 SSE 端点）
                await db.update_workflow_sim_v2_session(sid, {"status": "running"})
                await _execute_session_task(sid, db, "")
        # 全部完成，生成项目级汇总
        sessions = []
        for s in session_ids:
            sess = await db.get_workflow_sim_v2_session(s["session_id"])
            if sess:
                sessions.append(sess)
        report = aggregate_project_report(sessions)
        await db.save_workflow_sim_v2_batch(
            {
                "batch_id": batch_id,
                "status": "completed",
                "session_ids": session_ids,
                "report": report,
                "completed_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
            }
        )

    @router.post("/cannbot/workflow-v2/batch")
    async def create_batch(req: CreateBatchRequest, background_tasks: BackgroundTasks):
        """创建项目级批量可用性评估，后台串行执行所有任务。"""
        if not db:
            return {"error": "数据库未连接"}
        if not req.tasks:
            return {"error": "任务列表为空"}
        batch_id = uuid.uuid4().hex[:12]
        await db.save_workflow_sim_v2_batch(
            {
                "batch_id": batch_id,
                "status": "pending",
                "session_ids": [],
                "task_count": len(req.tasks),
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
            }
        )
        background_tasks.add_task(
            _run_batch, batch_id, req.tasks, req.work_dir_prefix
        )
        return {"batch_id": batch_id, "status": "pending", "task_count": len(req.tasks)}

    @router.get("/cannbot/workflow-v2/batches")
    async def list_batches(limit: int = 30):
        if not db:
            return {"error": "数据库未连接"}
        return {"batches": await db.list_workflow_sim_v2_batches(limit)}

    @router.get("/cannbot/workflow-v2/batches/{batch_id}")
    async def get_batch(batch_id: str):
        if not db:
            return {"error": "数据库未连接"}
        batch = await db.get_workflow_sim_v2_batch(batch_id)
        if not batch:
            return {"error": "批量评估未找到"}
        return batch

    @router.get("/cannbot/workflow-v2/batches/{batch_id}/export")
    async def export_batch_report(batch_id: str):
        """导出项目级可用性评估 Markdown 报告"""
        from fastapi.responses import Response

        if not db:
            return {"error": "数据库未连接"}
        batch = await db.get_workflow_sim_v2_batch(batch_id)
        if not batch:
            return {"error": "批量评估未找到"}
        report = batch.get("report")
        # 若 report 未生成（仍在跑），实时从已完成 session 汇总
        if not report:
            sessions = []
            for s in batch.get("session_ids", []):
                sess = await db.get_workflow_sim_v2_session(s.get("session_id"))
                if sess:
                    sessions.append(sess)
            report = aggregate_project_report(sessions)

        lines = []
        lines.append("# cannbot-skills 项目可用性仿真评估报告")
        lines.append("")
        lines.append("## 评估对象")
        lines.append("")
        lines.append(
            "本报告评估 **cannbot-skills 开源算子开发 skill 插件库** 结合 AI 辅助开发算子的可行性与可用性。"
        )
        lines.append(
            f"覆盖 {report.get('plugin_count', 0)} 个插件、{report.get('session_count', 0)} 次仿真。"
        )
        lines.append("")
        lines.append("## 结论")
        lines.append("")
        lines.append(f"| 指标 | 值 |")
        lines.append(f"|------|-----|")
        lines.append(f"| 项目可用性总分 | **{report.get('total_score', 0)} / 100** |")
        lines.append(f"| 结论 | **{report.get('conclusion', '-')}** |")
        lines.append(f"| 批次状态 | {batch.get('status', '-')} |")
        lines.append("")
        lines.append("## 各维度得分（跨所有仿真均值）")
        lines.append("")
        lines.append("| 维度 | 得分 | 权重 |")
        lines.append("|------|------|------|")
        dim_names = {
            "design_quality": "设计质量",
            "code_quality": "代码质量",
            "boundary_compliance": "职责边界合规",
            "design_impl_consistency": "设计-实现一致性",
            "skill_compliance": "Skill 遵从度",
            "gate_pass_rate": "门禁通过率",
            "token_efficiency": "Token 效率",
            "cicd_result": "CI/CD 结果",
        }
        for dim, info in (report.get("per_dim_avg") or {}).items():
            name = dim_names.get(dim, dim)
            score = (
                "N/A"
                if info.get("na") or info.get("score") is None
                else f"{info['score']}"
            )
            lines.append(f"| {name} | {score} | {info.get('weight', 0)} |")
        lines.append("")
        lines.append(
            "> CI/CD 结果、修复效率在本地优先仿真下标注 N/A（未跑真实 GitCode CI/CD）。"
        )
        lines.append("")
        lines.append("## 各插件小计")
        lines.append("")
        lines.append("| 插件 | 仿真次数 | 平均分 |")
        lines.append("|------|----------|--------|")
        for p in report.get("plugin_subtotals") or []:
            lines.append(
                f"| {p['plugin_id']} | {p['session_count']} | {p['avg_score']} |"
            )
        lines.append("")
        lines.append("## 各次仿真明细")
        lines.append("")
        lines.append("| Session | 插件 | 算子 | 总分 | verdict |")
        lines.append("|---------|------|------|------|---------|")
        for ps in report.get("per_session") or []:
            lines.append(
                f"| {ps.get('session_id', '')} | {ps.get('plugin_id', '')} | {ps.get('op_name', '')} | {ps.get('weighted_total', 0)} | {ps.get('verdict', '-')} |"
            )
        lines.append("")
        md_content = "\n".join(lines)
        return Response(
            content=md_content,
            media_type="text/markdown; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="batch-{batch_id}-report.md"'
            },
        )

