"""
数据库服务模块（异步版本）
使用 motor 替代 pymongo，所有方法均为 async
"""
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import asyncio
import logging
import uuid

try:
    from motor.motor_asyncio import AsyncIOMotorClient
    from pymongo.errors import ConnectionFailure, OperationFailure
    DATABASE_AVAILABLE = True
except ImportError:
    DATABASE_AVAILABLE = False
    AsyncIOMotorClient = None

logger = logging.getLogger(__name__)

try:
    from app.core.encryption import get_password_manager
    ENCRYPTION_AVAILABLE = True
except ImportError:
    ENCRYPTION_AVAILABLE = False


class DatabaseService:
    """数据库服务类（异步版本），基于 motor"""

    def __init__(self, host: str = "127.0.0.1", port: int = 27017,
                 username: str = "admin", password: str = "",
                 database: str = "github_pr_db"):
        if not DATABASE_AVAILABLE:
            logger.warning("motor 未安装，数据库功能不可用")
            self.client = None
            self.db = None
            return

        decrypted_password = self._decrypt_password(password)
        self.connection_string = f"mongodb://{username}:{decrypted_password}@{host}:{port}/"
        self.database_name = database
        self.client: Optional[AsyncIOMotorClient] = None
        self.db = None
        logger.info(f"数据库服务初始化: {host}:{port}/{database}")

    def _decrypt_password(self, password: str) -> str:
        if not ENCRYPTION_AVAILABLE:
            return password
        try:
            password_manager = get_password_manager()
            if password_manager.is_encrypted(password):
                decrypted = password_manager.decrypt(password)
                if decrypted:
                    logger.info("密码解密成功")
                    return decrypted
                else:
                    logger.error("密码解密失败，使用原密码")
                    return password
            return password
        except Exception as e:
            logger.warning(f"密码解密过程出错: {e}，使用原密码")
            return password

    # 平台集合映射：不同平台的数据存入不同集合，避免混淆
    _PLATFORM_PREFIXES = {
        "github": "",        # github 保持原集合名（向后兼容）
        "atomgit": "atomgit_",
        "gitcode": "gitcode_",
    }

    _PLATFORM_COLLECTIONS = {
        "pr_data", "pr_comments", "pr_timeline", "pr_details",
        "pr_reviews", "pr_commits", "pr_files", "issues",
        "issue_timelines", "cicd_results", "registered_projects",
        "user_profiles", "user_contributed_repos",
        "git_log_summaries", "git_log_commits",
        "notifications_config", "notifications_history",
    }

    def _coll(self, name: str, platform: str = "github") -> Any:
        """获取平台对应的集合。github 用原名，其他平台加前缀。"""
        if self.db is None:
            return None
        prefix = self._PLATFORM_PREFIXES.get(platform, "")
        return self.db[f"{prefix}{name}"]

    async def connect(self) -> bool:
        """异步连接数据库"""
        if not DATABASE_AVAILABLE:
            return False
        try:
            self.client = AsyncIOMotorClient(
                self.connection_string,
                serverSelectionTimeoutMS=5000
            )
            # 测试连接
            await self.client.admin.command('ping')
            self.db = self.client[self.database_name]
            logger.info("数据库连接成功")
            return True
        except ConnectionFailure as e:
            logger.error(f"数据库连接失败: {e}")
            return False
        except Exception as e:
            logger.error(f"数据库连接异常: {e}")
            return False

    async def disconnect(self):
        """断开数据库连接"""
        if self.client:
            self.client.close()
            logger.info("数据库连接已关闭")

    async def save_pr_data(self, owner: str, repo: str, pr_data: Dict[str, Any], platform: str = "github") -> bool:
        if self.db is None:
            return False
        try:
            collection = self._coll('pr_data')
            prs = pr_data.get("prs", [])
            now = datetime.now().isoformat()
            operations = []
            for pr in prs:
                pr_number = pr.get("number")
                if pr_number is None:
                    continue
                document = {
                    "owner": owner,
                    "repo": repo,
                    "pr_number": pr_number,
                    "platform": platform,
                    "title": pr.get("title"),
                    "user": pr.get("user"),
                    "state": pr.get("state"),
                    "created_at": pr.get("created_at"),
                    "updated_at": pr.get("updated_at"),
                    "url": pr.get("url"),
                    "saved_at": now,
                }
                operations.append(
                    collection.update_one(
                        {"owner": owner, "repo": repo, "pr_number": pr_number, "platform": platform},
                        {"$set": document},
                        upsert=True,
                    )
                )
            if operations:
                await asyncio.gather(*operations)
            logger.info(f"PR 数据已保存: {owner}/{repo}, 共 {len(operations)} 条")
            return True
        except Exception as e:
            logger.error(f"保存 PR 数据失败: {e}")
            return False

    async def update_pr_data(self, owner: str, repo: str, github_service, platform: str = "github") -> Dict[str, Any]:
        """增量更新 PR 数据：对比 updated_at，有变化则替换，无则新增"""
        if self.db is None:
            return {"error": "数据库未连接", "updated": 0, "added": 0, "unchanged": 0}
        try:
            collection = self._coll('pr_data')
            cursor = collection.find({"owner": owner, "repo": repo, "platform": platform}, {"pr_number": 1, "updated_at": 1, "_id": 0})
            old_docs = await cursor.to_list(length=None)
            old_map = {d["pr_number"]: d.get("updated_at") for d in old_docs}
            old_numbers = set(old_map.keys())

            result = await github_service.fetch_prs_for_project(owner, repo, max_count=100)
            if result.get("error"):
                return {"error": result["error"], "updated": 0, "added": 0, "unchanged": 0}

            now = datetime.now().isoformat()
            updated, added, unchanged = 0, 0, 0
            operations = []
            for pr in result.get("prs", []):
                pr_number = pr.get("number")
                if pr_number is None:
                    continue
                new_updated = pr.get("updated_at")
                if pr_number in old_numbers:
                    if old_map[pr_number] != new_updated:
                        document = {
                            "owner": owner, "repo": repo, "pr_number": pr_number,
                            "platform": platform,
                            "title": pr.get("title"), "user": pr.get("user"),
                            "state": pr.get("state"), "created_at": pr.get("created_at"),
                            "updated_at": new_updated, "url": pr.get("url"),
                            "saved_at": now,
                        }
                        operations.append(collection.update_one(
                            {"owner": owner, "repo": repo, "pr_number": pr_number, "platform": platform},
                            {"$set": document},
                        ))
                        updated += 1
                    else:
                        unchanged += 1
                else:
                    document = {
                        "owner": owner, "repo": repo, "pr_number": pr_number,
                        "platform": platform,
                        "title": pr.get("title"), "user": pr.get("user"),
                        "state": pr.get("state"), "created_at": pr.get("created_at"),
                        "updated_at": new_updated, "url": pr.get("url"),
                        "saved_at": now,
                    }
                    operations.append(collection.update_one(
                        {"owner": owner, "repo": repo, "pr_number": pr_number, "platform": platform},
                        {"$set": document},
                        upsert=True,
                    ))
                    added += 1

            if operations:
                await asyncio.gather(*operations)
            logger.info(f"PR 数据更新完成: {owner}/{repo}, 更新={updated}, 新增={added}, 未变={unchanged}")
            return {"updated": updated, "added": added, "unchanged": unchanged, "error": None}
        except Exception as e:
            logger.error(f"更新 PR 数据失败: {e}")
            return {"error": str(e), "updated": 0, "added": 0, "unchanged": 0}

    async def update_issues(self, owner: str, repo: str, github_service) -> Dict[str, Any]:
        """增量更新 Issues 数据"""
        if self.db is None:
            return {"error": "数据库未连接", "updated": 0, "added": 0, "unchanged": 0}
        try:
            collection = self._coll('issues')
            cursor = collection.find({"owner": owner, "repo": repo}, {"number": 1, "updated_at": 1, "_id": 0})
            old_docs = await cursor.to_list(length=None)
            old_map = {d["number"]: d.get("updated_at") for d in old_docs}

            result = await github_service.fetch_issues(owner, repo, max_count=100)
            if result.get("error"):
                return {"error": result["error"], "updated": 0, "added": 0, "unchanged": 0}

            now = datetime.now().isoformat()
            updated, added, unchanged = 0, 0, 0
            operations = []
            for issue in result.get("issues", []):
                number = issue.get("number")
                if number is None:
                    continue
                new_updated = issue.get("updated_at")
                if number in old_map:
                    if old_map[number] != new_updated:
                        document = {**issue, "owner": owner, "repo": repo, "saved_at": now}
                        operations.append(collection.update_one(
                            {"owner": owner, "repo": repo, "number": number},
                            {"$set": document},
                        ))
                        updated += 1
                    else:
                        unchanged += 1
                else:
                    document = {**issue, "owner": owner, "repo": repo, "saved_at": now}
                    operations.append(collection.update_one(
                        {"owner": owner, "repo": repo, "number": number},
                        {"$set": document},
                        upsert=True,
                    ))
                    added += 1

            if operations:
                await asyncio.gather(*operations)
            logger.info(f"Issues 更新完成: {owner}/{repo}, 更新={updated}, 新增={added}, 未变={unchanged}")
            return {"updated": updated, "added": added, "unchanged": unchanged, "error": None}
        except Exception as e:
            logger.error(f"更新 Issues 失败: {e}")
            return {"error": str(e), "updated": 0, "added": 0, "unchanged": 0}

    async def update_comments(self, owner: str, repo: str, github_service, platform: str = "github") -> Dict[str, Any]:
        """增量更新 PR 评论数据：获取数据库中已有 PR，重新拉取评论"""
        if self.db is None:
            return {"error": "数据库未连接", "updated": 0, "added": 0, "unchanged": 0}
        try:
            pr_data = await self.get_pr_data(owner, repo, platform=platform)
            if not pr_data:
                return {"error": "无 PR 数据，请先获取 PR", "updated": 0, "added": 0, "unchanged": 0}
            pr_numbers = [pr["number"] for pr in pr_data.get("prs", [])]

            collection = self._coll('pr_comments')
            cursor = collection.find({"owner": owner, "repo": repo, "platform": platform}, {"comment_id": 1, "updated_at": 1, "_id": 0})
            old_docs = await cursor.to_list(length=None)
            old_map = {d["comment_id"]: d.get("updated_at") for d in old_docs}

            semaphore = asyncio.Semaphore(github_service.max_workers)
            total_updated, total_added, total_unchanged = 0, 0, 0

            async def _fetch_pr_comments(pr_num):
                nonlocal total_updated, total_added, total_unchanged
                async with semaphore:
                    result = await github_service.fetch_pr_comments(owner, repo, pr_num)
                    if result.get("error"):
                        return
                    now = datetime.now().isoformat()
                    operations = []
                    for comment in result.get("comments", []):
                        comment_id = str(comment.get("id"))
                        if not comment_id:
                            continue
                        new_updated = comment.get("updated_at")
                        if comment_id in old_map:
                            if old_map[comment_id] != new_updated:
                                document = {
                                    "owner": owner, "repo": repo, "pr_number": pr_num,
                                    "platform": platform,
                                    "comment_id": comment_id,
                                    "user": comment.get("user"),
                                    "user_id": comment.get("user_id"),
                                    "user_type": comment.get("user_type"),
                                    "is_bot": comment.get("is_bot", False),
                                    "author_association": comment.get("author_association"),
                                    "body": comment.get("body"),
                                    "url": comment.get("url"),
                                    "reactions": comment.get("reactions"),
                                    "created_at": comment.get("created_at"),
                                    "updated_at": new_updated,
                                    "saved_at": now,
                                }
                                operations.append(collection.update_one(
                                    {"comment_id": comment_id, "platform": platform}, {"$set": document}
                                ))
                                total_updated += 1
                            else:
                                total_unchanged += 1
                        else:
                            document = {
                                "owner": owner, "repo": repo, "pr_number": pr_num,
                                "platform": platform,
                                "comment_id": comment_id,
                                "user": comment.get("user"),
                                "user_id": comment.get("user_id"),
                                "user_type": comment.get("user_type"),
                                "is_bot": comment.get("is_bot", False),
                                "author_association": comment.get("author_association"),
                                "body": comment.get("body"),
                                "url": comment.get("url"),
                                "reactions": comment.get("reactions"),
                                "created_at": comment.get("created_at"),
                                "updated_at": new_updated,
                                "saved_at": now,
                            }
                            operations.append(collection.update_one(
                                {"comment_id": comment_id, "platform": platform}, {"$set": document}, upsert=True
                            ))
                            total_added += 1
                    if operations:
                        await asyncio.gather(*operations)
                    await asyncio.sleep(github_service.request_delay)

            await asyncio.gather(*[_fetch_pr_comments(n) for n in pr_numbers])
            logger.info(f"评论更新完成: {owner}/{repo}, 更新={total_updated}, 新增={total_added}, 未变={total_unchanged}")
            return {"updated": total_updated, "added": total_added, "unchanged": total_unchanged, "error": None}
        except Exception as e:
            logger.error(f"更新评论失败: {e}")
            return {"error": str(e), "updated": 0, "added": 0, "unchanged": 0}

    async def get_pr_data(self, owner: str, repo: str, platform: str = None) -> Optional[Dict[str, Any]]:
        if self.db is None:
            return None
        try:
            query = {"owner": owner, "repo": repo}
            if platform is not None:
                query["platform"] = platform
            cursor = self._coll('pr_data').find(query, {"_id": 0})
            docs = await cursor.to_list(length=None)
            if not docs:
                return None
            prs = []
            for doc in docs:
                prs.append({
                    "number": doc.get("pr_number"),
                    "title": doc.get("title"),
                    "user": doc.get("user"),
                    "state": doc.get("state"),
                    "created_at": doc.get("created_at"),
                    "updated_at": doc.get("updated_at"),
                    "url": doc.get("url"),
                })
            return {"owner": owner, "repo": repo, "prs": prs, "total": len(prs), "error": None}
        except Exception as e:
            logger.error(f"获取 PR 数据失败: {e}")
            return None

    async def list_pr_data(self, limit: int = 100, platform: str = None) -> List[Dict[str, Any]]:
        if self.db is None:
            return []
        try:
            pipeline = []
            if platform is not None:
                pipeline.append({"$match": {"platform": platform}})
            pipeline.extend([
                {"$group": {"_id": {"owner": "$owner", "repo": "$repo"}, "total": {"$sum": 1}}},
                {"$limit": limit},
            ])
            cursor = self._coll('pr_data').aggregate(pipeline)
            results = []
            async for doc in cursor:
                key = doc["_id"]
                results.append({"owner": key["owner"], "repo": key["repo"], "total": doc["total"]})
            return results
        except Exception as e:
            logger.error(f"列出 PR 数据失败: {e}")
            return []

    async def delete_pr_data(self, owner: str, repo: str) -> bool:
        if self.db is None:
            return False
        try:
            result = await self._coll('pr_data').delete_many({"owner": owner, "repo": repo})
            if result.deleted_count > 0:
                logger.info(f"PR 数据已删除: {owner}/{repo}, 共 {result.deleted_count} 条")
                return True
            return False
        except Exception as e:
            logger.error(f"删除 PR 数据失败: {e}")
            return False

    async def save_user_profile(self, profile: Dict[str, Any]) -> bool:
        if self.db is None:
            return False
        try:
            login = profile.get("login")
            if not login:
                return False
            now = datetime.now().isoformat()
            await self._coll('user_profiles').update_one(
                {"login": login},
                {"$set": {**profile, "saved_at": now}},
                upsert=True,
            )
            return True
        except Exception as e:
            logger.error(f"保存用户 Profile 失败: {e}")
            return False

    async def save_user_profiles_batch(self, profiles: List[Dict[str, Any]]) -> int:
        if self.db is None or not profiles:
            return 0
        try:
            now = datetime.now().isoformat()
            operations = []
            for p in profiles:
                login = p.get("login")
                if not login:
                    continue
                operations.append(
                    self._coll('user_profiles').update_one(
                        {"login": login},
                        {"$set": {**p, "saved_at": now}},
                        upsert=True,
                    )
                )
            if operations:
                await asyncio.gather(*operations)
            logger.info(f"批量保存用户 Profile: {len(operations)} 条")
            return len(operations)
        except Exception as e:
            logger.error(f"批量保存用户 Profile 失败: {e}")
            return 0

    async def list_user_profiles(self, page: int = 1, size: int = 20,
                                  sort_by: str = "followers", sort_order: int = -1) -> Dict[str, Any]:
        if self.db is None:
            return {"data": [], "total": 0, "page": page, "size": size}
        try:
            collection = self._coll('user_profiles')
            total = await collection.count_documents({})
            skip = (page - 1) * size
            cursor = collection.find({}, {"_id": 0}).sort(sort_by, sort_order).skip(skip).limit(size)
            data = await cursor.to_list(length=size)
            return {"data": data, "total": total, "page": page, "size": size,
                    "total_pages": (total + size - 1) // size if size > 0 else 0}
        except Exception as e:
            logger.error(f"查询用户 Profile 列表失败: {e}")
            return {"data": [], "total": 0, "page": page, "size": size, "error": str(e)}

    async def save_user_repos(self, username: str, repos_data: Dict[str, Any]) -> bool:
        if self.db is None:
            return False
        try:
            now = datetime.now().isoformat()
            collection = self._coll('user_contributed_repos')
            operations = []
            for repo in repos_data.get("repos", []):
                document = {**repo, "username": username, "saved_at": now}
                operations.append(
                    collection.update_one(
                        {"username": username, "repo": repo["repo"]},
                        {"$set": document},
                        upsert=True,
                    )
                )
            if operations:
                await asyncio.gather(*operations)
            logger.info(f"用户参与项目已保存: {username}, 共 {len(operations)} 个项目")
            return True
        except Exception as e:
            logger.error(f"保存用户参与项目失败: {e}")
            return False

    async def list_user_repos(self, username: str = None, page: int = 1, size: int = 20,
                               sort_by: str = "total_events", sort_order: int = -1) -> Dict[str, Any]:
        if self.db is None:
            return {"data": [], "total": 0, "page": page, "size": size}
        try:
            query = {}
            if username:
                query["username"] = username
            total = await self._coll('user_contributed_repos').count_documents(query)
            skip = (page - 1) * size
            cursor = self._coll('user_contributed_repos').find(query, {"_id": 0}).sort(sort_by, sort_order).skip(skip).limit(size)
            data = await cursor.to_list(length=size)
            return {"data": data, "total": total, "page": page, "size": size,
                    "total_pages": (total + size - 1) // size if size > 0 else 0}
        except Exception as e:
            logger.error(f"查询用户参与项目失败: {e}")
            return {"data": [], "total": 0, "page": page, "size": size, "error": str(e)}

    async def save_issues(self, owner: str, repo: str, issues_data: Dict[str, Any], platform: str = "github") -> bool:
        if self.db is None:
            return False
        try:
            collection = self._coll('issues')
            issues = issues_data.get("issues", [])
            now = datetime.now().isoformat()
            operations = []
            for issue in issues:
                number = issue.get("number")
                if number is None:
                    continue
                document = {**issue, "owner": owner, "repo": repo, "platform": platform, "saved_at": now}
                operations.append(
                    collection.update_one(
                        {"owner": owner, "repo": repo, "number": number, "platform": platform},
                        {"$set": document},
                        upsert=True,
                    )
                )
            if operations:
                await asyncio.gather(*operations)
            logger.info(f"Issues 数据已保存: {owner}/{repo}, 共 {len(operations)} 条")
            return True
        except Exception as e:
            logger.error(f"保存 Issues 数据失败: {e}")
            return False

    async def get_issue(self, owner: str, repo: str, number: int) -> Optional[Dict[str, Any]]:
        if self.db is None:
            return None
        try:
            return await self._coll('issues').find_one({"owner": owner, "repo": repo, "number": number}, {"_id": 0})
        except Exception as e:
            logger.error(f"获取 Issue 数据失败: {e}")
            return None

    async def list_issues(self, owner: str = None, repo: str = None,
                           page: int = 1, size: int = 20,
                           sort_by: str = "created_at", sort_order: int = -1,
                           state: str = None, platform: str = None) -> Dict[str, Any]:
        if self.db is None:
            return {"data": [], "total": 0, "page": page, "size": size}
        try:
            query = {}
            if owner:
                query["owner"] = owner
            if repo:
                query["repo"] = repo
            if state:
                query["state"] = state
            if platform is not None:
                query["platform"] = platform
            total = await self._coll('issues').count_documents(query)
            skip = (page - 1) * size
            cursor = self._coll('issues').find(query, {"_id": 0}).sort(sort_by, sort_order).skip(skip).limit(size)
            data = await cursor.to_list(length=size)
            return {"data": data, "total": total, "page": page, "size": size,
                    "total_pages": (total + size - 1) // size if size > 0 else 0}
        except Exception as e:
            logger.error(f"查询 Issues 列表失败: {e}")
            return {"data": [], "total": 0, "page": page, "size": size, "error": str(e)}

    async def save_issue_timeline(self, owner: str, repo: str, issue_number: int, timeline_data: Dict[str, Any], platform: str = "github") -> bool:
        if self.db is None:
            return False
        try:
            collection = self._coll('issue_timelines')
            events = timeline_data.get("events", [])
            is_pr = timeline_data.get("is_pr", False)
            now = datetime.now().isoformat()
            operations = []
            for event in events:
                event_id = event.get("event_id")
                if event_id is None:
                    continue
                document = {
                    "owner": owner, "repo": repo, "issue_number": issue_number,
                    "platform": platform,
                    "is_pr": is_pr,
                    "event_id": str(event_id),
                    "event_type": event.get("event_type"),
                    "actor": event.get("actor"),
                    "actor_id": event.get("actor_id"),
                    "actor_type": event.get("actor_type"),
                    "commit_id": event.get("commit_id"),
                    "commit_url": event.get("commit_url"),
                    "label": event.get("label"),
                    "label_color": event.get("label_color"),
                    "assignee": event.get("assignee"),
                    "milestone": event.get("milestone"),
                    "body": event.get("body"),
                    "url": event.get("url"),
                    "state": event.get("state"),
                    "author_association": event.get("author_association"),
                    "reactions_total": event.get("reactions_total"),
                    "source_type": event.get("source_type"),
                    "source_issue_url": event.get("source_issue_url"),
                    "created_at": event.get("created_at"),
                    "saved_at": now,
                }
                operations.append(
                    collection.update_one(
                        {"owner": owner, "repo": repo, "event_id": str(event_id), "platform": platform},
                        {"$set": document},
                        upsert=True,
                    )
                )
            if operations:
                await asyncio.gather(*operations)
            logger.info(f"Issue Timeline 已保存: {owner}/{repo} Issue#{issue_number}, 共 {len(operations)} 条")
            return True
        except Exception as e:
            logger.error(f"保存 Issue Timeline 失败: {e}")
            return False

    async def list_issue_timelines(self, owner: str = None, repo: str = None, issue_number: int = None,
                                    page: int = 1, size: int = 20,
                                    sort_by: str = "created_at", sort_order: int = -1,
                                    platform: str = None) -> Dict[str, Any]:
        if self.db is None:
            return {"data": [], "total": 0, "page": page, "size": size}
        try:
            query = {}
            if owner:
                query["owner"] = owner
            if repo:
                query["repo"] = repo
            if issue_number:
                query["issue_number"] = issue_number
            if platform is not None:
                query["platform"] = platform
            total = await self._coll('issue_timelines').count_documents(query)
            skip = (page - 1) * size
            cursor = self._coll('issue_timelines').find(query, {"_id": 0}).sort(sort_by, sort_order).skip(skip).limit(size)
            data = await cursor.to_list(length=size)
            return {"data": data, "total": total, "page": page, "size": size,
                    "total_pages": (total + size - 1) // size if size > 0 else 0}
        except Exception as e:
            logger.error(f"查询 Issue Timeline 失败: {e}")
            return {"data": [], "total": 0, "page": page, "size": size, "error": str(e)}

    async def save_pr_comments(self, owner: str, repo: str, pr_number: int, comments_data: Dict[str, Any], platform: str = "github") -> bool:
        if self.db is None:
            return False
        try:
            collection = self._coll('pr_comments')
            comments = comments_data.get("comments", [])
            now = datetime.now().isoformat()
            operations = []
            for comment in comments:
                comment_id = comment.get("id")
                if comment_id is None:
                    continue
                document = {
                    "owner": owner,
                    "repo": repo,
                    "pr_number": pr_number,
                    "platform": platform,
                    "comment_id": str(comment_id),
                    "user": comment.get("user"),
                    "user_id": comment.get("user_id"),
                    "user_type": comment.get("user_type"),
                    "is_bot": comment.get("is_bot", False),
                    "author_association": comment.get("author_association"),
                    "body": comment.get("body"),
                    "url": comment.get("url"),
                    "reactions": comment.get("reactions"),
                    "created_at": comment.get("created_at"),
                    "updated_at": comment.get("updated_at"),
                    "saved_at": now,
                }
                operations.append(
                    collection.update_one(
                        {"owner": owner, "repo": repo, "comment_id": str(comment_id), "platform": platform},
                        {"$set": document},
                        upsert=True,
                    )
                )
            if operations:
                await asyncio.gather(*operations)
            logger.info(f"PR 评论数据已保存: {owner}/{repo} PR#{pr_number}, 共 {len(operations)} 条")
            return True
        except Exception as e:
            logger.error(f"保存 PR 评论数据失败: {e}")
            return False

    async def get_pr_comments(self, owner: str, repo: str, pr_number: int, platform: str = None) -> Optional[Dict[str, Any]]:
        if self.db is None:
            return None
        try:
            query = {"owner": owner, "repo": repo, "pr_number": pr_number}
            if platform is not None:
                query["platform"] = platform
            cursor = self._coll('pr_comments').find(query, {"_id": 0})
            docs = await cursor.to_list(length=None)
            if not docs:
                return None
            comments = []
            for doc in docs:
                comments.append({
                    "id": doc.get("comment_id"),
                    "user": doc.get("user"),
                    "user_id": doc.get("user_id"),
                    "user_type": doc.get("user_type"),
                    "is_bot": doc.get("is_bot"),
                    "author_association": doc.get("author_association"),
                    "body": doc.get("body"),
                    "url": doc.get("url"),
                    "reactions": doc.get("reactions"),
                    "created_at": doc.get("created_at"),
                    "updated_at": doc.get("updated_at"),
                })
            return {"owner": owner, "repo": repo, "pr_number": pr_number, "comments": comments, "total": len(comments), "error": None}
        except Exception as e:
            logger.error(f"获取 PR 评论数据失败: {e}")
            return None

    async def save_pr_timeline(self, owner: str, repo: str, pr_number: int, timeline_data: Dict[str, Any], platform: str = "github") -> bool:
        if self.db is None:
            return False
        try:
            collection = self._coll('pr_timeline')
            document = {
                "owner": owner, "repo": repo, "pr_number": pr_number, "platform": platform, "data": timeline_data,
                "created_at": datetime.now().isoformat(), "updated_at": datetime.now().isoformat()
            }
            await collection.update_one(
                {"owner": owner, "repo": repo, "pr_number": pr_number, "platform": platform},
                {"$set": document}, upsert=True
            )
            logger.info(f"PR 时间线数据已保存: {owner}/{repo} PR#{pr_number}")
            return True
        except Exception as e:
            logger.error(f"保存 PR 时间线数据失败: {e}")
            return False

    async def get_pr_timeline(self, owner: str, repo: str, pr_number: int, platform: str = None) -> Optional[Dict[str, Any]]:
        if self.db is None:
            return None
        try:
            query = {"owner": owner, "repo": repo, "pr_number": pr_number}
            if platform is not None:
                query["platform"] = platform
            return await self._coll('pr_timeline').find_one(
                query, {"_id": 0}
            )
        except Exception as e:
            logger.error(f"获取 PR 时间线数据失败: {e}")
            return None

    async def save_pr_detail(self, owner: str, repo: str, pr_number: int, detail_data: Dict[str, Any], platform: str = "github") -> bool:
        if self.db is None:
            return False
        try:
            collection = self._coll('pr_details')
            document = {
                "owner": owner, "repo": repo, "pr_number": pr_number, "platform": platform, "data": detail_data,
                "created_at": datetime.now().isoformat(), "updated_at": datetime.now().isoformat()
            }
            await collection.update_one(
                {"owner": owner, "repo": repo, "pr_number": pr_number, "platform": platform},
                {"$set": document}, upsert=True
            )
            logger.info(f"PR 详细信息数据已保存: {owner}/{repo} PR#{pr_number}")
            return True
        except Exception as e:
            logger.error(f"保存 PR 详细信息数据失败: {e}")
            return False

    async def get_pr_detail(self, owner: str, repo: str, pr_number: int, platform: str = None) -> Optional[Dict[str, Any]]:
        if self.db is None:
            return None
        try:
            query = {"owner": owner, "repo": repo, "pr_number": pr_number}
            if platform is not None:
                query["platform"] = platform
            return await self._coll('pr_details').find_one(
                query, {"_id": 0}
            )
        except Exception as e:
            logger.error(f"获取 PR 详细信息数据失败: {e}")
            return None

    async def get_stats(self, platform: str = None) -> Dict[str, Any]:
        if self.db is None:
            return {"error": "数据库未连接"}
        try:
            collection_names = await self.db.list_collection_names()
            query = {}
            if platform is not None:
                query["platform"] = platform

            async def _count(name):
                coll = self._coll(name)
                if coll is not None:
                    try:
                        return await coll.count_documents(query)
                    except Exception:
                        return 0
                return 0

            pr_count = await _count('pr_data')
            pr_details_count = await _count('pr_details')
            pr_comments_count = await _count('pr_comments')
            issues_count = await _count('issues')
            issue_timelines_count = await _count('issue_timelines')
            user_profiles_count = await _count('user_profiles')
            user_repos_count = await _count('user_contributed_repos')
            task_count = await _count('tasks')

            return {
                "database": self.database_name,
                "status": "connected",
                "pr_data_count": pr_count,
                "pr_details_count": pr_details_count,
                "pr_comments_count": pr_comments_count,
                "issues_count": issues_count,
                "issue_timelines_count": issue_timelines_count,
                "user_profiles_count": user_profiles_count,
                "user_contributed_repos_count": user_repos_count,
                "task_count": task_count,
            }
        except Exception as e:
            logger.error(f"获取统计信息失败: {e}")
            return {"error": str(e)}

    async def list_pr_comments(self, owner: str = None, repo: str = None,
                               page: int = 1, size: int = 20,
                               sort_by: str = "created_at", sort_order: int = -1,
                               platform: str = None) -> Dict[str, Any]:
        if self.db is None:
            return {"data": [], "total": 0, "page": page, "size": size}
        try:
            collection = self._coll('pr_comments')
            query = {}
            if owner:
                query["owner"] = owner
            if repo:
                query["repo"] = repo
            if platform is not None:
                query["platform"] = platform
            total = await collection.count_documents(query)
            skip = (page - 1) * size
            cursor = collection.find(query, {"_id": 0}).sort(sort_by, sort_order).skip(skip).limit(size)
            data = await cursor.to_list(length=size)
            return {"data": data, "total": total, "page": page, "size": size,
                    "total_pages": (total + size - 1) // size if size > 0 else 0}
        except Exception as e:
            logger.error(f"查询 PR 评论列表失败: {e}")
            return {"data": [], "total": 0, "page": page, "size": size, "error": str(e)}

    async def list_pr_timeline(self, owner: str = None, repo: str = None,
                               page: int = 1, size: int = 20,
                               sort_by: str = "updated_at", sort_order: int = -1,
                               platform: str = None) -> Dict[str, Any]:
        if self.db is None:
            return {"data": [], "total": 0, "page": page, "size": size}
        try:
            collection = self._coll('pr_timeline')
            query = {}
            if owner:
                query["owner"] = owner
            if owner and repo:
                query["repo"] = repo
            if platform is not None:
                query["platform"] = platform
            total = await collection.count_documents(query)
            skip = (page - 1) * size
            cursor = collection.find(query, {"_id": 0}).sort(sort_by, sort_order).skip(skip).limit(size)
            data = await cursor.to_list(length=size)
            return {"data": data, "total": total, "page": page, "size": size,
                    "total_pages": (total + size - 1) // size if size > 0 else 0}
        except Exception as e:
            logger.error(f"查询 PR 时间线列表失败: {e}")
            return {"data": [], "total": 0, "page": page, "size": size, "error": str(e)}

    async def list_pr_details(self, owner: str = None, repo: str = None,
                              page: int = 1, size: int = 20,
                              sort_by: str = "updated_at", sort_order: int = -1,
                              state: str = None, start_time: str = None, end_time: str = None,
                              platform: str = None) -> Dict[str, Any]:
        if self.db is None:
            return {"data": [], "total": 0, "page": page, "size": size}
        try:
            collection = self._coll('pr_details')
            query = {}
            if owner:
                query["owner"] = owner
            if owner and repo:
                query["repo"] = repo
            if state:
                query["data.state"] = state
            if platform is not None:
                query["platform"] = platform
            if start_time or end_time:
                time_query = {}
                if start_time:
                    time_query["$gte"] = start_time
                if end_time:
                    time_query["$lte"] = end_time
                query["updated_at"] = time_query
            total = await collection.count_documents(query)
            skip = (page - 1) * size
            cursor = collection.find(query, {"_id": 0}).sort(sort_by, sort_order).skip(skip).limit(size)
            data = await cursor.to_list(length=size)
            return {"data": data, "total": total, "page": page, "size": size,
                    "total_pages": (total + size - 1) // size if size > 0 else 0}
        except Exception as e:
            logger.error(f"查询 PR 详细信息列表失败: {e}")
            return {"data": [], "total": 0, "page": page, "size": size, "error": str(e)}

    async def search_pr_details(self, keyword: str, owner: str = None, repo: str = None,
                                page: int = 1, size: int = 20, platform: str = None) -> Dict[str, Any]:
        if self.db is None:
            return {"data": [], "total": 0, "page": page, "size": size}
        try:
            collection = self._coll('pr_details')
            query = {"$or": [
                {"data.title": {"$regex": keyword, "$options": "i"}},
                {"data.body": {"$regex": keyword, "$options": "i"}}
            ]}
            if owner:
                query["owner"] = owner
            if owner and repo:
                query["repo"] = repo
            if platform is not None:
                query["platform"] = platform
            total = await collection.count_documents(query)
            skip = (page - 1) * size
            cursor = collection.find(query, {"_id": 0}).sort("updated_at", -1).skip(skip).limit(size)
            data = await cursor.to_list(length=size)
            return {"data": data, "total": total, "page": page, "size": size,
                    "total_pages": (total + size - 1) // size if size > 0 else 0, "keyword": keyword}
        except Exception as e:
            logger.error(f"搜索 PR 详细信息失败: {e}")
            return {"data": [], "total": 0, "page": page, "size": size, "error": str(e)}

    async def save_pr_reviews(self, owner: str, repo: str, pr_number: int, reviews_data: Dict[str, Any]) -> bool:
        if self.db is None:
            return False
        try:
            collection = self._coll('pr_reviews')
            document = {
                "owner": owner, "repo": repo, "pr_number": pr_number, "data": reviews_data,
                "created_at": datetime.now().isoformat(), "updated_at": datetime.now().isoformat()
            }
            await collection.update_one(
                {"owner": owner, "repo": repo, "pr_number": pr_number},
                {"$set": document}, upsert=True
            )
            logger.info(f"PR Reviews 数据已保存: {owner}/{repo} PR#{pr_number}")
            return True
        except Exception as e:
            logger.error(f"保存 PR Reviews 数据失败: {e}")
            return False

    async def get_pr_reviews(self, owner: str, repo: str, pr_number: int) -> Optional[Dict[str, Any]]:
        if self.db is None:
            return None
        try:
            return await self._coll('pr_reviews').find_one(
                {"owner": owner, "repo": repo, "pr_number": pr_number}, {"_id": 0}
            )
        except Exception as e:
            logger.error(f"获取 PR Reviews 数据失败: {e}")
            return None

    async def list_pr_reviews(self, owner: str = None, repo: str = None,
                              page: int = 1, size: int = 20,
                              sort_by: str = "updated_at", sort_order: int = -1) -> Dict[str, Any]:
        if self.db is None:
            return {"data": [], "total": 0, "page": page, "size": size}
        try:
            collection = self._coll('pr_reviews')
            query = {}
            if owner:
                query["owner"] = owner
            if owner and repo:
                query["repo"] = repo
            total = await collection.count_documents(query)
            skip = (page - 1) * size
            cursor = collection.find(query, {"_id": 0}).sort(sort_by, sort_order).skip(skip).limit(size)
            data = await cursor.to_list(length=size)
            return {"data": data, "total": total, "page": page, "size": size,
                    "total_pages": (total + size - 1) // size if size > 0 else 0}
        except Exception as e:
            logger.error(f"查询 PR Reviews 列表失败: {e}")
            return {"data": [], "total": 0, "page": page, "size": size, "error": str(e)}

    async def save_pr_commits(self, owner: str, repo: str, pr_number: int, commits_data: Dict[str, Any]) -> bool:
        if self.db is None:
            return False
        try:
            collection = self._coll('pr_commits')
            document = {
                "owner": owner, "repo": repo, "pr_number": pr_number, "data": commits_data,
                "created_at": datetime.now().isoformat(), "updated_at": datetime.now().isoformat()
            }
            await collection.update_one(
                {"owner": owner, "repo": repo, "pr_number": pr_number},
                {"$set": document}, upsert=True
            )
            logger.info(f"PR Commits 数据已保存: {owner}/{repo} PR#{pr_number}")
            return True
        except Exception as e:
            logger.error(f"保存 PR Commits 数据失败: {e}")
            return False

    async def get_pr_commits(self, owner: str, repo: str, pr_number: int) -> Optional[Dict[str, Any]]:
        if self.db is None:
            return None
        try:
            return await self._coll('pr_commits').find_one(
                {"owner": owner, "repo": repo, "pr_number": pr_number}, {"_id": 0}
            )
        except Exception as e:
            logger.error(f"获取 PR Commits 数据失败: {e}")
            return None

    async def list_pr_commits(self, owner: str = None, repo: str = None,
                              page: int = 1, size: int = 20,
                              sort_by: str = "updated_at", sort_order: int = -1) -> Dict[str, Any]:
        if self.db is None:
            return {"data": [], "total": 0, "page": page, "size": size}
        try:
            collection = self._coll('pr_commits')
            query = {}
            if owner:
                query["owner"] = owner
            if owner and repo:
                query["repo"] = repo
            total = await collection.count_documents(query)
            skip = (page - 1) * size
            cursor = collection.find(query, {"_id": 0}).sort(sort_by, sort_order).skip(skip).limit(size)
            data = await cursor.to_list(length=size)
            return {"data": data, "total": total, "page": page, "size": size,
                    "total_pages": (total + size - 1) // size if size > 0 else 0}
        except Exception as e:
            logger.error(f"查询 PR Commits 列表失败: {e}")
            return {"data": [], "total": 0, "page": page, "size": size, "error": str(e)}

    async def save_cicd_result(self, result_data: Dict[str, Any]) -> bool:
        if self.db is None:
            return False
        try:
            collection = self._coll('cicd_results')
            filter_query = {"owner": result_data.get("owner"), "repo": result_data.get("repo")}
            comment_id = result_data.get("comment_id")
            filter_query["comment_id"] = comment_id if comment_id else None
            result_data["updated_at"] = datetime.now().isoformat()
            await collection.update_one(filter_query, {"$set": result_data}, upsert=True)
            return True
        except Exception as e:
            logger.error(f"保存 CI/CD 结果失败: {e}")
            return False

    async def save_cicd_results_batch(self, results: List[Dict[str, Any]]) -> Dict[str, int]:
        saved = 0
        failed = 0
        for result_data in results:
            if await self.save_cicd_result(result_data):
                saved += 1
            else:
                failed += 1
        logger.info(f"批量保存 CI/CD 结果: {saved} 成功, {failed} 失败")
        return {"saved": saved, "failed": failed}

    async def query_cicd_results(self, owner: str, repo: str,
                                 pr_number: int = None, build_status: str = None,
                                 parser_name: str = None,
                                 start_date: str = None, end_date: str = None,
                                 page: int = 1, size: int = 20,
                                 sort_by: str = "analyzed_at", sort_order: int = -1) -> Dict[str, Any]:
        if self.db is None:
            return {"data": [], "total": 0, "page": page, "size": size}
        try:
            collection = self._coll('cicd_results')
            query = {"owner": owner, "repo": repo}
            if pr_number is not None:
                query["pr_number"] = pr_number
            if build_status:
                query["build_status"] = build_status
            if parser_name:
                query["parser_name"] = parser_name
            if start_date or end_date:
                time_query = {}
                if start_date:
                    time_query["$gte"] = start_date
                if end_date:
                    time_query["$lte"] = end_date
                query["analyzed_at"] = time_query
            total = await collection.count_documents(query)
            skip = (page - 1) * size
            cursor = collection.find(query, {"_id": 0}).sort(sort_by, sort_order).skip(skip).limit(size)
            data = await cursor.to_list(length=size)
            return {"data": data, "total": total, "page": page, "size": size,
                    "total_pages": (total + size - 1) // size if size > 0 else 0}
        except Exception as e:
            logger.error(f"查询 CI/CD 结果失败: {e}")
            return {"data": [], "total": 0, "page": page, "size": size, "error": str(e)}

    async def get_cicd_summary_from_db(self, owner: str, repo: str,
                                       start_date: str = None, end_date: str = None) -> Dict[str, Any]:
        if self.db is None:
            return {"error": "数据库未连接"}
        try:
            collection = self._coll('cicd_results')
            match = {"owner": owner, "repo": repo}
            if start_date or end_date:
                time_query = {}
                if start_date:
                    time_query["$gte"] = start_date
                if end_date:
                    time_query["$lte"] = end_date
                match["analyzed_at"] = time_query

            status_pipeline = [{"$match": match}, {"$group": {"_id": "$build_status", "count": {"$sum": 1}}}]
            by_status = {item["_id"]: item["count"] async for item in collection.aggregate(status_pipeline)}

            parser_pipeline = [{"$match": match}, {"$group": {"_id": "$parser_name", "count": {"$sum": 1}}}]
            by_parser = {item["_id"]: item["count"] async for item in collection.aggregate(parser_pipeline)}

            duration_match = {**match, "duration_seconds": {"$ne": None}}
            duration_pipeline = [{"$match": duration_match}, {"$group": {
                "_id": None, "avg_duration": {"$avg": "$duration_seconds"},
                "count": {"$sum": 1}, "durations": {"$push": "$duration_seconds"}}}]
            duration_stats = await collection.aggregate(duration_pipeline).to_list(length=1)

            coverage_match = {**match, "coverage.percentage": {"$ne": None}}
            coverage_pipeline = [{"$match": coverage_match}, {"$group": {
                "_id": None, "avg_coverage": {"$avg": "$coverage.percentage"}, "count": {"$sum": 1}}}]
            coverage_stats = await collection.aggregate(coverage_pipeline).to_list(length=1)

            total = sum(by_status.values())
            success_count = by_status.get("success", 0)
            failed_count = by_status.get("failed", 0)
            result = {
                "total": total, "by_status": by_status, "by_parser": by_parser,
                "success_count": success_count, "failed_count": failed_count,
                "success_rate": round(success_count / total * 100, 2) if total > 0 else None,
                "failure_rate": round(failed_count / total * 100, 2) if total > 0 else None,
            }
            if duration_stats:
                ds = duration_stats[0]
                result["avg_duration_seconds"] = round(ds["avg_duration"], 2)
                result["duration_count"] = ds["count"]
            if coverage_stats:
                cs = coverage_stats[0]
                result["avg_coverage"] = round(cs["avg_coverage"], 2)
                result["coverage_count"] = cs["count"]
            return result
        except Exception as e:
            logger.error(f"聚合 CI/CD 统计失败: {e}")
            return {"error": str(e)}

    async def get_cicd_trends_from_db(self, owner: str, repo: str,
                                      granularity: str = "day",
                                      start_date: str = None, end_date: str = None) -> List[Dict[str, Any]]:
        if self.db is None:
            return []
        try:
            collection = self._coll('cicd_results')
            match = {"owner": owner, "repo": repo, "analyzed_at": {"$ne": None}}
            if start_date or end_date:
                time_query = {}
                if start_date:
                    time_query["$gte"] = start_date
                if end_date:
                    time_query["$lte"] = end_date
                match["analyzed_at"] = time_query

            if granularity == "month":
                date_format = "%Y-%m"
            elif granularity == "week":
                date_format = "%Y-W%V"
            else:
                date_format = "%Y-%m-%d"

            pipeline = [
                {"$match": match},
                {"$addFields": {"period": {"$dateToString": {
                    "format": date_format,
                    "date": {"$dateFromString": {"dateString": "$analyzed_at"}}}}}},
                {"$group": {
                    "_id": "$period", "total": {"$sum": 1},
                    "success_count": {"$sum": {"$cond": [{"$eq": ["$build_status", "success"]}, 1, 0]}},
                    "failed_count": {"$sum": {"$cond": [{"$eq": ["$build_status", "failed"]}, 1, 0]}},
                    "avg_duration": {"$avg": "$duration_seconds"},
                    "avg_coverage": {"$avg": "$coverage.percentage"}}},
                {"$sort": {"_id": 1}},
            ]
            raw = await collection.aggregate(pipeline).to_list(length=None)
            trends = []
            for r in raw:
                trends.append({
                    "period": r["_id"], "total": r["total"],
                    "success_count": r["success_count"], "failed_count": r["failed_count"],
                    "success_rate": round(r["success_count"] / r["total"] * 100, 2) if r["total"] > 0 else None,
                    "avg_duration_seconds": round(r["avg_duration"], 2) if r.get("avg_duration") else None,
                    "avg_coverage": round(r["avg_coverage"], 2) if r.get("avg_coverage") else None,
                })
            return trends
        except Exception as e:
            logger.error(f"获取 CI/CD 趋势失败: {e}")
            return []

    async def get_cicd_failure_analysis_from_db(self, owner: str, repo: str,
                                                start_date: str = None, end_date: str = None,
                                                top_n: int = 10) -> Dict[str, Any]:
        if self.db is None:
            return {"error": "数据库未连接"}
        try:
            collection = self._coll('cicd_results')
            match = {"owner": owner, "repo": repo, "build_status": "failed"}
            if start_date or end_date:
                time_query = {}
                if start_date:
                    time_query["$gte"] = start_date
                if end_date:
                    time_query["$lte"] = end_date
                match["analyzed_at"] = time_query

            total_failures = await collection.count_documents(match)

            top_jobs_pipeline = [
                {"$match": {**match, "failed_jobs": {"$ne": None, "$not": {"$size": 0}}}},
                {"$unwind": "$failed_jobs"},
                {"$group": {"_id": "$failed_jobs", "count": {"$sum": 1}}},
                {"$sort": {"count": -1}}, {"$limit": top_n},
            ]
            top_failed_jobs = [{"name": item["_id"], "count": item["count"]}
                               async for item in collection.aggregate(top_jobs_pipeline)]

            parser_pipeline = [
                {"$match": match}, {"$group": {"_id": "$parser_name", "count": {"$sum": 1}}},
                {"$sort": {"count": -1}},
            ]
            top_failed_parsers = [{"name": item["_id"], "count": item["count"]}
                                  async for item in collection.aggregate(parser_pipeline)]

            mttr = await self._compute_mttr(collection, owner, repo, start_date, end_date)
            return {
                "total_failures": total_failures, "top_failed_jobs": top_failed_jobs,
                "top_failed_parsers": top_failed_parsers, "avg_recovery_time_seconds": mttr,
            }
        except Exception as e:
            logger.error(f"获取 CI/CD 失败分析失败: {e}")
            return {"error": str(e)}

    async def _compute_mttr(self, collection, owner: str, repo: str,
                            start_date: str = None, end_date: str = None) -> Optional[float]:
        try:
            match = {"owner": owner, "repo": repo, "analyzed_at": {"$ne": None}}
            if start_date or end_date:
                time_query = {}
                if start_date:
                    time_query["$gte"] = start_date
                if end_date:
                    time_query["$lte"] = end_date
                match["analyzed_at"] = time_query

            pipeline = [
                {"$match": match}, {"$sort": {"pr_number": 1, "analyzed_at": 1}},
                {"$group": {"_id": "$pr_number", "results": {"$push": {"status": "$build_status", "time": "$analyzed_at"}}}},
            ]
            pr_groups = await collection.aggregate(pipeline).to_list(length=None)

            recovery_times = []
            for group in pr_groups:
                results = group["results"]
                for i in range(len(results) - 1):
                    if results[i]["status"] == "failed" and results[i + 1]["status"] == "success":
                        try:
                            t_failed = datetime.fromisoformat(results[i]["time"].replace("Z", "+00:00"))
                            t_success = datetime.fromisoformat(results[i + 1]["time"].replace("Z", "+00:00"))
                            delta = (t_success - t_failed).total_seconds()
                            if delta >= 0:
                                recovery_times.append(delta)
                        except Exception:
                            pass
            if recovery_times:
                return round(sum(recovery_times) / len(recovery_times), 2)
            return None
        except Exception as e:
            logger.warning(f"计算 MTTR 失败: {e}")
            return None

    async def get_projects_overview(self) -> List[Dict[str, Any]]:
        """获取所有项目的数据获取情况总览"""
        if self.db is None:
            return []
        try:
            collection_names = await self.db.list_collection_names()

            async def _group_count(collection_name):
                coll = self._coll(collection_name)
                if coll is None:
                    return {}
                pipeline = [
                    {"$group": {"_id": {"owner": "$owner", "repo": "$repo"}, "count": {"$sum": 1}}}
                ]
                cursor = coll.aggregate(pipeline)
                result = {}
                async for doc in cursor:
                    key = f"{doc['_id']['owner']}/{doc['_id']['repo']}"
                    result[key] = doc["count"]
                return result

            pr_data_counts, comments_counts, issues_counts, timeline_counts, details_counts, reviews_counts, pr_commits_counts, git_log_counts = await asyncio.gather(
                _group_count("pr_data"),
                _group_count("pr_comments"),
                _group_count("issues"),
                _group_count("issue_timelines"),
                _group_count("pr_details"),
                _group_count("pr_reviews"),
                _group_count("pr_commits"),
                _group_count("git_log_commits"),
            )

            all_projects = set()
            for m in [pr_data_counts, comments_counts, issues_counts, timeline_counts, details_counts, reviews_counts, pr_commits_counts, git_log_counts]:
                all_projects.update(m.keys())

            async for doc in self._coll('registered_projects').find({}, {"owner": 1, "repo": 1, "_id": 0}):
                all_projects.add(f"{doc['owner']}/{doc['repo']}")

            # 批量读取已缓存的 GitHub 统计和同步状态
            github_stats_map = {}
            sync_status_map = {}
            async for doc in self._coll('registered_projects').find({}, {"owner": 1, "repo": 1, "github_stats": 1, "sync_status": 1, "_id": 0}):
                pk = f"{doc['owner']}/{doc['repo']}"
                if doc.get("github_stats"):
                    github_stats_map[pk] = doc["github_stats"]
                if doc.get("sync_status"):
                    sync_status_map[pk] = doc["sync_status"]

            overview = []
            for project_key in sorted(all_projects):
                parts = project_key.split("/", 1)
                owner, repo = parts[0], parts[1] if len(parts) > 1 else ""

                pr_count = pr_data_counts.get(project_key, 0)
                comments_count = comments_counts.get(project_key, 0)
                issues_count = issues_counts.get(project_key, 0)
                timeline_count = timeline_counts.get(project_key, 0)
                details_count = details_counts.get(project_key, 0)
                reviews_count = reviews_counts.get(project_key, 0)
                git_log_total = git_log_counts.get(project_key, 0)
                commits_count = git_log_total or pr_commits_counts.get(project_key, 0)

                last_updated = None
                for coll_name in ["pr_data", "pr_comments", "issues", "issue_timelines", "pr_details", "git_log_summaries", "git_log_commits"]:
                    try:
                        coll = self._coll(coll_name)
                        if coll is None:
                            continue
                        agg_result = await coll.aggregate([
                            {"$match": {"owner": owner, "repo": repo}},
                            {"$sort": {"saved_at": -1}},
                            {"$limit": 1},
                            {"$project": {"saved_at": 1, "_id": 0}},
                        ]).to_list(length=1)
                        if agg_result and agg_result[0].get("saved_at"):
                            sa = agg_result[0]["saved_at"]
                            if last_updated is None or sa > last_updated:
                                last_updated = sa
                    except Exception:
                        pass

                # GitHub 实际总量（从缓存读取）
                gh_stats = github_stats_map.get(project_key, {})
                # 读取已记录的同步状态（由任务完成时 update_sync_status 写入）
                sync_status = sync_status_map.get(project_key, {})
                # 合并推断：对于已明确标记为 full 的维度保留，其余用推断补充
                inferred = self._infer_sync_status(
                    pr_count, comments_count, issues_count,
                    timeline_count, details_count, reviews_count, commits_count,
                    gh_stats,
                )
                # 如果数据库有明确的 full 标记，优先保留；否则用推断
                merged = {}
                for dim in ["prs", "comments", "issues", "details", "reviews", "commits", "timelines"]:
                    db_val = sync_status.get(dim)
                    if db_val == "full":
                        merged[dim] = "full"
                    else:
                        merged[dim] = inferred.get(dim, "none")
                    sync_status = self._infer_sync_status(
                        pr_count, comments_count, issues_count,
                        timeline_count, details_count, reviews_count, commits_count,
                        gh_stats,
                    )

                overview.append({
                    "owner": owner,
                    "repo": repo,
                    "pr_count": pr_count,
                    "comments_count": comments_count,
                    "issues_count": issues_count,
                    "timeline_count": timeline_count,
                    "details_count": details_count,
                    "reviews_count": reviews_count,
                    "commits_count": commits_count,
                    "git_log_total": git_log_total,
                    "last_updated": last_updated,
                    "github_pr_total": gh_stats.get("github_pr_total"),
                    "github_comments_total": gh_stats.get("github_comments_total"),
                    "github_issues_total": gh_stats.get("github_issues_total"),
                    "sync_status": merged,
                })

            logger.info(f"项目总览: {len(overview)} 个项目")
            return overview
        except Exception as e:
            logger.error(f"获取项目总览失败: {e}")
            return []

    @staticmethod
    def _infer_sync_status(pr_count, comments_count, issues_count,
                           timeline_count, details_count, reviews_count,
                           commits_count, gh_stats) -> Dict[str, str]:
        """根据本地数量和 GitHub 总量自动推断同步状态"""
        gh_pr = gh_stats.get("github_pr_total") if gh_stats else None
        gh_comments = gh_stats.get("github_comments_total") if gh_stats else None
        gh_issues = gh_stats.get("github_issues_total") if gh_stats else None

        def _status(local, remote):
            if local <= 0:
                return "none"
            if remote and remote > 0:
                return "full" if local >= remote else "partial"
            # 有本地数据但没有 GitHub 总量参考，标记为 partial
            return "partial"

        return {
            "prs": _status(pr_count, gh_pr),
            "comments": _status(comments_count, gh_comments),
            "issues": _status(issues_count, gh_issues),
            "details": _status(details_count, gh_pr),
            "reviews": _status(reviews_count, gh_pr),
            "commits": _status(commits_count, gh_pr),
            "timelines": "none" if timeline_count <= 0 else "partial",
        }

    async def update_sync_status(self, owner: str, repo: str, dimension: str, status: str = "full"):
        """更新项目的同步状态"""
        if self.db is None:
            return
        try:
            await self._coll('registered_projects').update_one(
                {"owner": owner, "repo": repo},
                {"$set": {f"sync_status.{dimension}": status}},
            )
        except Exception as e:
            logger.error(f"更新同步状态失败: {e}")

    async def refresh_project_github_stats(self, owner: str, repo: str, github_service) -> Dict:
        """刷新单个项目的 GitHub 统计数据"""
        if self.db is None:
            return {"error": "数据库未连接"}
        try:
            stats = await github_service.get_repo_stats(owner, repo)
            if stats.get("error"):
                return {"error": stats["error"]}

            gh_stats = {
                "github_pr_total": stats.get("github_pr_total"),
                "github_comments_total": stats.get("github_pr_comments_total"),
                "github_issues_total": stats.get("github_pure_issues_total"),
                "stargazers_count": stats.get("stargazers_count"),
                "forks_count": stats.get("forks_count"),
                "updated_at": datetime.now().isoformat(),
            }

            await self._coll('registered_projects').update_one(
                {"owner": owner, "repo": repo},
                {"$set": {"github_stats": gh_stats}},
                upsert=True,
            )
            return {"data": gh_stats, "error": None}
        except Exception as e:
            logger.error(f"刷新 GitHub 统计失败: {e}")
            return {"error": str(e)}

    async def refresh_all_github_stats(self, github_service) -> Dict:
        """批量刷新所有已注册项目的 GitHub 统计"""
        if self.db is None:
            return {"results": [], "error": "数据库未连接"}
        try:
            projects = []
            async for doc in self._coll('registered_projects').find({}, {"owner": 1, "repo": 1, "_id": 0}):
                projects.append((doc["owner"], doc["repo"]))

            results = []
            for owner, repo in projects:
                res = await self.refresh_project_github_stats(owner, repo, github_service)
                results.append({
                    "project": f"{owner}/{repo}",
                    "success": "error" not in res,
                    "error": res.get("error"),
                })

            return {"results": results, "total": len(results)}
        except Exception as e:
            logger.error(f"批量刷新 GitHub 统计失败: {e}")
            return {"results": [], "error": str(e)}

            logger.info(f"项目总览: {len(overview)} 个项目")
            return overview
        except Exception as e:
            logger.error(f"获取项目总览失败: {e}")
            return []

    async def save_git_log_summary(self, owner: str, repo: str, data: Dict[str, Any]) -> bool:
        """保存 git log 提取摘要（不含完整 commits）"""
        if self.db is None:
            return False
        try:
            commits = data.pop("commits", [])
            summary = {**data, "commit_count": len(commits), "saved_at": datetime.now().isoformat()}
            await self._coll('git_log_summaries').update_one(
                {"owner": owner, "repo": repo},
                {"$set": summary},
                upsert=True,
            )
            collection = self._coll('git_log_commits')
            operations = []
            for c in commits:
                doc = {"owner": owner, "repo": repo, **c}
                operations.append(
                    collection.update_one(
                        {"owner": owner, "repo": repo, "hash": c["hash"]},
                        {"$set": doc},
                        upsert=True,
                    )
                )
            if operations:
                await asyncio.gather(*operations)
            logger.info(f"git log 已保存: {owner}/{repo}, {len(commits)} commits")
            return True
        except Exception as e:
            logger.error(f"保存 git log 失败: {e}")
            return False

    async def get_git_log_summary(self, owner: str, repo: str) -> Optional[Dict[str, Any]]:
        if self.db is None:
            return None
        try:
            return await self._coll('git_log_summaries').find_one(
                {"owner": owner, "repo": repo}, {"_id": 0}
            )
        except Exception as e:
            logger.error(f"获取 git log 摘要失败: {e}")
            return None

    async def list_git_log_commits(self, owner: str, repo: str,
                                    author: str = None, branch: str = None,
                                    page: int = 1, size: int = 20,
                                    sort_by: str = "author_date", sort_order: int = -1) -> Dict[str, Any]:
        if self.db is None:
            return {"data": [], "total": 0, "page": page, "size": size}
        try:
            query = {"owner": owner, "repo": repo}
            if author:
                query["author_name"] = {"$regex": author, "$options": "i"}
            if branch:
                query["branches"] = branch
            total = await self._coll('git_log_commits').count_documents(query)
            skip = (page - 1) * size
            cursor = self._coll('git_log_commits').find(query, {"_id": 0}).sort(sort_by, sort_order).skip(skip).limit(size)
            data = await cursor.to_list(length=size)
            return {"data": data, "total": total, "page": page, "size": size,
                    "total_pages": (total + size - 1) // size if size > 0 else 0}
        except Exception as e:
            logger.error(f"查询 git log commits 失败: {e}")
            return {"data": [], "total": 0, "page": page, "size": size, "error": str(e)}

    async def get_aggregate_stats(self, owner: str = None, repo: str = None) -> Dict[str, Any]:
        if self.db is None:
            return {"error": "数据库未连接"}
        try:
            query = {}
            if owner:
                query["owner"] = owner
            if owner and repo:
                query["repo"] = repo

            pr_data_count = await self._coll('pr_data').count_documents(query)
            pr_comments_count = await self._coll('pr_comments').count_documents(query)
            pr_timeline_count = await self._coll('pr_timeline').count_documents(query)
            pr_details_count = await self._coll('pr_details').count_documents(query)

            pipeline = [
                {"$match": query} if query else {"$match": {}},
                {"$group": {"_id": {"owner": "$owner", "repo": "$repo"}, "count": {"$sum": 1}}}
            ]
            by_repo = await self._coll('pr_details').aggregate(pipeline).to_list(length=None)

            state_pipeline = [
                {"$match": query} if query else {"$match": {}},
                {"$group": {"_id": "$data.state", "count": {"$sum": 1}}}
            ]
            by_state = await self._coll('pr_details').aggregate(state_pipeline).to_list(length=None)

            return {
                "pr_data_count": pr_data_count, "pr_comments_count": pr_comments_count,
                "pr_timeline_count": pr_timeline_count, "pr_details_count": pr_details_count,
                "by_repo": by_repo, "by_state": by_state
            }
        except Exception as e:
            logger.error(f"聚合统计失败: {e}")
            return {"error": str(e)}

    # ====================
    # Review 质量评估
    # ====================

    async def get_review_quality_report(self, owner: str, repo: str,
                                         start_date: str = None, end_date: str = None,
                                         top_n: int = 10) -> Dict[str, Any]:
        """
        生成 Review 质量评估报告
        聚合 pr_reviews + pr_details 数据，计算覆盖率/延迟/深度/分布
        """
        if self.db is None:
            return {"error": "数据库未连接"}
        try:
            # 构建时间过滤条件
            time_filter = {}
            if start_date:
                time_filter["$gte"] = start_date
            if end_date:
                time_filter["$lte"] = end_date

            # 1. Review 覆盖率
            coverage = await self._compute_review_coverage(owner, repo, time_filter)

            # 2. Review 延迟
            delay = await self._compute_review_delay(owner, repo, time_filter)

            # 3. Review 深度
            depth = await self._compute_review_depth(owner, repo, time_filter)

            # 4. Review 状态分布
            state_dist = await self._compute_review_state_distribution(owner, repo, time_filter)

            # 5. Top Reviewer
            top_reviewers = await self._compute_top_reviewers(owner, repo, time_filter, top_n)

            # 6. 洞察项
            insights = self._build_review_quality_insights(coverage, delay, depth, state_dist)

            return {
                "owner": owner, "repo": repo,
                "start_date": start_date, "end_date": end_date,
                "coverage": coverage,
                "delay": delay,
                "depth": depth,
                "state_distribution": state_dist,
                "top_reviewers": top_reviewers,
                "insights": insights,
                "generated_at": datetime.now().isoformat(),
            }
        except Exception as e:
            logger.error(f"生成 Review 质量报告失败: {e}")
            return {"error": str(e)}

    async def _compute_review_coverage(self, owner: str, repo: str,
                                        time_filter: dict) -> Dict[str, Any]:
        """计算 Review 覆盖率: 有 review 的 PR 占比"""
        # 从 pr_details 获取 PR 总数（代表已获取详情的 PR）
        details_query = {"owner": owner, "repo": repo}
        if time_filter:
            details_query["data.created_at"] = time_filter

        total_prs = await self._coll('pr_details').count_documents(details_query)

        # 从 pr_reviews 获取有 review 的 PR 数
        reviews_query = {"owner": owner, "repo": repo}
        prs_with_review = await self._coll('pr_reviews').count_documents(reviews_query)

        # 计算平均 reviewer 数（用聚合替代全量加载）
        if prs_with_review > 0:
            try:
                # 先尝试 data 为 array 的格式
                agg_result = await self._coll('pr_reviews').aggregate([
                    {"$match": reviews_query},
                    {"$project": {"review_count": {"$size": {"$ifNull": ["$data", []]}}}},
                    {"$group": {"_id": None, "avg": {"$avg": "$review_count"}}},
                ]).to_list(length=1)
                if agg_result and agg_result[0].get("avg") is not None:
                    avg_reviewers = round(agg_result[0]["avg"], 2)
                else:
                    # data 为 dict 格式，回退到采样
                    sample_docs = await self._coll('pr_reviews').find(reviews_query, {"_id": 0}).to_list(length=100)
                    review_counts = []
                    for doc in sample_docs:
                        reviews_list = self._extract_reviews_list(doc.get("data"))
                        if reviews_list:
                            review_counts.append(len(reviews_list))
                    avg_reviewers = round(sum(review_counts) / len(review_counts), 2) if review_counts else None
            except Exception:
                avg_reviewers = None
        else:
            avg_reviewers = None

        prs_without_review = max(0, total_prs - prs_with_review)
        coverage_rate = round(prs_with_review / total_prs * 100, 2) if total_prs > 0 else None

        return {
            "total_prs": total_prs,
            "prs_with_review": prs_with_review,
            "prs_without_review": prs_without_review,
            "coverage_rate": coverage_rate,
            "avg_reviewers_per_pr": avg_reviewers,
        }

    async def _compute_review_delay(self, owner: str, repo: str,
                                     time_filter: dict) -> Dict[str, Any]:
        """计算 Review 延迟: 首次 review 响应时间"""
        reviews_query = {"owner": owner, "repo": repo}

        # 获取所有 review 文档
        review_docs = await self._coll('pr_reviews').find(reviews_query, {"_id": 0}).to_list(length=None)

        if not review_docs:
            return {
                "total_reviews": 0,
                "avg_first_review_delay_hours": None,
                "median_first_review_delay_hours": None,
                "p90_first_review_delay_hours": None,
                "avg_review_delay_hours": None,
            }

        # 获取对应 PR 的创建时间
        pr_numbers = [doc["pr_number"] for doc in review_docs]
        pr_created_map = {}
        async for detail in self._coll('pr_details').find(
            {"owner": owner, "repo": repo, "pr_number": {"$in": pr_numbers}},
            {"pr_number": 1, "data.created_at": 1, "_id": 0}
        ):
            pr_created_map[detail["pr_number"]] = detail.get("data", {}).get("created_at")

        # 计算每个 PR 的首次 review 延迟和所有 review 延迟
        first_review_delays = []
        all_review_delays = []
        total_reviews = 0

        for doc in review_docs:
            pr_number = doc["pr_number"]
            pr_created = pr_created_map.get(pr_number)
            if not pr_created:
                continue

            try:
                pr_created_dt = datetime.fromisoformat(pr_created[:19])
            except (ValueError, AttributeError):
                continue

            reviews_data = self._extract_reviews_list(doc.get("data"))
            if not reviews_data:
                continue

            # 找到最早的 submitted_at
            pr_first_delay = None
            for review in reviews_data:
                submitted_at = review.get("submitted_at")
                if not submitted_at:
                    continue
                try:
                    submitted_dt = datetime.fromisoformat(submitted_at[:19])
                except (ValueError, AttributeError):
                    continue

                delay_hours = (submitted_dt - pr_created_dt).total_seconds() / 3600
                if delay_hours >= 0:
                    all_review_delays.append(delay_hours)
                    total_reviews += 1
                    if pr_first_delay is None or delay_hours < pr_first_delay:
                        pr_first_delay = delay_hours

            if pr_first_delay is not None:
                first_review_delays.append(pr_first_delay)

        # 计算统计量
        def _percentile(data: list, p: float) -> Optional[float]:
            if not data:
                return None
            sorted_data = sorted(data)
            idx = int(len(sorted_data) * p / 100)
            return round(sorted_data[min(idx, len(sorted_data) - 1)], 2)

        return {
            "total_reviews": total_reviews,
            "avg_first_review_delay_hours": round(sum(first_review_delays) / len(first_review_delays), 2) if first_review_delays else None,
            "median_first_review_delay_hours": _percentile(first_review_delays, 50),
            "p90_first_review_delay_hours": _percentile(first_review_delays, 90),
            "avg_review_delay_hours": round(sum(all_review_delays) / len(all_review_delays), 2) if all_review_delays else None,
        }

    @staticmethod
    def _extract_reviews_list(data) -> list:
        """从 pr_reviews.data 提取 reviews 列表，兼容 array 和 dict 两种格式"""
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            # dict 格式：{"owner":..., "reviews": [...], "total": N}
            if "reviews" in data and isinstance(data["reviews"], list):
                return data["reviews"]
            # 其他 dict 格式尝试取 values
            for v in data.values():
                if isinstance(v, list) and len(v) > 0 and isinstance(v[0], dict):
                    return v
        return []

    async def _compute_review_depth(self, owner: str, repo: str,
                                     time_filter: dict) -> Dict[str, Any]:
        """计算 Review 深度: 评论长度、有内容占比"""
        reviews_query = {"owner": owner, "repo": repo}

        review_docs = await self._coll('pr_reviews').find(reviews_query, {"_id": 0}).to_list(length=None)

        all_reviews = []
        for doc in review_docs:
            all_reviews.extend(self._extract_reviews_list(doc.get("data")))

        total = len(all_reviews)
        if total == 0:
            return {
                "total_reviews": 0, "avg_body_length": None,
                "reviews_with_body": 0, "reviews_without_body": 0, "body_rate": None,
            }

        body_lengths = [len(r.get("body", "") or "") for r in all_reviews]
        with_body = sum(1 for bl in body_lengths if bl > 0)
        without_body = total - with_body
        avg_body_length = round(sum(body_lengths) / total, 2)

        return {
            "total_reviews": total,
            "avg_body_length": avg_body_length,
            "reviews_with_body": with_body,
            "reviews_without_body": without_body,
            "body_rate": round(with_body / total * 100, 2),
        }

    async def _compute_review_state_distribution(self, owner: str, repo: str,
                                                   time_filter: dict) -> Dict[str, Any]:
        """计算 Review 状态分布"""
        reviews_query = {"owner": owner, "repo": repo}

        review_docs = await self._coll('pr_reviews').find(reviews_query, {"_id": 0}).to_list(length=None)

        by_state = {}
        for doc in review_docs:
            for r in self._extract_reviews_list(doc.get("data")):
                state = r.get("state")
                if state:
                    by_state[state] = by_state.get(state, 0) + 1

        return {
            "approved": by_state.get("APPROVED", 0),
            "changes_requested": by_state.get("CHANGES_REQUESTED", 0),
            "commented": by_state.get("COMMENTED", 0),
            "dismissed": by_state.get("DISMISSED", 0),
            "pending": by_state.get("PENDING", 0),
        }

    async def _compute_top_reviewers(self, owner: str, repo: str,
                                       time_filter: dict, top_n: int = 10) -> List[Dict[str, Any]]:
        """计算 Top Reviewer 统计"""
        reviews_query = {"owner": owner, "repo": repo}

        review_docs = await self._coll('pr_reviews').find(reviews_query, {"_id": 0}).to_list(length=None)

        reviewer_map = {}
        for doc in review_docs:
            for r in self._extract_reviews_list(doc.get("data")):
                user = (r.get("user") or {})
                login = user.get("login") if isinstance(user, dict) else str(user)
                if not login:
                    continue
                if login not in reviewer_map:
                    reviewer_map[login] = {"review_count": 0, "approved_count": 0, "changes_requested_count": 0, "body_lengths": []}
                entry = reviewer_map[login]
                entry["review_count"] += 1
                if r.get("state") == "APPROVED":
                    entry["approved_count"] += 1
                if r.get("state") == "CHANGES_REQUESTED":
                    entry["changes_requested_count"] += 1
                body = r.get("body", "") or ""
                entry["body_lengths"].append(len(body))

        sorted_reviewers = sorted(reviewer_map.items(), key=lambda x: x[1]["review_count"], reverse=True)[:top_n]

        return [
            {
                "user": login,
                "review_count": stats["review_count"],
                "approved_count": stats["approved_count"],
                "changes_requested_count": stats["changes_requested_count"],
                "avg_body_length": round(sum(stats["body_lengths"]) / len(stats["body_lengths"]), 2) if stats["body_lengths"] else None,
                "avg_delay_hours": None,
            }
            for login, stats in sorted_reviewers
        ]

    def _build_review_quality_insights(self, coverage: dict, delay: dict,
                                        depth: dict, state_dist: dict) -> List[Dict[str, Any]]:
        """根据统计数据构建 Review 质量洞察项"""
        insights = []

        # 覆盖率洞察
        coverage_rate = coverage.get("coverage_rate")
        if coverage_rate is not None:
            grade, suggestion = self._grade_review_coverage(coverage_rate)
            insights.append({
                "name": "Review 覆盖率",
                "value": coverage_rate,
                "grade": grade,
                "description": f"共 {coverage.get('total_prs', 0)} 个 PR，{coverage.get('prs_with_review', 0)} 个有 review，覆盖率 {coverage_rate}%",
                "suggestion": suggestion,
            })

        # 首次 review 延迟洞察
        avg_delay = delay.get("avg_first_review_delay_hours")
        if avg_delay is not None:
            grade, suggestion = self._grade_review_delay(avg_delay)
            insights.append({
                "name": "首次 Review 延迟",
                "value": avg_delay,
                "grade": grade,
                "description": f"首次 review 平均延迟 {avg_delay} 小时",
                "suggestion": suggestion,
            })

        # Review 深度洞察
        body_rate = depth.get("body_rate")
        if body_rate is not None:
            grade, suggestion = self._grade_review_depth(body_rate)
            insights.append({
                "name": "Review 深度",
                "value": body_rate,
                "grade": grade,
                "description": f"有评论内容的 review 占比 {body_rate}%",
                "suggestion": suggestion,
            })

        # 状态分布洞察
        approved = state_dist.get("approved", 0)
        changes_req = state_dist.get("changes_requested", 0)
        total_states = approved + changes_req + state_dist.get("commented", 0)
        if total_states > 0:
            changes_rate = round(changes_req / total_states * 100, 2)
            if changes_rate > 30:
                insights.append({
                    "name": "变更请求率",
                    "value": changes_rate,
                    "grade": "D",
                    "description": f"CHANGES_REQUESTED 占比 {changes_rate}%，PR 质量可能需要提升",
                    "suggestion": "建议加强 PR 提交前的自审，或拆分大 PR 为小 PR",
                })

        return insights

    @staticmethod
    def _grade_review_coverage(rate: float) -> tuple:
        """Review 覆盖率评级"""
        if rate >= 90:
            return "A", "Review 覆盖率优秀，几乎所有 PR 都经过 review"
        elif rate >= 70:
            return "B", "Review 覆盖率良好，建议关注无 review 的 PR"
        elif rate >= 50:
            return "C", "近半数 PR 缺少 review，建议加强 review 流程"
        elif rate >= 30:
            return "D", "多数 PR 缺少 review，代码质量风险较高"
        else:
            return "F", "Review 覆盖率极低，建议强制要求 PR review"

    @staticmethod
    def _grade_review_delay(hours: float) -> tuple:
        """首次 Review 延迟评级"""
        if hours <= 4:
            return "A", "Review 响应迅速"
        elif hours <= 12:
            return "B", "Review 响应及时"
        elif hours <= 24:
            return "C", "Review 响应偏慢，建议优化 review 流程"
        elif hours <= 48:
            return "D", "Review 响应很慢，影响开发效率"
        else:
            return "F", "Review 严重滞后，建议分配更多 reviewer 或拆分 PR"

    @staticmethod
    def _grade_review_depth(body_rate: float) -> tuple:
        """Review 深度评级（有评论内容的 review 占比）"""
        if body_rate >= 80:
            return "A", "Review 质量优秀，大部分 review 有实质性评论"
        elif body_rate >= 60:
            return "B", "Review 质量良好，部分 review 仅为通过/拒绝"
        elif body_rate >= 40:
            return "C", "Review 深度一般，建议鼓励 reviewer 提供详细反馈"
        elif body_rate >= 20:
            return "D", "Review 深度较浅，多数 review 无实质内容"
        else:
            return "F", "Review 流于形式，建议加强 review 文化"

    async def get_review_quality_trends(self, owner: str, repo: str,
                                         granularity: str = "week",
                                         start_date: str = None, end_date: str = None) -> List[Dict[str, Any]]:
        """获取 Review 质量趋势数据"""
        if self.db is None:
            return []
        try:
            reviews_query = {"owner": owner, "repo": repo}

            if granularity == "month":
                date_format = "%Y-%m"
            elif granularity == "week":
                date_format = "%Y-W%V"
            else:
                date_format = "%Y-%m-%d"

            # 基于 pr_reviews 的 updated_at 做时间聚合
            pipeline = [
                {"$match": reviews_query},
                {"$addFields": {
                    "period": {"$dateToString": {
                        "format": date_format,
                        "date": {"$dateFromString": {"dateString": "$updated_at"}}
                    }},
                    "review_count": {"$size": {"$ifNull": ["$data", []]}},
                }},
                {"$group": {
                    "_id": "$period",
                    "pr_count": {"$sum": 1},
                    "total_reviews": {"$sum": "$review_count"},
                }},
                {"$sort": {"_id": 1}},
            ]

            raw = await self._coll('pr_reviews').aggregate(pipeline).to_list(length=None)

            trends = []
            for r in raw:
                trends.append({
                    "period": r["_id"],
                    "pr_count": r["pr_count"],
                    "total_reviews": r["total_reviews"],
                    "avg_reviews_per_pr": round(r["total_reviews"] / r["pr_count"], 2) if r["pr_count"] > 0 else 0,
                })
            return trends
        except Exception as e:
            logger.error(f"获取 Review 质量趋势失败: {e}")
            return []

    # ====================
    # 项目健康度评分
    # ====================

    async def get_project_health_report(self, owner: str, repo: str,
                                         start_date: str = None, end_date: str = None) -> Dict[str, Any]:
        """
        生成项目健康度报告
        综合多维度指标计算加权健康度分数
        """
        if self.db is None:
            return {"error": "数据库未连接"}
        try:
            time_filter = {}
            if start_date:
                time_filter["$gte"] = start_date
            if end_date:
                time_filter["$lte"] = end_date

            # 1. PR 存活时间维度
            pr_lifetime = await self._compute_pr_lifetime_score(owner, repo, time_filter)

            # 2. Merge 率维度
            merge_rate = await self._compute_merge_rate_score(owner, repo, time_filter)

            # 3. Review 覆盖率维度（复用 29.2）
            review_coverage = await self._compute_review_coverage_score(owner, repo, time_filter)

            # 4. CI 成功率维度
            ci_success = await self._compute_ci_success_score(owner, repo, time_filter)

            # 5. 贡献者多样性维度
            contributor_diversity = await self._compute_contributor_diversity_score(owner, repo, time_filter)

            # 6. Issue 响应速度维度
            issue_response = await self._compute_issue_response_score(owner, repo, time_filter)

            dimensions = [pr_lifetime, merge_rate, review_coverage, ci_success, contributor_diversity, issue_response]
            # 过滤掉无数据的维度
            valid_dims = [d for d in dimensions if d.get("score") is not None and d["score"] > 0]

            if not valid_dims:
                return {
                    "owner": owner, "repo": repo,
                    "start_date": start_date, "end_date": end_date,
                    "overall_score": 0, "overall_grade": "N/A",
                    "dimensions": dimensions, "radar_data": [],
                    "insights": [], "generated_at": datetime.now().isoformat(),
                    "data_available": False,
                }

            # 归一化权重（仅对有数据的维度）
            total_weight = sum(d["weight"] for d in valid_dims)
            overall_score = 0
            for d in valid_dims:
                normalized_weight = d["weight"] / total_weight
                d["weighted_score"] = round(d["score"] * normalized_weight, 2)
                overall_score += d["weighted_score"]
            overall_score = round(overall_score, 2)

            overall_grade = self._score_to_grade(overall_score)

            # 雷达图数据
            radar_data = [{"dimension": d["name"], "score": d["score"]} for d in valid_dims]

            # 洞察项
            insights = self._build_health_insights(dimensions, overall_score, overall_grade)

            return {
                "owner": owner, "repo": repo,
                "start_date": start_date, "end_date": end_date,
                "overall_score": overall_score,
                "overall_grade": overall_grade,
                "dimensions": dimensions,
                "radar_data": radar_data,
                "insights": insights,
                "generated_at": datetime.now().isoformat(),
                "data_available": True,
            }
        except Exception as e:
            logger.error(f"生成项目健康度报告失败: {e}")
            return {"error": str(e)}

    async def _compute_pr_lifetime_score(self, owner: str, repo: str, time_filter: dict) -> Dict[str, Any]:
        """PR 存活时间评分：越短越好，用 Python 计算避免 MongoDB 聚合管道兼容问题"""
        query = {"owner": owner, "repo": repo, "data.merged_at": {"$ne": None}}
        if time_filter:
            query["data.created_at"] = time_filter

        try:
            docs = await self._coll('pr_details').find(
                query, {"data.created_at": 1, "data.merged_at": 1, "_id": 0}
            ).to_list(length=None)
        except Exception:
            docs = []

        if not docs:
            return {"name": "PR 存活时间", "value": None, "score": 0, "weight": 0.2, "weighted_score": 0, "grade": None, "description": "无数据"}

        lifetimes = []
        for doc in docs:
            try:
                created_str = doc.get("data", {}).get("created_at", "")[:19]
                merged_str = doc.get("data", {}).get("merged_at", "")[:19]
                if not created_str or not merged_str:
                    continue
                created_dt = datetime.fromisoformat(created_str)
                merged_dt = datetime.fromisoformat(merged_str)
                hours = (merged_dt - created_dt).total_seconds() / 3600
                if 0 <= hours < 7200:
                    lifetimes.append(hours)
            except (ValueError, TypeError):
                continue

        if not lifetimes:
            return {"name": "PR 存活时间", "value": None, "score": 0, "weight": 0.2, "weighted_score": 0, "grade": None, "description": "无有效数据"}

        avg_hours = sum(lifetimes) / len(lifetimes)
        count = len(lifetimes)
        if avg_hours <= 24:
            score = 100
        elif avg_hours <= 72:
            score = 80 + (72 - avg_hours) / 48 * 20
        elif avg_hours <= 168:
            score = 60 + (168 - avg_hours) / 96 * 20
        elif avg_hours <= 336:
            score = 40 + (336 - avg_hours) / 168 * 20
        elif avg_hours <= 720:
            score = 20 + (720 - avg_hours) / 384 * 20
        else:
            score = max(5, 20 - (avg_hours - 720) / 720 * 10)
        score = round(score, 2)

        grade = self._score_to_grade(score)
        desc = f"平均存活 {avg_hours:.1f}h ({avg_hours/24:.1f}天), 共 {count} 个 PR"
        return {"name": "PR 存活时间", "value": round(avg_hours, 1), "score": score, "weight": 0.2, "weighted_score": 0, "grade": grade, "description": desc}

    async def _compute_merge_rate_score(self, owner: str, repo: str, time_filter: dict) -> Dict[str, Any]:
        """Merge 率评分：适中为佳（60-85% 为最佳区间）"""
        query = {"owner": owner, "repo": repo}
        if time_filter:
            query["data.created_at"] = time_filter

        pipeline = [
            {"$match": query},
            {"$group": {
                "_id": None,
                "total": {"$sum": 1},
                "merged": {"$sum": {"$cond": [{"$eq": ["$data.state", "closed"]}, 1, 0]}},
                "open": {"$sum": {"$cond": [{"$eq": ["$data.state", "open"]}, 1, 0]}},
            }},
        ]

        try:
            result = await self._coll('pr_details').aggregate(pipeline).to_list(length=1)
        except Exception:
            result = []

        if not result:
            return {"name": "Merge 率", "value": None, "score": 0, "weight": 0.15, "weighted_score": 0, "grade": None, "description": "无数据"}

        total = result[0]["total"]
        merged = result[0]["merged"]
        open_count = result[0]["open"]
        closed_count = total - open_count
        merge_rate = round(merged / closed_count * 100, 2) if closed_count > 0 else None

        if merge_rate is None:
            return {"name": "Merge 率", "value": None, "score": 0, "weight": 0.15, "weighted_score": 0, "grade": None, "description": "无已关闭 PR"}

        # 60-85% 最佳区间=100, 偏离越远分越低
        if 60 <= merge_rate <= 85:
            score = 100
        elif merge_rate < 60:
            score = max(10, merge_rate / 60 * 100)
        else:
            score = max(10, 100 - (merge_rate - 85) * 3)
        score = round(score, 2)

        grade = self._score_to_grade(score)
        desc = f"Merge 率 {merge_rate}% ({merged}/{closed_count} 已关闭 PR)"

        return {"name": "Merge 率", "value": merge_rate, "score": score, "weight": 0.15, "weighted_score": 0, "grade": grade, "description": desc}

    async def _compute_review_coverage_score(self, owner: str, repo: str, time_filter: dict) -> Dict[str, Any]:
        """Review 覆盖率评分（复用 29.2 的覆盖率计算）"""
        coverage = await self._compute_review_coverage(owner, repo, time_filter)
        coverage_rate = coverage.get("coverage_rate")

        if coverage_rate is None:
            return {"name": "Review 覆盖率", "value": None, "score": 0, "weight": 0.25, "weighted_score": 0, "grade": None, "description": "无数据"}

        # 直接用覆盖率作为分数
        score = round(coverage_rate, 2)
        grade = self._score_to_grade(score)
        desc = f"覆盖率 {coverage_rate}% ({coverage.get('prs_with_review', 0)}/{coverage.get('total_prs', 0)} PR)"

        return {"name": "Review 覆盖率", "value": coverage_rate, "score": score, "weight": 0.25, "weighted_score": 0, "grade": grade, "description": desc}

    async def _compute_ci_success_score(self, owner: str, repo: str, time_filter: dict) -> Dict[str, Any]:
        """CI 成功率评分"""
        summary = await self.get_cicd_summary_from_db(owner, repo,
                                                       start_date=time_filter.get("$gte"),
                                                       end_date=time_filter.get("$lte"))
        if "error" in summary or summary.get("total", 0) == 0:
            return {"name": "CI 成功率", "value": None, "score": 0, "weight": 0.2, "weighted_score": 0, "grade": None, "description": "无 CI/CD 数据"}

        success_rate = summary.get("success_rate")
        if success_rate is None:
            return {"name": "CI 成功率", "value": None, "score": 0, "weight": 0.2, "weighted_score": 0, "grade": None, "description": "无数据"}

        score = round(success_rate, 2)
        grade = self._score_to_grade(score)
        total = summary.get("total", 0)
        desc = f"成功率 {success_rate}% (共 {total} 次构建)"

        return {"name": "CI 成功率", "value": success_rate, "score": score, "weight": 0.2, "weighted_score": 0, "grade": grade, "description": desc}

    async def _compute_contributor_diversity_score(self, owner: str, repo: str, time_filter: dict) -> Dict[str, Any]:
        """贡献者多样性评分：核心贡献者占比越低越好（Bus Factor）"""
        pipeline = [
            {"$match": {"owner": owner, "repo": repo}},
            {"$group": {"_id": "$data.user.login", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
        ]

        try:
            contributors = await self._coll('pr_details').aggregate(pipeline).to_list(length=None)
        except Exception:
            contributors = []

        contributors = [c for c in contributors if c["_id"]]

        if len(contributors) < 2:
            return {"name": "贡献者多样性", "value": None, "score": 0, "weight": 0.1, "weighted_score": 0, "grade": None, "description": "贡献者不足 2 人"}

        total_prs = sum(c["count"] for c in contributors)
        top3_prs = sum(c["count"] for c in contributors[:3])
        top3_ratio = round(top3_prs / total_prs * 100, 2) if total_prs > 0 else 100

        # Top3 占比越低越好：<=30%=100, 50%=80, 70%=50, 90%=20
        if top3_ratio <= 30:
            score = 100
        elif top3_ratio <= 50:
            score = 80 + (50 - top3_ratio) / 20 * 20
        elif top3_ratio <= 70:
            score = 50 + (70 - top3_ratio) / 20 * 30
        elif top3_ratio <= 90:
            score = 20 + (90 - top3_ratio) / 20 * 30
        else:
            score = max(5, 20 - (top3_ratio - 90) * 1)
        score = round(score, 2)

        grade = self._score_to_grade(score)
        desc = f"Top3 贡献者占比 {top3_ratio}% (共 {len(contributors)} 人)"

        return {"name": "贡献者多样性", "value": top3_ratio, "score": score, "weight": 0.1, "weighted_score": 0, "grade": grade, "description": desc}

    async def _compute_issue_response_score(self, owner: str, repo: str, time_filter: dict) -> Dict[str, Any]:
        """Issue 响应速度评分，用 Python 计算"""
        query = {"owner": owner, "repo": repo, "state": "closed", "closed_at": {"$ne": None}}
        if time_filter:
            query["created_at"] = time_filter

        try:
            docs = await self._coll('issues').find(
                query, {"created_at": 1, "closed_at": 1, "_id": 0}
            ).to_list(length=None)
        except Exception:
            docs = []

        if not docs:
            return {"name": "Issue 响应速度", "value": None, "score": 0, "weight": 0.1, "weighted_score": 0, "grade": None, "description": "无已关闭 Issue 数据"}

        lifetimes = []
        for doc in docs:
            try:
                created_str = (doc.get("created_at") or "")[:19]
                closed_str = (doc.get("closed_at") or "")[:19]
                if not created_str or not closed_str:
                    continue
                created_dt = datetime.fromisoformat(created_str)
                closed_dt = datetime.fromisoformat(closed_str)
                hours = (closed_dt - created_dt).total_seconds() / 3600
                if 0 <= hours < 8760:
                    lifetimes.append(hours)
            except (ValueError, TypeError):
                continue

        if not lifetimes:
            return {"name": "Issue 响应速度", "value": None, "score": 0, "weight": 0.1, "weighted_score": 0, "grade": None, "description": "无有效数据"}

        avg_hours = sum(lifetimes) / len(lifetimes)
        count = len(lifetimes)

        if avg_hours <= 24:
            score = 100
        elif avg_hours <= 72:
            score = 80 + (72 - avg_hours) / 48 * 20
        elif avg_hours <= 168:
            score = 60 + (168 - avg_hours) / 96 * 20
        elif avg_hours <= 336:
            score = 40 + (336 - avg_hours) / 168 * 20
        elif avg_hours <= 720:
            score = 20 + (720 - avg_hours) / 384 * 20
        else:
            score = max(5, 20 - (avg_hours - 720) / 720 * 10)
        score = round(score, 2)

        grade = self._score_to_grade(score)
        desc = f"平均关闭时间 {avg_hours:.1f}h ({avg_hours/24:.1f}天), 共 {count} 个 Issue"
        return {"name": "Issue 响应速度", "value": round(avg_hours, 1), "score": score, "weight": 0.1, "weighted_score": 0, "grade": grade, "description": desc}

    @staticmethod
    def _score_to_grade(score: float) -> str:
        """分数转评级"""
        if score >= 90:
            return "A"
        elif score >= 75:
            return "B"
        elif score >= 60:
            return "C"
        elif score >= 40:
            return "D"
        else:
            return "F"

    def _build_health_insights(self, dimensions: list, overall_score: float, overall_grade: str) -> List[Dict[str, Any]]:
        """构建健康度洞察项"""
        insights = []

        # 综合评级洞察
        grade_desc = {
            "A": "项目非常健康，各维度表现优秀",
            "B": "项目整体健康，部分维度有提升空间",
            "C": "项目健康状况一般，建议关注低分维度",
            "D": "项目健康度较低，需要重点改进",
            "F": "项目健康度很差，建议全面审视流程",
        }
        insights.append({
            "name": "综合健康度",
            "value": overall_score,
            "grade": overall_grade,
            "description": f"综合健康度 {overall_score} 分，评级 {overall_grade}",
            "suggestion": grade_desc.get(overall_grade, ""),
        })

        # 找出最弱维度
        valid_dims = [d for d in dimensions if d.get("score") and d["score"] > 0]
        if valid_dims:
            weakest = min(valid_dims, key=lambda d: d["score"])
            if weakest["grade"] in ("D", "F"):
                suggestions = {
                    "PR 存活时间": "建议拆分大 PR、优化 review 流程以缩短 PR 存活时间",
                    "Merge 率": "建议审视 PR 流程，过低说明大量 PR 未合并，过高可能缺乏审查",
                    "Review 覆盖率": "建议强制要求 PR review，配置 CODEOWNERS",
                    "CI 成功率": "建议优先修复 CI 失败，排查 flaky test",
                    "贡献者多样性": "建议鼓励更多贡献者参与，降低贡献门槛",
                    "Issue 响应速度": "建议增加维护者，或设置 Issue 自动分派",
                }
                insights.append({
                    "name": "最弱维度",
                    "value": weakest["score"],
                    "grade": weakest["grade"],
                    "description": f"{weakest['name']} 评分最低 ({weakest['score']} 分)",
                    "suggestion": suggestions.get(weakest["name"], "建议重点关注该维度的改进"),
                })

        # 找出最强维度
        if valid_dims:
            strongest = max(valid_dims, key=lambda d: d["score"])
            if strongest["grade"] == "A":
                insights.append({
                    "name": "最强维度",
                    "value": strongest["score"],
                    "grade": "A",
                    "description": f"{strongest['name']} 表现优秀 ({strongest['score']} 分)",
                    "suggestion": "保持当前水平",
                })

        return insights

    async def get_project_health_trends(self, owner: str, repo: str,
                                         granularity: str = "month",
                                         start_date: str = None, end_date: str = None) -> List[Dict[str, Any]]:
        """获取项目健康度趋势（按时间段分别计算健康度）"""
        if self.db is None:
            return []
        try:
            # 基于 pr_details 的 created_at 做时间分桶
            if granularity == "month":
                date_format = "%Y-%m"
            elif granularity == "week":
                date_format = "%Y-W%V"
            else:
                date_format = "%Y-%m-%d"

            pipeline = [
                {"$match": {"owner": owner, "repo": repo, "data.created_at": {"$ne": None}}},
                {"$addFields": {
                    "period": {"$dateToString": {
                        "format": date_format,
                        "date": {"$dateFromString": {"dateString": "$data.created_at"}}
                    }},
                }},
                {"$group": {
                    "_id": "$period",
                    "total_prs": {"$sum": 1},
                    "merged_prs": {"$sum": {"$cond": [{"$eq": ["$data.state", "closed"]}, 1, 0]}},
                    "open_prs": {"$sum": {"$cond": [{"$eq": ["$data.state", "open"]}, 1, 0]}},
                    "contributors": {"$addToSet": "$data.user.login"},
                }},
                {"$addFields": {"contributor_count": {"$size": "$contributors"}}},
                {"$sort": {"_id": 1}},
            ]

            raw = await self._coll('pr_details').aggregate(pipeline).to_list(length=None)

            trends = []
            for r in raw:
                total = r["total_prs"]
                merged = r["merged_prs"]
                open_count = r["open_prs"]
                closed = total - open_count
                merge_rate = round(merged / closed * 100, 2) if closed > 0 else None
                contributor_count = r["contributor_count"]

                # 简化评分：merge_rate + contributor 多样性
                merge_score = 100 if merge_rate and 60 <= merge_rate <= 85 else (merge_rate or 0) * 0.8
                diversity_score = min(100, contributor_count * 10)

                trends.append({
                    "period": r["_id"],
                    "total_prs": total,
                    "merged_prs": merged,
                    "merge_rate": merge_rate,
                    "contributor_count": contributor_count,
                    "merge_score": round(merge_score, 2),
                    "diversity_score": round(diversity_score, 2),
                })
            return trends
        except Exception as e:
            logger.error(f"获取项目健康度趋势失败: {e}")
            return []

    # ====================
    # 趋势预警
    # ====================

    async def get_trend_alerts(self, owner: str, repo: str,
                                period_days: int = 7) -> Dict[str, Any]:
        """
        生成趋势预警报告
        对比本期和上期指标，检测异常变化
        """
        if self.db is None:
            return {"error": "数据库未连接"}
        try:
            now = datetime.now()
            period_start = (now - timedelta(days=period_days)).strftime("%Y-%m-%d")
            prev_start = (now - timedelta(days=period_days * 2)).strftime("%Y-%m-%d")
            today = now.strftime("%Y-%m-%d")

            alerts = []

            # 1. CI 失败率突增预警
            ci_alert = await self._check_ci_failure_alert(owner, repo, period_start, today, prev_start, period_start)
            if ci_alert:
                alerts.append(ci_alert)

            # 2. Review 延迟增长预警
            review_alert = await self._check_review_delay_alert(owner, repo, period_start, today, prev_start, period_start)
            if review_alert:
                alerts.append(review_alert)

            # 3. 贡献者流失预警
            contrib_alert = await self._check_contributor_loss_alert(owner, repo, period_start, today, prev_start, period_start)
            if contrib_alert:
                alerts.append(contrib_alert)

            # 4. PR 存活时间增长预警
            lifetime_alert = await self._check_pr_lifetime_alert(owner, repo, period_start, today, prev_start, period_start)
            if lifetime_alert:
                alerts.append(lifetime_alert)

            # 摘要
            critical = sum(1 for a in alerts if a["severity"] == "critical")
            warning = sum(1 for a in alerts if a["severity"] == "warning")
            info = sum(1 for a in alerts if a["severity"] == "info")

            return {
                "owner": owner, "repo": repo,
                "period_days": period_days,
                "alerts": alerts,
                "summary": {
                    "total": len(alerts),
                    "critical": critical,
                    "warning": warning,
                    "info": info,
                },
                "generated_at": now.isoformat(),
            }
        except Exception as e:
            logger.error(f"生成趋势预警失败: {e}")
            return {"error": str(e)}

    async def _check_ci_failure_alert(self, owner: str, repo: str,
                                       cur_start: str, cur_end: str,
                                       prev_start: str, prev_end: str) -> Optional[Dict[str, Any]]:
        """CI 失败率环比预警"""
        cur = await self.get_cicd_summary_from_db(owner, repo, cur_start, cur_end)
        prev = await self.get_cicd_summary_from_db(owner, repo, prev_start, prev_end)

        cur_rate = cur.get("failure_rate")
        prev_rate = prev.get("failure_rate")

        if cur_rate is None or prev_rate is None:
            return None

        change = cur_rate - prev_rate
        change_pct = round(change / prev_rate * 100, 2) if prev_rate > 0 else None

        if change > 20:
            severity = "critical"
        elif change > 10:
            severity = "warning"
        elif change > 5:
            severity = "info"
        else:
            return None

        return {
            "alert_type": "ci_failure",
            "severity": severity,
            "title": "CI 失败率上升",
            "description": f"CI 失败率从 {prev_rate}% 上升到 {cur_rate}%（+{change:.1f}%）",
            "current_value": cur_rate,
            "previous_value": prev_rate,
            "change_rate": change_pct,
            "threshold": 10.0,
            "dimension": "CI 成功率",
            "suggestion": "建议排查近期 CI 失败原因，关注 flaky test 和环境变更",
        }

    async def _check_review_delay_alert(self, owner: str, repo: str,
                                          cur_start: str, cur_end: str,
                                          prev_start: str, prev_end: str) -> Optional[Dict[str, Any]]:
        """Review 延迟环比预警"""
        cur_report = await self.get_review_quality_report(owner, repo, cur_start, cur_end)
        prev_report = await self.get_review_quality_report(owner, repo, prev_start, prev_end)

        if "error" in cur_report or "error" in prev_report:
            return None

        cur_delay = cur_report.get("delay", {}).get("avg_first_review_delay_hours")
        prev_delay = prev_report.get("delay", {}).get("avg_first_review_delay_hours")

        if cur_delay is None or prev_delay is None or prev_delay == 0:
            return None

        change = cur_delay - prev_delay
        change_pct = round(change / prev_delay * 100, 2)

        if change_pct > 50:
            severity = "critical"
        elif change_pct > 30:
            severity = "warning"
        elif change_pct > 15:
            severity = "info"
        else:
            return None

        return {
            "alert_type": "review_delay",
            "severity": severity,
            "title": "Review 响应变慢",
            "description": f"首次 Review 延迟从 {prev_delay}h 增加到 {cur_delay}h（+{change_pct}%）",
            "current_value": cur_delay,
            "previous_value": prev_delay,
            "change_rate": change_pct,
            "threshold": 30.0,
            "dimension": "Review 延迟",
            "suggestion": "建议分配更多 reviewer，或拆分大 PR 缩短 review 时间",
        }

    async def _check_contributor_loss_alert(self, owner: str, repo: str,
                                              cur_start: str, cur_end: str,
                                              prev_start: str, prev_end: str) -> Optional[Dict[str, Any]]:
        """贡献者流失预警"""
        cur_contribs = await self._count_active_contributors(owner, repo, cur_start, cur_end)
        prev_contribs = await self._count_active_contributors(owner, repo, prev_start, prev_end)

        if prev_contribs == 0:
            return None

        loss = prev_contribs - cur_contribs
        loss_pct = round(loss / prev_contribs * 100, 2)

        if loss_pct > 40:
            severity = "critical"
        elif loss_pct > 25:
            severity = "warning"
        elif loss_pct > 10:
            severity = "info"
        else:
            return None

        return {
            "alert_type": "contributor_loss",
            "severity": severity,
            "title": "活跃贡献者减少",
            "description": f"活跃贡献者从 {prev_contribs} 人减少到 {cur_contribs} 人（-{loss_pct}%）",
            "current_value": cur_contribs,
            "previous_value": prev_contribs,
            "change_rate": -loss_pct,
            "threshold": 25.0,
            "dimension": "贡献者多样性",
            "suggestion": "建议关注核心贡献者状态，降低贡献门槛，鼓励新贡献者参与",
        }

    async def _count_active_contributors(self, owner: str, repo: str,
                                           start_date: str, end_date: str) -> int:
        """统计时间段内活跃贡献者数"""
        query = {"owner": owner, "repo": repo}
        if start_date:
            query["data.created_at"] = {"$gte": start_date}
        if end_date:
            time_cond = query.get("data.created_at", {})
            if isinstance(time_cond, dict):
                time_cond["$lte"] = end_date
            query["data.created_at"] = time_cond

        pipeline = [
            {"$match": query},
            {"$group": {"_id": "$data.user.login"}},
        ]
        try:
            result = await self._coll('pr_details').aggregate(pipeline).to_list(length=None)
            return len([r for r in result if r["_id"]])
        except Exception:
            return 0

    async def _check_pr_lifetime_alert(self, owner: str, repo: str,
                                         cur_start: str, cur_end: str,
                                         prev_start: str, prev_end: str) -> Optional[Dict[str, Any]]:
        """PR 存活时间增长预警"""
        cur_score = await self._compute_pr_lifetime_score(owner, repo, {"$gte": cur_start, "$lte": cur_end})
        prev_score = await self._compute_pr_lifetime_score(owner, repo, {"$gte": prev_start, "$lte": prev_end})

        cur_val = cur_score.get("value")
        prev_val = prev_score.get("value")

        if cur_val is None or prev_val is None or prev_val == 0:
            return None

        change_pct = round((cur_val - prev_val) / prev_val * 100, 2)

        if change_pct > 50:
            severity = "critical"
        elif change_pct > 30:
            severity = "warning"
        elif change_pct > 15:
            severity = "info"
        else:
            return None

        return {
            "alert_type": "pr_lifetime",
            "severity": severity,
            "title": "PR 存活时间增长",
            "description": f"PR 平均存活时间从 {prev_val}h 增加到 {cur_val}h（+{change_pct}%）",
            "current_value": cur_val,
            "previous_value": prev_val,
            "change_rate": change_pct,
            "threshold": 30.0,
            "dimension": "PR 存活时间",
            "suggestion": "建议拆分大 PR、优化 review 流程、设置 PR 自动分派",
        }

    # ====================
    # PR 变更文件 + 代码变更热力图
    # ====================

    async def save_pr_files(self, owner: str, repo: str, pr_number: int, files_data: List[Dict[str, Any]]) -> bool:
        """保存 PR 变更文件数据"""
        if self.db is None:
            return False
        try:
            collection = self._coll('pr_files')
            document = {
                "owner": owner, "repo": repo, "pr_number": pr_number,
                "data": files_data,
                "created_at": datetime.now().isoformat(), "updated_at": datetime.now().isoformat(),
            }
            await collection.update_one(
                {"owner": owner, "repo": repo, "pr_number": pr_number},
                {"$set": document}, upsert=True
            )
            logger.info(f"PR 变更文件已保存: {owner}/{repo} PR#{pr_number} ({len(files_data)} files)")
            return True
        except Exception as e:
            logger.error(f"保存 PR 变更文件失败: {e}")
            return False

    async def get_pr_files(self, owner: str, repo: str, pr_number: int) -> Optional[Dict[str, Any]]:
        """获取 PR 变更文件数据"""
        if self.db is None:
            return None
        try:
            return await self._coll('pr_files').find_one(
                {"owner": owner, "repo": repo, "pr_number": pr_number}, {"_id": 0}
            )
        except Exception as e:
            logger.error(f"获取 PR 变更文件失败: {e}")
            return None

    async def get_code_change_heatmap(self, owner: str, repo: str,
                                       start_date: str = None, end_date: str = None,
                                       top_n: int = 50) -> Dict[str, Any]:
        """
        生成代码变更热力图数据
        聚合 pr_files 中的文件变更频率和规模
        """
        if self.db is None:
            return {"error": "数据库未连接"}
        try:
            # 获取所有 pr_files 文档，按时间过滤
            query = {"owner": owner, "repo": repo}

            if start_date or end_date:
                # 按关联 PR 的创建时间过滤
                pr_query = {"owner": owner, "repo": repo}
                if start_date:
                    pr_query["data.created_at"] = {"$gte": start_date}
                if end_date:
                    time_cond = pr_query.get("data.created_at", {})
                    if isinstance(time_cond, dict):
                        time_cond["$lte"] = end_date
                    else:
                        time_cond = {"$gte": start_date, "$lte": end_date}
                    pr_query["data.created_at"] = time_cond

                valid_pr_numbers = set()
                async for doc in self._coll('pr_details').find(pr_query, {"pr_number": 1, "_id": 0}):
                    valid_pr_numbers.add(doc["pr_number"])
                query["pr_number"] = {"$in": list(valid_pr_numbers)}

            docs = await self._coll('pr_files').find(query, {"_id": 0}).to_list(length=None)

            if not docs:
                return {
                    "owner": owner, "repo": repo,
                    "files": [], "directories": [], "total_prs": 0,
                    "generated_at": datetime.now().isoformat(),
                }

            # 按文件聚合变更统计
            file_stats = {}
            dir_stats = {}
            pr_numbers = set()

            for doc in docs:
                pr_num = doc.get("pr_number")
                pr_numbers.add(pr_num)
                for f in doc.get("data", []):
                    filename = f.get("filename", "")
                    if not filename:
                        continue
                    additions = f.get("additions", 0)
                    deletions = f.get("deletions", 0)
                    changes = f.get("changes", 0)

                    # 文件级聚合
                    if filename not in file_stats:
                        file_stats[filename] = {
                            "filename": filename,
                            "change_count": 0, "total_additions": 0, "total_deletions": 0,
                            "total_changes": 0, "pr_numbers": [],
                        }
                    entry = file_stats[filename]
                    entry["change_count"] += 1
                    entry["total_additions"] += additions
                    entry["total_deletions"] += deletions
                    entry["total_changes"] += changes
                    if pr_num not in entry["pr_numbers"]:
                        entry["pr_numbers"].append(pr_num)

                    # 目录级聚合
                    parts = filename.split("/")
                    for depth in range(1, len(parts)):
                        dir_path = "/".join(parts[:depth]) + "/"
                        if dir_path not in dir_stats:
                            dir_stats[dir_path] = {
                                "directory": dir_path,
                                "change_count": 0, "total_additions": 0, "total_deletions": 0,
                                "total_changes": 0, "file_count": 0,
                            }
                            d_entry = dir_stats[dir_path]
                        else:
                            d_entry = dir_stats[dir_path]
                        d_entry["change_count"] += 1
                        d_entry["total_additions"] += additions
                        d_entry["total_deletions"] += deletions
                        d_entry["total_changes"] += changes

            # 去重目录文件计数
            for d, entry in dir_stats.items():
                unique_files = set()
                for doc2 in docs:
                    for f2 in doc2.get("data", []):
                        fn = f2.get("filename", "")
                        if fn.startswith(d):
                            unique_files.add(fn)
                entry["file_count"] = len(unique_files)

            # 排序取 top
            sorted_files = sorted(file_stats.values(), key=lambda x: x["change_count"], reverse=True)[:top_n]
            sorted_dirs = sorted(dir_stats.values(), key=lambda x: x["change_count"], reverse=True)[:top_n]

            # 计算热度值（归一化到 0-100）
            max_file_changes = sorted_files[0]["change_count"] if sorted_files else 1
            max_dir_changes = sorted_dirs[0]["change_count"] if sorted_dirs else 1

            for f in sorted_files:
                f["heat"] = round(f["change_count"] / max_file_changes * 100, 1)
            for d in sorted_dirs:
                d["heat"] = round(d["change_count"] / max_dir_changes * 100, 1)

            return {
                "owner": owner, "repo": repo,
                "files": sorted_files, "directories": sorted_dirs,
                "total_prs": len(pr_numbers),
                "total_files": len(file_stats), "total_dirs": len(dir_stats),
                "generated_at": datetime.now().isoformat(),
            }
        except Exception as e:
            logger.error(f"生成代码变更热力图失败: {e}")
            return {"error": str(e)}

    # ====================
    # 代码变更深度分析 + 阶段性洞察
    # ====================

    @staticmethod
    @staticmethod
    def _classify_change(pr_title: str, pr_body: str, filenames: List[str], labels: List[str]) -> str:
        """
        基于 PR 标题、body、文件路径和标签分类变更类型
        返回: feature / bugfix / refactor / docs / test / ci / perf / security / other
        """
        import re
        text = f"{pr_title} {pr_body}".lower()
        all_files = " ".join(filenames).lower()
        all_labels = " ".join(labels).lower()

        # 安全修复（最高优先级）
        sec_keywords = ["cve", "vulnerability", "xss", "csrf", "injection", "sanitize",
                        "privilege escalation", "security fix", "security patch", "auth bypass"]
        sec_labels = ["security", "type:security", "kind/security", "vulnerability"]
        if any(k in text for k in sec_keywords) or any(k in all_labels for k in sec_labels):
            return "security"

        # CI/构建
        ci_keywords = ["ci", "build", "pipeline", "workflow", "docker", "deploy", "makefile", "cmake", "jenkins", "github-actions", "gitlab-ci"]
        ci_files = [".github/workflows/", "Dockerfile", "docker-compose", "Jenkinsfile", ".gitlab-ci.yml", "Makefile", "CMakeLists"]
        if any(k in text for k in ci_keywords) or any(k in all_labels for k in ci_keywords) or any(f.startswith(tuple(ci_files)) or f in ci_files for f in filenames):
            return "ci"

        # 测试
        test_keywords = ["test", "spec", "fixture", "mock", "coverage", "unittest", "pytest", "jest"]
        test_files = ["test/", "tests/", "spec/", "__test__", "_test.", ".test.", ".spec.", ".test.ts", ".spec.ts"]
        if any(k in text for k in test_keywords) or any(f.startswith(tuple(test_files)) or any(s in f for s in test_files) for f in filenames):
            return "test"

        # 文档
        doc_keywords = ["doc", "readme", "changelog", "license", "contributing"]
        if any(k in text for k in doc_keywords) or any(f.startswith(tuple(["docs/", "doc/"])) or f.lower() in ["readme.md", "changelog.md", "license"] for f in filenames):
            return "docs"

        # Bug 修复
        bug_keywords = ["fix", "bug", "issue", "patch", "hotfix", "revert", "crash", "error", "fault", "defect"]
        bug_labels = ["bug", "type:bug", "kind/bug", "priority/critical"]
        if any(k in text for k in bug_keywords) or any(k in all_labels for k in bug_labels):
            return "bugfix"

        # 性能优化
        perf_keywords = ["perf", "optim", "speed", "memory", "alloc", "cache", "lazy", "benchmark", "n+1", "slow"]
        if any(k in text for k in perf_keywords):
            return "perf"

        # 重构
        refactor_keywords = ["refactor", "clean", "restructure", "reorg", "move", "rename", "deprecat", "remove dead", "simplify"]
        refactor_labels = ["refactor", "type:refactor", "kind/refactor"]
        if any(k in text for k in refactor_keywords) or any(k in all_labels for k in refactor_labels):
            return "refactor"

        # 新功能
        feature_keywords = ["feat", "add", "new", "implement", "support", "introduc", "create", "enabl"]
        feature_labels = ["feature", "enhancement", "type:feature", "kind/feature"]
        if any(k in text for k in feature_keywords) or any(k in all_labels for k in feature_labels):
            return "feature"

        return "other"

    @staticmethod
    def _classify_scope(filenames: List[str]) -> str:
        """识别变更影响范围: frontend / backend / infra / docs / fullstack"""
        if not filenames:
            return "unknown"
        scopes = set()
        for fn in filenames:
            fl = fn.lower()
            if any(s in fl for s in ["src/components/", "src/views/", "src/pages/", ".vue", ".jsx", ".tsx",
                                     "static/", "public/", "assets/css", ".css", ".scss", ".less", ".html"]):
                scopes.add("frontend")
            elif any(s in fl for s in ["src/api/", "src/services/", "src/models/", "app/", "server/",
                                       "lib/", "internal/", "pkg/", "cmd/", ".py", ".go", ".rs", ".java"]):
                scopes.add("backend")
            elif any(s in fl for s in [".github/", "dockerfile", "docker-compose", "k8s/", "terraform/",
                                       "ansible/", ".tf", ".yaml", ".yml", "Makefile", "CMakeLists"]):
                scopes.add("infra")
            elif any(s in fl for s in ["docs/", "readme", "changelog", ".md", ".rst"]):
                scopes.add("docs")
        if len(scopes) == 1:
            return scopes.pop()
        elif scopes >= {"frontend", "backend"}:
            return "fullstack"
        elif scopes:
            return sorted(scopes)[0]
        return "unknown"

    @staticmethod
    def _classify_size(additions: int, deletions: int, changed_files: int) -> str:
        """PR 体积分类: S / M / L / XL"""
        total = additions + deletions
        if total <= 50 and changed_files <= 3:
            return "S"
        elif total <= 300 and changed_files <= 10:
            return "M"
        elif total <= 1000 and changed_files <= 30:
            return "L"
        else:
            return "XL"

    @staticmethod
    def _detect_breaking_change(pr_title: str, pr_body: str, filenames: List[str]) -> bool:
        """检测是否包含 breaking change"""
        import re
        text = f"{pr_title} {pr_body}".lower()
        # Conventional Commits breaking: feat! or BREAKING CHANGE in body
        if re.search(r'(!:|breaking\s+change|breaking-change)', text):
            return True
        # 删除公共 API 文件
        public_paths = ["api/", "public/", "exports/", "index.ts", "index.js", "__init__.py", "mod.rs"]
        for fn in filenames:
            if any(p in fn for p in public_paths):
                return True
        return False

    @staticmethod
    def _classify_file_type(filename: str) -> str:
        """按文件扩展名分类文件类型"""
        ext_map = {
            ".py": "python", ".js": "javascript", ".ts": "typescript", ".tsx": "typescript",
            ".jsx": "javascript", ".java": "java", ".go": "go", ".rs": "rust",
            ".c": "c", ".cpp": "cpp", ".h": "c", ".hpp": "cpp", ".cu": "cuda", ".cuh": "cuda",
            ".rb": "ruby", ".php": "php", ".swift": "swift", ".kt": "kotlin",
            ".scala": "scala", ".cs": "csharp", ".m": "objc", ".mm": "objc",
            ".css": "style", ".scss": "style", ".less": "style", ".html": "markup",
            ".xml": "markup", ".yaml": "config", ".yml": "config", ".json": "config",
            ".toml": "config", ".ini": "config", ".cfg": "config", ".conf": "config",
            ".sh": "script", ".bash": "script", ".zsh": "script",
            ".sql": "database", ".proto": "protobuf",
            ".md": "docs", ".rst": "docs", ".txt": "docs",
        }
        for ext, lang in ext_map.items():
            if filename.endswith(ext):
                return lang
        return "other"

    @staticmethod
    def _analyze_diff_content(patch: str, filename: str) -> Dict[str, Any]:
        """
        解析单个文件的 diff/patch 内容，提取代码变更语义
        返回变更模式、关键函数/类变更、import 变更、重构模式、API 变更等
        """
        import re
        if not patch or not isinstance(patch, str):
            return {"change_patterns": [], "affected_symbols": [], "import_changes": [], "line_stats": {}, "refactor_patterns": [], "api_changes": []}

        lines = patch.split('\n')
        added_lines = [l[1:] for l in lines if l.startswith('+') and not l.startswith('+++')]
        removed_lines = [l[1:] for l in lines if l.startswith('-') and not l.startswith('---')]

        line_stats = {
            "added": len(added_lines),
            "removed": len(removed_lines),
            "net_change": len(added_lines) - len(removed_lines),
        }

        change_patterns = []
        affected_symbols = []
        import_changes = []
        refactor_patterns = []
        api_changes = []

        all_added = '\n'.join(added_lines)
        all_removed = '\n'.join(removed_lines)

        # 函数/类定义关键词
        fn_kws = ['def ', 'function ', 'func ', 'fn ', 'pub fn ', 'async def ', 'async fn ',
                  'pub async fn ', 'static ', 'private ', 'protected ', 'public ']
        cls_kws = ['class ', 'struct ', 'interface ', 'enum ', 'type ', 'trait ', 'impl ']

        # 1. 新增/删除 函数/类/装饰器
        for line in added_lines:
            stripped = line.strip()
            if any(stripped.startswith(kw) for kw in fn_kws):
                fn_name = stripped.split('(')[0].split()[-1] if '(' in stripped else stripped.split()[-1]
                affected_symbols.append({"symbol": fn_name, "type": "function_added", "line": stripped[:100]})
                # 检测 API 变更（public 方法签名变更）
                if any(stripped.startswith(kw) for kw in ['pub fn ', 'pub async fn ', 'def ', 'public ', 'async def ']):
                    api_changes.append({"type": "api_added", "symbol": fn_name, "line": stripped[:80]})
            elif any(stripped.startswith(kw) for kw in cls_kws):
                cls_name = stripped.split('(')[0].split()[-1].rstrip(':').rstrip('{') if '(' in stripped else stripped.split()[-1].rstrip(':').rstrip('{')
                affected_symbols.append({"symbol": cls_name, "type": "class_added", "line": stripped[:100]})
            elif stripped.startswith('@'):
                affected_symbols.append({"symbol": stripped[:50], "type": "decorator_added", "line": stripped[:100]})

        for line in removed_lines:
            stripped = line.strip()
            if any(stripped.startswith(kw) for kw in fn_kws):
                fn_name = stripped.split('(')[0].split()[-1] if '(' in stripped else stripped.split()[-1]
                affected_symbols.append({"symbol": fn_name, "type": "function_removed", "line": stripped[:100]})
                if any(stripped.startswith(kw) for kw in ['pub fn ', 'pub async fn ', 'def ', 'public ', 'async def ']):
                    api_changes.append({"type": "api_removed", "symbol": fn_name, "line": stripped[:80]})
            elif any(stripped.startswith(kw) for kw in cls_kws):
                cls_name = stripped.split('(')[0].split()[-1].rstrip(':').rstrip('{') if '(' in stripped else stripped.split()[-1].rstrip(':').rstrip('{')
                affected_symbols.append({"symbol": cls_name, "type": "class_removed", "line": stripped[:100]})

        # 2. Import 变更
        import_keywords = ['import ', 'from ', 'require(', 'use ', '#include', 'using ']
        for line in added_lines:
            stripped = line.strip()
            if any(stripped.startswith(kw) for kw in import_keywords):
                import_changes.append({"change": "added", "line": stripped[:80]})
        for line in removed_lines:
            stripped = line.strip()
            if any(stripped.startswith(kw) for kw in import_keywords):
                import_changes.append({"change": "removed", "line": stripped[:80]})

        # 3. 基本变更模式
        if len(added_lines) > 0 and len(removed_lines) == 0:
            change_patterns.append("pure_addition")
        elif len(removed_lines) > 0 and len(added_lines) == 0:
            change_patterns.append("pure_deletion")
        else:
            change_patterns.append("modification")

        # 4. 语义变更模式
        if 'TODO' in all_added or 'FIXME' in all_added or 'HACK' in all_added:
            change_patterns.append("adds_todo")
        if 'raise ' in all_added or 'throw ' in all_added or 'panic!' in all_added:
            change_patterns.append("adds_error_handling")
        if 'log.' in all_added or 'logger.' in all_added or 'console.log' in all_added or 'println!' in all_added or 'print(' in all_added:
            change_patterns.append("adds_logging")
        if 'assert' in all_added or 'expect' in all_added:
            change_patterns.append("adds_assertion")
        if any(kw in all_added for kw in ['// ', '# ', '/*', '"""', "'''"]):
            if not any(kw in all_added for kw in ['def ', 'class ', 'function ', 'if ']):
                change_patterns.append("adds_comments_only")

        # 安全相关变更
        sec_patterns = ['sanitize', 'escape', 'encrypt', 'decrypt', 'hashlib', 'bcrypt',
                        'password', 'token', 'auth', 'permission', 'csrf', 'xss', 'injection']
        if any(p in all_added.lower() for p in sec_patterns) or any(p in all_removed.lower() for p in sec_patterns):
            change_patterns.append("security_related")

        # 5. 重构模式检测
        # 重命名：同文件中删除函数+添加函数，且行数相近
        added_fns = [s for s in affected_symbols if s["type"] == "function_added"]
        removed_fns = [s for s in affected_symbols if s["type"] == "function_removed"]
        if added_fns and removed_fns and len(added_fns) == len(removed_fns):
            refactor_patterns.append("rename_function")

        # 移动文件：文件路径含 move/rename
        if any(kw in filename.lower() for kw in ['move', 'rename', 'migrate']):
            refactor_patterns.append("move_file")

        # 提取方法：删除大函数 + 添加多个小函数
        if removed_fns and len(added_fns) >= 2:
            refactor_patterns.append("extract_method")

        # 内联/简化：删除函数多于添加
        if len(removed_fns) > len(added_fns) and len(removed_fns) >= 2:
            refactor_patterns.append("inline_or_simplify")

        # 仅修改函数签名（参数变更）
        added_fn_names = {s["symbol"] for s in added_fns}
        removed_fn_names = {s["symbol"] for s in removed_fns}
        common_names = added_fn_names & removed_fn_names
        if common_names:
            refactor_patterns.append("signature_change")

        # 6. API 签名变更检测（参数增删）
        for name in common_names:
            added_sig = next((s["line"] for s in added_fns if s["symbol"] == name), "")
            removed_sig = next((s["line"] for s in removed_fns if s["symbol"] == name), "")
            if added_sig and removed_sig and added_sig != removed_sig:
                api_changes.append({"type": "signature_modified", "symbol": name, "before": removed_sig[:80], "after": added_sig[:80]})

        return {
            "change_patterns": change_patterns,
            "affected_symbols": affected_symbols[:30],
            "import_changes": import_changes[:15],
            "line_stats": line_stats,
            "refactor_patterns": refactor_patterns,
            "api_changes": api_changes[:10],
        }

    @staticmethod
    def _summarize_diff_analysis(file_analyses: List[Dict]) -> Dict[str, Any]:
        """汇总多个文件的 diff 分析结果，包含重构模式和 API 变更"""
        total_symbols = []
        total_imports = []
        pattern_counts = {}
        refactor_counts = {}
        api_changes_all = []
        total_added = 0
        total_removed = 0

        for fa in file_analyses:
            total_symbols.extend(fa.get("affected_symbols", []))
            total_imports.extend(fa.get("import_changes", []))
            for p in fa.get("change_patterns", []):
                pattern_counts[p] = pattern_counts.get(p, 0) + 1
            for rp in fa.get("refactor_patterns", []):
                refactor_counts[rp] = refactor_counts.get(rp, 0) + 1
            api_changes_all.extend(fa.get("api_changes", []))
            ls = fa.get("line_stats", {})
            total_added += ls.get("added", 0)
            total_removed += ls.get("removed", 0)

        symbols_by_type = {}
        for sym in total_symbols:
            t = sym.get("type", "unknown")
            if t not in symbols_by_type:
                symbols_by_type[t] = []
            symbols_by_type[t].append(sym.get("symbol", ""))

        added_imports = [ic["line"] for ic in total_imports if ic.get("change") == "added"]
        removed_imports = [ic["line"] for ic in total_imports if ic.get("change") == "removed"]

        return {
            "total_added_lines": total_added,
            "total_removed_lines": total_removed,
            "symbols_by_type": {k: list(set(v))[:10] for k, v in symbols_by_type.items()},
            "added_imports": list(set(added_imports))[:10],
            "removed_imports": list(set(removed_imports))[:10],
            "pattern_counts": pattern_counts,
            "refactor_counts": refactor_counts,
            "api_changes": api_changes_all[:10],
        }

    async def get_code_change_insight(self, owner: str, repo: str,
                                       start_date: str = None, end_date: str = None,
                                       granularity: str = "week") -> Dict[str, Any]:
        """
        生成代码变更深度洞察报告
        按时间分桶，对每个阶段分类变更内容，生成阶段性摘要
        """
        if self.db is None:
            return {"error": "数据库未连接"}
        try:
            now = datetime.now()
            if not end_date:
                end_date = now.strftime("%Y-%m-%d")
            if not start_date:
                start_date = (now - timedelta(days=30)).strftime("%Y-%m-%d")

            # 获取时间范围内的 PR 详情
            # 兼容两种数据格式: data.detail.xxx (NVIDIA/cccl) 和 data.xxx (test-org)
            # 先用顶层 created_at 做粗筛（记录入库时间），再用 PR 的 created_at 精确过滤
            pr_query = {"owner": owner, "repo": repo}
            pr_docs = await self._coll('pr_details').find(pr_query, {"_id": 0}).to_list(length=None)

            # 获取对应的 pr_files
            pr_numbers = [doc["pr_number"] for doc in pr_docs]
            files_map = {}
            if pr_numbers:
                async for fdoc in self._coll('pr_files').find(
                    {"owner": owner, "repo": repo, "pr_number": {"$in": pr_numbers}},
                    {"pr_number": 1, "data": 1, "_id": 0}
                ):
                    files_map[fdoc["pr_number"]] = fdoc.get("data", [])

            # 分类每个 PR
            classified_prs = []
            category_counts = {}
            file_type_counts = {}
            total_additions = 0
            total_deletions = 0

            for doc in pr_docs:
                pr_num = doc.get("pr_number")
                pr_data = doc.get("data", {})

                # 兼容两种数据格式: data.detail 存在则取 detail，否则直接用 data
                detail = pr_data.get("detail") if isinstance(pr_data.get("detail"), dict) else None
                source = detail if detail else pr_data

                title = source.get("title", "")
                body = source.get("body", "") or ""
                labels = [l.get("name", "") for l in source.get("labels", []) if isinstance(l, dict)]
                created_at = source.get("created_at", "")
                user_info = source.get("user")
                if isinstance(user_info, dict):
                    user = user_info.get("login", "")
                elif isinstance(user_info, str):
                    user = user_info
                else:
                    user = ""
                state = source.get("state", "")
                additions = source.get("additions", 0) or 0
                deletions = source.get("deletions", 0) or 0
                merged = source.get("merged", False)

                # 按日期精确过滤（PR 的 created_at）
                if created_at:
                    pr_date = created_at[:10]
                    if pr_date < start_date or pr_date > end_date:
                        continue

                # 获取文件列表
                pr_files = files_map.get(pr_num, [])
                filenames = [f.get("filename", "") for f in pr_files if isinstance(f, dict)]

                # 分析 diff 内容
                file_analyses = []
                for f in pr_files:
                    if isinstance(f, dict) and f.get("patch"):
                        fa = self._analyze_diff_content(f["patch"], f.get("filename", ""))
                        fa["filename"] = f.get("filename", "")
                        file_analyses.append(fa)
                diff_summary = self._summarize_diff_analysis(file_analyses) if file_analyses else None

                # 分类
                category = self._classify_change(title, body, filenames, labels)
                file_types = [self._classify_file_type(fn) for fn in filenames]
                scope = self._classify_scope(filenames)
                size = self._classify_size(additions, deletions, len(filenames))
                breaking = self._detect_breaking_change(title, body, filenames)

                total_additions += additions
                total_deletions += deletions

                # 统计分类
                category_counts[category] = category_counts.get(category, 0) + 1
                for ft in file_types:
                    file_type_counts[ft] = file_type_counts.get(ft, 0) + 1

                # 风险指标
                risk_flags = []
                if size == "XL":
                    risk_flags.append("xl_pr")
                if len(filenames) > 20:
                    risk_flags.append("too_many_files")
                if breaking:
                    risk_flags.append("breaking_change")
                if additions > 500 and deletions < 10:
                    risk_flags.append("large_addition")

                classified_prs.append({
                    "pr_number": pr_num, "title": title, "category": category,
                    "user": user, "state": state, "merged": merged,
                    "created_at": created_at,
                    "additions": additions, "deletions": deletions,
                    "changed_files": len(filenames),
                    "file_types": list(set(file_types)),
                    "scope": scope, "size": size, "breaking": breaking,
                    "risk_flags": risk_flags,
                    "diff_summary": diff_summary,
                })

            # 按时间分桶
            periods = self._bucket_prs_by_time(classified_prs, granularity)

            # 汇总所有 PR 的 diff 分析
            all_diff_summaries = [pr.get("diff_summary") for pr in classified_prs if pr.get("diff_summary")]
            overall_diff = self._summarize_diff_analysis(
                [fa for ds in all_diff_summaries for fa in ds.get("file_analyses", [])]
            ) if all_diff_summaries else None
            # 直接从 classified_prs 的 diff_summary 聚合
            overall_diff_agg = self._aggregate_diff_summaries(all_diff_summaries)

            # 生成阶段性摘要
            for period in periods:
                period["summary"] = self._generate_period_summary(period)

            # 计算阶段间环比趋势
            period_trends = self._compute_period_trends(periods)

            # 工程洞察：scope 分布、size 分布、风险汇总、文件耦合、变更速率
            scope_counts = {}
            size_counts = {}
            risk_summary = {}
            file_coupling = {}  # 文件同现次数
            for pr in classified_prs:
                s = pr.get("scope", "unknown")
                scope_counts[s] = scope_counts.get(s, 0) + 1
                sz = pr.get("size", "M")
                size_counts[sz] = size_counts.get(sz, 0) + 1
                for rf in pr.get("risk_flags", []):
                    risk_summary[rf] = risk_summary.get(rf, 0) + 1

            # 文件耦合分析（同 PR 中一起变更的文件对）
            file_pr_count = {}  # 每个文件被多少 PR 变更
            for pr in classified_prs:
                pr_files_list = []
                for f_doc in files_map.get(pr.get("pr_number"), []):
                    if isinstance(f_doc, dict):
                        fn = f_doc.get("filename", "")
                        if fn:
                            pr_files_list.append(fn)
                            file_pr_count[fn] = file_pr_count.get(fn, 0) + 1
                # 同 PR 文件对（最多取 5 个文件避免组合爆炸）
                for i in range(min(len(pr_files_list), 5)):
                    for j in range(i + 1, min(len(pr_files_list), 5)):
                        pair = tuple(sorted([pr_files_list[i], pr_files_list[j]]))
                        file_coupling[pair] = file_coupling.get(pair, 0) + 1

            # 高耦合文件对（同现 >= 2 次）
            high_coupling = [
                {"files": list(pair), "count": cnt}
                for pair, cnt in sorted(file_coupling.items(), key=lambda x: x[1], reverse=True)
                if cnt >= 2
            ][:15]

            # 高 churn 文件（被最多 PR 变更）
            high_churn_files = [
                {"filename": fn, "pr_count": cnt}
                for fn, cnt in sorted(file_pr_count.items(), key=lambda x: x[1], reverse=True)
            ][:15]

            # 变更速率（PR/天）
            total_days = max((datetime.fromisoformat(end_date) - datetime.fromisoformat(start_date)).days, 1)
            pr_velocity = round(len(classified_prs) / total_days, 2)

            # 整体摘要
            overall_summary = self._generate_overall_summary(
                classified_prs, category_counts, file_type_counts,
                total_additions, total_deletions, start_date, end_date,
                scope_counts, size_counts, risk_summary, pr_velocity
            )

            return {
                "owner": owner, "repo": repo,
                "start_date": start_date, "end_date": end_date,
                "granularity": granularity,
                "total_prs": len(classified_prs),
                "category_counts": category_counts,
                "file_type_counts": dict(sorted(file_type_counts.items(), key=lambda x: x[1], reverse=True)[:15]),
                "scope_counts": scope_counts,
                "size_counts": size_counts,
                "risk_summary": risk_summary,
                "total_additions": total_additions,
                "total_deletions": total_deletions,
                "pr_velocity": pr_velocity,
                "high_churn_files": high_churn_files,
                "high_coupling": high_coupling,
                "periods": periods,
                "period_trends": period_trends,
                "classified_prs": classified_prs,
                "overall_summary": overall_summary,
                "diff_analysis": overall_diff_agg,
                "generated_at": now.isoformat(),
            }
        except Exception as e:
            logger.error(f"生成代码变更洞察失败: {e}")
            return {"error": str(e)}

    async def ai_analyze_code_changes(self, owner: str, repo: str,
                                       start_date: str = None, end_date: str = None,
                                       focus: str = "overview") -> Dict[str, Any]:
        """
        使用 LLM 对代码变更进行深度语义分析
        focus: overview(整体分析) / risk(风险分析) / architecture(架构影响) / quality(代码质量)
        """
        if self.db is None:
            return {"error": "数据库未连接"}

        # 先获取洞察数据作为 LLM 输入
        insight = await self.get_code_change_insight(owner, repo, start_date, end_date, "week")
        if insight.get("error") or insight.get("total_prs", 0) == 0:
            return {"error": insight.get("error", "无变更数据，无法分析")}

        # 构建发给 LLM 的变更摘要
        pr_summaries = []
        for pr in insight.get("classified_prs", [])[:10]:
            summary = f"PR #{pr['pr_number']}: {pr['title']}\n"
            summary += f"  分类: {pr['category']}, 范围: {pr.get('scope','?')}, 体积: {pr.get('size','?')}"
            summary += f", +{pr['additions']}/-{pr['deletions']}, {pr['changed_files']}文件\n"
            if pr.get('risk_flags'):
                summary += f"  风险: {', '.join(pr['risk_flags'])}\n"
            ds = pr.get('diff_summary', {})
            if ds:
                syms = ds.get('symbols_by_type', {})
                if syms:
                    sym_parts = []
                    for t, names in syms.items():
                        sym_parts.append(f"{t}: {', '.join(names[:3])}")
                    summary += f"  符号变更: {'; '.join(sym_parts)}\n"
                patterns = ds.get('pattern_counts', {})
                if patterns:
                    summary += f"  变更模式: {', '.join(f'{k}×{v}' for k,v in list(patterns.items())[:5])}\n"
                refactors = ds.get('refactor_counts', {})
                if refactors:
                    summary += f"  重构: {', '.join(f'{k}×{v}' for k,v in refactors.items())}\n"
                apis = ds.get('api_changes', [])
                if apis:
                    summary += f"  API变更: {len(apis)}处\n"
            pr_summaries.append(summary)

        # 构建 LLM prompt
        focus_prompts = {
            "overview": "请从以下维度进行综合分析：\n1. 变更意图：这批变更整体在做什么？解决什么问题？\n2. 变更质量：代码变更是否合理？有无过度工程或遗漏？\n3. 风险评估：有哪些潜在风险？哪些变更需要重点关注？\n4. 架构影响：对项目架构有什么影响？是否引入新的依赖或耦合？\n5. 改进建议：有什么可以改进的地方？",
            "risk": "请重点进行风险分析：\n1. 哪些变更可能引入 Bug？为什么？\n2. 是否有破坏性变更？影响范围？\n3. 大型 PR 是否可以拆分？\n4. 是否有安全相关的变更需要特别注意？\n5. 测试覆盖是否充分？\n6. 给出风险等级（高/中/低）和具体建议",
            "architecture": "请重点分析架构影响：\n1. 变更对模块划分有什么影响？\n2. 是否引入了新的耦合？\n3. 文件变更模式反映了什么架构特征？\n4. 是否有架构层面的技术债？\n5. 对未来扩展性的影响？",
            "quality": "请重点分析代码质量：\n1. 变更的代码质量如何？\n2. 是否有代码异味（code smell）？\n3. 重构是否充分？\n4. 是否有重复代码或可以抽象的地方？\n5. 错误处理和日志是否完善？",
        }

        system_prompt = """你是一位资深软件工程师和代码审查专家，正在分析一个项目的代码变更。
请基于提供的变更数据，给出专业、具体、有洞察力的分析。
避免泛泛而谈，要结合具体变更内容给出判断。
用中文回答，使用 Markdown 格式。"""

        user_prompt = f"""## 项目: {owner}/{repo}
## 时间范围: {insight.get('start_date')} ~ {insight.get('end_date')}

## 统计概览
- PR 总数: {insight.get('total_prs')}
- 变更类型: {insight.get('category_counts')}
- 影响范围: {insight.get('scope_counts')}
- PR 体积: {insight.get('size_counts')}
- 风险指标: {insight.get('risk_summary')}
- 变更速率: {insight.get('pr_velocity')} PR/天

## 高 Churn 文件
{chr(10).join(f"- {f['filename']} ({f['pr_count']} PRs)" for f in insight.get('high_churn_files', [])[:10])}

## 高耦合文件对
{chr(10).join(f"- {c['files'][0]} ↔ {c['files'][1]} ({c['count']}次)" for c in insight.get('high_coupling', [])[:8])}

## 各 PR 变更详情
{chr(10).join(pr_summaries)}

## 分析要求
{focus_prompts.get(focus, focus_prompts['overview'])}"""

        # 调用 LLM
        try:
            from workflow.config import workflow_config
            if not workflow_config.ai_ready:
                return {"error": "LLM 未配置或初始化失败，请先配置 API Key 并重启服务", "ai_ready": False}

            import asyncio
            try:
                response = await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: workflow_config.llm.invoke([
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ])
                    ),
                    timeout=120.0
                )
            except asyncio.TimeoutError:
                return {"error": "LLM 请求超时（60秒），请检查 LLM 服务是否可达、Base URL 是否正确", "ai_ready": True}

            content = response.content if hasattr(response, 'content') else str(response)
            if not content or not content.strip():
                return {"error": "LLM 返回空内容，请检查模型是否正常", "ai_ready": True}

            return {
                "owner": owner, "repo": repo,
                "focus": focus,
                "start_date": insight.get("start_date"),
                "end_date": insight.get("end_date"),
                "analysis": content,
                "total_prs_analyzed": insight.get("total_prs", 0),
                "ai_ready": True,
                "generated_at": datetime.now().isoformat(),
            }
        except ImportError:
            return {"error": "LLM 模块未安装", "ai_ready": False}
        except Exception as e:
            err_msg = str(e)
            # 提供更友好的错误提示
            if "Connection" in err_msg:
                err_msg = f"LLM 连接失败，请检查 Base URL 是否正确、LLM 服务是否可达\n详细信息: {err_msg}"
            elif "401" in err_msg or "Unauthorized" in err_msg:
                err_msg = "LLM API Key 认证失败（401），请检查 API Key 是否正确"
            elif "403" in err_msg:
                err_msg = "LLM API 访问被拒绝（403），请检查 API Key 权限"
            elif "404" in err_msg:
                err_msg = "LLM API 端点不存在（404），请检查 Base URL 和模型名称是否正确"
            elif "429" in err_msg:
                err_msg = "LLM API 请求频率超限（429），请稍后重试"
            logger.error(f"AI 分析代码变更失败: {e}")
            return {"error": err_msg, "ai_ready": False}

    @staticmethod
    def _bucket_prs_by_time(classified_prs: List[Dict], granularity: str) -> List[Dict[str, Any]]:
        """按时间分桶，并聚合每阶段的 diff 分析、文件类型、贡献者分布"""
        buckets = {}
        for pr in classified_prs:
            created = pr.get("created_at", "")[:10]
            if not created:
                continue
            try:
                dt = datetime.fromisoformat(created)
            except ValueError:
                continue

            if granularity == "month":
                key = dt.strftime("%Y-%m")
            elif granularity == "week":
                key = f"{dt.year}-W{dt.isocalendar()[1]:02d}"
            else:
                key = created

            if key not in buckets:
                buckets[key] = {
                    "period": key, "prs": [],
                    "category_counts": {}, "additions": 0, "deletions": 0,
                    "file_type_counts": {}, "contributors": {},
                    "diff_summaries": [],
                }
            bucket = buckets[key]
            bucket["prs"].append(pr)
            bucket["additions"] += pr.get("additions", 0)
            bucket["deletions"] += pr.get("deletions", 0)
            cat = pr.get("category", "other")
            bucket["category_counts"][cat] = bucket["category_counts"].get(cat, 0) + 1

            # 聚合文件类型
            for ft in pr.get("file_types", []):
                bucket["file_type_counts"][ft] = bucket["file_type_counts"].get(ft, 0) + 1

            # 聚合贡献者
            user = pr.get("user", "")
            if user:
                bucket["contributors"][user] = bucket["contributors"].get(user, 0) + 1

            # 收集 diff_summary 用于阶段级聚合
            ds = pr.get("diff_summary")
            if ds:
                bucket["diff_summaries"].append(ds)

        # 为每个阶段生成聚合 diff 分析
        result = []
        for k in sorted(buckets.keys()):
            bucket = buckets[k]
            # 阶段级 diff 聚合
            if bucket["diff_summaries"]:
                bucket["diff_analysis"] = DatabaseService._aggregate_diff_summaries(bucket["diff_summaries"])
            else:
                bucket["diff_analysis"] = {}
            del bucket["diff_summaries"]

            # 贡献者排序取 Top
            bucket["top_contributors"] = sorted(
                bucket["contributors"].items(), key=lambda x: x[1], reverse=True
            )[:10]
            del bucket["contributors"]

            # 文件类型排序取 Top
            bucket["file_type_counts"] = dict(
                sorted(bucket["file_type_counts"].items(), key=lambda x: x[1], reverse=True)[:10]
            )

            result.append(bucket)

        return result

    @staticmethod
    def _generate_period_summary(period: Dict) -> str:
        """生成单个时间阶段的自然语言摘要，包含分类、文件类型、贡献者和 diff 分析概要"""
        prs = period.get("prs", [])
        cats = period.get("category_counts", {})
        additions = period.get("additions", 0)
        deletions = period.get("deletions", 0)
        period_key = period.get("period", "")
        file_types = period.get("file_type_counts", {})
        top_contributors = period.get("top_contributors", [])
        diff_analysis = period.get("diff_analysis", {})

        if not prs:
            return f"{period_key}: 无变更"

        cat_names = {
            "feature": "新功能", "bugfix": "Bug修复", "refactor": "重构",
            "docs": "文档", "test": "测试", "ci": "CI/构建", "perf": "性能优化", "other": "其他",
        }

        lines = [f"{period_key}: {len(prs)} 个 PR"]

        # 分类统计
        cat_parts = []
        for cat, count in sorted(cats.items(), key=lambda x: x[1], reverse=True):
            name = cat_names.get(cat, cat)
            cat_parts.append(f"{name} {count}")
        lines.append("变更类型：" + "、".join(cat_parts))

        # 代码变更量
        lines.append(f"代码变更：+{additions}/-{deletions}")

        # 涉及语言
        if file_types:
            top_ft = list(file_types.keys())[:5]
            lines.append("涉及语言：" + "、".join(top_ft))

        # 主要贡献者
        if top_contributors:
            contrib_str = "、".join(f"{u}({c})" for u, c in top_contributors[:5])
            lines.append(f"贡献者：{contrib_str}")

        # Diff 分析概要
        if diff_analysis:
            sym_parts = []
            for sym_type, syms in diff_analysis.get("symbols_by_type", {}).items():
                if syms:
                    sym_labels = {
                        "function_added": "新增函数", "function_removed": "删除函数",
                        "class_added": "新增类", "class_removed": "删除类",
                        "decorator_added": "新增装饰器",
                    }
                    label = sym_labels.get(sym_type, sym_type)
                    sym_parts.append(f"{label} {len(syms)}")
            if sym_parts:
                lines.append("符号变更：" + "、".join(sym_parts))

            patterns = diff_analysis.get("pattern_counts", {})
            if patterns:
                pat_str = "、".join(f"{k}×{v}" for k, v in sorted(patterns.items(), key=lambda x: x[1], reverse=True)[:5])
                lines.append(f"变更模式：{pat_str}")

        # 关键 PR 标题（最多 3 个）
        key_prs = []
        for pr in prs[:3]:
            title = pr.get("title", "")
            if title:
                key_prs.append(f"#{pr.get('pr_number', '?')} {title[:60]}")
        if key_prs:
            lines.append("关键 PR：" + "; ".join(key_prs))

        return "\n".join(lines)

    @staticmethod
    def _generate_overall_summary(prs: List[Dict], category_counts: Dict,
                                    file_type_counts: Dict, total_add: int, total_del: int,
                                    start_date: str, end_date: str,
                                    scope_counts: Dict = None, size_counts: Dict = None,
                                    risk_summary: Dict = None, pr_velocity: float = 0) -> str:
        """生成洞察驱动的整体摘要，突出异常、趋势和行动建议"""
        cat_names = {
            "feature": "新功能", "bugfix": "Bug修复", "refactor": "重构",
            "docs": "文档", "test": "测试", "ci": "CI/构建", "perf": "性能优化",
            "security": "安全修复", "other": "其他",
        }
        size_labels = {"S": "小型", "M": "中型", "L": "大型", "XL": "超大型"}
        risk_labels = {
            "xl_pr": "超大型PR", "too_many_files": "变更文件过多",
            "breaking_change": "破坏性变更", "large_addition": "大量新增代码",
        }

        lines = [f"📊 {start_date} ~ {end_date} 项目变更洞察"]
        lines.append(f"共 {len(prs)} 个 PR，+{total_add}/-{total_del} 行变更，变更速率 {pr_velocity} PR/天")

        # 分类统计
        cat_parts = []
        for cat, count in sorted(category_counts.items(), key=lambda x: x[1], reverse=True):
            name = cat_names.get(cat, cat)
            pct = round(count / len(prs) * 100) if prs else 0
            cat_parts.append(f"{name} {count}({pct}%)")
        lines.append("变更类型：" + "、".join(cat_parts))

        # Scope 分布
        if scope_counts:
            scope_parts = [f"{s} {c}" for s, c in sorted(scope_counts.items(), key=lambda x: x[1], reverse=True)]
            lines.append("影响范围：" + "、".join(scope_parts))

        # Size 分布
        if size_counts:
            size_parts = []
            for sz in ["S", "M", "L", "XL"]:
                if sz in size_counts:
                    size_parts.append(f"{size_labels[sz]} {size_counts[sz]}")
            lines.append("PR 体积：" + "、".join(size_parts))

        # Top 文件类型
        top_types = sorted(file_type_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        type_parts = [f"{t} {c}" for t, c in top_types]
        lines.append("涉及语言：" + "、".join(type_parts))

        # Top 贡献者
        user_counts = {}
        for pr in prs:
            user = pr.get("user", "")
            if user:
                user_counts[user] = user_counts.get(user, 0) + 1
        top_users = sorted(user_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        if top_users:
            user_parts = [f"{u}({c})" for u, c in top_users]
            lines.append("主要贡献者：" + "、".join(user_parts))

        # 风险预警
        if risk_summary:
            risk_parts = [f"{risk_labels.get(k, k)} {v}" for k, v in sorted(risk_summary.items(), key=lambda x: x[1], reverse=True)]
            lines.append("⚠️ 风险指标：" + "、".join(risk_parts))

        # 行动建议
        suggestions = []
        if risk_summary and risk_summary.get("xl_pr", 0) > 0:
            suggestions.append(f"有 {risk_summary['xl_pr']} 个超大型 PR，建议拆分为更小的变更以降低审查难度")
        if risk_summary and risk_summary.get("breaking_change", 0) > 0:
            suggestions.append(f"检测到 {risk_summary['breaking_change']} 个破坏性变更，需确认下游兼容性")
        if category_counts.get("bugfix", 0) > len(prs) * 0.3:
            suggestions.append("Bug 修复占比超过 30%，建议关注代码质量和测试覆盖率")
        if size_counts and size_counts.get("XL", 0) > len(prs) * 0.2:
            suggestions.append("超大型 PR 占比超过 20%，建议推行小 PR 策略")
        if scope_counts and scope_counts.get("fullstack", 0) > 0:
            suggestions.append(f"有 {scope_counts['fullstack']} 个全栈变更 PR，建议前后端分离提交")
        if pr_velocity > 5:
            suggestions.append(f"变更速率 {pr_velocity} PR/天 较高，确保 review 跟上节奏")

        if suggestions:
            lines.append("\n💡 行动建议：")
            for i, s in enumerate(suggestions, 1):
                lines.append(f"  {i}. {s}")

        return "\n".join(lines)

    @staticmethod
    def _aggregate_diff_summaries(summaries: List[Dict]) -> Dict[str, Any]:
        """聚合多个 PR 的 diff_summary 为整体 diff 分析"""
        if not summaries:
            return {}

        total_added = sum(s.get("total_added_lines", 0) for s in summaries)
        total_removed = sum(s.get("total_removed_lines", 0) for s in summaries)

        all_symbols = {}
        all_imports_added = []
        all_imports_removed = []
        all_patterns = {}

        for s in summaries:
            for sym_type, syms in s.get("symbols_by_type", {}).items():
                if sym_type not in all_symbols:
                    all_symbols[sym_type] = set()
                all_symbols[sym_type].update(syms)
            all_imports_added.extend(s.get("added_imports", []))
            all_imports_removed.extend(s.get("removed_imports", []))
            for p, cnt in s.get("pattern_counts", {}).items():
                all_patterns[p] = all_patterns.get(p, 0) + cnt

        return {
            "total_added_lines": total_added,
            "total_removed_lines": total_removed,
            "symbols_by_type": {k: sorted(list(v))[:10] for k, v in all_symbols.items()},
            "added_imports": sorted(list(set(all_imports_added)))[:15],
            "removed_imports": sorted(list(set(all_imports_removed)))[:15],
            "pattern_counts": dict(sorted(all_patterns.items(), key=lambda x: x[1], reverse=True)),
        }

    @staticmethod
    def _compute_period_trends(periods: List[Dict]) -> Dict[str, Any]:
        """计算阶段间环比趋势，包含 PR 数、增删行、分类占比的变化"""
        if len(periods) < 2:
            return {"trend_points": [], "insight": "阶段数不足，无法计算趋势"}

        trend_points = []
        all_categories = set()
        for p in periods:
            all_categories.update(p.get("category_counts", {}).keys())

        for i, period in enumerate(periods):
            point = {
                "period": period["period"],
                "pr_count": len(period.get("prs", [])),
                "additions": period.get("additions", 0),
                "deletions": period.get("deletions", 0),
                "net_change": period.get("additions", 0) - period.get("deletions", 0),
                "category_counts": period.get("category_counts", {}),
            }

            # 计算环比变化率
            if i > 0:
                prev = periods[i - 1]
                prev_pr_count = len(prev.get("prs", []))
                prev_add = prev.get("additions", 0)
                prev_del = prev.get("deletions", 0)

                point["pr_count_change"] = round(
                    (point["pr_count"] - prev_pr_count) / prev_pr_count * 100, 1
                ) if prev_pr_count > 0 else None
                point["additions_change"] = round(
                    (point["additions"] - prev_add) / prev_add * 100, 1
                ) if prev_add > 0 else None
                point["deletions_change"] = round(
                    (point["deletions"] - prev_del) / prev_del * 100, 1
                ) if prev_del > 0 else None

                # 分类占比变化
                cat_changes = {}
                for cat in all_categories:
                    cur_cnt = period.get("category_counts", {}).get(cat, 0)
                    prev_cnt = prev.get("category_counts", {}).get(cat, 0)
                    cur_total = point["pr_count"] if point["pr_count"] > 0 else 1
                    prev_total = prev_pr_count if prev_pr_count > 0 else 1
                    cur_pct = cur_cnt / cur_total
                    prev_pct = prev_cnt / prev_total
                    cat_changes[cat] = round((cur_pct - prev_pct) * 100, 1)
                point["category_pct_change"] = cat_changes
            else:
                point["pr_count_change"] = None
                point["additions_change"] = None
                point["deletions_change"] = None
                point["category_pct_change"] = {}

            trend_points.append(point)

        # 生成趋势洞察
        insights = []
        if len(trend_points) >= 2:
            last = trend_points[-1]
            if last.get("pr_count_change") is not None:
                if last["pr_count_change"] > 20:
                    insights.append(f"最近阶段 PR 数环比增长 {last['pr_count_change']}%，活跃度上升")
                elif last["pr_count_change"] < -20:
                    insights.append(f"最近阶段 PR 数环比下降 {abs(last['pr_count_change'])}%，活跃度降低")

            if last.get("additions_change") is not None and last["additions_change"] > 50:
                insights.append(f"新增代码量环比增长 {last['additions_change']}%，可能有大功能上线")

            # 检查分类占比显著变化
            cat_pct = last.get("category_pct_change", {})
            for cat, change in cat_pct.items():
                cat_names = {
                    "feature": "新功能", "bugfix": "Bug修复", "refactor": "重构",
                    "docs": "文档", "test": "测试", "ci": "CI/构建", "perf": "性能优化",
                }
                if abs(change) >= 10:
                    name = cat_names.get(cat, cat)
                    direction = "上升" if change > 0 else "下降"
                    insights.append(f"{name}占比{direction} {abs(change)}%")

        return {
            "trend_points": trend_points,
            "insight": "；".join(insights) if insights else "各指标环比变化平稳",
        }

    async def get_recent_activities(self, limit: int = 15) -> Dict[str, Any]:
        """获取最近活动时间线，合并 PR、评论、Issue 三种类型"""
        if self.db is None:
            return {"activities": [], "total": 0}
        try:
            collection_names = await self.db.list_collection_names()
            activities = []

            # PR 创建活动
            if 'pr_data' in collection_names:
                cursor = self._coll('pr_data').find(
                    {}, {"_id": 0, "owner": 1, "repo": 1, "number": 1, "title": 1, "user": 1, "state": 1, "created_at": 1}
                ).sort("created_at", -1).limit(limit)
                async for doc in cursor:
                    activities.append({
                        "type": "pr_created",
                        "owner": doc.get("owner", ""),
                        "repo": doc.get("repo", ""),
                        "number": doc.get("number"),
                        "title": doc.get("title", ""),
                        "user": doc.get("user", ""),
                        "state": doc.get("state", ""),
                        "created_at": doc.get("created_at", ""),
                    })

            # 评论活动
            if 'pr_comments' in collection_names:
                cursor = self._coll('pr_comments').find(
                    {}, {"_id": 0, "owner": 1, "repo": 1, "pr_number": 1, "user": 1, "body": 1, "created_at": 1}
                ).sort("created_at", -1).limit(limit)
                async for doc in cursor:
                    body = doc.get("body", "") or ""
                    activities.append({
                        "type": "comment",
                        "owner": doc.get("owner", ""),
                        "repo": doc.get("repo", ""),
                        "pr_number": doc.get("pr_number"),
                        "user": doc.get("user", ""),
                        "body_preview": body[:80] + ("..." if len(body) > 80 else ""),
                        "created_at": doc.get("created_at", ""),
                    })

            # Issue 活动
            if 'issues' in collection_names:
                cursor = self._coll('issues').find(
                    {}, {"_id": 0, "owner": 1, "repo": 1, "number": 1, "title": 1, "user": 1, "state": 1, "created_at": 1, "closed_at": 1}
                ).sort("created_at", -1).limit(limit)
                async for doc in cursor:
                    is_closed = doc.get("state") == "closed"
                    activities.append({
                        "type": "issue_closed" if is_closed else "issue_opened",
                        "owner": doc.get("owner", ""),
                        "repo": doc.get("repo", ""),
                        "number": doc.get("number"),
                        "title": doc.get("title", ""),
                        "user": doc.get("user", ""),
                        "created_at": doc.get("closed_at" if is_closed else "created_at", ""),
                    })

            # 按时间降序合并排序
            activities.sort(key=lambda x: x.get("created_at") or "", reverse=True)
            total = len(activities)
            activities = activities[:limit]

            return {"activities": activities, "total": total}
        except Exception as e:
            logger.error(f"获取最近活动失败: {e}")
            return {"activities": [], "total": 0, "error": str(e)}

    async def get_top_contributors(self, limit: int = 10, sort_by: str = "total_activity") -> Dict[str, Any]:
        """获取贡献者排行榜，合并 PR、评论、Issue 统计"""
        if self.db is None:
            return {"contributors": [], "total": 0, "sort_by": sort_by}
        try:
            contributor_map = {}

            # 从 pr_data 统计 PR 数
            pipeline_pr = [
                {"$group": {"_id": "$user", "pr_count": {"$sum": 1}, "projects": {"$addToSet": {"$concat": ["$owner", "/", "$repo"]}}}},
            ]
            async for doc in self._coll('pr_data').aggregate(pipeline_pr):
                user = doc["_id"]
                if not user or user.endswith("[bot]") or "[bot]" in (user or ""):
                    continue
                contributor_map[user] = {
                    "user": user,
                    "pr_count": doc["pr_count"],
                    "comment_count": 0,
                    "issue_count": 0,
                    "total_activity": doc["pr_count"],
                    "first_active": None,
                    "last_active": None,
                    "projects": list(doc.get("projects", [])),
                }

            # 从 pr_comments 统计评论数
            pipeline_comments = [
                {"$group": {"_id": "$user", "comment_count": {"$sum": 1}}},
            ]
            async for doc in self._coll('pr_comments').aggregate(pipeline_comments):
                user = doc["_id"]
                if not user or "[bot]" in (user or ""):
                    continue
                if user not in contributor_map:
                    contributor_map[user] = {
                        "user": user, "pr_count": 0, "comment_count": 0,
                        "issue_count": 0, "total_activity": 0,
                        "first_active": None, "last_active": None, "projects": [],
                    }
                contributor_map[user]["comment_count"] = doc["comment_count"]

            # 从 issues 统计 Issue 数
            pipeline_issues = [
                {"$group": {"_id": "$user", "issue_count": {"$sum": 1}}},
            ]
            async for doc in self._coll('issues').aggregate(pipeline_issues):
                user = doc["_id"]
                if not user or "[bot]" in (user or ""):
                    continue
                if user not in contributor_map:
                    contributor_map[user] = {
                        "user": user, "pr_count": 0, "comment_count": 0,
                        "issue_count": 0, "total_activity": 0,
                        "first_active": None, "last_active": None, "projects": [],
                    }
                contributor_map[user]["issue_count"] = doc["issue_count"]

            # 计算总活跃度
            for c in contributor_map.values():
                c["total_activity"] = c["pr_count"] + c["comment_count"] + c["issue_count"]

            # 排序
            valid_sorts = {"pr_count", "comment_count", "issue_count", "total_activity"}
            sort_key = sort_by if sort_by in valid_sorts else "total_activity"
            contributors = sorted(contributor_map.values(), key=lambda x: x[sort_key], reverse=True)
            total = len(contributors)
            contributors = contributors[:limit]

            return {"contributors": contributors, "total": total, "sort_by": sort_key}
        except Exception as e:
            logger.error(f"获取贡献者排行失败: {e}")
            return {"contributors": [], "total": 0, "sort_by": sort_by, "error": str(e)}

    async def get_batch_health_snapshots(self, projects: List[str] = None) -> Dict[str, Any]:
        """批量获取项目健康度快照"""
        if self.db is None:
            return {"snapshots": [], "total": 0}
        try:
            # 获取项目列表
            if not projects:
                projects = []
                async for doc in self._coll('registered_projects').find({}, {"owner": 1, "repo": 1, "_id": 0}):
                    projects.append(f"{doc['owner']}/{doc['repo']}")

            if not projects:
                return {"snapshots": [], "total": 0}

            # 并发获取健康度（限制并发数）
            sem = asyncio.Semaphore(3)

            async def _get_snapshot(project_key: str) -> Dict[str, Any]:
                parts = project_key.split("/", 1)
                if len(parts) < 2:
                    return None
                owner, repo = parts[0], parts[1]
                async with sem:
                    try:
                        report = await self.get_project_health_report(owner, repo)
                        if "error" in report:
                            return {"owner": owner, "repo": repo, "data_available": False,
                                    "overall_score": 0, "overall_grade": "N/A"}
                        # 提取维度摘要
                        dimensions_summary = {}
                        for dim in report.get("dimensions", []):
                            dimensions_summary[dim.get("name", "")] = {
                                "score": dim.get("score", 0),
                            }
                        return {
                            "owner": owner,
                            "repo": repo,
                            "overall_score": report.get("overall_score", 0),
                            "overall_grade": report.get("overall_grade", "N/A"),
                            "data_available": True,
                            "dimensions_summary": dimensions_summary,
                        }
                    except Exception:
                        return {"owner": owner, "repo": repo, "data_available": False,
                                "overall_score": 0, "overall_grade": "N/A"}

            results = await asyncio.gather(*[_get_snapshot(p) for p in projects])
            snapshots = [r for r in results if r is not None]

            return {"snapshots": snapshots, "total": len(snapshots)}
        except Exception as e:
            logger.error(f"批量获取健康度快照失败: {e}")
            return {"snapshots": [], "total": 0, "error": str(e)}

    # ====================
    # 通知配置 CRUD
    # ====================

    async def save_notification_config(self, config_data: Dict) -> Dict:
        """保存通知配置"""
        if self.db is None:
            return {"data": None, "error": "数据库未连接"}
        try:
            config_id = config_data.get("config_id") or uuid.uuid4().hex[:8]
            now = datetime.now().isoformat()
            config_data["config_id"] = config_id
            config_data["created_at"] = config_data.get("created_at") or now
            config_data["updated_at"] = now
            await self._coll('notifications_config').update_one(
                {"config_id": config_id},
                {"$set": config_data},
                upsert=True,
            )
            config_data["_id"] = str(config_data.get("_id", ""))
            return {"data": config_data, "error": None}
        except Exception as e:
            logger.error(f"保存通知配置失败: {e}")
            return {"data": None, "error": str(e)}

    async def update_notification_config(self, config_id: str, updates: Dict) -> Dict:
        """更新通知配置"""
        if self.db is None:
            return {"data": None, "error": "数据库未连接"}
        try:
            updates["updated_at"] = datetime.now().isoformat()
            result = await self._coll('notifications_config').update_one(
                {"config_id": config_id},
                {"$set": updates},
            )
            if result.matched_count == 0:
                return {"data": None, "error": "配置不存在"}
            doc = await self._coll('notifications_config').find_one({"config_id": config_id})
            if doc:
                doc["_id"] = str(doc["_id"])
            return {"data": doc, "error": None}
        except Exception as e:
            logger.error(f"更新通知配置失败: {e}")
            return {"data": None, "error": str(e)}

    async def delete_notification_config(self, config_id: str) -> Dict:
        """删除通知配置"""
        if self.db is None:
            return {"data": None, "error": "数据库未连接"}
        try:
            await self._coll('notifications_config').delete_one({"config_id": config_id})
            return {"data": {"deleted": True, "config_id": config_id}, "error": None}
        except Exception as e:
            logger.error(f"删除通知配置失败: {e}")
            return {"data": None, "error": str(e)}

    async def list_notification_configs(self) -> Dict:
        """获取所有通知配置"""
        if self.db is None:
            return {"data": [], "error": "数据库未连接"}
        try:
            configs = []
            async for doc in self._coll('notifications_config').find().sort("created_at", -1):
                doc["_id"] = str(doc["_id"])
                configs.append(doc)
            return {"data": configs, "error": None}
        except Exception as e:
            logger.error(f"获取通知配置失败: {e}")
            return {"data": [], "error": str(e)}

    async def get_notification_config(self, config_id: str) -> Dict:
        """获取单条通知配置"""
        if self.db is None:
            return {"data": None, "error": "数据库未连接"}
        try:
            doc = await self._coll('notifications_config').find_one({"config_id": config_id})
            if doc:
                doc["_id"] = str(doc["_id"])
            return {"data": doc, "error": None}
        except Exception as e:
            logger.error(f"获取通知配置失败: {e}")
            return {"data": None, "error": str(e)}

    # ====================
    # 通知历史 CRUD
    # ====================

    async def save_notification_history(self, history_data: Dict) -> str:
        """保存通知发送记录"""
        if self.db is None:
            return ""
        try:
            history_data["history_id"] = history_data.get("history_id") or uuid.uuid4().hex[:8]
            history_data["sent_at"] = datetime.now().isoformat()
            await self._coll('notifications_history').insert_one(history_data)
            return history_data["history_id"]
        except Exception as e:
            logger.error(f"保存通知历史失败: {e}")
            return ""

    async def list_notification_history(self, config_id: str = None, status: str = None,
                                        page: int = 1, size: int = 20) -> Dict:
        """查询通知历史（分页）"""
        if self.db is None:
            return {"data": [], "total": 0, "error": "数据库未连接"}
        try:
            query = {}
            if config_id:
                query["config_id"] = config_id
            if status:
                query["status"] = status
            total = await self._coll('notifications_history').count_documents(query)
            items = []
            async for doc in self._coll('notifications_history').find(query).sort("sent_at", -1).skip((page - 1) * size).limit(size):
                doc["_id"] = str(doc["_id"])
                items.append(doc)
            return {"data": items, "total": total, "page": page, "size": size, "error": None}
        except Exception as e:
            logger.error(f"查询通知历史失败: {e}")
            return {"data": [], "total": 0, "error": str(e)}

    # ====================
    # 多仓库对比分析
    # ====================

    async def compare_projects(self, project_keys: List[str], dimensions: List[str] = None) -> Dict:
        """多项目横向对比分析"""
        if self.db is None:
            return {"error": "数据库未连接"}
        if len(project_keys) < 2:
            return {"error": "至少需要 2 个项目进行对比"}
        try:
            semaphore = asyncio.Semaphore(3)

            async def _get_report(project_key: str) -> Optional[Dict]:
                parts = project_key.split("/", 1)
                if len(parts) < 2:
                    return None
                owner, repo = parts[0], parts[1]
                async with semaphore:
                    report = await self.get_project_health_report(owner, repo)
                    if "error" in report:
                        return None
                    return {
                        "project": project_key,
                        "owner": owner,
                        "repo": repo,
                        "overall_score": report.get("overall_score", 0),
                        "overall_grade": report.get("overall_grade", "N/A"),
                        "dimensions": report.get("dimensions", []),
                        "data_available": report.get("data_available", True),
                    }

            results = await asyncio.gather(*[_get_report(pk) for pk in project_keys])
            projects = [r for r in results if r is not None]

            if not projects:
                return {"projects": [], "comparison": {}, "error": "无可用数据"}

            # 构建对比数据
            comparison = self._build_comparison(projects, dimensions)

            # 贡献者重叠分析
            overlap = await self.get_contributors_overlap(project_keys)

            return {
                "projects": projects,
                "comparison": comparison,
                "contributors_overlap": overlap.get("contributors", []),
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            logger.error(f"多仓库对比失败: {e}")
            return {"error": str(e)}

    def _build_comparison(self, projects: List[Dict], dimensions: List[str] = None) -> Dict:
        """构建对比数据（维度排名 + 雷达图数据）"""
        # 收集所有维度名称
        all_dim_names = []
        for p in projects:
            for dim in p.get("dimensions", []):
                if dim["name"] not in all_dim_names:
                    all_dim_names.append(dim["name"])

        if dimensions:
            all_dim_names = [d for d in all_dim_names if d in dimensions]

        # 每个维度的排名
        rankings = []
        for dim_name in all_dim_names:
            dim_scores = []
            for p in projects:
                score = 0
                for dim in p.get("dimensions", []):
                    if dim["name"] == dim_name:
                        score = dim.get("score", 0)
                        break
                dim_scores.append({"project": p["project"], "score": round(score, 1)})
            dim_scores.sort(key=lambda x: x["score"], reverse=True)
            for i, ds in enumerate(dim_scores):
                ds["rank"] = i + 1
            rankings.append({"dimension": dim_name, "rankings": dim_scores})

        # 雷达图数据
        radar_data = []
        for p in projects:
            values = []
            for dim_name in all_dim_names:
                score = 0
                for dim in p.get("dimensions", []):
                    if dim["name"] == dim_name:
                        score = dim.get("score", 0)
                        break
                values.append({"dimension": dim_name, "score": round(score, 1)})
            radar_data.append({"project": p["project"], "values": values})

        return {"rankings": rankings, "radar_data": radar_data, "dimensions": all_dim_names}

    async def get_contributors_overlap(self, project_keys: List[str]) -> Dict:
        """跨项目贡献者重叠分析"""
        if self.db is None:
            return {"contributors": [], "error": "数据库未连接"}
        try:
            user_projects = {}  # user -> {project -> pr_count}

            for pk in project_keys:
                parts = pk.split("/", 1)
                if len(parts) < 2:
                    continue
                owner, repo = parts[0], parts[1]
                pipeline = [
                    {"$match": {"owner": owner, "repo": repo}},
                    {"$group": {"_id": "$user", "pr_count": {"$sum": 1}}},
                ]
                async for doc in self._coll('pr_data').aggregate(pipeline):
                    user = doc["_id"]
                    if not user or "[bot]" in (user or ""):
                        continue
                    if user not in user_projects:
                        user_projects[user] = {}
                    user_projects[user][pk] = doc["pr_count"]

            # 过滤出跨项目贡献者（2+ 个项目）
            overlap = []
            for user, projs in user_projects.items():
                if len(projs) >= 2:
                    total = sum(projs.values())
                    overlap.append({
                        "user": user,
                        "projects": list(projs.keys()),
                        "project_count": len(projs),
                        "total_prs": total,
                        "details": projs,
                    })

            overlap.sort(key=lambda x: x["total_prs"], reverse=True)
            return {"contributors": overlap, "total": len(overlap)}
        except Exception as e:
            logger.error(f"贡献者重叠分析失败: {e}")
            return {"contributors": [], "error": str(e)}

    # ==================== 工作流仿真 ====================

    async def save_workflow_simulation(self, result: dict) -> bool:
        """保存仿真结果"""
        if self.db is None:
            return False
        try:
            await self.db["workflow_simulations"].update_one(
                {"simulation_id": result.get("simulation_id")},
                {"$set": result},
                upsert=True,
            )
            return True
        except Exception as e:
            logger.error(f"保存工作流仿真失败: {e}")
            return False

    async def get_workflow_simulations(self, plugin_id: str = None,
                                        limit: int = 20) -> list:
        """查询仿真历史"""
        if self.db is None:
            return []
        try:
            query = {"plugin_id": plugin_id} if plugin_id else {}
            cursor = self.db["workflow_simulations"].find(
                query, {"_id": 0}
            ).sort("compared_at", -1).limit(limit)
            return await cursor.to_list(length=limit)
        except Exception as e:
            logger.error(f"查询工作流仿真失败: {e}")
            return []

    async def get_latest_simulation(self, plugin_id: str) -> Optional[dict]:
        """获取最新仿真"""
        if self.db is None:
            return None
        try:
            return await self.db["workflow_simulations"].find_one(
                {"plugin_id": plugin_id}, {"_id": 0},
                sort=[("compared_at", -1)],
            )
        except Exception as e:
            logger.error(f"查询最新仿真失败: {e}")
            return None

    async def get_simulation_by_id(self, simulation_id: str) -> Optional[dict]:
        """按 simulation_id 获取仿真结果"""
        if self.db is None:
            return None
        try:
            return await self.db["workflow_simulations"].find_one(
                {"simulation_id": simulation_id}, {"_id": 0},
            )
        except Exception as e:
            logger.error(f"查询仿真结果失败 [{simulation_id}]: {e}")
            return None

    # ==================== 算子辅助开发会话 ====================

    async def save_ops_dev_session(self, data: dict) -> bool:
        """保存算子开发会话（upsert by session_id）"""
        if self.db is None:
            return False
        try:
            await self.db["ops_dev_sessions"].update_one(
                {"session_id": data.get("session_id")},
                {"$set": data},
                upsert=True,
            )
            return True
        except Exception as e:
            logger.error(f"保存算子开发会话失败: {e}")
            return False

    async def get_ops_dev_sessions(self, limit: int = 30) -> list:
        """查询算子开发会话列表（按 created_at 降序）"""
        if self.db is None:
            return []
        try:
            cursor = self.db["ops_dev_sessions"].find(
                {}, {"_id": 0}
            ).sort("created_at", -1).limit(limit)
            return await cursor.to_list(length=limit)
        except Exception as e:
            logger.error(f"查询算子开发会话列表失败: {e}")
            return []

    async def get_ops_dev_session(self, session_id: str) -> Optional[dict]:
        """按 session_id 获取算子开发会话"""
        if self.db is None:
            return None
        try:
            return await self.db["ops_dev_sessions"].find_one(
                {"session_id": session_id}, {"_id": 0},
            )
        except Exception as e:
            logger.error(f"查询算子开发会话失败 [{session_id}]: {e}")
            return None

    async def delete_ops_dev_session(self, session_id: str) -> bool:
        """删除算子开发会话"""
        if self.db is None:
            return False
        try:
            result = await self.db["ops_dev_sessions"].delete_one(
                {"session_id": session_id},
            )
            return result.deleted_count > 0
        except Exception as e:
            logger.error(f"删除算子开发会话失败 [{session_id}]: {e}")
            return False
