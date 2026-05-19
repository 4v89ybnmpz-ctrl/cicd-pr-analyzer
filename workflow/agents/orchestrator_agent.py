"""
Orchestrator Agent — 总调度 Agent
通过 agent_registry 统一管理 Agent 实例（不再使用 _agents 字典）
"""
import json
import logging
from typing import Dict, Any, List, Optional
from enum import Enum
from langchain_core.tools import tool
from .base_agent import BaseAgent, AgentEventType
from .blackboard import blackboard, DataType

logger = logging.getLogger(__name__)


def _get_agent(name: str):
    """通过 agent_registry 获取 Agent 实例（统一入口）"""
    from .registry import agent_registry
    registered = [d["name"] for d in agent_registry.list_registered()]
    if name not in registered:
        agent_registry.register_defaults()
    return agent_registry.get(name)


@tool
def delegate_to_planner(task: str) -> str:
    """将任务规划委托给 Planner Agent。
    task: 规划任务描述，如 "为 rust-lang/rust 制定分析计划"
    Planner 会分析项目画像并生成 DAG 执行计划。
    返回执行计划 JSON。"""
    agent = _get_agent("planner")
    if not agent or not agent.available:
        return json.dumps({"error": "Planner Agent 不可用"}, ensure_ascii=False)
    result = agent.run(task)
    return result["output"]


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
def delegate_to_validator(task: str) -> str:
    """将数据验证委托给 Validator Agent。
    task: 验证任务描述，如 "验证 rust-lang/rust 的数据质量"
    Validator 会检查数据完整性、分析可信度。
    返回验证报告。"""
    agent = _get_agent("validator")
    if not agent or not agent.available:
        return "Validator Agent 不可用（LLM 未初始化）"
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


@tool
def get_blackboard_summary() -> str:
    """获取共享黑板的当前状态，查看各 Agent 写入的中间结果。"""
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
                "performance": agent.get_performance_summary(),
            }
        else:
            statuses[name] = {"available": False, "error": "未初始化"}

    return json.dumps(statuses, ensure_ascii=False)


ORCHESTRATOR_SYSTEM_PROMPT = """你是 CI/CD 工程能力洞察系统的总调度。你负责理解用户需求，制定执行计划，并将任务分解给专业 Agent 执行。

## 你管理的 Agent

### 0. Planner Agent（规划）
- 职责: 分析项目画像，制定执行计划（DAG）
- 何时调用: 复杂任务或用户没有明确指定分析目标时
- 调用方式: delegate_to_planner("为 {owner}/{repo} 制定分析计划")

### 1. Collector Agent（数据采集）
- 职责: 从 GitHub 获取 PR 数据（PR列表、评论、详情、Reviews）
- 何时调用: 数据库中没有该项目的数据
- 调用方式: delegate_to_collector("采集 {owner}/{repo} 的 PR 数据")

### 2. Analyst Agent（分析）
- 职责: CI/CD 工程效能分析（统计、趋势、失败分析、AI 深度洞察）
- 何时调用: 数据已采集完成后
- 调用方式: delegate_to_analyst("分析 {owner}/{repo} 的 CI/CD 工程效能")

### 3. Validator Agent（验证）
- 职责: 数据质量验证（完整性、一致性、可信度）
- 何时调用: 分析完成后，报告生成前
- 调用方式: delegate_to_validator("验证 {owner}/{repo} 的数据质量")

### 4. Reporter Agent（报告）
- 职责: 生成洞察报告（统计评级、AI 建议、风险评估、Markdown 格式化）
- 何时调用: 验证通过后
- 调用方式: delegate_to_reporter("为 {owner}/{repo} 生成 CI/CD 洞察报告")

## 辅助工具
- get_blackboard_summary: 查看 Agent 间共享的中间结果
- check_agent_status: 检查所有 Agent 可用状态

## 调度策略

### 完整流程（推荐）
1. **Planner** → 分析项目画像，生成执行计划
2. **Collector** → 按计划采集数据
3. **Analyst** → 分析数据
4. **Validator** → 验证数据质量和分析结果
5. **Reporter** → 生成报告
6. 向用户返回最终报告

### 快速流程（数据已缓存）
1. **Analyst** → 直接分析已有数据
2. **Reporter** → 生成报告

### 按需调度
- 用户只要求采集数据 → 只调 Collector
- 用户只要求分析 → 只调 Analyst
- 用户只要求报告 → 只调 Reporter
- 用户要求对比分析 → 调用多次 Analyst，然后 Reporter 汇总

### 动态策略
- 如果 Validator 发现数据不足 → 请求 Collector 补充数据
- 如果 Analyst 发现缺少评论 → 请求 Collector 补充采集
- 如果 Reporter 发现分析维度不够 → 请求 Analyst 补充分析

### 错误处理
- Agent 不可用时使用 get_blackboard_summary 和 check_agent_status 诊断
- Collector 失败 → 告知用户检查仓库地址
- Analyst 无数据 → 建议先运行 Collector
- 任何 Agent 超时 → 向用户报告具体错误

## 输出
最终向用户输出完整的分析报告，不要输出内部调度细节。"""


class OrchestratorAgent(BaseAgent):
    """增强版总调度 Agent"""

    name = "orchestrator"
    system_prompt = ORCHESTRATOR_SYSTEM_PROMPT

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
