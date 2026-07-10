"""
MOD-001: WebhookReceiver — HTTP endpoint for receiving Mock Zabbix alert webhooks.
@author sub_agent_software_developer
@module MOD-001
@implements IFC-001-01, IFC-001-02
@depends MOD-004 (AlertNormalizer)
@covers REQ-FUNC-001, REQ-FUNC-002
"""

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import ValidationError as PydanticValidationError
from loguru import logger

from src.models.alert import AlertPayload, AlertReceipt
from src.orchestration.alert_normalizer import AlertNormalizer


class WebhookReceiver:
    """
    FastAPI Webhook 接收器。
    暴露 POST /webhook/alert 端点，接收 Mock Zabbix 告警推送。

    IFC-001-01: POST /webhook/alert
      - 输入: AlertPayload (JSON body)
      - 返回: AlertReceipt { alert_id, status }
      - 错误: HTTP 400 (Schema 校验失败), HTTP 503 (内部队列满)

    IFC-001-02: start_server(host, port) -> None
    """

    def __init__(self, normalizer: AlertNormalizer):
        self.normalizer = normalizer
        self.app = FastAPI(
            title="NetworkAgentDemo Webhook Receiver",
            version="0.1.0",
        )
        self._setup_routes()

    def _setup_routes(self) -> None:
        """注册 FastAPI 路由。"""

        @self.app.post("/webhook/alert", response_model=AlertReceipt)
        async def receive_alert(payload: AlertPayload):
            """
            接收 Mock Zabbix Webhook 告警推送。
            归一化后触发 LangGraph 工作流。
            """
            logger.info(f"Webhook received: {payload.alert_name} on {payload.alert_host}")

            # 归一化告警
            try:
                alert = self.normalizer.normalize_webhook_event(payload)
            except Exception as e:
                logger.error(f"Alert normalization failed: {e}")
                raise HTTPException(status_code=503, detail="Alert normalization service unavailable")

            if alert is None:
                # 去重或过期
                return AlertReceipt(
                    alert_id="",
                    status="DUPLICATE",
                )

            # 触发 LangGraph 工作流（由调用方注入）
            # WebhookReceiver 只负责接收和归一化，由 main.py 负责编排
            logger.info(f"Alert accepted: {alert.alert_id} ({alert.alert_type})")
            return AlertReceipt(
                alert_id=alert.alert_id,
                status="ACCEPTED",
            )

        @self.app.get("/health")
        async def health_check():
            return {"status": "healthy", "service": "webhook_receiver"}

    # ── IFC-001-02: start_server ─────────────────────────

    def start_server(self, host: str = "0.0.0.0", port: int = 8000) -> None:
        """启动 Uvicorn ASGI 服务器。"""
        logger.info(f"Starting WebhookReceiver on {host}:{port}")
        uvicorn.run(self.app, host=host, port=port, log_level="info")
