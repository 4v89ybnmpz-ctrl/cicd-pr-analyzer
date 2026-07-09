"""工作流仿真 V2 路由 — register_diff_routes

文件改动 diff：相对于仿真开始时的 work_dir HEAD 基线，展示 Claude 改了哪些文件、每个文件的具体改动。
基线 sha 在 drive_session_events 启动时写入 session.diff_baseline。
"""

import os
from fastapi import APIRouter

from .workflow_sim_v2_helpers import run_git as _run_git


def _parse_numstat_namestatus(stdout: str) -> list:
    """解析 `git diff --numstat --name-status <baseline>` 的输出（已跟踪文件的改动）。

    每行格式：'<status>\t<additions>\t<deletions>\t<path>'
    其中 status 可能是 A/M/D 或 R100/C 等（取首字母）。二进制文件 additions/deletions 为 '-'。
    """
    files = []
    for line in (stdout or "").splitlines():
        line = line.rstrip("\n")
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 4:
            continue
        status_raw, add, dele, path = parts[0], parts[1], parts[2], "\t".join(parts[3:])
        try:
            additions = int(add) if add.isdigit() else 0
        except Exception:
            additions = 0
        try:
            deletions = int(dele) if dele.isdigit() else 0
        except Exception:
            deletions = 0
        files.append({
            "path": path,
            "status": status_raw[0] if status_raw else "M",
            "additions": additions,
            "deletions": deletions,
            "binary": add == "-" or dele == "-",
        })
    return files


async def _list_changed_files(baseline: str, work_dir: str) -> list:
    """列出相对 baseline 的全部改动文件，含 untracked（git diff 默认忽略 untracked）。

    - 已跟踪改动：git diff --numstat --name-status <baseline>
    - baseline 失效时：git log --name-status 列出最近提交的改动文件
    - 新文件（untracked）：git ls-files --others --exclude-standard（status=A，无行数）
    """
    files = []
    # 1. 已跟踪文件改动
    r = await _run_git("diff", "--numstat", "--name-status", baseline, cwd=work_dir)
    if r.get("returncode") == 0:
        files.extend(_parse_numstat_namestatus(r.get("stdout", "")))
    else:
        # baseline 丢失（如 --shared clone alternates 断导致 git 重建），fallback 到最近 commit 的文件改动
        r = await _run_git("log", "--diff-filter=AM", "--name-status", "--pretty=format:", "-20", cwd=work_dir)
        if r.get("returncode") == 0:
            seen = set()
            for parts in [l.split("\t", 1) for l in (r.get("stdout","")).splitlines() if l.strip()]:
                if len(parts) >= 2 and parts[1] not in seen:
                    seen.add(parts[1])
                    files.append({"path": parts[1], "status": parts[0][0] if parts[0] else "M",
                                  "additions": 0, "deletions": 0, "binary": False})
    # 2. untracked 新文件（git diff 看不到，单独列）
    r2 = await _run_git("ls-files", "--others", "--exclude-standard", cwd=work_dir)
    if r2.get("returncode") == 0:
        existing = {f["path"] for f in files}
        for path in r2.get("stdout", "").splitlines():
            path = path.strip()
            if path and path not in existing:
                files.append({"path": path, "status": "A", "additions": 0, "deletions": 0, "binary": False})
    return files


def _is_safe_relative_path(path: str) -> bool:
    """校验 file 参数：只允许仓库内相对路径，禁止绝对路径和 .. 穿越。"""
    if not path:
        return False
    if os.path.isabs(path):
        return False
    # 归一化后仍在仓库内（不含 ..）
    norm = os.path.normpath(path)
    if norm.startswith("..") or os.path.isabs(norm):
        return False
    return True


def register_diff_routes(router: APIRouter, db=None):

    @router.get("/cannbot/workflow-v2/sessions/{session_id}/diff")
    async def get_session_diff(session_id: str, file: str = None):
        """文件改动 diff。

        - 默认（无 file）：返回改动文件列表 {baseline, files:[{path,status,additions,deletions,binary}]}
        - 带 ?file=path：返回单文件 unified patch {file, patch}
        """
        if not db:
            return {"error": "数据库未连接", "files": []}
        session = await db.get_workflow_sim_v2_session(session_id)
        if not session:
            return {"error": "会话不存在", "files": []}
        work_dir = session.get("work_dir") or ""
        if not work_dir or not os.path.isdir(os.path.join(work_dir, ".git")):
            return {"error": "work_dir 不是 git 仓库", "files": []}

        # 基线：优先用仿真启动时拍的 diff_baseline（最精确）；没有则用 work_dir 当前 HEAD
        # （假设每次开发都从最新 commit 之后开始，HEAD 即天然基线；也覆盖老仿真无快照的情况）
        baseline = session.get("diff_baseline")
        if not baseline:
            try:
                r = await _run_git("rev-parse", "HEAD", cwd=work_dir)
                if r.get("returncode") == 0 and r.get("stdout", "").strip():
                    baseline = r["stdout"].strip()
            except Exception:
                pass
        if not baseline:
            return {"error": "无法确定基线（work_dir 为空 git 仓库）", "files": []}

        try:
            if file:
                if not _is_safe_relative_path(file):
                    return {"error": "非法文件路径", "file": file, "patch": ""}
                # 先按已跟踪文件 diff；若为空，可能是 untracked 新文件，用 --no-index 生成整文件 patch
                r = await _run_git("diff", baseline, "--", file, cwd=work_dir)
                patch = r.get("stdout", "") if r.get("returncode") == 0 else ""
                if not patch:
                    full = os.path.join(work_dir, file)
                    if os.path.isfile(full):
                        # untracked 或 baseline 中不存在的文件：生成"全新增"patch
                        r2 = await _run_git("diff", "--no-index", "/dev/null", full, cwd=work_dir)
                        # --no-index 非 0 返回码是正常的（有差异时 returncode=1）
                        patch = r2.get("stdout", "") if r2.get("stdout") else ""
                return {"file": file, "patch": patch}
            else:
                files = await _list_changed_files(baseline, work_dir)
                return {"baseline": baseline, "files": files}
        except Exception as e:
            return {"error": f"git diff 异常: {e}", "files": []}
