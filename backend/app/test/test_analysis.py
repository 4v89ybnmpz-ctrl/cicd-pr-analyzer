"""
分析模块测试用例
测试数据清洗、CI/CD 提取、项目映射 + 自动检测混合策略
"""
import sys
import os
import json

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from app.analysis import DataCleaner, CICDExtractor
from app.analysis.parsers import ParserRegistry
from app.analysis.parsers.nvidia_cccl_parser import NvidiaCcclParser
from app.analysis.parsers.github_actions_parser import GitHubActionsParser
from app.analysis.parsers.generic_parser import GenericParser

# 测试结果统计
results = {"total": 0, "passed": 0, "failed": 0, "errors": []}


def assert_test(condition: bool, name: str):
    """断言测试结果"""
    results["total"] += 1
    if condition:
        print(f"  ✅ {name}")
        results["passed"] += 1
    else:
        print(f"  ❌ {name}")
        results["failed"] += 1
        results["errors"].append(name)


# ========== DataCleaner 测试 ==========
print("\n🧪 DataCleaner 测试")
print("-" * 50)

cleaner = DataCleaner()

# 测试文本清洗
comment = {
    'id': 1,
    'body': '  Hello\x00 World  <b>bold</b>  ',
    'user': {'login': 'test-bot', 'name': 'Test Bot'},
    'created_at': '2026-03-26T23:30:14Z',
}
cleaned = cleaner.clean_comment(comment)
assert_test(cleaned.get('body') == 'Hello World bold', "文本清洗：去无效字符+HTML+空白")
assert_test(cleaned.get('_cleaned') is True, "清洗标记")
assert_test('T' in cleaned.get('created_at', ''), "时间标准化")

# 测试元数据提取
meta = cleaner.extract_comment_metadata(comment)
assert_test(meta['has_link'] is False, "元数据：无链接")
assert_test(meta['is_bot'] is False, "元数据：非Bot")

# 测试有效评论过滤
comments = [
    {'body': '', 'user_type': 'User'},
    {'body': 'ok', 'user_type': 'User'},
    {'body': 'This is a valid comment', 'user_type': 'User'},
    {'body': 'This branch was successfully merged', 'user_type': 'Bot'},
]
valid = cleaner.filter_valid_comments(comments)
assert_test(len(valid) == 1, "过滤有效评论：排除空/短/系统评论")


# ========== CICDExtractor 基础测试 ==========
print("\n🧪 CICDExtractor 基础测试")
print("-" * 50)

extractor = CICDExtractor()

# NVIDIA CCCL 格式评论
nvidia_comment = {
    'id': 100,
    'user': 'github-actions[bot]',
    'user_type': 'Bot',
    'is_bot': True,
    'body': '## 😬 CI Workflow Results\n\n### 🟥 Finished in 12m 41s: Pass:  10%/48  | Total:  2h 20m | Max: 12m 22s | Hits: 100%/1110\n\nSee results [here](https://github.com/NVIDIA/cccl/actions/runs/23622748175).',
    'created_at': '2026-03-26T23:30:14Z',
}

assert_test(extractor.is_cicd_comment(nvidia_comment), "识别 NVIDIA CI/CD 评论")
result = extractor.extract(nvidia_comment)
assert_test(result is not None, "提取结果非空")
assert_test(result['build_status'] == 'failed', "NVIDIA: build_status=failed")
assert_test(result['parsed_data']['pass_rate'] == 10.0, "NVIDIA: pass_rate=10%")
assert_test(result['parsed_data']['duration_seconds'] == 761, "NVIDIA: duration=761s")
assert_test(result['parsed_data']['hits_rate'] == 100.0, "NVIDIA: hits_rate=100%")

# NVIDIA 成功格式
nvidia_success = {
    'id': 101,
    'user': 'github-actions[bot]',
    'user_type': 'Bot',
    'is_bot': True,
    'body': '## 🥳 CI Workflow Results\n\n### 🟩 Finished in 52m 49s: Pass: 100%/48  | Total: 21h 13m | Max: 42m 34s | Hits:  53%/26011\n\nSee results [here](https://github.com/NVIDIA/cccl/actions/runs/12345).',
    'created_at': '2026-03-27T01:00:00Z',
}
result = extractor.extract(nvidia_success)
assert_test(result['build_status'] == 'success', "NVIDIA 成功: build_status=success")
assert_test(result['parsed_data']['pass_rate'] == 100.0, "NVIDIA 成功: pass_rate=100%")

