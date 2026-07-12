"""
Unit tests for MOD-INSP-001: systemd_unit_manager.
@author sub_agent_test_engineer
@module MOD-INSP-001
@covers REQ-INSP-002, REQ-INSP-003, REQ-INSP-013, REQ-INSP-015, REQ-INSP-016
@test_level UNIT
@mocking_strategy Mock SystemctlExecutor and Path operations for cross-platform testing.
"""
import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import pytest
from unittest.mock import patch, MagicMock, PropertyMock

from src.systemd.systemd_unit_manager import (
    SystemdUnitManager,
    WriteResult,
    VerifyResult,
    SyncResult,
)
from src.systemd.systemctl_executor import (
    SystemctlExecutor,
    SystemctlResult,
    TimerStatus,
    ServiceStatus,
    SystemdAvailability,
)


# ── Fixtures ────────────────────────────────────────────────────

@pytest.fixture
def mock_executor():
    """Create a mock SystemctlExecutor."""
    executor = MagicMock(spec=SystemctlExecutor)
    executor.check_systemd_available.return_value = SystemdAvailability(available=True)
    executor.daemon_reload.return_value = SystemctlResult(
        success=True, action="daemon-reload", message="done"
    )
    executor.get_timer_status.return_value = TimerStatus(
        active_state="inactive", unit_file_state="disabled"
    )
    executor.restart_service.return_value = SystemctlResult(
        success=True, action="restart", message="done"
    )
    return executor


@pytest.fixture
def manager(mock_executor):
    """Create SystemdUnitManager with mock executor and real templates dir."""
    templates_dir = _project_root / "resources" / "templates" / "systemd"
    return SystemdUnitManager(
        systemctl_executor=mock_executor,
        templates_dir=templates_dir,
    )


# ════════════════════════════════════════════════════════════════
# TC-UNIT-030~033: generate_service_unit / generate_timer_unit
# ════════════════════════════════════════════════════════════════

class TestGenerateUnitFiles:

    def test_generate_service_unit_content(self, manager):
        """TC-UNIT-030: generate_service_unit produces valid systemd service file."""
        config = {
            "timeout_seconds": 30,
            "python_bin": "python3.11",
            "working_directory": "/opt/networkagent",
            "user": "networkagent",
        }
        content = manager.generate_service_unit(config)

        assert "[Unit]" in content
        assert "Type=oneshot" in content
        assert "ExecStart=python3.11 -m src.inspection_cli run" in content
        assert "TimeoutStopSec=30" in content
        assert "Restart=on-failure" in content
        assert "RestartSec=30" in content
        assert "WorkingDirectory=/opt/networkagent" in content
        assert "User=networkagent" in content
        assert "StandardOutput=journal" in content
        assert "StandardError=journal" in content

    def test_generate_timer_unit_content_10min(self, manager):
        """TC-UNIT-031: generate_timer_unit with interval_minutes=10 -> OnUnitActiveSec=600."""
        config = {"interval_minutes": 10}
        content = manager.generate_timer_unit(config)

        assert "[Unit]" in content
        assert "[Timer]" in content
        assert "OnUnitActiveSec=600" in content
        assert "Unit=networkagent-inspection.service" in content
        assert "Persistent=true" in content

    def test_generate_timer_unit_content_5min(self, manager):
        """TC-UNIT-032: generate_timer_unit with interval_minutes=5 -> OnUnitActiveSec=300."""
        config = {"interval_minutes": 5}
        content = manager.generate_timer_unit(config)
        assert "OnUnitActiveSec=300" in content

    def test_generate_service_unit_defaults(self, manager):
        """TC-UNIT-033: generate_service_unit uses defaults for empty config."""
        content = manager.generate_service_unit({})
        assert "TimeoutStopSec=30" in content
        assert "python3.11" in content

    def test_generate_service_unit_custom_timeout(self, manager):
        """generate_service_unit honors custom timeout_seconds."""
        config = {"timeout_seconds": 60}
        content = manager.generate_service_unit(config)
        assert "TimeoutStopSec=60" in content

    def test_generate_timer_unit_custom_accuracy(self, manager):
        """generate_timer_unit honors custom accuracy_sec."""
        config = {"interval_minutes": 10, "accuracy_sec": 2}
        content = manager.generate_timer_unit(config)
        assert "AccuracySec=2" in content

    def test_generate_service_unit_includes_environment(self, manager):
        """generate_service_unit includes NETWORKAGENT_HOME env var."""
        config = {"working_directory": "/opt/na"}
        content = manager.generate_service_unit(config)
        assert "NETWORKAGENT_HOME=/opt/na" in content

    def test_generate_timer_unit_includes_install_section(self, manager):
        """generate_timer_unit includes [Install] section."""
        config = {"interval_minutes": 10}
        content = manager.generate_timer_unit(config)
        assert "[Install]" in content
        assert "WantedBy=timers.target" in content


