"""
Collector Agent 工具集
将现有 github_service / database_service 封装为 LangChain Tool
"""
import json
import logging
from typing import Optional
from langchain_core.tools import tool

logger = logging.getLogger(__name__)


def _get_services():
    """获取服务实例"""
    from workflow.config import workflow_config
    return workflow_config.github_service, workflow_config.db


@tool
def fetch_pr_list(owner: str, repo: str, max_count: int = 0) -> str:
    """获取仓库的 PR 列表。max_count=0 获取全部。返回 PR 编号列表和基本信息。"""
    github_service, db = _get_services()
    if not github_service:
        return "错误: GitHub 服务不可用"

    result = github_service.fetch_prs_for_project(owner, repo, max_count=max_count)
    if result["error"]:
        return f"获取 PR 列表失败: {result['error']}"

    # 保存到数据库
    if db:
        try:
            db.save_pr_data(owner, repo, result)
        except Exception:
            pass

    pr_numbers = [pr["number"] for pr in result["prs"]]
    summary = {
        "owner": owner,
        "repo": repo,
        "total_prs": result["total"],
        "pr_numbers": pr_numbers[:50],  # 截断避免过长
        "total_returned": len(pr_numbers),
    }
    return json.dumps(summary, ensure_ascii=False)


@tool
def fetch_pr_comments(owner: str, repo: str, pr_numbers: str) -> str:
    """获取指定 PR 的评论。pr_numbers 是逗号分隔的 PR 编号，如 '1,2,3'。返回每个 PR 的评论数量。"""
    github_service, db = _get_services()
    if not github_service:
        return "错误: GitHub 服务不可用"

    numbers = [int(n.strip()) for n in pr_numbers.split(",") if n.strip()]
    results = {}
    total_comments = 0

    for pr_num in numbers:
        result = github_service.fetch_pr_comments(owner, repo, pr_num)
        if result["error"] is None:
            total_comments += result["total"]
            results[str(pr_num)] = {"comments": result["total"], "error": None}
            if db:
                try:
                    db.save_pr_comments(owner, repo, pr_num, result)
                except Exception:
                    pass
        else:
            results[str(pr_num)] = {"comments": 0, "error": result["error"]}

    return json.dumps({
        "owner": owner, "repo": repo,
        "requested_prs": len(numbers),
        "total_comments": total_comments,
        "details": results,
    }, ensure_ascii=False)


@tool
def fetch_pr_details(owner: str, repo: str, pr_numbers: str) -> str:
    """获取指定 PR 的详情（标签、合并状态、代码变更统计）。pr_numbers 逗号分隔。"""
    github_service, db = _get_services()
    if not github_service:
        return "错误: GitHub 服务不可用"

    numbers = [int(n.strip()) for n in pr_numbers.split(",") if n.strip()]
    result = github_service.fetch_pr_detail_batch(owner, repo, numbers)

    details = {}
    for item in result.get("results", []):
        if item.get("error") is None:
            d = item.get("detail", {})
            details[str(item["pr_number"])] = {
                "state": d.get("state"),
                "merged": d.get("merged"),
                "additions": d.get("additions"),
                "deletions": d.get("deletions"),
                "changed_files": d.get("changed_files"),
            }
            if db:
                try:
                    db.save_pr_detail(owner, repo, item["pr_number"], item)
                except Exception:
                    pass

    return json.dumps({
        "owner": owner, "repo": repo,
        "fetched": len(details),
        "details": details,
    }, ensure_ascii=False)


@tool
def fetch_pr_reviews(owner: str, repo: str, pr_numbers: str) -> str:
    """获取指定 PR 的 Reviews（审批状态、评审人）。pr_numbers 逗号分隔。"""
    github_service, db = _get_services()
    if not github_service:
        return "错误: GitHub 服务不可用"

    numbers = [int(n.strip()) for n in pr_numbers.split(",") if n.strip()]
    result = github_service.fetch_all_pr_reviews(owner, repo, numbers)

    reviews = {}
    for item in result.get("results", []):
        if item.get("error") is None:
            review_list = item.get("reviews", [])
            states = {}
            for r in review_list:
                s = r.get("state", "UNKNOWN")
                states[s] = states.get(s, 0) + 1
            reviews[str(item["pr_number"])] = {
                "total_reviews": len(review_list),
                "states": states,
            }
            if db:
                try:
                    db.save_pr_reviews(owner, repo, item["pr_number"], item)
                except Exception:
                    pass

    return json.dumps({
        "owner": owner, "repo": repo,
        "fetched": len(reviews),
        "reviews": reviews,
    }, ensure_ascii=False)


@tool
def check_db_cache(owner: str, repo: str) -> str:
    """检查数据库中已有的数据，避免重复拉取。返回各集合的数据条数。"""
    _, db = _get_services()
    if not db:
        return "数据库不可用"

    try:
        stats = db.get_aggregate_stats(owner, repo)
        pr_data = db.get_pr_data(owner, repo)
        cached_prs = []
        if pr_data:
            cached_prs = [pr["number"] for pr in pr_data.get("data", {}).get("prs", [])]

        return json.dumps({
            "owner": owner, "repo": repo,
            "has_pr_data": pr_data is not None,
            "cached_pr_count": len(cached_prs),
            "cached_pr_numbers": cached_prs[:50],
            "pr_comments_count": stats.get("pr_comments_count", 0),
            "pr_details_count": stats.get("pr_details_count", 0),
        }, ensure_ascii=False)
    except Exception as e:
        return f"查询缓存失败: {e}"


@tool
def query_cicd_results(owner: str, repo: str, page: int = 1, size: int = 5) -> str:
    """查询已有的 CI/CD 分析结果。返回最近的几条结果作为参考。"""
    _, db = _get_services()
    if not db:
        return "数据库不可用"

    try:
        result = db.query_cicd_results(owner, repo, page=page, size=size)
        return json.dumps({
            "owner": owner, "repo": repo,
            "total": result.get("total", 0),
            "results": result.get("data", []),
        }, ensure_ascii=False)
    except Exception as e:
        return f"查询 CI/CD 结果失败: {e}"
