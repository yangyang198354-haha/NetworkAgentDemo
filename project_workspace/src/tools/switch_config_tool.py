"""
MOD-010: SwitchConfigTool — Configuration command execution on network switches.
@author sub_agent_software_developer
@module MOD-010
@implements IFC-010-01
@depends None
@covers REQ-FUNC-014, REQ-FUNC-017, REQ-NFUNC-014, REAL-DEVICE-004

Strategy Pattern: AbstractSwitchConfigTool (ABC)
  → MockSwitchConfigTool | TpLinkSwitchConfigTool (REAL/SSH + Simulator delegated)
"""

import time
from abc import ABC, abstractmethod
from typing import Any, Optional

from langchain_core.tools import BaseTool
from loguru import logger

from src.models.alert import DeviceAuth
from src.models.fix_plan import ConfigResult


# ────────────────────────────────────────────────────
# Abstract Base Class
# ────────────────────────────────────────────────────

class AbstractSwitchConfigTool(BaseTool, ABC):
    """
    交换机配置下发工具抽象基类。
    IFC-010-01: configure(device_ip, commands, auth) → ConfigResult
    """

    name: str = "switch_config"
    description: str = "Execute configuration commands on network switch"

    @abstractmethod
    def _run(
        self,
        device_ip: str,
        commands: list[str],
        auth: DeviceAuth,
    ) -> ConfigResult:
        """Execute configuration commands and return result."""

    # LangChain BaseTool 兼容入口
    def _to_args_and_kwargs(self, *args: Any, **kwargs: Any) -> tuple[tuple, dict]:
        return args, kwargs

    def run(
        self,
        tool_input: str = "",
        device_ip: str = "",
        commands: Optional[list[str]] = None,
        auth: Optional[DeviceAuth] = None,
        **kwargs: Any,
    ) -> str:
        """LangChain Tool 统一入口（将 dict 参数转换为工具调用）。"""
        if commands is None:
            commands = []
        if auth is None:
            auth = DeviceAuth(username="admin", password="")
        result = self._run(device_ip, commands, auth)
        return str(result.model_dump())


# ────────────────────────────────────────────────────
# Mock Implementation (Demo)
# ────────────────────────────────────────────────────

class MockSwitchConfigTool(AbstractSwitchConfigTool):
    """
    Mock 实现 — 不真实连接交换机，所有命令返回 success=true。
    模拟延迟 0.5s/条命令。
    """

    name: str = "switch_config"
    description: str = "Execute configuration commands on network switch (Mock)"

    def _run(
        self,
        device_ip: str,
        commands: list[str],
        auth: DeviceAuth,
        alert_id: str = "",
    ) -> ConfigResult:
        commands_executed = 0
        output_lines: list[str] = []

        for cmd in commands:
            logger.info(f"[MockConfig] {device_ip}: executing '{cmd}'")
            time.sleep(0.5)  # 模拟网络延迟

            output_lines.append(f"{device_ip}# {cmd}")
            output_lines.append(f"[OK] Command executed successfully")
            commands_executed += 1

            if "interface" in cmd.lower():
                output_lines.append("Entering interface configuration mode...")
            elif "no shutdown" in cmd.lower():
                output_lines.append("Interface enabled")
            elif "shutdown" in cmd.lower():
                output_lines.append("Interface disabled")
            elif "switchport" in cmd.lower():
                output_lines.append("Switchport configuration applied")
            elif "description" in cmd.lower():
                output_lines.append("Description updated")
            elif "router" in cmd.lower():
                output_lines.append("Routing configuration applied")

        return ConfigResult(
            success=True,
            output="\n".join(output_lines),
            commands_executed=commands_executed,
            commands_failed=0,
        )


# ────────────────────────────────────────────────────
# TP-Link Real SSH Implementation (REAL-DEVICE-004)
# ────────────────────────────────────────────────────

