"""
GitHub PR 接口路由
"""
from fastapi import HTTPException
from datetime import datetime
from typing import List
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging

from app.models.schemas import MultiProjectRequest, PRDetailsRequest
from app.services.github_service import task_progress_manager

logger = logging.getLogger(__name__)


def register_github_routes(router, cache, github_service, db):
    """注册 GitHub PR 相关路由"""

    @router.get("/github/prs/{owner}/{repo}")
    async def get_prs(owner: str, repo: str, use_cache: bool = True):
        """获取指定项目的 PR 数据"""
        cache_key = f"github:prs:{owner}/{repo}"

        if use_cache:
            cached_data = cache.get(cache_key)
            if cached_data:
                return {"source": "cache", "data": cached_data}

        result = github_service.fetch_prs_for_project(owner, repo)
        if result["error"] is None:
            cache.set(cache_key, result)

        if db is not None:
            try:
                db.save_pr_data(owner, repo, result)
            except Exception as e:
                logger.error(f"保存到数据库失败: {e}")

        return {"source": "api", "data": result}

    @router.post("/github/prs/batch")
    async def get_prs_batch(request: MultiProjectRequest, use_cache: bool = True):
        """批量获取多个项目的 PR 数据"""
        results = []
        for project in request.projects:
            cache_key = f"github:prs:{project.owner}/{project.repo}"

            if use_cache:
                cached_data = cache.get(cache_key)
                if cached_data:
                    results.append(cached_data)
                    continue

            result = github_service.fetch_prs_for_project(project.owner, project.repo)
            if result["error"] is None:
                cache.set(cache_key, result)

            if db is not None:
                try:
                    db.save_pr_data(project.owner, project.repo, result)
                except Exception as e:
                    logger.error(f"保存到数据库失败: {e}")

            results.append(result)

        return {
            "results": results,
            "total_projects": len(request.projects),
            "success_projects": sum(1 for r in results if r["error"] is None),
            "failed_projects": sum(1 for r in results if r["error"] is not None),
            "total_prs": sum(r["total"] for r in results),
            "timestamp": datetime.now().isoformat()
        }

    @router.get("/github/prs/{owner}/{repo}/comments")
    async def get_all_pr_comments(owner: str, repo: str, limit: int = 10):
        """并发获取所有PR的评论"""
        pr_numbers = _get_pr_numbers(owner, repo, limit, db, github_service)
        results, success_count, failed_count = [], 0, 0

        with ThreadPoolExecutor(max_workers=github_service.max_workers) as executor:
            futures = {
                executor.submit(github_service.fetch_pr_comments, owner, repo, pr_num): pr_num
                for pr_num in pr_numbers
            }
            for future in as_completed(futures):
                pr_num = futures[future]
                try:
                    result = future.result()
                    results.append(result)
                    if result["error"] is None:
                        success_count += 1
                        if db is not None:
                            db.save_pr_comments(owner, repo, pr_num, result)
                    else:
                        failed_count += 1
                except Exception as e:
                    failed_count += 1
                    logger.error(f"获取PR#{pr_num}评论异常: {e}")

        return {
            "owner": owner, "repo": repo, "results": results,
            "total_prs": len(pr_numbers), "success_count": success_count,
            "failed_count": failed_count, "timestamp": datetime.now().isoformat()
        }

    @router.get("/github/prs/{owner}/{repo}/timeline")
    async def get_all_pr_timeline(owner: str, repo: str, limit: int = 10):
        """并发获取所有PR的时间线"""
        pr_numbers = _get_pr_numbers(owner, repo, limit, db, github_service)
        results, success_count, failed_count = [], 0, 0

        with ThreadPoolExecutor(max_workers=github_service.max_workers) as executor:
            futures = {
                executor.submit(github_service.fetch_pr_timeline, owner, repo, pr_num): pr_num
                for pr_num in pr_numbers
            }
            for future in as_completed(futures):
                pr_num = futures[future]
                try:
                    result = future.result()
                    results.append(result)
                    if result["error"] is None:
                        success_count += 1
                        if db is not None:
                            db.save_pr_timeline(owner, repo, pr_num, result)
                    else:
                        failed_count += 1
                except Exception as e:
                    failed_count += 1
                    logger.error(f"获取PR#{pr_num}时间线异常: {e}")

        return {
            "owner": owner, "repo": repo, "results": results,
            "total_prs": len(pr_numbers), "success_count": success_count,
            "failed_count": failed_count, "timestamp": datetime.now().isoformat()
        }

    @router.get("/github/prs/{owner}/{repo}/{pr_number}/detail")
    async def get_pr_detail(owner: str, repo: str, pr_number: int):
        """获取单个 PR 的详细信息"""
        result = github_service.fetch_pr_detail(owner, repo, pr_number)
        if db is not None and result["error"] is None:
            db.save_pr_detail(owner, repo, pr_number, result)
        return {"data": result, "timestamp": datetime.now().isoformat()}

    @router.post("/github/prs/detail/batch")
    async def get_pr_detail_batch(request: PRDetailsRequest):
        """批量获取多个 PR 的详细信息"""
        result = github_service.fetch_pr_detail_batch(request.owner, request.repo, request.pr_numbers)
        if db is not None:
            for item in result["results"]:
                if item["error"] is None:
                    db.save_pr_detail(request.owner, request.repo, item["pr_number"], item)
        return {"data": result, "timestamp": datetime.now().isoformat()}

    @router.get("/github/prs/{owner}/{repo}/details")
    async def get_all_pr_details(owner: str, repo: str, limit: int = 10):
        """并发获取所有 PR 的详细信息"""
        pr_numbers = _get_pr_numbers(owner, repo, limit, db, github_service)
        result = github_service.fetch_pr_detail_batch(owner, repo, pr_numbers)
        if db is not None:
            for item in result["results"]:
                if item["error"] is None:
                    db.save_pr_detail(owner, repo, item["pr_number"], item)
        return {
            "owner": owner, "repo": repo, "results": result["results"],
            "total_prs": len(pr_numbers), "success_count": result["success_count"],
            "failed_count": result["failed_count"], "timestamp": datetime.now().isoformat()
        }

    @router.get("/github/prs/{owner}/{repo}/{pr_number}/reviews")
    async def get_pr_reviews(owner: str, repo: str, pr_number: int):
        """获取单个 PR 的 Reviews"""
        result = github_service.fetch_pr_reviews(owner, repo, pr_number)
        if db is not None and result["error"] is None:
            db.save_pr_reviews(owner, repo, pr_number, result)
        return {"data": result, "timestamp": datetime.now().isoformat()}

    @router.get("/github/prs/{owner}/{repo}/reviews")
    async def get_all_pr_reviews(owner: str, repo: str, limit: int = 10):
        """并发获取所有 PR 的 Reviews"""
        pr_numbers = _get_pr_numbers(owner, repo, limit, db, github_service)
        result = github_service.fetch_all_pr_reviews(owner, repo, pr_numbers)
        if db is not None:
            for item in result["results"]:
                if item["error"] is None:
                    db.save_pr_reviews(owner, repo, item["pr_number"], item)
        return {
            "owner": owner, "repo": repo, "results": result["results"],
            "total_prs": len(pr_numbers), "success_count": result["success_count"],
            "failed_count": result["failed_count"], "timestamp": datetime.now().isoformat()
        }

    @router.get("/github/prs/{owner}/{repo}/{pr_number}/commits")
    async def get_pr_commits(owner: str, repo: str, pr_number: int):
        """获取单个 PR 的 Commits"""
        result = github_service.fetch_pr_commits(owner, repo, pr_number)
        if db is not None and result["error"] is None:
            db.save_pr_commits(owner, repo, pr_number, result)
        return {"data": result, "timestamp": datetime.now().isoformat()}

    @router.get("/github/prs/{owner}/{repo}/commits")
    async def get_all_pr_commits(owner: str, repo: str, limit: int = 10):
        """并发获取所有 PR 的 Commits"""
        pr_numbers = _get_pr_numbers(owner, repo, limit, db, github_service)
        result = github_service.fetch_all_pr_commits(owner, repo, pr_numbers)
        if db is not None:
            for item in result["results"]:
                if item["error"] is None:
                    db.save_pr_commits(owner, repo, item["pr_number"], item)
        return {
            "owner": owner, "repo": repo, "results": result["results"],
            "total_prs": len(pr_numbers), "success_count": result["success_count"],
            "failed_count": result["failed_count"], "timestamp": datetime.now().isoformat()
        }

    @router.get("/github/token-pool")
    async def get_token_pool():
        """获取 Token 池信息"""
        return {"token_pool": github_service.token_pool.get_stats(), "timestamp": datetime.now().isoformat()}


def _get_pr_numbers(owner: str, repo: str, limit: int, db, github_service) -> List[int]:
    """获取 PR 编号列表"""
    if db is not None:
        pr_data = db.get_pr_data(owner, repo)
        if pr_data:
            prs = pr_data.get("data", {}).get("prs", [])
            return [pr["number"] for pr in prs[:limit]]

    pr_result = github_service.fetch_prs_for_project(owner, repo, max_count=limit)
    if pr_result["error"]:
        raise HTTPException(status_code=404, detail=pr_result["error"])
    return [pr["number"] for pr in pr_result["prs"][:limit]]