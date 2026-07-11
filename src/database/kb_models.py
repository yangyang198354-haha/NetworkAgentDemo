"""
MOD-WEB-003: Knowledge Base Models — knowledge_documents + command_templates tables.
@author sub_agent_software_developer
@module MOD-WEB-003
@implements KnowledgeDocument (knowledge_documents 表), CommandTemplate (command_templates 表)
@covers REQ-WEBUI-FUNC-016, REQ-WEBUI-FUNC-017
"""

from typing import Optional, Any

from sqlalchemy import String, Integer, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class KnowledgeDocument(Base, TimestampMixin):
    """Knowledge base document (fault cases, remediation plans)."""

    __tablename__ = "knowledge_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(
        String(200), nullable=False, comment="文档标题"
    )
    alert_type: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True,
        comment="告警类型分类 MAC_FLAPPING / PORT_DOWN / CPU_HIGH"
    )
    content: Mapped[str] = mapped_column(
        Text, nullable=False, comment="文档内容（Markdown格式）"
    )
    embedding_id: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, comment="Chroma中的embedding文档ID"
    )

    def __repr__(self) -> str:
        return f"<KnowledgeDocument(id={self.id}, title='{self.title}', type='{self.alert_type}')>"


class CommandTemplate(Base, TimestampMixin):
    """Switch command template (YAML + Jinja2 parameters)."""

    __tablename__ = "command_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True, comment="模板名称"
    )
    alert_type: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True, comment="适用告警类型"
    )
    yaml_content: Mapped[str] = mapped_column(
        Text, nullable=False, comment="YAML格式模板内容（含Jinja2变量）"
    )
    parameters: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, comment="参数定义列表"
    )
    embedding_id: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, comment="Chroma中的embedding模板ID"
    )

    def __repr__(self) -> str:
        return f"<CommandTemplate(id={self.id}, name='{self.name}', type='{self.alert_type}')>"
