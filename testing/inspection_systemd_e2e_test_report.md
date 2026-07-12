<file_header>
  <author_agent>sub_agent_test_engineer</author_agent>
  <timestamp>2026-07-12T00:00:00Z</timestamp>
  <project_name>NetworkAgentDemo</project_name>
  <version>0.2.0</version>
  <input_files>
    <file>testing/inspection_systemd_test_plan.md</file>
    <file>testing/inspection_systemd_unit_test_report.md</file>
    <file>testing/inspection_systemd_integration_test_report.md</file>
  </input_files>
  <phase>PHASE_INSP_04</phase>
  <status>APPROVED</status>
</file_header>

# E2E 测试执行报告 -- 巡检机制 systemd 重构 (重试 v2)

---

## 1. E2E 测试摘要

| 指标 | 值 |
|------|-----|
| 执行时间 | 2026-07-12 (重试) |
| 测试环境 | Windows 11 Pro, Python 3.14.6, pytest 9.1.1 |
| 前置: python-jose | 已安装 (v3.5.0) |
| 前置: python-multipart | 已安装 (v0.0.32) |
| **Total** | **9** |
| **Pass** | **2 (22.22%)** |
| **Fail** | **7 (77.78%)** |
| **Skip** | **0** |
| **Blocked** | **0 (0.00%)** |
| Critical Path 覆盖率 (Must Have 故事) | **25.00%** (2/8 故事通过) |

### 前置门控检查

| 条件 | 结果 |
|------|------|
| 单元测试通过率 >= 80% | **PASSED (100.00%)** |
| 集成测试通过率 >= 90% | **FAILED (50.00%)** |
| python-jose 已安装 | **PASSED** |
| python-multipart 已安装 | **PASSED** |
| **前置门控** | **FAILED** -- 集成测试未通过门控 |

> **门控违规说明**: 根据测试规程，集成测试通过率 < 90% 时禁止开始 E2E 测试。本次执行是在 PM 明确指令下进行的，结果仅供参考，不应作为 E2E 正式门控判定依据。

### 与上次测试的对比

| 指标 | 上次 (BLOCKED) | 本次 (重试) |
|------|---------------|------------|
| Total | 9 | 9 |
| Pass | 0 | 2 |
| Fail | 0 | 7 |
| Blocked | 9 (ENV-DEP-001) | 0 |
| 通过率 | N/A | 22.22% |
| 阻塞原因 | python-jose/multipart 未安装 | — |
| 新失败原因 | — | Mock 目标属性不存在 (TEST-BUG-002) |

---

## 2. 用户旅程测试详情

---

### TC-E2E-200: 巡检配置管理完整旅程 (US-INSP-001)

- **关联 AC**: AC-INSP-001-01~05
- **结果**: **FAIL**
- **根因**: TEST-BUG-002: monkeypatch 目标 `"src.api.inspection_router._get_systemctl_executor"` 不存在于 APIRouter 对象上
- **预期路径**: GET /config -> PUT /config -> GET /config verify -> Validation test
- **实际结果**: `AttributeError: 'APIRouter' object has no attribute '_get_systemctl_executor'`

---

### TC-E2E-201: systemd Unit 文件生成完整流程 (US-INSP-002)

- **关联 AC**: AC-INSP-002-01~05
- **结果**: **FAIL**
- **根因**: TEST-BUG-002 (同 TC-E2E-200)
- **预期路径**: PUT /config -> verify unit file generation -> daemon-reload chain

---

### TC-E2E-202: 巡检状态查询完整旅程 (US-INSP-003)

- **关联 AC**: AC-INSP-003-01~05
- **结果**: **FAIL**
- **根因**: TEST-BUG-002 (同 TC-E2E-200)
- **预期路径**: GET /status (available) -> GET /status (unavailable)

---

### TC-E2E-203: 巡检服务生命周期控制完整旅程 (US-INSP-004)

- **关联 AC**: AC-INSP-004-01~06
- **结果**: **FAIL**
- **根因**: TEST-BUG-002 (同 TC-E2E-200)
- **预期路径**: start -> status -> stop -> status -> restart -> status

---

### TC-E2E-204: Timer 启用/禁用完整旅程 (US-INSP-005)

