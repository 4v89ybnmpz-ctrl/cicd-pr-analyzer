"""
多 Agent 协作图
Orchestrator Agent 作为主图入口，通过工具调用分派子 Agent
同时提供简化的 LangGraph 节点包装，兼容现有 runner.py
"""
import logging
from typing import Dict, Any, List
from datetime import datetime

logger = logging.getLogger(__name__)


def build_multi_agent_graph():
    """
    构建多 Agent 协作图

    本质上 Orchestrator Agent 内部通过 tool_call 自主决定调度哪个子 Agent，
    LangGraph 图提供外部封装（状态管理、进度追踪、结果持久化）

    图拓扑:
    orchestrator_node (Orchestrator Agent 自主决策) → END
    """
    from langgraph.graph import StateGraph, END
    from .state import PipelineState
    from .agents.orchestrator_agent import OrchestratorAgent

    def orchestrator_node(state: PipelineState) -> Dict[str, Any]:
        """Orchestrator 节点：根据 state 构建任务描述，交给 Orchestrator Agent"""
        from .config import workflow_config

        owner = state["owner"]
        repo = state["repo"]
        max_prs = state.get("max_prs", 0)

        llm = workflow_config.llm
        orchestrator = OrchestratorAgent(llm=llm)

        if not orchestrator.available:
            return {
                "errors": state.get("errors", []) + ["Orchestrator Agent 不可用"],
                "current_step": "orchestrator_failed",
            }

        # 构建任务描述
        task = (
            f"请分析 {owner}/{repo} 项目的 CI/CD 工程能力"
            + (f"，最多分析 {max_prs} 个 PR" if max_prs > 0 else "")
            + "。按顺序调用 Collector 采集数据，Analyst 分析数据，Reporter 生成报告。"
        )

        logger.info(f"[Orchestrator] 开始分析: {owner}/{repo}")
        result = orchestrator.run(task)

        return {
            "report": {
                "owner": owner,
                "repo": repo,
                "ai_analysis": result.get("output", ""),
                "generated_at": datetime.now().isoformat(),
            },
            "current_step": "orchestrator_completed",
            "progress": 100.0,
            "completed_at": datetime.now().isoformat(),
            "errors": state.get("errors", []) + (result.get("errors", [])),
        }

    graph = StateGraph(PipelineState)
    graph.add_node("orchestrator", orchestrator_node)
    graph.set_entry_point("orchestrator")
    graph.add_edge("orchestrator", END)

    compiled = graph.compile()
    logger.info("多 Agent 协作图构建完成")
    return compiled


def build_sequential_agent_graph():
    """
    构建顺序 Agent 协作图（显式 3 步调用，不依赖 Orchestrator 自主决策）
    适用于需要精确控制流程的场景

    流程: collector_node → analyst_node → reporter_node → END
    """
    from langgraph.graph import StateGraph, END
    from .state import PipelineState
    from .config import workflow_config

    def collector_node(state: PipelineState) -> Dict[str, Any]:
        """Collector 节点"""
        from .agents.collector_agent import CollectorAgent

        owner = state["owner"]
        repo = state["repo"]
        max_prs = state.get("max_prs", 0)

        agent = CollectorAgent(llm=workflow_config.llm)
        if not agent.available:
            return {
                "errors": state.get("errors", []) + ["Collector 不可用"],
                "current_step": "collector_failed",
                "progress": 10.0,
            }

        task = f"采集 {owner}/{repo} 的 PR 数据" + (f"，最多 {max_prs} 个" if max_prs > 0 else "")
        result = agent.run(task)

        return {
            "current_step": "collector",
            "progress": 33.0,
            "comments": {"_collector_result": result.get("output", "")},
        }

    def analyst_node(state: PipelineState) -> Dict[str, Any]:
        """Analyst 节点"""
        from .agents.analyst_agent import AnalystAgent

        owner = state["owner"]
        repo = state["repo"]

        agent = AnalystAgent(llm=workflow_config.llm)
        if not agent.available:
            return {
                "errors": state.get("errors", []) + ["Analyst 不可用"],
                "current_step": "analyst_failed",
                "progress": 40.0,
            }

        result = agent.run(f"分析 {owner}/{repo} 的 CI/CD 工程效能")

        return {
            "cicd_results": [{"_analyst_result": result.get("output", "")}],
            "current_step": "analyst",
            "progress": 66.0,
        }

    def reporter_node(state: PipelineState) -> Dict[str, Any]:
        """Reporter 节点"""
        from .agents.reporter_agent import ReporterAgent

        owner = state["owner"]
        repo = state["repo"]

        agent = ReporterAgent(llm=workflow_config.llm)
        if not agent.available:
            return {
                "errors": state.get("errors", []) + ["Reporter 不可用"],
                "current_step": "reporter_failed",
                "progress": 70.0,
            }

        result = agent.run(f"为 {owner}/{repo} 生成 CI/CD 洞察报告")

        return {
            "report": {
                "owner": owner,
                "repo": repo,
                "ai_analysis": result.get("output", ""),
                "generated_at": datetime.now().isoformat(),
            },
            "current_step": "reporter",
            "progress": 100.0,
            "completed_at": datetime.now().isoformat(),
        }

    graph = StateGraph(PipelineState)
    graph.add_node("collector", collector_node)
    graph.add_node("analyst", analyst_node)
    graph.add_node("reporter", reporter_node)

    graph.set_entry_point("collector")
    graph.add_edge("collector", "analyst")
    graph.add_edge("analyst", "reporter")
    graph.add_edge("reporter", END)

    compiled = graph.compile()
    logger.info("顺序 Agent 协作图构建完成")
    return compiled
