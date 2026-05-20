"""
Agent 基类 v3
重构重点:
1. run/run_with_context 公共逻辑提取到 _invoke_core
2. 修复 create_react_agent deprecation → 使用 try/except 兼容新旧 import
3. Prompt 模板化: render_prompt() 支持 {owner}/{repo} 等变量
4. Agent 能力自省: capabilities 属性 + describe() 方法
"""
import logging
import time
import uuid
from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum

from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

logger = logging.getLogger(__name__)


class AgentEventType(str, Enum):
    STARTED = "started"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRY = "retry"
    DELEGATE = "delegate"


@dataclass
class AgentEvent:
    event_type: AgentEventType
    agent_name: str
    timestamp: float = field(default_factory=time.time)
    data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionStats:
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
    output: str
    messages: List[Dict[str, str]]
    tool_calls: int
    stats: ExecutionStats
    events: List[AgentEvent] = field(default_factory=list)
    error: Optional[str] = None
    run_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])


AgentCallback = Callable[[AgentEvent], None]


def _create_react_agent(model, tools, prompt: str):
    """
    兼容新旧版 LangGraph 的 create_react_agent
    V1.0 标记 create_react_agent 从 langgraph.prebuilt 移到 langchain.agents
    V2.0 将完全移除旧路径
    """
    try:
        from langgraph.prebuilt import create_react_agent
        return create_react_agent(model=model, tools=tools, prompt=prompt)
    except (ImportError, TypeError):
        pass

    try:
        from langchain.agents import create_agent
        return create_agent(model=model, tools=tools, prompt=prompt)
    except ImportError:
        pass

    # 最终 fallback: 手动构建简单的 tool-calling agent
    raise ImportError("无法创建 react agent: 需要 langgraph>=0.2 或 langchain>=0.3")


class PromptTemplate:
    """
    简单 prompt 模板
    支持 {variable} 占位符
    """
    def __init__(self, template: str):
        self._template = template

    def render(self, **kwargs) -> str:
        try:
            return self._template.format(**kwargs)
        except KeyError:
            # 未提供的变量保留原样
            return self._template


