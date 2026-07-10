"""
MOD-016: ConfigManager — Global configuration management.
@author sub_agent_software_developer
@module MOD-016
@implements IFC-016-01, IFC-016-02, IFC-016-03, IFC-016-04
@depends None
@covers REQ-NFUNC-004, REQ-NFUNC-007, REQ-NFUNC-012
"""

import os
import threading
from pathlib import Path
from typing import Any, Optional

import yaml

from src.models.alert import DeviceAuth


# ────────────────────────────────────────────────────
# Default configuration (同 module_design.md MOD-016 默认配置项表)
# ────────────────────────────────────────────────────

DEFAULT_CONFIG: dict[str, Any] = {
    "inspection": {
        "interval_minutes": 5,
    },
    "diagnosis": {
        "timeout_seconds": 30,
        "retry_max": 3,
        "retry_backoff_base": 1.0,
    },
    "alert": {
        "ttl_minutes": 15,
        "dedup_cache_size": 100,
    },
    "rag": {
        "similarity_threshold": 0.6,
        "chroma_persist_path": "./data/chroma_db/",
        "collection_name": "network_knowledge",
        "embedding_model": "text-embedding-3-small",
    },
    "logging": {
        "level": "INFO",
        "audit_enabled": True,
        "operations_log_path": "./logs/",
        "audit_log_path": "./logs/audit.log",
    },
    "devices": {},   # device_name → {ip, username, password, ...}
    "server": {
        "host": "0.0.0.0",
        "port": 8000,
    },
    "templates": {
        "directory": "./resources/templates/",
    },
    "knowledge": {
        "seed_file": "./resources/knowledge/seed_knowledge.json",
    },
}


class ConfigManager:
    """
    全局配置管理器（单例模式，线程安全）。
    实现 IFC-016-01 (get), IFC-016-02 (set), IFC-016-03 (load_config), IFC-016-04 (get_device_credentials).
    """

    _instance: Optional["ConfigManager"] = None
    _lock: threading.Lock = threading.Lock()

    def __new__(cls) -> "ConfigManager":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    instance = super().__new__(cls)
                    instance._config = dict(DEFAULT_CONFIG)
                    instance._config_lock = threading.Lock()
                    cls._instance = instance
        return cls._instance

    # ── IFC-016-01: get(key: str) → Any ──────────────────────

    def get(self, key: str) -> Any:
        """
        读取配置值，支持点号分隔的嵌套 key（如 "inspection.interval_minutes"）。
        若 key 不存在，返回 None。
        """
        parts = key.split(".")
        with self._config_lock:
            current: Any = self._config
            for part in parts:
                if isinstance(current, dict) and part in current:
                    current = current[part]
                else:
                    return None
            return current

    # ── IFC-016-02: set(key: str, value: Any) → None ──────────

    def set(self, key: str, value: Any) -> None:
        """动态更新配置值（运行时生效）。"""
        parts = key.split(".")
        with self._config_lock:
            current: Any = self._config
            for part in parts[:-1]:
                if part not in current:
                    current[part] = {}
                current = current[part]
            current[parts[-1]] = value

    # ── IFC-016-03: load_config(file_path: str) → None ────────

    def load_config(self, file_path: str) -> None:
        """从 YAML/JSON 配置文件加载，深度合并到当前配置。"""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {file_path}")

        with open(path, "r", encoding="utf-8") as f:
            loaded: dict[str, Any] = yaml.safe_load(f) or {}

        with self._config_lock:
            self._deep_merge(self._config, loaded)

    # ── IFC-016-04: get_device_credentials(device_name: str) → DeviceAuth | None ──

    def get_device_credentials(self, device_name: str) -> Optional[DeviceAuth]:
        """查询设备凭据（支持环境变量覆盖密码）。"""
        devices = self.get("devices") or {}
        dev_cfg = devices.get(device_name)
        if dev_cfg is None:
            return None

        username = dev_cfg.get("username", "admin")
        password = os.environ.get(f"DEVICE_{device_name.upper()}_PASSWORD", dev_cfg.get("password", ""))
        enable_password = os.environ.get(
            f"DEVICE_{device_name.upper()}_ENABLE_PASSWORD",
            dev_cfg.get("enable_password", ""),
        )
        port = dev_cfg.get("port", 22)

        return DeviceAuth(
            username=username,
            password=password,
            enable_password=enable_password or None,
            port=port,
        )

    # ── 内部辅助 ──────────────────────────────────────────────

    @staticmethod
    def _deep_merge(base: dict, override: dict) -> dict:
        """递归深度合并两个字典（override 覆盖 base）。"""
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                ConfigManager._deep_merge(base[key], value)
            else:
                base[key] = value
        return base
