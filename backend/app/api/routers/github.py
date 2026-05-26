"""
GitHub PR 接口路由
"""
from fastapi import HTTPException
from datetime import datetime
from typing import List
import asyncio
import logging

from app.models.schemas import MultiProjectRequest, PRDetailsRequest
from app.models.responses import SourceDataResponse, BatchProjectsResponse, MultiPRCollectionResponse, TokenPoolResponse
from app.services.github_service import task_progress_manager

logger = logging.getLogger(__name__)


def register_github_routes(router, cache, github_service, db):
    """注册 GitHub PR 相关路由"""

    @router.get("/github/prs/{owner}/{repo}", response_model=SourceDataResponse)
    async def get_prs(owner: str, repo: str, max_count: int = 0, start_page: int = 1, use_cache: bool = False):
        """获取指定项目的 PR 数据，max_count=0 表示获取全部，start_page 指定从第几页开始"""
        cache_key = f"github:prs:{owner}/{repo}:{max_count}:{start_page}"

        if use_cache:
            cached_data = cache.get(cache_key)
            if cached_data:
                return {"source": "cache", "data": cached_data}

        result = await github_service.fetch_prs_for_project(owner, repo, max_count=max_count, start_page=start_page)
        if result["error"] is None:
            cache.set(cache_key, result)

        if db is not None:
            try:
                await db.save_pr_data(owner, repo, result)
            except Exception as e:
                logger.error(f"保存到数据库失败: {e}")

        return {"source": "api", "data": result}

    @router.post("/github/prs/{owner}/{repo}/update")
    async def update_prs(owner: str, repo: str):
        """增量更新 PR 数据"""
        if db is None:
            raise HTTPException(status_code=503, detail="数据库未连接")
        result = await db.update_pr_data(owner, repo, github_service)
        if result.get("error"):
            raise HTTPException(status_code=500, detail=result["error"])
        return {**result, "timestamp": datetime.now().isoformat()}

    @router.post("/github/issues/{owner}/{repo}/update")
    async def update_issues(owner: str, repo: str):
        """增量更新 Issues 数据"""
        if db is None:
            raise HTTPException(status_code=503, detail="数据库未连接")
        result = await db.update_issues(owner, repo, github_service)
        if result.get("error"):
            raise HTTPException(status_code=500, detail=result["error"])
        return {**result, "timestamp": datetime.now().isoformat()}

    @router.post("/github/prs/{owner}/{repo}/comments/update")
    async def update_comments(owner: str, repo: str):
        """增量更新 PR 评论数据"""
        if db is None:
            raise HTTPException(status_code=503, detail="数据库未连接")
        result = await db.update_comments(owner, repo, github_service)
        if result.get("error"):
            raise HTTPException(status_code=500, detail=result["error"])
        return {**result, "timestamp": datetime.now().isoformat()}

    @router.post("/github/prs/batch", response_model=BatchProjectsResponse)
    async def get_prs_batch(request: MultiProjectRequest, use_cache: bool = True):
        """批量获取多个项目的 PR 数据"""
        semaphore = asyncio.Semaphore(github_service.max_workers)

        async def _fetch_project(project):
            cache_key = f"github:prs:{project.owner}/{project.repo}"
            if use_cache:
                cached_data = cache.get(cache_key)
                if cached_data:
                    return cached_data
            async with semaphore:
                result = await github_service.fetch_prs_for_project(project.owner, project.repo)
            if result["error"] is None:
                cache.set(cache_key, result)
            if db is not None:
                try:
                    await db.save_pr_data(project.owner, project.repo, result)
                except Exception as e:
                    logger.error(f"保存到数据库失败: {e}")
            return result

        results = await asyncio.gather(*[_fetch_project(p) for p in request.projects])

        return {
            "results": results,
            "total_projects": len(request.projects),
            "success_projects": sum(1 for r in results if r["error"] is None),
            "failed_projects": sum(1 for r in results if r["error"] is not None),
            "total_prs": sum(r["total"] for r in results),
            "timestamp": datetime.now().isoformat()
        }

    @router.get("/github/prs/{owner}/{repo}/comments", response_model=MultiPRCollectionResponse)
    async def get_all_pr_comments(owner: str, repo: str, limit: int = 10):
        """并发获取所有PR的评论"""
        pr_numbers = await _get_pr_numbers(owner, repo, limit, db, github_service)
        semaphore = asyncio.Semaphore(github_service.max_workers)
        results, success_count, failed_count = [], 0, 0

        async def _fetch_comments(pr_num):
            async with semaphore:
                return await github_service.fetch_pr_comments(owner, repo, pr_num)

        task_results = await asyncio.gather(
            *[_fetch_comments(pr_num) for pr_num in pr_numbers],
            return_exceptions=True
        )

        for pr_num, result in zip(pr_numbers, task_results):
            if isinstance(result, Exception):
                failed_count += 1
                logger.error(f"获取PR#{pr_num}评论异常: {result}")
            else:
                results.append(result)
                if result["error"] is None:
                    success_count += 1
                else:
                    failed_count += 1

        # 批量保存到数据库（并行）
        if db is not None:
            save_coros = []
            for result in results:
                if result.get("error") is not None:
                    continue
                pr_num = result.get("pr_number")
                save_coros.append(db.save_pr_comments(owner, repo, pr_num, result))
            if save_coros:
                save_results = await asyncio.gather(*save_coros, return_exceptions=True)
                for i, sr in enumerate(save_results):
                    if isinstance(sr, Exception):
                        logger.error(f"保存评论到数据库失败: {sr}")

        return {
            "owner": owner, "repo": repo, "results": results,
            "total_prs": len(pr_numbers), "success_count": success_count,
            "failed_count": failed_count, "timestamp": datetime.now().isoformat()
        }

    @router.get("/github/prs/{owner}/{repo}/timeline", response_model=MultiPRCollectionResponse)
    async def get_all_pr_timeline(owner: str, repo: str, limit: int = 10):
        """并发获取所有PR的时间线"""
        pr_numbers = await _get_pr_numbers(owner, repo, limit, db, github_service)
        semaphore = asyncio.Semaphore(github_service.max_workers)
        results, success_count, failed_count = [], 0, 0

        async def _fetch_timeline(pr_num):
            async with semaphore:
                return await github_service.fetch_pr_timeline(owner, repo, pr_num)

        task_results = await asyncio.gather(
            *[_fetch_timeline(pr_num) for pr_num in pr_numbers],
            return_exceptions=True
        )

        for pr_num, result in zip(pr_numbers, task_results):
            if isinstance(result, Exception):
                failed_count += 1
                logger.error(f"获取PR#{pr_num}时间线异常: {result}")
            else:
                results.append(result)
                if result["error"] is None:
                    success_count += 1
                else:
                    failed_count += 1

        # 批量保存
        if db is not None:
            save_coros = []
            for result in results:
                if result.get("error") is not None:
                    continue
                pr_num = result.get("pr_number")
                save_coros.append(db.save_pr_timeline(owner, repo, pr_num, result))
            if save_coros:
                save_results = await asyncio.gather(*save_coros, return_exceptions=True)
                for i, sr in enumerate(save_results):
                    if isinstance(sr, Exception):
                        logger.error(f"保存时间线到数据库失败: {sr}")

        return {
            "owner": owner, "repo": repo, "results": results,
            "total_prs": len(pr_numbers), "success_count": success_count,
            "failed_count": failed_count, "timestamp": datetime.now().isoformat()
        }

    @router.get("/github/prs/{owner}/{repo}/{pr_number}/detail")
    async def get_pr_detail(owner: str, repo: str, pr_number: int):
        """获取单个 PR 的详细信息"""
        result = await github_service.fetch_pr_detail(owner, repo, pr_number)
        if db is not None and result["error"] is None:
            await db.save_pr_detail(owner, repo, pr_number, result)
        return {"data": result, "timestamp": datetime.now().isoformat()}

    @router.post("/github/prs/detail/batch")
    async def get_pr_detail_batch(request: PRDetailsRequest):
        """批量获取多个 PR 的详细信息"""
        result = await github_service.fetch_pr_detail_batch(request.owner, request.repo, request.pr_numbers)
        if db is not None:
            save_coros = [db.save_pr_detail(request.owner, request.repo, item["pr_number"], item)
                          for item in result["results"] if item["error"] is None]
            if save_coros:
                await asyncio.gather(*save_coros, return_exceptions=True)
        return {"data": result, "timestamp": datetime.now().isoformat()}

    @router.get("/github/prs/{owner}/{repo}/details", response_model=MultiPRCollectionResponse)
    async def get_all_pr_details(owner: str, repo: str, limit: int = 10):
        """并发获取所有 PR 的详细信息"""
        pr_numbers = await _get_pr_numbers(owner, repo, limit, db, github_service)
        result = await github_service.fetch_pr_detail_batch(owner, repo, pr_numbers)
        if db is not None:
            save_coros = [db.save_pr_detail(owner, repo, item["pr_number"], item)
                          for item in result["results"] if item["error"] is None]
            if save_coros:
                await asyncio.gather(*save_coros, return_exceptions=True)
        return {
            "owner": owner, "repo": repo, "results": result["results"],
            "total_prs": len(pr_numbers), "success_count": result["success_count"],
            "failed_count": result["failed_count"], "timestamp": datetime.now().isoformat()
        }

    @router.get("/github/prs/{owner}/{repo}/{pr_number}/reviews")
    async def get_pr_reviews(owner: str, repo: str, pr_number: int):
        """获取单个 PR 的 Reviews"""
        result = await github_service.fetch_pr_reviews(owner, repo, pr_number)
        if db is not None and result["error"] is None:
            await db.save_pr_reviews(owner, repo, pr_number, result)
        return {"data": result, "timestamp": datetime.now().isoformat()}

    @router.get("/github/prs/{owner}/{repo}/reviews", response_model=MultiPRCollectionResponse)
    async def get_all_pr_reviews(owner: str, repo: str, limit: int = 10):
        """并发获取所有 PR 的 Reviews"""
        pr_numbers = await _get_pr_numbers(owner, repo, limit, db, github_service)
        result = await github_service.fetch_all_pr_reviews(owner, repo, pr_numbers)
        if db is not None:
            save_coros = [db.save_pr_reviews(owner, repo, item["pr_number"], item)
                          for item in result["results"] if item["error"] is None]
            if save_coros:
                await asyncio.gather(*save_coros, return_exceptions=True)
        return {
            "owner": owner, "repo": repo, "results": result["results"],
            "total_prs": len(pr_numbers), "success_count": result["success_count"],
            "failed_count": result["failed_count"], "timestamp": datetime.now().isoformat()
        }

    @router.get("/github/prs/{owner}/{repo}/{pr_number}/commits")
    async def get_pr_commits(owner: str, repo: str, pr_number: int):
        """获取单个 PR 的 Commits"""
        result = await github_service.fetch_pr_commits(owner, repo, pr_number)
        if db is not None and result["error"] is None:
            await db.save_pr_commits(owner, repo, pr_number, result)
        return {"data": result, "timestamp": datetime.now().isoformat()}

    @router.get("/github/prs/{owner}/{repo}/commits", response_model=MultiPRCollectionResponse)
    async def get_all_pr_commits(owner: str, repo: str, limit: int = 10):
        """并发获取所有 PR 的 Commits"""
        pr_numbers = await _get_pr_numbers(owner, repo, limit, db, github_service)
        result = await github_service.fetch_all_pr_commits(owner, repo, pr_numbers)
        if db is not None:
            save_coros = [db.save_pr_commits(owner, repo, item["pr_number"], item)
                          for item in result["results"] if item["error"] is None]
            if save_coros:
                await asyncio.gather(*save_coros, return_exceptions=True)
        return {
            "owner": owner, "repo": repo, "results": result["results"],
            "total_prs": len(pr_numbers), "success_count": result["success_count"],
            "failed_count": result["failed_count"], "timestamp": datetime.now().isoformat()
        }

    @router.get("/github/prs/{owner}/{repo}/{pr_number}/files")
    async def get_pr_files(owner: str, repo: str, pr_number: int):
        """获取单个 PR 的变更文件列表"""
        result = await github_service.fetch_pr_files(owner, repo, pr_number)
        if db is not None and result["error"] is None:
            await db.save_pr_files(owner, repo, pr_number, result["files"])
        return {"data": result, "timestamp": datetime.now().isoformat()}

    @router.get("/github/prs/{owner}/{repo}/files", response_model=MultiPRCollectionResponse)
    async def get_all_pr_files(owner: str, repo: str, limit: int = 10):
        """并发获取所有 PR 的变更文件列表"""
        pr_numbers = await _get_pr_numbers(owner, repo, limit, db, github_service)
        result = await github_service.fetch_all_pr_files(owner, repo, pr_numbers)
        if db is not None:
            save_coros = [db.save_pr_files(owner, repo, item["pr_number"], item["files"])
                          for item in result["results"] if item["error"] is None]
            if save_coros:
                await asyncio.gather(*save_coros, return_exceptions=True)
        return {
            "owner": owner, "repo": repo, "results": result["results"],
            "total_prs": len(pr_numbers), "success_count": result["success_count"],
            "failed_count": result["failed_count"], "timestamp": datetime.now().isoformat()
        }

    @router.get("/github/token-pool", response_model=TokenPoolResponse)
    async def get_token_pool():
        """获取 Token 池信息"""
        return {"token_pool": github_service.token_pool.get_stats(), "timestamp": datetime.now().isoformat()}

    @router.get("/github/users/{username}/profile")
    async def get_user_profile(username: str):
        """获取单个 GitHub 用户 Profile"""
        result = await github_service.fetch_user_profile(username)
        if result.get("error"):
            raise HTTPException(status_code=404, detail=result["error"])
        return {"data": result, "timestamp": datetime.now().isoformat()}

    @router.get("/github/users/{username}/repos")
    async def get_user_repos(username: str, max_pages: int = 3):
        """获取用户参与过的项目"""
        result = await github_service.fetch_user_contributed_repos(username, max_pages=max_pages)
        if result.get("error"):
            raise HTTPException(status_code=500, detail=result["error"])
        if db is not None:
            await db.save_user_repos(username, result)
        return {"data": result, "timestamp": datetime.now().isoformat()}

    @router.post("/github/users/profiles")
    async def get_user_profiles(request: MultiProjectRequest):
        """批量获取 GitHub 用户 Profile，projects 中 name 字段为用户名"""
        usernames = [p.get("name", "") for p in request.projects if p.get("name")]
        if not usernames:
            raise HTTPException(status_code=400, detail="请提供用户名列表")
        result = await github_service.fetch_user_profiles_batch(usernames)
        if db is not None and result.get("profiles"):
            await db.save_user_profiles_batch(result["profiles"])
        return {**result, "timestamp": datetime.now().isoformat()}

    @router.get("/github/prs/{owner}/{repo}/commenters/profiles")
    async def get_commenters_profiles(owner: str, repo: str, limit: int = 20):
        """从 Timeline 触发者中提取去重用户并获取 Profile"""
        if db is None:
            raise HTTPException(status_code=503, detail="数据库未连接")
        # 优先从 issue_timelines 取 actor
        collection = db.db['issue_timelines']
        if await collection.count_documents({"owner": owner, "repo": repo}) > 0:
            cursor = collection.find({"owner": owner, "repo": repo}, {"actor": 1, "_id": 0}).limit(5000)
            docs = await cursor.to_list(length=5000)
            usernames = list(set(d["actor"] for d in docs if d.get("actor")))
        else:
            # 降级到 pr_comments
            cursor = db.db['pr_comments'].find({"owner": owner, "repo": repo}, {"user": 1, "_id": 0}).limit(1000)
            comments = await cursor.to_list(length=1000)
            usernames = list(set(c["user"] for c in comments if c.get("user")))
        if limit > 0:
            usernames = usernames[:limit]
        if not usernames:
            return {"profiles": [], "total": 0, "success_count": 0, "failed_count": 0, "timestamp": datetime.now().isoformat()}
        result = await github_service.fetch_user_profiles_batch(usernames)
        if db is not None and result.get("profiles"):
            await db.save_user_profiles_batch(result["profiles"])
        return {**result, "timestamp": datetime.now().isoformat()}

    @router.get("/github/issues/{owner}/{repo}")
    async def get_issues(owner: str, repo: str, max_count: int = 30, start_page: int = 1, state: str = "all"):
        """获取指定项目的 Issues 数据"""
        result = await github_service.fetch_issues(owner, repo, max_count=max_count, start_page=start_page, state=state)
        if db is not None and result.get("error") is None:
            try:
                await db.save_issues(owner, repo, result)
            except Exception as e:
                logger.error(f"保存 Issues 到数据库失败: {e}")
        return {"source": "api", "data": result, "timestamp": datetime.now().isoformat()}

    @router.get("/github/issues/{owner}/{repo}/{issue_number}/timeline")
    async def get_issue_timeline(owner: str, repo: str, issue_number: int):
        """获取单个 Issue 的 Timeline"""
        result = await github_service.fetch_issue_timeline(owner, repo, issue_number)
        if db is not None and result.get("error") is None:
            try:
                await db.save_issue_timeline(owner, repo, issue_number, result)
            except Exception as e:
                logger.error(f"保存 Issue Timeline 到数据库失败: {e}")
        return {"data": result, "timestamp": datetime.now().isoformat()}

    @router.get("/github/issues/{owner}/{repo}/timelines")
    async def get_issue_timelines(owner: str, repo: str, limit: int = 10):
        """批量获取 Issues 和 PRs 的 Timeline"""
        if db is None:
            raise HTTPException(status_code=503, detail="数据库未连接")
        all_numbers = set()
        # 从 issues 表取编号
        cursor = db.db['issues'].find({"owner": owner, "repo": repo}, {"number": 1, "_id": 0}).sort("number", -1).limit(limit)
        issues = await cursor.to_list(length=limit)
        for i in issues:
            all_numbers.add(i["number"])
        # 从 pr_data 表取编号
        cursor2 = db.db['pr_data'].find({"owner": owner, "repo": repo}, {"pr_number": 1, "_id": 0}).sort("pr_number", -1).limit(limit)
        prs = await cursor2.to_list(length=limit)
        for p in prs:
            all_numbers.add(p["pr_number"])
        issue_numbers = sorted(all_numbers, reverse=True)[:limit]
        if not issue_numbers:
            return {"results": [], "total": 0, "success_count": 0, "failed_count": 0, "timestamp": datetime.now().isoformat()}
        result = await github_service.fetch_issue_timelines_batch(owner, repo, issue_numbers)
        if db is not None:
            for r in result.get("results", []):
                if r.get("error") is None:
                    try:
                        await db.save_issue_timeline(owner, repo, r["issue_number"], r)
                    except Exception:
                        pass
        return {**result, "timestamp": datetime.now().isoformat()}

    @router.get("/github/repos/{owner}/{repo}/stats")
    async def get_repo_stats(owner: str, repo: str):
        """获取仓库在 GitHub 上的各类数据总数"""
        if github_service is None:
            raise HTTPException(status_code=503, detail="GitHub 服务未配置")
        result = await github_service.get_repo_stats(owner, repo)
        return {"stats": result, "timestamp": datetime.now().isoformat()}


async def _get_pr_numbers(owner: str, repo: str, limit: int, db, github_service) -> List[int]:
    """获取 PR 编号列表"""
    if db is not None:
        pr_data = await db.get_pr_data(owner, repo)
        if pr_data:
            prs = pr_data.get("prs", [])
            return [pr["number"] for pr in prs[:limit]]

    pr_result = await github_service.fetch_prs_for_project(owner, repo, max_count=limit)
    if pr_result["error"]:
        raise HTTPException(status_code=404, detail=pr_result["error"])
    return [pr["number"] for pr in pr_result["prs"][:limit]]
