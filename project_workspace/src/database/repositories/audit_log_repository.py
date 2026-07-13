"""
MOD-WEB-004: AuditLogRepository — Audit log CRUD.
@author sub_agent_software_developer
@module MOD-WEB-004
@implements AuditLogRepository (create_log, search_logs)
@depends MOD-WEB-003
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import select, func, desc
from sqlalchemy.orm import Session

from src.database.config_models import AuditLog


class AuditLogRepository:
    """Repository for AuditLog entries."""

    def __init__(self, db: Session):
        self.db = db

    # ── create_log ──────────────────────────────────────────

    def create_log(self, entry_data: dict) -> AuditLog:
        """Create and persist a new audit log entry."""
        log_entry = AuditLog(**entry_data)
        self.db.add(log_entry)
        self.db.commit()
        self.db.refresh(log_entry)
        return log_entry

    # ── search_logs ─────────────────────────────────────────

    def search_logs(
        self,
        level: str | None = None,
        module: str | None = None,
        time_from: datetime | None = None,
        time_to: datetime | None = None,
        page: int = 1,
        page_size: int = 100,
    ) -> dict:
        """Paginated audit log search with optional filters."""
        query = select(AuditLog)

        if level:
            query = query.where(AuditLog.level == level)
        if module:
            query = query.where(AuditLog.module == module)
        if time_from:
            query = query.where(AuditLog.timestamp >= time_from)
        if time_to:
            query = query.where(AuditLog.timestamp <= time_to)

        count_query = select(func.count()).select_from(query.subquery())
        total = self.db.execute(count_query).scalar() or 0

        query = query.order_by(desc(AuditLog.timestamp))
        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size)

        rows = self.db.execute(query).scalars().all()

        return {
            "items": list(rows),
            "total": total,
            "page": page,
            "page_size": page_size,
        }
