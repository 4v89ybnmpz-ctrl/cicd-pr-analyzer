"""
配置管理模块
负责加载和管理应用配置
"""
import json
import os
from typing import Dict, Any, Optional
from pathlib import Path


class ConfigManager:
    """配置管理器"""

    def __init__(self, config_file: str = "config.json"):
        """
        初始化配置管理器
        :param config_file: 配置文件名
        """
        self.config_file = config_file
        self.config_dir = Path(__file__).parent.parent.parent  # backend目录
        self.config_path = self.config_dir / config_file
        self.config: Dict[str, Any] = {}
        self.load_config()

    def load_config(self) -> Dict[str, Any]:
        """
        加载配置文件
        :return: 配置字典
        """
        if not self.config_path.exists():
            print(f"⚠️  配置文件不存在: {self.config_path}")
            self._create_default_config()
            return self.config

        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self.config = json.load(f)
            print(f"✅ 配置文件加载成功: {self.config_path}")
            return self.config
        except json.JSONDecodeError as e:
            print(f"❌ 配置文件 JSON 格式错误: {e}")
            self._create_default_config()
            return self.config
        except Exception as e:
            print(f"❌ 加载配置文件失败: {e}")
            self._create_default_config()
            return self.config

    def _create_default_config(self):
        """创建默认配置"""
        self.config = {
            "app_name": "GitHub PR API",
            "version": "1.0.0",
            "tokens": [],
            "cache": {
                "ttl": 300
            },
            "api_settings": {
                "base_url": "https://api.github.com",
                "per_page": 100,
                "state": "all",
                "request_delay": 0.5,
                "max_workers": 3
            }
        }
        print("⚠️  使用默认配置")

    def reload_config(self) -> Dict[str, Any]:
        """
        重新加载配置文件
        :return: 新的配置字典
        """
        return self.load_config()

    def get(self, key: str, default: Any = None) -> Any:
        """
        获取配置项
        :param key: 配置键
        :param default: 默认值
        :return: 配置值
        """
        return self.config.get(key, default)

    def get_tokens(self) -> list:
        """获取 Token 列表"""
        return self.config.get("tokens", [])

    def get_cache_ttl(self) -> int:
        """获取缓存 TTL"""
        return self.config.get("cache", {}).get("ttl", 300)

    def get_api_settings(self) -> Dict[str, Any]:
        """获取 API 设置"""
        return self.config.get("api_settings", {
            "base_url": "https://api.github.com",
            "per_page": 100,
            "state": "all",
            "request_delay": 0.5,
            "max_workers": 3
        })

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return self.config.copy()


# 全局配置管理器实例
config_manager = ConfigManager()
