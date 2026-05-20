"""
安全功能测试脚本
测试 API Key 认证、限流、安全响应头、日志脱敏、Git 安全检查等功能
"""
import sys
import os
import time
from unittest.mock import MagicMock, patch

backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, backend_dir)

from app.core.security import (
    mask_token, mask_password, mask_url_params, mask_dict,
    APIKeyAuth, RateLimiter, SecurityHeadersConfig,
    SecurityMiddleware, run_security_check,
)

test_results = {"total": 0, "passed": 0, "failed": 0, "errors": []}


def run_test(name: str, test_func):
    """执行单个测试"""
    test_results["total"] += 1
    print(f"  [{name}] ", end="")
    try:
        test_func()
        test_results["passed"] += 1
        print("✅")
    except AssertionError as e:
        test_results["failed"] += 1
        print(f"❌ {e}")
    except Exception as e:
        test_results["failed"] += 1
        test_results["errors"].append(f"{name}: {e}")
        print(f"❌ 异常: {e}")


def make_mock_request(path: str = "/api/test", headers: dict = None,
                      query_params: dict = None, client_host: str = "127.0.0.1"):
    """创建 Mock Request 对象"""
    request = MagicMock()
    request.url = MagicMock()
    request.url.path = path
    request.url.__str__ = lambda self: f"http://localhost{path}"
    request.headers = headers or {}
    request.query_params = query_params or {}
    request.client = MagicMock()
    request.client.host = client_host
    return request


# ====================
# 日志脱敏测试
# ====================

def test_mask_token_normal():
    """Token 脱敏：正常长度"""
    result = mask_token("ghp_1234567890abcdef")
    assert result == "ghp_****cdef", f"期望 'ghp_****cdef'，实际 '{result}'"


def test_mask_token_short():
    """Token 脱敏：短字符串"""
    result = mask_token("ab")
    assert result == "****", f"期望 '****'，实际 '{result}'"


def test_mask_token_empty():
    """Token 脱敏：空字符串"""
    result = mask_token("")
    assert result == "****", f"期望 '****'，实际 '{result}'"


def test_mask_token_none():
    """Token 脱敏：None"""
    result = mask_token(None)
    assert result == "****", f"期望 '****'，实际 '{result}'"


def test_mask_password():
    """密码脱敏"""
    result = mask_password("my_secret_123")
    assert "my_secret" not in result, f"密码不应包含原始内容: {result}"
    assert "len=" in result, f"应包含长度信息: {result}"


def test_mask_password_empty():
    """密码脱敏：空值"""
    assert mask_password("") == "<empty>"
    assert mask_password(None) == "<empty>"


def test_mask_url_params():
    """URL 参数脱敏"""
    url = "http://example.com/api?api_key=secret123&name=test"
    result = mask_url_params(url)
    assert "secret123" not in result, f"URL 中的 api_key 未脱敏: {result}"
    assert "name=test" in result, f"非敏感参数被错误脱敏: {result}"


def test_mask_url_params_multiple():
    """URL 参数脱敏：多敏感参数"""
    url = "/api?token=abc&password=secret&safe=yes"
    result = mask_url_params(url)
    assert "abc" not in result
    assert "secret" not in result
    assert "safe=yes" in result


def test_mask_dict():
    """字典脱敏"""
    data = {"token": "ghp_abc123", "name": "test", "password": "secret"}
    result = mask_dict(data)
    assert result["name"] == "test", "非敏感字段不应被修改"
    assert result["token"] != "ghp_abc123", "token 字段应被脱敏"
    assert result["password"] != "secret", "password 字段应被脱敏"


def test_mask_dict_nested_key():
    """字典脱敏：包含 Authorization 键"""
    data = {"Authorization": "Bearer sk-123", "user": "admin"}
    result = mask_dict(data)
    assert result["user"] == "admin"
    assert "sk-123" not in str(result["Authorization"])


# ====================
# API Key 认证测试
# ====================

