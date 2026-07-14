"""
MOD-DS-004: DeviceStateManager — In-memory switch state for simulator.
@module device_simulator
@implements IFC-DS-004-01 ~ IFC-DS-004-05
@covers REQ-FUNC-107, REQ-FUNC-108, REQ-FUNC-109, REQ-FUNC-110

Maintains mutable in-memory state for a simulated switch:
  - 8 GigabitEthernet ports (Gi0/1 ~ Gi0/8) with status/VLAN/duplex/speed/MAC
  - CPU usage (dynamic random, 5s/1min/5min averages) + process list
  - Memory usage (used/total MB)
  - IO read/write rates
  - Running configuration
"""

import random
import time
from dataclasses import dataclass, field
from typing import Optional

from loguru import logger


# ────────────────────────────────────────────────────
# Port state data class
# ────────────────────────────────────────────────────

@dataclass
class PortState:
    """Single switch port state."""
    name: str
    status: str = "up"              # up | down | administratively down | notconnect
    vlan: int = 1
    duplex: str = "Full"
    speed: str = "1000"             # Mbps as string: "10" | "100" | "1000"
    port_type: str = "10/100/1000BaseTX"
    description: str = ""
    mac_address: str = ""           # auto-generated if empty
    enabled: bool = True            # no shutdown (True) / shutdown (False)

    # Statistics
    input_packets: int = 0
    output_packets: int = 0
    input_errors: int = 0
    output_errors: int = 0
    input_rate_bps: int = 0         # 5-min input rate
    output_rate_bps: int = 0        # 5-min output rate

    def effective_status(self) -> str:
        """Return effective port status considering enabled flag."""
        if not self.enabled:
            return "administratively down"
        return self.status

    def to_summary(self) -> dict:
        """Return short status dict for API responses."""
        return {
            "name": self.name,
            "status": self.effective_status(),
            "vlan": self.vlan,
            "duplex": self.duplex if self.enabled else "Auto",
            "speed": self.speed if self.enabled else "Auto",
            "type": self.port_type,
            "description": self.description,
        }

    def to_detail(self) -> dict:
        """Return detailed status dict (show interface)."""
        eff = self.effective_status()
        is_up = eff == "up"
        return {
            "name": self.name,
            "status": eff,
            "mac_address": self.mac_address,
            "mtu": 1500,
            "bandwidth_kbps": int(self.speed) * 1000 if self.speed.isdigit() else 1000000,
            "duplex": self.duplex,
            "speed": self.speed,
            "vlan": self.vlan,
            "description": self.description,
            "input_packets": self.input_packets + random.randint(0, 100),
            "output_packets": self.output_packets + random.randint(0, 100),
            "input_errors": self.input_errors,
            "output_errors": self.output_errors,
            "input_rate_bps": self.input_rate_bps + random.randint(0, 10000),
            "output_rate_bps": self.output_rate_bps + random.randint(0, 100000),
        }


# ────────────────────────────────────────────────────
# Device State Manager
# ────────────────────────────────────────────────────

