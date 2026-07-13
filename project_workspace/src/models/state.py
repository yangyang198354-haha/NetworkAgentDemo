"""
LangGraph State definitions for NetworkAgentDemo.
@author sub_agent_software_developer
@module Data Models (shared)
@implements NetworkAgentState (TypedDict for LangGraph StateGraph)
@fixes D-001: Added pydantic import for BaseModel and Field
"""

from datetime import datetime
from typing import TypedDict, Optional, Any

from pydantic import BaseModel, Field

from .enums import AlertType, AlertSeverity, WorkflowStatus, ApprovalStatus, RiskLevel
from .alert import DeviceInfo
from .fix_plan import FixPlan, ExecRecord, VerifyResult, KnowledgeRef


class NetworkAgentState(TypedDict, total=False):
    """
    LangGraph StateGraph 的状态字典。
    字段按 module_design.md "State 字段的生命周期" 表定义。

    所有字段标记为 Optional（total=False），允许 LangGraph 增量更新。
    """

    # ── 告警基本信息（receive_alert / parse_alert 写入）──
    alert_id: str
    alert_type: str  # AlertType 值（序列化后在 LangGraph checkpoint 中作为 str 存储）
    alert_content: str
    alert_timestamp: str  # ISO8601 格式

    # ── 设备信息（parse_alert / get_device_info 写入）──
    device_info: dict[str, Any]  # DeviceInfo 序列化为 dict

    # ── 校验结果（validate_alert 写入）──
    is_valid: bool

    # ── 诊断结果（collect_diag 写入）──
    diag_commands: list[str]
    diag_result: str

    # ── 根因分析（analyze_root_cause 写入）──
    root_cause: str
    knowledge_refs: list[dict[str, Any]]  # list[KnowledgeRef] 序列化

    # ── 修复方案（generate_fix_plan 写入）──
    fix_plan: dict[str, Any]  # FixPlan 序列化

    # ── 风险评估（assess_risk 写入）──
    need_human_approval: bool
    risk_level: str  # RiskLevel 值

    # ── 审批（human_approval 写入）──
    approval_status: str  # ApprovalStatus 值

    # ── 备份（backup_config 写入）──
    config_backup: str
    backup_id: str

    # ── 执行（execute_fix 写入）──
    exec_log: list[dict[str, Any]]  # list[ExecRecord] 序列化

    # ── 验证（verify_result 写入）──
    verify_result: dict[str, Any]  # VerifyResult 序列化

    # ── 最终报告（final_report 写入）──
    final_report: str
    status: str  # WorkflowStatus 值

    # ── 内部状态标记 ──
    _error_message: str  # 错误信息（非正常路径）


class PendingApproval(BaseModel):
    """IFC-003-04 返回 — 挂起的审批项"""
    checkpoint_id: str
    alert_id: str
    alert_type: str
    alert_content: str
    device_name: str
    fix_plan_summary: str
    risk_level: str
    risk_reasons: list[str]
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ApprovalDecision(BaseModel):
    """IFC-003-03 输入 — 审批决定"""
    checkpoint_id: str
    decision: str  # "APPROVED" | "REJECTED"
    operator: str = "admin"
    comment: str = ""