def test_auth_disabled():
    """认证关闭时所有请求通过"""
    auth = APIKeyAuth({"auth_enabled": False})
    request = make_mock_request("/api/data")
    result = auth.authenticate(request)
    assert result == "auth_disabled", f"认证关闭时应返回 'auth_disabled'，实际 '{result}'"


def test_auth_public_path():
    """公共路径免认证"""
    auth = APIKeyAuth({
        "auth_enabled": True,
        "api_keys": [{"key": "test-key", "name": "test"}],
    })
    for path in ["/", "/health", "/docs", "/openapi.json"]:
        request = make_mock_request(path)
        result = auth.authenticate(request)
        assert result == "public", f"路径 {path} 应免认证"


def test_auth_valid_header():
    """有效 API Key（请求头）"""
    auth = APIKeyAuth({
        "auth_enabled": True,
        "api_keys": [{"key": "sk-valid-key", "name": "test-user"}],
    })
    request = make_mock_request("/api/data", headers={"X-API-Key": "sk-valid-key"})
    result = auth.authenticate(request)
    assert result == "test-user", f"有效 Key 应返回用户名，实际 '{result}'"


def test_auth_valid_query():
    """有效 API Key（查询参数）"""
    auth = APIKeyAuth({
        "auth_enabled": True,
        "api_keys": [{"key": "sk-valid", "name": "user1"}],
    })
    request = make_mock_request("/api/data", query_params={"api_key": "sk-valid"})
    result = auth.authenticate(request)
    assert result == "user1"


def test_auth_valid_bearer():
    """有效 API Key（Bearer Token）"""
    auth = APIKeyAuth({
        "auth_enabled": True,
        "api_keys": [{"key": "sk-bearer", "name": "bearer-user"}],
    })
    request = make_mock_request("/api/data", headers={"Authorization": "Bearer sk-bearer"})
    result = auth.authenticate(request)
    assert result == "bearer-user"


def test_auth_invalid_key():
    """无效 API Key"""
    auth = APIKeyAuth({
        "auth_enabled": True,
        "api_keys": [{"key": "sk-valid", "name": "user"}],
    })
    request = make_mock_request("/api/data", headers={"X-API-Key": "sk-invalid"})
    result = auth.authenticate(request)
    assert result is None, f"无效 Key 应返回 None，实际 '{result}'"


def test_auth_missing_key():
    """缺少 API Key"""
    auth = APIKeyAuth({
        "auth_enabled": True,
        "api_keys": [{"key": "sk-valid", "name": "user"}],
    })
    request = make_mock_request("/api/data")
    result = auth.authenticate(request)
    assert result is None


def test_auth_disabled_key():
    """已禁用的 API Key"""
    auth = APIKeyAuth({
        "auth_enabled": True,
        "api_keys": [{"key": "sk-disabled", "name": "disabled-user", "enabled": False}],
    })
    request = make_mock_request("/api/data", headers={"X-API-Key": "sk-disabled"})
    result = auth.authenticate(request)
    assert result is None, "已禁用的 Key 应返回 None"


def test_auth_unauthorized_response():
    """401 响应格式"""
    auth = APIKeyAuth({"auth_enabled": True, "api_keys": []})
    response = auth.create_unauthorized_response()
    assert response.status_code == 401
    assert "WWW-Authenticate" in response.headers
    body = response.body
    assert b"Unauthorized" in body


def test_auth_simple_key_format():
    """简单格式 API Key（字符串列表）"""
    auth = APIKeyAuth({
        "auth_enabled": True,
        "api_keys": ["simple-key-1", "simple-key-2"],
    })
    request = make_mock_request("/api/data", headers={"X-API-Key": "simple-key-1"})
    result = auth.authenticate(request)
    assert result == "default"


def test_auth_multiple_keys():
    """多 API Key 支持"""
    auth = APIKeyAuth({
        "auth_enabled": True,
        "api_keys": [
            {"key": "key-admin", "name": "admin"},
            {"key": "key-reader", "name": "reader"},
        ],
    })
    # admin key
    req1 = make_mock_request("/api/data", headers={"X-API-Key": "key-admin"})
    assert auth.authenticate(req1) == "admin"
    # reader key
    req2 = make_mock_request("/api/data", headers={"X-API-Key": "key-reader"})
    assert auth.authenticate(req2) == "reader"


