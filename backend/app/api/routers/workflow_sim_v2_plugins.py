"""工作流仿真 V2 路由 — register_plugins_routes（由 workflow_sim_v2.py 拆分）"""

import json
import logging
import os
from datetime import datetime


from fastapi import APIRouter, BackgroundTasks


from .workflow_sim_v2_helpers import (
    _PROJECT_ROOT,
)

logger = logging.getLogger(__name__)


def _ts():
    return datetime.now().strftime("%H:%M:%S")


def register_plugins_routes(router: APIRouter, db=None):
    @router.get("/cannbot/workflow-v2/plugins")
    async def list_v2_plugins():
        """列出可用插件（轻量扫描，不解析完整 workflow）"""
        plugins = []
        for parent in ("plugins-official", "plugins-community"):
            parent_dir = os.path.join(
                _PROJECT_ROOT, "external", "cannbot-skills", parent
            )
            if not os.path.isdir(parent_dir):
                continue
            for name in sorted(os.listdir(parent_dir)):
                plugin_dir = os.path.join(parent_dir, name)
                if not os.path.isdir(plugin_dir):
                    continue
                # 必须有 AGENTS.md 或 CLAUDE.md 才算有效插件
                has_agents = os.path.isfile(os.path.join(plugin_dir, "AGENTS.md"))
                has_claude = os.path.isfile(os.path.join(plugin_dir, "CLAUDE.md"))
                if not has_agents and not has_claude:
                    continue

                # 读 plugin.json 获取名称（如有）
                plugin_name = name
                description = ""
                plugin_json_path = os.path.join(
                    plugin_dir, ".claude-plugin", "plugin.json"
                )
                if os.path.isfile(plugin_json_path):
                    try:
                        with open(plugin_json_path, "r", encoding="utf-8") as f:
                            pj = json.load(f)
                            plugin_name = pj.get("name", name)
                            description = pj.get("description", "")
                    except Exception:
                        pass

                # 快速统计 agents 目录
                agents_dir = os.path.join(plugin_dir, "agents")
                agent_count = (
                    len([f for f in os.listdir(agents_dir) if f.endswith(".md")])
                    if os.path.isdir(agents_dir)
                    else 0
                )

                plugins.append(
                    {
                        "plugin_id": name,
                        "plugin_name": plugin_name,
                        "description": description,
                        "agents_count": agent_count,
                    }
                )
        return {"plugins": plugins}

