"""
算子辅助开发 V2 — 会话管理 + 步骤执行 + SSE 实时流
封装 README 4 步操作：克隆仓库 → 安装插件 → 验证安装 → 执行开发
"""
import asyncio
import json
import logging
import os
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# 内存中的活跃进程引用（用于停止）
_active_procs: dict[str, asyncio.subprocess.Process] = {}

# CANNBot 仓库路径
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
CANNBOT_DIR = PROJECT_ROOT / "external" / "cannbot-skills"


class CreateSessionRequest(BaseModel):
    scenario: str = "ops-direct-invoke"
    tool: str = "claude"
    op_name: str = ""
    op_spec: str = ""
    work_dir: str = ""


STEPS_DEF = [
    {"step_id": "clone", "step_name": "克隆仓库"},
    {"step_id": "install", "step_name": "安装插件"},
    {"step_id": "verify", "step_name": "验证安装"},
    {"step_id": "execute", "step_name": "执行开发"},
]


def register_ops_dev_session_routes(router: APIRouter, db=None):
    """注册算子辅助开发会话路由"""

    @router.post("/cannbot/ops-dev/sessions")
    async def create_session(req: CreateSessionRequest):
        session_id = uuid.uuid4().hex[:8]
        # 所有会话共用 external/cannbot-skills 目录（和 Skill 测试 Tab 共用）
        work_dir = str(CANNBOT_DIR)
        now = datetime.now().isoformat()

        # 检测仓库是否已存在，自动标记 clone 步骤
        repo_exists = os.path.isdir(work_dir) and os.path.isdir(os.path.join(work_dir, ".git"))

        steps = []
        for s in STEPS_DEF:
            step_data = {
                "step_id": s["step_id"],
                "step_name": s["step_name"],
                "status": "pending",
                "command": "",
                "started_at": None,
                "completed_at": None,
                "output": "",
                "error": None,
                "events": [],
            }
            # 如果仓库已存在，clone 步骤直接标记完成
            if s["step_id"] == "clone" and repo_exists:
                step_data["status"] = "completed"
                step_data["command"] = "git pull (仓库已存在)"
                step_data["started_at"] = now
                step_data["completed_at"] = now
                step_data["output"] = f"仓库已存在: {work_dir}"
            steps.append(step_data)

        session = {
            "session_id": session_id,
            "scenario": req.scenario,
            "tool": req.tool,
            "op_name": req.op_name,
            "op_spec": req.op_spec,
            "work_dir": work_dir,
            "status": "in_progress",
            "created_at": now,
            "completed_at": None,
            "steps": steps,
        }

        if db:
            await db.save_ops_dev_session(session)
        return session

    @router.get("/cannbot/ops-dev/sessions")
    async def list_sessions(limit: int = 30):
        if not db:
            raise HTTPException(status_code=503, detail="数据库不可用")
        sessions = await db.get_ops_dev_sessions(limit=limit)
        # 返回概要
        summaries = []
        for s in sessions:
            steps_status = {st["step_id"]: st["status"] for st in s.get("steps", [])}
            summaries.append({
                "session_id": s.get("session_id", ""),
                "scenario": s.get("scenario", ""),
                "op_name": s.get("op_name", ""),
                "status": s.get("status", ""),
                "created_at": s.get("created_at", ""),
                "completed_at": s.get("completed_at", ""),
                "steps_status": steps_status,
            })
        return {"total": len(summaries), "sessions": summaries}

    @router.get("/cannbot/ops-dev/sessions/{session_id}")
    async def get_session(session_id: str):
        if not db:
            raise HTTPException(status_code=503, detail="数据库不可用")
        session = await db.get_ops_dev_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="会话未找到")
        return session

    @router.delete("/cannbot/ops-dev/sessions/{session_id}")
    async def delete_session(session_id: str):
        if not db:
            raise HTTPException(status_code=503, detail="数据库不可用")
        ok = await db.delete_ops_dev_session(session_id)
        if not ok:
            raise HTTPException(status_code=404, detail="会话未找到")
        return {"deleted": True}

    @router.post("/cannbot/ops-dev/sessions/{session_id}/steps/{step_id}/execute")
    async def execute_step(session_id: str, step_id: str):
        if not db:
            raise HTTPException(status_code=503, detail="数据库不可用")

        session = await db.get_ops_dev_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="会话未找到")

        # 查找目标步骤
        target = None
        for s in session["steps"]:
            if s["step_id"] == step_id:
                target = s
                break
        if not target:
            raise HTTPException(status_code=404, detail=f"步骤 {step_id} 未找到")

        # 检查依赖：前一步必须 completed
        step_order = ["clone", "install", "verify", "execute"]
        idx = step_order.index(step_id)
        if idx > 0:
            prev = session["steps"][idx - 1]
            if prev["status"] != "completed":
                raise HTTPException(
                    status_code=400,
                    detail=f"前置步骤 {prev['step_name']} 尚未完成 (状态: {prev['status']})",
                )

        # 构建命令
        scenario = session["scenario"]
        tool = session["tool"]
        op_name = session.get("op_name", "")
        op_spec = session.get("op_spec", "")
        work_dir = session.get("work_dir", "")

        if step_id == "clone":
            if os.path.isdir(work_dir) and os.path.isdir(os.path.join(work_dir, ".git")):
                # 仓库已存在，执行 git pull 更新
                cmd = ["git", "pull"]
                cwd = work_dir
            else:
                # 仓库不存在，clone 到 external/cannbot-skills
                cmd = ["git", "clone", "https://gitcode.com/cann/cannbot-skills.git", work_dir]
                cwd = str(PROJECT_ROOT / "external")
        elif step_id == "install":
            scenario_dir = os.path.join(work_dir, "plugins-official", scenario)
            init_sh = os.path.join(scenario_dir, "init.sh")
            install_sh = os.path.join(scenario_dir, "install.sh")
            script = init_sh if os.path.isfile(init_sh) else install_sh
            if not script or not os.path.isfile(script):
                raise HTTPException(status_code=400, detail=f"场景 {scenario} 未找到安装脚本")
            cmd = ["bash", os.path.basename(script), "project", tool]
            cwd = scenario_dir
        elif step_id == "verify":
            # 验证安装：检查 skills/agents/manifest/CLAUDE.md
            verify_dir = os.path.join(work_dir, "plugins-official", scenario)
            cmd = ["bash", "-c",
                   "echo '========== 验证安装 ==========' && "
                   "echo '' && "
                   "echo '--- Skills 目录 ---' && "
                   "if [ -d .claude/skills ]; then ls -1 .claude/skills/ && echo \"(共 $(ls -1 .claude/skills/ | wc -l | tr -d ' ') 个 skills)\"; else echo '⚠ 未找到 .claude/skills/'; fi && "
                   "echo '' && "
                   "echo '--- Agents 目录 ---' && "
                   "if [ -d .claude/agents ]; then ls -1 .claude/agents/ && echo \"(共 $(ls -1 .claude/agents/ | wc -l | tr -d ' ') 个 agents)\"; else echo '⚠ 未找到 .claude/agents/'; fi && "
                   "echo '' && "
                   "echo '--- Manifest ---' && "
                   "ls .claude/*-manifest.json 2>/dev/null || echo '⚠ 未找到 manifest 文件' && "
                   "echo '' && "
                   "echo '--- CLAUDE.md ---' && "
                   "if [ -f CLAUDE.md ]; then echo '✓ CLAUDE.md 存在 ($(wc -l < CLAUDE.md | tr -d ' ') 行)'; else echo '⚠ 未找到 CLAUDE.md'; fi && "
                   "echo '' && "
                   "echo '--- .claude 目录总览 ---' && "
                   "ls -la .claude/ 2>/dev/null || echo '⚠ 未找到 .claude 目录' && "
                   "echo '' && "
                   "echo '========== 验证完成 =========='"]
            cwd = verify_dir
        elif step_id == "execute":
            if not op_name and not op_spec:
                raise HTTPException(status_code=400, detail="执行开发需要填写算子名称或算子规格")
            # 构造完整的算子开发需求
            if op_spec:
                prompt = op_spec
            else:
                prompt = (
                    f"帮我开发一个 {op_name} 算子，"
                    f"支持 float16 数据类型，"
                    f"请按照算子开发工作流完整执行：环境检查 → 架构设计 → 代码实现 → 测试验证"
                )
            cmd = ["claude", "-p", prompt, "--output-format", "json", "--verbose"]
            cwd = os.path.join(work_dir, "plugins-official", scenario)
        else:
            raise HTTPException(status_code=400, detail=f"未知步骤: {step_id}")

        # 更新步骤状态为 running
        now = datetime.now().isoformat()
        target["status"] = "running"
        target["command"] = " ".join(cmd)
        target["started_at"] = now
        target["output"] = ""
        target["error"] = None
        target["events"] = []
        await db.save_ops_dev_session(session)

        return {"status": "running", "session_id": session_id, "step_id": step_id}

    @router.get("/cannbot/ops-dev/sessions/{session_id}/stream")
    async def stream_session(session_id: str):
        """SSE 实时流：推送步骤执行输出"""

        async def event_generator():
            if not db:
                yield f"event: error\ndata: {json.dumps({'error': '数据库不可用'})}\n\n"
                return

            session = await db.get_ops_dev_session(session_id)
            if not session:
                yield f"event: error\ndata: {json.dumps({'error': '会话未找到'})}\n\n"
                return

            # 找到 running 步骤
            running_step = None
            for s in session["steps"]:
                if s["status"] == "running":
                    running_step = s
                    break

            if not running_step:
                yield f"event: error\ndata: {json.dumps({'error': '没有正在运行的步骤'})}\n\n"
                return

            step_id = running_step["step_id"]
            cmd_str = running_step["command"]
            cwd = "."

            # 重建 cwd
            scenario = session["scenario"]
            tool = session["tool"]
            work_dir = session.get("work_dir", "")
            op_name = session.get("op_name", "")
            op_spec = session.get("op_spec", "")

            if step_id == "clone":
                # clone 步骤的 cwd 由 command 决定
                # 如果仓库已存在则 cwd=work_dir（pull），否则 cwd=external（clone）
                if os.path.isdir(work_dir) and os.path.isdir(os.path.join(work_dir, ".git")):
                    cwd = work_dir
                else:
                    cwd = str(PROJECT_ROOT / "external")
            elif step_id == "install":
                cwd = os.path.join(work_dir, "plugins-official", scenario)
            elif step_id == "verify":
                cwd = os.path.join(work_dir, "plugins-official", scenario)
            elif step_id == "execute":
                cwd = os.path.join(work_dir, "plugins-official", scenario)

            try:
                import shlex
                cmd_parts = shlex.split(cmd_str)
            except ValueError:
                cmd_parts = cmd_str.split()

            proc = None
            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd_parts,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                    cwd=cwd,
                    stdin=asyncio.subprocess.PIPE if step_id == "install" else None,
                )
                _active_procs[session_id] = proc

                # install 步骤自动确认
                if step_id == "install" and proc.stdin:
                    try:
                        proc.stdin.write(b"y\n")
                        await proc.stdin.drain()
                        # 保持 stdin 打开一会，以防后续还有交互
                        await asyncio.sleep(0.5)
                        proc.stdin.close()
                    except Exception:
                        pass

                output_lines = []
                events = []

                async def read_stream():
                    raw_chunks = []
                    while True:
                        line = await proc.stdout.readline()
                        if not line:
                            break
                        line_str = line.decode("utf-8", errors="replace").rstrip("\n\r")
                        output_lines.append(line_str)

                        # 推送原始输出
                        yield f"event: output\ndata: {json.dumps({'line': line_str}, ensure_ascii=False)}\n\n"

                        # Step 4: 收集完整输出后再解析 JSON 数组
                        if step_id == "execute":
                            raw_chunks.append(line_str)

                    # Step 4: 进程结束后解析完整 JSON
                    if step_id == "execute" and raw_chunks:
                        full_output = "".join(raw_chunks).strip()
                        try:
                            parsed = json.loads(full_output)
                            if isinstance(parsed, list):
                                for obj in parsed:
                                    evt = _parse_claude_event(obj)
                                    if evt:
                                        events.append(evt)
                                        yield f"event: claude_event\ndata: {json.dumps(evt, ensure_ascii=False)}\n\n"
                            elif isinstance(parsed, dict):
                                evt = _parse_claude_event(parsed)
                                if evt:
                                    events.append(evt)
                                    yield f"event: claude_event\ndata: {json.dumps(evt, ensure_ascii=False)}\n\n"
                        except (json.JSONDecodeError, ValueError):
                            pass

                async for chunk in read_stream():
                    yield chunk

                await proc.wait()
                returncode = proc.returncode

                # Claude Code 的 --output-format json 可能返回非零 exit code
                # 但输出中有 type=result + subtype=success 仍应视为成功
                if step_id == "execute" and returncode != 0:
                    has_success = any(
                        evt.get("type") == "result"
                        for evt in events
                    )
                    if has_success:
                        returncode = 0

            except asyncio.CancelledError:
                if proc:
                    proc.kill()
                return
            except Exception as e:
                logger.error(f"步骤执行异常 [{session_id}/{step_id}]: {e}")
                yield f"event: error\ndata: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"
                returncode = -1
            finally:
                _active_procs.pop(session_id, None)

            # 更新步骤状态
            now = datetime.now().isoformat()
            session = await db.get_ops_dev_session(session_id)
            if session:
                for s in session["steps"]:
                    if s["step_id"] == step_id:
                        s["status"] = "completed" if returncode == 0 else "failed"
                        s["completed_at"] = now
                        s["output"] = "\n".join(output_lines)
                        s["error"] = None if returncode == 0 else f"Exit code: {returncode}"
                        if step_id == "execute":
                            s["events"] = events
                        break

                # 更新会话状态
                all_done = all(
                    s["status"] in ("completed", "failed")
                    for s in session["steps"]
                )
                any_failed = any(
                    s["status"] == "failed"
                    for s in session["steps"]
                )
                if all_done:
                    session["status"] = "completed" if not any_failed else "failed"
                    session["completed_at"] = now

                await db.save_ops_dev_session(session)

            # 推送完成事件
            yield f"event: step_complete\ndata: {json.dumps({'step_id': step_id, 'returncode': returncode}, ensure_ascii=False)}\n\n"

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @router.post("/cannbot/ops-dev/sessions/{session_id}/steps/{step_id}/stop")
    async def stop_step(session_id: str, step_id: str):
        proc = _active_procs.get(session_id)
        if proc and proc.returncode is None:
            proc.kill()
            _active_procs.pop(session_id, None)

            # 更新步骤状态
            if db:
                session = await db.get_ops_dev_session(session_id)
                if session:
                    now = datetime.now().isoformat()
                    for s in session["steps"]:
                        if s["step_id"] == step_id and s["status"] == "running":
                            s["status"] = "failed"
                            s["completed_at"] = now
                            s["error"] = "用户手动停止"
                            break
                    await db.save_ops_dev_session(session)

            return {"stopped": True, "session_id": session_id, "step_id": step_id}

        return {"stopped": False, "message": "没有正在运行的进程"}

    @router.get("/cannbot/ops-dev/sessions/{session_id}/export")
    async def export_session_report(session_id: str, format: str = "markdown"):
        """导出会话报告（markdown 或 text）"""
        if not db:
            raise HTTPException(status_code=503, detail="数据库不可用")
        session = await db.get_ops_dev_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="会话未找到")

        if format == "markdown":
            content = _build_session_markdown(session)
            filename = f"ops-dev-{session_id}.md"
            media_type = "text/markdown"
        else:
            content = _build_session_text(session)
            filename = f"ops-dev-{session_id}.txt"
            media_type = "text/plain"

        # 写临时文件
        export_dir = os.path.join(str(PROJECT_ROOT), "backend", "exports")
        os.makedirs(export_dir, exist_ok=True)
        filepath = os.path.join(export_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

        return FileResponse(filepath, media_type=media_type, filename=filename)

    @router.post("/cannbot/ops-dev/sessions/{session_id}/supervise")
    async def supervise_session(session_id: str):
        """调用 LLM 分析会话执行过程，监督 Skills/Agents 使用情况"""
        if not db:
            raise HTTPException(status_code=503, detail="数据库不可用")

        session = await db.get_ops_dev_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="会话未找到")

        # 收集 execute 步骤的 events
        execute_step = None
        for s in session.get("steps", []):
            if s["step_id"] == "execute":
                execute_step = s
                break

        if not execute_step:
            raise HTTPException(status_code=400, detail="执行步骤尚未开始")

        events = execute_step.get("events", [])
        output = execute_step.get("output", "")

        if not events and not output:
            raise HTTPException(status_code=400, detail="执行步骤暂无输出数据")

        # 读取插件的 skills 和 agents 信息
        scenario = session.get("scenario", "ops-direct-invoke")
        plugin_dir = os.path.join(str(CANNBOT_DIR), "plugins-official", scenario)
        skill_info = _read_plugin_skills(plugin_dir)
        agent_info = _read_plugin_agents(plugin_dir)

        # 构建 LLM 分析 prompt
        events_summary = _summarize_events(events, max_events=80)
        prompt = _build_supervise_prompt(
            scenario=scenario,
            op_name=session.get("op_name", ""),
            skill_info=skill_info,
            agent_info=agent_info,
            events_summary=events_summary,
            output_tail=output[-3000:] if output else "",
        )

        # 调用 LLM
        try:
            from workflow.config import workflow_config
            if not workflow_config.ai_ready:
                raise HTTPException(status_code=503, detail="LLM 未配置，请先在 Agent 设置中配置 LLM")

            loop = asyncio.get_event_loop()
            response = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    lambda: workflow_config.llm.invoke([
                        {"role": "system", "content": SUPERVISION_SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ])
                ),
                timeout=120.0,
            )
            analysis_text = response.content
        except HTTPException:
            raise
        except asyncio.TimeoutError:
            raise HTTPException(status_code=504, detail="LLM 分析超时")
        except Exception as e:
            logger.error(f"监督分析失败: {e}")
            raise HTTPException(status_code=500, detail=f"LLM 分析失败: {str(e)}")

        # 解析 LLM 返回的结构化结果
        result = _parse_supervision_result(analysis_text)
        result["session_id"] = session_id
        result["scenario"] = scenario
        result["total_events"] = len(events)
        result["skill_count"] = len(skill_info)
        result["agent_count"] = len(agent_info)

        return result


