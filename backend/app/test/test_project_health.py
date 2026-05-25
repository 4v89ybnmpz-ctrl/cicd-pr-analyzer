"""
项目健康度评分测试
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from unittest.mock import MagicMock, AsyncMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers.analysis import register_analysis_routes
from models.responses import ProjectHealthReport, ProjectHealthTrendsResponse


MOCK_HEALTH_REPORT = {
    "owner": "rust-lang", "repo": "rust",
    "start_date": None, "end_date": None,
    "overall_score": 78.5, "overall_grade": "B",
    "dimensions": [
        {"name": "PR 存活时间", "value": 48.0, "score": 80.0, "weight": 0.2, "weighted_score": 16.0, "grade": "B", "description": "平均存活 48.0h (2.0天), 共 50 个 PR"},
        {"name": "Merge 率", "value": 75.0, "score": 100.0, "weight": 0.15, "weighted_score": 15.0, "grade": "A", "description": "Merge 率 75.0%"},
        {"name": "Review 覆盖率", "value": 85.0, "score": 85.0, "weight": 0.25, "weighted_score": 21.25, "grade": "B", "description": "覆盖率 85.0%"},
        {"name": "CI 成功率", "value": 90.0, "score": 90.0, "weight": 0.2, "weighted_score": 18.0, "grade": "A", "description": "成功率 90.0%"},
        {"name": "贡献者多样性", "value": 45.0, "score": 85.0, "weight": 0.1, "weighted_score": 8.5, "grade": "B", "description": "Top3 贡献者占比 45.0%"},
        {"name": "Issue 响应速度", "value": 36.0, "score": 70.0, "weight": 0.1, "weighted_score": 7.0, "grade": "C", "description": "平均关闭时间 36.0h"},
    ],
    "radar_data": [
        {"dimension": "PR 存活时间", "score": 80.0},
        {"dimension": "Merge 率", "score": 100.0},
        {"dimension": "Review 覆盖率", "score": 85.0},
        {"dimension": "CI 成功率", "score": 90.0},
        {"dimension": "贡献者多样性", "score": 85.0},
        {"dimension": "Issue 响应速度", "score": 70.0},
    ],
    "insights": [
        {"name": "综合健康度", "value": 78.5, "grade": "B", "description": "综合健康度 78.5 分，评级 B", "suggestion": "项目整体健康，部分维度有提升空间"},
    ],
    "generated_at": "2026-05-25T12:00:00",
    "data_available": True,
}

MOCK_HEALTH_TRENDS = [
    {"period": "2026-04", "total_prs": 20, "merged_prs": 15, "merge_rate": 75.0, "contributor_count": 8, "merge_score": 100.0, "diversity_score": 80.0},
    {"period": "2026-05", "total_prs": 25, "merged_prs": 18, "merge_rate": 72.0, "contributor_count": 10, "merge_score": 100.0, "diversity_score": 100.0},
]


def make_mock_db():
    db = MagicMock()
    db.get_project_health_report = AsyncMock(return_value=MOCK_HEALTH_REPORT)
    db.get_project_health_trends = AsyncMock(return_value=MOCK_HEALTH_TRENDS)
    db.db = MagicMock()
    return db


def create_test_app():
    return FastAPI()


def test_health_report_endpoint():
    """测试 GET /analysis/health/{owner}/{repo}"""
    app = create_test_app()
    db = make_mock_db()
    register_analysis_routes(app, db, MagicMock())

    client = TestClient(app)
    response = client.get("/analysis/health/rust-lang/rust")

    assert response.status_code == 200
    data = response.json()
    assert data["owner"] == "rust-lang"
    assert data["overall_grade"] == "B"
    assert len(data["dimensions"]) == 6
    assert len(data["radar_data"]) == 6
    assert data["data_available"] is True
    print("  ✅ GET /health 报告端点正确")


def test_health_report_with_date_range():
    """测试带日期范围"""
    app = create_test_app()
    db = make_mock_db()
    register_analysis_routes(app, db, MagicMock())

    client = TestClient(app)
    response = client.get("/analysis/health/rust-lang/rust", params={"start_date": "2026-05-01", "end_date": "2026-05-25"})

    assert response.status_code == 200
    print("  ✅ GET /health 日期范围参数正确")


def test_health_dimensions_completeness():
    """测试维度完整性"""
    app = create_test_app()
    db = make_mock_db()
    register_analysis_routes(app, db, MagicMock())

    client = TestClient(app)
    data = client.get("/analysis/health/rust-lang/rust").json()

    dim_names = [d["name"] for d in data["dimensions"]]
    assert "PR 存活时间" in dim_names
    assert "Merge 率" in dim_names
    assert "Review 覆盖率" in dim_names
    assert "CI 成功率" in dim_names
    assert "贡献者多样性" in dim_names
    assert "Issue 响应速度" in dim_names

    for d in data["dimensions"]:
        assert "score" in d
        assert "weight" in d
        assert "grade" in d
    print("  ✅ 6 个维度完整")


def test_health_grades():
    """测试评级正确性"""
    app = create_test_app()
    db = make_mock_db()
    register_analysis_routes(app, db, MagicMock())

    client = TestClient(app)
    data = client.get("/analysis/health/rust-lang/rust").json()

    assert data["overall_grade"] in ["A", "B", "C", "D", "F"]
    for d in data["dimensions"]:
        if d["grade"]:
            assert d["grade"] in ["A", "B", "C", "D", "F"]
    print("  ✅ 评级 A-F 正确")


def test_health_radar_data():
    """测试雷达图数据"""
    app = create_test_app()
    db = make_mock_db()
    register_analysis_routes(app, db, MagicMock())

    client = TestClient(app)
    data = client.get("/analysis/health/rust-lang/rust").json()

    assert len(data["radar_data"]) == 6
    for r in data["radar_data"]:
        assert "dimension" in r
        assert "score" in r
    print("  ✅ 雷达图数据正确")


def test_health_insights():
    """测试洞察项"""
    app = create_test_app()
    db = make_mock_db()
    register_analysis_routes(app, db, MagicMock())

    client = TestClient(app)
    data = client.get("/analysis/health/rust-lang/rust").json()

    assert len(data["insights"]) >= 1
    assert data["insights"][0]["name"] == "综合健康度"
    print("  ✅ 洞察项正确")


def test_health_trends_endpoint():
    """测试 GET /analysis/health/{owner}/{repo}/trends"""
    app = create_test_app()
    db = make_mock_db()
    register_analysis_routes(app, db, MagicMock())

    client = TestClient(app)
    response = client.get("/analysis/health/rust-lang/rust/trends", params={"granularity": "month"})

    assert response.status_code == 200
    data = response.json()
    assert data["granularity"] == "month"
    assert len(data["trends"]) == 2
    print("  ✅ GET /health/trends 趋势端点正确")


def test_health_trends_granularity():
    """测试趋势粒度"""
    app = create_test_app()
    db = make_mock_db()
    register_analysis_routes(app, db, MagicMock())

    client = TestClient(app)
    for g in ["day", "week", "month"]:
        response = client.get("/analysis/health/rust-lang/rust/trends", params={"granularity": g})
        assert response.status_code == 200
        assert response.json()["granularity"] == g
    print("  ✅ 趋势粒度 day/week/month 均支持")


def test_health_db_not_connected():
    """测试数据库未连接返回 503"""
    app = create_test_app()
    db = MagicMock()
    db.db = None
    register_analysis_routes(app, db, MagicMock())

    client = TestClient(app)
    response = client.get("/analysis/health/test/test")
    assert response.status_code == 503
    print("  ✅ 数据库未连接返回 503 正确")


def test_score_to_grade():
    """测试分数转评级函数"""
    from services.database_service import DatabaseService

    assert DatabaseService._score_to_grade(95) == "A"
    assert DatabaseService._score_to_grade(90) == "A"
    assert DatabaseService._score_to_grade(80) == "B"
    assert DatabaseService._score_to_grade(75) == "B"
    assert DatabaseService._score_to_grade(65) == "C"
    assert DatabaseService._score_to_grade(60) == "C"
    assert DatabaseService._score_to_grade(50) == "D"
    assert DatabaseService._score_to_grade(40) == "D"
    assert DatabaseService._score_to_grade(30) == "F"
    assert DatabaseService._score_to_grade(10) == "F"
    print("  ✅ 分数转评级函数正确")


def main():
    print("=" * 60)
    print("项目健康度评分测试")
    print("=" * 60)

    tests = [
        ("GET /health 报告端点", test_health_report_endpoint),
        ("GET /health 日期范围", test_health_report_with_date_range),
        ("6 个维度完整性", test_health_dimensions_completeness),
        ("评级 A-F 正确", test_health_grades),
        ("雷达图数据", test_health_radar_data),
        ("洞察项", test_health_insights),
        ("GET /health/trends", test_health_trends_endpoint),
        ("趋势粒度选项", test_health_trends_granularity),
        ("数据库未连接 503", test_health_db_not_connected),
        ("分数转评级函数", test_score_to_grade),
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
