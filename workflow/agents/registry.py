"""
Agent Registry — Agent 注册表
统一管理所有 Agent 的注册、发现、生命周期和热替换
替代 orchestrator_agent.py 中分散的 _agents 字典
"""
import logging
import time
import threading
from typing import Dict, Any, List, Optional, Type
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class AgentStatus(str, Enum):
    """Agent 运行状态"""
    CREATED = "created"
    IDLE = "idle"
    RUNNING = "running"
    ERROR = "error"
    DESTROYED = "destroyed"


@dataclass
class AgentDescriptor:
    """Agent 描述符"""
    name: str
    agent_class: str
    status: AgentStatus = AgentStatus.CREATED
    instance: Any = None
    created_at: float = field(default_factory=time.time)
    last_used_at: float = 0.0
    total_invocations: int = 0
    total_errors: int = 0
    tags: List[str] = field(default_factory=list)


class AgentRegistry:
    """
    Agent 注册表 (全局单例)

    职责:
    - 注册: 注册 Agent 类，延迟实例化
    - 发现: 按名称/标签查找 Agent
    - 生命周期: 创建、获取、销毁 Agent 实例
    - 热替换: 替换 Agent 实例（如切换 LLM 后重建）
    - 监控: Agent 调用次数、错误率、最后使用时间
    """

    def __init__(self):
        self._registry: Dict[str, AgentDescriptor] = {}
        self._instances: Dict[str, Any] = {}
        self._lock = threading.Lock()
        self._llm = None

    def set_llm(self, llm):
        """设置全局 LLM（用于 Agent 实例化）"""
        self._llm = llm

    def register(self, name: str, agent_class_path: str,
                 tags: List[str] = None, lazy: bool = True) -> bool:
        """
        注册 Agent 类
        :param name: Agent 唯一名称 (如 'collector')
        :param agent_class_path: 类路径 (如 'workflow.agents.collector_agent.CollectorAgent')
        :param tags: 标签 (如 ['data', 'github'])
        :param lazy: 是否延迟实例化
        """
        with self._lock:
            if name in self._registry:
                logger.warning(f"Agent [{name}] 已注册, 跳过")
                return False

            desc = AgentDescriptor(
                name=name,
                agent_class=agent_class_path,
                tags=tags or [],
            )
            self._registry[name] = desc

        logger.info(f"Agent [{name}] 已注册 (class={agent_class_path}, tags={tags})")

        if not lazy:
            self.get(name)

        return True

    def register_defaults(self):
        """注册所有内置 Agent"""
        defaults = [
            ("planner", "workflow.agents.planner_agent.PlannerAgent", ["planning"]),
            ("collector", "workflow.agents.collector_agent.CollectorAgent", ["data", "github"]),
            ("analyst", "workflow.agents.analyst_agent.AnalystAgent", ["analysis", "cicd"]),
            ("validator", "workflow.agents.validator_agent.ValidatorAgent", ["validation", "quality"]),
            ("reporter", "workflow.agents.reporter_agent.ReporterAgent", ["report", "format"]),
            ("orchestrator", "workflow.agents.orchestrator_agent.OrchestratorAgent", ["orchestration"]),
        ]
        for name, path, tags in defaults:
            self.register(name, path, tags)
        logger.info(f"已注册 {len(defaults)} 个内置 Agent")

    def get(self, name: str) -> Optional[Any]:
        """
        获取 Agent 实例（延迟实例化）
        如果实例不存在，自动创建
        """
        with self._lock:
            desc = self._registry.get(name)
            if not desc:
                return None

            # 已有实例且未被销毁
            if name in self._instances and desc.status != AgentStatus.DESTROYED:
                desc.last_used_at = time.time()
                return self._instances[name]

        # 需要创建实例（锁外执行避免死锁）
        instance = self._create_instance(desc)
        if instance:
            with self._lock:
                self._instances[name] = instance
                desc.instance = instance
                desc.status = AgentStatus.IDLE
                desc.last_used_at = time.time()

        return instance

    def _create_instance(self, desc: AgentDescriptor) -> Optional[Any]:
        """动态创建 Agent 实例"""
        try:
            parts = desc.agent_class.rsplit(".", 1)
            module_path = parts[0]
            class_name = parts[1]

            import importlib
            module = importlib.import_module(module_path)
            agent_class = getattr(module, class_name)

            instance = agent_class(llm=self._llm)
            logger.info(f"Agent [{desc.name}] 实例化成功")
            return instance
        except Exception as e:
            logger.error(f"Agent [{desc.name}] 实例化失败: {e}")
            desc.status = AgentStatus.ERROR
            return None

    def destroy(self, name: str) -> bool:
        """销毁 Agent 实例"""
        with self._lock:
            desc = self._registry.get(name)
            if not desc:
                return False

            self._instances.pop(name, None)
            desc.instance = None
            desc.status = AgentStatus.DESTROYED

        logger.info(f"Agent [{name}] 已销毁")
        return True

    def hot_replace(self, name: str) -> Optional[Any]:
        """
        热替换 Agent 实例
        销毁旧实例，创建新实例（用于切换 LLM 后重建）
        """
        self.destroy(name)
        return self.get(name)

    def hot_replace_all(self):
        """热替换所有 Agent"""
        with self._lock:
            names = list(self._registry.keys())

        for name in names:
            self.hot_replace(name)

        logger.info(f"已热替换 {len(names)} 个 Agent")

    def record_invocation(self, name: str, success: bool = True):
        """记录 Agent 调用"""
        with self._lock:
            desc = self._registry.get(name)
            if desc:
                desc.total_invocations += 1
                if not success:
                    desc.total_errors += 1
                desc.last_used_at = time.time()
                desc.status = AgentStatus.IDLE if success else AgentStatus.ERROR

    def find_by_tag(self, tag: str) -> List[str]:
        """按标签查找 Agent"""
        with self._lock:
            return [
                name for name, desc in self._registry.items()
                if tag in desc.tags
            ]

    def get_status(self, name: str) -> Optional[Dict[str, Any]]:
        """获取单个 Agent 状态"""
        with self._lock:
            desc = self._registry.get(name)
            if not desc:
                return None

            instance = self._instances.get(name)
            result = {
                "name": name,
                "status": desc.status.value,
                "available": instance is not None and hasattr(instance, 'available') and instance.available,
                "total_invocations": desc.total_invocations,
                "total_errors": desc.total_errors,
                "last_used_at": desc.last_used_at,
                "tags": desc.tags,
            }

            if instance and hasattr(instance, 'tool_names'):
                result["tools"] = instance.tool_names
            if instance and hasattr(instance, 'get_performance_summary'):
                result["performance"] = instance.get_performance_summary()

            return result

    def get_all_status(self) -> Dict[str, Any]:
        """获取所有 Agent 状态"""
        with self._lock:
            names = list(self._registry.keys())

        statuses = {}
        for name in names:
            statuses[name] = self.get_status(name)

        total_invocations = sum(
            s.get("total_invocations", 0) for s in statuses.values() if s
        )
        total_errors = sum(
            s.get("total_errors", 0) for s in statuses.values() if s
        )

        return {
            "agents": statuses,
            "total_registered": len(names),
            "total_invocations": total_invocations,
            "total_errors": total_errors,
            "error_rate": round(total_errors / max(total_invocations, 1) * 100, 2),
        }

    def list_registered(self) -> List[Dict[str, Any]]:
        """列出所有已注册的 Agent"""
        with self._lock:
            return [
                {
                    "name": name,
                    "class": desc.agent_class,
                    "status": desc.status.value,
                    "tags": desc.tags,
                    "instantiated": name in self._instances,
                }
                for name, desc in self._registry.items()
            ]

    def clear(self):
        """清空所有注册和实例"""
        with self._lock:
            self._registry.clear()
            self._instances.clear()


# 全局单例
agent_registry = AgentRegistry()
