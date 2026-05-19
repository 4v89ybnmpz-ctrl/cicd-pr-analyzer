"""
Phase 6 增强测试
覆盖: AgentRegistry, ArtifactStore, TraceManager, CostController,
       Collector 增量/并发工具, Reporter HTML 工具, 新 API 端点
"""
import sys
import os
import json
import time
import threading

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from unittest.mock import MagicMock, patch


# ====================
# 1. AgentRegistry 测试
# ====================

def test_registry_register():
    from workflow.agents.registry import AgentRegistry
    reg = AgentRegistry()
    reg.register("test_agent", "workflow.agents.collector_agent.CollectorAgent", ["test"])
    desc = reg._registry.get("test_agent")
    assert desc is not None
    assert desc.agent_class == "workflow.agents.collector_agent.CollectorAgent"
    assert "test" in desc.tags
    print("  ✅ AgentRegistry 注册正确")


def test_registry_register_defaults():
    from workflow.agents.registry import AgentRegistry
    reg = AgentRegistry()
    reg.set_llm(MagicMock())
    reg.register_defaults()
    names = [d["name"] for d in reg.list_registered()]
    assert "planner" in names
    assert "collector" in names
    assert "analyst" in names
    assert "validator" in names
    assert "reporter" in names
    print("  ✅ AgentRegistry register_defaults 正确")


def test_registry_get_creates_instance():
    from workflow.agents.registry import AgentRegistry
    reg = AgentRegistry()
    reg.set_llm(None)  # 无 LLM，Agent 不可用但能实例化
    reg.register("col", "workflow.agents.collector_agent.CollectorAgent")
    instance = reg.get("col")
    assert instance is not None
    assert instance.name == "collector"
    print("  ✅ AgentRegistry get 延迟实例化正确")


def test_registry_get_nonexistent():
    from workflow.agents.registry import AgentRegistry
    reg = AgentRegistry()
    assert reg.get("nonexistent") is None
    print("  ✅ AgentRegistry get 不存在返回 None")


def test_registry_destroy():
    from workflow.agents.registry import AgentRegistry
    reg = AgentRegistry()
    reg.set_llm(None)
    reg.register("col", "workflow.agents.collector_agent.CollectorAgent")
    reg.get("col")
    assert reg.destroy("col") is True
    from workflow.agents.registry import AgentStatus
    assert reg._registry["col"].status == AgentStatus.DESTROYED
    print("  ✅ AgentRegistry destroy 正确")


def test_registry_hot_replace():
    from workflow.agents.registry import AgentRegistry
    reg = AgentRegistry()
    reg.set_llm(None)
    reg.register("col", "workflow.agents.collector_agent.CollectorAgent")
    inst1 = reg.get("col")
    inst2 = reg.hot_replace("col")
    assert inst2 is not None
    assert inst2 is not inst1
    print("  ✅ AgentRegistry hot_replace 正确")


def test_registry_find_by_tag():
    from workflow.agents.registry import AgentRegistry
    reg = AgentRegistry()
    reg.register("a", "x", ["data", "github"])
    reg.register("b", "y", ["analysis"])
    reg.register("c", "z", ["data"])
    assert sorted(reg.find_by_tag("data")) == ["a", "c"]
    assert reg.find_by_tag("github") == ["a"]
    print("  ✅ AgentRegistry find_by_tag 正确")


def test_registry_get_status():
    from workflow.agents.registry import AgentRegistry
    reg = AgentRegistry()
    reg.register("col", "workflow.agents.collector_agent.CollectorAgent")
    status = reg.get_status("col")
    assert status["name"] == "col"
    assert status["status"] == "created"
    reg.get("col")
    status = reg.get_status("col")
    assert status["total_invocations"] == 0
    print("  ✅ AgentRegistry get_status 正确")


def test_registry_record_invocation():
    from workflow.agents.registry import AgentRegistry
    reg = AgentRegistry()
    reg.register("col", "workflow.agents.collector_agent.CollectorAgent")
    reg.record_invocation("col", success=True)
    reg.record_invocation("col", success=False)
    status = reg.get_status("col")
    assert status["total_invocations"] == 2
    assert status["total_errors"] == 1
    print("  ✅ AgentRegistry record_invocation 正确")


# ====================
# 2. ArtifactStore 测试
# ====================

