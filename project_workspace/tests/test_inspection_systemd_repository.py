"""
Unit tests for MOD-WEB-004: inspection_repository (v0.2.0 enhancements).
@author sub_agent_test_engineer
@module MOD-WEB-004
@covers REQ-INSP-001, REQ-INSP-010, REQ-INSP-011, REQ-INSP-012, REQ-INSP-013
@test_level UNIT
"""
import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import pytest
from datetime import datetime, timezone
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session

from src.database.base import Base
from src.database.inspection_models import InspectionRecord
from src.database.config_models import SystemConfig
from src.database.device_models import Device
from src.database.repositories.inspection_repository import InspectionRepository


# ── Fixtures ────────────────────────────────────────────────────

@pytest.fixture(scope="function")
def db_session():
    """Create an in-memory SQLite database with all tables for testing."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def repo(db_session):
    """Create InspectionRepository with test session."""
    return InspectionRepository(db_session)


# ── Helper ──────────────────────────────────────────────────────

def _add_config(db: Session, key: str, value: str):
    db.add(SystemConfig(config_key=key, config_value=value))
    db.commit()


def _add_device(db: Session, name: str, ip: str, model: str = "TestModel"):
    db.add(Device(device_name=name, device_ip=ip, device_model=model))
    db.commit()


def _add_inspection_record(db: Session, trigger_mode: str, status: str,
                           total_devices: int = 3, anomaly_count: int = 0):
    record = InspectionRecord(
        trigger_mode=trigger_mode,
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
        total_devices=total_devices,
        anomaly_count=anomaly_count,
        status=status,
        details={"devices": {}},
    )
    db.add(record)
    db.commit()
    return record


# ════════════════════════════════════════════════════════════════
# TC-UNIT-080~082: get_config / update_config with retry_backoff
# ════════════════════════════════════════════════════════════════

class TestConfigRetryBackoff:

    def test_get_config_returns_4_keys_when_empty(self, repo):
        """TC-UNIT-080: get_config returns 4 keys with empty strings when no config."""
        config = repo.get_config()
        assert "inspection.interval_minutes" in config
        assert "diagnosis.timeout_seconds" in config
        assert "diagnosis.retry_max" in config
        assert "diagnosis.retry_backoff" in config
        # No data → returns sensible defaults (not empty strings)
        assert config["diagnosis.retry_backoff"] == "2"

    def test_get_config_returns_stored_values(self, repo, db_session):
        """TC-UNIT-080: get_config returns stored values from SystemConfig."""
        _add_config(db_session, "diagnosis.retry_backoff", "10")
        _add_config(db_session, "inspection.interval_minutes", "15")
        config = repo.get_config()
        assert config["diagnosis.retry_backoff"] == "10"
        assert config["inspection.interval_minutes"] == "15"

    def test_update_config_creates_new_key(self, repo, db_session):
        """TC-UNIT-081: update_config creates new retry_backoff config key."""
        repo.update_config({"diagnosis.retry_backoff": "10"})
        config = repo.get_config()
        assert config["diagnosis.retry_backoff"] == "10"

    def test_update_config_updates_existing_key(self, repo, db_session):
        """TC-UNIT-082: update_config updates existing retry_backoff config."""
        _add_config(db_session, "diagnosis.retry_backoff", "5")
        repo.update_config({"diagnosis.retry_backoff": "15"})
        config = repo.get_config()
        assert config["diagnosis.retry_backoff"] == "15"

    def test_update_config_multiple_keys(self, repo, db_session):
        """update_config handles multiple keys at once."""
        repo.update_config({
            "diagnosis.retry_backoff": "7",
            "inspection.interval_minutes": "10",
        })
        config = repo.get_config()
        assert config["diagnosis.retry_backoff"] == "7"
        assert config["inspection.interval_minutes"] == "10"

    def test_get_config_does_not_include_polling_interval(self, repo):
        """v0.2.0: get_config should NOT include ui.polling_interval_seconds."""
        config = repo.get_config()
        assert "ui.polling_interval_seconds" not in config


# ════════════════════════════════════════════════════════════════
# TC-UNIT-083: create_record
# ════════════════════════════════════════════════════════════════

class TestCreateRecord:

    def test_create_record_basic(self, repo, db_session):
        """TC-UNIT-083: create_record creates InspectionRecord successfully."""
        data = {
            "trigger_mode": "MANUAL",
            "started_at": datetime.now(timezone.utc),
            "total_devices": 2,
            "anomaly_count": 0,
            "status": "SUCCESS",
            "details": {"devices": {}},
        }
        record = repo.create_record(data)
        assert record.id is not None
        assert record.trigger_mode == "MANUAL"
        assert record.status == "SUCCESS"
        assert record.total_devices == 2

    def test_create_record_default_status(self, repo, db_session):
        """create_record uses default status=SUCCESS if not provided."""
        data = {
            "trigger_mode": "SCHEDULED",
            "started_at": datetime.now(timezone.utc),
            "total_devices": 3,
            "anomaly_count": 0,
            "details": {},
        }
        record = repo.create_record(data)
        assert record.status == "SUCCESS"

    def test_create_record_with_completed_at(self, repo, db_session):
        """create_record with completed_at set.

        Note: SQLite stores datetimes without timezone info, so SQLAlchemy
        returns naive datetimes. We compare using replace(tzinfo=None).
        """
        now = datetime.now(timezone.utc)
        data = {
            "trigger_mode": "SCHEDULED",
            "started_at": now,
            "completed_at": now,
            "total_devices": 1,
            "anomaly_count": 0,
            "details": {},
        }
        record = repo.create_record(data)
        # SQLite stores naive datetimes; compare without timezone
        assert record.completed_at is not None
        assert record.completed_at.replace(tzinfo=None) == now.replace(tzinfo=None)


# ════════════════════════════════════════════════════════════════
# TC-UNIT-084~085: get_latest_inspection
# ════════════════════════════════════════════════════════════════

class TestGetLatestInspection:

    def test_get_latest_returns_most_recent(self, repo, db_session):
        """TC-UNIT-084: get_latest_inspection returns record with latest completed_at."""
        early = datetime(2026, 7, 10, 10, 0, 0, tzinfo=timezone.utc)
        late = datetime(2026, 7, 10, 11, 0, 0, tzinfo=timezone.utc)

        rec1 = InspectionRecord(
            trigger_mode="SCHEDULED", started_at=early, completed_at=early,
            total_devices=2, anomaly_count=0, status="SUCCESS", details={},
        )
        rec2 = InspectionRecord(
            trigger_mode="MANUAL", started_at=late, completed_at=late,
            total_devices=3, anomaly_count=1, status="PARTIAL", details={},
        )
        db_session.add_all([rec1, rec2])
        db_session.commit()

        latest = repo.get_latest_inspection()
        assert latest is not None
        assert latest["trigger_mode"] == "MANUAL"
        assert latest["anomaly_count"] == 1
        assert latest["status"] == "PARTIAL"

    def test_get_latest_returns_none_when_empty(self, repo):
        """TC-UNIT-085: get_latest_inspection returns None when no records."""
        latest = repo.get_latest_inspection()
        assert latest is None


# ════════════════════════════════════════════════════════════════
# TC-UNIT-086: get_devices_for_inspection
# ════════════════════════════════════════════════════════════════

class TestGetDevicesForInspection:

    def test_get_devices_returns_list(self, repo, db_session):
        """TC-UNIT-086: get_devices_for_inspection returns device list."""
        _add_device(db_session, "Core-SW-01", "192.168.1.1", "T2600G-28TS")
        _add_device(db_session, "Access-SW-02", "192.168.1.2", "T2600G-28TS")

        devices = repo.get_devices_for_inspection()
        assert len(devices) == 2
        assert devices[0]["device_name"] == "Core-SW-01"
        assert devices[0]["device_ip"] == "192.168.1.1"
        assert devices[0]["device_model"] == "T2600G-28TS"

    def test_get_devices_empty(self, repo):
        """get_devices_for_inspection returns empty list when no devices."""
        devices = repo.get_devices_for_inspection()
        assert devices == []


# ════════════════════════════════════════════════════════════════
# TC-UNIT-087~089: list_history with status filter
# ════════════════════════════════════════════════════════════════

class TestListHistory:

    def test_list_history_by_trigger_mode(self, repo, db_session):
        """TC-UNIT-087: list_history filters by trigger_mode."""
        _add_inspection_record(db_session, "SCHEDULED", "SUCCESS")
        _add_inspection_record(db_session, "SCHEDULED", "SUCCESS")
        _add_inspection_record(db_session, "MANUAL", "SUCCESS")

        result = repo.list_history(trigger_mode="MANUAL")
        assert result["total"] == 1
        items = list(result["items"])
        assert items[0].trigger_mode == "MANUAL"

        result = repo.list_history(trigger_mode="SCHEDULED")
        assert result["total"] == 2

    def test_list_history_by_status(self, repo, db_session):
        """TC-UNIT-088: list_history filters by status."""
        _add_inspection_record(db_session, "SCHEDULED", "SUCCESS")
        _add_inspection_record(db_session, "SCHEDULED", "PARTIAL")
        _add_inspection_record(db_session, "MANUAL", "FAILED")

        result = repo.list_history(status="FAILED")
        assert result["total"] == 1
        items = list(result["items"])
        assert items[0].status == "FAILED"

        result = repo.list_history(status="SUCCESS")
        assert result["total"] == 1

    def test_list_history_by_trigger_and_status(self, repo, db_session):
        """list_history filters by both trigger_mode and status."""
        _add_inspection_record(db_session, "SCHEDULED", "FAILED")
        _add_inspection_record(db_session, "MANUAL", "FAILED")

        result = repo.list_history(trigger_mode="SCHEDULED", status="FAILED")
        assert result["total"] == 1

    def test_list_history_pagination(self, repo, db_session):
        """TC-UNIT-089: list_history supports pagination."""
        for i in range(25):
            _add_inspection_record(db_session, "SCHEDULED", "SUCCESS")

        result = repo.list_history(page=1, page_size=10)
        assert result["total"] == 25
        assert result["page"] == 1
        assert result["page_size"] == 10
        assert len(list(result["items"])) == 10

        result = repo.list_history(page=2, page_size=10)
        assert result["page"] == 2
        assert len(list(result["items"])) == 10

        result = repo.list_history(page=3, page_size=10)
        assert result["page"] == 3
        assert len(list(result["items"])) == 5

    def test_list_history_empty(self, repo):
        """list_history returns empty items when no records."""
        result = repo.list_history()
        assert result["total"] == 0
        assert len(list(result["items"])) == 0
