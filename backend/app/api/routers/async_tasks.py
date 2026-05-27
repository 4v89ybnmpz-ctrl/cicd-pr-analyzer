"""
异步任务路由
"""
from fastapi import HTTPException
from datetime import datetime
import asyncio
import logging

from app.core.task_queue import task_queue

logger = logging.getLogger(__name__)


def register_async_task_routes(router, github_service, db):

    @router.post("/github/tasks/prs/{owner}/{repo}")
    async def async_fetch_prs(owner: str, repo: str, max_count: int = 50, start_page: int = 1):
        """异步获取 PR 数据"""
        key = f"{owner}/{repo}"
        running = task_queue.is_running("fetch_prs", key)
        if running:
            return {"task": running.to_dict(), "message": "该项目的 PR 获取任务正在进行中", "timestamp": datetime.now().isoformat()}

        task = await task_queue._create_task("fetch_prs", f"获取 {owner}/{repo} PR 数据 (max={max_count}, page={start_page})", {"owner": owner, "repo": repo, "max_count": max_count})
        task.total = max_count

        async def _do(t):
            t.log("INFO", f"开始获取 {owner}/{repo} PR, max_count={max_count}, start_page={start_page}")
            result = await github_service.fetch_prs_for_project(owner, repo, max_count=max_count, start_page=start_page)
            t.log("INFO", f"GitHub 返回 {result.get('total', 0)} 个 PR")
            if result.get("error"):
                t.log("ERROR", f"获取失败: {result['error']}")
                return {"fetched": 0, "error": result["error"]}
            if db is not None:
                t.log("INFO", "正在保存到数据库...")
                await db.save_pr_data(owner, repo, result)
                t.log("INFO", "数据库保存完成")
                # 更新同步状态为已全量
                await db.update_sync_status(owner, repo, "prs", "full")
            return {"fetched": result.get("total", 0), "error": None}

        asyncio.create_task(task_queue.run_task(task, _do, key))
        return {"task": task.to_dict(), "message": "任务已创建", "timestamp": datetime.now().isoformat()}

    @router.post("/github/tasks/issues/{owner}/{repo}")
    async def async_fetch_issues(owner: str, repo: str, max_count: int = 30):
        """异步获取 Issues 数据"""
        key = f"{owner}/{repo}"
        running = task_queue.is_running("fetch_issues", key)
        if running:
            return {"task": running.to_dict(), "message": "该项目的 Issues 获取任务正在进行中", "timestamp": datetime.now().isoformat()}

        task = await task_queue._create_task("fetch_issues", f"获取 {owner}/{repo} Issues (max={max_count})", {"owner": owner, "repo": repo, "max_count": max_count})
        task.total = max_count

        async def _do(t):
            t.log("INFO", f"开始获取 {owner}/{repo} Issues, max_count={max_count}")
            result = await github_service.fetch_issues(owner, repo, max_count=max_count)
            t.log("INFO", f"GitHub 返回 {result.get('total', 0)} 个 Issues")
            if result.get("error"):
                t.log("ERROR", f"获取失败: {result['error']}")
                return {"fetched": 0, "error": result["error"]}
            if db is not None:
                t.log("INFO", "正在保存到数据库...")
                await db.save_issues(owner, repo, result)
                t.log("INFO", "数据库保存完成")
                await db.update_sync_status(owner, repo, "issues", "full")
            return {"fetched": result.get("total", 0), "error": None}

        asyncio.create_task(task_queue.run_task(task, _do, key))
        return {"task": task.to_dict(), "message": "任务已创建", "timestamp": datetime.now().isoformat()}

    @router.post("/github/tasks/comments/{owner}/{repo}")
    async def async_fetch_comments(owner: str, repo: str, limit: int = 20):
        """异步获取 PR 评论"""
        key = f"{owner}/{repo}"
        running = task_queue.is_running("fetch_comments", key)
        if running:
            return {"task": running.to_dict(), "message": "该项目的评论获取任务正在进行中", "timestamp": datetime.now().isoformat()}

        task = await task_queue._create_task("fetch_comments", f"获取 {owner}/{repo} PR 评论 (limit={limit})", {"owner": owner, "repo": repo, "limit": limit})
        task.total = limit

        async def _do(t):
            pr_numbers = await _get_pr_numbers(owner, repo, limit, db, github_service)
            t.log("INFO", f"找到 {len(pr_numbers)} 个 PR 需要获取评论")
            semaphore = asyncio.Semaphore(github_service.max_workers)
            total_saved = 0

            async def _fetch(pr_num):
                nonlocal total_saved
                async with semaphore:
                    result = await github_service.fetch_pr_comments(owner, repo, pr_num)
                    if result.get("error") is None and db is not None:
                        await db.save_pr_comments(owner, repo, pr_num, result)
                        total_saved += 1
                        t.progress = total_saved
                        t.log("INFO", f"PR#{pr_num}: {result.get('total', 0)} 条评论")
                    await asyncio.sleep(github_service.request_delay)

            await asyncio.gather(*[_fetch(n) for n in pr_numbers])
            if db is not None:
                await db.update_sync_status(owner, repo, "comments", "full")
            return {"fetched": total_saved}

        asyncio.create_task(task_queue.run_task(task, _do, key))
        return {"task": task.to_dict(), "message": "任务已创建", "timestamp": datetime.now().isoformat()}

    @router.post("/github/tasks/timelines/{owner}/{repo}")
    async def async_fetch_timelines(owner: str, repo: str, limit: int = 10):
        """异步获取 Issue/PR Timelines"""
        key = f"{owner}/{repo}"
        running = task_queue.is_running("fetch_timelines", key)
        if running:
            return {"task": running.to_dict(), "message": "该项目的 Timeline 获取任务正在进行中", "timestamp": datetime.now().isoformat()}

        task = await task_queue._create_task("fetch_timelines", f"获取 {owner}/{repo} Timelines (limit={limit})", {"owner": owner, "repo": repo, "limit": limit})
        task.total = limit

        async def _do(t):
            all_numbers = set()
            if db is not None:
                cursor1 = db.db['issues'].find({"owner": owner, "repo": repo}, {"number": 1, "_id": 0}).limit(limit)
                issues = await cursor1.to_list(length=limit)
                for i in issues:
                    all_numbers.add(i["number"])
                cursor2 = db.db['pr_data'].find({"owner": owner, "repo": repo}, {"pr_number": 1, "_id": 0}).limit(limit)
                prs = await cursor2.to_list(length=limit)
                for p in prs:
                    all_numbers.add(p["pr_number"])
            issue_numbers = sorted(all_numbers, reverse=True)[:limit]
            t.log("INFO", f"共 {len(issue_numbers)} 个 Issue/PR 需要获取 Timeline")
            result = await github_service.fetch_issue_timelines_batch(owner, repo, issue_numbers)
            t.log("INFO", f"批量获取完成, 成功={result.get('success_count', 0)}, 失败={result.get('failed_count', 0)}")
            if db is not None:
                saved = 0
                for r in result.get("results", []):
                    if r.get("error") is None:
                        try:
                            await db.save_issue_timeline(owner, repo, r["issue_number"], r)
                            saved += 1
                        except Exception as ex:
                            t.log("WARN", f"保存 Issue#{r['issue_number']} Timeline 失败: {ex}")
                t.log("INFO", f"已保存 {saved} 个 Timeline 到数据库")
                await db.update_sync_status(owner, repo, "timelines", "full")
            return {"fetched": result.get("success_count", 0), "failed": result.get("failed_count", 0)}

        asyncio.create_task(task_queue.run_task(task, _do, key))
        return {"task": task.to_dict(), "message": "任务已创建", "timestamp": datetime.now().isoformat()}

    @router.post("/github/tasks/profiles/{owner}/{repo}")
    async def async_fetch_profiles(owner: str, repo: str, limit: int = 20):
        """异步获取 Timeline 触发者 Profile"""
        key = f"{owner}/{repo}"
        running = task_queue.is_running("fetch_profiles", key)
        if running:
            return {"task": running.to_dict(), "message": "该项目的 Profile 获取任务正在进行中", "timestamp": datetime.now().isoformat()}

        task = await task_queue._create_task("fetch_profiles", f"获取 {owner}/{repo} 用户 Profile (limit={limit})", {"owner": owner, "repo": repo, "limit": limit})
        task.total = limit

        async def _do(t):
            collection = db.db['issue_timelines']
            if await collection.count_documents({"owner": owner, "repo": repo}) > 0:
                cursor = collection.find({"owner": owner, "repo": repo}, {"actor": 1, "_id": 0}).limit(5000)
                docs = await cursor.to_list(length=5000)
                usernames = list(set(d["actor"] for d in docs if d.get("actor")))
                t.log("INFO", f"从 Timeline 中提取 {len(usernames)} 个去重用户")
            else:
                cursor = db.db['pr_comments'].find({"owner": owner, "repo": repo}, {"user": 1, "_id": 0}).limit(1000)
                comments = await cursor.to_list(length=1000)
                usernames = list(set(c["user"] for c in comments if c.get("user")))
                t.log("INFO", f"从评论中提取 {len(usernames)} 个去重用户")
            if limit > 0:
                usernames = usernames[:limit]
            if not usernames:
                t.log("WARN", "没有可用的用户数据")
                return {"fetched": 0, "error": "没有可用的用户数据"}
            t.log("INFO", f"开始获取 {len(usernames)} 个用户 Profile")
            result = await github_service.fetch_user_profiles_batch(usernames)
            t.log("INFO", f"获取完成, 成功={result.get('success_count', 0)}, 失败={result.get('failed_count', 0)}")
            if db is not None and result.get("profiles"):
                await db.save_user_profiles_batch(result["profiles"])
                t.log("INFO", "Profile 已保存到数据库")
            return {"fetched": result.get("success_count", 0), "failed": result.get("failed_count", 0)}

        asyncio.create_task(task_queue.run_task(task, _do, key))
        return {"task": task.to_dict(), "message": "任务已创建", "timestamp": datetime.now().isoformat()}

    @router.post("/github/tasks/files/{owner}/{repo}")
    async def async_fetch_pr_files(owner: str, repo: str, limit: int = 30):
        """异步获取 PR 变更文件列表"""
        key = f"{owner}/{repo}"
        running = task_queue.is_running("fetch_files", key)
        if running:
            return {"task": running.to_dict(), "message": "该项目的文件获取任务正在进行中", "timestamp": datetime.now().isoformat()}

        task = await task_queue._create_task("fetch_files", f"获取 {owner}/{repo} PR 变更文件 (limit={limit})", {"owner": owner, "repo": repo, "limit": limit})
        task.total = limit

        async def _do(t):
            pr_numbers = await _get_pr_numbers(owner, repo, limit, db, github_service)
            t.log("INFO", f"找到 {len(pr_numbers)} 个 PR 需要获取变更文件")
            semaphore = asyncio.Semaphore(github_service.max_workers)
            total_saved = 0
            total_failed = 0

            async def _fetch(pr_num):
                nonlocal total_saved, total_failed
                async with semaphore:
                    result = await github_service.fetch_pr_files(owner, repo, pr_num)
                    if result.get("error") is None and db is not None:
                        await db.save_pr_files(owner, repo, pr_num, result["files"])
                        total_saved += 1
                        t.progress = total_saved
                        t.log("INFO", f"PR#{pr_num}: {result.get('total', 0)} 个变更文件")
                    else:
                        total_failed += 1
                        t.log("WARN", f"PR#{pr_num}: 获取失败 - {result.get('error', 'unknown')}")
                    await asyncio.sleep(github_service.request_delay)

            await asyncio.gather(*[_fetch(n) for n in pr_numbers])
            t.log("INFO", f"完成: {total_saved} 成功, {total_failed} 失败")
            if db is not None:
                await db.update_sync_status(owner, repo, "details", "full")
            return {"fetched": total_saved, "failed": total_failed}

        asyncio.create_task(task_queue.run_task(task, _do, key))
        return {"task": task.to_dict(), "message": "任务已创建", "timestamp": datetime.now().isoformat()}


async def _get_pr_numbers(owner, repo, limit, db, github_service):
    if db is not None:
        pr_data = await db.get_pr_data(owner, repo)
        if pr_data:
            prs = pr_data.get("prs", [])
            return [pr["number"] for pr in prs[:limit]]
    pr_result = await github_service.fetch_prs_for_project(owner, repo, max_count=limit)
    if pr_result["error"]:
        raise HTTPException(status_code=404, detail=pr_result["error"])
    return [pr["number"] for pr in pr_result["prs"][:limit]]
