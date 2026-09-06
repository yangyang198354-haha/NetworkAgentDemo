"""
Integration tests for REAL device E2E workflow — NodeHandlers REAL branches.
@author sub_agent_test_engineer
@covers US-RE-001 ~ US-RE-008 (REAL branch wiring: MOD-RE-001 ~ MOD-RE-006 + ADR-RE-007)
@note Mock/monkeypatch isolates DB and real_device_client; NEVER connects to a real switch.
"""
import asyncio
import contextlib
import importlib.util
import sys
import types
from pathlib import Path

import pytest

from src.models.alert import DeviceAuth
from src.models.enums import AlertType, ApprovalStatus, WorkflowStatus
from src.models.fix_plan import DiagResult
from src.orchestration import node_handlers as nh
from src.orchestration.node_handlers import (
    NodeHandlers,
    RealAccessContext,
    REAL_CREDENTIAL_MISSING_MSG,
)
from src.llm.template_engine import TemplateEngine

# 遵循仓库既有约定（test_real_panel_api.py）：`src.api.__init__` 会把子模块名
# 重绑定为 APIRouter 实例，且既有 test_inspection_systemd_integration.py 在模块
# 加载期会替换 sys.modules["src.api"] 为 MagicMock（预存在隔离缺陷）。因此不依赖
# src.api 包结构，直接从文件加载 alerts_router 与其依赖 dependencies。
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
_ALERTS_ROUTER = _load_from_file("src.api.alerts_router", "src/api/alerts_router.py")


# ── 共享夹具 ─────────────────────────────────────────────

class _FakeRepo:
    def __init__(self, devices):
        self._devices = devices

    def list_devices(self):
        return list(self._devices)


def _fake_device(name="TL-SG5428-核心交换机", model="TL-SG5428",
                 dtype="REAL", frp_host="127.0.0.1", frp_port=6022,
                 protocol="SSH", ip="192.168.31.220"):
    return types.SimpleNamespace(
        device_name=name,
        device_model=model,
        device_type=dtype,
        frp_proxy_host=frp_host,
        frp_proxy_port=frp_port,
        connection_protocol=protocol,
        device_ip=ip,
        credential=None,
    )


def _real_state(**overrides):
    state = {
        "alert_id": "alert-real-001",
        "alert_type": "PORT_DOWN",
        "alert_content": "interface Gi1/0/2 down",
        "device_info": {
            "device_name": "TL-SG5428-核心交换机",
            "device_type": "REAL",
            "interface_name": "Gi1/0/2",
        },
        "is_valid": True,
        "status": "ACTIVE",
    }
    state.update(overrides)
    return state


def _make_handlers():
    """NodeHandlers with minimal deps; LLM/template never hit REAL branch in these tests."""
    return NodeHandlers()


def _no_llm(**kw):
    """LLM 桩：抛异常使 handle_generate_fix_plan 回退默认参数，保持测试无网络。"""
    raise RuntimeError("no LLM in test")


# ────────────────────────────────────────────────────────
# AC-RE-002-01 / AC-RE-006-01: handle_get_device_info REAL
# ────────────────────────────────────────────────────────

