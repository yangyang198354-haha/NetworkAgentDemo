"""
MOD-WEB-001: Alerts Router — GET/POST /api/alerts* (4 endpoints).
@author sub_agent_software_developer
@module MOD-WEB-001
@covers REQ-WEBUI-FUNC-001, REQ-WEBUI-FUNC-002, REQ-WEBUI-FUNC-003, REQ-WEBUI-FUNC-004
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
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

    # Try to read fix_plan + approval from LangGraph checkpoint
    fix_plan = None
    commands = []
    approval_info = None
    try:
        import sys
        main_module = sys.modules.get("src.main")
        if main_module:
            state = main_module.state_graph_engine.get_workflow_state(alert_id)
            if state:
                fp = state.get("fix_plan")
                if fp and isinstance(fp, dict):
                    fix_plan = {
                        "template_id": fp.get("template_id", ""),
                        "description": fp.get("description", ""),
                        "params": fp.get("params", {}),
                    }
                    commands = fp.get("commands", [])
                # Extract approval info from LangGraph state
                approval_info = {
                    "need_human_approval": state.get("need_human_approval", False),
                    "approval_status": state.get("approval_status", "NOT_REQUIRED"),
                    "risk_level": state.get("risk_level", "LOW"),
                }
    except Exception:
        pass  # LangGraph state unavailable, return without fix_plan/approval

    # Try to read memory timeline from NodeHandlers
    memory_timeline = []
    try:
        if main_module:
            memory_timeline = main_module.node_handlers.get_timeline(alert_id)
    except Exception:
        pass

    # Try to read LLM call records
    llm_calls = []
    try:
        if main_module:
            llm_calls = main_module.llm_service.get_llm_logs(alert_id)
    except Exception:
        pass

    # Use memory timeline if available (from current process), fallback to DB
    effective_timeline = memory_timeline if memory_timeline else timeline

    return {
        "alert": alert,
        "timeline": effective_timeline,
        "fix_plan": fix_plan,
        "commands": commands,
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

    descriptions = {
        AlertType.MAC_FLAPPING: (
            f"MAC地址 00:1A:2B:3C:4D:5E 在设备 {body.device_name} 的VLAN 1内发生漂移"
        ),
        AlertType.PORT_DOWN: (
            f"接口 {body.interface or 'Gi0/1'} 在设备 {body.device_name} 上状态变更为 down"
        ),
        AlertType.CPU_HIGH: (
            f"设备 {body.device_name} 的CPU利用率在5秒内达到92%，超过告警阈值80%"
        ),
        AlertType.PORT_SHUTDOWN: (
            f"接口 {body.interface or 'Gi0/1'} 在设备 {body.device_name} 上检测到安全威胁，需要紧急隔离关闭"
        ),
    }

    alert = Alert(
        alert_type=atype,
        alert_severity=AlertSeverity.MAJOR,
        alert_content=descriptions.get(atype, f"Simulated {body.alert_type} alert on {body.device_name}"),
        device_info=DeviceInfo(
            device_name=body.device_name,
            device_ip=body.device_ip,
            device_model="TP-Link T2600G-28TS",
            interface_name=body.interface,
            mac_address=body.mac_address,
            cpu_percent=body.cpu_percent,
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
