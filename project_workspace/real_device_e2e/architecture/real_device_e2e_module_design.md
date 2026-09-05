<file_header>
  <project_id>NetworkAgentDemo</project_id>
  <module_id>real_device_e2e</module_id>
  <doc_type>module_design</doc_type>
  <file_name>real_device_e2e_module_design.md</file_name>
  <version>0.2.0</version>
  <status>APPROVED</status>
  <author_agent>sub_agent_system_architect</author_agent>
  <created_at>2026-09-05T04:00:00Z</created_at>
  <last_updated>2026-09-05T04:00:00Z</last_updated>
  <invocation_id>inv-real-e2e-b-001</invocation_id>
  <input_source>PM agent_invocation — GROUP_B 模块设计（基于 APPROVED 需求 inv-real-e2e-a-002）</input_source>
</file_header>

# 真实设备（REAL）端到端工作流 — 模块设计

## 模块总览

| MOD-ID | 模块名 | 层级 | 职责 | 依赖于 |
|--------|--------|------|------|--------|
| MOD-RE-001 | REAL 接入上下文解析 | 工作流层 | device_name → Device（DB），复用 `_resolve_access` 解析 FRP host/port/protocol，回填 device_info + 凭据安全校验 | DeviceRepository, real_device_client._resolve_access, ConfigManager |
| MOD-RE-002 | REAL 工具运行时选择 | 工作流层 | `_get_*_tool_for_device`/`_execute_single_command` 补 REAL 分支，establish_ssh 真实可达性校验 | create_switch_diag_tool/create_switch_config_tool 工厂 |
| MOD-RE-003 | REAL 诊断命令映射与解析 | 工作流层 | device_type 感知命令映射（补 PORT_SHUTDOWN、CPU/MAC 只读命令）+ 复用 real_panel_parsers 结构化解析 | real_panel_parsers |
| MOD-RE-004 | REAL 修复能力裁决与模板 | 工作流层+模板层 | 四类告警修复能力裁决（FIXABLE/DEGRADED），PORT 模板去 description，CPU/MAC 双分支降级 | TemplateEngine |
| MOD-RE-005 | REAL 验证结构化比较 | 工作流层 | 基于 parse_interface_status/parse_cpu_utilization 的结构化修复前后比较 | real_panel_parsers |
| MOD-RE-006 | REAL 会话接入（复用） | 基础设施层（复用） | 复用 real_session_gate 串行化 + TpLink*Tool finally 关闭 + 不 save，非新增模块 | real_session_gate, real_device_client |

---

## 模块详情

---

### MOD-RE-001: REAL 接入上下文解析

- **职责**: 在 `handle_get_device_info`（node_handlers L430-451）对 `device_type == "REAL"` 走新分支：按 `device_name` 经 `SessionLocal` + `DeviceRepository` 取 Device 对象，调用 `real_device_client._resolve_access(device)` 得到 `(host, port, protocol)`，回填 `device_info`；并校验 REAL 凭据仅来自 `DEVICE_<NAME>_PASSWORD` 环境变量或 DB Fernet 解密，缺失即失败（禁用 `admin123` 兜底）。MOCK/SIMULATOR 走原路径逐字不变。
- **覆盖需求**: REQ-RE-FUNC-001（真实型号/地址回填）、REQ-RE-FUNC-002（FRP 接入）、REQ-RE-NFUNC-001（凭据安全）、REQ-RE-NFUNC-004（零回归）。
- **公开接口契约**:

  - **IFC-RE-001-01**: `resolve_real_access(device_name: str) -> RealAccessContext | None`
    - 入参: `device_name: str`（来自 `device_info.device_name`）
    - 出参: `RealAccessContext` = `{host: str, port: int, protocol: str, device_model: str, frp_proxy_host: str|None, frp_proxy_port: int|None}`；查无 Device 返回 `None`
    - 行为: `SessionLocal()` → `DeviceRepository.list_devices()` 按 `device_name` 匹配 → `_resolve_access(device)` 得 `(host, port, protocol)` → 组装 `RealAccessContext`；`finally db.close()`
    - 错误码: 查无设备返回 `None`（上层转为 WORKFLOW FAILED，不落 Mock）

  - **IFC-RE-001-02**: `enrich_device_info(device_info: dict, access: RealAccessContext) -> dict`
    - 入参: `device_info: dict`（原 state 字段）、`access: RealAccessContext`
    - 出参: 回填后的 `dict`（新增/覆盖 `device_ip=host`、`port=port`、`protocol=protocol`、`device_model=device_model`、`frp_proxy_host`、`frp_proxy_port`）
    - 行为: 仅追加键，不改 `src/models/alert.DeviceInfo` pydantic 模型（避免破坏序列化契约）

  - **IFC-RE-001-03**: `_extract_auth(device_info: dict) -> DeviceAuth`（扩展）
    - 入参: `device_info: dict`（已由 IFC-RE-001-02 回填）
    - 出参: `DeviceAuth(username, password, enable_password, port=device_info.get("port", 22), protocol=device_info.get("protocol", "SSH"))`
    - 行为: 相比现状（node_handlers L1086-1093）新增 `protocol` 透传；`password` 缺失不得回退 `admin123`（由 IFC-RE-001-01 前置校验保证）

