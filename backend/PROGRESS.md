# GitHub PR 获取工具 - 实现进度

> AI 自动更新此文件，记录功能实现状态

## 完成状态总览

| 模块 | 状态 | 完成时间 |
|------|------|----------|
| 1. 配置管理 | ✅ 完成 | 2026-03-26 |
| 2. FastAPI 框架 | ✅ 完成 | 2026-03-27 |
| 3. 错误处理 | ✅ 完成 | 2026-03-27 |
| 4. 日志处理 | ✅ 完成 | 2026-03-27 |
| 5. 数据持久化 | ✅ 完成 | 2026-04-02 |
| 6. 测试用例 | ✅ 完成 | 2026-04-02 |
| 7. 代码模块化 | ✅ 完成 | 2026-03-28 |
| 8. 版本控制 | ✅ 完成 | 2026-03-27 |
| 9. 接口扩展 | ✅ 完成 | 2026-04-02 |
| 10. 密码保护 | ✅ 完成 | 2026-04-02 |
| 11. PR 详细信息 | ✅ 完成 | 2026-04-09 |
| 12. 评论 Bot 识别 | ✅ 完成 | 2026-04-09 |
| 13. 数据库查询增强 | ✅ 完成 | 2026-04-09 |
| 14. GitCode 平台支持 | ✅ 完成 | 2026-04-09 |
| 15. 服务稳定性监控 | ✅ 完成 | 2026-04-10 |
| 16. 配置与日志整理 | ✅ 完成 | 2026-04-10 |
| 17. 数据分析模块 | ✅ 完成 | 2026-04-12 |
| 18. 浏览器自动化模块 | ✅ 完成 | 2026-04-12 |
| 19. AtomGit 平台支持 | ✅ 完成 | 2026-04-12 |
| 20. 版本控制 | ✅ 完成 | 2026-05-18 |
| 21. Docker 化部署 | ✅ 完成 | 2026-05-18 |
| 22. CI/CD 工程能力洞察报告 | ✅ 完成 | 2026-05-18 |
| 23. PR Reviews 接口 | ✅ 完成 | 2026-05-18 |
| 24. 多 Agent 协作系统 | ✅ 完成 | 2026-05-19 |
| 25. 安全加固 | ✅ 完成 | 2026-05-20 |
| 26. 异步改造 | ✅ 完成 | 2026-05-20 |

## 详细实现记录

### 1. 配置管理 ✅
- [config_manager.py](app/config/config_manager.py) - 配置加载、验证、热更新
- `/config/reload` 接口实现热更新

### 2. FastAPI 框架 ✅
- [main.py](app/main.py) - 应用入口
- [routes.py](app/api/routes.py) - 所有 API 路由
- [cache.py](app/core/cache.py) - 数据缓存
- [github_service.py](app/services/github_service.py) - GitHub API 服务

### 3. 错误处理 ✅
- [github_service.py:217-238](app/services/github_service.py) - 重试机制

### 4. 日志处理 ✅
- [logger.py](app/core/logger.py) - 日志配置、全局异常处理

### 5. 数据持久化 ✅
- [docker-compose.yml](docker-compose.yml) - MongoDB + Mongo Express
- [database_service.py](app/services/database_service.py) - 数据库操作
- [docker_secrets.py](app/core/docker_secrets.py) - Docker Secrets 支持

### 6. 测试用例 ✅
- [test_api.py](app/test/test_api.py) - 所有接口测试
- [test_encryption.py](app/test/test_encryption.py) - 加密功能测试
- 测试通过率: 100%

### 7. 代码模块化 ✅
```
app/
├── api/       # API 路由
├── core/      # 核心组件
├── config/    # 配置管理
├── models/    # 数据模型
├── services/  # 服务层
└── test/      # 测试
```

### 8. 版本控制 ✅
- Git 在项目根目录初始化
- 尚未提交，等待开发者确认

### 9. 接口扩展 ✅
- `GET /github/prs/{owner}/{repo}/comments` - 并发获取所有 PR 评论
- `GET /github/prs/{owner}/{repo}/timeline` - 并发获取所有 PR 时间线
- `POST /github/prs/details/batch` - 批量获取 PR 详细信息

### 10. 密码保护 ✅
- [encryption.py](app/core/encryption.py) - AES 加密
- [password_manager.py](password_manager.py) - 密码管理工具
- Docker Secrets 配置完成

### 11. PR 详细信息获取 ✅ (2026-04-09)
- [github_service.py](app/services/github_service.py) - 新增方法:
  - `fetch_pr_detail()` - 获取单个 PR 详细信息
  - `fetch_pr_detail_batch()` - 并发获取多个 PR 详细信息
- [routes.py](app/api/routes.py) - 新增接口:
  - `GET /github/prs/{owner}/{repo}/{pr_number}/detail` - 获取单个 PR 详细信息
  - `POST /github/prs/detail/batch` - 批量获取 PR 详细信息
  - `GET /github/prs/{owner}/{repo}/details` - 并发获取所有 PR 详细信息
- PR 详细信息包含: 描述、标签、指派人、评审人、里程碑、代码变更统计、合并状态

### 12. 评论字段完善与 Bot 识别 ✅ (2026-04-09 新增)
- [github_service.py](app/services/github_service.py) - 修改:
  - 评论字段完善，新增: `user_id`, `user_type`, `avatar_url`, `author_association`, `reactions`, `is_bot`
  - `_is_bot_user()` - Bot 识别方法
  - `known_bot_patterns` - 已知 Bot 用户名列表 (30+ 个常见 Bot)
  - `bot_regex_patterns` - Bot 命名模式正则 (xxx[bot], xxx-bot, xxx_bot 等)
- Bot 识别逻辑:
  - GitHub API 标记的 `type == "Bot"`
  - 匹配已知 Bot 用户名列表
  - 匹配 Bot 命名正则模式
- [test_api.py](app/test/test_api.py) - 新增:
  - `test_comment_bot_detection()` - 评论 Bot 识别测试

### 13. 数据库查询功能增强 ✅ (2026-04-09 新增)
- [database_service.py](app/services/database_service.py) - 新增方法:
  - `list_pr_comments()` - 分页查询 PR 评论
  - `list_pr_timeline()` - 分页查询 PR 时间线
  - `list_pr_details()` - 分页查询 PR 详细信息（支持状态/时间筛选）
  - `search_pr_details()` - 模糊搜索 PR（标题/描述关键词）
  - `get_aggregate_stats()` - 聚合统计（按仓库/状态分组）
- [routes.py](app/api/routes.py) - 新增接口:
  - `GET /database/comments` - 查询 PR 评论列表
  - `GET /database/timeline` - 查询 PR 时间线列表
  - `GET /database/details` - 查询 PR 详细信息列表
  - `GET /database/details/search` - 模糊搜索 PR
  - `GET /database/aggregate` - 聚合统计
- [test_api.py](app/test/test_api.py) - 新增:
  - `test_database_query()` - 数据库高级查询测试

