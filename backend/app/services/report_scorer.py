"""可用性仿真评估 — 维度评分器

从一次仿真 session 的已有数据（步骤状态、门禁、产物、Skill 遵从度、token、错误分类）
计算 9 个评估维度的 0-100 分，不做外部 LLM 调用，保证报告在任何环境下都能产出。

设计原则：
- 纯数据驱动，基于 session 已采集字段计算
- 本地优先：CI/CD 结果、修复效率在无 pipeline 数据时标注 N/A（不参与计分，权重重分配）
- 需要语义判断的维度（设计/代码质量）用"产物存在性 + 结构完整性"等可客观计算的代理指标
"""

from __future__ import annotations
import os
from typing import Optional

# 维度默认权重（本地优先；N/A 维度的权重会并入代码质量）
DEFAULT_WEIGHTS = {
    "design_quality": 15,        # 设计质量
    "code_quality": 20,          # 代码质量
    "boundary_compliance": 15,   # 职责边界合规
    "design_impl_consistency": 10,  # 设计-实现一致性
    "skill_compliance": 15,      # Skill 遵从度
    "gate_pass_rate": 10,        # 门禁通过率
    "token_efficiency": 5,       # Token 效率
    "cicd_result": 10,           # CI/CD 结果（本地优先常为 N/A）
}

# 设计文档期望包含的章节关键词（用于设计质量的结构完整性评分）
DESIGN_SECTIONS = ["tiling", "api", "数据流", "dataflow", "分支", "branch", "伪代码", "pseudocode"]
# 代码文件扩展名（用于代码质量维度的产物识别）
CODE_EXTS = (".asc", ".cpp", ".cc", ".cu", ".py", ".h")


def _clamp(v: float) -> float:
    return max(0.0, min(100.0, v))


def _score_skill_compliance(steps: list) -> Optional[float]:
    """Skill 遵从度：各配置了 expected skill 的步骤 score 均值。
    无任何步骤配置 expected skill 时返回 None（无法评估，非 0 分）。"""
    scores = []
    for s in steps:
        sc = s.get("skill_compliance") or {}
        expected = sc.get("skills_expected") or []
        if expected:  # 只统计配置了期望 skill 的步骤
            scores.append(float(sc.get("score", 0.0)) * 100)
    if not scores:
        return None
    return _clamp(sum(scores) / len(scores))


def _score_gate_pass_rate(steps: list) -> Optional[float]:
    """门禁通过率：gated 步骤中 passed / gated_total。
    无任何 gated 步骤时返回 None。"""
    gated = [s for s in steps if s.get("gate_passed") is not None]
    if not gated:
        return None
    passed = [s for s in gated if s.get("gate_passed") is True]
    return _clamp(len(passed) / len(gated) * 100)


def _score_design_quality(steps: list, work_dir: str) -> Optional[float]:
    """设计质量：设计类步骤的 docs 产物存在率 × 结构完整性。
    代理指标——检查 DESIGN.md/PLAN.md 是否存在且包含关键章节。"""
    design_steps = [s for s in steps if any(
        k in (s.get("step_name") or "").lower() for k in ("设计", "design", "架构", "arch"))]
    if not design_steps:
        return None
    # 产物存在率
    existence_scores = []
    for s in design_steps:
        arts = s.get("gate_artifacts") or []
        if not arts:
            continue
        exists = sum(1 for a in arts if a.get("exists"))
        existence_scores.append(exists / len(arts))
    if not existence_scores:
        return None
    existence = sum(existence_scores) / len(existence_scores)
    # 结构完整性：扫描 work_dir 下的 DESIGN.md 是否含关键章节
    structure = 0.0
    design_md = _find_artifact(work_dir, "DESIGN.md")
    if design_md and os.path.exists(design_md):
        try:
            text = open(design_md, encoding="utf-8", errors="ignore").read().lower()
            hits = sum(1 for kw in DESIGN_SECTIONS if kw in text)
            structure = hits / len(DESIGN_SECTIONS)
        except Exception:
            structure = 0.0
    # 存在率占 70%，结构占 30%
    return _clamp(existence * 70 + structure * 30)


