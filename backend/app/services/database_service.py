"""
数据库服务模块（异步版本）
使用 motor 替代 pymongo，所有方法均为 async
"""
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import asyncio
import logging

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

    async def save_pr_data(self, owner: str, repo: str, pr_data: Dict[str, Any]) -> bool:
        if self.db is None:
            return False
        try:
            collection = self.db['pr_data']
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
                        {"owner": owner, "repo": repo, "pr_number": pr_number},
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

    async def update_pr_data(self, owner: str, repo: str, github_service) -> Dict[str, Any]:
        """增量更新 PR 数据：对比 updated_at，有变化则替换，无则新增"""
        if self.db is None:
            return {"error": "数据库未连接", "updated": 0, "added": 0, "unchanged": 0}
        try:
            collection = self.db['pr_data']
            cursor = collection.find({"owner": owner, "repo": repo}, {"pr_number": 1, "updated_at": 1, "_id": 0})
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
                            "title": pr.get("title"), "user": pr.get("user"),
                            "state": pr.get("state"), "created_at": pr.get("created_at"),
                            "updated_at": new_updated, "url": pr.get("url"),
                            "saved_at": now,
                        }
                        operations.append(collection.update_one(
                            {"owner": owner, "repo": repo, "pr_number": pr_number},
                            {"$set": document},
                        ))
                        updated += 1
                    else:
                        unchanged += 1
                else:
                    document = {
                        "owner": owner, "repo": repo, "pr_number": pr_number,
                        "title": pr.get("title"), "user": pr.get("user"),
                        "state": pr.get("state"), "created_at": pr.get("created_at"),
                        "updated_at": new_updated, "url": pr.get("url"),
                        "saved_at": now,
                    }
                    operations.append(collection.update_one(
                        {"owner": owner, "repo": repo, "pr_number": pr_number},
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
            collection = self.db['issues']
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

    async def update_comments(self, owner: str, repo: str, github_service) -> Dict[str, Any]:
        """增量更新 PR 评论数据：获取数据库中已有 PR，重新拉取评论"""
        if self.db is None:
            return {"error": "数据库未连接", "updated": 0, "added": 0, "unchanged": 0}
        try:
            pr_data = await self.get_pr_data(owner, repo)
            if not pr_data:
                return {"error": "无 PR 数据，请先获取 PR", "updated": 0, "added": 0, "unchanged": 0}
            pr_numbers = [pr["number"] for pr in pr_data.get("prs", [])]

            collection = self.db['pr_comments']
            cursor = collection.find({"owner": owner, "repo": repo}, {"comment_id": 1, "updated_at": 1, "_id": 0})
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
                                    {"comment_id": comment_id}, {"$set": document}
                                ))
                                total_updated += 1
                            else:
                                total_unchanged += 1
                        else:
                            document = {
                                "owner": owner, "repo": repo, "pr_number": pr_num,
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
                                {"comment_id": comment_id}, {"$set": document}, upsert=True
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

    async def get_pr_data(self, owner: str, repo: str) -> Optional[Dict[str, Any]]:
        if self.db is None:
            return None
        try:
            cursor = self.db['pr_data'].find({"owner": owner, "repo": repo}, {"_id": 0})
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

    async def list_pr_data(self, limit: int = 100) -> List[Dict[str, Any]]:
        if self.db is None:
            return []
        try:
            pipeline = [
                {"$group": {"_id": {"owner": "$owner", "repo": "$repo"}, "total": {"$sum": 1}}},
                {"$limit": limit},
            ]
            cursor = self.db['pr_data'].aggregate(pipeline)
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
            result = await self.db['pr_data'].delete_many({"owner": owner, "repo": repo})
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
            await self.db['user_profiles'].update_one(
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
                    self.db['user_profiles'].update_one(
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
            collection = self.db['user_profiles']
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
            collection = self.db['user_contributed_repos']
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
            total = await self.db['user_contributed_repos'].count_documents(query)
            skip = (page - 1) * size
            cursor = self.db['user_contributed_repos'].find(query, {"_id": 0}).sort(sort_by, sort_order).skip(skip).limit(size)
            data = await cursor.to_list(length=size)
            return {"data": data, "total": total, "page": page, "size": size,
                    "total_pages": (total + size - 1) // size if size > 0 else 0}
        except Exception as e:
            logger.error(f"查询用户参与项目失败: {e}")
            return {"data": [], "total": 0, "page": page, "size": size, "error": str(e)}

    async def save_issues(self, owner: str, repo: str, issues_data: Dict[str, Any]) -> bool:
        if self.db is None:
            return False
        try:
            collection = self.db['issues']
            issues = issues_data.get("issues", [])
            now = datetime.now().isoformat()
            operations = []
            for issue in issues:
                number = issue.get("number")
                if number is None:
                    continue
                document = {**issue, "owner": owner, "repo": repo, "saved_at": now}
                operations.append(
                    collection.update_one(
                        {"owner": owner, "repo": repo, "number": number},
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
            return await self.db['issues'].find_one({"owner": owner, "repo": repo, "number": number}, {"_id": 0})
        except Exception as e:
            logger.error(f"获取 Issue 数据失败: {e}")
            return None

    async def list_issues(self, owner: str = None, repo: str = None,
                           page: int = 1, size: int = 20,
                           sort_by: str = "created_at", sort_order: int = -1,
                           state: str = None) -> Dict[str, Any]:
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
            total = await self.db['issues'].count_documents(query)
            skip = (page - 1) * size
            cursor = self.db['issues'].find(query, {"_id": 0}).sort(sort_by, sort_order).skip(skip).limit(size)
            data = await cursor.to_list(length=size)
            return {"data": data, "total": total, "page": page, "size": size,
                    "total_pages": (total + size - 1) // size if size > 0 else 0}
        except Exception as e:
            logger.error(f"查询 Issues 列表失败: {e}")
            return {"data": [], "total": 0, "page": page, "size": size, "error": str(e)}

    async def save_issue_timeline(self, owner: str, repo: str, issue_number: int, timeline_data: Dict[str, Any]) -> bool:
        if self.db is None:
            return False
        try:
            collection = self.db['issue_timelines']
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
                        {"owner": owner, "repo": repo, "event_id": str(event_id)},
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
                                    sort_by: str = "created_at", sort_order: int = -1) -> Dict[str, Any]:
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
            total = await self.db['issue_timelines'].count_documents(query)
            skip = (page - 1) * size
            cursor = self.db['issue_timelines'].find(query, {"_id": 0}).sort(sort_by, sort_order).skip(skip).limit(size)
            data = await cursor.to_list(length=size)
            return {"data": data, "total": total, "page": page, "size": size,
                    "total_pages": (total + size - 1) // size if size > 0 else 0}
        except Exception as e:
            logger.error(f"查询 Issue Timeline 失败: {e}")
            return {"data": [], "total": 0, "page": page, "size": size, "error": str(e)}

    async def save_pr_comments(self, owner: str, repo: str, pr_number: int, comments_data: Dict[str, Any]) -> bool:
        if self.db is None:
            return False
        try:
            collection = self.db['pr_comments']
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
                        {"owner": owner, "repo": repo, "comment_id": str(comment_id)},
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

    async def get_pr_comments(self, owner: str, repo: str, pr_number: int) -> Optional[Dict[str, Any]]:
        if self.db is None:
            return None
        try:
            cursor = self.db['pr_comments'].find({"owner": owner, "repo": repo, "pr_number": pr_number}, {"_id": 0})
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

    async def save_pr_timeline(self, owner: str, repo: str, pr_number: int, timeline_data: Dict[str, Any]) -> bool:
        if self.db is None:
            return False
        try:
            collection = self.db['pr_timeline']
            document = {
                "owner": owner, "repo": repo, "pr_number": pr_number, "data": timeline_data,
                "created_at": datetime.now().isoformat(), "updated_at": datetime.now().isoformat()
            }
            await collection.update_one(
                {"owner": owner, "repo": repo, "pr_number": pr_number},
                {"$set": document}, upsert=True
            )
            logger.info(f"PR 时间线数据已保存: {owner}/{repo} PR#{pr_number}")
            return True
        except Exception as e:
            logger.error(f"保存 PR 时间线数据失败: {e}")
            return False

    async def get_pr_timeline(self, owner: str, repo: str, pr_number: int) -> Optional[Dict[str, Any]]:
        if self.db is None:
            return None
        try:
            return await self.db['pr_timeline'].find_one(
                {"owner": owner, "repo": repo, "pr_number": pr_number}, {"_id": 0}
            )
        except Exception as e:
            logger.error(f"获取 PR 时间线数据失败: {e}")
            return None

    async def save_pr_detail(self, owner: str, repo: str, pr_number: int, detail_data: Dict[str, Any]) -> bool:
        if self.db is None:
            return False
        try:
            collection = self.db['pr_details']
            document = {
                "owner": owner, "repo": repo, "pr_number": pr_number, "data": detail_data,
                "created_at": datetime.now().isoformat(), "updated_at": datetime.now().isoformat()
            }
            await collection.update_one(
                {"owner": owner, "repo": repo, "pr_number": pr_number},
                {"$set": document}, upsert=True
            )
            logger.info(f"PR 详细信息数据已保存: {owner}/{repo} PR#{pr_number}")
            return True
        except Exception as e:
            logger.error(f"保存 PR 详细信息数据失败: {e}")
            return False

    async def get_pr_detail(self, owner: str, repo: str, pr_number: int) -> Optional[Dict[str, Any]]:
        if self.db is None:
            return None
        try:
            return await self.db['pr_details'].find_one(
                {"owner": owner, "repo": repo, "pr_number": pr_number}, {"_id": 0}
            )
        except Exception as e:
            logger.error(f"获取 PR 详细信息数据失败: {e}")
            return None

    async def get_stats(self) -> Dict[str, Any]:
        if self.db is None:
            return {"error": "数据库未连接"}
        try:
            collection_names = await self.db.list_collection_names()

            async def _count(name):
                return await self.db[name].count_documents({}) if name in collection_names else 0

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
                               sort_by: str = "created_at", sort_order: int = -1) -> Dict[str, Any]:
        if self.db is None:
            return {"data": [], "total": 0, "page": page, "size": size}
        try:
            collection = self.db['pr_comments']
            query = {}
            if owner:
                query["owner"] = owner
            if repo:
                query["repo"] = repo
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
                               sort_by: str = "updated_at", sort_order: int = -1) -> Dict[str, Any]:
        if self.db is None:
            return {"data": [], "total": 0, "page": page, "size": size}
        try:
            collection = self.db['pr_timeline']
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
            logger.error(f"查询 PR 时间线列表失败: {e}")
            return {"data": [], "total": 0, "page": page, "size": size, "error": str(e)}

    async def list_pr_details(self, owner: str = None, repo: str = None,
                              page: int = 1, size: int = 20,
                              sort_by: str = "updated_at", sort_order: int = -1,
                              state: str = None, start_time: str = None, end_time: str = None) -> Dict[str, Any]:
        if self.db is None:
            return {"data": [], "total": 0, "page": page, "size": size}
        try:
            collection = self.db['pr_details']
            query = {}
            if owner:
                query["owner"] = owner
            if owner and repo:
                query["repo"] = repo
            if state:
                query["data.state"] = state
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
                                page: int = 1, size: int = 20) -> Dict[str, Any]:
        if self.db is None:
            return {"data": [], "total": 0, "page": page, "size": size}
        try:
            collection = self.db['pr_details']
            query = {"$or": [
                {"data.title": {"$regex": keyword, "$options": "i"}},
                {"data.body": {"$regex": keyword, "$options": "i"}}
            ]}
            if owner:
                query["owner"] = owner
            if owner and repo:
                query["repo"] = repo
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
            collection = self.db['pr_reviews']
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
            return await self.db['pr_reviews'].find_one(
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
            collection = self.db['pr_reviews']
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
            collection = self.db['pr_commits']
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
            return await self.db['pr_commits'].find_one(
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
            collection = self.db['pr_commits']
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
            collection = self.db['cicd_results']
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
            collection = self.db['cicd_results']
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
            collection = self.db['cicd_results']
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
            collection = self.db['cicd_results']
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
            collection = self.db['cicd_results']
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
                if collection_name not in collection_names:
                    return {}
                pipeline = [
                    {"$group": {"_id": {"owner": "$owner", "repo": "$repo"}, "count": {"$sum": 1}}}
                ]
                cursor = self.db[collection_name].aggregate(pipeline)
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

            async for doc in self.db['registered_projects'].find({}, {"owner": 1, "repo": 1, "_id": 0}):
                all_projects.add(f"{doc['owner']}/{doc['repo']}")

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
                    if coll_name not in collection_names:
                        continue
                    doc = await self.db[coll_name].find_one(
                        {"owner": owner, "repo": repo},
                        {"saved_at": 1, "_id": 0},
                        sort=[("saved_at", -1)],
                    )
                    if doc and doc.get("saved_at"):
                        sa = doc["saved_at"]
                        if last_updated is None or sa > last_updated:
                            last_updated = sa

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
                })

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
            await self.db['git_log_summaries'].update_one(
                {"owner": owner, "repo": repo},
                {"$set": summary},
                upsert=True,
            )
            collection = self.db['git_log_commits']
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
            return await self.db['git_log_summaries'].find_one(
                {"owner": owner, "repo": repo}, {"_id": 0}
            )
        except Exception as e:
            logger.error(f"获取 git log 摘要失败: {e}")
            return None

    async def list_git_log_commits(self, owner: str, repo: str,
                                    author: str = None, page: int = 1, size: int = 20,
                                    sort_by: str = "author_date", sort_order: int = -1) -> Dict[str, Any]:
        if self.db is None:
            return {"data": [], "total": 0, "page": page, "size": size}
        try:
            query = {"owner": owner, "repo": repo}
            if author:
                query["author_name"] = {"$regex": author, "$options": "i"}
            total = await self.db['git_log_commits'].count_documents(query)
            skip = (page - 1) * size
            cursor = self.db['git_log_commits'].find(query, {"_id": 0}).sort(sort_by, sort_order).skip(skip).limit(size)
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

            pr_data_count = await self.db['pr_data'].count_documents(query)
            pr_comments_count = await self.db['pr_comments'].count_documents(query)
            pr_timeline_count = await self.db['pr_timeline'].count_documents(query)
            pr_details_count = await self.db['pr_details'].count_documents(query)

            pipeline = [
                {"$match": query} if query else {"$match": {}},
                {"$group": {"_id": {"owner": "$owner", "repo": "$repo"}, "count": {"$sum": 1}}}
            ]
            by_repo = await self.db['pr_details'].aggregate(pipeline).to_list(length=None)

            state_pipeline = [
                {"$match": query} if query else {"$match": {}},
                {"$group": {"_id": "$data.state", "count": {"$sum": 1}}}
            ]
            by_state = await self.db['pr_details'].aggregate(state_pipeline).to_list(length=None)

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

        total_prs = await self.db['pr_details'].count_documents(details_query)

        # 从 pr_reviews 获取有 review 的 PR 数
        reviews_query = {"owner": owner, "repo": repo}
        prs_with_review = await self.db['pr_reviews'].count_documents(reviews_query)

        # 计算平均 reviewer 数（兼容 data 为 array 或 dict 两种格式）
        if prs_with_review > 0:
            review_docs = await self.db['pr_reviews'].find(reviews_query, {"_id": 0}).to_list(length=None)
            review_counts = []
            for doc in review_docs:
                reviews_list = self._extract_reviews_list(doc.get("data"))
                if reviews_list:
                    review_counts.append(len(reviews_list))
            avg_reviewers = round(sum(review_counts) / len(review_counts), 2) if review_counts else None
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
        review_docs = await self.db['pr_reviews'].find(reviews_query, {"_id": 0}).to_list(length=None)

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
        async for detail in self.db['pr_details'].find(
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

        review_docs = await self.db['pr_reviews'].find(reviews_query, {"_id": 0}).to_list(length=None)

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

        review_docs = await self.db['pr_reviews'].find(reviews_query, {"_id": 0}).to_list(length=None)

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

        review_docs = await self.db['pr_reviews'].find(reviews_query, {"_id": 0}).to_list(length=None)

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

            raw = await self.db['pr_reviews'].aggregate(pipeline).to_list(length=None)

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
            docs = await self.db['pr_details'].find(
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
            result = await self.db['pr_details'].aggregate(pipeline).to_list(length=1)
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
            contributors = await self.db['pr_details'].aggregate(pipeline).to_list(length=None)
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
            docs = await self.db['issues'].find(
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

            raw = await self.db['pr_details'].aggregate(pipeline).to_list(length=None)

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
            result = await self.db['pr_details'].aggregate(pipeline).to_list(length=None)
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
            collection = self.db['pr_files']
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
            return await self.db['pr_files'].find_one(
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
            # 获取所有 pr_files 文档
            query = {"owner": owner, "repo": repo}
            docs = await self.db['pr_files'].find(query, {"_id": 0}).to_list(length=None)

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
