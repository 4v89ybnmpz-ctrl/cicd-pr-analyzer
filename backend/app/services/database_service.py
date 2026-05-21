"""
数据库服务模块（异步版本）
使用 motor 替代 pymongo，所有方法均为 async
"""
from typing import Dict, Any, List, Optional
from datetime import datetime
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

            pr_data_counts, comments_counts, issues_counts, timeline_counts, details_counts, reviews_counts, commits_counts = await asyncio.gather(
                _group_count("pr_data"),
                _group_count("pr_comments"),
                _group_count("issues"),
                _group_count("issue_timelines"),
                _group_count("pr_details"),
                _group_count("pr_reviews"),
                _group_count("pr_commits"),
            )

            all_projects = set()
            for m in [pr_data_counts, comments_counts, issues_counts, timeline_counts, details_counts, reviews_counts, commits_counts]:
                all_projects.update(m.keys())

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
                commits_count = commits_counts.get(project_key, 0)

                last_updated = None
                for coll_name in ["pr_data", "pr_comments", "issues", "issue_timelines", "pr_details"]:
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
                    "last_updated": last_updated,
                })

            logger.info(f"项目总览: {len(overview)} 个项目")
            return overview
        except Exception as e:
            logger.error(f"获取项目总览失败: {e}")
            return []

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
