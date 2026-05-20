"""
Planner Agent — 任务规划 Agent
将复杂分析任务拆解为结构化的执行计划（DAG）
根据项目特征动态调整策略，支持并行任务识别
"""
import json
import logging
from typing import Dict, Any, List, Optional
from langchain_core.tools import tool
from .base_agent import BaseAgent

logger = logging.getLogger(__name__)


@tool
def analyze_project_profile(owner: str, repo: str) -> str:
    """分析项目画像: PR数量、评论密度、平台类型、数据缓存状态。
    返回项目特征摘要，用于后续策略决策。"""
    from .blackboard import blackboard, DataType

    # 先检查黑板缓存
    cached = blackboard.read(f"profile/{owner}/{repo}")
    if cached:
        return json.dumps({"cached": True, **cached}, ensure_ascii=False)

    from workflow.config import workflow_config
    github_service, db = workflow_config.github_service, workflow_config.db

    profile = {
        "owner": owner, "repo": repo,
        "platform": "github",
        "estimated_size": "unknown",
        "has_pr_data": False,
        "has_comments": False,
        "has_cicd_results": False,
        "pr_count": 0,
        "comment_count": 0,
        "recommendations": [],
    }

    # 检查数据库缓存
    if db:
        try:
            stats = db.get_aggregate_stats(owner, repo)
            profile["has_pr_data"] = stats.get("pr_data_count", 0) > 0
            profile["has_comments"] = stats.get("pr_comments_count", 0) > 0
            profile["comment_count"] = stats.get("pr_comments_count", 0)

            cicd = db.query_cicd_results(owner, repo, page=1, size=1)
            profile["has_cicd_results"] = cicd.get("total", 0) > 0

            if profile["has_pr_data"]:
                pr_data = db.get_pr_data(owner, repo)
                if pr_data:
                    profile["pr_count"] = len(pr_data.get("data", {}).get("prs", []))
        except Exception as e:
            profile["cache_error"] = str(e)

    # 如果没有缓存数据，通过 API 估算
    if profile["pr_count"] == 0 and github_service:
        try:
            result = github_service.fetch_prs_for_project(owner, repo, max_count=1)
            if result["error"] is None:
                profile["pr_count"] = result.get("total", 0)
        except Exception as e:
            logger.warning(f"API 估算失败: {e}")

    # 判断项目规模
    if profile["pr_count"] < 50:
        profile["estimated_size"] = "small"
    elif profile["pr_count"] < 500:
        profile["estimated_size"] = "medium"
    else:
        profile["estimated_size"] = "large"

    # 生成推荐策略
    if profile["has_comments"] and profile["has_cicd_results"]:
        profile["recommendations"].append("skip_collection")
        profile["recommendations"].append("incremental_analysis")
    elif profile["has_comments"]:
        profile["recommendations"].append("skip_collection")
        profile["recommendations"].append("needs_cicd_extraction")
    else:
        profile["recommendations"].append("full_collection")

    if profile["estimated_size"] == "large":
        profile["recommendations"].append("sampling_strategy")
        profile["recommendations"].append("parallel_collection")

    # 写入黑板
    blackboard.write(
        f"profile/{owner}/{repo}", DataType.METRICS,
        profile, producer="planner",
    )

    return json.dumps(profile, ensure_ascii=False)


