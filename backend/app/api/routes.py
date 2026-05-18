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
)

logger = logging.getLogger(__name__)


def create_router(cache, github_service, db, config_manager, gitcode_service=None):
    """
    创建 API 路由
    :param cache: 缓存实例
    :param github_service: GitHub 服务实例
    :param db: 数据库实例
    :param config_manager: 配置管理器实例
    :param gitcode_service: GitCode 服务实例（可选）
    :return: APIRouter 实例
    """
    router = APIRouter()

    # 注册所有路由
    register_base_routes(router)
    register_config_routes(router, cache, github_service, config_manager)
    register_cache_routes(router, cache)
    register_github_routes(router, cache, github_service, db)
    register_database_routes(router, db)
    register_task_routes(router, cache, github_service, db)
    register_browser_routes(router)
    register_atomgit_routes(router, db)
    register_analysis_routes(router, db, cache)

    if gitcode_service:
        register_gitcode_routes(router, gitcode_service, db)

    logger.info("所有路由注册完成")
    return router