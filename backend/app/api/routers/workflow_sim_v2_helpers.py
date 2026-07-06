"""工作流仿真 V2 — 通用辅助函数、Pydantic 模型、共享状态"""

import asyncio
import json
import logging
import os
from typing import Optional

from pydantic import BaseModel

from app.services.session_event_bus import SessionEventBus

logger = logging.getLogger(__name__)

_PROJECT_ROOT = os.path.dirname(
    os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    )
)
CANNBOT_PLUGINS_DIR = os.path.join(
    _PROJECT_ROOT, "external", "cannbot-skills", "plugins-official"
)

# ==================== 共享状态 ====================
_pipeline_cancel_flags: dict = {}
_npu_test_cancel_flags: dict = {}
_active_session_tasks: dict = {}
_session_event_buses: dict = {}

# ==================== 请求模型 ====================


class CreateSessionRequest(BaseModel):
    plugin_id: str
    op_name: str
    op_spec: str = ""
    work_dir: str = ""
    step_timeout: int = 0  # 0 = 不限制
    gitcode_token: str = ""
    auto_pipeline: bool = False
    repo_url: str = ""
    fork_info: Optional[dict] = None
    clone_status: str = "pending"  # pending | cloned | failed（clone 先于 session，由前端传入）


class BatchTaskSpec(BaseModel):
    plugin_id: str
    op_name: str
    op_spec: str = ""
    step_timeout: int = 0  # 0 = 不限制


class CreateBatchRequest(BaseModel):
    tasks: list[BatchTaskSpec]
    work_dir_prefix: str = "/tmp/cannbot-batch"


DEFAULT_PIPELINE_STAGES = [
    {"name": "提交代码", "key": "git_commit"},
    {"name": "推送到 Fork 仓库", "key": "git_push"},
    {"name": "向上游创建 PR", "key": "create_pr"},
    {"name": "触发编译", "key": "trigger_ci"},
    {"name": "等待 CI/CD 结果", "key": "wait_ci"},
    {"name": "分析失败原因", "key": "analyze_failure"},
    {"name": "自动修复", "key": "auto_fix"},
    {"name": "提交修复并重试", "key": "fix_commit_retry"},
]


def _make_external_step(step_id: str, step_name: str, step_category: str, step_index: int) -> dict:
    """构造一个外部生命周期步骤（clone/NPU/CI-CD），不进 Claude 执行，仅用于前端串联展示。

    step_type='external' 是 drive.py 跳过执行、前端视觉区分的标记。
    """
    return {
        "step_id": step_id,
        "step_name": step_name,
        "step_type": "external",
        "step_category": step_category,
        "step_index": step_index,
        "status": "pending",
        "prompt_template": "",
        "required_skills": [],
        "output_artifacts": [],
        "dispatch_target": None,
        "fallback": None,
        "output": "",
        "events": [],
        "duration_ms": 0,
        "gate_passed": None,
        "gate_artifacts": [],
        "skill_compliance": None,
        "token_usage": {},
        "started_at": None,
        "completed_at": None,
    }


# 外部生命周期步骤模板（clone 前置，npu/cicd 后置）
PRE_EXT_STEP_DEFS = [("ext_clone", "Clone 算子库", "clone")]
POST_EXT_STEP_DEFS = [
    ("ext_npu", "NPU 性能测试", "npu"),
    ("ext_cicd", "CI/CD 流水线", "cicd"),
]


def build_pre_external_steps(start_index: int = 0) -> list:
    """前置外部步骤（clone），插在插件开发流程之前。"""
    return [
        _make_external_step(sid, name, cat, start_index + i)
        for i, (sid, name, cat) in enumerate(PRE_EXT_STEP_DEFS)
    ]


def build_post_external_steps(start_index: int) -> list:
    """后置外部步骤（NPU/CI-CD），追加在插件开发流程之后。"""
    return [
        _make_external_step(sid, name, cat, start_index + i)
        for i, (sid, name, cat) in enumerate(POST_EXT_STEP_DEFS)
    ]


