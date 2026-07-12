"""
MOD-002: InspectionScheduler — Periodic inspection trigger via APScheduler.
@author sub_agent_software_developer
@module MOD-002
@implements IFC-002-01, IFC-002-02, IFC-002-03
@depends MOD-004 (AlertNormalizer), MOD-011 (SwitchDiagTool), MOD-016 (ConfigManager)
@covers REQ-FUNC-003
"""

from datetime import datetime, timezone
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from loguru import logger

from src.models.alert import DeviceInfo, RawInspectionEvent, DeviceAuth
from src.models.enums import AlertType, AlertSeverity
from src.orchestration.alert_normalizer import AlertNormalizer
from src.tools.switch_diag_tool import AbstractSwitchDiagTool
from src.security.config_manager import ConfigManager


class InspectionScheduler:
    """
    基于 APScheduler 的定时巡检调度器。

    IFC-002-01: start_scheduler(interval_minutes, device_list) → job_id
    IFC-002-02: stop_scheduler(job_id) → None
    IFC-002-03: run_inspection_once(device_list) → list[RawInspectionEvent]
    """

    def __init__(
        self,
        normalizer: AlertNormalizer,
        diag_tool: Optional[AbstractSwitchDiagTool] = None,
        config_manager: Optional[ConfigManager] = None,
    ):
        self.normalizer = normalizer
        self.diag_tool = diag_tool
        self.config_manager = config_manager or ConfigManager()
        self._scheduler: Optional[BackgroundScheduler] = None
        self._job_id: Optional[str] = None
        self._device_list: list[DeviceInfo] = []

    # ── IFC-002-01: start_scheduler ──────────────────────

    def start_scheduler(
        self, interval_minutes: int | None = None, device_list: list[DeviceInfo] | None = None
    ) -> str:
        """
        启动定时巡检任务。
        若 interval_minutes 为 None，从 ConfigManager 读取配置。
        """
        if interval_minutes is None:
            interval_minutes = self.config_manager.get("inspection.interval_minutes") or 5

        if device_list:
            self._device_list = device_list

        if self._scheduler is None:
            self._scheduler = BackgroundScheduler()
            self._scheduler.start()

        self._job_id = f"inspection_job_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"

        self._scheduler.add_job(
            func=lambda: self.run_inspection_once(self._device_list),
            trigger=IntervalTrigger(minutes=interval_minutes),
            id=self._job_id,
            name="Network Agent Periodic Inspection",
            replace_existing=True,
        )

        logger.info(f"InspectionScheduler started: interval={interval_minutes}min, job_id={self._job_id}")
        return self._job_id

    # ── IFC-002-02: stop_scheduler ───────────────────────

    def stop_scheduler(self, job_id: str | None = None) -> None:
        """停止定时巡检任务。"""
        target_id = job_id or self._job_id
        if self._scheduler and target_id:
            try:
                self._scheduler.remove_job(target_id)
                logger.info(f"InspectionScheduler stopped: job_id={target_id}")
            except Exception as e:
                logger.warning(f"Failed to stop scheduler job {target_id}: {e}")

        if self._scheduler:
            self._scheduler.shutdown(wait=False)
            self._scheduler = None

    # ── IFC-002-03: run_inspection_once ──────────────────

    def run_inspection_once(self, device_list: list[DeviceInfo] | None = None) -> list[RawInspectionEvent]:
        """
        手动触发一次巡检，对所有纳管设备执行健康检查。
        优先从 SQLite 读取设备列表，为空则用传入的 device_list。
        返回检测到的异常事件列表。
        """
        # Try to read devices from SQLite first
        effective_devices = device_list or []
        try:
            from src.database.base import SessionLocal
            from src.database.device_models import Device as DbDevice
            from sqlalchemy import select
            db = SessionLocal()
            try:
                db_devices = db.execute(select(DbDevice)).scalars().all()
                if db_devices:
                    effective_devices = [
                        DeviceInfo(
                            device_name=d.device_name,
                            device_ip=d.device_ip,
                            device_model=d.device_model,
                        )
                        for d in db_devices
                    ]
                    logger.info(f"Inspection using {len(effective_devices)} device(s) from database")
            finally:
                db.close()
        except Exception as e:
            logger.debug(f"Inspection DB device read skipped: {e}")

        if not effective_devices:
            logger.warning("No devices configured for inspection")
            return []

        events: list[RawInspectionEvent] = []
        logger.info(f"Inspection started for {len(effective_devices)} device(s)")

        for device in effective_devices:
            device_events = self._inspect_device(device)
            events.extend(device_events)

            # 将发现的异常事件归一化、持久化、触发工作流
            for event in device_events:
                alert = self.normalizer.normalize_inspection_event(event)
                if alert:
                    logger.info(
                        f"Inspection alert: {alert.alert_type} on "
                        f"{alert.device_info.device_name} (id={alert.alert_id})"
                    )
                    # Persist to SQLite
                    try:
                        from src.database.base import SessionLocal
                        from src.database.repositories.alert_repository import AlertRepository
                        db = SessionLocal()
                        try:
                            repo = AlertRepository(db)
                            repo.create_alert({
                                "alert_id": alert.alert_id,
                                "alert_type": str(alert.alert_type.value) if hasattr(alert.alert_type, 'value') else str(alert.alert_type),
                                "severity": str(alert.alert_severity.value) if hasattr(alert.alert_severity, 'value') else str(alert.alert_severity),
                                "content": alert.alert_content,
                                "device_info": alert.device_info.model_dump() if alert.device_info else {},
                                "source": str(alert.source.value) if hasattr(alert.source, 'value') else str(alert.source),
                            })
                        finally:
                            db.close()
                    except Exception as e:
                        logger.warning(f"Failed to persist inspection alert to DB: {e}")

        logger.info(f"Inspection complete: {len(events)} anomaly event(s) found")
        return events

    # ── 内部辅助 ──────────────────────────────────────────

    def _inspect_device(self, device: DeviceInfo) -> list[RawInspectionEvent]:
        """对单台设备执行诊断命令并检测异常。"""
        events: list[RawInspectionEvent] = []
        auth = self._get_auth(device)
        device_ip = device.device_ip

        # 检查接口状态
        if self.diag_tool:
            status_result = self.diag_tool._run(device_ip, "show interface status", auth)
            if status_result.success:
                # 检测 down 状态接口
                for line in status_result.output.split("\n"):
                    if "down" in line.lower() or "notconnect" in line.lower():
                        parts = line.split()
                        if parts:
                            iface_name = parts[0]
                            events.append(RawInspectionEvent(
                                device_info=DeviceInfo(
                                    device_name=device.device_name,
                                    device_ip=device.device_ip,
                                    device_model=device.device_model,
                                    interface_name=iface_name,
                                ),
                                alert_type=AlertType.PORT_DOWN,
                                alert_content=f"Interface {iface_name} is down on {device.device_name}",
                                alert_severity=AlertSeverity.MAJOR,
                            ))

            # 检查 CPU
            cpu_result = self.diag_tool._run(device_ip, "show processes cpu", auth)
            if cpu_result.success:
                import re
                cpu_match = re.search(r"CPU utilization.*?(\d+)%", cpu_result.output)
                if cpu_match:
                    cpu_percent = int(cpu_match.group(1))
                    if cpu_percent > 80:  # 阈值
                        events.append(RawInspectionEvent(
                            device_info=DeviceInfo(
                                device_name=device.device_name,
                                device_ip=device.device_ip,
                                cpu_percent=float(cpu_percent),
                            ),
                            alert_type=AlertType.CPU_HIGH,
                            alert_content=f"CPU utilization at {cpu_percent}% on {device.device_name}",
                            alert_severity=AlertSeverity.MAJOR,
                        ))

        return events

    def _get_auth(self, device: DeviceInfo) -> DeviceAuth:
        """获取设备认证凭据。"""
        creds = self.config_manager.get_device_credentials(device.device_name)
        if creds:
            return creds
        return DeviceAuth(username="admin", password="admin123")
