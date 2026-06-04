"""
工作流仿真 V2 路由
驱动真实的 Claude Code CLI 执行算子开发全流程
"""
import asyncio
import json
import logging
import os
import re
import time
import uuid
from datetime import datetime
from typing import Optional

import aiohttp

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.services.claude_code_driver import claude_driver, ClaudeCodeDriver
from app.services.workflow_parser import build_workflow_definition

logger = logging.getLogger(__name__)

# 项目根目录
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))
CANNBOT_PLUGINS_DIR = os.path.join(_PROJECT_ROOT, "external", "cannbot-skills", "plugins-official")


# ==================== 请求模型 ====================

class CreateSessionRequest(BaseModel):
    plugin_id: str
    op_name: str
    op_spec: str = ""
    work_dir: str = ""
    step_timeout: int = 1800  # 每步骤超时秒数，默认 30 分钟

# 默认流水线阶段定义（可被需求文档 3.2 覆盖）
DEFAULT_PIPELINE_STAGES = [
    {"name": "编译", "key": "compile"},
    {"name": "单元测试", "key": "unit_test"},
    {"name": "集成测试", "key": "integration_test"},
    {"name": "精度测试", "key": "precision_test"},
    {"name": "性能测试", "key": "performance_test"},
]


# ==================== 辅助函数 ====================

def _find_plugin_dir(plugin_id: str) -> Optional[str]:
    """在 plugins-official 和 plugins-community 中查找插件目录"""
    for parent in ("plugins-official", "plugins-community"):
        d = os.path.join(_PROJECT_ROOT, "external", "cannbot-skills", parent, plugin_id)
        if os.path.isdir(d):
            return d
    return None


def _classify_error(error_content: str, exit_code: Optional[int] = None) -> dict:
    """
    对错误进行自动分类，返回错误详情。
    分类维度：
      - ENV: 基础环境问题（CLI 未安装、Python 缺失、磁盘不足等）
      - NETWORK: 网络问题（API 超时、连接断开、DNS 等）
      - SKILL: Skill/插件问题（引用失败、模板缺失等）
      - CLI: Claude CLI 内部错误（进程崩溃、OOM、内部异常等）
      - TIMEOUT: 超时
      - PERMISSION: 权限问题
      - UNKNOWN: 无法分类
    """
    content = (error_content or "").lower()
    category = "UNKNOWN"
    root_cause = error_content
    suggestion = "查看错误详情排查问题"

    if "未找到" in content or "not found" in content or "cli 未找到" in content:
        category = "ENV"
        root_cause = "Claude Code CLI 未安装或不在 PATH 中"
        suggestion = "运行 `npm install -g @anthropic-ai/claude-code` 安装 CLI，或确认 `claude` 命令在终端可用"
    elif "separator is found, but chunk is longer than limit" in content:
        category = "ENV"
        root_cause = "Python asyncio StreamReader 行缓冲区溢出（64KB 限制）。Claude CLI 的 stream-json 输出中单行 JSON 超过了 Python asyncio 的默认行长度限制。通常是 thinking 内容过长导致。"
        suggestion = "此为驱动层已知限制，需升级 _read_lines 使用无限制的行读取方式（已在新版本中修复）"
    elif "timeout" in content or "超时" in content:
        category = "TIMEOUT"
        root_cause = "Claude Code CLI 执行超时"
        suggestion = "可增大步骤超时时间，或检查 Claude CLI 是否卡住"
    elif "被取消" in content or "cancelled" in content:
        category = "TIMEOUT"
        root_cause = "仿真被用户手动取消"
        suggestion = "正常操作，无需处理"
    elif exit_code == -9:
        category = "CLI"
        root_cause = f"Claude 进程被 SIGKILL 信号终止（exit code -9），通常由系统 OOM Killer 或手动 kill 导致"
        suggestion = "检查系统内存使用情况，或查看是否有其他进程管理工具终止了 claude 进程"
    elif exit_code and exit_code < 0:
        category = "CLI"
        root_cause = f"Claude 进程被信号终止（exit code {exit_code}，信号 {-exit_code}）"
        suggestion = "检查系统资源（内存、CPU）是否充足"
    elif "connection" in content or "网络" in content or "dns" in content or "refused" in content:
        category = "NETWORK"
        root_cause = "网络连接异常"
        suggestion = "检查网络连接，确认能访问 Anthropic API（api.anthropic.com）"
    elif "permission" in content or "权限" in content or "eacces" in content or "access denied" in content:
        category = "PERMISSION"
        root_cause = "文件或命令权限不足"
        suggestion = "检查工作目录和文件的读写权限"
    elif "skill" in content or "插件" in content or "plugin" in content:
        category = "SKILL"
        root_cause = "Skill 或插件相关错误"
        suggestion = "检查 Skill 是否正确安装在工作目录的 .claude/ 目录下"
    elif "启动" in content and "失败" in content:
        category = "CLI"
        root_cause = error_content
        suggestion = "检查 Claude CLI 版本和配置"

    return {
        "category": category,
        "root_cause": root_cause,
        "suggestion": suggestion,
        "original_error": error_content,
        "exit_code": exit_code,
    }


