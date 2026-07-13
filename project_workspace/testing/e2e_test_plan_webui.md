<file_header>
  <author_agent>main_agent_pm</author_agent>
  <timestamp>2026-07-11T00:00:00Z</timestamp>
  <project_name>NetworkAgentDemo</project_name>
  <version>0.2.0</version>
  <input_files>
    <file>requirements/requirements_spec.md</file>
    <file>requirements/webui_requirements_spec.md</file>
    <file>architecture/module_design.md</file>
    <file>architecture/webui_module_design.md</file>
    <file>src/main.py</file>
    <file>src/api/__init__.py</file>
    <file>testing/e2e_test_report.md</file>
  </input_files>
  <phase>PHASE_09</phase>
  <status>DRAFT</status>
</file_header>

# E2E 测试计划 — NetworkAgentDemo v0.2.0 Web UI

---

## 1. 测试范围概述

### 1.1 目标环境
| 项目 | 值 |
|------|-----|
| 目标 URL | `http://47.109.197.217:8001` |
| 登录凭据 | admin / admin |
| 技术栈 | FastAPI + LangGraph + SQLite + Vue 3 SPA |
| 测试类型 | 黑盒 E2E（远程 HTTP 测试） |

### 1.2 测试范围矩阵

| 需求 ID | 需求描述 | E2E 测试用例 | 优先级 |
|---------|---------|------------|--------|
| REQ-FUNC-002 | Mock 告警推送 | TC-E2E-WEB-001, TC-E2E-WEB-004~006 | P0 |
| REQ-FUNC-006 | LangGraph 状态机编排 | TC-E2E-WEB-007~008 | P0 |
| REQ-FUNC-013 | 人工审批中断与恢复 | TC-E2E-WEB-009~010 | P0 |
| REQ-WEBUI-FUNC-001 | 告警列表查看与筛选 | TC-E2E-WEB-005 | P0 |
| REQ-WEBUI-FUNC-002 | 告警详情查看 | TC-E2E-WEB-006 | P0 |
| REQ-WEBUI-FUNC-003 | 手动模拟发送告警 | TC-E2E-WEB-004 | P0 |
| REQ-WEBUI-FUNC-004 | 告警处理流程实时状态追踪 | TC-E2E-WEB-007 | P0 |
| REQ-WEBUI-FUNC-005 | LangGraph 节点拓扑可视化 | TC-E2E-WEB-008 | P1 |
| REQ-WEBUI-FUNC-007 | 待审批列表展示 | TC-E2E-WEB-009 | P0 |
| REQ-WEBUI-FUNC-008 | 审批决策操作 | TC-E2E-WEB-010 | P0 |
| REQ-WEBUI-FUNC-010 | 纳管设备 CRUD | TC-E2E-WEB-013~014 | P0/P1 |
| REQ-WEBUI-FUNC-016 | 知识文档列表 | TC-E2E-WEB-015 | P1 |
| REQ-WEBUI-FUNC-019 | 全局配置读取 | TC-E2E-WEB-016 | P1 |
| REQ-WEBUI-FUNC-022 | 告警统计图表（Dashboard） | TC-E2E-WEB-012 | P1 |
| REQ-WEBUI-FUNC-024 | 系统健康状态面板 | TC-E2E-WEB-011 | P0 |
| REQ-WEBUI-FUNC-025 | 用户登录与 JWT 认证 | TC-E2E-WEB-001~003 | P0 |

---

## 2. 测试用例详情

---

### TC-E2E-WEB-001: 用户登录成功

| 字段 | 内容 |
|------|------|
| **ID** | TC-E2E-WEB-001 |
| **优先级** | P0 |
| **覆盖需求** | REQ-WEBUI-FUNC-025 |
| **覆盖 AC** | AC-W025-01 |
| **前置条件** | 服务运行在 47.109.197.217:8001，admin 账号已初始化 |
| **类型** | 正向测试 |

**测试步骤：**

| 步骤 | 操作 | 预期结果 |
|------|------|---------|
| 1 | POST `/auth/login` 使用正确的 admin/admin（form-data） | HTTP 200 |
| 2 | 验证响应 JSON | 包含 `access_token` 字符串，`token_type` = "bearer"，`expires_in` = 86400 |
| 3 | 使用返回的 token 调用 GET `/api/alerts` | HTTP 200，返回告警列表，不被 401/403 拦截 |

