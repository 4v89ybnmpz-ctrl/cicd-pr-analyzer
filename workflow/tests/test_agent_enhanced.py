"""
Agent 系统增强测试
覆盖: BaseAgent 增强、Planner Agent、Validator Agent、Blackboard、Insights Engine、API
"""
import sys
import os
import json
import time
import threading

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from unittest.mock import MagicMock, patch


# ====================
# 1. Insights Engine 测试
# ====================

def test_grade_success_rate():
    from workflow.agents.insights_engine import grade_success_rate
    assert grade_success_rate(96) == ("A", "构建稳定性优秀")
    assert grade_success_rate(88) == ("B", "建议关注偶发失败，排查 flaky test")
    assert grade_success_rate(75) == ("C", "失败率较高，建议加强 CI 代码审查")
    assert grade_success_rate(55) == ("D", "构建成功率较低，需要重点改善")
    assert grade_success_rate(30) == ("F", "构建严重不稳定，建议暂停合并，集中修复")
    print("  ✅ grade_success_rate 评级正确")


def test_grade_duration():
    from workflow.agents.insights_engine import grade_duration
    assert grade_duration(200) == ("A", "构建速度优秀")
    assert grade_duration(600) == ("B", "构建速度良好")
    assert grade_duration(1200) == ("C", "构建偏慢，建议优化耗时较长的 job")
    assert grade_duration(2400) == ("D", "构建很慢，建议并行化或拆分 pipeline")
    assert grade_duration(4000) == ("F", "构建极慢，需要紧急优化")
    print("  ✅ grade_duration 评级正确")


def test_grade_coverage():
    from workflow.agents.insights_engine import grade_coverage
    assert grade_coverage(92) == ("A", "覆盖率优秀")
    assert grade_coverage(82) == ("B", "覆盖率良好，可进一步提升")
    assert grade_coverage(65) == ("C", "覆盖率一般，建议补充核心模块测试")
    assert grade_coverage(45) == ("D", "覆盖率较低，需要加强测试")
    assert grade_coverage(20) == ("F", "覆盖率极低，测试严重不足")
    print("  ✅ grade_coverage 评级正确")


def test_format_duration():
    from workflow.agents.insights_engine import format_duration
    assert format_duration(30) == "30s"
    assert format_duration(120) == "2.0m"
    assert format_duration(7200) == "2.0h"
    print("  ✅ format_duration 格式化正确")


def test_build_insights():
    from workflow.agents.insights_engine import build_insights
    result = build_insights(
        {"total": 100, "success_rate": 90.5, "avg_duration_seconds": 500, "avg_coverage": 75.0},
        {"top_failed_jobs": [{"name": "test-x86", "count": 8}]},
    )
    assert len(result) == 4  # 成功率 + 耗时 + 覆盖率 + 失败Job
    assert result[0]["grade"] == "B"
    assert result[1]["grade"] == "B"
    assert result[2]["grade"] == "C"
    assert result[3]["grade"] == "D"
    print("  ✅ build_insights 洞察生成正确")


def test_build_insights_empty():
    from workflow.agents.insights_engine import build_insights
    assert build_insights({"total": 0}, {}) == []
    print("  ✅ build_insights 空数据处理正确")


def test_compute_overall_grade():
    from workflow.agents.insights_engine import compute_overall_grade
    insights_a = [{"grade": "A"}, {"grade": "A"}]
    assert compute_overall_grade(insights_a) == "A"
    insights_mix = [{"grade": "A"}, {"grade": "C"}, {"grade": "B"}]
    grade = compute_overall_grade(insights_mix)
    assert grade in ("A", "B", "C")
    assert compute_overall_grade([]) == "N/A"
    print("  ✅ compute_overall_grade 综合评级正确")


# ====================
# 2. SharedBlackboard 测试
# ====================

def test_blackboard_write_read():
    from workflow.agents.blackboard import SharedBlackboard, DataType
    bb = SharedBlackboard()
    bb.write("test/key", DataType.CUSTOM, {"value": 42}, producer="test_agent")
    result = bb.read("test/key")
    assert result == {"value": 42}
    print("  ✅ SharedBlackboard 写入/读取正确")