def _summarize_tool_use(tool_name: str, tool_input: dict) -> str:
    """将工具调用转为人类可读的操作摘要"""
    if tool_name == "Read":
        path = tool_input.get("file_path", "")
        return f"📖 读取文件: {path}"
    elif tool_name == "Write":
        path = tool_input.get("file_path", "")
        content = tool_input.get("content", "")
        lines = content.count("\n") + 1 if content else 0
        return f"✏️ 写入文件: {path} ({lines} 行)"
    elif tool_name == "Edit":
        path = tool_input.get("file_path", "")
        return f"📝 编辑文件: {path}"
    elif tool_name == "Bash":
        cmd = tool_input.get("command", "")
        desc = tool_input.get("description", "")
        label = f" — {desc}" if desc else ""
        return f"⚙️ 执行命令: {cmd[:120]}{label}"
    elif tool_name == "Glob":
        pattern = tool_input.get("pattern", "")
        return f"🔍 搜索文件: {pattern}"
    elif tool_name == "Grep":
        pattern = tool_input.get("pattern", "")
        path = tool_input.get("path", "")
        return f"🔍 搜索内容: '{pattern}' in {path}"
    elif tool_name == "Agent":
        desc = tool_input.get("description", "")
        agent_type = tool_input.get("subagent_type", "")
        return f"🤖 调用子Agent: {agent_type} — {desc}"
    elif tool_name == "LSP":
        op = tool_input.get("operation", "")
        path = tool_input.get("filePath", "")
        return f"🔗 LSP {op}: {path}"
    elif tool_name == "WebSearch":
        query = tool_input.get("query", "")
        return f"🌐 搜索: {query}"
    else:
        return f"🔧 {tool_name}({json.dumps(tool_input, ensure_ascii=False)[:100]})"


def _gate_check(work_dir: str, artifacts: list) -> dict:
    """门禁检查：验证产出物文件是否存在"""
    results = []
    for art in artifacts:
        path = os.path.join(work_dir, art) if not os.path.isabs(art) else art
        exists = os.path.exists(path)
        results.append({"name": art, "exists": exists})
    passed = all(r["exists"] for r in results) if results else True
    return {"passed": passed, "artifacts": results}


def _compute_skill_compliance(
    events: list,
    required_skills: list,
) -> dict:
    """计算 Skill 遵从度"""
    referenced = ClaudeCodeDriver.extract_skill_references(events)
    expected = [s for s in required_skills if s]
    missing = [s for s in expected if s not in referenced]
    violations = []

    if missing:
        violations.append({
            "type": "SKILL_NOT_REFERENCED",
            "detail": f"未引用预期 Skill: {', '.join(missing)}",
            "severity": "MED",
        })

    score = len(set(referenced) & set(expected)) / len(expected) if expected else 1.0
    return {
        "score": round(score, 2),
        "skills_referenced": referenced,
        "skills_expected": expected,
        "skills_missing": missing,
        "violations": violations,
    }


def _render_prompt(prompt_template: str, op_name: str, op_spec: str) -> str:
    """渲染 prompt 模板，替换变量"""
    spec_part = f"\n\n需求描述：{op_spec}" if op_spec else ""
    if not prompt_template:
        return f"请执行以下算子的开发工作流：{op_name}。{spec_part}\n遵循 .claude/ 下安装的 Skills 和 Agents 指南。"
    return prompt_template.replace("{operator_name}", op_name).replace("{op_name}", op_name).replace("{op_spec}", op_spec or op_name)


