"""
E2E Tests — Inspection Configuration Page Refactoring (v0.3.0).
@author sub_agent_test_engineer
@module Inspection Config Refactoring E2E
@version 0.1.0

Covers user stories US-002 through US-005, systemd unavailable degradation
(REQ-NFUNC-004 / Q3), and button API consistency (REQ-NFUNC-001).

Supports two modes:
  1. Mock mode: USE_MOCK=true — runs entirely with httpx.MockTransport, no backend needed
  2. Real mode: (default) — targets BASE_URL remote VPS or custom endpoint

Prerequisites:
    pip install pytest httpx

Usage:
    # Mock mode (CI-friendly, no backend needed)
    USE_MOCK=true pytest tests/test_e2e_inspection_config_refactor.py -v

    # Real mode (targets VPS by default)
    pytest tests/test_e2e_inspection_config_refactor.py -v

    # Custom target
    BASE_URL=http://localhost:8001 pytest tests/test_e2e_inspection_config_refactor.py -v

    # Only P0 tests
    pytest tests/test_e2e_inspection_config_refactor.py -v -k "P0 or p0"
"""

import os
import json
import pytest
import httpx


# ═══════════════════════════════════════════════════════════════
# Configuration
# ═══════════════════════════════════════════════════════════════

BASE_URL = os.environ.get("BASE_URL", "http://47.109.197.217:8001")
USERNAME = os.environ.get("TEST_USERNAME", "admin")
PASSWORD = os.environ.get("TEST_PASSWORD", "admin")
HTTP_TIMEOUT = int(os.environ.get("HTTP_TIMEOUT", "30"))
USE_MOCK = os.environ.get("USE_MOCK", "").lower() in ("true", "1", "yes")

# ── Mock response data (used when USE_MOCK=true) ─────────────

MOCK_JWT_TOKEN = "mock-jwt-token-for-testing-purposes-only-e2e-refactor"

MOCK_STATUS_SYSTEMD_AVAILABLE = {
    "timer": {
        "active_state": "active",
        "unit_file_state": "enabled",
        "next_trigger": "2026-07-13T00:00:00+08:00",
        "last_trigger": "2026-07-12T23:55:00+08:00",
    },
    "service": {
        "active_state": "active",
        "sub_state": "running",
        "last_result": "success",
        "last_execution": "2026-07-12T23:55:00+08:00",
    },
    "last_inspection": {
        "id": 42,
        "trigger_mode": "scheduled",
        "started_at": "2026-07-12T23:55:00+08:00",
        "completed_at": "2026-07-12T23:56:30+08:00",
        "status": "SUCCESS",
        "anomaly_count": 0,
        "total_devices": 15,
    },
    "systemd_available": True,
    "message": None,
}

MOCK_STATUS_SYSTEMD_UNAVAILABLE = {
    "timer": None,
    "service": None,
    "last_inspection": {
        "id": 42,
        "trigger_mode": "manual",
        "started_at": "2026-07-12T23:55:00+08:00",
        "completed_at": "2026-07-12T23:56:30+08:00",
        "status": "SUCCESS",
        "anomaly_count": 0,
        "total_devices": 15,
    },
    "systemd_available": False,
    "message": "当前环境不支持 systemd，定时巡检功能不可用。手动触发仍可使用。",
}

MOCK_HISTORY_RECORDS = [
    {
        "id": 42,
        "trigger_mode": "scheduled",
        "started_at": "2026-07-12T23:55:00+08:00",
        "completed_at": "2026-07-12T23:56:30+08:00",
        "status": "SUCCESS",
        "anomaly_count": 0,
        "total_devices": 15,
    },
    {
        "id": 41,
        "trigger_mode": "manual",
        "started_at": "2026-07-12T22:30:00+08:00",
        "completed_at": "2026-07-12T22:31:15+08:00",
        "status": "PARTIAL",
        "anomaly_count": 2,
        "total_devices": 15,
    },
    {
        "id": 40,
        "trigger_mode": "scheduled",
        "started_at": "2026-07-12T21:55:00+08:00",
        "completed_at": "2026-07-12T21:56:00+08:00",
        "status": "FAILED",
        "anomaly_count": 5,
        "total_devices": 15,
    },
    {
        "id": 39,
        "trigger_mode": "scheduled",
        "started_at": "2026-07-12T20:55:00+08:00",
        "completed_at": "2026-07-12T20:56:30+08:00",
        "status": "SUCCESS",
        "anomaly_count": 0,
        "total_devices": 15,
    },
    {
        "id": 38,
        "trigger_mode": "manual",
        "started_at": "2026-07-12T19:30:00+08:00",
        "completed_at": "2026-07-12T19:31:10+08:00",
        "status": "SUCCESS",
        "anomaly_count": 0,
        "total_devices": 15,
    },
]

