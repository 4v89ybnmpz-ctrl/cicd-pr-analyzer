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

from .workflow_sim_v2_helpers import (
    render_prompt as _render_prompt,
    summarize_tool_use as _summarize_tool_use,
    classify_error as _classify_error,
    gate_check as _gate_check,
    run_git as _run_git,
    get_or_create_bus as _get_or_create_bus,
    _pipeline_cancel_flags,
    _active_session_tasks,
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
            prompt = prompt_template.replace("{work_dir}", work_dir) \
                .replace("{gitcode_token}", gitcode_token or "") \
                .replace("{repo_url}", session.get("repo_url", "") or "") \
                .replace("{fork_path}", _fork_info.get("fork_path", "") or "")
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
            gate_prompt = f"""请对本步骤的交付物进行门禁检查。

## 预期交付物
{artifact_list_str}

## 步骤要求（prompt）
{prompt[:3000]}

## 检查要求
1. 对每个文件，使用 Read 工具检查是否存在且内容不为空
2. 评估内容是否满足步骤要求中的核心要素
3. 不得仅凭文件名判断，必须读取实际内容

## 判定规则
- 文件存在且内容满足要求 → passed
- 文件不存在但有等价产出覆盖核心要素 → passed
- 文件存在但内容不完整（空、仅标题、模板未填） → failed
- 文件不存在且无等价产出 → failed

## 输出方式（重要）
完成检查后，直接在你的回复文本中输出以下JSON。禁止使用 Bash/cat/echo 等工具输出JSON，必须作为你的文本回复直接输出。

请严格按以下JSON格式输出判定结果：
```json
{{
  "verdict": "passed" | "failed",
  "reasoning": "判断依据",
  "files": [
    {{"name": "文件路径", "exists": true, "adequate": true, "issue": ""}}
  ],
  "missing_core": ["缺失的核心要素"],
  "suggestion": "如failed，给出修正建议"
}}
```"""

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

            gate_result = _parse_claude_gate(gate_text)
            gate_verdict = gate_result.get("verdict", "skipped")

            # fallback: 如果 text/result 都没解析出 JSON，尝试从 tool_result 提取
            if gate_verdict == "skipped" and gate_tool_output.strip():
                await _push_proglog(
                    "INFO",
                    f"门禁 fallback: 从 tool_result 提取JSON, output_len={len(gate_tool_output)}",
                    step=step_id,
                )
                fallback_result = _parse_claude_gate(gate_tool_output)
                if fallback_result.get("verdict") != "skipped":
                    gate_result = fallback_result
                    gate_verdict = gate_result.get("verdict", "skipped")
                    await _push_proglog(
                        "INFO",
                        f"门禁 fallback 成功: verdict={gate_verdict}",
                        step=step_id,
                    )

            gate_reasoning = gate_result.get("reasoning", "")
            gate_passed = gate_verdict == "passed"

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

            file_gate = _gate_check(work_dir, artifacts)
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
                if gate_verdict == "skipped":
                    if missing:
                        alert_msg = f"AI门禁解析失败且产出物缺失: {', '.join(missing)}"
                    else:
                        alert_msg = (
                            f"AI门禁解析失败(产出物已存在): {', '.join(existing)}"
                        )
                elif missing:
                    alert_msg = f"产出物缺失: {', '.join(missing)}"
                elif existing:
                    alert_msg = f"产出物内容不达标: {', '.join(existing)}"
                else:
                    alert_msg = "门禁未通过(原因未知)"
                root_cause = (
                    f"Claude 门禁: {gate_reasoning}"
                    if gate_reasoning
                    else f"门禁解析失败, 原始响应: {gate_text[:300]}"
                )
                await _push_alert(
                    {
                        "type": "ARTIFACT_MISSING",
                        "severity": "HIGH",
                        "step_id": step_id,
                        "message": alert_msg,
                        "root_cause": root_cause,
                        "suggestion": gate_result.get("suggestion", ""),
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

                # ===== 同会话修复 =====
                fix_prompt = f"""门禁检查未通过。

判断依据：{gate_reasoning}
缺失核心要素：{", ".join(gate_result.get("missing_core", [])) or "未具体标注"}
修正建议：{gate_result.get("suggestion", "")}

## 算子信息
- 算子名称：{op_name}
- 需求描述：{op_spec[:1000]}

## 原始步骤要求（prompt）
{prompt[:3000]}

请立即修正上述问题，确保所有交付物文件存在且内容满足步骤要求。每个文件必须有实质内容，不得为空或仅含模板占位符。完成后确认每个文件都已正确写入。"""

                yield _emit(
                    "fix_start", {"step_id": step_id, "missing": missing or inadequate}
                )

                async for cev in claude_driver.run_step(
                    session_id,
                    fix_prompt,
                    work_dir,
                    timeout=step_timeout,
                    step_id=f"{step_id}_fix",
                    persist_proc_on_consumer_exit=True,
                    resume_session_id=claude_session_id,
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
                        c_content = str(cev.get("content", ""))[:500]
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
                file_gate = _gate_check(work_dir, artifacts)
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
