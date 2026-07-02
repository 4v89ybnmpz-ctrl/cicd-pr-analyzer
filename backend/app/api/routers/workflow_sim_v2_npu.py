"""工作流仿真 V2 路由 — register_npu_routes（由 workflow_sim_v2.py 拆分）"""

import json
import logging
import time
from datetime import datetime


from fastapi import APIRouter, BackgroundTasks
from fastapi.responses import StreamingResponse

from app.services.claude_code_driver import claude_driver, ClaudeCodeDriver

from .workflow_sim_v2_helpers import (
    _npu_test_cancel_flags,
    summarize_tool_use as _summarize_tool_use,
)

logger = logging.getLogger(__name__)


def _ts():
    return datetime.now().strftime("%H:%M:%S")


def register_npu_routes(router: APIRouter, db=None):
    # ==================== 真机 NPU 远程测试 ====================

    @router.get("/cannbot/workflow-v2/npu-hosts")
    async def list_npu_hosts():
        """返回 ~/.ssh/config 解析出的可用 Host 别名列表（不含敏感信息）"""
        from app.services.npu_test_service import NpuTestRunner

        return NpuTestRunner.list_ssh_hosts()

    @router.post("/cannbot/workflow-v2/sessions/{session_id}/cancel-npu-test")
    async def cancel_npu_test(session_id: str):
        """取消正在运行的真机 NPU 测试"""
        _npu_test_cancel_flags[session_id] = True
        if db:
            session = await db.get_workflow_sim_v2_session(session_id)
            if session:
                n = session.get("npu_test") or {}
                if n.get("status") == "running":
                    n["status"] = "cancelled"
                    n["completed_at"] = datetime.now().isoformat()
                    for s in n.get("steps", []):
                        if s.get("status") == "running":
                            s["status"] = "cancelled"
                    await db.update_workflow_sim_v2_session(session_id, {"npu_test": n})
        return {"session_id": session_id, "cancelled": True}

    @router.get("/cannbot/workflow-v2/sessions/{session_id}/npu-test")
    async def trigger_npu_test_sse(
        session_id: str,
        host: str,
        remote_dir: str = "",
        build_cmd: str = "",
        test_cmd: str = "",
        env_check: bool = True,
        cleanup: bool = True,
    ):
        """发起真机 NPU 远程测试（SSE 实时推送）。仿真需已完成。"""
        if not db:
            return {"error": "数据库未连接"}

        session = await db.get_workflow_sim_v2_session(session_id)
        if not session:
            return {"error": "会话未找到"}

        # 校验仿真状态
        if session.get("status") not in ("completed", "stopped"):
            return {"error": "仿真尚未完成，无法发起真机测试"}

        from app.services.npu_test_service import (
            NpuTestRunner,
            DEFAULT_BUILD_CMD,
            DEFAULT_TEST_CMD,
            _new_npu_steps,
        )

        runner = NpuTestRunner()
        work_dir = session.get("work_dir", "")
        op_name = session.get("op_name", "")
        rdir = remote_dir.strip() or f"/tmp/cannbot-npu-{session_id}"
        bcmd = build_cmd.strip() or DEFAULT_BUILD_CMD
        tcmd = test_cmd.strip() or DEFAULT_TEST_CMD

        # 重置 npu_test 状态
        npu = session.get("npu_test") or {}
        npu.update(
            {
                "status": "running",
                "host": host,
                "remote_dir": rdir,
                "build_cmd": bcmd,
                "test_cmd": tcmd,
                "steps": _new_npu_steps(),
                "logs": [],
                "summary": None,
                "triggered_at": datetime.now().isoformat(),
                "completed_at": None,
                "error": None,
                "error_detail": None,
            }
        )
        await db.update_workflow_sim_v2_session(session_id, {"npu_test": npu})

        async def gen():
            try:
                async for event in runner.run_npu_test_lifecycle(
                    work_dir=work_dir,
                    op_name=op_name,
                    host=host,
                    remote_dir=rdir,
                    build_cmd=bcmd,
                    test_cmd=tcmd,
                    session_id=session_id,
                    env_check=env_check,
                    cleanup=cleanup,
                    cancel_check=lambda sid=session_id: _npu_test_cancel_flags.get(
                        sid, False
                    ),
                ):
                    sse_event = event.get("sse_event", "")
                    data = event.get("data", {})
                    if sse_event:
                        yield f"event: {sse_event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

                    # 持久化（与 pipeline 一致的「收到事件即 update」）
                    cur = await db.get_workflow_sim_v2_session(session_id)
                    if cur:
                        n = cur.get("npu_test") or {}
                        if sse_event == "npu_start":
                            n["status"] = "running"
                            n["steps"] = data.get("steps", n.get("steps", []))
                            n["triggered_at"] = data.get(
                                "started_at", n.get("triggered_at")
                            )
                        elif sse_event == "npu_step_update":
                            n["steps"] = data.get("steps", n.get("steps", []))
                        elif sse_event == "npu_log":
                            logs = n.get("logs") or []
                            logs.append(
                                {
                                    "step": data.get("step"),
                                    "stream": data.get("stream"),
                                    "line": data.get("line"),
                                }
                            )
                            n["logs"] = logs[-499:]  # 截断避免文档膨胀
                        elif sse_event == "npu_result":
                            n["summary"] = data.get("summary")
                        elif sse_event == "npu_done":
                            n["status"] = data.get("status")
                            n["steps"] = data.get("steps", n.get("steps", []))
                            n["summary"] = data.get("summary", n.get("summary"))
                            n["completed_at"] = data.get("completed_at")
                            n["error"] = data.get("error")
                            n["error_detail"] = data.get("error_detail")
                            if data.get("status") == "cancelled":
                                _npu_test_cancel_flags.pop(session_id, None)
                        await db.update_workflow_sim_v2_session(
                            session_id, {"npu_test": n}
                        )
            except Exception as e:
                logger.error(f"真机 NPU 测试异常: {e}", exc_info=True)
                yield f"event: npu_done\ndata: {json.dumps({'status': 'failed', 'error': str(e), 'completed_at': datetime.now().isoformat()}, ensure_ascii=False)}\n\n"

        return StreamingResponse(
            gen(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @router.get("/cannbot/workflow-v2/sessions/{session_id}/npu-test-claude")
    async def npu_test_claude(
        session_id: str,
        ssh_host: str = "",
        remote_dir: str = "",
        build_cmd: str = "",
        test_cmd: str = "",
    ):
        """Claude 驱动的真机远程测试：--resume 续接工作流同一会话，Claude 自己 SSH 执行并分析。"""
        if not db:
            return {"error": "数据库未连接"}

        session = await db.get_workflow_sim_v2_session(session_id)
        if not session:
            return {"error": "会话未找到"}

        claude_session_id = session.get("claude_session_id", "")
        work_dir = session.get("work_dir", "")
        op_name = session.get("op_name", "")

        if not claude_session_id:
            return {"error": "无 claude_session_id，无法 --resume 续接会话"}

        npu_prompt = f"""现在需要对算子 {op_name} 进行真机远程测试。

## 远程测试配置
- SSH 主机: {ssh_host}
- 远程目录: {remote_dir}
- 构建命令: {build_cmd or "source /usr/local/Ascend/ascend-toolkit/set_env.sh; cd " + remote_dir + " && bash build.sh"}
- 测试命令: {test_cmd or "source /usr/local/Ascend/ascend-toolkit/set_env.sh; cd " + remote_dir + " && bash run.sh " + op_name + " ascend910b1 st"}

## 执行步骤
1. 用 Bash 工具通过 SSH 将本地 {work_dir} 的算子代码同步到远程 {ssh_host}:{remote_dir}
   - 使用 scp -r 或 rsync
2. 在远程执行构建命令，流式收集输出
3. 在远程执行测试命令，流式收集输出
4. 分析测试结果：
   - 统计 PASS/FAIL/ERROR 数量
   - 如果有失败，分析失败原因并给出修复建议
   - 检查精度是否达标（atol/rtol）
5. 输出结构化测试报告

## 输出格式
请最终输出以下 JSON：
```json
{{
  "verdict": "passed" | "failed",
  "pass_count": 0,
  "fail_count": 0,
  "error_count": 0,
  "summary": "测试摘要",
  "failures": ["失败用例描述"],
  "suggestion": "修复建议（如有）"
}}
```"""

        async def npu_claude_generator():
            yield f"event: npu_claude_start\ndata: {json.dumps({'session_id': session_id, 'claude_session_id': claude_session_id[:16]})}\n\n"

            npu_logs = []
            npu_text = ""
            step_idx = 0

            async for ev in claude_driver.run_step(
                session_id,
                npu_prompt,
                work_dir,
                timeout=600,
                step_id=f"npu_test_claude",
                persist_proc_on_consumer_exit=True,
                resume_session_id=claude_session_id,
            ):
                evt_type = ev.get("type", "")
                if evt_type == "tool_use":
                    tool_name = ev.get("name", "")
                    tool_input = ev.get("input", {})
                    summary = _summarize_tool_use(tool_name, tool_input)
                    npu_logs.append(
                        {
                            "time": _ts(),
                            "type": "tool_use",
                            "content": summary,
                            "tool_name": tool_name,
                        }
                    )
                    yield f"event: npu_claude_log\ndata: {json.dumps({'time': _ts(), 'type': 'tool_use', 'content': summary, 'tool_name': tool_name}, ensure_ascii=False)}\n\n"
                elif evt_type in ("text", "thinking"):
                    c = str(ev.get("content", ""))
                    npu_text += c
                    npu_logs.append(
                        {"time": _ts(), "type": evt_type, "content": c[:500]}
                    )
                    yield f"event: npu_claude_log\ndata: {json.dumps({'time': _ts(), 'type': evt_type, 'content': c[:500]}, ensure_ascii=False)}\n\n"
                elif evt_type == "tool_result":
                    c = str(ev.get("output", ""))[:500]
                    npu_logs.append(
                        {"time": _ts(), "type": "tool_result", "content": c}
                    )
                    yield f"event: npu_claude_log\ndata: {json.dumps({'time': _ts(), 'type': 'tool_result', 'content': c}, ensure_ascii=False)}\n\n"
                elif evt_type == "result":
                    tokens = ev.get("tokens", {})
                    csid = ev.get("claude_session_id", "")
                    if csid:
                        await db.update_workflow_sim_v2_session(
                            session_id, {"claude_session_id": csid}
                        )

            # 持久化
            await db.update_workflow_sim_v2_session(
                session_id,
                {
                    "npu_claude_test": {
                        "status": "completed",
                        "logs": npu_logs[-500:],
                        "response_text": npu_text[:4000],
                        "completed_at": datetime.now().isoformat(),
                    }
                },
            )

            yield f"event: npu_claude_done\ndata: {json.dumps({'response_text': npu_text[:2000]}, ensure_ascii=False)}\n\n"

        return StreamingResponse(
            npu_claude_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

