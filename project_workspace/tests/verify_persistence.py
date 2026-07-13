"""
Quick end-to-end verification of data persistence fix.
Tests: workflow_state write/read, LLM call log persistence, approval lookup by alert_id.
Uses in-memory SQLite for isolation (no file DB lock issues).
"""
import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_project_root))

import uuid
from datetime import datetime, timezone

from sqlalchemy import create_engine, delete
from sqlalchemy.pool import StaticPool

from src.database.base import Base, init_session
from src.database.alert_models import Alert
from src.database.llm_call_models import LLMCallLog
from src.database.repositories.alert_repository import AlertRepository
from src.database.repositories.approval_repository import ApprovalRepository
from src.database.repositories.llm_call_repository import LLMCallLogRepository


def test_persistence():
    """Verify complete data persistence flow."""
    print("=" * 65)
    print("  Data Persistence Fix -- End-to-End Verification")
    print("=" * 65)

    # Setup: in-memory SQLite
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    init_session(engine)
    # Import SessionLocal AFTER init_session -- it's None until init_session() sets it
    from src.database.base import SessionLocal
    db = SessionLocal()

    test_id = str(uuid.uuid4())

    try:
        print(f"\nTest Alert ID: {test_id}")

        # 1. Create Alert
        print("\n[1/6] Creating alert...")
        repo = AlertRepository(db)
        alert = repo.create_alert({
            "alert_id": test_id,
            "alert_type": "PORT_DOWN",
            "severity": "MAJOR",
            "content": "Interface Gi0/1 on Core-SW-01 is down",
            "device_info": {"device_name": "Core-SW-01", "device_ip": "192.168.1.1"},
            "source": "MOCK",
        })
        assert alert.alert_id == test_id
        assert alert.workflow_state is None
        print("   [PASS] Alert created (workflow_state=NULL)")

        # 2. Write diag_result (simulating collect_diag node)
        print("\n[2/6] Writing diag_result (collect_diag -> DB)...")
        repo.update_workflow_state(test_id, {
            "diag_result": "Interface Gi0/1 is administratively down. "
                           "MAC table shows 0 entries. No link beat detected."
        })
        alert = repo.get_alert_by_id(test_id)
        assert alert.workflow_state is not None
        assert "diag_result" in alert.workflow_state
        print("   [PASS] diag_result persisted")

        # 3. Write root_cause + fix_plan (simulating analyze + generate nodes)
        print("\n[3/6] Writing root_cause + fix_plan "
              "(analyze_root_cause + generate_fix_plan -> DB)...")
        repo.update_workflow_state(test_id, {
            "root_cause": "Port administratively shutdown by operator",
            "knowledge_refs": ["KB-001: Port shutdown recovery procedure"],
        })
        repo.update_workflow_state(test_id, {
            "fix_plan": {
                "template_id": "TPL-001",
                "description": "Re-enable port and configure port-security",
                "commands": ["no shutdown", "switchport port-security maximum 2"],
                "params": {"iface_name": "Gi0/1", "max_mac": 2},
            }
        })
        alert = repo.get_alert_by_id(test_id)
        wf = alert.workflow_state
        assert wf["root_cause"] == "Port administratively shutdown by operator"
        assert wf["fix_plan"]["template_id"] == "TPL-001"
        assert len(wf["fix_plan"]["commands"]) == 2
        print("   [PASS] root_cause + fix_plan persisted (deep merge verified)")

        # 4. Write exec_log + verify_result + final_report
        print("\n[4/6] Writing exec_log + verify_result + final_report...")
        repo.update_workflow_state(test_id, {
            "exec_log": [
                {"command": "no shutdown", "success": True,
                 "output": "Interface Gi0/1 enabled"},
                {"command": "switchport port-security maximum 2", "success": True,
                 "output": "Port-security max set to 2"},
            ]
        })
        repo.update_workflow_state(test_id, {
            "verify_result": {
                "verify_passed": True,
                "comparison_notes": "Interface is up. MAC learning active.",
                "metrics": {"link_status": "up", "mac_count": 1},
            }
        })
        repo.update_workflow_state(test_id, {
            "final_report": "# Alert Resolution Report\n\nAlert resolved successfully.",
            "_completed": True,
        })
        alert = repo.get_alert_by_id(test_id)
        wf = alert.workflow_state
        assert len(wf["exec_log"]) == 2
        assert wf["verify_result"]["verify_passed"] is True
        assert wf["_completed"] is True
        print("   [PASS] exec_log + verify_result + final_report + _completed persisted")

        # 5. Write LLM call logs
        print("\n[5/6] Writing LLM call logs (LLMService -> llm_calls table)...")
        llm_repo = LLMCallLogRepository(db)
        llm_repo.create_log({
            "alert_id_fk": test_id, "endpoint": "analyze_root_cause",
            "elapsed_s": 2.35, "prompt_tokens": 450, "completion_tokens": 200,
            "prompt_summary": "Analyze root cause...",
            "response_summary": "Root cause: Port shutdown.", "is_mock": False,
        })
        llm_repo.create_log({
            "alert_id_fk": test_id, "endpoint": "fill_template_params",
            "elapsed_s": 1.12, "prompt_tokens": 320, "completion_tokens": 80,
            "prompt_summary": "Fill template...",
            "response_summary": '{"iface_name": "Gi0/1"}', "is_mock": True,
        })
        llm_repo.create_log({
            "alert_id_fk": test_id, "endpoint": "generate_report",
            "elapsed_s": 3.01, "prompt_tokens": 600, "completion_tokens": 300,
            "prompt_summary": "Generate report...",
            "response_summary": "# Alert Resolution Report...", "is_mock": False,
        })

        logs = llm_repo.get_logs_by_alert_id(test_id)
        assert len(logs) == 3, f"Expected 3 LLM logs, got {len(logs)}"
        log_dicts = llm_repo.get_logs_by_alert_id_as_dicts(test_id)
        assert len(log_dicts) == 3
        assert log_dicts[0]["endpoint"] == "analyze_root_cause"
        assert log_dicts[0]["prompt_tokens"] == 450
        print("   [PASS] 3 LLM call logs persisted (2 real + 1 mock)")

        # 6. Write approval and query by alert_id
        print("\n[6/6] Writing approval + query by alert_id...")
        approval_repo = ApprovalRepository(db)
        approval_repo.create_approval({
            "alert_id_fk": test_id,
            "checkpoint_id": f"checkpoint_{test_id}",
            "fix_plan": {"template_id": "TPL-001", "commands": ["no shutdown"]},
            "risk_level": "MEDIUM",
            "decision": "APPROVED",
            "decided_by": "admin",
            "note": "Approved: low-impact config change",
        })
        approvals = approval_repo.get_approvals_by_alert_id(test_id)
        assert len(approvals) == 1
        assert approvals[0].risk_level == "MEDIUM"
        assert approvals[0].decision == "APPROVED"
        print("   [PASS] Approval record persisted and queryable by alert_id")

        # 7. Verify API response shape
        print("\n" + "=" * 65)
        print("  Verifying API Response Shape (alerts_router-compatible)")
        print("=" * 65)

        alert = repo.get_alert_by_id(test_id)
        wf = alert.workflow_state or {}

        fp = wf.get("fix_plan")
        fix_plan = {
            "template_id": fp.get("template_id", ""),
            "description": fp.get("description", ""),
            "params": fp.get("params", {}),
        } if fp and isinstance(fp, dict) else None
        commands = fp.get("commands", []) if fp else []

        approvals = approval_repo.get_approvals_by_alert_id(test_id)
        approval_info = None
        if approvals:
            latest = approvals[0]
            approval_info = {
                "need_human_approval": True,
                "approval_status": latest.decision or "NOT_REQUIRED",
                "risk_level": latest.risk_level or "LOW",
                "decision": latest.decision,
            }

        llm_calls = llm_repo.get_logs_by_alert_id_as_dicts(test_id)

        response = {
            "alert": {"alert_id": alert.alert_id, "alert_type": alert.alert_type,
                       "status": alert.status},
            "timeline": [],
            "fix_plan": fix_plan,
            "commands": commands,
            "llm_calls": llm_calls,
            "approval": approval_info,
        }

        # Assertions
        assert response["fix_plan"] is not None, "FAIL: fix_plan should NOT be None!"
        assert response["fix_plan"]["template_id"] == "TPL-001"
        assert len(response["commands"]) == 2
        assert len(response["llm_calls"]) == 3
        assert response["approval"] is not None, "FAIL: approval should NOT be None!"
        assert response["approval"]["risk_level"] == "MEDIUM"

        # Verify workflow_state completeness
        assert "root_cause" in wf
        assert "diag_result" in wf
        assert "exec_log" in wf
        assert "verify_result" in wf
        assert "final_report" in wf
        assert wf["_completed"] is True

        print("\n   [PASS] ALL 12 ASSERTIONS PASSED\n")
        for k, v in response.items():
            if k in ("alert", "timeline"):
                continue
            print(f"   {k}: {v}")
        print()
        print("   workflow_state keys:", list(wf.keys()))
        print()
        print("=" * 65)
        print("  [SUCCESS] Data Persistence Fix -- FULLY VERIFIED")
        print("=" * 65)

    finally:
        db.close()
        engine.dispose()


if __name__ == "__main__":
    test_persistence()
