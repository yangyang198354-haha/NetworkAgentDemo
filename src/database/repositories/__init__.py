"""
MOD-WEB-004: DataAccessLayer — Repository package init.
@author sub_agent_software_developer
@module MOD-WEB-004
@depends MOD-WEB-003

Unified export of all 7 repository classes.
"""

from .alert_repository import AlertRepository
from .approval_repository import ApprovalRepository
from .device_repository import DeviceRepository
from .inspection_repository import InspectionRepository
from .knowledge_repository import KnowledgeRepository
from .config_repository import ConfigRepository
from .audit_log_repository import AuditLogRepository

__all__ = [
    "AlertRepository",
    "ApprovalRepository",
    "DeviceRepository",
    "InspectionRepository",
    "KnowledgeRepository",
    "ConfigRepository",
    "AuditLogRepository",
]