- **依赖模块**: `DeviceRepository`（`src.database.repositories.device_repository`）、`real_device_client._resolve_access`、`ConfigManager`/`EncryptionService`（凭据读取）。
- **外部依赖**: 无新增第三方依赖（仅 stdlib + 既有 DB/加密模块）。

---

### MOD-RE-002: REAL 工具运行时选择

- **职责**: 扩展 `_get_diag_tool_for_device`/`_get_config_tool_for_device`/`_get_backup_tool_for_device`（node_handlers L169-191）与 `_execute_single_command`（L1140-1177）增加 `device_type == "REAL"` 分支，返回真实 TpLink 工具；`handle_establish_ssh`（L455-471）对 REAL 执行真实可达性校验（TCP + 协议握手）而非 Mock 日志。
- **覆盖需求**: REQ-RE-FUNC-003（REAL 不落 Mock）、REQ-RE-FUNC-007（闭环可达）、REQ-RE-NFUNC-004（MOCK 默认不变）。
- **公开接口契约**:

  - **IFC-RE-002-01**: `get_diag_tool_for_device(state: NetworkAgentState) -> AbstractSwitchDiagTool`
    - 入参: `state`（含 `device_info.device_type`）
    - 出参: `MOCK` → `self.switch_diag_tool`（注入的 Mock）；`SIMULATOR` → `SimulatorDiagTool()`；`REAL` → `create_switch_diag_tool(device_type="REAL")`（即 `TpLinkSwitchDiagTool()`）
    - 行为: 与现有 SIMULATOR 分支同构；`main.py:79-80` 的 Mock 注入保持为 MOCK/兜底

  - **IFC-RE-002-02**: `get_config_tool_for_device(state: NetworkAgentState) -> AbstractSwitchConfigTool`
    - 入参/出参/行为: 同 IFC-RE-002-01，`REAL` → `create_switch_config_tool(device_type="REAL")`；`_execute_single_command` 的 REAL 分支复用同一工厂

  - **IFC-RE-002-03**: `establish_real_reachability(access: RealAccessContext, username: str, password: str) -> bool`
    - 入参: `access: RealAccessContext`（IFC-RE-001-01）、`username`、`password`（已解密）
    - 出参: `bool`（可达 true / 不可达 false）
    - 行为: `_tcp_check(host, port)` 快速 TCP 探测 + 协议握手校验；失败返回 false，工作流在 establish_ssh 标记失败

- **依赖模块**: `create_switch_diag_tool`/`create_switch_config_tool` 工厂、`real_device_client`（`_tcp_check`/`check_connectivity`）。
- **外部依赖**: 无新增第三方依赖。

