"""
工作流运行器（增强版）
支持: 同步/异步执行、流式事件推送、多会话管理、批量分析
生产级: health check、graceful shutdown、后台 TTL 清理、统一 logging
"""
import atexit
import logging
import uuid
import time
import threading
from datetime import datetime
from typing import Dict, Any, Optional, List, Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict

from .state import PipelineState
from .graphs import build_full_analysis_graph, build_incremental_graph
from .config import workflow_config
from .agents.blackboard import blackboard
from .agents.base_agent import AgentEvent, AgentEventType
from .agents.registry import agent_registry
from .agents.artifact_store import artifact_store, ArtifactType
from .agents.tracer import trace_manager
from .agents.cost_controller import cost_controller

logger = logging.getLogger(__name__)

# ====================
# 全局状态
# ====================

_tasks: Dict[str, Dict[str, Any]] = {}
_task_lock = threading.Lock()

_sessions: Dict[str, Dict[str, Any]] = {}
_session_lock = threading.Lock()

_event_subscribers: Dict[str, List[Callable]] = defaultdict(list)
_event_lock = threading.Lock()

_shared_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="runner")

_TASK_TTL = 3600
_SESSION_TTL = 7200
_CLEANUP_INTERVAL = 300  # 5 分钟清理一次
_registry_initialized = False


def _init_registry_once():
    """确保 registry 只初始化一次"""
    global _registry_initialized
    if not _registry_initialized:
        agent_registry.set_llm(workflow_config.llm)
        agent_registry.register_defaults()
        _registry_initialized = True


def _periodic_cleanup():
    """后台定时清理过期任务和会话"""
    while not _shutdown_event.is_set():
        _shutdown_event.wait(timeout=_CLEANUP_INTERVAL)
        if not _shutdown_event.is_set():
            _cleanup_expired()
            blackboard.cleanup_expired()
            artifact_store.cleanup_expired()


_shutdown_event = threading.Event()
_cleanup_thread = threading.Thread(target=_periodic_cleanup, daemon=True, name="cleanup")


def _start_background_threads():
    """启动后台线程（只启动一次）"""
    if not _cleanup_thread.is_alive():
        _cleanup_thread.start()


def _shutdown():
    """graceful shutdown: 停线程池、等任务完成"""
    logger.info("Runner shutdown: 停止后台清理线程")
    _shutdown_event.set()
    logger.info("Runner shutdown: 关闭线程池 (等待最多 30s)")
    _shared_executor.shutdown(wait=True)
    logger.info("Runner shutdown: 完成")


atexit.register(_shutdown)


def get_health() -> Dict[str, Any]:
    """健康检查"""
    checks = {
        "status": "healthy",
        "workflow_initialized": workflow_config._initialized,
        "github_service": workflow_config.github_service is not None,
        "database": workflow_config.db is not None,
        "llm_available": workflow_config.llm is not None,
        "registry_agents": len(agent_registry.list_registered()),
        "active_tasks": sum(1 for t in _tasks.values() if t.get("status") == "running"),
        "active_sessions": len(_sessions),
        "thread_pool_active": not _shared_executor._shutdown,
    }
    unhealthy = [k for k, v in checks.items() if v is False and k in ("workflow_initialized", "github_service")]
    if unhealthy:
        checks["status"] = "degraded"
        checks["degraded_components"] = unhealthy

    return checks


def _make_initial_state(owner: str, repo: str, max_prs: int) -> PipelineState:
    return {
        "owner": owner, "repo": repo, "max_prs": max_prs,
        "pr_list": [], "pr_numbers": [], "comments": {},
        "details": {}, "reviews": {}, "cicd_results": [],
        "stats_report": {}, "ai_analysis": "",
        "ai_suggestions": [], "ai_risk_assessment": "",
        "report": {}, "current_step": "init",
        "progress": 0.0, "errors": [],
        "started_at": datetime.now().isoformat(), "completed_at": "",
    }


def _emit_task_event(task_id: str, event_type: str, data: Dict[str, Any] = None):
    with _event_lock:
        callbacks = _event_subscribers.get(task_id, [])
    for cb in callbacks:
        try:
            cb({"task_id": task_id, "event_type": event_type, "data": data or {}, "timestamp": time.time()})
        except Exception as e:
            logger.warning(f"事件推送失败: {e}")


