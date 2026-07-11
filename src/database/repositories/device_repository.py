"""
MOD-WEB-004: DeviceRepository — Device and DeviceCredential CRUD.
@author sub_agent_software_developer
@module MOD-WEB-004
@implements DeviceRepository (list_devices, get_device_by_id, create_device,
           update_device, delete_device, get_device_active_alert_count,
           upsert_credentials, get_device_diagnostics)
@depends MOD-WEB-003
@covers REQ-WEBUI-FUNC-010, REQ-WEBUI-FUNC-011, REQ-WEBUI-FUNC-012
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.orm import Session, joinedload

from src.database.device_models import Device, DeviceCredential
from src.database.alert_models import Alert


class DeviceRepository:
    """Repository for Device and DeviceCredential entities."""

    def __init__(self, db: Session):
        self.db = db

    # ── list_devices ────────────────────────────────────────

    def list_devices(self) -> list[Device]:
        """Return all managed devices, eager-loading credentials."""
        stmt = select(Device).outerjoin(Device.credential).options(
            joinedload(Device.credential)
        ).order_by(Device.device_name)
        return list(self.db.execute(stmt).unique().scalars().all())

    # ── get_device_by_id ────────────────────────────────────

    def get_device_by_id(self, device_id: int) -> Device | None:
        """Return a single device by its integer ID."""
        stmt = (
            select(Device)
            .where(Device.id == device_id)
            .options(joinedload(Device.credential))
        )
        return self.db.execute(stmt).unique().scalar_one_or_none()

    # ── create_device ───────────────────────────────────────

    def create_device(self, device_data: dict) -> Device:
        """Create and persist a new Device record."""
        device = Device(**device_data)
        self.db.add(device)
        self.db.commit()
        self.db.refresh(device)
        return device

    # ── update_device ───────────────────────────────────────

    def update_device(self, device_id: int, device_data: dict) -> Device | None:
        """Update an existing device's fields."""
        device = self.get_device_by_id(device_id)
        if device:
            for key, value in device_data.items():
                if hasattr(device, key) and key not in ("id", "created_at"):
                    setattr(device, key, value)
            device.updated_at = datetime.now(timezone.utc)
            self.db.commit()
            self.db.refresh(device)
        return device

    # ── delete_device ───────────────────────────────────────

    def delete_device(self, device_id: int) -> bool:
        """Delete a device. Returns False if active alerts exist."""
        active_count = self.get_device_active_alert_count(device_id)
        if active_count > 0:
            return False

        device = self.get_device_by_id(device_id)
        if device:
            self.db.delete(device)
            self.db.commit()
            return True
        return False

    # ── get_device_active_alert_count ───────────────────────

    def get_device_active_alert_count(self, device_id: int) -> int:
        """Count alerts in PROCESSING status for a device."""
        device = self.get_device_by_id(device_id)
        if not device:
            return 0
        stmt = (
            select(func.count(Alert.id))
            .where(Alert.status == "PROCESSING")
            .where(Alert.device_info["device_name"].as_string() == device.device_name)
        )
        return self.db.execute(stmt).scalar() or 0

    # ── upsert_credentials ──────────────────────────────────

    def upsert_credentials(self, device_id: int, cred_data: dict) -> DeviceCredential:
        """Create or update SSH credentials for a device (one-to-one)."""
        # Find existing
        stmt = select(DeviceCredential).where(DeviceCredential.device_id == device_id)
        existing = self.db.execute(stmt).scalar_one_or_none()

        if existing:
            for key, value in cred_data.items():
                if hasattr(existing, key):
                    setattr(existing, key, value)
            existing.updated_at = datetime.now(timezone.utc)
            self.db.commit()
            self.db.refresh(existing)
            return existing
        else:
            cred = DeviceCredential(device_id=device_id, **cred_data)
            self.db.add(cred)
            self.db.commit()
            self.db.refresh(cred)
            return cred

    # ── get_device_diagnostics ──────────────────────────────

    def get_device_diagnostics(self, device_id: int) -> list[dict]:
        """Return diagnostics records for a device (via related alerts)."""
        device = self.get_device_by_id(device_id)
        if not device:
            return []

        stmt = (
            select(Alert)
            .where(Alert.device_info["device_name"].as_string() == device.device_name)
            .order_by(Alert.created_at.desc())
            .limit(10)
        )
        alerts = self.db.execute(stmt).scalars().all()

        results = []
        for alert in alerts:
            results.append({
                "alert_id": alert.alert_id,
                "alert_type": alert.alert_type,
                "executed_at": alert.created_at.isoformat() if alert.created_at else None,
                "status": alert.status,
                "content": alert.content[:300],
            })
        return results
