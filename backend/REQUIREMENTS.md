# GitHub PR 获取工具 - 需求清单

## 0.前提条件
 1.阅读pr_download/CLAUDE.md 文件 遵守该文件的规则

## 1. 配置管理
- [x] 从 JSON 配置文件加载配置
- [x] 配置文件路径自动定位（脚本所在目录）
- [x] 配置文件不存在时显示示例格式
- [x] JSON 格式验证
- [x] fetch_github_prs 功能转移到 backend
- [x] 数据获取的 owner/repo 只能通过接口提供
- [x] 配置文件热更新功能

## 2. FastAPI 框架
- [x] 创建基础 API 服务
- [x] 数据缓存机制
- [x] fetch_github_prs 功能集成到 FastAPI
- [x] 通过接口获取数据下载进度
- [x] 分页获取 PR 数据
- [x] 支持 GitHub Token 认证
- [x] 请求头配置 (Accept, Authorization)
- [x] API 限流保护（请求延迟）
- [x] 超时处理（30秒）
- [x] 并发获取多个项目

## 3. 错误处理
- [x] 网络请求出错重试机制（3次重试，5秒间隔）

## 4. 日志处理
- [x] 日志落盘到 server.log 文件
- [x] 服务监控日志输出，避免服务异常退出无日志

## 5. 数据持久化
- [x] 数据库放在 Docker 中
- [x] 配置 JSON 数据库在 Docker 中，使用 Docker Secrets 管理密码
- [x] PR 数据、PR Comments、PR Timeline 落盘到数据库
- [x] 数据分表存储（pr_data, pr_comments, pr_timeline）

## 6. 测试用例
- [x] 测试脚本：正常场景、异常场景、接口功能验证

## 7. 代码模块化
- [x] 拆分为多文件结构
- [x] 每个模块职责清晰
- [x] 按职责拆分模块 (API / Service / Core / Model / Config / Test)
- [x] backend 目录放在根目录 pr_download 下

## 8. 版本控制
- [x] 使用 Git 做版本控制
- [x] 在 pr_download 目录层初始化，不做提交

## 9. FastAPI 接口扩展
- [x] 并发获取所有已下载 PR 的 Comments 和 Timeline
- [x] 接口支持获取 owner/repo 下所有数据，增加并发获取功能

## 10. 安全性密码保护
- [x] Docker 数据库密码加密存储，不能明文形式存在

## 11. 更详细的 PR 信息获取
- [x] 获取单个 PR 详细信息（描述、标签、指派人、评审人、里程碑）
- [x] 获取 PR 代码变更统计（additions、deletions、changed_files）
- [x] 获取 PR 合并状态信息（mergeable、merged、merge_commit_sha）
- [x] 批量并发获取多个 PR 详细信息
- [x] PR 详细信息落盘到数据库（pr_details 集合）

## 12. 评论字段完善与 Bot 识别
- [x] 评论字段添加 user_type（User/Bot/Organization）
- [x] 评论字段添加 user_id、avatar_url
- [x] 评论字段添加 author_association（权限关联）
- [x] 评论字段添加 reactions（反应统计）
- [x] Bot 识别功能 - 基于用户名模式和类型判断
- [x] 评论数据添加 is_bot 字段



## 13. 数据库查询功能增强
- [x] 查询 pr_comments 集合 - 按仓库/PR号查询评论数据
- [x] 查询 pr_timeline 集合 - 按仓库/PR号查询时间线数据
- [x] 查询 pr_details 集合 - 按仓库/PR号查询详细信息
- [x] 分页查询 - 支持 page/size 参数
- [x] 排序功能 - 支持按时间、PR号等字段排序
- [x] 条件筛选 - 支持按时间范围、状态、作者等条件过滤
- [x] 聚合统计 - 统计仓库PR数量、评论数量等
- [x] 模糊搜索 - 按标题、描述关键词搜索

## 14. GitCode 平台支持
- [x] GitCode API 适配 - 支持 GitCode 平台的 API 调用
- [x] GitCode PR 列表获取 - 获取仓库 PR 列表（MR）
- [x] GitCode PR 评论获取 - 获取 PR 评论数据
- [x] GitCode PR 详情获取 - 获取 PR 详细信息
- [x] GitCode Token 认证 - 支持 GitCode 个人访问令牌
- [x] 多平台适配架构 - 支持 GitHub/GitCode 双平台

## 15. 服务稳定性监控
- [x] 心跳检测机制 - 定期记录服务存活状态
- [x] 请求超时监控 - 记录超时请求的调用栈和参数
- [x] 死锁检测 - 检测线程池/连接池阻塞情况
- [x] 内存监控 - 记录内存使用情况，检测内存泄漏
- [x] 异常捕获增强 - 捕获未处理异常并记录详细信息
- [x] 服务卡死诊断日志 - 记录卡死时的线程状态、请求队列、资源占用
- [x] 自动恢复机制 - 检测到卡死时自动重启服务（watchdog 进程 + exit code 42 + 指数退避）

