"""
Unit tests for MOD-014 RiskAssessor.
@author sub_agent_test_engineer
@covers AC-006-05 (port shutdown triggers approval), AC-006-06 (VLAN delete triggers approval)
"""
import pytest
from src.models.fix_plan import FixPlan, RiskAssessment
from src.models.enums import RiskLevel
from src.security.risk_assessor import RiskAssessor


class TestRiskAssessor:
    """MOD-014 RiskAssessor unit tests."""

    def setup_method(self):
        self.assessor = RiskAssessor()

    # ── AC-006-04: Non-high-risk operations should skip approval ──
    def test_low_risk_no_approval(self):
        """Low-risk operations should not require human approval."""
        plan = FixPlan(
            template_id="TPL-DESC-UPDATE",
            params={"iface_name": "Gi0/1", "desc": "Updated description"},
            commands=["description Updated by Agent"],
        )
        result = self.assessor.assess(plan)
        assert result.risk_level == RiskLevel.LOW
        assert result.need_human_approval is False

    # ── AC-006-05: Port shutdown operations MUST trigger approval ──
    def test_shutdown_triggers_high_risk(self):
        """Port shutdown commands should trigger HIGH risk and approval."""
        plan = FixPlan(
            template_id="TPL-PORT-DISABLE",
            params={"iface_name": "Gi0/1"},
            commands=["interface Gi0/1", "shutdown"],
        )
        result = self.assessor.assess(plan)
        assert result.risk_level == RiskLevel.HIGH
        assert result.need_human_approval is True
        assert any("shutdown" in r.lower() for r in result.risk_reasons)

    def test_no_shutdown_is_medium_risk(self):
        """Port no-shutdown commands should be MEDIUM risk (standard recovery op)."""
        plan = FixPlan(
            template_id="TPL-PORT-ENABLE",
            params={"iface_name": "Gi0/1", "desc": "Recovered"},
            commands=["interface Gi0/1", "no shutdown", "description Auto-recovered"],
        )
        result = self.assessor.assess(plan)
        assert result.risk_level == RiskLevel.MEDIUM
        # Single MEDIUM pattern → auto-execute (no approval needed)
        assert result.need_human_approval is False

    # ── AC-006-06: VLAN delete operations MUST trigger approval ──
    def test_vlan_delete_triggers_critical(self):
        """VLAN delete commands should trigger CRITICAL risk."""
        plan = FixPlan(
            template_id="TPL-VLAN-DELETE",
            params={"vlan_id": 100},
            commands=["no vlan 100"],
        )
        result = self.assessor.assess(plan)
        assert result.risk_level == RiskLevel.CRITICAL
        assert result.need_human_approval is True

    def test_reload_triggers_critical(self):
        """Device reload/reboot should trigger CRITICAL risk."""
        plan = FixPlan(
            template_id="TPL-RELOAD",
            params={},
            commands=["reload"],
        )
        result = self.assessor.assess(plan)
        assert result.risk_level == RiskLevel.CRITICAL
        assert result.need_human_approval is True

    def test_ospf_router_config_high_risk(self):
        """Routing protocol changes should trigger HIGH risk."""
        plan = FixPlan(
            template_id="TPL-OSPF",
            params={"process_id": 1},
            commands=["router ospf 1", "network 10.0.0.0 0.0.0.255 area 0"],
        )
        result = self.assessor.assess(plan)
        assert result.risk_level == RiskLevel.HIGH
        assert result.need_human_approval is True

    def test_spanning_tree_medium_risk(self):
        """Spanning-tree changes -> MEDIUM risk, single command -> no approval."""
        plan = FixPlan(
            template_id="TPL-STP",
            params={},
            commands=["spanning-tree vlan 1 priority 4096"],
        )
        result = self.assessor.assess(plan)
        assert result.risk_level == RiskLevel.MEDIUM
        # Single MEDIUM command does NOT trigger approval
        assert result.need_human_approval is False

    def test_multiple_medium_commands_trigger_approval(self):
        """Multiple DIFFERENT MEDIUM-risk patterns should trigger approval."""
        plan = FixPlan(
            template_id="TPL-MIXED-MEDIUM",
            params={},
            commands=[
                "spanning-tree vlan 1 priority 4096",  # MEDIUM: spanning-tree
                "no shutdown",                          # MEDIUM: no shutdown
            ],
        )
        result = self.assessor.assess(plan)
        assert result.risk_level == RiskLevel.MEDIUM
        # Two different MEDIUM patterns → need approval
        assert result.need_human_approval is True

    def test_write_memory_low_risk(self):
        """Write memory operations are LOW risk."""
        plan = FixPlan(
            template_id="TPL-SAVE",
            params={},
            commands=["write memory"],
        )
        result = self.assessor.assess(plan)
        assert result.risk_level == RiskLevel.LOW

    def test_empty_commands_low_risk(self):
        """Empty command list should be LOW risk."""
        plan = FixPlan(
            template_id="TPL-EMPTY",
            params={},
            commands=[],
        )
        result = self.assessor.assess(plan)
        assert result.risk_level == RiskLevel.LOW
        assert result.need_human_approval is False

    def test_multiple_risk_levels_highest_wins(self):
        """When commands match multiple risk levels, the highest should win."""
        plan = FixPlan(
            template_id="TPL-MIXED",
            params={},
            commands=[
                "write memory",     # LOW
                "spanning-tree vlan 1",  # MEDIUM
                "shutdown",         # HIGH
            ],
        )
        result = self.assessor.assess(plan)
        assert result.risk_level == RiskLevel.HIGH
        assert result.need_human_approval is True
        assert "端口 shutdown" in str(result.matched_high_risk_patterns)

    def test_risk_hints_in_plan_appear_in_reasons(self):
        """Template-level risk_hints should appear in the assessment reasons."""
        plan = FixPlan(
            template_id="TPL-TEST",
            params={},
            commands=["description test"],
            risk_hints=["This template modifies critical infrastructure"],
        )
        result = self.assessor.assess(plan)
        assert any("critical infrastructure" in r for r in result.risk_reasons)