---

### MOD-RE-003: REAL 诊断命令映射与解析

- **职责**: 提供 device_type 感知的命令解析 `get_diag_commands(alert_type, device_type)`（REAL 用 TP-Link 命令集，MOCK/SIMULATOR 沿用原 `DIAG_COMMAND_MAP`）；对 REAL 诊断输出调用 `real_panel_parsers` 转结构化，解析失败返回明确错误而非错误数据。
- **覆盖需求**: REQ-RE-FUNC-004（TP-Link 命令 + 结构化解析）、REQ-RE-NFUNC-004（原 dict 零改动）。
- **公开接口契约**:

  - **IFC-RE-003-01**: `get_diag_commands(alert_type: str, device_type: str) -> list[str]`
    - 入参: `alert_type`（PORT_DOWN/PORT_SHUTDOWN/CPU_HIGH/MAC_FLAPPING）、`device_type`（MOCK/SIMULATOR/REAL）
    - 出参: `list[str]`
    - 行为: `device_type == "REAL"` 时返回 TP-Link 命令集：
      - `PORT_DOWN` → `["show interface status"]`
      - `PORT_SHUTDOWN` → `["show interface status"]`
      - `CPU_HIGH` → `["show cpu-utilization", "show memory-utilization"]`
      - `MAC_FLAPPING` → `["show interface status"]`
      - 非 REAL → 返回原 `DIAG_COMMAND_MAP`（缺 PORT_SHUTDOWN 键的兜底保留，但 REAL 补齐）
    - 错误码: 未知 alert_type 返回 `["show interface status"]` 兜底

  - **IFC-RE-003-02**: `parse_diag_output(alert_type: str, device_type: str, text: str) -> dict`
    - 入参: 清洗后诊断文本（`_strip_echo_and_prompts` 输出）、`alert_type`、`device_type`
    - 出参: `dict`（如端口列表 `list[PortStatus]`、`CpuUsage`、`MemoryUsage` 的 dataclass 转 dict）
    - 行为: REAL → `parse_interface_status`/`parse_cpu_utilization`/`parse_memory_utilization`；解析抛 `RealPanelError` 时上层转 `DiagResult(success=False, error=...)` 明确错误（不返回伪造数据）
    - 错误码: `RealPanelError(section, reason, raw_excerpt)`

- **依赖模块**: `real_panel_parsers`（MOD-RP-003，复用）、`real_device_client._strip_echo_and_prompts`/`_looks_like_error`。
- **外部依赖**: 无（仅 stdlib `re`，复用既有解析器）。

---

### MOD-RE-004: REAL 修复能力裁决与模板

