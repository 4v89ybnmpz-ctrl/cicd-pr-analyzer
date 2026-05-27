"""
报告导出引擎
支持 PDF / Excel / CSV 三种格式的数据导出
"""
import os
import csv
import io
import time
import logging
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger(__name__)

# 导出文件暂存目录
EXPORT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "exports")


class ReportExporter:
    """报告导出器"""

    def __init__(self, db):
        self._db = db
        os.makedirs(EXPORT_DIR, exist_ok=True)

    async def export_csv(self, owner: str, repo: str, collection: str,
                         query: Dict = None, fields: List[str] = None) -> str:
        """导出 CSV 文件"""
        if self._db is None or self._db.db is None:
            raise RuntimeError("数据库未连接")

        self._cleanup_old_exports()

        query = query or {}
        if owner:
            query["owner"] = owner
        if repo:
            query["repo"] = repo

        docs = []
        cursor = self._db.db[collection].find(query, {"_id": 0})
        async for doc in cursor:
            docs.append(self._flatten_doc(doc))

        if not docs:
            raise ValueError("没有可导出的数据")

        # 如果未指定字段，使用第一个文档的所有键
        if not fields:
            fields = list(docs[0].keys())

        filename = f"{owner}_{repo}_{collection}_{int(time.time())}.csv"
        filepath = os.path.join(EXPORT_DIR, filename)

        with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            for doc in docs:
                # 将所有值转为字符串，处理嵌套对象
                row = {k: str(v) if v is not None else "" for k, v in doc.items() if k in fields}
                writer.writerow(row)

        logger.info(f"CSV 导出完成: {filename}, {len(docs)} 条记录")
        return filepath

    async def export_excel(self, owner: str, repo: str,
                           sheets_config: List[Dict]) -> str:
        """导出 Excel（多 Sheet）"""
        from openpyxl import Workbook

        if self._db is None or self._db.db is None:
            raise RuntimeError("数据库未连接")

        self._cleanup_old_exports()

        wb = Workbook()
        first_sheet = True

        for sheet_cfg in sheets_config:
            collection = sheet_cfg["collection"]
            query = dict(sheet_cfg.get("query", {}))
            if owner:
                query["owner"] = owner
            if repo:
                query["repo"] = repo
            sheet_fields = sheet_cfg.get("fields")
            sheet_name = sheet_cfg.get("name", collection)[:31]  # Excel Sheet 名称限制 31 字符

            docs = []
            cursor = self._db.db[collection].find(query, {"_id": 0})
            async for doc in cursor:
                docs.append(self._flatten_doc(doc))

            if first_sheet:
                ws = wb.active
                ws.title = sheet_name
                first_sheet = False
            else:
                ws = wb.create_sheet(title=sheet_name)

            if not docs:
                ws.append(["无数据"])
                continue

            fields = sheet_fields or list(docs[0].keys())
            ws.append(fields)

            for doc in docs:
                row = [str(doc.get(f, "")) if doc.get(f) is not None else "" for f in fields]
                ws.append(row)

            # 自动调整列宽
            for col_idx, field in enumerate(fields, 1):
                max_len = len(str(field))
                for doc in docs[:100]:
                    val = str(doc.get(field, ""))
                    max_len = max(max_len, min(len(val), 50))
                ws.column_dimensions[ws.cell(row=1, column=col_idx).column_letter].width = max_len + 2

        filename = f"{owner}_{repo}_data_{int(time.time())}.xlsx"
        filepath = os.path.join(EXPORT_DIR, filename)
        wb.save(filepath)

        logger.info(f"Excel 导出完成: {filename}")
        return filepath

    async def export_pdf(self, owner: str, repo: str, report_type: str,
                         report_data: Dict, date_range: Tuple[str, str] = None) -> str:
        """导出 PDF 报告"""
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.lib.colors import HexColor
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont

        self._cleanup_old_exports()

        filename = f"{owner}_{repo}_{report_type}_{int(time.time())}.pdf"
        filepath = os.path.join(EXPORT_DIR, filename)

        doc = SimpleDocTemplate(
            filepath, pagesize=A4,
            leftMargin=2 * cm, rightMargin=2 * cm, topMargin=2 * cm, bottomMargin=2 * cm,
        )
        styles = getSampleStyleSheet()

        # 尝试注册中文字体
        try:
            # macOS 系统字体
            font_path = "/System/Library/Fonts/PingFang.ttc"
            if os.path.exists(font_path):
                pdfmetrics.registerFont(TTFont("PingFang", font_path))
                cn_font = "PingFang"
            else:
                cn_font = "Helvetica"
        except Exception:
            cn_font = "Helvetica"

        # 自定义样式
        title_style = ParagraphStyle(
            "CNTitle", parent=styles["Title"],
            fontName=cn_font, fontSize=18, spaceAfter=12,
        )
        heading_style = ParagraphStyle(
            "CNHeading", parent=styles["Heading2"],
            fontName=cn_font, fontSize=14, spaceAfter=8, textColor=HexColor("#1890ff"),
        )
        body_style = ParagraphStyle(
            "CNBody", parent=styles["Normal"],
            fontName=cn_font, fontSize=10, spaceAfter=6,
        )

        story = []

        # 标题
        report_titles = {
            "cicd": "CI/CD 洞察报告",
            "review_quality": "Review 质量报告",
            "project_health": "项目健康度报告",
            "trend_alerts": "趋势预警报告",
            "all": "综合分析报告",
        }
        title = report_titles.get(report_type, "分析报告")
        story.append(Paragraph(f"{title} — {owner}/{repo}", title_style))

        date_info = ""
        if date_range and date_range[0] and date_range[1]:
            date_info = f"统计周期: {date_range[0]} ~ {date_range[1]}"
        story.append(Paragraph(date_info or f"生成时间: {report_data.get('generated_at', '')}", body_style))
        story.append(Spacer(1, 12))

        # 根据报告类型渲染不同内容
        if report_type == "project_health":
            self._build_pdf_health(story, report_data, heading_style, body_style, cn_font)
        elif report_type == "review_quality":
            self._build_pdf_review(story, report_data, heading_style, body_style, cn_font)
        elif report_type == "trend_alerts":
            self._build_pdf_alerts(story, report_data, heading_style, body_style, cn_font)
        else:
            # 通用渲染：遍历所有字段
            self._build_pdf_generic(story, report_data, heading_style, body_style, cn_font)

        doc.build(story)
        logger.info(f"PDF 导出完成: {filename}")
        return filepath

    def _build_pdf_generic(self, story, data, heading_style, body_style, cn_font):
        """通用 PDF 内容构建"""
        for key, value in data.items():
            if key in ("error", "generated_at"):
                continue
            story.append(Paragraph(str(key).replace("_", " ").title(), heading_style))
            if isinstance(value, dict):
                self._add_table(story, value, cn_font)
            elif isinstance(value, list) and value and isinstance(value[0], dict):
                self._add_list_table(story, value, cn_font)
            else:
                story.append(Paragraph(str(value), body_style))
            story.append(Spacer(1, 8))

    def _build_pdf_health(self, story, data, heading_style, body_style, cn_font):
        """项目健康度 PDF 内容"""
        story.append(Paragraph(f"总体评分: {data.get('overall_score', 'N/A')} 分 ({data.get('overall_grade', 'N/A')})", body_style))
        story.append(Spacer(1, 8))

        for dim in data.get("dimensions", []):
            story.append(Paragraph(f"{dim.get('name', '')}: {dim.get('score', 0)} 分 ({dim.get('grade', '')})", body_style))
            if dim.get("suggestion"):
                story.append(Paragraph(f"  建议: {dim['suggestion']}", body_style))
        story.append(Spacer(1, 8))

        insights = data.get("insights", [])
        if insights:
            story.append(Paragraph("洞察与建议", heading_style))
            for ins in insights:
                story.append(Paragraph(f"- {ins}", body_style))

    def _build_pdf_review(self, story, data, heading_style, body_style, cn_font):
        """Review 质量 PDF 内容"""
        metrics = data.get("summary", {})
        story.append(Paragraph("概览指标", heading_style))
        self._add_table(story, metrics, cn_font)
        story.append(Spacer(1, 8))

        reviewers = data.get("top_reviewers", [])
        if reviewers:
            story.append(Paragraph("Top Reviewers", heading_style))
            self._add_list_table(story, reviewers[:10], cn_font)

    def _build_pdf_alerts(self, story, data, heading_style, body_style, cn_font):
        """趋势预警 PDF 内容"""
        alerts = data.get("alerts", [])
        story.append(Paragraph(f"预警数量: {len(alerts)}", body_style))
        story.append(Spacer(1, 8))

        for alert in alerts:
            severity = alert.get("severity", "info")
            color = "#f5222d" if severity == "critical" else "#faad14" if severity == "warning" else "#1890ff"
            story.append(Paragraph(f"[{severity.upper()}] {alert.get('title', '')}", heading_style))
            story.append(Paragraph(alert.get("description", ""), body_style))
            if alert.get("suggestion"):
                story.append(Paragraph(f"建议: {alert['suggestion']}", body_style))
            story.append(Spacer(1, 6))

    def _add_table(self, story, data: Dict, cn_font: str):
        """将字典转为 PDF 表格"""
        if not data:
            return
        table_data = [[str(k), str(v)] for k, v in data.items() if k != "_id"]
        t = Table(table_data, colWidths=[6 * cm, 10 * cm])
        t.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), cn_font),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("BACKGROUND", (0, 0), (0, -1), HexColor("#f5f5f5")),
            ("GRID", (0, 0), (-1, -1), 0.5, HexColor("#e8e8e8")),
        ]))
        story.append(t)

    def _add_list_table(self, story, data: List[Dict], cn_font: str):
        """将列表转为 PDF 表格"""
        if not data:
            return
        # 取所有键的并集（限制前 8 列）
        all_keys = list(dict.fromkeys(k for d in data for k in d.keys() if k != "_id"))[:8]
        table_data = [all_keys]
        for item in data[:50]:
            table_data.append([str(item.get(k, "")) for k in all_keys])

        col_width = min(4 * cm, 16 * cm / len(all_keys))
        t = Table(table_data, colWidths=[col_width] * len(all_keys))
        t.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), cn_font),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("BACKGROUND", (0, 0), (-1, 0), HexColor("#1890ff")),
            ("TEXTCOLOR", (0, 0), (-1, 0), HexColor("#ffffff")),
            ("GRID", (0, 0), (-1, -1), 0.5, HexColor("#e8e8e8")),
        ]))
        story.append(t)

    def _flatten_doc(self, doc: Dict, prefix: str = "") -> Dict:
        """将嵌套文档展平为一级字典"""
        items = {}
        for k, v in doc.items():
            new_key = f"{prefix}.{k}" if prefix else k
            if isinstance(v, dict):
                items.update(self._flatten_doc(v, new_key))
            elif isinstance(v, list):
                items[new_key] = str(v)[:200]
            else:
                items[new_key] = v
        return items

    def _cleanup_old_exports(self, max_age_hours: int = 24):
        """清理过期的导出文件"""
        try:
            if not os.path.exists(EXPORT_DIR):
                return
            now = time.time()
            for f in os.listdir(EXPORT_DIR):
                filepath = os.path.join(EXPORT_DIR, f)
                if os.path.isfile(filepath) and (now - os.path.getmtime(filepath)) > max_age_hours * 3600:
                    os.remove(filepath)
        except Exception as e:
            logger.warning(f"清理导出文件失败: {e}")
