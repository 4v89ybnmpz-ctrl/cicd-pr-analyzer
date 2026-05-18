"""
Phase 3 测试 — Orchestrator Agent + 多 Agent 图
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from unittest.mock import MagicMock, patch
import json


# ====================
# Orchestrator Agent 测试
# ====================

def test_orchestrator_creation():
    """测试 Orchestrator Agent 创建"""
    from workflow.agents.orchestrator_agent import OrchestratorAgent
    o = OrchestratorAgent()
    assert o.name == "orchestrator"
    assert len(o.tool_names) == 3
    assert "delegate_to_collector" in o.tool_names
    assert "delegate_to_analyst" in o.tool_names
    assert "delegate_to_reporter" in o.tool_names
    print("  ✅ OrchestratorAgent 创建正确")


def test_delegate_to_collector():
    """测试 delegate_to_collector 路由工具"""
    from workflow.agents.orchestrator_agent import delegate_to_collector, _agents

    mock_agent = MagicMock()
    mock_agent.available = True
    mock_agent.run.return_value = {"output": "采集完成: 100 个 PR"}

    _agents["collector"] = mock_agent
    try:
        result = delegate_to_collector.invoke({"task": "采集 rust-lang/rust 的数据"})
        assert "采集完成" in result
    finally:
        _agents.pop("collector", None)
    print("  ✅ delegate_to_collector 正确路由")


def test_delegate_to_analyst():
    """测试 delegate_to_analyst 路由工具"""
    from workflow.agents.orchestrator_agent import delegate_to_analyst, _agents

    mock_agent = MagicMock()
    mock_agent.available = True
    mock_agent.run.return_value = {"output": "分析完成: 成功率 85%"}

    _agents["analyst"] = mock_agent
    try:
        result = delegate_to_analyst.invoke({"task": "分析 CI/CD"})
        assert "成功率" in result
    finally:
        _agents.pop("analyst", None)
    print("  ✅ delegate_to_analyst 正确路由")


def test_delegate_to_reporter():
    """测试 delegate_to_reporter 路由工具"""
    from workflow.agents.orchestrator_agent import delegate_to_reporter, _agents

    mock_agent = MagicMock()
    mock_agent.available = True
    mock_agent.run.return_value = {"output": "# CI/CD 洞察报告\n..."}

    _agents["reporter"] = mock_agent
    try:
        result = delegate_to_reporter.invoke({"task": "生成报告"})
        assert "洞察报告" in result
    finally:
        _agents.pop("reporter", None)
    print("  ✅ delegate_to_reporter 正确路由")


def test_delegate_agent_unavailable():
    """测试 Agent 不可用时的降级"""
    from workflow.agents.orchestrator_agent import delegate_to_collector, _agents

    mock_agent = MagicMock()
    mock_agent.available = False
    _agents["collector"] = mock_agent
    try:
        result = delegate_to_collector.invoke({"task": "采集数据"})
        assert "不可用" in result
    finally:
        _agents.pop("collector", None)
    print("  ✅ Agent 不可用时降级正确")


# ====================
# 多 Agent 图测试
# ====================

def test_multi_agent_graph_build():
    """测试多 Agent 图构建"""
    from workflow.agent_graphs import build_multi_agent_graph
    g = build_multi_agent_graph()
    nodes = list(g.get_graph().nodes.keys())
    assert "orchestrator" in nodes
    print("  ✅ 多 Agent 图构建正确")


def test_sequential_agent_graph_build():
    """测试顺序 Agent 图构建"""
    from workflow.agent_graphs import build_sequential_agent_graph
    g = build_sequential_agent_graph()
    nodes = list(g.get_graph().nodes.keys())
    assert "collector" in nodes
    assert "analyst" in nodes
    assert "reporter" in nodes
    print("  ✅ 顺序 Agent 图构建正确")


def test_multi_agent_graph_invoke():
    """测试多 Agent 图执行（Mock create_react_agent）"""
    from workflow.agent_graphs import build_multi_agent_graph
    from workflow.config import workflow_config

    g = build_multi_agent_graph()

    orig_llm = workflow_config.llm
    mock_llm = MagicMock()
    workflow_config.llm = mock_llm

    try:
        with patch("workflow.agents.base_agent.create_react_agent") as mock_create:
            mock_agent_instance = MagicMock()
            mock_agent_instance.invoke.return_value = {
                "messages": [MagicMock(content="报告: 分析完成", type="ai")]
            }
            mock_create.return_value = mock_agent_instance

            state = {
                "owner": "test", "repo": "project", "max_prs": 10,
                "pr_list": [], "pr_numbers": [], "comments": {},
                "details": {}, "reviews": {}, "cicd_results": [],
                "stats_report": {}, "ai_analysis": "",
                "ai_suggestions": [], "ai_risk_assessment": "",
                "report": {}, "current_step": "init",
                "progress": 0.0, "errors": [],
                "started_at": "2026-05-18T10:00:00", "completed_at": "",
            }
            result = g.invoke(state)
    finally:
        workflow_config.llm = orig_llm

    assert result["progress"] == 100.0
    assert "report" in result
    assert result["current_step"] == "orchestrator_completed"
    print("  ✅ 多 Agent 图执行正确")


def test_sequential_agent_graph_invoke():
    """测试顺序 Agent 图执行（Mock 所有 Agent）"""
    from workflow.agent_graphs import build_sequential_agent_graph

    g = build_sequential_agent_graph()

    def make_mock_agent(name):
        mock = MagicMock()
        mock.available = True
        mock.run.return_value = {"output": f"{name} 完成", "messages": [], "tool_calls": 1}
        return mock

    import workflow.agents.collector_agent as col_mod
    import workflow.agents.analyst_agent as ana_mod
    import workflow.agents.reporter_agent as rep_mod

    orig_c, orig_a, orig_r = col_mod.CollectorAgent, ana_mod.AnalystAgent, rep_mod.ReporterAgent
    col_mod.CollectorAgent = lambda **kw: make_mock_agent("collector")
    ana_mod.AnalystAgent = lambda **kw: make_mock_agent("analyst")
    rep_mod.ReporterAgent = lambda **kw: make_mock_agent("reporter")

    try:
        state = {
            "owner": "test", "repo": "project", "max_prs": 5,
            "pr_list": [], "pr_numbers": [], "comments": {},
            "details": {}, "reviews": {}, "cicd_results": [],
            "stats_report": {}, "ai_analysis": "",
            "ai_suggestions": [], "ai_risk_assessment": "",
            "report": {}, "current_step": "init",
            "progress": 0.0, "errors": [],
            "started_at": "2026-05-18T10:00:00", "completed_at": "",
        }
        result = g.invoke(state)
    finally:
        col_mod.CollectorAgent, ana_mod.AnalystAgent, rep_mod.ReporterAgent = orig_c, orig_a, orig_r

    assert result["progress"] == 100.0
    assert result["current_step"] == "reporter"
    assert "report" in result
    print("  ✅ 顺序 Agent 图执行正确")


# ====================
# Runner 多 Agent 模式测试
# ====================

def test_runner_multi_agent():
    """测试 runner 多 Agent 分析"""
    from workflow.runner import run_multi_agent_analysis
    from workflow.config import workflow_config

    original_ready = workflow_config._initialized
    original_gs = workflow_config.github_service
    workflow_config._initialized = True
    workflow_config.github_service = MagicMock()

    mock_graph = MagicMock()
    mock_graph.invoke.return_value = {
        "progress": 100.0,
        "report": {"owner": "t", "repo": "p"},
        "completed_at": "2026-05-18T10:00:00",
        "errors": [],
    }

    import workflow.agent_graphs as ag_mod
    orig_fn = ag_mod.build_multi_agent_graph
    ag_mod.build_multi_agent_graph = lambda: mock_graph
    try:
        result = run_multi_agent_analysis("t", "p", mode="orchestrator")
    finally:
        ag_mod.build_multi_agent_graph = orig_fn
        workflow_config._initialized = original_ready
        workflow_config.github_service = original_gs

    assert result["status"] == "completed"
    assert result["mode"] == "orchestrator"
    print("  ✅ runner 多 Agent 分析正确")


def test_runner_agent_api():
    """测试 Agent API 路由"""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from workflow.api.routes import register_workflow_routes, AgentRequest

    app = FastAPI()
    router = app.router
    register_workflow_routes(router)
    client = TestClient(app)

    # Agent 任务列表
    resp = client.get("/agent/tasks")
    assert resp.status_code == 200

    # Agent 状态查询不存在的任务
    resp = client.get("/agent/status/nonexistent")
    assert resp.status_code == 404

    print("  ✅ Agent API 路由正确")


# ====================
# 运行测试
# ====================

def main():
    print("=" * 60)
    print("Phase 3 测试 — Orchestrator + 多 Agent 图")
    print("=" * 60)

    sections = [
        ("Orchestrator Agent", [
            ("Orchestrator 创建", test_orchestrator_creation),
            ("delegate_to_collector", test_delegate_to_collector),
            ("delegate_to_analyst", test_delegate_to_analyst),
            ("delegate_to_reporter", test_delegate_to_reporter),
            ("Agent 不可用降级", test_delegate_agent_unavailable),
        ]),
        ("多 Agent 图", [
            ("多 Agent 图构建", test_multi_agent_graph_build),
            ("顺序 Agent 图构建", test_sequential_agent_graph_build),
            ("多 Agent 图执行", test_multi_agent_graph_invoke),
            ("顺序 Agent 图执行", test_sequential_agent_graph_invoke),
        ]),
        ("Runner + API", [
            ("runner 多 Agent", test_runner_multi_agent),
            ("Agent API 路由", test_runner_agent_api),
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
