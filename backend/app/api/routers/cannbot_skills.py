"""
CANNBot Skills 路由
扫描 external/cannbot-skills 项目，提供技能列表、详情、评估、统计和安装场景接口
"""
from fastapi import APIRouter, HTTPException
from pathlib import Path
from datetime import datetime, timezone
import asyncio
import logging
import os
import re

logger = logging.getLogger(__name__)

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
CANNBOT_DIR = PROJECT_ROOT / "external" / "cannbot-skills"
REPO_URL = "https://gitcode.com/cann/cannbot-skills.git"

# 技能分类目录（扫描用）
SKILL_CATEGORIES = {
    "ops": "算子开发",
    "model": "模型推理",
    "infra": "基础设施",
    "graph": "计算图",
    "ops-lab": "实验算子",
}

# 触发关键词（源自 tests/lib/rules.yaml skill_keywords）
TRIGGER_KEYWORDS = [
    "ascend", "算子", "kernel", "tiling", "调试", "debug", "测试",
    "ut", "性能", "perf", "精度", "precision", "npu", "api", "aclnn",
    "运行时", "runtime", "推理", "infer", "模型", "并行", "融合",
    "cann", "昇腾", "triton", "pypto",
]

# 评分等级
GRADE_COLORS = {"A": "#52c41a", "B": "#1890ff", "C": "#faad14", "D": "#fa541c", "F": "#ff4d4f"}


def _to_grade(score: int) -> str:
    if score >= 90: return "A"
    if score >= 75: return "B"
    if score >= 60: return "C"
    if score >= 40: return "D"
    return "F"


def _fmt_size(size_bytes: int) -> str:
    if size_bytes < 1024: return f"{size_bytes}B"
    if size_bytes < 1024 * 1024: return f"{size_bytes / 1024:.0f}K"
    return f"{size_bytes / (1024 * 1024):.1f}M"


def _parse_skill_md(skill_md_path: Path) -> dict:
    """解析 SKILL.md 的 YAML frontmatter，返回 name/description/frontmatter/body"""
    text = skill_md_path.read_text(encoding="utf-8", errors="replace")
    name = ""
    description = ""
    frontmatter = {}
    body = text

    if text.startswith("---"):
        end = text.find("---", 3)
        if end > 0:
            fm_text = text[3:end].strip()
            body = text[end + 3:].strip()
            for line in fm_text.split("\n"):
                if ":" in line:
                    k, v = line.split(":", 1)
                    frontmatter[k.strip()] = v.strip()
                    if k.strip() == "name":
                        name = v.strip()
                    elif k.strip() == "description":
                        description = v.strip()

    if not name:
        name = skill_md_path.parent.name
    if not description:
        for line in body.split("\n"):
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                description = stripped[:200]
                break

    return {"name": name, "description": description, "frontmatter": frontmatter, "body": body}


def _scan_skills() -> list:
    """扫描所有技能目录"""
    skills = []
    if not CANNBOT_DIR.exists():
        return skills

    for cat_key, cat_label in SKILL_CATEGORIES.items():
        cat_dir = CANNBOT_DIR / cat_key
        if not cat_dir.is_dir():
            continue
        for skill_dir in sorted(cat_dir.iterdir()):
            if not skill_dir.is_dir():
                continue
            skill_md = skill_dir / "SKILL.md"
            readme_md = skill_dir / "README.md"
            info = {
                "id": f"{cat_key}/{skill_dir.name}",
                "category": cat_key,
                "categoryLabel": cat_label,
                "name": skill_dir.name,
                "description": "",
                "hasSkillMd": skill_md.exists(),
                "hasReadme": readme_md.exists(),
            }
            if skill_md.exists():
                parsed = _parse_skill_md(skill_md)
                info["name"] = parsed["name"]
                info["description"] = parsed["description"]
            elif readme_md.exists():
                text = readme_md.read_text(encoding="utf-8", errors="replace")
                for line in text.split("\n"):
                    stripped = line.strip()
                    if stripped.startswith("#"):
                        info["name"] = stripped.lstrip("# ").strip()
                        break
                info["description"] = text[:200].strip()
            skills.append(info)
    return skills


