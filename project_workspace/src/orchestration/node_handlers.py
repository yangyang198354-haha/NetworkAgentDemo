"""
MOD-005: NodeHandlers — LangGraph node handler functions (14 nodes).
MOD-TL-002: _log_node enhanced with sequence_number, duration_ms, status parameter,
           START INSERT + END UPDATE dual-phase DB persistence.
@author sub_agent_software_developer
@module MOD-005, MOD-TL-002
@implements IFC-005-01 ~ IFC-005-14, IFC-TL-002-01, IFC-TL-002-02, IFC-TL-002-03
@depends MOD-006, MOD-007, MOD-008, MOD-009, MOD-010, MOD-011, MOD-012, MOD-013, MOD-014, MOD-015, MOD-TL-003
@covers REQ-FUNC-005 ~ REQ-FUNC-016, REQ-FUNC-023 ~ REQ-FUNC-025, REQ-FUNC-001 ~ REQ-FUNC-006
@fixes D-002: PendingApprovalRecord import relocated from src.models.state to src.models.fix_plan
"""

from datetime import datetime, timezone
from dataclasses import dataclass
from enum import Enum
import json
import os
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
    KnowledgeRef, RiskAssessment, PendingApprovalRecord, BackupResult,
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


# ────────────────────────────────────────────────────
# REAL 端到端工作流：接入上下文 / 命令映射 / 能力裁决 / 结构化验证
# (MOD-RE-001 ~ MOD-RE-006, IFC-RE-001-01 ~ IFC-RE-005-01)
# ────────────────────────────────────────────────────

class FixCapability(str, Enum):
    """REAL 修复能力裁决：可修复 / 降级（真实诊断 + 告警闭环）。"""
    FIXABLE = "FIXABLE"
    DEGRADED = "DEGRADED"


@dataclass
class RealAccessContext:
    """IFC-RE-001-01 出参：REAL 设备接入上下文（经 _resolve_access 解析）。"""
    host: str
    port: int
    protocol: str
    device_model: str = "TL-SG5428"
    frp_proxy_host: str | None = None
    frp_proxy_port: int | None = None


# ADR-RE-003: REAL 用已校准 TL-SG5428 命令集（空格版 show mac address-table）
REAL_DIAG_COMMAND_MAP: dict[str, list[str]] = {
    AlertType.PORT_DOWN: ["show interface status"],
    AlertType.PORT_SHUTDOWN: ["show interface status"],
    AlertType.CPU_HIGH: ["show cpu-utilization", "show memory-utilization"],
    AlertType.MAC_FLAPPING: ["show interface status", "show mac address-table"],
}

# ADR-RE-004: CPU_HIGH/MAC_FLAPPING 在 TL-SG5428 无已核实等价修复命令 → DEGRADED
REAL_FIX_CAPABILITY: dict[str, FixCapability] = {
    AlertType.PORT_DOWN: FixCapability.FIXABLE,
    AlertType.PORT_SHUTDOWN: FixCapability.FIXABLE,
    AlertType.CPU_HIGH: FixCapability.DEGRADED,
    AlertType.MAC_FLAPPING: FixCapability.DEGRADED,
}

REAL_FIX_TEMPLATE_MAP: dict[str, str] = {
    AlertType.PORT_DOWN: "TPL-PORT-ENABLE",
    AlertType.PORT_SHUTDOWN: "TPL-PORT-DISABLE",
}

# ADR-RE-006: REAL 写操作仅限授权测试端口（shutdown 需更高授权）
REAL_WRITE_PORT_WHITELIST: frozenset[str] = frozenset({"Gi1/0/2"})

REAL_CREDENTIAL_MISSING_MSG = (
    "REAL 凭据未配置：仅接受 DEVICE_<NAME>_PASSWORD 环境变量或 DB Fernet 解密，"
    "禁止使用 admin123 兜底"
)

DEGRADED_FIX_DESCRIPTION = "修复降级：该告警类型在 TL-SG5428 无已核实 CLI 修复能力"


def resolve_real_access(device_name: str) -> RealAccessContext | None:
    """IFC-RE-001-01: device_name → DB Device → _resolve_access → RealAccessContext。"""
    try:
        from src.database.base import SessionLocal
        from src.database.repositories.device_repository import DeviceRepository
        from src.tools.real_device_client import _resolve_access
    except Exception:
        return None

    try:
        db = SessionLocal()
    except Exception:
        return None
    try:
        repo = DeviceRepository(db)
        for device in repo.list_devices():
            if device.device_name == device_name:
                host, port, protocol = _resolve_access(device)
                return RealAccessContext(
                    host=host,
                    port=int(port),
                    protocol=protocol or "SSH",
                    device_model=device.device_model or "TL-SG5428",
                    frp_proxy_host=device.frp_proxy_host,
                    frp_proxy_port=device.frp_proxy_port,
                )
    except Exception as e:
        logger.warning(f"resolve_real_access failed for {device_name}: {e}")
    finally:
        db.close()
    return None


