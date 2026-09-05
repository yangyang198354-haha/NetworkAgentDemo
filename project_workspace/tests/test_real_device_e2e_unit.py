"""
Unit tests for REAL device E2E workflow — pure functions (MOD-RE-001 ~ MOD-RE-006).
@author sub_agent_test_engineer
@covers US-RE-001 ~ US-RE-008 (AC-RE-001-01 ~ AC-RE-008-02)
@note Uses mock/monkeypatch to isolate DB and real_device_client; NEVER connects
      to a real switch.
"""
import os
import types

import pytest

from src.models.enums import AlertType
from src.orchestration import node_handlers as nh
from src.tools.real_device_client import (
    _tp_link_full_port_name,
    _normalize_tp_link_commands,
    _TelnetSession,
)
from src.orchestration.node_handlers import (
    FixCapability,
    RealAccessContext,
    NodeHandlers,
    resolve_real_access,
    enrich_device_info,
    _resolve_real_credentials,
    get_diag_commands,
    parse_diag_output,
    resolve_fix_capability,
    get_fix_template,
    build_degraded_fix_plan,
    verify_real_fix,
    REAL_WRITE_PORT_WHITELIST,
    REAL_CREDENTIAL_MISSING_MSG,
    DEGRADED_FIX_DESCRIPTION,
)


# ── 共享夹具 ─────────────────────────────────────────────

class _FakeResult:
    def __init__(self, row):
        self._row = row

    def scalar_one_or_none(self):
        return self._row


class _FakeDb:
    """Fake SQLAlchemy Session: execute() returns a fixed result, close() is a no-op."""

    def __init__(self, row=None):
        self._row = row

    def execute(self, *args, **kwargs):
        return _FakeResult(self._row)

    def close(self):
        pass


class _FakeRepo:
    def __init__(self, devices):
        self._devices = devices

    def list_devices(self):
        return list(self._devices)


def _fake_device(name="TL-SG5428-核心交换机", model="TL-SG5428",
                 frp_host="127.0.0.1", frp_port=6022, protocol="SSH",
                 ip="192.168.31.220"):
    return types.SimpleNamespace(
        device_name=name,
        device_model=model,
        frp_proxy_host=frp_host,
        frp_proxy_port=frp_port,
        connection_protocol=protocol,
        device_ip=ip,
        credential=None,
    )


# ────────────────────────────────────────────────────────
# AC-RE-006-01 / AC-RE-001-02: resolve_real_access
# ────────────────────────────────────────────────────────

class TestResolveRealAccess:
    def test_db_no_device_returns_none(self, monkeypatch):
        monkeypatch.setattr("src.database.base.SessionLocal", lambda: _FakeDb())
        monkeypatch.setattr(
            "src.database.repositories.device_repository.DeviceRepository",
            lambda db: _FakeRepo([]),
        )
        assert resolve_real_access("unknown-device") is None

    def test_matched_device_resolves_frp_access(self, monkeypatch):
        device = _fake_device()
        monkeypatch.setattr("src.database.base.SessionLocal", lambda: _FakeDb())
        monkeypatch.setattr(
            "src.database.repositories.device_repository.DeviceRepository",
            lambda db: _FakeRepo([device]),
        )
        monkeypatch.setattr(
            "src.tools.real_device_client._resolve_access",
            lambda d: ("127.0.0.1", 6022, "SSH"),
        )
        ctx = resolve_real_access("TL-SG5428-核心交换机")
        assert isinstance(ctx, RealAccessContext)
        assert ctx.host == "127.0.0.1"
        assert ctx.port == 6022
        assert ctx.protocol == "SSH"
        assert ctx.device_model == "TL-SG5428"
        assert ctx.frp_proxy_host == "127.0.0.1"
        assert ctx.frp_proxy_port == 6022

    def test_session_local_exception_returns_none(self, monkeypatch):
        def _boom():
            raise RuntimeError("no db")
        monkeypatch.setattr("src.database.base.SessionLocal", _boom)
        assert resolve_real_access("TL-SG5428-核心交换机") is None


