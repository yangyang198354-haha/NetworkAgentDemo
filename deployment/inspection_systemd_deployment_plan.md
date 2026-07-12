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

# 生产部署计划 -- 巡检机制 systemd 重构 v0.2.0

**目标环境**: Alibaba Cloud ECS (47.109.197.217), Alibaba Cloud Linux 3, kernel 5.10
**部署策略**: 滚动更新（单实例 Demo，先备份再覆盖，最小化停机时间）
**变更版本**: v0.1.0 (APScheduler 巡检 + Web UI) → v0.2.0 (systemd timer + service 巡检 + Web UI 增强)
**连接方式**: PuTTY plink via PowerShell（本地 Windows 通过 plink 执行远程命令）
**停机时间**: networkagent.service 重启约 5-10 秒（仅 Web 进程重启，巡检 CLI 独立进程不受影响）

---

## 部署前检查清单（Pre-deployment Checklist）

| 检查项 ID | 检查项 | 检查方法 | 成功标准 | 负责方 |
|-----------|--------|---------|---------|--------|
| PRECHK-01 | Python 3.11 可用 | `plink root@47.109.197.217 "python3.11 --version"` | 输出 `Python 3.11.x` | DevOps |
| PRECHK-02 | Node.js >= 20 可用 | `plink root@47.109.197.217 "node --version"` | 输出 `v20.x.x` 或更高 | DevOps |
| PRECHK-03 | 端口 8001 可安全使用 | `plink root@47.109.197.217 "ss -tlnp \| grep 8001"` | 仅 networkagent 进程监听或端口空闲 | DevOps |
| PRECHK-04 | GenPlatform 后端正常运行 | `plink root@47.109.197.217 "systemctl is-active genplatform-backend"` | 输出 `active` | DevOps |
| PRECHK-05 | 端口 80/8000 未被占用（除 GenPlatform 外）| `plink root@47.109.197.217 "ss -tlnp \| grep -E ':80\|:8000'"` | 80=nginx, 8000=GenPlatform backend | DevOps |
| PRECHK-06 | 磁盘空间充足 | `plink root@47.109.197.217 "df -h /opt"` | 可用 > 1GB | DevOps |
| PRECHK-07 | 现有 networkagent.service 正常运行 | `plink root@47.109.197.217 "systemctl is-active networkagent"` | 输出 `active` | DevOps |
| PRECHK-08 | /etc/systemd/system/ 目录可写 | `plink root@47.109.197.217 "test -w /etc/systemd/system && echo WRITABLE \|\| echo NOT_WRITABLE"` | 输出 `WRITABLE` | DevOps |
| PRECHK-09 | /etc/sudoers.d/ 目录存在且可写 | `plink root@47.109.197.217 "test -d /etc/sudoers.d && test -w /etc/sudoers.d && echo OK \|\| echo FAIL"` | 输出 `OK` | DevOps |
| PRECHK-10 | iptables 放行端口 8001 | `plink root@47.109.197.217 "iptables -L INPUT -n \| grep 8001 \|\| echo 'NO_RULE'"` | 存在 ACCEPT 规则或 `NO_RULE`（依赖阿里云安全组）| DevOps |
| PRECHK-11 | 单元测试门控通过 | 读取 `testing/inspection_systemd_unit_test_report.md` | 通过率 >= 80%（当前: 100%） | Test Engineer |
| PRECHK-12 | 集成测试门控通过 | 读取 `testing/inspection_systemd_integration_test_report.md` | 通过率 >= 90%（**当前: 50.00% FAILED — 阻塞部署**）| Test Engineer |
| PRECHK-13 | E2E 测试门控通过 | 读取 `testing/inspection_systemd_e2e_test_report.md` | Critical Path >= 100%（**当前: 12.5% FAILED — 阻塞部署**）| Test Engineer |
| PRECHK-14 | architecture_design 已审批 | 读取 `architecture/inspection_systemd_architecture_design.md` header | status=APPROVED（**当前: DRAFT**）| System Architect |
| PRECHK-15 | module_design 已审批 | 读取 `architecture/inspection_systemd_module_design.md` header | status=APPROVED（**当前: DRAFT**）| System Architect |

> **门控警告**: PRECHK-12 (集成测试 50.00%), PRECHK-13 (E2E 22.22%), PRECHK-14/15 (架构 DRAFT) 当前未通过。这些阻塞项必须在生产部署执行前解决。本部署计划可在阻塞项解决前作为参考文档审阅。

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

---

## 部署步骤（正向）

---

**DEPLOY-001: SSH 预检 — 环境就绪性验证**

- **组件**: VPS 运行环境（非变更操作）
- **操作**:
  ```powershell
  # 在本地 Windows PowerShell 中执行（通过 plink）
  plink root@47.109.197.217 "echo '=== SSH OK ===' && python3.11 --version && node --version"
  plink root@47.109.197.217 "systemctl is-active genplatform-backend && echo 'GenPlatform OK'"
  plink root@47.109.197.217 "ss -tlnp | grep -E ':80\b|:8000\b|:8001\b'"
  plink root@47.109.197.217 "df -h /opt | tail -1"
  plink root@47.109.197.217 "test -d /opt/NetworkAgentDemo && echo 'Project dir EXISTS' || echo 'Project dir MISSING'"
  ```
- **预期结果**:
  - SSH 连通，python3.11 版本 >= 3.11.0
  - Node.js >= v20.0.0
  - genplatform-backend = active
  - 端口 80 (nginx), 8000 (gunicorn), 8001 (networkagent) 按预期占用
  - /opt 磁盘可用 > 1GB
  - /opt/NetworkAgentDemo 目录存在
- **对应回滚**: ROLLBACK-001 (验证步骤，无回滚操作)
- **备注**: 纯验证步骤，不执行任何变更。若任一检查失败，中止部署并通知 PM。

---

**DEPLOY-002: 备份现有部署**

- **组件**: `/opt/NetworkAgentDemo/` 整个目录 + `/etc/systemd/system/networkagent.service` 现有配置
- **操作**:
  ```bash
  # 1. 停止 networkagent Web 服务（巡检 CLI 独立进程不受影响）
  plink root@47.109.197.217 "systemctl stop networkagent"

  # 2. 确认服务已停止
  plink root@47.109.197.217 "systemctl is-active networkagent || echo 'STOPPED_OK'"

  # 3. 创建带时间戳的完整备份
  plink root@47.109.197.217 "cp -a /opt/NetworkAgentDemo /opt/NetworkAgentDemo.backup.$(date +%Y%m%d_%H%M%S)"

  # 4. 备份现有 systemd service 文件
  plink root@47.109.197.217 "cp /etc/systemd/system/networkagent.service /etc/systemd/system/networkagent.service.backup.$(date +%Y%m%d_%H%M%S)"

  # 5. 验证备份完整性
  plink root@47.109.197.217 "ls -la /opt/NetworkAgentDemo.backup.*/src/main.py && echo 'BACKUP_VERIFIED'"
  plink root@47.109.197.217 "ls -la /etc/systemd/system/networkagent.service.backup.* && echo 'SERVICE_BACKUP_VERIFIED'"
  ```
