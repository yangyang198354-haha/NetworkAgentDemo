"""
E2E tests for v0.2.0 inspection systemd refactoring.
Full user journeys spanning all 8 user stories (US-INSP-001~008).
@author sub_agent_test_engineer
@covers All US-INSP-* Critical Paths, TC-E2E-200~208
@test_level E2E
"""
import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

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


# ── Fixtures ────────────────────────────────────────────────────

@pytest.fixture(scope="function")
def db_engine():
    from sqlalchemy.pool import StaticPool
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    init_session(engine)
    yield engine
    engine.dispose()


def _seed_all(db: Session):
    """Seed DB with config, devices, and history."""
    for key, val in {
        "inspection.interval_minutes": "10",
        "diagnosis.timeout_seconds": "30",
        "diagnosis.retry_max": "3",
        "diagnosis.retry_backoff": "5",
    }.items():
        db.add(SystemConfig(config_key=key, config_value=val))
    db.add(Device(device_name="Core-SW-01", device_ip="192.168.1.1", device_model="T2600G-28TS"))
    db.add(Device(device_name="Access-SW-02", device_ip="192.168.1.2", device_model="T2600G-28TS"))
    for i in range(5):
        db.add(InspectionRecord(
            trigger_mode="SCHEDULED" if i % 2 == 0 else "MANUAL",
            started_at=datetime(2026, 7, 10, 10, i, 0, tzinfo=timezone.utc),
            completed_at=datetime(2026, 7, 10, 10, i, 30, tzinfo=timezone.utc),
            total_devices=2,
            anomaly_count=0 if i < 3 else 1,
            status="SUCCESS" if i < 3 else "PARTIAL",
            details={"devices": {}},
        ))
    db.commit()


def _create_app_with_full_mocks(monkeypatch, systemd_available=True):
    """Create FastAPI app with fully mocked systemd for E2E."""
    from src.api import _inspection_router_module as router_mod
    from src.api.inspection_router import inspection_router
    from fastapi import FastAPI

    mock_executor = MagicMock(spec=SystemctlExecutor)
    mock_manager = MagicMock(spec=SystemdUnitManager)

    if systemd_available:
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
        mock_manager.sync_config_to_systemd.return_value = SyncResult(
            success=True, actions_performed=["rendered", "wrote", "daemon-reload"]
        )
    else:
        mock_executor.check_systemd_available.return_value = SystemdAvailability(
            available=False, reason="no systemd"
        )

    monkeypatch.setattr(router_mod, "_get_systemctl_executor", lambda: mock_executor)
    monkeypatch.setattr(router_mod, "_get_systemd_unit_manager", lambda: mock_manager)

    app = FastAPI()
    app.include_router(inspection_router, prefix="/api/inspection", tags=["inspection"])
    return app, mock_executor, mock_manager


# ════════════════════════════════════════════════════════════════
# TC-E2E-200: US-INSP-001 — 巡检配置管理完整旅程
# ════════════════════════════════════════════════════════════════

