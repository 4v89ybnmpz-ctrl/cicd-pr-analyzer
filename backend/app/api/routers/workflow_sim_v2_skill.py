"""工作流仿真 V2 — Skill 遵从度计算 + 监控 LLM 语义分析"""

import asyncio
import json
import logging
import os
from typing import Optional

from app.services.claude_code_driver import ClaudeCodeDriver

logger = logging.getLogger(__name__)

_PROJECT_ROOT = os.path.dirname(
    os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    )
)


def _find_plugin_dir(plugin_id: str) -> Optional[str]:
    for parent in ("plugins-official", "plugins-community"):
        d = os.path.join(_PROJECT_ROOT, "external", "cannbot-skills", parent, plugin_id)
        if os.path.isdir(d):
            return d
    return None


def compute_skill_compliance(
    events: list,
    required_skills: list,
    extra_referenced: list = None,
) -> dict:
    """计算 Skill 遵从度。"""
    referenced = ClaudeCodeDriver.extract_skill_references(events)
    skills_from_subagents = []
    if extra_referenced:
        for s in extra_referenced:
            if s not in referenced:
                referenced.append(s)
            if s not in skills_from_subagents:
                skills_from_subagents.append(s)
    expected = [s for s in required_skills if s]
    missing = [s for s in expected if s not in referenced]
    violations = []

    if missing:
        violations.append(
            {
                "type": "SKILL_NOT_REFERENCED",
                "detail": f"未引用预期 Skill: {', '.join(missing)}",
                "severity": "MED",
            }
        )

    score = len(set(referenced) & set(expected)) / len(expected) if expected else 1.0
    return {
        "score": round(score, 2),
        "skills_referenced": referenced,
        "skills_from_subagents": skills_from_subagents,
        "skills_expected": expected,
        "skills_missing": missing,
        "violations": violations,
    }


def read_skill_constraints(plugin_id: str, skill_names: list) -> dict:
    """读取指定 skills 的核心约束内容（SKILL.md 正文，截断 1500 字符）。"""
    plugin_dir = _find_plugin_dir(plugin_id)
    if not plugin_dir:
        return {}
    skills_dir = os.path.join(plugin_dir, ".claude", "skills")
    if not os.path.isdir(skills_dir):
        skills_dir = os.path.join(plugin_dir, "skills")
    if not os.path.isdir(skills_dir):
        return {}
    result = {}
    for name in skill_names:
        if not name:
            continue
        skill_md = os.path.join(skills_dir, name, "SKILL.md")
        if not os.path.isfile(skill_md):
            continue
        try:
            text = open(skill_md, encoding="utf-8", errors="replace").read(2000)
            desc = ""
            if text.startswith("---"):
                end = text.find("---", 3)
                if end > 0:
                    for line in text[3:end].split("\n"):
                        if line.startswith("description:"):
                            desc = line.split(":", 1)[1].strip().strip("'\"")
                            break
            if not desc:
                for line in text.split("\n"):
                    if line.startswith("# "):
                        desc = line.lstrip("# ").strip()[:100]
                        break
            body = text
            if text.startswith("---"):
                end = text.find("---", 3)
                if end > 0:
                    body = text[end + 3 :].strip()
            result[name] = {"description": desc, "constraints": body[:1500]}
        except Exception:
            pass
    return result


def summarize_events_for_monitor(events: list, max_events: int = 60) -> str:
    """将 events 列表格式化为监控 LLM 可读的摘要。"""
    if not events:
        return "(无事件)"
    lines = []
    for i, evt in enumerate(events[-max_events:]):
        et = evt.get("type", "unknown")
        if et == "thinking":
            lines.append(f"[{i + 1}] 思考: {str(evt.get('content', ''))[:200]}")
        elif et == "tool_use":
            name = evt.get("name", "")
            inp = evt.get("input", {})
            if isinstance(inp, dict):
                inp = json.dumps(inp, ensure_ascii=False)[:200]
            else:
                inp = str(inp)[:200]
            lines.append(f"[{i + 1}] 工具调用({name}): {inp}")
        elif et == "text":
            lines.append(f"[{i + 1}] 文本输出: {str(evt.get('content', ''))[:300]}")
        elif et == "result":
            lines.append(f"[{i + 1}] 最终结果: {str(evt.get('content', ''))[:300]}")
        else:
            lines.append(f"[{i + 1}] {et}: {json.dumps(evt, ensure_ascii=False)[:200]}")
    return "\n".join(lines)


