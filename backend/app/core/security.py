"""
安全模块
提供 API 认证、限流、安全响应头、日志脱敏等安全功能
"""
import os
import re
import time
import logging
import hashlib
from typing import Dict, Any, Optional, List, Callable
from collections import defaultdict
from functools import wraps
from threading import Lock

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

logger = logging.getLogger(__name__)


# ====================
# 日志脱敏工具
# ====================

def mask_token(token: str, visible_chars: int = 4) -> str:
    """
    脱敏 Token/密钥类字符串
    保留前 N 位和后 N 位，中间用 **** 替代
    :param token: 原始 Token
    :param visible_chars: 前后保留的可见字符数
    :return: 脱敏后的字符串
    """
    if not token or len(token) <= visible_chars * 2:
        return "****"
    return f"{token[:visible_chars]}{'*' * 4}{token[-visible_chars:]}"


def mask_password(password: str) -> str:
    """脱敏密码，只显示长度"""
    if not password:
        return "<empty>"
    return f"<password len={len(password)}>"


def mask_url_params(url: str, sensitive_params: List[str] = None) -> str:
    """
    脱敏 URL 中的敏感查询参数
    :param url: 原始 URL
    :param sensitive_params: 需要脱敏的参数名列表
    :return: 脱敏后的 URL
    """
    if sensitive_params is None:
        sensitive_params = ["api_key", "token", "password", "secret", "key"]

    result = url
    for param in sensitive_params:
        # 匹配 param=value 模式
        pattern = rf'({param}=)([^&]+)'
        result = re.sub(pattern, r'\1****', result, flags=re.IGNORECASE)
    return result


def mask_dict(data: Dict[str, Any], sensitive_keys: List[str] = None) -> Dict[str, Any]:
    """
    脱敏字典中的敏感字段
    :param data: 原始字典
    :param sensitive_keys: 敏感字段名列表
    :return: 脱敏后的字典（浅拷贝）
    """
    if sensitive_keys is None:
        sensitive_keys = [
            "password", "token", "secret", "api_key", "apiKey",
            "authorization", "cookie", "session"
        ]

    masked = {}
    for key, value in data.items():
        lower_key = key.lower()
        if any(sk in lower_key for sk in sensitive_keys):
            if isinstance(value, str):
                masked[key] = mask_token(value)
            else:
                masked[key] = "****"
        else:
            masked[key] = value
    return masked


# ====================
# API Key 认证
# ====================

# 免认证路径（公共接口）
PUBLIC_PATHS = {
    "/", "/health", "/docs", "/openapi.json", "/redoc",
    "/monitor/status",
}


class APIKeyAuth:
    """API Key 认证管理器"""

    def __init__(self, config: Dict[str, Any]):
        """
        初始化认证管理器
        :param config: security 配置节
        """
        self.enabled = config.get("auth_enabled", False)
        self.keys: Dict[str, Dict[str, Any]] = {}

        # 加载 API Keys
        api_keys = config.get("api_keys", [])
        for key_entry in api_keys:
            if isinstance(key_entry, str):
                # 简单格式: 直接是 key 字符串
                self.keys[key_entry] = {"name": "default", "enabled": True}
            elif isinstance(key_entry, dict):
                # 详细格式: {"key": "...", "name": "...", "enabled": true}
                key_value = key_entry.get("key", "")
                if key_value:
                    self.keys[key_value] = {
                        "name": key_entry.get("name", "unnamed"),
                        "enabled": key_entry.get("enabled", True),
                    }

        if self.enabled:
            logger.info(f"API Key 认证已启用，已加载 {len(self.keys)} 个有效 Key")
        else:
            logger.info("API Key 认证未启用")

    def is_public_path(self, path: str) -> bool:
        """判断路径是否为公共路径（免认证）"""
        # 精确匹配
        if path in PUBLIC_PATHS:
            return True
        # 前缀匹配: /docs/ 开头的静态资源
        if path.startswith("/docs/") or path.startswith("/redoc/"):
            return True
        return False

    def authenticate(self, request: Request) -> Optional[str]:
        """
        验证请求的 API Key
        :param request: FastAPI 请求对象
        :return: 认证通过的 Key 名称，失败返回 None
        """
        if not self.enabled:
            return "auth_disabled"

        # 公共路径免认证
        if self.is_public_path(request.url.path):
            return "public"

        # 从请求头获取
        api_key = request.headers.get("X-API-Key")

        # 从查询参数获取
        if not api_key:
            api_key = request.query_params.get("api_key")

        # 从 Authorization 头获取 (Bearer 格式)
        if not api_key:
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                api_key = auth_header[7:]

        # 验证 Key
        if not api_key:
            return None

        key_info = self.keys.get(api_key)
        if key_info is None:
            return None

        if not key_info.get("enabled", True):
            return None

        return key_info.get("name", "unknown")

    def create_unauthorized_response(self) -> JSONResponse:
        """创建 401 未认证响应"""
        return JSONResponse(
            status_code=401,
            content={
                "error": "Unauthorized",
                "message": "Valid API Key required. Provide via X-API-Key header or api_key query parameter.",
            },
            headers={"WWW-Authenticate": 'Bearer realm="API"'},
        )


