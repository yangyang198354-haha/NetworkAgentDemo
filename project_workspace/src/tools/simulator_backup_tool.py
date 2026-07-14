"""
MOD-DS-008: SimulatorBackupTool — Backup/rollback tool via SSH to simulator device.
@module device_simulator
@implements IFC-DS-008-01, IFC-DS-008-02
@covers REQ-FUNC-108, REQ-FUNC-119

Connects to a running simulator SSH server to:
  - backup: execute 'show running-config' via SSH and return the config
  - rollback: restore configuration from a previous backup
"""

import time
import uuid
from typing import Any, Optional

import paramiko
from loguru import logger

from src.models.alert import DeviceAuth
from src.models.fix_plan import BackupResult, RollbackResult
from src.tools.backup_tool import AbstractBackupTool


class SimulatorBackupTool(AbstractBackupTool):
    """
    Simulator backup/rollback tool — connects to simulator SSH server.

    IFC-DS-008-01: backup(device_ip, auth) → BackupResult
    IFC-DS-008-02: rollback(device_ip, backup_id, auth) → RollbackResult
    """

    name: str = "config_backup_simulator"
    description: str = "Backup or rollback simulator switch configuration via SSH"

    def __init__(self, timeout: float = 5.0):
        super().__init__()
        self._timeout = timeout
        self._backup_store: dict[str, str] = {}

    def _run(
        self,
        device_ip: str,
        auth: DeviceAuth,
        operation: str = "backup",
        backup_id: str | None = None,
    ) -> BackupResult | RollbackResult:
        if operation == "rollback":
            return self._do_rollback(device_ip, backup_id, auth)
        else:
            return self._do_backup(device_ip, auth)

    def _do_backup(self, device_ip: str, auth: DeviceAuth) -> BackupResult:
        """IFC-DS-008-01: Execute backup via SSH."""
        port = getattr(auth, "port", 22) or 22
        username = auth.username or "admin"
        password = auth.password or ""

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

            stdin, stdout, stderr = client.exec_command("show running-config", timeout=self._timeout)
            config = stdout.read().decode("utf-8", errors="replace")

            backup_id_str = str(uuid.uuid4())
            self._backup_store[backup_id_str] = config

            time.sleep(0.2)  # Simulate slight delay

            logger.info(f"[SimulatorBackup] {device_ip}:{port} backup created — "
                        f"backup_id={backup_id_str[:8]}...")
            return BackupResult(
                success=True,
                backup_id=backup_id_str,
                config=config,
            )

        except Exception as e:
            logger.error(f"[SimulatorBackup] {device_ip}:{port} backup FAILED: {e}")
            return BackupResult(
                success=False,
                backup_id="",
                config="",
                error=str(e),
            )
        finally:
            try:
                client.close()
            except Exception:
                pass

    def _do_rollback(
        self, device_ip: str, backup_id: str | None, auth: DeviceAuth
    ) -> RollbackResult:
        """IFC-DS-008-02: Execute rollback via SSH."""
        if backup_id is None:
            return RollbackResult(
                success=False,
                error="backup_id is required for rollback operation",
            )

        config = self._backup_store.get(backup_id)
        if config is None:
            return RollbackResult(
                success=False,
                error=f"Backup not found: {backup_id}",
            )

        port = getattr(auth, "port", 22) or 22
        username = auth.username or "admin"
        password = auth.password or ""

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

            # Send config lines via configure terminal
            channel = client.invoke_shell()
            time.sleep(0.2)
            # Read banner
            SimulatorConfigTool._read_channel(channel)

            channel.send("configure terminal\n")
            time.sleep(0.1)
            SimulatorConfigTool._read_channel(channel)

            for line in config.split("\n"):
                line = line.strip()
                if line and not line.startswith("!"):
                    channel.send(f"{line}\n")
                    time.sleep(0.05)

            channel.send("end\n")
            time.sleep(0.1)
            channel.close()

            logger.info(f"[SimulatorBackup] {device_ip}:{port} rollback from "
                        f"backup_id={backup_id[:8]}...")
            return RollbackResult(
                success=True,
                output=f"Configuration restored from backup {backup_id[:8]}...\n"
                       f"Device {device_ip} rolled back successfully.\n",
            )

        except Exception as e:
            logger.error(f"[SimulatorBackup] rollback FAILED: {e}")
            return RollbackResult(
                success=False,
                error=str(e),
            )
        finally:
            try:
                client.close()
            except Exception:
                pass


# Import for _read_channel
from src.tools.simulator_config_tool import SimulatorConfigTool
