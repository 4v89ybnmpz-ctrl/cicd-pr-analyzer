"""
浏览器自动化模块测试
测试 BrowserManager、NetworkInterceptor、AuthManager、OpenLibingExtractor
"""
import sys
import os
import json
import asyncio

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from app.browser.manager import BrowserManager
from app.browser.interceptor import NetworkInterceptor
from app.browser.auth import AuthManager
from app.browser.extractors import OpenLibingExtractor
from app.browser.config import BROWSER_CONFIG, INTERCEPTOR_CONFIG, PLATFORM_CONFIG

results = {"total": 0, "passed": 0, "failed": 0, "errors": []}


def assert_test(condition: bool, name: str):
    results["total"] += 1
    if condition:
        print(f"  ✅ {name}")
        results["passed"] += 1
    else:
        print(f"  ❌ {name}")
        results["failed"] += 1
        results["errors"].append(name)


# ===== 配置测试 =====
print("\n🧪 配置测试")
print("-" * 50)

assert_test("browser_type" in BROWSER_CONFIG, "浏览器配置包含 browser_type")
assert_test("headless" in BROWSER_CONFIG, "浏览器配置包含 headless")
assert_test("viewport" in BROWSER_CONFIG, "浏览器配置包含 viewport")
assert_test("url_patterns" in INTERCEPTOR_CONFIG, "拦截器配置包含 url_patterns")
assert_test("openlibing" in PLATFORM_CONFIG, "平台配置包含 openlibing")
assert_test("pipeline_url_template" in PLATFORM_CONFIG["openlibing"], "openlibing 配置包含 pipeline_url_template")


# ===== BrowserManager 测试 =====
print("\n🧪 BrowserManager 测试")
print("-" * 50)

manager = BrowserManager()
assert_test(not manager.is_running, "初始状态: 未运行")
assert_test("chromium" in str(manager.get_status()), "状态包含浏览器类型")
assert_test(manager.get_status()["page_count"] == 0, "初始页面数为 0")


# ===== NetworkInterceptor 测试 =====
print("\n🧪 NetworkInterceptor 测试")
print("-" * 50)

interceptor = NetworkInterceptor()
assert_test(not interceptor.is_active, "初始状态: 未激活")
assert_test(interceptor.captured_count == 0, "初始捕获数为 0")

# 测试 URL 过滤
assert_test(interceptor._should_capture("https://api.example.com/v1/pipelines"), "捕获 API URL")
assert_test(interceptor._should_capture("https://example.com/ci/run/123"), "捕获 CI URL")
assert_test(not interceptor._should_capture("https://example.com/assets/main.js"), "忽略 JS 资源")
assert_test(not interceptor._should_capture("https://example.com/style.css"), "忽略 CSS 资源")
assert_test(not interceptor._should_capture("https://example.com/logo.png"), "忽略图片资源")

# 测试统计
stats = interceptor.get_stats()
assert_test("total_captured" in stats, "统计包含 total_captured")
assert_test("url_patterns" in stats, "统计包含 url_patterns")


# ===== AuthManager 测试 =====
print("\n🧪 AuthManager 测试")
print("-" * 50)

auth = AuthManager(cookie_dir="/tmp/test_cookies")
assert_test(isinstance(auth.list_platforms(), list), "列出平台返回列表")

platforms = auth.list_platforms()
assert_test(len(platforms) > 0, "至少有一个平台配置")
assert_test(platforms[0]["name"] == "openlibing", "第一个平台是 openlibing")
assert_test("base_url" in platforms[0], "平台信息包含 base_url")
assert_test("login_url" in platforms[0], "平台信息包含 login_url")


# ===== OpenLibingExtractor 测试 =====
print("\n🧪 OpenLibingExtractor 测试")
print("-" * 50)

extractor = OpenLibingExtractor()
assert_test(extractor.name == "openlibing", "提取器名称为 openlibing")
assert_test(len(extractor.api_patterns) > 0, "有 API 模式配置")