async def _run_git(*args, cwd: str = None) -> dict:
    """执行 git 命令"""
    cmd = ["git"] + list(args)
    proc = await asyncio.create_subprocess_exec(
        *cmd, cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
    return {
        "returncode": proc.returncode,
        "stdout": stdout.decode("utf-8", errors="replace").strip(),
        "stderr": stderr.decode("utf-8", errors="replace").strip(),
    }


# ==================== 路由注册 ====================

def register_workflow_sim_v2_routes(router: APIRouter, db=None):
    """注册工作流仿真 V2 路由"""

    @router.post("/cannbot/workflow-v2/fork-repo")
    async def fork_repo(request: dict):
        """通过 GitCode API fork 仓库到用户账号"""
        repo_url = request.get("repo_url", "").strip()
        token = request.get("token", "").strip()
        if not repo_url:
            return {"error": "请输入仓库地址"}
        if not token:
            return {"error": "请输入 GitCode Token"}

        # 解析 owner/repo from URL，支持多种格式：
        # https://gitcode.com/cann/ops-math.git
        # https://atomgit.com/cann/ops-math
        # cann/ops-math
        match = re.search(r'[:/]([^/]+/[^/]+?)(?:\.git)?$', repo_url)
        if not match:
            return {"error": "无法解析仓库地址，请使用 https://gitcode.com/{owner}/{repo}.git 格式"}
        owner_repo = match.group(1)
        owner, repo = owner_repo.split("/", 1)

        try:
            async with aiohttp.ClientSession() as session:
                # Step 1: 先查用户是否已有同名仓库（即已 fork）
                user_repos_url = "https://api.gitcode.com/api/v5/user/repos"
                async with session.get(
                    user_repos_url,
                    params={"access_token": token, "repo_name": repo, "per_page": 100},
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as check_resp:
                    if check_resp.status == 200:
                        user_repos = await check_resp.json()
                        if isinstance(user_repos, list):
                            for ur in user_repos:
                                if ur.get("name") == repo and ur.get("fork"):
                                    fork_path = ur.get("full_name", "") or ur.get("path_with_namespace", "")
                                    fork_https = ur.get("https_url_to_repo", "") or ur.get("ssh_url", "") or (f"https://gitcode.com/{fork_path}.git" if fork_path else "")
                                    return {
                                        "status": "already_forked",
                                        "fork_url": fork_https,
                                        "fork_ssh": ur.get("ssh_url_to_repo", ""),
                                        "fork_path": fork_path,
                                        "message": "仓库已 fork 到您的账号",
                                    }

                # Step 2: 不存在则调 fork API
                fork_api_url = f"https://api.gitcode.com/api/v5/repos/{owner}/{repo}/forks"
                async with session.post(
                    fork_api_url,
                    params={"access_token": token},
                    timeout=aiohttp.ClientTimeout(total=60),
                ) as resp:
                    body = await resp.json()

                    if resp.status in (200, 201):
                        fork_path = body.get("full_name", "") or body.get("path_with_namespace", "")
                        fork_https = body.get("https_url_to_repo", "") or (f"https://gitcode.com/{fork_path}.git" if fork_path else "")
                        fork_ssh = body.get("ssh_url_to_repo", "")
                        return {
                            "status": "forked",
                            "fork_url": fork_https,
                            "fork_ssh": fork_ssh,
                            "fork_path": fork_path,
                        }

                    # 处理各种"已存在"情况
                    if resp.status in (409, 422):
                        body_str = json.dumps(body, ensure_ascii=False) if isinstance(body, dict) else str(body)
                        exist_keywords = ["已经存在", "already exist", "already been forked", "duplicate"]
                        if any(kw in body_str.lower() or kw in body_str for kw in exist_keywords):
                            # 尝试再次查找
                            async with session.get(
                                user_repos_url,
                                params={"access_token": token, "repo_name": repo, "per_page": 100},
                                timeout=aiohttp.ClientTimeout(total=30),
                            ) as retry_check:
                                if retry_check.status == 200:
                                    retry_repos = await retry_check.json()
                                    if isinstance(retry_repos, list):
                                        for ur in retry_repos:
                                            if ur.get("name") == repo:
                                                fp = ur.get("full_name", "") or ur.get("path_with_namespace", "")
                                                return {
                                                    "status": "already_forked",
                                                    "fork_url": ur.get("https_url_to_repo", "") or ur.get("ssh_url", "") or (f"https://gitcode.com/{fp}.git" if fp else ""),
                                                    "fork_ssh": ur.get("ssh_url_to_repo", ""),
                                                    "fork_path": fp,
                                                    "message": "仓库已 fork 到您的账号",
                                                }
                            return {"error": "仓库可能已 fork，但无法获取 fork 地址，请在 GitCode 上手动查看"}

                    error_msg = body.get("message", body.get("error_message", "")) if isinstance(body, dict) else str(body)
                    return {"error": f"Fork 失败 ({resp.status}): {error_msg}"}

        except asyncio.TimeoutError:
            return {"error": "Fork 请求超时，请稍后重试"}
        except Exception as e:
            return {"error": f"Fork 请求失败: {e}"}

    @router.get("/cannbot/workflow-v2/check-repo")
    async def check_repo(target_dir: str = ""):
        """检查目录是否已存在且是 git 仓库"""
        if not target_dir:
            return {"exists": False, "is_git": False}
        target_path = os.path.abspath(target_dir)
        exists = os.path.isdir(target_path)
        is_git = os.path.isdir(os.path.join(target_path, ".git")) if exists else False
        branch = None
        if is_git:
            result = await _run_git("rev-parse", "--abbrev-ref", "HEAD", cwd=target_path)
            if result["returncode"] == 0:
                branch = result["stdout"]
        return {"exists": exists, "is_git": is_git, "branch": branch, "path": target_path}

    @router.post("/cannbot/workflow-v2/clone-repo")
    async def clone_repo(request: dict):
        """Clone 算子库到指定工作目录"""
        repo_url = request.get("repo_url", "").strip()
        target_dir = request.get("target_dir", "").strip()
        if not repo_url:
            return {"error": "请输入算子库地址"}
        if not target_dir:
            return {"error": "请输入工作目录"}

        target_path = os.path.abspath(target_dir)

        # 检查是否已存在
        if os.path.isdir(target_path) and os.path.isdir(os.path.join(target_path, ".git")):
            branch_result = await _run_git("rev-parse", "--abbrev-ref", "HEAD", cwd=target_path)
            return {
                "status": "already_exists",
                "path": target_path,
                "branch": branch_result["stdout"] if branch_result["returncode"] == 0 else None,
            }

        # 如果目录已存在但不是 git 仓库，报错
        if os.path.isdir(target_path):
            return {"error": f"目录已存在但不是 git 仓库: {target_path}"}

        # 执行 clone
        os.makedirs(os.path.dirname(target_path) or ".", exist_ok=True)
        result = await _run_git("clone", repo_url, target_path)
        if result["returncode"] != 0:
            return {"error": f"Clone 失败: {result['stderr']}"}

        return {"status": "cloned", "path": target_path}

    @router.get("/cannbot/workflow-v2/list-branches")
    async def list_branches(work_dir: str = ""):
        """列出本地仓库的所有分支（本地 + 远程）"""
        if not work_dir:
            return {"error": "请提供工作目录"}
        work_path = os.path.abspath(work_dir)
        if not os.path.isdir(os.path.join(work_path, ".git")):
            return {"error": "目录不是 git 仓库"}

        # 获取当前分支
        cur = await _run_git("rev-parse", "--abbrev-ref", "HEAD", cwd=work_path)
        current_branch = cur["stdout"] if cur["returncode"] == 0 else ""

        # 列出所有分支（本地 + 远程）
        br = await _run_git("branch", "-a", "--format=%(refname:short)", cwd=work_path)
        if br["returncode"] != 0:
            return {"error": f"获取分支失败: {br['stderr']}"}

        branches = []
        remote_prefix = "origin/"
        for line in br["stdout"].splitlines():
            line = line.strip()
            if not line:
                continue
            is_remote = line.startswith(remote_prefix)
            name = line[len(remote_prefix):] if is_remote else line
            # 去重：同名分支优先保留本地
            if name not in [b["name"] for b in branches]:
                branches.append({
                    "name": name,
                    "is_remote": is_remote,
                    "is_current": name == current_branch,
                })

        # 当前分支置顶
        branches.sort(key=lambda b: (not b["is_current"], b["is_remote"], b["name"]))
        return {"current_branch": current_branch, "branches": branches}

    @router.post("/cannbot/workflow-v2/create-branch")
    async def create_branch(request: dict):
        """在本地仓库创建新分支并切换到该分支（基于指定的 base 分支）"""
        work_dir = request.get("work_dir", "").strip()
        branch_name = request.get("branch_name", "").strip()
        base_branch = request.get("base_branch", "").strip()  # 可选，默认自动检测主分支
        if not work_dir:
            return {"error": "请提供工作目录"}
        if not branch_name:
            return {"error": "请输入分支名称"}
        work_path = os.path.abspath(work_dir)
        if not os.path.isdir(os.path.join(work_path, ".git")):
            return {"error": "目录不是 git 仓库"}

        # 检查分支是否已存在
        check = await _run_git("branch", "--list", branch_name, cwd=work_path)
        if check["returncode"] == 0 and check["stdout"].strip():
            sw = await _run_git("checkout", branch_name, cwd=work_path)
            if sw["returncode"] != 0:
                return {"error": f"切换分支失败: {sw['stderr']}"}
            return {"status": "switched", "branch": branch_name, "message": f"已切换到分支 {branch_name}"}

        # 确定 base 分支：优先用户指定，否则自动找 origin/main 或 origin/master
        if not base_branch:
            # 先 fetch 确保远程引用最新
            await _run_git("fetch", "origin", cwd=work_path)
            for candidate in ("origin/main", "origin/master"):
                r = await _run_git("rev-parse", "--verify", candidate, cwd=work_path)
                if r["returncode"] == 0:
                    base_branch = candidate
                    break
            if not base_branch:
                # 回退到当前 HEAD
                base_branch = "HEAD"

        # 基于指定起点创建新分支
        result = await _run_git("checkout", "-b", branch_name, base_branch, cwd=work_path)
        if result["returncode"] != 0:
            return {"error": f"创建分支失败: {result['stderr']}"}
        return {
            "status": "created",
            "branch": branch_name,
            "base": base_branch,
            "message": f"已基于 {base_branch} 创建并切换到分支 {branch_name}",
        }

    @router.post("/cannbot/workflow-v2/switch-branch")
    async def switch_branch(request: dict):
        """切换到指定分支"""
        work_dir = request.get("work_dir", "").strip()
        branch_name = request.get("branch_name", "").strip()
        if not work_dir:
            return {"error": "请提供工作目录"}
        if not branch_name:
            return {"error": "请输入分支名称"}
        work_path = os.path.abspath(work_dir)
        if not os.path.isdir(os.path.join(work_path, ".git")):
            return {"error": "目录不是 git 仓库"}

        # 如果是远程分支，先创建本地跟踪分支
        remote_branch = f"origin/{branch_name}"
        check_remote = await _run_git("rev-parse", "--verify", remote_branch, cwd=work_path)
        check_local = await _run_git("rev-parse", "--verify", branch_name, cwd=work_path)

        if check_remote["returncode"] == 0 and check_local["returncode"] != 0:
            # 远程分支存在但本地没有，创建跟踪分支
            result = await _run_git("checkout", "-b", branch_name, "--track", remote_branch, cwd=work_path)
        else:
            result = await _run_git("checkout", branch_name, cwd=work_path)

        if result["returncode"] != 0:
            return {"error": f"切换分支失败: {result['stderr']}"}
        return {"status": "switched", "branch": branch_name, "message": f"已切换到分支 {branch_name}"}

    @router.get("/cannbot/workflow-v2/plugins")
    async def list_v2_plugins():
        """列出可用插件（轻量扫描，不解析完整 workflow）"""
        plugins = []
        for parent in ("plugins-official", "plugins-community"):
            parent_dir = os.path.join(_PROJECT_ROOT, "external", "cannbot-skills", parent)
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
                plugin_json_path = os.path.join(plugin_dir, ".claude-plugin", "plugin.json")
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
                agent_count = len([f for f in os.listdir(agents_dir) if f.endswith(".md")]) if os.path.isdir(agents_dir) else 0

                plugins.append({
                    "plugin_id": name,
                    "plugin_name": plugin_name,
                    "description": description,
                    "agents_count": agent_count,
                })
        return {"plugins": plugins}

    @router.post("/cannbot/workflow-v2/sessions")
    async def create_session(req: CreateSessionRequest):
        """创建 V2 仿真会话"""
        plugin_dir = _find_plugin_dir(req.plugin_id)
        if not plugin_dir:
            return {"error": f"插件 {req.plugin_id} 未找到"}

        wf = build_workflow_definition(plugin_dir)
        if not wf:
            return {"error": f"插件 {req.plugin_id} 工作流解析失败"}

        work_dir = req.work_dir or os.path.join("/tmp", f"cannbot-v2-{uuid.uuid4().hex[:8]}")

        session_id = uuid.uuid4().hex[:12]
        now = datetime.now().isoformat()

        steps = []
        for i, step in enumerate(wf.steps):
            prompt_template = step.prompt_def.prompt_template if step.prompt_def else ""
            required_skills = step.prompt_def.required_skills + step.prompt_def.recommended_skills if step.prompt_def else []
            artifacts = step.output_artifacts or []

            steps.append({
                "step_id": step.step_id,
                "step_name": step.name,
                "step_index": i,
                "status": "pending",
                "prompt_template": prompt_template,
                "required_skills": required_skills,
                "output_artifacts": artifacts,
                "dispatch_target": step.dispatch_target,
                "fallback": step.fallback,
                "output": "",
                "events": [],
                "duration_ms": 0,
                "gate_passed": None,
                "gate_artifacts": [],
                "skill_compliance": None,
                "token_usage": {},
                "started_at": None,
                "completed_at": None,
            })

        # 初始化流水线阶段
        pipeline_stages = [
            {**s, "status": "pending", "log": None, "started_at": None, "completed_at": None, "duration_ms": 0}
            for s in DEFAULT_PIPELINE_STAGES
        ]

        session = {
            "session_id": session_id,
            "plugin_id": req.plugin_id,
            "plugin_name": wf.plugin_name,
            "op_name": req.op_name,
            "op_spec": req.op_spec,
            "work_dir": work_dir,
            "step_timeout": req.step_timeout,
            "status": "pending",
            "steps": steps,
            "breakpoint_alerts": [],
            "summary": None,
            "pipeline": {
                "status": "pending",
                "mr_url": None,
                "mr_iid": None,
                "stages": pipeline_stages,
                "triggered_at": None,
                "completed_at": None,
                "fix_rounds": [],
            },
            "created_at": now,
            "completed_at": None,
            "total_steps": len(steps),
        }

        if db:
            await db.save_workflow_sim_v2_session(session)

        return session

    @router.get("/cannbot/workflow-v2/sessions")
    async def list_sessions(limit: int = 30):
        """列出 V2 仿真会话"""
        if db:
            sessions = await db.get_workflow_sim_v2_sessions(limit)
            return {"total": len(sessions), "sessions": sessions}
        return {"total": 0, "sessions": []}

    @router.get("/cannbot/workflow-v2/sessions/active")
    async def get_active_session():
        """获取当前正在运行的会话（最多返回 1 个）"""
        if not db:
            return {"active": None}
        sessions = await db.get_workflow_sim_v2_sessions(limit=50)
        for s in sessions:
            if s.get("status") == "running":
                return {"active": s}
        return {"active": None}

    def _fill_legacy_logs(session: dict) -> dict:
        """兼容老会话：从 steps 数据反向生成 terminal_log 和 simulation_log"""
        steps = session.get("steps", [])
        if not steps:
            return session

        if not session.get("terminal_log"):
            terminal_log = []
            for step in steps:
                step_id = step.get("step_id", "")
                for ev in step.get("events", []):
                    ev_type = ev.get("type", "")
                    content = str(ev.get("content", ""))
                    name = ev.get("name", "")
                    if ev_type == "tool_use" and name:
                        content = _summarize_tool_use(name, ev.get("input") or {})
                    terminal_log.append({
                        "time": step.get("started_at", "")[11:19] if step.get("started_at") else "",
                        "type": ev_type,
                        "content": content[:500],
                        "step_id": step_id,
                    })
            session["terminal_log"] = terminal_log

        if not session.get("simulation_log"):
            simulation_log = []
            summary = session.get("summary")
            for i, step in enumerate(steps):
                step_id = step.get("step_id", "")
                step_name = step.get("step_name", "")
                status = step.get("status", "")
                duration = step.get("duration_ms", 0)
                started = step.get("started_at", "")
                time_str = started[11:19] if started else ""
                simulation_log.append({"time": time_str, "type": "info", "text": f"[{i+1}/{len(steps)}] {step_name}"})
                if status == "completed":
                    gate = "门禁通过" if step.get("gate_passed", True) else "门禁未通过"
                    ed = step.get("error_detail")
                    err_info = f" [{ed['category']}]" if ed else ""
                    simulation_log.append({"time": time_str, "type": "warn" if ed else "success", "text": f"{step_id} 完成 ({duration}ms, {gate}){err_info}"})
                elif status == "failed":
                    simulation_log.append({"time": time_str, "type": "error", "text": f"{step_id} 失败"})
            if summary:
                simulation_log.append({"time": session.get("completed_at", "")[11:19] if session.get("completed_at") else "", "type": "info", "text": f"仿真完成 — {summary.get('verdict', '-')}, {summary.get('passed_steps', 0)}/{summary.get('total_steps', 0)} 步通过"})
            session["simulation_log"] = simulation_log

        return session

    @router.get("/cannbot/workflow-v2/sessions/{session_id}")
    async def get_session(session_id: str):
        """获取 V2 仿真会话详情"""
        if db:
            session = await db.get_workflow_sim_v2_session(session_id)
            if session:
                return _fill_legacy_logs(session)
        return {"error": "会话未找到"}

    @router.get("/cannbot/workflow-v2/sessions/{session_id}/process")
    async def get_session_process(session_id: str):
        """获取会话的 Claude 进程信息"""
        # 驱动器中的实时状态
        proc_info = claude_driver.get_process_info(session_id)
        # 每个步骤的进程信息
        step_procs = {}
        if db:
            session = await db.get_workflow_sim_v2_session(session_id)
            if session:
                for step in session.get("steps", []):
                    sid = step.get("step_id", "")
                    sp = claude_driver.get_step_process(session_id, sid)
                    if sp:
                        step_procs[sid] = sp
        return {
            "session_id": session_id,
            "process": proc_info,
            "step_processes": step_procs,
        }

    @router.get("/cannbot/workflow-v2/processes")
    async def list_all_processes():
        """列出所有被追踪的 Claude 进程"""
        return {"processes": claude_driver.get_all_processes()}

    @router.post("/cannbot/workflow-v2/sessions/{session_id}/start")
    async def start_session(session_id: str):
        """启动仿真（标记为 running，实际执行在 SSE 端点）"""
        if db:
            session = await db.get_workflow_sim_v2_session(session_id)
            if not session:
                return {"error": "会话未找到"}
            await db.update_workflow_sim_v2_session(session_id, {
                "status": "running",
            })
        return {"session_id": session_id, "status": "running"}

    @router.post("/cannbot/workflow-v2/sessions/{session_id}/stop")
    async def stop_session(session_id: str):
        """停止仿真：杀进程 + 标记状态"""
        claude_driver.stop(session_id)
        if db:
            session = await db.get_workflow_sim_v2_session(session_id)
            if session:
                steps = session.get("steps", [])
                for s in steps:
                    if s.get("status") == "running":
                        s["status"] = "failed"
                        s["completed_at"] = datetime.now().isoformat()
                await db.update_workflow_sim_v2_session(session_id, {
                    "status": "stopped",
                    "steps": steps,
                    "completed_at": datetime.now().isoformat(),
                })
        return {"session_id": session_id, "stopped": True}

    @router.get("/cannbot/workflow-v2/sessions/{session_id}/stream")
    async def stream_session(session_id: str):
        """SSE 实时流：驱动 Claude Code CLI 按步骤执行"""
        if not db:
            return {"error": "数据库未连接"}

        session = await db.get_workflow_sim_v2_session(session_id)
        if not session:
            return {"error": "会话未找到"}

        async def event_generator():
            work_dir = session.get("work_dir", "")
            op_name = session.get("op_name", "")
            op_spec = session.get("op_spec", "")
            steps = session.get("steps", [])
            plugin_id = session.get("plugin_id", "")
            step_timeout = session.get("step_timeout", 1800)
            alerts = []
            all_tokens = {"input": 0, "output": 0}

            # 日志收集器
            terminal_log = []  # 终端输出日志（所有 claude_output 事件）
            simulation_log = []  # 仿真日志（关键事件：启动、步骤开始/完成、告警、门禁、结束）

            def _ts():
                return datetime.now().strftime("%H:%M:%S")

            # 确保工作目录存在
            os.makedirs(work_dir, exist_ok=True)

            # 发送 start 事件
            simulation_log.append({"time": _ts(), "type": "info", "text": f"开始仿真: {op_name} ({len(steps)} 步)"})
            yield f"event: start\ndata: {json.dumps({'session_id': session_id, 'plugin_id': plugin_id, 'op_name': op_name, 'total_steps': len(steps)})}\n\n"

            for i, step in enumerate(steps):
                if step.get("status") == "completed":
                    continue

                step_id = step["step_id"]
                step_name = step["step_name"]
                prompt_template = step.get("prompt_template", "")
                required_skills = step.get("required_skills", [])
                artifacts = step.get("output_artifacts", [])

                # 渲染 prompt
                prompt = _render_prompt(prompt_template, op_name, op_spec)

                # 更新步骤状态
                step["status"] = "running"
                step["started_at"] = datetime.now().isoformat()
                await db.update_workflow_sim_v2_session(session_id, {"steps": steps})

                # 发送 step_start
                simulation_log.append({"time": _ts(), "type": "info", "text": f"[{i+1}/{len(steps)}] {step_name}"})
                # 获取刚启动的进程信息写入 step
                proc_info = claude_driver.get_process_info(session_id)
                if proc_info:
                    step["process"] = proc_info
                yield f"event: step_start\ndata: {json.dumps({'step_id': step_id, 'step_name': step_name, 'step_index': i, 'total': len(steps), 'prompt': prompt[:200]}, ensure_ascii=False)}\n\n"

                # 调用 Claude Code CLI
                events = []
                step_output_parts = []
                step_start_time = time.time()

                async for ev in claude_driver.run_step(session_id, prompt, work_dir, timeout=step_timeout, step_id=step_id):
                    events.append(ev)

                    # 转发 claude_output 事件
                    ev_type = ev["type"]
                    if ev_type == "tool_use":
                        tool_name = ev.get("name", "")
                        tool_input = ev.get("input", {})
                        summary = _summarize_tool_use(tool_name, tool_input)
                        step_output_parts.append(summary)
                        terminal_log.append({"time": _ts(), "type": "tool_use", "content": summary, "step_id": step_id})
                        yield f"event: claude_output\ndata: {json.dumps({'step_id': step_id, 'type': 'tool_use', 'content': summary, 'tool_name': tool_name, 'tool_input': tool_input}, ensure_ascii=False)}\n\n"
                    elif ev_type == "tool_result":
                        output_content = str(ev.get("output", ""))[:2000]
                        tool_name = ev.get("name", "")
                        step_output_parts.append(f"[{tool_name}] {output_content[:200]}")
                        terminal_log.append({"time": _ts(), "type": "tool_result", "content": output_content[:500], "step_id": step_id})
                        yield f"event: claude_output\ndata: {json.dumps({'step_id': step_id, 'type': 'tool_result', 'content': output_content, 'tool_name': tool_name}, ensure_ascii=False)}\n\n"
                    elif ev_type in ("text", "thinking", "raw"):
                        output_content = ev.get("content", "")
                        if output_content:
                            step_output_parts.append(str(output_content))
                        terminal_log.append({"time": _ts(), "type": ev_type, "content": str(output_content or "")[:500], "step_id": step_id})
                        yield f"event: claude_output\ndata: {json.dumps({'step_id': step_id, 'type': ev_type, 'content': str(output_content or '')[:2000]}, ensure_ascii=False)}\n\n"

                    elif ev["type"] == "timeout":
                        error_detail = _classify_error("步骤执行超时", exit_code=None)
                        alerts.append({
                            "type": "STEP_TIMEOUT",
                            "severity": "HIGH",
                            "step_id": step_id,
                            "message": f"步骤 {step_name} 超时",
                            "root_cause": f"步骤在 {step_timeout} 秒内未完成，Claude CLI 可能卡住或任务过于复杂",
                            "suggestion": "增大步骤超时时间，或检查 Claude CLI 是否正常响应",
                            "error_category": "TIMEOUT",
                            "detected_at": datetime.now().isoformat(),
                        })
                        simulation_log.append({"time": _ts(), "type": "warn", "text": f"步骤 {step_name} 超时 ({step_timeout}s)"})
                        yield f"event: breakpoint_alert\ndata: {json.dumps(alerts[-1], ensure_ascii=False)}\n\n"

                    elif ev["type"] == "error":
                        error_content = ev.get("content", "未知错误")
                        error_detail = _classify_error(error_content)
                        alerts.append({
                            "type": error_detail["category"],
                            "severity": "CRITICAL",
                            "step_id": step_id,
                            "message": error_content,
                            "root_cause": error_detail["root_cause"],
                            "suggestion": error_detail["suggestion"],
                            "error_category": error_detail["category"],
                            "detected_at": datetime.now().isoformat(),
                        })
                        step["error_detail"] = error_detail
                        simulation_log.append({"time": _ts(), "type": "error", "text": f"[CRITICAL] {error_content}"})
                        yield f"event: breakpoint_alert\ndata: {json.dumps(alerts[-1], ensure_ascii=False)}\n\n"

                    elif ev["type"] == "result":
                        # 提取 token 用量
                        tokens = ev.get("tokens", {})
                        step["token_usage"] = tokens
                        if isinstance(tokens, dict):
                            all_tokens["input"] += tokens.get("input", 0)
                            all_tokens["output"] += tokens.get("output", 0)

                step_duration = int((time.time() - step_start_time) * 1000)

                # 门禁检查
                gate = _gate_check(work_dir, artifacts)
                step["gate_passed"] = gate["passed"]
                step["gate_artifacts"] = gate["artifacts"]

                if not gate["passed"]:
                    missing = [a["name"] for a in gate["artifacts"] if not a["exists"]]
                    simulation_log.append({"time": _ts(), "type": "warn", "text": f"门禁未通过: {', '.join(missing)}"})
                    alerts.append({
                        "type": "ARTIFACT_MISSING",
                        "severity": "HIGH",
                        "step_id": step_id,
                        "message": f"产出物缺失: {', '.join(missing)}",
                        "root_cause": f"步骤执行完成但以下预期文件未生成: {', '.join(missing)}。可能是 Claude 跳过了某些操作，或执行过程中发生了未捕获的错误。",
                        "suggestion": "检查步骤输出日志，确认 Claude 是否完成了产出文件的编写。如果步骤有 error_detail，先解决该错误。",
                        "error_category": "SKILL",
                        "detected_at": datetime.now().isoformat(),
                    })
                    yield f"event: breakpoint_alert\ndata: {json.dumps(alerts[-1], ensure_ascii=False)}\n\n"

                yield f"event: gate_check\ndata: {json.dumps({'step_id': step_id, 'passed': gate['passed'], 'artifacts': gate['artifacts']}, ensure_ascii=False)}\n\n"

                # Skill 遵从度
                compliance = _compute_skill_compliance(events, required_skills)
                step["skill_compliance"] = compliance

                if compliance["violations"]:
                    for v in compliance["violations"]:
                        alerts.append({
                            "type": "SKILL_NOT_REFERENCED",
                            "severity": v.get("severity", "MED"),
                            "step_id": step_id,
                            "message": v["detail"],
                            "root_cause": f"步骤要求的 Skill 文件未被 Claude 读取引用。可能是 Skill 未安装到工作目录的 .claude/ 目录，或 prompt 中缺少 Skill 引用指令。",
                            "suggestion": "确认 Skill 已通过 `bash init.sh project claude` 正确安装到工作目录的 .claude/skills/ 或 .claude/agents/ 目录下",
                            "error_category": "SKILL",
                            "detected_at": datetime.now().isoformat(),
                        })

                yield f"event: skill_compliance\ndata: {json.dumps({'step_id': step_id, **compliance}, ensure_ascii=False)}\n\n"

                # 更新步骤状态
                step["status"] = "completed"
                step["duration_ms"] = step_duration
                step["output"] = "\n".join(step_output_parts)[-20000:]
                step["events"] = [
                    {
                        "type": e["type"],
                        "name": e.get("name", ""),
                        "content": str(e.get("content", ""))[:500],
                        "input": e.get("input") if e.get("type") == "tool_use" else None,
                    }
                    for e in events
                    if e.get("type") not in ("message_start", "message_delta", "message_stop", "text_start", "thinking_start")
                ]
                step["completed_at"] = datetime.now().isoformat()
                # 更新进程信息（进程已退出）
                final_proc = claude_driver.get_process_info(session_id)
                if final_proc:
                    step["process"] = final_proc
                    # 如果进程异常退出且步骤没有 error_detail，补充分类
                    if final_proc.get("exit_code") not in (0, None) and not step.get("error_detail"):
                        proc_error = final_proc.get("error", "") or f"进程异常退出 (exit code {final_proc['exit_code']})"
                        step["error_detail"] = _classify_error(proc_error, exit_code=final_proc["exit_code"])
                        alerts.append({
                            "type": step["error_detail"]["category"],
                            "severity": "HIGH",
                            "step_id": step_id,
                            "message": proc_error,
                            "root_cause": step["error_detail"]["root_cause"],
                            "suggestion": step["error_detail"]["suggestion"],
                            "error_category": step["error_detail"]["category"],
                            "detected_at": datetime.now().isoformat(),
                        })
                        yield f"event: breakpoint_alert\ndata: {json.dumps(alerts[-1], ensure_ascii=False)}\n\n"

                # 仿真日志：步骤完成
                gate_info = f"门禁{'通过' if gate['passed'] else '未通过'}"
                err_info = f" [{step['error_detail']['category']}]" if step.get("error_detail") else ""
                simulation_log.append({"time": _ts(), "type": "success" if not step.get("error_detail") else "warn", "text": f"{step_id} 完成 ({step_duration}ms, {gate_info}){err_info}"})

                await db.update_workflow_sim_v2_session(session_id, {
                    "steps": steps,
                    "breakpoint_alerts": alerts,
                    "terminal_log": terminal_log,
                    "simulation_log": simulation_log,
                })

                # 发送 step_done
                step_done_data = {
                    'step_id': step_id, 'status': 'completed',
                    'duration_ms': step_duration, 'gate_passed': gate['passed'],
                    'token_usage': step['token_usage'], 'skill_compliance_score': compliance['score'],
                }
                if step.get("error_detail"):
                    step_done_data['error_detail'] = step['error_detail']
                yield f"event: step_done\ndata: {json.dumps(step_done_data, ensure_ascii=False)}\n\n"

            # 生成 summary
            completed_steps = [s for s in steps if s.get("status") == "completed"]
            passed_steps = [s for s in completed_steps if s.get("gate_passed", True)]
            failed_steps = [s for s in completed_steps if not s.get("gate_passed", True)]

            summary = {
                "session_id": session_id,
                "total_steps": len(steps),
                "completed_steps": len(completed_steps),
                "passed_steps": len(passed_steps),
                "failed_steps": len(failed_steps),
                "total_alerts": len(alerts),
                "critical_alerts": len([a for a in alerts if a.get("severity") == "CRITICAL"]),
                "total_tokens": all_tokens,
                "verdict": "PASS" if not failed_steps and not alerts else "PASS_WITH_ISSUES" if not failed_steps else "FAIL",
            }

            simulation_log.append({"time": _ts(), "type": "info", "text": f"仿真完成 — {summary['verdict']}, {summary['passed_steps']}/{summary['total_steps']} 步通过"})

            await db.update_workflow_sim_v2_session(session_id, {
                "status": "completed",
                "summary": summary,
                "breakpoint_alerts": alerts,
                "terminal_log": terminal_log,
                "simulation_log": simulation_log,
                "completed_at": datetime.now().isoformat(),
            })

            yield f"event: summary\ndata: {json.dumps(summary, ensure_ascii=False)}\n\n"

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @router.get("/cannbot/workflow-v2/sessions/{session_id}/export")
    async def export_session_log(session_id: str, format: str = "md"):
        """导出会话日志为 Markdown 文件"""
        if not db:
            return {"error": "数据库未连接"}

        session = await db.get_workflow_sim_v2_session(session_id)
        if not session:
            return {"error": "会话未找到"}

        from fastapi.responses import Response

        op_name = session.get("op_name", "unknown")
        plugin_name = session.get("plugin_name", "")
        created_at = session.get("created_at", "")
        work_dir = session.get("work_dir", "")
        steps = session.get("steps", [])
        summary = session.get("summary")
        alerts = session.get("breakpoint_alerts", [])
        terminal_log = session.get("terminal_log", [])
        simulation_log = session.get("simulation_log", [])

        # 兼容老会话
        if not terminal_log or not simulation_log:
            session = _fill_legacy_logs(session)
            terminal_log = session.get("terminal_log", terminal_log)
            simulation_log = session.get("simulation_log", simulation_log)

        lines = []
        lines.append(f"# 工作流仿真报告")
        lines.append("")
        lines.append(f"| 字段 | 值 |")
        lines.append(f"|------|-----|")
        lines.append(f"| 会话 ID | `{session_id}` |")
        lines.append(f"| 算子 | {op_name} |")
        lines.append(f"| 插件 | {plugin_name} |")
        lines.append(f"| 工作目录 | `{work_dir}` |")
        lines.append(f"| 创建时间 | {created_at} |")
        lines.append(f"| 完成时间 | {session.get('completed_at', '-')} |")
        if summary:
            lines.append(f"| 总评 | **{summary.get('verdict', '-')}** |")
            lines.append(f"| 步骤通过 | {summary.get('passed_steps', 0)}/{summary.get('total_steps', 0)} |")
            lines.append(f"| 告警总数 | {summary.get('total_alerts', 0)} ({summary.get('critical_alerts', 0)} CRITICAL) |")
            tokens = summary.get('total_tokens', {})
            lines.append(f"| Token | input {tokens.get('input', 0):,} / output {tokens.get('output', 0):,} |")
        lines.append("")

        # 步骤详情
        lines.append("## 步骤详情")
        lines.append("")
        for i, step in enumerate(steps):
            status = step.get("status", "unknown")
            status_emoji = {"completed": "✅", "running": "🔄", "failed": "❌", "pending": "⏳"}.get(status, "❓")
            duration = step.get("duration_ms", 0)
            gate = step.get("gate_passed")
            gate_str = "通过" if gate else "未通过" if gate is False else "-"
            lines.append(f"### {status_emoji} Step {i+1}: {step.get('step_name', step.get('step_id', ''))}")
            lines.append("")
            lines.append(f"- **状态**: {status}")
            if duration:
                lines.append(f"- **耗时**: {duration}ms ({duration/1000:.1f}s)")
            lines.append(f"- **门禁**: {gate_str}")
            proc = step.get("process")
            if proc:
                lines.append(f"- **进程**: PID {proc.get('pid', '-')}, exit code {proc.get('exit_code', '-')}, {proc.get('elapsed_sec', '-')}s")
            ed = step.get("error_detail")
            if ed:
                lines.append(f"- **错误分类**: {ed.get('category', 'UNKNOWN')}")
                lines.append(f"- **根因**: {ed.get('root_cause', '-')}")
                lines.append(f"- **建议**: {ed.get('suggestion', '-')}")
                lines.append(f"- **原始错误**: `{ed.get('original_error', '-')}`")
            sc = step.get("skill_compliance")
            if sc:
                lines.append(f"- **Skill 遵从度**: {sc.get('score', 0)*100:.0f}% (引用: {', '.join(sc.get('skills_referenced', [])) or '无'}, 缺失: {', '.join(sc.get('skills_missing', [])) or '无'})")
            ga = step.get("gate_artifacts", [])
            if ga:
                for a in ga:
                    lines.append(f"  - {'✅' if a.get('exists') else '❌'} {a.get('name', '')}")
            lines.append("")

        # 告警
        if alerts:
            lines.append("## 告警列表")
            lines.append("")
            for a in alerts:
                severity = a.get("severity", "UNKNOWN")
                cat = a.get("error_category", a.get("type", ""))
                lines.append(f"### [{severity}] {a.get('message', '')}")
                lines.append("")
                if a.get("root_cause"):
                    lines.append(f"- **根因**: {a['root_cause']}")
                if a.get("suggestion"):
                    lines.append(f"- **建议**: {a['suggestion']}")
                if a.get("step_id"):
                    lines.append(f"- **步骤**: {a['step_id']}")
                if a.get("detected_at"):
                    lines.append(f"- **时间**: {a['detected_at']}")
                lines.append("")

        # 仿真日志
        if simulation_log:
            lines.append("## 仿真日志")
            lines.append("")
            lines.append("```")
            for entry in simulation_log:
                prefix = {"info": "INFO ", "warn": "WARN ", "error": "ERROR", "success": " OK  "}.get(entry.get("type", ""), "     ")
                lines.append(f"[{entry.get('time', '')}] {prefix} {entry.get('text', '')}")
            lines.append("```")
            lines.append("")

        # 终端输出
        if terminal_log:
            lines.append("## 终端输出")
            lines.append("")
            lines.append("```")
            for entry in terminal_log:
                t = entry.get("type", "")
                prefix = {"tool_use": "🔧", "tool_result": "⚙️", "text": "📝", "thinking": "💭", "raw": "📄"}.get(t, "  ")
                lines.append(f"[{entry.get('time', '')}] {prefix} [{t}] {entry.get('content', '')}")
            lines.append("```")
            lines.append("")

        md_content = "\n".join(lines)
        filename = f"sim-{session_id}-{op_name}.md"

        return Response(
            content=md_content,
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