### 14. GitCode 平台支持 ✅ (2026-04-09 新增)
- [gitcode_service.py](app/services/gitcode_service.py) - GitCode 服务适配器:
  - `GitCodeTokenPool` - GitCode Token 池管理
  - `GitCodePRService` - GitCode PR 服务类
  - `fetch_merge_requests()` - 获取合并请求列表（MR）
  - `fetch_mr_comments()` - 获取 MR 评论
  - `fetch_mr_detail()` - 获取 MR 详细信息
  - `fetch_mr_changes()` - 获取 MR 代码变更
  - `fetch_all_mr_comments()` - 并发获取所有 MR 评论
  - `fetch_all_mr_details()` - 并发获取所有 MR 详情
  - `_is_bot_user()` - Bot 用户识别
- [routes.py](app/api/routes.py) - 新增 GitCode 接口:
  - `GET /gitcode/mrs/{owner}/{repo}` - 获取 MR 列表
  - `GET /gitcode/mrs/{owner}/{repo}/{mr_iid}/comments` - 获取 MR 评论
  - `GET /gitcode/mrs/{owner}/{repo}/{mr_iid}/detail` - 获取 MR 详情
  - `GET /gitcode/mrs/{owner}/{repo}/{mr_iid}/changes` - 获取 MR 代码变更
  - `GET /gitcode/mrs/{owner}/{repo}/comments` - 并发获取所有 MR 评论
  - `GET /gitcode/mrs/{owner}/{repo}/details` - 并发获取所有 MR 详情
- [config.json](config.json) - 新增配置:
  - `gitcode_tokens` - GitCode Token 列表
  - `gitcode_settings` - GitCode API 设置
- [test_api.py](app/test/test_api.py) - 新增:
  - `test_gitcode_api()` - GitCode API 测试

### 15. 代码重构优化 ✅ (2026-04-10 新增)
- **删除多余文件**
  - 删除 shell 脚本：monitor_service.sh, restart_service.sh, service_daemon.sh, start_service.sh, stop_service.sh
  - 删除文档文件：DOCKER_README.md, DOCKER_SECRETS_README.md, PASSWORD_ENCRYPTION_README.md, SERVICE_MANAGEMENT.md
  - 删除临时文件：backend_service.pid, test.py, password_manager.py
- **路由模块拆分** [app/api/routes/](app/api/routes/)
  - [base.py](app/api/routes/base.py) - 基础接口（根路径、健康检查）
  - [config.py](app/api/routes/config.py) - 配置和缓存接口
  - [github.py](app/api/routes/github.py) - GitHub PR 接口
  - [database.py](app/api/routes/database.py) - 数据库查询接口
  - [gitcode.py](app/api/routes/gitcode.py) - GitCode API 接口
  - [task.py](app/api/routes/task.py) - 任务管理接口
- **服务层优化** [app/services/](app/services/)
  - [base_service.py](app/services/base_service.py) - 公共基类
    - `TokenPool` - Token 池管理基类
    - `TaskProgress` - 任务进度管理
    - `BotDetector` - Bot 用户检测器
    - `retry_on_failure` - 重试装饰器
- **目录结构更清晰**
  ```
  backend/
  ├── app/
  │   ├── api/routes/    # 分离的路由模块
  │   ├── core/          # 核心组件
  │   ├── config/        # 配置管理
  │   ├── models/        # 数据模型
  │   ├── services/      # 服务层
  │   └── test/          # 测试
  ├── config.json        # 主配置
  ├── docker-compose.yml # Docker 配置
  └── requirements.txt   # 依赖
  ```

### 16. 服务稳定性监控 ✅ (2026-04-10 新增, 2026-05-27 更新)
- [monitor.py](app/core/monitor.py) - 服务监控模块:
  - `ServiceMonitor` - 服务监控器类
  - `track_request()` - 请求追踪
  - `_check_heartbeat()` - 心跳检测
  - `_check_requests()` - 超时请求检测
  - `_check_memory()` - 内存监控
  - `_check_threads()` - 线程状态检测
  - `_dump_thread_status()` - 导出线程堆栈
  - `_trigger_recovery()` - 自动恢复触发（exit code 42 退出，由 watchdog 重启）
  - `ExceptionHook` - 全局异常钩子
  - `ServiceWatchdog` - 看门狗进程管理器（子进程启动 + HTTP 健康检查 + 指数退避重启）
- [main.py](app/main.py) - 集成监控:
  - 监控中间件 - 请求追踪中间件
  - `GET /monitor/status` - 监控状态接口（含 auto_recovery/recovery_count）
  - 支持 `--watchdog` 命令行参数启动看门狗模式
- 监控日志输出到 `logs/monitor.log`
- 功能:
  - 心跳检测（10秒间隔）
  - 请求超时监控（60秒阈值）
  - 内存使用监控（500MB阈值）
  - 线程数异常检测
  - 未捕获异常记录
  - 卡死时导出线程堆栈
  - **自动恢复** — 检测到卡死时以 exit code 42 退出，watchdog 自动重启（指数退避，最大 10 次）

### 16. 配置与日志整理 ✅ (2026-04-10 新增)
- **合并配置文件**
  - 删除 `db_config.json`，合并到 `config.json`
  - 新增 `database` 配置节
  - 新增 `logging` 配置节（log_dir, log_file, log_level）
- **日志目录统一**
  - `server.log` 移动到 `logs/` 目录
  - `monitor.log` 也在 `logs/` 目录
- **代码更新**
  - [logger.py](app/core/logger.py) - 从 config.json 读取日志配置
  - [main.py](app/main.py) - 从 config.json 读取数据库配置

### 17. 数据分析模块 ✅ (2026-04-12 更新)
- **目录结构** [app/analysis/](app/analysis/)
  - [__init__.py](app/analysis/__init__.py) - 模块入口
  - [cleaner.py](app/analysis/cleaner.py) - 数据清洗服务
  - [cicd_extractor.py](app/analysis/cicd_extractor.py) - CI/CD 提取器（支持项目映射 + 自动检测）
  - [parsers/](app/analysis/parsers/) - 解析器模块
    - [base_parser.py](app/analysis/parsers/base_parser.py) - 解析器基类
    - [nvidia_cccl_parser.py](app/analysis/parsers/nvidia_cccl_parser.py) - NVIDIA CCCL 解析器 (Python 类)
    - [github_actions_parser.py](app/analysis/parsers/github_actions_parser.py) - GitHub Actions 解析器 (Python 类)
    - [rust_bors_parser.py](app/analysis/parsers/rust_bors_parser.py) - Rust Bors 解析器 (Python 类)
    - [configurable_parser.py](app/analysis/parsers/configurable_parser.py) - 可配置模式解析器 (JSON 规则)
    - [generic_parser.py](app/analysis/parsers/generic_parser.py) - 通用兜底解析器
    - [project_parsers.json](app/analysis/parsers/project_parsers.json) - 项目映射配置
    - [parser_rules.json](app/analysis/parsers/parser_rules.json) - JSON 解析规则（flutter-luci, jenkins-ci, zuul-ci）
- **解析器架构**
  - ParserRegistry - 解析器注册表，支持项目映射 + 自动检测混合策略
  - 匹配优先级: 项目精确映射 → 通配符映射 → can_parse 自动检测 → generic 兜底
  - 新项目接入: 格式简单加 JSON 规则，格式复杂写 Python Parser 类
