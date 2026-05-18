"""
Orchestrator Agent — 总调度 Agent
理解用户意图，将任务分解并分派给 Collector/Analyst/Reporter Agent
"""
import logging
from typing import Dict, Any
from langchain_core.tools import tool
from .base_agent import BaseAgent

logger = logging.getLogger(__name__)

# Agent 实例缓存（延迟初始化）
_agents = {}


def _get_agent(name: str):
    """延迟获取 Agent 实例"""
    if name in _agents:
        return _agents[name]

    from workflow.config import workflow_config
    llm = workflow_config.llm

    if name == "collector":
        from .collector_agent import CollectorAgent
        _agents[name] = CollectorAgent(llm=llm)
    elif name == "analyst":
        from .analyst_agent import AnalystAgent
        _agents[name] = AnalystAgent(llm=llm)
    elif name == "reporter":
        from .reporter_agent import ReporterAgent
        _agents[name] = ReporterAgent(llm=llm)

    return _agents.get(name)


@tool
def delegate_to_collector(task: str) -> str:
    """将数据采集任务委托给 Collector Agent。
    task: 采集任务描述，如 "采集 rust-lang/rust 项目的 PR 数据"
    Collector 会自主决定采集策略（先查缓存，根据项目大小选择全量/抽样）。
    返回采集结果摘要。"""
    agent = _get_agent("collector")
    if not agent or not agent.available:
        return "Collector Agent 不可用（LLM 未初始化）"
    result = agent.run(task)
    return result["output"]


@tool
def delegate_to_analyst(task: str) -> str:
    """将分析任务委托给 Analyst Agent。
    task: 分析任务描述，如 "分析 rust-lang/rust 的 CI/CD 工程效能"
    Analyst 会自主选择分析维度，使用工具获取统计数据并生成深度分析。
    返回分析报告。"""
    agent = _get_agent("analyst")
    if not agent or not agent.available:
        return "Analyst Agent 不可用（LLM 未初始化）"
    result = agent.run(task)
    return result["output"]


@tool
def delegate_to_reporter(task: str) -> str:
    """将报告生成任务委托给 Reporter Agent。
    task: 报告任务描述，如 "为 rust-lang/rust 生成 CI/CD 洞察报告"
    Reporter 会生成统计报告、AI 建议和风险评估，格式化为 Markdown。
    返回完整报告。"""
    agent = _get_agent("reporter")
    if not agent or not agent.available:
        return "Reporter Agent 不可用（LLM 未初始化）"
    result = agent.run(task)
    return result["output"]


ORCHESTRATOR_SYSTEM_PROMPT = """你是 CI/CD 工程能力洞察系统的总调度。你负责理解用户需求，并将任务分解给专业 Agent 执行。

## 你管理的 Agent

### 1. Collector Agent（数据采集）
- 职责: 从 GitHub 获取 PR 数据（PR列表、评论、详情、Reviews）
- 何时调用: 用户需要分析一个项目，且数据库中没有该项目的数据
- 调用方式: delegate_to_collector("采集 {owner}/{repo} 的 PR 数据")

### 2. Analyst Agent（分析）
- 职责: CI/CD 工程效能分析（统计、趋势、失败分析、AI 深度洞察）
- 何时调用: 数据已采集完成后，需要进行分析
- 调用方式: delegate_to_analyst("分析 {owner}/{repo} 的 CI/CD 工程效能")

### 3. Reporter Agent（报告）
- 职责: 生成洞察报告（统计评级、AI 建议、风险评估、Markdown 格式化）
- 何时调用: 分析完成后，需要生成报告
- 调用方式: delegate_to_reporter("为 {owner}/{repo} 生成 CI/CD 洞察报告")

## 调度策略

### 标准流程（用户要求分析一个项目）
1. **Collector** → 采集数据
2. **Analyst** → 分析数据
3. **Reporter** → 生成报告
4. 向用户返回最终报告

### 按需调度
- 用户只要求采集数据 → 只调 Collector
- 用户只要求分析 → 只调 Analyst（前提: 数据已在数据库中）
- 用户只要求报告 → 只调 Reporter（前提: 分析已完成）

### 错误处理
- 如果 Collector 返回失败，告知用户并建议检查仓库地址
- 如果 Analyst 发现没有评论数据，建议先运行 Collector
- 如果任何 Agent 超时或失败，向用户报告具体错误

## 输出
最终向用户输出完整的分析报告，不要输出内部调度细节。"""


class OrchestratorAgent(BaseAgent):
    """总调度 Agent"""

    name = "orchestrator"
    system_prompt = ORCHESTRATOR_SYSTEM_PROMPT

    def _register_tools(self) -> list:
        return [
            delegate_to_collector,
            delegate_to_analyst,
            delegate_to_reporter,
        ]
