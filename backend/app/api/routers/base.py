"""
基础接口路由
"""


def register_base_routes(router):
    """注册基础路由"""

    @router.get("/")
    async def root():
        """根路径"""
        return {
            "name": "GitHub PR API",
            "version": "1.0.0",
            "status": "running",
            "message": "Welcome to GitHub PR API"
        }

    @router.get("/health")
    async def health_check():
        """健康检查"""
        return {"status": "healthy", "version": "1.0.0"}