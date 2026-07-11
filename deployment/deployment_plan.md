<file_header>
  <author_agent>devops_engineer</author_agent>
  <timestamp>2026-07-10T08:00:00Z</timestamp>
  <project_name>NetworkAgentDemo</project_name>
  <version>0.2.0</version>
  <input_files>
    <file>architecture/architecture_design.md</file>
    <file>architecture/tech_stack.md</file>
    <file>testing/unit_test_report.md</file>
    <file>testing/integration_test_report.md</file>
    <file>testing/e2e_test_report.md</file>
    <file>deployment_guide.md</file>
    <file>src/main.py</file>
    <file>requirements.txt</file>
    <file>.env.example</file>
    <file>webui/package.json</file>
  </input_files>
  <phase>PHASE_11</phase>
  <status>DRAFT</status>
</file_header>

# 生产部署计划 — NetworkAgentDemo v0.2.0

**目标环境**: Alibaba Cloud ECS (47.109.197.217)
**部署策略**: 滚动更新（单实例 Demo，先备份再覆盖）
**变更版本**: v0.1.0 (无 Web UI) → v0.2.0 (含 Web UI + JWT 认证 + SQLite 持久化)

---

## 部署前检查清单（Pre-deployment Checklist）

| 检查项 | 检查方法 | 成功标准 | 负责方 |
|--------|---------|---------|--------|
| PRECHK-01: Python 3.11 可用 | `python3.11 --version` | 输出 `Python 3.11.x` | DevOps |
| PRECHK-02: Node.js >= 20 可用 | `node --version` | 输出 `v20.x.x` | DevOps |
| PRECHK-03: 端口 8001 未被其他进程占用 | `ss -tlnp \| grep 8001` | 仅 networkagent 监听 | DevOps |
| PRECHK-04: GenPlatform 正常运行 | `systemctl is-active genplatform-backend` | `active` | DevOps |
| PRECHK-05: 磁盘空间充足 | `df -h /opt` | 可用 > 1GB | DevOps |
| PRECHK-06: Git 可用 | `git --version` | 输出版本号 | DevOps |
| PRECHK-07: 单元测试门控通过 | 读取 `testing/unit_test_report.md` | gate_decision=PASSED (>=80%) | Test Engineer |
| PRECHK-08: 集成测试门控通过 | 读取 `testing/integration_test_report.md` | gate_decision=PASSED (>=90%) | Test Engineer |
| PRECHK-09: E2E 测试门控通过 | 读取 `testing/e2e_test_report.md` | 100% Critical Path 覆盖 | Test Engineer |
| PRECHK-10: architecture_design.md APPROVED | 读取文件 header | status=APPROVED | System Architect |
| PRECHK-11: tech_stack.md APPROVED | 读取文件 header | status=APPROVED | System Architect |
| PRECHK-12: 阿里云安全组放行端口 8001 | 阿里云控制台 | 入方向规则包含 TCP 8001 | DevOps |
| PRECHK-13: iptables 放行端口 8001 | `iptables -L INPUT -n \| grep 8001` | 存在 ACCEPT 规则 | DevOps |

---

## 部署步骤（正向）

---

**DEPLOY-001: 备份现有部署**

- **组件**: 整个 `/opt/NetworkAgentDemo/` 目录（现有 v0.1.0 版本）
- **操作**:
  ```bash
  # 停止服务
  systemctl stop networkagent

  # 创建带时间戳的备份
  cp -r /opt/NetworkAgentDemo /opt/NetworkAgentDemo.backup.$(date +%Y%m%d_%H%M%S)

  # 验证备份
  ls -la /opt/NetworkAgentDemo.backup.*/
  ```
- **预期结果**: 备份目录创建成功，包含完整旧版本文件；networkagent 服务已停止
- **对应回滚**: ROLLBACK-001
- **备注**: 备份目录命名格式: `/opt/NetworkAgentDemo.backup.YYYYMMDD_HHMMSS`

---

**DEPLOY-002: 上传新版本代码**

