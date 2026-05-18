"""
Reporter Agent 工具集
报告生成工具
"""
import json
import logging
from typing import Optional, List
from langchain_core.tools import tool

logger = logging.getLogger(__name__)


def _get_db():
    from workflow.config import workflow_config
    return workflow_config.db


def _get_llm():
    from workflow.config import workflow_config
    return workflow_config.llm


@tool
def generate_stats_report(owner: str, repo: str) -> str:
    """生成规则引擎统计报告（成功率评级、耗时评级、覆盖率评级）。不依赖 AI。"""
    from app.api.routers.analysis import _build_insights

    db = _get_db()
    if not db:
        return "数据库不可用"

    try:
        summary = db.get_cicd_summary_from_db(owner, repo)
        trends = db.get_cicd_trends_from_db(owner, repo)
        failure = db.get_cicd_failure_analysis_from_db(owner, repo)
        insights = _build_insights(summary, failure)

        report = {
            "owner": owner, "repo": repo,
            "summary": summary,
            "trends": trends[:10],
            "failure_analysis": failure,
            "insights": insights,
            "data_source_count": summary.get("total", 0),
        }
        return json.dumps(report, ensure_ascii=False)
    except Exception as e:
        return f"生成统计报告失败: {e}"


@tool
def ai_generate_suggestions(stats_json: str, analysis_text: str) -> str:
    """使用 AI 生成 5 条具体的改进建议。stats_json 是统计数据的 JSON 字符串，analysis_text 是分析文本。"""
    llm = _get_llm()
    if not llm:
        return "AI 不可用（未配置 ANTHROPIC_API_KEY）"

    try:
        prompt = f"""基于以下 CI/CD 数据和分析，给出 5 条具体的改进建议。

## 统计数据
{stats_json[:3000]}

## 分析报告
{analysis_text[:3000]}

请用 JSON 格式输出：
```json
{{
  "suggestions": ["建议1：问题描述 + 操作步骤 + 预期效果", "建议2：...", ...],
}}
```"""
        response = llm.invoke([
            {"role": "system", "content": "你是 DevOps 顾问，请给出可执行的改进建议。"},
            {"role": "user", "content": prompt},
        ])
        import re
        content = response.content
        json_match = re.search(r'```json\s*(.*?)\s*```', content, re.DOTALL)
        if json_match:
            parsed = json.loads(json_match.group(1))
        else:
            parsed = json.loads(content)
        return json.dumps(parsed, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"suggestions": [f"AI 建议生成失败: {e}"]}, ensure_ascii=False)


@tool
def ai_risk_assessment(stats_json: str, failure_json: str) -> str:
    """使用 AI 进行风险评估（低/中/高），给出风险描述。"""
    llm = _get_llm()
    if not llm:
        return "AI 不可用"

    try:
        prompt = f"""基于以下 CI/CD 数据进行风险评估。

## 统计数据
{stats_json[:2000]}

## 失败分析
{failure_json[:2000]}

请用 JSON 格式输出：
```json
{{
  "risk_level": "低/中/高",
  "risk_description": "风险描述...",
  "top_risks": ["风险1", "风险2", "风险3"]
}}
```"""
        response = llm.invoke([
            {"role": "system", "content": "你是风险评估专家。"},
            {"role": "user", "content": prompt},
        ])
        import re
        content = response.content
        json_match = re.search(r'```json\s*(.*?)\s*```', content, re.DOTALL)
        if json_match:
            parsed = json.loads(json_match.group(1))
        else:
            parsed = json.loads(content)
        return json.dumps(parsed, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"risk_level": "未知", "risk_description": f"评估失败: {e}"}, ensure_ascii=False)


@tool
def format_report_md(report_json: str) -> str:
    """将 JSON 报告格式化为可读的 Markdown 文本。"""
    try:
        report = json.loads(report_json)
    except Exception:
        return report_json

    lines = []
    lines.append(f"# {report.get('owner', '')}/{report.get('repo', '')} CI/CD 工程能力洞察报告\n")

    # 概览
    summary = report.get("summary", {})
    lines.append("## 概览")
    lines.append(f"- 总构建数: {summary.get('total', 0)}")
    lines.append(f"- 成功率: {summary.get('success_rate', 'N/A')}%")
    lines.append(f"- 平均耗时: {summary.get('avg_duration_seconds', 'N/A')}s")
    lines.append(f"- 平均覆盖率: {summary.get('avg_coverage', 'N/A')}%\n")

    # 洞察
    insights = report.get("insights", [])
    if insights:
        lines.append("## 规则引擎评级")
        for i in insights:
            lines.append(f"- **{i.get('name', '')}**: {i.get('value', '')} (评级: {i.get('grade', '')})")
        lines.append("")

    # AI 分析
    ai_analysis = report.get("ai_analysis", "")
    if ai_analysis:
        lines.append("## AI 深度分析")
        lines.append(ai_analysis)
        lines.append("")

    # AI 建议
    ai_suggestions = report.get("ai_suggestions", [])
    if ai_suggestions:
        lines.append("## 改进建议")
        for idx, s in enumerate(ai_suggestions, 1):
            lines.append(f"{idx}. {s}")
        lines.append("")

    # 风险评估
    risk = report.get("ai_risk_assessment", "")
    if risk:
        lines.append(f"## 风险评估\n{risk}\n")

    lines.append(f"---\n*生成时间: {report.get('generated_at', '')}*")
    return "\n".join(lines)


@tool
def format_report_json(report_json: str) -> str:
    """格式化并验证 JSON 报告结构完整性。"""
    try:
        report = json.loads(report_json)
        required_fields = ["owner", "repo", "summary"]
        missing = [f for f in required_fields if f not in report]
        if missing:
            return json.dumps({"valid": False, "missing_fields": missing}, ensure_ascii=False)
        return json.dumps({"valid": True, "fields": list(report.keys())}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"valid": False, "error": str(e)}, ensure_ascii=False)