def _score_code_quality(steps: list, work_dir: str) -> Optional[float]:
    """代码质量：是否有代码产物生成 + 步骤失败率（崩溃/错误越多分越低）。
    本地优先下不做真实编译，用产物存在性和执行稳定性作代理。"""
    # 代码产物存在性
    has_code = False
    if work_dir and os.path.isdir(work_dir):
        for root, _, files in os.walk(work_dir):
            if any(f.endswith(CODE_EXTS) for f in files):
                has_code = True
                break
    # 执行稳定性：非 failed 的步骤占比
    total = len(steps)
    if total == 0:
        return None
    failed = sum(1 for s in steps if s.get("status") == "failed")
    stability = (total - failed) / total
    # 有代码产物占 60%，执行稳定占 40%
    artifact_score = 100.0 if has_code else 0.0
    return _clamp(artifact_score * 0.6 + stability * 100 * 0.4)


def _score_boundary_compliance(steps: list) -> Optional[float]:
    """职责边界合规：各步骤 skill_compliance 中无 violation 的占比。
    violation 越多说明 Agent 越界（该用 skill 没用、不该做的做了）。"""
    relevant = [s for s in steps if s.get("skill_compliance")]
    if not relevant:
        return None
    clean = sum(1 for s in relevant if not (s.get("skill_compliance") or {}).get("violations"))
    return _clamp(clean / len(relevant) * 100)


def _score_design_impl_consistency(steps: list, work_dir: str) -> Optional[float]:
    """设计-实现一致性：设计产物与代码产物是否同时存在。
    有设计文档且有代码 → 高分；只有设计无代码 → 低分（设计没落地）。"""
    has_design = _find_artifact(work_dir, "DESIGN.md") is not None
    has_code = False
    if work_dir and os.path.isdir(work_dir):
        for root, _, files in os.walk(work_dir):
            if any(f.endswith(CODE_EXTS) for f in files):
                has_code = True
                break
    if not has_design and not has_code:
        return None
    if has_design and has_code:
        return 100.0
    if has_design and not has_code:
        return 40.0  # 有设计但没实现
    return 60.0  # 有代码但缺设计文档


def _score_token_efficiency(session: dict) -> Optional[float]:
    """Token 效率：基于总 token 量的分段评分。
    无 token 数据（进程被杀没记录）时返回 None。"""
    tokens = (session.get("summary") or {}).get("total_tokens") or {}
    total = (tokens.get("input") or 0) + (tokens.get("output") or 0)
    if total == 0:
        return None
    # 分段：<50k 满分，>500k 低分
    if total < 50000:
        return 100.0
    if total < 150000:
        return 80.0
    if total < 300000:
        return 60.0
    if total < 500000:
        return 40.0
    return 20.0


def _find_artifact(work_dir: str, name: str) -> Optional[str]:
    """在 work_dir 下递归查找指定文件名。"""
    if not work_dir or not os.path.isdir(work_dir):
        return None
    for root, _, files in os.walk(work_dir):
        if name in files:
            return os.path.join(root, name)
    return None


