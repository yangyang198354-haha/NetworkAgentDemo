"""
MOD-DS-006: SimulatorDiagTool — Diagnostic tool via SSH to simulator device.
@module device_simulator
@implements IFC-DS-006-01
@covers REQ-FUNC-107, REQ-FUNC-109, REQ-FUNC-110, REQ-FUNC-119

Connects to a running simulator SSH server and executes diagnostic commands.
Uses paramiko SSHClient (NOT the simulator ServerInterface) to provide the same
interface as a real SSH-based diagnostic tool.
"""

import time
import random
from typing import Any, Optional

import paramiko
from loguru import logger

from src.models.alert import DeviceAuth
from src.models.fix_plan import DiagResult
from src.tools.switch_diag_tool import AbstractSwitchDiagTool


class SimulatorDiagTool(AbstractSwitchDiagTool):
    """
    Simulator diagnostic tool — connects to simulator SSH server and runs commands.

    IFC-DS-006-01: _run(device_ip, command, auth) → DiagResult
    Uses paramiko SSHClient to send commands to the simulator process.
    Falls back to mock-like behavior if SSH connection fails.
    """

    name: str = "switch_diag_simulator"
    description: str = "Execute diagnostic commands on simulator switch via SSH"

    def __init__(self, timeout: float = 5.0):
        super().__init__()
        self._timeout = timeout

    def _run(
        self,
        device_ip: str,
        command: str,
        auth: DeviceAuth,
    ) -> DiagResult:
        """
        Execute a diagnostic command via SSH to the simulator.

        Args:
            device_ip: IP address of the simulator (usually 127.0.0.1)
            command: CLI command to execute
            auth: SSH credentials (username, password, port in extra fields)
        """
        port = getattr(auth, "port", 22) or 22
        username = auth.username or "admin"
        password = auth.password or ""

        start = time.perf_counter()

        try:
            output = self._ssh_exec(device_ip, port, username, password, command)
            elapsed = int((time.perf_counter() - start) * 1000)
            logger.info(f"[SimulatorDiag] {device_ip}:{port} '{command}' → {len(output)} bytes, {elapsed}ms")
            return DiagResult(
                success=True,
                output=output,
                execution_time_ms=elapsed,
            )
        except Exception as e:
            elapsed = int((time.perf_counter() - start) * 1000)
            logger.warning(f"[SimulatorDiag] {device_ip}:{port} '{command}' → FAILED: {e}")
            return DiagResult(
                success=False,
                output=f"% SSH connection failed: {e}",
                execution_time_ms=elapsed,
            )

    def _ssh_exec(
        self, host: str, port: int, username: str, password: str, command: str
    ) -> str:
        """Execute a single command via SSH exec channel."""
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        try:
            client.connect(
                hostname=host,
                port=port,
                username=username,
                password=password,
                timeout=self._timeout,
                allow_agent=False,
                look_for_keys=False,
            )

            # Use exec_command for single-command execution
            stdin, stdout, stderr = client.exec_command(command, timeout=self._timeout)
            output = stdout.read().decode("utf-8", errors="replace")
            err_output = stderr.read().decode("utf-8", errors="replace")

            if err_output and "error" in err_output.lower():
                return err_output

            # Simulate realistic execution delay
            time.sleep(random.uniform(0.1, 0.4))
            return output

        finally:
            try:
                client.close()
            except Exception:
                pass
