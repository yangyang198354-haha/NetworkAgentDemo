"""
Unit tests for MOD-INSP-002: systemctl_executor.
@author sub_agent_test_engineer
@module MOD-INSP-002
@covers REQ-INSP-004, REQ-INSP-006, REQ-INSP-007, REQ-INSP-NF-003, REQ-INSP-NF-006
@test_level UNIT
@mocking_strategy Mock subprocess.run and os.path.exists for Windows development.
"""
import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import pytest
import subprocess
from unittest.mock import patch, MagicMock, PropertyMock
from datetime import datetime, timezone

from src.systemd.systemctl_executor import (
    SystemctlExecutor,
    TimerStatus,
    ServiceStatus,
    SystemctlResult,
    SystemdAvailability,
    SystemctlPermissionError,
    SystemctlTimeoutError,
    SystemdNotAvailableError,
    SystemctlCommandError,
    TIMER_UNIT,
    SERVICE_UNIT,
)


# ── Fixtures ────────────────────────────────────────────────────

@pytest.fixture
def executor():
    """Create a SystemctlExecutor with default timeout."""
    return SystemctlExecutor(timeout=5)


@pytest.fixture
def mock_available():
    """Mock systemd as available (os.path.exists + shutil.which success)."""
    with patch("os.path.exists", return_value=True), \
         patch("shutil.which", return_value="/usr/bin/systemctl"):
        yield


@pytest.fixture
def mock_unavailable():
    """Mock systemd as unavailable."""
    with patch("os.path.exists", return_value=False), \
         patch("shutil.which", return_value=None):
        yield


# ════════════════════════════════════════════════════════════════
# TC-UNIT-001~003: check_systemd_available
# ════════════════════════════════════════════════════════════════

class TestCheckSystemdAvailable:

    def test_available_when_both_checks_pass(self, executor, mock_available):
        """TC-UNIT-001: check_systemd_available returns available=True."""
        result = executor.check_systemd_available()
        assert isinstance(result, SystemdAvailability)
        assert result.available is True
        assert result.reason is None

    def test_unavailable_when_run_dir_missing(self, executor):
        """TC-UNIT-002: check_systemd_available returns False when dir missing."""
        with patch("os.path.exists", return_value=False):
            result = executor.check_systemd_available()
        assert result.available is False
        assert "not found" in result.reason

    def test_unavailable_when_systemctl_not_in_path(self, executor):
        """TC-UNIT-003: check_systemd_available returns False when which fails."""
        with patch("os.path.exists", return_value=True), \
             patch("shutil.which", return_value=None):
            result = executor.check_systemd_available()
        assert result.available is False
        assert "not found in PATH" in result.reason


# ════════════════════════════════════════════════════════════════
# TC-UNIT-004~005: get_timer_status
# ════════════════════════════════════════════════════════════════

class TestGetTimerStatus:

    MOCK_TIMER_OUTPUT = (
        "ActiveState=active\n"
        "UnitFileState=enabled\n"
        "NextElapseUSRealtime=1754989200000000\n"
        "LastTriggerUSec=1754988600000000\n"
    )

    def test_active_enabled_timer(self, executor, mock_available):
        """TC-UNIT-004: get_timer_status returns active+enabled with timestamps."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout=self.MOCK_TIMER_OUTPUT, stderr=""
            )
            result = executor.get_timer_status()

        assert isinstance(result, TimerStatus)
        assert result.active_state == "active"
        assert result.unit_file_state == "enabled"
        assert result.next_trigger is not None
        assert result.last_trigger is not None

    def test_inactive_timer(self, executor, mock_available):
        """get_timer_status returns inactive state."""
        output = "ActiveState=inactive\nUnitFileState=disabled\nNextElapseUSRealtime=0\nLastTriggerUSec=0\n"
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=output, stderr="")
            result = executor.get_timer_status()

        assert result.active_state == "inactive"
        assert result.unit_file_state == "disabled"
        assert result.next_trigger is None  # 0 timestamp → None
        assert result.last_trigger is None

    def test_not_found_unit(self, executor, mock_available):
        """TC-UNIT-005: get_timer_status returns not-found when command fails."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1, stdout="", stderr="Unit not found"
            )
            result = executor.get_timer_status()

        assert result.active_state == "not-found"
        assert result.unit_file_state == "not-found"

    def test_systemd_unavailable_returns_not_found(self, executor, mock_unavailable):
        """TC-UNIT-018: get_timer_status returns not-found when systemd unavailable."""
        result = executor.get_timer_status()
        assert result.active_state == "not-found"
        assert result.unit_file_state == "not-found"

    def test_timeout_returns_not_found(self, executor, mock_available):
        """TC-UNIT-017: get_timer_status returns not-found on timeout.

        Note: get_timer_status() uses a broad except Exception that catches
        SystemctlTimeoutError and gracefully returns not-found status.
        This is by design — a timeout means the unit status is unknown.
        The timeout is still logged at ERROR level.
        """
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="systemctl show", timeout=5)
            result = executor.get_timer_status()
        # Graceful degradation: timeout → not-found
        assert result.active_state == "not-found"
        assert result.unit_file_state == "not-found"


