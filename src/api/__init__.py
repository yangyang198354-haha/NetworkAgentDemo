"""
MOD-WEB-001: APIRouterLayer — API Router package init.
@author sub_agent_software_developer
@module MOD-WEB-001
@implements IFC-WEB-001-01, IFC-WEB-001-02
@depends MOD-WEB-002, MOD-WEB-003, MOD-WEB-004, MOD-WEB-005, MOD-WEB-006, MOD-WEB-007
"""

from .dependencies import get_db, get_current_user

from . import inspection_router as _inspection_router_module  # raw module (for test mocking)
from .inspection_router import inspection_router

from .auth_router import auth_router
from .alerts_router import alerts_router
from .workflow_router import workflow_router
from .approvals_router import approvals_router
from .devices_router import devices_router
from .kb_router import kb_router
from .config_router import config_router
from .dashboard_router import dashboard_router

from fastapi import APIRouter, Depends

# Master API router: all /api/* endpoints share JWT protection
api_router = APIRouter(prefix="/api", dependencies=[Depends(get_current_user)])
api_router.include_router(alerts_router, prefix="/alerts", tags=["Alerts"])
api_router.include_router(workflow_router, prefix="/workflow", tags=["Workflow"])
api_router.include_router(approvals_router, prefix="/approvals", tags=["Approvals"])
api_router.include_router(devices_router, prefix="/devices", tags=["Devices"])
api_router.include_router(inspection_router, prefix="/inspection", tags=["Inspection"])
api_router.include_router(kb_router, prefix="/knowledge", tags=["Knowledge Base"])
api_router.include_router(config_router, prefix="/system", tags=["System Config"])
api_router.include_router(dashboard_router, prefix="/dashboard", tags=["Dashboard"])

__all__ = [
    "get_db", "get_current_user",
    "auth_router", "api_router",
    "_inspection_router_module",
]
