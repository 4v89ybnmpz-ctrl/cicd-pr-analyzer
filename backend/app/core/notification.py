"""
通知推送引擎
支持邮件、飞书、钉钉、Slack 四种通知渠道
"""
import logging
import uuid
import json
import hashlib
import hmac
import base64
import time
from typing import Dict, Any, List, Optional
from datetime import datetime

import httpx

logger = logging.getLogger(__name__)


class NotificationEngine:
    """通知引擎（全局单例）"""

    def __init__(self, db):
        self._db = db
        self._http_client: Optional[httpx.AsyncClient] = None
        self._smtp_config: Dict = {}

    async def initialize(self):
        """初始化 HTTP 客户端和 SMTP 配置"""
        self._http_client = httpx.AsyncClient(timeout=30.0)

        # 从 config.json 读取 SMTP 默认配置
        try:
            from app.config.config_manager import config_manager
            notification_cfg = config_manager.get("notification", {})
            self._smtp_config = notification_cfg.get("smtp", {})
        except Exception as e:
            logger.warning(f"加载通知配置失败: {e}")

        logger.info("通知引擎初始化完成")

    async def shutdown(self):
        """关闭 HTTP 客户端"""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    # ====================
    # 配置管理（委托给 DatabaseService）
    # ====================

    async def load_configs(self) -> List[Dict]:
        """获取所有通知配置"""
        result = await self._db.list_notification_configs()
        return result.get("data", [])

    async def save_config(self, config_data: Dict) -> Dict:
        """保存通知配置"""
        return await self._db.save_notification_config(config_data)

    async def update_config(self, config_id: str, updates: Dict) -> Dict:
        """更新通知配置"""
        return await self._db.update_notification_config(config_id, updates)

    async def delete_config(self, config_id: str) -> Dict:
        """删除通知配置"""
        return await self._db.delete_notification_config(config_id)

    # ====================
    # 通知发送
    # ====================

    async def evaluate_and_notify(self, trigger: str, context: Dict) -> List[str]:
        """评估规则并发送通知"""
        history_ids = []
        configs = await self.load_configs()
        if not configs:
            return history_ids

        owner = context.get("owner", "")
        repo = context.get("repo", "")
        project_key = f"{owner}/{repo}" if owner and repo else ""

        for config in configs:
            if not config.get("enabled", True):
                continue

            # 检查触发条件
            schedule = config.get("schedule", "on_complete")
            if trigger == "analysis_complete" and schedule != "on_complete":
                continue

            # 检查规则匹配
            rules = config.get("rules", [])
            matched = self._evaluate_rules(rules, project_key, context)

            if not matched and rules:
                continue

            # 渲染通知内容
            subject, body = self._render_message(config.get("name", ""), trigger, context)

            # 向所有启用的渠道发送
            channels = config.get("channels", [])
            channel_settings = config.get("channel_settings", {})

            for channel in channels:
                settings = channel_settings.get(channel, {})
                success = False
                error_msg = None

                try:
                    if channel == "email":
                        success = await self._send_email(settings, subject, body)
                    elif channel == "feishu":
                        success = await self._send_feishu(settings, subject, body)
                    elif channel == "dingtalk":
                        success = await self._send_dingtalk(settings, subject, body)
                    elif channel == "slack":
                        success = await self._send_slack(settings, subject, body)
                    else:
                        error_msg = f"未知渠道: {channel}"
                except Exception as e:
                    error_msg = str(e)
                    logger.error(f"发送通知失败 [{channel}]: {e}")

                # 记录历史
                history_id = await self._db.save_notification_history({
                    "config_id": config.get("config_id", ""),
                    "config_name": config.get("name", ""),
                    "channel": channel,
                    "status": "success" if success else "failed",
                    "subject": subject,
                    "body_summary": body[:200] if body else "",
                    "trigger_type": trigger,
                    "trigger_context": context,
                    "error": error_msg,
                })
                if history_id:
                    history_ids.append(history_id)

        return history_ids

    async def test_send(self, config_id: str) -> Dict:
        """测试发送通知"""
        config_result = await self._db.get_notification_config(config_id)
        config = config_result.get("data")
        if not config:
            return {"sent": False, "message": "配置不存在"}

        channels = config.get("channels", [])
        channel_settings = config.get("channel_settings", {})
        subject = f"[测试] {config.get('name', '通知测试')}"
        body = f"这是一条测试通知，发送时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

        results = []
        for channel in channels:
            settings = channel_settings.get(channel, {})
            try:
                if channel == "email":
                    ok = await self._send_email(settings, subject, body)
                elif channel == "feishu":
                    ok = await self._send_feishu(settings, subject, body)
                elif channel == "dingtalk":
                    ok = await self._send_dingtalk(settings, subject, body)
                elif channel == "slack":
                    ok = await self._send_slack(settings, subject, body)
                else:
                    ok = False
                results.append({"channel": channel, "success": ok})

                # 记录测试历史
                await self._db.save_notification_history({
                    "config_id": config_id,
                    "config_name": config.get("name", ""),
                    "channel": channel,
                    "status": "success" if ok else "failed",
                    "subject": subject,
                    "body_summary": body,
                    "trigger_type": "test",
                    "trigger_context": {},
                })
            except Exception as e:
                results.append({"channel": channel, "success": False, "error": str(e)})

        any_success = any(r["success"] for r in results)
        return {"sent": any_success, "results": results}

    # ====================
    # 渠道发送实现
    # ====================

    async def _send_email(self, settings: Dict, subject: str, body: str) -> bool:
        """通过 SMTP 发送邮件"""
        try:
            import aiosmtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart

            smtp_host = settings.get("smtp_host") or self._smtp_config.get("host", "smtp.example.com")
            smtp_port = int(settings.get("smtp_port") or self._smtp_config.get("port", 465))
            use_tls = settings.get("use_tls", True)
            username = settings.get("username") or self._smtp_config.get("username", "")
            password = settings.get("password") or self._smtp_config.get("password", "")
            sender = settings.get("sender") or self._smtp_config.get("sender", "noreply@example.com")
            recipients = settings.get("recipients", [])

            # 前端可能传逗号分隔的字符串，需要转为列表
            if isinstance(recipients, str):
                recipients = [r.strip() for r in recipients.split(",") if r.strip()]

            if not recipients:
                logger.warning("邮件收件人列表为空")
                return False

            msg = MIMEMultipart()
            msg["From"] = sender
            msg["To"] = ", ".join(recipients)
            msg["Subject"] = subject
            msg.attach(MIMEText(body, "plain", "utf-8"))

            # 端口 465 用直接 SSL，其他端口用 STARTTLS
            if smtp_port == 465:
                await aiosmtplib.send(
                    msg,
                    hostname=smtp_host,
                    port=smtp_port,
                    username=username if username else None,
                    password=password if password else None,
                    use_tls=True,
                )
            else:
                await aiosmtplib.send(
                    msg,
                    hostname=smtp_host,
                    port=smtp_port,
                    username=username if username else None,
                    password=password if password else None,
                    start_tls=use_tls,
                )
            logger.info(f"邮件发送成功: {recipients}")
            return True
        except ImportError:
            logger.warning("aiosmtplib 未安装，无法发送邮件")
            return False
        except Exception as e:
            logger.error(f"邮件发送失败: {e}")
            return False

    async def _send_feishu(self, settings: Dict, title: str, body: str) -> bool:
        """通过飞书 Bot Webhook 发送"""
        webhook_url = settings.get("webhook_url", "")
        if not webhook_url:
            logger.warning("飞书 Webhook URL 为空")
            return False

        payload = {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {"tag": "plain_text", "content": title},
                    "template": "blue",
                },
                "elements": [
                    {"tag": "markdown", "content": body},
                ],
            },
        }

        resp = await self._http_client.post(webhook_url, json=payload)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("code") == 0 or data.get("StatusCode") == 0:
                logger.info("飞书通知发送成功")
                return True
        logger.error(f"飞书通知发送失败: {resp.status_code} {resp.text}")
        return False

    async def _send_dingtalk(self, settings: Dict, title: str, body: str) -> bool:
        """通过钉钉 Bot Webhook 发送"""
        webhook_url = settings.get("webhook_url", "")
        secret = settings.get("secret", "")
        if not webhook_url:
            logger.warning("钉钉 Webhook URL 为空")
            return False

        # 签名
        if secret:
            timestamp = str(round(time.time() * 1000))
            string_to_sign = f"{timestamp}\n{secret}"
            hmac_code = hmac.new(
                secret.encode("utf-8"),
                string_to_sign.encode("utf-8"),
                digestmod=hashlib.sha256,
            ).digest()
            sign = base64.b64encode(hmac_code).decode("utf-8")
            webhook_url += f"&timestamp={timestamp}&sign={sign}"

        payload = {
            "msgtype": "markdown",
            "markdown": {
                "title": title,
                "text": f"### {title}\n\n{body}",
            },
        }

        resp = await self._http_client.post(webhook_url, json=payload)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("errcode") == 0:
                logger.info("钉钉通知发送成功")
                return True
        logger.error(f"钉钉通知发送失败: {resp.status_code} {resp.text}")
        return False

    async def _send_slack(self, settings: Dict, title: str, body: str) -> bool:
        """通过 Slack Webhook 发送"""
        webhook_url = settings.get("webhook_url", "")
        if not webhook_url:
            logger.warning("Slack Webhook URL 为空")
            return False

        payload = {
            "blocks": [
                {"type": "header", "text": {"type": "plain_text", "text": title}},
                {"type": "section", "text": {"type": "mrkdwn", "text": body}},
            ],
        }

        resp = await self._http_client.post(webhook_url, json=payload)
        if resp.status_code == 200:
            logger.info("Slack 通知发送成功")
            return True
        logger.error(f"Slack 通知发送失败: {resp.status_code} {resp.text}")
        return False

    # ====================
    # 规则评估
    # ====================

    def _evaluate_rules(self, rules: List[Dict], project_key: str, context: Dict) -> bool:
        """评估通知规则是否匹配"""
        if not rules:
            return True  # 无规则时默认匹配

        for rule in rules:
            # 项目匹配
            pattern = rule.get("project_pattern", "*")
            if pattern != "*" and pattern != project_key:
                continue

            # 指标匹配
            metric = rule.get("metric", "")
            metric_value = self._extract_metric_value(metric, context)
            if metric_value is None:
                continue

            # 阈值比较
            operator = rule.get("operator", "gt")
            threshold = rule.get("threshold", 0)

            if self._compare(metric_value, operator, threshold):
                return True

        return False

    def _extract_metric_value(self, metric: str, context: Dict) -> Optional[float]:
        """从上下文中提取指标值"""
        report_data = context.get("report_data", {})

        value_map = {
            "health_score": report_data.get("overall_score"),
            "ci_failure_rate": report_data.get("ci_failure_rate"),
            "review_delay": report_data.get("avg_review_delay_hours"),
            "trend_alert": len(report_data.get("alerts", [])),
        }
        val = value_map.get(metric)
        if val is not None:
            try:
                return float(val)
            except (ValueError, TypeError):
                return None
        return None

    @staticmethod
    def _compare(value: float, operator: str, threshold: float) -> bool:
        """比较操作"""
        ops = {
            "gt": lambda a, b: a > b,
            "gte": lambda a, b: a >= b,
            "lt": lambda a, b: a < b,
            "lte": lambda a, b: a <= b,
            "eq": lambda a, b: a == b,
        }
        return ops.get(operator, lambda a, b: False)(value, threshold)

    # ====================
    # 消息渲染
    # ====================

    def _render_message(self, config_name: str, trigger: str, context: Dict) -> tuple:
        """渲染通知标题和正文"""
        owner = context.get("owner", "")
        repo = context.get("repo", "")
        report_type = context.get("report_type", "")
        report_data = context.get("report_data", {})

        type_labels = {
            "cicd": "CI/CD 洞察",
            "review_quality": "Review 质量",
            "project_health": "项目健康度",
            "trend_alerts": "趋势预警",
        }
        type_label = type_labels.get(report_type, report_type)

        if trigger == "analysis_complete":
            subject = f"[{config_name}] {type_label}分析完成 — {owner}/{repo}"
        else:
            subject = f"[{config_name}] 通知 — {owner}/{repo}"

        # 构建正文
        lines = [f"项目: {owner}/{repo}", f"报告类型: {type_label}"]

        if report_data:
            if "overall_score" in report_data:
                lines.append(f"总体评分: {report_data['overall_score']} 分 ({report_data.get('overall_grade', '')})")
            if "overall_grade" in report_data:
                lines.append(f"评级: {report_data['overall_grade']}")

            alerts = report_data.get("alerts", [])
            if alerts:
                lines.append(f"\n预警 ({len(alerts)} 条):")
                for a in alerts[:5]:
                    lines.append(f"  - [{a.get('severity', '')}] {a.get('title', '')}")

        lines.append(f"\n生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        body = "\n".join(lines)

        return subject, body