## 16. 配置与日志整理
- [x] 合并配置文件 - 将 db_config.json 合并到 config.json
- [x] 日志目录统一 - 将 server.log 移动到 logs/ 目录
- [x] 日志配置集中化 - 在 config.json 中统一配置日志路径和级别

## 17. 数据分析模块
- [x] 创建数据分析目录 - app/analysis/ 模块
- [x] 数据清洗服务 - 清洗和标准化评论数据
- [x] CI/CD 评论识别 - 识别 CI/CD Bot 评论（GitHub Actions、Jenkins、Travis 等）
- [x] CI/CD 结果提取 - 提取构建状态、测试结果、覆盖率等信息
- [x] CI/CD 解析器架构 - 可扩展的解析器注册表 + 项目映射 + 自动检测混合策略
- [x] 项目映射配置 - owner/repo 到解析器的映射，支持通配符 (owner/*)
- [x] 可配置模式解析器 - JSON 规则定义解析逻辑，无需写代码即可支持新项目
- [x] Rust Bors 解析器 - 解析 rust-lang/rust 自建 CI (bors/homu) 评论格式
- [x] Flutter LUCI 解析器 - JSON 规则解析 Flutter/Chromium CI 评论格式
- [x] Jenkins/Zuul 解析器 - JSON 规则解析 Jenkins 和 Zuul CI 评论格式
- [x] PR 列表获取优化 - fetch_prs_for_project 增加 max_count 参数，避免全量分页
- [x] CI/CD 数据结构化 - 将 CI/CD 评论转换为结构化数据（Section 22.1 CICDResult 模型）
- [x] CI/CD 结果统计接口 - 提供构建成功率、平均耗时等统计（Section 22.4 API 端点）
- [x] 数据分析结果存储 - 将分析结果存入数据库（Section 22.2 cicd_results 集合）

## 18. 浏览器自动化模块
- [x] Playwright 集成 - 安装并配置 Playwright 浏览器自动化框架
- [x] 浏览器生命周期管理 - BrowserManager 启动/关闭/页面/截图
- [x] 网络请求拦截 - NetworkInterceptor 捕获 API 请求/响应
- [x] 登录与会话管理 - AuthManager Cookie 持久化/登录检测/自动登录
- [x] openLiBing 提取器 - 从拦截的 API 响应中提取流水线数据
- [x] 浏览器抓取服务 - BrowserScrapingService 串联所有组件
- [x] API 路由 - /browser/* 接口（状态/初始化/抓取/拦截数据）

## 19. AtomGit 平台支持
- [x] AtomGit API 适配 - 通过 AtomGit API v5 获取 PR 和评论数据
- [x] AtomGit PR 列表获取 - 获取仓库 PR 列表
- [x] AtomGit PR 评论获取 - 获取单个 PR 评论（自动分页）
- [x] AtomGit 批量评论获取 - 批量获取多个 PR 的评论
- [x] AtomGit 全量评论获取 - 获取整个项目全部 PR 评论（自动遍历所有 PR 分页）
- [x] AtomGit 评论存库 - PR 评论自动保存到数据库
- [x] AtomGit 流水线信息提取 - 从 Bot 评论中提取 openlibing.com 流水线链接和任务状态
- [x] AtomGit API 路由 - /atomgit/* 接口

---


## 20. 版本控制
- [x] 初始化 Git 仓库（如果尚未初始化）
- [x] 配置 .gitignore 文件（排除 config.json、encryption_key.json、secrets/、logs/、__pycache__/、*.pyc、.env 等）
- [x] 创建初始提交，包含所有现有代码
- [x] 确保敏感信息（Token、密码、密钥）不会被提交到仓库

## 21. Docker 化部署
- [x] 编写后端服务 Dockerfile（基于 Python 镜像，安装依赖，复制代码）
- [x] 修改 docker-compose.yml 添加 backend 服务，依赖 mongodb
- [x] backend 服务通过 Docker 内部网络连接 mongodb（不再暴露 27017 到宿主机）
- [x] 支持通过环境变量或 Docker Secrets 传入敏感配置（Token、密码）
- [x] docker-compose up 一键启动全套服务（mongodb + backend）
- [x] 验证服务正常启动并可访问

## 22. CI/CD 工程能力洞察报告
### 22.1 CI/CD 结构化数据模型
- [x] CICDResult 模型 - CI/CD 单条解析结果标准模型（统一各解析器返回格式）
- [x] CICDSummary 模型 - CI/CD 汇总统计模型（成功率/失败率/耗时/覆盖率）
- [x] CICDReport 模型 - 项目级 CI/CD 洞察报告模型（多维度聚合）
- [x] CICDInsight 模型 - 工程能力洞察项模型（趋势/评级/建议）

### 22.2 CI/CD 数据持久化
- [x] cicd_results 集合 - 存储结构化 CI/CD 解析结果
- [x] 数据关联 - CI/CD 结果关联 PR 信息（owner/repo/pr_number/timestamp）
- [x] 批量入库接口 - 支持批量将评论解析后存入 cicd_results 集合
- [x] 查询接口 - 支持按项目/PR/时间范围/状态查询 CI/CD 结果

### 22.3 CI/CD 统计分析服务
- [x] 成功率统计 - 按时间窗口统计构建成功率趋势
- [x] 耗时分析 - 统计平均构建耗时、P50/P90/P95 耗时分布
- [x] 失败模式分析 - 统计高频失败原因和失败 job
- [x] 覆盖率趋势 - 统计测试覆盖率变化趋势
- [x] MTTR 统计 - 平均修复时间（从失败到下一次成功）
- [x] 按维度聚合 - 按时间（日/周/月）、按 PR、按解析器类型聚合

### 22.4 CI/CD 洞察报告 API
- [x] GET /analysis/cicd/report/{owner}/{repo} - 获取项目级 CI/CD 洞察报告
- [x] GET /analysis/cicd/stats/{owner}/{repo} - 获取 CI/CD 统计数据
- [x] GET /analysis/cicd/trends/{owner}/{repo} - 获取 CI/CD 趋势数据
- [x] POST /analysis/cicd/analyze/{owner}/{repo} - 触发全量分析（从评论库解析并入库）
- [x] 报告参数 - 支持时间范围（start_date/end_date）、时间粒度（day/week/month）

### 22.5 测试用例
- [x] 模型测试 - CICDResult/CICDSummary/CICDReport 模型验证
- [x] 持久化测试 - cicd_results 集合 CRUD 测试
- [x] 统计服务测试 - 各维度统计计算正确性验证
- [x] API 集成测试 - 报告接口端到端测试

---

## 23. PR Reviews 接口
- [x] GitHub Reviews API 适配 - 调用 GitHub Pulls Reviews API 获取评审记录
- [x] 单 PR Reviews 获取 - 获取指定 PR 的所有评审记录（支持分页）
- [x] 批量 PR Reviews 获取 - 并发获取多个 PR 的评审记录
- [x] Review 数据字段 - 包含 reviewer、state(APPROVED/CHANGES_REQUESTED/COMMENTED/PENDING)、body、提交时间等
- [x] Reviews 数据持久化 - pr_reviews 集合，支持 upsert 去重
- [x] Reviews 查询接口 - 按项目/仓库分页查询
- [x] API 路由 - /github/prs/{owner}/{repo}/{pr_number}/reviews 和 /github/prs/{owner}/{repo}/reviews
- [x] 数据库查询路由 - /database/reviews
- [x] 测试用例 - 服务层、数据库、API 集成测试（12 项）

---

## 待开发功能
- [x] 建立脚本获取 openlibing.com 流水线数据（已通过浏览器自动化模块 + AtomGit 评论提取实现）
<!-- - [ ] PR Commits 接口 - 获取提交记录 -->

---

## 24. 多 Agent 协作系统 (Multi-Agent Collaboration)
> 将当前 LangGraph 固定流水线重构为多 Agent 自主协作架构。
> 每个 Agent 拥有独立的 system prompt、工具集和决策能力，
> 由 Orchestrator Agent 统一调度，实现自主规划 + 工具调用 + Agent 间通信。

### 24.1 Agent 基础架构
- [x] Agent 基类 — 封装 LangGraph `create_react_agent`，统一 Agent 创建模式
- [x] Agent 状态定义 — AgentState (TypedDict)，包含 messages/工具调用结果/错误信息
- [x] Agent 工具注册机制 — `@tool` 装饰器 + `bind_tools()` 绑定到 LLM
- [x] Agent 消息历史 — 每轮对话保留 messages，支持多轮推理
- [x] Agent 错误处理 — 工具调用失败时 Agent 自主决定重试或换策略

### 24.2 Orchestrator Agent (调度 Agent)
- [x] Orchestrator system prompt — 总调度角色，理解用户意图，决定调用哪个 Agent
- [x] Agent 路由工具 — `delegate_to_collector()`、`delegate_to_analyst()`、`delegate_to_reporter()`
- [x] 任务分解 — 将"分析 rust-lang/rust 的 CI/CD 能力"分解为多 Agent 子任务
- [x] 结果汇总 — 收集各 Agent 返回结果，组装最终响应
- [x] 决策逻辑 — 根据数据量、平台类型等条件动态调整策略

### 24.3 Collector Agent (数据采集 Agent)
- [x] Collector system prompt — 数据采集专家角色，理解"需要什么数据"
- [x] 采集工具集:
  - [x] `fetch_pr_list(owner, repo, max_count)` — 获取 PR 列表
  - [x] `fetch_pr_comments(owner, repo, pr_numbers)` — 获取 PR 评论
  - [x] `fetch_pr_details(owner, repo, pr_numbers)` — 获取 PR 详情
  - [x] `fetch_pr_reviews(owner, repo, pr_numbers)` — 获取 PR Reviews
  - [x] `check_db_cache(owner, repo)` — 检查数据库中已有数据（避免重复拉取）
  - [x] `query_cicd_results(owner, repo)` — 查询已有 CI/CD 分析结果
- [x] 自主决策 — Agent 根据项目大小决定拉取范围（小项目全量，大项目抽样）
- [x] 增量采集 — Agent 对比 DB 已有数据，只拉取增量部分

### 24.4 Analyst Agent (分析 Agent)
- [x] Analyst system prompt — CI/CD 工程效能分析专家角色
- [x] 分析工具集:
  - [x] `analyze_cicd_comments(comments)` — CI/CD 评论识别 + 结构化提取
  - [x] `get_cicd_stats(owner, repo)` — 获取 CI/CD 统计数据
  - [x] `get_cicd_trends(owner, repo, granularity)` — 获取趋势数据
  - [x] `get_failure_analysis(owner, repo)` — 获取失败分析
  - [x] `query_pr_details(owner, repo)` — 查询 PR 详情（辅助分析协作模式）
  - [x] `query_pr_reviews(owner, repo)` — 查询 PR Reviews（辅助分析 review 质量）
- [x] 自主分析 — Agent 根据数据特征选择分析维度
  - 数据量大时: 聚合统计 + 趋势分析
  - 数据量小时: 逐条深入分析
  - 失败率高时: 重点做根因分析
- [x] AI 深度洞察 — Claude 对统计数据做 6 维度深度分析（复用现有 prompt）

### 24.5 Reporter Agent (报告 Agent)
- [x] Reporter system prompt — 报告撰写专家角色，面向不同受众调整报告风格
- [x] 报告工具集:
  - [x] `generate_stats_report(stats, trends, failure)` — 生成规则引擎统计报告
  - [x] `ai_generate_suggestions(analysis, stats)` — AI 生成改进建议
  - [x] `ai_risk_assessment(analysis, failure)` — AI 风险评估
  - [x] `format_report_md(report)` — Markdown 格式化报告
  - [x] `format_report_json(report)` — JSON 结构化报告
- [x] 报告分级 — 根据受众生成不同详细程度的报告
  - 执行摘要版: 面向管理层，1页纸
  - 技术详情版: 面向工程师，含数据和代码
  - 行动计划版: 面向 PM，含优先级排序的建议列表

### 24.6 Agent 间通信协议
- [x] 消息格式定义 — AgentMessage (sender/receiver/content/metadata)
- [x] 数据传递 — 通过 LangGraph State 在 Agent 间传递结构化数据
- [x] 结果确认 — 下游 Agent 可以向上游 Agent 请求数据补充
  - 例: Reporter 发现分析维度不够 → 请求 Analyst 补充特定维度
  - 例: Analyst 发现缺少评论数据 → 请求 Collector 补充拉取

### 24.7 LangGraph 多 Agent 图编排
- [x] Orchestrator 主图 — `create_react_agent` + 子图调用
- [x] Collector 子图 — 采集 Agent 的内部决策图
- [x] Analyst 子图 — 分析 Agent 的内部决策图
- [x] Reporter 子图 — 报告 Agent 的内部决策图
- [x] 图拓扑:
  ```
  用户请求 → Orchestrator → [判断需要什么]
      ├── delegate_to_collector() → Collector Agent → 返回数据
      ├── delegate_to_analyst()   → Analyst Agent   → 返回分析
      └── delegate_to_reporter()  → Reporter Agent  → 返回报告
  Orchestrator 汇总 → 返回用户
  ```
- [x] 保留现有图 — `build_full_analysis_graph()` 保留为快速通道（不需要 Agent 决策时使用）

### 24.8 API 接口
- [x] `POST /agent/analyze` — 多 Agent 分析（输入 owner/repo，Orchestrator 自主规划）
- [x] `POST /agent/analyze/async` — 异步多 Agent 分析
- [x] `GET /agent/status/{task_id}` — 查询 Agent 执行状态（含每个 Agent 的进度）
- [x] `GET /agent/tasks` — 列出所有 Agent 任务
- [x] `POST /agent/chat` — 对话式接口（支持追问"深入分析失败原因"等）

### 24.9 测试用例
- [x] Agent 基类测试 — 工具绑定、消息处理、错误恢复
- [x] Collector Agent 测试 — 工具调用 Mock、增量决策验证
- [x] Analyst Agent 测试 — 分析维度选择 Mock、AI 分析 Mock
- [x] Reporter Agent 测试 — 报告分级验证、格式化验证
- [x] Orchestrator 测试 — Agent 路由决策、任务分解、结果汇总
- [x] 端到端集成测试 — 完整多 Agent 协作流程验证

### 24.10 实施优先级
1. **Phase 1** (基础): 24.1 Agent 基类 + 24.3 Collector Agent（最小可用） ✅
2. **Phase 2** (核心): 24.4 Analyst Agent + 24.5 Reporter Agent（核心能力） ✅
3. **Phase 3** (编排): 24.2 Orchestrator + 24.7 图编排（多 Agent 协作） ✅
4. **Phase 4** (增强): 24.6 通信协议 + 24.8 API + 24.9 测试 ✅

### 24.11 技术依赖
- [x] langgraph >= 0.2.0 (已安装)
- [x] langchain-core >= 0.3.0 (已安装)
- [x] langchain-anthropic >= 0.3.0 (已安装)
- [x] 现有服务层包装为 LangChain Tool（github_service / database_service / CICDExtractor）

---

## 25. 安全加固
> 针对企业级安全标准，对系统进行全面安全加固，包括 API 认证、CORS 限制、请求限流、安全响应头、日志脱敏等。

### 25.1 API 认证中间件
- [x] API Key 认证机制 — 通过请求头 `X-API-Key` 或查询参数 `api_key` 验证身份
- [x] API Key 配置管理 — 支持在 `config.json` 中配置多个 API Key（key + name + enabled）
- [x] 白名单路径 — `/`, `/health`, `/docs`, `/openapi.json` 等公共路径免认证
- [x] 认证失败返回标准 401 错误 — 含 `WWW-Authenticate` 响应头
- [x] 可选启用 — 通过 `security.auth_enabled` 配置项控制，默认关闭（向后兼容）

### 25.2 CORS 安全加固
- [x] CORS 白名单配置 — 从 `config.json` 的 `cors.allow_origins` 读取，替代硬编码 `["*"]`
- [x] 支持 `*` 通配符（仅开发环境使用，生产环境应配置具体域名）
- [x] CORS 相关方法/头部/凭证均可配置

### 25.3 安全响应头
- [x] 添加安全响应头中间件 — 在所有响应中自动注入:
  - `X-Content-Type-Options: nosniff`
  - `X-Frame-Options: DENY`
  - `X-XSS-Protection: 1; mode=block`
  - `Strict-Transport-Security: max-age=31536000; includeSubDomains`
  - `Content-Security-Policy: default-src 'self'`
  - `Referrer-Policy: strict-origin-when-cross-origin`
- [x] 安全响应头可通过 `security.security_headers` 配置开关

### 25.4 API 请求限流
- [x] 全局限流 — 基于 IP 的请求频率限制（默认 60次/分钟）
- [x] 路由级别限流 — 对数据写入类接口施加更严格限制（默认 20次/分钟）
- [x] 限流配置可调 — 通过 `security.rate_limit` 配置项控制窗口大小和最大请求数
- [x] 超限返回 429 Too Many Requests — 含 `Retry-After` 响应头

### 25.5 敏感信息日志脱敏
- [x] Token 脱敏 — 日志中 Token 只显示前4位和后4位，中间用 `****` 替代
- [x] 密码脱敏 — 数据库密码、API Key 等敏感信息在日志中自动脱敏
- [x] 请求参数脱敏 — 请求 URL 中 `api_key` 参数自动脱敏
- [x] 日志脱敏工具函数 — `core/security.py` 中提供统一的脱敏工具

### 25.6 Git 安全增强
- [x] .gitignore 完善补全 — 确保所有敏感文件模式都被忽略
- [x] 安全检查脚本 — 启动时检测敏感文件是否被 git 追踪，发出告警

### 25.7 安全配置集成
- [x] config.json 新增 `security` 配置节 — 统一管理认证、限流、安全头等配置
- [x] config.example.json 同步更新 — 提供安全配置示例（不含真实密钥）
- [x] 所有安全功能可通过配置开关独立启用/禁用

### 25.8 测试用例
- [x] 认证中间件测试 — 有效/无效/缺失 API Key、白名单路径、401 响应格式
- [x] CORS 测试 — 白名单域名放行、非白名单拒绝、通配符模式
- [x] 安全响应头测试 — 验证所有安全头正确注入
- [x] 限流测试 — 超限返回 429、Retry-After 头、正常请求不受影响
- [x] 日志脱敏测试 — Token/密码/Key 脱敏格式正确

---

## 26. 异步改造
> 将全量同步 I/O（requests + pymongo + ThreadPoolExecutor）改造为原生异步（httpx + motor + asyncio），
> 充分利用 FastAPI 异步特性，提升并发性能和资源利用率。

### 26.1 依赖替换
- [x] `requests` → `httpx`（异步 HTTP 客户端）
- [x] `pymongo.MongoClient` → `motor.motor_asyncio.AsyncIOMotorClient`（异步 MongoDB 驱动）
- [x] `ThreadPoolExecutor` → `asyncio.gather` / `asyncio.Semaphore`（异步并发）
- [x] `threading.Lock` → `asyncio.Lock`（异步锁）
- [x] `time.sleep()` → `asyncio.sleep()`（异步等待）

### 26.2 公共组件改造 (base_service.py)
- [x] `retry_on_failure` → 异步重试装饰器（async wrapper + asyncio.sleep）
- [x] `TokenPool` → threading.Lock 替换为 asyncio.Lock
- [x] `TaskProgress` → threading.Lock 替换为 asyncio.Lock

### 26.3 GitHub 服务异步化 (github_service.py)
- [x] `requests.get` → `httpx.AsyncClient.get`
- [x] `_make_request` → `async def _make_request`
- [x] 所有 `fetch_*` 方法 → `async def fetch_*`
- [x] `ThreadPoolExecutor` 并发 → `asyncio.gather` + `asyncio.Semaphore` 控制并发数
- [x] `time.sleep` → `asyncio.sleep`

### 26.4 数据库服务异步化 (database_service.py)
- [x] `MongoClient` → `AsyncIOMotorClient`
- [x] 所有集合操作（`update_one`/`find_one`/`find`/`count_documents`/`aggregate`）添加 `await`
- [x] `list(cursor)` → `await cursor.to_list(length=None)`
- [x] `connect()` → `async def connect()`

### 26.5 GitCode 服务异步化 (gitcode_service.py)
- [x] 与 GitHub 服务同模式改造（httpx + asyncio.gather）

### 26.6 API 路由层适配
- [x] 所有路由处理函数中添加 `await` 调用异步服务方法
- [x] 路由层 `ThreadPoolExecutor` → `asyncio.gather`
- [x] analysis.py 中直接 pymongo 操作迁移为通过 db 服务层调用

### 26.7 主应用异步化 (main.py)
- [x] 使用 FastAPI `lifespan` 异步上下文管理器（替代模块级初始化）
- [x] 数据库连接/断开放入 lifespan
- [x] 安全中间件兼容异步

### 26.8 测试用例
- [x] 异步服务方法测试（Mock httpx.AsyncClient）
- [x] 异步数据库方法测试（Mock motor）
- [x] API 集成测试使用 httpx.AsyncClient

---

## 27. 统一 Pydantic Response Models
> 将所有 API 返回的 `Dict[str, Any]` 替换为类型安全的 Pydantic Response Model，
> 实现自动 OpenAPI 文档生成、类型校验和接口规范化。

### 27.1 基础 Response 模型
- [ ] 创建 `models/responses.py` — 统一管理所有 Response Model
- [ ] 通用包装模型: `PaginatedResponse[T]`（分页）、`DataTimestampResponse[T]`（数据+时间戳）
- [ ] 通用简单模型: `MessageResponse`（消息）、`HealthResponse`（健康检查）、`RootResponse`（根路径）
- [ ] 所有 Response 模型含 `timestamp: str` 字段

### 27.2 GitHub 服务 Response 模型
- [ ] `PRItem` — 单条 PR 信息
- [ ] `PRListResult` — PR 列表结果（含 owner/repo/prs/error）
- [ ] `CommentItem` / `PRCommentsResult` — 评论
- [ ] `TimelineEventItem` / `PRTimelineResult` — 时间线
- [ ] `PRDetailResult` — PR 详情
- [ ] `ReviewItem` / `PRReviewsResult` — Reviews
- [ ] `CommitItem` / `PRCommitsResult` — Commits
- [ ] `MultiPRCollectionResponse` — 多 PR 并发获取结果
- [ ] `BatchProjectsResponse` — 多项目批量获取结果
- [ ] `TokenPoolResponse` — Token 池信息

### 27.3 数据库查询 Response 模型
- [ ] `DatabaseStatsResponse` — 数据库统计
- [ ] `DatabaseAggregateResponse` — 聚合统计
- [ ] `DatabasePaginatedResponse` — 分页查询结果
- [ ] `DatabaseSearchResponse` — 搜索结果（含 keyword）

### 27.4 CI/CD 分析 Response 模型
- [ ] `CICDAnalysisTriggerResponse` — 触发分析结果
- [ ] 复用已有 `CICDReport` / `CICDResultSummary` 等模型

### 27.5 其他 Response 模型
- [ ] `TaskResponse` / `TaskListResponse` — 任务管理
- [ ] `ConfigResponse` / `CacheStatsResponse` — 配置和缓存
- [ ] `ErrorResponse` — 统一错误响应

### 27.6 路由集成
- [ ] 所有路由端点添加 `response_model` 参数
- [ ] 验证 OpenAPI 文档自动生成正确

### 27.7 测试用例
- [ ] Response Model 序列化/反序列化测试
- [ ] 字段缺失/类型错误的校验测试

---

## 28. 数据维度增强
> 扩展 PR 数据的关联分析和深度挖掘能力，从单维数据获取升级为多维关联分析。

### 28.1 PR 关联分析
- [ ] PR 依赖关系提取 — 解析 PR body 中的 mentions、linked issues、related PR
- [ ] 跨仓库 PR 关联 — 识别跨仓库引用（如 mono-repo 中子项目 PR 依赖）
- [ ] 关联关系持久化 — pr_relations 集合，存储 PR 间的依赖/引用/阻塞关系
- [ ] 关联关系查询 API — `GET /database/relations/{owner}/{repo}`

### 28.2 代码变更深度分析
- [x] 逐文件 diff 解析 — 解析 PR 的 files changed，提取每个文件的增删行数、文件类型
- [x] 变更热点文件识别 — 统计高频变更文件/目录，识别项目热点模块
- [x] 代码复杂度趋势 — 基于变更规模（additions/deletions/changed_files）追踪复杂度变化
- [x] 变更分析 API — `GET /analysis/code-changes/{owner}/{repo}`
- [x] 变更内容分类 — 基于 PR 标题/body/文件路径/标签自动分类（新功能/Bug修复/重构/文档/测试/CI/性能优化）
- [x] 阶段性变更洞察 — 按周/月分桶，生成每个阶段的变更摘要和分类统计
- [x] 变更洞察 API — `GET /analysis/code-insight/{owner}/{repo}`

### 28.3 贡献者画像
- [ ] 贡献者活跃度统计 — PR 提交频率、review 参与频率、comment 频率
- [ ] 贡献领域分析 — 按变更文件路径归类贡献者专注领域（前端/后端/CI/文档等）
- [ ] Review 参与度统计 — review 数量、review 深度、review 响应时间
- [ ] 协作网络图数据 — 基于同 PR 参与（author + reviewer + commenter）构建协作关系
- [ ] 贡献者画像 API — `GET /analysis/contributors/{owner}/{repo}/profiles`

### 28.4 Issue 与 PR 联动
- [ ] Issue→PR 生命周期追踪 — 追踪 issue 从创建到关联 PR 合并的完整周期
- [ ] Bug 修复周期统计 — 从 bug issue 创建到修复 PR 合并的平均时间
- [ ] Issue 响应 SLA — 首次响应时间、关闭时间分布统计
- [ ] 联动分析 API — `GET /analysis/issue-pr-lifecycle/{owner}/{repo}`

---

## 29. 分析能力拓展
> 在现有 CI/CD 分析基础上，增加代码质量、Review 质量、项目健康度等分析维度。

### 29.1 代码质量指标
- [ ] 代码 churn 分析 — 基于 git log 计算文件级代码增删频率，识别高 churn 文件
- [ ] 技术债评估 — 基于 PR 存活时间、reopen 率、大 PR 比例等指标评估技术债
- [ ] 代码质量趋势 — 追踪项目代码质量指标随时间的变化趋势

### 29.2 Review 质量评估
- [x] Review 深度分析 — 统计 review 评论行数、review 耗时、review 轮次
- [x] Review 覆盖率 — 有 review 的 PR 占比、reviewer 数量分布
- [x] Review 延迟统计 — 从 PR 创建到首次 review 的平均等待时间
- [x] Review 质量 API — `GET /analysis/review-quality/{owner}/{repo}`

### 29.3 项目健康度评分
- [x] 健康度指标体系 — 综合评分维度:
  - PR 存活时间（越短越好）
  - Merge 率（适中为佳）
  - Review 覆盖率（越高越好）
  - CI 成功率（越高越好）
  - 贡献者多样性（核心贡献者占比）
  - Issue 响应速度
- [x] 健康度评级 — A-F 评级 + 各维度雷达图数据
- [x] 健康度趋势 — 按周/月追踪健康度变化
- [x] 健康度 API — `GET /analysis/health/{owner}/{repo}`

### 29.4 趋势预警
- [x] CI 失败率突增预警 — 检测 CI 失败率环比异常上升
- [x] Review 响应变慢预警 — 检测 review 延迟环比异常增长
- [x] 贡献者流失预警 — 检测核心贡献者活跃度下降
- [x] 预警规则配置 — 支持自定义阈值和预警维度
- [x] 预警 API — `GET /analysis/alerts/{owner}/{repo}`

---

## 30. 平台与集成拓展
> 增强平台集成能力，支持实时数据更新、通知推送和数据导出。

### 30.1 Webhook 接收
- [x] GitHub Webhook 接收 — 监听 push/pull_request/pull_request_review 事件
- [x] GitCode Webhook 接收 — 监听 merge_request 事件
- [x] Webhook 签名验证 — 验证 payload 签名防止伪造
- [x] 实时增量更新 — Webhook 事件触发后自动增量拉取关联数据
- [x] Webhook 管理 API — `POST /webhooks/configure`, `GET /webhooks/events`

### 30.2 通知推送
- [x] 邮件通知 — 分析报告完成后发送邮件摘要
- [x] 飞书/钉钉/Slack 通知 — 推送报告链接和关键指标到 IM
- [x] 通知规则配置 — 按项目/指标/阈值配置通知触发条件
- [x] 通知管理 API — `POST /notifications/config`, `GET /notifications/history`

### 30.3 数据导出
- [x] 报告导出 PDF — 将 CI/CD 洞察报告导出为 PDF
- [x] 报告导出 Excel — 将统计数据导出为 Excel（多 Sheet）
- [x] 数据批量导出 CSV — 支持各数据集合的 CSV 导出
- [x] 导出 API — `GET /export/report/{owner}/{repo}?format=pdf|excel|csv`

### 30.4 多仓库对比
- [x] 同组织多项目横向对比 — 按健康度/CI 成功率/Review 覆盖率等维度对比
- [x] 跨项目贡献者重叠分析 — 识别在多个项目间活跃的贡献者
- [x] 对比看板 API — `POST /analysis/compare`, `GET /analysis/compare/{compare_id}`

---

## 31. 前端可视化增强
> 提升前端数据可视化能力，增加交互式图表和实时看板。

### 31.1 PR 生命周期桑基图
- [ ] 全链路可视化 — open→review→CI→merge 状态流转桑基图
- [ ] 状态停留时间 — 各阶段平均停留时间标注
- [ ] 筛选交互 — 按时间范围/作者/标签筛选后动态更新

### 31.2 贡献者热力图
- [ ] 贡献日历 — 类似 GitHub 贡献日历，按 PR/review/comment 维度着色
- [ ] 维度切换 — PR 提交/Review/Comment 三种维度切换
- [ ] 贡献者排行 — 按选定维度和时间段排行

### 31.3 CI/CD 仪表盘
- [ ] 实时构建状态墙 — 最新 PR 的 CI 状态一览（pass/fail/pending）
- [ ] 失败率趋势图 — 按日/周展示 CI 失败率变化
- [ ] MTTR 趋势图 — 平均修复时间变化趋势
- [ ] 耗时分布图 — P50/P90/P95 构建耗时分布

### 31.4 代码变更热力图
- [x] 文件/目录变更频率 — 热力图展示高频变更区域
- [x] 变更规模气泡图 — 按文件/目录展示 additions/deletions
- [x] 热点模块识别 — 标记 churn 率最高的模块

---

## 32. 前端交互增强
> 提升前端用户体验，增加个性化配置和交互能力。

### 32.1 项目收藏与分组
- [ ] 项目收藏功能 — 用户收藏常用项目，快速入口
- [ ] 自定义分组 — 按组织/语言/业务线分组管理项目
- [ ] 分组管理 API — `POST /user/favorites`, `GET /user/favorites`

### 32.2 自定义看板
- [ ] 拖拽式仪表盘 — 用户选择指标卡片和布局
- [ ] 指标卡片库 — 提供可选指标卡片（健康度/CI 趋势/Review 统计等）
- [ ] 布局持久化 — 保存用户自定义看板布局

### 32.3 时间范围选择器
- [ ] 全局时间筛选 — 全局时间范围选择器，所有页面联动
- [ ] 快捷时间段 — 近7天/近30天/近90天/自定义
- [ ] 时间范围持久化 — 记住用户上次选择的时间范围

### 32.4 深色模式
- [ ] 明暗主题切换 — 支持 Light/Dark 模式切换
- [ ] 系统主题跟随 — 自动跟随操作系统主题设置
- [ ] 主题偏好持久化 — 记住用户主题偏好

---

## 33. 前端协作增强
> 增强团队协作能力，支持报告分享和对比分析。

### 33.1 报告批注与分享
- [ ] 报告批注 — 在报告特定位置添加批注/评论
- [ ] 生成分享链接 — 生成报告的只读分享链接（含有效期）
- [ ] 批注 API — `POST /reports/{report_id}/annotations`, `GET /reports/{report_id}/share-link`

### 33.2 对比模式
- [ ] 时间段对比 — 同项目两个时间段的指标对比视图
- [ ] 项目对比 — 两个项目的横向对比视图（雷达图/表格）
- [ ] 对比差异高亮 — 差异指标用颜色/箭头高亮

### 33.3 Agent 对话增强
- [ ] 思考过程展示 — Agent Studio 中展示 Agent 推理步骤和决策过程
- [ ] 图表渲染 — Agent 回复中支持渲染 Mermaid/Recharts 图表
- [ ] 工具调用可视化 — 展示 Agent 调用了哪些工具、参数和返回结果