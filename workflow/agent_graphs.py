"""
多 Agent 协作图（增强版）
支持: Orchestrator 自主调度、顺序执行、并行调度、状态机追踪
"""
import json
import logging
from typing import Dict, Any, List
from datetime import datetime
from .agents.blackboard import blackboard, DataType

logger = logging.getLogger(__name__)


def build_multi_agent_graph():
    """
    构建多 Agent 协作图（增强版）

    图拓扑:
    planner_node → orchestrator_node(自主调度) → END

    Orchestrator 通过 tool_call 自主决定调度哪些子 Agent,
    额外支持 Planner 前置规划和黑板数据共享
    """
    from langgraph.graph import StateGraph, END
    from .state import PipelineState
    from .agents.orchestrator_agent import OrchestratorAgent

    def planner_node(state: PipelineState) -> Dict[str, Any]:
        """Planner 节点: 分析项目画像，为 Orchestrator 提供决策依据"""
        from .config import workflow_config
        from .agents.planner_agent import PlannerAgent

        owner = state["owner"]
        repo = state["repo"]

        llm = workflow_config.llm
        planner = PlannerAgent(llm=llm)

        if not planner.available:
            logger.warning("Planner 不可用, 跳过规划阶段")
            return {
                "current_step": "planner_skipped",
                "progress": 5.0,
            }

        logger.info(f"[Planner] 分析项目画像: {owner}/{repo}")
        plan_result = planner.run(f"分析 {owner}/{repo} 项目画像并制定执行计划")

        return {
            "current_step": "planned",
            "progress": 10.0,
            "stats_report": {"planner_output": plan_result.get("output", "")},
        }

    def orchestrator_node(state: PipelineState) -> Dict[str, Any]:
        """Orchestrator 节点: 自主调度执行"""
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

        # 构建任务描述（融入 Planner 的输出）
        planner_output = state.get("stats_report", {}).get("planner_output", "")
        task = (
            f"请分析 {owner}/{repo} 项目的 CI/CD 工程能力"
            + (f"，最多分析 {max_prs} 个 PR" if max_prs > 0 else "")
            + "。按顺序调用 Collector 采集数据，Analyst 分析数据，Validator 验证质量，Reporter 生成报告。"
        )

        if planner_output:
            task += f"\n\n以下是 Planner 的建议:\n{planner_output[:1000]}"

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
        }

    graph = StateGraph(PipelineState)
    graph.add_node("planner", planner_node)
    graph.add_node("orchestrator", orchestrator_node)

    graph.set_entry_point("planner")
    graph.add_edge("planner", "orchestrator")
    graph.add_edge("orchestrator", END)

    compiled = graph.compile()
    logger.info("多 Agent 协作图（增强版）构建完成: planner → orchestrator → END")
    return compiled


