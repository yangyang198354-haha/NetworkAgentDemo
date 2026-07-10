"""
Data models for NetworkAgentDemo.
@author sub_agent_software_developer
@module Data Models (shared across all MOD-NNN)
"""

from .enums import (
    AlertType, AlertSeverity, AlertSource, WorkflowStatus,
    RiskLevel, ApprovalStatus, AuditEventType, DocType,
)
from .alert import (
    AlertPayload, AlertReceipt, Alert, DeviceInfo, DeviceAuth,
    RawAlertEvent, RawInspectionEvent,
)
from .state import (
    NetworkAgentState, PendingApproval, ApprovalDecision,
)
from .fix_plan import (
    FixPlan, RootCauseResult, TemplateParams, TemplateMeta,
    TemplateDefinition, ConfigResult, DiagResult, BackupResult,
    RollbackResult, ExecRecord, VerifyResult, KnowledgeRef,
    KnowledgeDocument, KnowledgeBaseResult, RiskAssessment, PendingApprovalRecord,
)

__all__ = [
    # enums
    "AlertType", "AlertSeverity", "AlertSource", "WorkflowStatus",
    "RiskLevel", "ApprovalStatus", "AuditEventType", "DocType",
    # alert
    "AlertPayload", "AlertReceipt", "Alert", "DeviceInfo", "DeviceAuth",
    "RawAlertEvent", "RawInspectionEvent",
    # state
    "NetworkAgentState", "PendingApproval", "ApprovalDecision",
    # fix_plan
    "FixPlan", "RootCauseResult", "TemplateParams", "TemplateMeta",
    "TemplateDefinition", "ConfigResult", "DiagResult", "BackupResult",
    "RollbackResult", "ExecRecord", "VerifyResult", "KnowledgeRef",
    "KnowledgeDocument", "KnowledgeBaseResult", "RiskAssessment", "PendingApprovalRecord",
]
