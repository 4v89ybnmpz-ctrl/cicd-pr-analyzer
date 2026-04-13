"""
openLiBing 平台数据提取器
从拦截的网络请求中提取流水线相关数据
"""
import re
import logging
from typing import Dict, Any, List
from .base import BaseExtractor

logger = logging.getLogger(__name__)


class OpenLibingExtractor(BaseExtractor):
    """
    openLiBing 流水线数据提取器
    从拦截的 API 响应中提取流水线运行详情
    """

    name = "openlibing"

    # 关注的 API 路径模式
    api_patterns = [
        r"pipeline",
        r"project.*build",
        r"ci.*run",
        r"task.*detail",
        r"stage.*list",
        r"job.*log",
    ]

    def extract(self, api_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        提取流水线数据
        :param api_data: 拦截到的 API 响应列表
        :return: 结构化的流水线数据
        """
        relevant = self.filter_relevant(api_data)

        result = {
            "platform": "openlibing",
            "total_api_calls": len(api_data),
            "relevant_api_calls": len(relevant),
            "pipelines": [],
            "stages": [],
            "tasks": [],
            "raw_responses": [],
        }

        for item in relevant:
            url = item.get("url", "")
            body = item.get("response_body")
            status = item.get("status")

            # 保存原始响应
            result["raw_responses"].append({
                "url": url,
                "status": status,
                "method": item.get("method"),
                "timestamp": item.get("timestamp"),
            })

            if not body or status != 200:
                continue

            # 根据响应内容分类提取
            if isinstance(body, dict):
                extracted = self._extract_from_dict(url, body)
                if extracted:
                    category = extracted.pop("_category", "unknown")
                    if category == "pipeline":
                        result["pipelines"].append(extracted)
                    elif category == "stage":
                        result["stages"].append(extracted)
                    elif category == "task":
                        result["tasks"].append(extracted)

            elif isinstance(body, list):
                for item_data in body:
                    if isinstance(item_data, dict):
                        extracted = self._extract_from_dict(url, item_data)
                        if extracted:
                            category = extracted.pop("_category", "unknown")
                            if category == "pipeline":
                                result["pipelines"].append(extracted)
                            elif category == "stage":
                                result["stages"].append(extracted)
                            elif category == "task":
                                result["tasks"].append(extracted)

        # 汇总
        result["summary"] = {
            "pipeline_count": len(result["pipelines"]),
            "stage_count": len(result["stages"]),
            "task_count": len(result["tasks"]),
        }

        logger.info(
            f"openLiBing 提取完成: "
            f"{len(result['pipelines'])} 流水线, "
            f"{len(result['stages'])} 阶段, "
            f"{len(result['tasks'])} 任务"
        )

        return result

    def _extract_from_dict(self, url: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        从字典数据中提取信息
        :param url: API URL
        :param data: 响应数据
        :return: 提取结果
        """
        extracted = {}

        # 判断数据类型
        if self._is_pipeline_data(data):
            extracted = self._extract_pipeline(data)
            extracted["_category"] = "pipeline"
        elif self._is_stage_data(data):
            extracted = self._extract_stage(data)
            extracted["_category"] = "stage"
        elif self._is_task_data(data):
            extracted = self._extract_task(data)
            extracted["_category"] = "task"
        else:
            # 通用提取
            extracted = self._extract_generic(data)
            extracted["_category"] = "unknown"

        if extracted:
            extracted["source_url"] = url

        return extracted

    def _is_pipeline_data(self, data: Dict) -> bool:
        """判断是否为流水线数据"""
        pipeline_keys = {"pipelineId", "pipelineName", "pipelineRunId", "pipelineStatus", "pipelineNameEn"}
        return bool(pipeline_keys & set(data.keys()))

    def _is_stage_data(self, data: Dict) -> bool:
        """判断是否为阶段数据"""
        stage_keys = {"stageId", "stageName", "stageStatus", "stageSeqId"}
        return bool(stage_keys & set(data.keys()))

    def _is_task_data(self, data: Dict) -> bool:
        """判断是否为任务数据"""
        task_keys = {"taskId", "taskName", "taskStatus", "jobId"}
        return bool(task_keys & set(data.keys()))

    def _extract_pipeline(self, data: Dict) -> Dict[str, Any]:
        """提取流水线信息"""
        return {
            "pipeline_id": data.get("pipelineId") or data.get("id"),
            "pipeline_name": data.get("pipelineName") or data.get("name"),
            "run_id": data.get("pipelineRunId") or data.get("runId"),
            "status": self._normalize_status(data.get("pipelineStatus") or data.get("status")),
            "trigger_type": data.get("triggerType"),
            "branch": data.get("branch") or data.get("sourceBranch"),
            "commit_id": data.get("commitId") or data.get("sha"),
            "duration": data.get("duration"),
            "start_time": data.get("startTime") or data.get("createdAt"),
            "end_time": data.get("endTime") or data.get("finishedAt"),
            "creator": data.get("creator") or data.get("triggerUser"),
        }

    def _extract_stage(self, data: Dict) -> Dict[str, Any]:
        """提取阶段信息"""
        return {
            "stage_id": data.get("stageId") or data.get("id"),
            "stage_name": data.get("stageName") or data.get("name"),
            "status": self._normalize_status(data.get("stageStatus") or data.get("status")),
            "seq_id": data.get("stageSeqId") or data.get("order"),
            "duration": data.get("duration"),
            "start_time": data.get("startTime"),
            "end_time": data.get("endTime"),
        }

    def _extract_task(self, data: Dict) -> Dict[str, Any]:
        """提取任务信息"""
        return {
            "task_id": data.get("taskId") or data.get("id"),
            "task_name": data.get("taskName") or data.get("name"),
            "status": self._normalize_status(data.get("taskStatus") or data.get("status")),
            "job_id": data.get("jobId"),
            "duration": data.get("duration"),
            "start_time": data.get("startTime"),
            "end_time": data.get("endTime"),
            "result": data.get("result") or data.get("output"),
        }

    def _extract_generic(self, data: Dict) -> Dict[str, Any]:
        """通用提取（未知数据结构）"""
        # 提取常见的状态和名称字段
        result = {}
        for key in ["id", "name", "status", "result", "message", "error", "code"]:
            if key in data:
                result[key] = data[key]
        return result

    def _normalize_status(self, status: Any) -> str:
        """标准化状态值"""
        if not status:
            return "unknown"

        status_str = str(status).lower().strip()

        # 成功状态
        if status_str in ("success", "succeeded", "passed", "completed", "ok", "0", "finished"):
            return "success"

        # 失败状态
        if status_str in ("failed", "failure", "error", "aborted", "cancelled", "timeout", "-1"):
            return "failed"

        # 运行中
        if status_str in ("running", "in_progress", "pending", "queued", "waiting", "executing"):
            return "running"

        return status_str
