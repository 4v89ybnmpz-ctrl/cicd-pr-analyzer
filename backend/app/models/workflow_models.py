"""
工作流仿真引擎数据模型
定义工作流定义、仿真结果、断点等 Pydantic 模型
"""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel


# ==================== 工作流定义 ====================

class StepPrompt(BaseModel):
    """从 task-prompts.md 解析出的单步 prompt 定义"""
    step_id: str
    subagent_type: Optional[str] = None
    prompt_template: str = ""
    required_skills: List[str] = []
    recommended_skills: List[str] = []
    validation_criteria: List[str] = []
    constraints: List[str] = []


class SubAgentDef(BaseModel):
    """子 Agent 定义"""
    name: str
    description: str = ""
    mode: str = "subagent"
    skills: List[str] = []
    permissions: Dict[str, str] = {}


class WorkflowStep(BaseModel):
    """工作流单步定义"""
    step_id: str                    # "step_1_env_check"
    name: str                       # "环境检查"
    gate_condition: Optional[str] = None
    dispatch_target: Optional[str] = None
    output_artifacts: List[str] = []
    required_skills: List[str] = []
    fallback: Optional[str] = None
    fix_loop_bound: Optional[int] = None
    sub_steps: List['WorkflowStep'] = []
    prompt_def: Optional[StepPrompt] = None


class WorkflowDefinition(BaseModel):
    """完整的工作流定义（从插件 AGENTS.md + task-prompts.md 解析）"""
    plugin_id: str
    plugin_name: str
    description: str = ""
    mode: str = "primary"
    required_skills: List[str] = []
    agents: List[str] = []
    agent_defs: List[SubAgentDef] = []
    steps: List[WorkflowStep] = []
    constraints: List[Dict[str, str]] = []
    parsed_at: str = ""


# ==================== 裁判断点模型 ====================

class ArbitratorIssue(BaseModel):
    """裁判发现的单个问题"""
    problem: str                            # 问题描述
    severity: str = "HIGH"                  # CRITICAL | HIGH | MEDIUM | LOW
    category: str = "OTHER"                 # MISSING_FILE | CONTENT_INCOMPLETE | WRONG_PATH | SKILL_NOT_USED | ENV_MISSING | CONSTRAINT_VIOLATION | COMPILE_ERROR | OTHER
    suggestion: str = ""                    # 修复建议（中文）
    suggestion_action: str = ""             # 具体修复命令或操作
    affected_file: Optional[str] = None     # 受影响的文件路径


class ArbitratorReport(BaseModel):
    """裁判完整报告（每个 step 一次）"""
    session_id: str
    step_id: str
    verdict: str = "unknown"                # pass | fail | unknown
    summary: str = ""                       # 总体评价
    issues: List[ArbitratorIssue] = []      # 问题列表
    raw_response: str = ""                  # 裁判原始输出（备查）
    parsing_success: bool = False           # JSON 是否解析成功
    detected_at: str = ""                   # 时间戳


# ==================== 仿真结果 ====================

class Breakpoint(BaseModel):
    """工程能力断点"""
    step_id: str
    category: str           # SKILL_GAP | CONSTRAINT_VIOLATION | MISSING_ARTIFACT | GATE_FAILURE | PROMPT_AMBIGUITY | FIX_LOOP_RISK
    severity: str           # CRITICAL | HIGH | MEDIUM | LOW
    description: str
    recommendation: str = ""
    affected_artifact: Optional[str] = None


class StepSimResult(BaseModel):
    """单步仿真结果"""
    step_id: str
    step_name: str
    simulated_pass_rate: float = 0.0
    breakpoints: List[Breakpoint] = []
    skills_used: List[str] = []
    skills_missing: List[str] = []
    llm_response_summary: str = ""
    token_usage: Dict[str, int] = {}
    persona_impact: Dict[str, float] = {}


class SimulationResult(BaseModel):
    """完整仿真结果"""
    simulation_id: str
    plugin_id: str
    plugin_name: str
    persona: str             # novice | intermediate | experienced
    steps: List[StepSimResult] = []
    overall_pass_rate: float = 0.0
    total_breakpoints: int = 0
    critical_breakpoints: int = 0
    skill_heatmap: Dict[str, Dict[str, float]] = {}
    antipatterns_matched: List[Dict[str, Any]] = []
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0
    compared_at: str = ""


# ==================== 跨插件对比 ====================

class PluginSimSummary(BaseModel):
    """插件仿真摘要（用于对比）"""
    plugin_id: str
    plugin_name: str
    overall_pass_rate: float
    total_breakpoints: int
    critical_breakpoints: int
    skill_coverage: float
    persona_results: Dict[str, float] = {}


class ComparisonReport(BaseModel):
    """跨插件对比报告"""
    plugins: List[PluginSimSummary] = []
    common_breakpoints: List[Dict[str, Any]] = []
    generated_at: str = ""