def _parse_claude_event(obj: dict) -> Optional[dict]:
    """解析 claude --output-format json 的一行输出，提取结构化事件"""
    msg_type = obj.get("type", "")

    if msg_type == "assistant":
        # assistant 消息可能包含 content blocks
        content = obj.get("message", {}).get("content", [])
        if isinstance(content, list):
            for block in content:
                if block.get("type") == "thinking":
                    return {"type": "thinking", "content": block.get("thinking", ""), "ts": datetime.now().isoformat()}
                elif block.get("type") == "tool_use":
                    return {"type": "tool_use", "name": block.get("name", ""), "input": block.get("input", {}), "ts": datetime.now().isoformat()}
                elif block.get("type") == "text":
                    return {"type": "text", "content": block.get("text", ""), "ts": datetime.now().isoformat()}

    if msg_type == "content_block_start":
        cb = obj.get("content_block", {})
        cb_type = cb.get("type", "")
        if cb_type == "thinking":
            return {"type": "thinking", "content": cb.get("thinking", ""), "ts": datetime.now().isoformat()}
        elif cb_type == "tool_use":
            return {"type": "tool_use", "name": cb.get("name", ""), "input": cb.get("input", {}), "ts": datetime.now().isoformat()}
        elif cb_type == "text":
            return {"type": "text", "content": cb.get("text", ""), "ts": datetime.now().isoformat()}

    if msg_type == "content_block_delta":
        delta = obj.get("delta", {})
        delta_type = delta.get("type", "")
        if delta_type == "thinking_delta":
            return {"type": "thinking", "content": delta.get("thinking", ""), "ts": datetime.now().isoformat()}
        elif delta_type == "text_delta":
            return {"type": "text", "content": delta.get("text", ""), "ts": datetime.now().isoformat()}
        elif delta_type == "input_json_delta":
            return {"type": "tool_use", "name": "", "input": delta.get("partial_json", ""), "ts": datetime.now().isoformat()}

    # result 消息
    if msg_type == "result":
        return {"type": "result", "content": obj.get("result", ""), "ts": datetime.now().isoformat()}

    return None


