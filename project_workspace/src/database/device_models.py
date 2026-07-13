"""
MOD-WEB-003: Device Models — devices + device_credentials tables.
@author sub_agent_software_developer
@module MOD-WEB-003
@implements Device (devices 表), DeviceCredential (device_credentials 表)
@covers REQ-WEBUI-FUNC-010, REQ-WEBUI-FUNC-011
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import String, Integer, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin


class Device(Base, TimestampMixin):
    """Managed network device."""

    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_name: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, index=True, comment="设备名称"
    )
    device_ip: Mapped[str] = mapped_column(
        String(15), nullable=False, comment="IPv4地址"
    )
    device_model: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True, comment="设备型号"
    )
    group_name: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True, comment="所属分组"
    )
    status: Mapped[Optional[str]] = mapped_column(
        String(15), nullable=True, default="UNKNOWN",
        comment="ONLINE / OFFLINE / UNKNOWN"
    )
    last_diag_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, comment="最近一次诊断时间"
    )

    # ── Relationships (one-to-one with DeviceCredential) ──
    credential: Mapped[Optional["DeviceCredential"]] = relationship(
        "DeviceCredential", back_populates="device", uselist=False,
        cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Device(name='{self.device_name}', ip='{self.device_ip}')>"


class DeviceCredential(Base, TimestampMixin):
    """Encrypted SSH credentials for a managed device (one-to-one)."""

    __tablename__ = "device_credentials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("devices.id", ondelete="CASCADE"),
        unique=True, nullable=False, comment="关联设备ID"
    )
    ssh_username: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="SSH用户名"
    )
    ssh_password_encrypted: Mapped[str] = mapped_column(
        String(512), nullable=False, comment="AES加密后的密码 (Fernet token)"
    )
    ssh_port: Mapped[int] = mapped_column(
        Integer, nullable=False, default=22, comment="SSH端口"
    )

    # ── Relationships ──
    device: Mapped["Device"] = relationship("Device", back_populates="credential")

    def __repr__(self) -> str:
        return f"<DeviceCredential(device_id={self.device_id}, user='{self.ssh_username}')>"
