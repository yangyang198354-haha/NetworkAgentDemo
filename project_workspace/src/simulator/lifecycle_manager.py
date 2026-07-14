"""
MOD-DS-005: SimulatorLifecycleManager — Remote simulator process lifecycle (VPS).
@module device_simulator
@implements IFC-DS-005-01 ~ IFC-DS-005-07
@covers REQ-FUNC-105, REQ-FUNC-121

Architecture (方案 B — VPS standalone process):
  - Each simulator runs as an independent process (simulator_service.py)
  - LifecycleManager uses subprocess.Popen to start/stop
  - Communication: HTTP to management API for status/ports/system
  - Heartbeat: TCP connect to SSH port

Concurrency safety:
  - Lock held ONLY for dict operations (<1ms), NEVER during I/O
  - All HTTP calls and subprocess waits are outside lock
  - Global socket timeout prevents hung HTTP requests
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

# ── Global socket timeout to prevent hung HTTP requests ──
_socket_timeout_set = False


def _ensure_socket_timeout():
    """Set a global default socket timeout to prevent hung connections."""
    global _socket_timeout_set
    if not _socket_timeout_set:
        socket.setdefaulttimeout(10.0)
        _socket_timeout_set = True


# ── Management API port range ─────────────────────────
MGMT_PORT_BASE = 9222


class SimulatorLifecycleManager:
    """
    Manages simulator processes on the VPS.

    Thread-safety: _lock protects _instances dict only. All I/O operations
    (HTTP calls, subprocess waits) are performed outside the lock to prevent
    deadlocks and thread pool exhaustion.
    """

    def __init__(self):
        self._instances: dict[int, dict] = {}
        self._lock = threading.Lock()
        self._project_root = str(Path(__file__).resolve().parent.parent.parent)
        self._python = sys.executable
        _ensure_socket_timeout()

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
        """Allocate SSH + management port pair."""
        used_ssh = set()
        used_mgmt = set()
        with self._lock:
            for info in self._instances.values():
                if info.get("ssh_port"):
                    used_ssh.add(info["ssh_port"])
                if info.get("mgmt_port"):
                    used_mgmt.add(info["mgmt_port"])

        if preferred_ssh > 0 and preferred_ssh not in used_ssh and not self.check_port_used(preferred_ssh):
            ssh_port = preferred_ssh
            mgmt_port = ssh_port + 7000
            if not self.check_port_used(mgmt_port) and mgmt_port not in used_mgmt:
                return ssh_port, mgmt_port

        for ssh_port in range(2222, 65536 - 7000):
            if ssh_port in used_ssh or self.check_port_used(ssh_port):
                continue
            mgmt_port = ssh_port + 7000
            if mgmt_port in used_mgmt or self.check_port_used(mgmt_port):
                continue
            return ssh_port, mgmt_port

        raise RuntimeError("No available port pair in range 2222-58535")

    # ── Heartbeat ──────────────────────────────────────────

    @staticmethod
    def heartbeat(host: str, port: int, timeout: float = 3.0) -> tuple[bool, Optional[float]]:
        """TCP-level heartbeat check. Returns (is_online, response_time_ms)."""
        start = time.perf_counter()
        try:
            with socket.create_connection((host, port), timeout=timeout):
                elapsed = (time.perf_counter() - start) * 1000
                return True, round(elapsed, 1)
        except (socket.timeout, OSError, ConnectionRefusedError):
            return False, None

    # ── HTTP helpers (NEVER call while holding _lock) ──────

    @staticmethod
    def _mgmt_get(mgmt_port: int, path: str, timeout: float = 3.0) -> Optional[dict]:
        """GET request to simulator management API."""
        try:
            url = f"http://127.0.0.1:{mgmt_port}/{path.lstrip('/')}"
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            logger.debug(f"[LifecycleManager] MGMT GET {path} failed: {e}")
            return None

    @staticmethod
    def _mgmt_post(mgmt_port: int, path: str, data: dict, timeout: float = 3.0) -> Optional[dict]:
        """POST request to simulator management API."""
        try:
            url = f"http://127.0.0.1:{mgmt_port}/{path.lstrip('/')}"
            body = json.dumps(data).encode("utf-8")
            req = urllib.request.Request(url, data=body, method="POST")
            req.add_header("Content-Type", "application/json")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            logger.debug(f"[LifecycleManager] MGMT POST {path} failed: {e}")
            return None

    @staticmethod
    def _wait_for_ready(mgmt_port: int, timeout: float = 8.0) -> bool:
        """Poll the management API /health until it responds. STATIC — no lock needed."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            data = SimulatorLifecycleManager._mgmt_get(mgmt_port, "health", timeout=2.0)
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
        Launch a simulator process via subprocess.
        Lock is held only for dict mutation, NOT during _wait_for_ready.
        """
        # ── Phase 1: Allocate and launch (under lock) ──
        with self._lock:
            if device_id in self._instances:
                info = self._instances[device_id]
                if info.get("process") and info["process"].poll() is None:
                    return False, f"模拟器已在运行 (SSH={info['ssh_port']}, MGMT={info['mgmt_port']})", \
                           info["ssh_port"], info["mgmt_port"]
                else:
                    del self._instances[device_id]

            try:
                actual_ssh, actual_mgmt = self.allocate_ports(ssh_port, mgmt_port)
            except RuntimeError as e:
                return False, str(e), None, None

            cmd = [
                self._python, "-m", "src.simulator.simulator_service",
                "--device-name", device_name,
                "--ssh-host", ssh_host,
                "--ssh-port", str(actual_ssh),
                "--mgmt-host", "127.0.0.1",
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
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except Exception as e:
                return False, f"启动进程失败: {e}", None, None

            # Register immediately so other methods can see it
            self._instances[device_id] = {
                "device_id": device_id,
                "device_name": device_name,
                "ssh_host": ssh_host,
                "ssh_port": actual_ssh,
                "mgmt_port": actual_mgmt,
                "process": process,
                "username": username,
            }

        # ── Phase 2: Wait for ready (OUTSIDE lock — NO I/O under lock) ──
        if not self._wait_for_ready(actual_mgmt, timeout=10.0):
            logger.error(f"[LifecycleManager] Simulator API not ready in 10s, killing...")
            try:
                process.terminate()
                process.wait(timeout=3)
            except Exception:
                try:
                    process.kill()
                except Exception:
                    pass

            with self._lock:
                self._instances.pop(device_id, None)

            return False, f"模拟器进程启动但管理 API 无响应 (端口 {actual_mgmt})", None, None

        logger.info(f"[LifecycleManager] Simulator running: device_id={device_id} "
                    f"SSH={ssh_host}:{actual_ssh} MGMT=127.0.0.1:{actual_mgmt}")
        return True, f"模拟器已启动 (SSH:{actual_ssh}, MGMT:{actual_mgmt})", actual_ssh, actual_mgmt

    def stop_simulator(self, device_id: int) -> tuple[bool, str]:
        """
        Stop a simulator process.
        Lock held only for dict pop; all I/O (HTTP, process wait) is outside lock.
        """
        # ── Phase 1: Remove from registry (under lock) ──
        with self._lock:
            if device_id not in self._instances:
                return False, "模拟器未运行"
            info = self._instances.pop(device_id)

        process: subprocess.Popen = info["process"]
        mgmt_port: int = info["mgmt_port"]
        ssh_port: int = info["ssh_port"]

        # ── Phase 2: Stop the process (OUTSIDE lock — NO I/O under lock) ──
        # 1. Graceful shutdown via management API
        self._mgmt_post(mgmt_port, "shutdown", {}, timeout=2.0)

        # 2. Wait for process to exit
        try:
            process.wait(timeout=5.0)
            logger.info(f"[LifecycleManager] Process exited cleanly (device_id={device_id})")
        except subprocess.TimeoutExpired:
            # 3. SIGTERM
            logger.warning(f"[LifecycleManager] Sending SIGTERM to device_id={device_id}...")
            try:
                process.terminate()
                process.wait(timeout=3.0)
            except subprocess.TimeoutExpired:
                # 4. SIGKILL
                logger.warning(f"[LifecycleManager] Sending SIGKILL to device_id={device_id}...")
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
        Return simulator status. HTTP health check is outside lock.
        """
        # Fast path under lock
        with self._lock:
            info = self._instances.get(device_id)
            if info is None:
                return {
                    "device_id": device_id, "running": False, "status": "STOPPED",
                    "ssh_host": None, "ssh_port": None, "mgmt_port": None,
                }
            # Snapshot needed fields while holding lock
            alive = info["process"].poll() is None
            snapshot = {
                "ssh_host": info["ssh_host"],
                "ssh_port": info["ssh_port"],
                "mgmt_port": info["mgmt_port"],
            }

        # HTTP health check OUTSIDE lock
        mgmt_data = None
        if alive:
            mgmt_data = self._mgmt_get(snapshot["mgmt_port"], "health", timeout=2.0)

        return {
            "device_id": device_id,
            "running": alive and mgmt_data is not None,
            "status": "RUNNING" if (alive and mgmt_data is not None) else "ERROR",
            "ssh_host": snapshot["ssh_host"],
            "ssh_port": snapshot["ssh_port"],
            "mgmt_port": snapshot["mgmt_port"],
            "uptime_seconds": mgmt_data.get("uptime_seconds") if mgmt_data else None,
        }

    def get_simulator_info(self, device_id: int) -> Optional[dict]:
        """Return full instance info dict, or None."""
        with self._lock:
            info = self._instances.get(device_id)
            if info is None:
                return None
            return dict(info)

    def find_by_device_name(self, device_name: str) -> Optional[dict]:
        """Find a running simulator by device name. Returns info dict or None."""
        with self._lock:
            for info in self._instances.values():
                if info.get("device_name") == device_name:
                    if info["process"].poll() is None:
                        return dict(info)
            return None

    # ── State proxy methods (HTTP outside lock) ──────────

    def get_ports(self, device_id: int) -> Optional[dict]:
        """Get port status via management API."""
        info = self.get_simulator_info(device_id)  # lock released inside
        if info is None:
            return None
        return self._mgmt_get(info["mgmt_port"], "ports")

    def get_system(self, device_id: int) -> Optional[dict]:
        """Get CPU/memory/IO via management API."""
        info = self.get_simulator_info(device_id)
        if info is None:
            return None
        return self._mgmt_get(info["mgmt_port"], "status")

    def configure_port(self, device_id: int, port_name: str, action: str, value: str = "") -> Optional[dict]:
        """Configure a port via management API."""
        info = self.get_simulator_info(device_id)
        if info is None:
            return None
        return self._mgmt_post(info["mgmt_port"], f"ports/{port_name}/config",
                               {"action": action, "value": value})

    # ── Bulk operations ────────────────────────────────────

    def list_instances(self) -> list[dict]:
        """Return all running simulator instances."""
        with self._lock:
            return [
                {
                    "device_id": info["device_id"],
                    "device_name": info["device_name"],
                    "ssh_host": info["ssh_host"],
                    "ssh_port": info["ssh_port"],
                    "mgmt_port": info["mgmt_port"],
                    "running": info["process"].poll() is None,
                }
                for info in self._instances.values()
            ]

    def shutdown_all(self) -> None:
        """
        Stop all running simulators. Collects IDs under lock, then stops outside.
        Max total shutdown time is bounded: N * (2+5+3+2) seconds worst case.
        For a typical 1-2 simulators, this is ~12-24 seconds.
        """
        with self._lock:
            device_ids = list(self._instances.keys())
        for device_id in device_ids:
            self.stop_simulator(device_id)
        logger.info("[LifecycleManager] All simulators shut down")

    def __len__(self) -> int:
        with self._lock:
            return len(self._instances)
