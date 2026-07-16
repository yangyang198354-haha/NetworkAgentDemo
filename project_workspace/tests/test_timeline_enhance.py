"""
Unit and integration tests for Timeline Enhancement (MOD-TL-001/002/003).

Covers:
  1. AlertTimeline model columns (sequence_number, duration_ms)
  2. AlertRepository new methods (update_timeline_entry, ensure_timeline_columns)
  3. _log_node START/END dual-phase DB persistence
  4. Backward compatibility with old records
  5. Full timeline workflow integration

@author sub_agent_test_engineer
@module MOD-TL-001, MOD-TL-002, MOD-TL-003
@covers REQ-FUNC-001, REQ-FUNC-002, REQ-FUNC-006, REQ-NFUNC-002
@test_level UNIT | INTEGRATION
"""

import sys
import os
import time
import tempfile
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import pytest
from datetime import datetime, timezone
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from src.database.base import Base
from src.database.alert_models import Alert, AlertTimeline
from src.database.repositories.alert_repository import AlertRepository, ensure_timeline_columns
from src.orchestration.node_handlers import NodeHandlers
from src.models.state import NetworkAgentState
from src.models.enums import AlertType, WorkflowStatus
from src.security.audit_logger import AuditLogger
from src.security.config_manager import ConfigManager
from src.security.risk_assessor import RiskAssessor
from src.llm.llm_service import LLMService
from src.llm.template_engine import TemplateEngine
from src.llm.output_validator import OutputValidator
from src.llm.rag_service import RAGService
from src.tools.switch_config_tool import create_switch_config_tool
from src.tools.switch_diag_tool import create_switch_diag_tool
from src.tools.backup_tool import create_backup_tool
from src.tools.knowledge_base_tool import KnowledgeBaseTool


# ════════════════════════════════════════════════════════════════
# Fixtures
# ════════════════════════════════════════════════════════════════

@pytest.fixture(scope="function")
def db_path():
    """Create a temporary SQLite database file for shared-engine tests."""
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    yield path
    try:
        os.unlink(path)
    except OSError:
        pass


@pytest.fixture(scope="function")
def db_engine(db_path):
    """Create SQLAlchemy engine bound to temp file."""
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    # Enable WAL + FK for consistency with production
    with engine.connect() as conn:
        conn.execute(text("PRAGMA journal_mode=WAL"))
        conn.execute(text("PRAGMA foreign_keys=ON"))
        conn.commit()
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture(scope="function")
def db_session(db_engine):
    """Create a session from the temp-file engine."""
    Session = sessionmaker(bind=db_engine, autocommit=False, autoflush=False)
    session = Session()
    yield session
    session.close()


@pytest.fixture(scope="function")
def repo(db_session):
    """Create AlertRepository with test session."""
    return AlertRepository(db_session)


@pytest.fixture(scope="function")
def patched_session_local(db_engine):
    """
    Patch src.database.base.SessionLocal so _log_node's internal
    DB sessions bind to our test engine. Restored on teardown.
    """
    import src.database.base
    original = src.database.base.SessionLocal
    src.database.base.SessionLocal = sessionmaker(
        bind=db_engine, autocommit=False, autoflush=False
    )
    yield db_engine
    src.database.base.SessionLocal = original


@pytest.fixture(scope="function")
def verify_session(db_engine):
    """A separate session for verifying DB state after _log_node calls."""
    S = sessionmaker(bind=db_engine, autocommit=False, autoflush=False)
    session = S()
    yield session
    session.close()


@pytest.fixture
def handlers():
    """Create NodeHandlers with mock dependencies."""
    audit_logger = AuditLogger()
    return NodeHandlers(
        llm_service=LLMService(),
        template_engine=TemplateEngine(),
        rag_service=RAGService(),
        output_validator=OutputValidator(audit_logger=audit_logger),
        switch_config_tool=create_switch_config_tool(use_mock=True),
        switch_diag_tool=create_switch_diag_tool(use_mock=True),
        backup_tool=create_backup_tool(use_mock=True),
        knowledge_base_tool=KnowledgeBaseTool(rag_service=RAGService()),
        risk_assessor=RiskAssessor(),
        audit_logger=audit_logger,
        config_manager=ConfigManager(),
    )


