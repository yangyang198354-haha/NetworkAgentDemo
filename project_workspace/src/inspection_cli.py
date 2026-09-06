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

    SUCCESS and PARTIAL both map to 0 — the inspection completed successfully
    regardless of whether anomalies were found.  Only system errors (DB failure,
    all devices unreachable) return non-zero to avoid triggering Restart=on-failure.
    """
    SUCCESS = 0   # All devices normal, or no devices
    PARTIAL = 0   # Anomalies found — normal operational result
    FAILURE = 1   # System error (DB unreadable, all devices unreachable)


# ── Constants ────────────────────────────────────────────────────

CPU_THRESHOLD = 80  # CPU utilization warning threshold (%)

# ── PORT_DOWN 告警白名单（按 device_type）──────────────────────────
# 实验室交换机的绝大多数端口未插网线、恒为 down，逐端口上报 PORT_DOWN 会产生大量
# 噪声告警 + 工作流。仅对白名单内端口上报 PORT_DOWN；白名单为 None（缺省）表示
# 全部上报，从而保留 MOCK/SIMULATOR 写死的异常端口行为。
INSPECTION_PORT_WHITELIST: dict[str, frozenset[str]] = {
    "REAL": frozenset({"Gi1/0/2"}),  # 唯一允许写入/关注的 REAL 端口
}


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

    def run(self, trigger_mode: str = "SCHEDULED") -> CLIExitCode:
        """
        执行全量巡检并持久化结果。CLI 主入口。

        Args:
            trigger_mode: "SCHEDULED" (systemd timer) or "MANUAL" (API trigger).

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
            completed_at = datetime.now(timezone.utc)
            try:
                self._persist_record(
                    trigger_mode=trigger_mode,
                    started_at=started_at,
                    completed_at=completed_at,
                    total_devices=0,
                    anomaly_count=0,
                    status="SUCCESS",
                    details={"devices": {}},
                )
                logger.info("InspectionRecord persisted: 0 devices, status=SUCCESS")
            except Exception as e:
                logger.error(f"Failed to persist empty-device InspectionRecord: {e}")
            self._close_db()
            return CLIExitCode.SUCCESS

        # 4. Execute inspection for each device
        timeout_seconds = int(config.get("diagnosis.timeout_seconds", 30))
        total_devices = len(devices)
        anomaly_count = 0
        device_results: dict[str, dict] = {}
        has_system_error = False
        anomaly_alert_ids: list[str] = []  # [NEW] Track created Alert IDs for workflow trigger

        for device in devices:
            device_name = device.get("device_name", "unknown")
            device_ip = device.get("device_ip", "unknown")
            logger.info(f"Inspecting device: {device_name} ({device_ip})")

            try:
                result = self._inspect_device(device, timeout_seconds)
                device_results[device_name] = result
                if result.get("error") and result.get("anomalies", 0) == 0:
                    # 设备不可达/巡检失败（0 异常但有 error）→ 记为系统级失败，
                    # 使「全部设备均失败」时能正确判定 FAILURE（否则误报 SUCCESS）。
                    has_system_error = True
                if result.get("anomalies", 0) > 0:
                    anomaly_count += result["anomalies"]
                    logger.warning(
                        f"Device {device_name}: {result['anomalies']} anomaly(s) found"
                    )

                    # [NEW] Create Alert records for each anomaly event (ADR-001, REQ-FUNC-004)
                    for event in result.get("events", []):
                        alert_id = self._create_alert_from_event(
                            event=event,
                            device=device,
                            trigger_mode=trigger_mode,
                        )
                        if alert_id:
                            anomaly_alert_ids.append(alert_id)
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
        record_id: int | None = None
        try:
            record_id = self._persist_record(
                trigger_mode=trigger_mode,
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
            if exit_code == CLIExitCode.SUCCESS:
                exit_code = CLIExitCode.PARTIAL

        # 6.5. [NEW] Link Alert records to InspectionRecord (ADR-004)
        if anomaly_alert_ids and record_id is not None:
            self._link_alerts_to_record(anomaly_alert_ids, record_id)

        # 6.6. [NEW] Trigger workflows via HTTP callback (ADR-002)
        if anomaly_alert_ids and record_id is not None:
            web_port = int(os.environ.get("APP_PORT", "8001"))
            self._trigger_workflows(anomaly_alert_ids, record_id, web_port)

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
            from sqlalchemy.orm import joinedload
            from src.database.device_models import Device as DbDevice

            devices = (
                self._db_session.execute(
                    select(DbDevice).options(joinedload(DbDevice.credential))
                )
                .scalars()
                .all()
            )
            return [
                {
                    "device_name": d.device_name,
                    "device_ip": d.device_ip,
                    "device_model": d.device_model or "",
                    "device_type": d.device_type or "MOCK",       # G4
                    "simulator_port": d.simulator_port,          # G4
                    # REAL/SIMULATOR 接入解析所需字段（host/FRP/凭据）
                    "connection_protocol": getattr(d, "connection_protocol", None),
                    "frp_proxy_host": getattr(d, "frp_proxy_host", None),
                    "frp_proxy_port": getattr(d, "frp_proxy_port", None),
                    "ssh_username": d.credential.ssh_username if d.credential else None,
                    "ssh_password_encrypted": (
                        d.credential.ssh_password_encrypted if d.credential else None
                    ),
                    "ssh_port": d.credential.ssh_port if d.credential else None,
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

    def _decrypt_password(self, token: Optional[str]) -> str:
        """Fernet 解密设备凭据密码（优先级：ENV 密钥 > data/.encryption_key 文件）。

        不使用 ConfigManager.get_device_credentials() —— 该路径的 decrypt_credential
        是悬空 import，会静默回退成 "admin123"，导致真实设备/模拟器认证失败。
        """
        if not token:
            return ""
        try:
            from src.services.encryption_service import EncryptionService

            svc = EncryptionService()
            if getattr(svc, "_fernet", None) is None:
                svc.initialize()
            return svc.decrypt(token)
        except Exception as e:
            logger.warning(f"Password decrypt failed: {e}")
            return ""

    def _resolve_device_auth(self, device: dict) -> tuple[str, int, str, str, str]:
        """按 device_type 解析 (host, port, protocol, username, password)。

        - SIMULATOR → 127.0.0.1:simulator_port (SSH)
        - REAL      → frp_proxy_host:frp_proxy_port + connection_protocol（FRP 反代），
                      否则回退 device_ip:ssh_port
        - MOCK      → device_ip:ssh_port（无网络，仅占位）
        """
        device_name = device.get("device_name", "unknown")
        dev_type = (device.get("device_type") or "MOCK").upper()

        username = device.get("ssh_username") or "admin"
        env_pwd = os.environ.get(f"DEVICE_{device_name.upper()}_PASSWORD", "").strip()
        password = env_pwd or self._decrypt_password(
            device.get("ssh_password_encrypted")
        )

        if dev_type == "SIMULATOR":
            host = "127.0.0.1"
            port = int(device.get("simulator_port") or 2222)
            protocol = "SSH"
        elif dev_type == "REAL":
            if device.get("frp_proxy_host") and device.get("frp_proxy_port"):
                host = device["frp_proxy_host"]
                port = int(device["frp_proxy_port"])
            else:
                host = device.get("device_ip", "unknown")
                port = int(device.get("ssh_port") or 22)
            protocol = (device.get("connection_protocol") or "SSH").upper()
        else:  # MOCK
            host = device.get("device_ip", "unknown")
            port = int(device.get("ssh_port") or 22)
            protocol = "SSH"

        return host, port, protocol, username, password

    @staticmethod
    def _parse_cpu_percent(output: str, dev_type: str) -> Optional[float]:
        """从诊断命令输出提取 CPU 占用百分比（REAL 设备命令/格式不同）。"""
        if (dev_type or "").upper() == "REAL":
            from src.tools.real_panel_parsers import parse_cpu_utilization

            try:
                return parse_cpu_utilization(output).cpu_5s
            except Exception:
                return None
        m = re.search(r"CPU utilization.*?(\d+)%", output)
        return float(m.group(1)) if m else None

    def _inspect_device(self, device: dict, timeout_seconds: int = 30) -> dict:
        """
        对单台设备执行诊断命令并检测异常。
        迁移自 inspection_scheduler.py 的 _inspect_device() 方法。

        v0.2.x 修复：按 device_type 解析真实接入地址（SIMULATOR→127.0.0.1、
        REAL→FRP 反代 + connection_protocol），凭据经 Fernet 正确解密，
        连接/命令失败记入 error 字段（不再静默返回 0 异常）。

        Returns:
            dict with keys: device_name, device_ip, anomalies (count), events (list), [error]
        """
        device_name = device.get("device_name", "unknown")
        device_ip = device.get("device_ip", "unknown")
        dev_type = (device.get("device_type") or "MOCK").upper()
        events: list[dict] = []
        anomalies = 0
        errors: list[str] = []
        port_whitelist = INSPECTION_PORT_WHITELIST.get(dev_type)

        # 解析接入地址 + 凭据
        try:
            host, port, protocol, username, password = self._resolve_device_auth(device)
        except Exception as e:
            logger.warning(f"Connection resolve failed for {device_name}: {e}")
            return {
                "device_name": device_name,
                "device_ip": device_ip,
                "anomalies": 0,
                "events": [],
                "error": f"connection resolve failed: {e}",
            }

        from src.models.alert import DeviceAuth
        auth = DeviceAuth(
            username=username, password=password, port=port, protocol=protocol
        )

        try:
            from src.tools.switch_diag_tool import create_switch_diag_tool
            diag_tool = create_switch_diag_tool(use_mock=True, device_type=dev_type)
        except Exception as e:
            logger.warning(f"Cannot create diag tool: {e}")
            return {
                "device_name": device_name,
                "device_ip": device_ip,
                "anomalies": 0,
                "events": [],
                "error": str(e),
            }

        # 1. Check interface status
        try:
            status_result = diag_tool._run(host, "show interface status", auth)
            if status_result and status_result.success:
                for line in status_result.output.split("\n"):
                    if "down" in line.lower() or "notconnect" in line.lower():
                        parts = line.split()
                        if parts:
                            iface_name = parts[0]
                            # 白名单过滤：仅对关注端口上报，抑制未插线端口噪声
                            if port_whitelist is not None and iface_name not in port_whitelist:
                                continue
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
            else:
                msg = (getattr(status_result, "output", "") or "no output")[:200]
                errors.append(f"show interface status failed: {msg}")
        except Exception as e:
            logger.warning(f"Interface status check failed for {device_name}: {e}")
            errors.append(f"show interface status error: {e}")

        # 2. Check CPU utilization (REAL 使用 TL-SG5428 `show cpu-utilization`)
        cpu_cmd = "show cpu-utilization" if dev_type == "REAL" else "show processes cpu"
        try:
            cpu_result = diag_tool._run(host, cpu_cmd, auth)
            if cpu_result and cpu_result.success:
                cpu_percent = self._parse_cpu_percent(cpu_result.output, dev_type)
                if cpu_percent is None:
                    errors.append(f"{cpu_cmd}: could not parse CPU%")
                elif cpu_percent > CPU_THRESHOLD:
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
            else:
                msg = (getattr(cpu_result, "output", "") or "no output")[:200]
                errors.append(f"{cpu_cmd} failed: {msg}")
        except Exception as e:
            logger.warning(f"CPU check failed for {device_name}: {e}")
            errors.append(f"{cpu_cmd} error: {e}")

        result = {
            "device_name": device_name,
            "device_ip": device_ip,
            "anomalies": anomalies,
            "events": events,
        }
        if errors:
            result["error"] = "; ".join(errors)
        return result

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
    ) -> int | None:
        """Persist inspection result to SQLite InspectionRecord table.

        Returns:
            record_id (int) if successfully persisted, None on failure.
        """
        if not self._db_session:
            raise RuntimeError("No DB session available")

        from src.database.repositories.inspection_repository import InspectionRepository
        repo = InspectionRepository(self._db_session)
        record = repo.create_record({
            "trigger_mode": trigger_mode,
            "started_at": started_at,
            "completed_at": completed_at,
            "total_devices": total_devices,
            "anomaly_count": anomaly_count,
            "status": status,
            "details": details,
        })
        return record.id if record else None


    # ── [NEW] Alert creation from inspection events (ADR-001) ──────

    def _create_alert_from_event(
        self,
        event: dict,
        device: dict,
        trigger_mode: str,
    ) -> Optional[str]:
        """
        Create an Alert record from an inspection anomaly event.

        Args:
            event: dict from _inspect_device() with keys:
                alert_type, severity, content, [interface], [cpu_percent]
            device: device dict with device_name, device_ip, device_model
            trigger_mode: "SCHEDULED" or "MANUAL" (reserved for future use)

        Returns:
            alert_id (str) if created, None on failure.
        """
        import uuid
        from src.database.repositories.alert_repository import AlertRepository

        try:
            repo = AlertRepository(self._db_session)

            device_info: dict = {
                "device_name": device.get("device_name", "unknown"),
                "device_ip": device.get("device_ip", "unknown"),
                "device_model": device.get("device_model", ""),
                "device_type": device.get("device_type", "MOCK"),     # G3
                "simulator_port": device.get("simulator_port"),       # G3
            }

            if "interface" in event:
                device_info["interface_name"] = event["interface"]
            if "cpu_percent" in event:
                device_info["cpu_percent"] = event["cpu_percent"]

            alert_id = str(uuid.uuid4())
            repo.create_alert({
                "alert_id": alert_id,
                "alert_type": event["alert_type"],
                "severity": event["severity"],
                "content": event["content"],
                "device_info": device_info,
                "source": "INSPECTION",
            })

            logger.info(
                f"Alert created: {alert_id} "
                f"type={event['alert_type']} device={device.get('device_name')}"
            )
            return alert_id

        except Exception as e:
            logger.error(
                f"Failed to create alert for event on {device.get('device_name')}: {e}"
            )
            return None

    # ── [NEW] Link alerts to InspectionRecord (ADR-004) ────────────

    def _link_alerts_to_record(self, alert_ids: list[str], record_id: int) -> None:
        """
        Update Alert device_info JSON to include inspection_record_id.
        Uses SQLite json_set() for safe JSON mutation.
        """
        try:
            from sqlalchemy import text
            for alert_id in alert_ids:
                self._db_session.execute(
                    text(
                        "UPDATE alerts SET device_info = json_set("
                        "  COALESCE(device_info, '{}'), "
                        "  '$.inspection_record_id', :rid"
                        ") WHERE alert_id = :aid"
                    ),
                    {"rid": record_id, "aid": alert_id},
                )
            self._db_session.commit()
            logger.info(
                f"Linked {len(alert_ids)} alert(s) to InspectionRecord #{record_id}"
            )
        except Exception as e:
            logger.error(f"Failed to link alerts to InspectionRecord: {e}")
            try:
                self._db_session.rollback()
            except Exception:
                pass

    # ── [NEW] Batch workflow trigger via HTTP callback (ADR-002) ────

    def _trigger_workflows(
        self,
        alert_ids: list[str],
        record_id: int,
        web_port: int = 8001,
    ) -> bool:
        """
        POST alert_ids to web server for batch workflow triggering.

        Uses stdlib urllib.request — zero new dependencies.
        Timeout 5 seconds, non-fatal on failure (alerts already persisted).

        Returns:
            True on success, False on failure (non-fatal).
        """
        import json
        from urllib import request, error

        url = f"http://127.0.0.1:{web_port}/api/inspection/{record_id}/trigger-workflows"
        data = json.dumps({"alert_ids": alert_ids}).encode("utf-8")

        try:
            req = request.Request(
                url,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with request.urlopen(req, timeout=5) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                logger.info(
                    f"Workflow trigger callback: {body.get('triggered_count', 0)} triggered, "
                    f"{body.get('skipped_count', 0)} skipped"
                )
                return True
        except error.URLError as e:
            logger.warning(
                f"Workflow trigger callback failed (server unreachable): {e}. "
                f"{len(alert_ids)} alert(s) persisted but workflows not started."
            )
            return False
        except Exception as e:
            logger.warning(f"Workflow trigger callback failed: {e}")
            return False


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
    run_parser.add_argument('--trigger', choices=['scheduled', 'manual'], default='scheduled',
                            help='触发方式 (scheduled=定时巡检, manual=手动触发)')
    run_parser.set_defaults(func=_run_command)

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(CLIExitCode.FAILURE)

    args.func(args)


def _run_command(args):
    """Execute the 'run' command.

    v0.2.1: Passes --trigger value from CLI args to InspectionCLI.run().
    """
    cli = InspectionCLI()
    exit_code = cli.run(trigger_mode=args.trigger.upper())
    sys.exit(exit_code.value)


if __name__ == "__main__":
    main()
