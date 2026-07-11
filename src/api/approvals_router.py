"""
MOD-WEB-001: Approvals Router — /api/approvals/* (3 endpoints).
@author sub_agent_software_developer
@module MOD-WEB-001
@covers REQ-WEBUI-FUNC-007, REQ-WEBUI-FUNC-008, REQ-WEBUI-FUNC-009
"""

import sys
import threading
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.api.dependencies import get_db
from src.database.repositories.approval_repository import ApprovalRepository
from src.models.state import ApprovalDecision

approvals_router = APIRouter()


class DecisionRequest(BaseModel):
    decision: str  # APPROVED | REJECTED
    note: str = ""


# ── GET /api/approvals/pending ─────────────────────────────

@approvals_router.get("/pending")
async def get_pending_approvals(db: Session = Depends(get_db)):
    """Return all pending approval items."""
    repo = ApprovalRepository(db)
    items = repo.list_pending_approvals()

    result = []
    for item in items:
        result.append({
            "checkpoint_id": item.checkpoint_id,
            "alert_id": item.alert_id_fk,
            "fix_plan": item.fix_plan,
            "risk_level": item.risk_level,
            "decision": item.decision or "PENDING",
            "created_at": item.created_at.isoformat() if item.created_at else None,
        })

    return {"pending": result, "count": len(result)}


# ── POST /api/approvals/{checkpoint_id}/decide ─────────────

@approvals_router.post("/{checkpoint_id}/decide")
async def decide_approval(
    checkpoint_id: str,
    body: DecisionRequest,
    db: Session = Depends(get_db),
):
    """Make an approval decision (APPROVED / REJECTED)."""
    if body.decision not in ("APPROVED", "REJECTED"):
        raise HTTPException(status_code=400, detail="decision must be APPROVED or REJECTED")

    # Update in database
    repo = ApprovalRepository(db)
    updated = repo.update_approval_decision(
        checkpoint_id=checkpoint_id,
        decision=body.decision,
        decided_by="admin",
        note=body.note,
    )

    # Resume LangGraph workflow
    main_module = sys.modules.get("src.main")
    if main_module:
        decision = ApprovalDecision(
            checkpoint_id=checkpoint_id,
            decision=body.decision,
            operator="admin",
            comment=body.note,
        )

        def resume():
            try:
                result = main_module.state_graph_engine.resume_workflow(checkpoint_id, decision)
            except Exception:
                pass

        threading.Thread(target=resume, daemon=True).start()

    return {
        "message": f"审批已提交: {body.decision}",
        "checkpoint_id": checkpoint_id,
        "decision": body.decision,
    }


# ── GET /api/approvals/history ─────────────────────────────

@approvals_router.get("/history")
async def get_approval_history(
    decision: Optional[str] = Query(None),
    time_from: Optional[str] = Query(None),
    time_to: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Return paginated approval history."""
    repo = ApprovalRepository(db)

    tf = datetime.fromisoformat(time_from) if time_from else None
    tt = datetime.fromisoformat(time_to) if time_to else None

    result = repo.list_approval_history(
        decision=decision,
        time_from=tf,
        time_to=tt,
        page=page,
        page_size=page_size,
    )
    return result
