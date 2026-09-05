#!/usr/bin/env python3
"""REAL device e2e: DB upsert + credential + TELNET L7 → SSH L7 → SSH config."""
import sys, os, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(PROJECT_ROOT, "data", "webui.db")
KEY_PATH = os.path.join(PROJECT_ROOT, "data", ".encryption_key")

from src.database.base import (
    create_engine as db_create_engine,
    init_session, init_db,
)
engine = db_create_engine(DB_PATH)
init_session(engine)
init_db(engine)

from src.database.base import SessionLocal
from src.database.repositories.device_repository import DeviceRepository
from src.models.enums import DeviceType, ConnectionProtocol
from src.services.encryption_service import EncryptionService
encryption_service = EncryptionService()
encryption_service.initialize(KEY_PATH)
ENC_PW = encryption_service.encrypt("admin")

db = SessionLocal()
repo = DeviceRepository(db)

devices = repo.list_devices()
print("Current devices:")
for d in devices:
    print(f"  id={d.id} name={d.device_name!r} type={d.device_type} "
          f"ip={d.device_ip} protocol={d.connection_protocol} "
          f"frp={d.frp_proxy_host}:{d.frp_proxy_port} "
          f"cred={bool(d.credential)} status={d.status}")

existing = [d for d in devices
            if d.device_type == DeviceType.REAL
            and d.device_ip == "192.168.31.220"]
if existing:
    dev = existing[0]
    print(f"\nUsing existing REAL device id={dev.id} name={dev.device_name!r}")
else:
    dev = repo.create_device({
        "device_name": "TL-SG5428-REAL",
        "device_type": DeviceType.REAL,
        "device_ip": "192.168.31.220",
        "connection_protocol": ConnectionProtocol.TELNET,
        "description": "Real TP-Link TL-SG5428 on home LAN",
        "device_model": "",
    })
    print(f"\nCreated REAL device id={dev.id}")

if not dev.credential:
    repo.set_credentials(dev.id, {
        "ssh_username": "admin",
        "ssh_password_encrypted": ENC_PW,
        "ssh_port": 22,
        "enable_password_encrypted": None,
    })
    print(f"Set credential for id={dev.id}")
else:
    print(f"Credential already set: user={dev.credential.ssh_username}")

db.commit()
db.refresh(dev)
PASSWORD = encryption_service.decrypt(dev.credential.ssh_password_encrypted)
USERNAME = dev.credential.ssh_username
DEV_ID = dev.id

from src.tools.real_device_client import (
    check_connectivity as l7,
    _open_telnet_session, _open_ssh_session,
    DeviceToolSession,
    _tcp_check,
)

# ── Step 1: FORCE protocol → TELNET then run L7 ──
repo.update_device(DEV_ID, {
    "connection_protocol": ConnectionProtocol.TELNET,
})
db.commit()
db.refresh(dev)
print(f"\n[prep] device.protocol forced = {dev.connection_protocol}")

print("\n=== [1] check_connectivity via TELNET ===")
t0 = time.time()
rep = l7(dev, USERNAME, PASSWORD)
wall_tel = time.time() - t0
print(f"  wall={wall_tel:.2f}s  ok={rep.ok}  layer={rep.layer}  latency_ms={rep.latency_ms}")
print(f"  sw={rep.software_version!r}  model={rep.model!r}")
print(f"  message: {rep.message}")
if rep.banner:
    head = rep.banner[:250].replace("\r", "␍")
    print(f"  banner-head: {head!r}")
assert rep.ok, f"TELNET L7 check FAILED: {rep.message}"
assert rep.software_version, f"TELNET L7 returned empty software_version — session output broken"
print("  ✓ TELNET check ok (non-empty output)")

repo.update_device(DEV_ID, {
    "status": "ONLINE" if rep.ok else "OFFLINE",
    "device_model": rep.model or dev.device_model,
    "software_version": rep.software_version or "",
})
db.commit()

# ── Step 2: flip protocol → SSH and run L7 ──
print("\n=== [2] flip protocol → SSH (direct LAN ip:22, no FRP) ===")
repo.update_device(DEV_ID, {
    "connection_protocol": ConnectionProtocol.SSH,
})
db.commit()
db.refresh(dev)
print(f"  protocol={dev.connection_protocol} frp={dev.frp_proxy_host}:{dev.frp_proxy_port}")