---

### TC-E2E-WEB-002: 用户登录失败（错误密码）

| 字段 | 内容 |
|------|------|
| **ID** | TC-E2E-WEB-002 |
| **优先级** | P0 |
| **覆盖需求** | REQ-WEBUI-FUNC-025 |
| **覆盖 AC** | AC-W025-02 |
| **前置条件** | 服务运行中 |
| **类型** | 负向测试 |

**测试步骤：**

| 步骤 | 操作 | 预期结果 |
|------|------|---------|
| 1 | POST `/auth/login` 使用 admin/wrongpassword | HTTP 401 |
| 2 | 验证响应 JSON | 包含 `detail` 字段，消息为"用户名或密码错误" |

---

### TC-E2E-WEB-003: 无 Token 直接访问受保护 API 返回 401

| 字段 | 内容 |
|------|------|
| **ID** | TC-E2E-WEB-003 |
| **优先级** | P0 |
| **覆盖需求** | REQ-WEBUI-FUNC-025 |
| **覆盖 AC** | AC-W025-04 |
| **前置条件** | 服务运行中 |
| **类型** | 负向测试 |

**测试步骤：**

| 步骤 | 操作 | 预期结果 |
|------|------|---------|
| 1 | GET `/api/alerts`（不携带 Authorization header） | HTTP 401 或 403 |
| 2 | GET `/api/devices`（不携带 Authorization header） | HTTP 401 或 403 |

---

### TC-E2E-WEB-004: 模拟发送 PORT_DOWN 告警

| 字段 | 内容 |
|------|------|
| **ID** | TC-E2E-WEB-004 |
| **优先级** | P0 |
| **覆盖需求** | REQ-FUNC-002, REQ-WEBUI-FUNC-003 |
| **覆盖 AC** | AC-W003-01, AC-W003-02 |
| **前置条件** | 已获取有效 JWT Token |
| **类型** | 正向测试 + 端到端工作流触发 |

**测试步骤：**

| 步骤 | 操作 | 预期结果 |
|------|------|---------|
| 1 | POST `/api/alerts/simulate`，Body = `{"alert_type": "PORT_DOWN", "device_name": "Core-SW-01", "device_ip": "192.168.1.1", "interface": "Gi0/1"}` | HTTP 200 |
| 2 | 验证响应 | `message` = "模拟告警已发送"，`alert_id` 非空字符串，`alert_type` = "PORT_DOWN" |
| 3 | 记录 alert_id 用于后续测试 | — |

---

### TC-E2E-WEB-005: 查询告警列表（含筛选）

| 字段 | 内容 |
|------|------|
| **ID** | TC-E2E-WEB-005 |
| **优先级** | P0 |
| **覆盖需求** | REQ-WEBUI-FUNC-001 |
| **覆盖 AC** | AC-W001-01, AC-W001-02 |
| **前置条件** | 已获取有效 JWT Token，系统中存在告警记录 |
| **类型** | 正向测试 |

**测试步骤：**

| 步骤 | 操作 | 预期结果 |
|------|------|---------|
| 1 | GET `/api/alerts`（无筛选条件） | HTTP 200，返回 `items` 列表和 `total`/`page`/`page_size` |
| 2 | GET `/api/alerts?alert_type=PORT_DOWN` | HTTP 200，所有返回项的 `alert_type` 均为 PORT_DOWN |
| 3 | GET `/api/alerts?page=1&page_size=5` | HTTP 200，返回不超过 5 条记录 |

---

### TC-E2E-WEB-006: 查询告警详情

| 字段 | 内容 |
|------|------|
| **ID** | TC-E2E-WEB-006 |
| **优先级** | P0 |
| **覆盖需求** | REQ-WEBUI-FUNC-002 |
| **覆盖 AC** | AC-W002-01 |
| **前置条件** | 已获取有效 JWT Token，已知一个有效的 alert_id |
| **类型** | 正向测试 |

**测试步骤：**

| 步骤 | 操作 | 预期结果 |
|------|------|---------|
| 1 | GET `/api/alerts/{alert_id}` | HTTP 200 |
| 2 | 验证响应 | 包含 `alert` 对象（含 alert_id, alert_type, status 等字段）和 `timeline` 数组 |

