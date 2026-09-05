"""
Unit tests for MOD-RP-003: TP-Link CLI output parsers (real_panel_parsers.py).
@author sub_agent_test_engineer
@module MOD-RP-003
@covers REQ-RP-FUNC-002, REQ-RP-FUNC-003, REQ-RP-FUNC-004, REQ-RP-FUNC-005,
        REQ-RP-FUNC-009, REQ-RP-FUNC-010
@tracks AC-RP-002-01, AC-RP-003-01, AC-RP-003-02, AC-RP-004-01, AC-RP-009-01,
        AC-RP-009-02

纯函数单测：五个 parse_* 函数 + RealPanelError。样例贴近 TP-Link TL-SG5428
输出格式与 MOCK_INTERFACE_STATUS 参考格式；覆盖正常行、空列、notconnect/connected/
down、畸形行返回 unknown 或明确错误。

注意：FND-001（vlan/speed 位置启发式未用真实输出校准）与 FND-002（畸形行 unknown
而非抛错）为 code review 遗留 MAJOR/MINOR，本文件以 xfail 或显式断言记录其现状。
"""
from __future__ import annotations

import pytest

from src.tools.real_panel_parsers import (
    RealPanelError,
    PortStatus,
    CpuUsage,
    MemoryUsage,
    IoRates,
    DeviceInfo,
    parse_interface_status,
    parse_cpu_utilization,
    parse_memory_utilization,
    parse_io_rates,
    parse_system_info,
    _parse_port_line,
)


# ── 参考样例（贴近 TP-Link TL-SG5428 / MOCK_INTERFACE_STATUS） ──────────

MOCK_INTERFACE_STATUS = """Port      Name  Status       Vlan  Duplex Speed  Type
Gi0/1     Uplink1  down      1     Auto   Auto   10/100/1000BaseTX
Gi0/2           notconnect  1     Auto   Auto   10/100/1000BaseTX
Gi0/3           connected   1     Full   1000   10/100/1000BaseTX
Gi0/4           connected   1     Full   1000   10/100/1000BaseTX
Gi0/5           connected  10     Full   1000   10/100/1000BaseTX
Gi0/6           connected  10     Full   1000   10/100/1000BaseTX
Gi0/7           connected  10     Full   1000   10/100/1000BaseTX
Gi0/8           connected  10     Full   1000   10/100/1000BaseTX"""

# 单列 Status 的 TP-Link 风格输出（解析器可正确解析）
TPLINK_SINGLE_COLUMN = """Port       Status     Vlan   Speed
Gi1/0/1    up         1      1000
Gi1/0/2    down       1      1000
Gi1/0/3    notconnect 10     Auto"""

# TP-Link 双列 State(Enabled/Disabled)/Link(Up/Down) 风格（合成样例，见 FND-001）
TPLINK_TWO_COLUMN = """Port       State     Link   Speed   Duplex  PVID   Type
Gi1/0/1    Enabled   Up     1000    Full    1      10/100/1000BASE-T
Gi1/0/2    Enabled   Down   1000    Full    1      10/100/1000BASE-T"""


# ═══════════════════════════════════════════════════════════
# RealPanelError
# ═══════════════════════════════════════════════════════════

class TestRealPanelError:
    def test_fields_section_reason_excerpt(self):
        err = RealPanelError("ports", "输出为空", "PORT\nfoo")
        assert err.section == "ports"
        assert err.reason == "输出为空"
        assert err.raw_excerpt == "PORT\nfoo"

    def test_str_contains_section(self):
        err = RealPanelError("cpu", "未能解析出 CPU 5s 使用率")
        assert "[cpu]" in str(err)

    def test_is_exception(self):
        assert issubclass(RealPanelError, Exception)


# ═══════════════════════════════════════════════════════════
# IFC-RP-003-01: parse_interface_status
# ═══════════════════════════════════════════════════════════

