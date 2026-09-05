"""
Integration tests for MOD-RP-001: REAL panel API endpoints (devices_router.py).
@author sub_agent_test_engineer
@module MOD-RP-001
@covers REQ-RP-FUNC-006, REQ-RP-FUNC-007, REQ-RP-NFUNC-002, REQ-RP-NFUNC-003
@tracks AC-RP-002-02, AC-RP-005-01, AC-RP-005-02, AC-RP-005-04, AC-RP-006-02,
        AC-RP-008-01, AC-RP-008-02

直接调用路由函数（monkeypatch DeviceRepository / _decrypt_password /
collect_real_panel / configure_real_port / AuditLogger），验证：
  - GET /real_panel: 非 REAL→400、无凭据→400、采集失败→502、成功→200
  - 写端点 REAL 分支: action 校验、审计含 operator 且 detail 无明文密码
  - 写路径不调 save（由 service 单测覆盖，此处验证编排层不直连会话）
  - 非 REAL（SIMULATOR/MOCK）路径零破坏（NFUNC-003）
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from src.models.enums import AuditEventType
from src.tools.real_panel_parsers import RealPanelError
from src.tools.real_panel_service import PortWriteResult

# ── Robust module load ─────────────────────────────────────────────
# `src.api.__init__` 将 `devices_router` 名字重绑定为 APIRouter 实例；且既有
# test_inspection_systemd_integration.py 在模块加载期会把 sys.modules["src.api"]
# 替换为 MagicMock（预存在测试隔离缺陷）。为保证本文件在单跑与全量回归下均可用，
# 按仓库既有约定（inspection_router "raw module for test mocking"）直接从文件
# 加载 devices_router 与其依赖 dependencies，不依赖 src.api 包结构。
_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _load_from_file(module_name: str, relpath: str):
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, str(_PROJECT_ROOT / relpath))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


_load_from_file("src.api.dependencies", "src/api/dependencies.py")
router = _load_from_file("src.api.devices_router", "src/api/devices_router.py")


def _make_device(device_type="REAL", with_cred=True, cred_username="admin"):
    cred = None
    if with_cred:
        cred = SimpleNamespace(
            ssh_username=cred_username,
            ssh_password_encrypted="enc-bytes",
            ssh_port=22,
        )
    return SimpleNamespace(
        id=1,
        device_type=device_type,
        device_name="core-sw-1",
        device_ip="10.0.0.1",
        device_model=None,
        connection_protocol="SSH",
        frp_proxy_host=None,
        frp_proxy_port=None,
        credential=cred,
    )


def _make_user(username="ops-admin"):
    return SimpleNamespace(username=username)


class _FakeRepo:
    def __init__(self, device):
        self._device = device

    def get_device_by_id(self, device_id):
        if self._device is not None and self._device.id == device_id:
            return self._device
        return None


def _patch_repo(device):
    return patch("src.api.devices_router.DeviceRepository", lambda db: _FakeRepo(device))


# ═══════════════════════════════════════════════════════════
# GET /real_panel
# ═══════════════════════════════════════════════════════════

class TestGetRealPanel:
    def test_device_not_found_404(self):
        with _patch_repo(None):
            with pytest.raises(HTTPException) as ei:
                router.get_real_panel(999, db=MagicMock())
        assert ei.value.status_code == 404

    def test_non_real_400(self):
        device = _make_device(device_type="SIMULATOR")
        with _patch_repo(device):
            with pytest.raises(HTTPException) as ei:
                router.get_real_panel(1, db=MagicMock())
        assert ei.value.status_code == 400
        assert "REAL" in ei.value.detail

    def test_no_credential_400(self):
        device = _make_device(device_type="REAL", with_cred=False)
        with _patch_repo(device):
            with pytest.raises(HTTPException) as ei:
                router.get_real_panel(1, db=MagicMock())
        assert ei.value.status_code == 400

    def test_decrypt_none_400(self):
        device = _make_device(device_type="REAL")
        with _patch_repo(device), \
             patch("src.api.devices_router._decrypt_password", return_value=None):
            with pytest.raises(HTTPException) as ei:
                router.get_real_panel(1, db=MagicMock())
        assert ei.value.status_code == 400

    def test_collection_real_panel_error_502(self):
        device = _make_device(device_type="REAL")
        with _patch_repo(device), \
             patch("src.api.devices_router._decrypt_password", return_value="secret"), \
             patch("src.tools.real_panel_service.collect_real_panel",
                   side_effect=RealPanelError("ports", "解析失败")):
            with pytest.raises(HTTPException) as ei:
                router.get_real_panel(1, db=MagicMock())
        assert ei.value.status_code == 502
        assert "ports" in ei.value.detail

    def test_collection_generic_error_502(self):
        device = _make_device(device_type="REAL")
        with _patch_repo(device), \
             patch("src.api.devices_router._decrypt_password", return_value="secret"), \
             patch("src.tools.real_panel_service.collect_real_panel",
                   side_effect=RuntimeError("boom")):
            with pytest.raises(HTTPException) as ei:
                router.get_real_panel(1, db=MagicMock())
        assert ei.value.status_code == 502

    def test_success_200(self):
        device = _make_device(device_type="REAL")
        snapshot = {"device_id": 1, "ports": [], "cpu": {}, "memory": {}, "io": {}, "info": None}
        with _patch_repo(device), \
             patch("src.api.devices_router._decrypt_password", return_value="secret"), \
             patch("src.tools.real_panel_service.collect_real_panel", return_value=snapshot):
            resp = router.get_real_panel(1, db=MagicMock())
        assert resp == snapshot


# ═══════════════════════════════════════════════════════════
# POST /ports/{port_name}/config — REAL 分支
# ═══════════════════════════════════════════════════════════

class TestConfigureRealPortApi:
    def test_device_not_found_404(self):
        with _patch_repo(None):
            with pytest.raises(HTTPException) as ei:
                router.configure_device_port(
                    999, "Gi0/1", SimpleNamespace(action="shutdown"),
                    db=MagicMock(), current_user=_make_user(),
                )
        assert ei.value.status_code == 404

    def test_invalid_action_400(self):
        device = _make_device(device_type="REAL")
        with _patch_repo(device):
            with pytest.raises(HTTPException) as ei:
                router.configure_device_port(
                    1, "Gi0/1", SimpleNamespace(action="set-vlan"),
                    db=MagicMock(), current_user=_make_user(),
                )
        assert ei.value.status_code == 400
        assert "shutdown" in ei.value.detail

    def test_no_credential_400(self):
        device = _make_device(device_type="REAL", with_cred=False)
        with _patch_repo(device):
            with pytest.raises(HTTPException) as ei:
                router.configure_device_port(
                    1, "Gi0/1", SimpleNamespace(action="shutdown"),
                    db=MagicMock(), current_user=_make_user(),
                )
        assert ei.value.status_code == 400

    def test_success_audits_with_operator_and_no_password(self):
        device = _make_device(device_type="REAL")
        mock_audit = MagicMock()
        mock_audit.return_value.log_audit_event.return_value = "audit-123"

        with _patch_repo(device), \
             patch("src.api.devices_router._decrypt_password", return_value="s3cr3t-pw"), \
             patch("src.tools.real_panel_service.configure_real_port",
                   return_value=PortWriteResult(success=True, message="端口配置成功", output="ok")), \
             patch("src.security.audit_logger.AuditLogger", mock_audit):
            resp = router.configure_device_port(
                1, "Gi0/1", SimpleNamespace(action="shutdown"),
                db=MagicMock(), current_user=_make_user("ops-admin"),
            )

        assert resp["success"] is True
        assert resp["action"] == "shutdown"
        assert resp["audit_record_id"] == "audit-123"

        # 审计调用参数校验（AC-RP-006-02）
        mock_audit.return_value.log_audit_event.assert_called_once()
        kwargs = mock_audit.return_value.log_audit_event.call_args.kwargs
        assert kwargs["event_type"] == AuditEventType.CONFIG_CHANGE
        assert kwargs["alert_id"] == "device:1"
        assert kwargs["operator"] == "ops-admin"
        assert kwargs["action"] == "port_shutdown"

        detail = kwargs["detail"]
        assert detail["device_id"] == 1
        assert detail["device_name"] == "core-sw-1"
        assert detail["port_name"] == "Gi0/1"
        # 硬性安全：detail 无明文密码
        assert "password" not in json.dumps(detail)
        assert "s3cr3t-pw" not in json.dumps(detail)

    def test_no_shutdown_audit_action(self):
        device = _make_device(device_type="REAL")
        mock_audit = MagicMock()
        mock_audit.return_value.log_audit_event.return_value = "audit-456"

        with _patch_repo(device), \
             patch("src.api.devices_router._decrypt_password", return_value="pw"), \
             patch("src.tools.real_panel_service.configure_real_port",
                   return_value=PortWriteResult(success=True, message="ok", output="")), \
             patch("src.security.audit_logger.AuditLogger", mock_audit):
            router.configure_device_port(
                1, "Gi0/1", SimpleNamespace(action="no-shutdown"),
                db=MagicMock(), current_user=_make_user(),
            )
        kwargs = mock_audit.return_value.log_audit_event.call_args.kwargs
        assert kwargs["action"] == "port_no_shutdown"

    def test_write_failure_502(self):
        device = _make_device(device_type="REAL")
        with _patch_repo(device), \
             patch("src.api.devices_router._decrypt_password", return_value="pw"), \
             patch("src.tools.real_panel_service.configure_real_port",
                   side_effect=RuntimeError("cmd failed")):
            with pytest.raises(HTTPException) as ei:
                router.configure_device_port(
                    1, "Gi0/1", SimpleNamespace(action="shutdown"),
                    db=MagicMock(), current_user=_make_user(),
                )
        assert ei.value.status_code == 502


# ═══════════════════════════════════════════════════════════
# NFUNC-003 回归：非 REAL 路径零破坏
# ═══════════════════════════════════════════════════════════

class TestSimulatorPathRegression:
    def test_mock_device_config_returns_simulator_only_message(self):
        # 既有 SIMULATOR 分支守卫逻辑不变：非 SIMULATOR 返回原提示
        device = _make_device(device_type="MOCK")
        with _patch_repo(device):
            with pytest.raises(HTTPException) as ei:
                router.configure_device_port(
                    1, "Gi0/1", SimpleNamespace(action="shutdown"),
                    db=MagicMock(), current_user=_make_user(),
                )
        assert ei.value.status_code == 400
        assert "模拟器" in ei.value.detail

    def test_ports_endpoint_real_returns_simulator_only_message(self):
        # 现有 /ports 端点对 REAL 仍返回"仅模拟器"提示（NFUNC-003：零变更）
        device = _make_device(device_type="REAL")
        with _patch_repo(device):
            resp = router.get_device_ports(1, db=MagicMock())
        assert resp["ports"] == []
        assert "模拟器" in resp["message"]