- **已实现解析器**
  - rust-bors (priority=8) - Rust 自建 CI (bors/homu)，提取 emoji 状态/commit/duration/failed_jobs
  - flutter-luci (priority=9) - Flutter LUCI/Chromium CI，JSON 规则
  - nvidia-cccl (priority=10) - NVIDIA CCCL CI，提取 Pass率/Hits率/耗时
  - jenkins-ci (priority=15) - Jenkins CI，JSON 规则
  - zuul-ci (priority=15) - Zuul CI，JSON 规则
  - github-actions (priority=20) - GitHub Actions
  - generic (priority=100) - 通用兜底
- **PR 列表获取优化**
  - `fetch_prs_for_project()` 增加 `max_count` 参数，避免大仓库全量分页
- **验证数据**
  - rust-lang/rust: 500 PR, 2275 评论, 350 Bot 评论，rust-bors 解析器 100% 匹配
  - NVIDIA/cccl: 解析器正常工作
  - flutter-luci, jenkins-ci, zuul-ci: 可配置解析器验证通过

### 18. 浏览器自动化模块 ✅ (2026-04-12 新增)
- **目录结构** [app/browser/](app/browser/)
  - [manager.py](app/browser/manager.py) - BrowserManager 浏览器生命周期管理
  - [interceptor.py](app/browser/interceptor.py) - NetworkInterceptor 网络请求拦截
  - [auth.py](app/browser/auth.py) - AuthManager 登录与会话管理
  - [service.py](app/browser/service.py) - BrowserScrapingService 主服务
  - [config.py](app/browser/config.py) - 浏览器/拦截器/平台配置
  - [extractors/](app/browser/extractors/) - 数据提取器
    - [base.py](app/browser/extractors/base.py) - 提取器基类
    - [openlibing.py](app/browser/extractors/openlibing.py) - openLiBing 流水线提取器
- **功能**
  - Playwright 集成，支持 headless/headed 模式
  - 网络请求拦截，自动捕获 API 请求/响应
  - Cookie 持久化，登录态复用（24h 有效期）
  - 自动登录检测 + 登录表单填写
  - 从拦截数据中提取流水线/阶段/任务信息
- **API 接口**
  - `GET /browser/status` - 服务状态
  - `POST /browser/initialize` - 启动浏览器
  - `POST /browser/shutdown` - 关闭浏览器
  - `GET /browser/platforms` - 列出支持的平台
  - `POST /browser/fetch-pipeline` - 抓取流水线数据
  - `GET /browser/captured-requests` - 查看拦截的请求
  - `GET /browser/api-responses` - 查看拦截的 API 响应
- **测试**: 44/44 通过 (100%)

### 19. AtomGit 平台支持 ✅ (2026-04-12 新增, 2026-05-27 增强)
- **目录结构** [app/gitcode/](app/gitcode/)
  - [service.py](app/gitcode/service.py) - AtomGitService API 服务类
  - [config.py](app/gitcode/config.py) - AtomGit API 配置
  - [fetch_comments.py](app/gitcode/fetch_comments.py) - 命令行获取脚本
- **AtomGitService 功能**
  - `get_user()` - 验证 Token
  - `fetch_pulls()` - 获取 PR 列表
  - `fetch_pull_comments()` - 获取单个 PR 评论
  - `fetch_all_pull_comments()` - 获取 PR 全部评论（自动分页）
  - `fetch_pulls_with_comments()` - 批量获取 PR 及评论
  - `fetch_all_project_comments()` - 全量获取整个项目 PR 评论（自动遍历所有 PR）
  - `fetch_pull_detail()` - 获取单个 PR 详细信息（描述/标签/指派人/评审人/里程碑/代码变更统计/合并状态）
  - `fetch_pull_reviews()` - 获取 PR Reviews（自动分页）
  - `fetch_pull_commits()` - 获取 PR Commits（自动分页）
  - `fetch_pull_files()` - 获取 PR 变更文件列表（自动分页）
  - `fetch_pull_timeline()` - 获取 PR 时间线事件（自动分页）
  - `fetch_issues()` - 获取仓库 Issue 列表（自动过滤 PR）
  - `fetch_issue_detail()` - 获取单个 Issue 详细信息
  - `fetch_all_pull_details()` - 并发获取多个 PR 详情
  - `fetch_all_pull_reviews()` - 并发获取多个 PR Reviews
  - `fetch_all_pull_commits()` - 并发获取多个 PR Commits
  - `fetch_all_pull_files()` - 并发获取多个 PR 变更文件
  - `fetch_all_pull_timelines()` - 并发获取多个 PR 时间线
  - `_extract_pipeline_info()` - 从 Bot 评论提取 openlibing.com 流水线信息
- **API 接口**
  - `GET /atomgit/pulls/{owner}/{repo}` - PR 列表
  - `GET /atomgit/pulls/{owner}/{repo}/{number}/detail` - PR 详情（存库）
  - `GET /atomgit/pulls/{owner}/{repo}/{number}/comments` - 单个 PR 评论（存库）
  - `GET /atomgit/pulls/{owner}/{repo}/{number}/reviews` - PR Reviews（存库）
  - `GET /atomgit/pulls/{owner}/{repo}/{number}/commits` - PR Commits（存库）
  - `GET /atomgit/pulls/{owner}/{repo}/{number}/files` - PR 变更文件（存库）
  - `GET /atomgit/pulls/{owner}/{repo}/{number}/timeline` - PR 时间线（存库）
  - `GET /atomgit/pulls/{owner}/{repo}/comments` - 批量获取评论（存库）
  - `GET /atomgit/pulls/{owner}/{repo}/comments/all` - **全量获取整个项目评论（存库）**
  - `GET /atomgit/pulls/{owner}/{repo}/details` - 并发获取多个 PR 详情（存库）
  - `GET /atomgit/pulls/{owner}/{repo}/reviews` - 并发获取多个 PR Reviews（存库）
  - `GET /atomgit/pulls/{owner}/{repo}/commits` - 并发获取多个 PR Commits（存库）
  - `GET /atomgit/pulls/{owner}/{repo}/files` - 并发获取多个 PR 变更文件（存库）
  - `GET /atomgit/pulls/{owner}/{repo}/timelines` - 并发获取多个 PR 时间线（存库）
  - `GET /atomgit/issues/{owner}/{repo}` - Issue 列表
  - `GET /atomgit/issues/{owner}/{repo}/{number}` - Issue 详情
- **全量获取参数**
  - `state=open/closed/all` - PR 状态
  - `max_prs=0` - 最大 PR 数（0=全部）
  - `skip_no_comments=true` - 跳过无评论 PR
- **验证数据**: cann/ge 项目 1838 个 PR, 30491 条评论, 17154 条 Bot 评论, 全部存库
- **测试**: [test_atomgit.py](app/test/test_atomgit.py) - 28 项测试（100% 通过）

### 20. 版本控制 ✅ (2026-05-18 新增)
- 补充 `.gitignore` 规则，添加 `backend/secrets/` 排除
- 从 Git 追踪中移除 `mongodb_root_password.txt` 敏感文件
- 标记版本控制需求全部完成

### 21. Docker 化部署 ✅ (2026-05-18 新增)
- **Dockerfile** [Dockerfile](Dockerfile)
  - 基于 `python:3.11-slim` 镜像
  - 安装 Playwright 所需系统依赖
  - 复制应用代码和示例配置
