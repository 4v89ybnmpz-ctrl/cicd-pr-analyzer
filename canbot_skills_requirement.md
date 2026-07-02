# CANNBot Skills 端到端质量验收平台 — 需求文档

## 1. 项目背景

### 1.1 现状

CANNBot Skills 是面向昇腾 NPU 开发的 AI 编程辅助知识库，通过安装脚本（`init.sh`）将 Skills 和 Agents 部署到 Claude Code / OpenCode / Trae / Cursor 等 AI 编程工具中。用户在 AI 编程工具中描述需求，工具读取已安装的 Skills 和 Agents，按工作流自动完成算子开发。

当前 cicd-pr-analyzer 项目中已有"工作流仿真"功能，但它是**独立的 LLM 角色扮演**——后端自己调一个 LLM 来假装走流程，与真实使用场景脱节。

### 1.2 问题

- 仿真使用独立的 LLM API 调用，不走 Claude Code + cannbot-skills 的真实链路
- 无法验证 Skills 安装后 AI 编程工具的实际表现
- 无法测试 PR → CI/CD 流水线 → 错误修复的完整闭环
- 仿真结果与真实开发者体验差距大

### 1.3 目标

构建一个**端到端质量验收平台**，驱动本地的 Claude Code CLI + GLM-5.1 模型 + cannbot-skills 插件，按真实工作流执行完整的算子开发流程，包括：

1. 遵循插件中 workflow（AGENTS.md / task-prompts.md）的具体要求完成算子开发全流程
2. 提交 PR → 触发线上 CI/CD 流水线
3. 读取流水线错误日志 → 自动修复 → 再次提交
4. 多轮修复直到流水线通过或达到修复上限

### 1.4 约束

- 本地**没有 NPU 环境**，编译和运行依赖线上 CI/CD 流水线
- AI 编程工具为 **Claude Code CLI**（`claude` 命令），模型为 **GLM-5.1**（通过 settings.json 配置的代理地址接入）
- 目标代码仓库托管在 **GitCode**（https://gitcode.com）

---

## 2. 端到端流程（举例说明）

### 2.1 真实使用场景

