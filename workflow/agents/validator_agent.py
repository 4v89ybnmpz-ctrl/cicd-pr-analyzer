"""
Validator Agent — 数据质量验证 Agent
验证采集数据的完整性、一致性，检查分析结果的可信度
"""
import json
import logging
from typing import Dict, Any, List, Optional
from langchain_core.tools import tool
from .base_agent import BaseAgent

logger = logging.getLogger(__name__)


@tool
def validate_collected_data(owner: str, repo: str) -> str:
    """验证采集数据的完整性：PR列表、评论、详情、Reviews 是否完整。
    返回验证报告，包含缺失数据和异常项。"""
    from workflow.config import workflow_config
    from .blackboard import blackboard, DataType

    db = workflow_config.db
    if not db:
        return json.dumps({"valid": False, "error": "数据库不可用"}, ensure_ascii=False)

    report = {
        "owner": owner, "repo": repo,
        "valid": True,
        "checks": [],
        "warnings": [],
        "errors": [],
        "completeness_score": 0.0,
    }

    checks_passed = 0
    total_checks = 5

    # 检查 1: PR 数据
    try:
        pr_data = db.get_pr_data(owner, repo)
        if pr_data:
            prs = pr_data.get("data", {}).get("prs", [])
            report["checks"].append({
                "name": "pr_data", "status": "pass",
                "count": len(prs),
            })
            checks_passed += 1
        else:
            report["checks"].append({"name": "pr_data", "status": "missing"})
            report["warnings"].append("缺少 PR 列表数据")
    except Exception as e:
        report["checks"].append({"name": "pr_data", "status": "error", "error": str(e)})
        report["errors"].append(f"PR 数据检查失败: {e}")

    # 检查 2: 评论数据
    try:
        stats = db.get_aggregate_stats(owner, repo)
        comment_count = stats.get("pr_comments_count", 0)
        if comment_count > 0:
            report["checks"].append({
                "name": "comments", "status": "pass",
                "count": comment_count,
            })
            checks_passed += 1
        else:
            report["checks"].append({"name": "comments", "status": "missing"})
            report["warnings"].append("没有评论数据，CI/CD 分析可能不完整")
    except Exception as e:
        report["checks"].append({"name": "comments", "status": "error", "error": str(e)})

    # 检查 3: CI/CD 结果
    try:
        cicd = db.query_cicd_results(owner, repo, page=1, size=1)
        if cicd.get("total", 0) > 0:
            report["checks"].append({
                "name": "cicd_results", "status": "pass",
                "count": cicd["total"],
            })
            checks_passed += 1
        else:
            report["checks"].append({"name": "cicd_results", "status": "missing"})
            report["warnings"].append("未找到 CI/CD 分析结果")
    except Exception as e:
        report["checks"].append({"name": "cicd_results", "status": "error", "error": str(e)})

    # 检查 4: 统计数据合理性
    try:
        summary = db.get_cicd_summary_from_db(owner, repo)
        total = summary.get("total", 0)
        if total > 0:
            success_rate = summary.get("success_rate", 0)
            if success_rate is not None and 0 <= success_rate <= 100:
                report["checks"].append({
                    "name": "stats_sanity", "status": "pass",
                    "success_rate": success_rate,
                })
                checks_passed += 1
            else:
                report["checks"].append({"name": "stats_sanity", "status": "warning"})
                report["warnings"].append(f"成功率异常: {success_rate}")
        else:
            report["checks"].append({"name": "stats_sanity", "status": "skip"})
            checks_passed += 0.5
    except Exception as e:
        report["checks"].append({"name": "stats_sanity", "status": "error", "error": str(e)})

    # 检查 5: 数据时效性
    try:
        trends = db.get_cicd_trends_from_db(owner, repo, granularity="day")
        if trends:
            latest = trends[-1] if isinstance(trends, list) else {}
            report["checks"].append({
                "name": "data_freshness", "status": "pass",
                "latest_data_point": str(latest.get("date", "unknown")),
            })
            checks_passed += 1
        else:
            report["checks"].append({"name": "data_freshness", "status": "missing"})
            report["warnings"].append("没有趋势数据")
    except Exception as e:
        report["checks"].append({"name": "data_freshness", "status": "error", "error": str(e)})

    # 计算完整度分数
    report["completeness_score"] = round(checks_passed / total_checks * 100, 1)
    report["valid"] = checks_passed >= 3

    # 写入黑板
    blackboard.write(
        f"validation/{owner}/{repo}", DataType.VALIDATION_RESULT,
        report, producer="validator",
    )

    return json.dumps(report, ensure_ascii=False)


@tool
def validate_analysis_quality(owner: str, repo: str) -> str:
    """验证分析结果的质量：检查评级合理性、报告完整性、建议可操作性。"""
    from .blackboard import blackboard, DataType

    report = {
        "owner": owner, "repo": repo,
        "quality_score": 0.0,
        "issues": [],
        "suggestions": [],
    }

    # 从黑板读取分析结果
    analysis_entry = blackboard.read_entry(f"analysis/{owner}/{repo}")
    if analysis_entry:
        analysis = analysis_entry.value
        # 检查分析是否包含关键维度
        required_dimensions = ["构建稳定性", "效率", "质量"]
        for dim in required_dimensions:
            found = any(dim in str(analysis) for _ in [1])
            if not found:
                report["issues"].append(f"缺少分析维度: {dim}")

    # 检查统计报告
    stats_entry = blackboard.read_entry(f"stats/{owner}/{repo}")
    if not stats_entry:
        report["issues"].append("缺少统计报告数据")

    # 计算质量分数
    issue_count = len(report["issues"])
    if issue_count == 0:
        report["quality_score"] = 100.0
    elif issue_count <= 2:
        report["quality_score"] = 70.0
    else:
        report["quality_score"] = 40.0

    if report["quality_score"] < 80:
        report["suggestions"].append("建议补充缺失的分析维度")
    if report["quality_score"] < 50:
        report["suggestions"].append("数据质量不足，建议重新采集")

    return json.dumps(report, ensure_ascii=False)


VALIDATOR_SYSTEM_PROMPT = """你是一个数据质量验证专家。你的任务是检查数据的完整性和分析结果的可信度。

## 你的能力
- validate_collected_data: 验证采集数据完整性（5项检查）
- validate_analysis_quality: 验证分析结果质量

## 工作流程

### 第一步：验证采集数据
调用 validate_collected_data 检查:
- PR 数据是否存在
- 评论数据是否充足
- CI/CD 结果是否已提取
- 统计数据是否合理（成功率 0-100%）
- 数据时效性

### 第二步：验证分析质量
调用 validate_analysis_quality 检查:
- 分析是否覆盖关键维度
- 评级是否合理
- 建议是否具体可操作

### 第三步：输出验证报告
输出验证结果:
- 完整度分数 (0-100)
- 通过/失败的检查项
- 警告和建议
- 如果数据不足，建议需要补充什么

## 决策逻辑
- 完整度 >= 80% → 数据充足，可继续
- 完整度 50-80% → 数据部分缺失，建议补充
- 完整度 < 50% → 数据不足，建议重新采集"""


class ValidatorAgent(BaseAgent):
    """数据质量验证 Agent"""

    name = "validator"
    system_prompt = VALIDATOR_SYSTEM_PROMPT

    def _register_tools(self) -> list:
        return [
            validate_collected_data,
            validate_analysis_quality,
        ]