# ====================
# 限流测试
# ====================

def test_rate_limiter_disabled():
    """限流关闭"""
    limiter = RateLimiter({"enabled": False})
    request = make_mock_request()
    allowed, remaining = limiter.is_allowed(request)
    assert allowed is True


def test_rate_limiter_normal():
    """正常请求不被限流"""
    limiter = RateLimiter({"enabled": True, "window_seconds": 60, "max_requests": 5})
    for i in range(5):
        request = make_mock_request(client_host=f"10.0.0.{i % 5}")
        allowed, _ = limiter.is_allowed(request)
        assert allowed is True, f"第 {i+1} 个请求不应被限流"


def test_rate_limiter_exceeded():
    """超出限流"""
    limiter = RateLimiter({"enabled": True, "window_seconds": 60, "max_requests": 3})
    for i in range(3):
        request = make_mock_request(client_host="192.168.1.1")
        limiter.is_allowed(request)

    # 第 4 个请求应被限流
    request = make_mock_request(client_host="192.168.1.1")
    allowed, remaining = limiter.is_allowed(request)
    assert allowed is False, "超出限制后应被拒绝"
    assert remaining == 0


def test_rate_limiter_remaining():
    """剩余次数计算"""
    limiter = RateLimiter({"enabled": True, "window_seconds": 60, "max_requests": 5})
    request = make_mock_request(client_host="10.0.0.1")

    _, remaining = limiter.is_allowed(request)
    assert remaining == 4, f"第一次请求后应剩 4 次，实际 {remaining}"

    limiter.is_allowed(request)
    _, remaining = limiter.is_allowed(request)
    assert remaining == 2, f"第三次请求后应剩 2 次，实际 {remaining}"


def test_rate_limiter_different_ips():
    """不同 IP 独立计数"""
    limiter = RateLimiter({"enabled": True, "window_seconds": 60, "max_requests": 2})
    # IP1 消耗 2 次
    for _ in range(2):
        limiter.is_allowed(make_mock_request(client_host="10.0.0.1"))

    # IP2 应不受影响
    allowed, _ = limiter.is_allowed(make_mock_request(client_host="10.0.0.2"))
    assert allowed is True, "不同 IP 的限流应独立计数"


def test_rate_limiter_strict_paths():
    """严格路径限流"""
    limiter = RateLimiter({
        "enabled": True,
        "window_seconds": 60,
        "max_requests": 10,
        "strict_max_requests": 2,
        "strict_paths": ["/analysis/cicd/analyze"],
    })
    # 普通路径：允许 10 次
    for _ in range(5):
        allowed, _ = limiter.is_allowed(make_mock_request("/api/data", client_host="10.0.0.1"))
        assert allowed is True

    # 严格路径：限制 2 次
    limiter.is_allowed(make_mock_request("/analysis/cicd/analyze/rust-lang/rust", client_host="10.0.0.2"))
    limiter.is_allowed(make_mock_request("/analysis/cicd/analyze/rust-lang/rust", client_host="10.0.0.2"))
    allowed, _ = limiter.is_allowed(make_mock_request("/analysis/cicd/analyze/rust-lang/rust", client_host="10.0.0.2"))
    assert allowed is False, "严格路径超出限制应被拒绝"


def test_rate_limiter_429_response():
    """429 限流响应"""
    limiter = RateLimiter({"enabled": True, "window_seconds": 60})
    response = limiter.create_rate_limit_response(30)
    assert response.status_code == 429
    assert response.headers.get("Retry-After") == "30"
    assert b"Too Many Requests" in response.body


def test_rate_limiter_cleanup():
    """限流记录清理"""
    limiter = RateLimiter({"enabled": True, "window_seconds": 1, "max_requests": 1})
    limiter.is_allowed(make_mock_request(client_host="10.0.0.1"))
    assert len(limiter._requests) > 0

    time.sleep(1.1)
    limiter.cleanup()
    assert len(limiter._requests) == 0, "过期记录应被清理"


