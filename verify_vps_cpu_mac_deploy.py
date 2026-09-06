"""Read-only verify: does production VPS run the CPU/MAC FIXABLE upgrade?

Checks (all read-only grep/ls/curl, no writes, no restart):
  1. node_handlers.py: CPU_HIGH/MAC_FLAPPING -> FixCapability.FIXABLE
  2. switch_config_tool.py: run_records(..., save=...) signature
  3. real_device_client.py: _enters_interface_mode helper present
  4. templates: tpl_real_cpu_dos_prevent.yaml + tpl_real_mac_port_security.yaml
  5. /health + service last-restart time

Auth: SSH key only (~/.ssh/vps_rsa_key). No secrets printed.
"""
import os, pathlib, sys, time

import paramiko

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

VPS = os.environ.get("VPS_HOST", "47.109.197.217")
USER = os.environ.get("VPS_USER", "root")
WS = "/opt/NetworkAgentDemo/project_workspace"


def _resolve_key():
    for name in ("vps_rsa_key", "vps_deploy_key", "id_ed25519"):
        p = pathlib.Path.home() / ".ssh" / name
        if p.exists():
            return p
    raise SystemExit("No authorized SSH private key found in ~/.ssh/")


def run(cli, cmd, timeout=60):
    print(f"\n$ {cmd}")
    stdin, stdout, stderr = cli.exec_command(cmd, timeout=timeout)
    ch = stdout.channel
    out, err = b"", b""
    end = time.time() + max(timeout, 20)
    while time.time() < end and not ch.exit_status_ready():
        if ch.recv_ready():
            out += ch.recv(65535)
        if ch.recv_stderr_ready():
            err += ch.recv_stderr(65535)
        time.sleep(0.05)
    while ch.recv_ready():
        out += ch.recv(65535)
    while ch.recv_stderr_ready():
        err += ch.recv_stderr(65535)
    o = out.decode("utf-8", errors="replace")
    e = err.decode("utf-8", errors="replace")
    if o.strip():
        print(o.rstrip())
    if e.strip():
        print("[stderr] " + e.rstrip())
    return o, e


def main():
    key = _resolve_key()
    cli = paramiko.SSHClient()
    cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    print(f"[ssh] {USER}@{VPS} key={key.name}")
    cli.connect(VPS, 22, USER, key_filename=str(key), timeout=15,
                banner_timeout=30, auth_timeout=20, allow_agent=False,
                look_for_keys=False)
    try:
        # 1. node_handlers capability
        run(cli, f"grep -n 'CPU_HIGH: FixCapability.FIXABLE\\|MAC_FLAPPING: FixCapability.FIXABLE\\|MAC_FLAPPING: FixCapability.DEGRADED' {WS}/src/orchestration/node_handlers.py || echo 'NOT_FOUND'")
        # 2. switch_config_tool save signature
        run(cli, f"grep -n 'def run_records' {WS}/src/tools/switch_config_tool.py")
        run(cli, f"grep -n 'save: bool = False\\|save=True' {WS}/src/tools/switch_config_tool.py || echo 'NOT_FOUND'")
        # 3. real_device_client interface-mode helper
        run(cli, f"grep -n '_enters_interface_mode' {WS}/src/tools/real_device_client.py | head -5 || echo 'NOT_FOUND'")
        # 4. templates
        run(cli, f"ls -la {WS}/resources/templates/tpl_real_cpu_dos_prevent.yaml {WS}/resources/templates/tpl_real_mac_port_security.yaml 2>&1")
        run(cli, f"grep -n 'ip dos-prevent' {WS}/resources/templates/tpl_real_cpu_dos_prevent.yaml")
        # 5. health + service restart time
        run(cli, "curl -s -m 8 http://localhost:8001/health")
        run(cli, "systemctl show networkagent --property=ActiveEnterTimestamp,ExecMainStartTimestamp")
        print("\n=== VERIFY DONE ===")
    finally:
        try:
            cli.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