- **组件**: `src/`（含新增 `src/api/`, `src/database/`, `src/services/`） + `webui/` + `requirements.txt`
- **操作**:
  ```bash
  # 方法A: 从 GitHub 拉取（推荐，如果已推送）
  cd /opt/NetworkAgentDemo
  git pull origin master

  # 方法B: 从本地上传（如果 GitHub 未更新）
  # 使用 pscp 上传 src/、webui/、requirements.txt 到 /opt/NetworkAgentDemo/
  ```
- **预期结果**: VPS 上 `/opt/NetworkAgentDemo/` 目录包含 v0.2.0 完整源码
- **对应回滚**: ROLLBACK-002
- **备注**: 关键新目录: `src/api/` (8 个 API Router), `src/database/` (ORM), `src/services/` (加密+认证), `webui/` (Vue 3 前端)

---

**DEPLOY-003: 创建运行时目录**

- **组件**: `data/` 目录（SQLite 数据文件 + 加密密钥存储）
- **操作**:
  ```bash
  mkdir -p /opt/NetworkAgentDemo/data
  mkdir -p /opt/NetworkAgentDemo/logs
  chmod 755 /opt/NetworkAgentDemo/data
  chmod 755 /opt/NetworkAgentDemo/logs
  ```
- **预期结果**: `data/` 和 `logs/` 目录存在，权限正确
- **对应回滚**: ROLLBACK-003

---

**DEPLOY-004: 安装/更新 Python 依赖**

- **组件**: Python venv + 所有 `requirements.txt` 依赖（含新增 Web UI 依赖）
- **操作**:
  ```bash
  cd /opt/NetworkAgentDemo
  source venv/bin/activate
  pip install --upgrade pip
  pip install -r requirements.txt
  ```
- **预期结果**: 所有依赖安装成功，包含新增的 sqlalchemy, python-jose, passlib, cryptography, aiofiles, python-multipart
- **对应回滚**: ROLLBACK-004
- **备注**: 新增依赖（v0.2.0）:
  - `sqlalchemy>=2.0.0` — ORM 数据库
  - `python-jose[cryptography]>=3.3.0` — JWT 认证
  - `passlib[bcrypt]>=1.7.0` — 密码哈希
  - `cryptography>=42.0.0` — Fernet 加密
  - `aiofiles>=23.0.0` — 静态文件服务
  - `python-multipart>=0.0.6` — OAuth2 表单解析

---

**DEPLOY-005: 配置环境变量（.env）**

- **组件**: `/opt/NetworkAgentDemo/.env`（新增 JWT/加密密钥）
- **操作**:
  ```bash
  # 生成随机 JWT 密钥（32 字节）
  JWT_SECRET=$(python3.11 -c "import secrets; print(secrets.token_hex(32))")

  # 生成 Fernet 加密密钥
  ENCRYPTION_KEY=$(python3.11 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")

  # 追加到 .env（保留现有 DEEPSEEK_API_KEY 等配置）
  cat >> /opt/NetworkAgentDemo/.env << EOF

  # ── MOD-WEB: Web UI v0.2.0 新增环境变量 ──
  JWT_SECRET_KEY=${JWT_SECRET}
  ENCRYPTION_KEY=${ENCRYPTION_KEY}
  ADMIN_PASSWORD=admin
  EOF
  ```
- **预期结果**: `.env` 文件包含 `DEEPSEEK_API_KEY`, `JWT_SECRET_KEY`, `ENCRYPTION_KEY`, `ADMIN_PASSWORD`
- **对应回滚**: ROLLBACK-005
- **备注**:
  - JWT_SECRET_KEY 重启后变更会导致所有已签发 Token 失效（Demo 可接受）
  - ENCRYPTION_KEY 丢失则所有 Fernet 加密数据不可恢复
  - ADMIN_PASSWORD 可选，默认值为 `admin`

---

**DEPLOY-006: 前端构建（npm install + build）**

