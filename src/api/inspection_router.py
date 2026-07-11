"""
MOD-WEB-001: Inspection Router — /api/inspection/* (4 endpoints).
@author sub_agent_software_developer
@module MOD-WEB-001
@covers REQ-WEBUI-FUNC-013, REQ-WEBUI-FUNC-014, REQ-WEBUI-FUNC-015
"""

import sys
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional

from src.api.dependencies import get_db
from src.database.repositories.inspection_repository import InspectionRepository

inspection_router = APIRouter()


class InspectionConfigUpdate(BaseModel):
    inspection_interval_minutes: Optional[int] = None
    diagnosis_timeout_seconds: Optional[int] = None
    diagnosis_retry_max: Optional[int] = None
    polling_interval_seconds: Optional[int] = None


# ── GET /api/inspection/config ─────────────────────────────

@inspection_router.get("/config")
async def get_inspection_config(db: Session = Depends(get_db)):
    """Return current inspection configuration."""
    repo = InspectionRepository(db)
    config = repo.get_config()
    return {"config": config}


# ── PUT /api/inspection/config ─────────────────────────────

@inspection_router.put("/config")
async def update_inspection_config(
    body: InspectionConfigUpdate,
    db: Session = Depends(get_db),
):
    """Update inspection configuration."""
    repo = InspectionRepository(db)
    mapping = {
        "inspection.interval_minutes": body.inspection_interval_minutes,
        "diagnosis.timeout_seconds": body.diagnosis_timeout_seconds,
        "diagnosis.retry_max": body.diagnosis_retry_max,
        "ui.polling_interval_seconds": body.polling_interval_seconds,
    }
    updates = {k: str(v) for k, v in mapping.items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No valid configuration values provided")

    updated = repo.update_config(updates)
    return {"message": "巡检配置已更新", "config": updated}


# ── POST /api/inspection/trigger ───────────────────────────

@inspection_router.post("/trigger")
async def trigger_inspection(db: Session = Depends(get_db)):
    """Manually trigger an inspection run."""
    main_module = sys.modules.get("src.main")
    if main_module is None:
        raise HTTPException(status_code=503, detail="System not initialized")

    # Check if an inspection is already running
    if hasattr(main_module.inspection_scheduler, "_inspection_running") and \
       main_module.inspection_scheduler._inspection_running:
        raise HTTPException(
            status_code=409,
            detail="巡检任务正在执行中，请等待完成后再触发",
        )

    # Run inspection in background thread
    import threading
    def run_inspection():
        try:
            main_module.inspection_scheduler._inspection_running = True
            main_module.inspection_scheduler.run_inspection_once()
        finally:
            main_module.inspection_scheduler._inspection_running = False

    threading.Thread(target=run_inspection, daemon=True).start()

    return {"message": "巡检已触发", "status": "running"}


# ── GET /api/inspection/history ────────────────────────────

@inspection_router.get("/history")
async def get_inspection_history(
    trigger_mode: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Return paginated inspection history."""
    repo = InspectionRepository(db)
    result = repo.list_history(
        trigger_mode=trigger_mode,
        page=page,
        page_size=page_size,
    )
    return result
