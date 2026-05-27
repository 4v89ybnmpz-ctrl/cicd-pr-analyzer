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

    @router.get("/config/tokens/github")
    async def get_github_tokens():
        """获取 GitHub Token 池（脱敏显示，仅保留前4后4位）"""
        tokens = config_manager.get_tokens()
        masked = []
        for t in tokens:
            if len(t) > 8:
                masked.append(t[:4] + '*' * (len(t) - 8) + t[-4:])
            else:
                masked.append('****')
        return {"tokens": masked, "total": len(tokens), "timestamp": datetime.now().isoformat()}

    @router.put("/config/tokens/github")
    async def update_github_tokens(payload: dict):
        """
        更新 GitHub Token 池
        支持两种模式:
        - 全量替换: {"tokens": ["token1", "token2"]}
        - 追加: {"action": "add", "token": "new_token"}
        - 删除: {"action": "remove", "index": 0}
        """
        try:
            config = config_manager.config
            current_tokens = config.get("tokens", [])

            if "tokens" in payload:
                # 全量替换
                new_tokens = payload["tokens"]
            elif payload.get("action") == "add":
                token = payload.get("token", "").strip()
                if not token:
                    raise HTTPException(status_code=400, detail="Token 不能为空")
                if token in current_tokens:
                    raise HTTPException(status_code=400, detail="Token 已存在")
                new_tokens = current_tokens + [token]
            elif payload.get("action") == "remove":
                index = payload.get("index", -1)
                if index < 0 or index >= len(current_tokens):
                    raise HTTPException(status_code=400, detail="索引越界")
                new_tokens = current_tokens[:index] + current_tokens[index + 1:]
            else:
                raise HTTPException(status_code=400, detail="无效的请求格式")

            config["tokens"] = new_tokens

            config_path = config_manager.config_path
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2, ensure_ascii=False)

            # 刷新运行中的 TokenPool
            github_service.token_pool.tokens = new_tokens
            github_service.token_pool.current_index = 0
            if hasattr(github_service.token_pool, '_rate_limits'):
                github_service.token_pool._rate_limits.clear()

            logger.info(f"GitHub Token 池已更新: {len(new_tokens)} 个 Token")
            return {"message": f"GitHub Token 池已更新: {len(new_tokens)} 个 Token", "total": len(new_tokens)}
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"更新 GitHub Token 池失败: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/config/tokens/atomgit")
    async def get_atomgit_tokens():
        """获取 AtomGit Token 池（脱敏显示）"""
        tokens = config_manager.config.get("gitcode_tokens", [])
        masked = []
        for t in tokens:
            if len(t) > 8:
                masked.append(t[:4] + '*' * (len(t) - 8) + t[-4:])
            else:
                masked.append('****')
        return {"tokens": masked, "total": len(tokens), "timestamp": datetime.now().isoformat()}

    @router.put("/config/tokens/atomgit")
    async def update_atomgit_tokens(payload: dict):
        """
        更新 AtomGit Token 池
        支持两种模式:
        - 全量替换: {"tokens": ["token1", "token2"]}
        - 追加: {"action": "add", "token": "new_token"}
        - 删除: {"action": "remove", "index": 0}
        """
        try:
            config = config_manager.config
            current_tokens = config.get("gitcode_tokens", [])

            if "tokens" in payload:
                new_tokens = payload["tokens"]
            elif payload.get("action") == "add":
                token = payload.get("token", "").strip()
                if not token:
                    raise HTTPException(status_code=400, detail="Token 不能为空")
                if token in current_tokens:
                    raise HTTPException(status_code=400, detail="Token 已存在")
                new_tokens = current_tokens + [token]
            elif payload.get("action") == "remove":
                index = payload.get("index", -1)
                if index < 0 or index >= len(current_tokens):
                    raise HTTPException(status_code=400, detail="索引越界")
                new_tokens = current_tokens[:index] + current_tokens[index + 1:]
            else:
                raise HTTPException(status_code=400, detail="无效的请求格式")

            config["gitcode_tokens"] = new_tokens

            config_path = config_manager.config_path
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2, ensure_ascii=False)

            logger.info(f"AtomGit Token 池已更新: {len(new_tokens)} 个 Token")
            return {"message": f"AtomGit Token 池已更新: {len(new_tokens)} 个 Token", "total": len(new_tokens)}
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"更新 AtomGit Token 池失败: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/config/tokens/github/check")
    async def check_github_tokens():
        """
        主动检测 GitHub Token 额度
        调用 GitHub rate_limit API 获取每个 Token 的实时剩余额度和重置时间
        """
        import httpx as _httpx
        tokens = config_manager.get_tokens()
        now = __import__('time').time()
        results = []

        async def _check(token, index):
            masked = token[:4] + '*' * (len(token) - 8) + token[-4:] if len(token) > 8 else '****'
            try:
                async with _httpx.AsyncClient(timeout=10) as client:
                    r = await client.get(
                        "https://api.github.com/rate_limit",
                        headers={"Authorization": f"token {token}", "Accept": "application/json"},
                    )
                if r.status_code == 401:
                    return {"index": index, "token_masked": masked, "valid": False, "error": "Token 无效"}
                if r.status_code != 200:
                    return {"index": index, "token_masked": masked, "valid": None, "error": f"HTTP {r.status_code}"}

                data = r.json().get("resources", {})
                core = data.get("core", {})
                search = data.get("search", {})
                graphql = data.get("graphql", {})

                # 更新 TokenPool 的速率限制信息
                core_remaining = core.get("remaining", 0)
                core_reset = core.get("reset", 0)
                github_service.token_pool.update_rate_limit(token, core_remaining, core_reset)

                return {
                    "index": index,
                    "token_masked": masked,
                    "valid": True,
                    "core": {
                        "limit": core.get("limit", 0),
                        "remaining": core_remaining,
                        "used": core.get("used", 0),
                        "reset_at": core_reset,
                        "reset_in_seconds": max(0, core_reset - now),
                    },
                    "search": {
                        "limit": search.get("limit", 0),
                        "remaining": search.get("remaining", 0),
                        "used": search.get("used", 0),
                        "reset_at": search.get("reset", 0),
                        "reset_in_seconds": max(0, search.get("reset", 0) - now),
                    },
                    "graphql": {
                        "limit": graphql.get("limit", 0),
                        "remaining": graphql.get("remaining", 0),
                        "used": graphql.get("used", 0),
                        "reset_at": graphql.get("reset", 0),
                        "reset_in_seconds": max(0, graphql.get("reset", 0) - now),
                    },
                }
            except Exception as e:
                return {"index": index, "token_masked": masked, "valid": None, "error": str(e)[:100]}

        tasks = [_check(t, i) for i, t in enumerate(tokens)]
        results = await __import__('asyncio').gather(*tasks)

        return {"tokens": results, "total": len(tokens), "timestamp": datetime.now().isoformat()}

    @router.get("/config/tokens/atomgit/check")
    async def check_atomgit_tokens():
        """
        主动检测 AtomGit Token 额度
        调用 AtomGit user API 验证 Token 有效性，并从响应头解析速率限制
        """
        import httpx as _httpx
        tokens = config_manager.config.get("gitcode_tokens", [])
        base_url = config_manager.config.get("gitcode_settings", {}).get("base_url", "https://atomgit.com/api/v5")
        now = __import__('time').time()
        results = []

        async def _check(token, index):
            masked = token[:4] + '*' * (len(token) - 8) + token[-4:] if len(token) > 8 else '****'
            try:
                async with _httpx.AsyncClient(timeout=10) as client:
                    r = await client.get(
                        f"{base_url}/user",
                        params={"access_token": token},
                        headers={"Accept": "application/json"},
                    )

                # 从响应头解析速率限制（Gitee/AtomGit 风格）
                limit_total = r.headers.get("X-RateLimit-Limit") or r.headers.get("X-Total-Count")
                limit_remaining = r.headers.get("X-RateLimit-Remaining")
                limit_reset = r.headers.get("X-RateLimit-Reset")

                rate_info = None
                if limit_remaining is not None:
                    try:
                        remaining = int(limit_remaining)
                        reset_epoch = float(limit_reset) if limit_reset else now + 3600
                        rate_info = {
                            "limit": int(limit_total) if limit_total else None,
                            "remaining": remaining,
                            "reset_at": reset_epoch,
                            "reset_in_seconds": max(0, reset_epoch - now),
                        }
                    except (ValueError, TypeError):
                        pass

                if r.status_code == 401:
                    return {"index": index, "token_masked": masked, "valid": False, "error": "Token 无效", "rate_limit": rate_info}
                if r.status_code != 200:
                    return {"index": index, "token_masked": masked, "valid": None, "error": f"HTTP {r.status_code}", "rate_limit": rate_info}

                user_data = r.json()
                return {
                    "index": index,
                    "token_masked": masked,
                    "valid": True,
                    "user": user_data.get("login"),
                    "user_id": user_data.get("id"),
                    "rate_limit": rate_info,
                }
            except Exception as e:
                return {"index": index, "token_masked": masked, "valid": None, "error": str(e)[:100]}

        tasks = [_check(t, i) for i, t in enumerate(tokens)]
        results = await __import__('asyncio').gather(*tasks)

        return {"tokens": results, "total": len(tokens), "timestamp": datetime.now().isoformat()}


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