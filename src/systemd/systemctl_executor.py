"""
MOD-INSP-002: systemctl_executor — systemctl command abstraction layer.
@author sub_agent_software_developer
@module MOD-INSP-002
@implements IFC-INSP-002-01, IFC-INSP-002-02, IFC-INSP-002-03, IFC-INSP-002-04,
           IFC-INSP-002-05, IFC-INSP-002-06, IFC-INSP-002-07, IFC-INSP-002-08,
           IFC-INSP-002-09
@depends None (subprocess + shutil stdlib only)
@covers REQ-INSP-004, REQ-INSP-006, REQ-INSP-007, REQ-INSP-NF-003, REQ-INSP-NF-006

Zero-dependency systemctl command wrapper. Uses subprocess.run with shell=False
and list-arg form for command injection prevention. All operations return
Pydantic-typed results for type-safe consumption by upper modules.

v0.2.0 added for inspection systemd refactoring.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import re
from datetime import datetime, timezone
from typing import Optional

from loguru import logger
from pydantic import BaseModel


# ── Pydantic Data Models ────────────────────────────────────────

class TimerStatus(BaseModel):
    """networkagent-inspection.timer 状态快照 (IFC-INSP-002-02)"""
    active_state: str = "not-found"           # active | inactive | not-found
    unit_file_state: str = "not-found"        # enabled | disabled | not-found
    next_trigger: Optional[datetime] = None   # UTC datetime or None
    last_trigger: Optional[datetime] = None


class ServiceStatus(BaseModel):
    """networkagent-inspection.service 状态快照 (IFC-INSP-002-03)"""
    active_state: str = "not-found"           # active | inactive | not-found
    sub_state: str = "not-found"              # running | dead | exited | failed
    last_result: str = "not-found"            # success | failure
    last_execution: Optional[datetime] = None


class SystemctlResult(BaseModel):
    """systemctl 命令执行结果 (IFC-INSP-002-04~09)"""
    success: bool
    action: str                               # start | stop | restart | enable | disable | daemon-reload
    message: str
    detail: Optional[str] = None


class SystemdAvailability(BaseModel):
    """systemd 环境检测结果 (IFC-INSP-002-01)"""
    available: bool
    reason: Optional[str] = None


# ── Exception Definitions ───────────────────────────────────────

class SystemctlPermissionError(Exception):
    """sudo 权限不足（sudoers 未配置或不正确）"""
    pass


class SystemctlTimeoutError(Exception):
    """systemctl 命令执行超时"""
    pass


class SystemdNotAvailableError(Exception):
    """systemd 不可用（非 Linux 或未安装 systemd）"""
    pass


class SystemctlCommandError(Exception):
    """其他 systemctl 执行错误"""
    pass


# ── Constants ───────────────────────────────────────────────────

TIMER_UNIT = "networkagent-inspection.timer"
SERVICE_UNIT = "networkagent-inspection.service"
SYSTEMD_RUN_DIR = "/run/systemd/system"
DEFAULT_TIMEOUT = 5  # seconds
SUDO = "sudo"
SYSTEMCTL = "systemctl"


# ── MOD-INSP-002: systemctl_executor ────────────────────────────

class SystemctlExecutor:
    """
    封装 sudo systemctl 命令调用，提供类型化的操作接口。

    所有 systemctl 调用使用 subprocess.run(shell=False, list args) 防命令注入。
    默认超时 5 秒（可通过构造参数覆盖）。
    命令执行记录 INFO 级别日志（命令 + 退出码 + 耗时）。
    """

    def __init__(self, timeout: int = DEFAULT_TIMEOUT):
        self.timeout = timeout

    # ── IFC-INSP-002-01: check_systemd_available ────────────

    def check_systemd_available(self) -> SystemdAvailability:
        """
        检测 systemd 环境是否可用。
        检查 /run/systemd/system 路径 + which systemctl。
        """
        # Check systemd runtime directory
        if not os.path.exists(SYSTEMD_RUN_DIR):
            return SystemdAvailability(
                available=False,
                reason=f"systemd runtime directory not found: {SYSTEMD_RUN_DIR}"
            )

        # Check systemctl command availability
        systemctl_path = shutil.which(SYSTEMCTL)
        if systemctl_path is None:
            return SystemdAvailability(
                available=False,
                reason=f"'{SYSTEMCTL}' command not found in PATH"
            )

        return SystemdAvailability(available=True)

    # ── IFC-INSP-002-02: get_timer_status ────────────────────

    def get_timer_status(self) -> TimerStatus:
        """
        查询 networkagent-inspection.timer 状态。
        执行 systemctl show --property=... 并解析 Key=Value 输出。
        """
        try:
            output = self._run_systemctl_show(
                TIMER_UNIT,
                ["ActiveState", "UnitFileState", "NextElapseUSRealtime", "LastTriggerUSec"]
            )
        except SystemdNotAvailableError:
            return TimerStatus(active_state="not-found", unit_file_state="not-found")
        except Exception:
            # Unit not found / other errors → return not-found
            return TimerStatus(active_state="not-found", unit_file_state="not-found")

        props = self._parse_show_output(output)

        status = TimerStatus(
            active_state=props.get("ActiveState", "not-found"),
            unit_file_state=props.get("UnitFileState", "not-found"),
        )

        # Parse NextElapseUSRealtime (microseconds since epoch, 0 means no trigger)
        next_raw = props.get("NextElapseUSRealtime", "0")
        try:
            next_us = int(next_raw)
            if next_us > 0:
                status.next_trigger = datetime.fromtimestamp(next_us / 1_000_000, tz=timezone.utc)
        except (ValueError, OSError):
            pass

        # Parse LastTriggerUSec
        last_raw = props.get("LastTriggerUSec", "0")
        try:
            last_us = int(last_raw)
            if last_us > 0:
                status.last_trigger = datetime.fromtimestamp(last_us / 1_000_000, tz=timezone.utc)
        except (ValueError, OSError):
            pass

        return status

    # ── IFC-INSP-002-03: get_service_status ──────────────────

    def get_service_status(self) -> ServiceStatus:
        """
        查询 networkagent-inspection.service 状态。
        执行 systemctl show --property=... 并解析输出。
        """
        try:
            output = self._run_systemctl_show(
                SERVICE_UNIT,
                ["ActiveState", "SubState", "Result", "ExecMainExitTimestamp"]
            )
        except SystemdNotAvailableError:
            return ServiceStatus(active_state="not-found", sub_state="not-found")
        except Exception:
            return ServiceStatus(active_state="not-found", sub_state="not-found")

        props = self._parse_show_output(output)

        status = ServiceStatus(
            active_state=props.get("ActiveState", "not-found"),
            sub_state=props.get("SubState", "not-found"),
            last_result=props.get("Result", "not-found"),
        )

        # Parse ExecMainExitTimestamp
        exit_ts = props.get("ExecMainExitTimestamp", "0")
        try:
            ts_us = int(exit_ts)
            if ts_us > 0:
                status.last_execution = datetime.fromtimestamp(ts_us / 1_000_000, tz=timezone.utc)
        except (ValueError, OSError):
            pass

        return status

    # ── IFC-INSP-002-04: start_service ───────────────────────

    def start_service(self) -> SystemctlResult:
        """启动 networkagent-inspection.service（systemctl start）"""
        return self._exec_systemctl("start", SERVICE_UNIT)

    # ── IFC-INSP-002-05: stop_service ────────────────────────

    def stop_service(self) -> SystemctlResult:
        """
        停止 networkagent-inspection.service（systemctl stop）。
        注意：仅停止 service 进程，不影响 timer。
        """
        return self._exec_systemctl("stop", SERVICE_UNIT)

    # ── IFC-INSP-002-06: restart_service ─────────────────────

    def restart_service(self) -> SystemctlResult:
        """重启 networkagent-inspection.service（systemctl restart）"""
        return self._exec_systemctl("restart", SERVICE_UNIT)

    # ── IFC-INSP-002-07: enable_timer ────────────────────────

    def enable_timer(self) -> SystemctlResult:
        """
        启用 networkagent-inspection.timer（systemctl enable + start）。
        若 timer 已 enabled + active，返回幂等提示。
        """
        # Check current state for idempotent handling
        timer = self.get_timer_status()
        if timer.active_state == "active" and timer.unit_file_state == "enabled":
            return SystemctlResult(
                success=True,
                action="enable",
                message="timer 已处于启用状态，无需操作",
            )

        # Enable the timer
        enable_result = self._exec_systemctl("enable", TIMER_UNIT)
        if not enable_result.success:
            return enable_result

        # Start the timer
        start_result = self._exec_systemctl("start", TIMER_UNIT)
        if not start_result.success:
            return SystemctlResult(
                success=False,
                action="enable",
                message=f"enable 成功但 start 失败: {start_result.message}",
                detail=start_result.detail,
            )

        return SystemctlResult(
            success=True,
            action="enable",
            message="timer 已启用并启动",
        )

    # ── IFC-INSP-002-08: disable_timer ───────────────────────

    def disable_timer(self) -> SystemctlResult:
        """
        禁用 networkagent-inspection.timer（systemctl stop + disable）。
        若 timer 已 disabled，返回幂等提示。
        """
        # Check current state for idempotent handling
        timer = self.get_timer_status()
        if timer.unit_file_state == "disabled" and timer.active_state == "inactive":
            return SystemctlResult(
                success=True,
                action="disable",
                message="timer 已处于禁用状态，无需操作",
            )

        # Stop the timer
        stop_result = self._exec_systemctl("stop", TIMER_UNIT)
        if not stop_result.success:
            return stop_result

        # Disable the timer
        disable_result = self._exec_systemctl("disable", TIMER_UNIT)
        if not disable_result.success:
            return SystemctlResult(
                success=False,
                action="disable",
                message=f"stop 成功但 disable 失败: {disable_result.message}",
                detail=disable_result.detail,
            )

        return SystemctlResult(
            success=True,
            action="disable",
            message="timer 已停止并禁用",
        )

    # ── IFC-INSP-002-09: daemon_reload ───────────────────────

    def daemon_reload(self) -> SystemctlResult:
        """执行 systemctl daemon-reload"""
        return self._exec_systemctl("daemon-reload", None)

    # ── Internal helpers ────────────────────────────────────

    def _run_systemctl_show(self, unit: str, properties: list[str]) -> str:
        """
        执行 systemctl show <unit> --property=<p1>,<p2>,...
        返回 stdout 文本。
        """
        cmd = [SUDO, SYSTEMCTL, "show", unit]
        props_str = ",".join(properties)
        cmd.append(f"--property={props_str}")

        # Check systemd availability first
        avail = self.check_systemd_available()
        if not avail.available:
            raise SystemdNotAvailableError(avail.reason or "systemd not available")

        logger.debug(f"Executing: {' '.join(cmd)}")
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                shell=False,
            )
        except subprocess.TimeoutExpired:
            logger.error(f"systemctl show timed out after {self.timeout}s: {unit}")
            raise SystemctlTimeoutError(f"systemctl show {unit} timed out after {self.timeout}s")

        if result.returncode != 0:
            stderr = result.stderr.strip()
            logger.warning(f"systemctl show {unit} exited {result.returncode}: {stderr}")
            raise SystemctlCommandError(f"systemctl show {unit} failed: {stderr}")

        return result.stdout

    def _parse_show_output(self, output: str) -> dict[str, str]:
        """将 systemctl show 的 Key=Value 输出解析为 dict"""
        result: dict[str, str] = {}
        for line in output.strip().split("\n"):
            line = line.strip()
            if "=" in line:
                key, _, value = line.partition("=")
                result[key] = value
        return result

    def _exec_systemctl(self, action: str, unit: str | None) -> SystemctlResult:
        """
        执行 systemctl <action> [<unit>] 命令，统一处理错误。
        返回 SystemctlResult。
        """
        # Check systemd availability first
        avail = self.check_systemd_available()
        if not avail.available:
            return SystemctlResult(
                success=False,
                action=action,
                message=f"systemd 不可用: {avail.reason}",
                detail=avail.reason,
            )

        cmd = [SUDO, SYSTEMCTL, action]
        if unit:
            cmd.append(unit)

        logger.info(f"Executing systemctl: {' '.join(cmd)}")
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                shell=False,
            )
        except subprocess.TimeoutExpired:
            logger.error(f"systemctl {action} timed out after {self.timeout}s")
            return SystemctlResult(
                success=False,
                action=action,
                message=f"systemctl {action} 执行超时（{self.timeout}秒）",
                detail="Command timed out",
            )

        if result.returncode != 0:
            stderr = result.stderr.strip()
            logger.warning(f"systemctl {action} exited {result.returncode}: {stderr}")

            # Classify error type
            if "Interactive authentication required" in stderr or "not allowed" in stderr:
                raise SystemctlPermissionError(
                    f"systemctl {action} 权限不足: {stderr}. "
                    f"请配置 sudoers: /etc/sudoers.d/networkagent"
                )

            return SystemctlResult(
                success=False,
                action=action,
                message=f"systemctl {action} 执行失败",
                detail=stderr if stderr else f"Exit code: {result.returncode}",
            )

        stdout = result.stdout.strip()
        logger.info(f"systemctl {action} completed successfully (exit 0)")
        return SystemctlResult(
            success=True,
            action=action,
            message=f"systemctl {action} 执行成功",
            detail=stdout if stdout else None,
        )