class TestHandleGetDeviceInfoReal:
    def test_real_enriches_access_and_credentials(self, monkeypatch):
        handlers = _make_handlers()
        access = RealAccessContext(host="127.0.0.1", port=6022, protocol="SSH",
                                   device_model="TL-SG5428",
                                   frp_proxy_host="127.0.0.1", frp_proxy_port=6022)
        monkeypatch.setattr(nh, "resolve_real_access", lambda name: access)
        monkeypatch.setattr(nh, "_resolve_real_credentials", lambda name: ("admin", "secret"))
        state = _real_state()
        out = handlers.handle_get_device_info(state)
        di = out["device_info"]
        assert di["device_ip"] == "127.0.0.1"
        assert di["port"] == 6022
        assert di["protocol"] == "SSH"
        assert di["device_model"] == "TL-SG5428"
        assert di["username"] == "admin"
        assert di["password"] == "secret"

    def test_real_not_registered_returns_failed(self, monkeypatch):
        handlers = _make_handlers()
        monkeypatch.setattr(nh, "resolve_real_access", lambda name: None)
        out = handlers.handle_get_device_info(_real_state())
        assert out["status"] == "FAILED"
        assert "未在 devices 表中注册" in out["_error_message"]

    def test_real_missing_credentials_returns_failed_no_admin123(self, monkeypatch):
        handlers = _make_handlers()
        access = RealAccessContext(host="127.0.0.1", port=6022, protocol="SSH")
        monkeypatch.setattr(nh, "resolve_real_access", lambda name: access)
        monkeypatch.setattr(nh, "_resolve_real_credentials", lambda name: None)
        out = handlers.handle_get_device_info(_real_state())
        assert out["status"] == "FAILED"
        assert out["_error_message"] == REAL_CREDENTIAL_MISSING_MSG
        assert "admin123" not in str(out.get("device_info", {}))


# ────────────────────────────────────────────────────────
# AC-RE-002-01: handle_establish_ssh REAL reachability
# ────────────────────────────────────────────────────────

class TestHandleEstablishSshReal:
    def test_reachable_continues(self, monkeypatch):
        handlers = _make_handlers()
        monkeypatch.setattr(nh, "establish_real_reachability", lambda a, u, p: True)
        state = _real_state(device_info={
            "device_name": "TL-SG5428-核心交换机",
            "device_type": "REAL",
            "device_ip": "127.0.0.1",
            "port": 6022,
            "protocol": "SSH",
            "device_model": "TL-SG5428",
            "username": "admin",
            "password": "secret",
        })
        out = handlers.handle_establish_ssh(state)
        assert out.get("status") != "FAILED"

    def test_unreachable_returns_failed(self, monkeypatch):
        handlers = _make_handlers()
        monkeypatch.setattr(nh, "establish_real_reachability", lambda a, u, p: False)
        state = _real_state(device_info={
            "device_name": "TL-SG5428-核心交换机",
            "device_type": "REAL",
            "device_ip": "127.0.0.1",
            "port": 6022,
            "protocol": "SSH",
            "username": "admin",
            "password": "secret",
        })
        out = handlers.handle_establish_ssh(state)
        assert out["status"] == "FAILED"
        assert "不可达" in out["_error_message"]


# ────────────────────────────────────────────────────────
# AC-RE-003-01 / AC-RE-003-03 / AC-RE-008-02:
# handle_generate_fix_plan REAL (degraded + template)
# ────────────────────────────────────────────────────────

class TestHandleGenerateFixPlanReal:
    def test_cpu_high_renders_dos_prevent(self, monkeypatch):
        handlers = _make_handlers()
        monkeypatch.setattr(handlers.llm_service, "fill_template_params", _no_llm)
        state = _real_state(alert_type="CPU_HIGH", root_cause="cpu busy", diag_result="CPU 92%")
        out = handlers.handle_generate_fix_plan(state)
        fp = out["fix_plan"]
        assert fp["template_id"] == "TPL-REAL-CPU-DOS-PREVENT"
        assert fp["commands"] == ["ip dos-prevent", "ip dos-prevent type syn-flood"]

    def test_mac_flapping_renders_port_security(self, monkeypatch):
        handlers = _make_handlers()
        monkeypatch.setattr(handlers.llm_service, "fill_template_params", _no_llm)
        state = _real_state(alert_type="MAC_FLAPPING", root_cause="flapping", diag_result="mac flapping")
        out = handlers.handle_generate_fix_plan(state)
        fp = out["fix_plan"]
        assert fp["template_id"] == "TPL-REAL-MAC-PORT-SECURITY"
        assert fp["commands"] == [
            "interface Gi1/0/2",
            "mac address-table max-mac-count max-number 10",
            "mac address-table max-mac-count mode dynamic",
            "mac address-table max-mac-count status enable",
        ]

    def test_port_template_renders_two_commands_no_description(self):
        """TC-INT-008 / AC-RE-003-01: PORT 模板去 description 后渲染 2 条命令。"""
        engine = TemplateEngine()
        cmds = engine.render("TPL-PORT-ENABLE", {"iface_name": "Gi1/0/2"})
        assert cmds == ["interface Gi1/0/2", "no shutdown"]
        assert not any("description" in c.lower() for c in cmds)

    def test_port_shutdown_template_no_description(self):
        engine = TemplateEngine()
        cmds = engine.render("TPL-PORT-DISABLE", {"iface_name": "Gi1/0/2"})
        assert cmds == ["interface Gi1/0/2", "shutdown"]
        assert not any("description" in c.lower() for c in cmds)


