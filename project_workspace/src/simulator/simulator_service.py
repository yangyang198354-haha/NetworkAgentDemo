"""
MOD-DS-016: Simulator Service — Standalone simulator process (VPS-deployable).
@module device_simulator
@covers REQ-FUNC-106~110, REQ-FUNC-121 (VPS remote control)

Entry point for a standalone simulator process that provides:
  - SSH server on --ssh-port for device CLI interaction (paramiko)
  - HTTP management API on --mgmt-port for remote lifecycle control

Usage:
  python -m src.simulator.simulator_service \
      --ssh-port 2222 --mgmt-port 9222 \
      --device-name "Sim-SW-01" \
      --username admin --password switch123

Management API (HTTP, JSON):
  GET  /health                    → {"status":"ok","device_name":"..."}
  GET  /status                    → cpu, memory, io, ssh_port, uptime
  GET  /ports                     → port status list + up-port details
  POST /ports/{name}/config       → configure port (body: {action, value})
  POST /shutdown                  → graceful shutdown
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import sys
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

# ── Ensure project root in sys.path ─────────────────────
_project_root = Path(__file__).resolve().parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from loguru import logger

from src.simulator.state_manager import DeviceStateManager
from src.simulator.ssh_server import SimulatorSSHServer

# ────────────────────────────────────────────────────
# HTTP Management API Handler
# ────────────────────────────────────────────────────

class _ManagementHandler(BaseHTTPRequestHandler):
    """
    Lightweight HTTP handler for simulator management API.
    No framework dependency — uses stdlib http.server.
    """

    # Class-level references set by SimulatorService
    state_manager: DeviceStateManager = None  # type: ignore
    ssh_server: SimulatorSSHServer = None  # type: ignore
    device_name: str = "Sim-SW-01"
    ssh_port: int = 2222
    start_time: float = 0.0

    def log_message(self, format, *args):
        """Redirect HTTP logs to loguru."""
        logger.debug(f"[MgmtAPI] {args[0] if args else format}")

    def _send_json(self, data: dict, status: int = 200):
        """Send a JSON response."""
        body = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> dict:
        """Read and parse JSON request body."""
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8"))

    def _parse_path(self):
        """Parse the request path into components."""
        parsed = urlparse(self.path)
        # e.g. /ports/Gi0/1/config → ["", "ports", "Gi0/1", "config"]
        parts = [p for p in parsed.path.split("/") if p]
        return parts, parsed.query

    # ── Routing ──────────────────────────────────────

    def do_GET(self):
        parts, _ = self._parse_path()

        if not parts or parts[0] == "health":
            return self._handle_health()
        if parts[0] == "status":
            return self._handle_status()
        if parts[0] == "ports":
            return self._handle_ports(parts[1:])
        return self._send_json({"error": "not found"}, 404)

    def do_POST(self):
        parts, _ = self._parse_path()

        if parts[0] == "shutdown":
            return self._handle_shutdown()
        if parts[0] == "ports" and len(parts) >= 3 and parts[-1] == "config":
            port_name = "/".join(parts[1:-1])  # support Gi0/1
            return self._handle_port_config(port_name)
        return self._send_json({"error": "not found"}, 404)

    def do_OPTIONS(self):
        """CORS preflight."""
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    # ── Handler methods ──────────────────────────────

    def _handle_health(self):
        self._send_json({
            "status": "ok",
            "device_name": self.device_name,
            "ssh_port": self.ssh_port,
            "ssh_running": self.ssh_server.is_running if self.ssh_server else False,
            "uptime_seconds": round(time.time() - self.start_time, 1),
        })

    def _handle_status(self):
        if not self.state_manager:
            return self._send_json({"error": "state not initialized"}, 500)

        cpu = self.state_manager.get_cpu()
        mem_io = self.state_manager.get_memory_io()

        self._send_json({
            "device_name": self.device_name,
            "ssh_port": self.ssh_port,
            "ssh_running": self.ssh_server.is_running if self.ssh_server else False,
            "uptime_seconds": round(time.time() - self.start_time, 1),
            "cpu": cpu,
            "memory": {
                "total_mb": mem_io["memory_total_mb"],
                "used_mb": mem_io["memory_used_mb"],
                "free_mb": mem_io["memory_free_mb"],
                "usage_pct": mem_io["memory_usage_pct"],
            },
            "io": {
                "read_kbps": mem_io["io_read_kbps"],
                "write_kbps": mem_io["io_write_kbps"],
            },
        })

    def _handle_ports(self, extra: list):
        if not self.state_manager:
            return self._send_json({"error": "state not initialized"}, 500)

        ports = [p.to_summary() for p in self.state_manager.get_all_ports()]
        up_ports = [p.to_detail() for p in self.state_manager.get_up_ports()]

        self._send_json({
            "device_name": self.device_name,
            "ports": ports,
            "up_ports_detail": up_ports,
        })

    def _handle_port_config(self, port_name: str):
        if not self.state_manager:
            return self._send_json({"error": "state not initialized"}, 500)

        body = self._read_body()
        action = body.get("action", "")
        value = body.get("value", "")

        success, message = self.state_manager.configure_port(port_name, action, value)
        self._send_json({
            "port_name": port_name,
            "action": action,
            "success": success,
            "message": message,
        })

    def _handle_shutdown(self):
        """Graceful shutdown — stop SSH, then HTTP server."""
        logger.info(f"[MgmtAPI] Shutdown requested for {self.device_name}")
        self._send_json({"message": "shutting down", "device_name": self.device_name})

        # Stop SSH in background to allow response to be sent
        def _do_shutdown():
            time.sleep(0.3)
            if self.ssh_server:
                self.ssh_server.stop()
            # Signal the main thread to exit
            os.kill(os.getpid(), signal.SIGTERM)

        threading.Thread(target=_do_shutdown, daemon=True).start()


# ────────────────────────────────────────────────────
# SimulatorService — Main process controller
# ────────────────────────────────────────────────────

class SimulatorService:
    """
    Standalone simulator process controller.

    Starts SSH server + HTTP management API in separate daemon threads.
    Main thread blocks waiting for shutdown signal.
    """

    def __init__(
        self,
        device_name: str = "Sim-SW-01",
        ssh_host: str = "0.0.0.0",
        ssh_port: int = 2222,
        mgmt_host: str = "0.0.0.0",
        mgmt_port: int = 9222,
        ssh_username: str = "admin",
        ssh_password: str = "switch123",
        max_connections: int = 5,
    ):
        self.device_name = device_name
        self.ssh_host = ssh_host
        self.ssh_port = ssh_port
        self.mgmt_host = mgmt_host
        self.mgmt_port = mgmt_port
        self.ssh_username = ssh_username
        self.ssh_password = ssh_password
        self.max_connections = max_connections

        self.state_manager = DeviceStateManager(device_name=device_name)
        self.ssh_server = SimulatorSSHServer(
            self.state_manager,
            max_connections=max_connections,
        )
        self._http_server: Optional[HTTPServer] = None

    def start(self) -> None:
        """Start SSH server and HTTP management API. Blocks until shutdown."""
        logger.info(f"[SimulatorService] Starting {self.device_name}...")

        # 1. Start SSH server
        self.ssh_server.start(
            host=self.ssh_host,
            port=self.ssh_port,
            username=self.ssh_username,
            password=self.ssh_password,
        )
        logger.info(f"[SimulatorService] SSH server on {self.ssh_host}:{self.ssh_port}")

        # 2. Configure management handler
        _ManagementHandler.state_manager = self.state_manager
        _ManagementHandler.ssh_server = self.ssh_server
        _ManagementHandler.device_name = self.device_name
        _ManagementHandler.ssh_port = self.ssh_port
        _ManagementHandler.start_time = time.time()

        # 3. Start HTTP management API
        self._http_server = HTTPServer((self.mgmt_host, self.mgmt_port), _ManagementHandler)
        logger.info(f"[SimulatorService] Management API on {self.mgmt_host}:{self.mgmt_port}")

        # Run HTTP server in daemon thread
        http_thread = threading.Thread(
            target=self._http_server.serve_forever,
            daemon=True,
            name=f"mgmt-api-{self.mgmt_port}",
        )
        http_thread.start()

        logger.info(f"[SimulatorService] {self.device_name} is ready.")
        logger.info(f"  SSH:    {self.ssh_host}:{self.ssh_port} (user={self.ssh_username})")
        logger.info(f"  Mgmt:   http://{self.mgmt_host}:{self.mgmt_port}")
        logger.info(f"  Health: http://{self.mgmt_host}:{self.mgmt_port}/health")

        # 4. Wait for shutdown signal
        self._wait_for_shutdown()

    def _wait_for_shutdown(self) -> None:
        """Block until SIGTERM/SIGINT received."""
        shutdown_event = threading.Event()

        def _handler(signum, frame):
            logger.info(f"[SimulatorService] Received signal {signum}, shutting down...")
            shutdown_event.set()

        signal.signal(signal.SIGTERM, _handler)
        signal.signal(signal.SIGINT, _handler)

        try:
            while not shutdown_event.is_set():
                shutdown_event.wait(timeout=1.0)
        except KeyboardInterrupt:
            pass

        self._cleanup()

    def _cleanup(self) -> None:
        """Clean up resources."""
        logger.info(f"[SimulatorService] Cleaning up {self.device_name}...")
        if self.ssh_server:
            self.ssh_server.stop()
        if self._http_server:
            self._http_server.shutdown()
        logger.info(f"[SimulatorService] {self.device_name} stopped.")


# ────────────────────────────────────────────────────
# CLI Entry Point
# ────────────────────────────────────────────────────

def main():
    """CLI entry point for standalone simulator process."""
    parser = argparse.ArgumentParser(
        description="NetworkAgentDemo — Standalone Switch Simulator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m src.simulator.simulator_service --ssh-port 2222 --mgmt-port 9222
  python -m src.simulator.simulator_service --device-name "Core-SW-01" --ssh-port 2223 --mgmt-port 9223 --username admin --password cisco123
        """,
    )
    parser.add_argument("--device-name", default="Sim-SW-01", help="Device display name")
    parser.add_argument("--ssh-host", default="0.0.0.0", help="SSH listen address")
    parser.add_argument("--ssh-port", type=int, default=2222, help="SSH listen port")
    parser.add_argument("--mgmt-host", default="0.0.0.0", help="Management API listen address")
    parser.add_argument("--mgmt-port", type=int, default=9222, help="Management API listen port")
    parser.add_argument("--username", default="admin", help="SSH username")
    parser.add_argument("--password", default="switch123", help="SSH password")
    parser.add_argument("--max-connections", type=int, default=5, help="Max concurrent SSH connections")

    args = parser.parse_args()

    # Configure loguru
    logger.remove()
    logger.add(
        sys.stderr,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
        level="INFO",
    )

    service = SimulatorService(
        device_name=args.device_name,
        ssh_host=args.ssh_host,
        ssh_port=args.ssh_port,
        mgmt_host=args.mgmt_host,
        mgmt_port=args.mgmt_port,
        ssh_username=args.username,
        ssh_password=args.password,
        max_connections=args.max_connections,
    )
    service.start()


if __name__ == "__main__":
    main()
