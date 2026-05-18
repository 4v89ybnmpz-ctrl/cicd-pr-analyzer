# LangGraph 知识点测验题

> 基于本项目的 workflow 模块，考察 LangGraph 工作流编排、状态管理、图构建、AI 节点等核心知识点。

---

## LangGraph 基础概念题

### Q1: LangGraph 和 LangChain 的关系是什么？LangGraph 解决了什么问题？
> **思考提示：**
> - **LangChain**：LLM 应用开发框架，提供模型调用、Prompt 管理、工具集成等基础能力
> - **LangGraph**：基于 LangChain 生态的**工作流编排框架**，专注于构建有状态的、多步骤的 AI Agent 和复杂流程
> - LangGraph 解决的核心问题：多步骤流程编排、状态在节点间传递、条件路由、循环和重试、人机协作
> - 本项目依赖：`langgraph>=0.2.0`（流程编排）+ `langchain-anthropic>=0.3.0`（Claude 调用）

---

### Q2: LangGraph 的核心概念有哪些？本项目中分别对应什么？
> **思考提示：**
> | 概念 | 说明 | 本项目对应 |
> |------|------|-----------|
> | **State** | 节点间传递的数据载体 | `PipelineState`（TypedDict） |
> | **Node** | 执行具体操作的函数 | `fetch_pr_list_node`、`ai_analyze_node` 等 |
> | **Edge** | 节点间的连接，定义执行顺序 | `graph.add_edge("A", "B")` |
> | **Conditional Edge** | 根据条件动态选择下一节点 | `route_by_diff`（增量图中根据是否有新 PR 分流） |
> | **Graph** | 节点和边的组合 | `StateGraph(PipelineState)` |
> | **Compiled Graph** | 编译后的可执行图 | `graph.compile()` |

---

### Q3: LangGraph 的 `StateGraph` 和普通的函数调用链有什么区别？
> **思考提示：** StateGraph 的优势：
> 1. **状态自动管理**：每个节点返回的部分状态会自动合并到全局状态，无需手动传递
> 2. **可视化**：编译后的图可以导出为 Mermaid/PNG 流程图
> 3. **条件路由**：`add_conditional_edges` 实现动态分支，函数调用链需要 if-else 硬编码
> 4. **可中断恢复**：配合 Checkpointing 可以暂停/恢复执行
> 5. **可观测性**：每一步的状态变化都可以追踪和调试

---

## 状态管理题

### Q4: 本项目为什么使用 `TypedDict` 而不是 Pydantic `BaseModel` 定义 State？
> **思考提示：**
> - **TypedDict**：Python 类型提示，轻量级，LangGraph 默认用字典合并方式更新状态（**增量合并**）
> - **BaseModel**：Pydantic 模型，有验证但 LangGraph 使用时会整体替换而非合并
> - TypedDict 允许节点只返回需要更新的字段（如 `{"progress": 50.0}`），其余字段保持不变
> - 如果需要严格的输入验证，可以使用 `Annotated` + 自定义 reducer 函数

---

### Q5: `PipelineState` 中的字段分为哪几类？各自的作用是什么？
> **思考提示：** 三大类：
> 1. **输入参数**：`owner`、`repo`、`max_prs` — 由调用方传入，全流程只读
> 2. **中间数据**：`pr_list`、`comments`、`details`、`reviews`、`cicd_results` — 节点之间传递的数据，逐步填充
> 3. **进度控制**：`current_step`、`progress`、`errors`、`started_at`、`completed_at` — 追踪执行状态
>
> 最终报告相关：`stats_report`、`ai_analysis`、`ai_suggestions`、`ai_risk_assessment`、`report`

---

### Q6: 节点函数只返回部分字段（如 `{"progress": 50.0}`），其他字段的值如何保持？
> **思考提示：** LangGraph 的状态更新机制是**浅合并（Shallow Merge）**：
> - 节点返回的字典会与当前状态做 `dict.update()` 合并
> - 未返回的字段保持原值不变
> - 这就是为什么节点只需返回自己修改的字段
>
> 注意：对于嵌套字典和列表，默认是**整体替换**而非深度合并。如果需要列表追加，需要使用 `Annotated` + 自定义 reducer：
> ```python
> from typing import Annotated
> from langgraph.graph import add
>
> class State(TypedDict):
>     errors: Annotated[list, add]  # 追加而非替换
> ```