- **docker-compose.yml** 更新
  - 新增 `backend` 服务，依赖 `mongodb`
  - 通过 Docker Secrets 注入数据库密码
  - 通过环境变量传入数据库连接信息（`MONGODB_HOST`、`MONGODB_PASSWORD` 等）
  - 挂载 `config.json` 和 `encryption_key.json` 为只读卷
  - 日志和数据使用 Docker Volume 持久化
- **main.py** 修改
  - 数据库连接支持从环境变量读取（兼容 Docker 和本地运行）
  - 服务 host/port 支持从环境变量读取
- **使用方式**:
  ```bash
  docker-compose up -d       # 一键启动全套服务
  docker-compose logs -f backend  # 查看后端日志
  ```

---

## 待开发功能

- [ ] 28. 数据维度增强 — PR 关联分析、代码变更深度分析、贡献者画像、Issue 与 PR 联动
- [x] 28.2 代码变更深度分析 — 变更分类+阶段性洞察+自然语言摘要+阶段级diff/文件类型/贡献者+环比趋势 (2026-05-25)
- [x] 29.2 Review 质量评估 — 覆盖率/延迟/深度/状态分布/Top Reviewer/洞察 (2026-05-25)
- [ ] 29.1 代码质量指标 — 代码 churn 分析、技术债评估
- [x] 29.3 项目健康度评分 — 6维度加权评分/A-F评级/雷达图/趋势 (2026-05-25)
- [x] 29.4 趋势预警 — CI失败率/Review延迟/贡献者流失/PR存活时间 环比预警 (2026-05-25)
- [ ] 29.4 趋势预警 — CI 失败率/Review 延迟/贡献者流失预警
- [ ] 30. 平台与集成拓展 — Webhook 接收、通知推送、数据导出、多仓库对比
- [ ] 31. 前端可视化增强 — PR 生命周期桑基图、贡献者热力图、CI/CD 仪表盘
- [x] 31.4 代码变更热力图 — 文件/目录变更频率+热度+规模 (2026-05-25)
- [ ] 32. 前端交互增强 — 项目收藏与分组、自定义看板、时间范围选择器、深色模式
- [ ] 33. 前端协作增强 — 报告批注与分享、对比模式、Agent 对话增强

### 24. 多 Agent 协作系统 🚧 (2026-05-18 规划中)

#### 架构设计
```
                        ┌─────────────────┐
                        │  Orchestrator   │  调度 Agent (Claude)
                        │    Agent        │  理解意图 → 分解任务 → 调度 Agent → 汇总结果
                        └────────┬────────┘
                                 │
                 ┌───────────────┼───────────────┐
                 │               │               │
        ┌────────▼──┐   ┌───────▼──────┐  ┌──────▼───────┐
        │ Collector │   │   Analyst    │  │   Reporter   │
        │  Agent    │   │   Agent      │  │   Agent      │
        │           │   │              │  │              │
        │ Tools:    │   │ Tools:       │  │ Tools:       │
        │ fetch_prs │   │ analyze_cicd │  │ gen_stats    │
        │ fetch_cm  │   │ get_stats    │  │ ai_analyze   │
        │ fetch_det │   │ get_trends   │  │ ai_suggest   │
        │ fetch_rev │   │ get_failure  │  │ format_rpt   │
        │ check_db  │   │ query_detail │  │              │
        └───────────┘   └──────────────┘  └──────────────┘
```

#### 与当前架构对比
| 维度 | 当前 (Pipeline) | 目标 (Multi-Agent) |
|------|----------------|-------------------|
| 执行方式 | 固定 9 步线性 | Agent 自主决策 |
| AI 参与 | 最后 2 步 | 每步都有 AI 决策 |
| 工具调用 | 节点直接调服务 | Agent 通过 tool 自主选择 |
| 适应性 | 所有项目同流程 | 根据项目特征动态调整 |
| 可扩展性 | 加步骤需改图 | 加 tool 即可 |

#### 实施计划
- Phase 1: Agent 基类 + Collector Agent (最小可用) ✅
- Phase 2: Analyst Agent + Reporter Agent (核心能力) ✅
- Phase 3: Orchestrator + 图编排 (多 Agent 协作) ✅
- Phase 4: 通信协议 + API + 测试 ✅

#### Phase 1 完成 (2026-05-18)
- [base_agent.py](../workflow/agents/base_agent.py) - Agent 基类
  - `BaseAgent` 封装 `create_react_agent`，统一创建模式
  - `run(message)` / `run_with_context(message, context)` 执行方法
  - 工具注册 `_register_tools()` 子类重写
  - LLM 不可用时优雅降级
- [collector_agent.py](../workflow/agents/collector_agent.py) - Collector Agent
  - `CollectorAgent` 继承 `BaseAgent`
  - system prompt: 数据采集专家，含 3 级策略（小/中/大项目）
  - 6 个 LangChain Tool:
    - `fetch_pr_list` — 获取 PR 列表
    - `fetch_pr_comments` — 获取 PR 评论
    - `fetch_pr_details` — 获取 PR 详情
    - `fetch_pr_reviews` — 获取 PR Reviews
    - `check_db_cache` — 检查数据库缓存
    - `query_cicd_results` — 查询已有分析结果
- [test_agent_base.py](../workflow/tests/test_agent_base.py) - 14 项测试 (100% 通过)

#### Phase 2 完成 (2026-05-18)
- [analyst_agent.py](../workflow/agents/analyst_agent.py) - Analyst Agent
  - system prompt: CI/CD 工程效能分析专家，根据数据特征动态选择分析维度
  - 6 个 LangChain Tool:
    - `analyze_cicd_comments` — 从评论提取 CI/CD 结果
    - `get_cicd_stats` — 统计数据
    - `get_cicd_trends` — 趋势数据
    - `get_failure_analysis` — 失败分析
    - `query_pr_details` — PR 详情（辅助）
    - `query_pr_reviews` — Reviews（辅助）
- [reporter_agent.py](../workflow/agents/reporter_agent.py) - Reporter Agent
  - system prompt: 报告撰写专家，支持三级报告（执行摘要/技术详情/行动计划）
  - 5 个 LangChain Tool:
    - `generate_stats_report` — 规则引擎统计
    - `ai_generate_suggestions` — AI 改进建议
    - `ai_risk_assessment` — AI 风险评估
    - `format_report_md` — Markdown 格式化
    - `format_report_json` — JSON 验证
- [test_agent_phase2.py](../workflow/tests/test_agent_phase2.py) - 16 项测试 (100% 通过)

#### Phase 3 完成 (2026-05-18)
- [orchestrator_agent.py](../workflow/agents/orchestrator_agent.py) - Orchestrator Agent
  - system prompt: 总调度角色，按顺序调度 Collector → Analyst → Reporter
  - 3 个路由工具: delegate_to_collector/analyst/reporter
  - 错误处理: Agent 不可用时返回降级提示
- [agent_graphs.py](../workflow/agent_graphs.py) - 2 种图模式
  - `build_multi_agent_graph()`: Orchestrator 自主调度（单节点图，内部 tool_call 决策）
  - `build_sequential_agent_graph()`: 顺序 3 步（collector → analyst → reporter）
- [runner.py](../workflow/runner.py) - 新增 `run_multi_agent_analysis()` / `run_multi_agent_async()`
- [api/routes.py](../workflow/api/routes.py) - 新增 Agent API 端点:
  - `POST /agent/analyze` / `POST /agent/analyze/async`
  - `GET /agent/status/{task_id}` / `GET /agent/tasks`
