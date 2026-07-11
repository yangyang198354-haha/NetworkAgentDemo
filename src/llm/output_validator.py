"""
MOD-009: OutputValidator — LLM output security validation layer.
@author sub_agent_software_developer
@module MOD-009
@implements IFC-009-01, IFC-009-02
@depends MOD-015 (AuditLogger — for security alert logging)
@covers REQ-NFUNC-001, REQ-NFUNC-002
"""

import json
import re
from typing import Any, Optional

from loguru import logger

from src.models.enums import AuditEventType
from src.security.audit_logger import AuditLogger


# ────────────────────────────────────────────────────
# CLI 命令黑名单正则（module_design.md MOD-009）
# ────────────────────────────────────────────────────

CLI_BLACKLIST_PATTERN = re.compile(
    r"(interface\s+\S+|shutdown|no\s+shutdown|switchport|vlan\s+\d+|"
    r"reload|configure\s+terminal|router\s+\w+|spanning-tree|"
    r"write\s+memory|copy\s+running)",
    re.IGNORECASE,
)

# 次要 CLI 模式（用于 sanitize_root_cause 的警告，不拒绝）
CLI_WARNING_PATTERN = re.compile(
    r"(show\s+\S+|interface\s+\S+|mac\s+address|processes\s+cpu|running-config)",
    re.IGNORECASE,
)


class ValidationError(Exception):
    """LLM 输出校验失败时抛出。"""
    pass