def subscribe_task_events(task_id: str, callback: Callable):
    with _event_lock:
        _event_subscribers[task_id].append(callback)


def unsubscribe_task_events(task_id: str, callback: Callable = None):
    with _event_lock:
        if callback:
            _event_subscribers[task_id] = [cb for cb in _event_subscribers.get(task_id, []) if cb != callback]
        else:
            _event_subscribers.pop(task_id, None)


def _validate_config(need_ai: bool = False) -> Optional[str]:
    """校验配置状态，返回错误信息或 None"""
    if need_ai:
        if not workflow_config.llm:
            return "AI 不可用"
        return None
    # 全量操作需要完整初始化
    if not workflow_config._initialized or not workflow_config.github_service:
        return "工作流未初始化"
    return None


# ====================
# 基础工作流
# ====================

def run_full_analysis(owner: str, repo: str, max_prs: int = 0) -> Dict[str, Any]:
    err = _validate_config()
    if err:
        return {"error": err}

    _start_background_threads()

    task_id = f"full_{owner}_{repo}_{int(datetime.now().timestamp())}"
    initial_state = _make_initial_state(owner, repo, max_prs)

    with _task_lock:
        _tasks[task_id] = {
            "task_id": task_id, "type": "full_analysis",
            "owner": owner, "repo": repo, "status": "running",
            "started_at": initial_state["started_at"], "started_at_ts": time.time(),
        }

    _emit_task_event(task_id, "started", {"owner": owner, "repo": repo})

    try:
        graph = build_full_analysis_graph()
        result = graph.invoke(initial_state)
        with _task_lock:
            _tasks[task_id].update({"status": "completed", "completed_at": result.get("completed_at", ""), "state": result})
        _emit_task_event(task_id, "completed", {"progress": 100})
        return {
            "task_id": task_id, "status": "completed",
            "report": result.get("report", {}),
            "ai_analysis": result.get("ai_analysis", ""),
            "ai_suggestions": result.get("ai_suggestions", []),
            "progress": result.get("progress", 100.0),
            "errors": result.get("errors", []),
        }
    except Exception as e:
        logger.error(f"工作流执行失败: {e}")
        with _task_lock:
            _tasks[task_id].update({"status": "failed", "error": str(e)})
        _emit_task_event(task_id, "failed", {"error": str(e)})
        return {"task_id": task_id, "status": "failed", "error": str(e)}


def run_full_analysis_async(owner: str, repo: str, max_prs: int = 0) -> str:
    task_id = f"full_{owner}_{repo}_{int(datetime.now().timestamp())}"
    with _task_lock:
        _tasks[task_id] = {
            "task_id": task_id, "type": "full_analysis",
            "owner": owner, "repo": repo,
            "status": "pending", "started_at": datetime.now().isoformat(),
        }

    def _run():
        result = run_full_analysis(owner, repo, max_prs)
        with _task_lock:
            if task_id in _tasks:
                _tasks[task_id].update(result)

    _shared_executor.submit(_run)
    return task_id


# ====================
# 多 Agent 工作流
# ====================

def run_multi_agent_analysis(owner: str, repo: str, max_prs: int = 0,
                              mode: str = "orchestrator") -> Dict[str, Any]:
    err = _validate_config()
    if err:
        return {"error": err}

    _start_background_threads()
    _init_registry_once()

    task_id = f"agent_{owner}_{repo}_{int(datetime.now().timestamp())}"

    with _task_lock:
        _tasks[task_id] = {
            "task_id": task_id, "type": f"multi_agent_{mode}",
            "owner": owner, "repo": repo,
            "status": "running", "started_at": datetime.now().isoformat(),
        }

    _emit_task_event(task_id, "started", {"owner": owner, "repo": repo, "mode": mode})

    try:
        from .agent_graphs import build_multi_agent_graph, build_sequential_agent_graph, build_smart_agent_graph
        if mode == "sequential":
            graph = build_sequential_agent_graph()
        elif mode == "smart":
            graph = build_smart_agent_graph()
        else:
            graph = build_multi_agent_graph()

        result = graph.invoke(_make_initial_state(owner, repo, max_prs))

        with _task_lock:
            _tasks[task_id].update({
                "status": "completed",
                "completed_at": result.get("completed_at", ""),
                "progress": result.get("progress", 100.0),
            })
        _emit_task_event(task_id, "completed", {"progress": result.get("progress", 100)})

        return {
            "task_id": task_id, "status": "completed",
            "report": result.get("report", {}),
            "progress": result.get("progress", 100.0),
            "errors": result.get("errors", []),
            "mode": mode, "blackboard": blackboard.summary(),
        }
    except Exception as e:
        logger.error(f"多 Agent 分析失败: {e}")
        with _task_lock:
            _tasks[task_id].update({"status": "failed", "error": str(e)})
        _emit_task_event(task_id, "failed", {"error": str(e)})
        return {"task_id": task_id, "status": "failed", "error": str(e), "mode": mode}


