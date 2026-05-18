"""
CI/CD 结构化数据模型测试
验证模型定义、字段校验、状态标准化等
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from models.cicd_models import (
    BuildStatus,
    TestResult,
    CoverageInfo,
    CheckResult,
    CICDResult,
    CICDResultSummary,
    CICDTrendPoint,
    CICDFailureAnalysis,
    CICDInsight,
    CICDReport,
    TimeGranularity,
)


def test_build_status_enum():
    """测试构建状态枚举"""
    assert BuildStatus.SUCCESS == "success"
    assert BuildStatus.FAILED == "failed"
    assert BuildStatus.PENDING == "pending"
    assert BuildStatus.RUNNING == "running"
    assert BuildStatus.QUEUED == "queued"
    assert BuildStatus.CANCELLED == "cancelled"
    assert BuildStatus.UNKNOWN == "unknown"
    print("  ✅ BuildStatus 枚举正确")


def test_build_status_normalize():
    """测试构建状态标准化"""
    result = CICDResult(
        owner="test", repo="test", parser_name="test",
        build_status="succeeded"
    )
    assert result.build_status == BuildStatus.SUCCESS

    result2 = CICDResult(
        owner="test", repo="test", parser_name="test",
        build_status="failure"
    )
    assert result2.build_status == BuildStatus.FAILED

    result3 = CICDResult(
        owner="test", repo="test", parser_name="test",
        build_status="in_progress"
    )
    assert result3.build_status == BuildStatus.RUNNING

    result4 = CICDResult(
        owner="test", repo="test", parser_name="test",
        build_status="unapproved"
    )
    assert result4.build_status == BuildStatus.CANCELLED
    print("  ✅ 构建状态标准化正确")


def test_cicd_result_basic():
    """测试 CICDResult 基本创建"""
    result = CICDResult(
        owner="NVIDIA",
        repo="cccl",
        pr_number=123,
        parser_name="nvidia-cccl",
        build_status="success",
        duration_seconds=3169,
        pass_rate=100.0,
        pass_count=48,
        url="https://github.com/NVIDIA/cccl/actions/runs/12345",
    )
    assert result.owner == "NVIDIA"
    assert result.repo == "cccl"
    assert result.build_status == BuildStatus.SUCCESS
    assert result.duration_seconds == 3169
    assert result.pass_rate == 100.0
    print("  ✅ CICDResult 基本创建正确")


def test_cicd_result_rust_bors():
    """测试 Rust Bors 格式"""
    result = CICDResult(
        owner="rust-lang",
        repo="rust",
        pr_number=456,
        parser_name="rust-bors",
        build_status="success",
        build_type="test",
        commit="abc1234",
        merge_commit="def5678",
        approver="user1",
        duration_seconds=11366,
        failed_jobs=[],
        url="https://github.com/rust-lang/rust/actions/runs/999",
    )
    assert result.parser_name == "rust-bors"
    assert result.build_type == "test"
    assert result.commit == "abc1234"
    assert result.approver == "user1"
    assert result.duration_seconds == 11366
    print("  ✅ CICDResult Rust Bors 格式正确")


def test_cicd_result_github_actions():
    """测试 GitHub Actions 格式"""
    result = CICDResult(
        owner="test",
        repo="project",
        parser_name="github-actions",
        build_status="failed",
        checks=CheckResult(passed=5, failed=2, skipped=1),
        coverage=CoverageInfo(percentage=85.5),
    )
    assert result.checks.passed == 5
    assert result.checks.failed == 2
    assert result.coverage.percentage == 85.5
    print("  ✅ CICDResult GitHub Actions 格式正确")


def test_cicd_result_generic():
    """测试通用格式"""
    result = CICDResult(
        owner="test",
        repo="project",
        parser_name="generic",
        build_status="success",
        test_results=TestResult(passed=100, failed=3, total=103),
        coverage=CoverageInfo(percentage=92.1),
        url="https://ci.example.com/build/123",
    )
    assert result.test_results.passed == 100
    assert result.test_results.failed == 3
    assert result.coverage.percentage == 92.1
    print("  ✅ CICDResult 通用格式正确")


def test_to_db_dict():
    """测试数据库存储格式转换"""
    result = CICDResult(
        owner="test",
        repo="project",
        parser_name="generic",
        build_status="success",
        test_results=TestResult(passed=10, failed=0),
    )
    db_dict = result.to_db_dict()
    assert 'owner' in db_dict
    assert 'repo' in db_dict
    assert 'parser_name' in db_dict
    assert 'build_status' in db_dict
    # 未设置的字段不应出现在字典中
    assert 'commit' not in db_dict
    assert 'merge_commit' not in db_dict
    assert 'pr_number' not in db_dict
    print("  ✅ to_db_dict() 排除 None 值正确")


def test_cicd_summary_compute_rates():
    """测试汇总统计比率计算"""
    summary = CICDResultSummary(
        total=100,
        success_count=80,
        failed_count=15,
        pending_count=3,
        running_count=1,
        cancelled_count=0,
        unknown_count=1,
    )
    summary.compute_rates()
    assert summary.success_rate == 80.0
    assert summary.failure_rate == 15.0
    print("  ✅ CICDResultSummary 比率计算正确")


def test_cicd_trend_point():
    """测试趋势数据点"""
    point = CICDTrendPoint(
        period="2026-05-18",
        total=50,
        success_count=40,
        failed_count=10,
        success_rate=80.0,
        avg_duration_seconds=120.5,
    )
    assert point.period == "2026-05-18"
    assert point.success_rate == 80.0
    print("  ✅ CICDTrendPoint 创建正确")


def test_cicd_failure_analysis():
    """测试失败分析模型"""
    analysis = CICDFailureAnalysis(
        total_failures=25,
        top_failed_jobs=[
            {"name": "test-linux", "count": 8},
            {"name": "build-mac", "count": 5},
        ],
        top_failed_parsers=[
            {"name": "rust-bors", "count": 15},
            {"name": "generic", "count": 10},
        ],
        avg_recovery_time_seconds=3600.0,
    )
    assert analysis.total_failures == 25
    assert len(analysis.top_failed_jobs) == 2
    assert analysis.avg_recovery_time_seconds == 3600.0
    print("  ✅ CICDFailureAnalysis 创建正确")


def test_cicd_insight():
    """测试洞察项模型"""
    insight = CICDInsight(
        name="构建成功率",
        value=85.5,
        grade="B",
        description="近30天构建成功率85.5%",
        suggestion="建议关注 flaky test，降低失败率",
    )
    assert insight.name == "构建成功率"
    assert insight.grade == "B"
    assert insight.suggestion is not None
    print("  ✅ CICDInsight 创建正确")


def test_cicd_report():
    """测试完整报告模型"""
    report = CICDReport(
        owner="rust-lang",
        repo="rust",
        start_date="2026-04-18",
        end_date="2026-05-18",
        summary=CICDResultSummary(
            total=200,
            success_count=170,
            failed_count=25,
            pending_count=5,
        ),
        trends=[
            CICDTrendPoint(period="2026-W18", total=50, success_count=42, failed_count=8),
            CICDTrendPoint(period="2026-W19", total=50, success_count=45, failed_count=5),
        ],
        failure_analysis=CICDFailureAnalysis(
            total_failures=25,
            top_failed_jobs=[{"name": "test-x86", "count": 10}],
        ),
        insights=[
            CICDInsight(
                name="构建稳定性",
                value=85.0,
                grade="B",
                description="整体稳定性良好",
            ),
        ],
        data_source_count=200,
    )
    assert report.owner == "rust-lang"
    assert report.summary.total == 200
    assert len(report.trends) == 2
    assert len(report.insights) == 1
    print("  ✅ CICDReport 完整报告创建正确")


def test_model_from_parser_output():
    """测试从解析器原始输出构建 CICDResult"""
    # 模拟 nvidia_cccl_parser 的原始输出
    raw = {
        'parser': 'nvidia-cccl',
        'build_status': 'success',
        'duration_seconds': 3169,
        'pass_rate': 100.0,
        'pass_count': 48,
        'total_time_seconds': 76380,
        'hits_rate': 53.0,
        'hits_count': 26011,
        'url': 'https://github.com/NVIDIA/cccl/actions/runs/23619126945',
    }

    result = CICDResult(
        owner="NVIDIA",
        repo="cccl",
        pr_number=100,
        parser_name=raw['parser'],
        build_status=raw['build_status'],
        duration_seconds=raw['duration_seconds'],
        pass_rate=raw.get('pass_rate'),
        pass_count=raw.get('pass_count'),
        hits_rate=raw.get('hits_rate'),
        hits_count=raw.get('hits_count'),
        url=raw.get('url'),
        raw_parsed=raw,
    )
    assert result.parser_name == "nvidia-cccl"
    assert result.build_status == BuildStatus.SUCCESS
    assert result.pass_rate == 100.0
    assert result.hits_count == 26011
    assert result.raw_parsed == raw
    print("  ✅ 从解析器原始输出构建 CICDResult 正确")

    # 模拟 rust_bors_parser 的原始输出
    raw2 = {
        'parser': 'rust-bors',
        'build_status': 'failed',
        'commit': 'abc123',
        'merge_commit': 'def456',
        'failed_jobs': ['test-x86', 'build-arm'],
        'build_type': 'test',
        'url': 'https://github.com/rust-lang/rust/actions/runs/888',
    }
    result2 = CICDResult(
        owner="rust-lang",
        repo="rust",
        pr_number=200,
        parser_name=raw2['parser'],
        build_status=raw2['build_status'],
        build_type=raw2.get('build_type'),
        commit=raw2.get('commit'),
        merge_commit=raw2.get('merge_commit'),
        failed_jobs=raw2.get('failed_jobs'),
        url=raw2.get('url'),
        raw_parsed=raw2,
    )
    assert result2.build_status == BuildStatus.FAILED
    assert len(result2.failed_jobs) == 2
    print("  ✅ 从 Rust Bors 原始输出构建 CICDResult 正确")


def main():
    """运行所有测试"""
    print("=" * 60)
    print("CI/CD 结构化数据模型测试")
    print("=" * 60)

    tests = [
        ("BuildStatus 枚举", test_build_status_enum),
        ("构建状态标准化", test_build_status_normalize),
        ("CICDResult 基本创建", test_cicd_result_basic),
        ("CICDResult Rust Bors", test_cicd_result_rust_bors),
        ("CICDResult GitHub Actions", test_cicd_result_github_actions),
        ("CICDResult 通用格式", test_cicd_result_generic),
        ("to_db_dict 转换", test_to_db_dict),
        ("汇总统计比率计算", test_cicd_summary_compute_rates),
        ("趋势数据点", test_cicd_trend_point),
        ("失败分析模型", test_cicd_failure_analysis),
        ("洞察项模型", test_cicd_insight),
        ("完整报告模型", test_cicd_report),
        ("从解析器输出构建", test_model_from_parser_output),
    ]

    passed = 0
    failed = 0
    for name, test_fn in tests:
        try:
            test_fn()
            passed += 1
        except Exception as e:
            print(f"  ❌ {name} 失败: {e}")
            failed += 1

    print("=" * 60)
    print(f"测试结果: {passed} 通过, {failed} 失败 (共 {passed + failed} 项)")
    print("=" * 60)
    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
