"""
Review 质量评估测试
覆盖服务层 + API 集成测试
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers.analysis import register_analysis_routes
from models.responses import ReviewQualityReport, ReviewQualityTrendsResponse


# ====================
# Mock 数据构造
# ====================

def make_mock_db_for_review_quality():
    """构造 Mock 数据库，预设 review 质量数据"""
    db = MagicMock()

    # get_review_quality_report mock
    db.get_review_quality_report = AsyncMock(return_value={
        "owner": "rust-lang", "repo": "rust",
        "start_date": None, "end_date": None,
        "coverage": {
            "total_prs": 100, "prs_with_review": 85, "prs_without_review": 15,
            "coverage_rate": 85.0, "avg_reviewers_per_pr": 2.3,
        },
        "delay": {
            "total_reviews": 200, "avg_first_review_delay_hours": 6.5,
            "median_first_review_delay_hours": 4.0,
            "p90_first_review_delay_hours": 18.0,
            "avg_review_delay_hours": 8.2,
        },
        "depth": {
            "total_reviews": 200, "avg_body_length": 120.5,
            "reviews_with_body": 160, "reviews_without_body": 40,
            "body_rate": 80.0,
        },
        "state_distribution": {
            "approved": 150, "changes_requested": 20,
            "commented": 25, "dismissed": 2, "pending": 3,
        },
        "top_reviewers": [
            {"user": "reviewer-a", "review_count": 30, "approved_count": 25,
             "changes_requested_count": 3, "avg_body_length": 150.0, "avg_delay_hours": None},
            {"user": "reviewer-b", "review_count": 22, "approved_count": 18,
             "changes_requested_count": 2, "avg_body_length": 80.0, "avg_delay_hours": None},
        ],
        "insights": [
            {"name": "Review 覆盖率", "value": 85.0, "grade": "B",
             "description": "共 100 个 PR，85 个有 review，覆盖率 85.0%",
             "suggestion": "Review 覆盖率良好，建议关注无 review 的 PR"},
            {"name": "首次 Review 延迟", "value": 6.5, "grade": "B",
             "description": "首次 review 平均延迟 6.5 小时",
             "suggestion": "Review 响应及时"},
            {"name": "Review 深度", "value": 80.0, "grade": "A",
             "description": "有评论内容的 review 占比 80.0%",
             "suggestion": "Review 质量优秀，大部分 review 有实质性评论"},
        ],
        "generated_at": "2026-05-25T10:00:00",
    })

    # get_review_quality_trends mock
    db.get_review_quality_trends = AsyncMock(return_value=[
        {"period": "2026-W20", "pr_count": 12, "total_reviews": 28, "avg_reviews_per_pr": 2.33},
        {"period": "2026-W21", "pr_count": 15, "total_reviews": 35, "avg_reviews_per_pr": 2.33},
    ])

    db.db = MagicMock()
    return db


def create_test_app():
    app = FastAPI()
    return app


# ====================
# API 集成测试
# ====================

def test_review_quality_report_endpoint():
    """测试 GET /analysis/review-quality/{owner}/{repo}"""
    app = create_test_app()
    db = make_mock_db_for_review_quality()
    cache = MagicMock()
    register_analysis_routes(app, db, cache)

    client = TestClient(app)
    response = client.get("/analysis/review-quality/rust-lang/rust")

    assert response.status_code == 200
    data = response.json()
    assert data["owner"] == "rust-lang"
    assert data["repo"] == "rust"
    assert "coverage" in data
    assert "delay" in data
    assert "depth" in data
    assert "state_distribution" in data
    assert "top_reviewers" in data
    assert "insights" in data
    print("  ✅ GET /review-quality 报告端点正确")


def test_review_quality_report_with_date_range():
    """测试带日期范围的 Review 质量报告"""
    app = create_test_app()
    db = make_mock_db_for_review_quality()
    cache = MagicMock()
    register_analysis_routes(app, db, cache)

    client = TestClient(app)
    response = client.get(
        "/analysis/review-quality/rust-lang/rust",
        params={"start_date": "2026-05-01", "end_date": "2026-05-25"}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["owner"] == "rust-lang"
    print("  ✅ GET /review-quality 日期范围参数正确")


def test_review_quality_report_with_top_n():
    """测试 top_n 参数"""
    app = create_test_app()
    db = make_mock_db_for_review_quality()
    cache = MagicMock()
    register_analysis_routes(app, db, cache)

    client = TestClient(app)
    response = client.get(
        "/analysis/review-quality/rust-lang/rust",
        params={"top_n": 5}
    )

    assert response.status_code == 200
    print("  ✅ GET /review-quality top_n 参数正确")


def test_review_quality_coverage_metrics():
    """测试覆盖率指标字段完整性"""
    app = create_test_app()
    db = make_mock_db_for_review_quality()
    cache = MagicMock()
    register_analysis_routes(app, db, cache)

    client = TestClient(app)
    response = client.get("/analysis/review-quality/rust-lang/rust")
    data = response.json()

    coverage = data["coverage"]
    assert coverage["total_prs"] == 100
    assert coverage["prs_with_review"] == 85
    assert coverage["prs_without_review"] == 15
    assert coverage["coverage_rate"] == 85.0
    assert coverage["avg_reviewers_per_pr"] == 2.3
    print("  ✅ 覆盖率指标字段完整")


def test_review_quality_delay_metrics():
    """测试延迟指标字段完整性"""
    app = create_test_app()
    db = make_mock_db_for_review_quality()
    cache = MagicMock()
    register_analysis_routes(app, db, cache)

    client = TestClient(app)
    response = client.get("/analysis/review-quality/rust-lang/rust")
    data = response.json()

    delay = data["delay"]
    assert delay["total_reviews"] == 200
    assert delay["avg_first_review_delay_hours"] == 6.5
    assert delay["median_first_review_delay_hours"] == 4.0
    assert delay["p90_first_review_delay_hours"] == 18.0
    assert delay["avg_review_delay_hours"] == 8.2
    print("  ✅ 延迟指标字段完整")


def test_review_quality_depth_metrics():
    """测试深度指标字段完整性"""
    app = create_test_app()
    db = make_mock_db_for_review_quality()
    cache = MagicMock()
    register_analysis_routes(app, db, cache)

    client = TestClient(app)
    response = client.get("/analysis/review-quality/rust-lang/rust")
    data = response.json()

    depth = data["depth"]
    assert depth["total_reviews"] == 200
    assert depth["avg_body_length"] == 120.5
    assert depth["reviews_with_body"] == 160
    assert depth["reviews_without_body"] == 40
    assert depth["body_rate"] == 80.0
    print("  ✅ 深度指标字段完整")


def test_review_quality_state_distribution():
    """测试状态分布字段完整性"""
    app = create_test_app()
    db = make_mock_db_for_review_quality()
    cache = MagicMock()
    register_analysis_routes(app, db, cache)

    client = TestClient(app)
    response = client.get("/analysis/review-quality/rust-lang/rust")
    data = response.json()

    state_dist = data["state_distribution"]
    assert state_dist["approved"] == 150
    assert state_dist["changes_requested"] == 20
    assert state_dist["commented"] == 25
    assert state_dist["dismissed"] == 2
    assert state_dist["pending"] == 3
    print("  ✅ 状态分布字段完整")


def test_review_quality_insights():
    """测试洞察项评级完整性"""
    app = create_test_app()
    db = make_mock_db_for_review_quality()
    cache = MagicMock()
    register_analysis_routes(app, db, cache)

    client = TestClient(app)
    response = client.get("/analysis/review-quality/rust-lang/rust")
    data = response.json()

    insights = data["insights"]
    assert len(insights) >= 3

    # 验证每个洞察项都有必要字段
    for insight in insights:
        assert "name" in insight
        assert "value" in insight
        assert "grade" in insight
        assert insight["grade"] in ["A", "B", "C", "D", "F"]
        assert "description" in insight
        assert "suggestion" in insight

    # 验证覆盖率洞察
    coverage_insight = [i for i in insights if i["name"] == "Review 覆盖率"]
    assert len(coverage_insight) == 1
    assert coverage_insight[0]["grade"] == "B"
    print("  ✅ 洞察项评级完整性正确")


def test_review_quality_trends_endpoint():
    """测试 GET /analysis/review-quality/{owner}/{repo}/trends"""
    app = create_test_app()
    db = make_mock_db_for_review_quality()
    cache = MagicMock()
    register_analysis_routes(app, db, cache)

    client = TestClient(app)
    response = client.get(
        "/analysis/review-quality/rust-lang/rust/trends",
        params={"granularity": "week"}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["owner"] == "rust-lang"
    assert data["repo"] == "rust"
    assert data["granularity"] == "week"
    assert len(data["trends"]) == 2
    assert data["trends"][0]["period"] == "2026-W20"
    assert data["trends"][0]["pr_count"] == 12
    assert data["trends"][0]["total_reviews"] == 28
    print("  ✅ GET /review-quality/trends 趋势端点正确")


def test_review_quality_trends_granularity():
    """测试趋势数据支持不同粒度"""
    app = create_test_app()
    db = make_mock_db_for_review_quality()
    cache = MagicMock()
    register_analysis_routes(app, db, cache)

    client = TestClient(app)
    for granularity in ["day", "week", "month"]:
        response = client.get(
            "/analysis/review-quality/rust-lang/rust/trends",
            params={"granularity": granularity}
        )
        assert response.status_code == 200
        assert response.json()["granularity"] == granularity

    print("  ✅ 趋势粒度 day/week/month 均支持")


def test_review_quality_db_not_connected():
    """测试数据库未连接时返回 503"""
    app = create_test_app()
    db = MagicMock()
    db.db = None
    cache = MagicMock()
    register_analysis_routes(app, db, cache)

    client = TestClient(app)
    response = client.get("/analysis/review-quality/test/test")

    assert response.status_code == 503
    assert "数据库未连接" in response.json()["detail"]
    print("  ✅ 数据库未连接返回 503 正确")


# ====================
# 评级函数单元测试
# ====================

def test_grade_review_coverage():
    """测试 Review 覆盖率评级"""
    from services.database_service import DatabaseService

    assert DatabaseService._grade_review_coverage(95) == ("A", "Review 覆盖率优秀，几乎所有 PR 都经过 review")
    assert DatabaseService._grade_review_coverage(85)[0] == "B"
    assert DatabaseService._grade_review_coverage(60)[0] == "C"
    assert DatabaseService._grade_review_coverage(40)[0] == "D"
    assert DatabaseService._grade_review_coverage(10)[0] == "F"
    print("  ✅ Review 覆盖率评级正确")


def test_grade_review_delay():
    """测试 Review 延迟评级"""
    from services.database_service import DatabaseService

    assert DatabaseService._grade_review_delay(2)[0] == "A"
    assert DatabaseService._grade_review_delay(8)[0] == "B"
    assert DatabaseService._grade_review_delay(18)[0] == "C"
    assert DatabaseService._grade_review_delay(36)[0] == "D"
    assert DatabaseService._grade_review_delay(60)[0] == "F"
    print("  ✅ Review 延迟评级正确")


def test_grade_review_depth():
    """测试 Review 深度评级"""
    from services.database_service import DatabaseService

    assert DatabaseService._grade_review_depth(90)[0] == "A"
    assert DatabaseService._grade_review_depth(70)[0] == "B"
    assert DatabaseService._grade_review_depth(50)[0] == "C"
    assert DatabaseService._grade_review_depth(30)[0] == "D"
    assert DatabaseService._grade_review_depth(10)[0] == "F"
    print("  ✅ Review 深度评级正确")


# ====================
# 运行测试
# ====================

def main():
    print("=" * 60)
    print("Review 质量评估测试")
    print("=" * 60)

    tests = [
        ("GET /review-quality 报告端点", test_review_quality_report_endpoint),
        ("GET /review-quality 日期范围", test_review_quality_report_with_date_range),
        ("GET /review-quality top_n 参数", test_review_quality_report_with_top_n),
        ("覆盖率指标字段", test_review_quality_coverage_metrics),
        ("延迟指标字段", test_review_quality_delay_metrics),
        ("深度指标字段", test_review_quality_depth_metrics),
        ("状态分布字段", test_review_quality_state_distribution),
        ("洞察项评级完整性", test_review_quality_insights),
        ("GET /review-quality/trends", test_review_quality_trends_endpoint),
        ("趋势粒度选项", test_review_quality_trends_granularity),
        ("数据库未连接 503", test_review_quality_db_not_connected),
        ("覆盖率评级函数", test_grade_review_coverage),
        ("延迟评级函数", test_grade_review_delay),
        ("深度评级函数", test_grade_review_depth),
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
