"""
LLM 驱动的工作流仿真引擎
通过调用 LLM 模拟不同角色开发者在工作流各步骤的行为，识别工程能力断点
"""
import asyncio
import json
import logging
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Any

from app.models.workflow_models import (
    WorkflowDefinition, WorkflowStep, StepSimResult, SimulationResult,
    Breakpoint,
)
from app.services.antipattern_library import (
    get_antipatterns_for_step, get_antipatterns_for_plugin,
)
from app.services.workflow_parser import build_workflow_definition, CANNBOT_DIR

logger = logging.getLogger(__name__)

# ==================== 角色画像 ====================

PERSONAS = {
    "novice": {
        "name": "新手开发者",
        "description": "刚接触 Ascend C 和 CANN 平台的开发者",
        "system_prompt": (
            "你是一名刚接触 Ascend C 和 CANN 平台的初级开发者。"
            "你的行为特征：\n"
            "1. 倾向跳过文档阅读，直接动手写代码\n"
            "2. 不了解工具链的最佳实践，容易凭直觉做决策\n"
            "3. 可能忽略环境检查、设计评审等前置步骤\n"
            "4. 对 API 不熟悉，可能选用错误的 API\n"
            "5. 测试覆盖通常不完整\n"
            "请严格按照工作流步骤的指示执行，但在每个步骤中表现出上述特征。"
            "在回复末尾用 JSON 格式总结你的行为：\n"
            "```json\n"
            '{"skipped_docs": true/false, "skills_used": [...], '
            '"mistakes_made": [...], "artifacts_produced": [...]}\n'
            "```\n"
        ),
    },
    "intermediate": {
        "name": "中级开发者",
        "description": "有 Ascend C 经验但不够深入的开发者",
        "system_prompt": (
            "你是一名有 1-2 年 Ascend C 经验的中级开发者。"
            "你的行为特征：\n"
            "1. 通常会阅读文档，但可能遗漏关键约束\n"
            "2. 能正确使用大部分 API，但在边界情况可能出错\n"
            "3. 偶尔跳过推荐 Skill 的使用\n"
            "4. 修复循环中可能与 Reviewer 理解不一致\n"
            "请严格按照工作流步骤的指示执行，但在细节上表现出上述特征。"
            "在回复末尾用 JSON 格式总结你的行为：\n"
            "```json\n"
            '{"skipped_docs": true/false, "skills_used": [...], '
            '"mistakes_made": [...], "artifacts_produced": [...]}\n'
            "```\n"
        ),
    },
    "experienced": {
        "name": "资深开发者",
        "description": "精通 Ascend C 和 CANN 生态的资深工程师",
        "system_prompt": (
            "你是一名精通 Ascend C 和 CANN 生态的资深工程师。"
            "你的行为特征：\n"
            "1. 会仔细阅读所有文档和 Skill 指引\n"
            "2. 正确使用所有推荐 Skill\n"
            "3. 极少犯低级错误，但可能在极端边界情况遗漏\n"
            "4. 性能优化意识强，测试覆盖充分\n"
            "请严格按照工作流步骤的指示执行。你的执行质量应该很高，"
            "但允许在复杂场景中有极小概率的遗漏。"
            "在回复末尾用 JSON 格式总结你的行为：\n"
            "```json\n"
            '{"skipped_docs": true/false, "skills_used": [...], '
            '"mistakes_made": [...], "artifacts_produced": [...]}\n'
            "```\n"
        ),
    },
}


# ==================== 步骤 prompt 模板 ====================