class BaseAgent:
    """
    Agent 基类 v3

    子类需要实现:
    - name: str
    - system_prompt: str (支持 {owner}/{repo} 等占位符)
    - _register_tools() -> list
    可选重写:
    - description: str — Agent 功能描述（用于能力自省）
    - capabilities: list[str] — 能力列表
    """

    name: str = "base"
    system_prompt: str = ""
    description: str = ""
    capabilities: List[str] = []
    max_retries: int = 2
    retry_delay: float = 1.0

    def __init__(self, llm=None, callbacks: List[AgentCallback] = None):
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
        try:
            self._agent = _create_react_agent(
                model=self.llm,
                tools=self._tools,
                prompt=self.system_prompt,
            )
            logger.info(f"Agent [{self.name}] 创建成功, 工具: {[t.name for t in self._tools]}")
        except Exception as e:
            logger.error(f"Agent [{self.name}] 创建失败: {e}")
            self._agent = None

    def _register_tools(self) -> list:
        return []

    # ====================
    # 事件系统
    # ====================

    def on_event(self, callback: AgentCallback):
        self._callbacks.append(callback)
        return self

    def _emit_event(self, event_type: AgentEventType, data: Dict[str, Any] = None):
        event = AgentEvent(event_type=event_type, agent_name=self.name, data=data or {})
        for cb in self._callbacks:
            try:
                cb(event)
            except Exception as e:
                logger.warning(f"Agent [{self.name}] 回调失败: {e}")

    # ====================
    # Prompt 模板
    # ====================

    def render_prompt(self, **kwargs) -> str:
        """渲染系统 prompt 模板"""
        return PromptTemplate(self.system_prompt).render(**kwargs)

    # ====================
    # 能力自省
    # ====================

    def describe(self) -> Dict[str, Any]:
        """Agent 自我描述（用于 Agent 间能力发现）"""
        return {
            "name": self.name,
            "description": self.description or f"{self.name} agent",
            "capabilities": self.capabilities,
            "tools": self.tool_names,
            "available": self.available,
        }

    # ====================
    # 核心执行（公共逻辑）
    # ====================

    def _extract_token_usage(self, messages: list) -> Dict[str, int]:
        input_tokens = 0
        output_tokens = 0
        for m in messages:
            usage = getattr(m, 'usage_metadata', None)
            if usage:
                input_tokens += usage.get('input_tokens', 0)
                output_tokens += usage.get('output_tokens', 0)
        return {"input_tokens": input_tokens, "output_tokens": output_tokens}

    def _parse_result(self, raw_result: Dict) -> Dict[str, Any]:
        """解析 Agent 原始返回，提取 output/tool_calls/tokens"""
        messages = raw_result.get("messages", [])
        output = messages[-1].content if messages else ""

        tool_calls = 0
        tool_names = []
        for m in messages:
            if hasattr(m, 'type') and m.type == 'tool':
                tool_calls += 1
                tool_names.append(getattr(m, 'name', 'unknown'))

        token_usage = self._extract_token_usage(messages)

        return {
            "output": output,
            "messages": [{"role": m.type, "content": m.content} for m in messages],
            "tool_calls": tool_calls,
            "tool_names": tool_names,
            "input_tokens": token_usage["input_tokens"],
            "output_tokens": token_usage["output_tokens"],
        }

    def _build_messages(self, message: str, context: List[Dict[str, str]] = None) -> list:
        """构建消息列表（支持可选上下文）"""
        msgs = []
        if context:
            for msg in context:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if role == "user":
                    msgs.append(HumanMessage(content=content))
                elif role in ("assistant", "ai"):
                    msgs.append(AIMessage(content=content))
                elif role == "system":
                    msgs.append(SystemMessage(content=content))
        msgs.append(HumanMessage(content=message))
        return msgs

    def _invoke_core(self, message: str, context: List[Dict[str, str]] = None) -> Dict[str, Any]:
        """
        核心调用逻辑（run 和 run_with_context 共用）
        返回 AgentRunResult dict
        """
        stats = ExecutionStats(agent_name=self.name)
        stats.start_time = time.time()
        self._emit_event(AgentEventType.STARTED, {
            "message": message[:200],
            "has_context": context is not None and len(context) > 0,
        })

        if not self._agent:
            stats.end_time = time.time()
            stats.duration_seconds = stats.end_time - stats.start_time
            stats.error = "LLM 未初始化"
            self._total_errors += 1
            self._emit_event(AgentEventType.FAILED, {"error": stats.error})
            return AgentRunResult(
                output=f"Agent [{self.name}] 不可用（LLM 未初始化）",
                messages=[], tool_calls=0, stats=stats, error=stats.error,
            ).__dict__

        self._total_runs += 1
        last_error = None

        for attempt in range(self.max_retries + 1):
            try:
                msgs = self._build_messages(message, context)
                raw = self._agent.invoke({"messages": msgs})
                parsed = self._parse_result(raw)

                stats.end_time = time.time()
                stats.duration_seconds = stats.end_time - stats.start_time
                stats.tool_calls = parsed["tool_calls"]
                stats.tool_names = parsed["tool_names"]
                stats.success = True
                stats.input_tokens = parsed["input_tokens"]
                stats.output_tokens = parsed["output_tokens"]

                self._execution_history.append(stats)
                self._emit_event(AgentEventType.COMPLETED, {
                    "tool_calls": stats.tool_calls,
                    "duration": stats.duration_seconds,
                    "tokens": {"input": stats.input_tokens, "output": stats.output_tokens},
                })

                logger.info(
                    f"Agent [{self.name}] 完成, {stats.tool_calls} 工具调用, "
                    f"{stats.duration_seconds:.2f}s, {len(parsed['output'])} 字"
                )

                return AgentRunResult(
                    output=parsed["output"],
                    messages=parsed["messages"],
                    tool_calls=parsed["tool_calls"],
                    stats=stats,
                ).__dict__

            except Exception as e:
                last_error = str(e)
                stats.retry_count = attempt + 1
                if attempt < self.max_retries:
                    self._emit_event(AgentEventType.RETRY, {
                        "attempt": attempt + 1, "error": last_error,
                    })
                    logger.warning(f"Agent [{self.name}] 重试 {attempt + 1}: {e}")
                    time.sleep(self.retry_delay * (attempt + 1))
                else:
                    logger.error(f"Agent [{self.name}] 失败（重试 {self.max_retries} 次）: {e}")

        stats.end_time = time.time()
        stats.duration_seconds = stats.end_time - stats.start_time
        stats.success = False
        stats.error = last_error
        self._total_errors += 1
        self._execution_history.append(stats)
        self._emit_event(AgentEventType.FAILED, {"error": last_error})

        return AgentRunResult(
            output=f"执行失败: {last_error}",
            messages=[], tool_calls=0, stats=stats, error=last_error,
        ).__dict__

    # ====================
    # 公共 API
    # ====================

    def run(self, message: str) -> Dict[str, Any]:
        """运行 Agent（带重试）"""
        return self._invoke_core(message, context=None)

    def run_with_context(self, message: str, context: List[Dict[str, str]]) -> Dict[str, Any]:
        """带上下文运行（用于多轮对话）"""
        return self._invoke_core(message, context=context)

    def run_with_prompt_vars(self, message: str, **prompt_vars) -> Dict[str, Any]:
        """运行 Agent 并动态渲染 prompt（注入 owner/repo 等变量）"""
        rendered = self.render_prompt(**prompt_vars)
        original_prompt = self.system_prompt
        self.system_prompt = rendered
        if self._agent:
            self._build_agent()
        result = self._invoke_core(message, context=None)
        self.system_prompt = original_prompt
        if self._agent:
            self._build_agent()
        return result

    @property
    def available(self) -> bool:
        return self._agent is not None

    @property
    def tool_names(self) -> List[str]:
        return [t.name for t in self._tools]

    @property
    def execution_history(self) -> List[ExecutionStats]:
        return self._execution_history

    def get_performance_summary(self) -> Dict[str, Any]:
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
