"""
Pydantic Response Models
统一管理所有 API 返回类型，实现类型安全 + 自动 OpenAPI 文档
"""
from typing import Any, Dict, Generic, List, Optional, TypeVar
from pydantic import BaseModel, Field


# ====================
# 泛型类型变量
# ====================
T = TypeVar("T")


# ====================
# 通用基础模型
# ====================

class TimestampMixin(BaseModel):
    """时间戳混入"""
    timestamp: str = Field(default="", description="ISO 格式时间戳")


class RootResponse(BaseModel):
    """根路径响应"""
    name: str
    version: str
    status: str
    message: str


class HealthResponse(BaseModel):
    """健康检查响应"""
    status: str
    version: str


class MessageResponse(TimestampMixin):
    """通用消息响应"""
    message: str


class ErrorResponse(BaseModel):
    """错误响应"""
    error: str
    detail: Optional[str] = None


# ====================
# 泛型包装模型
# ====================

class DataTimestampResponse(TimestampMixin, Generic[T]):
    """数据 + 时间戳响应"""
    data: T


class SourceDataResponse(TimestampMixin, Generic[T]):
    """来源 + 数据响应（缓存/API）"""
    source: str
    data: T


class PaginatedResponse(TimestampMixin, Generic[T]):
    """分页响应"""
    data: List[T]
    total: int
    page: int
    size: int
    total_pages: int


class PaginatedSearchResponse(PaginatedResponse[T], Generic[T]):
    """分页搜索响应（含关键词）"""
    keyword: Optional[str] = None


# ====================
# GitHub PR 子模型
# ====================

class PRItem(BaseModel):
    """单条 PR 信息"""
    number: int
    title: str
    user: Optional[str] = None
    state: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    url: Optional[str] = None


class PRListResult(BaseModel):
    """PR 列表结果"""
    owner: str
    repo: str
    prs: List[PRItem]
    total: int
    error: Optional[str] = None


class CommentItem(BaseModel):
    """评论条目"""
    id: Optional[int] = None
    user: Optional[str] = None
    user_id: Optional[int] = None
    user_type: Optional[str] = None
    avatar_url: Optional[str] = None
    is_bot: bool = False
    author_association: Optional[str] = None
    body: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    url: Optional[str] = None
    reactions: int = 0


class PRCommentsResult(BaseModel):
    """PR 评论结果"""
    owner: str
    repo: str
    pr_number: int
    comments: List[CommentItem]
    total: int
    error: Optional[str] = None


class TimelineEventItem(BaseModel):
    """时间线事件条目"""
    id: Optional[int] = None
    event: Optional[str] = None
    actor: Optional[str] = None
    created_at: Optional[str] = None
    url: Optional[str] = None


class PRTimelineResult(BaseModel):
    """PR 时间线结果"""
    owner: str
    repo: str
    pr_number: int
    events: List[TimelineEventItem]
    total: int
    error: Optional[str] = None


class PRUser(BaseModel):
    """PR 用户信息"""
    login: Optional[str] = None
    avatar_url: Optional[str] = None
    type: Optional[str] = None


class PRLabel(BaseModel):
    """PR 标签"""
    name: str
    color: str


class PRBranch(BaseModel):
    """PR 分支信息"""
    ref: Optional[str] = None
    sha: Optional[str] = None
    label: Optional[str] = None


class PRMilestone(BaseModel):
    """PR 里程碑"""
    number: int
    title: str
    state: str
    due_on: Optional[str] = None


class PRDetail(BaseModel):
    """PR 详细信息"""
    number: Optional[int] = None
    title: Optional[str] = None
    body: Optional[str] = None
    state: Optional[str] = None
    draft: bool = False
    locked: bool = False
    user: Optional[PRUser] = None
    labels: List[PRLabel] = []
    assignees: List[PRUser] = []
    requested_reviewers: List[PRUser] = []
    milestone: Optional[PRMilestone] = None
    head: Optional[PRBranch] = None
    base: Optional[PRBranch] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    closed_at: Optional[str] = None
    merged_at: Optional[str] = None
    mergeable: Optional[bool] = None
    mergeable_state: Optional[str] = None
    merged: bool = False
    merge_commit_sha: Optional[str] = None
    commits: Optional[int] = None
    additions: Optional[int] = None
    deletions: Optional[int] = None
    changed_files: Optional[int] = None
    comments: Optional[int] = None
    review_comments: Optional[int] = None
    url: Optional[str] = None
    api_url: Optional[str] = None


