"""
Orchestrator Agent — 总调度 Agent
通过 agent_registry 统一管理 Agent 实例
delegate 工具通过通用 _delegate 函数消除重复代码
"""
import json
import logging
from typing import Dict, Any
from langchain_core.tools import tool
from .base_agent import BaseAgent

logger = logging.getLogger(__name__)


def _get_agent(name: str):
    """通过 agent_registry 获取 Agent 实例"""
    from .registry import agent_registry
    registered = [d["name"] for d in agent_registry.list_registered()]
    if name not in registered:
        agent_registry.register_defaults()
    return agent_registry.get(name)


def _delegate(agent_name: str, task: str) -> str:
    """通用委托函数 — 所有 delegate_* 工具的统一实现"""
    agent = _get_agent(agent_name)
    if not agent or not agent.available:
        return json.dumps({
            "error": f"{agent_name} Agent 不可用",
            "agent": agent_name,
            "available": False,
        }, ensure_ascii=False)
    result = agent.run(task)
    return result["output"]


@tool
def delegate_to_planner(task: str) -> str:
    """将任务规划委托给 Planner Agent。Planner 分析项目画像并生成 DAG 执行计划。"""
    return _delegate("planner", task)


@tool
def delegate_to_collector(task: str) -> str:
    """将数据采集委托给 Collector Agent。Collector 自主决定采集策略。"""
    return _delegate("collector", task)


@tool
def delegate_to_analyst(task: str) -> str:
    """将分析任务委托给 Analyst Agent。Analyst 自主选择分析维度。"""
    return _delegate("analyst", task)


@tool
def delegate_to_validator(task: str) -> str:
    """将数据验证委托给 Validator Agent。Validator 检查数据完整性。"""
    return _delegate("validator", task)


@tool
def delegate_to_reporter(task: str) -> str:
    """将报告生成委托给 Reporter Agent。Reporter 生成统计报告和 AI 建议。"""
    return _delegate("reporter", task)


@tool
def get_blackboard_summary() -> str:
    """获取共享黑板的当前状态。"""
    from .blackboard import blackboard
    return json.dumps(blackboard.summary(), ensure_ascii=False)


@tool
def check_agent_status() -> str:
    """检查所有 Agent 的可用状态和性能指标。"""
    statuses = {}
    for name in ["planner", "collector", "analyst", "validator", "reporter"]:
        agent = _get_agent(name)
        if agent:
            statuses[name] = {
                "available": agent.available,
                "tools": agent.tool_names,
                "capabilities": agent.capabilities,
                "performance": agent.get_performance_summary(),
            }
        else:
            statuses[name] = {"available": False}

    return json.dumps(statuses, ensure_ascii=False)


ORCHESTRATOR_SYSTEM_PROMPT = """你是 CI/CD 工程能力洞察系统的总调度。你负责理解用户需求，制定执行计划，并将任务分解给专业 Agent 执行。

## 你管理的 Agent

### 0. Planner Agent（规划）
- 职责: 分析项目画像，制定执行计划（DAG）
- 何时调用: 复杂任务或用户没有明确指定分析目标时
- 调用: delegate_to_planner("为 {owner}/{repo} 制定分析计划")

### 1. Collector Agent（数据采集）
- 职责: 从 GitHub 获取 PR 数据
- 何时调用: 数据库中没有该项目的数据
- 调用: delegate_to_collector("采集 {owner}/{repo} 的 PR 数据")

### 2. Analyst Agent（分析）
- 职责: CI/CD 工程效能分析
- 何时调用: 数据已采集完成后
- 调用: delegate_to_analyst("分析 {owner}/{repo} 的 CI/CD 工程效能")

### 3. Validator Agent（验证）
- 职责: 数据质量验证
- 何时调用: 分析完成后，报告生成前
- 调用: delegate_to_validator("验证 {owner}/{repo} 的数据质量")

### 4. Reporter Agent（报告）
- 职责: 生成洞察报告
- 何时调用: 验证通过后
- 调用: delegate_to_reporter("为 {owner}/{repo} 生成 CI/CD 洞察报告")

## 重要: 执行顺序
必须按此顺序调用 Agent，不可跳步:
1. Collector（采集）→ 2. Analyst（分析）→ 3. Validator（验证）→ 4. Reporter（报告）
Planner 可以在最前面用于规划，但不替代上述顺序。

## 动态策略
- Validator 发现数据不足 → 请求 Collector 补充数据，然后重新走 Analyst → Validator
- Analyst 发现缺少评论 → 请求 Collector 补充采集
- Reporter 发现分析不够 → 请求 Analyst 补充分析

## 输出
最终向用户输出完整的分析报告，不要输出内部调度细节。"""


class OrchestratorAgent(BaseAgent):
    """总调度 Agent"""

    name = "orchestrator"
    system_prompt = ORCHESTRATOR_SYSTEM_PROMPT
    description = "总调度 Agent，理解用户需求并协调各专业 Agent 执行"
    capabilities = [
        "task_decomposition",      # 任务分解
        "agent_orchestration",     # Agent 调度
        "dynamic_retry",           # 动态重试
        "blackboard_management",   # 黑板管理
    ]

    def _register_tools(self) -> list:
        return [
            delegate_to_planner,
            delegate_to_collector,
            delegate_to_analyst,
            delegate_to_validator,
            delegate_to_reporter,
            get_blackboard_summary,
            check_agent_status,
        ]
