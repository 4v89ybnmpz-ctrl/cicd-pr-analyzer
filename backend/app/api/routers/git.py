"""
Git 仓库接口路由
"""
from fastapi import HTTPException
from datetime import datetime
import asyncio
import os
import logging

from app.core.task_queue import task_queue

logger = logging.getLogger(__name__)


def _repo_path_static(owner: str, repo: str) -> str:
    """构造 bare 仓库路径"""
    from app.services.git_service import REPOS_DIR
    return os.path.join(REPOS_DIR, owner, f"{repo}.git")

# 模块级代理配置
_proxy = None


def register_git_routes(router, db, github_service=None, config=None):
    """注册 Git 仓库相关路由"""
    global _proxy

    # 代理配置：优先 config.json 的 proxy 字段，其次环境变量 HTTPS_PROXY
    _proxy = None
    if config and isinstance(config, dict):
        _proxy = config.get("proxy")
    if not _proxy:
        import os
        _proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")

    @router.get("/git/projects")
    async def list_git_projects():
        """获取已有 git log 数据的项目列表（用于自动补全）"""
        if db is None:
            raise HTTPException(status_code=503, detail="数据库未连接")
        try:
            pipeline = [
                {"$group": {"_id": {"owner": "$owner", "repo": "$repo"}, "commit_count": {"$sum": 1}}},
                {"$project": {"_id": 0, "owner": "$_id.owner", "repo": "$_id.repo", "commit_count": 1}},
                {"$sort": {"commit_count": -1}},
            ]
            cursor = db.db['git_log_commits'].aggregate(pipeline)
            projects = []
            async for doc in cursor:
                projects.append(doc)
            return {"projects": projects}
        except Exception as e:
            logger.error(f"获取 git 项目列表失败: {e}")
            return {"projects": []}

    @router.get("/git/repos/{owner}/{repo}/status")
    async def get_repo_status(owner: str, repo: str):
        """获取仓库克隆状态"""
        from app.services.git_service import GitRepoService
        gs = _get_git_service(github_service)
        return {
            "cloned": gs.is_cloned(owner, repo),
            "size_mb": gs.get_repo_size_mb(owner, repo),
            "owner": owner, "repo": repo,
        }

    @router.get("/git/repos/{owner}/{repo}/log/summary")
    async def get_git_log_summary(owner: str, repo: str):
        """获取已提取的 git log 摘要"""
        if db is None:
            raise HTTPException(status_code=503, detail="数据库未连接")
        summary = await db.get_git_log_summary(owner, repo)
        if not summary:
            raise HTTPException(status_code=404, detail="尚未提取 git log 数据")
        return {"summary": summary, "timestamp": datetime.now().isoformat()}

    @router.get("/git/repos/{owner}/{repo}/branches")
    async def get_repo_branches(owner: str, repo: str):
        """获取仓库的分支列表（优先从数据库摘要读取，否则从本地 bare 仓库读取）"""
        branches = []
        # 先从已保存的摘要中获取
        if db is not None:
            summary = await db.get_git_log_summary(owner, repo)
            if summary and summary.get("branches"):
                branches = summary["branches"]
        # 如果摘要中没有，从本地 bare 仓库获取
        if not branches:
            from app.services.git_service import GitRepoService
            gs = _get_git_service(github_service)
            if gs.is_cloned(owner, repo):
                import asyncio as _aio
                dest = os.path.join(gs.repos_dir if hasattr(gs, 'repos_dir') else "",
                                     owner, f"{repo}.git")
                dest = _repo_path_static(owner, repo)
                proc = await _aio.create_subprocess_exec(
                    "git", "branch", "-r", "--format=%(refname:short)",
                    stdout=_aio.subprocess.PIPE,
                    stderr=_aio.subprocess.PIPE,
                    cwd=dest,
                )
                out, _ = await proc.communicate()
                branches = [b.strip() for b in out.decode("utf-8", errors="replace").splitlines() if b.strip()]
        return {"branches": branches, "count": len(branches)}

    @router.get("/git/repos/{owner}/{repo}/log/commits")
    async def list_git_log_commits(owner: str, repo: str, author: str = None,
                                    branch: str = None,
                                    page: int = 1, size: int = 20,
                                    sort_by: str = "author_date", sort_order: str = "desc"):
        """查询 git log 提交记录"""
        if db is None:
            raise HTTPException(status_code=503, detail="数据库未连接")
        sort_order_int = -1 if sort_order == "desc" else 1
        result = await db.list_git_log_commits(owner, repo, author, branch, page, size, sort_by, sort_order_int)
        return {**result, "timestamp": datetime.now().isoformat()}

    @router.post("/git/tasks/clone/{owner}/{repo}")
    async def async_clone_repo(owner: str, repo: str):
        """异步克隆仓库"""
        key = f"{owner}/{repo}"
        running = task_queue.is_running("git_clone", key)
        if running:
            return {"task": running.to_dict(), "message": "克隆任务正在进行中"}

        task = await task_queue._create_task("git_clone", f"克隆仓库 {owner}/{repo}", {"owner": owner, "repo": repo})

        async def _do(t):
            from app.services.git_service import GitRepoService
            gs = _get_git_service(github_service)
            t.log("INFO", f"开始克隆 {owner}/{repo}")
            result = await gs.clone_bare(owner, repo)
            if result.get("status") == "error":
                t.log("ERROR", f"克隆失败: {result['error']}")
                return {"error": result["error"]}
            t.log("INFO", f"克隆完成: {result['status']}, 路径: {result.get('path', '')}")
            return {"cloned": True, "status": result["status"]}

        asyncio.create_task(task_queue.run_task(task, _do, key))
        return {"task": task.to_dict(), "message": "克隆任务已创建"}

    @router.post("/git/tasks/extract/{owner}/{repo}")
    async def async_extract_log(owner: str, repo: str, max_count: int = 0, branch: str = None):
        """异步提取 git log 数据，可指定分支"""
        key = f"{owner}/{repo}"
        running = task_queue.is_running("git_extract", key)
        if running:
            return {"task": running.to_dict(), "message": "提取任务正在进行中"}

        branch_desc = f" (分支: {branch})" if branch else ""
        task = await task_queue._create_task("git_extract", f"提取 {owner}/{repo} git log{branch_desc}", {"owner": owner, "repo": repo, "max_count": max_count, "branch": branch})

        async def _do(t):
            from app.services.git_service import GitRepoService
            gs = _get_git_service(github_service)

            if not gs.is_cloned(owner, repo):
                t.log("INFO", "仓库未克隆，先执行 clone...")
                clone_result = await gs.clone_bare(owner, repo)
                if clone_result.get("status") == "error":
                    t.log("ERROR", f"克隆失败: {clone_result['error']}")
                    return {"error": clone_result["error"]}
                t.log("INFO", f"克隆完成: {clone_result['status']}")

            t.log("INFO", f"开始提取 git log, branch={branch}...")
            result = await gs.extract_git_log(owner, repo, max_count, branch=branch)
            if result.get("error"):
                t.log("ERROR", f"提取失败: {result['error']}")
                return {"error": result["error"]}

            total = result.get("total_commits", 0)
            t.log("INFO", f"提取到 {total} 条 commit")

            if db is not None:
                t.log("INFO", "保存到数据库...")
                await db.save_git_log_summary(owner, repo, result)
                t.log("INFO", "数据库保存完成")

            return {"extracted": total, "branches": len(result.get("branches", [])), "tags": len(result.get("tags", [])), "contributors": len(result.get("contributors", []))}

        asyncio.create_task(task_queue.run_task(task, _do, key))
        return {"task": task.to_dict(), "message": "提取任务已创建"}

    @router.post("/git/tasks/update/{owner}/{repo}")
    async def async_git_update(owner: str, repo: str):
        """异步更新 Git 仓库（fetch 远程更新 + 重新提取 log）"""
        key = f"{owner}/{repo}"
        running = task_queue.is_running("git_update", key)
        if running:
            return {"task": running.to_dict(), "message": "Git 更新任务正在进行中"}

        task = await task_queue._create_task("git_update", f"更新 {owner}/{repo} Git 仓库", {"owner": owner, "repo": repo})

        async def _do(t):
            from app.services.git_service import GitRepoService
            gs = _get_git_service(github_service)

            # 第一步：如果未克隆则先克隆
            if not gs.is_cloned(owner, repo):
                t.log("INFO", "仓库未克隆，先执行 clone...")
                clone_result = await gs.clone_bare(owner, repo)
                if clone_result.get("status") == "error":
                    t.log("ERROR", f"克隆失败: {clone_result['error']}")
                    return {"error": clone_result["error"]}
                t.log("INFO", f"克隆完成: {clone_result['status']}")
            else:
                # 已克隆：fetch 更新远程数据
                t.log("INFO", "执行 git fetch --all...")
                fetch_result = await gs.fetch_update(owner, repo)
                if fetch_result.get("status") == "error":
                    t.log("ERROR", f"fetch 失败: {fetch_result.get('error', '未知错误')}")
                    return {"error": fetch_result.get("error", "fetch 失败")}
                t.log("INFO", f"fetch 完成: {fetch_result.get('status', 'ok')}")

            # 第二步：重新提取 git log（所有分支）
            t.log("INFO", "开始重新提取 git log (所有分支)...")
            result = await gs.extract_git_log(owner, repo, branch="all")
            if result.get("error"):
                t.log("ERROR", f"提取失败: {result['error']}")
                return {"error": result["error"]}

            total = result.get("total_commits", 0)
            t.log("INFO", f"提取到 {total} 条 commit")

            # 第三步：保存到数据库
            if db is not None:
                t.log("INFO", "保存到数据库...")
                await db.save_git_log_summary(owner, repo, result)
                t.log("INFO", "数据库保存完成")

            return {"extracted": total, "branches": len(result.get("branches", [])), "tags": len(result.get("tags", [])), "contributors": len(result.get("contributors", []))}

        asyncio.create_task(task_queue.run_task(task, _do, key))
        return {"task": task.to_dict(), "message": "Git 更新任务已创建"}

    @router.delete("/git/repos/{owner}/{repo}")
    async def delete_repo(owner: str, repo: str):
        """删除已克隆的仓库（仅删除本地文件，不删数据库数据）"""
        from app.services.git_service import GitRepoService
        gs = _get_git_service(github_service)
        deleted = await gs.delete_repo(owner, repo)
        if not deleted:
            raise HTTPException(status_code=404, detail="仓库不存在")
        return {"message": "仓库已删除", "owner": owner, "repo": repo}


def _get_git_service(github_service=None):
    from app.services.git_service import GitRepoService
    token = None
    if github_service and hasattr(github_service, 'token_pool'):
        import asyncio
        try:
            token = asyncio.get_event_loop().run_until_complete(github_service.token_pool.get_token())
        except Exception:
            pass
    return GitRepoService(github_token=token, proxy=_proxy)