# ────────────────────────────────────────────────────────
# AC-RE-005-01: handle_execute_fix REAL write whitelist
# ────────────────────────────────────────────────────────

class TestHandleExecuteFixRealWhitelist:
    def test_unauthorized_port_blocked(self, monkeypatch):
        handlers = _make_handlers()
        calls = []
        monkeypatch.setattr(handlers, "_execute_single_command",
                            lambda *a, **k: calls.append(a) or {"success": True})
        state = _real_state(
            fix_plan={"commands": ["interface Gi1/0/5", "no shutdown"],
                      "template_id": "TPL-PORT-ENABLE", "params": {}},
            device_info={"device_name": "TL-SG5428-核心交换机", "device_type": "REAL",
                         "interface_name": "Gi1/0/5"},
        )
        out = handlers.handle_execute_fix(state)
        assert out["status"] == "FAILED"
        assert "越权" in out["_error_message"]
        assert calls == [], "unauthorized port must NOT execute any command"

    def test_authorized_port_executes(self, monkeypatch):
        handlers = _make_handlers()
        sent = []
        cmds = ["interface Gi1/0/2", "no shutdown"]

        class _FakeTool:
            def run_records(self, device_ip, commands, auth, save=False):
                sent.append(list(commands))
                return [{"command": c, "success": True, "output": "ok",
                         "error": None} for c in commands]

        monkeypatch.setattr(
            "src.tools.switch_config_tool.create_switch_config_tool",
            lambda **k: _FakeTool(),
        )
        state = _real_state(
            fix_plan={"commands": cmds,
                      "template_id": "TPL-PORT-ENABLE", "params": {}},
            device_info={"device_name": "TL-SG5428-核心交换机", "device_type": "REAL",
                         "interface_name": "Gi1/0/2"},
        )
        out = handlers.handle_execute_fix(state)
        assert "status" not in out or out.get("status") != "FAILED"
        # 关键回归断言：interface + no shutdown 必须在**同一会话**一次性下发
        assert sent == [cmds], "REAL 写命令必须单会话批量下发（不能逐条分会话）"
        assert len(out["exec_log"]) == 2
        assert all(r["success"] for r in out["exec_log"])

    def test_cpu_high_global_bypasses_port_whitelist_and_saves(self, monkeypatch):
        """CPU_HIGH 的 ip dos-prevent 是全局 config，不走端口白名单，且 save=True。"""
        handlers = _make_handlers()
        sent = []
        cmds = ["ip dos-prevent", "ip dos-prevent type syn-flood"]

        class _FakeTool:
            def run_records(self, device_ip, commands, auth, save=False):
                sent.append((list(commands), save))
                return [{"command": c, "success": True, "output": "ok",
                         "error": None} for c in commands]

        monkeypatch.setattr(
            "src.tools.switch_config_tool.create_switch_config_tool",
            lambda **k: _FakeTool(),
        )
        state = _real_state(
            alert_type="CPU_HIGH",
            fix_plan={"commands": cmds, "template_id": "TPL-REAL-CPU-DOS-PREVENT",
                      "params": {"dos_type": "syn-flood"}},
            device_info={"device_name": "TL-SG5428-核心交换机", "device_type": "REAL"},
        )
        out = handlers.handle_execute_fix(state)
        assert "status" not in out or out.get("status") != "FAILED"
        assert sent == [(cmds, True)], "CPU 全局写不应被端口白名单拦截，且应 save=True"
        assert all(r["success"] for r in out["exec_log"])


