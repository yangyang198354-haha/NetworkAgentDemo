"""
MOD-WEB-004: AlertRepository — Alert and AlertTimeline CRUD operations.
MOD-TL-003: AlertRepository enhanced with update_timeline_entry and ensure_timeline_columns.
@author sub_agent_software_developer
@module MOD-WEB-004, MOD-TL-003
@implements IFC-TL-003-01, IFC-TL-003-02, IFC-TL-003-03, IFC-TL-003-04,
           AlertRepository (list_alerts, get_alert_by_id, get_alert_timeline,
           create_alert, update_alert_status, append_timeline_entry, update_timeline_entry)
@depends MOD-WEB-003, MOD-TL-001

Provides paginated, filtered alert queries and timeline management.
@covers REQ-WEBUI-FUNC-001, REQ-WEBUI-FUNC-002, REQ-FUNC-006
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, func, desc, text, inspect
from sqlalchemy.orm import Session

from src.database.alert_models import Alert, AlertTimeline


class AlertRepository:
    """Repository for Alert and AlertTimeline entities."""

    def __init__(self, db: Session):
        self.db = db

    # ── list_alerts: paginated + filtered ───────────────────

    def list_alerts(
        self,
        alert_type: str | None = None,
        severity: str | None = None,
        status: str | None = None,
        source: str | None = None,
        time_from: datetime | None = None,
        time_to: datetime | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        """Return paginated, filtered alerts."""
        query = select(Alert)

        if alert_type:
            query = query.where(Alert.alert_type == alert_type)
        if severity:
            query = query.where(Alert.severity == severity)
        if status:
            query = query.where(Alert.status == status)
        if source:
            query = query.where(Alert.source == source)
        if time_from:
            query = query.where(Alert.created_at >= time_from)
        if time_to:
            query = query.where(Alert.created_at <= time_to)

        # Count total
        count_query = select(func.count()).select_from(query.subquery())
        total = self.db.execute(count_query).scalar() or 0

        # Apply ordering and pagination
        query = query.order_by(desc(Alert.created_at))
        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size)

        rows = self.db.execute(query).scalars().all()

        return {
            "items": list(rows),
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    # ── get_alert_by_id ─────────────────────────────────────

    def get_alert_by_id(self, alert_id: str) -> Alert | None:
        """Return a single Alert by its UUID alert_id."""
        stmt = select(Alert).where(Alert.alert_id == alert_id)
        return self.db.execute(stmt).scalar_one_or_none()

    # ── get_alert_timeline ──────────────────────────────────

    def get_alert_timeline(self, alert_id: str) -> list[AlertTimeline]:
        """Return all timeline entries for an alert, ordered by start time."""
        stmt = (
            select(AlertTimeline)
            .where(AlertTimeline.alert_id_fk == alert_id)
            .order_by(AlertTimeline.started_at)
        )
        return list(self.db.execute(stmt).scalars().all())

    # ── create_alert ────────────────────────────────────────

    def create_alert(self, alert_data: dict) -> Alert:
        """
        Create and persist a new Alert record.
        alert_data must contain: alert_id, alert_type, severity, content, device_info, source
        """
        alert = Alert(**alert_data)
        self.db.add(alert)
        self.db.commit()
        self.db.refresh(alert)
        return alert

    # ── update_alert_status ─────────────────────────────────

    def update_alert_status(self, alert_id: str, status_val: str) -> Alert | None:
        """Update an alert's status (e.g. PROCESSING → CLOSED)."""
        alert = self.get_alert_by_id(alert_id)
        if alert:
            alert.status = status_val
            alert.updated_at = datetime.now(timezone.utc)
            self.db.commit()
            self.db.refresh(alert)
        return alert

    # ── list_by_inspection_record ───────────────────────────

    def list_by_inspection_record(
        self,
        record_id: int,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        """
        Query alerts linked to a specific InspectionRecord via
        device_info JSON field's inspection_record_id key.
        Uses SQLite json_extract() for JSON field querying (ADR-004).
        """
        from sqlalchemy import text

        offset = (page - 1) * page_size

        count_sql = text(
            "SELECT COUNT(*) FROM alerts "
            "WHERE json_extract(device_info, '$.inspection_record_id') = :rid"
        )
        total = self.db.execute(count_sql, {"rid": record_id}).scalar() or 0

        data_sql = text(
            "SELECT * FROM alerts "
            "WHERE json_extract(device_info, '$.inspection_record_id') = :rid "
            "ORDER BY created_at DESC "
            "LIMIT :limit OFFSET :offset"
        )
        rows = self.db.execute(
            data_sql,
            {"rid": record_id, "limit": page_size, "offset": offset},
        ).fetchall()

        items = [dict(row._mapping) for row in rows]

        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": max(1, (total + page_size - 1) // page_size),
        }

    # ── append_timeline_entry ───────────────────────────────

    def append_timeline_entry(self, alert_id: str, entry_data: dict) -> AlertTimeline:
        """
        Append a timeline entry for a given alert.
        entry_data must contain: node_name, state_snapshot, started_at, status
        """
        entry = AlertTimeline(alert_id_fk=alert_id, **entry_data)
        self.db.add(entry)
        self.db.commit()
        self.db.refresh(entry)
        return entry

    # ── IFC-TL-003-01: update_timeline_entry ────────────────────

    def update_timeline_entry(self, entry_id: int, updates: dict) -> AlertTimeline | None:
        """
        Update an existing AlertTimeline record by its primary key id.

        Args:
            entry_id: int — the AlertTimeline.id to update.
            updates: dict — fields to update, may include:
                completed_at (datetime), duration_ms (int),
                status (str), state_snapshot (dict)

        Returns:
            Updated AlertTimeline ORM object, or None if entry_id not found.
        """
        stmt = select(AlertTimeline).where(AlertTimeline.id == entry_id)
        entry = self.db.execute(stmt).scalar_one_or_none()
        if entry is None:
            return None
        for key, value in updates.items():
            setattr(entry, key, value)
        self.db.commit()
        self.db.refresh(entry)
        return entry

    # ── IFC-DP-004-01: update_workflow_state ──────────────────

    def update_workflow_state(self, alert_id: str, partial_update: dict) -> Alert | None:
        """
        Incrementally update the workflow_state JSON column via deep merge.

        Reads the current workflow_state, deep-merges partial_update into it,
        and writes back. If current value is NULL, partial_update becomes the
        initial value.

        Merge strategy:
          - Nested dicts: recursive deep merge
          - Lists: direct replacement (not append)
          - Scalars (str/int/bool/float): direct replacement

        Args:
            alert_id: str — the alert UUID to update.
            partial_update: dict — key-value pairs to merge.

        Returns:
            Updated Alert ORM object, or None if alert_id not found.
        """
        # Force fresh read from DB (bypass ORM identity map cache)
        self.db.expire_all()
        alert = self.get_alert_by_id(alert_id)
        if alert is None:
            return None
        current = alert.workflow_state or {}
        merged = self._deep_merge(current, partial_update)
        alert.workflow_state = merged
        alert.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        return alert

    # ── IFC-DP-004-02: get_workflow_state ─────────────────────

    def get_workflow_state(self, alert_id: str) -> dict | None:
        """
        Return the workflow_state JSON column value for a given alert.

        Args:
            alert_id: str — the alert UUID.

        Returns:
            dict — the full workflow_state JSON object;
            None — if alert does not exist or column value is NULL.
        """
        alert = self.get_alert_by_id(alert_id)
        if alert is None:
            return None
        return alert.workflow_state

    # ── _deep_merge (static helper) ───────────────────────────

    @staticmethod
    def _deep_merge(base: dict, update: dict) -> dict:
        """
        Deep merge ``update`` into ``base``.

        - If both values are dicts at the same key, recursively merge.
        - Otherwise, the update value replaces the base value (lists are replaced,
          not appended).

        Returns a new dict; does not mutate the input ``base``.
        """
        result = dict(base)
        for key, value in update.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = AlertRepository._deep_merge(result[key], value)
            else:
                result[key] = value
        return result


