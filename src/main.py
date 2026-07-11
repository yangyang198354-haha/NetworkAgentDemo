"""
NetworkAgentDemo — Application Entry Point.
@author sub_agent_software_developer
@module Main Application
@version 0.2.0

Integrates FastAPI server, LangGraph workflow engine, APScheduler inspection,
and all 16 modules. Provides REST API endpoints for alert submission,
workflow management, approval handling, and Web UI management.

Web UI additions (v0.2.0):
  - MOD-WEB-001~007: API routers, auth, encryption, DB, dashboard, log reader
  - JWT-protected /api/* endpoints (8 APIRouters, ~41 endpoints)
  - SQLite persistence layer (11 ORM models, 7 repositories)
  - Existing 6 endpoints preserved with zero deletion
"""

import os
import sys
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

# ── 将 src 目录加入 sys.path（如果需要） ──
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from fastapi import FastAPI, HTTPException
from loguru import logger
from pydantic import ValidationError as PydanticValidationError

from src.models.alert import AlertPayload, AlertReceipt, Alert, DeviceInfo
from src.models.state import ApprovalDecision, PendingApproval
from src.models.enums import AlertType, AlertSeverity, AlertSource

from src.security.config_manager import ConfigManager
from src.security.audit_logger import AuditLogger
from src.security.risk_assessor import RiskAssessor

from src.llm.llm_service import LLMService
from src.llm.template_engine import TemplateEngine
from src.llm.rag_service import RAGService
from src.llm.output_validator import OutputValidator

from src.tools.switch_config_tool import create_switch_config_tool
from src.tools.switch_diag_tool import create_switch_diag_tool
from src.tools.backup_tool import create_backup_tool
from src.tools.knowledge_base_tool import KnowledgeBaseTool

from src.orchestration.alert_normalizer import AlertNormalizer
from src.orchestration.node_handlers import NodeHandlers
from src.orchestration.state_graph_engine import StateGraphEngine

from src.trigger.webhook_receiver import WebhookReceiver
from src.trigger.inspection_scheduler import InspectionScheduler

# ── MOD-WEB: Web UI 新增模块导入 ───────────────────────────
from src.database.base import create_engine as db_create_engine, init_session, init_db, get_db as db_get_db
from src.services.encryption_service import EncryptionService
from src.services.auth_service import init_admin_user


# ────────────────────────────────────────────────────
# 模块初始化（单例）
# ────────────────────────────────────────────────────

config_manager = ConfigManager()
audit_logger = AuditLogger()
risk_assessor = RiskAssessor()

llm_service = LLMService()
template_engine = TemplateEngine()
rag_service = RAGService()
output_validator = OutputValidator(audit_logger=audit_logger)

switch_config_tool = create_switch_config_tool(use_mock=True)
switch_diag_tool = create_switch_diag_tool(use_mock=True)
backup_tool = create_backup_tool(use_mock=True)
knowledge_base_tool = KnowledgeBaseTool(rag_service=rag_service)

alert_normalizer = AlertNormalizer()

node_handlers = NodeHandlers(
    llm_service=llm_service,
    template_engine=template_engine,
    rag_service=rag_service,
    output_validator=output_validator,
    switch_config_tool=switch_config_tool,
    switch_diag_tool=switch_diag_tool,
    backup_tool=backup_tool,
    knowledge_base_tool=knowledge_base_tool,
    risk_assessor=risk_assessor,
    audit_logger=audit_logger,
    config_manager=config_manager,
)

state_graph_engine = StateGraphEngine(node_handlers=node_handlers)

webhook_receiver = WebhookReceiver(normalizer=alert_normalizer)
inspection_scheduler = InspectionScheduler(
    normalizer=alert_normalizer,
    diag_tool=switch_diag_tool,
    config_manager=config_manager,
)

# ── MOD-WEB: Web UI 单例 ───────────────────────────────────
encryption_service = EncryptionService()


