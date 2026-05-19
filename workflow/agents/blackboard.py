"""
共享黑板 (Shared Blackboard)
Agent 间通过黑板共享数据和中间结果
支持: 发布/订阅模式、数据版本控制、过期清理
"""
import logging
import time
import threading
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class DataType(str, Enum):
    """黑板数据类型"""
    COLLECTION_RESULT = "collection_result"
    ANALYSIS_RESULT = "analysis_result"
    REPORT_RESULT = "report_result"
    VALIDATION_RESULT = "validation_result"
    PLAN = "plan"
    METRICS = "metrics"
    CUSTOM = "custom"


@dataclass
class BlackboardEntry:
    """黑板条目"""
    key: str
    data_type: DataType
    value: Any
    producer: str
    timestamp: float = field(default_factory=time.time)
    version: int = 1
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def age_seconds(self) -> float:
        return time.time() - self.timestamp

    def is_expired(self, ttl_seconds: float = 3600) -> bool:
        return self.age_seconds > ttl_seconds


# 订阅回调类型
SubscribeCallback = Callable[[str, BlackboardEntry], None]


class SharedBlackboard:
    """
    共享黑板

    Agent 间的数据交换中心:
    - 写入: Agent 将中间结果写入黑板
    - 读取: 其他 Agent 从黑板获取所需数据
    - 订阅: Agent 订阅特定类型的数据变更通知
    - 版本: 每次更新版本号递增，支持版本追踪

    使用方式:
        blackboard = SharedBlackboard()
        blackboard.write("collection/rust-lang/rust", DataType.COLLECTION_RESULT, data, producer="collector")
        data = blackboard.read("collection/rust-lang/rust")
    """

    def __init__(self, default_ttl: float = 3600):
        self._store: Dict[str, BlackboardEntry] = {}
        self._subscribers: Dict[DataType, List[SubscribeCallback]] = {}
        self._lock = threading.Lock()
        self._default_ttl = default_ttl
        self._write_count = 0
        self._read_count = 0

    def write(self, key: str, data_type: DataType, value: Any,
              producer: str, metadata: Dict[str, Any] = None) -> BlackboardEntry:
        """
        写入黑板
        如果 key 已存在，更新值并递增版本号
        """
        with self._lock:
            version = 1
            if key in self._store:
                version = self._store[key].version + 1

            entry = BlackboardEntry(
                key=key,
                data_type=data_type,
                value=value,
                producer=producer,
                version=version,
                metadata=metadata or {},
            )
            self._store[key] = entry
            self._write_count += 1

        logger.debug(f"黑板写入: {key} (type={data_type}, producer={producer}, v{version})")

        # 通知订阅者
        self._notify_subscribers(data_type, key, entry)

        return entry

    def read(self, key: str) -> Optional[Any]:
        """从黑板读取数据值"""
        entry = self.read_entry(key)
        return entry.value if entry else None

    def read_entry(self, key: str) -> Optional[BlackboardEntry]:
        """从黑板读取完整条目"""
        with self._lock:
            entry = self._store.get(key)
            if entry and entry.is_expired(self._default_ttl):
                del self._store[key]
                logger.debug(f"黑板过期清理: {key}")
                return None
            self._read_count += 1
            return entry

    def read_by_type(self, data_type: DataType) -> List[BlackboardEntry]:
        """按类型读取所有条目"""
        with self._lock:
            return [
                entry for entry in self._store.values()
                if entry.data_type == data_type and not entry.is_expired(self._default_ttl)
            ]

    def read_by_prefix(self, prefix: str) -> List[BlackboardEntry]:
        """按键前缀读取所有条目"""
        with self._lock:
            return [
                entry for key, entry in self._store.items()
                if key.startswith(prefix) and not entry.is_expired(self._default_ttl)
            ]

    def delete(self, key: str) -> bool:
        """删除条目"""
        with self._lock:
            if key in self._store:
                del self._store[key]
                return True
            return False

    def subscribe(self, data_type: DataType, callback: SubscribeCallback):
        """订阅特定类型的数据变更"""
        if data_type not in self._subscribers:
            self._subscribers[data_type] = []
        self._subscribers[data_type].append(callback)

    def _notify_subscribers(self, data_type: DataType, key: str, entry: BlackboardEntry):
        """通知订阅者"""
        callbacks = self._subscribers.get(data_type, [])
        for cb in callbacks:
            try:
                cb(key, entry)
            except Exception as e:
                logger.warning(f"黑板订阅回调失败: {e}")

    def cleanup_expired(self):
        """清理所有过期条目"""
        with self._lock:
            expired_keys = [
                key for key, entry in self._store.items()
                if entry.is_expired(self._default_ttl)
            ]
            for key in expired_keys:
                del self._store[key]

        if expired_keys:
            logger.info(f"黑板清理: {len(expired_keys)} 条过期数据")

    def clear(self):
        """清空黑板"""
        with self._lock:
            self._store.clear()
            self._write_count = 0
            self._read_count = 0

    def summary(self) -> Dict[str, Any]:
        """黑板状态摘要"""
        with self._lock:
            type_counts = {}
            for entry in self._store.values():
                t = entry.data_type.value
                type_counts[t] = type_counts.get(t, 0) + 1

            return {
                "total_entries": len(self._store),
                "type_counts": type_counts,
                "total_writes": self._write_count,
                "total_reads": self._read_count,
                "keys": list(self._store.keys()),
            }


# 全局黑板实例
blackboard = SharedBlackboard()