def test_artifact_store_and_get():
    from workflow.agents.artifact_store import ArtifactStore, ArtifactType
    store = ArtifactStore(default_ttl=3600)
    store.store(ArtifactType.PLAN, "owner", "repo", {"plan": "full"}, producer="planner")
    content = store.get_content(ArtifactType.PLAN, "owner", "repo")
    assert content == {"plan": "full"}
    print("  ✅ ArtifactStore store/get 正确")


def test_artifact_versioning():
    from workflow.agents.artifact_store import ArtifactStore, ArtifactType
    store = ArtifactStore(default_ttl=3600)
    store.store(ArtifactType.STATS_REPORT, "o", "r", {"v": 1})
    store.store(ArtifactType.STATS_REPORT, "o", "r", {"v": 2})
    artifact = store.get(ArtifactType.STATS_REPORT, "o", "r")
    assert artifact.version == 2
    assert artifact.content == {"v": 2}
    print("  ✅ ArtifactStore 版本递增正确")


def test_artifact_project_artifacts():
    from workflow.agents.artifact_store import ArtifactStore, ArtifactType
    store = ArtifactStore(default_ttl=3600)
    store.store(ArtifactType.PLAN, "o", "r", {"plan": True})
    store.store(ArtifactType.ANALYSIS_RESULT, "o", "r", {"analysis": True})
    result = store.get_project_artifacts("o", "r")
    assert "plan" in result
    assert "analysis_result" in result
    print("  ✅ ArtifactStore get_project_artifacts 正确")


def test_artifact_is_changed():
    from workflow.agents.artifact_store import ArtifactStore, ArtifactType
    store = ArtifactStore(default_ttl=3600)
    assert store.is_changed(ArtifactType.PLAN, "o", "r", {"a": 1}) is True
    store.store(ArtifactType.PLAN, "o", "r", {"a": 1})
    assert store.is_changed(ArtifactType.PLAN, "o", "r", {"a": 1}) is False
    assert store.is_changed(ArtifactType.PLAN, "o", "r", {"a": 2}) is True
    print("  ✅ ArtifactStore is_changed 正确")


def test_artifact_delete():
    from workflow.agents.artifact_store import ArtifactStore, ArtifactType
    store = ArtifactStore(default_ttl=3600)
    store.store(ArtifactType.PLAN, "o", "r", {"data": True})
    assert store.delete(ArtifactType.PLAN, "o", "r") is True
    assert store.get_content(ArtifactType.PLAN, "o", "r") is None
    print("  ✅ ArtifactStore delete 正确")


def test_artifact_snapshot():
    from workflow.agents.artifact_store import ArtifactStore, ArtifactType
    store = ArtifactStore(default_ttl=3600)
    store.store(ArtifactType.PLAN, "o", "r", {"plan": True})
    snapshot = json.loads(store.snapshot())
    assert snapshot["total_artifacts"] == 1
    print("  ✅ ArtifactStore snapshot 正确")


def test_artifact_summary():
    from workflow.agents.artifact_store import ArtifactStore, ArtifactType
    store = ArtifactStore(default_ttl=3600)
    store.store(ArtifactType.PLAN, "o", "r", {})
    store.store(ArtifactType.ANALYSIS_RESULT, "o", "r2", {})
    s = store.summary()
    assert s["total_artifacts"] == 2
    assert s["total_projects"] == 2
    print("  ✅ ArtifactStore summary 正确")


# ====================
# 3. TraceManager 测试
# ====================

def test_trace_start_finish():
    from workflow.agents.tracer import TraceManager
    tm = TraceManager()
    trace_id = tm.start_trace("owner", "repo", "sequential")
    assert trace_id.startswith("trace_")
    tm.finish_trace(trace_id, status="ok")
    trace = tm.get_trace(trace_id)
    assert trace["status"] == "ok"
    assert trace["total_duration_ms"] > 0
    print("  ✅ TraceManager start/finish 正确")


def test_trace_spans():
    from workflow.agents.tracer import TraceManager
    tm = TraceManager()
    trace_id = tm.start_trace("o", "r")
    span_id = tm.start_span(trace_id, "collector", "run")
    tm.finish_span(trace_id, span_id, input_tokens=100, output_tokens=50, tool_calls=3)
    tm.finish_trace(trace_id)

    trace = tm.get_trace(trace_id)
    assert len(trace["spans"]) == 1
    assert trace["spans"][0]["agent"] == "collector"
    assert trace["spans"][0]["tokens"] == 150
    assert trace["spans"][0]["tool_calls"] == 3
    assert trace["total_tokens"] == 150
    print("  ✅ TraceManager spans 正确")


