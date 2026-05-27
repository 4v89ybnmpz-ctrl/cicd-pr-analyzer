"""
AtomGit API 路由
通过 AtomGit API v5 获取 PR 数据并保存到数据库
支持: PR 列表/详情/评论/Reviews/Commits/变更文件/时间线/Issues
"""
import logging
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query
from app.models.responses import AtomGitBatchCommentsResponse
from datetime import datetime

logger = logging.getLogger(__name__)


def _get_service():
    """创建 AtomGit 服务实例"""
    from app.gitcode.service import AtomGitService
    from app.gitcode.fetch_comments import load_token

    token = load_token()
    if not token:
        raise HTTPException(status_code=401, detail="未配置 AtomGit Token")

    return AtomGitService(access_token=token)


def register_atomgit_routes(router, db):
    """注册 AtomGit 相关路由"""

    # ========================
    # PR 列表与详情
    # ========================

    @router.get("/atomgit/pulls/{owner}/{repo}")
    async def get_atomgit_pulls(owner: str, repo: str, state: str = "all", page: int = 1, size: int = 20):
        """获取 PR 列表"""
        service = _get_service()
        result = await service.fetch_pulls(owner, repo, state=state, page=page, per_page=size)

        if result.get("error"):
            raise HTTPException(status_code=500, detail=result["error"])

        return {**result, "timestamp": datetime.now().isoformat()}

    @router.get("/atomgit/pulls/{owner}/{repo}/{pull_number}/detail")
    async def get_atomgit_pull_detail(owner: str, repo: str, pull_number: int):
        """获取单个 PR 的详细信息"""
        service = _get_service()
        result = await service.fetch_pull_detail(owner, repo, pull_number)

        if result.get("error"):
            raise HTTPException(status_code=500, detail=result["error"])

        # 保存到数据库
        if db is not None and result.get("detail"):
            detail_data = {
                **result["detail"],
                "platform": "atomgit",
            }
            await db.save_pr_detail(owner, repo, pull_number, detail_data, platform="atomgit")

        return {**result, "timestamp": datetime.now().isoformat()}

    @router.get("/atomgit/pulls/{owner}/{repo}/details")
    async def get_atomgit_all_pull_details(
        owner: str, repo: str,
        pr_numbers: str = Query(..., description="PR 编号列表，逗号分隔"),
        max_workers: int = 3,
    ):
        """
        并发获取多个 PR 的详细信息
        - pr_numbers: 逗号分隔的 PR 编号，如 "1,2,3"
        """
        service = _get_service()
        numbers = [int(n.strip()) for n in pr_numbers.split(",") if n.strip()]
        result = await service.fetch_all_pull_details(owner, repo, numbers, max_workers=max_workers)

        # 保存到数据库
        saved_count = 0
        if db is not None:
            for r in result.get("results", []):
                if r.get("detail") and r.get("error") is None:
                    detail_data = {**r["detail"], "platform": "atomgit"}
                    if await db.save_pr_detail(owner, repo, r["pull_number"], detail_data, platform="atomgit"):
                        saved_count += 1

        return {**result, "owner": owner, "repo": repo, "saved_to_db": saved_count,
                "timestamp": datetime.now().isoformat()}

    # ========================
    # PR 评论
    # ========================

    @router.get("/atomgit/pulls/{owner}/{repo}/{pull_number}/comments")
    async def get_atomgit_pull_comments(owner: str, repo: str, pull_number: int):
        """获取单个 PR 的评论"""
        service = _get_service()
        result = await service.fetch_all_pull_comments(owner, repo, pull_number)

        if result.get("error"):
            raise HTTPException(status_code=500, detail=result["error"])

        # 保存到数据库
        if db is not None and result.get("comments"):
            comments_data = {
                "owner": owner,
                "repo": repo,
                "pull_number": pull_number,
                "comments": result["comments"],
                "total": result["total"],
                "platform": "atomgit",
            }
            await db.save_pr_comments(owner, repo, pull_number, comments_data, platform="atomgit")

        return {**result, "timestamp": datetime.now().isoformat()}

    @router.get("/atomgit/pulls/{owner}/{repo}/comments", response_model=AtomGitBatchCommentsResponse)
    async def get_atomgit_all_comments(owner: str, repo: str, limit: int = 10, state: str = "all"):
        """
        批量获取 PR 评论并保存到数据库
        - limit: 获取 PR 数量
        - state: PR 状态 open/closed/all
        """
        service = _get_service()
        result = await service.fetch_pulls_with_comments(owner, repo, limit=limit, state=state)

        if result.get("error"):
            raise HTTPException(status_code=500, detail=result["error"])

        # 保存到数据库
        saved_count = 0
        if db is not None:
            for pr in result.get("results", []):
                pull_number = pr["pull_number"]
                comments_data = {
                    "owner": owner,
                    "repo": repo,
                    "pull_number": pull_number,
                    "comments": pr.get("comments", []),
                    "total": pr.get("comment_count", 0),
                    "platform": "atomgit",
                    "bot_comments": pr.get("bot_comment_count", 0),
                }
                if await db.save_pr_comments(owner, repo, pull_number, comments_data, platform="atomgit"):
                    saved_count += 1

        return {
            "owner": owner,
            "repo": repo,
            "total_prs": result.get("total_prs", 0),
            "total_comments": result.get("total_comments", 0),
            "bot_comments": result.get("bot_comments", 0),
            "saved_to_db": saved_count,
            "results": [
                {
                    "pull_number": pr["pull_number"],
                    "title": pr["title"],
                    "state": pr["state"],
                    "comment_count": pr.get("comment_count", 0),
                    "bot_comment_count": pr.get("bot_comment_count", 0),
                }
                for pr in result.get("results", [])
            ],
            "timestamp": datetime.now().isoformat(),
        }

    @router.get("/atomgit/pulls/{owner}/{repo}/comments/all", response_model=AtomGitBatchCommentsResponse)
    async def get_atomgit_project_all_comments(
        owner: str, repo: str,
        state: str = "all",
        max_prs: int = 0,
        skip_no_comments: bool = True,
    ):
        """
        获取整个项目的全部 PR 评论并保存到数据库

        - state: PR 状态 open/closed/all
        - max_prs: 最大 PR 数量，0=全部
        - skip_no_comments: 跳过无评论的 PR（默认 true）
        """
        service = _get_service()

        result = await service.fetch_all_project_comments(
            owner, repo,
            state=state,
            max_prs=max_prs,
            skip_no_comments=skip_no_comments,
        )

        if result.get("error"):
            raise HTTPException(status_code=500, detail=result["error"])

        # 保存到数据库
        saved_count = 0
        if db is not None:
            for pr in result.get("results", []):
                pull_number = pr["pull_number"]
                comments_data = {
                    "owner": owner,
                    "repo": repo,
                    "pull_number": pull_number,
                    "comments": pr.get("comments", []),
                    "total": pr.get("comment_count", 0),
                    "platform": "atomgit",
                    "bot_comments": pr.get("bot_comment_count", 0),
                }
                if await db.save_pr_comments(owner, repo, pull_number, comments_data, platform="atomgit"):
                    saved_count += 1

        return {
            "owner": owner,
            "repo": repo,
            "total_prs": result.get("total_prs", 0),
            "total_comments": result.get("total_comments", 0),
            "bot_comments": result.get("bot_comments", 0),
            "saved_to_db": saved_count,
            "results": [
                {
                    "pull_number": pr["pull_number"],
                    "title": pr["title"],
                    "state": pr["state"],
                    "comment_count": pr.get("comment_count", 0),
                    "bot_comment_count": pr.get("bot_comment_count", 0),
                }
                for pr in result.get("results", [])
            ],
            "timestamp": datetime.now().isoformat(),
        }

    # ========================
    # PR Reviews
    # ========================

    @router.get("/atomgit/pulls/{owner}/{repo}/{pull_number}/reviews")
    async def get_atomgit_pull_reviews(owner: str, repo: str, pull_number: int):
        """获取单个 PR 的 Reviews"""
        service = _get_service()
        result = await service.fetch_pull_reviews(owner, repo, pull_number)

        if result.get("error"):
            raise HTTPException(status_code=500, detail=result["error"])

        # 保存到数据库
        if db is not None and result.get("reviews"):
            reviews_data = {
                "owner": owner,
                "repo": repo,
                "pull_number": pull_number,
                "reviews": result["reviews"],
                "total": result["total"],
                "platform": "atomgit",
            }
            await db.save_pr_reviews(owner, repo, pull_number, reviews_data, platform="atomgit")

        return {**result, "timestamp": datetime.now().isoformat()}

    @router.get("/atomgit/pulls/{owner}/{repo}/reviews")
    async def get_atomgit_all_pull_reviews(
        owner: str, repo: str,
        pr_numbers: str = Query(..., description="PR 编号列表，逗号分隔"),
        max_workers: int = 3,
    ):
        """并发获取多个 PR 的 Reviews"""
        service = _get_service()
        numbers = [int(n.strip()) for n in pr_numbers.split(",") if n.strip()]
        result = await service.fetch_all_pull_reviews(owner, repo, numbers, max_workers=max_workers)

        # 保存到数据库
        saved_count = 0
        if db is not None:
            for r in result.get("results", []):
                if r.get("reviews") and r.get("error") is None:
                    reviews_data = {
                        "owner": owner, "repo": repo,
                        "pull_number": r["pull_number"],
                        "reviews": r["reviews"],
                        "total": r["total"],
                        "platform": "atomgit",
                    }
                    if await db.save_pr_reviews(owner, repo, r["pull_number"], reviews_data, platform="atomgit"):
                        saved_count += 1

        return {**result, "owner": owner, "repo": repo, "saved_to_db": saved_count,
                "timestamp": datetime.now().isoformat()}

    # ========================
    # PR Commits
    # ========================

    @router.get("/atomgit/pulls/{owner}/{repo}/{pull_number}/commits")
    async def get_atomgit_pull_commits(owner: str, repo: str, pull_number: int):
        """获取单个 PR 的 Commits"""
        service = _get_service()
        result = await service.fetch_pull_commits(owner, repo, pull_number)

        if result.get("error"):
            raise HTTPException(status_code=500, detail=result["error"])

        # 保存到数据库
        if db is not None and result.get("commits"):
            commits_data = {
                "owner": owner,
                "repo": repo,
                "pull_number": pull_number,
                "commits": result["commits"],
                "total": result["total"],
                "platform": "atomgit",
            }
            await db.save_pr_commits(owner, repo, pull_number, commits_data, platform="atomgit")

        return {**result, "timestamp": datetime.now().isoformat()}

    @router.get("/atomgit/pulls/{owner}/{repo}/commits")
    async def get_atomgit_all_pull_commits(
        owner: str, repo: str,
        pr_numbers: str = Query(..., description="PR 编号列表，逗号分隔"),
        max_workers: int = 3,
    ):
        """并发获取多个 PR 的 Commits"""
        service = _get_service()
        numbers = [int(n.strip()) for n in pr_numbers.split(",") if n.strip()]
        result = await service.fetch_all_pull_commits(owner, repo, numbers, max_workers=max_workers)

        # 保存到数据库
        saved_count = 0
        if db is not None:
            for r in result.get("results", []):
                if r.get("commits") and r.get("error") is None:
                    commits_data = {
                        "owner": owner, "repo": repo,
                        "pull_number": r["pull_number"],
                        "commits": r["commits"],
                        "total": r["total"],
                        "platform": "atomgit",
                    }
                    if await db.save_pr_commits(owner, repo, r["pull_number"], commits_data, platform="atomgit"):
                        saved_count += 1

        return {**result, "owner": owner, "repo": repo, "saved_to_db": saved_count,
                "timestamp": datetime.now().isoformat()}

    # ========================
    # PR 变更文件
    # ========================

    @router.get("/atomgit/pulls/{owner}/{repo}/{pull_number}/files")
    async def get_atomgit_pull_files(owner: str, repo: str, pull_number: int):
        """获取单个 PR 的变更文件列表"""
        service = _get_service()
        result = await service.fetch_pull_files(owner, repo, pull_number)

        if result.get("error"):
            raise HTTPException(status_code=500, detail=result["error"])

        # 保存到数据库
        if db is not None and result.get("files"):
            await db.save_pr_files(owner, repo, pull_number, result["files"], platform="atomgit")

        return {**result, "timestamp": datetime.now().isoformat()}

    @router.get("/atomgit/pulls/{owner}/{repo}/files")
    async def get_atomgit_all_pull_files(
        owner: str, repo: str,
        pr_numbers: str = Query(..., description="PR 编号列表，逗号分隔"),
        max_workers: int = 3,
    ):
        """并发获取多个 PR 的变更文件"""
        service = _get_service()
        numbers = [int(n.strip()) for n in pr_numbers.split(",") if n.strip()]
        result = await service.fetch_all_pull_files(owner, repo, numbers, max_workers=max_workers)

        # 保存到数据库
        saved_count = 0
        if db is not None:
            for r in result.get("results", []):
                if r.get("files") and r.get("error") is None:
                    if await db.save_pr_files(owner, repo, r["pull_number"], r["files"], platform="atomgit"):
                        saved_count += 1

        return {**result, "owner": owner, "repo": repo, "saved_to_db": saved_count,
                "timestamp": datetime.now().isoformat()}

    # ========================
    # PR 时间线
    # ========================

    @router.get("/atomgit/pulls/{owner}/{repo}/{pull_number}/timeline")
    async def get_atomgit_pull_timeline(owner: str, repo: str, pull_number: int):
        """获取单个 PR 的时间线事件"""
        service = _get_service()
        result = await service.fetch_pull_timeline(owner, repo, pull_number)

        if result.get("error"):
            raise HTTPException(status_code=500, detail=result["error"])

        # 保存到数据库
        if db is not None and result.get("events"):
            timeline_data = {
                "owner": owner,
                "repo": repo,
                "pull_number": pull_number,
                "events": result["events"],
                "total": result["total"],
                "platform": "atomgit",
            }
            await db.save_pr_timeline(owner, repo, pull_number, timeline_data, platform="atomgit")

        return {**result, "timestamp": datetime.now().isoformat()}

    @router.get("/atomgit/pulls/{owner}/{repo}/timelines")
    async def get_atomgit_all_pull_timelines(
        owner: str, repo: str,
        pr_numbers: str = Query(..., description="PR 编号列表，逗号分隔"),
        max_workers: int = 3,
    ):
        """并发获取多个 PR 的时间线"""
        service = _get_service()
        numbers = [int(n.strip()) for n in pr_numbers.split(",") if n.strip()]
        result = await service.fetch_all_pull_timelines(owner, repo, numbers, max_workers=max_workers)

        # 保存到数据库
        saved_count = 0
        if db is not None:
            for r in result.get("results", []):
                if r.get("events") and r.get("error") is None:
                    timeline_data = {
                        "owner": owner, "repo": repo,
                        "pull_number": r["pull_number"],
                        "events": r["events"],
                        "total": r["total"],
                        "platform": "atomgit",
                    }
                    if await db.save_pr_timeline(owner, repo, r["pull_number"], timeline_data, platform="atomgit"):
                        saved_count += 1

        return {**result, "owner": owner, "repo": repo, "saved_to_db": saved_count,
                "timestamp": datetime.now().isoformat()}

    # ========================
    # Issues
    # ========================

    @router.get("/atomgit/issues/{owner}/{repo}")
    async def get_atomgit_issues(
        owner: str, repo: str,
        state: str = "all",
        page: int = 1,
        size: int = 20,
        max_count: int = 0,
    ):
        """
        获取仓库的 Issue 列表（不含 PR）
        - state: 状态 open/closed/all
        - max_count: 最大数量，0=不限
        """
        service = _get_service()
        result = await service.fetch_issues(
            owner, repo, state=state, page=page, per_page=size, max_count=max_count,
        )

        if result.get("error"):
            raise HTTPException(status_code=500, detail=result["error"])

        return {**result, "timestamp": datetime.now().isoformat()}

    @router.get("/atomgit/issues/{owner}/{repo}/{issue_number}")
    async def get_atomgit_issue_detail(owner: str, repo: str, issue_number: int):
        """获取单个 Issue 的详细信息"""
        service = _get_service()
        result = await service.fetch_issue_detail(owner, repo, issue_number)

        if result.get("error"):
            raise HTTPException(status_code=500, detail=result["error"])

        return {**result, "timestamp": datetime.now().isoformat()}
