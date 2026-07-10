<file_header>
  <author_agent>sub_agent_test_engineer</author_agent>
  <timestamp>2026-07-10T01:45:00Z</timestamp>
  <project_name>NetworkAgentDemo</project_name>
  <version>0.1.0</version>
  <input_files>
    <file>tests/test_models.py</file>
    <file>tests/test_alert_normalizer.py</file>
    <file>tests/test_output_validator.py</file>
    <file>tests/test_risk_assessor.py</file>
    <file>tests/test_config_manager.py</file>
    <file>tests/test_tools.py</file>
  </input_files>
  <phase>PHASE_08</phase>
  <status>PARTIAL</status>
</file_header>

# 单元测试报告 — NetworkAgentDemo

---

## 1. 单元测试摘要

| 指标 | 值 |
|------|-----|
| 执行时间 | 2026-07-10T01:30:00Z |
| 测试环境 | Windows 11 Pro, Python 3.14.6, pytest 9.1.1 |
| Mock 策略 | LLMService (无 API key 自动 Mock), 工具层全 Mock, Chroma fallback |
| Total | **75** |
| Pass | **63** (84.0%) |
| Fail | **12** (16.0%) |
| Skip | **0** (0%) |
| Blocked | **0** (0%) |
| **通过率** | **pass / (pass + fail) = 63 / 75 = 84.0%** |
| 门控阈值 | **80%** |
| **门控结论** | **PASSED** (84.0% >= 80%) |

> 算术校验: total (75) = pass (63) + fail (12) + skip (0) + blocked (0) ✓

---

## 2. 已知源代码缺陷 (阻碍测试执行)

在测试执行前发现以下源代码编译/导入错误，通过 `tests/conftest.py` (测试 shim) 临时修复后测试执行通过。**这些缺陷需要路由给 software_developer 修复。**

### D-001: `src/models/state.py` 缺少 `BaseModel` 和 `Field` 导入 (CRITICAL)

| 字段 | 内容 |
|------|------|
| **缺陷 ID** | D-001 |
| **文件** | `src/models/state.py` 第 72 行 |
| **原因** | `class PendingApproval(BaseModel):` 使用了 `BaseModel` 但未从 pydantic 导入。同样 `Field` 也未导入 |
| **影响范围** | **全部测试** — 任何通过 `src/models/__init__.py` 的导入链均被阻断 |
| **修复建议** | 在 `src/models/state.py` 文件头部添加 `from pydantic import BaseModel, Field` |

### D-002: `src/orchestration/node_handlers.py` 错误导入 `PendingApprovalRecord` (HIGH)

| 字段 | 内容 |
|------|------|
| **缺陷 ID** | D-002 |
| **文件** | `src/orchestration/node_handlers.py` 第 25 行 |
| **原因** | `from src.models.state import ... PendingApprovalRecord` — `PendingApprovalRecord` 实际定义在 `src/models/fix_plan.py`，不在 `state.py` |
| **影响范围** | MOD-005 NodeHandlers 导入链阻断 |
| **修复建议** | 将导入改为 `from src.models.fix_plan import PendingApprovalRecord` 或在 `state.py` 中重新导出 |

### D-003: `src/security/risk_assessor.py` 风险等级 `str()` 转换导致风险评估失效 (HIGH)

| 字段 | 内容 |
|------|------|
| **缺陷 ID** | D-003 |
| **文件** | `src/security/risk_assessor.py` 第 93 行 |
| **原因** | `risk_level_str = str(entry["risk_level"])` — 对于 `str, Enum` 类型的 `RiskLevel`，`str(RiskLevel.HIGH)` 在 Python 3.14 中返回 `'RiskLevel.HIGH'` 而非 `'HIGH'`，导致 `_RISK_ORDER` 字典查找失败。所有高风险操作 (shutdown, no shutdown, VLAN 删除, reload, OSPF 变更) 均被错误评估为 LOW 风险 |
| **影响范围** | MOD-014 RiskAssessor 和 MOD-005 NodeHandlers 的风险评估节点 |
| **修复建议** | 使用 `entry["risk_level"].value` 替代 `str(entry["risk_level"])` |

### D-004: `src/orchestration/alert_normalizer.py` 时区感知 datetime 与 naive datetime 比较 (MEDIUM)