# ════════════════════════════════════════════════════════════════
# TC-UNIT-034~036: write_unit_files
# ════════════════════════════════════════════════════════════════

class TestWriteUnitFiles:

    SVC = "[Unit]\nDescription=Test\n"
    TMR = "[Unit]\nDescription=TestTimer\n"

    def test_dir_not_exists(self, manager):
        """TC-UNIT-034: write_unit_files fails when SYSTEMD_DIR does not exist."""
        with patch.object(Path, "exists", return_value=False):
            result = manager.write_unit_files(self.SVC, self.TMR)
        assert result.success is False
        assert "not found" in result.error

    def test_write_permission_error_on_service_write(self, manager, monkeypatch):
        """TC-UNIT-035: write_unit_files reports permission error on file write.

        We use monkeypatch to mock Path.write_text at the instance level
        by patching it on the Path class.
        """
        monkeypatch.setattr(Path, "exists", lambda self: "/etc/systemd/system" in str(self) or True)
        monkeypatch.setattr(Path, "write_text", lambda self, content, encoding=None: (_ for _ in ()).throw(PermissionError("Permission denied")))
        monkeypatch.setattr(Path, "read_text", lambda self, encoding=None: "")
        result = manager.write_unit_files(self.SVC, self.TMR)
        assert result.success is False
        assert "权限不足" in result.error or "Permission" in result.error

    def test_write_idempotent_skip(self, manager):
        """TC-UNIT-036: write_unit_files skips when content unchanged.

        Both service and timer files must have matching content for both to be skipped.
        """
        svc_full = self.SVC.strip()
        tmr_full = self.TMR.strip()
        with patch.object(Path, "exists", return_value=True):
            with patch.object(Path, "read_text") as mock_read:
                # Both files return content that matches what we're writing
                mock_read.side_effect = [svc_full, tmr_full]
                with patch.object(Path, "write_text") as mock_write:
                    result = manager.write_unit_files(svc_full, tmr_full)
        assert result.success is True
        assert len(result.files_written) == 0

    def test_write_creates_new_files(self, manager, monkeypatch):
        """write_unit_files writes when files are new.

        Monkeypatch Path methods: SYSTEMD_DIR exists, individual files don't,
        so the write path is triggered and both files get written.
        On Windows, path separators are backslashes, so we check with rsplit.
        """
        import os as _os
        monkeypatch.setattr(
            Path, "exists",
            lambda self: (
                str(self).replace("\\", "/").rstrip("/").endswith("systemd/system")
            )
        )
        mock_write = MagicMock()
        monkeypatch.setattr(Path, "write_text", mock_write)
        monkeypatch.setattr(Path, "read_text", lambda self, encoding=None: "")

        result = manager.write_unit_files(self.SVC, self.TMR)
        assert result.success is True
        # Both service and timer files should have been written
        assert len(result.files_written) == 2


# ════════════════════════════════════════════════════════════════
# TC-UNIT-037~038: is_config_changed
# ════════════════════════════════════════════════════════════════

