"""
AtomGit API 服务（异步版本）
通过 AtomGit API v5 获取 PR 和评论数据，使用 httpx 异步客户端

API 文档 (AtomGit/Gitee 风格 API v5):
  GET /repos/:owner/:repo/pulls                     → PR 列表
  GET /repos/:owner/:repo/pulls/:number             → PR 详情
  GET /repos/:owner/:repo/pulls/:number/comments    → PR 评论 (review comments)
  GET /repos/:owner/:repo/pulls/:number/commits     → PR 提交记录
  GET /repos/:owner/:repo/pulls/:number/files       → PR 变更文件
  GET /repos/:owner/:repo/pulls/:number/reviews     → PR Reviews
  GET /repos/:owner/:repo/issues/:number/timeline   → Issue/PR 时间线
  GET /repos/:owner/:repo/issues                    → Issue 列表
  GET /repos/:owner/:repo/issues/:number            → Issue 详情
"""
import re
import asyncio
import logging
from typing import Dict, Any, List, Optional
from functools import wraps

import httpx

from .config import ATOMGIT_CONFIG

logger = logging.getLogger(__name__)


def retry_on_failure(max_retries: int = 3, delay: float = 1.0):
    """异步重试装饰器"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        logger.warning(f"请求失败 (尝试 {attempt+1}/{max_retries}): {e}, {delay}s 后重试")
                        await asyncio.sleep(delay)
                    else:
                        logger.error(f"请求失败，已达最大重试次数: {e}")
            raise last_exception
        return wrapper
    return decorator


class AtomGitService:
    """
    AtomGit API 服务类（异步版本）
    封装 AtomGit API v5 的 PR 评论数据获取
    """

    def __init__(self, access_token: str = None, config: Dict[str, Any] = None):
        """
        初始化服务
        :param access_token: AtomGit 访问令牌
        :param config: 配置覆盖
        """
        self.config = {**ATOMGIT_CONFIG, **(config or {})}
        self.access_token = access_token or self.config.get("access_token", "")
        self.base_url = self.config["base_url"]
        self.per_page = self.config["per_page"]
        self.request_delay = self.config["request_delay"]

        # 已知 Bot 模式
        self.known_bots = [
            "cann-robot", "openeuler-bot", "mindspore-bot",
            "ci-bot", "renovate-bot", "dependabot-bot",
        ]

        # 异步 HTTP 客户端（跟随服务生命周期）
        self._client: Optional[httpx.AsyncClient] = None

        logger.info(f"AtomGit 服务初始化完成, Base URL: {self.base_url}")

    def _get_client(self) -> httpx.AsyncClient:
        """获取或创建异步 HTTP 客户端"""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self.config["timeout"])
        return self._client

    async def close(self):
        """关闭 HTTP 客户端"""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    def _get_params(self, **kwargs) -> Dict[str, Any]:
        """构建请求参数（自动附加 token）"""
        params = {"access_token": self.access_token}
        params.update(kwargs)
        return params

    def _is_bot(self, username: str) -> bool:
        """判断是否为 Bot 用户"""
        if not username:
            return False
        for bot in self.known_bots:
            if bot in username.lower():
                return True
        if re.search(r'(-bot|\[bot\]|_bot)$', username, re.IGNORECASE):
            return True
        return False

    @retry_on_failure(max_retries=3, delay=1.0)
    async def _request(self, url: str, params: Dict = None) -> httpx.Response:
        """发起异步 API 请求"""
        client = self._get_client()
        headers = {"Accept": "application/json"}
        response = await client.get(url, headers=headers, params=params)

        if response.status_code == 401:
            raise Exception(f"Token 无效: {response.text[:200]}")
        if response.status_code == 404:
            raise Exception(f"资源不存在: {url}")
        if response.status_code != 200:
            raise Exception(f"API 请求失败: {response.status_code} - {response.text[:200]}")

        return response

    async def get_user(self) -> Optional[Dict[str, Any]]:
        """获取当前用户信息（验证 Token）"""
        try:
            r = await self._request(f"{self.base_url}/user", self._get_params())
            return r.json()
        except Exception as e:
            logger.error(f"获取用户信息失败: {e}")
            return None

    async def fetch_pulls(self, owner: str, repo: str,
                    state: str = "all", page: int = 1,
                    per_page: int = None, sort: str = "updated",
                    direction: str = "desc") -> Dict[str, Any]:
        """
        获取 PR 列表
        :param owner: 仓库所有者
        :param repo: 仓库名
        :param state: 状态 open/closed/all
        :param page: 页码
        :param per_page: 每页数量
        :param sort: 排序方式 created/updated
        :param direction: 排序方向 asc/desc
        :return: PR 列表数据
        """
        url = f"{self.base_url}/repos/{owner}/{repo}/pulls"
        params = self._get_params(
            state=state, page=page,
            per_page=per_page or self.per_page,
            sort=sort, direction=direction,
        )

        logger.info(f"获取 PR 列表: {owner}/{repo}, page={page}")

        try:
            r = await self._request(url, params)
            pulls = r.json()

            # 从响应头获取总数（AtomGit/Gitee 风格）
            total_count = None
            for header_key in ["X-Total", "X-Total-Count", "total_count"]:
                val = r.headers.get(header_key)
                if val:
                    try:
                        total_count = int(val)
                        break
                    except (ValueError, TypeError):
                        pass

            # 格式化 PR 数据
            formatted = [self._format_pull(p) for p in pulls]

            return {
                "owner": owner,
                "repo": repo,
                "pulls": formatted,
                "total": total_count if total_count is not None else len(formatted),
                "page": page,
                "error": None,
            }
        except Exception as e:
            logger.error(f"获取 PR 列表失败: {e}")
            return {"owner": owner, "repo": repo, "pulls": [], "total": 0, "error": str(e)}

    async def fetch_pull_comments(self, owner: str, repo: str,
                            pull_number: int, page: int = 1,
                            per_page: int = None) -> Dict[str, Any]:
        """
        获取 PR 评论
        :param owner: 仓库所有者
        :param repo: 仓库名
        :param pull_number: PR 编号
        :param page: 页码
        :param per_page: 每页数量
        :return: 评论数据
        """
        url = f"{self.base_url}/repos/{owner}/{repo}/pulls/{pull_number}/comments"
        params = self._get_params(page=page, per_page=per_page or self.per_page)

        logger.info(f"获取 PR 评论: {owner}/{repo} #{pull_number}, page={page}")

        try:
            r = await self._request(url, params)
            comments = r.json()

            # 格式化评论
            formatted = [self._format_comment(c) for c in comments]

            return {
                "owner": owner,
                "repo": repo,
                "pull_number": pull_number,
                "comments": formatted,
                "total": len(formatted),
                "page": page,
                "error": None,
            }
        except Exception as e:
            logger.error(f"获取 PR 评论失败: {e}")
            return {"owner": owner, "repo": repo, "pull_number": pull_number,
                    "comments": [], "total": 0, "error": str(e)}

    async def fetch_all_pull_comments(self, owner: str, repo: str,
                                pull_number: int) -> Dict[str, Any]:
        """
        获取 PR 的全部评论（自动分页）
        :param owner: 仓库所有者
        :param repo: 仓库名
        :param pull_number: PR 编号
        :return: 全部评论数据
        """
        all_comments = []
        page = 1

        while True:
            result = await self.fetch_pull_comments(owner, repo, pull_number, page=page, per_page=100)
            if result.get("error"):
                return result

            comments = result.get("comments", [])
            all_comments.extend(comments)

            if len(comments) < 100:
                break

            page += 1
            await asyncio.sleep(self.request_delay)

        return {
            "owner": owner,
            "repo": repo,
            "pull_number": pull_number,
            "comments": all_comments,
            "total": len(all_comments),
            "error": None,
        }

    async def fetch_pulls_with_comments(self, owner: str, repo: str,
                                  limit: int = 10, state: str = "all") -> Dict[str, Any]:
        """
        批量获取 PR 及其评论
        :param owner: 仓库所有者
        :param repo: 仓库名
        :param limit: PR 数量限制
        :param state: PR 状态
        :return: PR 及评论数据
        """
        logger.info(f"批量获取 {owner}/{repo} PR 评论, limit={limit}")

        # 获取 PR 列表
        pulls_result = await self.fetch_pulls(owner, repo, state=state, per_page=limit)
        if pulls_result.get("error"):
            return pulls_result

        pulls = pulls_result["pulls"]
        results = []
        total_comments = 0
        bot_comments = 0

        for i, pull in enumerate(pulls, 1):
            pull_number = pull["number"]

            # 获取评论
            comment_result = await self.fetch_all_pull_comments(owner, repo, pull_number)
            comments = comment_result.get("comments", [])

            # 统计
            pr_bot = sum(1 for c in comments if c.get("is_bot"))
            total_comments += len(comments)
            bot_comments += pr_bot

            results.append({
                "pull_number": pull_number,
                "title": pull["title"],
                "state": pull["state"],
                "user": pull["user"],
                "comments": comments,
                "comment_count": len(comments),
                "bot_comment_count": pr_bot,
            })

            logger.info(
                f"  [{i}/{len(pulls)}] PR#{pull_number}: "
                f"{len(comments)} 条评论 (Bot:{pr_bot})"
            )

            await asyncio.sleep(self.request_delay)

        return {
            "owner": owner,
            "repo": repo,
            "results": results,
            "total_prs": len(results),
            "total_comments": total_comments,
            "bot_comments": bot_comments,
            "error": None,
        }

    async def fetch_all_project_comments(self, owner: str, repo: str,
                                        state: str = "all",
                                        max_prs: int = 0,
                                        skip_no_comments: bool = False,
                                        on_pr_done: callable = None) -> Dict[str, Any]:
        """
        获取整个项目的全部 PR 评论（自动分页遍历所有 PR）
        :param owner: 仓库所有者
        :param repo: 仓库名
        :param state: PR 状态 open/closed/all
        :param max_prs: 最大 PR 数量，0 表示全部
        :param skip_no_comments: 跳过无评论的 PR
        :param on_pr_done: 单个 PR 完成回调 fn(pr_number, comment_count, bot_count, total_done)
        :return: 全量结果
        """
        logger.info(f"全量获取 {owner}/{repo} 全部 PR 评论, state={state}, max_prs={max_prs or '全部'}")

        all_results = []
        total_comments = 0
        bot_comments = 0
        total_prs = 0
        page = 1
        per_page = 100

        # 遍历所有 PR 页
        while True:
            pulls_result = await self.fetch_pulls(owner, repo, state=state, page=page, per_page=per_page)
            if pulls_result.get("error"):
                logger.error(f"获取 PR 列表失败 (page={page}): {pulls_result['error']}")
                break

            pulls = pulls_result.get("pulls", [])
            if not pulls:
                break

            for pull in pulls:
                # 检查是否达到上限
                if max_prs > 0 and total_prs >= max_prs:
                    break

                pull_number = pull["number"]
                total_prs += 1

                # 跳过无评论的 PR
                if skip_no_comments and pull.get("comments_count", 0) == 0 and pull.get("review_comments_count", 0) == 0:
                    logger.debug(f"跳过无评论 PR#{pull_number}")
                    continue

                # 获取评论
                comment_result = await self.fetch_all_pull_comments(owner, repo, pull_number)
                comments = comment_result.get("comments", [])

                pr_bot = sum(1 for c in comments if c.get("is_bot"))
                total_comments += len(comments)
                bot_comments += pr_bot

                all_results.append({
                    "pull_number": pull_number,
                    "title": pull["title"],
                    "state": pull["state"],
                    "user": pull["user"],
                    "comments": comments,
                    "comment_count": len(comments),
                    "bot_comment_count": pr_bot,
                })

                logger.info(
                    f"  [{total_prs}] PR#{pull_number}: "
                    f"{len(comments)} 条评论 (Bot:{pr_bot})"
                )

                # 回调通知
                if on_pr_done:
                    try:
                        on_pr_done(pull_number, len(comments), pr_bot, total_prs)
                    except Exception:
                        pass

                await asyncio.sleep(self.request_delay)

            # 检查是否需要继续翻页
            if max_prs > 0 and total_prs >= max_prs:
                break
            if len(pulls) < per_page:
                break

            page += 1
            await asyncio.sleep(self.request_delay)

        logger.info(
            f"全量获取完成: {owner}/{repo} "
            f"共 {total_prs} 个 PR, {total_comments} 条评论, {bot_comments} 条 Bot 评论"
        )

        return {
            "owner": owner,
            "repo": repo,
            "results": all_results,
            "total_prs": total_prs,
            "total_comments": total_comments,
            "bot_comments": bot_comments,
            "error": None,
        }

    async def fetch_pull_detail(self, owner: str, repo: str, pull_number: int) -> Dict[str, Any]:
        """
        获取单个 PR 的详细信息
        AtomGit API: GET /repos/:owner/:repo/pulls/:number
        """
        url = f"{self.base_url}/repos/{owner}/{repo}/pulls/{pull_number}"
        params = self._get_params()

        logger.info(f"获取 PR 详情: {owner}/{repo} #{pull_number}")

        try:
            r = await self._request(url, params)
            pr = r.json()
            return {
                "owner": owner,
                "repo": repo,
                "pull_number": pull_number,
                "detail": self._format_pull_detail(pr),
                "error": None,
            }
        except Exception as e:
            logger.error(f"获取 PR 详情失败: {e}")
            return {"owner": owner, "repo": repo, "pull_number": pull_number,
                    "detail": {}, "error": str(e)}

    async def fetch_pull_reviews(self, owner: str, repo: str, pull_number: int) -> Dict[str, Any]:
        """
        获取 PR 的 Reviews
        AtomGit API: GET /repos/:owner/:repo/pulls/:number/reviews
        """
        url = f"{self.base_url}/repos/{owner}/{repo}/pulls/{pull_number}/reviews"
        all_reviews = []
        page = 1

        logger.info(f"获取 PR Reviews: {owner}/{repo} #{pull_number}")

        try:
            while True:
                params = self._get_params(page=page, per_page=self.per_page)
                r = await self._request(url, params)
                reviews = r.json()

                if not reviews:
                    break

                for review in reviews:
                    all_reviews.append(self._format_review(review))

                if len(reviews) < self.per_page:
                    break

                page += 1
                await asyncio.sleep(self.request_delay)

            return {
                "owner": owner,
                "repo": repo,
                "pull_number": pull_number,
                "reviews": all_reviews,
                "total": len(all_reviews),
                "error": None,
            }
        except Exception as e:
            logger.error(f"获取 PR Reviews 失败: {e}")
            return {"owner": owner, "repo": repo, "pull_number": pull_number,
                    "reviews": [], "total": 0, "error": str(e)}

    async def fetch_pull_commits(self, owner: str, repo: str, pull_number: int) -> Dict[str, Any]:
        """
        获取 PR 的 Commits
        AtomGit API: GET /repos/:owner/:repo/pulls/:number/commits
        """
        url = f"{self.base_url}/repos/{owner}/{repo}/pulls/{pull_number}/commits"
        all_commits = []
        page = 1

        logger.info(f"获取 PR Commits: {owner}/{repo} #{pull_number}")

        try:
            while True:
                params = self._get_params(page=page, per_page=self.per_page)
                r = await self._request(url, params)
                commits = r.json()

                if not commits:
                    break

                for commit in commits:
                    all_commits.append(self._format_commit(commit))

                if len(commits) < self.per_page:
                    break

                page += 1
                await asyncio.sleep(self.request_delay)

            return {
                "owner": owner,
                "repo": repo,
                "pull_number": pull_number,
                "commits": all_commits,
                "total": len(all_commits),
                "error": None,
            }
        except Exception as e:
            logger.error(f"获取 PR Commits 失败: {e}")
            return {"owner": owner, "repo": repo, "pull_number": pull_number,
                    "commits": [], "total": 0, "error": str(e)}

    async def fetch_pull_files(self, owner: str, repo: str, pull_number: int) -> Dict[str, Any]:
        """
        获取 PR 的变更文件列表
        AtomGit API: GET /repos/:owner/:repo/pulls/:number/files
        """
        url = f"{self.base_url}/repos/{owner}/{repo}/pulls/{pull_number}/files"
        all_files = []
        page = 1

        logger.info(f"获取 PR 变更文件: {owner}/{repo} #{pull_number}")

        try:
            while True:
                params = self._get_params(page=page, per_page=self.per_page)
                r = await self._request(url, params)
                files = r.json()

                if not files:
                    break

                for f in files:
                    all_files.append(self._format_file(f))

                if len(files) < self.per_page:
                    break

                page += 1
                await asyncio.sleep(self.request_delay)

            return {
                "owner": owner,
                "repo": repo,
                "pull_number": pull_number,
                "files": all_files,
                "total": len(all_files),
                "error": None,
            }
        except Exception as e:
            logger.error(f"获取 PR 变更文件失败: {e}")
            return {"owner": owner, "repo": repo, "pull_number": pull_number,
                    "files": [], "total": 0, "error": str(e)}

    async def fetch_pull_timeline(self, owner: str, repo: str, pull_number: int) -> Dict[str, Any]:
        """
        获取 PR 的时间线事件
        AtomGit API: GET /repos/:owner/:repo/issues/:number/timeline
        注意: 时间线通过 Issues API 访问，PR 也是一种 Issue
        """
        url = f"{self.base_url}/repos/{owner}/{repo}/issues/{pull_number}/timeline"
        all_events = []
        page = 1

        logger.info(f"获取 PR 时间线: {owner}/{repo} #{pull_number}")

        try:
            while True:
                params = self._get_params(page=page, per_page=self.per_page)
                r = await self._request(url, params)
                events = r.json()

                if not events:
                    break

                for event in events:
                    all_events.append(self._format_timeline_event(event))

                if len(events) < self.per_page:
                    break

                page += 1
                await asyncio.sleep(self.request_delay)

            return {
                "owner": owner,
                "repo": repo,
                "pull_number": pull_number,
                "events": all_events,
                "total": len(all_events),
                "error": None,
            }
        except Exception as e:
            logger.error(f"获取 PR 时间线失败: {e}")
            return {"owner": owner, "repo": repo, "pull_number": pull_number,
                    "events": [], "total": 0, "error": str(e)}

    async def fetch_issues(self, owner: str, repo: str,
                           state: str = "all", page: int = 1,
                           per_page: int = None,
                           max_count: int = 0) -> Dict[str, Any]:
        """
        获取仓库的 Issue 列表（不含 PR）
        AtomGit API: GET /repos/:owner/:repo/issues
        """
        url = f"{self.base_url}/repos/{owner}/{repo}/issues"
        all_issues = []
        current_page = page

        logger.info(f"获取 Issue 列表: {owner}/{repo}, state={state}")

        try:
            while True:
                params = self._get_params(
                    state=state, page=current_page,
                    per_page=per_page or self.per_page,
                )
                r = await self._request(url, params)
                issues = r.json()

                if not issues:
                    break

                for issue in issues:
                    # 跳过 PR（AtomGit 中 PR 也会出现在 issues 列表）
                    if "pull_request" in issue:
                        continue
                    all_issues.append(self._format_issue(issue))

                if max_count > 0 and len(all_issues) >= max_count:
                    all_issues = all_issues[:max_count]
                    break

                if len(issues) < (per_page or self.per_page):
                    break

                current_page += 1
                await asyncio.sleep(self.request_delay)

            return {
                "owner": owner,
                "repo": repo,
                "issues": all_issues,
                "total": len(all_issues),
                "page": page,
                "error": None,
            }
        except Exception as e:
            logger.error(f"获取 Issue 列表失败: {e}")
            return {"owner": owner, "repo": repo, "issues": [], "total": 0, "error": str(e)}

    async def fetch_issue_detail(self, owner: str, repo: str, issue_number: int) -> Dict[str, Any]:
        """
        获取单个 Issue 的详细信息
        AtomGit API: GET /repos/:owner/:repo/issues/:number
        """
        url = f"{self.base_url}/repos/{owner}/{repo}/issues/{issue_number}"
        params = self._get_params()

        logger.info(f"获取 Issue 详情: {owner}/{repo} #{issue_number}")

        try:
            r = await self._request(url, params)
            issue = r.json()
            return {
                "owner": owner,
                "repo": repo,
                "issue_number": issue_number,
                "detail": self._format_issue(issue),
                "error": None,
            }
        except Exception as e:
            logger.error(f"获取 Issue 详情失败: {e}")
            return {"owner": owner, "repo": repo, "issue_number": issue_number,
                    "detail": {}, "error": str(e)}

    # ========================
    # 批量并发获取方法
    # ========================

    async def fetch_all_pull_details(self, owner: str, repo: str,
                                     pr_numbers: List[int],
                                     max_workers: int = 3) -> Dict[str, Any]:
        """并发获取多个 PR 的详细信息"""
        logger.info(f"并发获取 {owner}/{repo} {len(pr_numbers)} 个 PR 详情")
        semaphore = asyncio.Semaphore(max_workers)

        async def _fetch(pr_num):
            async with semaphore:
                result = await self.fetch_pull_detail(owner, repo, pr_num)
                await asyncio.sleep(self.request_delay)
                return result

        results = await asyncio.gather(*[_fetch(n) for n in pr_numbers], return_exceptions=True)
        return self._collect_batch_results(pr_numbers, results, "detail")

    async def fetch_all_pull_reviews(self, owner: str, repo: str,
                                     pr_numbers: List[int],
                                     max_workers: int = 3) -> Dict[str, Any]:
        """并发获取多个 PR 的 Reviews"""
        logger.info(f"并发获取 {owner}/{repo} {len(pr_numbers)} 个 PR Reviews")
        semaphore = asyncio.Semaphore(max_workers)

        async def _fetch(pr_num):
            async with semaphore:
                result = await self.fetch_pull_reviews(owner, repo, pr_num)
                await asyncio.sleep(self.request_delay)
                return result

        results = await asyncio.gather(*[_fetch(n) for n in pr_numbers], return_exceptions=True)
        return self._collect_batch_results(pr_numbers, results, "reviews")

    async def fetch_all_pull_commits(self, owner: str, repo: str,
                                     pr_numbers: List[int],
                                     max_workers: int = 3) -> Dict[str, Any]:
        """并发获取多个 PR 的 Commits"""
        logger.info(f"并发获取 {owner}/{repo} {len(pr_numbers)} 个 PR Commits")
        semaphore = asyncio.Semaphore(max_workers)

        async def _fetch(pr_num):
            async with semaphore:
                result = await self.fetch_pull_commits(owner, repo, pr_num)
                await asyncio.sleep(self.request_delay)
                return result

        results = await asyncio.gather(*[_fetch(n) for n in pr_numbers], return_exceptions=True)
        return self._collect_batch_results(pr_numbers, results, "commits")

    async def fetch_all_pull_files(self, owner: str, repo: str,
                                   pr_numbers: List[int],
                                   max_workers: int = 3) -> Dict[str, Any]:
        """并发获取多个 PR 的变更文件"""
        logger.info(f"并发获取 {owner}/{repo} {len(pr_numbers)} 个 PR 变更文件")
        semaphore = asyncio.Semaphore(max_workers)

        async def _fetch(pr_num):
            async with semaphore:
                result = await self.fetch_pull_files(owner, repo, pr_num)
                await asyncio.sleep(self.request_delay)
                return result

        results = await asyncio.gather(*[_fetch(n) for n in pr_numbers], return_exceptions=True)
        return self._collect_batch_results(pr_numbers, results, "files")

    async def fetch_all_pull_timelines(self, owner: str, repo: str,
                                       pr_numbers: List[int],
                                       max_workers: int = 3) -> Dict[str, Any]:
        """并发获取多个 PR 的时间线"""
        logger.info(f"并发获取 {owner}/{repo} {len(pr_numbers)} 个 PR 时间线")
        semaphore = asyncio.Semaphore(max_workers)

        async def _fetch(pr_num):
            async with semaphore:
                result = await self.fetch_pull_timeline(owner, repo, pr_num)
                await asyncio.sleep(self.request_delay)
                return result

        results = await asyncio.gather(*[_fetch(n) for n in pr_numbers], return_exceptions=True)
        return self._collect_batch_results(pr_numbers, results, "events")

    def _collect_batch_results(self, pr_numbers: List[int], results: List,
                               data_key: str) -> Dict[str, Any]:
        """汇总批量并发获取结果"""
        success_count = 0
        failed_count = 0
        final_results = []

        for i, r in enumerate(results):
            if isinstance(r, Exception):
                failed_count += 1
                final_results.append({
                    "owner": "", "repo": "", "pull_number": pr_numbers[i],
                    data_key: [], "total": 0, "error": str(r),
                })
            else:
                final_results.append(r)
                if r.get("error") is None:
                    success_count += 1
                else:
                    failed_count += 1

        return {
            "results": final_results,
            "total_prs": len(pr_numbers),
            "success_count": success_count,
            "failed_count": failed_count,
        }

    # ========================
    # 数据格式化方法
    # ========================

    def _format_pull(self, pull: Dict) -> Dict[str, Any]:
        """格式化 PR 数据"""
        user = pull.get("user", {})
        username = user.get("login", "")
        return {
            "number": pull.get("number"),
            "title": pull.get("title"),
            "body": pull.get("body"),
            "state": pull.get("state"),
            "user": username,
            "user_id": user.get("id"),
            "is_bot": self._is_bot(username),
            "labels": [l.get("name", l) if isinstance(l, dict) else l for l in pull.get("labels", [])],
            "comments_count": pull.get("comments", 0),
            "review_comments_count": pull.get("review_comments", 0),
            "created_at": pull.get("created_at"),
            "updated_at": pull.get("updated_at"),
            "closed_at": pull.get("closed_at"),
            "merged_at": pull.get("merged_at"),
            "html_url": pull.get("html_url"),
        }

    def _format_comment(self, comment: Dict) -> Dict[str, Any]:
        """格式化评论数据"""
        user = comment.get("user", {})
        username = user.get("login", "")
        is_bot = self._is_bot(username)

        formatted = {
            "id": comment.get("id"),
            "body": comment.get("body"),
            "user": username,
            "user_id": user.get("id"),
            "is_bot": is_bot,
            "created_at": comment.get("created_at"),
            "updated_at": comment.get("updated_at"),
            "html_url": comment.get("html_url"),
        }

        # 从 Bot 评论中提取流水线信息
        if is_bot:
            pipeline_info = self._extract_pipeline_info(comment.get("body", ""))
            if pipeline_info:
                formatted["pipeline_info"] = pipeline_info

        return formatted

    def _format_pull_detail(self, pr: Dict) -> Dict[str, Any]:
        """格式化 PR 详细信息"""
        user = pr.get("user", {}) or {}
        username = user.get("login", "")
        head = pr.get("head", {}) or {}
        base = pr.get("base", {}) or {}
        milestone = pr.get("milestone") or {}

        return {
            "number": pr.get("number"),
            "title": pr.get("title"),
            "body": pr.get("body"),
            "state": pr.get("state"),
            "draft": pr.get("draft", False),
            "user": {
                "login": username,
                "id": user.get("id"),
                "avatar_url": user.get("avatar_url"),
                "type": user.get("type", "User"),
            },
            "labels": [
                {"name": l.get("name", l), "color": l.get("color", "")}
                if isinstance(l, dict) else {"name": l, "color": ""}
                for l in pr.get("labels", [])
            ],
            "assignees": [
                {"login": a.get("login"), "avatar_url": a.get("avatar_url")}
                for a in (pr.get("assignees") or [])
            ],
            "requested_reviewers": [
                {"login": r.get("login"), "avatar_url": r.get("avatar_url")}
                for r in (pr.get("requested_reviewers") or [])
            ],
            "milestone": {
                "number": milestone.get("number"),
                "title": milestone.get("title"),
                "state": milestone.get("state"),
            } if milestone else None,
            "head": {
                "ref": head.get("ref"),
                "sha": head.get("sha"),
                "label": head.get("label"),
            },
            "base": {
                "ref": base.get("ref"),
                "sha": base.get("sha"),
                "label": base.get("label"),
            },
            "created_at": pr.get("created_at"),
            "updated_at": pr.get("updated_at"),
            "closed_at": pr.get("closed_at"),
            "merged_at": pr.get("merged_at"),
            "mergeable": pr.get("mergeable"),
            "merged": pr.get("merged", False),
            "merge_commit_sha": pr.get("merge_commit_sha"),
            "commits": pr.get("commits"),
            "additions": pr.get("additions"),
            "deletions": pr.get("deletions"),
            "changed_files": pr.get("changed_files"),
            "comments": pr.get("comments", 0),
            "review_comments": pr.get("review_comments", 0),
            "html_url": pr.get("html_url"),
        }

    def _format_review(self, review: Dict) -> Dict[str, Any]:
        """格式化 Review 数据"""
        user = review.get("user", {}) or {}
        username = user.get("login", "")
        return {
            "id": review.get("id"),
            "review_id": review.get("id"),
            "user": username,
            "user_id": user.get("id"),
            "user_type": user.get("type", "User"),
            "avatar_url": user.get("avatar_url"),
            "state": review.get("state"),
            "body": review.get("body"),
            "submitted_at": review.get("submitted_at"),
            "commit_id": review.get("commit_id"),
            "author_association": review.get("author_association"),
            "html_url": review.get("html_url"),
        }

    def _format_commit(self, commit: Dict) -> Dict[str, Any]:
        """格式化 Commit 数据"""
        commit_data = commit.get("commit", {}) or {}
        author = commit_data.get("author", {}) or {}
        committer = commit_data.get("committer", {}) or {}
        return {
            "sha": commit.get("sha", ""),
            "message": commit_data.get("message", ""),
            "author_name": author.get("name", ""),
            "author_email": author.get("email", ""),
            "author_date": author.get("date", ""),
            "committer_name": committer.get("name", ""),
            "committer_date": committer.get("date", ""),
            "url": commit.get("html_url", ""),
            "verified": commit_data.get("verification", {}).get("verified", False)
            if commit_data.get("verification") else False,
        }

    def _format_file(self, f: Dict) -> Dict[str, Any]:
        """格式化变更文件数据"""
        return {
            "filename": f.get("filename", ""),
            "status": f.get("status", ""),
            "additions": f.get("additions", 0),
            "deletions": f.get("deletions", 0),
            "changes": f.get("changes", 0),
            "sha": f.get("sha", ""),
            "patch": f.get("patch", ""),
        }

    def _format_timeline_event(self, event: Dict) -> Dict[str, Any]:
        """格式化时间线事件"""
        actor = event.get("actor") or event.get("user") or {}
        return {
            "id": event.get("id"),
            "event": event.get("event"),
            "actor": actor.get("login"),
            "actor_id": actor.get("id"),
            "commit_id": event.get("commit_id"),
            "created_at": event.get("created_at"),
            "url": event.get("html_url") or event.get("url"),
            "label": (event.get("label") or {}).get("name") if event.get("label") else None,
            "state": event.get("state"),
        }

    def _format_issue(self, issue: Dict) -> Dict[str, Any]:
        """格式化 Issue 数据"""
        user = issue.get("user", {}) or {}
        return {
            "number": issue.get("number"),
            "title": issue.get("title"),
            "body": (issue.get("body") or "")[:500],
            "state": issue.get("state"),
            "user": user.get("login"),
            "user_id": user.get("id"),
            "labels": [
                l.get("name", l) if isinstance(l, dict) else l
                for l in (issue.get("labels") or [])
            ],
            "assignees": [
                a.get("login") for a in (issue.get("assignees") or [])
            ],
            "comments_count": issue.get("comments", 0),
            "created_at": issue.get("created_at"),
            "updated_at": issue.get("updated_at"),
            "closed_at": issue.get("closed_at"),
            "html_url": issue.get("html_url"),
        }

    def _extract_pipeline_info(self, body: str) -> Optional[Dict[str, Any]]:
        """
        从 Bot 评论中提取流水线信息
        识别 openlibing.com 流水线链接和任务状态
        """
        if not body or "openlibing.com" not in body:
            return None

        info = {
            "platform": "openlibing",
            "pipeline_id": None,
            "pipeline_run_id": None,
            "project_name": None,
            "tasks": [],
        }

        # 提取 pipelineId
        m = re.search(r'pipelineId=([0-9a-f]+)', body)
        if m:
            info["pipeline_id"] = m.group(1)

        # 提取 pipelineRunId
        m = re.search(r'pipelineRunId=([0-9a-f]+)', body)
        if m:
            info["pipeline_run_id"] = m.group(1)

        # 提取 projectName
        m = re.search(r'projectName=([A-Za-z0-9_]+)', body)
        if m:
            info["project_name"] = m.group(1)

        # 提取任务状态表格: <strong>任务名</strong> ... ✅/❌ SUCCESS/FAILED
        task_pattern = re.compile(
            r'<strong>([^<]+)</strong>.*?(✅|❌)\s*(\w+)',
            re.DOTALL
        )
        for m in task_pattern.finditer(body):
            info["tasks"].append({
                "name": m.group(1).strip(),
                "status": "success" if m.group(2) == "✅" else "failed",
                "result": m.group(3),
            })

        return info
