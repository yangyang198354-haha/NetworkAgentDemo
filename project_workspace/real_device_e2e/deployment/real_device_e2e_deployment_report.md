<file_header>
  <project_id>NetworkAgentDemo</project_id>
  <module_id>real_device_e2e</module_id>
  <doc_type>deployment_report</doc_type>
  <file_name>real_device_e2e_deployment_report.md</file_name>
  <version>0.2.0</version>
  <status>DEPLOYED_E2E_BLOCKED</status>
  <author_agent>pm_orchestrator</author_agent>
  <created_at>2026-09-05T17:40:00Z</created_at>
  <last_updated>2026-09-05T19:00:00Z</last_updated>
  <invocation_id>inv-real-e2e-e-002</invocation_id>
  <input_source>GROUP_RE_E 部署执行 — 用户在会话内显式授权生产 VPS 47.109.197.217 的 SSH 部署 + 真实写 E2E</input_source>
</file_header>

# 真实设备（REAL）端到端工作流 — 部署执行结果报告（修订版）

## 1. 部署摘要

| 项 | 值 |
|----|----|
| 部署时间 | 2026-09-05 18:09 CST |
| 目标环境 | 生产 VPS 47.109.197.217（root，密钥认证） |
| 部署代码 | commit `2207351`（origin/master HEAD，已 push） |
| 部署方式 | `git fetch + reset --hard origin/master` + `py_compile` + `systemctl restart` |
| 部署结果 | **成功**（服务 active，`/health` healthy，版本 0.2.0） |
| 真实写 E2E | **已执行但 BLOCKED**（establish_ssh 节点失败，根因：交换机 SSH 不可达） |

## 2. 部署执行明细（DEPLOY-001 ~ 005）

| 步骤 | 描述 | 结果 |
|------|------|------|
| PRE-CHECK | 确认仓库布局 / systemd unit / main.py / 4 个目标文件 | PASS |
| BACKUP | `cp -a /opt/NetworkAgentDemo /opt/NetworkAgentDemo.backup.<ts>` | PASS |
| GIT-SYNC | `git fetch + reset --hard origin/master` → HEAD=`220735136f...` | PASS |
| PY-COMPILE | `py_compile src/orchestration/node_handlers.py src/api/alerts_router.py` | PASS |
| RESTART | `systemctl restart networkagent` → is-active=active | PASS |
| HEALTH | `curl http://localhost:8001/health` → `{"status":"healthy","version":"0.2.0"}` | PASS |

> 首次 health 校验曾出现 curl exit 7（connection refused），系**时序问题**：应用启动约需 7s（18:09:14 restart → 18:09:21 `Application startup complete`），脚本 `sleep 6` 后即 curl，恰好打在绑定完成前。诊断确认 8001 LISTEN、health healthy，非故障。

## 3. 真实写 E2E 执行结果（部署后）

| 场景 | alert_type | 期望 | 实际 | 退出码 |
|------|-----------|------|------|--------|
| TC-E2E-002 | PORT_SHUTDOWN（shutdown Gi1/0/2） | CLOSED | **FAILED @ establish_ssh** | 1 |
| TC-E2E-001 | PORT_DOWN（no shutdown Gi1/0/2） | CLOSED | **FAILED @ establish_ssh** | 1 |

**时间线**（两个场景一致）：

```
receive_alert   COMPLETED
parse_alert     COMPLETED
validate_alert  COMPLETED
get_device_info COMPLETED   ← 设备解析（REAL）+ 凭据解析（credential 表 Fernet）成功
establish_ssh   FAILED      ← 可达性校验失败（TCP 通，SSH banner 握手失败）
collect_diag    FAILED      ← 级联
analyze_root_cause FAILED   ← 级联
final_report    COMPLETED
```

## 4. 根因分析（establish_ssh 失败）

- `_resolve_access` 正确返回 FRP 代理 `127.0.0.1:6022`（device 3 `frp_proxy_host=127.0.0.1`、`frp_proxy_port=6022`）。
- 凭据解析成功（`get_device_info` COMPLETED，`credential` 表 `ssh_password_encrypted` + Fernet 解密正常）。
- **journalctl 警告**：`establish_real_reachability: protocol handshake failed: Error reading SSH protocol banner`（paramiko）。
- **原始 TCP 抓 banner**：`/dev/tcp/127.0.0.1/6022` 连通但 `head -c 200` 返回**空**（无 SSH banner）。
- **ssh 详细报错**：`kex_exchange_identification: Connection closed by remote host`。
- **frps 日志**：`tplink-ssh` 代理只记录「get a user connection」（18:17 / 18:24 / 18:36），无后端 dial 成功记录；`ss` 仅见 frpc（树莓派 182.148.120.213）→ frps:7000 的控制连接。

**结论（已从 Pi 侧只读诊断精确定位，2026-09-05 21:00）**：交换机 SSH（`192.168.31.220:22`）**接受 TCP 连接但立即关闭、不发 SSH banner**。该现象在 Pi 直连交换机时同样复现（`head -c 120` 读 0 字节），完全绕过 FRP，故排除 frpc/frps。同时 frpc 正常（active，`192.168.31.51:57854 → 47.109.197.217:7000` ESTAB）、frpc.toml 配置正确、交换机在线（ping 0% 丢包，telnet 23/http 80/https 443 均 OPEN）。**根因判定为交换机 SSH 守护进程会话耗尽或挂死**（TL-SG5428 管理面有并发会话上限，卡死会话占满后新连接被接受即丢弃），非代码缺陷、非 frpc/frps、非内网链路故障。修复需交换机本体操作（重启或清 SSH 会话）。

## 5. 附带发现（测试脚本缺陷，非阻塞）

`e2e_real_write_test.py` 的 `TERMINAL_STATUSES = {"CLOSED","FAILED","REJECTED","EXPIRED"}` 与实际 API 返回的状态字符串不匹配：API 返回的是枚举字符串 `WorkflowStatus.FAILED`（而非 `FAILED`），导致脚本在 FAILED 后仍轮询至 420s 超时，而非快速失败。属次要缺陷，建议后续修正（将 `WorkflowStatus.*` 归一化或扩展终端集合）。

## 6. 待用户决定

- 交换机 SSH 恢复：需用户检查真实交换机（192.168.31.220）SSH 服务，或授权排查树莓派 frpc → 交换机链路。恢复后可原样重跑写 E2E（无需改代码）。
- 测试脚本缺陷（TERMINAL_STATUSES）：可选修复后随下一 commit 部署。

<audit_log>
  <log time="2026-09-05T18:09:00Z" state="DEPLOY" action="git_reset_hard_2207351" result="SUCCESS" trace_id="inv-real-e2e-e-002" target="47.109.197.217"/>
  <log time="2026-09-05T18:09:00Z" state="DEPLOY" action="systemctl_restart_networkagent" result="SUCCESS" trace_id="inv-real-e2e-e-002"/>
  <log time="2026-09-05T18:09:00Z" state="VERIFY" action="health_check" result="HEALTHY" trace_id="inv-real-e2e-e-002"/>
  <log time="2026-09-05T18:17:00Z" state="E2E" action="real_write_PORT_SHUTDOWN" result="FAILED_establish_ssh" trace_id="inv-real-e2e-e-002"/>
  <log time="2026-09-05T18:24:00Z" state="E2E" action="real_write_PORT_DOWN" result="FAILED_establish_ssh" trace_id="inv-real-e2e-e-002"/>
</audit_log>
</file_header>