- **预期结果**:
  - networkagent.service 状态为 `inactive` (stopped)
  - 备份目录 `/opt/NetworkAgentDemo.backup.YYYYMMDD_HHMMSS/` 创建成功，包含完整 v0.1.0 文件
  - systemd service 文件备份创建成功
  - 备份验证通过
- **对应回滚**: ROLLBACK-002

---

**DEPLOY-003: 创建 networkagent 运行用户**

- **组件**: Linux 系统用户 `networkagent`（巡检 CLI 进程的运行用户）
- **操作**:
  ```bash
  # 检查用户是否已存在
  plink root@47.109.197.217 "id networkagent 2>/dev/null && echo 'USER_EXISTS' || echo 'USER_NOT_FOUND'"

  # 若不存在则创建（系统用户，不可登录）
  plink root@47.109.197.217 "id networkagent 2>/dev/null || useradd -r -s /sbin/nologin -d /opt/NetworkAgentDemo -M networkagent"

  # 验证用户创建成功
  plink root@47.109.197.217 "id networkagent"
  ```
- **预期结果**:
  - `networkagent` 用户存在（新建或已存在）
  - UID 为系统用户范围，shell 为 `/sbin/nologin`
- **对应回滚**: ROLLBACK-003
- **备注**: 此用户用于运行巡检 CLI 进程（networkagent-inspection.service 的 User= 配置）。Web 进程（networkagent.service）以 root 运行（与 v0.1.0 一致）。

---

**DEPLOY-004: 推送 v0.2.0 新增源文件**

- **组件**: v0.2.0 新增的后端模块、CLI 入口、systemd 模板文件
- **新增文件清单**:

  | 文件路径 | 对应模块 | 说明 |
  |---------|---------|------|
  | `src/systemd/__init__.py` | MOD-INSP-001/002 包初始化 | systemd 模块包 |
  | `src/systemd/systemctl_executor.py` | MOD-INSP-002 | systemctl 命令封装 |
  | `src/systemd/systemd_unit_manager.py` | MOD-INSP-001 | unit 文件生成/管理 |
  | `src/inspection_cli.py` | MOD-INSP-003 | CLI 巡检执行入口 |
  | `resources/templates/systemd/networkagent-inspection.service.j2` | — (Jinja2 模板) | service unit 模板 |
  | `resources/templates/systemd/networkagent-inspection.timer.j2` | — (Jinja2 模板) | timer unit 模板 |

- **操作**:
  ```powershell
  # 在本地 Windows PowerShell 中执行（使用 pscp 逐文件上传）
  pscp "C:\...\src\systemd\__init__.py" root@47.109.197.217:/opt/NetworkAgentDemo/src/systemd/__init__.py
  pscp "C:\...\src\systemd\systemctl_executor.py" root@47.109.197.217:/opt/NetworkAgentDemo/src/systemd/systemctl_executor.py
  pscp "C:\...\src\systemd\systemd_unit_manager.py" root@47.109.197.217:/opt/NetworkAgentDemo/src/systemd/systemd_unit_manager.py
  pscp "C:\...\src\inspection_cli.py" root@47.109.197.217:/opt/NetworkAgentDemo/src/inspection_cli.py
  ```
  ```bash
  # 在 VPS 上创建目录并上传模板文件
  plink root@47.109.197.217 "mkdir -p /opt/NetworkAgentDemo/resources/templates/systemd"
  ```
  ```powershell
  pscp "C:\...\resources\templates\systemd\networkagent-inspection.service.j2" root@47.109.197.217:/opt/NetworkAgentDemo/resources/templates/systemd/networkagent-inspection.service.j2
  pscp "C:\...\resources\templates\systemd\networkagent-inspection.timer.j2" root@47.109.197.217:/opt/NetworkAgentDemo/resources/templates/systemd/networkagent-inspection.timer.j2
  ```
  ```bash
  # 验证文件已上传
  plink root@47.109.197.217 "ls -la /opt/NetworkAgentDemo/src/systemd/ && ls -la /opt/NetworkAgentDemo/src/inspection_cli.py && ls -la /opt/NetworkAgentDemo/resources/templates/systemd/"
  ```
- **预期结果**:
  - `src/systemd/` 目录含 3 个 .py 文件
  - `src/inspection_cli.py` 存在
  - `resources/templates/systemd/` 含 2 个 .j2 模板文件
- **对应回滚**: ROLLBACK-004

---

**DEPLOY-005: 推送 v0.2.0 修改的源文件**

- **组件**: v0.2.0 增强的现有模块文件 + 前端修改文件
- **修改文件清单**:

  | 文件路径 | 变更类型 | 说明 |
  |---------|---------|------|
  | `src/api/inspection_router.py` | 增强 | 新增 6 个端点 + 增强 4 个端点 |
  | `src/database/inspection_models.py` | 增强 | InspectionRecord 新增 status 字段 |
  | `src/database/repositories/inspection_repository.py` | 增强 | 新增 retry_backoff 配置项 + unit 文件生成触发方法 |
  | `src/main.py` | 修改 | 移除 APScheduler 初始化代码 |
  | `requirements.txt` | 修改 | 移除 apscheduler 依赖 |
  | `webui/src/views/inspection/InspectionConfigView.vue` | 增强 | 新增状态面板 + 控制按钮组 |
  | `webui/src/stores/inspection.ts` | 增强 | 新增 6 个 Pinia store actions |

- **操作**:
  ```bash
  # 先在 VPS 上备份每个即将覆盖的文件
  plink root@47.109.197.217 "for f in \
    src/api/inspection_router.py \
    src/database/inspection_models.py \
    src/database/repositories/inspection_repository.py \
    src/main.py \
    requirements.txt \
    webui/src/views/inspection/InspectionConfigView.vue \
    webui/src/stores/inspection.ts; do \
    cp /opt/NetworkAgentDemo/\$f /opt/NetworkAgentDemo/\$f.v0.1.0.bak 2>/dev/null; done && echo 'ALL_BACKED_UP'"
  ```
  ```powershell
  # 在本地 Windows PowerShell 中使用 pscp 上传修改后的文件
  pscp "C:\...\src\api\inspection_router.py" root@47.109.197.217:/opt/NetworkAgentDemo/src/api/inspection_router.py
  pscp "C:\...\src\database\inspection_models.py" root@47.109.197.217:/opt/NetworkAgentDemo/src/database/inspection_models.py
  pscp "C:\...\src\database\repositories\inspection_repository.py" root@47.109.197.217:/opt/NetworkAgentDemo/src/database/repositories/inspection_repository.py
  pscp "C:\...\src\main.py" root@47.109.197.217:/opt/NetworkAgentDemo/src/main.py
  pscp "C:\...\requirements.txt" root@47.109.197.217:/opt/NetworkAgentDemo/requirements.txt
  pscp "C:\...\webui\src\views\inspection\InspectionConfigView.vue" root@47.109.197.217:/opt/NetworkAgentDemo/webui/src/views/inspection/InspectionConfigView.vue
  pscp "C:\...\webui\src\stores\inspection.ts" root@47.109.197.217:/opt/NetworkAgentDemo/webui/src/stores/inspection.ts
  ```
  ```bash
  # 验证关键文件已更新
  plink root@47.109.197.217 "grep -c 'systemd' /opt/NetworkAgentDemo/src/api/inspection_router.py && echo 'ROUTER_UPDATED'"
  plink root@47.109.197.217 "grep -c 'status' /opt/NetworkAgentDemo/src/database/inspection_models.py && echo 'MODELS_UPDATED'"
  plink root@47.109.197.217 "grep 'DEPRECATED.*v0.2.0.*APScheduler' /opt/NetworkAgentDemo/src/main.py && echo 'MAIN_UPDATED'"
  plink root@47.109.197.217 "grep 'DEPRECATED.*apscheduler' /opt/NetworkAgentDemo/requirements.txt && echo 'REQS_UPDATED'"
  ```
