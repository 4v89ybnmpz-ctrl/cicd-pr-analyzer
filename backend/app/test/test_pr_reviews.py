"""
PR Reviews 接口测试
覆盖：服务层 Mock、数据库 Mock、API 集成测试
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from unittest.mock import MagicMock, patch, PropertyMock
from datetime import datetime
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers.github import register_github_routes
from api.routers.database import register_database_routes


def make_mock_github_service():
    """构造 Mock GitHub 服务"""
    service = MagicMock()
    service.max_workers = 3

    # fetch_pr_reviews 模拟返回
    service.fetch_pr_reviews.return_value = {
        "owner": "rust-lang",
        "repo": "rust",
        "pr_number": 100,
        "reviews": [
            {
                "id": 12345,
                "review_id": 12345,
                "pr_number": 100,
                "user": "reviewer1",
                "user_id": 111,
                "user_type": "User",
                "avatar_url": "https://github.com/avatar1.png",
                "state": "APPROVED",
                "body": "LGTM!",
                "submitted_at": "2026-05-18T10:00:00Z",
                "commit_id": "abc123",
                "author_association": "CONTRIBUTOR",
                "url": "https://github.com/rust-lang/rust/pull/100#pullrequestreview-12345",
            },
            {
                "id": 12346,
                "review_id": 12346,
                "pr_number": 100,
                "user": "reviewer2",
                "user_id": 222,
                "user_type": "User",
                "avatar_url": "https://github.com/avatar2.png",
                "state": "CHANGES_REQUESTED",
                "body": "Please fix the typo",
                "submitted_at": "2026-05-18T11:00:00Z",
                "commit_id": "abc123",
                "author_association": "MEMBER",
                "url": "https://github.com/rust-lang/rust/pull/100#pullrequestreview-12346",
            },
        ],
        "total": 2,
        "error": None,
    }

    # fetch_all_pr_reviews 模拟返回
    service.fetch_all_pr_reviews.return_value = {
        "owner": "rust-lang",
        "repo": "rust",
        "results": [service.fetch_pr_reviews.return_value],
        "total_prs": 1,
        "success_count": 1,
        "failed_count": 0,
    }

    # fetch_prs_for_project 模拟返回（给 _get_pr_numbers 用）
    service.fetch_prs_for_project.return_value = {
        "prs": [{"number": 100}, {"number": 101}],
        "error": None,
    }

    return service


def make_mock_db():
    """构造 Mock 数据库"""
    db = MagicMock()

    db.get_pr_data.return_value = {
        "data": {
            "prs": [{"number": 100}, {"number": 101}]
        }
    }

    db.save_pr_reviews.return_value = True

    db.list_pr_reviews.return_value = {
        "data": [
            {
                "owner": "rust-lang", "repo": "rust", "pr_number": 100,
                "data": {"reviews": [], "total": 2, "error": None},
                "updated_at": "2026-05-18T10:00:00",
            }
        ],
        "total": 1,
        "page": 1,
        "size": 20,
        "total_pages": 1,
    }

    return db


# ====================
# 1. 服务层测试
# ====================

def test_fetch_pr_reviews_service():
    """测试 fetch_pr_reviews 返回数据格式"""
    from services.github_service import GitHubPRService, TokenPool

    service = GitHubPRService.__new__(GitHubPRService)
    service.token_pool = MagicMock()
    service.token_pool.get_token.return_value = "fake_token"
    service.base_url = "https://api.github.com"
    service.per_page = 100
    service.request_delay = 0
    service.max_retries = 3
    service.retry_delay = 0

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.side_effect = [
        [
            {
                "id": 111, "user": {"login": "alice", "id": 1, "type": "User", "avatar_url": "url"},
                "state": "APPROVED", "body": "Nice!", "submitted_at": "2026-05-18T10:00:00Z",
                "commit_id": "abc", "author_association": "CONTRIBUTOR", "html_url": "http://review",
            },
        ],
        [],
    ]
    service._make_request = MagicMock(return_value=mock_response)

    result = service.fetch_pr_reviews("owner", "repo", 1)

    assert result["owner"] == "owner"
    assert result["repo"] == "repo"
    assert result["pr_number"] == 1
    assert result["total"] == 1
    assert result["error"] is None
    assert result["reviews"][0]["user"] == "alice"
    assert result["reviews"][0]["state"] == "APPROVED"
    print("  ✅ fetch_pr_reviews 返回数据格式正确")


def test_fetch_pr_reviews_pagination():
    """测试 fetch_pr_reviews 分页"""
    from services.github_service import GitHubPRService

    service = GitHubPRService.__new__(GitHubPRService)
    service.token_pool = MagicMock()
    service.token_pool.get_token.return_value = "fake_token"
    service.base_url = "https://api.github.com"
    service.per_page = 100
    service.request_delay = 0
    service.max_retries = 3
    service.retry_delay = 0

    page1 = [{"id": i, "user": {"login": f"user{i}", "id": i, "type": "User", "avatar_url": ""},
              "state": "COMMENTED", "body": "", "submitted_at": "", "commit_id": "",
              "author_association": "", "html_url": ""} for i in range(100)]
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.side_effect = [page1, []]

    service._make_request = MagicMock(return_value=mock_response)

    result = service.fetch_pr_reviews("owner", "repo", 1)
    assert result["total"] == 100
    assert service._make_request.call_count == 2
    print("  ✅ fetch_pr_reviews 分页正确")


def test_fetch_pr_reviews_error():
    """测试 fetch_pr_reviews 错误处理"""
    from services.github_service import GitHubPRService

    service = GitHubPRService.__new__(GitHubPRService)
    service.token_pool = MagicMock()
    service.token_pool.get_token.return_value = None
    service.base_url = "https://api.github.com"
    service.per_page = 100
    service.request_delay = 0
    service.max_retries = 3
    service.retry_delay = 0

    mock_response = MagicMock()
    mock_response.status_code = 404
    service._make_request = MagicMock(return_value=mock_response)

    result = service.fetch_pr_reviews("owner", "repo", 999)
    assert result["error"] is not None
    assert result["total"] == 0
    print("  ✅ fetch_pr_reviews 404 错误处理正确")


# ====================
# 2. 数据库持久化测试
# ====================

def test_database_save_pr_reviews():
    """测试 save_pr_reviews"""
    from services.database_service import DatabaseService

    db = DatabaseService.__new__(DatabaseService)
    db.db = MagicMock()
    mock_collection = MagicMock()
    db.db.__getitem__ = MagicMock(return_value=mock_collection)

    ok = db.save_pr_reviews("rust-lang", "rust", 100, {"reviews": [], "total": 2})
    assert ok is True
    mock_collection.update_one.assert_called_once()
    print("  ✅ save_pr_reviews 正确")


def test_database_get_pr_reviews():
    """测试 get_pr_reviews"""
    from services.database_service import DatabaseService

    db = DatabaseService.__new__(DatabaseService)
    db.db = MagicMock()
    mock_collection = MagicMock()
    mock_collection.find_one.return_value = {"owner": "rust-lang", "repo": "rust", "pr_number": 100}
    db.db.__getitem__ = MagicMock(return_value=mock_collection)

    result = db.get_pr_reviews("rust-lang", "rust", 100)
    assert result is not None
    assert result["pr_number"] == 100
    print("  ✅ get_pr_reviews 正确")


def test_database_list_pr_reviews():
    """测试 list_pr_reviews"""
    from services.database_service import DatabaseService

    db = DatabaseService.__new__(DatabaseService)
    db.db = MagicMock()
    mock_collection = MagicMock()
    mock_collection.count_documents.return_value = 5
    mock_cursor = MagicMock()
    mock_cursor.sort.return_value.skip.return_value.limit.return_value = iter([
        {"owner": "rust-lang", "repo": "rust", "pr_number": i} for i in range(5)
    ])
    mock_collection.find.return_value = mock_cursor
    db.db.__getitem__ = MagicMock(return_value=mock_collection)

    result = db.list_pr_reviews("rust-lang", "rust")
    assert result["total"] == 5
    assert len(result["data"]) == 5
    print("  ✅ list_pr_reviews 分页查询正确")


def test_database_reviews_no_db():
    """测试数据库未连接时 Reviews 操作"""
    from services.database_service import DatabaseService

    db = DatabaseService.__new__(DatabaseService)
    db.db = None
    assert db.save_pr_reviews("x", "y", 1, {}) is False
    assert db.get_pr_reviews("x", "y", 1) is None
    assert db.list_pr_reviews()["total"] == 0
    print("  ✅ 数据库未连接时 Reviews 操作正确返回")


# ====================
# 3. API 集成测试
# ====================

def test_api_single_pr_reviews():
    """测试 GET /github/prs/{owner}/{repo}/{pr_number}/reviews"""
    app = FastAPI()
    router = app.router
    mock_cache = MagicMock()
    mock_service = make_mock_github_service()
    mock_db = make_mock_db()
    register_github_routes(router, mock_cache, mock_service, mock_db)

    client = TestClient(app)
    response = client.get("/github/prs/rust-lang/rust/100/reviews")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["total"] == 2
    assert data["reviews"][0]["state"] == "APPROVED"
    assert data["reviews"][1]["state"] == "CHANGES_REQUESTED"
    mock_db.save_pr_reviews.assert_called_once()
    print("  ✅ GET /reviews/{pr_number} 单PR Reviews 正确")


def test_api_all_pr_reviews():
    """测试 GET /github/prs/{owner}/{repo}/reviews"""
    app = FastAPI()
    router = app.router
    mock_cache = MagicMock()
    mock_service = make_mock_github_service()
    mock_db = make_mock_db()
    register_github_routes(router, mock_cache, mock_service, mock_db)

    client = TestClient(app)
    response = client.get("/github/prs/rust-lang/rust/reviews?limit=10")

    assert response.status_code == 200
    data = response.json()
    assert data["total_prs"] >= 1
    assert data["success_count"] >= 1
    print("  ✅ GET /reviews 全量 Reviews 正确")


def test_api_database_reviews():
    """测试 GET /database/reviews"""
    app = FastAPI()
    router = app.router
    mock_db = make_mock_db()
    register_database_routes(router, mock_db)

    client = TestClient(app)
    response = client.get("/database/reviews?owner=rust-lang&repo=rust")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    print("  ✅ GET /database/reviews 查询正确")


def test_api_database_reviews_no_db():
    """测试数据库未连接时 /database/reviews 返回 503"""
    app = FastAPI()
    router = app.router
    register_database_routes(router, None)

    client = TestClient(app)
    response = client.get("/database/reviews")

    assert response.status_code == 503
    print("  ✅ 数据库未连接 /database/reviews 返回 503")


def test_api_reviews_review_fields():
    """测试 Review 数据字段完整性"""
    app = FastAPI()
    router = app.router
    mock_cache = MagicMock()
    mock_service = make_mock_github_service()
    mock_db = make_mock_db()
    register_github_routes(router, mock_cache, mock_service, mock_db)

    client = TestClient(app)
    response = client.get("/github/prs/rust-lang/rust/100/reviews")
    reviews = response.json()["data"]["reviews"]

    required_fields = ["id", "user", "user_id", "state", "body", "submitted_at", "commit_id", "url"]
    for field in required_fields:
        assert field in reviews[0], f"缺少字段: {field}"
    print("  ✅ Review 数据字段完整")


# ====================
# 运行测试
# ====================

def main():
    """运行所有测试"""
    print("=" * 60)
    print("PR Reviews 接口测试")
    print("=" * 60)

    sections = [
        ("服务层", [
            ("fetch_pr_reviews 数据格式", test_fetch_pr_reviews_service),
            ("fetch_pr_reviews 分页", test_fetch_pr_reviews_pagination),
            ("fetch_pr_reviews 错误处理", test_fetch_pr_reviews_error),
        ]),
        ("数据库持久化", [
            ("save_pr_reviews", test_database_save_pr_reviews),
            ("get_pr_reviews", test_database_get_pr_reviews),
            ("list_pr_reviews", test_database_list_pr_reviews),
            ("数据库未连接", test_database_reviews_no_db),
        ]),
        ("API 集成", [
            ("GET /reviews/{pr_number}", test_api_single_pr_reviews),
            ("GET /reviews 全量", test_api_all_pr_reviews),
            ("GET /database/reviews", test_api_database_reviews),
            ("数据库未连接 503", test_api_database_reviews_no_db),
            ("Review 字段完整性", test_api_reviews_review_fields),
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