# ════════════════════════════════════════════════════════════════
# TC-UNIT-006~007: get_service_status
# ════════════════════════════════════════════════════════════════

class TestGetServiceStatus:

    MOCK_SERVICE_OUTPUT = (
        "ActiveState=active\n"
        "SubState=running\n"
        "Result=success\n"
        "ExecMainExitTimestamp=0\n"
    )

    def test_running_service(self, executor, mock_available):
        """TC-UNIT-006: get_service_status returns active+running."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout=self.MOCK_SERVICE_OUTPUT, stderr=""
            )
            result = executor.get_service_status()

        assert isinstance(result, ServiceStatus)
        assert result.active_state == "active"
        assert result.sub_state == "running"
        assert result.last_result == "success"

    def test_dead_service(self, executor, mock_available):
        """get_service_status returns inactive+dead for completed oneshot."""
        output = "ActiveState=inactive\nSubState=dead\nResult=success\nExecMainExitTimestamp=1754988700000000\n"
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=output, stderr="")
            result = executor.get_service_status()

        assert result.active_state == "inactive"
        assert result.sub_state == "dead"

    def test_not_found_service(self, executor, mock_available):
        """TC-UNIT-007: get_service_status returns not-found when unit missing."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="not found")
            result = executor.get_service_status()

        assert result.active_state == "not-found"
        assert result.sub_state == "not-found"

    def test_systemd_unavailable_service(self, executor, mock_unavailable):
        """TC-UNIT-019: get_service_status returns not-found when systemd unavailable."""
        result = executor.get_service_status()
        assert result.active_state == "not-found"


# ════════════════════════════════════════════════════════════════
# TC-UNIT-008~010: start/stop/restart service
# ════════════════════════════════════════════════════════════════