class TestIsConfigChanged:

    def test_no_change(self, manager):
        """TC-UNIT-037: is_config_changed returns False when content matches."""
        new_config = {"interval_minutes": 10, "timeout_seconds": 30}
        existing_service = manager.generate_service_unit(new_config)
        existing_timer = manager.generate_timer_unit(new_config)

        with patch.object(Path, "exists", return_value=True):
            with patch.object(Path, "read_text") as mock_read:
                mock_read.side_effect = [existing_service, existing_timer]
                result = manager.is_config_changed(new_config)
        assert result is False

    def test_files_missing(self, manager):
        """TC-UNIT-038: is_config_changed returns True when files don't exist."""
        with patch.object(Path, "exists", return_value=False):
            result = manager.is_config_changed({"interval_minutes": 10})
        assert result is True

    def test_service_changed(self, manager):
        """is_config_changed returns True when service content differs."""
        new_config = {"interval_minutes": 10, "timeout_seconds": 60}
        old_config = {"interval_minutes": 10, "timeout_seconds": 30}
        existing_service = manager.generate_service_unit(old_config)
        existing_timer = manager.generate_timer_unit(old_config)

        with patch.object(Path, "exists", return_value=True):
            with patch.object(Path, "read_text") as mock_read:
                mock_read.side_effect = [existing_service, existing_timer]
                result = manager.is_config_changed(new_config)
        assert result is True

    def test_timer_changed(self, manager):
        """is_config_changed returns True when timer content differs."""
        new_config = {"interval_minutes": 5, "timeout_seconds": 30}
        old_config = {"interval_minutes": 10, "timeout_seconds": 30}
        existing_service = manager.generate_service_unit(old_config)
        existing_timer = manager.generate_timer_unit(old_config)

        with patch.object(Path, "exists", return_value=True):
            with patch.object(Path, "read_text") as mock_read:
                mock_read.side_effect = [existing_service, existing_timer]
                result = manager.is_config_changed(new_config)
        assert result is True


# ════════════════════════════════════════════════════════════════
# TC-UNIT-039~046: sync_config_to_systemd
# ════════════════════════════════════════════════════════════════

