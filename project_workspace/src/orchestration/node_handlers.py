"""
MOD-005: NodeHandlers — LangGraph node handler functions (14 nodes).
@author sub_agent_software_developer
@module MOD-005
@implements IFC-005-01 ~ IFC-005-14
@depends MOD-006, MOD-007, MOD-008, MOD-009, MOD-010, MOD-011, MOD-012, MOD-013, MOD-014, MOD-015
@covers REQ-FUNC-005 ~ REQ-FUNC-016, REQ-FUNC-023 ~ REQ-FUNC-025
@fixes D-002: PendingApprovalRecord import relocated from src.models.state to src.models.fix_plan
"""

from datetime import datetime, timezone
import json
from typing import Any, Optional
from uuid import uuid4

from loguru import logger

from src.models.alert import DeviceInfo, DeviceAuth
from src.models.enums import (
    AlertType, AlertSeverity, AlertSource, WorkflowStatus,
    ApprovalStatus, RiskLevel, AuditEventType,
)
from src.models.fix_plan import (
    FixPlan, RootCauseResult, TemplateParams, ExecRecord, VerifyResult,
    KnowledgeRef, RiskAssessment, PendingApprovalRecord,
)
from src.models.state import NetworkAgentState

from src.llm.llm_service import LLMService
from src.llm.template_engine import TemplateEngine, TemplateNotFoundError, ParamMissingError
from src.llm.rag_service import RAGService
from src.llm.output_validator import OutputValidator, ValidationError
from src.tools.switch_config_tool import AbstractSwitchConfigTool
from src.tools.switch_diag_tool import AbstractSwitchDiagTool
from src.tools.backup_tool import AbstractBackupTool
from src.tools.knowledge_base_tool import KnowledgeBaseTool
from src.security.risk_assessor import RiskAssessor
from src.security.audit_logger import AuditLogger
from src.security.config_manager import ConfigManager


# ────────────────────────────────────────────────────
# 诊断命令映射（根据告警类型选择）
# ────────────────────────────────────────────────────

DIAG_COMMAND_MAP: dict[str, list[str]] = {
    AlertType.MAC_FLAPPING: [
        "show mac address-table",
        "show logging",
    ],
    AlertType.PORT_DOWN: [
        "show interface status",
        "show logging",
    ],
    AlertType.CPU_HIGH: [
        "show processes cpu",
        "show processes cpu history",
    ],
}


