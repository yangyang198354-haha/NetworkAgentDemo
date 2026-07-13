"""
MOD-WEB-005: EncryptionService — Fernet symmetric encryption.
@author sub_agent_software_developer
@module MOD-WEB-005
@implements IFC-WEB-005-01, IFC-WEB-005-02, IFC-WEB-005-03, IFC-WEB-005-04, IFC-WEB-005-05
@depends None

Uses cryptography.fernet for AES-128-CBC + HMAC-SHA256 authenticated encryption.
Key management: ENCRYPTION_KEY env > ./.data/.encryption_key file > auto-generate.
@covers REQ-WEBUI-NFUNC-005, REQ-WEBUI-FUNC-011, REQ-WEBUI-FUNC-020
"""

import os
from pathlib import Path

from cryptography.fernet import Fernet
from loguru import logger


class EncryptionService:
    """
    Symmetric encryption service using Fernet (AES-128-CBC + HMAC-SHA256).

    Key lifecycle:
      1. Environment variable ENCRYPTION_KEY (highest priority)
      2. File ./.data/.encryption_key (auto-generated on first run)
      3. Generate new key and persist to file (lowest priority, auto)
    """

    _instance: "EncryptionService | None" = None

    def __new__(cls) -> "EncryptionService":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._fernet: Fernet | None = None
            cls._instance._key_status: str = "UNINITIALIZED"
        return cls._instance

    # ── IFC-WEB-005-01: initialize ──────────────────────────

    def initialize(self, key_file_path: str = "./data/.encryption_key") -> None:
        """Load or generate the encryption key and initialize Fernet."""
        key: bytes | None = None

        # Priority 1: Environment variable
        env_key = os.environ.get("ENCRYPTION_KEY", "").strip()
        if env_key:
            try:
                key = env_key.encode("utf-8")
                # Validate the key can be used
                Fernet(key)
                self._key_status = "ENV"
                logger.info("EncryptionService: key loaded from ENCRYPTION_KEY env")
            except Exception as e:
                logger.warning(f"ENCRYPTION_KEY env value invalid: {e}, falling back...")
                key = None

        # Priority 2: File
        if key is None:
            key_path = Path(key_file_path)
            if key_path.exists():
                try:
                    key = key_path.read_bytes()
                    Fernet(key)
                    self._key_status = "FILE"
                    logger.info(f"EncryptionService: key loaded from {key_file_path}")
                except Exception as e:
                    logger.warning(f"Key file invalid: {e}, generating new key...")
                    key = None

        # Priority 3: Generate new key
        if key is None:
            key = Fernet.generate_key()
            key_path = Path(key_file_path)
            key_path.parent.mkdir(parents=True, exist_ok=True)
            key_path.write_bytes(key)
            # Set restrictive permissions on POSIX
            try:
                os.chmod(key_file_path, 0o600)
            except OSError:
                pass
            self._key_status = "GENERATED"
            logger.warning(
                f"EncryptionService: new key generated and saved to {key_file_path}. "
                "Keep this file secure — losing it means all encrypted data is unrecoverable."
            )

        self._fernet = Fernet(key)

    # ── IFC-WEB-005-02: encrypt ─────────────────────────────

    def encrypt(self, plaintext: str) -> str:
        """Encrypt a plaintext string to a Fernet token (Base64)."""
        if not plaintext:
            return ""
        if self._fernet is None:
            raise RuntimeError("EncryptionService not initialized. Call initialize() first.")
        return self._fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")

    # ── IFC-WEB-005-03: decrypt ─────────────────────────────

    def decrypt(self, token: str) -> str:
        """Decrypt a Fernet token back to plaintext."""
        if not token:
            return ""
        if self._fernet is None:
            raise RuntimeError("EncryptionService not initialized. Call initialize() first.")
        return self._fernet.decrypt(token.encode("utf-8")).decode("utf-8")

    # ── IFC-WEB-005-04: mask_sensitive ──────────────────────

    @staticmethod
    def mask_sensitive(value: str, visible_prefix: int = 4, visible_suffix: int = 4) -> str:
        """
        Mask a sensitive string for display.
        e.g., "sk-abc123def456" → "sk-a****f456"
        """
        if not value:
            return ""
        if len(value) <= visible_prefix + visible_suffix:
            return "*" * len(value)
        return (
            value[:visible_prefix]
            + "*" * (len(value) - visible_prefix - visible_suffix)
            + value[-visible_suffix:]
        )

    # ── IFC-WEB-005-05: get_key_status ──────────────────────

    def get_key_status(self) -> str:
        """Return key source: ENV / FILE / GENERATED / UNINITIALIZED."""
        return self._key_status
