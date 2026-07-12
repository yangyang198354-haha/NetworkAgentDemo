"""
Unit tests for MOD-016 ConfigManager.
@author sub_agent_test_engineer
@covers REQ-NFUNC-004, REQ-NFUNC-007
"""
import pytest
from src.security.config_manager import ConfigManager, DEFAULT_CONFIG


class TestConfigManager:
    """MOD-016 ConfigManager unit tests."""

    def test_get_nested_key(self):
        """IFC-016-01: get() with dot-separated nested keys."""
        mgr = ConfigManager()
        # Override singleton state for testing
        mgr._config = dict(DEFAULT_CONFIG)
        assert mgr.get("inspection.interval_minutes") == 5
        assert mgr.get("diagnosis.timeout_seconds") == 30
        assert mgr.get("alert.ttl_minutes") == 15

    def test_get_missing_key_returns_none(self):
        """Non-existent keys should return None."""
        mgr = ConfigManager()
        mgr._config = dict(DEFAULT_CONFIG)
        assert mgr.get("nonexistent.key") is None
        assert mgr.get("inspection.nonexistent") is None

    def test_set_and_get(self):
        """IFC-016-02: set() then get() should return the value."""
        mgr = ConfigManager()
        mgr._config = dict(DEFAULT_CONFIG)
        mgr.set("inspection.interval_minutes", 10)
        assert mgr.get("inspection.interval_minutes") == 10

    def test_set_new_key(self):
        """set() should create nested dicts as needed."""
        mgr = ConfigManager()
        mgr._config = dict(DEFAULT_CONFIG)
        mgr.set("new_category.new_key", "new_value")
        assert mgr.get("new_category.new_key") == "new_value"

    def test_default_config_values(self):
        """Default config should contain all expected sections."""
        mgr = ConfigManager()
        mgr._config = dict(DEFAULT_CONFIG)
        assert "inspection" in mgr._config
        assert "diagnosis" in mgr._config
        assert "alert" in mgr._config
        assert "rag" in mgr._config
        assert "logging" in mgr._config
        assert "server" in mgr._config

    def test_get_device_credentials_nonexistent(self):
        """get_device_credentials returns default DeviceAuth for unknown device (fallback)."""
        mgr = ConfigManager()
        mgr._config = dict(DEFAULT_CONFIG)
        result = mgr.get_device_credentials("NonExistentDevice")
        # Now returns default credentials instead of None (SQLite fallback)
        assert result is not None
        assert result.username == "admin"

    def test_deep_merge_preserves_existing(self):
        """Deep merge should preserve existing keys not in override."""
        base = {"a": 1, "b": {"c": 2}}
        override = {"b": {"d": 3}}
        result = ConfigManager._deep_merge(base, override)
        assert result["a"] == 1
        assert result["b"]["c"] == 2
        assert result["b"]["d"] == 3
