"""
AI 分析节点
使用 Claude 对 CI/CD 统计数据进行深度分析
"""
import json
import logging
from typing import Dict, Any, List

from .state import PipelineState
from .config import workflow_config

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是一位资深 DevOps 工程效能专家。你的任务是基于 CI/CD 构建数据分析项目的工程能力，给出专业洞察。

你的分析应该：
1. 用清晰的人话解释数据背后的含义（不要只罗列数字）
2. 识别数据中的模式和异常
3. 给出具体的、可执行的改进建议（不是泛泛而谈）
4. 评估风险等级和紧急程度
5. 与业界最佳实践做对比

请用 Markdown 格式输出。"""


def ai_analyze_node(state: PipelineState) -> Dict[str, Any]:
    """
    节点: AI 深度分析
    将统计数据、趋势、失败分析喂给 Claude，获取深度洞察
    """
    cfg = workflow_config
    stats_report = state.get("stats_report", {})
    owner = state["owner"]
    repo = state["repo"]

    logger.info(f"[节点] AI 深度分析: {owner}/{repo}")

    if not cfg.ai_ready:
        logger.warning("LLM 不可用，跳过 AI 分析")
        return {
            "ai_analysis": "AI 分析不可用（未配置 ANTHROPIC_API_KEY）",
            "ai_suggestions": ["请配置 ANTHROPIC_API_KEY 以启用 AI 分析"],
            "ai_risk_assessment": "未评估",
            "current_step": "ai_analyze_skipped",
            "progress": 90.0,
        }

    # 构建分析 prompt
    user_prompt = _build_analysis_prompt(owner, repo, stats_report, state)

    try:
        response = cfg.llm.invoke([
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ])

        ai_analysis = response.content
        logger.info(f"AI 分析完成，生成 {len(ai_analysis)} 字")

    except Exception as e:
        logger.error(f"AI 分析失败: {e}")
        ai_analysis = f"AI 分析失败: {e}"

    return {
        "ai_analysis": ai_analysis,
        "current_step": "ai_analyze",
        "progress": 90.0,
    }


def ai_suggest_node(state: PipelineState) -> Dict[str, Any]:
    """
    节点: AI 改进建议
    让 Claude 基于分析结果给出具体的改进方案
    """
    cfg = workflow_config
    stats_report = state.get("stats_report", {})
    ai_analysis = state.get("ai_analysis", "")
    owner = state["owner"]
    repo = state["repo"]

    logger.info(f"[节点] AI 改进建议: {owner}/{repo}")

    if not cfg.ai_ready:
        return {
            "ai_suggestions": ["请配置 ANTHROPIC_API_KEY"],
            "ai_risk_assessment": "未评估",
            "current_step": "ai_suggest_skipped",
            "progress": 95.0,
        }

    prompt = f"""基于以下 {owner}/{repo} 的 CI/CD 分析，请给出：

## 要求
1. **5 条具体的改进建议** — 每条建议要包含：问题描述、具体操作步骤、预期效果
2. **风险评估** — 用"低/中/高"评估当前项目的 CI/CD 风险等级，并说明理由

## 统计数据
{json.dumps(stats_report.get('summary', {}), ensure_ascii=False, indent=2)}

## 失败分析
{json.dumps(stats_report.get('failure_analysis', {}), ensure_ascii=False, indent=2)}

## 规则引擎洞察
{json.dumps(stats_report.get('insights', []), ensure_ascii=False, indent=2)}

## AI 初步分析
{ai_analysis[:2000]}