---

### TC-E2E-WEB-007: 告警触发后轮询工作流状态直到完成

| 字段 | 内容 |
|------|------|
| **ID** | TC-E2E-WEB-007 |
| **优先级** | P0 |
| **覆盖需求** | REQ-FUNC-006, REQ-WEBUI-FUNC-004 |
| **覆盖 AC** | AC-W004-01 |
| **前置条件** | 已获取有效 JWT Token，刚触发了一条模拟告警 |
| **类型** | 正向测试 + 端到端工作流验证 |

**测试步骤：**

| 步骤 | 操作 | 预期结果 |
|------|------|---------|
| 1 | 先触发一条 MAC_FLAPPING 告警 | HTTP 200，获得 alert_id |
| 2 | 轮询 GET `/api/alerts/{alert_id}/workflow`，间隔 3 秒，最多等待 60 秒 | 每次请求 HTTP 200 |
| 3 | 在 60 秒内，workflow 的 `timeline` 数组从空逐渐累积节点执行记录 | timeline 包含至少 receive_alert, parse_alert 等节点 |
| 4 | 最终 `status` 字段变为 CLOSED 或 FAILED 或 REJECTED（非 PROCESSING） | 状态机在 60 秒内完成 |

---

### TC-E2E-WEB-008: 工作流拓扑图查询

| 字段 | 内容 |
|------|------|
| **ID** | TC-E2E-WEB-008 |
| **优先级** | P1 |
| **覆盖需求** | REQ-WEBUI-FUNC-005 |
| **覆盖 AC** | AC-W005-01 |
| **前置条件** | 已获取有效 JWT Token |
| **类型** | 正向测试 |

**测试步骤：**

| 步骤 | 操作 | 预期结果 |
|------|------|---------|
| 1 | GET `/api/workflow/graph` | HTTP 200 |
| 2 | 验证响应 | 包含节点列表（14 个节点）和边列表（含条件边描述） |

---

### TC-E2E-WEB-009: 查询待审批列表

| 字段 | 内容 |
|------|------|
| **ID** | TC-E2E-WEB-009 |
| **优先级** | P0 |
| **覆盖需求** | REQ-WEBUI-FUNC-007 |
| **覆盖 AC** | AC-W007-01, AC-W007-02 |
| **前置条件** | 已获取有效 JWT Token |
| **类型** | 正向测试 |

**测试步骤：**

| 步骤 | 操作 | 预期结果 |
|------|------|---------|
| 1 | GET `/api/approvals/pending` | HTTP 200 |
| 2 | 验证响应 | 包含 `pending` 数组和 `count` 字段；若 count > 0，每条包含 `checkpoint_id`, `alert_id`, `fix_plan`, `risk_level`；若 count = 0，数组为空 |

---

### TC-E2E-WEB-010: 审批决策操作（批准）

| 字段 | 内容 |
|------|------|
| **ID** | TC-E2E-WEB-010 |
| **优先级** | P0 |
| **覆盖需求** | REQ-FUNC-013, REQ-WEBUI-FUNC-008 |
| **覆盖 AC** | AC-W008-02 |
| **前置条件** | 已获取有效 JWT Token，待审批列表中至少有一条待审批项 |
| **类型** | 正向测试 |

**测试步骤：**

| 步骤 | 操作 | 预期结果 |
|------|------|---------|
| 1 | GET `/api/approvals/pending`，获取第一个待审批项的 checkpoint_id | HTTP 200，count > 0 |
| 2 | POST `/api/approvals/{checkpoint_id}/decide`，Body = `{"decision": "APPROVED", "note": "E2E auto-approve"}` | HTTP 200 |
| 3 | 验证响应 | `message` = "审批已提交: APPROVED"，`decision` = "APPROVED" |
| 4 | 再次 GET `/api/approvals/pending` | 该 checkpoint_id 不再出现在 pending 列表中 |

---

### TC-E2E-WEB-011: 系统健康检查

| 字段 | 内容 |
|------|------|
| **ID** | TC-E2E-WEB-011 |
| **优先级** | P0 |
| **覆盖需求** | REQ-WEBUI-FUNC-024 |
| **覆盖 AC** | AC-W024-01 |
| **前置条件** | 已获取有效 JWT Token |
| **类型** | 正向测试 |

**测试步骤：**

