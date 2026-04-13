"""
路由模块
"""
from .base import register_base_routes
from .config import register_config_routes, register_cache_routes
from .github import register_github_routes
from .database import register_database_routes
from .gitcode import register_gitcode_routes
from .task import register_task_routes
from .browser import register_browser_routes
from .atomgit import register_atomgit_routes

__all__ = [
    'register_base_routes',
    'register_config_routes',
    'register_cache_routes',
    'register_github_routes',
    'register_database_routes',
    'register_gitcode_routes',
    'register_task_routes',
    'register_browser_routes',
    'register_atomgit_routes',
]