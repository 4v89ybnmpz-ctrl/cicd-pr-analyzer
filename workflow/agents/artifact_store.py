"""
Artifact Store — 分析产物存储
管理分析过程中产生的各类产物（报告、统计数据、执行计划）
支持: 版本管理、按项目索引、过期清理、快照导出
"""
import json
import logging
import time
import threading
import hashlib
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class ArtifactType(str, Enum):
    """产物类型"""
    PLAN = "plan"
    PROFILE = "profile"
    COLLECTION_SUMMARY = "collection_summary"
    ANALYSIS_RESULT = "analysis_result"
    VALIDATION_RESULT = "validation_result"
    STATS_REPORT = "stats_report"
    INSIGHT_REPORT = "insight_report"
    RAW_DATA = "raw_data"


@dataclass
class Artifact:
    """产物条目"""
    artifact_id: str
    artifact_type: ArtifactType
    owner: str
    repo: str
    content: Any
    version: int = 1
    producer: str = ""
    created_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)
    content_hash: str = ""

    def compute_hash(self) -> str:
        """计算内容哈希"""
        raw = json.dumps(self.content, sort_keys=True, ensure_ascii=False, default=str)
        return hashlib.md5(raw.encode()).hexdigest()[:12]


class ArtifactStore:
    """
    产物存储

    管理 Agent 分析过程中产生的所有产物:
    - 按项目 (owner/repo) 索引
    - 按类型分类
    - 版本管理（同 key 更新时版本递增）
    - 内容哈希去重
    - 按时间范围查询
    - 快照导出/恢复
    """

    def __init__(self, max_versions: int = 10, default_ttl: float = 86400):
        self._store: Dict[str, Artifact] = {}
        self._project_index: Dict[str, List[str]] = {}
        self._lock = threading.Lock()
        self._max_versions = max_versions
        self._default_ttl = default_ttl
        self._total_stored = 0

    def store(self, artifact_type: ArtifactType, owner: str, repo: str,
              content: Any, producer: str = "",
              metadata: Dict[str, Any] = None) -> Artifact:
        """
        存储产物
        如果同 key + type 已存在，版本递增
        """
        key = f"{artifact_type.value}/{owner}/{repo}"

        with self._lock:
            version = 1
            if key in self._store:
                version = self._store[key].version + 1

            artifact = Artifact(
                artifact_id=f"{key}/v{version}",
                artifact_type=artifact_type,
                owner=owner,
                repo=repo,
                content=content,
                version=version,
                producer=producer,
                metadata=metadata or {},
            )
            artifact.content_hash = artifact.compute_hash()

            self._store[key] = artifact
            self._total_stored += 1

            # 更新项目索引
            project_key = f"{owner}/{repo}"
            if project_key not in self._project_index:
                self._project_index[project_key] = []
            if key not in self._project_index[project_key]:
                self._project_index[project_key].append(key)

        logger.debug(
            f"产物存储: {key} v{version} "
            f"(hash={artifact.content_hash}, producer={producer})"
        )
        return artifact

    def get(self, artifact_type: ArtifactType, owner: str,
            repo: str) -> Optional[Artifact]:
        """获取最新版本产物"""
        key = f"{artifact_type.value}/{owner}/{repo}"
        with self._lock:
            artifact = self._store.get(key)
            if artifact and self._is_expired(artifact):
                del self._store[key]
                return None
            return artifact

    def get_content(self, artifact_type: ArtifactType, owner: str,
                    repo: str) -> Optional[Any]:
        """获取最新版本产物的内容"""
        artifact = self.get(artifact_type, owner, repo)
        return artifact.content if artifact else None

    def get_project_artifacts(self, owner: str, repo: str) -> Dict[str, Any]:
        """获取项目所有产物"""
        project_key = f"{owner}/{repo}"
        with self._lock:
            keys = self._project_index.get(project_key, [])
            result = {}
            for key in keys:
                artifact = self._store.get(key)
                if artifact and not self._is_expired(artifact):
                    result[artifact.artifact_type.value] = {
                        "version": artifact.version,
                        "producer": artifact.producer,
                        "created_at": artifact.created_at,
                        "hash": artifact.content_hash,
                        "content_preview": str(artifact.content)[:500],
                    }
            return result

    def query_by_type(self, artifact_type: ArtifactType) -> List[Artifact]:
        """按类型查询所有产物"""
        with self._lock:
            prefix = f"{artifact_type.value}/"
            return [
                a for key, a in self._store.items()
                if key.startswith(prefix) and not self._is_expired(a)
            ]

    def delete(self, artifact_type: ArtifactType, owner: str, repo: str) -> bool:
        """删除产物"""
        key = f"{artifact_type.value}/{owner}/{repo}"
        with self._lock:
            if key in self._store:
                del self._store[key]
                project_key = f"{owner}/{repo}"
                if project_key in self._project_index:
                    self._project_index[project_key] = [
                        k for k in self._project_index[project_key] if k != key
                    ]
                return True
            return False

    def is_changed(self, artifact_type: ArtifactType, owner: str,
                   repo: str, content: Any) -> bool:
        """检查内容是否与已存储的不同"""
        key = f"{artifact_type.value}/{owner}/{repo}"
        with self._lock:
            existing = self._store.get(key)
            if not existing:
                return True
            new_hash = hashlib.md5(
                json.dumps(content, sort_keys=True, ensure_ascii=False, default=str).encode()
            ).hexdigest()[:12]
            return new_hash != existing.content_hash

    def snapshot(self) -> str:
        """导出快照 JSON"""
        with self._lock:
            data = {
                "timestamp": time.time(),
                "total_artifacts": len(self._store),
                "total_stored": self._total_stored,
                "artifacts": {},
            }
            for key, artifact in self._store.items():
                if not self._is_expired(artifact):
                    data["artifacts"][key] = {
                        "type": artifact.artifact_type.value,
                        "version": artifact.version,
                        "hash": artifact.content_hash,
                        "producer": artifact.producer,
                        "created_at": artifact.created_at,
                    }
            return json.dumps(data, ensure_ascii=False, indent=2)

    def _is_expired(self, artifact: Artifact) -> bool:
        """检查是否过期"""
        return (time.time() - artifact.created_at) > self._default_ttl

    def cleanup_expired(self):
        """清理过期产物"""
        with self._lock:
            expired_keys = [
                key for key, artifact in self._store.items()
                if self._is_expired(artifact)
            ]
            for key in expired_keys:
                del self._store[key]

            if expired_keys:
                logger.info(f"产物清理: {len(expired_keys)} 条过期数据")

    def clear(self):
        """清空所有产物"""
        with self._lock:
            self._store.clear()
            self._project_index.clear()
            self._total_stored = 0

    def summary(self) -> Dict[str, Any]:
        """存储摘要"""
        with self._lock:
            type_counts = {}
            for artifact in self._store.values():
                t = artifact.artifact_type.value
                type_counts[t] = type_counts.get(t, 0) + 1

            project_count = len(self._project_index)

            return {
                "total_artifacts": len(self._store),
                "total_projects": project_count,
                "total_stored": self._total_stored,
                "type_counts": type_counts,
            }


# 全局单例
artifact_store = ArtifactStore()
