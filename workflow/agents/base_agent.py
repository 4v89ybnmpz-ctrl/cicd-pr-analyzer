"""
Agent 基类
封装 LangGraph create_react_agent，统一 Agent 创建和管理模式
支持: 回调事件、执行统计、自动重试、token 追踪、生命周期管理
"""
import logging
import time
import uuid
from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum

from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, SystemMessage

logger = logging.getLogger(__name__)


class AgentEventType(str, Enum):
    """Agent 事件类型"""
    STARTED = "started"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRY = "retry"
    DELEGATE = "delegate"


@dataclass
class AgentEvent:
    """Agent 执行事件"""
    event_type: AgentEventType
    agent_name: str
    timestamp: float = field(default_factory=time.time)
    data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionStats:
    """单次执行统计"""
    agent_name: str
    start_time: float = 0.0
    end_time: float = 0.0
    duration_seconds: float = 0.0
    tool_calls: int = 0
    tool_names: List[str] = field(default_factory=list)
    retry_count: int = 0
    success: bool = False
    error: Optional[str] = None
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass
class AgentRunResult:
    """Agent 运行结果（增强版）"""
    output: str
    messages: List[Dict[str, str]]
    tool_calls: int
    stats: ExecutionStats
    events: List[AgentEvent] = field(default_factory=list)
    error: Optional[str] = None
    run_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])


# 回调类型
AgentCallback = Callable[[AgentEvent], None]


