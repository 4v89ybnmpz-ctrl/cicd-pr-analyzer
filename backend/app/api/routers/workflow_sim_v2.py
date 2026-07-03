"""
工作流仿真 V2 路由 — 聚合器
驱动真实的 Claude Code CLI 执行算子开发全流程

按域拆分到子模块，本文件只做路由注册聚合：
  - workflow_sim_v2_repo:            仓库 fork/clone/分支
  - workflow_sim_v2_plugins:         插件列表
  - workflow_sim_v2_sessions:        会话 CRUD
  - workflow_sim_v2_lifecycle:       会话生命周期（start/stop/stream/export）
  - workflow_sim_v2_batch:           批量可用性评估
  - workflow_sim_v2_pipeline:        pipeline CI/CD 触发
  - workflow_sim_v2_npu:             真机 NPU 远程测试
  - workflow_sim_v2_jsonl_routes:    jsonl tail/history
  - workflow_sim_v2_diagnosis:       插件断点诊断（跨 session 病灶聚合）
辅助逻辑见 workflow_sim_v2_helpers / jsonl / skill / drive。
"""

from fastapi import APIRouter

from .workflow_sim_v2_repo import register_repo_routes
from .workflow_sim_v2_plugins import register_plugins_routes
from .workflow_sim_v2_sessions import register_sessions_routes
from .workflow_sim_v2_lifecycle import register_lifecycle_routes
from .workflow_sim_v2_batch import register_batch_routes
from .workflow_sim_v2_pipeline import register_pipeline_routes
from .workflow_sim_v2_npu import register_npu_routes
from .workflow_sim_v2_jsonl_routes import register_jsonl_routes
from .workflow_sim_v2_diagnosis import register_diagnosis_routes
from .workflow_sim_v2_diff import register_diff_routes


def register_workflow_sim_v2_routes(router: APIRouter, db=None):
    """注册工作流仿真 V2 路由（按域聚合）"""
    register_repo_routes(router, db)
    register_plugins_routes(router, db)
    register_sessions_routes(router, db)
    register_lifecycle_routes(router, db)
    register_batch_routes(router, db)
    register_pipeline_routes(router, db)
    register_npu_routes(router, db)
    register_jsonl_routes(router, db)
    register_diagnosis_routes(router, db)
    register_diff_routes(router, db)
