"""
AtomGit 服务测试用例
测试新增的 PR Detail / Reviews / Commits / Files / Timeline / Issues 功能
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from app.gitcode.service import AtomGitService


# ========================
# Mock 数据
# ========================

MOCK_PR_DETAIL = {
    "number": 42,
    "title": "Fix critical bug",
    "body": "This PR fixes a critical bug",
    "state": "open",
    "draft": False,
    "user": {"login": "developer", "id": 100, "avatar_url": "https://avatar.url", "type": "User"},
    "labels": [{"name": "bug", "color": "ff0000"}, {"name": "critical", "color": "00ff00"}],
    "assignees": [{"login": "reviewer1", "avatar_url": "https://avatar.url/r1"}],
    "requested_reviewers": [{"login": "reviewer2", "avatar_url": "https://avatar.url/r2"}],
    "milestone": {"number": 1, "title": "v2.0", "state": "open"},
    "head": {"ref": "fix-bug", "sha": "abc123", "label": "fix-bug"},
    "base": {"ref": "main", "sha": "def456", "label": "main"},
    "created_at": "2026-01-01T00:00:00Z",
    "updated_at": "2026-01-02T00:00:00Z",
    "closed_at": None,
    "merged_at": None,
    "mergeable": True,
    "merged": False,
    "merge_commit_sha": None,
    "commits": 3,
    "additions": 50,
    "deletions": 10,
    "changed_files": 5,
    "comments": 2,
    "review_comments": 1,
    "html_url": "https://atomgit.com/owner/repo/pulls/42",
}

MOCK_REVIEW = {
    "id": 1001,
    "user": {"login": "reviewer1", "id": 200, "type": "User", "avatar_url": "https://avatar.url/r1"},
    "state": "APPROVED",
    "body": "Looks good to me",
    "submitted_at": "2026-01-01T12:00:00Z",
    "commit_id": "abc123",
    "author_association": "COLLABORATOR",
    "html_url": "https://atomgit.com/owner/repo/pulls/42/reviews/1001",
}

MOCK_COMMIT = {
    "sha": "abc123def456",
    "commit": {
        "message": "Fix the bug",
        "author": {"name": "developer", "email": "dev@example.com", "date": "2026-01-01T10:00:00Z"},
        "committer": {"name": "developer", "date": "2026-01-01T10:00:00Z"},
        "verification": {"verified": True},
    },
    "html_url": "https://atomgit.com/owner/repo/commits/abc123",
}

MOCK_FILE = {
    "filename": "src/main.py",
    "status": "modified",
    "additions": 10,
    "deletions": 3,
    "changes": 13,
    "sha": "file123",
    "patch": "@@ -1,3 +1,10 @@",
}

MOCK_TIMELINE_EVENT = {
    "id": 5001,
    "event": "labeled",
    "actor": {"login": "developer", "id": 100},
    "commit_id": None,
    "created_at": "2026-01-01T00:00:00Z",
    "label": {"name": "bug", "color": "ff0000"},
}

MOCK_ISSUE = {
    "number": 99,
    "title": "Bug report",
    "body": "Something is broken",
    "state": "open",
    "user": {"login": "reporter", "id": 300},
    "labels": [{"name": "bug"}],
    "assignees": [{"login": "developer"}],
    "comments": 5,
    "created_at": "2026-01-01T00:00:00Z",
    "updated_at": "2026-01-02T00:00:00Z",
    "closed_at": None,
    "html_url": "https://atomgit.com/owner/repo/issues/99",
}


# ========================
# 服务层测试
# ========================

class TestAtomGitPullDetail:
    """PR 详情获取测试"""

    def test_fetch_pull_detail_success(self):
        """测试成功获取 PR 详情"""
        async def _test():
            service = AtomGitService(access_token="test_token")
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = MOCK_PR_DETAIL

            with patch.object(service, '_request', new_callable=AsyncMock, return_value=mock_response):
                result = await service.fetch_pull_detail("owner", "repo", 42)

            assert result["error"] is None
            assert result["pull_number"] == 42
            detail = result["detail"]
            assert detail["number"] == 42
            assert detail["title"] == "Fix critical bug"
            assert detail["state"] == "open"
            assert detail["draft"] is False
            assert detail["user"]["login"] == "developer"
            assert detail["additions"] == 50
            assert detail["deletions"] == 10
            assert detail["changed_files"] == 5
            assert detail["merged"] is False
            assert detail["milestone"]["title"] == "v2.0"
            assert len(detail["labels"]) == 2
            assert len(detail["assignees"]) == 1
            assert len(detail["requested_reviewers"]) == 1

        asyncio.run(_test())

    def test_fetch_pull_detail_error(self):
        """测试 PR 详情获取失败"""
        async def _test():
            service = AtomGitService(access_token="test_token")
            with patch.object(service, '_request', new_callable=AsyncMock, side_effect=Exception("API error")):
                result = await service.fetch_pull_detail("owner", "repo", 42)
            assert result["error"] == "API error"
            assert result["detail"] == {}

        asyncio.run(_test())


class TestAtomGitReviews:
    """PR Reviews 获取测试"""

    def test_fetch_pull_reviews_success(self):
        """测试成功获取 Reviews"""
        async def _test():
            service = AtomGitService(access_token="test_token")
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = [MOCK_REVIEW]

            with patch.object(service, '_request', new_callable=AsyncMock, return_value=mock_response):
                result = await service.fetch_pull_reviews("owner", "repo", 42)

            assert result["error"] is None
            assert result["total"] == 1
            review = result["reviews"][0]
            assert review["user"] == "reviewer1"
            assert review["state"] == "APPROVED"
            assert review["body"] == "Looks good to me"

        asyncio.run(_test())

    def test_fetch_pull_reviews_empty(self):
        """测试 Reviews 为空"""
        async def _test():
            service = AtomGitService(access_token="test_token")
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = []

            with patch.object(service, '_request', new_callable=AsyncMock, return_value=mock_response):
                result = await service.fetch_pull_reviews("owner", "repo", 42)

            assert result["error"] is None
            assert result["total"] == 0

        asyncio.run(_test())


class TestAtomGitCommits:
    """PR Commits 获取测试"""

    def test_fetch_pull_commits_success(self):
        """测试成功获取 Commits"""
        async def _test():
            service = AtomGitService(access_token="test_token")
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = [MOCK_COMMIT]

            with patch.object(service, '_request', new_callable=AsyncMock, return_value=mock_response):
                result = await service.fetch_pull_commits("owner", "repo", 42)

            assert result["error"] is None
            assert result["total"] == 1
            commit = result["commits"][0]
            assert commit["sha"] == "abc123def456"
            assert commit["message"] == "Fix the bug"
            assert commit["author_name"] == "developer"
            assert commit["verified"] is True

        asyncio.run(_test())


class TestAtomGitFiles:
    """PR 变更文件获取测试"""

    def test_fetch_pull_files_success(self):
        """测试成功获取变更文件"""
        async def _test():
            service = AtomGitService(access_token="test_token")
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = [MOCK_FILE]

            with patch.object(service, '_request', new_callable=AsyncMock, return_value=mock_response):
                result = await service.fetch_pull_files("owner", "repo", 42)

            assert result["error"] is None
            assert result["total"] == 1
            f = result["files"][0]
            assert f["filename"] == "src/main.py"
            assert f["status"] == "modified"
            assert f["additions"] == 10
            assert f["deletions"] == 3

        asyncio.run(_test())


class TestAtomGitTimeline:
    """PR 时间线获取测试"""

    def test_fetch_pull_timeline_success(self):
        """测试成功获取时间线"""
        async def _test():
            service = AtomGitService(access_token="test_token")
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = [MOCK_TIMELINE_EVENT]

            with patch.object(service, '_request', new_callable=AsyncMock, return_value=mock_response):
                result = await service.fetch_pull_timeline("owner", "repo", 42)

            assert result["error"] is None
            assert result["total"] == 1
            event = result["events"][0]
            assert event["event"] == "labeled"
            assert event["actor"] == "developer"
            assert event["label"] == "bug"

        asyncio.run(_test())


class TestAtomGitIssues:
    """Issue 获取测试"""

    def test_fetch_issues_success(self):
        """测试成功获取 Issue 列表（PR 被过滤）"""
        async def _test():
            service = AtomGitService(access_token="test_token")
            issue_with_pr = {**MOCK_ISSUE, "pull_request": {"url": "https://atomgit.com/owner/repo/pulls/1"}}
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = [issue_with_pr, MOCK_ISSUE]

            with patch.object(service, '_request', new_callable=AsyncMock, return_value=mock_response):
                result = await service.fetch_issues("owner", "repo")

            assert result["error"] is None
            assert result["total"] == 1
            assert result["issues"][0]["number"] == 99
            assert result["issues"][0]["title"] == "Bug report"

        asyncio.run(_test())

    def test_fetch_issue_detail_success(self):
        """测试成功获取 Issue 详情"""
        async def _test():
            service = AtomGitService(access_token="test_token")
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = MOCK_ISSUE

            with patch.object(service, '_request', new_callable=AsyncMock, return_value=mock_response):
                result = await service.fetch_issue_detail("owner", "repo", 99)

            assert result["error"] is None
            assert result["detail"]["number"] == 99
            assert result["detail"]["title"] == "Bug report"

        asyncio.run(_test())


class TestAtomGitBatchFetch:
    """批量并发获取测试"""

    def test_fetch_all_pull_details(self):
        """测试并发获取多个 PR 详情"""
        async def _test():
            service = AtomGitService(access_token="test_token")

            async def mock_fetch_detail(owner, repo, pull_number):
                return {
                    "owner": owner, "repo": repo, "pull_number": pull_number,
                    "detail": {"number": pull_number, "title": f"PR {pull_number}"},
                    "error": None,
                }

            with patch.object(service, 'fetch_pull_detail', side_effect=mock_fetch_detail):
                result = await service.fetch_all_pull_details("owner", "repo", [1, 2, 3], max_workers=2)

            assert result["total_prs"] == 3
            assert result["success_count"] == 3
            assert result["failed_count"] == 0

        asyncio.run(_test())

    def test_fetch_all_pull_reviews(self):
        """测试并发获取多个 PR Reviews"""
        async def _test():
            service = AtomGitService(access_token="test_token")

            async def mock_fetch_reviews(owner, repo, pull_number):
                return {
                    "owner": owner, "repo": repo, "pull_number": pull_number,
                    "reviews": [{"id": 1, "user": "r1", "state": "APPROVED"}],
                    "total": 1, "error": None,
                }

            with patch.object(service, 'fetch_pull_reviews', side_effect=mock_fetch_reviews):
                result = await service.fetch_all_pull_reviews("owner", "repo", [1, 2], max_workers=2)

            assert result["total_prs"] == 2
            assert result["success_count"] == 2

        asyncio.run(_test())

    def test_fetch_all_pull_commits(self):
        """测试并发获取多个 PR Commits"""
        async def _test():
            service = AtomGitService(access_token="test_token")

            async def mock_fetch_commits(owner, repo, pull_number):
                return {
                    "owner": owner, "repo": repo, "pull_number": pull_number,
                    "commits": [{"sha": "abc", "message": "fix"}],
                    "total": 1, "error": None,
                }

            with patch.object(service, 'fetch_pull_commits', side_effect=mock_fetch_commits):
                result = await service.fetch_all_pull_commits("owner", "repo", [1], max_workers=2)

            assert result["total_prs"] == 1
            assert result["success_count"] == 1

        asyncio.run(_test())

    def test_batch_with_exception(self):
        """测试批量获取中部分失败"""
        async def _test():
            service = AtomGitService(access_token="test_token")

            async def mock_fetch_detail(owner, repo, pull_number):
                if pull_number == 2:
                    raise Exception("Network error")
                return {
                    "owner": owner, "repo": repo, "pull_number": pull_number,
                    "detail": {"number": pull_number}, "error": None,
                }

            with patch.object(service, 'fetch_pull_detail', side_effect=mock_fetch_detail):
                result = await service.fetch_all_pull_details("owner", "repo", [1, 2, 3], max_workers=2)

            assert result["total_prs"] == 3
            assert result["failed_count"] == 1

        asyncio.run(_test())


class TestAtomGitFormatting:
    """数据格式化测试"""

    def test_format_pull_detail_with_milestone(self):
        """测试带里程碑的 PR 详情格式化"""
        service = AtomGitService(access_token="test_token")
        result = service._format_pull_detail(MOCK_PR_DETAIL)
        assert result["milestone"]["title"] == "v2.0"
        assert result["milestone"]["number"] == 1
        assert result["head"]["ref"] == "fix-bug"
        assert result["base"]["ref"] == "main"

    def test_format_pull_detail_without_milestone(self):
        """测试无里程碑的 PR 详情格式化"""
        service = AtomGitService(access_token="test_token")
        pr = {**MOCK_PR_DETAIL, "milestone": None}
        result = service._format_pull_detail(pr)
        assert result["milestone"] is None

    def test_format_review(self):
        """测试 Review 格式化"""
        service = AtomGitService(access_token="test_token")
        result = service._format_review(MOCK_REVIEW)
        assert result["user"] == "reviewer1"
        assert result["state"] == "APPROVED"
        assert result["review_id"] == 1001

    def test_format_commit(self):
        """测试 Commit 格式化"""
        service = AtomGitService(access_token="test_token")
        result = service._format_commit(MOCK_COMMIT)
        assert result["sha"] == "abc123def456"
        assert result["message"] == "Fix the bug"
        assert result["verified"] is True

    def test_format_file(self):
        """测试变更文件格式化"""
        service = AtomGitService(access_token="test_token")
        result = service._format_file(MOCK_FILE)
        assert result["filename"] == "src/main.py"
        assert result["additions"] == 10

    def test_format_timeline_event(self):
        """测试时间线事件格式化"""
        service = AtomGitService(access_token="test_token")
        result = service._format_timeline_event(MOCK_TIMELINE_EVENT)
        assert result["event"] == "labeled"
        assert result["actor"] == "developer"
        assert result["label"] == "bug"

    def test_format_issue(self):
        """测试 Issue 格式化"""
        service = AtomGitService(access_token="test_token")
        result = service._format_issue(MOCK_ISSUE)
        assert result["number"] == 99
        assert result["title"] == "Bug report"
        assert result["user"] == "reporter"
        assert result["labels"] == ["bug"]

    def test_format_pull_detail_empty_user(self):
        """测试 PR 详情中 user 为空的情况"""
        service = AtomGitService(access_token="test_token")
        pr = {**MOCK_PR_DETAIL, "user": None}
        result = service._format_pull_detail(pr)
        assert result["user"]["login"] == ""
        assert result["user"]["id"] is None


# ========================
# API 集成测试
# ========================

class TestAtomGitAPI:
    """API 端点集成测试"""

    @pytest.fixture
    def client(self):
        """创建测试客户端"""
        from fastapi.testclient import TestClient
        from app.main import app
        return TestClient(app)

    def test_pull_detail_endpoint(self, client):
        """测试 PR 详情端点"""
        response = client.get("/atomgit/pulls/test-owner/test-repo/42/detail")
        assert response.status_code in [401, 500]

    def test_pull_reviews_endpoint(self, client):
        """测试 PR Reviews 端点"""
        response = client.get("/atomgit/pulls/test-owner/test-repo/42/reviews")
        assert response.status_code in [401, 500]

    def test_pull_commits_endpoint(self, client):
        """测试 PR Commits 端点"""
        response = client.get("/atomgit/pulls/test-owner/test-repo/42/commits")
        assert response.status_code in [401, 500]

    def test_pull_files_endpoint(self, client):
        """测试 PR 变更文件端点"""
        response = client.get("/atomgit/pulls/test-owner/test-repo/42/files")
        assert response.status_code in [401, 500]

    def test_pull_timeline_endpoint(self, client):
        """测试 PR 时间线端点"""
        response = client.get("/atomgit/pulls/test-owner/test-repo/42/timeline")
        assert response.status_code in [401, 500]

    def test_issues_endpoint(self, client):
        """测试 Issue 列表端点"""
        response = client.get("/atomgit/issues/test-owner/test-repo")
        assert response.status_code in [401, 500]

    def test_issue_detail_endpoint(self, client):
        """测试 Issue 详情端点"""
        response = client.get("/atomgit/issues/test-owner/test-repo/99")
        assert response.status_code in [401, 500]
