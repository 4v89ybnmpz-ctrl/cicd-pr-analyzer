"""
LangGraph 图定义
编排各节点，定义流程拓扑

完整流程:
  数据采集 → CI/CD分析 → 统计报告 → AI深度分析 → AI改进建议 → 最终报告
"""
import logging

logger = logging.getLogger(__name__)


def build_full_analysis_graph():
    """
    构建全量分析工作流图 (含 AI 分析)

    fetch_pr_list
      → fetch_comments
      → fetch_details
      → fetch_reviews
      → analyze_cicd
      → generate_stats_report (规则引擎统计)
      → ai_analyze (Claude 深度分析)
      → ai_suggest (Claude 改进建议)
      → generate_final_report (合并输出)
    """
    from langgraph.graph import StateGraph, END
    from .state import PipelineState
    from .nodes import (
        fetch_pr_list_node,
        fetch_comments_node,
        fetch_details_node,
        fetch_reviews_node,
        analyze_cicd_node,
        generate_stats_report_node,
        generate_final_report_node,
    )
    from .ai_nodes import ai_analyze_node, ai_suggest_node

    graph = StateGraph(PipelineState)

    # 数据采集节点
    graph.add_node("fetch_pr_list", fetch_pr_list_node)
    graph.add_node("fetch_comments", fetch_comments_node)
    graph.add_node("fetch_details", fetch_details_node)
    graph.add_node("fetch_reviews", fetch_reviews_node)

    # 分析节点
    graph.add_node("analyze_cicd", analyze_cicd_node)
    graph.add_node("generate_stats_report", generate_stats_report_node)

    # AI 节点
    graph.add_node("ai_analyze", ai_analyze_node)
    graph.add_node("ai_suggest", ai_suggest_node)

    # 最终报告
    graph.add_node("generate_final_report", generate_final_report_node)

    # 定义边
    graph.set_entry_point("fetch_pr_list")
    graph.add_edge("fetch_pr_list", "fetch_comments")
    graph.add_edge("fetch_comments", "fetch_details")
    graph.add_edge("fetch_details", "fetch_reviews")
    graph.add_edge("fetch_reviews", "analyze_cicd")
    graph.add_edge("analyze_cicd", "generate_stats_report")
    graph.add_edge("generate_stats_report", "ai_analyze")
    graph.add_edge("ai_analyze", "ai_suggest")
    graph.add_edge("ai_suggest", "generate_final_report")
    graph.add_edge("generate_final_report", END)

    compiled = graph.compile()
    logger.info("全量分析图 (含 AI) 构建完成, 共 9 个节点")
    return compiled


def build_stats_only_graph():
    """
    构建纯统计报告图 (不含 AI)
    适用于没有配置 ANTHROPIC_API_KEY 的场景
    """
    from langgraph.graph import StateGraph, END
    from .state import PipelineState
    from .nodes import (
        fetch_pr_list_node,
        fetch_comments_node,
        analyze_cicd_node,
        generate_stats_report_node,
        generate_final_report_node,
    )

    graph = StateGraph(PipelineState)

    graph.add_node("fetch_pr_list", fetch_pr_list_node)
    graph.add_node("fetch_comments", fetch_comments_node)
    graph.add_node("analyze_cicd", analyze_cicd_node)
    graph.add_node("generate_stats_report", generate_stats_report_node)
    graph.add_node("generate_final_report", generate_final_report_node)

    graph.set_entry_point("fetch_pr_list")
    graph.add_edge("fetch_pr_list", "fetch_comments")
    graph.add_edge("fetch_comments", "analyze_cicd")
    graph.add_edge("analyze_cicd", "generate_stats_report")
    graph.add_edge("generate_stats_report", "generate_final_report")
    graph.add_edge("generate_final_report", END)

    compiled = graph.compile()
    logger.info("纯统计图 (无 AI) 构建完成, 共 5 个节点")
    return compiled


def build_incremental_graph():
    """
    构建增量分析工作流图 (含 AI)
    只处理数据库中没有的新 PR
    """
    from langgraph.graph import StateGraph, END
    from .state import PipelineState
    from .nodes import (
        fetch_pr_list_node,
        fetch_comments_node,
        analyze_cicd_node,
        generate_stats_report_node,
        generate_final_report_node,
    )
    from .ai_nodes import ai_analyze_node, ai_suggest_node

    def check_existing_node(state):
        """检查数据库中已有的 PR 数据"""
        from .config import workflow_config
        db = workflow_config.db
        if db is None:
            return {"current_step": "check_existing", "progress": 15.0}

        existing = db.get_pr_data(state["owner"], state["repo"])
        if existing:
            existing_prs = set(
                pr["number"]
                for pr in existing.get("data", {}).get("prs", [])
            )
            new_prs = [
                n for n in state.get("pr_numbers", [])
                if n not in existing_prs
            ]
            return {
                "pr_numbers": new_prs,
                "current_step": "check_existing",
                "progress": 15.0,
            }
        return {"current_step": "check_existing", "progress": 15.0}

    def route_by_diff(state):
        """根据是否有新 PR 决定下一步"""
        if not state.get("pr_numbers"):
            return "generate_stats_report"
        return "fetch_comments"

    graph = StateGraph(PipelineState)

    graph.add_node("fetch_pr_list", fetch_pr_list_node)
    graph.add_node("check_existing", check_existing_node)
    graph.add_node("fetch_comments", fetch_comments_node)
    graph.add_node("analyze_cicd", analyze_cicd_node)
    graph.add_node("generate_stats_report", generate_stats_report_node)
    graph.add_node("ai_analyze", ai_analyze_node)
    graph.add_node("ai_suggest", ai_suggest_node)
    graph.add_node("generate_final_report", generate_final_report_node)

    graph.set_entry_point("fetch_pr_list")
    graph.add_edge("fetch_pr_list", "check_existing")
    graph.add_conditional_edges("check_existing", route_by_diff)
    graph.add_edge("fetch_comments", "analyze_cicd")
    graph.add_edge("analyze_cicd", "generate_stats_report")
    graph.add_edge("generate_stats_report", "ai_analyze")
    graph.add_edge("ai_analyze", "ai_suggest")
    graph.add_edge("ai_suggest", "generate_final_report")
    graph.add_edge("generate_final_report", END)

    compiled = graph.compile()
    logger.info("增量分析图 (含 AI) 构建完成")
    return compiled