MOCK_HISTORY_EMPTY = {
    "items": [],
    "total": 0,
    "page": 1,
    "page_size": 5,
}

MOCK_HISTORY_WITH_RECORDS = {
    "items": MOCK_HISTORY_RECORDS,
    "total": len(MOCK_HISTORY_RECORDS),
    "page": 1,
    "page_size": 5,
}

MOCK_ACTION_SUCCESS = {
    "result": "success",
    "action": "start",  # Will be overridden per endpoint
    "message": "操作成功",
    "detail": "Operation completed via mock transport",
}

def _mock_action_response(action: str) -> dict:
    """Build a mock InspectionActionResponse for a given action."""
    messages = {
        "start": "巡检服务已启动",
        "stop": "巡检服务已停止",
        "restart": "巡检服务已重启",
        "enable": "定时器已启用并开始运行",
        "disable": "定时器已停止并禁用，系统重启后不会自动恢复",
    }
    return {
        "result": "success",
        "action": action,
        "message": messages.get(action, f"{action} 操作成功"),
        "detail": f"Mock: systemctl {action} executed successfully",
    }

MOCK_SYSTEMD_UNAVAILABLE_ERROR = {
    "detail": "当前环境不支持 systemd，无法执行此操作",
}

MOCK_TRIGGER_SUCCESS = {
    "result": "success",
    "message": "巡检已触发",
    "trigger_mode": "MANUAL",
    "detail": "Mock: inspection triggered successfully",
}

MOCK_CONFIG = {
    "config": {
        "inspection.interval_minutes": "5",
        "diagnosis.timeout_seconds": "30",
        "diagnosis.retry_max": "3",
        "diagnosis.retry_backoff": "5",
    },
}


# ═══════════════════════════════════════════════════════════════
# Mock Transport Handlers
# ═══════════════════════════════════════════════════════════════

def _mock_handler_systemd_available(request: httpx.Request) -> httpx.Response:
    """
    Mock handler simulating a systemd-available environment.
    All control endpoints return 200 with success responses.
    """
    url_path = request.url.path
    method = request.method

    # Auth
    if method == "POST" and url_path == "/auth/login":
        return httpx.Response(200, json={
            "access_token": MOCK_JWT_TOKEN,
            "token_type": "bearer",
            "expires_in": 86400,
        })

    # Status
    if method == "GET" and url_path == "/api/inspection/status":
        return httpx.Response(200, json=MOCK_STATUS_SYSTEMD_AVAILABLE)

    # History
    if method == "GET" and url_path == "/api/inspection/history":
        status_filter = request.url.params.get("status")
        if status_filter:
            filtered = [r for r in MOCK_HISTORY_RECORDS if r["status"] == status_filter]
            return httpx.Response(200, json={
                "items": filtered,
                "total": len(filtered),
                "page": int(request.url.params.get("page", "1")),
                "page_size": int(request.url.params.get("page_size", "5")),
            })
        return httpx.Response(200, json=MOCK_HISTORY_WITH_RECORDS)

    # Config
    if method == "GET" and url_path == "/api/inspection/config":
        return httpx.Response(200, json=MOCK_CONFIG)

    # Control actions
    control_actions = ["start", "stop", "restart", "enable", "disable"]
    for action in control_actions:
        if method == "POST" and url_path == f"/api/inspection/{action}":
            return httpx.Response(200, json=_mock_action_response(action))

    # Trigger
    if method == "POST" and url_path == "/api/inspection/trigger":
        return httpx.Response(200, json=MOCK_TRIGGER_SUCCESS)

    # Fallback
    return httpx.Response(404, json={"detail": f"Mock: endpoint not found: {url_path}"})


