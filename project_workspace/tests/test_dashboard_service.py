"""
Unit tests for MOD-WEB-006: DashboardService fix-success-rate computation.
@author sub_agent_test_engineer
@module MOD-WEB-006
@covers REQ-WEBUI-FUNC-022, REQ-WEBUI-FUNC-023 (fix success rate + distribution)
@test_level UNIT

Verifies the revised口径: success rate is computed from real fix outcomes
(workflow_state.verify_result.verify_passed), not raw alert.status.
"""
import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database.base import Base
from src.database.alert_models import Alert, AlertTimeline  # noqa: F401 (register tables)
from src.database.approval_models import Approval  # noqa: F401 (register table + FK)
from src.services.dashboard_service import DashboardService


# ── Fixtures ────────────────────────────────────────────────────

@pytest.fixture(scope="function")
def db_session():
    """In-memory SQLite with all registered tables."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


# ── Helper ──────────────────────────────────────────────────────

def _add_alert(db, alert_id, alert_type="PORT_DOWN", severity="MAJOR",
               status="PROCESSING", workflow_state=None):
    alert = Alert(
        alert_id=alert_id,
        alert_type=alert_type,
        severity=severity,
        content=f"Test alert {alert_id}",
        device_info={"device_name": "SW1"},
        source="MOCK",
        status=status,
        workflow_state=workflow_state,
    )
    db.add(alert)
    return alert


# ── Tests: fix success rate口径 ─────────────────────────────────

class TestFixSuccessRate:
    def test_success_requires_closed_and_verify_passed(self, db_session):
        service = DashboardService(db_session)
        # 成功：CLOSED + verify_passed=True
        _add_alert(db_session, "a1", status="CLOSED",
                   workflow_state={"verify_result": {"verify_passed": True}})
        # 失败（回滚）：CLOSED + verify_passed=False
        _add_alert(db_session, "a2", status="CLOSED",
                   workflow_state={"verify_result": {"verify_passed": False}})
        # 失败（修复降级/不可修复）：CLOSED + verify_passed=True 但无下发命令
        _add_alert(db_session, "a3", status="CLOSED", workflow_state={
            "verify_result": {"verify_passed": True},
            "fix_plan": {"commands": [], "description": "修复降级：仅执行真实诊断", "template_id": ""},
        })
        # 失败（明确失败）：FAILED
        _add_alert(db_session, "a4", status="FAILED",
                   workflow_state={"verify_result": {"verify_passed": False}})
        # 被拒：REJECTED
        _add_alert(db_session, "a5", status="REJECTED")
        # 处理中：PROCESSING
        _add_alert(db_session, "a6", status="PROCESSING")
        # 未完成：EXPIRED
        _add_alert(db_session, "a7", status="EXPIRED")
        db_session.commit()

        stats = service.get_alert_stats()
        fs = stats["fix_stats"]

        assert fs["success_count"] == 1
        assert fs["failed_count"] == 3  # a2 + a3 + a4
        assert fs["rejected_count"] == 1
        assert fs["processing_count"] == 2  # a6 + a7
        assert fs["total_count"] == 5  # 分母 = 成功 + 失败 + 被拒（不含处理中）
        assert fs["success_rate"] == 20.0  # 1/5

        # 顶层兼容字段
        assert stats["fix_success_rate"] == 20.0
        assert stats["closed_count"] == 1  # 旧字段语义 = 修复成功
        assert stats["failed_count"] == 3
        assert stats["rejected_count"] == 1
        assert stats["processing_count"] == 2

    def test_zero_rate_when_no_decided_outcomes(self, db_session):
        service = DashboardService(db_session)
        _add_alert(db_session, "d1", status="PROCESSING")
        _add_alert(db_session, "d2", status="EXPIRED")
        db_session.commit()

        fs = service.get_alert_stats()["fix_stats"]
        assert fs["success_rate"] == 0.0
        assert fs["total_count"] == 0
        assert fs["processing_count"] == 2

    def test_normalizes_legacy_enum_repr_status(self, db_session):
        service = DashboardService(db_session)
        # 历史数据：status 被存成 "WorkflowStatus.CLOSED" 形式的 enum repr
        _add_alert(db_session, "b1", status="WorkflowStatus.CLOSED",
                   workflow_state={"verify_result": {"verify_passed": True}})
        _add_alert(db_session, "b2", status="WorkflowStatus.FAILED")
        db_session.commit()

        fs = service.get_alert_stats()["fix_stats"]
        assert fs["success_count"] == 1
        assert fs["failed_count"] == 1
        assert fs["total_count"] == 2
        assert fs["success_rate"] == 50.0

    def test_get_fix_success_rate_returns_breakdown(self, db_session):
        service = DashboardService(db_session)
        _add_alert(db_session, "e1", status="CLOSED",
                   workflow_state={"verify_result": {"verify_passed": True}})
        db_session.commit()

        result = service.get_fix_success_rate(None, None)
        assert result["success_count"] == 1
        assert result["total_count"] == 1
        assert result["success_rate"] == 100.0


# ── Tests: distribution fields ──────────────────────────────────

class TestDistributionFields:
    def test_by_type_and_by_severity_returned(self, db_session):
        service = DashboardService(db_session)
        _add_alert(db_session, "c1", alert_type="PORT_DOWN", severity="CRITICAL",
                   status="CLOSED", workflow_state={"verify_result": {"verify_passed": True}})
        _add_alert(db_session, "c2", alert_type="PORT_DOWN", severity="MAJOR",
                   status="CLOSED", workflow_state={"verify_result": {"verify_passed": True}})
        _add_alert(db_session, "c3", alert_type="CPU_HIGH", severity="WARNING",
                   status="FAILED")
        db_session.commit()

        stats = service.get_alert_stats()
        by_type = {x["type"]: x["count"] for x in stats["by_type"]}
        by_severity = {x["severity"]: x["count"] for x in stats["by_severity"]}

        assert by_type == {"PORT_DOWN": 2, "CPU_HIGH": 1}
        assert by_severity == {"CRITICAL": 1, "MAJOR": 1, "WARNING": 1}
        assert stats["total_count"] == 3
