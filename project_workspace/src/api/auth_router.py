"""
MOD-WEB-001: Auth Router — POST /auth/login, POST /auth/logout.
@author sub_agent_software_developer
@module MOD-WEB-001
@implements IFC-WEB-001-01
@covers REQ-WEBUI-FUNC-025, REQ-WEBUI-FUNC-026
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.api.dependencies import get_db
from src.services.auth_service import authenticate

# IFC-WEB-001-01: Auth router WITHOUT JWT protection (dependencies=[])
auth_router = APIRouter(prefix="/auth", tags=["Authentication"], dependencies=[])


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = 86400


class LogoutResponse(BaseModel):
    message: str = "已登出"


@auth_router.post("/login", response_model=LoginResponse)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    """
    Authenticate user and return JWT access token.
    Uses OAuth2 password flow (application/x-www-form-urlencoded).
    """
    token = authenticate(form_data.username, form_data.password, db)
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )

    return LoginResponse(
        access_token=token,
        token_type="bearer",
        expires_in=86400,
    )


@auth_router.post("/logout", response_model=LogoutResponse)
async def logout():
    """
    User logout endpoint.
    Demo phase: purely client-side token removal; no server-side blacklist.
    """
    return LogoutResponse(message="已登出")
