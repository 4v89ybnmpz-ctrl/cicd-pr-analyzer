"""
执行追踪器 — 全链路追踪
每次分析任务生成全局唯一 trace_id，贯穿所有 Agent
支持: 追踪链、耗时分析、token 消耗汇总、JSON 导出
"""
import json
import logging
import time
import uuid
import threading
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class TraceSpan:
    """追踪片段"""
    span_id: str
    trace_id: str
    agent_name: str
    action: str
    start_time: float = field(default_factory=time.time)
    end_time: float = 0.0
    duration_ms: float = 0.0
    status: str = "running"
    input_tokens: int = 0
    output_tokens: int = 0
    tool_calls: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

    def finish(self, status: str = "ok", error: str = None):
        """完成 span"""
        self.end_time = time.time()
        self.duration_ms = round((self.end_time - self.start_time) * 1000, 2)
        self.status = status
        if error:
            self.error = error
            self.status = "error"


@dataclass
class Trace:
    """完整追踪链"""
    trace_id: str
    owner: str
    repo: str
    mode: str = "orchestrator"
    started_at: float = field(default_factory=time.time)
    completed_at: float = 0.0
    total_duration_ms: float = 0.0
    status: str = "running"
    spans: List[TraceSpan] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        return sum(s.input_tokens + s.output_tokens for s in self.spans)

    @property
    def total_tool_calls(self) -> int:
        return sum(s.tool_calls for s in self.spans)

    def finish(self, status: str = "ok"):
        self.completed_at = time.time()
        self.total_duration_ms = round((self.completed_at - self.started_at) * 1000, 2)
        self.status = status


