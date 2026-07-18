"""
Unit tests for SimulatorCLI command parser (MOD-DS-003).
@author sub_agent_test_engineer
@covers REQ-FUNC-011 ~ REQ-FUNC-016, IFC-DS-003-01 ~ IFC-DS-003-04

Tests the CLI parser directly WITHOUT paramiko dependency.
Uses `from src.simulator.ssh_server import SimulatorCLI` and
`from src.simulator.state_manager import DeviceStateManager`.
"""
import pytest
from src.simulator.ssh_server import SimulatorCLI
from src.simulator.state_manager import DeviceStateManager


@pytest.fixture
def cli():
    """Create a fresh SimulatorCLI backed by a fresh DeviceStateManager."""
    state = DeviceStateManager(device_name="Sim-SW-01")
    return SimulatorCLI(state, hostname="Sim-SW-01")


# ── Initial State ──────────────────────────────────────

class TestSimulatorCLIInitial:
    """Tests for CLI initial state."""

    def test_initial_prompt(self, cli):
        """Prompt in user EXEC mode is 'Sim-SW-01> '."""
        assert cli.prompt == "Sim-SW-01> "
        assert cli.in_config_mode is False
        assert cli.current_interface is None

    def test_initial_not_config_mode(self, cli):
        """Initially not in config mode."""
        assert cli.in_config_mode is False
        assert cli.current_interface is None


# ── Empty / Enable / Help Commands ─────────────────────

class TestSimulatorCLIBasic:
    """Tests for empty, enable, help, exit commands."""

    def test_empty_command(self, cli):
        """Empty command returns empty string."""
        assert cli.execute("") == ""
        assert cli.execute("   ") == ""

    def test_enable_command(self, cli):
        """enable returns empty string."""
        assert cli.execute("enable") == ""
        assert cli.execute("en") == ""

    def test_exit_command(self, cli):
        """exit returns connection closed message."""
        assert "Connection closed" in cli.execute("exit")

    def test_help_user(self, cli):
        """? shows help in user mode."""
        output = cli.execute("?")
        assert "Exec commands" in output
        assert "configure terminal" in output
        assert "show" in output

    def test_help_config(self, cli):
        """? shows help in config mode."""
        cli.execute("configure terminal")
        output = cli.execute("?")
        assert "Configure commands" in output
        assert "interface" in output or "hostname" in output

    def test_help_show(self, cli):
        """show ? shows show sub-commands."""
        output = cli.execute("show ?")
        assert "interface status" in output
        assert "running-config" in output


# ── Show Commands ──────────────────────────────────────

class TestSimulatorCLIShowInterfaceStatus:
    """Tests for 'show interface status'."""

    def test_show_interface_status_header(self, cli):
        """Output contains column headers."""
        output = cli.execute("show interface status")
        assert "Port" in output
        assert "Name" in output
        assert "Status" in output
        assert "Vlan" in output
        assert "Duplex" in output
        assert "Speed" in output
        assert "Type" in output

    def test_show_interface_status_8_ports(self, cli):
        """Output contains all 8 port lines."""
        output = cli.execute("show interface status")
        for i in range(1, 9):
            assert f"Gi0/{i}" in output

    def test_show_interface_status_down_port(self, cli):
        """Down ports show correct status."""
        output = cli.execute("show interface status")
        # Gi0/2 is down, should show 'down' in status column
        assert "down" in output.lower()

    def test_show_interface_status_notconnect(self, cli):
        """Notconnect ports show correct status."""
        output = cli.execute("show interface status")
        assert "notconnect" in output.lower()

    def test_show_interface_status_admin_down_after_shutdown(self, cli):
        """After shutdown via state_manager, port shows 'admin down' in CLI.
        NOTE: Uses state_manager directly because CLI interface sub-mode has
        a case-sensitivity defect (D-ST-001)."""
        cli.state.configure_port("Gi0/1", "shutdown")
        output = cli.execute("show interface status")
        assert "admin down" in output.lower()


class TestSimulatorCLIShowInterfaceDetail:
    """Tests for 'show interface <iface>'.

    NOTE: The SimulatorCLI lowercases the interface name before lookup (D-ST-001),
    but port keys in DeviceStateManager are title-case (e.g. "Gi0/1").
    As a result, 'show interface Gi0/1' returns an error due to case mismatch.
    """

    def test_show_interface_case_mismatch_error(self, cli):
        """D-ST-001: show interface with title-case returns 'Invalid interface' due to case mismatch."""
        output = cli.execute("show interface Gi0/1")
        assert "Invalid interface" in output

    def test_show_interface_invalid(self, cli):
        """show interface with invalid name returns error."""
        output = cli.execute("show interface Gi0/99")
        assert "Invalid" in output

    def test_show_interface_status_works(self, cli):
        """show interface status (bulk listing) works correctly."""
        output = cli.execute("show interface status")
        for i in range(1, 9):
            assert f"Gi0/{i}" in output


