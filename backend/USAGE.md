# GitHub PR 获取工具 - 使用手册

> 本文档描述项目所有功能的使用方法，包括 API 接口、命令行脚本和数据分析功能

---

## 一、服务启动

```bash
# 启动服务
cd backend
python main.py

# 服务默认地址
http://127.0.0.1:1234

# 健康检查
curl http://127.0.0.1:1234/health
```

---

## 二、GitHub PR 数据获取

### 2.1 获取 PR 列表

```bash
# 获取 PR 列表（默认缓存）
curl "http://127.0.0.1:1234/github/prs/NVIDIA/cccl"

# 强制刷新（不使用缓存）
curl "http://127.0.0.1:1234/github/prs/NVIDIA/cccl?use_cache=false"

# 限制获取数量（避免大仓库全量分页）
curl "http://127.0.0.1:1234/github/prs/rust-lang/rust?limit=500"
```

### 2.2 获取 PR 评论

```bash
# 获取所有 PR 的评论（limit 控制PR数量）
curl "http://127.0.0.1:1234/github/prs/NVIDIA/cccl/comments?limit=10"

# 获取单个 PR 的评论
curl "http://127.0.0.1:1234/github/prs/NVIDIA/cccl/123/comments"
```

### 2.3 获取 PR 详细信息

```bash
# 单个 PR 详情
curl "http://127.0.0.1:1234/github/prs/NVIDIA/cccl/123/detail"

# 批量获取详情
curl -X POST "http://127.0.0.1:1234/github/prs/detail/batch" \
  -H "Content-Type: application/json" \
  -d '{"owner":"NVIDIA","repo":"cccl","pr_numbers":[1,2,3]}'

# 所有 PR 详情
curl "http://127.0.0.1:1234/github/prs/NVIDIA/cccl/details"
```

### 2.4 获取 PR 时间线

```bash
curl "http://127.0.0.1:1234/github/prs/NVIDIA/cccl/timeline?limit=10"
```

### 2.5 批量与异步获取

```bash
# 批量获取多个项目
curl -X POST "http://127.0.0.1:1234/github/prs/batch" \
  -H "Content-Type: application/json" \
  -d '{"projects":[{"owner":"NVIDIA","repo":"cccl"},{"owner":"rust-lang","repo":"rust"}]}'

# 异步批量获取
curl -X POST "http://127.0.0.1:034/github/prs/batch-async" \
  -H "Content-Type: application/json" \
  -d '{"projects":[{"owner":"NVIDIA","repo":"cccl"}]}'
```

---

## 三、AtomGit/GitCode PR 数据获取

> 通过 AtomGit API v5 获取 GitCode 平台的 PR 评论数据，支持自动存库

### 3.1 获取 PR 列表

```bash
curl "http://127.0.0.1:1234/atomgit/pulls/cann/ge?state=all&page=1&size=20"
```

### 3.2 获取单个 PR 评论

```bash
# 获取评论并自动保存到数据库
curl "http://127.0.0.1:1234/atomgit/pulls/cann/ge/1840/comments"
```

### 3.3 批量获取评论

```bash
# 获取最近 10 个 PR 的评论并保存到数据库
curl "http://127.0.0.1:1234/atomgit/pulls/cann/ge/comments?limit=10&state=all"
```

### 3.4 全量获取整个项目评论

```bash
# 获取全部 PR 评论并保存到数据库
curl "http://127.0.0.1:1234/atomgit/pulls/cann/ge/comments/all"

# 限制最大 PR 数量
curl "http://127.0.0.1:1234/atomgit/pulls/cann/ge/comments/all?max_prs=50"

# 只获取 open 状态，跳过无评论的 PR
curl "http://127.0.0.1:1234/atomgit/pulls/cann/ge/comments/all?state=open&skip_no_comments=true"

# 不跳过无评论 PR（确保不遗漏）
curl "http://127.0.0.1:1234/atomgit/pulls/cann/ge/comments/all?skip_no_comments=false"
```

**参数说明：**

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `state` | `all` | PR 状态：`open`/`closed`/`all` |
| `max_prs` | `0` | 最大 PR 数量，`0` 表示全部 |
| `skip_no_comments` | `true` | 跳过无评论的 PR |

### 3.5 命令行脚本

```bash
# 直接运行脚本（不通过 API）
cd backend
python -m app.gitcode.fetch_comments cann ge --limit 10

# 保存结果到 JSON 文件
python -m app.gitcode.fetch_comments cann ge --limit 50 --save

# 指定 Token
GITCODE_TOKEN=xxx python -m app.gitcode.fetch_comments cann ge --limit 10
```

### 3.6 流水线信息自动提取