- **职责**: 提供 `resolve_fix_capability(alert_type, device_type)` 裁决四类告警在 REAL 下「可修复 FIXABLE / 降级 DEGRADED」；PORT 类模板去 `description` 行；CPU_HIGH/MAC_FLAPPING 默认 DEGRADED，等价命令核实后经注册表升为 FIXABLE（补 TP-Link 模板）。`shutdown` 属隔离场景需更高授权（assess_risk → human_approval），不作默认修复动作。
- **覆盖需求**: REQ-RE-FUNC-005（四类 TP-Link 模板）、REQ-RE-FUNC-008（双分支降级）、REQ-RE-NFUNC-002（shutdown 更高授权、description 不纳入、不 save）。
- **公开接口契约**:

  - **IFC-RE-004-01**: `resolve_fix_capability(alert_type: str, device_type: str) -> FixCapability`
    - 入参: `alert_type`、`device_type`
    - 出参: `FixCapability`（枚举：`FIXABLE` | `DEGRADED`）
    - 行为: `device_type != "REAL"` → 全部 `FIXABLE`（原 MOCK/SIMULATOR 行为不变）；`REAL` 下 PORT_DOWN/PORT_SHUTDOWN → `FIXABLE`，CPU_HIGH/MAC_FLAPPING → 默认 `DEGRADED`（注册表可由「只读探测核实」结果升为 `FIXABLE`）
    - 错误码: 未知 alert_type → 按 `FIXABLE`（沿用 `_get_default_template` 兜底 `TPL-PORT-ENABLE`）

  - **IFC-RE-004-02**: `get_fix_template(alert_type: str, device_type: str) -> str | None`
    - 入参: `alert_type`、`device_type`
    - 出参: `template_id: str`（FIXABLE）或 `None`（DEGRADED）
    - 行为: `REAL` + `FIXABLE`：PORT_DOWN → `TPL-PORT-ENABLE`、PORT_SHUTDOWN → `TPL-PORT-DISABLE`（模板已去 description）；CPU/MAC 若核实后 FIXABLE → 对应 TP-Link 模板 ID；`DEGRADED` → `None`

  - **IFC-RE-004-03**: `build_degraded_fix_plan(alert_type: str) -> FixPlan`
    - 入参: `alert_type`
    - 出参: `FixPlan(commands=[], template_id=None, description="修复降级：该告警类型在 TL-SG5428 无已核实 CLI 修复能力", risk_hints=[...])`
    - 行为: `generate_fix_plan` 对 DEGRADED 告警产出空命令 FixPlan；`execute_fix` 据此**不下发任何命令**；`finish_report` 标注「修复降级/不可修复」

- **依赖模块**: `TemplateEngine`（`get_template`/`render`）、`resources/templates/tpl_*.yaml`。
- **外部依赖**: 无新增第三方依赖。

---

### MOD-RE-005: REAL 验证结构化比较

- **职责**: 提供 `verify_real_fix(alert_type, before_text, after_text, target_port)`，基于 `real_panel_parsers` 的结构化结果判定修复前后，替代 `handle_verify_result`（L962-970）对 REAL 的关键词匹配；MOCK/SIMULATOR 保留原关键词逻辑。
- **覆盖需求**: REQ-RE-FUNC-006（结构化验证）、REQ-RE-FUNC-007（收敛关闭）、AC-RE-004-01/02。
- **公开接口契约**:

  - **IFC-RE-005-01**: `verify_real_fix(alert_type: str, before_text: str, after_text: str, target_port: str) -> VerifyResult`
    - 入参: `alert_type`、`before_text`（修复前诊断文本）、`after_text`（修复后诊断文本）、`target_port`（`device_info.interface_name`）
    - 出参: `VerifyResult(verify_passed: bool, before_state: str, after_state: str, comparison_notes: str)`
    - 行为:
      - `PORT_DOWN`: `parse_interface_status` 定位 `target_port`，before Status ∈ {down, notconnect} 且 after Status == up → 通过
      - `PORT_SHUTDOWN`: before Status == up 且 after Status == down → 通过（隔离成功）
      - `CPU_HIGH`: `parse_cpu_utilization` 比较 before/after `cpu_5s`，after 低于阈值（Q-RE-04）→ 通过；DEGRADED 时返回「不可修复」而非通过
      - `MAC_FLAPPING`: DEGRADED 时返回「不可修复」；若有只读命令则按对应解析器比较（[待核实]）
    - 错误码: 解析失败 → `verify_passed=False` + `comparison_notes` 记录解析错误（不伪造通过）

- **依赖模块**: `real_panel_parsers`（`parse_interface_status`/`parse_cpu_utilization`）。
- **外部依赖**: 无。

---

### MOD-RE-006: REAL 会话接入（复用，非新增）

