"""
MOD-WEB-003: DatabaseManager — Package init.
@author sub_agent_software_developer
@module MOD-WEB-003
@depends None

统一导出所有 SQLAlchemy Model 类 + Base + DB session infrastructure.
"""

from .base import Base, TimestampMixin, get_session_factory, init_db, create_engine, get_db, SessionLocal

# Auth
from .auth_models import User

# Alert
from .alert_models import Alert, AlertTimeline

# Approval
from .approval_models import Approval

# Device
from .device_models import Device, DeviceCredential

# Inspection
from .inspection_models import InspectionRecord

# Knowledge Base
from .kb_models import KnowledgeDocument, CommandTemplate

# Config
from .config_models import SystemConfig, AuditLog

__all__ = [
    "Base", "TimestampMixin",
    "create_engine", "get_session_factory", "init_db", "get_db", "SessionLocal",
    "User", "Alert", "AlertTimeline", "Approval",
    "Device", "DeviceCredential", "InspectionRecord",
    "KnowledgeDocument", "CommandTemplate",
    "SystemConfig", "AuditLog",
]