- [test_agent_phase3.py](../workflow/tests/test_agent_phase3.py) - 11 项测试 (100% 通过)

#### Phase 4 完成 (2026-05-18)
- 对话式接口 `POST /agent/chat` — 支持多轮对话和追问
  - Orchestrator 复用实例，保留对话上下文
  - 支持 "深入分析失败原因" / "生成执行摘要版报告" 等追问
- PR Commits 接口 — 完整实现:
  - `fetch_pr_commits()` / `fetch_all_pr_commits()` 服务方法
  - `save_pr_commits()` / `get_pr_commits()` / `list_pr_commits()` 数据库持久化
  - `GET /github/prs/{owner}/{repo}/{pr_number}/commits` 路由
  - `GET /github/prs/{owner}/{repo}/commits` 批量路由
  - `GET /database/commits` 查询路由
- [test_phase4.py](../workflow/tests/test_phase4.py) - 11 项测试 (100% 通过)

#### Phase 5 增强 (2026-05-19)
- **BaseAgent 增强** [base_agent.py](../workflow/agents/base_agent.py)
  - 回调事件系统: `on_event()` 注册回调，支持 `started/tool_call/completed/failed/retry` 事件
  - 执行统计: `ExecutionStats` 记录每次运行的耗时、工具调用数、token 消耗
  - 自动重试: 可配置 `max_retries` 和 `retry_delay`，指数退避
  - Token 追踪: 从 LLM 响应提取 `usage_metadata`，统计 input/output tokens
  - 性能摘要: `get_performance_summary()` 返回平均耗时、成功率、总 token 数
  - `AgentRunResult` 增强返回结构，含 `stats`/`events`/`run_id`
- **Planner Agent** [planner_agent.py](../workflow/agents/planner_agent.py)
  - `analyze_project_profile()`: 分析项目画像（规模/缓存/平台），写入黑板
  - `create_execution_plan()`: 生成 DAG 执行计划，支持 full/quick/cicd_only/report_only
  - 自动识别可并行任务组，估算步骤数
  - 3 种项目规模策略: 小项目全量、中项目优先评论、大项目采样
- **Validator Agent** [validator_agent.py](../workflow/agents/validator_agent.py)
  - `validate_collected_data()`: 5 项数据完整性检查（PR/评论/CI/CD/统计/时效性）
  - `validate_analysis_quality()`: 分析质量评分（维度覆盖/评级合理性）
  - 完整度评分 0-100，低于 50% 建议重新采集
- **共享黑板** [blackboard.py](../workflow/agents/blackboard.py)
  - `SharedBlackboard`: Agent 间数据交换中心，支持发布/订阅模式
  - 数据类型分类: `COLLECTION_RESULT`/`ANALYSIS_RESULT`/`REPORT_RESULT`/`VALIDATION_RESULT`/`PLAN`/`METRICS`
  - 版本控制、TTL 过期清理、按键前缀/类型查询
  - 全局单例 `blackboard` 供所有 Agent 共享
- **洞察引擎** [insights_engine.py](../workflow/agents/insights_engine.py)
  - 独立于 backend `app` 模块，解决 `ModuleNotFoundError` 导入失败 bug
  - 复用评级逻辑（成功率 A-F、耗时 A-F、覆盖率 A-F）
  - 新增 `compute_overall_grade()` 综合评级
- **Orchestrator 增强** [orchestrator_agent.py](../workflow/agents/orchestrator_agent.py)
  - 新增工具: `delegate_to_planner`、`delegate_to_validator`、`get_blackboard_summary`、`check_agent_status`
  - 完整流程: Planner → Collector → Analyst → Validator → Reporter
  - 动态策略: 验证不通过时自动请求补充数据
- **Runner 增强** [runner.py](../workflow/runner.py)
  - 多会话管理: `create_session()`/`chat_in_session()`/`get_session()`/`list_sessions()`/`delete_session()`
  - 批量分析: `run_batch_analysis()` 支持并发分析多个项目
  - 事件订阅: `subscribe_task_events()` 支持 SSE 流式推送
  - Agent 状态: `get_all_agent_status()`/`get_blackboard_status()` 监控接口
- **API 增强** [routes.py](../workflow/api/routes.py)
  - `GET /agent/stream/{task_id}` — SSE 流式事件推送
  - `POST /agent/sessions` — 创建会话
  - `POST /agent/sessions/{id}/chat` — 会话内对话
  - `GET /agent/sessions` — 列出会话
  - `GET /agent/sessions/{id}` — 获取会话详情
  - `DELETE /agent/sessions/{id}` — 删除会话
  - `POST /agent/batch` — 批量分析
  - `GET /agent/agents/status` — Agent 状态监控
  - `GET /agent/blackboard` — 黑板状态查看
- **图增强** [agent_graphs.py](../workflow/agent_graphs.py)
  - 多 Agent 图: `planner → orchestrator → END`
  - 顺序 Agent 图: `planner → collector → analyst → validator → reporter → END`
  - 各节点自动将中间结果写入黑板
- [test_agent_enhanced.py](../workflow/tests/test_agent_enhanced.py) - 38 项测试 (100% 通过)

### 22. CI/CD 工程能力洞察报告 🚧 (2026-05-18 开始)

#### 22.1 CI/CD 结构化数据模型 ✅ (2026-05-18)
- [cicd_models.py](app/models/cicd_models.py) - CI/CD 结构化数据模型
  - `BuildStatus` - 7 种构建状态枚举，含自动标准化（succeeded→success 等）
  - `CICDResult` - 统一 7 种解析器输出的标准模型，支持 `to_db_dict()`
  - `CICDResultSummary` - 汇总统计（成功率/耗时分布/覆盖率）
  - `CICDTrendPoint` - 趋势数据点
  - `CICDFailureAnalysis` - 失败分析（高频失败 job、MTTR）
  - `CICDInsight` - 洞察项（指标值+评级 A-F+建议）
  - `CICDReport` - 项目级完整报告
- [test_cicd_models.py](app/test/test_cicd_models.py) - 13 项模型验证测试（100% 通过）

#### 22.2 CI/CD 数据持久化 ✅ (2026-05-18)
- [database_service.py](app/services/database_service.py) - 新增 cicd_results 集合操作:
  - `save_cicd_result()` - 保存单条结果（按 comment_id 去重 upsert）
  - `save_cicd_results_batch()` - 批量保存
  - `query_cicd_results()` - 多条件查询（项目/PR/状态/解析器/时间范围，分页排序）
- [cicd_extractor.py](app/analysis/cicd_extractor.py) - 新增结构化提取方法:
  - `extract_structured()` - 从评论提取返回 `CICDResult` 模型
  - `extract_batch_structured()` - 批量结构化提取

#### 22.3 CI/CD 统计分析服务 ✅ (2026-05-18)
- [database_service.py](app/services/database_service.py) - 新增聚合查询:
  - `get_cicd_summary_from_db()` - 成功率/耗时/覆盖率/按解析器统计
  - `get_cicd_trends_from_db()` - 按日/周/月聚合趋势数据
  - `get_cicd_failure_analysis_from_db()` - 失败分析（高频失败 job、按解析器失败统计）
  - `_compute_mttr()` - MTTR 平均修复时间（按 PR 分组，failed→success 时间差）