class BaseAgent:
    """
    Agent 基类
    所有 Agent（Collector/Analyst/Reporter/Orchestrator/Planner/Validator）继承此类

    子类需要实现:
    - name: Agent 名称
    - system_prompt: 系统提示词
    - _register_tools(): 注册工具列表

    增强功能:
    - 回调事件系统: on_event 注册回调，监听 Agent 生命周期事件
    - 执行统计: 每次运行记录耗时、工具调用、token 消耗
    - 自动重试: 可配置最大重试次数
    - token 追踪: 从 LLM 响应中提取 token 用量
    """

    name: str = "base"
    system_prompt: str = ""
    max_retries: int = 2
    retry_delay: float = 1.0

    def __init__(self, llm=None, callbacks: List[AgentCallback] = None):
        """
        :param llm: LangChain LLM 实例
        :param callbacks: 事件回调列表
        """
        self.llm = llm
        self._tools = self._register_tools()
        self._agent = None
        self._callbacks: List[AgentCallback] = callbacks or []
        self._execution_history: List[ExecutionStats] = []
        self._total_runs = 0
        self._total_errors = 0

        if self.llm and self._tools:
            self._build_agent()
        else:
            logger.warning(f"Agent [{self.name}] LLM 或工具不可用, Agent 未创建")

    def _build_agent(self):
        """构建 LangGraph react agent"""
        try:
            from langgraph.prebuilt import create_react_agent
            self._agent = create_react_agent(
                model=self.llm,
                tools=self._tools,
                prompt=self.system_prompt,
            )
            logger.info(f"Agent [{self.name}] 创建成功, 工具: {[t.name for t in self._tools]}")
        except Exception as e:
            logger.error(f"Agent [{self.name}] 创建失败: {e}")
            self._agent = None

    def _register_tools(self) -> list:
        """子类重写此方法，返回工具列表"""
        return []

    def on_event(self, callback: AgentCallback):
        """注册事件回调"""
        self._callbacks.append(callback)
        return self

    def _emit_event(self, event_type: AgentEventType, data: Dict[str, Any] = None):
        """触发事件"""
        event = AgentEvent(
            event_type=event_type,
            agent_name=self.name,
            data=data or {},
        )
        for cb in self._callbacks:
            try:
                cb(event)
            except Exception as e:
                logger.warning(f"Agent [{self.name}] 回调执行失败: {e}")

    def _extract_token_usage(self, messages: list) -> Dict[str, int]:
        """从 LLM 响应中提取 token 使用量"""
        input_tokens = 0
        output_tokens = 0
        for m in messages:
            usage = getattr(m, 'usage_metadata', None)
            if usage:
                input_tokens += usage.get('input_tokens', 0)
                output_tokens += usage.get('output_tokens', 0)
        return {"input_tokens": input_tokens, "output_tokens": output_tokens}

    def run(self, message: str) -> Dict[str, Any]:
        """
        运行 Agent（带自动重试）
        :param message: 用户消息
        :return: AgentRunResult 的字典形式
        """
        stats = ExecutionStats(agent_name=self.name)
        events: List[AgentEvent] = []
        stats.start_time = time.time()

        if not self._agent:
            stats.end_time = time.time()
            stats.duration_seconds = stats.end_time - stats.start_time
            stats.error = "LLM 未初始化"
            self._total_errors += 1
            self._emit_event(AgentEventType.FAILED, {"error": stats.error})
            return AgentRunResult(
                output=f"Agent [{self.name}] 不可用（LLM 未初始化）",
                messages=[], tool_calls=0, stats=stats,
                events=events, error=stats.error,
            ).__dict__

        self._emit_event(AgentEventType.STARTED, {"message": message[:200]})
        self._total_runs += 1

        last_error = None
        for attempt in range(self.max_retries + 1):
            try:
                result = self._agent.invoke(
                    {"messages": [HumanMessage(content=message)]}
                )

                messages = result.get("messages", [])
                output = messages[-1].content if messages else ""

                # 统计工具调用
                tool_calls = 0
                tool_names = []
                for m in messages:
                    if hasattr(m, 'type') and m.type == 'tool':
                        tool_calls += 1
                        tool_names.append(getattr(m, 'name', 'unknown'))

                # token 使用统计
                token_usage = self._extract_token_usage(messages)

                stats.end_time = time.time()
                stats.duration_seconds = stats.end_time - stats.start_time
                stats.tool_calls = tool_calls
                stats.tool_names = tool_names
                stats.success = True
                stats.input_tokens = token_usage["input_tokens"]
                stats.output_tokens = token_usage["output_tokens"]

                self._execution_history.append(stats)
                self._emit_event(AgentEventType.COMPLETED, {
                    "tool_calls": tool_calls,
                    "duration": stats.duration_seconds,
                    "tokens": token_usage,
                })

                logger.info(
                    f"Agent [{self.name}] 完成, "
                    f"{tool_calls} 次工具调用, "
                    f"耗时 {stats.duration_seconds:.2f}s, "
                    f"输出 {len(output)} 字"
                )

                return AgentRunResult(
                    output=output,
                    messages=[{"role": m.type, "content": m.content} for m in messages],
                    tool_calls=tool_calls,
                    stats=stats,
                    events=events,
                ).__dict__

            except Exception as e:
                last_error = str(e)
                stats.retry_count = attempt + 1

                if attempt < self.max_retries:
                    self._emit_event(AgentEventType.RETRY, {
                        "attempt": attempt + 1,
                        "max_retries": self.max_retries,
                        "error": last_error,
                    })
                    logger.warning(
                        f"Agent [{self.name}] 第 {attempt + 1} 次重试: {e}"
                    )
                    time.sleep(self.retry_delay * (attempt + 1))
                else:
                    logger.error(f"Agent [{self.name}] 执行失败（已重试 {self.max_retries} 次）: {e}")

        # 所有重试都失败
        stats.end_time = time.time()
        stats.duration_seconds = stats.end_time - stats.start_time
        stats.success = False
        stats.error = last_error
        self._total_errors += 1
        self._execution_history.append(stats)

        self._emit_event(AgentEventType.FAILED, {"error": last_error})

        return AgentRunResult(
            output=f"执行失败: {last_error}",
            messages=[], tool_calls=0, stats=stats,
            events=events, error=last_error,
        ).__dict__

    def run_with_context(self, message: str, context: List[Dict[str, str]]) -> Dict[str, Any]:
        """
        带上下文运行 Agent（用于 Agent 间通信）
        :param message: 当前消息
        :param context: 之前的对话历史 [{"role": "user", "content": "..."}, ...]
        """
        if not self._agent:
            return {
                "output": f"Agent [{self.name}] 不可用",
                "messages": [], "tool_calls": 0,
                "stats": ExecutionStats(agent_name=self.name).__dict__,
                "error": "LLM 未初始化",
            }

        stats = ExecutionStats(agent_name=self.name)
        stats.start_time = time.time()
        self._emit_event(AgentEventType.STARTED, {"message": message[:200], "context_length": len(context)})

        try:
            from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

            # 重建消息历史
            history = []
            for msg in context:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if role == "user":
                    history.append(HumanMessage(content=content))
                elif role in ("assistant", "ai"):
                    history.append(AIMessage(content=content))
                elif role == "system":
                    history.append(SystemMessage(content=content))

            history.append(HumanMessage(content=message))

            result = self._agent.invoke({"messages": history})

            messages = result.get("messages", [])
            output = messages[-1].content if messages else ""
            tool_calls = sum(
                1 for m in messages
                if hasattr(m, 'type') and m.type == 'tool'
            )
            token_usage = self._extract_token_usage(messages)

            stats.end_time = time.time()
            stats.duration_seconds = stats.end_time - stats.start_time
            stats.tool_calls = tool_calls
            stats.success = True
            stats.input_tokens = token_usage["input_tokens"]
            stats.output_tokens = token_usage["output_tokens"]
            self._execution_history.append(stats)

            self._emit_event(AgentEventType.COMPLETED, {
                "tool_calls": tool_calls,
                "duration": stats.duration_seconds,
            })

            return {
                "output": output,
                "messages": [{"role": m.type, "content": m.content} for m in messages],
                "tool_calls": tool_calls,
                "stats": stats.__dict__,
            }
        except Exception as e:
            stats.end_time = time.time()
            stats.duration_seconds = stats.end_time - stats.start_time
            stats.error = str(e)
            stats.success = False
            self._total_errors += 1

            logger.error(f"Agent [{self.name}] 执行失败: {e}")
            return {
                "output": f"执行失败: {e}",
                "messages": [], "tool_calls": 0,
                "stats": stats.__dict__,
                "error": str(e),
            }

    @property
    def available(self) -> bool:
        """Agent 是否可用"""
        return self._agent is not None

    @property
    def tool_names(self) -> List[str]:
        """返回工具名称列表"""
        return [t.name for t in self._tools]

    @property
    def execution_history(self) -> List[ExecutionStats]:
        """获取执行历史"""
        return self._execution_history

    def get_performance_summary(self) -> Dict[str, Any]:
        """获取 Agent 性能摘要"""
        if not self._execution_history:
            return {
                "agent_name": self.name,
                "total_runs": 0,
                "total_errors": self._total_errors,
            }

        successful = [s for s in self._execution_history if s.success]
        durations = [s.duration_seconds for s in successful]
        tool_calls = [s.tool_calls for s in successful]

        return {
            "agent_name": self.name,
            "total_runs": self._total_runs,
            "successful_runs": len(successful),
            "total_errors": self._total_errors,
            "avg_duration": sum(durations) / len(durations) if durations else 0,
            "max_duration": max(durations) if durations else 0,
            "avg_tool_calls": sum(tool_calls) / len(tool_calls) if tool_calls else 0,
            "total_tokens": sum(s.total_tokens for s in self._execution_history),
        }