# ====================
# 请求限流
# ====================

class RateLimiter:
    """基于 IP 的请求限流器（滑动窗口算法）"""

    def __init__(self, config: Dict[str, Any]):
        """
        初始化限流器
        :param config: security.rate_limit 配置节
        """
        self.enabled = config.get("enabled", True)
        self.window_seconds = config.get("window_seconds", 60)
        self.max_requests = config.get("max_requests", 60)
        self.strict_max_requests = config.get("strict_max_requests", 20)
        # 严格限流路径前缀（写入类操作）
        self.strict_paths = config.get("strict_paths", [
            "/github/prs/details/batch",
            "/analysis/cicd/analyze",
            "/agent/analyze",
            "/browser/fetch",
        ])

        # 请求记录: {ip: [(timestamp, ...), ...]}
        self._requests: Dict[str, List[float]] = defaultdict(list)
        self._lock = Lock()

        if self.enabled:
            logger.info(
                f"请求限流已启用: {self.max_requests}次/{self.window_seconds}秒, "
                f"严格路径 {self.strict_max_requests}次/{self.window_seconds}秒"
            )

    def _get_client_ip(self, request: Request) -> str:
        """获取客户端真实 IP（支持代理头）"""
        forwarded = request.headers.get("X-Forwarded-For", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
        real_ip = request.headers.get("X-Real-IP", "")
        if real_ip:
            return real_ip.strip()
        return request.client.host if request.client else "unknown"

    def _get_limit_for_path(self, path: str) -> int:
        """根据路径获取限流上限"""
        for strict_path in self.strict_paths:
            if path.startswith(strict_path):
                return self.strict_max_requests
        return self.max_requests

    def is_allowed(self, request: Request) -> tuple[bool, int]:
        """
        检查请求是否被允许
        :param request: FastAPI 请求对象
        :return: (是否允许, 剩余可用次数)
        """
        if not self.enabled:
            return True, self.max_requests

        ip = self._get_client_ip(request)
        path = request.url.path
        max_req = self._get_limit_for_path(path)
        now = time.time()

        with self._lock:
            # 清理过期记录
            self._requests[ip] = [
                t for t in self._requests[ip]
                if now - t < self.window_seconds
            ]

            remaining = max(0, max_req - len(self._requests[ip]))
            if len(self._requests[ip]) >= max_req:
                return False, 0

            self._requests[ip].append(now)
            return True, remaining - 1

    def create_rate_limit_response(self, retry_after: int = None) -> JSONResponse:
        """创建 429 限流响应"""
        if retry_after is None:
            retry_after = self.window_seconds
        return JSONResponse(
            status_code=429,
            content={
                "error": "Too Many Requests",
                "message": f"Rate limit exceeded. Retry after {retry_after} seconds.",
            },
            headers={"Retry-After": str(retry_after)},
        )

    def cleanup(self):
        """清理过期的请求记录，防止内存泄漏"""
        now = time.time()
        with self._lock:
            expired_ips = []
            for ip, timestamps in self._requests.items():
                self._requests[ip] = [
                    t for t in timestamps if now - t < self.window_seconds
                ]
                if not self._requests[ip]:
                    expired_ips.append(ip)
            for ip in expired_ips:
                del self._requests[ip]


# ====================
# 安全响应头
# ====================

DEFAULT_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "X-XSS-Protection": "1; mode=block",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "Content-Security-Policy": "default-src 'self'",
    "Referrer-Policy": "strict-origin-when-cross-origin",
}


