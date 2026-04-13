"""
AtomGit API 路由
通过 AtomGit API v5 获取 PR 评论数据并保存到数据库
"""
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException
from datetime import datetime

logger = logging.getLogger(__name__)


def register_atomgit_routes(router, db):
    """注册 AtomGit 相关路由"""

    @router.get("/atomgit/pulls/{owner}/{repo}")
    async def get_atomgit_pulls(owner: str, repo: str, state: str = "all", page: int = 1, size: int = 20):
        """获取 PR 列表"""
        from app.gitcode.service import AtomGitService
        from app.gitcode.fetch_comments import load_token

        token = load_token()
        if not token:
            raise HTTPException(status_code=401, detail="未配置 AtomGit Token")

        service = AtomGitService(access_token=token)
        result = service.fetch_pulls(owner, repo, state=state, page=page, per_page=size)

        if result.get("error"):
            raise HTTPException(status_code=500, detail=result["error"])

        return {**result, "timestamp": datetime.now().isoformat()}

    @router.get("/atomgit/pulls/{owner}/{repo}/{pull_number}/comments")
    async def get_atomgit_pull_comments(owner: str, repo: str, pull_number: int):
        """获取单个 PR 的评论"""
        from app.gitcode.service import AtomGitService
        from app.gitcode.fetch_comments import load_token

        token = load_token()
        if not token:
            raise HTTPException(status_code=401, detail="未配置 AtomGit Token")

        service = AtomGitService(access_token=token)
        result = service.fetch_all_pull_comments(owner, repo, pull_number)

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
            db.save_pr_comments(owner, repo, pull_number, comments_data)

        return {**result, "timestamp": datetime.now().isoformat()}

    @router.get("/atomgit/pulls/{owner}/{repo}/comments")
    async def get_atomgit_all_comments(owner: str, repo: str, limit: int = 10, state: str = "all"):
        """
        批量获取 PR 评论并保存到数据库
        - limit: 获取 PR 数量
        - state: PR 状态 open/closed/all
        """
        from app.gitcode.service import AtomGitService
        from app.gitcode.fetch_comments import load_token

        token = load_token()
        if not token:
            raise HTTPException(status_code=401, detail="未配置 AtomGit Token")

        service = AtomGitService(access_token=token)
        result = service.fetch_pulls_with_comments(owner, repo, limit=limit, state=state)

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
                if db.save_pr_comments(owner, repo, pull_number, comments_data):
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

    @router.get("/atomgit/pulls/{owner}/{repo}/comments/all")
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
        from app.gitcode.service import AtomGitService
        from app.gitcode.fetch_comments import load_token

        token = load_token()
        if not token:
            raise HTTPException(status_code=401, detail="未配置 AtomGit Token")

        service = AtomGitService(access_token=token)

        # 保存计数
        saved = {"count": 0}

        def on_pr_done(pull_number, comment_count, bot_count, total_done):
            """每个 PR 完成后保存到数据库"""
            if db is None:
                return
            # 从结果中取最新的一条
            # 回调中无法直接拿 comments，用6通过 service 重新获取太浪费
            # 改为在主流程中保存
            pass

        result = service.fetch_all_project_comments(
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
                if db.save_pr_comments(owner, repo, pull_number, comments_data):
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