def _build_step_prompt(step: WorkflowStep, persona: str, skill_evals: dict,
                       context: dict) -> str:
    """构建发送给 LLM 的步骤仿真 prompt"""
    persona_info = PERSONAS.get(persona, PERSONAS["intermediate"])

    # 技能信息
    skills_text = ""
    if step.required_skills:
        skills_text = "该步骤关联的 Skills：\n"
        for sk in step.required_skills:
            eval_data = skill_evals.get(sk, {})
            grade = eval_data.get("grade", "N/A")
            score = eval_data.get("total_score", 0)
            skills_text += f"  - {sk} (评分: {score}/100, 等级: {grade})\n"

    # 验收标准
    gate_text = ""
    if step.gate_condition:
        gate_text = f"门禁条件: {step.gate_condition}\n"

    # 产物要求
    artifacts_text = ""
    if step.output_artifacts:
        artifacts_text = f"预期产出文件: {', '.join(step.output_artifacts)}\n"

    # prompt 模板
    prompt_template = ""
    if step.prompt_def and step.prompt_def.prompt_template:
        prompt_template = f"\n步骤 prompt 定义（摘要）：\n{step.prompt_def.prompt_template[:500]}\n"

    # 反模式提醒
    antipatterns = get_antipatterns_for_step(step.step_id, context.get("plugin_id"))
    ap_text = ""
    if antipatterns:
        ap_text = "已知风险模式：\n"
        for ap in antipatterns[:3]:
            ap_text += f"  - [{ap['severity']}] {ap['name']}: {ap['description'][:80]}\n"

    user_prompt = f"""## 工作流步骤仿真

你正在执行插件「{context.get('plugin_name', '')}」的工作流。

### 当前步骤: {step.name} (ID: {step.step_id})

{gate_text}{artifacts_text}{skills_text}{prompt_template}{ap_text}

### 任务
请模拟执行这个工作流步骤。说明：
1. 你会如何执行这个步骤
2. 你会使用哪些 Skills
3. 你会产出什么文件
4. 你是否遇到了任何困难或遗漏
5. 该步骤的 prompt 定义是否清晰，有无歧义

请在回复末尾附上 JSON 行为总结。
"""
    return user_prompt


def _parse_behavior_json(response: str) -> dict:
    """从 LLM 回复中提取行为总结 JSON"""
    json_match = None
    # 尝试 ```json ... ``` 格式
    if "```json" in response:
        start = response.index("```json") + 7
        end = response.find("```", start)
        if end > start:
            json_match = response[start:end].strip()
    elif "```" in response:
        start = response.index("```") + 3
        end = response.find("```", start)
        if end > start:
            json_match = response[start:end].strip()

    if json_match:
        try:
            return json.loads(json_match)
        except json.JSONDecodeError:
            pass

    # 尝试找最后一个 { ... } 块
    last_brace = response.rfind('{')
    if last_brace >= 0:
        try:
            return json.loads(response[last_brace:response.rfind('}') + 1])
        except json.JSONDecodeError:
            pass

    return {}


def _detect_breakpoints_from_response(step: WorkflowStep, response: str,
                                       behavior: dict, persona: str) -> List[Breakpoint]:
    """从 LLM 回复中检测断点"""
    breakpoints = []

    # 检查 Skill 使用情况
    skills_used = behavior.get("skills_used", [])
    if step.required_skills:
        missing = [s for s in step.required_skills if s not in skills_used]
        if missing:
            breakpoints.append(Breakpoint(
                step_id=step.step_id,
                category="SKILL_GAP",
                severity="HIGH" if len(missing) > len(step.required_skills) // 2 else "MEDIUM",
                description=f"步骤要求使用 {missing} 但未被使用",
                recommendation=f"在 Step prompt 中强化「必读 Skill」的调用要求",
                affected_artifact=", ".join(missing),
            ))

    # 检查是否跳过了文档
    if behavior.get("skipped_docs") and persona in ("novice", "intermediate"):
        breakpoints.append(Breakpoint(
            step_id=step.step_id,
            category="CONSTRAINT_VIOLATION",
            severity="MEDIUM",
            description=f"角色({persona})跳过了文档阅读",
            recommendation="增加文档阅读的前置检查",
        ))

    # 检查错误
    mistakes = behavior.get("mistakes_made", [])
    if mistakes:
        for mistake in mistakes[:3]:
            severity = "HIGH" if "CRITICAL" in str(mistake).upper() or "critical" in str(mistake) else "MEDIUM"
            breakpoints.append(Breakpoint(
                step_id=step.step_id,
                category="CONSTRAINT_VIOLATION",
                severity=severity,
                description=f"犯错: {str(mistake)[:100]}",
                recommendation="检查 prompt 是否明确约束了此行为",
            ))

    # 检查产物
    artifacts_produced = behavior.get("artifacts_produced", [])
    if step.output_artifacts:
        missing_artifacts = [a for a in step.output_artifacts if a not in str(artifacts_produced)]
        if missing_artifacts:
            breakpoints.append(Breakpoint(
                step_id=step.step_id,
                category="MISSING_ARTIFACT",
                severity="HIGH",
                description=f"缺失产出文件: {missing_artifacts}",
                recommendation="在验收标准中明确列出所有必须产出的文件",
            ))

    # 检查 prompt 歧义（LLM 在回复中提到"不清楚"/"模糊"等）
    ambiguity_keywords = ["不清楚", "模糊", "歧义", "不明确", "ambiguous", "unclear"]
    for kw in ambiguity_keywords:
        if kw in response:
            # 找到包含歧义关键词的句子
            for line in response.split('\n'):
                if kw in line and len(line) < 200:
                    breakpoints.append(Breakpoint(
                        step_id=step.step_id,
                        category="PROMPT_AMBIGUITY",
                        severity="MEDIUM",
                        description=f"Prompt 存在歧义: {line.strip()[:100]}",
                        recommendation="重写 prompt 中相关描述，增加具体示例",
                    ))
                    break
            break

    return breakpoints