class TpLinkSwitchConfigTool(AbstractSwitchConfigTool):
    """
    TP-Link 真实设备配置工具（基于 paramiko SSH / telnetlib TELNET）。

    Supports:
      - Enter config mode, run ordered list of commands, exit, save.
      - Auto-detect connection protocol via Device.connection_protocol; if
        the caller only passes plain `device_ip` without a device object we
        default to SSH.
    """

    name: str = "switch_config_tplink"
    description: str = (
        "Execute configuration commands on a real TP-Link switch via SSH or "
        "Telnet (REAL-DEVICE-004). Supports FRP-mapped host/ports by passing "
        "auth.port override or device.frp_proxy_* through session factory."
    )

    def _run(
        self,
        device_ip: str,
        commands: list[str],
        auth: DeviceAuth,
    ) -> ConfigResult:
        from src.tools.real_device_client import (
            DeviceToolSession,
            _SshSession,
            _TelnetSession,
        )
        from src.tools.real_session_gate import session_guard_by_access

        if not commands:
            return ConfigResult(success=True, output="(no commands provided)",
                                commands_executed=0, commands_failed=0)

        start = time.perf_counter()
        port = int(getattr(auth, "port", None) or auth.ssh_port or 22)
        protocol = (getattr(auth, "protocol", None) or "SSH").upper()
        username = auth.username or "admin"
        password = auth.password or ""
        logger.info(f"[TpLinkConfig] {device_ip}:{port} proto={protocol} cmds={len(commands)}")

        # NFUNC-004: 工作流配置会话与面板/连通性/写操作串行化（仅包裹门，不改会话逻辑）
        with session_guard_by_access(device_ip, port, protocol):
            try:
                if protocol == "SSH":
                    sess = _SshSession(device_ip, port, username, password).open()
                elif protocol == "TELNET":
                    sess = _TelnetSession(device_ip, port, username, password).open()
                else:
                    raise ValueError(f"Unsupported protocol {protocol}")
            except Exception as e:
                logger.exception(f"[TpLinkConfig] connect failed")
                return ConfigResult(
                    success=False,
                    output=f"Connect failed ({protocol} {device_ip}:{port}): {e.__class__.__name__}: {e}",
                    commands_executed=0,
                    commands_failed=len(commands),
                )

            try:
                executed, failed, output = sess.configure(commands)
            finally:
                try:
                    sess.close()
                except Exception:
                    pass

        elapsed = int((time.perf_counter() - start) * 1000)
        success = (failed == 0) and (executed > 0 or len(commands) == 0)
        logger.info(f"[TpLinkConfig] done ok={success} exec={executed} fail={failed} {elapsed}ms")
        return ConfigResult(
            success=success,
            output=output,
            commands_executed=executed,
            commands_failed=failed,
        )

    def run_records(self, device_ip: str, commands: list[str],
                    auth: DeviceAuth, save: bool = False) -> list[dict]:
        """单会话批量下发并返回逐命令结果（interface + shutdown 需同会话）。

        返回形如 [{"command","success","output","error"}] 的列表，供 execute_fix
        构造逐命令 exec_log。区别于 `_run`（返回 ConfigResult 汇总）。

        save=True 时，在 configure_records 退出 config 模式后，于 enable 模式追加
        一次 `copy running-config startup-config` 持久化（用户已授权「允许 save」），
        并在结果列表末尾追加 {"command":"save", ...} 记录。
        """
        from src.tools.real_device_client import _SshSession, _TelnetSession
        from src.tools.real_session_gate import session_guard_by_access

        if not commands:
            return []

        port = int(getattr(auth, "port", None) or auth.ssh_port or 22)
        protocol = (getattr(auth, "protocol", None) or "SSH").upper()
        username = auth.username or "admin"
        password = auth.password or ""

        with session_guard_by_access(device_ip, port, protocol):
            try:
                if protocol == "SSH":
                    sess = _SshSession(device_ip, port, username, password).open()
                elif protocol == "TELNET":
                    sess = _TelnetSession(device_ip, port, username, password).open()
                else:
                    raise ValueError(f"Unsupported protocol {protocol}")
            except Exception as e:
                logger.exception(f"[TpLinkConfig] connect failed")
                return [{
                    "command": c,
                    "success": False,
                    "output": "",
                    "error": f"Connect failed ({protocol} {device_ip}:{port}): {e.__class__.__name__}: {e}",
                } for c in commands]

            try:
                records = sess.configure_records(commands)
                if save:
                    ok, out = sess.save()
                    records.append({
                        "command": "save",
                        "success": ok,
                        "output": out,
                        "error": None,
                    })
                return records
            finally:
                try:
                    sess.close()
                except Exception:
                    pass


# ────────────────────────────────────────────────────
# Factory
# ────────────────────────────────────────────────────

def create_switch_config_tool(
    use_mock: bool = True,
    device_type: str = "MOCK",
) -> AbstractSwitchConfigTool:
    """
    工厂函数：根据 device_type 创建对应的配置工具实现。

    Args:
        use_mock: [DEPRECATED] 保留向后兼容，优先使用 device_type
        device_type: MOCK → MockSwitchConfigTool
                     SIMULATOR → SimulatorConfigTool
                     REAL → TpLinkSwitchConfigTool (真实 SSH/Telnet)

    REAL-DEVICE-004: 工具工厂策略扩展 — 新增 REAL 分支。
    """
    dt = (device_type or "").upper()
    if dt == "SIMULATOR":
        from src.tools.simulator_config_tool import SimulatorConfigTool
        return SimulatorConfigTool()
    if dt == "REAL":
        return TpLinkSwitchConfigTool()
    if not use_mock:
        return TpLinkSwitchConfigTool()
    return MockSwitchConfigTool()
