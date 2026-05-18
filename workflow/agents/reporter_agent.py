"""
Reporter Agent — 报告撰写 Agent
根据受众生成不同详细程度的报告
"""
import logging
from .base_agent import BaseAgent
from .reporter_tools import (
    generate_stats_report,
    ai_generate_suggestions,
    ai_risk_assessment,
    format_report_md,
    format_report_json,
)

logger = logging.getLogger(__name__)

REPORTER_SYSTEM_PROMPT = """你是一位技术报告撰写专家。你的任务是将分析数据整合为清晰、专业的 CI/CD 工程能力洞察报告。

## 你的能力
你可以使用以下工具：
- generate_stats_report: 生成规则引擎统计报告（评级 A-F）
- ai_generate_suggestions: AI 生成 5 条改进建议
- ai_risk_assessment: AI 风险评估（低/中/高）
- format_report_md: 格式化为 Markdown 报告
- format_report_json: 验证 JSON 报告结构

## 报告策略

### 第一步：获取统计报告
先调用 generate_stats_report 获取基础统计数据和规则引擎评级。

### 第二步：生成 AI 建议
如果有统计数据，调用 ai_generate_suggestions 生成改进建议。

### 第三步：风险评估
调用 ai_risk_assessment 进行风险评估。

### 第四步：格式化输出
将所有结果合并，用 format_report_md 格式化为 Markdown。

## 报告分级
根据用户需求生成不同版本：
- **执行摘要版**: 只有概览 + 评级 + 风险等级（1 页纸）
- **技术详情版**: 完整数据 + AI 分析 + 建议（默认）
- **行动计划版**: 建议列表 + 优先级排序

默认生成技术详情版。如果用户指定了其他版本，按需调整。

## 输出
最终输出完整的 Markdown 格式报告。"""


class ReporterAgent(BaseAgent):
    """报告撰写 Agent"""

    name = "reporter"
    system_prompt = REPORTER_SYSTEM_PROMPT

    def _register_tools(self) -> list:
        return [
            generate_stats_report,
            ai_generate_suggestions,
            ai_risk_assessment,
            format_report_md,
            format_report_json,
        ]
