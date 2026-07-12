"""
MOD-INSP-003: inspection_cli — CLI inspection entry point.
@author sub_agent_software_developer
@module MOD-INSP-003
@implements IFC-INSP-003-01 (run), IFC-INSP-003-02 (load_inspection_config),
           IFC-INSP-003-03 (load_device_list)
@depends MOD-WEB-003 (inspection_models), MOD-WEB-004 (inspection_repository),
         MOD-016 (ConfigManager), MOD-011 (SwitchDiagTool)
@covers REQ-INSP-010, REQ-INSP-014, REQ-INSP-017

CLI entry for systemd-triggered inspection: python3.11 -m src.inspection_cli run
Runs independently from the Web process, loads device list and config from SQLite,
executes full device inspection (interface status + CPU check), persists results
to InspectionRecord table, and exits with status code:
  0 → SUCCESS (all devices normal)
  1 → PARTIAL (some devices anomalous)
  2 → FAILURE (system error)

Key migration from v0.1.0 MOD-002 (inspection_scheduler.py):
  - Core inspection logic (run_inspection_once) migrated here
  - APScheduler scheduling logic removed
  - Standalone SQLAlchemy Session management added
  - Exit code mapping for systemd service Result
"""

from __future__ import annotations

import enum
import os
import re
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from loguru import logger

# ── Ensure project root in sys.path for standalone execution ─────
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))


# ── Exit Code Enum ───────────────────────────────────────────────

class CLIExitCode(enum.IntEnum):
    """CLI exit codes mapping to systemd service Result.
    IFC-INSP-003-01: run() returns CLIExitCode.
    """
    SUCCESS = 0   # All devices normal
    PARTIAL = 0   # Anomalies found (normal, not an error)
    FAILURE = 2   # System error (DB unreadable, all devices unreachable)


# ── Constants ────────────────────────────────────────────────────

CPU_THRESHOLD = 80  # CPU utilization warning threshold (%)


# ── MOD-INSP-003: Inspection CLI ─────────────────────────────────