class PRDetailResult(BaseModel):
    """PR 详情获取结果"""
    owner: str
    repo: str
    pr_number: int
    detail: PRDetail = Field(default_factory=PRDetail)
    error: Optional[str] = None


class ReviewItem(BaseModel):
    """Review 条目"""
    id: Optional[int] = None
    review_id: Optional[int] = None
    pr_number: Optional[int] = None
    user: Optional[str] = None
    user_id: Optional[int] = None
    user_type: Optional[str] = None
    avatar_url: Optional[str] = None
    state: Optional[str] = None
    body: Optional[str] = None
    submitted_at: Optional[str] = None
    commit_id: Optional[str] = None
    author_association: Optional[str] = None
    url: Optional[str] = None


class PRReviewsResult(BaseModel):
    """PR Reviews 结果"""
    owner: str
    repo: str
    pr_number: int
    reviews: List[ReviewItem]
    total: int
    error: Optional[str] = None


class CommitItem(BaseModel):
    """Commit 条目"""
    sha: str = ""
    message: str = ""
    author_name: str = ""
    author_email: str = ""
    author_date: str = ""
    committer_name: str = ""
    committer_date: str = ""
    url: str = ""
    verified: bool = False
    additions: int = 0
    deletions: int = 0
    total_changes: int = 0
    files_changed: int = 0


class PRCommitsResult(BaseModel):
    """PR Commits 结果"""
    owner: str
    repo: str
    pr_number: int
    commits: List[CommitItem]
    total: int
    error: Optional[str] = None


# ====================
# GitHub 路由级 Response 模型
# ====================

class MultiPRCollectionResponse(TimestampMixin):
    """多 PR 并发获取响应"""
    owner: str
    repo: str
    results: List[Dict[str, Any]]
    total_prs: int
    success_count: int
    failed_count: int


class BatchProjectsResponse(TimestampMixin):
    """多项目批量获取响应"""
    results: List[PRListResult]
    total_projects: int
    success_projects: int
    failed_projects: int
    total_prs: int


class BatchPRDetailResponse(TimestampMixin):
    """批量 PR 详情响应"""
    data: Optional[Dict[str, Any]] = None


class TokenPoolInfo(BaseModel):
    """Token 池信息"""
    total_tokens: int
    current_index: int


class TokenPoolResponse(TimestampMixin):
    """Token 池响应"""
    token_pool: TokenPoolInfo


# ====================
# 数据库查询 Response 模型
# ====================

class DatabaseStats(BaseModel):
    """数据库统计"""
    database: Optional[str] = None
    pr_data_count: int = 0
    pr_details_count: int = 0
    pr_comments_count: int = 0
    issues_count: int = 0
    issue_timelines_count: int = 0
    user_profiles_count: int = 0
    user_contributed_repos_count: int = 0
    task_count: int = 0
    status: str = "connected"


class DatabaseStatsResponse(TimestampMixin):
    """数据库统计响应"""
    stats: DatabaseStats


class RepoCountItem(BaseModel):
    """仓库计数项"""
    id: Optional[Dict[str, str]] = Field(None, alias="_id")
    count: int


class StateCountItem(BaseModel):
    """状态计数项"""
    id: Optional[str] = Field(None, alias="_id")
    count: int


class DatabaseAggregateData(BaseModel):
    """聚合统计数据"""
    pr_data_count: int = 0
    pr_comments_count: int = 0
    pr_timeline_count: int = 0
    pr_details_count: int = 0
    by_repo: List[Dict[str, Any]] = []
    by_state: List[Dict[str, Any]] = []


class DatabaseAggregateResponse(TimestampMixin):
    """聚合统计响应"""
    stats: DatabaseAggregateData


class DeleteResponse(TimestampMixin):
    """删除响应"""
    message: str
    owner: Optional[str] = None
    repo: Optional[str] = None


