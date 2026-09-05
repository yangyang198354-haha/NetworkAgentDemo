<file_header>
  <project_id>NetworkAgentDemo</project_id>
  <module_id>real_device_panel</module_id>
  <doc_type>cicd_pipeline</doc_type>
  <file_name>real_panel_cicd_pipeline.md</file_name>
  <version>0.1.0</version>
  <status>APPROVED</status>
  <author_agent>sub_agent_devops_engineer</author_agent>
  <created_at>2026-09-05T00:00:00Z</created_at>
  <last_updated>2026-09-05T00:00:00Z</last_updated>
  <invocation_id>inv-real-panel-e-001</invocation_id>
  <input_source>PM agent_invocation — REAL_DEVICE_PANEL / GROUP_RP_E（CI/CD 定义阶段，未授权生产部署）</input_source>
</file_header>

# CI/CD 流水线定义 — 真实设备（REAL）面板（REAL_DEVICE_PANEL）

> 本文件只定义 CI/CD 流水线；生产部署执行步骤见 `real_panel_deployment_plan.md`。
> 生产部署执行被 **PRODUCTION_DEPLOY_CONFIRM=true** 门控拦截，本轮未授权，流水线仅可执行至 Deploy Staging（dry-run）阶段。

---

## 流水线概览

```
[Source] -> [Build] -> [Unit Test] -> [Integration Test] -> [Regression] -> [Package] -> [Deploy Staging(dry-run)] -> [Deploy Prod]
                                                                                                                          ^
                                                                                                                  MANUAL GATE
                                                                                                          (PRODUCTION_DEPLOY_CONFIRM=true)
                                                                                                            + 真实设备 E2E 通过

[E2E(真实设备)] --(仅 workflow_dispatch 手动触发, 需真实 TL-SG5428 可达)-->
```

**流水线类型**: 半自动流水线（Source/Build/Test/Package 阶段自动执行；Deploy Staging 为只读 dry-run；Deploy Prod 需人工门控 + 明确 CONFIRM）。

**执行环境**:
- Build & Test 阶段: 开发机（Windows 11 Pro，Python 3.11+ / 实际 3.14.6，Node.js 20+ / 实际 v24.18.0）
- Deploy 阶段: 通过 SSH（PuTTY plink/pscp）远程执行至 Alibaba Cloud ECS（47.109.197.217，端口 8001，`networkagent.service`）

**目标环境**: Alibaba Cloud Linux 3，systemd 管理，单实例 FastAPI 进程（端口 8001）。

**输入锚定**: 构建工具引用自 `real_device_panel/architecture/real_panel_tech_stack.md`（零新增依赖，复用 pytest / npm / Vue3+Vite）；部署组件引用自 `real_device_panel/architecture/real_panel_module_design.md`（MOD-RP-001~007）。

---

## 阶段定义表

