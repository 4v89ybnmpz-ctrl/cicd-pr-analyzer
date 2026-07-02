"""
真机 NPU 远程测试服务 — NpuTestRunner

通过 SSH 连接远程真实昇腾 NPU 服务器，把本地算子代码同步过去，
在真机上执行编译 + ST 穿刺测试，实时流式回传日志与结果。

设计要点：
  - paramiko 是同步库，所有阻塞调用（connect / sftp.put / exec_command 读 stdout）
    用 asyncio.to_thread() 包装，避免阻塞事件循环。
  - 远程命令 stdout 实时流式回传：exec_command 的 channel 上开一条后台线程
    按 stdout.readline() 读行，通过 asyncio.Queue 跨线程推回 async 侧逐行 yield。
    不能用 stdout.read() 一次性读（会等命令结束）。
  - 取消 = channel.close() 触发 EOF 让读线程自然退出。
  - SSH host 别名来自用户 ~/.ssh/config（paramiko 4.x 自动读取），只回传别名，
    绝不泄露 hostname/user/port/identityfile。

事件模式对齐 pipeline_service.GitCodePipelineClient：
  yield {"sse_event": "npu_xxx", "data": {...}}
"""
import asyncio
import logging
import os
import re
import shlex
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator, Callable, Dict, List, Optional, Tuple

import paramiko

logger = logging.getLogger(__name__)

# ==================== 常量 ====================

# NPU 测试生命周期步骤（前端 NpuTestPanel 按此渲染）
NPU_TEST_STEPS = [
    {"name": "建立 SSH 连接", "key": "ssh_connect"},
    {"name": "同步算子代码", "key": "sync_code"},
    {"name": "远程环境检查", "key": "env_check"},
    {"name": "真机编译", "key": "build"},
    {"name": "ST 穿刺测试", "key": "st_test"},
    {"name": "解析测试结果", "key": "parse_result"},
    {"name": "清理远程目录", "key": "cleanup"},
]

# 默认命令模板（前端可覆盖）。占位符在执行前由 _render() 替换。
DEFAULT_BUILD_CMD = (
    "source /usr/local/Ascend/ascend-toolkit/set_env.sh 2>/dev/null; "
    "cd {remote_dir} && bash build.sh 2>&1"
)
DEFAULT_TEST_CMD = (
    "source /usr/local/Ascend/ascend-toolkit/set_env.sh 2>/dev/null; "
    "cd {remote_dir}/tests/st && bash run.sh {op_name} ascend910b1 st 2>&1"
)

# 同步时排除的目录名与文件后缀（相对算子工程根）
SYNC_EXCLUDE_DIRS = {".git", "build", "cmake", "__pycache__", ".cache", "out", "node_modules"}
SYNC_EXCLUDE_SUFFIX = (".o", ".so", ".out", ".log", ".pyc", ".class")

# 超时
SSH_CONNECT_TIMEOUT = 30      # SSH 连接超时（秒）
CMD_LINE_TIMEOUT = 1800       # 单条远程命令最大执行时长（编译/测试可能很久）
ENV_CHECK_TIMEOUT = 30        # 环境检查命令超时


def _new_npu_steps() -> list:
    """创建初始 NPU 测试步骤列表（全部 pending）"""
    return [
        {**s, "status": "pending", "log": None,
         "started_at": None, "completed_at": None, "duration_ms": 0}
        for s in NPU_TEST_STEPS
    ]


def default_npu_test_field() -> dict:
    """session.npu_test 字段的默认结构（用于初始化与老会话兼容）"""
    return {
        "status": "pending",          # pending/running/success/failed/cancelled/timeout
        "host": None,
        "remote_dir": None,
        "build_cmd": None,
        "test_cmd": None,
        "steps": [],
        "logs": [],                   # 关键 stdout 行（持久化最近 N 行）
        "summary": None,              # {passed, passed_count, failed_count, total, raw}
        "triggered_at": None,
        "completed_at": None,
        "error": None,
        "error_detail": None,
    }


# ==================== 错误分类 ====================

