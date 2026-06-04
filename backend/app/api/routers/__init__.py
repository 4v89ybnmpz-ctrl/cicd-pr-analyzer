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
from .analysis import register_analysis_routes
from .export import register_export_routes
from .notifications import register_notification_routes
from .webhooks import register_webhook_routes
from .compare import register_compare_routes
from .cannbot_skills import register_cannbot_routes
from .terminal import register_terminal_routes
from .workflow_simulation import register_workflow_simulation_routes
from .ops_dev_session import register_ops_dev_session_routes
from .workflow_sim_v2 import register_workflow_sim_v2_routes

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
    'register_analysis_routes',
    'register_export_routes',
    'register_notification_routes',
    'register_webhook_routes',
    'register_compare_routes',
    'register_cannbot_routes',
    'register_terminal_routes',
    'register_workflow_simulation_routes',
    'register_ops_dev_session_routes',
    'register_workflow_sim_v2_routes',
]