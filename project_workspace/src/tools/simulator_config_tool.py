"""
MOD-DS-007: SimulatorConfigTool — Configuration tool via SSH to simulator device.
@module device_simulator
@implements IFC-DS-007-01
@covers REQ-FUNC-108, REQ-FUNC-119

Connects to a running simulator SSH server and executes configuration commands.
Sends configure terminal + commands + exit sequence over exec channel.
"""

import time
from typing import Any, Optional

import paramiko
from loguru import logger

from src.models.alert import DeviceAuth
from src.models.fix_plan import ConfigResult
from src.tools.switch_config_tool import AbstractSwitchConfigTool


class SimulatorConfigTool(AbstractSwitchConfigTool):
    """
    Simulator configuration tool — connects to simulator SSH server via paramiko.

    IFC-DS-007-01: _run(device_ip, commands, auth) → ConfigResult
    Sends commands through SSH exec channel wrapped in config mode.
    """

    name: str = "switch_config_simulator"
    description: str = "Execute configuration commands on simulator switch via SSH"

    def __init__(self, timeout: float = 5.0):
        super().__init__()
        self._timeout = timeout

    def _run(
        self,
        device_ip: str,
        commands: list[str],
        auth: DeviceAuth,
    ) -> ConfigResult:
        port = getattr(auth, "port", 22) or 22
        username = auth.username or "admin"
        password = auth.password or ""

        commands_executed = 0
        commands_failed = 0
        output_lines: list[str] = []

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        try:
            client.connect(
                hostname=device_ip,
                port=port,
                username=username,
                password=password,
                timeout=self._timeout,
                allow_agent=False,
                look_for_keys=False,
            )

            # For config mode commands, we use an interactive channel approach
            # Build the full command sequence: config t → commands → end
            channel = client.invoke_shell()
            time.sleep(0.2)
            # Read initial banner/prompt
            self._read_channel(channel)

            # Enter config mode
            channel.send("configure terminal\n")
            time.sleep(0.2)
            output_lines.append(self._read_channel(channel))

            for cmd in commands:
                logger.info(f"[SimulatorConfig] {device_ip}:{port} executing '{cmd}'")
                channel.send(f"{cmd}\n")
                time.sleep(0.1)
                output = self._read_channel(channel)
                output_lines.append(f"{device_ip}# {cmd}")

                if "Invalid input" in output or "Error" in output or "Unknown" in output:
                    output_lines.append(f"[FAILED] {output.strip()}")
                    commands_failed += 1
                else:
                    output_lines.append(output.strip() or f"[OK] Command executed successfully")
                    commands_executed += 1

            # Exit config mode
            channel.send("end\n")
            time.sleep(0.1)
            self._read_channel(channel)

            channel.close()

        except paramiko.AuthenticationException:
            logger.error(f"[SimulatorConfig] Auth failed for {device_ip}:{port}")
            return ConfigResult(
                success=False,
                output="Authentication failed — check username/password",
                commands_executed=0,
                commands_failed=len(commands),
            )
        except Exception as e:
            logger.error(f"[SimulatorConfig] SSH error: {e}")
            return ConfigResult(
                success=False,
                output=f"SSH connection error: {e}",
                commands_executed=commands_executed,
                commands_failed=len(commands) - commands_executed,
            )
        finally:
            try:
                client.close()
            except Exception:
                pass

        return ConfigResult(
            success=commands_failed == 0,
            output="\n".join(output_lines),
            commands_executed=commands_executed,
            commands_failed=commands_failed,
        )

    @staticmethod
    def _read_channel(channel, timeout: float = 0.5) -> str:
        """Read available data from an SSH channel with a short timeout."""
        import select as _select
        output = b""
        try:
            while _select.select([channel], [], [], timeout)[0]:
                if channel.recv_ready():
                    data = channel.recv(4096)
                    if not data:
                        break
                    output += data
                    timeout = 0.1  # shorter timeout after first data
                else:
                    break
        except Exception:
            pass
        return output.decode("utf-8", errors="replace")