# ────────────────────────────────────────────────────────
# AC-RE-004-01: handle_verify_result REAL structured verify
# ────────────────────────────────────────────────────────

AFTER_UP_TEXT = (
    "Port       Status     Vlan   Speed\n"
    "Gi1/0/1    up         1      1000\n"
    "Gi1/0/2    up         1      1000\n"
)
BEFORE_DOWN_TEXT = (
    "Port       Status     Vlan   Speed\n"
    "Gi1/0/1    up         1      1000\n"
    "Gi1/0/2    down       1      1000\n"
)


class TestHandleVerifyResultReal:
    def test_real_port_down_structured_passes(self, monkeypatch):
        handlers = _make_handlers()
        fake_diag_tool = types.SimpleNamespace(
            _run=lambda ip, cmd, auth: DiagResult(success=True, output=AFTER_UP_TEXT)
        )
        monkeypatch.setattr(handlers, "_get_diag_tool_for_device", lambda state: fake_diag_tool)
        monkeypatch.setattr("src.tools.real_device_client._strip_echo_and_prompts",
                            lambda text, cmd: text)
        state = _real_state(
            alert_type="PORT_DOWN",
            diag_result=BEFORE_DOWN_TEXT,
            device_info={"device_name": "TL-SG5428-核心交换机", "device_type": "REAL",
                         "interface_name": "Gi1/0/2", "device_ip": "127.0.0.1",
                         "port": 6022, "protocol": "SSH", "username": "admin", "password": "s"},
        )
        out = handlers.handle_verify_result(state)
        assert out["verify_result"]["verify_passed"] is True


# ────────────────────────────────────────────────────────
# AC-RE-008-02: handle_final_report degraded marker
# ────────────────────────────────────────────────────────

class TestHandleFinalReportDegraded:
    def test_degraded_report_prefixed_and_closed_with_backup(self, monkeypatch):
        handlers = _make_handlers()
        handlers.llm_service = types.SimpleNamespace(
            generate_report=lambda **kw: "# report body"
        )
        state = _real_state(
            alert_type="CPU_HIGH",
            root_cause="cpu busy",
            fix_plan={"commands": [], "template_id": "", "params": {},
                      "description": "修复降级：该告警类型在 TL-SG5428 无已核实 CLI 修复能力",
                      "risk_hints": []},
            exec_log=[],
            verify_result={"verify_passed": False, "before_state": "", "after_state": "",
                           "comparison_notes": "修复降级/不可修复"},
            is_valid=True,
            approval_status="",
            backup_id="bk-1",
        )
        out = handlers.handle_final_report(state)
        assert out["final_report"].startswith("## 修复降级 / 不可修复")
        # 有 backup_id 时，验证失败 → 回滚后 CLOSED
        assert out["status"] == "CLOSED"


# ────────────────────────────────────────────────────────
# TC-INT-013 / AC-RE-003-02 + MOD-RE-006: _real_backup 只读备份不 save
# ────────────────────────────────────────────────────────

class _FakeBackupSession:
    """Fake SSH/Telnet 会话：只记录 show() 收到的命令，绝不真正连接。"""

    def __init__(self, config="hostname SW-01\n"):
        self._config = config
        self.commands: list[str] = []
        self.closed = False

    def show(self, command: str) -> str:
        self.commands.append(command)
        return self._config

    def close(self):
        self.closed = True


