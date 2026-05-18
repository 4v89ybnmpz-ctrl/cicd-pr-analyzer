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

    # ====================
    # CI/CD 结果持久化
    # ====================

    def save_cicd_result(self, result_data: Dict[str, Any]) -> bool:
        """
        保存单条 CI/CD 解析结果
        :param result_data: CICDResult.to_db_dict() 的输出
        :return: 是否保存成功
        """
        if self.db is None:
            return False

        try:
            collection = self.db['cicd_results']

            # 按 comment_id + owner + repo 去重，存在则更新
            filter_query = {
                "owner": result_data.get("owner"),
                "repo": result_data.get("repo"),
            }
            comment_id = result_data.get("comment_id")
            if comment_id:
                filter_query["comment_id"] = comment_id
            else:
                filter_query["comment_id"] = None

            result_data["updated_at"] = datetime.now().isoformat()

            collection.update_one(
                filter_query,
                {"$set": result_data},
                upsert=True
            )
            return True
        except Exception as e:
            logger.error(f"保存 CI/CD 结果失败: {e}")
            return False

    def save_cicd_results_batch(self, results: List[Dict[str, Any]]) -> Dict[str, int]:
        """
        批量保存 CI/CD 解析结果
        :param results: CICDResult.to_db_dict() 列表
        :return: {"saved": 成功数, "failed": 失败数}
        """
        saved = 0
        failed = 0
        for result_data in results:
            if self.save_cicd_result(result_data):
                saved += 1
            else:
                failed += 1
        logger.info(f"批量保存 CI/CD 结果: {saved} 成功, {failed} 失败")
        return {"saved": saved, "failed": failed}

    def query_cicd_results(self, owner: str, repo: str,
                           pr_number: int = None,
                           build_status: str = None,
                           parser_name: str = None,
                           start_date: str = None, end_date: str = None,
                           page: int = 1, size: int = 20,
                           sort_by: str = "analyzed_at", sort_order: int = -1) -> Dict[str, Any]:
        """
        查询 CI/CD 结果（支持多条件筛选、分页、排序）
        """
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

            total = collection.count_documents(query)
            skip = (page - 1) * size
            cursor = collection.find(query, {"_id": 0}).sort(sort_by, sort_order).skip(skip).limit(size)
            data = list(cursor)

            return {
                "data": data,
                "total": total,
                "page": page,
                "size": size,
                "total_pages": (total + size - 1) // size if size > 0 else 0,
            }
        except Exception as e:
            logger.error(f"查询 CI/CD 结果失败: {e}")
            return {"data": [], "total": 0, "page": page, "size": size, "error": str(e)}

    def get_cicd_summary_from_db(self, owner: str, repo: str,
                                 start_date: str = None, end_date: str = None) -> Dict[str, Any]:
        """
        从数据库聚合 CI/CD 统计数据（成功率、耗时分布、覆盖率等）
        """
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

            # 按状态统计
            status_pipeline = [
                {"$match": match},
                {"$group": {"_id": "$build_status", "count": {"$sum": 1}}}
            ]
            by_status = {item["_id"]: item["count"] for item in collection.aggregate(status_pipeline)}

            # 按解析器统计
            parser_pipeline = [
                {"$match": match},
                {"$group": {"_id": "$parser_name", "count": {"$sum": 1}}}
            ]
            by_parser = {item["_id"]: item["count"] for item in collection.aggregate(parser_pipeline)}

            # 耗时统计（仅对有 duration_seconds 的文档）
            duration_match = {**match, "duration_seconds": {"$ne": None}}
            duration_pipeline = [
                {"$match": duration_match},
                {"$group": {
                    "_id": None,
                    "avg_duration": {"$avg": "$duration_seconds"},
                    "count": {"$sum": 1},
                    "durations": {"$push": "$duration_seconds"},
                }}
            ]
            duration_stats = list(collection.aggregate(duration_pipeline))

            # 覆盖率统计
            coverage_match = {**match, "coverage.percentage": {"$ne": None}}
            coverage_pipeline = [
                {"$match": coverage_match},
                {"$group": {
                    "_id": None,
                    "avg_coverage": {"$avg": "$coverage.percentage"},
                    "count": {"$sum": 1},
                }}
            ]
            coverage_stats = list(collection.aggregate(coverage_pipeline))

            total = sum(by_status.values())
            success_count = by_status.get("success", 0)
            failed_count = by_status.get("failed", 0)

            result = {
                "total": total,
                "by_status": by_status,
                "by_parser": by_parser,
                "success_count": success_count,
                "failed_count": failed_count,
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

    def get_cicd_trends_from_db(self, owner: str, repo: str,
                                granularity: str = "day",
                                start_date: str = None, end_date: str = None) -> List[Dict[str, Any]]:
        """
        从数据库获取 CI/CD 趋势数据
        :param granularity: 时间粒度 day/week/month
        """
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

            # 根据粒度选择日期格式
            if granularity == "month":
                date_format = "%Y-%m"
            elif granularity == "week":
                date_format = "%Y-W%V"
            else:
                date_format = "%Y-%m-%d"

            pipeline = [
                {"$match": match},
                {"$addFields": {
                    "period": {"$dateToString": {"format": date_format, "date": {"$dateFromString": {"dateString": "$analyzed_at"}}}}
                }},
                {"$group": {
                    "_id": "$period",
                    "total": {"$sum": 1},
                    "success_count": {"$sum": {"$cond": [{"$eq": ["$build_status", "success"]}, 1, 0]}},
                    "failed_count": {"$sum": {"$cond": [{"$eq": ["$build_status", "failed"]}, 1, 0]}},
                    "avg_duration": {"$avg": "$duration_seconds"},
                    "avg_coverage": {"$avg": "$coverage.percentage"},
                }},
                {"$sort": {"_id": 1}},
            ]

            results = list(collection.aggregate(pipeline))
            trends = []
            for r in results:
                point = {
                    "period": r["_id"],
                    "total": r["total"],
                    "success_count": r["success_count"],
                    "failed_count": r["failed_count"],
                    "success_rate": round(r["success_count"] / r["total"] * 100, 2) if r["total"] > 0 else None,
                    "avg_duration_seconds": round(r["avg_duration"], 2) if r.get("avg_duration") else None,
                    "avg_coverage": round(r["avg_coverage"], 2) if r.get("avg_coverage") else None,
                }
                trends.append(point)

            return trends
        except Exception as e:
            logger.error(f"获取 CI/CD 趋势失败: {e}")
            return []

    def get_cicd_failure_analysis_from_db(self, owner: str, repo: str,
                                          start_date: str = None, end_date: str = None,
                                          top_n: int = 10) -> Dict[str, Any]:
        """
        从数据库获取 CI/CD 失败分析
        """
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

            total_failures = collection.count_documents(match)

            # 高频失败 job（展开 failed_jobs 数组）
            top_jobs_pipeline = [
                {"$match": {**match, "failed_jobs": {"$ne": None, "$not": {"$size": 0}}}},
                {"$unwind": "$failed_jobs"},
                {"$group": {"_id": "$failed_jobs", "count": {"$sum": 1}}},
                {"$sort": {"count": -1}},
                {"$limit": top_n},
            ]
            top_failed_jobs = [{"name": item["_id"], "count": item["count"]}
                               for item in collection.aggregate(top_jobs_pipeline)]

            # 按解析器统计失败
            parser_pipeline = [
                {"$match": match},
                {"$group": {"_id": "$parser_name", "count": {"$sum": 1}}},
                {"$sort": {"count": -1}},
            ]
            top_failed_parsers = [{"name": item["_id"], "count": item["count"]}
                                  for item in collection.aggregate(parser_pipeline)]

            return {
                "total_failures": total_failures,
                "top_failed_jobs": top_failed_jobs,
                "top_failed_parsers": top_failed_parsers,
                "avg_recovery_time_seconds": self._compute_mttr(collection, owner, repo, start_date, end_date),
            }
        except Exception as e:
            logger.error(f"获取 CI/CD 失败分析失败: {e}")
            return {"error": str(e)}

    def _compute_mttr(self, collection, owner: str, repo: str,
                      start_date: str = None, end_date: str = None) -> Optional[float]:
        """
        计算平均修复时间 MTTR (Mean Time To Recovery)
        逻辑：按 PR 分组，找到 failed -> 下一条 success 的时间差，取平均值
        """
        try:
            match = {"owner": owner, "repo": repo, "analyzed_at": {"$ne": None}}
            if start_date or end_date:
                time_query = {}
                if start_date:
                    time_query["$gte"] = start_date
                if end_date:
                    time_query["$lte"] = end_date
                match["analyzed_at"] = time_query

            # 按 PR + 时间排序获取所有结果
            pipeline = [
                {"$match": match},
                {"$sort": {"pr_number": 1, "analyzed_at": 1}},
                {"$group": {
                    "_id": "$pr_number",
                    "results": {"$push": {"status": "$build_status", "time": "$analyzed_at"}},
                }},
            ]
            pr_groups = list(collection.aggregate(pipeline))

            recovery_times = []
            for group in pr_groups:
                results = group["results"]
                # 遍历同一 PR 的结果序列，找 failed -> success 的时间差
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