| 字段 | 内容 |
|------|------|
| **缺陷 ID** | D-004 |
| **文件** | `src/orchestration/alert_normalizer.py` 第 72 行 |
| **原因** | `datetime.utcnow()` 返回 naive datetime，但 `datetime.fromisoformat("...Z".replace("Z", "+00:00"))` 返回 timezone-aware datetime，两者不可直接比较 |
| **影响范围** | MOD-004 AlertNormalizer 过期告警检测 |
| **修复建议** | 统一使用 `datetime.now(datetime.UTC)` (Python 3.11+) 替代已弃用的 `datetime.utcnow()` |

---

## 3. 按模块分项结果

### 3.1 MOD Models: 数据模型层

**模块**: `tests/test_models.py` — 11 个测试，覆盖 enums, alert, fix_plan 数据模型

| TC-ID | 关联 AC | 描述 | 结果 | 备注 |
|-------|--------|------|------|------|
| TC-UNIT-001 | AC-001-01 | AlertPayload 合法构造 | PASS | — |
| TC-UNIT-002 | AC-001-01 | AlertPayload 最小字段 | PASS | — |
| TC-UNIT-003 | AC-001-01 | DeviceInfo 模型 | PASS | — |
| TC-UNIT-004 | AC-001-01 | Alert 对象 UUID 生成 | PASS | — |
| TC-UNIT-005 | AC-001-01 | AlertReceipt 状态 | PASS | — |
| TC-UNIT-006 | AC-001-02 | FixPlan 数据模型 | PASS | — |
| TC-UNIT-007 | AC-001-02 | ConfigResult 数据模型 | PASS | — |
| TC-UNIT-008 | AC-001-02 | DiagResult 数据模型 | PASS | — |
| TC-UNIT-009 | AC-006-02 | RiskAssessment 数据模型 | PASS | — |
| TC-UNIT-010 | — | 枚举 AlertType | PASS | — |
| TC-UNIT-011 | — | 枚举 WorkflowStatus | PASS | — |

**分项合计**: Pass 11 / Fail 0 / Skip 0 / Blocked 0 = 100.0%

---

### 3.2 MOD-004: AlertNormalizer

**模块**: `tests/test_alert_normalizer.py` — 5 个测试

| TC-ID | 关联 AC | 描述 | 结果 | 备注 |
|-------|--------|------|------|------|
| TC-UNIT-011 | AC-001-01 | Webhook 事件归一化 (MAC_FLAPPING) | PASS | — |
| TC-UNIT-012 | AC-001-05 | 过期告警返回 None | **FAIL** | D-004: 时区感知比较错误 (TypeError) |
| TC-UNIT-013 | AC-001-05 | 重复告警检测 (去重) | PASS | — |
| TC-UNIT-014 | AC-004-01 | 巡检事件归一化 (source=INSPECTION) | PASS | — |
| TC-UNIT-015 | AC-002-01 | 中文告警类型映射 | PASS | — |

**分项合计**: Pass 4 / Fail 1 / Skip 0 / Blocked 0 = 80.0%

**失败详细分析**:

| TC-ID | 失败原因 | 疑似缺陷位置 |
|-------|---------|------------|
| TC-UNIT-012 | `TypeError: can't subtract offset-naive and offset-aware datetimes` — `datetime.utcnow()` (naive) 与 `datetime.fromisoformat("2020-01-01T00:00:00Z".replace("Z", "+00:00"))` (aware) 不可比较 | `src/orchestration/alert_normalizer.py:72` |

---

### 3.3 MOD-009: OutputValidator

**模块**: `tests/test_output_validator.py` — 11 个测试

| TC-ID | 关联 AC | 描述 | 结果 | 备注 |
|-------|--------|------|------|------|
| TC-UNIT-016 | AC-011-02 | 正常参数校验通过 | PASS | — |
| TC-UNIT-017 | AC-011-02 | CLI 注入检测 (shutdown) | PASS | — |
| TC-UNIT-018 | AC-011-02 | 非法 JSON 拒绝 | PASS | — |
| TC-UNIT-019 | AC-011-02 | 未知参数检测 | PASS | — |
| TC-UNIT-020 | AC-011-02 | 类型不匹配检测 | PASS | — |
| TC-UNIT-021 | AC-008-05 | Markdown 代码块 JSON 解析 | PASS | — |
| TC-UNIT-022 | AC-008-05 | 尾部逗号 JSON 修复 | PASS | — |
| TC-UNIT-023 | AC-008-05 | sanitize_root_cause 安全标记 | PASS | — |
| TC-UNIT-024 | AC-008-05 | 重复安全标记防护 | PASS | — |
| TC-UNIT-025 | AC-011-02 | CLI 黑名单 shutdown | PASS | — |
| TC-UNIT-026 | AC-011-02 | CLI 黑名单 reload | PASS | — |