---

## 图构建与编排题

### Q7: 本项目定义了哪几种图？各自的使用场景是什么？
> **思考提示：** 三种图：
> 1. **`build_full_analysis_graph()`**：全量分析（含 AI），9 个节点，拉取全部数据 → CI/CD 分析 → AI 分析 → 报告
> 2. **`build_stats_only_graph()`**：纯统计报告（无 AI），5 个节点，适用于未配置 `ANTHROPIC_API_KEY` 的场景
> 3. **`build_incremental_graph()`**：增量分析（含 AI），8 个节点，只处理数据库中没有的新 PR，通过条件边分流
>
> 选择逻辑：配置了 API Key → 全量/增量（含 AI）；未配置 → 纯统计图

---

### Q8: `graph.compile()` 做了什么？为什么必须编译后才能执行？
> **思考提示：** `compile()` 对图进行验证和优化：
> 1. **验证图结构**：检查所有边的目标节点是否存在、入口点是否设置、是否有孤立节点
> 2. **构建执行计划**：确定节点的执行顺序和依赖关系
> 3. **生成可调用对象**：返回的 compiled graph 支持 `.invoke()`（同步）和 `.ainvoke()`（异步）
> 4. **注入中间件**：如 Checkpointing（持久化）、中断点（Interrupt）等
>
> 不编译直接调用 `graph.invoke()` 会报错，因为 StateGraph 只是定义，不是可执行对象。

---

### Q9: `set_entry_point` 和 `add_edge` 的区别是什么？
> **思考提示：**
> - **`set_entry_point("node_a")`**：定义图的起始节点（从 START 到 node_a 的边），**每个图只能有一个入口点**
> - **`add_edge("node_a", "node_b")`**：定义节点间的普通边（无条件），表示 node_a 执行完后一定执行 node_b
> - `set_entry_point("A")` 等价于 `add_edge(START, "A")`
> - `add_edge("Z", END)` 表示 node_z 是终止节点，执行完结束

---

### Q10: 本项目全量分析图的完整执行流程是怎样的？各节点之间的数据如何流转？
> **思考提示：**
> ```
> fetch_pr_list → fetch_comments → fetch_details → fetch_reviews
>       ↓               ↓               ↓              ↓
>   [pr_numbers]    [comments]     [details]      [reviews]
>       ↓
> analyze_cicd → generate_stats_report → ai_analyze → ai_suggest
>       ↓               ↓                    ↓            ↓
>   [cicd_results]  [stats_report]      [ai_analysis] [ai_suggestions]
>       ↓
> generate_final_report → END
>       ↓
>   [report] (合并所有结果)
> ```
> 每个节点从 state 读取上游数据、写入处理结果到 state，下游节点自动获取最新 state。

---

## 条件路由题

### Q11: 增量分析图中的 `add_conditional_edges` 是如何工作的？
> **思考提示：** 条件路由机制：
> ```python
> graph.add_conditional_edges("check_existing", route_by_diff)
> ```
> 1. `check_existing` 节点执行完后，将其输出 state 传给 `route_by_diff` 函数
> 2. `route_by_diff` 函数根据 state 返回下一个节点名称（字符串）
> 3. 如果 `pr_numbers` 为空 → 返回 `"generate_stats_report"`（直接生成报告）
> 4. 如果有新 PR → 返回 `"fetch_comments"`（继续拉取数据）
>
> 这是 LangGraph 的核心能力：**根据运行时状态动态决定执行路径**。

---

