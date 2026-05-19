"""
数据库接口路由
"""
from fastapi import HTTPException
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


def register_database_routes(router, db):
    """注册数据库相关路由"""

    @router.get("/database/stats")
    async def get_database_stats():
        """获取数据库统计信息"""
        if db is None:
            raise HTTPException(status_code=503, detail="数据库未连接")
        stats = db.get_stats()
        return {"stats": stats, "timestamp": datetime.now().isoformat()}

    @router.get("/database/prs")
    async def list_database_prs(limit: int = 100):
        """列出数据库中的 PR 数据"""
        if db is None:
            raise HTTPException(status_code=503, detail="数据库未连接")
        data = db.list_pr_data(limit=limit)
        return {"data": data, "total": len(data), "timestamp": datetime.now().isoformat()}

    @router.get("/database/prs/{owner}/{repo}")
    async def get_database_pr(owner: str, repo: str):
        """获取数据库中的 PR 数据"""
        if db is None:
            raise HTTPException(status_code=503, detail="数据库未连接")
        data = db.get_pr_data(owner, repo)
        if not data:
            raise HTTPException(status_code=404, detail="数据不存在")
        return {"data": data, "timestamp": datetime.now().isoformat()}

    @router.delete("/database/prs/{owner}/{repo}")
    async def delete_database_pr(owner: str, repo: str):
        """删除数据库中的 PR 数据"""
        if db is None:
            raise HTTPException(status_code=503, detail="数据库未连接")
        if not db.delete_pr_data(owner, repo):
            raise HTTPException(status_code=404, detail="数据不存在")
        return {"message": "数据已删除", "owner": owner, "repo": repo, "timestamp": datetime.now().isoformat()}

    @router.get("/database/comments")
    async def query_pr_comments(owner: str = None, repo: str = None, page: int = 1, size: int = 20,
                                sort_by: str = "updated_at", sort_order: str = "desc"):
        """查询 PR 评论数据"""
        if db is None:
            raise HTTPException(status_code=503, detail="数据库未连接")
        sort_order_int = -1 if sort_order == "desc" else 1
        result = db.list_pr_comments(owner, repo, page, size, sort_by, sort_order_int)
        return {**result, "timestamp": datetime.now().isoformat()}

    @router.get("/database/timeline")
    async def query_pr_timeline(owner: str = None, repo: str = None, page: int = 1, size: int = 20,
                                sort_by: str = "updated_at", sort_order: str = "desc"):
        """查询 PR 时间线数据"""
        if db is None:
            raise HTTPException(status_code=503, detail="数据库未连接")
        sort_order_int = -1 if sort_order == "desc" else 1
        result = db.list_pr_timeline(owner, repo, page, size, sort_by, sort_order_int)
        return {**result, "timestamp": datetime.now().isoformat()}

    @router.get("/database/reviews")
    async def query_pr_reviews(owner: str = None, repo: str = None, page: int = 1, size: int = 20,
                               sort_by: str = "updated_at", sort_order: str = "desc"):
        """查询 PR Reviews 数据"""
        if db is None:
            raise HTTPException(status_code=503, detail="数据库未连接")
        sort_order_int = -1 if sort_order == "desc" else 1
        result = db.list_pr_reviews(owner, repo, page, size, sort_by, sort_order_int)
        return {**result, "timestamp": datetime.now().isoformat()}

    @router.get("/database/commits")
    async def query_pr_commits(owner: str = None, repo: str = None, page: int = 1, size: int = 20,
                               sort_by: str = "updated_at", sort_order: str = "desc"):
        """查询 PR Commits 数据"""
        if db is None:
            raise HTTPException(status_code=503, detail="数据库未连接")
        sort_order_int = -1 if sort_order == "desc" else 1
        result = db.list_pr_commits(owner, repo, page, size, sort_by, sort_order_int)
        return {**result, "timestamp": datetime.now().isoformat()}

    @router.get("/database/details")
    async def query_pr_details(owner: str = None, repo: str = None, page: int = 1, size: int = 20,
                               sort_by: str = "updated_at", sort_order: str = "desc",
                               state: str = None, start_time: str = None, end_time: str = None):
        """查询 PR 详细信息数据"""
        if db is None:
            raise HTTPException(status_code=503, detail="数据库未连接")
        sort_order_int = -1 if sort_order == "desc" else 1
        result = db.list_pr_details(owner, repo, page, size, sort_by, sort_order_int, state, start_time, end_time)
        return {**result, "timestamp": datetime.now().isoformat()}

    @router.get("/database/details/search")
    async def search_pr_details(keyword: str, owner: str = None, repo: str = None, page: int = 1, size: int = 20):
        """模糊搜索 PR 详细信息"""
        if db is None:
            raise HTTPException(status_code=503, detail="数据库未连接")
        result = db.search_pr_details(keyword, owner, repo, page, size)
        return {**result, "timestamp": datetime.now().isoformat()}

    @router.get("/database/aggregate")
    async def get_aggregate_stats(owner: str = None, repo: str = None):
        """聚合统计"""
        if db is None:
            raise HTTPException(status_code=503, detail="数据库未连接")
        result = db.get_aggregate_stats(owner, repo)
        return {"stats": result, "timestamp": datetime.now().isoformat()}