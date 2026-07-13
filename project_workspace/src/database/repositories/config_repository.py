"""
MOD-WEB-004: ConfigRepository — SystemConfig CRUD operations.
@author sub_agent_software_developer
@module MOD-WEB-004
@implements ConfigRepository (get_all_configs, get_config, upsert_config,
           get_llm_api_key_encrypted, set_llm_api_key_encrypted)
@depends MOD-WEB-003
@covers REQ-WEBUI-FUNC-019, REQ-WEBUI-FUNC-020
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.database.config_models import SystemConfig


class ConfigRepository:
    """Repository for SystemConfig key-value pairs."""

    def __init__(self, db: Session):
        self.db = db

    # ── get_all_configs ─────────────────────────────────────

    def get_all_configs(self) -> list[SystemConfig]:
        """Return all system configuration entries."""
        stmt = select(SystemConfig).order_by(SystemConfig.config_key)
        return list(self.db.execute(stmt).scalars().all())

    # ── get_config ──────────────────────────────────────────

    def get_config(self, key: str) -> SystemConfig | None:
        """Return a single config entry by key."""
        stmt = select(SystemConfig).where(SystemConfig.config_key == key)
        return self.db.execute(stmt).scalar_one_or_none()

    # ── upsert_config ───────────────────────────────────────

    def upsert_config(self, key: str, value: str) -> SystemConfig:
        """Create or update a single config key-value pair."""
        existing = self.get_config(key)
        if existing:
            existing.config_value = value
            existing.updated_at = datetime.now(timezone.utc)
            self.db.commit()
            self.db.refresh(existing)
            return existing
        else:
            cfg = SystemConfig(config_key=key, config_value=value)
            self.db.add(cfg)
            self.db.commit()
            self.db.refresh(cfg)
            return cfg

    def upsert_configs(self, configs: dict[str, str]) -> list[SystemConfig]:
        """Bulk upsert multiple config entries."""
        results = []
        for key, value in configs.items():
            results.append(self.upsert_config(key, str(value)))
        return results

    # ── LLM API Key helpers ─────────────────────────────────

    def get_llm_api_key_encrypted(self) -> str | None:
        """Return the encrypted LLM API Key from system_config."""
        cfg = self.get_config("llm.api_key_encrypted")
        return cfg.config_value if cfg else None

    def set_llm_api_key_encrypted(self, encrypted_token: str) -> None:
        """Store the encrypted LLM API Key."""
        self.upsert_config("llm.api_key_encrypted", encrypted_token)
