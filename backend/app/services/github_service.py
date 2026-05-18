"""
GitHub PR 服务模块
负责从 GitHub API 获取 PR 数据
"""
import requests
import threading
import time
from typing import Dict, Any, List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging
from functools import wraps

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
                        logger.warning(f"请求失败 (尝试 {attempt + 1}/{max_retries}): {e}, {delay}秒后重试...")
                        time.sleep(delay)
                    else:
                        logger.error(f"请求失败，已达到最大重试次数 {max_retries}: {e}")
            raise last_exception
        return wrapper
    return decorator


class TokenPool:
    """
    Token 池管理类
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
        logger.info(f"Token 池初始化完成，共 {len(self.tokens)} 个 Token")

    def get_token(self) -> Optional[str]:
        """
        获取下一个可用的 Token
        :return: Token 字符串，如果没有可用 Token 则返回 None
        """
        if not self.tokens:
            return None

        with self.lock:
            token = self.tokens[self.current_index]
            self.current_index = (self.current_index + 1) % len(self.tokens)
            return token

    def add_token(self, token: str):
        """
        添加 Token
        :param token: Token 字符串
        """
        with self.lock:
            if token not in self.tokens:
                self.tokens.append(token)
                logger.info(f"Token 已添加，当前共 {len(self.tokens)} 个 Token")

    def remove_token(self, token: str):
        """
        移除 Token
        :param token: Token 字符串
        """
        with self.lock:
            if token in self.tokens:
                self.tokens.remove(token)
                logger.info(f"Token 已移除，当前共 {len(self.tokens)} 个 Token")

    def get_stats(self) -> Dict[str, Any]:
        """
        获取 Token 池统计信息
        :return: 统计信息字典
        """
        with self.lock:
            return {
                "total_tokens": len(self.tokens),
                "current_index": self.current_index
            }


class TaskProgress:
    """
    任务进度管理类
    用于跟踪异步任务的进度
    """

    def __init__(self):
        """初始化任务进度管理器"""
        self.tasks: Dict[str, Dict[str, Any]] = {}
        self.lock = threading.Lock()
        logger.info("任务进度管理器初始化完成")

    def create_task(self, task_id: str, total: int = 100) -> Dict[str, Any]:
        """
        创建新任务
        :param task_id: 任务 ID
        :param total: 总进度
        :return: 任务信息
        """
        task = {
            "task_id": task_id,
            "status": "pending",
            "progress": 0.0,
            "total": total,
            "current": 0,
            "message": "任务已创建",
            "created_at": time.time(),
            "updated_at": time.time()
        }

        with self.lock:
            self.tasks[task_id] = task

        logger.info(f"任务已创建: {task_id}")
        return task

    def update_task(self, task_id: str, current: int, message: str = "") -> Optional[Dict[str, Any]]:
        """
        更新任务进度
        :param task_id: 任务 ID
        :param current: 当前进度
        :param message: 进度消息
        :return: 更新后的任务信息
        """
        with self.lock:
            if task_id not in self.tasks:
                return None

            task = self.tasks[task_id]
            task["current"] = current
            task["progress"] = (current / task["total"] * 100) if task["total"] > 0 else 0
            task["message"] = message
            task["updated_at"] = time.time()

            if task["progress"] >= 100:
                task["status"] = "completed"
                task["message"] = "任务已完成"

            return task

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        获取任务信息
        :param task_id: 任务 ID
        :return: 任务信息
        """
        with self.lock:
            return self.tasks.get(task_id)

    def get_all_tasks(self) -> List[Dict[str, Any]]:
        """
        获取所有任务
        :return: 任务列表
        """
        with self.lock:
            return list(self.tasks.values())

    def delete_task(self, task_id: str) -> bool:
        """
        删除任务
        :param task_id: 任务 ID
        :return: 是否删除成功
        """
        with self.lock:
            if task_id in self.tasks:
                del self.tasks[task_id]
                logger.info(f"任务已删除: {task_id}")
                return True
            return False


