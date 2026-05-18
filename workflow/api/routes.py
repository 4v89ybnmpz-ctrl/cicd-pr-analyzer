"""
工作流 API 路由
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class WorkflowRequest(BaseModel):
    """工作流请求"""
    owner: str
    repo: str
    max_prs: int = 0


class BatchWorkflowRequest(BaseModel):
    """批量工作流请求"""
    projects: List[WorkflowRequest]


def register_workflow_routes(router: APIRouter):
    """注册工作流路由"""

    @router.post("/workflow/analyze", tags=["Workflow"])
    async def run_analysis(request: WorkflowRequest):
        """
        一键全量分析 (同步)
        自动执行: 获取PR → 评论 → 详情 → Reviews → CI/CD分析 → 报告
        """
        from workflow.runner import run_full_analysis
        from workflow.config import workflow_config

        if not workflow_config.ready:
            raise HTTPException(status_code=503, detail="工作流未初始化")

        result = run_full_analysis(request.owner, request.repo, request.max_prs)
        return {"timestamp": datetime.now().isoformat(), **result}

    @router.post("/workflow/analyze/async", tags=["Workflow"])
    async def run_analysis_async(request: WorkflowRequest):
        """
        一键全量分析 (异步)
        返回 task_id，通过 /workflow/status/{task_id} 查询进度
        """
        from workflow.runner import run_full_analysis_async
        from workflow.config import workflow_config

        if not workflow_config.ready:
            raise HTTPException(status_code=503, detail="工作流未初始化")

        task_id = run_full_analysis_async(request.owner, request.repo, request.max_prs)
        return {
            "task_id": task_id,
            "status": "pending",
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
