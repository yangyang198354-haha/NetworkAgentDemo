"""
Unit tests for SimulatorService HTTP management API (MOD-DS-016).
@author sub_agent_test_engineer
@covers REQ-FUNC-018, REQ-FUNC-019, REQ-FUNC-020

Tests the _ManagementHandler endpoints using a real HTTP server on a random port.
"""
import json
import threading
import time
import os
import signal
import pytest
from http.server import HTTPServer
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from unittest.mock import patch

from src.simulator.simulator_service import SimulatorService, _ManagementHandler
from src.simulator.state_manager import DeviceStateManager
from src.simulator.ssh_server import SimulatorSSHServer


class _MockSSHServer:
    """Mock SSH server for unit testing without actual paramiko socket binding."""

    def __init__(self):
        self._running = False
        self.host = "0.0.0.0"
        self.port = 0

    @property
    def is_running(self):
        return self._running

    def start(self, host, port, username, password):
        self._running = True
        self.host = host
        self.port = port

    def stop(self):
        self._running = False


@pytest.fixture
def mgmt_server():
    """Start a management HTTP server on a random available port."""
    state = DeviceStateManager(device_name="Test-SW")
    ssh = _MockSSHServer()
    ssh._running = True
    ssh.port = 2222

    # Configure handler class attributes
    _ManagementHandler.state_manager = state
    _ManagementHandler.ssh_server = ssh
    _ManagementHandler.device_name = "Test-SW"
    _ManagementHandler.ssh_port = 2222
    _ManagementHandler.start_time = time.time()

    # Bind to a random available port
    httpd = HTTPServer(("127.0.0.1", 0), _ManagementHandler)
    mgmt_port = httpd.server_port

    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()

    yield mgmt_port, state, ssh

    httpd.shutdown()
    thread.join(timeout=2.0)


def _get(mgmt_port, path):
    """Helper: GET request to management API."""
    url = f"http://127.0.0.1:{mgmt_port}{path}"
    with urlopen(url, timeout=5.0) as resp:
        body = resp.read().decode("utf-8")
        return resp.status, json.loads(body)


def _post(mgmt_port, path, data):
    """Helper: POST request to management API."""
    url = f"http://127.0.0.1:{mgmt_port}{path}"
    body = json.dumps(data).encode("utf-8")
    req = Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    with urlopen(req, timeout=5.0) as resp:
        resp_body = resp.read().decode("utf-8")
        return resp.status, json.loads(resp_body)


def _options(mgmt_port, path):
    """Helper: OPTIONS request to management API."""
    url = f"http://127.0.0.1:{mgmt_port}{path}"
    req = Request(url, method="OPTIONS")
    with urlopen(req, timeout=5.0) as resp:
        return resp.status, dict(resp.headers)


class TestManagementHandlerHealth:
    """Tests for GET /health endpoint."""

    def test_health_returns_200(self, mgmt_server):
        mgmt_port, _, _ = mgmt_server
        status, data = _get(mgmt_port, "/health")
        assert status == 200

    def test_health_returns_status_ok(self, mgmt_server):
        mgmt_port, _, _ = mgmt_server
        _, data = _get(mgmt_port, "/health")
        assert data["status"] == "ok"

    def test_health_returns_device_name(self, mgmt_server):
        mgmt_port, _, _ = mgmt_server
        _, data = _get(mgmt_port, "/health")
        assert data["device_name"] == "Test-SW"

    def test_health_returns_ssh_port(self, mgmt_server):
        mgmt_port, _, _ = mgmt_server
        _, data = _get(mgmt_port, "/health")
        assert data["ssh_port"] == 2222

    def test_health_returns_ssh_running(self, mgmt_server):
        mgmt_port, _, _ = mgmt_server
        _, data = _get(mgmt_port, "/health")
        assert data["ssh_running"] is True

    def test_health_returns_uptime(self, mgmt_server):
        mgmt_port, _, _ = mgmt_server
        _, data = _get(mgmt_port, "/health")
        assert "uptime_seconds" in data
        assert data["uptime_seconds"] >= 0

    def test_health_ssh_running_false_when_no_ssh(self):
        """When ssh_server is None, ssh_running should be False."""
        state = DeviceStateManager(device_name="Test-SW-NOSS")
        _ManagementHandler.state_manager = state
        _ManagementHandler.ssh_server = None
        _ManagementHandler.device_name = "Test-SW-NOSS"
        _ManagementHandler.ssh_port = 0
        _ManagementHandler.start_time = time.time()

        httpd = HTTPServer(("127.0.0.1", 0), _ManagementHandler)
        mgmt_port = httpd.server_port
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()

        try:
            _, data = _get(mgmt_port, "/health")
            assert data["ssh_running"] is False
        finally:
            httpd.shutdown()
            thread.join(timeout=2.0)


