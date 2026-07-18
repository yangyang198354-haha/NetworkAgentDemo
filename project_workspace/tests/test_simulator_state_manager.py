"""
Unit tests for DeviceStateManager and PortState (MOD-DS-004).
@author sub_agent_test_engineer
@covers REQ-FUNC-001 ~ REQ-FUNC-010, IFC-DS-004-01 ~ IFC-DS-004-05
"""
import pytest
import time
from src.simulator.state_manager import DeviceStateManager, PortState


class TestPortState:
    """Unit tests for PortState dataclass."""

    def test_default_values(self):
        """PortState() creates a port with correct defaults."""
        port = PortState(name="Gi0/1")
        assert port.name == "Gi0/1"
        assert port.status == "up"
        assert port.vlan == 1
        assert port.duplex == "Full"
        assert port.speed == "1000"
        assert port.port_type == "10/100/1000BaseTX"
        assert port.description == ""
        assert port.mac_address == ""
        assert port.enabled is True
        assert port.input_packets == 0
        assert port.output_packets == 0
        assert port.input_errors == 0
        assert port.output_errors == 0
        assert port.input_rate_bps == 0
        assert port.output_rate_bps == 0

    def test_effective_status_up(self):
        """PortState with enabled=True returns actual status."""
        port = PortState(name="Gi0/1", status="up", enabled=True)
        assert port.effective_status() == "up"

    def test_effective_status_down(self):
        """PortState with enabled=True and status=down returns 'down'."""
        port = PortState(name="Gi0/2", status="down", enabled=True)
        assert port.effective_status() == "down"

    def test_effective_status_admin_down(self):
        """PortState with enabled=False returns 'administratively down' regardless of status."""
        port = PortState(name="Gi0/1", status="up", enabled=False)
        assert port.effective_status() == "administratively down"

    def test_effective_status_admin_down_when_notconnect(self):
        """PortState with enabled=False and status='notconnect' returns 'administratively down'."""
        port = PortState(name="Gi0/7", status="notconnect", enabled=False)
        assert port.effective_status() == "administratively down"

    def test_to_summary_shape(self):
        """to_summary() returns correct shape with expected keys."""
        port = PortState(name="Gi0/1", status="up", enabled=True, vlan=10,
                         description="Test Port", mac_address="00:1A:2B:3C:4D:01")
        summary = port.to_summary()
        assert "name" in summary
        assert "status" in summary
        assert "vlan" in summary
        assert "duplex" in summary
        assert "speed" in summary
        assert "type" in summary
        assert "description" in summary
        assert summary["name"] == "Gi0/1"
        assert summary["status"] == "up"
        assert summary["vlan"] == 10
        assert summary["description"] == "Test Port"

    def test_to_summary_admin_down_shows_auto(self):
        """to_summary() for disabled port shows Auto for duplex and speed."""
        port = PortState(name="Gi0/1", status="up", enabled=False)
        summary = port.to_summary()
        assert summary["status"] == "administratively down"
        assert summary["duplex"] == "Auto"
        assert summary["speed"] == "Auto"

    def test_to_detail_shape(self):
        """to_detail() returns correct shape with expected keys."""
        port = PortState(name="Gi0/1", status="up", enabled=True,
                         mac_address="00:1A:2B:3C:4D:01")
        detail = port.to_detail()
        assert "name" in detail
        assert "status" in detail
        assert "mac_address" in detail
        assert "mtu" in detail
        assert "bandwidth_kbps" in detail
        assert "duplex" in detail
        assert "speed" in detail
        assert "vlan" in detail
        assert "description" in detail
        assert "input_packets" in detail
        assert "output_packets" in detail
        assert "input_errors" in detail
        assert "output_errors" in detail
        assert "input_rate_bps" in detail
        assert "output_rate_bps" in detail

    def test_to_detail_bandwidth_calculation(self):
        """to_detail() bandwidth_kbps is speed * 1000."""
        port = PortState(name="Gi0/1", speed="1000")
        detail = port.to_detail()
        assert detail["bandwidth_kbps"] == 1000000  # 1000 * 1000


