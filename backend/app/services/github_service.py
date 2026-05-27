"""
GitHub PR 服务模块（异步版本）
使用 httpx 替代 requests，asyncio.gather 替代 ThreadPoolExecutor
"""
import asyncio
import re
import time
from typing import Dict, Any, List, Optional
import logging
from functools import wraps

import httpx

logger = logging.getLogger(__name__)



class TokenPool:
    """Token 池管理类（异步安全）"""

    def __init__(self, tokens: List[str]):
        self.tokens = tokens if tokens else []
        self.current_index = 0
        self.lock = asyncio.Lock()
        # 速率限制追踪: token -> (remaining, reset_epoch)
        self._rate_limits: Dict[str, Tuple[int, float]] = {}
        logger.info(f"Token 池初始化完成，共 {len(self.tokens)} 个 Token")

    async def get_token(self) -> Optional[str]:
        if not self.tokens:
            return None
        async with self.lock:
            now = time.time()
            # 尝试找一个未限速的 token
            for _ in range(len(self.tokens)):
                token = self.tokens[self.current_index]
                self.current_index = (self.current_index + 1) % len(self.tokens)
                limit_info = self._rate_limits.get(token)
                if limit_info is None:
                    return token
                remaining, reset_epoch = limit_info
                if remaining > 0 or now >= reset_epoch:
                    # 配额有余或已过重置时间，清除限速标记
                    if now >= reset_epoch:
                        self._rate_limits.pop(token, None)
                    return token
            # 所有 token 都限速了，找最早重置的等待
            earliest_reset = min((info[1] for info in self._rate_limits.values()), default=now)
            wait = max(0, earliest_reset - now) + 1
            logger.warning(f"所有 Token 已限速，等待 {wait:.0f} 秒")
            return None

    def update_rate_limit(self, token: str, remaining: int, reset_epoch: float):
        """更新 token 的速率限制状态"""
        if remaining <= 0:
            self._rate_limits[token] = (remaining, reset_epoch)
            logger.warning(f"Token 限速: remaining={remaining}, reset in {reset_epoch - time.time():.0f}s")
        elif token in self._rate_limits:
            del self._rate_limits[token]

    async def add_token(self, token: str):
        async with self.lock:
            if token not in self.tokens:
                self.tokens.append(token)
                logger.info(f"Token 已添加，当前共 {len(self.tokens)} 个 Token")

    def remove_token(self, token: str):
        if token in self.tokens:
            self.tokens.remove(token)
            logger.info(f"Token 已移除，当前共 {len(self.tokens)} 个 Token")

    def get_stats(self) -> Dict[str, Any]:
        now = time.time()
        rate_limits = []
        for i, token in enumerate(self.tokens):
            masked = token[:4] + '*' * (len(token) - 8) + token[-4:] if len(token) > 8 else '****'
            info = self._rate_limits.get(token)
            if info:
                remaining, reset_epoch = info
                rate_limits.append({
                    "index": i,
                    "token_masked": masked,
                    "remaining": remaining,
                    "reset_at": reset_epoch,
                    "reset_in_seconds": max(0, reset_epoch - now),
                    "limited": remaining <= 0 and now < reset_epoch,
                })
            else:
                rate_limits.append({
                    "index": i,
                    "token_masked": masked,
                    "remaining": None,
                    "reset_at": None,
                    "reset_in_seconds": None,
                    "limited": False,
                })
        return {
            "total_tokens": len(self.tokens),
            "current_index": self.current_index,
            "rate_limits": rate_limits,
        }


class TaskProgress:
    """任务进度管理类（异步安全）"""

    def __init__(self):
        self.tasks: Dict[str, Dict[str, Any]] = {}
        self.lock = asyncio.Lock()
        logger.info("任务进度管理器初始化完成")

    async def create_task(self, task_id: str, total: int = 100) -> Dict[str, Any]:
        task = {
            "task_id": task_id, "status": "pending", "progress": 0.0,
            "total": total, "current": 0, "message": "任务已创建",
            "created_at": time.time(), "updated_at": time.time()
        }
        async with self.lock:
            self.tasks[task_id] = task
        logger.info(f"任务已创建: {task_id}")
        return task

    async def update_task(self, task_id: str, current: int, message: str = "") -> Optional[Dict[str, Any]]:
        async with self.lock:
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

    async def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        async with self.lock:
            return self.tasks.get(task_id)

    async def get_all_tasks(self) -> List[Dict[str, Any]]:
        async with self.lock:
            return list(self.tasks.values())

    async def delete_task(self, task_id: str) -> bool:
        async with self.lock:
            if task_id in self.tasks:
                del self.tasks[task_id]
                logger.info(f"任务已删除: {task_id}")
                return True
            return False