# ────────────────────────────────────────────────────────
# enrich_device_info (IFC-RE-001-02)
# ────────────────────────────────────────────────────────

class TestEnrichDeviceInfo:
    def test_backfills_frp_protocol_model(self):
        access = RealAccessContext(
            host="127.0.0.1", port=6022, protocol="SSH",
            device_model="TL-SG5428", frp_proxy_host="127.0.0.1", frp_proxy_port=6022,
        )
        di = {"device_name": "TL-SG5428-核心交换机"}
        enriched = enrich_device_info(di, access)
        assert enriched["device_ip"] == "127.0.0.1"
        assert enriched["port"] == 6022
        assert enriched["protocol"] == "SSH"
        assert enriched["device_model"] == "TL-SG5428"
        assert enriched["frp_proxy_host"] == "127.0.0.1"
        assert enriched["frp_proxy_port"] == 6022


# ────────────────────────────────────────────────────────
# AC-RE-006-01: _resolve_real_credentials
# ────────────────────────────────────────────────────────

class TestResolveRealCredentials:
    ENV_KEY = "DEVICE_TL-SG5428-核心交换机_PASSWORD"

    def _patch_db(self, monkeypatch, row=None):
        monkeypatch.setattr("src.database.base.SessionLocal", lambda: _FakeDb(row))

    def test_env_priority_over_db(self, monkeypatch):
        monkeypatch.setenv(self.ENV_KEY, "env-secret")
        self._patch_db(monkeypatch, row=None)
        monkeypatch.setattr(nh, "_decrypt_fernet", lambda token: "db-secret")
        assert _resolve_real_credentials("TL-SG5428-核心交换机") == ("admin", "env-secret")

    def test_db_fernet_decrypt(self, monkeypatch):
        monkeypatch.delenv(self.ENV_KEY, raising=False)
        cred = types.SimpleNamespace(ssh_username="admin", ssh_password_encrypted="fernet-token")
        row = types.SimpleNamespace(credential=cred)
        self._patch_db(monkeypatch, row=row)
        monkeypatch.setattr(nh, "_decrypt_fernet", lambda token: "decrypted-pwd")
        assert _resolve_real_credentials("TL-SG5428-核心交换机") == ("admin", "decrypted-pwd")

    def test_missing_returns_none_no_admin123(self, monkeypatch):
        monkeypatch.delenv(self.ENV_KEY, raising=False)
        self._patch_db(monkeypatch, row=None)
        monkeypatch.setattr(nh, "_decrypt_fernet", lambda token: "")
        result = _resolve_real_credentials("TL-SG5428-核心交换机")
        assert result is None, "REAL credentials must NOT fall back to admin123"

    def test_db_error_returns_none_no_admin123(self, monkeypatch):
        monkeypatch.delenv(self.ENV_KEY, raising=False)
        def _boom():
            raise RuntimeError("db down")
        monkeypatch.setattr("src.database.base.SessionLocal", _boom)
        assert _resolve_real_credentials("TL-SG5428-核心交换机") is None


# ────────────────────────────────────────────────────────
# AC-RE-003-03 / AC-RE-007-02: get_diag_commands
# ────────────────────────────────────────────────────────

