"""
工作流配置
注入现有服务实例和 LLM，供节点函数使用
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
    持有各服务实例和 LLM 的引用，供所有节点共享
    """

    def __init__(self):
        self.github_service = None
        self.db = None
        self.cache = None
        self.config_manager = None
        self.gitcode_service = None
        self.llm = None
        self._initialized = False

    def initialize(self, github_service=None, db=None, cache=None,
                   config_manager=None, gitcode_service=None,
                   anthropic_api_key: str = None):
        """
        注入现有服务实例 + 初始化 LLM
        """
        self.github_service = github_service
        self.db = db
        self.cache = cache
        self.config_manager = config_manager
        self.gitcode_service = gitcode_service

        # 初始化 LLM (Anthropic Claude)
        api_key = anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY")
        if api_key:
            try:
                from langchain_anthropic import ChatAnthropic
                self.llm = ChatAnthropic(
                    model="claude-sonnet-4-20250514",
                    api_key=api_key,
                    max_tokens=4096,
                    temperature=0.3,
                )
                logger.info("LLM (Claude) 初始化成功")
            except Exception as e:
                logger.warning(f"LLM 初始化失败: {e}, AI 分析将不可用")
                self.llm = None
        else:
            logger.warning("未设置 ANTHROPIC_API_KEY, AI 分析将不可用")
            self.llm = None

        self._initialized = True

        # 初始化完成后启动后台线程
        from .runner import _start_background_threads
        _start_background_threads()

        logger.info("WorkflowConfig 初始化完成")

    @property
    def ready(self) -> bool:
        return self._initialized and self.github_service is not None

    @property
    def ai_ready(self) -> bool:
        return self.llm is not None


# 全局配置单例
workflow_config = WorkflowConfig()
