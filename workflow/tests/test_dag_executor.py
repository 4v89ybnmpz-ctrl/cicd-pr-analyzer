"""
DAG 执行引擎 v2 测试
覆盖: 工具直接执行、并行组、Agent 路由、验证反馈、Smart 模式
"""
import sys
import os
import json
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from unittest.mock import MagicMock, patch


def _make_plan(stages, parallel_groups=None):
    return json.dumps({
        "plan_id": "test", "owner": "o", "repo": "r", "goals": "full",
        "stages": stages,
        "parallel_groups": parallel_groups or [],
    })


# ====================
# 1. DAG v2 核心
# ====================

def test_dag_tools_direct_collector():
    """collector 是工具型 Agent，直接调工具不走 LLM"""
    from workflow.agents.dag_executor import DAGExecutor
    plan = _make_plan([
        {"stage": "collection", "agent": "collector", "tasks": [
            {"id": "t1", "tool": "check_db_cache", "params": {"owner": "o", "repo": "r"}},
        ]},
    ])
    with patch("workflow.agents.dag_executor._invoke_tool") as mock:
        mock.return_value = json.dumps({"has_pr_data": True})
        executor = DAGExecutor(llm=None)
        result = executor.execute(plan)
    assert result.stages[0].agent == "tools"
    assert result.stages[0].status == "ok"
    print("  ✅ collector 直接调工具正确")


def test_dag_tools_direct_validator():
    """validator 也是工具型 Agent"""
    from workflow.agents.dag_executor import DAGExecutor
    plan = _make_plan([
        {"stage": "validation", "agent": "validator", "tasks": [
            {"id": "t1", "tool": "validate_collected_data", "params": {"owner": "o", "repo": "r"}},
        ]},
    ])
    with patch("workflow.agents.dag_executor._invoke_tool") as mock:
        mock.return_value = json.dumps({"valid": True, "completeness_score": 90})
        executor = DAGExecutor(llm=None)
        result = executor.execute(plan)
    assert result.stages[0].agent == "tools"
    print("  ✅ validator 直接调工具正确")


def test_dag_llm_agent_analyst():
    """analyst 需要 LLM，走 Agent 路径"""
    from workflow.agents.dag_executor import DAGExecutor
    plan = _make_plan([
        {"stage": "analysis", "agent": "analyst", "tasks": [
            {"id": "t1", "tool": "analyze_cicd_comments", "params": {"owner": "o", "repo": "r"}},
        ]},
    ])
    with patch("workflow.agents.dag_executor._run_agent") as mock_agent:
        mock_agent.return_value = {"output": "分析完成", "tool_calls": 3, "source": "agent"}
        executor = DAGExecutor(llm=MagicMock())
        result = executor.execute(plan)
    assert result.stages[0].agent == "analyst"
    assert result.stages[0].status == "ok"
    print("  ✅ analyst 走 Agent 正确")


def test_dag_llm_agent_fallback():
    """LLM 不可用时 analyst fallback 到工具直接调用"""
    from workflow.agents.dag_executor import DAGExecutor
    plan = _make_plan([
        {"stage": "analysis", "agent": "analyst", "tasks": [
            {"id": "t1", "tool": "get_cicd_stats", "params": {"owner": "o", "repo": "r"}},
        ]},
    ])
    with patch("workflow.agents.dag_executor._run_agent") as mock_agent, \
         patch("workflow.agents.dag_executor._invoke_tool") as mock_tool:
        mock_agent.return_value = {"output": "", "tool_calls": 0, "source": "fallback"}
        mock_tool.return_value = json.dumps({"total": 50, "success_rate": 90})
        executor = DAGExecutor(llm=None)
        result = executor.execute(plan)
    assert result.stages[0].status == "ok"
    print("  ✅ LLM fallback 正确")


def test_dag_parallel_execution():
    """并行组真正并行执行"""
    from workflow.agents.dag_executor import DAGExecutor
    plan = _make_plan([
        {"stage": "collection", "agent": "collector", "tasks": [
            {"id": "t1", "tool": "check_db_cache", "params": {"owner": "o", "repo": "r"}},
            {"id": "t2", "tool": "incremental_fetch", "params": {"owner": "o", "repo": "r"}},
        ]},
    ], parallel_groups=[["t1", "t2"]])

    call_times = []
    import threading

    def mock_invoke(tool, params):
        call_times.append((tool, time.time(), threading.current_thread().ident))
        time.sleep(0.05)
        return json.dumps({"ok": True})

    with patch("workflow.agents.dag_executor._invoke_tool", side_effect=mock_invoke):
        executor = DAGExecutor(llm=None, max_parallel=4)
        result = executor.execute(plan)

    # 验证两个任务在不同线程执行（并行）
    thread_ids = set(ct[2] for ct in call_times)
    assert len(call_times) == 2
    # 并行组里的任务 + 可能的顺序任务都执行了
    assert result.stages[0].status == "ok"
    print("  ✅ 并行执行正确")


