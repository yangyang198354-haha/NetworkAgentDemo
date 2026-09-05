"""
Unit tests for MOD-RP-002: REAL panel collection service (real_panel_service.py).
@author sub_agent_test_engineer
@module MOD-RP-002
@covers REQ-RP-FUNC-002/003/004/005/006/007/010, REQ-RP-NFUNC-004
@tracks AC-RP-002-01, AC-RP-005-03, AC-RP-005-04, AC-RP-006-02, AC-RP-009-02

重点：_map_action 动作映射；configure_real_port 不调 save（AC-RP-005-03）；
collect_real_panel 单会话批量采集 + info 容错非阻塞。
全程 mock DeviceToolSession / session_guard，不依赖真实网络设备。
"""
from __future__ import annotations

import contextlib
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.tools.real_panel_service import (
    PortWriteResult,
    _map_action,
    configure_real_port,
    collect_real_panel,
)
from src.tools.real_panel_parsers import RealPanelError


def _make_device():
    return SimpleNamespace(id=7, device_name="core-sw-1")


@contextlib.contextmanager
def _null_guard(*args, **kwargs):
    yield


# ═══════════════════════════════════════════════════════════
# _map_action
# ═══════════════════════════════════════════════════════════

class TestMapAction:
    def test_shutdown(self):
        assert _map_action("shutdown") == "shutdown"

    def test_no_shutdown(self):
        assert _map_action("no-shutdown") == "no shutdown"

    def test_no_shutdown_underscore(self):
        assert _map_action("no_shutdown") == "no shutdown"

    def test_case_insensitive_and_strip(self):
        assert _map_action(" SHUTDOWN ") == "shutdown"
        assert _map_action("NO-SHUTDOWN") == "no shutdown"

    def test_invalid_action_raises_value_error(self):
        with pytest.raises(ValueError):
            _map_action("set-vlan")

    def test_none_action_raises_value_error(self):
        with pytest.raises(ValueError):
            _map_action(None)


# ═══════════════════════════════════════════════════════════
# configure_real_port
# ═══════════════════════════════════════════════════════════

class TestConfigureRealPort:
    def test_shutdown_success(self):
        mock_sess = MagicMock()
        mock_sess.configure.return_value = (2, 0, "ok")
        mock_sess.save = MagicMock(side_effect=AssertionError("save() must not be called"))

        mock_dts = MagicMock()
        mock_dts.return_value.__enter__.return_value = mock_sess

        with patch("src.tools.real_panel_service.DeviceToolSession", mock_dts), \
             patch("src.tools.real_panel_service.session_guard", _null_guard):
            result = configure_real_port(_make_device(), "admin", "secret", "Gi0/1", "shutdown")

        assert isinstance(result, PortWriteResult)
        assert result.success is True
        assert result.message == "端口配置成功"
        mock_sess.configure.assert_called_once_with(["interface Gi0/1", "shutdown"])
        mock_sess.save.assert_not_called()  # AC-RP-005-03：绝不持久化

    def test_no_shutdown_maps_command(self):
        mock_sess = MagicMock()
        mock_sess.configure.return_value = (2, 0, "ok")
        mock_dts = MagicMock()
        mock_dts.return_value.__enter__.return_value = mock_sess

        with patch("src.tools.real_panel_service.DeviceToolSession", mock_dts), \
             patch("src.tools.real_panel_service.session_guard", _null_guard):
            configure_real_port(_make_device(), "admin", "secret", "Gi0/1", "no-shutdown")

        mock_sess.configure.assert_called_once_with(["interface Gi0/1", "no shutdown"])

    def test_partial_failure_returns_false(self):
        mock_sess = MagicMock()
        mock_sess.configure.return_value = (1, 1, "err")
        mock_dts = MagicMock()
        mock_dts.return_value.__enter__.return_value = mock_sess

        with patch("src.tools.real_panel_service.DeviceToolSession", mock_dts), \
             patch("src.tools.real_panel_service.session_guard", _null_guard):
            result = configure_real_port(_make_device(), "admin", "secret", "Gi0/1", "shutdown")

        assert result.success is False
        assert "失败" in result.message

    def test_executed_less_than_commands_returns_false(self):
        mock_sess = MagicMock()
        mock_sess.configure.return_value = (1, 0, "ok")  # executed < len(commands)=2
        mock_dts = MagicMock()
        mock_dts.return_value.__enter__.return_value = mock_sess

        with patch("src.tools.real_panel_service.DeviceToolSession", mock_dts), \
             patch("src.tools.real_panel_service.session_guard", _null_guard):
            result = configure_real_port(_make_device(), "admin", "secret", "Gi0/1", "shutdown")

        assert result.success is False

    def test_invalid_action_propagates_value_error_before_session(self):
        mock_dts = MagicMock()
        with patch("src.tools.real_panel_service.DeviceToolSession", mock_dts), \
             patch("src.tools.real_panel_service.session_guard", _null_guard):
            with pytest.raises(ValueError):
                configure_real_port(_make_device(), "admin", "secret", "Gi0/1", "set-vlan")
        mock_dts.assert_not_called()  # 非法动作不建立会话

    def test_session_closed_via_context_manager(self):
        mock_sess = MagicMock()
        mock_sess.configure.return_value = (2, 0, "ok")
        mock_dts = MagicMock()
        mock_dts.return_value.__enter__.return_value = mock_sess

        with patch("src.tools.real_panel_service.DeviceToolSession", mock_dts), \
             patch("src.tools.real_panel_service.session_guard", _null_guard):
            configure_real_port(_make_device(), "admin", "secret", "Gi0/1", "shutdown")

        mock_dts.return_value.__exit__.assert_called_once()