def test_blackboard_version():
    from workflow.agents.blackboard import SharedBlackboard, DataType
    bb = SharedBlackboard()
    bb.write("key1", DataType.CUSTOM, "v1", producer="a")
    bb.write("key1", DataType.CUSTOM, "v2", producer="a")
    entry = bb.read_entry("key1")
    assert entry.version == 2
    assert entry.value == "v2"
    print("  ✅ SharedBlackboard 版本递增正确")


def test_blackboard_read_by_type():
    from workflow.agents.blackboard import SharedBlackboard, DataType
    bb = SharedBlackboard()
    bb.write("c1", DataType.COLLECTION_RESULT, "data1", producer="c")
    bb.write("c2", DataType.COLLECTION_RESULT, "data2", producer="c")
    bb.write("a1", DataType.ANALYSIS_RESULT, "data3", producer="a")
    results = bb.read_by_type(DataType.COLLECTION_RESULT)
    assert len(results) == 2
    print("  ✅ SharedBlackboard 按类型读取正确")


def test_blackboard_read_by_prefix():
    from workflow.agents.blackboard import SharedBlackboard, DataType
    bb = SharedBlackboard()
    bb.write("profile/rust/rust", DataType.METRICS, "p1", producer="p")
    bb.write("profile/python/cpython", DataType.METRICS, "p2", producer="p")
    bb.write("collection/rust/rust", DataType.COLLECTION_RESULT, "c1", producer="c")
    results = bb.read_by_prefix("profile/")
    assert len(results) == 2
    print("  ✅ SharedBlackboard 按前缀读取正确")


def test_blackboard_delete():
    from workflow.agents.blackboard import SharedBlackboard, DataType
    bb = SharedBlackboard()
    bb.write("del/me", DataType.CUSTOM, "data", producer="t")
    assert bb.delete("del/me") is True
    assert bb.read("del/me") is None
    assert bb.delete("nonexist") is False
    print("  ✅ SharedBlackboard 删除正确")


def test_blackboard_subscribe():
    from workflow.agents.blackboard import SharedBlackboard, DataType
    bb = SharedBlackboard()
    events = []
    bb.subscribe(DataType.COLLECTION_RESULT, lambda k, e: events.append((k, e.value)))
    bb.write("col/1", DataType.COLLECTION_RESULT, "data", producer="c")
    bb.write("ana/1", DataType.ANALYSIS_RESULT, "other", producer="a")
    assert len(events) == 1
    assert events[0] == ("col/1", "data")
    print("  ✅ SharedBlackboard 订阅通知正确")


def test_blackboard_summary():
    from workflow.agents.blackboard import SharedBlackboard, DataType
    bb = SharedBlackboard()
    bb.write("k1", DataType.CUSTOM, "v1", producer="t")
    bb.write("k2", DataType.CUSTOM, "v2", producer="t")
    s = bb.summary()
    assert s["total_entries"] == 2
    assert s["total_writes"] == 2
    print("  ✅ SharedBlackboard 摘要正确")


def test_blackboard_clear():
    from workflow.agents.blackboard import SharedBlackboard, DataType
    bb = SharedBlackboard()
    bb.write("k", DataType.CUSTOM, "v", producer="t")
    bb.clear()
    assert bb.read("k") is None
    print("  ✅ SharedBlackboard 清空正确")


# ====================
# 3. BaseAgent 增强 测试
# ====================

def test_base_agent_callbacks():
    from workflow.agents.base_agent import BaseAgent, AgentEventType
    events = []

    class TestAgent(BaseAgent):
        name = "test"
        system_prompt = "test"
        def _register_tools(self):
            return []

    agent = TestAgent()
    agent.on_event(lambda e: events.append(e.event_type))

    # 模拟 run — agent 不可用
    agent.run("test")
    assert AgentEventType.FAILED in events
    print("  ✅ BaseAgent 回调事件触发正确")


def test_base_agent_execution_stats():
    from workflow.agents.base_agent import BaseAgent

    class TestAgent(BaseAgent):
        name = "test"
        system_prompt = "test"
        def _register_tools(self):
            return []

    agent = TestAgent()
    agent._agent = MagicMock()
    mock_msg = MagicMock()
    mock_msg.content = "结果"
    mock_msg.type = "ai"
    mock_msg.usage_metadata = {"input_tokens": 100, "output_tokens": 50}
    agent._agent.invoke.return_value = {"messages": [mock_msg]}

    result = agent.run("test")
    # stats 是 ExecutionStats dataclass，转为 dict 检查
    stats = result["stats"]
    if hasattr(stats, "success"):
        assert stats.success is True
        assert stats.input_tokens == 100
        assert stats.output_tokens == 50
        assert stats.duration_seconds > 0
    else:
        assert stats["success"] is True
    print("  ✅ BaseAgent 执行统计正确")


