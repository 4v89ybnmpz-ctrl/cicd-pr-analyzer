"""
CI/CD 结构化数据模型
统一各解析器的输出格式，为数据持久化和统计分析提供标准 Schema
"""
from enum import Enum
from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field, field_validator


class BuildStatus(str, Enum):
    """构建状态枚举"""
    SUCCESS = "success"
    FAILED = "failed"
    PENDING = "pending"
    RUNNING = "running"
    QUEUED = "queued"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"


class TimeGranularity(str, Enum):
    """统计时间粒度"""
    DAY = "day"
    WEEK = "week"
    MONTH = "month"


class TestResult(BaseModel):
    """测试结果"""
    passed: Optional[int] = Field(None, description="通过数")
    failed: Optional[int] = Field(None, description="失败数")
    skipped: Optional[int] = Field(None, description="跳过数")
    total: Optional[int] = Field(None, description="总数")


class CoverageInfo(BaseModel):
    """覆盖率信息"""
    percentage: Optional[float] = Field(None, description="覆盖率百分比")
    covered_lines: Optional[int] = Field(None, description="覆盖行数")
    total_lines: Optional[int] = Field(None, description="总行数")


class CheckResult(BaseModel):
    """检查结果（如 GitHub Checks）"""
    passed: Optional[int] = Field(None, description="通过数")
    failed: Optional[int] = Field(None, description="失败数")
    skipped: Optional[int] = Field(None, description="跳过数")


class CICDResult(BaseModel):
    """
    CI/CD 单条解析结果 - 标准化模型
    统一各解析器（rust-bors/nvidia-cccl/github-actions/generic 等）的输出格式
    """
    # 来源信息
    comment_id: Optional[str] = Field(None, description="原始评论 ID")
    owner: str = Field(..., description="仓库所有者")
    repo: str = Field(..., description="仓库名")
    pr_number: Optional[int] = Field(None, description="PR 编号")
    user: Optional[str] = Field(None, description="评论发布者")

    # 解析信息
    parser_name: str = Field(..., description="解析器名称 (rust-bors/nvidia-cccl/github-actions/generic 等)")
    build_status: BuildStatus = Field(BuildStatus.UNKNOWN, description="构建状态")
    build_type: Optional[str] = Field(None, description="构建类型 (try/test/approved 等)")

    # 核心指标
    duration_seconds: Optional[int] = Field(None, description="构建耗时（秒）")
    test_results: Optional[TestResult] = Field(None, description="测试结果")
    coverage: Optional[CoverageInfo] = Field(None, description="覆盖率信息")
    checks: Optional[CheckResult] = Field(None, description="检查结果")

    # NVIDIA CCCL 特有字段
    pass_rate: Optional[float] = Field(None, description="通过率 (0-100)")
    pass_count: Optional[int] = Field(None, description="通过数")
    hits_rate: Optional[float] = Field(None, description="命中命中率 (0-100)")
    hits_count: Optional[int] = Field(None, description="命中数")

    # Rust Bors 特有字段
    commit: Optional[str] = Field(None, description="Commit hash")
    merge_commit: Optional[str] = Field(None, description="Merge commit hash")
    approver: Optional[str] = Field(None, description="批准人")
    failed_jobs: Optional[List[str]] = Field(None, description="失败的 job 列表")

    # 通用字段
    url: Optional[str] = Field(None, description="CI/CD 详情 URL")
    details: Optional[List[str]] = Field(None, description="详细信息列表")

    # 时间信息
    comment_created_at: Optional[str] = Field(None, description="评论创建时间（原始字符串）")
    analyzed_at: Optional[datetime] = Field(None, description="分析时间")

    # 原始数据保留
    raw_parsed: Optional[Dict[str, Any]] = Field(None, description="解析器原始输出（兼容用）")

    @field_validator('build_status', mode='before')
    @classmethod
    def normalize_status(cls, v):
        """标准化构建状态字符串"""
        if isinstance(v, str):
            mapping = {
                'succeeded': 'success',
                'success': 'success',
                'failed': 'failed',
                'failure': 'failed',
                'pending': 'pending',
                'running': 'running',
                'in_progress': 'running',
                'queued': 'queued',
                'cancelled': 'cancelled',
                'unapproved': 'cancelled',
            }
            return mapping.get(v.lower(), 'unknown')
        return v

    def to_db_dict(self) -> Dict[str, Any]:
        """转换为数据库存储格式（排除 None 值）"""
        data = self.model_dump(exclude_none=True)
        if self.analyzed_at:
            data['analyzed_at'] = self.analyzed_at.isoformat()
        return data