- **关联 AC**: AC-INSP-005-01~05
- **结果**: **FAIL**
- **根因**: TEST-BUG-002 (同 TC-E2E-200)
- **预期路径**: enable -> status -> disable -> status -> idempotent enable

---

### TC-E2E-205: 手动触发巡检完整旅程 (US-INSP-006)

- **关联 AC**: AC-INSP-006-01~05
- **结果**: **FAIL**
- **根因**: TEST-BUG-002 (同 TC-E2E-200)
- **预期路径**: trigger -> success -> re-trigger 409 -> unavailable 503

---

### TC-E2E-206: 巡检历史查询完整旅程 (US-INSP-007)

- **关联 AC**: AC-INSP-007-01~06
- **结果**: **FAIL**
- **根因**: TEST-BUG-002 (同 TC-E2E-200)
- **预期路径**: list -> paginate -> filter trigger_mode -> filter status

---

### TC-E2E-207: systemd 定时触发 CLI 巡检旅程 (US-INSP-008)

- **关联 AC**: AC-INSP-008-01~07
- **结果**: **PASS** (2 个子测试均通过)

**test_cli_inspection_full_flow** — CLI 巡检全流程:

| 步骤 | 操作 | 期望响应 | 实际响应 | 结果 |
|------|------|---------|---------|------|
| 1 | 构造 InspectionCLI 实例 | CLI 正常初始化 | InspectionCLI 实例创建成功 | PASS |
| 2 | Mock _init_db 绕过真实 DB | 不抛出异常 | DB 初始化被跳过 | PASS |
| 3 | Mock load_inspection_config | 返回 4 键配置字典 | interval_minutes=10 等 | PASS |
| 4 | Mock load_device_list 返回空列表 | 返回 [] | [] | PASS |
| 5 | 调用 cli.run() | CLIExitCode.SUCCESS | CLIExitCode.SUCCESS (0) | PASS |

**test_cli_exit_codes** — 退出码枚举:

| 步骤 | 操作 | 期望响应 | 实际响应 | 结果 |
|------|------|---------|---------|------|
| 1 | 验证 SUCCESS | CLIExitCode.SUCCESS == 0 | 0 | PASS |
| 2 | 验证 PARTIAL | CLIExitCode.PARTIAL == 1 | 1 | PASS |
| 3 | 验证 FAILURE | CLIExitCode.FAILURE == 2 | 2 | PASS |

- **最终结论**: **PASS** — CLI 巡检完整流程通过，退出码枚举正确

---

### TC-E2E-208: 跨用户故事完整流程 (US-INSP-001~008)

- **关联 AC**: ALL Must Have ACs
- **结果**: **FAIL**
- **根因**: TEST-BUG-002 (同 TC-E2E-200)
- **预期路径**: config -> sync -> status -> control -> trigger -> history

---

## 3. 失败根因分析

### TEST-BUG-002: E2E 测试 Mock 目标属性解析错误 (CRITICAL)

**所有 7 个失败 E2E 测试的公共根因**

| 字段 | 内容 |
|------|------|
| **缺陷 ID** | TEST-BUG-002 |
| **文件** | `tests/test_inspection_systemd_e2e.py` 第 105-106 行 |
| **原因** | E2E 测试通过 `monkeypatch.setattr("src.api.inspection_router._get_systemctl_executor", ...)` 尝试 Mock 模块级工厂函数。但在 Python 导入链中，`src.api.inspection_router` 解析为 `APIRouter` 对象实例（而非模块），该对象没有 `_get_systemctl_executor` 属性。结果: `AttributeError: 'APIRouter' object has no attribute '_get_systemctl_executor'` |
| **影响范围** | 7 个 E2E 测试: TC-E2E-200, 201, 202, 203, 204, 205, 206, 208 |
| **不受影响** | 2 个 CLI 测试 (TC-E2E-207) — 不依赖 FastAPI 应用, 直接操作 InspectionCLI |
| **建议修复** | 方案 A: 使用 `monkeypatch.setattr` 时传入模块对象而非字符串路径（需要保存对 inspection_router 模块的引用）。方案 B: 在 `_create_app_with_full_mocks` 中先保存模块引用 (`from src.api import inspection_router as _mod`)，然后使用 `monkeypatch.setattr(_mod, "_get_systemctl_executor", ...)`。方案 C: 直接将 `_get_systemctl_executor` 和 `_get_systemd_unit_manager` 改为依赖注入 (FastAPI Depends)，由 `app.dependency_overrides` 统一管理 |

