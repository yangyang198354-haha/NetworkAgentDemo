"""
MOD-WEB-003: Config Models — system_config + audit_logs tables.
@author sub_agent_software_developer
@module MOD-WEB-003
@implements SystemConfig (system_config 表), AuditLog (audit_logs 表)
@covers REQ-WEBUI-FUNC-019, REQ-WEBUI-FUNC-021
"""

from datetime import datetime, timezone
from typing import Optional, Any

from sqlalchemy import String, Integer, Text, DateTime, JSON, Index
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class SystemConfig(Base):
    """Key-value system configuration store."""

    __tablename__ = "system_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    config_key: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, index=True, comment="配置键"
    )
    config_value: Mapped[str] = mapped_column(
        Text, nullable=False, comment="配置值（字符串存储，使用时类型转换）"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        comment="最后更新时间"
    )

    def __repr__(self) -> str:
        val_preview = self.config_value[:30] if self.config_value else ""
        return f"<SystemConfig(key='{self.config_key}', value='{val_preview}...')>"


class AuditLog(Base):
    """Audit / operations log — persisted log entries."""

    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("idx_auditlogs_timestamp_level", "timestamp", "level"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, index=True,
        default=lambda: datetime.now(timezone.utc), comment="日志时间戳"
    )
    level: Mapped[str] = mapped_column(
        String(10), nullable=False, index=True,
        comment="INFO / WARNING / ERROR"
    )
    module: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="来源模块"
    )
    message: Mapped[str] = mapped_column(
        Text, nullable=False, comment="日志消息内容"
    )
    details: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSON, nullable=True, comment="附加详情JSON"
    )

    def __repr__(self) -> str:
        return f"<AuditLog(id={self.id}, level='{self.level}', module='{self.module}')>"
