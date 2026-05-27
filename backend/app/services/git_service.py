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

    def __init__(self, github_token: str = None, proxy: str = None):
        self.github_token = github_token
        self.proxy = proxy
        os.makedirs(REPOS_DIR, exist_ok=True)
        # 构建带代理的环境变量（clone/fetch 需要网络）
        self._net_env = None
        if proxy:
            import copy
            self._net_env = copy.copy(os.environ)
            self._net_env["http_proxy"] = proxy
            self._net_env["https_proxy"] = proxy
            self._net_env["HTTP_PROXY"] = proxy
            self._net_env["HTTPS_PROXY"] = proxy
            logger.info(f"GitRepoService 代理已配置: {proxy}")
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
            env=self._net_env,
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
            env=self._net_env,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            err_msg = stderr.decode("utf-8", errors="replace").strip()
            return {"status": "error", "error": err_msg}

        return {"status": "updated"}

    async def extract_git_log(self, owner: str, repo: str, max_count: int = 0,
                              branch: str = None) -> Dict[str, Any]:
        """
        从 bare 仓库提取 git log 数据
        branch: 指定分支名（如 origin/main），"all" 表示所有分支，None 表示默认分支
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

        # 分支参数：指定分支、--all 或默认
        extract_branches = []
        if branch == "all" or branch == "--all":
            cmd.append("--all")
        elif branch:
            cmd.append(branch)

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

        # 获取所有远程分支列表
        branch_proc = await asyncio.create_subprocess_exec(
            "git", "branch", "-r", "--format=%(refname:short)",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=dest,
        )
        branch_out, _ = await branch_proc.communicate()
        all_branches = [b.strip() for b in branch_out.decode("utf-8", errors="replace").splitlines() if b.strip()]

        # 为 commits 标注分支来源
        if branch and branch not in ("all", "--all"):
            # 指定单个分支
            short_name = branch.replace("origin/", "") if branch.startswith("origin/") else branch
            for c in commits:
                c["branches"] = [short_name]
            extract_branches = [short_name]
        else:
            # --all 或默认：用 git branch --contains 标注每个 commit
            extract_branches = all_branches
            await self._annotate_commit_branches(commits, all_branches, dest)

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

        logger.info(f"git log 提取完成: {owner}/{repo}, {len(commits)} commits, {len(all_branches)} branches, {len(tags)} tags, branch={branch}")

        return {
            "owner": owner,
            "repo": repo,
            "total_commits": len(commits),
            "commits": commits,
            "branches": all_branches,
            "tags": tags,
            "extract_branch": branch or "default",
            "contributors": [{"name": k, **v} for k, v in sorted(contributors.items(), key=lambda x: x[1]["commits"], reverse=True)],
            "extracted_at": datetime.now().isoformat(),
        }

    async def _annotate_commit_branches(self, commits: list, branches: list, cwd: str):
        """为每个 commit 标注它属于哪些分支"""
        # 批量查询：对每个分支执行 git log --format=%H 获取该分支的 commit 集合
        commit_branches = {}  # hash -> set of branch names
        for br in branches:
            short_name = br.replace("origin/", "") if br.startswith("origin/") else br
            try:
                proc = await asyncio.create_subprocess_exec(
                    "git", "log", br, "--format=%H",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=cwd,
                )
                out, _ = await proc.communicate()
                if proc.returncode == 0:
                    for line in out.decode("utf-8", errors="replace").splitlines():
                        h = line.strip()
                        if h:
                            commit_branches.setdefault(h, set()).add(short_name)
            except Exception:
                pass

        for c in commits:
            c["branches"] = list(commit_branches.get(c.get("hash", ""), []))

    @staticmethod
    def _extract_tz(iso_str: str) -> str:
        if not iso_str:
            return ""
        import re
        match = re.search(r'([+-]\d{2}:\d{2})$', iso_str)
        return match.group(1) if match else ""

    @staticmethod
    def _to_utc_minute(iso_str: str) -> str:
        if not iso_str:
            return ""
        try:
            from datetime import timezone
            dt = datetime.fromisoformat(iso_str)
            utc_dt = dt.astimezone(timezone.utc)
            return utc_dt.strftime("%Y-%m-%dT%H:%M")
        except Exception:
            return iso_str[:16] if len(iso_str) >= 16 else iso_str

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

            json_idx = None
            for i, line in enumerate(lines):
                stripped = line.strip()
                if stripped.startswith("{"):
                    try:
                        commit = json.loads(stripped)
                        json_idx = i
                        break
                    except (json.JSONDecodeError, ValueError):
                        continue
            if json_idx is None:
                continue

            commit["author_date_utc"] = self._to_utc_minute(commit.get("author_date"))
            commit["author_tz"] = self._extract_tz(commit.get("author_date"))
            commit["committer_date_utc"] = self._to_utc_minute(commit.get("committer_date"))
            commit["committer_tz"] = self._extract_tz(commit.get("committer_date"))

            files = []
            for line in lines[json_idx + 1:]:
                line = line.strip()
                if not line or line.startswith("---"):
                    continue
                file_parts = line.split("\t")
                if len(file_parts) == 3:
                    try:
                        add = int(file_parts[0]) if file_parts[0] != "-" else 0
                        delete = int(file_parts[1]) if file_parts[1] != "-" else 0
                        files.append({
                            "file": file_parts[2],
                            "additions": add,
                            "deletions": delete,
                        })
                    except ValueError:
                        pass

            # numstat 行可能出现在 JSON 之前（git log --numstat 输出格式）
            for line in lines[:json_idx]:
                line = line.strip()
                if not line or line.startswith("---"):
                    continue
                file_parts = line.split("\t")
                if len(file_parts) == 3:
                    try:
                        add = int(file_parts[0]) if file_parts[0] != "-" else 0
                        delete = int(file_parts[1]) if file_parts[1] != "-" else 0
                        files.append({
                            "file": file_parts[2],
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
