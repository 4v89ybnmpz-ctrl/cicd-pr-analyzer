"""
服务基类模块
提供公共服务功能（异步版本）
"""
import asyncio
import time
from typing import Dict, Any, List, Optional
import logging
from functools import wraps
import re

logger = logging.getLogger(__name__)


def retry_on_failure(max_retries: int = 3, delay: int = 5):
    """
    异步重试装饰器
    :param max_retries: 最大重试次数
    :param delay: 重试间隔（秒）
    :return: 装饰器函数
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        logger.warning(f"请求失败 (尝试 {attempt + 1}/{max_retries}): {e}, {delay}秒后重试...")
                        await asyncio.sleep(delay)
                    else:
                        logger.error(f"请求失败，已达到最大重试次数 {max_retries}: {e}")
            raise last_exception
        return wrapper
    return decorator


class TokenPool:
    """
    Token 池管理基类（异步安全）
    支持多个 Token 轮询使用
    """

    def __init__(self, tokens: List[str]):
        """
        初始化 Token 池
        :param tokens: Token 列表
        """
        self.tokens = tokens if tokens else []
        self.current_index = 0
        self.lock = asyncio.Lock()
        logger.info(f"Token 池初始化完成，共 {len(self.tokens)} 个 Token")

    async def get_token(self) -> Optional[str]:
        """
        获取下一个可用的 Token
        :return: Token 字符串
        """
        if not self.tokens:
            return None

        async with self.lock:
            token = self.tokens[self.current_index]
            self.current_index = (self.current_index + 1) % len(self.tokens)
            return token

    async def add_token(self, token: str):
        """添加 Token"""
        async with self.lock:
            if token not in self.tokens:
                self.tokens.append(token)
                logger.info(f"Token 已添加，当前共 {len(self.tokens)} 个 Token")

    def get_stats(self) -> Dict[str, Any]:
        """获取 Token 池统计信息"""
        return {
            "total_tokens": len(self.tokens),
            "current_index": self.current_index
        }


class TaskProgress:
    """
    任务进度管理类（异步安全）
    用于跟踪异步任务的进度
    """

    def __init__(self):
        """初始化任务进度管理器"""
        self.tasks: Dict[str, Dict[str, Any]] = {}
        self.lock = asyncio.Lock()
        logger.info("任务进度管理器初始化完成")

    async def create_task(self, task_id: str, total: int = 100) -> Dict[str, Any]:
        """创建新任务"""
        task = {
            "task_id": task_id,
            "status": "pending",
            "progress": 0.0,
            "total": total,
            "current": 0,
            "message": "任务已创建",
            "created_at": time.time(),
            "updated_at": time.time()
        }

        async with self.lock:
            self.tasks[task_id] = task

        logger.info(f"任务已创建: {task_id}")
        return task

    async def update_task(self, task_id: str, current: int, message: str = "") -> Optional[Dict[str, Any]]:
        """更新任务进度"""
        async with self.lock:
            if task_id not in self.tasks:
                return None

            task = self.tasks[task_id]
            task["current"] = current
            task["progress"] = (current / task["total"] * 100) if task["total"] > 0 else 0
            task["message"] = message
            task["updated_at"] = time.time()

            if task["progress"] >= 100:
                task["status"] = "completed"
                task["message"] = "任务已完成"

            return task

    async def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务信息"""
        async with self.lock:
            return self.tasks.get(task_id)

    async def get_all_tasks(self) -> List[Dict[str, Any]]:
        """获取所有任务"""
        async with self.lock:
            return list(self.tasks.values())

    async def delete_task(self, task_id: str) -> bool:
        """删除任务"""
        async with self.lock:
            if task_id in self.tasks:
                del self.tasks[task_id]
                logger.info(f"任务已删除: {task_id}")
                return True
            return False


class BotDetector:
    """
    Bot 用户检测器
    """

    KNOWN_BOT_PATTERNS = [
        "github-actions[bot]", "dependabot[bot]", "renovate[bot]",
        "greenkeeper[bot]", "pre-commit-ci[bot]", "codecov-io[bot]",
        "coveralls[bot]", "snyk-bot", "jenkins-bot", "circleci",
        "travis-ci", "gitcode-bot", "semantic-release-bot",
    ]

    BOT_REGEX_PATTERNS = [
        r".*-bot$",
        r".*\[bot\]$",
        r".*_bot$",
        r"^bot-.*",
    ]

    @classmethod
    def is_bot(cls, username: str, user_type: str = None) -> bool:
        """
        判断用户是否为 Bot
        :param username: 用户名
        :param user_type: 用户类型
        :return: 是否为 Bot
        """
        if not username:
            return False

        if user_type and user_type.lower() == "bot":
            return True

        if username.lower() in [p.lower() for p in cls.KNOWN_BOT_PATTERNS]:
            return True

        for pattern in cls.BOT_REGEX_PATTERNS:
            if re.match(pattern, username, re.IGNORECASE):
                return True

        return False


# 全局任务进度管理器
task_progress_manager = TaskProgress()