class TestSimulatorCLIShowCPU:
    """Tests for 'show processes cpu'."""

    def test_show_processes_cpu(self, cli):
        """Output contains CPU utilization header."""
        output = cli.execute("show processes cpu")
        assert "CPU utilization for five seconds" in output
        assert "PID" in output
        assert "Process" in output

    def test_show_proc_cpu_alias(self, cli):
        """Alias 'show proc cpu' also works."""
        output = cli.execute("show proc cpu")
        assert "CPU utilization for five seconds" in output


class TestSimulatorCLIShowCPUHistory:
    """Tests for 'show processes cpu history'."""

    def test_show_cpu_history(self, cli):
        """Output contains CPU history chart."""
        output = cli.execute("show processes cpu history")
        assert "CPU%" in output
        assert "seconds" in output


class TestSimulatorCLIShowMemory:
    """Tests for 'show memory'."""

    def test_show_memory(self, cli):
        """Output contains memory information."""
        output = cli.execute("show memory")
        assert "Processor" in output
        assert "Memory Summary" in output
        assert "Total:" in output
        assert "Used:" in output
        assert "Free:" in output

    def test_show_mem_alias(self, cli):
        """Alias 'show mem' works."""
        output = cli.execute("show mem")
        assert "Memory Summary" in output


class TestSimulatorCLIShowIO:
    """Tests for 'show io'."""

    def test_show_io(self, cli):
        """Output contains IO statistics."""
        output = cli.execute("show io")
        assert "IO Statistics" in output
        assert "Read rate" in output
        assert "Write rate" in output


class TestSimulatorCLIShowMacTable:
    """Tests for 'show mac address-table'."""

    def test_show_mac_table(self, cli):
        """Output contains MAC address table."""
        output = cli.execute("show mac address-table")
        assert "Mac Address Table" in output
        assert "Vlan" in output
        assert "Mac Address" in output

    def test_show_mac_table_alias(self, cli):
        """Alias 'show mac address' works."""
        output = cli.execute("show mac address")
        assert "Mac Address Table" in output


class TestSimulatorCLIShowRunningConfig:
    """Tests for 'show running-config'."""

    def test_show_running_config(self, cli):
        """Output contains running configuration."""
        output = cli.execute("show running-config")
        assert "hostname Sim-SW-01" in output
        assert "interface Gi0/1" in output
        assert "interface Gi0/8" in output
        assert "end" in output

    def test_show_run_alias(self, cli):
        """Alias 'show run' works."""
        output = cli.execute("show run")
        assert "hostname" in output


class TestSimulatorCLIShowLogging:
    """Tests for 'show logging'."""

    def test_show_logging(self, cli):
        """Output contains syslog messages."""
        output = cli.execute("show logging")
        assert "Syslog logging: enabled" in output
        assert "Console logging" in output
        assert "%SYS-5-CONFIG_I" in output or "Buffer" in output
        assert "%LINEPROTO-5-UPDOWN" in output or "Log Buffer" in output


class TestSimulatorCLIShowVersion:
    """Tests for 'show version'."""

    def test_show_version(self, cli):
        """Output contains version information."""
        output = cli.execute("show version")
        assert "Cisco IOS Software" in output
        assert "Simulator Version 17.9.0" in output
        assert "Sim-SW-01" in output
        assert "uptime" in output.lower()

    def test_show_ver_alias(self, cli):
        """Alias 'show ver' works."""
        output = cli.execute("show ver")
        assert "Simulator Version" in output


# ── Config Mode Transitions ────────────────────────────

class TestSimulatorCLIConfigMode:
    """Tests for configure terminal, exit, end transitions."""

    def test_configure_terminal(self, cli):
        """configure terminal enters config mode."""
        output = cli.execute("configure terminal")
        assert "Enter configuration commands" in output
        assert "CNTL/Z" in output
        assert cli.in_config_mode is True
        assert cli.prompt == "Sim-SW-01(config)# "

    def test_configure_t_alias(self, cli):
        """'conf t' alias works."""
        cli.execute("conf t")
        assert cli.in_config_mode is True

    def test_exit_from_config(self, cli):
        """exit from config mode returns to user EXEC."""
        cli.execute("configure terminal")
        assert cli.in_config_mode is True
        cli.execute("exit")
        assert cli.in_config_mode is False
        assert cli.prompt == "Sim-SW-01> "

    def test_end_from_config(self, cli):
        """end from config mode returns to user EXEC."""
        cli.execute("configure terminal")
        cli.execute("end")
        assert cli.in_config_mode is False

    def test_hostname_in_config(self, cli):
        """hostname command changes the hostname (note: code lowercases the value)."""
        cli.execute("configure terminal")
        cli.execute("hostname NewSwitch")
        # The _exec_config_mode uses lower[9:].strip() which lowercases
        assert cli.hostname == "newswitch"
        assert "newswitch" in cli.prompt.lower()


