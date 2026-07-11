"""
MOD-WEB-001: FastAPI dependencies — get_db and get_current_user.
@author sub_agent_software_developer
@module MOD-WEB-001
@implements IFC-WEB-001-02 (JWT dependency injection)

Provides FastAPI Depends functions for database session and JWT authentication.
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from src.database.base import get_db as _db_dependency
from src.database.auth_models import User
from src.services.auth_service import get_user_from_token

# OAuth2 scheme for extracting Bearer token from Authorization header
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


def get_db() -> Session:
    """
    FastAPI dependency: yield a SQLAlchemy Session.
    Wraps the database module's get_db generator.
    """
    yield from _db_dependency()


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """
    FastAPI dependency: validate JWT token and return User object.
    Raises 401 if token is missing, invalid, or expired.
    """
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未提供认证令牌",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = get_user_from_token(token, db)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="令牌无效或已过期",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user
