"""
MOD-WEB-001: Devices Router — CRUD /api/devices* (7 endpoints).
@author sub_agent_software_developer
@module MOD-WEB-001
@covers REQ-WEBUI-FUNC-010, REQ-WEBUI-FUNC-011, REQ-WEBUI-FUNC-012
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, IPvAnyAddress
from sqlalchemy.orm import Session
from typing import Optional

from src.api.dependencies import get_db
from src.database.repositories.device_repository import DeviceRepository

devices_router = APIRouter()


class DeviceCreate(BaseModel):
    device_name: str
    device_ip: str
    device_model: Optional[str] = None
    group_name: Optional[str] = None


class DeviceUpdate(BaseModel):
    device_name: Optional[str] = None
    device_ip: Optional[str] = None
    device_model: Optional[str] = None
    group_name: Optional[str] = None
    status: Optional[str] = None


class CredentialUpsert(BaseModel):
    ssh_username: str
    ssh_password: str
    ssh_port: int = 22


# ── GET /api/devices ───────────────────────────────────────

@devices_router.get("")
async def list_devices(db: Session = Depends(get_db)):
    """Return all managed devices with credentials (password masked)."""
    repo = DeviceRepository(db)
    devices = repo.list_devices()

    result = []
    for d in devices:
        item = {
            "id": d.id,
            "device_name": d.device_name,
            "device_ip": d.device_ip,
            "device_model": d.device_model,
            "group_name": d.group_name,
            "status": d.status or "UNKNOWN",
            "last_diag_at": d.last_diag_at.isoformat() if d.last_diag_at else None,
            "created_at": d.created_at.isoformat() if d.created_at else None,
            "updated_at": d.updated_at.isoformat() if d.updated_at else None,
            "credential": None,
        }
        if d.credential:
            item["credential"] = {
                "ssh_username": d.credential.ssh_username,
                "ssh_password_encrypted": "****",
                "ssh_port": d.credential.ssh_port,
            }
        result.append(item)

    return {"devices": result, "count": len(result)}


# ── POST /api/devices ──────────────────────────────────────

@devices_router.post("")
async def create_device(body: DeviceCreate, db: Session = Depends(get_db)):
    """Add a new managed device."""
    repo = DeviceRepository(db)
    device = repo.create_device({
        "device_name": body.device_name,
        "device_ip": body.device_ip,
        "device_model": body.device_model,
        "group_name": body.group_name,
    })
    return {"message": "设备已添加", "device_id": device.id, "device_name": device.device_name}


# ── GET /api/devices/{device_id} ───────────────────────────

@devices_router.get("/{device_id}")
async def get_device(device_id: int, db: Session = Depends(get_db)):
    """Return device detail."""
    repo = DeviceRepository(db)
    device = repo.get_device_by_id(device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="设备不存在")
    return device


# ── PUT /api/devices/{device_id} ───────────────────────────

@devices_router.put("/{device_id}")
async def update_device(device_id: int, body: DeviceUpdate, db: Session = Depends(get_db)):
    """Update device information."""
    repo = DeviceRepository(db)
    data = body.model_dump(exclude_unset=True, exclude_none=True)
    device = repo.update_device(device_id, data)
    if device is None:
        raise HTTPException(status_code=404, detail="设备不存在")
    return {"message": "设备已更新", "device_id": device.id}


# ── DELETE /api/devices/{device_id} ────────────────────────

@devices_router.delete("/{device_id}")
async def delete_device(device_id: int, db: Session = Depends(get_db)):
    """Delete a device (blocked if active alerts exist)."""
    repo = DeviceRepository(db)
    if not repo.delete_device(device_id):
        # Check if device exists at all
        device = repo.get_device_by_id(device_id)
        if device is None:
            raise HTTPException(status_code=404, detail="设备不存在")
        count = repo.get_device_active_alert_count(device_id)
        raise HTTPException(
            status_code=409,
            detail=f"该设备有 {count} 条处理中的告警，无法删除",
        )
    return {"message": "设备已删除"}


# ── PUT /api/devices/{device_id}/credentials ───────────────

@devices_router.put("/{device_id}/credentials")
async def upsert_credentials(device_id: int, body: CredentialUpsert, db: Session = Depends(get_db)):
    """Configure SSH credentials for a device (password encrypted at storage)."""
    import sys
    main_module = sys.modules.get("src.main")
    if main_module is None or main_module.encryption_service is None:
        raise HTTPException(status_code=503, detail="Encryption service not initialized")

    encrypted_password = main_module.encryption_service.encrypt(body.ssh_password)

    repo = DeviceRepository(db)
    cred_data = {
        "ssh_username": body.ssh_username,
        "ssh_password_encrypted": encrypted_password,
        "ssh_port": body.ssh_port,
    }
    cred = repo.upsert_credentials(device_id, cred_data)
    return {
        "message": "凭据已配置",
        "ssh_username": cred.ssh_username,
        "ssh_password_encrypted": "****",
        "ssh_port": cred.ssh_port,
    }


# ── GET /api/devices/{device_id}/diagnostics ───────────────

@devices_router.get("/{device_id}/diagnostics")
async def get_device_diagnostics(device_id: int, db: Session = Depends(get_db)):
    """Return recent diagnostic results for a device."""
    repo = DeviceRepository(db)
    results = repo.get_device_diagnostics(device_id)
    return {"device_id": device_id, "diagnostics": results}