### TEST-BUG-001 (级联影响)

集成测试中发现的 DB session 表隔离问题 (TEST-BUG-001) 也会影响 E2E 测试中涉及数据库查询的步骤。即使修复 TEST-BUG-002，部分 E2E 测试可能仍会因 TEST-BUG-001 而失败。

---

## 4. Critical Path 覆盖率分析

| Must Have 故事 | 关联 E2E TC | 结果 | 覆盖 |
|---------------|-------------|------|------|
| US-INSP-001 (配置管理) | TC-E2E-200 | FAIL (TEST-BUG-002) | 0% |
| US-INSP-002 (Unit 文件生成) | TC-E2E-201 | FAIL (TEST-BUG-002) | 0% |
| US-INSP-003 (状态查询) | TC-E2E-202 | FAIL (TEST-BUG-002) | 0% |
| US-INSP-004 (生命周期控制) | TC-E2E-203 | FAIL (TEST-BUG-002) | 0% |
| US-INSP-005 (Timer 启停) | TC-E2E-204 | FAIL (TEST-BUG-002) | 0% |
| US-INSP-006 (手动触发) | TC-E2E-205 | FAIL (TEST-BUG-002) | 0% |
| US-INSP-007 (历史查询) | TC-E2E-206 | FAIL (TEST-BUG-002) | 0% |
| US-INSP-008 (CLI 巡检) | TC-E2E-207 | **PASS** | **100%** |
| 跨故事流程 | TC-E2E-208 | FAIL (TEST-BUG-002) | 0% |
| **总 Critical Path** | | | **12.5% (1/8 故事)** |

---

## 5. 算术一致性校验

```
total = pass + fail + skip + blocked
9     = 2    + 7    + 0    + 0
9     = 9 ✓

通过率 = pass / (pass + fail) × 100%
       = 2 / 9 × 100%
       = 22.22% ✓
```

---

## 6. 门控结论

| 条件 | 结果 |
|------|------|
| 前置门控 (集成测试 >= 90%) | **FAILED** |
| E2E Critical Path >= 100% | **FAILED (12.5%)** |
| **总体门控结论** | **FAILED -- 前置阶段未通过，E2E 测试不应正式执行** |

> 本次执行是在 PM 明确指令下的验证性运行。正式 E2E 测试应在集成测试修复 TEST-BUG-001 并通过 >= 90% 门控后再执行。

---

## 7. 需路由的事项

### 7.1 需路由给 Developer

| 优先级 | 事项 | 说明 |
|--------|------|------|
| **CRITICAL** | TEST-BUG-002: E2E monkeypatch 目标属性解析错误 | `monkeypatch.setattr("src.api.inspection_router._get_systemctl_executor", ...)` 中 `src.api.inspection_router` 解析为 APIRouter 对象而非模块。需调整 Mock 策略或在 `src/api/__init__.py` 中保留模块引用 |
| **HIGH** | TEST-BUG-001 (级联影响) | 集成测试中发现的 DB session 表隔离问题，修复后将影响 E2E 测试中涉及 DB 查询的步骤 |

### 7.2 需路由给 PM

| 优先级 | 事项 | 说明 |
|--------|------|------|
| **HIGH** | 正式 E2E 门控不可绕过 | 集成测试通过率 50.00% 未达标，E2E 测试应在集成测试修复后重新执行 |
| **MEDIUM** | TEST-BUG-001 和 TEST-BUG-002 需协调修复 | 两个测试缺陷均影响 FastAPI TestClient 场景。建议统一使用 `app.dependency_overrides` 机制处理 router 依赖注入和 systemd mock |

---

## 8. 全阶段门控链总结

```
UNIT (109 test)    → PASS  (100.00%)  ✓ 门控 >= 80%
  ↓
INT  (18 test)     → FAIL  (50.00%)   ✗ 门控 >= 90%
  ↓
E2E  (9 test)      → N/A   (22.22%)  ✗ 前置门控未通过
```

**下一步建议**:
1. Developer 修复 TEST-BUG-001 (DB session 表隔离) 和 TEST-BUG-002 (Mock 属性路径)
2. 重新执行集成测试，验证通过率 >= 90%
3. 在集成测试门控通过后，重新执行 E2E 测试