def _build_session_markdown(session: dict) -> str:
    """生成会话 Markdown 报告"""
    lines = []
    lines.append(f"# 算子辅助开发报告\n")
    lines.append("## 会话信息\n")
    lines.append("| 字段 | 值 |")
    lines.append("|------|-----|")
    lines.append(f"| 会话 ID | {session.get('session_id', '')} |")
    lines.append(f"| 场景 | {session.get('scenario', '')} |")
    lines.append(f"| AI 工具 | {session.get('tool', '')} |")
    lines.append(f"| 算子名称 | {session.get('op_name', '')} |")
    lines.append(f"| 算子规格 | {session.get('op_spec', '')} |")
    lines.append(f"| 状态 | {session.get('status', '')} |")
    lines.append(f"| 创建时间 | {session.get('created_at', '')} |")
    lines.append(f"| 完成时间 | {session.get('completed_at', 'N/A')} |")
    lines.append("")

    # 步骤概览
    lines.append("## 步骤概览\n")
    lines.append("| 步骤 | 状态 | 命令 | 开始时间 | 完成时间 |")
    lines.append("|------|------|------|---------|---------|")
    for step in session.get("steps", []):
        status_icon = {"completed": "✅", "failed": "❌", "running": "⏳"}.get(step.get("status", ""), "⬜")
        lines.append(
            f"| {step.get('step_name', '')} | {status_icon} {step.get('status', '')} "
            f"| `{step.get('command', '')}` | {step.get('started_at', 'N/A')} "
            f"| {step.get('completed_at', 'N/A')} |"
        )
    lines.append("")

    # 各步骤详细输出
    for step in session.get("steps", []):
        lines.append(f"## {step.get('step_name', '')}\n")
        if step.get("command"):
            lines.append(f"**命令**: `{step['command']}`\n")
        if step.get("error"):
            lines.append(f"**错误**: {step['error']}\n")

        if step.get("output"):
            lines.append("### 终端输出\n")
            lines.append("```\n" + step["output"] + "\n```\n")

        if step.get("events"):
            lines.append("### 结构化日志\n")
            for evt in step["events"]:
                evt_type = evt.get("type", "")
                ts = evt.get("ts", "")
                if evt_type == "thinking":
                    lines.append(f"- **[{ts}] 思考**: {evt.get('content', '')}")
                elif evt_type == "tool_use":
                    name = evt.get("name", "")
                    inp = evt.get("input", "")
                    if isinstance(inp, dict):
                        inp = json.dumps(inp, ensure_ascii=False)[:200]
                    lines.append(f"- **[{ts}] 工具 `{name}`**: {inp}")
                elif evt_type == "text":
                    lines.append(f"- **[{ts}] 文本**: {evt.get('content', '')}")
                elif evt_type == "result":
                    lines.append(f"- **[{ts}] 结果**: {evt.get('content', '')[:500]}")
            lines.append("")

    return "\n".join(lines)