- **组件**: `webui/` → `webui/dist/`（Vue 3 + Vite 生产构建）
- **操作**:
  ```bash
  cd /opt/NetworkAgentDemo/webui
  npm install
  npm run build
  ```
- **预期结果**: `webui/dist/` 目录生成，包含 `index.html` 和 static assets
- **对应回滚**: ROLLBACK-006
- **备注**: 前端依赖（package.json）:
  - Vue 3.4 + Vue Router 4.3 + Pinia 2.1
  - Element Plus 2.7（UI 组件库）
  - ECharts 5.5 + vue-echarts 6.6（图表）
  - Axios 1.7（HTTP 客户端）
  - Vite 5.4 + TypeScript 5.4（构建工具）

---

**DEPLOY-007: 更新 systemd 服务文件**

- **组件**: `/etc/systemd/system/networkagent.service`（增加环境变量文件加载）
- **操作**:
  ```bash
  cat > /etc/systemd/system/networkagent.service << 'EOF'
  [Unit]
  Description=NetworkAgentDemo FastAPI Service (v0.2.0 with Web UI)
  After=network.target

  [Service]
  Type=simple
  User=root
  WorkingDirectory=/opt/NetworkAgentDemo
  EnvironmentFile=/opt/NetworkAgentDemo/.env
  ExecStart=/opt/NetworkAgentDemo/venv/bin/python -m uvicorn src.main:app --host 0.0.0.0 --port 8001
  Restart=always
  RestartSec=5
  Environment=PYTHONUNBUFFERED=1

  [Install]
  WantedBy=multi-user.target
  EOF

  systemctl daemon-reload
  ```
- **预期结果**: systemd 配置更新，`EnvironmentFile` 指向 `.env`，`systemctl daemon-reload` 成功
- **对应回滚**: ROLLBACK-007
- **备注**: 相比旧版新增: `EnvironmentFile=/opt/NetworkAgentDemo/.env` 确保 JWT_SECRET_KEY 等环境变量在 systemd 管理的进程中可用

---

**DEPLOY-008: 启动服务**

- **组件**: networkagent.service（systemd 管理的 uvicorn 进程）
- **操作**:
  ```bash
  systemctl start networkagent
  sleep 3
  systemctl status networkagent --no-pager
  ```
- **预期结果**: `active (running)` 状态，无启动错误
- **对应回滚**: ROLLBACK-008

---

**DEPLOY-009: 健康检查验证**

- **组件**: FastAPI 后端 + Web UI 静态文件挂载
- **操作**:
  ```bash
  # 原有健康检查端点
  curl -s http://localhost:8001/health

  # 新 Web UI 仪表盘健康检查
  curl -s http://localhost:8001/api/dashboard/health

  # 端口监听确认
  ss -tlnp | grep 8001

  # 外部可达性
  curl -s http://47.109.197.217:8001/health
  ```
- **预期结果**:
  - `/health` 返回 `{"status":"healthy","service":"NetworkAgentDemo",...}`
  - `/api/dashboard/health` 返回 Web UI 健康状态
  - 端口 8001 在监听
  - 外部可达
- **对应回滚**: ROLLBACK-009

---

**DEPLOY-010: GenPlatform 完整性验证**

- **组件**: GenPlatform（端口 80/8000），**绝对不可破坏**
- **操作**:
  ```bash
  systemctl is-active genplatform-backend
  curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/
  curl -s -o /dev/null -w "%{http_code}" http://localhost:80/
  ```
- **预期结果**:
  - `genplatform-backend.service` 状态为 `active`
  - 端口 8000 返回 HTTP 200
  - 端口 80 返回 HTTP 200
- **对应回滚**: ROLLBACK-010 (验证步骤，无回滚操作)
- **备注**: 此步骤纯粹为验证，不执行任何变更操作。若 GenPlatform 异常，需立即排查但不应回滚 NetworkAgentDemo（因为 NetworkAgentDemo 不操作 80/8000 端口）。

---

## 回滚步骤（逆向，按逆序排列）

---

**ROLLBACK-010: GenPlatform 验证（无需回滚）**

