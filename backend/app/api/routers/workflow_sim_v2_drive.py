"""工作流仿真 V2 — 核心仿真执行（后台 Task 驱动）"""

import asyncio
import json
import logging
import os
import re
import time
from datetime import datetime

from app.services.claude_code_driver import claude_driver, ClaudeCodeDriver
from app.services.session_event_bus import SessionEventBus
from app.config.config_manager import config_manager
from app.models.workflow_models import ArbitratorReport, ArbitratorIssue

from .workflow_sim_v2_helpers import (
    render_prompt as _render_prompt,
    summarize_tool_use as _summarize_tool_use,
    classify_error as _classify_error,
    gate_check as _gate_check,
    run_git as _run_git,
    get_or_create_bus as _get_or_create_bus,
    _pipeline_cancel_flags,
    _active_session_tasks,
    _PROJECT_ROOT,
    ARBITRATOR_PROMPT,
)
from .workflow_sim_v2_skill import (
    compute_skill_compliance as _compute_skill_compliance,
    monitor_skill_compliance as _monitor_skill_compliance,
    ai_gate_check as _ai_gate_check,
)
from .workflow_sim_v2_jsonl import (
    harvest_subagent_skill_refs as _harvest_subagent_skill_refs,
    harvest_new_jsonl_lines as _harvest_new_jsonl_lines,
)

logger = logging.getLogger(__name__)


def _parse_arbitrator_json(text: str) -> dict:
    """从 claude 的文本回复中解析裁判断点 JSON（和 _parse_claude_gate 类似但提取 issues 列表）。"""
    try:
        # 优先找 ```json ... ``` 代码块
        start = text.find("```json")
        if start >= 0:
            start = text.find("\n", start) + 1
            end = text.find("```", start)
            if end > start:
                return json.loads(text[start:end])
    except (json.JSONDecodeError, ValueError):
        pass
    try:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
    except (json.JSONDecodeError, ValueError):
        pass
    return {"verdict": "unknown", "issues": [], "summary": "无法解析裁判 JSON"}


def _parse_claude_gate(text: str) -> dict:
    """从 Claude 的文本回复中解析门禁判定 JSON。"""
    try:
        start = text.find("```json")
        if start >= 0:
            start = text.find("\n", start) + 1
            end = text.find("```", start)
            if end > start:
                return json.loads(text[start:end])
    except (json.JSONDecodeError, ValueError):
        pass
    try:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
    except (json.JSONDecodeError, ValueError):
        pass
    return {
        "verdict": "skipped",
        "reasoning": "Claude 门禁输出无法解析",
        "raw": text[:500],
    }


