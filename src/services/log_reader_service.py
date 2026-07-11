"""
MOD-WEB-007: LogReaderService — File-based log reading and searching.
@author sub_agent_software_developer
@module MOD-WEB-007
@implements IFC-WEB-007-01, IFC-WEB-007-02
@depends None

Reads operations.log and audit.log from the filesystem with filtering
and pagination. Uses reverse reading for efficient tail access to large files.
@covers REQ-WEBUI-FUNC-021
"""

import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from loguru import logger


LOG_SOURCES = {
    "operations": "./logs/operations_{date}.log",
    "audit": "./logs/audit.log",
}

# Matches loguru format: YYYY-MM-DD HH:mm:ss.SSS | ...
LOG_LINE_PATTERN = re.compile(
    r"^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d{3})\s*\|\s*(INFO|WARNING|ERROR|DEBUG)\s*\|"
)


class LogReaderService:
    """
    File-based log reader for operations and audit logs.

    Features:
    - Reverse reading for efficient tail access
    - Level filtering (INFO / WARNING / ERROR)
    - Keyword search (case-insensitive substring match)
    - Time range filtering
    - Paginated output (max 500 per page)
    """

    def __init__(self, logs_dir: str = "./logs/"):
        self._logs_dir = logs_dir

    # ── IFC-WEB-007-02: get_log_sources ─────────────────────

    @staticmethod
    def get_log_sources() -> list[str]:
        """Return available log sources."""
        return list(LOG_SOURCES.keys())

    # ── IFC-WEB-007-01: read_logs ───────────────────────────

    def read_logs(
        self,
        source: str = "operations",
        level: str | None = None,
        keyword: str | None = None,
        time_from: datetime | None = None,
        time_to: datetime | None = None,
        page: int = 1,
        page_size: int = 100,
    ) -> dict:
        """
        Read logs from the specified source with filtering and pagination.

        Returns:
            dict with keys: entries, total, page, page_size
        """
        if source not in LOG_SOURCES:
            return {"entries": [], "total": 0, "page": page, "page_size": page_size,
                    "error": f"Unknown log source: {source}"}

        file_path = self._resolve_path(source)
        if not os.path.isfile(file_path):
            return {"entries": [], "total": 0, "page": page, "page_size": page_size}

        entries: list[dict] = []
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        except OSError as e:
            logger.error(f"Failed to read log file {file_path}: {e}")
            return {"entries": [], "total": 0, "page": page, "page_size": page_size,
                    "error": str(e)}

        # Read from end (reverse) — most recent entries first
        lines.reverse()

        for raw_line in lines:
            entry = self._parse_line(raw_line.strip())
            if entry is None:
                continue

            # Apply filters
            if not self._match_filters(entry, level, keyword, time_from, time_to):
                continue

            entries.append(entry)

            # Limit to prevent memory issues
            if len(entries) >= 5000:
                break

        total = len(entries)

        # Apply pagination
        start = (page - 1) * page_size
        end = start + page_size
        paged_entries = entries[start:end] if start < total else []

        return {
            "entries": paged_entries,
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    # ── Internal helpers ────────────────────────────────────

    def _resolve_path(self, source: str) -> str:
        """Resolve the log file path, handling date-based rotation."""
        pattern = LOG_SOURCES.get(source, "")
        if "{date}" in pattern:
            today = datetime.now().strftime("%Y-%m-%d")
            return pattern.format(date=today)
        return pattern

    @staticmethod
    def _parse_line(line: str) -> dict | None:
        """Parse a single log line into a structured entry."""
        if not line:
            return None

        match = LOG_LINE_PATTERN.match(line)
        if not match:
            # Try to parse loosely — take the whole line as message
            return {
                "timestamp": "",
                "level": "INFO",
                "module": "",
                "message": line[:500],
                "details": None,
            }

        timestamp_str = match.group(1)
        level_val = match.group(2)

        # Parse the rest as module and message
        rest = line[match.end():].strip()
        parts = rest.split("|", 2)
        module_val = parts[0].strip() if len(parts) > 0 else ""
        message_val = parts[1].strip() if len(parts) > 1 else rest[:500]

        # Attempt to parse timestamp
        parsed_ts: datetime | None = None
        try:
            parsed_ts = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S.%f")
        except ValueError:
            parsed_ts = datetime.now(timezone.utc)

        return {
            "timestamp": parsed_ts.isoformat() if parsed_ts else timestamp_str,
            "level": level_val,
            "module": module_val,
            "message": message_val[:500],
            "details": None,
        }

    @staticmethod
    def _match_filters(
        entry: dict,
        level: str | None,
        keyword: str | None,
        time_from: datetime | None,
        time_to: datetime | None,
    ) -> bool:
        """Check whether an entry matches the given filters."""
        # Level filter
        if level and entry.get("level", "").upper() != level.upper():
            return False

        # Keyword filter (case-insensitive)
        if keyword:
            msg = entry.get("message", "").lower()
            if keyword.lower() not in msg:
                return False

        # Time range filter
        if time_from or time_to:
            ts_str = entry.get("timestamp", "")
            if ts_str:
                try:
                    ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                    if time_from and ts < time_from:
                        return False
                    if time_to and ts > time_to:
                        return False
                except (ValueError, TypeError):
                    pass

        return True
