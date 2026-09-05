"""
MOD-RP-002: REAL 面板采集服务（单会话批量采集 + 端口写操作编排）。
@author sub_agent_software_developer
@module MOD-RP-002
@implements IFC-RP-002-01, IFC-RP-002-02
@depends MOD-RP-003, MOD-RP-004, src.tools.real_device_client.DeviceToolSession
@covers REQ-RP-FUNC-002/003/004/005/006/007/010, REQ-RP-NFUNC-004

单会话内依次下发多条 show 命令（避免多次会话建立），会话在
`with DeviceToolSession(...)` 内建立、`__exit__` 保证 finally 关闭，
外层套 `session_guard` 串行化门。写操作复用 `configure()`，绝不调用 save()
（DeviceToolSession 未暴露 save()，结构上保证 AC-RP-005-03）。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from loguru import logger

from src.tools.real_device_client import (
    DeviceToolSession,
    _looks_like_error,
    _strip_echo_and_prompts,
)
from src.tools.real_panel_parsers import (
    RealPanelError,
    parse_interface_status,
    parse_cpu_utilization,
    parse_memory_utilization,
    parse_io_rates,
    parse_system_info,
)
from src.tools.real_session_gate import session_guard


@dataclass
class PortWriteResult:
    success: bool
    message: str
    output: str


_ACTION_MAP = {
    "shutdown": "shutdown",
    "no-shutdown": "no shutdown",
    "no_shutdown": "no shutdown",
}


def _map_action(action: str) -> str:
    cli = _ACTION_MAP.get((action or "").strip().lower())
    if cli is None:
        raise ValueError(f"不支持的端口动作: {action!r}（仅支持 shutdown / no-shutdown）")
    return cli


def _run_show(sess, command: str, section: str) -> str:
    """单条 show：清洗后校验错误，返回解析前文本。"""
    text = sess.show(command)
    # show() 已剥离 echo/prompt；再次清洗兜底，保证解析器拿到干净文本
    text = _strip_echo_and_prompts(text, command)
    if _looks_like_error(text):
        raise RealPanelError(section, f"命令 '{command}' 返回错误", text[:400])
    return text


def collect_real_panel(device, username: str, password: str) -> dict:
    """IFC-RP-002-01: 单会话批量采集并组装 RealPanelSnapshot。

    返回 JSON 友好 dict：
    {device_id, ports, cpu, memory, io, info, collected_at}
    """
    with session_guard(device):
        with DeviceToolSession(device, username, password) as sess:
            ports_text = _run_show(sess, "show interface status", "ports")
            ports = parse_interface_status(ports_text)

            cpu_text = _run_show(sess, "show cpu-utilization", "cpu")
            cpu = parse_cpu_utilization(cpu_text)

            mem_text = _run_show(sess, "show memory-utilization", "memory")
            memory = parse_memory_utilization(mem_text)

            # IO 本轮降级占位（ADR-RP-002，无已验证 CLI 命令）
            io = parse_io_rates(None)

            # 基本信息（Should Have，容错非阻塞：失败置 None，不阻塞其余区块，ADR-RP-004）
            info = None
            try:
                info_text = _run_show(sess, "show system-info", "info")
                info = parse_system_info(info_text)
            except RealPanelError as e:
                logger.warning(f"[real_panel] info 采集失败（非阻塞）: {e}")

    return {
        "device_id": device.id,
        "ports": [asdict(p) for p in ports],
        "cpu": asdict(cpu),
        "memory": asdict(memory),
        "io": asdict(io),
        "info": asdict(info) if info else None,
        "collected_at": datetime.now(timezone.utc).isoformat(),
    }


def configure_real_port(
    device, username: str, password: str, port_name: str, action: str,
) -> PortWriteResult:
    """IFC-RP-002-02: 端口启用/禁用写操作（configure 不 save，AC-RP-005-03）。

    命令序列：configure → interface <name> → shutdown|no shutdown → exit
    （由 DeviceToolSession.configure 内部负责进入/退出 config 模式）。
    """
    cli_cmd = _map_action(action)
    commands = ["interface " + (port_name or "").strip(), cli_cmd]
    with session_guard(device):
        with DeviceToolSession(device, username, password) as sess:
            # DeviceToolSession 不暴露 save()，configure() 仅下发命令并 exit，
            # 结构上保证「不执行 copy running-config startup-config 持久化」。
            executed, failed, output = sess.configure(commands)

    success = (failed == 0) and (executed >= len(commands))
    if success:
        message = "端口配置成功"
    else:
        message = f"端口配置完成但存在失败命令（executed={executed}, failed={failed}）"
    return PortWriteResult(success=success, message=message, output=output)