# 平台注入步骤的 prompt（不属于插件 task-prompts.md，由平台写死；drive.py 替换 {work_dir}）
PLATFORM_INSTALL_PROMPT = """你正在 {work_dir} 这个已 clone 下来的算子库工作目录中，算子名为 {op_name}。
这是仿真平台在执行插件开发流程之前注入的「安装环境」步骤。本步骤固定调用 ascendc-env-setup skill 完成环境准备——该 skill 面向【无 NPU 的开发机】，只配置算子的【编译路径】，不碰 NPU/运行态。

## 任务（严格按顺序）
1. 跑只读检测（不改环境，保留输出供填台账）：
   bash {env_setup_dir}/scripts/detect_env.sh {work_dir}
2. 跑配置脚本（幂等、可安全执行；它【不会】下载 CANN、【不会】执行 sudo）：
   bash {env_setup_dir}/scripts/setup_env.sh {work_dir}
3. 若上一步在 {work_dir}/.env.ascendc.sh 生成了环境片段，在后续编译类步骤中保持 `source {work_dir}/.env.ascendc.sh` 生效。
4. 按 {env_setup_dir}/templates/env-setup-template.md 的格式，把 detect 输出填入台账，产出文件：
   {work_dir}/operators/{op_name}/docs/dev-environment.md
   - 状态行据实填写：✅ 就绪 / ⚠ 部分就绪 / ❌ 缺失
   - NPU 相关项一律 ⊘ 跳过（本机无 NPU）
   - 若 CANN Toolkit 未装，台账如实标❌（本 skill 不自动下载 CANN）

## 约束
- 严格走 ascendc-env-setup skill 的脚本，不要自行臆造安装命令。
- 不下载/安装 CANN Toolkit 本体（缺失只在台账标❌并告知）。
- 不碰 NPU 相关（npu-smi 等一律不跑）。
- 不执行 sudo。
- 只做环境准备，不要开始任何算子开发工作（那是后续插件步骤的任务）。
- 台账必须如实：装了什么、缺什么、跳过什么都写清楚。
"""


def _make_platform_step(step_id: str, step_name: str, step_category: str, prompt: str, step_index: int, output_artifacts: list = None) -> dict:
    """构造一个平台注入步骤（进 Claude 执行，prompt 由平台写死）。"""
    return {
        "step_id": step_id,
        "step_name": step_name,
        "step_type": "platform",
        "step_category": step_category,
        "step_index": step_index,
        "status": "pending",
        "prompt_template": prompt,
        "required_skills": [],
        "output_artifacts": output_artifacts or [],
        "dispatch_target": None,  # 主 Claude 自己执行，不派给 subagent
        "fallback": None,
        "output": "",
        "events": [],
        "duration_ms": 0,
        "gate_passed": None,
        "gate_artifacts": [],
        "skill_compliance": None,
        "token_usage": {},
        "started_at": None,
        "completed_at": None,
    }


# 平台注入步骤模板（step_index 在插入时续号）
# 第 5 项为 output_artifacts（含 {operator_name} 占位符，由 drive.py platform 分支替换）
PRE_PLATFORM_STEP_DEFS = [
    ("platform_install_env", "安装环境", "install_env", PLATFORM_INSTALL_PROMPT,
     ["operators/{operator_name}/docs/dev-environment.md"]),
]
POST_PLATFORM_STEP_DEFS = [("platform_upload_repo", "上库", "upload_repo", None)]  # upload_repo 的 prompt 见下方常量


# 上库步骤 prompt（开发完成后，把本地代码 commit + push 到远程 fork 个人仓库）
PLATFORM_UPLOAD_PROMPT = """你正在 {work_dir} 这个算子库工作目录中，此时插件开发流程已结束、本地已产出开发好的算子代码与文档。
这是仿真平台在开发流程之后、CI/CD 之前为你准备的「上库」步骤：把本地成果提交并推送到你 fork 的远程个人仓库。

## 任务
1. 先用 Bash 执行 `git -C {work_dir} status` 与 `git -C {work_dir} log --oneline -5`，确认当前工作区改动与分支状态。
2. 将本次开发产出的改动纳入提交：`git -C {work_dir} add -A`（注意排除无意改动的临时文件，如 .claude/ 等本地配置目录，必要时先 `git reset` 它们）。
3. 创建一个语义清晰的 commit，message 概括本次算子开发内容（算子名、主要产出），例如：`feat(operator): 新增 Xxx 算子（kernel + 测试 + 文档）`。
4. 推送到当前分支对应的远程（fork）仓库：`git -C {work_dir} push -u origin HEAD`（若提示无远程或需 upstream，按提示处理；若 push 因鉴权失败，如实报告，不要反复重试）。
5. 完成后给出简明上库总结：提交的 commit sha 与 message、推送的远程仓库与分支、本次纳入提交的主要文件清单。

## 约束
- 只做 commit + push 到 fork，不要创建 PR、不要触发或等待 CI（那是后续 CI/CD 步骤的任务）。
- 提交信息要如实反映本次开发内容，不要夸大或臆造。
- 若工作区无任何改动（开发产物为空），如实报告"无改动可提交"并结束，不要创建空 commit。
- 所有 git 命令均在 {work_dir} 下执行。
"""
# 把 upload prompt 填回模板（保持 POST_PLATFORM_STEP_DEFS 第 4 项为该 prompt）
POST_PLATFORM_STEP_DEFS = [
    ("platform_upload_repo", "上库", "upload_repo", PLATFORM_UPLOAD_PROMPT),
]