class TestGetDiagCommands:
    def test_real_port_down(self):
        assert get_diag_commands("PORT_DOWN", "REAL") == ["show interface status"]

    def test_real_port_shutdown(self):
        assert get_diag_commands("PORT_SHUTDOWN", "REAL") == ["show interface status"]

    def test_real_cpu_high(self):
        assert get_diag_commands("CPU_HIGH", "REAL") == ["show cpu-utilization", "show memory-utilization"]

    def test_real_mac_flapping_space_version(self):
        cmds = get_diag_commands("MAC_FLAPPING", "REAL")
        assert "show mac address-table" in cmds  # 空格版（探测已核实）
        assert "show mac-address-table" not in cmds

    def test_mock_port_down_uses_original_map(self):
        assert get_diag_commands("PORT_DOWN", "MOCK") == nh.DIAG_COMMAND_MAP[AlertType.PORT_DOWN]

    def test_simulator_cpu_high_uses_original_map(self):
        assert get_diag_commands("CPU_HIGH", "SIMULATOR") == nh.DIAG_COMMAND_MAP[AlertType.CPU_HIGH]

    def test_unknown_alert_type_real_falls_back(self):
        assert get_diag_commands("UNKNOWN", "REAL") == ["show interface status"]


# ────────────────────────────────────────────────────────
# AC-RE-002-02: parse_diag_output
# ────────────────────────────────────────────────────────

INTERFACE_DOWN_TEXT = (
    "Port       Status     Vlan   Speed\n"
    "Gi1/0/1    up         1      1000\n"
    "Gi1/0/2    down       1      1000\n"
)
CPU_TEXT = "CPU utilization 45%"

class TestParseDiagOutput:
    def test_real_port_down_structured(self):
        out = parse_diag_output("PORT_DOWN", "REAL", INTERFACE_DOWN_TEXT)
        assert "ports" in out
        names = {p["name"] for p in out["ports"]}
        assert "Gi1/0/2" in names

    def test_real_cpu_structured(self):
        out = parse_diag_output("CPU_HIGH", "REAL", CPU_TEXT)
        assert "cpu" in out
        assert out["cpu"]["cpu_5s"] == 45.0

    def test_real_parse_failure_returns_error(self):
        out = parse_diag_output("PORT_DOWN", "REAL", "garbage without header")
        assert "error" in out
        assert "REAL 诊断解析失败" in out["error"]

    def test_non_real_returns_raw(self):
        out = parse_diag_output("PORT_DOWN", "MOCK", "raw text")
        assert out == {"raw": "raw text"}


# ────────────────────────────────────────────────────────
# AC-RE-003-03: resolve_fix_capability / get_fix_template
# ────────────────────────────────────────────────────────

class TestResolveFixCapability:
    def test_real_port_fixable(self):
        assert resolve_fix_capability("PORT_DOWN", "REAL") == FixCapability.FIXABLE
        assert resolve_fix_capability("PORT_SHUTDOWN", "REAL") == FixCapability.FIXABLE

    def test_real_cpu_mac_degraded(self):
        assert resolve_fix_capability("CPU_HIGH", "REAL") == FixCapability.DEGRADED
        assert resolve_fix_capability("MAC_FLAPPING", "REAL") == FixCapability.DEGRADED

    def test_non_real_all_fixable(self):
        assert resolve_fix_capability("CPU_HIGH", "MOCK") == FixCapability.FIXABLE
        assert resolve_fix_capability("MAC_FLAPPING", "SIMULATOR") == FixCapability.FIXABLE

    def test_unknown_real_defaults_fixable(self):
        assert resolve_fix_capability("UNKNOWN", "REAL") == FixCapability.FIXABLE


class TestGetFixTemplate:
    def test_real_port_template(self):
        assert get_fix_template("PORT_DOWN", "REAL") == "TPL-PORT-ENABLE"
        assert get_fix_template("PORT_SHUTDOWN", "REAL") == "TPL-PORT-DISABLE"

    def test_real_degraded_returns_none(self):
        assert get_fix_template("CPU_HIGH", "REAL") is None
        assert get_fix_template("MAC_FLAPPING", "REAL") is None


# ────────────────────────────────────────────────────────
# AC-RE-008-02: build_degraded_fix_plan
# ────────────────────────────────────────────────────────

class TestBuildDegradedFixPlan:
    def test_empty_commands(self):
        plan = build_degraded_fix_plan("CPU_HIGH")
        assert plan.commands == []
        assert plan.template_id == ""
        assert "修复降级" in plan.description
        assert plan.description == DEGRADED_FIX_DESCRIPTION