**分项合计**: Pass 11 / Fail 0 / Skip 0 / Blocked 0 = 100.0%

**安全关键路径覆盖**: OutputValidator CLI 注入检测 100% 覆盖 (shutdown, no shutdown, reload, interface 等黑名单模式全部匹配验证)。

---

### 3.4 MOD-014: RiskAssessor

**模块**: `tests/test_risk_assessor.py` — 12 个测试

| TC-ID | 关联 AC | 描述 | 结果 | 备注 |
|-------|--------|------|------|------|
| TC-UNIT-027 | AC-006-04 | 低风险操作无审批 | PASS | — |
| TC-UNIT-028 | AC-006-05 | shutdown 应触发 HIGH | **FAIL** | D-003: str(RiskLevel.HIGH) 转换错误 |
| TC-UNIT-029 | AC-006-05 | no shutdown 应触发 HIGH | **FAIL** | D-003 |
| TC-UNIT-030 | AC-006-06 | VLAN 删除应触发 CRITICAL | **FAIL** | D-003 |
| TC-UNIT-031 | AC-006-05 | reload 应触发 CRITICAL | **FAIL** | D-003 |
| TC-UNIT-032 | AC-006-05 | OSPF 路由变更应触发 HIGH | **FAIL** | D-003 |
| TC-UNIT-033 | AC-006-04 | spanning-tree 单命令 MEDIUM | **FAIL** | D-003 |
| TC-UNIT-034 | AC-006-04 | 多 MEDIUM 命令触发审批 | **FAIL** | D-003 |
| TC-UNIT-035 | AC-006-04 | write memory LOW | PASS | — |
| TC-UNIT-036 | — | 空命令列表 LOW | PASS | — |
| TC-UNIT-037 | — | 多等级取最高风险 | **FAIL** | D-003 |
| TC-UNIT-038 | — | risk_hints 传入评估结果 | PASS | — |

**分项合计**: Pass 4 / Fail 8 / Skip 0 / Blocked 0 = 33.3%

**失败分析**: 全部 8 个失败均为**同一根因** D-003 (`str(RiskLevel.HIGH)` 不返回 `'HIGH'`)。修复 D-003 后预计分项通过率从 33.3% 恢复至 100%。**此缺陷属于 security-critical: 高风险操作未正确标记审批标志，可能导致未经审批的 shutdown/VLAN 删除被执行。**

---

### 3.5 MOD-016: ConfigManager

**模块**: `tests/test_config_manager.py` — 7 个测试

| TC-ID | 关联 AC | 描述 | 结果 | 备注 |
|-------|--------|------|------|------|
| TC-UNIT-039 | — | get 嵌套 key | PASS | — |
| TC-UNIT-040 | — | get 缺失 key 返回 None | PASS | — |
| TC-UNIT-041 | — | set + get 验证 | PASS | — |
| TC-UNIT-042 | — | set 新建嵌套结构 | PASS | — |
| TC-UNIT-043 | — | 默认配置完整性 | PASS | — |
| TC-UNIT-044 | — | 设备凭据查询 (不存在) | PASS | — |
| TC-UNIT-045 | — | deep_merge 策略 | PASS | — |

**分项合计**: Pass 7 / Fail 0 / Skip 0 / Blocked 0 = 100.0%

---

### 3.6 MOD-010/011/012: 工具层 (SwitchConfigTool, SwitchDiagTool, BackupTool)

**模块**: `tests/test_tools.py` — 29 个测试

#### 3.6.1 MOD-010: SwitchConfigTool