# 测试流水线数据提取
pipeline_api_data = [
    {
        "url": "https://api.example.com/pipeline/detail",
        "method": "GET",
        "status": 200,
        "timestamp": "2026-04-12T10:00:00Z",
        "response_body": {
            "pipelineId": "8033cdebd5e5420e9165181589392a80",
            "pipelineName": "main-ci-pipeline",
            "pipelineRunId": "4ddba58b78e04ccbbd2fd34e9a05c6fe",
            "pipelineStatus": "SUCCESS",
            "branch": "master",
            "commitId": "abc123",
            "duration": 3600,
            "creator": "ci-bot",
        }
    },
    {
        "url": "https://api.example.com/stage/list",
        "method": "GET",
        "status": 200,
        "timestamp": "2026-04-12T10:00:01Z",
        "response_body": [
            {
                "stageId": "stage-1",
                "stageName": "Build",
                "stageStatus": "SUCCESS",
                "stageSeqId": 1,
                "duration": 1200,
            },
            {
                "stageId": "stage-2",
                "stageName": "Test",
                "stageStatus": "FAILED",
                "stageSeqId": 2,
                "duration": 2400,
            }
        ]
    },
    {
        "url": "https://api.example.com/task/detail",
        "method": "GET",
        "status": 200,
        "timestamp": "2026-04-12T10:00:02Z",
        "response_body": {
            "taskId": "task-1",
            "taskName": "compile",
            "taskStatus": "SUCCESS",
            "jobId": "job-1",
            "duration": 300,
        }
    },
    # 非 API 请求（应被忽略）
    {
        "url": "https://example.com/assets/main.js",
        "method": "GET",
        "status": 200,
        "response_body": {"some": "js"},
    }
]

result = extractor.extract(pipeline_api_data)
assert_test(result["platform"] == "openlibing", "提取结果平台为 openlibing")
assert_test(result["relevant_api_calls"] >= 3, f"相关 API 调用 >= 3 (实际 {result['relevant_api_calls']})")
assert_test(len(result["pipelines"]) >= 1, f"提取到流水线 >= 1 (实际 {len(result['pipelines'])})")
assert_test(len(result["stages"]) >= 2, f"提取到阶段 >= 2 (实际 {len(result['stages'])})")
assert_test(len(result["tasks"]) >= 1, f"提取到任务 >= 1 (实际 {len(result['tasks'])})")

# 验证流水线提取结果
if result["pipelines"]:
    p = result["pipelines"][0]
    assert_test(p["status"] == "success", f"流水线状态为 success (实际 {p['status']})")
    assert_test(p["pipeline_name"] == "main-ci-pipeline", "流水线名称正确")

# 验证阶段提取结果
if len(result["stages"]) >= 2:
    assert_test(result["stages"][0]["status"] == "success", "阶段1状态为 success")
    assert_test(result["stages"][1]["status"] == "failed", "阶段2状态为 failed")

# 验证汇总
assert_test("summary" in result, "包含汇总信息")
assert_test(result["summary"]["pipeline_count"] >= 1, "汇总: 流水线数 >= 1")
assert_test(result["summary"]["stage_count"] >= 2, "汇总: 阶段数 >= 2")


# ===== Playwright 异步测试 =====
print("\n🧪 Playwright 浏览器测试")
print("-" * 50)


async def test_browser():
    """异步测试浏览器启动和页面操作"""
    mgr = BrowserManager({"headless": True, "enable_screenshots": False})

    # 启动浏览器
    success = await mgr.start()
    assert_test(success, "浏览器启动成功")
    assert_test(mgr.is_running, "浏览器运行中")

    # 创建页面
    page = await mgr.new_page("test")
    assert_test(page is not None, "创建页面成功")

    # 导航到简单页面
    nav = await mgr.navigate("https://httpbin.org/get", "test", wait_until="load")
    assert_test(nav, "导航到 httpbin 成功")

    # 获取页面内容
    content = await mgr.get_page_content("test")
    assert_test(content is not None and len(content) > 0, "获取页面内容成功")

    # 执行 JS
    result = await mgr.evaluate("document.title", "test")
    assert_test(result is not None, "执行 JS 成功")

    # 关闭浏览器
    await mgr.stop()
    assert_test(not mgr.is_running, "浏览器已关闭")


try:
    asyncio.run(test_browser())
except Exception as e:
    print(f"  ⚠️ Playwright 测试跳过: {e}")
    results["total"] += 5
    results["failed"] += 5
    for name in ["浏览器启动", "创建页面", "导航", "页面内容", "JS执行"]:
        results["errors"].append(f"Playwright: {name}")


# ===== 测试汇总 =====
print("\n" + "=" * 50)
print("📊 测试汇总")
print("=" * 50)
print(f"总测试数: {results['total']}")
print(f"✅ 通过: {results['passed']}")
print(f"❌ 失败: {results['failed']}")
if results['total'] > 0:
    print(f"通过率: {results['passed'] / results['total'] * 100:.1f}%")
if results['errors']:
    print(f"\n❌ 失败项: {results['errors']}")