- **预期结果**:
  - 所有 7 个修改文件已覆盖上传
  - `inspection_router.py` 含 systemd 相关代码
  - `main.py` 中 APScheduler 初始化代码已标记 DEPRECATED
  - `requirements.txt` 中 apscheduler 已标记 DEPRECATED
- **对应回滚**: ROLLBACK-005

---

**DEPLOY-006: 安装/更新 Python 依赖**

- **组件**: Python virtual environment（移除 apscheduler，依赖列表不变更其他包）
- **操作**:
  ```bash
  # 1. 使用 python3.11 激活 venv
  plink root@47.109.197.217 "cd /opt/NetworkAgentDemo && source venv/bin/activate && python3.11 --version"

  # 2. 升级 pip
  plink root@47.109.197.217 "cd /opt/NetworkAgentDemo && source venv/bin/activate && pip install --upgrade pip"

  # 3. 安装依赖（apscheduler 已从 requirements.txt 中注释掉，不会安装）
  plink root@47.109.197.217 "cd /opt/NetworkAgentDemo && source venv/bin/activate && pip install -r requirements.txt"

  # 4. 验证 apscheduler 未安装
  plink root@47.109.197.217 "cd /opt/NetworkAgentDemo && source venv/bin/activate && pip show apscheduler 2>&1 || echo 'APSCHEDULER_NOT_INSTALLED_OK'"

  # 5. 验证关键依赖已安装
  plink root@47.109.197.217 "cd /opt/NetworkAgentDemo && source venv/bin/activate && pip show sqlalchemy jinja2 fastapi uvicorn | grep -E '^Name:|^Version:'"
  ```
- **预期结果**:
  - pip install 退出码 0
  - `pip show apscheduler` 返回 "not found"（确认已移除）
  - sqlalchemy, jinja2, fastapi, uvicorn 均已安装且版本满足要求
- **对应回滚**: ROLLBACK-006
- **备注**: 由于 requirements.txt 中 apscheduler 已注释为 `# [DEPRECATED v0.2.0]`，pip install 不会安装该包。若 VPS 上之前的 venv 曾安装过 apscheduler，需手动卸载：`pip uninstall -y apscheduler`。

---

**DEPLOY-007: 部署 systemd Unit 文件（初始默认配置）**

- **组件**: `/etc/systemd/system/networkagent-inspection.service` + `/etc/systemd/system/networkagent-inspection.timer`
- **操作**:
  ```bash
  # 1. 渲染 Jinja2 模板生成初始 unit 文件（使用默认配置值）
  #    默认值来源: config.yaml inspection.interval_minutes=5, diagnosis.timeout_seconds=30
  #    在 VPS 上使用 python3.11 渲染模板
  plink root@47.109.197.217 "cd /opt/NetworkAgentDemo && python3.11 -c \"
  from jinja2 import Environment, FileSystemLoader
  env = Environment(loader=FileSystemLoader('resources/templates/systemd'))
  
  # service unit
  svc_tmpl = env.get_template('networkagent-inspection.service.j2')
  svc_content = svc_tmpl.render(
      working_directory='/opt/NetworkAgentDemo',
      user='networkagent',
      python_bin='python3.11',
      timeout_stop_sec=30,
      restart_sec=30,
  )
  with open('/etc/systemd/system/networkagent-inspection.service', 'w') as f:
      f.write(svc_content)
  print('SERVICE_UNIT_WRITTEN')
  
  # timer unit
  tmr_tmpl = env.get_template('networkagent-inspection.timer.j2')
  tmr_content = tmr_tmpl.render(
      on_unit_active_sec=300,
      accuracy_sec=1,
  )
  with open('/etc/systemd/system/networkagent-inspection.timer', 'w') as f:
      f.write(tmr_content)
  print('TIMER_UNIT_WRITTEN')
  \""

  # 2. 验证 unit 文件内容
  plink root@47.109.197.217 "echo '=== SERVICE UNIT ===' && cat /etc/systemd/system/networkagent-inspection.service"
  plink root@47.109.197.217 "echo '=== TIMER UNIT ===' && cat /etc/systemd/system/networkagent-inspection.timer"

  # 3. systemd-analyze verify 语法校验
  plink root@47.109.197.217 "systemd-analyze verify /etc/systemd/system/networkagent-inspection.service 2>&1 && echo 'SERVICE_VERIFY_OK'"
  plink root@47.109.197.217 "systemd-analyze verify /etc/systemd/system/networkagent-inspection.timer 2>&1 && echo 'TIMER_VERIFY_OK'"

  # 4. 设置 unit 文件权限（root 拥有，644）
  plink root@47.109.197.217 "chmod 644 /etc/systemd/system/networkagent-inspection.service /etc/systemd/system/networkagent-inspection.timer"
  ```
- **预期结果**:
  - `networkagent-inspection.service` 写入成功，内容包含:
    - `[Service] Type=oneshot`
    - `ExecStart=python3.11 -m src.inspection_cli run`
    - `WorkingDirectory=/opt/NetworkAgentDemo`
    - `User=networkagent`
    - `Restart=on-failure`
    - `TimeoutStopSec=30`
    - `StandardOutput=journal`, `StandardError=journal`
  - `networkagent-inspection.timer` 写入成功，内容包含:
    - `[Timer] OnUnitActiveSec=300`
    - `Unit=networkagent-inspection.service`
    - `Persistent=true`
    - `AccuracySec=1s`
  - `systemd-analyze verify` 两次验证均通过
- **对应回滚**: ROLLBACK-007
- **备注**: 
  - 初始 unit 文件使用 config.yaml 默认值渲染（interval_minutes=5 → 300s, timeout_seconds=30）。
  - Timer **不启用、不启动**（enable/start 由运维人员通过 Web UI 首次配置后执行）。
  - 之后运维人员通过 Web UI 修改巡检配置时，MOD-INSP-001 会自动重新渲染并覆写这些文件（REQ-INSP-013）。