class OutputValidator:
    """
    LLM 输出安全校验层。

    对 fill_template_params 端点输出:
      - Step 1: JSON 格式校验
      - Step 2: JSON Schema 校验（每个 key 必须在 schema 中，value 类型必须匹配）
      - Step 3: CLI 命令黑名单正则扫描
      - Step 4: 通过则返回纯净参数字典

    对 analyze_root_cause 端点输出:
      - 追加安全标记
      - 检测 CLI 命令片段（warn 但不拒绝）

    实现 IFC-009-01 (validate_params), IFC-009-02 (sanitize_root_cause).
    """

    def __init__(self, audit_logger: Optional[AuditLogger] = None):
        self._audit_logger = audit_logger

    # ── IFC-009-01: validate_params ──────────────────────

    def validate_params(self, raw_output: str, template_params_schema: dict[str, str]) -> dict[str, Any]:
        """
        校验 LLM 的 fill_template_params 输出。

        Args:
            raw_output: LLM 原始输出字符串
            template_params_schema: 模板参数 Schema (key → type, 如 {"iface_name": "string", "max_mac": "integer"})

        Returns:
            校验通过的参数字典

        Raises:
            ValidationError: 任何校验步骤失败
        """
        alerts: list[str] = []

        # Step 1: JSON 格式校验
        try:
            parsed = self._parse_json(raw_output)
        except (json.JSONDecodeError, ValueError) as e:
            raise ValidationError(f"LLM output is not valid JSON: {e}")

        if not isinstance(parsed, dict):
            raise ValidationError(f"LLM output must be a JSON object, got {type(parsed).__name__}")

        # Step 2: JSON Schema 校验（key 存在性 + value 类型匹配）
        for key, value in parsed.items():
            if key not in template_params_schema:
                alerts.append(f"Unknown parameter '{key}' not in template schema")
                continue

            expected_type = template_params_schema[key]
            if not self._check_type(value, expected_type):
                alerts.append(
                    f"Type mismatch for '{key}': expected {expected_type}, "
                    f"got {type(value).__name__} (value={repr(value)[:100]})"
                )

        # 检查必需参数是否都存在
        for param_name in template_params_schema:
            if param_name not in parsed:
                # 某些参数可能是可选的，仅记录
                logger.debug(f"Optional param '{param_name}' not provided by LLM")

        # Step 3: CLI 命令黑名单正则扫描（对每个 string 类型的参数值）
        for key, value in parsed.items():
            if isinstance(value, str):
                match = CLI_BLACKLIST_PATTERN.search(value)
                if match:
                    alert_msg = (
                        f"SECURITY_ALERT: LLM attempted to inject CLI command in parameter "
                        f"'{key}': matched pattern '{match.group()}' in value '{value[:200]}'"
                    )
                    alerts.append(alert_msg)
                    logger.warning(alert_msg)

                    # 记录安全告警到 AuditLogger
                    if self._audit_logger:
                        self._audit_logger.log_audit_event(
                            event_type=AuditEventType.SECURITY_ALERT,
                            alert_id="VALIDATION",
                            operator="OutputValidator",
                            action="CLI_INJECTION_DETECTED",
                            detail={
                                "param_name": key,
                                "matched_pattern": match.group(),
                                "value_snippet": value[:200],
                            },
                        )

        # Step 4: 检查结果
        if alerts:
            # 如果有 CLI 注入告警，拒绝整个输出
            if any("SECURITY_ALERT" in a for a in alerts):
                raise ValidationError(
                    f"LLM output rejected due to security violations:\n" + "\n".join(alerts)
                )
            # 如果只有 type mismatch 等非安全告警，也拒绝
            raise ValidationError(
                f"LLM output validation failed:\n" + "\n".join(alerts)
            )

        logger.info(f"OutputValidator: params validated successfully ({len(parsed)} params)")
        return parsed

    # ── IFC-009-02: sanitize_root_cause ──────────────────

    def sanitize_root_cause(self, raw_output: str) -> str:
        """
        对根因分析输出做安全标记。
        不拒绝包含 CLI 片段的输出（因为分析中引用诊断命令是合理的），
        但追加安全声明并记录 CLI 引用。
        """
        sanitized = raw_output.strip()

        # 检查是否包含 CLI 命令片段
        cli_matches = CLI_WARNING_PATTERN.findall(sanitized)
        if cli_matches:
            cli_terms = list(set(cli_matches))
            logger.info(
                f"OutputValidator: root_cause contains CLI references: {cli_terms[:5]} "
                f"(warn but not reject — diagnostic context is acceptable)"
            )

        # 追加安全标记
        security_marker = (
            "\n\n---\n"
            "[SECURITY: This analysis was generated by LLM, review before acting. "
            "Do not execute any commands based solely on this output.]"
        )

        if "SECURITY:" not in sanitized:
            sanitized += security_marker

        return sanitized

    # ── 内部辅助 ──────────────────────────────────────────

    @staticmethod
    def _parse_json(raw: str) -> Any:
        """解析 JSON，支持 LLM 输出中常见格式问题。"""
        raw = raw.strip()

        # 移除 Markdown 代码块标记
        if raw.startswith("```"):
            lines = raw.split("\n")
            lines = lines[1:] if len(lines) > 1 else lines
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            raw = "\n".join(lines)

        # 定位 JSON 对象边界
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            raw = raw[start:end + 1]

        # 尝试常见修复
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass

        # 尝试修复尾部逗号
        try:
            fixed = re.sub(r",\s*}", "}", raw)
            fixed = re.sub(r",\s*]", "]", fixed)
            return json.loads(fixed)
        except json.JSONDecodeError:
            pass

        # 尝试单引号→双引号（DeepSeek 偶尔输出 Python repr 格式）
        try:
            fixed = raw.replace("'", '"')
            fixed = re.sub(r",\s*}", "}", fixed)
            fixed = re.sub(r",\s*]", "]", fixed)
            return json.loads(fixed)
        except json.JSONDecodeError:
            pass

        # 最后一次尝试
        return json.loads(raw)

    @staticmethod
    def _check_type(value: Any, expected_type: str) -> bool:
        """检查 Python 值是否匹配 Schema 声明的类型。"""
        type_map = {
            "string": str,
            "str": str,
            "integer": int,
            "int": int,
            "number": (int, float),
            "float": (int, float),
            "boolean": bool,
            "bool": bool,
            "list": list,
            "array": list,
        }
        expected = type_map.get(expected_type.lower())
        if expected is None:
            logger.debug(f"Unknown type in schema: {expected_type}")
            return True  # 未知类型不拒绝

        if isinstance(expected, tuple):
            return isinstance(value, expected)
        return isinstance(value, expected)
