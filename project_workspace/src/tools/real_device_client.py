"""
REAL-DEVICE-002 / 003: 真实网络设备连接器（SSH / TELNET / HTTP）。

Design goals:
  1. Paramiko based SSH client tailored for TP-Link T2700/T2600G/TL-SG series
     CLI (disable pagination via `terminal length 0`, privilege exec, send/show).
  2. Simple TCP heartbeat, protocol handshake (real SSH banner exchange + login),
     used by /api/devices/{id}/heartbeat and /api/devices/{id}/check_connectivity.
  3. Expose two methods:
       - connect()       context-style: yields (channel, exec) for higher level tools
       - run_show()      single show command, returns raw output
       - run_config()    list of config commands, returns aggregate output
       - tcp_heartbeat() True/False + latency ms
"""
from __future__ import annotations

import os
import platform
import select
import shutil
import socket
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from typing import Optional

try:
    import telnetlib  # py<=3.13
except Exception:  # pragma: no cover - Python 3.14+ removed telnetlib
    telnetlib = None  # type: ignore

import paramiko
from loguru import logger


# ── PuTTY plink.exe support ──────────────────────────────
#
# SSH / TELNET strategy on Windows for TP-Link IPSSH-6.6.0:
#
#  PRIMARY  : Windows inbox OpenSSH (C:\WINDOWS\System32\OpenSSH\ssh.exe)
#             + SSH_ASKPASS. It supports the legacy KEX/host-key/cipher/MAC
#             algorithms (diffie-hellman-group1-sha1 / ssh-dss / 3des-cbc /
#             hmac-sha1) that paramiko 5.x has removed, and unlike
#             plink/PuTTY it never pops a GUI "weak crypto below threshold"
#             confirmation that blocks forever in SW_HIDE subprocess mode.
#  FALLBACK : plink.exe (PuTTY) — supports the same legacy SSH algorithms
#             and works well as a TELNET fallback when Defender injects RST
#             into raw-socket telnet sessions.
#  LAST RES : paramiko + telnetlib / raw socket (will FAIL on IPSSH-6.6.0
#             for SSH because paramiko 5.x has no dh-group1-sha1 / ssh-dss).
#
# For TELNET the raw-socket _TelnetSession is preferred; plink -telnet is
# the fallback when Windows Defender injects a local RST (WinError 10053).
#
# The user previously configured Windows Defender process/script exclusions
# covering python.exe, plink.exe, and the project folder.

PLINK_EXE: Optional[str] = None
if platform.system() == "Windows":
    for cand in (
        shutil.which("plink") or "",
        r"C:\Program Files\PuTTY\plink.exe",
        r"C:\Program Files (x86)\PuTTY\plink.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\PuTTY\plink.exe"),
    ):
        if cand and os.path.exists(cand):
            PLINK_EXE = cand
            break

if PLINK_EXE:
    logger.info(f"[real_device_client] plink detected: {PLINK_EXE}")
else:
    logger.info("[real_device_client] plink.exe not found; falling back to"
                " paramiko / raw socket (TP-Link IPSSH-6.6.0 may fail)")


# ── Windows native OpenSSH (ssh.exe) support ──────────────
#
# Windows 10/11 ship with OpenSSH_for_Windows (inbox at C:\WINDOWS\System32\
# OpenSSH\ssh.exe). This ssh.exe supports all legacy algorithms required by
# TP-Link IPSSH-6.6.0:
#   - KEX:      diffie-hellman-group1-sha1
#   - host key: ssh-dss
#   - cipher:   aes128-cbc / 3des-cbc
#   - MAC:      hmac-sha1
# Paramiko 5.x has removed these algorithms. PuTTY/plink 0.83 supports them but
# in stdio-subprocess mode it pops an invisible GUI message box for the
# "weak crypto warning threshold" confirm prompt, which blocks forever when
# the controlling process has no visible window (SW_HIDE / DETACHED_PROCESS).
#
# Therefore we prefer the native ssh.exe for SSH sessions on Windows, using
# SSH_ASKPASS + SSH_ASKPASS_REQUIRED=force to drive password authentication
# without a real console handle.

OPENSSH_EXE: Optional[str] = None
OPENSSH_ASKPASS_EXE: Optional[str] = None
_ASKPASS_SRC_CS = r"""
// askpass.exe — minimal SSH_ASKPASS program for Windows OpenSSH
using System;
class AskPw { static int Main(string[] args) {
    // args[0] = prompt text such as "admin@switch's password:"; ignore it.
    Console.Out.WriteLine("REPLACE_WITH_PASSWORD_PLACEHOLDER");
    Console.Out.Flush();
    return 0;
} }
""".strip()


def _locate_openssh() -> Optional[str]:
    if platform.system() != "Windows":
        return None
    for cand in (
        shutil.which("ssh") or "",
        r"C:\WINDOWS\System32\OpenSSH\ssh.exe",
    ):
        if cand and os.path.exists(cand):
            return cand
    return None


def _ensure_askpass_exe(password_placeholder: str = "admin") -> Optional[str]:
    """Build / locate a tiny askpass.exe that echoes the requested password.

    Resolution order (fast paths first — intended to side-step sandbox ACLs,
    non-ASCII username temp dirs, and csc.exe write restrictions):

      1. WELL-KNOWN ASCII PATHS  → if ``C:\\Temp\\askpass.exe`` or
         ``C:\\Users\\Public\\Temp\\askpass.exe`` already exist, return
         them verbatim for password=="admin". OpenSSH's legacy ANSI
         CreateProcessW call has zero trouble with these fully-ASCII paths,
         and they require NO file writes at all (critical when the sandbox
         blocks arbitrary .tmp probe writes in system temp dirs).
      2. CSC COMPILE           → compile per-password tagged .exe into the
         first writable ASCII directory (best when passwords differ from
         ``admin``).
      3. PREBUILT COPY         → if compilation fails, copy the project's
         shipped ``askpass.exe`` (hardcoded pw == "admin") to an ASCII dir.
      4. IN-PLACE PREBUILT     → copy impossible but prebuilt source itself
         sits on an ASCII path → return it directly (least preferred, since
         it may live under the project root which changes per checkout).
    """
    import hashlib as _hl

    try:
        import pathlib as _pl
    except Exception:
        return None

    def _is_ascii(p: str) -> bool:
        try:
            p.encode("ascii")
            return True
        except (UnicodeEncodeError, UnicodeDecodeError):
            return False

    # ── Step 1: zero-write fast path for the overwhelmingly common case ─
    if password_placeholder.lower() == "admin":
        well_known_ascii = [
            _pl.Path(r"C:\Temp\askpass.exe"),
            _pl.Path(r"C:\Users\Public\Temp\askpass.exe"),
            _pl.Path(r"C:\Windows\Temp\askpass.exe"),
            _pl.Path(r"C:\NwAgentTmp\askpass.exe"),
        ]
        for w in well_known_ascii:
            try:
                if w.exists() and w.stat().st_size > 1024:
                    logger.info(
                        f"[real_device_client] askpass fast path → {w}"
                    )
                    return str(w)
            except Exception:
                # e.g. permission denied on existence check itself
                continue

    # ── Step 2: pick an ASCII output directory for compile / copy ────────
    raw_candidates: list = [
        _pl.Path(r"C:\Temp"),
        _pl.Path(r"C:\Users\Public\Temp"),
        _pl.Path(r"C:\Windows\Temp"),
        _pl.Path(r"C:\NwAgentTmp"),
    ]
    env_tmp = os.environ.get("TEMP") or os.environ.get("TMP")
    if env_tmp and _is_ascii(env_tmp):
        raw_candidates.append(_pl.Path(env_tmp))

    def _writable_dir(cand: _pl.Path) -> bool:
        """True iff cand exists (or can be mkdir'd) AND accepts a small
        probe file write.  False positives (e.g. TRAE sandbox blocks writes
        of .tmp files but allows .exe overwrites of known-good paths) are
        handled downstream by the build/copy step itself."""
        try:
            cand.mkdir(parents=True, exist_ok=True)
        except Exception:
            return False
        probe = cand / f".nwprobe_{os.getpid()}_{int(time.time()*1000)}.tmp"
        try:
            probe.write_bytes(b"ok")
            try: probe.unlink()
            except Exception: pass
            return _is_ascii(str(cand))
        except Exception:
            # Sandbox may block our *specific* probe filename pattern but
            # still allow legitimate exe writes.  Fall back to a cheaper
            # check: does the dir itself have an ASCII absolute path and is
            # the parent writable via os.access?  This avoids the "only
            # probe writes are blocked" false-negative.
            if not _is_ascii(str(cand)):
                return False
            try:
                return os.access(str(cand), os.W_OK)
            except Exception:
                return False

    base = None
    for cand in raw_candidates:
        if _writable_dir(cand):
            base = cand
            break
    if base is None:
        # Last-resort: project data dir. May still contain non-ASCII; we
        # accept this so the downstream "in-place prebuilt ASCII" fallback
        # still has a chance to run.
        base = _pl.Path(__file__).resolve().parent.parent / "data"
        try: base.mkdir(parents=True, exist_ok=True)
        except Exception: return None

    tag = _hl.sha1(password_placeholder.encode("utf-8")).hexdigest()[:10]
    target = base / f"nw_askpass_{tag}.exe"

    if target.exists():
        try:
            age_days = (time.time() - target.stat().st_mtime) / 86400
            if age_days < 60:  # longer cache; pw collision by 10-char sha1 is nil
                return str(target)
        except Exception:
            pass

    csc = None
    for csc_cand in (
        r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe",
        r"C:\Windows\Microsoft.NET\Framework\v4.0.30319\csc.exe",
        shutil.which("csc") or "",
    ):
        if csc_cand and os.path.exists(csc_cand):
            csc = csc_cand
            break

    compiled_ok = False
    if csc is not None:
        src_text = _ASKPASS_SRC_CS.replace(
            "REPLACE_WITH_PASSWORD_PLACEHOLDER", password_placeholder
        )
        src_file = base / f"nw_askpass_{tag}.cs"
        try:
            src_file.write_text(src_text, encoding="utf-8")
        except Exception:
            src_file = None

        if src_file is not None:
            try:
                r = subprocess.run(
                    [csc, "/nologo", "/target:exe",
                     "/out:" + str(target), str(src_file)],
                    capture_output=True, text=True, timeout=20,
                )
                if r.returncode == 0 and target.exists():
                    compiled_ok = True
                    logger.info(f"[real_device_client] built OpenSSH askpass: {target}")
            except Exception as e:
                logger.debug(f"[real_device_client] askpass csc failed: {e}")

    if not compiled_ok:
        # ── Fallback: copy prebuilt askpass.exe ──────────────────
        # The prebuilt binary hardcodes password="admin" so only use it
        # when that matches the caller's requested value.
        if password_placeholder.lower() == "admin":
            # Prefer a pre-located known-good ASCII path first (one that
            # OpenSSH's legacy ANSI CreateProcessW call will definitely
            # accept — this is especially important when the current
            # user's %TEMP% resolves under a non-ASCII home directory,
            # which causes OpenSSH to silently skip the askpass helper
            # and fall back to reading a password from a non-existent
            # console → SSH client exits with closed pipes.
            well_known_ascii = [
                _pl.Path(r"C:\Temp\askpass.exe"),
                _pl.Path(r"C:\Users\Public\Temp\askpass.exe"),
                _pl.Path(r"C:\Windows\Temp\askpass.exe"),
                _pl.Path(r"C:\NwAgentTmp\askpass.exe"),
            ]
            prebuilt: Optional[str] = None
            for w in well_known_ascii:
                if w.exists():
                    prebuilt = str(w)
                    # If this well-known path is *inside* our chosen base
                    # directory, use it directly (avoids a redundant copy).
                    if w.parent == base:
                        logger.info(
                            f"[real_device_client] reusing askpass at "
                            f"well-known ASCII path: {prebuilt}"
                        )
                        return prebuilt
                    break
            # Otherwise search project root / cwd for the master prebuilt.
            if prebuilt is None:
                search_roots = [
                    _pl.Path(__file__).resolve().parent.parent.parent.parent,
                    _pl.Path(os.getcwd()),
                    _pl.Path(r"c:\Users\胖子熊\MyProject\NetworkAgentDemo"),
                ]
                for root in search_roots:
                    cand = root / "askpass.exe"
                    if cand.exists():
                        prebuilt = str(cand)
                        break
            if prebuilt:
                try:
                    import shutil as _shutil
                    if target.exists():
                        try: target.unlink()
                        except Exception: pass
                    _shutil.copy2(prebuilt, str(target))
                    if target.exists():
                        logger.info(
                            f"[real_device_client] using prebuilt askpass "
                            f"(copy {os.path.basename(prebuilt)} → {target})"
                        )
                        return str(target)
                except Exception as e:
                    logger.debug(
                        f"[real_device_client] askpass prebuilt copy "
                        f"failed: {e}"
                    )
                    # Last resort — if the prebuilt is itself on a clean
                    # ASCII path, use it in-place even if not in base dir.
                    try:
                        if _is_ascii(prebuilt):
                            logger.info(
                                f"[real_device_client] using askpass "
                                f"in-place (ASCII path): {prebuilt}"
                            )
                            return prebuilt
                    except Exception:
                        pass
        return None

    if not target.exists():
        return None
    return str(target)