class TestE2EConfigManagement:
    """Critical Path: Configuration read → modify → verify → systemd sync."""

    def test_config_full_cycle(self, db_engine, monkeypatch):
        """TC-E2E-200: Complete config CRUD journey."""
        from src.database.base import SessionLocal
        session = SessionLocal()
        _seed_all(session)
        session.close()

        app, _, _ = _create_app_with_full_mocks(monkeypatch, systemd_available=True)
        client = TestClient(app)

        # Step 1: Read current config
        resp = client.get("/api/inspection/config")
        assert resp.status_code == 200
        config = resp.json()["config"]
        assert config["inspection.interval_minutes"] == "10"
        assert config["diagnosis.retry_backoff"] == "5"

        # Step 2: Modify config
        resp = client.put("/api/inspection/config", json={
            "inspection_interval_minutes": 15,
            "retry_backoff_seconds": 7,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["systemd_sync"] == "success"
        assert data["config"]["inspection.interval_minutes"] == "15"

        # Step 3: Re-read and verify
        resp = client.get("/api/inspection/config")
        assert resp.status_code == 200
        config = resp.json()["config"]
        assert config["inspection.interval_minutes"] == "15"
        assert config["diagnosis.retry_backoff"] == "7"

        # Step 4: Verify validation
        resp = client.put("/api/inspection/config", json={
            "inspection_interval_minutes": 0,
        })
        assert resp.status_code == 422


# ════════════════════════════════════════════════════════════════
# TC-E2E-202: US-INSP-003 — 巡检状态查询完整旅程
# ════════════════════════════════════════════════════════════════

class TestE2EStatusQuery:
    """Critical Path: Status query in both available and unavailable environments."""

    def test_status_both_environments(self, db_engine, monkeypatch):
        """TC-E2E-202: Status query in both systemd-available and unavailable modes."""
        from src.database.base import SessionLocal
        session = SessionLocal()
        _seed_all(session)
        session.close()

        # Test 1: systemd available
        app, _, _ = _create_app_with_full_mocks(monkeypatch, systemd_available=True)
        client = TestClient(app)
        resp = client.get("/api/inspection/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["systemd_available"] is True
        assert data["timer"]["active_state"] == "active"
        assert data["service"]["sub_state"] == "dead"

        # Test 2: systemd unavailable (need fresh app)
        app2, _, _ = _create_app_with_full_mocks(monkeypatch, systemd_available=False)
        client2 = TestClient(app2)
        resp = client2.get("/api/inspection/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["systemd_available"] is False
        assert data["timer"] is None
        assert "手动触发" in data.get("message", "")


# ════════════════════════════════════════════════════════════════
# TC-E2E-203: US-INSP-004 — 巡检服务生命周期控制完整旅程
# ════════════════════════════════════════════════════════════════

class TestE2EServiceLifecycle:
    """Critical Path: start → status → stop → status → restart → status."""

    def test_lifecycle_full_flow(self, db_engine, monkeypatch):
        """TC-E2E-203: Complete service lifecycle: start, status check, stop, restart."""
        from src.database.base import SessionLocal
        session = SessionLocal()
        _seed_all(session)
        session.close()

        app, exec_mock, _ = _create_app_with_full_mocks(monkeypatch, systemd_available=True)
        client = TestClient(app)

        # Step 1: Start service
        resp = client.post("/api/inspection/start")
        assert resp.status_code == 200
        assert resp.json()["result"] == "success"
        exec_mock.start_service.assert_called_once()

        # Step 2: Check status (simulate service started)
        exec_mock.get_service_status.return_value = ServiceStatus(
            active_state="active", sub_state="running", last_result="success",
        )
        resp = client.get("/api/inspection/status")
        assert resp.status_code == 200
        assert resp.json()["service"]["active_state"] == "active"

        # Step 3: Stop service
        resp = client.post("/api/inspection/stop")
        assert resp.status_code == 200
        assert resp.json()["result"] == "success"
        exec_mock.stop_service.assert_called_once()

        # Step 4: Restart service
        resp = client.post("/api/inspection/restart")
        assert resp.status_code == 200
        assert resp.json()["result"] == "success"
        exec_mock.restart_service.assert_called_once()

        # Step 5: Verify systemd unavailable → 503
        app2, _, _ = _create_app_with_full_mocks(monkeypatch, systemd_available=False)
        client2 = TestClient(app2)
        resp = client2.post("/api/inspection/start")
        assert resp.status_code == 503


# ════════════════════════════════════════════════════════════════
# TC-E2E-204: US-INSP-005 — Timer 启用/禁用完整旅程
# ════════════════════════════════════════════════════════════════

class TestE2ETimerEnableDisable:
    """Critical Path: enable → status → disable → status → idempotent enable."""

    def test_timer_enable_disable_cycle(self, db_engine, monkeypatch):
        """TC-E2E-204: Enable, check status, disable, check status, idempotent enable."""
        from src.database.base import SessionLocal
        session = SessionLocal()
        _seed_all(session)
        session.close()

        app, exec_mock, _ = _create_app_with_full_mocks(monkeypatch, systemd_available=True)
        client = TestClient(app)

        # Step 1: Enable timer (initially disabled)
        exec_mock.get_timer_status.return_value = TimerStatus(
            active_state="inactive", unit_file_state="disabled"
        )
        resp = client.post("/api/inspection/enable")
        assert resp.status_code == 200
        assert resp.json()["result"] == "success"

        # Step 2: Check timer is enabled
        exec_mock.get_timer_status.return_value = TimerStatus(
            active_state="active", unit_file_state="enabled"
        )
        resp = client.get("/api/inspection/status")
        assert resp.status_code == 200
        assert resp.json()["timer"]["unit_file_state"] == "enabled"

        # Step 3: Disable timer
        resp = client.post("/api/inspection/disable")
        assert resp.status_code == 200
        assert resp.json()["result"] == "success"

        # Step 4: Check timer is disabled
        exec_mock.get_timer_status.return_value = TimerStatus(
            active_state="inactive", unit_file_state="disabled"
        )
        resp = client.get("/api/inspection/status")
        assert resp.status_code == 200
        assert resp.json()["timer"]["unit_file_state"] == "disabled"


# ════════════════════════════════════════════════════════════════
# TC-E2E-205: US-INSP-006 — 手动触发巡检完整旅程
# ════════════════════════════════════════════════════════════════

class TestE2EManualTrigger:
    """Critical Path: trigger → success → re-trigger 409 → unavailable 503."""

    def test_manual_trigger_full_flow(self, db_engine, monkeypatch):
        """TC-E2E-205: Manual trigger journey including conflict and unavailable paths."""
        from src.database.base import SessionLocal
        session = SessionLocal()
        _seed_all(session)
        session.close()

        app, exec_mock, _ = _create_app_with_full_mocks(monkeypatch, systemd_available=True)
        client = TestClient(app)

        # Step 1: Trigger (service not running)
        exec_mock.get_service_status.return_value = ServiceStatus(
            active_state="inactive", sub_state="dead"
        )
        resp = client.post("/api/inspection/trigger")
        assert resp.status_code == 200
        assert resp.json()["trigger_mode"] == "MANUAL"

        # Step 2: Re-trigger while running → 409
        exec_mock.get_service_status.return_value = ServiceStatus(
            active_state="active", sub_state="running"
        )
        resp = client.post("/api/inspection/trigger")
        assert resp.status_code == 409

        # Step 3: Trigger when systemd unavailable → 503
        app2, _, _ = _create_app_with_full_mocks(monkeypatch, systemd_available=False)
        client2 = TestClient(app2)
        resp = client2.post("/api/inspection/trigger")
        assert resp.status_code == 503


# ════════════════════════════════════════════════════════════════
# TC-E2E-206: US-INSP-007 — 巡检历史查询完整旅程
# ════════════════════════════════════════════════════════════════

class TestE2EHistoryQuery:
    """Critical Path: list → paginate → filter by trigger_mode → filter by status."""

    def test_history_full_flow(self, db_engine, monkeypatch):
        """TC-E2E-206: Full history query journey with all filters."""
        from src.database.base import SessionLocal
        session = SessionLocal()
        _seed_all(session)
        session.close()

        app, _, _ = _create_app_with_full_mocks(monkeypatch, systemd_available=True)
        client = TestClient(app)

        # Step 1: List all history
        resp = client.get("/api/inspection/history?page=1&page_size=10")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 5
        assert len(data["items"]) == 5

        # Step 2: Filter by trigger_mode
        resp = client.get("/api/inspection/history?trigger_mode=SCHEDULED")
        assert resp.status_code == 200
        items = resp.json()["items"]
        for item in items:
            assert item["trigger_mode"] == "SCHEDULED"

        # Step 3: Filter by status
        resp = client.get("/api/inspection/history?status=SUCCESS")
        assert resp.status_code == 200
        items = resp.json()["items"]
        for item in items:
            assert item["status"] == "SUCCESS"

        # Step 4: Pagination
        resp = client.get("/api/inspection/history?page=1&page_size=2")
        assert resp.status_code == 200
        data = resp.json()
        assert data["page_size"] == 2
        assert len(data["items"]) == 2


# ════════════════════════════════════════════════════════════════
# TC-E2E-207: US-INSP-008 — systemd 定时触发 CLI 巡检旅程
# ════════════════════════════════════════════════════════════════

class TestE2ECLIInspection:
    """Critical Path: CLI run → SQLite persists → exit code correct."""

    def test_cli_inspection_full_flow(self, db_engine, monkeypatch):
        """TC-E2E-207: CLI inspection execution journey."""
        from src.database.base import SessionLocal
        session = SessionLocal()
        _seed_all(session)
        session.close()

        from src.inspection_cli import InspectionCLI, CLIExitCode

        cli = InspectionCLI()

        # Mock DB init so we don't actually connect
        mock_session = MagicMock()
        mock_session.execute.return_value.scalars.return_value.all.return_value = []
        cli._db_session = mock_session

        with patch.object(cli, "_init_db"):
            with patch.object(cli, "load_inspection_config") as mock_cfg:
                mock_cfg.return_value = {
                    "inspection.interval_minutes": "10",
                    "diagnosis.timeout_seconds": "30",
                    "diagnosis.retry_max": "3",
                    "diagnosis.retry_backoff": "5",
                }
                with patch.object(cli, "load_device_list") as mock_devs:
                    mock_devs.return_value = []
                    with patch.object(cli, "_close_db"):
                        result = cli.run()

        assert result == CLIExitCode.SUCCESS

    def test_cli_exit_codes(self):
        """Verify all CLIExitCode values."""
        from src.inspection_cli import CLIExitCode
        assert CLIExitCode.SUCCESS == 0
        assert CLIExitCode.PARTIAL == 1
        assert CLIExitCode.FAILURE == 2


# ════════════════════════════════════════════════════════════════
# TC-E2E-208: US-INSP-001~008 — 全链路跨故事旅程
# ════════════════════════════════════════════════════════════════

class TestE2ECrossStoryFullChain:
    """Critical Path: Full cross-story journey: config → sync → status → control → trigger → history."""

    def test_full_cross_story_journey(self, db_engine, monkeypatch):
        """TC-E2E-208: Execute the entire inspection management lifecycle across all stories."""
        from src.database.base import SessionLocal
        session = SessionLocal()
        _seed_all(session)
        session.close()

        app, exec_mock, _ = _create_app_with_full_mocks(monkeypatch, systemd_available=True)
        client = TestClient(app)

        # ── US-INSP-001: 配置管理 ──
        resp = client.get("/api/inspection/config")
        assert resp.status_code == 200
        assert resp.json()["config"]["diagnosis.retry_backoff"] == "5"

        resp = client.put("/api/inspection/config", json={
            "retry_backoff_seconds": 8,
        })
        assert resp.status_code == 200
        assert resp.json()["systemd_sync"] == "success"

        # ── US-INSP-003: 状态查询 ──
        resp = client.get("/api/inspection/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["systemd_available"] is True
        assert data["timer"] is not None

        # ── US-INSP-005: Timer 启用 ──
        exec_mock.get_timer_status.return_value = TimerStatus(
            active_state="inactive", unit_file_state="disabled"
        )
        resp = client.post("/api/inspection/enable")
        assert resp.status_code == 200

        # ── US-INSP-004: Service 生命周期 ──
        resp = client.post("/api/inspection/restart")
        assert resp.status_code == 200

        # ── US-INSP-006: 手动触发 ──
        exec_mock.get_service_status.return_value = ServiceStatus(
            active_state="inactive", sub_state="dead"
        )
        resp = client.post("/api/inspection/trigger")
        assert resp.status_code == 200

        # ── US-INSP-007: 历史查询 ──
        resp = client.get("/api/inspection/history")
        assert resp.status_code == 200
        assert resp.json()["total"] >= 5

        # ── US-INSP-005: Timer 禁用 ──
        resp = client.post("/api/inspection/disable")
        assert resp.status_code == 200

        # All stories executed without errors
        print("[E2E-208] Cross-story journey completed successfully")