# ────────────────────────────────────────────────────────
# AC-RE-004-01: verify_real_fix
# ────────────────────────────────────────────────────────

class TestVerifyRealFix:
    TARGET = "Gi1/0/2"

    def _text(self, status):
        return (
            "Port       Status     Vlan   Speed\n"
            f"Gi1/0/1    up         1      1000\n"
            f"Gi1/0/2    {status}        1      1000\n"
        )

    def test_port_down_down_to_up_passes(self):
        r = verify_real_fix("PORT_DOWN", self._text("down"), self._text("up"), self.TARGET)
        assert r.verify_passed is True
        assert "before=down" in r.comparison_notes
        assert "after=up" in r.comparison_notes

    def test_port_shutdown_up_to_down_passes(self):
        r = verify_real_fix("PORT_SHUTDOWN", self._text("up"), self._text("down"), self.TARGET)
        assert r.verify_passed is True

    def test_cpu_high_not_fixable(self):
        r = verify_real_fix("CPU_HIGH", "before", "after", self.TARGET)
        assert r.verify_passed is False
        assert "修复降级/不可修复" in r.comparison_notes

    def test_mac_flapping_not_fixable(self):
        r = verify_real_fix("MAC_FLAPPING", "before", "after", self.TARGET)
        assert r.verify_passed is False
        assert "修复降级/不可修复" in r.comparison_notes

    def test_parse_failure_not_passed(self):
        r = verify_real_fix("PORT_DOWN", "garbage", "garbage2", self.TARGET)
        assert r.verify_passed is False
        assert "REAL 验证解析失败" in r.comparison_notes


# ────────────────────────────────────────────────────────
# AC-RE-003-02: _sanitize_state_snapshot
# ────────────────────────────────────────────────────────

class TestSanitizeStateSnapshot:
    def test_removes_passwords_keeps_others(self):
        state = {
            "alert_id": "a1",
            "device_info": {
                "device_name": "TL-SG5428-核心交换机",
                "username": "admin",
                "password": "plain-secret",
                "enable_password": "enable-secret",
                "device_ip": "127.0.0.1",
            },
        }
        snap = NodeHandlers._sanitize_state_snapshot(state)
        assert "password" not in snap["device_info"]
        assert "enable_password" not in snap["device_info"]
        assert snap["device_info"]["device_name"] == "TL-SG5428-核心交换机"
        assert snap["alert_id"] == "a1"

    def test_does_not_mutate_original(self):
        state = {
            "device_info": {"password": "plain-secret", "device_ip": "127.0.0.1"},
        }
        NodeHandlers._sanitize_state_snapshot(state)
        assert state["device_info"]["password"] == "plain-secret"

    def test_no_device_info_ok(self):
        snap = NodeHandlers._sanitize_state_snapshot({"alert_id": "a1"})
        assert snap["alert_id"] == "a1"


# ────────────────────────────────────────────────────────
# 白名单 / 常量静态断言（AC-RE-005-01/02）
# ────────────────────────────────────────────────────────

class TestRealWriteWhitelist:
    def test_whitelist_contains_only_authorized_port(self):
        assert REAL_WRITE_PORT_WHITELIST == frozenset({"Gi1/0/2"})

    def test_credential_missing_msg_prohibits_admin123(self):
        # 错误信息仅以「禁止使用」语境提及 admin123，绝不将其作为凭据返回
        assert "禁止使用 admin123 兜底" in REAL_CREDENTIAL_MISSING_MSG


# ────────────────────────────────────────────────────────
# TP-Link 端口名翻译（config-mode `interface` 需要全称）
# ────────────────────────────────────────────────────────