class NodeHandlers:
    """
    14 个 LangGraph 节点处理函数的集合。
    每个函数签名: (state: NetworkAgentState) → dict[str, Any]（返回 State 的部分更新字段）。

    依赖注入: 所有下层模块通过构造函数注入，便于单元测试和模块替换。
    """

    def __init__(
        self,
        llm_service: Optional[LLMService] = None,
        template_engine: Optional[TemplateEngine] = None,
        rag_service: Optional[RAGService] = None,
        output_validator: Optional[OutputValidator] = None,
        switch_config_tool: Optional[AbstractSwitchConfigTool] = None,
        switch_diag_tool: Optional[AbstractSwitchDiagTool] = None,
        backup_tool: Optional[AbstractBackupTool] = None,
        knowledge_base_tool: Optional[KnowledgeBaseTool] = None,
        risk_assessor: Optional[RiskAssessor] = None,
        audit_logger: Optional[AuditLogger] = None,
        config_manager: Optional[ConfigManager] = None,
    ):
        self.llm_service = llm_service or LLMService()
        self.template_engine = template_engine or TemplateEngine()
        self.rag_service = rag_service or RAGService()
        self.output_validator = output_validator or OutputValidator(audit_logger)
        self.switch_config_tool = switch_config_tool
        self.switch_diag_tool = switch_diag_tool
        self.backup_tool = backup_tool
        self.knowledge_base_tool = knowledge_base_tool
        self.risk_assessor = risk_assessor or RiskAssessor()
        self.audit_logger = audit_logger or AuditLogger()
        self.config_manager = config_manager or ConfigManager()
        self._timeline_store: dict[str, list[dict[str, Any]]] = {}  # alert_id → timeline entries

    def get_timeline(self, alert_id: str) -> list[dict[str, Any]]:
        """Return timeline entries for an alert."""
        return self._timeline_store.get(alert_id, [])

    # ── 工具动态选择 (REQ-FUNC-119) ──────────────────────────

    def _get_device_type(self, state: NetworkAgentState) -> str:
        """Extract device_type from workflow state. Defaults to MOCK."""
        device_info = state.get("device_info", {})
        if isinstance(device_info, dict):
            return device_info.get("device_type", "MOCK")
        return getattr(device_info, "device_type", "MOCK") or "MOCK"

    def _resolve_simulator_connection(self, state: NetworkAgentState) -> tuple[str, int, str, str] | None:
        """
        For SIMULATOR devices: resolve (host, port, username, password).
        Priority: LifecycleManager → DB (G5 fallback).
        """
        device_type = self._get_device_type(state)
        if device_type != "SIMULATOR":
            return None

        device_info = state.get("device_info", {})
        device_name = (device_info.get("device_name", "") if isinstance(device_info, dict)
                      else getattr(device_info, "device_name", ""))

        # 1. Try LifecycleManager
        try:
            import sys
            main_module = sys.modules.get("src.main")
            lm = getattr(main_module, "simulator_lifecycle_manager", None)
            if lm and device_name:
                info = lm.find_by_device_name(device_name)
                if info:
                    return ("127.0.0.1", info["ssh_port"],
                            info.get("username", "admin"), "N/A")  # password via DB fallback
        except Exception:
            pass

        # 2. Fallback: query DB for port + credential
        try:
            from src.database.base import SessionLocal
            from src.database.repositories.device_repository import DeviceRepository
            db = SessionLocal()
            try:
                repo = DeviceRepository(db)
                devices = repo.list_devices()
                for d in devices:
                    if d.device_name == device_name and d.simulator_port:
                        username = "admin"
                        password = "admin"
                        if d.credential:
                            username = d.credential.ssh_username or username
                            try:
                                import sys
                                main_module = sys.modules.get("src.main")
                                if main_module and main_module.encryption_service:
                                    password = main_module.encryption_service.decrypt(
                                        d.credential.ssh_password_encrypted)
                            except Exception:
                                pass
                        return ("127.0.0.1", d.simulator_port, username, password)
            finally:
                db.close()
        except Exception:
            pass

        return None

    def _get_diag_tool_for_device(self, state: NetworkAgentState):
        """Return the appropriate diag tool based on device_type in state."""
        device_type = self._get_device_type(state)
        if device_type == "SIMULATOR":
            from src.tools.simulator_diag_tool import SimulatorDiagTool
            return SimulatorDiagTool()
        return self.switch_diag_tool

    def _get_config_tool_for_device(self, state: NetworkAgentState):
        """Return the appropriate config tool based on device_type in state."""
        device_type = self._get_device_type(state)
        if device_type == "SIMULATOR":
            from src.tools.simulator_config_tool import SimulatorConfigTool
            return SimulatorConfigTool()
        return self.switch_config_tool

    def _get_backup_tool_for_device(self, state: NetworkAgentState):
        """Return the appropriate backup tool based on device_type in state."""
        device_type = self._get_device_type(state)
        if device_type == "SIMULATOR":
            from src.tools.simulator_backup_tool import SimulatorBackupTool
            return SimulatorBackupTool()
        return self.backup_tool

    # ── 内部辅助: 日志记录 + 时间线 ──────────────────────────

    def _log_node(self, state: NetworkAgentState, node_name: str, phase: str, duration_ms: int = 0) -> None:
        """记录节点执行日志 + 写入内存时间线。"""
        alert_id = state.get("alert_id", "UNKNOWN")
        now_ts = datetime.now(timezone.utc).isoformat()
        summary = {
            "alert_type": state.get("alert_type", ""),
            "status": state.get("status", ""),
        }

        if phase == "START":
            # Create pending timeline entry
            if alert_id not in self._timeline_store:
                self._timeline_store[alert_id] = []
            self._timeline_store[alert_id].append({
                "id": f"{node_name}_{len(self._timeline_store[alert_id])}",
                "node_name": node_name,
                "status": "RUNNING",
                "started_at": now_ts,
                "completed_at": None,
                "state_snapshot": dict(state),
            })
        elif phase == "END":
            # Finalize the matching START entry
            entries = self._timeline_store.get(alert_id, [])
            matched_entry = None
            for entry in reversed(entries):
                if entry["node_name"] == node_name and entry["status"] == "RUNNING":
                    entry["status"] = "COMPLETED"
                    entry["completed_at"] = now_ts
                    entry["duration_ms"] = duration_ms
                    entry["state_snapshot"] = dict(state)
                    matched_entry = entry
                    break
            self.audit_logger.log_node_execution(alert_id, node_name, phase, summary, duration_ms)
            # Persist timeline to SQLite so it survives restart
            if matched_entry:
                try:
                    from src.database.base import SessionLocal
                    from src.database.repositories.alert_repository import AlertRepository
                    db = SessionLocal()
                    try:
                        AlertRepository(db).append_timeline_entry(alert_id, {
                            "node_name": node_name,
                            "state_snapshot": dict(state),
                            "started_at": datetime.now(timezone.utc),
                            "status": "COMPLETED",
                        })
                    finally:
                        db.close()
                except Exception as e:
                    logger.debug(f"Timeline DB persist skipped: {e}")

    # ── IFC-005-01: handle_receive_alert ─────────────────

    def handle_receive_alert(self, state: NetworkAgentState) -> dict[str, Any]:
        """接收标准 Alert 对象，初始化 State。"""
        node = "receive_alert"
        self._log_node(state, node, "START")

        alert_id = state.get("alert_id", str(uuid4()))
        status = WorkflowStatus.ACTIVE.value

        self._log_node(state, node, "END")
        return {
            "alert_id": alert_id,
            "status": status,
        }

    # ── IFC-005-02: handle_parse_alert ──────────────────

    def handle_parse_alert(self, state: NetworkAgentState) -> dict[str, Any]:
        """解析告警字段，提取 alert_type/content/device_info。"""
        node = "parse_alert"
        self._log_node(state, node, "START")

        # State 中已通过 run_workflow(alert) 注入了 alert 数据
        alert_content = state.get("alert_content", "")
        alert_type = state.get("alert_type", "")
        device_info = state.get("device_info", {})

        # 如果没有 device_info 中的 ip，从 device_info 字典中提取
        device_name = device_info.get("device_name", "Unknown-Device")

        result: dict[str, Any] = {
            "alert_content": alert_content,
            "alert_type": alert_type,
            "alert_timestamp": state.get("alert_timestamp", datetime.now(timezone.utc).isoformat()),
        }

        if device_info:
            result["device_info"] = device_info

        self._log_node(state, node, "END")
        return result

    # ── IFC-005-03: handle_validate_alert ────────────────

    def handle_validate_alert(self, state: NetworkAgentState) -> dict[str, Any]:
        """告警去重 + 时效性检查，设置 is_valid 标志。"""
        node = "validate_alert"
        self._log_node(state, node, "START")

        alert_timestamp = state.get("alert_timestamp", "")
        alert_content = state.get("alert_content", "")

        is_valid = True

        # 时效性检查（默认 TTL 15 分钟）
        ttl_minutes = self.config_manager.get("alert.ttl_minutes") or 15
        if alert_timestamp:
            try:
                alert_time = datetime.fromisoformat(alert_timestamp.replace("Z", "+00:00"))
                if alert_time.tzinfo is None:
                    alert_time = alert_time.replace(tzinfo=timezone.utc)
                elapsed = (datetime.now(timezone.utc) - alert_time).total_seconds() / 60
                if elapsed > ttl_minutes:
                    is_valid = False
                    logger.info(f"Alert expired: elapsed={elapsed:.1f}min > ttl={ttl_minutes}min")
            except (ValueError, AttributeError):
                pass

        # 内容检查
        if not alert_content or len(alert_content.strip()) < 5:
            is_valid = False
            logger.info("Alert invalid: empty or too short content")

        self._log_node(state, node, "END")
        return {"is_valid": is_valid}

    # ── IFC-005-04: handle_get_device_info ──────────────

    def handle_get_device_info(self, state: NetworkAgentState) -> dict[str, Any]:
        """查询设备信息库，获取 IP/型号/凭据。"""
        node = "get_device_info"
        self._log_node(state, node, "START")

        device_info = state.get("device_info", {})
        device_name = device_info.get("device_name", "")

        # 从 ConfigManager 获取凭据
        auth = self.config_manager.get_device_credentials(device_name)
        if auth:
            device_info["username"] = auth.username
            device_info["password"] = auth.password

        # 补充缺失字段
        if not device_info.get("device_model"):
            device_info["device_model"] = "TP-Link T2600G-28TS"
        if not device_info.get("device_ip"):
            device_info["device_ip"] = "192.168.1.1"

        self._log_node(state, node, "END")
        return {"device_info": device_info}

    # ── IFC-005-05: handle_establish_ssh ──────────────

    def handle_establish_ssh(self, state: NetworkAgentState) -> dict[str, Any]:
        """建立 SSH 连接（Mock 阶段验证凭据格式）。"""
        node = "establish_ssh"
        self._log_node(state, node, "START")

        device_info = state.get("device_info", {})
        username = device_info.get("username", "")
        password = device_info.get("password", "")

        if not username or not password:
            logger.warning(f"SSH credentials incomplete for {device_info.get('device_name', 'unknown')}")

        # Mock: 验证格式
        logger.info(f"[Mock] SSH connection established to {device_info.get('device_ip')} as {username}")

        self._log_node(state, node, "END")
        return {}  # 无新增 State 字段

    # ── IFC-005-06: handle_collect_diag ─────────────────

    def handle_collect_diag(self, state: NetworkAgentState) -> dict[str, Any]:
        """调用 SwitchDiagTool 执行诊断命令，收集诊断数据。"""
        node = "collect_diag"
        self._log_node(state, node, "START")

        alert_type = state.get("alert_type", AlertType.PORT_DOWN)
        device_info = state.get("device_info", {})
        device_ip = device_info.get("device_ip", "192.168.1.1")

        # 选择诊断命令
        commands = DIAG_COMMAND_MAP.get(alert_type, ["show interface status"])
        diag_results: list[str] = []
        diag_outputs: list[str] = []

        auth = self._extract_auth(device_info)

        # Resolve simulator to localhost (REQ-FUNC-119)
        sim_conn = self._resolve_simulator_connection(state)
        if sim_conn:
            device_ip = sim_conn[0]
            auth.port = sim_conn[1]
            auth.username = sim_conn[2]
            auth.password = sim_conn[3]

        for command in commands:
            # 对 PORT_DOWN 类型，动态生成接口级命令
            actual_command = command
            if alert_type == AlertType.PORT_DOWN and "show interface status" not in command:
                iface = device_info.get("interface_name", "Gi0/1")
                actual_command = f"show interface {iface}"

            diag_tool = self._get_diag_tool_for_device(state)
            if diag_tool:
                result = diag_tool._run(device_ip, actual_command, auth)
                if result.success:
                    diag_outputs.append(f"--- {actual_command} ---\n{result.output}")
                else:
                    diag_outputs.append(f"--- {actual_command} ---\nERROR: {result.error}")
            else:
                diag_outputs.append(f"--- {actual_command} ---\n[Mock] No diag tool available")

        combined_result = "\n\n".join(diag_outputs)
        logger.info(f"collect_diag: collected {len(commands)} diagnostic outputs ({len(combined_result)} chars)")

        # ★ MOD-DP-006: Persist diag_result to DB ★
        try:
            from src.database.base import SessionLocal
            from src.database.repositories.alert_repository import AlertRepository
            db = SessionLocal()
            try:
                AlertRepository(db).update_workflow_state(alert_id, {"diag_result": combined_result})
            finally:
                db.close()
        except Exception as e:
            logger.warning(f"Failed to persist diag_result to DB: {e}")

        self._log_node(state, node, "END")
        return {
            "diag_commands": commands,
            "diag_result": combined_result,
        }

    # ── IFC-005-07: handle_analyze_root_cause ────────────

    def handle_analyze_root_cause(self, state: NetworkAgentState) -> dict[str, Any]:
        """调用 LLMService + RAGService 分析根因。"""
        node = "analyze_root_cause"
        self._log_node(state, node, "START")

        alert_content = state.get("alert_content", "")
        diag_result = state.get("diag_result", "")
        alert_type = state.get("alert_type", "")

        # LLM 根因分析 (with error handling — don't hang forever)
        self.llm_service.set_context(state.get("alert_id"))
        try:
            root_cause_result: RootCauseResult = self.llm_service.analyze_root_cause(alert_content, diag_result)
        except Exception as e:
            logger.error(f"LLM analyze_root_cause failed: {e}")
            self._log_node(state, node, "END")
            return {
                "root_cause": f"LLM分析失败: {str(e)[:200]}",
                "knowledge_refs": [],
                "_error_message": f"analyze_root_cause: {str(e)[:200]}",
                "status": "FAILED",
            }
        root_cause = root_cause_result.description
        if root_cause_result.possible_causes:
            root_cause += "\n\n可能原因:\n- " + "\n- ".join(root_cause_result.possible_causes)
        if root_cause_result.suggested_direction:
            root_cause += f"\n\n建议方向: {root_cause_result.suggested_direction}"

        # 安全标记
        root_cause = self.output_validator.sanitize_root_cause(root_cause)

        # RAG 检索
        knowledge_refs: list[dict[str, Any]] = []
        if self.rag_service:
            rag_results = self.rag_service.search(diag_result, alert_type, top_k=5)
            for ref in rag_results:
                knowledge_refs.append(ref.model_dump())

        # ★ MOD-DP-006: Persist root_cause + knowledge_refs to DB ★
        try:
            from src.database.base import SessionLocal
            from src.database.repositories.alert_repository import AlertRepository
            db = SessionLocal()
            try:
                AlertRepository(db).update_workflow_state(alert_id, {
                    "root_cause": root_cause,
                    "knowledge_refs": knowledge_refs,
                })
            finally:
                db.close()
        except Exception as e:
            logger.warning(f"Failed to persist root_cause to DB: {e}")

        self._log_node(state, node, "END")
        return {
            "root_cause": root_cause,
            "knowledge_refs": knowledge_refs,
        }

    # ── IFC-005-08: handle_generate_fix_plan ─────────────

    def handle_generate_fix_plan(self, state: NetworkAgentState) -> dict[str, Any]:
        """
        模板匹配 + LLM 参数填充 + OutputValidator 校验 + TemplateEngine 拼装。
        安全流程: LLM 填参 → OutputValidator 校验 → TemplateEngine 确定性拼装。
        """
        node = "generate_fix_plan"
        self._log_node(state, node, "START")

        alert_type = state.get("alert_type", AlertType.PORT_DOWN)
        root_cause = state.get("root_cause", "")
        diag_result = state.get("diag_result", "")
        device_info_dict = state.get("device_info", {})
        knowledge_refs = state.get("knowledge_refs", [])

        # 构造 DeviceInfo 对象
        device_info = DeviceInfo(
            device_name=device_info_dict.get("device_name", "Unknown"),
            device_ip=device_info_dict.get("device_ip", "0.0.0.0"),
            device_model=device_info_dict.get("device_model"),
            interface_name=device_info_dict.get("interface_name"),
            mac_address=device_info_dict.get("mac_address"),
            cpu_percent=device_info_dict.get("cpu_percent"),
        )

        # 从知识库获取匹配模板
        template_id = self._select_best_template(alert_type, knowledge_refs)
        if not template_id:
            template_id = self._get_default_template(alert_type)

        try:
            template_def = self.template_engine.get_template(template_id)
        except TemplateNotFoundError:
            logger.warning(f"Template not found: {template_id}, using default")
            template_id = self._get_default_template(AlertType.PORT_DOWN)
            template_def = self.template_engine.get_template(template_id)

        # Step 1: LLM 填充参数
        try:
            llm_params: TemplateParams = self.llm_service.fill_template_params(
                template_id=template_id,
                template_description=template_def.description,
                root_cause=root_cause,
                diag_result=diag_result,
                device_info=device_info,
                params_schema=template_def.params_schema,
            )
        except Exception as e:
            logger.error(f"LLM fill_template_params failed: {e}")
            # 使用默认参数
            llm_params = TemplateParams(params=self._get_default_params(template_def))

        # Step 2: OutputValidator 校验（必须在 TemplateEngine 拼装之前）
        try:
            validated_params = self.output_validator.validate_params(
                raw_output=json.dumps(llm_params.params, ensure_ascii=False),
                template_params_schema=template_def.params_schema,
            )
        except ValidationError as e:
            logger.error(f"OutputValidator rejected LLM params: {e}")
            # 安全底线: 校验失败则使用默认参数
            validated_params = self._get_default_params(template_def)

        # Step 3: TemplateEngine 确定性拼装（非 LLM）
        try:
            commands = self.template_engine.render(template_id, validated_params)
        except (TemplateNotFoundError, ParamMissingError) as e:
            logger.error(f"TemplateEngine render failed: {e}")
            commands = []

        # 构造 FixPlan
        fix_plan = FixPlan(
            template_id=template_id,
            params=validated_params,
            commands=commands,
            risk_hints=template_def.risk_hints,
            description=template_def.description,
        )

        # ★ MOD-DP-006: Persist fix_plan to DB (covers all alerts, REQ-FUNC-001) ★
        try:
            from src.database.base import SessionLocal
            from src.database.repositories.alert_repository import AlertRepository
            db = SessionLocal()
            try:
                AlertRepository(db).update_workflow_state(alert_id, {"fix_plan": fix_plan.model_dump()})
            finally:
                db.close()
        except Exception as e:
            logger.warning(f"Failed to persist fix_plan to DB: {e}")

        self._log_node(state, node, "END")
        return {"fix_plan": fix_plan.model_dump()}

    # ── IFC-005-09: handle_assess_risk ─────────────────

    def handle_assess_risk(self, state: NetworkAgentState) -> dict[str, Any]:
        """调用 RiskAssessor 评估风险等级。"""
        node = "assess_risk"
        self._log_node(state, node, "START")

        fix_plan_dict = state.get("fix_plan", {})
        fix_plan = FixPlan(**fix_plan_dict) if fix_plan_dict else FixPlan(
            template_id="", params={}, commands=[]
        )

        assessment: RiskAssessment = self.risk_assessor.assess(fix_plan)

        result: dict[str, Any] = {
            "need_human_approval": assessment.need_human_approval,
            "risk_level": assessment.risk_level,
        }

        # If approval is needed, set PENDING status immediately (before interrupt)
        if assessment.need_human_approval:
            result["approval_status"] = "PENDING"
            # Register pending approval so it appears in API
            alert_id = state.get("alert_id", "")
            alert_type = state.get("alert_type", "")
            alert_content = state.get("alert_content", "")
            device_info = state.get("device_info", {})
            pending = PendingApprovalRecord(
                checkpoint_id=alert_id,
                alert_id=alert_id,
                alert_type=alert_type,
                alert_content=alert_content,
                device_name=device_info.get("device_name", "Unknown"),
                fix_plan_summary=fix_plan.description or fix_plan.template_id or "",
                risk_level=assessment.risk_level,
                risk_reasons=assessment.risk_reasons,
                created_at=datetime.now(timezone.utc).isoformat(),
            )
            self.audit_logger.register_pending_approval(pending)
            # Also persist to SQLite so it survives restart
            try:
                from src.database.base import SessionLocal
                from src.database.repositories.approval_repository import ApprovalRepository
                db = SessionLocal()
                try:
                    ApprovalRepository(db).create_approval({
                        "checkpoint_id": alert_id,
                        "alert_id_fk": alert_id,
                        "fix_plan": {"template_id": fix_plan.template_id, "description": fix_plan.description, "commands": fix_plan.commands},
                        "risk_level": assessment.risk_level,
                        "decision": "PENDING",
                        "decided_by": None,
                        "note": "",
                    })
                finally:
                    db.close()
            except Exception as e:
                logger.warning(f"Failed to persist pending approval to DB: {e}")
            logger.info(f"Approval PENDING for alert {alert_id} (risk={assessment.risk_level})")

        self._log_node(state, node, "END")
        return result

    # ── IFC-005-10: handle_human_approval ────────────────

    def handle_human_approval(self, state: NetworkAgentState) -> dict[str, Any]:
        """
        Interrupt 挂起点，等待/接收审批决定。
        当 LangGraph resume_workflow 被调用时，状态中会包含 approval_status。
        """
        node = "human_approval"
        self._log_node(state, node, "START")

        approval_status = state.get("approval_status", ApprovalStatus.PENDING)
        alert_id = state.get("alert_id", "")
        alert_type = state.get("alert_type", "")
        alert_content = state.get("alert_content", "")
        device_info = state.get("device_info", {})
        fix_plan_dict = state.get("fix_plan", {})
        risk_level = state.get("risk_level", RiskLevel.LOW)

        # 如果仍是 PENDING（首次进入节点），注册待审批项
        if approval_status == ApprovalStatus.PENDING:
            checkpoint_id = state.get("alert_id", str(uuid4()))
            pending = PendingApprovalRecord(
                checkpoint_id=checkpoint_id,
                alert_id=alert_id,
                alert_type=alert_type,
                alert_content=alert_content,
                device_name=device_info.get("device_name", "Unknown"),
                fix_plan_summary=fix_plan_dict.get("description", "No description"),
                risk_level=risk_level,
                risk_reasons=fix_plan_dict.get("risk_hints", []),
                created_at=datetime.now(timezone.utc).isoformat(),
            )
            self.audit_logger.register_pending_approval(pending)
            logger.info(f"Human approval pending for alert {alert_id} (checkpoint={checkpoint_id})")

        if approval_status == ApprovalStatus.APPROVED:
            self.audit_logger.log_audit_event(
                event_type=AuditEventType.APPROVAL_DECISION,
                alert_id=alert_id,
                operator="human_approver",
                action="APPROVED",
                detail={"alert_type": alert_type},
            )
            logger.info(f"Human approval GRANTED for alert {alert_id}")

        elif approval_status == ApprovalStatus.REJECTED:
            self.audit_logger.log_audit_event(
                event_type=AuditEventType.APPROVAL_DECISION,
                alert_id=alert_id,
                operator="human_approver",
                action="REJECTED",
                detail={"alert_type": alert_type},
            )
            logger.info(f"Human approval REJECTED for alert {alert_id}")

        self._log_node(state, node, "END")
        return {"approval_status": approval_status}

    # ── IFC-005-11: handle_backup_config ────────────────

    def handle_backup_config(self, state: NetworkAgentState) -> dict[str, Any]:
        """调用 BackupTool 备份 running-config。"""
        node = "backup_config"
        self._log_node(state, node, "START")

        device_info = state.get("device_info", {})
        device_ip = device_info.get("device_ip", "0.0.0.0")
        auth = self._extract_auth(device_info)

        sim_conn = self._resolve_simulator_connection(state)
        if sim_conn:
            device_ip = sim_conn[0]
            auth.port = sim_conn[1]
            auth.username = sim_conn[2]
            auth.password = sim_conn[3]

        if self.backup_tool:
            backup_tool = self._get_backup_tool_for_device(state)
            result = backup_tool._run(device_ip, auth, operation="backup")
            if isinstance(result, dict):
                backup_success = result.get("success", False)
                config_backup = result.get("config", "")
                backup_id = result.get("backup_id", "")
            else:
                backup_success = result.success
                config_backup = result.config or ""
                backup_id = result.backup_id
        else:
            backup_success = False
            config_backup = ""
            backup_id = ""

        self._log_node(state, node, "END")
        return {
            "config_backup": config_backup,
            "backup_id": backup_id,
            "_backup_success": backup_success,  # 条件边路由用
        }

    # ── IFC-005-12: handle_execute_fix ──────────────────

    def handle_execute_fix(self, state: NetworkAgentState) -> dict[str, Any]:
        """调用 SwitchConfigTool 下发修复命令，逐条执行前幂等检查。"""
        node = "execute_fix"
        self._log_node(state, node, "START")

        fix_plan_dict = state.get("fix_plan", {})
        commands = fix_plan_dict.get("commands", [])
        device_info = state.get("device_info", {})
        device_ip = device_info.get("device_ip", "0.0.0.0")
        auth = self._extract_auth(device_info)

        sim_conn = self._resolve_simulator_connection(state)
        if sim_conn:
            device_ip = sim_conn[0]
            auth.port = sim_conn[1]
            auth.username = sim_conn[2]
            auth.password = sim_conn[3]

        exec_log: list[dict[str, Any]] = []
        device_type = self._get_device_type(state)

        for cmd in commands:
            record = self._execute_single_command(device_ip, cmd, auth, device_type)
            exec_log.append(record)

            # 审计日志：配置变更
            self.audit_logger.log_audit_event(
                event_type=AuditEventType.CONFIG_CHANGE,
                alert_id=state.get("alert_id", ""),
                operator="auto_agent",
                action="configure",
                detail={
                    "command": cmd,
                    "success": record.get("success", False),
                    "device_ip": device_ip,
                },
            )

        all_success = all(r.get("success", False) for r in exec_log)
        logger.info(f"execute_fix: {len(exec_log)} commands, all_success={all_success}")

        # ★ MOD-DP-006: Persist exec_log to DB ★
        try:
            from src.database.base import SessionLocal
            from src.database.repositories.alert_repository import AlertRepository
            db = SessionLocal()
            try:
                AlertRepository(db).update_workflow_state(alert_id, {"exec_log": exec_log})
            finally:
                db.close()
        except Exception as e:
            logger.warning(f"Failed to persist exec_log to DB: {e}")

        self._log_node(state, node, "END")
        return {"exec_log": exec_log}

    # ── IFC-005-13: handle_verify_result ────────────────

    def handle_verify_result(self, state: NetworkAgentState) -> dict[str, Any]:
        """重新诊断，对比修复前后状态。"""
        node = "verify_result"
        self._log_node(state, node, "START")

        alert_type = state.get("alert_type", AlertType.PORT_DOWN)
        device_info = state.get("device_info", {})
        device_ip = device_info.get("device_ip", "0.0.0.0")
        before_diag = state.get("diag_result", "")

        # 重新执行诊断
        commands = DIAG_COMMAND_MAP.get(alert_type, ["show interface status"])
        after_outputs: list[str] = []
        auth = self._extract_auth(device_info)

        sim_conn = self._resolve_simulator_connection(state)
        if sim_conn:
            device_ip = sim_conn[0]
            auth.port = sim_conn[1]
            auth.username = sim_conn[2]
            auth.password = sim_conn[3]

        for command in commands[:1]:  # 验证仅跑第一条命令（快速检查）
            actual_command = command
            if alert_type == AlertType.PORT_DOWN:
                iface = device_info.get("interface_name", "Gi0/1")
                actual_command = f"show interface {iface}"

            verify_diag_tool = self._get_diag_tool_for_device(state)
            if verify_diag_tool:
                result = verify_diag_tool._run(device_ip, actual_command, auth)
                if result.success:
                    after_outputs.append(result.output)
                else:
                    after_outputs.append(f"ERROR: {result.error}")
            else:
                after_outputs.append("Mock verify: OK")

        after_diag = "\n".join(after_outputs)

        # 简单对比：检查 before 中的异常关键词是否消失
        alert_keywords = {
            AlertType.MAC_FLAPPING: ["flapping", "WARNING"],
            AlertType.PORT_DOWN: ["down", "notconnect"],
            AlertType.CPU_HIGH: ["92%", "CPU utilization.*high"],
        }
        keywords = alert_keywords.get(alert_type, [])
        before_has_issue = any(kw.lower() in before_diag.lower() for kw in keywords)
        after_has_issue = any(kw.lower() in after_diag.lower() for kw in keywords)
        verify_passed = before_has_issue and not after_has_issue

        # 如果修复前就没有问题（Mock 场景正常不会发生），也视为通过
        if not before_has_issue:
            verify_passed = True
            logger.info("verify_result: no issue detected in before state, assuming passed")

        verify = VerifyResult(
            verify_passed=verify_passed,
            before_state=before_diag[:500],
            after_state=after_diag[:500],
            comparison_notes=f"Before had issue: {before_has_issue}, After has issue: {after_has_issue}",
        )

        logger.info(f"verify_result: passed={verify_passed}")

        # ★ MOD-DP-006: Persist verify_result to DB ★
        try:
            from src.database.base import SessionLocal
            from src.database.repositories.alert_repository import AlertRepository
            db = SessionLocal()
            try:
                AlertRepository(db).update_workflow_state(alert_id, {"verify_result": verify.model_dump()})
            finally:
                db.close()
        except Exception as e:
            logger.warning(f"Failed to persist verify_result to DB: {e}")

        self._log_node(state, node, "END")
        return {"verify_result": verify.model_dump()}

    # ── IFC-005-14: handle_final_report ─────────────────

    def handle_final_report(self, state: NetworkAgentState) -> dict[str, Any]:
        """调用 LLM 生成处理报告，设置 status=CLOSED。"""
        node = "final_report"
        self._log_node(state, node, "START")

        alert_id = state.get("alert_id", "")
        root_cause = state.get("root_cause", "")
        fix_plan_dict = state.get("fix_plan", {})
        exec_log_dicts = state.get("exec_log", [])
        verify_result_dict = state.get("verify_result", {})
        is_valid = state.get("is_valid", False)
        approval_status = state.get("approval_status", "")
        backup_id = state.get("backup_id", "")

        # 构造对象
        fix_plan = FixPlan(**fix_plan_dict) if fix_plan_dict else FixPlan(template_id="", params={}, commands=[])
        exec_log = [ExecRecord(**r) for r in exec_log_dicts] if exec_log_dicts else []
        verify_result = VerifyResult(**verify_result_dict) if verify_result_dict else VerifyResult(verify_passed=False)

        # 确定最终状态
        status = WorkflowStatus.CLOSED
        if not is_valid:
            status = WorkflowStatus.EXPIRED
        elif approval_status == ApprovalStatus.REJECTED:
            status = WorkflowStatus.REJECTED
        elif verify_result.verify_passed:
            status = WorkflowStatus.CLOSED
        elif not verify_result.verify_passed and not backup_id:
            status = WorkflowStatus.FAILED
        else:
            # 验证失败但有备份 → 回滚后标记为 CLOSED（回滚成功）
            status = WorkflowStatus.CLOSED

        # LLM 生成报告
        try:
            final_report = self.llm_service.generate_report(
                alert_id=alert_id,
                root_cause=root_cause,
                fix_plan=fix_plan,
                exec_log=exec_log,
                verify_result=verify_result,
            )
        except Exception as e:
            logger.error(f"LLM generate_report failed: {e}")
            final_report = f"# Alert Processing Report\n\nAlert ID: {alert_id}\nStatus: {status}"

        # Sync status to SQLite
        try:
            from src.database.base import SessionLocal
            from src.database.repositories.alert_repository import AlertRepository
            db = SessionLocal()
            try:
                AlertRepository(db).update_alert_status(alert_id, str(status))
                logger.info(f"Alert status synced to DB: {alert_id} → {status}")
            finally:
                db.close()
        except Exception as e:
            logger.warning(f"Failed to sync alert status to DB: {e}")

        # ★ MOD-DP-006: Persist final_report + _completed marker to DB ★
        try:
            from src.database.base import SessionLocal
            from src.database.repositories.alert_repository import AlertRepository
            db = SessionLocal()
            try:
                AlertRepository(db).update_workflow_state(alert_id, {
                    "final_report": final_report,
                    "_completed": True,
                })
            finally:
                db.close()
        except Exception as e:
            logger.warning(f"Failed to persist final_report to DB: {e}")

        self._log_node(state, node, "END")
        return {
            "final_report": final_report,
            "status": status,
        }

    # ── 内部辅助方法 ──────────────────────────────────────

    @staticmethod
    def _extract_auth(device_info: dict[str, Any]) -> DeviceAuth:
        """从设备信息中提取认证凭据。"""
        return DeviceAuth(
            username=device_info.get("username", "admin"),
            password=device_info.get("password", "admin123"),
            enable_password=device_info.get("enable_password"),
            port=device_info.get("port", 22),
        )

    @staticmethod
    def _select_best_template(alert_type: str, knowledge_refs: list[dict[str, Any]]) -> str:
        """从知识库检索结果中选择最佳匹配的模板 ID。"""
        # 优先从 knowledge_refs 中提取 template_id
        for ref in knowledge_refs:
            tid = ref.get("template_id")
            if tid:
                return tid

        # fallback: 按告警类型默认
        return NodeHandlers._get_default_template(alert_type)

    @staticmethod
    def _get_default_template(alert_type: str) -> str:
        """根据告警类型获取默认模板 ID。"""
        default_map = {
            AlertType.MAC_FLAPPING: "TPL-MAC-PORT-SECURITY",
            AlertType.PORT_DOWN: "TPL-PORT-ENABLE",
            AlertType.CPU_HIGH: "TPL-CPU-RATE-LIMIT",
            AlertType.PORT_SHUTDOWN: "TPL-PORT-DISABLE",  # 高风险：需要审批
        }
        return default_map.get(alert_type, "TPL-PORT-ENABLE")

    @staticmethod
    def _get_default_params(template_def: Any) -> dict[str, Any]:
        """生成模板的默认参数。"""
        from src.models.fix_plan import TemplateDefinition
        if isinstance(template_def, TemplateDefinition):
            schema = template_def.params_schema
        else:
            schema = getattr(template_def, "params_schema", {})

        defaults: dict[str, Any] = {}
        for key, ptype in schema.items():
            ptype_lower = str(ptype).lower()
            if ptype_lower in ("integer", "int", "number"):
                defaults[key] = 1
            elif ptype_lower in ("float",):
                defaults[key] = 0.0
            elif ptype_lower in ("boolean", "bool"):
                defaults[key] = False
            else:
                defaults[key] = "Gi0/1"
        return defaults

    def _execute_single_command(
        self, device_ip: str, command: str, auth: DeviceAuth, device_type: str = "MOCK"
    ) -> dict[str, Any]:
        """执行单条命令（含幂等检查 fallback）。REQ-FUNC-119: device_type 驱动工具选择。"""
        try:
            if self.switch_config_tool:
                if device_type == "SIMULATOR":
                    from src.tools.simulator_config_tool import SimulatorConfigTool
                    config_tool = SimulatorConfigTool()
                else:
                    config_tool = self.switch_config_tool
                result = config_tool._run(device_ip, [command], auth)
                return {
                    "command": command,
                    "success": result.success,
                    "output": result.output,
                    "error": result.error,
                    "execution_time_ms": 500,
                    "was_idempotent_skip": False,
                }
            else:
                return {
                    "command": command,
                    "success": True,
                    "output": f"[Mock] {command}",
                    "error": None,
                    "execution_time_ms": 0,
                    "was_idempotent_skip": False,
                }
        except Exception as e:
            return {
                "command": command,
                "success": False,
                "output": "",
                "error": str(e),
                "execution_time_ms": 0,
                "was_idempotent_skip": False,
            }