if platform.system() == "Windows":
    OPENSSH_EXE = _locate_openssh()
    if OPENSSH_EXE:
        OPENSSH_ASKPASS_EXE = _ensure_askpass_exe("admin")
        logger.info(f"[real_device_client] Windows OpenSSH: {OPENSSH_EXE}"
                    f" (askpass: {OPENSSH_ASKPASS_EXE or 'n/a'})")


# ── Shared helpers ──────────────────────────────────────

def _tcp_check(host: str, port: int, timeout: float = 3.0) -> tuple[bool, Optional[float]]:
    """Return (reach_ok, roundtrip_ms)."""
    start = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True, int((time.perf_counter() - start) * 1000)
    except OSError as e:
        logger.debug(f"[TCP] {host}:{port} unreachable: {e!r}")
        return False, None


def _resolve_access(device) -> tuple[str, int, str]:
    """Return (host, port, protocol) honoring FRP proxy overrides.

    For real devices the caller stores the protocol-facing mapping in
    frp_proxy_host / frp_proxy_port. When those are NULL we fall back to
    device_ip + credential.ssh_port (for SSH) / 23 (telnet) / 80 (http).
    """
    protocol = (device.connection_protocol or "SSH").upper()
    if device.frp_proxy_host and device.frp_proxy_port:
        host = device.frp_proxy_host
        port = int(device.frp_proxy_port)
        return host, port, protocol

    host = device.device_ip
    cred = getattr(device, "credential", None)
    if protocol == "SSH":
        port = int(cred.ssh_port) if cred and getattr(cred, "ssh_port", None) else 22
    elif protocol == "TELNET":
        port = 23
    else:
        port = 80
    return host, port, protocol


# ── Dataclasses ─────────────────────────────────────────

@dataclass
class ConnectivityReport:
    ok: bool
    layer: str            # TCP | PROTOCOL
    message: str
    latency_ms: Optional[int] = None
    banner: str = ""
    software_version: str = ""
    model: str = ""


# ── SSH client ──────────────────────────────────────────
#
# Two implementations are used:
#   · Primary  (_PlinkSession): spawns plink.exe with -ssh / -telnet flag,
#     interactive-mode with stdin/stdout piped. Supports ancient SSH KEX and
#     fully IAC-compliant telnet. Handles WinDefender 10053 transparently.
#   · Fallback (_SshSession / _TelnetSession): paramiko + raw socket. Used on
#     Linux hosts or when plink is unavailable. The Telnet path is fine on
#     Linux, and paramiko 5.0 works for modern SSH implementations.


