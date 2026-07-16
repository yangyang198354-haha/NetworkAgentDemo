<file_header>
  <file_path>docs/timeline_enhance_test_plan.md</file_path>
  <file_type>TEST_PLAN</file_type>
  <author_agent>sub_agent_test_engineer</author_agent>
  <created_at>2026-07-16T12:20:00Z</created_at>
  <version>1.0</version>
  <status>APPROVED</status>
</file_header>

# Timeline Enhancement Test Plan

## 1. 测试策略

### 1.1 测试目标
验证"告警详情页处理时间线（Timeline）组件增强"变更的正确性，覆盖 4 个核心文件的修改：

| 文件 | 模块 | 变更要点 |
|------|------|---------|
| `src/database/alert_models.py` | MOD-TL-001 | AlertTimeline 新增 sequence_number、duration_ms 列 |
| `src/database/repositories/alert_repository.py` | MOD-TL-003 | 新增 update_timeline_entry()、ensure_timeline_columns() |
| `src/orchestration/node_handlers.py` | MOD-TL-002 | _log_node 重写为 START INSERT + END UPDATE 双步持久化 |
| `webui/src/views/alerts/AlertsDetailView.vue` | MOD-TL-005 | 前端增强：序号 + 耗时渲染 + 智能轮询 |

### 1.2 测试范围

**In-Scope:**
- AlertTimeline 模型新列属性验证（存在性、可为空、类型）
- AlertRepository 新增方法功能验证（update、idempotent migration）
- _log_node START/END 双阶段 DB 持久化流程
- sequence_number 累加与 per-alert 隔离
- duration_ms 计算精度
- 旧记录向后兼容性
- 完整工作流集成

**Out-of-Scope:**
- 前端 Vue 组件渲染测试（需浏览器环境）
- 智能轮询逻辑测试（需 WebSocket/HTTP 实时环境）
- E2E 用户操作流测试
- 性能/压力测试

### 1.3 测试环境
- Python 3.12, pytest 9.0.1
- SQLite 文件级临时数据库（`tempfile.mkstemp`）
- WAL 模式 + 外键约束开启（与生产一致）
- `src.database.base.SessionLocal` monkey-patch 注入测试引擎

### 1.4 覆盖率目标
| 阶段 | 门控阈值 | 测量方式 |
|------|---------|---------|
| 单元测试 | >= 80% | pass / (pass + fail) x 100% |
| 集成测试 | >= 90% | pass / (pass + fail) x 100% |
| 回归测试 | 0 新增失败 | 全量测试套件 diff |

---

## 2. 测试用例清单

### 2.1 单元测试 — 模型列验证 (TC-UNIT-TL-001 ~ 003)

| TC-ID | 所属 US | 关联 AC | 级别 | 描述 | 前置条件 | 动作 | 预期结果 |
|-------|--------|--------|------|------|---------|------|---------|
| TC-UNIT-TL-001 | US-TL-001 | AC-TL-001-01 | UNIT | 验证 AlertTimeline 模型包含 sequence_number 和 duration_ms 属性 | AlertTimeline 模型已导入 | 检查 hasattr() 和 __table__.columns | 两个属性均存在 |
| TC-UNIT-TL-002 | US-TL-001 | AC-TL-001-02 | UNIT | 验证新列为 NULLABLE | AlertTimeline 模型已导入 | 检查 column.nullable | nullable=True |
| TC-UNIT-TL-003 | US-TL-001 | AC-TL-001-03 | UNIT | 验证新列类型为 Integer | AlertTimeline 模型已导入 | 检查 column.type | INTEGER |

### 2.2 单元测试 — Repository 方法 (TC-UNIT-TL-010 ~ 014)

| TC-ID | 所属 US | 关联 AC | 级别 | 描述 | 前置条件 | 动作 | 预期结果 |
|-------|--------|--------|------|------|---------|------|---------|
| TC-UNIT-TL-010 | US-TL-003 | AC-TL-003-01 | UNIT | update_timeline_entry 更新 status/completed_at/duration_ms | DB 中有 RUNNING 条目 | 调用 update_timeline_entry | 返回更新的条目，3 个字段正确 |
| TC-UNIT-TL-011 | US-TL-003 | AC-TL-003-02 | UNIT | update_timeline_entry 不存在 ID 返回 None | 空 DB 或 ID=99999 | 调用 update_timeline_entry(99999, {...}) | 返回 None |
| TC-UNIT-TL-012 | US-TL-003 | AC-TL-003-03 | UNIT | 部分更新仅修改 status | DB 中有条目 | 只传 {"status": "FAILED"} | status 更新，其他字段不变 |
| TC-UNIT-TL-013 | US-TL-003 | AC-TL-003-04 | UNIT | append_timeline_entry 可存储新字段 | DB 中有 alert | append 含 sequence_number 的条目 | 返回条目 seq 等于传入值 |
| TC-UNIT-TL-014 | US-TL-003 | AC-TL-003-05 | UNIT | ensure_timeline_columns 连续调用两次不报错 | 列已通过 create_all 创建 | 两次调用 ensure_timeline_columns() | 无异常抛出 |