# GitHub Actions 格式评论
gh_comment = {
    'id': 200,
    'user': 'github-actions[bot]',
    'user_type': 'Bot',
    'is_bot': True,
    'body': '✅ All checks have passed\n2 successful checks, 0 failed checks',
    'created_at': '2026-03-27T02:00:00Z',
}
result = extractor.extract(gh_comment)
assert_test(result is not None, "提取 GitHub Actions 评论")
assert_test(result['cicd_type'] == 'github-actions', "GitHub Actions: cicd_type")
assert_test(result['build_status'] == 'success', "GitHub Actions: build_status=success")

# 非 CI/CD 评论
normal_comment = {
    'id': 300,
    'user': 'developer',
    'user_type': 'User',
    'is_bot': False,
    'body': 'Looks good to me, approved!',
    'created_at': '2026-03-27T03:00:00Z',
}
assert_test(not extractor.is_cicd_comment(normal_comment), "排除非 CI/CD 评论")


# ========== 项目映射 + 自动检测 混合策略测试 ==========
print("\n🧪 项目映射 + 自动检测 混合策略测试")
print("-" * 50)

# 测试项目映射加载
mappings = extractor.list_project_mappings()
print(f"  已加载映射: {mappings}")
assert_test('nvidia/cccl' in mappings, "项目映射：NVIDIA/cccl 已加载")
assert_test('nvidia/*' in mappings, "项目映射：NVIDIA/* 通配符已加载")

# 测试1: 精确映射 - NVIDIA/cccl 应使用 nvidia-cccl 解析器
result = extractor.extract(nvidia_comment, owner="NVIDIA", repo="cccl")
assert_test(result['cicd_type'] == 'nvidia-cccl', "精确映射: NVIDIA/cccl -> nvidia-cccl")

# 测试2: 通配符映射 - NVIDIA/其他仓库 也应使用 nvidia-cccl 解析器
nvidia_other_comment = {
    'id': 102,
    'user': 'github-actions[bot]',
    'user_type': 'Bot',
    'is_bot': True,
    'body': '## 🥳 CI Workflow Results\n\n### 🟩 Finished in 5m 10s: Pass: 90%/20\n\nSee results [here](https://github.com/NVIDIA/other/actions/runs/999).',
    'created_at': '2026-03-27T04:00:00Z',
}
result = extractor.extract(nvidia_other_comment, owner="NVIDIA", repo="other-repo")
assert_test(result['cicd_type'] == 'nvidia-cccl', "通配符映射: NVIDIA/other-repo -> nvidia-cccl")

# 测试3: 无映射项目 - 走自动检测
result = extractor.extract(gh_comment, owner="some-owner", repo="some-repo")
assert_test(result['cicd_type'] == 'github-actions', "无映射: 自动检测 -> github-actions")

# 测试4: 无映射且无法自动检测 - 走兜底 generic
generic_comment = {
    'id': 400,
    'user': 'ci-bot',
    'user_type': 'Bot',
    'is_bot': True,
    'body': 'build passed successfully',
    'created_at': '2026-03-27T05:00:00Z',
}
result = extractor.extract(generic_comment, owner="unknown", repo="project")
assert_test(result['cicd_type'] == 'generic', "兜底: 无映射+无匹配 -> generic")

# 测试5: 动态注册项目映射
extractor.register_project_parser("tensorflow", "tensorflow", "github-actions")
mappings = extractor.list_project_mappings()
assert_test('tensorflow/tensorflow' in mappings, "动态注册: tensorflow/tensorflow 映射")

# 测试6: ParserRegistry 直接测试
registry = ParserRegistry()
parser = registry.get_parser("## 😬 CI Workflow Results", owner="NVIDIA", repo="cccl")
assert_test(parser.name == 'nvidia-cccl', "Registry: 精确映射返回 nvidia-cccl")

parser = registry.get_parser("✅ All checks have passed", owner="unknown", repo="project")
assert_test(parser.name == 'github-actions', "Registry: 自动检测返回 github-actions")


# ========== 批量提取 + 汇总测试 ==========
print("\n🧪 批量提取 + 汇总测试")
print("-" * 50)

batch_comments = [nvidia_comment, nvidia_success, gh_comment, normal_comment, generic_comment]
summary = extractor.get_cicd_summary(batch_comments, owner="NVIDIA", repo="cccl")
assert_test(summary['total'] == 4, f"汇总: 总计4条CI/CD评论（实际{summary['total']}）")
assert_test(summary['failed_count'] == 1, f"汇总: 1条失败（实际{summary['failed_count']}）")
# NVIDIA 项目映射下，gh_comment 也走 nvidia-cccl 解析器，结果为 unknown
assert_test(summary['success_count'] == 1, f"汇总: 1条成功（实际{summary['success_count']}）")
assert_test('nvidia-cccl' in summary['by_parser'], "汇总: by_parser 包含 nvidia-cccl")


# ========== 测试汇总 ==========
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
