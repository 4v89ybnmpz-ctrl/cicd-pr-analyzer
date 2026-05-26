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
        self._provider = "anthropic"
        self._initialized = False

    def initialize(self, github_service=None, db=None, cache=None,
                   config_manager=None, gitcode_service=None,
                   anthropic_api_key: str = None,
                   anthropic_base_url: str = None,
                   max_tokens: int = None,
                   temperature: float = None,
                   model: str = None,
                   provider: str = None):
        """
        注入现有服务实例 + 初始化 LLM
        provider: "anthropic" 或 "openai"，决定使用哪个 LangChain Chat 类
        """
        self.github_service = github_service
        self.db = db
        self.cache = cache
        self.config_manager = config_manager
        self.gitcode_service = gitcode_service

        # 初始化 LLM
        api_key = anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("OPENAI_API_KEY")
        _provider = provider or os.environ.get("LLM_PROVIDER", "anthropic")
        _model = model or "glm-5.1"
        _base_url = anthropic_base_url or os.environ.get("ANTHROPIC_BASE_URL") or os.environ.get("OPENAI_BASE_URL", "")
        _max_tokens = max_tokens or 4096
        _temperature = temperature if temperature is not None else 0.3

        if api_key:
            try:
                if _provider == "openai":
                    from langchain_openai import ChatOpenAI
                    self.llm = ChatOpenAI(
                        model=_model,
                        api_key=api_key,
                        base_url=_base_url or None,
                        max_tokens=_max_tokens,
                        temperature=_temperature,
                    )
                    logger.info(f"LLM (OpenAI/{_model}) 初始化成功, base_url={_base_url or 'default'}")
                else:
                    from langchain_anthropic import ChatAnthropic
                    self.llm = ChatAnthropic(
                        model=_model,
                        api_key=api_key,
                        base_url=_base_url or "https://open.bigmodel.cn/api/paas/v4",
                        max_tokens=_max_tokens,
                        temperature=_temperature,
                    )
                    logger.info(f"LLM (Anthropic/{_model}) 初始化成功, base_url={_base_url}")
                self._provider = _provider
            except Exception as e:
                logger.warning(f"LLM 初始化失败: {e}, AI 分析将不可用")
                self.llm = None
                self._provider = _provider
        else:
            logger.warning("未设置 API Key, AI 分析将不可用")
            self.llm = None
            self._provider = _provider

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