class TestParseInterfaceStatus:
    def test_empty_text_raises(self):
        with pytest.raises(RealPanelError) as ei:
            parse_interface_status("")
        assert ei.value.section == "ports"

    def test_whitespace_only_raises(self):
        with pytest.raises(RealPanelError) as ei:
            parse_interface_status("   \n  \n")
        assert ei.value.section == "ports"

    def test_no_header_raises(self):
        # 无 "Port/Status" 或 "Interface/Status" 表头
        with pytest.raises(RealPanelError) as ei:
            parse_interface_status("Gi0/1 up 1")
        assert ei.value.section == "ports"

    def test_mock_reference_format_parses_8_ports(self):
        ports = parse_interface_status(MOCK_INTERFACE_STATUS)
        assert len(ports) == 8
        assert all(isinstance(p, PortStatus) for p in ports)

    def test_mock_reference_status_normalization(self):
        ports = parse_interface_status(MOCK_INTERFACE_STATUS)
        by_name = {p.name: p for p in ports}
        assert by_name["Gi0/1"].status == "down"        # down → down
        assert by_name["Gi0/2"].status == "notconnect"  # notconnect → notconnect
        assert by_name["Gi0/3"].status == "up"          # connected → up

    def test_empty_name_column(self):
        # Description/Name 列可为空（非定宽对齐），仍解析端口名
        ports = parse_interface_status(MOCK_INTERFACE_STATUS)
        by_name = {p.name: p for p in ports}
        assert by_name["Gi0/2"].name == "Gi0/2"
        assert by_name["Gi0/2"].vlan == "1"
        assert by_name["Gi0/2"].speed == "Auto"

    def test_vlan_and_speed_from_mock(self):
        ports = parse_interface_status(MOCK_INTERFACE_STATUS)
        by_name = {p.name: p for p in ports}
        assert by_name["Gi0/5"].vlan == "10"
        assert by_name["Gi0/5"].speed == "1000"
        assert by_name["Gi0/1"].speed == "Auto"

    def test_tplink_single_column_status(self):
        ports = parse_interface_status(TPLINK_SINGLE_COLUMN)
        assert [(p.name, p.status, p.vlan, p.speed) for p in ports] == [
            ("Gi1/0/1", "up", "1", "1000"),
            ("Gi1/0/2", "down", "1", "1000"),
            ("Gi1/0/3", "notconnect", "10", "Auto"),
        ]

    def test_interface_header_fallback(self):
        ports = parse_interface_status("Interface  Status  Vlan\nGi0/1  up  5")
        assert len(ports) == 1
        assert ports[0].name == "Gi0/1"
        assert ports[0].status == "up"
        assert ports[0].vlan == "5"

    def test_separator_line_skipped(self):
        text = "Port Status Vlan Speed\n---- ------ ---- -----\nGi0/1 up 1 1000"
        ports = parse_interface_status(text)
        assert len(ports) == 1
        assert ports[0].name == "Gi0/1"

    def test_pager_footer_skipped(self):
        # 真实 TL-SG5428 分页输出末尾带 "Press any key to continue (Q to quit)"
        text = ("Port Status Speed Duplex FlowCtrl Active-Medium\n"
                "Gi1/0/1 LinkUp 1000M Full Disable Copper\n"
                "Press any key to continue (Q to quit)")
        ports = parse_interface_status(text)
        assert len(ports) == 1
        assert ports[0].name == "Gi1/0/1"

    def test_real_speed_format_no_vlan(self):
        # 真实 TL-SG5428 `show interface status` 无 VLAN 列，speed 取 status 后一列
        text = ("Port Status Speed Duplex FlowCtrl Active-Medium\n"
                "---- ------ ----- ------ -------- -------------\n"
                "Gi1/0/1 LinkUp 1000M Full Disable Copper\n"
                "Gi1/0/2 LinkDown N/A N/A N/A Copper")
        ports = parse_interface_status(text)
        assert len(ports) == 2
        assert ports[0].name == "Gi1/0/1"
        assert ports[0].status == "up"
        assert ports[0].speed == "1000M"
        assert ports[0].vlan == ""
        assert ports[1].name == "Gi1/0/2"
        assert ports[1].status == "down"
        assert ports[1].speed == ""
        assert ports[1].vlan == ""

    def test_header_only_no_rows_raises(self):
        with pytest.raises(RealPanelError) as ei:
            parse_interface_status("Port Status Vlan Speed")
        assert ei.value.section == "ports"

    def test_malformed_line_returns_unknown(self):
        # FND-002: 未识别状态关键字时返回 status="unknown"（记录现状，不抛错）
        ports = parse_interface_status("Port Status Vlan\nGi0/1 foobar")
        assert ports[0].name == "Gi0/1"
        assert ports[0].status == "unknown"

    def test_status_normalization_table(self):
        cases = {
            "connected": "up", "link up": "up", "enabled": "up", "enable": "up",
            "up": "up", "link down": "down", "disabled": "down", "disable": "down",
            "down": "down", "not connect": "notconnect", "notconnect": "notconnect",
        }
        for raw, expected in cases.items():
            assert _parse_port_line(f"Gi0/1 {raw} 1 Auto").status == expected

    def test_parse_port_line_vlan_speed_positional(self):
        p = _parse_port_line("Gi0/1 down 10 Auto")
        assert p.name == "Gi0/1"
        assert p.status == "down"
        assert p.vlan == "10"
        assert p.speed == "Auto"

    @pytest.mark.xfail(
        reason=(
            "FND-001: vlan/speed 位置启发式在 TP-Link State(Enabled/Disabled)/"
            "Link(Up/Down) 双列格式下误配（合成样例，需真实 TL-SG5428 输出校准）"
        ),
        strict=False,
    )
    def test_tplink_two_column_state_link_format(self):
        # 期望：status 取 Link 列（Up→up），vlan 取 PVID 列，speed 取 Speed 列
        ports = parse_interface_status(TPLINK_TWO_COLUMN)
        assert [(p.name, p.status, p.vlan, p.speed) for p in ports] == [
            ("Gi1/0/1", "up", "1", "1000"),
            ("Gi1/0/2", "down", "1", "1000"),
        ]


