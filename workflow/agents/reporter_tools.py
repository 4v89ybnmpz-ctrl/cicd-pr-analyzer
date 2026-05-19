"""
Reporter Agent 增强工具集
支持: Markdown/HTML/JSON 多格式输出、模板系统
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
    from .insights_engine import build_insights, compute_overall_grade

    db = _get_db()
    if not db:
        return "数据库不可用"

    try:
        summary = db.get_cicd_summary_from_db(owner, repo)
        trends = db.get_cicd_trends_from_db(owner, repo)
        failure = db.get_cicd_failure_analysis_from_db(owner, repo)
        insights = build_insights(summary, failure)
        overall_grade = compute_overall_grade(insights)

        report = {
            "owner": owner, "repo": repo,
            "summary": summary,
            "trends": trends[:10],
            "failure_analysis": failure,
            "insights": insights,
            "overall_grade": overall_grade,
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
{{{{
  "suggestions": ["建议1：问题描述 + 操作步骤 + 预期效果", "建议2：...", ...],
}}}}
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
{{{{
  "risk_level": "低/中/高",
  "risk_description": "风险描述...",
  "top_risks": ["风险1", "风险2", "风险3"]
}}}}
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

    from .insights_engine import format_duration

    lines = []
    owner = report.get('owner', '')
    repo = report.get('repo', '')
    lines.append(f"# {owner}/{repo} CI/CD 工程能力洞察报告\n")

    # 概览
    summary = report.get("summary", {})
    lines.append("## 概览")
    lines.append(f"- 总构建数: {summary.get('total', 0)}")
    lines.append(f"- 成功率: {summary.get('success_rate', 'N/A')}%")
    avg_dur = summary.get('avg_duration_seconds')
    lines.append(f"- 平均耗时: {format_duration(avg_dur) if avg_dur else 'N/A'}")
    lines.append(f"- 平均覆盖率: {summary.get('avg_coverage', 'N/A')}%\n")

    # 综合评级
    overall_grade = report.get("overall_grade", "")
    if overall_grade:
        grade_emoji = {"A": "🟢", "B": "🟡", "C": "🟠", "D": "🔴", "F": "⛔"}.get(overall_grade, "⚪")
        lines.append(f"## 综合评级: {grade_emoji} {overall_grade}\n")

    # 洞察
    insights = report.get("insights", [])
    if insights:
        lines.append("## 分项评级")
        lines.append("")
        lines.append("| 指标 | 值 | 评级 | 建议 |")
        lines.append("|------|-----|------|------|")
        for i in insights:
            lines.append(
                f"| {i.get('name', '')} | {i.get('value', '')} | "
                f"{i.get('grade', '')} | {i.get('suggestion', '')} |"
            )
        lines.append("")

    # 失败分析
    failure = report.get("failure_analysis", {})
    top_jobs = failure.get("top_failed_jobs", [])
    if top_jobs:
        lines.append("## 高频失败 Job (Top 5)")
        for idx, job in enumerate(top_jobs[:5], 1):
            lines.append(f"{idx}. **{job.get('name', '')}** — 失败 {job.get('count', 0)} 次")
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


def _html_escape(text: str) -> str:
    """转义 HTML 特殊字符防止 XSS"""
    return (text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&#x27;"))


@tool
def format_report_html(report_json: str) -> str:
    """将 JSON 报告格式化为 HTML 页面，适合浏览器展示。"""
    try:
        report = json.loads(report_json)
    except Exception:
        return f"<pre>{report_json}</pre>"

    from .insights_engine import format_duration

    owner = _html_escape(report.get('owner', ''))
    repo = _html_escape(report.get('repo', ''))
    summary = report.get("summary", {})
    insights = report.get("insights", [])
    overall_grade = _html_escape(report.get("overall_grade", ""))

    # 构建洞察行（转义所有动态值）
    insight_rows = ""
    for i in insights:
        grade_color = {"A": "#22c55e", "B": "#84cc16", "C": "#eab308", "D": "#f97316", "F": "#ef4444"}.get(i.get("grade", ""), "#94a3b8")
        insight_rows += f"""
        <tr>
            <td>{_html_escape(str(i.get('name', '')))}</td>
            <td>{_html_escape(str(i.get('value', '')))}</td>
            <td><span style="color:{grade_color};font-weight:bold">{_html_escape(str(i.get('grade', '')))}</span></td>
            <td>{_html_escape(str(i.get('description', '')))}</td>
            <td>{_html_escape(str(i.get('suggestion', '')))}</td>
        </tr>"""

    avg_dur = summary.get('avg_duration_seconds')
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{owner}/{repo} CI/CD 洞察报告</title>
    <style>
        body {{ font-family: -apple-system, sans-serif; max-width: 960px; margin: 0 auto; padding: 20px; background: #f8fafc; }}
        h1 {{ color: #1e293b; border-bottom: 2px solid #3b82f6; padding-bottom: 10px; }}
        h2 {{ color: #334155; margin-top: 30px; }}
        .metrics {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin: 20px 0; }}
        .metric-card {{ background: white; border-radius: 8px; padding: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
        .metric-value {{ font-size: 24px; font-weight: bold; color: #1e293b; }}
        .metric-label {{ font-size: 14px; color: #64748b; }}
        .grade-badge {{ display: inline-block; font-size: 36px; font-weight: bold; padding: 10px 20px; border-radius: 12px; background: #f1f5f9; }}
        table {{ width: 100%; border-collapse: collapse; margin: 16px 0; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
        th {{ background: #f1f5f9; padding: 12px; text-align: left; font-size: 14px; color: #475569; }}
        td {{ padding: 12px; border-top: 1px solid #e2e8f0; font-size: 14px; }}
        .footer {{ margin-top: 40px; padding-top: 20px; border-top: 1px solid #e2e8f0; color: #94a3b8; font-size: 12px; }}
    </style>
</head>
<body>
    <h1>{owner}/{repo} CI/CD 工程能力洞察报告</h1>

    <div class="metrics">
        <div class="metric-card">
            <div class="metric-value">{summary.get('total', 0)}</div>
            <div class="metric-label">总构建数</div>
        </div>
        <div class="metric-card">
            <div class="metric-value">{summary.get('success_rate', 'N/A')}%</div>
            <div class="metric-label">成功率</div>
        </div>
        <div class="metric-card">
            <div class="metric-value">{format_duration(avg_dur) if avg_dur else 'N/A'}</div>
            <div class="metric-label">平均耗时</div>
        </div>
        <div class="metric-card">
            <div class="metric-value">{summary.get('avg_coverage', 'N/A')}%</div>
            <div class="metric-label">覆盖率</div>
        </div>
    </div>

    {"<h2>综合评级</h2><div class='grade-badge'>" + overall_grade + "</div>" if overall_grade else ""}

    {"<h2>分项评级</h2><table><tr><th>指标</th><th>值</th><th>评级</th><th>描述</th><th>建议</th></tr>" + insight_rows + "</table>" if insight_rows else ""}

    <div class="footer">生成时间: {report.get('generated_at', '')}</div>
</body>
</html>"""
    return html


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
