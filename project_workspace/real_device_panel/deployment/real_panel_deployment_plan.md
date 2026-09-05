<file_header>
  <project_id>NetworkAgentDemo</project_id>
  <module_id>real_device_panel</module_id>
  <doc_type>deployment_plan</doc_type>
  <file_name>real_panel_deployment_plan.md</file_name>
  <version>0.1.0</version>
  <status>APPROVED</status>
  <author_agent>sub_agent_devops_engineer</author_agent>
  <created_at>2026-09-05T00:00:00Z</created_at>
  <last_updated>2026-09-05T00:00:00Z</last_updated>
  <invocation_id>inv-real-panel-e-001</invocation_id>
  <input_source>PM agent_invocation — REAL_DEVICE_PANEL / GROUP_RP_E（部署计划阶段，未授权生产部署）</input_source>
</file_header>

# 生产部署计划 — 真实设备（REAL）面板（REAL_DEVICE_PANEL）

> **状态**: 本文件为**部署计划（已通过计划级门控 gate-rp-e-001）**，仅定义执行步骤，**本轮未授权、不执行任何生产部署写操作**。
> 生产部署执行被 `PRODUCTION_DEPLOY_CONFIRM=true` 门控拦截（见「生产部署执行前置条件」）。
> `real_panel_deployment_report.md` 本轮保持 **NOT_CREATED / DEPLOYMENT_PENDING**。

**目标环境**: Alibaba Cloud ECS（47.109.197.217），Alibaba Cloud Linux 3，端口 8001，`networkagent.service`
**部署策略**: 滚动更新（单实例 Demo，先逐文件备份 → 覆盖 → `npm run build` → 重启服务，最小化停机时间）
**连接方式**: PuTTY plink/pscp via PowerShell（本地 Windows 通过 plink 执行远程命令）
**停机时间**: `networkagent.service` 重启约 5-10 秒（仅 Web 进程，前端构建在服务重启前完成）

**变更版本**: REAL_DEVICE_PANEL 垂直切片（后端新增 3 + 后端修改 3 + 前端修改 2 + 测试 4；零新增依赖；无数据库 schema 变更）

---

## 变更范围清单（部署组件，锚定 module_design.md）

### 后端（新增，3 文件）
| 文件路径 | 对应模块 | 说明 |
|---------|---------|------|
| `src/tools/real_panel_parsers.py` | MOD-RP-003 | CLI 输出纯函数解析器 |
| `src/tools/real_panel_service.py` | MOD-RP-002 | 单会话批量采集 + 写操作编排 |
| `src/tools/real_session_gate.py` | MOD-RP-004 | per-device 会话串行化门 |

### 后端（修改，3 文件）
| 文件路径 | 变更 | 对应模块 |
|---------|------|---------|
| `src/api/devices_router.py` | 新增 `GET /{device_id}/real_panel`；`configure_device_port` 新增 REAL 分支；`check_connectivity` 的 `_l7_check` 包裹 `session_guard` | MOD-RP-001 |
| `src/tools/switch_diag_tool.py` | `TpLinkSwitchDiagTool._run` REAL 分支包裹 `session_guard_by_access` | ADR-RP-003 |
| `src/tools/switch_config_tool.py` | `TpLinkSwitchConfigTool._run` REAL 分支包裹 `session_guard_by_access` | ADR-RP-003 |

### 前端（修改，2 文件）
| 文件路径 | 变更 | 对应模块 |
|---------|------|---------|
| `webui/src/stores/devices.ts` | 新增 `getRealPanel` + `configurePort` 可选超时 | MOD-RP-006 |
| `webui/src/views/devices/DevicesListView.vue` | 新增 REAL「面板」按钮 + REAL 抽屉 + loading/二次确认/IO 降级 | MOD-RP-005 |

### 测试（新增，4 文件，CI-only，不部署到生产）
| 文件路径 | 级别 |
|---------|------|
| `tests/test_real_panel_parsers.py` | UNIT |
| `tests/test_real_session_gate.py` | UNIT |
| `tests/test_real_panel_service.py` | UNIT |
| `tests/test_real_panel_api.py` | INT |

> 测试文件为 CI/回归产物，**不推送至生产 VPS**（与既有 inspection_systemd 部署一致，测试在开发机/CI 环境执行）。

### 零变更（NFUNC-003 约束，严禁触碰）
- `src/tools/real_device_client.py`（零改动，只读复用）
- `src/security/audit_logger.py`、`src/models/enums.py`（复用，零改动）
- `devices_router.py` 中 SIMULATOR 分支、`/heartbeat`、`/check_connectivity` 返回字段（零改动）
- 数据库 schema（无新表/迁移）

---

## 部署前检查清单（Pre-deployment Checklist）