### 2.3 单元测试 — _log_node 流程 (TC-UNIT-TL-020 ~ 027)

| TC-ID | 所属 US | 关联 AC | 级别 | 描述 | 前置条件 | 动作 | 预期结果 |
|-------|--------|--------|------|------|---------|------|---------|
| TC-UNIT-TL-020 | US-TL-002 | AC-TL-002-01 | UNIT | START 后在 DB 中创建 RUNNING 条目 | DB 中有 alert 记录 | _log_node(state, "parse_alert", "START") | 1 行，status=RUNNING，seq=1，dur=NULL |
| TC-UNIT-TL-021 | US-TL-002 | AC-TL-002-02 | UNIT | END 后更新 status、completed_at、duration_ms | START 已执行 | START → END | status=COMPLETED，completed_at 非空，duration_ms 非空 |
| TC-UNIT-TL-022 | US-TL-002 | AC-TL-002-03 | UNIT | 同一 alert 连续 3 次 START → 序号 1,2,3 | DB 中有 alert | 三次 START 不同 node_name | seqs=[1,2,3] |
| TC-UNIT-TL-023 | US-TL-002 | AC-TL-002-04 | UNIT | 不同 alert 各自独立计数 | DB 中有两个 alert | Alert A START x2，Alert B START x1 | A 序号 [1,2]，B 序号 [1] |
| TC-UNIT-TL-024 | US-TL-002 | AC-TL-002-05 | UNIT | duration_ms 与实际时间差一致（误差 < 100ms） | START 已执行 | START → sleep(50ms) → END | 0 ≤ duration_ms < 200 |
| TC-UNIT-TL-025 | US-TL-002 | AC-TL-002-06 | UNIT | status="FAILED" 传入后条目 status=FAILED | START 已执行 | START → END(status="FAILED") | DB status=FAILED |
| TC-UNIT-TL-026 | US-TL-002 | AC-TL-002-07 | UNIT | 多节点 START/END 周期 → 有序连续序号 | DB 中有 alert | 4 节点各一次 START/END | 4 行 COMPLETED，seq 1-4 |
| TC-UNIT-TL-027 | US-TL-002 | AC-TL-002-08 | UNIT | 无 START 直接 END 不崩溃 | 无前置 START | 直接调用 END | 不抛异常 |

### 2.4 单元测试 — 向后兼容 (TC-UNIT-TL-030 ~ 031)

| TC-ID | 所属 US | 关联 AC | 级别 | 描述 | 前置条件 | 动作 | 预期结果 |
|-------|--------|--------|------|------|---------|------|---------|
| TC-UNIT-TL-030 | US-TL-004 | AC-TL-004-01 | UNIT | 模拟旧记录（seq=NULL, dur=NULL）查询不报错 | DB 中有旧格式记录 | 用 ORM/原生 SQL 查询 | 返回值 seq=None, dur=None |
| TC-UNIT-TL-031 | US-TL-004 | AC-TL-004-02 | UNIT | get_alert_timeline 混合新旧记录返回全部 | DB 中有新旧两种记录 | 调用 get_alert_timeline | 返回 2 条 |

### 2.5 集成测试 (TC-INT-TL-001 ~ 003)

| TC-ID | 所属 US | 关联 AC | 级别 | 描述 | 前置条件 | 动作 | 预期结果 |
|-------|--------|--------|------|------|---------|------|---------|
| TC-INT-TL-001 | US-TL-ALL | AC-TL-002-ALL | INT | 完整 START→END 流程验证所有字段 | DB 中有 alert | 3 节点各 START→END | 3 COMPLETED，seq 1-3，completed_at 非空 |
| TC-INT-TL-002 | US-TL-ALL | AC-TL-002-06 | INT | 中途失败节点后续仍有序号 | DB 中有 alert | COMPLETED → FAILED → COMPLETED | 状态序列正确，seq 1,2,3 连续 |
| TC-INT-TL-003 | US-TL-ALL | AC-TL-002-ALL | INT | 通过 NodeHandlers 实际方法触发时间线 | DB 中有 alert | handle_receive_alert → handle_parse_alert | 时间线有对应条目，status COMPLETED |

---

## 3. 不可测试项

| AC-ID | 原因 |
|-------|------|
| AC-TL-005-01 (前端序号渲染) | 需浏览器环境，Vue 组件渲染测试超出本阶段范围 |
| AC-TL-005-02 (前端耗时渲染) | 同上 |
| AC-TL-006-01 (智能轮询逻辑) | 需 HTTP 实时服务环境 |

---

## 4. 门控条件

| 门控 | 条件 | 通过标准 |
|------|------|---------|
| UNIT_GATE | 单元测试通过率 | >= 80% |
| INT_GATE | 集成测试通过率 | >= 90% |
| REGRESSION_GATE | 全量回归零新增失败 | = 0 |
