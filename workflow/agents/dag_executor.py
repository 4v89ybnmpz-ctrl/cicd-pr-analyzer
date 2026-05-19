"""
DAG 执行引擎 v2
核心改进:
1. 直接按任务列表调用工具函数，不拼文本给 LLM 再让 LLM 解析
2. 真正执行并行组（parallel_groups）
3. 规则工具（collector/validator）不经过 LLM，节省 token
4. 需要 LLM 的 Agent（analyst/reporter）才走 Agent
5. 验证反馈循环: 数据不足时重跑 collector + analyst
"""
import json
import logging
import time
from typing import Dict, Any, List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# 工具直接调用映射 — 这些工具是纯代码，不需要 LLM
_TOOL_MAP = {
    "fetch_pr_list": "workflow.agents.collector_tools",
    "fetch_pr_comments": "workflow.agents.collector_tools",
    "fetch_pr_details": "workflow.agents.collector_tools",
    "fetch_pr_reviews": "workflow.agents.collector_tools",
    "check_db_cache": "workflow.agents.collector_tools",
    "query_cicd_results": "workflow.agents.collector_tools",
    "incremental_fetch": "workflow.agents.collector_tools",
    "parallel_fetch": "workflow.agents.collector_tools",
    "analyze_cicd_comments": "workflow.agents.analyst_tools",
    "get_cicd_stats": "workflow.agents.analyst_tools",
    "get_cicd_trends": "workflow.agents.analyst_tools",
    "get_failure_analysis": "workflow.agents.analyst_tools",
    "query_pr_details": "workflow.agents.analyst_tools",
    "query_pr_reviews": "workflow.agents.analyst_tools",
    "generate_stats_report": "workflow.agents.reporter_tools",
    "format_report_md": "workflow.agents.reporter_tools",
    "format_report_html": "workflow.agents.reporter_tools",
    "format_report_json": "workflow.agents.reporter_tools",
    "validate_collected_data": "workflow.agents.validator_agent",
    "validate_analysis_quality": "workflow.agents.validator_agent",
}

# 需要 LLM 才能工作的 Agent（需要 LLM 做推理/生成）
_LLM_REQUIRED_AGENTS = {"analyst", "reporter"}

# 纯工具 Agent（所有功能都是工具调用，LLM 只做路由）
_TOOL_ONLY_AGENTS = {"collector", "validator"}


def _invoke_tool(tool_name: str, params: Dict[str, Any]) -> str:
    """直接调用工具函数，返回结果字符串"""
    import importlib
    module_path = _TOOL_MAP.get(tool_name)
    if not module_path:
        return json.dumps({"error": f"未知工具: {tool_name}"}, ensure_ascii=False)
    try:
        mod = importlib.import_module(module_path)
        func = getattr(mod, tool_name)
        return func.invoke(params)
    except Exception as e:
        return json.dumps({"error": f"{tool_name} 调用失败: {e}"}, ensure_ascii=False)


def _run_agent(agent_name: str, task: str, llm: Any = None) -> Dict[str, Any]:
    """运行 Agent，LLM 不可用时自动降级"""
    if llm:
        try:
            from workflow.agents.registry import agent_registry
            registered = [d["name"] for d in agent_registry.list_registered()]
            if agent_name not in registered:
                agent_registry.register_defaults()
            agent = agent_registry.get(agent_name)
            if agent and agent.available:
                result = agent.run(task)
                agent_registry.record_invocation(agent_name, success=result.get("error") is None)
                return {
                    "output": result.get("output", ""),
                    "tool_calls": result.get("tool_calls", 0),
                    "source": "agent",
                }
        except Exception as e:
            logger.warning(f"Agent [{agent_name}] 失败: {e}")
    return {"output": "", "tool_calls": 0, "source": "fallback"}


@dataclass
class StageResult:
    stage: str
    agent: str
    status: str  # ok / skipped / error
    output: str = ""
    error: Optional[str] = None
    duration_ms: float = 0.0
    skipped: bool = False
    skip_reason: str = ""
    tool_results: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class DAGRunResult:
    plan_id: str
    owner: str
    repo: str
    status: str = "running"
    stages: List[StageResult] = field(default_factory=list)
    total_duration_ms: float = 0.0
    retry_count: int = 0
    max_retries: int = 1
    started_at: float = field(default_factory=time.time)
    completed_at: float = 0.0
    report: Dict[str, Any] = field(default_factory=dict)

    @property
    def failed_stages(self):
        return [s for s in self.stages if s.status == "error"]


