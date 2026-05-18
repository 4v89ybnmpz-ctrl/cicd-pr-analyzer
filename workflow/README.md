# LangGraph 工作流编排规划

## 1. 背景

### 当前痛点
用户要获取一个项目的 CI/CD 工程能力洞察报告，需要**手动按顺序调用 5+ 个 API**：

```
Step 1: GET  /github/prs/{owner}/{repo}              → 获取 PR 列表
Step 2: GET  /github/prs/{owner}/{repo}/comments      → 获取所有评论
Step 3: GET  /github/prs/{owner}/{repo}/details        → 获取 PR 详情 (可选)
Step 4: GET  /github/prs/{owner}/{repo}/reviews        → 获取 Reviews (可选)
Step 5: POST /analysis/cicd/analyze/{owner}/{repo}     → 触发 CI/CD 分析
Step 6: GET  /analysis/cicd/report/{owner}/{repo}      → 获取报告
```

**问题**：
- 用户必须知道正确的调用顺序
- 没有自动链式执行
- 没有跨步骤的进度追踪
- 中间步骤失败需要手动重试
- 不支持一键分析多个项目

### LangGraph 能解决什么
| 能力 | 对应场景 |
|------|---------|
| StateGraph 状态图 | 定义完整的 pipeline 流程 |
| Fan-out/Fan-in 并行 | 并发获取 comments/details/reviews |
| Checkpointing 检查点 | 中断后可恢复，不重复拉取 |
| Conditional Routing | 根据 pr_comments 有无跳过拉取步骤 |
| Human-in-the-loop | 报告生成前可人工审核 |
| Sub-graph 子图 | CI/CD 解析逻辑可复用 |

---

## 2. 目录结构

```
workflow/
├── __init__.py
├── README.md                    # 本文件
├── requirements.txt             # LangGraph 依赖
│
├── state.py                     # 状态定义 (TypedDict)
├── nodes.py                     # 节点函数 (每个步骤的具体实现)
├── graphs.py                    # 图定义 (编排节点和边)
│
├── config.py                    # 工作流配置 (服务实例注入)
├── runner.py                    # 运行器 (执行图的入口)
│
├── api/
│   ├── __init__.py
│   └── routes.py                # FastAPI 路由 (暴露 workflow 接口)
│
└── tests/
    ├── __init__.py
    ├── test_state.py            # 状态测试
    ├── test_nodes.py            # 节点测试
    └── test_graphs.py           # 图测试
```

---

## 3. 工作流设计

### 3.1 主流程: 全量项目分析

```
                    ┌──────────────────┐
                    │  fetch_pr_list   │  获取 PR 列表
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │  check_existing   │  检查已存在的数据 (条件分支)
                    └────────┬─────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
    ┌─────────▼──┐  ┌───────▼────┐  ┌──────▼──────┐
    │  fetch_    │  │  fetch_    │  │  fetch_     │  并行 Fan-out
    │  comments  │  │  details   │  │  reviews    │
    └─────────┬──┘  └───────┬────┘  └──────┬──────┘
              │              │              │
              └──────────────┼──────────────┘
                             │
                    ┌────────▼─────────┐
                    │  save_to_db      │  批量入库
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │  analyze_cicd    │  CI/CD 分析
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │  generate_report │  生成洞察报告
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │  END             │  返回报告
                    └──────────────────┘
```

### 3.2 增量流程: 只处理新 PR

```
fetch_pr_list → diff_with_db → [有新PR?] → fetch_new_data → analyze_cicd → update_report
                                    │
                                    └→ [无新PR] → END (返回缓存报告)
```

### 3.3 多项目流程: 批量对比

```
START → fan-out(project_1, project_2, ...) → [每个项目走主流程] → fan-in → cross_project_report → END
```

---

## 4. 状态定义

