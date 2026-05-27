"""
GitCode API 接口路由
"""
from fastapi import HTTPException
from app.models.responses import GitCodeMultiMRResponse
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


def register_gitcode_routes(router, gitcode_service, db):
    """注册 GitCode 相关路由"""

    @router.get("/gitcode/mrs/{owner}/{repo}")
    async def get_gitcode_merge_requests(owner: str, repo: str, state: str = "all", page: int = 1, size: int = 20):
        """获取 GitCode 合并请求列表"""
        if gitcode_service is None:
            raise HTTPException(status_code=503, detail="GitCode 服务未配置")
        result = await gitcode_service.fetch_merge_requests(owner, repo, state, page, size)
        if result.get("error"):
            raise HTTPException(status_code=500, detail=result["error"])
        return {**result, "timestamp": datetime.now().isoformat()}

    @router.get("/gitcode/mrs/{owner}/{repo}/{mr_iid}/comments")
    async def get_gitcode_mr_comments(owner: str, repo: str, mr_iid: int):
        """获取 GitCode MR 评论"""
        if gitcode_service is None:
            raise HTTPException(status_code=503, detail="GitCode 服务未配置")
        result = await gitcode_service.fetch_mr_comments(owner, repo, mr_iid)
        if result.get("error"):
            raise HTTPException(status_code=500, detail=result["error"])
        if db is not None:
            await db.save_pr_comments(owner, repo, mr_iid, {**result, "platform": "gitcode"}, platform="gitcode")
        return {**result, "timestamp": datetime.now().isoformat()}

    @router.get("/gitcode/mrs/{owner}/{repo}/{mr_iid}/detail")
    async def get_gitcode_mr_detail(owner: str, repo: str, mr_iid: int):
        """获取 GitCode MR 详细信息"""
        if gitcode_service is None:
            raise HTTPException(status_code=503, detail="GitCode 服务未配置")
        result = await gitcode_service.fetch_mr_detail(owner, repo, mr_iid)
        if result.get("error"):
            raise HTTPException(status_code=500, detail=result["error"])
        if db is not None:
            await db.save_pr_detail(owner, repo, mr_iid, {**result, "platform": "gitcode"}, platform="gitcode")
        return {**result, "timestamp": datetime.now().isoformat()}

    @router.get("/gitcode/mrs/{owner}/{repo}/{mr_iid}/changes")
    async def get_gitcode_mr_changes(owner: str, repo: str, mr_iid: int):
        """获取 GitCode MR 代码变更"""
        if gitcode_service is None:
            raise HTTPException(status_code=503, detail="GitCode 服务未配置")
        result = await gitcode_service.fetch_mr_changes(owner, repo, mr_iid)
        if result.get("error"):
            raise HTTPException(status_code=500, detail=result["error"])
        return {**result, "timestamp": datetime.now().isoformat()}

    @router.get("/gitcode/mrs/{owner}/{repo}/comments", response_model=GitCodeMultiMRResponse)
    async def get_all_gitcode_mr_comments(owner: str, repo: str, limit: int = 10):
        """并发获取 GitCode 所有 MR 的评论"""
        if gitcode_service is None:
            raise HTTPException(status_code=503, detail="GitCode 服务未配置")
        results = await gitcode_service.fetch_all_mr_comments(owner, repo, limit)
        return {"owner": owner, "repo": repo, "results": results, "total_mrs": len(results), "timestamp": datetime.now().isoformat()}

    @router.get("/gitcode/mrs/{owner}/{repo}/details", response_model=GitCodeMultiMRResponse)
    async def get_all_gitcode_mr_details(owner: str, repo: str, limit: int = 10):
        """并发获取 GitCode 所有 MR 的详细信息"""
        if gitcode_service is None:
            raise HTTPException(status_code=503, detail="GitCode 服务未配置")
        results = await gitcode_service.fetch_all_mr_details(owner, repo, limit)
        if db is not None:
            for item in results:
                if item.get("error") is None:
                    await db.save_pr_detail(owner, repo, item["mr_iid"], {**item, "platform": "gitcode"}, platform="gitcode")
        return {"owner": owner, "repo": repo, "results": results, "total_mrs": len(results), "timestamp": datetime.now().isoformat()}