def run_multi_agent_async(owner: str, repo: str, max_prs: int = 0, mode: str = "orchestrator") -> str:
    task_id = f"agent_{owner}_{repo}_{int(datetime.now().timestamp())}"
    with _task_lock:
        _tasks[task_id] = {
            "task_id": task_id, "type": f"multi_agent_{mode}",
            "owner": owner, "repo": repo,
            "status": "pending", "started_at": datetime.now().isoformat(),
        }

    def _run():
        result = run_multi_agent_analysis(owner, repo, max_prs, mode)
        with _task_lock:
            if task_id in _tasks:
                _tasks[task_id].update(result)

    _shared_executor.submit(_run)
    return task_id


# ====================
# 批量分析
# ====================

def run_batch_analysis(projects: List[Dict[str, Any]], mode: str = "sequential",
                        max_workers: int = 2) -> Dict[str, Any]:
    batch_id = f"batch_{int(datetime.now().timestamp())}"
    results = {}
    total = len(projects)

    with _task_lock:
        _tasks[batch_id] = {
            "task_id": batch_id, "type": "batch_analysis",
            "status": "running", "total": total,
            "started_at": datetime.now().isoformat(), "results": {},
        }

    _emit_task_event(batch_id, "batch_started", {"total": total})

    def _analyze_one(project):
        owner, repo, max_prs = project["owner"], project["repo"], project.get("max_prs", 0)
        try:
            result = run_multi_agent_analysis(owner, repo, max_prs, mode)
            return (f"{owner}/{repo}", {"status": "completed", **result})
        except Exception as e:
            return (f"{owner}/{repo}", {"status": "failed", "error": str(e)})

    # 保持结果按项目顺序排列
    ordered_keys = [f"{p['owner']}/{p['repo']}" for p in projects]
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        future_to_idx = {pool.submit(_analyze_one, p): i for i, p in enumerate(projects)}
        for future in as_completed(future_to_idx):
            key, result = future.result()
            results[key] = result
            completed_count = len(results)

            with _task_lock:
                _tasks[batch_id]["results"] = {k: results[k] for k in ordered_keys if k in results}
                _tasks[batch_id]["progress"] = completed_count / total * 100

            _emit_task_event(batch_id, "batch_progress", {
                "completed": completed_count, "total": total, "project": key,
            })

    # 简化 results（上面的排序太复杂，直接用）
    with _task_lock:
        _tasks[batch_id].update({"status": "completed", "completed_at": datetime.now().isoformat(), "results": results})

    completed = sum(1 for r in results.values() if r["status"] == "completed")
    _emit_task_event(batch_id, "batch_completed", {"completed": completed, "total": total})

    return {
        "batch_id": batch_id, "status": "completed",
        "total": total, "completed": completed, "failed": total - completed,
        "results": results,
    }


# ====================
# 会话管理
# ====================

def create_session() -> str:
    session_id = str(uuid.uuid4())[:12]
    with _session_lock:
        _sessions[session_id] = {
            "session_id": session_id, "messages": [],
            "created_at": datetime.now().isoformat(),
            "last_active": datetime.now().isoformat(),
            "last_active_ts": time.time(),
        }
    return session_id


