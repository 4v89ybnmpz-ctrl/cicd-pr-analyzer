"""
多仓库对比分析接口路由
"""
from fastapi import APIRouter, HTTPException
from typing import List
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


def register_compare_routes(router: APIRouter, db):
    """注册多仓库对比路由"""

    @router.post("/analysis/compare", tags=["多仓库对比"])
    async def compare_projects(body: dict):
        """多项目横向对比分析"""
        if db is None:
            raise HTTPException(status_code=503, detail="数据库未连接")

        projects = body.get("projects", [])
        dimensions = body.get("dimensions", None)

        if not projects or len(projects) < 2:
            raise HTTPException(status_code=400, detail="至少需要 2 个项目进行对比")

        result = await db.compare_projects(projects, dimensions)
        if result.get("error"):
            raise HTTPException(status_code=500, detail=result["error"])

        return {**result, "timestamp": datetime.now().isoformat()}

    @router.get("/analysis/compare/contributors-overlap", tags=["多仓库对比"])
    async def get_contributors_overlap(projects: str = ""):
        """跨项目贡献者重叠分析"""
        if db is None:
            raise HTTPException(status_code=503, detail="数据库未连接")

        project_keys = [p.strip() for p in projects.split(",") if p.strip()]
        if len(project_keys) < 2:
            raise HTTPException(status_code=400, detail="至少需要 2 个项目，用逗号分隔")

        result = await db.get_contributors_overlap(project_keys)
        if result.get("error"):
            raise HTTPException(status_code=500, detail=result["error"])

        return {
            "contributors": result.get("contributors", []),
            "total": result.get("total", 0),
            "projects": project_keys,
            "timestamp": datetime.now().isoformat(),
        }