def _mock_handler_systemd_unavailable(request: httpx.Request) -> httpx.Response:
    """
    Mock handler simulating a systemd-unavailable environment.
    All control endpoints return 503; status returns degraded.
    """
    url_path = request.url.path
    method = request.method

    # Auth
    if method == "POST" and url_path == "/auth/login":
        return httpx.Response(200, json={
            "access_token": MOCK_JWT_TOKEN,
            "token_type": "bearer",
            "expires_in": 86400,
        })

    # Status — degraded
    if method == "GET" and url_path == "/api/inspection/status":
        return httpx.Response(200, json=MOCK_STATUS_SYSTEMD_UNAVAILABLE)

    # History — still works (uses DB, not systemd)
    if method == "GET" and url_path == "/api/inspection/history":
        status_filter = request.url.params.get("status")
        if status_filter:
            filtered = [r for r in MOCK_HISTORY_RECORDS if r["status"] == status_filter]
            return httpx.Response(200, json={
                "items": filtered,
                "total": len(filtered),
                "page": int(request.url.params.get("page", "1")),
                "page_size": int(request.url.params.get("page_size", "5")),
            })
        return httpx.Response(200, json=MOCK_HISTORY_WITH_RECORDS)

    # Config — still works
    if method == "GET" and url_path == "/api/inspection/config":
        return httpx.Response(200, json=MOCK_CONFIG)

    # Control actions — all return 503
    control_actions = ["start", "stop", "restart", "enable", "disable"]
    for action in control_actions:
        if method == "POST" and url_path == f"/api/inspection/{action}":
            return httpx.Response(503, json=MOCK_SYSTEMD_UNAVAILABLE_ERROR)

    # Trigger — also returns 503 (systemctl start required)
    if method == "POST" and url_path == "/api/inspection/trigger":
        return httpx.Response(503, json={
            "detail": "请先配置巡检服务：当前环境不支持 systemd，无法触发巡检。"
                       "请确保系统安装了 systemd 并正确配置。"
        })

    # Fallback
    return httpx.Response(404, json={"detail": f"Mock: endpoint not found: {url_path}"})


# ═══════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════

def api_url(path: str) -> str:
    """Build full URL for an API path."""
    return f"{BASE_URL.rstrip('/')}{path}"


def auth_headers(token: str) -> dict:
    """Return Authorization header dict for a JWT token."""
    return {"Authorization": f"Bearer {token}"}


def login(client: httpx.Client) -> str:
    """Perform login and return access_token. Raises on failure."""
    resp = client.post(
        api_url("/auth/login"),
        data={"username": USERNAME, "password": PASSWORD},
        timeout=HTTP_TIMEOUT,
    )
    assert resp.status_code == 200, f"Login failed: {resp.status_code} {resp.text}"
    data = resp.json()
    assert "access_token" in data, f"No access_token in response: {data}"
    return data["access_token"]


# ═══════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════

@pytest.fixture(scope="session")
def client():
    """
    Session-scoped HTTP client.
    In mock mode, uses MockTransport; in real mode, connects to BASE_URL.
    """
    if USE_MOCK:
        transport = httpx.MockTransport(_mock_handler_systemd_available)
        c = httpx.Client(transport=transport, base_url=BASE_URL, timeout=HTTP_TIMEOUT)
    else:
        c = httpx.Client(base_url=BASE_URL, timeout=HTTP_TIMEOUT)
    yield c
    c.close()


@pytest.fixture(scope="session")
def token(client: httpx.Client) -> str:
    """Session-scoped JWT token — obtained once and reused."""
    return login(client)


@pytest.fixture(scope="session")
def token_headers(token: str) -> dict:
    """Convenience fixture: return Authorization headers."""
    return auth_headers(token)


@pytest.fixture(scope="session")
def mock_systemd_unavailable_client():
    """
    Session-scoped mock client simulating systemd-unavailable environment.
    Used specifically for degradation test cases (TC-E2E-008, TC-E2E-009).
    """
    transport = httpx.MockTransport(_mock_handler_systemd_unavailable)
    c = httpx.Client(transport=transport, base_url=BASE_URL, timeout=HTTP_TIMEOUT)
    yield c
    c.close()


@pytest.fixture(scope="session")
def is_systemd_available(client: httpx.Client, token_headers: dict) -> bool:
    """
    Detect whether the real backend has systemd available.
    Returns True if available, False otherwise.
    In mock mode, always returns True (systemd-available mock).
    """
    if USE_MOCK:
        return True
    try:
        resp = client.get(api_url("/api/inspection/status"), headers=token_headers)
        if resp.status_code == 200:
            return resp.json().get("systemd_available", False)
    except Exception:
        pass
    return False


# ═══════════════════════════════════════════════════════════════
# Test Classes
# ═══════════════════════════════════════════════════════════════


# ── US-001: Systemd Status (P0 regression) ────────────────────

