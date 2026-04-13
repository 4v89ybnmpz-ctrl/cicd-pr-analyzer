"""
浏览器自动化模块
通过 Playwright 实现对需要登录的内部 CI/CD 平台的数据抓取

架构：
  BrowserManager   → 浏览器生命周期管理（启动/关闭/页面）
  AuthManager      → 登录与会话管理（Cookie 持久化/登录检测）
  NetworkInterceptor → 网络请求拦截（捕获 API 请求/响应）
  extractors/      → 平台特定的数据提取器
"""

from .manager import BrowserManager
from .interceptor import NetworkInterceptor
from .auth import AuthManager

__all__ = [
    'BrowserManager',
    'NetworkInterceptor',
    'AuthManager',
]
