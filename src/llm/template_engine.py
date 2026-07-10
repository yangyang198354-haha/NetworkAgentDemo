"""
MOD-007: TemplateEngine — Deterministic CLI command template rendering engine.
@author sub_agent_software_developer
@module MOD-007
@implements IFC-007-01, IFC-007-02, IFC-007-03
@depends None
@covers REQ-FUNC-011, REQ-FUNC-021, REQ-NFUNC-001, REQ-NFUNC-002
"""

import os
from pathlib import Path
from typing import Any

import yaml
from jinja2.sandbox import SandboxedEnvironment
from loguru import logger

from src.models.fix_plan import TemplateMeta, TemplateDefinition


class TemplateNotFoundError(Exception):
    """模板 ID 不存在时抛出。"""
    pass


class ParamMissingError(Exception):
    """必需参数在 params dict 中缺失时抛出。"""
    pass


class TemplateEngine:
    """
    确定性命令模板拼装引擎。
    使用 Jinja2 SandboxedEnvironment 渲染 CLI 命令模板。
    模板存储在 resources/templates/ 目录下的 YAML 文件中。

    实现 IFC-007-01 (render), IFC-007-02 (list_templates), IFC-007-03 (get_template).
    """

    def __init__(self, templates_dir: str = "./resources/templates/"):
        self._templates_dir = Path(templates_dir)
        self._env = SandboxedEnvironment(
            autoescape=False,       # CLI 命令不需要 HTML 转义
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self._templates_cache: dict[str, TemplateDefinition] = {}
        self._loaded = False

    def load_templates(self) -> int:
        """从模板目录加载所有 YAML 模板文件，返回加载数量。"""
        if not self._templates_dir.exists():
            logger.warning(f"Templates directory not found: {self._templates_dir}")
            return 0

        count = 0
        for yaml_file in self._templates_dir.glob("*.yaml"):
            try:
                with open(yaml_file, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)

                if not isinstance(data, dict):
                    continue

                # 支持单模板文件和批量模板文件（列表格式）
                templates_list = data if isinstance(data, list) else [data]

                for tpl_data in templates_list:
                    if not isinstance(tpl_data, dict):
                        continue

                    tpl_id = tpl_data.get("template_id", "")
                    if not tpl_id:
                        continue

                    definition = TemplateDefinition(
                        template_id=tpl_id,
                        description=tpl_data.get("description", ""),
                        alert_type=tpl_data.get("alert_type", ""),
                        jinja2_template=tpl_data.get("template", ""),
                        params_schema=tpl_data.get("params_schema", {}),
                        risk_level=tpl_data.get("risk_level", "LOW"),
                        risk_hints=tpl_data.get("risk_hints", []),
                    )
                    self._templates_cache[tpl_id] = definition
                    count += 1

            except (yaml.YAMLError, OSError) as e:
                logger.error(f"Failed to load template file {yaml_file}: {e}")

        self._loaded = True
        logger.info(f"TemplateEngine loaded {count} templates from {self._templates_dir}")
        return count

    # ── IFC-007-01: render ─────────────────────────────────

    def render(self, template_id: str, params: dict[str, Any]) -> list[str]:
        """
        使用 Jinja2 渲染模板，输出 CLI 命令列表。
        若 template_id 不存在抛出 TemplateNotFoundError。
        若 params 缺少必需参数抛出 ParamMissingError。
        """
        definition = self.get_template(template_id)

        # 校验必需参数
        for param_name, param_type in definition.params_schema.items():
            if param_name not in params:
                raise ParamMissingError(
                    f"Required parameter '{param_name}' missing for template '{template_id}'"
                )

        # Jinja2 渲染
        try:
            template = self._env.from_string(definition.jinja2_template)
            rendered = template.render(**params)
        except Exception as e:
            logger.error(f"Template render error for '{template_id}': {e}")
            raise

        # 拆分为命令列表（每行一条命令）
        commands = [line.strip() for line in rendered.strip().split("\n") if line.strip()]
        logger.info(f"TemplateEngine rendered {len(commands)} commands for '{template_id}'")
        return commands

    # ── IFC-007-02: list_templates ──────────────────────────

    def list_templates(self, alert_type: str | None = None) -> list[TemplateMeta]:
        """
        列出指定告警类型关联的所有模板元数据。
        若 alert_type 为 None，返回所有模板。
        """
        if not self._loaded:
            self.load_templates()

        result: list[TemplateMeta] = []
        for tpl_id, definition in self._templates_cache.items():
            if alert_type and definition.alert_type.upper() != alert_type.upper():
                continue
            result.append(TemplateMeta(
                template_id=tpl_id,
                description=definition.description,
                alert_type=definition.alert_type,
                params_schema=definition.params_schema,
                risk_level=definition.risk_level,
            ))
        return result

    # ── IFC-007-03: get_template ───────────────────────────

    def get_template(self, template_id: str) -> TemplateDefinition:
        """
        获取模板完整定义。
        若 template_id 不存在抛出 TemplateNotFoundError。
        """
        if not self._loaded:
            self.load_templates()

        if template_id not in self._templates_cache:
            raise TemplateNotFoundError(f"Template '{template_id}' not found in registry")

        return self._templates_cache[template_id]
