"""
配置和缓存接口路由
"""
from fastapi import HTTPException
from datetime import datetime
import logging
import json

from app.models.responses import ConfigResponse, ConfigReloadResponse, CacheStatsResponse, MessageResponse

logger = logging.getLogger(__name__)


def register_config_routes(router, cache, github_service, config_manager):
    """注册配置相关路由"""

    @router.get("/config", response_model=ConfigResponse)
    async def get_config():
        """获取配置信息"""
        logger.info("获取配置信息")
        config = config_manager.to_dict()
        return {
            "config": {
                "app_name": config.get("app_name"),
                "version": config.get("version"),
                "tokens_count": len(config.get("tokens", [])),
                "cache_ttl": config.get("cache", {}).get("ttl", 300),
                "api_settings": config.get("api_settings", {}),
                "proxy": config.get("proxy", ""),
            },
            "timestamp": datetime.now().isoformat()
        }

    @router.post("/config/reload", response_model=ConfigReloadResponse)
    async def reload_config():
        """重新加载配置"""
        logger.info("重新加载配置")
        try:
            new_config = config_manager.reload_config()

            tokens = new_config.get("tokens", [])
            github_service.token_pool.tokens = tokens
            github_service.token_pool.current_index = 0

            new_api_settings = new_config.get("api_settings", {})
            github_service.base_url = new_api_settings.get("base_url", "https://api.github.com")
            github_service.per_page = new_api_settings.get("per_page", 100)
            github_service.state = new_api_settings.get("state", "all")
            github_service.request_delay = new_api_settings.get("request_delay", 0.5)
            github_service.max_workers = new_api_settings.get("max_workers", 3)

            logger.info("配置文件重新加载成功")

            return {
                "message": "配置已重新加载",
                "config": {
                    "app_name": new_config.get("app_name"),
                    "version": new_config.get("version"),
                    "tokens_count": len(new_config.get("tokens", [])),
                    "cache_ttl": new_config.get("cache", {}).get("ttl", 300),
                    "api_settings": new_config.get("api_settings", {})
                },
                "timestamp": datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"配置重新加载失败: {e}")
            raise HTTPException(status_code=500, detail=f"配置重新加载失败: {e}")

    @router.get("/config/proxy")
    async def get_proxy_config():
        """获取代理配置"""
        config = config_manager.config
        return {
            "proxy": config.get("proxy", ""),
            "env_proxy": __import__('os').environ.get("HTTPS_PROXY", ""),
            "timestamp": datetime.now().isoformat(),
        }

    @router.put("/config/proxy")
    async def update_proxy_config(proxy: str = ""):
        """更新代理配置（写入 config.json 并更新 GitRepoService）"""
        try:
            config = config_manager.config
            config["proxy"] = proxy

            # 写入 config.json
            config_path = config_manager.config_path
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2, ensure_ascii=False)

            # 更新 git 路由中的模块级代理变量
            from app.api.routers import git as git_router
            git_router._proxy = proxy if proxy else None

            logger.info(f"代理配置已更新: {proxy or '(无代理)'}")
            return {"message": f"代理配置已更新: {proxy or '已清除'}", "proxy": proxy}
        except Exception as e:
            logger.error(f"更新代理配置失败: {e}")
            raise HTTPException(status_code=500, detail=str(e))


def register_cache_routes(router, cache):
    """注册缓存相关路由"""

    @router.get("/cache/stats", response_model=CacheStatsResponse)
    async def get_cache_stats():
        """获取缓存统计信息"""
        logger.info("获取缓存统计信息")
        stats = cache.get_stats()
        return {"cache_stats": stats, "timestamp": datetime.now().isoformat()}

    @router.delete("/cache/clear", response_model=MessageResponse)
    async def clear_cache():
        """清空缓存"""
        logger.info("清空缓存")
        cache.clear()
        return {"message": "缓存已清空", "timestamp": datetime.now().isoformat()}