def enrich_device_info(device_info: dict, access: RealAccessContext) -> dict:
    """IFC-RE-001-02: 回填 FRP/协议/型号到 device_info dict（不改 pydantic 模型）。"""
    device_info["device_ip"] = access.host
    device_info["port"] = access.port
    device_info["protocol"] = access.protocol
    device_info["device_model"] = access.device_model
    device_info["frp_proxy_host"] = access.frp_proxy_host
    device_info["frp_proxy_port"] = access.frp_proxy_port
    return device_info


def _decrypt_fernet(token: str) -> str:
    """复用 main_module.encryption_service.decrypt（与 _resolve_simulator_connection 一致）。"""
    if not token:
        return ""
    try:
        import sys
        main_module = sys.modules.get("src.main")
        if main_module is not None and getattr(main_module, "encryption_service", None) is not None:
            return main_module.encryption_service.decrypt(token)
        from src.services.encryption_service import EncryptionService
        svc = EncryptionService()
        if getattr(svc, "_fernet", None) is None:
            svc.initialize()
        return svc.decrypt(token)
    except Exception as e:
        logger.warning(f"Fernet decrypt failed: {e}")
        return ""


def _resolve_real_credentials(device_name: str) -> tuple[str, str] | None:
    """ADR-RE-006: REAL 凭据仅来自 env 或 DB Fernet，缺失返回 None（禁用 admin123 兜底）。"""
    username = "admin"
    encrypted_password: str | None = None
    try:
        from src.database.base import SessionLocal
        from src.database.device_models import Device as DbDevice
        from sqlalchemy import select
        from sqlalchemy.orm import joinedload
        db = SessionLocal()
        try:
            row = db.execute(
                select(DbDevice).where(DbDevice.device_name == device_name)
                .options(joinedload(DbDevice.credential))
            ).scalar_one_or_none()
            if row is not None and row.credential is not None:
                username = row.credential.ssh_username or "admin"
                encrypted_password = row.credential.ssh_password_encrypted or None
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"_resolve_real_credentials DB query failed for {device_name}: {e}")

    env_pwd = os.environ.get(f"DEVICE_{device_name.upper()}_PASSWORD", "").strip()
    if env_pwd:
        return username, env_pwd

    if encrypted_password:
        pwd = _decrypt_fernet(encrypted_password)
        if pwd:
            return username, pwd

    return None


def establish_real_reachability(access: RealAccessContext, username: str, password: str) -> bool:
    """IFC-RE-002-03: TCP + 协议握手可达性校验（复用 _open_*_session 会话链）。"""
    from src.tools.real_device_client import _tcp_check, _open_ssh_session, _open_telnet_session
    from src.tools.real_session_gate import session_guard_by_access

    ok, _ms = _tcp_check(access.host, access.port, timeout=3.0)
    if not ok:
        logger.warning(f"establish_real_reachability: TCP {access.host}:{access.port} unreachable")
        return False

    protocol = (access.protocol or "SSH").upper()
    if protocol not in ("SSH", "TELNET"):
        return False

    try:
        with session_guard_by_access(access.host, access.port, protocol):
            if protocol == "SSH":
                sess = _open_ssh_session(access.host, access.port, username, password)
            else:
                sess = _open_telnet_session(access.host, access.port, username, password)
            try:
                sess.show("show system-info")
            finally:
                try:
                    sess.close()
                except Exception:
                    pass
        return True
    except Exception as e:
        logger.warning(f"establish_real_reachability: protocol handshake failed: {e}")
        return False


def get_diag_commands(alert_type: str, device_type: str) -> list[str]:
    """IFC-RE-003-01: device_type 感知诊断命令映射。"""
    dt = (device_type or "").upper()
    if dt == "REAL":
        return REAL_DIAG_COMMAND_MAP.get(alert_type, ["show interface status"])
    return DIAG_COMMAND_MAP.get(alert_type, ["show interface status"])