# ═══════════════════════════════════════════════════════════
# collect_real_panel
# ═══════════════════════════════════════════════════════════

class TestCollectRealPanel:
    def _setup_session(self, show_map):
        mock_sess = MagicMock()
        mock_sess.show.side_effect = lambda cmd: show_map.get(
            cmd, f"! no data for {cmd}"
        )
        mock_dts = MagicMock()
        mock_dts.return_value.__enter__.return_value = mock_sess
        return mock_dts, mock_sess

    def test_success_assembles_snapshot(self):
        show_map = {
            "show interface status": (
                "Port Status Vlan Speed\nGi0/1 up 1 1000\nGi0/2 down 1 Auto"
            ),
            "show cpu-utilization": "5 seconds: 12%\n1 minute: 8%",
            "show memory-utilization": "Used: 1024 KB\nTotal: 2048 KB",
            "show system-info": "Device Name - SW-1\nModel - TL-SG5428\nSoftware Version - 2.0",
        }
        mock_dts, mock_sess = self._setup_session(show_map)

        with patch("src.tools.real_panel_service.DeviceToolSession", mock_dts), \
             patch("src.tools.real_panel_service.session_guard", _null_guard):
            snap = collect_real_panel(_make_device(), "admin", "secret")

        assert snap["device_id"] == 7
        assert len(snap["ports"]) == 2
        assert snap["ports"][0]["name"] == "Gi0/1"
        assert snap["cpu"]["cpu_5s"] == 12.0
        assert snap["memory"]["usage_pct"] == pytest.approx(50.0, abs=0.01)
        assert snap["io"]["supported"] is False
        assert "不支持" in snap["io"]["message"]
        assert snap["info"]["device_name"] == "SW-1"
        assert "collected_at" in snap

    def test_info_failure_non_blocking(self):
        def _show(cmd):
            if cmd == "show system-info":
                raise RealPanelError("info", "bad output")
            return {
                "show interface status": "Port Status Vlan Speed\nGi0/1 up 1 1000",
                "show cpu-utilization": "5 seconds: 5%",
                "show memory-utilization": "Used: 100 MB\nTotal: 200 MB",
            }[cmd]

        mock_sess = MagicMock()
        mock_sess.show.side_effect = _show
        mock_dts = MagicMock()
        mock_dts.return_value.__enter__.return_value = mock_sess

        with patch("src.tools.real_panel_service.DeviceToolSession", mock_dts), \
             patch("src.tools.real_panel_service.session_guard", _null_guard):
            snap = collect_real_panel(_make_device(), "admin", "secret")

        assert snap["info"] is None          # ADR-RP-004：info 失败不阻塞
        assert len(snap["ports"]) == 1
        assert snap["cpu"]["cpu_5s"] == 5.0

    def test_single_session_for_all_commands(self):
        show_map = {
            "show interface status": "Port Status Vlan Speed\nGi0/1 up 1 1000",
            "show cpu-utilization": "5 seconds: 5%",
            "show memory-utilization": "Used: 100 MB\nTotal: 200 MB",
        }
        mock_dts, _ = self._setup_session(show_map)

        with patch("src.tools.real_panel_service.DeviceToolSession", mock_dts), \
             patch("src.tools.real_panel_service.session_guard", _null_guard):
            collect_real_panel(_make_device(), "admin", "secret")

        # 单会话批量采集：DeviceToolSession 只建立一次
        assert mock_dts.call_count == 1

    def test_command_error_raises_real_panel_error(self):
        # _looks_like_error 命中时抛 RealPanelError（区块标识 ports）
        mock_sess = MagicMock()
        mock_sess.show.return_value = "Error: bad command"
        mock_dts = MagicMock()
        mock_dts.return_value.__enter__.return_value = mock_sess

        with patch("src.tools.real_panel_service.DeviceToolSession", mock_dts), \
             patch("src.tools.real_panel_service.session_guard", _null_guard):
            with pytest.raises(RealPanelError) as ei:
                collect_real_panel(_make_device(), "admin", "secret")
        assert ei.value.section == "ports"