def classify_npu_error(stage: str, error_content: str, exit_code: Optional[int] = None) -> dict:
    """NPU 测试专用错误分类。
    维度：SSH_CONNECT / AUTH / SYNC / ENV / BUILD / TEST / TIMEOUT / CANCELLED / UNKNOWN
    对齐 workflow_sim_v2_helpers.classify_error 的返回结构。
    """
    c = (error_content or "").lower()
    category = "UNKNOWN"
    root_cause = error_content or ""
    suggestion = "查看日志排查问题"

    if stage == "ssh_connect":
        if any(k in c for k in ("timed out", "timeout", "超时")):
            category = "TIMEOUT"
            root_cause = "SSH 连接超时"
            suggestion = "检查网络可达性、端口、ssh config 中该 Host 的配置"
        elif any(k in c for k in ("auth fail", "permission denied", "publickey", "bad authentication")):
            category = "AUTH"
            root_cause = "SSH 密钥认证失败"
            suggestion = "确认 ~/.ssh/config 已配好免密，对应 identityfile 在 ssh-agent 或磁盘上"
        elif any(k in c for k in ("refused", "unreachable", "no route", "not known", "resolve")):
            category = "SSH_CONNECT"
            root_cause = "网络不可达 / 端口拒绝 / 无法解析主机"
            suggestion = "检查 NPU 服务器在线状态、网络与 ssh config Host 配置"
        else:
            category = "SSH_CONNECT"
            root_cause = error_content or "SSH 连接失败"
            suggestion = "检查 ssh config、网络与服务器状态"
    elif stage == "sync_code":
        category = "SYNC"
        root_cause = f"代码同步失败: {error_content}" if error_content else "代码同步失败"
        suggestion = "检查远端磁盘空间、写权限与网络稳定性"
    elif stage == "env_check":
        category = "ENV"
        root_cause = "远端 CANN 环境异常"
        suggestion = "确认远端已安装 Ascend toolkit，且 npu-smi info 与 ASCEND_HOME_PATH 可用"
    elif stage == "build":
        category = "BUILD"
        root_cause = f"真机编译失败 (exit code {exit_code})" if exit_code is not None else "真机编译失败"
        suggestion = "查看编译日志，常见为头文件/接口/算子实现/Tiling 问题"
    elif stage == "st_test":
        category = "TEST"
        root_cause = f"ST 测试失败 (exit code {exit_code})" if exit_code is not None else "ST 测试失败"
        suggestion = "查看测试输出，定位失败用例与原因"
    elif stage == "timeout":
        category = "TIMEOUT"
        root_cause = "远程命令执行超时"
        suggestion = "编译/测试可能耗时过长，可增大命令超时或拆分任务"
    elif stage == "cancelled":
        category = "CANCELLED"
        root_cause = "用户手动取消"
        suggestion = "正常操作，无需处理"

    return {
        "category": category,
        "root_cause": root_cause,
        "suggestion": suggestion,
        "original_error": error_content,
        "exit_code": exit_code,
        "stage": stage,
    }


# ==================== 主类 ====================

