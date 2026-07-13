"""
MOD-WEB-001: Knowledge Base Router — /api/knowledge/* (11 endpoints).
@author sub_agent_software_developer
@module MOD-WEB-001
@covers REQ-WEBUI-FUNC-016, REQ-WEBUI-FUNC-017, REQ-WEBUI-FUNC-018
"""

import sys
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional

from src.api.dependencies import get_db
from src.database.repositories.knowledge_repository import KnowledgeRepository

kb_router = APIRouter()


# ── Pydantic schemas ───────────────────────────────────────

class DocCreate(BaseModel):
    title: str
    alert_type: str
    content: str


class DocUpdate(BaseModel):
    title: Optional[str] = None
    alert_type: Optional[str] = None
    content: Optional[str] = None


class TemplateCreate(BaseModel):
    name: str
    alert_type: str
    yaml_content: str
    parameters: list[dict] = []


class TemplateUpdate(BaseModel):
    name: Optional[str] = None
    alert_type: Optional[str] = None
    yaml_content: Optional[str] = None
    parameters: Optional[list[dict]] = None


class RetrievalRequest(BaseModel):
    query: str
    alert_type: Optional[str] = None
    top_k: int = 5


# ════════════════════════════════════════════════════════════
# Document endpoints (5)
# ════════════════════════════════════════════════════════════

@kb_router.get("/documents")
async def list_documents(
    alert_type: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """List knowledge documents with optional alert_type filter."""
    repo = KnowledgeRepository(db)
    return repo.list_documents(alert_type=alert_type, page=page, page_size=page_size)


@kb_router.post("/documents")
async def create_document(body: DocCreate, db: Session = Depends(get_db)):
    """Create a new knowledge document."""
    repo = KnowledgeRepository(db)
    doc = repo.create_document(body.model_dump())
    return {"message": "文档已创建", "document_id": doc.id, "title": doc.title}


@kb_router.get("/documents/{doc_id}")
async def get_document(doc_id: int, db: Session = Depends(get_db)):
    """Get a single knowledge document."""
    repo = KnowledgeRepository(db)
    doc = repo.get_document(doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    return doc


@kb_router.put("/documents/{doc_id}")
async def update_document(doc_id: int, body: DocUpdate, db: Session = Depends(get_db)):
    """Update a knowledge document."""
    repo = KnowledgeRepository(db)
    data = body.model_dump(exclude_unset=True, exclude_none=True)
    doc = repo.update_document(doc_id, data)
    if doc is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    return {"message": "文档已更新", "document_id": doc.id}


@kb_router.delete("/documents/{doc_id}")
async def delete_document(doc_id: int, db: Session = Depends(get_db)):
    """Delete a knowledge document."""
    repo = KnowledgeRepository(db)
    if not repo.delete_document(doc_id):
        raise HTTPException(status_code=404, detail="文档不存在")
    return {"message": "文档已删除"}


# ════════════════════════════════════════════════════════════
# Template endpoints (5)
# ════════════════════════════════════════════════════════════

@kb_router.get("/templates")
async def list_templates(
    alert_type: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """List command templates."""
    repo = KnowledgeRepository(db)
    templates = repo.list_templates(alert_type=alert_type)
    return {"templates": templates, "count": len(templates)}


@kb_router.post("/templates")
async def create_template(body: TemplateCreate, db: Session = Depends(get_db)):
    """Create a new command template."""
    repo = KnowledgeRepository(db)
    tmpl = repo.create_template(body.model_dump())
    return {"message": "模板已创建", "template_id": tmpl.id, "name": tmpl.name}


@kb_router.get("/templates/{template_id}")
async def get_template(template_id: int, db: Session = Depends(get_db)):
    """Get a single command template."""
    repo = KnowledgeRepository(db)
    tmpl = repo.get_template(template_id)
    if tmpl is None:
        raise HTTPException(status_code=404, detail="模板不存在")
    return tmpl


@kb_router.put("/templates/{template_id}")
async def update_template(template_id: int, body: TemplateUpdate, db: Session = Depends(get_db)):
    """Update a command template."""
    repo = KnowledgeRepository(db)
    data = body.model_dump(exclude_unset=True, exclude_none=True)
    tmpl = repo.update_template(template_id, data)
    if tmpl is None:
        raise HTTPException(status_code=404, detail="模板不存在")
    return {"message": "模板已更新", "template_id": tmpl.id}


@kb_router.delete("/templates/{template_id}")
async def delete_template(template_id: int, db: Session = Depends(get_db)):
    """Delete a command template."""
    repo = KnowledgeRepository(db)
    if not repo.delete_template(template_id):
        raise HTTPException(status_code=404, detail="模板不存在")
    return {"message": "模板已删除"}


# ════════════════════════════════════════════════════════════
# Retrieval test (1)
# ════════════════════════════════════════════════════════════

@kb_router.post("/test-retrieval")
async def test_retrieval(body: RetrievalRequest, db: Session = Depends(get_db)):
    """
    Test RAG retrieval with a query string.
    Returns matched documents with similarity scores.
    """
    main_module = sys.modules.get("src.main")
    if main_module is None:
        raise HTTPException(status_code=503, detail="System not initialized")

    rag_service = main_module.rag_service
    try:
        results = rag_service.search(body.query, body.alert_type or "", top_k=body.top_k)
        return {
            "results": [r.model_dump() for r in results],
            "total_indexed": len(rag_service._fallback_docs),
            "query_time_ms": 0,
        }
    except Exception as e:
        return {
            "results": [],
            "total_indexed": len(rag_service._fallback_docs) if hasattr(rag_service, "_fallback_docs") else 0,
            "query_time_ms": 0,
            "error": str(e),
        }