class TestRealBackupReadOnly:
    def test_incomplete_auth_returns_failed_no_session(self, monkeypatch):
        opened = []
        monkeypatch.setattr("src.tools.real_device_client._open_ssh_session",
                            lambda *a, **k: opened.append(a) or _FakeBackupSession())
        result = NodeHandlers._real_backup(
            {"device_ip": "127.0.0.1", "port": 6022, "protocol": "SSH"},
            DeviceAuth(username="admin", password=""),
        )
        assert result.success is False
        assert "接入信息不完整" in (result.error or "")
        assert opened == [], "缺凭据时不得建立会话"

    def test_backup_runs_only_show_running_config(self, monkeypatch):
        fake_sess = _FakeBackupSession(config="hostname SW-01\ninterface Gi1/0/2\n")
        monkeypatch.setattr("src.tools.real_device_client._open_ssh_session",
                            lambda h, p, u, pw: fake_sess)
        monkeypatch.setattr("src.tools.real_session_gate.session_guard_by_access",
                            lambda *a, **k: contextlib.nullcontext())
        monkeypatch.setattr("src.tools.real_device_client._strip_echo_and_prompts",
                            lambda text, cmd: text)

        result = NodeHandlers._real_backup(
            {"device_ip": "127.0.0.1", "port": 6022, "protocol": "SSH"},
            DeviceAuth(username="admin", password="secret"),
        )
        assert result.success is True
        assert fake_sess.commands == ["show running-config"]
        assert fake_sess.closed is True
        # 只读红线：绝不调用 save / write / copy running-config startup-config
        assert not any(("save" in c or "write" in c or "startup-config" in c)
                       for c in fake_sess.commands)


# ────────────────────────────────────────────────────────
# AC-RE-001-01/02: alerts_router.simulate_alert REAL 回填
# ────────────────────────────────────────────────────────

class TestSimulateAlertRealBackfill:
    def _patch_main(self, monkeypatch):
        fake_main = types.ModuleType("src.main")
        fake_main.state_graph_engine = types.SimpleNamespace(run_workflow=lambda alert: None)
        fake_main.alert_normalizer = types.SimpleNamespace()
        monkeypatch.setitem(sys.modules, "src.main", fake_main)

    def _patch_alert_repo(self, monkeypatch, captured):
        class _FakeAlertRepo:
            def __init__(self, db):
                pass

            def create_alert(self, data):
                captured["device_info"] = data.get("device_info")

        # 关键：patch alerts_router 命名空间内的 AlertRepository（顶层 from-import 绑定）
        monkeypatch.setattr(_ALERTS_ROUTER, "AlertRepository", _FakeAlertRepo)

    def _patch_device_repo(self, monkeypatch, device):
        monkeypatch.setattr(
            "src.database.repositories.device_repository.DeviceRepository",
            lambda db: _FakeRepo([device]),
        )

    def test_real_backfill_model_ip_interface(self, monkeypatch):
        captured = {}
        self._patch_main(monkeypatch)
        self._patch_device_repo(monkeypatch, _fake_device())
        self._patch_alert_repo(monkeypatch, captured)

        simulate_alert = _ALERTS_ROUTER.simulate_alert
        SimulateAlertRequest = _ALERTS_ROUTER.SimulateAlertRequest
        body = SimulateAlertRequest(alert_type="PORT_DOWN",
                                    device_name="TL-SG5428-核心交换机")
        result = asyncio.run(simulate_alert(body=body, db=object()))
        assert result["alert_type"] == "PORT_DOWN"

        di = captured.get("device_info", {})
        assert di.get("device_model") == "TL-SG5428"
        assert di.get("interface_name") == "Gi1/0/2"
        assert di.get("device_ip") == "192.168.31.220"
        assert di.get("device_type") == "REAL"

    def test_explicit_params_take_priority(self, monkeypatch):
        captured = {}
        self._patch_main(monkeypatch)
        self._patch_device_repo(monkeypatch, _fake_device())
        self._patch_alert_repo(monkeypatch, captured)

        simulate_alert = _ALERTS_ROUTER.simulate_alert
        SimulateAlertRequest = _ALERTS_ROUTER.SimulateAlertRequest
        body = SimulateAlertRequest(alert_type="PORT_DOWN",
                                    device_name="TL-SG5428-核心交换机",
                                    device_ip="10.0.0.9",
                                    interface="Gi1/0/9")
        asyncio.run(simulate_alert(body=body, db=object()))

        di = captured.get("device_info", {})
        assert di.get("device_ip") == "10.0.0.9"
        assert di.get("interface_name") == "Gi1/0/9"
