"""
MOD-WEB-004: AlertRepository — Alert and AlertTimeline CRUD operations.
@author sub_agent_software_developer
@module MOD-WEB-004
@implements AlertRepository (list_alerts, get_alert_by_id, get_alert_timeline,
           create_alert, update_alert_status, append_timeline_entry)
@depends MOD-WEB-003

Provides paginated, filtered alert queries and timeline management.
@covers REQ-WEBUI-FUNC-001, REQ-WEBUI-FUNC-002
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, func, desc
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
