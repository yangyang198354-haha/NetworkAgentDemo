<file_header>
  <project_id>NetworkAgentDemo</project_id>
  <module_id>real_device_e2e</module_id>
  <doc_type>unit_test_report</doc_type>
  <file_name>real_device_e2e_unit_test_report.md</file_name>
  <version>0.2.0</version>
  <status>PASSED</status>
  <author_agent>sub_agent_test_engineer</author_agent>
  <created_at>2026-09-05T17:25:00Z</created_at>
  <last_updated>2026-09-05T17:25:00Z</last_updated>
  <invocation_id>inv-real-e2e-d-002</invocation_id>
  <input_source>GROUP_RE_D 测试阶段 — PHASE_D2 单元测试执行（基于 APPROVED real_device_e2e_test_plan.md）</input_source>
</file_header>

# 真实设备（REAL）端到端工作流 — 单元测试报告

## 1. 单元测试摘要

- **执行时间**：2026-09-05T17:20Z
- **环境**：Windows 11 Pro（Python 3.14.6，pytest 9.1.1）
- **测试文件**：`tests/test_real_device_e2e_unit.py`
- **门控阈值**：单元测试通过率 ≥ 80%

| 指标 | 值 |
|------|-----|
| Total | 36 |
| Pass | 36 (100%) |
| Fail | 0 (0%) |
| Skip | 0 |
| Blocked | 0 |

- **通过率**：`pass / (pass + fail) = 36 / (36 + 0) = 100%`
- **算术一致性**：`total = pass + fail + skip + blocked = 36 + 0 + 0 + 0 = 36` ✓
- **门控结论**：**PASSED**（100% ≥ 80%，进入集成测试阶段）

## 2. 按模块分项结果

> 溯源说明：19 个 `TC-UNIT-*` 用例组在本文件展开为 36 个测试函数（每个 AC 的 Given/When/Then 边界情况拆分）。全部以 mock/monkeypatch 隔离 DB 与 `real_device_client`，**不连接真实交换机**。

### MOD-RE-001：REAL 接入上下文解析（resolve_real_access / enrich_device_info）

| TC-ID | 关联 AC | 测试函数 | 结果 |
|-------|--------|---------|------|
| TC-UNIT-001 | AC-RE-006-01 | test_db_no_device_returns_none | PASS |
| TC-UNIT-001 | AC-RE-006-01 | test_session_local_exception_returns_none | PASS |
| TC-UNIT-002 | AC-RE-001-02 | test_matched_device_resolves_frp_access | PASS |
| TC-UNIT-002 | AC-RE-001-02 | test_backfills_frp_protocol_model | PASS |

### MOD-RE-006：凭据解析（_resolve_real_credentials）

| TC-ID | 关联 AC | 测试函数 | 结果 |
|-------|--------|---------|------|
| TC-UNIT-003 | AC-RE-006-01 | test_env_priority_over_db | PASS |
| TC-UNIT-004 | AC-RE-006-01 | test_db_fernet_decrypt | PASS |
| TC-UNIT-005 | AC-RE-006-01 | test_missing_returns_none_no_admin123 | PASS |
| TC-UNIT-005 | AC-RE-006-01 | test_db_error_returns_none_no_admin123 | PASS |

### MOD-RE-003：诊断命令映射 + 解析（get_diag_commands / parse_diag_output）

| TC-ID | 关联 AC | 测试函数 | 结果 |
|-------|--------|---------|------|
| TC-UNIT-006 | AC-RE-003-03 | test_real_port_down | PASS |
| TC-UNIT-006 | AC-RE-003-03 | test_real_port_shutdown | PASS |
| TC-UNIT-006 | AC-RE-003-03 | test_real_cpu_high | PASS |
| TC-UNIT-006 | AC-RE-003-03 | test_real_mac_flapping_space_version | PASS |
| TC-UNIT-006 | AC-RE-003-03 | test_unknown_alert_type_real_falls_back | PASS |
| TC-UNIT-007 | AC-RE-007-02 | test_mock_port_down_uses_original_map | PASS |
| TC-UNIT-007 | AC-RE-007-02 | test_simulator_cpu_high_uses_original_map | PASS |
| TC-UNIT-008 | AC-RE-002-02 | test_real_port_down_structured | PASS |
| TC-UNIT-008 | AC-RE-002-02 | test_real_cpu_structured | PASS |
| TC-UNIT-009 | AC-RE-002-02 | test_real_parse_failure_returns_error | PASS |
| TC-UNIT-010 | AC-RE-002-02 | test_non_real_returns_raw | PASS |