def test_base_agent_retry():
    from workflow.agents.base_agent import BaseAgent

    class TestAgent(BaseAgent):
        name = "test_retry"
        system_prompt = "test"
        max_retries = 2
        retry_delay = 0.01
        def _register_tools(self):
            return []

    agent = TestAgent()
    agent._agent = MagicMock()
    agent._agent.invoke.side_effect = [Exception("fail1"), Exception("fail2"), Exception("fail3")]

    result = agent.run("test")
    assert "fail3" in result["output"]
    assert agent._agent.invoke.call_count == 3  # 1 + 2 retries
    print("  ✅ BaseAgent 重试机制正确")


def test_base_agent_retry_success_on_second():
    from workflow.agents.base_agent import BaseAgent

    class TestAgent(BaseAgent):
        name = "test_retry2"
        system_prompt = "test"
        max_retries = 2
        retry_delay = 0.01
        def _register_tools(self):
            return []

    agent = TestAgent()
    agent._agent = MagicMock()
    mock_msg = MagicMock()
    mock_msg.content = "成功"
    mock_msg.type = "ai"
    mock_msg.usage_metadata = {}
    agent._agent.invoke.side_effect = [
        Exception("fail"),
        {"messages": [mock_msg]},
    ]

    result = agent.run("test")
    assert result["output"] == "成功"
    assert agent._agent.invoke.call_count == 2
    print("  ✅ BaseAgent 重试后成功正确")


def test_base_agent_performance_summary():
    from workflow.agents.base_agent import BaseAgent

    class TestAgent(BaseAgent):
        name = "perf_test"
        system_prompt = "test"
        def _register_tools(self):
            return []

    agent = TestAgent()
    summary = agent.get_performance_summary()
    assert summary["total_runs"] == 0

    # 模拟一次执行
    agent._agent = MagicMock()
    mock_msg = MagicMock()
    mock_msg.content = "ok"
    mock_msg.type = "ai"
    mock_msg.usage_metadata = {}
    agent._agent.invoke.return_value = {"messages": [mock_msg]}

    agent.run("test")
    summary = agent.get_performance_summary()
    assert summary["total_runs"] == 1
    assert summary["successful_runs"] == 1
    print("  ✅ BaseAgent 性能摘要正确")


# ====================
# 4. Planner Agent 测试
# ====================

def test_planner_agent_creation():
    from workflow.agents.planner_agent import PlannerAgent
    agent = PlannerAgent()
    assert agent.name == "planner"
    assert "analyze_project_profile" in agent.tool_names
    assert "create_execution_plan" in agent.tool_names
    print("  ✅ PlannerAgent 创建正确")


def test_analyze_project_profile():
    from workflow.agents.planner_agent import analyze_project_profile

    mock_bb = MagicMock()
    mock_bb.read.return_value = None

    with patch("workflow.agents.blackboard.blackboard", mock_bb):
        with patch("workflow.config.workflow_config") as mock_config:
            mock_config.github_service = MagicMock()
            mock_config.db = MagicMock()

            mock_config.db.get_aggregate_stats.return_value = {
                "pr_data_count": 10, "pr_comments_count": 200,
            }
            mock_config.db.query_cicd_results.return_value = {"total": 0}
            mock_config.db.get_pr_data.return_value = {
                "data": {"prs": [{"number": i} for i in range(30)]}
            }
            mock_config.github_service.fetch_prs_for_project.return_value = {
                "total": 30, "prs": [], "error": None,
            }

            result = analyze_project_profile.invoke({"owner": "test", "repo": "project"})

    parsed = json.loads(result)
    assert parsed["owner"] == "test"
    assert parsed["pr_count"] == 30
    assert parsed["estimated_size"] == "small"
    assert "skip_collection" in parsed["recommendations"]
    print("  ✅ analyze_project_profile 工具正确")


