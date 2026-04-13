"""
数据提取器模块
从拦截的网络请求中提取特定平台的数据
"""
from .base import BaseExtractor
from .openlibing import OpenLibingExtractor

__all__ = [
    'BaseExtractor',
    'OpenLibingExtractor',
]
