"""工作流仿真 V2 — Claude Code jsonl 会话存档工具

Claude Code 把每个会话的完整流水存为 ~/.claude/projects/<work_dir编码>/<uuid>.jsonl
本模块负责定位、读取、增量 harvest 这些 jsonl 文件。
"""

import json
import logging
import os
import time
from typing import Optional

from app.services.claude_code_driver import ClaudeCodeDriver

logger = logging.getLogger(__name__)


def claude_project_dir(work_dir: str) -> str:
    """work_dir → ~/.claude/projects/<编码> 目录路径。"""
    real = os.path.realpath(work_dir or "")
    encoded = real.replace("/", "-")
    return os.path.expanduser(f"~/.claude/projects/{encoded}")


def jsonl_is_finished(path: str) -> bool:
    """判断一个 jsonl 会话是否已结束（不再增长）。"""
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            if size == 0:
                return True
            back = min(size, 8192)
            f.seek(size - back)
            tail = f.read().decode("utf-8", errors="replace")
        last_line = ""
        for ln in reversed(tail.splitlines()):
            ln = ln.strip()
            if ln:
                last_line = ln
                break
        if not last_line:
            return True
        o = json.loads(last_line)
        if o.get("type") == "last-prompt":
            return True
        sr = (o.get("message") or {}).get("stop_reason")
        if sr in ("end_turn", "stop_sequence"):
            return True
        return False
    except Exception:
        return False


def list_subagent_jsonls(project_dir: str) -> list:
    """列出项目目录下所有子 Agent 的 jsonl 文件。"""
    result = []
    if not project_dir or not os.path.isdir(project_dir):
        return result
    try:
        for entry in os.listdir(project_dir):
            sub_agents_dir = os.path.join(project_dir, entry, "subagents")
            if not os.path.isdir(sub_agents_dir):
                continue
            for f in os.listdir(sub_agents_dir):
                if f.endswith(".jsonl"):
                    p = os.path.join(sub_agents_dir, f)
                    if os.path.isfile(p):
                        result.append(p)
    except Exception:
        pass
    return result


def pick_active_jsonl(project_dir: str) -> Optional[str]:
    """从 Claude Code 项目目录里选出当前活跃的 jsonl。"""
    if not project_dir or not os.path.isdir(project_dir):
        return None
    try:
        main_files = [
            os.path.join(project_dir, f)
            for f in os.listdir(project_dir)
            if f.endswith(".jsonl") and os.path.isfile(os.path.join(project_dir, f))
        ]
    except Exception:
        return None
    main_files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    main_active = main_files[0] if main_files else None

    now = time.time()
    MAIN_STALE_SEC = 4

    if (
        main_active
        and not jsonl_is_finished(main_active)
        and (now - os.path.getmtime(main_active)) < MAIN_STALE_SEC
    ):
        return main_active

    sub_files = list_subagent_jsonls(project_dir)
    sub_unfinished = [p for p in sub_files if not jsonl_is_finished(p)]
    if sub_unfinished:
        sub_unfinished.sort(key=lambda p: os.path.getmtime(p), reverse=True)
        return sub_unfinished[0]

    if main_active and not jsonl_is_finished(main_active):
        return main_active

    return None


def parse_jsonl_tool_uses(path: str) -> list:
    """读取一个 Claude jsonl 文件，提取所有 tool_use 事件。"""
    events = []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if obj.get("type") != "assistant":
                    continue
                blocks = (obj.get("message") or {}).get("content") or []
                for block in blocks:
                    if not isinstance(block, dict):
                        continue
                    if block.get("type") == "tool_use":
                        events.append(
                            {
                                "type": "tool_use",
                                "name": block.get("name", ""),
                                "input": block.get("input", {}),
                            }
                        )
    except Exception as e:
        logger.warning(f"解析 jsonl tool_use 失败 [{path}]: {e}")
    return events


def harvest_subagent_skill_refs(work_dir: str, step_start_time: float) -> dict:
    """步骤完成后，扫描 subagent jsonl 提取内部引用的 skill。"""
    project_dir = claude_project_dir(work_dir)
    sub_files = list_subagent_jsonls(project_dir)
    relevant = [p for p in sub_files if os.path.getmtime(p) >= step_start_time]

    by_source = {}
    all_events = []
    for path in relevant:
        evts = parse_jsonl_tool_uses(path)
        if not evts:
            continue
        all_events.extend(evts)
        skills_in_file = ClaudeCodeDriver.extract_skill_references(evts)
        if skills_in_file:
            by_source[os.path.basename(path)] = skills_in_file

    skills = ClaudeCodeDriver.extract_skill_references(all_events) if all_events else []
    return {
        "skills": skills,
        "files_scanned": len(relevant),
        "by_source": by_source,
    }


