"""
MOD-WEB-003: Inspection Model — inspection_records table.
@author sub_agent_software_developer
@module MOD-WEB-003
@implements InspectionRecord (inspection_records 表)
@covers REQ-WEBUI-FUNC-013, REQ-WEBUI-FUNC-015
"""

from datetime import datetime, timezone
from typing import Optional, Any

from sqlalchemy import String, Integer, DateTime, JSON, Index
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class InspectionRecord(Base):
    """Inspection execution record — persisted inspection history."""

    __tablename__ = "inspection_records"
    __table_args__ = (
        Index("idx_inspections_trigger_started", "trigger_mode", "started_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trigger_mode: Mapped[str] = mapped_column(
        String(15), nullable=False, index=True,
        comment="SCHEDULED / MANUAL"
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc),
        comment="巡检开始时间"
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, comment="巡检完成时间"
    )
    total_devices: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="检查设备总数"
    )
    anomaly_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="发现异常数"
    )
    details: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, comment="巡检详情"
    )

    def __repr__(self) -> str:
        return f"<InspectionRecord(id={self.id}, trigger='{self.trigger_mode}', anomalies={self.anomaly_count})>"
