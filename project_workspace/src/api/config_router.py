"""
MOD-WEB-001: Config Router — /api/system/* (5 endpoints).
@author sub_agent_software_developer
@module MOD-WEB-001
@covers REQ-WEBUI-FUNC-019, REQ-WEBUI-FUNC-020, REQ-WEBUI-FUNC-021
"""

import sys
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.api.dependencies import get_db
from src.database.repositories.config_repository import ConfigRepository
from src.database.repositories.audit_log_repository import AuditLogRepository

config_router = APIRouter()


class ConfigUpdate(BaseModel):
    inspection_interval_minutes: Optional[int] = None
    diagnosis_timeout_seconds: Optional[int] = None
    diagnosis_retry_max: Optional[int] = None
    rag_similarity_threshold: Optional[float] = None
    polling_interval_seconds: Optional[int] = None


class ApiKeyUpdate(BaseModel):
    api_key: str


# ── GET /api/system/config ─────────────────────────────────

@config_router.get("/config")
async def get_system_config(db: Session = Depends(get_db)):
    """Return all system configuration entries."""
    repo = ConfigRepository(db)
    configs = repo.get_all_configs()

    result = []
    for cfg in configs:
        # Mask LLM API key
        if cfg.config_key == "llm.api_key_encrypted" and cfg.config_value:
            result.append({
                "config_key": cfg.config_key,
                "config_value": "****",
                "updated_at": cfg.updated_at.isoformat() if cfg.updated_at else None,
                "masked": True,
            })
        else:
            result.append({
                "config_key": cfg.config_key,
                "config_value": cfg.config_value,
                "updated_at": cfg.updated_at.isoformat() if cfg.updated_at else None,
                "masked": False,
            })

    return {"configs": result}


# ── PUT /api/system/config ─────────────────────────────────

@config_router.put("/config")
async def update_system_config(body: ConfigUpdate, db: Session = Depends(get_db)):
    """Update system configuration entries (bulk)."""
    repo = ConfigRepository(db)

    mapping = {
        "inspection.interval_minutes": body.inspection_interval_minutes,
        "diagnosis.timeout_seconds": body.diagnosis_timeout_seconds,
        "diagnosis.retry_max": body.diagnosis_retry_max,
        "rag.similarity_threshold": body.rag_similarity_threshold,
        "ui.polling_interval_seconds": body.polling_interval_seconds,
    }

    updates = {k: str(v) for k, v in mapping.items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="没有提供有效的配置项")

    repo.upsert_configs(updates)
    return {"message": "系统配置已更新", "updated_keys": list(updates.keys())}


# ── PUT /api/system/config/llm-api-key ─────────────────────

@config_router.put("/config/llm-api-key")
async def update_llm_api_key(body: ApiKeyUpdate, db: Session = Depends(get_db)):
    """Store LLM API Key (encrypted)."""
    main_module = sys.modules.get("src.main")
    if main_module is None or main_module.encryption_service is None:
        raise HTTPException(status_code=503, detail="Encryption service not initialized")

    encrypted = main_module.encryption_service.encrypt(body.api_key)

    repo = ConfigRepository(db)
    repo.set_llm_api_key_encrypted(encrypted)

    return {"message": "API Key已安全存储", "masked": "****"}


# ── POST /api/system/config/llm-test ───────────────────────

@config_router.post("/config/llm-test")
async def test_llm_connection(db: Session = Depends(get_db)):
    """Test the LLM (DeepSeek) API connection."""
    main_module = sys.modules.get("src.main")
    if main_module is None:
        raise HTTPException(status_code=503, detail="System not initialized")

    try:
        llm = main_module.llm_service
        # Attempt a lightweight call
        test_result = llm.test_connection() if hasattr(llm, "test_connection") else True
        return {
            "status": "healthy" if test_result else "error",
            "detail": "DeepSeek API reachable" if test_result else "Connection failed",
        }
    except Exception as e:
        return {"status": "error", "detail": str(e)}


# ── GET /api/system/logs ───────────────────────────────────

@config_router.get("/logs")
async def get_system_logs(
    level: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None),
    time_from: Optional[str] = Query(None),
    time_to: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """Search and return log entries (file-based reading)."""
    from src.services.log_reader_service import LogReaderService

    reader = LogReaderService()

    tf = datetime.fromisoformat(time_from) if time_from else None
    tt = datetime.fromisoformat(time_to) if time_to else None

    result = reader.read_logs(
        source="operations",
        level=level,
        keyword=keyword,
        time_from=tf,
        time_to=tt,
        page=page,
        page_size=page_size,
    )
    return result
