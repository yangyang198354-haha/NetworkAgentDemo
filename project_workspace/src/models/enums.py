"""
Enumeration types for NetworkAgentDemo.
@author sub_agent_software_developer
@module Data Models (shared)
"""

from enum import Enum


class AlertType(str, Enum):
    """告警类型 — 对应 REQ-FUNC-001, module_design.md Alert 数据结构"""
    MAC_FLAPPING = "MAC_FLAPPING"
    PORT_DOWN = "PORT_DOWN"
    CPU_HIGH = "CPU_HIGH"
    PORT_SHUTDOWN = "PORT_SHUTDOWN"  # 端口需要隔离关闭（触发审批流程）


class AlertSeverity(str, Enum):
    """告警严重级别"""
    CRITICAL = "CRITICAL"
    MAJOR = "MAJOR"
    MINOR = "MINOR"
    WARNING = "WARNING"


class AlertSource(str, Enum):
    """告警来源

    Values:
        WEBHOOK:    外部 webhook 推送（Zabbix/Prometheus/Grafana/etc.）
        MOCK:       模拟告警（POST /api/alerts/simulate）
        INSPECTION: 巡检发现（定时/手动）
    """
    WEBHOOK = "WEBHOOK"
    MOCK = "MOCK"
    INSPECTION = "INSPECTION"


class WorkflowStatus(str, Enum):
    """工作流状态 — NetworkAgentState.status 的可能值"""
    ACTIVE = "ACTIVE"
    CLOSED = "CLOSED"
    FAILED = "FAILED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class RiskLevel(str, Enum):
    """风险等级 — MOD-014 RiskAssessor 输出"""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ApprovalStatus(str, Enum):
    """审批状态 — MOD-003 Interrupt 恢复后写入"""
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class AuditEventType(str, Enum):
    """审计事件类型 — MOD-015 AuditLogger"""
    CONFIG_CHANGE = "CONFIG_CHANGE"
    APPROVAL_DECISION = "APPROVAL_DECISION"
    ROLLBACK = "ROLLBACK"
    SECURITY_ALERT = "SECURITY_ALERT"
    NODE_START = "NODE_START"
    NODE_END = "NODE_END"


class DocType(str, Enum):
    """知识文档类型 — MOD-008 RAGService 元数据"""
    CASE = "case"
    PLAN = "plan"
    TEMPLATE = "template"


class DeviceType(str, Enum):
    """设备类型 — 区分 Mock 设备和模拟器设备 (REQ-FUNC-101)

    Values:
        MOCK:      Mock 设备，返回预设值的假设备，用于软件测试
        SIMULATOR: 交换机模拟器，具备可交互 SSH 服务
    """
    MOCK = "MOCK"
    SIMULATOR = "SIMULATOR"


class SimulatorStatus(str, Enum):
    """模拟器 SSH 服务运行状态 (REQ-FUNC-121)"""
    RUNNING = "RUNNING"
    STOPPED = "STOPPED"
    ERROR = "ERROR"
