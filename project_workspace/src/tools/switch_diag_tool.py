"""
MOD-011: SwitchDiagTool — Diagnostic command execution on network switches.
@author sub_agent_software_developer
@module MOD-011
@implements IFC-011-01
@depends None
@covers REQ-FUNC-008, REQ-FUNC-009, REQ-FUNC-018, REQ-NFUNC-014

Strategy Pattern: AbstractSwitchDiagTool (ABC) → MockSwitchDiagTool | TpLinkSwitchDiagTool (reserved)

Mock 实现为 3 种告警类型提供逼真的模拟诊断数据:
  - MAC_FLAPPING → show mac address-table（含 MAC 漂移信息）
  - PORT_DOWN → show interface {iface}（端口 down 状态）
  - CPU_HIGH → show processes cpu（高 CPU 进程列表）
"""

import time
import random
from abc import ABC, abstractmethod
from typing import Any, Optional

from langchain_core.tools import BaseTool
from loguru import logger

from src.models.alert import DeviceAuth
from src.models.fix_plan import DiagResult


# ────────────────────────────────────────────────────
# Mock 诊断数据模板（3 种告警类型）
# ────────────────────────────────────────────────────

MOCK_MAC_TABLE = """Mac Address Table
-------------------------------------------
Vlan    Mac Address       Type        Ports
----    -----------       --------    -----
   1    00:1A:2B:3C:4D:5E DYNAMIC     Gi0/1
   1    00:1A:2B:3C:4D:5E DYNAMIC     Gi0/2
   1    00:2F:3A:4B:5C:6D DYNAMIC     Gi0/3
   1    00:3A:4B:5C:6D:7E DYNAMIC     Gi0/1
   1    00:4B:5C:6D:7E:8F DYNAMIC     Gi0/4
  10    00:1A:2B:3C:4D:5E DYNAMIC     Gi0/5
  10    00:5C:6D:7E:8F:9A DYNAMIC     Gi0/5
Total Mac Addresses for this criterion: 7

! WARNING: MAC address 00:1A:2B:3C:4D:5E appears on multiple ports (Gi0/1, Gi0/2) in VLAN 1
! MAC flapping detected — possible loop or security violation"""

MOCK_INTERFACE_STATUS = """Port      Name  Status       Vlan  Duplex Speed  Type
Gi0/1     Uplink1  down      1     Auto   Auto   10/100/1000BaseTX
Gi0/2           notconnect  1     Auto   Auto   10/100/1000BaseTX
Gi0/3           connected   1     Full   1000   10/100/1000BaseTX
Gi0/4           connected   1     Full   1000   10/100/1000BaseTX
Gi0/5           connected  10     Full   1000   10/100/1000BaseTX
Gi0/6           connected  10     Full   1000   10/100/1000BaseTX
Gi0/7           connected  10     Full   1000   10/100/1000BaseTX
Gi0/8           connected  10     Full   1000   10/100/1000BaseTX"""

MOCK_INTERFACE_DETAIL = """GigabitEthernet0/1 is down, line protocol is down (notconnect)
  Hardware is Gigabit Ethernet, address is 00:1A:2B:3C:4D:5E (bia 00:1A:2B:3C:4D:5E)
  MTU 1500 bytes, BW 1000000 Kbit/sec, DLY 10 usec,
     reliability 255/255, txload 1/255, rxload 1/255
  Encapsulation ARPA, loopback not set
  Keepalive set (10 sec)
  Auto-duplex, Auto-speed, media type is 10/100/1000BaseTX
  input flow-control is off, output flow-control is unsupported
  ARP type: ARPA, ARP Timeout 04:00:00
  Last input never, output never, output hang never
  Last clearing of "show interface" counters never
  Input queue: 0/75/0/0 (size/max/drops/flushes); Total output drops: 0
  Queueing strategy: fifo
  Output queue: 0/40 (size/max)
  5 minute input rate 0 bits/sec, 0 packets/sec
  5 minute output rate 0 bits/sec, 0 packets/sec
     0 packets input, 0 bytes, 0 no buffer
     Received 0 broadcasts (0 multicasts)
     0 runts, 0 giants, 0 throttles
     0 input errors, 0 CRC, 0 frame, 0 overrun, 0 ignored
     0 watchdog, 0 multicast, 0 pause input
     0 input packets with dribble condition detected
     0 packets output, 0 bytes, 0 underruns
     0 output errors, 0 collisions, 0 interface resets
     0 unknown protocol drops
     0 babbles, 0 late collision, 0 deferred
     0 lost carrier, 0 no carrier, 0 pause output
     0 output buffer failures, 0 output buffers swapped out"""