def compute_dimension_scores(session: dict, work_dir: Optional[str] = None) -> dict:
    """计算单次 session 的 9 维度评分。

    返回:
        {
          "dimensions": {dim: {"score": float|None, "na": bool, "reason": str}},
          "weighted_total": float,           # 加权总分（N/A 维度权重重分配后）
          "available_weight": float,         # 实际参与计分的权重总和
        }
    """
    steps = session.get("steps") or []
    wd = work_dir or session.get("work_dir") or ""

    raw = {
        "skill_compliance": _score_skill_compliance(steps),
        "gate_pass_rate": _score_gate_pass_rate(steps),
        "design_quality": _score_design_quality(steps, wd),
        "code_quality": _score_code_quality(steps, wd),
        "boundary_compliance": _score_boundary_compliance(steps),
        "design_impl_consistency": _score_design_impl_consistency(steps, wd),
        "token_efficiency": _score_token_efficiency(session),
    }

    # CI/CD 结果与修复效率：本地优先下无 pipeline 数据则 N/A
    pipeline = session.get("pipeline") or {}
    has_pipeline = bool(pipeline and pipeline.get("stages"))
    cicd_score = None
    cicd_na = not has_pipeline
    cicd_reason = "本地仿真未跑真实 CI/CD" if cicd_na else ""

    dimensions = {}
    for dim, weight in DEFAULT_WEIGHTS.items():
        if dim == "cicd_result":
            dimensions[dim] = {
                "score": round(cicd_score, 1) if cicd_score is not None else None,
                "na": cicd_na,
                "reason": cicd_reason,
                "weight": weight,
            }
        else:
            val = raw.get(dim)
            dimensions[dim] = {
                "score": round(val, 1) if val is not None else None,
                "na": val is None,
                "reason": "无可用数据" if val is None else "",
                "weight": weight,
            }

    # 修复效率维度（不在 DEFAULT_WEIGHTS，单独处理，本地优先下通常 N/A）
    fix_rounds = pipeline.get("fix_rounds") if has_pipeline else None
    dimensions["fix_efficiency"] = {
        "score": None,
        "na": fix_rounds is None,
        "reason": "本地仿真未跑修复循环" if fix_rounds is None else "",
        "weight": 0,  # 本地优先下不占权重
    }

    # 加权总分：N/A 维度的权重按比例并入 code_quality（最核心维度）
    active = {d: v for d, v in dimensions.items() if not v["na"] and v["weight"] > 0}
    na_weight = sum(v["weight"] for d, v in dimensions.items() if v["na"] and d != "fix_efficiency")
    if active:
        total_weight = sum(v["weight"] for v in active.values())
        # 把 N/A 权重并入 code_quality（若它 active）
        if "code_quality" in active and na_weight > 0:
            active["code_quality"]["weight"] += na_weight
            total_weight += na_weight
        weighted_total = sum(v["score"] * v["weight"] for v in active.values()) / total_weight
    else:
        weighted_total = 0.0

    return {
        "dimensions": dimensions,
        "weighted_total": round(weighted_total, 1),
    }


# ==================== 项目级汇总 ====================

def _conclusion(total: float, dims: dict) -> str:
    """根据总分和硬性否决条件得出可用性结论。"""
    # 硬性否决：门禁通过率 <50% 或 Skill 遵从度 <40% → 不可用
    gate = dims.get("gate_pass_rate", {})
    skill = dims.get("skill_compliance", {})
    if (not gate["na"] and gate["score"] is not None and gate["score"] < 50):
        return "不可用（门禁通过率过低）"
    if (not skill["na"] and skill["score"] is not None and skill["score"] < 40):
        return "不可用（Skill 遵从度过低）"
    if total >= 80:
        return "可用"
    if total >= 60:
        return "基本可用（需改进）"
    return "不可用"