class DataListResponse(TimestampMixin, Generic[T]):
    """数据列表响应"""
    data: List[T]
    total: int


# ====================
# 任务管理 Response 模型
# ====================

class TaskInfo(BaseModel):
    """任务信息"""
    task_id: str
    status: str
    progress: float
    total: int
    current: int
    message: str
    created_at: float
    updated_at: float


class TaskListResponse(TimestampMixin):
    """任务列表响应"""
    tasks: List[TaskInfo]
    total: int


class SingleTaskResponse(TimestampMixin):
    """单个任务响应"""
    task: TaskInfo


class TaskCreateResponse(TimestampMixin):
    """任务创建响应"""
    task_id: str
    status: str
    message: str


# ====================
# 配置和缓存 Response 模型
# ====================

class ConfigInfo(BaseModel):
    """配置信息"""
    app_name: str
    version: str
    tokens_count: int
    cache_ttl: int
    api_settings: Dict[str, Any]


class ConfigResponse(TimestampMixin):
    """配置响应"""
    config: ConfigInfo


class ConfigReloadResponse(TimestampMixin):
    """配置重载响应"""
    message: str
    config: ConfigInfo


class CacheStats(BaseModel):
    """缓存统计"""
    total: int
    valid: int
    expired: int
    default_ttl: int


class CacheStatsResponse(TimestampMixin):
    """缓存统计响应"""
    cache_stats: CacheStats


# ====================
# CI/CD 分析 Response 模型
# ====================

class CICDAnalysisTriggerResponse(BaseModel):
    """CI/CD 分析触发响应"""
    message: str
    owner: str
    repo: str
    total_comments: int = 0
    cicd_comments: int = 0
    saved: int = 0
    failed: int = 0
    date_range: Optional[Dict[str, Optional[str]]] = None
    analyzed: Optional[int] = None


class CICDTrendsResponse(TimestampMixin):
    """CI/CD 趋势响应"""
    owner: str
    repo: str
    granularity: str
    trends: List[Dict[str, Any]]


# ====================
# GitCode Response 模型
# ====================

class GitCodeServiceResponse(TimestampMixin):
    """GitCode 服务结果响应（通用包装）"""
    class Config:
        extra = "allow"


class GitCodeMultiMRResponse(TimestampMixin):
    """GitCode 多 MR 响应"""
    owner: str
    repo: str
    results: List[Dict[str, Any]]
    total_mrs: int


# ====================
# AtomGit Response 模型
# ====================

class AtomGitPRSummary(BaseModel):
    """AtomGit PR 摘要"""
    pull_number: int
    title: str
    state: str
    comment_count: int = 0
    bot_comment_count: int = 0


class AtomGitBatchCommentsResponse(TimestampMixin):
    """AtomGit 批量评论响应"""
    owner: str
    repo: str
    total_prs: int = 0
    total_comments: int = 0
    bot_comments: int = 0
    saved_to_db: int = 0
    results: List[AtomGitPRSummary] = []


# ====================
# 浏览器 Response 模型
# ====================

class BrowserStatus(BaseModel):
    """浏览器状态"""
    is_running: bool
    browser_type: str = ""
    headless: bool = True
    pages: List[str] = []
    page_count: int = 0


class InterceptorStats(BaseModel):
    """拦截器统计"""
    is_active: bool
    total_captured: int = 0
    pending_count: int = 0
    status_counts: Dict[str, int] = {}
    url_patterns: List[str] = []


class PlatformInfo(BaseModel):
    """平台信息"""
    name: str
    display_name: str
    base_url: str
    login_url: str
    has_cookies: bool = False
    login_status: Optional[str] = None


class BrowserStatusResponse(TimestampMixin):
    """浏览器状态响应"""
    is_initialized: bool
    browser: Optional[BrowserStatus] = None
    interceptor: Optional[InterceptorStats] = None
    platforms: List[PlatformInfo] = []
    extractors: List[str] = []


class BrowserActionResponse(TimestampMixin):
    """浏览器操作响应"""
    status: str
    browser: Optional[BrowserStatus] = None


