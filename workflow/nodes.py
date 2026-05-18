"""
工作流节点函数
每个节点对应 pipeline 中的一个步骤
调用现有服务层完成具体工作
"""
import logging
from datetime import datetime
from typing import Dict, Any

from .state import PipelineState
from .config import workflow_config

logger = logging.getLogger(__name__)


def fetch_pr_list_node(state: PipelineState) -> Dict[str, Any]:
    """
    节点: 获取 PR 列表
    """
    cfg = workflow_config
    owner = state["owner"]
    repo = state["repo"]
    max_prs = state.get("max_prs", 0)

    logger.info(f"[节点] 获取 PR 列表: {owner}/{repo} (max={max_prs})")

    result = cfg.github_service.fetch_prs_for_project(owner, repo, max_count=max_prs)

    if result["error"]:
        return {
            "errors": state.get("errors", []) + [f"fetch_pr_list: {result['error']}"],
            "current_step": "fetch_pr_list_failed",
        }

    pr_numbers = [pr["number"] for pr in result["prs"]]

    # 保存到数据库
    if cfg.db is not None:
        try:
            cfg.db.save_pr_data(owner, repo, result)
        except Exception as e:
            logger.warning(f"保存 PR 数据失败: {e}")

    return {
        "pr_list": result["prs"],
        "pr_numbers": pr_numbers,
        "current_step": "fetch_pr_list",
        "progress": 10.0,
    }


def fetch_comments_node(state: PipelineState) -> Dict[str, Any]:
    """
    节点: 并发获取所有 PR 评论
    """
    cfg = workflow_config
    owner = state["owner"]
    repo = state["repo"]
    pr_numbers = state.get("pr_numbers", [])

    logger.info(f"[节点] 获取评论: {owner}/{repo}, {len(pr_numbers)} 个 PR")

    from concurrent.futures import ThreadPoolExecutor, as_completed

    results = {}
    errors = state.get("errors", [])

    with ThreadPoolExecutor(max_workers=cfg.github_service.max_workers) as executor:
        futures = {
            executor.submit(cfg.github_service.fetch_pr_comments, owner, repo, pr_num): pr_num
            for pr_num in pr_numbers
        }
        for future in as_completed(futures):
            pr_num = futures[future]
            try:
                result = future.result()
                results[str(pr_num)] = result
                if result["error"] is None and cfg.db is not None:
                    cfg.db.save_pr_comments(owner, repo, pr_num, result)
            except Exception as e:
                errors.append(f"fetch_comments PR#{pr_num}: {e}")

    return {
        "comments": results,
        "current_step": "fetch_comments",
        "progress": 40.0,
        "errors": errors,
    }


def fetch_details_node(state: PipelineState) -> Dict[str, Any]:
    """
    节点: 并发获取 PR 详情
    """
    cfg = workflow_config
    owner = state["owner"]
    repo = state["repo"]
    pr_numbers = state.get("pr_numbers", [])

    logger.info(f"[节点] 获取详情: {owner}/{repo}, {len(pr_numbers)} 个 PR")

    result = cfg.github_service.fetch_pr_detail_batch(owner, repo, pr_numbers)

    details = {}
    if cfg.db is not None:
        for item in result.get("results", []):
            if item.get("error") is None:
                details[str(item["pr_number"])] = item
                cfg.db.save_pr_detail(owner, repo, item["pr_number"], item)

    return {
        "details": details,
        "current_step": "fetch_details",
        "progress": 55.0,
    }


def fetch_reviews_node(state: PipelineState) -> Dict[str, Any]:
    """
    节点: 并发获取 PR Reviews
    """
    cfg = workflow_config
    owner = state["owner"]
    repo = state["repo"]
    pr_numbers = state.get("pr_numbers", [])

    logger.info(f"[节点] 获取 Reviews: {owner}/{repo}, {len(pr_numbers)} 个 PR")

    result = cfg.github_service.fetch_all_pr_reviews(owner, repo, pr_numbers)

    reviews = {}
    if cfg.db is not None:
        for item in result.get("results", []):
            if item.get("error") is None:
                reviews[str(item["pr_number"])] = item
                cfg.db.save_pr_reviews(owner, repo, item["pr_number"], item)

    return {
        "reviews": reviews,
        "current_step": "fetch_reviews",
        "progress": 70.0,
    }


def analyze_cicd_node(state: PipelineState) -> Dict[str, Any]:
    """
    节点: CI/CD 分析
    从评论中提取 CI/CD 结果，存入 cicd_results 集合
    """
    from app.analysis.cicd_extractor import CICDExtractor

    owner = state["owner"]
    repo = state["repo"]
    comments_data = state.get("comments", {})

    logger.info(f"[节点] CI/CD 分析: {owner}/{repo}")

    extractor = CICDExtractor()
    all_results = []

    for pr_num_str, comment_data in comments_data.items():
        comments = comment_data.get("comments", [])
        pr_number = int(pr_num_str) if pr_num_str.isdigit() else None

        structured = extractor.extract_batch_structured(comments, owner=owner, repo=repo, pr_number=pr_number)
        for r in structured:
            all_results.append(r.to_db_dict())

    # 保存到数据库
    if workflow_config.db is not None and all_results:
        workflow_config.db.save_cicd_results_batch(all_results)

    return {
        "cicd_results": all_results,
        "current_step": "analyze_cicd",
        "progress": 90.0,
    }


def generate_report_node(state: PipelineState) -> Dict[str, Any]:
    """
    节点: 生成洞察报告
    """
    from app.api.routers.analysis import _build_insights

    owner = state["owner"]
    repo = state["repo"]
    db = workflow_config.db

    logger.info(f"[节点] 生成报告: {owner}/{repo}")

    if db is None:
        return {
            "report": {"error": "数据库未连接"},
            "current_step": "generate_report",
            "progress": 100.0,
            "completed_at": datetime.now().isoformat(),
        }

    summary = db.get_cicd_summary_from_db(owner, repo)
    trends = db.get_cicd_trends_from_db(owner, repo)
    failure = db.get_cicd_failure_analysis_from_db(owner, repo)
    insights = _build_insights(summary, failure)

    report = {
        "owner": owner,
        "repo": repo,
        "summary": summary,
        "trends": trends,
        "failure_analysis": failure,
        "insights": insights,
        "data_source_count": summary.get("total", 0),
        "generated_at": datetime.now().isoformat(),
    }

    return {
        "report": report,
        "current_step": "generate_report",
        "progress": 100.0,
        "completed_at": datetime.now().isoformat(),
    }