def chat_in_session(session_id: str, message: str) -> Dict[str, Any]:
    from .agents.registry import agent_registry

    err = _validate_config(need_ai=True)
    if err:
        return {"error": err}

    with _session_lock:
        session = _sessions.get(session_id)
        if not session:
            return {"error": "会话不存在"}

    _init_registry_once()

    orchestrator_key = f"orchestrator_{session_id}"
    if not any(d["name"] == orchestrator_key for d in agent_registry.list_registered()):
        agent_registry.register(orchestrator_key, "workflow.agents.orchestrator_agent.OrchestratorAgent", ["session"])
    orchestrator = agent_registry.get(orchestrator_key)
    if not orchestrator or not orchestrator.available:
        return {"error": "Orchestrator 不可用"}

    context = session["messages"][-10:]
    result = orchestrator.run_with_context(message, context)

    with _session_lock:
        session["messages"].append({"role": "user", "content": message})
        session["messages"].append({"role": "assistant", "content": result.get("output", "")})
        session["last_active"] = datetime.now().isoformat()
        session["last_active_ts"] = time.time()

    return {
        "response": result.get("output", ""),
        "session_id": session_id,
        "tool_calls": result.get("tool_calls", 0),
        "stats": result.get("stats", {}),
    }


def get_session(session_id: str) -> Optional[Dict[str, Any]]:
    with _session_lock:
        session = _sessions.get(session_id)
        if session:
            return {
                "session_id": session_id,
                "message_count": len(session["messages"]),
                "created_at": session["created_at"],
                "last_active": session["last_active"],
            }
        return None


def list_sessions() -> List[Dict[str, Any]]:
    with _session_lock:
        return [
            {"session_id": s["session_id"], "message_count": len(s["messages"]),
             "created_at": s["created_at"], "last_active": s["last_active"]}
            for s in _sessions.values()
        ]


def delete_session(session_id: str) -> bool:
    from .agents.registry import agent_registry
    with _session_lock:
        if session_id in _sessions:
            del _sessions[session_id]
    agent_registry.destroy(f"orchestrator_{session_id}")
    return True


# ====================
# 查询
# ====================

def get_task_status(task_id: str) -> Optional[Dict[str, Any]]:
    with _task_lock:
        return _tasks.get(task_id)


def list_tasks() -> List[Dict[str, Any]]:
    with _task_lock:
        return list(_tasks.values())


def _cleanup_expired():
    now = time.time()
    with _task_lock:
        expired = [k for k, v in _tasks.items() if now - v.get("started_at_ts", now) > _TASK_TTL]
        for k in expired:
            del _tasks[k]
    with _session_lock:
        expired_sessions = [k for k, v in _sessions.items() if now - v.get("last_active_ts", now) > _SESSION_TTL]
        for k in expired_sessions:
            del _sessions[k]
            agent_registry.destroy(f"orchestrator_{k}")
    if expired_sessions:
        logger.info(f"清理过期: {len(expired_sessions)} 会话, {len(expired)} 任务")


def get_blackboard_status() -> Dict[str, Any]:
    return blackboard.summary()


def get_all_agent_status() -> Dict[str, Any]:
    _init_registry_once()
    return agent_registry.get_all_status()


def get_trace_history(trace_id: str = None, owner: str = None,
                      repo: str = None, limit: int = 20) -> Dict[str, Any]:
    if trace_id:
        trace = trace_manager.get_trace(trace_id)
        return {"trace": trace} if trace else {"error": "追踪不存在"}
    elif owner and repo:
        return {"traces": trace_manager.get_project_traces(owner, repo, limit)}
    else:
        return {"traces": trace_manager.list_traces(limit)}


def get_cost_report() -> Dict[str, Any]:
    return cost_controller.get_usage_report()


def get_artifact(owner: str, repo: str, artifact_type: str = None) -> Dict[str, Any]:
    if artifact_type:
        try:
            at = ArtifactType(artifact_type)
            content = artifact_store.get_content(at, owner, repo)
            if content is not None:
                return {"artifact_type": artifact_type, "content": content}
            return {"error": f"未找到 {artifact_type} 产物"}
        except ValueError:
            return {"error": f"未知的产物类型: {artifact_type}"}
    else:
        return artifact_store.get_project_artifacts(owner, repo)
