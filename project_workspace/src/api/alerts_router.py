"""
MOD-WEB-001: Alerts Router — GET/POST /api/alerts* (4 endpoints).
@author sub_agent_software_developer
@module MOD-WEB-001
@covers REQ-WEBUI-FUNC-001, REQ-WEBUI-FUNC-002, REQ-WEBUI-FUNC-003, REQ-WEBUI-FUNC-004
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from loguru import logger
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.api.dependencies import get_db
from src.database.repositories.alert_repository import AlertRepository
from src.models.enums import AlertType

alerts_router = APIRouter()


class SimulateAlertRequest(BaseModel):
    alert_type: str = "PORT_DOWN"
    device_name: str = "Core-SW-01"
    device_ip: str = "192.168.1.1"
    interface: Optional[str] = "Gi0/1"
    mac_address: Optional[str] = None
    cpu_percent: Optional[float] = None


# ── GET /api/alerts ────────────────────────────────────────

@alerts_router.get("")
async def list_alerts(
    alert_type: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    time_from: Optional[str] = Query(None),
    time_to: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Return paginated alert list with optional filters."""
    repo = AlertRepository(db)

    tf = datetime.fromisoformat(time_from) if time_from else None
    tt = datetime.fromisoformat(time_to) if time_to else None

    result = repo.list_alerts(
        alert_type=alert_type,
        severity=severity,
        status=status,
        source=source,
        time_from=tf,
        time_to=tt,
        page=page,
        page_size=page_size,
    )
    return result


# ── GET /api/alerts/{alert_id} ─────────────────────────────

@alerts_router.get("/{alert_id}")
async def get_alert_detail(alert_id: str, db: Session = Depends(get_db)):
    """Return alert detail with full timeline and fix plan (if available)."""
    repo = AlertRepository(db)
    alert = repo.get_alert_by_id(alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="告警不存在")

    timeline = repo.get_alert_timeline(alert_id)

    # ★ MOD-DP-008: Read fix_plan and commands from workflow_state JSON column ★
    fix_plan = None
    commands = []
    exec_log = []
    verify_result = None
    wf_state = alert.workflow_state
    if wf_state:
        fp = wf_state.get("fix_plan")
        if fp and isinstance(fp, dict):
            fix_plan = {
                "template_id": fp.get("template_id", ""),
                "description": fp.get("description", ""),
                "params": fp.get("params", {}),
            }
            commands = fp.get("commands", [])
        # 暴露实际下发执行结果（逐命令 success）与结构化验证结果，供 E2E 断言
        if isinstance(wf_state.get("exec_log"), list):
            exec_log = wf_state["exec_log"]
        if isinstance(wf_state.get("verify_result"), dict):
            verify_result = wf_state["verify_result"]

    # ★ MOD-DP-008: Read approval from DB (ApprovalRepository) ★
    approval_info = None
    try:
        from src.database.repositories.approval_repository import ApprovalRepository
        approval_repo = ApprovalRepository(db)
        approvals = approval_repo.get_approvals_by_alert_id(alert_id)
        if approvals:
            latest = approvals[0]  # Already sorted by created_at DESC
            approval_info = {
                "need_human_approval": True,
                "approval_status": latest.decision or "NOT_REQUIRED",
                "risk_level": latest.risk_level or "LOW",
                "decision": latest.decision,
                "decided_by": latest.decided_by,
                "decided_at": latest.decided_at.isoformat() if latest.decided_at else None,
                "note": latest.note or "",
            }
    except Exception:
        pass

    # ★ MOD-DP-008: Read LLM call logs from DB (LLMCallLogRepository) ★
    llm_calls = []
    try:
        from src.database.repositories.llm_call_repository import LLMCallLogRepository
        llm_repo = LLMCallLogRepository(db)
        llm_calls = llm_repo.get_logs_by_alert_id_as_dicts(alert_id)
    except Exception as e:
        logger.warning(f"LLMCallLogRepository failed for {alert_id}: {e}", exc_info=True)
        # Fallback: direct SQLAlchemy query bypassing the repository
        try:
            from src.database.llm_call_models import LLMCallLog
            from sqlalchemy import select
            logs = list(db.execute(
                select(LLMCallLog)
                .where(LLMCallLog.alert_id_fk == alert_id)
                .order_by(LLMCallLog.timestamp)
            ).scalars().all())
            for log in logs:
                ts = log.timestamp
                ts_str = ts.strftime("%H:%M:%S") if hasattr(ts, 'strftime') else str(ts)[-12:-3] if ts else ""
                llm_calls.append({
                    "endpoint": log.endpoint or "",
                    "timestamp": ts_str,
                    "elapsed_s": log.elapsed_s or 0,
                    "prompt_tokens": log.prompt_tokens or 0,
                    "completion_tokens": log.completion_tokens or 0,
                    "prompt": log.prompt_summary or "",
                    "response": log.response_summary or "",
                })
        except Exception as e2:
            logger.error(f"LLM call fallback also failed for {alert_id}: {e2}", exc_info=True)

    return {
        "alert": alert,
        "timeline": timeline,
        "fix_plan": fix_plan,
        "commands": commands,
        "exec_log": exec_log,
        "verify_result": verify_result,
        "llm_calls": llm_calls,
        "approval": approval_info,
    }


