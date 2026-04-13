"""
浏览器生命周期管理
启动/关闭 Playwright 浏览器实例，管理页面上下文
"""
import os
import asyncio
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

from playwright.async_api import async_playwright, Browser, BrowserContext, Page

from .config import BROWSER_CONFIG

logger = logging.getLogger(__name__)


class BrowserManager:
    """
    浏览器管理器
    管理 Playwright 浏览器的启动、页面创建、截图和关闭
    """

    def __init__(self, config: Dict[str, Any] = None):
        """
        初始化浏览器管理器
        :param config: 配置覆盖
        """
        self.config = {**BROWSER_CONFIG, **(config or {})}
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._pages: Dict[str, Page] = {}
        self._is_running = False

        # 确保目录存在
        os.makedirs(self.config.get("screenshot_dir", "/tmp/screenshots"), exist_ok=True)
        os.makedirs(self.config.get("cookie_dir", "/tmp/cookies"), exist_ok=True)

    @property
    def is_running(self) -> bool:
        """浏览器是否正在运行"""
        return self._is_running and self._browser is not None

    @property
    def context(self) -> Optional[BrowserContext]:
        """获取当前浏览器上下文"""
        return self._context

    async def start(self) -> bool:
        """
        启动浏览器
        :return: 是否启动成功
        """
        if self.is_running:
            logger.warning("浏览器已在运行")
            return True

        try:
            self._playwright = await async_playwright().start()

            browser_type = self.config["browser_type"]
            launch_options = {
                "headless": self.config["headless"],
            }
            if self.config.get("slow_mo"):
                launch_options["slow_mo"] = self.config["slow_mo"]

            # 根据类型启动浏览器
            if browser_type == "chromium":
                self._browser = await self._playwright.chromium.launch(**launch_options)
            elif browser_type == "firefox":
                self._browser = await self._playwright.firefox.launch(**launch_options)
            elif browser_type == "webkit":
                self._browser = await self._playwright.webkit.launch(**launch_options)
            else:
                raise ValueError(f"不支持的浏览器类型: {browser_type}")

            # 创建上下文
            context_options = {
                "viewport": self.config["viewport"],
            }
            if self.config.get("user_agent"):
                context_options["user_agent"] = self.config["user_agent"]

            self._context = await self._browser.new_context(**context_options)

            # 设置默认超时
            self._context.set_default_timeout(self.config["default_timeout"])
            self._context.set_default_navigation_timeout(self.config["navigation_timeout"])

            self._is_running = True
            logger.info(f"浏览器启动成功: {browser_type}, headless={self.config['headless']}")
            return True

        except Exception as e:
            logger.error(f"浏览器启动失败: {e}")
            self._is_running = False
            return False

    async def stop(self):
        """关闭浏览器"""
        try:
            # 关闭所有页面
            for name, page in self._pages.items():
                try:
                    await page.close()
                except Exception:
                    pass
            self._pages.clear()

            # 关闭上下文
            if self._context:
                await self._context.close()
                self._context = None

            # 关闭浏览器
            if self._browser:
                await self._browser.close()
                self._browser = None

            # 停止 Playwright
            if self._playwright:
                await self._playwright.stop()
                self._playwright = None

            self._is_running = False
            logger.info("浏览器已关闭")

        except Exception as e:
            logger.error(f"浏览器关闭异常: {e}")

    async def new_page(self, name: str = "default") -> Optional[Page]:
        """
        创建新页面
        :param name: 页面名称（用于管理）
        :return: Page 实例
        """
        if not self._context:
            logger.error("浏览器上下文不存在，请先启动浏览器")
            return None

        try:
            page = await self._context.new_page()
            self._pages[name] = page
            logger.info(f"创建页面: {name}")
            return page
        except Exception as e:
            logger.error(f"创建页面失败: {e}")
            return None

    async def get_page(self, name: str = "default") -> Optional[Page]:
        """
        获取已有页面
        :param name: 页面名称
        :return: Page 实例
        """
        return self._pages.get(name)

    async def navigate(self, url: str, page_name: str = "default",
                       wait_until: str = "networkidle") -> bool:
        """
        导航到指定 URL
        :param url: 目标 URL
        :param page_name: 页面名称
        :param wait_until: 等待条件 (load, domcontentloaded, networkidle, commit)
        :return: 是否成功
        """
        page = self._pages.get(page_name)
        if not page:
            page = await self.new_page(page_name)
            if not page:
                return False

        try:
            await page.goto(url, wait_until=wait_until)
            logger.info(f"导航成功: {url[:80]}")
            return True
        except Exception as e:
            logger.error(f"导航失败: {url[:80]}, 错误: {e}")
            return False

    async def screenshot(self, page_name: str = "default",
                         filename: str = None) -> Optional[str]:
        """
        截图
        :param page_name: 页面名称
        :param filename: 文件名（不含路径）
        :return: 截图文件路径
        """
        if not self.config.get("enable_screenshots"):
            return None

        page = self._pages.get(page_name)
        if not page:
            return None

        try:
            if not filename:
                filename = f"{page_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"

            filepath = os.path.join(self.config["screenshot_dir"], filename)
            await page.screenshot(path=filepath, full_page=True)
            logger.info(f"截图保存: {filepath}")
            return filepath
        except Exception as e:
            logger.error(f"截图失败: {e}")
            return None

    async def get_page_content(self, page_name: str = "default") -> Optional[str]:
        """
        获取页面 HTML 内容
        :param page_name: 页面名称
        :return: HTML 内容
        """
        page = self._pages.get(page_name)
        if not page:
            return None
        try:
            return await page.content()
        except Exception as e:
            logger.error(f"获取页面内容失败: {e}")
            return None

    async def evaluate(self, expression: str, page_name: str = "default") -> Any:
        """
        在页面中执行 JavaScript
        :param expression: JavaScript 表达式
        :param page_name: 页面名称
        :return: 执行结果
        """
        page = self._pages.get(page_name)
        if not page:
            return None
        try:
            return await page.evaluate(expression)
        except Exception as e:
            logger.error(f"执行 JS 失败: {e}")
            return None

    def get_status(self) -> Dict[str, Any]:
        """获取浏览器状态"""
        return {
            "is_running": self.is_running,
            "browser_type": self.config["browser_type"],
            "headless": self.config["headless"],
            "pages": list(self._pages.keys()),
            "page_count": len(self._pages),
        }
