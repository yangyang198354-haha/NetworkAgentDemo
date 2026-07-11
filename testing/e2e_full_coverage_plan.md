<file_header>
  <author_agent>main_agent_pm</author_agent>
  <timestamp>2026-07-11T00:00:00Z</timestamp>
  <project_name>NetworkAgentDemo</project_name>
  <version>0.2.0</version>
  <input_files>
    <file>requirements/requirements_spec.md</file>
    <file>tests/test_e2e_webui.py (existing reference)</file>
    <file>testing/e2e_test_plan_webui.md</file>
    <file>testing/e2e_test_report.md</file>
  </input_files>
  <phase>PHASE_09</phase>
  <status>DRAFT</status>
</file_header>

# E2E 全量覆盖测试计划 — NetworkAgentDemo v0.2.0

---

## 1. 测试目标

对 NetworkAgentDemo v0.2.0 生产环境 `http://47.109.197.217:8001/` 的所有 HTTP API 端点执行全面黑盒 E2E 测试，覆盖以下 10 个功能模块的 **全部已实现端点**：

1. **认证模块** — 登录成功/失败、Token 格式、无凭据访问拒绝
2. **告警管理** — 模拟告警（3种类型+非法类型400）、列表筛选分页、详情深度验证、工作流状态
3. **告警详情新增字段** — timeline（14节点）、fix_plan、commands、llm_calls、approval
4. **审批管理** — 组合端点（pending+history JSON）、单独 pending、单独 history
5. **Dashboard** — stats 全字段（7项指标）、health 组件级验证（4组件）
6. **设备管理** — 列表、CRUD 闭环（创建→读取→更新→删除→验证404）
7. **巡检管理** — config、手动触发、历史查询
8. **知识库** — documents、templates、retrieval（RAG检索）
9. **系统配置** — config（含API Key掩码）、logs
10. **关键修复验证** — RiskAssessor PORT_DOWN、timeline完整性、LLM记录数、pending_approval_count、审批API JSON格式

---

## 2. 测试用例清单

### 2.1 用例分类总览

| 测试类 | 用例数 | 优先级 | 标记 | 覆盖功能模块 |
|--------|--------|--------|------|------------|
| TestAuthLoginSuccess | 2 | P0 | — | 1.认证 |
| TestAuthLoginFailure | 2 | P0 | — | 1.认证 |
| TestAuthUnauthenticated | 2 | P0 | — | 1.认证 |
| TestAlertSimulate | 4 | P0 | — | 2.告警管理 |
| TestAlertList | 4 | P0 | — | 2.告警管理 |
| TestAlertDetail | 3 | P0 | — | 2.告警管理 |
| TestAlertDetailNewFields | 8 | P0 | @slow | 3.详情新字段 |
| TestWorkflowPolling | 1 | P0 | @slow | 2.工作流 |
| TestWorkflowGraph | 1 | P1 | — | 2.工作流 |
| TestApprovalCombined | 1 | P0 | — | 4.审批管理 |
| TestApprovalPending | 2 | P0 | — | 4.审批管理 |
| TestApprovalHistory | 1 | P0 | — | 4.审批管理 |
| TestApprovalDecide | 2 | P0 | @slow | 4.审批管理 |
| TestDashboardHealth | 2 | P0 | — | 5.Dashboard |
| TestDashboardStats | 3 | P0 | — | 5.Dashboard |
| TestDeviceList | 2 | P0 | — | 6.设备管理 |
| TestDeviceCRUD | 1 | P1 | — | 6.设备管理 |
| TestInspectionManagement | 3 | P1 | — | 7.巡检管理 |
| TestKnowledgeBase | 3 | P1 | — | 8.知识库 |
| TestSystemManagement | 3 | P1 | — | 9.系统配置 |
| TestKeyFixVerification | 6 | P0 | @slow | 10.关键修复 |
| **总计** | **49** | P0:35, P1:14 | slow:15 | 10模块全覆盖 |

---

### 2.2 详细用例规格

#### 2.2.1 认证模块（Auth）— TC-AUTH

| TC-ID | 方法 | 描述 | 预期 |
|-------|------|------|------|
| TC-AUTH-001 | POST /auth/login | 正确凭据返回JWT | 200, access_token长度>10, token_type=bearer, expires_in=86400 |
| TC-AUTH-002 | GET /api/alerts (with token) | Token可访问受保护端点 | 200 |
| TC-AUTH-003 | POST /auth/login | 错误密码 | 401, detail含错误信息 |
| TC-AUTH-004 | POST /auth/login | 不存在用户 | 401 |
| TC-AUTH-005 | GET /api/alerts (no token) | 无Token访问 | 401或403 |
| TC-AUTH-006 | GET /api/devices (no token) | 无Token访问设备API | 401或403 |

#### 2.2.2 告警模拟（Alert Simulate）— TC-ALERT-SIM

