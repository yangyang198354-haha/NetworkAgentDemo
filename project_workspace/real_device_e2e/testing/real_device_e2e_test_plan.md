<file_header>
  <project_id>NetworkAgentDemo</project_id>
  <module_id>real_device_e2e</module_id>
  <doc_type>test_plan</doc_type>
  <file_name>real_device_e2e_test_plan.md</file_name>
  <version>0.2.0</version>
  <status>APPROVED</status>
  <author_agent>sub_agent_test_engineer</author_agent>
  <created_at>2026-09-05T06:10:00Z</created_at>
  <last_updated>2026-09-05T06:10:00Z</last_updated>
  <invocation_id>inv-real-e2e-d-001</invocation_id>
  <input_source>PM agent_invocation — GROUP_RE_D 测试阶段（基于 APPROVED user_stories / module_design / architecture_design + GROUP_RE_C code_review_report）</input_source>
</file_header>

# 真实设备（REAL）端到端工作流 — 测试计划

## 1. 测试策略

### 1.1 测试目标

验证 GROUP_RE_C 交付的 7 条 ADR（ADR-RE-001 ~ ADR-RE-007）在「真实设备（REAL）端到端工作流」垂直切片上正确落地，覆盖 8 个用户故事 / 16 个验收标准组，同时确保 MOCK / SIMULATOR / REAL 面板零回归。

### 1.2 测试范围（In-Scope / Out-of-Scope）

**In-Scope：**

| 层 | 内容 |
|----|------|
| 单元测试（UNIT） | `resolve_real_access`、`_resolve_real_credentials`、`get_diag_commands`、`parse_diag_output`、`resolve_fix_capability`、`get_fix_template`、`build_degraded_fix_plan`、`verify_real_fix`、`_sanitize_state_snapshot`、`enrich_device_info` |
| 集成测试（INT） | `handle_get_device_info` REAL 分支、`handle_establish_ssh` REAL 可达性、`handle_generate_fix_plan` REAL 降级、`handle_execute_fix` REAL 写白名单、`handle_verify_result` REAL 结构化验证、`handle_final_report` 降级标注、`_real_backup` 只读备份、`alerts_router.simulate_alert` REAL 回填 |
| E2E 测试（E2E） | 真实 TL-SG5428 上的「模拟告警 → 真实诊断 → 真实修复 → 真实验证 → 收敛关闭」完整闭环（PORT_DOWN / PORT_SHUTDOWN），以及 MOCK / SIMULATOR 回归 |

**Out-of-Scope：**

- `copy running-config startup-config` 持久化（OS-02，明确不做）
- 巡检（inspection）REAL 化 / 告警风暴治理（OS-05）
- SNMP / NETCONF / RESTCONF 采集（OS-04）

### 1.3 测试环境要求

| 阶段 | 环境 | 约束 |
|------|------|------|
| UNIT / INT | 本地（Windows 11，Python 3.11+） | 不碰真机；用 mock/monkeypatch 隔离 DB 与 `real_device_client` |
| E2E（dry-run） | 本地 + MOCK/SIMULATOR 告警 | 校验「触发→轮询→断言」链路；不连真机 |
| E2E（真实写） | VPS（GROUP_E 部署后） | FRP 隧道 `frp_proxy_host=127.0.0.1:6022` 可达；凭据走 env / DB Fernet |

### 1.4 门控标准（沿用项目既有）

| 阶段 | 门控 |
|------|------|
| 单元测试覆盖率 | ≥ 80%（本切片 REAL 分支纯函数） |
| 单元测试通过率 | ≥ 80% |
| 集成测试通过率 | ≥ 90% |
| E2E critical path（Must Have 故事） | 100%（PORT_DOWN / PORT_SHUTDOWN 关键路径） |

### 1.5 测试数据

