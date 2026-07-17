"""
工作流定义解析器
解析 CANNBot 插件的 AGENTS.md + task-prompts.md 为结构化 WorkflowDefinition
"""

import os
import re
import logging
from datetime import datetime
from typing import List, Dict, Optional

from app.models.workflow_models import (
    WorkflowDefinition,
    WorkflowStep,
    StepPrompt,
    SubAgentDef,
)

logger = logging.getLogger(__name__)

# 项目根目录
_PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
CANNBOT_DIR = os.path.join(_PROJECT_ROOT, "external", "cannbot-skills")


def _parse_yaml_frontmatter(text: str) -> dict:
    """解析 YAML frontmatter（--- ... --- 之间的内容），支持多行列表"""
    match = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    if not match:
        return {}
    raw = match.group(1)
    lines = raw.split("\n")

    result = {}
    current_key = None
    current_list = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        # 多行列表项: "  - value"
        if stripped.startswith("- ") and current_key is not None:
            val = stripped[2:].strip().strip("'\"")
            current_list.append(val)
            continue

        # 保存上一个 key 的列表
        if current_key is not None and current_list:
            result[current_key] = current_list
            current_key = None
            current_list = []
        elif current_key is not None:
            # key 没有值也没列表，存 None
            if current_key not in result:
                result[current_key] = None
            current_key = None

        # key: value 行
        if ":" in stripped:
            key, _, val = stripped.partition(":")
            key = key.strip()
            val = val.strip()

            if val.startswith("[") and val.endswith("]"):
                # 行内列表 [a, b, c]
                result[key] = [
                    v.strip().strip("'\"") for v in val[1:-1].split(",") if v.strip()
                ]
            elif val:
                result[key] = val
                current_key = None
            else:
                # key: 后无值，可能是多行列表开头
                current_key = key
                current_list = []

    # 处理最后一个 key
    if current_key is not None and current_list:
        result[current_key] = current_list

    return result


def parse_agents_md(plugin_dir: str) -> dict:
    """
    解析插件的 AGENTS.md 文件
    返回: {description, mode, skills, agents, steps_raw, constraints}
    """
    agents_path = os.path.join(plugin_dir, "AGENTS.md")
    if not os.path.exists(agents_path):
        # 尝试 CLAUDE.md（某些插件用这个）
        agents_path = os.path.join(plugin_dir, "CLAUDE.md")
    if not os.path.exists(agents_path):
        return {}

    text = open(agents_path, encoding="utf-8", errors="replace").read()

    # 解析 frontmatter
    fm = _parse_yaml_frontmatter(text)

    # 提取 skills 列表
    skills = fm.get("skills", [])
    if isinstance(skills, str):
        skills = [s.strip() for s in skills.split(",") if s.strip()]

    # 提取 Subagent 职责表（只取"职责划分"段落的第一个表格）
    agents = []
    # 找到 Subagent/职责划分 段落
    agent_section_match = re.search(
        r"(?:Subagent|职责划分|Subagent 职责).*?\n\|[^|]+\|[^|]+\|\n\|[-\s|]+\|\n((?:\|.*\|\n?)+)",
        text,
        re.DOTALL | re.IGNORECASE,
    )
    if agent_section_match:
        table_text = agent_section_match.group(1)
        table_pattern = r"\|\s*\*?\*?(\w[\w\s\-]*)\*?\*?\s*\|\s*([^|]+)\|"
        for match in re.finditer(table_pattern, table_text):
            role = match.group(1).strip().replace("**", "")
            desc = match.group(2).strip()
            if role in ("角色", "Role", "---"):
                continue
            agents.append({"role": role, "description": desc})

    # 提取约束表
    constraints = []
    constraint_pattern = r"\|\s*(\w+)\s*\|\s*([^|]+)\|"
    in_constraint_section = False
    for line in text.split("\n"):
        if "约束" in line and ("#" in line or "Constraint" in line):
            in_constraint_section = True
            continue
        if in_constraint_section and line.startswith("#"):
            in_constraint_section = False
        if in_constraint_section and "|" in line:
            m = re.match(constraint_pattern, line)
            if m:
                rule_id = m.group(1).strip()
                rule_text = m.group(2).strip()
                if rule_id not in ("#", "Rule", "---") and not rule_id.startswith("-"):
                    constraints.append({"id": rule_id, "rule": rule_text})

    return {
        "description": fm.get("description", ""),
        "mode": fm.get("mode", "primary"),
        "skills": skills,
        "agents": agents,
        "constraints": constraints,
    }


