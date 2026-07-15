"""
MOD-WEB-001: Devices Router — CRUD /api/devices* (14 endpoints).
@author sub_agent_software_developer
@module MOD-WEB-001
@covers REQ-WEBUI-FUNC-010, REQ-WEBUI-FUNC-011, REQ-WEBUI-FUNC-012
@extended REQ-FUNC-112 ~ REQ-FUNC-115 (device_simulator)
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional

from src.api.dependencies import get_db
from src.database.repositories.device_repository import DeviceRepository

devices_router = APIRouter()


# ────────────────────────────────────────────────────
# Schemas
# ────────────────────────────────────────────────────

class DeviceCreate(BaseModel):
    device_name: str
    device_ip: str
    device_model: Optional[str] = None
    group_name: Optional[str] = None
    device_type: Optional[str] = "MOCK"       # REQ-FUNC-112: MOCK | SIMULATOR
    simulator_port: Optional[int] = None       # 模拟器 SSH 端口 (仅 SIMULATOR)


class DeviceUpdate(BaseModel):
    device_name: Optional[str] = None
    device_ip: Optional[str] = None
    device_model: Optional[str] = None
    group_name: Optional[str] = None
    status: Optional[str] = None
    device_type: Optional[str] = None          # REQ-FUNC-112
    simulator_port: Optional[int] = None


class CredentialUpsert(BaseModel):
    ssh_username: str
    ssh_password: str
    ssh_port: int = 22


class PortConfigRequest(BaseModel):
    """REQ-FUNC-114: Port configuration request."""
    action: str  # shutdown | no-shutdown | set-vlan | set-description
    value: Optional[str] = None  # VLAN ID or description text


class SimulatorStartRequest(BaseModel):
    """REQ-FUNC-121: Start simulator request."""
    host: str = "0.0.0.0"          # 监听地址
    port: int = 0                  # 0 = 自动分配
    ssh_username: str = "admin"
    ssh_password: str = "switch123"


# ── Helper: build device response dict ────────────────────

def _device_to_dict(d) -> dict:
    """Serialize a Device ORM object to API response dict."""
    item = {
        "id": d.id,
        "device_name": d.device_name,
        "device_ip": d.device_ip,
        "device_model": d.device_model,
        "group_name": d.group_name,
        "device_type": d.device_type or "MOCK",          # REQ-FUNC-112
        "simulator_port": d.simulator_port,               # REQ-FUNC-112
        "simulator_status": d.simulator_status or "STOPPED",  # REQ-FUNC-121
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
    return item


def _get_lifecycle_manager():
    """Lazy-load the global SimulatorLifecycleManager from main module."""
    import sys
    main_module = sys.modules.get("src.main")
    if main_module is None or getattr(main_module, "simulator_lifecycle_manager", None) is None:
        raise HTTPException(status_code=503, detail="Simulator lifecycle manager not initialized")
    return main_module.simulator_lifecycle_manager


# ── GET /api/devices ───────────────────────────────────────

@devices_router.get("")
async def list_devices(db: Session = Depends(get_db)):
    """Return all managed devices with credentials (password masked)."""
    repo = DeviceRepository(db)
    devices = repo.list_devices()

    # Merge simulator status for running instances
    try:
        import sys
        main_module = sys.modules.get("src.main")
        lm = getattr(main_module, "simulator_lifecycle_manager", None)
    except Exception:
        lm = None

    result = []
    for d in devices:
        item = _device_to_dict(d)
        # Override with live simulator status if available
        if lm and d.device_type == "SIMULATOR":
            live = lm.get_status(d.id)
            if live.get("running"):
                item["simulator_status"] = "RUNNING"
                item["simulator_port"] = live.get("port") or item["simulator_port"]
        result.append(item)

    return {"devices": result, "count": len(result)}


# ── POST /api/devices ──────────────────────────────────────

@devices_router.post("")
async def create_device(body: DeviceCreate, db: Session = Depends(get_db)):
    """Add a new managed device. REQ-FUNC-104: supports device_type=SIMULATOR."""
    repo = DeviceRepository(db)
    device_data = {
        "device_name": body.device_name,
        "device_ip": body.device_ip,
        "device_model": body.device_model,
        "group_name": body.group_name,
        "device_type": body.device_type or "MOCK",
        "simulator_port": body.simulator_port,
        "simulator_status": "STOPPED",
    }
    device = repo.create_device(device_data)
    return {
        "message": "设备已添加",
        "device_id": device.id,
        "device_name": device.device_name,
        "device_type": device.device_type,
    }


# ── GET /api/devices/{device_id} ───────────────────────────

@devices_router.get("/{device_id}")
async def get_device(device_id: int, db: Session = Depends(get_db)):
    """Return device detail with simulator status if applicable."""
    repo = DeviceRepository(db)
    device = repo.get_device_by_id(device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="设备不存在")

    item = _device_to_dict(device)
    # Merge live simulator status
    if device.device_type == "SIMULATOR":
        try:
            lm = _get_lifecycle_manager()
            live = lm.get_status(device_id)
            if live.get("running"):
                item["simulator_status"] = "RUNNING"
                item["simulator_port"] = live.get("port") or item["simulator_port"]
        except HTTPException:
            pass  # lifecycle manager not ready yet

    return item


# ── PUT /api/devices/{device_id} ───────────────────────────

@devices_router.put("/{device_id}")
async def update_device(device_id: int, body: DeviceUpdate, db: Session = Depends(get_db)):
    """Update device information. REQ-FUNC-112: supports device_type field."""
    repo = DeviceRepository(db)
    data = body.model_dump(exclude_unset=True, exclude_none=True)
    device = repo.update_device(device_id, data)
    if device is None:
        raise HTTPException(status_code=404, detail="设备不存在")
    return {"message": "设备已更新", "device_id": device.id}


# ── DELETE /api/devices/{device_id} ────────────────────────

@devices_router.delete("/{device_id}")
async def delete_device(device_id: int, db: Session = Depends(get_db)):
    """Delete a device. Stops simulator if running (REQ-FUNC-121)."""
    repo = DeviceRepository(db)
    device = repo.get_device_by_id(device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="设备不存在")

    # Stop simulator if running
    if device.device_type == "SIMULATOR":
        try:
            lm = _get_lifecycle_manager()
            lm.stop_simulator(device_id)
        except HTTPException:
            pass

    if not repo.delete_device(device_id):
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


# ═══════════════════════════════════════════════════════════
# 模拟器专用端点 (REQ-FUNC-113 ~ REQ-FUNC-115, REQ-FUNC-121)
# ═══════════════════════════════════════════════════════════

# ── POST /api/devices/{device_id}/simulator/start ──────────

@devices_router.post("/{device_id}/simulator/start")
def simulator_start(device_id: int, body: SimulatorStartRequest, db: Session = Depends(get_db)):
    """
    REQ-FUNC-121: 启动模拟器 SSH 服务。
    用户确认: 手动触发策略 — 创建设备后点击"启动模拟器"按钮。
    """
    repo = DeviceRepository(db)
    device = repo.get_device_by_id(device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="设备不存在")
    if device.device_type != "SIMULATOR":
        raise HTTPException(status_code=400, detail="仅模拟器设备支持此操作")

    lm = _get_lifecycle_manager()

    # Determine SSH credentials
    username = body.ssh_username or "admin"
    password = body.ssh_password or "switch123"
    if device.credential:
        import sys
        main_module = sys.modules.get("src.main")
        if main_module and main_module.encryption_service:
            try:
                password = main_module.encryption_service.decrypt(
                    device.credential.ssh_password_encrypted
                )
            except Exception:
                password = body.ssh_password or "switch123"
        username = device.credential.ssh_username or username

    # Use configured port or allocate
    port = body.port or device.simulator_port or 0

    success, message, actual_ssh_port, actual_mgmt_port = lm.start_simulator(
        device_id=device_id,
        ssh_host=body.host,
        ssh_port=port,
        username=username,
        password=password,
        device_name=device.device_name,
    )

    if success and actual_ssh_port:
        # Persist port and status
        repo.update_device(device_id, {
            "simulator_port": actual_ssh_port,
            "simulator_status": "RUNNING",
        })

    return {
        "success": success,
        "message": message,
        "ssh_port": actual_ssh_port,
        "mgmt_port": actual_mgmt_port,
    }


# ── POST /api/devices/{device_id}/simulator/stop ───────────

@devices_router.post("/{device_id}/simulator/stop")
def simulator_stop(device_id: int, db: Session = Depends(get_db)):
    """REQ-FUNC-121: 停止模拟器 SSH 服务。"""
    repo = DeviceRepository(db)
    device = repo.get_device_by_id(device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="设备不存在")

    lm = _get_lifecycle_manager()
    success, message = lm.stop_simulator(device_id)

    if success:
        repo.update_device(device_id, {"simulator_status": "STOPPED"})

    return {"success": success, "message": message}


# ── GET /api/devices/{device_id}/simulator/status ──────────

@devices_router.get("/{device_id}/simulator/status")
def simulator_status(device_id: int, db: Session = Depends(get_db)):
    """REQ-FUNC-121: 查询模拟器运行状态。"""
    repo = DeviceRepository(db)
    device = repo.get_device_by_id(device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="设备不存在")
    if device.device_type != "SIMULATOR":
        return {"device_id": device_id, "running": False, "status": "N/A",
                "message": "非模拟器设备"}

    lm = _get_lifecycle_manager()
    return lm.get_status(device_id)


# ── POST /api/devices/{device_id}/heartbeat ────────────────

@devices_router.post("/{device_id}/heartbeat")
def device_heartbeat(device_id: int, db: Session = Depends(get_db)):
    """
    REQ-FUNC-113: 心跳检测 — TCP 端口可达性探测。
    仅适用于 SIMULATOR 设备，MOCK 设备返回 UNKNOWN。
    """
    repo = DeviceRepository(db)
    device = repo.get_device_by_id(device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="设备不存在")

    if device.device_type != "SIMULATOR":
        return {
            "device_id": device_id,
            "status": "UNKNOWN",
            "message": "心跳检测仅适用于模拟器设备",
            "response_time_ms": None,
        }

    lm = _get_lifecycle_manager()
    live_status = lm.get_status(device_id)

    if live_status.get("running") and live_status.get("ssh_port"):
        # Simulator runs on same VPS — always use 127.0.0.1
        ssh_host = "127.0.0.1"
        ssh_port = live_status["ssh_port"]
        is_online, response_ms = lm.heartbeat(ssh_host, ssh_port)

        # Update device status
        new_status = "ONLINE" if is_online else "OFFLINE"
        repo.update_device(device_id, {"status": new_status})

        return {
            "device_id": device_id,
            "status": new_status,
            "response_time_ms": response_ms,
        }
    else:
        repo.update_device(device_id, {"status": "OFFLINE"})
        return {
            "device_id": device_id,
            "status": "OFFLINE",
            "response_time_ms": None,
        }


# ── GET /api/devices/{device_id}/ports ─────────────────────

@devices_router.get("/{device_id}/ports")
def get_device_ports(device_id: int, db: Session = Depends(get_db)):
    """
    REQ-FUNC-114: 查看模拟器端口状态列表。
    仅适用于 SIMULATOR 设备。
    """
    repo = DeviceRepository(db)
    device = repo.get_device_by_id(device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="设备不存在")
    if device.device_type != "SIMULATOR":
        return {"device_id": device_id, "ports": [],
                "message": "端口查看仅适用于模拟器设备"}

    lm = _get_lifecycle_manager()
    ports_data = lm.get_ports(device_id)
    if ports_data is None:
        raise HTTPException(status_code=400, detail="模拟器未运行，请先启动模拟器")

    return {
        "device_id": device_id,
        "ports": ports_data.get("ports", []),
        "up_ports_detail": ports_data.get("up_ports_detail", []),
    }


# ── POST /api/devices/{device_id}/ports/{port_name}/config ─

@devices_router.post("/{device_id}/ports/{port_name}/config")
def configure_device_port(
    device_id: int,
    port_name: str,
    body: PortConfigRequest,
    db: Session = Depends(get_db),
):
    """
    REQ-FUNC-114: 对模拟器端口执行配置操作。
    Actions: shutdown, no-shutdown, set-vlan, set-description
    """
    repo = DeviceRepository(db)
    device = repo.get_device_by_id(device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="设备不存在")
    if device.device_type != "SIMULATOR":
        raise HTTPException(status_code=400, detail="端口配置仅适用于模拟器设备")

    lm = _get_lifecycle_manager()
    result = lm.configure_port(device_id, port_name, body.action, body.value or "")
    if result is None:
        raise HTTPException(status_code=400, detail="模拟器未运行，请先启动模拟器")

    return {
        "device_id": device_id,
        "port_name": port_name,
        "action": body.action,
        "success": result.get("success", False),
        "message": result.get("message", ""),
    }


# ── GET /api/devices/{device_id}/system ────────────────────

@devices_router.get("/{device_id}/system")
def get_device_system(device_id: int, db: Session = Depends(get_db)):
    """
    REQ-FUNC-115: 查看模拟器 CPU/内存/IO 使用情况。
    仅适用于 SIMULATOR 设备。
    """
    repo = DeviceRepository(db)
    device = repo.get_device_by_id(device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="设备不存在")
    if device.device_type != "SIMULATOR":
        return {"device_id": device_id, "message": "系统资源查看仅适用于模拟器设备"}

    lm = _get_lifecycle_manager()
    sys_data = lm.get_system(device_id)
    if sys_data is None:
        raise HTTPException(status_code=400, detail="模拟器未运行，请先启动模拟器")

    return {
        "device_id": device_id,
        "cpu": sys_data.get("cpu", {}),
        "memory": sys_data.get("memory", {}),
        "io": sys_data.get("io", {}),
    }
