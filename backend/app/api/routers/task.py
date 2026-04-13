"""
任务接口路由
"""
from fastapi import HTTPException
from datetime import datetime
from typing import List
import logging
import asyncio
import uuid

from app.services.github_service import task_progress_manager

logger = logging.getLogger(__name__)


def register_task_routes(router, cache, github_service, db):
    """注册任务相关路由"""

    @router.get("/tasks")
    async def get_all_tasks():
        """获取所有任务"""
        tasks = task_progress_manager.get_all_tasks()
        return {"tasks": tasks, "total": len(tasks), "timestamp": datetime.now().isoformat()}

    @router.get("/tasks/{task_id}")
    async def get_task(task_id: str):
        """获取任务进度"""
        task = task_progress_manager.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="任务不存在")
        return {"task": task, "timestamp": datetime.now().isoformat()}

    @router.delete("/tasks/{task_id}")
    async def delete_task(task_id: str):
        """删除任务"""
        task = task_progress_manager.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="任务不存在")
        task_progress_manager.delete_task(task_id)
        return {"message": "任务已删除", "task_id": task_id, "timestamp": datetime.now().isoformat()}

    @router.post("/github/prs/batch-async")
    async def get_prs_batch_async(request, use_cache: bool = True):
        """批量获取多个项目的 PR 数据（异步）"""
        task_id = str(uuid.uuid4())
        task = task_progress_manager.create_task(task_id, total=len(request.projects))
        asyncio.create_task(_fetch_prs_async(task_id, request.projects, use_cache, cache, github_service, db))
        return {"task_id": task_id, "status": task["status"], "message": "任务已创建", "timestamp": datetime.now().isoformat()}


async def _fetch_prs_async(task_id: str, projects: List, use_cache: bool, cache, github_service, db):
    """异步获取 PR 数据的后台任务"""
    results = []
    for i, project in enumerate(projects):
        cache_key = f"github:prs:{project.owner}/{project.repo}"

        if use_cache:
            cached_data = cache.get(cache_key)
            if cached_data:
                results.append(cached_data)
                task_progress_manager.update_task(task_id, current=i + 1, message=f"从缓存获取 {project.owner}/{project.repo}")
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
        task_progress_manager.update_task(task_id, current=i + 1, message=f"已获取 {project.owner}/{project.repo}")