def parse_workflow_steps(text: str) -> List[dict]:
    """
    从 AGENTS.md 的 ASCII 流程图或标题中提取工作流步骤
    支持: Step N / Phase N / Stage N 格式
    """
    steps = []

    # 匹配多种格式的步骤行
    step_patterns = [
        r"Step\s+([\d.]+)\s*[:：]\s*(.+?)(?:\s*[（(](.+?)[）)])?\s*$",
        r"Phase\s+([\d.]+)\s*[:：]\s*(.+?)(?:\s*[（(](.+?)[）)])?\s*$",
        r"Stage\s+([\d.]+)\s*[:：]\s*(.+?)(?:\s*[（(](.+?)[）)])?\s*$",
        r"阶段\s*(\d+)\s*[:：]\s*(.+?)(?:\s*[（(](.+?)[）)])?\s*$",
    ]

    for line in text.split("\n"):
        line = line.strip()
        for pattern in step_patterns:
            m = re.match(pattern, line)
            if m:
                step_num = m.group(1)
                step_name = m.group(2).strip()
                agent_hint = (m.group(3) or "").strip()
                steps.append(
                    {
                        "step_num": step_num,
                        "name": step_name,
                        "agent_hint": agent_hint,
                    }
                )
                break

    if not steps:
        return steps

    # 从 Step 详解段落中提取 gate / dispatch / artifacts
    for step in steps:
        sn = step["step_num"]
        # 查找该步骤的详细段落（支持 Step/Phase/Stage）
        section_pattern = rf"(?:####|###)\s+(?:Step|Phase|Stage)\s+{re.escape(sn)}[：:\s]*(.*?)(?=(?:####|###)\s+(?:Step|Phase|Stage)|\Z)"
        match = re.search(section_pattern, text, re.DOTALL)
        if match:
            section_text = match.group(1)

            # 提取门禁/完成判定
            gate_match = re.search(r"(?:完成判定|gate)[：:]\s*(.+)", section_text)
            if gate_match:
                step["gate"] = gate_match.group(1).strip()

            # 提取触发条件
            trigger_match = re.search(r"触发条件[：:]\s*(.+)", section_text)
            if trigger_match:
                step["trigger"] = trigger_match.group(1).strip()

            # 提取失败处理
            fail_matches = re.findall(r"(?:失败处理|失败)[：:]\s*(.+)", section_text)
            if fail_matches:
                step["fallback"] = fail_matches[0].strip()

            # 提取修复循环上限
            loop_match = re.search(r"最多\s*(\d+)\s*轮", section_text)
            if loop_match:
                step["fix_loop_bound"] = int(loop_match.group(1))

    return steps


def _clean_skill_name(raw: str) -> Optional[str]:
    """从一行 skill 引用里提取干净的 skill 名。

    task-prompts.md 实际行格式如：
        - /ascendc-precision-debug — 遇到...症状时使用
        - ascendc-tiling-design：Tiling 设计
    需剥掉前导 `/`、可能的 plugin 前缀（plugin:skill）、以及 ` — 描述`/`：描述` 尾巴。
    """
    s = raw.strip().lstrip("-").strip().lstrip("/").strip()
    # 去 plugin 前缀（如 ops-direct-invoke-skills:ascendc-tiling-design）
    if ":" in s:
        s = s.rsplit(":", 1)[-1].strip()
    m = re.match(r"([A-Za-z0-9][\w-]*)", s)
    return m.group(1) if m else None


