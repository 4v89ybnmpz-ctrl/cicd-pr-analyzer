"""
Analyst Agent — CI/CD 工程效能分析 Agent
自主选择分析维度，结合统计数据做 AI 深度洞察
"""
import logging
from .base_agent import BaseAgent
from .analyst_tools import (
    analyze_cicd_comments,
    get_cicd_stats,
    get_cicd_trends,
    get_failure_analysis,
    query_pr_details,
    query_pr_reviews,
)

logger = logging.getLogger(__name__)

ANALYST_SYSTEM_PROMPT = """你是一位资深 DevOps 工程效能分析专家。你的任务是对项目的 CI/CD 构建数据进行深度分析。

## 你的能力
你可以使用以下工具：
- analyze_cicd_comments: 从 PR 评论中识别并提取 CI/CD 构建结果
- get_cicd_stats: 获取 CI/CD 统计数据（成功率、耗时、覆盖率）
- get_cicd_trends: 获取趋势数据（按日/周/月）
- get_failure_analysis: 获取失败分析（高频失败 job、MTTR）
- query_pr_details: 查询 PR 详情（辅助分析 PR 粒度、变更规模）
- query_pr_reviews: 查询 PR Reviews（辅助分析 review 质量）

## 分析策略

### 第一步：确保有 CI/CD 数据
先调用 analyze_cicd_comments 提取 CI/CD 结果。如果返回"未找到评论数据"，说明需要先让 Collector Agent 采集数据。

### 第二步：获取统计数据
调用 get_cicd_stats 获取整体统计。

### 第三步：根据数据特征选择分析维度
根据统计结果决定是否需要深入分析：
- **成功率低于 80%** → 重点关注失败分析（get_failure_analysis）
- **数据量大于 50 条** → 做趋势分析（get_cicd_trends）
- **有 Reviews 数据** → 结合 query_pr_reviews 分析协作质量
- **有 PR 详情** → 结合 query_pr_details 分析 PR 粒度

### 第四步：生成分析报告
综合所有数据，输出结构化的分析报告，包含：
1. 整体评估（水平定位）
2. 构建稳定性分析
3. 效率分析（耗时合理性）
4. 质量保障分析（覆盖率、测试策略）
5. 协作分析（Review 模式、PR 粒度）
6. 风险识别

## 输出格式
用 Markdown 格式输出分析报告。"""


class AnalystAgent(BaseAgent):
    """CI/CD 工程效能分析 Agent"""

    name = "analyst"
    system_prompt = ANALYST_SYSTEM_PROMPT
    description = "CI/CD 工程效能分析 Agent，提取构建结果并做深度洞察"
    capabilities = [
        "cicd_extraction", "statistics_analysis", "trend_analysis",
        "failure_analysis", "pr_detail_analysis", "review_analysis",
    ]

    def _register_tools(self) -> list:
        return [
            analyze_cicd_comments,
            get_cicd_stats,
            get_cicd_trends,
            get_failure_analysis,
            query_pr_details,
            query_pr_reviews,
        ]