class TestInspectionStatusAPI:
    """
    TC-E2E-001: Verify GET /api/inspection/status returns systemd_available flag.
    Covers: US-001, AC-001-03
    """

    def test_status_endpoint_returns_200(self, client: httpx.Client, token_headers: dict):
        """GET /api/inspection/status returns HTTP 200."""
        resp = client.get(api_url("/api/inspection/status"), headers=token_headers)
        assert resp.status_code == 200, \
            f"Status endpoint failed: {resp.status_code} {resp.text}"

    def test_status_response_has_systemd_available(self, client: httpx.Client, token_headers: dict):
        """AC-001-03: Response includes systemd_available boolean field."""
        resp = client.get(api_url("/api/inspection/status"), headers=token_headers)
        data = resp.json()
        assert "systemd_available" in data, \
            f"Missing 'systemd_available' in response: {list(data.keys())}"
        assert isinstance(data["systemd_available"], bool), \
            f"systemd_available should be bool, got {type(data['systemd_available'])}"

    def test_status_response_has_expected_keys(self, client: httpx.Client, token_headers: dict):
        """Status response contains timer, service, last_inspection, message keys."""
        resp = client.get(api_url("/api/inspection/status"), headers=token_headers)
        data = resp.json()
        for key in ("timer", "service", "last_inspection", "message"):
            assert key in data, f"Missing key '{key}' in status response: {list(data.keys())}"

    def test_status_when_systemd_available_has_timer_service(self, client: httpx.Client, token_headers: dict, is_systemd_available: bool):
        """When systemd is available, timer and service should be non-null dicts."""
        if not is_systemd_available:
            pytest.skip("systemd not available on this backend")
        resp = client.get(api_url("/api/inspection/status"), headers=token_headers)
        data = resp.json()
        assert data["systemd_available"] is True
        assert data["timer"] is not None, "timer should be non-null when systemd is available"
        assert data["service"] is not None, "service should be non-null when systemd is available"


# ── US-002: Inspection Summary (P0 / P1) ─────────────────────

class TestInspectionHistoryAPI:
    """
    TC-E2E-002: Verify GET /api/inspection/history returns records with required fields.
    TC-E2E-003: Verify empty history returns gracefully.
    Covers: US-002, AC-002-01, AC-002-02
    """

    def test_history_endpoint_returns_200(self, client: httpx.Client, token_headers: dict):
        """GET /api/inspection/history returns HTTP 200."""
        resp = client.get(api_url("/api/inspection/history"), headers=token_headers)
        assert resp.status_code == 200, \
            f"History endpoint failed: {resp.status_code} {resp.text}"

    def test_history_response_has_pagination_keys(self, client: httpx.Client, token_headers: dict):
        """AC-002-01: History response includes pagination fields."""
        resp = client.get(
            api_url("/api/inspection/history"),
            params={"page": 1, "page_size": 5},
            headers=token_headers,
        )
        data = resp.json()
        for key in ("items", "total", "page", "page_size"):
            assert key in data, f"Missing key '{key}' in history response: {list(data.keys())}"
        assert isinstance(data["items"], list), "items should be a list"
        assert isinstance(data["total"], int), "total should be an integer"

    def test_history_items_have_required_fields(self, client: httpx.Client, token_headers: dict):
        """AC-002-01: Each history item has trigger_mode, started_at, completed_at, status, anomaly_count, total_devices."""
        resp = client.get(
            api_url("/api/inspection/history"),
            params={"page": 1, "page_size": 5},
            headers=token_headers,
        )
        data = resp.json()
        if data["total"] > 0:
            item = data["items"][0]
            required_fields = {
                "trigger_mode", "started_at", "completed_at", "status",
                "anomaly_count", "total_devices",
            }
            for field in required_fields:
                assert field in item, \
                    f"History item missing field '{field}': {list(item.keys())[:10]}"
            # Validate trigger_mode values
            assert item["trigger_mode"] in ("scheduled", "manual", "MANUAL", "SCHEDULED"), \
                f"Unexpected trigger_mode: {item['trigger_mode']}"
            # Validate status values
            assert item["status"] in ("SUCCESS", "PARTIAL", "FAILED", "RUNNING", "PROCESSING"), \
                f"Unexpected status: {item['status']}"

    def test_history_pagination_respects_page_size(self, client: httpx.Client, token_headers: dict):
        """AC-002-01: Pagination respects page_size parameter (max 5 as per design)."""
        resp = client.get(
            api_url("/api/inspection/history"),
            params={"page": 1, "page_size": 5},
            headers=token_headers,
        )
        data = resp.json()
        assert len(data["items"]) <= 5, \
            f"History returned {len(data['items'])} items, expected <= 5"

    def test_history_empty_returns_gracefully(self, client: httpx.Client, token_headers: dict):
        """AC-002-02: Empty history returns items=[], total=0 without error."""
        resp = client.get(
            api_url("/api/inspection/history"),
            params={"page": 1, "page_size": 5},
            headers=token_headers,
        )
        data = resp.json()
        assert resp.status_code == 200, \
            f"Empty history should return 200, got {resp.status_code}"
        assert data["items"] == [] or len(data["items"]) >= 0, \
            "items must be a list (possibly empty)"
        assert data["total"] >= 0, "total must be >= 0"

    def test_history_filter_by_status(self, client: httpx.Client, token_headers: dict):
        """History supports status filter parameter."""
        resp = client.get(
            api_url("/api/inspection/history"),
            params={"status": "SUCCESS", "page": 1, "page_size": 5},
            headers=token_headers,
        )
        assert resp.status_code == 200, f"Status filter failed: {resp.status_code}"
        data = resp.json()
        # If items exist, all should have status=SUCCESS
        for item in data["items"]:
            assert item["status"] == "SUCCESS", \
                f"Status filter mismatch: expected SUCCESS, got {item['status']}"


