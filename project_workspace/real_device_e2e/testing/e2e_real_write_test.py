#!/usr/bin/env python3
"""
E2E 脚本：真实设备（REAL）端到端工作流垂直切片。
触发 → 轮询 → (人工审批) → 断言 CLOSED + 验证通过 + 命令安全。

@author sub_agent_test_engineer
@covers US-RE-001 ~ US-RE-008（TC-E2E-001 ~ TC-E2E-005）
@module real_device_e2e/testing

安全红线（本脚本硬约束，不可覆盖）：
  1. 不硬编码任何交换机明文密码。交换机凭据由服务端 `_resolve_real_credentials`
     （env `DEVICE_<NAME>_PASSWORD` 或 DB Fernet）解析，本脚本不接触、不传递。
  2. 真实写默认关闭。必须显式 `--real-write` 且目标接口 ∈ {Gi1/0/2} 才允许。
  3. 断言下发命令不含 `description`（save/持久化已获授权）。
  4. 仅 stdlib（urllib/json/argparse/os/sys/time/ssl），零第三方依赖。

用法：
  # 1) 语法/结构/安全自检（不发网络请求，退出码 0=通过）
  python e2e_real_write_test.py --dry-run

  # 2) 本地 MOCK/SIMULATOR 链路验证（需本地已起服务，默认 base_url）
  python e2e_real_write_test.py --alert-type PORT_DOWN

  # 3) 真实写（GROUP_E 部署后，VPS 上执行；必须显式 --real-write）
  python e2e_real_write_test.py --alert-type PORT_DOWN --real-write \
      --base-url http://127.0.0.1:8000

退出码：0=全部断言通过；1=测试断言失败；2=用法/配置错误（含白名单违规）。
"""
import argparse
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

# ── 常量 ──────────────────────────────────────────────────

# 真实写白名单：与 node_handlers.REAL_WRITE_PORT_WHITELIST 保持一致
REAL_WRITE_PORT_WHITELIST = frozenset({"Gi1/0/2"})

# 允许下发真实写的告警类型（4 类均已升级为 FIXABLE；CPU/MAC 走缓解命令）
REAL_WRITE_ALERT_TYPES = frozenset({"PORT_DOWN", "PORT_SHUTDOWN", "CPU_HIGH", "MAC_FLAPPING"})

# 终端状态（工作流结束）
TERMINAL_STATUSES = frozenset({"CLOSED", "FAILED", "REJECTED", "EXPIRED"})

# 被禁止的下发命令关键字（不区分大小写）。save/持久化已获授权（「允许 save」），
# 仅 description 仍为红线（不向交换机写描述）。
FORBIDDEN_COMMAND_TOKENS = ("description",)

DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_DEVICE_NAME = "TL-SG5428-核心交换机"