def _scan_inline_skills(text: str) -> List[str]:
    """扫描正文里隐式的 /skill-name 引用。

    skill 名在 cannbot-skills 项目里命名高度规整，统一以这些前缀开头，
    用前缀白名单过滤，避免把 /docs、/api、/matmul 这类路径/参数误判为 skill。
    """
    SKILL_PREFIXES = (
        "ascendc-",
        "ops-",
        "npu-",
        "pypto-",
        "model-infer-",
        "tilelang-",
        "catlass-",
        "triton-",
        "gitcode-",
        "cann-",
        "torch-",
        "aiss-",
        "cuda2ascend-",
    )
    found = re.findall(r"/(?=[a-z])([\w-]+)", text or "")
    seen: List[str] = []
    for name in found:
        if name.startswith(SKILL_PREFIXES) and name not in seen:
            seen.append(name)
    return seen


def parse_task_prompts(task_prompts_path: str) -> Dict[str, StepPrompt]:
    """
    解析 task-prompts.md，提取每个 Step 的 prompt 定义
    """
    if not os.path.exists(task_prompts_path):
        return {}

    text = open(task_prompts_path, encoding="utf-8", errors="replace").read()

    # 按 ## Step N 分块
    step_blocks = re.split(r"^##\s+Step\s+([\d.]+)", text, flags=re.MULTILINE)

    result = {}
    i = 1  # step_blocks[0] 是标题前的内容
    while i < len(step_blocks):
        step_num = step_blocks[i].strip()
        block_text = step_blocks[i + 1] if i + 1 < len(step_blocks) else ""
        i += 2

        prompt = StepPrompt(step_id=f"step_{step_num}")

        # 提取 subagent_type（支持同一 ## Step 下多个 JSON 块如 5a/5b、6a/6b，逗号拼接）
        sa_matches = re.findall(r'"subagent_type"\s*:\s*"([^"]+)"', block_text)
        if sa_matches:
            prompt.subagent_type = ", ".join(sa_matches)

        # 提取 prompt 模板（整个 prompt 字段内容）
        prompt_match = re.search(r'"prompt"\s*:\s*"(.+?)"\s*\}', block_text, re.DOTALL)
        if prompt_match:
            prompt.prompt_template = prompt_match.group(1)[:2000]  # 截断过长内容

        # 提取必读 Skill（清洗为干净 skill 名）
        required = re.findall(r"【必读\s*Skill】\s*\n((?:\s*-\s*.+\n?)+)", block_text)
        if required:
            prompt.required_skills = [
                name
                for name in (
                    _clean_skill_name(s) for s in required[0].split("\n") if s.strip()
                )
                if name
            ]

        # 提取推荐 Skill（清洗为干净 skill 名）
        recommended = re.findall(
            r"【推荐\s*Skill】\s*\n((?:\s*-\s*.+\n?)+)", block_text
        )
        rec_names: List[str] = []
        if recommended:
            rec_names = [
                name
                for name in (
                    _clean_skill_name(s)
                    for s in recommended[0].split("\n")
                    if s.strip()
                )
                if name
            ]

        # 扫描正文里隐式 /skill-name 引用（plan 缺口 A），并入推荐 Skill（去重）
        for name in _scan_inline_skills(block_text):
            if name not in rec_names:
                rec_names.append(name)
        prompt.recommended_skills = rec_names

        # 提取验收标准
        validation = re.findall(r"【验收标准】\s*\n((?:\s*-\s*.+\n?)+)", block_text)
        if validation:
            prompt.validation_criteria = [
                v.strip().lstrip("- ").strip()
                for v in validation[0].strip().split("\n")
                if v.strip()
            ]

        # 提取约束
        constraints = re.findall(r"【约束】\s*\n((?:\s*-\s*.+\n?)+)", block_text)
        if constraints:
            prompt.constraints = [
                c.strip().lstrip("- ").strip()
                for c in constraints[0].strip().split("\n")
                if c.strip()
            ]

        result[f"step_{step_num}"] = prompt

    return result


