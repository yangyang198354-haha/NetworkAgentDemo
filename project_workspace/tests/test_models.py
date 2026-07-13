"""
Unit tests for data models.
@author sub_agent_software_developer
"""

import pytest
from datetime import datetime

from src.models.alert import AlertPayload, AlertReceipt, Alert, DeviceInfo, DeviceAuth
from src.models.enums import AlertType, AlertSeverity, AlertSource, WorkflowStatus
from src.models.fix_plan import FixPlan, ConfigResult, DiagResult, RiskAssessment


class TestAlertPayload:
    """IFC-001 Schema 测试"""

    def test_valid_payload(self):
        payload = AlertPayload(
            alert_name="MAC 地址漂移检测",
            alert_type="MAC_FLAPPING",
            alert_severity="MAJOR",
            alert_host="Core-SW-01",
            alert_ip="192.168.1.1",
            alert_time="2026-07-10T08:00:00Z",
            alert_description="MAC地址在端口间漂移",
            alert_interface="Gi0/1",
            alert_mac="00:1A:2B:3C:4D:5E",
        )
        assert payload.alert_type == "MAC_FLAPPING"
        assert payload.alert_host == "Core-SW-01"

    def test_minimal_payload(self):
        """最简必填字段。"""
        payload = AlertPayload(
            alert_name="Port Down",
            alert_type="PORT_DOWN",
            alert_severity="CRITICAL",
            alert_host="Switch-01",
            alert_ip="10.0.0.1",
            alert_time="2026-07-10T08:00:00Z",
            alert_description="Interface down",
        )
        assert payload.alert_interface is None
        assert payload.alert_mac is None


class TestAlertDataStructures:
    """Alert、DeviceInfo、DeviceAuth 测试"""

    def test_device_info(self):
        info = DeviceInfo(
            device_name="Core-SW-01",
            device_ip="192.168.1.1",
            device_model="TP-Link T2600G-28TS",
            interface_name="Gi0/1",
        )
        assert info.device_model == "TP-Link T2600G-28TS"

    def test_alert_construction(self):
        alert = Alert(
            alert_type=AlertType.PORT_DOWN,
            alert_severity=AlertSeverity.MAJOR,
            alert_content="Port Gi0/1 is down",
            device_info=DeviceInfo(device_name="SW1", device_ip="1.1.1.1"),
            source=AlertSource.MOCK,
        )
        assert alert.alert_id is not None
        assert len(alert.alert_id) == 36  # UUID length

    def test_alert_receipt(self):
        receipt = AlertReceipt(alert_id="abc-123", status="ACCEPTED")
        assert receipt.status == "ACCEPTED"


class TestFixPlanModels:
    """FixPlan 及相关数据类测试"""

    def test_fix_plan(self):
        plan = FixPlan(
            template_id="TPL-PORT-ENABLE",
            params={"iface_name": "Gi0/1", "desc": "Auto-recovered"},
            commands=["interface Gi0/1", "no shutdown"],
            risk_hints=["端口恢复操作"],
        )
        assert len(plan.commands) == 2

    def test_config_result(self):
        result = ConfigResult(
            success=True,
            output="Commands executed",
            commands_executed=3,
            commands_failed=0,
        )
        assert result.success
        assert result.commands_failed == 0

    def test_diag_result(self):
        result = DiagResult(
            success=True,
            output="show mac address-table output...",
            execution_time_ms=350,
        )
        assert result.execution_time_ms > 0

    def test_risk_assessment(self):
        assessment = RiskAssessment(
            risk_level="HIGH",
            need_human_approval=True,
            risk_reasons=["端口 shutdown 操作"],
            matched_high_risk_patterns=["端口 shutdown"],
        )
        assert assessment.need_human_approval
        assert assessment.risk_level == "HIGH"


class TestEnums:
    """枚举类型测试"""

    def test_alert_types(self):
        assert AlertType.MAC_FLAPPING == "MAC_FLAPPING"
        assert AlertType.PORT_DOWN == "PORT_DOWN"
        assert AlertType.CPU_HIGH == "CPU_HIGH"

    def test_workflow_status(self):
        assert WorkflowStatus.ACTIVE == "ACTIVE"
        assert WorkflowStatus.CLOSED == "CLOSED"
        assert WorkflowStatus.FAILED == "FAILED"