def _calculate_pass_rate(breakpoints: List[Breakpoint], persona: str) -> float:
    """基于断点计算步骤通过率"""
    base_rate = 0.95
    for bp in breakpoints:
        if bp.severity == "CRITICAL":
            base_rate -= 0.25
        elif bp.severity == "HIGH":
            base_rate -= 0.15
        elif bp.severity == "MEDIUM":
            base_rate -= 0.08
        else:
            base_rate -= 0.03

    # 角色修正
    persona_penalty = {"novice": 0.10, "intermediate": 0.05, "experienced": 0.02}
    base_rate -= persona_penalty.get(persona, 0.05)

    return max(0.0, min(1.0, base_rate))


# ==================== 主仿真函数 ====================

async def simulate_step(
    step: WorkflowStep,
    persona: str,
    skill_evals: dict,
    context: dict,
) -> StepSimResult:
    """仿真单个步骤"""
    from workflow.config import workflow_config

    if not workflow_config.ai_ready:
        return StepSimResult(
            step_id=step.step_id,
            step_name=step.name,
            simulated_pass_rate=0.0,
            breakpoints=[Breakpoint(
                step_id=step.step_id,
                category="GATE_FAILURE",
                severity="CRITICAL",
                description="LLM 不可用，无法执行仿真",
                recommendation="配置 LLM API Key 后重试",
            )],
            llm_response_summary="LLM 不可用",
        )

    persona_info = PERSONAS.get(persona, PERSONAS["intermediate"])
    user_prompt = _build_step_prompt(step, persona, skill_evals, context)

    try:
        from langchain_core.messages import SystemMessage, HumanMessage
        messages = [
            SystemMessage(content=persona_info["system_prompt"]),
            HumanMessage(content=user_prompt),
        ]

        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: workflow_config.llm.invoke(messages),
        )

        response_text = response.content if hasattr(response, 'content') else str(response)
        token_usage = {}
        if hasattr(response, 'usage_metadata') and response.usage_metadata:
            token_usage = {
                "prompt_tokens": response.usage_metadata.get("input_tokens", 0),
                "completion_tokens": response.usage_metadata.get("output_tokens", 0),
            }
        elif hasattr(response, 'response_metadata'):
            meta = response.response_metadata.get("token_usage", {})
            token_usage = {
                "prompt_tokens": meta.get("prompt_tokens", 0),
                "completion_tokens": meta.get("completion_tokens", 0),
            }

        # 解析行为
        behavior = _parse_behavior_json(response_text)

        # 检测断点
        breakpoints = _detect_breakpoints_from_response(step, response_text, behavior, persona)

        # 匹配反模式
        antipatterns = get_antipatterns_for_step(step.step_id, context.get("plugin_id"))
        for ap in antipatterns:
            persona_suscept = ap.get("persona_susceptibility", {}).get(persona, 0.1)
            if persona_suscept > 0.3:
                # 高易感性的反模式也加入断点
                already_detected = any(
                    bp.category == "CONSTRAINT_VIOLATION" and ap["name"] in bp.description
                    for bp in breakpoints
                )
                if not already_detected:
                    breakpoints.append(Breakpoint(
                        step_id=step.step_id,
                        category="CONSTRAINT_VIOLATION",
                        severity=ap["severity"],
                        description=f"反模式[{ap['name']}]: {ap['description'][:80]}",
                        recommendation=ap.get("mitigation", ""),
                    ))

        # 计算通过率
        pass_rate = _calculate_pass_rate(breakpoints, persona)

        return StepSimResult(
            step_id=step.step_id,
            step_name=step.name,
            simulated_pass_rate=round(pass_rate, 3),
            breakpoints=breakpoints,
            skills_used=behavior.get("skills_used", []),
            skills_missing=[s for s in step.required_skills
                          if s not in behavior.get("skills_used", [])],
            llm_response_summary=response_text[:200],
            token_usage=token_usage,
            persona_impact={persona: round(pass_rate, 3)},
        )

    except Exception as e:
        logger.error(f"步骤仿真失败 [{step.step_id}]: {e}")
        return StepSimResult(
            step_id=step.step_id,
            step_name=step.name,
            simulated_pass_rate=0.0,
            breakpoints=[Breakpoint(
                step_id=step.step_id,
                category="GATE_FAILURE",
                severity="CRITICAL",
                description=f"仿真执行异常: {str(e)[:100]}",
                recommendation="检查 LLM 配置和网络连接",
            )],
            llm_response_summary=f"Error: {str(e)[:100]}",
        )