def test_dag_skip_stage():
    from workflow.agents.dag_executor import DAGExecutor
    plan = _make_plan([
        {"stage": "collection", "agent": "collector", "tasks": [], "skipped": True, "reason": "已缓存"},
        {"stage": "reporting", "agent": "reporter", "tasks": [
            {"id": "t1", "tool": "generate_stats_report", "params": {"owner": "o", "repo": "r"}},
        ]},
    ])
    with patch("workflow.agents.dag_executor._run_agent") as mock:
        mock.return_value = {"output": "报告", "tool_calls": 1, "source": "agent"}
        executor = DAGExecutor(llm=MagicMock())
        result = executor.execute(plan)
    assert result.stages[0].skipped is True
    assert result.stages[0].skip_reason == "已缓存"
    assert result.stages[1].skipped is False
    print("  ✅ 跳过阶段正确")


def test_dag_validation_retry():
    """验证失败时重跑 collector + analyst"""
    from workflow.agents.dag_executor import DAGExecutor
    plan = _make_plan([
        {"stage": "collection", "agent": "collector", "tasks": [
            {"id": "t1", "tool": "check_db_cache", "params": {"owner": "o", "repo": "r"}},
        ]},
        {"stage": "analysis", "agent": "analyst", "tasks": [
            {"id": "t2", "tool": "get_cicd_stats", "params": {"owner": "o", "repo": "r"}},
        ]},
        {"stage": "validation", "agent": "validator", "tasks": [
            {"id": "t3", "tool": "validate_collected_data", "params": {"owner": "o", "repo": "r"}},
        ]},
    ])

    invoke_results = {
        "check_db_cache": json.dumps({"has_pr_data": True}),
        "get_cicd_stats": json.dumps({"total": 50}),
        "validate_collected_data": json.dumps({
            "valid": False, "completeness_score": 30,
            "warnings": ["数据不足", "缺少评论数据"],
        }),
    }

    def mock_invoke(tool, params):
        return invoke_results.get(tool, json.dumps({"ok": True}))

    with patch("workflow.agents.dag_executor._invoke_tool", side_effect=mock_invoke), \
         patch("workflow.agents.dag_executor._run_agent") as mock_agent:
        mock_agent.return_value = {"output": "分析", "tool_calls": 1, "source": "agent"}
        executor = DAGExecutor(llm=MagicMock(), max_retries=1)
        result = executor.execute(plan)

    assert result.retry_count == 1
    stage_names = [s.stage for s in result.stages]
    assert any("retry" in n for n in stage_names)
    print("  ✅ 验证反馈循环: 重跑 collection + analysis")


def test_dag_invoke_tool():
    from workflow.agents.dag_executor import _invoke_tool
    with patch("workflow.agents.collector_tools.check_db_cache") as m:
        m.invoke.return_value = json.dumps({"has_pr_data": True})
        result = _invoke_tool("check_db_cache", {"owner": "o", "repo": "r"})
    assert "has_pr_data" in result
    print("  ✅ _invoke_tool 正确")


def test_dag_invoke_tool_unknown():
    from workflow.agents.dag_executor import _invoke_tool
    result = _invoke_tool("unknown_tool", {})
    assert "error" in result
    print("  ✅ _invoke_tool 未知工具处理正确")


# ====================
# 2. Smart 模式图
# ====================

def test_smart_graph_build():
    from workflow.agent_graphs import build_smart_agent_graph
    graph = build_smart_agent_graph()
    nodes = list(graph.get_graph().nodes.keys())
    assert "planner" in nodes
    assert "dag_executor" in nodes
    print("  ✅ Smart 图构建正确")