- 测试设备名：`TL-SG5428-核心交换机`（REAL）
- 测试端口：`Gi1/0/2`（授权白名单唯一端口）
- 凭据：`DEVICE_TL-SG5428-核心交换机_PASSWORD` 环境变量或 DB Fernet 密文（测试断言中不出现明文）
- 真实诊断命令：`show interface status`、`show cpu-utilization`、`show memory-utilization`、`show mac address-table`（空格版）

### 1.6 溯源约束

每个测试用例必须溯源至 `real_device_e2e_user_stories.md` 中的 `AC-RE-NNN-NN`。本计划覆盖 16 个验收标准组（源文档汇总表标注「17 组」为上游计数误差，实际枚举 AC ID 为 16 个，见 §4）。

---

## 2. 测试用例清单

### 2.1 单元测试用例（TC-UNIT-*）

| TC-ID | 所属 US | 关联 AC | 描述 | 前置条件 | 动作 | 预期结果 | 测试数据 | 备注 |
|-------|--------|--------|------|---------|------|---------|---------|------|
| TC-UNIT-001 | US-RE-006 | AC-RE-006-01 | `resolve_real_access` DB 查无设备返回 None | 无 DB 记录 | 调用 `resolve_real_access("unknown")` | 返回 `None` | 空 DeviceRepository | — |
| TC-UNIT-002 | US-RE-001 | AC-RE-001-02 | `resolve_real_access` 命中设备解析 FRP 接入 | DB 有 REAL 设备（FRP 127.0.0.1:6022） | 调用 `resolve_real_access("TL-SG5428-核心交换机")` | 返回 `RealAccessContext(host=127.0.0.1, port=6022, protocol=SSH)` | mock Device + `_resolve_access` | — |
| TC-UNIT-003 | US-RE-006 | AC-RE-006-01 | `_resolve_real_credentials` env 优先 | 设 `DEVICE_*_PASSWORD` env | 调用 `_resolve_real_credentials` | 返回 `(username, env_pwd)`，优先于 DB Fernet | env 值 | 断言不含 admin123 |
| TC-UNIT-004 | US-RE-006 | AC-RE-006-01 | `_resolve_real_credentials` DB Fernet 解密 | DB credential 有 Fernet 密文，无 env | 调用 `_resolve_real_credentials` | 返回解密后的密码 | mock Fernet 密文 | — |
| TC-UNIT-005 | US-RE-006 | AC-RE-006-01 | `_resolve_real_credentials` 缺失返回 None（无 admin123 兜底） | 无 env、无 DB 凭据 | 调用 `_resolve_real_credentials` | 返回 `None`，绝不返回 `("admin","admin123")` | — | 安全红线 |
| TC-UNIT-006 | US-RE-003 | AC-RE-003-03 | `get_diag_commands` REAL 命令集 | device_type=REAL | 分别调 PORT_DOWN/PORT_SHUTDOWN/CPU_HIGH/MAC_FLAPPING | REAL 返回 TP-Link 命令集（含空格版 `show mac address-table`） | 4 类告警 | — |
| TC-UNIT-007 | US-RE-007 | AC-RE-007-02 | `get_diag_commands` MOCK/SIMULATOR 零回归 | device_type=MOCK/SIMULATOR | 调 PORT_DOWN/CPU_HIGH | 返回原 `DIAG_COMMAND_MAP` | — | — |
| TC-UNIT-008 | US-RE-002 | AC-RE-002-02 | `parse_diag_output` REAL 结构化 | 有效 `show interface status` 文本 | 调 `parse_diag_output(PORT_DOWN, REAL, text)` | 返回 `{"ports":[...]}` 结构化 | 端口表文本 | — |
| TC-UNIT-009 | US-RE-002 | AC-RE-002-02 | `parse_diag_output` 解析失败返回 error | 无表头文本 | 调 `parse_diag_output(PORT_DOWN, REAL, text)` | 返回 `{"error":...}` 而非伪造数据 | 垃圾文本 | — |
| TC-UNIT-010 | US-RE-002 | AC-RE-002-02 | `parse_diag_output` 非 REAL 返回原文 | device_type=MOCK | 调 `parse_diag_output` | 返回 `{"raw": text}` | — | — |
| TC-UNIT-011 | US-RE-003 | AC-RE-003-03 | `resolve_fix_capability` PORT=FIXABLE / CPU/MAC=DEGRADED | device_type=REAL | 分别调 4 类告警 | PORT_DOWN/PORT_SHUTDOWN=FIXABLE；CPU_HIGH/MAC_FLAPPING=DEGRADED | — | — |
| TC-UNIT-012 | US-RE-003 | AC-RE-003-03 | `resolve_fix_capability` 非 REAL 全 FIXABLE | device_type=MOCK | 调 CPU_HIGH | 返回 FIXABLE | — | 零回归 |
| TC-UNIT-013 | US-RE-003 | AC-RE-003-03 | `get_fix_template` REAL DEGRADED 返回 None | device_type=REAL | 调 CPU_HIGH | 返回 None | — | — |
| TC-UNIT-014 | US-RE-008 | AC-RE-008-02 | `build_degraded_fix_plan` 空命令 | CPU_HIGH | 调 `build_degraded_fix_plan` | `commands=[]`、`template_id=""`、description 含「修复降级」 | — | — |
| TC-UNIT-015 | US-RE-004 | AC-RE-004-01 | `verify_real_fix` PORT_DOWN down→up 通过 | before down / after up | 调 `verify_real_fix(PORT_DOWN,...)` | `verify_passed=True` | 端口表文本 | — |
| TC-UNIT-016 | US-RE-004 | AC-RE-004-01 | `verify_real_fix` PORT_SHUTDOWN up→down 通过 | before up / after down | 调 `verify_real_fix(PORT_SHUTDOWN,...)` | `verify_passed=True` | 端口表文本 | — |
| TC-UNIT-017 | US-RE-004 | AC-RE-004-01 | `verify_real_fix` CPU/MAC 不可修复 | CPU_HIGH/MAC_FLAPPING | 调 `verify_real_fix` | `verify_passed=False`，notes 含「修复降级/不可修复」 | — | — |
| TC-UNIT-018 | US-RE-004 | AC-RE-004-01 | `verify_real_fix` 解析失败不伪造通过 | 无表头文本 | 调 `verify_real_fix(PORT_DOWN,...)` | `verify_passed=False` | 垃圾文本 | — |
| TC-UNIT-019 | US-RE-003 | AC-RE-003-02 | `_sanitize_state_snapshot` 密码脱敏 | state 含 password/enable_password | 调 `_sanitize_state_snapshot` | 返回快照无 password/enable_password，其他键保留 | — | 安全红线 |