#### 22.4 CI/CD 洞察报告 API ✅ (2026-05-18)
- [analysis.py](app/api/routers/analysis.py) - 新增 5 个 API 端点:
  - `POST /analysis/cicd/analyze/{owner}/{repo}` - 触发全量分析（从评论库解析并入库）
  - `GET /analysis/cicd/report/{owner}/{repo}` - 获取项目级洞察报告（含评级建议）
  - `GET /analysis/cicd/stats/{owner}/{repo}` - 获取统计数据
  - `GET /analysis/cicd/trends/{owner}/{repo}` - 获取趋势数据（支持 day/week/month）
  - `GET /analysis/cicd/results/{owner}/{repo}` - 查询 CI/CD 结果（分页）
- 洞察评级引擎: 构建成功率/耗时/覆盖率自动评级（A-F）+ 改进建议

#### 22.5 测试用例 ✅ (2026-05-18)
- [test_cicd_models.py](app/test/test_cicd_models.py) - 13 项模型验证测试（100% 通过）
- [test_cicd_analysis.py](app/test/test_cicd_analysis.py) - 19 项分析测试（100% 通过）
  - 结构化提取（NVIDIA CCCL/Rust Bors/非 CI/CD/批量）
  - 持久化 Mock（save/query/batch/数据库未连接）
  - 统计服务 Mock（summary/failure_analysis/trends）
  - 洞察评级（成功率/耗时/覆盖率 A-F + 高频失败 Job）
  - 统计模型（比率计算/零值处理）
- [test_cicd_api.py](app/test/test_cicd_api.py) - 10 项 API 集成测试（100% 通过）
  - TestClient + Mock 数据库端到端测试
  - POST /analyze 触发分析
  - GET /report 洞察报告（含日期范围、评级验证）
  - GET /stats 统计数据
  - GET /trends 趋势数据（day/week/month）
  - GET /results 结果查询（PR 过滤）
  - 数据库未连接 503 错误处理

### 23. PR Reviews 接口 ✅ (2026-05-18 新增)
- [github_service.py](app/services/github_service.py) - 新增方法:
  - `fetch_pr_reviews()` - 获取单个 PR 的所有 Reviews（分页）
  - `fetch_all_pr_reviews()` - 并发获取多个 PR 的 Reviews
- [database_service.py](app/services/database_service.py) - 新增 pr_reviews 集合:
  - `save_pr_reviews()` - 保存 Reviews（upsert 去重）
  - `get_pr_reviews()` - 获取单个 PR Reviews
  - `list_pr_reviews()` - 分页查询 Reviews
- [github.py](app/api/routers/github.py) - 新增接口:
  - `GET /github/prs/{owner}/{repo}/{pr_number}/reviews` - 获取单个 PR Reviews
  - `GET /github/prs/{owner}/{repo}/reviews` - 并发获取所有 PR Reviews
- [database.py](app/api/routers/database.py) - 新增接口:
  - `GET /database/reviews` - 查询 Reviews（分页）
- [test_pr_reviews.py](app/test/test_pr_reviews.py) - 12 项测试（100% 通过）
  - 服务层: 数据格式、分页、错误处理
  - 数据库: save/get/list、未连接处理
  - API: 单PR/全量/数据库查询/503/字段完整性

#### Phase 6 深度优化 (2026-05-19)
- **AgentRegistry** [registry.py](../workflow/agents/registry.py)
  - 统一 Agent 注册/发现/生命周期管理，替代分散的 `_agents` 字典
  - 延迟实例化、热替换（切换 LLM 后重建）、按标签查找
  - 调用次数/错误率/最后使用时间监控
  - `register_defaults()` 一键注册 6 个内置 Agent
- **ArtifactStore** [artifact_store.py](../workflow/agents/artifact_store.py)
  - 分析产物存储和版本管理（计划/报告/统计/验证结果）
  - 按项目索引、内容哈希去重、快照导出
  - `is_changed()` 增量检测、`snapshot()` 导出、`query_by_type()` 按类型查询
- **TraceManager** [tracer.py](../workflow/agents/tracer.py)
  - 全链路追踪: 每次 trace_id 贯穿所有 Agent
  - TraceSpan 记录每个 Agent 的耗时/token/工具调用/错误
  - 按项目查看历史、JSON 导出、自动清理超限 trace
- **CostController** [cost_controller.py](../workflow/agents/cost_controller.py)
  - Token 预算控制: 总预算/使用量/超限告警/硬限制
  - LLM 分层策略: premium/standard/economy 三级模型
  - 预算紧张时自动降级（80% 降一级，95% 强制 economy）
  - 成本估算、用量报告（按 Agent 分项统计费用）
- **Collector 增强** [collector_tools.py](../workflow/agents/collector_tools.py)
  - `incremental_fetch()`: 增量采集，只拉取新 PR 数据（对比已有缓存）
  - `parallel_fetch()`: 并发拉取多种数据类型（ThreadPoolExecutor 4 workers）
  - Collector Agent 工具数从 6 → 8
- **Reporter 增强** [reporter_tools.py](../workflow/agents/reporter_tools.py)
  - `format_report_html()`: HTML 格式化报告，带 CSS 样式、表格、评级徽章
  - Markdown 格式增强: 综合评级徽章、分项评级表格、Top5 失败 Job
  - Reporter Agent 工具数从 5 → 6
- **新增 API 端点**:
  - `GET /agent/traces` — 列出执行追踪
  - `GET /agent/traces/{trace_id}` — 追踪详情
  - `GET /agent/traces/project/{owner}/{repo}` — 项目追踪历史
  - `GET /agent/cost` — 成本报告
  - `GET /agent/artifacts/{owner}/{repo}` — 分析产物
  - `GET /agent/artifacts/{owner}/{repo}/snapshot` — 产物快照
- [test_phase6.py](../workflow/tests/test_phase6.py) - 40 项测试 (100% 通过)
---

## 测试结果

```
总测试数: 179 (安全加固: 40 + Phase 6: 40 + Phase 5 增强: 38 + Phase 1-4: 52 + AI Nodes: 9)
✅ 通过: 179
❌ 失败: 0
通过率: 100%
```

---

## 最后更新时间

2026-05-27 (自动恢复机制完成)

> 将全量同步 I/O 改造为原生异步，充分利用 FastAPI 异步特性

#### 26.1 核心变更
- **依赖替换**
  - `requests` → `httpx`（异步 HTTP 客户端）
  - `pymongo.MongoClient` → `motor.AsyncIOMotorClient`（异步 MongoDB 驱动）
  - `ThreadPoolExecutor` → `asyncio.gather` + `asyncio.Semaphore`
  - `threading.Lock` → `asyncio.Lock`
  - `time.sleep()` → `await asyncio.sleep()`

#### 26.2 服务层改造
- [base_service.py](app/services/base_service.py) — 异步公共组件
  - `retry_on_failure` → async 装饰器
  - `TokenPool` → asyncio.Lock
  - `TaskProgress` → asyncio.Lock
- [github_service.py](app/services/github_service.py) — GitHub 服务异步化
  - `httpx.AsyncClient` 替代 `requests`
  - 所有 `fetch_*` 方法 → `async def`
  - `asyncio.gather` + `Semaphore` 替代 ThreadPoolExecutor
  - 新增 `_get_client()` 和 `async def close()` 生命周期管理