# ────────────────────────────────────────────────────
# 应用启动/关闭管理
# ────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI 生命周期管理 — 启动时初始化所有模块，关闭时清理资源。"""
    logger.info("=" * 60)
    logger.info("NetworkAgentDemo v0.2.0 — Starting up...")
    logger.info("=" * 60)

    # 1. 加载配置
    config_path = os.environ.get("CONFIG_PATH", "./config/config.yaml")
    try:
        config_manager.load_config(config_path)
        logger.info(f"Configuration loaded from {config_path}")
    except FileNotFoundError:
        logger.warning(f"Config file not found: {config_path}, using defaults")

    # 2. 配置 AuditLogger
    ops_log_path = config_manager.get("logging.operations_log_path") or "./logs/"
    audit_log_path = config_manager.get("logging.audit_log_path") or "./logs/audit.log"
    audit_enabled = config_manager.get("logging.audit_enabled") or True
    audit_logger.configure(ops_log_path, audit_log_path, audit_enabled)
    logger.info("AuditLogger configured")

    # 3. 配置 TemplateEngine
    templates_dir = config_manager.get("templates.directory") or "./resources/templates/"
    template_engine._templates_dir = Path(templates_dir)
    template_engine.load_templates()
    logger.info(f"TemplateEngine loaded {len(template_engine._templates_cache)} templates")

    # 4. 初始化 RAGService
    chroma_path = config_manager.get("rag.chroma_persist_path") or "./data/chroma_db/"
    rag_service._persist_path = chroma_path
    rag_service._similarity_threshold = config_manager.get("rag.similarity_threshold") or 0.6
    rag_service.initialize()

    # 5. 加载种子知识库
    seed_file = config_manager.get("knowledge.seed_file") or "./resources/knowledge/seed_knowledge.json"
    rag_service.load_seed_knowledge(seed_file)
    logger.info("RAGService initialized with seed knowledge")

    # ── MOD-WEB: 6. 初始化数据库 (MOD-WEB-003) ─────────────
    db_path = config_manager.get("webui.db_path") or "./data/webui.db"
    engine = db_create_engine(db_path)
    init_session(engine)
    init_db(engine)
    logger.info("SQLite database initialized (webui.db)")

    # ── MOD-WEB: 7. 初始化加密服务 (MOD-WEB-005) ────────────
    encryption_service.initialize()
    logger.info(f"EncryptionService initialized (key source: {encryption_service.get_key_status()})")

    # ── MOD-WEB: 8. 初始化 admin 用户 (MOD-WEB-002) ─────────
    db_gen = db_get_db()
    admin_db = next(db_gen)
    try:
        init_admin_user(admin_db)
    finally:
        admin_db.close()
    logger.info("Admin user initialized")

    # 6. 构建 LangGraph
    state_graph_engine.build_graph()
    logger.info("LangGraph StateGraph compiled")

    # 7. 启动巡检调度器（带默认设备列表）
    default_devices = [
        DeviceInfo(
            device_name="Core-SW-01",
            device_ip="192.168.1.1",
            device_model="TP-Link T2600G-28TS",
        ),
        DeviceInfo(
            device_name="Access-SW-02",
            device_ip="192.168.1.2",
            device_model="TP-Link T2600G-28TS",
        ),
    ]
    interval = config_manager.get("inspection.interval_minutes") or 5
    inspection_scheduler.start_scheduler(interval_minutes=interval, device_list=default_devices)
    logger.info(f"InspectionScheduler started (interval={interval}min)")

    logger.info("NetworkAgentDemo is ready!")
    yield

    # ── 关闭 ──
    logger.info("NetworkAgentDemo shutting down...")
    inspection_scheduler.stop_scheduler()
    logger.info("NetworkAgentDemo shutdown complete.")


# ────────────────────────────────────────────────────
# FastAPI 应用
# ────────────────────────────────────────────────────

app = FastAPI(
    title="NetworkAgentDemo",
    description="LangGraph-based network automation agent (Demo) with Web UI",
    version="0.2.0",
    lifespan=lifespan,
)

# ── MOD-WEB: 注册 Web UI 路由 (MOD-WEB-001) ─────────────────
from src.api import auth_router, api_router

app.include_router(auth_router)
app.include_router(api_router)
logger.info("Web UI API routers registered (auth + 8 API routers)")


# ────────────────────────────────────────────────────
# API 端点（原有 6 个，保持向后兼容）
# ────────────────────────────────────────────────────

@app.post("/webhook/alert", response_model=AlertReceipt)
async def handle_webhook_alert(payload: AlertPayload):
    """
    接收 Mock Zabbix Webhook 告警推送。
    归一化后触发 LangGraph 工作流。
    """
    logger.info(f"[API] Webhook alert received: {payload.alert_name} on {payload.alert_host}")

    # 归一化
    alert = alert_normalizer.normalize_webhook_event(payload)
    if alert is None:
        return AlertReceipt(alert_id="", status="DUPLICATE")

    # 触发 LangGraph 工作流（在线程池中执行同步 StateGraph）
    def run_workflow():
        try:
            result = state_graph_engine.run_workflow(alert)
            logger.info(f"Workflow finished: {alert.alert_id} → {result.get('status')}")
        except Exception as e:
            logger.error(f"Workflow exception: {e}", exc_info=True)

    # 在后台线程执行（LangGraph 同步，FastAPI async）
    threading.Thread(target=run_workflow, daemon=True).start()

    return AlertReceipt(alert_id=alert.alert_id, status="ACCEPTED")