### 2.2 集成测试用例（TC-INT-*）

| TC-ID | 所属 US | 关联 AC | 描述 | 集成边界 | 预期结果 |
|-------|--------|--------|------|---------|---------|
| TC-INT-001 | US-RE-001 | AC-RE-001-01/02 | `alerts_router.simulate_alert` REAL 回填型号/地址/端口 | alerts_router ↔ DeviceRepository | REAL 设备回填 `TL-SG5428` / `Gi1/0/2` / 真实 device_ip |
| TC-INT-002 | US-RE-001 | AC-RE-001-01 | simulate 调用侧显式传参优先 | alerts_router 回填逻辑 | 显式 interface/device_ip 不被回填覆盖 |
| TC-INT-003 | US-RE-002 | AC-RE-002-01 | `handle_get_device_info` REAL 命中回填 FRP/协议/型号 + 凭据 | NodeHandlers ↔ resolve_real_access ↔ _resolve_real_credentials | device_info 含 host/port/protocol/username/password |
| TC-INT-004 | US-RE-002 | AC-RE-002-01 | `handle_get_device_info` REAL 查无设备 → FAILED | NodeHandlers ↔ resolve_real_access | 返回 `status=FAILED` + 明确错误，不落 Mock |
| TC-INT-005 | US-RE-006 | AC-RE-006-01 | `handle_get_device_info` REAL 凭据缺失 → FAILED | NodeHandlers ↔ _resolve_real_credentials | 返回 `status=FAILED` + 凭据缺失信息 |
| TC-INT-006 | US-RE-002 | AC-RE-002-01 | `handle_establish_ssh` REAL 可达性校验 | NodeHandlers ↔ establish_real_reachability | 可达 true→继续；不可达 false→FAILED |
| TC-INT-007 | US-RE-003 | AC-RE-003-03 | `handle_generate_fix_plan` REAL CPU/MAC → 降级 FixPlan | NodeHandlers ↔ resolve_fix_capability ↔ build_degraded_fix_plan | `fix_plan.commands=[]`，template_id 为空 |
| TC-INT-008 | US-RE-003 | AC-RE-003-01 | `handle_generate_fix_plan` REAL PORT 渲染 2 命令（无 description） | NodeHandlers ↔ TemplateEngine ↔ tpl_port_enable | commands 长度 2，含 `interface`+`no shutdown`，无 `description` |
| TC-INT-009 | US-RE-005 | AC-RE-005-01 | `handle_execute_fix` REAL 写白名单拦截越权端口 | NodeHandlers ↔ REAL_WRITE_PORT_WHITELIST | 越权端口 → FAILED + 审计，不下发命令 |
| TC-INT-010 | US-RE-005 | AC-RE-005-02 | `handle_execute_fix` 白名单内端口正常下发 | NodeHandlers ↔ REAL_WRITE_PORT_WHITELIST | `Gi1/0/2` 放行，执行命令 |
| TC-INT-011 | US-RE-004 | AC-RE-004-01 | `handle_verify_result` REAL 走结构化验证 | NodeHandlers ↔ verify_real_fix | 返回结构化 VerifyResult（非关键词匹配） |
| TC-INT-012 | US-RE-008 | AC-RE-008-02 | `handle_final_report` 降级标注 | NodeHandlers ↔ degraded_fix 判定 | 降级报告前置「修复降级 / 不可修复」，状态仍 CLOSED |
| TC-INT-013 | US-RE-003 | AC-RE-003-02 | `_real_backup` 只读备份不 save | NodeHandlers ↔ _open_*_session | 返回只读 running-config，不调用 save() |
| TC-INT-014 | US-RE-007 | AC-RE-007-02 | MOCK/SIMULATOR 路径零回归 | NodeHandlers 原路径 | MOCK/SIMULATOR 分支逐字不变（回归套件） |

