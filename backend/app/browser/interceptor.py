"""
网络请求拦截器
通过 Playwright 的 route 机制拦截和捕获 API 请求/响应
"""
import re
import json
import time
import logging
from typing import Dict, Any, List, Optional, Callable
from datetime import datetime
from playwright.async_api import Page, Route, Request, Response

from .config import INTERCEPTOR_CONFIG

logger = logging.getLogger(__name__)


class CapturedRequest:
    """捕获的请求数据"""

    def __init__(self, request: Request, response: Response = None, body: bytes = None):
        self.url = request.url
        self.method = request.method
        self.status = response.status if response else None
        self.headers = dict(request.headers) if request.headers else {}
        self.response_headers = dict(response.headers) if response and response.headers else {}
        self.post_data = request.post_data
        self.body = body
        self.timestamp = datetime.now().isoformat()
        self.resource_type = request.resource_type
        self.duration_ms = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        result = {
            "url": self.url,
            "method": self.method,
            "status": self.status,
            "resource_type": self.resource_type,
            "timestamp": self.timestamp,
            "duration_ms": self.duration_ms,
        }

        # 解析响应体
        if self.body:
            try:
                body_str = self.body.decode("utf-8")
                # 尝试解析 JSON
                try:
                    result["response_body"] = json.loads(body_str)
                except json.JSONDecodeError:
                    result["response_body_text"] = body_str[:2000]
            except UnicodeDecodeError:
                result["response_body_size"] = len(self.body)

        if self.post_data:
            result["post_data"] = self.post_data[:2000]

        return result


class NetworkInterceptor:
    """
    网络请求拦截器
    捕获页面上发出的 API 请求及其响应，用于提取内部平台数据
    """

    def __init__(self, config: Dict[str, Any] = None):
        """
        初始化拦截器
        :param config: 配置覆盖
        """
        self.config = {**INTERCEPTOR_CONFIG, **(config or {})}
        self._captured: List[CapturedRequest] = []
        self._pending: Dict[str, Dict[str, Any]] = {}
        self._callbacks: List[Callable] = []
        self._is_active = False

        # 编译 URL 模式
        self._url_patterns = [
            re.compile(p) for p in self.config["url_patterns"]
        ]
        self._ignore_patterns = [
            re.compile(p) for p in self.config["ignore_patterns"]
        ]

    @property
    def is_active(self) -> bool:
        """拦截器是否激活"""
        return self._is_active

    @property
    def captured_count(self) -> int:
        """已捕获的请求数"""
        return len(self._captured)

    def _should_capture(self, url: str) -> bool:
        """判断 URL 是否应该被捕获"""
        # 先检查忽略模式
        for pattern in self._ignore_patterns:
            if pattern.search(url):
                return False

        # 再检查匹配模式
        for pattern in self._url_patterns:
            if pattern.search(url):
                return True

        return False

    def on_captured(self, callback: Callable):
        """
        注册捕获回调
        :param callback: 回调函数，接收 CapturedRequest 参数
        """
        self._callbacks.append(callback)

    async def attach(self, page: Page):
        """
        将拦截器附加到页面
        :param page: Playwright Page 实例
        """
        # 监听请求
        page.on("request", self._on_request)
        # 监听响应
        page.on("response", self._on_response)

        self._is_active = True
        logger.info(f"网络拦截器已附加到页面，监控 {len(self._url_patterns)} 个 URL 模式")

    async def detach(self):
        """分离拦截器"""
        self._is_active = False
        logger.info(f"网络拦截器已分离，共捕获 {len(self._captured)} 个请求")

    async def _on_request(self, request: Request):
        """请求事件处理"""
        if not self._should_capture(request.url):
            return

        request_id = f"{request.method}:{request.url}"

        self._pending[request_id] = {
            "request": request,
            "start_time": time.time(),
        }

        logger.debug(f"捕获请求: {request.method} {request.url[:100]}")

    async def _on_response(self, response: Response):
        """响应事件处理"""
        request = response.request
        if not self._should_capture(request.url):
            return

        request_id = f"{request.method}:{request.url}"

        # 获取响应体
        try:
            body = await response.body()
        except Exception as e:
            logger.warning(f"获取响应体失败: {request.url[:80]}, 错误: {e}")
            body = None

        # 创建捕获记录
        captured = CapturedRequest(request, response, body)

        # 计算耗时
        pending = self._pending.pop(request_id, None)
        if pending:
            captured.duration_ms = int((time.time() - pending["start_time"]) * 1000)

        # 存储
        if len(self._captured) < self.config["max_captures"]:
            self._captured.append(captured)

        # 触发回调
        for callback in self._callbacks:
            try:
                callback(captured)
            except Exception as e:
                logger.warning(f"捕获回调执行失败: {e}")

        logger.debug(
            f"捕获响应: {response.status} {request.method} {request.url[:80]} "
            f"({captured.duration_ms}ms)"
        )

    def get_captured(self, url_pattern: str = None,
                     method: str = None,
                     status: int = None) -> List[Dict[str, Any]]:
        """
        获取捕获的请求数据
        :param url_pattern: URL 过滤模式（正则）
        :param method: HTTP 方法过滤
        :param status: 状态码过滤
        :return: 匹配的请求数据列表
        """
        results = []

        for captured in self._captured:
            # URL 过滤
            if url_pattern and not re.search(url_pattern, captured.url):
                continue
            # 方法过滤
            if method and captured.method.upper() != method.upper():
                continue
            # 状态码过滤
            if status and captured.status != status:
                continue

            results.append(captured.to_dict())

        return results

    def get_api_responses(self, url_pattern: str = None) -> List[Dict[str, Any]]:
        """
        获取 API 响应数据（只返回有 JSON 响应体的）
        :param url_pattern: URL 过滤模式
        :return: API 响应列表
        """
        captured = self.get_captured(url_pattern=url_pattern)
        return [c for c in captured if "response_body" in c and isinstance(c["response_body"], (dict, list))]

    def clear(self):
        """清空捕获数据"""
        self._captured.clear()
        self._pending.clear()
        logger.info("捕获数据已清空")

    def get_stats(self) -> Dict[str, Any]:
        """获取拦截器统计"""
        status_counts = {}
        for c in self._captured:
            status = c.status or 0
            status_counts[status] = status_counts.get(status, 0) + 1

        return {
            "is_active": self._is_active,
            "total_captured": len(self._captured),
            "pending_count": len(self._pending),
            "status_counts": status_counts,
            "url_patterns": self.config["url_patterns"],
        }
