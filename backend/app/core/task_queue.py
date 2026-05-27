"""
异步任务队列管理器
支持后台执行耗时任务，实时查询任务状态和日志
"""
import asyncio
import uuid
import os
import json
from datetime import datetime
from typing import Dict, Any, Optional, List
import logging

logger = logging.getLogger(__name__)

LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "logs", "tasks")


class TaskInfo:
    def __init__(self, task_id: str, task_type: str, description: str, params: dict):
        self.task_id = task_id
        self.task_type = task_type
        self.description = description
        self.params = params
        self.status = "pending"
        self.progress = 0
        self.total = 0
        self.result = None
        self.error = None
        self.created_at = datetime.now().isoformat()
        self.started_at = None
        self.finished_at = None
        self.log_lines = []
        os.makedirs(LOG_DIR, exist_ok=True)

    def log(self, level: str, message: str):
        entry = {"time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "level": level, "message": message}
        self.log_lines.append(entry)
        if len(self.log_lines) > 1000:
            self.log_lines = self.log_lines[-1000:]
        self._append_log_file(entry)

    def _append_log_file(self, entry):
        try:
            log_path = os.path.join(LOG_DIR, f"{self.task_id}.log")
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def to_dict(self, include_log=False):
        d = {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "description": self.description,
            "params": self.params,
            "status": self.status,
            "progress": self.progress,
            "total": self.total,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }
        if include_log:
            d["logs"] = self.log_lines
            d["log_count"] = len(self.log_lines)
        return d


class TaskQueue:
    def __init__(self, max_concurrent: int = 5):
        self.tasks: Dict[str, TaskInfo] = {}
        self._running_keys: Dict[str, str] = {}
        self._concurrency_sem = asyncio.Semaphore(max_concurrent)
        self._db = None

    def set_db(self, db):
        self._db = db

    async def _save_to_db(self, task: TaskInfo):
        if self._db is None:
            return
        try:
            await self._db.db['tasks'].update_one(
                {"task_id": task.task_id},
                {"$set": task.to_dict()},
                upsert=True,
            )
        except Exception:
            pass

    def create_task(self, task_type: str, description: str, params: dict) -> TaskInfo:
        task_id = str(uuid.uuid4())[:8]
        task = TaskInfo(task_id, task_type, description, params)
        self.tasks[task_id] = task
        task.log("INFO", f"任务已创建: {description}")
        return task

    async def _create_task(self, task_type: str, description: str, params: dict) -> TaskInfo:
        task = self.create_task(task_type, description, params)
        await self._save_to_db(task)
        return task

    def get_task(self, task_id: str) -> Optional[TaskInfo]:
        return self.tasks.get(task_id)

    async def get_task_async(self, task_id: str) -> Optional[dict]:
        task = self.tasks.get(task_id)
        if task:
            return task.to_dict(include_log=True)
        if self._db is not None:
            try:
                doc = await self._db.db['tasks'].find_one({"task_id": task_id}, {"_id": 0})
                return doc
            except Exception:
                pass
        return None

    def get_task_logs(self, task_id: str) -> Optional[List[dict]]:
        task = self.tasks.get(task_id)
        if not task:
            log_path = os.path.join(LOG_DIR, f"{task_id}.log")
            if os.path.exists(log_path):
                logs = []
                with open(log_path, "r", encoding="utf-8") as f:
                    for line in f:
                        try:
                            logs.append(json.loads(line.strip()))
                        except Exception:
                            pass
                return logs
            return None
        return task.log_lines

    async def list_tasks(self, status: str = None, limit: int = 50) -> List[dict]:
        result = {}
        for t in self.tasks.values():
            if status and t.status != status:
                continue
            result[t.task_id] = t.to_dict()
        if self._db is not None:
            try:
                query = {"status": status} if status else {}
                cursor = self._db.db['tasks'].find(query, {"_id": 0}).sort("created_at", -1).limit(limit)
                async for doc in cursor:
                    if doc["task_id"] not in result:
                        result[doc["task_id"]] = doc
            except Exception:
                pass
        tasks = list(result.values())
        tasks.sort(key=lambda t: t.get("created_at", ""), reverse=True)
        return tasks[:limit]

    def is_running(self, task_type: str, key: str) -> Optional[TaskInfo]:
        task_id = self._running_keys.get(f"{task_type}:{key}")
        if task_id:
            task = self.tasks.get(task_id)
            if task and task.status == "running":
                return task
        return None

    async def run_task(self, task: TaskInfo, coro_func, key: str = None):
        task.status = "running"
        task.started_at = datetime.now().isoformat()
        if key:
            self._running_keys[f"{task.task_type}:{key}"] = task.task_id
        task.log("INFO", f"任务开始执行")
        await self._save_to_db(task)
        try:
            async with self._concurrency_sem:
                result = await coro_func(task)
            task.result = result
            # 检查返回值是否包含错误信息，统一标记为失败
            if isinstance(result, dict) and result.get("error"):
                task.error = result["error"]
                task.status = "failed"
                task.log("ERROR", f"任务失败: {result['error']}")
            else:
                task.status = "completed"
                task.progress = task.total
                task.log("INFO", f"任务完成, 结果: {json.dumps(result, ensure_ascii=False)[:200]}")
        except Exception as e:
            task.error = str(e)
            task.status = "failed"
            task.log("ERROR", f"任务失败: {e}")
            logger.error(f"任务 {task.task_id} ({task.description}) 失败: {e}")
        finally:
            task.finished_at = datetime.now().isoformat()
            if key:
                self._running_keys.pop(f"{task.task_type}:{key}", None)
            await self._save_to_db(task)

    def delete_task(self, task_id: str) -> bool:
        task = self.tasks.get(task_id)
        if task and task.status not in ("running",):
            del self.tasks[task_id]
            log_path = os.path.join(LOG_DIR, f"{task_id}.log")
            if os.path.exists(log_path):
                os.remove(log_path)
            if self._db is not None:
                try:
                    import asyncio
                    asyncio.create_task(self._db.db['tasks'].delete_one({"task_id": task_id}))
                except Exception:
                    pass
            return True
        return False

    def cleanup(self, max_age_hours: int = 24):
        now = datetime.now()
        to_delete = []
        for tid, task in self.tasks.items():
            if task.status in ("completed", "failed"):
                if task.finished_at:
                    finished = datetime.fromisoformat(task.finished_at)
                    if (now - finished).total_seconds() > max_age_hours * 3600:
                        to_delete.append(tid)
        for tid in to_delete:
            self.delete_task(tid)
        logger.info(f"清理过期任务: {len(to_delete)} 个")


task_queue = TaskQueue()
