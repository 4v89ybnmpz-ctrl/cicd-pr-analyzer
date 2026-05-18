"""
工作流配置
注入现有服务实例，供节点函数使用
"""
import os
import sys
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# 确保能导入 backend 模块
_backend_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'backend')
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)


class WorkflowConfig:
    """
    工作流配置单例
    持有各服务实例的引用，供所有节点共享
    """

    def __init__(self):
        self.github_service = None
        self.db = None
        self.cache = None
        self.config_manager = None
        self.gitcode_service = None
        self._initialized = False

    def initialize(self, github_service=None, db=None, cache=None,
                   config_manager=None, gitcode_service=None):
        """
        注入现有服务实例
        通常在 FastAPI 启动时从 main.py 注入
        """
        self.github_service = github_service
        self.db = db
        self.cache = cache
        self.config_manager = config_manager
        self.gitcode_service = gitcode_service
        self._initialized = True
        logger.info("WorkflowConfig 初始化完成")

    @property
    def ready(self) -> bool:
        return self._initialized and self.github_service is not None


# 全局配置单例
workflow_config = WorkflowConfig()
