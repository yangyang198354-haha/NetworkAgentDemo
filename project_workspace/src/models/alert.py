"""
Alert-related data models for NetworkAgentDemo.
@author sub_agent_software_developer
@module Data Models (shared)
@implements IFC-001, IFC-004 Alert data structures
"""

from datetime import datetime
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field

from .enums import AlertType, AlertSeverity, AlertSource


class DeviceAuth(BaseModel):
    """设备认证凭据 — REQ-NFUNC-004 最小权限账号"""
    username: str
    password: str
    enable_password: Optional[str] = None
    port: int = 22


class DeviceInfo(BaseModel):
    """设备信息 — module_design.md Alert 数据结构中的 DeviceInfo"""
    device_name: str
    device_ip: str
    device_model: Optional[str] = None
    interface_name: Optional[str] = None
    mac_address: Optional[str] = None
    cpu_percent: Optional[float] = None
    device_type: Optional[str] = "MOCK"  # REQ-FUNC-119: MOCK | SIMULATOR


class AlertPayload(BaseModel):
    """IFC-001 Schema — Mock Zabbix Webhook 推送的告警 Payload"""
    alert_name: str = Field(..., description="告警名称，如 'MAC 地址漂移检测'")
    alert_type: str = Field(..., description="告警类型: MAC_FLAPPING | PORT_DOWN | CPU_HIGH")
    alert_severity: str = Field(..., description="告警严重级别")
    alert_host: str = Field(..., description="告警主机名")
    alert_ip: str = Field(..., description="告警主机 IP")
    alert_time: str = Field(..., description="告警时间 ISO8601 格式")
    alert_description: str = Field(..., description="告警详细描述")
    alert_interface: Optional[str] = Field(None, description="相关接口名")
    alert_mac: Optional[str] = Field(None, description="相关 MAC 地址")
    alert_cpu: Optional[float] = Field(None, description="CPU 利用率百分比")
    event_id: Optional[str] = Field(None, description="Zabbix event ID")


class AlertReceipt(BaseModel):
    """IFC-001-01 返回 — Webhook 接收确认"""
    alert_id: str = Field(default_factory=lambda: str(uuid4()))
    status: str  # "ACCEPTED" | "DUPLICATE" | "EXPIRED"


class Alert(BaseModel):
    """标准 Alert 对象 — module_design.md Alert 数据结构（IFC-004 输出）"""
    alert_id: str = Field(default_factory=lambda: str(uuid4()))
    alert_type: AlertType
    alert_severity: AlertSeverity = AlertSeverity.WARNING
    alert_content: str
    alert_timestamp: datetime = Field(default_factory=datetime.utcnow)
    device_info: DeviceInfo
    source: AlertSource = AlertSource.MOCK


class RawAlertEvent(BaseModel):
    """原始 Webhook 事件（MOD-001 → MOD-004 传递）"""
    payload: AlertPayload
    received_at: datetime = Field(default_factory=datetime.utcnow)


class RawInspectionEvent(BaseModel):
    """原始巡检事件（MOD-002 → MOD-004 传递）"""
    device_info: DeviceInfo
    alert_type: AlertType
    alert_content: str
    alert_severity: AlertSeverity = AlertSeverity.WARNING
    detected_at: datetime = Field(default_factory=datetime.utcnow)