def _safe_resolve(base: Path, user_path: str) -> Path:
    """安全路径解析，防止路径遍历"""
    resolved = (base / user_path).resolve()
    if not str(resolved).startswith(str(base.resolve())):
        raise ValueError("非法路径")
    return resolved


async def _run_git(*args, cwd: Path = None) -> dict:
    """执行 git 命令"""
    cmd = ["git"] + list(args)
    proc = await asyncio.create_subprocess_exec(
        *cmd, cwd=str(cwd) if cwd else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
    return {
        "returncode": proc.returncode,
        "stdout": stdout.decode("utf-8", errors="replace").strip(),
        "stderr": stderr.decode("utf-8", errors="replace").strip(),
    }


# ==================== 评估函数 ====================

def _score_doc(has_skill_md: bool, frontmatter: dict) -> tuple:
    """文档完整度评分 (0-100)"""
    score = 0
    details = []
    if has_skill_md:
        score += 40
        details.append("SKILL.md 存在")
    else:
        details.append("缺少 SKILL.md")
    if frontmatter.get("name"):
        score += 20
        details.append("name 字段完整")
    if frontmatter.get("description"):
        score += 20
        details.append("description 字段完整")
    desc_len = len(frontmatter.get("description", ""))
    if desc_len > 20:
        score += 10
    if desc_len <= 1024:
        score += 10
    return min(score, 100), "；".join(details)


def _score_content(description: str, body: str) -> tuple:
    """内容质量评分 (0-100)"""
    score = 50
    details = []
    combined = (description + " " + body).lower()
    hits = sum(1 for kw in TRIGGER_KEYWORDS if kw.lower() in combined)
    keyword_score = min(hits * 5, 30)
    score += keyword_score
    if hits > 0:
        details.append(f"含 {hits} 个触发关键词")
    if "```" in body:
        score += 10
        details.append("有代码示例")
    if re.search(r"^\d+\.\s", body, re.MULTILINE):
        score += 10
        details.append("有操作步骤")
    return min(score, 100), "；".join(details) if details else "内容较简单"


def _score_references(skill_dir: Path) -> tuple:
    """参考资料评分 (0-100)"""
    ref_dir = skill_dir / "references"
    if not ref_dir.exists():
        return 0, "无 references 目录"
    files = [f for f in ref_dir.iterdir() if f.is_file()]
    count = len(files)
    if count == 0:
        return 10, "references 目录为空"
    if count >= 5:
        return 100, f"references/ 含 {count} 个参考文件"
    return 40 + count * 12, f"references/ 含 {count} 个参考文件"


def _score_activity(last_date: str) -> tuple:
    """活跃度评分 (0-100)，last_date 格式 YYYY-MM-DD"""
    if not last_date:
        return 0, "无提交记录"
    try:
        d = datetime.strptime(last_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        days = (datetime.now(timezone.utc) - d).days
    except Exception:
        return 0, "日期解析失败"
    if days <= 7:
        score = 100
    elif days <= 14:
        score = 80
    elif days <= 30:
        score = 60
    elif days <= 60:
        score = 40
    else:
        score = 20
    return score, f"最后更新 {days} 天前"


def _score_capability(skill_dir: Path, frontmatter: dict, body: str) -> tuple:
    """实际使用能力评分 (0-100)"""
    score = 0
    details = []
    name = frontmatter.get("name", skill_dir.name)

    # 1. 有无可执行脚本 (30分)
    scripts_dir = skill_dir / "scripts"
    if scripts_dir.is_dir():
        scripts = [f for f in scripts_dir.iterdir() if f.is_file() and not f.name.startswith(".")]
        if scripts:
            score += 30
            details.append(f"含 {len(scripts)} 个可执行脚本")
        else:
            score += 5
            details.append("scripts/ 目录为空")
    else:
        details.append("无 scripts 目录")

    # 2. 有无工作流/场景定义 (20分)
    has_workflow = False
    for subdir in ["workflows", "scenarios", "templates"]:
        d = skill_dir / subdir
        if d.is_dir() and any(f.is_file() for f in d.iterdir()):
            has_workflow = True
            break
    if has_workflow:
        score += 20
        details.append("有工作流/场景定义")
    else:
        details.append("无工作流定义")

    # 3. 触发条件是否清晰 (20分) — description 中是否包含触发条件说明
    desc = frontmatter.get("description", "")
    trigger_phrases = ["use when", "when user", "当用户", "触发条件", "适用场景", "使用场景", "用于", "支持"]
    has_trigger = any(p in (desc + body[:500]).lower() for p in trigger_phrases)
    if has_trigger:
        score += 20
        details.append("触发条件清晰")
    else:
        score += 5
        details.append("触发条件不明确")

    # 4. 有无真实代码示例 (15分)
    code_blocks = body.count("```")
    if code_blocks >= 6:
        score += 15
        details.append(f"含 {code_blocks // 2} 个代码示例")
    elif code_blocks >= 2:
        score += 8
        details.append(f"含少量代码示例")
    else:
        details.append("无代码示例")

    # 5. 有无交互式指令/步骤 (15分) — 多步骤操作说明
    steps = len(re.findall(r"^\d+\.\s", body, re.MULTILINE))
    if steps >= 5:
        score += 15
        details.append(f"含 {steps} 步操作流程")
    elif steps >= 2:
        score += 8
        details.append("有基本操作步骤")
    else:
        details.append("无结构化操作步骤")

    return min(score, 100), "；".join(details)


async def _get_dir_last_dates() -> dict:
    """批量获取每个 Skill 目录的最后 commit 日期"""
    if not CANNBOT_DIR.exists():
        return {}
    result = await _run_git(
        "log", "--format=%ai %s", "--name-only", "--diff-filter=AMDR",
        cwd=CANNBOT_DIR
    )
    dates = {}
    if result["returncode"] != 0:
        return dates
    current_date = ""
    for line in result["stdout"].split("\n"):
        line = line.strip()
        # 日期行格式：2026-05-27 19:41:54 +0800 xxx
        if re.match(r"^\d{4}-\d{2}-\d{2}", line):
            current_date = line[:10]
        elif line and current_date:
            # 文件路径，提取顶层分类/技能名
            parts = line.split("/")
            if len(parts) >= 2 and parts[0] in SKILL_CATEGORIES:
                key = f"{parts[0]}/{parts[1]}"
                if key not in dates:
                    dates[key] = current_date
    return dates


def _parse_changelog() -> list:
    """解析 CHANGELOG.md"""
    changelog_path = CANNBOT_DIR / "CHANGELOG.md"
    if not changelog_path.exists():
        return []
    text = changelog_path.read_text(encoding="utf-8", errors="replace")
    entries = []
    current = None
    current_section = None
    for line in text.split("\n"):
        # 日期标题 ### 【2026-05-27】
        m = re.match(r"###\s*【(\d{4}-\d{2}-\d{2})】", line)
        if m:
            if current:
                entries.append(current)
            current = {"date": m.group(1), "features": [], "enhancements": [], "fixes": [], "other": [], "total": 0}
            current_section = None
            continue
        if not current:
            continue
        # 分类标题
        if "新特性" in line or "New Feature" in line:
            current_section = "features"
        elif "特性增强" in line or "Enhancement" in line:
            current_section = "enhancements"
        elif "问题修复" in line or "Bug Fix" in line:
            current_section = "fixes"
        elif line.strip().startswith("- ") and current_section:
            item = line.strip()[2:]
            current[current_section].append(item)
            current["total"] += 1
    if current:
        entries.append(current)
    return entries


def _collect_install_artifacts(config_dir: str, project_dir: str, tool: str) -> dict:
    """安装后检测实际产物"""
    config_path = Path(config_dir)
    result = {
        "configDir": config_dir,
        "exists": config_path.is_dir(),
        "skills": [],
        "agents": [],
        "configFiles": [],
        "manifest": None,
    }
    if not config_path.is_dir():
        return result

    # 检测 skills/ 目录
    skills_dir = config_path / "skills"
    if skills_dir.is_dir():
        for item in sorted(skills_dir.iterdir()):
            if item.is_symlink() or item.is_dir():
                target = os.readlink(str(item)) if item.is_symlink() else ""
                result["skills"].append({
                    "name": item.name,
                    "isSymlink": item.is_symlink(),
                    "target": target,
                })

    # 检测 agents/ 目录
    agents_dir = config_path / "agents"
    if agents_dir.is_dir():
        for item in sorted(agents_dir.iterdir()):
            if item.is_symlink() or item.is_dir() or (item.is_file() and item.suffix == ".md"):
                target = os.readlink(str(item)) if item.is_symlink() else ""
                result["agents"].append({
                    "name": item.stem if item.suffix == ".md" else item.name,
                    "isSymlink": item.is_symlink(),
                    "target": target,
                })

    # 检测配置文件（项目根目录或 config 目录）
    config_names = ["CLAUDE.md", "AGENTS.md"]
    search_dirs = [Path(project_dir), config_path]
    for fname in config_names:
        for d in search_dirs:
            fpath = d / fname
            if fpath.exists():
                result["configFiles"].append({"name": fname, "path": str(fpath)})
                break

    # 检测 manifest
    manifest_path = config_path / "cannbot-manifest.json"
    if manifest_path.exists():
        try:
            import json
            result["manifest"] = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    return result


def _scan_scenarios() -> list:

    """扫描安装场景（plugins）"""
    scenarios = []
    for plugin_type, plugin_dir in [("official", "plugins-official"), ("community", "plugins-community")]:
        base = CANNBOT_DIR / plugin_dir
        if not base.is_dir():
            continue
        for d in sorted(base.iterdir()):
            if not d.is_dir():
                continue
            # 解析 AGENTS.md 获取名称和描述
            agents_md = d / "AGENTS.md"
            name = d.name
            description = ""
            agents = []
            if agents_md.exists():
                text = agents_md.read_text(encoding="utf-8", errors="replace")
                # 提取 frontmatter 中的 description
                if text.startswith("---"):
                    end = text.find("---", 3)
                    if end > 0:
                        fm = text[3:end]
                        for line in fm.split("\n"):
                            if line.startswith("description:"):
                                description = line.split(":", 1)[1].strip()
                # 提取第一个标题
                for line in text.split("\n"):
                    if line.startswith("# ") and not name:
                        name = line.lstrip("# ").strip()
                        break
            # 扫描 agents 子目录
            agents_dir = d / "agents"
            if agents_dir.is_dir():
                for f in agents_dir.iterdir():
                    if f.is_file() and f.suffix == ".md":
                        agents.append(f.stem)
            # 判断安装命令
            init_sh = d / "init.sh"
            install_sh = d / "install.sh"
            if install_sh.exists():
                install_cmd = f"bash install.sh project <tool>"
            elif init_sh.exists():
                install_cmd = f"bash init.sh project <tool>"
            else:
                install_cmd = ""
            # 统计文件数和大小
            file_count = 0
            total_size = 0
            for f in d.rglob("*"):
                if f.is_file() and not any(p.startswith(".") for p in f.relative_to(d).parts):
                    file_count += 1
                    total_size += f.stat().st_size
            scenarios.append({
                "id": d.name,
                "name": name,
                "type": plugin_type,
                "description": description[:200] if description else "",
                "installCmd": install_cmd,
                "hasInit": init_sh.exists() or install_sh.exists(),
                "agents": agents,
                "path": f"{plugin_dir}/{d.name}",
                "fileCount": file_count,
                "size": _fmt_size(total_size),
            })
    return scenarios


# ==================== 路由注册 ====================

def register_cannbot_routes(router: APIRouter):
    """注册 CANNBot Skills 路由"""

    @router.get("/cannbot/status")
    async def get_cannbot_status():
        """检查 cannbot-skills clone 状态"""
        if not CANNBOT_DIR.exists():
            return {"cloned": False, "path": str(CANNBOT_DIR)}

        commit = ""
        commit_date = ""
        branch = ""
        try:
            result = await _run_git("log", "-1", "--format=%H %ai", cwd=CANNBOT_DIR)
            if result["returncode"] == 0:
                parts = result["stdout"].split(" ", 2)
                commit = parts[0] if len(parts) > 0 else ""
                commit_date = parts[1] + " " + parts[2] if len(parts) > 2 else ""
            result = await _run_git("rev-parse", "--abbrev-ref", "HEAD", cwd=CANNBOT_DIR)
            if result["returncode"] == 0:
                branch = result["stdout"]
        except Exception:
            pass

        return {
            "cloned": True,
            "path": str(CANNBOT_DIR),
            "branch": branch,
            "commit": commit[:12],
            "commitDate": commit_date,
        }

    @router.post("/cannbot/clone")
    async def clone_cannbot_skills():
        """克隆 cannbot-skills 仓库"""
        if CANNBOT_DIR.exists():
            return {"status": "already_exists", "path": str(CANNBOT_DIR)}

        CANNBOT_DIR.parent.mkdir(parents=True, exist_ok=True)
        result = await _run_git("clone", REPO_URL, str(CANNBOT_DIR))
        if result["returncode"] != 0:
            raise HTTPException(status_code=500, detail=f"Clone 失败: {result['stderr']}")
        return {"status": "cloned", "path": str(CANNBOT_DIR)}

    @router.post("/cannbot/update")
    async def update_cannbot_skills():
        """更新 cannbot-skills 仓库"""
        if not CANNBOT_DIR.exists():
            raise HTTPException(status_code=404, detail="仓库尚未 clone")
        result = await _run_git("pull", "--ff-only", cwd=CANNBOT_DIR)
        if result["returncode"] != 0:
            raise HTTPException(status_code=500, detail=f"更新失败: {result['stderr']}")
        return {"status": "updated", "output": result["stdout"]}

    @router.get("/cannbot/skills")
    async def get_cannbot_skills():
        """获取技能列表"""
        if not CANNBOT_DIR.exists():
            return {"cloned": False, "skills": [], "categories": SKILL_CATEGORIES}
        skills = _scan_skills()
        return {
            "cloned": True,
            "skills": skills,
            "categories": SKILL_CATEGORIES,
            "total": len(skills),
        }

    @router.get("/cannbot/stats")
    async def get_cannbot_stats():
        """项目统计概览"""
        if not CANNBOT_DIR.exists():
            raise HTTPException(status_code=404, detail="仓库尚未 clone")

        skills = _scan_skills()
        # 分类统计
        cat_counts = {}
        for s in skills:
            cat_counts[s["category"]] = cat_counts.get(s["category"], 0) + 1
        # 插件统计
        scenarios = _scan_scenarios()
        # Agent 统计
        agent_count = 0
        for s in scenarios:
            agent_count += len(s["agents"])
        # 文件统计
        total_files = 0
        total_size = 0
        for f in CANNBOT_DIR.rglob("*"):
            if f.is_file() and not any(p.startswith(".") for p in f.relative_to(CANNBOT_DIR).parts):
                total_files += 1
                total_size += f.stat().st_size
        # Git 统计
        commit_count = 0
        latest_commit = ""
        first_commit = ""
        try:
            result = await _run_git("rev-list", "--count", "HEAD", cwd=CANNBOT_DIR)
            if result["returncode"] == 0:
                commit_count = int(result["stdout"])
            result = await _run_git("log", "-1", "--format=%ai", cwd=CANNBOT_DIR)
            if result["returncode"] == 0:
                latest_commit = result["stdout"][:10]
            result = await _run_git("log", "--reverse", "-1", "--format=%ai", cwd=CANNBOT_DIR)
            if result["returncode"] == 0:
                first_commit = result["stdout"][:10]
        except Exception:
            pass

        return {
            "totalSkills": len(skills),
            "categories": cat_counts,
            "totalPlugins": len(scenarios),
            "totalAgents": agent_count,
            "totalFiles": total_files,
            "repoSize": _fmt_size(total_size),
            "commitCount": commit_count,
            "latestCommit": latest_commit,
            "firstCommit": first_commit,
        }

    @router.get("/cannbot/evaluation")
    async def get_cannbot_evaluation():
        """技能质量评估"""
        if not CANNBOT_DIR.exists():
            raise HTTPException(status_code=404, detail="仓库尚未 clone")

        # 获取每个目录的最后提交日期
        last_dates = await _get_dir_last_dates()

        results = []
        grade_dist = {"A": 0, "B": 0, "C": 0, "D": 0, "F": 0}
        total_score = 0

        for cat_key, cat_label in SKILL_CATEGORIES.items():
            cat_dir = CANNBOT_DIR / cat_key
            if not cat_dir.is_dir():
                continue
            for skill_dir in sorted(cat_dir.iterdir()):
                if not skill_dir.is_dir():
                    continue
                skill_id = f"{cat_key}/{skill_dir.name}"
                skill_md = skill_dir / "SKILL.md"
                has_skill_md = skill_md.exists()
                frontmatter = {}
                description = ""
                body = ""
                name = skill_dir.name

                if has_skill_md:
                    parsed = _parse_skill_md(skill_md)
                    frontmatter = parsed["frontmatter"]
                    description = parsed["description"]
                    body = parsed["body"]
                    name = parsed["name"]

                # 文件统计
                file_count = 0
                total_size = 0
                for f in skill_dir.rglob("*"):
                    if f.is_file() and not any(p.startswith(".") for p in f.relative_to(skill_dir).parts):
                        file_count += 1
                        total_size += f.stat().st_size

                # 五维评分
                doc_score, doc_detail = _score_doc(has_skill_md, frontmatter)
                content_score, content_detail = _score_content(description, body)
                ref_score, ref_detail = _score_references(skill_dir)
                last_date = last_dates.get(skill_id, "")
                act_score, act_detail = _score_activity(last_date)
                cap_score, cap_detail = _score_capability(skill_dir, frontmatter, body)

                # 加权总分（文档20% + 内容20% + 参考15% + 活跃15% + 能力30%）
                total = int(doc_score * 0.2 + content_score * 0.2 + ref_score * 0.15 + act_score * 0.15 + cap_score * 0.3)
                grade = _to_grade(total)
                grade_dist[grade] += 1
                total_score += total

                results.append({
                    "id": skill_id,
                    "name": name,
                    "category": cat_key,
                    "categoryLabel": cat_label,
                    "score": total,
                    "grade": grade,
                    "dimensions": {
                        "docCompleteness": {"score": doc_score, "detail": doc_detail},
                        "contentQuality": {"score": content_score, "detail": content_detail},
                        "references": {"score": ref_score, "detail": ref_detail},
                        "activity": {"score": act_score, "detail": act_detail},
                        "capability": {"score": cap_score, "detail": cap_detail},
                    },
                    "lastUpdated": last_date,
                    "fileCount": file_count,
                    "totalSize": _fmt_size(total_size),
                })

        count = len(results)
        return {
            "skills": results,
            "summary": {
                "avgScore": round(total_score / count, 1) if count else 0,
                "gradeDistribution": grade_dist,
                "totalSkills": count,
            },
            "checkedAt": datetime.now(timezone.utc).isoformat(),
        }

    @router.get("/cannbot/changelog")
    async def get_cannbot_changelog():
        """版本变更记录"""
        if not CANNBOT_DIR.exists():
            raise HTTPException(status_code=404, detail="仓库尚未 clone")

        entries = _parse_changelog()
        # 30天内的统计
        commit_count_30d = 0
        try:
            result = await _run_git(
                "log", "--oneline", "--since=30.days.ago", cwd=CANNBOT_DIR
            )
            if result["returncode"] == 0:
                commit_count_30d = len([l for l in result["stdout"].split("\n") if l.strip()])
        except Exception:
            pass

        active_days = len(set(e["date"] for e in entries))

        return {
            "entries": entries[:30],
            "commitCount30d": commit_count_30d,
            "activeDays30d": active_days,
        }

    @router.get("/cannbot/scenarios")
    async def get_cannbot_scenarios():
        """安装场景列表"""
        if not CANNBOT_DIR.exists():
            raise HTTPException(status_code=404, detail="仓库尚未 clone")
        scenarios = _scan_scenarios()
        return {"scenarios": scenarios, "total": len(scenarios)}

    @router.get("/cannbot/skills/{skill_path:path}")
    async def get_cannbot_skill_detail(skill_path: str):
        """获取技能详情（SKILL.md 或 README.md 内容）"""
        if not CANNBOT_DIR.exists():
            raise HTTPException(status_code=404, detail="仓库尚未 clone")

        try:
            skill_dir = _safe_resolve(CANNBOT_DIR, skill_path)
        except ValueError:
            raise HTTPException(status_code=400, detail="非法路径")

        if not skill_dir.is_dir():
            raise HTTPException(status_code=404, detail=f"技能目录不存在: {skill_path}")

        content = ""
        doc_file = None
        for fname in ["SKILL.md", "README.md"]:
            fpath = skill_dir / fname
            if fpath.exists():
                content = fpath.read_text(encoding="utf-8", errors="replace")
                doc_file = fname
                break

        files = []
        for item in sorted(skill_dir.rglob("*")):
            if item.is_file():
                rel = item.relative_to(skill_dir)
                if any(p.startswith(".") for p in rel.parts):
                    continue
                if item.stat().st_size > 100 * 1024:
                    continue
                files.append(str(rel))

        return {
            "id": skill_path,
            "name": skill_dir.name,
            "docFile": doc_file,
            "content": content,
            "files": files,
        }

    @router.get("/cannbot/skill-file/{file_path:path}")
    async def get_cannbot_skill_file(file_path: str):
        """读取技能目录下的指定文件"""
        if not CANNBOT_DIR.exists():
            raise HTTPException(status_code=404, detail="仓库尚未 clone")

        try:
            abs_path = _safe_resolve(CANNBOT_DIR, file_path)
        except ValueError:
            raise HTTPException(status_code=400, detail="非法路径")

        if not abs_path.is_file():
            raise HTTPException(status_code=404, detail="文件不存在")

        if abs_path.stat().st_size > 200 * 1024:
            raise HTTPException(status_code=400, detail="文件过大，请使用本地查看")

        return {
            "path": file_path,
            "content": abs_path.read_text(encoding="utf-8", errors="replace"),
        }

    @router.post("/cannbot/install-scenario")
    async def install_cannbot_scenario(request: dict):
        """执行场景安装脚本 init.sh/install.sh，安装到项目根目录"""
        if not CANNBOT_DIR.exists():
            raise HTTPException(status_code=404, detail="仓库尚未 clone")

        scenario_path = request.get("scenario_path", "")
        tool = request.get("tool", "claude")
        level = request.get("level", "project")
        install_path = request.get("install_path", str(PROJECT_ROOT))
        if not scenario_path:
            raise HTTPException(status_code=400, detail="缺少 scenario_path")

        scenario_dir = CANNBOT_DIR / scenario_path
        if not scenario_dir.is_dir():
            raise HTTPException(status_code=404, detail=f"场景目录不存在: {scenario_path}")

        # 检测安装脚本
        install_sh = scenario_dir / "install.sh"
        init_sh = scenario_dir / "init.sh"
        script = install_sh if install_sh.exists() else init_sh if init_sh.exists() else None
        if not script:
            raise HTTPException(status_code=404, detail="该场景没有安装脚本")

        # 确定安装目标目录（项目级 = PROJECT_ROOT，全局级 = HOME）
        if level == "global":
            target_dir = str(Path.home())
        else:
            target_dir = str(PROJECT_ROOT)

        # 检测脚本是否支持路径参数（有些脚本有 Unknown argument 兜底会报错）
        script_text = script.read_text(encoding="utf-8", errors="replace")
        supports_path_arg = "INSTALL_PATH" in script_text and "Unknown argument" not in script_text

        # 构建命令
        if supports_path_arg:
            # 支持 install_path 参数的脚本：bash init.sh [level] [tool] [path]
            cmd = ["bash", str(script), level, tool, target_dir]
            cwd_dir = str(scenario_dir)
        else:
            # 不支持路径参数的脚本：只传 level + tool，通过 cwd 控制安装位置
            cmd = ["bash", str(script), level, tool]
            # project 级别：cwd 设为目标项目目录（脚本会用 $PWD 作为安装基础）
            cwd_dir = target_dir
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=cwd_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
            output = stdout.decode("utf-8", errors="replace")
            errors = stderr.decode("utf-8", errors="replace")

            # 解析安装后的实际路径
            tool_config_dirs = {
                "claude": [".claude"],
                "cursor": [".cursor"],
                "trae": [".trae-cn", ".marscode", ".trae", ".traecli"],
                "opencode": [".opencode"],
            }
            config_dir_name = tool_config_dirs.get(tool, [f".{tool}"])[0]
            actual_config_dir = str(Path(target_dir) / config_dir_name)

            # 检测安装产物
            artifacts = _collect_install_artifacts(actual_config_dir, target_dir, tool)

            return {
                "success": proc.returncode == 0,
                "returnCode": proc.returncode,
                "output": output,
                "errors": errors,
                "scenarioPath": scenario_path,
                "tool": tool,
                "level": level,
                "installDir": actual_config_dir,
                "artifacts": artifacts,
                "script": script.name,
            }
        except asyncio.TimeoutError:
            raise HTTPException(status_code=500, detail="安装超时（120 秒）")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"安装失败: {str(e)}")

    @router.get("/cannbot/install-check/{scenario_path:path}")
    async def check_cannbot_install(scenario_path: str):
        """检查场景安装状态：检测项目级和全局级目录"""
        if not CANNBOT_DIR.exists():
            raise HTTPException(status_code=404, detail="仓库尚未 clone")

        scenario_dir = CANNBOT_DIR / scenario_path
        if not scenario_dir.is_dir():
            raise HTTPException(status_code=404, detail=f"场景目录不存在: {scenario_path}")

        home = Path.home()
        tools_config = {
            "claude": {
                "project": [PROJECT_ROOT / ".claude"],
                "global": [home / ".claude"],
            },
            "cursor": {
                "project": [PROJECT_ROOT / ".cursor"],
                "global": [home / ".cursor"],
            },
            "trae": {
                "project": [PROJECT_ROOT / ".trae-cn", PROJECT_ROOT / ".marscode", PROJECT_ROOT / ".trae"],
                "global": [home / ".trae-cn", home / ".marscode", home / ".traecli"],
            },
            "opencode": {
                "project": [PROJECT_ROOT / ".opencode"],
                "global": [home / ".config" / "opencode"],
            },
        }

        results = {}
        for tool_name, level_dirs in tools_config.items():
            project_artifacts = []
            global_artifacts = []
            installed = False

            # 项目级检测
            for config_dir in level_dirs.get("project", []):
                art = _collect_install_artifacts(str(config_dir), str(PROJECT_ROOT), tool_name)
                art["level"] = "project"
                if art["exists"] and (art["skills"] or art["agents"]):
                    installed = True
                project_artifacts.append(art)

            # 全局级检测
            for config_dir in level_dirs.get("global", []):
                art = _collect_install_artifacts(str(config_dir), str(home), tool_name)
                art["level"] = "global"
                if art["exists"] and (art["skills"] or art["agents"]):
                    installed = True
                global_artifacts.append(art)

            results[tool_name] = {
                "installed": installed,
                "project": project_artifacts,
                "global": global_artifacts,
            }

        return {"scenario": scenario_path, "tools": results}
