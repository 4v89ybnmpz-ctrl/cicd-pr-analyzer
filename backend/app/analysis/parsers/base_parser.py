"""
CI/CD 解析器基类
提供可扩展的解析器接口
"""
import re
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


class BaseCICDParser(ABC):
    """
    CI/CD 解析器基类
    所有项目特定的解析器都继承此类
    """

    # 解析器名称
    name: str = "base"

    # 解析器优先级（数字越小优先级越高）
    priority: int = 100

    # 识别模式（用于判断是否使用此解析器）
    patterns: List[str] = []

    def __init__(self):
        """初始化解析器"""
        self.compiled_patterns = [re.compile(p, re.IGNORECASE | re.MULTILINE) for p in self.patterns]

    def can_parse(self, body: str, user: str = "") -> bool:
        """
        判断是否可以使用此解析器解析
        :param body: 评论内容
        :param user: 用户名
        :return: 是否可以解析
        """
        if not body:
            return False

        for pattern in self.compiled_patterns:
            if pattern.search(body):
                return True

        return False

    @abstractmethod
    def parse(self, body: str, user: str = "") -> Dict[str, Any]:
        """
        解析 CI/CD 评论内容
        :param body: 评论内容
        :param user: 用户名
        :return: 解析结果
        """
        pass

    def _extract_url(self, body: str) -> Optional[str]:
        """提取 URL"""
        # GitHub Actions
        match = re.search(r'https?://github\.com/[^/]+/[^/]+/actions/runs/\d+', body)
        if match:
            return match.group(0)

        # 通用 CI URL
        match = re.search(r'https?://[^\s<>"\']+(?:actions|build|ci|pipeline)[^\s<>"\']*', body)
        if match:
            return match.group(0)

        return None

    def _parse_duration(self, time_str: str) -> Optional[int]:
        """
        解析时长字符串为秒数
        :param time_str: 如 "1h 30m 45s" 或 "90m" 或 "3600s"
        :return: 秒数
        """
        if not time_str:
            return None

        total_seconds = 0

        # 提取小时
        hours = re.search(r'(\d+)\s*h', time_str)
        if hours:
            total_seconds += int(hours.group(1)) * 3600

        # 提取分钟
        minutes = re.search(r'(\d+)\s*m', time_str)
        if minutes:
            total_seconds += int(minutes.group(1)) * 60

        # 提取秒
        seconds = re.search(r'(\d+)\s*s', time_str)
        if seconds:
            total_seconds += int(seconds.group(1))

        return total_seconds if total_seconds > 0 else None