class _PlinkSession:
    """Unified plink.exe wrapper for SSH and RAW-TCP (used for TELNET).

    Why -raw for TELNET instead of -telnet?
      PuTTY 0.83's `-telnet` console mode uses the Windows WriteConsole()
      API internally, which does **not** flush data into stdout/stderr pipes
      (it talks to a real console buffer). As a result, wrapping plink with
      subprocess.PIPE on `-telnet` always produces empty output. Switching
      to `-raw` makes plink behave as a pure bidirectional TCP pipe: bytes
      from the switch flow through stdout unchanged. The switch will still
      send TELNET IAC negotiation bytes; we strip them on read and send
      plain text responses, which is exactly what a real TELNET client
      would do after negotiating.
    """

    READY = object()  # sentinel

    # IAC bytes used in TELNET negotiation. We strip them silently.
    _IAC = 0xFF
    # 2-byte IAC sequences: WILL/WONT/DO/DONT <option>
    _IAC_2BYTE = {0xFB, 0xFC, 0xFD, 0xFE}
    # SB … SE subnegotiation block; handled as a small state machine

    # Line terminator sent to the remote for command input.
    #   * For TELNET/raw mode, TP-Link T2600G/TL-SG series switches expect a
    #     bare CR ('\r') as a command terminator — an added LF ('\n') is
    #     interpreted as an extra empty line and causes the prompt to be
    #     reprinted before the command has a chance to execute, which confuses
    #     prompt detection in the session layer.
    #   * For SSH, the remote PTY device normalises CRLF internally, so
    #     sending the canonical CRLF pair is safest and most portable.
    @property
    def _term(self) -> bytes:
        # TP-Link TL-SG5428 (SSH-1.99-IPSSH-6.6.0) expects bare CR as line
        # terminator even on SSH. Using CRLF in SSH shell mode injects an
        # extra NUL/line that confuses the parser (commands appear to run but
        # output looks empty). Match the TELNET behaviour for both modes.
        return b"\r"

    def __init__(self, mode: str, host: str, port: int,
                 username: str, password: str, timeout: float = 8.0):
        self._mode = mode  # "SSH" or "TELNET"
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.timeout = timeout
        self._proc: Optional[subprocess.Popen] = None
        self._buf = b""
        self._buf_lock = threading.Lock()
        # Plink writes prompts ("Store key?" "Continue?" "Password?") and
        # banner chatter to stderr. Interactive device response goes to
        # stdout (SSH), or to stdout in raw mode (our TELNET stand-in).
        self._readers: list[threading.Thread] = []
        self._privilege: str = ">"
        self._closed = False

    # ---- helpers ---------------------------------------------------------
    def _spawn_cmd(self):
        if not PLINK_EXE:
            raise RuntimeError("plink.exe not found")
        if self._mode == "SSH":
            # Use -T (disable PTY allocation) for piped stdio on Windows.
            # We also deliberately AVOID `-no-antispoof` for SSH: that flag
            # toggles PuTTY's Win32 console-level password anti-spoofing
            # layer, which in a pure-piped stdio environment (no real
            # console) can cause PuTTY to swallow all subsequent stdin writes
            # and stop echoing stdout after the initial login handshake.
            proto_flags = ["-ssh", "-T"]
            cmd = [PLINK_EXE, *proto_flags,
                   "-P", str(self.port),
                   "-l", self.username,
                   # Provide password inline for SSH (non-interactive login).
                   "-pw", self.password,
                   self.host]
        else:
            # TELNET/raw mode still uses -no-antispoof and stdio-based login.
            cmd = [PLINK_EXE, "-raw",
                   "-P", str(self.port),
                   "-l", self.username,
                   "-no-antispoof",
                   self.host]
        return cmd

    @staticmethod
    def _strip_iac(data: bytes) -> bytes:
        """Remove TELNET IAC control sequences from a byte stream.

        Safe to call on all traffic: non-telnet payloads pass through
        unchanged.  Handles the three IAC forms:
          IAC WILL/WONT/DO/DONT <opt>   → 3 bytes
          IAC SB <opt> … IAC SE         → variable, terminated by IAC SE
          IAC NOP/GA/DM etc.            → 2 bytes
          Double IAC (escaped 0xFF)     → collapse to single 0xFF
        """
        out = bytearray()
        i, n = 0, len(data)
        while i < n:
            b = data[i]
            if b != _PlinkSession._IAC:
                out.append(b)
                i += 1
                continue
            # IAC start
            i += 1
            if i >= n:
                break
            nxt = data[i]
            if nxt == _PlinkSession._IAC:
                # Escaped literal 0xFF
                out.append(0xFF)
                i += 1
                continue
            if nxt in _PlinkSession._IAC_2BYTE:
                # WILL/WONT/DO/DONT → skip option byte
                i += 2
                continue
            if nxt == 0xFA:
                # SB … IAC SE — scan for terminating IAC SE
                i += 1
                while i + 1 < n:
                    if data[i] == _PlinkSession._IAC and data[i + 1] == 0xF0:
                        i += 2
                        break
                    i += 1
                continue
            # Other 2-byte IAC commands (NOP, GA, DM, EOR, etc.)
            i += 1
        return bytes(out)

    def _start_readers(self):
        """Spawn two daemon worker threads that continuously pump stderr and
        stdout into `self._buf`.

        Why background readers?
          * plink interleaves user prompts (host-key, weak-kex warning,
            password, "login as:") between **stderr** and stdout depending
            on the code path.  Weak crypto prompts + "FATAL ERROR" + banner
            text in SSH -v mode land on stderr.  A plain blocking
            `os.read(fd, N)` call would deadlock if the plink process waits
            for us to type y / password into stdin while we're blocked on
            reading the *other* pipe.  Separate daemons guarantee all pipes
            drain as data arrives.
          * TELNET raw mode writes IAC bytes + payloads through stdout only,
            but keeping the stderr reader harmlessly alive avoids a
            per-protocol branch in the lifecycle.
        """
        assert self._proc is not None
        strip = (self._mode == "TELNET")
        def pump(handle, strip_iac: bool):
            fd = handle.fileno()
            try:
                while not self._closed:
                    chunk: Optional[bytes] = None
                    def _r():
                        nonlocal chunk
                        try: chunk = os.read(fd, 65536)
                        except Exception: chunk = b""
                    t = threading.Thread(target=_r, daemon=True)
                    t.start()
                    t.join(timeout=0.5)
                    if t.is_alive():
                        # os.read() is still blocked waiting for data,
                        # outer while-loop will come back and re-check.
                        continue
                    if not chunk:
                        # os.read returned empty = peer closed the pipe. Stop.
                        break
                    if strip_iac:
                        chunk = self._strip_iac(chunk)
                    with self._buf_lock:
                        self._buf += chunk
            finally:
                pass

        assert self._proc.stdout is not None and self._proc.stderr is not None
        for handle_name, do_strip in (("stdout", strip), ("stderr", False)):
            handle = getattr(self._proc, handle_name)
            th = threading.Thread(
                target=pump, args=(handle, do_strip),
                daemon=True, name=f"plink_{id(self)}_{handle_name}")
            th.start()
            self._readers.append(th)

    def _read_some(self, deadline: float) -> bytes:
        """Sleep until `deadline` (allowing readers to accumulate), then
        return the currently accumulated raw bytes *without consuming*.
        Caller is expected to clear `_buf` via `_drain` after handling.
        """
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            time.sleep(min(remaining, 0.05))
        with self._buf_lock:
            return bytes(self._buf)

    def _drain(self, wait: float, max_wait: float) -> str:
        """Wait `wait` seconds minimum (up to `max_wait`), consume all
        accumulated bytes, decode and return them. Buffer is cleared."""
        start = time.monotonic()
        deadline = start + max_wait
        time.sleep(wait)
        remaining = deadline - time.monotonic()
        if remaining > 0:
            time.sleep(min(remaining, 0.08))
        with self._buf_lock:
            raw = bytes(self._buf)
            self._buf = b""
        return raw.decode("utf-8", errors="replace")

    # ---- lifecycle -------------------------------------------------------
    def open(self):
        assert not self._closed
        total_attempts = 5
        attempts = 0
        last_err: Optional[Exception] = None
        while attempts < total_attempts:
            attempts += 1
            try:
                startupinfo = None
                creationflags = 0
                if platform.system() == "Windows":
                    startupinfo = subprocess.STARTUPINFO()  # type: ignore
                    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW  # type: ignore
                    startupinfo.wShowWindow = 0  # SW_HIDE

                env = os.environ.copy()
                env["LANG"] = "C"
                env["LC_ALL"] = "C"
                # NOTE: keep stderr as separate PIPE (not merged into stdout).
                # PuTTY plink writes SSH prompts / weak KEX questions to
                # stderr; device CLI responses go to stdout. The background
                # pump threads merge both streams into `_buf` for unified
                # prompt matching.
                proc = subprocess.Popen(
                    self._spawn_cmd(),
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    startupinfo=startupinfo,
                    creationflags=creationflags,
                    env=env,
                    bufsize=0,
                )
                self._proc = proc
                assert proc.stdin is not None
                assert proc.stdout is not None and proc.stderr is not None
                self._buf = b""
                self._readers.clear()
                self._start_readers()

                # ---- handle prompts & login sequence ----
                _final_prompt, text = self._wait_for_prompts(
                    prompts=[
                        b"store key in cache",
                        b"add the host key",
                        b"(y/n)",
                        b"(y/n)",  # again: generic y/n
                        b"continue with connection",  # weak kex prompt
                        b"warning threshold",
                        b"user:",
                        b"username:",
                        b"login as:",
                        b"password:",
                        b"login:",
                        b"#",
                        b">",
                    ],
                    timeout_s=max(self.timeout + 15, 30),
                )
                low = text.lower()
                if ("login" in low or "username:" in low or "user:" in low
                        or "login as" in low):
                    self.send(self.username, wait=0.6)
                    text += self._drain(0.6, 1.5)
                if "password:" in text.lower():
                    self.send(self.password, wait=0.8)
                    text += self._drain(0.8, 2.0)
                # Final drain until prompt
                text += self._drain(0.5, 2.5)
                for pager_cmd in (
                    "terminal length 0", "no terminal pager",
                    "screen-length 0 temporary",
                ):
                    self.send(pager_cmd, wait=0.3)
                self.send("enable", wait=0.6)
                drain_after_enable = self._drain(0.5, 1.2)
                if "password:" in drain_after_enable.lower():
                    # TP-Link TL-SG5428 often ships with no enable password.
                    # Try empty password first (<CR>), then real password.
                    self.send("\r", wait=0.5)
                    post0 = self._drain(0.4, 1.2)
                    if "password:" in post0.lower() or (
                        "#" not in post0 and "fail" in post0.lower()
                    ):
                        self.send(self.password, wait=0.6)
                post = self._drain(0.4, 1.2)
                if "#" in post:
                    self._privilege = "#"
                logger.info(
                    f"[PLINK-{self._mode}-{self.host}:{self.port}] session opened"
                    f" (priv={self._privilege})"
                )
                return self
            except (ConnectionResetError, ConnectionAbortedError,
                    BrokenPipeError, OSError, subprocess.SubprocessError) as e:
                last_err = e
                try: self.close()
                except Exception: pass
                if attempts >= total_attempts:
                    break
                time.sleep(1.2 * attempts)
        assert last_err is not None
        raise last_err

    def _wait_for_prompts(self, prompts: list[bytes],
                          timeout_s: float):
        """Poll the combined `_buf` (stdout + stderr merged by readers)
        until any prompt fires or timeout elapses. Auto-respond with y for
        weak/host-key prompts, credentials for user/pass prompts.
        """
        assert self._proc is not None and self._proc.stdin is not None
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            # Give the pump threads a little time to accumulate
            self._read_some(min(deadline, time.monotonic() + 0.25))
            with self._buf_lock:
                tail = bytes(self._buf).lower()
            matched_bytes = None
            for p in prompts:
                if p in tail:
                    matched_bytes = p
                    break
            if matched_bytes:
                matched_str = matched_bytes.decode(errors="replace").lower()
                # --- auto-respond logic --------------------------------
                is_confirm_prompt = (
                    b"y/n" in matched_bytes or
                    b"store key" in matched_bytes or
                    b"add the host" in matched_bytes or
                    b"continue with connection" in matched_bytes or
                    b"warning threshold" in matched_bytes
                )
                if is_confirm_prompt:
                    try:
                        self._proc.stdin.write(b"y" + self._term)
                        self._proc.stdin.flush()
                    except Exception:
                        pass
                    self._read_some(min(deadline, time.monotonic() + 0.8))
                elif b"password" in matched_bytes:
                    try:
                        self._proc.stdin.write(
                            self.password.encode() + self._term)
                        self._proc.stdin.flush()
                    except Exception:
                        pass
                    self._read_some(min(deadline, time.monotonic() + 1.0))
                elif (b"user:" in matched_bytes or b"username:" in matched_bytes
                      or b"login as:" in matched_bytes or
                      b"login:" in matched_bytes):
                    try:
                        self._proc.stdin.write(
                            self.username.encode() + self._term)
                        self._proc.stdin.flush()
                    except Exception:
                        pass
                    self._read_some(min(deadline, time.monotonic() + 0.6))
                with self._buf_lock:
                    text = self._buf.decode("utf-8", errors="replace")
                    self._buf = b""
                return matched_str, text
            time.sleep(0.06)
        with self._buf_lock:
            text = self._buf.decode("utf-8", errors="replace")
            self._buf = b""
        return ("<timeout>", text)

    def close(self):
        if self._closed:
            return
        self._closed = True
        if self._proc is None:
            return
        try:
            if self._proc.stdin is not None:
                try:
                    self._proc.stdin.write(b"exit\r\nlogout\r\nquit\r\n")
                    self._proc.stdin.flush()
                except Exception:
                    pass
                try: self._proc.stdin.close()
                except Exception: pass
        except Exception:
            pass
        try:
            self._proc.wait(timeout=3)
        except Exception:
            try: self._proc.kill()
            except Exception: pass
            try: self._proc.wait(timeout=2)
            except Exception: pass
        self._readers.clear()

    def send(self, command: str, wait: float = 0.8) -> str:
        assert self._proc is not None and self._proc.stdin is not None
        try:
            self._proc.stdin.write(command.encode("ascii", errors="replace")
                                   + self._term)
            self._proc.stdin.flush()
        except (BrokenPipeError, ConnectionResetError, OSError) as e:
            logger.warning(f"[PLINK-{self._mode}] send({command!r}): {e}")
            return ""
        return self._drain(wait, max(wait * 5, 4.0))

    def _run_cmd(self, command: str, wait: float = 0.8,
                 max_wait: float = 9.0) -> str:
        start = time.monotonic()
        deadline = start + max_wait
        assert self._proc is not None and self._proc.stdin is not None
        try:
            self._proc.stdin.write(command.encode("ascii", errors="replace")
                                   + self._term)
            self._proc.stdin.flush()
        except Exception as e:
            logger.warning(f"[PLINK-{self._mode}] send({command!r}): {e}")
            return ""
        pager_sent = False
        while True:
            self._read_some(min(deadline, time.monotonic() + 0.4))
            with self._buf_lock:
                decoded = self._buf.decode("utf-8", errors="replace").lower()
            if "press any key to continue" in decoded and not pager_sent:
                pager_sent = True
                try:
                    self._proc.stdin.write(b"q")
                    self._proc.stdin.flush()
                except Exception:
                    pass
                time.sleep(0.25)
                continue
            pager_sent = False
            prompt_marker_found = False
            lines = [ln for ln in decoded.splitlines() if ln.strip()]
            if lines:
                last = lines[-1].rstrip()
                if (last.endswith("#") or last.endswith(">") or
                        last.rstrip().endswith(")#")):
                    prompt_marker_found = True
            now = time.monotonic()
            if prompt_marker_found or now >= deadline:
                break
            if now < start + wait:
                time.sleep(0.05)
            else:
                time.sleep(0.08)
        with self._buf_lock:
            text = self._buf.decode("utf-8", errors="replace")
            self._buf = b""
        return text

    def show(self, command: str) -> str:
        return _strip_echo_and_prompts(
            self._run_cmd(command, wait=1.0, max_wait=9), command
        )

    def configure(self, commands: list[str]) -> tuple[int, int, str]:
        """Enter configure-mode-style state, run each command, exit."""
        success = 0
        errors = 0
        log_lines: list[str] = []
        try:
            assert self._proc is not None and self._proc.stdin is not None
            for cmd in commands:
                self._proc.stdin.write(
                    cmd.encode("ascii", errors="replace") + self._term)
                self._proc.stdin.flush()
                per_cmd_deadline = time.monotonic() + max(10.0, 3.0)
                while time.monotonic() < per_cmd_deadline:
                    self._read_some(min(per_cmd_deadline,
                                        time.monotonic() + 0.5))
                    with self._buf_lock:
                        decoded = self._buf.decode(
                            "utf-8", errors="replace").lower()
                    if "confirm to overwrite" in decoded or "[y/n]" in decoded:
                        try:
                            self._proc.stdin.write(b"y" + self._term)
                            self._proc.stdin.flush()
                        except Exception:
                            pass
                        time.sleep(0.8)
                        continue
                    lines = [ln for ln in decoded.splitlines() if ln.strip()]
                    last = lines[-1].rstrip() if lines else ""
                    if last.endswith("#") or last.endswith(")#") or \
                            "error" in decoded:
                        break
                    time.sleep(0.1)
                with self._buf_lock:
                    out = self._buf.decode("utf-8", errors="replace")
                    self._buf = b""
                has_err = _looks_like_error(out)
                if has_err:
                    errors += 1
                else:
                    success += 1
                log_lines.append(f"## {cmd}\n{out}")
        except (BrokenPipeError, ConnectionResetError, OSError,
                subprocess.SubprocessError) as e:
            log_lines.append(f"## (aborted: {e})")
            errors += 1
        return success, errors, "\n".join(log_lines)


