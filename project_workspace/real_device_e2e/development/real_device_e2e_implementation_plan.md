<file_header>
  <project_id>NetworkAgentDemo</project_id>
  <module_id>real_device_e2e</module_id>
  <doc_type>implementation_plan</doc_type>
  <file_name>real_device_e2e_implementation_plan.md</file_name>
  <version>0.2.0</version>
  <status>DRAFT</status>
  <author_agent>sub_agent_software_developer</author_agent>
  <created_at>2026-09-05T05:30:00Z</created_at>
  <last_updated>2026-09-05T05:30:00Z</last_updated>
  <invocation_id>inv-real-e2e-c-001</invocation_id>
  <input_source>PM agent_invocation — GROUP_RE_C 编码实现（基于 APPROVED architecture inv-real-e2e-b-001 / module_design inv-real-e2e-c-000）</input_source>
</file_header>

# 真实设备（REAL）端到端工作流 — 实现计划

> 输入锚定：`real_device_e2e/architecture/real_device_e2e_module_design.md`（APPROVED）与
> `real_device_e2e/architecture/real_device_e2e_architecture_design.md`（APPROVED）。
> 本实现严格遵循 7 条 ADR（ADR-RE-001 ~ ADR-RE-007）与零回归硬约束。

## 实现概览

- **总模块数**：7（MOD-RE-001 ~ MOD-RE-006 + ADR-RE-007 告警回填）
- **总文件数**：4 个实际代码/资源文件改动（另产出 2 份开发文档）
  - `src/orchestration/node_handlers.py`（主改动：REAL 分支 + 8 个新模块级函数 + 2 个新方法 + 1 个脱敏方法）
  - `src/api/alerts_router.py`（ADR-RE-007：simulate 回填）
  - `resources/templates/tpl_port_enable.yaml`（ADR-RE-004：删 `description` 行 + 去 `desc` schema）
  - `resources/templates/tpl_port_disable.yaml`（同上）
- **实现顺序**：按模块依赖图拓扑排序——先落地资源模板（叶子），再落地编排层 REAL 分支（依赖工具/DB/模板），最后落地告警入口回填（依赖 DB 查询）。
- **零回归保障**：MOCK / SIMULATOR 路径全部保留原逻辑逐字不动；`src/main.py` L79-80 MOCK 注入未改；`switch_diag_tool.py` / `switch_config_tool.py` / `backup_tool.py` / `real_device_client.py` / `real_panel_parsers.py` / `real_session_gate.py` / `src/models/alert.py` 均零改动（仅复用）。

## 模块实现计划（按拓扑顺序）

| 序号 | MOD-ID | 模块名 | 文件路径 | 依赖前置模块 | 复杂度 | 状态 |
|------|--------|--------|---------|------------|--------|------|
| 1 | ADR-RE-004-资源 | 修复模板去 description | resources/templates/tpl_port_enable.yaml, tpl_port_disable.yaml | —（资源叶子） | L | DONE |
| 2 | MOD-RE-001 | REAL 接入上下文解析 | src/orchestration/node_handlers.py | DeviceRepository, real_device_client._resolve_access | H | DONE |
| 3 | MOD-RE-002 | REAL 工具选择 + 可达性 | src/orchestration/node_handlers.py | MOD-RE-001 | M | DONE |
| 4 | MOD-RE-003 | REAL 诊断命令映射 + 解析 | src/orchestration/node_handlers.py | MOD-RE-002 | M | DONE |
| 5 | MOD-RE-004 | 修复能力裁决 + 降级 | src/orchestration/node_handlers.py | MOD-RE-003, ADR-RE-004-资源 | H | DONE |
| 6 | MOD-RE-005 | REAL 结构化验证 | src/orchestration/node_handlers.py | MOD-RE-003 | M | DONE |
| 7 | MOD-RE-006 | 安全（凭据/写白名单/审计脱敏/只读备份） | src/orchestration/node_handlers.py | MOD-RE-004, MOD-RE-005 | H | DONE |
| 8 | ADR-RE-007 | simulate 告警真实性回填 | src/api/alerts_router.py | DeviceRepository（MOD-RE-001 同源） | M | DONE |

### 各模块实现要点

#### 1. ADR-RE-004-资源 — 修复模板去 description
- `tpl_port_enable.yaml` / `tpl_port_disable.yaml`：`params_schema` 删除 `desc: string`；模板体删除 `description {{ desc }}` 行。
- 效果：PORT_DOWN/PORT_SHUTDOWN 渲染命令由 3 条降为 2 条（`interface <port>` + `no shutdown`/`shutdown`），`configure`/`exit` 由 `TpLinkSwitchConfigTool._run` 内的 `sess.configure()` 自动包裹，不调 `save()`。

#### 2. MOD-RE-001 — REAL 接入上下文解析
- 新增模块级：`RealAccessContext` dataclass、`resolve_real_access(device_name)`、`enrich_device_info(device_info, access)`、`_decrypt_fernet(token)`、`_resolve_real_credentials(device_name)`。
- `handle_get_device_info` 对 `device_type == "REAL"` 走新分支：DB 查 Device → `_resolve_access(device)` → 回填 `device_ip/port/protocol/device_model/frp_proxy_host/frp_proxy_port`；凭据仅来自 `DEVICE_<NAME>_PASSWORD` 环境变量或 DB Fernet 解密，缺失返回 `status=FAILED`（禁用 `admin123` 兜底）。
- MOCK/SIMULATOR 原路径逐字保留。

