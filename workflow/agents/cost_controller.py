"""
成本控制器 — Token 预算和 LLM 降级策略
控制多 Agent 系统的 AI 调用成本
"""
import json
import logging
import time
import threading
from typing import Dict, Any, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class TokenBudget:
    """Token 预算"""
    total_budget: int = 100000
    used_tokens: int = 0
    warning_threshold: float = 0.8
    hard_limit: float = 0.95
    started_at: float = field(default_factory=time.time)

    @property
    def remaining(self) -> int:
        return max(0, self.total_budget - self.used_tokens)

    @property
    def usage_ratio(self) -> float:
        return self.used_tokens / self.total_budget if self.total_budget > 0 else 0.0

    @property
    def is_exceeded(self) -> bool:
        return self.usage_ratio >= self.hard_limit

    @property
    def is_warning(self) -> bool:
        return self.usage_ratio >= self.warning_threshold


@dataclass
class LLMTierConfig:
    """LLM 分层配置"""
    tier_name: str
    model_name: str
    max_tokens_per_call: int
    cost_per_1k_input: float
    cost_per_1k_output: float


# 预定义 LLM 分级
LLM_TIERS = {
    "premium": LLMTierConfig("premium", "claude-sonnet-4-20250514", 4096, 0.003, 0.015),
    "standard": LLMTierConfig("standard", "claude-3-5-haiku-20241022", 2048, 0.001, 0.005),
    "economy": LLMTierConfig("economy", "claude-3-haiku-20240307", 1024, 0.00025, 0.00125),
}

# Agent 使用的 LLM 等级映射（高优先级 Agent 用高端模型）
AGENT_TIER_MAP = {
    "orchestrator": "premium",
    "analyst": "premium",
    "planner": "standard",
    "reporter": "standard",
    "collector": "economy",
    "validator": "economy",
}


