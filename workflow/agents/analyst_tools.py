"""
Analyst Agent 工具集
CI/CD 工程效能分析工具
"""
import json
import logging
from typing import Optional
from langchain_core.tools import tool

logger = logging.getLogger(__name__)


def _get_services():
    from workflow.config import workflow_config
    return workflow_config.github_service, workflow_config.db


@tool
def analyze_cicd_comments(owner: str, repo: str) -> str:
    """从数据库中的 PR 评论识别并提取 CI/CD 构建结果。返回提取到的 CI/CD 记录数和状态分布。"""
    try:
        from app.analysis.cicd_extractor import CICDExtractor
    except ImportError:
        return json.dumps({
            "error": "CICDExtractor 模块不可用（backend 未在 Python 路径中）",
            "hint": "通过后端服务调用，或确保 backend/ 目录已加入 sys.path",
        }, ensure_ascii=False)

    _, db = _get_services()
    if not db:
        return "数据库不可用"

    try:
        collection = db.db['pr_comments']
        docs = list(collection.find({"owner": owner, "repo": repo}, {"_id": 0}))
        if not docs:
            return json.dumps({"error": "未找到评论数据，请先用 Collector Agent 采集评论"}, ensure_ascii=False)

        extractor = CICDExtractor()
        all_results = []
        for doc in docs:
            pr_number = doc.get("pr_number")
            data = doc.get("data", [])
            comments = data if isinstance(data, list) else [data] if isinstance(data, dict) else []
            structured = extractor.extract_batch_structured(comments, owner=owner, repo=repo, pr_number=pr_number)
            for r in structured:
                all_results.append(r.to_db_dict())

        if all_results:
            db.save_cicd_results_batch(all_results)

        status_counts = {}
        for r in all_results:
            s = r.get("build_status", "unknown")
            status_counts[s] = status_counts.get(s, 0) + 1

        return json.dumps({
            "owner": owner, "repo": repo,
            "cicd_records": len(all_results),
            "status_distribution": status_counts,
        }, ensure_ascii=False)
    except Exception as e:
        return f"CI/CD 分析失败: {e}"


@tool
def get_cicd_stats(owner: str, repo: str) -> str:
    """获取项目的 CI/CD 统计数据（成功率、平均耗时、覆盖率等）。"""
    _, db = _get_services()
    if not db:
        return "数据库不可用"

    try:
        result = db.get_cicd_summary_from_db(owner, repo)
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        return f"获取统计失败: {e}"


@tool
def get_cicd_trends(owner: str, repo: str, granularity: str = "day") -> str:
    """获取 CI/CD 趋势数据。granularity: day/week/month。"""
    _, db = _get_services()
    if not db:
        return "数据库不可用"

    try:
        trends = db.get_cicd_trends_from_db(owner, repo, granularity=granularity)
        return json.dumps({
            "owner": owner, "repo": repo,
            "granularity": granularity,
            "data_points": len(trends),
            "trends": trends[:20],
        }, ensure_ascii=False)
    except Exception as e:
        return f"获取趋势失败: {e}"


@tool
def get_failure_analysis(owner: str, repo: str) -> str:
    """获取 CI/CD 失败分析（高频失败 job、MTTR、按解析器统计）。"""
    _, db = _get_services()
    if not db:
        return "数据库不可用"

    try:
        result = db.get_cicd_failure_analysis_from_db(owner, repo)
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        return f"失败分析失败: {e}"


@tool
def query_pr_details(owner: str, repo: str, page: int = 1, size: int = 10) -> str:
    """查询 PR 详情数据（用于辅助分析协作模式、PR 粒度等）。"""
    _, db = _get_services()
    if not db:
        return "数据库不可用"

    try:
        result = db.list_pr_details(owner, repo, page=page, size=size)
        items = result.get("data", [])
        summary = {
            "total": result.get("total", 0),
            "states": {},
            "avg_additions": 0,
            "avg_deletions": 0,
        }
        total_add, total_del, count = 0, 0, 0
        for item in items:
            d = item.get("data", {}).get("detail", item.get("data", {}))
            state = d.get("state", "unknown")
            summary["states"][state] = summary["states"].get(state, 0) + 1
            total_add += d.get("additions", 0) or 0
            total_del += d.get("deletions", 0) or 0
            count += 1
        if count:
            summary["avg_additions"] = total_add // count
            summary["avg_deletions"] = total_del // count
        return json.dumps(summary, ensure_ascii=False)
    except Exception as e:
        return f"查询 PR 详情失败: {e}"


@tool
def query_pr_reviews(owner: str, repo: str, page: int = 1, size: int = 10) -> str:
    """查询 PR Reviews 数据（用于辅助分析 review 质量和协作效率）。"""
    _, db = _get_services()
    if not db:
        return "数据库不可用"

    try:
        result = db.list_pr_reviews(owner, repo, page=page, size=size)
        items = result.get("data", [])
        review_states = {}
        total_reviews = 0
        for item in items:
            reviews = item.get("data", {}).get("reviews", [])
            total_reviews += len(reviews)
            for r in reviews:
                s = r.get("state", "UNKNOWN")
                review_states[s] = review_states.get(s, 0) + 1
        return json.dumps({
            "total_prs_with_reviews": result.get("total", 0),
            "total_reviews": total_reviews,
            "review_states": review_states,
        }, ensure_ascii=False)
    except Exception as e:
        return f"查询 Reviews 失败: {e}"