def test_create_execution_plan_full():
    from workflow.agents.planner_agent import create_execution_plan
    profile = json.dumps({
        "owner": "rust-lang", "repo": "rust",
        "estimated_size": "large",
        "recommendations": ["full_collection", "sampling_strategy", "parallel_collection"],
    })
    result = create_execution_plan.invoke({"profile_json": profile, "analysis_goals": "full"})
    parsed = json.loads(result)
    assert parsed["owner"] == "rust-lang"
    assert len(parsed["stages"]) == 4  # collection + analysis + validation + reporting
    assert parsed["estimated_steps"] > 0
    print("  ✅ create_execution_plan 全量计划正确")


def test_create_execution_plan_cached():
    from workflow.agents.planner_agent import create_execution_plan
    profile = json.dumps({
        "owner": "test", "repo": "cached",
        "estimated_size": "small",
        "recommendations": ["skip_collection", "needs_cicd_extraction"],
    })
    result = create_execution_plan.invoke({"profile_json": profile, "analysis_goals": "full"})
    parsed = json.loads(result)
    # 采集阶段应被跳过
    collection_stage = parsed["stages"][0]
    assert collection_stage.get("skipped") is True
    print("  ✅ create_execution_plan 缓存跳过正确")


def test_create_execution_plan_report_only():
    from workflow.agents.planner_agent import create_execution_plan
    profile = json.dumps({
        "owner": "t", "repo": "p",
        "estimated_size": "small",
        "recommendations": ["skip_collection"],
    })
    result = create_execution_plan.invoke({"profile_json": profile, "analysis_goals": "report_only"})
    parsed = json.loads(result)
    # 应跳过分析阶段
    stage_names = [s["stage"] for s in parsed["stages"]]
    assert "analysis" not in stage_names
    print("  ✅ create_execution_plan report_only 模式正确")


# ====================
# 5. Validator Agent 测试
# ====================

def test_validator_agent_creation():
    from workflow.agents.validator_agent import ValidatorAgent
    agent = ValidatorAgent()
    assert agent.name == "validator"
    assert "validate_collected_data" in agent.tool_names
    assert "validate_analysis_quality" in agent.tool_names
    print("  ✅ ValidatorAgent 创建正确")


def test_validate_collected_data():
    from workflow.agents.validator_agent import validate_collected_data

    with patch("workflow.config.workflow_config") as mock_config:
        mock_db = MagicMock()
        mock_config.db = mock_db

        mock_db.get_pr_data.return_value = {"data": {"prs": [{"number": 1}]}}
        mock_db.get_aggregate_stats.return_value = {"pr_comments_count": 50}
        mock_db.query_cicd_results.return_value = {"total": 10}
        mock_db.get_cicd_summary_from_db.return_value = {
            "total": 10, "success_rate": 85.0,
        }
        mock_db.get_cicd_trends_from_db.return_value = [{"date": "2026-05-18"}]

        result = validate_collected_data.invoke({"owner": "t", "repo": "p"})

    parsed = json.loads(result)
    assert parsed["valid"] is True
    assert parsed["completeness_score"] >= 60
    assert len(parsed["checks"]) == 5
    print("  ✅ validate_collected_data 验证正确")


def test_validate_collected_data_no_db():
    from workflow.agents.validator_agent import validate_collected_data

    with patch("workflow.config.workflow_config") as mock_config:
        mock_config.db = None
        result = validate_collected_data.invoke({"owner": "t", "repo": "p"})

    parsed = json.loads(result)
    assert parsed["valid"] is False
    print("  ✅ validate_collected_data 无数据库降级正确")


# ====================
# 6. Orchestrator 增强 测试
# ====================

def test_orchestrator_has_new_tools():
    from workflow.agents.orchestrator_agent import OrchestratorAgent
    agent = OrchestratorAgent()
    tools = agent.tool_names
    assert "delegate_to_planner" in tools
    assert "delegate_to_validator" in tools
    assert "get_blackboard_summary" in tools
    assert "check_agent_status" in tools
    assert len(tools) == 7
    print("  ✅ OrchestratorAgent 新工具注册正确")


