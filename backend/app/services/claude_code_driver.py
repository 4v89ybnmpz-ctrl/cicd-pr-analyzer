"""
Claude Code CLI Driver
通过 asyncio subprocess 调用 claude CLI，解析 stream-json 输出

Claude CLI stream-json 实际输出格式：
  {"type": "system", "subtype": "init", ...}           — 初始化信息
  {"type": "system", "subtype": "hook_started", ...}    — hook 事件
  {"type": "assistant", "message": {"content": [...]}}  — 助手消息（含 text/tool_use/thinking）
  {"type": "user", "message": {"content": [...]}}       — 用户消息（含 tool_result）
  {"type": "result", "result": "...", "duration_ms": N} — 最终结果

注意：Claude CLI 会将整条 assistant 消息（含 thinking）编码为单行 JSON，
thinking 内容可能超过 10 万字符。asyncio.StreamReader 默认行限制为 64KB，
使用 async for line in proc.stdout 会导致 LimitOverrunError。
因此使用自定义的分块读取方式，支持任意长度的行。
"""
import asyncio
import json
import logging
import os
import time
from typing import AsyncGenerator, Dict, List, Optional

# 单行最大允许 20MB，Claude CLI 的 thinking 输出可能非常长
_LINE_BUF_SIZE = 20 * 1024 * 1024

logger = logging.getLogger(__name__)


async def _read_lines(stream: asyncio.StreamReader) -> AsyncGenerator[bytes, None]:
    """
    从 StreamReader 中逐行读取，不受 asyncio 默认 64KB 行限制。
    使用分块读取 + 手动按 \\n 分割，支持任意长度的行。
    """
    buf = b""
    while True:
        chunk = await stream.read(65536)
        if not chunk:
            if buf:
                yield buf
            break
        buf += chunk
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            yield line


class ProcessInfo:
    """单个 Claude 进程的生命周期信息"""

    def __init__(self, pid: int, session_id: str, step_id: str = "", work_dir: str = ""):
        self.pid = pid
        self.session_id = session_id
        self.step_id = step_id
        self.work_dir = work_dir
        self.started_at = time.time()
        self.finished_at: Optional[float] = None
        self.exit_code: Optional[int] = None
        self.alive = True
        self.killed = False
        self.error: Optional[str] = None

    @property
    def elapsed_sec(self) -> float:
        end = self.finished_at or time.time()
        return round(end - self.started_at, 1)

    def to_dict(self) -> dict:
        return {
            "pid": self.pid,
            "session_id": self.session_id,
            "step_id": self.step_id,
            "work_dir": self.work_dir,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "elapsed_sec": self.elapsed_sec,
            "exit_code": self.exit_code,
            "alive": self.alive,
            "killed": self.killed,
            "error": self.error,
        }


