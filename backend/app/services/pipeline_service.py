"""
CI/CD 流水线服务 — GitCodePipelineClient

封装 GitCode API 的 MR 创建、评论触发、结果轮询、自动修复循环。
支持双 API：
  - v5: api.gitcode.com/api/v5（access_token 参数，Gitee/GitHub 风格）
  - v4: gitcode.net/api/v4（Private-Token 头，GitLab 风格）
"""
import asyncio
import json
import logging
import os
import re
import time
import urllib.parse
from datetime import datetime
from typing import AsyncGenerator, Dict, List, Optional, Tuple

import aiohttp

from app.services.claude_code_driver import claude_driver

logger = logging.getLogger(__name__)

# 第三方流水线评论解析正则（用于提取 CI/CD 结果细节）
PIPELINE_PATTERNS = {
    "all_passed": re.compile(r'✅\s*Pipeline\s+passed', re.IGNORECASE),
    "all_failed": re.compile(r'❌\s*Pipeline\s+failed', re.IGNORECASE),
    "stage_result": re.compile(r'(✅|❌)\s*(编译|单元测试|集成测试|精度测试|性能测试)'),
    "log_link": re.compile(r'\[([^\]]+)\]\((https?://[^\)]+)\)'),
}

STAGE_KEY_MAP = {
    "编译": "compile",
    "单元测试": "unit_test",
    "集成测试": "integration_test",
    "精度测试": "precision_test",
    "性能测试": "performance_test",
}

# CI/CD 编排步骤（用户可见的真实流程）
PIPELINE_STEPS = [
    {"name": "提交代码", "key": "git_commit"},
    {"name": "推送到 Fork 仓库", "key": "git_push"},
    {"name": "向上游创建 PR", "key": "create_pr"},
    {"name": "触发编译", "key": "trigger_ci"},
    {"name": "等待 CI/CD 结果", "key": "wait_ci"},
    {"name": "分析失败原因", "key": "analyze_failure"},
    {"name": "自动修复", "key": "auto_fix"},
    {"name": "提交修复并重试", "key": "fix_commit_retry"},
]


def _new_steps() -> list:
    """创建初始编排步骤列表（全部 pending）"""
    return [
        {**s, "status": "pending", "log": None, "started_at": None, "completed_at": None, "duration_ms": 0}
        for s in PIPELINE_STEPS
    ]