def test_trace_list():
    from workflow.agents.tracer import TraceManager
    tm = TraceManager()
    t1 = tm.start_trace("o1", "r1")
    tm.finish_trace(t1)
    t2 = tm.start_trace("o2", "r2")
    tm.finish_trace(t2)

    traces = tm.list_traces()
    assert len(traces) == 2
    print("  ✅ TraceManager list_traces 正确")


def test_trace_project_history():
    from workflow.agents.tracer import TraceManager
    tm = TraceManager()
    t1 = tm.start_trace("o", "r")
    tm.finish_trace(t1)
    t2 = tm.start_trace("o", "r")
    tm.finish_trace(t2)

    history = tm.get_project_traces("o", "r")
    assert len(history) == 2
    print("  ✅ TraceManager get_project_traces 正确")


def test_trace_export():
    from workflow.agents.tracer import TraceManager
    tm = TraceManager()
    trace_id = tm.start_trace("o", "r")
    tm.finish_trace(trace_id)
    exported = tm.export_trace(trace_id)
    assert exported is not None
    data = json.loads(exported)
    assert data["trace_id"] == trace_id
    print("  ✅ TraceManager export 正确")


def test_trace_summary():
    from workflow.agents.tracer import TraceManager
    tm = TraceManager()
    t1 = tm.start_trace("o", "r")
    tm.finish_trace(t1, status="ok")
    s = tm.summary()
    assert s["total_traces"] == 1
    assert s["completed"] == 1
    print("  ✅ TraceManager summary 正确")


def test_trace_max_traces():
    from workflow.agents.tracer import TraceManager
    tm = TraceManager(max_traces=3)
    for i in range(5):
        tid = tm.start_trace("o", f"r{i}")
        tm.finish_trace(tid)
    assert len(tm._traces) <= 3
    print("  ✅ TraceManager max_traces 清理正确")


# ====================
# 4. CostController 测试
# ====================

def test_cost_record_usage():
    from workflow.agents.cost_controller import CostController
    cc = CostController(total_budget=10000)
    ok = cc.record_usage("analyst", 500, 200)
    assert ok is True
    assert cc.budget.used_tokens == 700
    print("  ✅ CostController record_usage 正确")


def test_cost_budget_exceeded():
    from workflow.agents.cost_controller import CostController
    cc = CostController(total_budget=100)
    cc.record_usage("analyst", 50, 30)
    ok = cc.record_usage("reporter", 10, 20)
    assert ok is False
    assert cc.budget.is_exceeded is True
    print("  ✅ CostController 预算超限正确")


def test_cost_recommended_tier():
    from workflow.agents.cost_controller import CostController
    cc = CostController(total_budget=10000)
    assert cc.get_recommended_tier("analyst") == "premium"
    assert cc.get_recommended_tier("collector") == "economy"

    # 超过 80% 时降级
    cc.record_usage("analyst", 8000, 500)
    assert cc.get_recommended_tier("analyst") == "standard"
    print("  ✅ CostController LLM 分级降级正确")


def test_cost_tier_override():
    from workflow.agents.cost_controller import CostController
    cc = CostController()
    cc.set_tier_override("economy")
    assert cc.get_recommended_tier("analyst") == "economy"
    cc.clear_tier_override()
    assert cc.get_recommended_tier("analyst") == "premium"
    print("  ✅ CostController tier override 正确")


def test_cost_estimate():
    from workflow.agents.cost_controller import CostController
    cc = CostController(total_budget=100000)
    est = cc.estimate_cost(project_count=1, avg_pr_count=100)
    assert est["estimated_tokens"] > 0
    assert est["estimated_cost_usd"] > 0
    assert est["within_budget"] is True
    print("  ✅ CostController estimate_cost 正确")


def test_cost_usage_report():
    from workflow.agents.cost_controller import CostController
    cc = CostController(total_budget=10000)
    cc.record_usage("analyst", 500, 200)
    cc.record_usage("collector", 100, 50)
    report = cc.get_usage_report()
    assert "analyst" in report["agent_usage"]
    assert "collector" in report["agent_usage"]
    assert report["budget"]["used"] == 850
    assert report["total_cost_usd"] > 0
    print("  ✅ CostController usage_report 正确")