class CapturedRequest(BaseModel):
    """捕获的请求"""
    url: str
    method: str
    status: Optional[int] = None
    resource_type: Optional[str] = None
    timestamp: Optional[str] = None
    duration_ms: Optional[float] = None
    response_body: Optional[Any] = None
    response_body_text: Optional[str] = None
    response_body_size: Optional[int] = None
    post_data: Optional[str] = None


class CapturedRequestsResponse(TimestampMixin):
    """捕获请求响应"""
    total: int
    requests: List[CapturedRequest]


class APIResponsesResponse(TimestampMixin):
    """API 响应列表"""
    total: int
    responses: List[CapturedRequest]


# ====================
# Review 质量评估 Response 模型
# ====================

class ReviewCoverageMetrics(BaseModel):
    """Review 覆盖率指标"""
    total_prs: int = Field(0, description="PR 总数")
    prs_with_review: int = Field(0, description="有 review 的 PR 数")
    prs_without_review: int = Field(0, description="无 review 的 PR 数")
    coverage_rate: Optional[float] = Field(None, description="Review 覆盖率 (0-100)")
    avg_reviewers_per_pr: Optional[float] = Field(None, description="平均每个 PR 的 reviewer 数")


class ReviewDelayMetrics(BaseModel):
    """Review 延迟指标"""
    total_reviews: int = Field(0, description="Review 总数")
    avg_first_review_delay_hours: Optional[float] = Field(None, description="首次 review 平均延迟（小时）")
    median_first_review_delay_hours: Optional[float] = Field(None, description="首次 review 中位延迟（小时）")
    p90_first_review_delay_hours: Optional[float] = Field(None, description="首次 review P90 延迟（小时）")
    avg_review_delay_hours: Optional[float] = Field(None, description="所有 review 平均延迟（小时）")


class ReviewDepthMetrics(BaseModel):
    """Review 深度指标"""
    total_reviews: int = Field(0, description="Review 总数")
    avg_body_length: Optional[float] = Field(None, description="Review body 平均字符数")
    reviews_with_body: int = Field(0, description="有评论内容的 review 数")
    reviews_without_body: int = Field(0, description="无评论内容的 review 数（仅 APPROVED/PENDING）")
    body_rate: Optional[float] = Field(None, description="有评论内容的 review 占比 (0-100)")


class ReviewStateDistribution(BaseModel):
    """Review 状态分布"""
    approved: int = Field(0, description="APPROVED 数")
    changes_requested: int = Field(0, description="CHANGES_REQUESTED 数")
    commented: int = Field(0, description="COMMENTED 数")
    dismissed: int = Field(0, description="DISMISSED 数")
    pending: int = Field(0, description="PENDING 数")


class ReviewerStats(BaseModel):
    """单个 Reviewer 统计"""
    user: str = Field(..., description="Reviewer 用户名")
    review_count: int = Field(0, description="Review 总数")
    approved_count: int = Field(0, description="APPROVED 数")
    changes_requested_count: int = Field(0, description="CHANGES_REQUESTED 数")
    avg_body_length: Optional[float] = Field(None, description="平均评论长度")
    avg_delay_hours: Optional[float] = Field(None, description="平均响应延迟（小时）")


class ReviewQualityReport(BaseModel):
    """Review 质量评估报告"""
    owner: str = Field(..., description="仓库所有者")
    repo: str = Field(..., description="仓库名")
    start_date: Optional[str] = Field(None, description="开始日期")
    end_date: Optional[str] = Field(None, description="结束日期")
    coverage: Optional[ReviewCoverageMetrics] = Field(None, description="覆盖率指标")
    delay: Optional[ReviewDelayMetrics] = Field(None, description="延迟指标")
    depth: Optional[ReviewDepthMetrics] = Field(None, description="深度指标")
    state_distribution: Optional[ReviewStateDistribution] = Field(None, description="状态分布")
    top_reviewers: List[ReviewerStats] = Field(default_factory=list, description="Top Reviewer 列表")
    insights: List[Dict[str, Any]] = Field(default_factory=list, description="洞察项")
    generated_at: Optional[str] = Field(None, description="报告生成时间")


class ReviewQualityTrendsResponse(TimestampMixin):
    """Review 质量趋势响应"""
    owner: str
    repo: str
    granularity: str
    trends: List[Dict[str, Any]]
