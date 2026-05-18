"""
工作流运行器
提供统一的执行入口
"""
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List
from concurrent.futures import ThreadPoolExecutor
import threading

from .state import PipelineState
from .graphs import build_full_analysis_graph, build_incremental_graph
from .config import workflow_config

logger = logging.getLogger(__name__)

# 内存中的任务存储
_tasks: Dict[str, Dict[str, Any]] = {}
_task_lock = threading.Lock()


def _make_initial_state(owner: str, repo: str, max_prs: int) -> PipelineState:
    """构造初始状态"""
    return {
        "owner": owner,
        "repo": repo,
        "max_prs": max_prs,
        "pr_list": [],
        "pr_numbers": [],
        "comments": {},
        "details": {},
        "reviews": {},
        "cicd_results": [],
        "stats_report": {},
        "ai_analysis": "",
        "ai_suggestions": [],
        "ai_risk_assessment": "",
        "report": {},
        "current_step": "init",
        "progress": 0.0,
        "errors": [],
        "started_at": datetime.now().isoformat(),
        "completed_at": "",
    }


def run_full_analysis(owner: str, repo: str, max_prs: int = 0) -> Dict[str, Any]:
    """
    同步执行全量分析工作流 (含 AI 分析)
    """
    if not workflow_config.ready:
        return {"error": "工作流未初始化，请先调用 workflow_config.initialize()"}

    task_id = f"full_{owner}_{repo}_{int(datetime.now().timestamp())}"
    initial_state = _make_initial_state(owner, repo, max_prs)

    with _task_lock:
        _tasks[task_id] = {
            "task_id": task_id,
            "type": "full_analysis",
            "owner": owner,
            "repo": repo,
            "status": "running",
            "state": initial_state,
            "started_at": initial_state["started_at"],
        }

    try:
        graph = build_full_analysis_graph()
        result = graph.invoke(initial_state)

        with _task_lock:
            _tasks[task_id]["status"] = "completed"
            _tasks[task_id]["state"] = result
            _tasks[task_id]["completed_at"] = result.get("completed_at", "")

        return {
            "task_id": task_id,
            "status": "completed",
            "report": result.get("report", {}),
            "ai_analysis": result.get("ai_analysis", ""),
            "ai_suggestions": result.get("ai_suggestions", []),
            "progress": result.get("progress", 100.0),
            "errors": result.get("errors", []),
        }
    except Exception as e:
        logger.error(f"工作流执行失败: {e}")
        with _task_lock:
            _tasks[task_id]["status"] = "failed"
            _tasks[task_id]["error"] = str(e)
        return {
            "task_id": task_id,
            "status": "failed",
            "error": str(e),
        }


def run_full_analysis_async(owner: str, repo: str, max_prs: int = 0) -> str:
    """
    异步执行全量分析，返回 task_id
    """
    task_id = f"full_{owner}_{repo}_{int(datetime.now().timestamp())}"

    with _task_lock:
        _tasks[task_id] = {
            "task_id": task_id,
            "type": "full_analysis",
            "owner": owner,
            "repo": repo,
            "status": "pending",
            "started_at": datetime.now().isoformat(),
        }

    def _run():
        result = run_full_analysis(owner, repo, max_prs)
        with _task_lock:
            if task_id in _tasks:
                _tasks[task_id].update(result)

    executor = ThreadPoolExecutor(max_workers=1)
    executor.submit(_run)

    return task_id


def get_task_status(task_id: str) -> Optional[Dict[str, Any]]:
    """获取任务状态"""
    with _task_lock:
        return _tasks.get(task_id)


def list_tasks() -> List[Dict[str, Any]]:
    """列出所有任务"""
    with _task_lock:
        return list(_tasks.values())