请用 JSON 格式输出：
```json
{{
  "suggestions": ["建议1...", "建议2...", ...],
  "risk_assessment": "风险描述..."
}}
```"""

    try:
        response = cfg.llm.invoke([
            {"role": "system", "content": "你是一位 DevOps 顾问。请用 JSON 格式输出改进建议和风险评估。"},
            {"role": "user", "content": prompt},
        ])

        content = response.content

        # 尝试从 Markdown 代码块中提取 JSON
        import re
        json_match = re.search(r'```json\s*(.*?)\s*```', content, re.DOTALL)
        if json_match:
            parsed = json.loads(json_match.group(1))
        else:
            parsed = json.loads(content)

        suggestions = parsed.get("suggestions", [])
        risk = parsed.get("risk_assessment", "")

        logger.info(f"AI 建议: {len(suggestions)} 条, 风险: {risk[:50]}")

    except Exception as e:
        logger.error(f"AI 建议生成失败: {e}")
        suggestions = [f"AI 建议生成失败: {e}"]
        risk = "评估失败"

    return {
        "ai_suggestions": suggestions,
        "ai_risk_assessment": risk,
        "current_step": "ai_suggest",
        "progress": 95.0,
    }


def _build_analysis_prompt(owner: str, repo: str,
                           stats_report: Dict, state: Dict) -> str:
    """构建 AI 分析 prompt，把统计数据序列化喂给 LLM"""
    summary = stats_report.get("summary", {})
    trends = stats_report.get("trends", [])
    failure = stats_report.get("failure_analysis", {})
    insights = stats_report.get("insights", [])

    # 获取 Reviews 概要
    reviews_data = state.get("reviews", {})
    review_summary = _summarize_reviews(reviews_data)

    # 获取 PR 详情概要
    details_data = state.get("details", {})
    detail_summary = _summarize_details(details_data)

    prompt = f"""# 项目 CI/CD 工程能力分析请求

## 项目信息
- **项目**: {owner}/{repo}
- **分析 PR 数**: {len(state.get('pr_numbers', []))}
- **CI/CD 记录数**: {summary.get('total', 0)}

## CI/CD 统计数据
{json.dumps(summary, ensure_ascii=False, indent=2)}

## 趋势数据 (最近 {len(trends)} 个时间段)
{json.dumps(trends[:10], ensure_ascii=False, indent=2)}

## 失败分析
{json.dumps(failure, ensure_ascii=False, indent=2)}

## 规则引擎评级
{json.dumps(insights, ensure_ascii=False, indent=2)}

## PR Review 概要
{review_summary}

## PR 详情概要
{detail_summary}

---

请从以下维度进行深度分析：

### 1. 整体评估
这个项目的 CI/CD 工程能力处于什么水平？和同类型开源项目相比如何？

### 2. 构建稳定性分析
成功率 {summary.get('success_rate', 'N/A')}% 是好还是差？可能的原因是什么？

### 3. 效率分析
平均构建耗时 {_format_duration(summary.get('avg_duration_seconds'))} 是否合理？
有哪些可以优化的方向？

### 4. 质量保障分析
覆盖率、测试策略是否充足？

### 5. 协作分析
Review 模式、PR 粒度、合并策略是否合理？

### 6. 风险识别
当前最大的风险点是什么？"""

    return prompt


def _summarize_reviews(reviews_data: Dict) -> str:
    """生成 Reviews 概要"""
    if not reviews_data:
        return "无 Review 数据"

    total_reviews = 0
    status_counts = {}
    for pr_num, data in reviews_data.items():
        reviews = data.get("reviews", [])
        total_reviews += len(reviews)
        for r in reviews:
            s = r.get("state", "UNKNOWN")
            status_counts[s] = status_counts.get(s, 0) + 1

    lines = [
        f"共 {len(reviews_data)} 个 PR 有 Review，总计 {total_reviews} 条",
        f"状态分布: {json.dumps(status_counts, ensure_ascii=False)}",
    ]
    return "\n".join(lines)


def _summarize_details(details_data: Dict) -> str:
    """生成 PR 详情概要"""
    if not details_data:
        return "无 PR 详情数据"

    states = {"open": 0, "closed": 0, "merged": 0}
    total_additions = 0
    total_deletions = 0
    total_changed_files = 0
    count = 0

    for pr_num, data in details_data.items():
        detail = data.get("detail", {})
        state = detail.get("state", "")
        if state in states:
            states[state] += 1
        total_additions += detail.get("additions", 0) or 0
        total_deletions += detail.get("deletions", 0) or 0
        total_changed_files += detail.get("changed_files", 0) or 0
        count += 1

    lines = [
        f"共 {count} 个 PR 详情",
        f"状态: open={states['open']}, closed={states['closed']}, merged={states['merged']}",
        f"平均每个 PR: +{total_additions // max(count, 1)} -{total_deletions // max(count, 1)} 行, {total_changed_files // max(count, 1)} 文件变更",
    ]
    return "\n".join(lines)


def _format_duration(seconds) -> str:
    """格式化耗时"""
    if seconds is None:
        return "N/A"
    if seconds < 60:
        return f"{seconds:.0f}s"
    elif seconds < 3600:
        return f"{seconds / 60:.1f}m"
    else:
        return f"{seconds / 3600:.1f}h"
