"""
MOD-WEB-004: ApprovalRepository — Approval CRUD operations.
@author sub_agent_software_developer
@module MOD-WEB-004
@implements ApprovalRepository (list_pending_approvals, get_approval_by_checkpoint,
           create_approval, update_approval_decision, list_approval_history)
@depends MOD-WEB-003
@covers REQ-WEBUI-FUNC-007, REQ-WEBUI-FUNC-008, REQ-WEBUI-FUNC-009
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, func, desc
from sqlalchemy.orm import Session

from src.database.approval_models import Approval


class ApprovalRepository:
    """Repository for Approval entities."""

    def __init__(self, db: Session):
        self.db = db

    # ── list_pending_approvals ──────────────────────────────

    def list_pending_approvals(self) -> list[Approval]:
        """Return all approvals with decision=PENDING (or None)."""
        stmt = (
            select(Approval)
            .where((Approval.decision == "PENDING") | (Approval.decision.is_(None)))
            .order_by(desc(Approval.created_at))
        )
        return list(self.db.execute(stmt).scalars().all())

    # ── get_approval_by_checkpoint ──────────────────────────

    def get_approval_by_checkpoint(self, checkpoint_id: str) -> Approval | None:
        """Find an approval record by its LangGraph checkpoint_id."""
        stmt = select(Approval).where(Approval.checkpoint_id == checkpoint_id)
        return self.db.execute(stmt).scalar_one_or_none()

    # ── create_approval ─────────────────────────────────────

    def create_approval(self, approval_data: dict) -> Approval:
        """Create and persist a new Approval record."""
        approval = Approval(**approval_data)
        self.db.add(approval)
        self.db.commit()
        self.db.refresh(approval)
        return approval

    # ── update_approval_decision ────────────────────────────

    def update_approval_decision(
        self,
        checkpoint_id: str,
        decision: str,
        decided_by: str = "admin",
        note: str = "",
    ) -> Approval | None:
        """Record an approval decision (APPROVED / REJECTED)."""
        approval = self.get_approval_by_checkpoint(checkpoint_id)
        if approval:
            approval.decision = decision
            approval.decided_by = decided_by
            approval.decided_at = datetime.now(timezone.utc)
            approval.note = note
            self.db.commit()
            self.db.refresh(approval)
        return approval

    # ── IFC-DP-005-01: get_approvals_by_alert_id ──────────────

    def get_approvals_by_alert_id(self, alert_id: str) -> list[Approval]:
        """
        Return all approval records for a given alert_id, ordered by created_at DESC.

        Args:
            alert_id: str — the alerts.alert_id value (maps to approvals.alert_id_fk).

        Returns:
            list[Approval] — empty list if no approval records found.
        """
        stmt = (
            select(Approval)
            .where(Approval.alert_id_fk == alert_id)
            .order_by(desc(Approval.created_at))
        )
        return list(self.db.execute(stmt).scalars().all())

    # ── list_approval_history ───────────────────────────────

    def list_approval_history(
        self,
        decision: str | None = None,
        time_from: datetime | None = None,
        time_to: datetime | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        """Return paginated approval history with optional filtering."""
        query = select(Approval)

        if decision:
            query = query.where(Approval.decision == decision)
        if time_from:
            query = query.where(Approval.created_at >= time_from)
        if time_to:
            query = query.where(Approval.created_at <= time_to)

        count_query = select(func.count()).select_from(query.subquery())
        total = self.db.execute(count_query).scalar() or 0

        query = query.order_by(desc(Approval.created_at))
        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size)

        rows = self.db.execute(query).scalars().all()

        return {
            "items": list(rows),
            "total": total,
            "page": page,
            "page_size": page_size,
        }