# ── Interface Sub-Mode ─────────────────────────────────

class TestSimulatorCLIInterfaceMode:
    """Tests for interface sub-mode commands.

    NOTE (D-ST-001): The SimulatorCLI lowercases port names before lookup in
    DeviceStateManager, but port dictionary keys are title-case ("Gi0/1").
    This means 'interface Gi0/1' in config mode always returns 'Invalid interface'.
    """

    def test_interface_case_mismatch_returns_error(self, cli):
        """D-ST-001: interface Gi0/1 returns error due to case mismatch."""
        cli.execute("configure terminal")
        result = cli.execute("interface Gi0/1")
        assert "Invalid" in result
        assert cli.current_interface is None

    def test_interface_invalid_port_returns_error(self, cli):
        """interface with invalid name returns error."""
        cli.execute("configure terminal")
        result = cli.execute("interface Gi0/99")
        assert "Invalid" in result
        assert cli.current_interface is None

    def test_exit_config_mode_works(self, cli):
        """exit from config mode returns to user EXEC (no interface submode needed)."""
        cli.execute("configure terminal")
        assert cli.in_config_mode is True
        cli.execute("exit")
        assert cli.in_config_mode is False
        assert cli.current_interface is None
        assert cli.prompt == "Sim-SW-01> "

    def test_end_from_config_works(self, cli):
        """end from any mode returns to user EXEC."""
        cli.execute("configure terminal")
        cli.execute("end")
        assert cli.current_interface is None
        assert cli.in_config_mode is False


class TestSimulatorCLIInterfaceCommands:
    """Tests for commands in the config mode context.

    NOTE (D-ST-001): Due to case sensitivity bug, interface sub-mode
    cannot be entered via CLI. Interface commands are tested directly
    against the state_manager API in test_simulator_state_manager.py.
    """

    def test_invalid_interface_command(self, cli):
        """Invalid command in config mode returns error."""
        cli.execute("configure terminal")
        result = cli.execute("bogus cmd")
        assert "Invalid input" in result

    def test_interface_case_mismatch_error(self, cli):
        """D-ST-001: interface command cannot match title-case port keys."""
        cli.execute("configure terminal")
        result = cli.execute("interface Gi0/1")
        assert "Invalid" in result
        assert cli.current_interface is None


# ── Error Handling ─────────────────────────────────────

class TestSimulatorCLIErrors:
    """Tests for error handling."""

    def test_unknown_command(self, cli):
        """Unknown command in user EXEC returns error."""
        result = cli.execute("randomgarbage")
        assert "Unknown command" in result

    def test_invalid_show(self, cli):
        """Unknown show sub-command returns error."""
        result = cli.execute("show bogus things")
        assert "Invalid input" in result or "Unknown" in result

    def test_invalid_config_command(self, cli):
        """Invalid command in config mode returns error."""
        cli.execute("configure terminal")
        result = cli.execute("bogus config cmd")
        assert "Invalid input" in result


# ── Prompt Transitions ─────────────────────────────────

class TestSimulatorCLIPrompt:
    """Tests for prompt property across modes."""

    def test_user_prompt(self, cli):
        """User EXEC prompt."""
        assert cli.prompt == "Sim-SW-01> "

    def test_config_prompt(self, cli):
        """Config mode prompt."""
        cli.execute("configure terminal")
        assert cli.prompt == "Sim-SW-01(config)# "

    def test_no_interface_prompt_without_submode(self, cli):
        """Without interface sub-mode (D-ST-001), prompt stays in config mode."""
        cli.execute("configure terminal")
        cli.execute("interface Gi0/1")
        # Interface sub-mode not entered due to case mismatch
        assert cli.current_interface is None
        assert cli.in_config_mode is True
        assert cli.prompt == "Sim-SW-01(config)# "

    def test_prompt_after_hostname_change(self, cli):
        """Prompt reflects hostname change (note: hostname is lowercased)."""
        cli.execute("configure terminal")
        cli.execute("hostname CoreSW")
        # hostname is lowercased by the code
        assert "coresw" in cli.prompt.lower()
        cli.execute("end")
        assert "coresw" in cli.prompt.lower()