class GitHubPRService:
    """GitHub PR 服务类（异步版本）"""

    def __init__(self, token_pool: TokenPool, api_settings: Dict[str, Any]):
        self.token_pool = token_pool
        self.api_settings = api_settings
        self.base_url = api_settings.get("base_url", "https://api.github.com")
        self.per_page = api_settings.get("per_page", 100)
        self.state = api_settings.get("state", "all")
        self.request_delay = api_settings.get("request_delay", 0.5)
        self.max_workers = api_settings.get("max_workers", 3)
        self.max_retries = 3
        self.retry_delay = 5
        # 异步 HTTP 客户端（跟随服务生命周期，在 main.py lifespan 中关闭）
        self._client: Optional[httpx.AsyncClient] = None
        logger.info(f"GitHub PR 服务初始化完成，Base URL: {self.base_url}")

        self.known_bot_patterns = [
            "github-actions[bot]", "dependabot[bot]", "renovate[bot]",
            "greenkeeper[bot]", "pre-commit-ci[bot]", "codecov-io[bot]",
            "coveralls[bot]", "snyk-bot", "jenkins-bot", "circleci",
            "travis-ci", "azure-pipelines[bot]", "appveyor-ci",
            "cla-assistant[bot]", "stale[bot]", "mergify[bot]",
            "netlify[bot]", "now-integration[bot]", "vercel[bot]",
            "imgbot[bot]", "allcontributors[bot]", "semantic-release-bot",
            "lgtm-com[bot]", "deepscan-io[bot]", "codacy-badger[bot]",
            "sonarcloud[bot]", "scala-steward[bot]", "nucleusbot", "taichi-bot",
        ]
        self.bot_regex_patterns = [
            r".*\[bot\]$", r".*-bot$", r".*_bot$", r"^bot-.*",
            r".*-ci$", r".*-automation$", r".*pipeline.*",
        ]
        self._compiled_bot_regex = [re.compile(p, re.IGNORECASE) for p in self.bot_regex_patterns]

    def _get_client(self) -> httpx.AsyncClient:
        """获取或创建异步 HTTP 客户端"""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    async def close(self):
        """关闭 HTTP 客户端"""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    def _is_bot_user(self, username: str, user_type: str) -> bool:
        if not username:
            return False
        if user_type == "Bot" or user_type == "Organization":
            return True
        if username.lower() in [bot.lower() for bot in self.known_bot_patterns]:
            return True
        for compiled in self._compiled_bot_regex:
            if compiled.match(username):
                return True
        return False

    async def _make_request(self, url: str, headers: Dict[str, str],
                            params: Dict[str, Any], timeout: int = 30) -> httpx.Response:
        """发起异步 HTTP 请求（带重试 + 速率限制感知）"""
        client = self._get_client()
        last_exception = None
        for attempt in range(self.max_retries):
            try:
                response = await client.get(url, headers=headers, params=params, timeout=timeout)

                # 解析速率限制响应头
                remaining = response.headers.get("X-RateLimit-Remaining")
                reset_epoch = response.headers.get("X-RateLimit-Reset")
                token = headers.get("Authorization", "").replace("token ", "")
                if remaining is not None and reset_epoch is not None:
                    try:
                        self.token_pool.update_rate_limit(token, int(remaining), float(reset_epoch))
                    except (ValueError, TypeError):
                        pass

                # 处理 403 速率限制耗尽
                if response.status_code == 403 and remaining is not None and int(remaining) == 0:
                    reset_at = float(reset_epoch) if reset_epoch else time.time() + 60
                    wait = max(1, reset_at - time.time()) + 1
                    logger.warning(f"GitHub API 速率限制耗尽，等待 {wait:.0f} 秒后重试 (attempt {attempt + 1})")
                    await asyncio.sleep(wait)
                    continue

                return response
            except (httpx.RequestError, httpx.HTTPStatusError) as e:
                last_exception = e
                if attempt < self.max_retries - 1:
                    # 指数退避
                    delay = self.retry_delay * (2 ** attempt)
                    logger.warning(f"请求失败 (尝试 {attempt + 1}/{self.max_retries}): {e}, {delay}秒后重试...")
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"请求失败，已达到最大重试次数 {self.max_retries}: {e}")
        raise last_exception

    async def _get_headers(self) -> Dict[str, str]:
        """构建请求头（含 Token）"""
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "GitHub-PR-Fetcher"
        }
        token = await self.token_pool.get_token()
        if token:
            headers["Authorization"] = f"token {token}"
        return headers

    async def fetch_prs_for_project(self, owner: str, repo: str, max_count: int = 0, start_page: int = 1) -> Dict[str, Any]:
        """获取指定项目的 PR 数据"""
        log_msg = f"开始获取 {owner}/{repo} 的 PR 数据"
        if start_page > 1:
            log_msg += f" (从第 {start_page} 页开始)"
        if max_count > 0:
            log_msg += f" (最多 {max_count} 个)"
        logger.info(log_msg)

        all_prs = []
        page = start_page
        error = None

        try:
            while True:
                headers = await self._get_headers()
                url = f"{self.base_url}/repos/{owner}/{repo}/pulls"
                params = {"state": self.state, "per_page": self.per_page, "page": page}

                response = await self._make_request(url, headers, params, 30)

                if response.status_code == 404:
                    error = "仓库不存在"
                    break
                if response.status_code != 200:
                    error = f"API 请求失败: {response.status_code}"
                    break

                prs = response.json()
                if not prs:
                    break

                for pr in prs:
                    all_prs.append({
                        "number": pr.get("number"), "title": pr.get("title"),
                        "user": pr.get("user", {}).get("login"), "state": pr.get("state"),
                        "created_at": pr.get("created_at"), "updated_at": pr.get("updated_at"),
                        "url": pr.get("html_url")
                    })

                if max_count > 0 and len(all_prs) >= max_count:
                    all_prs = all_prs[:max_count]
                    break

                page += 1
                await asyncio.sleep(self.request_delay)

            logger.info(f"获取 {owner}/{repo} 完成，共 {len(all_prs)} 个 PR")
        except Exception as e:
            error = str(e)
            logger.error(f"获取 {owner}/{repo} PR 数据异常: {e}")

        return {"owner": owner, "repo": repo, "prs": all_prs, "total": len(all_prs), "error": error}

    async def fetch_prs_batch(self, projects: List[Dict[str, str]]) -> Dict[str, Any]:
        """异步并发获取多个项目的 PR 数据"""
        logger.info(f"开始批量获取 {len(projects)} 个项目的 PR 数据")

        semaphore = asyncio.Semaphore(self.max_workers)

        async def _fetch_with_semaphore(project):
            async with semaphore:
                return await self.fetch_prs_for_project(project["owner"], project["repo"])

        results = await asyncio.gather(*[_fetch_with_semaphore(p) for p in projects], return_exceptions=True)

        success_count = 0
        failed_count = 0
        total_prs = 0
        final_results = []

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                failed_count += 1
                final_results.append({"owner": projects[i]["owner"], "repo": projects[i]["repo"],
                                      "prs": [], "total": 0, "error": str(result)})
            else:
                final_results.append(result)
                if result["error"] is None:
                    success_count += 1
                    total_prs += result["total"]
                else:
                    failed_count += 1

        logger.info(f"批量获取完成，成功: {success_count}, 失败: {failed_count}, 总 PR: {total_prs}")
        return {
            "results": final_results, "total_projects": len(projects),
            "success_projects": success_count, "failed_projects": failed_count, "total_prs": total_prs
        }

    async def fetch_pr_comments(self, owner: str, repo: str, pr_number: int) -> Dict[str, Any]:
        """获取指定 PR 的所有评论"""
        logger.info(f"开始获取 {owner}/{repo} PR#{pr_number} 的评论")
        all_comments = []
        page = 1
        error = None

        try:
            while True:
                headers = await self._get_headers()
                url = f"{self.base_url}/repos/{owner}/{repo}/issues/{pr_number}/comments"
                params = {"per_page": self.per_page, "page": page}

                response = await self._make_request(url, headers, params, 30)
                if response.status_code == 404:
                    error = "PR不存在"
                    break
                if response.status_code != 200:
                    error = f"API请求失败: {response.status_code}"
                    break

                comments = response.json()
                if not comments:
                    break

                for comment in comments:
                    user = comment.get("user", {})
                    user_login = user.get("login", "")
                    user_type = user.get("type", "User")
                    is_bot = self._is_bot_user(user_login, user_type)
                    all_comments.append({
                        "id": comment.get("id"), "user": user_login,
                        "user_id": user.get("id"), "user_type": user_type,
                        "avatar_url": user.get("avatar_url"), "is_bot": is_bot,
                        "author_association": comment.get("author_association"),
                        "body": comment.get("body"), "created_at": comment.get("created_at"),
                        "updated_at": comment.get("updated_at"), "url": comment.get("html_url"),
                        "reactions": comment.get("reactions", {}).get("total_count", 0) if comment.get("reactions") else 0
                    })

                page += 1
                await asyncio.sleep(self.request_delay)

            logger.info(f"获取 {owner}/{repo} PR#{pr_number} 评论完成，共 {len(all_comments)} 条")
        except Exception as e:
            error = str(e)
            logger.error(f"获取 {owner}/{repo} PR#{pr_number} 评论异常: {e}")

        return {"owner": owner, "repo": repo, "pr_number": pr_number,
                "comments": all_comments, "total": len(all_comments), "error": error}

    async def fetch_pr_timeline(self, owner: str, repo: str, pr_number: int) -> Dict[str, Any]:
        """获取指定 PR 的时间线事件"""
        logger.info(f"开始获取 {owner}/{repo} PR#{pr_number} 的时间线")
        all_events = []
        page = 1
        error = None

        try:
            while True:
                headers = await self._get_headers()
                url = f"{self.base_url}/repos/{owner}/{repo}/issues/{pr_number}/timeline"
                params = {"per_page": self.per_page, "page": page}

                response = await self._make_request(url, headers, params, 30)
                if response.status_code == 404:
                    error = "PR不存在"
                    break
                if response.status_code != 200:
                    error = f"API请求失败: {response.status_code}"
                    break

                events = response.json()
                if not events:
                    break

                for event in events:
                    all_events.append({
                        "id": event.get("id"), "event": event.get("event"),
                        "actor": event.get("actor", {}).get("login") if event.get("actor") else None,
                        "created_at": event.get("created_at"), "url": event.get("url")
                    })

                page += 1
                await asyncio.sleep(self.request_delay)

            logger.info(f"获取 {owner}/{repo} PR#{pr_number} 时间线完成，共 {len(all_events)} 个事件")
        except Exception as e:
            error = str(e)
            logger.error(f"获取 {owner}/{repo} PR#{pr_number} 时间线异常: {e}")

        return {"owner": owner, "repo": repo, "pr_number": pr_number,
                "events": all_events, "total": len(all_events), "error": error}

    async def fetch_pr_detail(self, owner: str, repo: str, pr_number: int) -> Dict[str, Any]:
        """获取单个 PR 的详细信息"""
        logger.info(f"开始获取 {owner}/{repo} PR#{pr_number} 的详细信息")
        error = None
        pr_detail = {}

        try:
            headers = await self._get_headers()
            url = f"{self.base_url}/repos/{owner}/{repo}/pulls/{pr_number}"
            response = await self._make_request(url, headers, {}, 30)

            if response.status_code == 404:
                error = "PR不存在"
            elif response.status_code != 200:
                error = f"API请求失败: {response.status_code}"
            else:
                pr = response.json()
                pr_detail = {
                    "number": pr.get("number"), "title": pr.get("title"), "body": pr.get("body"),
                    "state": pr.get("state"), "draft": pr.get("draft", False),
                    "locked": pr.get("locked", False),
                    "user": {"login": pr.get("user", {}).get("login"),
                             "avatar_url": pr.get("user", {}).get("avatar_url"),
                             "type": pr.get("user", {}).get("type")},
                    "labels": [{"name": label.get("name"), "color": label.get("color")}
                               for label in pr.get("labels", [])],
                    "assignees": [{"login": a.get("login"), "avatar_url": a.get("avatar_url")}
                                  for a in pr.get("assignees", [])],
                    "requested_reviewers": [{"login": r.get("login"), "avatar_url": r.get("avatar_url")}
                                            for r in pr.get("requested_reviewers", [])],
                    "milestone": None,
                    "head": {"ref": pr.get("head", {}).get("ref"), "sha": pr.get("head", {}).get("sha"),
                             "label": pr.get("head", {}).get("label")},
                    "base": {"ref": pr.get("base", {}).get("ref"), "sha": pr.get("base", {}).get("sha"),
                             "label": pr.get("base", {}).get("label")},
                    "created_at": pr.get("created_at"), "updated_at": pr.get("updated_at"),
                    "closed_at": pr.get("closed_at"), "merged_at": pr.get("merged_at"),
                    "mergeable": pr.get("mergeable"), "mergeable_state": pr.get("mergeable_state"),
                    "merged": pr.get("merged", False), "merge_commit_sha": pr.get("merge_commit_sha"),
                    "commits": pr.get("commits"), "additions": pr.get("additions"),
                    "deletions": pr.get("deletions"), "changed_files": pr.get("changed_files"),
                    "comments": pr.get("comments"), "review_comments": pr.get("review_comments"),
                    "url": pr.get("html_url"), "api_url": pr.get("url")
                }
                if pr.get("milestone"):
                    milestone = pr["milestone"]
                    pr_detail["milestone"] = {
                        "number": milestone.get("number"), "title": milestone.get("title"),
                        "state": milestone.get("state"), "due_on": milestone.get("due_on")
                    }
                logger.info(f"获取 {owner}/{repo} PR#{pr_number} 详细信息完成")
        except Exception as e:
            error = str(e)
            logger.error(f"获取 {owner}/{repo} PR#{pr_number} 详细信息异常: {e}")

        return {"owner": owner, "repo": repo, "pr_number": pr_number,
                "detail": pr_detail, "error": error}

    async def fetch_pr_detail_batch(self, owner: str, repo: str, pr_numbers: List[int]) -> Dict[str, Any]:
        """异步并发获取多个 PR 的详细信息"""
        logger.info(f"开始并发获取 {owner}/{repo} {len(pr_numbers)} 个PR的详细信息")
        semaphore = asyncio.Semaphore(self.max_workers)

        async def _fetch(pr_num):
            async with semaphore:
                return await self.fetch_pr_detail(owner, repo, pr_num)

        results = await asyncio.gather(*[_fetch(n) for n in pr_numbers], return_exceptions=True)
        success_count = sum(1 for r in results if not isinstance(r, Exception) and r["error"] is None)
        failed_count = len(results) - success_count
        final_results = []
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                final_results.append({"owner": owner, "repo": repo, "pr_number": pr_numbers[i],
                                      "detail": {}, "error": str(r)})
            else:
                final_results.append(r)

        return {"owner": owner, "repo": repo, "results": final_results,
                "total_prs": len(pr_numbers), "success_count": success_count, "failed_count": failed_count}

    async def fetch_pr_reviews(self, owner: str, repo: str, pr_number: int) -> Dict[str, Any]:
        """获取指定 PR 的所有 Reviews"""
        logger.info(f"开始获取 {owner}/{repo} PR#{pr_number} 的 Reviews")
        all_reviews = []
        page = 1
        error = None

        try:
            while True:
                headers = await self._get_headers()
                url = f"{self.base_url}/repos/{owner}/{repo}/pulls/{pr_number}/reviews"
                params = {"per_page": self.per_page, "page": page}

                response = await self._make_request(url, headers, params, 30)
                if response.status_code == 404:
                    error = "PR不存在"
                    break
                if response.status_code != 200:
                    error = f"API请求失败: {response.status_code}"
                    break

                reviews = response.json()
                if not reviews:
                    break

                for review in reviews:
                    user = review.get("user", {})
                    all_reviews.append({
                        "id": review.get("id"), "review_id": review.get("id"),
                        "pr_number": pr_number, "user": user.get("login", ""),
                        "user_id": user.get("id"), "user_type": user.get("type", "User"),
                        "avatar_url": user.get("avatar_url"), "state": review.get("state"),
                        "body": review.get("body"), "submitted_at": review.get("submitted_at"),
                        "commit_id": review.get("commit_id"),
                        "author_association": review.get("author_association"),
                        "url": review.get("html_url"),
                    })

                page += 1
                await asyncio.sleep(self.request_delay)

            logger.info(f"获取 {owner}/{repo} PR#{pr_number} Reviews 完成，共 {len(all_reviews)} 条")
        except Exception as e:
            error = str(e)
            logger.error(f"获取 {owner}/{repo} PR#{pr_number} Reviews 异常: {e}")

        return {"owner": owner, "repo": repo, "pr_number": pr_number,
                "reviews": all_reviews, "total": len(all_reviews), "error": error}

    async def fetch_all_pr_reviews(self, owner: str, repo: str, pr_numbers: List[int]) -> Dict[str, Any]:
        """异步并发获取多个 PR 的 Reviews"""
        logger.info(f"开始并发获取 {owner}/{repo} {len(pr_numbers)} 个 PR 的 Reviews")
        semaphore = asyncio.Semaphore(self.max_workers)

        async def _fetch(pr_num):
            async with semaphore:
                return await self.fetch_pr_reviews(owner, repo, pr_num)

        results = await asyncio.gather(*[_fetch(n) for n in pr_numbers], return_exceptions=True)
        success_count = sum(1 for r in results if not isinstance(r, Exception) and r["error"] is None)
        failed_count = len(results) - success_count
        final_results = []
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                final_results.append({"owner": owner, "repo": repo, "pr_number": pr_numbers[i],
                                      "reviews": [], "total": 0, "error": str(r)})
            else:
                final_results.append(r)

        return {"owner": owner, "repo": repo, "results": final_results,
                "total_prs": len(pr_numbers), "success_count": success_count, "failed_count": failed_count}

    async def fetch_pr_commits(self, owner: str, repo: str, pr_number: int) -> Dict[str, Any]:
        """获取指定 PR 的 Commits"""
        logger.info(f"开始获取 {owner}/{repo} PR#{pr_number} 的 Commits")
        all_commits = []
        page = 1
        error = None

        try:
            while True:
                headers = await self._get_headers()
                url = f"{self.base_url}/repos/{owner}/{repo}/pulls/{pr_number}/commits"
                params = {"per_page": self.per_page, "page": page}

                response = await self._make_request(url, headers, params, 30)
                if response.status_code == 404:
                    error = "PR不存在"
                    break
                if response.status_code != 200:
                    error = f"API请求失败: {response.status_code}"
                    break

                commits = response.json()
                if not commits:
                    break

                for commit in commits:
                    commit_data = commit.get("commit", {})
                    author = commit_data.get("author", {})
                    committer = commit_data.get("committer", {})
                    all_commits.append({
                        "sha": commit.get("sha", ""), "message": commit_data.get("message", ""),
                        "author_name": author.get("name", ""), "author_email": author.get("email", ""),
                        "author_date": author.get("date", ""), "committer_name": committer.get("name", ""),
                        "committer_date": committer.get("date", ""), "url": commit.get("html_url", ""),
                        "verified": commit_data.get("verification", {}).get("verified", False),
                        "additions": commit.get("stats", {}).get("additions", 0),
                        "deletions": commit.get("stats", {}).get("deletions", 0),
                        "total_changes": commit.get("stats", {}).get("total", 0),
                        "files_changed": len(commit.get("files", [])),
                    })

                page += 1
                await asyncio.sleep(self.request_delay)

            logger.info(f"获取 {owner}/{repo} PR#{pr_number} Commits 完成，共 {len(all_commits)} 条")
        except Exception as e:
            error = str(e)
            logger.error(f"获取 {owner}/{repo} PR#{pr_number} Commits 异常: {e}")

        return {"owner": owner, "repo": repo, "pr_number": pr_number,
                "commits": all_commits, "total": len(all_commits), "error": error}

    async def fetch_all_pr_commits(self, owner: str, repo: str, pr_numbers: List[int]) -> Dict[str, Any]:
        """异步并发获取多个 PR 的 Commits"""
        logger.info(f"开始并发获取 {owner}/{repo} {len(pr_numbers)} 个 PR 的 Commits")
        semaphore = asyncio.Semaphore(self.max_workers)

        async def _fetch(pr_num):
            async with semaphore:
                return await self.fetch_pr_commits(owner, repo, pr_num)

        results = await asyncio.gather(*[_fetch(n) for n in pr_numbers], return_exceptions=True)
        success_count = sum(1 for r in results if not isinstance(r, Exception) and r["error"] is None)
        failed_count = len(results) - success_count
        final_results = []
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                final_results.append({"owner": owner, "repo": repo, "pr_number": pr_numbers[i],
                                      "commits": [], "total": 0, "error": str(r)})
            else:
                final_results.append(r)

        return {"owner": owner, "repo": repo, "results": final_results,
                "total_prs": len(pr_numbers), "success_count": success_count, "failed_count": failed_count}

    async def fetch_all_pr_details_batch(self, owner: str, repo: str, pr_numbers: List[int]) -> Dict[str, Any]:
        """异步并发获取多个PR的评论和时间线"""
        logger.info(f"开始并发获取 {owner}/{repo} {len(pr_numbers)} 个PR的详细信息")
        semaphore = asyncio.Semaphore(self.max_workers)

        async def _fetch_pr_details(pr_number: int) -> Dict[str, Any]:
            async with semaphore:
                comments, timeline = await asyncio.gather(
                    self.fetch_pr_comments(owner, repo, pr_number),
                    self.fetch_pr_timeline(owner, repo, pr_number),
                )
                return {
                    "pr_number": pr_number, "comments": comments, "timeline": timeline,
                    "error": comments.get("error") or timeline.get("error")
                }

        results = await asyncio.gather(*[_fetch_pr_details(n) for n in pr_numbers], return_exceptions=True)
        success_count = sum(1 for r in results if not isinstance(r, Exception) and r["error"] is None)
        failed_count = len(results) - success_count
        final_results = []
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                final_results.append({"pr_number": pr_numbers[i], "comments": None,
                                      "timeline": None, "error": str(r)})
            else:
                final_results.append(r)

        return {"owner": owner, "repo": repo, "results": final_results,
                "total_prs": len(pr_numbers), "success_count": success_count, "failed_count": failed_count}

    async def fetch_user_profile(self, username: str) -> Dict[str, Any]:
        """获取 GitHub 用户 Profile"""
        try:
            headers = await self._get_headers()
            url = f"{self.base_url}/users/{username}"
            response = await self._make_request(url, headers, {}, 30)
            if response.status_code != 200:
                return {"username": username, "error": f"API 请求失败: {response.status_code}"}
            data = response.json()
            return {
                "login": data.get("login"),
                "id": data.get("id"),
                "avatar_url": data.get("avatar_url"),
                "html_url": data.get("html_url"),
                "type": data.get("type"),
                "name": data.get("name"),
                "company": data.get("company"),
                "blog": data.get("blog"),
                "location": data.get("location"),
                "email": data.get("email"),
                "bio": data.get("bio"),
                "public_repos": data.get("public_repos"),
                "followers": data.get("followers"),
                "following": data.get("following"),
                "created_at": data.get("created_at"),
                "error": None,
            }
        except Exception as e:
            return {"username": username, "error": str(e)}

    async def fetch_user_profiles_batch(self, usernames: List[str]) -> Dict[str, Any]:
        """批量获取 GitHub 用户 Profile"""
        semaphore = asyncio.Semaphore(self.max_workers)

        async def _fetch(username):
            async with semaphore:
                result = await self.fetch_user_profile(username)
                await asyncio.sleep(self.request_delay)
                return result

        results = await asyncio.gather(*[_fetch(u) for u in usernames], return_exceptions=True)
        success, failed = [], []
        for r in results:
            if isinstance(r, Exception):
                failed.append({"error": str(r)})
            elif r.get("error"):
                failed.append(r)
            else:
                success.append(r)
        return {"profiles": success, "failed": failed, "total": len(usernames), "success_count": len(success), "failed_count": len(failed)}

    async def fetch_user_contributed_repos(self, username: str, max_pages: int = 5) -> Dict[str, Any]:
        """获取用户参与过的项目（通过 Events API）"""
        repo_map = {}
        page = 1
        error = None

        try:
            while page <= max_pages:
                headers = await self._get_headers()
                url = f"{self.base_url}/users/{username}/events"
                params = {"per_page": 100, "page": page}
                response = await self._make_request(url, headers, params, 30)
                if response.status_code != 200:
                    error = f"API 请求失败: {response.status_code}"
                    break
                events = response.json()
                if not events:
                    break
                for event in events:
                    repo_name = event.get("repo", {}).get("name")
                    event_type = event.get("type", "")
                    if not repo_name:
                        continue
                    if repo_name not in repo_map:
                        repo_map[repo_name] = {"repo": repo_name, "events": {}}
                    if event_type not in repo_map[repo_name]["events"]:
                        repo_map[repo_name]["events"][event_type] = 0
                    repo_map[repo_name]["events"][event_type] += 1
                page += 1
                await asyncio.sleep(self.request_delay)

            repos = []
            for name, info in repo_map.items():
                total = sum(info["events"].values())
                repos.append({
                    "repo": name,
                    "total_events": total,
                    "event_types": info["events"],
                })
            repos.sort(key=lambda x: x["total_events"], reverse=True)
            logger.info(f"获取用户 {username} 参与项目完成，共 {len(repos)} 个项目")
        except Exception as e:
            error = str(e)
            logger.error(f"获取用户参与项目异常: {e}")

        return {"username": username, "repos": repos, "total": len(repos), "error": error}

    async def fetch_issues(self, owner: str, repo: str, max_count: int = 0, start_page: int = 1, state: str = "all") -> Dict[str, Any]:
        """获取指定项目的 Issues 数据（不含 PR）"""
        log_msg = f"开始获取 {owner}/{repo} 的 Issues 数据"
        if start_page > 1:
            log_msg += f" (从第 {start_page} 页开始)"
        if max_count > 0:
            log_msg += f" (最多 {max_count} 个)"
        logger.info(log_msg)

        all_items = []
        page = start_page
        error = None

        try:
            while True:
                headers = await self._get_headers()
                url = f"{self.base_url}/repos/{owner}/{repo}/issues"
                params = {"state": state, "per_page": self.per_page, "page": page}

                response = await self._make_request(url, headers, params, 30)

                if response.status_code == 404:
                    error = "仓库不存在"
                    break
                if response.status_code != 200:
                    error = f"API 请求失败: {response.status_code}"
                    break

                issues = response.json()
                if not issues:
                    break

                for issue in issues:
                    if "pull_request" in issue:
                        continue
                    labels = [l.get("name") for l in (issue.get("labels") or [])]
                    assignees = [a.get("login") for a in (issue.get("assignees") or [])]
                    all_items.append({
                        "number": issue.get("number"),
                        "title": issue.get("title"),
                        "user": (issue.get("user") or {}).get("login"),
                        "state": issue.get("state"),
                        "labels": labels,
                        "assignees": assignees,
                        "comments_count": issue.get("comments", 0),
                        "created_at": issue.get("created_at"),
                        "updated_at": issue.get("updated_at"),
                        "closed_at": issue.get("closed_at"),
                        "url": issue.get("html_url"),
                        "body": (issue.get("body") or "")[:500],
                    })

                if max_count > 0 and len(all_items) >= max_count:
                    all_items = all_items[:max_count]
                    break

                page += 1
                await asyncio.sleep(self.request_delay)

            logger.info(f"获取 {owner}/{repo} Issues 完成，共 {len(all_items)} 个")
        except Exception as e:
            error = str(e)
            logger.error(f"获取 {owner}/{repo} Issues 数据异常: {e}")

        return {"owner": owner, "repo": repo, "issues": all_items, "total": len(all_items), "error": error}

    async def fetch_issue_timeline(self, owner: str, repo: str, issue_number: int) -> Dict[str, Any]:
        """获取单个 Issue/PR 的 Timeline（PR 通过 Issues API 访问）"""
        all_events = []
        page = 1
        error = None
        is_pr = False

        try:
            # 先判断是 PR 还是 Issue
            check_headers = await self._get_headers()
            check_url = f"{self.base_url}/repos/{owner}/{repo}/issues/{issue_number}"
            check_resp = await self._make_request(check_url, check_headers, {}, 10)
            if check_resp.status_code == 200:
                is_pr = "pull_request" in check_resp.json()
            elif check_resp.status_code == 404:
                # 试试 PR API
                pr_url = f"{self.base_url}/repos/{owner}/{repo}/pulls/{issue_number}"
                pr_resp = await self._make_request(pr_url, check_headers, {}, 10)
                is_pr = pr_resp.status_code == 200
            while True:
                headers = await self._get_headers()
                headers["Accept"] = "application/vnd.github.mockingbird-preview+json"
                url = f"{self.base_url}/repos/{owner}/{repo}/issues/{issue_number}/timeline"
                params = {"per_page": 100, "page": page}

                response = await self._make_request(url, headers, params, 30)

                if response.status_code == 404:
                    error = "Issue/PR 不存在"
                    break
                if response.status_code != 200:
                    error = f"API 请求失败: {response.status_code}"
                    break

                events = response.json()
                if not events:
                    break

                for event in events:
                    actor = event.get("actor") or event.get("user") or {}
                    label = event.get("label") or {}
                    assignee = event.get("assignee") or {}
                    milestone = event.get("milestone") or {}
                    source = event.get("source") or {}
                    source_issue = source.get("issue") or {}
                    reactions = event.get("reactions") or {}
                    all_events.append({
                        "event_id": event.get("id"),
                        "event_type": event.get("event"),
                        "actor": actor.get("login"),
                        "actor_id": actor.get("id"),
                        "actor_type": actor.get("type"),
                        "commit_id": event.get("commit_id"),
                        "commit_url": event.get("commit_url"),
                        "label": label.get("name"),
                        "label_color": label.get("color"),
                        "assignee": assignee.get("login"),
                        "milestone": milestone.get("title"),
                        "body": (event.get("body") or "")[:500],
                        "url": event.get("html_url") or event.get("url"),
                        "state": event.get("state"),
                        "author_association": event.get("author_association"),
                        "reactions_total": reactions.get("total_count", 0),
                        "source_type": source.get("type"),
                        "source_issue_url": source_issue.get("html_url"),
                        "created_at": event.get("created_at"),
                    })

                if len(events) < 100:
                    break
                page += 1
                await asyncio.sleep(self.request_delay)

            logger.info(f"获取 {owner}/{repo} Issue#{issue_number} Timeline 完成，共 {len(all_events)} 个事件")
        except Exception as e:
            error = str(e)
            logger.error(f"获取 Issue Timeline 异常: {e}")

        return {"owner": owner, "repo": repo, "issue_number": issue_number, "is_pr": is_pr, "events": all_events, "total": len(all_events), "error": error}

    async def fetch_issue_timelines_batch(self, owner: str, repo: str, issue_numbers: List[int]) -> Dict[str, Any]:
        """批量获取多个 Issue/PR 的 Timeline"""
        semaphore = asyncio.Semaphore(self.max_workers)
        results, success_count, failed_count = [], 0, 0

        async def _fetch(number):
            async with semaphore:
                result = await self.fetch_issue_timeline(owner, repo, number)
                await asyncio.sleep(self.request_delay)
                return result

        task_results = await asyncio.gather(*[_fetch(n) for n in issue_numbers], return_exceptions=True)

        for number, result in zip(issue_numbers, task_results):
            if isinstance(result, Exception):
                failed_count += 1
            else:
                results.append(result)
                if result.get("error") is None:
                    success_count += 1
                else:
                    failed_count += 1

        return {"owner": owner, "repo": repo, "results": results, "total": len(issue_numbers), "success_count": success_count, "failed_count": failed_count}


    def _parse_last_page(self, link_header: str) -> int:
        if not link_header:
            return 0
        import re
        match = re.search(r'<[^>]*[?&]page=(\d+)>;\s*rel="last"', link_header)
        return int(match.group(1)) if match else 0

    async def get_repo_stats(self, owner: str, repo: str) -> Dict[str, Any]:
        """获取仓库在 GitHub 上的各类数据总数（PR/Issues/评论等）"""
        import re
        headers = await self._get_headers()
        client = self._get_client()
        result = {"owner": owner, "repo": repo}

        try:
            repo_resp = await self._make_request(
                f"{self.base_url}/repos/{owner}/{repo}", headers, {})
            if repo_resp.status_code != 200:
                return {**result, "error": f"获取仓库信息失败: {repo_resp.status_code}"}
            repo_data = repo_resp.json()
            result["stargazers_count"] = repo_data.get("stargazers_count", 0)
            result["forks_count"] = repo_data.get("forks_count", 0)
            result["open_issues_count"] = repo_data.get("open_issues_count", 0)
        except Exception as e:
            return {**result, "error": f"获取仓库信息异常: {e}"}

        async def _get_total(endpoint, params=None):
            try:
                p = {"state": "all", "per_page": 1, "page": 1}
                if params:
                    p.update(params)
                resp = await client.get(
                    f"{self.base_url}/repos/{owner}/{repo}/{endpoint}",
                    headers=headers, params=p, timeout=15)
                if resp.status_code != 200:
                    return None
                data = resp.json()
                if not isinstance(data, list):
                    return None
                total = self._parse_last_page(resp.headers.get("link", ""))
                return total if total > 0 else len(data)
            except Exception:
                return None

        async def _get_total_via_search(query):
            try:
                resp = await client.get(
                    f"{self.base_url}/search/issues",
                    headers=headers,
                    params={"q": query, "per_page": 1},
                    timeout=15)
                if resp.status_code == 200:
                    return resp.json().get("total_count")
                return None
            except Exception:
                return None

        pr_total, pr_comments_total, issue_comments_total = await asyncio.gather(
            _get_total("pulls"),
            _get_total("pulls/comments"),
            _get_total("issues/comments"),
        )

        repo_full = f"{owner}/{repo}"
        pure_issues_total = await _get_total_via_search(f"repo:{repo_full} is:issue")

        result["github_pr_total"] = pr_total
        result["github_pure_issues_total"] = pure_issues_total
        result["github_pr_comments_total"] = pr_comments_total
        result["github_issue_comments_total"] = issue_comments_total

        return result

    async def fetch_pr_files(self, owner: str, repo: str, pr_number: int) -> Dict[str, Any]:
        """获取指定 PR 的变更文件列表"""
        logger.info(f"开始获取 {owner}/{repo} PR#{pr_number} 的变更文件")
        all_files = []
        page = 1
        error = None

        try:
            while True:
                headers = await self._get_headers()
                url = f"{self.base_url}/repos/{owner}/{repo}/pulls/{pr_number}/files"
                params = {"per_page": 100, "page": page}

                response = await self._make_request(url, headers, params, 30)
                if response.status_code == 404:
                    error = "PR不存在"
                    break
                if response.status_code != 200:
                    error = f"API请求失败: {response.status_code}"
                    break

                files = response.json()
                if not files:
                    break

                for f in files:
                    all_files.append({
                        "filename": f.get("filename", ""),
                        "status": f.get("status", ""),
                        "additions": f.get("additions", 0),
                        "deletions": f.get("deletions", 0),
                        "changes": f.get("changes", 0),
                        "patch": f.get("patch", ""),
                        "sha": f.get("sha", ""),
                    })

                page += 1
                await asyncio.sleep(self.request_delay)

            logger.info(f"获取 {owner}/{repo} PR#{pr_number} 变更文件完成，共 {len(all_files)} 个")
        except Exception as e:
            error = str(e)
            logger.error(f"获取 {owner}/{repo} PR#{pr_number} 变更文件异常: {e}")

        return {"owner": owner, "repo": repo, "pr_number": pr_number,
                "files": all_files, "total": len(all_files), "error": error}

    async def fetch_all_pr_files(self, owner: str, repo: str, pr_numbers: List[int]) -> Dict[str, Any]:
        """异步并发获取多个 PR 的变更文件"""
        logger.info(f"开始并发获取 {owner}/{repo} {len(pr_numbers)} 个 PR 的变更文件")
        semaphore = asyncio.Semaphore(self.max_workers)

        async def _fetch(pr_num):
            async with semaphore:
                return await self.fetch_pr_files(owner, repo, pr_num)

        results = await asyncio.gather(*[_fetch(n) for n in pr_numbers], return_exceptions=True)
        success_count = sum(1 for r in results if not isinstance(r, Exception) and r["error"] is None)
        failed_count = len(results) - success_count
        final_results = []
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                final_results.append({"owner": owner, "repo": repo, "pr_number": pr_numbers[i],
                                      "files": [], "total": 0, "error": str(r)})
            else:
                final_results.append(r)

        result = {
            "owner": owner, "repo": repo,
            "results": final_results, "total_prs": len(pr_numbers),
            "success_count": success_count, "failed_count": failed_count,
        }
        logger.info(f"并发获取 {owner}/{repo} 变更文件完成: {success_count} 成功, {failed_count} 失败")
        return result


# 全局任务进度管理器
task_progress_manager = TaskProgress()