def extract_subagents(plugin_dir: str) -> List[SubAgentDef]:
    """扫描 agents/*.md 提取子 Agent 定义"""
    agents_dir = os.path.join(plugin_dir, "agents")
    if not os.path.isdir(agents_dir):
        return []

    result = []
    for fname in sorted(os.listdir(agents_dir)):
        if not fname.endswith(".md"):
            continue
        fpath = os.path.join(agents_dir, fname)
        text = open(fpath, encoding="utf-8", errors="replace").read()
        fm = _parse_yaml_frontmatter(text)

        skills = fm.get("skills", [])
        if isinstance(skills, str):
            skills = [s.strip() for s in skills.split(",") if s.strip()]

        result.append(
            SubAgentDef(
                name=fname.replace(".md", ""),
                description=fm.get("description", ""),
                mode=fm.get("mode", "subagent"),
                skills=skills,
                permissions={},
            )
        )

    return result


def _build_step_from_parsed(
    step_info: dict, prompts: Dict[str, StepPrompt]
) -> WorkflowStep:
    """将解析出的步骤信息转换为 WorkflowStep"""
    step_num = step_info.get("step_num", "0")
    step_key = f"step_{step_num}"
    name = step_info.get("name", f"Step {step_num}")
    agent_hint = step_info.get("agent_hint", "")

    # 查找对应的 prompt 定义
    prompt_def = prompts.get(step_key)

    # 确定调度目标
    dispatch = None
    if prompt_def and prompt_def.subagent_type:
        dispatch = prompt_def.subagent_type
    elif agent_hint:
        dispatch = agent_hint

    # 确定需要的 Skills
    skills = []
    if prompt_def:
        skills = prompt_def.required_skills + prompt_def.recommended_skills

    # 确定输出产物
    artifacts = []
    if prompt_def and prompt_def.prompt_template:
        tpl = prompt_def.prompt_template
        # 优先从【输出】段落提取，避免误匹配输入引用
        output_section = ""
        m = re.search(r"【输出】(.*?)(?:【|##|\Z)", tpl, re.DOTALL)
        if m:
            output_section = m.group(1)
        # 若无【输出】标记，从【验收标准】段落提取（含"已创建"/"都存在"等完成条件）
        if not output_section:
            m2 = re.search(r"【验收标准】(.*?)(?:【|##|\Z)", tpl, re.DOTALL)
            if m2:
                output_section = m2.group(1)
        # 提取完整相对路径（含 {operator_name} 占位符，session 创建时替换）
        search_text = output_section if output_section else tpl
        artifact_patterns = re.findall(
            r"(operators/\{?\w+\}?/docs/[\w/]+\.\w+)", search_text
        )
        artifacts = list(set(artifact_patterns))

    return WorkflowStep(
        step_id=step_key,
        name=name,
        gate_condition=step_info.get("gate"),
        dispatch_target=dispatch,
        output_artifacts=artifacts,
        required_skills=skills,
        fallback=step_info.get("fallback"),
        fix_loop_bound=step_info.get("fix_loop_bound"),
        prompt_def=prompt_def,
    )


