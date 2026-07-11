"""
MOD-WEB-003: Auth Models — User table.
@author sub_agent_software_developer
@module MOD-WEB-003
@implements User (users 表)

Stores admin user credentials with bcrypt password hash.
"""

from sqlalchemy import String, Integer
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class User(Base, TimestampMixin):
    """Admin user account (Demo: single 'admin' user)."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, index=True, comment="用户名（Demo仅admin）"
    )
    password_hash: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="bcrypt哈希值 ($2b$12$...)"
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, username='{self.username}')>"