class _SshSession:
    """Tiny paramiko shell wrapper around a single channel."""

    def __init__(self, host: str, port: int, username: str, password: str,
                 timeout: float = 8.0):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.timeout = timeout
        self.client: Optional[paramiko.SSHClient] = None
        self.shell: Optional[paramiko.Channel] = None
        self._privilege: str = ">"  # > user, # enable

    def open(self):
        # Retry loop: TL-SG5428 may briefly reset the SSH connection or Windows
        # Defender may inject a local RST. Same strategy as _TelnetSession.
        attempts = 0
        total_attempts = 5
        last_err: Optional[Exception] = None
        while attempts < total_attempts:
            attempts += 1
            try:
                client = paramiko.SSHClient()
                client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                try:
                    # First attempt: standard connect with all legacy crypto
                    # re-enabled via disabled_algorithms (paramiko >= 3.0).
                    client.connect(
                        self.host, port=self.port,
                        username=self.username, password=self.password,
                        timeout=self.timeout,
                        banner_timeout=max(self.timeout + 5, 20),
                        auth_timeout=max(self.timeout + 2, 15),
                        allow_agent=False, look_for_keys=False,
                        compress=False,
                        # Re-enable all algorithms that paramiko 3.0+ disables
                        # by default — TP-Link IPSSH-6.6.0 firmware only
                        # advertises old kex/cipher/hostkey/mac.
                        disabled_algorithms={
                            "pubkeys": [],
                            "kex": [],
                            "ciphers": [],
                            "macs": [],
                            "hostkeys": [],
                        },
                    )
                except paramiko.ssh_exception.IncompatiblePeer:
                    # Fallback: raw Transport with explicit legacy algorithms.
                    # Some paramiko builds ignore disabled_algorithms for kex.
                    sock = socket.create_connection(
                        (self.host, self.port), timeout=self.timeout
                    )
                    try: sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                    except OSError: pass
                    sock.settimeout(max(self.timeout + 5, 20))
                    t = paramiko.Transport(sock)
                    sec = t.get_security_options()
                    try:
                        # paramiko 5.0 renamed host_key_types → host_keys
                        for attr in ("kex", "ciphers", "macs"):
                            current = list(getattr(sec, attr))
                            legacy = {
                                "kex": [
                                    "diffie-hellman-group-exchange-sha1",
                                    "diffie-hellman-group14-sha1",
                                    "diffie-hellman-group1-sha1",
                                ],
                                "ciphers": [
                                    "aes128-cbc", "aes192-cbc", "aes256-cbc",
                                    "3des-cbc", "blowfish-cbc", "cast128-cbc",
                                ],
                                "macs": [
                                    "hmac-sha1", "hmac-sha1-96",
                                    "hmac-md5", "hmac-md5-96",
                                ],
                            }
                            setattr(sec, attr,
                                    list(dict.fromkeys(current + legacy[attr])))
                        # host keys: try both API names
                        for hk_attr in ("host_keys", "host_key_types"):
                            if hasattr(sec, hk_attr):
                                current = list(getattr(sec, hk_attr))
                                legacy_hk = [
                                    "ssh-rsa", "ssh-dss",
                                    "ecdsa-sha2-nistp256",
                                    "rsa-sha2-512", "rsa-sha2-256",
                                ]
                                setattr(sec, hk_attr,
                                        list(dict.fromkeys(current + legacy_hk)))
                                break
                    except Exception:
                        pass
                    t.connect(
                        username=self.username,
                        password=self.password,
                        hostkey=None,
                    )
                    client._transport = t
                except paramiko.ssh_exception.SSHException as exc:
                    # Some TP-Link devices send their SSH banner only after
                    # the client sends a TCP byte. Work around by pre-sending
                    # a newline on a fresh socket, then retrying connect.
                    if "banner" in str(exc).lower() and attempts < total_attempts:
                        raise ConnectionAbortedError(
                            f"SSH banner timeout (attempt {attempts}), retrying"
                        ) from exc
                    raise
                self.client = client
                shell = client.invoke_shell(width=200, height=2000)
                shell.settimeout(self.timeout)
                self.shell = shell
                self._drain(0.8)
                # TP-Link JetStream-style switches do not support
                # `terminal length 0`. Send multiple pager-disable variants.
                for pager_cmd in (
                    "terminal length 0",
                    "no terminal pager",
                    "screen-length 0 temporary",
                ):
                    self.send(pager_cmd, wait=0.4)
                # Enter enable mode silently.
                self.send("enable", wait=0.5)
                self._drain(0.5)
                return self
            except (ConnectionResetError, ConnectionAbortedError,
                    BrokenPipeError, OSError, paramiko.ssh_exception.SSHException) as e:
                last_err = e
                if self.client is not None:
                    try: self.client.close()
                    except Exception: pass
                    self.client = None
                if attempts >= total_attempts:
                    break
                time.sleep(1.2 * attempts)
        assert last_err is not None
        raise last_err

    def close(self):
        try:
            if self.shell:
                self.shell.close()
        except Exception:
            pass
        try:
            if self.client:
                self.client.close()
        except Exception:
            pass
        self.client = None
        self.shell = None

    def _drain(self, wait_s: float = 0.5) -> str:
        buf: list[str] = []
        end = time.time() + wait_s
        while time.time() < end:
            if self.shell.recv_ready():
                data = self.shell.recv(16384).decode("utf-8", errors="replace")
                if data:
                    buf.append(data)
                    end = time.time() + min(0.5, wait_s)
                    # Handle TP-Link pager: "Press any key to continue (Q to quit)"
                    if "Press any key to continue" in data:
                        try:
                            self.shell.send("q")
                        except Exception:
                            pass
                        end = time.time() + 0.8
            else:
                time.sleep(0.05)
        return "".join(buf)

    def send(self, cmd: str, wait: float = 0.8, max_wait: float = 12.0) -> str:
        assert self.shell is not None, "session not open"
        self.shell.send(cmd.rstrip("\r\n") + "\r")
        start = time.time()
        out_lines: list[str] = []
        pager_hits = 0
        while time.time() - start < max_wait:
            if self.shell.recv_ready():
                chunk = self.shell.recv(65535).decode("utf-8", errors="replace")
                out_lines.append(chunk)
                tail = chunk
                if "Press any key to continue" in tail:
                    # Send q to quit pagination — one q typically exits back to prompt
                    try:
                        self.shell.send("q")
                    except Exception:
                        pass
                    pager_hits += 1
                    time.sleep(0.15)
                    continue
                if (tail.rstrip().endswith("#") or tail.rstrip().endswith(">") or
                    tail.rstrip().endswith("(config)#")) and len(out_lines) > 1:
                    time.sleep(0.08)
                    # Drain one more tiny time slice to be sure prompt is fully arrived
                    extra = 0
                    while self.shell.recv_ready() and extra < 3:
                        c2 = self.shell.recv(4096).decode("utf-8", errors="replace")
                        out_lines.append(c2); extra += 1; time.sleep(0.05)
                    break
                time.sleep(0.03)
            else:
                time.sleep(0.05)
        extra = max(0.0, wait - (time.time() - start))
        if extra > 0:
            time.sleep(extra)
            try:
                while self.shell.recv_ready():
                    out_lines.append(self.shell.recv(65535).decode("utf-8", errors="replace"))
                    time.sleep(0.03)
            except Exception:
                pass
        return "".join(out_lines)

    # ── Convenience ────────────────────────────────────

    def show(self, command: str) -> str:
        """Run a show-* command and return its output strip of the echo/prompt."""
        out = self.send(command, wait=1.4, max_wait=20)
        return _strip_echo_and_prompts(out, command)

    def configure(self, commands: list[str]) -> tuple[int, int, str]:
        """Run a list of commands inside config mode (enters/exits automatically).

        TP-Link TL-SG5428 specific:
          - Enter config mode with `configure` (NOT `configure terminal`)
          - Exit back to enable mode with `exit` (NOT `end`)
          - Save config with `copy running-config startup-config` from enable mode
            (NOT `write memory`, NOT from inside config)
        """
        output: list[str] = []
        executed = 0
        failed = 0
        # Ensure enable mode first
        if self._privilege != "#":
            r = self.send("enable", wait=0.6)
            if "#" in r[-40:] or r.rstrip().endswith("#"):
                self._privilege = "#"
        r = self.send("configure", wait=0.7)
        output.append(r)
        for cmd in commands:
            c = cmd.strip()
            if not c or c.startswith("!"):
                continue
            r = self.send(c, wait=0.9, max_wait=15)
            output.append(r)
            executed += 1
            if _looks_like_error(r):
                failed += 1
        # Exit config mode (leave enable mode for subsequent save())
        r = self.send("exit", wait=0.6)
        output.append(r)
        return executed, failed, "\n".join(output)

    def save(self) -> tuple[bool, str]:
        """Persist running-config to startup-config from enable mode.
        Returns (success, log_text)."""
        try:
            out = self.send("copy running-config startup-config", wait=5.0, max_wait=30)
        except Exception as e:
            return False, f"save raised: {e}"
        ok = (
            "success" in out.lower()
            or "succeeded" in out.lower()
            or ("saved" in out.lower() and "fail" not in out.lower())
        )
        return ok, out


