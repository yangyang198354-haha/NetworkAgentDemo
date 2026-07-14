"""
MOD-WEB-004: InspectionRepository — Inspection configuration and history.
@author sub_agent_software_developer
@module MOD-WEB-004
@implements InspectionRepository (get_config, update_config, create_record,
           update_record, list_history, get_devices_for_inspection,
           get_latest_inspection)
@depends MOD-WEB-003
@covers REQ-WEBUI-FUNC-013, REQ-WEBUI-FUNC-014, REQ-WEBUI-FUNC-015
@v0.2.0 增强:
  - REQ-INSP-001: get_config() 新增 retry_backoff, 移除 polling_interval
  - REQ-INSP-011: list_history() 新增 status 筛选
  - MOD-INSP-003: 新增 get_devices_for_inspection(), get_latest_inspection()
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, func, desc
from sqlalchemy.orm import Session

from src.database.inspection_models import InspectionRecord
from src.database.config_models import SystemConfig


class InspectionRepository:
    """Repository for InspectionRecord and inspection-related SystemConfig.

    v0.2.0 enhancements:
      - get_config() → added diagnosis.retry_backoff, removed ui.polling_interval_seconds
      - Added get_devices_for_inspection(), get_latest_inspection()
      - list_history() → added status filter
    """

    def __init__(self, db: Session):
        self.db = db

    # ── get_config ──────────────────────────────────────────
    # IFC-WEB-004-01 (增强): 配置键列表增加 retry_backoff, 移除 polling_interval

    def get_config(self) -> dict:
        """Return inspection-related configuration as a dict.

        v0.2.0: Added diagnosis.retry_backoff; removed ui.polling_interval_seconds.
        """
        keys = [
            "inspection.interval_minutes",
            "diagnosis.timeout_seconds",
            "diagnosis.retry_max",
            "diagnosis.retry_backoff",
        ]
        result: dict[str, str] = {}
        for key in keys:
            stmt = select(SystemConfig).where(SystemConfig.config_key == key)
            row = self.db.execute(stmt).scalar_one_or_none()
            result[key] = row.config_value if row else ""
        return result

    # ── update_config ───────────────────────────────────────
    # IFC-WEB-004-02 (增强): 接收的 config_values 可包含 diagnosis.retry_backoff

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

    # ── get_by_id ───────────────────────────────────────────

    def get_by_id(self, record_id: int) -> InspectionRecord | None:
        """Return an InspectionRecord by its primary key id.

        Args:
            record_id: The integer primary key of the InspectionRecord.

        Returns:
            The InspectionRecord ORM object if found, or None if no such record.
        """
        stmt = select(InspectionRecord).where(InspectionRecord.id == record_id)
        return self.db.execute(stmt).scalar_one_or_none()

    # ── get_devices_for_inspection ───────────────────────────
    # IFC-WEB-004-05 (新增): 获取纳管设备列表供 CLI 巡检使用

    def get_devices_for_inspection(self) -> list[dict]:
        """Return list of managed devices for inspection execution.

        MOD-INSP-003 (inspection_cli) uses this to load device list.
        Returns: list of dicts with device_name, device_ip, device_model.
        """
        try:
            from src.database.device_models import Device as DbDevice
            stmt = select(DbDevice)
            devices = self.db.execute(stmt).scalars().all()
            return [
                {
                    "device_name": d.device_name,
                    "device_ip": d.device_ip,
                    "device_model": d.device_model or "",
                }
                for d in devices
            ]
        except Exception:
            # Device table may not exist in early development
            return []

    # ── get_latest_inspection ────────────────────────────────
    # IFC-WEB-004-06 (新增): 获取最近一次巡检记录摘要

    def get_latest_inspection(self) -> dict | None:
        """Return latest inspection record summary.

        Used by GET /api/inspection/status for the last_inspection field.
        Returns: dict with id, trigger_mode, total_devices, anomaly_count,
                 status, started_at, completed_at, or None if no records.
        """
        stmt = (
            select(InspectionRecord)
            .order_by(desc(InspectionRecord.completed_at))
            .limit(1)
        )
        record = self.db.execute(stmt).scalar_one_or_none()
        if record is None:
            return None

        return {
            "record_id": record.id,
            "trigger_mode": record.trigger_mode,
            "total_devices": record.total_devices,
            "anomaly_count": record.anomaly_count,
            "status": getattr(record, "status", "SUCCESS"),
            "started_at": record.started_at.isoformat() if record.started_at else None,
            "completed_at": record.completed_at.isoformat() if record.completed_at else None,
        }

    # ── list_history ────────────────────────────────────────
    # IFC-WEB-004-07 (增强): 新增 status 筛选参数

    def list_history(
        self,
        trigger_mode: str | None = None,
        status: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        """Return paginated inspection history.

        v0.2.0: Added status filter (SUCCESS/PARTIAL/FAILED).
        """
        query = select(InspectionRecord)

        if trigger_mode:
            query = query.where(InspectionRecord.trigger_mode == trigger_mode)
        if status:
            query = query.where(InspectionRecord.status == status)

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
