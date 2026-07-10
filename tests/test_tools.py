"""
Unit tests for MOD-010 SwitchConfigTool, MOD-011 SwitchDiagTool, MOD-012 BackupTool.
@author sub_agent_test_engineer
@covers REQ-FUNC-017, REQ-FUNC-018, REQ-FUNC-020
"""
import pytest
from src.models.alert import DeviceAuth
from src.models.fix_plan import ConfigResult, DiagResult, BackupResult, RollbackResult
from src.tools.switch_config_tool import (
    AbstractSwitchConfigTool, MockSwitchConfigTool, TpLinkSwitchConfigTool,
    create_switch_config_tool,
)
from src.tools.switch_diag_tool import (
    AbstractSwitchDiagTool, MockSwitchDiagTool, TpLinkSwitchDiagTool,
    create_switch_diag_tool,
)
from src.tools.backup_tool import (
    AbstractBackupTool, MockBackupTool, TpLinkBackupTool,
    create_backup_tool,
)


# ═══════════════════════════════════════════════════════
# MOD-010: SwitchConfigTool
# ═══════════════════════════════════════════════════════

class TestSwitchConfigTool:
    """MOD-010 SwitchConfigTool unit tests."""

    def setup_method(self):
        self.tool = MockSwitchConfigTool()
        self.auth = DeviceAuth(username="admin", password="test123")

    def test_configure_single_command(self):
        """Single command should return success."""
        result = self.tool._run("192.168.1.1", ["show version"], self.auth)
        assert isinstance(result, ConfigResult)
        assert result.success is True
        assert result.commands_executed == 1
        assert result.commands_failed == 0

    def test_configure_multiple_commands(self):
        """Multiple commands should all succeed."""
        commands = [
            "interface Gi0/1",
            "no shutdown",
            "description Auto-recovered",
        ]
        result = self.tool._run("192.168.1.1", commands, self.auth)
        assert result.success is True
        assert result.commands_executed == 3

    def test_configure_empty_commands(self):
        """Empty command list should succeed with zero executed."""
        result = self.tool._run("192.168.1.1", [], self.auth)
        assert result.success is True
        assert result.commands_executed == 0

    def test_interface_command_output(self):
        """Interface commands should get specialized mock output."""
        result = self.tool._run("192.168.1.1", ["interface Gi0/1"], self.auth)
        assert "Entering interface configuration mode" in result.output

    def test_no_shutdown_command_output(self):
        """no shutdown command should get specialized output."""
        result = self.tool._run("192.168.1.1", ["no shutdown"], self.auth)
        assert "Interface enabled" in result.output

    def test_shutdown_command_output(self):
        """shutdown command should get specialized output."""
        result = self.tool._run("192.168.1.1", ["shutdown"], self.auth)
        assert "Interface disabled" in result.output

    def test_factory_creates_mock(self):
        """Factory should return Mock implementation."""
        tool = create_switch_config_tool(use_mock=True)
        assert isinstance(tool, MockSwitchConfigTool)

    def test_factory_creates_tplink(self):
        """Factory should return TpLink implementation when use_mock=False."""
        tool = create_switch_config_tool(use_mock=False)
        assert isinstance(tool, TpLinkSwitchConfigTool)

    def test_tplink_raises_not_implemented(self):
        """TpLink implementation should raise NotImplementedError."""
        tool = TpLinkSwitchConfigTool()
        with pytest.raises(NotImplementedError):
            tool._run("192.168.1.1", ["show version"], self.auth)

    def test_abstract_class_exists(self):
        """Abstract base class should be importable."""
        assert AbstractSwitchConfigTool is not None


# ═══════════════════════════════════════════════════════
# MOD-011: SwitchDiagTool
# ═══════════════════════════════════════════════════════