```python
class PipelineState(TypedDict):
    # 输入
    owner: str
    repo: str
    max_prs: int                           # 最大 PR 数 (0=全部)

    # 中间数据
    pr_list: List[Dict]                    # PR 列表
    pr_numbers: List[int]                  # PR 编号列表
    comments: Dict[str, List[Dict]]        # pr_number -> comments
    details: Dict[str, Dict]              # pr_number -> detail
    reviews: Dict[str, List[Dict]]        # pr_number -> reviews

    # 分析结果
    cicd_results: List[Dict]              # 结构化 CI/CD 结果
    report: Dict[str, Any]                # 最终洞察报告

    # 进度追踪
    current_step: str                     # 当前步骤名
    progress: float                       # 进度 0-100
    errors: List[str]                     # 错误列表
    started_at: str                       # 开始时间
    completed_at: str                     # 完成时间
```

---

## 5. 节点定义

| 节点 | 函数 | 职责 | 依赖 |
|------|------|------|------|
| `fetch_pr_list` | `fetch_pr_list_node` | 调用 `GitHubPRService.fetch_prs_for_project()` | github_service |
| `check_existing` | `check_existing_node` | 检查数据库中已有的数据，决定是否需要拉取 | db |
| `fetch_comments` | `fetch_comments_node` | 并发获取所有 PR 评论 | github_service |
| `fetch_details` | `fetch_details_node` | 并发获取 PR 详情 | github_service |
| `fetch_reviews` | `fetch_reviews_node` | 并发获取 PR Reviews | github_service |
| `save_to_db` | `save_to_db_node` | 批量保存到 MongoDB | db |
| `analyze_cicd` | `analyze_cicd_node` | CICDExtractor 提取 + 入库 | db, extractor |
| `generate_report` | `generate_report_node` | 聚合统计 + 洞察评级 | db |

---

## 6. API 接口设计

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/workflow/analyze` | 一键全量分析 (输入 owner/repo) |
| `POST` | `/workflow/analyze/batch` | 批量多项目分析 |
| `GET` | `/workflow/status/{task_id}` | 查询工作流执行状态 |
| `POST` | `/workflow/incremental` | 增量分析 (只处理新 PR) |
| `GET` | `/workflow/report/{task_id}` | 获取工作流最终报告 |

---

## 7. 依赖

```
langgraph>=0.2.0
langchain-core>=0.3.0
```

> LangGraph 不依赖 LLM，纯流程编排不需要 langchain 的 LLM 模块

---

## 8. 实施计划

### Phase 1: 基础框架
- [ ] 创建 `workflow/` 目录结构
- [ ] 安装 langgraph 依赖
- [ ] 定义 `PipelineState` 状态
- [ ] 实现服务注入 `config.py` (复用现有 github_service, db 等)

### Phase 2: 节点实现
- [ ] `fetch_pr_list_node` - 获取 PR 列表
- [ ] `fetch_comments_node` - 并发获取评论
- [ ] `fetch_details_node` - 并发获取详情
- [ ] `fetch_reviews_node` - 并发获取 Reviews
- [ ] `save_to_db_node` - 批量入库
- [ ] `analyze_cicd_node` - CI/CD 分析
- [ ] `generate_report_node` - 报告生成

### Phase 3: 图编排
- [ ] 全量分析图 `build_full_analysis_graph()`
- [ ] 增量分析图 `build_incremental_graph()`
- [ ] 多项目批量图 `build_batch_graph()`

### Phase 4: API 集成
- [ ] FastAPI 路由注册
- [ ] 异步执行 + 进度查询
- [ ] 与现有 main.py 集成

### Phase 5: 测试
- [ ] 节点单元测试
- [ ] 图集成测试
- [ ] API 端到端测试

---

## 9. 与现有代码的关系

```
workflow/ (新增)
  │
  ├── 复用 backend/app/services/github_service.py    (不修改)
  ├── 复用 backend/app/services/database_service.py  (不修改)
  ├── 复用 backend/app/analysis/cicd_extractor.py    (不修改)
  ├── 复用 backend/app/models/cicd_models.py         (不修改)
  │
  └── 新增 workflow/ 目录
        ├── 定义 State (状态流转)
        ├── 定义 Nodes (调用已有服务)
        ├── 定义 Graph (编排流程)
        └── 暴露新 API (一键触发)
```

**原则**: 不修改现有代码，workflow 层只做编排调用。