class TestManagementHandlerStatus:
    """Tests for GET /status endpoint."""

    def test_status_returns_200(self, mgmt_server):
        mgmt_port, _, _ = mgmt_server
        status, data = _get(mgmt_port, "/status")
        assert status == 200

    def test_status_has_device_name(self, mgmt_server):
        mgmt_port, _, _ = mgmt_server
        _, data = _get(mgmt_port, "/status")
        assert data["device_name"] == "Test-SW"

    def test_status_has_cpu(self, mgmt_server):
        mgmt_port, _, _ = mgmt_server
        _, data = _get(mgmt_port, "/status")
        assert "cpu" in data
        assert "cpu_5s" in data["cpu"]
        assert "cpu_1m" in data["cpu"]
        assert "cpu_5m" in data["cpu"]

    def test_status_has_memory(self, mgmt_server):
        mgmt_port, _, _ = mgmt_server
        _, data = _get(mgmt_port, "/status")
        assert "memory" in data
        assert "total_mb" in data["memory"]
        assert "used_mb" in data["memory"]
        assert "free_mb" in data["memory"]
        assert "usage_pct" in data["memory"]

    def test_status_has_io(self, mgmt_server):
        mgmt_port, _, _ = mgmt_server
        _, data = _get(mgmt_port, "/status")
        assert "io" in data
        assert "read_kbps" in data["io"]
        assert "write_kbps" in data["io"]

    def test_status_500_when_no_state_manager(self):
        """GET /status returns 500 when state_manager is None."""
        _ManagementHandler.state_manager = None
        _ManagementHandler.ssh_server = _MockSSHServer()
        _ManagementHandler.device_name = "Test-SW"
        _ManagementHandler.start_time = time.time()

        httpd = HTTPServer(("127.0.0.1", 0), _ManagementHandler)
        mgmt_port = httpd.server_port
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()

        try:
            with pytest.raises(HTTPError) as exc_info:
                _get(mgmt_port, "/status")
            assert exc_info.value.code == 500
        finally:
            httpd.shutdown()
            thread.join(timeout=2.0)


class TestManagementHandlerPorts:
    """Tests for GET /ports endpoint."""

    def test_ports_returns_200(self, mgmt_server):
        mgmt_port, _, _ = mgmt_server
        status, data = _get(mgmt_port, "/ports")
        assert status == 200

    def test_ports_has_device_name(self, mgmt_server):
        mgmt_port, _, _ = mgmt_server
        _, data = _get(mgmt_port, "/ports")
        assert data["device_name"] == "Test-SW"

    def test_ports_has_8_ports(self, mgmt_server):
        mgmt_port, _, _ = mgmt_server
        _, data = _get(mgmt_port, "/ports")
        assert len(data["ports"]) == 8

    def test_ports_have_required_fields(self, mgmt_server):
        mgmt_port, _, _ = mgmt_server
        _, data = _get(mgmt_port, "/ports")
        for p in data["ports"]:
            assert "name" in p
            assert "status" in p
            assert "vlan" in p
            assert "duplex" in p
            assert "speed" in p
            assert "type" in p
            assert "description" in p

    def test_ports_has_up_ports_detail(self, mgmt_server):
        mgmt_port, _, _ = mgmt_server
        _, data = _get(mgmt_port, "/ports")
        assert "up_ports_detail" in data
        assert isinstance(data["up_ports_detail"], list)
        for detail in data["up_ports_detail"]:
            assert detail["status"] == "up"