class CICDResultSummary(BaseModel):
    """
    CI/CD 结果汇总统计
    用于展示一组 CI/CD 结果的基本统计信息
    """
    total: int = Field(0, description="总数")
    success_count: int = Field(0, description="成功数")
    failed_count: int = Field(0, description="失败数")
    pending_count: int = Field(0, description="等待中数")
    running_count: int = Field(0, description="运行中数")
    cancelled_count: int = Field(0, description="已取消数")
    unknown_count: int = Field(0, description="未知状态数")

    success_rate: Optional[float] = Field(None, description="成功率 (0-100)")
    failure_rate: Optional[float] = Field(None, description="失败率 (0-100)")

    avg_duration_seconds: Optional[float] = Field(None, description="平均耗时（秒）")
    median_duration_seconds: Optional[float] = Field(None, description="中位耗时（秒）")
    p90_duration_seconds: Optional[float] = Field(None, description="P90 耗时（秒）")
    p95_duration_seconds: Optional[float] = Field(None, description="P95 耗时（秒）")

    avg_coverage: Optional[float] = Field(None, description="平均覆盖率")

    by_parser: Dict[str, int] = Field(default_factory=dict, description="按解析器统计")
    by_status: Dict[str, int] = Field(default_factory=dict, description="按状态统计")

    def compute_rates(self):
        """根据计数计算比率"""
        if self.total > 0:
            self.success_rate = round(self.success_count / self.total * 100, 2)
            self.failure_rate = round(self.failed_count / self.total * 100, 2)


class CICDTrendPoint(BaseModel):
    """CI/CD 趋势数据点"""
    period: str = Field(..., description="时间段标识 (如 2026-05-18 或 2026-W20)")
    total: int = Field(0, description="总构建数")
    success_count: int = Field(0, description="成功数")
    failed_count: int = Field(0, description="失败数")
    success_rate: Optional[float] = Field(None, description="成功率")
    avg_duration_seconds: Optional[float] = Field(None, description="平均耗时")
    avg_coverage: Optional[float] = Field(None, description="平均覆盖率")


class CICDFailureAnalysis(BaseModel):
    """CI/CD 失败分析"""
    total_failures: int = Field(0, description="总失败次数")
    top_failed_jobs: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="高频失败 job，格式 [{name: str, count: int}]"
    )
    top_failed_parsers: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="失败最多的解析器类型"
    )
    avg_recovery_time_seconds: Optional[float] = Field(None, description="平均修复时间 MTTR（秒）")


class CICDInsight(BaseModel):
    """
    CI/CD 工程能力洞察项
    包含指标值、评级和改进建议
    """
    name: str = Field(..., description="洞察项名称")
    value: Any = Field(..., description="指标值")
    grade: Optional[str] = Field(None, description="评级 (A/B/C/D/F)")
    description: Optional[str] = Field(None, description="说明")
    suggestion: Optional[str] = Field(None, description="改进建议")


class CICDReport(BaseModel):
    """
    项目级 CI/CD 工程能力洞察报告
    整合多维度分析结果，生成可读性强的报告
    """
    # 项目信息
    owner: str = Field(..., description="仓库所有者")
    repo: str = Field(..., description="仓库名")

    # 时间范围
    start_date: Optional[str] = Field(None, description="报告开始日期")
    end_date: Optional[str] = Field(None, description="报告结束日期")

    # 总览统计
    summary: Optional[CICDResultSummary] = Field(None, description="汇总统计")

    # 趋势数据
    trends: List[CICDTrendPoint] = Field(default_factory=list, description="趋势数据")

    # 失败分析
    failure_analysis: Optional[CICDFailureAnalysis] = Field(None, description="失败分析")

    # 工程能力洞察
    insights: List[CICDInsight] = Field(default_factory=list, description="洞察项列表")

    # 报告元信息
    generated_at: Optional[datetime] = Field(None, description="报告生成时间")
    data_source_count: int = Field(0, description="数据源条数")
