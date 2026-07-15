"""
MOD-DS-003: SimulatorSSHServer — paramiko-based simulated SSH server.
@module device_simulator
@implements IFC-DS-003-01 ~ IFC-DS-003-04
@covers REQ-FUNC-106, REQ-FUNC-107, REQ-FUNC-108, REQ-FUNC-109, REQ-FUNC-110

Provides a process-in-thread SSH server that:
  - Listens on a configurable TCP port
  - Authenticates via username/password (check_auth_password)
  - Parses Cisco-like CLI commands and returns simulated output
  - Supports both interactive shell (SSH shell channel) and exec (SSH exec channel)
  - Maintains session state (configure terminal mode, current interface context)
"""

import logging
import os
import random
import socket
import threading
import time
from typing import Optional

import paramiko
from loguru import logger

from src.simulator.state_manager import DeviceStateManager

# ── Suppress paramiko transport debug noise ──
paramiko_logger = logging.getLogger("paramiko")
paramiko_logger.setLevel(logging.WARNING)

# ── RSA host key (persisted to data/simulator_host_key) ──
_HOST_KEY_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "simulator_host_key")
_host_key: Optional[paramiko.RSAKey] = None


def _get_host_key() -> paramiko.RSAKey:
    """Get or generate a persistent RSA host key (saved to data/simulator_host_key)."""
    global _host_key
    if _host_key is not None:
        return _host_key

    # Try loading existing key
    if os.path.exists(_HOST_KEY_PATH):
        try:
            _host_key = paramiko.RSAKey(filename=_HOST_KEY_PATH)
            logger.info(f"[SSHServer] Loaded persistent host key from {_HOST_KEY_PATH}")
            return _host_key
        except Exception as e:
            logger.warning(f"[SSHServer] Failed to load host key: {e}, generating new one")

    # Generate and save new key
    _host_key = paramiko.RSAKey.generate(2048)
    os.makedirs(os.path.dirname(_HOST_KEY_PATH), exist_ok=True)
    _host_key.write_private_key_file(_HOST_KEY_PATH)
    logger.info(f"[SSHServer] Generated and saved persistent host key to {_HOST_KEY_PATH}")
    return _host_key


# ────────────────────────────────────────────────────
# CLI Command Parser
# ────────────────────────────────────────────────────