# 提 PR 步骤 prompt（上库之后，从 fork 个人仓向上游仓提 PR）
# drive.py 替换 {work_dir} / {gitcode_token} / {repo_url} / {fork_path}
PLATFORM_PR_PROMPT = """你正在 {work_dir} 这个算子库工作目录中。上一步「上库」已把开发成果 commit 并 push 到你 fork 的远程个人仓库。
本步骤的任务是：从你的 fork 个人仓，向上游（源）仓库提交一个 Pull Request。

## 你拥有的信息
- 算子库上游仓库地址：{repo_url}
- 你 fork 的个人仓库路径：{fork_path}（格式 owner/repo；若为空说明未 fork，此时如实报告"未 fork 无法提 PR"并结束）
- GitCode API Token：{gitcode_token}（已提供，用于调用 API；不要泄露或写入文件）
- 当前本地分支可用 `git -C {work_dir} rev-parse --abbrev-ref HEAD` 获取

## 任务
1. 解析上游仓库 owner/repo：从 {repo_url}（形如 https://atomgit.com/<owner>/<repo> 或 https://gitcode.com/<owner>/<repo>）中解析出 owner 与 repo；解析对应的 API 域名（如 atomgit.com → api.atomgit.com）。
2. 解析 fork owner/repo：从 {fork_path}（已是 owner/repo 形态）取。
3. 用 Bash + curl 调 GitCode 的「跨仓 PR」接口，从 fork 仓的当前分支，向 upstream 仓的 main（或 master）分支提 PR：
   - GitCode v5 风格（atomgit）：POST https://<api_host>/repos/{upstream_owner}/{upstream_repo}/pulls
     body JSON: {{"title": "...", "body": "...", "base": "main", "head": "{fork_owner}:{source_branch}", "fork_path": "{fork_owner}/{fork_repo}"}}
   - 请求头带 PRIVATE-TOKEN: {gitcode_token}（或 Authorization: Bearer {gitcode_token}，按平台而定）
   - title 概括本次算子开发内容；body 简述改动（可参考本地 commit message 与设计文档摘要）。
4. 若返回已有同名 PR（409/已存在），取该 PR 的 url 报告"PR 已存在"，不要重复创建。
5. 完成后给出简明总结：PR 的 url、源分支→目标分支、PR 标题。

## 约束
- 只提 PR，不要触发或等待 CI（那是后续 CI/CD 步骤的任务）。
- token 仅用于本次 curl 请求，不要写入任何文件、不要 echo 到日志明文。
- 若 API 鉴权失败或仓库路径解析失败，如实报告原因并结束，不要反复重试。
"""
POST_PLATFORM_STEP_DEFS = [
    ("platform_upload_repo", "上库", "upload_repo", PLATFORM_UPLOAD_PROMPT),
    ("platform_create_pr", "提 PR", "create_pr", PLATFORM_PR_PROMPT),
]


def build_pre_platform_steps(start_index: int = 0) -> list:
    """前置平台步骤（安装环境），插在 Clone 之后、插件开发流程之前。"""
    return [
        _make_platform_step(sid, name, cat, prompt, start_index + i, output_artifacts=arts)
        for i, (sid, name, cat, prompt, arts) in enumerate(PRE_PLATFORM_STEP_DEFS)
    ]