class GitCodePipelineClient:
    """GitCode CI/CD 流水线客户端"""

    def __init__(
        self,
        token: str,
        api_base: str = "v5",
        poll_interval: int = 30,
        poll_timeout: int = 1800,
        max_fix_rounds: int = 5,
    ):
        self.token = token
        # 选择 API 风格：v5 或 v4
        if api_base == "v4":
            self.api_base = "https://gitcode.net/api/v4"
            self.api_style = "v4"
        else:
            self.api_base = "https://api.gitcode.com/api/v5"
            self.api_style = "v5"
        self.poll_interval = poll_interval
        self.poll_timeout = poll_timeout
        self.max_fix_rounds = max_fix_rounds

    async def _request(
        self,
        method: str,
        path: str,
        params: dict = None,
        json_body: dict = None,
    ) -> Tuple[int, dict]:
        """统一 HTTP 请求，根据 api_style 选择认证方式"""
        headers = {"Accept": "application/json"}
        params = dict(params or {})

        if self.api_style == "v4":
            headers["Private-Token"] = self.token
        else:
            params["access_token"] = self.token

        url = f"{self.api_base}{path}"
        async with aiohttp.ClientSession() as session:
            async with session.request(
                method, url,
                headers=headers,
                params=params,
                json=json_body,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                body = {}
                try:
                    body = await resp.json()
                except Exception:
                    text = await resp.text()
                    body = {"raw": text[:500]}
                return resp.status, body

    async def get_repo_info(self, owner: str, repo: str) -> dict:
        """查询仓库信息，返回 {parent_owner, parent_repo, default_branch}"""
        if self.api_style == "v4":
            encoded = urllib.parse.quote(f"{owner}/{repo}", safe="")
            path = f"/projects/{encoded}"
        else:
            path = f"/repos/{owner}/{repo}"

        status, resp = await self._request("GET", path)
        if status != 200:
            return {}

        # 默认分支
        default_branch = resp.get("default_branch") or resp.get("default_branch_ref", "")

        # fork parent
        parent = resp.get("parent") or resp.get("fork_parent") or {}
        full_path = (
            parent.get("path_with_namespace")
            or parent.get("full_name")
            or parent.get("path")
            or ""
        )
        parent_owner, parent_repo = "", ""
        if "/" in full_path and not full_path.startswith("/"):
            parts = full_path.split("/", 1)
            if parts[0] and parts[1]:
                parent_owner, parent_repo = parts[0], parts[1]

        return {
            "parent_owner": parent_owner,
            "parent_repo": parent_repo,
            "default_branch": default_branch,
        }

    # ==================== MR 操作 ====================

    async def find_open_mr(
        self,
        owner: str,
        repo: str,
        source_branch: str,
        fork_owner: str = "",
    ) -> dict:
        """查找已存在的 open 状态 MR，返回 {mr_iid, mr_url} 或空 dict"""
        if self.api_style == "v4":
            encoded = urllib.parse.quote(f"{owner}/{repo}", safe="")
            path = f"/projects/{encoded}/merge_requests"
            params = {"state": "opened", "source_branch": source_branch}
        else:
            path = f"/repos/{owner}/{repo}/pulls"
            params = {"state": "open", "head": f"{fork_owner}:{source_branch}"}

        status, resp = await self._request("GET", path, params=params)
        if status != 200:
            return {}

        items = resp if isinstance(resp, list) else resp.get("data", resp.get("items", []))
        for item in items:
            if not isinstance(item, dict):
                continue
            mr_iid = item.get("iid") or item.get("number", "")
            mr_url = item.get("web_url") or item.get("html_url", "")
            if mr_iid:
                return {"mr_iid": mr_iid, "mr_url": mr_url}
        return {}

    async def create_merge_request(
        self,
        owner: str,
        repo: str,
        source_branch: str,
        target_branch: str = "main",
        title: str = "",
        body: str = "",
        fork_owner: str = "",
        fork_repo: str = "",
    ) -> dict:
        """创建 MR/PR，返回 {mr_iid, mr_url} 或 {error}

        跨仓 PR (fork → upstream):
          - v5: head="username:branch", fork_path="fork_owner/fork_repo"
          - v4: source_project_id 需要额外查询（暂不支持跨仓）
        """
        if not title:
            title = f"[Auto] CI/CD Pipeline — {source_branch}"

        is_cross_repo = fork_owner and f"{fork_owner}/{fork_repo}" != f"{owner}/{repo}"

        if self.api_style == "v4":
            encoded = urllib.parse.quote(f"{owner}/{repo}", safe="")
            path = f"/projects/{encoded}/merge_requests"
            req_body = {
                "source_branch": source_branch,
                "target_branch": target_branch,
                "title": title,
            }
            if body:
                req_body["description"] = body
            status, resp = await self._request("POST", path, json_body=req_body)
        else:
            path = f"/repos/{owner}/{repo}/pulls"
            req_body = {
                "title": title,
                "base": target_branch,
            }
            if body:
                req_body["body"] = body
            if is_cross_repo:
                req_body["head"] = f"{fork_owner}:{source_branch}"
                req_body["fork_path"] = f"{fork_owner}/{fork_repo}"
            else:
                req_body["head"] = source_branch
            status, resp = await self._request("POST", path, json_body=req_body)

        if status in (200, 201):
            mr_iid = resp.get("iid") or resp.get("number", "")
            mr_url = resp.get("web_url") or resp.get("html_url", "")
            return {"mr_iid": mr_iid, "mr_url": mr_url}

        error_msg = resp.get("message", resp.get("error_message", str(resp)))
        return {"error": f"创建 MR 失败 ({status}): {error_msg}"}

    async def create_mr_comment(
        self,
        owner: str,
        repo: str,
        mr_iid: int,
        body: str,
    ) -> dict:
        """在 MR 上发表评论"""
        if self.api_style == "v4":
            encoded = urllib.parse.quote(f"{owner}/{repo}", safe="")
            path = f"/projects/{encoded}/merge_requests/{mr_iid}/notes"
            status, resp = await self._request("POST", path, json_body={"body": body})
        else:
            path = f"/repos/{owner}/{repo}/pulls/{mr_iid}/comments"
            status, resp = await self._request("POST", path, json_body={"body": body})

        if status in (200, 201):
            return {"status": "ok"}
        return {"error": f"评论失败 ({status})"}

    async def fetch_mr_comments(
        self,
        owner: str,
        repo: str,
        mr_iid: int,
        since: str = "",
    ) -> List[dict]:
        """获取 MR 评论列表"""
        params = {}
        if since and self.api_style == "v4":
            params["after"] = since

        if self.api_style == "v4":
            encoded = urllib.parse.quote(f"{owner}/{repo}", safe="")
            path = f"/projects/{encoded}/merge_requests/{mr_iid}/notes"
        else:
            path = f"/repos/{owner}/{repo}/pulls/{mr_iid}/comments"

        status, resp = await self._request("GET", path, params=params)

        if status != 200:
            return []

        if isinstance(resp, list):
            comments = resp
        elif isinstance(resp, dict):
            comments = resp.get("data", resp.get("items", []))
        else:
            return []

        result = []
        for note in comments:
            if isinstance(note, dict) and note.get("system", False):
                continue
            body_text = note.get("body", "") or note.get("content", "") or ""
            created = note.get("created_at", "") or note.get("updated_at", "")
            author = note.get("author", {})
            username = author.get("username", "") if isinstance(author, dict) else ""
            is_bot = any(
                p in username.lower()
                for p in ("bot", "ci", "pipeline", "jenkins", "gitlab-bot", "gitcode-bot")
            )
            result.append({
                "id": note.get("id", ""),
                "body": body_text,
                "created_at": created,
                "user": username,
                "is_bot": is_bot,
            })

        return result

    # ==================== 解析 ====================

    def parse_pipeline_result(self, comments: List[dict]) -> dict:
        """从评论中解析流水线结果"""
        stage_results = {}
        error_log = ""
        log_url = ""
        all_passed = False
        all_failed = False

        for comment in comments:
            if not comment.get("is_bot"):
                continue
            body = comment.get("body", "")

            if PIPELINE_PATTERNS["all_passed"].search(body):
                all_passed = True
            if PIPELINE_PATTERNS["all_failed"].search(body):
                all_failed = True

            for match in PIPELINE_PATTERNS["stage_result"].finditer(body):
                icon, stage_name = match.group(1), match.group(2)
                key = STAGE_KEY_MAP.get(stage_name)
                if key:
                    stage_results[key] = "success" if icon == "✅" else "failed"

            for match in PIPELINE_PATTERNS["log_link"].finditer(body):
                link_text, link_url = match.group(1), match.group(2)
                log_url = link_url
                if not error_log or "error" in link_text.lower() or "失败" in link_text:
                    error_log = f"[{link_text}]({link_url})"

        return {
            "passed": all_passed and not all_failed,
            "failed": all_failed,
            "stage_results": stage_results,
            "error_log": error_log,
            "log_url": log_url,
        }

    async def download_log(self, log_url: str) -> str:
        """下载日志内容（简单 HTTP GET）"""
        if not log_url:
            return ""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(log_url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    if resp.status == 200:
                        return await resp.text()
                    return f"下载日志失败 ({resp.status})"
        except Exception as e:
            return f"下载日志异常: {e}"

    # ==================== 流水线操作 ====================

    async def fetch_pr_labels(self, owner: str, repo: str, pr_number) -> list:
        """获取 PR 的 labels 列表"""
        if self.api_style == "v4":
            encoded = urllib.parse.quote(f"{owner}/{repo}", safe="")
            path = f"/projects/{encoded}/merge_requests/{pr_number}"
            status, resp = await self._request("GET", path)
            if status != 200:
                return []
            labels = resp.get("labels", [])
            # v4: labels 可能是字符串列表
            if isinstance(labels, list):
                return [l if isinstance(l, str) else l.get("name", "") for l in labels]
            return []
        else:
            path = f"/repos/{owner}/{repo}/pulls/{pr_number}"
            status, resp = await self._request("GET", path)
            if status != 200:
                return []
            # v5: labels 在 resp.labels 中
            raw_labels = resp.get("labels", [])
            result = []
            for l in raw_labels:
                if isinstance(l, str):
                    result.append(l)
                elif isinstance(l, dict):
                    result.append(l.get("name", l.get("title", "")))
            return result

    async def trigger_pipeline(
        self,
        owner: str,
        repo: str,
        mr_iid: int,
    ) -> str:
        """通过评论 'compile' 触发流水线，返回触发时间 ISO"""
        triggered_at = datetime.now().isoformat()
        result = await self.create_mr_comment(owner, repo, mr_iid, "compile")
        if result.get("error"):
            logger.warning(f"触发流水线评论失败: {result['error']}")
        return triggered_at

    async def poll_pipeline_result(
        self,
        owner: str,
        repo: str,
        mr_iid: int,
        triggered_at: str,
        cancel_check=None,
    ) -> AsyncGenerator[dict, None]:
        """轮询 MR 评论，解析第三方 CI/CD 流水线状态。

        yield 事件不再映射到编排步骤，而是返回原始解析结果：
        - {"type": "ci_detail", "ci_stages": {key: status}, ...}  第三方流水线子阶段细节
        - {"type": "poll_tick", ...}                              轮询进度
        - {"type": "done", "status": "success"/"failed", ...}     最终结果
        - {"type": "timeout", ...}                                超时
        """
        start_time = time.time()

        while True:
            # 检查外部取消请求
            if cancel_check and cancel_check():
                logger.info("[pipeline] 收到取消请求，停止轮询")
                yield {"type": "cancelled"}
                return

            elapsed = time.time() - start_time
            if elapsed > self.poll_timeout:
                yield {"type": "timeout", "elapsed_sec": int(elapsed)}
                return

            # 同时检查评论和 labels
            comments = await self.fetch_mr_comments(owner, repo, mr_iid, since=triggered_at)
            result = self.parse_pipeline_result(comments)

            # 通过 labels 判断流水线最终状态
            labels = await self.fetch_pr_labels(owner, repo, mr_iid)
            label_names = [l.lower() for l in labels]
            label_passed = any("pipeline-pass" in l or "pipeline-passed" in l or "ci-pass" in l or "ci-passed" in l for l in label_names)
            label_failed = any("pipeline-fail" in l or "pipeline-failed" in l or "ci-fail" in l or "ci-failed" in l for l in label_names)
            label_running = any("pipeline-running" in l or "ci-running" in l for l in label_names)
            if label_running:
                logger.debug(f"[pipeline] CI/CD 流水线仍在运行中 (labels: {labels})")

            if result.get("stage_results"):
                yield {
                    "type": "ci_detail",
                    "ci_stages": result["stage_results"],
                    "error_log": result.get("error_log", ""),
                    "log_url": result.get("log_url", ""),
                }

            # 优先用 labels 判断最终状态
            if label_passed:
                logger.info(f"[pipeline] PR labels 检测到流水线通过: {labels}")
                yield {"type": "done", "status": "success", "ci_stages": result.get("stage_results", {})}
                return

            if label_failed:
                logger.info(f"[pipeline] PR labels 检测到流水线失败: {labels}")
                yield {
                    "type": "done", "status": "failed",
                    "ci_stages": result.get("stage_results", {}),
                    "error_log": result.get("error_log", ""),
                    "log_url": result.get("log_url", ""),
                }
                return

            # fallback 到评论解析
            if result["passed"]:
                yield {"type": "done", "status": "success", "ci_stages": result["stage_results"]}
                return

            if result["failed"]:
                yield {
                    "type": "done", "status": "failed",
                    "ci_stages": result["stage_results"],
                    "error_log": result.get("error_log", ""),
                    "log_url": result.get("log_url", ""),
                }
                return

            poll_round = int((time.time() - start_time) / self.poll_interval) + 1
            yield {"type": "poll_tick", "round": poll_round, "elapsed_sec": int(time.time() - start_time)}

            await asyncio.sleep(self.poll_interval)

    # ==================== 辅助方法 ====================

    def _update_step(self, steps: list, key: str, status: str, log: str = None):
        """更新编排步骤状态"""
        for s in steps:
            if s["key"] == key:
                old_status = s.get("status")
                s["status"] = status
                s["log"] = log
                now = datetime.now().isoformat()
                if status == "running" and old_status == "pending":
                    s["started_at"] = now
                if status in ("success", "failed"):
                    s["completed_at"] = now
                break

    def _step_status(self, steps: list, key: str) -> str:
        """获取步骤状态"""
        for s in steps:
            if s["key"] == key:
                return s.get("status", "pending")
        return "pending"

    # ==================== 核心编排 ====================

    async def run_pipeline_lifecycle(
        self,
        work_dir: str,
        owner: str,
        repo: str,
        source_branch: str,
        target_branch: str = "main",
        op_name: str = "",
        op_spec: str = "",
        session_id: str = "",
        git_user: str = "CANNBot",
        git_email: str = "cannbot@auto.dev",
        upstream_owner: str = "",
        upstream_repo: str = "",
        fork_owner: str = "",
        fork_repo: str = "",
        existing_mr_iid: str = "",
        existing_mr_url: str = "",
        cancel_check=None,
    ) -> AsyncGenerator[dict, None]:
        """
        CI/CD 编排生命周期，展示 8 步真实流程。
        existing_mr_iid/url: 如果已有 PR，直接跳到触发编译（复用 PR）。
        """
        steps = _new_steps()

        # 确定各角色
        if upstream_owner and upstream_repo:
            mr_target_owner, mr_target_repo = upstream_owner, upstream_repo
        else:
            mr_target_owner, mr_target_repo = owner, repo

        if fork_owner and fork_repo:
            mr_source_owner, mr_source_repo = fork_owner, fork_repo
        else:
            mr_source_owner, mr_source_repo = owner, repo

        mr_iid = None
        mr_url = None

        # ====== Step 1-3: 提交、推送、创建 PR（或复用已有 PR） ======
        if existing_mr_iid:
            # 复用已有 PR，跳过 commit/push/create
            mr_iid = existing_mr_iid
            mr_url = existing_mr_url
            self._update_step(steps, "git_commit", "success")
            self._update_step(steps, "git_push", "success")
            self._update_step(steps, "create_pr", "success")
            yield {"sse_event": "pipeline_start", "data": {
                "status": "running", "steps": steps,
                "message": f"复用已有 PR: {mr_url}",
                "mr_url": mr_url, "mr_iid": mr_iid,
            }}
        else:
            # ====== Step 1: 提交代码 ======
            self._update_step(steps, "git_commit", "running")
            yield {"sse_event": "pipeline_start", "data": {
                "status": "running", "steps": steps,
                "message": "正在提交代码到本地仓库...",
            }}

            git_ok = await self._git_add_commit_push(work_dir, git_user, git_email)
            if not git_ok:
                self._update_step(steps, "git_commit", "failed", "Git commit 失败")
                yield {"sse_event": "pipeline_done", "data": {
                    "status": "failed", "steps": steps, "completed_at": datetime.now().isoformat(),
                    "error": "Git commit 失败",
                }}
                return

            self._update_step(steps, "git_commit", "success")
            yield {"sse_event": "pipeline_step_update", "data": {
                "step_key": "git_commit", "step": {"status": "success"},
                "steps": steps, "message": "代码已提交到本地仓库",
            }}

            # ====== Step 2: 推送到 Fork 仓库 ======
            self._update_step(steps, "git_push", "running")
            yield {"sse_event": "pipeline_step_update", "data": {
                "step_key": "git_push", "step": {"status": "running"},
                "steps": steps, "message": f"正在推送到 {mr_source_owner}/{mr_source_repo}...",
            }}

            push_ok = await self._git_push(work_dir, source_branch)
            if not push_ok:
                self._update_step(steps, "git_push", "failed", "Git push 失败")
                yield {"sse_event": "pipeline_done", "data": {
                    "status": "failed", "steps": steps, "completed_at": datetime.now().isoformat(),
                    "error": "Git push 失败",
                }}
                return

            self._update_step(steps, "git_push", "success")
            yield {"sse_event": "pipeline_step_update", "data": {
                "step_key": "git_push", "step": {"status": "success"},
                "steps": steps, "message": f"已推送到 {mr_source_owner}/{mr_source_repo}",
            }}

            # ====== Step 3: 向上游创建 PR ======
            self._update_step(steps, "create_pr", "running")
            yield {"sse_event": "pipeline_step_update", "data": {
                "step_key": "create_pr", "step": {"status": "running"},
                "steps": steps,
                "message": f"正在创建 PR: {mr_source_owner}:{source_branch} → {mr_target_owner}/{mr_target_repo}:{target_branch}",
            }}

            # 构造 PR 标题和内容
            pr_title = f"[Auto] 新增算子 {op_name} — {source_branch}" if op_name else f"[Auto] CI/CD Pipeline — {source_branch}"
            pr_body_lines = [
                f"## 算子: {op_name}",
                "",
            ]
            if op_spec:
                pr_body_lines.append(f"### 需求描述")
                pr_body_lines.append(op_spec)
                pr_body_lines.append("")
            pr_body_lines.extend([
                "### 自动化 CI/CD",
                f"- 会话: `{session_id}`",
                f"- 分支: `{source_branch}` → `{target_branch}`",
                f"- 来源: {mr_source_owner}/{mr_source_repo} → {mr_target_owner}/{mr_target_repo}",
                "",
                "---",
                "*此 PR 由 CANNBot 工作流仿真自动创建*",
            ])
            pr_body = "\n".join(pr_body_lines)

            mr_result = await self.create_merge_request(
                mr_target_owner, mr_target_repo,
                source_branch=source_branch,
                target_branch=target_branch,
                title=pr_title,
                body=pr_body,
                fork_owner=mr_source_owner,
                fork_repo=mr_source_repo,
            )
            if mr_result.get("error"):
                self._update_step(steps, "create_pr", "failed", mr_result["error"])
                yield {"sse_event": "pipeline_done", "data": {
                    "status": "failed", "steps": steps, "completed_at": datetime.now().isoformat(),
                    "error": mr_result["error"],
                }}
                return

            mr_iid = mr_result["mr_iid"]
            mr_url = mr_result["mr_url"]
            self._update_step(steps, "create_pr", "success")
            yield {"sse_event": "pipeline_step_update", "data": {
                "step_key": "create_pr", "step": {"status": "success"},
                "steps": steps, "message": f"PR 已创建: {mr_url}",
                "mr_url": mr_url, "mr_iid": mr_iid,
            }}

        # ====== Step 4: 触发编译（评论 compile） ======
        self._update_step(steps, "trigger_ci", "running")
        yield {"sse_event": "pipeline_step_update", "data": {
            "step_key": "trigger_ci", "step": {"status": "running"},
            "steps": steps, "message": "正在评论 compile 触发第三方流水线...",
        }}

        triggered_at = await self.trigger_pipeline(mr_target_owner, mr_target_repo, mr_iid)

        self._update_step(steps, "trigger_ci", "success")
        yield {"sse_event": "pipeline_step_update", "data": {
            "step_key": "trigger_ci", "step": {"status": "success"},
            "steps": steps, "message": "已评论 compile，流水线已触发",
            "mr_url": mr_url, "mr_iid": mr_iid, "triggered_at": triggered_at,
        }}

        # ====== Step 5~8: 轮询 + 修复循环 ======
        fix_round = 0
        while fix_round <= self.max_fix_rounds:
            # --- Step 5: 等待 CI/CD 结果 ---
            self._update_step(steps, "wait_ci", "running")
            yield {"sse_event": "pipeline_step_update", "data": {
                "step_key": "wait_ci", "step": {"status": "running"},
                "steps": steps, "message": "等待第三方流水线运行...",
            }}

            ci_result = None
            async for event in self.poll_pipeline_result(
                mr_target_owner, mr_target_repo, mr_iid, triggered_at,
                cancel_check=cancel_check,
            ):
                if event["type"] == "cancelled":
                    self._update_step(steps, "wait_ci", "failed", "用户手动取消")
                    yield {"sse_event": "pipeline_done", "data": {
                        "status": "cancelled", "steps": steps,
                        "completed_at": datetime.now().isoformat(),
                        "error": "流水线已被用户手动取消",
                    }}
                    return

                if event["type"] == "ci_detail":
                    ci_names = []
                    for k, v in event.get("ci_stages", {}).items():
                        cn = next((cn for cn, ck in STAGE_KEY_MAP.items() if ck == k), k)
                        ci_names.append(f"{cn}={v}")
                    yield {"sse_event": "pipeline_step_update", "data": {
                        "step_key": "wait_ci", "step": {"status": "running"},
                        "steps": steps,
                        "message": f"检测到流水线进展: {', '.join(ci_names)}",
                        "ci_stages": event.get("ci_stages", {}),
                    }}

                elif event["type"] == "timeout":
                    self._update_step(steps, "wait_ci", "failed", f"轮询超时 ({self.poll_timeout}s)")
                    yield {"sse_event": "pipeline_done", "data": {
                        "status": "timeout", "steps": steps,
                        "completed_at": datetime.now().isoformat(),
                        "error": f"流水线轮询超时 ({self.poll_timeout}s)",
                    }}
                    return

                elif event["type"] == "poll_tick":
                    yield {"sse_event": "pipeline_step_update", "data": {
                        "step_key": "wait_ci", "step": {"status": "running"},
                        "steps": steps,
                        "message": f"等待流水线结果... (第 {event['round']} 次轮询, 已等待 {event['elapsed_sec']}s)",
                    }}

                elif event["type"] == "done":
                    ci_result = event

            if not ci_result:
                self._update_step(steps, "wait_ci", "failed", "未获取到流水线结果")
                yield {"sse_event": "pipeline_done", "data": {
                    "status": "failed", "steps": steps,
                    "completed_at": datetime.now().isoformat(),
                    "error": "未获取到流水线结果",
                }}
                return

            # CI 通过
            if ci_result["status"] == "success":
                ci_names = []
                for k, v in ci_result.get("ci_stages", {}).items():
                    cn = next((cn for cn, ck in STAGE_KEY_MAP.items() if ck == k), k)
                    ci_names.append(f"{cn}={v}")
                self._update_step(steps, "wait_ci", "success")
                yield {"sse_event": "pipeline_step_update", "data": {
                    "step_key": "wait_ci", "step": {"status": "success"},
                    "steps": steps, "message": f"流水线全部通过: {', '.join(ci_names)}",
                    "ci_stages": ci_result.get("ci_stages", {}),
                }}
                yield {"sse_event": "pipeline_done", "data": {
                    "status": "success", "steps": steps,
                    "completed_at": datetime.now().isoformat(),
                    "fix_rounds": fix_round,
                    "mr_url": mr_url,
                }}
                return

            # CI 失败 → 进入修复循环
            error_log = ci_result.get("error_log", "")
            log_url = ci_result.get("log_url", "")
            failed_ci = [k for k, v in ci_result.get("ci_stages", {}).items() if v == "failed"]
            failed_ci_names = [
                next((cn for cn, ck in STAGE_KEY_MAP.items() if ck == k), k)
                for k in failed_ci
            ] or ["未知阶段"]

            self._update_step(steps, "wait_ci", "failed", f"失败阶段: {', '.join(failed_ci_names)}")
            yield {"sse_event": "pipeline_step_update", "data": {
                "step_key": "wait_ci", "step": {"status": "failed"},
                "steps": steps,
                "message": f"流水线失败: {', '.join(failed_ci_names)}",
                "ci_stages": ci_result.get("ci_stages", {}),
            }}

            # --- Step 6: 分析失败原因 ---
            self._update_step(steps, "analyze_failure", "running")
            yield {"sse_event": "pipeline_step_update", "data": {
                "step_key": "analyze_failure", "step": {"status": "running"},
                "steps": steps, "message": "正在提取并分析错误日志...",
            }}

            full_log = error_log
            if log_url:
                downloaded = await self.download_log(log_url)
                if downloaded and not downloaded.startswith("下载"):
                    full_log = downloaded

            analysis = f"失败阶段: {', '.join(failed_ci_names)}"
            if full_log:
                # 取最后 500 字符作为摘要
                analysis += f"\n日志摘要: ...{full_log[-500:]}"

            self._update_step(steps, "analyze_failure", "success", analysis)
            yield {"sse_event": "pipeline_step_update", "data": {
                "step_key": "analyze_failure", "step": {"status": "success"},
                "steps": steps,
                "message": f"失败原因已定位: {', '.join(failed_ci_names)}",
            }}

            # 检查修复轮次上限
            if fix_round >= self.max_fix_rounds:
                self._update_step(steps, "auto_fix", "failed", f"已达最大修复轮次 ({self.max_fix_rounds})")
                yield {"sse_event": "pipeline_done", "data": {
                    "status": "failed", "steps": steps,
                    "completed_at": datetime.now().isoformat(),
                    "fix_rounds": fix_round,
                    "error": f"已达最大修复轮次 ({self.max_fix_rounds})",
                    "mr_url": mr_url,
                }}
                return

            fix_round += 1

            # --- Step 7: 自动修复 ---
            self._update_step(steps, "auto_fix", "running")
            yield {"sse_event": "pipeline_step_update", "data": {
                "step_key": "auto_fix", "step": {"status": "running"},
                "steps": steps,
                "message": f"第 {fix_round} 次自动修复中...",
            }}

            yield {"sse_event": "pipeline_fix_round", "data": {
                "round_number": fix_round,
                "error_type": "pipeline_failed",
                "error_log": full_log[:500] if full_log else "",
                "failed_stages": failed_ci,
            }}

            fix_ok = await self._auto_fix(
                work_dir, op_name, ", ".join(failed_ci_names), full_log, fix_round, session_id,
            )

            if not fix_ok:
                self._update_step(steps, "auto_fix", "failed", "自动修复未产出有效结果")
                yield {"sse_event": "pipeline_step_update", "data": {
                    "step_key": "auto_fix", "step": {"status": "failed"},
                    "steps": steps, "message": "自动修复未产出有效结果，继续下一轮尝试",
                }}
                # 重置 wait_ci 和 analyze 以便下一轮重用
                self._update_step(steps, "wait_ci", "pending")
                self._update_step(steps, "analyze_failure", "pending")
                self._update_step(steps, "auto_fix", "pending")
                continue

            self._update_step(steps, "auto_fix", "success")
            yield {"sse_event": "pipeline_step_update", "data": {
                "step_key": "auto_fix", "step": {"status": "success"},
                "steps": steps, "message": f"第 {fix_round} 次修复完成",
            }}

            # --- Step 8: 提交修复并重试 ---
            self._update_step(steps, "fix_commit_retry", "running")
            yield {"sse_event": "pipeline_step_update", "data": {
                "step_key": "fix_commit_retry", "step": {"status": "running"},
                "steps": steps,
                "message": f"提交修复代码并重新触发流水线 (第 {fix_round} 次)...",
            }}

            await self._git_add_commit_push(work_dir, git_user, git_email, suffix=f"[fix #{fix_round}]")
            push_ok2 = await self._git_push(work_dir, source_branch)
            if not push_ok2:
                self._update_step(steps, "fix_commit_retry", "failed", "修复后 push 失败")
                yield {"sse_event": "pipeline_done", "data": {
                    "status": "failed", "steps": steps,
                    "completed_at": datetime.now().isoformat(),
                    "error": "修复后 push 失败",
                }}
                return

            triggered_at = await self.trigger_pipeline(mr_target_owner, mr_target_repo, mr_iid)

            self._update_step(steps, "fix_commit_retry", "success")
            yield {"sse_event": "pipeline_step_update", "data": {
                "step_key": "fix_commit_retry", "step": {"status": "success"},
                "steps": steps,
                "message": f"修复代码已提交并重新触发流水线 (第 {fix_round} 次)",
            }}

            # 重置步骤 5~8 为 pending，进入下一轮
            self._update_step(steps, "wait_ci", "pending")
            self._update_step(steps, "analyze_failure", "pending")
            self._update_step(steps, "auto_fix", "pending")
            self._update_step(steps, "fix_commit_retry", "pending")

    async def _git_add_commit_push(
        self,
        work_dir: str,
        git_user: str,
        git_email: str,
        suffix: str = "",
    ) -> bool:
        """git add + commit（仅在有变更时提交）"""
        try:
            # 先检查是否有未暂存的变更
            proc = await asyncio.create_subprocess_exec(
                "git", "status", "--porcelain",
                cwd=work_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=30)
            has_changes = bool(stdout.decode("utf-8", errors="replace").strip())

            if not has_changes:
                logger.info("[pipeline] 没有代码变更，跳过 commit")
                return True

            # git add
            proc = await asyncio.create_subprocess_exec(
                "git", "add", "-A",
                cwd=work_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(proc.wait(), timeout=60)

            # git commit（不用 --allow-empty）
            msg = f"auto: CANNBot pipeline commit{suffix}"
            proc = await asyncio.create_subprocess_exec(
                "git", "-c", f"user.name={git_user}", "-c", f"user.email={git_email}",
                "commit", "-m", msg,
                cwd=work_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
            if proc.returncode != 0:
                err_text = stderr.decode("utf-8", errors="replace")
                if "nothing to commit" in err_text:
                    return True
                logger.warning(f"git commit 失败: {err_text}")
            return True
        except Exception as e:
            logger.error(f"git add/commit 异常: {e}")
            return False

    async def _git_push(self, work_dir: str, branch: str) -> bool:
        """git push — 使用 token 认证推送到 fork 仓库"""
        try:
            # 获取当前 origin URL
            proc = await asyncio.create_subprocess_exec(
                "git", "remote", "get-url", "origin",
                cwd=work_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
            origin_url = stdout.decode("utf-8", errors="replace").strip()

            if not origin_url:
                logger.error("无法获取 origin URL")
                return False

            # 在 URL 中嵌入 token 用于认证
            # https://gitcode.com/owner/repo.git → https://oauth2:{token}@gitcode.com/owner/repo.git
            auth_url = origin_url
            if self.token and "@" not in origin_url:
                if "gitcode.com" in origin_url:
                    auth_url = origin_url.replace("https://", f"https://oauth2:{self.token}@")
                elif "atomgit.com" in origin_url:
                    auth_url = origin_url.replace("https://", f"https://oauth2:{self.token}@")

            proc = await asyncio.create_subprocess_exec(
                "git", "push", auth_url, branch,
                cwd=work_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
            if proc.returncode != 0:
                err_text = stderr.decode("utf-8", errors="replace")
                logger.warning(f"git push 失败: {err_text}")
                return False
            return True
        except Exception as e:
            logger.error(f"git push 异常: {e}")
            return False

    async def _auto_fix(
        self,
        work_dir: str,
        op_name: str,
        failed_stage: str,
        error_log: str,
        round_number: int,
        session_id: str,
    ) -> bool:
        """调用 Claude Code CLI 自动修复"""
        prompt = (
            f"CI/CD 流水线失败 — {failed_stage} 阶段\n\n"
            f"错误日志:\n{error_log[:8000]}\n\n"
            f"请修复当前工作目录中与算子 {op_name} 相关的代码。"
            f"这是第 {round_number} 次修复（最多 {self.max_fix_rounds} 次）。\n"
            f"只需修复导致失败的问题，不要改动无关代码。"
        )

        try:
            got_result = False
            async for ev in claude_driver.run_step(
                session_id=f"{session_id}_fix_{round_number}",
                prompt=prompt,
                work_dir=work_dir,
                timeout=600,
                step_id=f"pipeline_fix_{round_number}",
            ):
                if ev["type"] == "result":
                    got_result = True
            return got_result
        except Exception as e:
            logger.error(f"自动修复异常: {e}")
            return False
