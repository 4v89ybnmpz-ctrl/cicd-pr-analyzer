"""
GitCode PR 服务模块
负责从 GitCode API 获取 PR 数据
GitCode 基于 GitLab，使用 GitLab API 风格
"""
import requests
import threading
import time
from typing import Dict, Any, List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging
from functools import wraps
import re

logger = logging.getLogger(__name__)


def retry_on_failure(max_retries: int = 3, delay: int = 5):
    """
    重试装饰器
    :param max_retries: 最大重试次数
    :param delay: 重试间隔（秒）
    :return: 装饰器函数
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        logger.warning(f"GitCode 请求失败 (尝试 {attempt + 1}/{max_retries}): {e}, {delay}秒后重试...")
                        time.sleep(delay)
                    else:
                        logger.error(f"GitCode 请求失败，已达到最大重试次数 {max_retries}: {e}")
            raise last_exception
        return wrapper
    return decorator


class GitCodeTokenPool:
    """
    GitCode Token 池管理类
    支持多个 Token 轮询使用
    """

    def __init__(self, tokens: List[str]):
        """
        初始化 Token 池
        :param tokens: Token 列表
        """
        self.tokens = tokens if tokens else []
        self.current_index = 0
        self.lock = threading.Lock()
        logger.info(f"GitCode Token 池初始化完成，共 {len(self.tokens)} 个 Token")

    def get_token(self) -> Optional[str]:
        """
        获取下一个可用的 Token
        :return: Token 字符串
        """
        if not self.tokens:
            return None

        with self.lock:
            token = self.tokens[self.current_index]
            self.current_index = (self.current_index + 1) % len(self.tokens)
            return token

    def add_token(self, token: str):
        """添加 Token"""
        with self.lock:
            if token not in self.tokens:
                self.tokens.append(token)
                logger.info(f"GitCode Token 已添加，当前共 {len(self.tokens)} 个 Token")

    def get_stats(self) -> Dict[str, Any]:
        """获取 Token 池统计信息"""
        with self.lock:
            return {
                "total_tokens": len(self.tokens),
                "current_index": self.current_index
            }


class GitCodePRService:
    """
    GitCode PR 服务类
    GitCode 基于 GitLab，使用 GitLab API 风格
    GitCode API 文档: https://gitcode.net/help/api/merge_requests.md
    """

    def __init__(self, token_pool: GitCodeTokenPool, api_settings: Dict[str, Any]):
        """
        初始化 GitCode PR 服务
        :param token_pool: Token 池
        :param api_settings: API 设置
        """
        self.token_pool = token_pool
        self.api_settings = api_settings
        # GitCode API 基础 URL
        self.base_url = api_settings.get("base_url", "https://gitcode.net/api/v4")
        self.per_page = api_settings.get("per_page", 100)
        self.state = api_settings.get("state", "all")  # opened, closed, merged, all
        self.request_delay = api_settings.get("request_delay", 0.5)
        self.max_workers = api_settings.get("max_workers", 3)
        self.max_retries = 3
        self.retry_delay = 5
        logger.info(f"GitCode PR 服务初始化完成，Base URL: {self.base_url}")

        # 已知的 Bot 用户名模式
        self.known_bot_patterns = [
            "gitcode-bot",
            "renovate-bot",
            "dependabot",
            "semantic-release-bot",
            "greenkeeper",
            "codecov-bot",
        ]

        # Bot 命名正则模式
        self.bot_regex_patterns = [
            r".*-bot$",
            r".*\[bot\]$",
            r".*_bot$",
            r"^bot-.*",
        ]

    def _get_headers(self) -> Dict[str, str]:
        """
        获取请求头
        :return: 请求头字典
        """
        token = self.token_pool.get_token()
        headers = {
            "Accept": "application/json",
        }
        if token:
            # GitCode 使用 Private-Token 头
            headers["Private-Token"] = token
        return headers

    def _is_bot_user(self, username: str, user_type: str = None) -> bool:
        """
        判断用户是否为 Bot
        :param username: 用户名
        :param user_type: 用户类型
        :return: 是否为 Bot
        """
        if not username:
            return False

        # 检查用户类型
        if user_type and user_type.lower() == "bot":
            return True

        # 检查已知 Bot 模式
        if username.lower() in [p.lower() for p in self.known_bot_patterns]:
            return True

        # 检查正则模式
        for pattern in self.bot_regex_patterns:
            if re.match(pattern, username, re.IGNORECASE):
                return True

        return False

    def _encode_project_path(self, owner: str, repo: str) -> str:
        """
        编码项目路径（GitLab API 需要URL编码的项目ID）
        :param owner: 所有者
        :param repo: 仓库名
        :return: 编码后的项目路径
        """
        import urllib.parse
        return urllib.parse.quote(f"{owner}/{repo}", safe='')

    @retry_on_failure(max_retries=3, delay=5)
    def fetch_merge_requests(self, owner: str, repo: str, state: str = None,
                             page: int = 1, per_page: int = None) -> Dict[str, Any]:
        """
        获取合并请求列表（GitCode/GitLab 称 MR，等同于 PR）
        :param owner: 项目所有者/命名空间
        :param repo: 项目名称
        :param state: MR 状态 (opened, closed, merged, all)
        :param page: 页码
        :param per_page: 每页数量
        :return: MR 列表数据
        """
        project_path = self._encode_project_path(owner, repo)
        url = f"{self.base_url}/projects/{project_path}/merge_requests"

        params = {
            "page": page,
            "per_page": per_page or self.per_page,
        }

        # 状态筛选
        if state or self.state != "all":
            params["state"] = state or self.state

        logger.info(f"获取 GitCode MR: {owner}/{repo}, page={page}")

        headers = self._get_headers()
        response = requests.get(url, headers=headers, params=params, timeout=30)

        if response.status_code != 200:
            logger.error(f"获取 GitCode MR 失败: {response.status_code} - {response.text}")
            return {
                "owner": owner,
                "repo": repo,
                "merge_requests": [],
                "error": f"HTTP {response.status_code}: {response.text[:200]}"
            }

        data = response.json()

        # 格式化 MR 数据
        merge_requests = []
        for mr in data:
            formatted_mr = self._format_merge_request(mr)
            merge_requests.append(formatted_mr)

        # 获取分页信息
        total_count = int(response.headers.get("X-Total", 0))
        total_pages = int(response.headers.get("X-Total-Pages", 0))

        time.sleep(self.request_delay)

        return {
            "owner": owner,
            "repo": repo,
            "merge_requests": merge_requests,
            "total_count": total_count,
            "total_pages": total_pages,
            "current_page": page,
            "error": None
        }

    def _format_merge_request(self, mr: Dict[str, Any]) -> Dict[str, Any]:
        """
        格式化合并请求数据
        :param mr: 原始 MR 数据
        :return: 格式化后的 MR 数据
        """
        author = mr.get("author", {})
        author_username = author.get("username", "")

        return {
            "iid": mr.get("iid"),  # MR 内部ID
            "id": mr.get("id"),    # MR 全局ID
            "title": mr.get("title"),
            "description": mr.get("description"),
            "state": mr.get("state"),  # opened, closed, merged
            "merged": mr.get("state") == "merged",
            "draft": mr.get("draft", False),
            "work_in_progress": mr.get("work_in_progress", False),
            "author": {
                "id": author.get("id"),
                "username": author_username,
                "name": author.get("name"),
                "avatar_url": author.get("avatar_url"),
                "type": "Bot" if self._is_bot_user(author_username) else "User"
            },
            "source_branch": mr.get("source_branch"),
            "target_branch": mr.get("target_branch"),
            "created_at": mr.get("created_at"),
            "updated_at": mr.get("updated_at"),
            "merged_at": mr.get("merged_at"),
            "closed_at": mr.get("closed_at"),
            "labels": mr.get("labels", []),
            "upvotes": mr.get("upvotes", 0),
            "downvotes": mr.get("downvotes", 0),
            "user_notes_count": mr.get("user_notes_count", 0),  # 评论数
            "web_url": mr.get("web_url"),
            "is_bot": self._is_bot_user(author_username)
        }

    @retry_on_failure(max_retries=3, delay=5)
    def fetch_mr_comments(self, owner: str, repo: str, mr_iid: int) -> Dict[str, Any]:
        """
        获取合并请求评论
        :param owner: 项目所有者
        :param repo: 项目名称
        :param mr_iid: MR 内部ID
        :return: 评论数据
        """
        project_path = self._encode_project_path(owner, repo)
        url = f"{self.base_url}/projects/{project_path}/merge_requests/{mr_iid}/notes"

        logger.info(f"获取 GitCode MR 评论: {owner}/{repo} !{mr_iid}")

        headers = self._get_headers()
        response = requests.get(url, headers=headers, timeout=30)

        if response.status_code != 200:
            logger.error(f"获取 GitCode MR 评论失败: {response.status_code}")
            return {
                "owner": owner,
                "repo": repo,
                "mr_iid": mr_iid,
                "comments": [],
                "error": f"HTTP {response.status_code}"
            }

        data = response.json()

        # 格式化评论
        comments = []
        for note in data:
            # 跳过系统评论（GitLab 系统生成的笔记）
            if note.get("system", False):
                continue

            formatted_comment = self._format_comment(note)
            comments.append(formatted_comment)

        time.sleep(self.request_delay)

        return {
            "owner": owner,
            "repo": repo,
            "mr_iid": mr_iid,
            "comments": comments,
            "total_count": len(comments),
            "error": None
        }

    def _format_comment(self, note: Dict[str, Any]) -> Dict[str, Any]:
        """
        格式化评论数据
        :param note: 原始笔记数据
        :return: 格式化后的评论
        """
        author = note.get("author", {})
        author_username = author.get("username", "")
        is_bot = self._is_bot_user(author_username)

        return {
            "id": note.get("id"),
            "body": note.get("body"),
            "created_at": note.get("created_at"),
            "updated_at": note.get("updated_at"),
            "user": author_username,
            "user_id": author.get("id"),
            "user_name": author.get("name"),
            "user_type": "Bot" if is_bot else "User",
            "avatar_url": author.get("avatar_url"),
            "is_bot": is_bot,
            "resolvable": note.get("resolvable", False),
            "resolved": note.get("resolved", False),
            "type": note.get("type", "DiscussionNote"),  # DiscussionNote, DiffNote
            "position": note.get("position")  # 代码位置信息
        }

    @retry_on_failure(max_retries=3, delay=5)
    def fetch_mr_detail(self, owner: str, repo: str, mr_iid: int) -> Dict[str, Any]:
        """
        获取合并请求详细信息
        :param owner: 项目所有者
        :param repo: 项目名称
        :param mr_iid: MR 内部ID
        :return: MR 详细信息
        """
        project_path = self._encode_project_path(owner, repo)
        url = f"{self.base_url}/projects/{project_path}/merge_requests/{mr_iid}"

        logger.info(f"获取 GitCode MR 详情: {owner}/{repo} !{mr_iid}")

        headers = self._get_headers()
        response = requests.get(url, headers=headers, timeout=30)

        if response.status_code != 200:
            logger.error(f"获取 GitCode MR 详情失败: {response.status_code}")
            return {
                "owner": owner,
                "repo": repo,
                "mr_iid": mr_iid,
                "detail": None,
                "error": f"HTTP {response.status_code}"
            }

        data = response.json()
        detail = self._format_mr_detail(data)

        time.sleep(self.request_delay)

        return {
            "owner": owner,
            "repo": repo,
            "mr_iid": mr_iid,
            "detail": detail,
            "error": None
        }

    def _format_mr_detail(self, mr: Dict[str, Any]) -> Dict[str, Any]:
        """
        格式化 MR 详细信息
        :param mr: 原始 MR 数据
        :return: 格式化后的详细信息
        """
        author = mr.get("author", {})
        merge_user = mr.get("merged_by", {})
        assignees = mr.get("assignees", [])
        reviewers = mr.get("reviewers", [])

        return {
            "iid": mr.get("iid"),
            "id": mr.get("id"),
            "title": mr.get("title"),
            "description": mr.get("description"),
            "state": mr.get("state"),
            "draft": mr.get("draft", False),
            "author": {
                "id": author.get("id"),
                "username": author.get("username"),
                "name": author.get("name"),
                "avatar_url": author.get("avatar_url")
            },
            "source_branch": mr.get("source_branch"),
            "target_branch": mr.get("target_branch"),
            "source_project_id": mr.get("source_project_id"),
            "target_project_id": mr.get("target_project_id"),
            "labels": mr.get("labels", []),
            "assignees": [
                {
                    "id": a.get("id"),
                    "username": a.get("username"),
                    "name": a.get("name")
                } for a in assignees
            ],
            "reviewers": [
                {
                    "id": r.get("id"),
                    "username": r.get("username"),
                    "name": r.get("name")
                } for r in reviewers
            ],
            "milestone": mr.get("milestone"),
            "created_at": mr.get("created_at"),
            "updated_at": mr.get("updated_at"),
            "merged_at": mr.get("merged_at"),
            "closed_at": mr.get("closed_at"),
            "merged_by": {
                "id": merge_user.get("id"),
                "username": merge_user.get("username"),
                "name": merge_user.get("name")
            } if merge_user else None,
            "merge_status": mr.get("merge_status"),  # can_be_merged, cannot_be_merged
            "detailed_merge_status": mr.get("detailed_merge_status"),
            "merge_commit_sha": mr.get("merge_commit_sha"),
            "squash_commit_sha": mr.get("squash_commit_sha"),
            "head_sha": mr.get("sha"),
            "changes_count": mr.get("changes_count"),
            "user_notes_count": mr.get("user_notes_count", 0),
            "upvotes": mr.get("upvotes", 0),
            "downvotes": mr.get("downvotes", 0),
            "pipeline_status": mr.get("head_pipeline", {}).get("status") if mr.get("head_pipeline") else None,
            "web_url": mr.get("web_url"),
            "reference": mr.get("reference"),  # 简短引用，如 !123
            "time_stats": mr.get("time_stats"),  # 时间统计
            "has_conflicts": mr.get("has_conflicts", False),
            "blocking_discussions_resolved": mr.get("blocking_discussions_resolved", True)
        }

    @retry_on_failure(max_retries=3, delay=5)
    def fetch_mr_changes(self, owner: str, repo: str, mr_iid: int) -> Dict[str, Any]:
        """
        获取合并请求代码变更
        :param owner: 项目所有者
        :param repo: 项目名称
        :param mr_iid: MR 内部ID
        :return: 代码变更数据
        """
        project_path = self._encode_project_path(owner, repo)
        url = f"{self.base_url}/projects/{project_path}/merge_requests/{mr_iid}/changes"

        logger.info(f"获取 GitCode MR 变更: {owner}/{repo} !{mr_iid}")

        headers = self._get_headers()
        response = requests.get(url, headers=headers, timeout=30)

        if response.status_code != 200:
            return {
                "owner": owner,
                "repo": repo,
                "mr_iid": mr_iid,
                "changes": [],
                "error": f"HTTP {response.status_code}"
            }

        data = response.json()
        changes = data.get("changes", [])

        formatted_changes = []
        for change in changes:
            formatted_changes.append({
                "old_path": change.get("old_path"),
                "new_path": change.get("new_path"),
                "diff": change.get("diff"),
                "new_file": change.get("new_file", False),
                "renamed_file": change.get("renamed_file", False),
                "deleted_file": change.get("deleted_file", False)
            })

        time.sleep(self.request_delay)

        return {
            "owner": owner,
            "repo": repo,
            "mr_iid": mr_iid,
            "changes": formatted_changes,
            "changes_count": len(formatted_changes),
            "error": None
        }

    def fetch_all_mr_comments(self, owner: str, repo: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        并发获取所有 MR 的评论
        :param owner: 项目所有者
        :param repo: 项目名称
        :param limit: MR 数量限制
        :return: 所有 MR 评论列表
        """
        logger.info(f"并发获取 GitCode {owner}/{repo} 所有 MR 评论，限制: {limit}")

        # 先获取 MR 列表
        mr_data = self.fetch_merge_requests(owner, repo, state="all", per_page=limit)
        merge_requests = mr_data.get("merge_requests", [])

        if not merge_requests:
            return []

        results = []
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_mr = {
                executor.submit(self.fetch_mr_comments, owner, repo, mr["iid"]): mr
                for mr in merge_requests[:limit]
            }

            for future in as_completed(future_to_mr):
                mr = future_to_mr[future]
                try:
                    comment_data = future.result()
                    results.append({
                        "mr_iid": mr["iid"],
                        "mr_title": mr["title"],
                        "comments": comment_data.get("comments", []),
                        "total_count": comment_data.get("total_count", 0)
                    })
                except Exception as e:
                    logger.error(f"获取 MR !{mr['iid']} 评论失败: {e}")
                    results.append({
                        "mr_iid": mr["iid"],
                        "mr_title": mr["title"],
                        "comments": [],
                        "error": str(e)
                    })

        return results

    def fetch_all_mr_details(self, owner: str, repo: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        并发获取所有 MR 的详细信息
        :param owner: 项目所有者
        :param repo: 项目名称
        :param limit: MR 数量限制
        :return: 所有 MR 详细信息列表
        """
        logger.info(f"并发获取 GitCode {owner}/{repo} 所有 MR 详情，限制: {limit}")

        mr_data = self.fetch_merge_requests(owner, repo, state="all", per_page=limit)
        merge_requests = mr_data.get("merge_requests", [])

        if not merge_requests:
            return []

        results = []
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_mr = {
                executor.submit(self.fetch_mr_detail, owner, repo, mr["iid"]): mr
                for mr in merge_requests[:limit]
            }

            for future in as_completed(future_to_mr):
                mr = future_to_mr[future]
                try:
                    detail_data = future.result()
                    results.append(detail_data)
                except Exception as e:
                    logger.error(f"获取 MR !{mr['iid']} 详情失败: {e}")
                    results.append({
                        "mr_iid": mr["iid"],
                        "error": str(e)
                    })

        return results