"""工作流仿真 V2 路由 — register_diagnosis_routes（由 workflow_sim_v2.py 拆分）

插件断点诊断：按 plugin_id 聚合该插件所有已完成 session，
产出跨样本的「断点/病灶」视图（步骤失败率、错误分类分布、Skill 漏读排行、产物缺失排行）。
"""

from fastapi import APIRouter
from fastapi.responses import Response

from app.services.report_scorer import build_breakpoint_diagnosis


def register_diagnosis_routes(router: APIRouter, db=None):
    # ==================== 插件断点诊断 ====================

    @router.get("/cannbot/workflow-v2/diagnosis")
    async def get_breakpoint_diagnosis(plugin_id: str, limit: int = 50):
        """按 plugin_id 聚合断点诊断。

        返回 build_breakpoint_diagnosis 的 JSON 结构。
        无 session 时返回 meta.session_count=0 的空结构（不报错）。
        """
        if not db:
            return {"error": "数据库未连接"}
        if not plugin_id:
            return {"error": "plugin_id 必填"}
        sessions = await db.get_workflow_sim_v2_sessions_by_plugin(plugin_id, limit)
        return build_breakpoint_diagnosis(sessions, plugin_id)

    @router.get("/cannbot/workflow-v2/diagnosis/export")
    async def export_breakpoint_diagnosis(plugin_id: str, limit: int = 50):
        """导出插件断点诊断 Markdown 报告。"""
        if not db:
            return {"error": "数据库未连接"}
        if not plugin_id:
            return {"error": "plugin_id 必填"}
        sessions = await db.get_workflow_sim_v2_sessions_by_plugin(plugin_id, limit)
        diag = build_breakpoint_diagnosis(sessions, plugin_id)

        meta = diag.get("meta") or {}
        lines = []
        lines.append(f"# 插件断点诊断报告 — {plugin_id}")
        lines.append("")
        lines.append(
            f"跨 **{meta.get('session_count', 0)}** 次仿真（覆盖 "
            f"{meta.get('op_count', 0)} 个算子）聚合该插件工作流的断点与病灶。"
        )
        lines.append("")

        # 概览
        lines.append("## 概览")
        lines.append("")
        lines.append("| 指标 | 值 |")
        lines.append("|------|-----|")
        lines.append(f"| 仿真样本数 | {meta.get('session_count', 0)} |")
        lines.append(f"| 覆盖算子数 | {meta.get('op_count', 0)} |")
        vd = meta.get("verdict_distribution") or {}
        lines.append(
            f"| verdict 分布 | "
            + " / ".join(f"{k}={v}" for k, v in vd.items())
            + " |"
        )
        lines.append("")

        # 步骤断点排行
        lines.append("## 步骤断点排行（按失败率降序）")
        lines.append("")
        sb = diag.get("step_breakdown") or []
        if sb:
            lines.append("| 步骤 | 出现 | 失败 | 失败率 | 门禁未通过 | 平均耗时(s) | 主要错误 |")
            lines.append("|------|------|------|--------|------------|-------------|----------|")
            for s in sb:
                cats = s.get("error_categories") or {}
                top_cat = ", ".join(f"{k}×{v}" for k, v in
                                    sorted(cats.items(), key=lambda x: -x[1])[:2])
                lines.append(
                    f"| {s.get('step_name', '')} | {s.get('appear', 0)} | {s.get('failed', 0)} | "
                    f"{round((s.get('fail_rate') or 0) * 100)}% | {s.get('gate_failed', 0)} | "
                    f"{round((s.get('avg_duration_ms') or 0) / 1000)} | {top_cat} |"
                )
        else:
            lines.append("_无步骤数据_")
        lines.append("")

        # 错误类型分布
        ecd = diag.get("error_category_distribution") or {}
        lines.append("## 错误类型分布")
        lines.append("")
        if ecd:
            lines.append("| 错误类型 | 次数 |")
            lines.append("|----------|------|")
            for k, v in sorted(ecd.items(), key=lambda x: -x[1]):
                lines.append(f"| {k} | {v} |")
        else:
            lines.append("_无错误_")
        lines.append("")

        # 告警类型分布
        atd = diag.get("alert_type_distribution") or {}
        lines.append("## 告警类型分布")
        lines.append("")
        if atd:
            lines.append("| 告警类型 | 次数 |")
            lines.append("|----------|------|")
            for k, v in sorted(atd.items(), key=lambda x: -x[1]):
                lines.append(f"| {k} | {v} |")
        else:
            lines.append("_无告警_")
        lines.append("")

        # Skill 漏读排行
        smr = diag.get("skill_missing_ranking") or []
        lines.append("## Skill 漏读排行（哪个 skill 最常未被引用）")
        lines.append("")
        if smr:
            lines.append("| Skill | 漏读次数 | 出现在 N 个 session | 发生步骤 |")
            lines.append("|-------|----------|---------------------|----------|")
            for s in smr:
                steps = ", ".join(s.get("steps") or [])
                lines.append(
                    f"| {s.get('skill', '')} | {s.get('missing_count', 0)} | "
                    f"{s.get('in_sessions', 0)} | {steps} |"
                )
        else:
            lines.append("_无漏读_")
        lines.append("")

        # 产物缺失排行
        amr = diag.get("artifact_missing_ranking") or []
        lines.append("## 门禁产物缺失排行（哪个产出物最常未生成）")
        lines.append("")
        if amr:
            lines.append("| 产物 | 缺失次数 | 发生步骤 |")
            lines.append("|------|----------|----------|")
            for a in amr:
                steps = ", ".join(a.get("steps") or [])
                lines.append(f"| {a.get('artifact', '')} | {a.get('missing_count', 0)} | {steps} |")
        else:
            lines.append("_无缺失_")
        lines.append("")

        md_content = "\n".join(lines)
        return Response(
            content=md_content,
            media_type="text/markdown; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="diagnosis-{plugin_id}.md"'
            },
        )