# ── IFC-TL-003-04: ensure_timeline_columns (module-level migration) ──


def ensure_timeline_columns() -> None:
    """
    Idempotent migration: detect and add missing sequence_number / duration_ms
    columns to the alert_timeline table. Safe to call multiple times.

    Must be called AFTER init_db() / create_all(), or on an already-existing DB.
    Uses its own SessionLocal instance (creates and closes internally).
    """
    from loguru import logger
    from src.database.base import SessionLocal

    if SessionLocal is None:
        logger.warning("ensure_timeline_columns: SessionLocal not initialized, skipping migration")
        return

    db = SessionLocal()
    try:
        # Use PRAGMA table_info to inspect existing columns
        existing_columns: set[str] = set()
        result = db.execute(text("PRAGMA table_info('alert_timeline')"))
        for row in result.fetchall():
            # row is a Row with columns: cid, name, type, notnull, dflt_value, pk
            col_name = row[1] if isinstance(row, (tuple, list)) else row.name
            existing_columns.add(col_name)

        migrations_applied = False

        if 'sequence_number' not in existing_columns:
            db.execute(text("ALTER TABLE alert_timeline ADD COLUMN sequence_number INTEGER"))
            logger.info("Migration: added column sequence_number to alert_timeline")
            migrations_applied = True

        if 'duration_ms' not in existing_columns:
            db.execute(text("ALTER TABLE alert_timeline ADD COLUMN duration_ms INTEGER"))
            logger.info("Migration: added column duration_ms to alert_timeline")
            migrations_applied = True

        if migrations_applied:
            db.commit()
            logger.info("ensure_timeline_columns: migration committed successfully")
        else:
            logger.debug("ensure_timeline_columns: all columns present, no migration needed")

    except Exception as e:
        logger.warning(f"ensure_timeline_columns: migration skipped or failed: {e}")
        db.rollback()
    finally:
        db.close()