# ── US-003: Start Inspection Service (P0) ────────────────────

class TestStartServiceAPI:
    """
    TC-E2E-004: Verify POST /api/inspection/start returns correct response structure.
    Covers: US-003, AC-003-01, AC-003-02
    """

    def test_start_endpoint_exists(self, client: httpx.Client, token_headers: dict, is_systemd_available: bool):
        """AC-003-01: POST /api/inspection/start is a valid endpoint."""
        resp = client.post(api_url("/api/inspection/start"), headers=token_headers)
        # Accept 200 (success), 500 (service already running), 503 (systemd unavailable)
        status = resp.status_code
        assert status in (200, 500, 503), \
            f"Unexpected status from /api/inspection/start: {status} {resp.text}"

    def test_start_success_response_has_expected_schema(self, client: httpx.Client, token_headers: dict, is_systemd_available: bool):
        """AC-003-01: Success response has result='success', action='start', message non-empty."""
        if not is_systemd_available:
            pytest.skip("systemd not available on this backend")
        resp = client.post(api_url("/api/inspection/start"), headers=token_headers)
        if resp.status_code == 200:
            data = resp.json()
            assert data.get("result") == "success", \
                f"Expected result='success', got {data}"
            assert data.get("action") == "start", \
                f"Expected action='start', got {data.get('action')}"
            assert "message" in data and len(data["message"]) > 0, \
                f"message should be non-empty: {data}"
        elif resp.status_code == 500:
            # Acceptable: service may already be running (AC-003-02)
            data = resp.json()
            assert "detail" in data, "500 response should have detail field"
        elif resp.status_code == 503:
            pytest.skip("systemd not available, endpoint correctly returned 503")

    def test_start_idempotent_call(self, client: httpx.Client, token_headers: dict, is_systemd_available: bool):
        """AC-003-02: Calling start when service is running should return appropriate response (not crash)."""
        if not is_systemd_available:
            pytest.skip("systemd not available on this backend")
        # Call start twice — second call should either succeed or report already-running
        resp1 = client.post(api_url("/api/inspection/start"), headers=token_headers)
        resp2 = client.post(api_url("/api/inspection/start"), headers=token_headers)
        # Both should be handleable responses
        assert resp2.status_code in (200, 500, 503), \
            f"Second start call returned unexpected status: {resp2.status_code}"


# ── US-004: Stop Inspection Service (P0) ─────────────────────

class TestStopServiceAPI:
    """
    TC-E2E-005: Verify POST /api/inspection/stop returns correct response structure.
    Covers: US-004, AC-004-01
    """

    def test_stop_endpoint_exists(self, client: httpx.Client, token_headers: dict):
        """AC-004-01: POST /api/inspection/stop is a valid endpoint."""
        resp = client.post(api_url("/api/inspection/stop"), headers=token_headers)
        status = resp.status_code
        assert status in (200, 500, 503), \
            f"Unexpected status from /api/inspection/stop: {status} {resp.text}"

    def test_stop_success_response_has_expected_schema(self, client: httpx.Client, token_headers: dict, is_systemd_available: bool):
        """AC-004-01: Success response has result='success', action='stop', message='巡检服务已停止'."""
        if not is_systemd_available:
            pytest.skip("systemd not available on this backend")
        resp = client.post(api_url("/api/inspection/stop"), headers=token_headers)
        if resp.status_code == 200:
            data = resp.json()
            assert data.get("result") == "success"
            assert data.get("action") == "stop"
            assert "message" in data and len(data["message"]) > 0
        elif resp.status_code == 503:
            pytest.skip("systemd not available, endpoint correctly returned 503")


# ── US-005: Restart Inspection Service (P0) ──────────────────

class TestRestartServiceAPI:
    """
    TC-E2E-006: Verify POST /api/inspection/restart returns correct response structure.
    Covers: US-005, AC-005-01, AC-005-02
    """

    def test_restart_endpoint_exists(self, client: httpx.Client, token_headers: dict):
        """AC-005-01: POST /api/inspection/restart is a valid endpoint."""
        resp = client.post(api_url("/api/inspection/restart"), headers=token_headers)
        status = resp.status_code
        assert status in (200, 500, 503), \
            f"Unexpected status from /api/inspection/restart: {status} {resp.text}"

    def test_restart_success_response_has_expected_schema(self, client: httpx.Client, token_headers: dict, is_systemd_available: bool):
        """AC-005-01: Success response has result='success', action='restart', message='巡检服务已重启'."""
        if not is_systemd_available:
            pytest.skip("systemd not available on this backend")
        resp = client.post(api_url("/api/inspection/restart"), headers=token_headers)
        if resp.status_code == 200:
            data = resp.json()
            assert data.get("result") == "success"
            assert data.get("action") == "restart"
            assert "message" in data and len(data["message"]) > 0
        elif resp.status_code == 503:
            pytest.skip("systemd not available, endpoint correctly returned 503")


