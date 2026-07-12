"""
Integration tests for v0.2.0 inspection systemd refactoring.
Tests MOD-WEB-001 (inspection_router) + MOD-INSP-001/002 + MOD-WEB-004 collaboration.
@author sub_agent_test_engineer
@covers US-INSP-001~007, all INT test cases
@test_level INT
"""
import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

# ── Safe import: bypass api/__init__.py which triggers all other routers ──
# Use importlib to load inspection_router module directly.
import importlib
import importlib.util
import importlib.machinery

_insp_router_path = _project_root / "src" / "api" / "inspection_router.py"
_spec = importlib.util.spec_from_file_location(
    "src.api.inspection_router",
    str(_insp_router_path),
)
_inspection_router_mod = importlib.util.module_from_spec(_spec)

# The module imports from src.api.dependencies, so we must also provide that
# without triggering api/__init__.py chain.
_dep_path = _project_root / "src" / "api" / "dependencies.py"
_dep_spec = importlib.util.spec_from_file_location(
    "src.api.dependencies",
    str(_dep_path),
)
# Pre-load dependencies module with mocked auth_service
import unittest.mock as _um
_mock_auth_svc = _um.MagicMock()
_mock_auth_svc.get_user_from_token = _um.MagicMock(return_value=None)
sys.modules["src.services"] = _um.MagicMock()
sys.modules["src.services.auth_service"] = _mock_auth_svc
sys.modules["jose"] = _um.MagicMock()

# Load dependencies module through its spec
_dep_mod = importlib.util.module_from_spec(_dep_spec)
sys.modules["src.api.dependencies"] = _dep_mod
_dep_spec.loader.exec_module(_dep_mod)

# Also pre-load api/__init__.py mocks to satisfy imported references
# (inspection_router.py imports nothing from __init__.py directly)
sys.modules["src.api"] = _um.MagicMock()
sys.modules["src.api.inspection_router"] = _inspection_router_mod

# Now load the inspection_router module
_spec.loader.exec_module(_inspection_router_mod)

# Patch the inspection_router's get_db dependency to use task-specific session
# We'll need to override this for each test

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from src.database.base import Base, init_session
from src.database.inspection_models import InspectionRecord
from src.database.config_models import SystemConfig
from src.database.device_models import Device
from src.systemd.systemctl_executor import (
    SystemctlExecutor,
    TimerStatus,
    ServiceStatus,
    SystemctlResult,
    SystemdAvailability,
)
from src.systemd.systemd_unit_manager import (
    SystemdUnitManager, WriteResult, VerifyResult, SyncResult,
)


# ── Database fixtures ───────────────────────────────────────────

