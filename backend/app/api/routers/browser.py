"""
浏览器自动化抓取 API 路由
"""
import asyncio
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException
from datetime import datetime

logger = logging.getLogger(__name__)

# 全局服务实例（延迟初始化）
_scraping_service = None


def get_scraping_service():
    """获取抓取服务实例"""
    global _scraping_service
    if _scraping_service is None:
        from .service import BrowserScrapingService
        _scraping_service = BrowserScrapingService()
    return _scraping_service


def register_browser_routes(router):
    """注册浏览器自动化相关路由"""

    @router.get("/browser/status")
    async def get_browser_status():
        """获取浏览器抓取服务状态"""
        service = get_scraping_service()
        return {
            **service.get_status(),
            "timestamp": datetime.now().isoformat()
        }

    @router.post("/browser/initialize")
    async def initialize_browser():
        """初始化浏览器（启动浏览器实例）"""
        service = get_scraping_service()
        success = await service.initialize()
        if not success:
            raise HTTPException(status_code=500, detail="浏览器启动失败")
        return {
            "status": "initialized",
            "browser": service.browser.get_status(),
            "timestamp": datetime.now().isoformat()
        }

    @router.post("/browser/shutdown")
    async def shutdown_browser():
        """关闭浏览器"""
        service = get_scraping_service()
        await service.shutdown()
        return {
            "status": "shutdown",
            "timestamp": datetime.now().isoformat()
        }

    @router.get("/browser/platforms")
    async def list_platforms():
        """列出支持的内部平台"""
        service = get_scraping_service()
        return {
            "platforms": service.auth.list_platforms(),
            "timestamp": datetime.now().isoformat()
        }

    @router.post("/browser/fetch-pipeline")
    async def fetch_pipeline_data(
        platform: str,
        pipeline_id: Optional[str] = None,
        pipeline_run_id: Optional[str] = None,
        project_id: Optional[str] = None,
        url: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
    ):
        """
        抓取内部平台流水线数据

        - platform: 平台名称 (openlibing)
        - pipeline_id: 流水线 ID
        - pipeline_run_id: 流水线运行 ID
        - project_id: 项目 ID
        - url: 直接指定 URL
        - username: 登录用户名
        - password: 登录密码
        """
        service = get_scraping_service()
        result = await service.fetch_pipeline_data(
            platform=platform,
            pipeline_id=pipeline_id,
            pipeline_run_id=pipeline_run_id,
            project_id=project_id,
            url=url,
            username=username,
            password=password,
        )
        return result

    @router.get("/browser/captured-requests")
    async def get_captured_requests(
        url_pattern: Optional[str] = None,
        method: Optional[str] = None,
    ):
        """获取拦截到的网络请求"""
        service = get_scraping_service()
        captured = service.interceptor.get_captured(
            url_pattern=url_pattern,
            method=method,
        )
        return {
            "total": len(captured),
            "requests": captured,
            "timestamp": datetime.now().isoformat()
        }

    @router.get("/browser/api-responses")
    async def get_api_responses(
        url_pattern: Optional[str] = None,
    ):
        """获取拦截到的 API 响应（JSON）"""
        service = get_scraping_service()
        responses = service.interceptor.get_api_responses(url_pattern=url_pattern)
        return {
            "total": len(responses),
            "responses": responses,
            "timestamp": datetime.now().isoformat()
        }