- **职责**: 复用 `real_session_gate`（`session_guard_by_access`）串行化 REAL 诊断/配置会话，复用 TpLink*Tool 既有 finally 关闭，复用 `real_device_client` 会话链；**不调用 `save()`**、**不持久化**。本模块无新增代码，仅声明复用与约束。
- **覆盖需求**: REQ-RE-NFUNC-002（不 save）、REQ-RE-NFUNC-003（串行化 + finally + 超时）、REQ-RE-NFUNC-004（复用现有能力）。
- **公开接口契约**（复用现有，非新增）:

  - **IFC-RE-006-01**（复用 IFC-RP-004-03）: `session_guard_by_access(host: str, port: int, protocol: str) -> ContextManager`
    - 调用约定: TpLink*Tool（switch_diag_tool L267、switch_config_tool L166）已在 `_run` 内包裹；ADR-RE-001 回填后 `host=frp_proxy_host`、`port=frp_proxy_port`、`protocol=connection_protocol`，其 key 与面板 `session_key` 对齐
  - **IFC-RE-006-02**（复用）: `_SshSession/_TelnetSession.open()/show()/configure()/close()` 与 `_open_ssh_session/_open_telnet_session`
    - 约束: 会话 `finally` 关闭、设超时；单次诊断同会话批量下发多条 show（NFUNC-003）；写操作仅 `configure([...])`，**不调用 `save()`**（`real_device_client.py` L1226-1238 不暴露于工作流路径）

- **依赖模块**: `real_session_gate`、`real_device_client`。
- **外部依赖**: 无新增第三方依赖。

---

## 依赖关系图（文本格式，无循环依赖，已验证）

```
MOD-RE-001 (REAL 接入上下文解析)
   └─→ DeviceRepository / real_device_client._resolve_access / ConfigManager
MOD-RE-002 (REAL 工具运行时选择)
   ├─→ create_switch_diag_tool / create_switch_config_tool 工厂
   └─→ MOD-RE-001 (establish_real_reachability 消费 RealAccessContext)
MOD-RE-003 (REAL 诊断命令映射与解析)
   └─→ real_panel_parsers
MOD-RE-004 (REAL 修复能力裁决与模板)
   └─→ TemplateEngine + resources/templates/tpl_*.yaml
MOD-RE-005 (REAL 验证结构化比较)
   └─→ real_panel_parsers
MOD-RE-006 (REAL 会话接入，复用)
   └─→ real_session_gate + real_device_client
```

- 依赖方向单向：接入解析（MOD-RE-001）为入口，工具选择/命令/修复/验证（MOD-RE-002~005）并行依赖基础设施（MOD-RE-006 + real_panel_parsers + 工厂），无回边，**无循环依赖**。

---

## 需求覆盖追溯矩阵（REQ-RE-FUNC-001~008 / NFUNC-001~004 100% 覆盖）

| 需求 ID | 覆盖模块 / ADR |
|---------|----------------|
| REQ-RE-FUNC-001 | MOD-RE-001（真实型号/地址回填）, ADR-RE-007 |
| REQ-RE-FUNC-002 | MOD-RE-001（FRP 接入）, MOD-RE-006（会话）, ADR-RE-001 |
| REQ-RE-FUNC-003 | MOD-RE-002（工具选择）, ADR-RE-002 |
| REQ-RE-FUNC-004 | MOD-RE-003（命令映射+解析）, ADR-RE-003 |
| REQ-RE-FUNC-005 | MOD-RE-004（四类模板 + 去 description）, ADR-RE-004 |
| REQ-RE-FUNC-006 | MOD-RE-005（结构化验证）, ADR-RE-005 |
| REQ-RE-FUNC-007 | MOD-RE-002（establish_ssh 可达）+ MOD-RE-005（收敛关闭）, ADR-RE-002/005 |
| REQ-RE-FUNC-008 | MOD-RE-004（双分支降级）, ADR-RE-004 |
| REQ-RE-NFUNC-001 | MOD-RE-001（凭据安全校验）, ADR-RE-006 |
| REQ-RE-NFUNC-002 | MOD-RE-004（shutdown 授权/description 不纳入/不 save）, ADR-RE-006 |
| REQ-RE-NFUNC-003 | MOD-RE-006（串行化+finally+超时）, ADR-RE-006 |
| REQ-RE-NFUNC-004 | ADR-RE-002/003（零回归）+ 变更范围「零变更清单」 |