---

**DEPLOY-008: 配置 sudoers 权限**

- **组件**: `/etc/sudoers.d/networkagent` — 授权 networkagent 用户免密码执行 systemctl 命令
- **操作**:
  ```bash
  # 1. 创建 sudoers 配置文件（使用 visudo 安全方式）
  plink root@47.109.197.217 "cat > /tmp/networkagent_sudoers << 'SUDOERS_EOF'
  # NetworkAgentDemo v0.2.0 — systemd 巡检权限
  # 授权 networkagent 用户免密码管理 networkagent-inspection 相关 unit
  networkagent ALL=(root) NOPASSWD: /usr/bin/systemctl * networkagent-inspection.*
  networkagent ALL=(root) NOPASSWD: /usr/bin/systemd-analyze verify /etc/systemd/system/networkagent-inspection.*
  SUDOERS_EOF
  "

  # 2. 语法校验
  plink root@47.109.197.217 "visudo -c -f /tmp/networkagent_sudoers && echo 'SUDOERS_SYNTAX_OK'"

  # 3. 安装到正式路径并设置正确权限
  plink root@47.109.197.217 "cp /tmp/networkagent_sudoers /etc/sudoers.d/networkagent && chmod 440 /etc/sudoers.d/networkagent && echo 'SUDOERS_INSTALLED'"

  # 4. 验证文件存在且权限正确
  plink root@47.109.197.217 "ls -la /etc/sudoers.d/networkagent"
  ```
- **预期结果**:
  - `/etc/sudoers.d/networkagent` 文件存在
  - 权限为 `-r--r-----` (0440)
  - visudo 语法校验通过
  - 内容精确授权 `networkagent-inspection.*` 相关操作
- **对应回滚**: ROLLBACK-008
- **备注**: 
  - sudoers 白名单模式 (ADR-INSP-002 Option A)，仅授权 networkagent-inspection 相关命令
  - 不授权其他 systemctl 操作，最小权限原则
  - 若部署时 networkagent 用户尚未创建（DEPLOY-003），sudoers 文件语法仍然有效（用户后续创建后生效）

---

**DEPLOY-009: 设置 NETWORKAGENT_HOME 环境变量**

- **组件**: 环境变量配置注入到 systemd service 的 Environment 中
- **操作**:
  ```bash
  # 1. 检查现有 .env 文件中是否已有 NETWORKAGENT_HOME
  plink root@47.109.197.217 "grep 'NETWORKAGENT_HOME' /opt/NetworkAgentDemo/.env 2>/dev/null || echo 'NOT_SET'"

  # 2. 若未设置，追加到 .env 文件
  plink root@47.109.197.217 "grep -q 'NETWORKAGENT_HOME' /opt/NetworkAgentDemo/.env 2>/dev/null || echo 'NETWORKAGENT_HOME=/opt/NetworkAgentDemo' >> /opt/NetworkAgentDemo/.env"

  # 3. 验证环境变量已设置
  plink root@47.109.197.217 "grep 'NETWORKAGENT_HOME' /opt/NetworkAgentDemo/.env"
  ```
- **预期结果**:
  - `.env` 文件中包含 `NETWORKAGENT_HOME=/opt/NetworkAgentDemo`
  - 若已存在则不重复添加（幂等操作）
- **对应回滚**: ROLLBACK-009
- **备注**: 
  - `NETWORKAGENT_HOME` 由 MOD-016 (ConfigManager) 和 MOD-INSP-001 (systemd_unit_manager) 读取，用于确定 WorkingDirectory
  - 环境变量通过 systemd service 的 `EnvironmentFile=/opt/NetworkAgentDemo/.env` 注入（已在 v0.2.0 DEPLOY-007 service 文件中配置）

---

**DEPLOY-010: 执行 systemctl daemon-reload**

- **组件**: systemd 守护进程 — 重新加载所有 unit 文件配置
- **操作**:
  ```bash
  # 1. 执行 daemon-reload
  plink root@47.109.197.217 "systemctl daemon-reload && echo 'DAEMON_RELOAD_OK'"

  # 2. 验证新 unit 文件已被 systemd 识别
  plink root@47.109.197.217 "systemctl status networkagent-inspection.service --no-pager 2>&1 | head -5"
  plink root@47.109.197.217 "systemctl status networkagent-inspection.timer --no-pager 2>&1 | head -5"

  # 3. 确认 timer 处于 inactive + disabled 状态（未被自动启动）
  plink root@47.109.197.217 "systemctl is-active networkagent-inspection.timer || echo 'TIMER_INACTIVE_OK'"
  plink root@47.109.197.217 "systemctl is-enabled networkagent-inspection.timer 2>&1 || echo 'TIMER_DISABLED_OK'"
  ```
- **预期结果**:
  - `systemctl daemon-reload` 执行成功（无错误输出）
  - `systemctl status networkagent-inspection.service` 识别到新 unit，状态为 `inactive (dead)`
  - `systemctl status networkagent-inspection.timer` 识别到新 unit，状态为 `inactive (dead)`
  - timer 的 `is-enabled` 返回 `disabled`（未被自动启用）
- **对应回滚**: ROLLBACK-010 (恢复旧 unit 文件 + daemon-reload)
- **备注**: daemon-reload 会通知 systemd 重新扫描所有 unit 文件目录，这是新 unit 文件生效的必要步骤。不会影响正在运行的服务。

---

**DEPLOY-011: 重启 networkagent.service（Web 进程）**

- **组件**: networkagent.service（systemd 管理的 uvicorn FastAPI 进程，端口 8001）
- **操作**:
  ```bash
  # 1. 重新加载 systemd 配置（确保 service 文件最新）
  plink root@47.109.197.217 "systemctl daemon-reload"

  # 2. 启动 networkagent 服务
  plink root@47.109.197.217 "systemctl start networkagent"

  # 3. 等待服务启动
  plink root@47.109.197.217 "sleep 5"

  # 4. 检查服务状态
  plink root@47.109.197.217 "systemctl status networkagent --no-pager"

  # 5. 验证端口监听
  plink root@47.109.197.217 "ss -tlnp | grep 8001"
  ```
- **预期结果**:
  - `systemctl status networkagent` 显示 `active (running)`
  - 端口 8001 在监听（LISTEN 状态）
  - 日志中无 FATAL/CRITICAL 级别错误
  - 日志确认 "NetworkAgentDemo v0.2.0 — Starting up..." 出现
  - 日志确认 APScheduler 初始化日志不再出现（"NetworkAgentDemo is ready!" 之前无 scheduler 相关日志）
- **对应回滚**: ROLLBACK-011
- **备注**: 
  - 巡检 CLI 进程（若此前在运行）不受 Web 进程重启影响（进程隔离，REQ-INSP-NF-004）
  - 重启后 systemd timer 巡检配置不变

---

**DEPLOY-012: 前端重新构建（npm install + npm build）**