# ====================
# 5. Collector 增强工具测试
# ====================

def test_collector_has_new_tools():
    from workflow.agents.collector_agent import CollectorAgent
    agent = CollectorAgent()
    tools = agent.tool_names
    assert "incremental_fetch" in tools
    assert "parallel_fetch" in tools
    assert len(tools) == 8
    print("  ✅ CollectorAgent 新工具注册正确")


def test_incremental_fetch_no_new():
    from workflow.agents.collector_tools import incremental_fetch

    mock_gs = MagicMock()
    mock_gs.fetch_prs_for_project.return_value = {
        "prs": [{"number": 1}, {"number": 2}], "total": 2, "error": None,
    }
    mock_db = MagicMock()
    mock_db.get_pr_data.return_value = {
        "data": {"prs": [{"number": 1}, {"number": 2}]}
    }

    with patch("workflow.agents.collector_tools._get_services", return_value=(mock_gs, mock_db)):
        result = incremental_fetch.invoke({"owner": "o", "repo": "r"})

    parsed = json.loads(result)
    assert parsed["new_prs"] == 0
    assert "无新增" in parsed["message"]
    print("  ✅ incremental_fetch 无新增 PR 正确")


def test_incremental_fetch_has_new():
    from workflow.agents.collector_tools import incremental_fetch

    mock_gs = MagicMock()
    mock_gs.fetch_prs_for_project.return_value = {
        "prs": [{"number": 1}, {"number": 2}, {"number": 3}],
        "total": 3, "error": None,
    }
    mock_gs.fetch_pr_comments.return_value = {"total": 5, "error": None, "comments": []}
    mock_gs.fetch_pr_detail_batch.return_value = {"results": [{"pr_number": 3, "error": None}]}
    mock_gs.fetch_all_pr_reviews.return_value = {"results": [{"pr_number": 3, "error": None, "reviews": []}]}
    mock_db = MagicMock()
    mock_db.get_pr_data.return_value = {
        "data": {"prs": [{"number": 1}, {"number": 2}]}
    }

    with patch("workflow.agents.collector_tools._get_services", return_value=(mock_gs, mock_db)):
        result = incremental_fetch.invoke({"owner": "o", "repo": "r"})

    parsed = json.loads(result)
    assert parsed["new_prs"] == 1
    print("  ✅ incremental_fetch 有新增 PR 正确")


def test_parallel_fetch():
    from workflow.agents.collector_tools import parallel_fetch

    mock_gs = MagicMock()
    mock_gs.fetch_pr_comments.return_value = {"total": 10, "error": None}
    mock_gs.fetch_pr_detail_batch.return_value = {
        "results": [{"pr_number": 1, "error": None}, {"pr_number": 2, "error": None}]
    }
    mock_gs.fetch_all_pr_reviews.return_value = {
        "results": [
            {"pr_number": 1, "error": None, "reviews": [{"state": "APPROVED"}]},
            {"pr_number": 2, "error": None, "reviews": []},
        ]
    }
    mock_db = MagicMock()

    with patch("workflow.agents.collector_tools._get_services", return_value=(mock_gs, mock_db)):
        result = parallel_fetch.invoke({
            "owner": "o", "repo": "r",
            "pr_numbers": "1,2", "data_types": "comments,details,reviews",
        })

    parsed = json.loads(result)
    assert parsed["fetched_prs"] == 2
    assert parsed["total_items"] > 0
    print("  ✅ parallel_fetch 并发拉取正确")


# ====================
# 6. Reporter HTML 工具测试
# ====================

def test_reporter_has_html_tool():
    from workflow.agents.reporter_agent import ReporterAgent
    agent = ReporterAgent()
    assert "format_report_html" in agent.tool_names
    assert len(agent.tool_names) == 6
    print("  ✅ ReporterAgent HTML 工具注册正确")


def test_format_report_html():
    from workflow.agents.reporter_tools import format_report_html
    report = {
        "owner": "test", "repo": "project",
        "summary": {"total": 100, "success_rate": 92.5, "avg_duration_seconds": 500, "avg_coverage": 75.0},
        "insights": [
            {"name": "成功率", "value": 92.5, "grade": "B", "description": "良好", "suggestion": "关注偶发失败"},
        ],
        "overall_grade": "B",
        "generated_at": "2026-05-19",
    }
    html = format_report_html.invoke({"report_json": json.dumps(report)})
    assert "<html" in html
    assert "test/project" in html
    assert "92.5%" in html
    assert "综合评级" in html
    print("  ✅ format_report_html 正确")


