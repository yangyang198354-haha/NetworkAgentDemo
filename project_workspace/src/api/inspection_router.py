"""
MOD-WEB-001: Inspection Router — /api/inspection/* (10 endpoints in v0.2.0).
@author sub_agent_software_developer
@module MOD-WEB-001
@implements IFC-WEB-001-05~10 (new), IFC-WEB-001-01~04 (enhanced)
@depends MOD-INSP-001, MOD-INSP-002, MOD-WEB-004, MOD-016
@covers REQ-INSP-001, REQ-INSP-004, REQ-INSP-006, REQ-INSP-007, REQ-INSP-009,
        REQ-INSP-011, REQ-WEBUI-FUNC-013, REQ-WEBUI-FUNC-014, REQ-WEBUI-FUNC-015

v0.2.0 enhancements:
  - [NEW] 6 endpoints: status / start / stop / restart / enable / disable
  - [ENH] 4 endpoints: config (retry_backoff + systemd sync), trigger (systemctl start),
          history (+status filter)
  - Retains v0.1.0 backward compatibility for all endpoint URL paths
"""

import subprocess
import sys
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from loguru import logger

from src.api.dependencies import get_db
from src.database.repositories.inspection_repository import InspectionRepository
from src.database.repositories.alert_repository import AlertRepository

inspection_router = APIRouter()


# ── Pydantic Models ──────────────────────────────────────────────

class InspectionConfigUpdate(BaseModel):
    """巡检配置更新请求体 (v0.2.0: polling_interval → retry_backoff)"""
    inspection_interval_minutes: Optional[int] = Field(None, ge=1, le=1440)
    diagnosis_timeout_seconds: Optional[int] = Field(None, ge=1, le=600)
    diagnosis_retry_max: Optional[int] = Field(None, ge=0, le=10)
    retry_backoff_seconds: Optional[int] = Field(None, ge=1, le=300)


class InspectionStatusResponse(BaseModel):
    """GET /api/inspection/status 响应体"""
    timer: Optional[dict] = None
    service: Optional[dict] = None
    last_inspection: Optional[dict] = None
    systemd_available: bool = False
    message: Optional[str] = None


class InspectionActionResponse(BaseModel):
    """systemd 控制操作响应体"""
    result: str           # "success" | "failed" | "rejected"
    action: str           # "start" | "stop" | "restart" | "enable" | "disable"
    message: str
    detail: Optional[str] = None
    service_state: Optional[dict] = None


# ── v0.2.0-unified: Trigger Workflows models (ADR-002) ────────────

class TriggerWorkflowsRequest(BaseModel):
    """Batch workflow trigger request from InspectionCLI."""
    alert_ids: list[str] = Field(
        ..., min_length=1, max_length=50,
        description="Alert UUIDs to trigger workflows for"
    )


class TriggerWorkflowsResponse(BaseModel):
    """Batch workflow trigger response."""
    result: str                         # "accepted"
    record_id: int
    triggered_count: int
    skipped_count: int
    errors: list[str] = []


# ── Lazy-loader for systemd modules (avoids import errors on non-Linux) ─

def _get_systemctl_executor():
    """Lazy import MOD-INSP-002 to avoid import errors on non-Linux systems."""
    from src.systemd.systemctl_executor import SystemctlExecutor
    return SystemctlExecutor()


def _get_systemd_unit_manager():
    """Lazy import MOD-INSP-001 to avoid import errors on non-Linux systems."""
    from src.systemd.systemd_unit_manager import SystemdUnitManager
    from src.systemd.systemctl_executor import SystemctlExecutor
    return SystemdUnitManager(systemctl_executor=SystemctlExecutor())


# ══════════════════════════════════════════════════════════════════
#  v0.1.0 保留端点（增强）
# ══════════════════════════════════════════════════════════════════

# ── GET /api/inspection/config (增强: +retry_backoff) ─────────

@inspection_router.get("/config")
async def get_inspection_config(db: Session = Depends(get_db)):
    """
    Return current inspection configuration.
    v0.2.0: Added diagnosis.retry_backoff; removed ui.polling_interval_seconds.
    """
    repo = InspectionRepository(db)
    config = repo.get_config()
    return {"config": config}


# ── PUT /api/inspection/config (增强: retry_backoff + systemd sync) ──

