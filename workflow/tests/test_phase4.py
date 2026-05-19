"""
Phase 4 测试 — 对话式接口 + PR Commits
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from unittest.mock import MagicMock, patch
import json


# ====================
# 对话式接口测试
# ====================

def test_chat_endpoint_registered():
    """测试 /agent/chat 端点已注册"""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from workflow.api.routes import register_workflow_routes

    app = FastAPI()
    router = app.router
    register_workflow_routes(router)
    client = TestClient(app)

    # 未初始化时返回 503
    resp = client.post("/agent/chat", json={"message": "hello"})
    assert resp.status_code == 503
    print("  ✅ /agent/chat 端点注册正确")


def test_chat_with_llm():
    """测试对话接口调用 Orchestrator"""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from workflow.api.routes import register_workflow_routes
    from workflow.agents.registry import agent_registry
    from workflow.config import workflow_config
    from workflow.agents.base_agent import BaseAgent

    app = FastAPI()
    router = app.router
    register_workflow_routes(router)
    client = TestClient(app)

    orig_llm = workflow_config.llm
    mock_llm = MagicMock()
    workflow_config.llm = mock_llm

    try:
        with patch("langgraph.prebuilt.create_react_agent") as mock_create:
            mock_agent = MagicMock()
            mock_agent.invoke.return_value = {
                "messages": [MagicMock(content="项目 CI/CD 能力良好，成功率 95%", type="ai")]
            }
            mock_create.return_value = mock_agent
            agent_registry.destroy("orchestrator")

            resp = client.post("/agent/chat", json={"message": "分析 rust-lang/rust"})
            assert resp.status_code == 200
            data = resp.json()
            assert "95%" in data["response"]
    finally:
        workflow_config.llm = orig_llm
        agent_registry.destroy("orchestrator")
    print("  ✅ /agent/chat 对话调用正确")


def test_chat_followup_question():
    """测试追问场景"""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from workflow.api.routes import register_workflow_routes
    from workflow.agents.registry import agent_registry
    from workflow.config import workflow_config

    app = FastAPI()
    router = app.router
    register_workflow_routes(router)
    client = TestClient(app)

    orig_llm = workflow_config.llm
    mock_llm = MagicMock()
    workflow_config.llm = mock_llm

    try:
        with patch("langgraph.prebuilt.create_react_agent") as mock_create:
            mock_agent = MagicMock()
            mock_agent.invoke.return_value = {
                "messages": [MagicMock(content="失败主要集中在 test-x86 job，原因是内存泄漏", type="ai")]
            }
            mock_create.return_value = mock_agent
            agent_registry.destroy("orchestrator")

            resp = client.post("/agent/chat", json={"message": "深入分析失败原因"})
            assert resp.status_code == 200
            assert "test-x86" in resp.json()["response"]
    finally:
        workflow_config.llm = orig_llm
        agent_registry.destroy("orchestrator")
    print("  ✅ /agent/chat 追问场景正确")


# ====================
# PR Commits 接口测试
# ====================

def test_fetch_pr_commits_service():
    """测试 fetch_pr_commits 服务方法"""
    from app.services.github_service import GitHubPRService

    service = GitHubPRService.__new__(GitHubPRService)
    service.token_pool = MagicMock()
    service.token_pool.get_token.return_value = "fake"
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
                "sha": "abc123",
                "commit": {
                    "message": "fix: memory leak",
                    "author": {"name": "dev", "email": "dev@test.com", "date": "2026-05-18T10:00:00Z"},
                    "committer": {"name": "dev", "date": "2026-05-18T10:00:00Z"},
                    "verification": {"verified": True},
                },
                "html_url": "https://github.com/test/project/commit/abc123",
                "stats": {"additions": 10, "deletions": 5, "total": 15},
                "files": [{"filename": "a.py"}, {"filename": "b.py"}],
            },
        ],
        [],
    ]
    service._make_request = MagicMock(return_value=mock_response)

    result = service.fetch_pr_commits("test", "project", 1)

    assert result["total"] == 1
    assert result["commits"][0]["sha"] == "abc123"
    assert result["commits"][0]["message"] == "fix: memory leak"
    assert result["commits"][0]["additions"] == 10
    assert result["commits"][0]["files_changed"] == 2
    assert result["error"] is None
    print("  ✅ fetch_pr_commits 服务方法正确")


def test_fetch_pr_commits_404():
    """测试 fetch_pr_commits 404 处理"""
    from app.services.github_service import GitHubPRService

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

    result = service.fetch_pr_commits("x", "y", 999)
    assert result["error"] == "PR不存在"
    assert result["total"] == 0
    print("  ✅ fetch_pr_commits 404 处理正确")


def test_fetch_all_pr_commits():
    """测试并发获取 PR Commits"""
    from app.services.github_service import GitHubPRService

    service = GitHubPRService.__new__(GitHubPRService)
    service.token_pool = MagicMock()
    service.max_workers = 2

    service.fetch_pr_commits = MagicMock(side_effect=[
        {"owner": "t", "repo": "p", "pr_number": 1, "commits": [{"sha": "a"}], "total": 1, "error": None},
        {"owner": "t", "repo": "p", "pr_number": 2, "commits": [{"sha": "b"}], "total": 1, "error": None},
    ])

    result = service.fetch_all_pr_commits("t", "p", [1, 2])
    assert result["success_count"] == 2
    assert result["failed_count"] == 0
    print("  ✅ fetch_all_pr_commits 并发获取正确")


def test_database_save_pr_commits():
    """测试 PR Commits 数据库持久化"""
    from app.services.database_service import DatabaseService

    db = DatabaseService.__new__(DatabaseService)
    db.db = MagicMock()
    mock_collection = MagicMock()
    db.db.__getitem__ = MagicMock(return_value=mock_collection)

    ok = db.save_pr_commits("t", "p", 1, {"commits": [{"sha": "abc"}], "total": 1, "error": None})
    assert ok is True
    mock_collection.update_one.assert_called_once()
    print("  ✅ save_pr_commits 持久化正确")


def test_database_get_pr_commits():
    """测试获取 PR Commits"""
    from app.services.database_service import DatabaseService

    db = DatabaseService.__new__(DatabaseService)
    db.db = MagicMock()
    mock_collection = MagicMock()
    mock_collection.find_one.return_value = {"owner": "t", "repo": "p", "pr_number": 1}
    db.db.__getitem__ = MagicMock(return_value=mock_collection)

    result = db.get_pr_commits("t", "p", 1)
    assert result["pr_number"] == 1
    print("  ✅ get_pr_commits 获取正确")


def test_database_list_pr_commits():
    """测试分页查询 PR Commits"""
    from app.services.database_service import DatabaseService

    db = DatabaseService.__new__(DatabaseService)
    db.db = MagicMock()
    mock_collection = MagicMock()
    mock_collection.count_documents.return_value = 3
    mock_cursor = MagicMock()
    mock_cursor.sort.return_value.skip.return_value.limit.return_value = iter([
        {"pr_number": 1}, {"pr_number": 2},
    ])
    mock_collection.find.return_value = mock_cursor
    db.db.__getitem__ = MagicMock(return_value=mock_collection)

    result = db.list_pr_commits("t", "p", page=1, size=2)
    assert result["total"] == 3
    assert len(result["data"]) == 2
    print("  ✅ list_pr_commits 分页查询正确")


def test_commits_github_api_route():
    """测试 GitHub Commits API 路由"""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.routers.github import register_github_routes

    app = FastAPI()
    router = app.router
    mock_service = MagicMock()
    mock_service.fetch_pr_commits.return_value = {
        "owner": "t", "repo": "p", "pr_number": 1,
        "commits": [{"sha": "abc", "message": "fix"}],
        "total": 1, "error": None,
    }
    mock_service.fetch_all_pr_commits.return_value = {
        "owner": "t", "repo": "p", "results": [], "total_prs": 0,
        "success_count": 0, "failed_count": 0,
    }
    register_github_routes(router, MagicMock(), mock_service, None)
    client = TestClient(app)

    resp = client.get("/github/prs/t/p/1/commits")
    assert resp.status_code == 200
    assert resp.json()["data"]["total"] == 1
    print("  ✅ GET /github/prs/{owner}/{repo}/{pr_number}/commits 路由正确")


def test_commits_database_route():
    """测试 Database Commits 查询路由"""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.routers.database import register_database_routes

    app = FastAPI()
    router = app.router
    mock_db = MagicMock()
    mock_db.list_pr_commits.return_value = {"data": [], "total": 0, "page": 1, "size": 20}
    register_database_routes(router, mock_db)
    client = TestClient(app)

    resp = client.get("/database/commits?owner=t&repo=p")
    assert resp.status_code == 200
    print("  ✅ GET /database/commits 路由正确")


# ====================
# 运行测试
# ====================

def main():
    print("=" * 60)
    print("Phase 4 测试 — 对话式接口 + PR Commits")
    print("=" * 60)

    sections = [
        ("Health Check", [
            ("/health", test_health_check),
        ]),
        ("对话式接口", [
            ("/agent/chat 注册", test_chat_endpoint_registered),
            ("/agent/chat 调用", test_chat_with_llm),
            ("/agent/chat 追问", test_chat_followup_question),
        ]),
        ("PR Commits 服务", [
            ("fetch_pr_commits", test_fetch_pr_commits_service),
            ("fetch_pr_commits 404", test_fetch_pr_commits_404),
            ("fetch_all_pr_commits", test_fetch_all_pr_commits),
        ]),
        ("PR Commits 数据库", [
            ("save_pr_commits", test_database_save_pr_commits),
            ("get_pr_commits", test_database_get_pr_commits),
            ("list_pr_commits", test_database_list_pr_commits),
        ]),
        ("PR Commits 路由", [
            ("GitHub 路由", test_commits_github_api_route),
            ("Database 路由", test_commits_database_route),
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