class SecurityHeadersConfig:
    """安全响应头配置"""

    def __init__(self, config: Dict[str, Any]):
        self.enabled = config.get("enabled", True)
        custom_headers = config.get("custom_headers", {})
        self.headers = {**DEFAULT_SECURITY_HEADERS, **custom_headers}


# ====================
# 安全中间件
# ====================

class SecurityMiddleware(BaseHTTPMiddleware):
    """统一安全中间件：认证 + 限流 + 安全响应头"""

    def __init__(self, app, auth: APIKeyAuth, rate_limiter: RateLimiter,
                 headers_config: SecurityHeadersConfig):
        super().__init__(app)
        self.auth = auth
        self.rate_limiter = rate_limiter
        self.headers_config = headers_config

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # 1. API Key 认证检查
        identity = self.auth.authenticate(request)
        if identity is None:
            logger.warning(f"认证失败: {mask_url_params(str(request.url))}")
            return self.auth.create_unauthorized_response()

        # 2. 请求限流检查
        allowed, remaining = self.rate_limiter.is_allowed(request)
        if not allowed:
            logger.warning(f"限流触发: IP={self.rate_limiter._get_client_ip(request)} path={request.url.path}")
            response = self.rate_limiter.create_rate_limit_response()
        else:
            # 3. 正常处理请求
            response = await call_next(request)

        # 4. 注入安全响应头
        if self.headers_config.enabled:
            for header_name, header_value in self.headers_config.headers.items():
                response.headers[header_name] = header_value

        # 5. 添加限流信息头
        if self.rate_limiter.enabled:
            max_req = self.rate_limiter._get_limit_for_path(request.url.path)
            response.headers["X-RateLimit-Limit"] = str(max_req)
            response.headers["X-RateLimit-Remaining"] = str(remaining)

        return response


# ====================
# Git 安全检查
# ====================

def check_git_security(repo_root: str = None) -> List[str]:
    """
    检查 Git 仓库中是否存在敏感文件被追踪
    :param repo_root: 仓库根目录
    :return: 告警消息列表
    """
    warnings = []

    if repo_root is None:
        # 向上查找 git 根目录
        current = os.path.dirname(os.path.abspath(__file__))
        while current != "/":
            if os.path.exists(os.path.join(current, ".git")):
                repo_root = current
                break
            current = os.path.dirname(current)

    if repo_root is None or not os.path.exists(os.path.join(repo_root, ".git")):
        return warnings

    # 检查敏感文件模式
    sensitive_patterns = [
        "backend/config.json",
        "backend/encryption_key.json",
        "encryption_key.json",
        "backend/secrets/",
        ".env",
        ".env.local",
    ]

    # 读取 git 追踪的文件列表
    tracked_file = os.path.join(repo_root, ".git", "index")
    if not os.path.exists(tracked_file):
        return warnings

    try:
        import subprocess
        result = subprocess.run(
            ["git", "ls-files"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=5,
        )
        tracked_files = set(result.stdout.strip().split("\n")) if result.stdout.strip() else set()
    except Exception:
        return warnings

    for pattern in sensitive_patterns:
        for f in tracked_files:
            if pattern.endswith("/"):
                if f.startswith(pattern):
                    warnings.append(f"敏感文件被 Git 追踪: {f}")
            elif f == pattern:
                warnings.append(f"敏感文件被 Git 追踪: {f}")

    return warnings


def run_security_check():
    """启动时执行安全检查，输出告警"""
    warnings = check_git_security()
    for w in warnings:
        logger.warning(f"[安全告警] {w}")
    if not warnings:
        logger.info("[安全检查] Git 追踪文件检查通过，未发现敏感文件泄露")
    return warnings
