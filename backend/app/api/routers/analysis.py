"""
CI/CD 分析 API 路由
提供 CI/CD 工程能力洞察报告接口
"""
from fastapi import APIRouter, Query, HTTPException
import logging
from datetime import datetime, timedelta
from typing import Optional

from app.models.cicd_models import (
    CICDReport, CICDResultSummary, CICDInsight, TimeGranularity,
)
from app.models.responses import CICDAnalysisTriggerResponse, CICDTrendsResponse
from app.models.responses import ReviewQualityReport, ReviewQualityTrendsResponse

logger = logging.getLogger(__name__)


def register_analysis_routes(router: APIRouter, db, cache):
    """注册 CI/CD 分析路由"""

    @router.post("/analysis/cicd/analyze/{owner}/{repo}", tags=["CI/CD 分析"], response_model=CICDAnalysisTriggerResponse)
    async def analyze_cicd_comments(
        owner: str,
        repo: str,
        start_date: Optional[str] = Query(None, description="开始日期 (YYYY-MM-DD)"),
        end_date: Optional[str] = Query(None, description="结束日期 (YYYY-MM-DD)"),
    ):
        """
        触发 CI/CD 全量分析
        从 pr_comments 集合读取评论，通过 CICDExtractor 解析后存入 cicd_results 集合
        """
        if db is None or db.db is None:
            raise HTTPException(status_code=503, detail="数据库未连接")

        from app.analysis.cicd_extractor import CICDExtractor
        extractor = CICDExtractor()

        # 从 pr_comments 集合读取该项目的所有评论
        query = {"owner": owner, "repo": repo}
        try:
            comments_docs = await db.db['pr_comments'].find(query, {"_id": 0}).to_list(length=None)
        except Exception as e:
            logger.error(f"查询 pr_comments 失败: {e}")
            raise HTTPException(status_code=500, detail=f"查询评论数据失败: {e}")

        if not comments_docs:
            return {"message": "未找到评论数据", "owner": owner, "repo": repo, "analyzed": 0}

        # 展开评论：每个文档的 data 字段是评论列表
        all_comments = []
        for doc in comments_docs:
            pr_number = doc.get("pr_number")
            data = doc.get("data", [])
            if isinstance(data, list):
                for comment in data:
                    comment["_pr_number"] = pr_number
                    all_comments.append(comment)
            elif isinstance(data, dict):
                data["_pr_number"] = pr_number
                all_comments.append(data)

        # 结构化提取并存入数据库
        results = extractor.extract_batch_structured(all_comments, owner=owner, repo=repo)
        db_results = []
        for r in results:
            r_dict = r.to_db_dict()
            # 从评论中补充 pr_number
            for comment in all_comments:
                if str(comment.get('id')) == r.comment_id:
                    r_dict['pr_number'] = comment.get('_pr_number', r.pr_number)
                    break
            db_results.append(r_dict)

        save_result = await db.save_cicd_results_batch(db_results)

        return {
            "message": "CI/CD 分析完成",
            "owner": owner,
            "repo": repo,
            "total_comments": len(all_comments),
            "cicd_comments": len(results),
            "saved": save_result["saved"],
            "failed": save_result["failed"],
            "date_range": {"start": start_date, "end": end_date},
        }

    @router.get("/analysis/cicd/report/{owner}/{repo}", tags=["CI/CD 分析"])
    async def get_cicd_report(
        owner: str,
        repo: str,
        start_date: Optional[str] = Query(None, description="开始日期 (YYYY-MM-DD)"),
        end_date: Optional[str] = Query(None, description="结束日期 (YYYY-MM-DD)"),
    ):
        """获取项目级 CI/CD 工程能力洞察报告"""
        if db is None or db.db is None:
            raise HTTPException(status_code=503, detail="数据库未连接")

        # 默认最近30天
        if not end_date:
            end_date = datetime.now().strftime("%Y-%m-%d")
        if not start_date:
            start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")

        # 获取汇总统计
        summary_data = await db.get_cicd_summary_from_db(owner, repo, start_date, end_date)

        # 获取趋势数据
        trends = await db.get_cicd_trends_from_db(owner, repo, granularity="day",
                                            start_date=start_date, end_date=end_date)

        # 获取失败分析
        failure_analysis = await db.get_cicd_failure_analysis_from_db(owner, repo,
                                                                 start_date=start_date, end_date=end_date)

        # 构建洞察项
        insights = _build_insights(summary_data, failure_analysis)

        # 组装报告
        total = summary_data.get("total", 0)
        report = {
            "owner": owner,
            "repo": repo,
            "start_date": start_date,
            "end_date": end_date,
            "summary": summary_data,
            "trends": trends,
            "failure_analysis": failure_analysis,
            "insights": insights,
            "generated_at": datetime.now().isoformat(),
            "data_source_count": total,
        }

        return report

    @router.get("/analysis/cicd/stats/{owner}/{repo}", tags=["CI/CD 分析"])
    async def get_cicd_stats(
        owner: str,
        repo: str,
        start_date: Optional[str] = Query(None, description="开始日期"),
        end_date: Optional[str] = Query(None, description="结束日期"),
    ):
        """获取 CI/CD 统计数据"""
        if db is None or db.db is None:
            raise HTTPException(status_code=503, detail="数据库未连接")
        return await db.get_cicd_summary_from_db(owner, repo, start_date, end_date)

    @router.get("/analysis/cicd/trends/{owner}/{repo}", tags=["CI/CD 分析"], response_model=CICDTrendsResponse)
    async def get_cicd_trends(
        owner: str,
        repo: str,
        granularity: str = Query("day", description="时间粒度 day/week/month"),
        start_date: Optional[str] = Query(None, description="开始日期"),
        end_date: Optional[str] = Query(None, description="结束日期"),
    ):
        """获取 CI/CD 趋势数据"""
        if db is None or db.db is None:
            raise HTTPException(status_code=503, detail="数据库未连接")
        trends = await db.get_cicd_trends_from_db(owner, repo, granularity=granularity,
                                            start_date=start_date, end_date=end_date)
        return {"owner": owner, "repo": repo, "granularity": granularity, "trends": trends}

    @router.get("/analysis/cicd/results/{owner}/{repo}", tags=["CI/CD 分析"])
    async def query_cicd_results(
        owner: str,
        repo: str,
        pr_number: Optional[int] = Query(None, description="PR 编号"),
        build_status: Optional[str] = Query(None, description="构建状态"),
        parser_name: Optional[str] = Query(None, description="解析器名称"),
        start_date: Optional[str] = Query(None, description="开始日期"),
        end_date: Optional[str] = Query(None, description="结束日期"),
        page: int = Query(1, ge=1, description="页码"),
        size: int = Query(20, ge=1, le=100, description="每页数量"),
    ):
        """查询 CI/CD 结果（分页）"""
        if db is None or db.db is None:
            raise HTTPException(status_code=503, detail="数据库未连接")
        return await db.query_cicd_results(
            owner=owner, repo=repo,
            pr_number=pr_number, build_status=build_status, parser_name=parser_name,
            start_date=start_date, end_date=end_date,
            page=page, size=size,
        )

    # ====================
    # Review 质量评估
    # ====================

    @router.get("/analysis/review-quality/{owner}/{repo}", tags=["Review 质量评估"], response_model=ReviewQualityReport)
    async def get_review_quality_report(
        owner: str,
        repo: str,
        start_date: Optional[str] = Query(None, description="开始日期 (YYYY-MM-DD)"),
        end_date: Optional[str] = Query(None, description="结束日期 (YYYY-MM-DD)"),
        top_n: int = Query(10, ge=1, le=50, description="Top Reviewer 数量"),
    ):
        """
        获取 Review 质量评估报告
        包含覆盖率、延迟、深度、状态分布、Top Reviewer 和洞察项
        """
        if db is None or db.db is None:
            raise HTTPException(status_code=503, detail="数据库未连接")
        return await db.get_review_quality_report(owner, repo, start_date, end_date, top_n)

    @router.get("/analysis/review-quality/{owner}/{repo}/trends", tags=["Review 质量评估"], response_model=ReviewQualityTrendsResponse)
    async def get_review_quality_trends(
        owner: str,
        repo: str,
        granularity: str = Query("week", description="时间粒度 day/week/month"),
        start_date: Optional[str] = Query(None, description="开始日期 (YYYY-MM-DD)"),
        end_date: Optional[str] = Query(None, description="结束日期 (YYYY-MM-DD)"),
    ):
        """获取 Review 质量趋势数据"""
        if db is None or db.db is None:
            raise HTTPException(status_code=503, detail="数据库未连接")
        trends = await db.get_review_quality_trends(owner, repo, granularity, start_date, end_date)
        return {"owner": owner, "repo": repo, "granularity": granularity, "trends": trends}


