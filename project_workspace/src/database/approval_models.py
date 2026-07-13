"""
MOD-WEB-003: Approval Model — approvals table.
@author sub_agent_software_developer
@module MOD-WEB-003
@implements Approval (approvals 表)
@covers REQ-WEBUI-FUNC-007, REQ-WEBUI-FUNC-008, REQ-WEBUI-FUNC-009
"""

from datetime import datetime, timezone
from typing import Optional, Any

from sqlalchemy import String, Integer, Text, DateTime, JSON, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Approval(Base):
    """Approval record — persists LangGraph interrupt-based approval decisions."""

    __tablename__ = "approvals"
    __table_args__ = (
        Index("idx_approvals_alert_decision", "alert_id_fk", "decision"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    alert_id_fk: Mapped[str] = mapped_column(
        String(36), ForeignKey("alerts.alert_id", ondelete="CASCADE"),
        nullable=False, index=True, comment="关联告警alert_id"
    )
    checkpoint_id: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False,
        comment="LangGraph Interrupt checkpoint ID"
    )
    fix_plan: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, comment="修复方案完整内容"
    )
    risk_level: Mapped[str] = mapped_column(
        String(10), nullable=False,
        comment="LOW / MEDIUM / HIGH / CRITICAL"
    )
    decision: Mapped[Optional[str]] = mapped_column(
        String(10), nullable=True, index=True,
        comment="PENDING / APPROVED / REJECTED"
    )
    decided_by: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True, comment="审批人（Demo固定admin）"
    )
    decided_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, comment="审批时间"
    )
    note: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="审批备注（拒绝原因等）"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc),
        comment="审批挂起时间"
    )

    # ── Relationships ──
    alert: Mapped["Alert"] = relationship("Alert", back_populates="approvals")

    def __repr__(self) -> str:
        return f"<Approval(checkpoint='{self.checkpoint_id}', decision='{self.decision}')>"