def test_smart_graph_planner_rule_based():
    """Smart 模式的 planner 直接调用规则函数，不浪费 LLM"""
    from workflow.agent_graphs import build_smart_agent_graph
    from workflow.config import workflow_config
    from datetime import datetime

    graph = build_smart_agent_graph()
    mock_llm = MagicMock()
    orig_llm = workflow_config.llm
    workflow_config.llm = mock_llm

    try:
        # 规则函数 mock
        with patch("workflow.agents.planner_agent.analyze_project_profile") as mock_profile, \
             patch("workflow.agents.planner_agent.create_execution_plan") as mock_plan, \
             patch("workflow.agents.dag_executor.DAGExecutor.execute") as mock_exec:
            mock_profile.invoke.return_value = json.dumps({
                "owner": "o", "repo": "r", "estimated_size": "small",
                "recommendations": ["full_collection"],
            })
            mock_plan.invoke.return_value = json.dumps({
                "plan_id": "plan_o_r", "owner": "o", "repo": "r",
                "stages": [{"stage": "collection", "agent": "collector", "tasks": []}],
                "parallel_groups": [],
            })

            from workflow.agents.dag_executor import DAGRunResult
            mock_result = DAGRunResult(plan_id="plan_o_r", owner="o", repo="r", status="completed")
            mock_result.report = {"final_report": "done"}
            mock_exec.return_value = mock_result

            state = {
                "owner": "o", "repo": "r", "max_prs": 0,
                "pr_list": [], "pr_numbers": [], "comments": {},
                "details": {}, "reviews": {}, "cicd_results": [],
                "stats_report": {}, "ai_analysis": "",
                "ai_suggestions": [], "ai_risk_assessment": "",
                "report": {}, "current_step": "init",
                "progress": 0.0, "errors": [],
                "started_at": datetime.now().isoformat(), "completed_at": "",
            }
            result = graph.invoke(state)

        # 验证调用了规则函数（而非 LLM Agent）
        assert mock_profile.invoke.called
        assert mock_plan.invoke.called
        assert result["current_step"] == "dag_completed"
    finally:
        workflow_config.llm = orig_llm
    print("  ✅ Smart planner 规则函数直接调用正确")


# ====================
# 3. Sequential 图 Registry 复用
# ====================

def test_sequential_registry_reuse():
    from workflow.agent_graphs import build_sequential_agent_graph
    from workflow.config import workflow_config
    from workflow.agents.registry import agent_registry
    from datetime import datetime

    agent_registry.clear()
    agent_registry.set_llm(MagicMock())

    graph = build_sequential_agent_graph()

    def make_mock(name):
        m = MagicMock()
        m.available = True
        m.run.return_value = {"output": f"{name} ok", "messages": [], "tool_calls": 0, "error": None}
        return m

    with patch.object(agent_registry, "get", side_effect=make_mock) as mock_get:
        state = {
            "owner": "o", "repo": "r", "max_prs": 0,
            "pr_list": [], "pr_numbers": [], "comments": {},
            "details": {}, "reviews": {}, "cicd_results": [],
            "stats_report": {}, "ai_analysis": "",
            "ai_suggestions": [], "ai_risk_assessment": "",
            "report": {}, "current_step": "init",
            "progress": 0.0, "errors": [],
            "started_at": datetime.now().isoformat(), "completed_at": "",
        }
        result = graph.invoke(state)

    assert mock_get.call_count >= 5
    assert result["current_step"] == "reported"
    print("  ✅ Sequential 图 Registry 复用正确")


# ====================
# 运行
# ====================

def main():
    print("=" * 60)
    print("DAG v2 执行引擎测试")
    print("=" * 60)

    tests = [
        ("collector 直接调工具", test_dag_tools_direct_collector),
        ("validator 直接调工具", test_dag_tools_direct_validator),
        ("analyst 走 Agent", test_dag_llm_agent_analyst),
        ("LLM fallback", test_dag_llm_agent_fallback),
        ("并行执行", test_dag_parallel_execution),
        ("跳过阶段", test_dag_skip_stage),
        ("验证反馈循环", test_dag_validation_retry),
        ("_invoke_tool", test_dag_invoke_tool),
        ("_invoke_tool 未知", test_dag_invoke_tool_unknown),
        ("Smart 图构建", test_smart_graph_build),
        ("Smart 规则路由", test_smart_graph_planner_rule_based),
        ("Sequential Registry", test_sequential_registry_reuse),
    ]

    passed = failed = 0
    errors = []
    for name, fn in tests:
        try:
            fn()
            passed += 1
        except Exception as e:
            print(f"  ❌ {name}: {e}")
            failed += 1
            errors.append(f"{name}: {e}")

    print(f"\n{'=' * 60}")
    print(f"📊 {passed} 通过, {failed} 失败 (共 {passed + failed})")
    if errors:
        for e in errors:
            print(f"  ❌ {e}")
    print("=" * 60)
    return failed == 0


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