MONITOR_SYSTEM_PROMPT = """你是一个 AI 辅助开发过程的 Skill 遵从度监控专家。
你需要分析 Claude Code 在执行某一步骤时的事件流，对照该步骤关联的 Skill 约束文档，判断每个 Skill 的核心要求是否被遵守。

分析维度：
1. Skill 中定义的流程/步骤是否被执行
2. Skill 中要求的产出物是否存在
3. Skill 中的禁止项/约束是否被违反
4. Skill 中的关键决策点是否遵循了指引

请严格按以下 JSON 格式输出（不要输出其他内容）：

```json
{
  "analysis_process": "一段话描述整体分析思路：看了哪些事件、怎么对照 Skill 约束、关键判断依据",
  "skills_analysis": [
    {
      "skill": "skill名称",
      "status": "compliant|partial|violation|not_detected",
      "confidence": 0.8,
      "constraints_checked": ["该 Skill 中你检查了哪些具体约束/要求"],
      "evidence_found": ["从事件流中找到的支撑证据，如具体的工具调用、输出内容"],
      "evidence_missing": ["期望找到但未找到的证据"],
      "reasoning": "详细的推理过程：为什么得出这个结论，引用具体事件编号和内容",
      "followed": ["已遵守的要求列表"],
      "violated": ["被违反的要求列表"],
      "missing": ["未检测到的要求列表"],
      "detail": "一句话说明"
    }
  ],
  "overall_score": 75,
  "overall_reasoning": "总体评分依据：为什么给这个分数，哪些 skill 表现好/差",
  "warnings": ["需要关注的警告"]
}
```"""


def parse_monitor_result(text: str) -> dict:
    """解析监控 LLM 返回的 JSON 结果。"""
    try:
        start = text.find("```json")
        if start >= 0:
            start = text.find("\n", start) + 1
            end = text.find("```", start)
            if end > start:
                return json.loads(text[start:end])
    except (json.JSONDecodeError, ValueError):
        pass
    try:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
    except (json.JSONDecodeError, ValueError):
        pass
    return {
        "skills_analysis": [],
        "overall_score": -1,
        "warnings": ["LLM 输出无法解析"],
        "raw": text[:500],
    }