class TestSyncConfigToSystemd:

    def test_sync_success_complete_chain(self, manager, mock_executor):
        """TC-UNIT-039: sync_config_to_systemd full chain succeeds."""
        mock_executor.check_systemd_available.return_value = SystemdAvailability(available=True)
        mock_executor.daemon_reload.return_value = SystemctlResult(
            success=True, action="daemon-reload", message="ok"
        )
        mock_executor.get_timer_status.return_value = TimerStatus(
            active_state="active", unit_file_state="enabled"
        )
        mock_executor.restart_service.return_value = SystemctlResult(
            success=True, action="restart", message="ok"
        )

        with patch.object(manager, "is_config_changed", return_value=True):
            with patch.object(manager, "write_unit_files") as mock_write:
                mock_write.return_value = WriteResult(
                    success=True, files_written=["svc", "tmr"]
                )
                with patch.object(manager, "verify_unit_files") as mock_verify:
                    mock_verify.return_value = VerifyResult(success=True)
                    result = manager.sync_config_to_systemd(
                        {"interval_minutes": 10, "timeout_seconds": 30}
                    )

        assert result.success is True
        assert result.timer_was_active is True
        assert any("daemon-reload" in a for a in result.actions_performed)

    def test_sync_timer_inactive_no_restart(self, manager, mock_executor):
        """TC-UNIT-040: sync_config_to_systemd does not restart inactive timer."""
        mock_executor.get_timer_status.return_value = TimerStatus(
            active_state="inactive", unit_file_state="disabled"
        )

        with patch.object(manager, "is_config_changed", return_value=True):
            with patch.object(manager, "write_unit_files") as mock_write:
                mock_write.return_value = WriteResult(success=True, files_written=["tmr"])
                with patch.object(manager, "verify_unit_files") as mock_verify:
                    mock_verify.return_value = VerifyResult(success=True)
                    result = manager.sync_config_to_systemd({"interval_minutes": 5})

        assert result.success is True
        assert result.timer_was_active is False

    def test_sync_timer_active_restart(self, manager, mock_executor):
        """TC-UNIT-041: sync_config_to_systemd restarts when timer is active."""
        mock_executor.get_timer_status.return_value = TimerStatus(
            active_state="active", unit_file_state="enabled"
        )

        with patch.object(manager, "is_config_changed", return_value=True):
            with patch.object(manager, "write_unit_files") as mock_write:
                mock_write.return_value = WriteResult(success=True, files_written=["tmr"])
                with patch.object(manager, "verify_unit_files") as mock_verify:
                    mock_verify.return_value = VerifyResult(success=True)
                    result = manager.sync_config_to_systemd({"interval_minutes": 10})

        assert result.success is True
        assert result.timer_was_active is True

    def test_sync_idempotent_skip(self, manager, mock_executor):
        """TC-UNIT-042: sync_config_to_systemd skips when config unchanged."""
        with patch.object(manager, "is_config_changed", return_value=False):
            result = manager.sync_config_to_systemd({"interval_minutes": 10})

        assert result.success is True
        assert any("skipped" in str(a).lower() for a in result.actions_performed)

    def test_sync_systemd_unavailable(self, manager, mock_executor):
        """TC-UNIT-043: sync_config_to_systemd fails when systemd unavailable."""
        mock_executor.check_systemd_available.return_value = SystemdAvailability(
            available=False, reason="no systemd"
        )
        result = manager.sync_config_to_systemd({"interval_minutes": 10})

        assert result.success is False
        assert "不可用" in result.error

    def test_sync_template_render_failure(self, manager, mock_executor):
        """TC-UNIT-044: sync_config_to_systemd fails on template render error."""
        with patch.object(manager, "is_config_changed", return_value=True):
            with patch.object(manager, "generate_service_unit") as mock_gen:
                mock_gen.side_effect = ValueError("template missing")
                result = manager.sync_config_to_systemd({})

        assert result.success is False
        assert "渲染失败" in result.error

    def test_sync_write_failure(self, manager, mock_executor):
        """TC-UNIT-045: sync_config_to_systemd fails when write_unit_files fails."""
        with patch.object(manager, "is_config_changed", return_value=True):
            with patch.object(manager, "write_unit_files") as mock_write:
                mock_write.return_value = WriteResult(success=False, error="disk full")
                result = manager.sync_config_to_systemd(
                    {"interval_minutes": 10, "timeout_seconds": 30}
                )

        assert result.success is False
        assert "disk full" in result.error

    def test_sync_daemon_reload_failure(self, manager, mock_executor):
        """TC-UNIT-046: sync_config_to_systemd fails on daemon-reload failure."""
        mock_executor.daemon_reload.return_value = SystemctlResult(
            success=False, action="daemon-reload", message="reload failed"
        )

        with patch.object(manager, "is_config_changed", return_value=True):
            with patch.object(manager, "write_unit_files") as mock_write:
                mock_write.return_value = WriteResult(success=True, files_written=["tmr"])
                with patch.object(manager, "verify_unit_files") as mock_verify:
                    mock_verify.return_value = VerifyResult(success=True)
                    result = manager.sync_config_to_systemd(
                        {"interval_minutes": 10, "timeout_seconds": 30}
                    )

        assert result.success is False
        assert "daemon-reload 失败" in result.error


# ════════════════════════════════════════════════════════════════
# TC-UNIT-047~048: verify_unit_files
# ════════════════════════════════════════════════════════════════

class TestVerifyUnitFiles:

    def test_verify_skips_when_systemd_unavailable(self, manager, mock_executor):
        """TC-UNIT-047: verify_unit_files returns success when systemd unavailable."""
        mock_executor.check_systemd_available.return_value = SystemdAvailability(
            available=False
        )
        result = manager.verify_unit_files()
        assert result.success is True
        assert len(result.errors) == 0

    def test_verify_reports_missing_files(self, manager, mock_executor):
        """TC-UNIT-048: verify_unit_files reports missing files as errors."""
        mock_executor.check_systemd_available.return_value = SystemdAvailability(
            available=True
        )
        with patch.object(Path, "exists", return_value=False):
            result = manager.verify_unit_files()
        assert result.success is False
        assert len(result.errors) > 0
        assert any("not found" in e for e in result.errors)