def _build_session_text(session: dict) -> str:
    """生成会话纯文本报告"""
    lines = []
    lines.append(f"算子辅助开发报告 - {session.get('session_id', '')}")
    lines.append(f"场景: {session.get('scenario', '')} | 工具: {session.get('tool', '')}")
    lines.append(f"算子: {session.get('op_name', '')} | 状态: {session.get('status', '')}")
    lines.append(f"创建: {session.get('created_at', '')} | 完成: {session.get('completed_at', 'N/A')}")
    lines.append("=" * 60)

    for step in session.get("steps", []):
        lines.append(f"\n--- {step.get('step_name', '')} [{step.get('status', '')}] ---")
        if step.get("command"):
            lines.append(f"命令: {step['command']}")
        if step.get("error"):
            lines.append(f"错误: {step['error']}")
        if step.get("output"):
            lines.append(step["output"])
        if step.get("events"):
            lines.append("\n[结构化日志]")
            for evt in step["events"]:
                lines.append(f"  [{evt.get('type', '')}] {evt.get('content', evt.get('name', ''))}")

    return "\n".join(lines)


# ==================== 监督分析辅助函数 ====================

SUPERVISION_SYSTEM_PROMPT = """你是一个 AI 辅助算子开发过程的监督分析专家。
你需要分析 Claude Code 执行算子开发过程中的实时事件流，判断：

1. 插件 Skills 和 Agents 是否被正确调用和使用
2. AI 的每一步决策是否遵循了 Skill 定义的工作流
3. 哪些操作是 Skill/Agent 定义中要求的，哪些是 Claude 自主额外添加的
4. 是否有遗漏的 Skill 或 Agent 未被使用
5. 决策质量评估：关键节点的技术选型是否合理

请严格按以下 JSON 格式输出分析结果（不要输出其他内容）：

```json
{
  "overview": "一段话总结整个执行过程",
  "skills_usage": [
    {"skill": "skill名称", "status": "used|partially_used|unused|unknown", "detail": "使用详情"}
  ],
  "agents_usage": [
    {"agent": "agent名称", "status": "invoked|not_invoked|unknown", "detail": "调用详情"}
  ],
  "decisions": [
    {"step": "决策节点描述", "source": "skill|claude_extra|unknown", "quality": "good|acceptable|questionable", "detail": "分析说明"}
  ],
  "skill_coverage": 85,
  "warnings": ["警告列表，如遗漏的 skill 或可疑决策"],
  "conclusion": "整体评价一段话"
}
```"""


