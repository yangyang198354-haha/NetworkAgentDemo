"""
MOD-DP-002: LLMCallLog Model — llm_calls table.
@author sub_agent_software_developer
@module MOD-DP-002
@implements IFC-DP-002-01 ~ IFC-DP-002-11
@depends MOD-WEB-003 (Base)
@covers REQ-FUNC-002
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import String, Integer, Float, Text, DateTime, Boolean, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class LLMCallLog(Base):
    """LLM call log record — one row per LLM API invocation."""

    __tablename__ = "llm_calls"
    __table_args__ = (
        # IFC-DP-002-02: index on alert_id_fk for efficient per-alert queries
        Index("idx_llm_calls_alert", "alert_id_fk"),
        # IFC-DP-002-03: index on endpoint for filtering/aggregation
        Index("idx_llm_calls_endpoint", "endpoint"),
    )

    # IFC-DP-002-01: id (PK, autoincrement)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # IFC-DP-002-02: alert_id_fk (FK -> alerts.alert_id, ON DELETE CASCADE)
    alert_id_fk: Mapped[str] = mapped_column(
        String(36), ForeignKey("alerts.alert_id", ondelete="CASCADE"),
        nullable=False, index=True, comment="关联告警alert_id"
    )

    # IFC-DP-002-03: endpoint — LLM call endpoint identifier
    endpoint: Mapped[str] = mapped_column(
        String(50), nullable=False,
        comment="analyze_root_cause / fill_template_params / generate_report / mock"
    )

    # IFC-DP-002-04: timestamp — call timestamp
    timestamp: Mapped[datetime] = mapped_column(
        DateTime, nullable=False,
        default=lambda: datetime.now(timezone.utc),
        comment="LLM调用时间戳"
    )

    # IFC-DP-002-05: elapsed_s — call duration in seconds
    elapsed_s: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0,
        comment="调用耗时（秒）"
    )

    # IFC-DP-002-06: prompt_tokens — prompt token count
    prompt_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0,
        comment="prompt token用量"
    )

    # IFC-DP-002-07: completion_tokens — completion token count
    completion_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0,
        comment="completion token用量"
    )

    # IFC-DP-002-08: prompt_summary — truncated prompt text (max 3000 chars)
    prompt_summary: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
        comment="prompt摘要（截断至3000字符）"
    )

    # IFC-DP-002-09: response_summary — truncated response text (max 3000 chars)
    response_summary: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
        comment="response摘要（截断至3000字符）"
    )

    # IFC-DP-002-10: is_mock — whether this was a mock (no API key) call
    is_mock: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False,
        comment="是否为Mock调用（无API key时的fallback）"
    )

    # IFC-DP-002-11: created_at — record creation timestamp
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False,
        default=lambda: datetime.now(timezone.utc),
        comment="记录创建时间"
    )

    def __repr__(self) -> str:
        return f"<LLMCallLog(id={self.id}, alert_id='{self.alert_id_fk}', endpoint='{self.endpoint}', mock={self.is_mock})>"