| TC-ID | 方法 | 描述 | 预期 |
|-------|------|------|------|
| TC-ALERT-SIM-001 | POST /api/alerts/simulate | PORT_DOWN | 200, message="模拟告警已发送", alert_id非空, alert_type=PORT_DOWN |
| TC-ALERT-SIM-002 | POST /api/alerts/simulate | MAC_FLAPPING | 200, alert_type=MAC_FLAPPING |
| TC-ALERT-SIM-003 | POST /api/alerts/simulate | CPU_HIGH | 200, alert_type=CPU_HIGH |
| TC-ALERT-SIM-004 | POST /api/alerts/simulate | INVALID_TYPE | 400 |

#### 2.2.3 告警列表（Alert List）— TC-ALERT-LIST

| TC-ID | 方法 | 描述 | 预期 |
|-------|------|------|------|
| TC-ALERT-LIST-001 | GET /api/alerts | 全部列表 | 200, 含items或alerts或total |
| TC-ALERT-LIST-002 | GET /api/alerts?alert_type=PORT_DOWN | 按类型筛选 | 200 |
| TC-ALERT-LIST-003 | GET /api/alerts?severity=WARNING | 按严重级别筛选 | 200 |
| TC-ALERT-LIST-004 | GET /api/alerts?page=1&page_size=5 | 分页 | 200, 返回<=5条 |

#### 2.2.4 告警详情基础（Alert Detail）— TC-ALERT-DETAIL

| TC-ID | 方法 | 描述 | 预期 |
|-------|------|------|------|
| TC-ALERT-DETAIL-001 | GET /api/alerts/{id} | 查看告警详情 | 200, 含alert对象 |
| TC-ALERT-DETAIL-002 | GET /api/alerts/{id} | 含workflow状态 | timeline字段存在 |
| TC-ALERT-DETAIL-003 | GET /api/alerts/nonexistent | 不存在ID | 404 |

#### 2.2.5 告警详情新字段深度验证（Alert Detail New Fields）— TC-ALERT-NEW

| TC-ID | 验证字段 | 描述 | 预期 |
|-------|---------|------|------|
| TC-ALERT-NEW-001 | timeline | timeline数组存在, 每个节点含node_name/status/started_at/completed_at | ≥10个节点, 字段完整 |
| TC-ALERT-NEW-002 | timeline node status | 检查节点状态字段 | 存在COMPLETED状态节点 |
| TC-ALERT-NEW-003 | fix_plan | fix_plan字段存在 | 含template_id, description, params |
| TC-ALERT-NEW-004 | commands | commands数组存在 | 含CLI命令字符串（如interface/description等） |
| TC-ALERT-NEW-005 | llm_calls | llm_calls数组存在 | 2-3条记录, 每条含endpoint/elapsed_s/prompt_tokens/completion_tokens/prompt/response |
| TC-ALERT-NEW-006 | llm_calls structure | LLM调用记录字段类型 | elapsed_s为float, tokens为整数, response为非空字符串 |
| TC-ALERT-NEW-007 | approval | approval字段存在 | 含need_human_approval/approval_status/risk_level |
| TC-ALERT-NEW-008 | approval PORT_DOWN | PORT_DOWN告警审批状态 | need_human_approval=False, risk_level在{LOW,MEDIUM,HIGH,CRITICAL}中 |

#### 2.2.6 工作流（Workflow）— TC-WF

| TC-ID | 方法 | 描述 | 预期 |
|-------|------|------|------|
| TC-WF-001 | GET /api/alerts/{id}/workflow | 轮询工作流状态 | 200, 含alert_id/status/timeline, status非空 |
| TC-WF-002 | GET /api/workflow/graph | 工作流拓扑图 | 200, 含节点/边数据 |

#### 2.2.7 审批管理（Approval）— TC-APPROVAL

| TC-ID | 方法 | 描述 | 预期 |
|-------|------|------|------|
| TC-APPROVAL-001 | GET /api/approvals | 组合端点(pending+history) | 200, 返回JSON非HTML, content-type含json |
| TC-APPROVAL-002 | GET /api/approvals/pending | 待审批列表 | 200, 含pending数组+count, count==len(pending) |
| TC-APPROVAL-003 | GET /api/approvals/pending | 审批项结构 | 每条含checkpoint_id/alert_id/risk_level |
| TC-APPROVAL-004 | GET /api/approvals/history | 审批历史 | 200, 返回分页dict |
| TC-APPROVAL-005 | POST /api/approvals/{id}/decide | 批准审批 | 200, decision=APPROVED |
| TC-APPROVAL-006 | POST /api/approvals/{id}/decide | 无效decision | 400 |

#### 2.2.8 Dashboard 健康检查 — TC-DASH-HEALTH

| TC-ID | 方法 | 描述 | 预期 |
|-------|------|------|------|
| TC-DASH-HEALTH-001 | GET /api/dashboard/health | 组件健康状态 | 200, 含langgraph/rag/scheduler/llm各组件status |
| TC-DASH-HEALTH-002 | GET /health | 公开健康端点 | 200, status=healthy, 含components |

