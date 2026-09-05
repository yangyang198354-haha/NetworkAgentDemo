"""
MOD-WEB-001: Devices Router — CRUD /api/devices* (14 endpoints).
@author sub_agent_software_developer
@module MOD-WEB-001
@covers REQ-WEBUI-FUNC-010, REQ-WEBUI-FUNC-011, REQ-WEBUI-FUNC-012
@extended REQ-FUNC-112 ~ REQ-FUNC-115 (device_simulator)
@extended REAL-DEVICE-001~005    (真实设备接入 + FRP 穿透 + 连通性校验)
"""

from datetime import datetime, timezone

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
    # REQ-FUNC-112 / REAL-DEVICE-001: MOCK | SIMULATOR | REAL
    device_type: Optional[str] = "MOCK"
    simulator_port: Optional[int] = None          # 仅 SIMULATOR: 模拟器 SSH 端口

    # REAL-DEVICE-002/003 真实设备接入参数（仅 device_type=REAL 时必填/建议）
    connection_protocol: Optional[str] = None     # SSH (默认) | TELNET | HTTP
    frp_proxy_host: Optional[str] = None          # FRP 映射后的可达地址（空=直连 device_ip）
    frp_proxy_port: Optional[int] = None          # FRP 映射后的协议端口（SSH 对应）


class DeviceUpdate(BaseModel):
    device_name: Optional[str] = None
    device_ip: Optional[str] = None
    device_model: Optional[str] = None
    group_name: Optional[str] = None
    status: Optional[str] = None
    device_type: Optional[str] = None
    simulator_port: Optional[int] = None
    connection_protocol: Optional[str] = None
    frp_proxy_host: Optional[str] = None
    frp_proxy_port: Optional[int] = None


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
    host: str = "0.0.0.0"
    port: int = 0
    ssh_username: str = "admin"
    ssh_password: str = "switch123"


# ── Helper: build device response dict ────────────────────

