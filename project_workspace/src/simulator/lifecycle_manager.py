"""
MOD-DS-005: SimulatorLifecycleManager — Remote simulator process lifecycle (VPS).
@module device_simulator
@implements IFC-DS-005-01 ~ IFC-DS-005-04
@covers REQ-FUNC-105, REQ-FUNC-121

Architecture (方案 B — VPS standalone process):
  - Each simulator runs as an independent process (simulator_service.py)
  - LifecycleManager uses subprocess.Popen to start/stop
  - Communication: HTTP to management API for status/ports/system
  - Heartbeat: TCP connect to SSH port
"""

from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional

from loguru import logger

# ── Management API port range ─────────────────────────
MGMT_PORT_BASE = 9222


class SimulatorLifecycleManager:
    """
    Manages simulator processes on the VPS.

    IFC-DS-005-01: start_simulator(device_id, ...) → (bool, str, int ssh_port, int mgmt_port)
    IFC-DS-005-02: stop_simulator(device_id) → (bool, str)
    IFC-DS-005-03: heartbeat(host, port, timeout) → (bool, float | None)
    IFC-DS-005-04: get_status(device_id) → dict (via HTTP proxy to mgmt API)
    IFC-DS-005-05: get_ports(device_id) → dict (via HTTP proxy)
    IFC-DS-005-06: get_system(device_id) → dict (via HTTP proxy)
    IFC-DS-005-07: configure_port(device_id, port_name, action, value) → dict
    """

    def __init__(self):
        self._instances: dict[int, dict] = {}
        self._lock = threading.Lock()
        # Determine project root for subprocess launch
        self._project_root = str(Path(__file__).resolve().parent.parent.parent)
        self._python = sys.executable

    # ── Port utilities ────────────────────────────────────

    @staticmethod
    def check_port_used(port: int, host: str = "0.0.0.0") -> bool:
        """Check if a TCP port is already in use."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind((host, port))
                s.close()
                return False
        except OSError:
            return True

    def allocate_ports(self, preferred_ssh: int = 0, preferred_mgmt: int = 0) -> tuple[int, int]:
        """
        Allocate SSH + management port pair for a new simulator.

        Strategy:
          - SSH ports start from 2222
          - Management ports = SSH port + 7000 (e.g. 2222 → 9222)
        """
        used_ssh = set()
        used_mgmt = set()
        with self._lock:
            for info in self._instances.values():
                if info.get("ssh_port"):
                    used_ssh.add(info["ssh_port"])
                if info.get("mgmt_port"):
                    used_mgmt.add(info["mgmt_port"])

        # Try preferred ports first
        if preferred_ssh > 0 and preferred_ssh not in used_ssh and not self.check_port_used(preferred_ssh):
            ssh_port = preferred_ssh
            mgmt_port = ssh_port + 7000
            if not self.check_port_used(mgmt_port) and mgmt_port not in used_mgmt:
                return ssh_port, mgmt_port

        # Scan from 2222 upward
        for ssh_port in range(2222, 65536 - 7000):
            if ssh_port in used_ssh or self.check_port_used(ssh_port):
                continue
            mgmt_port = ssh_port + 7000
            if mgmt_port in used_mgmt or self.check_port_used(mgmt_port):
                continue
            # Check mgmt port is also free
            return ssh_port, mgmt_port

        raise RuntimeError("No available port pair in range 2222-58535")

    # ── Heartbeat ──────────────────────────────────────────

    @staticmethod
    def heartbeat(host: str, port: int, timeout: float = 3.0) -> tuple[bool, Optional[float]]:
        """
        IFC-DS-005-03: TCP-level heartbeat check on SSH port.
        Returns (is_online, response_time_ms).
        """
        start = time.perf_counter()
        try:
            with socket.create_connection((host, port), timeout=timeout):
                elapsed = (time.perf_counter() - start) * 1000
                return True, round(elapsed, 1)
        except (socket.timeout, OSError, ConnectionRefusedError):
            return False, None

    # ── HTTP helpers for management API ────────────────────

    def _mgmt_get(self, mgmt_port: int, path: str, timeout: float = 3.0) -> Optional[dict]:
        """GET request to simulator management API."""
        try:
            url = f"http://127.0.0.1:{mgmt_port}/{path.lstrip('/')}"
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            logger.warning(f"[LifecycleManager] MGMT GET {path} failed: {e}")
            return None

    def _mgmt_post(self, mgmt_port: int, path: str, data: dict, timeout: float = 3.0) -> Optional[dict]:
        """POST request to simulator management API."""
        try:
            url = f"http://127.0.0.1:{mgmt_port}/{path.lstrip('/')}"
            body = json.dumps(data).encode("utf-8")
            req = urllib.request.Request(url, data=body, method="POST")
            req.add_header("Content-Type", "application/json")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            logger.warning(f"[LifecycleManager] MGMT POST {path} failed: {e}")
            return None

    def _wait_for_ready(self, mgmt_port: int, timeout: float = 8.0) -> bool:
        """Poll the management API /health until it responds."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            data = self._mgmt_get(mgmt_port, "health", timeout=1.5)
            if data and data.get("status") == "ok":
                return True
            time.sleep(0.3)
        return False

    # ── Instance management ────────────────────────────────

    def start_simulator(
        self,
        device_id: int,
        ssh_host: str = "0.0.0.0",
        ssh_port: int = 0,
        mgmt_port: int = 0,
        username: str = "admin",
        password: str = "switch123",
        device_name: str = "Sim-SW-01",
    ) -> tuple[bool, str, Optional[int], Optional[int]]:
        """
        IFC-DS-005-01: Launch a simulator process via subprocess.

        Returns:
            (success, message, ssh_port, mgmt_port)
        """
        with self._lock:
            # Check if already running
            if device_id in self._instances:
                info = self._instances[device_id]
                if info.get("process") and info["process"].poll() is None:
                    return False, f"模拟器已在运行 (SSH={info['ssh_port']}, MGMT={info['mgmt_port']})", \
                           info["ssh_port"], info["mgmt_port"]
                else:
                    # Stale entry, clean up
                    del self._instances[device_id]

            # Allocate port pair
            try:
                actual_ssh, actual_mgmt = self.allocate_ports(ssh_port, mgmt_port)
            except RuntimeError as e:
                return False, str(e), None, None

            # Build subprocess command
            cmd = [
                self._python, "-m", "src.simulator.simulator_service",
                "--device-name", device_name,
                "--ssh-host", ssh_host,
                "--ssh-port", str(actual_ssh),
                "--mgmt-host", "127.0.0.1",  # Management API only on localhost
                "--mgmt-port", str(actual_mgmt),
                "--username", username,
                "--password", password,
                "--max-connections", "5",
            ]

            logger.info(f"[LifecycleManager] Launching: {' '.join(cmd)}")

            try:
                process = subprocess.Popen(
                    cmd,
                    cwd=self._project_root,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    # Don't use start_new_session on Windows; on Linux use os.setsid
                )
            except Exception as e:
                return False, f"启动进程失败: {e}", None, None

            # Wait for management API to become ready
            if not self._wait_for_ready(actual_mgmt, timeout=10.0):
                # Process started but API not responding — kill it
                logger.error(f"[LifecycleManager] Simulator process started but API not ready in 10s")
                try:
                    process.terminate()
                    process.wait(timeout=3)
                except Exception:
                    process.kill()
                return False, f"模拟器进程启动但管理 API 无响应 (端口 {actual_mgmt})", None, None

            self._instances[device_id] = {
                "device_id": device_id,
                "device_name": device_name,
                "ssh_host": ssh_host,
                "ssh_port": actual_ssh,
                "mgmt_port": actual_mgmt,
                "process": process,
                "username": username,
            }

            logger.info(f"[LifecycleManager] Simulator running: device_id={device_id} "
                        f"SSH={ssh_host}:{actual_ssh} MGMT=127.0.0.1:{actual_mgmt}")
            return True, f"模拟器已启动 (SSH:{actual_ssh}, MGMT:{actual_mgmt})", actual_ssh, actual_mgmt

    def stop_simulator(self, device_id: int) -> tuple[bool, str]:
        """
        IFC-DS-005-02: Stop a simulator process.
        Tries graceful shutdown (POST /shutdown), then SIGTERM, then SIGKILL.
        """
        with self._lock:
            if device_id not in self._instances:
                return False, "模拟器未运行"

            info = self._instances.pop(device_id)
            process: subprocess.Popen = info["process"]
            mgmt_port: int = info["mgmt_port"]
            ssh_port: int = info["ssh_port"]

            # 1. Try graceful shutdown via management API
            result = self._mgmt_post(mgmt_port, "shutdown", {}, timeout=3.0)
            if result:
                logger.info(f"[LifecycleManager] Graceful shutdown accepted for device_id={device_id}")

            # 2. Wait for process to exit
            try:
                process.wait(timeout=5.0)
                logger.info(f"[LifecycleManager] Process exited cleanly (device_id={device_id})")
            except subprocess.TimeoutExpired:
                # 3. SIGTERM
                logger.warning(f"[LifecycleManager] Process still alive, sending SIGTERM...")
                try:
                    process.terminate()
                    process.wait(timeout=3.0)
                except subprocess.TimeoutExpired:
                    # 4. SIGKILL
                    logger.warning(f"[LifecycleManager] SIGTERM didn't work, sending SIGKILL...")
                    process.kill()
                    try:
                        process.wait(timeout=2.0)
                    except subprocess.TimeoutExpired:
                        logger.error(f"[LifecycleManager] Failed to kill process for device_id={device_id}")

            logger.info(f"[LifecycleManager] Stopped simulator device_id={device_id} "
                        f"(released SSH={ssh_port}, MGMT={mgmt_port})")
            return True, f"模拟器已停止 (SSH {ssh_port}, MGMT {mgmt_port} 已释放)"

    def get_status(self, device_id: int) -> dict:
        """
        IFC-DS-005-04: Return simulator status.
        Checks process alive + management API health.
        """
        with self._lock:
            info = self._instances.get(device_id)
            if info is None:
                return {
                    "device_id": device_id,
                    "running": False,
                    "status": "STOPPED",
                    "ssh_host": None,
                    "ssh_port": None,
                    "mgmt_port": None,
                }

            process: subprocess.Popen = info["process"]
            alive = process.poll() is None

            # Verify via management API
            mgmt_data = None
            if alive:
                mgmt_data = self._mgmt_get(info["mgmt_port"], "health", timeout=2.0)

            return {
                "device_id": device_id,
                "running": alive and mgmt_data is not None,
                "status": "RUNNING" if (alive and mgmt_data is not None) else "ERROR",
                "ssh_host": info["ssh_host"],
                "ssh_port": info["ssh_port"],
                "mgmt_port": info["mgmt_port"],
                "uptime_seconds": mgmt_data.get("uptime_seconds") if mgmt_data else None,
            }

    def get_simulator_info(self, device_id: int) -> Optional[dict]:
        """Return full instance info dict, or None."""
        with self._lock:
            return self._instances.get(device_id)

    # ── State proxy methods (via management API) ──────────

    def get_ports(self, device_id: int) -> Optional[dict]:
        """IFC-DS-005-05: Get port status via management API."""
        info = self.get_simulator_info(device_id)
        if info is None:
            return None
        return self._mgmt_get(info["mgmt_port"], "ports")

    def get_system(self, device_id: int) -> Optional[dict]:
        """IFC-DS-005-06: Get CPU/memory/IO via management API."""
        info = self.get_simulator_info(device_id)
        if info is None:
            return None
        return self._mgmt_get(info["mgmt_port"], "status")

    def configure_port(self, device_id: int, port_name: str, action: str, value: str = "") -> Optional[dict]:
        """IFC-DS-005-07: Configure a port via management API."""
        info = self.get_simulator_info(device_id)
        if info is None:
            return None
        return self._mgmt_post(info["mgmt_port"], f"ports/{port_name}/config",
                               {"action": action, "value": value})

    # ── Bulk operations ────────────────────────────────────

    def list_instances(self) -> list[dict]:
        """Return all running simulator instances."""
        with self._lock:
            result = []
            for info in self._instances.values():
                process = info["process"]
                result.append({
                    "device_id": info["device_id"],
                    "device_name": info["device_name"],
                    "ssh_host": info["ssh_host"],
                    "ssh_port": info["ssh_port"],
                    "mgmt_port": info["mgmt_port"],
                    "running": process.poll() is None,
                })
            return result

    def shutdown_all(self) -> None:
        """Stop all running simulators (for graceful FastAPI shutdown)."""
        with self._lock:
            device_ids = list(self._instances.keys())
        for device_id in device_ids:
            self.stop_simulator(device_id)
        logger.info("[LifecycleManager] All simulators shut down")

    def __len__(self) -> int:
        with self._lock:
            return len(self._instances)