| 步骤 | 操作 | 预期结果 |
|------|------|---------|
| 1 | GET `/api/dashboard/health` | HTTP 200 |
| 2 | 验证响应 | 包含 `langgraph`（status）、`rag`（status）、`scheduler`（status）等组件状态对象 |
| 3 | 同时验证公开端点 | GET `/health` → HTTP 200，`status` = "healthy" |

---

### TC-E2E-WEB-012: Dashboard 统计数据

| 字段 | 内容 |
|------|------|
| **ID** | TC-E2E-WEB-012 |
| **优先级** | P1 |
| **覆盖需求** | REQ-WEBUI-FUNC-022, REQ-WEBUI-FUNC-023 |
| **覆盖 AC** | AC-W022-01, AC-W023-01 |
| **前置条件** | 已获取有效 JWT Token |
| **类型** | 正向测试 |

**测试步骤：**

| 步骤 | 操作 | 预期结果 |
|------|------|---------|
| 1 | GET `/api/dashboard/stats` | HTTP 200 |
| 2 | 验证响应 | 包含告警统计字段（如 total, by_type, by_severity, by_status, trend 等），数据为整数或合理数值 |

---

### TC-E2E-WEB-013: 设备列表查询

| 字段 | 内容 |
|------|------|
| **ID** | TC-E2E-WEB-013 |
| **优先级** | P0 |
| **覆盖需求** | REQ-WEBUI-FUNC-010 |
| **覆盖 AC** | AC-W010-01 |
| **前置条件** | 已获取有效 JWT Token |
| **类型** | 正向测试 |

**测试步骤：**

| 步骤 | 操作 | 预期结果 |
|------|------|---------|
| 1 | GET `/api/devices` | HTTP 200 |
| 2 | 验证响应 | 包含 `devices` 数组和 `count` 字段；每条设备记录包含 `device_name`, `device_ip`, `device_model`, `status` 等字段 |

---

### TC-E2E-WEB-014: 创建并删除测试设备（CRUD 完整闭环）

| 字段 | 内容 |
|------|------|
| **ID** | TC-E2E-WEB-014 |
| **优先级** | P1 |
| **覆盖需求** | REQ-WEBUI-FUNC-010 |
| **覆盖 AC** | AC-W010-02, AC-W010-05 |
| **前置条件** | 已获取有效 JWT Token |
| **类型** | 正向测试 + 清理 |

**测试步骤：**

| 步骤 | 操作 | 预期结果 |
|------|------|---------|
| 1 | POST `/api/devices`，Body = `{"device_name": "E2E-TEST-DEV-01", "device_ip": "10.0.0.99", "device_model": "Test Model", "group_name": "E2E"}` | HTTP 200，返回 `device_id` |
| 2 | GET `/api/devices/{device_id}` | HTTP 200，设备名称为 E2E-TEST-DEV-01 |
| 3 | PUT `/api/devices/{device_id}`，Body = `{"device_name": "E2E-TEST-DEV-01-UPDATED"}` | HTTP 200 |
| 4 | DELETE `/api/devices/{device_id}` | HTTP 200，`message` = "设备已删除" |
| 5 | 再次 GET `/api/devices/{device_id}` | HTTP 404 |

---

### TC-E2E-WEB-015: 知识库文档列表

| 字段 | 内容 |
|------|------|
| **ID** | TC-E2E-WEB-015 |
| **优先级** | P1 |
| **覆盖需求** | REQ-WEBUI-FUNC-016 |
| **覆盖 AC** | AC-W016-01 |
| **前置条件** | 已获取有效 JWT Token |
| **类型** | 正向测试 |

**测试步骤：**

| 步骤 | 操作 | 预期结果 |
|------|------|---------|
| 1 | GET `/api/knowledge/documents` | HTTP 200 |
| 2 | GET `/api/knowledge/templates` | HTTP 200 |
| 3 | 验证文档和模板响应结构 | documents 响应含分页结构（items/total）；templates 响应含 `templates` 数组和 `count` |

---

### TC-E2E-WEB-016: 系统配置读取

| 字段 | 内容 |
|------|------|
| **ID** | TC-E2E-WEB-016 |
| **优先级** | P1 |
| **覆盖需求** | REQ-WEBUI-FUNC-019 |
| **覆盖 AC** | AC-W019-01 |
| **前置条件** | 已获取有效 JWT Token |
| **类型** | 正向测试 |