class CostController:
    """
    成本控制器

    功能:
    - Token 预算: 设置总预算，跟踪消耗，超限告警
    - LLM 分层: 不同 Agent 使用不同等级的模型
    - 降级策略: 预算紧张时自动降级到更便宜的模型
    - 成本估算: 预估分析任务的总成本
    - 用量报告: 输出成本报告
    """

    def __init__(self, total_budget: int = 100000):
        self.budget = TokenBudget(total_budget=total_budget)
        self._agent_usage: Dict[str, Dict[str, int]] = {}
        self._lock = threading.Lock()
        self._current_tier_override: Optional[str] = None
        self._total_cost_usd: float = 0.0

    def set_budget(self, total: int):
        """设置总 Token 预算"""
        self.budget.total_budget = total
        logger.info(f"Token 预算设置为: {total}")

    def record_usage(self, agent_name: str, input_tokens: int, output_tokens: int) -> bool:
        """
        记录 Token 使用量
        返回: 是否还在预算内
        """
        total = input_tokens + output_tokens

        with self._lock:
            self.budget.used_tokens += total

            if agent_name not in self._agent_usage:
                self._agent_usage[agent_name] = {"input": 0, "output": 0, "calls": 0}
            self._agent_usage[agent_name]["input"] += input_tokens
            self._agent_usage[agent_name]["output"] += output_tokens
            self._agent_usage[agent_name]["calls"] += 1

            # 计算成本
            tier_name = AGENT_TIER_MAP.get(agent_name, "standard")
            tier = LLM_TIERS[tier_name]
            cost = (input_tokens / 1000 * tier.cost_per_1k_input +
                    output_tokens / 1000 * tier.cost_per_1k_output)
            self._total_cost_usd += cost

        if self.budget.is_warning and not self.budget.is_exceeded:
            logger.warning(
                f"Token 预算警告: {self.budget.usage_ratio:.1%} 已使用 "
                f"({self.budget.used_tokens}/{self.budget.total_budget})"
            )

        if self.budget.is_exceeded:
            logger.error(
                f"Token 预算超限! {self.budget.usage_ratio:.1%} 已使用"
            )
            return False

        return True

    def can_proceed(self, estimated_tokens: int = 0) -> bool:
        """检查是否可以继续执行"""
        if estimated_tokens > 0:
            return (self.budget.remaining - estimated_tokens) > 0
        return not self.budget.is_exceeded

    def get_recommended_tier(self, agent_name: str) -> str:
        """
        根据预算状态获取推荐的 LLM 等级
        预算充足时使用 Agent 默认等级
        预算紧张时自动降级
        """
        if self._current_tier_override:
            return self._current_tier_override

        default_tier = AGENT_TIER_MAP.get(agent_name, "standard")

        if self.budget.is_exceeded:
            return "economy"
        elif self.budget.usage_ratio > 0.8:
            # 超过 80% 时降一级
            tier_order = {"premium": "standard", "standard": "economy", "economy": "economy"}
            return tier_order.get(default_tier, "economy")

        return default_tier

    def set_tier_override(self, tier_name: str):
        """强制所有 Agent 使用指定等级"""
        if tier_name in LLM_TIERS:
            self._current_tier_override = tier_name
            logger.info(f"LLM 等级强制设为: {tier_name}")
        else:
            logger.warning(f"未知的 LLM 等级: {tier_name}")

    def clear_tier_override(self):
        """清除等级覆盖"""
        self._current_tier_override = None

    def estimate_cost(self, project_count: int = 1,
                      avg_pr_count: int = 100) -> Dict[str, Any]:
        """预估分析成本"""
        # 经验值: 每个项目大约消耗的 token 数
        base_tokens = 5000  # 基础开销（规划+调度+报告）
        per_pr_tokens = 200  # 每个 PR 的分析 token
        total_estimated = (base_tokens + per_pr_tokens * avg_pr_count) * project_count

        tier = LLM_TIERS["standard"]
        estimated_cost = total_estimated / 1000 * (tier.cost_per_1k_input + tier.cost_per_1k_output) / 2

        return {
            "estimated_tokens": total_estimated,
            "estimated_cost_usd": round(estimated_cost, 4),
            "budget_remaining": self.budget.remaining,
            "within_budget": total_estimated <= self.budget.remaining,
            "projects": project_count,
            "avg_pr_count": avg_pr_count,
        }

    def get_usage_report(self) -> Dict[str, Any]:
        """获取用量报告"""
        with self._lock:
            agent_reports = {}
            for name, usage in self._agent_usage.items():
                tier_name = AGENT_TIER_MAP.get(name, "standard")
                tier = LLM_TIERS[tier_name]
                cost = (usage["input"] / 1000 * tier.cost_per_1k_input +
                        usage["output"] / 1000 * tier.cost_per_1k_output)
                agent_reports[name] = {
                    "input_tokens": usage["input"],
                    "output_tokens": usage["output"],
                    "total_tokens": usage["input"] + usage["output"],
                    "api_calls": usage["calls"],
                    "tier": tier_name,
                    "estimated_cost_usd": round(cost, 4),
                }

            return {
                "budget": {
                    "total": self.budget.total_budget,
                    "used": self.budget.used_tokens,
                    "remaining": self.budget.remaining,
                    "usage_ratio": round(self.budget.usage_ratio, 4),
                    "is_warning": self.budget.is_warning,
                    "is_exceeded": self.budget.is_exceeded,
                },
                "total_cost_usd": round(self._total_cost_usd, 4),
                "agent_usage": agent_reports,
                "current_tier_override": self._current_tier_override,
            }

    def reset(self):
        """重置用量统计"""
        with self._lock:
            self.budget.used_tokens = 0
            self.budget.started_at = time.time()
            self._agent_usage.clear()
            self._total_cost_usd = 0.0
            self._current_tier_override = None


# 全局单例
cost_controller = CostController()
