"""
数据导出接口路由
"""
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from datetime import datetime
import logging
import os

logger = logging.getLogger(__name__)


def register_export_routes(router: APIRouter, db, exporter):
    """注册数据导出路由"""

    @router.get("/export/report/{owner}/{repo}", tags=["数据导出"])
    async def export_report(
        owner: str,
        repo: str,
        format: str = Query("pdf", description="导出格式: pdf | excel"),
        report_type: str = Query("all", description="报告类型: cicd | review_quality | project_health | trend_alerts | all"),
        start_date: str = Query(None, description="开始日期 YYYY-MM-DD"),
        end_date: str = Query(None, description="结束日期 YYYY-MM-DD"),
    ):
        """导出分析报告（PDF/Excel）"""
        if db is None:
            raise HTTPException(status_code=503, detail="数据库未连接")

        try:
            # 收集报告数据
            report_data = await _gather_report_data(db, owner, repo, report_type, start_date, end_date)
            report_data["generated_at"] = datetime.now().isoformat()

            date_range = (start_date, end_date) if start_date and end_date else None

            if format == "pdf":
                filepath = await exporter.export_pdf(owner, repo, report_type, report_data, date_range)
                filename = os.path.basename(filepath)
                return FileResponse(
                    filepath,
                    media_type="application/pdf",
                    filename=f"report_{owner}_{repo}_{report_type}.pdf",
                )
            elif format == "excel":
                # 报告导出为 Excel：每个维度一个 Sheet
                sheets_config = _build_report_sheets(report_type, report_data, owner, repo)
                filepath = await exporter.export_excel(owner, repo, sheets_config)
                return FileResponse(
                    filepath,
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    filename=f"report_{owner}_{repo}_{report_type}.xlsx",
                )
            else:
                raise HTTPException(status_code=400, detail=f"不支持的格式: {format}")
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            logger.error(f"导出报告失败: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/export/data/{owner}/{repo}", tags=["数据导出"])
    async def export_data(
        owner: str,
        repo: str,
        collection: str = Query("pr_data", description="数据集合: pr_data | pr_details | pr_comments | pr_reviews | pr_commits | issues | cicd_results"),
        format: str = Query("excel", description="导出格式: excel | csv"),
        fields: str = Query(None, description="导出字段，逗号分隔"),
    ):
        """导出原始数据（Excel/CSV）"""
        if db is None:
            raise HTTPException(status_code=503, detail="数据库未连接")

        # 合法集合白名单
        valid_collections = {
            "pr_data", "pr_details", "pr_comments", "pr_reviews",
            "pr_commits", "pr_files", "pr_timeline", "issues",
            "issue_timelines", "cicd_results", "git_log_commits",
        }
        if collection not in valid_collections:
            raise HTTPException(status_code=400, detail=f"不支持的数据集合: {collection}")

        try:
            field_list = fields.split(",") if fields else None

            if format == "csv":
                filepath = await exporter.export_csv(owner, repo, collection, fields=field_list)
                return FileResponse(
                    filepath,
                    media_type="text/csv",
                    filename=f"{owner}_{repo}_{collection}.csv",
                )
            elif format == "excel":
                sheet_name_map = {
                    "pr_data": "PR 列表", "pr_details": "PR 详情", "pr_comments": "PR 评论",
                    "pr_reviews": "PR Reviews", "pr_commits": "PR Commits", "pr_files": "PR 变更文件",
                    "pr_timeline": "PR 时间线", "issues": "Issues", "issue_timelines": "Issue 时间线",
                    "cicd_results": "CI/CD 结果", "git_log_commits": "Git 提交",
                }
                sheets_config = [{
                    "name": sheet_name_map.get(collection, collection),
                    "collection": collection,
                    "fields": field_list,
                }]
                filepath = await exporter.export_excel(owner, repo, sheets_config)
                return FileResponse(
                    filepath,
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    filename=f"{owner}_{repo}_{collection}.xlsx",
                )
            else:
                raise HTTPException(status_code=400, detail=f"不支持的格式: {format}")
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            logger.error(f"导出数据失败: {e}")
            raise HTTPException(status_code=500, detail=str(e))


async def _gather_report_data(db, owner: str, repo: str, report_type: str,
                              start_date: str = None, end_date: str = None) -> dict:
    """收集报告数据"""
    data = {"owner": owner, "repo": repo}

    try:
        if report_type in ("project_health", "all"):
            health = await db.get_project_health_report(owner, repo)
            if "error" not in health:
                data["health"] = health

        if report_type in ("review_quality", "all"):
            review = await db.get_review_quality_report(owner, repo, start_date=start_date, end_date=end_date)
            if "error" not in review:
                data["review_quality"] = review

        if report_type in ("trend_alerts", "all"):
            alerts = await db.get_trend_alerts(owner, repo)
            if "error" not in alerts:
                data["trend_alerts"] = alerts

        if report_type in ("cicd", "all"):
            cicd = await db.query_cicd_results(owner, repo)
            if "error" not in cicd:
                data["cicd"] = cicd
    except Exception as e:
        logger.error(f"收集报告数据失败: {e}")

    return data


def _build_report_sheets(report_type: str, report_data: dict, owner: str, repo: str) -> list:
    """构建 Excel 导出的 Sheet 配置"""
    sheets = []

    if report_type in ("project_health", "all") and "health" in report_data:
        health = report_data["health"]
        sheets.append({
            "name": "项目健康度",
            "collection": "pr_data",
            "query": {"owner": owner, "repo": repo},
        })

    if report_type in ("review_quality", "all") and "review_quality" in report_data:
        sheets.append({
            "name": "Review 质量",
            "collection": "pr_reviews",
            "query": {"owner": owner, "repo": repo},
        })

    if report_type in ("trend_alerts", "all"):
        sheets.append({
            "name": "趋势预警",
            "collection": "pr_data",
            "query": {"owner": owner, "repo": repo},
        })

    # 默认至少一个 Sheet
    if not sheets:
        sheets.append({
            "name": "PR 数据",
            "collection": "pr_data",
            "query": {"owner": owner, "repo": repo},
        })

    return sheets
