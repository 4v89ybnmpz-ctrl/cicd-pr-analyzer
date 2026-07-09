"""工作流仿真 V2 路由 — register_repo_routes（由 workflow_sim_v2.py 拆分）"""

import asyncio
import json
import logging
import os
import re
import secrets
from datetime import datetime

import aiohttp

from fastapi import APIRouter, BackgroundTasks

from app.config.config_manager import config_manager
from .workflow_sim_v2_helpers import (
    run_git as _run_git,
)

logger = logging.getLogger(__name__)


def _ts():
    return datetime.now().strftime("%H:%M:%S")


def _get_evaluations_base() -> str:
    """从 config 读取评估隔离根目录"""
    try:
        return (config_manager.get("workflow_v2", {}) or {}).get(
            "evaluations_base_dir", ""
        ).strip()
    except Exception:
        return ""


def _parse_repo_name(repo_url: str) -> str:
    """从 repo_url 解析算子库名（最后一段，如 https://xxx/cann/ops-math → ops-math）"""
    m = re.search(r"[:/]([^/]+?)(?:\.git)?$", repo_url)
    return (m.group(1) if m else "repo").replace("/", "_")


def _gen_eval_identity(root: str, op_name: str):
    """生成派生目录 <root>/evaluations/<时间戳>_<算子>_<rand> + 评估分支名（rand 对齐）"""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    rand = secrets.token_hex(3)
    safe_op = re.sub(r"[^a-zA-Z0-9_-]", "", op_name or "")[:20]
    op_part = safe_op if safe_op else "eval"
    dir_path = os.path.join(root, "evaluations", f"{ts}_{op_part}_{rand}")
    branch = f"eval/{op_part}-{rand}"
    return dir_path, branch


async def _ensure_base_repo(repo_url: str, root: str):
    """确保母本 <root>/<算子库名>/ 存在（保留算子库名层，幂等复用）。返回路径或 {"error":...}"""
    import time as _time
    base = os.path.join(root, _parse_repo_name(repo_url))
    if os.path.isdir(os.path.join(base, ".git")):
        logger.info(f"[base] 复用已存在母本: {base}")
        return base
    os.makedirs(root, exist_ok=True)
    logger.info(f"[base] 首次克隆母本: {repo_url} → {base}（大算子库可能耗时数分钟）")
    _t0 = _time.time()
    result = await _run_git("clone", repo_url, base)
    logger.info(f"[base] 克隆结束，耗时 {_time.time() - _t0:.1f}s, rc={result['returncode']}")
    if result["returncode"] != 0:
        return {"error": f"建立母本失败: {result['stderr']}"}
    return base


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
        is_clean = True
        modified_count = 0
        if is_git:
            result = await _run_git(
                "rev-parse", "--abbrev-ref", "HEAD", cwd=target_path
            )
            if result["returncode"] == 0:
                branch = result["stdout"].strip()
            # 工作区改动检测（含未跟踪文件）：判断派生工作区是"全新"还是"已动过"
            st = await _run_git("status", "--porcelain", cwd=target_path)
            if st["returncode"] == 0:
                modified_count = sum(1 for l in st["stdout"].splitlines() if l.strip())
            is_clean = modified_count == 0
        return {
            "exists": exists,
            "is_git": is_git,
            "branch": branch,
            "path": target_path,
            "is_clean": is_clean,
            "modified_count": modified_count,
        }

    @router.post("/cannbot/workflow-v2/clone-repo")
    async def clone_repo(request: dict):
        """Clone 算子库到工作区（根目录下 <算子库名>/ 母本 + evaluations/ 派生）

        工作目录（target_dir）= 根目录，结构：
          <根>/<算子库名>/          ← 母本（clone repo_url，保留算子库名层）
          <根>/evaluations/<隔离>/  ← 本次评估派生工作区（--shared，秒级）
        target_dir 空 → 根 = config.evaluations_base_dir
        target_dir 本身已是 git 仓库 → 直接当 work_dir 返回（兼容老用法）
        """
        repo_url = request.get("repo_url", "").strip()
        target_dir = request.get("target_dir", "").strip()
        op_name = request.get("op_name", "").strip()
        if not repo_url:
            return {"error": "请输入算子库地址"}

        # 根目录：target_dir 优先，否则 config 默认
        root = os.path.abspath(target_dir) if target_dir else _get_evaluations_base()
        if not root:
            return {"error": "请填写工作目录（根），或配置 evaluations_base_dir"}
        os.makedirs(root, exist_ok=True)

        # 兼容：根本身已是 git 仓库 → 直接当 work_dir
        if os.path.isdir(os.path.join(root, ".git")):
            br = await _run_git("rev-parse", "--abbrev-ref", "HEAD", cwd=root)
            return {
                "status": "already_exists",
                "path": root,
                "branch": br["stdout"].strip() if br["returncode"] == 0 else None,
            }

        # 1. 母本 <根>/<算子库名>/（幂等复用）
        base = await _ensure_base_repo(repo_url, root)
        if isinstance(base, dict):
            return base  # 含 error

        # 2. 派生 <根>/evaluations/<隔离> + 评估分支（--shared，秒级）
        work_dir, eval_branch = _gen_eval_identity(root, op_name)
        result = await _run_git("clone", "--shared", base, work_dir)
        if result["returncode"] != 0:
            return {"error": f"派生 clone 失败: {result['stderr']}"}

        # 3. origin 指回真实远程（--shared 默认 origin=母本本地路径；改为 repo_url 便于 push 到 fork）
        await _run_git("remote", "set-url", "origin", repo_url, cwd=work_dir)

        # 4. 自动建评估分支（与目录共用 rand，命名对齐）
        co = await _run_git("checkout", "-b", eval_branch, cwd=work_dir)
        if co["returncode"] == 0:
            final_branch, auto_branch = eval_branch, True
        else:
            fb = await _run_git("rev-parse", "--abbrev-ref", "HEAD", cwd=work_dir)
            final_branch = fb["stdout"].strip() if fb["returncode"] == 0 else None
            auto_branch = False

        return {
            "status": "cloned",
            "path": work_dir,
            "branch": final_branch,
            "base_repo": base,
            "root": root,
            "isolated": True,
            "auto_branch": auto_branch,
        }

    @router.get("/cannbot/workflow-v2/check-base")
    async def check_base(repo_url: str = "", target_dir: str = ""):
        """检查母本 <根>/<算子库名>/ 是否就绪（前端据此显示 Clone 或派生按钮）"""
        repo_url = (repo_url or "").strip()
        root = (target_dir or "").strip() or _get_evaluations_base()
        if not repo_url or not root:
            return {"base_ready": False}
        base = os.path.join(os.path.abspath(root), _parse_repo_name(repo_url))
        ready = os.path.isdir(os.path.join(base, ".git"))
        return {"base_ready": ready, "base_repo": base if ready else None}

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

