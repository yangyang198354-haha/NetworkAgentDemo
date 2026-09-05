<file_header>
  <project_id>NetworkAgentDemo</project_id>
  <module_id>real_device_panel</module_id>
  <doc_type>integration_test_report</doc_type>
  <file_name>real_panel_integration_test_report.md</file_name>
  <version>0.1.0</version>
  <status>APPROVED</status>
  <author_agent>sub_agent_test_engineer</author_agent>
  <created_at>2026-09-05T00:00:00Z</created_at>
  <last_updated>2026-09-05T00:00:00Z</last_updated>
  <invocation_id>inv-real-panel-d-001</invocation_id>
  <input_source>PM agent_invocation — REAL_DEVICE_PANEL / GROUP_RP_D（集成测试阶段）</input_source>
</file_header>

# 真实设备（REAL）面板 — 集成测试报告

## 1. 集成测试摘要

- 前置门控：单元测试通过率 100.00%（≥ 80%）→ 允许进入集成测试。
- 执行时间：2026-09-05（本会话）
- 环境：Windows 11 Pro / Python 3.14.6 / pytest 9.1.1
- 命令：`python -m pytest tests/test_real_panel_api.py -v`

| 指标 | 数值 |
|------|------|
| Total | 15 |
| Pass | 15 |
| Fail | 0 |
| Skip | 0 |
| Blocked | 0 |

- 算术校验：`15 = 15 + 0 + 0 + 0`
- 通过率：`pass / (pass + fail) = 15 / 15 = 100.00%`
- 门控阈值：90%
- **门控结论：PASSED**（100.00% ≥ 90%）

## 2. 集成边界与分项结果

集成点：`src/api/devices_router.py` REAL 分支 ↔ `real_panel_service` / `real_panel_parsers` /
`AuditLogger` / `DeviceRepository` / `get_current_user`。
测试直接调用路由函数，monkeypatch `DeviceRepository` / `_decrypt_password` /
`collect_real_panel` / `configure_real_port` / `AuditLogger`，不依赖真实网络与数据库。

### 2.1 GET /real_panel（7 例）

| TC | 集成边界 | 关联 AC | 结果 |
|----|---------|---------|------|
| test_device_not_found_404 | repo → 404 | AC-RP-002-02 | PASS |
| test_non_real_400 | 非 REAL → 400「仅适用于 REAL」 | AC-RP-008-02 | PASS |
| test_no_credential_400 | 无凭据 → 400 | AC-RP-002-02 | PASS |
| test_decrypt_none_400 | 解密失败 → 400 | AC-RP-002-02 | PASS |
| test_collection_real_panel_error_502 | `collect_real_panel` 抛 `RealPanelError` → 502（含 section） | AC-RP-002-02 | PASS |
| test_collection_generic_error_502 | 通用异常 → 502 | AC-RP-002-02 | PASS |
| test_success_200 | 成功 → 200 快照 | AC-RP-002-01 | PASS |

### 2.2 写端点 REAL 分支（6 例）

| TC | 集成边界 | 关联 AC | 结果 |
|----|---------|---------|------|
| test_device_not_found_404 | 设备不存在 → 404 | AC-RP-005-04 | PASS |
| test_invalid_action_400 | action ∉ {shutdown, no-shutdown} → 400 | AC-RP-005-01 | PASS |
| test_no_credential_400 | 无凭据 → 400 | AC-RP-005-04 | PASS |
| test_success_audits_with_operator_and_no_password | 成功 → 审计（operator + detail 无明文密码） | AC-RP-006-02 | PASS |
| test_no_shutdown_audit_action | no-shutdown → `port_no_shutdown` 审计动作 | AC-RP-005-02 / AC-RP-006-02 | PASS |
| test_write_failure_502 | `configure_real_port` 异常 → 502 | AC-RP-005-04 | PASS |

### 2.3 NFUNC-003 回归（2 例）

| TC | 集成边界 | 关联 AC | 结果 |
|----|---------|---------|------|
| test_mock_device_config_returns_simulator_only_message | 非 SIMULATOR 写 → 400「仅模拟器」 | AC-RP-008-01 | PASS |
| test_ports_endpoint_real_returns_simulator_only_message | `/ports` 对 REAL 仍返回「仅模拟器」 | AC-RP-008-02 | PASS |

## 3. 写操作安全验证结论（REQ-RP-NFUNC-002 / AC-RP-006-02）

`test_success_audits_with_operator_and_no_password` 捕获 `AuditLogger.log_audit_event` 调用参数，逐项断言：

| 审计字段 | 断言值 | 结果 |
|---------|--------|------|
| event_type | `AuditEventType.CONFIG_CHANGE` | 通过 |
| alert_id | `device:1`（合成设备标识，ADR-RP-005） | 通过 |
| operator | `current_user.username`（`ops-admin`） | 通过 |
| action | `port_shutdown` / `port_no_shutdown` | 通过 |
| detail | `{device_id, device_name, port_name, action, success, message}` | 通过 |
| detail 无明文密码 | `json.dumps(detail)` 不含 `password` / `s3cr3t-pw` | 通过 |

> 写路径「不调 save / 不执行 `copy running-config startup-config`」由单元测试
> `TestConfigureRealPort.test_shutdown_success`（`save.assert_not_called()`）覆盖；本层验证
> 编排层 `_configure_real_port` 仅调用 `configure_real_port`（configure 不 save），不直连底层会话。

## 4. 失败/阻塞汇总

- 无 FAIL、无 SKIP、无 BLOCKED。

*文档版本 0.1.0 | 状态 APPROVED | 作者 sub_agent_test_engineer | invocation inv-real-panel-d-001*