def parse_diag_output(alert_type: str, device_type: str, text: str) -> dict:
    """IFC-RE-003-02: REAL 结构化解析；非 REAL 返回原文；解析失败返回明确错误。"""
    dt = (device_type or "").upper()
    if dt != "REAL":
        return {"raw": text or ""}
    try:
        from src.tools.real_panel_parsers import (
            parse_interface_status, parse_cpu_utilization,
        )
        if alert_type in (AlertType.PORT_DOWN, AlertType.PORT_SHUTDOWN, AlertType.MAC_FLAPPING):
            ports = parse_interface_status(text)
            return {"ports": [p.__dict__ for p in ports]}
        if alert_type == AlertType.CPU_HIGH:
            cpu = parse_cpu_utilization(text)
            return {"cpu": cpu.__dict__}
    except Exception as e:
        return {"error": f"REAL 诊断解析失败: {e.__class__.__name__}: {e}"}
    return {"raw": text or ""}


def resolve_fix_capability(alert_type: str, device_type: str) -> FixCapability:
    """IFC-RE-004-01: REAL 修复能力裁决。"""
    dt = (device_type or "").upper()
    if dt != "REAL":
        return FixCapability.FIXABLE
    return REAL_FIX_CAPABILITY.get(alert_type, FixCapability.FIXABLE)


def get_fix_template(alert_type: str, device_type: str) -> str | None:
    """IFC-RE-004-02: FIXABLE 返回模板 ID，DEGRADED 返回 None。"""
    if resolve_fix_capability(alert_type, device_type) != FixCapability.FIXABLE:
        return None
    return REAL_FIX_TEMPLATE_MAP.get(alert_type)


def build_degraded_fix_plan(alert_type: str) -> FixPlan:
    """IFC-RE-004-03: 降级 FixPlan（空命令，不下发任何写操作）。"""
    return FixPlan(
        template_id="",
        params={},
        commands=[],
        risk_hints=["修复降级：仅执行真实诊断与告警闭环，不下发任何写命令"],
        description=DEGRADED_FIX_DESCRIPTION,
    )


