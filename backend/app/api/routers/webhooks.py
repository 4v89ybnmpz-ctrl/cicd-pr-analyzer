"""
Webhook 接收和管理接口路由
"""
from fastapi import APIRouter, HTTPException, Query, Request
from typing import Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


def register_webhook_routes(router: APIRouter, db, webhook_handler):
    """注册 Webhook 路由"""

    @router.post("/webhooks/github", tags=["Webhook"])
    async def receive_github_webhook(request: Request):
        """接收 GitHub Webhook 事件"""
        if webhook_handler is None:
            raise HTTPException(status_code=503, detail="Webhook 处理器未初始化")

        body = await request.body()
        signature = request.headers.get("X-Hub-Signature-256", "")
        event_type = request.headers.get("X-GitHub-Event", "ping")

        # 签名验证
        if not webhook_handler.verify_github_signature(body, signature):
            raise HTTPException(status_code=403, detail="签名验证失败")

        # ping 事件（GitHub 配置 Webhook 时发送）
        if event_type == "ping":
            return {"msg": "pong", "zen": "Keep it simple"}

        payload = await request.json()
        result = await webhook_handler.handle_github_event(event_type, payload)
        return result

    @router.post("/webhooks/gitcode", tags=["Webhook"])
    async def receive_gitcode_webhook(request: Request):
        """接收 GitCode Webhook 事件"""
        if webhook_handler is None:
            raise HTTPException(status_code=503, detail="Webhook 处理器未初始化")

        token = request.headers.get("X-Gitlab-Token", "")

        if not webhook_handler.verify_gitcode_signature(token):
            raise HTTPException(status_code=403, detail="Token 验证失败")

        payload = await request.json()
        event_type = payload.get("object_kind", "push")
        result = await webhook_handler.handle_gitcode_event(event_type, payload)
        return result

    @router.get("/webhooks/events", tags=["Webhook"])
    async def get_webhook_events(
        page: int = Query(1, ge=1),
        size: int = Query(20, ge=1, le=100),
        source: Optional[str] = Query(None, description="来源筛选: github | gitcode"),
        event_type: Optional[str] = Query(None, description="事件类型筛选"),
    ):
        """查询 Webhook 事件日志"""
        if webhook_handler is None:
            raise HTTPException(status_code=503, detail="Webhook 处理器未初始化")
        result = await webhook_handler.list_events(source=source, event_type=event_type, page=page, size=size)
        return {
            "data": result.get("data", []),
            "total": result.get("total", 0),
            "page": page,
            "size": size,
            "timestamp": datetime.now().isoformat(),
        }

    @router.get("/webhooks/config", tags=["Webhook"])
    async def get_webhook_config():
        """获取 Webhook 配置"""
        if webhook_handler is None:
            raise HTTPException(status_code=503, detail="Webhook 处理器未初始化")
        config = await webhook_handler.get_config()
        return {"data": config, "timestamp": datetime.now().isoformat()}

    @router.put("/webhooks/config", tags=["Webhook"])
    async def update_webhook_config(config: dict):
        """更新 Webhook 配置"""
        if webhook_handler is None:
            raise HTTPException(status_code=503, detail="Webhook 处理器未初始化")
        result = await webhook_handler.save_config(config)
        if result.get("error"):
            raise HTTPException(status_code=500, detail=result["error"])
        return {"data": await webhook_handler.get_config(), "message": "配置已更新", "timestamp": datetime.now().isoformat()}