#### 2.2.9 Dashboard 统计 — TC-DASH-STATS

| TC-ID | 方法 | 验证字段 | 预期 |
|-------|------|---------|------|
| TC-DASH-STATS-001 | GET /api/dashboard/stats | 基础字段存在 | total_count/today_count/pending_approval_count/fix_success_rate为数值 |
| TC-DASH-STATS-002 | GET /api/dashboard/stats | by_type/by_severity | 含PORT_DOWN/MAC_FLAPPING/CPU_HIGH计数 |
| TC-DASH-STATS-003 | GET /api/dashboard/stats | trend字段 | trend为数组 |

#### 2.2.10 设备管理（Device）— TC-DEVICE

| TC-ID | 方法 | 描述 | 预期 |
|-------|------|------|------|
| TC-DEVICE-001 | GET /api/devices | 设备列表 | 200, 含devices数组+count |
| TC-DEVICE-002 | GET /api/devices | 设备结构 | 每条含device_name/device_ip |
| TC-DEVICE-003 | POST+GET+PUT+DELETE | CRUD闭环 | 创建→读取→更新→删除→验证404 |

#### 2.2.11 巡检管理（Inspection）— TC-INSP

| TC-ID | 方法 | 描述 | 预期 |
|-------|------|------|------|
| TC-INSP-001 | GET /api/inspection/config | 巡检配置 | 200, 含config字段 |
| TC-INSP-002 | POST /api/inspection/trigger | 手动触发巡检 | 200, 含message |
| TC-INSP-003 | GET /api/inspection/history | 巡检历史 | 200, 返回历史列表 |

#### 2.2.12 知识库（Knowledge Base）— TC-KB

| TC-ID | 方法 | 描述 | 预期 |
|-------|------|------|------|
| TC-KB-001 | GET /api/knowledge/documents | 知识文档列表 | 200 |
| TC-KB-002 | GET /api/knowledge/templates | 命令模板列表 | 200, templates数组+count |
| TC-KB-003 | POST /api/knowledge/retrieval | RAG检索测试 | 200, results数组 |

#### 2.2.13 系统管理（System）— TC-SYS

| TC-ID | 方法 | 描述 | 预期 |
|-------|------|------|------|
| TC-SYS-001 | GET /api/system/config | 系统配置列表 | 200, configs数组 |
| TC-SYS-002 | GET /api/system/config | LLM API Key掩码 | config_value="****", masked=True |
| TC-SYS-003 | GET /api/system/logs | 系统日志 | 200, 返回日志列表 |

#### 2.2.14 关键修复验证（Key Fix Verification）— TC-FIX

| TC-ID | 描述 | 验证点 | 预期 | 标记 |
|-------|------|--------|------|------|
| TC-FIX-001 | PORT_DOWN RiskAssessor修复 | need_human_approval | False | @slow |
| TC-FIX-002 | PORT_DOWN RiskAssessor修复 | risk_level | MEDIUM | @slow |
| TC-FIX-003 | Timeline完整性 | timeline节点数 | ≥10个节点 | @slow |
| TC-FIX-004 | LLM调用记录 | llm_calls记录数 | 2-3条 | @slow |
| TC-FIX-005 | Dashboard pending_approval_count | 数值 | 0（非50） | — |
| TC-FIX-006 | 审批API JSON格式 | content-type | application/json, 非text/html | — |

---

## 3. 测试环境

| 项目 | 值 |
|------|-----|
| 目标URL | http://47.109.197.217:8001 |
| 登录凭据 | admin / admin |
| 测试框架 | pytest >= 9.1.1 + httpx |
| Python | >= 3.8 |
| HTTP超时 | 30s（单请求） |
| 工作流轮询间隔 | 3s |
| 工作流最大等待 | 120s |
| 测试文件 | tests/test_e2e_full.py |

---

## 4. 运行方式

```bash
# 全量运行（含慢速工作流测试）
pytest tests/test_e2e_full.py -v --tb=short

# 快速模式（跳过工作流轮询）
pytest tests/test_e2e_full.py -v --tb=short -k "not slow"

# 仅运行慢速关键修复验证
pytest tests/test_e2e_full.py -v --tb=short -k "KeyFix or slow"

# 指定自定义目标
BASE_URL=http://47.109.197.217:8001 pytest tests/test_e2e_full.py -v
```

---

## 5. 风险与限制

| 风险 | 级别 | 缓解 |
|------|------|------|
| 工作流执行时间不可控 | MEDIUM | 最长120s超时，超时标记FAIL |
| VPS网络延迟/重启 | HIGH | 内置重试机制(3次)，连接错误自动重试 |
| PORT_DOWN触发审批中断 | MEDIUM | 关键修复测试等待工作流完成或使用MAC_FLAPPING(不触发审批) |
| 测试设备名冲突 | LOW | 使用E2E-FULL-TEST-DEV-01命名，finally清理 |
| SQLite数据积累 | LOW | 不删除历史数据，仅验证结构和字段 |
</file_header>