@tool
def create_execution_plan(profile_json: str, analysis_goals: str = "full") -> str:
    """根据项目画像创建执行计划。
    profile_json: analyze_project_profile 返回的 JSON
    analysis_goals: "full"(全量), "quick"(快速), "cicd_only"(仅CI/CD), "report_only"(仅报告)
    返回 DAG 执行计划。"""
    try:
        profile = json.loads(profile_json)
    except Exception:
        return "错误: 无效的项目画像 JSON"

    owner = profile.get("owner", "")
    repo = profile.get("repo", "")
    size = profile.get("estimated_size", "medium")
    recommendations = profile.get("recommendations", [])

    plan = {
        "plan_id": f"plan_{owner}_{repo}",
        "owner": owner,
        "repo": repo,
        "goals": analysis_goals,
        "stages": [],
        "parallel_groups": [],
        "estimated_steps": 0,
    }

    # 阶段 1: 数据采集（如果需要）
    if "skip_collection" not in recommendations:
        collection_stage = {
            "stage": "collection",
            "agent": "collector",
            "tasks": [],
            "parallel": False,
        }

        tasks = [
            {"id": "collect_pr_list", "tool": "fetch_pr_list", "params": {"owner": owner, "repo": repo}},
        ]

        if size == "large":
            tasks.append({"id": "collect_comments_sample", "tool": "fetch_pr_comments",
                          "params": {"owner": owner, "repo": repo}, "depends_on": ["collect_pr_list"]})
        else:
            tasks.extend([
                {"id": "collect_comments", "tool": "fetch_pr_comments",
                 "params": {"owner": owner, "repo": repo}, "depends_on": ["collect_pr_list"]},
                {"id": "collect_reviews", "tool": "fetch_pr_reviews",
                 "params": {"owner": owner, "repo": repo}, "depends_on": ["collect_pr_list"]},
            ])
            # 详情和 reviews 可以并行
            plan["parallel_groups"].append(["collect_comments", "collect_reviews"])

        if size != "large":
            tasks.append({"id": "collect_details", "tool": "fetch_pr_details",
                          "params": {"owner": owner, "repo": repo}, "depends_on": ["collect_pr_list"]})
            plan["parallel_groups"].append(["collect_comments", "collect_details"])

        collection_stage["tasks"] = tasks
        plan["stages"].append(collection_stage)
    else:
        plan["stages"].append({
            "stage": "collection", "agent": "collector",
            "tasks": [], "skipped": True, "reason": "数据已缓存",
        })

    # 阶段 2: CI/CD 分析
    if analysis_goals != "report_only":
        plan["stages"].append({
            "stage": "analysis",
            "agent": "analyst",
            "tasks": [
                {"id": "extract_cicd", "tool": "analyze_cicd_comments", "params": {"owner": owner, "repo": repo}},
                {"id": "get_stats", "tool": "get_cicd_stats", "params": {"owner": owner, "repo": repo}},
                {"id": "get_trends", "tool": "get_cicd_trends", "params": {"owner": owner, "repo": repo}},
                {"id": "get_failure", "tool": "get_failure_analysis", "params": {"owner": owner, "repo": repo}},
            ],
            "parallel": False,
            "depends_on": ["collection"],
        })

    # 阶段 3: 验证（新增）
    plan["stages"].append({
        "stage": "validation",
        "agent": "validator",
        "tasks": [
            {"id": "validate_data", "tool": "validate_collected_data", "params": {"owner": owner, "repo": repo}},
        ],
        "parallel": False,
        "depends_on": ["analysis"],
    })

    # 阶段 4: 报告生成
    plan["stages"].append({
        "stage": "reporting",
        "agent": "reporter",
        "tasks": [
            {"id": "gen_report", "tool": "generate_stats_report", "params": {"owner": owner, "repo": repo}},
            {"id": "gen_suggestions", "tool": "ai_generate_suggestions", "depends_on": ["gen_report"]},
            {"id": "gen_risk", "tool": "ai_risk_assessment", "depends_on": ["gen_report"]},
        ],
        "parallel": False,
        "depends_on": ["validation"],
    })
    plan["parallel_groups"].append(["gen_suggestions", "gen_risk"])

    # 统计步骤数
    for stage in plan["stages"]:
        plan["estimated_steps"] += len(stage.get("tasks", []))

    return json.dumps(plan, ensure_ascii=False)


PLANNER_SYSTEM_PROMPT = """你是一个任务规划专家。你的任务是分析项目特征，制定最优的执行计划。

## 你的能力
- analyze_project_profile: 分析项目画像（规模、缓存状态、平台特征）
- create_execution_plan: 根据画像创建 DAG 执行计划

## 工作流程

### 第一步：分析项目画像
先调用 analyze_project_profile 获取项目特征：
- 项目规模（小/中/大）
- 已有数据缓存
- 推荐策略

### 第二步：创建执行计划
根据画像和分析目标创建执行计划：
- 全量分析: 采集 → 分析 → 验证 → 报告
- 快速分析: 采集(抽样) → 分析 → 简要报告
- 仅分析: 跳过采集，直接分析已有数据
- 仅报告: 跳过采集和分析，生成报告

### 第三步：输出计划
输出结构化的执行计划 JSON，包含:
- 执行阶段（stage）
- 每阶段的任务列表和依赖关系
- 可并行执行的任务组
- 预估步骤数

## 优化策略
- 小项目全量采集，大项目采样或增量
- 有缓存数据时跳过采集阶段
- 识别可并行的任务组，提升执行效率
- 根据分析目标裁剪不必要的步骤"""


class PlannerAgent(BaseAgent):
    """任务规划 Agent"""

    name = "planner"
    system_prompt = PLANNER_SYSTEM_PROMPT
    description = "任务规划 Agent，分析项目画像并生成 DAG 执行计划"
    capabilities = [
        "project_profiling", "dag_planning", "strategy_selection",
        "parallel_group_identification",
    ]

    def _register_tools(self) -> list:
        return [
            analyze_project_profile,
            create_execution_plan,
        ]