#### 3. MOD-RE-002 — REAL 工具选择 + 可达性
- `_get_diag_tool_for_device` / `_get_config_tool_for_device` / `_execute_single_command` 增加 `REAL` 分支返回 `create_*_tool(device_type="REAL")`。
- `handle_establish_ssh` REAL 分支：由回填后的 `RealAccessContext` 调 `establish_real_reachability`（`_tcp_check` + `_open_ssh_session`/`_open_telnet_session` 协议握手 + `session_guard_by_access`）；并增加上游 `status=FAILED` 短路保护。
- `_get_backup_tool_for_device` 保持原样（REAL 备份改在工作流层 `_real_backup` 处理，见 MOD-RE-006）。

#### 4. MOD-RE-003 — REAL 诊断命令映射 + 解析
- 新增 `REAL_DIAG_COMMAND_MAP`（空格版 `show mac address-table`）与 `get_diag_commands(alert_type, device_type)`；`parse_diag_output` 对 REAL 走 `real_panel_parsers`，非 REAL 返回 `{"raw": text}`。
- `handle_collect_diag` 使用 `get_diag_commands`；REAL 输出经 `_strip_echo_and_prompts` 清洗 + 主命令结构化解析校验；MOCK/SIMULATOR 的 `show interface {iface}` 动态替换被 `device_type != "REAL"` 保护。

#### 5. MOD-RE-004 — 修复能力裁决 + 降级
- 新增 `FixCapability` 枚举、`REAL_FIX_CAPABILITY`、`REAL_FIX_TEMPLATE_MAP`、`resolve_fix_capability`、`get_fix_template`、`build_degraded_fix_plan`。
- `handle_generate_fix_plan` REAL 分支：`get_fix_template` 返回 `None`（CPU_HIGH/MAC_FLAPPING DEGRADED）→ `build_degraded_fix_plan`（`commands=[]`）早退；否则正常渲染。REAL 端口写操作 `iface_name` 覆盖为告警真实端口（默认 `Gi1/0/2`）。
- `handle_final_report` 检测降级（空命令 + 空 template_id 或描述含「修复降级」）并前置 `## 修复降级 / 不可修复`，状态仍 CLOSED（告警闭环）。
- 注：`_get_default_template` 本身未改，但 REAL 路径在模板选择前即被能力裁决拦截，故 REAL CPU/MAC 不会再落到 Cisco 模板（ADR-RE-004 意图落地）。

#### 6. MOD-RE-005 — REAL 结构化验证
- 新增 `verify_real_fix(alert_type, before_text, after_text, target_port)`，用 `parse_interface_status` 的 Status 列（`up/down/notconnect`）判定。
- `handle_verify_result` REAL 分支调用 `verify_real_fix`；CPU/MAC 返回 `verify_passed=False` 并标注「修复降级/不可修复」；MOCK/SIMULATOR 原关键词逻辑逐字保留。

#### 7. MOD-RE-006 — 安全（凭据/写白名单/审计脱敏/只读备份）
- `REAL_WRITE_PORT_WHITELIST = frozenset({"Gi1/0/2"})`；`handle_execute_fix` 对 REAL 非空命令下发前校验目标端口 ∈ 白名单，越权则记审计 + `status=FAILED`。
- `handle_backup_config` REAL 分支调用新 `_real_backup`（只读 `show running-config` 经 `_open_ssh_session`/`_open_telnet_session` + `session_guard_by_access`，不 `save()`、不写）。
- `_sanitize_state_snapshot` 新增脱敏方法，`_log_node` 的 5 处 `state_snapshot` 均移除 `device_info.password/enable_password`（ADR-RE-006：审计/时间线不含明文密码）。

#### 8. ADR-RE-007 — simulate 告警真实性回填
- `alerts_router.simulate_alert` 捕获 DB Device 记录；`device_type == "REAL"` 时回填 `device_model`（真实型号）、`device_ip`（默认 `192.168.1.1` 时取 DB 值）、`interface`（默认 `Gi0/1` 时取 `Gi1/0/2`）；调用侧显式传参优先；告警文案同步使用回填后的端口。

## 架构偏差记录

无架构偏差。所有实现均落在 APPROVED 的 ADR-RE-001 ~ ADR-RE-007 与 module_design.md 变更范围清单内；`switch_diag_tool.py` / `switch_config_tool.py` 会话链（`_SshSession` paramiko 直连）按零改动清单保持不动，其 DSA KEX 兼容风险作为已知开放问题记录在代码评审报告（见 MAJOR-001）。

## 零回归验证

- 执行命令：`python -m pytest tests/ -v --tb=short --ignore=tests/test_e2e_webui.py --ignore=tests/test_e2e_full.py --ignore=tests/test_inspection_systemd_e2e.py --ignore=tests/test_e2e_inspection_config_refactor.py --ignore=tests/test_simulator_e2e.py --ignore=tests/test_simulator_tools_e2e.py -k "not slow"`
- 结果：**487 passed, 1 xfailed**（xfailed 为既有预期失败，非本次引入）。
- 零新增 Python/Node 依赖；`src/main.py` L79-80 MOCK 注入未改。

<audit_log>
  <log time="2026-09-05T05:30:00Z" state="WRITE_FILES" action="file_write" result="SUCCESS" trace_id="inv-real-e2e-c-001" file_path="project_workspace/real_device_e2e/development/real_device_e2e_implementation_plan.md"/>
</audit_log>
