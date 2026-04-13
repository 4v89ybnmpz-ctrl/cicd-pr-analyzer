"""
GitHub Actions CI 解析器
解析标准 GitHub Actions CI 结果格式
"""
import re
import logging
from typing import Dict, Any, Optional
from .base_parser import BaseCICDParser

logger = logging.getLogger(__name__)


class GitHubActionsParser(BaseCICDParser):
    """
    GitHub Actions CI 解析器

    解析格式示例:
    **Workflow run failed:** https://github.com/owner/repo/actions/runs/12345

    或:
    ✅ All checks have passed
    2 successful checks, 0 failed checks

    或:
    ❌ 1 check failed
    - test (ubuntu-latest): failed
    """

    name = "github-actions"
    priority = 20  # 中等优先级

    patterns = [
        r'workflow\s+run\s+(passed|failed|succeeded)',
        r'all\s+checks\s+have\s+passed',
        r'\d+\s+successful\s+checks',
        r'\d+\s+check(s)?\s+failed',
        r'\[actions\]',
        r'github\.com/.+/actions/runs/\d+',
    ]

    def parse(self, body: str, user: str = "") -> Dict[str, Any]:
        """解析 GitHub Actions CI 结果"""
        result = {
            'parser': self.name,
            'build_status': self._extract_status(body),
            'checks': self._extract_checks(body),
            'url': self._extract_url(body),
        }

        # 提取覆盖率（如果有）
        coverage = self._extract_coverage(body)
        if coverage:
            result['coverage'] = coverage

        return result

    def _extract_status(self, body: str) -> str:
        """提取构建状态"""
        body_lower = body.lower()

        # 成功模式
        success_patterns = [
            r'all\s+checks\s+have\s+passed',
            r'\d+\s+successful\s+checks',
            r'✅',
            r'✔️?',
            r'workflow\s+run\s+(passed|succeeded)',
        ]
        for pattern in success_patterns:
            if re.search(pattern, body_lower):
                return 'success'

        # 失败模式
        failure_patterns = [
            r'\d+\s+check(s)?\s+failed',
            r'workflow\s+run\s+failed',
            r'❌',
            r'✗',
        ]
        for pattern in failure_patterns:
            if re.search(pattern, body_lower):
                return 'failed'

        return 'unknown'

    def _extract_checks(self, body: str) -> Optional[Dict[str, Any]]:
        """提取检查统计"""
        result = {}

        # 提取成功检查数
        success_match = re.search(r'(\d+)\s+successful\s+checks?', body)
        if success_match:
            result['passed'] = int(success_match.group(1))

        # 提取失败检查数
        failed_match = re.search(r'(\d+)\s+failed\s+checks?', body)
        if failed_match:
            result['failed'] = int(failed_match.group(1))

        # 提取跳过检查数
        skipped_match = re.search(r'(\d+)\s+skipped\s+checks?', body)
        if skipped_match:
            result['skipped'] = int(skipped_match.group(1))

        return result if result else None

    def _extract_coverage(self, body: str) -> Optional[Dict[str, Any]]:
        """提取覆盖率"""
        result = {}

        # Codecov 格式: Coverage: 85.5%
        coverage_match = re.search(r'coverage[:\s]+(\d+\.?\d*)%', body, re.IGNORECASE)
        if coverage_match:
            result['percentage'] = float(coverage_match.group(1))

        return result if result else None

    def _extract_url(self, body: str) -> Optional[str]:
        """提取 GitHub Actions URL"""
        match = re.search(r'https?://github\.com/[^/]+/[^/]+/actions/runs/\d+', body)
        if match:
            return match.group(0)
        return None