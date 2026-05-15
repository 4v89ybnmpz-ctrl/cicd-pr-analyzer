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
- [ ] 自动恢复机制 - 检测到卡死时自动重启服务

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
<!-- - [ ] CI/CD 数据结构化 - 将 CI/CD 评论转换为结构化数据
- [ ] CI/CD 结果统计接口 - 提供构建成功率、平均耗时等统计
- [ ] 数据分析结果存储 - 将分析结果存入数据库 -->

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

## 待开发功能
- [x] 建立脚本获取 openlibing.com 流水线数据（已通过浏览器自动化模块 + AtomGit 评论提取实现）
<!-- - [ ] PR Reviews 接口 - 获取评审记录
- [ ] PR Commits 接口 - 获取提交记录 -->