# ── GET /api/alerts/{alert_id}/workflow ────────────────────

@alerts_router.get("/{alert_id}/workflow")
async def get_alert_workflow(alert_id: str, db: Session = Depends(get_db)):
    """Return workflow state for a specific alert."""
    repo = AlertRepository(db)
    alert = repo.get_alert_by_id(alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="告警不存在")

    timeline = repo.get_alert_timeline(alert_id)
    return {
        "alert_id": alert_id,
        "alert_type": alert.alert_type,
        "status": alert.status,
        "timeline": timeline,
    }


# ── POST /api/alerts/simulate ──────────────────────────────

@alerts_router.post("/simulate")
async def simulate_alert(
    body: SimulateAlertRequest,
    db: Session = Depends(get_db),
):
    """
    Simulate an alert (JSON Body).
    This replaces the old query-params POST /alerts/simulate.
    """
    import threading

    # We try to import main's singletons; they should be available at runtime
    # after main.py lifespan completes. To avoid circular imports, we access
    # via sys.modules at runtime.
    import sys
    main_module = sys.modules.get("src.main")
    if main_module is None:
        raise HTTPException(status_code=503, detail="System not fully initialized")

    state_graph_engine = main_module.state_graph_engine
    alert_normalizer = main_module.alert_normalizer

    try:
        atype = AlertType(body.alert_type.upper())
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid alert_type: {body.alert_type}")

    from src.models.alert import Alert, DeviceInfo
    from src.models.enums import AlertSeverity, AlertSource

    # G1: Look up device_type + metadata from DB (ADR-RE-007: REAL 回填真实型号/地址/端口)
    device_type = "MOCK"
    matched_device = None
    try:
        from src.database.repositories.device_repository import DeviceRepository
        device_repo = DeviceRepository(db)
        existing = device_repo.list_devices()
        for d in existing:
            if d.device_name == body.device_name:
                device_type = d.device_type or "MOCK"
                matched_device = d
                break
    except Exception:
        pass

    # ADR-RE-007: REAL 回填真实元数据（调用侧显式传参优先）
    device_model = "TP-Link T2600G-28TS"
    device_ip = body.device_ip
    interface_name = body.interface
    if device_type == "REAL" and matched_device is not None:
        device_model = matched_device.device_model or "TL-SG5428"
        if not device_ip or device_ip == "192.168.1.1":
            device_ip = matched_device.device_ip or device_ip
        if not interface_name or interface_name == "Gi0/1":
            interface_name = "Gi1/0/2"

    descriptions = {
        AlertType.MAC_FLAPPING: (
            f"MAC地址 00:1A:2B:3C:4D:5E 在设备 {body.device_name} 的VLAN 1内发生漂移"
        ),
        AlertType.PORT_DOWN: (
            f"接口 {interface_name or 'Gi0/1'} 在设备 {body.device_name} 上状态变更为 down"
        ),
        AlertType.CPU_HIGH: (
            f"设备 {body.device_name} 的CPU利用率在5秒内达到92%，超过告警阈值80%"
        ),
        AlertType.PORT_SHUTDOWN: (
            f"接口 {interface_name or 'Gi0/1'} 在设备 {body.device_name} 上检测到安全威胁，需要紧急隔离关闭"
        ),
    }

    alert = Alert(
        alert_type=atype,
        alert_severity=AlertSeverity.MAJOR,
        alert_content=descriptions.get(atype, f"Simulated {body.alert_type} alert on {body.device_name}"),
        device_info=DeviceInfo(
            device_name=body.device_name,
            device_ip=device_ip,
            device_model=device_model,
            interface_name=interface_name,
            mac_address=body.mac_address,
            cpu_percent=body.cpu_percent,
            device_type=device_type,
        ),
        source=AlertSource.MOCK,
    )

    # ── Persist alert to SQLite database ──
    repo = AlertRepository(db)
    try:
        repo.create_alert({
            "alert_id": alert.alert_id,
            "alert_type": alert.alert_type.value if hasattr(alert.alert_type, 'value') else str(alert.alert_type),
            "severity": alert.alert_severity.value if hasattr(alert.alert_severity, 'value') else str(alert.alert_severity),
            "content": alert.alert_content,
            "device_info": alert.device_info.model_dump() if alert.device_info else {},
            "source": alert.source.value if hasattr(alert.source, 'value') else str(alert.source),
        })
    except Exception as e:
        # Log but don't fail — alert simulation should work even if DB is down
        import logging
        logging.getLogger("uvicorn").warning(f"Failed to persist simulated alert to DB: {e}")

    def run_workflow():
        try:
            result = state_graph_engine.run_workflow(alert)
        except Exception:
            pass

    threading.Thread(target=run_workflow, daemon=True).start()

    return {
        "message": "模拟告警已发送",
        "alert_id": alert.alert_id,
        "alert_type": alert.alert_type,
    }
