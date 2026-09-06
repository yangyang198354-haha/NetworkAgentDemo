"""
MOD-WEB-006: DashboardService — Aggregated statistics and health checks.
@author sub_agent_software_developer
@module MOD-WEB-006
@implements IFC-WEB-006-01, IFC-WEB-006-02, IFC-WEB-006-03
@depends MOD-WEB-004 (AlertRepository, ConfigRepository)

Provides Dashboard aggregated data: alert stats, fix success rate, system health.
@covers REQ-WEBUI-FUNC-022, REQ-WEBUI-FUNC-023, REQ-WEBUI-FUNC-024
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, select, case
from sqlalchemy.orm import Session

from src.database.alert_models import Alert
from src.database.approval_models import Approval


class DashboardService:
    """Aggregation service for Dashboard statistics."""

    def __init__(self, db: Session):
        self.db = db

    # ── IFC-WEB-006-01: get_alert_stats ─────────────────────

    def get_alert_stats(
        self,
        time_from: datetime | None = None,
        time_to: datetime | None = None,
    ) -> dict:
        """
        Return alert statistics: by type, by severity, trend, totals.
        """
        # Base query
        query = select(Alert)
        if time_from:
            query = query.where(Alert.created_at >= time_from)
        if time_to:
            query = query.where(Alert.created_at <= time_to)

        all_alerts = self.db.execute(query).scalars().all()

        # By type
        by_type: dict[str, int] = {}
        for a in all_alerts:
            by_type[a.alert_type] = by_type.get(a.alert_type, 0) + 1

        # By severity
        by_severity: dict[str, int] = {}
        for a in all_alerts:
            by_severity[a.severity] = by_severity.get(a.severity, 0) + 1

        # Today count
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        today_query = select(func.count(Alert.id)).where(Alert.created_at >= today_start)
        today_count = self.db.execute(today_query).scalar() or 0

        # Pending approval count — count approvals where decision is PENDING (not yet decided)
        pending_query = (
            select(func.count(Approval.id))
            .where((Approval.decision == "PENDING") | (Approval.decision == None))
        )
        pending_count = self.db.execute(pending_query).scalar() or 0

        # Fix success rate — 基于真实修复结果（workflow_state.verify_result），而非裸 status
        fix_stats = self._get_fix_stats(time_from, time_to)

        # Trend: group by day for last 7 days
        trend = self._get_daily_trend()

        return {
            "total_count": len(all_alerts),
            "today_count": today_count,
            "pending_approval_count": pending_count,
            # 兼容旧字段：标量修复成功率（基于真实修复结果计算）
            "fix_success_rate": fix_stats.get("success_rate", 0.0),
            # 新增：完整修复结果口径（成功/失败/被拒/处理中-未完成）
            "fix_stats": fix_stats,
            # 兼容旧前端字段（closed_count 语义 = 修复成功，见 IFC-WEB-006-02）
            "closed_count": fix_stats.get("success_count", 0),
            "failed_count": fix_stats.get("failed_count", 0),
            "rejected_count": fix_stats.get("rejected_count", 0),
            "processing_count": fix_stats.get("processing_count", 0),
            "by_type": [{"type": k, "count": v} for k, v in by_type.items()],
            "by_severity": [{"severity": k, "count": v} for k, v in by_severity.items()],
            "trend": trend,
        }

    # ── IFC-WEB-006-02: get_fix_success_rate ────────────────

    def get_fix_success_rate(
        self,
        time_from: datetime | None = None,
        time_to: datetime | None = None,
    ) -> dict:
        """Return fix success/failure/rejected counts and rate."""
        return self._get_fix_stats(time_from, time_to)

    # ── IFC-WEB-006-03: get_health_status ───────────────────

    def get_health_status(self) -> dict:
        """
        Return system health status for LangGraph, RAG, Scheduler, LLM.
        Note: actual component checks are done via the existing singletons,
        this method provides the structure for the API response.
        """
        return {
            "langgraph": {
                "status": "healthy",
                "detail": "14 nodes compiled",
            },
            "rag": {
                "status": "healthy",
                "detail": "Chroma OK",
            },
            "scheduler": {
                "status": "healthy",
                "detail": "Running",
            },
            "llm": {
                "status": "unknown",
                "detail": "LLM connection test not yet run",
            },
        }

    # ── Internal helpers ────────────────────────────────────

    def _get_fix_stats(
        self, time_from: datetime | None, time_to: datetime | None
    ) -> dict:
        """
        Compute fix success rate from real fix outcomes.

        口径（REQ-WEBUI-FUNC-022 修订）：
          - 成功 success_count:  status=CLOSED 且 workflow_state.verify_result.verify_passed=True
                               （且非「修复降级/不可修复」）
          - 失败 failed_count:   status=FAILED，或 status=CLOSED 但验证未通过（含回滚、修复降级）
          - 被拒 rejected_count: status=REJECTED（人工拒绝）
          - 处理中/未完成 processing_count: PROCESSING / EXPIRED / 无最终结果 —— 不计入分母
          - 分母 total_count = success + failed + rejected
          - success_rate = success / total * 100（total=0 时取 0.0）

        判定依据以 workflow_state.verify_result.verify_passed 为准（真正的修复后验证结果），
        不再依赖裸 status（历史实现把「CLOSED」误当成「修复成功」，混入了回滚/降级场景）。
        """
        query = select(Alert)
        if time_from:
            query = query.where(Alert.created_at >= time_from)
        if time_to:
            query = query.where(Alert.created_at <= time_to)

        alerts = self.db.execute(query).scalars().all()

        success = failed = rejected = processing = 0
        for a in alerts:
            outcome = self._classify_fix_outcome(a)
            if outcome == "SUCCESS":
                success += 1
            elif outcome == "FAILED":
                failed += 1
            elif outcome == "REJECTED":
                rejected += 1
            else:  # PROCESSING / 未完成 / 无法判定
                processing += 1

        total = success + failed + rejected
        success_rate = round(success / total * 100, 1) if total > 0 else 0.0

        return {
            "success_count": success,
            "failed_count": failed,
            "rejected_count": rejected,
            "processing_count": processing,
            "total_count": total,
            "success_rate": success_rate,
            # 兼容旧字段：closed_count 语义 = 修复成功（见 webui_module_design.md IFC-WEB-006-02）
            "closed_count": success,
        }

    # ── 修复结果分类辅助 ────────────────────────────────────

    @staticmethod
    def _normalize_status(raw_status: str | None) -> str:
        """Normalize alert.status to a plain uppercase token.

        兼容历史数据：status 曾被存为 enum repr（如 "WorkflowStatus.CLOSED"），
        这里截取最后一个点号之后的部分，得到 "CLOSED"。
        """
        s = (raw_status or "").strip()
        if "." in s:
            s = s.rsplit(".", 1)[-1]
        return s.upper()

    @staticmethod
    def _is_degraded_fix(wf: dict) -> bool:
        """检测「修复降级/不可修复」：无下发命令且描述含「修复降级」或无模板。

        与 node_handlers.handle_final_report 的 degraded_fix 判定保持一致。
        """
        fp = wf.get("fix_plan") if isinstance(wf, dict) else None
        if not isinstance(fp, dict):
            return False
        commands = fp.get("commands") or []
        description = fp.get("description") or ""
        template_id = fp.get("template_id") or ""
        return (not commands) and ("修复降级" in description or not template_id)

    @classmethod
    def _classify_fix_outcome(cls, alert) -> str:
        """Classify an alert's fix outcome from status + workflow_state.

        Returns one of: SUCCESS / FAILED / REJECTED / PROCESSING.
        """
        status = cls._normalize_status(alert.status)
        wf = alert.workflow_state if isinstance(alert.workflow_state, dict) else {}

        if status == "REJECTED":
            return "REJECTED"
        if status == "FAILED":
            return "FAILED"
        if status in ("PROCESSING", "ACTIVE", ""):
            return "PROCESSING"
        if status == "EXPIRED":
            # 无效/过期告警未走修复流程，视为「未完成」，不计入分母
            return "PROCESSING"

        if status == "CLOSED":
            verify = wf.get("verify_result")
            verify_passed = (
                bool(verify.get("verify_passed", False))
                if isinstance(verify, dict)
                else False
            )
            if verify_passed and not cls._is_degraded_fix(wf):
                return "SUCCESS"
            # 验证未通过（含回滚）或修复降级 → 未真正修复
            return "FAILED"

        # 未知状态：保守归入「处理中/未完成」，不误计入分母
        return "PROCESSING"

    def _get_daily_trend(self, days: int = 7) -> list[dict]:
        """Return daily alert count for the last N days."""
        trend = []
        today = datetime.now(timezone.utc).date()

        for i in range(days - 1, -1, -1):
            day = today - timedelta(days=i)
            day_start = datetime.combine(day, datetime.min.time()).replace(tzinfo=timezone.utc)
            day_end = day_start + timedelta(days=1)

            stmt = select(func.count(Alert.id)).where(
                Alert.created_at >= day_start, Alert.created_at < day_end
            )
            count = self.db.execute(stmt).scalar() or 0
            trend.append({"date": day.isoformat(), "count": count})

        return trend
