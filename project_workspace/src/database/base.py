"""
MOD-WEB-003: DatabaseManager — Base infrastructure.
@author sub_agent_software_developer
@module MOD-WEB-003
@implements IFC-WEB-003-01, IFC-WEB-003-02, IFC-WEB-003-03, IFC-WEB-003-04

Provides SQLAlchemy declarative Base, TimestampMixin, engine/session factory,
and FastAPI dependency `get_db`.
"""

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator

from loguru import logger
from sqlalchemy import create_engine as sa_create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker, Session


class Base(DeclarativeBase):
    """SQLAlchemy declarative base for all ORM models."""
    pass


class TimestampMixin:
    """Mixin providing created_at / updated_at timestamp columns."""
    created_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


# ── IFC-WEB-003-01: create_engine ───────────────────────────

def create_engine(db_path: str = "./data/webui.db") -> Engine:
    """
    Create a SQLAlchemy Engine for SQLite with WAL mode and foreign keys enabled.
    """
    if not os.path.isabs(db_path):
        db_path = os.path.join(os.getcwd(), db_path)

    # Ensure the data directory exists
    db_file = Path(db_path)
    db_file.parent.mkdir(parents=True, exist_ok=True)

    engine = sa_create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        pool_pre_ping=True,
    )

    # Enable WAL mode and foreign keys on each connection
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    logger.info(f"SQLite engine created: {db_path} (WAL mode, FK ON)")
    return engine


# ── IFC-WEB-003-02: get_session_factory ─────────────────────

def get_session_factory(engine: Engine) -> sessionmaker:
    """
    Return a configured sessionmaker bound to the given engine.
    autocommit=False, autoflush=False per PM specification.
    """
    return sessionmaker(bind=engine, autocommit=False, autoflush=False)


# ── Global session factory (initialized at startup) ─────────

SessionLocal: sessionmaker | None = None


def init_session(engine: Engine) -> None:
    """Initialize the global session factory."""
    global SessionLocal
    SessionLocal = get_session_factory(engine)


# ── IFC-WEB-003-03: init_db ─────────────────────────────────

def init_db(engine: Engine) -> None:
    """
    Auto-create all tables using Base.metadata.create_all().
    Suitable for Demo phase; production should use Alembic migrations.

    Per-project convention: incremental column migrations are applied after
    create_all() via idempotent PRAGMA-detected ALTER TABLE ADD COLUMN helpers.
    This keeps the zero-config SQLite-on-startup behavior while safely
    upgrading older databases without requiring the Alembic CLI.
    """
    logger.info("Initializing database — creating all tables...")
    Base.metadata.create_all(engine)
    logger.info(f"Database initialized — {len(Base.metadata.tables)} tables created")

    # MOD-TL-003: Run timeline column migration (idempotent, safe to call multiple times)
    try:
        from src.database.repositories.alert_repository import ensure_timeline_columns
        ensure_timeline_columns()
    except Exception as e:
        logger.warning(f"Timeline column migration skipped: {e}")

    # REAL-DEVICE-002 / 003: Add REAL-device columns on top of existing `devices` table.
    try:
        _ensure_real_device_columns()
    except Exception as e:
        logger.warning(f"REAL-device column migration skipped: {e}")


def _ensure_real_device_columns() -> None:
    """Idempotent migration for REAL-device support on the ORM `devices` table.

    Adds (if missing) three columns declared in ``src.database.device_models.Device``:
      - connection_protocol  VARCHAR(10) NULL   SSH|TELNET|HTTP
      - frp_proxy_host       VARCHAR(100) NULL  "127.0.0.1"  (VPS 端 FRP)
      - frp_proxy_port       INTEGER NULL       6023 / 6022 / ...

    Safe to call on brand-new DBs (create_all already has the columns) and on
    DBs created before REAL-device support landed. Wrapped in try/except per
    the project's migration convention so startup never blocks.
    """
    from loguru import logger as _log

    if SessionLocal is None:
        _log.warning("_ensure_real_device_columns: SessionLocal not initialized, skipping")
        return

    db = SessionLocal()
    try:
        rows = db.execute(text("PRAGMA table_info('devices')")).fetchall()
        existing: set[str] = set()
        for r in rows:
            # Row indexing: (cid, name, type, notnull, dflt_value, pk) — name at pos 1
            existing.add(r[1] if isinstance(r, (tuple, list)) else r.name)

        applied = False
        # connection_protocol: String(10), nullable=True
        if "connection_protocol" not in existing:
            db.execute(text(
                "ALTER TABLE devices ADD COLUMN connection_protocol VARCHAR(10)"
            ))
            _log.info("Migration: devices.connection_protocol added (REAL-DEVICE-002)")
            applied = True
        # frp_proxy_host: String(100), nullable=True
        if "frp_proxy_host" not in existing:
            db.execute(text(
                "ALTER TABLE devices ADD COLUMN frp_proxy_host VARCHAR(100)"
            ))
            _log.info("Migration: devices.frp_proxy_host added (REAL-DEVICE-003)")
            applied = True
        # frp_proxy_port: Integer, nullable=True
        if "frp_proxy_port" not in existing:
            db.execute(text(
                "ALTER TABLE devices ADD COLUMN frp_proxy_port INTEGER"
            ))
            _log.info("Migration: devices.frp_proxy_port added (REAL-DEVICE-003)")
            applied = True

        if applied:
            db.commit()
            _log.info("_ensure_real_device_columns: committed")
        else:
            _log.debug("_ensure_real_device_columns: columns already present, nothing to do")
    except Exception as e:
        _log.warning(f"_ensure_real_device_columns failed (rolled back): {e}")
        db.rollback()
    finally:
        db.close()


# ── IFC-WEB-003-04: get_db (FastAPI Depends) ────────────────

def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency: yield a SQLAlchemy Session, close after request.
    """
    if SessionLocal is None:
        raise RuntimeError("Database not initialized. Call init_session() first.")
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
