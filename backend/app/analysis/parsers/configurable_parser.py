"""
可配置模式解析器
通过 JSON 规则文件定义解析逻辑，无需编写代码即可支持新项目

规则文件: parser_rules.json
格式说明:
{
  "rules": [
    {
      "name": "规则名称",
      "priority": 优先级数字,
      "match_projects": ["owner/repo", "owner/*"],  // 项目映射（可选）
      "match_users": ["bot-name"],                  // 匹配的用户名
      "match_patterns": ["正则表达式"],              // 匹配的内容模式
      "status_rules": {                             // 状态判断规则
        "success": ["模式1", "模式2"],
        "failed": ["模式1"],
        "running": ["模式1"],
        "queued": ["模式1"]
      },
      "extract_rules": {                            // 字段提取规则
        "url": "正则表达式",
        "duration": "正则表达式",
        ...
      }
    }
  ]
}
"""
import re
import json
import os
import logging
from typing import Dict, Any, List, Optional
from .base_parser import BaseCICDParser

logger = logging.getLogger(__name__)

# 规则文件路径
RULES_FILE = os.path.join(os.path.dirname(__file__), 'parser_rules.json')


class ConfigurableParser(BaseCICDParser):
    """
    可配置模式解析器
    根据 JSON 规则动态匹配和解析 CI/CD 评论
    """

    # 类属性（会被实例属性覆盖）
    name = "configurable"
    priority = 50

    def __init__(self, rule: Dict[str, Any]):
        """
        根据单条规则初始化解析器
        :param rule: JSON 规则字典
        """
        self.name = rule.get('name', 'configurable')
        self.priority = rule.get('priority', 50)
        self.description = rule.get('description', '')
        self.match_projects = rule.get('match_projects', [])
        self.match_users = rule.get('match_users', [])
        self.match_patterns = rule.get('match_patterns', [])
        self.status_rules = rule.get('status_rules', {})
        self.extract_rules = rule.get('extract_rules', {})

        # 编译正则表达式
        self._compiled_match = [re.compile(p, re.IGNORECASE) for p in self.match_patterns]
        self._compiled_status = {}
        for status, patterns in self.status_rules.items():
            self._compiled_status[status] = [re.compile(p, re.IGNORECASE) for p in patterns]
        self._compiled_extract = {}
        for field, pattern in self.extract_rules.items():
            self._compiled_extract[field] = re.compile(pattern, re.IGNORECASE)

        # 调用基类初始化（设置 compiled_patterns）
        super().__init__()

    def can_parse(self, body: str, user: str = "") -> bool:
        """判断是否匹配此规则"""
        if not body:
            return False

        # 检查用户名匹配
        if self.match_users:
            user_lower = user.lower()
            for match_user in self.match_users:
                if match_user.lower() in user_lower or user_lower in match_user.lower():
                    return True

        # 检查内容模式匹配
        for pattern in self._compiled_match:
            if pattern.search(body):
                return True

        return False

    def parse(self, body: str, user: str = "") -> Dict[str, Any]:
        """根据规则解析评论"""
        result = {
            "parser": self.name,
            "build_status": "unknown",
        }

        if not body:
            return result

        # 判断构建状态
        result["build_status"] = self._determine_status(body)

        # 提取字段
        extracted = self._extract_fields(body)
        result.update(extracted)

        # 提取 URL（优先使用专用方法）
        if not result.get("url"):
            result["url"] = self._extract_url(body)

        return result

    def _determine_status(self, body: str) -> str:
        """根据状态规则判断构建状态"""
        # 按优先级检查：failed > success > running > queued
        for status in ['failed', 'success', 'running', 'queued']:
            patterns = self._compiled_status.get(status, [])
            for pattern in patterns:
                if pattern.search(body):
                    return status
        return "unknown"

    def _extract_fields(self, body: str) -> Dict[str, Any]:
        """根据提取规则提取字段"""
        extracted = {}

        for field, pattern in self._compiled_extract.items():
            match = pattern.search(body)
            if match:
                # 如果有捕获组，取第一个捕获组；否则取整个匹配
                if match.groups():
                    extracted[field] = match.group(1)
                else:
                    extracted[field] = match.group(0)

        # 特殊处理 duration
        if 'duration' in extracted:
            duration_str = extracted['duration']
            extracted['duration_seconds'] = self._parse_duration_string(duration_str)

        return extracted

    def _parse_duration_string(self, duration_str: str) -> Optional[int]:
        """解析时长字符串为秒数"""
        total = 0
        m = re.search(r'(\d+)h', duration_str)
        if m: total += int(m.group(1)) * 3600
        m = re.search(r'(\d+)m', duration_str)
        if m: total += int(m.group(1)) * 60
        m = re.search(r'(\d+)s', duration_str)
        if m: total += int(m.group(1))
        return total if total > 0 else None


def load_configurable_parsers() -> List[ConfigurableParser]:
    """
    从规则文件加载所有可配置解析器
    :return: ConfigurableParser 实例列表
    """
    parsers = []

    if not os.path.exists(RULES_FILE):
        logger.info(f"规则文件不存在: {RULES_FILE}")
        return parsers

    try:
        with open(RULES_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)

        rules = config.get('rules', [])
        for rule in rules:
            try:
                parser = ConfigurableParser(rule)
                parsers.append(parser)
                logger.info(f"加载可配置解析器: {parser.name} (priority={parser.priority})")
            except Exception as e:
                logger.warning(f"加载规则失败: {rule.get('name', '?')}, 错误: {e}")

        logger.info(f"共加载 {len(parsers)} 个可配置解析器")
    except Exception as e:
        logger.error(f"加载规则文件失败: {e}")

    return parsers
