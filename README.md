# GitHub PR Data Analyzer

多平台 PR 数据获取、持久化和 CI/CD 工程能力分析服务。支持 GitHub、GitCode、AtomGit 三大平台，提供异步 API 接口、数据持久化、CI/CD 分析、浏览器自动化抓取等功能。

## 技术栈

- **Web 框架**: FastAPI (异步)
- **HTTP 客户端**: httpx (异步)
- **数据库**: MongoDB (motor 异步驱动)
- **部署**: Docker Compose
- **安全**: API Key 认证 + AES 加密 + 请求限流

## 快速开始

### 1. 环境准备

```bash
# 安装依赖
pip install -r backend/requirements.txt
```

### 2. 配置

```bash
# 复制示例配置
cp backend/config.example.json backend/config.json
```

编辑 `backend/config.json`，填入你的 GitHub Token：

```json
{
  "tokens": [
    "ghp_你的GitHubPersonalAccessToken"
  ]
}
```

如需数据库持久化，配置 MongoDB 连接信息（支持 AES 加密密码）：

```json
{
  "database": {
    "host": "127.0.0.1",
    "port": 27017,
    "username": "admin",
    "password": "加密后的密码",
    "database": "github_pr_db",
    "encrypted": true
  }
}
```

### 3. 启动 MongoDB (Docker)

```bash
cd backend
docker-compose up -d mongodb
```

### 4. 启动服务

```bash
cd backend
python -m app.main
```

服务默认监听 `http://0.0.0.0:1234`，可通过环境变量或配置文件修改：

```bash
HOST=0.0.0.0 PORT=8080 python -m app.main
```

### 5. 验证

```bash
# 健康检查
curl http://localhost:1234/health

# API 文档
open http://localhost:1234/docs
```

## Docker 部署

一键启动全部服务（后端 + MongoDB + Mongo Express 管理界面）：

```bash
cd backend

# 设置 MongoDB 密码
echo "your_secure_password" > secrets/mongodb_root_password.txt

# 启动
docker-compose up -d
```

| 服务 | 端口 | 说明 |
|------|------|------|
| backend | 1234 | FastAPI 应用 |
| mongodb | 27017 | 数据库 |
| mongo-express | 8081 | 数据库管理界面 (http://localhost:8081) |

## API 概览

### 基础接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | 服务信息 |
| GET | `/health` | 健康检查 |
| GET | `/docs` | Swagger API 文档 |

### GitHub PR 数据获取

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/github/prs/{owner}/{repo}` | 获取项目 PR 列表 |
| POST | `/github/prs/batch` | 批量获取多项目 PR |
| GET | `/github/prs/{owner}/{repo}/{pr_number}/detail` | PR 详情 |
| POST | `/github/prs/detail/batch` | 批量 PR 详情 |
| GET | `/github/prs/{owner}/{repo}/comments` | 获取所有 PR 评论 |
| GET | `/github/prs/{owner}/{repo}/timeline` | 获取所有 PR 时间线 |
| GET | `/github/prs/{owner}/{repo}/reviews` | 获取所有 PR Reviews |
| GET | `/github/prs/{owner}/{repo}/commits` | 获取所有 PR Commits |
| GET | `/github/token-pool` | Token 池状态 |

### 数据库查询

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/database/stats` | 数据库统计 |
| GET | `/database/prs` | PR 数据列表 |
| GET | `/database/prs/{owner}/{repo}` | 查询指定仓库 PR |
| DELETE | `/database/prs/{owner}/{repo}` | 删除 PR 数据 |
| GET | `/database/details` | PR 详情分页查询 |
| GET | `/database/details/search` | PR 详情模糊搜索 |
| GET | `/database/comments` | 评论分页查询 |
| GET | `/database/timeline` | 时间线分页查询 |
| GET | `/database/aggregate` | 聚合统计 |

### CI/CD 分析

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/analysis/cicd/analyze/{owner}/{repo}` | 触发 CI/CD 分析 |
| GET | `/analysis/cicd/report/{owner}/{repo}` | 获取完整分析报告 |
| GET | `/analysis/cicd/stats/{owner}/{repo}` | 统计摘要 |
| GET | `/analysis/cicd/trends/{owner}/{repo}` | 趋势数据 |
| GET | `/analysis/cicd/results/{owner}/{repo}` | 原始结果查询 |

### GitCode / AtomGit

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/gitcode/mrs/{owner}/{repo}` | GitCode MR 列表 |
| GET | `/atomgit/pulls/{owner}/{repo}` | AtomGit PR 列表 |
| GET | `/atomgit/pulls/{owner}/{repo}/comments` | AtomGit 批量评论 |

### 任务管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/tasks` | 所有任务列表 |
| GET | `/tasks/{task_id}` | 查询任务进度 |
| DELETE | `/tasks/{task_id}` | 删除任务 |
| POST | `/github/prs/batch-async` | 异步批量获取 |

### 配置和监控

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/config` | 当前配置 |
| POST | `/config/reload` | 热重载配置 |
| GET | `/cache/stats` | 缓存统计 |
| DELETE | `/cache/clear` | 清空缓存 |
| GET | `/monitor/status` | 服务监控状态 |

## 使用示例

### 获取 PR 列表

```bash
curl "http://localhost:1234/github/prs/rust-lang/rust"
```

### 批量获取多仓库 PR

```bash
curl -X POST "http://localhost:1234/github/prs/batch" \
  -H "Content-Type: application/json" \
  -d '{
    "projects": [
      {"owner": "rust-lang", "repo": "rust"},
      {"owner": "python", "repo": "cpython"}
    ]
  }'
