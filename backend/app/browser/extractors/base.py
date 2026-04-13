"""
提取器基类
定义数据提取的统一接口
"""
import logging
from typing import Dict, Any, List, Optional
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class BaseExtractor(ABC):
    """
    数据提取器基类
    从拦截的 API 响应中提取结构化数据
    """

    # 提取器名称
    name: str = "base"

    # 该提取器关注的 API 路径模式（正则）
    api_patterns: List[str] = []

    @abstractmethod
    def extract(self, api_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        从 API 响应数据中提取结构化信息
        :param api_data: 拦截到的 API 响应列表
        :return: 提取结果
        """
        pass

    def filter_relevant(self, api_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        过滤出与该提取器相关的 API 响应
        :param api_data: 所有 API 响应
        :return: 相关的 API 响应
        """
        import re

        if not self.api_patterns:
            return api_data

        relevant = []
        for item in api_data:
            url = item.get("url", "")
            for pattern in self.api_patterns:
                if re.search(pattern, url):
                    relevant.append(item)
                    break

        return relevant