---

## 变更范围清单

### 后端（修改）
| 文件 | 变更 | 关联模块 |
|------|------|----------|
| `src/orchestration/node_handlers.py` | `handle_get_device_info` REAL 分支（FRP/协议/型号回填 + 凭据安全校验）；`_extract_auth` 透传 protocol；`_get_*_tool_for_device`/`_execute_single_command` 补 REAL 分支；新增 `get_diag_commands`/`resolve_fix_capability`/`get_fix_template`/`build_degraded_fix_plan`/`verify_real_fix`；`handle_establish_ssh`/`handle_collect_diag`/`handle_execute_fix`/`handle_verify_result` 接 REAL 分支 | MOD-RE-001~005 |
| `src/api/alerts_router.py` | `simulate_alert` 按 device_name 回填真实 device_model/device_ip/interface（调用侧传参优先） | ADR-RE-007 |
| `resources/templates/tpl_port_enable.yaml` | 删除 `description {{ desc }}` 行 | MOD-RE-004 |
| `resources/templates/tpl_port_disable.yaml` | 删除 `description {{ desc }}` 行 | MOD-RE-004 |

### 后端（可选，视只读探测核实结果）
| 文件 | 变更 | 关联模块 |
|------|------|----------|
| `resources/templates/tpl_cpu_storm_control.yaml`（新增） | 仅当核实 TL-SG5428 存在 storm-control 等价命令后新增 TP-Link 版 CPU 模板 | MOD-RE-004 分支 1 |
| `resources/templates/tpl_mac_port_security_tp.yaml`（新增） | 仅当核实等价命令后新增 TP-Link 版 MAC 模板 | MOD-RE-004 分支 1 |

### 零变更（NFUNC-004 约束清单）
| 文件/能力 | 说明 |
|-----------|------|
| `src/main.py` L79-80（`use_mock=True` 默认注入 Mock） | 不改，MOCK 默认与兜底保持（REAL 由运行时分支覆盖） |
| `src/tools/switch_diag_tool.py` / `switch_config_tool.py` 工厂与 `_run` | 不改（工厂 REAL 分支已存在并复用；`_run` 继续消费 device_ip + auth.port/protocol） |
| `src/orchestration/node_handlers.py` `DIAG_COMMAND_MAP`（L48-61） | 不改原 dict（MOCK/SIMULATOR 命令映射零回归）；REAL 命令集由 `get_diag_commands` 另设 |
| `handle_verify_result` L962-970 关键词逻辑 | MOCK/SIMULATOR 路径逐字不变；仅 REAL 走结构化验证 |
| `src/tools/real_device_client.py`、`src/tools/real_panel_parsers.py`、`src/tools/real_session_gate.py` | 复用，零改动 |
| `src/models/alert.py`（`DeviceInfo`/`DeviceAuth`） | `DeviceInfo` 不加 frp 字段（以 dict 附加键承载）；`DeviceAuth` 已含 protocol（L27） |
| SIMULATOR 分支（`_get_*_tool_for_device` SIMULATOR、`_resolve_simulator_connection`） | 逐字不变 |

### 依赖约束
- **零新增 Python/Node 依赖**：全部复用 `real_device_client`、`real_panel_parsers`、`real_session_gate`、FastAPI、`AuditLogger`、stdlib（`threading`/`re`）。
- **不改 `src/` 修测试导入**（D-001/D-002）：本设计仅在既有文件内加分支/函数，不新增会影响 `tests/conftest.py` 的导入结构。

---

*文档版本 0.2.0 | 状态 APPROVED | 生成时间 2026-09-05 | 作者 sub_agent_system_architect*

<audit_log>
  <log time="2026-09-05T04:00:00Z" state="WRITE_FILES" action="file_write" result="SUCCESS" trace_id="inv-real-e2e-b-001" file_path="project_workspace/real_device_e2e/architecture/real_device_e2e_module_design.md"/>
</audit_log>
