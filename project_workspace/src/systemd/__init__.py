"""
MOD-INSP-001, MOD-INSP-002: systemd package — systemd interaction layer.
@author sub_agent_software_developer
@module systemd
@version 0.2.0

Provides:
  - MOD-INSP-001: systemd_unit_manager — Jinja2-based unit file generation
  - MOD-INSP-002: systemctl_executor — sudo systemctl command abstraction
"""

from .systemctl_executor import (
    SystemctlExecutor,
    TimerStatus,
    ServiceStatus,
    SystemctlResult,
    SystemdAvailability,
    SystemctlPermissionError,
    SystemctlTimeoutError,
    SystemdNotAvailableError,
    SystemctlCommandError,
)

from .systemd_unit_manager import SystemdUnitManager

__all__ = [
    "SystemctlExecutor",
    "SystemdUnitManager",
    "TimerStatus",
    "ServiceStatus",
    "SystemctlResult",
    "SystemdAvailability",
    "SystemctlPermissionError",
    "SystemctlTimeoutError",
    "SystemdNotAvailableError",
    "SystemctlCommandError",
]