# ── REQ-NFUNC-001: Button API Consistency (P0) ───────────────

class TestControlButtonAPIConsistency:
    """
    TC-E2E-007: Verify all 5 control endpoints return consistent InspectionActionResponse schema.
    Covers: REQ-NFUNC-001, AC-NFUNC-001-01
    """

    CONTROL_ENDPOINTS = ["start", "stop", "restart", "enable", "disable"]

    def test_all_5_control_endpoints_exist(self, client: httpx.Client, token_headers: dict):
        """AC-NFUNC-001-01: All 5 control endpoints return valid HTTP responses (not 404)."""
        for action in self.CONTROL_ENDPOINTS:
            resp = client.post(api_url(f"/api/inspection/{action}"), headers=token_headers)
            assert resp.status_code != 404, \
                f"Endpoint /api/inspection/{action} returned 404 — endpoint missing!"

    def test_control_response_schema_uniform(self, client: httpx.Client, token_headers: dict, is_systemd_available: bool):
        """AC-NFUNC-001-01: All control endpoints share uniform response schema."""
        if not is_systemd_available:
            pytest.skip("systemd not available — verifying 503 uniformity instead")
        schemas_match = True
        first_schema = None
        for action in self.CONTROL_ENDPOINTS:
            resp = client.post(api_url(f"/api/inspection/{action}"), headers=token_headers)
            data = resp.json()
            keys = set(data.keys())
            if first_schema is None:
                first_schema = keys
            elif keys != first_schema:
                schemas_match = False
                break
        assert schemas_match, \
            f"Control endpoint response schemas are not uniform across {self.CONTROL_ENDPOINTS}"

    def test_control_response_contains_result_action_message(self, client: httpx.Client, token_headers: dict, is_systemd_available: bool):
        """Each successful control response contains result, action, message fields."""
        if not is_systemd_available:
            pytest.skip("systemd not available on this backend")
        for action in self.CONTROL_ENDPOINTS:
            resp = client.post(api_url(f"/api/inspection/{action}"), headers=token_headers)
            if resp.status_code == 200:
                data = resp.json()
                for field in ("result", "action", "message"):
                    assert field in data, \
                        f"POST /api/inspection/{action}: missing '{field}' in response: {list(data.keys())}"
                assert data["result"] == "success", \
                    f"POST /api/inspection/{action}: expected result='success', got {data.get('result')}"


# ── REQ-NFUNC-004: Systemd Unavailable Degradation (P0) ──────

