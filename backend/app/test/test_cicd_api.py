"""
CI/CD 分析 API 集成测试
使用 FastAPI TestClient + Mock 数据库，不依赖外部环境
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from unittest.mock import MagicMock, patch
from datetime import datetime
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers.analysis import register_analysis_routes
from models.cicd_models import CICDResult, BuildStatus, CoverageInfo


def create_test_app():
    """创建测试用 FastAPI 应用"""
    app = FastAPI()
    return app


def make_mock_db():
    """构造 Mock 数据库"""
    db = MagicMock()

    # 预设一些 cicd_results 数据
    mock_results = [
        {
            "owner": "rust-lang", "repo": "rust", "pr_number": 100,
            "build_status": "success", "parser_name": "rust-bors",
            "duration_seconds": 11366, "analyzed_at": "2026-05-18T10:00:00",
            "coverage": {"percentage": 85.5},
        },
        {
            "owner": "rust-lang", "repo": "rust", "pr_number": 101,
            "build_status": "failed", "parser_name": "rust-bors",
            "duration_seconds": 3600, "analyzed_at": "2026-05-18T12:00:00",
            "failed_jobs": ["test-x86", "build-arm"],
        },
        {
            "owner": "rust-lang", "repo": "rust", "pr_number": 102,
            "build_status": "success", "parser_name": "rust-bors",
            "duration_seconds": 10000, "analyzed_at": "2026-05-18T14:00:00",
            "coverage": {"percentage": 87.0},
        },
    ]

    # mock query_cicd_results
    db.query_cicd_results.return_value = {
        "data": mock_results,
        "total": 3,
        "page": 1,
        "size": 20,
        "total_pages": 1,
    }

    # mock get_cicd_summary_from_db
    db.get_cicd_summary_from_db.return_value = {
        "total": 3,
        "success_count": 2,
        "failed_count": 1,
        "success_rate": 66.67,
        "failure_rate": 33.33,
        "avg_duration_seconds": 8322.0,
        "avg_coverage": 86.25,
        "by_status": {"success": 2, "failed": 1},
        "by_parser": {"rust-bors": 3},
    }

    # mock get_cicd_trends_from_db
    db.get_cicd_trends_from_db.return_value = [
        {
            "period": "2026-05-18",
            "total": 3, "success_count": 2, "failed_count": 1,
            "success_rate": 66.67, "avg_duration_seconds": 8322.0, "avg_coverage": 86.25,
        },
    ]

    # mock get_cicd_failure_analysis_from_db
    db.get_cicd_failure_analysis_from_db.return_value = {
        "total_failures": 1,
        "top_failed_jobs": [{"name": "test-x86", "count": 1}, {"name": "build-arm", "count": 1}],
        "top_failed_parsers": [{"name": "rust-bors", "count": 1}],
        "avg_recovery_time_seconds": 7200.0,
    }

    # mock save_cicd_results_batch
    db.save_cicd_results_batch.return_value = {"saved": 2, "failed": 0}

    # mock db.db['pr_comments']
    mock_pr_comments_col = MagicMock()
    mock_pr_comments_col.find.return_value = [
        {
            "pr_number": 100,
            "data": [
                {
                    "id": "c1",
                    "user": {"login": "bors[bot]"},
                    "body": ":sunny: Test successful\n[CI](https://github.com/rust-lang/rust/actions/runs/888)\nDuration: `3h 9m 26s`",
                    "created_at": "2026-05-18T10:00:00Z",
                },
                {
                    "id": "c2",
                    "user": {"login": "bors[bot]"},
                    "body": ":broken_heart: Test for abc failed: [CI](url)\n- `test-x86` ([log](url))",
                    "created_at": "2026-05-18T12:00:00Z",
                },
            ],
        },
    ]
    db.db = MagicMock()
    db.db.__getitem__ = MagicMock(return_value=mock_pr_comments_col)

    return db


# ====================
# 测试
# ====================

def test_analyze_endpoint():
    """测试 POST /analysis/cicd/analyze/{owner}/{repo}"""
    app = create_test_app()
    db = make_mock_db()
    cache = MagicMock()
    register_analysis_routes(app, db, cache)

    client = TestClient(app)
    response = client.post("/analysis/cicd/analyze/rust-lang/rust")

    assert response.status_code == 200
    data = response.json()
    assert data["owner"] == "rust-lang"
    assert data["repo"] == "rust"
    assert "cicd_comments" in data
    assert "saved" in data
    print("  ✅ POST /analyze 触发分析正确")


def test_report_endpoint():
    """测试 GET /analysis/cicd/report/{owner}/{repo}"""
    app = create_test_app()
    db = make_mock_db()
    cache = MagicMock()
    register_analysis_routes(app, db, cache)

    client = TestClient(app)
    response = client.get("/analysis/cicd/report/rust-lang/rust")

    assert response.status_code == 200
    data = response.json()
    assert data["owner"] == "rust-lang"
    assert data["repo"] == "rust"
    assert "summary" in data
    assert "trends" in data
    assert "failure_analysis" in data
    assert "insights" in data
    assert data["summary"]["total"] == 3
    assert data["summary"]["success_rate"] == 66.67
    assert len(data["trends"]) == 1
    assert data["failure_analysis"]["total_failures"] == 1
    print("  ✅ GET /report 洞察报告正确")


def test_report_with_date_range():
    """测试 GET /report 带日期范围参数"""
    app = create_test_app()
    db = make_mock_db()
    cache = MagicMock()
    register_analysis_routes(app, db, cache)

    client = TestClient(app)
    response = client.get(
        "/analysis/cicd/report/rust-lang/rust",
        params={"start_date": "2026-05-01", "end_date": "2026-05-18"}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["start_date"] == "2026-05-01"
    assert data["end_date"] == "2026-05-18"
    print("  ✅ GET /report 日期范围参数正确")


def test_stats_endpoint():
    """测试 GET /analysis/cicd/stats/{owner}/{repo}"""
    app = create_test_app()
    db = make_mock_db()
    cache = MagicMock()
    register_analysis_routes(app, db, cache)

    client = TestClient(app)
    response = client.get("/analysis/cicd/stats/rust-lang/rust")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 3
    assert data["success_count"] == 2
    assert data["failed_count"] == 1
    assert data["success_rate"] == 66.67
    print("  ✅ GET /stats 统计数据正确")


def test_trends_endpoint():
    """测试 GET /analysis/cicd/trends/{owner}/{repo}"""
    app = create_test_app()
    db = make_mock_db()
    cache = MagicMock()
    register_analysis_routes(app, db, cache)

    client = TestClient(app)
    response = client.get(
        "/analysis/cicd/trends/rust-lang/rust",
        params={"granularity": "week"}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["granularity"] == "week"
    assert len(data["trends"]) == 1
    assert data["trends"][0]["success_rate"] == 66.67
    print("  ✅ GET /trends 趋势数据正确")


def test_results_endpoint():
    """测试 GET /analysis/cicd/results/{owner}/{repo}"""
    app = create_test_app()
    db = make_mock_db()
    cache = MagicMock()
    register_analysis_routes(app, db, cache)

    client = TestClient(app)
    response = client.get(
        "/analysis/cicd/results/rust-lang/rust",
        params={"build_status": "failed", "page": 1, "size": 10}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 3
    assert len(data["data"]) == 3
    assert data["page"] == 1
    print("  ✅ GET /results 结果查询正确")


def test_report_db_not_connected():
    """测试数据库未连接时返回 503"""
    app = create_test_app()
    db = MagicMock()
    db.db = None
    cache = MagicMock()
    register_analysis_routes(app, db, cache)

    client = TestClient(app)
    response = client.get("/analysis/cicd/report/test/test")

    assert response.status_code == 503
    assert "数据库未连接" in response.json()["detail"]
    print("  ✅ 数据库未连接返回 503 正确")


def test_report_insights_grading():
    """测试报告洞察评级完整性"""
    app = create_test_app()
    db = make_mock_db()
    cache = MagicMock()
    register_analysis_routes(app, db, cache)

    client = TestClient(app)
    response = client.get("/analysis/cicd/report/rust-lang/rust")
    data = response.json()

    insights = data["insights"]
    assert len(insights) >= 1
    # 成功率洞察
    success_insights = [i for i in insights if i["name"] == "构建成功率"]
    assert len(success_insights) == 1
    assert success_insights[0]["grade"] in ["A", "B", "C", "D", "F"]
    assert success_insights[0]["value"] == 66.67
    print("  ✅ 洞察评级完整性正确")


def test_results_with_pr_number_filter():
    """测试结果查询带 PR 编号过滤"""
    app = create_test_app()
    db = make_mock_db()
    cache = MagicMock()
    register_analysis_routes(app, db, cache)

    client = TestClient(app)
    response = client.get(
        "/analysis/cicd/results/rust-lang/rust",
        params={"pr_number": 100}
    )

    assert response.status_code == 200
    # 验证 query_cicd_results 被正确调用
    db.query_cicd_results.assert_called_once()
    call_kwargs = db.query_cicd_results.call_args[1]
    assert call_kwargs["pr_number"] == 100
    print("  ✅ PR 编号过滤参数传递正确")


def test_trends_granularity_options():
    """测试趋势数据支持不同粒度"""
    app = create_test_app()
    db = make_mock_db()
    cache = MagicMock()
    register_analysis_routes(app, db, cache)

    client = TestClient(app)

    for granularity in ["day", "week", "month"]:
        response = client.get(
            "/analysis/cicd/trends/rust-lang/rust",
            params={"granularity": granularity}
        )
        assert response.status_code == 200
        assert response.json()["granularity"] == granularity

    print("  ✅ 趋势粒度 day/week/month 均支持")


# ====================
# 运行测试
# ====================

def main():
    """运行所有测试"""
    print("=" * 60)
    print("CI/CD 分析 API 集成测试")
    print("=" * 60)

    tests = [
        ("POST /analyze 触发分析", test_analyze_endpoint),
        ("GET /report 洞察报告", test_report_endpoint),
        ("GET /report 日期范围", test_report_with_date_range),
        ("GET /stats 统计数据", test_stats_endpoint),
        ("GET /trends 趋势数据", test_trends_endpoint),
        ("GET /results 结果查询", test_results_endpoint),
        ("数据库未连接 503", test_report_db_not_connected),
        ("洞察评级完整性", test_report_insights_grading),
        ("PR 编号过滤", test_results_with_pr_number_filter),
        ("趋势粒度选项", test_trends_granularity_options),
    ]

    passed = 0
    failed = 0
    errors = []

    for name, test_fn in tests:
        try:
            test_fn()
            passed += 1
        except Exception as e:
            print(f"  ❌ {name} 失败: {e}")
            failed += 1
            errors.append(f"{name}: {e}")

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