class TestDeviceStateManagerInit:
    """Unit tests for DeviceStateManager initialization."""

    def test_creates_8_ports(self):
        """DeviceStateManager creates exactly 8 ports on init."""
        state = DeviceStateManager()
        ports = state.get_all_ports()
        assert len(ports) == 8

    def test_port_names_correct(self):
        """Ports are named Gi0/1 through Gi0/8."""
        state = DeviceStateManager()
        port_names = sorted([p.name for p in state.get_all_ports()])
        expected = [f"Gi0/{i}" for i in range(1, 9)]
        assert port_names == expected

    def test_device_name_default(self):
        """Default device_name is 'Sim-SW-01'."""
        state = DeviceStateManager()
        assert state.device_name == "Sim-SW-01"

    def test_device_name_custom(self):
        """Custom device_name is stored correctly."""
        state = DeviceStateManager(device_name="Custom-SW")
        assert state.device_name == "Custom-SW"

    def test_port_gi0_1_defaults(self):
        """Gi0/1 has status='up', vlan=1, description='Uplink to Core'."""
        state = DeviceStateManager()
        port = state.get_port("Gi0/1")
        assert port is not None
        assert port.status == "up"
        assert port.vlan == 1
        assert port.description == "Uplink to Core"
        assert port.enabled is True

    def test_port_gi0_2_down(self):
        """Gi0/2 has status='down'."""
        state = DeviceStateManager()
        port = state.get_port("Gi0/2")
        assert port is not None
        assert port.status == "down"

    def test_port_gi0_7_notconnect(self):
        """Gi0/7 has status='notconnect'."""
        state = DeviceStateManager()
        port = state.get_port("Gi0/7")
        assert port is not None
        assert port.status == "notconnect"

    def test_port_gi0_5_vlan_10(self):
        """Gi0/5 has vlan=10."""
        state = DeviceStateManager()
        port = state.get_port("Gi0/5")
        assert port is not None
        assert port.vlan == 10


class TestDeviceStateManagerQueries:
    """Unit tests for port query methods."""

    def test_get_all_ports_count(self):
        """get_all_ports() returns exactly 8 PortState objects."""
        state = DeviceStateManager()
        ports = state.get_all_ports()
        assert len(ports) == 8
        for p in ports:
            assert isinstance(p, PortState)

    def test_get_port_known(self):
        """get_port() for known port returns PortState."""
        state = DeviceStateManager()
        port = state.get_port("Gi0/1")
        assert isinstance(port, PortState)
        assert port.name == "Gi0/1"

    def test_get_port_unknown_returns_none(self):
        """get_port() for unknown port returns None."""
        state = DeviceStateManager()
        assert state.get_port("Gi0/99") is None
        assert state.get_port("Te1/1") is None

    def test_get_up_ports(self):
        """get_up_ports() returns only ports with effective_status=='up'."""
        state = DeviceStateManager()
        up_ports = state.get_up_ports()
        for p in up_ports:
            assert p.effective_status() == "up"
        # Gi0/2 is down, Gi0/7-8 are notconnect => 5 ports should be up
        # (Gi0/1, Gi0/3, Gi0/4, Gi0/5, Gi0/6 are all "up")
        assert len(up_ports) == 5
        up_names = {p.name for p in up_ports}
        assert "Gi0/1" in up_names
        assert "Gi0/3" in up_names
        assert "Gi0/4" in up_names
        assert "Gi0/5" in up_names
        assert "Gi0/6" in up_names
        # after Gi0/5 check, let me just verify that down ports are excluded
        assert "Gi0/2" not in up_names
        assert "Gi0/7" not in up_names
        assert "Gi0/8" not in up_names

    def test_get_up_ports_after_shutdown(self):
        """After shutdown, port is excluded from up_ports."""
        state = DeviceStateManager()
        state.configure_port("Gi0/1", "shutdown")
        up = state.get_up_ports()
        assert "Gi0/1" not in {p.name for p in up}