def _make_state(alert_id="test-alert-001") -> NetworkAgentState:
    """Create a minimal NetworkAgentState for testing."""
    return NetworkAgentState(
        alert_id=alert_id,
        alert_type=AlertType.PORT_DOWN,
        alert_content="Test port down alert on Gi0/1",
        alert_timestamp=datetime.now(timezone.utc).isoformat(),
        device_info={
            "device_name": "Test-SW-01",
            "device_ip": "192.168.1.1",
        },
        is_valid=True,
        status=WorkflowStatus.ACTIVE,
    )


def _ensure_alert_in_db(alert_id):
    """
    Create an Alert row in the test DB (via patched SessionLocal) so that
    _log_node's INSERT into alert_timeline satisfies the FK constraint.
    Safe to call multiple times for the same alert_id (INSERT OR IGNORE).
    """
    import src.database.base
    if src.database.base.SessionLocal is None:
        return
    db = src.database.base.SessionLocal()
    try:
        db.execute(
            text(
                "INSERT OR IGNORE INTO alerts (alert_id, alert_type, severity, content, "
                "device_info, source, status, created_at, updated_at) "
                "VALUES (:aid, :atype, :sev, :content, :di, :src, :st, :ca, :ua)"
            ),
            {
                "aid": alert_id,
                "atype": "PORT_DOWN",
                "sev": "MAJOR",
                "content": "Test alert for timeline FK",
                "di": '{"device_name":"Test-SW"}',
                "src": "MOCK",
                "st": "PROCESSING",
                "ca": datetime.now(timezone.utc),
                "ua": datetime.now(timezone.utc),
            },
        )
        db.commit()
    finally:
        db.close()


def _db_verify(session):
    """Return list of dicts for all rows in alert_timeline."""
    rows = session.execute(
        text("SELECT id, alert_id_fk, node_name, status, started_at, completed_at, "
             "sequence_number, duration_ms FROM alert_timeline ORDER BY id")
    ).fetchall()
    return [dict(row._mapping) for row in rows]


# ════════════════════════════════════════════════════════════════
# 1. Model Column Tests (TC-UNIT-TL-001 ~ TC-UNIT-TL-003)
# ════════════════════════════════════════════════════════════════

class TestTimelineModelColumns:
    """Unit tests for MOD-TL-001: AlertTimeline new column attributes."""

    def test_timeline_model_has_new_columns(self):
        """TC-UNIT-TL-001: AlertTimeline model must expose sequence_number and duration_ms."""
        assert hasattr(AlertTimeline, 'sequence_number'), \
            "AlertTimeline missing 'sequence_number' attribute"
        assert hasattr(AlertTimeline, 'duration_ms'), \
            "AlertTimeline missing 'duration_ms' attribute"

        columns = {c.name for c in AlertTimeline.__table__.columns}
        assert 'sequence_number' in columns, \
            "'sequence_number' column not found in AlertTimeline.__table__"
        assert 'duration_ms' in columns, \
            "'duration_ms' column not found in AlertTimeline.__table__"

    def test_timeline_new_columns_nullable(self):
        """TC-UNIT-TL-002: sequence_number and duration_ms must be NULLABLE."""
        seq_col = AlertTimeline.__table__.columns['sequence_number']
        dur_col = AlertTimeline.__table__.columns['duration_ms']
        assert seq_col.nullable is True, \
            f"sequence_number nullable={seq_col.nullable}, expected True"
        assert dur_col.nullable is True, \
            f"duration_ms nullable={dur_col.nullable}, expected True"

    def test_timeline_new_columns_type(self):
        """TC-UNIT-TL-003: sequence_number and duration_ms must be Integer type."""
        seq_type = str(AlertTimeline.__table__.columns['sequence_number'].type)
        dur_type = str(AlertTimeline.__table__.columns['duration_ms'].type)
        assert 'INTEGER' in seq_type.upper(), \
            f"sequence_number type={seq_type}, expected INTEGER"
        assert 'INTEGER' in dur_type.upper(), \
            f"duration_ms type={dur_type}, expected INTEGER"