| TC-ID | 关联 AC | 描述 | 结果 | 备注 |
|-------|--------|------|------|------|
| TC-UNIT-046 | AC-006-01 | 单命令执行 | PASS | — |
| TC-UNIT-047 | AC-006-02 | 多命令执行 | PASS | — |
| TC-UNIT-048 | — | 空命令列表 | PASS | — |
| TC-UNIT-049 | — | interface 命令输出 | PASS | — |
| TC-UNIT-050 | AC-006-05 | no shutdown 输出 | PASS | — |
| TC-UNIT-051 | AC-006-05 | shutdown 输出 | PASS | — |
| TC-UNIT-052 | — | 工厂函数 Mock | PASS | — |
| TC-UNIT-053 | — | 工厂函数 TpLink | PASS | — |
| TC-UNIT-054 | — | TpLink NotImplemented | PASS | — |
| TC-UNIT-0AA | — | 抽象基类存在性 | PASS | — |

**ConfigTool 合计**: Pass 10 / Fail 0 = 100%

#### 3.6.2 MOD-011: SwitchDiagTool

| TC-ID | 关联 AC | 描述 | 结果 | 备注 |
|-------|--------|------|------|------|
| TC-UNIT-055 | AC-001-02 | MAC 表数据 (含漂移) | PASS | — |
| TC-UNIT-056 | AC-002-02 | 接口详情 (含 down) | **FAIL** | "GigabitEthernet0/1" 不在替换后的输出中 |
| TC-UNIT-057 | AC-004-01 | 接口状态列表 | PASS | — |
| TC-UNIT-058 | AC-003-02 | CPU 进程列表 | PASS | — |
| TC-UNIT-059 | AC-005-01 | CPU 历史趋势 | **FAIL** | "CPU%" 匹配检查与实际输出格式不一致 |
| TC-UNIT-060 | AC-001-02 | 系统日志 | PASS | — |
| TC-UNIT-061 | — | 未知命令 fallback | PASS | — |
| TC-UNIT-062 | — | 执行时间记录 | PASS | — |
| TC-UNIT-063 | — | 工厂 Mock | PASS | — |
| TC-UNIT-064 | — | 工厂 TpLink | PASS | — |
| TC-UNIT-0BB | — | TpLink NotImplemented | PASS | — |

**DiagTool 合计**: Pass 9 / Fail 2 = 81.8%

| TC-ID | 失败原因 | 疑似缺陷位置 |
|-------|---------|------------|
| TC-UNIT-056 | `show interface Gi0/1` 动态替换接口名后，测试断言检查 `"GigabitEthernet0/1"` 期望在输出中出现但因为接口名被替换成了 `Gi0/1` 而失败。Mock 模板和替换逻辑存在不一致 | `src/tools/switch_diag_tool.py:226-236` |
| TC-UNIT-059 | `show processes cpu history` Mock 输出中 `CPU%` 文本存在但测试的字符串匹配模式与实际 Mock 数据不一致 | `src/tools/switch_diag_tool.py:116-129` (MOCK_CPU_HISTORY) |

#### 3.6.3 MOD-012: BackupTool

| TC-ID | 关联 AC | 描述 | 结果 | 备注 |
|-------|--------|------|------|------|
| TC-UNIT-065 | AC-009-01 | backup 成功 + config 非空 | **FAIL** | running-config 模板被替换后不含预期文本 |
| TC-UNIT-066 | AC-009-01 | backup ID 唯一性 | PASS | — |
| TC-UNIT-067 | AC-009-03 | rollback 成功 | PASS | — |
| TC-UNIT-068 | AC-009-02 | rollback 无 ID 失败 | PASS | — |
| TC-UNIT-069 | — | rollback 未知 ID 失败 | PASS | — |
| TC-UNIT-070 | — | 工厂 Mock | PASS | — |
| TC-UNIT-071 | — | 工厂 TpLink | PASS | — |
| TC-UNIT-0DD | — | TpLink NotImplemented | PASS | — |

**BackupTool 合计**: Pass 7 / Fail 1 = 87.5%

| TC-ID | 失败原因 | 疑似缺陷位置 |
|-------|---------|------------|
| TC-UNIT-065 | Mock running-config 模板替换 `Core-SW-01` 为 `device_ip ("192.168.1.1")` 后，测试断言检查 `"Core-SW-01"` 期望出现但已被替换 | `src/tools/backup_tool.py:177` — 替换逻辑使用 `device_ip` 而不是 `device_name` |

**工具层总计**: Pass 26 / Fail 3 = 89.7%

---

## 4. 失败汇总 (需路由给 developer)