### Q12: `route_by_diff` 函数的返回值为什么必须是节点名字符串？
> **思考提示：** LangGraph 的条件边约定：
> - 条件函数接收 state，返回**下一个节点的名称**（字符串）
> - 返回值必须是图中已注册的节点名，否则运行时报错
> - 可以返回单个字符串（单路分支）或列表（多路分支/fan-out）
> - 可以映射为更友好的名称：`add_conditional_edges("node", fn, {"yes": "A", "no": "B"})`

---

### Q13: 如果需要在条件路由中实现多路分支（fan-out），应该怎么做？
> **思考提示：**
> ```python
> def route_by_type(state):
>     if state["type"] == "github":
>         return ["fetch_github_comments", "fetch_github_details"]  # 并行执行
>     return ["fetch_gitcode_comments"]
>
> graph.add_conditional_edges("fetch_pr_list", route_by_type)
> ```
> 返回列表时，LangGraph 会并行执行列表中的所有节点（fan-out）。等所有并行节点完成后，再继续后续边（fan-in）。
>
> 本项目的 README 中规划了 fan-out/fan-in 并行获取 comments/details/reviews，但当前实现是串行。

---

## AI 节点与 LLM 集成题

### Q14: 本项目的 AI 节点如何与 LangChain 的 LLM 集成？
> **思考提示：** 集成方式：
> 1. `WorkflowConfig` 持有 `ChatAnthropic` 实例（`self.llm`）
> 2. AI 节点通过 `cfg.llm.invoke(messages)` 调用 Claude
> 3. 消息格式遵循 LangChain 标准：`[{"role": "system", "content": "..."}, {"role": "user", "content": "..."}]`
> 4. 返回 `response.content` 获取 AI 生成文本
>
> 这种设计把 LLM 调用封装在节点内部，对图的编排逻辑完全透明。

---

### Q15: `ai_analyze_node` 和 `ai_suggest_node` 为什么分成两个节点而不是一个？
> **思考提示：** 分离的好处：
> 1. **关注点分离**：分析是"理解现状"，建议是"提出方案"，职责不同
> 2. **状态可见性**：分析结果存入 `ai_analysis`，建议可以引用分析结果
> 3. **可独立跳过**：如果只想分析不需要建议，可以在图中去掉 `ai_suggest` 节点
> 4. **可观测**：每一步的状态变化都可以追踪，便于调试
> 5. **可扩展**：未来可以在两个节点之间插入其他处理（如人工审核）

---

### Q16: AI 节点的 `ai_ready` 检查模式有什么好处？如果 LLM 不可用会怎样？
> **思考提示：**
> ```python
> if not cfg.ai_ready:
>     return {"ai_analysis": "AI 分析不可用...", "progress": 90.0}
> ```
> 好处：
> 1. **优雅降级**：LLM 不可用时不会报错中断整个流程，而是跳过并给出提示
> 2. **全流程可执行**：即使没有 API Key，统计报告部分仍然正常生成
> 3. **对应 `build_stats_only_graph()`**：无 AI 的场景使用单独的精简图
>
> 这是一种**防御性编程**策略，确保工作流在任何配置下都能产出有价值的结果。

---

### Q17: `ai_suggest_node` 中如何解析 LLM 返回的 JSON？为什么要处理 Markdown 代码块？
> **思考提示：** 解析逻辑：
> ```python
> json_match = re.search(r'```json\s*(.*?)\s*```', content, re.DOTALL)
> if json_match:
>     parsed = json.loads(json_match.group(1))
> else:
>     parsed = json.loads(content)
> ```
> 原因：LLM 经常将 JSON 包裹在 Markdown 代码块中（````json ... ````），直接 `json.loads` 会失败。正则先提取代码块内容，提取失败则尝试直接解析。这是 LLM 输出解析的常见模式。
>
> 更健壮的方案可以使用 LangChain 的 `JsonOutputParser` 或 `PydanticOutputParser`。

---