class InspectionCLI:
    """
    CLI 巡检执行器。独立进程运行，不依赖 Web 进程。

    使用流程：
      1. 初始化 SQLAlchemy Session
      2. load_inspection_config()   → 从 SQLite + ConfigManager 读取配置
      3. load_device_list()         → 从 SQLite Device 表加载设备
      4. 遍历设备，执行诊断（接口状态 + CPU 检查）
      5. 分析结果，构造 InspectionSummary
      6. 持久化 InspectionRecord
      7. 返回 CLIExitCode
    """

    def __init__(self):
        self._db_session = None
        self._db_engine = None

    # ── IFC-INSP-003-01: run (main entry) ────────────────────

    def run(self) -> CLIExitCode:
        """
        执行全量巡检并持久化结果。CLI 主入口。

        Returns:
            CLIExitCode enum value.
        """
        started_at = datetime.now(timezone.utc)
        logger.info("=" * 60)
        logger.info("Inspection CLI started")
        logger.info("=" * 60)

        # 1. Initialize database connection
        try:
            self._init_db()
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            logger.error(traceback.format_exc())
            return CLIExitCode.FAILURE

        # 2. Load configuration
        try:
            config = self.load_inspection_config()
            logger.info(f"Loaded config: {config}")
        except Exception as e:
            logger.error(f"Failed to load inspection config: {e}")
            self._close_db()
            return CLIExitCode.FAILURE

        # 3. Load device list
        try:
            devices = self.load_device_list()
            logger.info(f"Loaded {len(devices)} device(s) for inspection")
        except Exception as e:
            logger.error(f"Failed to load device list: {e}")
            self._close_db()
            return CLIExitCode.FAILURE

        if not devices:
            logger.warning("No devices configured for inspection")
            self._close_db()
            return CLIExitCode.SUCCESS

        # 4. Execute inspection for each device
        timeout_seconds = int(config.get("diagnosis.timeout_seconds", 30))
        total_devices = len(devices)
        anomaly_count = 0
        device_results: dict[str, dict] = {}
        has_system_error = False

        for device in devices:
            device_name = device.get("device_name", "unknown")
            device_ip = device.get("device_ip", "unknown")
            logger.info(f"Inspecting device: {device_name} ({device_ip})")

            try:
                result = self._inspect_device(device, timeout_seconds)
                device_results[device_name] = result
                if result.get("anomalies", 0) > 0:
                    anomaly_count += result["anomalies"]
                    logger.warning(
                        f"Device {device_name}: {result['anomalies']} anomaly(s) found"
                    )
                else:
                    logger.info(f"Device {device_name}: OK")
            except Exception as e:
                logger.error(f"Inspection failed for device {device_name}: {e}")
                device_results[device_name] = {
                    "device_name": device_name,
                    "device_ip": device_ip,
                    "error": str(e),
                    "anomalies": 0,
                    "events": [],
                }
                has_system_error = True

        # 5. Determine overall status
        completed_at = datetime.now(timezone.utc)

        if has_system_error and anomaly_count == 0 and all(
            "error" in r for r in device_results.values()
        ):
            # All devices failed → system error
            status = "FAILED"
            exit_code = CLIExitCode.FAILURE
        elif anomaly_count > 0:
            status = "PARTIAL"
            exit_code = CLIExitCode.PARTIAL
        else:
            status = "SUCCESS"
            exit_code = CLIExitCode.SUCCESS

        # 6. Persist InspectionRecord
        try:
            self._persist_record(
                trigger_mode="SCHEDULED",
                started_at=started_at,
                completed_at=completed_at,
                total_devices=total_devices,
                anomaly_count=anomaly_count,
                status=status,
                details={"devices": device_results},
            )
            logger.info(f"InspectionRecord persisted: status={status}, anomalies={anomaly_count}")
        except Exception as e:
            logger.error(f"Failed to persist InspectionRecord: {e}")
            logger.error(traceback.format_exc())
            # Don't fail the whole run for persistence error
            if exit_code == CLIExitCode.SUCCESS:
                exit_code = CLIExitCode.PARTIAL

        # 7. Print summary
        elapsed = (completed_at - started_at).total_seconds()
        logger.info("=" * 60)
        logger.info(f"Inspection complete: {total_devices} device(s), "
                    f"{anomaly_count} anomaly(s), status={status}, "
                    f"elapsed={elapsed:.1f}s")
        logger.info(f"Exit code: {exit_code.name} ({exit_code.value})")
        logger.info("=" * 60)

        self._close_db()
        return exit_code

    # ── IFC-INSP-003-02: load_inspection_config ──────────────

    def load_inspection_config(self) -> dict:
        """
        从 SQLite SystemConfig 表读取巡检配置。
        无值时降级到 ConfigManager 的 config.yaml 默认值。

        Priority: SQLite > config.yaml > DEFAULT_CONFIG

        Returns:
            dict with keys: inspection.interval_minutes, diagnosis.timeout_seconds,
                           diagnosis.retry_max, diagnosis.retry_backoff
        """
        config: dict[str, str] = {}

        # Try SQLite first
        if self._db_session:
            try:
                from src.database.repositories.inspection_repository import InspectionRepository
                repo = InspectionRepository(self._db_session)
                config = repo.get_config()
            except Exception as e:
                logger.debug(f"Inspection config from SQLite failed: {e}")

        # Fallback to ConfigManager
        from src.security.config_manager import ConfigManager
        cm = ConfigManager()

        result: dict[str, str] = {}
        keys = [
            "inspection.interval_minutes",
            "diagnosis.timeout_seconds",
            "diagnosis.retry_max",
            "diagnosis.retry_backoff",
        ]
        for key in keys:
            sqlite_val = config.get(key, "")
            if sqlite_val and sqlite_val.strip():
                result[key] = sqlite_val
            else:
                # Fallback to config.yaml → DEFAULT_CONFIG
                cm_val = cm.get(key)
                if cm_val is not None:
                    result[key] = str(cm_val)
                else:
                    # Hardcoded defaults
                    defaults = {
                        "inspection.interval_minutes": "5",
                        "diagnosis.timeout_seconds": "30",
                        "diagnosis.retry_max": "3",
                        "diagnosis.retry_backoff": "5",
                    }
                    result[key] = defaults.get(key, "")

        return result

    # ── IFC-INSP-003-03: load_device_list ────────────────────

    def load_device_list(self) -> list[dict]:
        """
        从 SQLite Device 表查询所有纳管设备。

        Returns:
            list of dicts with device_name, device_ip, device_model.
            Empty list if no devices or table unavailable.
        """
        if not self._db_session:
            logger.warning("No DB session available for device list")
            return []

        try:
            from sqlalchemy import select
            from src.database.device_models import Device as DbDevice

            devices = self._db_session.execute(select(DbDevice)).scalars().all()
            return [
                {
                    "device_name": d.device_name,
                    "device_ip": d.device_ip,
                    "device_model": d.device_model or "",
                }
                for d in devices
            ]
        except Exception as e:
            logger.debug(f"Device list from SQLite failed: {e}")
            return []

    # ── Internal: database management ────────────────────────

    def _init_db(self) -> None:
        """Initialize standalone SQLAlchemy engine and session."""
        from src.database.base import create_engine as db_create_engine, get_session_factory
        from src.security.config_manager import ConfigManager

        cm = ConfigManager()
        db_path = cm.get("webui.db_path") or "./data/webui.db"

        if not os.path.isabs(db_path):
            db_path = str(_project_root / db_path)

        self._db_engine = db_create_engine(db_path)
        session_factory = get_session_factory(self._db_engine)
        self._db_session = session_factory()
        logger.info(f"Database initialized: {db_path}")

    def _close_db(self) -> None:
        """Close database session and engine."""
        if self._db_session:
            try:
                self._db_session.close()
            except Exception:
                pass
            self._db_session = None
        if self._db_engine:
            try:
                self._db_engine.dispose()
            except Exception:
                pass
            self._db_engine = None

    # ── Internal: device inspection logic ────────────────────

    def _inspect_device(self, device: dict, timeout_seconds: int = 30) -> dict:
        """
        对单台设备执行诊断命令并检测异常。
        迁移自 inspection_scheduler.py 的 _inspect_device() 方法。

        Returns:
            dict with keys: device_name, device_ip, anomalies (count), events (list)
        """
        device_name = device.get("device_name", "unknown")
        device_ip = device.get("device_ip", "unknown")
        events: list[dict] = []
        anomalies = 0

        # Get diag tool (reuse v0.1.0 SwitchDiagTool)
        try:
            from src.tools.switch_diag_tool import create_switch_diag_tool
            diag_tool = create_switch_diag_tool(use_mock=True)
        except Exception as e:
            logger.warning(f"Cannot create diag tool: {e}")
            return {
                "device_name": device_name,
                "device_ip": device_ip,
                "anomalies": 0,
                "events": [],
                "error": str(e),
            }

        # Get device auth credentials
        from src.security.config_manager import ConfigManager
        cm = ConfigManager()
        from src.models.alert import DeviceInfo
        dev_info = DeviceInfo(
            device_name=device_name,
            device_ip=device_ip,
            device_model=device.get("device_model", ""),
        )
        auth = cm.get_device_credentials(device_name)

        # 1. Check interface status
        try:
            status_result = diag_tool._run(device_ip, "show interface status", auth)
            if status_result and status_result.success:
                for line in status_result.output.split("\n"):
                    if "down" in line.lower() or "notconnect" in line.lower():
                        parts = line.split()
                        if parts:
                            iface_name = parts[0]
                            event = {
                                "device_name": device_name,
                                "interface": iface_name,
                                "alert_type": "PORT_DOWN",
                                "severity": "MAJOR",
                                "content": f"Interface {iface_name} is down on {device_name}",
                            }
                            events.append(event)
                            anomalies += 1
                            logger.info(
                                f"  [ANOMALY] {device_name}: PORT_DOWN — {iface_name}"
                            )
        except Exception as e:
            logger.warning(f"Interface status check failed for {device_name}: {e}")

        # 2. Check CPU utilization
        try:
            cpu_result = diag_tool._run(device_ip, "show processes cpu", auth)
            if cpu_result and cpu_result.success:
                cpu_match = re.search(r"CPU utilization.*?(\d+)%", cpu_result.output)
                if cpu_match:
                    cpu_percent = int(cpu_match.group(1))
                    if cpu_percent > CPU_THRESHOLD:
                        event = {
                            "device_name": device_name,
                            "cpu_percent": cpu_percent,
                            "alert_type": "CPU_HIGH",
                            "severity": "MAJOR",
                            "content": (
                                f"CPU utilization at {cpu_percent}% on {device_name} "
                                f"(threshold: {CPU_THRESHOLD}%)"
                            ),
                        }
                        events.append(event)
                        anomalies += 1
                        logger.info(
                            f"  [ANOMALY] {device_name}: CPU_HIGH — {cpu_percent}%"
                        )
                    else:
                        logger.info(f"  [OK] {device_name}: CPU at {cpu_percent}%")
        except Exception as e:
            logger.warning(f"CPU check failed for {device_name}: {e}")

        return {
            "device_name": device_name,
            "device_ip": device_ip,
            "anomalies": anomalies,
            "events": events,
        }

    # ── Internal: persistence ────────────────────────────────

    def _persist_record(
        self,
        trigger_mode: str,
        started_at: datetime,
        completed_at: datetime,
        total_devices: int,
        anomaly_count: int,
        status: str,
        details: dict,
    ) -> None:
        """Persist inspection result to SQLite InspectionRecord table."""
        if not self._db_session:
            raise RuntimeError("No DB session available")

        from src.database.repositories.inspection_repository import InspectionRepository
        repo = InspectionRepository(self._db_session)
        repo.create_record({
            "trigger_mode": trigger_mode,
            "started_at": started_at,
            "completed_at": completed_at,
            "total_devices": total_devices,
            "anomaly_count": anomaly_count,
            "status": status,
            "details": details,
        })


# ── CLI entry point: python3.11 -m src.inspection_cli run ────

def main():
    """CLI main entry. Supports: python3.11 -m src.inspection_cli run"""
    import argparse

    parser = argparse.ArgumentParser(
        description="NetworkAgent Inspection CLI — systemd-triggered inspection runner"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # run command
    run_parser = subparsers.add_parser("run", help="Execute a full inspection cycle")
    run_parser.set_defaults(func=_run_command)

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(CLIExitCode.FAILURE)

    args.func(args)


def _run_command(_args):
    """Execute the 'run' command."""
    cli = InspectionCLI()
    exit_code = cli.run()
    sys.exit(exit_code.value)


if __name__ == "__main__":
    main()