def build_sequential_agent_graph():
    """
    构建顺序 Agent 协作图（增强版: 5 步顺序调用）
    planner → collector → analyst → validator → reporter → END
    使用 Registry 获取 Agent 实例，不再每次重建
    """
    from langgraph.graph import StateGraph, END
    from .state import PipelineState
    from .config import workflow_config
    from .agents.blackboard import blackboard, DataType
    from .agents.registry import agent_registry

    def _get_agent(name: str):
        """通过 Registry 获取 Agent（复用实例）"""
        if not any(d["name"] == name for d in agent_registry.list_registered()):
            agent_registry.register_defaults()
        return agent_registry.get(name)

    def planner_node(state: PipelineState) -> Dict[str, Any]:
        from .agents.planner_agent import PlannerAgent

        owner = state["owner"]
        repo = state["repo"]

        agent = _get_agent("planner")
        if not agent or not agent.available:
            return {
                "current_step": "planner_skipped",
                "progress": 5.0,
            }

        result = agent.run(f"分析 {owner}/{repo} 项目画像")

        blackboard.write(
            f"plan/{owner}/{repo}", DataType.PLAN,
            {"output": result.get("output", "")}, producer="planner",
        )

        agent_registry.record_invocation("planner", success=result.get("error") is None)

        return {
            "current_step": "planned",
            "progress": 10.0,
        }

    def collector_node(state: PipelineState) -> Dict[str, Any]:
        owner = state["owner"]
        repo = state["repo"]
        max_prs = state.get("max_prs", 0)

        agent = _get_agent("collector")
        if not agent or not agent.available:
            return {
                "errors": state.get("errors", []) + ["Collector 不可用"],
                "current_step": "collector_failed",
                "progress": 10.0,
            }

        task = f"采集 {owner}/{repo} 的 PR 数据" + (f"，最多 {max_prs} 个" if max_prs > 0 else "")
        result = agent.run(task)
        agent_registry.record_invocation("collector", success=result.get("error") is None)

        blackboard.write(
            f"collection/{owner}/{repo}", DataType.COLLECTION_RESULT,
            {"output": result.get("output", "")}, producer="collector",
        )

        return {
            "current_step": "collected",
            "progress": 30.0,
            "comments": {"_collector_result": result.get("output", "")},
        }

    def analyst_node(state: PipelineState) -> Dict[str, Any]:
        owner = state["owner"]
        repo = state["repo"]

        agent = _get_agent("analyst")
        if not agent or not agent.available:
            return {
                "errors": state.get("errors", []) + ["Analyst 不可用"],
                "current_step": "analyst_failed",
                "progress": 35.0,
            }

        result = agent.run(f"分析 {owner}/{repo} 的 CI/CD 工程效能")
        agent_registry.record_invocation("analyst", success=result.get("error") is None)

        blackboard.write(
            f"analysis/{owner}/{repo}", DataType.ANALYSIS_RESULT,
            {"output": result.get("output", "")}, producer="analyst",
        )

        return {
            "cicd_results": [{"_analyst_result": result.get("output", "")}],
            "current_step": "analyzed",
            "progress": 55.0,
        }

    def validator_node(state: PipelineState) -> Dict[str, Any]:
        owner = state["owner"]
        repo = state["repo"]

        agent = _get_agent("validator")
        if not agent or not agent.available:
            logger.warning("Validator 不可用, 跳过验证")
            return {
                "current_step": "validation_skipped",
                "progress": 65.0,
            }

        result = agent.run(f"验证 {owner}/{repo} 的数据质量")
        agent_registry.record_invocation("validator", success=result.get("error") is None)

        return {
            "current_step": "validated",
            "progress": 70.0,
            "ai_suggestions": [result.get("output", "")],
        }

    def reporter_node(state: PipelineState) -> Dict[str, Any]:
        owner = state["owner"]
        repo = state["repo"]

        agent = _get_agent("reporter")
        if not agent or not agent.available:
            return {
                "errors": state.get("errors", []) + ["Reporter 不可用"],
                "current_step": "reporter_failed",
                "progress": 70.0,
            }

        result = agent.run(f"为 {owner}/{repo} 生成 CI/CD 洞察报告")
        agent_registry.record_invocation("reporter", success=result.get("error") is None)

        blackboard.write(
            f"report/{owner}/{repo}", DataType.REPORT_RESULT,
            {"output": result.get("output", "")}, producer="reporter",
        )

        return {
            "report": {
                "owner": owner,
                "repo": repo,
                "ai_analysis": result.get("output", ""),
                "generated_at": datetime.now().isoformat(),
            },
            "current_step": "reported",
            "progress": 100.0,
            "completed_at": datetime.now().isoformat(),
        }

    graph = StateGraph(PipelineState)
    graph.add_node("planner", planner_node)
    graph.add_node("collector", collector_node)
    graph.add_node("analyst", analyst_node)
    graph.add_node("validator", validator_node)
    graph.add_node("reporter", reporter_node)

    graph.set_entry_point("planner")
    graph.add_edge("planner", "collector")
    graph.add_edge("collector", "analyst")
    graph.add_edge("analyst", "validator")
    graph.add_edge("validator", "reporter")
    graph.add_edge("reporter", END)

    compiled = graph.compile()
    logger.info("顺序 Agent 协作图构建完成 (使用 Registry)")
    return compiled