目标：为 [cann/ops-math](https://atomgit.com/cann/ops-math) 项目添加新算子 —— "指数缩放第一类修正贝塞尔函数 I₁(x)·exp(-|x|) 的 AscendC 实现"

### 2.2 完整流程

```
┌─ 前置准备（用户手动或自动化）────────────────────────────────┐
│                                                               │
│  ① Fork 目标仓库                                              │
│     atomgit.com/cann/ops-math                                │
│     → gitcode.com/{my_account}/ops-math                      │
│                                                               │
│  ② Clone fork 的仓库到本地                                    │
│     git clone https://gitcode.com/{my_account}/ops-math.git  │
│     cd ops-math                                               │
│                                                               │
│  ③ 新建开发分支                                               │
│     git checkout -b feature/scaled-bessel-i1                 │
│                                                               │
│  ④ 安装 cannbot-skills 插件到项目级别                         │
│     cd /path/to/cannbot-skills/plugins-official/ops-direct-invoke│
│     bash init.sh project claude                               │
│     # 安装结果：ops-math/.claude/skills/ 和 .claude/agents/  │
│                                                               │
└───────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─ Step A: 启动 Claude Code 输入需求 ──────────────────────────┐
│                                                               │
│  用户在 ops-math 目录下启动 Claude Code：                     │
│    $ claude                                                   │
│    > 指数缩放第一类修正贝塞尔函数 I₁(x)·exp(-|x|) 的 AscendC│
│      实现                                                     │
│                                                               │
│  Claude Code 自动读取 .claude/ 下的 CLAUDE.md（即 CANNBot    │
│  AGENTS.md），识别自己是 CANNBot 主 Agent，开始按 workflow    │
│  调度 Subagent。                                              │
│                                                               │
└───────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─ Step B: CANNBot 工作流执行（Claude Code 内部自动调度）──────┐
│                                                               │
│  Claude Code 读取已安装的插件 AGENTS.md 和 task-prompts.md， │
│  按其中定义的 workflow 自动调度 Subagent 完成全流程。          │
│  具体步骤、门禁规则、产出物要求等均遵循插件 workflow 定义，    │
│  仿真引擎不干预也不内联这些细节。                              │
│                                                               │
│  预期产出（因插件而异，以下为常见产出物示例）：                │
│  → 环境检查报告                                                │
│  → 设计文档 + 计划文档                                         │
│  → 设计串讲记录                                                │
│  → 算子源代码文件                                              │
│  → 代码审查报告                                                │
│  → 性能数据（需 NPU 环境）                                    │
│                                                               │
└───────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─ Step C: 代码提交与 PR ──────────────────────────────────────┐
│                                                               │
│  C1. 提交代码到 fork 仓库                                     │
│      git add operators/ScaledBesselI1/                        │
│      git commit -m "feat: 指数缩放第一类修正贝塞尔函数"       │
│      git push origin feature/scaled-bessel-i1                 │
│                                                               │
│  C2. 调用 GitCode API 向上游仓库提交 MR                       │
│      POST /api/v4/projects/{cann_ops_math_id}/merge_requests │
│      source_branch: feature/scaled-bessel-i1                 │
│      target_branch: master                                    │
│      target_project_id: cann/ops-math                        │
│                                                               │
└───────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─ Step D: 触发第三方 CI/CD 流水线 ────────────────────────────┐
│                                                               │
│  D1. 在 MR 评论区输入 "compile"                               │
│      POST /api/v4/projects/{id}/merge_requests/{iid}/notes   │
│      body: "compile"                                          │
│                                                               │
│  D2. 第三方 CI/CD 平台监听评论，触发编译+测试流水线           │
│      （非 GitCode 官方 CI/CD，是外部平台）                    │
│                                                               │
│  D3. 流水线完成后，结果回写到 MR 评论区                       │
│      评论格式示例：                                            │
│      ✅ Pipeline passed: 编译通过, UT通过, 精度通过           │
│      或                                                       │
│      ❌ Pipeline failed:                                      │
│         - 编译错误: [日志链接]                                 │
│         - UT 失败: [日志链接]                                  │
│                                                               │
│  D4. 通过 API 轮询 MR 评论，解析流水线结果                    │
│      GET /api/v4/projects/{id}/merge_requests/{iid}/notes    │
│      → 查找包含 Pipeline passed/failed 的评论                │
│      → 提取日志链接                                           │
│                                                               │
└───────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─ Step E: 流水线失败时的自动修复循环 ─────────────────────────┐
│                                                               │
│  E1. 解析失败评论中的日志链接                                 │
│      → 下载/抓取日志内容                                      │
│      → 识别错误类型（编译错误 / UT失败 / 精度不达标）        │
│                                                               │
│  E2. 调用 Claude Code 修复                                    │
│      claude -p "CI/CD 流水线失败，错误日志如下：{logs}       │
│             请修复 operators/ScaledBesselI1/ 下的代码"        │
│                                                               │
│  E3. 修复后提交并推送                                         │
│      git add -u && git commit -m "fix: 修复 CI 编译错误"      │
│      git push origin feature/scaled-bessel-i1                 │
│                                                               │
│  E4. 再次在 MR 评论区输入 "compile" 触发新流水线             │
│                                                               │
│  E5. 等待流水线结果，重复 E1-E4 直到：                       │
│      - 流水线全部通过 ✅                                      │
│      - 或达到修复上限（建议 5 轮）                            │
│                                                               │
└───────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─ Step F: 验收报告 ──────────────────────────────────────────┐
│                                                               │
│  汇总全流程数据：                                              │
│  - 工作流各步骤完成情况 + 门禁结果                            │
│  - 代码审查评分 + 修复轮次                                    │
│  - CI/CD 流水线各轮结果                                       │
│  - Token 消耗 + 成本                                          │
│  - Skill 实际利用率                                            │
│  - 最终判定：PASS / PASS_WITH_ISSUES / FAIL                  │
│                                                               │
└───────────────────────────────────────────────────────────────┘
```

### 2.3 关键交互节点

| 节点 | 触发方式 | 涉及 API |
|------|---------|---------|
| Fork 仓库 | GitCode Web UI 或 API | `POST /projects/{id}/fork` |
| Clone + 分支 | `git clone` + `git checkout -b` | Git CLI |
| 安装 Skills | `bash init.sh project claude` | Shell 脚本 |
| 启动 Claude Code | 用户在终端运行 `claude` | Claude Code CLI |
| 工作流调度 | Claude Code 内部读取 AGENTS.md | 文件系统 + Claude Code Agent 机制 |
| 提交 PR | `git push` + GitCode API | `POST /projects/{id}/merge_requests` |
| 触发流水线 | MR 评论 "compile" | `POST /projects/{id}/merge_requests/{iid}/notes` |
| 获取流水线结果 | 轮询 MR 评论 | `GET /projects/{id}/merge_requests/{iid}/notes` |
| 获取错误日志 | 抓取评论中的日志链接 | HTTP GET 日志 URL |
| 修复代码 | Claude Code CLI | `claude -p "修复 CI 错误..."` |
| 重新触发 | `git push` + 评论 "compile" | Git CLI + GitCode API |

### 2.4 CI/CD 流水线特殊性

与 GitCode 官方 CI/CD 不同，cann/ops-math 项目使用的是**第三方 CI/CD 平台**：

- **不通过** `.gitlab-ci.yml` 或 `Jenkinsfile` 触发
- **通过 MR 评论** "compile" 触发
- **结果不回写到** pipeline API，而是**回写到 MR 评论区**
- **日志不通过** Job API 获取，而是**通过评论中的外部链接**访问

这意味着仿真引擎需要：
1. **评论解析器** — 从 MR 评论中识别流水线结果（正则匹配 `✅ Pipeline passed` / `❌ Pipeline failed`）
2. **日志抓取器** — 从评论中提取外部日志 URL 并下载内容
3. **错误分类器** — 将日志内容分类为编译错误 / UT 失败 / 精度不达标 / 性能不达标
4. **评论触发器** — 每次修复后自动发送 "compile" 评论

## 3. 核心需求

### 3.1 驱动 Claude Code CLI 执行工作流

#### 3.1.1 CLI 调用方式

Claude Code CLI 支持非交互模式：

```bash
claude -p "你的 prompt" \
  --output-format stream-json \
  --dangerously-skip-permissions \
  --add-dir /path/to/project
```

后端通过 `subprocess` 调用 `claude -p` 并监听 `stream-json` 输出，实现逐步驱动。

#### 3.1.2 工作流步骤映射

每个插件定义了自己的 workflow（步骤、prompt 模板、门禁规则、Subagent 职责），存储在插件的 `AGENTS.md` 和 `workflows/task-prompts.md` 中。仿真引擎**读取插件 workflow 定义**，按其中描述的步骤依次调用 Claude Code CLI，不自行构造 prompt 内容。

具体步骤数量、名称、Subagent 调度方式因插件而异，仿真引擎通过解析插件 workflow 定义文件动态适配，而非硬编码步骤表。

#### 3.1.3 门禁检查

每个步骤完成后，后端根据插件 workflow 定义中声明的期望产出物，检查文件是否存在且内容合法。门禁规则同样从插件定义中读取，而非硬编码。

门禁未通过时，根据插件 workflow 中定义的策略决定：重试当前步骤、回退到上一步、或终止并上报。

#### 3.1.4 步骤间上下文传递

真实场景中，每个步骤的 Claude Code 调用是独立的进程，但**共享同一个文件系统**。上下文传递通过文件实现——每个步骤读取前序步骤产出的文件作为输入。

这是 cannbot-skills 工作流设计的核心机制——**文件系统即上下文总线**。仿真引擎需要尊重这个机制，不在 prompt 中内联上一步的文件内容。

---

### 3.2 PR 提交与第三方 CI/CD 流水线集成

#### 3.2.1 自动创建 PR

开发完成并通过本地审查后，仿真引擎自动执行：

```bash
# 1. 创建分支
git checkout -b feature/{operator_name}-v{version}

# 2. 提交代码
git add operators/{operator_name}/
git commit -m "feat: {operator_name} 算子实现"

# 3. 推送并创建 PR
git push origin feature/{operator_name}-v{version}
# 调用 GitCode API 创建 MR
```

#### 3.2.2 触发与监听第三方 CI/CD 流水线

CI/CD 通过 **MR 评论触发**（非 GitCode 官方 pipeline API）：

1. **触发**：向 MR 评论区发送 `"compile"`
2. **监听**：轮询 MR 评论列表，查找包含流水线结果的评论
3. **解析**：从评论内容中提取通过/失败状态和日志链接
4. **日志获取**：抓取评论中嵌入的外部日志 URL

```
评论 "compile" → 第三方平台触发 → 编译 + 测试 → 结果回写 MR 评论
```

#### 3.2.3 流水线失败处理

当流水线失败时：

1. **获取错误日志** — 从 MR 评论中提取外部日志 URL 并下载内容
2. **解析错误类型** — 编译错误 / UT 失败 / 精度不达标 / 性能不达标
3. **构造修复 prompt** — 将错误日志 + 相关源码片段 + 设计文档注入 prompt
4. **调用 Claude Code 修复** — `claude -p "以下是 CI/CD 流水线的错误日志，请修复：{logs}"`
5. **提交修复** — `git commit --amend` 或新的 commit，推送并等待流水线重新触发
6. **循环直到通过或达到修复上限**（建议上限 5 轮）

---

### 3.3 前端实时展示

#### 3.3.1 SSE 实时推送

后端通过 SSE 推送每一步的执行状态：

```
event: step_start
data: {"step_id": "step_2_design", "step_name": "设计", "status": "running"}

event: claude_output
data: {"step_id": "step_2_design", "type": "text", "content": "正在分析 API..."}

event: gate_check
data: {"step_id": "step_2_design", "passed": true, "artifacts": ["..."]}

event: step_done
data: {"step_id": "step_2_design", "status": "passed", "duration_ms": 45000}
```

#### 3.3.2 流水线状态展示

PR 创建后，前端实时展示 CI/CD 流水线各阶段状态：

```
编译 ─── 单元测试 ─── 集成测试 ─── 精度测试 ─── 性能测试
 ✅        ✅         ❌          ⏳          ⏳
```

失败阶段点击展开错误日志。

#### 3.3.3 修复循环可视化

展示修复轮次历史：

```
轮次 1: 编译失败 → 修复 → 重新提交
轮次 2: 精度不达标 → 修复 → 重新提交  
轮次 3: 全部通过 ✅
```

---

### 3.4 仿真断点分析与质量监控（核心价值）

本节定义仿真过程中**实时**和**事后**两个层面的质量监控能力。这是平台区别于"单纯跑通流程"的核心价值——不仅要跑完，还要知道跑的过程中哪里出了问题、skill 体系哪里有缺口。

#### 3.4.1 Skill 遵从度监控（断点类型 A）

**问题**：Claude Code + LLM 可能绕过 skill 约束，自行做出本应由 skill/agent 控制的决策。

**检测机制**：解析 Claude Code 的 stream-json 输出，识别工具调用行为（`tool_use` 事件），与 skill 定义的预期行为做实时比对。

| 监控项 | 检测方法 | 断点等级 |
|--------|---------|---------|
| **Skill 文件引用** | 统计 Claude Code 是否读取了 `.claude/skills/` 和 `.claude/agents/` 下的文件 | 若某步骤完全未引用 skill 文件 → HIGH |
| **Agent 调用遵从** | 检测是否按插件 workflow 定义的 `subagent_type` 调用对应 Agent，而非用 `general` 类型绕过 | 调用了未定义的 agent 类型 → HIGH |
| **Prompt 模板遵从** | 检测发送给 Claude Code 的 prompt 是否来自 `task-prompts.md`，还是 LLM 自行构造 | prompt 不含模板标识 → MED |
| **Subagent 职责越界** | 检测 Subagent 是否执行了插件 workflow 中其他角色的职责（如开发步骤自行修改了设计文档） | 跨角色行为 → HIGH |
| **外部知识引入** | LLM 使用了 skill 体系外的知识（如直接引用未安装的 API 文档）做关键决策 | 引用非 skill 来源 → MED |
| **门禁跳过** | 步骤未产出插件 workflow 定义的产出物，却进入下一步 | 缺少产出物 → CRITICAL |

**实时展示**：前端每个工作流步骤节点旁显示 Skill 遵从度指示器：

```
[步骤 A] ───────────────────── ✅ 遵从度: 100%
  ✅ 读取了插件定义的 Agent 配置
  ✅ 引用了预期 skill 文件
  ✅ prompt 来自插件 task-prompts.md 模板

[步骤 B] ───────────────────── ⚠️ 遵从度: 70%
  ✅ 读取了插件定义的 Agent 配置
  ⚠️ 未引用某预期 skill（插件定义中声明应使用）
  ❌ 自行构造了关键参数（应从前序步骤产出物中读取）
```

**SSE 事件**：

```
event: skill_compliance
data: {
  "step_id": "step_3_develop",
  "compliance_score": 0.7,
  "skills_referenced": ["..."],
  "skills_expected_but_missing": ["..."],
  "violations": [
    {"type": "SELF_DECISION", "detail": "..."}
  ]
}
```

#### 3.4.2 流程断点与 Skill 覆盖度分析（断点类型 B）

**问题**：仿真全流程中，有些环节（如提交 PR、触发 CI/CD、解析流水线错误、修复循环）可能没有对应的 skill/agent 来控制，需要靠仿真引擎本身或人工干预。

**分析维度**：对仿真流程中的每个操作节点，判定其**控制来源**：

| 操作节点 | 是否有 skill/agent 控制？ | 控制来源 |
|---------|------------------------|---------|
| **插件 workflow 定义的全部步骤** | ✅ 有 | 插件 AGENTS.md + task-prompts.md 定义的步骤和 Subagent |
| **提交 PR** | ❓ 无 | 无 skill 控制，需仿真引擎实现 |
| **触发 CI/CD（评论 "compile"）** | ❓ 无 | 无 skill 控制，需仿真引擎实现 |
| **解析流水线结果** | ❓ 无 | 无 skill 控制，需仿真引擎实现 |
| **抓取错误日志** | ❓ 无 | 无 skill 控制，需仿真引擎实现 |
| **CI 修复循环** | ⚠️ 部分 | 可复用插件中的开发 Agent，但无专用 skill |
| **验收报告生成** | ❓ 无 | 无 skill 控制，需仿真引擎实现 |

> 注：插件 workflow 定义的步骤数量和名称因插件而异（如 ops-direct-invoke 有 7 个步骤，ops-registry-invoke 有不同的阶段划分），仿真引擎从插件定义文件中动态解析。

**输出格式**：仿真报告中生成"Skill 覆盖度热力图"：

```
─────────────────────────────────────────────────────
  Skill 覆盖度分析
─────────────────────────────────────────────────────
  [插件 workflow 步骤]  ██████████ 100%  ✅ 由插件 skill/agent 控制
  [插件 workflow 步骤]  ██████████ 100%  ✅ 由插件 skill/agent 控制
  ...（具体步骤名称从插件 workflow 定义中动态读取）
  ─────────────────────────────────────
  提交 PR             ░░░░░░░░░░   0%  ❌ 无 skill
  触发 CI/CD          ░░░░░░░░░░   0%  ❌ 无 skill
  解析流水线结果       ░░░░░░░░░░   0%  ❌ 无 skill
  抓取错误日志         ░░░░░░░░░░   0%  ❌ 无 skill
  CI 修复循环          ███░░░░░░░  30%  ⚠️ 可复用插件中的开发 Agent
  验收报告             ░░░░░░░░░░   0%  ❌ 无 skill
─────────────────────────────────────────────────────
  总覆盖度: N/M 节点 = XX%
  建议: 补充 CI/CD 集成 skill 和 验收报告 skill
```

**用途**：帮助 skill 维护者识别功能缺口，决定是将缺失能力开发为新 skill，还是作为仿真引擎内置能力。

#### 3.4.3 实时断点识别（断点类型 C）

**问题**：不应等仿真全部跑完才发现问题，应在仿真过程中实时识别异常。

**实时监控规则**：

| 规则 | 触发条件 | 告警等级 | 前端展示 |
|------|---------|---------|---------|
| **步骤超时** | 单步执行超过阈值（默认 10 分钟） | HIGH | 步骤节点变红 + 倒计时 |
| **LLM 输出截断** | Claude Code 输出不完整（如 `stream-json` 中无 `result` 事件） | HIGH | 终端面板显示截断警告 |
| **产出物缺失** | 步骤完成后，插件 workflow 定义的产出文件不存在 | CRITICAL | 步骤节点显示 ❌ + 缺失文件列表 |
| **Skill 未加载** | Claude Code 启动后未读取 `.claude/` 目录下的任何配置 | CRITICAL | 流程顶部红色横幅 |
| **Agent 调用异常** | 实际调用的 Agent 类型与插件 workflow 定义不匹配 | HIGH | 步骤节点显示 ⚠️ + 偏差描述 |
| **修复循环不收敛** | 同一错误连续 2 轮未修复 | MED | 修复轮次面板高亮 |
| **CI/CD 等待超时** | 评论 "compile" 后超过 30 分钟无流水线结果 | HIGH | 流水线面板显示超时 |
| **文件系统冲突** | 多步骤写入同一文件且内容冲突 | MED | 文件变更时间线告警 |

**SSE 事件**：

```
event: breakpoint_alert
data: {
  "type": "SKILL_NOT_LOADED",
  "severity": "CRITICAL",
  "step_id": "step_1_env_check",
  "message": "Claude Code 未读取 .claude/ 目录，可能 Skills 未正确安装",
  "suggestion": "检查 init.sh 是否成功执行，确认 .claude/skills/ 目录存在"
}
```

**前端展示**：在工作流 DAG 上方增加实时告警横幅，按严重程度排列，点击可展开详情。告警不打断仿真执行，但 CRITICAL 级别提供"暂停仿真"按钮。

#### 3.4.4 仿真完整性校验（断点类型 D）

**问题**：仿真跑完不代表产物完整。需要校验所有开发产物是否符合同 agent 职责边界和完整性要求。

**校验维度**：

##### D1. 工作流完整性

| 检查项 | 校验方法 |
|--------|---------|
| 步骤完整性 | 插件 workflow 定义的全部步骤是否按序执行，无跳过 |
| 门禁通过率 | 每步门禁是否通过，未通过是否有合理的回退/重试记录 |
| 修复循环收敛 | 修复循环是否在插件定义的轮次上限内收敛 |
| 子流程覆盖 | workflow 中定义的子流程（如设计串讲）是否完整执行 |

##### D2. 开发产物完整性

| 检查维度 | 校验方法 |
|---------|---------|
| 产物存在性 | 插件 workflow 中声明的全部产出物文件是否存在 |
| 产物归属 | 每个产出物是否由 workflow 中定义的对应 Subagent 产出 |
| 产物合法性 | 产出物内容是否符合插件定义的格式要求（如 DESIGN.md 的覆盖维度、REVIEW.md 的评分格式） |

> 具体的产物清单（如 DESIGN.md、PLAN.md、op_kernel/*.asc 等）因插件而异，从插件 workflow 定义中动态读取。

##### D3. Agent 职责边界合规

| 检查维度 | 校验方法 |
|---------|---------|
| Agent 产出范围 | 每个 Subagent 步骤产出的文件是否与插件定义的职责一致 |
| Agent 越界检测 | 通过 git diff 检查每个步骤是否修改了不该修改的文件（如设计步骤不应修改代码文件） |
| 主控职责 | 主控 Agent 是否直接参与了应由 Subagent 完成的工作 |

> 具体的 Agent 角色和职责边界从插件 AGENTS.md 中读取。不同插件可能有不同的 Agent 划分（如 ops-direct-invoke 有 3 个角色，ops-registry-invoke 有 4 个角色）。

##### D4. 设计-实现一致性

| 检查维度 | 校验方法 |
|---------|---------|
| API 映射落地 | 设计文档中列出的技术方案是否在源代码中被实现 |
| 策略落地 | 设计文档中定义的关键策略是否在代码中体现 |
| 数据流落地 | 设计文档中描述的数据处理流程是否与代码逻辑一致 |
| 边界场景覆盖 | 设计文档中列举的特殊场景是否有对应的代码处理 |

**校验输出**：

```
─────────────────────────────────────────────────────
  仿真完整性校验报告
─────────────────────────────────────────────────────
  D1. 工作流完整性
    ✅ 全部步骤按序执行
    ✅ 所有门禁通过
    ⚠️ 修复循环 2 轮后收敛（非 1 轮）

  D2. 产物完整性
    ✅ [产出物 1] — 存在，内容合法
    ✅ [产出物 2] — 存在，内容合法
    ❌ [产出物 3] — 缺失
    （产出物清单从插件 workflow 定义中动态读取）

  D3. 职责边界合规
    ✅ 各 Subagent 步骤未越界
    ❌ [某步骤] 中 [Agent] 修改了不应修改的文件
       → 建议: 应由 [对应 Agent] 负责

  D4. 设计-实现一致性
    ✅ 技术方案: 实现与设计一致
    ⚠️ 数据流: 主路径一致，但缺少边界场景处理
    （一致性校验从设计文档中提取关键承诺，在代码中逐一验证）
─────────────────────────────────────────────────────
```

---

### 3.5 验收报告

全流程完成后生成验收报告，涵盖以下维度：

| 维度 | 内容 | 来源 |
|------|------|------|
| 工作流完整性 | 每个步骤是否按序完成、门禁是否通过 | D1 校验结果 |
| 设计质量 | 设计文档的覆盖度（从设计文档中提取关键承诺维度） | D4 校验结果 |
| 代码质量 | 代码审查评分、问题数、修复轮次 | 审查报告 |
| Skill 遵从度 | 各步骤的 skill 引用率、agent 调用合规性 | 断点类型 A |
| Skill 覆盖度 | 仿真全流程中哪些环节有/无 skill 控制 | 断点类型 B |
| 实时断点 | 仿真过程中的异常事件汇总 | 断点类型 C |
| 产物完整性 | 所有期望产物是否存在且内容合法 | 断点类型 D2 |
| 职责边界合规 | 各 Agent 是否严格遵守职责边界 | 断点类型 D3 |
| 设计-实现一致性 | 设计文档与代码实现的对应关系 | 断点类型 D4 |
| CI/CD 结果 | 编译/测试/精度/性能各阶段结果 | 流水线评论解析 |
| 修复效率 | 总修复轮次、平均修复耗时、错误类型分布 | 修复循环记录 |
| Token 消耗 | 各步骤 token 用量、总成本 | Claude Code 输出 |
| 总评 | PASS / PASS_WITH_ISSUES / FAIL | 综合判定 |

---

## 4. 技术方案

### 4.1 架构

```
┌──────────────────────────────────────────────────────────────┐
│                       前端 (React)                             │
│  工作流面板 │ 断点告警 │ Skill覆盖度 │ CI/CD │ 验收报告        │
└───────────────────────────┬──────────────────────────────────┘
                            │ SSE / REST
┌───────────────────────────┴──────────────────────────────────┐
│                    后端 (FastAPI)                               │
│                                                                │
│  ┌───────────┐  ┌──────────────┐  ┌────────────────────────┐ │
│  │ 工作流引擎 │  │ CI/CD 集成    │  │ Claude Code CLI Driver │ │
│  │ (步骤调度  │  │ (评论触发     │  │ (subprocess            │ │
│  │  门禁检查  │  │  结果轮询     │  │  stream-json 解析)     │ │
│  │  上下文)   │  │  日志抓取)    │  └──────────┬─────────────┘ │
│  └─────┬─────┘  └──────┬───────┘             │               │
│        │               │                      │               │
│  ┌─────┴───────────────┴──────────────────────┴─────────────┐ │
│  │               断点分析引擎 (新增核心组件)                    │ │
│  │                                                            │ │
│  │  ┌──────────────┐  ┌──────────────┐  ┌─────────────────┐ │ │
│  │  │ Skill 遵从度  │  │ Skill 覆盖度  │  │ 完整性校验器     │ │ │
│  │  │ 监控器(A)     │  │ 分析器(B)     │  │ (D1-D4)         │ │ │
│  │  └──────────────┘  └──────────────┘  └─────────────────┘ │ │
│  │                                                            │ │
│  │  输入: stream-json 事件 + 文件系统快照 + AGENTS.md 规则     │ │
│  │  输出: 实时告警 SSE + 覆盖度报告 + 完整性报告                │ │
│  └────────────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────────┘
          │                │                  │
          ▼                ▼                  ▼
   ┌────────────┐   ┌───────────┐    ┌───────────────┐
   │ 文件系统    │   │ GitCode   │    │ Claude Code   │
   │ (operators/)│   │ 平台 API  │    │ CLI + GLM-5.1 │
   └────────────┘   └───────────┘    └───────────────┘
                                           │
                                    ┌──────┴──────┐
                                    │ cannbot-     │
                                    │ skills 插件  │
                                    └─────────────┘
```

### 4.2 Claude Code CLI Driver

后端通过 `asyncio.create_subprocess_exec` 调用 Claude Code CLI：

```python
async def run_claude_step(prompt: str, work_dir: str) -> AsyncGenerator:
    """调用 Claude Code CLI 执行单个步骤，yield stream-json 事件"""
    proc = await asyncio.create_subprocess_exec(
        "claude", "-p", prompt,
        "--output-format", "stream-json",
        "--dangerously-skip-permissions",
        "--add-dir", work_dir,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=work_dir,
    )
    async for line in proc.stdout:
        event = json.loads(line)
        yield event
    await proc.wait()
```

### 4.3 第三方 CI/CD 集成

cann/ops-math 项目使用**第三方 CI/CD 平台**（非 GitCode 官方 pipeline），集成方式如下：

```python
class ThirdPartyCICD:
    """第三方 CI/CD 集成 — 通过 MR 评论触发和获取结果"""

    async def trigger_pipeline(self, project_id: str, mr_iid: int):
        """在 MR 评论区发送 'compile' 触发流水线"""
        await gitcode_api.post_mr_note(
            project_id, mr_iid, body="compile"
        )

    async def poll_pipeline_result(self, project_id: str, mr_iid: int, timeout: int = 1800):
        """轮询 MR 评论，查找流水线结果"""
        while elapsed < timeout:
            notes = await gitcode_api.get_mr_notes(project_id, mr_iid)
            for note in reversed(notes):  # 从最新评论开始查找
                if "Pipeline passed" in note["body"]:
                    return PipelineResult(status="success")
                if "Pipeline failed" in note["body"]:
                    log_urls = extract_log_urls(note["body"])
                    return PipelineResult(status="failed", log_urls=log_urls)
            await asyncio.sleep(30)

    async def fetch_error_logs(self, log_urls: List[str]) -> str:
        """抓取评论中的外部日志链接内容"""
        logs = []
        for url in log_urls:
            resp = await http_client.get(url)
            logs.append(resp.text)
        return "\n".join(logs)
```

关键 API 调用：

- **触发流水线**: `POST /api/v4/projects/{id}/merge_requests/{iid}/notes`（body: `"compile"`）
- **获取流水线结果**: `GET /api/v4/projects/{id}/merge_requests/{iid}/notes`（解析评论内容）
- **获取错误日志**: HTTP GET 评论中嵌入的外部日志 URL

### 4.4 数据模型

```python
class SimulationSession(BaseModel):
    session_id: str
    plugin_id: str               # e.g. "ops-direct-invoke"
    operator_name: str           # e.g. "Abs"
    persona: str                 # novice / intermediate / experienced
    status: str                  # running / completed / failed
    
    steps: List[StepExecution]   # 各步骤执行记录
    pipeline_runs: List[PipelineRun]  # CI/CD 流水线记录
    fix_rounds: List[FixRound]   # 修复循环记录
    
    report: Optional[SessionReport]  # 最终验收报告
    created_at: str

class StepExecution(BaseModel):
    step_id: str
    step_name: str
    status: str                  # pending / running / passed / failed / skipped
    prompt: str                  # 发送给 Claude Code 的 prompt
    output: str                  # Claude Code 的完整输出
    artifacts: List[str]         # 产出的文件列表
    gate_passed: bool            # 门禁是否通过
    duration_ms: int
    token_usage: Dict[str, int]

    # 断点分析字段
    skill_compliance: SkillCompliance   # Skill 遵从度（断点 A）
    breakpoint_alerts: List[BreakpointAlert]  # 实时断点告警（断点 C）

class SkillCompliance(BaseModel):
    """断点 A: Skill 遵从度"""
    score: float                          # 0-1
    skills_referenced: List[str]          # 实际引用的 skill 文件
    skills_expected: List[str]            # AGENTS.md 预期应引用的 skill
    skills_missing: List[str]             # 预期但未引用
    agent_called: Optional[str]           # 实际调用的 agent 类型
    agent_expected: Optional[str]         # 预期调用的 agent 类型
    violations: List[ComplianceViolation] # 违规列表

class ComplianceViolation(BaseModel):
    type: str              # SELF_DECISION / WRONG_AGENT / SKILL_MISSING / PROMPT_TEMPLATE_MISSING
    detail: str
    severity: str          # HIGH / MED / LOW

class BreakpointAlert(BaseModel):
    """断点 C: 实时告警"""
    type: str              # SKILL_NOT_LOADED / STEP_TIMEOUT / ARTIFACT_MISSING / ...
    severity: str          # CRITICAL / HIGH / MED
    message: str
    suggestion: str
    detected_at: str       # ISO timestamp

class PipelineRun(BaseModel):
    pipeline_id: str
    mr_iid: int
    status: str                  # running / success / failed
    stages: List[PipelineStage]
    triggered_at: str

class PipelineStage(BaseModel):
    name: str                    # 编译 / 单元测试 / 精度测试 ...
    status: str
    job_id: Optional[str]
    log: Optional[str]          # 失败时的日志

class FixRound(BaseModel):
    round_number: int
    error_type: str              # compile_error / runtime_error / precision_fail / perf_fail
    error_log: str
    fix_prompt: str
    fix_commit: str
    pipeline_after_fix: Optional[PipelineRun]

class SessionReport(BaseModel):
    verdict: str                 # PASS / PASS_WITH_ISSUES / FAIL
    workflow_completeness: float  # 0-1
    design_quality: Dict
    code_review_score: int       # 0-100
    ci_cd_result: str
    total_fix_rounds: int
    total_duration_ms: int
    total_tokens: int

    # 断点分析汇总
    skill_compliance_summary: SkillComplianceSummary   # 断点 A 汇总
    skill_coverage: SkillCoverageReport                 # 断点 B: Skill 覆盖度
    breakpoint_summary: BreakpointSummary               # 断点 C: 告警汇总
    integrity_check: IntegrityCheckReport               # 断点 D: 完整性校验

class SkillComplianceSummary(BaseModel):
    """断点 A 汇总"""
    overall_score: float                       # 所有步骤的平均遵从度
    steps_with_violations: List[str]           # 有违规的步骤 ID
    violation_count_by_type: Dict[str, int]    # 按类型统计违规数
    skills_utilized: List[str]                 # 实际使用的 skill
    skills_unused: List[str]                   # 已安装但未使用的 skill

class SkillCoverageReport(BaseModel):
    """断点 B: Skill 覆盖度"""
    total_nodes: int                           # 仿真流程总操作节点数
    covered_nodes: int                         # 有 skill/agent 控制的节点数
    coverage_rate: float                       # 0-1
    uncovered_nodes: List[UncoveredNode]       # 无 skill 控制的节点
    partial_nodes: List[PartialCoveredNode]    # 部分 skill 覆盖的节点

class UncoveredNode(BaseModel):
    node_name: str
    description: str
    current_controller: str                    # "仿真引擎" / "人工干预"

class PartialCoveredNode(BaseModel):
    node_name: str
    covered_by: str                            # 可部分复用的 agent
    missing_capability: str                    # 缺失的能力描述

class BreakpointSummary(BaseModel):
    """断点 C: 告警汇总"""
    total_alerts: int
    critical_count: int
    high_count: int
    med_count: int
    alerts_by_type: Dict[str, int]             # 按类型统计

class IntegrityCheckReport(BaseModel):
    """断点 D: 完整性校验"""
    workflow_integrity: WorkflowIntegrityResult       # D1
    artifact_integrity: ArtifactIntegrityResult       # D2
    responsibility_compliance: ResponsibilityResult   # D3
    design_consistency: DesignConsistencyResult       # D4

class WorkflowIntegrityResult(BaseModel):
    all_steps_executed: bool
    all_gates_passed: bool
    fix_loop_converged: bool
    walkthrough_completed: bool
    issues: List[str]

class ArtifactIntegrityResult(BaseModel):
    artifacts: List[ArtifactCheck]
    all_present: bool
    all_valid: bool

class ArtifactCheck(BaseModel):
    name: str                 # e.g. "DESIGN.md"
    exists: bool
    valid: bool
    responsible_agent: str    # e.g. "Architect"
    issues: List[str]

class ResponsibilityResult(BaseModel):
    violations: List[ResponsibilityViolation]
    compliant: bool

class ResponsibilityViolation(BaseModel):
    agent: str                # e.g. "Developer"
    step_id: str
    action: str               # e.g. "修改了 DESIGN.md"
    expected_behavior: str    # e.g. "应由 Architect 负责设计文档更新"

class DesignConsistencyResult(BaseModel):
    api_mapping_score: float           # 0-1
    tiling_strategy_score: float
    data_flow_score: float
    branch_coverage_score: float
    overall_score: float
    mismatches: List[DesignMismatch]

class DesignMismatch(BaseModel):
    dimension: str            # api_mapping / tiling / data_flow / branch
    design_description: str
    actual_implementation: str
```

---

## 5. 用户故事

### US-1: 创建仿真任务

> 作为 cannbot-skills 维护者，我想选择一个 plugin 和算子名称，点击"开始端到端验收"，系统自动驱动 Claude Code 完成从环境检查到 PR 提交的全流程。

**验收标准**：
- 前端可选择 plugin（如 ops-direct-invoke）和输入算子名称（如 Abs）
- 点击后创建仿真任务，返回 session_id
- 后端按步骤依次调用 Claude Code CLI
- 前端通过 SSE 实时展示每步进展

### US-2: 实时查看 Claude Code 执行过程

> 作为验收人员，我想实时看到 Claude Code 在每个步骤中的输出（包括它调用了哪些 Skills、读了哪些文件、做了什么决策），以便判断工作流是否符合预期。

**验收标准**：
- SSE 推送 Claude Code 的 stream-json 输出
- 前端以终端风格实时滚动展示
- 每步完成后展示门禁检查结果（通过/未通过 + 原因）

### US-3: 自动提交 PR 并监控 CI/CD

> 作为验收人员，开发完成后系统自动向 GitCode 提交 PR，并监控 CI/CD 流水线状态，我不需要手动操作。

**验收标准**：
- 自动创建分支、提交代码、创建 MR
- 前端展示流水线各阶段状态（编译 → 测试 → 精度 → 性能）
- 流水线失败时自动拉取错误日志

### US-4: 自动修复 CI/CD 错误

> 作为验收人员，当流水线失败时，系统自动将错误日志发送给 Claude Code 进行修复，修复后自动提交并等待流水线重跑，最多循环 5 轮。

**验收标准**：
- 流水线失败后自动触发修复流程
- 错误日志注入修复 prompt
- 修复后自动 amend commit 并 force push（或新 commit）
- 前端展示修复轮次、每轮错误类型和修复内容
- 达到修复上限时停止并标记为 FAIL

### US-5: 查看验收报告

> 作为 cannbot-skills 维护者，仿真完成后我想看到一份完整的验收报告，包括工作流完整性、代码质量评分、CI/CD 结果、修复效率、Skill 利用率和 Token 消耗。

**验收标准**：
- 报告包含所有验收维度（见 3.4）
- 可导出为 Markdown / PDF
- 历史报告可查询和对比

### US-6: 多算子批量验收

> 作为 cannbot-skills 维护者，我想同时验收多个算子（如 Abs、Add、Relu），系统串行或并行执行，最后给出汇总报告。

**验收标准**：
- 支持选择多个算子名称
- 各算子仿真独立运行、互不干扰（工作目录隔离）
- 汇总报告展示各算子的通过/失败状态

### US-7: 实时查看 Skill 遵从度与断点告警

> 作为 cannbot-skills 维护者，我想在仿真运行过程中实时看到每个步骤是否正确使用了 skill，哪些操作绕过了 skill 体系由 LLM 自行决策，以便即时发现问题。

**验收标准**：
- 每个步骤节点实时显示 Skill 遵从度评分（0-100%）
- 违规行为（如 agent 类型不匹配、skill 未引用、prompt 非模板来源）实时高亮
- CRITICAL 级告警提供"暂停仿真"选项
- 告警不打断仿真执行（除非用户主动暂停）
- 仿真结束后可回溯所有告警的时间线

### US-8: 查看 Skill 覆盖度分析

> 作为 cannbot-skills 维护者，仿真完成后我想看到一份 Skill 覆盖度热力图，明确哪些仿真环节有对应的 skill/agent 控制，哪些环节功能缺失，以便规划 skill 开发优先级。

**验收标准**：
- 生成"Skill 覆盖度热力图"（见 3.4.2）
- 每个未覆盖节点标注当前控制来源（仿真引擎 / 人工干预）
- 对部分覆盖节点给出复用建议（如"可复用插件中的开发 Agent"）
- 覆盖度数据可跨多次仿真对比，识别 skill 补充后的改善趋势

### US-9: 仿真完整性校验

> 作为 cannbot-skills 维护者，仿真完成后我想看到一份完整性校验报告，确认所有开发产物齐全、各 agent 严格遵守职责边界、设计与实现一致。

**验收标准**：
- D1-D4 四个维度的校验结果清晰展示（见 3.4.4）
- 产物缺失或 agent 越界时标红并给出修复建议
- 设计-实现一致性校验覆盖 API 映射、Tiling 策略、数据流、分支场景
- 校验失败的维度不计入总评 PASS

---

## 6. 非功能需求

| 维度 | 要求 |
|------|------|
| **可靠性** | Claude Code CLI 调用需有超时机制（单步最长 10 分钟），超时后标记失败不阻塞后续 |
| **隔离性** | 每个仿真任务在独立的工作目录中执行（`operators/{session_id}/`），互不干扰 |
| **可恢复** | 仿真中断后可从失败的步骤恢复，不需要从头开始 |
| **安全性** | Claude Code CLI 以 `--dangerously-skip-permissions` 运行，需限制 `--add-dir` 范围 |
| **资源控制** | 限制并发仿真数量（建议最多 2 个），避免资源争抢 |
| **日志持久化** | 所有 Claude Code 输出和 CI/CD 日志保存到 MongoDB，支持回溯 |
| **Token 统计** | 记录每步 token 消耗，汇总展示总成本 |

---

## 7. 实施优先级

### P0 — 核心链路（MVP）

1. Claude Code CLI Driver — 非交互式调用 + stream-json 输出解析
2. 工作流引擎 — 步骤调度 + 门禁检查 + prompt 模板渲染
3. SSE 实时推送 — 前端展示每步执行状态
4. 文件系统门禁 — 检查插件 workflow 定义的产出物文件是否存在
5. **断点分析引擎（核心）** — Skill 遵从度监控(A) + 实时断点告警(C) + stream-json 行为解析

### P1 — CI/CD 闭环

5. GitCode MR 创建 — 自动提交 PR
6. 流水线监听 — 轮询 pipeline 状态
7. 错误日志拉取 — 获取失败 Job 的完整日志
8. 自动修复循环 — 错误日志 → Claude Code 修复 → 重新提交

### P2 — 验收报告与完整性校验

9. 验收报告生成 — 汇总所有维度数据
10. **完整性校验器** — 产物完整性(D2) + 职责边界合规(D3) + 设计实现一致性(D4)
11. **Skill 覆盖度分析器(B)** — 覆盖度热力图 + 缺口识别
12. 历史报告查询 — 按算子/时间/结果筛选
13. 导出功能 — Markdown / PDF 导出

### P3 — 批量与高级功能

12. 多算子批量验收
13. 仿真恢复（从失败步骤继续）
14. 跨 Plugin 对比报告
15. Skill 利用率热力图

---

## 8. 与现有系统的关系

| 现有模块 | 改造方向 |
|---------|---------|
| `workflow_simulator.py` | 废弃 LLM 角色扮演逻辑，改为调用 Claude Code CLI Driver |
| `workflow_parser.py` | 保留，用于解析 plugin 的步骤定义和 prompt 模板 |
| `workflow_simulation.py`（API 路由） | 改造 SSE 推送内容，增加 CI/CD 和修复循环事件 |
| `WorkflowSimPanel.jsx` | 改造 DAG 展示，增加 Skill 遵从度指示器 + 断点告警横幅 |
| `antipattern_library.py` | 保留，在验收报告中作为参考维度 |
| **新增: `breakpoint_analyzer.py`** | 断点分析引擎核心，解析 stream-json 事件，实时检测 skill 遵从度和流程断点 |
| **新增: `skill_coverage_analyzer.py`** | Skill 覆盖度分析，对比仿真全流程节点与 skill/agent 定义 |
| **新增: `integrity_checker.py`** | 完整性校验器，检查产物完整性 + 职责边界 + 设计一致性 |

---

## 9. 关键风险

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| Claude Code CLI 输出格式不稳定 | stream-json 解析失败 | 加固 JSON 解析，增加 fallback 纯文本模式 |
| GLM-5.1 模型能力不足以完成某些步骤 | 开发/修复步骤质量差 | 记录每步 LLM 输出，人工介入选项 |
| 线上 CI/CD 流水线排队时间长 | 仿真耗时过长 | 流水线等待加超时，超时后标记为 PENDING |
| GitCode API 变更 | MR 创建/流水线查询失败 | API 调用加错误重试，失败时提示人工操作 |
| 并发仿真导致文件冲突 | 多个仿真写入同一目录 | 每个仿真用独立的工作目录和 git worktree |
| Token 消耗过大 | 成本失控 | 单步 token 上限 + 总 token 上限，超限暂停 |