### Q18: 本项目的 LLM 配置参数（temperature=0.3, max_tokens=4096）分别代表什么？
> **思考提示：**
> - **`temperature=0.3`**：控制输出随机性。0 = 完全确定性输出，1 = 高随机性。0.3 适合分析场景：有一定灵活性但保持准确性
> - **`max_tokens=4096`**：单次回复最大 token 数。分析报告通常较长，4096 约等于 3000+ 中文字
> - **`model="claude-sonnet-4-20250514"`**：使用的具体模型版本
>
> temperature 选择建议：代码生成 0、分析报告 0.3、创意写作 0.7、头脑风暴 1.0

---

## 节点实现题

### Q19: 节点函数的输入输出约定是什么？为什么每个节点返回的是字典而不是直接修改 state？
> **思考提示：**
> - **输入**：节点函数接收完整的 `PipelineState` 字典（只读语义）
> - **输出**：返回一个**部分更新字典**，LangGraph 自动合并到全局 state
> - **不直接修改 state 的原因**：
>   1. 函数式编程：纯函数易于测试和理解
>   2. LangGraph 内部管理状态合并，直接修改可能被覆盖
>   3. 支持状态回溯和 Checkpointing
>   4. 并行节点同时修改同一字段时，LangGraph 能正确处理冲突

---

### Q20: `fetch_comments_node` 中的 `ThreadPoolExecutor` 并发是如何工作的？
> **思考提示：**
> ```python
> with ThreadPoolExecutor(max_workers=cfg.github_service.max_workers) as executor:
>     futures = {executor.submit(cfg.github_service.fetch_pr_comments, owner, repo, pr_num): pr_num
>                for pr_num in pr_numbers}
>     for future in as_completed(futures):
>         result = future.result()
> ```
> 1. 为每个 PR 创建一个提交任务（`executor.submit`）
> 2. `max_workers` 控制并发线程数
> 3. `as_completed` 按完成顺序（非提交顺序）获取结果
> 4. 每个结果独立处理，失败的记录到 errors 列表不影响其他 PR
>
> 这是在 LangGraph 节点内部使用线程池的模式：节点本身是同步的，内部通过线程池实现并发。

---

### Q21: `generate_final_report_node` 是如何合并统计报告和 AI 分析结果的？
> **思考提示：** 合并逻辑：
> ```python
> report = {
>     "summary": stats.get("summary", {}),       # 来自 stats_report
>     "trends": stats.get("trends", []),           # 来自 stats_report
>     "failure_analysis": stats.get(...),           # 来自 stats_report
>     "insights": stats.get("insights", []),        # 来自 stats_report
>     "ai_analysis": ai_analysis,                    # 来自 ai_analyze 节点
>     "ai_suggestions": ai_suggestions,              # 来自 ai_suggest 节点
>     "ai_risk_assessment": ai_risk,                 # 来自 ai_suggest 节点
> }
> ```
> 这个节点是**汇聚点（Fan-in）**，将前面多个节点的输出合并为一个完整报告。这正是 StateGraph 状态自动传递的价值：每个节点只关注自己的输入输出，最终由汇聚节点统一组装。

---

### Q22: 节点中的错误处理策略是什么？错误会中断整个流程吗？
> **思考提示：** 分层错误处理：
> 1. **节点内部捕获**：如 `fetch_comments_node` 中单个 PR 失败只追加到 `errors` 列表，不影响其他 PR
> 2. **关键节点检查**：如 `fetch_pr_list_node` 检查 `result["error"]`，如果有错误则设置 `current_step` 为 `fetch_pr_list_failed`
> 3. **AI 节点降级**：LLM 不可用或调用失败时返回默认值，不中断流程
> 4. **外层兜底**：`runner.py` 中 `try/except` 捕获整个图的异常，标记任务为 `failed`
>
> 策略：**非致命错误记录但不中断，致命错误让流程失败并报告原因**。

---

## Runner 与任务管理题

### Q23: `runner.py` 的同步和异步执行模式有什么区别？
> **思考提示：**
> - **`run_full_analysis()`**：同步执行，阻塞调用线程直到完成，直接返回结果
> - **`run_full_analysis_async()`**：异步执行，立即返回 `task_id`，通过 `get_task_status(task_id)` 查询进度
> - 异步实现方式：`ThreadPoolExecutor(max_workers=1)` 在后台线程执行同步函数
> - 任务状态存储在内存字典 `_tasks` 中，通过 `threading.Lock` 保证线程安全