# ═══════════════════════════════════════════════════════════
# IFC-RP-003-02: parse_cpu_utilization
# ═══════════════════════════════════════════════════════════

class TestParseCpuUtilization:
    def test_empty_text_raises(self):
        with pytest.raises(RealPanelError) as ei:
            parse_cpu_utilization("")
        assert ei.value.section == "cpu"

    def test_cisco_style_five_seconds(self):
        text = "CPU utilization for five seconds: 92%/5%; one minute: 88%; five minutes: 75%"
        cpu = parse_cpu_utilization(text)
        assert cpu.cpu_5s == 92.0
        assert cpu.cpu_1m == 88.0
        assert cpu.cpu_5m == 75.0

    def test_tplink_style_5s_labels(self):
        cpu = parse_cpu_utilization("CPU Utilization\n5 seconds: 12%\n1 minute: 8%\n5 minutes: 6%")
        assert cpu.cpu_5s == 12.0
        assert cpu.cpu_1m == 8.0
        assert cpu.cpu_5m == 6.0

    def test_5s_alias(self):
        cpu = parse_cpu_utilization("5s: 3%")
        assert cpu.cpu_5s == 3.0

    def test_fallback_first_percentage(self):
        # 无 5s 关键字时兜底取第一个百分数
        cpu = parse_cpu_utilization("CPU usage: 42%")
        assert cpu.cpu_5s == 42.0
        assert cpu.cpu_1m is None
        assert cpu.cpu_5m is None

    def test_optional_1m_5m_none(self):
        cpu = parse_cpu_utilization("five seconds: 7%")
        assert cpu.cpu_5s == 7.0
        assert cpu.cpu_1m is None
        assert cpu.cpu_5m is None

    def test_no_percentage_raises(self):
        with pytest.raises(RealPanelError) as ei:
            parse_cpu_utilization("no cpu data here")
        assert ei.value.section == "cpu"

    def test_returns_cpu_usage_type(self):
        assert isinstance(parse_cpu_utilization("5s: 1%"), CpuUsage)


# ═══════════════════════════════════════════════════════════
# IFC-RP-003-03: parse_memory_utilization
# ═══════════════════════════════════════════════════════════

