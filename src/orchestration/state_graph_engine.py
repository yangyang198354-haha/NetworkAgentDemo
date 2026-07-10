"""
MOD-003: StateGraphEngine — LangGraph StateGraph definition and lifecycle management.
@author sub_agent_software_developer
@module MOD-003
@implements IFC-003-01, IFC-003-02, IFC-003-03, IFC-003-04, IFC-003-05
@depends MOD-005 (NodeHandlers)
@covers REQ-FUNC-006, REQ-FUNC-013

Architecture: ADR-001 (Flat Sequential Graph with Conditional Edges)
- 14 nodes + 4 conditional edges + 1 interrupt point
- Synchronous StateGraph (非 async)
- MemorySaver as checkpointer for Interrupt support
"""

from typing import Any, Optional
from uuid import uuid4

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from loguru import logger

from src.models.state import NetworkAgentState, PendingApproval, ApprovalDecision
from src.models.enums import ApprovalStatus, WorkflowStatus
from src.models.alert import Alert
from src.orchestration.node_handlers import NodeHandlers


class StateGraphEngine:
    """
    LangGraph 状态机引擎。

    管理 StateGraph 的定义、编译、执行、中断恢复和状态查询。

    IFC-003-01: build_graph() → CompiledStateGraph
    IFC-003-02: run_workflow(alert) → NetworkAgentState
    IFC-003-03: resume_workflow(checkpoint_id, approval_decision) → NetworkAgentState
    IFC-003-04: get_pending_approvals() → list[PendingApproval]
    IFC-003-05: get_workflow_state(checkpoint_id) → NetworkAgentState | None
    """

    def __init__(self, node_handlers: Optional[NodeHandlers] = None):
        self.handlers = node_handlers or NodeHandlers()
        self._graph = None
        self._checkpointer = MemorySaver()
        self._config: dict[str, Any] = {"configurable": {"thread_id": "default"}}

        # 当前活跃的状态快照（用于查询）
        self._active_states: dict[str, NetworkAgentState] = {}

    # ── IFC-003-01: build_graph ───────────────────────────

    def build_graph(self):
        """
        构建并编译 LangGraph StateGraph。
        14 节点 + 4 条件边 + interrupt_before=["human_approval"]
        """
        logger.info("Building LangGraph StateGraph (14 nodes, 4 conditional edges)")

        # 创建 StateGraph
        workflow = StateGraph(NetworkAgentState)

        # ── 添加 14 个节点 ──
        workflow.add_node("receive_alert", self.handlers.handle_receive_alert)
        workflow.add_node("parse_alert", self.handlers.handle_parse_alert)
        workflow.add_node("validate_alert", self.handlers.handle_validate_alert)
        workflow.add_node("get_device_info", self.handlers.handle_get_device_info)
        workflow.add_node("establish_ssh", self.handlers.handle_establish_ssh)
        workflow.add_node("collect_diag", self.handlers.handle_collect_diag)
        workflow.add_node("analyze_root_cause", self.handlers.handle_analyze_root_cause)
        workflow.add_node("generate_fix_plan", self.handlers.handle_generate_fix_plan)
        workflow.add_node("assess_risk", self.handlers.handle_assess_risk)
        workflow.add_node("human_approval", self.handlers.handle_human_approval)
        workflow.add_node("backup_config", self.handlers.handle_backup_config)
        workflow.add_node("execute_fix", self.handlers.handle_execute_fix)
        workflow.add_node("verify_result", self.handlers.handle_verify_result)
        workflow.add_node("final_report", self.handlers.handle_final_report)

        # ── 设置入口节点 ──
        workflow.set_entry_point("receive_alert")

        # ── 主流程链式边 ──
        workflow.add_edge("receive_alert", "parse_alert")
        workflow.add_edge("parse_alert", "validate_alert")

        # ── CE-001: 告警有效性校验 ──
        workflow.add_conditional_edges(
            "validate_alert",
            self._route_after_validate,
            {
                "get_device_info": "get_device_info",
                "final_report": "final_report",
            },
        )

        # ── 有效告警的主流程 ──
        workflow.add_edge("get_device_info", "establish_ssh")
        workflow.add_edge("establish_ssh", "collect_diag")
        workflow.add_edge("collect_diag", "analyze_root_cause")
        workflow.add_edge("analyze_root_cause", "generate_fix_plan")
        workflow.add_edge("generate_fix_plan", "assess_risk")

        # ── CE-002: 风险评估路由 ──
        workflow.add_conditional_edges(
            "assess_risk",
            self._route_after_risk,
            {
                "human_approval": "human_approval",
                "backup_config": "backup_config",
            },
        )

        # ── CE-003: 备份成功路由 ──
        # backup_config → 成功: execute_fix / 失败: final_report
        workflow.add_conditional_edges(
            "backup_config",
            self._route_after_backup,
            {
                "execute_fix": "execute_fix",
                "final_report": "final_report",
            },
        )

        workflow.add_edge("execute_fix", "verify_result")

        # ── CE-004: 验证结果路由 ──
        workflow.add_conditional_edges(
            "verify_result",
            self._route_after_verify,
            {
                "final_report": "final_report",
                "execute_fix": "execute_fix",  # 验证失败 → 重试修复
            },
        )

        # ── 审批后的路径 ──
        # human_approval 之后根据 approval_status 路由
        workflow.add_conditional_edges(
            "human_approval",
            self._route_after_approval,
            {
                "backup_config": "backup_config",
                "final_report": "final_report",
            },
        )

        # ── 终点 ──
        workflow.add_edge("final_report", END)

        # ── 编译图 ──
        # interrupt_before=["human_approval"]: 在进入 human_approval 节点前挂起
        compiled = workflow.compile(
            checkpointer=self._checkpointer,
            interrupt_before=["human_approval"],
        )

        self._graph = compiled
        logger.info("LangGraph StateGraph compiled successfully")
        return compiled

    # ── IFC-003-02: run_workflow ─────────────────────────

    def run_workflow(self, alert: Alert) -> NetworkAgentState:
        """
        以标准 Alert 为输入启动状态机。
        同步执行直到完成或 Interrupt。
        """
        if self._graph is None:
            self.build_graph()

        # 构造初始状态
        initial_state: NetworkAgentState = {
            "alert_id": alert.alert_id,
            "alert_type": alert.alert_type,
            "alert_content": alert.alert_content,
            "alert_timestamp": alert.alert_timestamp.isoformat() if alert.alert_timestamp else "",
            "device_info": alert.device_info.model_dump() if alert.device_info else {},
            "status": WorkflowStatus.ACTIVE,
        }

        # 为每次运行生成唯一的 thread_id
        thread_id = f"workflow_{alert.alert_id}"
        config = {"configurable": {"thread_id": thread_id}}

        logger.info(f"Starting workflow for alert {alert.alert_id} (type={alert.alert_type})")

        try:
            # 同步执行（非 async）
            final_state = self._graph.invoke(initial_state, config)

            # 缓存最终状态
            self._active_states[thread_id] = final_state
            logger.info(f"Workflow completed for alert {alert.alert_id}: status={final_state.get('status')}")
            return final_state

        except Exception as e:
            logger.error(f"Workflow failed for alert {alert.alert_id}: {e}", exc_info=True)
            # 返回当前已知状态
            current = self._graph.get_state(config)
            if current and current.values:
                return current.values
            return {
                "alert_id": alert.alert_id,
                "status": WorkflowStatus.FAILED,
                "_error_message": str(e),
            }

    # ── IFC-003-03: resume_workflow ──────────────────────

    def resume_workflow(
        self, checkpoint_id: str, approval_decision: ApprovalDecision
    ) -> NetworkAgentState:
        """
        从 Interrupt 检查点恢复执行，传入审批决定。
        """
        if self._graph is None:
            self.build_graph()

        thread_id = f"workflow_{checkpoint_id}"
        config = {"configurable": {"thread_id": thread_id}}

        logger.info(
            f"Resuming workflow {checkpoint_id} with decision: {approval_decision.decision}"
        )

        try:
            # 更新状态中的 approval_status
            self._graph.update_state(
                config,
                {"approval_status": approval_decision.decision},
            )

            # 恢复执行（传入 None 表示从当前检查点继续，不重新调用当前节点）
            final_state = self._graph.invoke(None, config)

            self._active_states[thread_id] = final_state
            logger.info(f"Workflow resumed and completed: {checkpoint_id}")
            return final_state

        except Exception as e:
            logger.error(f"Workflow resume failed for {checkpoint_id}: {e}", exc_info=True)
            current = self._graph.get_state(config)
            if current and current.values:
                return current.values
            return {
                "alert_id": checkpoint_id,
                "status": WorkflowStatus.FAILED,
                "_error_message": str(e),
            }

    # ── IFC-003-04: get_pending_approvals ────────────────

    def get_pending_approvals(self) -> list[PendingApproval]:
        """
        查询所有处于 Interrupt 挂起状态的审批项列表。
        委托给 AuditLogger 的维护列表。
        """
        records = self.handlers.audit_logger.get_pending_approvals()
        approvals: list[PendingApproval] = []
        for rec in records:
            approvals.append(PendingApproval(
                checkpoint_id=rec.checkpoint_id,
                alert_id=rec.alert_id,
                alert_type=rec.alert_type,
                alert_content=rec.alert_content,
                device_name=rec.device_name,
                fix_plan_summary=rec.fix_plan_summary,
                risk_level=rec.risk_level,
                risk_reasons=rec.risk_reasons,
                created_at=rec.created_at,
            ))
        return approvals

    # ── IFC-003-05: get_workflow_state ───────────────────

    def get_workflow_state(self, checkpoint_id: str) -> Optional[NetworkAgentState]:
        """查询指定检查点的当前 State 快照。"""
        thread_id = f"workflow_{checkpoint_id}"

        # 先查缓存
        if thread_id in self._active_states:
            return self._active_states[thread_id]

        # 从 checkpointer 查询
        if self._graph:
            config = {"configurable": {"thread_id": thread_id}}
            state = self._graph.get_state(config)
            if state and state.values:
                return state.values

        return None

    # ── 条件边路由函数 ────────────────────────────────────

    @staticmethod
    def _route_after_validate(state: NetworkAgentState) -> str:
        """CE-001: is_valid=true → get_device_info; false → final_report"""
        is_valid = state.get("is_valid", False)
        route = "get_device_info" if is_valid else "final_report"
        logger.debug(f"CE-001 route_after_validate: is_valid={is_valid} → {route}")
        return route

    @staticmethod
    def _route_after_risk(state: NetworkAgentState) -> str:
        """CE-002: need_human_approval=true → human_approval; false → backup_config"""
        need_approval = state.get("need_human_approval", False)
        route = "human_approval" if need_approval else "backup_config"
        logger.debug(f"CE-002 route_after_risk: need_human_approval={need_approval} → {route}")
        return route

    @staticmethod
    def _route_after_approval(state: NetworkAgentState) -> str:
        """
        human_approval 之后的路径:
          - APPROVED → backup_config
          - REJECTED → final_report
        """
        approval_status = state.get("approval_status", ApprovalStatus.PENDING)
        if approval_status == ApprovalStatus.APPROVED:
            logger.debug("CE-route approval: APPROVED → backup_config")
            return "backup_config"
        else:
            logger.debug("CE-route approval: REJECTED → final_report")
            return "final_report"

    @staticmethod
    def _route_after_verify(state: NetworkAgentState) -> str:
        """
        CE-004: verify_passed=true → final_report; false → final_report (FAILED)
        [ROUTING NOTE: When verify fails, if a backup exists rollback is triggered
         before final status is set. The execute_fix path is used as a safety retry
         mechanism — after one retry attempt through execute_fix → verify_result,
         the second verify failure routes to final_report.]

        Simplified for Demo: both branches route to final_report.
        """
        verify_result = state.get("verify_result", {})
        verify_passed = verify_result.get("verify_passed", False) if verify_result else False
        route = "final_report" if verify_passed else "final_report"
        logger.debug(f"CE-004 route_after_verify: verify_passed={verify_passed} → {route}")
        return route

    @staticmethod
    def _route_after_backup(state: NetworkAgentState) -> str:
        """CE-003: backup_success=true → execute_fix; false → final_report"""
        backup_success = state.get("_backup_success", False)
        route = "execute_fix" if backup_success else "final_report"
        logger.debug(f"CE-003 route_after_backup: backup_success={backup_success} → {route}")
        return route