class DAGExecutor:
    """
    DAG 执行引擎 v2

    执行策略:
    - collector/validator: 直接按任务列表调用工具（不经过 LLM）
    - analyst/reporter: 通过 Agent 执行（需要 LLM 推理）
    - parallel_groups: 用 ThreadPoolExecutor 真正并行执行
    - 验证失败: 重跑 collector 的工具 + analyst
    """

    def __init__(self, llm=None, max_retries: int = 1, max_parallel: int = 4):
        self.llm = llm
        self.max_retries = max_retries
        self.max_parallel = max_parallel
        self._stage_outputs: Dict[str, str] = {}

    def execute(self, plan_json: str) -> DAGRunResult:
        try:
            plan = json.loads(plan_json)
        except Exception:
            return DAGRunResult(plan_id="invalid", owner="", repo="", status="error", completed_at=time.time())

        result = DAGRunResult(
            plan_id=plan.get("plan_id", "unknown"),
            owner=plan.get("owner", ""),
            repo=plan.get("repo", ""),
            max_retries=self.max_retries,
        )
        stages = plan.get("stages", [])
        parallel_groups = plan.get("parallel_groups", [])

        logger.info(f"[DAG] 开始: {result.plan_id}, {len(stages)} 阶段")

        for stage_def in stages:
            if stage_def.get("skipped"):
                result.stages.append(StageResult(
                    stage=stage_def.get("stage", ""),
                    agent=stage_def.get("agent", ""),
                    status="skipped", skipped=True,
                    skip_reason=stage_def.get("reason", ""),
                ))
                continue

            stage_result = self._execute_stage(stage_def, parallel_groups)
            result.stages.append(stage_result)

            # 验证反馈循环
            if stage_def.get("stage") == "validation":
                output = stage_result.output or ""
                # 解析 JSON 取结构化字段来判断（避免编码问题）
                needs_retry = stage_result.status == "error"
                if not needs_retry:
                    try:
                        parsed = json.loads(output)
                        score = parsed.get("completeness_score", 100)
                        is_valid = parsed.get("valid", True)
                        if score < 50 or is_valid is False:
                            needs_retry = True
                    except Exception:
                        pass
                if needs_retry and result.retry_count < self.max_retries:
                    retry = self._retry_after_validation(result, stages, parallel_groups)
                    if retry:
                        result.retry_count += 1

            # 关键阶段失败则终止
            if stage_result.status == "error" and stage_def.get("stage") == "collection":
                logger.error(f"[DAG] 采集失败，终止")
                break

        result.completed_at = time.time()
        result.total_duration_ms = round((result.completed_at - result.started_at) * 1000, 2)
        result.report = self._build_report(result)
        result.status = "completed" if not result.failed_stages else "partial"
        logger.info(f"[DAG] 完成: {result.status}, {result.total_duration_ms:.0f}ms")
        return result

    def _execute_stage(self, stage_def: Dict, parallel_groups: List[List[str]]) -> StageResult:
        stage_name = stage_def.get("stage", "unknown")
        agent_name = stage_def.get("agent", "")
        tasks = stage_def.get("tasks", [])
        start = time.time()

        logger.info(f"[DAG] 阶段: {stage_name} (agent={agent_name}, tasks={len(tasks)})")

        # 决策: 工具型 Agent 直接调工具，LLM 型 Agent 走 Agent
        if agent_name in _TOOL_ONLY_AGENTS:
            result = self._execute_tools_directly(stage_name, tasks, parallel_groups)
        elif agent_name in _LLM_REQUIRED_AGENTS:
            result = self._execute_via_agent(agent_name, stage_name, tasks)
        else:
            # 未知 Agent，先尝试直接调工具，失败则走 Agent
            result = self._execute_tools_directly(stage_name, tasks, parallel_groups)
            if result.status == "error" and self.llm:
                result = self._execute_via_agent(agent_name, stage_name, tasks)

        result.duration_ms = round((time.time() - start) * 1000, 2)
        self._stage_outputs[stage_name] = result.output
        return result

    def _execute_tools_directly(self, stage_name: str, tasks: List[Dict],
                                 parallel_groups: List[List[str]]) -> StageResult:
        """直接按任务列表调用工具函数"""
        outputs = []
        tool_results = []
        errors = []

        # 识别可并行的任务
        parallel_task_ids = set()
        for group in parallel_groups:
            for tid in group:
                parallel_task_ids.add(tid)

        sequential_tasks = [t for t in tasks if t.get("id") not in parallel_task_ids]
        parallel_tasks = [t for t in tasks if t.get("id") in parallel_task_ids]

        # 顺序执行
        for t in sequential_tasks:
            out = _invoke_tool(t.get("tool", ""), t.get("params", {}))
            outputs.append(out)
            tool_results.append({"task_id": t.get("id"), "output": out[:500]})
            if out.startswith('{"error"') or "不可用" in out:
                errors.append(t.get("id", ""))

        # 并行执行
        if parallel_tasks:
            with ThreadPoolExecutor(max_workers=self.max_parallel) as pool:
                futures = {
                    pool.submit(_invoke_tool, t.get("tool", ""), t.get("params", {})): t
                    for t in parallel_tasks
                }
                for future in as_completed(futures):
                    t = futures[future]
                    try:
                        out = future.result()
                        outputs.append(out)
                        tool_results.append({"task_id": t.get("id"), "output": out[:500]})
                        if out.startswith('{"error"') or "不可用" in out:
                            errors.append(t.get("id", ""))
                    except Exception as e:
                        errors.append(t.get("id", ""))
                        outputs.append(json.dumps({"error": str(e)}))

        combined = "\n".join(outputs)
        status = "error" if len(errors) > len(tasks) // 2 + 1 else "ok"

        return StageResult(
            stage=stage_name,
            agent="tools",
            status=status,
            output=combined,
            tool_results=tool_results,
        )

    def _execute_via_agent(self, agent_name: str, stage_name: str,
                            tasks: List[Dict]) -> StageResult:
        """通过 LLM Agent 执行"""
        owner = ""
        repo = ""
        for t in tasks:
            p = t.get("params", {})
            if "owner" in p:
                owner = p["owner"]
                repo = p.get("repo", "")
                break

        task = f"执行 {stage_name} 阶段, 项目 {owner}/{repo}"
        if agent_name == "analyst":
            task = f"分析 {owner}/{repo} 的 CI/CD 工程效能"
        elif agent_name == "reporter":
            task = f"为 {owner}/{repo} 生成 CI/CD 洞察报告"

        agent_result = _run_agent(agent_name, task, self.llm)

        # Agent fallback: 如果 LLM 不可用，降级到工具直接调用
        if agent_result.get("source") == "fallback":
            return self._execute_tools_directly(stage_name, tasks, [])

        output = agent_result.get("output", "")
        has_error = not output or "不可用" in output or output.startswith("执行失败")
        return StageResult(
            stage=stage_name,
            agent=agent_name,
            status="error" if has_error else "ok",
            output=output,
        )

    def _retry_after_validation(self, dag_result: DAGRunResult,
                                 stages: List[Dict],
                                 parallel_groups: List[List[str]]) -> bool:
        """验证失败后重试: 重跑 collection + analysis"""
        retry_done = False

        for stage_def in stages:
            stage_name = stage_def.get("stage", "")
            if stage_name in ("collection", "analysis") and not stage_def.get("skipped"):
                logger.info(f"[DAG] 重试阶段: {stage_name}")
                retry = self._execute_stage(stage_def, parallel_groups)
                retry.stage = f"{stage_name}_retry_{dag_result.retry_count + 1}"
                dag_result.stages.append(retry)
                retry_done = True

        return retry_done

    def _build_report(self, dag_result: DAGRunResult) -> Dict[str, Any]:
        report = {
            "plan_id": dag_result.plan_id,
            "owner": dag_result.owner, "repo": dag_result.repo,
            "status": dag_result.status,
            "duration_ms": dag_result.total_duration_ms,
            "retries": dag_result.retry_count,
            "stages": [
                {
                    "stage": s.stage, "agent": s.agent, "status": s.status,
                    "duration_ms": s.duration_ms, "skipped": s.skipped,
                }
                for s in dag_result.stages
            ],
        }
        reporter_stage = next(
            (s for s in reversed(dag_result.stages) if "report" in s.stage and s.status == "ok"),
            None,
        )
        if reporter_stage:
            report["final_report"] = reporter_stage.output
        return report