class TestSwitchDiagTool:
    """MOD-011 SwitchDiagTool unit tests."""

    def setup_method(self):
        self.tool = MockSwitchDiagTool()
        self.auth = DeviceAuth(username="admin", password="test123")

    def test_diagnose_mac_table(self):
        """show mac address-table should return MAC table with flapping info."""
        result = self.tool._run("192.168.1.1", "show mac address-table", self.auth)
        assert isinstance(result, DiagResult)
        assert result.success is True
        assert "00:1A:2B:3C:4D:5E" in result.output
        assert "WARNING" in result.output or "flapping" in result.output.lower()

    def test_diagnose_interface_detail(self):
        """show interface Gi0/1 should return detailed interface status."""
        result = self.tool._run("192.168.1.1", "show interface Gi0/1", self.auth)
        assert result.success is True
        assert "gigabitethernet0/1" in result.output.lower() or "gi0/1" in result.output.lower()
        assert "down" in result.output.lower()

    def test_diagnose_interface_status(self):
        """show interface status should return all interface statuses."""
        result = self.tool._run("192.168.1.1", "show interface status", self.auth)
        assert result.success is True
        assert "Gi0/1" in result.output
        assert "Gi0/2" in result.output

    def test_diagnose_cpu_processes(self):
        """show processes cpu should return CPU utilization data."""
        result = self.tool._run("192.168.1.1", "show processes cpu", self.auth)
        assert result.success is True
        assert "CPU utilization" in result.output
        assert "IP Input" in result.output
        assert "45.23%" in result.output or "92%" in result.output

    def test_diagnose_cpu_history(self):
        """show processes cpu history should return historical data."""
        result = self.tool._run("192.168.1.1", "show processes cpu history", self.auth)
        assert result.success is True
        assert "CPU%" in result.output or "cpu" in result.output.lower()

    def test_diagnose_logging(self):
        """show logging should return syslog messages."""
        result = self.tool._run("192.168.1.1", "show logging", self.auth)
        assert result.success is True
        assert "MACFLAP" in result.output or "Syslog" in result.output

    def test_diagnose_unknown_command(self):
        """Unknown command should still succeed with generic output."""
        result = self.tool._run("192.168.1.1", "show unknown-cmd", self.auth)
        assert result.success is True
        assert "Mock output" in result.output or "OK" in result.output

    def test_diagnose_execution_time(self):
        """Result should include execution time metric."""
        result = self.tool._run("192.168.1.1", "show version", self.auth)
        assert result.execution_time_ms >= 0

    def test_factory_creates_mock(self):
        """Factory should return Mock implementation."""
        tool = create_switch_diag_tool(use_mock=True)
        assert isinstance(tool, MockSwitchDiagTool)

    def test_factory_creates_tplink(self):
        """Factory should return TpLink implementation when use_mock=False."""
        tool = create_switch_diag_tool(use_mock=False)
        assert isinstance(tool, TpLinkSwitchDiagTool)

    def test_tplink_raises_not_implemented(self):
        """TpLink implementation should raise NotImplementedError."""
        tool = TpLinkSwitchDiagTool()
        with pytest.raises(NotImplementedError):
            tool._run("192.168.1.1", "show version", self.auth)


# ═══════════════════════════════════════════════════════
# MOD-012: BackupTool
# ═══════════════════════════════════════════════════════

class TestBackupTool:
    """MOD-012 BackupTool unit tests."""

    def setup_method(self):
        self.tool = MockBackupTool()
        self.auth = DeviceAuth(username="admin", password="test123")

    def test_backup_success(self):
        """Backup should succeed and return a running-config."""
        result = self.tool._run("192.168.1.1", self.auth, operation="backup")
        assert isinstance(result, BackupResult)
        assert result.success is True
        assert result.config is not None
        assert len(result.config) > 0
        assert "mock tp-link" in result.config.lower() or "192.168.1.1" in result.config

    def test_backup_generates_unique_id(self):
        """Each backup should generate a unique backup_id."""
        result1 = self.tool._run("192.168.1.1", self.auth, operation="backup")
        result2 = self.tool._run("192.168.1.1", self.auth, operation="backup")
        assert isinstance(result1, BackupResult)
        assert isinstance(result2, BackupResult)
        assert result1.backup_id != result2.backup_id

    def test_rollback_success_with_valid_id(self):
        """Rollback with a valid backup_id should succeed."""
        backup = self.tool._run("192.168.1.1", self.auth, operation="backup")
        assert isinstance(backup, BackupResult)
        result = self.tool._run("192.168.1.1", self.auth, operation="rollback", backup_id=backup.backup_id)
        assert isinstance(result, RollbackResult)
        assert result.success is True

    def test_rollback_fails_without_backup_id(self):
        """Rollback without backup_id should fail."""
        result = self.tool._run("192.168.1.1", self.auth, operation="rollback", backup_id=None)
        assert isinstance(result, RollbackResult)
        assert result.success is False
        assert "backup_id is required" in (result.error or "")

    def test_rollback_fails_with_unknown_id(self):
        """Rollback with an unknown backup_id should fail."""
        result = self.tool._run("192.168.1.1", self.auth, operation="rollback", backup_id="nonexistent-id")
        assert isinstance(result, RollbackResult)
        assert result.success is False
        assert "not found" in (result.error or "").lower()

    def test_factory_creates_mock(self):
        """Factory should return Mock implementation."""
        tool = create_backup_tool(use_mock=True)
        assert isinstance(tool, MockBackupTool)

    def test_factory_creates_tplink(self):
        """Factory should return TpLink implementation when use_mock=False."""
        tool = create_backup_tool(use_mock=False)
        assert isinstance(tool, TpLinkBackupTool)

    def test_tplink_raises_not_implemented(self):
        """TpLink implementation should raise NotImplementedError."""
        tool = TpLinkBackupTool()
        with pytest.raises(NotImplementedError):
            tool._run("192.168.1.1", self.auth, operation="backup")