def test_rate_limiter_forwarded_ip():
    """X-Forwarded-For 头获取真实 IP"""
    limiter = RateLimiter({"enabled": True, "window_seconds": 60, "max_requests": 1})
    request = make_mock_request(client_host="10.0.0.1")
    request.headers = {"X-Forwarded-For": "1.2.3.4, 5.6.7.8"}
    ip = limiter._get_client_ip(request)
    assert ip == "1.2.3.4", f"应取 X-Forwarded-For 第一个 IP，实际 '{ip}'"


# ====================
# 安全响应头测试
# ====================

def test_security_headers_default():
    """默认安全响应头"""
    config = SecurityHeadersConfig({"enabled": True})
    assert config.enabled is True
    assert config.headers["X-Content-Type-Options"] == "nosniff"
    assert config.headers["X-Frame-Options"] == "DENY"
    assert "Strict-Transport-Security" in config.headers
    assert "Content-Security-Policy" in config.headers
    assert "Referrer-Policy" in config.headers


def test_security_headers_disabled():
    """安全响应头关闭"""
    config = SecurityHeadersConfig({"enabled": False})
    assert config.enabled is False


def test_security_headers_custom():
    """自定义安全响应头"""
    config = SecurityHeadersConfig({
        "enabled": True,
        "custom_headers": {"X-Custom-Header": "custom-value"},
    })
    assert config.headers["X-Custom-Header"] == "custom-value"
    # 默认头仍存在
    assert "X-Content-Type-Options" in config.headers


def test_security_headers_override():
    """覆盖默认安全响应头"""
    config = SecurityHeadersConfig({
        "enabled": True,
        "custom_headers": {"X-Frame-Options": "SAMEORIGIN"},
    })
    assert config.headers["X-Frame-Options"] == "SAMEORIGIN"


# ====================
# Git 安全检查测试
# ====================

def test_git_security_check():
    """Git 安全检查函数可执行"""
    warnings = run_security_check()
    assert isinstance(warnings, list), "应返回列表"


# ====================
# 安全中间件集成测试
# ====================

def test_middleware_auth_reject():
    """中间件认证拒绝"""
    auth = APIKeyAuth({
        "auth_enabled": True,
        "api_keys": [{"key": "sk-valid", "name": "user"}],
    })
    limiter = RateLimiter({"enabled": False})
    headers_config = SecurityHeadersConfig({"enabled": False})

    request = make_mock_request("/api/data")
    # 认证应失败
    result = auth.authenticate(request)
    assert result is None, "无 Key 的请求应被拒绝"


def test_middleware_auth_allow():
    """中间件认证通过"""
    auth = APIKeyAuth({
        "auth_enabled": True,
        "api_keys": [{"key": "sk-valid", "name": "user"}],
    })
    limiter = RateLimiter({"enabled": False})
    headers_config = SecurityHeadersConfig({"enabled": False})

    request = make_mock_request("/api/data", headers={"X-API-Key": "sk-valid"})
    result = auth.authenticate(request)
    assert result == "user"


def test_middleware_rate_limit_and_auth():
    """限流 + 认证组合"""
    auth = APIKeyAuth({
        "auth_enabled": True,
        "api_keys": [{"key": "sk-key", "name": "user"}],
    })
    limiter = RateLimiter({"enabled": True, "window_seconds": 60, "max_requests": 2})

    # 通过认证 + 未超限
    request = make_mock_request("/api/data", headers={"X-API-Key": "sk-key"}, client_host="10.0.0.1")
    assert auth.authenticate(request) == "user"
    assert limiter.is_allowed(request)[0] is True

    # 超限
    limiter.is_allowed(request)
    limiter.is_allowed(request)
    allowed, _ = limiter.is_allowed(request)
    assert allowed is False