class TestTpLinkPortNameTranslation:
    def test_gi_short_to_full(self):
        assert _tp_link_full_port_name("Gi1/0/2") == "gigabitEthernet 1/0/2"

    def test_te_and_fa(self):
        assert _tp_link_full_port_name("Te1/0/1") == "ten-gigabitEthernet 1/0/1"
        assert _tp_link_full_port_name("fa1/0/1") == "fastEthernet 1/0/1"

    def test_case_insensitive(self):
        assert _tp_link_full_port_name("gi1/0/2") == "gigabitEthernet 1/0/2"
        assert _tp_link_full_port_name("GI1/0/2") == "gigabitEthernet 1/0/2"

    def test_whitespace_tolerance(self):
        assert _tp_link_full_port_name(" Gi1/0/2 ") == "gigabitEthernet 1/0/2"

    def test_non_matching_passthrough(self):
        assert _tp_link_full_port_name("gigabitEthernet 1/0/2") == "gigabitEthernet 1/0/2"
        assert _tp_link_full_port_name("Gi1/0/2/0") == "Gi1/0/2/0"

    def test_normalize_rewrites_interface_line(self):
        cmds = ["interface Gi1/0/2", "shutdown"]
        assert _normalize_tp_link_commands(cmds) == [
            "interface gigabitEthernet 1/0/2",
            "shutdown",
        ]

    def test_normalize_leaves_other_commands_untouched(self):
        cmds = ["configure", "no shutdown", "exit", "show interface status"]
        assert _normalize_tp_link_commands(cmds) == cmds

    def test_normalize_idempotent(self):
        once = _normalize_tp_link_commands(["interface Gi1/0/2"])
        twice = _normalize_tp_link_commands(once)
        assert twice == ["interface gigabitEthernet 1/0/2"]

    def test_normalize_does_not_mutate_original(self):
        cmds = ["interface Gi1/0/2"]
        _normalize_tp_link_commands(cmds)
        assert cmds == ["interface Gi1/0/2"]


# ────────────────────────────────────────────────────────
# 单会话批量下发（interface + shutdown 必须同会话）
# ────────────────────────────────────────────────────────

class TestConfigureRecordsSingleSession:
    def _session(self):
        s = _TelnetSession("h", 23, "u", "p", timeout=1.0)
        calls: list[str] = []
        outputs = {
            "enable": "TL-SG5428#",
            "configure": "TL-SG5428(config)#",
            "interface gigabitEthernet 1/0/2": "TL-SG5428(config-if)#",
            "shutdown": "TL-SG5428(config-if)#",
            "exit": "TL-SG5428(config)#",
        }

        def _fake_run_cmd(cmd, wait=0.8, max_wait=15.0):
            calls.append(cmd)
            return outputs.get(cmd, f"echo {cmd}")

        s._run_cmd = _fake_run_cmd
        return s, calls

    def test_batches_all_commands_in_one_session(self):
        s, calls = self._session()
        records = s.configure_records(["interface Gi1/0/2", "shutdown"])
        # 单会话：enable → configure → 两条命令 → exit（各仅一次）
        assert calls == [
            "enable",
            "configure",
            "interface gigabitEthernet 1/0/2",
            "shutdown",
            "exit",
        ]
        assert len(records) == 2
        assert records[0]["command"] == "interface gigabitEthernet 1/0/2"
        assert records[1]["command"] == "shutdown"
        assert all(r["success"] for r in records)

    def test_marks_error_commands_failed(self):
        s, calls = self._session()
        s._run_cmd = lambda cmd, wait=0.8, max_wait=15.0: (
            "Error: Bad command" if cmd == "shutdown" else f"echo {cmd}"
        )
        records = s.configure_records(["interface Gi1/0/2", "shutdown"])
        assert records[0]["success"] is True
        assert records[1]["success"] is False

    def test_skips_blank_and_comment_commands(self):
        s, calls = self._session()
        records = s.configure_records(["! comment", "", "shutdown"])
        assert [r["command"] for r in records] == ["shutdown"]