def _read_plugin_skills(plugin_dir: str) -> list:
    """读取插件 skills 目录信息"""
    skills = []
    skills_dir = os.path.join(plugin_dir, ".claude", "skills")
    if not os.path.isdir(skills_dir):
        skills_dir = os.path.join(plugin_dir, "skills")
    if not os.path.isdir(skills_dir):
        return skills

    for entry in sorted(os.listdir(skills_dir)):
        skill_path = os.path.join(skills_dir, entry)
        if os.path.isdir(skill_path):
            desc = ""
            skill_md = os.path.join(skill_path, "SKILL.md")
            if os.path.isfile(skill_md):
                try:
                    text = open(skill_md, encoding="utf-8", errors="replace").read(2000)
                    if text.startswith("---"):
                        end = text.find("---", 3)
                        if end > 0:
                            for line in text[3:end].split("\n"):
                                if line.startswith("description:"):
                                    desc = line.split(":", 1)[1].strip().strip('"\'')
                                    break
                    if not desc:
                        for line in text.split("\n"):
                            if line.startswith("# ") and not desc:
                                desc = line.lstrip("# ").strip()[:100]
                                break
                except Exception:
                    pass
            skills.append({"name": entry, "description": desc})
    return skills


def _read_plugin_agents(plugin_dir: str) -> list:
    """读取插件 agents 目录信息"""
    agents = []
    agents_dir = os.path.join(plugin_dir, "agents")
    if not os.path.isdir(agents_dir):
        return agents

    for entry in sorted(os.listdir(agents_dir)):
        if not entry.endswith(".md"):
            continue
        agent_path = os.path.join(agents_dir, entry)
        desc = ""
        try:
            text = open(agent_path, encoding="utf-8", errors="replace").read(2000)
            if text.startswith("---"):
                end = text.find("---", 3)
                if end > 0:
                    for line in text[3:end].split("\n"):
                        if line.startswith("description:"):
                            desc = line.split(":", 1)[1].strip().strip('"\'')
                            break
            if not desc:
                for line in text.split("\n"):
                    if line.startswith("# "):
                        desc = line.lstrip("# ").strip()[:100]
                        break
        except Exception:
            pass
        agents.append({"name": entry.replace(".md", ""), "description": desc})
    return agents


