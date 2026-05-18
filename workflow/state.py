"""
工作流状态定义
定义 LangGraph 流程中各节点之间传递的状态
"""
from typing import TypedDict, List, Dict, Any, Optional


class PipelineState(TypedDict):
    """
    全量分析工作流状态
    贯穿整个 pipeline 的数据载体
    """
    # 输入参数
    owner: str
    repo: str
    max_prs: int

    # 中间数据
    pr_list: List[Dict[str, Any]]
    pr_numbers: List[int]
    comments: Dict[str, Any]
    details: Dict[str, Any]
    reviews: Dict[str, Any]

    # CI/CD 分析结果
    cicd_results: List[Dict[str, Any]]

    # 统计报告 (规则引擎生成)
    stats_report: Dict[str, Any]

    # AI 深度分析结果
    ai_analysis: str
    ai_suggestions: List[str]
    ai_risk_assessment: str

    # 最终报告 (统计 + AI 合并)
    report: Dict[str, Any]

    # 进度追踪
    current_step: str
    progress: float
    errors: List[str]
    started_at: str
    completed_at: str
