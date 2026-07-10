"""
Fix plan and tool result data models for NetworkAgentDemo.
@author sub_agent_software_developer
@module Data Models (shared)
@implements IFC-006, IFC-007, IFC-008, IFC-010, IFC-011, IFC-012, IFC-013, IFC-014 data structures
"""

from datetime import datetime
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field


# ────────────────────────────────────────────────────
# MOD-006 LLMService 输出
# ────────────────────────────────────────────────────

class RootCauseResult(BaseModel):
    """IFC-006-01 返回 — 根因分析结果"""
    description: str
    possible_causes: list[str]
    suggested_direction: str


class TemplateParams(BaseModel):
    """IFC-006-02 返回 — LLM 填充的模板参数（原始 JSON 字符串，由 MOD-009 校验后解析）"""
    params: dict[str, str | int | float]


# ────────────────────────────────────────────────────
# MOD-007 TemplateEngine 相关
# ────────────────────────────────────────────────────

class TemplateMeta(BaseModel):
    """IFC-007-02 返回 — 模板元数据"""
    template_id: str
    description: str
    alert_type: str
    params_schema: dict[str, str]  # param_name → type (e.g. {"iface_name": "string"})
    risk_level: str


class TemplateDefinition(BaseModel):
    """IFC-007-03 返回 — 完整模板定义"""
    template_id: str
    description: str
    alert_type: str
    jinja2_template: str
    params_schema: dict[str, str]
    risk_level: str
    risk_hints: list[str] = []


# ────────────────────────────────────────────────────
# MOD-005 修复方案
# ────────────────────────────────────────────────────

class FixPlan(BaseModel):
    """IFC-005-08 输出 — 修复方案"""
    template_id: str
    params: dict[str, str | int | float]
    commands: list[str]
    risk_hints: list[str] = []
    description: str = ""


# ────────────────────────────────────────────────────
# MOD-010 SwitchConfigTool 输出
# ────────────────────────────────────────────────────

class ConfigResult(BaseModel):
    """IFC-010-01 返回 — 配置下发结果"""
    success: bool
    output: str = ""
    error: Optional[str] = None
    commands_executed: int = 0
    commands_failed: int = 0


# ────────────────────────────────────────────────────
# MOD-011 SwitchDiagTool 输出
# ────────────────────────────────────────────────────

class DiagResult(BaseModel):
    """IFC-011-01 返回 — 诊断结果"""
    success: bool
    output: str = ""
    error: Optional[str] = None
    execution_time_ms: int = 0


# ────────────────────────────────────────────────────
# MOD-012 BackupTool 输出
# ────────────────────────────────────────────────────

class BackupResult(BaseModel):
    """IFC-012-01 返回 — 备份结果"""
    success: bool
    backup_id: str = Field(default_factory=lambda: str(uuid4()))
    config: Optional[str] = None
    error: Optional[str] = None


class RollbackResult(BaseModel):
    """IFC-012-02 返回 — 回滚结果"""
    success: bool
    output: str = ""
    error: Optional[str] = None


# ────────────────────────────────────────────────────
# 执行记录与验证结果
# ────────────────────────────────────────────────────

class ExecRecord(BaseModel):
    """单条命令执行记录"""
    command: str
    success: bool
    output: str = ""
    error: Optional[str] = None
    execution_time_ms: int = 0
    was_idempotent_skip: bool = False  # 幂等检查跳过


class VerifyResult(BaseModel):
    """IFC-005-13 输出 — 验证结果"""
    verify_passed: bool
    before_state: str = ""
    after_state: str = ""
    comparison_notes: str = ""


# ────────────────────────────────────────────────────
# MOD-008 / MOD-013 知识库相关
# ────────────────────────────────────────────────────

class KnowledgeRef(BaseModel):
    """IFC-008-01 / IFC-013-01 返回 — 知识库检索结果条目"""
    doc_id: str
    title: str
    content: str
    relevance_score: float = 0.0
    template_id: Optional[str] = None


class KnowledgeDocument(BaseModel):
    """IFC-008-02 输入 — 知识文档"""
    doc_id: str = Field(default_factory=lambda: str(uuid4()))
    title: str
    content: str
    alert_type: str
    doc_type: str  # "case" | "plan" | "template"
    template_id: Optional[str] = None
    metadata: dict = {}


class KnowledgeBaseResult(BaseModel):
    """IFC-013-01 返回 — 知识库检索结果"""
    matches: list[KnowledgeRef]
    count: int = 0


# ────────────────────────────────────────────────────
# MOD-014 RiskAssessor 输出
# ────────────────────────────────────────────────────

class RiskAssessment(BaseModel):
    """IFC-014-01 返回 — 风险评估结果"""
    risk_level: str  # "LOW" | "MEDIUM" | "HIGH" | "CRITICAL"
    need_human_approval: bool
    risk_reasons: list[str] = []
    matched_high_risk_patterns: list[str] = []


# ────────────────────────────────────────────────────
# MOD-015 AuditLogger 查询
# ────────────────────────────────────────────────────

class AuditRecord(BaseModel):
    """IFC-015-03 返回 — 审计记录"""
    record_id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: str
    event_type: str
    alert_id: str
    operator: str = ""
    action: str = ""
    detail: dict = {}


class PendingApprovalRecord(BaseModel):
    """IFC-015-04 / IFC-003-04 返回 — 挂起审批记录"""
    checkpoint_id: str
    alert_id: str
    alert_type: str
    alert_content: str
    device_name: str
    fix_plan_summary: str
    risk_level: str
    risk_reasons: list[str]
    created_at: str