class TestServiceLifecycle:

    def test_start_service_success(self, executor, mock_available):
        """TC-UNIT-008: start_service returns success."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            result = executor.start_service()

        assert isinstance(result, SystemctlResult)
        assert result.success is True
        assert result.action == "start"

    def test_stop_service_success(self, executor, mock_available):
        """TC-UNIT-009: stop_service returns success."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            result = executor.stop_service()

        assert result.success is True
        assert result.action == "stop"

    def test_restart_service_success(self, executor, mock_available):
        """TC-UNIT-010: restart_service returns success."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            result = executor.restart_service()

        assert result.success is True
        assert result.action == "restart"

    def test_start_service_permission_denied(self, executor, mock_available):
        """TC-UNIT-016: start_service raises SystemctlPermissionError."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1, stdout="", stderr="Interactive authentication required"
            )
            with pytest.raises(SystemctlPermissionError) as exc_info:
                executor.start_service()
            assert "权限不足" in str(exc_info.value)
            assert "sudoers" in str(exc_info.value)

    def test_start_service_generic_failure(self, executor, mock_available):
        """start_service returns failed result for non-permission errors."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1, stdout="", stderr="Unit not loaded"
            )
            result = executor.start_service()

        assert result.success is False
        assert "执行失败" in result.message

    def test_start_service_with_not_allowed_permission(self, executor, mock_available):
        """Permission error detected via 'not allowed' keyword."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1, stdout="", stderr="user is not allowed to execute"
            )
            with pytest.raises(SystemctlPermissionError):
                executor.start_service()

    def test_stop_service_permission_denied(self, executor, mock_available):
        """stop_service raises SystemctlPermissionError on permission error."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1, stdout="", stderr="Interactive authentication required"
            )
            with pytest.raises(SystemctlPermissionError):
                executor.stop_service()


# ════════════════════════════════════════════════════════════════
# TC-UNIT-011~014: enable_timer / disable_timer
# ════════════════════════════════════════════════════════════════

class TestEnableDisableTimer:

    def test_enable_timer_success(self, executor, mock_available):
        """TC-UNIT-011: enable_timer returns success for inactive timer."""
        with patch.object(executor, "get_timer_status") as mock_status:
            mock_status.return_value = TimerStatus(
                active_state="inactive", unit_file_state="disabled"
            )
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
                result = executor.enable_timer()

        assert result.success is True
        assert result.action == "enable"
        assert "已启用" in result.message

    def test_enable_timer_idempotent(self, executor, mock_available):
        """TC-UNIT-012: enable_timer idempotent when already enabled+active."""
        with patch.object(executor, "get_timer_status") as mock_status:
            mock_status.return_value = TimerStatus(
                active_state="active", unit_file_state="enabled"
            )
            result = executor.enable_timer()

        assert result.success is True
        assert "无需操作" in result.message

    def test_enable_timer_enable_fails(self, executor, mock_available):
        """enable_timer returns failure when enable command fails."""
        with patch.object(executor, "get_timer_status") as mock_status:
            mock_status.return_value = TimerStatus(
                active_state="inactive", unit_file_state="disabled"
            )
            with patch.object(executor, "_exec_systemctl") as mock_exec:
                mock_exec.return_value = SystemctlResult(
                    success=False, action="enable", message="enable failed"
                )
                result = executor.enable_timer()
        assert result.success is False

    def test_enable_timer_start_fails_after_enable(self, executor, mock_available):
        """enable_timer: enable succeeds but start fails."""
        with patch.object(executor, "get_timer_status") as mock_status:
            mock_status.return_value = TimerStatus(
                active_state="inactive", unit_file_state="disabled"
            )
            with patch.object(executor, "_exec_systemctl") as mock_exec:
                mock_exec.side_effect = [
                    SystemctlResult(success=True, action="stop", message="ok"),
                    SystemctlResult(success=True, action="reset-failed", message="ok"),
                    SystemctlResult(success=True, action="enable", message="ok"),
                    SystemctlResult(success=False, action="start", message="start failed"),
                ]
                result = executor.enable_timer()
        assert result.success is False
        assert "start 失败" in result.message

    def test_disable_timer_success(self, executor, mock_available):
        """TC-UNIT-013: disable_timer returns success for active timer."""
        with patch.object(executor, "get_timer_status") as mock_status:
            mock_status.return_value = TimerStatus(
                active_state="active", unit_file_state="enabled"
            )
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
                result = executor.disable_timer()

        assert result.success is True
        assert result.action == "disable"

    def test_disable_timer_idempotent(self, executor, mock_available):
        """TC-UNIT-014: disable_timer idempotent when already disabled+inactive."""
        with patch.object(executor, "get_timer_status") as mock_status:
            mock_status.return_value = TimerStatus(
                active_state="inactive", unit_file_state="disabled"
            )
            result = executor.disable_timer()

        assert result.success is True
        assert "已处于禁用状态" in result.message

    def test_disable_timer_stop_fails(self, executor, mock_available):
        """disable_timer: stop fails, should return failure immediately."""
        with patch.object(executor, "get_timer_status") as mock_status:
            mock_status.return_value = TimerStatus(
                active_state="active", unit_file_state="enabled"
            )
            with patch.object(executor, "_exec_systemctl") as mock_exec:
                mock_exec.return_value = SystemctlResult(
                    success=False, action="stop", message="stop failed"
                )
                result = executor.disable_timer()
        assert result.success is False


# ════════════════════════════════════════════════════════════════
# TC-UNIT-015: daemon_reload
# ════════════════════════════════════════════════════════════════

class TestDaemonReload:

    def test_daemon_reload_success(self, executor, mock_available):
        """TC-UNIT-015: daemon_reload returns success."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            result = executor.daemon_reload()

        assert result.success is True
        assert result.action == "daemon-reload"