- [database_service.py](app/services/database_service.py) — 数据库服务异步化
  - `motor.AsyncIOMotorClient` 替代 `pymongo.MongoClient`
  - 所有集合操作添加 `await`
  - `list(cursor)` → `await cursor.to_list(length=None)`
  - `aggregate` 使用 `async for` 或 `.to_list()`
- [gitcode_service.py](app/services/gitcode_service.py) — GitCode 服务异步化
  - 同 GitHub 服务模式改造
- [app/gitcode/service.py](app/gitcode/service.py) — AtomGit 服务异步化
  - httpx + async 方法

#### 26.3 路由层适配
- 所有 9 个路由模块添加 `await`：
  - [github.py](app/api/routers/github.py) — ThreadPoolExecutor → asyncio.gather + Semaphore
  - [database.py](app/api/routers/database.py) — 所有 db.* 调用添加 await
  - [gitcode.py](app/api/routers/gitcode.py) — 所有服务调用添加 await
  - [analysis.py](app/api/routers/analysis.py) — db 调用 await + 直接 pymongo 改为 motor 异步操作
  - [task.py](app/api/routers/task.py) — task_progress_manager + db 调用 await
  - [atomgit.py](app/api/routers/atomgit.py) — AtomGit 服务 + db 调用 await
  - [config.py](app/api/routers/config.py) — 无需修改（仅调用同步 config_manager）
  - [base.py](app/api/routers/base.py) — 无需修改（纯返回）
  - [browser.py](app/api/routers/browser.py) — 已是 async，无需修改

#### 26.4 主应用改造
- [main.py](app/main.py) — 使用 FastAPI `lifespan` 异步上下文管理器
  - 数据库连接/断开放入 lifespan（异步 `await db.connect()` / `await db.disconnect()`）
  - HTTP 客户端关闭放入 lifespan（`await github_service.close()`）
  - 移除模块级 `db.connect()` 同步调用
  - 移除 `signal_handler` 中的同步 `db.disconnect()`

#### 26.5 requirements.txt 更新
- `requests>=2.31.0` → `httpx>=0.27.0`
- 新增 `motor>=3.3.0`

---

### 25. 安全加固 ✅ (2026-05-20 新增)

#### 25.1 安全模块 [core/security.py](app/core/security.py)
- **API Key 认证 (`APIKeyAuth`)**
  - 支持请求头 `X-API-Key`、查询参数 `api_key`、`Authorization: Bearer` 三种方式传递 Key
  - 支持简单字符串格式和详细对象格式（含 name/enabled）的 API Key 配置
  - 公共路径（`/`、`/health`、`/docs`、`/openapi.json` 等）免认证
  - 认证失败返回 401 + `WWW-Authenticate` 响应头
  - 通过 `security.auth_enabled` 配置开关，默认关闭（向后兼容）
- **请求限流 (`RateLimiter`)**
  - 基于 IP 的滑动窗口限流算法（内存存储，线程安全）
  - 全局默认 60 次/分钟，写入类路径严格限制 20 次/分钟
  - 支持 `X-Forwarded-For` / `X-Real-IP` 代理头获取真实 IP
  - 超限返回 429 + `Retry-After` 头
  - 自动清理过期记录防止内存泄漏
- **安全响应头 (`SecurityHeadersConfig`)**
  - 6 项安全头: `X-Content-Type-Options`、`X-Frame-Options`、`X-XSS-Protection`、`Strict-Transport-Security`、`Content-Security-Policy`、`Referrer-Policy`
  - 支持自定义头和覆盖默认头
- **日志脱敏工具**
  - `mask_token()` — Token/Key 脱敏（保留前后 4 位）
  - `mask_password()` — 密码脱敏（仅显示长度）
  - `mask_url_params()` — URL 敏感查询参数脱敏
  - `mask_dict()` — 字典敏感字段批量脱敏
- **Git 安全检查 (`run_security_check()`)**
  - 启动时自动扫描 Git 追踪文件，检测敏感文件泄露
- **统一安全中间件 (`SecurityMiddleware`)**
  - 整合认证 → 限流 → 安全头注入的完整请求处理链路
  - 附加 `X-RateLimit-Limit` / `X-RateLimit-Remaining` 响应头

#### 25.2 CORS 安全加固
- [main.py](app/main.py) — CORS 白名单从 `config.json` 的 `cors.allow_origins` 读取
- 替代硬编码 `["*"]`，支持字符串和数组两种配置格式
- 生产环境可配置具体域名白名单

#### 25.3 配置更新
- [config.example.json](config.example.json) — 新增 `security` 配置节:
  - `auth_enabled` + `api_keys` — API Key 认证配置
  - `rate_limit` — 限流配置（窗口、上限、严格路径）
  - `security_headers` — 安全响应头开关 + 自定义头
- [config.example.json](config.example.json) — 修复 CORS 配置键名 `Gallow_origins` → `allow_origins`

#### 25.4 Git 安全增强
- [.gitignore](../.gitignore) — 增强:
  - 新增 `.env.production`、`.env.staging` 环境文件排除
  - 新增 TLS 证书/私钥文件模式（`*.pem`、`*.key`、`*.crt`、`*.p12` 等）
  - 新增 SSH 密钥、Java Keystore、云服务凭证文件排除
  - 新增 `secrets/` 顶层目录排除

#### 25.5 测试用例 [test_security.py](app/test/test_security.py)
- 40 项测试（100% 通过）:
  - 日志脱敏: 10 项（Token/密码/URL参数/字典脱敏各种边界情况）
  - API Key 认证: 11 项（启用/关闭/公共路径/请求头/查询参数/Bearer/无效/缺失/禁用Key/多Key）
  - 请求限流: 9 项（关闭/正常/超限/剩余计数/不同IP/严格路径/429响应/清理/代理IP）
  - 安全响应头: 4 项（默认/关闭/自定义/覆盖）
  - Git 安全检查: 1 项
   - 集成测试: 5 项（认证拒绝/通过/组合/公共路径/文档资源）

---

### 29.2 Review 质量评估 ✅ (2026-05-25 新增)

#### 29.2.1 Response 模型 [responses.py](app/models/responses.py)
- `ReviewCoverageMetrics` — 覆盖率指标（total_prs/prs_with_review/coverage_rate/avg_reviewers_per_pr）
- `ReviewDelayMetrics` — 延迟指标（avg/median/p90 首次 review 延迟）
- `ReviewDepthMetrics` — 深度指标（avg_body_length/reviews_with_body/body_rate）
- `ReviewStateDistribution` — 状态分布（APPROVED/CHANGES_REQUESTED/COMMENTED/DISMISSED/PENDING）
- `ReviewerStats` — 单个 Reviewer 统计（review_count/approved_count/avg_body_length/avg_delay_hours）
- `ReviewQualityReport` — 完整报告模型
- `ReviewQualityTrendsResponse` — 趋势响应模型