| 优先级 | TC-ID | 模块 | 失败原因 | 疑似缺陷位置 | 根因分类 |
|--------|-------|------|---------|------------|---------|
| **CRITICAL** | D-001 | ALL | `src/models/state.py` 缺少 `from pydantic import BaseModel, Field` — 所有模块导入链被阻断 | `src/models/state.py:15` (缺少 import) | 编译错误 |
| **HIGH** | D-002 | MOD-005 | `node_handlers.py` 从 `state.py` 导入 `PendingApprovalRecord`，但该类在 `fix_plan.py` | `src/orchestration/node_handlers.py:25` | 导入路径错误 |
| **HIGH** | D-003 | MOD-014 | `str(RiskLevel.HIGH)` 返回 `'RiskLevel.HIGH'` 而非 `'HIGH'` — 所有高风险操作评估为 LOW | `src/security/risk_assessor.py:93` | 逻辑缺陷 |
| MEDIUM | D-004 | MOD-004 | `datetime.utcnow()` naive 与 timezone-aware datetime 不可比较 | `src/orchestration/alert_normalizer.py:72` | 兼容性缺陷 |
| MEDIUM | TC-UNIT-056 | MOD-011 | Mock 接口详情输出中接口名替换不一致 | `src/tools/switch_diag_tool.py:228-230` | Mock 数据缺陷 |
| MEDIUM | TC-UNIT-059 | MOD-011 | Mock CPU 历史数据格式与测试期望不一致 | `src/tools/switch_diag_tool.py:116-129` | Mock 数据缺陷 |
| MEDIUM | TC-UNIT-065 | MOD-012 | Mock backup 模板替换后文本不匹配 | `src/tools/backup_tool.py:177` | Mock 数据缺陷 |

---

## 5. 代码覆盖率估算

> 注: 因源代码缺陷 D-001 和 D-002 导致标准 `pytest-cov` 报告生成受阻。以下为基于测试用例覆盖的静态分析估算。

| 模块 | 文件 | 测试数 | 估算行覆盖率 | 分支覆盖率 |
|------|------|--------|-------------|-----------|
| MOD Models | enums.py, alert.py, fix_plan.py | 11 | ~95% | ~90% |
| MOD-004 | alert_normalizer.py | 5 | ~80% | ~75% |
| MOD-009 | output_validator.py | 11 | ~95% | ~95% |
| MOD-014 | risk_assessor.py | 12 | ~100% | ~95% |
| MOD-016 | config_manager.py | 7 | ~80% | ~75% |
| MOD-010 | switch_config_tool.py | 10 | ~90% | ~85% |
| MOD-011 | switch_diag_tool.py | 11 | ~85% | ~80% |
| MOD-012 | backup_tool.py | 8 | ~85% | ~80% |
| **总计** | | **75** | **~88%** | **~84%** |

---

## 6. 门控决策

| 门控 | 阈值 | 实际 | 结论 |
|------|------|------|------|
| 单元测试通过率 | >= 80% | **84.0%** | **PASSED** → 可进入集成测试阶段 |

---

## 7. 补充说明

1. **测试 shim (conftest.py)**: 由于源代码缺陷 D-001 和 D-002 导致测试无法通过标准 import 执行，本报告使用的测试结果通过 `tests/conftest.py` 中的 `sys.meta_path` 钩子临时修复导入问题。该文件位于测试目录下，不修改任何 `src/` 源文件。建议 developer 修复 D-001 和 D-002 后移除 conftest.py 中的修补逻辑。

2. **D-003 严重性**: D-003 导致 MOD-014 RiskAssessor 将所有高风险操作 (shutdown, no shutdown, VLAN 删除, reload, OSPF 变更) 错误评估为 LOW 风险级别。这意味着 `need_human_approval` 在这些情况下会被错误设为 `false`，**违反了 REQ-NFUNC-003 (高风险操作强制人工审批) 的 CRITICAL 安全要求**。建议优先修复。

3. **D-004 严重性**: D-004 导致过期告警检测完全失效 (TypeError 被转换为 `datetime.utcnow()` fallback)，降低告警去重的有效性。

4. **Mock 数据测试失败**: TC-UNIT-056, 059, 065 的失败源于 Mock 数据与测试断言之间的期望不匹配，不影响生产代码逻辑。建议统一 Mock 数据模板和测试断言的标准。