---

### Q24: 本项目的任务状态管理为什么使用内存字典而不是数据库？
> **思考提示：**
> - **简单高效**：工作流任务是临时性的，不需要持久化
> - **快速访问**：内存读取无 I/O 开销
> - **自动清理**：进程重启后自动清空（任务本身就是临时的）
> - **局限**：不支持多实例共享、进程重启后任务状态丢失
>
> 如果需要持久化任务状态，可以使用 LangGraph 的 **Checkpointing** 功能（如 `SqliteSaver` 或 `RedisSaver`）。

---

### Q25: `_make_initial_state` 函数为什么需要为所有字段提供默认值？
> **思考提示：** 原因：
> 1. **TypedDict 无运行时验证**：不提供默认值不会报错，但节点访问不存在的 key 会 `KeyError`
> 2. **状态完整性**：每个节点可能读取任意字段，初始状态必须包含所有可能的 key
> 3. **调试友好**：空列表 `[]` 和空字典 `{}` 比 `None` 更安全（可以直接 `len()` / `for` 遍历）
> 4. **LangGraph 合并要求**：第一次状态必须是完整的，后续节点只更新部分字段

---

## 配置与依赖注入题

### Q26: `WorkflowConfig` 的依赖注入模式有什么好处？
> **思考提示：**
> ```python
> workflow_config.initialize(
>     github_service=github_service,  # 复用已有服务
>     db=database_service,            # 复用已有服务
>     anthropic_api_key=key           # 注入 API Key
> )
> ```
> 好处：
> 1. **解耦**：节点不直接创建服务实例，通过 config 获取
> 2. **可测试**：测试时可以注入 mock 对象
> 3. **复用**：复用 backend 已有的 `GitHubPRService`、`DatabaseService`，不重复创建
> 4. **延迟初始化**：LLM 只在配置了 API Key 时才创建

---

### Q27: `workflow_config` 作为全局单例有什么潜在问题？如何改进？
> **思考提示：** 潜在问题：
> 1. **全局状态**：任何代码都能修改，难以追踪变更来源
> 2. **测试污染**：测试修改单例后可能影响其他测试
> 3. **线程安全**：`initialize()` 没有加锁，并发初始化可能导致竞态
>
> 改进方案：
> 1. 使用 FastAPI 的依赖注入（`Depends`）管理配置生命周期
> 2. 使用 Python 的 `contextvars` 实现请求级别的配置
> 3. 初始化时加锁确保只执行一次

---

### Q28: 本项目的 workflow 模块如何复用 backend 已有的服务？
> **思考提示：** 复用策略：
> ```
> workflow/
>   ├── config.py → sys.path 注入 backend 目录
>   ├── nodes.py → 调用 github_service.fetch_prs_for_project()
>   ├── nodes.py → 调用 db.save_pr_data() / db.save_pr_comments()
>   ├── nodes.py → 调用 CICDExtractor().extract_batch_structured()
>   └── ai_nodes.py → 调用 llm.invoke() (LangChain)
> ```
> 原则（README 中明确）：**不修改现有代码，workflow 层只做编排调用**。这是典型的**门面模式（Facade Pattern）**。

---

## API 路由与集成题

### Q29: workflow API 的设计遵循了什么原则？同步和异步接口如何选择？
> **思考提示：**
> - **`POST /workflow/analyze`**（同步）：适合小项目、快速分析，调用方等待结果
> - **`POST /workflow/analyze/async`**（异步）：适合大项目、耗时分析，返回 task_id 后轮询
> - **`GET /workflow/status/{task_id}`**：查询异步任务进度
> - **`GET /workflow/tasks`**：列出所有任务
>
> 设计原则：**同步接口简单直接，异步接口避免超时**。FastAPI 中 `async def` + 内部线程池，兼顾 API 响应速度和工作流执行效率。