def aggregate_project_report(sessions: list) -> dict:
    """从一批 session 汇总出项目级可用性评估。

    参数: sessions - 已跑完的 session dict 列表（含 steps/summary/work_dir）
    返回: {total_score, conclusion, per_dim_avg, plugin_subtotals, session_count, ...}
    """
    if not sessions:
        return {
            "total_score": 0.0,
            "conclusion": "无数据",
            "session_count": 0,
            "per_dim_avg": {},
            "plugin_subtotals": [],
        }

    # 逐 session 算分
    per_session = []
    for s in sessions:
        sc = compute_dimension_scores(s)
        per_session.append({
            "session_id": s.get("session_id"),
            "plugin_id": s.get("plugin_id"),
            "op_name": s.get("op_name"),
            "verdict": (s.get("summary") or {}).get("verdict"),
            "weighted_total": sc["weighted_total"],
            "dimensions": sc["dimensions"],
            "work_dir": s.get("work_dir"),
        })

    # 各维度跨 session 均值（只统计非 N/A 的）
    dim_avg = {}
    for dim in DEFAULT_WEIGHTS.keys():
        vals = [ps["dimensions"][dim]["score"] for ps in per_session
                if not ps["dimensions"][dim]["na"] and ps["dimensions"][dim]["score"] is not None]
        dim_avg[dim] = {
            "score": round(sum(vals) / len(vals), 1) if vals else None,
            "na": not vals,
            "weight": DEFAULT_WEIGHTS[dim],
        }

    # 项目总分：各 session weighted_total 的均值
    totals = [ps["weighted_total"] for ps in per_session]
    project_total = round(sum(totals) / len(totals), 1) if totals else 0.0
    conclusion = _conclusion(project_total, dim_avg)

    # 各插件小计
    plugin_map = {}
    for ps in per_session:
        pid = ps["plugin_id"] or "unknown"
        plugin_map.setdefault(pid, []).append(ps["weighted_total"])
    plugin_subtotals = [
        {"plugin_id": pid, "session_count": len(ts),
         "avg_score": round(sum(ts) / len(ts), 1)}
        for pid, ts in plugin_map.items()
    ]
    plugin_subtotals.sort(key=lambda x: -x["avg_score"])

    return {
        "total_score": project_total,
        "conclusion": conclusion,
        "session_count": len(sessions),
        "plugin_count": len(plugin_map),
        "per_dim_avg": dim_avg,
        "plugin_subtotals": plugin_subtotals,
        "per_session": per_session,
    }


# ==================== 插件断点诊断（跨 session 病灶聚合） ====================