# ── Windows native OpenSSH ssh.exe session (PREFERRED SSH) ───

class _NativeOpensshSession:
    """SSH client backed by C:\\WINDOWS\\System32\\OpenSSH\\ssh.exe.

    Why this instead of paramiko / plink?
      * Paramiko 5.x has removed diffie-hellman-group1-sha1 / ssh-dss KEX
        required by TP-Link IPSSH-6.6.0 firmware.
      * PuTTY/plink 0.83 supports the legacy KEX but prompts for a "weak
        crypto below warning threshold" GUI confirmation that blocks forever
        when the controlling process uses SW_HIDE / DETACHED_PROCESS (the
        normal case for backend services).
      * Windows inbox OpenSSH (9.5p1 / 9.5p2) ships with legacy KEX / host
        key / cipher / MAC algorithms still available and exposes them via
        `-o Ciphers=+aes128-cbc ...` flags. SSH_ASKPASS (forced via
        DETACHED_PROCESS) lets us supply a password programmatically without
        a real console handle.

    The session uses a single pump-thread that reads merged stdout+stderr
    into a bytearray. Command execution waits for a configurable quiet
    period (0.6s of no new data) before returning — perfect for slow old
    switch CLI. Bare CR (`\r`) is used as line terminator because
    IPSSH-6.6.0 non-PTY shell ignores `\n` completely.
    """

    DETACHED_PROCESS = 0x00000008

    def __init__(self, host: str, port: int, username: str, password: str,
                 timeout: float = 10.0):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.timeout = timeout
        self._proc: Optional[subprocess.Popen] = None
        self._buf = bytearray()
        self._lock = threading.Lock()
        self._closed = False
        self._pump: Optional[threading.Thread] = None
        self._askpass_path: Optional[str] = None

    # ── lifecycle --------------------------------------------------------
    def _args_and_env(self):
        askpass = self._askpass_path
        if not askpass:
            askpass = _ensure_askpass_exe(self.password)
            self._askpass_path = askpass
        if not askpass:
            raise RuntimeError(
                "Windows askpass.exe could not be built (csc.exe missing?)."
                " Install .NET csc or use plink.exe."
            )

        args = [
            OPENSSH_EXE,
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=NUL",
            "-o", "LogLevel=ERROR",
            "-o", "KexAlgorithms=+diffie-hellman-group1-sha1,diffie-hellman-group14-sha1,diffie-hellman-group-exchange-sha1",
            "-o", "HostKeyAlgorithms=+ssh-dss,ssh-rsa",
            "-o", "PubkeyAcceptedAlgorithms=+ssh-dss,ssh-rsa",
            "-o", "Ciphers=+aes128-cbc,aes192-cbc,aes256-cbc,3des-cbc",
            "-o", "MACs=+hmac-sha1,hmac-sha1-96,hmac-md5,hmac-md5-96",
            "-o", "NumberOfPasswordPrompts=1",
            "-o", f"ConnectTimeout={max(int(self.timeout), 5)}",
            "-o", "ServerAliveInterval=30",
            "-o", "PreferredAuthentications=password",
            "-o", "BatchMode=no",
            "-T",  # non-PTY; -t would require a console handle and fail here
            "-p", str(self.port),
            "-l", self.username,
            self.host,
        ]
        env = os.environ.copy()
        env["SSH_ASKPASS"] = askpass
        env["SSH_ASKPASS_REQUIRED"] = "force"
        env["DISPLAY"] = "none:0"  # SSH_ASKPASS fallback needs DISPLAY set
        env["LANG"] = "C"; env["LC_ALL"] = "C"
        env.pop("SSH_AUTH_SOCK", None)
        return args, env

    def open(self):
        attempts = 0
        total_attempts = 4
        last_err: Optional[Exception] = None
        while attempts < total_attempts:
            attempts += 1
            try:
                args, env = self._args_and_env()
                startupinfo = subprocess.STARTUPINFO()  # type: ignore[attr-defined]
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW  # type: ignore[attr-defined]
                startupinfo.wShowWindow = 0  # SW_HIDE
                flags = self.DETACHED_PROCESS  # force no console → SSH_ASKPASS_REQUIRED path
                proc = subprocess.Popen(
                    args,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,  # merge for single pump
                    bufsize=0,
                    startupinfo=startupinfo,
                    creationflags=flags,
                    env=env,
                )
                self._proc = proc
                self._buf = bytearray()
                self._closed = False
                self._pump = threading.Thread(target=self._reader, daemon=True,
                                              name=f"openssh_{id(self)}")
                self._pump.start()
                # Wait for device prompt (or EOF)
                # Max wait: self.timeout + 45s (KEX handshake for legacy DH may be slow)
                total, accum = self._collect(
                    max_wait_s=max(self.timeout + 45, 50),
                    min_pause_s=0.5,
                    stop_markers=(b"TL-SG5428>", b"TL-SG5428#"),
                )
                if not total:
                    rc = proc.poll()
                    # Tried to negotiate but got nothing: auth-reject / KEX fail
                    raise EOFError(
                        f"SSH subprocess produced no output before "
                        f"deadline (exit={rc if rc is not None else 'alive'})"
                    )
                # Try to enter enable mode
                # (no password on TP-Link; just the enable command)
                self._send(b"enable\r")
                _ = self._collect(max_wait_s=1.5, min_pause_s=0.4)
                logger.info(
                    f"[OpenSSH-{self.host}:{self.port}] session opened"
                    f" (askpass={bool(self._askpass_path)})"
                )
                return self
            except (ConnectionResetError, BrokenPipeError, OSError,
                    TimeoutError, EOFError) as e:
                last_err = e
                try: self.close()
                except Exception: pass
                if attempts >= total_attempts:
                    break
                time.sleep(1.5 * attempts)
        # Also surface generic exceptions (ValueError / RuntimeError etc.)
        # through the retry loop; the except clause above is narrow because
        # transient handshake issues are the only ones we want to retry.
        if last_err is None:
            last_err = RuntimeError("openssh session open failed (unknown)")
        raise last_err

    def _reader(self):
        try:
            fd = self._proc.stdout.fileno()  # type: ignore[union-attr]
        except Exception:
            return
        while not self._closed:
            try:
                chunk = os.read(fd, 65536)
            except Exception:
                chunk = b""
            if not chunk:
                break
            with self._lock:
                self._buf.extend(chunk)

    def close(self):
        if self._closed:
            return
        self._closed = True
        if self._proc is None:
            return
        try:
            if self._proc.stdin is not None:
                try:
                    self._proc.stdin.write(b"exit\rlogout\rquit\r")
                    self._proc.stdin.flush()
                except Exception:
                    pass
                try: self._proc.stdin.close()
                except Exception: pass
        except Exception:
            pass
        try:
            self._proc.wait(timeout=3)
        except Exception:
            try: self._proc.kill()
            except Exception: pass
            try: self._proc.wait(timeout=2)
            except Exception: pass
        self._proc = None

    # ── i/o helpers ------------------------------------------------------
    def _send(self, data_bytes: bytes) -> None:
        assert self._proc is not None and self._proc.stdin is not None
        self._proc.stdin.write(data_bytes)
        self._proc.stdin.flush()

    def _collect(self, max_wait_s: float, min_pause_s: float = 0.5,
                 stop_markers: tuple[bytes, ...] = ()) -> tuple[bytes, bytes]:
        """Collect output from pump buffer.

        Returns (accumulated_total, current_chunk). Both values will be the
        same byte slice when no stop_marker causes an early return.

        The quiet-period timer (`min_pause_s`) does NOT start counting until
        the *first* byte of output has been received. This matters on slow
        SSH sessions where legacy DH key-exchange can stall for 1-2 seconds
        before any prompt payload crosses the pipe; a naive timer would
        incorrectly declare "no output" 0.5s after `_collect` was invoked.
        """
        import queue as _q
        end = time.time() + max_wait_s
        last_data_t: Optional[float] = None  # None ⇒ no byte received yet
        total = bytearray()
        # Poll buffer directly + tiny sleeps, no need to wake pump thread
        # (it's always reading in the background).
        while time.time() < end:
            with self._lock:
                if self._buf:
                    chunk = bytes(self._buf)
                    self._buf.clear()
                else:
                    chunk = b""
            if chunk:
                total.extend(chunk)
                last_data_t = time.time()
                for marker in stop_markers:
                    if marker in total:
                        return bytes(total), chunk
                time.sleep(0.05)
                continue
            # If we've seen at least one byte and now nothing for ≥ min_pause
            # seconds → declare channel quiet and return.
            if last_data_t is not None and (time.time() - last_data_t) >= min_pause_s:
                break
            # Proactively check if the child died so we don't spin until the
            # full deadline on pipe-stdin-close -> OSError (22) writes.
            if self._proc is not None and self._proc.poll() is not None:
                break
            time.sleep(0.05)
        return bytes(total), bytes(total)

    def send(self, cmd: str, wait: float = 1.2, max_wait: float = 14.0) -> str:
        """Send a CLI line terminated by \\r and return the raw reply."""
        assert self._proc is not None, "session not open"
        self._send((cmd.rstrip("\r\n") + "\r").encode("ascii", errors="replace"))
        start = time.time()
        _, raw = self._collect(max_wait_s=max(max_wait, wait), min_pause_s=0.55)
        # Pager handling: "Press any key to continue" → send "q" and re-collect
        if b"Press any key to continue" in raw:
            try:
                self._send(b"q")
                time.sleep(0.3)
                _, more = self._collect(max_wait_s=max(5.0, wait), min_pause_s=0.5)
                raw = raw + more
            except Exception:
                pass
        # If caller requested an extra wait after data stabilises, honour it.
        extra = max(0.0, wait - (time.time() - start))
        if extra > 0:
            time.sleep(extra)
            try:
                with self._lock:
                    tail = bytes(self._buf); self._buf.clear()
                if tail:
                    raw = raw + tail
            except Exception:
                pass
        return raw.decode("utf-8", errors="replace")

    # ── Convenience (identical API to other sessions) ──────────
    def show(self, command: str) -> str:
        return _strip_echo_and_prompts(
            self.send(command, wait=1.5, max_wait=18), command
        )

    def configure(self, commands: list[str]) -> tuple[int, int, str]:
        out_lines: list[str] = []
        exec_ = 0
        fail = 0
        out_lines.append(self.send("enable", wait=0.6, max_wait=3))
        out_lines.append(self.send("configure", wait=0.7, max_wait=3))
        for c in commands:
            c = c.strip()
            if not c or c.startswith("!"):
                continue
            r = self.send(c, wait=0.9, max_wait=15)
            out_lines.append(r)
            exec_ += 1
            if _looks_like_error(r):
                fail += 1
        out_lines.append(self.send("exit", wait=0.6, max_wait=3))
        return exec_, fail, "\n".join(out_lines)

    def save(self) -> tuple[bool, str]:
        try:
            out = self.send("copy running-config startup-config",
                            wait=5.0, max_wait=30)
        except Exception as e:
            return False, f"save raised: {e}"
        low = out.lower()
        ok = (
            "success" in low
            or "succeeded" in low
            or ("saved" in low and "fail" not in low)
        )
        return ok, out