class TestParseMemoryUtilization:
    def test_empty_text_raises(self):
        with pytest.raises(RealPanelError) as ei:
            parse_memory_utilization("")
        assert ei.value.section == "memory"

    def test_used_free_total_with_pct(self):
        text = "Memory Utilization\nUsed: 12345 KB\nFree: 54321 KB\nTotal: 66666 KB\nUtilization: 18%"
        mem = parse_memory_utilization(text)
        assert mem.used_mb == pytest.approx(12.06, abs=0.01)
        assert mem.total_mb == pytest.approx(65.10, abs=0.01)
        assert mem.usage_pct == 18.0

    def test_used_free_no_pct_derives_total_and_pct(self):
        # 仅 used/free：total=used+free，pct=used/total*100
        mem = parse_memory_utilization("Memory Used: 512 KB  Free: 512 KB")
        assert mem.used_mb == pytest.approx(0.5, abs=0.01)
        assert mem.total_mb == pytest.approx(1.0, abs=0.01)
        assert mem.usage_pct == pytest.approx(50.0, abs=0.01)

    def test_used_total_no_pct_computes_pct(self):
        mem = parse_memory_utilization("used 1024 KB total 2048 KB")
        assert mem.used_mb == pytest.approx(1.0, abs=0.01)
        assert mem.total_mb == pytest.approx(2.0, abs=0.01)
        assert mem.usage_pct == pytest.approx(50.0, abs=0.01)

    def test_kb_to_mb_conversion(self):
        mem = parse_memory_utilization("Used: 1024 KB\nTotal: 2048 KB")
        assert mem.used_mb == pytest.approx(1.0, abs=0.01)

    def test_total_zero_raises(self):
        with pytest.raises(RealPanelError) as ei:
            parse_memory_utilization("Used: 100 MB\nTotal: 0 MB")
        assert ei.value.section == "memory"

    def test_missing_used_total_raises(self):
        with pytest.raises(RealPanelError) as ei:
            parse_memory_utilization("just some text")
        assert ei.value.section == "memory"

    def test_returns_memory_usage_type(self):
        assert isinstance(parse_memory_utilization("Used: 1 MB\nTotal: 2 MB"), MemoryUsage)

    def test_percentage_only_real_output_degrades(self):
        # 真实 TL-SG5428 `show memory-utilization` 仅返回裸百分比 "80%"
        mem = parse_memory_utilization(
            "Unit  |  Current Memory Utilization\n"
            "-------+----------------------------\n"
            " 1     |   80%"
        )
        assert mem.usage_pct == 80.0
        assert mem.used_mb is None
        assert mem.total_mb is None


# ═══════════════════════════════════════════════════════════
# IFC-RP-003-04: parse_io_rates
# ═══════════════════════════════════════════════════════════

class TestParseIoRates:
    def test_always_unsupported_placeholder(self):
        # ADR-RP-002: 本轮固定降级占位
        io = parse_io_rates(None)
        assert isinstance(io, IoRates)
        assert io.supported is False
        assert io.read_kbps is None
        assert io.write_kbps is None
        assert "不支持" in io.message


# ═══════════════════════════════════════════════════════════
# IFC-RP-003-05: parse_system_info
# ═══════════════════════════════════════════════════════════

class TestParseSystemInfo:
    def test_empty_text_raises(self):
        with pytest.raises(RealPanelError) as ei:
            parse_system_info("")
        assert ei.value.section == "info"

    def test_full_fields_dash_separator(self):
        text = (
            "Device Name - SW-CORE-1\n"
            "Hardware Version - TL-SG5428 1.0\n"
            "Software Version - 2.0.0 Build 20240101\n"
            "Model - TL-SG5428"
        )
        info = parse_system_info(text)
        assert info.device_name == "SW-CORE-1"
        assert info.hardware_version == "TL-SG5428 1.0"
        assert info.software_version == "2.0.0 Build 20240101"
        assert info.model == "TL-SG5428"

    def test_partial_fields_model_via_tl_prefix(self):
        # FND-006: 仅含 Model(TL- 前缀) 与 Version 时字段部分为空（容错，不阻塞）
        info = parse_system_info("TP-Link TL-SG5428 Switch\nSoftware Version 2.0")
        assert info.model == "TL-SG5428"
        assert info.software_version == "2.0"
        assert info.device_name == ""

    def test_no_fields_raises(self):
        with pytest.raises(RealPanelError) as ei:
            parse_system_info("Some unrelated text without any fields")
        assert ei.value.section == "info"

    def test_colon_separator_variant(self):
        info = parse_system_info("Device Name: SW-1\nHardware Version: HW1\nSoftware Version: 1.0\nModel: TL-SG5428")
        assert info.device_name == "SW-1"
        assert info.hardware_version == "HW1"
        assert info.software_version == "1.0"
        assert info.model == "TL-SG5428"

    def test_returns_device_info_type(self):
        assert isinstance(
            parse_system_info("Device Name - SW-1\nModel - TL-SG5428"), DeviceInfo
        )