def harvest_new_jsonl_lines(work_dir: str, offsets: dict) -> tuple:
    """增量读取所有 jsonl 文件的新行，返回 (lines, updated_offsets)。"""
    project_dir = claude_project_dir(work_dir)
    if not project_dir or not os.path.isdir(project_dir):
        return ([], offsets)

    lines = []
    MAX_LINES_PER_FILE = 3000

    main_files = []
    try:
        for f in os.listdir(project_dir):
            if f.endswith(".jsonl") and os.path.isfile(os.path.join(project_dir, f)):
                main_files.append(os.path.join(project_dir, f))
    except Exception:
        pass
    main_files.sort(key=lambda p: os.path.getmtime(p))

    sub_files = list_subagent_jsonls(project_dir)
    sub_files.sort(key=lambda p: os.path.getmtime(p))

    for path in main_files + sub_files:
        off = offsets.get(path, 0)
        objs, new_off = read_jsonl_lines(path, off)
        if new_off > off:
            offsets[path] = new_off
        for obj in objs[:MAX_LINES_PER_FILE]:
            k, s = summarize_jsonl_line(obj)
            if k == "other" and not s:
                continue
            lines.append(
                {
                    "ts": obj.get("timestamp", ""),
                    "kind": k,
                    "summary": s,
                    "type": obj.get("type", ""),
                }
            )

    return (lines, offsets)


def summarize_jsonl_line(obj: dict) -> tuple:
    """把一行 jsonl 解析为 (kind, summary) 用于前端轻量渲染。"""
    t = obj.get("type")
    if t == "assistant":
        blocks = (obj.get("message") or {}).get("content") or []
        for b in blocks:
            if not isinstance(b, dict):
                continue
            bt = b.get("type")
            if bt == "thinking":
                txt = (b.get("thinking") or "").replace("\n", " ")
                return ("thinking", f"💭 {txt[:160]}")
            if bt == "text":
                return (
                    "text",
                    f"💬 {(b.get('text') or '').replace(chr(10), ' ')[:200]}",
                )
            if bt == "tool_use":
                name = b.get("name", "")
                inp = b.get("input") or {}
                if name == "Read":
                    return (
                        "tool_use",
                        f"📖 读取文件: {inp.get('file_path', '')[:120]}",
                    )
                if name == "Write":
                    cnt = inp.get("content", "")
                    lines = cnt.count("\n") + 1 if cnt else 0
                    return (
                        "tool_use",
                        f"✏️ 写入文件: {inp.get('file_path', '')[:110]} ({lines} 行)",
                    )
                if name == "Edit":
                    return (
                        "tool_use",
                        f"📝 编辑文件: {inp.get('file_path', '')[:120]}",
                    )
                if name == "Bash":
                    desc = inp.get("description") or inp.get("command", "")
                    return ("tool_use", f"⚙️ 执行命令: {str(desc)[:110]}")
                if name == "Agent":
                    return (
                        "tool_use",
                        f"🤖 调用子Agent: {inp.get('subagent_type', '')} — {inp.get('description', '')[:70]}",
                    )
                if name == "Skill":
                    return ("tool_use", f"🎯 调用 Skill: /{inp.get('skill', '')}")
                if name == "TodoWrite":
                    todos = inp.get("todos") or []
                    return ("tool_use", f"📋 Todo 更新: {len(todos)} 项")
                if name == "Glob":
                    return ("tool_use", f"🔍 搜索文件: {inp.get('pattern', '')[:110]}")
                if name == "Grep":
                    return (
                        "tool_use",
                        f"🔍 搜索内容: {inp.get('pattern', '')[:80]} in {inp.get('path', '')[:60]}",
                    )
                return (
                    "tool_use",
                    f"🔧 {name}({json.dumps(inp, ensure_ascii=False)[:80]})",
                )
        return ("other", "")
    if t == "user":
        blocks = (obj.get("message") or {}).get("content") or []
        for b in blocks:
            if isinstance(b, dict) and b.get("type") == "tool_result":
                content = b.get("content")
                if isinstance(content, list):
                    content = " ".join(
                        str(x.get("text", "")) if isinstance(x, dict) else str(x)
                        for x in content
                    )
                txt = str(content or "").replace("\n", " ")
                return ("tool_result", f"↳ {txt[:200]}")
            if isinstance(b, dict) and b.get("type") == "text":
                return (
                    "text",
                    f"👤 {(b.get('text') or '').replace(chr(10), ' ')[:200]}",
                )
        return ("other", "")
    if t in (
        "attachment",
        "queue-operation",
        "file-history-snapshot",
        "last-prompt",
        "system",
    ):
        return ("system", f"[{t}]")
    return ("other", f"[{t}]")


def read_jsonl_lines(path: str, offset: int) -> tuple:
    """从 jsonl 文件的第 offset+1 行开始读到末尾。"""
    if not path or not os.path.isfile(path):
        return ([], offset)
    objs = []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for i, ln in enumerate(f):
                if i < offset:
                    continue
                ln = ln.strip()
                if not ln:
                    offset = i + 1
                    continue
                try:
                    objs.append(json.loads(ln))
                    offset = i + 1
                except Exception:
                    offset = i
                    break
    except Exception:
        pass
    return (objs, offset)


def format_jsonl_sse(obj: dict) -> str:
    """把一行 jsonl 格式化为 SSE 事件字符串。"""
    kind, summary = summarize_jsonl_line(obj)
    ts = obj.get("timestamp", "")
    payload = {"ts": ts, "kind": kind, "summary": summary, "type": obj.get("type", "")}
    return f"event: jsonl_line\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
