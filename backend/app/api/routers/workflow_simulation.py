"""
工作流仿真 API 路由
提供工作流定义查询、仿真执行（SSE 实时流）、结果检索、跨插件对比等端点
"""
import json
import logging
import os
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.services.workflow_parser import scan_all_plugins, build_workflow_definition, CANNBOT_DIR
from app.services.workflow_simulator import simulate_workflow, PERSONAS
from app.services.antipattern_library import get_all_antipatterns
from app.models.workflow_models import ComparisonReport, PluginSimSummary

logger = logging.getLogger(__name__)

# 内存缓存（避免重复解析）
_definitions_cache = []


def register_workflow_simulation_routes(router: APIRouter, db=None, exporter=None):
    """注册工作流仿真路由"""

    # ==================== 工作流定义 ====================

    @router.get("/cannbot/workflow/definitions")
    async def list_workflow_definitions():
        """列出所有插件的工作流定义概要"""
        global _definitions_cache
        try:
            if not _definitions_cache:
                _definitions_cache = scan_all_plugins()
            return {
                "total": len(_definitions_cache),
                "plugins": [
                    {
                        "plugin_id": wf.plugin_id,
                        "plugin_name": wf.plugin_name,
                        "description": wf.description[:100] if wf.description else "",
                        "steps_count": len(wf.steps),
                        "skills_count": len(wf.required_skills),
                        "agents_count": len(wf.agent_defs),
                    }
                    for wf in _definitions_cache
                ],
            }
        except Exception as e:
            logger.error(f"获取工作流定义列表失败: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/cannbot/workflow/{plugin_id}/definition")
    async def get_workflow_definition(plugin_id: str):
        """获取指定插件的完整工作流定义"""
        global _definitions_cache
        try:
            if not _definitions_cache:
                _definitions_cache = scan_all_plugins()

            for wf in _definitions_cache:
                if wf.plugin_id == plugin_id:
                    return wf.model_dump()

            # 尝试直接解析
            import os
            for plugins_dir in ["plugins-official", "plugins-community"]:
                plugin_dir = os.path.join(CANNBOT_DIR, plugins_dir, plugin_id)
                if os.path.isdir(plugin_dir):
                    wf = build_workflow_definition(plugin_dir)
                    if wf:
                        return wf.model_dump()

            raise HTTPException(status_code=404, detail=f"插件 {plugin_id} 未找到")
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"获取工作流定义失败 [{plugin_id}]: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # ==================== 仿真执行 ====================

    class SimulateRequest(BaseModel):
        plugin_id: str
        persona: str = "intermediate"  # novice | intermediate | experienced
        step_range: Optional[list] = None  # [start, end] 步骤索引范围

    @router.post("/cannbot/workflow/simulate")
    async def run_simulation(req: SimulateRequest):
        """启动单个插件的工作流仿真"""
        try:
            # 查找工作流定义
            global _definitions_cache
            if not _definitions_cache:
                _definitions_cache = scan_all_plugins()

            wf = None
            for w in _definitions_cache:
                if w.plugin_id == req.plugin_id:
                    wf = w
                    break

            if not wf:
                # 尝试直接解析
                import os
                for plugins_dir in ["plugins-official", "plugins-community"]:
                    plugin_dir = os.path.join(CANNBOT_DIR, plugins_dir, req.plugin_id)
                    if os.path.isdir(plugin_dir):
                        wf = build_workflow_definition(plugin_dir)
                        break

            if not wf:
                raise HTTPException(status_code=404, detail=f"插件 {req.plugin_id} 未找到")

            if not wf.steps:
                raise HTTPException(status_code=400, detail=f"插件 {req.plugin_id} 没有可仿真的步骤")

            if req.persona not in PERSONAS:
                raise HTTPException(
                    status_code=400,
                    detail=f"无效角色: {req.persona}，可选: {list(PERSONAS.keys())}"
                )

            # 获取技能评估数据（复用 cannbot_skills 的评分）
            skill_evals = _get_skill_evaluations()

            # 步骤范围
            step_range = None
            if req.step_range and len(req.step_range) == 2:
                step_range = tuple(req.step_range)

            # 执行仿真
            result = await simulate_workflow(wf, req.persona, skill_evals, step_range)

            # 保存结果
            if db:
                await db.save_workflow_simulation(result.model_dump())

            return result.model_dump()

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"仿真执行失败: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # ==================== SSE 实时仿真 ====================

    @router.get("/cannbot/workflow/simulate-stream")
    async def stream_simulation(
        plugin_id: str = Query(...),
        persona: str = Query("intermediate"),
    ):
        """
        SSE 实时仿真流：每完成一个步骤就推送一个事件
        事件格式:
          event: step_done    — 单步完成
          event: summary      — 全部完成汇总
          event: error        — 出错
        """
        from app.services.workflow_simulator import (
            simulate_step, PERSONAS, _build_skill_heatmap,
        )
        from app.services.antipattern_library import get_antipatterns_for_plugin

        async def event_generator():
            try:
                # 查找工作流定义
                global _definitions_cache
                logger.info(f"[SSE] 开始仿真流 plugin_id={plugin_id}, persona={persona}")
                if not _definitions_cache:
                    _definitions_cache = scan_all_plugins()

                wf = None
                for w in _definitions_cache:
                    if w.plugin_id == plugin_id:
                        wf = w
                        break

                if not wf:
                    err = {"error": f"插件 {plugin_id} 未找到"}
                    yield f"event: error\ndata: {json.dumps(err, ensure_ascii=False)}\n\n"
                    return

                if not wf.steps:
                    err = {"error": "没有可仿真的步骤"}
                    yield f"event: error\ndata: {json.dumps(err, ensure_ascii=False)}\n\n"
                    return

                if persona not in PERSONAS:
                    err = {"error": f"无效角色: {persona}"}
                    yield f"event: error\ndata: {json.dumps(err, ensure_ascii=False)}\n\n"
                    return

                # 发送开始事件
                start_data = {"plugin_id": plugin_id, "plugin_name": wf.plugin_name, "total_steps": len(wf.steps), "persona": persona}
                yield f"event: start\ndata: {json.dumps(start_data, ensure_ascii=False)}\n\n"

                logger.info("[SSE] 获取技能评估数据...")
                skill_evals = _get_skill_evaluations()
                logger.info(f"[SSE] 技能评估完成, {len(skill_evals)} 个技能")
                context = {"plugin_id": plugin_id, "plugin_name": wf.plugin_name}

                step_results = []
                total_tokens = 0

                for i, step in enumerate(wf.steps):
                    # 发送步骤开始事件
                    step_start_data = {"step_id": step.step_id, "step_name": step.name, "step_index": i, "total": len(wf.steps)}
                    yield f"event: step_start\ndata: {json.dumps(step_start_data, ensure_ascii=False)}\n\n"

                    # 执行单步仿真
                    logger.info(f"[SSE] 仿真步骤 {i+1}/{len(wf.steps)}: {step.name}")
                    result = await simulate_step(step, persona, skill_evals, context)
                    step_results.append(result)
                    total_tokens += result.token_usage.get("prompt_tokens", 0) + result.token_usage.get("completion_tokens", 0)

                    # 推送单步结果
                    logger.info(f"[SSE] 步骤 {step.name} 完成, 推送结果")
                    yield f"event: step_done\ndata: {json.dumps(result.model_dump(), ensure_ascii=False)}\n\n"

                # 计算汇总
                overall_pass = sum(r.simulated_pass_rate for r in step_results) / len(step_results) if step_results else 0
                all_breakpoints = []
                critical_count = 0
                for r in step_results:
                    all_breakpoints.extend(r.breakpoints)
                    critical_count += sum(1 for bp in r.breakpoints if bp.severity == "CRITICAL")

                skill_heatmap = _build_skill_heatmap(wf, step_results)

                plugin_antipatterns = get_antipatterns_for_plugin(plugin_id)
                matched = []
                for ap in plugin_antipatterns:
                    suscept = ap.get("persona_susceptibility", {}).get(persona, 0.1)
                    if suscept > 0.2:
                        matched.append({
                            "id": ap["id"], "name": ap["name"],
                            "severity": ap["severity"], "susceptibility": suscept,
                            "mitigation": ap.get("mitigation", ""),
                        })

                summary = {
                    "simulation_id": uuid.uuid4().hex[:8],
                    "plugin_id": plugin_id,
                    "plugin_name": wf.plugin_name,
                    "persona": persona,
                    "overall_pass_rate": round(overall_pass, 3),
                    "total_breakpoints": len(all_breakpoints),
                    "critical_breakpoints": critical_count,
                    "skill_heatmap": skill_heatmap,
                    "antipatterns_matched": sorted(matched, key=lambda x: x["susceptibility"], reverse=True),
                    "total_tokens": total_tokens,
                    "estimated_cost_usd": round(total_tokens * 0.000005, 4),
                    "compared_at": datetime.now().isoformat(),
                }

                # 保存结果
                if db:
                    save_data = {**summary, "steps": [r.model_dump() for r in step_results]}
                    await db.save_workflow_simulation(save_data)

                # 推送汇总事件
                yield f"event: summary\ndata: {json.dumps(summary, ensure_ascii=False)}\n\n"

            except Exception as e:
                import traceback
                import sys
                tb = traceback.format_exc()
                logger.error(f"SSE 仿真流异常: {e}")
                print(f"SSE TRACEBACK: {tb}", file=sys.stderr, flush=True)
                err = {"error": str(e)}
                yield f"event: error\ndata: {json.dumps(err, ensure_ascii=False)}\n\n"

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
    async def run_batch_simulation():
        """批量仿真所有插件（使用 intermediate 角色）"""
        try:
            global _definitions_cache
            if not _definitions_cache:
                _definitions_cache = scan_all_plugins()

            if not _definitions_cache:
                raise HTTPException(status_code=404, detail="没有找到可仿真的插件")

            skill_evals = _get_skill_evaluations()
            results = []

            for wf in _definitions_cache:
                if not wf.steps:
                    continue
                try:
                    result = await simulate_workflow(wf, "intermediate", skill_evals)
                    results.append(result.model_dump())
                    if db:
                        await db.save_workflow_simulation(result.model_dump())
                except Exception as e:
                    logger.error(f"批量仿真 [{wf.plugin_id}] 失败: {e}")
                    results.append({
                        "plugin_id": wf.plugin_id,
                        "plugin_name": wf.plugin_name,
                        "error": str(e),
                    })

            return {
                "total": len(results),
                "results": results,
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"批量仿真失败: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # ==================== 结果检索 ====================

    @router.get("/cannbot/workflow/simulations")
    async def list_simulations(plugin_id: str = None, limit: int = 20):
        """获取仿真历史列表"""
        if not db:
            raise HTTPException(status_code=503, detail="数据库不可用")
        simulations = await db.get_workflow_simulations(plugin_id=plugin_id, limit=limit)
        # 返回概要信息（不含 steps 详情，减少传输量）
        summaries = []
        for sim in simulations:
            summaries.append({
                "simulation_id": sim.get("simulation_id", ""),
                "plugin_id": sim.get("plugin_id", ""),
                "plugin_name": sim.get("plugin_name", ""),
                "persona": sim.get("persona", ""),
                "overall_pass_rate": sim.get("overall_pass_rate", 0),
                "total_breakpoints": sim.get("total_breakpoints", 0),
                "critical_breakpoints": sim.get("critical_breakpoints", 0),
                "total_tokens": sim.get("total_tokens", 0),
                "estimated_cost_usd": sim.get("estimated_cost_usd", 0),
                "compared_at": sim.get("compared_at", ""),
                "steps_count": len(sim.get("steps", [])),
            })
        return {"total": len(summaries), "simulations": summaries}

    @router.get("/cannbot/workflow/simulation/{sim_id}")
    async def get_simulation_result(sim_id: str):
        """获取仿真结果（按 simulation_id 查询）"""
        if not db:
            raise HTTPException(status_code=503, detail="数据库不可用")
        result = await db.get_simulation_by_id(sim_id)
        if not result:
            raise HTTPException(status_code=404, detail="仿真结果未找到")
        return result

    @router.get("/cannbot/workflow/comparison")
    async def get_comparison_report():
        """获取跨插件对比报告"""
        if not db:
            raise HTTPException(status_code=503, detail="数据库不可用")

        try:
            simulations = await db.get_workflow_simulations(limit=50)
            if not simulations:
                return {"plugins": [], "common_breakpoints": [], "generated_at": ""}

            # 按插件分组（取每个插件最新的仿真）
            latest_by_plugin = {}
            for sim in simulations:
                pid = sim.get("plugin_id", "")
                if pid not in latest_by_plugin:
                    latest_by_plugin[pid] = sim

            # 构建摘要
            plugin_summaries = []
            for pid, sim in latest_by_plugin.items():
                plugin_summaries.append(PluginSimSummary(
                    plugin_id=pid,
                    plugin_name=sim.get("plugin_name", pid),
                    overall_pass_rate=sim.get("overall_pass_rate", 0),
                    total_breakpoints=sim.get("total_breakpoints", 0),
                    critical_breakpoints=sim.get("critical_breakpoints", 0),
                    skill_coverage=_calc_skill_coverage(sim),
                    persona_results={sim.get("persona", ""): sim.get("overall_pass_rate", 0)},
                ))

            # 找出跨插件共性断点
            all_breakpoints = []
            for sim in latest_by_plugin.values():
                for step in sim.get("steps", []):
                    for bp in step.get("breakpoints", []):
                        all_breakpoints.append(bp)

            common_breakpoints = []
            from collections import Counter
            category_counts = Counter(bp.get("category") for bp in all_breakpoints)
            for cat, count in category_counts.most_common(5):
                if count >= 2:
                    common_breakpoints.append({
                        "category": cat,
                        "count": count,
                        "examples": [
                            bp for bp in all_breakpoints
                            if bp.get("category") == cat
                        ][:3],
                    })

            report = ComparisonReport(
                plugins=plugin_summaries,
                common_breakpoints=common_breakpoints,
            )
            return report.model_dump()

        except Exception as e:
            logger.error(f"获取对比报告失败: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # ==================== 反模式 ====================

    @router.get("/cannbot/workflow/antipatterns")
    async def list_antipatterns():
        """列出反模式库"""
        patterns = get_all_antipatterns()
        return {
            "total": len(patterns),
            "antipatterns": patterns,
        }

    # ==================== 仿真报告导出 ====================

    class WorkflowExportRequest(BaseModel):
        format: str = "pdf"  # "pdf" | "markdown"
        summary: Dict[str, Any]
        step_results: List[Dict[str, Any]]

    @router.post("/cannbot/workflow/export")
    async def export_simulation_report(req: WorkflowExportRequest):
        """导出仿真报告 (PDF 或 Markdown)"""
        if not req.summary:
            raise HTTPException(status_code=400, detail="summary 数据为空")
        if not req.step_results:
            raise HTTPException(status_code=400, detail="step_results 数据为空")

        if not exporter:
            raise HTTPException(status_code=503, detail="导出引擎不可用")

        try:
            if req.format == "pdf":
                filepath = exporter.export_simulation_pdf(req.summary, req.step_results)
                media_type = "application/pdf"
            elif req.format == "markdown":
                filepath = exporter.export_simulation_markdown(req.summary, req.step_results)
                media_type = "text/markdown"
            else:
                raise HTTPException(status_code=400, detail=f"不支持的格式: {req.format}，可选: pdf, markdown")

            from fastapi.responses import FileResponse
            return FileResponse(filepath, media_type=media_type, filename=os.path.basename(filepath))
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"导出仿真报告失败: {e}")
            raise HTTPException(status_code=500, detail=str(e))


def _get_skill_evaluations() -> dict:
    """获取技能评估数据（复用 cannbot_skills 的评分系统）"""
    try:
        from app.api.routers.cannbot_skills import (
            _scan_skills, _parse_skill_md, _score_doc, _score_content,
            _score_references, _score_activity, _score_capability,
            CANNBOT_DIR as SKILLS_DIR, SKILL_CATEGORIES,
        )
        from pathlib import Path

        if not SKILLS_DIR.exists():
            return {}

        evals = {}
        for cat_key in SKILL_CATEGORIES:
            cat_dir = SKILLS_DIR / cat_key
            if not cat_dir.is_dir():
                continue
            for skill_dir in sorted(cat_dir.iterdir()):
                if not skill_dir.is_dir():
                    continue
                skill_md = skill_dir / "SKILL.md"
                has_skill_md = skill_md.exists()
                frontmatter = {}
                description = ""
                body = ""
                name = skill_dir.name

                if has_skill_md:
                    parsed = _parse_skill_md(skill_md)
                    frontmatter = parsed["frontmatter"]
                    description = parsed["description"]
                    body = parsed["body"]
                    name = parsed["name"]

                doc_score, _ = _score_doc(has_skill_md, frontmatter)
                content_score, _ = _score_content(description, body)
                ref_score, _ = _score_references(skill_dir)
                act_score, _ = _score_activity("")  # 简化：不查询 git 日期
                cap_score, _ = _score_capability(skill_dir, frontmatter, body)

                total = (
                    doc_score * 0.20
                    + content_score * 0.20
                    + ref_score * 0.15
                    + act_score * 0.15
                    + cap_score * 0.30
                )

                if total >= 90:
                    grade = "A"
                elif total >= 75:
                    grade = "B"
                elif total >= 60:
                    grade = "C"
                elif total >= 40:
                    grade = "D"
                else:
                    grade = "F"

                evals[name] = {
                    "total_score": round(total, 1),
                    "grade": grade,
                    "doc": round(doc_score, 1),
                    "content": round(content_score, 1),
                    "references": round(ref_score, 1),
                    "activity": round(act_score, 1),
                    "capability": round(cap_score, 1),
                }
        return evals
    except Exception as e:
        logger.warning(f"获取技能评估数据失败: {e}")
        return {}


def _calc_skill_coverage(sim: dict) -> float:
    """计算技能覆盖率"""
    steps = sim.get("steps", [])
    if not steps:
        return 0.0
    total_skills = 0
    used_skills = 0
    for step in steps:
        skills_missing = step.get("skills_missing", [])
        skills_used = step.get("skills_used", [])
        total = len(skills_missing) + len(skills_used)
        if total > 0:
            total_skills += total
            used_skills += len(skills_used)
    return round(used_skills / total_skills, 3) if total_skills > 0 else 0.0