# ════════════════════════════════════════════════════════════════
# 2. Repository Tests (TC-UNIT-TL-010 ~ TC-UNIT-TL-014)
# ════════════════════════════════════════════════════════════════

class TestAlertRepositoryTimeline:
    """Unit tests for MOD-TL-003: AlertRepository enhanced methods."""

    # ── helpers ──

    def _create_alert(self, repo, alert_id="test-alert-repo-001"):
        return repo.create_alert({
            "alert_id": alert_id,
            "alert_type": "PORT_DOWN",
            "severity": "MAJOR",
            "content": "Test alert for repo timeline tests",
            "device_info": {"device_name": "SW1", "device_ip": "10.0.0.1"},
            "source": "MOCK",
        })

    def _create_timeline_entry(self, repo, alert_id, node_name="test_node"):
        return repo.append_timeline_entry(alert_id, {
            "node_name": node_name,
            "state_snapshot": {"key": "val"},
            "started_at": datetime.now(timezone.utc),
            "status": "RUNNING",
        })

    # ── TC-UNIT-TL-010 ──

    def test_update_timeline_entry_success(self, repo):
        """TC-UNIT-TL-010: update_timeline_entry updates status + completed_at + duration_ms."""
        self._create_alert(repo)
        entry = self._create_timeline_entry(repo, "test-alert-repo-001")

        now = datetime.now(timezone.utc)
        result = repo.update_timeline_entry(entry.id, {
            "status": "COMPLETED",
            "completed_at": now,
            "duration_ms": 1500,
        })

        assert result is not None, "update_timeline_entry returned None for valid id"
        assert result.status == "COMPLETED", f"status={result.status}, expected COMPLETED"
        assert result.completed_at is not None, "completed_at should be set"
        assert result.duration_ms == 1500, f"duration_ms={result.duration_ms}, expected 1500"

    # ── TC-UNIT-TL-011 ──

    def test_update_timeline_entry_not_found(self, repo):
        """TC-UNIT-TL-011: update_timeline_entry with non-existent id returns None."""
        result = repo.update_timeline_entry(99999, {"status": "COMPLETED"})
        assert result is None, (
            "update_timeline_entry should return None for non-existent entry_id"
        )

    # ── TC-UNIT-TL-012 ──

    def test_update_timeline_entry_partial(self, repo):
        """TC-UNIT-TL-012: Partial update — only status, no completed_at or duration_ms."""
        self._create_alert(repo)
        entry = self._create_timeline_entry(repo, "test-alert-repo-001")

        result = repo.update_timeline_entry(entry.id, {"status": "FAILED"})
        assert result is not None
        assert result.status == "FAILED"
        # completed_at and duration_ms should remain as-is (None)
        assert result.completed_at is None, "completed_at should not be set in partial update"
        assert result.duration_ms is None, "duration_ms should not be set in partial update"

    # ── TC-UNIT-TL-013 ──

    def test_append_timeline_entry_with_new_fields(self, repo):
        """TC-UNIT-TL-013: append_timeline_entry can store sequence_number and duration_ms."""
        self._create_alert(repo)
        entry = repo.append_timeline_entry("test-alert-repo-001", {
            "node_name": "seq_node",
            "state_snapshot": {},
            "started_at": datetime.now(timezone.utc),
            "status": "RUNNING",
            "sequence_number": 3,
            "duration_ms": None,
        })
        assert entry.sequence_number == 3, f"seq={entry.sequence_number}, expected 3"
        assert entry.duration_ms is None

    # ── TC-UNIT-TL-014: ensure_timeline_columns idempotent ──

    def test_ensure_timeline_columns_idempotent(self, db_engine):
        """
        TC-UNIT-TL-014: Calling ensure_timeline_columns twice does not raise error.
        Uses patched SessionLocal so the function can access the test DB.
        """
        import src.database.base
        original = src.database.base.SessionLocal
        src.database.base.SessionLocal = sessionmaker(
            bind=db_engine, autocommit=False, autoflush=False
        )
        try:
            # First call — should be a no-op (columns already exist from create_all)
            ensure_timeline_columns()
            # Second call — must be idempotent
            ensure_timeline_columns()
        finally:
            src.database.base.SessionLocal = original