def test_format_report_html_empty():
    from workflow.agents.reporter_tools import format_report_html
    html = format_report_html.invoke({"report_json": "{}"})
    assert "<html" in html
    print("  ✅ format_report_html 空数据处理正确")


# ====================
# 7. 新 API 端点测试
# ====================

def test_traces_endpoint():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from workflow.api.routes import register_workflow_routes

    app = FastAPI()
    register_workflow_routes(app.router)
    client = TestClient(app)

    resp = client.get("/agent/traces")
    assert resp.status_code == 200
    data = resp.json()
    assert "traces" in data
    print("  ✅ GET /agent/traces 端点正确")


def test_cost_endpoint():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from workflow.api.routes import register_workflow_routes

    app = FastAPI()
    register_workflow_routes(app.router)
    client = TestClient(app)

    resp = client.get("/agent/cost")
    assert resp.status_code == 200
    data = resp.json()
    assert "budget" in data
    assert "agent_usage" in data
    print("  ✅ GET /agent/cost 端点正确")


def test_artifacts_endpoint():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from workflow.api.routes import register_workflow_routes

    app = FastAPI()
    register_workflow_routes(app.router)
    client = TestClient(app)

    resp = client.get("/agent/artifacts/test/project")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, dict)
    print("  ✅ GET /agent/artifacts/{owner}/{repo} 端点正确")


def test_project_traces_endpoint():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from workflow.api.routes import register_workflow_routes

    app = FastAPI()
    register_workflow_routes(app.router)
    client = TestClient(app)

    resp = client.get("/agent/traces/project/test/project")
    assert resp.status_code == 200
    print("  ✅ GET /agent/traces/project/{owner}/{repo} 端点正确")


# ====================
# 运行测试
# ====================

def main():
    print("=" * 60)
    print("Phase 6 增强测试")
    print("=" * 60)

    sections = [
        ("AgentRegistry", [
            ("注册", test_registry_register),
            ("注册默认", test_registry_register_defaults),
            ("延迟实例化", test_registry_get_creates_instance),
            ("不存在返回 None", test_registry_get_nonexistent),
            ("销毁", test_registry_destroy),
            ("热替换", test_registry_hot_replace),
            ("标签查找", test_registry_find_by_tag),
            ("状态查询", test_registry_get_status),
            ("调用记录", test_registry_record_invocation),
        ]),
        ("ArtifactStore", [
            ("存储/获取", test_artifact_store_and_get),
            ("版本递增", test_artifact_versioning),
            ("项目产物", test_artifact_project_artifacts),
            ("变更检测", test_artifact_is_changed),
            ("删除", test_artifact_delete),
            ("快照", test_artifact_snapshot),
            ("摘要", test_artifact_summary),
        ]),
        ("TraceManager", [
            ("开始/完成", test_trace_start_finish),
            ("追踪片段", test_trace_spans),
            ("列表", test_trace_list),
            ("项目历史", test_trace_project_history),
            ("导出", test_trace_export),
            ("摘要", test_trace_summary),
            ("上限清理", test_trace_max_traces),
        ]),
        ("CostController", [
            ("用量记录", test_cost_record_usage),
            ("预算超限", test_cost_budget_exceeded),
            ("LLM 分级", test_cost_recommended_tier),
            ("等级覆盖", test_cost_tier_override),
            ("成本估算", test_cost_estimate),
            ("用量报告", test_cost_usage_report),
        ]),
        ("Collector 增强", [
            ("新工具注册", test_collector_has_new_tools),
            ("增量无新", test_incremental_fetch_no_new),
            ("增量有新", test_incremental_fetch_has_new),
            ("并发拉取", test_parallel_fetch),
        ]),
        ("Reporter 增强", [
            ("HTML 工具", test_reporter_has_html_tool),
            ("HTML 格式化", test_format_report_html),
            ("HTML 空", test_format_report_html_empty),
        ]),
        ("新 API", [
            ("追踪列表", test_traces_endpoint),
            ("成本报告", test_cost_endpoint),
            ("产物查询", test_artifacts_endpoint),
            ("项目追踪", test_project_traces_endpoint),
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