---

### Q30: 异步分析接口返回 `task_id` 后，调用方如何获取最终结果？
> **思考提示：** 轮询模式：
> 1. `POST /workflow/analyze/async` → 返回 `{"task_id": "full_owner_repo_1234", "status": "pending"}`
> 2. `GET /workflow/status/{task_id}` → 返回 `{"status": "running", "state": {...}}`
> 3. 轮询直到 `status` 变为 `"completed"` 或 `"failed"`
> 4. 完成后从返回的 `state.report` 中获取最终报告
>
> 更好的方案：WebSocket 推送进度，避免频繁轮询。

---

## 测试与 Mock 题题

### Q31: 本项目的 AI 节点测试中如何 Mock LLM？
> **思考提示：**
> ```python
> mock_llm = MagicMock()
> mock_response = MagicMock()
> mock_response.content = "## 深度分析\n\n该项目..."
> mock_llm.invoke.return_value = mock_response
>
> workflow_config.llm = mock_llm  # 注入 mock
> ```
> 关键点：
> 1. 用 `MagicMock` 模拟 `ChatAnthropic` 实例
> 2. 设置 `invoke.return_value.content` 为期望的输出
> 3. 测试完成后恢复原始 `llm`（`workflow_config.llm = original_llm`）
> 4. 验证 `mock_llm.invoke.call_count` 确认调用次数

---

### Q32: 测试中为什么要恢复 `workflow_config.llm`？不恢复会怎样？
> **思考提示：** 因为 `workflow_config` 是全局单例：
> - 不恢复会导致后续测试使用的还是 mock 对象
> - 测试顺序依赖：先跑 "无 LLM" 测试会将 `llm` 设为 `None`，影响后续 "有 LLM" 测试
> - 这是全局可变状态的经典测试陷阱
>
> 更好的做法：使用 `@patch` 装饰器自动恢复：
> ```python
> @patch('workflow.config.workflow_config.llm', new_callable=MagicMock)
> def test_ai_analyze(self, mock_llm):
>     ...
> ```

---

### Q33: `_build_analysis_prompt` 的测试验证了什么？为什么要测试 prompt 构建？
> **思考提示：** 验证 prompt 包含所有关键数据：
> ```python
> assert "rust-lang/rust" in prompt    # 项目信息
> assert "85.5" in prompt               # 成功率
> assert "test-x86" in prompt           # 失败任务名
> assert "APPROVED" in prompt           # Review 状态
> assert "深度分析" in prompt            # 分析维度关键词
> ```
> 测试 prompt 的原因：
> 1. Prompt 是 AI 分析质量的关键，遗漏数据会导致分析不完整
> 2. 确保新数据源（如 reviews、details）被正确纳入
> 3. 回归保护：修改 prompt 结构时不会意外丢失关键信息

---

## LangGraph 进阶特性题

### Q34: LangGraph 的 Checkpointing（检查点）是什么？本项目中如何应用？
> **思考提示：** Checkpointing 在每个节点执行后自动保存状态快照：
> - **中断恢复**：流程中断后可以从最后一个检查点继续，不重复执行已完成的节点
> - **时间旅行**：可以回退到任意检查点状态重新执行
> - **实现方式**：`MemorySaver`（内存）、`SqliteSaver`（SQLite）、`RedisSaver`（Redis）
>
> 本项目当前未使用 Checkpointing（`graph.compile()` 无参数）。如果需要支持中断恢复，可以：
> ```python
> from langgraph.checkpoint.memory import MemorySaver
> checkpointer = MemorySaver()
> compiled = graph.compile(checkpointer=checkpointer)
> result = graph.invoke(initial_state, config={"configurable": {"thread_id": "task_123"}})
> ```

---