Bot 评论中的 openlibing.com 流水线信息会被自动提取：

```json
{
  "pipeline_info": {
    "platform": "openlibing",
    "pipeline_id": "8033cdebd5e5420e9165181589392a80",
    "pipeline_run_id": "6db17973732944a699684c12a990544a",
    "project_name": "CANN",
    "tasks": [
      {"name": "Check_Pr", "status": "success", "result": "SUCCESS"},
      {"name": "Compile_X86_compiler", "status": "failed", "result": "FAILED"}
    ]
  }
}
```

---

## 四、GitCode (GitLab API) 数据获取

> 需要有效的 GitCode Token，在 `config.json` 的 `gitcode_tokens` 中配置

```bash
# 获取 MR 列表
curl "http://127.0.0.1:1234/gitcode/mrs/mindspore/mindspore?state=all&page=1&size=20"

# 获取 MR 评论
curl "http://127.0.0.1:1234/gitcode/mrs/mindspore/mindspore/123/comments"

# 获取 MR 详情
curl "http://127.0.0.1:1234/gitcode/mrs/mindspore/mindspore/123/detail"

# 获取 MR 代码变更
curl "http://127.0.0.1:1234/gitcode/mrs/mindspore/mindspore/123/changes"

# 批量获取所有 MR 评论
curl "http://127.0.0.1:1234/gitcode/mrs/mindspore/mindspore/comments?limit=10"
```

---

## 五、数据库查询

### 5.1 统计信息

```bash
# 数据库统计
curl "http://127.0.0.1:1234/database/stats"

# 聚合统计
curl "http://127.0.0.1:1234/database/aggregate"
```

### 5.2 查询 PR 数据

```bash
# 列出所有 PR
curl "http://127.0.0.1:1234/database/prs"

# 查询指定仓库 PR
curl "http://127.0.0.1:1234/database/prs/NVIDIA/cccl"

# 删除指定仓库数据
curl -X DELETE "http://127.0.0.1:1234/database/prs/NVIDIA/cccl"
```

### 5.3 查询评论

```bash
# 查询评论（支持分页、筛选）
curl "http://127.0.0.1:1234/database/comments?owner=NVIDIA&repo=cccl&limit=20"

# 查询 rust-lang/rust 评论
curl "http://127.0.0.1:1234/database/comments?owner=rust-lang&repo=rust&limit=20"

# 查询 cann/ge 评论（AtomGit 数据）
curl "http://127.0.0.1:1234/database/comments?owner=cann&repo=ge&limit=20"
```

### 5.4 查询详情与时间线

```bash
# PR 详情
curl "http://127.0.0.1:1234/database/details?owner=NVIDIA&repo=cccl&limit=10"

# 模糊搜索
curl "http://127.0.0.1:1234/database/details/search?keyword=fix&owner=NVIDIA&repo=cccl"

# PR 时间线
curl "http://127.0.0.1:12334/database/timeline?owner=NVIDIA&repo=cccl&limit=10"
```

---

## 六、数据分析

### 6.1 数据清洗

```python
from app.analysis import DataCleaner

cleaner = DataCleaner()

# 清洗单条评论
cleaned = cleaner.clean_comment(comment)

# 批量清洗
cleaned_list = cleaner.clean_comments_batch(comments)

# 提取元数据
metadata = cleaner.extract_comment_metadata(comment)

# 过滤有效评论
valid = cleaner.filter_valid_comments(comments)
```

### 6.2 CI/CD 评论识别与提取

```python
from app.analysis import CICDExtractor

extractor = CICDExtractor()

# 判断是否为 CI/CD 评论
is_cicd = extractor.is_cicd_comment(comment)

# 提取 CI/CD 结果（自动匹配解析器）
result = extractor.extract(comment, owner="rust-lang", repo="rust")

# 批量提取
results = extractor.extract_batch(comments, owner="NVIDIA", repo="cccl")

# 汇总统计
summary = extractor.get_cicd_summary(comments, owner="NVIDIA", repo="cccl")
```

### 6.3 解析器架构

**匹配优先级：**
1. 项目精确映射 `owner/repo` → 指定解析器
2. 通配符映射 `owner/*` → 指定解析器
3. 自动检测 `can_parse()` 内容匹配
4. 通用兜底 `generic`

**已实现的解析器：**

