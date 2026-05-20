"""
Collector Agent — 数据采集 Agent
拥有自主决策能力，根据项目大小和数据缓存情况决定采集策略
支持: 增量采集、并发拉取、断点续传
"""
import logging
from .base_agent import BaseAgent
from .collector_tools import (
    fetch_pr_list,
    fetch_pr_comments,
    fetch_pr_details,
    fetch_pr_reviews,
    check_db_cache,
    query_cicd_results,
    incremental_fetch,
    parallel_fetch,
)

logger = logging.getLogger(__name__)

COLLECTOR_SYSTEM_PROMPT = """你是一个数据采集专家。你的任务是高效地收集项目的 PR 数据。

## 你的能力
你可以使用以下工具来获取数据：
- fetch_pr_list: 获取 PR 列表
- fetch_pr_comments: 获取 PR 评论
- fetch_pr_details: 获取 PR 详情（标签、代码变更等）
- fetch_pr_reviews: 获取 PR Reviews（审批状态）
- check_db_cache: 检查数据库中已有的数据
- query_cicd_results: 查询已有的 CI/CD 分析结果
- incremental_fetch: 增量采集（只拉取新 PR 的数据）
- parallel_fetch: 并发拉取（快速获取多种数据类型）

## 工作策略

### 第一步：先检查缓存
在拉取数据之前，先用 check_db_cache 检查数据库中已有什么。如果已有数据足够，可以跳过部分步骤。

### 第二步：选择采集模式

#### 全量采集（首次分析）
1. fetch_pr_list → 获取 PR 列表
2. 根据 PR 数量选择:
   - **小项目**（PR < 50）: 全量拉取 comments + details + reviews
   - **中等项目**（50-500）: fetch_pr_list → fetch_pr_comments + fetch_pr_reviews
   - **大项目**（PR > 500）: 只拉取最近 100 个 PR 的数据

#### 增量采集（重复分析）
- 直接调用 incremental_fetch，自动对比已有数据，只拉取新增 PR

#### 快速采集
- 使用 parallel_fetch 并发拉取多种数据类型，速度最快

### 第三步：优先级排序
1. PR 列表（必须）
2. PR 评论（必须，CI/CD 分析依赖）
3. PR Reviews（推荐）
4. PR 详情（可选）

## 输出格式
采集完成后，用以下 JSON 格式汇报结果：
```json
{
  "owner": "...",
  "repo": "...",
  "strategy": "full|incremental|parallel",
  "pr_count": 0,
  "comments_count": 0,
  "details_count": 0,
  "reviews_count": 0,
  "cached_used": true/false,
  "summary": "简要描述采集了什么"
}
```"""


class CollectorAgent(BaseAgent):
    """数据采集 Agent"""

    name = "collector"
    system_prompt = COLLECTOR_SYSTEM_PROMPT
    description = "数据采集 Agent，从 GitHub 获取 PR 数据（列表、评论、详情、Reviews）"
    capabilities = [
        "pr_list_fetch", "pr_comments_fetch", "pr_details_fetch",
        "pr_reviews_fetch", "db_cache_check", "incremental_fetch",
        "parallel_fetch",
    ]

    def _register_tools(self) -> list:
        return [
            fetch_pr_list,
            fetch_pr_comments,
            fetch_pr_details,
            fetch_pr_reviews,
            check_db_cache,
            query_cicd_results,
            incremental_fetch,
            parallel_fetch,
        ]