- **组件**: `webui/` → `webui/dist/`（Vue 3 + Vite 生产构建，含增强的巡检配置页面）
- **操作**:
  ```bash
  # 1. 进入 webui 目录
  plink root@47.109.197.217 "cd /opt/NetworkAgentDemo/webui && pwd"

  # 2. 安装依赖（如有新增/更新）
  plink root@47.109.197.217 "cd /opt/NetworkAgentDemo/webui && npm install 2>&1 | tail -5"

  # 3. 执行生产构建
  plink root@47.109.197.217 "cd /opt/NetworkAgentDemo/webui && npm run build 2>&1 | tail -10"

  # 4. 验证构建产物
  plink root@47.109.197.217 "ls -la /opt/NetworkAgentDemo/webui/dist/index.html && echo 'BUILD_OK'"
  plink root@47.109.197.217 "ls /opt/NetworkAgentDemo/webui/dist/assets/ | head -5"
  ```
- **预期结果**:
  - `npm install` 退出码 0
  - `npm run build` 退出码 0
  - `webui/dist/index.html` 存在
  - `webui/dist/assets/` 含 JS/CSS 构建产物
- **对应回滚**: ROLLBACK-012
- **备注**: 
  - 前端构建在 VPS 上执行（需要 Node.js >= 20）
  - 若 VPS 上 Node.js 版本不足，可在本地构建后将 `webui/dist/` 上传至 VPS
  - 新构建包含增强的 InspectionConfigView.vue（状态面板 + 控制按钮组）

---

**DEPLOY-013: 后端健康检查验证**

- **组件**: FastAPI Web 进程（端口 8001）+ 巡检 CLI（独立进程）
- **操作**:
  ```bash
  # 1. 原有 /health 端点
  plink root@47.109.197.217 "curl -s http://localhost:8001/health | python3.11 -m json.tool"

  # 2. Web UI 仪表盘健康检查
  plink root@47.109.197.217 "curl -s http://localhost:8001/api/dashboard/health"

  # 3. 巡检配置端点（v0.1.0 保留）
  plink root@47.109.197.217 "curl -s http://localhost:8001/api/inspection/config | python3.11 -m json.tool"

  # 4. 巡检状态端点（v0.2.0 新增）
  plink root@47.109.197.217 "curl -s http://localhost:8001/api/inspection/status | python3.11 -m json.tool"

  # 5. Web UI 静态文件挂载
  plink root@47.109.197.217 "curl -s -o /dev/null -w '%{http_code}' http://localhost:8001/"

  # 6. API 文档可访问
  plink root@47.109.197.217 "curl -s -o /dev/null -w '%{http_code}' http://localhost:8001/docs"

  # 7. 外部可达性
  curl -s --connect-timeout 5 http://47.109.197.217:8001/health
  ```
- **预期结果**:
  - `/health` 返回 `{"status":"healthy","service":"NetworkAgentDemo","version":"0.2.0",...}`，HTTP 200
  - `/api/dashboard/health` 返回 Web UI 健康状态，HTTP 200
  - `/api/inspection/config` 返回巡检配置（含 retry_backoff 字段），HTTP 200
  - `/api/inspection/status` 返回 systemd 状态（timer + service），HTTP 200
  - `/` (SPA root) 返回 HTTP 200（index.html）
  - `/docs` 返回 HTTP 200（OpenAPI 文档）
  - 外部可达性验证 HTTP 200
- **对应回滚**: ROLLBACK-013 (验证步骤，无回滚操作)

---

**DEPLOY-014: Web UI 巡检配置页面功能验证**

- **组件**: Web UI 巡检配置页面（InspectionConfigView.vue 增强版）
- **操作**:
  ```bash
  # 1. 验证巡检配置 API 返回 v0.2.0 新增字段
  plink root@47.109.197.217 "curl -s http://localhost:8001/api/inspection/config | python3.11 -c \"import sys,json; d=json.load(sys.stdin); print('retry_backoff' in str(d))\""

  # 2. 验证巡检状态 API 包含 systemd 信息
  plink root@47.109.197.217 "curl -s http://localhost:8001/api/inspection/status | python3.11 -c \"import sys,json; d=json.load(sys.stdin); print('timer' in d, 'service' in d, 'systemd_available' in d)\""

  # 3. 验证巡检历史 API 包含 status 字段
  plink root@47.109.197.217 "curl -s 'http://localhost:8001/api/inspection/history?page=1&page_size=1' | python3.11 -c \"import sys,json; d=json.load(sys.stdin); print('items' in d)\""

  # 4. 验证 Web UI 首页可加载（SPA）
  plink root@47.109.197.217 "curl -s http://localhost:8001/ | head -c 200"
  ```
- **预期结果**:
  - 巡检配置 API 返回含 `retry_backoff`（v0.2.0 新增配置项）
  - 巡检状态 API 返回 `timer` + `service` + `systemd_available` 字段
  - 巡检历史 API 返回 items 列表（含 status 字段）
  - Web UI 首页加载正常（HTML 含 `<div id="app">`）
- **对应回滚**: ROLLBACK-014 (验证步骤，无回滚操作)
- **备注**: 
  - 巡检控制按钮（start/stop/restart/enable/disable）的后端 API 已在 DEPLOY-013 健康检查中间接验证（systemd status API 正常即表明 systemctl_executor 模块加载成功）
  - 完整的 Web UI 交互验证应通过浏览器访问 `http://47.109.197.217:8001/`，登录后检查巡检配置页面

---

**DEPLOY-015: GenPlatform 完整性验证**

- **组件**: GenPlatform（端口 80/8000），**验证不被破坏，不执行任何变更**
- **操作**:
  ```bash
  # 1. GenPlatform backend 服务状态
  plink root@47.109.197.217 "systemctl is-active genplatform-backend"

  # 2. GenPlatform backend 端口 8000
  plink root@47.109.197.217 "curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/"

  # 3. GenPlatform front-end 端口 80
  plink root@47.109.197.217 "curl -s -o /dev/null -w '%{http_code}' http://localhost:80/"

  # 4. 确认 8001 端口仅为 NetworkAgentDemo 占用
  plink root@47.109.197.217 "ss -tlnp | grep -E ':80\b|:8000\b|:8001\b'"
  ```
- **预期结果**:
  - `genplatform-backend.service` 状态为 `active`
  - 端口 8000 返回 HTTP 200（GenPlatform backend）
  - 端口 80 返回 HTTP 200（GenPlatform front-end）
  - 端口分配确认正确（80=nginx, 8000=gunicorn/uvicorn, 8001=networkagent）
- **对应回滚**: ROLLBACK-015 (验证步骤，无回滚操作)
- **备注**: 纯验证步骤，不执行任何系统变更。若 GenPlatform 异常，此为预先存在的问题，不应回滚 NetworkAgentDemo 部署。

---

## 回滚步骤（逆向，按逆序排列）

