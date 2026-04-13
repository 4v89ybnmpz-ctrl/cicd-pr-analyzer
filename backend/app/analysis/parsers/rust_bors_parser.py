"""
Rust Bors CI 解析器
解析 rust-lang/rust 项目中 rust-bors[bot] 的 CI 评论格式

支持的格式:
- :pushpin: Commit xxx has been approved by `user` (已批准/排队)
- :hourglass: Testing commit xxx with merge yyy... (正在测试)
- :hourglass: Trying commit xxx with merge yyy… (Try build)
- :sunny: Test successful - [CI](url) Duration: `3h 9m 26s` (测试成功)
- :sunny: Try build successful ([CI](url)) (Try build 成功)
- :broken_heart: Test for xxx failed: [CI](url) Failed job: ... (测试失败)
- This pull request was unapproved... (取消批准)
"""
import re
import json
import logging
from typing import Dict, Any
from .base_parser import BaseCICDParser

logger = logging.getLogger(__name__)


class RustBorsParser(BaseCICDParser):
    """
    Rust Bors CI 解析器
    解析 rust-lang/rust 项目使用 bors 合并机器人的 CI 评论
    """

    name = "rust-bors"
    priority = 8  # 比 nvidia-cccl(10) 更高优先级

    def __init__(self):
        super().__init__()

    def can_parse(self, body: str, user: str = "") -> bool:
        """判断是否为 rust-bors 格式评论"""
        if not body:
            return False

        # 检查用户名
        if 'bors' in user.lower():
            return True

        # 检查内容特征：bors 特有的 emoji + 关键词组合
        bors_patterns = [
            r':pushpin:\s+Commit\s+\w+\s+has been approved',
            r':hourglass:\s+Testing commit\s+\w+',
            r':hourglass:\s+Trying commit\s+\w+',
            r':sunny:\s+Test successful',
            r':sunny:\s+Try build successful',
            r':broken_heart:\s+Test for\s+\w+\s+failed',
            r'homu:\s*\{',  # homu 元数据标记
        ]

        for pattern in bors_patterns:
            if re.search(pattern, body):
                return True

        return False

    def parse(self, body: str, user: str = "") -> Dict[str, Any]:
        """解析 rust-bors CI 评论"""
        result = {
            "parser": self.name,
            "build_status": "unknown",
            "duration": None,
            "duration_seconds": None,
            "commit": None,
            "merge_commit": None,
            "approver": None,
            "url": None,
            "failed_jobs": [],
            "build_type": None,  # "try" 或 "test"
        }

        if not body:
            return result

        # 提取 commit hash
        result["commit"] = self._extract_commit(body)
        result["merge_commit"] = self._extract_merge_commit(body)

        # 提取 CI URL
        result["url"] = self._extract_url(body)

        # 按格式分类解析
        if body.startswith(':pushpin:'):
            self._parse_approved(body, result)
        elif body.startswith(':hourglass:'):
            self._parse_testing(body, result)
        elif body.startswith(':sunny:'):
            self._parse_success(body, result)
        elif body.startswith(':broken_heart:'):
            self._parse_failed(body, result)
        elif 'unapproved' in body or 'closed' in body:
            result["build_status"] = "cancelled"
            result["build_type"] = "unapproved"

        # 提取 homu 元数据
        homu_data = self._extract_homu_metadata(body)
        if homu_data:
            result["homu_type"] = homu_data.get("type")
            if homu_data.get("merge_sha") and not result["merge_commit"]:
                result["merge_commit"] = homu_data["merge_sha"]

        return result

    def _extract_commit(self, body: str) -> str:
        """提取 commit hash"""
        # :pushpin: Commit xxx has been approved
        m = re.search(r'Commit\s+([0-9a-f]{7,40})\s+has been approved', body)
        if m:
            return m.group(1)

        # :hourglass: Testing/Trying commit xxx
        m = re.search(r'(?:Testing|Trying)\s+commit\s+([0-9a-f]{7,40})', body)
        if m:
            return m.group(1)

        # Build commit: xxx
        m = re.search(r'Build commit:\s+([0-9a-f]{7,40})', body)
        if m:
            return m.group(1)

        return None

    def _extract_merge_commit(self, body: str) -> str:
        """提取 merge commit hash"""
        # with merge xxx
        m = re.search(r'with\s+merge\s+([0-9a-f]{7,40})', body)
        if m:
            return m.group(1)

        # Pushing xxx to `main`
        m = re.search(r'Pushing\s+([0-9a-f]{7,40})\s+to\s+`', body)
        if m:
            return m.group(1)

        return None

    def _extract_url(self, body: str) -> str:
        """提取 CI/CD URL"""
        # **Workflow**: https://...
        m = re.search(r'\*\*Workflow\*\*:\s+(https?://\S+)', body)
        if m:
            return m.group(1)

        # [CI](https://...)
        m = re.search(r'\[CI\]\((https?://[^)]+)\)', body)
        if m:
            return m.group(1)

        # bors queue URL
        m = re.search(r'\[queue\]\((https?://bors\.rust-lang\.org/[^)]+)\)', body)
        if m:
            return m.group(1)

        return super()._extract_url(body)

    def _parse_approved(self, body: str, result: Dict[str, Any]):
        """解析已批准/排队格式"""
        result["build_status"] = "queued"
        result["build_type"] = "approved"

        # 提取批准人
        m = re.search(r'approved by\s+`(\S+)`', body)
        if m:
            result["approver"] = m.group(1)

    def _parse_testing(self, body: str, result: Dict[str, Any]):
        """解析正在测试格式"""
        result["build_status"] = "running"

        if 'Trying commit' in body:
            result["build_type"] = "try"
        else:
            result["build_type"] = "test"

    def _parse_success(self, body: str, result: Dict[str, Any]):
        """解析测试成功格式"""
        result["build_status"] = "success"

        if 'Try build successful' in body:
            result["build_type"] = "try"
        else:
            result["build_type"] = "test"

        # 提取批准人
        m = re.search(r'Approved by:\s+`(\S+)`', body)
        if m:
            result["approver"] = m.group(1)

        # 提取耗时: Duration: `3h 9m 26s`
        m = re.search(r'Duration:\s+`([^`]+)`', body)
        if m:
            result["duration"] = m.group(1).strip()
            result["duration_seconds"] = self._parse_duration(m.group(1))

    def _parse_failed(self, body: str, result: Dict[str, Any]):
        """解析测试失败格式"""
        result["build_status"] = "failed"

        if 'Try' in body[:50]:
            result["build_type"] = "try"
        else:
            result["build_type"] = "test"

        # 提取失败的 job 列表
        # - `auto - dist-i586-gnu-i586-i686-musl` ([web logs](url), ...)
        failed_jobs = re.findall(r'-\s+`([^`]+)`\s+\(', body)
        if failed_jobs:
            result["failed_jobs"] = failed_jobs

    def _parse_duration(self, duration_str: str) -> int:
        """解析耗时字符串为秒数"""
        total_seconds = 0

        # 匹配 Xh
        m = re.search(r'(\d+)h', duration_str)
        if m:
            total_seconds += int(m.group(1)) * 3600

        # 匹配 Xm
        m = re.search(r'(\d+)m', duration_str)
        if m:
            total_seconds += int(m.group(1)) * 60

        # 匹配 Xs
        m = re.search(r'(\d+)s', duration_str)
        if m:
            total_seconds += int(m.group(1))

        return total_seconds if total_seconds > 0 else None

    def _extract_homu_metadata(self, body: str) -> Dict[str, Any]:
        """提取 homu 元数据 (HTML 注释中的 JSON)"""
        m = re.search(r'<!--\s*homu:\s*(\{[^}]+\})\s*-->', body)
        if m:
            try:
                return json.loads(m.group(1))
            except Exception:
                pass
        return None