def build_post_platform_steps(start_index: int) -> list:
    """后置平台步骤（上库），插在插件开发流程之后、NPU/CI-CD 之前。"""
    return [
        _make_platform_step(sid, name, cat, prompt, start_index + i)
        for i, (sid, name, cat, prompt) in enumerate(POST_PLATFORM_STEP_DEFS)
    ]


def build_platform_steps(start_index: int = 0) -> list:
    """【已弃用，保留向后兼容】返回前置平台步骤（安装环境）。新代码请用 build_pre_platform_steps。"""
    return build_pre_platform_steps(start_index)


# ==================== 辅助函数 ====================


def find_plugin_dir(plugin_id: str) -> Optional[str]:
    for parent in ("plugins-official", "plugins-community"):
        d = os.path.join(_PROJECT_ROOT, "external", "cannbot-skills", parent, plugin_id)
        if os.path.isdir(d):
            return d
    return None


def classify_error(error_content: str, exit_code: Optional[int] = None) -> dict:
    """对错误进行自动分类，返回错误详情。"""
    content = (error_content or "").lower()
    category = "UNKNOWN"
    root_cause = error_content
    suggestion = "查看错误详情排查问题"

    if "未找到" in content or "not found" in content or "cli 未找到" in content:
        category = "ENV"
        root_cause = "Claude Code CLI 未安装或不在 PATH 中"
        suggestion = "运行 `npm install -g @anthropic-ai/claude-code` 安装 CLI，或确认 `claude` 命令在终端可用"
    elif "separator is found, but chunk is longer than limit" in content:
        category = "ENV"
        root_cause = "Python asyncio StreamReader 行缓冲区溢出（64KB 限制）。"
        suggestion = "此为驱动层已知限制，需升级 _read_lines 使用无限制的行读取方式（已在新版本中修复）"
    elif "timeout" in content or "超时" in content:
        category = "TIMEOUT"
        root_cause = "Claude Code CLI 执行超时"
        suggestion = "可增大步骤超时时间，或检查 Claude CLI 是否卡住"
    elif "被取消" in content or "cancelled" in content:
        category = "TIMEOUT"
        root_cause = "仿真被用户手动取消"
        suggestion = "正常操作，无需处理"
    elif exit_code == -9:
        category = "CLI"
        root_cause = f"Claude 进程被 SIGKILL 信号终止（exit code -9），通常由系统 OOM Killer 或手动 kill 导致"
        suggestion = (
            "检查系统内存使用情况，或查看是否有其他进程管理工具终止了 claude 进程"
        )
    elif exit_code and exit_code < 0:
        category = "CLI"
        root_cause = (
            f"Claude 进程被信号终止（exit code {exit_code}，信号 {-exit_code}）"
        )
        suggestion = "检查系统资源（内存、CPU）是否充足"
    elif (
        "connection" in content
        or "网络" in content
        or "dns" in content
        or "refused" in content
    ):
        category = "NETWORK"
        root_cause = "网络连接异常"
        suggestion = "检查网络连接，确认能访问 Anthropic API（api.anthropic.com）"
    elif (
        "permission" in content
        or "权限" in content
        or "eacces" in content
        or "access denied" in content
    ):
        category = "PERMISSION"
        root_cause = "文件或命令权限不足"
        suggestion = "检查工作目录和文件的读写权限"
    elif "skill" in content or "插件" in content or "plugin" in content:
        category = "SKILL"
        root_cause = "Skill 或插件相关错误"
        suggestion = "检查 Skill 是否正确安装在工作目录的 .claude/ 目录下"
    elif "启动" in content and "失败" in content:
        category = "CLI"
        root_cause = error_content
        suggestion = "检查 Claude CLI 版本和配置"

    return {
        "category": category,
        "root_cause": root_cause,
        "suggestion": suggestion,
        "original_error": error_content,
        "exit_code": exit_code,
    }