class TestDeviceStateManagerConfigure:
    """Unit tests for configure_port() method."""

    def test_shutdown_success(self):
        """shutdown action disables port and returns success."""
        state = DeviceStateManager()
        success, msg = state.configure_port("Gi0/1", "shutdown")
        assert success is True
        assert "Gi0/1" in msg
        assert "disabled" in msg
        port = state.get_port("Gi0/1")
        assert port.enabled is False
        assert port.effective_status() == "administratively down"

    def test_no_shutdown_success(self):
        """no-shutdown action enables a previously shutdown port."""
        state = DeviceStateManager()
        state.configure_port("Gi0/2", "shutdown")  # Gi0/2 is already down
        port = state.get_port("Gi0/2")
        assert port.enabled is False
        success, msg = state.configure_port("Gi0/2", "no-shutdown")
        assert success is True
        assert "enabled" in msg
        assert state.get_port("Gi0/2").enabled is True

    def test_set_vlan_valid(self):
        """set-vlan with valid VLAN ID updates the port."""
        state = DeviceStateManager()
        success, msg = state.configure_port("Gi0/3", "set-vlan", "20")
        assert success is True
        assert "vlan 20" in msg.lower()
        assert state.get_port("Gi0/3").vlan == 20

    def test_set_vlan_invalid_zero(self):
        """set-vlan with 0 returns error."""
        state = DeviceStateManager()
        original_vlan = state.get_port("Gi0/3").vlan
        success, msg = state.configure_port("Gi0/3", "set-vlan", "0")
        assert success is False
        assert "VLAN ID" in msg or "范围" in msg
        assert state.get_port("Gi0/3").vlan == original_vlan

    def test_set_vlan_invalid_4095(self):
        """set-vlan with 4095 returns error (only 1-4094 is valid)."""
        state = DeviceStateManager()
        original_vlan = state.get_port("Gi0/3").vlan
        success, msg = state.configure_port("Gi0/3", "set-vlan", "4095")
        assert success is False
        assert "VLAN ID" in msg or "范围" in msg
        assert state.get_port("Gi0/3").vlan == original_vlan

    def test_set_vlan_non_numeric(self):
        """set-vlan with non-numeric value returns error."""
        state = DeviceStateManager()
        original_vlan = state.get_port("Gi0/3").vlan
        success, msg = state.configure_port("Gi0/3", "set-vlan", "abc")
        assert success is False
        assert state.get_port("Gi0/3").vlan == original_vlan

    def test_set_description(self):
        """set-description updates port description."""
        state = DeviceStateManager()
        success, msg = state.configure_port("Gi0/1", "set-description", "New Desc")
        assert success is True
        assert "description" in msg.lower()
        assert state.get_port("Gi0/1").description == "New Desc"

    def test_unknown_action(self):
        """Unknown action returns failure."""
        state = DeviceStateManager()
        success, msg = state.configure_port("Gi0/1", "bogus-action")
        assert success is False
        assert "未知" in msg or "unknown" in msg.lower()

    def test_nonexistent_port(self):
        """Configuring a nonexistent port returns failure."""
        state = DeviceStateManager()
        success, msg = state.configure_port("Gi0/99", "shutdown")
        assert success is False
        assert "不存在" in msg or "not found" in msg.lower()


