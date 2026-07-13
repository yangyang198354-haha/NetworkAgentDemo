"""
MOD-WEB-002: AuthService — JWT token management and bcrypt password hashing.
@author sub_agent_software_developer
@module MOD-WEB-002
@implements IFC-WEB-002-01, IFC-WEB-002-02, IFC-WEB-002-03, IFC-WEB-002-04, IFC-WEB-002-05
@depends MOD-WEB-003 (User model)

JWT config: HS256, 24h expiration, no refresh token (per PM decision D7).
Passwords: bcrypt via passlib, cost factor 12.
admin user: auto-created on first startup with password from ADMIN_PASSWORD env or default 'admin'.
@covers REQ-WEBUI-FUNC-025, REQ-WEBUI-FUNC-026, REQ-WEBUI-NFUNC-003, REQ-WEBUI-NFUNC-004
"""

import os
import secrets
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from loguru import logger
import bcrypt as _bcrypt_lib
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.database.auth_models import User

# ── JWT Configuration Constants ────────────────────────────

_SECRET_KEY: str | None = None
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_SECONDS = 86400  # 24 hours (PM decision D7)


def _get_secret_key() -> str:
    """Get or generate the JWT secret key."""
    global _SECRET_KEY
    if _SECRET_KEY is None:
        _SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "").strip()
        if not _SECRET_KEY:
            _SECRET_KEY = secrets.token_hex(32)
            logger.warning(
                "JWT_SECRET_KEY not set in environment. "
                f"Generated random key: {_SECRET_KEY[:8]}... "
                "Set JWT_SECRET_KEY env variable for persistence across restarts."
            )
        else:
            logger.info("JWT_SECRET_KEY loaded from environment variable")
    return _SECRET_KEY


# ── IFC-WEB-002-04: hash_password ──────────────────────────

def hash_password(password: str) -> str:
    """Hash a plaintext password using bcrypt (cost factor 12)."""
    return _bcrypt_lib.hashpw(password.encode("utf-8"), _bcrypt_lib.gensalt(12)).decode("utf-8")


# ── IFC-WEB-002-05: verify_password ────────────────────────

def verify_password(password: str, password_hash: str) -> bool:
    """Verify a plaintext password against a bcrypt hash."""
    return _bcrypt_lib.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


# ── IFC-WEB-002-01: authenticate ───────────────────────────

def authenticate(username: str, password: str, db: Session) -> str | None:
    """
    Authenticate a user by username and password.
    Returns JWT access_token on success, None on failure.
    """
    stmt = select(User).where(User.username == username)
    user = db.execute(stmt).scalar_one_or_none()

    if user is None:
        return None

    if not verify_password(password, user.password_hash):
        return None

    # Build JWT
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user.username,
        "iat": now,
        "exp": now + timedelta(seconds=ACCESS_TOKEN_EXPIRE_SECONDS),
        "type": "access",
    }
    secret = _get_secret_key()
    token = jwt.encode(payload, secret, algorithm=ALGORITHM)
    return token


# ── IFC-WEB-002-02: get_user_from_token ────────────────────

def get_user_from_token(token: str, db: Session) -> User | None:
    """
    Decode and validate a JWT token, returning the User object.
    Returns None if token is invalid or expired.
    """
    secret = _get_secret_key()
    try:
        payload = jwt.decode(token, secret, algorithms=[ALGORITHM])
        username: str | None = payload.get("sub")
        if username is None:
            return None
    except JWTError:
        return None

    stmt = select(User).where(User.username == username)
    user = db.execute(stmt).scalar_one_or_none()
    return user


# ── IFC-WEB-002-03: init_admin_user ────────────────────────

def init_admin_user(db: Session) -> None:
    """
    Ensure the admin user exists in the database.
    If not, create it with password from ADMIN_PASSWORD env or default 'admin'.
    Idempotent — does nothing if admin already exists.
    """
    stmt = select(User).where(User.username == "admin")
    existing = db.execute(stmt).scalar_one_or_none()

    if existing is None:
        password = os.environ.get("ADMIN_PASSWORD", "admin").strip()
        if not password:
            password = "admin"
            logger.warning("ADMIN_PASSWORD not set, using default password 'admin'")

        hashed = hash_password(password)
        user = User(username="admin", password_hash=hashed)
        db.add(user)
        db.commit()
        logger.info("Admin user created (password hashed with bcrypt)")
    else:
        logger.info("Admin user already exists, skipping creation")