async def monitor_skill_compliance(
    events: list,
    required_skills: list,
    plugin_id: str,
    step_name: str,
) -> dict:
    """调用监控 LLM 分析 skill 语义遵从度。"""
    if not required_skills:
        return {"skills_analysis": [], "overall_score": 100, "warnings": []}
    try:
        from workflow.config import workflow_config

        if not workflow_config.ai_ready:
            logger.warning("监控 LLM 未配置，跳过语义遵从度分析")
            return {
                "skills_analysis": [],
                "overall_score": -1,
                "warnings": ["LLM 未配置"],
            }

        skill_info = read_skill_constraints(plugin_id, required_skills)
        if not skill_info:
            return {
                "skills_analysis": [],
                "overall_score": -1,
                "warnings": ["Skill 文件未找到"],
            }

        events_summary = summarize_events_for_monitor(events, max_events=60)

        skills_desc = "\n\n".join(
            f"### Skill: {name}\n描述: {info['description']}\n约束内容:\n{info['constraints']}"
            for name, info in skill_info.items()
        )
        prompt = f"""## 分析任务
步骤名称: {step_name}
该步骤关联的 Skills:

{skills_desc}

## Claude Code 执行事件流
{events_summary}

请分析以上事件流，判断每个 Skill 的核心要求是否被遵守。"""

        loop = asyncio.get_event_loop()
        response = await asyncio.wait_for(
            loop.run_in_executor(
                None,
                lambda: workflow_config.llm.invoke(
                    [
                        {"role": "system", "content": MONITOR_SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ]
                ),
            ),
            timeout=60.0,
        )
        return parse_monitor_result(response.content)

    except asyncio.TimeoutError:
        logger.warning("监控 LLM 分析超时")
        return {
            "skills_analysis": [],
            "overall_score": -1,
            "warnings": ["LLM 分析超时"],
        }
    except Exception as e:
        logger.error(f"监控 LLM 分析失败: {e}")
        return {
            "skills_analysis": [],
            "overall_score": -1,
            "warnings": [f"LLM 分析失败: {str(e)}"],
        }


# ==================== AI 门禁判断 ====================

AI_GATE_PROMPT = """你是一个算子开发流程的门禁审查专家。
你需要判断当前步骤的产出是否符合插件标准。

## 判断标准
- 步骤名称和要求的产出物
- 步骤 prompt 中的完成条件（如"DESIGN.md 和 PLAN.md 都存在"等）
- 产出文件的实际内容是否满足步骤要求的核心要素

## 判断规则
1. 如果预期文件存在且内容符合要求 → passed
2. 如果预期文件不存在，但工作目录中有等价产出（内容覆盖了步骤要求的核心要素）→ passed（标注替代文件）
3. 如果文件存在但内容明显不完整（空文件、只有标题无正文、模板未填充）→ failed
4. 如果文件不存在且无等价产出 → failed

请严格按以下 JSON 格式输出：
```json
{
  "verdict": "passed" | "failed",
  "reasoning": "判断依据",
  "found_files": ["实际找到的相关文件路径"],
  "missing_core": ["缺失的核心要素"],
  "suggestion": "如 failed，给出修正建议"
}
```"""


async def ai_gate_check(
    work_dir: str,
    step_name: str,
    expected_artifacts: list,
    step_prompt: str,
) -> dict:
    """AI 门禁：读取产出文件内容 + 步骤要求，用 LLM 判断是否达标。

    在文件门禁失败时调用。如果 AI 判断产出已达标（即使文件名/路径不同），
    则覆盖文件门禁结果为通过。
    """
    if not expected_artifacts and not step_prompt:
        return {"verdict": "skipped", "reasoning": "无产出物要求"}

    try:
        from workflow.config import workflow_config

        if not workflow_config.ai_ready:
            return {"verdict": "skipped", "reasoning": "LLM 未配置"}

        # 收集工作目录中实际存在的文件（docs 目录 + 根目录）
        found_files = {}
        for search_dir in [
            work_dir,
            os.path.join(work_dir, "operators"),
            os.path.join(work_dir, "docs"),
        ]:
            if not os.path.isdir(search_dir):
                continue
            for root, dirs, files in os.walk(search_dir):
                # 跳过 .git, node_modules, __pycache__ 等
                dirs[:] = [
                    d
                    for d in dirs
                    if d
                    not in (".git", "node_modules", "__pycache__", ".claude", "build")
                ]
                for f in files:
                    if (
                        f.endswith(".md")
                        or f.endswith(".py")
                        or f.endswith(".yaml")
                        or f.endswith(".yml")
                    ):
                        fp = os.path.join(root, f)
                        try:
                            content = open(fp, encoding="utf-8", errors="replace").read(
                                3000
                            )
                            rel_path = os.path.relpath(fp, work_dir)
                            found_files[rel_path] = content
                        except Exception:
                            pass
                        if len(found_files) >= 30:
                            break
                if len(found_files) >= 30:
                    break
            if len(found_files) >= 30:
                break

        # 构建产出文件摘要
        files_summary = (
            "\n\n".join(
                f"### {path}\n```\n{content[:1500]}\n```"
                for path, content in list(found_files.items())[:20]
            )
            or "(无找到任何产出文件)"
        )

        expected_list = (
            "\n".join(f"- {a}" for a in expected_artifacts) or "(未声明具体文件)"
        )

        prompt = f"""## 步骤信息
步骤名称: {step_name}
预期产出物:
{expected_list}

## 步骤要求（prompt 摘要）
{step_prompt[:2000]}

## 工作目录中实际找到的文件
{files_summary}

请判断当前步骤的产出是否符合插件标准。"""

        loop = asyncio.get_event_loop()
        response = await asyncio.wait_for(
            loop.run_in_executor(
                None,
                lambda: workflow_config.llm.invoke(
                    [
                        {"role": "system", "content": AI_GATE_PROMPT},
                        {"role": "user", "content": prompt},
                    ]
                ),
            ),
            timeout=60.0,
        )

        # 解析结果
        result = _parse_ai_gate_result(response.content)
        result["found_files_list"] = list(found_files.keys())
        return result

    except asyncio.TimeoutError:
        return {"verdict": "skipped", "reasoning": "AI 门禁分析超时"}
    except Exception as e:
        logger.error(f"AI 门禁判断失败: {e}")
        return {"verdict": "skipped", "reasoning": f"AI 门禁异常: {e}"}


def _parse_ai_gate_result(text: str) -> dict:
    """解析 AI 门禁 LLM 返回的 JSON。"""
    try:
        start = text.find("```json")
        if start >= 0:
            start = text.find("\n", start) + 1
            end = text.find("```", start)
            if end > start:
                return json.loads(text[start:end])
    except (json.JSONDecodeError, ValueError):
        pass
    try:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
    except (json.JSONDecodeError, ValueError):
        pass
    return {"verdict": "skipped", "reasoning": "AI 门禁输出无法解析", "raw": text[:500]}