### Q35: LangGraph 的 Human-in-the-loop（人机协作）是什么？适合本项目的什么场景？
> **思考提示：** 允许在图的执行过程中暂停，等待人工输入后继续：
> ```python
> # 在节点中使用 interrupt
> from langgraph.types import interrupt
>
> def generate_report_node(state):
>     draft = generate_draft(state)
>     feedback = interrupt("请审核报告草稿", value=draft)
>     return {"report": apply_feedback(draft, feedback)}
> ```
> 适合本项目的场景：
> 1. AI 分析完成后，人工审核再生成最终报告
> 2. 大项目分析前确认 PR 数量和范围
> 3. 增量分析中人工决定是否重新分析某些 PR

---

### Q36: LangGraph 的 Sub-graph（子图）是什么？本项目中如何应用？
> **思考提示：** 子图是将一组节点封装为一个可复用的图单元：
> ```python
> # 定义数据采集子图
> fetch_subgraph = StateGraph(FetchState)
> fetch_subgraph.add_node("comments", fetch_comments_node)
> fetch_subgraph.add_node("details", fetch_details_node)
> compiled_fetch = fetch_subgraph.compile()
>
> # 在主图中引用
> main_graph.add_node("fetch_data", compiled_fetch)
> ```
> 本项目可以考虑将 "数据采集"（comments + details + reviews）封装为子图，在多种分析流程中复用。

---

### Q37: LangGraph 如何实现循环（Loop）？适合什么场景？
> **思考提示：** 通过条件边实现循环：
> ```python
> def should_retry(state):
>     if state.get("retry_count", 0) < 3 and state.get("errors"):
>         return "fetch_data"  # 重试
>     return "report"          # 放弃，生成报告
>
> graph.add_conditional_edges("validate", should_retry)
> ```
> 适用场景：
> 1. API 限流重试：请求失败后等待重试
> 2. 数据质量检查：数据不完整时重新拉取
> 3. AI 自我修正：AI 输出不合格时重新生成
> 4. 批量处理分页：循环处理直到所有页获取完毕

---

### Q38: `graph.invoke()` 和 `graph.stream()` 的区别是什么？
> **思考提示：**
> - **`invoke(state)`**：同步执行整个图，返回最终状态。阻塞直到所有节点完成
> - **`stream(state)`**：流式执行，每完成一个节点就 yield 一个状态快照。适合实时进度展示
> ```python
> for event in graph.stream(initial_state):
>     node_name = list(event.keys())[0]
>     print(f"节点 {node_name} 完成, 进度: {event[node_name].get('progress')}")
> ```
> 本项目使用 `invoke`，如果需要实时推送进度（WebSocket），应该改用 `stream`。

---

## 架构设计题

### Q39: 本项目的 workflow 模块与 backend 模块是什么关系？为什么要分开？
> **思考提示：**
> ```
> workflow/ (编排层)
>   ├── 依赖 backend/app/services/ (服务层，不修改)
>   ├── 依赖 backend/app/analysis/ (分析层，不修改)
>   └── 新增 workflow/ 目录 (编排逻辑)
> ```
> 分开的原因：
> 1. **关注点分离**：backend 负责 API + 数据 + 分析，workflow 负责流程编排
> 2. **独立演进**：LangGraph 依赖不影响 backend 核心功能
> 3. **可选安装**：不需要工作流的用户可以只用 backend
> 4. **可替换**：未来可以用其他编排引擎（如 Prefect、Airflow）替换 LangGraph

---

### Q40: 如果需要支持多项目批量分析（Cross-Project Report），如何设计图？
> **思考提示：** README 中规划的多项目流程：
> ```
> START → fan-out(project_1, project_2, ...)
>       → [每个项目走主流程]
>       → fan-in
>       → cross_project_report
>       → END
> ```
> 实现方式：
> ```python
> def fan_out_projects(state):
>     return [f"analyze_{p.owner}_{p.repo}" for p in state["projects"]]
>
> graph.add_conditional_edges("start", fan_out_projects)
> ```
> 每个项目动态创建分析子图实例，并行执行，最后由 `cross_project_report` 节点汇总对比。

---

## 参考答案速查

