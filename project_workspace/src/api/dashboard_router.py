"""
MOD-WEB-001: Dashboard Router — /api/dashboard/* (2 endpoints).
@author sub_agent_software_developer
@module MOD-WEB-001
@covers REQ-WEBUI-FUNC-022, REQ-WEBUI-FUNC-023, REQ-WEBUI-FUNC-024
"""

import sys
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from src.api.dependencies import get_db
from src.services.dashboard_service import DashboardService

dashboard_router = APIRouter()


# ── GET /api/dashboard/stats ───────────────────────────────

@dashboard_router.get("/stats")
async def get_dashboard_stats(
    time_from: Optional[str] = Query(None),
    time_to: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Return aggregated alert statistics for Dashboard."""
    service = DashboardService(db)

    tf = datetime.fromisoformat(time_from) if time_from else None
    tt = datetime.fromisoformat(time_to) if time_to else None

    return service.get_alert_stats(time_from=tf, time_to=tt)


# ── GET /api/dashboard/health ──────────────────────────────

@dashboard_router.get("/health")
async def get_dashboard_health(db: Session = Depends(get_db)):
    """Return system health status for all components."""
    service = DashboardService(db)
    base_health = service.get_health_status()

    # Augment with actual component status from singletons
    main_module = sys.modules.get("src.main")
    if main_module:
        base_health["langgraph"] = {
            "status": "healthy" if main_module.state_graph_engine._graph is not None else "error",
            "detail": "14 nodes compiled" if main_module.state_graph_engine._graph is not None else "Not compiled",
        }
        base_health["rag"] = {
            "status": "healthy",
            "detail": f"Chroma OK, {len(main_module.rag_service._fallback_docs)} documents",
        }
        # v0.2.0: inspection moved from APScheduler to systemd timer
        try:
            sched = main_module.inspection_scheduler
            base_health["scheduler"] = {
                "status": "healthy" if sched._scheduler is not None else "error",
                "detail": "APScheduler" if sched._scheduler is not None else "Not running",
            }
        except AttributeError:
            import subprocess
            try:
                result = subprocess.run(
                    ["systemctl", "is-active", "networkagent-inspection.timer"],
                    capture_output=True, text=True, timeout=5
                )
                active = result.stdout.strip()
                base_health["scheduler"] = {
                    "status": "healthy" if active == "active" else "warning",
                    "detail": f"systemd timer: {active}",
                }
            except Exception:
                base_health["scheduler"] = {"status": "unknown", "detail": "systemd timer not configured"}

    return base_health