class TestManagementHandlerPortConfig:
    """Tests for POST /ports/{name}/config endpoint."""

    def test_port_config_shutdown_success(self, mgmt_server):
        mgmt_port, state, _ = mgmt_server
        status, data = _post(mgmt_port, "/ports/Gi0/1/config", {"action": "shutdown"})
        assert status == 200
        assert data["success"] is True
        assert data["port_name"] == "Gi0/1"
        assert data["action"] == "shutdown"
        # Verify state changed
        assert state.get_port("Gi0/1").enabled is False

    def test_port_config_no_shutdown(self, mgmt_server):
        mgmt_port, state, _ = mgmt_server
        # First shutdown, then no-shutdown
        _post(mgmt_port, "/ports/Gi0/2/config", {"action": "shutdown"})
        _, data = _post(mgmt_port, "/ports/Gi0/2/config", {"action": "no-shutdown"})
        assert data["success"] is True
        assert state.get_port("Gi0/2").enabled is True

    def test_port_config_set_vlan(self, mgmt_server):
        mgmt_port, state, _ = mgmt_server
        _, data = _post(mgmt_port, "/ports/Gi0/3/config",
                        {"action": "set-vlan", "value": "100"})
        assert data["success"] is True
        assert state.get_port("Gi0/3").vlan == 100

    def test_port_config_set_description(self, mgmt_server):
        mgmt_port, state, _ = mgmt_server
        _, data = _post(mgmt_port, "/ports/Gi0/4/config",
                        {"action": "set-description", "value": "API Test"})
        assert data["success"] is True
        assert state.get_port("Gi0/4").description == "API Test"

    def test_port_config_nonexistent(self, mgmt_server):
        mgmt_port, _, _ = mgmt_server
        _, data = _post(mgmt_port, "/ports/Gi0/99/config", {"action": "shutdown"})
        assert data["success"] is False

    def test_port_config_500_when_no_state(self):
        """POST /ports/x/config returns 500 when state is None."""
        _ManagementHandler.state_manager = None
        _ManagementHandler.ssh_server = _MockSSHServer()
        _ManagementHandler.start_time = time.time()

        httpd = HTTPServer(("127.0.0.1", 0), _ManagementHandler)
        mgmt_port = httpd.server_port
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()

        try:
            with pytest.raises(HTTPError) as exc_info:
                _post(mgmt_port, "/ports/Gi0/1/config", {"action": "shutdown"})
            assert exc_info.value.code == 500
        finally:
            httpd.shutdown()
            thread.join(timeout=2.0)


class TestManagementHandlerShutdown:
    """Tests for POST /shutdown endpoint.

    NOTE: The shutdown handler calls os.kill(getpid(), SIGTERM) in a daemon
    thread. We patch os.kill to prevent this from killing the test process."""

    def test_shutdown_returns_200(self, mgmt_server):
        mgmt_port, _, _ = mgmt_server
        with patch("os.kill") as mock_kill:
            status, data = _post(mgmt_port, "/shutdown", {})
            # Give the background thread time to fire
            time.sleep(0.5)
            assert status == 200
            assert "shutting down" in data.get("message", "").lower()
            # Verify os.kill was called (but patched to not actually kill)
            mock_kill.assert_called_once()


class TestManagementHandlerErrors:
    """Tests for error handling - 404, etc."""

    def test_unknown_route_returns_404(self, mgmt_server):
        mgmt_port, _, _ = mgmt_server
        with pytest.raises(HTTPError) as exc_info:
            _get(mgmt_port, "/nonexistent")
        assert exc_info.value.code == 404

    def test_unknown_post_route_returns_404(self, mgmt_server):
        mgmt_port, _, _ = mgmt_server
        with pytest.raises(HTTPError) as exc_info:
            _post(mgmt_port, "/bogus/route", {"x": 1})
        assert exc_info.value.code == 404


class TestManagementHandlerCORS:
    """Tests for CORS preflight OPTIONS."""

    def test_options_returns_200(self, mgmt_server):
        mgmt_port, _, _ = mgmt_server
        status, headers = _options(mgmt_port, "/health")
        assert status == 200

    def test_options_has_cors_origin(self, mgmt_server):
        mgmt_port, _, _ = mgmt_server
        _, headers = _options(mgmt_port, "/health")
        assert headers.get("Access-Control-Allow-Origin") == "*"

    def test_options_has_cors_methods(self, mgmt_server):
        mgmt_port, _, _ = mgmt_server
        _, headers = _options(mgmt_port, "/health")
        allow_methods = headers.get("Access-Control-Allow-Methods", "")
        assert "GET" in allow_methods
        assert "POST" in allow_methods
        assert "OPTIONS" in allow_methods

    def test_options_has_cors_headers(self, mgmt_server):
        mgmt_port, _, _ = mgmt_server
        _, headers = _options(mgmt_port, "/health")
        assert "Content-Type" in headers.get("Access-Control-Allow-Headers", "")


class TestSimulatorServiceInit:
    """Tests for SimulatorService construction."""

    def test_creates_state_manager(self):
        svc = SimulatorService(device_name="InitTest")
        assert svc.state_manager is not None
        assert svc.state_manager.device_name == "InitTest"

    def test_creates_ssh_server(self):
        svc = SimulatorService(device_name="InitTest")
        assert svc.ssh_server is not None
        assert isinstance(svc.ssh_server, SimulatorSSHServer)

    def test_default_ports(self):
        svc = SimulatorService()
        assert svc.ssh_port == 2222
        assert svc.mgmt_port == 9222

    def test_custom_ports(self):
        svc = SimulatorService(ssh_port=3333, mgmt_port=9333)
        assert svc.ssh_port == 3333
        assert svc.mgmt_port == 9333

    def test_default_credentials(self):
        svc = SimulatorService()
        assert svc.ssh_username == "admin"
        assert svc.ssh_password == "switch123"
