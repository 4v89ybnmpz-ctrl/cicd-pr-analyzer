"""
趋势预警测试
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from unittest.mock import MagicMock, AsyncMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers.analysis import register_analysis_routes
from models.responses import TrendAlertsReport


MOCK_ALERTS = {
    "owner": "rust-lang", "repo": "rust",
    "period_days": 7,
    "alerts": [
        {
            "alert_type": "ci_failure", "severity": "critical",
            "title": "CI 失败率上升",
            "description": "CI 失败率从 10.0% 上升到 35.0%（+25.0%）",
            "current_value": 35.0, "previous_value": 10.0,
            "change_rate": 150.0, "threshold": 10.0,
            "dimension": "CI 成功率",
            "suggestion": "建议排查近期 CI 失败原因",
        },
        {
            "alert_type": "review_delay", "severity": "warning",
            "title": "Review 响应变慢",
            "description": "首次 Review 延迟从 4.0h 增加到 8.0h（+100%）",
            "current_value": 8.0, "previous_value": 4.0,
            "change_rate": 100.0, "threshold": 30.0,
            "dimension": "Review 延迟",
            "suggestion": "建议分配更多 reviewer",
        },
        {
            "alert_type": "contributor_loss", "severity": "info",
            "title": "活跃贡献者减少",
            "description": "活跃贡献者从 10 人减少到 8 人（-20%）",
            "current_value": 8, "previous_value": 10,
            "change_rate": -20.0, "threshold": 25.0,
            "dimension": "贡献者多样性",
            "suggestion": "建议关注核心贡献者状态",
        },
    ],
    "summary": {"total": 3, "critical": 1, "warning": 1, "info": 1},
    "generated_at": "2026-05-25T15:00:00",
}


def make_mock_db():
    db = MagicMock()
    db.get_trend_alerts = AsyncMock(return_value=MOCK_ALERTS)
    db.db = MagicMock()
    return db


def test_alerts_endpoint():
    """测试 GET /analysis/alerts/{owner}/{repo}"""
    app = FastAPI()
    db = make_mock_db()
    register_analysis_routes(app, db, MagicMock())
    client = TestClient(app)
    response = client.get("/analysis/alerts/rust-lang/rust")
    assert response.status_code == 200
    data = response.json()
    assert data["owner"] == "rust-lang"
    assert len(data["alerts"]) == 3
    print("  ✅ GET /alerts 端点正确")


def test_alerts_with_period():
    """测试 period_days 参数"""
    app = FastAPI()
    db = make_mock_db()
    register_analysis_routes(app, db, MagicMock())
    client = TestClient(app)
    response = client.get("/analysis/alerts/rust-lang/rust", params={"period_days": 14})
    assert response.status_code == 200
    print("  ✅ period_days 参数正确")


def test_alerts_severity():
    """测试预警严重程度"""
    app = FastAPI()
    db = make_mock_db()
    register_analysis_routes(app, db, MagicMock())
    client = TestClient(app)
    data = client.get("/analysis/alerts/rust-lang/rust").json()
    severities = [a["severity"] for a in data["alerts"]]
    for s in severities:
        assert s in ("critical", "warning", "info")
    print("  ✅ 预警严重程度正确")


def test_alerts_types():
    """测试预警类型"""
    app = FastAPI()
    db = make_mock_db()
    register_analysis_routes(app, db, MagicMock())
    client = TestClient(app)
    data = client.get("/analysis/alerts/rust-lang/rust").json()
    types = [a["alert_type"] for a in data["alerts"]]
    assert "ci_failure" in types
    assert "review_delay" in types
    assert "contributor_loss" in types
    print("  ✅ 预警类型正确")


def test_alerts_summary():
    """测试预警摘要"""
    app = FastAPI()
    db = make_mock_db()
    register_analysis_routes(app, db, MagicMock())
    client = TestClient(app)
    data = client.get("/analysis/alerts/rust-lang/rust").json()
    summary = data["summary"]
    assert summary["total"] == 3
    assert summary["critical"] == 1
    assert summary["warning"] == 1
    assert summary["info"] == 1
    print("  ✅ 预警摘要正确")


def test_alerts_fields():
    """测试预警字段完整性"""
    app = FastAPI()
    db = make_mock_db()
    register_analysis_routes(app, db, MagicMock())
    client = TestClient(app)
    data = client.get("/analysis/alerts/rust-lang/rust").json()
    for a in data["alerts"]:
        assert "alert_type" in a
        assert "severity" in a
        assert "title" in a
        assert "description" in a
        assert "current_value" in a
        assert "previous_value" in a
        assert "suggestion" in a
    print("  ✅ 预警字段完整")


def test_alerts_db_not_connected():
    """测试数据库未连接返回 503"""
    app = FastAPI()
    db = MagicMock()
    db.db = None
    register_analysis_routes(app, db, MagicMock())
    client = TestClient(app)
    response = client.get("/analysis/alerts/test/test")
    assert response.status_code == 503
    print("  ✅ 数据库未连接返回 503 正确")


def test_no_alerts():
    """测试无预警场景"""
    app = FastAPI()
    db = MagicMock()
    db.get_trend_alerts = AsyncMock(return_value={
        "owner": "test", "repo": "test", "period_days": 7,
        "alerts": [], "summary": {"total": 0, "critical": 0, "warning": 0, "info": 0},
        "generated_at": "2026-05-25T15:00:00",
    })
    db.db = MagicMock()
    register_analysis_routes(app, db, MagicMock())
    client = TestClient(app)
    data = client.get("/analysis/alerts/test/test").json()
    assert data["alerts"] == []
    assert data["summary"]["total"] == 0
    print("  ✅ 无预警场景正确")


def main():
    print("=" * 60)
    print("趋势预警测试")
    print("=" * 60)

    tests = [
        ("GET /alerts 端点", test_alerts_endpoint),
        ("period_days 参数", test_alerts_with_period),
        ("预警严重程度", test_alerts_severity),
        ("预警类型", test_alerts_types),
        ("预警摘要", test_alerts_summary),
        ("预警字段完整性", test_alerts_fields),
        ("数据库未连接 503", test_alerts_db_not_connected),
        ("无预警场景", test_no_alerts),
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