class GitHubPRService:
    """
    GitHub PR 服务类
    负责从 GitHub API 获取 PR 数据
    """

    def __init__(self, token_pool: TokenPool, api_settings: Dict[str, Any]):
        """
        初始化 GitHub PR 服务
        :param token_pool: Token 池
        :param api_settings: API 设置
        """
        self.token_pool = token_pool
        self.api_settings = api_settings
        self.base_url = api_settings.get("base_url", "https://api.github.com")
        self.per_page = api_settings.get("per_page", 100)
        self.state = api_settings.get("state", "all")
        self.request_delay = api_settings.get("request_delay", 0.5)
        self.max_workers = api_settings.get("max_workers", 3)
        self.max_retries = 3  # 最大重试次数
        self.retry_delay = 5  # 重试间隔（秒）
        logger.info(f"GitHub PR 服务初始化完成，Base URL: {self.base_url}")

        # 已知的 Bot 用户名模式
        self.known_bot_patterns = [
            "github-actions[bot]",
            "dependabot[bot]",
            "renovate[bot]",
            "greenkeeper[bot]",
            "pre-commit-ci[bot]",
            "codecov-io[bot]",
            "coveralls[bot]",
            "snyk-bot",
            "jenkins-bot",
            "circleci",
            "travis-ci",
            "azure-pipelines[bot]",
            "appveyor-ci",
            "cla-assistant[bot]",
            "stale[bot]",
            "mergify[bot]",
            "netlify[bot]",
            "now-integration[bot]",
            "vercel[bot]",
            "imgbot[bot]",
            "allcontributors[bot]",
            "semantic-release-bot",
            "lgtm-com[bot]",
            "deepscan-io[bot]",
            "codacy-badger[bot]",
            "sonarcloud[bot]",
            "scala-steward[bot]",
            "nucleusbot",
            "taichi-bot",
        ]

        # Bot 用户名正则模式
        self.bot_regex_patterns = [
            r".*\[bot\]$",           # xxx[bot]
            r".*-bot$",              # xxx-bot
            r".*_bot$",              # xxx_bot
            r"^bot-.*",              # bot-xxx
            r".*-ci$",               # xxx-ci
            r".*-automation$",       # xxx-automation
            r".*pipeline.*",         # xxxpipelinexxx
        ]

    def _is_bot_user(self, username: str, user_type: str) -> bool:
        """
        判断用户是否为 Bot
        :param username: 用户名
        :param user_type: 用户类型
        :return: 是否为 Bot
        """
        if not username:
            return False

        # 1. GitHub API 直接标记为 Bot 类型
        if user_type == "Bot" or user_type == "Organization":
            return True

        # 2. 检查是否在已知 Bot 列表中
        if username.lower() in [bot.lower() for bot in self.known_bot_patterns]:
            return True

        # 3. 检查是否匹配 Bot 命名模式
        import re
        for pattern in self.bot_regex_patterns:
            if re.match(pattern, username, re.IGNORECASE):
                return True

        return False

    def _make_request(self, url: str, headers: Dict[str, str], params: Dict[str, Any], timeout: int = 30) -> requests.Response:
        """
        发起HTTP请求（带重试机制）
        :param url: 请求URL
        :param headers: 请求头
        :param params: 请求参数
        :param timeout: 超时时间
        :return: 响应对象
        """
        last_exception = None
        for attempt in range(self.max_retries):
            try:
                response = requests.get(url, headers=headers, params=params, timeout=timeout)
                return response
            except requests.exceptions.RequestException as e:
                last_exception = e
                if attempt < self.max_retries - 1:
                    logger.warning(f"请求失败 (尝试 {attempt + 1}/{self.max_retries}): {e}, {self.retry_delay}秒后重试...")
                    time.sleep(self.retry_delay)
                else:
                    logger.error(f"请求失败，已达到最大重试次数 {self.max_retries}: {e}")
        raise last_exception

    def fetch_prs_for_project(self, owner: str, repo: str, max_count: int = 0) -> Dict[str, Any]:
        """
        获取指定项目的 PR 数据
        :param owner: 仓库所有者
        :param repo: 仓库名称
        :param max_count: 最大获取数量，0 表示获取全部
        :return: PR 数据字典
        """
        log_msg = f"开始获取 {owner}/{repo} 的 PR 数据"
        if max_count > 0:
            log_msg += f" (最多 {max_count} 个)"
        logger.info(log_msg)

        all_prs = []
        page = 1
        error = None

        try:
            while True:
                token = self.token_pool.get_token()
                headers = {
                    "Accept": "application/vnd.github.v3+json",
                    "User-Agent": "GitHub-PR-Fetcher"
                }

                if token:
                    headers["Authorization"] = f"token {token}"

                url = f"{self.base_url}/repos/{owner}/{repo}/pulls"
                params = {
                    "state": self.state,
                    "per_page": self.per_page,
                    "page": page
                }

                response = self._make_request(url, headers, params, 30)

                if response.status_code == 404:
                    error = "仓库不存在"
                    logger.warning(f"{owner}/{repo} 仓库不存在")
                    break

                if response.status_code != 200:
                    error = f"API 请求失败: {response.status_code}"
                    logger.error(f"获取 {owner}/{repo} PR 失败: {response.status_code}")
                    break

                prs = response.json()

                if not prs:
                    break

                # 提取 PR 关键信息
                for pr in prs:
                    all_prs.append({
                        "number": pr.get("number"),
                        "title": pr.get("title"),
                        "user": pr.get("user", {}).get("login"),
                        "state": pr.get("state"),
                        "created_at": pr.get("created_at"),
                        "updated_at": pr.get("updated_at"),
                        "url": pr.get("html_url")
                    })

                # 达到最大数量时提前终止
                if max_count > 0 and len(all_prs) >= max_count:
                    all_prs = all_prs[:max_count]
                    break

                page += 1
                time.sleep(self.request_delay)

            logger.info(f"获取 {owner}/{repo} 完成，共 {len(all_prs)} 个 PR")

        except Exception as e:
            error = str(e)
            logger.error(f"获取 {owner}/{repo} PR 数据异常: {e}")

        return {
            "owner": owner,
            "repo": repo,
            "prs": all_prs,
            "total": len(all_prs),
            "error": error
        }

    def fetch_prs_batch(self, projects: List[Dict[str, str]]) -> Dict[str, Any]:
        """
        批量获取多个项目的 PR 数据
        :param projects: 项目列表 [{"owner": "xxx", "repo": "yyy"}, ...]
        :return: 批量获取结果
        """
        logger.info(f"开始批量获取 {len(projects)} 个项目的 PR 数据")

        results = []
        success_count = 0
        failed_count = 0
        total_prs = 0

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(self.fetch_prs_for_project, p["owner"], p["repo"]): p
                for p in projects
            }

            for future in as_completed(futures):
                project = futures[future]
                try:
                    result = future.result()
                    results.append(result)

                    if result["error"] is None:
                        success_count += 1
                        total_prs += result["total"]
                    else:
                        failed_count += 1

                except Exception as e:
                    failed_count += 1
                    results.append({
                        "owner": project["owner"],
                        "repo": project["repo"],
                        "prs": [],
                        "total": 0,
                        "error": str(e)
                    })
                    logger.error(f"获取 {project['owner']}/{project['repo']} 异常: {e}")

        logger.info(f"批量获取完成，成功: {success_count}, 失败: {failed_count}, 总 PR: {total_prs}")

        return {
            "results": results,
            "total_projects": len(projects),
            "success_projects": success_count,
            "failed_projects": failed_count,
            "total_prs": total_prs
        }

    def fetch_pr_comments(self, owner: str, repo: str, pr_number: int) -> Dict[str, Any]:
        """
        获取指定 PR 的所有评论
        :param owner: 仓库所有者
        :param repo: 仓库名称
        :param pr_number: PR 编号
        :return: 评论数据字典
        """
        logger.info(f"开始获取 {owner}/{repo} PR#{pr_number} 的评论")

        all_comments = []
        page = 1
        error = None

        try:
            while True:
                token = self.token_pool.get_token()
                headers = {
                    "Accept": "application/vnd.github.v3+json",
                    "User-Agent": "GitHub-PR-Fetcher"
                }

                if token:
                    headers["Authorization"] = f"token {token}"

                url = f"{self.base_url}/repos/{owner}/{repo}/issues/{pr_number}/comments"
                params = {
                    "per_page": self.per_page,
                    "page": page
                }

                response = self._make_request(url, headers, params, 30)

                if response.status_code == 404:
                    error = "PR不存在"
                    logger.warning(f"{owner}/{repo} PR#{pr_number} 不存在")
                    break

                if response.status_code != 200:
                    error = f"API请求失败: {response.status_code}"
                    logger.error(f"获取 {owner}/{repo} PR#{pr_number} 评论失败: {response.status_code}")
                    break

                comments = response.json()

                if not comments:
                    break

                # 提取评论关键信息（包含完整的用户信息用于识别 Bot）
                for comment in comments:
                    user = comment.get("user", {})
                    user_login = user.get("login", "")
                    user_type = user.get("type", "User")

                    # 识别是否为 Bot
                    is_bot = self._is_bot_user(user_login, user_type)

                    all_comments.append({
                        "id": comment.get("id"),
                        "user": user_login,
                        "user_id": user.get("id"),
                        "user_type": user_type,
                        "avatar_url": user.get("avatar_url"),
                        "is_bot": is_bot,
                        "author_association": comment.get("author_association"),
                        "body": comment.get("body"),
                        "created_at": comment.get("created_at"),
                        "updated_at": comment.get("updated_at"),
                        "url": comment.get("html_url"),
                        "reactions": comment.get("reactions", {}).get("total_count", 0) if comment.get("reactions") else 0
                    })

                page += 1
                time.sleep(self.request_delay)

            logger.info(f"获取 {owner}/{repo} PR#{pr_number} 评论完成，共 {len(all_comments)} 条")

        except Exception as e:
            error = str(e)
            logger.error(f"获取 {owner}/{repo} PR#{pr_number} 评论异常: {e}")

        return {
            "owner": owner,
            "repo": repo,
            "pr_number": pr_number,
            "comments": all_comments,
            "total": len(all_comments),
            "error": error
        }

    def fetch_pr_timeline(self, owner: str, repo: str, pr_number: int) -> Dict[str, Any]:
        """
        获取指定 PR 的时间线事件
        :param owner: 仓库所有者
        :param repo: 仓库名称
        :param pr_number: PR 编号
        :return: 时间线数据字典
        """
        logger.info(f"开始获取 {owner}/{repo} PR#{pr_number} 的时间线")

        all_events = []
        page = 1
        error = None

        try:
            while True:
                token = self.token_pool.get_token()
                headers = {
                    "Accept": "application/vnd.github.v3+json",
                    "User-Agent": "GitHub-PR-Fetcher"
                }

                if token:
                    headers["Authorization"] = f"token {token}"

                url = f"{self.base_url}/repos/{owner}/{repo}/issues/{pr_number}/timeline"
                params = {
                    "per_page": self.per_page,
                    "page": page
                }

                response = self._make_request(url, headers, params, 30)

                if response.status_code == 404:
                    error = "PR不存在"
                    logger.warning(f"{owner}/{repo} PR#{pr_number} 不存在")
                    break

                if response.status_code != 200:
                    error = f"API请求失败: {response.status_code}"
                    logger.error(f"获取 {owner}/{repo} PR#{pr_number} 时间线失败: {response.status_code}")
                    break

                events = response.json()

                if not events:
                    break

                # 提取时间线事件关键信息
                for event in events:
                    all_events.append({
                        "id": event.get("id"),
                        "event": event.get("event"),
                        "actor": event.get("actor", {}).get("login") if event.get("actor") else None,
                        "created_at": event.get("created_at"),
                        "url": event.get("url")
                    })

                page += 1
                time.sleep(self.request_delay)

            logger.info(f"获取 {owner}/{repo} PR#{pr_number} 时间线完成，共 {len(all_events)} 个事件")

        except Exception as e:
            error = str(e)
            logger.error(f"获取 {owner}/{repo} PR#{pr_number} 时间线异常: {e}")

        return {
            "owner": owner,
            "repo": repo,
            "pr_number": pr_number,
            "events": all_events,
            "total": len(all_events),
            "error": error
        }

    def fetch_pr_detail(self, owner: str, repo: str, pr_number: int) -> Dict[str, Any]:
        """
        获取单个 PR 的详细信息
        包括：描述、标签、指派人、评审人、里程碑、合并状态、代码变更统计等
        :param owner: 仓库所有者
        :param repo: 仓库名称
        :param pr_number: PR 编号
        :return: PR 详细信息字典
        """
        logger.info(f"开始获取 {owner}/{repo} PR#{pr_number} 的详细信息")

        error = None
        pr_detail = {}

        try:
            token = self.token_pool.get_token()
            headers = {
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": "GitHub-PR-Fetcher"
            }

            if token:
                headers["Authorization"] = f"token {token}"

            # 获取 PR 详细信息
            url = f"{self.base_url}/repos/{owner}/{repo}/pulls/{pr_number}"
            response = self._make_request(url, headers, {}, 30)

            if response.status_code == 404:
                error = "PR不存在"
                logger.warning(f"{owner}/{repo} PR#{pr_number} 不存在")
            elif response.status_code != 200:
                error = f"API请求失败: {response.status_code}"
                logger.error(f"获取 {owner}/{repo} PR#{pr_number} 详细信息失败: {response.status_code}")
            else:
                pr = response.json()

                # 提取完整的 PR 信息
                pr_detail = {
                    "number": pr.get("number"),
                    "title": pr.get("title"),
                    "body": pr.get("body"),
                    "state": pr.get("state"),
                    "draft": pr.get("draft", False),
                    "locked": pr.get("locked", False),
                    "user": {
                        "login": pr.get("user", {}).get("login"),
                        "avatar_url": pr.get("user", {}).get("avatar_url"),
                        "type": pr.get("user", {}).get("type")
                    },
                    "labels": [
                        {"name": label.get("name"), "color": label.get("color")}
                        for label in pr.get("labels", [])
                    ],
                    "assignees": [
                        {"login": a.get("login"), "avatar_url": a.get("avatar_url")}
                        for a in pr.get("assignees", [])
                    ],
                    "requested_reviewers": [
                        {"login": r.get("login"), "avatar_url": r.get("avatar_url")}
                        for r in pr.get("requested_reviewers", [])
                    ],
                    "milestone": None,
                    "head": {
                        "ref": pr.get("head", {}).get("ref"),
                        "sha": pr.get("head", {}).get("sha"),
                        "label": pr.get("head", {}).get("label")
                    },
                    "base": {
                        "ref": pr.get("base", {}).get("ref"),
                        "sha": pr.get("base", {}).get("sha"),
                        "label": pr.get("base", {}).get("label")
                    },
                    "created_at": pr.get("created_at"),
                    "updated_at": pr.get("updated_at"),
                    "closed_at": pr.get("closed_at"),
                    "merged_at": pr.get("merged_at"),
                    "mergeable": pr.get("mergeable"),
                    "mergeable_state": pr.get("mergeable_state"),
                    "merged": pr.get("merged", False),
                    "merge_commit_sha": pr.get("merge_commit_sha"),
                    "commits": pr.get("commits"),
                    "additions": pr.get("additions"),
                    "deletions": pr.get("deletions"),
                    "changed_files": pr.get("changed_files"),
                    "comments": pr.get("comments"),
                    "review_comments": pr.get("review_comments"),
                    "url": pr.get("html_url"),
                    "api_url": pr.get("url")
                }

                # 处理里程碑
                if pr.get("milestone"):
                    milestone = pr["milestone"]
                    pr_detail["milestone"] = {
                        "number": milestone.get("number"),
                        "title": milestone.get("title"),
                        "state": milestone.get("state"),
                        "due_on": milestone.get("due_on")
                    }

                logger.info(f"获取 {owner}/{repo} PR#{pr_number} 详细信息完成")

        except Exception as e:
            error = str(e)
            logger.error(f"获取 {owner}/{repo} PR#{pr_number} 详细信息异常: {e}")

        return {
            "owner": owner,
            "repo": repo,
            "pr_number": pr_number,
            "detail": pr_detail,
            "error": error
        }

    def fetch_pr_detail_batch(self, owner: str, repo: str, pr_numbers: List[int]) -> Dict[str, Any]:
        """
        并发获取多个 PR 的详细信息
        :param owner: 仓库所有者
        :param repo: 仓库名称
        :param pr_numbers: PR 编号列表
        :return: 批量获取结果
        """
        logger.info(f"开始并发获取 {owner}/{repo} {len(pr_numbers)} 个PR的详细信息")

        results = []
        success_count = 0
        failed_count = 0

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(self.fetch_pr_detail, owner, repo, pr_num): pr_num
                for pr_num in pr_numbers
            }

            for future in as_completed(futures):
                pr_num = futures[future]
                try:
                    result = future.result()
                    results.append(result)

                    if result["error"] is None:
                        success_count += 1
                    else:
                        failed_count += 1

                except Exception as e:
                    failed_count += 1
                    results.append({
                        "owner": owner,
                        "repo": repo,
                        "pr_number": pr_num,
                        "detail": {},
                        "error": str(e)
                    })
                    logger.error(f"获取 {owner}/{repo} PR#{pr_num} 详细信息异常: {e}")

        logger.info(f"并发获取PR详细信息完成，成功: {success_count}, 失败: {failed_count}")

        return {
            "owner": owner,
            "repo": repo,
            "results": results,
            "total_prs": len(pr_numbers),
            "success_count": success_count,
            "failed_count": failed_count
        }

    def fetch_pr_reviews(self, owner: str, repo: str, pr_number: int) -> Dict[str, Any]:
        """
        获取指定 PR 的所有 Reviews
        :param owner: 仓库所有者
        :param repo: 仓库名称
        :param pr_number: PR 编号
        :return: Reviews 数据字典
        """
        logger.info(f"开始获取 {owner}/{repo} PR#{pr_number} 的 Reviews")

        all_reviews = []
        page = 1
        error = None

        try:
            while True:
                token = self.token_pool.get_token()
                headers = {
                    "Accept": "application/vnd.github.v3+json",
                    "User-Agent": "GitHub-PR-Fetcher"
                }

                if token:
                    headers["Authorization"] = f"token {token}"

                url = f"{self.base_url}/repos/{owner}/{repo}/pulls/{pr_number}/reviews"
                params = {
                    "per_page": self.per_page,
                    "page": page
                }

                response = self._make_request(url, headers, params, 30)

                if response.status_code == 404:
                    error = "PR不存在"
                    logger.warning(f"{owner}/{repo} PR#{pr_number} 不存在")
                    break

                if response.status_code != 200:
                    error = f"API请求失败: {response.status_code}"
                    logger.error(f"获取 {owner}/{repo} PR#{pr_number} Reviews 失败: {response.status_code}")
                    break

                reviews = response.json()

                if not reviews:
                    break

                for review in reviews:
                    user = review.get("user", {})
                    all_reviews.append({
                        "id": review.get("id"),
                        "review_id": review.get("id"),
                        "pr_number": pr_number,
                        "user": user.get("login", ""),
                        "user_id": user.get("id"),
                        "user_type": user.get("type", "User"),
                        "avatar_url": user.get("avatar_url"),
                        "state": review.get("state"),
                        "body": review.get("body"),
                        "submitted_at": review.get("submitted_at"),
                        "commit_id": review.get("commit_id"),
                        "author_association": review.get("author_association"),
                        "url": review.get("html_url"),
                    })

                page += 1
                time.sleep(self.request_delay)

            logger.info(f"获取 {owner}/{repo} PR#{pr_number} Reviews 完成，共 {len(all_reviews)} 条")

        except Exception as e:
            error = str(e)
            logger.error(f"获取 {owner}/{repo} PR#{pr_number} Reviews 异常: {e}")

        return {
            "owner": owner,
            "repo": repo,
            "pr_number": pr_number,
            "reviews": all_reviews,
            "total": len(all_reviews),
            "error": error
        }

    def fetch_all_pr_reviews(self, owner: str, repo: str, pr_numbers: List[int]) -> Dict[str, Any]:
        """
        并发获取多个 PR 的 Reviews
        :param owner: 仓库所有者
        :param repo: 仓库名称
        :param pr_numbers: PR 编号列表
        :return: 批量获取结果
        """
        logger.info(f"开始并发获取 {owner}/{repo} {len(pr_numbers)} 个 PR 的 Reviews")

        results = []
        success_count = 0
        failed_count = 0

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(self.fetch_pr_reviews, owner, repo, pr_num): pr_num
                for pr_num in pr_numbers
            }

            for future in as_completed(futures):
                pr_num = futures[future]
                try:
                    result = future.result()
                    results.append(result)
                    if result["error"] is None:
                        success_count += 1
                    else:
                        failed_count += 1
                except Exception as e:
                    failed_count += 1
                    results.append({
                        "owner": owner, "repo": repo, "pr_number": pr_num,
                        "reviews": [], "total": 0, "error": str(e)
                    })
                    logger.error(f"获取 {owner}/{repo} PR#{pr_num} Reviews 异常: {e}")

        logger.info(f"并发获取 Reviews 完成，成功: {success_count}, 失败: {failed_count}")

        return {
            "owner": owner,
            "repo": repo,
            "results": results,
            "total_prs": len(pr_numbers),
            "success_count": success_count,
            "failed_count": failed_count
        }

    def fetch_all_pr_details_batch(self, owner: str, repo: str, pr_numbers: List[int]) -> Dict[str, Any]:
        """
        并发获取多个PR的评论和时间线
        :param owner: 仓库所有者
        :param repo: 仓库名称
        :param pr_numbers: PR编号列表
        :return: 批量获取结果
        """
        logger.info(f"开始并发获取 {owner}/{repo} {len(pr_numbers)} 个PR的详细信息")

        results = []
        success_count = 0
        failed_count = 0

        def fetch_pr_details(pr_number: int) -> Dict[str, Any]:
            """获取单个PR的详细信息"""
            comments = self.fetch_pr_comments(owner, repo, pr_number)
            timeline = self.fetch_pr_timeline(owner, repo, pr_number)

            return {
                "pr_number": pr_number,
                "comments": comments,
                "timeline": timeline,
                "error": comments.get("error") or timeline.get("error")
            }

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(fetch_pr_details, pr_num): pr_num
                for pr_num in pr_numbers
            }

            for future in as_completed(futures):
                pr_num = futures[future]
                try:
                    result = future.result()
                    results.append(result)

                    if result["error"] is None:
                        success_count += 1
                    else:
                        failed_count += 1

                except Exception as e:
                    failed_count += 1
                    results.append({
                        "pr_number": pr_num,
                        "comments": None,
                        "timeline": None,
                        "error": str(e)
                    })
                    logger.error(f"获取 {owner}/{repo} PR#{pr_num} 详细信息异常: {e}")

        logger.info(f"并发获取完成，成功: {success_count}, 失败: {failed_count}")

        return {
            "owner": owner,
            "repo": repo,
            "results": results,
            "total_prs": len(pr_numbers),
            "success_count": success_count,
            "failed_count": failed_count
        }


# 全局任务进度管理器
task_progress_manager = TaskProgress()
