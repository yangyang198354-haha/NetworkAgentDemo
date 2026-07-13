"""
MOD-WEB-003: Alert Models — alerts + alert_timeline tables.
@author sub_agent_software_developer
@module MOD-WEB-003
@implements Alert (alerts 表), AlertTimeline (alert_timeline 表)
@covers REQ-WEBUI-FUNC-001, REQ-WEBUI-FUNC-002
"""

from datetime import datetime, timezone
from typing import Optional, Any

from sqlalchemy import String, Integer, Text, DateTime, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin


class Alert(Base, TimestampMixin):
    """Alert main table — persistent alert records."""

    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    alert_id: Mapped[str] = mapped_column(
        String(36), unique=True, nullable=False, index=True,
        comment="UUID格式告警唯一标识"
    )
    alert_type: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True,
        comment="MAC_FLAPPING / PORT_DOWN / CPU_HIGH"
    )
    severity: Mapped[str] = mapped_column(
        String(10), nullable=False,
        comment="CRITICAL / MAJOR / MINOR / WARNING"
    )
    content: Mapped[str] = mapped_column(
        Text, nullable=False, comment="告警描述文本"
    )
    device_info: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, comment="设备信息JSON"
    )
    source: Mapped[str] = mapped_column(
        String(15), nullable=False, index=True,
        comment="WEBHOOK / INSPECTION / MOCK"
    )
    status: Mapped[str] = mapped_column(
        String(15), nullable=False, index=True, default="PROCESSING",
        comment="PROCESSING / CLOSED / FAILED / REJECTED"
    )
    # ★ MOD-DP-001: 新增 workflow_state JSON 列 ★
    workflow_state: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSON, nullable=True, default=None,
        comment="工作流状态JSON: {fix_plan,root_cause,diag_result,exec_log,verify_result,final_report,_completed}"
    )

    # ── Relationships ──
    timeline: Mapped[list["AlertTimeline"]] = relationship(
        "AlertTimeline", back_populates="alert", cascade="all, delete-orphan"
    )
    approvals: Mapped[list["Approval"]] = relationship(
        "Approval", back_populates="alert", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Alert(alert_id='{self.alert_id}', type='{self.alert_type}', status='{self.status}')>"


class AlertTimeline(Base):
    """Alert processing timeline — one entry per executed LangGraph node."""

    __tablename__ = "alert_timeline"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    alert_id_fk: Mapped[str] = mapped_column(
        String(36), ForeignKey("alerts.alert_id", ondelete="CASCADE"),
        nullable=False, index=True, comment="关联告警alert_id"
    )
    node_name: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="节点名称"
    )
    state_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, comment="节点执行时NetworkAgentState快照"
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc),
        comment="节点开始执行时间"
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, comment="节点完成时间"
    )
    status: Mapped[str] = mapped_column(
        String(15), nullable=False, default="RUNNING",
        comment="RUNNING / COMPLETED / FAILED"
    )

    # ── Relationships ──
    alert: Mapped["Alert"] = relationship("Alert", back_populates="timeline")

    def __repr__(self) -> str:
        return f"<AlertTimeline(alert_id='{self.alert_id_fk}', node='{self.node_name}', status='{self.status}')>"
