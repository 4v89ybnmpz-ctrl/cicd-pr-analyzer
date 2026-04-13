"""
AtomGit API 配置
"""
import os

ATOMGIT_CONFIG = {
    # API 基础地址
    "base_url": "https://api.atomgit.com/api/v5",

    # Token（从 config.json 或环境变量读取）
    "access_token": "",

    # 请求配置
    "per_page": 20,
    "request_delay": 0.5,
    "max_retries": 3,
    "timeout": 30,
}