def build_smart_agent_graph():
    """
    构建 Smart 模式图 — Planner 生成 DAG → DAG 引擎实际执行
    这是真正消费 Planner 计划的图模式

    拓扑:
    planner_node → dag_executor_node → END

    planner_node: 调用 Planner 生成计划 JSON
    dag_executor_node: DAG 引擎消费计划, 按拓扑执行各阶段
    """
    from langgraph.graph import StateGraph, END
    from .state import PipelineState
    from .config import workflow_config
    from .agents.registry import agent_registry

    def planner_node(state: PipelineState) -> Dict[str, Any]:
        """
        Planner 节点（智能路由）
        优先直接调用规则函数 analyze_project_profile + create_execution_plan
        不浪费 LLM token（这两个函数本身就是纯规则逻辑）
        仅在规则函数失败时才回退到 LLM Agent
        """
        owner = state["owner"]
        repo = state["repo"]

        try:
            # 直接调用规则函数（不经过 LLM，零 token 消耗）
            from .agents.planner_agent import analyze_project_profile, create_execution_plan
            profile_json = analyze_project_profile.invoke({"owner": owner, "repo": repo})
            plan_json = create_execution_plan.invoke({"profile_json": profile_json, "analysis_goals": "full"})
            return {
                "current_step": "planned",
                "progress": 10.0,
                "stats_report": {"plan_json": plan_json},
            }
        except Exception as e:
            logger.warning(f"规则规划失败: {e}, 回退到 LLM")

        # 回退: LLM Agent
        if not any(d["name"] == "planner" for d in agent_registry.list_registered()):
            agent_registry.register_defaults()
        planner = agent_registry.get("planner")
        if planner and planner.available:
            result = planner.run(f"先分析 {owner}/{repo} 项目画像，然后创建执行计划。使用 full 模式。")
            agent_registry.record_invocation("planner", success=result.get("error") is None)
            return {
                "current_step": "planned",
                "progress": 10.0,
                "stats_report": {"plan_json": result.get("output", "")},
            }

        # 最终回退: 默认全量计划
        default_plan = {
            "plan_id": f"default_{owner}_{repo}",
            "owner": owner, "repo": repo,
            "goals": "full",
            "stages": [
                {"stage": "collection", "agent": "collector", "tasks": [
                    {"id": "t1", "tool": "check_db_cache", "params": {"owner": owner, "repo": repo}},
                    {"id": "t2", "tool": "incremental_fetch", "params": {"owner": owner, "repo": repo}},
                ]},
                {"stage": "analysis", "agent": "analyst", "tasks": [
                    {"id": "t3", "tool": "analyze_cicd_comments", "params": {"owner": owner, "repo": repo}},
                    {"id": "t4", "tool": "get_cicd_stats", "params": {"owner": owner, "repo": repo}},
                ]},
                {"stage": "validation", "agent": "validator", "tasks": [
                    {"id": "t5", "tool": "validate_collected_data", "params": {"owner": owner, "repo": repo}},
                ]},
                {"stage": "reporting", "agent": "reporter", "tasks": [
                    {"id": "t6", "tool": "generate_stats_report", "params": {"owner": owner, "repo": repo}},
                ]},
            ],
            "parallel_groups": [],
            "estimated_steps": 6,
        }
        return {
            "current_step": "planner_fallback",
            "progress": 10.0,
            "stats_report": {"plan_json": json.dumps(default_plan, ensure_ascii=False)},
        }

    def dag_executor_node(state: PipelineState) -> Dict[str, Any]:
        """DAG 执行引擎节点"""
        from .agents.dag_executor import DAGExecutor

        owner = state["owner"]
        repo = state["repo"]

        plan_json = state.get("stats_report", {}).get("plan_json", "")
        if not plan_json:
            return {
                "errors": state.get("errors", []) + ["无执行计划"],
                "current_step": "dag_failed",
            }

        executor = DAGExecutor(llm=workflow_config.llm, max_retries=1)
        dag_result = executor.execute(plan_json)

        # 构建 report
        report = {
            "owner": owner,
            "repo": repo,
            "ai_analysis": dag_result.report.get("final_report", ""),
            "dag_execution": {
                "status": dag_result.status,
                "stages": dag_result.report.get("stages", []),
                "duration_ms": dag_result.total_duration_ms,
                "retries": dag_result.retry_count,
            },
            "generated_at": datetime.now().isoformat(),
        }

        return {
            "report": report,
            "current_step": "dag_completed",
            "progress": 100.0,
            "completed_at": datetime.now().isoformat(),
            "errors": state.get("errors", []) + [
                f"阶段 {s.stage} 失败: {s.error}"
                for s in dag_result.failed_stages
            ],
        }

    graph = StateGraph(PipelineState)
    graph.add_node("planner", planner_node)
    graph.add_node("dag_executor", dag_executor_node)

    graph.set_entry_point("planner")
    graph.add_edge("planner", "dag_executor")
    graph.add_edge("dag_executor", END)

    compiled = graph.compile()
    logger.info("Smart 模式图构建完成: planner → dag_executor → END")
    return compiled