def test_public_path_with_auth():
    """公共路径即使启用认证也免验证"""
    auth = APIKeyAuth({
        "auth_enabled": True,
        "api_keys": [{"key": "sk-key", "name": "user"}],
    })
    request = make_mock_request("/health")
    assert auth.authenticate(request) == "public"


def test_docs_static_resources():
    """文档静态资源免认证"""
    auth = APIKeyAuth({
        "auth_enabled": True,
        "api_keys": [{"key": "sk-key", "name": "user"}],
    })
    request = make_mock_request("/docs/oauth2-redirect")
    assert auth.authenticate(request) == "public"


# ====================
# 主测试入口
# ====================

def main():
    print("=" * 60)
    print("🔒 安全功能测试")
    print("=" * 60)

    sections = {
        "日志脱敏": [
            ("Token 脱敏-正常", test_mask_token_normal),
            ("Token 脱敏-短字符串", test_mask_token_short),
            ("Token 脱敏-空值", test_mask_token_empty),
            ("Token 脱敏-None", test_mask_token_none),
            ("密码脱敏-正常", test_mask_password),
            ("密码脱敏-空值", test_mask_password_empty),
            ("URL 参数脱敏-单参数", test_mask_url_params),
            ("URL 参数脱敏-多参数", test_mask_url_params_multiple),
            ("字典脱敏-基本", test_mask_dict),
            ("字典脱敏-Authorization", test_mask_dict_nested_key),
        ],
        "API Key 认证": [
            ("认证关闭", test_auth_disabled),
            ("公共路径免认证", test_auth_public_path),
            ("有效 Key-请求头", test_auth_valid_header),
            ("有效 Key-查询参数", test_auth_valid_query),
            ("有效 Key-Bearer", test_auth_valid_bearer),
            ("无效 Key", test_auth_invalid_key),
            ("缺少 Key", test_auth_missing_key),
            ("已禁用 Key", test_auth_disabled_key),
            ("401 响应格式", test_auth_unauthorized_response),
            ("简单 Key 格式", test_auth_simple_key_format),
            ("多 Key 支持", test_auth_multiple_keys),
        ],
        "请求限流": [
            ("限流关闭", test_rate_limiter_disabled),
            ("正常请求不限流", test_rate_limiter_normal),
            ("超出限流", test_rate_limiter_exceeded),
            ("剩余次数", test_rate_limiter_remaining),
            ("不同 IP 独立", test_rate_limiter_different_ips),
            ("严格路径", test_rate_limiter_strict_paths),
            ("429 响应", test_rate_limiter_429_response),
            ("过期清理", test_rate_limiter_cleanup),
            ("代理 IP 获取", test_rate_limiter_forwarded_ip),
        ],
        "安全响应头": [
            ("默认头", test_security_headers_default),
            ("关闭安全头", test_security_headers_disabled),
            ("自定义头", test_security_headers_custom),
            ("覆盖默认头", test_security_headers_override),
        ],
        "Git 安全检查": [
            ("安全检查可执行", test_git_security_check),
        ],
        "集成测试": [
            ("认证拒绝", test_middleware_auth_reject),
            ("认证通过", test_middleware_auth_allow),
            ("限流+认证组合", test_middleware_rate_limit_and_auth),
            ("公共路径免认证", test_public_path_with_auth),
            ("文档静态资源", test_docs_static_resources),
        ],
    }

    for section, tests in sections.items():
        print(f"\n📋 {section}")
        print("-" * 40)
        for name, func in tests:
            run_test(name, func)

    # 汇总
    print("\n" + "=" * 60)
    print("📊 测试汇总")
    print("=" * 60)
    print(f"总测试数: {test_results['total']}")
    print(f"✅ 通过: {test_results['passed']}")
    print(f"❌ 失败: {test_results['failed']}")
    if test_results['total'] > 0:
        rate = test_results['passed'] / test_results['total'] * 100
        print(f"通过率: {rate:.1f}%")

    if test_results['errors']:
        print("\n❌ 错误列表:")
        for error in test_results['errors']:
            print(f"  - {error}")

    print("=" * 60)
    return test_results['failed'] == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