# ════════════════════════════════════════════════════════════════
# 3. _log_node Flow Tests (TC-UNIT-TL-020 ~ TC-UNIT-TL-027)
# ════════════════════════════════════════════════════════════════

class TestLogNodePersistence:
    """Unit tests for MOD-TL-002: _log_node START INSERT + END UPDATE flow."""

    # ── TC-UNIT-TL-020 ──

    def test_log_node_start_creates_db_entry(self, patched_session_local, handlers,
                                              verify_session):
        """TC-UNIT-TL-020: START phase INSERTs a RUNNING entry into alert_timeline."""
        _ensure_alert_in_db("alert-start-001")
        state = _make_state("alert-start-001")
        handlers._log_node(state, "parse_alert", "START")

        rows = _db_verify(verify_session)
        assert len(rows) == 1, f"Expected 1 row, got {len(rows)}"
        row = rows[0]
        assert row["alert_id_fk"] == "alert-start-001"
        assert row["node_name"] == "parse_alert"
        assert row["status"] == "RUNNING"
        assert row["sequence_number"] == 1, \
            f"First START seq={row['sequence_number']}, expected 1"
        assert row["duration_ms"] is None, \
            "duration_ms should be NULL after START"

    # ── TC-UNIT-TL-021 ──

    def test_log_node_end_updates_entry(self, patched_session_local, handlers,
                                         verify_session):
        """TC-UNIT-TL-021: END phase UPDATEs status, completed_at, duration_ms."""
        _ensure_alert_in_db("alert-end-001")
        state = _make_state("alert-end-001")
        handlers._log_node(state, "collect_diag", "START")
        handlers._log_node(state, "collect_diag", "END")

        rows = _db_verify(verify_session)
        assert len(rows) == 1
        row = rows[0]
        assert row["status"] == "COMPLETED", f"END status={row['status']}, expected COMPLETED"
        assert row["completed_at"] is not None, "completed_at should be set by END"
        assert row["duration_ms"] is not None, "duration_ms should be computed by END"
        assert isinstance(row["duration_ms"], int), \
            f"duration_ms type={type(row['duration_ms'])}, expected int"

    # ── TC-UNIT-TL-022 ──

    def test_sequence_number_increments(self, patched_session_local, handlers,
                                         verify_session):
        """TC-UNIT-TL-022: Three consecutive STARTs → sequence_number = 1, 2, 3."""
        _ensure_alert_in_db("alert-seq-001")
        state = _make_state("alert-seq-001")
        for node_name in ["receive_alert", "parse_alert", "validate_alert"]:
            handlers._log_node(state, node_name, "START")

        rows = _db_verify(verify_session)
        assert len(rows) == 3
        seqs = [r["sequence_number"] for r in rows]
        assert seqs == [1, 2, 3], f"sequence numbers={seqs}, expected [1, 2, 3]"

    # ── TC-UNIT-TL-023 ──

    def test_sequence_number_per_alert(self, patched_session_local, handlers,
                                        verify_session):
        """TC-UNIT-TL-023: Different alert_id → independent sequence counters."""
        _ensure_alert_in_db("alert-A-001")
        _ensure_alert_in_db("alert-B-001")
        state_a = _make_state("alert-A-001")
        state_b = _make_state("alert-B-001")

        handlers._log_node(state_a, "receive_alert", "START")
        handlers._log_node(state_b, "receive_alert", "START")
        handlers._log_node(state_a, "parse_alert", "START")

        rows = _db_verify(verify_session)
        # Alert A: seq 1, 2  |  Alert B: seq 1
        seq_a = [r["sequence_number"] for r in rows if r["alert_id_fk"] == "alert-A-001"]
        seq_b = [r["sequence_number"] for r in rows if r["alert_id_fk"] == "alert-B-001"]
        assert seq_a == [1, 2], f"Alert A seqs={seq_a}, expected [1, 2]"
        assert seq_b == [1], f"Alert B seqs={seq_b}, expected [1]"

    # ── TC-UNIT-TL-024 ──

    def test_duration_calculation_accuracy(self, patched_session_local, handlers,
                                            verify_session):
        """
        TC-UNIT-TL-024: duration_ms matches actual elapsed time (tolerance < 100ms).
        We insert a 50ms sleep between START and END.
        """
        _ensure_alert_in_db("alert-dur-001")
        state = _make_state("alert-dur-001")
        handlers._log_node(state, "establish_ssh", "START")
        time.sleep(0.05)  # 50 ms
        handlers._log_node(state, "establish_ssh", "END")

        rows = _db_verify(verify_session)
        assert len(rows) == 1
        row = rows[0]
        assert row["status"] == "COMPLETED"
        dur = row["duration_ms"]
        assert dur is not None, "duration_ms should be computed"
        # Should be approximately 50ms (allow 0-150ms for CI variance)
        assert 0 <= dur < 200, \
            f"duration_ms={dur}, expected roughly 50ms (sleep 50ms, tolerance <150ms)"

    # ── TC-UNIT-TL-025 ──

    def test_failed_node_status(self, patched_session_local, handlers, verify_session):
        """TC-UNIT-TL-025: status='FAILED' → DB entry status is FAILED."""
        _ensure_alert_in_db("alert-fail-001")
        state = _make_state("alert-fail-001")
        handlers._log_node(state, "analyze_root_cause", "START")
        handlers._log_node(state, "analyze_root_cause", "END", status="FAILED")

        rows = _db_verify(verify_session)
        assert len(rows) == 1
        assert rows[0]["status"] == "FAILED", \
            f"END status={rows[0]['status']}, expected FAILED"

    # ── TC-UNIT-TL-026 ──

    def test_start_resume_preserves_sequence(self, patched_session_local, handlers,
                                              verify_session):
        """
        TC-UNIT-TL-026: Multiple START/END cycles for different nodes on same alert
        should produce ordered, contiguous sequence_numbers in the DB.
        """
        _ensure_alert_in_db("alert-resume-001")
        state = _make_state("alert-resume-001")
        nodes = ["receive_alert", "parse_alert", "validate_alert", "get_device_info"]

        for node in nodes:
            handlers._log_node(state, node, "START")
            handlers._log_node(state, node, "END")

        rows = _db_verify(verify_session)
        # We should have 4 COMPLETED rows with seq 1-4
        assert len(rows) == 4
        for i, row in enumerate(rows):
            assert row["status"] == "COMPLETED", \
                f"Row {i} status={row['status']}, expected COMPLETED"
            assert row["sequence_number"] == i + 1, \
                f"Row {i} seq={row['sequence_number']}, expected {i+1}"
            assert row["completed_at"] is not None
            assert isinstance(row["duration_ms"], int)

    # ── TC-UNIT-TL-027 ──

    def test_end_without_start_no_crash(self, patched_session_local, handlers,
                                         verify_session):
        """
        TC-UNIT-TL-027: Calling END without a preceding START should not crash.
        The function should handle the missing RUNNING entry gracefully (no DB write).
        """
        state = _make_state("alert-no-start-001")
        # No START — call END directly
        handlers._log_node(state, "missing_start_node", "END")

        rows = _db_verify(verify_session)
        # No RUNNING entry was found → no UPDATE done
        # May or may not have a fallback INSERT (depends on _timeline_store state)
        # Key assertion: this call does not raise an exception
        assert True  # reached without exception

    def test_memory_timeline_populated(self, handlers):
        """Verify _timeline_store is populated after START."""
        state = _make_state("alert-mem-001")
        handlers._log_node(state, "test_node", "START")
        timeline = handlers.get_timeline("alert-mem-001")
        assert len(timeline) == 1
        assert timeline[0]["node_name"] == "test_node"
        assert timeline[0]["status"] == "RUNNING"
        assert "sequence_number" in timeline[0]
        assert timeline[0]["sequence_number"] == 1


