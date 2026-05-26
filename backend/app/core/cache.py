"""
数据缓存模块
支持设置过期时间，自动清理过期数据
"""
from typing import Any, Optional, Dict
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class DataCache:
    """
    数据缓存类
    支持设置过期时间，自动清理过期数据
    """

    def __init__(self, default_ttl: int = 300, max_entries: int = 500):
        """
        初始化缓存
        :param default_ttl: 默认过期时间（秒），默认5分钟
        :param max_entries: 最大缓存条目数，超出时 LRU 淘汰
        """
        self._cache: Dict[str, Dict[str, Any]] = {}
        self.default_ttl = default_ttl
        self.max_entries = max_entries
        self._cleanup_count = 0
        logger.info(f"缓存系统初始化，默认过期时间: {default_ttl}秒, 最大条目: {max_entries}")

    def get(self, key: str) -> Optional[Any]:
        """
        获取缓存数据
        :param key: 缓存键
        :return: 缓存数据，如果不存在或已过期则返回 None
        """
        if key not in self._cache:
            return None

        cache_item = self._cache[key]

        # 检查是否过期
        if datetime.now() > cache_item["expires_at"]:
            del self._cache[key]
            logger.debug(f"缓存已过期，已删除: {key}")
            return None

        logger.debug(f"缓存命中: {key}")
        return cache_item["data"]

    def set(self, key: str, data: Any, ttl: Optional[int] = None):
        """
        设置缓存数据
        :param key: 缓存键
        :param data: 缓存数据
        :param ttl: 过期时间（秒），None 则使用默认值
        """
        # LRU 淘汰：超出最大条目数时删除最早创建的
        if len(self._cache) >= self.max_entries:
            oldest_key = min(self._cache, key=lambda k: self._cache[k]["created_at"])
            del self._cache[oldest_key]

        expires_at = datetime.now() + timedelta(seconds=ttl or self.default_ttl)

        self._cache[key] = {
            "data": data,
            "expires_at": expires_at,
            "created_at": datetime.now()
        }

        # 每 50 次 set 自动清理一次过期缓存
        self._cleanup_count += 1
        if self._cleanup_count >= 50:
            self.cleanup_expired()
            self._cleanup_count = 0

        logger.debug(f"缓存已设置: {key}, TTL: {ttl or self.default_ttl}秒")

    def delete(self, key: str) -> bool:
        """
        删除缓存数据
        :param key: 缓存键
        :return: 是否删除成功
        """
        if key in self._cache:
            del self._cache[key]
            logger.debug(f"缓存已删除: {key}")
            return True
        return False

    def clear(self):
        """清空所有缓存"""
        count = len(self._cache)
        self._cache.clear()
        logger.info(f"缓存已清空，删除 {count} 条数据")

    def get_stats(self) -> Dict[str, Any]:
        """
        获取缓存统计信息
        :return: 统计信息字典
        """
        now = datetime.now()
        valid_count = 0
        expired_count = 0

        for key, item in self._cache.items():
            if now > item["expires_at"]:
                expired_count += 1
            else:
                valid_count += 1

        return {
            "total": len(self._cache),
            "valid": valid_count,
            "expired": expired_count,
            "default_ttl": self.default_ttl
        }

    def cleanup_expired(self) -> int:
        """
        清理过期缓存
        :return: 清理的数量
        """
        now = datetime.now()
        expired_keys = [
            key for key, item in self._cache.items()
            if now > item["expires_at"]
        ]

        for key in expired_keys:
            del self._cache[key]

        if expired_keys:
            logger.info(f"清理过期缓存: {len(expired_keys)} 条")

        return len(expired_keys)