> **回滚原则**: 逆序执行（最后部署的组件最先回滚），每步精确逆转对应 DEPLOY-NNN 的操作。
> **回滚基准**: v0.1.0 状态（APScheduler 巡检 + Web UI v0.1.0）

---

**ROLLBACK-015: GenPlatform 验证（无需回滚）**

- **回滚操作**: 无。此为验证步骤，不涉及状态变更。
- **预期结果**: N/A

---

**ROLLBACK-014: Web UI 功能验证（无需回滚）**

- **回滚操作**: 无。此为验证步骤，不涉及状态变更。
- **预期结果**: N/A

---

**ROLLBACK-013: 健康检查验证（无需回滚）**

- **回滚操作**: 无。此为验证步骤，不涉及状态变更。
- **预期结果**: N/A

---

**ROLLBACK-012: 恢复前端构建产物（使用 v0.1.0 备份）**

- **回滚操作**:
  ```bash
  # 1. 清理 v0.2.0 构建产物
  plink root@47.109.197.217 "rm -rf /opt/NetworkAgentDemo/webui/dist /opt/NetworkAgentDemo/webui/node_modules"
  
  # 2. 从备份恢复 v0.1.0 前端文件（若 v0.1.0 有前端）
  plink root@47.109.197.217 "BACKUP=\$(ls -dt /opt/NetworkAgentDemo.backup.*/ | head -1) && if [ -d \"\$BACKUP/webui/dist\" ]; then cp -r \"\$BACKUP/webui/dist\" /opt/NetworkAgentDemo/webui/dist && echo 'UI_RESTORED'; else echo 'NO_UI_BACKUP'; fi"
  ```
- **预期结果**: webui/dist/ 恢复为 v0.1.0 版本（或清理至无构建产物状态）

---

**ROLLBACK-011: 停止 v0.2.0 Web 进程，恢复 v0.1.0 进程**

- **回滚操作**:
  ```bash
  # 1. 停止当前 Web 服务
  plink root@47.109.197.217 "systemctl stop networkagent"

  # 2. 恢复 v0.1.0 systemd service 文件（从 DEPLOY-002 的备份）
  plink root@47.109.197.217 "LATEST_BAK=\$(ls -t /etc/systemd/system/networkagent.service.backup.* 2>/dev/null | head -1) && if [ -n \"\$LATEST_BAK\" ]; then cp \"\$LATEST_BAK\" /etc/systemd/system/networkagent.service && echo 'SERVICE_RESTORED'; else echo 'NO_SERVICE_BACKUP'; fi"

  # 3. 恢复 v0.1.0 源代码（从 DEPLOY-002 的备份）
  plink root@47.109.197.217 "BACKUP=\$(ls -dt /opt/NetworkAgentDemo.backup.*/ | head -1) && if [ -n \"\$BACKUP\" ]; then rm -rf /opt/NetworkAgentDemo/src && cp -r \"\$BACKUP/src\" /opt/NetworkAgentDemo/src && cp \"\$BACKUP/requirements.txt\" /opt/NetworkAgentDemo/requirements.txt && echo 'SRC_RESTORED'; else echo 'NO_BACKUP_FOR_SRC'; fi"

  # 4. 恢复 v0.1.0 Python 依赖
  plink root@47.109.197.217 "cd /opt/NetworkAgentDemo && source venv/bin/activate && pip install apscheduler>=3.10.0 && echo 'APSCHEDULER_RESTORED'"

  # 5. 重新加载 systemd 并启动服务
  plink root@47.109.197.217 "systemctl daemon-reload && systemctl start networkagent"

  # 6. 验证恢复后服务正常
  plink root@47.109.197.217 "sleep 3 && systemctl is-active networkagent && curl -s http://localhost:8001/health"
  ```
- **预期结果**: networkagent 恢复为 v0.1.0 版本正常运行（APScheduler 巡检 + v0.1.0 Web UI）

---

**ROLLBACK-010: 恢复 daemon-reload 前的 systemd 状态**

- **回滚操作**:
  ```bash
  # 移除新增的 unit 文件后重新加载
  plink root@47.109.197.217 "rm -f /etc/systemd/system/networkagent-inspection.service /etc/systemd/system/networkagent-inspection.timer && systemctl daemon-reload && echo 'UNITS_REMOVED_AND_RELOADED'"
  ```
- **预期结果**: systemd 不再识别 networkagent-inspection 相关 unit

---

**ROLLBACK-009: 移除 NETWORKAGENT_HOME 环境变量**

- **回滚操作**:
  ```bash
  # 从 .env 文件中移除 NETWORKAGENT_HOME 行
  plink root@47.109.197.217 "sed -i '/^NETWORKAGENT_HOME=/d' /opt/NetworkAgentDemo/.env && echo 'ENV_REMOVED'"
  ```
- **预期结果**: `.env` 文件中不再包含 `NETWORKAGENT_HOME=`
- **备注**: 此操作可能影响 v0.1.0 的行为（v0.1.0 不依赖此环境变量，安全删除）

---

**ROLLBACK-008: 移除 sudoers 配置**

- **回滚操作**:
  ```bash
  # 删除 sudoers 配置文件
  plink root@47.109.197.217 "rm -f /etc/sudoers.d/networkagent && echo 'SUDOERS_REMOVED'"
  ```
- **预期结果**: `/etc/sudoers.d/networkagent` 文件不存在
- **备注**: 删除 sudoers 文件后，networkagent 用户将无法执行 systemctl 命令（符合回滚预期——v0.1.0 不需要此权限）

---

**ROLLBACK-007: 移除 systemd unit 文件**

- **回滚操作**:
  ```bash
  # 删除两个 unit 文件
  plink root@47.109.197.217 "rm -f /etc/systemd/system/networkagent-inspection.service /etc/systemd/system/networkagent-inspection.timer && echo 'UNITS_REMOVED'"

  # 重新加载 systemd（清除缓存）
  plink root@47.109.197.217 "systemctl daemon-reload && echo 'RELOADED'"
  ```
- **预期结果**: 
  - `/etc/systemd/system/` 下不再存在 `networkagent-inspection.*` 文件
  - systemd 已重新加载，不再识别这些 unit

---

**ROLLBACK-006: 恢复 Python 依赖为 v0.1.0 状态**

- **回滚操作**:
  ```bash
  # 1. 恢复 v0.1.0 requirements.txt
  plink root@47.109.197.217 "BACKUP=\$(ls -dt /opt/NetworkAgentDemo.backup.*/ | head -1) && cp \"\$BACKUP/requirements.txt\" /opt/NetworkAgentDemo/requirements.txt"

  # 2. 重新安装 apscheduler
  plink root@47.109.197.217 "cd /opt/NetworkAgentDemo && source venv/bin/activate && pip install apscheduler>=3.10.0 && echo 'APSCHEDULER_RESTORED'"

  # 3. 重新安装 v0.1.0 完整依赖集
  plink root@47.109.197.217 "cd /opt/NetworkAgentDemo && source venv/bin/activate && pip install -r requirements.txt && echo 'DEPS_RESTORED'"
  ```
