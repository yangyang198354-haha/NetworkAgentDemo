"""
MOD-015: AuditLogger — Full-chain operation logging and immutable audit trail.
@author sub_agent_software_developer
@module MOD-015
@implements IFC-015-01, IFC-015-02, IFC-015-03, IFC-015-04
@depends None
@covers REQ-NFUNC-010, REQ-NFUNC-011
"""

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from loguru import logger

from src.models.enums import AuditEventType
from src.models.fix_plan import AuditRecord, PendingApprovalRecord


class AuditLogger:
    """
    全链路审计日志管理器（单例模式）。
    实现 IFC-015-01 (log_node_execution), IFC-015-02 (log_audit_event),
    IFC-015-03 (query_by_alert_id), IFC-015-04 (get_pending_approvals).

    日志文件路径（由 ConfigManager 配置）:
      - 操作日志: ./logs/operations_{date}.log
      - 审计日志: ./logs/audit.log（永久追加，不可删除）
    """

    _instance: Optional["AuditLogger"] = None
    _lock: threading.Lock = threading.Lock()

    def __new__(cls) -> "AuditLogger":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    instance = super().__new__(cls)
                    instance._pending_approvals: dict[str, PendingApprovalRecord] = {}
                    instance._audit_records: dict[str, list[AuditRecord]] = {}  # alert_id → records
                    instance._initialized = False
                    instance._ops_log_path = "./logs/"
                    instance._audit_log_path = "./logs/audit.log"
                    instance._enabled = True
                    cls._instance = instance
        return cls._instance

    def configure(self, ops_log_path: str, audit_log_path: str, enabled: bool = True) -> None:
        """配置日志路径（由 main.py 在启动时调用）。"""
        self._ops_log_path = ops_log_path
        self._audit_log_path = audit_log_path
        self._enabled = enabled

        # 确保日志目录存在
        Path(ops_log_path).mkdir(parents=True, exist_ok=True)
        Path(audit_log_path).parent.mkdir(parents=True, exist_ok=True)

        # 配置文件日志 sink
        logger.add(
            Path(ops_log_path) / "operations_{time:YYYY-MM-DD}.log",
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {extra[alert_id]} | {extra[node_name]} | {extra[phase]} | {extra[state_summary]} | duration={extra[duration_ms]}ms",
            rotation="00:00",
            retention="30 days",
            level="INFO",
            filter=lambda record: "alert_id" in record.get("extra", {}),
            enqueue=True,
        )
        self._initialized = True

    # ── IFC-015-01: log_node_execution ──────────────────────

    def log_node_execution(
        self,
        alert_id: str,
        node_name: str,
        phase: str,  # "START" | "END"
        state_summary: dict[str, Any],
        duration_ms: Optional[int] = None,
    ) -> None:
        """记录节点执行事件到操作日志。"""
        if not self._enabled or not self._initialized:
            return

        logger.bind(
            alert_id=alert_id,
            node_name=node_name,
            phase=phase,
            state_summary=json.dumps(state_summary, ensure_ascii=False, default=str),
            duration_ms=duration_ms or 0,
        ).info(f"Node {node_name} {phase}")

    # ── IFC-015-02: log_audit_event ─────────────────────────

    def log_audit_event(
        self,
        event_type: str,
        alert_id: str,
        operator: str,
        action: str,
        detail: dict[str, Any],
    ) -> str:
        """
        记录不可篡改审计事件到 audit.log。
        返回 audit_record_id。
        """
        timestamp = datetime.now(timezone.utc).isoformat()
        record = AuditRecord(
            timestamp=timestamp,
            event_type=event_type,
            alert_id=alert_id,
            operator=operator,
            action=action,
            detail=detail,
        )

        # 内存缓存
        if alert_id not in self._audit_records:
            self._audit_records[alert_id] = []
        self._audit_records[alert_id].append(record)

        # 追加写入审计日志文件
        if self._enabled:
            try:
                audit_path = Path(self._audit_log_path)
                audit_path.parent.mkdir(parents=True, exist_ok=True)
                with open(audit_path, "a", encoding="utf-8") as f:
                    f.write(
                        f"{timestamp} | {event_type} | {alert_id} | {operator} | {action} | "
                        f"{json.dumps(detail, ensure_ascii=False, default=str)}\n"
                    )
            except OSError as e:
                logger.error(f"Failed to write audit log: {e}")

        # 审批事件特殊处理：维护 pending_approvals
        if event_type == AuditEventType.APPROVAL_DECISION:
            # 移除对应的 pending approval
            checkpoint_id = detail.get("checkpoint_id", "")
            if checkpoint_id in self._pending_approvals:
                del self._pending_approvals[checkpoint_id]

        return record.record_id

    # ── IFC-015-03: query_by_alert_id ───────────────────────

    def query_by_alert_id(self, alert_id: str) -> list[AuditRecord]:
        """按告警 ID 查询全链路审计记录。"""
        return self._audit_records.get(alert_id, [])

    # ── IFC-015-04: get_pending_approvals ───────────────────

    def get_pending_approvals(self) -> list[PendingApprovalRecord]:
        """查询所有审批挂起中的记录。"""
        return list(self._pending_approvals.values())

    # ── 非接口契约的辅助方法 ────────────────────────────────

    def register_pending_approval(self, record: PendingApprovalRecord) -> None:
        """注册一个挂起审批项（由 MOD-005 human_approval 节点调用）。"""
        self._pending_approvals[record.checkpoint_id] = record

    def remove_pending_approval(self, checkpoint_id: str) -> None:
        """移除挂起审批项。"""
        self._pending_approvals.pop(checkpoint_id, None)

    def log_info(self, message: str) -> None:
        """通用 INFO 日志。"""
        logger.info(message)

    def log_warning(self, message: str) -> None:
        """通用 WARNING 日志。"""
        logger.warning(message)

    def log_error(self, message: str) -> None:
        """通用 ERROR 日志。"""
        logger.error(message)