### MOD-RE-004：修复能力裁决 + 降级（resolve_fix_capability / get_fix_template / build_degraded_fix_plan）

| TC-ID | 关联 AC | 测试函数 | 结果 |
|-------|--------|---------|------|
| TC-UNIT-011 | AC-RE-003-03 | test_real_port_fixable | PASS |
| TC-UNIT-011 | AC-RE-003-03 | test_real_cpu_mac_degraded | PASS |
| TC-UNIT-011 | AC-RE-003-03 | test_unknown_real_defaults_fixable | PASS |
| TC-UNIT-012 | AC-RE-003-03 | test_non_real_all_fixable | PASS |
| TC-UNIT-013 | AC-RE-003-03 | test_real_port_template | PASS |
| TC-UNIT-013 | AC-RE-003-03 | test_real_degraded_returns_none | PASS |
| TC-UNIT-014 | AC-RE-008-02 | test_empty_commands | PASS |

### MOD-RE-005：结构化验证（verify_real_fix）

| TC-ID | 关联 AC | 测试函数 | 结果 |
|-------|--------|---------|------|
| TC-UNIT-015 | AC-RE-004-01 | test_port_down_down_to_up_passes | PASS |
| TC-UNIT-016 | AC-RE-004-01 | test_port_shutdown_up_to_down_passes | PASS |
| TC-UNIT-017 | AC-RE-004-01 | test_cpu_high_not_fixable | PASS |
| TC-UNIT-017 | AC-RE-004-01 | test_mac_flapping_not_fixable | PASS |
| TC-UNIT-018 | AC-RE-004-01 | test_parse_failure_not_passed | PASS |

### MOD-RE-006：审计脱敏 + 写白名单常量（_sanitize_state_snapshot / 常量）

| TC-ID | 关联 AC | 测试函数 | 结果 |
|-------|--------|---------|------|
| TC-UNIT-019 | AC-RE-003-02 | test_removes_passwords_keeps_others | PASS |
| TC-UNIT-019 | AC-RE-003-02 | test_does_not_mutate_original | PASS |
| TC-UNIT-019 | AC-RE-003-02 | test_no_device_info_ok | PASS |
| TC-UNIT-019 | AC-RE-005-01 | test_whitelist_contains_only_authorized_port | PASS |
| TC-UNIT-005 | AC-RE-006-01 | test_credential_missing_msg_prohibits_admin123 | PASS |

## 3. 安全红线断言（本次单元测试重点覆盖）

1. **无 admin123 兜底**：`_resolve_real_credentials` 在无 env / 无 DB 凭据 / DB 异常三种情况下均返回 `None`，绝不回落 `("admin","admin123")`（TC-UNIT-005）。
2. **密码脱敏**：`_sanitize_state_snapshot` 移除 `password` / `enable_password`，且不修改原 state（TC-UNIT-019）。
3. **写白名单唯一性**：`REAL_WRITE_PORT_WHITELIST == frozenset({"Gi1/0/2"})`（TC-UNIT-019/AC-RE-005-01）。
4. **MAC 诊断命令空格版**：`get_diag_commands("MAC_FLAPPING","REAL")` 返回 `show mac address-table`（空格版，探测已核实），不含连字符版。

## 4. 失败汇总（需路由给 developer）

无。36/36 PASS，无 FAIL / SKIP / BLOCKED。

<audit_log>
  <log time="2026-09-05T17:25:00Z" state="WRITE_FILES" action="file_write" result="SUCCESS" trace_id="inv-real-e2e-d-002" file_path="project_workspace/real_device_e2e/testing/real_device_e2e_unit_test_report.md"/>
</audit_log>