```

### 获取 PR 评论并识别 Bot

```bash
curl "http://localhost:1234/github/prs/rust-lang/rust/comments?limit=20"
```

### 触发 CI/CD 分析

```bash
curl -X POST "http://localhost:1234/analysis/cicd/analyze/rust-lang/rust"
```

### 查看分析报告

```bash
curl "http://localhost:1234/analysis/cicd/report/rust-lang/rust"
```

### 数据库分页查询

```bash
curl "http://localhost:1234/database/details?owner=rust-lang&repo=rust&page=1&size=20"
```

## 安全配置

### 启用 API Key 认证

在 `config.json` 中：

```json
{
  "security": {
    "auth_enabled": true,
    "api_keys": [
      {"key": "sk-your-secret-key", "name": "admin", "enabled": true}
    ]
  }
}
```

请求时携带 Key：

```bash
# 方式 1: 请求头
curl -H "X-API-Key: sk-your-secret-key" http://localhost:1234/github/prs/owner/repo

# 方式 2: Bearer Token
curl -H "Authorization: Bearer sk-your-secret-key" http://localhost:1234/github/prs/owner/repo

# 方式 3: 查询参数
curl "http://localhost:1234/github/prs/owner/repo?api_key=sk-your-secret-key"
```

### 限流配置

默认 60 次/分钟，写入类接口 20 次/分钟。可在配置中调整：

```json
{
  "security": {
    "rate_limit": {
      "enabled": true,
      "window_seconds": 60,
      "max_requests": 60,
      "strict_max_requests": 20
    }
  }
}
```

## 项目结构

```
backend/
├── app/
│   ├── main.py              # FastAPI 入口 (lifespan 异步生命周期)
│   ├── api/routers/          # API 路由 (9 个模块)
│   ├── services/             # 服务层 (GitHub/GitCode/Database)
│   ├── models/               # Pydantic 模型 (Request + Response)
│   ├── analysis/             # CI/CD 分析引擎
│   ├── core/                 # 核心模块 (缓存/日志/加密/安全/监控)
│   ├── config/               # 配置管理
│   └── test/                 # 测试用例
├── docker-compose.yml        # Docker 编排
├── config.example.json       # 配置模板
└── requirements.txt          # Python 依赖

workflow/                      # LangGraph 多 Agent 工作流
├── agents/                   # Agent 模块
├── api/routes.py             # 工作流 API
└── README.md                 # 工作流详细文档
```

## 密码加密

使用内置工具加密数据库密码：

```bash
cd backend
python -m app.scripts.password_manager encrypt "你的明文密码"
```

将输出的加密字符串填入 `config.json` 的 `database.password` 字段，并设置 `"encrypted": true`。

## 测试

```bash
cd backend
python -m app.test.test_security      # 安全功能测试
python -m app.test.test_encryption    # 加密功能测试
# 或运行全部测试
python test.py
```

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `HOST` | 服务监听地址 | `0.0.0.0` |
| `PORT` | 服务监听端口 | `1234` |
| `MONGODB_HOST` | MongoDB 主机 | `127.0.0.1` |
| `MONGODB_PORT` | MongoDB 端口 | `27017` |
| `MONGODB_USERNAME` | MongoDB 用户名 | `admin` |
| `MONGODB_PASSWORD` | MongoDB 密码 | 配置文件值 |
| `MONGODB_DATABASE` | 数据库名 | `github_pr_db` |
