"""
浏览器自动化抓取服务
整合 BrowserManager + AuthManager + NetworkInterceptor + Extractors
提供对内部 CI/CD 平台的数据抓取能力
"""
import asyncio
import logging
from typing import Dict, Any, Optional
from datetime import datetime

from .manager import BrowserManager
from .interceptor import NetworkInterceptor
from .auth import AuthManager
from .extractors import OpenLibingExtractor
from .config import PLATFORM_CONFIG

logger = logging.getLogger(__name__)


class BrowserScrapingService:
    """
    浏览器自动化抓取服务
    对外提供统一接口，内部协调各组件完成数据抓取
    """

    def __init__(self):
        """初始化抓取服务"""
        self.browser = BrowserManager()
        self.auth = AuthManager(cookie_dir=self.browser.config.get("cookie_dir"))
        self.interceptor = NetworkInterceptor()
        self.extractors = {
            "openlibing": OpenLibingExtractor(),
        }
        self._is_initialized = False

    async def initialize(self) -> bool:
        """
        初始化服务（启动浏览器）
        :return: 是否成功
        """
        if self._is_initialized:
            return True

        success = await self.browser.start()
        if success:
            self._is_initialized = True
            logger.info("浏览器抓取服务初始化成功")
        return success

    async def shutdown(self):
        """关闭服务"""
        await self.interceptor.detach()
        await self.browser.stop()
        self._is_initialized = False
        logger.info("浏览器抓取服务已关闭")

    async def fetch_pipeline_data(
        self,
        platform: str,
        pipeline_id: str = None,
        pipeline_run_id: str = None,
        project_id: str = None,
        url: str = None,
        username: str = None,
        password: str = None,
    ) -> Dict[str, Any]:
        """
        抓取流水线数据（主入口）
        :param platform: 平台名称 (openlibing)
        :param pipeline_id: 流水线 ID
        :param pipeline_run_id: 流水线运行 ID
        :param project_id: 项目 ID
        :param url: 直接指定 URL（覆盖自动构建的 URL）
        :param username: 登录用户名
        :param password: 登录密码
        :return: 抓取结果
        """
        start_time = datetime.now()
        result = {
            "platform": platform,
            "pipeline_id": pipeline_id,
            "pipeline_run_id": pipeline_run_id,
            "project_id": project_id,
            "status": "pending",
            "error": None,
            "data": None,
            "captured_requests": 0,
        }

        try:
            # 1. 确保浏览器已启动
            if not self._is_initialized:
                success = await self.initialize()
                if not success:
                    result["status"] = "error"
                    result["error"] = "浏览器启动失败"
                    return result

            # 2. 创建页面并附加拦截器
            page = await self.browser.new_page(f"{platform}_page")
            if not page:
                result["status"] = "error"
                result["error"] = "创建页面失败"
                return result

            await self.interceptor.attach(page)

            # 3. 尝试加载已有 Cookie
            context = self.browser.context
            cookie_loaded = False
            if context:
                cookie_loaded = await self.auth.load_cookies(context, platform)

            # 4. 构建目标 URL
            if not url:
                url = self._build_pipeline_url(platform, pipeline_id, pipeline_run_id, project_id)

            if not url:
                result["status"] = "error"
                result["error"] = "无法构建目标 URL，请提供 url 参数"
                return result

            # 5. 导航到目标页面
            nav_success = await self.browser.navigate(url, page_name=f"{platform}_page")

            if not nav_success:
                # 可能需要登录
                result["status"] = "need_login"
                result["error"] = "页面无法访问，可能需要登录"
                return result

            # 6. 检测登录状态
            is_logged_in = await self.auth.check_login_status(page, platform)

            if not is_logged_in:
                # 尝试登录
                if username and password:
                    login_success = await self.auth.login(page, platform, username, password)
                    if not login_success:
                        result["status"] = "login_failed"
                        result["error"] = "登录失败"
                        return result
                    # 登录后重新导航
                    await self.browser.navigate(url, page_name=f"{platform}_page")
                else:
                    result["status"] = "need_login"
                    result["error"] = "需要登录，请提供 username/password 或设置环境变量"
                    # 保存截图帮助调试
                    await self.browser.screenshot(f"{platform}_page", f"{platform}_login_required.png")
                    return result

            # 7. 保存 Cookie
            if context:
                await self.auth.save_cookies(context, platform)

            # 8. 等待页面数据加载完成
            await asyncio.sleep(3)  # 等待 SPA 渲染和 API 请求完成
            await page.wait_for_load_state("networkidle", timeout=15000)

            # 9. 截图记录
            await self.browser.screenshot(f"{platform}_page", f"{platform}_pipeline.png")

            # 10. 从拦截器提取数据
            extractor = self.extractors.get(platform)
            api_data = self.interceptor.get_api_responses()
            result["captured_requests"] = len(api_data)

            if extractor and api_data:
                result["data"] = extractor.extract(api_data)
                result["status"] = "success"
            elif api_data:
                # 没有专用提取器，返回原始 API 数据
                result["data"] = {"raw_api_responses": api_data}
                result["status"] = "success_raw"
            else:
                result["status"] = "no_data"
                result["error"] = "未捕获到 API 请求，页面可能未正确加载"

            # 分离拦截器
            await self.interceptor.detach()

        except Exception as e:
            logger.error(f"抓取流水线数据异常: {e}")
            result["status"] = "error"
            result["error"] = str(e)

        # 计算耗时
        elapsed = (datetime.now() - start_time).total_seconds()
        result["elapsed_seconds"] = round(elapsed, 2)
        result["timestamp"] = datetime.now().isoformat()

        return result

    def _build_pipeline_url(self, platform: str,
                            pipeline_id: str = None,
                            pipeline_run_id: str = None,
                            project_id: str = None) -> Optional[str]:
        """构建流水线详情页 URL"""
        config = PLATFORM_CONFIG.get(platform)
        if not config:
            return None

        template = config.get("pipeline_url_template")
        if template and pipeline_id and pipeline_run_id:
            return template.format(
                pipeline_id=pipeline_id,
                pipeline_run_id=pipeline_run_id,
                project_id=project_id or "",
            )

        return None

    def get_status(self) -> Dict[str, Any]:
        """获取服务状态"""
        return {
            "is_initialized": self._is_initialized,
            "browser": self.browser.get_status(),
            "interceptor": self.interceptor.get_stats(),
            "platforms": self.auth.list_platforms(),
            "extractors": list(self.extractors.keys()),
        }