def _device_to_dict(d) -> dict:
    item = {
        "id": d.id,
        "device_name": d.device_name,
        "device_ip": d.device_ip,
        "device_model": d.device_model,
        "group_name": d.group_name,
        "device_type": d.device_type or "MOCK",
        "simulator_port": d.simulator_port,
        "simulator_status": d.simulator_status or "STOPPED",
        # REAL-DEVICE-002/003
        "connection_protocol": getattr(d, "connection_protocol", None),
        "frp_proxy_host": getattr(d, "frp_proxy_host", None),
        "frp_proxy_port": getattr(d, "frp_proxy_port", None),
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
    """Add a new managed device. Supports MOCK | SIMULATOR | REAL."""
    repo = DeviceRepository(db)

    device_type = (body.device_type or "MOCK").upper()
    if device_type not in ("MOCK", "SIMULATOR", "REAL"):
        raise HTTPException(status_code=400,
                            detail="device_type must be one of: MOCK, SIMULATOR, REAL")

    # REAL-DEVICE-001: input validation for REAL devices
    if device_type == "REAL":
        # frp_proxy_host/port is optional (when the service runs on the same network
        # as the device, or the user provides the already-mapped address in device_ip).
        proto = (body.connection_protocol or "SSH").upper()
        if proto not in ("SSH", "TELNET", "HTTP"):
            raise HTTPException(status_code=400,
                                detail="connection_protocol for REAL must be SSH|TELNET|HTTP")
        if bool(body.frp_proxy_host) != bool(body.frp_proxy_port):
            raise HTTPException(status_code=400,
                                detail="frp_proxy_host and frp_proxy_port must be provided together")
    else:
        proto = None

    existing = repo.list_devices()
    if any(d.device_name == body.device_name for d in existing):
        raise HTTPException(status_code=409,
                            detail=f"设备名称 '{body.device_name}' 已存在，请使用其他名称")

    device_data = {
        "device_name": body.device_name,
        "device_ip": body.device_ip,
        "device_model": body.device_model,
        "group_name": body.group_name,
        "device_type": device_type,
        "simulator_port": body.simulator_port,
        "simulator_status": "STOPPED" if device_type == "SIMULATOR" else None,
        "connection_protocol": proto,
        "frp_proxy_host": body.frp_proxy_host,
        "frp_proxy_port": body.frp_proxy_port,
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
    repo = DeviceRepository(db)
    device = repo.get_device_by_id(device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="设备不存在")

    item = _device_to_dict(device)
    if device.device_type == "SIMULATOR":
        try:
            lm = _get_lifecycle_manager()
            live = lm.get_status(device_id)
            if live.get("running"):
                item["simulator_status"] = "RUNNING"
                item["simulator_port"] = live.get("port") or item["simulator_port"]
        except HTTPException:
            pass
    return item


# ── PUT /api/devices/{device_id} ───────────────────────────

@devices_router.put("/{device_id}")
async def update_device(device_id: int, body: DeviceUpdate, db: Session = Depends(get_db)):
    repo = DeviceRepository(db)
    # NOTE: use exclude_unset=True only (NOT exclude_none=True) so that the caller
    # can explicitly clear a nullable column back to NULL by sending `null`.
    # This matters for REAL-device columns: frp_proxy_host=None / frp_proxy_port=None
    # means "stop routing through FRP — talk to the device directly on its LAN IP".
    data = body.model_dump(exclude_unset=True)
    # REAL validation: whitelist protocol + paired host/port (same as create_device)
    if "device_type" in data and str(data["device_type"]).upper() == "REAL":
        if "connection_protocol" in data and data["connection_protocol"] is not None:
            p = str(data["connection_protocol"]).upper()
            if p not in ("SSH", "TELNET", "HTTP"):
                raise HTTPException(status_code=400,
                                    detail="connection_protocol for REAL must be SSH|TELNET|HTTP")
        if bool(data.get("frp_proxy_host")) != bool(data.get("frp_proxy_port")):
            raise HTTPException(
                status_code=400,
                detail="frp_proxy_host and frp_proxy_port must be provided together (or both null to clear)",
            )
    device = repo.update_device(device_id, data)
    if device is None:
        raise HTTPException(status_code=404, detail="设备不存在")
    return {"message": "设备已更新", "device_id": device.id}


# ── DELETE /api/devices/{device_id} ────────────────────────

@devices_router.delete("/{device_id}")
async def delete_device(device_id: int, db: Session = Depends(get_db)):
    repo = DeviceRepository(db)
    device = repo.get_device_by_id(device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="设备不存在")

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
    repo = DeviceRepository(db)
    results = repo.get_device_diagnostics(device_id)
    return {"device_id": device_id, "diagnostics": results}


# ═══════════════════════════════════════════════════════════
# 模拟器专用端点
# ═══════════════════════════════════════════════════════════

@devices_router.post("/{device_id}/simulator/start")
def simulator_start(device_id: int, body: SimulatorStartRequest, db: Session = Depends(get_db)):
    repo = DeviceRepository(db)
    device = repo.get_device_by_id(device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="设备不存在")
    if device.device_type != "SIMULATOR":
        raise HTTPException(status_code=400, detail="仅模拟器设备支持此操作")

    lm = _get_lifecycle_manager()
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
        repo.update_device(device_id, {
            "simulator_port": actual_ssh_port,
            "simulator_status": "RUNNING",
            "status": "ONLINE",
        })

    return {
        "success": success,
        "message": message,
        "ssh_port": actual_ssh_port,
        "mgmt_port": actual_mgmt_port,
    }


@devices_router.post("/{device_id}/simulator/stop")
def simulator_stop(device_id: int, db: Session = Depends(get_db)):
    repo = DeviceRepository(db)
    device = repo.get_device_by_id(device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="设备不存在")

    lm = _get_lifecycle_manager()
    success, message = lm.stop_simulator(device_id)
    if success:
        repo.update_device(device_id, {"simulator_status": "STOPPED", "status": "OFFLINE"})
    return {"success": success, "message": message}


@devices_router.get("/{device_id}/simulator/status")
def simulator_status(device_id: int, db: Session = Depends(get_db)):
    repo = DeviceRepository(db)
    device = repo.get_device_by_id(device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="设备不存在")
    if device.device_type != "SIMULATOR":
        return {"device_id": device_id, "running": False, "status": "N/A",
                "message": "非模拟器设备"}
    lm = _get_lifecycle_manager()
    return lm.get_status(device_id)


# ═══════════════════════════════════════════════════════════
# 心跳 + 连通性检测（REAL-DEVICE-006/007）
# ═══════════════════════════════════════════════════════════

def _encrypt_svc():
    import sys
    main_module = sys.modules.get("src.main")
    if not main_module:
        return None
    return getattr(main_module, "encryption_service", None)


def _decrypt_password(device) -> Optional[str]:
    """Return plain password for the device credential, or None if missing/unavailable."""
    if not device.credential:
        return None
    svc = _encrypt_svc()
    if svc is None:
        return None
    try:
        return svc.decrypt(device.credential.ssh_password_encrypted)
    except Exception:
        return None


@devices_router.post("/{device_id}/heartbeat")
def device_heartbeat(device_id: int, db: Session = Depends(get_db)):
    """
    REQ-FUNC-113 / REAL-DEVICE-006: 心跳检测
      - SIMULATOR: use lifecycle manager SSH port
      - REAL: TCP check on FRP/protocol endpoint
      - MOCK: return UNKNOWN
    """
    repo = DeviceRepository(db)
    device = repo.get_device_by_id(device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="设备不存在")

    if device.device_type == "MOCK":
        return {
            "device_id": device_id,
            "status": "UNKNOWN",
            "message": "心跳检测对 Mock 设备无意义（返回 UNKNOWN）",
            "response_time_ms": None,
        }

    if device.device_type == "SIMULATOR":
        lm = _get_lifecycle_manager()
        live_status = lm.get_status(device_id)
        if live_status.get("running") and live_status.get("ssh_port"):
            ssh_host, ssh_port = "127.0.0.1", live_status["ssh_port"]
        elif device.simulator_port:
            ssh_host, ssh_port = "127.0.0.1", device.simulator_port
        else:
            repo.update_device(device_id, {"status": "OFFLINE"})
            return {"device_id": device_id, "status": "OFFLINE", "response_time_ms": None}
        is_online, response_ms = lm.heartbeat(ssh_host, ssh_port)
        new_status = "ONLINE" if is_online else "OFFLINE"
        repo.update_device(device_id, {"status": new_status})
        return {
            "device_id": device_id,
            "status": new_status,
            "response_time_ms": response_ms,
        }

    # REAL-DEVICE-006
    from src.tools.real_device_client import tcp_heartbeat
    is_online, response_ms = tcp_heartbeat(device, timeout_s=3.0)
    new_status = "ONLINE" if is_online else "OFFLINE"
    repo.update_device(device_id, {"status": new_status})
    return {
        "device_id": device_id,
        "device_type": "REAL",
        "protocol": device.connection_protocol or "SSH",
        "proxy_host": device.frp_proxy_host or "(直连)",
        "proxy_port": device.frp_proxy_port,
        "status": new_status,
        "response_time_ms": response_ms,
    }


# ═══════════════════════════════════════════════════════════
# REAL-DEVICE-007: Full protocol-level connectivity check
# ═══════════════════════════════════════════════════════════

@devices_router.post("/{device_id}/check_connectivity")
def device_check_connectivity(device_id: int, db: Session = Depends(get_db)):
    """
    REAL-DEVICE-007: 真实设备的完整协议握手检测（L4 + L7）。

    行为：
      - 先做 TCP 可达（与 heartbeat 相同）；
      - 再建立真实 SSH/Telnet/HTTP 会话，登录并执行 `show system-info` / `show version`，
        回显设备型号 + 软件版本 + 原始输出摘要；
      - 成功后将 status 更新为 ONLINE，并写入 last_diag_at；
      - 对 MOCK/SIMULATOR 返回明确的"不适用"提示。
    """
    repo = DeviceRepository(db)
    device = repo.get_device_by_id(device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="设备不存在")

    if device.device_type != "REAL":
        return {
            "device_id": device_id,
            "device_type": device.device_type,
            "ok": False,
            "message": "/check_connectivity 仅适用于 REAL 真实设备",
        }

    if not device.credential:
        return {
            "device_id": device_id,
            "device_type": "REAL",
            "ok": False,
            "message": "该 REAL 设备还未配置凭据，请先 PUT /api/devices/{id}/credentials",
        }

    from src.tools.real_device_client import check_connectivity as _l7_check

    username = device.credential.ssh_username
    password = _decrypt_password(device)
    if password is None:
        return {
            "device_id": device_id,
            "device_type": "REAL",
            "ok": False,
            "message": "无法解密凭据，encryption_service 未初始化或密码损坏",
        }

    report = _l7_check(device, username, password)
    repo_update = {}
    if report.ok:
        repo_update["status"] = "ONLINE"
        repo_update["last_diag_at"] = datetime.now(timezone.utc)
        if report.model and not device.device_model:
            repo_update["device_model"] = report.model
    else:
        repo_update["status"] = "OFFLINE"
    if repo_update:
        repo.update_device(device_id, repo_update)

    return {
        "device_id": device_id,
        "device_type": "REAL",
        "ok": report.ok,
        "layer": report.layer,
        "protocol": device.connection_protocol or "SSH",
        "proxy_host": device.frp_proxy_host or "(直连)",
        "proxy_port": device.frp_proxy_port,
        "latency_ms": report.latency_ms,
        "message": report.message,
        "banner_excerpt": report.banner[:600],
        "device_model": report.model or device.device_model,
        "software_version": report.software_version,
    }


# ── REAL 设备：通过 Telnet 远程启用 SSH 服务 ─────────────
@devices_router.post("/{device_id}/configure_ssh")
def device_configure_ssh(device_id: int, db: Session = Depends(get_db)):
    """连接 REAL 设备（通过 Telnet），执行 SSH 配置命令：
    crypto key generate rsa + ip ssh server + 保存配置。
    适用于 TP-Link TL-SG5428 等支持 CLI 的交换机。
    """
    repo = DeviceRepository(db)
    device = repo.get_device_by_id(device_id)
    if device is None:
        raise HTTPException(404, "设备不存在")
    if device.device_type != "REAL":
        return {"device_id": device_id, "ok": False,
                "message": "/configure_ssh 仅适用于 REAL 真实设备"}

    if not device.credential:
        return {"device_id": device_id, "ok": False,
                "message": "该 REAL 设备还未配置凭据"}

    from src.tools.real_device_client import (
        _TelnetSession, _PlinkSession, PLINK_EXE, _resolve_access,
    )
    import time as _time

    username = device.credential.ssh_username
    password = _decrypt_password(device)
    if password is None:
        return {"device_id": device_id, "ok": False,
                "message": "无法解密凭据"}

    host, port, protocol = _resolve_access(device)

    # L4 check first
    from src.tools.real_device_client import _tcp_check
    ok, ms = _tcp_check(host, int(port))
    if not ok:
        return {"device_id": device_id, "ok": False,
                "message": f"TCP {host}:{port} 不可达，无法配置 SSH"}
    _time.sleep(0.6)

    commands_output = []
    ssh_status = ""
    try:
        # Prefer raw socket _TelnetSession for Windows Defender: plink's
        # stdio mode on Windows can be intercepted with RST (WinError 10053).
        # We keep plink as fallback if raw socket fails (e.g. older switch
        # firmware with complex IAC negotiation).
        last_err = None
        sess = None
        for cls in (_TelnetSession, _PlinkSession):
            try:
                if cls is _PlinkSession:
                    if not PLINK_EXE:
                        continue
                    sess = _PlinkSession("TELNET", host, int(port), username, password, timeout=12)
                else:
                    sess = _TelnetSession(host, int(port), username, password, timeout=12)
                sess.open()
                break
            except OSError as e:
                last_err = f"{cls.__name__} open failed: {e}"
                try: sess.close()
                except Exception: pass
                sess = None
                _time.sleep(0.5)
            except Exception as e:
                last_err = f"{cls.__name__} open failed: {e}"
                try: sess.close()
                except Exception: pass
                sess = None
                break
        if sess is None:
            return {"device_id": device_id, "ok": False,
                    "message": f"无法建立 TELNET 会话: {last_err}"}

        try:
            # TP-Link TL-SG5428: crypto key generate rsa is optional if key
            # already exists; switch will return "Bad command" when rsa key
            # is already present. We treat this as non-fatal.
            cmds_ok, cmds_fail, cmds_log = sess.configure([
                "crypto key generate rsa",
                "ip ssh server",
            ])
            commands_output.append(
                f"configure session: exec_ok={cmds_ok}, fail={cmds_fail}\n{cmds_log}"
            )
            # 退出 configure 模式后保存配置（save method handles mode + prompts）
            saved, save_log = sess.save()
            commands_output.append(f"save: ok={saved}\n{save_log}")
            # 验证 SSH 状态
            ssh_status = sess.show("ip ssh")
            commands_output.append(ssh_status)
        finally:
            sess.close()

        combined = "\n".join(str(c) for c in commands_output)
        return {
            "device_id": device_id,
            "ok": True,
            "message": "SSH 配置命令已执行",
            "output": combined[:2000],
            "ssh_status": ssh_status[:500],
        }
    except Exception as e:
        return {
            "device_id": device_id,
            "ok": False,
            "message": f"配置失败: {type(e).__name__}: {e}",
            "output": "\n".join(str(c) for c in commands_output)[:2000],
        }


# ═══════════════════════════════════════════════════════════
# 模拟器工具端点（保持不变）
# ═══════════════════════════════════════════════════════════

@devices_router.get("/{device_id}/ports")
def get_device_ports(device_id: int, db: Session = Depends(get_db)):
    repo = DeviceRepository(db)
    device = repo.get_device_by_id(device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="设备不存在")
    if device.device_type != "SIMULATOR":
        return {"device_id": device_id, "ports": [],
                "message": "端口查看仅适用于模拟器设备（REAL 设备请通过 switch_diag_tool 执行 show interfaces）"}
    lm = _get_lifecycle_manager()
    ports_data = lm.get_ports(device_id)
    if ports_data is None:
        raise HTTPException(status_code=400, detail="模拟器未运行，请先启动模拟器")
    return {
        "device_id": device_id,
        "ports": ports_data.get("ports", []),
        "up_ports_detail": ports_data.get("up_ports_detail", []),
    }


@devices_router.post("/{device_id}/ports/{port_name}/config")
def configure_device_port(
    device_id: int,
    port_name: str,
    body: PortConfigRequest,
    db: Session = Depends(get_db),
):
    repo = DeviceRepository(db)
    device = repo.get_device_by_id(device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="设备不存在")
    if device.device_type != "SIMULATOR":
        raise HTTPException(
            status_code=400,
            detail="端口配置仅适用于模拟器设备（REAL 设备请通过 switch_config_tool 下发 interface commands）"
        )
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


@devices_router.get("/{device_id}/system")
def get_device_system(device_id: int, db: Session = Depends(get_db)):
    repo = DeviceRepository(db)
    device = repo.get_device_by_id(device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="设备不存在")
    if device.device_type != "SIMULATOR":
        return {
            "device_id": device_id,
            "message": (
                "系统资源查看仅适用于模拟器设备。REAL 设备请通过 switch_diag_tool "
                "执行 show cpu / show memory 等命令。"
            ),
        }
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