class SimulatorCLI:
    """
    Cisco-like CLI command parser for the simulator.
    Parses text commands and returns formatted output strings.
    Supports: show, configure terminal, interface context, etc.
    """

    def __init__(self, state: DeviceStateManager, hostname: str = "Sim-SW-01"):
        self.state = state
        self.hostname = hostname
        # Per-session state
        self.in_config_mode = False
        self.current_interface: Optional[str] = None

    @property
    def prompt(self) -> str:
        """Return current CLI prompt."""
        if self.in_config_mode:
            if self.current_interface:
                return f"{self.hostname}(config-if)# "
            return f"{self.hostname}(config)# "
        return f"{self.hostname}> "

    def execute(self, command: str) -> str:
        """
        Parse and execute a single CLI command.
        Returns formatted output string (no trailing newline — caller adds).
        """
        cmd = command.strip()

        if not cmd:
            return ""

        # ── Context-sensitive commands ──
        if self.in_config_mode:
            return self._exec_config_mode(cmd)
        else:
            return self._exec_user_mode(cmd)

    def _exec_user_mode(self, cmd: str) -> str:
        """Handle commands in user EXEC / privileged EXEC mode (prompt > or #)."""
        lower = cmd.lower().strip()

        # ── show commands ──
        if lower.startswith("show "):
            return self._handle_show(lower[5:].strip())

        # ── configure terminal ──
        if lower in ("configure terminal", "configure t", "conf t"):
            self.in_config_mode = True
            self.current_interface = None
            return "Enter configuration commands, one per line. End with CNTL/Z."

        # ── Other common commands ──
        if lower in ("enable", "en"):
            return ""  # already in privileged mode

        if lower in ("exit", "quit"):
            return "Connection closed."

        if lower == "?":
            return self._help_user()

        # ── Unrecognized ──
        return f"% Unknown command: {cmd}"

    def _exec_config_mode(self, cmd: str) -> str:
        """Handle commands in configuration mode (config / config-if)."""
        lower = cmd.lower().strip()

        # ── Exit config mode ──
        if lower in ("exit", "end", "ctrl/z"):
            if self.current_interface:
                # Exit interface sub-mode back to config mode
                self.current_interface = None
                return ""
            self.in_config_mode = False
            self.current_interface = None
            return ""

        # ── Interface context ──
        if lower.startswith("interface "):
            iface = lower[10:].strip()
            port = self.state.get_port(iface)
            if port is None:
                return f"% Invalid interface: {iface}"
            self.current_interface = iface
            return ""

        # ── In interface sub-mode ──
        if self.current_interface:
            return self._exec_interface_mode(cmd)

        # ── Global config commands ──
        if lower.startswith("hostname "):
            self.hostname = lower[9:].strip()
            return ""

        if lower.startswith("vlan "):
            return ""  # accept but no-op for simplicity

        if lower == "?":
            return self._help_config()

        return f"% Invalid input detected at '^' marker."

    def _exec_interface_mode(self, cmd: str) -> str:
        """Handle commands in interface sub-mode (config-if)."""
        lower = cmd.lower().strip()
        iface = self.current_interface

        if lower == "shutdown":
            ok, msg = self.state.configure_port(iface, "shutdown")
            return msg

        if lower == "no shutdown":
            ok, msg = self.state.configure_port(iface, "no-shutdown")
            return msg

        if lower.startswith("switchport access vlan "):
            vlan = lower[22:].strip()
            ok, msg = self.state.configure_port(iface, "set-vlan", vlan)
            return msg

        if lower.startswith("switchport mode "):
            return ""  # accept but no-op

        if lower.startswith("description "):
            desc = lower[12:].strip()
            ok, msg = self.state.configure_port(iface, "set-description", desc)
            return msg

        if lower in ("switchport port-security", "no switchport port-security"):
            return ""  # accept

        if lower == "?":
            return (
                "  shutdown              Disable interface\n"
                "  no shutdown           Enable interface\n"
                "  switchport access vlan <1-4094>  Set access VLAN\n"
                "  switchport mode access Set access mode\n"
                "  description TEXT      Set interface description\n"
                "  exit                  Exit to config mode\n"
            )

        return f"% Invalid input detected at '^' marker."

    # ── show command handlers ────────────────────────────

    def _handle_show(self, subcmd: str) -> str:
        """Route show sub-commands to handlers."""
        lower = subcmd.lower().strip()

        if lower in ("interface status", "interfaces status"):
            return self._show_interface_status()

        if lower.startswith("interface "):
            iface = lower[10:].strip().split()[0]  # handle "show interface Gi0/1 detail"
            return self._show_interface_detail(iface)

        if lower in ("processes cpu", "process cpu", "proc cpu"):
            return self._show_cpu()

        if lower in ("processes cpu history", "process cpu history"):
            return self._show_cpu_history()

        if lower in ("memory", "mem"):
            return self._show_memory()

        if lower in ("io", "io status"):
            return self._show_io()

        if lower in ("mac address-table", "mac address", "mac-address-table"):
            return self._show_mac_table()

        if lower in ("running-config", "running config", "run"):
            return self.state.get_running_config()

        if lower in ("logging", "log"):
            return self._show_logging()

        if lower in ("version", "ver"):
            return (
                "Cisco IOS Software, Simulator Version 17.9.0 (DEMO)\n"
                f"Copyright (c) 2026 NetworkAgentDemo\n"
                f"Compiled {time.strftime('%d-%b-%y %H:%M')}\n"
                f"ROM: Bootstrap program is SimIOS\n"
                f"{self.hostname} uptime is {random_uptime()}\n"
                f"System returned to ROM by power-on\n"
                f"System image file is 'flash:simios.bin'\n"
                f"Last reload reason: power-on\n"
            )

        if lower == "?" or lower == "":
            return self._help_show()

        # Generic fallback
        return f"% Invalid input detected at '^' marker: {subcmd}"

    def _show_interface_status(self) -> str:
        """Generate 'show interface status' output."""
        ports = self.state.get_all_ports()
        lines = [
            "Port      Name          Status       Vlan  Duplex  Speed  Type",
        ]
        for p in sorted(ports, key=lambda x: x.name):
            eff = p.effective_status()
            status_display = eff if eff != "administratively down" else "admin down"
            # Align columns
            port_col = f"{p.name:<10}"
            name_col = f"{p.description[:12]:<14}" if p.description else f"{'':<14}"
            status_col = f"{status_display:<12}"
            vlan_col = f"{p.vlan:<5}"
            dup_col = f"{p.duplex if p.enabled else 'Auto':<7}"
            speed_col = f"{p.speed if p.enabled else 'Auto':<6}"
            type_col = p.port_type
            lines.append(f"{port_col}{name_col}{status_col}{vlan_col}{dup_col}{speed_col}{type_col}")
        return "\n".join(lines)

    def _show_interface_detail(self, iface: str) -> str:
        """Generate detailed interface output."""
        port = self.state.get_port(iface)
        if port is None:
            return f"% Invalid interface: {iface}"

        detail = port.to_detail()
        eff = port.effective_status()
        is_up = eff == "up"
        line_proto = "up" if is_up else "down"
        link_status = f"is {eff}, line protocol is {line_proto}"

        return (
            f"{iface} {link_status}\n"
            f"  Hardware is Gigabit Ethernet, address is {detail['mac_address']} (bia {detail['mac_address']})\n"
            f"  Description: {port.description or 'N/A'}\n"
            f"  MTU {detail['mtu']} bytes, BW {detail['bandwidth_kbps']} Kbit/sec, DLY 10 usec,\n"
            f"     reliability 255/255, txload 1/255, rxload 1/255\n"
            f"  Encapsulation ARPA, loopback not set\n"
            f"  Keepalive set (10 sec)\n"
            f"  {detail['duplex']}-duplex, {detail['speed']}Mbps, media type is {port.port_type}\n"
            f"  input flow-control is off, output flow-control is unsupported\n"
            f"  ARP type: ARPA, ARP Timeout 04:00:00\n"
            f"  Last input never, output never, output hang never\n"
            f"  Last clearing of \"show interface\" counters never\n"
            f"  Input queue: 0/75/0/0 (size/max/drops/flushes); Total output drops: 0\n"
            f"  Queueing strategy: fifo\n"
            f"  Output queue: 0/40 (size/max)\n"
            f"  5 minute input rate {detail['input_rate_bps']} bits/sec, 0 packets/sec\n"
            f"  5 minute output rate {detail['output_rate_bps']} bits/sec, 0 packets/sec\n"
            f"     {detail['input_packets']} packets input, 0 bytes, 0 no buffer\n"
            f"     Received 0 broadcasts (0 multicasts)\n"
            f"     0 runts, 0 giants, 0 throttles\n"
            f"     {detail['input_errors']} input errors, 0 CRC, 0 frame, 0 overrun, 0 ignored\n"
            f"     0 watchdog, 0 multicast, 0 pause input\n"
            f"     0 input packets with dribble condition detected\n"
            f"     {detail['output_packets']} packets output, 0 bytes, 0 underruns\n"
            f"     {detail['output_errors']} output errors, 0 collisions, 0 interface resets\n"
            f"     0 unknown protocol drops\n"
            f"     0 babbles, 0 late collision, 0 deferred\n"
            f"     0 lost carrier, 0 no carrier, 0 pause output\n"
            f"     0 output buffer failures, 0 output buffers swapped out"
        )

    def _show_cpu(self) -> str:
        """Generate 'show processes cpu' output."""
        cpu = self.state.get_cpu()
        lines = [
            f"CPU utilization for five seconds: {cpu['cpu_5s']}%/5%; "
            f"one minute: {cpu['cpu_1m']}%; five minutes: {cpu['cpu_5m']}%",
            " PID Runtime(ms)     Invoked      uSecs   5Sec   1Min   5Min TTY Process",
        ]
        for p in cpu["processes"]:
            runtime = random.randint(100, 500000)
            invoked = random.randint(1000, 2000000)
            usecs = random.randint(100, 500)
            lines.append(
                f" {p['pid']:<4} {runtime:<13} {invoked:<12} {usecs:<7} "
                f"{p['cpu_5s']:.2f}% {p['cpu_1m']:.2f}% {p['cpu_5m']:.2f}% "
                f"  0 {p['name']}"
            )
        return "\n".join(lines)

    def _show_cpu_history(self) -> str:
        """Generate ASCII CPU history chart."""
        return (
            " CPU%  per second (last 60 seconds)\n"
            " 100 |\n"
            f"  {int(self.state.get_cpu()['cpu_5s']):2d} |"
            + "#" * min(50, int(self.state.get_cpu()['cpu_5s']))
            + "\n     +----------------------------------------------------\n"
            "       0    5    0    5    0    5    0    5    0    5    0\n"
            "               10   20   30   40   50   60 seconds"
        )

    def _show_memory(self) -> str:
        """Generate 'show memory' output."""
        mem = self.state.get_memory_io()
        return (
            f"                Head    Total(b)     Used(b)     Free(b)   Lowest(b)  Largest(b)\n"
            f"Processor  {hex(0x1A000000)}   {mem['memory_total_mb'] * 1024 * 1024}   "
            f"{int(mem['memory_used_mb']) * 1024 * 1024}   {int(mem['memory_free_mb']) * 1024 * 1024}   "
            f"{int(mem['memory_free_mb'] * 0.8) * 1024 * 1024}   {int(mem['memory_free_mb']) * 1024 * 1024}\n"
            f"\n"
            f"Memory Summary:\n"
            f"  Total: {mem['memory_total_mb']} MB\n"
            f"  Used:  {mem['memory_used_mb']} MB ({mem['memory_usage_pct']}%)\n"
            f"  Free:  {mem['memory_free_mb']} MB ({100 - mem['memory_usage_pct']:.1f}%)"
        )

    def _show_io(self) -> str:
        """Generate 'show io' output."""
        mem = self.state.get_memory_io()
        return (
            f"IO Statistics:\n"
            f"  Read rate:  {mem['io_read_kbps']:.1f} KB/s\n"
            f"  Write rate: {mem['io_write_kbps']:.1f} KB/s\n"
            f"  Read ops:   {random.randint(100, 9999)}\n"
            f"  Write ops:  {random.randint(100, 9999)}\n"
            f"  Queue depth: {random.randint(0, 4)}"
        )

    def _show_mac_table(self) -> str:
        """Generate 'show mac address-table' output."""
        ports = self.state.get_up_ports()
        if not ports:
            return "Mac Address Table\n-------------------------------------------\nNo entries found."

        lines = [
            "Mac Address Table",
            "-------------------------------------------",
            "Vlan    Mac Address       Type        Ports",
            "----    -----------       --------    -----",
        ]
        for i, port in enumerate(ports[:10]):  # max 10 entries
            mac = port.mac_address
            vlan = port.vlan
            entry_type = "DYNAMIC" if i % 3 != 0 else "STATIC"
            lines.append(f"   {vlan:<4} {mac:<18} {entry_type:<11} {port.name}")
        lines.append(f"Total Mac Addresses for this criterion: {len(ports[:10])}")
        return "\n".join(lines)

    def _show_logging(self) -> str:
        """Generate 'show logging' output."""
        return (
            "Syslog logging: enabled\n"
            "Console logging: level debugging\n"
            "Monitor logging: level informational\n"
            "Buffer logging: level debugging\n"
            "Trap logging: level informational\n"
            "\n"
            "Log Buffer (4096 bytes):\n"
            f"{time.strftime('%b %d %H:%M:%S')}: %SYS-5-CONFIG_I: "
            f"Configured from console by admin on vty0\n"
            f"{time.strftime('%b %d %H:%M:%S')}: %LINEPROTO-5-UPDOWN: "
            f"Line protocol on Interface GigabitEthernet0/2, changed state to down\n"
        )

    # ── Help texts ────────────────────────────────────────

    def _help_user(self) -> str:
        return (
            "Exec commands:\n"
            "  configure terminal  Enter configuration mode\n"
            "  enable              Turn on privileged commands\n"
            "  exit                Exit from the EXEC\n"
            "  show                Show running system information\n"
            "    show interface status       Display interface status\n"
            "    show interface <iface>      Display interface details\n"
            "    show processes cpu          Display CPU utilization\n"
            "    show processes cpu history  Display CPU history\n"
            "    show memory                 Display memory statistics\n"
            "    show io                     Display IO statistics\n"
            "    show mac address-table      Display MAC address table\n"
            "    show running-config         Display current configuration\n"
            "    show logging                Display syslog messages\n"
            "    show version                Display system version\n"
        )

    def _help_config(self) -> str:
        return (
            "Configure commands:\n"
            "  interface <iface>   Enter interface configuration mode\n"
            "  hostname <name>     Set system hostname\n"
            "  exit                Exit to exec mode\n"
            "  end                 Exit to exec mode\n"
        )

    def _help_show(self) -> str:
        return (
            "  interface status         Display interface status\n"
            "  interface <iface>        Display interface details\n"
            "  processes cpu            Display CPU utilization\n"
            "  processes cpu history    Display CPU history\n"
            "  memory                   Display memory statistics\n"
            "  io                       Display IO statistics\n"
            "  mac address-table        Display MAC address table\n"
            "  running-config           Display current configuration\n"
            "  logging                  Display syslog messages\n"
            "  version                  Display system version\n"
        )