| 阶段 ID | 阶段名 | 触发条件 | 命令 | 成功标准 | 失败处理 |
|---------|--------|---------|------|---------|---------|
| STAGE-01 | Source | 手动触发 / Git push 到 master | `git checkout master`<br>`git pull origin master`<br>`git log -1 --oneline` | 工作目录与远程一致，HEAD 指向包含 REAL_DEVICE_PANEL 变更的 commit | abort-and-notify（通知 PM 检查仓库状态） |
| STAGE-02 | Build | STAGE-01 成功 | **后端依赖（零新增，仅确认）**:<br>`cd project_workspace`<br>`python -m pip install -r requirements.txt`<br><br>**前端构建**:<br>`cd webui`<br>`npm run build` | ① pip install 退出码 0（无新增第三方依赖）<br>② `npm run build` 退出码 0，`webui/dist/` 生成 `index.html` + `assets/`（含 `DevicesListView-*.js` 产物）<br>③ 无 ERROR 级构建日志 | abort-and-notify（通知 PM 构建失败详情）；修复后重试 |
| STAGE-03 | Unit Test（REAL 面板） | STAGE-02 成功 | `cd project_workspace`<br>`python -m pytest tests/test_real_panel_parsers.py tests/test_real_session_gate.py tests/test_real_panel_service.py -v --tb=short` | 通过率 ≥ 80%（当前: 66/66 = 100%，1 xfail 不计分母）<br>覆盖率（`--cov=src.tools.real_panel_*`）≥ 80%（当前 99%） | abort-and-notify；路由失败用例给 Developer 修复后重试 |
| STAGE-04 | Integration Test（REAL 面板） | STAGE-03 成功 | `cd project_workspace`<br>`python -m pytest tests/test_real_panel_api.py -v --tb=short` | 通过率 ≥ 90%（当前: 15/15 = 100%） | abort-and-notify；阻塞后续阶段 |
| STAGE-05 | Regression（全量回归） | STAGE-04 成功 | `cd project_workspace`<br>`python -m pytest tests/ -v --tb=short`<br>`  --ignore=tests/test_e2e_webui.py`<br>`  --ignore=tests/test_e2e_full.py`<br>`  --ignore=tests/test_inspection_systemd_e2e.py`<br>`  --ignore=tests/test_e2e_inspection_config_refactor.py`<br>`  --ignore=tests/test_simulator_e2e.py`<br>`  --ignore=tests/test_simulator_tools_e2e.py`<br>`  -k "not slow"` | 全量 CI 单元套件 0 FAIL（排除 e2e/slow），4 个新增 `tests/test_real_*.py` 自然纳入（不匹配任何 ignore，且无 slow 标记） | abort-and-notify；路由失败用例给 Developer |
| STAGE-06 | Package | STAGE-05 成功 | `cd project_workspace`<br>`tar -czf /tmp/networkagent-real-panel-{version}.tar.gz`<br>`  --exclude='webui/node_modules'`<br>`  --exclude='__pycache__'`<br>`  --exclude='*.pyc'`<br>`  --exclude='.git'`<br>`  --exclude='venv'`<br>`  --exclude='data/'`<br>`  --exclude='logs/'`<br>`  src/ webui/dist/ requirements.txt .env.example` | ① tarball 生成成功<br>② 包含 `src/tools/real_panel_*.py`（3 个新文件）与修改后的 `devices_router.py`/`switch_*.py`<br>③ 不包含 `data/`、`venv/`、`node_modules/` | abort-and-notify；检查磁盘空间与文件权限 |
| STAGE-07 | Deploy Staging（dry-run） | STAGE-06 成功 | **只读 SSH 预检（不执行变更）**:<br>`plink root@47.109.197.217 "echo SSH_OK && python3.11 --version && node --version"`<br>`plink root@47.109.197.217 "systemctl is-active networkagent"`<br>`plink root@47.109.197.217 "ss -tlnp | grep 8001"`<br>`plink root@47.109.197.217 "df -h /opt | tail -1"` | ① SSH 连通，python3.11 ≥ 3.11，node ≥ 20<br>② networkagent = active<br>③ 端口 8001 由 networkagent 监听<br>④ /opt 磁盘可用 > 1GB | abort-and-notify；通知 PM 检查 VPS 状态后重试 |
| STAGE-08 | Deploy Production | STAGE-07 成功 **且** `PRODUCTION_DEPLOY_CONFIRM=true` **且** 真实设备 E2E 通过 | 按 `real_panel_deployment_plan.md` 中 DEPLOY-001 ~ DEPLOY-012 顺序执行 | 所有 DEPLOY-NNN 步骤 = SUCCESS，部署后验证 V1~Vn 全部通过 | **立即暂停**；执行逆序回滚（从失败步骤回滚至 DEPLOY-001）；写入 `deployment_report.md`（status=ROLLED_BACK） |
| STAGE-09 | E2E（真实设备，可选） | **仅 workflow_dispatch 手动触发**，需真实 TL-SG5428 可达 + 用户授权 | `python -m pytest tests/ -v -k "e2e"`（含真实设备采集与端口写回归，需环境显式提供真实设备凭据） | Critical Path 100% 通过（当前: **NOT_EXECUTED**，无真实设备接入） | abort-and-notify；不虚构通过率；记录 NOT_EXECUTED |

---

## CI 命令与 CLAUDE.md 一致性说明

- **后端 CI 单元测试命令**（STAGE-05）与仓库 `CLAUDE.md`「Run all unit tests (CI mode)」完全一致：排除 6 个 e2e 文件 + `-k "not slow"`。
- **新增测试纳入 CI**：4 个新文件
  - 单元：`tests/test_real_panel_parsers.py`、`tests/test_real_session_gate.py`、`tests/test_real_panel_service.py`
  - 集成：`tests/test_real_panel_api.py`
  - 注：`test_real_session_gate.py` 命名不匹配 `test_real_panel_*.py` glob，CI 显式列出或使用 `tests/test_real_*.py` glob 捕获全部 4 文件；STAGE-05 的全量 `pytest tests/` 会自然覆盖它们。
