"""
MOD-RP-004: REAL 面板会话串行化门（per-device threading.Lock 注册表）。
@author sub_agent_software_developer
@module MOD-RP-004
@implements IFC-RP-004-01, IFC-RP-004-02, IFC-RP-004-03
@depends src.tools.real_device_client._resolve_access
@covers REQ-RP-NFUNC-004

以 `_resolve_access(device)` 解析出的 (host, port, protocol) 为规范 key，
维护进程内 {canonical_key -> threading.Lock} 注册表，保证同一物理设备
同一时刻仅一个活动会话（TP-Link TL-SG5428 TELNET 单会话限制）。
零新增第三方依赖（仅 stdlib threading + contextlib）。
"""

from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import Iterator

from src.tools.real_device_client import _resolve_access

# {canonical_key -> threading.Lock} 进程内注册表
_locks: dict[str, threading.Lock] = {}
_registry_lock = threading.Lock()


def _get_lock(key: str) -> threading.Lock:
    """Return (creating if necessary) the per-device lock for `key`."""
    with _registry_lock:
        lock = _locks.get(key)
        if lock is None:
            lock = threading.Lock()
            _locks[key] = lock
        return lock


def session_key(device) -> str:
    """IFC-RP-004-01: 返回规范串行化 key（经 _resolve_access，含 FRP 映射）。"""
    host, port, protocol = _resolve_access(device)
    return f"{host}:{int(port)}:{protocol}"


@contextmanager
def session_guard(device) -> Iterator[None]:
    """IFC-RP-004-02: 以 `with session_guard(device):` 串行化面板/连通性/写会话。"""
    lock = _get_lock(session_key(device))
    with lock:
        yield


@contextmanager
def session_guard_by_access(host: str, port: int, protocol: str) -> Iterator[None]:
    """IFC-RP-004-03: 供工作流工具按原始访问三元组串行化（共享同一锁注册表）。

    key 与 session_guard 共享同一注册表；当 host/port/protocol 与
    `_resolve_access(device)` 一致时，二者获取的是同一把锁。
    """
    key = f"{host}:{int(port)}:{(protocol or 'SSH').upper()}"
    lock = _get_lock(key)
    with lock:
        yield
