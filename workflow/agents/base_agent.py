"""
Agent 基类
封装 LangGraph create_react_agent，统一 Agent 创建和管理模式
"""
import logging
from typing import List, Dict, Any, Optional

from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.prebuilt import create_react_agent

logger = logging.getLogger(__name__)


class BaseAgent:
    """
    Agent 基类
    所有 Agent（Collector/Analyst/Reporter/Orchestrator）继承此类

    子类需要实现:
    - name: Agent 名称
    - system_prompt: 系统提示词
    - _register_tools(): 注册工具列表
    """

    name: str = "base"
    system_prompt: str = ""

    def __init__(self, llm=None):
        """
        :param llm: LangChain LLM 实例 (ChatAnthropic 等)
        """
        self.llm = llm
        self._tools = self._register_tools()
        self._agent = None

        if self.llm and self._tools:
            self._agent = create_react_agent(
                model=self.llm,
                tools=self._tools,
                prompt=self.system_prompt,
            )
            logger.info(f"Agent [{self.name}] 创建成功, 工具: {[t.name for t in self._tools]}")
        else:
            logger.warning(f"Agent [{self.name}] LLM 或工具不可用, Agent 未创建")

    def _register_tools(self) -> list:
        """子类重写此方法，返回工具列表"""
        return []

    def run(self, message: str) -> Dict[str, Any]:
        """
        运行 Agent
        :param message: 用户消息
        :return: {"output": str, "messages": list, "tool_calls": int}
        """
        if not self._agent:
            return {
                "output": f"Agent [{self.name}] 不可用（LLM 未初始化）",
                "messages": [],
                "tool_calls": 0,
            }

        try:
            result = self._agent.invoke(
                {"messages": [HumanMessage(content=message)]}
            )

            messages = result.get("messages", [])
            output = messages[-1].content if messages else ""
            tool_calls = sum(
                1 for m in messages
                if hasattr(m, 'type') and m.type == 'tool'
            )

            logger.info(f"Agent [{self.name}] 完成, {tool_calls} 次工具调用, 输出 {len(output)} 字")

            return {
                "output": output,
                "messages": [{"role": m.type, "content": m.content} for m in messages],
                "tool_calls": tool_calls,
            }
        except Exception as e:
            logger.error(f"Agent [{self.name}] 执行失败: {e}")
            return {
                "output": f"执行失败: {e}",
                "messages": [],
                "tool_calls": 0,
                "error": str(e),
            }

    def run_with_context(self, message: str, context: List[Dict[str, str]]) -> Dict[str, Any]:
        """
        带上下文运行 Agent（用于 Agent 间通信）
        :param message: 当前消息
        :param context: 之前的对话历史 [{"role": "user", "content": "..."}, ...]
        """
        if not self._agent:
            return {
                "output": f"Agent [{self.name}] 不可用",
                "messages": [],
                "tool_calls": 0,
            }

        try:
            from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage

            # 重建消息历史
            history = []
            for msg in context:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if role == "user":
                    history.append(HumanMessage(content=content))
                elif role == "assistant" or role == "ai":
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

            return {
                "output": output,
                "messages": [{"role": m.type, "content": m.content} for m in messages],
                "tool_calls": tool_calls,
            }
        except Exception as e:
            logger.error(f"Agent [{self.name}] 执行失败: {e}")
            return {
                "output": f"执行失败: {e}",
                "messages": [],
                "tool_calls": 0,
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
