# GitHub PR Download 项目

## 项目概述
构建一个 FastAPI 后端服务，用于获取和管理 GitHub PR 数据，支持数据持久化到 MongoDB。

## 技术栈
- 后端框架: FastAPI
- 数据库: MongoDB (Docker)
- 密码管理: Docker Secrets + AES 加密
- 缓存: 内存缓存 (TTL)

## 目录结构
```
pr_download/
├── backend/           # 后端应用 (主要工作目录)
│   ├── app/
│   │   ├── api/       # API 路由
│   │   ├── core/      # 核心组件 (缓存、日志、加密)
│   │   ├── config/    # 配置管理
│   │   ├── models/    # 数据模型
│   │   ├── services/  # 服务层 (GitHub、数据库)
│   │   └── test/      # 测试用例
│   ├── REQUIREMENTS.md  # 需求清单
│   └── PROGRESS.md      # 实现进度
└── frontend/          # 前端应用
```

## AI 工作指令
### 基础环境
- 环境使用conda 创建虚拟环境 环境名称：github_pr_download
- 使用前先检查虚拟环境是否存在
- 服务的运行和测试都在该虚拟环境中执行

### 代码规范
- 生成的代码需要添加人性化注释
- 不要随意修改已完成且功能正确的代码
- 所有后端代码放在 `backend/` 目录
- 新功能需要添加对应的测试用例

### 需求管理流程
1. 阅读 `backend/REQUIREMENTS.md` 了解待实现需求
2. 实现功能后更新 `backend/PROGRESS.md`
3. 将 `- [ ]` 改为 `- [x]` 标记完成
4. 更新文件末尾的 `最后更新时间`

### 测试要求
- 新功能必须添加测试用例
- 运行 `python backend/test.py` 验证功能
- 测试通过率需保持 100%

### 数据库
- MongoDB 运行在 Docker 中
- 使用 `docker-compose up -d` 启动
- 数据分表存储: pr_data, pr_comments, pr_timeline