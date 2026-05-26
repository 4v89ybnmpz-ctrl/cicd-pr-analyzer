"""
任务接口路由
"""
from fastapi import HTTPException
from datetime import datetime
import logging

from app.core.task_queue import task_queue

logger = logging.getLogger(__name__)


def register_task_routes(router, cache, github_service, db):
    """注册任务相关路由"""

    @router.get("/tasks")
    async def get_all_tasks(status: str = None):
        """获取所有任务（含数据库历史）"""
        tasks = await task_queue.list_tasks(status, 50)
        counts = {"total": len(tasks), "running": 0, "completed": 0, "failed": 0, "pending": 0}
        for t in tasks:
            s = t.get("status", "")
            if s in counts:
                counts[s] += 1
        return {"tasks": tasks, "counts": counts, "timestamp": datetime.now().isoformat()}

    @router.get("/tasks/{task_id}")
    async def get_task(task_id: str):
        """获取任务详情（含日志）"""
        task = await task_queue.get_task_async(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="任务不存在")
        return {"task": task, "timestamp": datetime.now().isoformat()}

    @router.get("/tasks/{task_id}/logs")
    async def get_task_logs(task_id: str):
        """获取任务日志"""
        logs = task_queue.get_task_logs(task_id)
        if logs is None:
            raise HTTPException(status_code=404, detail="任务不存在")
        # 补全旧日志中缺失的年月日
        task = task_queue.get_task(task_id)
        task_date = None
        if task and task.created_at:
            task_date = task.created_at[:10]
        else:
            # 从数据库查
            try:
                doc = await db.db['tasks'].find_one({"task_id": task_id}, {"created_at": 1, "_id": 0})
                if doc and doc.get("created_at"):
                    task_date = doc["created_at"][:10]
            except Exception:
                pass
        if task_date:
            for log in logs:
                t = log.get("time", "")
                if t and "-" not in t:
                    log["time"] = f"{task_date} {t}"
        return {"task_id": task_id, "logs": logs, "total": len(logs), "timestamp": datetime.now().isoformat()}

    @router.delete("/tasks/{task_id}")
    async def delete_task(task_id: str):
        """删除任务"""
        task = task_queue.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="任务不存在")
        if task_queue.delete_task(task_id):
            return {"message": "任务已删除", "timestamp": datetime.now().isoformat()}
        raise HTTPException(status_code=400, detail="任务正在运行中，无法删除")