async def simulate_workflow(
    workflow_def: WorkflowDefinition,
    persona: str,
    skill_evals: dict,
    step_range: tuple = None,
) -> SimulationResult:
    """
    仿真完整工作流
    step_range: (start, end) 可选，只仿真指定步骤范围
    """
    sim_id = uuid.uuid4().hex[:8]
    context = {
        "plugin_id": workflow_def.plugin_id,
        "plugin_name": workflow_def.plugin_name,
    }

    steps = workflow_def.steps
    if step_range:
        start_idx, end_idx = step_range
        steps = steps[start_idx:end_idx + 1]

    step_results = []
    total_tokens = 0

    for step in steps:
        logger.info(f"仿真步骤 [{step.step_id}] {step.name} (角色: {persona})")
        result = await simulate_step(step, persona, skill_evals, context)
        step_results.append(result)
        total_tokens += result.token_usage.get("prompt_tokens", 0) + \
                       result.token_usage.get("completion_tokens", 0)

    # 计算总体通过率
    overall_pass = sum(r.simulated_pass_rate for r in step_results) / len(step_results) \
        if step_results else 0.0

    # 统计断点
    all_breakpoints = []
    critical_count = 0
    for r in step_results:
        all_breakpoints.extend(r.breakpoints)
        critical_count += sum(1 for bp in r.breakpoints if bp.severity == "CRITICAL")

    # 生成技能热力图
    skill_heatmap = _build_skill_heatmap(workflow_def, step_results)

    # 匹配反模式
    plugin_antipatterns = get_antipatterns_for_plugin(workflow_def.plugin_id)
    matched = []
    for ap in plugin_antipatterns:
        suscept = ap.get("persona_susceptibility", {}).get(persona, 0.1)
        if suscept > 0.2:
            matched.append({
                "id": ap["id"],
                "name": ap["name"],
                "severity": ap["severity"],
                "susceptibility": suscept,
                "mitigation": ap.get("mitigation", ""),
            })

    # 估算成本（基于 token 数，Claude Sonnet 约 $3/M input, $15/M output）
    estimated_cost = total_tokens * 0.000005

    return SimulationResult(
        simulation_id=sim_id,
        plugin_id=workflow_def.plugin_id,
        plugin_name=workflow_def.plugin_name,
        persona=persona,
        steps=step_results,
        overall_pass_rate=round(overall_pass, 3),
        total_breakpoints=len(all_breakpoints),
        critical_breakpoints=critical_count,
        skill_heatmap=skill_heatmap,
        antipatterns_matched=sorted(matched, key=lambda x: x["susceptibility"], reverse=True),
        total_tokens=total_tokens,
        estimated_cost_usd=round(estimated_cost, 4),
        compared_at=datetime.now().isoformat(),
    )


def _build_skill_heatmap(workflow_def: WorkflowDefinition,
                          step_results: List[StepSimResult]) -> Dict[str, Dict[str, float]]:
    """构建技能热力图: {step_id: {skill_name: utilization}}"""
    heatmap = {}
    for step, result in zip(workflow_def.steps, step_results):
        if not step.required_skills:
            continue
        step_heat = {}
        for skill in step.required_skills:
            utilization = 1.0 if skill in result.skills_used else 0.0
            step_heat[skill] = utilization
        heatmap[step.step_id] = step_heat
    return heatmap