### 2.3 E2E 测试用例（TC-E2E-*）

| TC-ID | 所属 US | 关联 AC | 描述 | 关键路径 | 预期结果 |
|-------|--------|--------|------|---------|---------|
| TC-E2E-001 | US-RE-001/002/004 | AC-RE-001-01/02、002-01、004-01/02 | REAL PORT_DOWN 完整闭环 | Must Have | 告警→真实诊断→真实 `no shutdown`→verify up→CLOSED |
| TC-E2E-002 | US-RE-003/005 | AC-RE-003-01/02、005-01/02 | REAL PORT_SHUTDOWN 隔离闭环（需更高审批） | Must Have | 告警→诊断→shutdown（审批后）→verify down→CLOSED |
| TC-E2E-003 | US-RE-008 | AC-RE-008-02 | REAL CPU_HIGH 降级闭环 | Must Have | 真实诊断 + 告警闭环，不下发写命令，报告标注降级 |
| TC-E2E-004 | US-RE-008 | AC-RE-008-02 | REAL MAC_FLAPPING 降级闭环 | Must Have | 真实诊断 + 告警闭环，不下发写命令，报告标注降级 |
| TC-E2E-005 | US-RE-007 | AC-RE-007-02 | MOCK/SIMULATOR E2E 零回归 | Must Have | 现有 MOCK/SIMULATOR 场景与升级前一致 |

---

## 3. 不可测试项（[NOT_TESTABLE]）