def test_delegate_to_planner():
    from workflow.agents.orchestrator_agent import delegate_to_planner
    from workflow.agents.registry import agent_registry
    agent_registry.destroy("planner")

    with patch("workflow.agents.orchestrator_agent._get_agent") as mock_get:
        mock_planner = MagicMock()
        mock_planner.available = True
        mock_planner.run.return_value = {"output": "计划: 全量采集 → 分析 → 报告"}
        mock_get.return_value = mock_planner

        result = delegate_to_planner.invoke({"task": "规划分析"})
    assert "计划" in result
    print("  ✅ delegate_to_planner 工具正确")


def test_delegate_to_validator():
    from workflow.agents.orchestrator_agent import delegate_to_validator
    from workflow.agents.registry import agent_registry
    agent_registry.destroy("validator")

    with patch("workflow.agents.orchestrator_agent._get_agent") as mock_get:
        mock_validator = MagicMock()
        mock_validator.available = True
        mock_validator.run.return_value = {"output": "数据完整度 85%"}
        mock_get.return_value = mock_validator

        result = delegate_to_validator.invoke({"task": "验证数据"})
    assert "85%" in result
    print("  ✅ delegate_to_validator 工具正确")


def test_get_blackboard_summary():
    from workflow.agents.orchestrator_agent import get_blackboard_summary
    from workflow.agents.blackboard import blackboard

    blackboard.clear()
    result = get_blackboard_summary.invoke({})
    parsed = json.loads(result)
    assert "total_entries" in parsed
    print("  ✅ get_blackboard_summary 工具正确")


def test_check_agent_status():
    from workflow.agents.orchestrator_agent import check_agent_status
    from workflow.agents.registry import agent_registry
    # 清除缓存确保测试隔离
    saved = dict(agent_registry._instances)
    agent_registry._instances.clear()

    result = check_agent_status.invoke({})
    parsed = json.loads(result)
    assert "planner" in parsed
    assert "collector" in parsed
    assert "analyst" in parsed
    assert "validator" in parsed
    assert "reporter" in parsed

    agent_registry._instances.update(saved)
    print("  ✅ check_agent_status 工具正确")


# ====================
# 7. API 路由测试
# ====================

def test_session_create_and_chat():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from workflow.api.routes import register_workflow_routes
    from workflow.config import workflow_config
    from workflow.agents.registry import agent_registry
    from workflow.runner import _sessions

    app = FastAPI()
    register_workflow_routes(app.router)
    client = TestClient(app)

    orig_llm = workflow_config.llm
    workflow_config.llm = MagicMock()

    try:
        # 创建会话
        resp = client.post("/agent/sessions")
        assert resp.status_code == 200
        session_id = resp.json()["session_id"]

        # 手动为该会话创建一个 mock orchestrator
        mock_agent = MagicMock()
        mock_msg = MagicMock()
        mock_msg.content = "分析完成"
        mock_msg.type = "ai"
        mock_msg.usage_metadata = {}
        mock_agent.invoke.return_value = {"messages": [mock_msg]}

        from workflow.agents.orchestrator_agent import OrchestratorAgent
        orch = OrchestratorAgent.__new__(OrchestratorAgent)
        orch.llm = MagicMock()
        orch._tools = orch._register_tools()
        orch._agent = mock_agent
        orch._callbacks = []
        orch._execution_history = []
        orch._total_runs = 0
        orch._total_errors = 0
        orch.max_retries = 0
        orch.retry_delay = 0
        agent_registry._instances[f"orchestrator_{session_id}"] = orch

        # 在会话中对话
        resp = client.post(f"/agent/sessions/{session_id}/chat",
                         json={"session_id": session_id, "message": "分析项目"})
        assert resp.status_code == 200
        assert "分析完成" in resp.json()["response"]

        # 列出会话
        resp = client.get("/agent/sessions")
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

        # 删除会话
        resp = client.delete(f"/agent/sessions/{session_id}")
        assert resp.status_code == 200
    finally:
        workflow_config.llm = orig_llm
        _sessions.clear()
    agent_registry.clear()
    print("  ✅ 会话管理 API 正确")