@app.post("/alerts/simulate", deprecated=True)
async def simulate_alert_legacy(
    alert_type: str = "PORT_DOWN",
    device_name: str = "Core-SW-01",
    device_ip: str = "192.168.1.1",
    interface: str = "Gi0/1",
):
    """
    [DEPRECATED] 模拟告警端点（便捷测试接口）。
    请使用 POST /api/alerts/simulate 替代。
    """
    try:
        atype = AlertType(alert_type.upper())
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid alert_type: {alert_type}")

    # 构造描述
    descriptions = {
        AlertType.MAC_FLAPPING: f"MAC地址 00:1A:2B:3C:4D:5E 在设备 {device_name} 的VLAN 1内发生漂移，"
                                 f"出现在端口 Gi0/1 和 Gi0/2 之间。",
        AlertType.PORT_DOWN: f"接口 {interface} 在设备 {device_name} 上状态变更为 down，"
                              f"线路协议状态为 down (notconnect)。",
        AlertType.CPU_HIGH: f"设备 {device_name} 的CPU利用率在5秒内达到92%，"
                             f"超过告警阈值80%。SNMP ENGINE 进程消耗最高。",
    }

    alert = Alert(
        alert_type=atype,
        alert_severity=AlertSeverity.MAJOR,
        alert_content=descriptions.get(atype, f"Simulated {alert_type} alert on {device_name}"),
        device_info=DeviceInfo(
            device_name=device_name,
            device_ip=device_ip,
            device_model="TP-Link T2600G-28TS",
            interface_name=interface,
            mac_address="00:1A:2B:3C:4D:5E" if atype == AlertType.MAC_FLAPPING else None,
            cpu_percent=92.0 if atype == AlertType.CPU_HIGH else None,
        ),
        source=AlertSource.MOCK,
    )

    def run_workflow():
        try:
            result = state_graph_engine.run_workflow(alert)
            logger.info(f"[Simulate] Workflow finished: {alert.alert_id} → {result.get('status')}")
        except Exception as e:
            logger.error(f"[Simulate] Workflow exception: {e}", exc_info=True)

    threading.Thread(target=run_workflow, daemon=True).start()

    return {
        "message": "Simulated alert accepted (DEPRECATED — use POST /api/alerts/simulate)",
        "alert_id": alert.alert_id,
        "alert_type": alert.alert_type,
        "warning": "This endpoint is deprecated, use POST /api/alerts/simulate instead",
    }


@app.get("/approvals/pending", response_model=list[PendingApproval])
async def get_pending_approvals():
    """查询所有处于 Interrupt 挂起状态的审批项。"""
    return state_graph_engine.get_pending_approvals()


@app.post("/approvals/{checkpoint_id}/decide")
async def decide_approval(checkpoint_id: str, decision: ApprovalDecision):
    """
    对挂起的审批做出决定（APPROVED / REJECTED），恢复 LangGraph 工作流。
    """
    decision.checkpoint_id = checkpoint_id

    def resume():
        try:
            result = state_graph_engine.resume_workflow(checkpoint_id, decision)
            logger.info(f"[Approval] Resume finished: {checkpoint_id} → {result.get('status')}")
        except Exception as e:
            logger.error(f"[Approval] Resume exception: {e}", exc_info=True)

    threading.Thread(target=resume, daemon=True).start()

    return {
        "message": f"Decision '{decision.decision}' submitted for checkpoint {checkpoint_id}",
        "checkpoint_id": checkpoint_id,
    }


@app.get("/workflow/{checkpoint_id}/state")
async def get_workflow_state(checkpoint_id: str):
    """查询指定检查点的当前工作流状态。"""
    state = state_graph_engine.get_workflow_state(checkpoint_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"Workflow state not found: {checkpoint_id}")
    return {"checkpoint_id": checkpoint_id, "state": state}


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "NetworkAgentDemo",
        "components": {
            "langgraph": state_graph_engine._graph is not None,
            "rag": rag_service._use_chroma or len(rag_service._fallback_docs) > 0,
            "scheduler": inspection_scheduler._scheduler is not None,
        },
    }


# ── MOD-WEB: Static files mount for Vue SPA ─────────────────

from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

_webui_dist = Path(__file__).resolve().parent.parent / "webui" / "dist"

if _webui_dist.exists():
    # Mount assets at /assets/ (JS, CSS, images)
    _assets_dir = _webui_dist / "assets"
    if _assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(_assets_dir)), name="assets")

    # Serve index.html for root and SPA fallback
    @app.get("/")
    async def serve_spa_root():
        return FileResponse(str(_webui_dist / "index.html"))

    @app.get("/{full_path:path}")
    async def serve_spa_fallback(full_path: str):
        """SPA fallback — serve index.html for all non-API routes."""
        file_path = _webui_dist / full_path
        if file_path.is_file():
            return FileResponse(str(file_path))
        return FileResponse(str(_webui_dist / "index.html"))

    logger.info(f"Web UI static files mounted from {_webui_dist}")
else:
    logger.warning(f"Web UI dist directory not found: {_webui_dist}")


# ────────────────────────────────────────────────────
# 主入口（直接运行 python src/main.py）
# ────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    host = config_manager.get("server.host") or "0.0.0.0"
    port = config_manager.get("server.port") or 8000

    logger.info(f"Starting NetworkAgentDemo server on {host}:{port}")
    uvicorn.run("src.main:app", host=host, port=port, reload=False, log_level="info")