# ════════════════════════════════════════════════════════════════
# TC-UNIT-020~021: Security and edge cases
# ════════════════════════════════════════════════════════════════

class TestSecurityAndEdgeCases:

    def test_subprocess_uses_shell_false(self, executor, mock_available):
        """TC-UNIT-020: _exec_systemctl uses shell=False for injection prevention."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            executor._exec_systemctl("start", SERVICE_UNIT)

        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["shell"] is False, "shell must be False for security"

    def test_exec_systemctl_unavailable(self, executor, mock_unavailable):
        """TC-UNIT-021: _exec_systemctl returns failure when systemd unavailable."""
        result = executor._exec_systemctl("start", SERVICE_UNIT)
        assert result.success is False
        assert "不可用" in result.message

    def test_exec_systemctl_timeout(self, executor, mock_available):
        """_exec_systemctl returns failure on timeout."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="systemctl", timeout=5)
            result = executor._exec_systemctl("start", SERVICE_UNIT)

        assert result.success is False
        assert "超时" in result.message

    def test_run_systemctl_show_unavailable(self, executor, mock_unavailable):
        """_run_systemctl_show raises SystemdNotAvailableError when unavailable."""
        with pytest.raises(SystemdNotAvailableError):
            executor._run_systemctl_show(TIMER_UNIT, ["ActiveState"])

    def test_run_systemctl_show_timeout(self, executor, mock_available):
        """_run_systemctl_show raises SystemctlTimeoutError on timeout."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="systemctl show", timeout=5)
            with pytest.raises(SystemctlTimeoutError):
                executor._run_systemctl_show(TIMER_UNIT, ["ActiveState"])

    def test_run_systemctl_show_nonzero_return(self, executor, mock_available):
        """_run_systemctl_show raises SystemctlCommandError on non-zero return."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1, stdout="", stderr="Unit not found"
            )
            with pytest.raises(SystemctlCommandError):
                executor._run_systemctl_show(TIMER_UNIT, ["ActiveState"])

    def test_parse_show_output(self, executor):
        """_parse_show_output correctly parses Key=Value format."""
        output = "ActiveState=active\nUnitFileState=enabled\n"
        result = executor._parse_show_output(output)
        assert result == {"ActiveState": "active", "UnitFileState": "enabled"}

    def test_parse_show_output_with_empty_lines(self, executor):
        """_parse_show_output handles empty and whitespace lines."""
        output = "Key1=val1\n\n  \nKey2=val2\n"
        result = executor._parse_show_output(output)
        assert result == {"Key1": "val1", "Key2": "val2"}

    def test_pydantic_models_default_values(self):
        """Verify Pydantic model default values."""
        ts = TimerStatus()
        assert ts.active_state == "not-found"
        assert ts.unit_file_state == "not-found"
        assert ts.next_trigger is None

        ss = ServiceStatus()
        assert ss.active_state == "not-found"
        assert ss.sub_state == "not-found"

    def test_systemd_availability_model(self):
        """SystemdAvailability model creation."""
        avail = SystemdAvailability(available=True)
        assert avail.available is True
        assert avail.reason is None

        avail2 = SystemdAvailability(available=False, reason="no systemd")
        assert avail2.available is False
        assert avail2.reason == "no systemd"