- **回滚操作**: 无。此为验证步骤，不涉及状态变更。
- **预期结果**: N/A

---

**ROLLBACK-009: 健康检查（无需回滚）**

- **回滚操作**: 无。此为验证步骤，不涉及状态变更。
- **预期结果**: N/A

---

**ROLLBACK-008: 停止新版本服务，恢复旧版本服务**

- **回滚操作**:
  ```bash
  systemctl stop networkagent
  # 恢复旧 systemd 配置（从备份）
  cp /etc/systemd/system/networkagent.service.backup /etc/systemd/system/networkagent.service 2>/dev/null || true
  systemctl daemon-reload
  # 如果已执行 DEPLOY-003 的备份恢复，旧代码和 venv 已恢复
  systemctl start networkagent
  ```
- **预期结果**: networkagent 恢复为 v0.1.0 版本运行

---

**ROLLBACK-007: 恢复旧 systemd 服务文件**

- **回滚操作**:
  ```bash
  cp /etc/systemd/system/networkagent.service.backup /etc/systemd/system/networkagent.service
  systemctl daemon-reload
  ```
- **预期结果**: systemd 配置恢复为旧版本（无 EnvironmentFile）

---

**ROLLBACK-006: 清理前端构建产物**

- **回滚操作**:
  ```bash
  rm -rf /opt/NetworkAgentDemo/webui/dist
  rm -rf /opt/NetworkAgentDemo/webui/node_modules
  ```
- **预期结果**: 前端构建产物和 node_modules 被清理

---

**ROLLBACK-005: 恢复旧 .env 文件**

- **回滚操作**:
  ```bash
  # 从备份恢复 .env
  cp /opt/NetworkAgentDemo.backup.{TIMESTAMP}/.env /opt/NetworkAgentDemo/.env
  ```
- **预期结果**: `.env` 文件恢复为 v0.1.0 版本（无 JWT/加密密钥）

---

**ROLLBACK-004: 恢复旧 Python 依赖**

- **回滚操作**:
  ```bash
  cd /opt/NetworkAgentDemo
  source venv/bin/activate
  pip install -r /opt/NetworkAgentDemo.backup.{TIMESTAMP}/requirements.txt
  ```
- **预期结果**: Python 依赖恢复为 v0.1.0 版本
- **备注**: 最简单的回滚是直接使用备份的整个 venv 目录

---

**ROLLBACK-003: 清理运行时数据目录**

- **回滚操作**:
  ```bash
  rm -rf /opt/NetworkAgentDemo/data/
  ```
- **预期结果**: 新创建的 `data/` 目录被移除
- **备注**: [MANUAL_ROLLBACK_REQUIRED] 如果 SQLite 数据库 `webui.db` 已写入重要业务数据，删除前需确认

---

**ROLLBACK-002: 恢复旧代码**

- **回滚操作**:
  ```bash
  # 使用 git 回退
  cd /opt/NetworkAgentDemo
  git checkout 3ea1f68  # v0.1.0 最新 commit

  # 或从备份完整恢复
  rm -rf /opt/NetworkAgentDemo/src /opt/NetworkAgentDemo/webui
  cp -r /opt/NetworkAgentDemo.backup.{TIMESTAMP}/src /opt/NetworkAgentDemo/
  ```
- **预期结果**: `src/` 目录恢复为 v0.1.0 版本，`webui/` 目录不存在

---

**ROLLBACK-001: 完整恢复备份**

- **回滚操作**:
  ```bash
  # 停止服务
  systemctl stop networkagent

  # 删除当前部署
  rm -rf /opt/NetworkAgentDemo

  # 从备份恢复
  cp -r /opt/NetworkAgentDemo.backup.{TIMESTAMP} /opt/NetworkAgentDemo

  # 恢复 systemd 配置
  cp /etc/systemd/system/networkagent.service.backup /etc/systemd/system/networkagent.service 2>/dev/null
  systemctl daemon-reload

  # 启动旧版本服务
  systemctl start networkagent

  # 验证
  curl -s http://localhost:8001/health
  ```
