"""
MOD-DP-003: LLMCallLogRepository — llm_calls table CRUD operations.
@author sub_agent_software_developer
@module MOD-DP-003
@implements IFC-DP-003-01 (create_log), IFC-DP-003-02 (get_logs_by_alert_id),
           IFC-DP-003-03 (get_logs_by_alert_id_as_dicts)
@depends MOD-DP-002 (LLMCallLog)
@covers REQ-FUNC-002, US-002
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.database.llm_call_models import LLMCallLog


class LLMCallLogRepository:
    """Repository for LLMCallLog entities — persist and query LLM API call records."""

    def __init__(self, db: Session):
        self.db = db

    # ── IFC-DP-003-01: create_log ─────────────────────────────

    def create_log(self, log_data: dict) -> LLMCallLog:
        """
        Create and persist a single LLM call log record.

        Required keys in log_data:
          - alert_id_fk (str)
          - endpoint (str)
          - elapsed_s (float)
          - prompt_tokens (int)
          - completion_tokens (int)
        Optional keys:
          - prompt_summary (str | None)
          - response_summary (str | None)
          - is_mock (bool, default False)
          - timestamp (datetime, default now)

        Returns: persisted + refreshed LLMCallLog ORM object.
        """
        log = LLMCallLog(**log_data)
        self.db.add(log)
        self.db.commit()
        self.db.refresh(log)
        return log

    # ── IFC-DP-003-02: get_logs_by_alert_id ───────────────────

    def get_logs_by_alert_id(self, alert_id: str) -> list[LLMCallLog]:
        """
        Return all LLM call log records for a given alert_id, ordered by timestamp ASC.

        Args:
            alert_id: str — the alerts.alert_id value to filter by.

        Returns:
            list[LLMCallLog] — empty list if no records found.
        """
        stmt = (
            select(LLMCallLog)
            .where(LLMCallLog.alert_id_fk == alert_id)
            .order_by(LLMCallLog.timestamp)
        )
        return list(self.db.execute(stmt).scalars().all())

    # ── IFC-DP-003-03: get_logs_by_alert_id_as_dicts ──────────

    def get_logs_by_alert_id_as_dicts(self, alert_id: str) -> list[dict]:
        """
        Return LLM call logs as JSON-serializable dicts for API response.

        Field mapping (API-compatible):
          - endpoint       → "endpoint"
          - timestamp      → "timestamp" (HH:MM:SS format string)
          - elapsed_s      → "elapsed_s"
          - prompt_tokens  → "prompt_tokens"
          - completion_tokens → "completion_tokens"
          - prompt_summary → "prompt"
          - response_summary → "response"

        Returns:
            list[dict] — empty list if no records found.
        """
        logs = self.get_logs_by_alert_id(alert_id)
        result = []
        for log in logs:
            # Robust timestamp formatting: handle both datetime objects and strings
            ts = log.timestamp
            if ts is None:
                ts_str = ""
            elif hasattr(ts, 'strftime'):
                ts_str = ts.strftime("%H:%M:%S")
            else:
                # Fallback for string timestamps: extract HH:MM:SS portion
                ts_str = str(ts)[-12:-3] if len(str(ts)) >= 12 else str(ts)
            result.append({
                "endpoint": log.endpoint,
                "timestamp": ts_str,
                "elapsed_s": log.elapsed_s,
                "prompt_tokens": log.prompt_tokens,
                "completion_tokens": log.completion_tokens,
                "prompt": log.prompt_summary or "",
                "response": log.response_summary or "",
            })
        return result