def summarize_tool_use(tool_name: str, tool_input: dict) -> str:
    """将工具调用转为人类可读的操作摘要。"""
    if tool_name == "Read":
        return f"📖 读取文件: {tool_input.get('file_path', '')}"
    elif tool_name == "Write":
        content = tool_input.get("content", "")
        lines = content.count("\n") + 1 if content else 0
        return f"✏️ 写入文件: {tool_input.get('file_path', '')} ({lines} 行)"
    elif tool_name == "Edit":
        return f"📝 编辑文件: {tool_input.get('file_path', '')}"
    elif tool_name == "Bash":
        cmd = tool_input.get("command", "")
        desc = tool_input.get("description", "")
        label = f" — {desc}" if desc else ""
        return f"⚙️ 执行命令: {cmd[:120]}{label}"
    elif tool_name == "Glob":
        return f"🔍 搜索文件: {tool_input.get('pattern', '')}"
    elif tool_name == "Grep":
        return f"🔍 搜索内容: '{tool_input.get('pattern', '')}' in {tool_input.get('path', '')}"
    elif tool_name == "Agent":
        return f"🤖 调用子Agent: {tool_input.get('subagent_type', '')} — {tool_input.get('description', '')}"
    elif tool_name == "LSP":
        return f"🔗 LSP {tool_input.get('operation', '')}: {tool_input.get('filePath', '')}"
    elif tool_name == "WebSearch":
        return f"🌐 搜索: {tool_input.get('query', '')}"
    elif tool_name == "Skill":
        sk = tool_input.get("skill", "") or ""
        args = (tool_input.get("args", "") or "")[:60]
        return f"🎯 调用 Skill: /{sk} {args}".rstrip()
    else:
        return f"🔧 {tool_name}({json.dumps(tool_input, ensure_ascii=False)[:100]})"


def gate_check(work_dir: str, artifacts: list) -> dict:
    """门禁检查：验证产出物文件是否存在。"""
    if not artifacts:
        return {"passed": None, "skipped": True, "artifacts": []}
    results = []
    for art in artifacts:
        path = os.path.join(work_dir, art) if not os.path.isabs(art) else art
        exists = os.path.exists(path)
        results.append({"name": art, "exists": exists})
    passed = all(r["exists"] for r in results)
    return {"passed": passed, "skipped": False, "artifacts": results}


def render_prompt(prompt_template: str, op_name: str, op_spec: str) -> str:
    """渲染 prompt 模板，替换变量。"""
    spec_part = f"\n\n需求描述：{op_spec}" if op_spec else ""
    if not prompt_template:
        return f"请执行以下算子的开发工作流：{op_name}。{spec_part}\n遵循 .claude/ 下安装的 Skills 和 Agents 指南。"
    return (
        prompt_template.replace("{operator_name}", op_name)
        .replace("{op_name}", op_name)
        .replace("{op_spec}", op_spec or op_name)
    )


async def run_git(*args, cwd: str = None) -> dict:
    """执行 git 命令。"""
    cmd = ["git"] + list(args)
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
    return {
        "returncode": proc.returncode,
        "stdout": stdout.decode("utf-8", errors="replace").strip(),
        "stderr": stderr.decode("utf-8", errors="replace").strip(),
    }


def get_or_create_bus(session_id: str) -> SessionEventBus:
    """获取或创建 per-session 事件总线。"""
    bus = _session_event_buses.get(session_id)
    if bus is None:
        bus = SessionEventBus()
        _session_event_buses[session_id] = bus
    return bus


def format_sse(ev: dict) -> str:
    """把 {event, data} 格式化为 SSE 文本。"""
    return f"event: {ev.get('event', 'message')}\ndata: {json.dumps(ev.get('data', {}), ensure_ascii=False)}\n\n"


def project_snapshot(session: dict) -> dict:
    """从 session 提取前端需要的全量快照字段。"""
    if not session:
        return {}
    return {
        "session_id": session.get("session_id"),
        "status": session.get("status"),
        "steps": session.get("steps", []),
        "breakpoint_alerts": session.get("breakpoint_alerts", []),
        "terminal_log": session.get("terminal_log", []),
        "simulation_log": session.get("simulation_log", []),
        "program_log": session.get("program_log", []),
        "gate_checks": session.get("gate_checks", []),
        "jsonl_log": session.get("jsonl_log", []),
        "fix_log": session.get("fix_log", []),
        "summary": session.get("summary"),
        "pipeline": session.get("pipeline"),
        "npu_test": session.get("npu_test"),
        "install_result": session.get("install_result"),
    }