| 检查项 ID | 检查项 | 检查方法 | 成功标准 | 负责方 |
|-----------|--------|---------|---------|--------|
| PRECHK-01 | 后端 py_compile 绿 | `python -m py_compile src/tools/real_panel_parsers.py src/tools/real_panel_service.py src/tools/real_session_gate.py src/api/devices_router.py src/tools/switch_diag_tool.py src/tools/switch_config_tool.py` | 6 个文件退出码 0，无语法错误 | DevOps |
| PRECHK-02 | 前端构建绿 | `cd webui && npm run build` | 退出码 0，`webui/dist/index.html` + `assets/DevicesListView-*.js` 生成 | DevOps |
| PRECHK-03 | REAL 面板单元测试门控 | 读取 `testing/real_panel_unit_test_report.md` | 通过率 ≥ 80%（当前 100%，1 xfail） | Test Engineer |
| PRECHK-04 | REAL 面板集成测试门控 | 读取 `testing/real_panel_integration_test_report.md` | 通过率 ≥ 90%（当前 100%） | Test Engineer |
| PRECHK-05 | 全量回归套件绿 | 运行 CLAUDE.md CI 命令（排除 e2e/slow） | 0 FAIL（4 个 `test_real_*.py` 纳入） | Test Engineer |
| PRECHK-06 | 依赖无变更确认 | 对比 `requirements.txt` / `webui/package.json` 与基线 | 零新增 Python/Node 依赖 | DevOps |
| PRECHK-07 | 数据库 schema 无变更确认 | 核对 module_design「零变更清单」 | 无新表/迁移，`create_all()` 幂等 | DevOps |
| PRECHK-08 | E2E 状态确认 | 读取 `testing/real_panel_e2e_test_report.md` | 状态 = NOT_EXECUTED（无真实设备）→ **部署后验证不得擅自写生产端口** | Test Engineer |
| PRECHK-09 | 生产部署 CONFIRM 信号 | 检查 PM `agent_invocation` 的 special_instructions | 本轮**未收到** `PRODUCTION_DEPLOY_CONFIRM=true` → **只出计划，不执行** | PM |

> **门控警告**: PRECHK-09（未授权）与 PRECHK-08（E2E NOT_EXECUTED）当前未满足，**阻塞任何生产部署执行**。其余 PRECHK-01~07 已由代码评审与测试阶段确认通过。

---

## 端口与进程分配（必须严格遵守）

| Port | Process | Service | 归属 | 操作限制 |
|------|---------|---------|------|---------|
| 80 | nginx | GenPlatform front-end | GenPlatform | **禁止触碰** |
| 8000 | gunicorn+uvicorn | GenPlatform backend | GenPlatform | **禁止触碰** |
| **8001** | uvicorn | NetworkAgentDemo Web API | **networkagent.service** | 本次部署操作范围 |

**绝对安全红线**:
- `pkill -f gunicorn` = **严禁执行**（会误杀 GenPlatform backend）
- 任何操作 `genplatform-*` systemd 服务 = **严禁执行**
- 任何操作 80/8000 端口 = **严禁执行**
- Python 必须使用 **python3.11**（系统默认 python3 是 3.6，不可用）
- **真实 TL-SG5428 端口写操作（enable/disable）** = 部署验证阶段**严禁擅自执行**，除非用户另行授权

---

## 部署步骤（正向）

---

**DEPLOY-001: SSH 预检 — 环境就绪性验证**

- **组件**: VPS 运行环境（非变更操作）
- **操作**:
  ```powershell
  plink root@47.109.197.217 "echo '=== SSH OK ===' && python3.11 --version && node --version"
  plink root@47.109.197.217 "systemctl is-active networkagent && echo 'networkagent active'"
  plink root@47.109.197.217 "ss -tlnp | grep -E ':8001'"
  plink root@47.109.197.217 "df -h /opt | tail -1"
  plink root@47.109.197.217 "test -d /opt/NetworkAgentDemo && echo 'Project dir EXISTS' || echo 'MISSING'"
  ```
- **预期结果**:
  - SSH 连通；python3.11 ≥ 3.11.0；node ≥ v20.0.0
  - networkagent = active；端口 8001 由 networkagent 监听
  - /opt 磁盘可用 > 1GB；/opt/NetworkAgentDemo 目录存在
- **对应回滚**: ROLLBACK-001（验证步骤，无回滚操作）
- **备注**: 纯验证，不执行任何变更。任一检查失败即中止并通知 PM。

---

**DEPLOY-002: 备份现有部署**

- **组件**: `/opt/NetworkAgentDemo/` 整个目录 + `/etc/systemd/system/networkagent.service`
- **操作**:
  ```bash
  plink root@47.109.197.217 "systemctl stop networkagent && systemctl is-active networkagent || echo 'STOPPED_OK'"
  plink root@47.109.197.217 "cp -a /opt/NetworkAgentDemo /opt/NetworkAgentDemo.backup.$(date +%Y%m%d_%H%M%S)"
  plink root@47.109.197.217 "cp /etc/systemd/system/networkagent.service /etc/systemd/system/networkagent.service.backup.$(date +%Y%m%d_%H%M%S)"
  plink root@47.109.197.217 "ls -la /opt/NetworkAgentDemo.backup.*/src/main.py && echo 'BACKUP_VERIFIED'"
  ```
