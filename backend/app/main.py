"""
FastAPI 主应用
GitHub PR 数据获取和管理 API
添加服务监控和异常处理功能
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import os
import json
import signal
import sys

# 导入核心模块
from app.core.logger import setup_logging, log_exception
from app.core.cache import DataCache
from app.core.monitor import start_monitoring, stop_monitoring, get_monitor

# 导入配置模块
from app.config.config_manager import config_manager

# 导入服务模块
from app.services.github_service import GitHubPRService, TokenPool
from app.services.gitcode_service import GitCodePRService, GitCodeTokenPool
from app.services.database_service import DatabaseService

# 导入 API 路由
from app.api.routes import create_router

# 设置日志
logger = setup_logging()

# 全局变量，用于优雅关闭
shutdown_flag = False

def signal_handler(signum, frame):
    """信号处理器，用于优雅关闭"""
    global shutdown_flag
    logger.info(f"收到信号 {signum}，准备关闭服务...")
    shutdown_flag = True
    stop_monitoring()

# 注册信号处理器
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# ====================
# 初始化配置
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
# 初始化核心组件
# ====================
try:
    cache = DataCache(default_ttl=cache_ttl)
    token_pool = TokenPool(tokens)
    github_service = GitHubPRService(token_pool, api_settings)
    logger.info("核心组件初始化成功")
except Exception as e:
    logger.error(f"核心组件初始化失败: {e}")
    log_exception(logger, "核心组件初始化失败")
    sys.exit(1)

# 初始化 GitCode 服务
gitcode_service = None
try:
    # 从配置获取 GitCode Token 和设置
    gitcode_tokens = config.get("gitcode_tokens", [])
    gitcode_settings = config.get("gitcode_settings", {
        "base_url": "https://gitcode.net/api/v4",
        "per_page": 100,
        "state": "all",
        "request_delay": 0.5,
        "max_workers": 3
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

# 初始化数据库
db = None
try:
    # 从配置读取数据库设置
    db_config = config.get("database", {})
    if db_config:
        db = DatabaseService(
            host=db_config.get('host', '127.0.0.1'),
            port=db_config.get('port', 27017),
            username=db_config.get('username', 'admin'),
            password=db_config.get('password', 'admin123'),
            database=db_config.get('database', 'github_pr_db')
        )
        logger.info(f"从配置文件加载数据库配置（密码加密: {db_config.get('encrypted', False)}）")
    else:
        db = DatabaseService()
        logger.info("使用默认数据库配置")

    if db.connect():
        logger.info("数据库连接成功")
    else:
        logger.warning("数据库连接失败，数据持久化功能不可用")
        db = None
except Exception as e:
    logger.error(f"数据库初始化失败: {e}")
    log_exception(logger, "数据库初始化失败")
    db = None

# ====================
# 创建 FastAPI 应用
# ====================
try:
    app = FastAPI(
        title=config.get("app_name", "GitHub PR API"),
        version=config.get("version", "1.0.0"),
        description="GitHub PR 数据获取和管理 API"
    )
    
    # 配置 CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # 注册路由
    router = create_router(cache, github_service, db, config_manager, gitcode_service)
    app.include_router(router)

    # 添加请求追踪中间件
    from fastapi import Request
    from fastapi.responses import JSONResponse
    import time

    @app.middleware("http")
    async def monitor_middleware(request: Request, call_next):
        """监控中间件"""
        monitor = get_monitor()
        endpoint = f"{request.method} {request.url.path}"
        req_id = monitor.track_request(endpoint, dict(request.query_params))

        try:
            response = await call_next(request)
            monitor.end_request(req_id)
            return response
        except Exception as e:
            monitor.end_request(req_id)
            logger.error(f"请求异常: {endpoint} - {e}")
            return JSONResponse(
                status_code=500,
                content={"error": str(e), "endpoint": endpoint}
            )

    # 添加监控状态接口
    @app.get("/monitor/status")
    async def get_monitor_status():
        """获取监控状态"""
        return get_monitor().get_status()

    logger.info("FastAPI 应用创建成功")
except Exception as e:
    logger.error(f"FastAPI 应用创建失败: {e}")
    log_exception(logger, "FastAPI 应用创建失败")
    sys.exit(1)


def main():
    """主函数"""
    try:
        logger.info(f"启动 {config.get('app_name', 'GitHub PR API')} v{config.get('version', '1.0.0')}")

        # 启动服务监控
        monitor = start_monitoring()
        logger.info("服务监控已启动，异常将记录到日志文件")

        # 配置uvicorn，添加详细的日志输出
        uvicorn.run(
            app,
            host="0.0.0.0",
            port=1234,
            log_level="info",
            access_log=True,
            use_colors=False
        )
    except KeyboardInterrupt:
        logger.info("收到键盘中断，正在关闭服务...")
    except Exception as e:
        logger.error(f"服务运行异常: {e}")
        log_exception(logger, "服务运行异常")
        sys.exit(1)
    finally:
        logger.info("服务已关闭")
        stop_monitoring()
        if db:
            db.disconnect()


if __name__ == "__main__":
    main()