#### 29.2.2 数据库服务层 [database_service.py](app/services/database_service.py)
- `get_review_quality_report()` — 生成完整 Review 质量评估报告
- `_compute_review_coverage()` — Review 覆盖率聚合（pr_details + pr_reviews 跨集合）
- `_compute_review_delay()` — Review 延迟统计（首次/中位/P90/平均延迟）
- `_compute_review_depth()` — Review 深度统计（body 长度/有内容占比）
- `_compute_review_state_distribution()` — Review 状态分布（APPROVED/CHANGES_REQUESTED 等）
- `_compute_top_reviewers()` — Top Reviewer 统计（review 数/approved 数/changes_requested 数）
- `_build_review_quality_insights()` — 洞察项构建（覆盖率/延迟/深度/变更请求率）
- `_grade_review_coverage()` / `_grade_review_delay()` / `_grade_review_depth()` — A-F 评级函数
- `get_review_quality_trends()` — Review 质量趋势数据（按日/周/月聚合）

#### 29.2.3 API 路由 [analysis.py](app/api/routers/analysis.py)
- `GET /analysis/review-quality/{owner}/{repo}` — Review 质量评估报告
  - 参数: start_date, end_date, top_n
  - 返回: 覆盖率 + 延迟 + 深度 + 状态分布 + Top Reviewer + 洞察项
- `GET /analysis/review-quality/{owner}/{repo}/trends` — Review 质量趋势
  - 参数: granularity (day/week/month), start_date, end_date

#### 29.2.4 测试用例 [test_review_quality.py](app/test/test_review_quality.py)
- 14 项测试（100% 通过）:
  - API 集成: 11 项（报告端点/日期范围/top_n/覆盖率/延迟/深度/状态分布/洞察/趋势/粒度/503）
  - 评级函数: 3 项（覆盖率/延迟/深度 A-F 评级）

---

## 30.2 通知推送 (2026-05-26)

- [x] 邮件通知 — aiosmtplib 异步 SMTP 发送
- [x] 飞书/钉钉/Slack 通知 — httpx 异步 Webhook 调用
- [x] 通知规则配置 — 按项目/指标/阈值/操作符配置触发条件
- [x] 通知管理 API — CRUD + 测试发送 + 历史查询

### 30.2.1 核心引擎 [notification.py](app/core/notification.py)
- `NotificationEngine` — 通知引擎（全局单例）
- `_send_email()` — aiosmtplib 异步邮件发送
- `_send_feishu()` — 飞书 Bot Webhook（Interactive Card）
- `_send_dingtalk()` — 钉钉 Bot Webhook（Markdown + HMAC 签名）
- `_send_slack()` — Slack Incoming Webhook（Block Kit）
- `evaluate_and_notify()` — 规则匹配 + 多渠道发送 + 历史记录
- `_evaluate_rules()` — 项目/指标/阈值规则匹配引擎

### 30.2.2 数据库服务 [database_service.py](app/services/database_service.py)
- `save/update/delete/list/get_notification_config()` — 配置 CRUD
- `save/list_notification_history()` — 历史记录管理

### 30.2.3 API 路由 [notifications.py](app/api/routers/notifications.py)
- `POST /notifications/config` — 创建通知配置
- `PUT /notifications/config/{config_id}` — 更新通知配置
- `DELETE /notifications/config/{config_id}` — 删除通知配置
- `GET /notifications/config` — 获取所有通知配置
- `POST /notifications/config/{config_id}/test` — 测试发送
- `GET /notifications/history` — 查询通知历史（分页）

### 30.2.4 前端页面
- `NotificationConfig.jsx` — 通知规则配置页（表单 + 动态规则列表）
- `NotificationHistory.jsx` — 通知历史记录页（分页列表 + 筛选）

---

## 30.3 数据导出 (2026-05-26)

- [x] 报告导出 PDF — reportlab 生成结构化 PDF（支持中文）
- [x] 报告导出 Excel — openpyxl 多 Sheet 导出（自动列宽）
- [x] 数据批量导出 CSV — csv 模块（utf-8-sig 编码）
- [x] 导出 API — FileResponse 流式下载

### 30.3.1 核心引擎 [exporter.py](app/core/exporter.py)
- `ReportExporter` — 导出引擎
- `export_csv()` — CSV 导出（嵌套文档展平）
- `export_excel()` — Excel 多 Sheet 导出（自动列宽调整）
- `export_pdf()` — PDF 报告生成（健康度/Review/预警/通用模板）
- `_cleanup_old_exports()` — 自动清理 24 小时前的导出文件

### 30.3.2 API 路由 [export.py](app/api/routers/export.py)
- `GET /export/report/{owner}/{repo}?format=pdf|excel` — 报告导出
- `GET /export/data/{owner}/{repo}?collection=...&format=excel|csv` — 原始数据导出

### 30.3.3 前端页面
- `DataExport.jsx` — 数据导出页（报告导出 + 原始数据导出）
---

## 30.1 Webhook 接收 (2026-05-26)

- [x] GitHub Webhook 接收 — 监听 push/pull_request/pull_request_review/issues 事件
- [x] GitCode Webhook 接收 — 监听 merge_request 事件
- [x] Webhook 签名验证 — HMAC-SHA256（GitHub）/ Token 对比（GitCode）
- [x] 实时增量更新 — 事件触发后自动增量拉取 PR 详情/评论/Reviews
- [x] Webhook 管理 API — 配置 CRUD + 事件日志查询

### 30.1.1 核心引擎 [webhook.py](app/core/webhook.py)
- `WebhookHandler` — Webhook 处理器（签名验证 + 事件分发 + 增量更新）
- `verify_github_signature()` — HMAC-SHA256 签名验证
- `verify_gitcode_signature()` — X-Gitlab-Token 验证
- `handle_github_event()` — GitHub 事件分发（PR/Review/Push/Issues）
- `handle_gitcode_event()` — GitCode MR 事件处理
- `_on_pr_event()` — 增量更新 PR 详情 + 评论 + Reviews
- `_on_review_event()` — 增量更新 Reviews
- `_on_issue_event()` — 增量更新 Issues

### 30.1.2 API 路由 [webhooks.py](app/api/routers/webhooks.py)
- `POST /webhooks/github` — GitHub Webhook 接收
- `POST /webhooks/gitcode` — GitCode Webhook 接收
- `GET /webhooks/events` — 事件日志查询（分页）
- `GET /webhooks/config` — 获取配置
- `PUT /webhooks/config` — 更新配置

### 30.1.3 前端页面
- `WebhookManager.jsx` — Webhook 配置 + 事件日志页

---

## 30.4 多仓库对比 (2026-05-26)

- [x] 同组织多项目横向对比 — 按健康度/CI成功率/Review覆盖率等维度对比
- [x] 跨项目贡献者重叠分析 — 识别跨项目贡献者
- [x] 对比看板 API — 同步返回对比结果

### 30.4.1 数据库服务 [database_service.py](app/services/database_service.py)
- `compare_projects()` — 多项目横向对比（并发获取健康度 + 维度排名 + 雷达图数据）
- `_build_comparison()` — 对比数据构建（维度排名 + 雷达图）
- `get_contributors_overlap()` — 跨项目贡献者重叠分析

### 30.4.2 API 路由 [compare.py](app/api/routers/compare.py)
- `POST /analysis/compare` — 多项目横向对比
- `GET /analysis/compare/contributors-overlap` — 贡献者重叠分析

### 30.4.3 前端页面
- `ProjectCompare.jsx` — 多仓库对比看板（雷达图 + 排名表 + 贡献者重叠）