def _fill_legacy_logs(session: dict) -> dict:
    """兼容老会话：从 steps 数据反向生成 terminal_log 和 simulation_log"""
    # 老会话补 npu_test 默认字段
    if not session.get("npu_test"):
        session["npu_test"] = {
            "status": "pending",
            "host": None,
            "remote_dir": None,
            "build_cmd": None,
            "test_cmd": None,
            "steps": [],
            "logs": [],
            "summary": None,
            "triggered_at": None,
            "completed_at": None,
            "error": None,
            "error_detail": None,
        }

    steps = session.get("steps", [])
    if not steps:
        return session

    # 老会话补 clone_status 默认值
    if not session.get("clone_status"):
        session["clone_status"] = "pending"

    # 老会话补外部生命周期步骤（clone 前置 / NPU·CI-CD 后置）+ 平台注入步骤，并重排为新顺序
    plugin_steps_local = [s for s in steps if s.get("step_type") not in ("external", "platform")]
    existing_ext = {s.get("step_id"): s for s in steps if s.get("step_type") == "external"}

    def _ext_or_new(step_id, builder):
        # 已有则复用（保留运行时 status），否则新建
        return existing_ext.get(step_id) or builder(0)[0]

    pre_steps = [_ext_or_new("ext_clone", build_pre_external_steps)]
    # 平台注入步骤（install_env 前置 / upload_repo+create_pr 后置）：老会话当时没跑过，标 skipped
    def _platform_or_skipped_at(step_id, builder, idx):
        existing = next((s for s in steps if s.get("step_id") == step_id), None)
        if existing:
            return existing
        s = builder(0)[idx]
        s["status"] = "skipped"
        return s

    pre_platform = [_platform_or_skipped_at("platform_install_env", build_pre_platform_steps, 0)]
    # post_platform 可能含多个（上库、提 PR），逐个按 idx 补
    _post_defs = build_post_platform_steps(0)
    post_platform = [
        _platform_or_skipped_at(s["step_id"], build_post_platform_steps, i)
        for i, s in enumerate(_post_defs)
    ]
    post_steps = [
        _ext_or_new("ext_npu", lambda idx: build_post_external_steps(idx)[:1]),
        _ext_or_new("ext_cicd", lambda idx: build_post_external_steps(idx)[1:2]),
    ]
    # 重新编号 step_index：clone=0, install_env=1, plugin=2.., upload_repo, npu/cicd
    seq = pre_steps + pre_platform + plugin_steps_local + post_platform + post_steps
    for i, s in enumerate(seq):
        s["step_index"] = i
    session["steps"] = seq

    if not session.get("terminal_log"):
        terminal_log = []
        for step in steps:
            step_id = step.get("step_id", "")
            for ev in step.get("events", []):
                ev_type = ev.get("type", "")
                content = str(ev.get("content", ""))
                name = ev.get("name", "")
                if ev_type == "tool_use" and name:
                    content = summarize_tool_use(name, ev.get("input") or {})
                terminal_log.append(
                    {
                        "time": step.get("started_at", "")[11:19]
                        if step.get("started_at")
                        else "",
                        "type": ev_type,
                        "content": content[:500],
                        "step_id": step_id,
                    }
                )
        session["terminal_log"] = terminal_log

    if not session.get("simulation_log"):
        simulation_log = []
        summary = session.get("summary")
        for i, step in enumerate(steps):
            step_id = step.get("step_id", "")
            step_name = step.get("step_name", "")
            status = step.get("status", "")
            duration = step.get("duration_ms", 0)
            started = step.get("started_at", "")
            time_str = started[11:19] if started else ""
            simulation_log.append(
                {
                    "time": time_str,
                    "type": "info",
                    "text": f"[{i + 1}/{len(steps)}] {step_name}",
                }
            )
            if status == "completed":
                gate = "门禁通过" if step.get("gate_passed", True) else "门禁未通过"
                ed = step.get("error_detail")
                err_info = f" [{ed['category']}]" if ed else ""
                simulation_log.append(
                    {
                        "time": time_str,
                        "type": "warn" if ed else "success",
                        "text": f"{step_id} 完成 ({duration}ms, {gate}){err_info}",
                    }
                )
            elif status == "failed":
                simulation_log.append(
                    {"time": time_str, "type": "error", "text": f"{step_id} 失败"}
                )
        if summary:
            simulation_log.append(
                {
                    "time": session.get("completed_at", "")[11:19]
                    if session.get("completed_at")
                    else "",
                    "type": "info",
                    "text": f"仿真完成 — {summary.get('verdict', '-')}, {summary.get('passed_steps', 0)}/{summary.get('total_steps', 0)} 步通过",
                }
            )
        session["simulation_log"] = simulation_log

    return session