- **预期结果**: networkagent 停止；备份目录（含 `src/main.py`）与 service 备份创建成功
- **对应回滚**: ROLLBACK-002
- **备注**: 逐文件备份在 DEPLOY-004/005 内另行执行（`.real-panel.bak`）。

---

**DEPLOY-003: 推送新增后端源文件（3 文件）**

- **组件**: `real_panel_parsers.py` / `real_panel_service.py` / `real_session_gate.py`
- **操作**:
  ```powershell
  pscp "C:\...\src\tools\real_panel_parsers.py"  root@47.109.197.217:/opt/NetworkAgentDemo/src/tools/real_panel_parsers.py
  pscp "C:\...\src\tools\real_panel_service.py"  root@47.109.197.217:/opt/NetworkAgentDemo/src/tools/real_panel_service.py
  pscp "C:\...\src\tools\real_session_gate.py"   root@47.109.197.217:/opt/NetworkAgentDemo/src/tools/real_session_gate.py
  ```
  ```bash
  plink root@47.109.197.217 "ls -la /opt/NetworkAgentDemo/src/tools/real_panel_parsers.py /opt/NetworkAgentDemo/src/tools/real_panel_service.py /opt/NetworkAgentDemo/src/tools/real_session_gate.py"
  ```
- **预期结果**: 3 个文件存在且大小与本地一致
- **对应回滚**: ROLLBACK-003

---

**DEPLOY-004: 推送修改后端源文件（3 文件）**

- **组件**: `devices_router.py` / `switch_diag_tool.py` / `switch_config_tool.py`
- **操作**:
  ```bash
  plink root@47.109.197.217 "for f in src/api/devices_router.py src/tools/switch_diag_tool.py src/tools/switch_config_tool.py; do cp /opt/NetworkAgentDemo/\$f /opt/NetworkAgentDemo/\$f.real-panel.bak; done && echo 'BACKED_UP'"
  ```
  ```powershell
  pscp "C:\...\src\api\devices_router.py"        root@47.109.197.217:/opt/NetworkAgentDemo/src/api/devices_router.py
  pscp "C:\...\src\tools\switch_diag_tool.py"    root@47.109.197.217:/opt/NetworkAgentDemo/src/tools/switch_diag_tool.py
  pscp "C:\...\src\tools\switch_config_tool.py"  root@47.109.197.217:/opt/NetworkAgentDemo/src/tools/switch_config_tool.py
  ```
  ```bash
  plink root@47.109.197.217 "grep -c 'real_panel' /opt/NetworkAgentDemo/src/api/devices_router.py && grep -c 'session_guard_by_access' /opt/NetworkAgentDemo/src/tools/switch_diag_tool.py /opt/NetworkAgentDemo/src/tools/switch_config_tool.py"
  ```
- **预期结果**: 3 文件覆盖更新；`devices_router.py` 含 `real_panel` 端点；两个工具含 `session_guard_by_access` 包裹
- **对应回滚**: ROLLBACK-004

---

**DEPLOY-005: 推送前端源码文件（2 文件）**

- **组件**: `webui/src/stores/devices.ts` / `webui/src/views/devices/DevicesListView.vue`
- **操作**:
  ```bash
  plink root@47.109.197.217 "for f in webui/src/stores/devices.ts webui/src/views/devices/DevicesListView.vue; do cp /opt/NetworkAgentDemo/\$f /opt/NetworkAgentDemo/\$f.real-panel.bak; done && echo 'BACKED_UP'"
  ```
  ```powershell
  pscp "C:\...\webui\src\stores\devices.ts"                    root@47.109.197.217:/opt/NetworkAgentDemo/webui/src/stores/devices.ts
  pscp "C:\...\webui\src\views\devices\DevicesListView.vue"    root@47.109.197.217:/opt/NetworkAgentDemo/webui/src/views/devices/DevicesListView.vue
  ```
  ```bash
  plink root@47.109.197.217 "grep -c 'getRealPanel' /opt/NetworkAgentDemo/webui/src/stores/devices.ts && grep -c 'showRealPanel' /opt/NetworkAgentDemo/webui/src/views/devices/DevicesListView.vue"
  ```
- **预期结果**: 2 文件覆盖更新；`devices.ts` 含 `getRealPanel`；`DevicesListView.vue` 含 `showRealPanel`
- **对应回滚**: ROLLBACK-005

---

**DEPLOY-006: 前端生产构建**

- **组件**: `webui/` → `webui/dist/`（含 REAL 面板抽屉的 Vue 3 + Vite 生产构建）
- **操作**:
  ```bash
  plink root@47.109.197.217 "cd /opt/NetworkAgentDemo/webui && npm run build 2>&1 | tail -10"
  plink root@47.109.197.217 "ls -la /opt/NetworkAgentDemo/webui/dist/index.html && ls /opt/NetworkAgentDemo/webui/dist/assets/ | grep -i DevicesListView && echo 'BUILD_OK'"
  ```