| AC-ID | 原因 |
|-------|------|
| AC-RE-008-01（核实等价命令是否存在） | 属架构阶段（GROUP_B）的事实核查项，已由只读探测 RESOLVED（ADR-RE-004 定稿 CPU/MAC=DEGRADED）；非运行时行为，不能作为运行时测试。其结论通过 AC-RE-008-02 的运行时行为（resolve_fix_capability / build_degraded_fix_plan）间接验证。 |

---

## 4. 需求覆盖追溯矩阵

| AC 组 | 覆盖 TC | 覆盖级别 |
|-------|--------|---------|
| AC-RE-001-01 | TC-INT-001, TC-INT-002, TC-E2E-001 | INT / E2E |
| AC-RE-001-02 | TC-UNIT-002, TC-INT-001, TC-E2E-001 | UNIT / INT / E2E |
| AC-RE-002-01 | TC-INT-003, TC-INT-004, TC-INT-006, TC-E2E-001 | INT / E2E |
| AC-RE-002-02 | TC-UNIT-008, TC-UNIT-009, TC-UNIT-010 | UNIT |
| AC-RE-003-01 | TC-INT-008, TC-E2E-001/002 | INT / E2E |
| AC-RE-003-02 | TC-UNIT-019, TC-INT-009, TC-INT-013 | UNIT / INT |
| AC-RE-003-03 | TC-UNIT-006, TC-UNIT-011, TC-UNIT-012, TC-UNIT-013, TC-INT-007 | UNIT / INT |
| AC-RE-004-01 | TC-UNIT-015, TC-UNIT-016, TC-UNIT-017, TC-UNIT-018, TC-INT-011 | UNIT / INT |
| AC-RE-004-02 | TC-E2E-001/002 | E2E |
| AC-RE-005-01 | TC-INT-009, TC-INT-010, TC-E2E-001/002 | INT / E2E |
| AC-RE-005-02 | TC-INT-010, TC-E2E-002 | INT / E2E |
| AC-RE-006-01 | TC-UNIT-001, TC-UNIT-003, TC-UNIT-004, TC-UNIT-005, TC-INT-005 | UNIT / INT |
| AC-RE-007-01 | （复用 real_session_gate，验证见 INT-006/013 + 现有 test_real_session_gate.py） | INT |
| AC-RE-007-02 | TC-UNIT-007, TC-INT-014, TC-E2E-005 | UNIT / INT / E2E |
| AC-RE-008-01 | [NOT_TESTABLE]（架构事实核查，见 §3） | — |
| AC-RE-008-02 | TC-UNIT-014, TC-INT-007, TC-INT-012, TC-E2E-003/004 | UNIT / INT / E2E |

> 说明：源文档 `real_device_e2e_user_stories.md` 汇总表标注「验收标准组数 17」，但实际枚举 AC ID 为 16 个（US-RE-001~008 共 2+2+3+2+2+1+2+2=16），已按实际 16 组覆盖。该计数差异建议由 requirement_analyst 后续勘误，不阻塞本测试阶段。

---

## 5. 测试执行顺序与门控

```
PHASE_D1 测试计划（本文档）
    ↓
PHASE_D2 单元测试（tests/test_real_device_e2e_unit.py）
    → 通过率 ≥ 80% 才进入集成
    ↓
PHASE_D2 集成测试（tests/test_real_device_e2e_integration.py）
    + 全量回归（487 passed / 1 xfailed 基线）
    → 通过率 ≥ 90% 才进入 E2E
    ↓
PHASE_D3 E2E 脚本 authoring + dry-run（e2e_real_write_test.py）
    → 脚本就绪；真实写执行待 GROUP_E 部署后由 PM 触发
```

*文档版本 0.2.0 | 状态 APPROVED | 生成时间 2026-09-05 | 作者 sub_agent_test_engineer*

<audit_log>
  <log time="2026-09-05T06:10:00Z" state="WRITE_FILES" action="file_write" result="SUCCESS" trace_id="inv-real-e2e-d-001" file_path="project_workspace/real_device_e2e/testing/real_device_e2e_test_plan.md"/>
</audit_log>
</file_header>