**测试步骤：**

| 步骤 | 操作 | 预期结果 |
|------|------|---------|
| 1 | GET `/api/system/config` | HTTP 200 |
| 2 | 验证响应 | 包含 `configs` 数组，每个配置项有 `config_key` 和 `config_value`；llm.api_key_encrypted 的 config_value 为 "****"（掩码） |
| 3 | GET `/api/inspection/config` | HTTP 200，返回巡检相关配置 |

---

## 3. 特殊考虑

### 3.1 巡检后台运行
- 巡检每 5 分钟自动触发，测试可能看到 source=INSPECTION 的告警
- 测试不依赖巡检，主要测试 Webhook 模拟触发路径

### 3.2 工作流执行异步
- 模拟告警在后台线程执行 LangGraph 工作流
- 需要轮询机制等待状态机完成（最多等待 60 秒）
- 如果请求审批中断后的工作流（如 PORT_DOWN 告警），需要在轮询中检测 status

### 3.3 测试数据清理
- 创建测试设备（E2E-TEST-DEV-01）后必须删除
- 模拟告警产生的工作流数据保留在生产数据库中（不删除历史数据）
- 审批决策后不执行反向操作

### 3.4 不测试项目
- 删除有活跃告警关联的设备（409 冲突） — 需要精确构造，跳过
- 巡检手动触发 — 可能与其他巡检冲突，跳过
- LLM 连接测试 — 需要真实 API Key，跳过
- 日志搜索 — 依赖文件系统，跳过

---

## 4. 测试用例汇总

| 编号 | 测试名称 | 优先级 | 类别 | 预计耗时 |
|------|---------|--------|------|---------|
| TC-E2E-WEB-001 | 登录成功 | P0 | 认证 | < 1s |
| TC-E2E-WEB-002 | 登录失败（错误密码） | P0 | 认证 | < 1s |
| TC-E2E-WEB-003 | 无 Token 访问拒绝 | P0 | 认证 | < 1s |
| TC-E2E-WEB-004 | 模拟 PORT_DOWN 告警 | P0 | 告警 | < 2s |
| TC-E2E-WEB-005 | 告警列表查询 | P0 | 告警 | < 2s |
| TC-E2E-WEB-006 | 告警详情 | P0 | 告警 | < 2s |
| TC-E2E-WEB-007 | 工作流状态轮询 | P0 | 工作流 | 5-60s |
| TC-E2E-WEB-008 | 工作流拓扑图 | P1 | 工作流 | < 2s |
| TC-E2E-WEB-009 | 待审批列表 | P0 | 审批 | < 2s |
| TC-E2E-WEB-010 | 审批批准操作 | P0 | 审批 | < 3s |
| TC-E2E-WEB-011 | 系统健康检查 | P0 | Dashboard | < 2s |
| TC-E2E-WEB-012 | Dashboard 统计 | P1 | Dashboard | < 2s |
| TC-E2E-WEB-013 | 设备列表 | P0 | 设备管理 | < 2s |
| TC-E2E-WEB-014 | 设备 CRUD 闭环 | P1 | 设备管理 | < 5s |
| TC-E2E-WEB-015 | 知识库列表 | P1 | 知识库 | < 2s |
| TC-E2E-WEB-016 | 系统配置读取 | P1 | 系统配置 | < 2s |

| 总计 | **16** | P0: 10, P1: 6 | 8 类别 | ~90s max |

---

## 5. 风险与限制

| 风险 | 级别 | 缓解措施 |
|------|------|---------|
| 工作流执行时间不可控 | MEDIUM | 设置 60s 超时，超时标记为 FAIL |
| PORT_DOWN 告警触发审批中断 | MEDIUM | 测试用例 TC-E2E-WEB-007 设计为等待所有可能状态（CLOSED/FAILED/REJECTED），不假设工作流立即完成 |
| 后台巡检产生额外告警 | LOW | 告警列表测试不依赖具体数量，仅验证结构和分页 |
| VPS 网络延迟 | LOW | 设置合理的 HTTP 超时（30s），轮询间隔 3s |
| 测试设备名冲突 | LOW | 使用 E2E-TEST-DEV-01 作为唯一名称，测试后删除 |
