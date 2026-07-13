"""
Unit tests for MOD-009 OutputValidator.
@author sub_agent_software_developer
"""

import pytest

from src.llm.output_validator import OutputValidator, ValidationError


class TestOutputValidator:
    """MOD-009 OutputValidator 测试"""

    def setup_method(self):
        self.validator = OutputValidator()

    def test_validate_valid_params(self):
        """正常参数应通过校验。"""
        raw = '{"iface_name": "Gi0/1", "max_mac": 2, "violation_mode": "restrict"}'
        schema = {"iface_name": "string", "max_mac": "integer", "violation_mode": "string"}
        result = self.validator.validate_params(raw, schema)
        assert result == {"iface_name": "Gi0/1", "max_mac": 2, "violation_mode": "restrict"}

    def test_validate_rejects_cli_injection(self):
        """包含 CLI 命令的参数值应被拒绝。"""
        raw = '{"iface_name": "interface Gi0/1\\n shutdown", "max_mac": 2}'
        schema = {"iface_name": "string", "max_mac": "integer"}

        with pytest.raises(ValidationError, match="SECURITY_ALERT"):
            self.validator.validate_params(raw, schema)

    def test_validate_rejects_invalid_json(self):
        """非法 JSON 应抛出 ValidationError。"""
        with pytest.raises(ValidationError, match="not valid JSON"):
            self.validator.validate_params("not json at all", {"key": "string"})

    def test_validate_rejects_unknown_param(self):
        """不在 schema 中的参数应被检测。"""
        raw = '{"unknown_key": "value"}'
        schema = {"iface_name": "string"}

        with pytest.raises(ValidationError, match="Unknown parameter"):
            self.validator.validate_params(raw, schema)

    def test_validate_rejects_type_mismatch(self):
        """类型不匹配应被检测。"""
        raw = '{"max_mac": "not_a_number"}'
        schema = {"max_mac": "integer"}

        with pytest.raises(ValidationError, match="Type mismatch"):
            self.validator.validate_params(raw, schema)

    def test_validate_markdown_json(self):
        """带 Markdown 代码块的 JSON 应被解析。"""
        raw = '```json\n{"iface_name": "Gi0/2", "desc": "test"}\n```'
        schema = {"iface_name": "string", "desc": "string"}
        result = self.validator.validate_params(raw, schema)
        assert result["iface_name"] == "Gi0/2"

    def test_validate_trailing_comma(self):
        """尾部逗号的 JSON 应被修复。"""
        raw = '{"iface_name": "Gi0/1",}'
        schema = {"iface_name": "string"}
        result = self.validator.validate_params(raw, schema)
        assert result["iface_name"] == "Gi0/1"

    def test_sanitize_root_cause_adds_marker(self):
        """sanitize_root_cause 应追加安全标记。"""
        raw = "这是根因分析结果。可能原因是端口配置错误。"
        result = self.validator.sanitize_root_cause(raw)
        assert "SECURITY:" in result
        assert "review before acting" in result.lower()

    def test_sanitize_already_has_marker(self):
        """已包含安全标记的不应重复追加。"""
        raw = "分析结果\n\n[SECURITY: ...]"
        result = self.validator.sanitize_root_cause(raw)
        assert result.count("[SECURITY:") == 1

    def test_cli_blacklist_matches_shutdown(self):
        """CLI 黑名单应匹配 shutdown 命令。"""
        raw = '{"desc": "需要执行 no shutdown 恢复端口"}'
        schema = {"desc": "string"}

        with pytest.raises(ValidationError, match="SECURITY_ALERT"):
            self.validator.validate_params(raw, schema)

    def test_cli_blacklist_matches_reload(self):
        """CLI 黑名单应匹配 reload 命令。"""
        raw = '{"action": "设备 reload 后恢复"}'
        schema = {"action": "string"}

        with pytest.raises(ValidationError, match="SECURITY_ALERT"):
            self.validator.validate_params(raw, schema)