class DeviceStateManager:
    """
    In-memory mutable state for a single simulated switch device.

    IFC-DS-004-01: get_all_ports() → list[PortState]
    IFC-DS-004-02: get_port(port_name) → PortState | None
    IFC-DS-004-03: configure_port(port_name, action, value) → (success: bool, message: str)
    IFC-DS-004-04: get_cpu() → dict
    IFC-DS-004-05: get_memory_io() → dict
    """

    # Default MAC addresses per port (locally-administered unicast)
    _BASE_MACS = [
        "00:1A:2B:3C:4D:01", "00:1A:2B:3C:4D:02",
        "00:1A:2B:3C:4D:03", "00:1A:2B:3C:4D:04",
        "00:1A:2B:3C:4D:05", "00:1A:2B:3C:4D:06",
        "00:1A:2B:3C:4D:07", "00:1A:2B:3C:4D:08",
    ]

    _DEFAULT_PROCESSES = [
        ("Chunk Manager", 0.0), ("Load Meter", 0.0), ("ARP Input", 0.31),
        ("IP Input", 8.5), ("TCP Timer", 1.2), ("HTTP CORE", 2.8),
        ("SNMP ENGINE", 3.5), ("SSH Process", 1.5), ("Spanning Tree", 2.3),
        ("HSRP Main", 1.1), ("OSPF Router", 1.5), ("CDP Protocol", 0.8),
    ]

    def __init__(self, device_name: str = "Sim-SW-01"):
        self.device_name = device_name
        self.ports: dict[str, PortState] = {}
        self._init_ports()
        self._cpu_base = random.uniform(15.0, 45.0)  # base CPU%
        self._mem_total_mb = 512
        self._mem_used_base_mb = random.uniform(180, 350)
        self._io_read_base = random.uniform(50, 200)     # KB/s
        self._io_write_base = random.uniform(30, 120)    # KB/s
        logger.info(f"[StateManager] Initialized for {device_name}: 8 ports, "
                     f"CPU base={self._cpu_base:.1f}%, MEM base={self._mem_used_base_mb:.0f}MB")

    def _init_ports(self) -> None:
        """Create 8 default GigabitEthernet ports with varied states."""
        defaults = [
            ("Gi0/1", "up", 1, "Uplink to Core"),
            ("Gi0/2", "down", 1, "Access Port"),
            ("Gi0/3", "up", 1, "Server Port"),
            ("Gi0/4", "up", 1, "Trunk to SW-02"),
            ("Gi0/5", "up", 10, "Production VLAN"),
            ("Gi0/6", "up", 10, "Production VLAN"),
            ("Gi0/7", "notconnect", 1, "Spare Port"),
            ("Gi0/8", "notconnect", 1, "Spare Port"),
        ]
        for i, (name, status, vlan, desc) in enumerate(defaults):
            self.ports[name] = PortState(
                name=name,
                status=status,
                vlan=vlan,
                description=desc,
                mac_address=self._BASE_MACS[i],
                input_packets=random.randint(1000, 50000),
                output_packets=random.randint(500, 30000),
                input_rate_bps=random.randint(0, 500000),
                output_rate_bps=random.randint(0, 1000000),
            )

    # ── Port queries ──────────────────────────────────────

    def get_all_ports(self) -> list[PortState]:
        """IFC-DS-004-01: Return all ports (state snapshot with random stats)."""
        return list(self.ports.values())

    def get_port(self, port_name: str) -> Optional[PortState]:
        """IFC-DS-004-02: Return a single port by name."""
        return self.ports.get(port_name)

    def get_up_ports(self) -> list[PortState]:
        """Return all ports that are effectively up."""
        return [p for p in self.ports.values() if p.effective_status() == "up"]

    # ── Port configuration ───────────────────────────────

    def configure_port(self, port_name: str, action: str, value: str = "") -> tuple[bool, str]:
        """
        IFC-DS-004-03: Configure a port.

        Actions: shutdown | no-shutdown | set-vlan | set-description
        """
        port = self.ports.get(port_name)
        if port is None:
            return False, f"端口 {port_name} 不存在"

        if action == "shutdown":
            port.enabled = False
            logger.info(f"[StateManager] {port_name}: shutdown → administratively down")
            return True, f"[OK] {port_name} disabled"

        elif action == "no-shutdown":
            port.enabled = True
            logger.info(f"[StateManager] {port_name}: no shutdown → {port.status}")
            return True, f"[OK] {port_name} enabled"

        elif action == "set-vlan":
            try:
                vlan_id = int(value)
                if vlan_id < 1 or vlan_id > 4094:
                    return False, f"VLAN ID {vlan_id} 超出范围 (1-4094)"
                port.vlan = vlan_id
                logger.info(f"[StateManager] {port_name}: vlan → {vlan_id}")
                return True, f"[OK] {port_name} switchport access vlan {vlan_id}"
            except ValueError:
                return False, f"无效的 VLAN ID: {value}"

        elif action == "set-description":
            port.description = value
            logger.info(f"[StateManager] {port_name}: description → '{value}'")
            return True, f"[OK] {port_name} description updated"

        else:
            return False, f"未知操作: {action}"

    # ── System resource queries ──────────────────────────

    def get_cpu(self) -> dict:
        """
        IFC-DS-004-04: Return current CPU usage.
        Values fluctuate ±5% around base for realistic feel.
        """
        # Dynamic random fluctuation around base
        delta = random.uniform(-5, 15)  # occasional spikes
        cpu_5s = min(100.0, max(1.0, self._cpu_base + delta))
        cpu_1m = min(100.0, max(1.0, self._cpu_base + delta * 0.7))
        cpu_5m = min(100.0, max(1.0, self._cpu_base + delta * 0.4))

        # Generate process list with fluctuating CPU%
        processes = []
        pid = 1
        for name, base_pct in self._DEFAULT_PROCESSES:
            pct = base_pct + random.uniform(-0.3, 0.5) if base_pct > 0 else 0.0
            processes.append({
                "pid": pid,
                "name": name,
                "cpu_5s": round(max(0, pct), 2),
                "cpu_1m": round(max(0, pct * 0.9), 2),
                "cpu_5m": round(max(0, pct * 0.85), 2),
            })
            pid += 1 if pid < 10 else random.randint(10, 30)

        return {
            "cpu_5s": round(cpu_5s, 1),
            "cpu_1m": round(cpu_1m, 1),
            "cpu_5m": round(cpu_5m, 1),
            "processes": processes,
        }

    def get_memory_io(self) -> dict:
        """
        IFC-DS-004-05: Return memory usage and IO statistics.
        """
        delta = random.uniform(-20, 30)
        used = min(self._mem_total_mb, max(10, self._mem_used_base_mb + delta))
        free = self._mem_total_mb - used

        return {
            "memory_total_mb": self._mem_total_mb,
            "memory_used_mb": round(used, 1),
            "memory_free_mb": round(free, 1),
            "memory_usage_pct": round(used / self._mem_total_mb * 100, 1),
            "io_read_kbps": round(self._io_read_base + random.uniform(-20, 50), 1),
            "io_write_kbps": round(self._io_write_base + random.uniform(-15, 40), 1),
        }

    # ── Running config ───────────────────────────────────

    def get_running_config(self) -> str:
        """Generate a running-config reflecting current state."""
        lines = [
            f"! Simulator Running Configuration",
            f"! Device: {self.device_name}",
            f"! Generated at: {time.strftime('%Y-%m-%d %H:%M:%S')}",
            f"!",
            f"hostname {self.device_name}",
            f"!",
            f"spanning-tree mode pvst",
            f"!",
        ]
        # VLANs
        vlans = sorted(set(p.vlan for p in self.ports.values()))
        for vid in vlans:
            lines.append(f"vlan {vid}")
            lines.append(f" name VLAN{vid:04d}")
            lines.append("!")
        # Interfaces
        for port in sorted(self.ports.values(), key=lambda p: p.name):
            lines.append(f"interface {port.name}")
            if port.description:
                lines.append(f" description {port.description}")
            lines.append(f" switchport access vlan {port.vlan}")
            if port.enabled:
                lines.append(" no shutdown")
            else:
                lines.append(" shutdown")
            lines.append("!")
        lines.append("end")
        return "\n".join(lines)