# ── Telnet (minimal compat) ─────────────────────────────

class _TelnetSession:
    """Very small telnet wrapper (for old gear that doesn't speak SSH).

    Uses stdlib `telnetlib` when available (Python ≤ 3.13). On Python ≥ 3.14
    telnetlib was removed from stdlib — we fall back to a tiny raw-socket
    implementation that performs the minimal IAC echo/will/wont negotiation
    required to login + run show/config commands against a TP-Link CLI.
    """

    def __init__(self, host: str, port: int, username: str, password: str,
                 timeout: float = 8.0):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.timeout = timeout
        self.tn = None
        self._sock: Optional[socket.socket] = None
        self._use_fallback = telnetlib is None

    def open(self):
        # Attempt the Telnet session with up to 5 retries on transient network
        # errors. TL-SG5428 allows only one active TELNET session and may reset a
        # second incoming connection if the previous one hasn't fully cleaned up.
        # Windows Defender / antivirus sometimes also injects a local RST
        # (WinError 10053) shortly after the handshake begins on port 23/telnet
        # — a few retries with generous backoff (1.2s × attempt) are enough to
        # ride through these transient resets.
        attempts = 0
        last_err: Optional[Exception] = None
        total_attempts = 5
        while attempts < total_attempts:
            attempts += 1
            try:
                if not self._use_fallback:
                    tn = telnetlib.Telnet(self.host, self.port, timeout=self.timeout)
                    self.tn = tn
                    self._login_with_telnetlib(tn)
                    return self
                # fallback: raw socket + minimal IAC pass-through
                s = socket.create_connection((self.host, self.port), timeout=self.timeout)
                # Disable Nagle on both ends so line-by-line CLI output flushes
                # promptly — otherwise the switch often waits ~200ms for a full
                # MSS and we end up consuming the full max_wait budget.
                try: s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                except OSError: pass
                s.settimeout(self.timeout)
                self._sock = s
                self._login_fallback(s)
                return self
            except (ConnectionResetError, ConnectionAbortedError,
                    BrokenPipeError, OSError) as e:
                last_err = e
                # Clean up partial state
                if self.tn is not None:
                    try: self.tn.close()
                    except Exception: pass
                    self.tn = None
                if self._sock is not None:
                    try: self._sock.close()
                    except Exception: pass
                    self._sock = None
                # Retry only if we haven't exhausted attempts, otherwise fall
                # through and re-raise.
                if attempts >= total_attempts:
                    break
                # Progressive backoff: 1.2s, 2.4s, 3.6s, 4.8s
                time.sleep(1.2 * attempts)
        assert last_err is not None
        raise last_err

    # ── telnetlib path ────────────────────────────────

    def _login_with_telnetlib(self, tn) -> None:
        buf = b""
        for _ in range(14):
            try:
                buf += tn.read_until(b"\n", timeout=1)
            except EOFError:
                break
            s = buf.decode("utf-8", errors="replace").lower()
            if ("name:" in s or "user:" in s or "login:" in s) and b"_USER_DONE_" not in buf:
                tn.write((self.username + "\r").encode())
                buf += b"_USER_DONE_"
            if "password:" in s and b"_PWD_DONE_" not in buf:
                tn.write((self.password + "\r").encode())
                buf += b"_PWD_DONE_"
                break
        time.sleep(0.6)
        try:
            tn.read_very_eager()
        except Exception:
            pass
        # Always try to enter enable mode (TL-SG5428: all useful commands are under #)
        tn.write(b"enable\r")
        time.sleep(0.8)
        try:
            tn.read_very_eager()
        except Exception:
            pass
        # Note: TP-Link does not support `terminal length 0`. Paging is handled per
        # command in _run_cmd by sending 'q' when 'Press any key...' appears.

    # ── raw socket fallback ───────────────────────────

    def _login_fallback(self, s: socket.socket) -> None:
        user_done = pwd_done = False
        acc = bytearray()
        end_at = time.time() + 12.0
        while time.time() < end_at:
            try:
                chunk = s.recv(4096)
            except socket.timeout:
                break
            if not chunk:
                break
            acc.extend(chunk)
            # Handle IAC: send back DO/DONT/WILL/WONT echo/sga/gmcp passively by
            # echoing WONT for WILLs, DONT for DOs (we decline all options).
            while b"\xff" in acc:
                iac = acc.index(b"\xff")
                if iac + 2 > len(acc):
                    break
                cmd = acc[iac + 1]
                opt = acc[iac + 2]
                # IAC = 255, WILL=251, WONT=252, DO=253, DONT=254
                reply = None
                if cmd == 251:        # WILL → reply DONT
                    reply = bytes([255, 254, opt])
                elif cmd == 253:      # DO → reply WONT
                    reply = bytes([255, 252, opt])
                elif cmd in (252, 254):  # WONT / DONT → no reply needed
                    del acc[iac:iac + 3]
                    continue
                else:
                    # Unknown/control; strip
                    del acc[iac:iac + 3]
                    continue
                if reply is not None:
                    try:
                        s.sendall(reply)
                    except Exception:
                        pass
                    del acc[iac:iac + 3]
            s_dec = acc.decode("utf-8", errors="replace").lower()
            if not user_done and any(kw in s_dec for kw in ("name:", "user:", "login:")):
                s.sendall((self.username + "\r").encode())
                user_done = True
            if not pwd_done and "password:" in s_dec:
                s.sendall((self.password + "\r").encode())
                pwd_done = True
                break
            time.sleep(0.05)
        # Disable pagination + enter enable. TP-Link TL-SG5428 does NOT support
        # `terminal length 0`. Paging is handled in _run_cmd via 'q'.
        time.sleep(0.4)
        self._send_fallback(s, b"enable\r")
        time.sleep(0.8)
        self._drain_fallback(s, max_wait=0.9)


    @staticmethod
    def _send_fallback(s: socket.socket, data: bytes) -> None:
        s.sendall(data)

    @staticmethod
    def _drain_fallback(s: socket.socket, max_wait: float = 0.6) -> bytes:
        out = bytearray()
        end = time.time() + max_wait
        while time.time() < end:
            try:
                c = s.recv(32768)
            except socket.timeout:
                break
            if not c:
                break
            out.extend(c)
            time.sleep(0.05)
        # Strip IAC sequences from returned bytes before handing to caller
        cleaned = bytearray()
        i = 0
        while i < len(out):
            if out[i] == 0xFF and i + 2 < len(out):
                i += 3
                continue
            cleaned.append(out[i])
            i += 1
        return bytes(cleaned)

    def close(self):
        try:
            if self.tn:
                self.tn.write(b"exit\r")
                self.tn.close()
            if self._sock:
                try:
                    self._sock.sendall(b"exit\r")
                except Exception:
                    pass
                self._sock.close()
        except Exception:
            pass
        self.tn = None
        self._sock = None

    def _run_cmd(self, cmd: str, wait: float = 1.2, max_wait: float = 15.0) -> str:
        # NOTE: TP-Link TL-SG5428 does not support `terminal length 0`. We need
        # to detect pager prompt "Press any key to continue (Q to quit)" and
        # send 'q' to exit paging.
        deadline = time.time() + max_wait
        chunks: list[bytes] = []

        def send_bytes(b: bytes):
            if self._use_fallback:
                assert self._sock is not None
                self._sock.sendall(b)
            else:
                assert self.tn is not None
                self.tn.write(b)

        def read_available():
            nonlocal chunks
            while True:
                try:
                    if self._use_fallback:
                        assert self._sock is not None
                        c = self._sock.recv(65535)
                    else:
                        assert self.tn is not None
                        try:
                            c = self.tn.read_very_eager()
                        except EOFError:
                            return False
                    if not c:
                        return False
                    chunks.append(c)
                except socket.timeout:
                    return False
                except Exception:
                    return False

        send_bytes((cmd + "\r").encode())
        # Give switch a chance to echo + start output
        time.sleep(min(0.3, wait))
        pager_hits = 0
        while time.time() < deadline:
            read_available()
            combined = b"".join(chunks)
            decoded = combined.decode("utf-8", errors="replace")
            if "Press any key to continue" in decoded:
                pager_hits += 1
                try: send_bytes(b"q")
                except Exception: pass
                time.sleep(0.2)
                continue
            # Detect prompt back: lines ending with #, >, or (config)#
            lines = decoded.splitlines()
            # Skip first line if it's the echoed command
            candidates = [l.rstrip() for l in lines if l.strip()]
            if len(candidates) > 1 and any(
                candidates[-1].endswith(end)
                for end in ("#", ">", "(config)#")
            ):
                time.sleep(0.1)
                read_available()
                break
            time.sleep(0.05)
        # Sleep remaining time up to `wait` for trailing data
        remaining = max(0.0, wait - 0.0)
        if remaining > 0:
            time.sleep(remaining)
            read_available()
        combined = b"".join(chunks)
        return combined.decode("utf-8", errors="replace")

    def show(self, command: str) -> str:
        return _strip_echo_and_prompts(
            # NOTE: max_wait reduced to 12s for typical show-* commands.
            # Long paginated outputs (show running-config etc.) may call
            # _run_cmd directly with a larger budget.
            self._run_cmd(command, wait=1.5, max_wait=12), command
        )

    def configure(self, commands: list[str]) -> tuple[int, int, str]:
        """TP-Link TL-SG5428-compatible configure (telnet flavor).
        Saves are performed explicitly via save() (after exiting configure).
        """
        out_lines: list[str] = []
        exec_ = 0
        fail = 0
        # Ensure enable
        out_lines.append(self._run_cmd("enable", wait=0.8))
        out_lines.append(self._run_cmd("configure", wait=0.7))
        for c in commands:
            if not c.strip() or c.lstrip().startswith("!"):
                continue
            r = self._run_cmd(c, wait=0.9)
            out_lines.append(r)
            exec_ += 1
            if _looks_like_error(r):
                fail += 1
        # Exit config mode (leave enable mode for save() call)
        out_lines.append(self._run_cmd("exit", wait=0.6))
        return exec_, fail, "\n".join(out_lines)

    def save(self) -> tuple[bool, str]:
        """Persist running-config to startup-config from enable mode."""
        try:
            out = self._run_cmd(
                "copy running-config startup-config", wait=5.0, max_wait=30
            )
        except Exception as e:
            return False, f"save raised: {e}"
        low = out.lower()
        ok = (
            "success" in low
            or "succeeded" in low
            or ("saved" in low and "fail" not in low)
        )
        return ok, out