def test_agents_status_endpoint():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from workflow.api.routes import register_workflow_routes

    app = FastAPI()
    register_workflow_routes(app.router)
    client = TestClient(app)

    resp = client.get("/agent/agents/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "agents" in data
    print("  ✅ /agent/agents/status 端点正确")


def test_blackboard_endpoint():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from workflow.api.routes import register_workflow_routes
    from workflow.agents.blackboard import blackboard

    blackboard.clear()
    app = FastAPI()
    register_workflow_routes(app.router)
    client = TestClient(app)

    resp = client.get("/agent/blackboard")
    assert resp.status_code == 200
    data = resp.json()
    assert "total_entries" in data
    print("  ✅ /agent/blackboard 端点正确")


def test_batch_endpoint():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from workflow.api.routes import register_workflow_routes
    from workflow.config import workflow_config

    app = FastAPI()
    register_workflow_routes(app.router)
    client = TestClient(app)

    if not workflow_config.ready:
        resp = client.post("/agent/batch", json={
            "projects": [{"owner": "t", "repo": "p"}],
            "mode": "sequential",
        })
        assert resp.status_code == 503
    print("  ✅ /agent/batch 端点注册正确")


# ====================
# 8. Reporter Tools 修复测试
# ====================

def test_generate_stats_report_with_local_engine():
    """测试修复后的 generate_stats_report 使用本地洞察引擎"""
    from workflow.agents.reporter_tools import generate_stats_report

    mock_db = MagicMock()
    mock_db.get_cicd_summary_from_db.return_value = {
        "total": 50, "success_rate": 92.0, "avg_duration_seconds": 600,
    }
    mock_db.get_cicd_trends_from_db.return_value = []
    mock_db.get_cicd_failure_analysis_from_db.return_value = {"top_failed_jobs": []}

    with patch("workflow.agents.reporter_tools._get_db", return_value=mock_db):
        result = generate_stats_report.invoke({"owner": "t", "repo": "p"})

    parsed = json.loads(result)
    assert parsed["owner"] == "t"
    assert parsed["overall_grade"] in ("A", "B", "C", "D", "F", "N/A")
    assert len(parsed["insights"]) > 0
    print("  ✅ generate_stats_report 本地洞察引擎正确")


# ====================
# 运行测试
# ====================

def main():
    print("=" * 60)
    print("Agent 系统增强测试")
    print("=" * 60)

    sections = [
        ("洞察引擎", [
            ("成功率评级", test_grade_success_rate),
            ("耗时评级", test_grade_duration),
            ("覆盖率评级", test_grade_coverage),
            ("耗时格式化", test_format_duration),
            ("洞察生成", test_build_insights),
            ("空数据洞察", test_build_insights_empty),
            ("综合评级", test_compute_overall_grade),
        ]),
        ("共享黑板", [
            ("写入/读取", test_blackboard_write_read),
            ("版本递增", test_blackboard_version),
            ("按类型读取", test_blackboard_read_by_type),
            ("按前缀读取", test_blackboard_read_by_prefix),
            ("删除", test_blackboard_delete),
            ("订阅通知", test_blackboard_subscribe),
            ("摘要", test_blackboard_summary),
            ("清空", test_blackboard_clear),
        ]),
        ("BaseAgent 增强", [
            ("回调事件", test_base_agent_callbacks),
            ("执行统计", test_base_agent_execution_stats),
            ("重试机制", test_base_agent_retry),
            ("重试成功", test_base_agent_retry_success_on_second),
            ("性能摘要", test_base_agent_performance_summary),
        ]),
        ("Planner Agent", [
            ("创建", test_planner_agent_creation),
            ("项目画像", test_analyze_project_profile),
            ("全量计划", test_create_execution_plan_full),
            ("缓存跳过", test_create_execution_plan_cached),
            ("仅报告模式", test_create_execution_plan_report_only),
        ]),
        ("Validator Agent", [
            ("创建", test_validator_agent_creation),
            ("数据验证", test_validate_collected_data),
            ("无数据库降级", test_validate_collected_data_no_db),
        ]),
        ("Orchestrator 增强", [
            ("新工具注册", test_orchestrator_has_new_tools),
            ("delegate_to_planner", test_delegate_to_planner),
            ("delegate_to_validator", test_delegate_to_validator),
            ("黑板摘要", test_get_blackboard_summary),
            ("Agent 状态", test_check_agent_status),
        ]),
        ("API 路由", [
            ("会话管理", test_session_create_and_chat),
            ("Agent 状态端点", test_agents_status_endpoint),
            ("黑板端点", test_blackboard_endpoint),
            ("批量端点", test_batch_endpoint),
        ]),
        ("Reporter 修复", [
            ("本地洞察引擎", test_generate_stats_report_with_local_engine),
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
