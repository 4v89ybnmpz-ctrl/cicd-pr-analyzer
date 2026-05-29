"""
反模式库
从真实社区开发者案例中提取的已知工程能力断点模式
"""

ANTIPATTERNS = [
    {
        "id": "late_tool_discovery",
        "name": "Agent 工具在代码完成后才发现",
        "severity": "CRITICAL",
        "affected_steps": ["step_3", "step_4"],
        "applicable_plugins": ["ops-direct-invoke", "catlass-op-generator",
                               "ops-registry-invoke", "pypto-op-orchestrator"],
        "description": "开发者在 Session 3 才发现 .claude/agents/ 下的 Agent 工具，"
                       "导致编码阶段未使用 Developer agent，遗留 Host 侧编程红线问题"
                       "（指针解引用前未判空），直到 Reviewer agent 检视时才发现。",
        "impact": -0.30,
        "persona_susceptibility": {"novice": 0.7, "intermediate": 0.4, "experienced": 0.1},
        "mitigation": "Step 1 增加 .claude/agents/ 目录发现检查；"
                      "Step 2 交接时明确列出可用 Agent 和 Skill；"
                      "CONTRIBUTING.md 中说明各阶段对应 Agent",
    },
    {
        "id": "env_skip_shortcut",
        "name": "跳过环境检查直接开发",
        "severity": "HIGH",
        "affected_steps": ["step_1"],
        "applicable_plugins": ["ALL"],
        "description": "新手开发者倾向跳过环境检查以更快开始编码，"
                       "导致后续编译失败或 CANN 环境不一致问题。",
        "impact": -0.25,
        "persona_susceptibility": {"novice": 0.6, "intermediate": 0.2, "experienced": 0.05},
        "mitigation": "environment.json 作为 Step 2 的硬依赖；"
                      "在 init.sh 中增加环境预检提示",
    },
    {
        "id": "single_file_design",
        "name": "设计文档合并为单文件",
        "severity": "MEDIUM",
        "affected_steps": ["step_2"],
        "applicable_plugins": ["ops-direct-invoke", "catlass-op-generator",
                               "ops-registry-invoke"],
        "description": "Architect agent 将 DESIGN.md 和 PLAN.md 合并为一个文件，"
                       "违反双文件规范，导致 Developer 无法区分设计和计划。",
        "impact": -0.15,
        "persona_susceptibility": {"novice": 0.2, "intermediate": 0.1, "experienced": 0.05},
        "mitigation": "验收标准明确检查双文件存在；"
                      "prompt 中增加「禁止合并为单文件」约束",
    },
    {
        "id": "fix_loop_no_converge",
        "name": "修复循环不收敛",
        "severity": "HIGH",
        "affected_steps": ["step_5"],
        "applicable_plugins": ["ops-direct-invoke", "catlass-op-generator",
                               "ops-registry-invoke"],
        "description": "Reviewer 和 Developer 对问题理解不一致，"
                       "修复后仍无法通过复审，修复循环耗尽 3 轮仍未通过。",
        "impact": -0.20,
        "persona_susceptibility": {"novice": 0.4, "intermediate": 0.25, "experienced": 0.1},
        "mitigation": "修复 prompt 中要求 Developer 逐条回应每个 Review 问题；"
                      "Reviewer 使用量化评分而非定性描述",
    },
    {
        "id": "skip_walkthrough",
        "name": "跳过设计串讲直接开发",
        "severity": "HIGH",
        "affected_steps": ["step_2.5"],
        "applicable_plugins": ["ops-direct-invoke", "catlass-op-generator"],
        "description": "开发者认为设计方案已经足够好，跳过 Step 2.5 设计串讲直接进入开发，"
                       "导致设计中的 API 可行性问题在编码阶段才发现。",
        "impact": -0.20,
        "persona_susceptibility": {"novice": 0.5, "intermediate": 0.35, "experienced": 0.15},
        "mitigation": "将 WALKTHROUGH.md 作为 Step 3 的强制前置条件",
    },
    {
        "id": "wrong_chip_target",
        "name": "芯片型号配置错误",
        "severity": "HIGH",
        "affected_steps": ["step_1", "step_3"],
        "applicable_plugins": ["ops-direct-invoke", "catlass-op-generator",
                               "ops-registry-invoke", "triton-op-generator"],
        "description": "骨架模板默认 ascend910b，开发者未修改为目标芯片（如 ascend950），"
                       "导致编译产物在目标设备上无法运行。",
        "impact": -0.20,
        "persona_susceptibility": {"novice": 0.5, "intermediate": 0.2, "experienced": 0.05},
        "mitigation": "Step 1 环境检查脚本自动检测芯片型号并提示；"
                      "CMake 模板参数化 ASCEND_COMPUTE_UNIT",
    },
    {
        "id": "tiling_param_mismatch",
        "name": "Tiling 参数与 Kernel Buffer 不匹配",
        "severity": "CRITICAL",
        "affected_steps": ["step_3", "step_4"],
        "applicable_plugins": ["ops-direct-invoke", "ops-registry-invoke"],
        "description": "OP_CALC_TENSOR_NUM / OP_MASK_NUM 与 Kernel 中实际 TBuf 数量不一致，"
                       "导致运行时内存越界。这是最常见的运行时 Bug 之一。",
        "impact": -0.25,
        "persona_susceptibility": {"novice": 0.5, "intermediate": 0.3, "experienced": 0.1},
        "mitigation": "Review 检查清单增加 Tiling 参数同步检查项；"
                      "在代码注释中标注 TBuf 数量便于对照",
    },
    {
        "id": "missing_precision_guard",
        "name": "缺少精度保护（除零/溢出）",
        "severity": "MEDIUM",
        "affected_steps": ["step_3", "step_4"],
        "applicable_plugins": ["ops-direct-invoke", "catlass-op-generator"],
        "description": "Kernel 代码中缺少除零保护、FP16 溢出保护等精度守卫，"
                       "导致特殊值输入时产生 NaN/Inf。",
        "impact": -0.15,
        "persona_susceptibility": {"novice": 0.4, "intermediate": 0.2, "experienced": 0.1},
        "mitigation": "ascendc-api-best-practices skill 中增加精度守卫模板；"
                      "Reviewer checklist 增加精度检查项",
    },
    {
        "id": "incomplete_test_coverage",
        "name": "测试用例覆盖不完整",
        "severity": "MEDIUM",
        "affected_steps": ["step_3"],
        "applicable_plugins": ["ALL"],
        "description": "测试只覆盖了主路径，缺少边界值、特殊值（NaN/Inf/空tensor）、"
                       "混合精度等场景，导致线上运行时出现未预期的精度问题。",
        "impact": -0.15,
        "persona_susceptibility": {"novice": 0.5, "intermediate": 0.3, "experienced": 0.1},
        "mitigation": "使用 ascendc-ut-develop / ascendc-st-design skill "
                      "自动生成测试用例矩阵",
    },
    {
        "id": "doc_not_updated_after_fix",
        "name": "代码修复后未同步更新文档",
        "severity": "LOW",
        "affected_steps": ["step_5", "step_6"],
        "applicable_plugins": ["ALL"],
        "description": "修复循环中修改了代码逻辑，但 DESIGN.md / PLAN.md 未同步更新，"
                       "导致文档与实际实现不一致。",
        "impact": -0.10,
        "persona_susceptibility": {"novice": 0.4, "intermediate": 0.3, "experienced": 0.15},
        "mitigation": "Step 5 修复 prompt 中明确要求同步更新相关文档",
    },
    {
        "id": "perf_no_baseline",
        "name": "性能验收缺少基线对比",
        "severity": "LOW",
        "affected_steps": ["step_6"],
        "applicable_plugins": ["ops-direct-invoke", "catlass-op-generator",
                               "ops-registry-invoke"],
        "description": "性能验收时只看绝对延迟，没有与基线实现（TBE/手写算子）对比，"
                       "无法判断性能是否达标。",
        "impact": -0.10,
        "persona_susceptibility": {"novice": 0.5, "intermediate": 0.3, "experienced": 0.1},
        "mitigation": "Step 6 prompt 中要求明确性能目标和对比基线",
    },
    {
        "id": "skill_not_loaded_at_right_time",
        "name": "Skill 在错误的阶段加载或未加载",
        "severity": "MEDIUM",
        "affected_steps": ["step_2", "step_3", "step_4"],
        "applicable_plugins": ["ALL"],
        "description": "某些 Skill（如 ascendc-api-best-practices）在开发阶段应该加载，"
                       "但由于 init.sh 的全局安装策略，Skill 在所有阶段都可见，"
                       "Agent 未在正确的步骤中主动调用它们。",
        "impact": -0.15,
        "persona_susceptibility": {"novice": 0.4, "intermediate": 0.2, "experienced": 0.05},
        "mitigation": "每个 Step 的 prompt 中明确列出「必读 Skill」和调用时机",
    },
]


def get_antipatterns_for_step(step_id: str, plugin_id: str = None) -> list:
    """获取适用于指定步骤的反模式"""
    result = []
    for ap in ANTIPATTERNS:
        if step_id in ap["affected_steps"]:
            if ap["applicable_plugins"] == ["ALL"] or \
               plugin_id in ap["applicable_plugins"]:
                result.append(ap)
    return result


def get_antipatterns_for_plugin(plugin_id: str) -> list:
    """获取适用于指定插件的所有反模式"""
    result = []
    for ap in ANTIPATTERNS:
        if ap["applicable_plugins"] == ["ALL"] or \
               plugin_id in ap["applicable_plugins"]:
            result.append(ap)
    return result


def get_all_antipatterns() -> list:
    """返回全部反模式"""
    return ANTIPATTERNS
