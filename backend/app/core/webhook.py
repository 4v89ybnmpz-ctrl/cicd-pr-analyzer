"""
Webhook 事件处理器
支持 GitHub 和 GitCode Webhook 签名验证、事件分发和增量更新
"""
import hmac
import hashlib
import uuid
import asyncio
import logging
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class WebhookHandler:
    """Webhook 事件处理器"""

    def __init__(self, db, github_service=None, gitcode_service=None):
        self._db = db
        self._github_service = github_service
        self._gitcode_service = gitcode_service
        self._github_secret = ""
        self._gitcode_token = ""
        self._auto_sync = True

    async def load_config(self):
        """从数据库加载 Webhook 配置"""
        if self._db is None or self._db.db is None:
            return
        try:
            doc = await self._db.db['webhook_config'].find_one({"_id": "default"})
            if doc:
                self._github_secret = doc.get("github_secret", "")
                self._gitcode_token = doc.get("gitcode_token", "")
                self._auto_sync = doc.get("auto_sync", True)
        except Exception as e:
            logger.error(f"加载 Webhook 配置失败: {e}")

    async def save_config(self, config: Dict) -> Dict:
        """保存 Webhook 配置"""
        if self._db is None or self._db.db is None:
            return {"error": "数据库未连接"}
        try:
            self._github_secret = config.get("github_secret", "")
            self._gitcode_token = config.get("gitcode_token", "")
            self._auto_sync = config.get("auto_sync", True)

            await self._db.db['webhook_config'].update_one(
                {"_id": "default"},
                {"$set": {
                    "github_secret": self._github_secret,
                    "gitcode_token": self._gitcode_token,
                    "auto_sync": self._auto_sync,
                    "updated_at": datetime.now().isoformat(),
                }},
                upsert=True,
            )
            return {"error": None}
        except Exception as e:
            logger.error(f"保存 Webhook 配置失败: {e}")
            return {"error": str(e)}

    async def get_config(self) -> Dict:
        """获取当前配置"""
        return {
            "github_secret_set": bool(self._github_secret),
            "gitcode_token_set": bool(self._gitcode_token),
            "auto_sync": self._auto_sync,
        }

    # ====================
    # 签名验证
    # ====================

    def verify_github_signature(self, body: bytes, signature: str) -> bool:
        """验证 GitHub Webhook 签名（HMAC-SHA256）"""
        if not self._github_secret:
            return True  # 未配置 secret 时不验证
        if not signature:
            return False
        expected = "sha256=" + hmac.new(
            self._github_secret.encode("utf-8"),
            body,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(signature, expected)

    def verify_gitcode_signature(self, token: str) -> bool:
        """验证 GitCode Webhook Token"""
        if not self._gitcode_token:
            return True  # 未配置 token 时不验证
        return hmac.compare_digest(token or "", self._gitcode_token)

    # ====================
    # 事件处理
    # ====================

    async def handle_github_event(self, event_type: str, payload: Dict) -> Dict:
        """处理 GitHub Webhook 事件"""
        try:
            # 提取仓库信息
            repo_info = payload.get("repository", {})
            owner = repo_info.get("owner", {}).get("login", "")
            repo = repo.get("name", "") if hasattr(repo_info, "get") else ""
            repo = repo_info.get("name", "")

            if not owner or not repo:
                return {"processed": False, "reason": "无法提取仓库信息"}

            # 检查是否是已注册项目
            if self._db and self._db.db:
                registered = await self._db.db['registered_projects'].find_one(
                    {"owner": owner, "repo": repo}
                )
                if not registered:
                    return {"processed": False, "reason": f"{owner}/{repo} 未注册"}

            action = payload.get("action", "")
            event_id = ""

            # 根据事件类型分发处理
            if event_type == "pull_request":
                pr_number = payload.get("pull_request", {}).get("number")
                event_id = await self._save_event("github", event_type, action, owner, repo, {
                    "pr_number": pr_number, "pr_state": payload.get("pull_request", {}).get("state"),
                })
                if self._auto_sync and pr_number:
                    await self._on_pr_event(owner, repo, pr_number, action)

            elif event_type == "pull_request_review":
                pr_number = payload.get("pull_request", {}).get("number")
                event_id = await self._save_event("github", event_type, action, owner, repo, {
                    "pr_number": pr_number, "review_state": payload.get("review", {}).get("state"),
                })
                if self._auto_sync and pr_number:
                    await self._on_review_event(owner, repo, pr_number, action)

            elif event_type == "push":
                event_id = await self._save_event("github", event_type, "push", owner, repo, {
                    "ref": payload.get("ref", ""), "commits_count": len(payload.get("commits", [])),
                })

            elif event_type == "issues":
                issue_number = payload.get("issue", {}).get("number")
                event_id = await self._save_event("github", event_type, action, owner, repo, {
                    "issue_number": issue_number,
                })
                if self._auto_sync and action in ("opened", "closed"):
                    await self._on_issue_event(owner, repo, action)

            else:
                event_id = await self._save_event("github", event_type, action, owner, repo, {})

            return {"processed": True, "event_id": event_id}
        except Exception as e:
            logger.error(f"处理 GitHub 事件失败: {e}")
            return {"processed": False, "error": str(e)}

    async def handle_gitcode_event(self, event_type: str, payload: Dict) -> Dict:
        """处理 GitCode (GitLab) Webhook 事件"""
        try:
            project = payload.get("project", {})
            path_with_namespace = project.get("path_with_namespace", "")
            if "/" in path_with_namespace:
                parts = path_with_namespace.split("/")
                owner = parts[-2] if len(parts) >= 2 else parts[0]
                repo = parts[-1]
            else:
                owner = project.get("namespace", "")
                repo = project.get("name", "")

            if not owner or not repo:
                return {"processed": False, "reason": "无法提取仓库信息"}

            action_map = {"open": "opened", "close": "closed", "merge": "merged", "update": "updated"}
            raw_action = payload.get("action", "")
            action = action_map.get(raw_action, raw_action)

            mr_iid = payload.get("object_attributes", {}).get("iid")

            event_id = await self._save_event("gitcode", event_type, action, owner, repo, {
                "mr_iid": mr_iid,
            })

            return {"processed": True, "event_id": event_id}
        except Exception as e:
            logger.error(f"处理 GitCode 事件失败: {e}")
            return {"processed": False, "error": str(e)}

    # ====================
    # 增量更新处理
    # ====================

    async def _on_pr_event(self, owner: str, repo: str, pr_number: int, action: str):
        """PR 事件 → 增量更新 PR 详情和相关数据"""
        if not self._github_service or not self._db:
            return
        try:
            # 获取最新 PR 详情
            detail_result = await self._github_service.fetch_pr_detail(owner, repo, pr_number)
            if detail_result and not detail_result.get("error"):
                await self._db.save_pr_details(owner, repo, [detail_result.get("detail", {})])

            # 获取最新评论
            comments_result = await self._github_service.fetch_pr_comments(owner, repo, pr_number)
            if comments_result and not comments_result.get("error"):
                await self._db.save_pr_comments(owner, repo, pr_number, comments_result.get("comments", []))

            # 获取最新 Reviews
            reviews_result = await self._github_service.fetch_pr_reviews(owner, repo, pr_number)
            if reviews_result and not reviews_result.get("error"):
                await self._db.save_pr_reviews(owner, repo, pr_number, reviews_result.get("reviews", []))

            logger.info(f"Webhook 增量更新完成: {owner}/{repo} PR#{pr_number} ({action})")
        except Exception as e:
            logger.error(f"Webhook 增量更新失败: {e}")

    async def _on_review_event(self, owner: str, repo: str, pr_number: int, action: str):
        """Review 事件 → 增量更新 Reviews"""
        if not self._github_service or not self._db:
            return
        try:
            reviews_result = await self._github_service.fetch_pr_reviews(owner, repo, pr_number)
            if reviews_result and not reviews_result.get("error"):
                await self._db.save_pr_reviews(owner, repo, pr_number, reviews_result.get("reviews", []))
            logger.info(f"Webhook Review 更新完成: {owner}/{repo} PR#{pr_number}")
        except Exception as e:
            logger.error(f"Webhook Review 更新失败: {e}")

    async def _on_issue_event(self, owner: str, repo: str, action: str):
        """Issue 事件 → 增量更新 Issues"""
        if not self._github_service or not self._db:
            return
        try:
            result = await self._db.update_issues(owner, repo, self._github_service)
            logger.info(f"Webhook Issues 更新完成: {owner}/{repo} ({action}): {result}")
        except Exception as e:
            logger.error(f"Webhook Issues 更新失败: {e}")

    # ====================
    # 事件存储
    # ====================

    async def _save_event(self, source: str, event_type: str, action: str,
                          owner: str, repo: str, payload_summary: Dict) -> str:
        """保存 Webhook 事件到数据库"""
        if self._db is None or self._db.db is None:
            return ""
        try:
            event_id = uuid.uuid4().hex[:8]
            doc = {
                "event_id": event_id,
                "source": source,
                "event_type": event_type,
                "action": action,
                "owner": owner,
                "repo": repo,
                "payload_summary": payload_summary,
                "processed": self._auto_sync,
                "created_at": datetime.now().isoformat(),
                "processed_at": datetime.now().isoformat() if self._auto_sync else None,
            }
            await self._db.db['webhook_events'].insert_one(doc)
            return event_id
        except Exception as e:
            logger.error(f"保存 Webhook 事件失败: {e}")
            return ""

    async def list_events(self, source: str = None, event_type: str = None,
                          page: int = 1, size: int = 20) -> Dict:
        """查询事件日志"""
        if self._db is None or self._db.db is None:
            return {"data": [], "total": 0}
        try:
            query = {}
            if source:
                query["source"] = source
            if event_type:
                query["event_type"] = event_type
            total = await self._db.db['webhook_events'].count_documents(query)
            events = []
            async for doc in self._db.db['webhook_events'].find(query).sort("created_at", -1).skip((page - 1) * size).limit(size):
                doc["_id"] = str(doc["_id"])
                events.append(doc)
            return {"data": events, "total": total, "page": page, "size": size}
        except Exception as e:
            logger.error(f"查询 Webhook 事件失败: {e}")
            return {"data": [], "total": 0, "error": str(e)}
