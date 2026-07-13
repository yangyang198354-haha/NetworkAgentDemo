<file_header>
  <author_agent>sub_agent_devops_engineer</author_agent>
  <timestamp>2026-07-12T00:00:00Z</timestamp>
  <project_name>NetworkAgentDemo</project_name>
  <version>0.2.0</version>
  <input_files>
    <file>requirements/inspection_systemd_requirements.md</file>
    <file>architecture/inspection_systemd_architecture_design.md</file>
    <file>architecture/inspection_systemd_module_design.md</file>
    <file>architecture/tech_stack.md</file>
    <file>testing/inspection_systemd_unit_test_report.md</file>
    <file>testing/inspection_systemd_integration_test_report.md</file>
    <file>testing/inspection_systemd_e2e_test_report.md</file>
    <file>development/inspection_systemd_code_review_report.md</file>
    <file>config/config.yaml</file>
    <file>requirements.txt</file>
    <file>src/main.py</file>
    <file>deployment/deployment_plan.md</file>
  </input_files>
  <phase>PHASE_INSP_05</phase>
  <status>DRAFT</status>
</file_header>

# CI/CD 流水线定义 -- 巡检机制 systemd 重构 v0.2.0

---

## 流水线概览

```
[Source] -> [Build] -> [Unit Test] -> [Integration Test] -> [Package] -> [Deploy Staging] -> [Deploy Prod]
                                                                                                    ^
                                                                                          MANUAL GATE
                                                                                    (PRODUCTION_DEPLOY_CONFIRM)
```

**流水线类型**: 半自动流水线（Build/Test 阶段自动执行，Deploy 阶段需人工确认门控）

**执行环境**: 
- Build & Test 阶段: 开发机（Windows 11 Pro, Python 3.11+, Node.js 20+）
- Deploy 阶段: 通过 SSH (plink) 远程执行至 Alibaba Cloud ECS (47.109.197.217)

**目标环境**: Alibaba Cloud Linux 3, kernel 5.10, systemd 管理

---

## 阶段定义表

