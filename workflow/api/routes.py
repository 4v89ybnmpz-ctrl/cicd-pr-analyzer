"""
工作流 API 路由（增强版）
支持: SSE 流式推送、多会话对话、批量分析、Agent 状态监控
"""
import json
import logging
import queue
import threading
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, constr
from typing import List, Optional, Literal
from datetime import datetime

logger = logging.getLogger(__name__)


class WorkflowRequest(BaseModel):
    owner: str = Field(..., min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_.\-/]+$")
    repo: str = Field(..., min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_.\-/]+$")
    max_prs: int = Field(0, ge=0, le=10000)


class AgentRequest(BaseModel):
    owner: str = Field(..., min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_.\-/]+$")
    repo: str = Field(..., min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_.\-/]+$")
    max_prs: int = Field(0, ge=0, le=10000)
    mode: Literal["orchestrator", "sequential", "smart"] = "orchestrator"


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=10000)
    conversation_id: Optional[str] = Field(None, max_length=64)


class BatchRequest(BaseModel):
    projects: List[WorkflowRequest] = Field(..., max_length=50)
    mode: Literal["orchestrator", "sequential", "smart"] = "sequential"
    max_workers: int = Field(2, ge=1, le=8)


class SessionChatRequest(BaseModel):
    session_id: str = Field(..., min_length=1, max_length=64)
    message: str = Field(..., min_length=1, max_length=10000)