def _summarize_events(events: list, max_events: int = 80) -> str:
    """将 events 列表格式化为 LLM 可读的摘要"""
    if not events:
        return "(无事件)"

    lines = []
    for i, evt in enumerate(events[-max_events:]):
        evt_type = evt.get("type", "unknown")
        if evt_type == "thinking":
            content = evt.get("content", "")[:200]
            lines.append(f"[{i+1}] 思考: {content}")
        elif evt_type == "tool_use":
            name = evt.get("name", "")
            inp = evt.get("input", "")
            if isinstance(inp, dict):
                inp = json.dumps(inp, ensure_ascii=False)[:200]
            elif isinstance(inp, str):
                inp = inp[:200]
            lines.append(f"[{i+1}] 工具调用({name}): {inp}")
        elif evt_type == "text":
            lines.append(f"[{i+1}] 文本输出: {evt.get('content', '')[:300]}")
        elif evt_type == "result":
            lines.append(f"[{i+1}] 最终结果: {evt.get('content', '')[:300]}")
        else:
            lines.append(f"[{i+1}] {evt_type}: {json.dumps(evt, ensure_ascii=False)[:200]}")

    return "\n".join(lines)


def _build_supervise_prompt(scenario: str, op_name: str, skill_info: list,
                            agent_info: list, events_summary: str, output_tail: str) -> str:
    """构建监督分析 prompt"""
    skills_desc = "\n".join(
        f"- {s['name']}: {s['description'] or '无描述'}" for s in skill_info
    ) if skill_info else "(未读取到 skills)"

    agents_desc = "\n".join(
        f"- {a['name']}: {a['description'] or '无描述'}" for a in agent_info
    ) if agent_info else "(未读取到 agents)"

    parts = [
        f"## 分析任务\n",
        f"场景插件: {scenario}",
        f"算子名称: {op_name or '未知'}\n",
        f"## 该插件定义的 Skills (共 {len(skill_info)} 个)\n",
        skills_desc,
        f"\n## 该插件定义的 Agents (共 {len(agent_info)} 个)\n",
        agents_desc,
        f"\n## Claude Code 执行事件流\n",
        events_summary,
    ]

    if output_tail:
        parts.append(f"\n## 终端输出尾部\n```\n{output_tail}\n```\n")

    parts.append("\n请分析以上事件流，判断 Skills 和 Agents 的使用情况、AI 决策来源和质量。")
    return "\n".join(parts)


def _parse_supervision_result(text: str) -> dict:
    """解析 LLM 返回的监督分析结果"""
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
            return json.loads(text[start:end + 1])
    except (json.JSONDecodeError, ValueError):
        pass

    return {
        "overview": text[:500],
        "skills_usage": [],
        "agents_usage": [],
        "decisions": [],
        "skill_coverage": 0,
        "warnings": ["LLM 输出无法解析为结构化 JSON"],
        "conclusion": text[:500],
    }