- **预期结果**: `npm run build` 退出码 0；`dist/index.html` 存在；`dist/assets/DevicesListView-*.js` 生成
- **对应回滚**: ROLLBACK-006
- **备注**: 零新增 npm 依赖，无需 `npm install`（若 node_modules 缺失则先 `npm install`，失败则改用「本地构建后上传 dist/」的备选路径）。

---

**DEPLOY-007: 后端编译与导入校验（重启前安全门）**

- **组件**: 6 个后端文件（3 新增 + 3 修改）
- **操作**:
  ```bash
  plink root@47.109.197.217 "cd /opt/NetworkAgentDemo && source venv/bin/activate && python3.11 -m py_compile src/tools/real_panel_parsers.py src/tools/real_panel_service.py src/tools/real_session_gate.py src/api/devices_router.py src/tools/switch_diag_tool.py src/tools/switch_config_tool.py && echo 'PY_COMPILE_OK'"
  plink root@47.109.197.217 "cd /opt/NetworkAgentDemo && source venv/bin/activate && python3.11 -c 'import src.tools.real_panel_parsers, src.tools.real_panel_service, src.tools.real_session_gate; print(\"IMPORT_OK\")'"
  ```
- **预期结果**: `py_compile` 退出码 0；三个新模块可被 import（`IMPORT_OK`）
- **对应回滚**: ROLLBACK-007（验证步骤，无回滚操作；若失败由 ROLLBACK-003/004 恢复）
- **备注**: 纯验证，不产生状态变更；失败即中止，不进入重启。

---

**DEPLOY-008: 重启 networkagent.service**

- **组件**: `networkagent.service`（systemd 管理的 uvicorn FastAPI 进程，端口 8001）
- **操作**:
  ```bash
  plink root@47.109.197.217 "systemctl daemon-reload && systemctl start networkagent"
  plink root@47.109.197.217 "sleep 5 && systemctl is-active networkagent"
  plink root@47.109.197.217 "ss -tlnp | grep 8001"
  plink root@47.109.197.217 "journalctl -u networkagent -n 30 --no-pager | grep -iE 'error|critical' || echo 'NO_FATAL'"
  ```
- **预期结果**: `active (running)`；端口 8001 LISTEN；日志无 FATAL/CRITICAL
- **对应回滚**: ROLLBACK-008

---

**DEPLOY-009: 后端健康检查 /health**

- **组件**: FastAPI Web 进程（端口 8001）
- **操作**:
  ```bash
  plink root@47.109.197.217 "curl -s http://localhost:8001/health | python3.11 -m json.tool"
  curl -s --connect-timeout 5 http://47.109.197.217:8001/health
  ```
- **预期结果**: HTTP 200；`status=healthy`；`service=NetworkAgentDemo`；版本字段与 REAL_DEVICE_PANEL 变更一致（具体以 `src/main.py` 实际 version 为准，≥ v0.2.0）；外部可达 HTTP 200
- **对应回滚**: ROLLBACK-009（验证步骤，无回滚操作）

---

**DEPLOY-010: REAL 面板端点验证**

- **组件**: `GET /api/devices/{device_id}/real_panel`
- **操作**（需先登录获取 JWT，`Authorization: Bearer <token>`）:
  ```bash
  # SIMULATOR 设备 → 期望 400（非 REAL 设备）
  plink root@47.109.197.217 "curl -s -o /dev/null -w '%{http_code}' -H 'Authorization: Bearer <TOKEN>' http://localhost:8001/api/devices/<SIMULATOR_ID>/real_panel"
  # REAL 设备（若在线）→ 期望 200 采集快照；若离线 → 期望明确 502（错误码语义正确，非 500）
  plink root@47.109.197.217 "curl -s -w '\n%{http_code}' -H 'Authorization: Bearer <TOKEN>' http://localhost:8001/api/devices/<REAL_ID>/real_panel"
  ```
- **预期结果**:
  - SIMULATOR → `400`（响应 `message` 含「仅适用于 REAL」）
  - REAL 在线 → `200`（`{ports,cpu,memory,io,info?,collected_at}`）
  - REAL 离线/凭据错 → `502`（含 `section`/`message`，非 500；错误码语义正确）
- **对应回滚**: ROLLBACK-010（验证步骤，无回滚操作）
- **备注**: **不执行真实端口写测试**。仅验证读端点与错误码语义。

---

**DEPLOY-011: SIMULATOR 面板/心跳/连通性零回归验证**