MOCK_CPU_PROCESSES = """CPU utilization for five seconds: 92%/5%; one minute: 88%; five minutes: 75%
 PID Runtime(ms)     Invoked      uSecs   5Sec   1Min   5Min TTY Process
   1           0           1          0  0.00%  0.00%  0.00%   0 Chunk Manager
   2         128        2184         58  0.00%  0.00%  0.00%   0 Load Meter
  23       10395       21766        477  0.31%  0.28%  0.25%   0 ARP Input
  47      452389     1234567        366 45.23% 42.18% 38.76%   0 IP Input
  53       12345       65432        188  1.20%  0.95%  0.88%   0 TCP Timer
  67       87654      345678        253  8.76%  7.23%  6.45%   0 HTTP CORE
  89      234567      987654        237 23.45% 20.11% 18.92%   0 SNMP ENGINE
 102       45678      123456        370  4.50%  3.98%  3.45%   0 SSH Process
 115       34567       87654        394  3.20%  2.87%  2.56%   0 Spanning Tree
 128       12340       56789        217  1.10%  0.95%  0.92%   0 HSRP Main
 145       23456       76543        306  2.30%  1.98%  1.88%   0 OSPF Router
 167       15678       34567        453  1.50%  1.28%  1.15%   0 CDP Protocol"""

MOCK_LOGGING = """Syslog logging: enabled
Console logging: level debugging
Monitor logging: level informational
Buffer logging: level debugging
Trap logging: level informational

Log Buffer (4096 bytes):
Jul 10 08:15:23: %SW_MATM-4-MACFLAP_NOTIF: Host 001a.2b3c.4d5e in vlan 1 is flapping between port Gi0/1 and port Gi0/2
Jul 10 08:15:18: %SW_MATM-4-MACFLAP_NOTIF: Host 001a.2b3c.4d5e in vlan 1 is flapping between port Gi0/2 and port Gi0/1
Jul 10 08:15:15: %LINEPROTO-5-UPDOWN: Line protocol on Interface GigabitEthernet0/1, changed state to down
Jul 10 08:14:50: %SYS-5-CONFIG_I: Configured from console by admin on vty0
Jul 10 08:10:00: %SYS-5-RESTART: System restarted"""

MOCK_CPU_HISTORY = """ CPU%  per second (last 60 seconds)
 100 |
  90 |          ##  #     #  ##   ##   ##     ###########
  80 |     ##  #### ##    #  ## ####   ## #   ###########
  70 |    ########### #   #  #######  ######  ###########
  60 |   #############  ##  ################  ###########
  50 |   ##################################  ###########
  40 |  ################################################
  30 | #################################################
  20 | #################################################
  10 | #################################################
     +----------------------------------------------------
       0    5    0    5    0    5    0    5    0    5    0
               10   20   30   40   50   60 seconds"""


# ────────────────────────────────────────────────────
# Abstract Base Class
# ────────────────────────────────────────────────────

class AbstractSwitchDiagTool(BaseTool, ABC):
    """
    交换机诊断工具抽象基类。
    IFC-011-01: diagnose(device_ip, command, auth) → DiagResult
    """

    name: str = "switch_diag"
    description: str = "Execute diagnostic commands on network switch and return output"

    @abstractmethod
    def _run(
        self,
        device_ip: str,
        command: str,
        auth: DeviceAuth,
    ) -> DiagResult:
        """Execute a diagnostic command and return structured output."""

    def run(
        self,
        tool_input: str = "",
        device_ip: str = "",
        command: str = "",
        auth: Optional[DeviceAuth] = None,
        **kwargs: Any,
    ) -> str:
        """LangChain Tool 统一入口。"""
        if auth is None:
            auth = DeviceAuth(username="admin", password="")
        result = self._run(device_ip, command, auth)
        return str(result.model_dump())


# ────────────────────────────────────────────────────
# Mock Implementation (Demo)
# ────────────────────────────────────────────────────