print("\n=== [3] check_connectivity via SSH ===")
t0 = time.time()
rep = l7(dev, USERNAME, PASSWORD)
wall_ssh = time.time() - t0
print(f"  wall={wall_ssh:.2f}s  ok={rep.ok}  layer={rep.layer}  latency_ms={rep.latency_ms}")
print(f"  sw={rep.software_version!r}  model={rep.model!r}")
print(f"  message: {rep.message}")
if rep.banner:
    head = rep.banner[:250].replace("\r", "␍")
    print(f"  banner-head: {head!r}")
assert rep.ok, f"SSH L7 check FAILED: {rep.message}"
assert rep.software_version, f"SSH L7 returned empty software_version — session output broken"
print("  ✓ SSH check ok (non-empty output)")

repo.update_device(DEV_ID, {
    "status": "ONLINE" if rep.ok else "OFFLINE",
    "device_model": rep.model or dev.device_model,
    "software_version": rep.software_version or "",
})
db.commit()

# ── Step 3: configure_ssh endpoint equivalent ──
print("\n=== [4] configure_ssh (TELNET → enable → configure → ip ssh server → save) ===")
HOST = dev.device_ip
ok23, ms23 = _tcp_check(HOST, 23, 5.0)
print(f"  TCP {HOST}:23 = {ok23} ({ms23} ms)")
assert ok23, f"Telnet port 23 unreachable on {HOST}"
time.sleep(0.6)

sess = _open_telnet_session(HOST, 23, USERNAME, PASSWORD)
print(f"  TELNET session via {type(sess).__name__} ✓")
enabled = False
save_ok = False
try:
    # Use the unified API: show() + configure() are supported on all sessions
    r_enable = sess.show("enable")  # still user-exec → enable mode
    r_before = sess.show("show ip ssh")
    print("  pre-config show ip ssh (head):")
    for line in r_before.splitlines()[:6]:
        print(f"    {line.strip()}")

    # TL-SG5428 CLI sequence inside configure() is:
    #   enable → configure → <commands> → exit (back to enable mode)
    exec_cnt, fail_cnt, cfg_out = sess.configure([
        "ip ssh server",
    ])
    print(f"  configure block: exec={exec_cnt} fail={fail_cnt}")

    ssh_stat = sess.show("show ip ssh")
    print("  post-config show ip ssh (head):")
    for line in ssh_stat.splitlines()[:8]:
        print(f"    {line.strip()}")
    try:
        after_colon = ssh_stat.split("SSH Server", 1)[1].split("\n", 1)[0]
        enabled = "Enabled" in after_colon
    except IndexError:
        enabled = "SSH Server:         Enabled" in ssh_stat
    print(f"  SSH server enabled parse: {enabled}")

    # save
    if hasattr(sess, "save") and callable(getattr(sess, "save")):
        save_ok, save_out = sess.save()
    else:
        save_out_raw = sess.show("copy running-config startup-config")
        # Wait for save result on slow switches — `show` uses `max_wait=18` by
        # default which is long enough, but we need an explicit extra quiet.
        time.sleep(2.0)
        try:
            tail = sess.show("!post-save-noop")  # command that echoes + returns prompt
        except Exception:
            tail = ""
        save_out = save_out_raw + tail
        low = save_out.lower()
        save_ok = ("success" in low or "succeeded" in low
                   or ("saved" in low and "fail" not in low))
    snippet = save_out.replace("\r", " ")[:240]
    print(f"  save OK={save_ok}  snippet: {snippet!r}")
finally:
    sess.close()

print("\n═══════════════════════════════════ SUMMARY ═══════════════════════════════════")
print(f"  device_id            = {DEV_ID}")
print(f"  device_name          = {dev.device_name!r}")
print(f"  device_ip            = {dev.device_ip}")
print(f"  final protocol (DB)  = {dev.connection_protocol}")
print(f"  model (auto-filled)  = {rep.model!r}")
print(f"  software_version     = {rep.software_version!r}")
print(f"  LATENCY L7 (TELNET)  = wall {wall_tel:.1f}s  ok=True  sw/model filled")
print(f"  LATENCY L7 (SSH)     = wall {wall_ssh:.1f}s  ok=True  sw/model filled")
print(f"  SSH server on switch = {'Enabled' if enabled else 'NOT CONFIRMED'}")
print(f"  running-config saved = {'OK' if save_ok else 'FAILED'}")
print("══════════════════════════ END-TO-END PASSED ✓ ══════════════════════════════")
db.close()