- **预期结果**: 
  - requirements.txt 恢复为 v0.1.0 版本
  - apscheduler 重新安装
  - 所有依赖版本与 v0.1.0 一致

---

**ROLLBACK-005: 恢复修改的源文件为 v0.1.0 版本**

- **回滚操作**:
  ```bash
  # 从备份恢复到 v0.1.0 版本的 7 个修改文件
  plink root@47.109.197.217 "BACKUP=\$(ls -dt /opt/NetworkAgentDemo.backup.*/ | head -1) && \
    for f in \
      src/api/inspection_router.py \
      src/database/inspection_models.py \
      src/database/repositories/inspection_repository.py \
      src/main.py \
      requirements.txt \
      webui/src/views/inspection/InspectionConfigView.vue \
      webui/src/stores/inspection.ts; do \
      cp \"\$BACKUP/\$f\" /opt/NetworkAgentDemo/\$f && echo \"RESTORED: \$f\"; \
    done && echo 'ALL_MODIFIED_FILES_RESTORED'"
  ```
- **预期结果**: 所有 7 个修改文件恢复为 v0.1.0 版本内容

---

**ROLLBACK-004: 移除 v0.2.0 新增源文件**

- **回滚操作**:
  ```bash
  # 删除 v0.2.0 新增的文件和目录
  plink root@47.109.197.217 "rm -rf /opt/NetworkAgentDemo/src/systemd/ && rm -f /opt/NetworkAgentDemo/src/inspection_cli.py && rm -rf /opt/NetworkAgentDemo/resources/templates/systemd/ && echo 'NEW_FILES_REMOVED'"
  ```
- **预期结果**: 
  - `src/systemd/` 目录不存在
  - `src/inspection_cli.py` 不存在
  - `resources/templates/systemd/` 目录不存在

---

**ROLLBACK-003: 移除 networkagent 用户**

- **回滚操作**:
  ```bash
  # 删除 networkagent 用户（谨慎操作）
  plink root@47.109.197.217 "id networkagent 2>/dev/null && userdel networkagent && echo 'USER_REMOVED' || echo 'USER_NOT_FOUND'"
  ```
- **预期结果**: `networkagent` 用户被删除
- **备注**: 
  - 若该用户在 v0.1.0 部署中已存在，此操作可能导致其他依赖该用户的服务受影响
  - **[MANUAL_ROLLBACK_REQUIRED]** 若 networkagent 用户曾属于其他组或有额外配置，需手动恢复。建议在 DEPLOY-003 执行前记录 `id networkagent` 的输出

---

**ROLLBACK-002: 完整恢复备份（从 DEPLOY-001 的备份恢复整个系统）**

- **回滚操作**:
  ```bash
  # 1. 停止当前服务
  plink root@47.109.197.217 "systemctl stop networkagent"

  # 2. 删除当前部署
  plink root@47.109.197.217 "rm -rf /opt/NetworkAgentDemo"

  # 3. 从备份完整恢复（使用最新的备份）
  plink root@47.109.197.217 "LATEST_BAK=\$(ls -dt /opt/NetworkAgentDemo.backup.*/ | head -1) && cp -a \"\$LATEST_BAK\" /opt/NetworkAgentDemo && echo 'FULL_RESTORE_DONE'"

  # 4. 恢复 systemd service 文件
  plink root@47.109.197.217 "LATEST_SVC_BAK=\$(ls -t /etc/systemd/system/networkagent.service.backup.* 2>/dev/null | head -1) && if [ -n \"\$LATEST_SVC_BAK\" ]; then cp \"\$LATEST_SVC_BAK\" /etc/systemd/system/networkagent.service && echo 'SERVICE_RESTORED'; fi"

  # 5. 清理 v0.2.0 systemd unit 文件
  plink root@47.109.197.217 "rm -f /etc/systemd/system/networkagent-inspection.service /etc/systemd/system/networkagent-inspection.timer"

  # 6. 清理 sudoers
  plink root@47.109.197.217 "rm -f /etc/sudoers.d/networkagent"

  # 7. 重新加载 systemd
  plink root@47.109.197.217 "systemctl daemon-reload"

  # 8. 启动恢复后的服务
  plink root@47.109.197.217 "systemctl start networkagent"

  # 9. 验证恢复
  plink root@47.109.197.217 "sleep 3 && systemctl is-active networkagent && curl -s http://localhost:8001/health && echo 'RECOVERY_VERIFIED'"
  ```
- **预期结果**: 系统完整恢复为 v0.1.0 部署状态，所有服务正常运行

---

**ROLLBACK-001: SSH 预检（无需回滚）**

- **回滚操作**: 无。此为验证步骤，不涉及状态变更。
- **预期结果**: N/A

---

## 部署后验证清单（Post-deployment Verification）

