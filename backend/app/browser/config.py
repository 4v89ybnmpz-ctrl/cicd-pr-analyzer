"""
浏览器配置
"""
import os

# 浏览器配置
BROWSER_CONFIG = {
    # 浏览器类型: chromium, firefox, webkit
    "browser_type": "chromium",

    # 是否无头模式
    "headless": True,

    # 页面超时（毫秒）
    "default_timeout": 30000,

    # 导航超时
    "navigation_timeout": 30000,

    # 视口大小
    "viewport": {"width": 1920, "height": 1080},

    # 用户代理
    "user_agent": None,  # None 使用默认

    # 慢动作延迟（毫秒），调试用
    "slow_mo": 0,

    # 是否启用截图
    "enable_screenshots": True,

    # 截图保存目录
    "screenshot_dir": os.path.join(os.path.dirname(__file__), '..', '..', 'logs', 'screenshots'),

    # Cookie 持久化目录
    "cookie_dir": os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'cookies'),
}

# 网络拦截配置
INTERCEPTOR_CONFIG = {
    # 只捕获这些 URL 模式的请求（正则）
    "url_patterns": [
        r"/api/",
        r"/v1/",
        r"/v2/",
        r"/rest/",
        r"/ci/",
        r"pipeline",
    ],

    # 忽略这些请求（静态资源等）
    "ignore_patterns": [
        r"\.(js|css|png|jpg|svg|ico|woff|ttf|map)$",
        r"/assets/",
        r"/_app\.",
    ],

    # 最大捕获数量
    "max_captures": 1000,

    # 请求超时
    "request_timeout": 30000,
}

# 平台登录配置
PLATFORM_CONFIG = {
    "openlibing": {
        "name": "openLiBing",
        "base_url": "https://www.openlibing.com",
        "login_url": "https://www.openlibing.com/login",
        "login_check_url": "https://www.openlibing.com/",
        # 登录检测：页面中存在此元素说明已登录
        "login_indicator": "[data-testid='user-avatar'], .user-info, .ant-avatar",
        # 登录表单选择器
        "username_selector": "input[placeholder*='用户'], input[name='username'], #username",
        "password_selector": "input[placeholder*='密码'], input[name='password'], #password",
        "submit_selector": "button[type='submit'], .login-btn, button:has-text('登录')",
        # 流水线页面 URL 模板
        "pipeline_url_template": "https://www.openlibing.com/apps/pipelineDetail?pipelineId={pipeline_id}&pipelineRunId={pipeline_run_id}&projectId={project_id}",
        # 流水线列表 API 可能的路径
        "pipeline_api_patterns": [
            r".*pipeline.*",
            r".*project.*build.*",
            r".*ci.*run.*",
        ],
    },
}
