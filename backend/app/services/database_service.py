"""
数据库服务模块
负责 MongoDB 数据库操作
"""
from typing import Dict, Any, List, Optional
from datetime import datetime
import logging

try:
    from pymongo import MongoClient
    from pymongo.errors import ConnectionFailure, OperationFailure
    DATABASE_AVAILABLE = True
except ImportError:
    DATABASE_AVAILABLE = False
    MongoClient = None

logger = logging.getLogger(__name__)

# 导入密码管理器
try:
    from app.core.encryption import get_password_manager
    ENCRYPTION_AVAILABLE = True
except ImportError:
    ENCRYPTION_AVAILABLE = False


class DatabaseService:
    """
    数据库服务类
    负责 MongoDB 数据库操作
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 27017,
                 username: str = "admin", password: str = "",
                 database: str = "github_pr_db"):
        """
        初始化数据库服务
        :param host: 数据库主机
        :param port: 数据库端口
        :param username: 用户名
        :param password: 密码（可以是明文或加密的）
        :param database: 数据库名
        """
        if not DATABASE_AVAILABLE:
            logger.warning("pymongo 未安装，数据库功能不可用")
            self.client = None
            self.db = None
            return

        # 解密密码（如果密码是加密的）
        decrypted_password = self._decrypt_password(password)

        self.connection_string = f"mongodb://{username}:{decrypted_password}@{host}:{port}/"
        self.database_name = database
        self.client: Optional[MongoClient] = None
        self.db = None
        logger.info(f"数据库服务初始化: {host}:{port}/{database}")

    def _decrypt_password(self, password: str) -> str:
        """
        解密密码
        :param password: 密码（可能是明文或加密的）
        :return: 解密后的密码
        """
        if not ENCRYPTION_AVAILABLE:
            # 如果加密功能不可用，直接返回原密码
            return password

        try:
            password_manager = get_password_manager()
            
            # 检查密码是否已加密
            if password_manager.is_encrypted(password):
                logger.info("检测到加密密码，正在解密...")
                decrypted = password_manager.decrypt(password)
                if decrypted:
                    logger.info("密码解密成功")
                    return decrypted
                else:
                    logger.error("密码解密失败，使用原密码")
                    return password
            else:
                # 密码是明文，直接返回
                logger.debug("密码为明文，无需解密")
                return password
        except Exception as e:
            logger.warning(f"密码解密过程出错: {e}，使用原密码")
            return password

    def connect(self) -> bool:
        """
        连接数据库
        :return: 是否连接成功
        """
        if not DATABASE_AVAILABLE:
            return False

        try:
            self.client = MongoClient(
                self.connection_string,
                serverSelectionTimeoutMS=5000
            )
            # 测试连接
            self.client.admin.command('ping')
            self.db = self.client[self.database_name]
            logger.info("数据库连接成功")
            return True
        except ConnectionFailure as e:
            logger.error(f"数据库连接失败: {e}")
            return False
        except Exception as e:
            logger.error(f"数据库连接异常: {e}")
            return False

    def disconnect(self):
        """断开数据库连接"""
        if self.client:
            self.client.close()
            logger.info("数据库连接已关闭")

    def save_pr_data(self, owner: str, repo: str, pr_data: Dict[str, Any]) -> bool:
        """
        保存 PR 数据
        :param owner: 仓库所有者
        :param repo: 仓库名称
        :param pr_data: PR 数据
        :return: 是否保存成功
        """
        if self.db is None:
            return False

        try:
            collection = self.db['pr_data']
            document = {
                "owner": owner,
                "repo": repo,
                "data": pr_data,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            }

            # 使用 upsert 更新或插入
            collection.update_one(
                {"owner": owner, "repo": repo},
                {"$set": document},
                upsert=True
            )

            logger.info(f"PR 数据已保存: {owner}/{repo}")
            return True
        except Exception as e:
            logger.error(f"保存 PR 数据失败: {e}")
            return False

    def get_pr_data(self, owner: str, repo: str) -> Optional[Dict[str, Any]]:
        """
        获取 PR 数据
        :param owner: 仓库所有者
        :param repo: 仓库名称
        :return: PR 数据
        """
        if self.db is None:
            return None

        try:
            collection = self.db['pr_data']
            document = collection.find_one(
                {"owner": owner, "repo": repo},
                {"_id": 0}
            )
            return document
        except Exception as e:
            logger.error(f"获取 PR 数据失败: {e}")
            return None

    def list_pr_data(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        列出所有 PR 数据
        :param limit: 限制数量
        :return: PR 数据列表
        """
        if self.db is None:
            return []

        try:
            collection = self.db['pr_data']
            cursor = collection.find({}, {"_id": 0}).limit(limit)
            return list(cursor)
        except Exception as e:
            logger.error(f"列出 PR 数据失败: {e}")
            return []

    def delete_pr_data(self, owner: str, repo: str) -> bool:
        """
        删除 PR 数据
        :param owner: 仓库所有者
        :param repo: 仓库名称
        :return: 是否删除成功
        """
        if self.db is None:
            return False

        try:
            collection = self.db['pr_data']
            result = collection.delete_one({"owner": owner, "repo": repo})
            if result.deleted_count > 0:
                logger.info(f"PR 数据已删除: {owner}/{repo}")
                return True
            return False
        except Exception as e:
            logger.error(f"删除 PR 数据失败: {e}")
            return False

    def save_pr_comments(self, owner: str, repo: str, pr_number: int, comments_data: Dict[str, Any]) -> bool:
        """
        保存 PR 评论数据
        :param owner: 仓库所有者
        :param repo: 仓库名称
        :param pr_number: PR 编号
        :param comments_data: 评论数据
        :return: 是否保存成功
        """
        if self.db is None:
            return False

        try:
            collection = self.db['pr_comments']
            document = {
                "owner": owner,
                "repo": repo,
                "pr_number": pr_number,
                "data": comments_data,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            }

            # 使用 upsert 更新或插入
            collection.update_one(
                {"owner": owner, "repo": repo, "pr_number": pr_number},
                {"$set": document},
                upsert=True
            )

            logger.info(f"PR 评论数据已保存: {owner}/{repo} PR#{pr_number}")
            return True
        except Exception as e:
            logger.error(f"保存 PR 评论数据失败: {e}")
            return False

    def get_pr_comments(self, owner: str, repo: str, pr_number: int) -> Optional[Dict[str, Any]]:
        """
        获取 PR 评论数据
        :param owner: 仓库所有者
        :param repo: 仓库名称
        :param pr_number: PR 编号
        :return: 评论数据
        """
        if self.db is None:
            return None

        try:
            collection = self.db['pr_comments']
            document = collection.find_one(
                {"owner": owner, "repo": repo, "pr_number": pr_number},
                {"_id": 0}
            )
            return document
        except Exception as e:
            logger.error(f"获取 PR 评论数据失败: {e}")
            return None

    def save_pr_timeline(self, owner: str, repo: str, pr_number: int, timeline_data: Dict[str, Any]) -> bool:
        """
        保存 PR 时间线数据
        :param owner: 仓库所有者
        :param repo: 仓库名称
        :param pr_number: PR 编号
        :param timeline_data: 时间线数据
        :return: 是否保存成功
        """
        if self.db is None:
            return False

        try:
            collection = self.db['pr_timeline']
            document = {
                "owner": owner,
                "repo": repo,
                "pr_number": pr_number,
                "data": timeline_data,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            }

            # 使用 upsert 更新或插入
            collection.update_one(
                {"owner": owner, "repo": repo, "pr_number": pr_number},
                {"$set": document},
                upsert=True
            )

            logger.info(f"PR 时间线数据已保存: {owner}/{repo} PR#{pr_number}")
            return True
        except Exception as e:
            logger.error(f"保存 PR 时间线数据失败: {e}")
            return False

    def get_pr_timeline(self, owner: str, repo: str, pr_number: int) -> Optional[Dict[str, Any]]:
        """
        获取 PR 时间线数据
        :param owner: 仓库所有者
        :param repo: 仓库名称
        :param pr_number: PR 编号
        :return: 时间线数据
        """
        if self.db is None:
            return None

        try:
            collection = self.db['pr_timeline']
            document = collection.find_one(
                {"owner": owner, "repo": repo, "pr_number": pr_number},
                {"_id": 0}
            )
            return document
        except Exception as e:
            logger.error(f"获取 PR 时间线数据失败: {e}")
            return None

    def save_pr_detail(self, owner: str, repo: str, pr_number: int, detail_data: Dict[str, Any]) -> bool:
        """
        保存 PR 详细信息数据
        :param owner: 仓库所有者
        :param repo: 仓库名称
        :param pr_number: PR 编号
        :param detail_data: PR 详细信息数据
        :return: 是否保存成功
        """
        if self.db is None:
            return False

        try:
            collection = self.db['pr_details']
            document = {
                "owner": owner,
                "repo": repo,
                "pr_number": pr_number,
                "data": detail_data,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            }

            # 使用 upsert 更新或插入
            collection.update_one(
                {"owner": owner, "repo": repo, "pr_number": pr_number},
                {"$set": document},
                upsert=True
            )

            logger.info(f"PR 详细信息数据已保存: {owner}/{repo} PR#{pr_number}")
            return True
        except Exception as e:
            logger.error(f"保存 PR 详细信息数据失败: {e}")
            return False

    def get_pr_detail(self, owner: str, repo: str, pr_number: int) -> Optional[Dict[str, Any]]:
        """
        获取 PR 详细信息数据
        :param owner: 仓库所有者
        :param repo: 仓库名称
        :param pr_number: PR 编号
        :return: PR 详细信息数据
        """
        if self.db is None:
            return None

        try:
            collection = self.db['pr_details']
            document = collection.find_one(
                {"owner": owner, "repo": repo, "pr_number": pr_number},
                {"_id": 0}
            )
            return document
        except Exception as e:
            logger.error(f"获取 PR 详细信息数据失败: {e}")
            return None

    def get_stats(self) -> Dict[str, Any]:
        """
        获取数据库统计信息
        :return: 统计信息字典
        """
        if self.db is None:
            return {"error": "数据库未连接"}

        try:
            pr_count = self.db['pr_data'].count_documents({})
            task_count = self.db['tasks'].count_documents({}) if 'tasks' in self.db.list_collection_names() else 0
            pr_details_count = self.db['pr_details'].count_documents({}) if 'pr_details' in self.db.list_collection_names() else 0

            return {
                "database": self.database_name,
                "pr_data_count": pr_count,
                "pr_details_count": pr_details_count,
                "task_count": task_count,
                "status": "connected"
            }
        except Exception as e:
            logger.error(f"获取统计信息失败: {e}")
            return {"error": str(e)}

    # ====================
    # 高级查询功能
    # ====================

    def list_pr_comments(self, owner: str = None, repo: str = None,
                         page: int = 1, size: int = 20,
                         sort_by: str = "updated_at", sort_order: int = -1) -> Dict[str, Any]:
        """
        查询 PR 评论列表
        :param owner: 仓库所有者（可选）
        :param repo: 仓库名称（可选）
        :param page: 页码
        :param size: 每页数量
        :param sort_by: 排序字段
        :param sort_order: 排序方向 (1 升序, -1 降序)
        :return: 分页结果
        """
        if self.db is None:
            return {"data": [], "total": 0, "page": page, "size": size}

        try:
            collection = self.db['pr_comments']
            query = {}
            if owner:
                query["owner"] = owner
            if owner and repo:
                query["repo"] = repo

            total = collection.count_documents(query)
            skip = (page - 1) * size
            cursor = collection.find(query, {"_id": 0}).sort(sort_by, sort_order).skip(skip).limit(size)
            data = list(cursor)

            return {
                "data": data,
                "total": total,
                "page": page,
                "size": size,
                "total_pages": (total + size - 1) // size if size > 0 else 0
            }
        except Exception as e:
            logger.error(f"查询 PR 评论列表失败: {e}")
            return {"data": [], "total": 0, "page": page, "size": size, "error": str(e)}

    def list_pr_timeline(self, owner: str = None, repo: str = None,
                         page: int = 1, size: int = 20,
                         sort_by: str = "updated_at", sort_order: int = -1) -> Dict[str, Any]:
        """
        查询 PR 时间线列表
        :param owner: 仓库所有者（可选）
        :param repo: 仓库名称（可选）
        :param page: 页码
        :param size: 每页数量
        :param sort_by: 排序字段
        :param sort_order: 排序方向 (1 升序, -1 降序)
        :return: 分页结果
        """
        if self.db is None:
            return {"data": [], "total": 0, "page": page, "size": size}

        try:
            collection = self.db['pr_timeline']
            query = {}
            if owner:
                query["owner"] = owner
            if owner and repo:
                query["repo"] = repo

            total = collection.count_documents(query)
            skip = (page - 1) * size
            cursor = collection.find(query, {"_id": 0}).sort(sort_by, sort_order).skip(skip).limit(size)
            data = list(cursor)

            return {
                "data": data,
                "total": total,
                "page": page,
                "size": size,
                "total_pages": (total + size - 1) // size if size > 0 else 0
            }
        except Exception as e:
            logger.error(f"查询 PR 时间线列表失败: {e}")
            return {"data": [], "total": 0, "page": page, "size": size, "error": str(e)}

    def list_pr_details(self, owner: str = None, repo: str = None,
                        page: int = 1, size: int = 20,
                        sort_by: str = "updated_at", sort_order: int = -1,
                        state: str = None, start_time: str = None, end_time: str = None) -> Dict[str, Any]:
        """
        查询 PR 详细信息列表
        :param owner: 仓库所有者（可选）
        :param repo: 仓库名称（可选）
        :param page: 页码
        :param size: 每页数量
        :param sort_by: 排序字段
        :param sort_order: 排序方向 (1 升序, -1 降序)
        :param state: PR 状态筛选 (open/closed/merged)
        :param start_time: 开始时间
        :param end_time: 结束时间
        :return: 分页结果
        """
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

            total = collection.count_documents(query)
            skip = (page - 1) * size
            cursor = collection.find(query, {"_id": 0}).sort(sort_by, sort_order).skip(skip).limit(size)
            data = list(cursor)

            return {
                "data": data,
                "total": total,
                "page": page,
                "size": size,
                "total_pages": (total + size - 1) // size if size > 0 else 0
            }
        except Exception as e:
            logger.error(f"查询 PR 详细信息列表失败: {e}")
            return {"data": [], "total": 0, "page": page, "size": size, "error": str(e)}

    def search_pr_details(self, keyword: str, owner: str = None, repo: str = None,
                          page: int = 1, size: int = 20) -> Dict[str, Any]:
        """
        模糊搜索 PR 详细信息
        :param keyword: 搜索关键词（标题/描述）
        :param owner: 仓库所有者（可选）
        :param repo: 仓库名称（可选）
        :param page: 页码
        :param size: 每页数量
        :return: 分页结果
        """
        if self.db is None:
            return {"data": [], "total": 0, "page": page, "size": size}

        try:
            collection = self.db['pr_details']
            # 构建模糊查询条件（标题或描述包含关键词）
            query = {
                "$or": [
                    {"data.title": {"$regex": keyword, "$options": "i"}},
                    {"data.body": {"$regex": keyword, "$options": "i"}}
                ]
            }
            if owner:
                query["owner"] = owner
            if owner and repo:
                query["repo"] = repo

            total = collection.count_documents(query)
            skip = (page - 1) * size
            cursor = collection.find(query, {"_id": 0}).sort("updated_at", -1).skip(skip).limit(size)
            data = list(cursor)

            return {
                "data": data,
                "total": total,
                "page": page,
                "size": size,
                "total_pages": (total + size - 1) // size if size > 0 else 0,
                "keyword": keyword
            }
        except Exception as e:
            logger.error(f"搜索 PR 详细信息失败: {e}")
            return {"data": [], "total": 0, "page": page, "size": size, "error": str(e)}

    def get_aggregate_stats(self, owner: str = None, repo: str = None) -> Dict[str, Any]:
        """
        聚合统计
        :param owner: 仓库所有者（可选）
        :param repo: 仓库名称（可选）
        :return: 统计结果
        """
        if self.db is None:
            return {"error": "数据库未连接"}

        try:
            query = {}
            if owner:
                query["owner"] = owner
            if owner and repo:
                query["repo"] = repo

            # 各集合数量统计
            pr_data_count = self.db['pr_data'].count_documents(query)
            pr_comments_count = self.db['pr_comments'].count_documents(query)
            pr_timeline_count = self.db['pr_timeline'].count_documents(query)
            pr_details_count = self.db['pr_details'].count_documents(query)

            # 按仓库分组统计
            pipeline = [
                {"$match": query} if query else {"$match": {}},
                {"$group": {"_id": {"owner": "$owner", "repo": "$repo"}, "count": {"$sum": 1}}}
            ]
            by_repo = list(self.db['pr_details'].aggregate(pipeline))

            # 按状态分组统计
            state_pipeline = [
                {"$match": query} if query else {"$match": {}},
                {"$group": {"_id": "$data.state", "count": {"$sum": 1}}}
            ]
            by_state = list(self.db['pr_details'].aggregate(state_pipeline))

            return {
                "pr_data_count": pr_data_count,
                "pr_comments_count": pr_comments_count,
                "pr_timeline_count": pr_timeline_count,
                "pr_details_count": pr_details_count,
                "by_repo": by_repo,
                "by_state": by_state
            }
        except Exception as e:
            logger.error(f"聚合统计失败: {e}")
            return {"error": str(e)}