def parse_registry_workflow(task_prompts_path: str) -> List[WorkflowStep]:
    """定制：解析 ops-registry-invoke 风格「任务恢复映射表」→ 4 大阶段 + 子 step。

    映射表格式（workflow/resources/task-prompts.md）：
        | 阶段 | Subagent | 恢复说明 |
        | 1.1 开发准备 | `general` | ... |
        | 2-迭代一-A1-Main | `ascendc-ops-developer` | ... |
        | 4.2 代码检视 | 主 Agent 加载 skill | 调用 /ascendc-code-review |
    按编号首位（1/2/3/4）归入 4 大阶段，每阶段一个大 WorkflowStep，
    其 sub_steps 为该阶段下的子 step（含 dispatch）。
    """
    PHASE_NAMES = {
        "1": "阶段一·需求与设计",
        "2": "阶段二·开发",
        "3": "阶段三·验收",
        "4": "阶段四·上库",
    }
    try:
        text = open(task_prompts_path, encoding="utf-8", errors="replace").read()
    except Exception:
        return []
    # ① 解析映射表行 → [(name, dispatch)]
    rows: List[tuple] = []
    in_table = False
    for line in text.split("\n"):
        s = line.strip()
        if not in_table:
            if s.startswith("|") and "Subagent" in s and ("阶段" in s or "中断" in s):
                in_table = True
            continue
        if not s.startswith("|"):
            if s:
                break  # 表格结束
            continue
        if "---" in s:
            continue
        cols = [c.strip() for c in s.split("|")]
        cols = [c for c in cols if c != ""]
        if len(cols) < 2:
            continue
        name = cols[0]
        sub_raw = cols[1]
        m_sub = re.match(r"[`'\s]*(general|ascendc-ops-[\w-]+)", sub_raw)
        sub = m_sub.group(1) if m_sub else sub_raw.strip("`").split()[0].strip("`")
        desc = " ".join(cols[2:])
        if sub.startswith(("general", "ascendc-ops-")):
            dispatch = sub
        else:
            m = re.search(r"/?(ascendc-[\w-]+)", desc + " " + sub)
            dispatch = m.group(1) if m else None
        rows.append((name, dispatch))
    # ② 按编号首位归入 4 大阶段，每阶段一个 WorkflowStep，子 step 进 sub_steps
    phases: dict = {}
    for name, dispatch in rows:
        m = re.match(r"^\s*(\d)", name)
        pnum = m.group(1) if m else "?"
        phases.setdefault(pnum, []).append((name, dispatch))
    # 各阶段的必用 Skill/Agent（用于 skill 遵从度检测，含 skill 名和 agent 名）
    PHASE_REQUIRED_SKILLS = {
        "1": ["ops-registry-invoke-workflow", "ascendc-registry-invoke-template", "ascendc-docs-search",
              "ascendc-ops-architect", "ascendc-ops-tester"],
        "2": ["ops-registry-invoke-workflow", "ascendc-registry-invoke-template",
              "ascendc-ops-developer", "ascendc-ops-tester", "ascendc-ut-develop"],
        "3": ["ops-registry-invoke-workflow", "ops-precision-standard", "ops-profiling",
              "ascendc-ops-tester", "ascendc-ops-developer"],
        "4": ["ops-registry-invoke-workflow", "ascendc-code-review", "ascendc-docs-gen"],
    }
    # 各阶段产出物，来自 data-flow.md 文件路径速查表。{} 占位符由 sessions.py 替换
    # phase 级别只检查"阶段完成后一定存在"的关键产出物；子步骤级别在 SUB_STEP_ARTIFACTS 中定义
    PHASE_ARTIFACTS = {
        "1": ["operators/{operator_name}/docs/LOG.md"],
        "2": ["operators/{operator_name}/tests/reports/iter"],
        "3": ["operators/{operator_name}/docs/precision-report.md"],
        "4": ["operators/{operator_name}/README.md"],
    }
    # 每个子步骤的关键产出物（来自 data-flow.md 的「文件路径速查表」和阶段表格）
    SUB_STEP_ARTIFACTS = {
        "1.1 开发准备": ["docs/LOG.md"],
        "1.2 需求分析": ["docs/REQUIREMENTS.md", "docs/aclnn{OperatorName}.md"],
        "1.2.5 spec 生成": ["docs/spec.yaml"],
        "1.3 方案设计": ["docs/DESIGN.md"],
        "1.3R 方案评审": ["docs/DESIGN_REVIEW.md"],
        "1.4 测试设计": ["docs/TEST.md"],
        "1.4R 测试设计评审": ["docs/TEST_REVIEW.md"],
        "2-迭代一-A1-Main": ["op_kernel/"],
        "2-迭代二-A1-P": ["probe/RESULT.md"],
        "2-汇合验证": ["tests/reports/iter"],
        "2-测试工程师验收": ["tests/reports/iter"],
        "3.1 精度验收": ["docs/precision-report.md"],
        "3.2 性能验收": ["docs/performance-report.md"],
        "4.1 文档与示例": ["README.md", "examples/"],
        "4.2 代码检视": ["docs/"],
        "4.3 开发总结": ["docs/LOG.md"],
    }
    steps: List[WorkflowStep] = []
    for pnum in sorted(phases.keys()):
        sub_steps = [
            WorkflowStep(
                step_id="step_" + re.sub(r"[^\w]", "_", sname).strip("_"),
                name=sname,
                dispatch_target=dispatch,
                output_artifacts=[
                    "operators/{operator_name}/" + a
                    for a in SUB_STEP_ARTIFACTS.get(sname, [])
                ],
            )
            for sname, dispatch in phases[pnum]
        ]
        steps.append(
            WorkflowStep(
                step_id=f"phase_{pnum}",
                name=PHASE_NAMES.get(pnum, f"阶段{pnum}"),
                sub_steps=sub_steps,
                output_artifacts=PHASE_ARTIFACTS.get(pnum, []),
                required_skills=PHASE_REQUIRED_SKILLS.get(pnum, []),
            )
        )
    return steps