| 阶段 ID | 阶段名 | 触发条件 | 命令 | 成功标准 | 失败处理 |
|---------|--------|---------|------|---------|---------|
| STAGE-01 | Source | 手动触发 / Git push | `git checkout v0.2.0-inspection-systemd`<br>`git pull origin master`<br>`git log -1 --oneline` | 工作目录与远程仓库一致，HEAD 指向预期 commit | abort-and-notify（通知 PM 检查仓库状态） |
| STAGE-02 | Build | STAGE-01 成功 | **Python 依赖**:<br>`cd /opt/NetworkAgentDemo`<br>`source venv/bin/activate`<br>`pip install --upgrade pip`<br>`pip install -r requirements.txt`<br><br>**前端构建**:<br>`cd webui`<br>`npm install`<br>`npm run build` | ① pip install 退出码 0，无 ERROR 日志<br>② npm build 退出码 0，`webui/dist/` 目录生成<br>③ apscheduler 不在已安装依赖列表中 | abort-and-notify（通知 PM 构建失败详情）；修复依赖后重试 |
| STAGE-03 | Unit Test | STAGE-02 成功 | `cd /opt/NetworkAgentDemo`<br>`source venv/bin/activate`<br>`pytest tests/test_inspection_systemd_*.py -v --tb=short` | 通过率 >= 80%，覆盖率 >= 80%<br>（当前: 109/109 = 100%，覆盖率 87%） | abort-and-notify；路由失败用例给 Developer 修复后重试 |
| STAGE-04 | Integration Test | STAGE-03 成功 | `cd /opt/NetworkAgentDemo`<br>`source venv/bin/activate`<br>`pytest tests/test_inspection_systemd_integration.py -v --tb=short` | 通过率 >= 90%<br>（**当前: 9/18 = 50.00% — 门控 FAILED，TEST-BUG-001 待修复**） | abort-and-notify；阻塞后续所有阶段；路由 TEST-BUG-001 给 Developer |
| STAGE-05 | Package | STAGE-04 成功 | `cd /opt/NetworkAgentDemo`<br>`tar -czf /tmp/networkagent-v0.2.0-inspection-systemd.tar.gz \`<br>`  --exclude='webui/node_modules' \`<br>`  --exclude='__pycache__' \`<br>`  --exclude='*.pyc' \`<br>`  --exclude='.git' \`<br>`  --exclude='venv' \`<br>`  --exclude='data/' \`<br>`  --exclude='logs/' \`<br>`  src/ resources/ config/ webui/dist/ requirements.txt .env.example` | ① tarball 生成成功<br>② 包含文件列表与预期一致 | abort-and-notify；检查磁盘空间和文件权限 |
| STAGE-06 | Deploy Staging (Dry-Run) | STAGE-05 成功 | **SSH 预检（不执行变更）**:<br>`plink root@47.109.197.217 "echo SSH_OK && python3.11 --version && node --version"`<br>`plink root@47.109.197.217 "systemctl is-active genplatform-backend"`<br>`plink root@47.109.197.217 "ss -tlnp | grep -E ':80\|:8000\|:8001'"` | ① SSH 连通性 OK<br>② python3.11 --version 输出 3.11.x<br>③ node --version 输出 v20.x.x<br>④ genplatform-backend = active<br>⑤ 端口 8001 可安全使用 | abort-and-notify；通知 PM 检查 VPS 状态；修复环境问题后重试 |
| STAGE-07 | Deploy Production | STAGE-06 成功 **且** `PRODUCTION_DEPLOY_CONFIRM=true` | 按 `deployment/inspection_systemd_deployment_plan.md` 中 DEPLOY-001 ~ DEPLOY-015 顺序执行 | 所有 DEPLOY-NNN 步骤状态 = SUCCESS<br>部署后验证全部通过 | **立即暂停**；执行逆序回滚（从失败步骤回滚至 DEPLOY-001）；写入 deployment_report.md（status=ROLLED_BACK） |

---

## 环境配置矩阵

| 配置项 | Dev 环境（Windows 开发机）| Staging 环境（Dry-Run）| Prod 环境（VPS） |
|--------|------------------------|----------------------|-------------------|
| **Python 版本** | 3.14.6（开发环境）| N/A（仅验证连通性）| python3.11（`/usr/bin/python3.11`）|
| **Node.js** | 20+ | N/A | v20.x.x |
| **systemd** | 不可用（Windows）| N/A | systemd 可用（Alibaba Cloud Linux 3）|
| **数据库路径** | `./data/webui.db` | N/A | `/opt/NetworkAgentDemo/data/webui.db` |
| **Web 端口** | 8000（开发默认）| N/A | **8001**（networkagent.service）|
| **巡检 CLI** | `python -m src.inspection_cli run` | N/A | `python3.11 -m src.inspection_cli run` |
| **运行用户** | 当前用户 | N/A | root（Web 进程）/ networkagent（巡检进程）|
| **systemd unit 路径** | N/A | N/A | `/etc/systemd/system/networkagent-inspection.{service,timer}` |
| **sudoers 路径** | N/A | N/A | `/etc/sudoers.d/networkagent` |
| **项目根目录** | 开发机工作目录 | N/A | `/opt/NetworkAgentDemo` |
| **环境变量** | `.env` 文件 | N/A | `NETWORKAGENT_HOME=/opt/NetworkAgentDemo`（通过 systemd Environment 或 .env）|

---

## Artifact 管理规则

### 构建产物

| 产物 | 位置 | 格式 | 晋升条件 |
|------|------|------|---------|
| Python 依赖包 | VPS `/opt/NetworkAgentDemo/venv/` | pip virtual environment | STAGE-04 (Integration Test) PASSED |
| 前端构建产物 | `webui/dist/`（本地）→ VPS `/opt/NetworkAgentDemo/webui/dist/` | 静态文件（HTML + JS + CSS） | STAGE-04 PASSED；npm build 退出码 = 0 |
| 部署 tarball | `/tmp/networkagent-v0.2.0-inspection-systemd.tar.gz` | gzip 压缩包 | STAGE-04 PASSED；包含所有必需文件 |
| systemd unit 文件 | VPS `/etc/systemd/system/networkagent-inspection.service`<br>VPS `/etc/systemd/system/networkagent-inspection.timer` | INI 格式 unit 文件 | STAGE-07 执行时由 Jinja2 模板渲染生成 |

### 产物晋升规则

```
Python 依赖安装 (STAGE-02)
  -> Unit Test PASSED (STAGE-03)
    -> Integration Test PASSED (STAGE-04)
      -> Package (STAGE-05)
        -> Deploy Staging dry-run PASSED (STAGE-06)
          -> [MANUAL GATE: PRODUCTION_DEPLOY_CONFIRM=true]
            -> Deploy Production (STAGE-07)