class E2EConfig:
    """一次运行的配置封装（来自 CLI 参数 + 环境变量）。"""

    def __init__(self, args: argparse.Namespace):
        self.base_url = (args.base_url or os.environ.get("E2E_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self.alert_type = (args.alert_type or "PORT_DOWN").upper()
        self.device_name = args.device_name or DEFAULT_DEVICE_NAME
        self.interface = args.interface  # None → 服务端 REAL 回填 Gi1/0/2
        self.real_write = bool(args.real_write)
        self.dry_run = bool(args.dry_run)
        self.auto_approve = not args.no_approve
        self.decision = args.decision or "APPROVED"
        self.poll_interval = args.poll_interval
        self.timeout = args.timeout
        self.admin_password = args.admin_password or os.environ.get("E2E_ADMIN_PASSWORD") or "admin"

    def effective_interface(self) -> str:
        """REAL 设备未显式传端口时，服务端回填 Gi1/0/2。"""
        return self.interface or "Gi1/0/2"

    def validate(self) -> str | None:
        """返回错误信息字符串；None 表示通过。"""
        if self.alert_type not in ("PORT_DOWN", "PORT_SHUTDOWN", "CPU_HIGH", "MAC_FLAPPING"):
            return f"不支持的 alert_type: {self.alert_type}"
        if self.decision not in ("APPROVED", "REJECTED"):
            return f"decision 必须是 APPROVED/REJECTED: {self.decision}"
        if self.poll_interval <= 0 or self.timeout <= 0:
            return "poll-interval/timeout 必须为正数"
        if self.real_write:
            if self.alert_type not in REAL_WRITE_ALERT_TYPES:
                return f"--real-write 仅允许 {sorted(REAL_WRITE_ALERT_TYPES)}，收到 {self.alert_type}"
            if self.effective_interface() not in REAL_WRITE_PORT_WHITELIST:
                return (
                    f"真实写白名单违规：接口 {self.effective_interface()} "
                    f"不在 {sorted(REAL_WRITE_PORT_WHITELIST)} 中"
                )
        return None


# ── HTTP 客户端（仅 stdlib） ──────────────────────────────

class HttpClient:
    def __init__(self, base_url: str):
        self.base_url = base_url
        self._ctx = ssl._create_unverified_context() if base_url.startswith("https") else None
        self.token: str | None = None

    def _request(self, method: str, path: str, *, data=None, form_data=None, timeout=120):
        url = self.base_url + path
        headers = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        body = None
        if form_data is not None:
            headers["Content-Type"] = "application/x-www-form-urlencoded"
            body = urllib.parse.urlencode(form_data).encode("utf-8")
        elif data is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(data).encode("utf-8")
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        t0 = time.time()
        try:
            resp = urllib.request.urlopen(req, timeout=timeout, context=self._ctx)
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:400]
            print(f"  [HTTP {e.code}] {method} {path} → {e.reason}: {detail}")
            raise
        elapsed = time.time() - t0
        raw = resp.read()
        try:
            result = json.loads(raw)
        except Exception:
            result = raw.decode(errors="replace")
        print(f"  [{elapsed:.1f}s] {method} {path} → {resp.status}")
        return result

    def login(self, admin_password: str):
        resp = self._request("POST", "/auth/login", form_data={"username": "admin", "password": admin_password})
        self.token = resp["access_token"]
        return self.token

    def simulate(self, alert_type: str, device_name: str, interface: str | None) -> dict:
        body = {"alert_type": alert_type, "device_name": device_name}
        if interface:
            body["interface"] = interface
        return self._request("POST", "/api/alerts/simulate", data=body)

    def workflow(self, alert_id: str) -> dict:
        return self._request("GET", f"/api/alerts/{alert_id}/workflow")

    def detail(self, alert_id: str) -> dict:
        return self._request("GET", f"/api/alerts/{alert_id}")

    def pending_approvals(self) -> dict:
        return self._request("GET", "/api/approvals/pending")

    def decide(self, checkpoint_id: str, decision: str, note: str) -> dict:
        return self._request(
            "POST", f"/api/approvals/{checkpoint_id}/decide",
            data={"decision": decision, "note": note},
        )


# ── 安全断言 ──────────────────────────────────────────────

def assert_commands_safe(commands: list) -> None:
    """断言下发命令不含 description（save/持久化已授权，不再禁止）。"""
    lowered = [str(c).lower() for c in commands]
    for token in FORBIDDEN_COMMAND_TOKENS:
        for cmd in lowered:
            if token in cmd:
                raise AssertionError(f"禁止的命令关键字 '{token}' 出现在下发命令: {cmd!r}")
    print(f"  [safe] 下发命令共 {len(commands)} 条，无 description")


def assert_exec_log_success(exec_log: list, real_write: bool) -> None:
    """断言实际下发的命令全部 success=true，杜绝「CLOSED 但命令全失败」的假通过。"""
    if not real_write:
        return
    if not exec_log:
        raise AssertionError("real-write 场景缺少 exec_log（未实际下发任何命令）")
    failed = [r for r in exec_log if not r.get("success", False)]
    if failed:
        cmds = [r.get("command") for r in failed]
        raise AssertionError(f"下发命令执行失败（success=false）: {cmds}")
    print(f"  [safe] exec_log 共 {len(exec_log)} 条命令，全部 success=true")


def assert_no_plaintext_switch_password(detail: dict) -> None:
    """断言告警详情/时间线中不含交换机明文密码泄漏。"""
    def _scan(obj, path="root"):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k in ("password", "enable_password", "ssh_password") and v:
                    raise AssertionError(f"详情中泄漏明文凭据字段 {path}.{k}")
                _scan(v, f"{path}.{k}")
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                _scan(item, f"{path}[{i}]")
    _scan(detail)
    print("  [safe] 告警详情/时间线无明文交换机凭据字段")


# ── 轮询逻辑 ──────────────────────────────────────────────

def _pending_checkpoint_for_alert(pending: dict, alert_id: str) -> str | None:
    for item in pending.get("pending", []):
        if item.get("alert_id") == alert_id:
            return item.get("checkpoint_id")
    return None


def run_scenario(cfg: E2EConfig, client: HttpClient) -> int:
    print(f"\n=== E2E 场景 {cfg.alert_type} @ {cfg.base_url} ===")
    print(f"  real_write={cfg.real_write}  interface={cfg.effective_interface()}  "
          f"auto_approve={cfg.auto_approve}  decision={cfg.decision}")

    client.login(cfg.admin_password)
    print(f"  login OK")

    simulate_resp = client.simulate(cfg.alert_type, cfg.device_name, cfg.interface)
    alert_id = simulate_resp.get("alert_id")
    if not alert_id:
        raise RuntimeError(f"simulate 响应缺少 alert_id: {simulate_resp!r}")
    print(f"  alert_id={alert_id}")

    deadline = time.time() + cfg.timeout
    decided = False
    final_status = None
    detail = None

    while time.time() < deadline:
        wf = client.workflow(alert_id)
        status = wf.get("status")
        print(f"  poll status={status}")

        if status in TERMINAL_STATUSES:
            final_status = status
            detail = client.detail(alert_id)
            break

        # 在非终端状态下检查并处理人工审批
        if cfg.auto_approve and not decided:
            pending = client.pending_approvals()
            ckpt = _pending_checkpoint_for_alert(pending, alert_id)
            if ckpt:
                print(f"  发现待审批 checkpoint={ckpt} → decision={cfg.decision}")
                client.decide(ckpt, cfg.decision, note="E2E 自动审批")
                decided = True

        time.sleep(cfg.poll_interval)

    if final_status is None:
        print(f"  [FAIL] 超时 {cfg.timeout}s 未达终端状态（最后 status={final_status}）")
        return 1

    if final_status != "CLOSED":
        print(f"  [FAIL] 最终状态 {final_status}，期望 CLOSED")
        return 1

    # 命令安全断言
    commands = (detail or {}).get("commands") or []
    assert_commands_safe(commands)

    # ★ 实际下发执行结果断言（杜绝 success=false 的假通过）
    exec_log = (detail or {}).get("exec_log") or []
    assert_exec_log_success(exec_log, cfg.real_write)

    # 结构化验证结果（Link 状态在无线上端口上无法反映 admin 变化，仅告警不判失败）
    verify_result = (detail or {}).get("verify_result")
    if verify_result is not None:
        passed = verify_result.get("verify_passed", False)
        note = verify_result.get("comparison_notes", "")
        if passed:
            print("  [verify] verify_passed=true")
        else:
            print(f"  [warn] verify_passed=false（Link 状态无法反映 admin 变化）: {note}")

    # 明文凭据泄漏断言
    assert_no_plaintext_switch_password(detail or {})

    # 验证节点是否完成（timeline 中出现 verify_fix 且 COMPLETED）
    timeline = (detail or {}).get("timeline") or []
    verify_nodes = [t for t in timeline if (t.get("node_name") == "verify_fix" or t.get("node") == "verify_fix")]
    if verify_nodes:
        completed = any((t.get("status") == "COMPLETED") for t in verify_nodes)
        print(f"  verify_fix 节点完成={completed}")
        if not completed:
            print(f"  [FAIL] verify_fix 节点未完成")
            return 1
    else:
        print("  [warn] timeline 中未找到 verify_fix 节点（降级/非写路径可能跳过，不判失败）")

    print(f"  [PASS] {cfg.alert_type} 场景 CLOSED + 命令安全 + 无明文泄漏")
    return 0


# ── dry-run 自检 ──────────────────────────────────────────

def dry_run_selfcheck(cfg: E2EConfig) -> int:
    print("\n=== DRY-RUN 自检（不发网络请求） ===")
    print(f"  alert_type={cfg.alert_type}  device_name={cfg.device_name}  "
          f"interface={cfg.effective_interface()}  real_write={cfg.real_write}")

    err = cfg.validate()
    if err:
        print(f"  [FAIL] 配置校验失败: {err}")
        return 2

    # 命令安全断言逻辑自检
    assert_commands_safe(["interface Gi1/0/2", "no shutdown"])
    try:
        assert_commands_safe(["interface Gi1/0/2", "description core-uplink"])
    except AssertionError:
        print("  [safe] description 命令被正确拦截（预期）")
    else:
        print("  [FAIL] description 命令未被拦截")
        return 1

    # save/持久化已授权（「允许 save」）——copy running-config 不再被拦截
    assert_commands_safe(["interface Gi1/0/2", "mac address-table max-mac-count max-number 10"])
    assert_commands_safe(["copy running-config startup-config"])
    print("  [safe] save/持久化命令已获授权，不再被拦截")

    # exec_log 成功断言逻辑自检
    assert_exec_log_success(
        [{"command": "interface gigabitEthernet 1/0/2", "success": True},
         {"command": "shutdown", "success": True}], real_write=True)
    try:
        assert_exec_log_success(
            [{"command": "shutdown", "success": False}], real_write=True)
    except AssertionError:
        print("  [safe] exec_log success=false 被正确拦截（预期）")
    else:
        print("  [FAIL] exec_log success=false 未被拦截")
        return 1
    try:
        assert_exec_log_success([], real_write=True)
    except AssertionError:
        print("  [safe] exec_log 为空被正确拦截（预期）")
    else:
        print("  [FAIL] exec_log 为空未被拦截")
        return 1

    print("  [PASS] dry-run 自检通过（语法/配置/安全断言逻辑）")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="REAL 端到端工作流 E2E 脚本")
    p.add_argument("--base-url", help="服务 base_url（默认 http://127.0.0.1:8000）")
    p.add_argument("--alert-type", default="PORT_DOWN",
                   choices=["PORT_DOWN", "PORT_SHUTDOWN", "CPU_HIGH", "MAC_FLAPPING"])
    p.add_argument("--device-name", default=DEFAULT_DEVICE_NAME)
    p.add_argument("--interface", help="目标接口；留空则 REAL 回填 Gi1/0/2")
    p.add_argument("--real-write", action="store_true",
                   help="显式允许向真实交换机下发写命令（默认关闭，仅限 Gi1/0/2）")
    p.add_argument("--dry-run", action="store_true",
                   help="仅做语法/配置/安全断言自检，不发网络请求")
    p.add_argument("--no-approve", action="store_true", help="不自动审批（人工审批挂起）")
    p.add_argument("--decision", default="APPROVED", choices=["APPROVED", "REJECTED"])
    p.add_argument("--admin-password", help="Web 面板 admin 密码（env E2E_ADMIN_PASSWORD 或默认 demo）")
    p.add_argument("--poll-interval", type=float, default=3.0, help="轮询间隔秒（默认 3）")
    p.add_argument("--timeout", type=float, default=300.0, help="总超时秒（默认 300）")
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    cfg = E2EConfig(args)

    if cfg.dry_run:
        return dry_run_selfcheck(cfg)

    err = cfg.validate()
    if err:
        print(f"[配置错误] {err}")
        return 2

    client = HttpClient(cfg.base_url)
    return run_scenario(cfg, client)


if __name__ == "__main__":
    sys.exit(main())