class MockSwitchDiagTool(AbstractSwitchDiagTool):
    """
    Mock 实现 — 根据命令和预定义的告警类型返回逼真的模拟诊断数据。

    支持的命令映射:
      - show mac address-table → MAC 表（含漂移检测）
      - show interface {iface} → 详细接口状态
      - show interface status → 所有接口状态列表
      - show processes cpu → CPU 进程列表
      - show processes cpu history → CPU 历史趋势
      - show logging → 系统日志
    """

    name: str = "switch_diag"
    description: str = "Execute diagnostic commands on network switch (Mock)"

    _MOCK_RESPONSES: dict[str, str] = {
        "show mac address-table": MOCK_MAC_TABLE,
        "show mac address": MOCK_MAC_TABLE,
        "show interface status": MOCK_INTERFACE_STATUS,
        "show processes cpu": MOCK_CPU_PROCESSES,
        "show process cpu": MOCK_CPU_PROCESSES,
        "show processes cpu history": MOCK_CPU_HISTORY,
        "show process cpu history": MOCK_CPU_HISTORY,
        "show logging": MOCK_LOGGING,
    }

    # 模拟命令执行时间范围 (ms)
    _MIN_EXEC_TIME = 200
    _MAX_EXEC_TIME = 800

    def _run(
        self,
        device_ip: str,
        command: str,
        auth: DeviceAuth,
    ) -> DiagResult:
        execution_time = random.randint(self._MIN_EXEC_TIME, self._MAX_EXEC_TIME)
        time.sleep(execution_time / 1000.0)  # 模拟网络延迟

        cmd_lower = command.lower().strip()

        # 精确匹配已知命令（按长度降序，避免子串误匹配）
        sorted_commands = sorted(self._MOCK_RESPONSES.keys(), key=len, reverse=True)
        for known_cmd in sorted_commands:
            if known_cmd in cmd_lower:
                logger.info(f"[MockDiag] {device_ip}: '{command}' → matched '{known_cmd}' ({execution_time}ms)")
                return DiagResult(
                    success=True,
                    output=self._MOCK_RESPONSES[known_cmd],
                    execution_time_ms=execution_time,
                )

        # show interface {iface} 动态匹配
        if "show interface " in cmd_lower:
            iface_name = cmd_lower.replace("show interface ", "").strip()
            # 替换接口名
            detail_output = MOCK_INTERFACE_DETAIL.replace("GigabitEthernet0/1", iface_name)
            detail_output = detail_output.replace("Gi0/1", iface_name)
            logger.info(f"[MockDiag] {device_ip}: '{command}' → interface detail ({execution_time}ms)")
            return DiagResult(
                success=True,
                output=detail_output,
                execution_time_ms=execution_time,
            )

        # 未匹配的命令
        logger.info(f"[MockDiag] {device_ip}: '{command}' → generic mock response ({execution_time}ms)")
        return DiagResult(
            success=True,
            output=f"! Mock output for: {command}\n! Device: {device_ip}\n! Status: OK\n",
            execution_time_ms=execution_time,
        )


# ────────────────────────────────────────────────────
# TP-Link Implementation (Reserved)
# ────────────────────────────────────────────────────

class TpLinkSwitchDiagTool(AbstractSwitchDiagTool):
    """
    TP-Link 真实实现（预留）。
    Demo 阶段不实现真实 SSH 调用，_run() 抛出 NotImplementedError。
    """

    name: str = "switch_diag_tplink"
    description: str = "Execute diagnostic commands on TP-Link switch via SSH (Reserved)"

    def _run(
        self,
        device_ip: str,
        command: str,
        auth: DeviceAuth,
    ) -> DiagResult:
        """
        [RESERVED] 后续阶段启用 TP-Link 真实 SSH 诊断。
        使用 Netmiko:
          - SSH 连接交换机
          - 执行 show 命令
          - 解析原始输出为结构化数据
        """
        raise NotImplementedError(
            "TpLinkSwitchDiagTool is reserved for future TP-Link integration. "
            "Use MockSwitchDiagTool for Demo phase."
        )


# ────────────────────────────────────────────────────
# Factory
# ────────────────────────────────────────────────────

def create_switch_diag_tool(
    use_mock: bool = True,
    device_type: str = "MOCK",
) -> AbstractSwitchDiagTool:
    """
    工厂函数：根据 device_type 创建对应的诊断工具实现。

    Args:
        use_mock: [DEPRECATED] 保留向后兼容，优先使用 device_type
        device_type: "MOCK" → MockSwitchDiagTool | "SIMULATOR" → SimulatorDiagTool

    REQ-FUNC-111: 工具工厂策略扩展 — 根据设备类型分发。
    """
    if device_type == "SIMULATOR":
        from src.tools.simulator_diag_tool import SimulatorDiagTool
        return SimulatorDiagTool()

    if not use_mock:
        return TpLinkSwitchDiagTool()

    return MockSwitchDiagTool()