@inspection_router.put("/config")
async def update_inspection_config(
    body: InspectionConfigUpdate,
    db: Session = Depends(get_db),
):
    """
    Update inspection configuration.
    v0.2.0: Saves retry_backoff, triggers systemd unit file sync on save.
    """
    repo = InspectionRepository(db)
    mapping = {
        "inspection.interval_minutes": body.inspection_interval_minutes,
        "diagnosis.timeout_seconds": body.diagnosis_timeout_seconds,
        "diagnosis.retry_max": body.diagnosis_retry_max,
        "diagnosis.retry_backoff": body.retry_backoff_seconds,
    }
    updates = {k: str(v) for k, v in mapping.items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No valid configuration values provided")

    # Step 1: Write to SQLite
    updated = repo.update_config(updates)

    # Step 2: Trigger systemd unit file sync
    systemd_sync_status = "not_attempted"
    systemd_sync_error = None

    try:
        # Build config dict for systemd sync
        config_for_sync = {
            "interval_minutes": int(updated.get("inspection.interval_minutes", "5")),
            "timeout_seconds": int(updated.get("diagnosis.timeout_seconds", "30")),
        }
        unit_mgr = _get_systemd_unit_manager()
        sync_result = unit_mgr.sync_config_to_systemd(config_for_sync)

        if sync_result.success:
            systemd_sync_status = "success"
            logger.info(f"systemd sync completed: {sync_result.actions_performed}")
        else:
            systemd_sync_status = "failed"
            systemd_sync_error = sync_result.error
            logger.warning(f"systemd sync failed: {sync_result.error}")
    except Exception as e:
        systemd_sync_status = "failed"
        systemd_sync_error = str(e)
        logger.warning(f"systemd sync exception: {e}")

    response = {
        "message": "巡检配置已更新" if systemd_sync_status != "failed" else "配置已保存但 systemd 同步失败",
        "config": updated,
        "systemd_sync": systemd_sync_status,
    }
    if systemd_sync_error:
        response["systemd_error"] = systemd_sync_error

    return response


# ── POST /api/inspection/trigger (增强: systemctl start) ─────

@inspection_router.post("/trigger")
async def trigger_inspection(db: Session = Depends(get_db)):
    """
    Manually trigger an inspection run.
    v0.2.1: Uses subprocess.Popen to call CLI directly with --trigger manual.
            Retains 409 duplicate trigger check via systemd (best-effort).
    """
    # Check if an inspection is already running (systemd-based, best-effort)
    try:
        executor = _get_systemctl_executor()
        service_status = executor.get_service_status()
        if service_status.sub_state == "running":
            raise HTTPException(
                status_code=409,
                detail="巡检正在执行中，请等待完成后再触发"
            )
    except HTTPException:
        raise  # Re-raise HTTP exceptions
    except Exception:
        # If we can't check status (e.g., systemd unavailable), proceed anyway
        pass

    # Trigger via subprocess — direct CLI call, non-blocking
    try:
        project_root = Path(__file__).resolve().parent.parent.parent
        subprocess.Popen(
            [sys.executable, '-m', 'src.inspection_cli', 'run', '--trigger', 'manual'],
            cwd=str(project_root),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"巡检触发失败: {str(e)}"
        )

    return {
        "result": "success",
        "message": "巡检已触发",
        "trigger_mode": "MANUAL",
    }


# ── GET /api/inspection/history (增强: +status 筛选) ─────────

@inspection_router.get("/history")
async def get_inspection_history(
    trigger_mode: Optional[str] = Query(None),
    status: Optional[str] = Query(None, description="SUCCESS / PARTIAL / FAILED"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """
    Return paginated inspection history.
    v0.2.0: Added status filter and status field in response.
    """
    repo = InspectionRepository(db)
    result = repo.list_history(
        trigger_mode=trigger_mode,
        status=status,
        page=page,
        page_size=page_size,
    )
    return result


# ══════════════════════════════════════════════════════════════════
#  v0.2.0 新增端点：systemd 状态查询与生命周期控制
# ══════════════════════════════════════════════════════════════════

# ── GET /api/inspection/status [NEW: IFC-WEB-001-05] ────────

@inspection_router.get("/status", response_model=InspectionStatusResponse)
async def get_inspection_status(db: Session = Depends(get_db)):
    """
    Query systemd timer + service real-time status.
    Also returns the latest inspection record summary.

    v0.2.0: New endpoint for REQ-INSP-004 (status query) and
            REQ-INSP-005 (Web UI status panel).
    """
    executor = _get_systemctl_executor()

    # Check systemd availability
    avail = executor.check_systemd_available()
    if not avail.available:
        # Return degraded response (REQ-INSP-NF-006)
        repo = InspectionRepository(db)
        last = repo.get_latest_inspection()
        return InspectionStatusResponse(
            timer=None,
            service=None,
            last_inspection=last,
            systemd_available=False,
            message="当前环境不支持 systemd，定时巡检功能不可用。手动触发仍可使用。",
        )

    # Query timer and service status
    try:
        timer = executor.get_timer_status()
    except Exception as e:
        logger.warning(f"Failed to get timer status: {e}")
        timer = None

    try:
        service = executor.get_service_status()
    except Exception as e:
        logger.warning(f"Failed to get service status: {e}")
        service = None

    # Query latest inspection record
    repo = InspectionRepository(db)
    last = repo.get_latest_inspection()

    return InspectionStatusResponse(
        timer={
            "active_state": timer.active_state if timer else "not-found",
            "unit_file_state": timer.unit_file_state if timer else "not-found",
            "next_trigger": timer.next_trigger.isoformat() if timer and timer.next_trigger else None,
            "last_trigger": timer.last_trigger.isoformat() if timer and timer.last_trigger else None,
        } if timer else None,
        service={
            "active_state": service.active_state if service else "not-found",
            "sub_state": service.sub_state if service else "not-found",
            "last_result": service.last_result if service else "not-found",
            "last_execution": service.last_execution.isoformat() if service and service.last_execution else None,
        } if service else None,
        last_inspection=last,
        systemd_available=True,
    )


# ── POST /api/inspection/start [NEW: IFC-WEB-001-06] ────────

@inspection_router.post("/start", response_model=InspectionActionResponse)
async def start_inspection_service():
    """Start networkagent-inspection.service (systemctl start)."""
    executor = _get_systemctl_executor()

    avail = executor.check_systemd_available()
    if not avail.available:
        raise HTTPException(status_code=503, detail="当前环境不支持 systemd，无法执行此操作")

    try:
        result = executor.start_service()
        if not result.success:
            raise HTTPException(status_code=500, detail=result.message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"启动失败: {str(e)}")

    return InspectionActionResponse(
        result="success",
        action="start",
        message="巡检服务已启动",
        detail=result.detail,
    )


# ── POST /api/inspection/stop [NEW: IFC-WEB-001-07] ─────────

@inspection_router.post("/stop", response_model=InspectionActionResponse)
async def stop_inspection_service():
    """
    Stop networkagent-inspection.service (systemctl stop).
    Note: Only stops the service process, timer continues its schedule.
    """
    executor = _get_systemctl_executor()

    avail = executor.check_systemd_available()
    if not avail.available:
        raise HTTPException(status_code=503, detail="当前环境不支持 systemd，无法执行此操作")

    try:
        result = executor.stop_service()
        if not result.success:
            raise HTTPException(status_code=500, detail=result.message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"停止失败: {str(e)}")

    return InspectionActionResponse(
        result="success",
        action="stop",
        message="巡检服务已停止",
        detail=result.detail,
    )


# ── POST /api/inspection/restart [NEW: IFC-WEB-001-08] ──────

@inspection_router.post("/restart", response_model=InspectionActionResponse)
async def restart_inspection_service():
    """Restart networkagent-inspection.service (systemctl restart)."""
    executor = _get_systemctl_executor()

    avail = executor.check_systemd_available()
    if not avail.available:
        raise HTTPException(status_code=503, detail="当前环境不支持 systemd，无法执行此操作")

    try:
        result = executor.restart_service()
        if not result.success:
            raise HTTPException(status_code=500, detail=result.message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"重启失败: {str(e)}")

    return InspectionActionResponse(
        result="success",
        action="restart",
        message="巡检服务已重启",
        detail=result.detail,
    )


# ── POST /api/inspection/enable [NEW: IFC-WEB-001-09] ───────

@inspection_router.post("/enable", response_model=InspectionActionResponse)
async def enable_inspection_timer():
    """
    Enable networkagent-inspection.timer (systemctl enable + start).
    Sets timer to start on boot and starts immediately.
    """
    executor = _get_systemctl_executor()

    avail = executor.check_systemd_available()
    if not avail.available:
        raise HTTPException(status_code=503, detail="当前环境不支持 systemd，无法执行此操作")

    try:
        result = executor.enable_timer()
        if not result.success:
            raise HTTPException(status_code=500, detail=result.message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"启用失败: {str(e)}")

    return InspectionActionResponse(
        result="success",
        action="enable",
        message=result.message,
        detail=result.detail,
    )


# ── POST /api/inspection/disable [NEW: IFC-WEB-001-10] ──────

@inspection_router.post("/disable", response_model=InspectionActionResponse)
async def disable_inspection_timer():
    """
    Disable networkagent-inspection.timer (systemctl stop + disable).
    Stops the timer and prevents auto-start on reboot.
    Manual trigger still works.
    """
    executor = _get_systemctl_executor()

    avail = executor.check_systemd_available()
    if not avail.available:
        raise HTTPException(status_code=503, detail="当前环境不支持 systemd，无法执行此操作")

    try:
        result = executor.disable_timer()
        if not result.success:
            raise HTTPException(status_code=500, detail=result.message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"禁用失败: {str(e)}")

    return InspectionActionResponse(
        result="success",
        action="disable",
        message=result.message,
        detail=result.detail,
    )


# ── GET /api/inspection/journal [NEW: v0.2.1] ──────────
#   REQ-FUNC-001: journalctl log query endpoint (JWT via global api_router)
#   REQ-FUNC-005: Zero-changes to this portion.

@inspection_router.get("/journal")
async def get_inspection_journal(
    lines: int = Query(default=100, ge=10, le=500),
):
    """
    Query systemd journal for networkagent-inspection.service logs.

    Returns recent N lines of inspection service logs from journalctl.
    JWT-protected via the global api_router dependency (Depends(get_current_user)).

    Args:
        lines: Number of log lines to return (10-500, default 100).

    Returns:
        {"lines": ["line1", "line2", ...]}

    Errors:
        503 — journalctl timeout or not available
        422 — lines out of range (handled by FastAPI)
    """
    try:
        result = subprocess.run(
            ['journalctl', '-u', 'networkagent-inspection.service', '--no-pager',
             '-n', str(lines)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return {"lines": result.stdout.splitlines()}
    except subprocess.TimeoutExpired:
        raise HTTPException(
            status_code=503,
            detail="日志查询超时，请稍后重试"
        )
    except FileNotFoundError:
        raise HTTPException(
            status_code=503,
            detail="当前环境不支持 journalctl，日志查询不可用"
        )


# ── POST /api/inspection/{record_id}/trigger-workflows [ADR-002] ──
# NOTE: This handler is registered directly in main.py (not via api_router)
# because it must be accessible from localhost without JWT auth.
# The api_router applies Depends(get_current_user) globally.

async def trigger_inspection_workflows_handler(
    record_id: int,
    body: TriggerWorkflowsRequest,
    db: Session,
):
    """
    [NEW v0.2.0-unified] Batch trigger LangGraph workflows for
    inspection-created alerts.

    Called by InspectionCLI after persisting alerts and inspection record.
    Each alert_id spawns a daemon thread via existing StateGraphEngine.
    Idempotent: skips alerts already in non-PROCESSING status.

    Registered without JWT (internal localhost endpoint, ADR-002).
    """
    import threading
    import sys

    repo = InspectionRepository(db)
    record = repo.get_by_id(record_id)
    if not record:
        raise HTTPException(
            status_code=404,
            detail=f"InspectionRecord #{record_id} not found",
        )

    main_module = sys.modules.get("src.main")
    if main_module is None:
        raise HTTPException(
            status_code=503,
            detail="System not fully initialized",
        )

    state_graph_engine = main_module.state_graph_engine
    alert_repo = AlertRepository(db)

    triggered = 0
    skipped = 0
    errors: list[str] = []

    for alert_id in body.alert_ids:
        try:
            alert = alert_repo.get_alert_by_id(alert_id)
            if not alert:
                errors.append(f"Alert {alert_id}: not found")
                skipped += 1
                continue

            if alert.status != "PROCESSING":
                skipped += 1
                continue

            from src.models.alert import Alert as DomainAlert, DeviceInfo
            from src.models.enums import AlertType, AlertSeverity, AlertSource

            domain_alert = DomainAlert(
                alert_id=alert.alert_id,
                alert_type=AlertType(alert.alert_type),
                alert_severity=AlertSeverity(alert.severity) if alert.severity else AlertSeverity.WARNING,
                alert_content=alert.content,
                device_info=DeviceInfo(**alert.device_info) if alert.device_info else DeviceInfo(
                    device_name="unknown", device_ip="unknown"
                ),
                source=AlertSource(alert.source) if alert.source else AlertSource.INSPECTION,
            )

            def _run_workflow(a=domain_alert):
                try:
                    state_graph_engine.run_workflow(a)
                except Exception:
                    pass

            threading.Thread(target=_run_workflow, daemon=True).start()
            triggered += 1
            logger.info(f"Workflow triggered for alert {alert_id}")

        except Exception as e:
            errors.append(f"Alert {alert_id}: {str(e)}")
            skipped += 1

    return TriggerWorkflowsResponse(
        result="accepted",
        record_id=record_id,
        triggered_count=triggered,
        skipped_count=skipped,
        errors=errors,
    )