def _build_insights(summary_data: dict, failure_analysis: dict) -> list:
    """根据统计数据构建洞察项"""
    insights = []
    total = summary_data.get("total", 0)
    if total == 0:
        return insights

    # 构建成功率洞察
    success_rate = summary_data.get("success_rate")
    if success_rate is not None:
        grade, suggestion = _grade_success_rate(success_rate)
        insights.append({
            "name": "构建成功率",
            "value": success_rate,
            "grade": grade,
            "description": f"共 {total} 次构建，成功率 {success_rate}%",
            "suggestion": suggestion,
        })

    # 耗时洞察
    avg_duration = summary_data.get("avg_duration_seconds")
    if avg_duration is not None:
        grade, suggestion = _grade_duration(avg_duration)
        insights.append({
            "name": "平均构建耗时",
            "value": avg_duration,
            "grade": grade,
            "description": f"平均耗时 {_format_duration(avg_duration)}",
            "suggestion": suggestion,
        })

    # 覆盖率洞察
    avg_coverage = summary_data.get("avg_coverage")
    if avg_coverage is not None:
        grade, suggestion = _grade_coverage(avg_coverage)
        insights.append({
            "name": "测试覆盖率",
            "value": avg_coverage,
            "grade": grade,
            "description": f"平均覆盖率 {avg_coverage}%",
            "suggestion": suggestion,
        })

    # 失败模式洞察
    top_jobs = failure_analysis.get("top_failed_jobs", [])
    if top_jobs:
        top_job = top_jobs[0]
        insights.append({
            "name": "最高频失败 Job",
            "value": top_job["name"],
            "grade": "D" if top_job["count"] > 5 else "C",
            "description": f"{top_job['name']} 失败 {top_job['count']} 次",
            "suggestion": "建议优先排查该 job 的失败原因",
        })

    return insights