- **组件**: SIMULATOR `/ports`、`/system`、`/heartbeat`、`/check_connectivity`（NFUNC-003）
- **操作**:
  ```bash
  plink root@47.109.197.217 "curl -s -o /dev/null -w '%{http_code}' -H 'Authorization: Bearer <TOKEN>' http://localhost:8001/api/devices/<SIMULATOR_ID>/ports"
  plink root@47.109.197.217 "curl -s -o /dev/null -w '%{http_code}' -H 'Authorization: Bearer <TOKEN>' http://localhost:8001/api/devices/<SIMULATOR_ID>/system"
  plink root@47.109.197.217 "curl -s -o /dev/null -w '%{http_code}' -H 'Authorization: Bearer <TOKEN>' http://localhost:8001/api/devices/<SIMULATOR_ID>/heartbeat"
  plink root@47.109.197.217 "curl -s -o /dev/null -w '%{http_code}' -H 'Authorization: Bearer <TOKEN>' http://localhost:8001/api/devices/<SIMULATOR_ID>/check_connectivity"
  # SIMULATOR /ports 对 REAL 设备仍返回「仅适用于模拟器」（非 SIMULATOR 不分支）
  plink root@47.109.197.217 "curl -s -w '\n%{http_code}' -H 'Authorization: Bearer <TOKEN>' http://localhost:8001/api/devices/<REAL_ID>/ports"
  ```
- **预期结果**: SIMULATOR 面板/心跳/连通性均 HTTP 200 且 schema 不变；`/ports` 对 REAL 设备仍返回「仅适用于模拟器」语义
- **对应回滚**: ROLLBACK-011（验证步骤，无回滚操作）

---

**DEPLOY-012: 写操作安全专项验证（三重防护核对）**

- **组件**: REAL 端口写操作安全（REQ-RP-NFUNC-002 / AC-RP-005-03 / AC-RP-006-02）
- **操作**（**静态核对 + 审计验证，不执行真实写操作**）:
  ```bash
  # ① 前端二次确认文案（静态核对部署产物/源码）
  plink root@47.109.197.217 "grep -o '此操作将修改真实生产设备配置' /opt/NetworkAgentDemo/webui/src/views/devices/DevicesListView.vue"
  # ② 后端审计 + 不持久化（代码路径核对，不直连真实设备）
  plink root@47.109.197.217 "grep -nE 'AuditEventType.CONFIG_CHANGE|alert_id=.*device:|save\(' /opt/NetworkAgentDemo/src/api/devices_router.py /opt/NetworkAgentDemo/src/tools/real_panel_service.py"
  # ③ 确认审计 detail 不含 password 字段（代码核对）
  plink root@47.109.197.217 "grep -n 'log_audit_event' /opt/NetworkAgentDemo/src/api/devices_router.py"
  ```
- **预期结果**:
  - ① 前端二次确认文案存在（含「此操作将修改真实生产设备配置」+ 目标端口 + 动作）
  - ② 后端审计调用含 `event_type=CONFIG_CHANGE`、`alert_id=f"device:{id}"`、`operator=current_user.username`、`action=port_shutdown|port_no_shutdown`
  - ③ 写路径只调 `configure_real_port`（`configure` 不 `save`），`detail` 不含 `password`/`ssh_password_encrypted`
  - **不执行任何真实 enable/disable 写命令**（仅代码/静态核对；单元测试 `save.assert_not_called` 已覆盖不持久化）
- **对应回滚**: ROLLBACK-012（验证步骤，无回滚操作）

---

## 回滚步骤（逆向，按逆序排列）

> **回滚原则**: 逆序执行（最后部署的组件最先回滚），每步精确逆转对应 DEPLOY-NNN 的操作。
> **回滚基准**: REAL_DEVICE_PANEL 变更前的部署状态（v0.2.0 基线）。

---

**ROLLBACK-012: 写操作安全验证（无需回滚）**

- **回滚操作**: 无。此为静态验证步骤，不涉及状态变更。
- **预期结果**: N/A

---

**ROLLBACK-011: SIMULATOR 零回归验证（无需回滚）**

- **回滚操作**: 无。此为验证步骤，不涉及状态变更。
- **预期结果**: N/A

---

**ROLLBACK-010: REAL 面板端点验证（无需回滚）**

- **回滚操作**: 无。此为验证步骤，不涉及状态变更。
- **预期结果**: N/A

---

**ROLLBACK-009: 健康检查验证（无需回滚）**

- **回滚操作**: 无。此为验证步骤，不涉及状态变更。
- **预期结果**: N/A

---

**ROLLBACK-008: 停止服务并恢复基线（回退到备份）**

- **回滚操作**:
  ```bash
  plink root@47.109.197.217 "systemctl stop networkagent"
  plink root@47.109.197.217 "BACKUP=\$(ls -dt /opt/NetworkAgentDemo.backup.*/ | head -1) && if [ -n \"\$BACKUP\" ]; then rm -rf /opt/NetworkAgentDemo/src && rm -rf /opt/NetworkAgentDemo/webui && cp -r \"\$BACKUP/src\" /opt/NetworkAgentDemo/src && cp -r \"\$BACKUP/webui\" /opt/NetworkAgentDemo/webui && echo 'SRC_UI_RESTORED'; else echo 'NO_BACKUP'; fi"
  plink root@47.109.197.217 "systemctl daemon-reload && systemctl start networkagent"
  plink root@47.109.197.217 "sleep 3 && systemctl is-active networkagent && curl -s http://localhost:8001/health"
  ```
