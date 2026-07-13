"""
MOD-010: SwitchConfigTool — Configuration command execution on network switches.
@author sub_agent_software_developer
@module MOD-010
@implements IFC-010-01
@depends None
@covers REQ-FUNC-014, REQ-FUNC-017, REQ-NFUNC-014

Strategy Pattern: AbstractSwitchConfigTool (ABC) → MockSwitchConfigTool | TpLinkSwitchConfigTool (reserved)
"""

import time
from abc import ABC, abstractmethod
from typing import Any, Optional, Type

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
    ) -> ConfigResult:
        commands_executed = 0
        output_lines: list[str] = []

        for cmd in commands:
            logger.info(f"[MockConfig] {device_ip}: executing '{cmd}'")
            time.sleep(0.5)  # 模拟网络延迟

            output_lines.append(f"{device_ip}# {cmd}")
            output_lines.append(f"[OK] Command executed successfully")
            commands_executed += 1

            # 模拟 ssh 命令执行结果
            if "interface" in cmd.lower():
                output_lines.append(f"Entering interface configuration mode...")
            elif "no shutdown" in cmd.lower():
                output_lines.append(f"Interface enabled")
            elif "shutdown" in cmd.lower():
                output_lines.append(f"Interface disabled")
            elif "switchport" in cmd.lower():
                output_lines.append(f"Switchport configuration applied")
            elif "description" in cmd.lower():
                output_lines.append(f"Description updated")
            elif "router" in cmd.lower():
                output_lines.append(f"Routing configuration applied")

        return ConfigResult(
            success=True,
            output="\n".join(output_lines),
            commands_executed=commands_executed,
            commands_failed=0,
        )


# ────────────────────────────────────────────────────
# TP-Link Implementation (Reserved)
# ────────────────────────────────────────────────────

class TpLinkSwitchConfigTool(AbstractSwitchConfigTool):
    """
    TP-Link 真实实现（预留）。
    Demo 阶段不实现真实 SSH 调用，_run() 抛出 NotImplementedError。
    """

    name: str = "switch_config_tplink"
    description: str = "Execute configuration commands on TP-Link switch via SSH (Reserved)"

    def _run(
        self,
        device_ip: str,
        commands: list[str],
        auth: DeviceAuth,
    ) -> ConfigResult:
        """
        [RESERVED] 后续阶段启用 TP-Link 真实 SSH 配置下发。
        使用 Netmiko + NAPALM:
          - Netmiko: SSH 连接 + 命令执行
          - NAPALM: merge/commit/discard 配置会话
        """
        raise NotImplementedError(
            "TpLinkSwitchConfigTool is reserved for future TP-Link integration. "
            "Use MockSwitchConfigTool for Demo phase."
        )


# ────────────────────────────────────────────────────
# Factory
# ────────────────────────────────────────────────────

def create_switch_config_tool(use_mock: bool = True) -> AbstractSwitchConfigTool:
    """工厂函数：根据配置创建 Mock 或 TP-Link 实现。"""
    if use_mock:
        return MockSwitchConfigTool()
    else:
        return TpLinkSwitchConfigTool()