def _grade_success_rate(rate: float) -> tuple:
    if rate >= 95:
        return "A", "构建稳定性优秀"
    elif rate >= 85:
        return "B", "建议关注偶发失败，排查 flaky test"
    elif rate >= 70:
        return "C", "失败率较高，建议加强 CI 代码审查"
    elif rate >= 50:
        return "D", "构建成功率较低，需要重点改善"
    else:
        return "F", "构建严重不稳定，建议暂停合并，集中修复"


def _grade_duration(seconds: float) -> tuple:
    if seconds <= 300:
        return "A", "构建速度优秀"
    elif seconds <= 900:
        return "B", "构建速度良好"
    elif seconds <= 1800:
        return "C", "构建偏慢，建议优化耗时较长的 job"
    elif seconds <= 3600:
        return "D", "构建很慢，建议并行化或拆分 pipeline"
    else:
        return "F", "构建极慢，需要紧急优化"


def _grade_coverage(coverage: float) -> tuple:
    if coverage >= 90:
        return "A", "覆盖率优秀"
    elif coverage >= 80:
        return "B", "覆盖率良好，可进一步提升"
    elif coverage >= 60:
        return "C", "覆盖率一般，建议补充核心模块测试"
    elif coverage >= 40:
        return "D", "覆盖率较低，需要加强测试"
    else:
        return "F", "覆盖率极低，测试严重不足"


def _format_duration(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.0f}s"
    elif seconds < 3600:
        return f"{seconds / 60:.1f}m"
    else:
        return f"{seconds / 3600:.1f}h"
