"""
FastAPI 主应用（异步版本）
使用 lifespan 管理异步资源生命周期
GitHub PR 数据获取和管理 API
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn
import os
import signal
import sys
import asyncio

# 导入核心模块
from app.core.logger import setup_logging, log_exception
from app.core.cache import DataCache
from app.core.monitor import start_monitoring, stop_monitoring, get_monitor

# 导入安全模块
from app.core.security import (
    SecurityMiddleware, APIKeyAuth, RateLimiter,
    SecurityHeadersConfig, run_security_check,
)

# 导入配置模块
from app.config.config_manager import config_manager

# 导入服务模块
from app.services.github_service import GitHubPRService, TokenPool
from app.services.gitcode_service import GitCodePRService, GitCodeTokenPool
from app.services.database_service import DatabaseService
from app.core.docker_secrets import get_database_password

# 导入 API 路由
from app.api.routes import create_router

# 设置日志
logger = setup_logging()

# 启动时安全检查
run_security_check()

# ====================
# 初始化配置（同步）
# ====================
try:
    config = config_manager.to_dict()
    tokens = config_manager.get_tokens()
    cache_ttl = config_manager.get_cache_ttl()
    api_settings = config_manager.get_api_settings()
    logger.info("配置加载成功")
except Exception as e:
    logger.error(f"配置加载失败: {e}")
    log_exception(logger, "配置加载失败")
    sys.exit(1)

# ====================
# 初始化核心组件（同步部分）
# ====================
cache = DataCache(default_ttl=cache_ttl)
token_pool = TokenPool(tokens)
github_service = GitHubPRService(token_pool, api_settings)
logger.info("核心组件初始化成功")

# 初始化 GitCode 服务
gitcode_service = None
try:
    gitcode_tokens = config.get("gitcode_tokens", [])
    gitcode_settings = config.get("gitcode_settings", {
        "base_url": "https://gitcode.net/api/v4",
        "per_page": 100, "state": "all",
        "request_delay": 0.5, "max_workers": 3
    })
    if gitcode_tokens:
        gitcode_token_pool = GitCodeTokenPool(gitcode_tokens)
        gitcode_service = GitCodePRService(gitcode_token_pool, gitcode_settings)
        logger.info("GitCode 服务初始化成功")
    else:
        logger.info("未配置 GitCode Token，GitCode 服务不可用")
except Exception as e:
    logger.warning(f"GitCode 服务初始化失败: {e}")
    gitcode_service = None

# 初始化数据库（构造函数同步，连接在 lifespan 中异步执行）
db_config = config.get("database", {})
db_host = os.environ.get("MONGODB_HOST", db_config.get('host', '127.0.0.1'))
db_port = int(os.environ.get("MONGODB_PORT", db_config.get('port', 27017)))
db_username = os.environ.get("MONGODB_USERNAME", db_config.get('username', 'admin'))
db_database = os.environ.get("MONGODB_DATABASE", db_config.get('database', 'github_pr_db'))
db_password_env = os.environ.get("MONGODB_PASSWORD")
db_password = db_password_env or db_config.get('password') or get_database_password()

db = DatabaseService(
    host=db_host, port=db_port, username=db_username,
    password=db_password, database=db_database
)
logger.info(f"数据库配置: {db_host}:{db_port}/{db_database} (环境变量: {'是' if db_password_env else '否'})")


# ====================
# Lifespan 异步生命周期管理
# ====================
@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理：启动时连接数据库，关闭时断开连接"""
    # === 启动 ===
    logger.info(f"启动 {config.get('app_name', 'GitHub PR API')} v{config.get('version', '1.0.0')}")

    # 异步连接数据库
    try:
        if await db.connect():
            logger.info("数据库连接成功")
            from app.core.task_queue import task_queue
            task_queue.set_db(db)
        else:
            logger.warning("数据库连接失败，数据持久化功能不可用")
    except Exception as e:
        logger.error(f"数据库连接异常: {e}")

    # 启动服务监控
    start_monitoring()
    logger.info("服务监控已启动")

    yield  # 应用运行中

    # === 关闭 ===
    logger.info("正在关闭服务...")
    stop_monitoring()

    # 关闭 GitHub 服务 HTTP 客户端
    try:
        await github_service.close()
    except Exception:
        pass

    # 关闭 GitCode 服务 HTTP 客户端
    if gitcode_service:
        try:
            await gitcode_service.close()
        except Exception:
            pass

    # 断开数据库连接
    try:
        await db.disconnect()
    except Exception:
        pass

    logger.info("服务已关闭")


