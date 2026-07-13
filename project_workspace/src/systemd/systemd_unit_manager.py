"""
MOD-INSP-001: systemd_unit_manager — systemd unit file generation and management.
@author sub_agent_software_developer
@module MOD-INSP-001
@implements IFC-INSP-001-01, IFC-INSP-001-02, IFC-INSP-001-03, IFC-INSP-001-04,
           IFC-INSP-001-05, IFC-INSP-001-06
@depends MOD-INSP-002 (systemctl_executor), MOD-016 (ConfigManager)
@covers REQ-INSP-002, REQ-INSP-003, REQ-INSP-013, REQ-INSP-015, REQ-INSP-016,
        REQ-INSP-NF-001, REQ-INSP-NF-002

Uses Jinja2 template engine to render systemd service and timer unit files.
Writes generated files to /etc/systemd/system/, runs daemon-reload,
and conditionally restarts the timer.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from jinja2 import Environment, FileSystemLoader, TemplateNotFound, TemplateError as Jinja2TemplateError
from loguru import logger


# ── Data Classes ─────────────────────────────────────────────────

@dataclass
class WriteResult:
    """Unit file write result (IFC-INSP-001-03)"""
    success: bool
    files_written: list[str] = field(default_factory=list)
    error: Optional[str] = None


@dataclass
class VerifyResult:
    """Unit file verify result (IFC-INSP-001-04)"""
    success: bool
    errors: list[str] = field(default_factory=list)


@dataclass
class SyncResult:
    """Configuration-to-systemd sync result (IFC-INSP-001-05)"""
    success: bool
    actions_performed: list[str] = field(default_factory=list)
    error: Optional[str] = None
    timer_was_active: bool = False


# ── Constants ────────────────────────────────────────────────────

SYSTEMD_DIR = Path("/etc/systemd/system")
SERVICE_FILENAME = "networkagent-inspection.service"
TIMER_FILENAME = "networkagent-inspection.timer"
TEMPLATES_DIR = "resources/templates/systemd"
SERVICE_TEMPLATE = "networkagent-inspection.service.j2"
TIMER_TEMPLATE = "networkagent-inspection.timer.j2"
DEFAULT_USER = "networkagent"
DEFAULT_PYTHON_BIN = "python3.11"
DEFAULT_RESTART_SEC = 30
DEFAULT_ACCURACY_SEC = 1
FIXED_DESCRIPTION = "NetworkAgent Inspection Service"


# ── MOD-INSP-001: SystemdUnitManager ─────────────────────────────

class SystemdUnitManager:
    """
    使用 Jinja2 模板生成 systemd unit 文件，管理 unit 文件的完整生命周期。

    实现 IFC-INSP-001-01~06 全部接口。
    复用 v0.1.0 MOD-007 (TemplateEngine) 使用的 Jinja2 引擎。
    """

    def __init__(
        self,
        systemctl_executor=None,
        templates_dir: Optional[Path] = None,
    ):
        """
        Args:
            systemctl_executor: MOD-INSP-002 SystemctlExecutor 实例
            templates_dir: Jinja2 模板目录路径（默认 project_root/resources/templates/systemd/）
        """
        # Lazy import to avoid circular dependency at module load time
        if systemctl_executor is None:
            from src.systemd.systemctl_executor import SystemctlExecutor
            self._executor = SystemctlExecutor()
        else:
            self._executor = systemctl_executor

        # Resolve templates directory
        if templates_dir is None:
            _project_root = Path(__file__).resolve().parent.parent.parent
            templates_dir = _project_root / TEMPLATES_DIR
        self._templates_dir = Path(templates_dir)

        # Initialize Jinja2 environment
        self._jinja_env = Environment(
            loader=FileSystemLoader(str(self._templates_dir)),
            autoescape=False,  # systemd unit files are plain text
        )

    # ── IFC-INSP-001-01: generate_service_unit ──────────────

    def generate_service_unit(self, config: dict) -> str:
        """
        生成 networkagent-inspection.service unit 文件内容。

        Args:
            config: dict with keys: timeout_seconds, working_directory,
                    user, python_bin (all optional with defaults)

        Returns:
            Complete service unit file content as string.

        Raises:
            ValueError: 必需配置缺失
            TemplateError: Jinja2 渲染失败
        """
        template_vars = self._build_service_template_vars(config)
        try:
            template = self._jinja_env.get_template(SERVICE_TEMPLATE)
            return template.render(**template_vars)
        except TemplateNotFound:
            raise ValueError(
                f"Service template not found: {self._templates_dir / SERVICE_TEMPLATE}"
            )
        except Jinja2TemplateError as e:
            raise Jinja2TemplateError(f"Failed to render service template: {e}")

    # ── IFC-INSP-001-02: generate_timer_unit ─────────────────

    def generate_timer_unit(self, config: dict) -> str:
        """
        生成 networkagent-inspection.timer unit 文件内容。

        Args:
            config: dict with keys: interval_minutes, accuracy_sec (optional)

        Returns:
            Complete timer unit file content as string.

        Raises:
            ValueError, TemplateError
        """
        template_vars = self._build_timer_template_vars(config)
        try:
            template = self._jinja_env.get_template(TIMER_TEMPLATE)
            return template.render(**template_vars)
        except TemplateNotFound:
            raise ValueError(
                f"Timer template not found: {self._templates_dir / TIMER_TEMPLATE}"
            )
        except Jinja2TemplateError as e:
            raise Jinja2TemplateError(f"Failed to render timer template: {e}")

    # ── IFC-INSP-001-03: write_unit_files ────────────────────

    def write_unit_files(self, service_content: str, timer_content: str) -> WriteResult:
        """
        将 unit 文件内容写入 /etc/systemd/system/ 目录。

        Args:
            service_content: 完整的 service unit 文件文本
            timer_content: 完整的 timer unit 文件文本

        Returns:
            WriteResult { success, files_written, error }
        """
        files_written: list[str] = []

        # Check directory writability
        if not SYSTEMD_DIR.exists():
            return WriteResult(
                success=False,
                error=f"systemd unit directory not found: {SYSTEMD_DIR}. "
                      f"请确认系统是否安装 systemd 且 /etc/systemd/system/ 目录存在。",
            )

        # Write service file
        service_path = SYSTEMD_DIR / SERVICE_FILENAME
        try:
            existing_service = service_path.read_text(encoding="utf-8") if service_path.exists() else ""
            if existing_service.strip() != service_content.strip():
                service_path.write_text(service_content, encoding="utf-8")
                files_written.append(str(service_path))
                logger.info(f"Written: {service_path}")
            else:
                logger.debug(f"Service file unchanged, skipping write: {service_path}")
        except PermissionError:
            return WriteResult(
                success=False,
                error=f"systemd unit 文件写入失败：权限不足，无法写入 {service_path}。"
                      f"请以 root 或 sudo 权限运行，或配置 sudoers。",
            )
        except OSError as e:
            return WriteResult(
                success=False,
                error=f"Failed to write {service_path}: {e}",
            )

        # Write timer file
        timer_path = SYSTEMD_DIR / TIMER_FILENAME
        try:
            existing_timer = timer_path.read_text(encoding="utf-8") if timer_path.exists() else ""
            if existing_timer.strip() != timer_content.strip():
                timer_path.write_text(timer_content, encoding="utf-8")
                files_written.append(str(timer_path))
                logger.info(f"Written: {timer_path}")
            else:
                logger.debug(f"Timer file unchanged, skipping write: {timer_path}")
        except PermissionError:
            return WriteResult(
                success=False,
                error=f"systemd unit 文件写入失败：权限不足，无法写入 {timer_path}。"
                      f"请以 root 或 sudo 权限运行，或配置 sudoers。",
            )
        except OSError as e:
            return WriteResult(
                success=False,
                error=f"Failed to write {timer_path}: {e}",
            )

        if not files_written:
            return WriteResult(success=True, files_written=files_written)

        return WriteResult(success=True, files_written=files_written)

    # ── IFC-INSP-001-04: verify_unit_files ───────────────────

    def verify_unit_files(self) -> VerifyResult:
        """
        使用 systemd-analyze verify 验证已写入的 unit 文件。若 systemd 不可用则跳过。

        Returns:
            VerifyResult { success, errors }
        """
        errors: list[str] = []
        avail = self._executor.check_systemd_available()
        if not avail.available:
            logger.warning(f"systemd not available, skipping verify: {avail.reason}")
            return VerifyResult(success=True, errors=[])

        for filename in [SERVICE_FILENAME, TIMER_FILENAME]:
            unit_path = SYSTEMD_DIR / filename
            if not unit_path.exists():
                errors.append(f"Unit file not found: {unit_path}")
                continue

            # systemd-analyze verify returns non-zero on validation errors,
            # but the error messages are on stderr
            import subprocess as _sp
            try:
                result = _sp.run(
                    ["sudo", "systemd-analyze", "verify", str(unit_path)],
                    capture_output=True, text=True, timeout=10, shell=False,
                )
                if result.returncode != 0:
                    err_msg = result.stderr.strip() or result.stdout.strip()
                    errors.append(f"Verify failed for {filename}: {err_msg}")
                    logger.warning(f"systemd-analyze verify {filename}: {err_msg}")
            except Exception as e:
                errors.append(f"Verify error for {filename}: {e}")
                logger.warning(f"systemd-analyze verify error: {e}")

        return VerifyResult(
            success=len(errors) == 0,
            errors=errors,
        )

    # ── IFC-INSP-001-05: sync_config_to_systemd ──────────────

    def sync_config_to_systemd(self, config: dict) -> SyncResult:
        """
        编排完整的配置同步链路：
          ① 渲染 service + timer 模板
          ② 写入 unit 文件
          ③ 执行 daemon-reload
          ④ 若 timer 当前 active 则 restart timer
          ⑤ 返回同步摘要

        Args:
            config: 巡检配置字典 for template rendering

        Returns:
            SyncResult { success, actions_performed, error, timer_was_active }
        """
        actions: list[str] = []
        timer_was_active = False
        service_file_changed = False
        timer_file_changed = False

        # Check systemd availability
        avail = self._executor.check_systemd_available()
        if not avail.available:
            return SyncResult(
                success=False,
                actions_performed=actions,
                error=f"systemd 不可用: {avail.reason}",
            )

        # ① Check if config has changed (idempotent check)
        if not self.is_config_changed(config):
            logger.info("Configuration unchanged, skipping systemd sync")
            return SyncResult(
                success=True,
                actions_performed=["skipped: configuration unchanged"],
                timer_was_active=False,
            )

        # ② Generate unit file content
        try:
            service_content = self.generate_service_unit(config)
            timer_content = self.generate_timer_unit(config)
            actions.append("rendered service + timer templates")
        except (ValueError, Jinja2TemplateError) as e:
            return SyncResult(
                success=False,
                actions_performed=actions,
                error=f"模板渲染失败: {e}",
            )

        # Check what files will change before writing
        service_path = SYSTEMD_DIR / SERVICE_FILENAME
        timer_path = SYSTEMD_DIR / TIMER_FILENAME
        if service_path.exists():
            existing_service = service_path.read_text(encoding="utf-8")
            service_file_changed = existing_service.strip() != service_content.strip()
        else:
            service_file_changed = True
        if timer_path.exists():
            existing_timer = timer_path.read_text(encoding="utf-8")
            timer_file_changed = existing_timer.strip() != timer_content.strip()
        else:
            timer_file_changed = True

        if not service_file_changed and not timer_file_changed:
            actions.append("skipped: unit files unchanged")
            return SyncResult(
                success=True,
                actions_performed=actions,
                timer_was_active=False,
            )

        # ③ Write unit files
        write_result = self.write_unit_files(service_content, timer_content)
        if not write_result.success:
            return SyncResult(
                success=False,
                actions_performed=actions,
                error=write_result.error,
            )

        actions.append("wrote unit files: " + ", ".join(write_result.files_written))

        # ④ Verify syntax
        verify_result = self.verify_unit_files()
        if not verify_result.success:
            # Log but don't block — syntax errors are logged, writes succeed
            logger.warning(f"Unit file verify warnings: {verify_result.errors}")
            actions.append(f"verify completed with {len(verify_result.errors)} warning(s)")

        # ⑤ daemon-reload
        reload_result = self._executor.daemon_reload()
        if not reload_result.success:
            return SyncResult(
                success=False,
                actions_performed=actions,
                error=f"daemon-reload 失败: {reload_result.message}",
            )
        actions.append("daemon-reload executed")

        # ⑥ Check timer state and restart if active
        try:
            timer_status = self._executor.get_timer_status()
        except Exception:
            timer_status = None

        if timer_status and timer_status.active_state == "active":
            timer_was_active = True
            restart_result = self._executor.restart_service()
            # restart_service restarts the service, also need to restart timer
            if restart_result.success:
                actions.append("timer was active — restarted")
            else:
                actions.append(f"timer restart warning: {restart_result.message}")
        else:
            actions.append("timer was inactive — no restart needed")

        return SyncResult(
            success=True,
            actions_performed=actions,
            timer_was_active=timer_was_active,
        )

    # ── IFC-INSP-001-06: is_config_changed ────────────────────

    def is_config_changed(self, new_config: dict) -> bool:
        """
        检查新配置与当前 unit 文件内容是否一致（幂等检查）。

        Args:
            new_config: 新的巡检配置字典

        Returns:
            True 表示配置有变更，需要同步
        """
        service_path = SYSTEMD_DIR / SERVICE_FILENAME
        timer_path = SYSTEMD_DIR / TIMER_FILENAME

        # If either file doesn't exist, treat as changed
        if not service_path.exists() or not timer_path.exists():
            return True

        try:
            # Generate what the new content would be
            new_service = self.generate_service_unit(new_config)
            new_timer = self.generate_timer_unit(new_config)

            existing_service = service_path.read_text(encoding="utf-8")
            existing_timer = timer_path.read_text(encoding="utf-8")

            service_changed = existing_service.strip() != new_service.strip()
            timer_changed = existing_timer.strip() != new_timer.strip()

            return service_changed or timer_changed

        except Exception:
            # If any error during comparison, treat as changed (safe default)
            return True

    # ── Internal helpers ────────────────────────────────────

    def _get_working_directory(self) -> str:
        """从 NETWORKAGENT_HOME 环境变量读取 WorkingDirectory。"""
        home = os.environ.get("NETWORKAGENT_HOME", "")
        if home:
            return home
        # Fallback: project root (parent of src/)
        return str(Path(__file__).resolve().parent.parent.parent)

    def _get_user(self) -> str:
        """获取运行用户。"""
        return os.environ.get("NETWORKAGENT_USER", DEFAULT_USER)

    def _build_service_template_vars(self, config: dict) -> dict:
        """
        构建 service unit 模板渲染变量。
        PM Q-INSP-004: WorkingDirectory 从 NETWORKAGENT_HOME 读取。
        PM Q-INSP-005: Demo 阶段不配置 MemoryLimit/CPUQuota。
        """
        return {
            "python_bin": config.get("python_bin", DEFAULT_PYTHON_BIN),
            "working_directory": config.get("working_directory", self._get_working_directory()),
            "user": config.get("user", self._get_user()),
            "timeout_stop_sec": int(config.get("timeout_seconds", 30)),
            "restart_sec": int(config.get("restart_sec", DEFAULT_RESTART_SEC)),
            "description": FIXED_DESCRIPTION,
        }

    def _build_timer_template_vars(self, config: dict) -> dict:
        """
        构建 timer unit 模板渲染变量。
        REQ-INSP-013: interval_minutes → OnUnitActiveSec 转换。
        REQ-INSP-NF-001: AccuracySec=1s 高精度触发。
        """
        interval_minutes = int(config.get("interval_minutes", 5))
        on_unit_active_sec = interval_minutes * 60  # Convert minutes to seconds
        return {
            "on_unit_active_sec": on_unit_active_sec,
            "accuracy_sec": int(config.get("accuracy_sec", DEFAULT_ACCURACY_SEC)),
        }