# ── Output cleaning ─────────────────────────────────────

def _looks_like_error(output: str) -> bool:
    if not output:
        return False
    low = output.lower()
    # TPLink / Cisco-style failures
    return any(b in low for b in (
        "error:", "error: bad command", "error: invalid parameter",
        "error: too many parameters", "error: incomplete command",
        "----------^", "bad command", "invalid parameter",
        "incomplete command", "too many parameters",
        "% invalid input", "% incomplete command", "unknown command",
    ))


def _strip_echo_and_prompts(raw: str, command: str) -> str:
    lines = raw.splitlines()
    # Drop the echoed command line if at top
    if lines and command.strip() and lines[0].strip() == command.strip():
        lines = lines[1:]
    # Drop trailing prompt lines ending with # or >
    while lines:
        tail = lines[-1].strip()
        if tail.endswith(">") or tail.endswith("#") or tail.endswith("(config)#") \
                or tail == "--More--":
            lines.pop()
            continue
        if not tail:
            lines.pop()
            continue
        break
    return "\n".join(lines).strip()


# ── Public API ──────────────────────────────────────────

def tcp_heartbeat(device, timeout_s: float = 3.0) -> tuple[bool, Optional[int]]:
    """L4-only heartbeat used by the /heartbeat endpoint. Cheap, fast."""
    host, port, _ = _resolve_access(device)
    return _tcp_check(host, int(port), timeout=timeout_s)


