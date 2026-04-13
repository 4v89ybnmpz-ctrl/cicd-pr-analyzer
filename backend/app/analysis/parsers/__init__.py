"""
CI/CD 解析器模块
提供可扩展的解析器架构，支持项目映射 + 自动检测混合策略
"""
import json
import os
import logging
from typing import Dict, Any, Optional, Tuple
from .base_parser import BaseCICDParser
from .nvidia_cccl_parser import NvidiaCcclParser
from .github_actions_parser import GitHubActionsParser
from .rust_bors_parser import RustBorsParser
from .configurable_parser import ConfigurableParser, load_configurable_parsers
from .generic_parser import GenericParser

logger = logging.getLogger(__name__)

# 导出所有解析器
__all__ = [
    'BaseCICDParser',
    'NvidiaCcclParser',
    'GitHubActionsParser',
    'RustBorsParser',
    'ConfigurableParser',
    'GenericParser',
    'ParserRegistry',
]

# 默认解析器列表（按优先级排序）
DEFAULT_PARSERS = [
    RustBorsParser,      # Rust Bors 格式（最高优先级）
    NvidiaCcclParser,    # NVIDIA CCCL 格式
    GitHubActionsParser, # GitHub Actions 格式
    GenericParser,       # 通用格式（兜底）
]

# 解析器名称到类的映射，用于从配置文件加载
PARSER_CLASS_MAP = {
    'rust-bors': RustBorsParser,
    'nvidia-cccl': NvidiaCcclParser,
    'github-actions': GitHubActionsParser,
    'generic': GenericParser,
}

# 项目映射配置文件路径
PROJECT_PARSERS_CONFIG = os.path.join(os.path.dirname(__file__), 'project_parsers.json')


