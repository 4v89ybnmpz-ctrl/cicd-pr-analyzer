"""工作流仿真 V2 路由 — register_repo_routes（由 workflow_sim_v2.py 拆分）"""

import asyncio
import json
import logging
import os
import re
from datetime import datetime

import aiohttp

from fastapi import APIRouter, BackgroundTasks


from .workflow_sim_v2_helpers import (
    run_git as _run_git,
)

logger = logging.getLogger(__name__)


def _ts():
    return datetime.now().strftime("%H:%M:%S")


def register_repo_routes(router: APIRouter, db=None):
    @router.post("/cannbot/workflow-v2/fork-repo")
    async def fork_repo(request: dict):
        """通过 GitCode API fork 仓库到用户账号（已 fork 则直接返回）"""
        repo_url = request.get("repo_url", "").strip()
        token = request.get("token", "").strip()
        if not repo_url:
            return {"error": "请输入仓库地址"}
        if not token:
            return {"error": "请输入 GitCode Token"}

        match = re.search(r"[:/]([^/]+/[^/]+?)(?:\.git)?$", repo_url)
        if not match:
            return {
                "error": "无法解析仓库地址，请使用 https://gitcode.com/{owner}/{repo}.git 格式"
            }
        owner_repo = match.group(1)
        owner, repo = owner_repo.split("/", 1)

        return await _do_fork_or_check(
            repo_url, token, owner, repo, fork_if_missing=True
        )

    @router.get("/cannbot/workflow-v2/check-fork")
    async def check_fork(repo_url: str = "", token: str = ""):
        """检测仓库是否已被当前用户 fork"""
        repo_url = repo_url.strip()
        token = token.strip()
        if not repo_url or not token:
            return {"forked": False}

        match = re.search(r"[:/]([^/]+/[^/]+?)(?:\.git)?$", repo_url)
        if not match:
            return {"forked": False}
        owner_repo = match.group(1)
        owner, repo = owner_repo.split("/", 1)

        return await _do_fork_or_check(
            repo_url, token, owner, repo, fork_if_missing=False
        )

    async def _do_fork_or_check(
        repo_url: str,
        token: str,
        owner: str,
        repo: str,
        fork_if_missing: bool,
    ) -> dict:
        """检测/执行 fork 的共用逻辑"""

        try:
            async with aiohttp.ClientSession() as session:
                # Step 1: 先查用户是否已有同名仓库（即已 fork）
                user_repos_url = "https://api.gitcode.com/api/v5/user/repos"
                async with session.get(
                    user_repos_url,
                    params={"access_token": token, "repo_name": repo, "per_page": 100},
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as check_resp:
                    if check_resp.status == 200:
                        user_repos = await check_resp.json()
                        if isinstance(user_repos, list):
                            for ur in user_repos:
                                if ur.get("name") == repo and ur.get("fork"):
                                    fork_path = ur.get("full_name", "") or ur.get(
                                        "path_with_namespace", ""
                                    )
                                    fork_https = (
                                        ur.get("https_url_to_repo", "")
                                        or ur.get("ssh_url", "")
                                        or (
                                            f"https://gitcode.com/{fork_path}.git"
                                            if fork_path
                                            else ""
                                        )
                                    )
                                    result = {
                                        "fork_url": fork_https,
                                        "fork_ssh": ur.get("ssh_url_to_repo", ""),
                                        "fork_path": fork_path,
                                    }
                                    if fork_if_missing:
                                        result["status"] = "already_forked"
                                        result["message"] = "仓库已 fork 到您的账号"
                                    else:
                                        result["forked"] = True
                                    return result

                # Step 2: 不存在则调 fork API（仅 fork_if_missing=True 时）
                if not fork_if_missing:
                    return {"forked": False}

                fork_api_url = (
                    f"https://api.gitcode.com/api/v5/repos/{owner}/{repo}/forks"
                )
                async with session.post(
                    fork_api_url,
                    params={"access_token": token},
                    timeout=aiohttp.ClientTimeout(total=60),
                ) as resp:
                    body = await resp.json()

                    if resp.status in (200, 201):
                        fork_path = body.get("full_name", "") or body.get(
                            "path_with_namespace", ""
                        )
                        fork_https = body.get("https_url_to_repo", "") or (
                            f"https://gitcode.com/{fork_path}.git" if fork_path else ""
                        )
                        fork_ssh = body.get("ssh_url_to_repo", "")
                        return {
                            "status": "forked",
                            "fork_url": fork_https,
                            "fork_ssh": fork_ssh,
                            "fork_path": fork_path,
                        }

                    # 处理各种"已存在"情况
                    if resp.status in (409, 422):
                        body_str = (
                            json.dumps(body, ensure_ascii=False)
                            if isinstance(body, dict)
                            else str(body)
                        )
                        exist_keywords = [
                            "已经存在",
                            "already exist",
                            "already been forked",
                            "duplicate",
                        ]
                        if any(
                            kw in body_str.lower() or kw in body_str
                            for kw in exist_keywords
                        ):
                            # 尝试再次查找
                            async with session.get(
                                user_repos_url,
                                params={
                                    "access_token": token,
                                    "repo_name": repo,
                                    "per_page": 100,
                                },
                                timeout=aiohttp.ClientTimeout(total=30),
                            ) as retry_check:
                                if retry_check.status == 200:
                                    retry_repos = await retry_check.json()
                                    if isinstance(retry_repos, list):
                                        for ur in retry_repos:
                                            if ur.get("name") == repo:
                                                fp = ur.get("full_name", "") or ur.get(
                                                    "path_with_namespace", ""
                                                )
                                                return {
                                                    "status": "already_forked",
                                                    "fork_url": ur.get(
                                                        "https_url_to_repo", ""
                                                    )
                                                    or ur.get("ssh_url", "")
                                                    or (
                                                        f"https://gitcode.com/{fp}.git"
                                                        if fp
                                                        else ""
                                                    ),
                                                    "fork_ssh": ur.get(
                                                        "ssh_url_to_repo", ""
                                                    ),
                                                    "fork_path": fp,
                                                    "message": "仓库已 fork 到您的账号",
                                                }
                            return {
                                "error": "仓库可能已 fork，但无法获取 fork 地址，请在 GitCode 上手动查看"
                            }

                    error_msg = (
                        body.get("message", body.get("error_message", ""))
                        if isinstance(body, dict)
                        else str(body)
                    )
                    return {"error": f"Fork 失败 ({resp.status}): {error_msg}"}

        except asyncio.TimeoutError:
            return {"error": "Fork 请求超时，请稍后重试"}
        except Exception as e:
            return {"error": f"Fork 请求失败: {e}"}

    @router.get("/cannbot/workflow-v2/check-repo")
    async def check_repo(target_dir: str = ""):
        """检查目录是否已存在且是 git 仓库"""
        if not target_dir:
            return {"exists": False, "is_git": False}
        target_path = os.path.abspath(target_dir)
        exists = os.path.isdir(target_path)
        is_git = os.path.isdir(os.path.join(target_path, ".git")) if exists else False
        branch = None
        if is_git:
            result = await _run_git(
                "rev-parse", "--abbrev-ref", "HEAD", cwd=target_path
            )
            if result["returncode"] == 0:
                branch = result["stdout"]
        return {
            "exists": exists,
            "is_git": is_git,
            "branch": branch,
            "path": target_path,
        }

    @router.post("/cannbot/workflow-v2/clone-repo")
    async def clone_repo(request: dict):
        """Clone 算子库到指定工作目录"""
        repo_url = request.get("repo_url", "").strip()
        target_dir = request.get("target_dir", "").strip()
        if not repo_url:
            return {"error": "请输入算子库地址"}
        if not target_dir:
            return {"error": "请输入工作目录"}

        target_path = os.path.abspath(target_dir)

        # 检查是否已存在
        if os.path.isdir(target_path) and os.path.isdir(
            os.path.join(target_path, ".git")
        ):
            branch_result = await _run_git(
                "rev-parse", "--abbrev-ref", "HEAD", cwd=target_path
            )
            return {
                "status": "already_exists",
                "path": target_path,
                "branch": branch_result["stdout"]
                if branch_result["returncode"] == 0
                else None,
            }

        # 如果目录已存在但不是 git 仓库，报错
        if os.path.isdir(target_path):
            return {"error": f"目录已存在但不是 git 仓库: {target_path}"}

        # 执行 clone
        os.makedirs(os.path.dirname(target_path) or ".", exist_ok=True)
        result = await _run_git("clone", repo_url, target_path)
        if result["returncode"] != 0:
            return {"error": f"Clone 失败: {result['stderr']}"}

        return {"status": "cloned", "path": target_path}

    @router.get("/cannbot/workflow-v2/list-branches")
    async def list_branches(work_dir: str = ""):
        """列出本地仓库的所有分支（本地 + 远程）"""
        if not work_dir:
            return {"error": "请提供工作目录"}
        work_path = os.path.abspath(work_dir)
        if not os.path.isdir(os.path.join(work_path, ".git")):
            return {"error": "目录不是 git 仓库"}

        # 获取当前分支
        cur = await _run_git("rev-parse", "--abbrev-ref", "HEAD", cwd=work_path)
        current_branch = cur["stdout"] if cur["returncode"] == 0 else ""

        # 列出所有分支（本地 + 远程）
        br = await _run_git("branch", "-a", "--format=%(refname:short)", cwd=work_path)
        if br["returncode"] != 0:
            return {"error": f"获取分支失败: {br['stderr']}"}

        branches = []
        remote_prefix = "origin/"
        for line in br["stdout"].splitlines():
            line = line.strip()
            if not line:
                continue
            is_remote = line.startswith(remote_prefix)
            name = line[len(remote_prefix) :] if is_remote else line
            # 去重：同名分支优先保留本地
            if name not in [b["name"] for b in branches]:
                branches.append(
                    {
                        "name": name,
                        "is_remote": is_remote,
                        "is_current": name == current_branch,
                    }
                )

        # 当前分支置顶
        branches.sort(key=lambda b: (not b["is_current"], b["is_remote"], b["name"]))
        return {"current_branch": current_branch, "branches": branches}

    @router.post("/cannbot/workflow-v2/create-branch")
    async def create_branch(request: dict):
        """在本地仓库创建新分支并切换到该分支（基于指定的 base 分支）"""
        work_dir = request.get("work_dir", "").strip()
        branch_name = request.get("branch_name", "").strip()
        base_branch = request.get("base_branch", "").strip()  # 可选，默认自动检测主分支
        if not work_dir:
            return {"error": "请提供工作目录"}
        if not branch_name:
            return {"error": "请输入分支名称"}
        work_path = os.path.abspath(work_dir)
        if not os.path.isdir(os.path.join(work_path, ".git")):
            return {"error": "目录不是 git 仓库"}

        # 检查分支是否已存在
        check = await _run_git("branch", "--list", branch_name, cwd=work_path)
        if check["returncode"] == 0 and check["stdout"].strip():
            sw = await _run_git("checkout", branch_name, cwd=work_path)
            if sw["returncode"] != 0:
                return {"error": f"切换分支失败: {sw['stderr']}"}
            return {
                "status": "switched",
                "branch": branch_name,
                "message": f"已切换到分支 {branch_name}",
            }

        # 确定 base 分支：优先用户指定，否则自动找 origin/main 或 origin/master
        if not base_branch:
            # 先 fetch 确保远程引用最新
            await _run_git("fetch", "origin", cwd=work_path)
            for candidate in ("origin/main", "origin/master"):
                r = await _run_git("rev-parse", "--verify", candidate, cwd=work_path)
                if r["returncode"] == 0:
                    base_branch = candidate
                    break
            if not base_branch:
                # 回退到当前 HEAD
                base_branch = "HEAD"

        # 基于指定起点创建新分支
        result = await _run_git(
            "checkout", "-b", branch_name, base_branch, cwd=work_path
        )
        if result["returncode"] != 0:
            return {"error": f"创建分支失败: {result['stderr']}"}
        return {
            "status": "created",
            "branch": branch_name,
            "base": base_branch,
            "message": f"已基于 {base_branch} 创建并切换到分支 {branch_name}",
        }

    @router.post("/cannbot/workflow-v2/switch-branch")
    async def switch_branch(request: dict):
        """切换到指定分支"""
        work_dir = request.get("work_dir", "").strip()
        branch_name = request.get("branch_name", "").strip()
        if not work_dir:
            return {"error": "请提供工作目录"}
        if not branch_name:
            return {"error": "请输入分支名称"}
        work_path = os.path.abspath(work_dir)
        if not os.path.isdir(os.path.join(work_path, ".git")):
            return {"error": "目录不是 git 仓库"}

        # 如果是远程分支，先创建本地跟踪分支
        remote_branch = f"origin/{branch_name}"
        check_remote = await _run_git(
            "rev-parse", "--verify", remote_branch, cwd=work_path
        )
        check_local = await _run_git(
            "rev-parse", "--verify", branch_name, cwd=work_path
        )

        if check_remote["returncode"] == 0 and check_local["returncode"] != 0:
            # 远程分支存在但本地没有，创建跟踪分支
            result = await _run_git(
                "checkout", "-b", branch_name, "--track", remote_branch, cwd=work_path
            )
        else:
            result = await _run_git("checkout", branch_name, cwd=work_path)

        if result["returncode"] != 0:
            return {"error": f"切换分支失败: {result['stderr']}"}
        return {
            "status": "switched",
            "branch": branch_name,
            "message": f"已切换到分支 {branch_name}",
        }