- **预期结果**: networkagent 恢复为变更前基线运行（REAL_DEVICE_PANEL 变更移除）
- **备注**: 亦可用于「回滚失败」时从 DEPLOY-002 完整备份整体恢复。

---

**ROLLBACK-007: 编译校验（无需回滚）**

- **回滚操作**: 无。纯验证步骤；若此步失败，实际恢复由 ROLLBACK-003/004 完成。
- **预期结果**: N/A

---

**ROLLBACK-006: 恢复前端构建产物**

- **回滚操作**:
  ```bash
  plink root@47.109.197.217 "BACKUP=\$(ls -dt /opt/NetworkAgentDemo.backup.*/ | head -1) && if [ -d \"\$BACKUP/webui/dist\" ]; then rm -rf /opt/NetworkAgentDemo/webui/dist && cp -r \"\$BACKUP/webui/dist\" /opt/NetworkAgentDemo/webui/dist && echo 'DIST_RESTORED'; else echo 'NO_DIST_BACKUP'; fi"
  ```
- **预期结果**: `webui/dist/` 恢复为变更前版本（或重建变更前构建）

---

**ROLLBACK-005: 恢复前端源码文件**

- **回滚操作**:
  ```bash
  plink root@47.109.197.217 "for f in webui/src/stores/devices.ts webui/src/views/devices/DevicesListView.vue; do cp /opt/NetworkAgentDemo/\$f.real-panel.bak /opt/NetworkAgentDemo/\$f && echo \"RESTORED: \$f\"; done"
  ```
- **预期结果**: 2 个前端文件恢复为变更前内容（`.real-panel.bak` 覆盖）

---

**ROLLBACK-004: 恢复修改后端源文件**

- **回滚操作**:
  ```bash
  plink root@47.109.197.217 "for f in src/api/devices_router.py src/tools/switch_diag_tool.py src/tools/switch_config_tool.py; do cp /opt/NetworkAgentDemo/\$f.real-panel.bak /opt/NetworkAgentDemo/\$f && echo \"RESTORED: \$f\"; done"
  ```
- **预期结果**: 3 个后端文件恢复为变更前内容（`.real-panel.bak` 覆盖）

---

**ROLLBACK-003: 移除新增后端源文件**

- **回滚操作**:
  ```bash
  plink root@47.109.197.217 "rm -f /opt/NetworkAgentDemo/src/tools/real_panel_parsers.py /opt/NetworkAgentDemo/src/tools/real_panel_service.py /opt/NetworkAgentDemo/src/tools/real_session_gate.py && echo 'NEW_FILES_REMOVED'"
  ```
- **预期结果**: 3 个新增文件不存在

---

**ROLLBACK-002: 完整恢复备份**

- **回滚操作**:
  ```bash
  plink root@47.109.197.217 "systemctl stop networkagent"
  plink root@47.109.197.217 "rm -rf /opt/NetworkAgentDemo && LATEST_BAK=\$(ls -dt /opt/NetworkAgentDemo.backup.*/ | head -1) && cp -a \"\$LATEST_BAK\" /opt/NetworkAgentDemo && echo 'FULL_RESTORE_DONE'"
  plink root@47.109.197.217 "systemctl daemon-reload && systemctl start networkagent"
  plink root@47.109.197.217 "sleep 3 && systemctl is-active networkagent && curl -s http://localhost:8001/health && echo 'RECOVERY_VERIFIED'"
  ```
- **预期结果**: 系统完整恢复为变更前部署状态，服务正常运行
- **备注**: 最彻底的兜底回滚（覆盖 DEPLOY-003~006 的全部变更）。

---

**ROLLBACK-001: SSH 预检（无需回滚）**

- **回滚操作**: 无。此为验证步骤，不涉及状态变更。
- **预期结果**: N/A

---

## 部署后验证清单（Post-deployment Verification）