| 题号 | 关键答案 |
|:---:|:---|
| Q1 | LangChain 是 LLM 框架；LangGraph 是工作流编排，专注有状态多步骤流程 |
| Q2 | State/Node/Edge/Conditional Edge/Graph/Compiled Graph 六个核心概念 |
| Q3 | 自动状态管理 + 可视化 + 条件路由 + 可中断恢复 + 可观测性 |
| Q4 | TypedDict 支持增量合并；BaseModel 会整体替换；节点只需返回修改的字段 |
| Q5 | 输入参数 / 中间数据 / 进度控制 三类，逐步填充 |
| Q6 | 浅合并（dict.update）；未返回字段保持原值；列表默认替换 |
| Q7 | 全量（9 节点含 AI）/ 纯统计（5 节点无 AI）/ 增量（8 节点含条件路由） |
| Q8 | 验证结构 + 构建执行计划 + 生成可调用对象 + 注入中间件 |
| Q9 | set_entry_point 定义唯一起始节点；add_edge 定义无条件顺序 |
| Q10 | 9 节点线性流：采集 → 评论 → 详情 → Reviews → CI/CD → 统计 → AI → 建议 → 报告 |
| Q11 | 节点输出 → 条件函数 → 返回节点名 → 动态路由 |
| Q12 | 返回值必须是已注册节点名；可返回列表实现 fan-out |
| Q13 | 条件函数返回节点名列表，LangGraph 并行执行 |
| Q14 | WorkflowConfig 持有 ChatAnthropic；节点内 llm.invoke(messages) |
| Q15 | 关注点分离 + 状态可见 + 可独立跳过 + 可扩展 |
| Q16 | 优雅降级：LLM 不可用时跳过 AI，统计报告正常生成 |
| Q17 | 正则提取 ```json``` 代码块；LLM 常将 JSON 包在 Markdown 中 |
| Q18 | temperature 0.3 低随机性保准确；max_tokens 4096 适合长报告 |
| Q19 | 接收完整 state，返回部分更新字典；不直接修改保证纯函数和可回溯 |
| Q20 | ThreadPoolExecutor 并发获取多 PR 评论；as_completed 按完成顺序处理 |
| Q21 | 汇聚节点：从 state 读取 stats + ai_analysis + ai_suggestions 合并 |
| Q22 | 非致命错误记录不中断；致命错误标记失败；AI 节点降级处理 |
| Q23 | 同步阻塞返回结果；异步 ThreadPoolExecutor 后台执行返回 task_id |
| Q24 | 任务是临时性的，内存高效够用；局限是不持久化和多实例不共享 |
| Q25 | 避免节点 KeyError；空集合比 None 更安全；首次状态需完整 |
| Q26 | 解耦 + 可测试 + 复用已有服务 + LLM 延迟初始化 |
| Q27 | 全局状态难追踪 + 测试污染 + 线程不安全；可用 Depends/contextvars 改进 |
| Q28 | sys.path 注入 + 调用已有服务 API；门面模式，不修改 backend 代码 |
| Q29 | 同步适合小项目快分析；异步避免超时；task_id 轮询获取结果 |
| Q30 | POST 获取 task_id → GET 轮询 status → completed 获取 report |
| Q31 | MagicMock 模拟 ChatAnthropic；设置 invoke.return_value.content |
| Q32 | 全局单例不恢复会污染后续测试；@patch 可自动恢复 |
| Q33 | 验证 prompt 包含所有关键数据；防止遗漏导致分析不完整 |
| Q34 | 节点执行后保存快照；支持中断恢复和时间旅行；当前项目未使用 |
| Q35 | interrupt 暂停等待人工输入；适合审核报告、确认分析范围 |
| Q36 | 封装一组节点为可复用图单元；适合封装数据采集子图 |
| Q37 | 条件边返回已执行的节点名形成循环；适合重试/分页/自我修正 |
| Q38 | invoke 同步阻塞返回最终状态；stream 流式每节点 yield 进度 |
| Q39 | 编排层和服务层分离；独立演进 + 可选安装 + 可替换编排引擎 |
| Q40 | fan-out 并行项目 → 各自走主流程 → fan-in 汇总对比 |