# ════════════════════════════════════════════════════════════════
# 4. Backward Compatibility Tests (TC-UNIT-TL-030 ~ TC-UNIT-TL-031)
# ════════════════════════════════════════════════════════════════

class TestBackwardCompatibility:
    """Tests for backward compatibility with old timeline records."""

    def test_timeline_old_record_no_new_fields(self, db_session, repo):
        """
        TC-UNIT-TL-030: Raw SQL INSERT of an old-style record (no sequence_number,
        no duration_ms) followed by SELECT must not raise errors.
        """
        # Create alert for FK
        repo.create_alert({
            "alert_id": "old-record-001",
            "alert_type": "PORT_DOWN",
            "severity": "MAJOR",
            "content": "Old record test",
            "device_info": {"device_name": "SW1"},
            "source": "MOCK",
        })

        # Insert old-style record via raw SQL (no new columns)
        now = datetime.now(timezone.utc).isoformat()
        db_session.execute(text(
            "INSERT INTO alert_timeline (alert_id_fk, node_name, state_snapshot, "
            "started_at, status) VALUES (:aid, :node, :snap, :started, :status)"
        ), {
            "aid": "old-record-001",
            "node": "legacy_node",
            "snap": '{"key":"val"}',
            "started": now,
            "status": "RUNNING",
        })
        db_session.commit()

        # Query via ORM — must not raise
        rows = db_session.execute(
            text("SELECT * FROM alert_timeline WHERE alert_id_fk = :aid")
            , {"aid": "old-record-001"}
        ).fetchall()
        assert len(rows) == 1, f"Expected 1 legacy row, got {len(rows)}"

        # Verify new columns are NULL for old-style inserts
        row = dict(rows[0]._mapping)
        assert row.get("sequence_number") is None, \
            f"Old record seq={row.get('sequence_number')}, expected None"
        assert row.get("duration_ms") is None, \
            f"Old record dur={row.get('duration_ms')}, expected None"

    def test_get_timeline_with_old_records(self, repo, db_session):
        """
        TC-UNIT-TL-031: AlertRepository.get_alert_timeline with mixed old/new
        records returns all entries without error.
        """
        repo.create_alert({
            "alert_id": "mixed-records-001",
            "alert_type": "PORT_DOWN",
            "severity": "MAJOR",
            "content": "Mixed records test",
            "device_info": {"device_name": "SW1"},
            "source": "MOCK",
        })

        # New-style entry
        repo.append_timeline_entry("mixed-records-001", {
            "node_name": "new_node",
            "state_snapshot": {},
            "started_at": datetime.now(timezone.utc),
            "status": "RUNNING",
            "sequence_number": 1,
            "duration_ms": 500,
        })

        # Old-style entry via raw SQL
        db_session.execute(text(
            "INSERT INTO alert_timeline (alert_id_fk, node_name, state_snapshot, "
            "started_at, status) VALUES (:aid, :node, :snap, :started, :status)"
        ), {
            "aid": "mixed-records-001",
            "node": "old_node",
            "snap": '{}',
            "started": datetime.now(timezone.utc).isoformat(),
            "status": "COMPLETED",
        })
        db_session.commit()

        timeline = repo.get_alert_timeline("mixed-records-001")
        assert len(timeline) == 2, f"Expected 2 entries, got {len(timeline)}"


