"""
MOD-WEB-001: Workflow Router — GET /api/workflow/* (3 endpoints).
@author sub_agent_software_developer
@module MOD-WEB-001
@covers REQ-WEBUI-FUNC-005, REQ-WEBUI-FUNC-006
"""

import sys
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from src.api.dependencies import get_db

workflow_router = APIRouter()

# Node descriptions for the 14-node LangGraph workflow
NODE_DESCRIPTIONS: dict[str, str] = {
    "receive_alert": "接收告警 — 初始化工作流状态",
    "parse_alert": "解析告警 — 提取告警字段和设备信息",
    "validate_alert": "校验告警 — 去重与时效性检查",
    "get_device_info": "获取设备信息 — 查询设备库与凭证",
    "establish_ssh": "建立SSH连接 — 验证凭据格式",
    "collect_diag": "采集诊断 — 执行诊断命令收集数据",
    "analyze_root_cause": "根因分析 — LLM+RAG联合分析",
    "generate_fix_plan": "生成修复方案 — 模板匹配+参数填充",
    "assess_risk": "风险评估 — 确定风险等级与审批需求",
    "human_approval": "人工审批 — 等待运维人员决策",
    "backup_config": "配置备份 — 备份 running-config",
    "execute_fix": "执行修复 — 下发修复命令序列",
    "verify_fix": "验证修复 — 重新诊断对比修复前后状态",
    "finish_report": "生成报告 — LLM生成最终处理报告",
}


# ── GET /api/workflow/graph ────────────────────────────────

@workflow_router.get("/graph")
async def get_workflow_graph(
    current_alert_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """
    Return the LangGraph node topology as a directed graph structure.
    Optionally highlight active nodes for a given alert.
    """
    # Build graph structure from known 14-node topology
    nodes = []
    edges = []

    node_names = list(NODE_DESCRIPTIONS.keys())

    for name in node_names:
        node = {
            "id": name,
            "name": name,
            "label": name.replace("_", " ").title(),
            "description": NODE_DESCRIPTIONS.get(name, ""),
            "status": "inactive",
        }
        nodes.append(node)

    # Define edges matching the StateGraph structure
    edge_list = [
        ("receive_alert", "parse_alert"),
        ("parse_alert", "validate_alert"),
        ("validate_alert", "get_device_info", "校验通过"),
        ("validate_alert", "finish_report", "校验失败"),
        ("get_device_info", "establish_ssh"),
        ("establish_ssh", "collect_diag"),
        ("collect_diag", "analyze_root_cause"),
        ("analyze_root_cause", "generate_fix_plan"),
        ("generate_fix_plan", "assess_risk"),
        ("assess_risk", "human_approval", "需要审批"),
        ("assess_risk", "backup_config", "无需审批"),
        ("human_approval", "backup_config", "批准"),
        ("human_approval", "finish_report", "拒绝"),
        ("backup_config", "execute_fix", "备份成功"),
        ("backup_config", "finish_report", "备份失败"),
        ("execute_fix", "verify_fix"),
        ("verify_fix", "finish_report", "验证通过/失败"),
    ]

    for edge in edge_list:
        edges.append({
            "source": edge[0],
            "target": edge[1],
            "label": edge[2] if len(edge) > 2 else "",
        })

    # If an alert_id is provided, check timeline for active nodes
    if current_alert_id:
        from src.database.repositories.alert_repository import AlertRepository
        repo = AlertRepository(db)
        alert = repo.get_alert_by_id(current_alert_id)
        if alert and alert.status == "PROCESSING":
            timeline = repo.get_alert_timeline(current_alert_id)
            completed_nodes = {t.node_name for t in timeline if t.status == "COMPLETED"}
            running_nodes = {t.node_name for t in timeline if t.status == "RUNNING"}

            for node in nodes:
                if node["id"] in running_nodes:
                    node["status"] = "active"
                elif node["id"] in completed_nodes:
                    node["status"] = "completed"

    return {"nodes": nodes, "edges": edges, "node_count": len(nodes)}


# ── GET /api/workflow/{checkpoint_id}/nodes/{node_name} ────

@workflow_router.get("/{checkpoint_id}/nodes/{node_name}")
async def get_node_state_snapshot(
    checkpoint_id: str,
    node_name: str,
    db: Session = Depends(get_db),
):
    """Return the State snapshot for a specific node in a workflow."""
    main_module = sys.modules.get("src.main")
    if main_module is None:
        raise HTTPException(status_code=503, detail="System not initialized")

    state = main_module.state_graph_engine.get_workflow_state(checkpoint_id)
    return {
        "checkpoint_id": checkpoint_id,
        "node_name": node_name,
        "state": state,
    }


# ── GET /api/workflow/{checkpoint_id}/state ────────────────

@workflow_router.get("/{checkpoint_id}/state")
async def get_workflow_state(checkpoint_id: str, db: Session = Depends(get_db)):
    """Return the current workflow state for a checkpoint."""
    main_module = sys.modules.get("src.main")
    if main_module is None:
        raise HTTPException(status_code=503, detail="System not initialized")

    state = main_module.state_graph_engine.get_workflow_state(checkpoint_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"Workflow state not found: {checkpoint_id}")
    return {"checkpoint_id": checkpoint_id, "state": state}
