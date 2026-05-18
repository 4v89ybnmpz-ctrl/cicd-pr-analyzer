"""
AI 分析节点测试
覆盖 prompt 构建、LLM Mock、跳过逻辑
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from unittest.mock import MagicMock, patch
import json


def test_build_analysis_prompt():
    """测试 prompt 构建包含所有关键数据"""
    from workflow.ai_nodes import _build_analysis_prompt

    stats_report = {
        "summary": {"total": 100, "success_rate": 85.5, "avg_duration_seconds": 600},
        "trends": [{"period": "2026-05-18", "total": 10, "success_rate": 90.0}],
        "failure_analysis": {"total_failures": 15, "top_failed_jobs": [{"name": "test-x86", "count": 8}]},
        "insights": [{"name": "构建成功率", "grade": "B", "value": 85.5}],
    }

    state = {
        "pr_numbers": [100, 101, 102],
        "reviews": {
            "100": {"reviews": [{"state": "APPROVED"}, {"state": "CHANGES_REQUESTED"}]},
        },
        "details": {
            "100": {"detail": {"state": "merged", "additions": 100, "deletions": 50, "changed_files": 10}},
        },
    }

    prompt = _build_analysis_prompt("rust-lang", "rust", stats_report, state)

    assert "rust-lang/rust" in prompt
    assert "85.5" in prompt
    assert "test-x86" in prompt
    assert "APPROVED" in prompt
    assert "merged" in prompt
    assert "深度分析" in prompt
    print("  ✅ prompt 包含所有关键数据")


def test_summarize_reviews():
    """测试 Review 概要生成"""
    from workflow.ai_nodes import _summarize_reviews

    reviews = {
        "100": {"reviews": [{"state": "APPROVED"}, {"state": "APPROVED"}]},
        "101": {"reviews": [{"state": "CHANGES_REQUESTED"}]},
    }
    summary = _summarize_reviews(reviews)
    assert "2 个 PR" in summary
    assert "APPROVED" in summary
    print("  ✅ Review 概要正确")

    assert "无 Review 数据" in _summarize_reviews({})
    print("  ✅ 空 Review 正确处理")


def test_summarize_details():
    """测试 PR 详情概要"""
    from workflow.ai_nodes import _summarize_details

    details = {
        "100": {"detail": {"state": "merged", "additions": 200, "deletions": 100, "changed_files": 15}},
        "101": {"detail": {"state": "open", "additions": 50, "deletions": 10, "changed_files": 5}},
    }
    summary = _summarize_details(details)
    assert "2 个 PR" in summary
    assert "merged" in summary
    print("  ✅ PR 详情概要正确")


def test_ai_analyze_node_no_llm():
    """测试 LLM 不可用时 ai_analyze 跳过"""
    from workflow.ai_nodes import ai_analyze_node
    from workflow.config import workflow_config

    original_llm = workflow_config.llm
    workflow_config.llm = None

    state = {
        "owner": "test", "repo": "test",
        "stats_report": {"summary": {"total": 10}},
    }
    result = ai_analyze_node(state)

    assert "不可用" in result["ai_analysis"]
    assert result["progress"] == 90.0
    print("  ✅ LLM 不可用时正确跳过")

    workflow_config.llm = original_llm


def test_ai_analyze_node_with_llm():
    """测试 AI 分析节点调用 LLM"""
    from workflow.ai_nodes import ai_analyze_node
    from workflow.config import workflow_config

    mock_llm = MagicMock()
    mock_response = MagicMock()
    mock_response.content = "## 深度分析\n\n该项目 CI/CD 能力处于中上水平..."
    mock_llm.invoke.return_value = mock_response

    original_llm = workflow_config.llm
    workflow_config.llm = mock_llm

    state = {
        "owner": "rust-lang", "repo": "rust",
        "stats_report": {
            "summary": {"total": 100, "success_rate": 85.0},
            "trends": [],
            "failure_analysis": {},
            "insights": [],
        },
        "reviews": {},
        "details": {},
    }
    result = ai_analyze_node(state)

    assert "深度分析" in result["ai_analysis"]
    assert mock_llm.invoke.call_count == 1

    # 验证 prompt 包含 system + user 两条消息
    messages = mock_llm.invoke.call_args[0][0]
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert "rust-lang" in messages[1]["content"]

    print("  ✅ AI 分析节点正确调用 LLM")

    workflow_config.llm = original_llm


def test_ai_suggest_node_with_llm():
    """测试 AI 建议节点解析 JSON"""
    from workflow.ai_nodes import ai_suggest_node
    from workflow.config import workflow_config

    mock_llm = MagicMock()
    mock_response = MagicMock()
    mock_response.content = '''```json
{
  "suggestions": [
    "建议1: 优化构建缓存策略",
    "建议2: 增加并行测试",
    "建议3: 设置构建超时阈值"
  ],
  "risk_assessment": "中等风险：构建成功率波动较大"
}
```'''
    mock_llm.invoke.return_value = mock_response

    original_llm = workflow_config.llm
    workflow_config.llm = mock_llm

    state = {
        "owner": "test", "repo": "test",
        "stats_report": {"summary": {}, "failure_analysis": {}, "insights": []},
        "ai_analysis": "初步分析结果...",
    }
    result = ai_suggest_node(state)

    assert len(result["ai_suggestions"]) == 3
    assert "优化构建缓存" in result["ai_suggestions"][0]
    assert "中等风险" in result["ai_risk_assessment"]
    print("  ✅ AI 建议节点正确解析 JSON")

    workflow_config.llm = original_llm


def test_ai_suggest_node_no_llm():
    """测试 LLM 不可用时 ai_suggest 跳过"""
    from workflow.ai_nodes import ai_suggest_node
    from workflow.config import workflow_config

    original_llm = workflow_config.llm
    workflow_config.llm = None

    state = {
        "owner": "test", "repo": "test",
        "stats_report": {}, "ai_analysis": "",
    }
    result = ai_suggest_node(state)

    assert "请配置" in result["ai_suggestions"][0]
    print("  ✅ LLM 不可用时建议节点正确跳过")

    workflow_config.llm = original_llm


def test_format_duration():
    """测试耗时格式化"""
    from workflow.ai_nodes import _format_duration

    assert _format_duration(None) == "N/A"
    assert _format_duration(30) == "30s"
    assert _format_duration(90) == "1.5m"
    assert _format_duration(7200) == "2.0h"
    print("  ✅ 耗时格式化正确")


def main():
    """运行所有测试"""
    print("=" * 60)
    print("AI 分析节点测试")
    print("=" * 60)

    tests = [
        ("prompt 构建", test_build_analysis_prompt),
        ("Review 概要", test_summarize_reviews),
        ("PR 详情概要", test_summarize_details),
        ("AI 分析跳过", test_ai_analyze_node_no_llm),
        ("AI 分析调用 LLM", test_ai_analyze_node_with_llm),
        ("AI 建议解析 JSON", test_ai_suggest_node_with_llm),
        ("AI 建议跳过", test_ai_suggest_node_no_llm),
        ("耗时格式化", test_format_duration),
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
