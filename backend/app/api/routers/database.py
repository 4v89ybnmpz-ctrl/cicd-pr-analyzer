"""
数据库接口路由
"""
from fastapi import HTTPException
from datetime import datetime
import logging

from app.models.responses import DatabaseStatsResponse, DeleteResponse, DatabaseAggregateResponse

logger = logging.getLogger(__name__)


def register_database_routes(router, db):
    """注册数据库相关路由"""

    @router.post("/database/projects/register")
    async def register_project(owner: str, repo: str):
        """注册一个项目（添加到项目列表）"""
        if db is None:
            raise HTTPException(status_code=503, detail="数据库未连接")
        existing = await db.db['registered_projects'].find_one({"owner": owner, "repo": repo})
        if existing:
            return {"message": "项目已存在", "owner": owner, "repo": repo}
        doc = {
            "owner": owner, "repo": repo,
            "registered_at": datetime.now().isoformat(),
        }
        await db.db['registered_projects'].insert_one(doc)
        return {"message": "项目已注册", "owner": owner, "repo": repo}

    @router.get("/database/projects/overview")
    async def get_projects_overview():
        """获取所有项目的数据获取情况总览"""
        if db is None:
            raise HTTPException(status_code=503, detail="数据库未连接")
        overview = await db.get_projects_overview()
        return {"projects": overview, "total": len(overview), "timestamp": datetime.now().isoformat()}

    @router.get("/database/stats", response_model=DatabaseStatsResponse)
    async def get_database_stats():
        """获取数据库统计信息"""
        if db is None:
            raise HTTPException(status_code=503, detail="数据库未连接")
        stats = await db.get_stats()
        return {"stats": stats, "timestamp": datetime.now().isoformat()}

    @router.get("/database/prs")
    async def list_database_prs(limit: int = 100):
        """列出数据库中的 PR 数据"""
        if db is None:
            raise HTTPException(status_code=503, detail="数据库未连接")
        data = await db.list_pr_data(limit=limit)
        return {"data": data, "total": len(data), "timestamp": datetime.now().isoformat()}

    @router.get("/database/prs/{owner}/{repo}")
    async def get_database_pr(owner: str, repo: str):
        """获取数据库中的 PR 数据"""
        if db is None:
            raise HTTPException(status_code=503, detail="数据库未连接")
        data = await db.get_pr_data(owner, repo)
        if not data:
            raise HTTPException(status_code=404, detail="数据不存在")
        return {"data": data, "timestamp": datetime.now().isoformat()}

    @router.delete("/database/prs/{owner}/{repo}", response_model=DeleteResponse)
    async def delete_database_pr(owner: str, repo: str):
        """删除数据库中的 PR 数据"""
        if db is None:
            raise HTTPException(status_code=503, detail="数据库未连接")
        if not await db.delete_pr_data(owner, repo):
            raise HTTPException(status_code=404, detail="数据不存在")
        return {"message": "数据已删除", "owner": owner, "repo": repo, "timestamp": datetime.now().isoformat()}

    @router.get("/database/comments")
    async def query_pr_comments(owner: str = None, repo: str = None, page: int = 1, size: int = 20,
                                sort_by: str = "updated_at", sort_order: str = "desc"):
        """查询 PR 评论数据"""
        if db is None:
            raise HTTPException(status_code=503, detail="数据库未连接")
        sort_order_int = -1 if sort_order == "desc" else 1
        result = await db.list_pr_comments(owner, repo, page, size, sort_by, sort_order_int)
        return {**result, "timestamp": datetime.now().isoformat()}

    @router.get("/database/comments/projects")
    async def list_comments_projects():
        """获取有评论数据的项目列表"""
        if db is None:
            raise HTTPException(status_code=503, detail="数据库未连接")
        try:
            pipeline = [
                {"$group": {"_id": {"owner": "$owner", "repo": "$repo"}, "count": {"$sum": 1}}},
                {"$project": {"_id": 0, "owner": "$_id.owner", "repo": "$_id.repo", "count": 1}},
                {"$sort": {"count": -1}},
            ]
            cursor = db.db['pr_comments'].aggregate(pipeline)
            projects = []
            async for doc in cursor:
                projects.append(doc)
            return {"projects": projects}
        except Exception as e:
            logger.error(f"获取评论项目列表失败: {e}")
            return {"projects": []}

    @router.get("/database/timeline")
    async def query_pr_timeline(owner: str = None, repo: str = None, page: int = 1, size: int = 20,
                                sort_by: str = "updated_at", sort_order: str = "desc"):
        """查询 PR 时间线数据"""
        if db is None:
            raise HTTPException(status_code=503, detail="数据库未连接")
        sort_order_int = -1 if sort_order == "desc" else 1
        result = await db.list_pr_timeline(owner, repo, page, size, sort_by, sort_order_int)
        return {**result, "timestamp": datetime.now().isoformat()}

    @router.get("/database/reviews")
    async def query_pr_reviews(owner: str = None, repo: str = None, page: int = 1, size: int = 20,
                               sort_by: str = "updated_at", sort_order: str = "desc"):
        """查询 PR Reviews 数据"""
        if db is None:
            raise HTTPException(status_code=503, detail="数据库未连接")
        sort_order_int = -1 if sort_order == "desc" else 1
        result = await db.list_pr_reviews(owner, repo, page, size, sort_by, sort_order_int)
        return {**result, "timestamp": datetime.now().isoformat()}

    @router.get("/database/commits")
    async def query_pr_commits(owner: str = None, repo: str = None, page: int = 1, size: int = 20,
                               sort_by: str = "updated_at", sort_order: str = "desc"):
        """查询 PR Commits 数据"""
        if db is None:
            raise HTTPException(status_code=503, detail="数据库未连接")
        sort_order_int = -1 if sort_order == "desc" else 1
        result = await db.list_pr_commits(owner, repo, page, size, sort_by, sort_order_int)
        return {**result, "timestamp": datetime.now().isoformat()}

    @router.get("/database/details")
    async def query_pr_details(owner: str = None, repo: str = None, page: int = 1, size: int = 20,
                               sort_by: str = "updated_at", sort_order: str = "desc",
                               state: str = None, start_time: str = None, end_time: str = None):
        """查询 PR 详细信息数据"""
        if db is None:
            raise HTTPException(status_code=503, detail="数据库未连接")
        sort_order_int = -1 if sort_order == "desc" else 1
        result = await db.list_pr_details(owner, repo, page, size, sort_by, sort_order_int, state, start_time, end_time)
        return {**result, "timestamp": datetime.now().isoformat()}

    @router.get("/database/details/search")
    async def search_pr_details(keyword: str, owner: str = None, repo: str = None, page: int = 1, size: int = 20):
        """模糊搜索 PR 详细信息"""
        if db is None:
            raise HTTPException(status_code=503, detail="数据库未连接")
        result = await db.search_pr_details(keyword, owner, repo, page, size)
        return {**result, "timestamp": datetime.now().isoformat()}

    @router.get("/database/aggregate", response_model=DatabaseAggregateResponse)
    async def get_aggregate_stats(owner: str = None, repo: str = None):
        """聚合统计"""
        if db is None:
            raise HTTPException(status_code=503, detail="数据库未连接")
        result = await db.get_aggregate_stats(owner, repo)
        return {"stats": result, "timestamp": datetime.now().isoformat()}

    @router.get("/database/profiles")
    async def list_user_profiles(page: int = 1, size: int = 20,
                                  sort_by: str = "followers", sort_order: str = "desc"):
        """查询用户 Profile 列表"""
        if db is None:
            raise HTTPException(status_code=503, detail="数据库未连接")
        sort_order_int = -1 if sort_order == "desc" else 1
        result = await db.list_user_profiles(page, size, sort_by, sort_order_int)
        return {**result, "timestamp": datetime.now().isoformat()}

    @router.get("/database/user-repos")
    async def list_user_repos(username: str = None, page: int = 1, size: int = 20,
                               sort_by: str = "total_events", sort_order: str = "desc"):
        """查询用户参与的项目"""
        if db is None:
            raise HTTPException(status_code=503, detail="数据库未连接")
        sort_order_int = -1 if sort_order == "desc" else 1
        result = await db.list_user_repos(username, page, size, sort_by, sort_order_int)
        return {**result, "timestamp": datetime.now().isoformat()}

    @router.get("/database/issues")
    async def list_issues(owner: str = None, repo: str = None, page: int = 1, size: int = 20,
                           sort_by: str = "created_at", sort_order: str = "desc", state: str = None):
        """查询 Issues 列表"""
        if db is None:
            raise HTTPException(status_code=503, detail="数据库未连接")
        sort_order_int = -1 if sort_order == "desc" else 1
        result = await db.list_issues(owner, repo, page, size, sort_by, sort_order_int, state)
        return {**result, "timestamp": datetime.now().isoformat()}

    @router.get("/database/issues/projects")
    async def list_issues_projects():
        """获取有 issues 数据的项目列表"""
        if db is None:
            raise HTTPException(status_code=503, detail="数据库未连接")
        try:
            pipeline = [
                {"$group": {"_id": {"owner": "$owner", "repo": "$repo"}, "count": {"$sum": 1}}},
                {"$project": {"_id": 0, "owner": "$_id.owner", "repo": "$_id.repo", "count": 1}},
                {"$sort": {"count": -1}},
            ]
            cursor = db.db['issues'].aggregate(pipeline)
            projects = []
            async for doc in cursor:
                projects.append(doc)
            return {"projects": projects}
        except Exception as e:
            logger.error(f"获取 issues 项目列表失败: {e}")
            return {"projects": []}

    @router.get("/database/issue-timelines")
    async def list_issue_timelines(owner: str = None, repo: str = None, issue_number: int = None,
                                     page: int = 1, size: int = 20,
                                     sort_by: str = "created_at", sort_order: str = "desc"):
        """查询 Issue Timeline"""
        if db is None:
            raise HTTPException(status_code=503, detail="数据库未连接")
        sort_order_int = -1 if sort_order == "desc" else 1
        result = await db.list_issue_timelines(owner, repo, issue_number, page, size, sort_by, sort_order_int)
        return {**result, "timestamp": datetime.now().isoformat()}

    @router.get("/database/issue-timelines/projects")
    async def list_issue_timeline_projects():
        """获取有 issue timeline 数据的项目列表"""
        if db is None:
            raise HTTPException(status_code=503, detail="数据库未连接")
        try:
            pipeline = [
                {"$group": {"_id": {"owner": "$owner", "repo": "$repo"}, "count": {"$sum": 1}}},
                {"$project": {"_id": 0, "owner": "$_id.owner", "repo": "$_id.repo", "count": 1}},
                {"$sort": {"count": -1}},
            ]
            cursor = db.db['issue_timelines'].aggregate(pipeline)
            projects = []
            async for doc in cursor:
                projects.append(doc)
            return {"projects": projects}
        except Exception as e:
            logger.error(f"获取 issue timeline 项目列表失败: {e}")
            return {"projects": []}

    @router.get("/database/developer-relations")
    async def get_developer_relations(owner: str, repo: str):
        """获取指定项目的开发者关系图数据"""
        if db is None:
            raise HTTPException(status_code=503, detail="数据库未连接")
        try:
            import re
            from collections import defaultdict

            # 收集所有 Bot 用户名，用于过滤
            bot_cursor = db.db['pr_comments'].find(
                {"owner": owner, "repo": repo},
                {"user": 1, "is_bot": 1, "user_type": 1, "_id": 0}
            )
            all_user_docs = await bot_cursor.to_list(length=10000)
            bot_names = set()
            for b in all_user_docs:
                u = b.get("user", "")
                if not u:
                    continue
                is_bot = b.get("is_bot", False)
                user_type = b.get("user_type", "")
                if is_bot or user_type == "Bot":
                    bot_names.add(u)
                    bot_names.add(u.replace("[bot]", ""))
                    continue
                lower = u.lower()
                bot_patterns = [
                    u.endswith("[bot]"), u.endswith("-bot"), u.endswith("_bot"),
                    "bot" in lower and any(kw in lower for kw in ["action", "review", "analyze", "timer", "log", "bors"]),
                    lower in ("rustbot", "rust-log-analyzer", "rust-timer", "rust-timer-app"),
                    "dependabot" in lower, "renovate" in lower, "coderabbit" in lower,
                    "github-actions" in lower, "stale" in lower,
                ]
                if any(bot_patterns):
                    bot_names.add(u)
                    bot_names.add(u.replace("[bot]", ""))

            # 拉取所有非 Bot 评论
            cursor = db.db['pr_comments'].find(
                {"owner": owner, "repo": repo, "is_bot": {"$ne": True}},
                {"user": 1, "pr_number": 1, "body": 1, "_id": 0}
            )
            raw_comments = await cursor.to_list(length=10000)
            comments = [c for c in raw_comments if c.get("user") not in bot_names]

            # 拉取 PR 列表（作者）
            pr_data = await db.db['pr_data'].find_one(
                {"owner": owner, "repo": repo},
                {"_id": 0}
            )
            pr_authors = {}
            if pr_data and "prs" in pr_data:
                for pr in pr_data["prs"]:
                    u = pr.get("user")
                    if u:
                        pr_authors[pr["number"]] = u

            # 构建：同一 PR 下互动的用户对
            pr_commenters = defaultdict(set)
            user_comment_count = defaultdict(int)
            for c in comments:
                u = c.get("user")
                if u:
                    pr_commenters[c["pr_number"]].add(u)
                    user_comment_count[u] += 1

            # PR 作者也算该 PR 的参与者（过滤 Bot）
            for pr_num, author in pr_authors.items():
                if author not in bot_names:
                    pr_commenters[pr_num].add(author)
                    user_comment_count.setdefault(author, 0)

            # 统计关系
            edge_counter = defaultdict(lambda: {"co_pr": 0, "mentions": 0, "total": 0})
            all_users = set()

            # 同 PR 互动
            for pr_num, users in pr_commenters.items():
                ulist = sorted(users)
                for i in range(len(ulist)):
                    all_users.add(ulist[i])
                    for j in range(i + 1, len(ulist)):
                        pair = (ulist[i], ulist[j])
                        edge_counter[pair]["co_pr"] += 1
                        edge_counter[pair]["total"] += 1

            # @mention 关系
            for c in comments:
                u = c.get("user")
                body = c.get("body", "")
                if not u or not body:
                    continue
                for m in re.findall(r'@([a-zA-Z0-9](?:[a-zA-Z0-9]|-(?=[a-zA-Z0-9])){0,38})', body):
                    is_bot_mention = m in bot_names or any(m in b or b in m for b in bot_names)
                    if m != u and not is_bot_mention:
                        all_users.add(u)
                        all_users.add(m)
                        a, b = sorted([u, m])
                        edge_counter[(a, b)]["mentions"] += 1
                        edge_counter[(a, b)]["total"] += 1

            # 构建图数据
            nodes = []
            for u in all_users:
                nodes.append({
                    "id": u,
                    "label": u,
                    "comments": user_comment_count.get(u, 0),
                })

            edges = []
            for (a, b), weights in edge_counter.items():
                if weights["total"] > 0:
                    edges.append({
                        "source": a,
                        "target": b,
                        "weight": weights["total"],
                        "co_pr": weights["co_pr"],
                        "mentions": weights["mentions"],
                    })

            edges.sort(key=lambda e: e["weight"], reverse=True)

            return {
                "owner": owner,
                "repo": repo,
                "nodes": nodes,
                "edges": edges,
                "stats": {
                    "total_users": len(nodes),
                    "total_connections": len(edges),
                    "total_comments": len(comments),
                },
            }
        except Exception as e:
            logger.error(f"获取开发者关系失败: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/agent/llm/config")
    async def get_llm_config():
        """获取当前 LLM 配置"""
        import json, os
        config_path = os.path.join(os.path.dirname(__file__), '..', '..', 'llm_config.json')
        saved = {}
        if os.path.exists(config_path):
            try:
                with open(config_path) as f:
                    saved = json.load(f)
            except Exception:
                pass
        try:
            from workflow.config import workflow_config
            llm = workflow_config.llm
            if llm is None:
                return {
                    "provider": saved.get("provider", "anthropic"),
                    "model": saved.get("model", "glm-5.1"),
                    "base_url": saved.get("base_url", ""),
                    "max_tokens": saved.get("max_tokens", 4096),
                    "temperature": saved.get("temperature", 0.3),
                    "ai_ready": False,
                    "api_key_set": bool(saved.get("api_key")),
                }
            return {
                "provider": getattr(workflow_config, "_provider", "anthropic"),
                "model": getattr(llm, "model_name", "") or getattr(llm, "model", "") or saved.get("model", "glm-5.1"),
                "base_url": getattr(llm, "anthropic_api_url", "") or getattr(llm, "base_url", "") or saved.get("base_url", ""),
                "max_tokens": getattr(llm, "max_tokens", 4096),
                "temperature": getattr(llm, "temperature", 0.3),
                "ai_ready": workflow_config.ai_ready,
                "api_key_set": bool(getattr(llm, "anthropic_api_key", None) or getattr(llm, "api_key", None) or saved.get("api_key")),
            }
        except ImportError:
            return {
                "provider": saved.get("provider", "anthropic"),
                "model": saved.get("model", "glm-5.1"),
                "base_url": saved.get("base_url", ""),
                "max_tokens": saved.get("max_tokens", 4096),
                "temperature": saved.get("temperature", 0.3),
                "ai_ready": False,
                "api_key_set": bool(saved.get("api_key")),
            }

    @router.put("/agent/llm/config")
    async def update_llm_config(
        model: str = None, base_url: str = None, api_key: str = None,
        max_tokens: int = None, temperature: float = None,
        provider: str = None,
    ):
        """热更新 LLM 配置（持久化到配置文件，支持热更新）"""
        import json, os
        config_path = os.path.join(os.path.dirname(__file__), '..', '..', 'llm_config.json')
        config = {}
        if os.path.exists(config_path):
            try:
                with open(config_path) as f:
                    config = json.load(f)
            except Exception:
                pass
        if model is not None: config["model"] = model
        if base_url is not None: config["base_url"] = base_url
        if api_key is not None: config["api_key"] = api_key
        if max_tokens is not None: config["max_tokens"] = max_tokens
        if temperature is not None: config["temperature"] = temperature
        if provider is not None: config["provider"] = provider
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)

        # provider 切换或 api_key 变更需要重新初始化 LLM
        need_reinit = provider is not None or api_key is not None
        changed = list(config.keys())
        try:
            from workflow.config import workflow_config
            if need_reinit:
                workflow_config.initialize(
                    anthropic_api_key=config.get("api_key"),
                    anthropic_base_url=config.get("base_url"),
                    max_tokens=config.get("max_tokens"),
                    temperature=config.get("temperature"),
                    model=config.get("model"),
                    provider=config.get("provider", "anthropic"),
                )
            else:
                llm = workflow_config.llm
                if llm is not None:
                    if model and hasattr(llm, "model_name"): llm.model_name = model
                    elif model and hasattr(llm, "model"): llm.model = model
                    if base_url and hasattr(llm, "anthropic_api_url"): llm.anthropic_api_url = base_url
                    elif base_url and hasattr(llm, "base_url"): llm.base_url = base_url
                    if max_tokens is not None: llm.max_tokens = max_tokens
                    if temperature is not None: llm.temperature = temperature
        except ImportError:
            pass
        return {"ok": True, "changed": changed, "message": f"配置已保存: {', '.join(changed)}"}

    @router.post("/agent/llm/test")
    async def test_llm_connection():
        """测试 LLM 连接是否可用，发送简单请求验证端到端可达性"""
        try:
            from workflow.config import workflow_config
            if not workflow_config.ai_ready:
                return {"ok": False, "error": "LLM 未初始化，请先配置 API Key"}
            llm = workflow_config.llm
            import time, asyncio
            start = time.time()
            try:
                response = await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: llm.invoke([
                            {"role": "system", "content": "你是一个测试助手，只回复 OK"},
                            {"role": "user", "content": "回复 OK"},
                        ])
                    ),
                    timeout=15.0
                )
            except asyncio.TimeoutError:
                return {"ok": False, "error": "请求超时（15秒），LLM 服务不可达，请检查 Base URL 和网络"}
            elapsed = round((time.time() - start) * 1000)
            content = response.content if hasattr(response, 'content') else str(response)
            return {
                "ok": True,
                "response": content[:100],
                "latency_ms": elapsed,
                "model": getattr(llm, "model_name", "") or getattr(llm, "model", ""),
            }
        except ImportError:
            return {"ok": False, "error": "LLM 模块未安装"}
        except Exception as e:
            err_msg = str(e)
            if "Connection" in err_msg:
                err_msg = f"连接失败，请检查 Base URL 和网络\n详细信息: {err_msg}"
            elif "401" in err_msg:
                err_msg = "API Key 认证失败（401），请检查 API Key"
            elif "404" in err_msg:
                err_msg = "API 端点不存在（404），请检查 Base URL 和模型名称"
            return {"ok": False, "error": err_msg}

    @router.get("/database/recent-activities")
    async def get_recent_activities(limit: int = 15):
        """获取最近活动时间线（PR创建、评论、Issue 等）"""
        if db is None:
            raise HTTPException(status_code=503, detail="数据库未连接")
        return await db.get_recent_activities(limit)

    @router.get("/database/contributors/top")
    async def get_top_contributors(limit: int = 10, sort_by: str = "total_activity"):
        """获取贡献者排行榜"""
        if db is None:
            raise HTTPException(status_code=503, detail="数据库未连接")
        return await db.get_top_contributors(limit, sort_by)