- **前端构建 job**：`cd webui && npm run build`（产出 `webui/dist/`），零新增 npm 依赖。
- **E2E**：仅 `workflow_dispatch` 手动触发（需真实设备），当前 `real_panel_e2e_test_report.md` 状态 = NOT_EXECUTED。

---

## 环境配置矩阵

| 配置项 | Dev 环境（Windows 开发机） | Staging 环境（dry-run） | Prod 环境（VPS） |
|--------|--------------------------|------------------------|-------------------|
| Python 版本 | 3.14.6（开发） | N/A（仅验证连通性） | python3.11（`/usr/bin/python3.11`） |
| Node.js | v24.18.0 | N/A | v20.x.x |
| systemd | 不可用（Windows） | N/A | 可用（Alibaba Cloud Linux 3） |
| 数据库路径 | `./data/webui.db` | N/A | `/opt/NetworkAgentDemo/data/webui.db`（无 schema 变更） |
| Web 端口 | 8000（开发默认） | N/A | **8001**（`networkagent.service`） |
| 前端产物 | `webui/dist/`（本地） | N/A | `/opt/NetworkAgentDemo/webui/dist/` |
| 项目根目录 | 开发机工作目录 | N/A | `/opt/NetworkAgentDemo` |
| 运行用户 | 当前用户 | N/A | root（Web 进程） |
| 新增 Python/Node 依赖 | 无 | N/A | 无（复用既有 venv） |
| 数据库迁移 | 无 | N/A | 无（`Base.metadata.create_all()` 幂等） |

---

## Artifact 管理规则

### 构建产物

| 产物 | 位置 | 格式 | 晋升条件 |
|------|------|------|---------|
| 前端构建产物 | `webui/dist/`（本地）→ VPS `/opt/NetworkAgentDemo/webui/dist/` | 静态文件（HTML + JS + CSS） | STAGE-02 npm build 退出码 0；STAGE-05 回归 PASSED |
| 部署 tarball | `/tmp/networkagent-real-panel-{version}-{YYYYMMDD_HHMMSS}.tar.gz` | gzip 压缩包 | STAGE-05 PASSED；包含全部必需文件 |
| 新增后端源文件 | VPS `/opt/NetworkAgentDemo/src/tools/real_panel_parsers.py`<br>`real_panel_service.py`<br>`real_session_gate.py` | Python 源文件 | STAGE-07 dry-run PASSED 后、STAGE-08 执行时推送 |

### 产物晋升规则

```
Build (STAGE-02) -> Unit Test PASSED (STAGE-03)
  -> Integration Test PASSED (STAGE-04)
    -> Regression PASSED (STAGE-05)
      -> Package (STAGE-06)
        -> Deploy Staging dry-run PASSED (STAGE-07)
          -> [MANUAL GATE: PRODUCTION_DEPLOY_CONFIRM=true + 真实设备 E2E 通过]
            -> Deploy Production (STAGE-08)
```

### 产物命名格式

- 部署 tarball: `networkagent-real-panel-{version}-{YYYYMMDD_HHMMSS}.tar.gz`
- 备份目录: `/opt/NetworkAgentDemo.backup.{YYYYMMDD_HHMMSS}/`
- 逐文件备份: `{file}.real-panel.bak`

---

## 阶段间数据传递

| 从阶段 | 到阶段 | 传递数据 | 方式 |
|--------|--------|---------|------|
| STAGE-01 (Source) | STAGE-02 (Build) | 完整源代码 | 本地文件系统（Git 工作目录） |
| STAGE-02 (Build) | STAGE-03/04/05 (Test) | venv + `webui/dist/` + 测试状态 | 本地文件系统 + 退出码 |
| STAGE-05 (Regression) | STAGE-06 (Package) | 回归通过状态 | 退出码 |
| STAGE-06 (Package) | STAGE-07 (Deploy Staging) | tarball 路径 | 文件路径引用 |
| STAGE-07 (Deploy Staging) | STAGE-08 (Deploy Prod) | dry-run 结果 + CONFIRM 信号 | 状态 + PM `agent_invocation` |

