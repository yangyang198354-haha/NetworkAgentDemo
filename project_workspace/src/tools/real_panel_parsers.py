"""
MOD-RP-003: TP-Link CLI 输出解析器（纯函数，仅 stdlib re）。
@author sub_agent_software_developer
@module MOD-RP-003
@implements IFC-RP-003-01, IFC-RP-003-02, IFC-RP-003-03, IFC-RP-003-04, IFC-RP-003-05
@depends 无（仅 stdlib re）
@covers REQ-RP-FUNC-002, REQ-RP-FUNC-003, REQ-RP-FUNC-004, REQ-RP-FUNC-005,
        REQ-RP-FUNC-009, REQ-RP-FUNC-010

将 TP-Link 真实 CLI 文本输出解析为结构化字段；纯函数、无状态、不建会话、
可直接单测；解析失败抛结构化异常 RealPanelError 而非返回伪造数据（REQ-RP-FUNC-009）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


# ── 类型定义（dataclass） ──────────────────────────────────

@dataclass
class PortStatus:
    name: str
    status: str
    vlan: str
    speed: str


@dataclass
class CpuUsage:
    cpu_5s: float
    cpu_1m: Optional[float] = None
    cpu_5m: Optional[float] = None


@dataclass
class MemoryUsage:
    used_mb: float
    total_mb: float
    usage_pct: float


@dataclass
class IoRates:
    supported: bool
    read_kbps: Optional[float] = None
    write_kbps: Optional[float] = None
    message: str = ""


@dataclass
class DeviceInfo:
    device_name: str
    model: str
    hardware_version: str
    software_version: str


class RealPanelError(Exception):
    """结构化解析错误：section=区块标识, reason=原因, raw_excerpt=原始输出摘录。"""

    def __init__(self, section: str, reason: str, raw_excerpt: str = ""):
        self.section = section
        self.reason = reason
        self.raw_excerpt = raw_excerpt
        super().__init__(f"[{section}] {reason}")


# ── 工具辅助 ──────────────────────────────────────────────

def _excerpt(text: str, limit: int = 400) -> str:
    if not text:
        return ""
    return text[:limit]


# ── IFC-RP-003-01: 端口状态 ───────────────────────────────

_STATUS_RE = (
    r"\b(?:not\s*connect|link\s*up|link\s*down|connected|"
    r"enabled?|disabled?|up|down)\b"
)


def parse_interface_status(text: str) -> list[PortStatus]:
    """解析 `show interface status` 清洗后文本 → 端口列表。

    表头用于定位表格起始行；数据行按「端口名(首列) + 状态关键字 + VLAN +
    速率」的容错规则解析，兼容 TP-Link 列式输出与 MOCK_INTERFACE_STATUS
    参考格式（Description/Name 列可为空，导致非定宽对齐）。
    """
    if not text or not text.strip():
        raise RealPanelError("ports", "show interface status 输出为空", _excerpt(text))

    lines = [ln.rstrip("\r\n") for ln in text.splitlines()]

    header_idx = None
    for i, ln in enumerate(lines):
        low = ln.lower()
        if "port" in low and ("status" in low or "state" in low):
            header_idx = i
            break
    if header_idx is None:
        for i, ln in enumerate(lines):
            low = ln.lower()
            if "interface" in low and ("status" in low or "state" in low):
                header_idx = i
                break
    if header_idx is None:
        raise RealPanelError("ports", "未找到端口状态表头（Port/Status）", _excerpt(text))

    ports: list[PortStatus] = []
    for ln in lines[header_idx + 1:]:
        s = ln.strip()
        if not s:
            continue
        # 跳过纯分隔线（如 ---- ---- ----）
        if set(s.replace("\t", " ").replace(" ", "")) <= set("-"):
            continue
        port = _parse_port_line(s)
        if port is not None:
            ports.append(port)

    if not ports:
        raise RealPanelError("ports", "未能解析出任何端口行", _excerpt(text))
    return ports


def _parse_port_line(line: str) -> Optional[PortStatus]:
    """按容错规则解析单条端口数据行（不依赖定宽列切分）。"""
    name_m = re.match(r"^(\S+)", line)
    if not name_m:
        return None
    name = name_m.group(1)

    sm = re.search(_STATUS_RE, line, re.I)
    status = _normalize_port_status(sm.group(0)) if sm else "unknown"
    search_from = sm.end() if sm else len(name)

    vlan = ""
    vm = re.search(r"\b(\d{1,4})\b", line[search_from:])
    if vm:
        vlan = vm.group(1)

    speed = ""
    speed_from = search_from + (vm.start() + len(vm.group(0)) if vm else 0)
    spd_m = re.search(r"\b(Auto|auto|--|\d+)\b", line[speed_from:])
    if spd_m:
        speed = spd_m.group(1)

    return PortStatus(name=name, status=status, vlan=vlan, speed=speed)


_STATUS_NORMALIZE = {
    "connected": "up",
    "link up": "up",
    "linkup": "up",
    "enabled": "up",
    "enable": "up",
    "up": "up",
    "link down": "down",
    "linkdown": "down",
    "disabled": "down",
    "disable": "down",
    "down": "down",
    "not connect": "notconnect",
    "not-connect": "notconnect",
    "notconnect": "notconnect",
}


def _normalize_port_status(status: str) -> str:
    s = (status or "").strip().lower()
    return _STATUS_NORMALIZE.get(s, s or "unknown")


# ── IFC-RP-003-02: CPU 利用率 ─────────────────────────────

_CPU_5S = re.compile(
    r"(?:5\s*seconds?|5s|five\s+seconds?)\s*[:=]?\s*(\d+(?:\.\d+)?)\s*%", re.I)
_CPU_1M = re.compile(
    r"(?:1\s*minute?|1m|one\s+minute?)\s*[:=]?\s*(\d+(?:\.\d+)?)\s*%", re.I)
_CPU_5M = re.compile(
    r"(?:5\s*minutes?|5m|five\s+minutes?)\s*[:=]?\s*(\d+(?:\.\d+)?)\s*%", re.I)


def _first_pct(pattern, text: str) -> Optional[float]:
    m = pattern.search(text)
    return float(m.group(1)) if m else None


def parse_cpu_utilization(text: str) -> CpuUsage:
    """解析 `show cpu-utilization` 文本 → CPU 5s（必填）/ 1m / 5m。"""
    if not text or not text.strip():
        raise RealPanelError("cpu", "show cpu-utilization 输出为空", _excerpt(text))

    cpu_5s = _first_pct(_CPU_5S, text)
    cpu_1m = _first_pct(_CPU_1M, text)
    cpu_5m = _first_pct(_CPU_5M, text)

    if cpu_5s is None:
        # 兜底：取文本中第一个百分数作为 5s 值（TP-Link 输出无 5s 关键字时）
        m = re.search(r"(\d+(?:\.\d+)?)\s*%", text)
        if m:
            cpu_5s = float(m.group(1))

    if cpu_5s is None:
        raise RealPanelError("cpu", "未能解析出 CPU 5s 使用率", _excerpt(text))

    return CpuUsage(cpu_5s=cpu_5s, cpu_1m=cpu_1m, cpu_5m=cpu_5m)


# ── IFC-RP-003-03: 内存利用率 ─────────────────────────────

_UNIT_MB = {
    "B": 1.0 / (1024 * 1024),
    "K": 1.0 / 1024,
    "KB": 1.0 / 1024,
    "M": 1.0,
    "MB": 1.0,
    "G": 1024.0,
    "GB": 1024.0,
}


def _mem_number(text: str, labels) -> Optional[float]:
    for label in labels:
        pat = re.compile(
            rf"\b{label}\b[^\d\n]*?(\d+(?:\.\d+)?)\s*(KB|MB|GB|K|M|G|B)?", re.I)
        m = pat.search(text)
        if m:
            val = float(m.group(1))
            unit = (m.group(2) or "MB").upper()
            return val * _UNIT_MB.get(unit, 1.0)
    return None


def parse_memory_utilization(text: str) -> MemoryUsage:
    """解析 `show memory-utilization` 文本 → used_mb / total_mb / usage_pct。

    若命令仅返回 used/free/total 则 usage_pct = used / total * 100。
    """
    if not text or not text.strip():
        raise RealPanelError("memory", "show memory-utilization 输出为空", _excerpt(text))

    used = _mem_number(text, ("used", "in use", "in-use"))
    total = _mem_number(text, ("total",))
    free = _mem_number(text, ("free",))

    pct = None
    m = re.search(r"(\d+(?:\.\d+)?)\s*%\s*(?:used|utiliz)", text, re.I)
    if m is None:
        m = re.search(r"(?:utiliz|usage)[^\d\n]*?(\d+(?:\.\d+)?)\s*%", text, re.I)
    if m:
        pct = float(m.group(1))

    if total is None and used is not None and free is not None:
        total = used + free
    if used is None and total is not None and free is not None:
        used = total - free

    if total is None or used is None:
        raise RealPanelError("memory", "未能解析出内存 used/total", _excerpt(text))
    if total <= 0:
        raise RealPanelError("memory", "内存 total 为 0，无法计算使用率", _excerpt(text))

    if pct is None:
        pct = round(used / total * 100.0, 2)

    return MemoryUsage(used_mb=round(used, 2), total_mb=round(total, 2), usage_pct=pct)


# ── IFC-RP-003-04: IO 读写速率（本轮降级占位） ────────────

def parse_io_rates(text: Optional[str] = None) -> IoRates:
    """本轮无已验证 IO CLI 命令，固定降级占位（ADR-RP-002）。

    未来接入替代命令时返回 supported=True 并填充速率，不改契约。
    """
    return IoRates(
        supported=False,
        read_kbps=None,
        write_kbps=None,
        message="该设备不支持 IO 采集（无已验证 CLI 命令）",
    )


# ── IFC-RP-003-05: 基本信息 ───────────────────────────────

def _re_field(text: str, pattern: str) -> str:
    m = re.search(pattern, text, re.I)
    return m.group(1).strip() if m else ""


def parse_system_info(text: str) -> DeviceInfo:
    """解析 `show system-info` 文本 → 设备名/型号/硬件版本/软件版本。

    字段提取对齐 real_device_client.check_connectivity 内
    `_parse_show_system_info` 的 Software/Hardware Version 提取方式。
    """
    if not text or not text.strip():
        raise RealPanelError("info", "show system-info 输出为空", _excerpt(text))

    device_name = (
        _re_field(text, r"Device Name\s*-\s*(\S+)")
        or _re_field(text, r"Device Name\s*[:=]\s*(\S+)")
    )
    hardware_version = (
        _re_field(text, r"Hardware Version\s*-\s*([A-Za-z0-9._\- ]+)")
        or _re_field(text, r"Hardware Version\s*[:=]\s*([A-Za-z0-9._\- ]+)")
    )
    software_version = (
        _re_field(text, r"Software Version\s*-\s*([A-Za-z0-9._\- ]+)")
        or _re_field(text, r"Software Version\s*[:=]\s*([A-Za-z0-9._\- ]+)")
        or _re_field(text, r"[Vv]ersion\s*[:=]?\s*([A-Za-z0-9._\-]+)")
    )
    model = (
        _re_field(text, r"Model\s*-\s*([A-Za-z0-9._\- ]+)")
        or _re_field(text, r"Model\s*[:=]\s*([A-Za-z0-9._\- ]+)")
        or _re_field(text, r"\b(TL-[A-Za-z0-9][A-Za-z0-9\-]*)")
        or _re_field(text, r"Device Model\s*[:=]\s*([A-Za-z0-9._\- ]+)")
    )

    if not any((device_name, hardware_version, software_version, model)):
        raise RealPanelError("info", "未能解析出任何系统信息字段", _excerpt(text))

    return DeviceInfo(
        device_name=device_name,
        model=model,
        hardware_version=hardware_version,
        software_version=software_version,
    )