| 检查项 ID | 检查项 | 检查方法（命令/URL/工具） | 成功标准 |
|-----------|--------|--------------------------|---------|
| V1 | `/health` 版本与进程存活 | `curl -s http://localhost:8001/health`；`systemctl is-active networkagent` | HTTP 200，`status=healthy`，`active (running)`，版本与本次变更一致（≥ v0.2.0） |
| V2 | 端口 8001 监听 | `ss -tlnp | grep 8001` | LISTEN，归属 networkagent |
| V3 | REAL 面板端点对 SIMULATOR 语义 | `curl -H 'Authorization: Bearer <TOKEN>' /api/devices/{SIMULATOR_ID}/real_panel` | HTTP 400，`message` 含「仅适用于 REAL」 |
| V4 | REAL 面板端点对 REAL 语义 | `curl -H 'Authorization: Bearer <TOKEN>' /api/devices/{REAL_ID}/real_panel` | REAL 在线 → 200 采集快照；离线/凭据错 → 502（错误码语义正确，非 500） |
| V5 | SIMULATOR `/ports` 零回归 | `curl -H 'Authorization: Bearer <TOKEN>' /api/devices/{SIMULATOR_ID}/ports` | HTTP 200，schema 不变 |
| V6 | SIMULATOR `/system` 零回归 | `curl -H 'Authorization: Bearer <TOKEN>' /api/devices/{SIMULATOR_ID}/system` | HTTP 200，schema 不变 |
| V7 | `/heartbeat` 零回归 | `curl -H 'Authorization: Bearer <TOKEN>' /api/devices/{SIMULATOR_ID}/heartbeat` | HTTP 200，返回字段不变 |
| V8 | `/check_connectivity` 零回归 | `curl -H 'Authorization: Bearer <TOKEN>' /api/devices/{REAL_ID}/check_connectivity` | HTTP 200，返回字段（`device_model`/`software_version`）不变 |
| V9 | `/ports` 对 REAL 仍限模拟器 | `curl -H 'Authorization: Bearer <TOKEN>' /api/devices/{REAL_ID}/ports` | 返回「仅适用于模拟器」语义（NFUNC-003） |
| V10 | 写操作·前端二次确认 | 静态核对 `DevicesListView.vue`（`confirmRealPortAction`） | 文案含「此操作将修改真实生产设备配置」+ 目标端口 + 动作 |
| V11 | 写操作·审计日志落库 | 静态核对 `devices_router.py` `_configure_real_port` 审计调用 | `AuditLogger.log_audit_event(CONFIG_CHANGE, alert_id=device:{id}, operator=current_user.username, action=port_shutdown/no_shutdown)` |
| V12 | 写操作·不持久化 | 单元测试 `save.assert_not_called()` + 代码路径核对 | 写路径仅 `configure()`，**不调 `save()`**，**不执行 `copy running-config startup-config`** |
| V13 | 审计 detail 无明文密码 | 核对 `detail` 字段构造 | `{device_id, device_name, port_name, action, success, message}`，不含 `password` |
| V14 | 前端构建产物 | `ls /opt/NetworkAgentDemo/webui/dist/index.html` + `assets/DevicesListView-*.js` | 文件存在 |
| V15 | SPA 首页加载 | `curl -s -o /dev/null -w '%{http_code}' http://localhost:8001/` | HTTP 200 |
| V16 | 日志无 ERROR | `journalctl -u networkagent -n 50 --no-pager | grep -i error | wc -l` | 0 或仅非关键错误 |
| V17 | GenPlatform 未受影响 | `systemctl is-active genplatform-backend`；`curl -s -o /dev/null -w '%{http_code}' http://localhost:80/`；`:8000/` | `active`；80/8000 均 HTTP 200 |

> **写操作安全专项（V10~V13）为硬性检查项**：必须在「前端二次确认 + 审计日志落库 + 不调 save/copy running-config」三处均通过，且**不执行任何真实 enable/disable 写测试**，方视为验证通过。

---

## 真实设备安全红线（必须严格遵守）

1. **端口写操作必须前端二次确认**：用户点击启用/禁用时，前端必须弹出确认（文案明确「此操作将修改真实生产设备配置」+ 目标端口 + shutdown/no shutdown 动作），确认后才调用后端。
2. **写操作必须审计日志落库**：后端 `AuditLogger.log_audit_event` 记录 `event_type=CONFIG_CHANGE`、`operator=current_user.username`、`action=port_shutdown|port_no_shutdown`，`detail` 不含明文密码。
3. **不做 running-config 持久化**：写路径仅 `DeviceToolSession.configure([...])`（`configure` 不 `save`），**绝不调用 `save()` / 不执行 `copy running-config startup-config`**（AC-RP-005-03）。
4. **部署验证不得擅自写生产端口**：本次部署后验证（V3/V4 及 DEPLOY-010）仅做读端点 + 错误码语义验证与静态核对，**不执行任何真实 `shutdown`/`no shutdown` 写测试**，除非用户另行授权并提供可达真实设备。

---

## 风险与缓解（遗留项，部署时需关注）

