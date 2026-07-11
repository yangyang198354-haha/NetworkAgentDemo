"""
MOD-WEB-004: KnowledgeRepository — Knowledge documents and command templates CRUD.
@author sub_agent_software_developer
@module MOD-WEB-004
@implements KnowledgeRepository (document & template CRUD operations)
@depends MOD-WEB-003
@covers REQ-WEBUI-FUNC-016, REQ-WEBUI-FUNC-017
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, func, desc
from sqlalchemy.orm import Session

from src.database.kb_models import KnowledgeDocument, CommandTemplate


class KnowledgeRepository:
    """Repository for KnowledgeDocument and CommandTemplate entities."""

    def __init__(self, db: Session):
        self.db = db

    # ── Document CRUD ───────────────────────────────────────

    def list_documents(
        self,
        alert_type: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        """Paginated document list, optional filter by alert_type."""
        query = select(KnowledgeDocument)
        if alert_type:
            query = query.where(KnowledgeDocument.alert_type == alert_type)

        count_query = select(func.count()).select_from(query.subquery())
        total = self.db.execute(count_query).scalar() or 0

        query = query.order_by(desc(KnowledgeDocument.updated_at))
        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size)

        rows = self.db.execute(query).scalars().all()

        return {
            "items": list(rows),
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def get_document(self, doc_id: int) -> KnowledgeDocument | None:
        """Return a single knowledge document by ID."""
        stmt = select(KnowledgeDocument).where(KnowledgeDocument.id == doc_id)
        return self.db.execute(stmt).scalar_one_or_none()

    def create_document(self, doc_data: dict) -> KnowledgeDocument:
        """Create a new knowledge document."""
        doc = KnowledgeDocument(**doc_data)
        self.db.add(doc)
        self.db.commit()
        self.db.refresh(doc)
        return doc

    def update_document(self, doc_id: int, doc_data: dict) -> KnowledgeDocument | None:
        """Update an existing knowledge document."""
        doc = self.get_document(doc_id)
        if doc:
            for key, value in doc_data.items():
                if hasattr(doc, key) and key not in ("id", "created_at"):
                    setattr(doc, key, value)
            doc.updated_at = datetime.now(timezone.utc)
            self.db.commit()
            self.db.refresh(doc)
        return doc

    def delete_document(self, doc_id: int) -> bool:
        """Delete a knowledge document by ID."""
        doc = self.get_document(doc_id)
        if doc:
            self.db.delete(doc)
            self.db.commit()
            return True
        return False

    # ── Template CRUD ───────────────────────────────────────

    def list_templates(self, alert_type: str | None = None) -> list[CommandTemplate]:
        """Return all command templates, optionally filtered by alert_type."""
        query = select(CommandTemplate)
        if alert_type:
            query = query.where(CommandTemplate.alert_type == alert_type)
        query = query.order_by(desc(CommandTemplate.updated_at))
        return list(self.db.execute(query).scalars().all())

    def get_template(self, template_id: int) -> CommandTemplate | None:
        """Return a single command template by ID."""
        stmt = select(CommandTemplate).where(CommandTemplate.id == template_id)
        return self.db.execute(stmt).scalar_one_or_none()

    def create_template(self, template_data: dict) -> CommandTemplate:
        """Create a new command template."""
        tmpl = CommandTemplate(**template_data)
        self.db.add(tmpl)
        self.db.commit()
        self.db.refresh(tmpl)
        return tmpl

    def update_template(self, template_id: int, data: dict) -> CommandTemplate | None:
        """Update an existing command template."""
        tmpl = self.get_template(template_id)
        if tmpl:
            for key, value in data.items():
                if hasattr(tmpl, key) and key not in ("id", "created_at"):
                    setattr(tmpl, key, value)
            tmpl.updated_at = datetime.now(timezone.utc)
            self.db.commit()
            self.db.refresh(tmpl)
        return tmpl

    def delete_template(self, template_id: int) -> bool:
        """Delete a command template by ID."""
        tmpl = self.get_template(template_id)
        if tmpl:
            self.db.delete(tmpl)
            self.db.commit()
            return True
        return False
