"""
Collector Agent 增强工具集
支持: 增量采集、并发拉取、断点续传、进度上报
"""
import json
import logging
import time
from typing import Dict, Any, List, Optional
from langchain_core.tools import tool
from concurrent.futures import ThreadPoolExecutor, as_completed

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

    if db:
        try:
            db.save_pr_data(owner, repo, result)
        except Exception as e:
            logger.warning(f"数据库写入失败: {e}")

    pr_numbers = [pr["number"] for pr in result["prs"]]
    summary = {
        "owner": owner, "repo": repo,
        "total_prs": result["total"],
        "pr_numbers": pr_numbers[:50],
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
                except Exception as e:
                    logger.warning(f"数据库写入失败: {e}")
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
                except Exception as e:
                    logger.warning(f"数据库写入失败: {e}")

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
                except Exception as e:
                    logger.warning(f"数据库写入失败: {e}")

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


@tool
def incremental_fetch(owner: str, repo: str) -> str:
    """增量采集: 只拉取数据库中没有的新 PR 数据（评论+详情+Reviews）。
    返回新增数据量。适合重复分析同一项目时使用。"""
    github_service, db = _get_services()
    if not github_service:
        return "错误: GitHub 服务不可用"

    result_summary = {
        "owner": owner, "repo": repo,
        "mode": "incremental",
        "new_prs": 0,
        "new_comments": 0,
        "new_details": 0,
        "new_reviews": 0,
    }

    # 获取数据库已有 PR
    existing_prs = set()
    if db:
        try:
            pr_data = db.get_pr_data(owner, repo)
            if pr_data:
                existing_prs = {
                    pr["number"] for pr in pr_data.get("data", {}).get("prs", [])
                }
        except Exception as e:
            logger.warning(f"数据库写入失败: {e}")

    # 获取最新 PR 列表
    pr_result = github_service.fetch_prs_for_project(owner, repo, max_count=0)
    if pr_result["error"]:
        return f"获取 PR 列表失败: {pr_result['error']}"

    all_prs = {pr["number"] for pr in pr_result["prs"]}
    new_prs = all_prs - existing_prs

    if not new_prs:
        return json.dumps({**result_summary, "message": "无新增 PR"}, ensure_ascii=False)

    result_summary["new_prs"] = len(new_prs)

    # 保存更新后的 PR 列表
    if db:
        try:
            db.save_pr_data(owner, repo, pr_result)
        except Exception as e:
            logger.warning(f"数据库写入失败: {e}")

    # 拉取新 PR 的数据
    new_pr_list = sorted(list(new_prs))[:100]  # 限制最多 100 个

    for pr_num in new_pr_list:
        try:
            comment_result = github_service.fetch_pr_comments(owner, repo, pr_num)
            if comment_result["error"] is None and db:
                db.save_pr_comments(owner, repo, pr_num, comment_result)
                result_summary["new_comments"] += comment_result["total"]
        except Exception as e:
            logger.warning(f"数据库写入失败: {e}")

    try:
        detail_result = github_service.fetch_pr_detail_batch(owner, repo, new_pr_list)
        for item in detail_result.get("results", []):
            if item.get("error") is None and db:
                try:
                    db.save_pr_detail(owner, repo, item["pr_number"], item)
                    result_summary["new_details"] += 1
                except Exception as e:
                    logger.warning(f"数据库写入失败: {e}")
    except Exception as e:
        logger.warning(f"数据库写入失败: {e}")

    try:
        review_result = github_service.fetch_all_pr_reviews(owner, repo, new_pr_list)
        for item in review_result.get("results", []):
            if item.get("error") is None and db:
                try:
                    db.save_pr_reviews(owner, repo, item["pr_number"], item)
                    result_summary["new_reviews"] += 1
                except Exception as e:
                    logger.warning(f"数据库写入失败: {e}")
    except Exception as e:
        logger.warning(f"数据库写入失败: {e}")

    return json.dumps(result_summary, ensure_ascii=False)


@tool
def parallel_fetch(owner: str, repo: str, pr_numbers: str,
                   data_types: str = "comments,details,reviews") -> str:
    """并发拉取多个 PR 的多种数据类型。data_types 是逗号分隔的类型列表。
    适合需要快速拉取大量数据的场景。"""
    github_service, db = _get_services()
    if not github_service:
        return "错误: GitHub 服务不可用"

    numbers = [int(n.strip()) for n in pr_numbers.split(",") if n.strip()]
    types = [t.strip() for t in data_types.split(",") if t.strip()]

    results = {"owner": owner, "repo": repo, "fetched_prs": len(numbers)}
    total_items = 0

    def _fetch_one(pr_num, data_type):
        try:
            if data_type == "comments":
                r = github_service.fetch_pr_comments(owner, repo, pr_num)
                if r["error"] is None and db:
                    db.save_pr_comments(owner, repo, pr_num, r)
                return ("comments", pr_num, r.get("total", 0), r["error"])
            elif data_type == "details":
                r = github_service.fetch_pr_detail_batch(owner, repo, [pr_num])
                items = r.get("results", [])
                if items and items[0].get("error") is None and db:
                    db.save_pr_detail(owner, repo, pr_num, items[0])
                return ("details", pr_num, 1 if items else 0, None)
            elif data_type == "reviews":
                r = github_service.fetch_all_pr_reviews(owner, repo, [pr_num])
                items = r.get("results", [])
                if items and items[0].get("error") is None and db:
                    db.save_pr_reviews(owner, repo, pr_num, items[0])
                return ("reviews", pr_num, len(items[0].get("reviews", [])) if items else 0, None)
        except Exception as e:
            return (data_type, pr_num, 0, str(e))
        return (data_type, pr_num, 0, "unknown type")

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = []
        for pr_num in numbers:
            for dt in types:
                futures.append(pool.submit(_fetch_one, pr_num, dt))

        for future in as_completed(futures):
            data_type, pr_num, count, error = future.result()
            total_items += count
            if error:
                logger.debug(f"并发拉取失败: {data_type} PR#{pr_num}: {error}")

    results["total_items"] = total_items
    results["data_types"] = types
    return json.dumps(results, ensure_ascii=False)