def verify_real_fix(
    alert_type: str,
    before_text: str,
    after_text: str,
    target_port: str,
) -> VerifyResult:
    """IFC-RE-005-01: REAL 结构化验证（parse_interface_status Status 列）。"""
    if alert_type in (AlertType.CPU_HIGH, AlertType.MAC_FLAPPING):
        return VerifyResult(
            verify_passed=False,
            before_state=(before_text or "")[:500],
            after_state=(after_text or "")[:500],
            comparison_notes="修复降级/不可修复：该告警类型在 TL-SG5428 无已核实 CLI 修复能力",
        )

    try:
        from src.tools.real_panel_parsers import parse_interface_status
        before_ports = parse_interface_status(before_text)
        after_ports = parse_interface_status(after_text)
    except Exception as e:
        return VerifyResult(
            verify_passed=False,
            before_state=(before_text or "")[:500],
            after_state=(after_text or "")[:500],
            comparison_notes=f"REAL 验证解析失败: {e.__class__.__name__}: {e}",
        )

    def _find(ports, name: str) -> str | None:
        for p in ports:
            if p.name == name:
                return p.status
        return None

    before_status = _find(before_ports, target_port)
    after_status = _find(after_ports, target_port)

    if alert_type == AlertType.PORT_DOWN:
        passed = before_status in ("down", "notconnect") and after_status == "up"
        note = f"PORT_DOWN: {target_port} before={before_status} after={after_status}"
    elif alert_type == AlertType.PORT_SHUTDOWN:
        passed = before_status == "up" and after_status == "down"
        note = f"PORT_SHUTDOWN: {target_port} before={before_status} after={after_status}"
    else:
        passed = False
        note = f"未支持的 REAL 验证告警类型: {alert_type}"

    if before_status is None or after_status is None:
        passed = False
        note += f"（未定位到目标端口 {target_port}）"

    return VerifyResult(
        verify_passed=passed,
        before_state=(before_text or "")[:500],
        after_state=(after_text or "")[:500],
        comparison_notes=note,
    )


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
        self.__seq_counters: dict[str, int] = {}  # IFC-TL-002-02: per-alert sequence_number counter

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
        if device_type == "REAL":
            from src.tools.switch_diag_tool import create_switch_diag_tool
            return create_switch_diag_tool(device_type="REAL")
        return self.switch_diag_tool

    def _get_config_tool_for_device(self, state: NetworkAgentState):
        """Return the appropriate config tool based on device_type in state."""
        device_type = self._get_device_type(state)
        if device_type == "SIMULATOR":
            from src.tools.simulator_config_tool import SimulatorConfigTool
            return SimulatorConfigTool()
        if device_type == "REAL":
            from src.tools.switch_config_tool import create_switch_config_tool
            return create_switch_config_tool(device_type="REAL")
        return self.switch_config_tool

    def _get_backup_tool_for_device(self, state: NetworkAgentState):
        """Return the appropriate backup tool based on device_type in state."""
        device_type = self._get_device_type(state)
        if device_type == "SIMULATOR":
            from src.tools.simulator_backup_tool import SimulatorBackupTool
            return SimulatorBackupTool()
        return self.backup_tool

    @staticmethod
    def _sanitize_state_snapshot(state: NetworkAgentState) -> dict[str, Any]:
        """ADR-RE-006: 时间线 state_snapshot 脱敏，不含明文凭据。

        仅用于 alert_timeline 的可观测性快照（不影响 LangGraph MemorySaver 的
        工作流恢复状态），移除 device_info 中的 password / enable_password。
        """
        snapshot = dict(state)
        di = snapshot.get("device_info")
        if isinstance(di, dict):
            cleaned = dict(di)
            cleaned.pop("password", None)
            cleaned.pop("enable_password", None)
            snapshot["device_info"] = cleaned
        return snapshot

    # ── 内部辅助: 日志记录 + 时间线 ──────────────────────────

    def _log_node(self, state: NetworkAgentState, node_name: str, phase: str,
                  duration_ms: int = 0, status: str = "COMPLETED") -> None:
        """
        记录节点执行日志 + 写入内存时间线 + 双步 DB 持久化。

        IFC-TL-002-01: START phase — allocate sequence_number, INSERT into DB (status=RUNNING),
                        store returned DB id in _timeline_store.
        IFC-TL-002-01: END phase — find matching RUNNING entry, compute duration_ms,
                        UPDATE DB (completed_at, duration_ms, status, state_snapshot).

        Args:
            state: Current NetworkAgentState dict.
            node_name: Name of the executing LangGraph node.
            phase: "START" or "END".
            duration_ms: Pre-computed duration (legacy, kept for compatibility; END phase
                         recomputes from started_at timestamp).
            status: Node result status. Default "COMPLETED". Set to "FAILED" for error paths.
        """
        alert_id = state.get("alert_id", "UNKNOWN")
        now_dt = datetime.now(timezone.utc)
        now_ts = now_dt.isoformat()
        summary = {
            "alert_type": state.get("alert_type", ""),
            "status": state.get("status", ""),
        }

        if phase == "START":
            # ── 1. Allocate sequence_number (IFC-TL-002-02) ──
            if alert_id not in self.__seq_counters:
                # Lazy-init: query DB for current MAX(sequence_number) for this alert
                max_seq = 0
                try:
                    from src.database.base import SessionLocal
                    from sqlalchemy import text as sa_text
                    db = SessionLocal()
                    try:
                        result = db.execute(
                            sa_text(
                                "SELECT COALESCE(MAX(sequence_number), 0) "
                                "FROM alert_timeline WHERE alert_id_fk = :aid"
                            ),
                            {"aid": alert_id},
                        )
                        max_seq = result.scalar() or 0
                    finally:
                        db.close()
                except Exception as e:
                    logger.debug(f"Failed to query MAX(sequence_number) for {alert_id}: {e}")
                self.__seq_counters[alert_id] = max_seq

            self.__seq_counters[alert_id] += 1
            seq_num = self.__seq_counters[alert_id]

            # ── 2. Create in-memory timeline entry ──
            if alert_id not in self._timeline_store:
                self._timeline_store[alert_id] = []
            mem_entry = {
                "id": f"{node_name}_{len(self._timeline_store[alert_id])}",
                "node_name": node_name,
                "status": "RUNNING",
                "started_at": now_ts,
                "started_at_dt": now_dt,  # keep datetime for duration calc
                "completed_at": None,
                "state_snapshot": self._sanitize_state_snapshot(state),
                "sequence_number": seq_num,
                "_db_id": None,  # will be filled by DB INSERT return
            }
            self._timeline_store[alert_id].append(mem_entry)

            # ── 3. DB INSERT (IFC-TL-003-02 / ADR-TL-004 Option B) ──
            try:
                from src.database.base import SessionLocal
                from src.database.repositories.alert_repository import AlertRepository
                db = SessionLocal()
                try:
                    db_entry = AlertRepository(db).append_timeline_entry(alert_id, {
                        "node_name": node_name,
                        "state_snapshot": self._sanitize_state_snapshot(state),
                        "started_at": now_dt,
                        "status": "RUNNING",
                        "sequence_number": seq_num,
                    })
                    mem_entry["_db_id"] = db_entry.id
                finally:
                    db.close()
            except Exception as e:
                logger.debug(f"Timeline START DB persist skipped: {e}")

        elif phase == "END":
            # ── 1. Find matching RUNNING entry (search reversed for latest) ──
            entries = self._timeline_store.get(alert_id, [])
            matched_entry = None
            for entry in reversed(entries):
                if entry["node_name"] == node_name and entry["status"] == "RUNNING":
                    matched_entry = entry
                    break

            # ── 2. Compute duration_ms ──
            if matched_entry and matched_entry.get("started_at_dt"):
                computed_duration = int(
                    (now_dt - matched_entry["started_at_dt"]).total_seconds() * 1000
                )
            else:
                computed_duration = duration_ms or 0

            # ── 3. Update in-memory entry ──
            if matched_entry:
                matched_entry["status"] = status
                matched_entry["completed_at"] = now_ts
                matched_entry["duration_ms"] = computed_duration
                matched_entry["state_snapshot"] = self._sanitize_state_snapshot(state)

            # ── 4. Audit log ──
            self.audit_logger.log_node_execution(alert_id, node_name, phase, summary, computed_duration)

            # ── 5. DB UPDATE (IFC-TL-003-01 / ADR-TL-004 Option B) ──
            if matched_entry and matched_entry.get("_db_id"):
                try:
                    from src.database.base import SessionLocal
                    from src.database.repositories.alert_repository import AlertRepository
                    db = SessionLocal()
                    try:
                        AlertRepository(db).update_timeline_entry(
                            matched_entry["_db_id"],
                            {
                                "completed_at": now_dt,
                                "duration_ms": computed_duration,
                                "status": status,
                                "state_snapshot": self._sanitize_state_snapshot(state),
                            },
                        )
                    finally:
                        db.close()
                except Exception as e:
                    logger.debug(f"Timeline END DB update skipped: {e}")
            elif matched_entry:
                # Fallback: no _db_id (START DB INSERT failed), do a fresh INSERT
                try:
                    from src.database.base import SessionLocal
                    from src.database.repositories.alert_repository import AlertRepository
                    db = SessionLocal()
                    try:
                        AlertRepository(db).append_timeline_entry(alert_id, {
                            "node_name": node_name,
                            "state_snapshot": self._sanitize_state_snapshot(state),
                            "started_at": now_dt,
                            "completed_at": now_dt,
                            "status": status,
                            "duration_ms": computed_duration,
                            "sequence_number": matched_entry.get("sequence_number"),
                        })
                    finally:
                        db.close()
                except Exception as e:
                    logger.debug(f"Timeline END fallback DB persist skipped: {e}")

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
        device_type = self._get_device_type(state)

        # ADR-RE-001: REAL 走 FRP 解析 + 凭据安全校验（禁用 admin123 兜底）
        if device_type == "REAL":
            access = resolve_real_access(device_name)
            if access is None:
                logger.error(f"REAL device not registered in DB: {device_name}")
                self._log_node(state, node, "END", status="FAILED")
                return {
                    "device_info": device_info,
                    "status": "FAILED",
                    "_error_message": f"REAL 设备未在 devices 表中注册: {device_name}",
                }
            enrich_device_info(device_info, access)
            creds = _resolve_real_credentials(device_name)
            if creds is None:
                logger.error(f"REAL credentials missing for {device_name}")
                self._log_node(state, node, "END", status="FAILED")
                return {
                    "device_info": device_info,
                    "status": "FAILED",
                    "_error_message": REAL_CREDENTIAL_MISSING_MSG,
                }
            device_info["username"] = creds[0]
            device_info["password"] = creds[1]
            self._log_node(state, node, "END")
            return {"device_info": device_info}

        # MOCK / SIMULATOR 原路径逐字不变
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
        """建立 SSH 连接（Mock 阶段验证凭据格式；REAL 做真实可达性校验）。"""
        node = "establish_ssh"
        self._log_node(state, node, "START")

        # 上游（get_device_info）已标记失败 → 短路，避免用缺失凭据继续开会话
        if state.get("status") == "FAILED":
            self._log_node(state, node, "END", status="FAILED")
            return {"status": "FAILED"}

        device_info = state.get("device_info", {})
        device_type = self._get_device_type(state)

        # ADR-RE-002: REAL 走解析后接入上下文的可达性校验（TCP + 协议握手）
        if device_type == "REAL":
            access = RealAccessContext(
                host=device_info.get("device_ip", ""),
                port=int(device_info.get("port", 22)),
                protocol=device_info.get("protocol", "SSH"),
                device_model=device_info.get("device_model", "TL-SG5428"),
                frp_proxy_host=device_info.get("frp_proxy_host"),
                frp_proxy_port=device_info.get("frp_proxy_port"),
            )
            username = device_info.get("username", "")
            password = device_info.get("password", "")
            if not username or not password:
                self._log_node(state, node, "END", status="FAILED")
                return {"status": "FAILED", "_error_message": REAL_CREDENTIAL_MISSING_MSG}
            if not establish_real_reachability(access, username, password):
                self._log_node(state, node, "END", status="FAILED")
                return {
                    "status": "FAILED",
                    "device_info": device_info,
                    "_error_message": f"REAL 设备不可达: {access.host}:{access.port} ({access.protocol})",
                }
            logger.info(f"[REAL] 可达性确认: {access.host}:{access.port} ({access.protocol})")
            self._log_node(state, node, "END")
            return {"device_info": device_info}

        # MOCK / SIMULATOR 原路径逐字不变
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
        alert_id = state.get("alert_id", "")

        # 上游（get_device_info/establish_ssh）已标记失败 → 短路
        if state.get("status") == "FAILED":
            self._log_node(state, node, "END", status="FAILED")
            return {"status": "FAILED", "diag_result": "", "diag_commands": []}

        alert_type = state.get("alert_type", AlertType.PORT_DOWN)
        device_info = state.get("device_info", {})
        device_type = self._get_device_type(state)
        device_ip = device_info.get("device_ip", "192.168.1.1")

        # 选择诊断命令（ADR-RE-003: device_type 感知）
        commands = get_diag_commands(alert_type, device_type)
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

        strip_real = None
        if device_type == "REAL":
            from src.tools.real_device_client import _strip_echo_and_prompts
            strip_real = _strip_echo_and_prompts

        for idx, command in enumerate(commands):
            # 对 PORT_DOWN 类型，动态生成接口级命令（仅 MOCK/SIMULATOR）
            actual_command = command
            if device_type != "REAL" and alert_type == AlertType.PORT_DOWN and "show interface status" not in command:
                iface = device_info.get("interface_name", "Gi0/1")
                actual_command = f"show interface {iface}"

            diag_tool = self._get_diag_tool_for_device(state)
            if diag_tool:
                result = diag_tool._run(device_ip, actual_command, auth)
                if result.success:
                    output = result.output or ""
                    if device_type == "REAL":
                        output = strip_real(output, actual_command)
                        # 主命令结构化解析校验（AC-RE-002-02）
                        if idx == 0:
                            parsed = parse_diag_output(alert_type, device_type, output)
                            if parsed.get("error"):
                                diag_outputs.append(f"--- {actual_command} ---\nERROR: {parsed['error']}")
                                continue
                    diag_outputs.append(f"--- {actual_command} ---\n{output}")
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
        alert_id = state.get("alert_id", "")

        # 上游已标记失败 → 跳过 LLM，直接短路到 finish_report
        if state.get("status") == "FAILED":
            self._log_node(state, node, "END", status="FAILED")
            return {
                "status": "FAILED",
                "root_cause": state.get("_error_message", "工作流提前失败"),
                "knowledge_refs": [],
            }

        alert_content = state.get("alert_content", "")
        diag_result = state.get("diag_result", "")
        alert_type = state.get("alert_type", "")

        # LLM 根因分析 (with error handling — don't hang forever)
        try:
            root_cause_result: RootCauseResult = self.llm_service.analyze_root_cause(
                alert_content, diag_result, alert_id=alert_id)
        except Exception as e:
            logger.error(f"LLM analyze_root_cause failed: {e}")
            self._log_node(state, node, "END", status="FAILED")
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
        alert_id = state.get("alert_id", "")

        alert_type = state.get("alert_type", AlertType.PORT_DOWN)
        root_cause = state.get("root_cause", "")
        diag_result = state.get("diag_result", "")
        device_info_dict = state.get("device_info", {})
        knowledge_refs = state.get("knowledge_refs", [])
        device_type = self._get_device_type(state)

        # 构造 DeviceInfo 对象
        device_info = DeviceInfo(
            device_name=device_info_dict.get("device_name", "Unknown"),
            device_ip=device_info_dict.get("device_ip", "0.0.0.0"),
            device_model=device_info_dict.get("device_model"),
            interface_name=device_info_dict.get("interface_name"),
            mac_address=device_info_dict.get("mac_address"),
            cpu_percent=device_info_dict.get("cpu_percent"),
        )

        # ADR-RE-004: REAL 走能力裁决（FIXABLE/DEGRADED），不落 Cisco 模板
        if device_type == "REAL":
            template_id = get_fix_template(alert_type, device_type)
            if template_id is None:
                fix_plan = build_degraded_fix_plan(alert_type)
                self._persist_fix_plan(alert_id, fix_plan)
                self._log_node(state, node, "END")
                return {"fix_plan": fix_plan.model_dump()}
            try:
                template_def = self.template_engine.get_template(template_id)
            except TemplateNotFoundError:
                logger.warning(f"REAL PORT template not found: {template_id}, degraded")
                fix_plan = build_degraded_fix_plan(alert_type)
                self._persist_fix_plan(alert_id, fix_plan)
                self._log_node(state, node, "END")
                return {"fix_plan": fix_plan.model_dump()}
        else:
            # MOCK / SIMULATOR 原路径逐字不变
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
                alert_id=alert_id,
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

        # ADR-RE-006: REAL 端口写操作固定到告警真实端口（不落默认 Gi0/1）
        if device_type == "REAL" and "iface_name" in (template_def.params_schema or {}):
            validated_params["iface_name"] = device_info_dict.get("interface_name") or "Gi1/0/2"

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

        # ADR-RE-002/006: REAL 走工作流层只读备份（不 save、不写），复用会话链
        if self._get_device_type(state) == "REAL":
            result = self._real_backup(device_info, auth)
            self._log_node(state, node, "END")
            return {
                "config_backup": result.config or "",
                "backup_id": result.backup_id or "",
                "_backup_success": result.success,
            }

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
        alert_id = state.get("alert_id", "")

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

        # ADR-RE-006: REAL 写操作端口白名单校验（不 save、不下发 description）
        if device_type == "REAL" and commands:
            target_port = device_info.get("interface_name") or "Gi1/0/2"
            if target_port not in REAL_WRITE_PORT_WHITELIST:
                exec_log = [{
                    "command": "",
                    "success": False,
                    "output": "",
                    "error": f"REAL 写操作目标端口 {target_port!r} 不在授权白名单 {sorted(REAL_WRITE_PORT_WHITELIST)}",
                    "execution_time_ms": 0,
                    "was_idempotent_skip": False,
                }]
                self.audit_logger.log_audit_event(
                    event_type=AuditEventType.CONFIG_CHANGE,
                    alert_id=state.get("alert_id", ""),
                    operator="auto_agent",
                    action="configure",
                    detail={
                        "command": "",
                        "success": False,
                        "device_ip": device_ip,
                        "message": f"写操作端口越权拦截: {target_port}",
                    },
                )
                self._log_node(state, node, "END", status="FAILED")
                return {
                    "exec_log": exec_log,
                    "status": "FAILED",
                    "_error_message": f"REAL 写操作端口越权: {target_port}",
                }

        if device_type == "REAL" and commands:
            # ADR-RE-006: interface + shutdown/no shutdown 必须在同一 config 会话
            # 连续执行，逐条各开一个会话会把 shutdown 落到全局 config 模式。
            from src.tools.switch_config_tool import create_switch_config_tool
            config_tool = create_switch_config_tool(device_type="REAL")
            for rec in config_tool.run_records(device_ip, commands, auth):
                record = {
                    "command": rec.get("command", ""),
                    "success": rec.get("success", False),
                    "output": rec.get("output", ""),
                    "error": rec.get("error"),
                    "execution_time_ms": 500,
                    "was_idempotent_skip": False,
                }
                exec_log.append(record)
                self.audit_logger.log_audit_event(
                    event_type=AuditEventType.CONFIG_CHANGE,
                    alert_id=state.get("alert_id", ""),
                    operator="auto_agent",
                    action="configure",
                    detail={
                        "command": record["command"],
                        "success": record["success"],
                        "device_ip": device_ip,
                    },
                )
        else:
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
        alert_id = state.get("alert_id", "")

        alert_type = state.get("alert_type", AlertType.PORT_DOWN)
        device_info = state.get("device_info", {})
        device_ip = device_info.get("device_ip", "0.0.0.0")
        before_diag = state.get("diag_result", "")

        # 重新执行诊断（ADR-RE-003: device_type 感知）
        device_type = self._get_device_type(state)
        commands = get_diag_commands(alert_type, device_type)
        after_outputs: list[str] = []
        auth = self._extract_auth(device_info)

        sim_conn = self._resolve_simulator_connection(state)
        if sim_conn:
            device_ip = sim_conn[0]
            auth.port = sim_conn[1]
            auth.username = sim_conn[2]
            auth.password = sim_conn[3]

        strip_real = None
        if device_type == "REAL":
            from src.tools.real_device_client import _strip_echo_and_prompts
            strip_real = _strip_echo_and_prompts

        for command in commands[:1]:  # 验证仅跑第一条命令（快速检查）
            actual_command = command
            if device_type != "REAL" and alert_type == AlertType.PORT_DOWN:
                iface = device_info.get("interface_name", "Gi0/1")
                actual_command = f"show interface {iface}"

            verify_diag_tool = self._get_diag_tool_for_device(state)
            if verify_diag_tool:
                result = verify_diag_tool._run(device_ip, actual_command, auth)
                if result.success:
                    output = result.output or ""
                    if device_type == "REAL":
                        output = strip_real(output, actual_command)
                    after_outputs.append(output)
                else:
                    after_outputs.append(f"ERROR: {result.error}")
            else:
                after_outputs.append("Mock verify: OK")

        after_diag = "\n".join(after_outputs)

        if device_type == "REAL":
            # ADR-RE-005: 结构化验证（parse_interface_status Status 列）
            target_port = device_info.get("interface_name") or "Gi1/0/2"
            verify = verify_real_fix(alert_type, before_diag, after_diag, target_port)
            verify_passed = verify.verify_passed
        else:
            # MOCK / SIMULATOR 原关键词逻辑逐字不变
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

        # ADR-RE-004: 降级修复标记（真实诊断 + 告警闭环、修复降级）
        degraded_fix = (
            not fix_plan.commands
            and ("修复降级" in (fix_plan.description or "") or not fix_plan.template_id)
        )

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

        # ADR-RE-004: 降级修复在最终报告中显式标注，状态仍为 CLOSED（告警闭环）
        if degraded_fix:
            final_report = "## 修复降级 / 不可修复\n\n" + final_report

        # Sync status to SQLite
        try:
            from src.database.base import SessionLocal
            from src.database.repositories.alert_repository import AlertRepository
            db = SessionLocal()
            try:
                AlertRepository(db).update_alert_status(alert_id, status.value)
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

    def _persist_fix_plan(self, alert_id: str, fix_plan: FixPlan) -> None:
        """MOD-DP-006: 持久化 fix_plan 到 DB（失败仅告警，不阻断工作流）。"""
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

    @staticmethod
    def _real_backup(device_info: dict[str, Any], auth: DeviceAuth) -> BackupResult:
        """REAL 只读配置备份：经 FRP 会话执行 show running-config，不 save、不写。"""
        from src.tools.real_device_client import (
            _open_ssh_session, _open_telnet_session, _strip_echo_and_prompts,
        )
        from src.tools.real_session_gate import session_guard_by_access

        host = device_info.get("device_ip", "")
        port = int(device_info.get("port") or auth.port or 22)
        protocol = (device_info.get("protocol") or auth.protocol or "SSH").upper()
        username = auth.username or "admin"
        password = auth.password or ""

        if not host or not username or not password:
            return BackupResult(success=False, error="REAL 备份接入信息不完整")

        try:
            with session_guard_by_access(host, port, protocol):
                if protocol == "SSH":
                    sess = _open_ssh_session(host, port, username, password)
                elif protocol == "TELNET":
                    sess = _open_telnet_session(host, port, username, password)
                else:
                    return BackupResult(success=False, error=f"Unsupported protocol {protocol}")
                try:
                    raw = sess.show("show running-config")
                finally:
                    try:
                        sess.close()
                    except Exception:
                        pass
        except Exception as e:
            logger.warning(f"REAL backup failed: {e}")
            return BackupResult(success=False, error=f"REAL 备份失败: {e.__class__.__name__}: {e}")

        config = _strip_echo_and_prompts(raw or "", "show running-config")
        if not config:
            return BackupResult(success=False, error="REAL 备份输出为空")
        return BackupResult(success=True, config=config)

    @staticmethod
    def _extract_auth(device_info: dict[str, Any]) -> DeviceAuth:
        """从设备信息中提取认证凭据（IFC-RE-001-03: 透传 protocol）。"""
        return DeviceAuth(
            username=device_info.get("username", "admin"),
            password=device_info.get("password", "admin123"),
            enable_password=device_info.get("enable_password"),
            port=device_info.get("port", 22),
            protocol=device_info.get("protocol", "SSH"),
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
                elif device_type == "REAL":
                    from src.tools.switch_config_tool import create_switch_config_tool
                    config_tool = create_switch_config_tool(device_type="REAL")
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