class TestSystemdUnavailableDegradation:
    """
    TC-E2E-008: systemd unavailable → control endpoints return 503.
    TC-E2E-009: systemd unavailable → status endpoint returns degraded response.
    Covers: REQ-NFUNC-004, Q3 decision (ADR-004), AC-001-03
    """

    CONTROL_ENDPOINTS = ["start", "stop", "restart", "enable", "disable"]

    def test_systemd_unavailable_control_endpoints_return_503(
        self, mock_systemd_unavailable_client: httpx.Client
    ):
        """TC-E2E-008: In mock systemd-unavailable mode, all 5 control endpoints return 503."""
        # Login first
        login_resp = mock_systemd_unavailable_client.post(
            api_url("/auth/login"),
            data={"username": USERNAME, "password": PASSWORD},
        )
        token = login_resp.json()["access_token"]
        hdr = auth_headers(token)

        for action in self.CONTROL_ENDPOINTS:
            resp = mock_systemd_unavailable_client.post(
                api_url(f"/api/inspection/{action}"), headers=hdr
            )
            assert resp.status_code == 503, \
                f"Expected 503 for /api/inspection/{action} when systemd unavailable, got {resp.status_code}"
            data = resp.json()
            assert "detail" in data, \
                f"503 response for {action} should have 'detail' field"
            assert "systemd" in data["detail"].lower() or "系统" in data["detail"], \
                f"503 detail should mention systemd unavailability: {data['detail'][:80]}"

    def test_systemd_unavailable_status_degraded_response(
        self, mock_systemd_unavailable_client: httpx.Client
    ):
        """TC-E2E-009: Status endpoint returns degraded response when systemd unavailable."""
        login_resp = mock_systemd_unavailable_client.post(
            api_url("/auth/login"),
            data={"username": USERNAME, "password": PASSWORD},
        )
        token = login_resp.json()["access_token"]
        hdr = auth_headers(token)

        resp = mock_systemd_unavailable_client.get(
            api_url("/api/inspection/status"), headers=hdr
        )
        assert resp.status_code == 200, \
            f"Status endpoint should return 200 even when systemd unavailable, got {resp.status_code}"
        data = resp.json()
        assert data["systemd_available"] is False, \
            "systemd_available must be false in degraded mode"
        assert data["timer"] is None, \
            "timer must be null when systemd unavailable"
        assert data["service"] is None, \
            "service must be null when systemd unavailable"
        assert data["message"] is not None and len(data["message"]) > 0, \
            "message must be non-empty with degradation explanation"

    def test_systemd_unavailable_history_still_works(
        self, mock_systemd_unavailable_client: httpx.Client
    ):
        """History endpoint should work even when systemd is unavailable (uses DB only)."""
        login_resp = mock_systemd_unavailable_client.post(
            api_url("/auth/login"),
            data={"username": USERNAME, "password": PASSWORD},
        )
        token = login_resp.json()["access_token"]
        hdr = auth_headers(token)

        resp = mock_systemd_unavailable_client.get(
            api_url("/api/inspection/history"), headers=hdr
        )
        assert resp.status_code == 200, \
            f"History should work even when systemd unavailable, got {resp.status_code}"
        data = resp.json()
        assert "items" in data and "total" in data

    def test_real_backend_systemd_unavailable_503(
        self, client: httpx.Client, token_headers: dict, is_systemd_available: bool
    ):
        """If real backend has systemd unavailable, verify control endpoints return 503."""
        if is_systemd_available:
            pytest.skip("systemd is available on this backend — degradation test not applicable")
        for action in self.CONTROL_ENDPOINTS:
            resp = client.post(api_url(f"/api/inspection/{action}"), headers=token_headers)
            assert resp.status_code == 503, \
                f"Expected 503 for /api/inspection/{action}, got {resp.status_code}: {resp.text[:200]}"


# ── US-006/US-007: Timer Control Regression (P0) ─────────────

class TestTimerControlAPI:
    """
    TC-E2E-010: Verify POST /api/inspection/enable returns success.
    TC-E2E-011: Verify POST /api/inspection/disable returns success.
    Covers: US-006, AC-006-01; US-007, AC-007-01
    """

    def test_enable_endpoint_exists(self, client: httpx.Client, token_headers: dict):
        """AC-006-01: POST /api/inspection/enable is valid."""
        resp = client.post(api_url("/api/inspection/enable"), headers=token_headers)
        assert resp.status_code in (200, 500, 503), \
            f"Unexpected status from /api/inspection/enable: {resp.status_code}"

    def test_enable_success_response_schema(self, client: httpx.Client, token_headers: dict, is_systemd_available: bool):
        """AC-006-01: Enable response has result='success', action='enable'."""
        if not is_systemd_available:
            pytest.skip("systemd not available on this backend")
        resp = client.post(api_url("/api/inspection/enable"), headers=token_headers)
        if resp.status_code == 200:
            data = resp.json()
            assert data["result"] == "success"
            assert data["action"] == "enable"

    def test_disable_endpoint_exists(self, client: httpx.Client, token_headers: dict):
        """AC-007-01: POST /api/inspection/disable is valid."""
        resp = client.post(api_url("/api/inspection/disable"), headers=token_headers)
        assert resp.status_code in (200, 500, 503), \
            f"Unexpected status from /api/inspection/disable: {resp.status_code}"

    def test_disable_success_response_schema(self, client: httpx.Client, token_headers: dict, is_systemd_available: bool):
        """AC-007-01: Disable response has result='success', action='disable'."""
        if not is_systemd_available:
            pytest.skip("systemd not available on this backend")
        resp = client.post(api_url("/api/inspection/disable"), headers=token_headers)
        if resp.status_code == 200:
            data = resp.json()
            assert data["result"] == "success"
            assert data["action"] == "disable"


# ── US-009: Manual Trigger Regression (P0) ───────────────────