@pytest.fixture(scope="function")
def db_engine():
    """In-memory SQLite engine with all tables."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    init_session(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(db_engine):
    """Create and yield a DB session."""
    from src.database.base import SessionLocal
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def _seed_config(db, **kwargs):
    """Seed SystemConfig with inspection keys."""
    defaults = {
        "inspection.interval_minutes": "10",
        "diagnosis.timeout_seconds": "30",
        "diagnosis.retry_max": "3",
        "diagnosis.retry_backoff": "5",
    }
    defaults.update(kwargs)
    for key, value in defaults.items():
        existing = db.query(SystemConfig).filter(SystemConfig.config_key == key).first()
        if existing:
            existing.config_value = str(value)
        else:
            db.add(SystemConfig(config_key=key, config_value=str(value)))
    db.commit()


def _seed_inspection_history(db, count=5):
    """Seed InspectionRecord with varied statuses."""
    for i in range(count):
        status = "SUCCESS" if i < 3 else ("PARTIAL" if i < 4 else "FAILED")
        trigger = "SCHEDULED" if i % 2 == 0 else "MANUAL"
        db.add(InspectionRecord(
            trigger_mode=trigger,
            started_at=datetime(2026, 7, 10, 10, i, 0, tzinfo=timezone.utc),
            completed_at=datetime(2026, 7, 10, 10, i, 30, tzinfo=timezone.utc),
            total_devices=2,
            anomaly_count=0 if status == "SUCCESS" else 1,
            status=status,
            details={"devices": {}},
        ))
    db.commit()


# ── FastAPI app fixture ─────────────────────────────────────────

@pytest.fixture
def app_with_mocks(db_session):
    """Create FastAPI app with the inspection_router directly included.

    We override the get_db dependency to use the test session.
    """
    from fastapi import FastAPI

    app = FastAPI()

    # Override get_db in the inspection_router module to use our test session
    _inspection_router_mod.get_db = lambda: (yield db_session)

    app.include_router(
        _inspection_router_mod.inspection_router,
        prefix="/api/inspection",
        tags=["inspection"],
    )
    return app


def _mock_systemd_success(monkeypatch):
    """Patch systemd modules to return success for all operations."""
    mock_executor = MagicMock(spec=SystemctlExecutor)
    mock_executor.check_systemd_available.return_value = SystemdAvailability(available=True)
    mock_executor.get_timer_status.return_value = TimerStatus(
        active_state="active", unit_file_state="enabled",
        next_trigger=datetime(2026, 7, 10, 14, 20, 0, tzinfo=timezone.utc),
    )
    mock_executor.get_service_status.return_value = ServiceStatus(
        active_state="inactive", sub_state="dead", last_result="success",
    )
    mock_executor.start_service.return_value = SystemctlResult(success=True, action="start", message="ok")
    mock_executor.stop_service.return_value = SystemctlResult(success=True, action="stop", message="ok")
    mock_executor.restart_service.return_value = SystemctlResult(success=True, action="restart", message="ok")
    mock_executor.enable_timer.return_value = SystemctlResult(success=True, action="enable", message="timer 已启用")
    mock_executor.disable_timer.return_value = SystemctlResult(success=True, action="disable", message="timer 已禁用")
    mock_executor.daemon_reload.return_value = SystemctlResult(success=True, action="daemon-reload", message="ok")

    mock_manager = MagicMock(spec=SystemdUnitManager)
    mock_manager.sync_config_to_systemd.return_value = SyncResult(
        success=True, actions_performed=["rendered", "wrote", "daemon-reload"],
    )

    monkeypatch.setattr(
        _inspection_router_mod, "_get_systemctl_executor", lambda: mock_executor
    )
    monkeypatch.setattr(
        _inspection_router_mod, "_get_systemd_unit_manager", lambda: mock_manager
    )
    return mock_executor, mock_manager


def _mock_systemd_unavailable(monkeypatch):
    """Patch systemd modules to simulate systemd unavailable."""
    mock_executor = MagicMock(spec=SystemctlExecutor)
    mock_executor.check_systemd_available.return_value = SystemdAvailability(
        available=False, reason="systemd runtime directory not found"
    )
    mock_executor.get_timer_status.return_value = TimerStatus()
    mock_executor.get_service_status.return_value = ServiceStatus()
    monkeypatch.setattr(
        _inspection_router_mod, "_get_systemctl_executor", lambda: mock_executor
    )
    return mock_executor


# ════════════════════════════════════════════════════════════════
# Integration Test Classes
# ════════════════════════════════════════════════════════════════

class TestInspectionStatusAPI:
    """TC-INT-101~102: GET /api/inspection/status"""

    def test_status_available(self, app_with_mocks, db_session, monkeypatch):
        """TC-INT-101: GET /status with systemd available."""
        _seed_config(db_session)
        _seed_inspection_history(db_session, 2)
        _mock_systemd_success(monkeypatch)
        client = TestClient(app_with_mocks)
        response = client.get("/api/inspection/status")
        assert response.status_code == 200
        data = response.json()
        assert data["systemd_available"] is True
        assert data["timer"] is not None

    def test_status_systemd_unavailable(self, app_with_mocks, db_session, monkeypatch):
        """TC-INT-102: GET /status with systemd unavailable."""
        _mock_systemd_unavailable(monkeypatch)
        client = TestClient(app_with_mocks)
        response = client.get("/api/inspection/status")
        assert response.status_code == 200
        data = response.json()
        assert data["systemd_available"] is False
        assert data["timer"] is None


class TestServiceLifecycleAPI:
    """TC-INT-103~105, 113: POST /start, /stop, /restart"""

    def test_start_service_success(self, app_with_mocks, db_session, monkeypatch):
        """TC-INT-103: POST /start returns success."""
        _seed_config(db_session)
        _mock_systemd_success(monkeypatch)
        client = TestClient(app_with_mocks)
        response = client.post("/api/inspection/start")
        assert response.status_code == 200
        assert response.json()["result"] == "success"

    def test_stop_service_success(self, app_with_mocks, db_session, monkeypatch):
        """TC-INT-104: POST /stop returns success."""
        _seed_config(db_session)
        _mock_systemd_success(monkeypatch)
        client = TestClient(app_with_mocks)
        response = client.post("/api/inspection/stop")
        assert response.status_code == 200

    def test_restart_service_success(self, app_with_mocks, db_session, monkeypatch):
        """TC-INT-105: POST /restart returns success."""
        _seed_config(db_session)
        _mock_systemd_success(monkeypatch)
        client = TestClient(app_with_mocks)
        response = client.post("/api/inspection/restart")
        assert response.status_code == 200

    def test_start_systemd_unavailable(self, app_with_mocks, db_session, monkeypatch):
        """TC-INT-113: POST /start returns 503."""
        _mock_systemd_unavailable(monkeypatch)
        client = TestClient(app_with_mocks)
        response = client.post("/api/inspection/start")
        assert response.status_code == 503


class TestEnableDisableAPI:
    """TC-INT-106~107: POST /enable, /disable"""

    def test_enable_timer_success(self, app_with_mocks, db_session, monkeypatch):
        """TC-INT-106: POST /enable returns success."""
        _seed_config(db_session)
        _mock_systemd_success(monkeypatch)
        client = TestClient(app_with_mocks)
        response = client.post("/api/inspection/enable")
        assert response.status_code == 200

    def test_disable_timer_success(self, app_with_mocks, db_session, monkeypatch):
        """TC-INT-107: POST /disable returns success."""
        _seed_config(db_session)
        _mock_systemd_success(monkeypatch)
        client = TestClient(app_with_mocks)
        response = client.post("/api/inspection/disable")
        assert response.status_code == 200


class TestConfigAPI:
    """TC-INT-108~109, 117~118: PUT/GET /api/inspection/config"""

    def test_put_config_sync_success(self, app_with_mocks, db_session, monkeypatch):
        """TC-INT-108: PUT /config triggers systemd sync."""
        _seed_config(db_session)
        _mock_systemd_success(monkeypatch)
        client = TestClient(app_with_mocks)
        response = client.put("/api/inspection/config", json={
            "inspection_interval_minutes": 15,
            "retry_backoff_seconds": 10,
        })
        assert response.status_code == 200
        data = response.json()
        assert data["systemd_sync"] == "success"
        assert data["config"]["diagnosis.retry_backoff"] == "10"

    def test_put_config_sync_failure(self, app_with_mocks, db_session, monkeypatch):
        """TC-INT-109: PUT /config with sync failure."""
        _seed_config(db_session)
        mock_executor = MagicMock(spec=SystemctlExecutor)
        mock_executor.check_systemd_available.return_value = SystemdAvailability(available=True)
        mock_manager = MagicMock(spec=SystemdUnitManager)
        mock_manager.sync_config_to_systemd.return_value = SyncResult(
            success=False, error="permission denied"
        )
        monkeypatch.setattr(_inspection_router_mod, "_get_systemctl_executor", lambda: mock_executor)
        monkeypatch.setattr(_inspection_router_mod, "_get_systemd_unit_manager", lambda: mock_manager)

        client = TestClient(app_with_mocks)
        response = client.put("/api/inspection/config", json={"inspection_interval_minutes": 20})
        assert response.status_code == 200
        assert response.json()["systemd_sync"] == "failed"

    def test_put_config_validation_negative(self, app_with_mocks, db_session, monkeypatch):
        """TC-INT-118: PUT /config rejects negative values."""
        _mock_systemd_success(monkeypatch)
        client = TestClient(app_with_mocks)
        response = client.put("/api/inspection/config", json={"inspection_interval_minutes": -1})
        assert response.status_code == 422

    def test_get_config_returns_retry_backoff(self, app_with_mocks, db_session, monkeypatch):
        """TC-INT-117: GET /config returns retry_backoff."""
        _seed_config(db_session, **{"diagnosis.retry_backoff": "7"})
        client = TestClient(app_with_mocks)
        response = client.get("/api/inspection/config")
        assert response.status_code == 200
        assert response.json()["config"]["diagnosis.retry_backoff"] == "7"


class TestTriggerAPI:
    """TC-INT-110~112: POST /api/inspection/trigger"""

    def test_trigger_success(self, app_with_mocks, db_session, monkeypatch):
        """TC-INT-110: POST /trigger returns success."""
        _seed_config(db_session)
        exec_mock, _ = _mock_systemd_success(monkeypatch)
        exec_mock.get_service_status.return_value = ServiceStatus(
            active_state="inactive", sub_state="dead"
        )
        client = TestClient(app_with_mocks)
        response = client.post("/api/inspection/trigger")
        assert response.status_code == 200
        assert response.json()["result"] == "success"

    def test_trigger_already_running_409(self, app_with_mocks, db_session, monkeypatch):
        """TC-INT-111: POST /trigger returns 409."""
        _seed_config(db_session)
        exec_mock, _ = _mock_systemd_success(monkeypatch)
        exec_mock.get_service_status.return_value = ServiceStatus(
            active_state="active", sub_state="running"
        )
        client = TestClient(app_with_mocks)
        response = client.post("/api/inspection/trigger")
        assert response.status_code == 409

    def test_trigger_systemd_unavailable_503(self, app_with_mocks, db_session, monkeypatch):
        """TC-INT-112: POST /trigger returns 503."""
        _mock_systemd_unavailable(monkeypatch)
        client = TestClient(app_with_mocks)
        response = client.post("/api/inspection/trigger")
        assert response.status_code == 503


class TestHistoryAPI:
    """TC-INT-114~116: GET /api/inspection/history"""

    def test_history_pagination(self, app_with_mocks, db_session, monkeypatch):
        """TC-INT-114: GET /history pagination."""
        _seed_inspection_history(db_session, 25)
        client = TestClient(app_with_mocks)
        response = client.get("/api/inspection/history?page=1&page_size=10")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 25

    def test_history_filter_trigger_mode(self, app_with_mocks, db_session, monkeypatch):
        """TC-INT-115: GET /history?trigger_mode= filter."""
        _seed_inspection_history(db_session, 5)
        client = TestClient(app_with_mocks)
        response = client.get("/api/inspection/history?trigger_mode=MANUAL")
        assert response.status_code == 200

    def test_history_filter_status(self, app_with_mocks, db_session, monkeypatch):
        """TC-INT-116: GET /history?status= filter."""
        _seed_inspection_history(db_session, 5)
        client = TestClient(app_with_mocks)
        response = client.get("/api/inspection/history?status=FAILED")
        assert response.status_code == 200