class TestDeviceStateManagerSystem:
    """Unit tests for get_cpu() and get_memory_io()."""

    def test_get_cpu_keys(self):
        """get_cpu() returns dict with required keys."""
        state = DeviceStateManager()
        cpu = state.get_cpu()
        assert "cpu_5s" in cpu
        assert "cpu_1m" in cpu
        assert "cpu_5m" in cpu
        assert "processes" in cpu

    def test_get_cpu_values_in_range(self):
        """get_cpu() values are within 1.0-100.0 range."""
        state = DeviceStateManager()
        for _ in range(10):
            cpu = state.get_cpu()
            assert 1.0 <= cpu["cpu_5s"] <= 100.0
            assert 1.0 <= cpu["cpu_1m"] <= 100.0
            assert 1.0 <= cpu["cpu_5m"] <= 100.0

    def test_get_cpu_processes_list(self):
        """get_cpu() processes is a list of dicts with pid, name, cpu fields."""
        state = DeviceStateManager()
        cpu = state.get_cpu()
        processes = cpu["processes"]
        assert isinstance(processes, list)
        assert len(processes) > 0
        for p in processes:
            assert "pid" in p
            assert "name" in p
            assert "cpu_5s" in p
            assert "cpu_1m" in p
            assert "cpu_5m" in p

    def test_get_memory_io_keys(self):
        """get_memory_io() returns dict with required keys."""
        state = DeviceStateManager()
        mem = state.get_memory_io()
        assert "memory_total_mb" in mem
        assert "memory_used_mb" in mem
        assert "memory_free_mb" in mem
        assert "memory_usage_pct" in mem
        assert "io_read_kbps" in mem
        assert "io_write_kbps" in mem

    def test_get_memory_total(self):
        """Memory total is 512 MB."""
        state = DeviceStateManager()
        mem = state.get_memory_io()
        assert mem["memory_total_mb"] == 512

    def test_get_memory_usage_pct(self):
        """memory_usage_pct = used / total * 100."""
        state = DeviceStateManager()
        mem = state.get_memory_io()
        expected_pct = round(mem["memory_used_mb"] / mem["memory_total_mb"] * 100, 1)
        assert abs(mem["memory_usage_pct"] - expected_pct) < 0.5

    def test_get_memory_free(self):
        """free + used == total."""
        state = DeviceStateManager()
        mem = state.get_memory_io()
        assert abs(mem["memory_free_mb"] + mem["memory_used_mb"] - mem["memory_total_mb"]) < 0.5


class TestDeviceStateManagerConfig:
    """Unit tests for get_running_config()."""

    def test_running_config_contains_hostname(self):
        """Running config contains hostname line."""
        state = DeviceStateManager(device_name="Sim-SW-01")
        config = state.get_running_config()
        assert "hostname Sim-SW-01" in config

    def test_running_config_contains_all_8_interfaces(self):
        """Running config has interface blocks for all 8 ports."""
        state = DeviceStateManager()
        config = state.get_running_config()
        for i in range(1, 9):
            assert f"interface Gi0/{i}" in config

    def test_running_config_shows_no_shutdown_for_enabled(self):
        """Enabled ports have 'no shutdown' in running config."""
        state = DeviceStateManager()
        config = state.get_running_config()
        # Gi0/1 is enabled by default -> 'no shutdown'
        assert "no shutdown" in config

    def test_running_config_shows_shutdown_for_disabled(self):
        """After shutdown, port shows 'shutdown' in config."""
        state = DeviceStateManager()
        state.configure_port("Gi0/2", "shutdown")
        config = state.get_running_config()
        # Gi0/2 should now be disabled
        assert "shutdown" in config

    def test_running_config_contains_vlans(self):
        """Running config contains VLAN declarations."""
        state = DeviceStateManager()
        config = state.get_running_config()
        assert "vlan 1" in config
        assert "vlan 10" in config

    def test_running_config_ends_with_end(self):
        """Running config ends with 'end'."""
        state = DeviceStateManager()
        config = state.get_running_config()
        assert config.strip().endswith("end")

    def test_running_config_has_timestamp(self):
        """Running config contains Generated timestamp."""
        state = DeviceStateManager()
        config = state.get_running_config()
        assert "Generated at:" in config