class TraceManager:
    """
    追踪管理器

    功能:
    - 创建 trace: 每次分析任务一个全局 trace_id
    - 创建 span: 每个 Agent 调用一个 span
    - 汇总统计: 总耗时、token 消耗、Agent 调用链
    - 导出: JSON 格式导出完整追踪链
    """

    def __init__(self, max_traces: int = 100):
        self._traces: Dict[str, Trace] = {}
        self._active_traces: Dict[str, str] = {}  # thread_id → trace_id
        self._lock = threading.Lock()
        self._max_traces = max_traces

    def start_trace(self, owner: str, repo: str,
                    mode: str = "orchestrator",
                    metadata: Dict[str, Any] = None) -> str:
        """创建新追踪"""
        trace_id = f"trace_{uuid.uuid4().hex[:12]}"

        trace = Trace(
            trace_id=trace_id,
            owner=owner,
            repo=repo,
            mode=mode,
            metadata=metadata or {},
        )

        with self._lock:
            self._traces[trace_id] = trace
            self._active_traces[threading.current_thread().ident] = trace_id

            # 超过上限时清理最旧的
            if len(self._traces) > self._max_traces:
                oldest_key = min(self._traces, key=lambda k: self._traces[k].started_at)
                del self._traces[oldest_key]

        logger.info(f"[Trace] 开始: {trace_id} ({owner}/{repo}, mode={mode})")
        return trace_id

    def start_span(self, trace_id: str, agent_name: str,
                   action: str = "run",
                   metadata: Dict[str, Any] = None) -> str:
        """创建追踪片段"""
        span_id = f"span_{uuid.uuid4().hex[:8]}"

        span = TraceSpan(
            span_id=span_id,
            trace_id=trace_id,
            agent_name=agent_name,
            action=action,
            metadata=metadata or {},
        )

        with self._lock:
            trace = self._traces.get(trace_id)
            if trace:
                trace.spans.append(span)

        return span_id

    def finish_span(self, trace_id: str, span_id: str,
                    status: str = "ok", error: str = None,
                    input_tokens: int = 0, output_tokens: int = 0,
                    tool_calls: int = 0):
        """完成追踪片段"""
        with self._lock:
            trace = self._traces.get(trace_id)
            if not trace:
                return

            for span in trace.spans:
                if span.span_id == span_id:
                    span.input_tokens = input_tokens
                    span.output_tokens = output_tokens
                    span.tool_calls = tool_calls
                    span.finish(status=status, error=error)
                    break

    def finish_trace(self, trace_id: str, status: str = "ok"):
        """完成追踪"""
        with self._lock:
            trace = self._traces.get(trace_id)
            if trace:
                trace.finish(status=status)

            self._active_traces.pop(threading.current_thread().ident, None)

        logger.info(
            f"[Trace] 完成: {trace_id} "
            f"(耗时={trace.total_duration_ms:.0f}ms, "
            f"tokens={trace.total_tokens}, "
            f"spans={len(trace.spans)})"
        )

    def get_current_trace_id(self) -> Optional[str]:
        """获取当前线程的 trace_id"""
        with self._lock:
            return self._active_traces.get(threading.current_thread().ident)

    def get_trace(self, trace_id: str) -> Optional[Dict[str, Any]]:
        """获取追踪详情"""
        with self._lock:
            trace = self._traces.get(trace_id)
            if not trace:
                return None

            return self._trace_to_dict(trace)

    def list_traces(self, limit: int = 20) -> List[Dict[str, Any]]:
        """列出所有追踪"""
        with self._lock:
            traces = sorted(
                self._traces.values(),
                key=lambda t: t.started_at,
                reverse=True,
            )[:limit]
            return [
                {
                    "trace_id": t.trace_id,
                    "owner": t.owner,
                    "repo": t.repo,
                    "mode": t.mode,
                    "status": t.status,
                    "total_duration_ms": t.total_duration_ms,
                    "total_tokens": t.total_tokens,
                    "span_count": len(t.spans),
                    "started_at": t.started_at,
                }
                for t in traces
            ]

    def get_project_traces(self, owner: str, repo: str,
                           limit: int = 10) -> List[Dict[str, Any]]:
        """获取项目的追踪历史"""
        with self._lock:
            traces = [
                t for t in self._traces.values()
                if t.owner == owner and t.repo == repo
            ]
            traces.sort(key=lambda t: t.started_at, reverse=True)
            return [self._trace_to_dict(t) for t in traces[:limit]]

    def _trace_to_dict(self, trace: Trace) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "trace_id": trace.trace_id,
            "owner": trace.owner,
            "repo": trace.repo,
            "mode": trace.mode,
            "status": trace.status,
            "started_at": trace.started_at,
            "completed_at": trace.completed_at,
            "total_duration_ms": trace.total_duration_ms,
            "total_tokens": trace.total_tokens,
            "total_tool_calls": trace.total_tool_calls,
            "spans": [
                {
                    "span_id": s.span_id,
                    "agent": s.agent_name,
                    "action": s.action,
                    "duration_ms": s.duration_ms,
                    "status": s.status,
                    "tokens": s.input_tokens + s.output_tokens,
                    "tool_calls": s.tool_calls,
                    "error": s.error,
                }
                for s in trace.spans
            ],
            "metadata": trace.metadata,
        }

    def export_trace(self, trace_id: str) -> Optional[str]:
        """导出追踪为 JSON"""
        data = self.get_trace(trace_id)
        if data:
            return json.dumps(data, ensure_ascii=False, indent=2)
        return None

    def summary(self) -> Dict[str, Any]:
        """追踪管理器摘要"""
        with self._lock:
            total_traces = len(self._traces)
            completed = [t for t in self._traces.values() if t.status != "running"]
            failed = [t for t in self._traces.values() if t.status == "error"]

            durations = [t.total_duration_ms for t in completed if t.total_duration_ms > 0]
            tokens = [t.total_tokens for t in self._traces.values()]

            return {
                "total_traces": total_traces,
                "completed": len(completed),
                "failed": len(failed),
                "avg_duration_ms": round(sum(durations) / len(durations), 2) if durations else 0,
                "total_tokens_consumed": sum(tokens),
            }

    def clear(self):
        """清空追踪"""
        with self._lock:
            self._traces.clear()
            self._active_traces.clear()


# 全局单例
trace_manager = TraceManager()
