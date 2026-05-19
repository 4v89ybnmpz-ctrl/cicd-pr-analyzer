"""
洞察评级引擎
独立于 backend app 模块，供 Agent 工具直接调用
根据 CI/CD 统计数据生成评级和洞察项
"""


def grade_success_rate(rate: float) -> tuple:
    """构建成功率评级"""
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


def grade_duration(seconds: float) -> tuple:
    """构建耗时评级"""
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


def grade_coverage(coverage: float) -> tuple:
    """测试覆盖率评级"""
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


def format_duration(seconds: float) -> str:
    """格式化耗时"""
    if seconds < 60:
        return f"{seconds:.0f}s"
    elif seconds < 3600:
        return f"{seconds / 60:.1f}m"
    else:
        return f"{seconds / 3600:.1f}h"


def build_insights(summary_data: dict, failure_analysis: dict) -> list:
    """根据统计数据构建洞察项"""
    insights = []
    total = summary_data.get("total", 0)
    if total == 0:
        return insights

    success_rate = summary_data.get("success_rate")
    if success_rate is not None:
        grade, suggestion = grade_success_rate(success_rate)
        insights.append({
            "name": "构建成功率",
            "value": success_rate,
            "grade": grade,
            "description": f"共 {total} 次构建，成功率 {success_rate}%",
            "suggestion": suggestion,
        })

    avg_duration = summary_data.get("avg_duration_seconds")
    if avg_duration is not None:
        grade, suggestion = grade_duration(avg_duration)
        insights.append({
            "name": "平均构建耗时",
            "value": avg_duration,
            "grade": grade,
            "description": f"平均耗时 {format_duration(avg_duration)}",
            "suggestion": suggestion,
        })

    avg_coverage = summary_data.get("avg_coverage")
    if avg_coverage is not None:
        grade, suggestion = grade_coverage(avg_coverage)
        insights.append({
            "name": "测试覆盖率",
            "value": avg_coverage,
            "grade": grade,
            "description": f"平均覆盖率 {avg_coverage}%",
            "suggestion": suggestion,
        })

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


def compute_overall_grade(insights: list) -> str:
    """计算综合评级"""
    if not insights:
        return "N/A"

    grade_order = {"A": 5, "B": 4, "C": 3, "D": 2, "F": 1}
    grades = [grade_order.get(i.get("grade", "F"), 1) for i in insights]
    avg = sum(grades) / len(grades)

    if avg >= 4.5:
        return "A"
    elif avg >= 3.5:
        return "B"
    elif avg >= 2.5:
        return "C"
    elif avg >= 1.5:
        return "D"
    else:
        return "F"
