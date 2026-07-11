"""
MOD-WEB-004: InspectionRepository — Inspection configuration and history.
@author sub_agent_software_developer
@module MOD-WEB-004
@implements InspectionRepository (get_config, update_config, create_record,
           update_record, list_history)
@depends MOD-WEB-003
@covers REQ-WEBUI-FUNC-013, REQ-WEBUI-FUNC-014, REQ-WEBUI-FUNC-015
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, func, desc
from sqlalchemy.orm import Session

from src.database.inspection_models import InspectionRecord
from src.database.config_models import SystemConfig


class InspectionRepository:
    """Repository for InspectionRecord and inspection-related SystemConfig."""

    def __init__(self, db: Session):
        self.db = db

    # ── get_config ──────────────────────────────────────────

    def get_config(self) -> dict:
        """Return inspection-related configuration as a dict."""
        keys = [
            "inspection.interval_minutes",
            "diagnosis.timeout_seconds",
            "diagnosis.retry_max",
            "ui.polling_interval_seconds",
        ]
        result: dict[str, str] = {}
        for key in keys:
            stmt = select(SystemConfig).where(SystemConfig.config_key == key)
            row = self.db.execute(stmt).scalar_one_or_none()
            result[key] = row.config_value if row else ""
        return result

    # ── update_config ───────────────────────────────────────

    def update_config(self, config_values: dict) -> dict:
        """Upsert inspection configuration values."""
        for key, value in config_values.items():
            stmt = select(SystemConfig).where(SystemConfig.config_key == key)
            existing = self.db.execute(stmt).scalar_one_or_none()
            if existing:
                existing.config_value = str(value)
                existing.updated_at = datetime.now(timezone.utc)
            else:
                self.db.add(SystemConfig(config_key=key, config_value=str(value)))
        self.db.commit()
        return self.get_config()

    # ── create_record ───────────────────────────────────────

    def create_record(self, record_data: dict) -> InspectionRecord:
        """Create a new inspection execution record."""
        record = InspectionRecord(**record_data)
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return record

    # ── update_record ───────────────────────────────────────

    def update_record(self, record_id: int, updates: dict) -> InspectionRecord | None:
        """Update an existing inspection record."""
        stmt = select(InspectionRecord).where(InspectionRecord.id == record_id)
        record = self.db.execute(stmt).scalar_one_or_none()
        if record:
            for key, value in updates.items():
                if hasattr(record, key):
                    setattr(record, key, value)
            self.db.commit()
            self.db.refresh(record)
        return record

    # ── list_history ────────────────────────────────────────

    def list_history(
        self,
        trigger_mode: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        """Return paginated inspection history."""
        query = select(InspectionRecord)

        if trigger_mode:
            query = query.where(InspectionRecord.trigger_mode == trigger_mode)

        count_query = select(func.count()).select_from(query.subquery())
        total = self.db.execute(count_query).scalar() or 0

        query = query.order_by(desc(InspectionRecord.started_at))
        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size)

        rows = self.db.execute(query).scalars().all()

        return {
            "items": list(rows),
            "total": total,
            "page": page,
            "page_size": page_size,
        }
