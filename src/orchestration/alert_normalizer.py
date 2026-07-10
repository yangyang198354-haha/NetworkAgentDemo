"""
MOD-004: AlertNormalizer — Normalize webhook/inspection events to standard Alert objects.
@author sub_agent_software_developer
@module MOD-004
@implements IFC-004-01, IFC-004-02, IFC-004-03
@depends None
@covers REQ-FUNC-001, REQ-FUNC-003, REQ-FUNC-004, REQ-FUNC-005
@fixes D-004: Replaced deprecated datetime.utcnow() with datetime.now(timezone.utc); added naive/aware timezone compatibility for detected_at
"""

import threading
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import uuid4

from loguru import logger

from src.models.alert import (
    Alert, AlertPayload, AlertReceipt, RawAlertEvent, RawInspectionEvent,
)
from src.models.enums import AlertType, AlertSeverity, AlertSource


class AlertNormalizer:
    """
    告警归一化器，提供 Webhook 事件和巡检事件的标准化转换、去重和时效性检查。

    去重缓存: 使用内存 dict + TTL（手动管理），缓存最近 100 条告警，TTL=15 分钟。
    实际生产可用 cachetools.TTLCache；Demo 阶段使用轻量手动实现以减少依赖。
    """

    def __init__(self, ttl_minutes: int = 15, max_cache_size: int = 100):
        self._ttl: timedelta = timedelta(minutes=ttl_minutes)
        self._max_cache_size: int = max_cache_size
        self._cache: dict[str, datetime] = {}  # dedup_key → first_seen_at
        self._lock: threading.Lock = threading.Lock()

    @staticmethod
    def _make_dedup_key(alert_type: str, device_name: str) -> str:
        """生成去重键：告警类型 + 设备名组合。"""
        return f"{alert_type}::{device_name}"

    # ── IFC-004-03: is_duplicate ────────────────────────────

    def is_duplicate(self, alert: Alert) -> bool:
        """检查告警是否已在近期处理中。"""
        dedup_key = self._make_dedup_key(alert.alert_type, alert.device_info.device_name)
        with self._lock:
            self._evict_expired()
            if dedup_key in self._cache:
                return True
            # 记录到缓存
            self._cache[dedup_key] = datetime.now(timezone.utc)
            if len(self._cache) > self._max_cache_size:
                # 淘汰最旧条目
                oldest_key = min(self._cache, key=lambda k: self._cache[k])
                del self._cache[oldest_key]
            return False

    # ── IFC-004-01: normalize_webhook_event ─────────────────

    def normalize_webhook_event(self, payload: AlertPayload) -> Optional[Alert]:
        """
        将 IFC-001 Schema 的 AlertPayload 归一化为标准 Alert 对象。
        若已去重或过期则返回 None。
        """
        # 时效性检查
        try:
            alert_time = datetime.fromisoformat(payload.alert_time.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            alert_time = datetime.now(timezone.utc)

        # 兼容 naive datetime（无时区 → 视为 UTC）
        if alert_time.tzinfo is None:
            alert_time = alert_time.replace(tzinfo=timezone.utc)

        if datetime.now(timezone.utc) - alert_time > self._ttl:
            logger.info(f"Alert expired: {payload.alert_name} @ {payload.alert_time}")
            return None

        # 确定告警类型
        alert_type = self._map_alert_type(payload.alert_type)

        # 构造标准 Alert
        alert = Alert(
            alert_id=str(uuid4()),
            alert_type=alert_type,
            alert_severity=self._map_severity(payload.alert_severity),
            alert_content=payload.alert_description,
            alert_timestamp=alert_time,
            device_info=self._extract_device_info(payload),
            source=AlertSource.MOCK if payload.event_id is None else AlertSource.ZABBIX,
        )

        # 去重检查
        if self.is_duplicate(alert):
            logger.info(f"Duplicate alert ignored: {payload.alert_name}")
            return None

        logger.info(f"Normalized webhook alert: {alert.alert_type} on {alert.device_info.device_name}")
        return alert

    # ── IFC-004-02: normalize_inspection_event ───────────────

    def normalize_inspection_event(self, event: RawInspectionEvent) -> Optional[Alert]:
        """
        将巡检异常事件归一化为标准 Alert 对象，source 标记为 INSPECTION。
        """
        # 时效性检查（兼容 naive / aware datetime）
        detected_at = event.detected_at
        if detected_at.tzinfo is None:
            detected_at = detected_at.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) - detected_at > self._ttl:
            logger.info(f"Inspection event expired: {event.alert_type} on {event.device_info.device_name}")
            return None

        alert = Alert(
            alert_id=str(uuid4()),
            alert_type=event.alert_type,
            alert_severity=event.alert_severity,
            alert_content=event.alert_content,
            alert_timestamp=event.detected_at,
            device_info=event.device_info,
            source=AlertSource.INSPECTION,
        )

        # 去重检查
        if self.is_duplicate(alert):
            logger.info(f"Duplicate inspection alert ignored: {event.alert_type}")
            return None

        logger.info(f"Normalized inspection alert: {alert.alert_type} on {alert.device_info.device_name}")
        return alert

    # ── 内部辅助 ────────────────────────────────────────────

    def _evict_expired(self) -> None:
        """清理过期缓存条目。"""
        now = datetime.now(timezone.utc)
        expired_keys = [k for k, v in self._cache.items() if now - v > self._ttl]
        for key in expired_keys:
            del self._cache[key]

    @staticmethod
    def _map_alert_type(raw_type: str) -> AlertType:
        """将原始告警类型字符串映射为标准 AlertType 枚举。"""
        raw_upper = raw_type.upper().strip()
        type_map = {
            "MAC_FLAPPING": AlertType.MAC_FLAPPING,
            "MAC 地址漂移": AlertType.MAC_FLAPPING,
            "MACF": AlertType.MAC_FLAPPING,
            "PORT_DOWN": AlertType.PORT_DOWN,
            "端口 DOWN": AlertType.PORT_DOWN,
            "IFDOWN": AlertType.PORT_DOWN,
            "CPU_HIGH": AlertType.CPU_HIGH,
            "CPU 过高": AlertType.CPU_HIGH,
            "CPUHIGH": AlertType.CPU_HIGH,
        }
        return type_map.get(raw_upper, AlertType.PORT_DOWN)

    @staticmethod
    def _map_severity(raw_severity: str) -> AlertSeverity:
        """映射严重级别。"""
        sev_map = {
            "CRITICAL": AlertSeverity.CRITICAL,
            "MAJOR": AlertSeverity.MAJOR,
            "MINOR": AlertSeverity.MINOR,
            "WARNING": AlertSeverity.WARNING,
        }
        return sev_map.get(raw_severity.upper(), AlertSeverity.WARNING)

    @staticmethod
    def _extract_device_info(payload: AlertPayload) -> dict:
        """从 AlertPayload 提取 DeviceInfo 字段。"""
        from src.models.alert import DeviceInfo
        return DeviceInfo(
            device_name=payload.alert_host,
            device_ip=payload.alert_ip,
            interface_name=payload.alert_interface,
            mac_address=payload.alert_mac,
            cpu_percent=payload.alert_cpu,
        )