---

## 通知与告警规则

| 事件 | 通知方式 | 接收人 |
|------|---------|--------|
| 任意阶段失败 | 流水线日志 + agent_response BLOCKED/FAILURE | PM（sub_agent_coordinator） |
| STAGE-05 Regression FAILED | 失败用例清单 | Developer + PM |
| STAGE-07 dry-run 就绪等待 CONFIRM | agent_response PARTIAL_SUCCESS + notes「等待 PRODUCTION_DEPLOY_CONFIRM=true」 | PM |
| STAGE-08 某步骤失败需回滚 | deployment_report.md（status=ROLLED_BACK）+ agent_response | PM |
| STAGE-09 E2E NOT_EXECUTED | e2e_test_report.md（status=NOT_EXECUTED） | PM + Test Engineer |
| 部署成功 | deployment_report.md（status=DEPLOYED_SUCCESSFULLY） | PM |

---

## 当前门控状态

| 门控项 | 状态 | 阻塞影响 |
|--------|------|---------|
| Unit Test（REAL 面板，≥ 80%） | **PASSED（100%，1 xfail）** | 无阻塞 |
| Integration Test（REAL 面板，≥ 90%） | **PASSED（100%）** | 无阻塞 |
| 全量 Regression（0 FAIL） | 需在 CI 环境重跑确认（既有套件 484 passed 基准） | 无已知阻塞 |
| 前端构建（npm run build） | **PASSED（9.43s，0 错误）** | 无阻塞 |
| Code Review | APPROVED（CRITICAL 0、MAJOR 3、MINOR 3，均 DOCUMENTED） | 低风险（遗留风险见 deployment_plan） |
| Architecture / Tech Stack | APPROVED | 无阻塞 |
| E2E（真实设备） | **NOT_EXECUTED（无真实 TL-SG5428 接入）** | **阻塞 STAGE-08 正式生产部署**（需授权 + 真实设备） |
| PRODUCTION_DEPLOY_CONFIRM | **PENDING（未授权）** | **阻塞 STAGE-08 正式生产部署** |

**结论**: STAGE-01 ~ STAGE-07（dry-run）可执行；STAGE-08 生产部署被「E2E NOT_EXECUTED + 未授权 CONFIRM」双重门控拦截。STAGE-09 E2E 仅 workflow_dispatch 且需真实设备授权。

---

## 安全与合规约束集成

| 约束 | 在流水线中的实施 |
|------|----------------|
| **生产部署 CONFIRM 门控** | STAGE-08 仅当 `PRODUCTION_DEPLOY_CONFIRM=true`（来自 PM 正式 `agent_invocation`）时执行，否则停在 dry-run |
| **真实设备写操作红线** | STAGE-09 E2E 及部署后验证**不得**擅自对生产端口执行 enable/disable 写测试，除非用户另行授权 |
| **端口隔离** | STAGE-07 dry-run 仅验证 8001 占用状态；不触碰 80/8000（GenPlatform） |
| **禁止 pkill -f gunicorn** | 所有命令仅用 `systemctl restart networkagent`，不涉及 gunicorn 操作 |
| **Python 版本锁定** | STAGE-07 dry-run 验证 `python3.11` 可用；STAGE-08 命令显式使用 `python3.11` |
| **敏感数据保护** | 配置中 API key/密码以 `[REDACTED]` 占位；凭据经 `EncryptionService` 解密，不进日志/响应 |
| **零新增依赖** | STAGE-02 不安装任何新第三方 Python/Node 依赖；pip 仅确认 requirements.txt 一致 |
| **审计留存** | 部署/回滚/写操作均记录至 audit_log；写操作审计含 operator + detail（无明文密码） |

---

*文档版本 0.1.0 | 状态 APPROVED | 生成时间 2026-09-05 | 作者 sub_agent_devops_engineer | invocation inv-real-panel-e-001*

<audit_log>
  <log time="2026-09-05T00:00:00Z" state="WRITE_FILES" action="file_write" result="SUCCESS" trace_id="inv-real-panel-e-001" file_path="project_workspace/real_device_panel/deployment/real_panel_cicd_pipeline.md"/>
</audit_log>