def register_workflow_routes(router: APIRouter):
    """注册工作流路由"""

    # ====================
    # Health Check
    # ====================

    @router.get("/health", tags=["System"])
    async def health_check():
        """系统健康检查"""
        from workflow.runner import get_health
        health = get_health()
        status_code = 200 if health["status"] == "healthy" else 503
        from fastapi.responses import JSONResponse
        return JSONResponse(content=health, status_code=status_code)

    # ====================
    # 基础工作流
    # ====================

    @router.post("/workflow/analyze", tags=["Workflow"])
    async def run_analysis(request: WorkflowRequest):
        """一键全量分析 (同步)"""
        from workflow.runner import run_full_analysis
        from workflow.config import workflow_config

        if not workflow_config.ready:
            raise HTTPException(status_code=503, detail="工作流未初始化")

        result = run_full_analysis(request.owner, request.repo, request.max_prs)
        return {"timestamp": datetime.now().isoformat(), **result}

    @router.post("/workflow/analyze/async", tags=["Workflow"])
    async def run_analysis_async(request: WorkflowRequest):
        """一键全量分析 (异步)"""
        from workflow.runner import run_full_analysis_async
        from workflow.config import workflow_config

        if not workflow_config.ready:
            raise HTTPException(status_code=503, detail="工作流未初始化")

        task_id = run_full_analysis_async(request.owner, request.repo, request.max_prs)
        return {
            "task_id": task_id, "status": "pending",
            "message": f"已提交 {request.owner}/{request.repo} 分析任务",
            "timestamp": datetime.now().isoformat(),
        }

    @router.get("/workflow/status/{task_id}", tags=["Workflow"])
    async def get_workflow_status(task_id: str):
        """查询工作流执行状态"""
        from workflow.runner import get_task_status

        status = get_task_status(task_id)
        if not status:
            raise HTTPException(status_code=404, detail="任务不存在")
        return {"timestamp": datetime.now().isoformat(), **status}

    @router.get("/workflow/tasks", tags=["Workflow"])
    async def list_workflow_tasks():
        """列出所有工作流任务"""
        from workflow.runner import list_tasks
        tasks = list_tasks()
        return {"tasks": tasks, "total": len(tasks), "timestamp": datetime.now().isoformat()}

    # ====================
    # 多 Agent 接口
    # ====================

    @router.post("/agent/analyze", tags=["Agent"])
    async def run_agent_analysis(request: AgentRequest):
        """多 Agent 分析 (同步)"""
        from workflow.runner import run_multi_agent_analysis
        from workflow.config import workflow_config

        if not workflow_config.ready:
            raise HTTPException(status_code=503, detail="工作流未初始化")

        result = run_multi_agent_analysis(request.owner, request.repo, request.max_prs, request.mode)
        return {"timestamp": datetime.now().isoformat(), **result}

    @router.post("/agent/analyze/async", tags=["Agent"])
    async def run_agent_analysis_async(request: AgentRequest):
        """多 Agent 分析 (异步)"""
        from workflow.runner import run_multi_agent_async
        from workflow.config import workflow_config

        if not workflow_config.ready:
            raise HTTPException(status_code=503, detail="工作流未初始化")

        task_id = run_multi_agent_async(request.owner, request.repo, request.max_prs, request.mode)
        return {
            "task_id": task_id, "status": "pending",
            "message": f"已提交 {request.owner}/{request.repo} 多 Agent 分析任务 (mode={request.mode})",
            "timestamp": datetime.now().isoformat(),
        }

    @router.get("/agent/status/{task_id}", tags=["Agent"])
    async def get_agent_status(task_id: str):
        """查询 Agent 任务状态"""
        from workflow.runner import get_task_status

        status = get_task_status(task_id)
        if not status:
            raise HTTPException(status_code=404, detail="任务不存在")
        return {"timestamp": datetime.now().isoformat(), **status}

    @router.get("/agent/tasks", tags=["Agent"])
    async def list_agent_tasks():
        """列出所有 Agent 任务"""
        from workflow.runner import list_tasks
        tasks = list_tasks()
        return {"tasks": tasks, "total": len(tasks), "timestamp": datetime.now().isoformat()}

    # ====================
    # SSE 流式事件
    # ====================

    @router.get("/agent/stream/{task_id}", tags=["Agent"])
    async def stream_agent_events(task_id: str):
        """
        SSE 流式推送 Agent 执行事件
        客户端可通过 EventSource API 实时接收进度
        """
        from workflow.runner import get_task_status, subscribe_task_events, unsubscribe_task_events

        status = get_task_status(task_id)
        if not status:
            raise HTTPException(status_code=404, detail="任务不存在")

        event_queue = queue.Queue(maxsize=100)

        def _on_event(event):
            try:
                event_queue.put_nowait(event)
            except queue.Full:
                pass

        subscribe_task_events(task_id, _on_event)

        def _event_generator():
            try:
                while True:
                    try:
                        event = event_queue.get(timeout=15)
                        yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

                        if event.get("event_type") in ("completed", "failed", "batch_completed"):
                            break
                    except queue.Empty:
                        # 心跳
                        yield f": keepalive\n\n"

                        current = get_task_status(task_id)
                        if current and current.get("status") in ("completed", "failed"):
                            yield f"data: {json.dumps({'event_type': current['status'], 'task_id': task_id})}\n\n"
                            break
            finally:
                unsubscribe_task_events(task_id, _on_event)

        return StreamingResponse(
            _event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    # ====================
    # 对话式接口 (兼容旧版)
    # ====================

    @router.post("/agent/chat", tags=["Agent"])
    async def agent_chat(request: ChatRequest):
        """对话式接口 — 自动创建会话或使用默认"""
        from workflow.runner import create_session, chat_in_session
        from workflow.config import workflow_config

        if not workflow_config.ai_ready:
            raise HTTPException(status_code=503, detail="AI 不可用")
        session_id = request.conversation_id or create_session()
        result = chat_in_session(session_id, request.message)

        if "error" in result:
            raise HTTPException(status_code=500, detail=result["error"])

        return {
            "response": result["response"],
            "conversation_id": session_id,
            "tool_calls": result.get("tool_calls", 0),
            "timestamp": datetime.now().isoformat(),
        }

    # ====================
    # 多会话管理
    # ====================

    @router.post("/agent/sessions", tags=["Agent"])
    async def create_new_session():
        """创建新的对话会话"""
        from workflow.runner import create_session
        session_id = create_session()
        return {
            "session_id": session_id,
            "created_at": datetime.now().isoformat(),
        }

    @router.post("/agent/sessions/{session_id}/chat", tags=["Agent"])
    async def session_chat(session_id: str, request: SessionChatRequest):
        """在指定会话中对话（支持多轮上下文）"""
        from workflow.runner import chat_in_session
        from workflow.config import workflow_config

        if not workflow_config.ai_ready:
            raise HTTPException(status_code=503, detail="AI 不可用")

        result = chat_in_session(session_id, request.message)

        if "error" in result:
            raise HTTPException(status_code=404 if "不存在" in result["error"] else 500, detail=result["error"])

        return {
            "response": result["response"],
            "session_id": session_id,
            "tool_calls": result.get("tool_calls", 0),
            "stats": result.get("stats", {}),
            "timestamp": datetime.now().isoformat(),
        }

    @router.get("/agent/sessions", tags=["Agent"])
    async def list_all_sessions():
        """列出所有会话"""
        from workflow.runner import list_sessions
        sessions = list_sessions()
        return {"sessions": sessions, "total": len(sessions), "timestamp": datetime.now().isoformat()}

    @router.get("/agent/sessions/{session_id}", tags=["Agent"])
    async def get_session_info(session_id: str):
        """获取会话详情"""
        from workflow.runner import get_session
        session = get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="会话不存在")
        return {"timestamp": datetime.now().isoformat(), **session}

    @router.delete("/agent/sessions/{session_id}", tags=["Agent"])
    async def delete_session(session_id: str):
        """删除会话"""
        from workflow.runner import delete_session
        delete_session(session_id)
        return {"status": "deleted", "session_id": session_id}

    # ====================
    # 批量分析
    # ====================

    @router.post("/agent/batch", tags=["Agent"])
    async def run_batch_analysis(request: BatchRequest):
        """批量分析多个项目"""
        from workflow.runner import run_batch_analysis
        from workflow.config import workflow_config

        if not workflow_config.ready:
            raise HTTPException(status_code=503, detail="工作流未初始化")

        projects = [p.dict() for p in request.projects]
        result = run_batch_analysis(projects, request.mode, request.max_workers)
        return {"timestamp": datetime.now().isoformat(), **result}

    # ====================
    # 监控 & 可观测性
    # ====================

    @router.get("/agent/agents/status", tags=["Agent"])
    async def agents_status():
        """获取所有 Agent 状态和性能指标"""
        from workflow.runner import get_all_agent_status
        statuses = get_all_agent_status()
        return {"timestamp": datetime.now().isoformat(), **statuses}

    @router.get("/agent/blackboard", tags=["Agent"])
    async def blackboard_status():
        """查看共享黑板状态"""
        from workflow.runner import get_blackboard_status
        summary = get_blackboard_status()
        return {"timestamp": datetime.now().isoformat(), **summary}

    # ====================
    # 追踪 & 成本
    # ====================

    @router.get("/agent/traces", tags=["Agent"])
    async def list_traces(limit: int = 20):
        """列出执行追踪"""
        from workflow.runner import get_trace_history
        result = get_trace_history(limit=limit)
        return {"timestamp": datetime.now().isoformat(), **result}

    @router.get("/agent/traces/{trace_id}", tags=["Agent"])
    async def get_trace_detail(trace_id: str):
        """获取追踪详情"""
        from workflow.runner import get_trace_history
        result = get_trace_history(trace_id=trace_id)
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        return {"timestamp": datetime.now().isoformat(), **result}

    @router.get("/agent/traces/project/{owner}/{repo}", tags=["Agent"])
    async def get_project_traces(owner: str, repo: str, limit: int = 10):
        """获取项目的追踪历史"""
        from workflow.runner import get_trace_history
        result = get_trace_history(owner=owner, repo=repo, limit=limit)
        return {"timestamp": datetime.now().isoformat(), **result}

    @router.get("/agent/cost", tags=["Agent"])
    async def cost_report():
        """获取成本报告（Token 用量 + 费用估算）"""
        from workflow.runner import get_cost_report
        report = get_cost_report()
        return {"timestamp": datetime.now().isoformat(), **report}

    # ====================
    # 产物
    # ====================

    @router.get("/agent/artifacts/{owner}/{repo}", tags=["Agent"])
    async def get_artifacts(owner: str, repo: str, type: Optional[str] = None):
        """获取项目分析产物"""
        from workflow.runner import get_artifact
        result = get_artifact(owner, repo, type)
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        return {"timestamp": datetime.now().isoformat(), **result}

    @router.get("/agent/artifacts/{owner}/{repo}/snapshot", tags=["Agent"])
    async def artifact_snapshot(owner: str, repo: str):
        """导出产物快照"""
        from workflow.agents.artifact_store import artifact_store
        snapshot = artifact_store.snapshot()
        return {"timestamp": datetime.now().isoformat(), "snapshot": snapshot}

    # ====================
    # LLM 配置
    # ====================

    @router.get("/agent/llm/config", tags=["Agent"])
    async def get_llm_config():
        """获取当前 LLM 配置"""
        from workflow.config import workflow_config
        llm = workflow_config.llm
        config = {
            "model": getattr(llm, "model_name", "") or getattr(llm, "model", "") or "",
            "base_url": getattr(llm, "anthropic_api_url", "") or getattr(llm, "base_url", "") or "",
            "max_tokens": getattr(llm, "max_tokens", 4096),
            "temperature": getattr(llm, "temperature", 0.3),
            "ai_ready": workflow_config.ai_ready,
            "api_key_set": bool(getattr(llm, "anthropic_api_key", None) or getattr(llm, "api_key", None)),
        }
        return config

    @router.put("/agent/llm/config", tags=["Agent"])
    async def update_llm_config(
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ):
        """热更新 LLM 配置（无需重启）"""
        from workflow.config import workflow_config
        try:
            llm = workflow_config.llm
            changed = []
            if model is not None and hasattr(llm, "model_name"):
                llm.model_name = model
                changed.append(f"model={model}")
            elif model is not None and hasattr(llm, "model"):
                llm.model = model
                changed.append(f"model={model}")
            if base_url is not None and hasattr(llm, "anthropic_api_url"):
                llm.anthropic_api_url = base_url
                changed.append(f"base_url={base_url}")
            elif base_url is not None and hasattr(llm, "base_url"):
                llm.base_url = base_url
                changed.append(f"base_url={base_url}")
            if api_key is not None and hasattr(llm, "anthropic_api_key"):
                llm.anthropic_api_key = api_key
                changed.append("api_key=***")
            elif api_key is not None and hasattr(llm, "api_key"):
                llm.api_key = api_key
                changed.append("api_key=***")
            if max_tokens is not None and hasattr(llm, "max_tokens"):
                llm.max_tokens = max_tokens
                changed.append(f"max_tokens={max_tokens}")
            if temperature is not None and hasattr(llm, "temperature"):
                llm.temperature = temperature
                changed.append(f"temperature={temperature}")
            return {"ok": True, "changed": changed, "message": f"已更新: {', '.join(changed)}" if changed else "无变更"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
