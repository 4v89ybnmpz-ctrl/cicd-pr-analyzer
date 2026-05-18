"""
CI/CD 评论提取器
识别和提取 CI/CD Bot 评论中的构建结果

使用可扩展的解析器架构，支持项目映射 + 自动检测混合策略
"""
import re
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
from .parsers import ParserRegistry, BaseCICDParser
from app.models.cicd_models import (
    CICDResult, BuildStatus, TestResult, CoverageInfo, CheckResult,
)

logger = logging.getLogger(__name__)


class CICDExtractor:
    """
    CI/CD 评论提取器
    识别 CI/CD Bot 评论并提取构建结果信息

    支持项目映射 + 自动检测混合策略：
    1. 已知项目通过 owner/repo 映射到指定解析器
    2. 未知项目通过评论内容自动匹配解析器
    """

    # 已知的 CI/CD Bot 用户名模式
    CICD_BOT_PATTERNS = [
        # GitHub Actions
        'github-actions[bot]',
        'actions-user',
        # Jenkins
        'jenkins-bot',
        'jenkinsci',
        # Travis CI
        'travis-ci',
        'traviscibot',
        # CircleCI
        'circleci',
        'circleci-bot',
        # GitLab CI
        'gitlab-ci-bot',
        # Azure Pipelines
        'azure-pipelines[bot]',
        # AppVeyor
        'appveyor',
        'appveyor-bot',
        # Drone
        'drone',
        'drone-bot',
        # TeamCity
        'teamcity',
        # Bitrise
        'bitrise',
        'bitrise-bot',
        # Codecov
        'codecov[bot]',
        'codecov-io[bot]',
        # Coveralls
        'coveralls[bot]',
        # SonarCloud
        'sonarcloud[bot]',
        # Danger
        'danger[bot]',
        # Dependabot (也会触发 CI)
        'dependabot[bot]',
        # Renovate
        'renovate[bot]',
    ]

    # CI/CD 评论内容模式
    CICD_CONTENT_PATTERNS = [
        r'build\s+(passed|failed|succeeded)',
        r'ci\s+(passed|failed|success)',
        r'workflow\s+(passed|failed)',
        r'pipeline\s+(passed|failed|succeeded)',
        r'checks\s+(passed|failed)',
        r'all\s+checks\s+have\s+passed',
        r'tests?\s+(passed|failed)',
        r'coverage\s*[:=]?\s*\d+\.?\d*%',
        r'test\s+coverage',
        r'build\s+status',
        r'\[build\]',
        r'\[ci\]',
        r'\[skip\s+ci\]',
        r'\[ci\s+skip\]',
        # NVIDIA CCCL
        r'CI Workflow Results',
    ]

    def __init__(self):
        """初始化 CI/CD 提取器"""
        # 编译正则表达式
        self.content_patterns = [re.compile(p, re.IGNORECASE) for p in self.CICD_CONTENT_PATTERNS]

        # 初始化解析器注册表
        self.registry = ParserRegistry()

        logger.info(f"CI/CD 提取器初始化完成")
        logger.info(f"已加载解析器: {self.registry.list_parsers()}")
        logger.info(f"已加载项目映射: {self.registry.list_project_mappings()}")

    def register_parser(self, parser: BaseCICDParser):
        """
        注册自定义解析器
        :param parser: 解析器实例
        """
        self.registry.register(parser)
        logger.info(f"注册解析器: {parser.name}, 当前解析器: {self.registry.list_parsers()}")

    def register_project_parser(self, owner: str, repo: str, parser_name: str):
        """
        注册项目到解析器的映射
        :param owner: 仓库所有者
        :param repo: 仓库名（支持 '*' 通配符）
        :param parser_name: 解析器名称
        """
        self.registry.register_project_parser(owner, repo, parser_name)

    def is_cicd_comment(self, comment: Dict[str, Any]) -> bool:
        """
        判断评论是否为 CI/CD 相关评论
        :param comment: 评论数据
        :return: 是否为 CI/CD 评论
        """
        # 检查用户名
        user = comment.get('user', '')
        if isinstance(user, dict):
            user = user.get('login', '')

        if self._is_cicd_bot(user):
            return True

        # 检查评论内容
        body = comment.get('body', '')
        if self._contains_cicd_content(body):
            return True

        # 检查 is_bot 标记
        if comment.get('is_bot', False):
            if self._contains_cicd_content(body):
                return True

        return False

    def _is_cicd_bot(self, username: str) -> bool:
        """判断用户名是否为 CI/CD Bot"""
        if not username:
            return False

        username_lower = username.lower()
        for pattern in self.CICD_BOT_PATTERNS:
            if pattern in username_lower or username_lower in pattern:
                return True

        # 检查常见命名模式
        cicd_suffixes = ['-bot', '[bot]', '_bot', '-ci', '-cd']
        for suffix in cicd_suffixes:
            if username_lower.endswith(suffix):
                return True

        return False

    def _contains_cicd_content(self, body: str) -> bool:
        """判断评论内容是否包含 CI/CD 相关信息"""
        if not body:
            return False

        for pattern in self.content_patterns:
            if pattern.search(body):
                return True

        return False

    def extract(self, comment: Dict[str, Any],
                owner: str = "", repo: str = "") -> Optional[Dict[str, Any]]:
        """
        从评论中提取 CI/CD 结果
        :param comment: 评论数据
        :param owner: 仓库所有者（用于项目映射选择解析器）
        :param repo: 仓库名（用于项目映射选择解析器）
        :return: CI/CD 结果数据
        """
        if not self.is_cicd_comment(comment):
            return None

        body = comment.get('body', '')
        user = comment.get('user', '')
        if isinstance(user, dict):
            user = user.get('login', '')

        # 使用解析器注册表解析（传入 owner/repo 支持项目映射）
        parsed = self.registry.parse(body, user, owner=owner, repo=repo)

        result = {
            'comment_id': comment.get('id'),
            'user': user,
            'cicd_type': parsed.get('parser', 'unknown'),
            'build_status': parsed.get('build_status'),
            'test_results': parsed.get('test_results'),
            'coverage': parsed.get('coverage'),
            'details': self._extract_details(body),
            'timestamp': comment.get('created_at'),
            'url': parsed.get('url'),
        }

        # 将解析器的原始结果也保存
        result['parsed_data'] = parsed

        return result

    def _extract_details(self, body: str) -> List[str]:
        """提取详细信息列表"""
        if not body:
            return []

        details = []
        lines = body.split('\n')
        keywords = ['test', 'build', 'coverage', 'check', 'passed', 'failed', 'error', 'warning']

        for line in lines:
            line = line.strip()
            if not line:
                continue

            line_lower = line.lower()
            if any(kw in line_lower for kw in keywords):
                line = re.sub(r'[#*`_\[\]]', '', line).strip()
                if line:
                    details.append(line)

        return details[:10]

    def extract_batch(self, comments: List[Dict[str, Any]],
                      owner: str = "", repo: str = "") -> List[Dict[str, Any]]:
        """
        批量提取 CI/CD 结果
        :param comments: 评论列表
        :param owner: 仓库所有者
        :param repo: 仓库名
        """
        results = []
        for comment in comments:
            try:
                result = self.extract(comment, owner=owner, repo=repo)
                if result:
                    results.append(result)
            except Exception as e:
                logger.warning(f"提取 CI/CD 结果失败: {e}")

        logger.info(f"批量提取完成，共 {len(results)} 条 CI/CD 评论")
        return results

    def get_cicd_summary(self, comments: List[Dict[str, Any]],
                         owner: str = "", repo: str = "") -> Dict[str, Any]:
        """
        获取 CI/CD 汇总统计
        :param comments: 评论列表
        :param owner: 仓库所有者
        :param repo: 仓库名
        """
        cicd_comments = self.extract_batch(comments, owner=owner, repo=repo)

        if not cicd_comments:
            return {'total': 0}

        summary = {
            'total': len(cicd_comments),
            'success_count': 0,
            'failed_count': 0,
            'pending_count': 0,
            'unknown_count': 0,
            'by_type': {},
            'by_parser': {},
            'avg_coverage': None,
        }

        coverages = []

        for item in cicd_comments:
            status = item.get('build_status')
            if status == 'success':
                summary['success_count'] += 1
            elif status == 'failed':
                summary['failed_count'] += 1
            elif status == 'pending':
                summary['pending_count'] += 1
            else:
                summary['unknown_count'] += 1

            # 按解析器类型统计
            parser = item.get('cicd_type', 'unknown')
            summary['by_parser'][parser] = summary['by_parser'].get(parser, 0) + 1

            coverage = item.get('coverage', {})
            if coverage and 'percentage' in coverage:
                coverages.append(coverage['percentage'])

        if coverages:
            summary['avg_coverage'] = round(sum(coverages) / len(coverages), 2)

        return summary

    def list_parsers(self) -> list:
        """列出所有已注册的解析器"""
        return self.registry.list_parsers()

    def list_project_mappings(self) -> Dict[str, str]:
        """列出所有项目映射"""
        return self.registry.list_project_mappings()

    def save_project_map(self):
        """保存项目映射到配置文件"""
        self.registry.save_project_map()

    def extract_structured(self, comment: Dict[str, Any],
                           owner: str = "", repo: str = "",
                           pr_number: int = None) -> Optional[CICDResult]:
        """
        从评论中提取 CI/CD 结果，返回结构化 CICDResult 模型
        :param comment: 评论数据
        :param owner: 仓库所有者
        :param repo: 仓库名
        :param pr_number: PR 编号
        :return: CICDResult 模型实例
        """
        if not self.is_cicd_comment(comment):
            return None

        body = comment.get('body', '')
        user = comment.get('user', '')
        if isinstance(user, dict):
            user = user.get('login', '')

        # 使用解析器注册表解析
        parsed = self.registry.parse(body, user, owner=owner, repo=repo)

        # 构建结构化模型
        kwargs = {
            "owner": owner or "",
            "repo": repo or "",
            "parser_name": parsed.get('parser', 'unknown'),
            "build_status": parsed.get('build_status', 'unknown'),
            "url": parsed.get('url'),
            "comment_id": str(comment.get('id')) if comment.get('id') else None,
            "user": user,
            "pr_number": pr_number,
            "comment_created_at": comment.get('created_at'),
            "analyzed_at": datetime.now(),
            "raw_parsed": parsed,
        }

        # 耗时
        if parsed.get('duration_seconds') is not None:
            kwargs["duration_seconds"] = parsed['duration_seconds']

        # 覆盖率
        coverage_data = parsed.get('coverage')
        if coverage_data and isinstance(coverage_data, dict):
            kwargs["coverage"] = CoverageInfo(**coverage_data)

        # 检查结果 (GitHub Actions)
        checks_data = parsed.get('checks')
        if checks_data and isinstance(checks_data, dict):
            kwargs["checks"] = CheckResult(**checks_data)

        # 测试结果 (Generic)
        test_data = parsed.get('test_results')
        if test_data and isinstance(test_data, dict):
            kwargs["test_results"] = TestResult(**test_data)

        # NVIDIA CCCL 特有
        for field in ('pass_rate', 'pass_count', 'hits_rate', 'hits_count'):
            if parsed.get(field) is not None:
                kwargs[field] = parsed[field]

        # Rust Bors 特有
        for field in ('commit', 'merge_commit', 'approver', 'build_type'):
            if parsed.get(field) is not None:
                kwargs[field] = parsed[field]
        if parsed.get('failed_jobs') is not None:
            kwargs["failed_jobs"] = parsed['failed_jobs']

        # 详细信息
        kwargs["details"] = self._extract_details(body)

        try:
            return CICDResult(**kwargs)
        except Exception as e:
            logger.warning(f"构建 CICDResult 失败: {e}, 原始数据: {parsed}")
            return None

    def extract_batch_structured(self, comments: List[Dict[str, Any]],
                                 owner: str = "", repo: str = "",
                                 pr_number: int = None) -> List[CICDResult]:
        """
        批量提取 CI/CD 结果，返回 CICDResult 列表
        """
        results = []
        for comment in comments:
            try:
                result = self.extract_structured(comment, owner=owner, repo=repo, pr_number=pr_number)
                if result:
                    results.append(result)
            except Exception as e:
                logger.warning(f"提取 CI/CD 结果失败: {e}")
        logger.info(f"批量结构化提取完成，共 {len(results)} 条 CI/CD 评论")
        return results
