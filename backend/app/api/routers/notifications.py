"""
通知推送接口路由
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


def register_notification_routes(router: APIRouter, db, notification_engine):
    """注册通知推送路由"""

    @router.get("/notifications/config", tags=["通知推送"])
    async def get_notification_configs():
        """获取所有通知配置"""
        if notification_engine is None:
            raise HTTPException(status_code=503, detail="通知引擎未初始化")
        result = await notification_engine.load_configs()
        return {"data": result, "timestamp": datetime.now().isoformat()}

    @router.post("/notifications/config", tags=["通知推送"])
    async def create_notification_config(config: dict):
        """创建通知配置"""
        if notification_engine is None:
            raise HTTPException(status_code=503, detail="通知引擎未初始化")

        # 基本校验
        name = config.get("name", "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="配置名称不能为空")

        channels = config.get("channels", [])
        if not channels:
            raise HTTPException(status_code=400, detail="至少选择一个通知渠道")

        result = await notification_engine.save_config(config)
        if result.get("error"):
            raise HTTPException(status_code=500, detail=result["error"])
        return {"data": result["data"], "timestamp": datetime.now().isoformat()}

    @router.put("/notifications/config/{config_id}", tags=["通知推送"])
    async def update_notification_config(config_id: str, updates: dict):
        """更新通知配置"""
        if notification_engine is None:
            raise HTTPException(status_code=503, detail="通知引擎未初始化")
        result = await notification_engine.update_config(config_id, updates)
        if result.get("error"):
            raise HTTPException(status_code=500, detail=result["error"])
        return {"data": result["data"], "timestamp": datetime.now().isoformat()}

    @router.delete("/notifications/config/{config_id}", tags=["通知推送"])
    async def delete_notification_config(config_id: str):
        """删除通知配置"""
        if notification_engine is None:
            raise HTTPException(status_code=503, detail="通知引擎未初始化")
        result = await notification_engine.delete_config(config_id)
        if result.get("error"):
            raise HTTPException(status_code=500, detail=result["error"])
        return {"data": result["data"], "timestamp": datetime.now().isoformat()}

    @router.post("/notifications/config/{config_id}/test", tags=["通知推送"])
    async def test_notification_config(config_id: str):
        """测试发送通知"""
        if notification_engine is None:
            raise HTTPException(status_code=503, detail="通知引擎未初始化")
        result = await notification_engine.test_send(config_id)
        return {
            "sent": result.get("sent", False),
            "results": result.get("results", []),
            "message": "测试发送完成" if result.get("sent") else "测试发送失败，请检查配置",
            "timestamp": datetime.now().isoformat(),
        }

    @router.get("/notifications/history", tags=["通知推送"])
    async def get_notification_history(
        page: int = Query(1, ge=1),
        size: int = Query(20, ge=1, le=100),
        config_id: Optional[str] = Query(None),
        status: Optional[str] = Query(None),
    ):
        """查询通知历史（分页）"""
        if db is None:
            raise HTTPException(status_code=503, detail="数据库未连接")
        result = await db.list_notification_history(
            config_id=config_id, status=status, page=page, size=size,
        )
        return {
            "data": result.get("data", []),
            "total": result.get("total", 0),
            "page": page,
            "size": size,
            "timestamp": datetime.now().isoformat(),
        }
