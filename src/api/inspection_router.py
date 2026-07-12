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

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from loguru import logger

from src.api.dependencies import get_db
from src.database.repositories.inspection_repository import InspectionRepository

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
    v0.2.0: Uses systemctl start networkagent-inspection.service (PM Q-INSP-003).
            Returns 503 if systemd is not available.
    """
    executor = _get_systemctl_executor()

    # Check systemd availability
    avail = executor.check_systemd_available()
    if not avail.available:
        raise HTTPException(
            status_code=503,
            detail="请先配置巡检服务：当前环境不支持 systemd，无法触发巡检。"
                   "请确保系统安装了 systemd 并正确配置。"
        )

    # Check if service is already running
    try:
        service_status = executor.get_service_status()
        if service_status.sub_state == "running":
            raise HTTPException(
                status_code=409,
                detail="巡检正在执行中，请等待完成后再触发"
            )
    except Exception:
        # If we can't check status, proceed anyway
        pass

    # Trigger via systemctl start
    result = executor.start_service()
    if not result.success:
        raise HTTPException(
            status_code=500,
            detail=f"巡检触发失败: {result.message}"
        )

    return {
        "result": "success",
        "message": "巡检已触发",
        "trigger_mode": "MANUAL",
        "detail": result.detail,
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
