<file_header>
  <project_id>NetworkAgentDemo</project_id>
  <module_id>real_device_e2e</module_id>
  <doc_type>deployment_plan</doc_type>
  <file_name>real_device_e2e_deployment_plan.md</file_name>
  <version>0.2.0</version>
  <status>READY</status>
  <author_agent>sub_agent_devops_engineer</author_agent>
  <created_at>2026-09-05T17:40:00Z</created_at>
  <last_updated>2026-09-05T17:40:00Z</last_updated>
  <invocation_id>inv-real-e2e-e-001</invocation_id>
  <input_source>GROUP_RE_E 部署阶段 — 基于 APPROVED real_device_e2e_architecture_design.md + real_device_e2e_tech_stack.md（PRODUCTION_DEPLOY_CONFIRM=true，来自 PM）</input_source>
</file_header>

# 真实设备（REAL）端到端工作流 — 生产部署计划

> 状态说明：本计划已就绪（READY）。实际生产执行状态见 `real_device_e2e_deployment_report.md`。

## 0. 部署摘要

| 项 | 值 |
|----|----|
| 目标环境 | 生产 VPS（阿里云 ECS 47.109.197.217，root） |
| 部署代码 | commit `2207351`（origin/master HEAD，已 push） |
| 代码路径 | `/opt/NetworkAgentDemo/project_workspace/` |
| Python venv | `/opt/NetworkAgentDemo/venv/bin/python` |
| 服务 | FastAPI，端口 8001，systemd 管理（unit 名待确认，见 DEPLOY-003） |
| 部署策略 | 直接替换 + 滚动重启（单实例，最小停机） |
| 新增依赖 | 无（零新增 Python/Node 依赖，见 tech_stack） |
| 部署文件 | 4 个生产文件（见下） |

### 本次部署的生产文件（4 个）

| 相对路径（project_workspace/ 下） | 变更内容 |
|-----------------------------------|---------|
| `src/orchestration/node_handlers.py` | REAL 分支：FRP 解析、REAL 工具选择、TP-Link 命令映射、能力裁决、结构化验证、凭据门控、脱敏 |
| `src/api/alerts_router.py` | simulate 回填真实元数据 |
| `resources/templates/tpl_port_enable.yaml` | 删除 description 行 |
| `resources/templates/tpl_port_disable.yaml` | 删除 description 行 |

## 1. 部署前检查清单（Pre-deployment Checklist）

| 检查项 | 检查方法 | 成功标准 | 负责方 |
|-------|---------|---------|-------|
| 输入门控 | 读取 architecture / tech_stack / 三份测试报告 file_header | architecture=APPROVED、tech_stack=APPROVED、unit=PASSED、integration=PASSED、e2e=PARTIAL（真实写按 PM 指令推迟 GROUP_E，非失败） | DevOps |
| 提交就绪 | `git -C <local> log --oneline -1 origin/master` | HEAD = `2207351` 且已 push | DevOps |
| SSH 免密连通 | `ssh -i ~/.ssh/vps_rsa_key -o BatchMode=yes root@47.109.197.217 'echo OK'` | 输出 OK，无密码提示 | DevOps |
| VPS 仓库状态 | `ls -d /opt/NetworkAgentDemo/.git` | 存在 `.git`（git 仓库） | DevOps |
| 当前服务进程 | `ps aux | grep -E 'main.py|uvicorn|gunicorn' | grep -v grep` | 存在且绑定 8001 | DevOps |
| systemd unit | `systemctl list-units --type=service | grep -iE 'networkagent|network'` | 确认 unit 名（预期 `networkagent.service`） | DevOps |
| venv python | `/opt/NetworkAgentDemo/venv/bin/python --version` | Python 3.11+ | DevOps |
| 端口监听 | `ss -ltnp | grep :8001` | 8001 处于 LISTEN | DevOps |
| 磁盘空间 | `df -h /opt` | 备份所需空间充足（≥ 备份目录大小） | DevOps |

## 2. 部署步骤（正向）

---
**DEPLOY-001: 部署前全量备份**
- **组件**：`/opt/NetworkAgentDemo/project_workspace/`（应用代码 + 资源 + 模板）
- **操作**：
  ```bash
  TS=$(date +%Y%m%d_%H%M%S)
  cp -a /opt/NetworkAgentDemo/project_workspace /opt/NetworkAgentDemo.backup.${TS}
  echo "$TS" > /opt/NetworkAgentDemo/.deploy_backup_ts
  ```
- **预期结果**：备份目录 `/opt/NetworkAgentDemo.backup.<ts>/` 存在，且与原目录一致（`diff -rq` 无差异）；`.deploy_backup_ts` 记录时间戳。
- **对应回滚**：ROLLBACK-001
- **备注**：`cp -a` 保留权限/软链；不触碰 `data/` 之外的运行时 DB（备份含 data，无害）。

---
**DEPLOY-002: 拉取代码到 commit 2207351**
- **组件**：`/opt/NetworkAgentDemo/project_workspace/`（git 仓库）
- **操作**（VPS 为 git 仓库时）：
  ```bash
  cd /opt/NetworkAgentDemo/project_workspace
  git fetch origin master
  git reset --hard origin/master
  git rev-parse HEAD   # 期望输出 2207351
  ```
  （若 VPS 非 git 仓库，改为 scp 覆盖 4 个文件到对应路径，见备注）
