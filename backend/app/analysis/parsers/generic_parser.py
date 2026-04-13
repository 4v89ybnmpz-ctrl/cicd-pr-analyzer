"""
通用 CI/CD 解析器
作为兜底解析器处理常见格式
"""
import re
import logging
from typing import Dict, Any, Optional
from .base_parser import BaseCICDParser

logger = logging.getLogger(__name__)


class GenericParser(BaseCICDParser):
    """
    通用 CI/CD 解析器
    处理常见 CI/CD 评论格式，作为兜底解析器
    """

    name = "generic"
    priority = 100  # 最低优先级，作为兜底

    patterns = [
        r'build\s+(passed|failed|succeeded)',
        r'ci\s+(passed|failed|success)',
        r'tests?\s+(passed|failed)',
        r'coverage\s*[:=]?\s*\d+\.?\d*%',
        r'✅|❌|✔|✗',
    ]

    # 状态关键词
    SUCCESS_KEYWORDS = ['passed', 'success', 'succeeded', '✅', '✔', '✓', 'successful']
    FAILURE_KEYWORDS = ['failed', 'failure', 'error', '❌', '✗', '✘']
    PENDING_KEYWORDS = ['pending', 'running', 'in progress', '⏳']

    def parse(self, body: str, user: str = "") -> Dict[str, Any]:
        """解析通用 CI/CD 结果"""
        result = {
            'parser': self.name,
            'build_status': self._extract_status(body),
            'test_results': self._extract_tests(body),
            'coverage': self._extract_coverage(body),
            'url': self._extract_url(body),
        }

        return result

    def _extract_status(self, body: str) -> str:
        """提取构建状态"""
        body_lower = body.lower()

        for keyword in self.SUCCESS_KEYWORDS:
            if keyword in body_lower:
                return 'success'

        for keyword in self.FAILURE_KEYWORDS:
            if keyword in body_lower:
                return 'failed'

        for keyword in self.PENDING_KEYWORDS:
            if keyword in body_lower:
                return 'pending'

        return 'unknown'

    def _extract_tests(self, body: str) -> Optional[Dict[str, Any]]:
        """提取测试结果"""
        result = {}

        # X tests passed
        passed = re.search(r'(\d+)\s*tests?\s*passed', body, re.IGNORECASE)
        if passed:
            result['passed'] = int(passed.group(1))

        # X tests failed
        failed = re.search(r'(\d+)\s*tests?\s*failed', body, re.IGNORECASE)
        if failed:
            result['failed'] = int(failed.group(1))

        # X tests total
        total = re.search(r'(\d+)\s*tests?\s*total', body, re.IGNORECASE)
        if total:
            result['total'] = int(total.group(1))

        return result if result else None

    def _extract_coverage(self, body: str) -> Optional[Dict[str, Any]]:
        """提取覆盖率"""
        result = {}

        # Coverage: XX%
        coverage = re.search(r'coverage\s*[:=]?\s*(\d+\.?\d*)\s*%', body, re.IGNORECASE)
        if coverage:
            result['percentage'] = float(coverage.group(1))

        # XX% covered
        covered = re.search(r'(\d+\.?\d*)\s*%\s*(covered|coverage)', body, re.IGNORECASE)
        if covered:
            result['percentage'] = float(covered.group(1))

        return result if result else None

    def _extract_url(self, body: str) -> Optional[str]:
        """提取 URL"""
        # GitHub Actions
        match = re.search(r'https?://github\.com/[^/]+/[^/]+/actions/runs/\d+', body)
        if match:
            return match.group(0)

        # CI 相关 URL
        match = re.search(r'https?://[^\s<>"\']+(?:ci|build|pipeline|actions)[^\s<>"\']*', body)
        if match:
            return match.group(0)

        return None