- **预期结果**: 系统完整恢复为部署前状态，v0.1.0 正常运行

---

## 部署后验证清单（Post-deployment Verification）

| 检查项 | 检查方法 | 成功标准 |
|--------|---------|---------|
| VERIFY-01: 服务进程运行 | `systemctl is-active networkagent` | `active` |
| VERIFY-02: 端口监听 | `ss -tlnp \| grep 8001` | LISTEN 状态 |
| VERIFY-03: 原有 /health 端点 | `curl -s http://localhost:8001/health \| python3.11 -m json.tool` | HTTP 200, status=healthy |
| VERIFY-04: 新 Web UI /api/dashboard/health | `curl -s http://localhost:8001/api/dashboard/health` | HTTP 200 |
| VERIFY-05: Web UI 静态文件挂载 | `curl -s -o /dev/null -w "%{http_code}" http://localhost:8001/` | HTTP 200 (返回 index.html) |
| VERIFY-06: JWT 认证端点可达 | `curl -s -o /dev/null -w "%{http_code}" http://localhost:8001/api/auth/login` | HTTP 405 (POST only) 或 200 |
| VERIFY-07: API 文档可访问 | `curl -s -o /dev/null -w "%{http_code}" http://localhost:8001/docs` | HTTP 200 |
| VERIFY-08: 原有 webhook 端点 | `curl -s -o /dev/null -w "%{http_code}" http://localhost:8001/webhook/alert` | HTTP 405/422 (需要 POST + body) |
| VERIFY-09: SQLite 数据库创建 | `ls -la /opt/NetworkAgentDemo/data/webui.db` | 文件存在 |
| VERIFY-10: 加密密钥文件 | `ls -la /opt/NetworkAgentDemo/data/.encryption_key` | 文件存在 |
| VERIFY-11: 日志正常 | `journalctl -u networkagent -n 20 --no-pager \| grep -i error \| wc -l` | 0 (无 ERROR 级别日志) |
| VERIFY-12: GenPlatform 后端未受影响 | `systemctl is-active genplatform-backend` | `active` |
| VERIFY-13: GenPlatform 前端未受影响 | `curl -s -o /dev/null -w "%{http_code}" http://localhost:80/` | HTTP 200 |
| VERIFY-14: GenPlatform 后端端口 | `curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/` | HTTP 200 |
| VERIFY-15: 外部可达性 | `curl -s --connect-timeout 5 http://47.109.197.217:8001/health` | HTTP 200 |

---

## 安全约束重申

| 约束 | 说明 |
|------|------|
| **绝对禁止 pkill -f gunicorn** | 会误杀 GenPlatform 进程 |
| **只操作 8001 端口** | 不修改 80/8000 相关配置 |
| **只操作 networkagent.service** | 不修改 genplatform-* 服务 |
| **Python 必须用 python3.11** | python3 默认是 3.6，不可用 |
| **部署失败立即回滚** | 不反复尝试破坏性操作 |
| **SQLite webui.db 注意** | VPS sqlite3 < 3.35.0（不影响 SQLAlchemy 操作的 SQLite 数据库，只影响 ChromaDB） |

---

## 预计耗时

| 步骤 | 预计耗时 |
|------|---------|
| DEPLOY-001: 备份 | < 10s |
| DEPLOY-002: 上传代码 | < 30s (pscp) 或 < 10s (git pull) |
| DEPLOY-003: 创建目录 | < 1s |
| DEPLOY-004: 安装依赖 | < 120s (含新增 Web UI 依赖) |
| DEPLOY-005: 配置 .env | < 5s |
| DEPLOY-006: 前端构建 | < 60s (npm install + build) |
| DEPLOY-007: 更新 systemd | < 5s |
| DEPLOY-008: 启动服务 | < 10s |
| DEPLOY-009: 健康检查 | < 10s |
| DEPLOY-010: GenPlatform 验证 | < 5s |
| **总计** | **约 4-5 分钟** |