| 检查项 ID | 检查项 | 检查方法（命令/URL/工具）| 成功标准 |
|-----------|--------|----------------------|---------|
| VERIFY-01 | networkagent.service 运行状态 | `systemctl is-active networkagent` | `active` |
| VERIFY-02 | 端口 8001 监听 | `ss -tlnp \| grep 8001` | LISTEN 状态，归属 networkagent |
| VERIFY-03 | /health 端点 | `curl -s http://localhost:8001/health` | HTTP 200, `"version":"0.2.0"`, `"status":"healthy"`, components 中无 scheduler |
| VERIFY-04 | /api/dashboard/health | `curl -s http://localhost:8001/api/dashboard/health` | HTTP 200 |
| VERIFY-05 | /api/inspection/config | `curl -s http://localhost:8001/api/inspection/config \| python3.11 -m json.tool` | HTTP 200, 返回含 `retry_backoff` 字段 |
| VERIFY-06 | /api/inspection/status | `curl -s http://localhost:8001/api/inspection/status \| python3.11 -m json.tool` | HTTP 200, 返回 `timer` + `service` + `systemd_available` |
| VERIFY-07 | /api/inspection/history | `curl -s 'http://localhost:8001/api/inspection/history?page=1&page_size=1'` | HTTP 200, items 列表 |
| VERIFY-08 | Web UI SPA 首页 | `curl -s http://localhost:8001/ \| head -c 100` | HTTP 200, HTML 含 `<div id="app">` |
| VERIFY-09 | API 文档 | `curl -s -o /dev/null -w '%{http_code}' http://localhost:8001/docs` | HTTP 200 |
| VERIFY-10 | systemd unit 文件存在 | `ls -la /etc/systemd/system/networkagent-inspection.service /etc/systemd/system/networkagent-inspection.timer` | 两个文件存在，权限 644 |
| VERIFY-11 | systemd unit 语法正确 | `systemd-analyze verify /etc/systemd/system/networkagent-inspection.service && systemd-analyze verify /etc/systemd/system/networkagent-inspection.timer` | 两次 verify 均无错误 |
| VERIFY-12 | timer 未被自动启动 | `systemctl is-active networkagent-inspection.timer; systemctl is-enabled networkagent-inspection.timer` | `inactive` + `disabled`（或 `not-found` 若 unit 未生成）|
| VERIFY-13 | sudoers 配置正确 | `cat /etc/sudoers.d/networkagent` | 内容含 `networkagent ALL=(root) NOPASSWD: /usr/bin/systemctl * networkagent-inspection.*` |
| VERIFY-14 | networkagent 用户存在 | `id networkagent` | 输出含 uid, gid, groups |
| VERIFY-15 | NETWORKAGENT_HOME 环境变量 | `grep NETWORKAGENT_HOME /opt/NetworkAgentDemo/.env` | `NETWORKAGENT_HOME=/opt/NetworkAgentDemo` |
| VERIFY-16 | 前端构建产物 | `ls /opt/NetworkAgentDemo/webui/dist/index.html` | 文件存在 |
| VERIFY-17 | apscheduler 未安装 | `cd /opt/NetworkAgentDemo && source venv/bin/activate && pip show apscheduler 2>&1 \|\| echo 'OK'` | 输出 `OK`（包未找到）|
| VERIFY-18 | src/systemd/ 模块存在 | `ls /opt/NetworkAgentDemo/src/systemd/__init__.py /opt/NetworkAgentDemo/src/systemd/systemctl_executor.py /opt/NetworkAgentDemo/src/systemd/systemd_unit_manager.py` | 三个文件存在 |
| VERIFY-19 | src/inspection_cli.py 存在 | `ls /opt/NetworkAgentDemo/src/inspection_cli.py` | 文件存在 |
| VERIFY-20 | Jinja2 模板文件存在 | `ls /opt/NetworkAgentDemo/resources/templates/systemd/networkagent-inspection.service.j2 /opt/NetworkAgentDemo/resources/templates/systemd/networkagent-inspection.timer.j2` | 两个文件存在 |
| VERIFY-21 | 日志无 ERROR | `journalctl -u networkagent -n 50 --no-pager \| grep -i error \| wc -l` | 0 或仅含非关键错误 |
| VERIFY-22 | GenPlatform 后端未受影响 | `systemctl is-active genplatform-backend` | `active` |
| VERIFY-23 | GenPlatform 前端未受影响 | `curl -s -o /dev/null -w '%{http_code}' http://localhost:80/` | HTTP 200 |
| VERIFY-24 | GenPlatform 后端端口 | `curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/` | HTTP 200 |
| VERIFY-25 | 外部可达性 | `curl -s --connect-timeout 5 http://47.109.197.217:8001/health` | HTTP 200 |

---

## 部署后运维指引

### Timer 启用流程（运维人员通过 Web UI 首次配置后执行）

1. 运维人员登录 Web UI (http://47.109.197.217:8001/)
2. 进入"巡检配置"页面
3. 配置巡检参数（interval_minutes, timeout_seconds, retry_max, retry_backoff）
4. 点击"保存配置"——系统自动：
   - 将配置写入 SQLite
   - 重新渲染 systemd unit 文件（使用最新参数）
   - 执行 `systemctl daemon-reload`
   - 若 timer 此前为 active，自动 restart timer
5. 首次配置完成后，点击"启用"按钮——系统执行 `systemctl enable --now networkagent-inspection.timer`
6. 状态面板显示 timer 为 `active + enabled`，下次触发时间开始倒计时

### 后续配置变更流程

- 运维人员修改巡检参数并保存 → 系统自动同步到 systemd unit 文件
- 若 timer 为 active 状态 → 自动 restart timer 使用新配置
- 若 timer 为 inactive → 仅更新 unit 文件，下次 enable 时使用新配置

### 手动触发巡检

- Web UI 点击"手动触发巡检"按钮 → 系统通过 `systemctl start networkagent-inspection.service` 执行
- 手动触发不依赖 timer 状态（即使 timer disabled 也可手动触发）
- 巡检结果持久化至 SQLite InspectionRecord 表（trigger_mode=MANUAL）

---

## 安全约束重申

| 约束 | 确保方式 |
|------|---------|
| **绝对禁止 pkill -f gunicorn** | 任何部署/回滚命令中不包含 pkill、killall gunicorn 等操作；仅使用 systemctl 管理 networkagent 服务 |
| **只操作 8001 端口** | 部署和验证命令仅检查 8001；不修改 80/8000 相关 iptables 规则或服务配置 |
| **只操作 networkagent.* 服务** | 所有 systemctl 操作限定于 networkagent 和 networkagent-inspection 两个 unit |
| **Python 必须用 python3.11** | 所有部署命令明确使用 `/usr/bin/python3.11` 或 `python3.11` 路径；不依赖系统默认 python3 |
| **部署失败立即回滚** | 任一步骤失败暂停后续步骤，从当前步骤开始逆序执行 ROLLBACK-NNN |
| **不自动启用 timer** | DEPLOY-007 仅部署 unit 文件，不执行 enable/start；timer 由运维人员通过 Web UI 手动启用 |
| **防火墙使用 iptables + 阿里云安全组** | firewall 未运行，不操作 firewall-cmd；端口放行通过 iptables 或阿里云控制台管理 |

---

## 预计耗时

| 步骤 | 预计耗时 | 备注 |
|------|---------|------|
| DEPLOY-001: SSH 预检 | < 10s | 纯验证，无变更 |
| DEPLOY-002: 备份现有部署 | < 30s | 取决于 /opt/NetworkAgentDemo 目录大小 |
| DEPLOY-003: 创建 networkagent 用户 | < 5s | |
| DEPLOY-004: 推送新增源文件 | < 30s | 6 个文件，pscp 上传 |
| DEPLOY-005: 推送修改源文件 | < 30s | 7 个文件，pscp 上传 |
| DEPLOY-006: 安装 Python 依赖 | < 60s | pip install |
| DEPLOY-007: 部署 systemd unit 文件 | < 15s | 模板渲染 + 写入 + verify |
| DEPLOY-008: 配置 sudoers | < 10s | |
| DEPLOY-009: 设置环境变量 | < 5s | |
| DEPLOY-010: systemctl daemon-reload | < 5s | |
| DEPLOY-011: 重启 networkagent.service | < 15s | 含 5s 等待启动 |
| DEPLOY-012: 前端重新构建 | < 120s | npm install + build |
| DEPLOY-013: 后端健康检查 | < 20s | 7 个 curl 命令 |
| DEPLOY-014: Web UI 功能验证 | < 15s | 4 个 curl 命令 |
| DEPLOY-015: GenPlatform 完整性验证 | < 10s | 纯验证 |
| **总计** | **约 6-7 分钟** | |

---

## 回滚预计耗时

| 场景 | 预计耗时 |
|------|---------|
| 单步骤失败回滚（仅回滚 1-2 步）| < 30s |
| 部分回滚（回滚至 DEPLOY-005）| < 2 分钟 |
| 完整回滚（ROLLBACK-002 完整恢复）| < 3 分钟 |