def random_uptime() -> str:
    """Generate a random uptime string."""
    days = random.randint(0, 30)
    hours = random.randint(0, 23)
    minutes = random.randint(0, 59)
    return f"{days} days, {hours} hours, {minutes} minutes"


# ────────────────────────────────────────────────────
# paramiko ServerInterface
# ────────────────────────────────────────────────────

class _SimulatorServerInterface(paramiko.ServerInterface):
    """
    paramiko ServerInterface implementation for the simulator.
    Handles authentication and channel requests.
    """

    def __init__(self, username: str, password: str, state: DeviceStateManager):
        self._expected_username = username
        self._expected_password = password
        self._state = state
        self._cli: Optional[SimulatorCLI] = None

    def check_auth_password(self, username: str, password: str) -> int:
        """IFC-DS-003-02: Authenticate via username/password."""
        if username == self._expected_username and password == self._expected_password:
            logger.info(f"[SSHServer] Auth SUCCESS: user='{username}'")
            return paramiko.AUTH_SUCCESSFUL
        logger.warning(f"[SSHServer] Auth FAILED: user='{username}'")
        return paramiko.AUTH_FAILED

    def check_channel_request(self, kind: str, chanid: int) -> int:
        """IFC-DS-003-03: Accept session channel requests."""
        if kind == "session":
            return paramiko.OPEN_SUCCEEDED
        return paramiko.OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED

    def check_channel_shell_request(self, channel: paramiko.Channel) -> bool:
        """IFC-DS-003-04: Handle interactive shell session."""
        self._cli = SimulatorCLI(self._state, "Sim-SW-01")
        threading.Thread(
            target=self._shell_loop,
            args=(channel,),
            daemon=True,
            name=f"ssh-shell-{id(channel)}",
        ).start()
        return True

    def check_channel_exec_request(self, channel: paramiko.Channel, command: bytes) -> bool:
        """Handle exec channel (single command execution)."""
        self._cli = SimulatorCLI(self._state, "Sim-SW-01")
        try:
            cmd = command.decode("utf-8", errors="replace")
            output = self._cli.execute(cmd)
            channel.send(output + "\r\n" if output else "")
        except Exception as e:
            logger.error(f"[SSHServer] Exec error: {e}")
            channel.send_stderr(f"% Error: {e}\r\n".encode())
        channel.send_exit_status(0)
        # ★ FIX: Use shutdown_write() instead of close() so that buffered
        # send data is flushed before the channel is torn down.  close() from
        # the transport thread can race with the client's stdout reads in
        # paramiko exec_command(), causing "SSHException: Channel closed."
        channel.shutdown_write()
        return True

    def _shell_loop(self, channel: paramiko.Channel) -> None:
        """Interactive shell read-eval-print loop."""
        try:
            channel.send(f"\r\nWelcome to {self._state.device_name} Simulator\r\n".encode())
            channel.send(self._cli.prompt.encode())

            buf = b""
            while not channel.closed:
                try:
                    data = channel.recv(1024)
                    if not data:
                        break
                except Exception:
                    break

                for byte in data:
                    ch = bytes([byte])
                    if ch == b"\r":
                        # Execute command
                        channel.send(b"\r\n")
                        cmd = buf.decode("utf-8", errors="replace").strip()
                        buf = b""

                        if cmd.lower() in ("exit", "quit"):
                            channel.send(b"Connection closed.\r\n")
                            channel.close()
                            return

                        try:
                            output = self._cli.execute(cmd)
                            if output:
                                channel.send((output + "\r\n").encode())
                        except Exception as e:
                            channel.send(f"% Error: {e}\r\n".encode())
                            logger.error(f"[SSHServer] Shell error: {e}")

                        channel.send(self._cli.prompt.encode())

                    elif ch == b"\n":
                        # Also execute on newline (some clients send only \n)
                        if buf.strip():
                            channel.send(b"\r\n")
                            cmd = buf.decode("utf-8", errors="replace").strip()
                            buf = b""

                            if cmd.lower() in ("exit", "quit"):
                                channel.send(b"Connection closed.\r\n")
                                channel.close()
                                return

                            try:
                                output = self._cli.execute(cmd)
                                if output:
                                    channel.send((output + "\r\n").encode())
                            except Exception as e:
                                channel.send(f"% Error: {e}\r\n".encode())
                                logger.error(f"[SSHServer] Shell error: {e}")

                            channel.send(self._cli.prompt.encode())

                    elif ch == b"\x08" or ch == b"\x7f":
                        # Backspace
                        if buf:
                            buf = buf[:-1]
                            channel.send(b"\x08 \x08")

                    elif ch == b"\x03":
                        # Ctrl+C — clear buffer
                        buf = b""
                        channel.send(b"^C\r\n")
                        channel.send(self._cli.prompt.encode())

                    else:
                        # Echo printable characters
                        if 32 <= byte[0] < 127:
                            buf += ch
                            channel.send(ch)
        except Exception as e:
            logger.error(f"[SSHServer] Shell loop error: {e}")
        finally:
            try:
                if not channel.closed:
                    channel.close()
            except Exception:
                pass


