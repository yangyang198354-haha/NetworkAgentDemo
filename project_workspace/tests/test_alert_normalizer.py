"""
Unit tests for MOD-004 AlertNormalizer.
@author sub_agent_software_developer
"""

import pytest
from datetime import datetime, timezone

from src.models.alert import AlertPayload, Alert, DeviceInfo, RawInspectionEvent
from src.models.enums import AlertType, AlertSeverity, AlertSource
from src.orchestration.alert_normalizer import AlertNormalizer


class TestAlertNormalizer:
    """MOD-004 AlertNormalizer 测试"""

    def setup_method(self):
        self.normalizer = AlertNormalizer(ttl_minutes=15, max_cache_size=100)

    def test_normalize_webhook_event(self):
        payload = AlertPayload(
            alert_name="MAC 漂移告警",
            alert_type="MAC_FLAPPING",
            alert_severity="MAJOR",
            alert_host="Core-SW-01",
            alert_ip="192.168.1.1",
            alert_time=datetime.now(timezone.utc).isoformat(),
            alert_description="MAC 地址在端口 Gi0/1 和 Gi0/2 之间漂移",
            alert_interface="Gi0/1",
            alert_mac="00:1A:2B:3C:4D:5E",
        )

        alert = self.normalizer.normalize_webhook_event(payload)
        assert alert is not None
        assert alert.alert_type == AlertType.MAC_FLAPPING
        assert alert.device_info.device_name == "Core-SW-01"
        assert alert.source == AlertSource.WEBHOOK

    def test_normalize_expired_alert(self):
        """过期告警应返回 None。"""
        payload = AlertPayload(
            alert_name="Old Alert",
            alert_type="PORT_DOWN",
            alert_severity="CRITICAL",
            alert_host="SW1",
            alert_ip="1.1.1.1",
            alert_time="2020-01-01T00:00:00Z",
            alert_description="Old port down alert",
        )

        alert = self.normalizer.normalize_webhook_event(payload)
        assert alert is None

    def test_duplicate_detection(self):
        """重复告警第二次应返回 None。"""
        payload = AlertPayload(
            alert_name="Dup Alert",
            alert_type="CPU_HIGH",
            alert_severity="WARNING",
            alert_host="Core-SW-01",
            alert_ip="192.168.1.1",
            alert_time=datetime.now(timezone.utc).isoformat(),
            alert_description="CPU high",
        )

        alert1 = self.normalizer.normalize_webhook_event(payload)
        assert alert1 is not None

        alert2 = self.normalizer.normalize_webhook_event(payload)
        assert alert2 is None  # 去重

    def test_normalize_inspection_event(self):
        event = RawInspectionEvent(
            device_info=DeviceInfo(device_name="SW1", device_ip="1.1.1.1"),
            alert_type=AlertType.PORT_DOWN,
            alert_content="Port down detected",
        )

        alert = self.normalizer.normalize_inspection_event(event)
        assert alert is not None
        assert alert.source == AlertSource.INSPECTION
        assert alert.alert_type == AlertType.PORT_DOWN

    def test_type_mapping_chinese(self):
        """中文告警类型映射。"""
        payload = AlertPayload(
            alert_name="测试",
            alert_type="端口 DOWN",
            alert_severity="CRITICAL",
            alert_host="SW1",
            alert_ip="1.1.1.1",
            alert_time=datetime.now(timezone.utc).isoformat(),
            alert_description="端口down",
        )

        alert = self.normalizer.normalize_webhook_event(payload)
        assert alert.alert_type == AlertType.PORT_DOWN