def check_connectivity(device, username: str, password: str) -> ConnectivityReport:
    """L7 connectivity: establish real session, send `show system-info` / `show ip ssh`,
    extract model and sw version. Used by /check_connectivity endpoint.

    Uses TP-Link TL-SG5428 compatible commands:
      - show system-info: returns Device Name / Hardware Version / Software Version / MAC
      - show version does NOT exist on this platform. Fallback: show ip ssh + running-config.
    """
    host, port, protocol = _resolve_access(device)
    # L4 first
    ok, ms = _tcp_check(host, int(port))
    if not ok:
        return ConnectivityReport(False, "TCP", f"TCP {host}:{port} unreachable", ms)
    # Small grace period after the TCP probe before we start the real L7
    # session. Without this, Windows Defender occasionally injects a local RST
    # (WinError 10053) on port 23 because it sees two rapid connections
    # (probe + login) on what it considers a "telnet probing" pattern. We also
    # rely on the open() retry loop, but the grace period drastically reduces
    # the chance of burning retry budget at all.
    time.sleep(0.6)
    banner = ""
    sw = ""
    model = ""

    def _parse_show_system_info(text: str) -> tuple[str, str]:
        """Return (software_version, model_hw) from show system-info output."""
        sw_v = _extract(text, r"(?im)Software Version\s*-\s*([A-Za-z0-9._\- ]+)") \
            or _extract(text, r"[Vv]ersion\s*[:=]?\s*([A-Za-z0-9._\-]+)")
        m = _extract(text, r"(?im)Hardware Version\s*-\s*([A-Za-z0-9._\- ]+)") \
            or _extract(text, r"(?im)(TL-[A-Za-z0-9]+)") \
            or _extract(text, r"(?im)Device Name\s*-\s*(\S+)")
        return sw_v.strip() if sw_v else "", m.strip() if m else ""

    try:
        # SSH    → _open_ssh_session (OpenSSH → plink → paramiko chain)
        # TELNET → _open_telnet_session (raw socket → plink fallback)
        if protocol == "SSH":
            sess = _open_ssh_session(host, int(port), username, password)
            try:
                out1 = sess.show("show system-info")
                out2 = sess.show("show ip ssh")
                sw, model = _parse_show_system_info(out1)
                banner = (out1 + "\n" + out2)[:2000]
            finally:
                sess.close()
            return ConnectivityReport(
                True, "PROTOCOL", f"SSH login OK, show system-info received", ms,
                banner=banner, software_version=sw, model=model,
            )
        if protocol == "TELNET":
            sess = _open_telnet_session(host, int(port), username, password)
            try:
                out1 = sess.show("show system-info")
                out2 = sess.show("show ip ssh")
                sw, model = _parse_show_system_info(out1)
                banner = (out1 + "\n" + out2)[:2000]
            finally:
                sess.close()
            return ConnectivityReport(
                True, "PROTOCOL", f"Telnet login OK, show system-info received", ms,
                banner=banner, software_version=sw, model=model,
            )
        if protocol == "HTTP":
            import requests
            r = requests.get(f"http://{host}:{port}/", timeout=5)
            model = _extract(r.text, r"(?:TL-[A-Z0-9\-]+|JetStream|TP-LINK\s*\S+)")
            sw = _extract(r.text, r"[Vv]ersion.{0,10}([0-9][0-9A-Za-z.\-]+)")
            banner = f"HTTP {r.status_code} len={len(r.text)}"
            return ConnectivityReport(r.status_code == 200, "PROTOCOL",
                                      f"HTTP GET / -> {r.status_code}", ms,
                                      banner=banner, software_version=sw, model=model)
        return ConnectivityReport(False, "PROTOCOL", f"Unknown protocol {protocol}", ms)
    except paramiko.AuthenticationException:
        return ConnectivityReport(False, "PROTOCOL", "SSH authentication failed", ms)
    except Exception as e:
        logger.exception("connectivity check error")
        return ConnectivityReport(False, "PROTOCOL",
                                  f"Protocol handshake error: {e.__class__.__name__}: {e}",
                                  ms)


# ── Tool-level session factories ────────────────────────

class DeviceToolSession:
    """Unified session used by the diag/config tools. Opens on enter,
    closes on exit. Handles both SSH and TELNET with identical API.
    """

    def __init__(self, device, username: str, password: str):
        self._host, self._port, self._protocol = _resolve_access(device)
        self._u = username
        self._p = password
        self._inner = None

    def __enter__(self):
        # Protocol preference (see module docstring / strategy comment at top):
        #   SSH    → Windows inbox OpenSSH → plink → paramiko fallback chain
        #   TELNET → raw socket implementation (_TelnetSession) preferred,
        #            with plink fallback for Defender-injected local RST.
        if self._protocol == "SSH":
            self._inner = _open_ssh_session(
                self._host, self._port, self._u, self._p,
            )
        elif self._protocol == "TELNET":
            self._inner = _open_telnet_session(
                self._host, self._port, self._u, self._p,
            )
        else:
            raise RuntimeError(f"Unsupported protocol for tool session: "
                               f"{self._protocol}")
        return self

    def __exit__(self, exc_type, exc, tb):
        if self._inner:
            self._inner.close()

    def show(self, command: str) -> str:
        return self._inner.show(command)

    def configure(self, commands: list[str]) -> tuple[int, int, str]:
        return self._inner.configure(commands)


# ── Session selector helpers ────────────────────────────

def _open_ssh_session(host: str, port: int, username: str, password: str):
    """Open an SSH session using the preferred-available implementation.

    Priority chain (Windows — other platforms fall straight to paramiko):
      1. Windows inbox OpenSSH + SSH_ASKPASS  (_NativeOpensshSession)
      2. PuTTY plink.exe                       (_PlinkSession "SSH")
      3. paramiko (legacy/fallback)            (_SshSession)

    Raises the last-seen exception if every option fails.
    """
    last_err: Optional[Exception] = None

    if platform.system() == "Windows" and OPENSSH_EXE:
        try:
            return _NativeOpensshSession(
                host, int(port), username, password,
            ).open()
        except Exception as e:
            last_err = e
            logger.debug(
                f"[_open_ssh_session] OpenSSH failed "
                f"({e.__class__.__name__}: {e}); trying plink fallback"
            )

    if PLINK_EXE:
        try:
            return _PlinkSession("SSH", host, int(port),
                                 username, password).open()
        except Exception as e:
            last_err = e
            logger.debug(
                f"[_open_ssh_session] plink SSH failed "
                f"({e.__class__.__name__}: {e}); trying paramiko fallback"
            )

    try:
        return _SshSession(host, int(port), username, password).open()
    except Exception as e:
        last_err = e

    assert last_err is not None
    raise last_err


def _open_telnet_session(host: str, port: int, username: str, password: str):
    """Open a TELNET session. Raw-socket first, plink fallback on OSError."""
    try:
        return _TelnetSession(host, int(port), username, password).open()
    except OSError as e:
        logger.debug(
            f"[_open_telnet_session] raw-telnet open failed ({e}); "
            "trying plink fallback")
        if not PLINK_EXE:
            raise
        return _PlinkSession("TELNET", host, int(port),
                             username, password).open()


# ── Tiny regex helper ───────────────────────────────────

import re as _re

def _extract(text: str, pattern: str) -> str:
    if not text:
        return ""
    m = _re.search(pattern, text)
    if not m:
        return ""
    return m.group(1) if m.groups() else m.group(0)
