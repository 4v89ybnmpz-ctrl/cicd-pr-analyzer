"""
数据清洗服务
清洗和标准化评论数据
"""
import re
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class DataCleaner:
    """
    数据清洗器
    清洗和标准化 PR 评论数据
    """

    def __init__(self):
        """初始化数据清洗器"""
        # 需要移除的无效字符
        self.invalid_chars_pattern = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]')

        # HTML 标签清理
        self.html_tag_pattern = re.compile(r'<[^>]+>')

        # 多余空白清理
        self.whitespace_pattern = re.compile(r'\s+')

        logger.info("数据清洗器初始化完成")

    def clean_comment(self, comment: Dict[str, Any]) -> Dict[str, Any]:
        """
        清洗单条评论数据
        :param comment: 原始评论数据
        :return: 清洗后的评论数据
        """
        if not comment:
            return {}

        cleaned = comment.copy()

        # 清洗评论文本
        if 'body' in cleaned:
            cleaned['body'] = self._clean_text(cleaned['body'])

        # 清洗用户信息
        if 'user' in cleaned and isinstance(cleaned['user'], dict):
            cleaned['user'] = self._clean_user_info(cleaned['user'])

        # 标准化时间格式
        for time_field in ['created_at', 'updated_at']:
            if time_field in cleaned:
                cleaned[time_field] = self._normalize_time(cleaned[time_field])

        # 添加清洗标记
        cleaned['_cleaned'] = True
        cleaned['_cleaned_at'] = datetime.now().isoformat()

        return cleaned

    def clean_comments_batch(self, comments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        批量清洗评论数据
        :param comments: 评论列表
        :return: 清洗后的评论列表
        """
        cleaned = []
        for comment in comments:
            try:
                cleaned_comment = self.clean_comment(comment)
                if cleaned_comment:
                    cleaned.append(cleaned_comment)
            except Exception as e:
                logger.warning(f"清洗评论失败: {e}")
                # 保留原始数据，添加错误标记
                failed_comment = comment.copy()
                failed_comment['_clean_error'] = str(e)
                cleaned.append(failed_comment)

        logger.info(f"批量清洗完成，共 {len(cleaned)} 条评论")
        return cleaned

    def _clean_text(self, text: str) -> str:
        """
        清洗文本内容
        :param text: 原始文本
        :return: 清洗后的文本
        """
        if not text:
            return ""

        # 移除无效字符
        text = self.invalid_chars_pattern.sub('', text)

        # 移除 HTML 标签（保留内容）
        text = self.html_tag_pattern.sub('', text)

        # 压缩多余空白
        text = self.whitespace_pattern.sub(' ', text)

        # 去除首尾空白
        text = text.strip()

        return text

    def _clean_user_info(self, user: Dict[str, Any]) -> Dict[str, Any]:
        """
        清洗用户信息
        :param user: 用户信息
        :return: 清洗后的用户信息
        """
        if not user:
            return {}

        cleaned = user.copy()

        # 清洗用户名
        if 'login' in cleaned:
            cleaned['login'] = self._clean_text(cleaned['login'])

        # 清洗显示名称
        if 'name' in cleaned:
            cleaned['name'] = self._clean_text(cleaned['name'])

        # 确保 avatar_url 是有效的
        if 'avatar_url' in cleaned:
            url = cleaned['avatar_url']
            if not url or not url.startswith('http'):
                cleaned['avatar_url'] = None

        return cleaned

    def _normalize_time(self, time_str: str) -> Optional[str]:
        """
        标准化时间格式
        :param time_str: 时间字符串
        :return: ISO 格式时间字符串
        """
        if not time_str:
            return None

        try:
            # 如果已经是 ISO 格式，直接返回
            if 'T' in time_str:
                # 尝试解析并重新格式化
                dt = datetime.fromisoformat(time_str.replace('Z', '+00:00'))
                return dt.isoformat()

            # 尝试其他常见格式
            for fmt in ['%Y-%m-%d %H:%M:%S', '%Y/%m/%d %H:%M:%S']:
                try:
                    dt = datetime.strptime(time_str, fmt)
                    return dt.isoformat()
                except ValueError:
                    continue

            return time_str
        except Exception as e:
            logger.warning(f"时间格式化失败: {time_str} - {e}")
            return time_str

    def extract_comment_metadata(self, comment: Dict[str, Any]) -> Dict[str, Any]:
        """
        提取评论元数据
        :param comment: 评论数据
        :return: 元数据
        """
        body = comment.get('body', '')

        metadata = {
            'length': len(body),
            'word_count': len(body.split()) if body else 0,
            'has_code': '```' in body or '`' in body,
            'has_link': 'http' in body or 'www.' in body,
            'has_mention': '@' in body,
            'has_emoji': any(c for c in body if ord(c) > 127 and not c.isalpha()),
            'is_empty': len(body.strip()) == 0,
            'is_bot': comment.get('is_bot', False),
            'user_type': comment.get('user_type', 'User'),
        }

        return metadata

    def filter_valid_comments(self, comments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        过滤有效评论（排除空评论、系统评论等）
        :param comments: 评论列表
        :return: 有效评论列表
        """
        valid = []
        for comment in comments:
            body = comment.get('body', '').strip()

            # 跳过空评论
            if not body:
                continue

            # 跳过过短评论（可能是无意义回复）
            if len(body) < 3:
                continue

            # 跳过系统评论（通常由特定模式标识）
            if comment.get('user_type') == 'Bot' and self._is_system_bot_comment(body):
                continue

            valid.append(comment)

        return valid

    def _is_system_bot_comment(self, body: str) -> bool:
        """
        判断是否为系统 Bot 评论
        :param body: 评论文本
        :return: 是否为系统评论
        """
        system_patterns = [
            r'^This branch was successfully merged',
            r'^Merged automatically',
            r'^This PR was closed',
            r'^Created by',
            r'^Deployed to',
        ]

        for pattern in system_patterns:
            if re.match(pattern, body, re.IGNORECASE):
                return True

        return False