```

### 产物命名格式

- 部署 tarball: `networkagent-v{version}-inspection-systemd-{YYYYMMDD_HHMMSS}.tar.gz`
- 备份目录: `/opt/NetworkAgentDemo.backup.{YYYYMMDD_HHMMSS}/`

---

## 阶段间数据传递

| 从阶段 | 到阶段 | 传递数据 | 方式 |
|--------|--------|---------|------|
| STAGE-01 (Source) | STAGE-02 (Build) | 完整源代码 | 本地文件系统（Git 工作目录）|
| STAGE-02 (Build) | STAGE-03 (Unit Test) | 已安装的 venv + webui/dist/ | 本地文件系统 |
| STAGE-03 (Unit Test) | STAGE-04 (Integration Test) | 测试通过状态 | 退出码 + 测试报告文件 |
| STAGE-04 (Integration Test) | STAGE-05 (Package) | 测试通过状态 | 退出码 |
| STAGE-05 (Package) | STAGE-06 (Deploy Staging) | tarball 路径 | 文件路径引用 |
| STAGE-06 (Deploy Staging) | STAGE-07 (Deploy Prod) | dry-run 结果 + CONFIRM 信号 | 状态文件 + PM agent_invocation |

---

## 通知与告警规则

| 事件 | 通知方式 | 接收人 |
|------|---------|--------|
| 任意阶段失败 | 流水线日志 + agent_response BLOCKED/FAILURE | PM (sub_agent_coordinator) |
| STAGE-04 Integration Test FAILED | 测试报告（含 TEST-BUG-001 详情）| Developer + PM |
| STAGE-07 Deploy Production 就绪等待 CONFIRM | agent_response PARTIAL_SUCCESS + notes | PM |
| STAGE-07 某步骤失败需回滚 | deployment_report.md（status=ROLLED_BACK）+ agent_response | PM |
| 部署成功 | deployment_report.md（status=DEPLOYED_SUCCESSFULLY）| PM |

---

## 当前门控状态

| 门控项 | 状态 | 阻塞影响 |
|--------|------|---------|
| Unit Test (>= 80%) | **PASSED (100%)** | 无阻塞 |
| Integration Test (>= 90%) | **FAILED (50.00%)** — TEST-BUG-001 | **阻塞 STAGE-04 及之后所有阶段** |
| E2E Test (pre-gate) | **FAILED (22.22%)** — TEST-BUG-001 + TEST-BUG-002 | **阻塞正式部署执行** |
| Code Review | DRAFT — 2 MAJOR (DOCUMENTED), 4 MINOR | 低风险 |
| Architecture Design | DRAFT | 待 PM 审批 |

**结论**: CI/CD 流水线 STAGE-01 ~ STAGE-03 可执行，STAGE-04 起被集成测试门控阻塞。生产部署执行被全面阻塞，需 Developer 修复 TEST-BUG-001（DB session 表隔离问题）和 TEST-BUG-002（E2E mock 属性路径问题）后重新执行测试。

---

## 安全与合规约束集成

| 约束 | 在流水线中的实施 |
|------|----------------|
| **端口隔离** | STAGE-06 dry-run 验证端口 80/8000/8001 占用状态；STAGE-07 仅操作 8001 |
| **禁止 pkill -f gunicorn** | 所有部署命令中不包含 gunicorn 相关操作；仅使用 systemctl restart networkagent |
| **Python 版本锁定** | STAGE-06 dry-run 验证 `python3.11` 可用；STAGE-07 所有命令明确使用 `python3.11` |
| **敏感数据保护** | 所有配置文件中 API key/密码以 `[REDACTED]` 占位；通过环境变量注入 |
| **sudoers 安全** | STAGE-07 DEPLOY-008 配置 `/etc/sudoers.d/networkagent`，使用精确命令白名单（`networkagent-inspection.*`）|
| **systemctl 命令注入防护** | 所有 systemctl 调用使用 `subprocess.run(shell=False, list args)`；流水线命令以参数列表形式传递 |
| **最小权限** | 巡检进程以 `networkagent` 用户运行（非 root）；Web 进程通过 sudoers 白名单调用 systemctl |
