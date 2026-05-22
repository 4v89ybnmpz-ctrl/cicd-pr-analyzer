"""
Git 仓库服务模块
支持 bare clone + git log 数据提取
"""
import asyncio
import os
import json
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

logger = logging.getLogger(__name__)

REPOS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "repos")


def _repo_path(owner: str, repo: str) -> str:
    return os.path.join(REPOS_DIR, owner, f"{repo}.git")


class GitRepoService:
    """Git 仓库克隆和日志提取服务"""

    def __init__(self, github_token: str = None):
        self.github_token = github_token
        os.makedirs(REPOS_DIR, exist_ok=True)
        logger.info(f"GitRepoService 初始化, repos 目录: {REPOS_DIR}")

    def _clone_url(self, owner: str, repo: str) -> str:
        if self.github_token:
            return f"https://{self.github_token}@github.com/{owner}/{repo}.git"
        return f"https://github.com/{owner}/{repo}.git"

    async def clone_bare(self, owner: str, repo: str) -> Dict[str, Any]:
        """bare clone 仓库到 data/repos/{owner}/{repo}.git"""
        dest = _repo_path(owner, repo)
        if os.path.exists(dest):
            return {"path": dest, "status": "already_exists", "owner": owner, "repo": repo}

        os.makedirs(os.path.dirname(dest), exist_ok=True)
        url = self._clone_url(owner, repo)
        cmd = ["git", "clone", "--bare", url, dest]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            err_msg = stderr.decode("utf-8", errors="replace").strip()
            logger.error(f"clone 失败: {owner}/{repo}: {err_msg}")
            return {"path": dest, "status": "error", "error": err_msg, "owner": owner, "repo": repo}

        logger.info(f"clone 完成: {owner}/{repo} -> {dest}")
        return {"path": dest, "status": "cloned", "owner": owner, "repo": repo}

    async def fetch_update(self, owner: str, repo: str) -> Dict[str, Any]:
        """对已有的 bare 仓库执行 git fetch 更新"""
        dest = _repo_path(owner, repo)
        if not os.path.exists(dest):
            return {"status": "not_found", "error": "仓库未克隆"}

        cmd = ["git", "fetch", "--all"]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=dest,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            err_msg = stderr.decode("utf-8", errors="replace").strip()
            return {"status": "error", "error": err_msg}

        return {"status": "updated"}

    async def extract_git_log(self, owner: str, repo: str, max_count: int = 0) -> Dict[str, Any]:
        """
        从 bare 仓库提取 git log 数据
        包含基础提交信息 + 每次提交的文件变更详情
        """
        dest = _repo_path(owner, repo)
        if not os.path.exists(dest):
            return {"error": "仓库未克隆，请先执行 clone"}

        log_format = json.dumps({
            "hash": "%H",
            "abbrev_hash": "%h",
            "author_name": "%an",
            "author_email": "%ae",
            "author_date": "%aI",
            "committer_name": "%cn",
            "committer_email": "%ce",
            "committer_date": "%cI",
            "subject": "%s",
            "body": "%b",
            "parents": "%P",
        }, separators=(',', ':'))

        sep = "---COMMIT_DELIMITER---"
        cmd = [
            "git", "log",
            f"--format={log_format}{sep}",
            "--numstat",
            "--date=iso-strict",
        ]
        if max_count > 0:
            cmd.append(f"--max-count={max_count}")

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=dest,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            err_msg = stderr.decode("utf-8", errors="replace").strip()
            logger.error(f"git log 失败: {owner}/{repo}: {err_msg}")
            return {"error": f"git log 执行失败: {err_msg}"}

        raw = stdout.decode("utf-8", errors="replace")
        commits = self._parse_git_log(raw)

        stats_cmd = ["git", "log", "--all", "--format=%H", "--shortstat"]
        stats_proc = await asyncio.create_subprocess_exec(
            *stats_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=dest,
        )
        stats_out, _ = await stats_proc.communicate()

        branch_proc = await asyncio.create_subprocess_exec(
            "git", "branch", "-r", "--format=%(refname:short)",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=dest,
        )
        branch_out, _ = await branch_proc.communicate()
        branches = [b.strip() for b in branch_out.decode("utf-8", errors="replace").splitlines() if b.strip()]

        tag_proc = await asyncio.create_subprocess_exec(
            "git", "tag",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=dest,
        )
        tag_out, _ = await tag_proc.communicate()
        tags = [t.strip() for t in tag_out.decode("utf-8", errors="replace").splitlines() if t.strip()]

        contributors = {}
        for c in commits:
            name = c.get("author_name", "unknown")
            if name not in contributors:
                contributors[name] = {"commits": 0, "additions": 0, "deletions": 0}
            contributors[name]["commits"] += 1
            for f in c.get("files", []):
                contributors[name]["additions"] += f.get("additions", 0) or 0
                contributors[name]["deletions"] += f.get("deletions", 0) or 0

        logger.info(f"git log 提取完成: {owner}/{repo}, {len(commits)} commits, {len(branches)} branches, {len(tags)} tags")

        return {
            "owner": owner,
            "repo": repo,
            "total_commits": len(commits),
            "commits": commits,
            "branches": branches,
            "tags": tags,
            "contributors": [{"name": k, **v} for k, v in sorted(contributors.items(), key=lambda x: x[1]["commits"], reverse=True)],
            "extracted_at": datetime.now().isoformat(),
        }

    def _parse_git_log(self, raw: str) -> List[Dict[str, Any]]:
        sep = "---COMMIT_DELIMITER---"
        parts = raw.split(sep)
        commits = []
        for part in parts:
            part = part.strip()
            if not part:
                continue
            lines = part.splitlines()
            if not lines:
                continue

            try:
                commit = json.loads(lines[0])
            except (json.JSONDecodeError, IndexError):
                continue

            files = []
            for line in lines[1:]:
                line = line.strip()
                if not line or line.startswith("---"):
                    continue
                parts = line.split("\t")
                if len(parts) == 3:
                    try:
                        add = int(parts[0]) if parts[0] != "-" else 0
                        delete = int(parts[1]) if parts[1] != "-" else 0
                        files.append({
                            "file": parts[2],
                            "additions": add,
                            "deletions": delete,
                        })
                    except ValueError:
                        pass

            commit["files"] = files
            commit["files_changed"] = len(files)
            commit["total_additions"] = sum(f["additions"] for f in files)
            commit["total_deletions"] = sum(f["deletions"] for f in files)
            commits.append(commit)

        return commits

    def is_cloned(self, owner: str, repo: str) -> bool:
        return os.path.exists(_repo_path(owner, repo))

    def get_repo_size_mb(self, owner: str, repo: str) -> Optional[float]:
        dest = _repo_path(owner, repo)
        if not os.path.exists(dest):
            return None
        total = 0
        for dirpath, dirnames, filenames in os.walk(dest):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                try:
                    total += os.path.getsize(fp)
                except OSError:
                    pass
        return round(total / (1024 * 1024), 2)

    async def delete_repo(self, owner: str, repo: str) -> bool:
        dest = _repo_path(owner, repo)
        if not os.path.exists(dest):
            return False
        cmd = ["rm", "-rf", dest]
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        await proc.communicate()
        logger.info(f"已删除仓库: {owner}/{repo}")
        return True