def build_breakpoint_diagnosis(sessions: list, plugin_id: str) -> dict:
    """跨 session 聚合插件断点/病灶。

    纯数据驱动，从一批已完成的 session 聚合出：
    - 步骤级失败率/门禁失败/错误分类分布（驱动 DAG 节点热度 + 排行表）
    - 错误类型 / 告警类型 / 告警严重度 总分布（饼图）
    - Skill 漏读排行 / 产物缺失排行（Top 病灶）

    所有计数对脏数据防御（字段缺失用 .get 兜底），无 session 时返回空结构。
    """
    plugin_id = plugin_id or ""
    # ----- meta -----
    op_names = []
    verdict_dist = {}
    for s in sessions:
        op = s.get("op_name") or ""
        if op and op not in op_names:
            op_names.append(op)
        verdict = (s.get("summary") or {}).get("verdict") or "UNKNOWN"
        verdict_dist[verdict] = verdict_dist.get(verdict, 0) + 1

    meta = {
        "session_count": len(sessions),
        "op_count": len(op_names),
        "op_names": op_names,
        "verdict_distribution": verdict_dist,
    }

    # ----- step_breakdown：按 step_id 跨 session 累加 -----
    step_acc = {}  # step_id -> 累加器
    for s in sessions:
        for st in (s.get("steps") or []):
            sid = st.get("step_id") or st.get("step_name") or "unknown"
            acc = step_acc.setdefault(sid, {
                "step_id": sid,
                "step_name": st.get("step_name") or sid,
                "appear": 0, "failed": 0, "gate_failed": 0,
                "duration_sum": 0, "duration_count": 0, "max_duration_ms": 0,
                "error_categories": {},
            })
            acc["appear"] += 1
            if st.get("status") == "failed":
                acc["failed"] += 1
            if st.get("gate_passed") is False:
                acc["gate_failed"] += 1
            dur = st.get("duration_ms") or 0
            if dur:
                acc["duration_sum"] += dur
                acc["duration_count"] += 1
                if dur > acc["max_duration_ms"]:
                    acc["max_duration_ms"] = dur
            cat = (st.get("error_detail") or {}).get("category")
            if cat:
                acc["error_categories"][cat] = acc["error_categories"].get(cat, 0) + 1

    step_breakdown = []
    for acc in step_acc.values():
        appear = acc["appear"] or 1
        step_breakdown.append({
            "step_id": acc["step_id"],
            "step_name": acc["step_name"],
            "appear": acc["appear"],
            "failed": acc["failed"],
            "fail_rate": round(acc["failed"] / appear, 3),
            "gate_failed": acc["gate_failed"],
            "avg_duration_ms": round(acc["duration_sum"] / (acc["duration_count"] or 1)),
            "max_duration_ms": acc["max_duration_ms"],
            "error_categories": acc["error_categories"],
        })
    step_breakdown.sort(key=lambda x: -x["fail_rate"])

    # ----- 三个总分布：error_category / alert_type / alert_severity -----
    error_cat_dist = {}
    alert_type_dist = {}
    alert_sev_dist = {}
    for s in sessions:
        # 步骤级 error_detail 汇总到 error_category_distribution
        for st in (s.get("steps") or []):
            cat = (st.get("error_detail") or {}).get("category")
            if cat and st.get("status") == "failed":
                error_cat_dist[cat] = error_cat_dist.get(cat, 0) + 1
        # 断点告警汇总
        for a in (s.get("breakpoint_alerts") or []):
            t = a.get("type")
            if t:
                alert_type_dist[t] = alert_type_dist.get(t, 0) + 1
            sev = a.get("severity")
            if sev:
                alert_sev_dist[sev] = alert_sev_dist.get(sev, 0) + 1
            # 告警里的 error_category 也并入错误分布（告警往往比 step.error_detail 更全）
            ec = a.get("error_category")
            if ec:
                error_cat_dist[ec] = error_cat_dist.get(ec, 0) + 1

    # ----- skill_missing_ranking：哪个 skill 最常被漏读 -----
    skill_acc = {}  # skill -> {missing_count, in_sessions(set), steps(set)}
    for s in sessions:
        sid = s.get("session_id") or ""
        for st in (s.get("steps") or []):
            step_id = st.get("step_id") or ""
            for sk in ((st.get("skill_compliance") or {}).get("skills_missing") or []):
                a = skill_acc.setdefault(sk, {"missing_count": 0, "_sessions": set(), "_steps": set()})
                a["missing_count"] += 1
                if sid:
                    a["_sessions"].add(sid)
                if step_id:
                    a["_steps"].add(step_id)
    skill_missing_ranking = [
        {
            "skill": sk,
            "missing_count": a["missing_count"],
            "in_sessions": len(a["_sessions"]),
            "steps": sorted(a["_steps"]),
        }
        for sk, a in skill_acc.items()
    ]
    skill_missing_ranking.sort(key=lambda x: -x["missing_count"])

    # ----- artifact_missing_ranking：哪个产出物最常没生成 -----
    art_acc = {}  # name -> {missing_count, steps(set)}
    for s in sessions:
        for st in (s.get("steps") or []):
            step_id = st.get("step_id") or ""
            for art in (st.get("gate_artifacts") or []):
                if not art.get("exists"):
                    name = art.get("name") or ""
                    if not name:
                        continue
                    a = art_acc.setdefault(name, {"missing_count": 0, "_steps": set()})
                    a["missing_count"] += 1
                    if step_id:
                        a["_steps"].add(step_id)
    artifact_missing_ranking = [
        {"artifact": name, "missing_count": a["missing_count"], "steps": sorted(a["_steps"])}
        for name, a in art_acc.items()
    ]
    artifact_missing_ranking.sort(key=lambda x: -x["missing_count"])

    return {
        "plugin_id": plugin_id,
        "meta": meta,
        "step_breakdown": step_breakdown,
        "error_category_distribution": error_cat_dist,
        "alert_type_distribution": alert_type_dist,
        "alert_severity_distribution": alert_sev_dist,
        "skill_missing_ranking": skill_missing_ranking,
        "artifact_missing_ranking": artifact_missing_ranking,
    }