# ────────────────────────────────────────────────────
# Simulator SSH Server (public API)
# ────────────────────────────────────────────────────

class SimulatorSSHServer:
    """
    IFC-DS-003-01: Process-in-thread SSH server for a single simulator device.

    Usage:
        server = SimulatorSSHServer(state_manager)
        server.start(host="0.0.0.0", port=2222, username="admin", password="switch123")
        server.stop()
        server.is_running() → bool
    """

    def __init__(
        self,
        state_manager: DeviceStateManager,
        max_connections: int = 5,
        command_timeout: float = 5.0,
    ):
        self._state = state_manager
        self._max_connections = max_connections
        self._command_timeout = command_timeout
        self._socket: Optional[socket.socket] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._host: str = ""
        self._port: int = 0
        self._username: str = ""
        self._password: str = ""
        self._active_channels: list[paramiko.Channel] = []

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def host(self) -> str:
        return self._host

    @property
    def port(self) -> int:
        return self._port

    def start(self, host: str, port: int, username: str, password: str) -> None:
        """
        Start the SSH server on the given host:port.

        Raises:
            OSError: if the port is already in use.
            RuntimeError: if already running.
        """
        if self._running:
            raise RuntimeError(f"SSH server already running on {self._host}:{self._port}")

        self._host = host
        self._port = port
        self._username = username
        self._password = password

        # Bind socket
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self._socket.bind((host, port))
        except OSError:
            self._socket.close()
            self._socket = None
            raise

        self._socket.listen(self._max_connections)
        self._running = True
        self._thread = threading.Thread(
            target=self._accept_loop,
            daemon=True,
            name=f"ssh-listener-{host}:{port}",
        )
        self._thread.start()
        logger.info(f"[SSHServer] Started on {host}:{port} (max {self._max_connections} connections)")

    def stop(self) -> None:
        """Stop the SSH server and release the port."""
        self._running = False

        # Close active channels
        for ch in list(self._active_channels):
            try:
                ch.close()
            except Exception:
                pass
        self._active_channels.clear()

        # Close listener socket
        if self._socket:
            try:
                self._socket.close()
            except Exception:
                pass
            self._socket = None

        # Wait for thread
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)

        logger.info(f"[SSHServer] Stopped on {self._host}:{self._port}")

    def _accept_loop(self) -> None:
        """Main accept loop running in a daemon thread."""
        while self._running and self._socket:
            try:
                self._socket.settimeout(1.0)
                client, addr = self._socket.accept()
            except socket.timeout:
                continue
            except Exception:
                if self._running:
                    logger.error(f"[SSHServer] Accept error")
                break

            if not self._running:
                try:
                    client.close()
                except Exception:
                    pass
                break

            # Limit concurrent connections
            active = [ch for ch in self._active_channels if not ch.closed]
            self._active_channels = active
            if len(active) >= self._max_connections:
                logger.warning(f"[SSHServer] Max connections ({self._max_connections}) reached, "
                               f"rejecting {addr}")
                try:
                    client.close()
                except Exception:
                    pass
                continue

            # Handle connection in a new daemon thread
            t = threading.Thread(
                target=self._handle_connection,
                args=(client, addr),
                daemon=True,
                name=f"ssh-conn-{addr[0]}:{addr[1]}",
            )
            t.start()

        logger.info(f"[SSHServer] Accept loop ended for {self._host}:{self._port}")

    def _handle_connection(self, client: socket.socket, addr: tuple) -> None:
        """Handle a single incoming SSH connection."""
        transport: Optional[paramiko.Transport] = None
        try:
            transport = paramiko.Transport(client)
            transport.add_server_key(_get_host_key())
            transport.set_keepalive(30)

            server_interface = _SimulatorServerInterface(
                username=self._username,
                password=self._password,
                state=self._state,
            )

            transport.start_server(server=server_interface)

            # Wait for channel (authentication + channel request)
            channel = transport.accept(timeout=self._command_timeout)
            if channel is None:
                logger.warning(f"[SSHServer] No channel from {addr} within {self._command_timeout}s")
                return

            self._active_channels.append(channel)

            # Wait for channel to close (shell/exec handled by ServerInterface callbacks)
            while channel.active and self._running:
                time.sleep(0.1)

        except paramiko.SSHException as e:
            logger.warning(f"[SSHServer] SSH error from {addr}: {e}")
        except Exception as e:
            logger.error(f"[SSHServer] Connection error from {addr}: {e}")
        finally:
            try:
                if transport:
                    transport.close()
            except Exception:
                pass
            try:
                client.close()
            except Exception:
                pass
