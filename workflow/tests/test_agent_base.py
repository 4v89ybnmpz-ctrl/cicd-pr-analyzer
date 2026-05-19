"""
Agent 基类 + Collector Agent 测试
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from unittest.mock import MagicMock, patch
import json


# ====================
# Agent 基类测试
# ====================

def test_base_agent_no_llm():
    """测试无 LLM 时 Agent 不可用"""
    from workflow.agents.base_agent import BaseAgent

    agent = BaseAgent()
    assert agent.available is False
    assert agent.tool_names == []
    result = agent.run("test")
    assert "不可用" in result["output"]
    print("  ✅ 无 LLM Agent 降级正确")


def test_base_agent_with_mock_llm():
    """测试带 Mock LLM 的 Agent"""
    from workflow.agents.base_agent import BaseAgent
    from langchain_core.tools import tool

    @tool
    def dummy_tool(query: str) -> str:
        """测试工具"""
        return f"结果: {query}"

    class TestAgent(BaseAgent):
        name = "test"
        system_prompt = "你是测试 Agent"
        def _register_tools(self):
            return [dummy_tool]

    mock_llm = MagicMock()
    agent = TestAgent(llm=mock_llm)
    assert agent.available is True
    assert "dummy_tool" in agent.tool_names
    print("  ✅ Mock LLM Agent 创建正确")


def test_base_agent_run_with_mock():
    """测试 Agent.run 调用图"""
    from workflow.agents.base_agent import BaseAgent
    from langchain_core.tools import tool

    @tool
    def echo(text: str) -> str:
        """回显"""
        return text

    class EchoAgent(BaseAgent):
        name = "echo"
        system_prompt = "你回显用户输入"
        def _register_tools(self):
            return [echo]

    mock_llm = MagicMock()
    agent = EchoAgent(llm=mock_llm)

    # Mock _agent.invoke
    mock_msg = MagicMock()
    mock_msg.content = "回显结果"
    mock_msg.type = "ai"
    agent._agent = MagicMock()
    agent._agent.invoke.return_value = {"messages": [mock_msg]}

    result = agent.run("hello")
    assert result["output"] == "回显结果"
    assert result["tool_calls"] == 0
    agent._agent.invoke.assert_called_once()
    print("  ✅ Agent.run 调用图正确")


def test_base_agent_run_with_context():
    """测试带上下文的 run"""
    from workflow.agents.base_agent import BaseAgent

    agent = BaseAgent()
    agent._agent = MagicMock()

    mock_msg = MagicMock()
    mock_msg.content = "上下文回复"
    mock_msg.type = "ai"
    agent._agent.invoke.return_value = {"messages": [mock_msg]}

    context = [
        {"role": "user", "content": "之前的问题"},
        {"role": "assistant", "content": "之前的回答"},
    ]
    result = agent.run_with_context("新问题", context)
    assert result["output"] == "上下文回复"

    # 验证传入了历史消息
    call_args = agent._agent.invoke.call_args[0][0]
    messages = call_args["messages"]
    assert len(messages) == 3  # 2条历史 + 1条新消息
    print("  ✅ Agent.run_with_context 正确")


def test_base_agent_error_handling():
    """测试 Agent 执行错误处理"""
    from workflow.agents.base_agent import BaseAgent

    agent = BaseAgent()
    agent._agent = MagicMock()
    agent._agent.invoke.side_effect = Exception("模拟错误")

    result = agent.run("test")
    assert "模拟错误" in result["output"]
    assert "error" in result
    print("  ✅ Agent 错误处理正确")


# ====================
# Collector Agent 测试
# ====================

def test_collector_agent_creation():
    """测试 Collector Agent 创建"""
    from workflow.agents.collector_agent import CollectorAgent

    agent = CollectorAgent()
    assert agent.name == "collector"
    assert len(agent.tool_names) == 8
    assert "fetch_pr_list" in agent.tool_names
    assert "check_db_cache" in agent.tool_names
    assert "query_cicd_results" in agent.tool_names
    print("  ✅ CollectorAgent 创建正确")


def test_collector_tools_fetch_pr_list():
    """测试 fetch_pr_list 工具"""
    from workflow.agents.collector_tools import fetch_pr_list

    mock_service = MagicMock()
    mock_service.fetch_prs_for_project.return_value = {
        "prs": [
            {"number": 1, "title": "PR 1"},
            {"number": 2, "title": "PR 2"},
        ],
        "total": 2,
        "error": None,
    }

    with patch("workflow.agents.collector_tools._get_services", return_value=(mock_service, None)):
        result = fetch_pr_list.invoke({"owner": "test", "repo": "project", "max_count": 10})

    parsed = json.loads(result)
    assert parsed["total_prs"] == 2
    assert parsed["pr_numbers"] == [1, 2]
    print("  ✅ fetch_pr_list 工具正确")


def test_collector_tools_fetch_pr_list_error():
    """测试 fetch_pr_list 错误处理"""
    from workflow.agents.collector_tools import fetch_pr_list

    mock_service = MagicMock()
    mock_service.fetch_prs_for_project.return_value = {
        "prs": [], "total": 0, "error": "仓库不存在"
    }

    with patch("workflow.agents.collector_tools._get_services", return_value=(mock_service, None)):
        result = fetch_pr_list.invoke({"owner": "x", "repo": "y"})

    assert "仓库不存在" in result
    print("  ✅ fetch_pr_list 错误处理正确")


def test_collector_tools_fetch_pr_comments():
    """测试 fetch_pr_comments 工具"""
    from workflow.agents.collector_tools import fetch_pr_comments

    mock_service = MagicMock()
    mock_service.fetch_pr_comments.return_value = {
        "comments": [{"id": 1}, {"id": 2}],
        "total": 2,
        "error": None,
    }

    with patch("workflow.agents.collector_tools._get_services", return_value=(mock_service, None)):
        result = fetch_pr_comments.invoke({"owner": "t", "repo": "p", "pr_numbers": "1,2"})

    parsed = json.loads(result)
    assert parsed["total_comments"] == 4  # 2 PRs * 2 comments each
    assert parsed["requested_prs"] == 2
    print("  ✅ fetch_pr_comments 工具正确")


def test_collector_tools_fetch_pr_details():
    """测试 fetch_pr_details 工具"""
    from workflow.agents.collector_tools import fetch_pr_details

    mock_service = MagicMock()
    mock_service.fetch_pr_detail_batch.return_value = {
        "results": [
            {"pr_number": 1, "error": None,
             "detail": {"state": "merged", "additions": 100, "deletions": 50, "changed_files": 10}},
        ],
        "success_count": 1,
        "failed_count": 0,
    }

    with patch("workflow.agents.collector_tools._get_services", return_value=(mock_service, None)):
        result = fetch_pr_details.invoke({"owner": "t", "repo": "p", "pr_numbers": "1"})

    parsed = json.loads(result)
    assert parsed["fetched"] == 1
    assert parsed["details"]["1"]["state"] == "merged"
    print("  ✅ fetch_pr_details 工具正确")


def test_collector_tools_fetch_pr_reviews():
    """测试 fetch_pr_reviews 工具"""
    from workflow.agents.collector_tools import fetch_pr_reviews

    mock_service = MagicMock()
    mock_service.fetch_all_pr_reviews.return_value = {
        "results": [
            {"pr_number": 1, "error": None,
             "reviews": [{"state": "APPROVED"}, {"state": "CHANGES_REQUESTED"}]},
        ],
        "success_count": 1,
        "failed_count": 0,
    }

    with patch("workflow.agents.collector_tools._get_services", return_value=(mock_service, None)):
        result = fetch_pr_reviews.invoke({"owner": "t", "repo": "p", "pr_numbers": "1"})

    parsed = json.loads(result)
    assert parsed["fetched"] == 1
    assert parsed["reviews"]["1"]["total_reviews"] == 2
    print("  ✅ fetch_pr_reviews 工具正确")


def test_collector_tools_check_db_cache():
    """测试 check_db_cache 工具"""
    from workflow.agents.collector_tools import check_db_cache

    mock_db = MagicMock()
    mock_db.get_aggregate_stats.return_value = {
        "pr_comments_count": 100,
        "pr_details_count": 50,
    }
    mock_db.get_pr_data.return_value = {
        "data": {"prs": [{"number": i} for i in range(1, 51)]}
    }

    with patch("workflow.agents.collector_tools._get_services", return_value=(None, mock_db)):
        result = check_db_cache.invoke({"owner": "t", "repo": "p"})

    parsed = json.loads(result)
    assert parsed["cached_pr_count"] == 50
    assert parsed["has_pr_data"] is True
    print("  ✅ check_db_cache 工具正确")


def test_collector_tools_query_cicd_results():
    """测试 query_cicd_results 工具"""
    from workflow.agents.collector_tools import query_cicd_results

    mock_db = MagicMock()
    mock_db.query_cicd_results.return_value = {
        "data": [{"build_status": "success"}],
        "total": 1,
    }

    with patch("workflow.agents.collector_tools._get_services", return_value=(None, mock_db)):
        result = query_cicd_results.invoke({"owner": "t", "repo": "p", "page": 1, "size": 5})

    parsed = json.loads(result)
    assert parsed["total"] == 1
    print("  ✅ query_cicd_results 工具正确")


def test_collector_tools_no_service():
    """测试服务不可用时工具降级"""
    from workflow.agents.collector_tools import fetch_pr_list, check_db_cache

    with patch("workflow.agents.collector_tools._get_services", return_value=(None, None)):
        result = fetch_pr_list.invoke({"owner": "t", "repo": "p"})
        assert "不可用" in result

        result2 = check_db_cache.invoke({"owner": "t", "repo": "p"})
        assert "不可用" in result2

    print("  ✅ 服务不可用时工具降级正确")


# ====================
# 运行测试
# ====================

def main():
    print("=" * 60)
    print("Agent 基类 + Collector Agent 测试")
    print("=" * 60)

    tests = [
        # Agent 基类
        ("Agent 无 LLM 降级", test_base_agent_no_llm),
        ("Agent Mock LLM 创建", test_base_agent_with_mock_llm),
        ("Agent.run 调用", test_base_agent_run_with_mock),
        ("Agent.run_with_context", test_base_agent_run_with_context),
        ("Agent 错误处理", test_base_agent_error_handling),
        # Collector Agent
        ("CollectorAgent 创建", test_collector_agent_creation),
        ("fetch_pr_list", test_collector_tools_fetch_pr_list),
        ("fetch_pr_list 错误", test_collector_tools_fetch_pr_list_error),
        ("fetch_pr_comments", test_collector_tools_fetch_pr_comments),
        ("fetch_pr_details", test_collector_tools_fetch_pr_details),
        ("fetch_pr_reviews", test_collector_tools_fetch_pr_reviews),
        ("check_db_cache", test_collector_tools_check_db_cache),
        ("query_cicd_results", test_collector_tools_query_cicd_results),
        ("工具服务降级", test_collector_tools_no_service),
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