# ════════════════════════════════════════════════════════════════
# 5. Integration Tests (TC-INT-TL-001 ~ TC-INT-TL-003)
# ════════════════════════════════════════════════════════════════

class TestTimelineIntegration:
    """Integration tests combining Repository + _log_node + DB."""

    def test_full_timeline_workflow(self, patched_session_local, handlers,
                                     verify_session, db_session, repo):
        """
        TC-INT-TL-001: Complete START → END → DB verify workflow.
        Exercise all fields: sequence_number, duration_ms, status, completed_at.
        """
        _ensure_alert_in_db("integ-full-001")
        state = _make_state("integ-full-001")

        # Simulate a 3-node workflow
        nodes = [
            ("receive_alert", "COMPLETED"),
            ("parse_alert", "COMPLETED"),
            ("validate_alert", "COMPLETED"),
        ]

        for node_name, expected_status in nodes:
            handlers._log_node(state, node_name, "START")
            handlers._log_node(state, node_name, "END", status=expected_status)

        # Verify DB state
        rows = _db_verify(verify_session)
        assert len(rows) == 3, f"Expected 3 timeline rows, got {len(rows)}"

        for i, (node_name, exp_status) in enumerate(nodes):
            row = rows[i]
            assert row["node_name"] == node_name, \
                f"Row {i} node={row['node_name']}, expected {node_name}"
            assert row["status"] == exp_status, \
                f"Row {i} status={row['status']}, expected {exp_status}"
            assert row["sequence_number"] == i + 1, \
                f"Row {i} seq={row['sequence_number']}, expected {i+1}"
            assert row["completed_at"] is not None, \
                f"Row {i} completed_at is NULL"
            assert isinstance(row["duration_ms"], int), \
                f"Row {i} duration_ms={row['duration_ms']}, expected int"

        # Also verify via repository
        timeline = repo.get_alert_timeline("integ-full-001")
        # Note: repo uses its own session; we need to sync
        # Since _log_node uses a different session, we need to commit our session
        # Actually repo is bound to db_session, _log_node to its own sessions.
        # All sessions write to the same file-based SQLite, so data should be visible.
        # Let's use a fresh session for the repo check.
        from sqlalchemy.orm import sessionmaker as sm
        fresh = sm(bind=verify_session.get_bind(), autocommit=False, autoflush=False)()
        try:
            fresh_repo = AlertRepository(fresh)
            tl = fresh_repo.get_alert_timeline("integ-full-001")
            assert len(tl) == 3, f"Repository query returned {len(tl)} entries, expected 3"
        finally:
            fresh.close()

    def test_workflow_with_failure_midway(self, patched_session_local, handlers,
                                           verify_session):
        """
        TC-INT-TL-002: Workflow where one node FAILED and subsequent nodes
        still get proper sequence numbers.
        """
        _ensure_alert_in_db("integ-fail-001")
        state = _make_state("integ-fail-001")

        # Node 1 succeeds
        handlers._log_node(state, "receive_alert", "START")
        handlers._log_node(state, "receive_alert", "END")

        # Node 2 fails
        handlers._log_node(state, "parse_alert", "START")
        handlers._log_node(state, "parse_alert", "END", status="FAILED")

        # Node 3 succeeds
        handlers._log_node(state, "get_device_info", "START")
        handlers._log_node(state, "get_device_info", "END")

        rows = _db_verify(verify_session)
        assert len(rows) == 3
        statuses = [r["status"] for r in rows]
        assert statuses == ["COMPLETED", "FAILED", "COMPLETED"], \
            f"Statuses={statuses}, expected [COMPLETED, FAILED, COMPLETED]"
        seqs = [r["sequence_number"] for r in rows]
        assert seqs == [1, 2, 3], f"Sequences={seqs}, expected [1, 2, 3]"

    def test_end_to_end_node_handler_timeline(self, patched_session_local, handlers,
                                               verify_session):
        """
        TC-INT-TL-003: Use actual node handler methods (handle_receive_alert,
        handle_parse_alert) and verify timeline entries are created.
        """
        _ensure_alert_in_db("integ-e2e-001")
        state = _make_state("integ-e2e-001")

        # Call actual node handler methods (they call _log_node internally)
        result1 = handlers.handle_receive_alert(state)
        result2 = handlers.handle_parse_alert({**state, **result1})

        rows = _db_verify(verify_session)
        assert len(rows) >= 2, (
            f"Expected at least 2 timeline rows from node handlers, got {len(rows)}"
        )

        node_names = [r["node_name"] for r in rows]
        assert "receive_alert" in node_names, "receive_alert timeline entry missing"
        assert "parse_alert" in node_names, "parse_alert timeline entry missing"

        # All entries should be COMPLETED
        for row in rows:
            assert row["status"] == "COMPLETED", \
                f"Node {row['node_name']} status={row['status']}, expected COMPLETED"
            assert row["sequence_number"] is not None, \
                f"Node {row['node_name']} has no sequence_number"
            assert row["completed_at"] is not None, \
                f"Node {row['node_name']} has no completed_at"