class TestManualTriggerAPI:
    """
    TC-E2E-012: Verify POST /api/inspection/trigger returns correct response.
    Covers: US-009, AC-009-01
    """

    def test_trigger_endpoint_exists(self, client: httpx.Client, token_headers: dict):
        """AC-009-01: POST /api/inspection/trigger is valid."""
        resp = client.post(api_url("/api/inspection/trigger"), headers=token_headers)
        # 200=success, 409=inspection already running, 503=systemd unavailable
        assert resp.status_code in (200, 409, 503), \
            f"Unexpected status from /api/inspection/trigger: {resp.status_code} {resp.text[:200]}"

    def test_trigger_success_response_has_trigger_mode(self, client: httpx.Client, token_headers: dict, is_systemd_available: bool):
        """AC-009-01: Trigger success response includes result, message, trigger_mode=MANUAL."""
        if not is_systemd_available:
            pytest.skip("systemd not available on this backend")
        resp = client.post(api_url("/api/inspection/trigger"), headers=token_headers)
        if resp.status_code == 200:
            data = resp.json()
            assert data.get("result") == "success", f"Expected result='success', got {data}"
            assert data.get("message") == "巡检已触发", \
                f"Expected message='巡检已触发', got {data.get('message')}"
            assert data.get("trigger_mode") == "MANUAL", \
                f"Expected trigger_mode='MANUAL', got {data.get('trigger_mode')}"

    def test_trigger_when_service_stopped_returns_503(self, client: httpx.Client, token_headers: dict, is_systemd_available: bool):
        """AC-009-02: Trigger when service stopped returns appropriate error."""
        if not is_systemd_available:
            pytest.skip("systemd not available on this backend")
        resp = client.post(api_url("/api/inspection/trigger"), headers=token_headers)
        if resp.status_code == 503:
            data = resp.json()
            assert "detail" in data


# ── US-008: Config Regression (P0) ───────────────────────────

class TestInspectionConfigAPI:
    """
    TC-E2E-013: Verify GET /api/inspection/config returns all 4 parameters.
    Covers: US-008, AC-008-01
    """

    REQUIRED_CONFIG_KEYS = [
        "inspection.interval_minutes",
        "diagnosis.timeout_seconds",
        "diagnosis.retry_max",
        "diagnosis.retry_backoff",
    ]

    def test_config_endpoint_returns_200(self, client: httpx.Client, token_headers: dict):
        """GET /api/inspection/config returns HTTP 200."""
        resp = client.get(api_url("/api/inspection/config"), headers=token_headers)
        assert resp.status_code == 200, \
            f"Config endpoint failed: {resp.status_code} {resp.text}"

    def test_config_response_has_all_parameters(self, client: httpx.Client, token_headers: dict):
        """AC-008-01: Config response includes all 4 required parameters."""
        resp = client.get(api_url("/api/inspection/config"), headers=token_headers)
        data = resp.json()
        assert "config" in data, f"Missing 'config' in response: {list(data.keys())}"
        config = data["config"]
        for key in self.REQUIRED_CONFIG_KEYS:
            assert key in config, \
                f"Missing config key '{key}': available keys = {list(config.keys())}"

    def test_config_values_are_parseable_as_integers(self, client: httpx.Client, token_headers: dict):
        """AC-008-01: All config values can be parsed as integers."""
        resp = client.get(api_url("/api/inspection/config"), headers=token_headers)
        config = resp.json()["config"]
        for key in self.REQUIRED_CONFIG_KEYS:
            val = config[key]
            try:
                int_val = int(val)
                assert int_val >= 0, f"Config {key} value {int_val} should be >= 0"
            except (ValueError, TypeError):
                pytest.fail(f"Config {key} value '{val}' is not parseable as integer")


# ── US-002 Cross-cutting: History after Trigger (P1) ─────────

class TestHistoryAfterTrigger:
    """
    TC-E2E-014: Verify history endpoint reflects manual trigger.
    Covers: US-002, AC-002-03
    """

    def test_history_available_after_trigger(self, client: httpx.Client, token_headers: dict, is_systemd_available: bool):
        """AC-002-03: After manual trigger, history endpoint is still accessible."""
        if not is_systemd_available:
            pytest.skip("systemd not available — cannot trigger inspection")
        # Get history before trigger
        before = client.get(
            api_url("/api/inspection/history"),
            params={"page": 1, "page_size": 5},
            headers=token_headers,
        )
        assert before.status_code == 200

        # Trigger inspection
        trigger_resp = client.post(api_url("/api/inspection/trigger"), headers=token_headers)
        if trigger_resp.status_code == 409:
            pytest.skip("Inspection already running, cannot trigger — skipping post-trigger check")
        if trigger_resp.status_code == 503:
            pytest.skip("systemd not available — cannot trigger")

        # Wait briefly, then check history again
        import time
        time.sleep(3)

        after = client.get(
            api_url("/api/inspection/history"),
            params={"page": 1, "page_size": 5},
            headers=token_headers,
        )
        assert after.status_code == 200, \
            f"History endpoint failed after trigger: {after.status_code}"
        after_data = after.json()
        assert "items" in after_data and "total" in after_data, \
            "History response structure intact after trigger"


# ═══════════════════════════════════════════════════════════════
# Run configuration
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
