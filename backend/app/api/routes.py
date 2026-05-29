"""
API 路由模块
统一注册所有路由
"""
from fastapi import APIRouter
import logging

from app.api.routers import (
    register_base_routes,
    register_config_routes,
    register_cache_routes,
    register_github_routes,
    register_database_routes,
    register_gitcode_routes,
    register_task_routes,
    register_browser_routes,
    register_atomgit_routes,
    register_analysis_routes,
    register_export_routes,
    register_notification_routes,
    register_webhook_routes,
    register_compare_routes,
    register_cannbot_routes,
    register_terminal_routes,
    register_workflow_simulation_routes,
)
from app.api.routers.async_tasks import register_async_task_routes
from app.api.routers.git import register_git_routes

logger = logging.getLogger(__name__)


def create_router(cache, github_service, db, config_manager, gitcode_service=None,
                  notification_engine=None, exporter=None, webhook_handler=None):
    """
    创建 API 路由
    """
    router = APIRouter()

    # 注册所有路由
    register_base_routes(router)
    register_config_routes(router, cache, github_service, config_manager)
    register_cache_routes(router, cache)
    register_github_routes(router, cache, github_service, db)
    register_database_routes(router, db, github_service)
    register_task_routes(router, cache, github_service, db)
    register_browser_routes(router)
    register_atomgit_routes(router, db)
    register_analysis_routes(router, db, cache)

    register_async_task_routes(router, github_service, db)

    register_git_routes(router, db, github_service, config=config_manager.config if hasattr(config_manager, 'config') else None)

    if gitcode_service:
        register_gitcode_routes(router, gitcode_service, db)

    # 数据导出路由
    if exporter:
        register_export_routes(router, db, exporter)

    # 通知推送路由
    if notification_engine:
        register_notification_routes(router, db, notification_engine)

    # Webhook 路由
    if webhook_handler:
        register_webhook_routes(router, db, webhook_handler)

    # 多仓库对比路由
    register_compare_routes(router, db)

    # CANNBot Skills 路由
    register_cannbot_routes(router)

    # WebSocket 终端路由
    register_terminal_routes(router)

    # 工作流仿真路由
    register_workflow_simulation_routes(router, db, exporter)

    logger.info("所有路由注册完成")
    return router