# ====================
# 创建 FastAPI 应用
# ====================
app = FastAPI(
    title=config.get("app_name", "GitHub PR API"),
    version=config.get("version", "1.0.0"),
    description="GitHub PR 数据获取和管理 API",
    lifespan=lifespan,
)

# 配置 CORS
cors_config = config.get("cors", {})
allow_origins = cors_config.get("allow_origins", ["*"])
if isinstance(allow_origins, str):
    allow_origins = [allow_origins]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=cors_config.get("allow_credentials", True),
    allow_methods=cors_config.get("allow_methods", ["*"]),
    allow_headers=cors_config.get("allow_headers", ["*"]),
)
logger.info(f"CORS 配置: allow_origins={allow_origins}")

# 注册路由
router = create_router(cache, github_service, db, config_manager, gitcode_service)
app.include_router(router)

# 注册安全中间件
security_config = config.get("security", {})
auth = APIKeyAuth(security_config)
rate_limiter = RateLimiter(security_config.get("rate_limit", {}))
headers_config = SecurityHeadersConfig(security_config.get("security_headers", {}))
security_middleware = SecurityMiddleware(app, auth, rate_limiter, headers_config)
app.add_middleware(SecurityMiddleware.__bases__[0], dispatch=security_middleware.dispatch)
logger.info(f"安全中间件已注册: 认证={'启用' if auth.enabled else '关闭'}, 限流={'启用' if rate_limiter.enabled else '关闭'}, 安全头={'启用' if headers_config.enabled else '关闭'}")

# 注册 Workflow 路由
try:
    import sys, os
    _project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if _project_root not in sys.path:
        sys.path.insert(0, _project_root)
    from workflow.config import workflow_config
    from workflow.api.routes import register_workflow_routes
    from fastapi import APIRouter

    # 从配置文件读取 LLM 参数
    import json
    _llm_config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'llm_config.json')
    _llm_kwargs = {}
    if os.path.exists(_llm_config_path):
        try:
            with open(_llm_config_path) as f:
                _saved = json.load(f)
            if _saved.get("api_key"): _llm_kwargs["anthropic_api_key"] = _saved["api_key"]
            if _saved.get("base_url"): _llm_kwargs["anthropic_base_url"] = _saved["base_url"]
            if _saved.get("max_tokens"): _llm_kwargs["max_tokens"] = _saved["max_tokens"]
            if _saved.get("temperature") is not None: _llm_kwargs["temperature"] = _saved["temperature"]
            if _saved.get("model"): _llm_kwargs["model"] = _saved["model"]
            if _saved.get("provider"): _llm_kwargs["provider"] = _saved["provider"]
        except Exception:
            pass

    workflow_config.initialize(
        github_service=github_service, db=db, cache=cache,
        config_manager=config_manager, gitcode_service=gitcode_service,
        **_llm_kwargs,
    )
    workflow_router = APIRouter()
    register_workflow_routes(workflow_router)
    app.include_router(workflow_router)
    logger.info("Workflow 路由注册成功")
except ImportError as e:
    logger.warning(f"Workflow 模块未安装，跳过: {e}")
except Exception as e:
    logger.warning(f"Workflow 路由注册失败: {e}")


# 请求追踪中间件
@app.middleware("http")
async def monitor_middleware(request: Request, call_next):
    """监控中间件（含请求参数脱敏）"""
    from app.core.security import mask_url_params
    monitor = get_monitor()
    endpoint = f"{request.method} {request.url.path}"
    safe_query = mask_url_params(str(request.query_params))
    req_id = monitor.track_request(endpoint, {"query": safe_query})

    try:
        response = await call_next(request)
        monitor.end_request(req_id)
        return response
    except Exception as e:
        monitor.end_request(req_id)
        logger.error(f"请求异常: {endpoint} - {e}")
        return JSONResponse(status_code=500, content={"error": str(e), "endpoint": endpoint})


# 监控状态接口
@app.get("/monitor/status")
async def get_monitor_status():
    return get_monitor().get_status()


def main():
    """主函数"""
    try:
        server_host = os.environ.get("HOST", config.get("host", "0.0.0.0"))
        server_port = int(os.environ.get("PORT", config.get("port", 1234)))
        uvicorn.run(
            app, host=server_host, port=server_port,
            log_level="info", access_log=True, use_colors=False
        )
    except KeyboardInterrupt:
        logger.info("收到键盘中断，正在关闭服务...")
    except Exception as e:
        logger.error(f"服务运行异常: {e}")
        log_exception(logger, "服务运行异常")
        sys.exit(1)


if __name__ == "__main__":
    main()