def build_workflow_definition(plugin_dir: str) -> Optional[WorkflowDefinition]:
    """
    构建完整的工作流定义
    编排所有解析函数，输出 WorkflowDefinition
    """
    if not os.path.isdir(plugin_dir):
        return None

    plugin_id = os.path.basename(plugin_dir)

    # 解析 AGENTS.md
    agents_info = parse_agents_md(plugin_dir)
    if not agents_info:
        logger.warning(f"插件 {plugin_id} 没有 AGENTS.md 或 CLAUDE.md")
        return None

    # 解析 task-prompts.md
    prompts_path = os.path.join(plugin_dir, "workflows", "task-prompts.md")
    prompts = parse_task_prompts(prompts_path)

    # 提取子 Agent
    agent_defs = extract_subagents(plugin_dir)

    # 读取主文件全文提取工作流步骤
    agents_file = os.path.join(plugin_dir, "AGENTS.md")
    if not os.path.exists(agents_file):
        agents_file = os.path.join(plugin_dir, "CLAUDE.md")
    full_text = open(agents_file, encoding="utf-8", errors="replace").read()
    parsed_steps = parse_workflow_steps(full_text)

    # 如果主文件没有步骤，尝试读取外部 workflow 文件
    if not parsed_steps:
        # 尝试 workflows/ 目录下的 md 文件
        wf_dir = os.path.join(plugin_dir, "workflows")
        if os.path.isdir(wf_dir):
            for wf_file in sorted(os.listdir(wf_dir)):
                if not wf_file.endswith(".md") or wf_file == "task-prompts.md":
                    continue
                wf_path = os.path.join(wf_dir, wf_file)
                wf_text = open(wf_path, encoding="utf-8", errors="replace").read()
                parsed_steps = parse_workflow_steps(wf_text)
                if parsed_steps:
                    # 也尝试解析这个文件的 task-prompts 内容
                    wf_prompts = parse_task_prompts(wf_path)
                    if wf_prompts:
                        prompts.update(wf_prompts)
                    break

    # 构建 WorkflowStep 列表
    steps = []
    for step_info in parsed_steps:
        step = _build_step_from_parsed(step_info, prompts)
        steps.append(step)

    # 如果 ASCII 流程图没提取到步骤，尝试从 task-prompts.md 构建
    if not steps and prompts:
        for step_key, prompt_def in sorted(prompts.items()):
            steps.append(
                WorkflowStep(
                    step_id=step_key,
                    name=step_key.replace("_", " "),
                    gate_condition=None,
                    dispatch_target=prompt_def.subagent_type,
                    output_artifacts=[],
                    required_skills=prompt_def.required_skills
                    + prompt_def.recommended_skills,
                    prompt_def=prompt_def,
                )
            )

    # 定制：registry 风格插件，尝试解析任务恢复映射表（workflow/resources/task-prompts.md 等）
    if not steps:
        for cand in ("workflow/resources/task-prompts.md", "workflows/task-prompts.md", "workflow/task-prompts.md"):
            rp = os.path.join(plugin_dir, cand)
            if os.path.isfile(rp):
                reg_steps = parse_registry_workflow(rp)
                if reg_steps:
                    steps = reg_steps
                    break

    # 如果还是没有步骤，但 agents 有定义，创建通用流程
    if not steps and agent_defs:
        steps = [
            WorkflowStep(
                step_id="step_1_analysis",
                name="需求分析",
                required_skills=agents_info.get("skills", []),
            ),
            WorkflowStep(
                step_id="step_2_design",
                name="方案设计",
                dispatch_target=agent_defs[0].name if agent_defs else None,
            ),
            WorkflowStep(
                step_id="step_3_develop",
                name="开发实现",
                dispatch_target=agent_defs[1].name if len(agent_defs) > 1 else None,
            ),
            WorkflowStep(
                step_id="step_4_review",
                name="审查验证",
                dispatch_target=agent_defs[2].name if len(agent_defs) > 2 else None,
            ),
            WorkflowStep(step_id="step_5_report", name="完成报告"),
        ]

    # 获取插件名称（从 plugin.json 或目录名）
    plugin_name = plugin_id
    plugin_json = os.path.join(plugin_dir, ".claude-plugin", "plugin.json")
    if os.path.exists(plugin_json):
        try:
            import json

            with open(plugin_json) as f:
                pdata = json.load(f)
            plugin_name = pdata.get("name", plugin_id)
        except Exception:
            pass

    return WorkflowDefinition(
        plugin_id=plugin_id,
        plugin_name=plugin_name,
        description=agents_info.get("description", ""),
        mode=agents_info.get("mode", "primary"),
        required_skills=agents_info.get("skills", []) or [],
        agents=[ad.name for ad in agent_defs]
        or [a["role"] for a in agents_info.get("agents", [])],
        agent_defs=agent_defs,
        steps=steps,
        constraints=agents_info.get("constraints", []),
        parsed_at=datetime.now().isoformat(),
    )


def scan_all_plugins() -> List[WorkflowDefinition]:
    """扫描所有官方和社区插件，返回工作流定义列表"""
    results = []
    for plugins_dir in ["plugins-official", "plugins-community"]:
        base = os.path.join(CANNBOT_DIR, plugins_dir)
        if not os.path.isdir(base):
            continue
        for name in sorted(os.listdir(base)):
            plugin_dir = os.path.join(base, name)
            if not os.path.isdir(plugin_dir):
                continue
            # 必须有 AGENTS.md 或 CLAUDE.md
            if not os.path.exists(
                os.path.join(plugin_dir, "AGENTS.md")
            ) and not os.path.exists(os.path.join(plugin_dir, "CLAUDE.md")):
                continue
            try:
                wf = build_workflow_definition(plugin_dir)
                if wf and wf.steps:
                    results.append(wf)
            except Exception as e:
                logger.warning(f"解析插件 {name} 失败: {e}")

    return results
