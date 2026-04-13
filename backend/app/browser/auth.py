"""
登录与会话管理
支持 Cookie 持久化、登录状态检测、自动登录
"""
import os
import json
import asyncio
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
from playwright.async_api import BrowserContext, Page

from .config import PLATFORM_CONFIG

logger = logging.getLogger(__name__)


class AuthManager:
    """
    认证管理器
    管理平台登录状态、Cookie 持久化、自动登录
    """

    def __init__(self, cookie_dir: str = None):
        """
        初始化认证管理器
        :param cookie_dir: Cookie 保存目录
        """
        self.cookie_dir = cookie_dir or PLATFORM_CONFIG.get("openlibing", {}).get("cookie_dir", "/tmp/cookies")
        os.makedirs(self.cookie_dir, exist_ok=True)

        # 登录状态缓存
        self._login_status: Dict[str, bool] = {}

    def _cookie_file(self, platform: str) -> str:
        """获取 Cookie 文件路径"""
        return os.path.join(self.cookie_dir, f"{platform}_cookies.json")

    async def save_cookies(self, context: BrowserContext, platform: str) -> bool:
        """
        保存当前上下文的 Cookie 到文件
        :param context: 浏览器上下文
        :param platform: 平台名称
        :return: 是否保存成功
        """
        try:
            cookies = await context.cookies()
            filepath = self._cookie_file(platform)

            data = {
                "platform": platform,
                "cookies": cookies,
                "saved_at": datetime.now().isoformat(),
                "count": len(cookies),
            }

            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            logger.info(f"Cookie 已保存: {platform}, {len(cookies)} 条")
            return True

        except Exception as e:
            logger.error(f"保存 Cookie 失败: {e}")
            return False

    async def load_cookies(self, context: BrowserContext, platform: str) -> bool:
        """
        从文件加载 Cookie 到上下文
        :param context: 浏览器上下文
        :param platform: 平台名称
        :return: 是否加载成功
        """
        filepath = self._cookie_file(platform)
        if not os.path.exists(filepath):
            logger.info(f"Cookie 文件不存在: {filepath}")
            return False

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)

            cookies = data.get("cookies", [])
            if not cookies:
                logger.warning(f"Cookie 文件为空: {platform}")
                return False

            # 检查 Cookie 是否过期
            saved_at = data.get("saved_at", "")
            if saved_at:
                saved_time = datetime.fromisoformat(saved_at)
                age_hours = (datetime.now() - saved_time).total_seconds() / 3600
                if age_hours > 24:
                    logger.warning(f"Cookie 已超过 24 小时: {platform} ({age_hours:.1f}h)")
                    return False

            await context.add_cookies(cookies)
            logger.info(f"Cookie 已加载: {platform}, {len(cookies)} 条 (保存于 {saved_at})")
            return True

        except Exception as e:
            logger.error(f"加载 Cookie 失败: {e}")
            return False

    async def check_login_status(self, page: Page, platform: str) -> bool:
        """
        检测是否已登录
        :param page: 页面实例
        :param platform: 平台名称
        :return: 是否已登录
        """
        config = PLATFORM_CONFIG.get(platform)
        if not config:
            logger.error(f"未知平台: {platform}")
            return False

        try:
            # 导航到首页
            check_url = config.get("login_check_url", config.get("base_url"))
            await page.goto(check_url, wait_until="networkidle", timeout=15000)

            # 检测登录指示元素
            indicator = config.get("login_indicator", "")
            if indicator:
                # 尝试多个选择器（逗号分隔）
                selectors = [s.strip() for s in indicator.split(",")]
                for selector in selectors:
                    try:
                        element = await page.wait_for_selector(selector, timeout=5000)
                        if element:
                            self._login_status[platform] = True
                            logger.info(f"已登录: {platform} (检测到: {selector})")
                            return True
                    except Exception:
                        continue

            # 如果没有检测到登录指示，检查 URL 是否被重定向到登录页
            current_url = page.url
            login_url = config.get("login_url", "")
            if login_url and login_url in current_url:
                self._login_status[platform] = False
                logger.info(f"未登录: {platform} (重定向到登录页)")
                return False

            # 检查页面内容是否有登录表单
            try:
                username_selector = config.get("username_selector", "")
                if username_selector:
                    for selector in username_selector.split(","):
                        element = await page.query_selector(selector.strip())
                        if element:
                            self._login_status[platform] = False
                            logger.info(f"未登录: {platform} (检测到登录表单)")
                            return False
            except Exception:
                pass

            # 无法确定，默认未登录
            self._login_status[platform] = False
            logger.warning(f"登录状态未知: {platform}")
            return False

        except Exception as e:
            logger.error(f"检测登录状态失败: {e}")
            self._login_status[platform] = False
            return False

    async def login(self, page: Page, platform: str,
                    username: str = None, password: str = None) -> bool:
        """
        执行登录
        :param page: 页面实例
        :param platform: 平台名称
        :param username: 用户名（可选，也可从环境变量读取）
        :param password: 密码（可选，也可从环境变量读取）
        :return: 是否登录成功
        """
        config = PLATFORM_CONFIG.get(platform)
        if not config:
            logger.error(f"未知平台: {platform}")
            return False

        # 获取凭据
        if not username:
            username = os.environ.get(f"{platform.upper()}_USERNAME", "")
        if not password:
            password = os.environ.get(f"{platform.upper()}_PASSWORD", "")

        if not username or not password:
            logger.error(f"缺少登录凭据: {platform} (设置环境变量 {platform.upper()}_USERNAME / {platform.upper()}_PASSWORD)")
            return False

        try:
            # 导航到登录页
            login_url = config.get("login_url", config.get("base_url"))
            await page.goto(login_url, wait_until="networkidle")
            logger.info(f"导航到登录页: {login_url}")

            # 填写用户名
            username_selector = config.get("username_selector", "")
            for selector in username_selector.split(","):
                selector = selector.strip()
                try:
                    await page.fill(selector, username, timeout=5000)
                    logger.info(f"填写用户名成功: {selector}")
                    break
                except Exception:
                    continue

            # 填写密码
            password_selector = config.get("password_selector", "")
            for selector in password_selector.split(","):
                selector = selector.strip()
                try:
                    await page.fill(selector, password, timeout=5000)
                    logger.info(f"填写密码成功: {selector}")
                    break
                except Exception:
                    continue

            # 点击登录按钮
            submit_selector = config.get("submit_selector", "")
            for selector in submit_selector.split(","):
                selector = selector.strip()
                try:
                    await page.click(selector, timeout=5000)
                    logger.info(f"点击登录按钮: {selector}")
                    break
                except Exception:
                    continue

            # 等待登录完成
            await page.wait_for_load_state("networkidle", timeout=15000)

            # 验证登录状态
            is_logged_in = await self.check_login_status(page, platform)

            if is_logged_in:
                logger.info(f"登录成功: {platform}")
            else:
                logger.warning(f"登录可能失败: {platform} (未检测到登录指示)")

            return is_logged_in

        except Exception as e:
            logger.error(f"登录失败: {e}")
            return False

    def get_login_status(self, platform: str) -> Optional[bool]:
        """获取缓存的登录状态"""
        return self._login_status.get(platform)

    def list_platforms(self) -> List[Dict[str, Any]]:
        """列出所有已配置的平台"""
        result = []
        for name, config in PLATFORM_CONFIG.items():
            result.append({
                "name": name,
                "display_name": config.get("name", name),
                "base_url": config.get("base_url", ""),
                "login_url": config.get("login_url", ""),
                "has_cookies": os.path.exists(self._cookie_file(name)),
                "login_status": self._login_status.get(name),
            })
        return result