class ParserRegistry:
    """
    解析器注册表
    管理所有 CI/CD 解析器，支持项目映射 + 自动检测混合策略

    匹配优先级：
    1. 项目映射（owner/repo -> parser）精确匹配
    2. 项目映射通配符（owner/* -> parser）
    3. 自动检测（can_parse 内容匹配）
    4. 通用兜底解析器
    """

    def __init__(self):
        """初始化解析器注册表"""
        self._parsers = []
        # 项目映射表：key 为 (owner, repo) 或 (owner, '*')，value 为解析器名称
        self._project_map: Dict[Tuple[str, str], str] = {}
        self._load_default_parsers()
        self._load_project_map()

    def _load_default_parsers(self):
        """加载默认解析器 + 可配置解析器"""
        for parser_class in DEFAULT_PARSERS:
            self.register(parser_class())

        # 加载 JSON 规则文件中的可配置解析器
        configurable_parsers = load_configurable_parsers()
        for parser in configurable_parsers:
            self.register(parser)
            # 自动注册规则中的项目映射
            for project in parser.match_projects:
                parts = project.strip().split('/')
                if len(parts) == 2:
                    self._project_map[(parts[0].lower(), parts[1].lower())] = parser.name
                    logger.info(f"自动映射: {project} -> {parser.name}")

    def _load_project_map(self):
        """从配置文件加载项目映射"""
        config_path = PROJECT_PARSERS_CONFIG
        if not os.path.exists(config_path):
            logger.info(f"项目映射配置文件不存在: {config_path}")
            return

        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)

            mappings = config.get('project_parsers', {})
            for key, parser_name in mappings.items():
                # 支持 "owner/repo" 和 "owner/*" 格式
                parts = key.strip().split('/')
                if len(parts) == 2:
                    owner, repo = parts[0].strip(), parts[1].strip()
                    if parser_name in PARSER_CLASS_MAP:
                        self._project_map[(owner.lower(), repo.lower())] = parser_name
                        logger.info(f"加载项目映射: {owner}/{repo} -> {parser_name}")
                    else:
                        logger.warning(f"未知解析器: {parser_name}，跳过映射 {owner}/{repo}")

            logger.info(f"项目映射加载完成，共 {len(self._project_map)} 条")
        except Exception as e:
            logger.error(f"加载项目映射配置失败: {e}")

    def register(self, parser: BaseCICDParser):
        """
        注册解析器
        :param parser: 解析器实例
        """
        self._parsers.append(parser)
        # 按优先级排序
        self._parsers.sort(key=lambda p: p.priority)

    def register_project_parser(self, owner: str, repo: str, parser_name: str):
        """
        注册项目到解析器的映射
        :param owner: 仓库所有者
        :param repo: 仓库名（支持 '*' 通配符匹配该 owner 下所有仓库）
        :param parser_name: 解析器名称
        """
        if parser_name not in PARSER_CLASS_MAP:
            logger.warning(f"未知解析器: {parser_name}")
            return

        key = (owner.lower(), repo.lower())
        self._project_map[key] = parser_name
        logger.info(f"注册项目映射: {owner}/{repo} -> {parser_name}")

    def _get_parser_by_name(self, parser_name: str) -> Optional[BaseCICDParser]:
        """根据解析器名称获取解析器实例"""
        for parser in self._parsers:
            if parser.name == parser_name:
                return parser
        return None

    def get_parser(self, body: str, user: str = "",
                   owner: str = "", repo: str = "") -> BaseCICDParser:
        """
        获取适合的解析器（混合策略）

        匹配顺序：
        1. 项目精确映射 (owner/repo)
        2. 项目通配符映射 (owner/*)
        3. 内容自动检测 (can_parse)
        4. 通用兜底解析器

        :param body: 评论内容
        :param user: 用户名
        :param owner: 仓库所有者（用于项目映射）
        :param repo: 仓库名（用于项目映射）
        :return: 解析器实例
        """
        # 1. 项目精确映射
        if owner and repo:
            key = (owner.lower(), repo.lower())
            if key in self._project_map:
                parser_name = self._project_map[key]
                parser = self._get_parser_by_name(parser_name)
                if parser:
                    logger.debug(f"项目映射命中: {owner}/{repo} -> {parser_name}")
                    return parser

        # 2. 项目通配符映射 (owner/*)
        if owner:
            wildcard_key = (owner.lower(), '*')
            if wildcard_key in self._project_map:
                parser_name = self._project_map[wildcard_key]
                parser = self._get_parser_by_name(parser_name)
                if parser:
                    logger.debug(f"通配符映射命中: {owner}/* -> {parser_name}")
                    return parser

        # 3. 内容自动检测
        for parser in self._parsers:
            if parser.can_parse(body, user):
                logger.debug(f"自动检测命中: {parser.name}")
                return parser

        # 4. 通用兜底
        return self._parsers[-1]

    def parse(self, body: str, user: str = "",
              owner: str = "", repo: str = "") -> Dict[str, Any]:
        """
        解析 CI/CD 评论
        :param body: 评论内容
        :param user: 用户名
        :param owner: 仓库所有者
        :param repo: 仓库名
        :return: 解析结果
        """
        parser = self.get_parser(body, user, owner, repo)
        return parser.parse(body, user)

    def list_parsers(self) -> list:
        """列出所有已注册的解析器"""
        return [{'name': p.name, 'priority': p.priority} for p in self._parsers]

    def list_project_mappings(self) -> Dict[str, str]:
        """列出所有项目映射"""
        return {f"{k[0]}/{k[1]}": v for k, v in self._project_map.items()}

    def save_project_map(self):
        """保存项目映射到配置文件"""
        config = {
            'project_parsers': {
                f"{k[0]}/{k[1]}": v for k, v in self._project_map.items()
            }
        }
        try:
            with open(PROJECT_PARSERS_CONFIG, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            logger.info(f"项目映射已保存到: {PROJECT_PARSERS_CONFIG}")
        except Exception as e:
            logger.error(f"保存项目映射失败: {e}")


# 全局解析器注册表实例
registry = ParserRegistry()
