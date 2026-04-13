"""
AtomGit API 服务
通过 AtomGit API v5 获取 PR 和评论数据

API 文档:
  GET /repos/:owner/:repo/pulls              → PR 列表
  GET /repos/:owner/:repo/pulls/:number      → PR 详情
  GET /repos/:owner/:repo/pulls/:number/comments → PR 评论
"""
import re
import time
import logging
import requests
from typing import Dict, Any, List, Optional
from functools import wraps
from datetime import datetime

from .config import ATOMGIT_CONFIG

logger = logging.getLogger(__name__)


def retry_on_failure(max_retries: int = 3, delay: float = 1.0):
    """重试装饰器"""
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
                        logger.warning(f"请求失败 (尝试 {attempt+1}/{max_retries}): {e}, {delay}s 后重试")
                        time.sleep(delay)
                    else:
                        logger.error(f"请求失败，已达最大重试次数: {e}")
            raise last_exception
        return wrapper
    return decorator


class AtomGitService:
    """
    AtomGit API 服务类
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

        logger.info(f"AtomGit 服务初始化完成, Base URL: {self.base_url}")

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
    def _request(self, url: str, params: Dict = None) -> requests.Response:
        """发起 API 请求"""
        headers = {"Accept": "application/json"}
        response = requests.get(url, headers=headers, params=params, timeout=self.config["timeout"])

        if response.status_code == 401:
            raise Exception(f"Token 无效: {response.text[:200]}")
        if response.status_code == 404:
            raise Exception(f"资源不存在: {url}")
        if response.status_code != 200:
            raise Exception(f"API 请求失败: {response.status_code} - {response.text[:200]}")

        return response

    def get_user(self) -> Optional[Dict[str, Any]]:
        """获取当前用户信息（验证 Token）"""
        try:
            r = self._request(f"{self.base_url}/user", self._get_params())
            return r.json()
        except Exception as e:
            logger.error(f"获取用户信息失败: {e}")
            return None

    def fetch_pulls(self, owner: str, repo: str,
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
            r = self._request(url, params)
            pulls = r.json()

            # 格式化 PR 数据
            formatted = [self._format_pull(p) for p in pulls]

            return {
                "owner": owner,
                "repo": repo,
                "pulls": formatted,
                "total": len(formatted),
                "page": page,
                "error": None,
            }
        except Exception as e:
            logger.error(f"获取 PR 列表失败: {e}")
            return {"owner": owner, "repo": repo, "pulls": [], "total": 0, "error": str(e)}

    def fetch_pull_comments(self, owner: str, repo: str,
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
            r = self._request(url, params)
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

    def fetch_all_pull_comments(self, owner: str, repo: str,
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
            result = self.fetch_pull_comments(owner, repo, pull_number, page=page, per_page=100)
            if result.get("error"):
                return result

            comments = result.get("comments", [])
            all_comments.extend(comments)

            if len(comments) < 100:
                break

            page += 1
            time.sleep(self.request_delay)

        return {
            "owner": owner,
            "repo": repo,
            "pull_number": pull_number,
            "comments": all_comments,
            "total": len(all_comments),
            "error": None,
        }

    def fetch_pulls_with_comments(self, owner: str, repo: str,
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
        pulls_result = self.fetch_pulls(owner, repo, state=state, per_page=limit)
        if pulls_result.get("error"):
            return pulls_result

        pulls = pulls_result["pulls"]
        results = []
        total_comments = 0
        bot_comments = 0

        for i, pull in enumerate(pulls, 1):
            pull_number = pull["number"]

            # 获取评论
            comment_result = self.fetch_all_pull_comments(owner, repo, pull_number)
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

            time.sleep(self.request_delay)

        return {
            "owner": owner,
            "repo": repo,
            "results": results,
            "total_prs": len(results),
            "total_comments": total_comments,
            "bot_comments": bot_comments,
            "error": None,
        }

    def fetch_all_project_comments(self, owner: str, repo: str,
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
            pulls_result = self.fetch_pulls(owner, repo, state=state, page=page, per_page=per_page)
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
                comment_result = self.fetch_all_pull_comments(owner, repo, pull_number)
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

                time.sleep(self.request_delay)

            # 检查是否需要继续翻页
            if max_prs > 0 and total_prs >= max_prs:
                break
            if len(pulls) < per_page:
                break

            page += 1
            time.sleep(self.request_delay)

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