| 解析器 | 优先级 | 来源 | 适用项目 |
|--------|--------|------|----------|
| rust-bors | 8 | Python 类 | rust-lang/rust |
| flutter-luci | 9 | JSON 规则 | flutter/* |
| nvidia-cccl | 10 | Python 类 | NVIDIA/cccl |
| jenkins-ci | 15 | JSON 规则 | 使用 Jenkins 的项目 |
| zuul-ci | 15 | JSON 规则 | OpenStack 项目 |
| github-actions | 20 | Python 类 | GitHub Actions 项目 |
| generic | 100 | Python 类 | 兜底 |

### 6.4 新项目接入

**方式一：JSON 规则（格式简单）**

编辑 `backend/app/analysis/parsers/parser_rules.json`：

```json
{
  "rules": [
    {
      "name": "my-project-ci",
      "priority": 12,
      "match_projects": ["my-org/*"],
      "match_users": ["my-ci-bot"],
      "match_patterns": ["pipeline.*completed"],
      "status_rules": {
        "success": ["passed", "SUCCESS"],
        "failed": ["failed", "FAILED"]
      },
      "extract_rules": {
        "url": "https?://[^\\s]+",
        "duration": "(\\d+h\\s*\\d*m\\s*\\d*s)"
      }
    }
  ]
}
```

**方式二：Python Parser 类（格式复杂）**

```python
from app.analysis.parsers.base_parser import BaseCICDParser

class MyProjectParser(BaseCICDParser):
    name = "my-project"
    priority = 12

    def can_parse(self, body, user=""):
        return "my-ci" in body.lower()

    def parse(self, body, user=""):
        # 自定义解析逻辑
        return {"parser": self.name, "build_status": "success"}
```

然后在 `parsers/__init__.py` 中注册。

---

## 七、浏览器自动化（内部平台）

> 用于抓取需要登录的内部 CI/CD 平台（如 openlibing.com）

### 7.1 API 接口

```bash
# 查看服务状态
curl "http://127.0.0.1:1234/browser/status"

# 启动浏览器
curl -X POST "http://127.0.0.1:1234/browser/initialize"

# 列出支持的平台
curl "http://127.0.0.1:1234/browser/platforms"

# 抓取流水线数据
curl -X POST "http://127.0.0.1:1234/browser/fetch-pipeline" \
  -d 'platform=openlibing' \
  -d 'pipeline_id=8033cdebd5e5420e9165181589392a80' \
  -d 'pipeline_run_id=4ddba58b78e04ccbbd2fd34e9a05c6fe' \
  -d 'project_id=300033' \
  -d 'username=YOUR_USERNAME' \
  -d 'password=YOUR_PASSWORD'

# 查看拦截到的请求
curl "http://127.0.0.1:1234/browser/captured-requests"

# 关闭浏览器
curl -X POST "http://127.0.0.1:1234/browser/shutdown"
```

### 7.2 Python 调用

```python
from app.browser import BrowserManager, NetworkInterceptor, AuthManager
from app.browser.service import BrowserScrapingService

service = BrowserScrapingService()
await service.initialize()

result = await service.fetch_pipeline_data(
    platform="openlibing",
    pipeline_id="8033cdebd5e5...",
    pipeline_run_id="4ddba58b...",
    username="xxx", password="xxx"
)

await service.shutdown()
```

---

## 八、配置管理

### 8.1 查看与重载配置

```bash
# 查看当前配置
curl "http://127.0.0.1:1234/config"

# 热更新配置
curl -X POST "http://127.0.0.1:1234/config/reload"
```

### 8.2 缓存管理

```bash
# 缓存统计
curl "http://127.0.0.1:1234/cache/stats"

# 清除缓存
curl -X DELETE "http://127.0.0.1:1234/cache/clear"
```

### 8.3 Token 管理

```bash
# 查看 Token 池状态
curl "http://127.0.0.1:1234/github/token-pool"
```

---

## 九、服务监控

```bash
# 监控状态
curl "http://127.0.0.1:1234/monitor/status"
```

返回：心跳状态、请求数、超时请求数、内存使用、线程数

---

## 十、任务管理

```bash
# 查看所有任务
curl "http://127.0.0.1:1234/tasks"

# 查看单个任务
curl "http://127.0.0.1:1234/tasks/{task_id}"

# 删除任务
curl -X DELETE "http://127.0.0.1:1234/tasks/{task_id}"
```

---

## 十一、测试

```bash
cd backend

# API 接口测试
python -m app.test.test_api

# 数据分析测试
python -m app.test.test_analysis

# 浏览器模块测试
python -m app.test.test_browser
```

---

## 十二、配置文件说明

### 12.1 首次部署：从样例创建配置

项目提供样例配置文件（`.example.json`），真实配置文件已被 `.gitignore` 忽略，不会提交到 git。

```bash
cd backend

# 从样例复制并填写真实值
cp config.example.json config.json
cp db_config.example.json db_config.json
cp encryption_key.example.json encryption_key.json
```

### 12.2 需要填写的配置文件

| 文件 | 是否必须 | 说明 |
|------|----------|------|
| `backend/config.json` | **必须** | 主配置文件（Token、数据库、日志等） |
| `backend/db_config.json` | 可选 | 数据库独立配置（如不使用 config.json 中的 database 节） |
| `backend/encryption_key.json` | **必须** | AES 加密密钥（用于数据库密码加密） |

### 12.3 config.json 配置项详解

```json
{
  "app_name": "GitHub PR API",
  "version": "1.0.0",
  "host": "0.0.0.0",
  "port": 1234,
  "debug": true,

  "tokens": [
    "ghp_你的GitHub个人访问令牌1",
    "ghp_你的GitHub个人访问令牌2"
  ],
  "gitcode_tokens": [
    "你的AtomGit个人访问令牌"
  ],

  "gitcode_settings": {
    "base_url": "https://gitcode.net/api/v4",
    "per_page": 100,
    "state": "all",
    "request_delay": 0.5,
    "max_workers": 3
  },

  "cache": {
    "ttl": 300
  },

  "api_settings": {
    "per_page": 100,
    "state": "all",
    "request_delay": 0.5,
    "max_workers": 3
  },

  "database": {
    "host": "127.0.0.1",
    "port": 27017,
    "username": "admin",
    "password": "使用 password_manager.py encrypt 生成",
    "database": "github_pr_db",
    "encrypted": true
  },

  "logging": {
    "log_dir": "logs",
    "log_file": "server.log",
    "log_level": "INFO",
    "max_size": 10485760,
    "backup_count": 5
  },

  "cors": {
    "allow_origins": ["*"],
    "allow_methods": ["*"],
    "allow_headers": ["*"]
  }
}
```

**配置项说明：**

| 字段 | 说明 | 获取方式 |
|------|------|----------|
| `tokens` | GitHub 个人访问令牌，支持多个轮询 | [GitHub Settings > Developer settings > Personal access tokens](https://github.com/settings/tokens) |
| `gitcode_tokens` | AtomGit/GitCode 访问令牌 | [AtomGit 个人设置 > 个人访问令牌](https://atomgit.com/-/user/settings/personal_access_token) |
| `database.password` | 数据库密码（加密存储） | 见下方 12.4 |
| `database.encrypted` | 密码是否加密 | 设为 `true` 时 password 填加密值，`false` 时填明文 |

### 12.4 数据库密码加密

```bash
# 1. 生成加密密钥（首次部署）
cd backend
python password_manager.py generate-key

# 2. 加密数据库密码
python password_manager.py encrypt 你的明文密码

# 3. 将输出的加密字符串填入 config.json 的 database.password 字段
```

### 12.5 解析器配置文件

**项目映射** `backend/app/analysis/parsers/project_parsers.json`：

```json
{
  "project_parsers": {
    "NVIDIA/cccl": "nvidia-cccl",
    "NVIDIA/*": "nvidia-cccl",
    "rust-lang/rust": "rust-bors",
    "rust-lang/*": "rust-bors"
  }
}
```

**解析器规则** `backend/app/analysis/parsers/parser_rules.json`：

```json
{
  "rules": [
    {
      "name": "flutter-luci",
      "priority": 9,
      "match_projects": ["flutter/*"],
      "match_users": ["auto-submit[bot]"],
      "match_patterns": ["cr-buildbucket\\.appspot\\.com"],
      "status_rules": {
        "success": ["has passed"],
        "failed": ["has failed"]
      },
      "extract_rules": {
        "url": "https?://[^\\s]+"
      }
    }
  ]
}
```

### 12.6 浏览器自动化平台配置

`backend/app/browser/config.py` 中的 `PLATFORM_CONFIG`：

```python
PLATFORM_CONFIG = {
    "openlibing": {
        "name": "openLiBing",
        "base_url": "https://www.openlibing.com",
        "login_url": "https://www.openlibing.com/login",
        "login_indicator": "[data-testid='user-avatar'], .user-info",
        "username_selector": "input[name='username'], #username",
        "password_selector": "input[name='password'], #password",
        "submit_selector": "button[type='submit']",
        "pipeline_url_template": "https://www.openlibing.com/apps/pipelineDetail?pipelineId={pipeline_id}&pipelineRunId={pipeline_run_id}&projectId={project_id}",
    },
}
```

新增平台只需在 `PLATFORM_CONFIG` 中添加对应配置。

---

## 十三、环境变量

| 变量 | 说明 |
|------|------|
| `GITCODE_TOKEN` | AtomGit/GitCode 访问令牌（覆盖 config.json） |
| `OPENLIBING_USERNAME` | openLiBing 登录用户名 |
| `OPENLIBING_PASSWORD` | openLiBing 登录密码 |