- **预期结果**：`git rev-parse HEAD` = `2207351`；4 个目标文件与本地 commit 内容一致。
- **对应回滚**：ROLLBACK-002
- **备注**：`git reset --hard` 会丢弃 VPS 上未提交的本地改动——若 VPS 有本地改动（如 `.env`），先单独备份后再 reset。`.env` 若被 `.gitignore` 排除则不受影响。

---
**DEPLOY-003: 确认 systemd unit 名**
- **组件**：服务编排（systemd）
- **操作**：
  ```bash
  systemctl list-units --type=service --all | grep -iE 'networkagent|network'
  systemctl is-active networkagent 2>/dev/null || true
  ```
- **预期结果**：确认 unit 名（预期 `networkagent.service`）与当前 active 状态；记录在案。
- **对应回滚**：无（只读确认，不改状态）
- **备注**：只读步骤；若 unit 名非 `networkagent`，以实际名执行 DEPLOY-004。

---
**DEPLOY-004: 重启 FastAPI 服务（滚动，最小停机）**
- **组件**：FastAPI 服务进程（8001）
- **操作**：
  ```bash
  systemctl restart networkagent   # 以 DEPLOY-003 确认的 unit 名为准
  sleep 2
  systemctl is-active networkagent
  ```
- **预期结果**：`systemctl is-active` 返回 `active`；进程重新加载了 2207351 代码。
- **对应回滚**：ROLLBACK-004
- **备注**：单实例，restart 有数秒停机；如采用 supervisor/nohup，按实际管理方式重启（先确认再重启，禁止 `pkill`）。

---
**DEPLOY-005: 部署后健康验证**
- **组件**：FastAPI `/health` 端点
- **操作**：
  ```bash
  curl -s -m 10 http://127.0.0.1:8001/health
  curl -s -m 10 http://127.0.0.1:8001/health | python3 -c 'import sys,json; d=json.load(sys.stdin); assert d.get("status")=="healthy"'
  ```
- **预期结果**：返回 `{"status":"healthy","version":"0.2.0"}`（或确认进程存活 + 8001 监听 + 无启动堆栈异常）。
- **对应回滚**：ROLLBACK-005
- **备注**：验证期间**不对交换机下发任何写命令**；写 E2E 由 PM 在部署确认后单独执行。

## 3. 回滚步骤（逆向，按逆序排列）

---
**ROLLBACK-005: 回滚健康验证**
- **回滚操作**：恢复代码后再次 `curl -s http://127.0.0.1:8001/health`，确认回退版本 `healthy`。
- **预期结果**：`{"status":"healthy","version":"0.2.0"}`（回退到备份版本）。

---
**ROLLBACK-004: 回滚服务重启**
- **回滚操作**：`systemctl restart networkagent`（恢复代码后重启，使旧版本生效）。
- **预期结果**：服务 active，运行旧代码。

---
**ROLLBACK-003: 回滚确认 unit 名**
- **回滚操作**：确认 unit 名不变，无状态变更（本步骤为只读，无需逆向）。

---
**ROLLBACK-002: 回滚代码版本**
- **回滚操作**：
  ```bash
  cd /opt/NetworkAgentDemo/project_workspace
  git reset --hard <原 HEAD 提交>   # 备份时记录的 git rev-parse HEAD
  ```
  （非 git 仓库时：用备份目录覆盖 4 个文件）
- **预期结果**：`git rev-parse HEAD` 回到部署前提交；4 文件内容与部署前一致。

---
**ROLLBACK-001: 回滚备份恢复**
- **回滚操作**（兜底，代码层 rollback 失败时）：
  ```bash
  TS=$(cat /opt/NetworkAgentDemo/.deploy_backup_ts)
  rm -rf /opt/NetworkAgentDemo/project_workspace
  cp -a /opt/NetworkAgentDemo.backup.${TS} /opt/NetworkAgentDemo/project_workspace
  ```
- **预期结果**：`project_workspace/` 完整恢复为部署前快照。
- **备注**：`[MANUAL_ROLLBACK_REQUIRED: 删除与 cp -a 为高危操作，仅在确认备份完整时由人工确认执行]`

## 4. 部署后验证清单（Post-deployment Verification）

| 检查项 | 检查方法 | 成功标准 |
|-------|---------|---------|
| 服务健康检查 | `curl -s http://127.0.0.1:8001/health` | HTTP 200，`status=healthy`，`version=0.2.0` |
| 端口监听 | `ss -ltnp | grep :8001` | 8001 LISTEN |
| 进程存活 | `systemctl is-active networkagent` | `active` |
| 启动日志无异常 | `journalctl -u networkagent -n 50 --no-pager` | 无 Python traceback / ImportError |
| 关键功能冒烟 | `curl -s http://127.0.0.1:8001/api/alerts/simulate`（仅 MOCK，不写真实交换机） | 返回合法响应，无 500 |

> 真实设备写 E2E（Gi1/0/2 `no shutdown` / `shutdown`）不在本部署步骤内，由 PM 在部署确认后单独执行。

<audit_log>
  <log time="2026-09-05T17:40:00Z" state="WRITE_FILES" action="file_write" result="SUCCESS" trace_id="inv-real-e2e-e-001" file_path="project_workspace/real_device_e2e/deployment/real_device_e2e_deployment_plan.md"/>
</audit_log>