async def drive_session_events(
    session_id: str,
    session: dict,
    db,
    gitcode_token: str,
    bus: SessionEventBus,
):
    """驱动仿真跑完，事件 publish 到 bus + 增量持久化到 DB。"""
    work_dir = session.get("work_dir", "")
    op_name = session.get("op_name", "")
    op_spec = session.get("op_spec", "")
    steps = session.get("steps", [])
    plugin_id = session.get("plugin_id", "")
    step_timeout = session.get("step_timeout") or 0
    alerts = []
    all_tokens = {"input": 0, "output": 0}

    terminal_log = []
    simulation_log = []
    jsonl_offsets: dict = {}

    # Docker 容器：整个仿真在容器内运行，work_dir → /workspace，cannbot-skills → /opt/cannbot-skills
    docker_container = f"cann-sim-{session_id}"
    _cannbot_skills_dir = os.path.join(_PROJECT_ROOT, "external", "cannbot-skills")

    def _ts():
        return datetime.now().strftime("%H:%M:%S")

    def _emit(event: str, data: dict):
        ev = {"event": event, "data": data}
        bus.publish(ev)
        return ev

    async def _push_term(entry: dict):
        terminal_log.append(entry)
        await db.append_workflow_sim_v2_log(session_id, "terminal_log", [entry])

    async def _push_simlog(entry: dict):
        simulation_log.append(entry)
        await db.append_workflow_sim_v2_log(session_id, "simulation_log", [entry])

    async def _push_alert(alert: dict):
        alerts.append(alert)
        await db.append_workflow_sim_v2_log(session_id, "breakpoint_alerts", [alert])

    program_log = []

    async def _push_proglog(level: str, msg: str, **extra):
        entry = {"time": _ts(), "level": level, "msg": msg}
        if extra:
            entry["extra"] = extra
        program_log.append(entry)
        await db.append_workflow_sim_v2_log(session_id, "program_log", [entry])
        bus.publish({"event": "program_log", "data": entry})

    async def _push_gate_record(rec: dict):
        """结构化存储门禁检查记录，便于事后复查。"""
        await db.append_workflow_sim_v2_log(session_id, "gate_checks", [rec])
        bus.publish({"event": "gate_record", "data": rec})

    os.makedirs(work_dir, exist_ok=True)

    # ===== Docker 容器管理 =====
    # 启动 cann-dev 容器，挂载 work_dir 和 cannbot-skills
    _container_ready = False
    # 平台产物目录（算子仓之外，不污染代码仓）
    _artifacts_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(work_dir))),
        "artifacts", session_id,
    )
    os.makedirs(_artifacts_dir, exist_ok=True)
    # 检测 --shared clone 的 alternates 母本路径，挂载到容器内同路径（避免 git 仓库断开）
    _base_mount = []
    _alt_file = os.path.join(work_dir, ".git", "objects", "info", "alternates")
    if os.path.isfile(_alt_file):
        _base_path = open(_alt_file).read().strip()
        if _base_path and os.path.isdir(_base_path):
            _base_mount = ["-v", f"{_base_path}:{_base_path}:ro"]
            logger.info(f"[docker] alternates 母本挂载: {_base_path}")
    try:
        _stop_cmd = ["docker", "rm", "-f", docker_container]
        _stop_proc = await asyncio.create_subprocess_exec(*_stop_cmd)
        await _stop_proc.communicate()
        _start_cmd = [
            "docker", "run", "-d", "--name", docker_container,
            "-v", f"{work_dir}:/workspace",
            "-v", f"{_cannbot_skills_dir}:{_cannbot_skills_dir}:ro",
            "-v", f"{_artifacts_dir}:/platform-artifacts",
            *_base_mount,
            "--network", "host",
            # 透传 Claude 认证相关环境变量（否则容器内 claude 报 Not logged in）
            "-e", "ANTHROPIC_AUTH_TOKEN",
            "-e", "ANTHROPIC_BASE_URL",
            "-e", "ANTHROPIC_DEFAULT_SONNET_MODEL",
            "-e", "ANTHROPIC_DEFAULT_OPUS_MODEL",
            "-e", "ANTHROPIC_DEFAULT_HAIKU_MODEL",
            "-e", "NODE_TLS_REJECT_UNAUTHORIZED",  # 宿主机 ANTHROPIC_BASE_URL 用自签证书，需跳过 SSL 验证
            "cann-dev:full", "sleep", "infinity",
        ]
        logger.info(f"[docker] 正在启动容器: {' '.join(_start_cmd)}")
        _proc = await asyncio.create_subprocess_exec(
            *_start_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        _stdout, _stderr = await _proc.communicate()
        logger.info(f"[docker] 启动结果: rc={_proc.returncode} stdout={_stdout!r} stderr={_stderr!r}")
        if _proc.returncode == 0:
            _container_ready = True
            # 换国内 apt 镜像源（加速 apt-get update/install）
            _sed_cmd = ["docker", "exec", "--user", "root", docker_container,
                        "sed", "-i", "s@archive.ubuntu.com@mirrors.aliyun.com@g", "/etc/apt/sources.list"]
            _sed_proc = await asyncio.create_subprocess_exec(*_sed_cmd)
            await _sed_proc.communicate()
            # 换国内 pip 镜像源（加速 pip install）
            _pip_cmd = ["docker", "exec", docker_container,
                        "pip", "config", "set", "global.index-url", "https://mirrors.aliyun.com/pypi/simple/"]
            _pip_proc = await asyncio.create_subprocess_exec(*_pip_cmd)
            await _pip_proc.communicate()
            await _push_proglog("INFO", f"Docker 容器已启动: {docker_container}（apt 源已换）", container=docker_container)
        else:
            _err = _stderr.decode() if _stderr else "无错误输出"
            logger.error(f"[docker] 容器启动失败: {_err}")
            await _push_proglog("WARN", f"Docker 容器启动失败: {_err}", container=docker_container)
    except Exception as _e:
        logger.exception(f"[docker] 容器启动异常: {_e}")
        try:
            await _push_proglog("WARN", f"Docker 容器启动异常: {_e}")
        except Exception:
            logger.exception("[docker] _push_proglog 也失败了")

    # 拍基线快照：记 HEAD commit sha 作为文件改动 diff 的基线（非 git 仓库则跳过，不阻断仿真）
    if os.path.isdir(os.path.join(work_dir, ".git")):
        try:
            r = await _run_git("rev-parse", "HEAD", cwd=work_dir)
            if r.get("returncode") == 0 and r.get("stdout", "").strip():
                baseline = r["stdout"].strip()
                session["diff_baseline"] = baseline
                try:
                    await db.update_workflow_sim_v2_session(session_id, {"diff_baseline": baseline})
                except Exception:
                    pass
        except Exception:
            pass

    await _push_simlog(
        {
            "time": _ts(),
            "type": "info",
            "text": f"开始仿真: {op_name} ({len(steps)} 步)",
        }
    )
    yield _emit(
        "start",
        {
            "session_id": session_id,
            "plugin_id": plugin_id,
            "op_name": op_name,
            "total_steps": len(steps),
        },
    )

    # Claude CLI 会话 ID：首步起新会话，后续步用 --resume 续接共享上下文
    claude_session_id = ""

    await _push_proglog(
        "INFO", f"仿真启动: op={op_name}, steps={len(steps)}, work_dir={work_dir}"
    )

    # 配置阀门：控制工作流走到哪个步骤后停止
    _wf_config = config_manager.get("workflow_v2", {}) if config_manager else {}
    _max_steps = _wf_config.get("max_steps", "all")  # clone | install_env | all
    _stop_after = {
        "clone": "platform_install_env",   # clone 之后无 platform step，等价于第一个 platform 前停
        "install_env": "platform_install_env",
        "env_check": "step_1",             # 插件 Step 1 环境检查后停
        "all": "__never__",
    }.get(_max_steps, "platform_install_env")

    for i, step in enumerate(steps):
        if step.get("step_type") == "external":
            # 外部生命周期步骤（clone/NPU/CI-CD）不进 Claude 执行，仅前端串联展示
            continue
        if step.get("status") == "completed":
            continue

        step_id = step["step_id"]
        step_name = step["step_name"]
        prompt_template = step.get("prompt_template", "")
        required_skills = step.get("required_skills", [])
        artifacts = step.get("output_artifacts", [])

        # 平台注入步骤（step_type=platform）：prompt 由平台写死，替换占位符，
        # 不走插件的 op_name/op_spec 渲染
        if step.get("step_type") == "platform":
            _fork_info = session.get("fork_info") or {}
            # Docker 模式下 env_setup_dir 用容器内路径
            _env_setup_dir = os.path.join(
                _cannbot_skills_dir, "ops", "ascendc-env-setup"
            )
            prompt = prompt_template.replace("{work_dir}", "/workspace") \
                .replace("{op_name}", op_name) \
                .replace("{env_setup_dir}", _env_setup_dir) \
                .replace("{gitcode_token}", gitcode_token or "") \
                .replace("{repo_url}", session.get("repo_url", "") or "") \
                .replace("{fork_path}", _fork_info.get("fork_path", "") or "")
            # platform step 的 artifacts 占位符在此替换（plugin step 已在 sessions.py 替换）
            artifacts = [a.replace("{operator_name}", op_name) for a in artifacts]
        else:
            prompt = _render_prompt(prompt_template, op_name, op_spec)

        # 追加产出物自检指令：让 Claude 在同一会话内完成前自行检查并补齐
        if artifacts:
            artifact_list = "\n".join(f"- {a}" for a in artifacts)
            prompt += f"""

## 产出物自检（完成前必须执行）

本步骤要求以下产出物文件全部存在：
{artifact_list}

在结束本步骤前，你必须：
1. 逐一检查上述文件是否已创建且内容不为空
2. 对每个缺失或空文件，根据步骤要求和 Skill 指南立即创建
3. 确认所有文件都已正确写入后才能结束

这是硬性要求，不得跳过。"""

        step["status"] = "running"
        step["started_at"] = datetime.now().isoformat()
        proc_info = claude_driver.get_process_info(session_id)
        if proc_info:
            step["process"] = proc_info
        await db.update_workflow_sim_v2_step(
            session_id,
            step_id,
            {
                "status": "running",
                "started_at": step["started_at"],
                **({"process": proc_info} if proc_info else {}),
            },
        )

        await _push_simlog(
            {
                "time": _ts(),
                "type": "info",
                "text": f"[{i + 1}/{len(steps)}] {step_name}",
            }
        )
        if claude_session_id:
            await _push_simlog(
                {
                    "time": _ts(),
                    "type": "info",
                    "text": f"  ↳ --resume 续接会话: {claude_session_id[:12]}...",
                }
            )
            await _push_proglog(
                "INFO",
                f"Step {i + 1} --resume 续接",
                session_id=claude_session_id[:16],
                step=step_id,
            )
        else:
            await _push_simlog(
                {
                    "time": _ts(),
                    "type": "info",
                    "text": "  ↳ 新建 Claude 会话（首步）",
                }
            )
            await _push_proglog("INFO", f"Step {i + 1} 新建 Claude 会话", step=step_id)
        yield _emit(
            "step_start",
            {
                "step_id": step_id,
                "step_name": step_name,
                "step_index": i,
                "total": len(steps),
                "prompt": prompt[:200],
            },
        )

        events = []
        step_output_parts = []
        step_start_time = time.time()

        async for ev in claude_driver.run_step(
            session_id,
            prompt,
            work_dir,
            timeout=step_timeout,
            step_id=step_id,
            persist_proc_on_consumer_exit=True,
            resume_session_id=claude_session_id,
            docker_container=docker_container if _container_ready else "",
        ):
            events.append(ev)
            ev_type = ev["type"]

            if ev_type == "tool_use":
                tool_name = ev.get("name", "")
                tool_input = ev.get("input", {})
                summary = _summarize_tool_use(tool_name, tool_input)
                step_output_parts.append(summary)
                await _push_term(
                    {
                        "time": _ts(),
                        "type": "tool_use",
                        "content": summary,
                        "step_id": step_id,
                    }
                )

                invoked_skills = ClaudeCodeDriver.extract_skill_references([ev])
                out_data = {
                    "step_id": step_id,
                    "type": "tool_use",
                    "content": summary,
                    "tool_name": tool_name,
                    "tool_input": tool_input,
                }
                if invoked_skills:
                    out_data["skill_invoked"] = invoked_skills[0]
                yield _emit("claude_output", out_data)

                if tool_name == "Agent":
                    agent_type = tool_input.get("subagent_type", "")
                    agent_desc = tool_input.get("description", "")
                    await _push_simlog(
                        {
                            "time": _ts(),
                            "type": "info",
                            "text": f"🤖 Agent 启动: {agent_type} — {agent_desc}",
                        }
                    )

                for ref_name in invoked_skills:
                    is_agent_file = tool_name in (
                        "Read",
                        "Glob",
                        "Grep",
                    ) and ".claude/agents/" in (
                        tool_input.get("file_path", "")
                        or tool_input.get("pattern", "")
                        or tool_input.get("path", "")
                    )
                    ref_type = "Agent 文件" if is_agent_file else "Skill"
                    await _push_simlog(
                        {
                            "time": _ts(),
                            "type": "info",
                            "text": f"📄 引用 {ref_type}: {ref_name}",
                        }
                    )
            elif ev_type == "tool_result":
                output_content = str(ev.get("output", ""))[:2000]
                tool_name = ev.get("name", "")
                step_output_parts.append(f"[{tool_name}] {output_content[:200]}")
                await _push_term(
                    {
                        "time": _ts(),
                        "type": "tool_result",
                        "content": output_content[:500],
                        "step_id": step_id,
                    }
                )
                yield _emit(
                    "claude_output",
                    {
                        "step_id": step_id,
                        "type": "tool_result",
                        "content": output_content,
                        "tool_name": tool_name,
                    },
                )
            elif ev_type in ("text", "thinking", "raw"):
                output_content = ev.get("content", "")
                if output_content:
                    step_output_parts.append(str(output_content))
                await _push_term(
                    {
                        "time": _ts(),
                        "type": ev_type,
                        "content": str(output_content or "")[:500],
                        "step_id": step_id,
                    }
                )
                yield _emit(
                    "claude_output",
                    {
                        "step_id": step_id,
                        "type": ev_type,
                        "content": str(output_content or "")[:2000],
                    },
                )

            elif ev["type"] == "timeout":
                error_detail = _classify_error("步骤执行超时", exit_code=None)
                step["status"] = "failed"
                step["error_detail"] = error_detail
                await _push_alert(
                    {
                        "type": "STEP_TIMEOUT",
                        "severity": "HIGH",
                        "step_id": step_id,
                        "message": f"步骤 {step_name} 超时",
                        "root_cause": f"步骤在 {step_timeout} 秒内未完成，Claude CLI 可能卡住或任务过于复杂",
                        "suggestion": "增大步骤超时时间，或检查 Claude CLI 是否正常响应",
                        "error_category": "TIMEOUT",
                        "detected_at": datetime.now().isoformat(),
                    }
                )
                await _push_simlog(
                    {
                        "time": _ts(),
                        "type": "warn",
                        "text": f"步骤 {step_name} 超时 ({step_timeout}s)",
                    }
                )
                yield _emit("breakpoint_alert", alerts[-1])

            elif ev["type"] == "error":
                error_content = ev.get("content", "未知错误")
                error_detail = _classify_error(error_content)
                await _push_alert(
                    {
                        "type": error_detail["category"],
                        "severity": "CRITICAL",
                        "step_id": step_id,
                        "message": error_content,
                        "root_cause": error_detail["root_cause"],
                        "suggestion": error_detail["suggestion"],
                        "error_category": error_detail["category"],
                        "detected_at": datetime.now().isoformat(),
                    }
                )
                step["error_detail"] = error_detail
                step["status"] = "failed"
                await _push_simlog(
                    {
                        "time": _ts(),
                        "type": "error",
                        "text": f"[CRITICAL] {error_content}",
                    }
                )
                yield _emit("breakpoint_alert", alerts[-1])

            elif ev["type"] == "result":
                tokens = ev.get("tokens", {})
                step["token_usage"] = tokens
                if isinstance(tokens, dict):
                    all_tokens["input"] += tokens.get("input", 0)
                    all_tokens["output"] += tokens.get("output", 0)
                # 捕获 Claude 会话 ID 供后续步 --resume 续接
                csid = ev.get("claude_session_id", "")
                if csid:
                    claude_session_id = csid
                    await db.update_workflow_sim_v2_session(
                        session_id, {"claude_session_id": csid}
                    )
                    await _push_simlog(
                        {
                            "time": _ts(),
                            "type": "info",
                            "text": f"📎 Claude 会话 ID 已捕获: {csid[:12]}...",
                        }
                    )
                    await _push_proglog(
                        "INFO", f"Claude session_id 捕获: {csid[:16]}", step=step_id
                    )

        step_duration = int((time.time() - step_start_time) * 1000)

        # ===== Claude 门禁：在同一会话中让 Claude 检查交付物 =====
        if not artifacts:
            gate = {
                "passed": None,
                "skipped": True,
                "artifacts": [],
                "gate_text": "",
                "gate_tool_output": "",
            }
            step["gate_passed"] = None
            step["gate_artifacts"] = []
        else:
            artifact_list_str = "\n".join(f"- {a}" for a in artifacts)
            gate_prompt = ARBITRATOR_PROMPT.replace(
                "{step_prompt}", prompt[:3000]
            ).replace(
                "{step_output}", "\n".join(step_output_parts)[-5000:]
            ).replace(
                "{artifacts}", artifact_list_str
            )

            await _push_simlog(
                {"time": _ts(), "type": "info", "text": "🔍 Claude 门禁检查中..."}
            )
            await _push_proglog(
                "INFO", f"门禁检查启动: artifacts={artifacts}", step=step_id
            )

            gate_text = ""
            gate_tool_output = ""
            gate_event_count = {
                "text": 0,
                "tool_use": 0,
                "thinking": 0,
                "tool_result": 0,
                "other": 0,
            }
            async for gev in claude_driver.run_step(
                session_id,
                gate_prompt,
                work_dir,
                timeout=step_timeout,
                step_id=f"{step_id}_gate",
                persist_proc_on_consumer_exit=True,
                resume_session_id=claude_session_id,
                docker_container=docker_container if _container_ready else "",
            ):
                evt_type = gev.get("type", "other")
                if evt_type in gate_event_count:
                    gate_event_count[evt_type] += 1
                else:
                    gate_event_count["other"] += 1

                if evt_type == "text":
                    c = gev.get("content", "")
                    gate_text += c
                    await _push_term(
                        {
                            "time": _ts(),
                            "type": "text",
                            "content": str(c)[:500],
                            "step_id": step_id,
                        }
                    )
                    await _push_proglog("DEBUG", f"门禁 text: {c[:200]}", step=step_id)
                elif evt_type == "tool_use":
                    c_summary = _summarize_tool_use(
                        gev.get("name", ""), gev.get("input", {})
                    )
                    await _push_term(
                        {
                            "time": _ts(),
                            "type": "tool_use",
                            "content": f"[门禁] {c_summary}",
                            "step_id": step_id,
                        }
                    )
                    yield _emit(
                        "claude_output",
                        {
                            "step_id": step_id,
                            "type": "tool_use",
                            "content": c_summary,
                            "tool_name": gev.get("name", ""),
                            "tool_input": gev.get("input", {}),
                        },
                    )
                    await _push_proglog(
                        "DEBUG",
                        f"门禁 tool_use: {gev.get('name', '')} {c_summary[:100]}",
                        step=step_id,
                    )
                elif evt_type == "thinking":
                    await _push_proglog(
                        "DEBUG",
                        f"门禁 thinking: {str(gev.get('content', ''))[:200]}",
                        step=step_id,
                    )
                elif evt_type == "tool_result":
                    tro = str(gev.get("output", ""))
                    if tro:
                        gate_tool_output += tro
                elif evt_type == "result":
                    csid = gev.get("claude_session_id", "")
                    if csid:
                        claude_session_id = csid
                    rc = gev.get("content", "")
                    await _push_proglog(
                        "INFO",
                        f"门禁 result 事件: content_len={len(rc)}, content={rc[:500]}",
                        step=step_id,
                    )
                    if rc:
                        gate_text += rc

            await _push_proglog(
                "INFO",
                f"门禁回复统计: {gate_event_count}, text长度={len(gate_text)}, tool_output长度={len(gate_tool_output)}",
                has_json_fence="```json" in gate_text,
                has_brace="{" in gate_text,
                step=step_id,
            )
            if gate_text.strip():
                await _push_proglog(
                    "INFO",
                    f"门禁回复全文(text+result):\n{gate_text[:2000]}",
                    step=step_id,
                )
            else:
                await _push_proglog("WARN", "门禁回复为空 (gate_text='')", step=step_id)
            if gate_tool_output.strip():
                await _push_proglog(
                    "INFO",
                    f"门禁 tool_output 全文:\n{gate_tool_output[:2000]}",
                    step=step_id,
                )

            gate_result = _parse_arbitrator_json(gate_text)
            gate_verdict = gate_result.get("verdict", "skipped")

            # 结构化存储裁判报告
            arb_issues = [
                ArbitratorIssue(
                    problem=iss.get("problem", ""),
                    severity=iss.get("severity", "HIGH"),
                    category=iss.get("category", "OTHER"),
                    suggestion=iss.get("suggestion", ""),
                    suggestion_action=iss.get("suggestion_action", ""),
                )
                for iss in (gate_result.get("issues") or [])
            ]
            arb_report = ArbitratorReport(
                session_id=session_id,
                step_id=step_id,
                verdict=gate_result.get("verdict", "unknown"),
                summary=gate_result.get("summary", ""),
                issues=arb_issues,
                raw_response=gate_text[:4000],
                parsing_success=gate_result.get("verdict", "unknown") != "unknown",
                detected_at=datetime.now().isoformat(),
            )
            await db.upsert_arbitrator_report(session_id, step_id, arb_report)

            # fallback: 如果 text/result 都没解析出 JSON，尝试从 tool_result 提取
            if gate_verdict == "skipped" and gate_tool_output.strip():
                await _push_proglog(
                    "INFO",
                    f"门禁 fallback: 从 tool_result 提取JSON, output_len={len(gate_tool_output)}",
                    step=step_id,
                )
                fallback_result = _parse_arbitrator_json(gate_tool_output)
                if fallback_result.get("verdict") != "skipped":
                    gate_result = fallback_result
                    gate_verdict = gate_result.get("verdict", "skipped")
                    await _push_proglog(
                        "INFO",
                        f"门禁 fallback 成功: verdict={gate_verdict}",
                        step=step_id,
                    )

            gate_reasoning = gate_result.get("summary", "") or gate_result.get("reasoning", "")
            # 裁判判定：verdict=pass 且 issues 为空 → 通过；否则不通过
            gate_passed = gate_verdict == "pass" and not gate_result.get("issues")

            # 诊断：Claude 门禁响应解析失败时输出原始文本
            if gate_verdict == "skipped" and gate_text.strip():
                await _push_simlog(
                    {
                        "time": _ts(),
                        "type": "warn",
                        "text": f"⚠️ Claude 门禁响应无法解析为JSON, 原始文本前200字: {gate_text[:200]}",
                    }
                )
                await _push_proglog(
                    "WARN", "门禁JSON解析失败", raw_text=gate_text[:500], step=step_id
                )
            elif not gate_text.strip():
                await _push_simlog(
                    {
                        "time": _ts(),
                        "type": "warn",
                        "text": "⚠️ Claude 门禁无文本输出（可能超时或错误）",
                    }
                )
                await _push_proglog("WARN", "门禁无文本输出", step=step_id)

            # gate_check 在宿主机跑，把容器内 /platform-artifacts 路径换成宿主机实际路径
            host_artifacts = [a.replace("/platform-artifacts", _artifacts_dir) for a in artifacts]
            file_gate = _gate_check(work_dir, host_artifacts)
            gate = {
                "passed": gate_passed,
                "skipped": False,
                "artifacts": file_gate["artifacts"],
                "gate_text": gate_text[:2000],
                "gate_tool_output": gate_tool_output[:2000],
            }
            step["gate_passed"] = gate_passed
            step["gate_artifacts"] = file_gate["artifacts"]

            # 结构化存储门禁记录
            await _push_gate_record(
                {
                    "step_id": step_id,
                    "step_name": step_name,
                    "timestamp": datetime.now().isoformat(),
                    "phase": "gate_check",
                    "artifacts_expected": list(artifacts),
                    "claude_response_raw": gate_text[:4000],
                    "claude_response_len": len(gate_text),
                    "event_counts": gate_event_count,
                    "has_json_fence": "```json" in gate_text,
                    "has_brace": "{" in gate_text,
                    "parsed_verdict": gate_verdict,
                    "parsed_reasoning": gate_reasoning[:500],
                    "parsed_missing_core": gate_result.get("missing_core", []),
                    "parsed_suggestion": gate_result.get("suggestion", "")[:500],
                    "file_gate_artifacts": file_gate["artifacts"],
                    "gate_passed": gate_passed,
                }
            )

            await _push_simlog(
                {
                    "time": _ts(),
                    "type": "info",
                    "text": f"🤖 Claude 门禁: {gate_verdict} — {gate_reasoning[:100]}",
                }
            )
            await _push_proglog(
                "INFO",
                f"门禁判定: {gate_verdict}",
                reasoning=gate_reasoning[:200],
                step=step_id,
            )
            yield _emit(
                "ai_gate",
                {
                    "step_id": step_id,
                    "verdict": gate_verdict,
                    "reasoning": gate_reasoning,
                    "found_files": [
                        f["name"]
                        for f in gate_result.get("files", [])
                        if f.get("exists")
                    ],
                    "missing_core": gate_result.get("missing_core", []),
                },
            )

            if not gate_passed:
                missing = [a["name"] for a in file_gate["artifacts"] if not a["exists"]]
                existing = [a["name"] for a in file_gate["artifacts"] if a["exists"]]
                # 从裁判 JSON 的 issues 构建断点 alerts（含 problem + suggestion + suggestion_action）
                issues = gate_result.get("issues", []) or []
                if issues:
                    for issue in issues:
                        await _push_alert(
                            {
                                "type": "ARBITRATOR",
                                "severity": issue.get("severity", "HIGH"),
                                "step_id": step_id,
                                "message": issue.get("problem", ""),
                                "root_cause": gate_reasoning or issue.get("category", "OTHER"),
                                "suggestion": issue.get("suggestion", ""),
                                "suggestion_action": issue.get("suggestion_action", ""),
                                "error_category": issue.get("category", "OTHER"),
                                "detected_at": datetime.now().isoformat(),
                            }
                        )
                        yield _emit("breakpoint_alert", alerts[-1])
                    await _push_proglog(
                        "WARN",
                        f"裁判发现 {len(issues)} 个断点: {gate_reasoning}",
                        step=step_id,
                    )
                else:
                    alert_msg = f"产出物缺失: {', '.join(missing)}" if missing else "门禁未通过(原因未知)"
                    await _push_alert(
                        {
                            "type": "ARTIFACT_MISSING",
                            "severity": "HIGH",
                            "step_id": step_id,
                            "message": alert_msg,
                            "root_cause": f"裁判: {gate_reasoning}" if gate_reasoning else f"原始响应: {gate_text[:300]}",
                            "error_category": "SKILL",
                            "detected_at": datetime.now().isoformat(),
                        }
                    )
                    yield _emit("breakpoint_alert", alerts[-1])
                    await _push_proglog(
                        "WARN",
                        f"门禁未通过: {alert_msg}",
                        reasoning=gate_reasoning[:200] or gate_text[:200],
                        step=step_id,
                    )

                # ===== 裁判分析 + 同会话修复 =====
                fix_prompt = f"""门禁检查未通过。请先以裁判视角分析问题，输出结构化断点报告，然后逐一修复。

## 裁判分析（先输出 JSON 断点报告）
严格输出以下 JSON（不要包含其他内容）：
```json
{{
  "verdict": "fail",
  "issues": [
    {{
      "problem": "问题描述（中文）",
      "severity": "CRITICAL" | "HIGH" | "MEDIUM" | "LOW",
      "category": "MISSING_FILE" | "CONTENT_INCOMPLETE" | "WRONG_PATH" | "SKILL_NOT_USED" | "ENV_MISSING" | "CONSTRAINT_VIOLATION" | "COMPILE_ERROR" | "OTHER",
      "suggestion": "具体修复建议（中文，直接可执行）",
      "suggestion_action": "具体的修复命令或文件创建指令"
    }}
  ],
  "summary": "总体评价"
}}
```

## 门禁检查结果
判断依据：{gate_reasoning}
缺失核心要素：{", ".join(gate_result.get("missing_core", [])) or "未具体标注"}
修正建议：{gate_result.get("suggestion", "")}
产出物缺失：{", ".join(missing) if missing else "无"}
已有但不达标：{", ".join(existing) if existing else "无"}

## 算子信息
- 算子名称：{op_name}
- 需求描述：{op_spec[:1000]}

## 原始步骤要求（prompt）
{prompt[:3000]}

## 执行要求
1. 先输出上述 JSON 断点报告
2. 然后根据分析结果逐一修复所有问题
3. 确保所有交付物文件存在且内容满足步骤要求（每个文件必须有实质内容，不得为空或仅含模板占位符）
4. 完成后确认每个文件都已正确写入"""

                yield _emit(
                    "fix_start", {"step_id": step_id, "missing": missing}
                )

                fix_text = ""  # 收集 fix claude 的完整文本输出，用于解析裁判 JSON

                async for cev in claude_driver.run_step(
                    session_id,
                    fix_prompt,
                    work_dir,
                    timeout=step_timeout,
                    step_id=f"{step_id}_fix",
                    persist_proc_on_consumer_exit=True,
                    resume_session_id=claude_session_id,
                    docker_container=docker_container if _container_ready else "",
                ):
                    fix_entry = None
                    if cev["type"] == "tool_use":
                        c_summary = _summarize_tool_use(
                            cev.get("name", ""), cev.get("input", {})
                        )
                        fix_entry = {
                            "time": _ts(),
                            "step_id": step_id,
                            "type": "tool_use",
                            "content": c_summary,
                            "tool_name": cev.get("name", ""),
                        }
                        await _push_term(
                            {
                                "time": _ts(),
                                "type": "tool_use",
                                "content": f"[补齐] {c_summary}",
                                "step_id": step_id,
                            }
                        )
                    elif cev["type"] in ("text", "thinking"):
                        c_content_full = str(cev.get("content", ""))
                        c_content = c_content_full[:500]
                        fix_text += c_content_full  # 累加完整文本供裁判 JSON 解析
                        fix_entry = {
                            "time": _ts(),
                            "step_id": step_id,
                            "type": cev["type"],
                            "content": c_content,
                        }
                        await _push_term(
                            {
                                "time": _ts(),
                                "type": cev["type"],
                                "content": c_content,
                                "step_id": step_id,
                            }
                        )
                    elif cev["type"] == "tool_result":
                        c_content = str(cev.get("output", ""))[:500]
                        fix_entry = {
                            "time": _ts(),
                            "step_id": step_id,
                            "type": "tool_result",
                            "content": c_content,
                        }
                    elif cev["type"] == "result":
                        ct = cev.get("tokens", {})
                        if isinstance(ct, dict):
                            all_tokens["input"] += ct.get("input", 0)
                            all_tokens["output"] += ct.get("output", 0)
                        csid = cev.get("claude_session_id", "")
                        if csid:
                            claude_session_id = csid
                    if fix_entry:
                        await db.append_workflow_sim_v2_log(
                            session_id, "fix_log", [fix_entry]
                        )
                        yield _emit("fix_output", fix_entry)

                # 从 fix claude 输出中解析裁判 JSON（断点 + 解决方案），记录到 alerts
                arbitrator = _parse_arbitrator_json(fix_text)
                if arbitrator.get("issues"):
                    for issue in arbitrator["issues"]:
                        await _push_alert(
                            {
                                "type": "ARBITRATOR",
                                "severity": issue.get("severity", "HIGH"),
                                "step_id": step_id,
                                "message": issue.get("problem", ""),
                                "suggestion": issue.get("suggestion", ""),
                                "suggestion_action": issue.get("suggestion_action", ""),
                                "root_cause": arbitrator.get("summary", ""),
                                "error_category": issue.get("category", "OTHER"),
                                "detected_at": datetime.now().isoformat(),
                            }
                        )
                        yield _emit("breakpoint_alert", alerts[-1])
                    await _push_proglog(
                        "WARN",
                        f"裁判发现 {len(arbitrator['issues'])} 个断点: {arbitrator.get('summary', '')}",
                        step=step_id,
                    )

                # 修复后 Claude 复查
                await _push_simlog(
                    {
                        "time": _ts(),
                        "type": "info",
                        "text": "🔍 补齐后 Claude 复查中...",
                    }
                )
                await _push_proglog("INFO", "修复完成, 启动 Claude 复查", step=step_id)
                re_gate_text = ""
                re_gate_tool_output = ""
                async for gev in claude_driver.run_step(
                    session_id,
                    gate_prompt,
                    work_dir,
                    timeout=step_timeout,
                    step_id=f"{step_id}_regate",
                    persist_proc_on_consumer_exit=True,
                    resume_session_id=claude_session_id,
                    docker_container=docker_container if _container_ready else "",
                ):
                    if gev["type"] == "text":
                        re_gate_text += gev.get("content", "")
                    elif gev["type"] == "tool_result":
                        tro = str(gev.get("output", ""))
                        if tro:
                            re_gate_tool_output += tro
                    elif gev["type"] == "result":
                        csid = gev.get("claude_session_id", "")
                        if csid:
                            claude_session_id = csid
                        rc = gev.get("content", "")
                        if rc:
                            re_gate_text += rc

                re_result = _parse_claude_gate(re_gate_text)
                if (
                    re_result.get("verdict") == "skipped"
                    and re_gate_tool_output.strip()
                ):
                    fallback = _parse_claude_gate(re_gate_tool_output)
                    if fallback.get("verdict") != "skipped":
                        re_result = fallback
                re_passed = re_result.get("verdict") == "passed"
                host_artifacts = [a.replace("/platform-artifacts", _artifacts_dir) for a in artifacts]
                file_gate = _gate_check(work_dir, host_artifacts)
                gate["passed"] = re_passed
                gate["artifacts"] = file_gate["artifacts"]
                step["gate_passed"] = re_passed
                step["gate_artifacts"] = file_gate["artifacts"]

                # 结构化存储补齐后复查记录
                await _push_gate_record(
                    {
                        "step_id": step_id,
                        "step_name": step_name,
                        "timestamp": datetime.now().isoformat(),
                        "phase": "re_check_after_fix",
                        "artifacts_expected": list(artifacts),
                        "claude_response_raw": re_gate_text[:4000],
                        "claude_response_len": len(re_gate_text),
                        "has_json_fence": "```json" in re_gate_text,
                        "has_brace": "{" in re_gate_text,
                        "parsed_verdict": re_result.get("verdict", "skipped"),
                        "parsed_reasoning": re_result.get("reasoning", "")[:500],
                        "file_gate_artifacts": file_gate["artifacts"],
                        "gate_passed": re_passed,
                    }
                )

                fix_result = {
                    "step_id": step_id,
                    "passed": re_passed,
                    "missing": [
                        a["name"] for a in file_gate["artifacts"] if not a["exists"]
                    ],
                }
                if re_passed:
                    await _push_simlog(
                        {
                            "time": _ts(),
                            "type": "success",
                            "text": f"✅ 补齐后 Claude 门禁通过 — {re_result.get('reasoning', '')[:80]}",
                        }
                    )
                else:
                    await _push_simlog(
                        {
                            "time": _ts(),
                            "type": "warn",
                            "text": f"补齐后 Claude 门禁仍不达标 — {re_result.get('reasoning', '')[:80]}",
                        }
                    )
                yield _emit("fix_done", fix_result)

        yield _emit(
            "gate_check",
            {
                "step_id": step_id,
                "passed": gate["passed"],
                "artifacts": gate["artifacts"],
            },
        )

        subagent_harvest = _harvest_subagent_skill_refs(work_dir, step_start_time)
        if subagent_harvest["skills"]:
            await _push_simlog(
                {
                    "time": _ts(),
                    "type": "info",
                    "text": f"  Subagent 内部 Skill 捕获: {', '.join(subagent_harvest['skills'])} (扫描 {subagent_harvest['files_scanned']} 个 subagent jsonl)",
                }
            )
        compliance = _compute_skill_compliance(
            events, required_skills, extra_referenced=subagent_harvest["skills"]
        )
        step["skill_compliance"] = compliance

        if compliance["violations"]:
            for v in compliance["violations"]:
                await _push_alert(
                    {
                        "type": "SKILL_NOT_REFERENCED",
                        "severity": v.get("severity", "MED"),
                        "step_id": step_id,
                        "message": v["detail"],
                        "root_cause": f"步骤要求的 Skill 文件未被 Claude 读取引用。可能是 Skill 未安装到工作目录的 .claude/ 目录，或 prompt 中缺少 Skill 引用指令。",
                        "suggestion": "确认 Skill 已通过 `bash init.sh project claude` 正确安装到工作目录的 .claude/skills/ 或 .claude/agents/ 目录下",
                        "error_category": "SKILL",
                        "detected_at": datetime.now().isoformat(),
                    }
                )

        yield _emit("skill_compliance", {"step_id": step_id, **compliance})

        monitor_result = await _monitor_skill_compliance(
            events, required_skills, plugin_id, step_name
        )
        if monitor_result.get("overall_score", -1) >= 0:
            step["monitor_insight"] = monitor_result
            yield _emit("monitor_insight", {"step_id": step_id, **monitor_result})
            score = monitor_result.get("overall_score", "?")
            log_type = (
                "success"
                if isinstance(score, (int, float)) and score >= 80
                else "warn"
                if isinstance(score, (int, float)) and score >= 50
                else "error"
            )
            await _push_simlog(
                {
                    "time": _ts(),
                    "type": log_type,
                    "text": f"  监控 LLM 语义遵从度: {score}分",
                }
            )
            for sa in monitor_result.get("skills_analysis", []):
                status_cn = {
                    "compliant": "合规",
                    "partial": "部分",
                    "violation": "违规",
                    "not_detected": "未检测",
                }.get(sa.get("status"), sa.get("status"))
                sa_type = (
                    "success"
                    if sa["status"] == "compliant"
                    else "warn"
                    if sa["status"] == "partial"
                    else "error"
                )
                await _push_simlog(
                    {
                        "time": _ts(),
                        "type": sa_type,
                        "text": f"    [{status_cn}] {sa.get('skill', '?')}: {sa.get('detail', '')}",
                    }
                )
            for w in monitor_result.get("warnings", []):
                await _push_simlog(
                    {"time": _ts(), "type": "warn", "text": f"    警告: {w}"}
                )

        step["status"] = "completed"
        step["duration_ms"] = step_duration
        step["output"] = "\n".join(step_output_parts)[-20000:]
        step["events"] = [
            {
                "type": e["type"],
                "name": e.get("name", ""),
                "content": str(e.get("content", ""))[:500],
                "input": e.get("input") if e.get("type") == "tool_use" else None,
            }
            for e in events
            if e.get("type")
            not in (
                "message_start",
                "message_delta",
                "message_stop",
                "text_start",
                "thinking_start",
            )
        ]
        step["completed_at"] = datetime.now().isoformat()
        final_proc = claude_driver.get_process_info(session_id)
        if final_proc:
            step["process"] = final_proc
            if final_proc.get("exit_code") not in (0, None) and not step.get(
                "error_detail"
            ):
                proc_error = (
                    final_proc.get("error", "")
                    or f"进程异常退出 (exit code {final_proc['exit_code']})"
                )
                step["error_detail"] = _classify_error(
                    proc_error, exit_code=final_proc["exit_code"]
                )
                if step["error_detail"]["category"] in (
                    "CLI",
                    "TIMEOUT",
                    "ENV",
                    "UNKNOWN",
                ):
                    step["status"] = "failed"
                await _push_alert(
                    {
                        "type": step["error_detail"]["category"],
                        "severity": "HIGH",
                        "step_id": step_id,
                        "message": proc_error,
                        "root_cause": step["error_detail"]["root_cause"],
                        "suggestion": step["error_detail"]["suggestion"],
                        "error_category": step["error_detail"]["category"],
                        "detected_at": datetime.now().isoformat(),
                    }
                )
                yield _emit("breakpoint_alert", alerts[-1])

        step_final_fields = {
            "status": step["status"],
            "duration_ms": step["duration_ms"],
            "output": step["output"],
            "events": step["events"],
            "completed_at": step["completed_at"],
            "gate_passed": step["gate_passed"],
            "gate_artifacts": step["gate_artifacts"],
            "skill_compliance": step["skill_compliance"],
            "token_usage": step.get("token_usage", {}),
        }
        if step.get("monitor_insight"):
            step_final_fields["monitor_insight"] = step["monitor_insight"]
        if final_proc:
            step_final_fields["process"] = final_proc
        if step.get("error_detail"):
            step_final_fields["error_detail"] = step["error_detail"]
        await db.update_workflow_sim_v2_step(session_id, step_id, step_final_fields)

        gate_info = f"门禁{'通过' if gate['passed'] is True else '跳过' if gate['passed'] is None else '未通过'}"
        err_info = (
            f" [{step['error_detail']['category']}]" if step.get("error_detail") else ""
        )
        await _push_simlog(
            {
                "time": _ts(),
                "type": "success" if not step.get("error_detail") else "warn",
                "text": f"{step_id} 完成 ({step_duration}ms, {gate_info}){err_info}",
            }
        )

        agents_used = set()
        for e in events:
            if e.get("type") == "tool_use" and e.get("name") == "Agent":
                at = (e.get("input") or {}).get("subagent_type", "")
                if at:
                    agents_used.add(at)
        skills_used = set(ClaudeCodeDriver.extract_skill_references(events))
        subagent_skills = set(subagent_harvest.get("skills", []))
        all_skills = skills_used | subagent_skills
        if agents_used:
            await _push_simlog(
                {
                    "time": _ts(),
                    "type": "info",
                    "text": f"  调用 Agent: {', '.join(sorted(agents_used))}",
                }
            )
        if all_skills:
            skill_parts = (
                [f"顶层: {', '.join(sorted(skills_used))}"] if skills_used else []
            )
            if subagent_skills:
                skill_parts.append(f"subagent: {', '.join(sorted(subagent_skills))}")
            await _push_simlog(
                {
                    "time": _ts(),
                    "type": "info",
                    "text": f"  引用 Skill: {' | '.join(skill_parts)}",
                }
            )

        step_done_data = {
            "step_id": step_id,
            "status": "completed",
            "duration_ms": step_duration,
            "gate_passed": gate["passed"],
            "gate_text": gate.get("gate_text", ""),
            "gate_tool_output": gate.get("gate_tool_output", ""),
            "token_usage": step.get("token_usage", {}),
            "skill_compliance_score": compliance["score"],
        }
        if step.get("error_detail"):
            step_done_data["error_detail"] = step["error_detail"]
        yield _emit("step_done", step_done_data)
        await _push_proglog(
            "INFO" if gate["passed"] else "WARN",
            f"Step 完成: {step_id}",
            duration_ms=step_duration,
            gate_passed=gate["passed"],
            gate_text=gate.get("gate_text", "")[:500],
            gate_tool_output=gate.get("gate_tool_output", "")[:500],
            tokens=step.get("token_usage", {}),
        )

        new_jsonl_lines, jsonl_offsets = _harvest_new_jsonl_lines(
            work_dir, jsonl_offsets
        )
        if new_jsonl_lines:
            await db.append_workflow_sim_v2_log(
                session_id, "jsonl_log", new_jsonl_lines
            )

        # 阀门：达到 max_steps 后跳过后续步骤
        if step_id == _stop_after and step["status"] == "completed":
            await _push_proglog("INFO", f"阀门触发: max_steps={_max_steps}, 在 {step_id} 后停止")
            for _s in steps[i + 1:]:
                _s["status"] = "skipped"
                await db.update_workflow_sim_v2_step(session_id, _s["step_id"], {"status": "skipped"})
                await _push_simlog({"time": _ts(), "type": "info", "text": f"{_s['step_id']} 跳过（阀门: {_max_steps}）"})
            break

    final_jsonl_lines, jsonl_offsets = _harvest_new_jsonl_lines(work_dir, jsonl_offsets)
    if final_jsonl_lines:
        await db.append_workflow_sim_v2_log(session_id, "jsonl_log", final_jsonl_lines)

    # summary 统计只针对插件步骤，排除外部生命周期步骤（clone/NPU/CI-CD）
    # summary 只统计插件开发流程，排除 external（前端展示用）和 platform（平台注入的安装环境步骤）
    plugin_steps = [s for s in steps if s.get("step_type") not in ("external", "platform")]
    completed_steps = [s for s in plugin_steps if s.get("status") == "completed"]
    failed_steps = [
        s
        for s in plugin_steps
        if s.get("status") == "failed"
        or (s.get("status") == "completed" and s.get("gate_passed") is False)
    ]
    passed_steps = [s for s in completed_steps if s.get("gate_passed") is True]
    ungated_steps = [s for s in completed_steps if s.get("gate_passed") is None]
    gated_steps = passed_steps + [
        s for s in completed_steps if s.get("gate_passed") is False
    ]

    summary = {
        "session_id": session_id,
        "total_steps": len(plugin_steps),
        "completed_steps": len(completed_steps),
        "passed_steps": len(passed_steps),
        "failed_steps": len(failed_steps),
        "ungated_steps": len(ungated_steps),
        "gated_total": len(gated_steps),
        "total_alerts": len(alerts),
        "critical_alerts": len([a for a in alerts if a.get("severity") == "CRITICAL"]),
        "total_tokens": all_tokens,
        "verdict": "PASS"
        if not failed_steps and not alerts
        else "PASS_WITH_ISSUES"
        if not failed_steps
        else "FAIL",
    }

    await _push_simlog(
        {
            "time": _ts(),
            "type": "info",
            "text": f"仿真完成 — {summary['verdict']}, {summary['passed_steps']}/{summary['total_steps']} 步通过",
        }
    )
    await db.update_workflow_sim_v2_session(
        session_id,
        {
            "status": "completed",
            "summary": summary,
            "completed_at": datetime.now().isoformat(),
        },
    )
    yield _emit("summary", summary)
    await _push_proglog(
        "INFO",
        f"仿真结束: verdict={summary.get('verdict')}, passed={summary.get('passed_steps')}/{summary.get('total_steps')}",
    )

    # --- Pipeline CI/CD Integration ---
    auto_pipeline = session.get("auto_pipeline", False)
    if auto_pipeline and gitcode_token and summary.get("verdict") != "FAIL":
        try:
            from app.services.pipeline_service import GitCodePipelineClient

            fork_owner, fork_repo = "", ""
            fork_info = session.get("fork_info") or {}
            fork_path = fork_info.get("fork_path", "")
            if fork_path and "/" in fork_path:
                fork_owner, fork_repo = fork_path.split("/", 1)
            if not fork_owner and work_dir:
                remote_result = await _run_git(
                    "remote", "get-url", "origin", cwd=work_dir
                )
                if remote_result["returncode"] == 0:
                    m = re.search(
                        r"[:/]([^/]+/[^/]+?)(?:\.git)?$",
                        remote_result["stdout"].strip(),
                    )
                    if m:
                        fork_owner, fork_repo = m.group(1).split("/", 1)

            client = GitCodePipelineClient(token=gitcode_token)

            upstream_owner, upstream_repo = "", ""
            repo_url = session.get("repo_url", "")
            if repo_url:
                m = re.search(r"[:/]([^/]+/[^/]+?)(?:\.git)?$", repo_url)
                if m:
                    upstream_owner, upstream_repo = m.group(1).split("/", 1)
            if not upstream_owner and work_dir:
                upstream_result = await _run_git(
                    "remote", "get-url", "upstream", cwd=work_dir
                )
                if upstream_result["returncode"] == 0:
                    m = re.search(
                        r"[:/]([^/]+/[^/]+?)(?:\.git)?$",
                        upstream_result["stdout"].strip(),
                    )
                    if m:
                        upstream_owner, upstream_repo = m.group(1).split("/", 1)
            if not upstream_owner and fork_owner:
                try:
                    info = await client.get_repo_info(fork_owner, fork_repo)
                    if info.get("parent_owner"):
                        upstream_owner, upstream_repo = (
                            info["parent_owner"],
                            info["parent_repo"],
                        )
                except Exception as e:
                    logger.warning(f"[pipeline] auto: 查询 fork info 失败: {e}")

            if not fork_owner:
                fork_owner, fork_repo = upstream_owner, upstream_repo
            if not upstream_owner:
                upstream_owner, upstream_repo = fork_owner, fork_repo

            if f"{upstream_owner}/{upstream_repo}" == f"{fork_owner}/{fork_repo}":
                await _push_simlog(
                    {
                        "time": _ts(),
                        "type": "warn",
                        "text": "Pipeline 跳过: 无法确定上游仓库，请添加 upstream remote",
                    }
                )
            else:
                branch_result = await _run_git(
                    "rev-parse", "--abbrev-ref", "HEAD", cwd=work_dir
                )
                source_branch = (
                    branch_result["stdout"]
                    if branch_result["returncode"] == 0
                    else "main"
                )
                target_branch = "main"
                try:
                    upstream_info = await client.get_repo_info(
                        upstream_owner, upstream_repo
                    )
                    if upstream_info.get("default_branch"):
                        target_branch = upstream_info["default_branch"]
                except Exception:
                    pass

                existing_mr_iid = ""
                existing_mr_url = ""
                existing_mr = await client.find_open_mr(
                    upstream_owner, upstream_repo, source_branch, fork_owner=fork_owner
                )
                if existing_mr:
                    existing_mr_iid = str(existing_mr["mr_iid"])
                    existing_mr_url = existing_mr["mr_url"]

                if fork_owner and fork_repo:
                    async for event in client.run_pipeline_lifecycle(
                        work_dir=work_dir,
                        owner=fork_owner,
                        repo=fork_repo,
                        source_branch=source_branch,
                        target_branch=target_branch,
                        op_name=op_name,
                        op_spec=session.get("op_spec", ""),
                        session_id=session_id,
                        upstream_owner=upstream_owner,
                        upstream_repo=upstream_repo,
                        fork_owner=fork_owner,
                        fork_repo=fork_repo,
                        existing_mr_iid=existing_mr_iid,
                        existing_mr_url=existing_mr_url,
                        cancel_check=lambda sid=session_id: _pipeline_cancel_flags.get(
                            sid, False
                        ),
                    ):
                        sse_event = event.get("sse_event", "")
                        event_data = event.get("data", {})
                        if sse_event:
                            yield _emit(sse_event, event_data)
                        if (
                            sse_event == "pipeline_done"
                            and event_data.get("status") == "cancelled"
                        ):
                            _pipeline_cancel_flags.pop(session_id, None)
                            break
                        if db:
                            current_session = await db.get_workflow_sim_v2_session(
                                session_id
                            )
                            if current_session:
                                pipeline = current_session.get("pipeline", {})
                                if sse_event == "pipeline_start":
                                    pipeline["status"] = "running"
                                    pipeline["mr_url"] = event_data.get("mr_url")
                                    pipeline["mr_iid"] = event_data.get("mr_iid")
                                    pipeline["triggered_at"] = event_data.get(
                                        "triggered_at"
                                    )
                                    pipeline["steps"] = event_data.get(
                                        "steps", pipeline.get("steps", [])
                                    )
                                elif sse_event == "pipeline_step_update":
                                    pipeline["steps"] = event_data.get(
                                        "steps", pipeline.get("steps", [])
                                    )
                                    pipeline["mr_url"] = event_data.get(
                                        "mr_url", pipeline.get("mr_url")
                                    )
                                    pipeline["mr_iid"] = event_data.get(
                                        "mr_iid", pipeline.get("mr_iid")
                                    )
                                elif sse_event == "pipeline_done":
                                    pipeline["status"] = event_data.get("status")
                                    pipeline["completed_at"] = event_data.get(
                                        "completed_at"
                                    )
                                    pipeline["steps"] = event_data.get(
                                        "steps", pipeline.get("steps", [])
                                    )
                                elif sse_event == "pipeline_fix_round":
                                    fix_rounds = pipeline.get("fix_rounds", [])
                                    fix_rounds.append(event_data)
                                    pipeline["fix_rounds"] = fix_rounds
                                await db.update_workflow_sim_v2_session(
                                    session_id, {"pipeline": pipeline}
                                )
                else:
                    await _push_simlog(
                        {
                            "time": _ts(),
                            "type": "warn",
                            "text": "Pipeline 跳过: 无法解析 owner/repo",
                        }
                    )

        except Exception as e:
            logger.error(f"Pipeline 执行异常: {e}", exc_info=True)
            await _push_simlog(
                {"time": _ts(), "type": "error", "text": f"Pipeline 异常: {e}"}
            )
            yield _emit(
                "pipeline_done",
                {
                    "status": "failed",
                    "error": str(e),
                    "completed_at": datetime.now().isoformat(),
                },
            )


async def execute_session_task(session_id: str, db, gitcode_token: str = ""):
    """后台执行仿真：消费 drive_session_events 的事件，publish 到 bus。"""
    bus = _get_or_create_bus(session_id)
    session = await db.get_workflow_sim_v2_session(session_id)
    if not session:
        bus.mark_finished()
        return
    try:
        async for _ev in drive_session_events(
            session_id, session, db, gitcode_token, bus
        ):
            pass
    except asyncio.CancelledError:
        logger.info(f"[exec] session {session_id} 被取消")
        bus.publish({"event": "session_cancelled", "data": {}})
        raise
    except Exception as e:
        logger.exception(f"[exec] session {session_id} 执行异常")
        try:
            await db.update_workflow_sim_v2_session(
                session_id,
                {"status": "failed", "completed_at": datetime.now().isoformat()},
            )
        except Exception:
            pass
        bus.publish({"event": "error", "data": {"error": str(e)}})
    finally:
        bus.mark_finished()
        _active_session_tasks.pop(session_id, None)
        # 清理 Docker 容器
        _ctn = f"cann-sim-{session_id}"
        try:
            await asyncio.create_subprocess_exec("docker", "rm", "-f", _ctn).communicate()
        except Exception:
            pass


def ensure_session_task_running(
    session_id: str, session: dict, db, gitcode_token: str = ""
) -> bool:
    """若该 session 没有活跃后台 Task 则启动一个（幂等）。"""
    existing = _active_session_tasks.get(session_id)
    if existing is not None and not existing.done():
        return False
    _get_or_create_bus(session_id)
    task = asyncio.create_task(execute_session_task(session_id, db, gitcode_token))
    _active_session_tasks[session_id] = task
    task.add_done_callback(lambda t: _active_session_tasks.pop(session_id, None))
    return True