| 风险 ID | 来源 | 描述 | 缓解/部署影响 |
|---------|------|------|--------------|
| FND-001 | 代码评审 MAJOR | 端口 `vlan`/`speed` 位置启发式仅用 MOCK 校准，真实 TP-Link 输出列序不同可能误配 | 部署后 REAL 面板端口列可能误配；需真实设备输出校准（E2E）；解析失败抛 `RealPanelError` 不返回伪造数据 |
| FND-006 | 代码评审 MAJOR | `parse_system_info` 的 Device Name/Model 标签未用真实输出校准，info 字段可能部分为空 | ADR-RP-004 容错设计下不阻塞；info 为 Should Have，可空 |
| FND-003 | 代码评审 MAJOR | 面板（FRP host）与工作流工具（device_ip）锁 key 未统一，FRP 场景下「面板+工作流并发」存在残余串行化缺口 | 进程内锁仅在 key 一致时共享；当前单实例 Demo 可接受；列为开放问题，需实现阶段校准 |
| FND-005 | 代码评审 MINOR | 写操作 `success` 判定（`failed==0 and executed>=len`）依赖底层会话语义，回显异常可能误判成功 | 测试阶段需真实设备校准；写失败反馈由 502 兜底 |
| FND-004 | 代码评审 MINOR | 会话锁注册表无清理机制，锁对象只增不减 | 演示规模可忽略（进程内存占用极小） |
| 单实例限制 | ADR-RP-003 | `threading.Lock` 仅进程内有效，多实例/多进程部署不跨实例 | 当前单进程 FastAPI 可接受；多实例部署需另议（开放问题） |
| E2E NOT_EXECUTED | 测试报告 | 无真实 TL-SG5428 接入，真实采集/写回归未执行 | **阻塞 STAGE-08 正式生产部署**；需授权 + 真实设备后补做 |

---

## 生产部署执行前置条件（本次未授权）

**生产部署执行（STAGE-08）必须满足以下全部条件，否则只输出计划、不执行：**

1. **PM 收到用户明确授权**，并在 `agent_invocation` 的 special_instructions 中发出 `PRODUCTION_DEPLOY_CONFIRM=true` 信号（不接受其他来源）。
2. **真实设备 E2E 通过**（或经 PM 明确豁免）：`real_panel_e2e_test_report.md` 状态由 NOT_EXECUTED 转为已执行并通过（需真实 TL-SG5428 可达 + 用户授权真实写测试）。
3. **部署前检查清单 PRECHK-01~07 全部通过**（后端 py_compile、前端 build、单元/集成/回归、依赖无变更、schema 无变更）。
4. **部署后验证 V1~V17 全部通过**，尤其写操作安全专项（V10~V13）。

**本次状态**: PRECHK-09 未收到 CONFIRM；PRECHK-08 E2E = NOT_EXECUTED。**生产部署未授权、未执行。**
`real_panel_deployment_report.md` 保持 **NOT_CREATED / DEPLOYMENT_PENDING**，待 PM 明确授权后由本代理执行并生成。

---

## 预计耗时

| 步骤 | 预计耗时 | 备注 |
|------|---------|------|
| DEPLOY-001 SSH 预检 | < 10s | 纯验证 |
| DEPLOY-002 备份现有部署 | < 30s | 取决于目录大小 |
| DEPLOY-003 推送新增后端 3 文件 | < 15s | pscp 上传 |
| DEPLOY-004 推送修改后端 3 文件 | < 15s | 含逐文件备份 |
| DEPLOY-005 推送前端 2 文件 | < 15s | 含逐文件备份 |
| DEPLOY-006 前端构建 | < 120s | npm run build |
| DEPLOY-007 后端编译/导入校验 | < 10s | py_compile + import |
| DEPLOY-008 重启服务 | < 15s | 含 5s 等待 |
| DEPLOY-009 健康检查 | < 10s | curl |
| DEPLOY-010 REAL 面板端点验证 | < 70s | REAL 离线则 502 语义验证（读，不写） |
| DEPLOY-011 SIMULATOR 零回归 | < 15s | curl |
| DEPLOY-012 写安全静态核对 | < 10s | grep 静态核对 |
| **总计** | **约 5-6 分钟** | |

---

## 安全约束重申

| 约束 | 确保方式 |
|------|---------|
| **绝对禁止 pkill -f gunicorn** | 部署/回滚命令仅用 `systemctl` 管理 networkagent |
| **只操作 8001 端口** | 命令仅检查/监听 8001；不修改 80/8000 规则 |
| **只操作 networkagent.service** | systemctl 操作限定于 networkagent |
| **Python 必须用 python3.11** | 命令显式 `python3.11` / `/usr/bin/python3.11` |
| **真实设备写操作红线** | 部署验证不执行 enable/disable 写；写操作必须二次确认 + 审计 + 不 save |
| **部署失败立即回滚** | 任一步骤失败暂停，从当前步骤逆序 ROLLBACK-NNN |
| **未授权不部署** | 无 `PRODUCTION_DEPLOY_CONFIRM=true` 即停在计划阶段 |

---

*文档版本 0.1.0 | 状态 APPROVED | 生成时间 2026-09-05 | 作者 sub_agent_devops_engineer | invocation inv-real-panel-e-001*

<audit_log>
  <log time="2026-09-05T00:00:00Z" state="WRITE_FILES" action="file_write" result="SUCCESS" trace_id="inv-real-panel-e-001" file_path="project_workspace/real_device_panel/deployment/real_panel_deployment_plan.md"/>
</audit_log>