class ClaudeCodeDriver:
    """Claude Code CLI 驱动器"""

    def __init__(self):
        self._active_procs: Dict[str, asyncio.subprocess.Process] = {}
        # session_id → ProcessInfo（最新一次）
        self._proc_history: Dict[str, ProcessInfo] = {}
        # session_id + step_id → ProcessInfo（每步记录）
        self._step_procs: Dict[str, ProcessInfo] = {}

    def get_process_info(self, session_id: str) -> Optional[dict]:
        """获取会话最新的进程信息"""
        info = self._proc_history.get(session_id)
        if info:
            # 刷新存活状态
            if info.alive:
                try:
                    os.kill(info.pid, 0)
                except (ProcessLookupError, OSError):
                    info.alive = False
                    if not info.finished_at:
                        info.finished_at = time.time()
            return info.to_dict()
        return None

    def get_all_processes(self) -> List[dict]:
        """获取所有被追踪的进程"""
        # 先刷新存活状态
        for info in self._proc_history.values():
            if info.alive:
                try:
                    os.kill(info.pid, 0)
                except (ProcessLookupError, OSError):
                    info.alive = False
                    if not info.finished_at:
                        info.finished_at = time.time()
        return [info.to_dict() for info in self._proc_history.values()]

    def get_step_process(self, session_id: str, step_id: str) -> Optional[dict]:
        """获取某个步骤的进程信息"""
        key = f"{session_id}:{step_id}"
        info = self._step_procs.get(key)
        if info:
            if info.alive:
                try:
                    os.kill(info.pid, 0)
                except (ProcessLookupError, OSError):
                    info.alive = False
                    if not info.finished_at:
                        info.finished_at = time.time()
            return info.to_dict()
        return None

    async def run_step(
        self,
        session_id: str,
        prompt: str,
        work_dir: str,
        timeout: int = 1800,
        step_id: str = "",
    ) -> AsyncGenerator[dict, None]:
        """
        执行单个 Claude Code CLI 步骤，yield 解析后的事件。
        """
        proc = None
        proc_info = None
        try:
            proc = await asyncio.create_subprocess_exec(
                "claude", "-p", prompt,
                "--output-format", "stream-json",
                "--dangerously-skip-permissions",
                "--add-dir", work_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=work_dir,
            )
            self._active_procs[session_id] = proc

            # 记录进程信息
            proc_info = ProcessInfo(
                pid=proc.pid,
                session_id=session_id,
                step_id=step_id,
                work_dir=work_dir,
            )
            self._proc_history[session_id] = proc_info
            if step_id:
                self._step_procs[f"{session_id}:{step_id}"] = proc_info

            logger.info(f"[claude] 进程启动 PID={proc.pid} session={session_id} step={step_id}")

            start_time = time.time()
            last_assistant_msg_id = None

            async def _read_stderr():
                try:
                    async for line in _read_lines(proc.stderr):
                        text = line.decode("utf-8", errors="replace").strip()
                        if text:
                            logger.info(f"[claude stderr] {text[:500]}")
                except Exception as e:
                    logger.warning(f"[claude stderr] 读取异常: {e}")

            stderr_task = asyncio.create_task(_read_stderr())

            try:
                async for raw_line in _read_lines(proc.stdout):
                    elapsed = time.time() - start_time
                    if timeout > 0 and elapsed > timeout:
                        yield {"type": "timeout", "elapsed_ms": int(elapsed * 1000)}
                        break

                    line_str = raw_line.decode("utf-8", errors="replace").strip()
                    if not line_str:
                        continue

                    try:
                        event = json.loads(line_str)
                    except json.JSONDecodeError:
                        yield {"type": "raw", "content": line_str}
                        continue

                    event_type = event.get("type", "")

                    if event_type == "assistant":
                        msg = event.get("message", {})
                        msg_id = msg.get("id", "")
                        content_blocks = msg.get("content", [])
                        if msg_id and msg_id == last_assistant_msg_id:
                            continue
                        if msg_id:
                            last_assistant_msg_id = msg_id
                        for block in content_blocks:
                            block_type = block.get("type", "")
                            if block_type == "text":
                                text = block.get("text", "")
                                if text:
                                    yield {"type": "text", "content": text}
                            elif block_type == "tool_use":
                                yield {
                                    "type": "tool_use",
                                    "name": block.get("name", ""),
                                    "input": block.get("input", {}),
                                    "id": block.get("id", ""),
                                }
                            elif block_type == "thinking":
                                thinking = block.get("thinking", "")
                                if thinking:
                                    yield {"type": "thinking", "content": thinking}
                        continue

                    if event_type == "user":
                        msg = event.get("message", {})
                        content_blocks = msg.get("content", [])
                        for block in content_blocks:
                            if block.get("type") == "tool_result":
                                yield {
                                    "type": "tool_result",
                                    "name": block.get("tool_use_id", ""),
                                    "output": block.get("content", ""),
                                    "is_error": block.get("is_error", False),
                                }
                        continue

                    if event_type == "result":
                        usage = event.get("usage", {})
                        model_usage = event.get("modelUsage", {})
                        tokens = {}
                        if model_usage:
                            for model_name, mu in model_usage.items():
                                tokens["input"] = tokens.get("input", 0) + mu.get("inputTokens", 0)
                                tokens["output"] = tokens.get("output", 0) + mu.get("outputTokens", 0)
                        elif usage:
                            tokens["input"] = usage.get("input_tokens", 0)
                            tokens["output"] = usage.get("output_tokens", 0)
                        yield {
                            "type": "result",
                            "content": event.get("result", ""),
                            "duration_ms": event.get("duration_ms", 0),
                            "tokens": tokens,
                            "cost_usd": event.get("total_cost_usd", 0),
                        }
                        continue

                    if event_type == "system":
                        subtype = event.get("subtype", "")
                        if subtype == "api_retry":
                            attempt = event.get("attempt", 0)
                            max_retries = event.get("max_retries", 0)
                            logger.info(f"[claude] API 重试 {attempt}/{max_retries}")
                        continue

                    logger.debug(f"[claude] 未知事件类型: {event_type}")

            except asyncio.CancelledError:
                yield {"type": "error", "content": "仿真被取消"}
                if proc_info:
                    proc_info.error = "仿真被取消"
            finally:
                stderr_task.cancel()
                try:
                    await stderr_task
                except asyncio.CancelledError:
                    pass

        except FileNotFoundError:
            yield {"type": "error", "content": "Claude Code CLI 未找到，请确认已安装 claude 命令"}
            if proc_info:
                proc_info.error = "CLI 未找到"
        except Exception as e:
            yield {"type": "error", "content": f"启动 Claude Code CLI 失败: {e}"}
            if proc_info:
                proc_info.error = str(e)
        finally:
            # 等待进程退出获取 exit code
            if proc and proc.returncode is None:
                try:
                    proc.kill()
                    await proc.wait()
                except Exception:
                    pass
            if proc_info:
                proc_info.alive = False
                proc_info.finished_at = time.time()
                proc_info.exit_code = proc.returncode if proc else None
                if proc_info.killed:
                    proc_info.error = (proc_info.error or "") + " (手动终止)"
                logger.info(
                    f"[claude] 进程结束 PID={proc_info.pid} exit={proc_info.exit_code} "
                    f"elapsed={proc_info.elapsed_sec}s step={proc_info.step_id}"
                )
            self._active_procs.pop(session_id, None)

    def stop(self, session_id: str) -> bool:
        """终止活跃的 Claude Code 进程"""
        proc = self._active_procs.get(session_id)
        info = self._proc_history.get(session_id)
        if proc and proc.returncode is None:
            try:
                proc.kill()
                if info:
                    info.killed = True
                return True
            except Exception:
                return False
        return False

    @staticmethod
    def extract_skill_references(events: List[dict]) -> List[str]:
        """从事件流中提取引用的 skill 文件"""
        referenced = set()
        for ev in events:
            if ev.get("type") == "tool_use" and ev.get("name") in ("Read", "Glob", "Grep"):
                inp = ev.get("input", {})
                file_path = inp.get("file_path", inp.get("pattern", ""))
                if ".claude/skills/" in file_path or ".claude/agents/" in file_path:
                    parts = file_path.replace("\\", "/").split("/")
                    for i, p in enumerate(parts):
                        if p in ("skills", "agents") and i + 1 < len(parts):
                            referenced.add(parts[i + 1].replace(".md", ""))
        return sorted(referenced)


# 全局单例
claude_driver = ClaudeCodeDriver()
