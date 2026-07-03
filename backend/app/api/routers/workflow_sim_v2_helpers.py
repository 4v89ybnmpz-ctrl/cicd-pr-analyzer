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
    ("ext_npu", "NPU 真机仿真", "npu"),
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
PLATFORM_INSTALL_PROMPT = """你正在 {work_dir} 这个已 clone 下来的算子库工作目录中。
这是仿真平台在执行插件开发流程之前，为你准备的「环境准备」步骤。

## 任务
1. 先用 Read/Glob 阅读该算子库根目录及 docs/ 下的文档：README、CONTRIBUTING（贡献指南）、开发文档、构建说明、环境要求等（找不到就跳过该文件，不要报错）。
2. 从文档中识别出本算子库的开发环境要求：依赖的编程语言/编译器版本、Python/Conda 环境、系统包、CANN/Ascend 工具链、第三方库、环境变量、初始化脚本（如 source env.sh / init.sh / install.sh）等。
3. 按文档描述安装/配置环境。可以执行文档中明确指明的安装命令或初始化脚本。如文档未指明，仅做最小必要的环境准备（如创建 venv、安装 requirements.txt 中的依赖），不要臆造命令。
4. 完成后给出简明安装总结：识别到的开发要求、实际执行的安装步骤、最终环境状态（已就绪 / 部分就绪 / 缺失项）。

## 约束
- 严格依据文档判断要装什么，不要套用通用模板。不同算子库要求差异很大。
- 只做"环境准备"，不要开始任何算子开发工作（那是后续插件步骤的任务）。
- 安装命令应在 {work_dir} 下执行。
"""


def build_platform_steps(start_index: int = 0) -> list:
    """平台注入步骤（不属于插件 task-prompts.md），由平台写死 prompt，进 Claude 执行。

    与 external 步骤的区别：external 仅前端展示、不进 Claude；
    platform 是真 Claude 执行步骤，prompt 由平台定义。
    """
    return [{
        "step_id": "platform_install_env",
        "step_name": "安装环境",
        "step_type": "platform",
        "step_category": "install_env",
        "step_index": start_index,
        "status": "pending",
        "prompt_template": PLATFORM_INSTALL_PROMPT,
        "required_skills": [],
        "output_artifacts": [],
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
    }]


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
    # 平台注入步骤：老会话当时没跑过，标 skipped（前端显示「已跳过」，不误导成未完成）
    platform_step = None
    if not any(s.get("step_id") == "platform_install_env" for s in steps):
        platform_step = build_platform_steps(0)[0]
        platform_step["status"] = "skipped"
    else:
        platform_step = next(s for s in steps if s.get("step_id") == "platform_install_env")
    post_steps = [
        _ext_or_new("ext_npu", lambda idx: build_post_external_steps(idx)[:1]),
        _ext_or_new("ext_cicd", lambda idx: build_post_external_steps(idx)[1:2]),
    ]
    # 重新编号 step_index：clone=0, platform=1, plugin=2..n+1, npu/cicd=n+2..
    seq = pre_steps + ([platform_step] if platform_step else []) + plugin_steps_local + post_steps
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

