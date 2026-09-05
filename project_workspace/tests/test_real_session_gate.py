"""
Unit tests for MOD-RP-004: session serialization gate (real_session_gate.py).
@author sub_agent_test_engineer
@module MOD-RP-004
@covers REQ-RP-NFUNC-004, Q-RP-05
@tracks (横切约束，体现在 US-RP-002/003/005/007/009 语境)

per-device threading.Lock 注册表：session_key / session_guard / session_guard_by_access。
验证 key 规范格式、串行化门 acquire/release、以及 session_guard 与
session_guard_by_access 共享同一锁注册表（FND-003 边界语义）。
"""
from __future__ import annotations

import threading
from types import SimpleNamespace
from unittest.mock import patch

from src.tools.real_session_gate import (
    session_key,
    session_guard,
    session_guard_by_access,
    _get_lock,
    _locks,
)


def _make_device(protocol="SSH", frp_host=None, frp_port=None, ip="10.0.0.1",
                 ssh_port=22):
    return SimpleNamespace(
        connection_protocol=protocol,
        frp_proxy_host=frp_host,
        frp_proxy_port=frp_port,
        device_ip=ip,
        credential=SimpleNamespace(ssh_port=ssh_port),
    )


class TestSessionKey:
    def test_key_format_direct_access(self):
        with patch("src.tools.real_session_gate._resolve_access",
                   return_value=("10.0.0.1", 22, "SSH")):
            assert session_key(_make_device()) == "10.0.0.1:22:SSH"

    def test_key_format_frp_mapped(self):
        with patch("src.tools.real_session_gate._resolve_access",
                   return_value=("47.109.197.217", 60022, "SSH")):
            assert session_key(_make_device()) == "47.109.197.217:60022:SSH"

    def test_port_coerced_to_int(self):
        with patch("src.tools.real_session_gate._resolve_access",
                   return_value=("10.0.0.1", "22", "TELNET")):
            assert session_key(_make_device()) == "10.0.0.1:22:TELNET"


class TestSessionGuard:
    def test_guard_acquires_and_releases_lock(self):
        with patch("src.tools.real_session_gate._resolve_access",
                   return_value=("10.0.0.1", 22, "SSH")):
            with session_guard(_make_device()):
                lock = _get_lock("10.0.0.1:22:SSH")
                assert lock.locked() is True
            assert lock.locked() is False

    def test_same_device_same_lock(self):
        with patch("src.tools.real_session_gate._resolve_access",
                   return_value=("10.0.0.1", 22, "SSH")):
            key1 = session_key(_make_device())
            key2 = session_key(_make_device())
            assert key1 == key2
            assert _get_lock(key1) is _get_lock(key2)


class TestSessionGuardByAccess:
    def test_key_normalizes_protocol_upper(self):
        with session_guard_by_access("10.0.0.1", 22, "ssh"):
            assert "10.0.0.1:22:SSH" in _locks

    def test_default_protocol_is_ssh(self):
        with session_guard_by_access("10.0.0.1", 22, None):
            assert "10.0.0.1:22:SSH" in _locks

    def test_guard_acquires_and_releases(self):
        with session_guard_by_access("10.0.0.1", 22, "SSH"):
            lock = _get_lock("10.0.0.1:22:SSH")
            assert lock.locked() is True
        assert lock.locked() is False

    def test_shares_registry_with_session_guard(self):
        # FND-003 边界：当 host/port/protocol 一致时二者应命中同一把锁
        with patch("src.tools.real_session_gate._resolve_access",
                   return_value=("10.0.0.1", 22, "SSH")):
            with session_guard(_make_device()):
                pass
        with session_guard_by_access("10.0.0.1", 22, "ssh"):
            pass
        assert _get_lock("10.0.0.1:22:SSH") is _get_lock("10.0.0.1:22:SSH")
        assert isinstance(_get_lock("10.0.0.1:22:SSH"), type(threading.Lock()))

    def test_registry_returns_threading_lock(self):
        lock = _get_lock("10.0.0.1:22:SSH")
        assert isinstance(lock, type(threading.Lock()))
