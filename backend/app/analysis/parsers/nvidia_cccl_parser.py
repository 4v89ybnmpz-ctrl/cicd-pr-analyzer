"""
NVIDIA CCCL CI 解析器
解析 NVIDIA CCCL 项目的 CI 结果格式
"""
import re
import logging
from typing import Dict, Any, Optional
from .base_parser import BaseCICDParser

logger = logging.getLogger(__name__)


class NvidiaCcclParser(BaseCICDParser):
    """
    NVIDIA CCCL CI 解析器

    解析格式示例:
    ## 🥳 CI Workflow Results

    ### 🟩 Finished in 52m 49s: Pass: 100%/48  | Total: 21h 13m | Max: 42m 34s | Hits:  53%/26011

    See results [here](https://github.com/NVIDIA/cccl/actions/runs/23619126945).
    """

    name = "nvidia-cccl"
    priority = 10  # 高优先级

    patterns = [
        r'##\s*[🥳😬]\s*CI Workflow Results',
    ]

    def can_parse(self, body: str, user: str = "") -> bool:
        """判断是否为 NVIDIA CCCL 格式"""
        return 'CI Workflow Results' in body and ('🥳' in body or '😬' in body)

    def parse(self, body: str, user: str = "") -> Dict[str, Any]:
        """解析 NVIDIA CCCL CI 结果"""
        result = {
            'parser': self.name,
            'build_status': self._extract_status(body),
            'duration': None,
            'duration_seconds': None,
            'pass_rate': None,
            'pass_count': None,
            'total_time': None,
            'total_time_seconds': None,
            'max_time': None,
            'max_time_seconds': None,
            'hits_rate': None,
            'hits_count': None,
            'url': self._extract_url(body),
        }

        # 提取 Finished in 时间
        finished_match = re.search(
            r'Finished in\s+((\d+)h\s+)?((\d+)m\s+)?((\d+)s)?',
            body
        )
        if finished_match:
            hours = int(finished_match.group(2) or 0)
            minutes = int(finished_match.group(4) or 0)
            seconds = int(finished_match.group(6) or 0)
            result['duration_seconds'] = hours * 3600 + minutes * 60 + seconds
            result['duration'] = self._format_duration(hours, minutes, seconds)

        # 提取 Pass: XX%/XX
        pass_match = re.search(r'Pass:\s*(\d+\.?\d*)%/(\d+)', body)
        if pass_match:
            result['pass_rate'] = float(pass_match.group(1))
            result['pass_count'] = int(pass_match.group(2))

        # 提取 Total 时间
        total_match = re.search(r'Total:\s*(\d+)h\s+(\d+)m', body)
        if total_match:
            hours = int(total_match.group(1))
            minutes = int(total_match.group(2))
            result['total_time_seconds'] = hours * 3600 + minutes * 60
            result['total_time'] = f"{hours}h {minutes}m"

        # 提取 Max 时间
        max_match = re.search(r'Max:\s*((\d+)h\s+)?((\d+)m\s+)?((\d+)s)?', body)
        if max_match:
            hours = int(max_match.group(2) or 0)
            minutes = int(max_match.group(4) or 0)
            seconds = int(max_match.group(6) or 0)
            result['max_time_seconds'] = hours * 3600 + minutes * 60 + seconds
            result['max_time'] = self._format_duration(hours, minutes, seconds)

        # 提取 Hits: XX%/XXXXX
        hits_match = re.search(r'Hits:\s*(\d+\.?\d*)%/(\d+)', body)
        if hits_match:
            result['hits_rate'] = float(hits_match.group(1))
            result['hits_count'] = int(hits_match.group(2))

        return result

    def _extract_status(self, body: str) -> str:
        """提取构建状态"""
        # 通过 emoji 判断
        if '🟩' in body and 'Finished in' in body:
            return 'success'
        if '🟥' in body and 'Finished in' in body:
            return 'failed'
        if '🥳' in body:
            return 'success'
        if '😬' in body:
            return 'failed'
        return 'unknown'

    def _format_duration(self, hours: int, minutes: int, seconds: int) -> str:
        """格式化时长"""
        parts = []
        if hours:
            parts.append(f"{hours}h")
        if minutes:
            parts.append(f"{minutes}m")
        if seconds:
            parts.append(f"{seconds}s")
        return ' '.join(parts) if parts else '0s'

    def _extract_url(self, body: str) -> Optional[str]:
        """提取 GitHub Actions URL"""
        match = re.search(r'https?://github\.com/[^/]+/[^/]+/actions/runs/\d+', body)
        if match:
            return match.group(0)
        return None