class NpuTestRunner:
    """真机 NPU 远程测试执行器"""

    def __init__(
        self,
        connect_timeout: int = SSH_CONNECT_TIMEOUT,
        cmd_timeout: int = CMD_LINE_TIMEOUT,
    ):
        self.connect_timeout = connect_timeout
        self.cmd_timeout = cmd_timeout

    # ---------------- SSH config 解析 ----------------

    @staticmethod
    def list_ssh_hosts() -> Dict:
        """解析 ~/.ssh/config 返回可用 Host 别名列表。
        过滤掉通配符 host（含 * 或 ?）。只返回别名，绝不回传敏感信息。
        """
        path = os.path.expanduser("~/.ssh/config")
        if not os.path.exists(path):
            return {"hosts": [], "total": 0,
                    "error": "未找到 ~/.ssh/config，请先创建并配置 NPU 服务器 Host"}
        try:
            cfg = paramiko.SSHConfig()
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                cfg.parse(f)
            hosts = sorted(
                h for h in cfg.get_hostnames()
                if not any(ch in h for ch in ("*", "?", "!", ","))
            )
            return {"hosts": hosts, "total": len(hosts)}
        except Exception as e:
            logger.error(f"解析 ssh config 失败: {e}")
            return {"hosts": [], "total": 0, "error": f"解析 ssh config 失败: {e}"}

    # ---------------- 远程命令实时流式执行（核心并发模型）----------------

    async def _stream_cmd_as_events(
        self,
        client: paramiko.SSHClient,
        cmd: str,
        step_key: str,
        cancel: Callable[[], bool],
        cmd_timeout: Optional[int] = None,
        line_collector: Optional[list] = None,
    ) -> AsyncGenerator[dict, None]:
        """执行远程命令并 yield 实时事件。
        - 每行 stdout/stderr → {"sse_event":"npu_log","data":{step,stream,line}}
        - 结束 → {"sse_event":"npu_cmd_done","data":{exit_code,timed_out,cancelled}}
        - line_collector 若提供，所有行（含 stderr）会追加进去，供后续解析。

        并发模型：读行用独立线程（paramiko.readline 是阻塞调用，无法被 asyncio
        取消，只能靠 channel.close() 触发 EOF 让其退出），通过 call_soon_threadsafe
        + asyncio.Queue 桥接到主协程逐行 yield。
        """
        loop = asyncio.get_running_loop()
        out_queue: asyncio.Queue = asyncio.Queue(maxsize=2000)
        collector = line_collector if line_collector is not None else []

        def _on_line(stream_name, line):
            collector.append(line)
            try:
                loop.call_soon_threadsafe(
                    out_queue.put_nowait, (stream_name, line))
            except Exception:
                pass

        timeout = cmd_timeout or self.cmd_timeout
        try:
            stdin, stdout, stderr = await asyncio.to_thread(
                client.exec_command, cmd, timeout=timeout)
        except Exception as e:
            yield {"sse_event": "npu_log", "data": {
                "step": step_key, "stream": "stderr",
                "line": f"[exec_command 失败] {e}"}}
            yield {"sse_event": "npu_cmd_done", "data": {
                "exit_code": None, "timed_out": False, "cancelled": cancel(),
                "error": str(e)}}
            return

        channel = stdout.channel
        channel.set_combine_stderr(False)

        def _reader(stream, stream_name: str):
            try:
                for line in iter(stream.readline, ''):
                    if cancel():
                        try:
                            channel.close()
                        except Exception:
                            pass
                        break
                    try:
                        loop.call_soon_threadsafe(
                            out_queue.put_nowait, (stream_name, line.rstrip("\n")))
                    except Exception:
                        pass
            except Exception:
                pass

        t_out = threading.Thread(target=_reader, args=(stdout, "stdout"), daemon=True)
        t_err = threading.Thread(target=_reader, args=(stderr, "stderr"), daemon=True)
        t_out.start()
        t_err.start()

        exit_code: Optional[int] = None
        timed_out = False
        start = time.time()

        async def _pump():
            nonlocal exit_code
            while True:
                if cancel():
                    break
                if channel.exit_status_ready() and out_queue.empty():
                    exit_code = channel.recv_exit_status()
                    while not out_queue.empty():
                        try:
                            out_queue.get_nowait()
                        except Exception:
                            break
                    break
                try:
                    item = await asyncio.wait_for(out_queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    if time.time() - start > timeout:
                        timed_out = True
                        try:
                            channel.close()
                        except Exception:
                            pass
                        break
                    continue
                yield item
            # exit_code 已通过 nonlocal 赋值，无需 return

        try:
            async for sn, ln in _pump():
                yield {"sse_event": "npu_log", "data": {
                    "step": step_key, "stream": sn, "line": ln}}
        except asyncio.TimeoutError:
            timed_out = True

        t_out.join(timeout=2)
        t_err.join(timeout=2)

        if exit_code is None and not timed_out:
            try:
                if channel.exit_status_ready():
                    exit_code = channel.recv_exit_status()
            except Exception:
                pass

        yield {"sse_event": "npu_cmd_done", "data": {
            "exit_code": exit_code, "timed_out": timed_out, "cancelled": cancel()}}

    # ---------------- SFTP 递归同步 ----------------

    async def _sync_via_sftp(
        self,
        client: paramiko.SSHClient,
        local_root: str,
        remote_root: str,
        cancel: Callable[[], bool],
    ) -> dict:
        """递归 SFTP 上传算子工程目录（排除构建产物）。返回 {files,bytes,error}"""
        stat = {"files": 0, "bytes": 0, "error": ""}

        def _blocking():
            try:
                sftp = client.open_sftp()

                def _ensure_remote_dir(rpath: str):
                    """逐级创建远程目录（已存在则跳过）"""
                    parts = [p for p in rpath.split("/") if p]
                    cur = ""
                    for p in parts:
                        cur = cur + "/" + p
                        try:
                            sftp.stat(cur)
                        except IOError:
                            try:
                                sftp.mkdir(cur)
                            except IOError:
                                pass

                _ensure_remote_dir(remote_root)
                local_root_p = Path(local_root)
                if not local_root_p.is_dir():
                    stat["error"] = f"本地工作目录不存在: {local_root}"
                    return stat

                for lp in local_root_p.rglob("*"):
                    if cancel():
                        break
                    rel = lp.relative_to(local_root_p)
                    # 排除目录
                    if any(part in SYNC_EXCLUDE_DIRS for part in rel.parts):
                        continue
                    # 排除后缀
                    if lp.is_file() and lp.suffix in SYNC_EXCLUDE_SUFFIX:
                        continue
                    rp = remote_root.rstrip("/") + "/" + rel.as_posix()
                    try:
                        if lp.is_dir():
                            _ensure_remote_dir(rp)
                        else:
                            _ensure_remote_dir(str(Path(rp).parent))
                            sftp.put(str(lp), rp)
                            stat["files"] += 1
                            try:
                                stat["bytes"] += lp.stat().st_size
                            except Exception:
                                pass
                    except Exception as e:
                        logger.debug(f"[sftp] 跳过 {rel}: {e}")
                        continue

                sftp.close()
                return stat
            except Exception as e:
                stat["error"] = str(e)
                return stat

        return await asyncio.to_thread(_blocking)

    # ---------------- 远程环境检查 ----------------

    async def _check_remote_env(
        self,
        client: paramiko.SSHClient,
        cancel: Callable[[], bool],
    ) -> Tuple[bool, str]:
        """检查远端 CANN 环境：npu-smi info + ASCEND_HOME_PATH"""
        cmd = (
            'echo "==NPU-SMI=="; npu-smi info 2>&1 | head -20; '
            'echo "==ENV=="; '
            'source /usr/local/Ascend/ascend-toolkit/set_env.sh 2>/dev/null; '
            'echo "ASCEND_HOME_PATH=$ASCEND_HOME_PATH"; '
            'echo "==ARCH=="; uname -m'
        )

        def _blocking():
            try:
                _, out, _ = client.exec_command(cmd, timeout=ENV_CHECK_TIMEOUT)
                return out.read().decode("utf-8", "replace")
            except Exception as e:
                return f"环境检查命令执行失败: {e}"

        text = await asyncio.to_thread(_blocking)
        has_npu = "npu-smi" in text and ("Ascend" in text or "NPU" in text or "Chip" in text)
        has_env = "ASCEND_HOME_PATH=" in text and "ASCEND_HOME_PATH=$" not in text
        ok = has_npu
        info = ("✅ 检测到 NPU 设备与 CANN 环境" if ok
                else "⚠️ 未检测到可用的 NPU 设备或 CANN 环境，可能影响编译/测试")
        return ok, f"{info}\n{text[:500]}"

    # ---------------- 测试结果解析 ----------------

    def _parse_test_result(self, test_output: str) -> dict:
        """从 ST 测试输出解析 pass/fail 与用例数。覆盖 ctest / pytest / PASS-FAIL 行。"""
        passed = failed = 0
        # ctest 风格: "100% tests passed, 0 tests failed out of N"
        m = re.search(
            r'(\d+)%\s*tests?\s*passed.*?(\d+)\s*tests?\s*failed.*?out of\s*(\d+)',
            test_output)
        if m:
            total = int(m.group(3))
            failed = int(m.group(2))
            passed = total - failed
        else:
            # pytest 风格: "===== 5 passed, 1 failed in 3.2s ====="
            mp = re.search(r'(\d+)\s*passed', test_output)
            mf = re.search(r'(\d+)\s*failed', test_output)
            passed = int(mp.group(1)) if mp else 0
            failed = int(mf.group(1)) if mf else 0
            if not mp and not mf:
                # 兜底：匹配 PASS/FAIL/ERROR 行
                passed = len(re.findall(r'(?i)\bPASS(ed)?\b', test_output))
                failed = (len(re.findall(r'(?i)\bFAIL(ed)?\b', test_output))
                          + len(re.findall(r'(?i)\bERROR\b', test_output)))

        return {
            "passed": failed == 0 and passed > 0,
            "passed_count": passed,
            "failed_count": failed,
            "total": passed + failed,
            "raw": test_output[-2000:],
        }

    # ---------------- 完整生命周期 ----------------

    async def run_npu_test_lifecycle(
        self,
        work_dir: str,
        op_name: str,
        host: str,
        remote_dir: str,
        build_cmd: str,
        test_cmd: str,
        session_id: str = "",
        env_check: bool = True,
        cleanup: bool = True,
        cancel_check: Optional[Callable[[], bool]] = None,
    ) -> AsyncGenerator[dict, None]:
        """NPU 测试 7 步生命周期。yield {"sse_event":"npu_xxx","data":{...}}"""
        steps = _new_npu_steps()
        cancel = cancel_check or (lambda: False)

        def _update(key: str, status: str, log: Optional[str] = None):
            for s in steps:
                if s["key"] == key:
                    old = s.get("status")
                    s["status"] = status
                    s["log"] = log
                    now = datetime.now().isoformat()
                    if status == "running" and not s.get("started_at"):
                        s["started_at"] = now
                    if status in ("success", "failed", "cancelled"):
                        s["completed_at"] = now
                        if s.get("started_at"):
                            try:
                                t = datetime.fromisoformat(s["started_at"])
                                s["duration_ms"] = int((datetime.now() - t).total_seconds() * 1000)
                            except Exception:
                                pass
                    break

        def _render(tmpl: str) -> str:
            return (tmpl.replace("{remote_dir}", remote_dir)
                        .replace("{op_name}", op_name)
                        .replace("{host}", host)
                        .replace("{work_dir}", work_dir))

        # ---- start ----
        yield {"sse_event": "npu_start", "data": {
            "status": "running", "steps": steps,
            "host": host, "remote_dir": remote_dir,
            "message": f"开始真机 NPU 测试 — {host}",
            "started_at": datetime.now().isoformat(),
        }}

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        try:
            # ---- Step 1: SSH 连接 ----
            _update("ssh_connect", "running")
            yield {"sse_event": "npu_step_update", "data": {
                "step_key": "ssh_connect", "step": {"status": "running"},
                "steps": steps, "message": f"正在连接 {host}..."}}

            ssh_err = ""
            try:
                await asyncio.to_thread(
                    client.connect, host,
                    timeout=self.connect_timeout,
                    allow_agent=True, look_for_keys=True,
                )
            except Exception as e:
                ssh_err = str(e)

            if ssh_err or cancel():
                ed = classify_npu_error("ssh_connect", ssh_err or "用户取消")
                _update("ssh_connect", "failed", ssh_err)
                yield {"sse_event": "npu_done", "data": {
                    "status": "cancelled" if cancel() else "failed",
                    "steps": steps, "completed_at": datetime.now().isoformat(),
                    "error": ssh_err, "error_detail": ed,
                }}
                return

            _update("ssh_connect", "success")
            yield {"sse_event": "npu_step_update", "data": {
                "step_key": "ssh_connect", "step": {"status": "success"},
                "steps": steps, "message": f"已连接 {host}"}}

            if cancel():
                yield {"sse_event": "npu_done", "data": {
                    "status": "cancelled", "steps": steps,
                    "completed_at": datetime.now().isoformat(),
                    "error": "用户取消",
                    "error_detail": classify_npu_error("cancelled", "用户取消")}}
                return

            # 准备远程目录：mkdir + 清空
            try:
                await asyncio.to_thread(
                    client.exec_command,
                    f"mkdir -p {shlex.quote(remote_dir)} && rm -rf {shlex.quote(remote_dir)}/* {shlex.quote(remote_dir)}/.* 2>/dev/null; echo OK",
                    30,
                )
            except Exception:
                pass

            # ---- Step 2: 同步代码（SFTP 递归）----
            _update("sync_code", "running")
            yield {"sse_event": "npu_step_update", "data": {
                "step_key": "sync_code", "step": {"status": "running"},
                "steps": steps,
                "message": f"同步本地算子代码 → {host}:{remote_dir}..."}}

            sync_stat = await self._sync_via_sftp(client, work_dir, remote_dir, cancel)

            if cancel():
                yield {"sse_event": "npu_done", "data": {
                    "status": "cancelled", "steps": steps,
                    "completed_at": datetime.now().isoformat(),
                    "error": "用户取消",
                    "error_detail": classify_npu_error("cancelled", "用户取消")}}
                return

            if sync_stat.get("error"):
                ed = classify_npu_error("sync_code", sync_stat["error"])
                _update("sync_code", "failed", sync_stat["error"])
                yield {"sse_event": "npu_done", "data": {
                    "status": "failed", "steps": steps,
                    "completed_at": datetime.now().isoformat(),
                    "error": sync_stat["error"], "error_detail": ed}}
                return

            _update("sync_code", "success")
            yield {"sse_event": "npu_step_update", "data": {
                "step_key": "sync_code", "step": {"status": "success"},
                "steps": steps,
                "message": (f"已同步 {sync_stat['files']} 个文件 "
                            f"({sync_stat['bytes'] // 1024} KB)"),
                "sync_stat": {"files": sync_stat["files"], "bytes": sync_stat["bytes"]}}}

            # ---- Step 3: 环境检查（可选）----
            if env_check:
                _update("env_check", "running")
                yield {"sse_event": "npu_step_update", "data": {
                    "step_key": "env_check", "step": {"status": "running"},
                    "steps": steps, "message": "检查远程 CANN 环境..."}}

                env_ok, env_info = await self._check_remote_env(client, cancel)
                _update("env_check", "success" if env_ok else "failed", env_info)
                yield {"sse_event": "npu_step_update", "data": {
                    "step_key": "env_check",
                    "step": {"status": "success" if env_ok else "failed"},
                    "steps": steps, "message": env_info.split("\n")[0]}}

            if cancel():
                yield {"sse_event": "npu_done", "data": {
                    "status": "cancelled", "steps": steps,
                    "completed_at": datetime.now().isoformat(),
                    "error": "用户取消",
                    "error_detail": classify_npu_error("cancelled", "用户取消")}}
                return

            # ---- Step 4: 真机编译 ----
            _update("build", "running")
            yield {"sse_event": "npu_step_update", "data": {
                "step_key": "build", "step": {"status": "running"},
                "steps": steps, "message": "开始真机编译..."}}

            build_full = _render(build_cmd)
            build_collector: list = []
            build_result = None
            async for ev in self._stream_cmd_as_events(
                client, build_full, "build", cancel, line_collector=build_collector,
            ):
                if ev["sse_event"] == "npu_log":
                    yield ev  # 实时转发编译日志
                elif ev["sse_event"] == "npu_cmd_done":
                    build_result = ev["data"]
                    # 不转发 npu_cmd_done 给前端（内部用）

            if cancel():
                yield {"sse_event": "npu_done", "data": {
                    "status": "cancelled", "steps": steps,
                    "completed_at": datetime.now().isoformat(),
                    "error": "用户取消",
                    "error_detail": classify_npu_error("cancelled", "用户取消")}}
                return

            build_exit = (build_result or {}).get("exit_code")
            build_timed_out = (build_result or {}).get("timed_out")

            if build_timed_out:
                ed = classify_npu_error("timeout", "编译超时")
                _update("build", "failed", ed["root_cause"])
                yield {"sse_event": "npu_done", "data": {
                    "status": "timeout", "steps": steps,
                    "completed_at": datetime.now().isoformat(),
                    "error": "编译超时", "error_detail": ed}}
                return

            if build_exit not in (0, None):
                tail = "\n".join(build_collector[-50:]) if build_collector else ""
                ed = classify_npu_error("build", tail or "编译失败", build_exit)
                _update("build", "failed", ed["root_cause"])
                yield {"sse_event": "npu_done", "data": {
                    "status": "failed", "steps": steps,
                    "completed_at": datetime.now().isoformat(),
                    "error": ed["root_cause"], "error_detail": ed}}
                return

            _update("build", "success")
            yield {"sse_event": "npu_step_update", "data": {
                "step_key": "build", "step": {"status": "success"},
                "steps": steps, "message": "编译成功"}}

            # ---- Step 5: ST 穿刺测试 ----
            _update("st_test", "running")
            yield {"sse_event": "npu_step_update", "data": {
                "step_key": "st_test", "step": {"status": "running"},
                "steps": steps, "message": "开始 ST 穿刺测试..."}}

            test_full = _render(test_cmd)
            test_collector: list = []
            test_result = None
            async for ev in self._stream_cmd_as_events(
                client, test_full, "st_test", cancel, line_collector=test_collector,
            ):
                if ev["sse_event"] == "npu_log":
                    yield ev
                elif ev["sse_event"] == "npu_cmd_done":
                    test_result = ev["data"]

            if cancel():
                yield {"sse_event": "npu_done", "data": {
                    "status": "cancelled", "steps": steps,
                    "completed_at": datetime.now().isoformat(),
                    "error": "用户取消",
                    "error_detail": classify_npu_error("cancelled", "用户取消")}}
                return

            test_timed_out = (test_result or {}).get("timed_out")
            if test_timed_out:
                ed = classify_npu_error("timeout", "ST 测试超时")
                _update("st_test", "failed", ed["root_cause"])
                yield {"sse_event": "npu_done", "data": {
                    "status": "timeout", "steps": steps,
                    "completed_at": datetime.now().isoformat(),
                    "error": "ST 测试超时", "error_detail": ed}}
                return

            _update("st_test", "success")
            yield {"sse_event": "npu_step_update", "data": {
                "step_key": "st_test", "step": {"status": "success"},
                "steps": steps, "message": "ST 测试执行完成"}}

            # ---- Step 6: 解析测试结果 ----
            _update("parse_result", "running")
            yield {"sse_event": "npu_step_update", "data": {
                "step_key": "parse_result", "step": {"status": "running"},
                "steps": steps, "message": "解析测试结果..."}}

            test_output = "\n".join(test_collector)
            summary = self._parse_test_result(test_output)
            _update("parse_result", "success")
            yield {"sse_event": "npu_result", "data": {"summary": summary}}
            yield {"sse_event": "npu_step_update", "data": {
                "step_key": "parse_result", "step": {"status": "success"},
                "steps": steps,
                "message": (f"通过 {summary['passed_count']} / 失败 {summary['failed_count']}"
                            f" / 共 {summary['total']}")}}

            # ---- Step 7: 清理远程目录 ----
            if cleanup:
                _update("cleanup", "running")
                try:
                    await asyncio.to_thread(
                        client.exec_command,
                        f"rm -rf {shlex.quote(remote_dir)} && echo CLEANED",
                        30,
                    )
                    _update("cleanup", "success")
                except Exception as e:
                    _update("cleanup", "failed", str(e))

            final_status = "success" if summary["passed"] else "failed"
            yield {"sse_event": "npu_done", "data": {
                "status": final_status, "steps": steps,
                "summary": summary,
                "completed_at": datetime.now().isoformat(),
            }}

        except Exception as e:
            logger.error(f"[npu_test] 生命周期异常: {e}", exc_info=True)
            yield {"sse_event": "npu_done", "data": {
                "status": "failed", "steps": steps,
                "completed_at": datetime.now().isoformat(),
                "error": str(e),
                "error_detail": classify_npu_error("unknown", str(e)),
            }}
        finally:
            try:
                client.close()
            except Exception:
                pass
