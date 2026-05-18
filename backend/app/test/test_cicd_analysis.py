"""
CI/CD 分析模块测试
覆盖：结构化提取、持久化 Mock、统计计算、洞察评级、API 路由
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from datetime import datetime
from unittest.mock import MagicMock, patch
from models.cicd_models import (
    CICDResult, BuildStatus, TestResult, CoverageInfo, CheckResult,
    CICDResultSummary, CICDTrendPoint, CICDFailureAnalysis, CICDInsight,
)
from analysis.cicd_extractor import CICDExtractor


# ====================
# 测试数据工厂
# ====================

def make_nvidia_comment(status="success"):
    """构造 NVIDIA CCCL CI 评论"""
    emoji = "🥳" if status == "success" else "😬"
    bar = "🟩" if status == "success" else "🟥"
    return {
        'id': 'c_001',
        'user': {'login': 'github-actions[bot]'},
        'body': (
            f'## {emoji} CI Workflow Results\n\n'
            f'### {bar} Finished in 52m 49s: Pass: 100%/48  | Total: 21h 13m | Max: 42m 34s | Hits:  53%/26011\n\n'
            f'See results [here](https://github.com/NVIDIA/cccl/actions/runs/23619126945).'
        ),
        'created_at': '2026-05-18T10:00:00Z',
    }


def make_rust_bors_comment(status="success"):
    """构造 Rust Bors CI 评论"""
    if status == "success":
        body = ':sunny: Test successful\n[CI](https://github.com/rust-lang/rust/actions/runs/888)\nDuration: `3h 9m 26s`'
    elif status == "failed":
        body = ':broken_heart: Test for abc123 failed: [CI](https://github.com/rust-lang/rust/actions/runs/889)\n- `test-x86` ([log](url))\n- `build-arm` ([log](url))'
    else:
        body = ':hourglass: Testing commit abc123 with merge def456...'
    return {
        'id': f'c_rust_{status}',
        'user': {'login': 'bors[bot]'},
        'body': body,
        'created_at': '2026-05-18T08:00:00Z',
    }


def make_cicd_result(owner="test", repo="project", pr_number=1,
                     build_status="success", duration_seconds=300,
                     parser_name="generic"):
    """构造一个 CICDResult 实例"""
    return CICDResult(
        owner=owner, repo=repo, pr_number=pr_number,
        parser_name=parser_name,
        build_status=build_status,
        duration_seconds=duration_seconds,
        coverage=CoverageInfo(percentage=85.5) if build_status == "success" else None,
        comment_id=f"c_{pr_number}_{build_status}",
        analyzed_at=datetime.now(),
    )


# ====================
# 1. 结构化提取测试
# ====================

def test_extract_structured_nvidia():
    """测试 NVIDIA CCCL 结构化提取"""
    extractor = CICDExtractor()
    result = extractor.extract_structured(
        make_nvidia_comment("success"), owner="NVIDIA", repo="cccl", pr_number=100
    )
    assert result is not None
    assert result.parser_name == "nvidia-cccl"
    assert result.build_status == BuildStatus.SUCCESS
    assert result.duration_seconds == 3169
    assert result.pass_rate == 100.0
    assert result.pass_count == 48
    assert result.hits_rate == 53.0
    assert result.hits_count == 26011
    assert result.owner == "NVIDIA"
    assert result.pr_number == 100
    print("  ✅ NVIDIA CCCL 结构化提取正确")


def test_extract_structured_rust_bors():
    """测试 Rust Bors 结构化提取"""
    extractor = CICDExtractor()

    result_success = extractor.extract_structured(
        make_rust_bors_comment("success"), owner="rust-lang", repo="rust", pr_number=200
    )
    assert result_success is not None
    assert result_success.parser_name == "rust-bors"
    assert result_success.build_status == BuildStatus.SUCCESS
    assert result_success.duration_seconds == 11366
    print("  ✅ Rust Bors 成功状态提取正确")

    result_failed = extractor.extract_structured(
        make_rust_bors_comment("failed"), owner="rust-lang", repo="rust", pr_number=201
    )
    assert result_failed is not None
    assert result_failed.build_status == BuildStatus.FAILED
    assert result_failed.failed_jobs is not None
    assert len(result_failed.failed_jobs) == 2
    assert "test-x86" in result_failed.failed_jobs
    print("  ✅ Rust Bors 失败状态提取正确")


def test_extract_structured_non_cicd():
    """测试非 CI/CD 评论返回 None"""
    extractor = CICDExtractor()
    comment = {
        'id': 'c_normal',
        'user': {'login': 'developer'},
        'body': 'LGTM, looks good to me!',
    }
    result = extractor.extract_structured(comment, owner="test", repo="test")
    assert result is None
    print("  ✅ 非 CI/CD 评论正确返回 None")


def test_extract_batch_structured():
    """测试批量结构化提取"""
    extractor = CICDExtractor()
    comments = [
        make_nvidia_comment("success"),
        make_rust_bors_comment("success"),
        make_rust_bors_comment("failed"),
        {'id': 'normal', 'user': {'login': 'dev'}, 'body': 'Normal comment'},
    ]
    results = extractor.extract_batch_structured(comments, owner="test", repo="test")
    assert len(results) == 3  # 3 条 CI/CD 评论
    statuses = [r.build_status for r in results]
    assert BuildStatus.SUCCESS in statuses
    assert BuildStatus.FAILED in statuses
    print("  ✅ 批量结构化提取正确")


def test_to_db_dict_complete():
    """测试 to_db_dict 包含所有必要字段"""
    result = make_cicd_result(pr_number=42, build_status="success")
    db_dict = result.to_db_dict()
    assert db_dict['owner'] == "test"
    assert db_dict['repo'] == "project"
    assert db_dict['pr_number'] == 42
    assert db_dict['build_status'] == BuildStatus.SUCCESS
    assert db_dict['duration_seconds'] == 300
    assert 'analyzed_at' in db_dict
    assert 'comment_id' in db_dict
    assert 'coverage' in db_dict
    assert db_dict['coverage']['percentage'] == 85.5
    print("  ✅ to_db_dict 字段完整")


# ====================
# 2. 持久化 Mock 测试
# ====================

def test_database_service_save_cicd_result():
    """测试 save_cicd_result 调用正确的 MongoDB 操作"""
    from services.database_service import DatabaseService

    db = DatabaseService.__new__(DatabaseService)
    db.db = MagicMock()
    mock_collection = MagicMock()
    db.db.__getitem__ = MagicMock(return_value=mock_collection)

    result_data = make_cicd_result().to_db_dict()
    ok = db.save_cicd_result(result_data)

    assert ok is True
    mock_collection.update_one.assert_called_once()
    call_args = mock_collection.update_one.call_args
    filter_q = call_args[0][0]
    update_op = call_args[0][1]
    assert filter_q["owner"] == "test"
    assert filter_q["repo"] == "project"
    assert "$set" in update_op
    assert update_op["$set"]["owner"] == "test"
    print("  ✅ save_cicd_result 正确调用 MongoDB upsert")


def test_database_service_save_batch():
    """测试批量保存"""
    from services.database_service import DatabaseService

    db = DatabaseService.__new__(DatabaseService)
    db.db = MagicMock()
    mock_collection = MagicMock()
    db.db.__getitem__ = MagicMock(return_value=mock_collection)

    results = [make_cicd_result(pr_number=i).to_db_dict() for i in range(5)]
    save_result = db.save_cicd_results_batch(results)

    assert save_result["saved"] == 5
    assert save_result["failed"] == 0
    assert mock_collection.update_one.call_count == 5
    print("  ✅ save_cicd_results_batch 批量保存正确")


def test_database_service_query_cicd_results():
    """测试查询 CI/CD 结果"""
    from services.database_service import DatabaseService

    db = DatabaseService.__new__(DatabaseService)
    db.db = MagicMock()
    mock_collection = MagicMock()
    db.db.__getitem__ = MagicMock(return_value=mock_collection)

    mock_collection.count_documents.return_value = 2
    mock_cursor = MagicMock()
    mock_cursor.sort.return_value.skip.return_value.limit.return_value = iter([
        {"owner": "test", "repo": "project", "build_status": "success"},
        {"owner": "test", "repo": "project", "build_status": "failed"},
    ])
    mock_collection.find.return_value = mock_cursor

    result = db.query_cicd_results("test", "project", page=1, size=10)

    assert result["total"] == 2
    assert len(result["data"]) == 2
    assert result["page"] == 1
    print("  ✅ query_cicd_results 查询正确")


def test_database_service_save_no_db():
    """测试数据库未连接时保存返回 False"""
    from services.database_service import DatabaseService

    db = DatabaseService.__new__(DatabaseService)
    db.db = None
    assert db.save_cicd_result({"owner": "x", "repo": "y"}) is False
    assert db.save_cicd_results_batch([{"owner": "x", "repo": "y"}]) == {"saved": 0, "failed": 1}
    print("  ✅ 数据库未连接时正确处理")


# ====================
# 3. 统计服务 Mock 测试
# ====================

def test_get_cicd_summary_from_db():
    """测试聚合统计查询"""
    from services.database_service import DatabaseService

    db = DatabaseService.__new__(DatabaseService)
    db.db = MagicMock()
    mock_collection = MagicMock()
    db.db.__getitem__ = MagicMock(return_value=mock_collection)

    mock_collection.aggregate.side_effect = [
        [{"_id": "success", "count": 80}, {"_id": "failed", "count": 20}],
        [{"_id": "nvidia-cccl", "count": 60}, {"_id": "rust-bors", "count": 40}],
        [{"_id": None, "avg_duration": 600.5, "count": 100, "durations": [300, 600, 900]}],
        [{"_id": None, "avg_coverage": 87.3, "count": 50}],
    ]

    result = db.get_cicd_summary_from_db("NVIDIA", "cccl")

    assert result["total"] == 100
    assert result["success_count"] == 80
    assert result["failed_count"] == 20
    assert result["success_rate"] == 80.0
    assert result["failure_rate"] == 20.0
    assert result["avg_duration_seconds"] == 600.5
    assert result["avg_coverage"] == 87.3
    print("  ✅ get_cicd_summary_from_db 聚合统计正确")


def test_get_cicd_failure_analysis_from_db():
    """测试失败分析查询"""
    from services.database_service import DatabaseService

    db = DatabaseService.__new__(DatabaseService)
    db.db = MagicMock()
    mock_collection = MagicMock()
    db.db.__getitem__ = MagicMock(return_value=mock_collection)

    mock_collection.count_documents.return_value = 20
    mock_collection.aggregate.side_effect = [
        [{"_id": "test-x86", "count": 8}, {"_id": "build-arm", "count": 5}],
        [{"_id": "rust-bors", "count": 12}, {"_id": "generic", "count": 8}],
        # MTTR pipeline 结果
        [],
    ]

    result = db.get_cicd_failure_analysis_from_db("rust-lang", "rust")

    assert result["total_failures"] == 20
    assert len(result["top_failed_jobs"]) == 2
    assert result["top_failed_jobs"][0]["name"] == "test-x86"
    assert result["top_failed_jobs"][0]["count"] == 8
    assert len(result["top_failed_parsers"]) == 2
    print("  ✅ get_cicd_failure_analysis_from_db 失败分析正确")


def test_get_cicd_trends_from_db():
    """测试趋势数据查询"""
    from services.database_service import DatabaseService

    db = DatabaseService.__new__(DatabaseService)
    db.db = MagicMock()
    mock_collection = MagicMock()
    db.db.__getitem__ = MagicMock(return_value=mock_collection)

    mock_collection.aggregate.return_value = [
        {
            "_id": "2026-05-17",
            "total": 10, "success_count": 8, "failed_count": 2,
            "avg_duration": 300.0, "avg_coverage": 85.0,
        },
        {
            "_id": "2026-05-18",
            "total": 15, "success_count": 12, "failed_count": 3,
            "avg_duration": 280.0, "avg_coverage": 87.5,
        },
    ]

    trends = db.get_cicd_trends_from_db("test", "project", granularity="day")

    assert len(trends) == 2
    assert trends[0]["period"] == "2026-05-17"
    assert trends[0]["total"] == 10
    assert trends[0]["success_rate"] == 80.0
    assert trends[1]["avg_coverage"] == 87.5
    print("  ✅ get_cicd_trends_from_db 趋势数据正确")


# ====================
# 4. 洞察评级测试
# ====================

def test_insight_grading_success_rate():
    """测试构建成功率评级"""
    from api.routers.analysis import _build_insights

    # A 级
    insights = _build_insights({"total": 100, "success_rate": 96.0, "failed_count": 4}, {})
    assert insights[0]["grade"] == "A"

    # B 级
    insights = _build_insights({"total": 100, "success_rate": 88.0, "failed_count": 12}, {})
    assert insights[0]["grade"] == "B"

    # D 级
    insights = _build_insights({"total": 100, "success_rate": 55.0, "failed_count": 45}, {})
    assert insights[0]["grade"] == "D"

    # F 级
    insights = _build_insights({"total": 100, "success_rate": 30.0, "failed_count": 70}, {})
    assert insights[0]["grade"] == "F"
    print("  ✅ 构建成功率评级 A-F 正确")


def test_insight_grading_duration():
    """测试耗时评级"""
    from api.routers.analysis import _build_insights

    insights = _build_insights({"total": 10, "success_rate": 95.0, "avg_duration_seconds": 180}, {})
    duration_insight = [i for i in insights if i["name"] == "平均构建耗时"][0]
    assert duration_insight["grade"] == "A"

    insights = _build_insights({"total": 10, "success_rate": 95.0, "avg_duration_seconds": 7200}, {})
    duration_insight = [i for i in insights if i["name"] == "平均构建耗时"][0]
    assert duration_insight["grade"] == "F"
    print("  ✅ 耗时评级 A-F 正确")


def test_insight_grading_coverage():
    """测试覆盖率评级"""
    from api.routers.analysis import _build_insights

    insights = _build_insights({"total": 10, "success_rate": 95.0, "avg_coverage": 92.0}, {})
    coverage_insight = [i for i in insights if i["name"] == "测试覆盖率"][0]
    assert coverage_insight["grade"] == "A"

    insights = _build_insights({"total": 10, "success_rate": 95.0, "avg_coverage": 30.0}, {})
    coverage_insight = [i for i in insights if i["name"] == "测试覆盖率"][0]
    assert coverage_insight["grade"] == "F"
    print("  ✅ 覆盖率评级 A-F 正确")


def test_insight_top_failed_job():
    """测试高频失败 Job 洞察"""
    from api.routers.analysis import _build_insights

    insights = _build_insights(
        {"total": 100, "success_rate": 80.0},
        {"top_failed_jobs": [{"name": "test-x86", "count": 8}]}
    )
    job_insight = [i for i in insights if i["name"] == "最高频失败 Job"]
    assert len(job_insight) == 1
    assert job_insight[0]["value"] == "test-x86"
    print("  ✅ 高频失败 Job 洞察正确")


def test_insight_empty_data():
    """测试无数据时返回空洞察"""
    from api.routers.analysis import _build_insights

    insights = _build_insights({"total": 0}, {})
    assert insights == []
    print("  ✅ 无数据时返回空洞察")


# ====================
# 5. CICDResultSummary 测试
# ====================

def test_summary_compute_rates():
    """测试统计比率计算"""
    summary = CICDResultSummary(
        total=200, success_count=170, failed_count=20,
        pending_count=5, running_count=3, cancelled_count=1, unknown_count=1,
    )
    summary.compute_rates()
    assert summary.success_rate == 85.0
    assert summary.failure_rate == 10.0
    print("  ✅ CICDResultSummary 比率计算正确")


def test_summary_zero_total():
    """测试总数为 0 时不计算比率"""
    summary = CICDResultSummary()
    summary.compute_rates()
    assert summary.success_rate is None
    assert summary.failure_rate is None
    print("  ✅ 总数为 0 时比率为 None")


# ====================
# 运行所有测试
# ====================

def main():
    """运行所有测试"""
    print("=" * 60)
    print("CI/CD 分析模块测试")
    print("=" * 60)

    sections = [
        ("结构化提取", [
            ("NVIDIA CCCL 提取", test_extract_structured_nvidia),
            ("Rust Bors 提取", test_extract_structured_rust_bors),
            ("非 CI/CD 评论", test_extract_structured_non_cicd),
            ("批量提取", test_extract_batch_structured),
            ("to_db_dict 完整性", test_to_db_dict_complete),
        ]),
        ("持久化 Mock", [
            ("save_cicd_result", test_database_service_save_cicd_result),
            ("save_cicd_results_batch", test_database_service_save_batch),
            ("query_cicd_results", test_database_service_query_cicd_results),
            ("数据库未连接处理", test_database_service_save_no_db),
        ]),
        ("统计服务 Mock", [
            ("get_cicd_summary_from_db", test_get_cicd_summary_from_db),
            ("get_cicd_failure_analysis_from_db", test_get_cicd_failure_analysis_from_db),
            ("get_cicd_trends_from_db", test_get_cicd_trends_from_db),
        ]),
        ("洞察评级", [
            ("成功率评级", test_insight_grading_success_rate),
            ("耗时评级", test_insight_grading_duration),
            ("覆盖率评级", test_insight_grading_coverage),
            ("高频失败 Job", test_insight_top_failed_job),
            ("空数据处理", test_insight_empty_data),
        ]),
        ("统计模型", [
            ("比率计算", test_summary_compute_rates),
            ("零值处理", test_summary_zero_total),
        ]),
    ]

    passed = 0
    failed = 0
    errors = []

    for section_name, tests in sections:
        print(f"\n🧪 {section_name}")
        print("-" * 60)
        for name, test_fn in tests:
            try:
                test_fn()
                passed += 1
            except Exception as e:
                print(f"  ❌ {name} 失败: {e}")
                failed += 1
                errors.append(f"{section_name}/{name}: {e}")

    print("\n" + "=" * 60)
    print(f"📊 测试结果: {passed} 通过, {failed} 失败 (共 {passed + failed} 项)")
    if errors:
        print("\n❌ 失败项:")
        for e in errors:
            print(f"  - {e}")
    print("=" * 60)
    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
