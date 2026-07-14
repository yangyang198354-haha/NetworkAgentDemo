"""
Simulator package — Switch simulator with interactive SSH service.
@module device_simulator
@covers REQ-FUNC-106 ~ REQ-FUNC-110, REQ-FUNC-121

Provides:
  - DeviceStateManager: in-memory port/VLAN/CPU/memory/IO state
  - SimulatorSSHServer: paramiko-based SSH server for CLI interaction
  - SimulatorLifecycleManager: start/stop/status of simulator instances
"""

from src.simulator.state_manager import DeviceStateManager
from src.simulator.ssh_server import SimulatorSSHServer
from src.simulator.lifecycle_manager import SimulatorLifecycleManager

__all__ = ["DeviceStateManager", "SimulatorSSHServer", "SimulatorLifecycleManager"]
