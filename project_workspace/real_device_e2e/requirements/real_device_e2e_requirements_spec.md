<file_header>
  <project_id>NetworkAgentDemo</project_id>
  <module_id>real_device_e2e</module_id>
  <doc_type>requirements_spec</doc_type>
  <file_name>real_device_e2e_requirements_spec.md</file_name>
  <version>0.2.0</version>
  <status>APPROVED</status>
  <author_agent>sub_agent_requirement_analyst</author_agent>
  <created_at>2026-09-05T03:00:00Z</created_at>
  <last_updated>2026-09-05T03:10:00Z</last_updated>
  <invocation_id>inv-real-e2e-a-002</invocation_id>
  <input_source>PM agent_invocation — 用户已确认决策（Q-RE-01/02/03 RESOLVED）定稿修订</input_source>
</file_header>

# 真实设备（REAL）端到端工作流 — 需求规格说明书

## 执行摘要

### 业务背景

NetworkAgentDemo 是 LangGraph 网络自动化 agent，14 节点工作流 `receive_alert → parse_alert → validate_alert → get_device_info → establish_ssh → collect_diag → analyze_root_cause → generate_fix_plan → assess_risk → human_approval → backup_config → execute_fix → verify_fix → finish_report`（`state_graph_engine.py` 第 62-76 行）。设备工具层采用策略模式三后端：MOCK（内存假数据）、SIMULATOR（本地模拟器 `src/simulator/`）、REAL（真实 TP-Link 客户端 `src/tools/real_device_client.py`）。

MOCK/SIMULATOR 上已有完整「告警→诊断→修复→验证→关闭」E2E 场景可跑通（`tests/test_e2e_full.py`、`tests/test_simulator_e2e.py`）。上一轮「真实设备面板」（REAL_DEVICE_PANEL）已全部 APPROVED，REAL 连接链路（TP-Link TL-SG5428 经 FRP 反代隧道 SSH `frp_proxy_host=127.0.0.1`、`frp_proxy_port=6022` → 交换机局域网 `192.168.31.220`）已打通，且产出 `src/tools/real_panel_parsers.py`（TP-Link 输出解析）、`src/tools/real_session_gate.py`（会话串行化门）、`src/tools/real_panel_service.py`。

**本需求的目标**：把 MOCK/SIMULATOR 上已有的完整 E2E 场景在 REAL 设备上调通——即「模拟告警 → 真实诊断 → 真实修复 → 真实验证 → 收敛关闭」这一端到端闭环，**尚未在真实设备上验证过完整跑通**（用户需求原文："本次目标：把 MOCK/SIMULATOR 上已有的完整 E2E 场景在 REAL 设备上调通"）。本需求层只约束「必须达成什么」，涉及「如何实现」（FRP 解析落点、命令映射表落点、工具选择逻辑落点、验证逻辑改动方式）一律标注为「交 GROUP_B 架构裁决」。

### 需求总览

| 类别 | 数量 |
|------|------|
| 功能需求（REQ-RE-FUNC） | 8 |
| 非功能需求（REQ-RE-NFUNC） | 4 |
| 用户故事（US-RE） | 8 |
| 开放问题（Q-RE） | 3（Q-RE-04/05/06 待确认；Q-RE-01/02/03 已 RESOLVED） |
| [INFERRED] 需求占比 | 0%（不确定项全部收敛进 Q-RE 开放问题，不进入需求正文） |

### 核心结论（用户已确认）

1. **测试端口（Q-RE-01 已确认）**：验证时允许对真实端口 **`Gi1/0/2`** 做写操作（当前 down 的空闲口，无关键业务）。
2. **写操作范围（Q-RE-02 已确认）**：`no shutdown` 与 `shutdown` 均允许；其中 `shutdown` 属隔离场景，需更高一级授权，不作为默认修复动作；`description <desc>` 默认不纳入。
3. **告警类型范围（Q-RE-03 已确认）**：PORT_DOWN / PORT_SHUTDOWN / CPU_HIGH / MAC_FLAPPING 四类**全部要求含真实修复**（不再仅 PORT_DOWN）；CPU_HIGH/MAC_FLAPPING 的 TP-Link 真实修复命令存在性需在 GROUP_B 核实（见 RISK-RE-01）。
4. **写操作安全红线（已确定，非开放项）**：真实端口写操作是高风险生产写，需用户单独授权并指定测试端口；默认不做 `copy running-config startup-config` 持久化。
5. **凭据安全红线（已确定，非开放项）**：不硬编码任何明文密码，凭据走既有 `DEVICE_<NAME>_PASSWORD` 环境变量或 DB Fernet 解密机制（`config_manager.py`），不得新增明文密码。

---

## 功能需求（Functional Requirements）

### REQ-RE-FUNC-001 — REAL 设备模拟告警硬件真实性

| 字段 | 内容 |
|------|------|
| ID | REQ-RE-FUNC-001 |
| 描述 | 发起模拟告警时，告警信息应当反映真实设备硬件，而非 MOCK 的假端口/假型号/假地址：端口使用真实 TP-Link 命名（如 `Gi1/0/1` 而非 `Gi0/1`）、设备型号为真实 `TL-SG5428`（而非硬编码的 `TP-Link T2600G-28TS`）、接入地址反映真实 FRP/局域网地址（而非默认 `192.168.1.1`）。CPU_HIGH 告警的百分比与阈值应符合 TL-SG5428 实际（具体数值待 Q-RE-04 确认）。 |
| 来源引用 | 用户需求原文（子场景1）："发出模拟告警——告警信息符合真实设备硬件（如真实端口 `Gi1/0/1` 的 PORT_DOWN/PORT_SHUTDOWN、或符合 TL-SG5428 实际的 CPU_HIGH 阈值），不用 MOCK 的 `Gi0/1` 假端口"；现有代码：`src/api/alerts_router.py` 第 23-29 行（`SimulateAlertRequest.interface` 默认 "Gi0/1"、`device_ip` 默认 "192.168.1.1"）、第 239 行（`device_model` 硬编码 "TP-Link T2600G-28TS"）、第 212 行（CPU_HIGH 描述硬编码 "92%...80%"） |
| 优先级 | Must Have |
| 备注 | 具体「如何让告警信息反映真实硬件」（是 simulate 端点自动按 device_name 回填真实元数据，还是仅测试/调用侧传入真实参数）交 GROUP_B 裁决；边界口径见 Q-RE-06 |

### REQ-RE-FUNC-002 — REAL 设备工作流接入路由（关键缺口）

| 字段 | 内容 |
|------|------|
| ID | REQ-RE-FUNC-002 |
| 描述 | `establish_ssh → collect_diag → execute_fix → verify_fix`（以及 `backup_config`）在 REAL 设备上必须通过真实接入路径到达交换机（FRP 隧道 `frp_proxy_host=127.0.0.1`、`frp_proxy_port=6022` → 局域网 `192.168.31.220`，协议 SSH），而非用告警携带的默认 `device_ip`（如 `192.168.1.1`）直连默认 22 端口。工作流必须能解析 REAL 设备的 FRP 映射、连接协议（`connection_protocol`）、真实凭据并回填到诊断/配置执行上下文。 |
| 来源引用 | PM 缺口2（原文）："REAL 接入路由缺失（关键）：工作流 `handle_collect_diag`/`handle_execute_fix`/`handle_verify_result` 用 `device_ip = device_info.get("device_ip")` + `_extract_auth`（不设 protocol、不解析 FRP）…未走 FRP（127.0.0.1:6022）…`handle_get_device_info` 只取凭据、不回填 device_ip/frp/protocol"；现有代码：`src/orchestration/node_handlers.py` 第 483 行（`device_ip = device_info.get("device_ip", "192.168.1.1")`）、第 490/1086-1093 行（`_extract_auth` 不设 protocol、port 默认 22）、第 430-451 行（`handle_get_device_info` 只回填 username/password 与默认 model/ip，不回填 frp/protocol）；`src/tools/real_device_client.py` 第 408-429 行（`_resolve_access` 可解析 FRP）、第 2088-2126 行（`DeviceToolSession` 使用 `_resolve_access`）；`src/tools/switch_diag_tool.py` 第 260-271 行、`src/tools/switch_config_tool.py` 第 159-171 行（TpLink* 工具 `_run` 用 `_SshSession(device_ip, port, ...)` 直连，仅取 auth.port/protocol，不解析 FRP） |
| 优先级 | Must Have |
| 备注 | FRP 解析与接入参数回填的「具体落点」（工作流节点内、`_extract_auth`、工具层、还是统一走 `DeviceToolSession`）交 GROUP_B 架构裁决；本需求只约束「必须真实到达 REAL 设备」 |

### REQ-RE-FUNC-003 — REAL 诊断/配置工具真实选择（不落 Mock）

| 字段 | 内容 |
|------|------|
| ID | REQ-RE-FUNC-003 |
| 描述 | 当告警 `device_type="REAL"` 时，诊断节点（collect_diag/verify_fix）与配置节点（execute_fix）必须选择真实 TP-Link 工具（`TpLinkSwitchDiagTool`/`TpLinkSwitchConfigTool`）执行，而非回落到 Mock 工具返回假数据；REAL 告警的 `establish_ssh` 节点也应执行真实 SSH 连接（或至少校验真实接入可达性），而非仅打印 Mock 日志。 |
| 来源引用 | 现有代码：`src/orchestration/node_handlers.py` 第 169-183 行（`_get_diag_tool_for_device`/`_get_config_tool_for_device` 仅对 `device_type=="SIMULATOR"` 分支，其余（含 REAL）返回注入的 `self.switch_diag_tool`/`self.switch_config_tool`）、第 455-471 行（`handle_establish_ssh` 仅打印 Mock 日志）；`src/main.py` 第 79-80 行（`create_switch_diag_tool(use_mock=True)`/`create_switch_config_tool(use_mock=True)`，默认注入 Mock 工具）；`src/tools/switch_diag_tool.py` 第 316-339 行（工厂 `device_type=="REAL"` 才返回 TpLink 工具） |
| 优先级 | Must Have |
| 备注 | 工具选择逻辑的落点（工厂按 device_type 注入 vs 工作流节点运行时按 device_type 分支）交 GROUP_B 裁决；本需求只约束「REAL 必须真实执行，不落 Mock」 |

### REQ-RE-FUNC-004 — REAL 诊断命令与输出解析真实映射

| 字段 | 内容 |
|------|------|
| ID | REQ-RE-FUNC-004 |
| 描述 | `collect_diag`/`verify_fix` 在 REAL 设备上必须使用真实 TL-SG5428 已校准命令（`show interface status`、`show cpu-utilization`、`show memory-utilization`、`show system-info`），而非 Cisco/Mock 风格命令（`show mac address-table`、`show processes cpu`、`show processes cpu history`、`show logging`）。诊断输出必须解析为可分析的结构化结果（复用上一轮 `src/tools/real_panel_parsers.py` 的 TP-Link 输出解析能力），解析失败时返回明确错误而非错误数据。 |
| 来源引用 | PM 缺口3（原文）："诊断命令 REAL 映射缺失：`DIAG_COMMAND_MAP` 用 Cisco/Mock 命令…真实 TL-SG5428 已验证命令是 `show interface status`/`show cpu-utilization`/`show memory-utilization`/`show system-info`"；用户背景原文："真实 CLI 已校准：`show interface status`（列：Port/Status/Speed/Duplex/FlowCtrl/Active-Medium，无 VLAN 列）、`show cpu-utilization`（返回百分比）、`show memory-utilization`（仅返回裸 `80%`）、`show system-info`"；现有代码：`src/orchestration/node_handlers.py` 第 48-61 行（`DIAG_COMMAND_MAP` 为 Cisco/Mock 命令）、`src/tools/switch_diag_tool.py` 第 178-187 行（Mock 命令表） |
| 优先级 | Must Have |
| 备注 | 命令映射表/解析逻辑的落点交 GROUP_B 裁决；`show interface status` 真实输出无 VLAN 列，需求层不预设 VLAN 字段 |

### REQ-RE-FUNC-005 — REAL 修复命令模板真实可用（覆盖四类告警，TP-Link 语法）

| 字段 | 内容 |
|------|------|
| ID | REQ-RE-FUNC-005 |
| 描述 | `execute_fix` 在 REAL 设备上下发的修复命令必须覆盖四类告警（PORT_DOWN / PORT_SHUTDOWN / CPU_HIGH / MAC_FLAPPING），且全部为 TP-Link TL-SG5428 可用语法。已可用：PORT_DOWN → `configure` → `interface <port>` → `no shutdown` → `exit`（TPL-PORT-ENABLE）；PORT_SHUTDOWN → `configure` → `interface <port>` → `shutdown` → `exit`（TPL-PORT-DISABLE）。CPU_HIGH / MAC_FLAPPING 需补 TP-Link 等价模板（当前 Cisco 模板不可用，见 REQ-RE-FUNC-008）。`description <desc>` 默认不纳入（Q-RE-02）。 |
| 来源引用 | 用户决策 Q-RE-03（原文）："告警类型范围 = 全部类型含修复：PORT_DOWN / PORT_SHUTDOWN / CPU_HIGH / MAC_FLAPPING 四类都要在 REAL 设备上有真实 TP-Link 修复"；用户决策 Q-RE-02（原文）："no shutdown + shutdown 均允许…description 默认不纳入"；现有代码：`resources/templates/tpl_port_enable.yaml`（`interface {{ iface_name }}` + `no shutdown`）、`resources/templates/tpl_port_disable.yaml`（`shutdown`）、`resources/templates/tpl_cpu_rate_limit.yaml`（CoPP Cisco 语法，不可用）、`resources/templates/tpl_mac_port_security.yaml`（port-security Cisco 语法，不可用） |
| 优先级 | Must Have |
| 备注 | CPU_HIGH/MAC_FLAPPING 的 TP-Link 等价模板可行性见 REQ-RE-FUNC-008 与 RISK-RE-01；`shutdown` 属隔离场景需更高授权（REQ-RE-NFUNC-002） |

### REQ-RE-FUNC-006 — REAL 验证对比真实校准

| 字段 | 内容 |
|------|------|
| ID | REQ-RE-FUNC-006 |
| 描述 | `verify_fix` 重新诊断对比修复前后状态时，判定逻辑必须基于真实 TL-SG5428 `show interface status` 输出格式（真实 Status 列是 Enable/Disable 或 up/down），而非 Cisco 风格关键词 `["down","notconnect"]`。验证通过/失败应当以真实输出的结构化解析结果为准（可复用 `real_panel_parsers.py`），而非对裸文本做关键词匹配。 |
| 来源引用 | PM 缺口5（原文）："验证对比校准：`handle_verify_result` 用关键词 ["down","notconnect"]（Cisco 风格）判断 PORT_DOWN 修复前后；真实 `show interface status` 的 Status 列是 Enable/Disable（或 up/down），需用真实输出格式校准（可复用 `real_panel_parsers.py` 的解析）"；现有代码：`src/orchestration/node_handlers.py` 第 962-970 行（`alert_keywords` 含 "down"/"notconnect"/"92%"）；`src/tools/switch_diag_tool.py` 第 46-54 行（MOCK_INTERFACE_STATUS 用 "down"/"notconnect"/"connected" 列） |
| 优先级 | Must Have |
| 备注 | 验证判定逻辑（关键词改结构化解析）的落点交 GROUP_B 裁决 |

### REQ-RE-FUNC-007 — REAL E2E 工作流端到端收敛闭环

| 字段 | 内容 |
|------|------|
| ID | REQ-RE-FUNC-007 |
| 描述 | 完整链路（模拟告警 → establish_ssh → collect_diag → analyze_root_cause → generate_fix_plan → assess_risk → [human_approval 如需要] → backup_config → execute_fix → verify_fix → finish_report）在 REAL 设备上必须端到端跑通并收敛：修复后 `verify_fix` 判定通过、工作流收敛到 `finish_report` 并将告警状态置为 CLOSED。四个子场景（真实告警、真实诊断、真实修复、真实验证）共同构成该闭环。 |
| 来源引用 | 用户需求原文（子场景2/3/4）："AI agent 通过命令真实诊断设备状态…在 REAL 设备上真实执行 `show interface status` 等诊断命令并解析"、"发送修复命令…真实下发修复命令序列（如 `interface <port> → no shutdown`）"、"检查验证…重新诊断对比修复前后状态，工作流收敛到 `finish_report` 关闭"；现有代码：`src/orchestration/state_graph_engine.py` 第 62-76 行（14 节点图）、第 133/136-143 行（execute_fix → verify_fix 边与路由）、`src/orchestration/node_handlers.py` 第 1023-1035 行（`handle_final_report` 状态判定 CLOSED） |
| 优先级 | Must Have |
| 备注 | — |

### REQ-RE-FUNC-008 — REAL CPU_HIGH/MAC_FLAPPING 修复可行性核实与降级（RISK）

| 字段 | 内容 |
|------|------|
| ID | REQ-RE-FUNC-008 |
| 描述 | CPU_HIGH / MAC_FLAPPING 的 TP-Link 真实修复命令是否存在必须由架构阶段（GROUP_B）核实：当前 Cisco 模板（CoPP `policy-map`/`class-map`、`switchport port-security`）在 TL-SG5428 不可用，GROUP_B 需确认 TL-SG5428 实际可用的等价 CLI 能力（如风暴抑制 storm-control / 端口安全 / CPU 限速是否有等价命令）。若存在等价命令 → 补写 TP-Link 版修复模板并纳入修复闭环；若无等价命令 → 该两类降级为「真实诊断 + 告警闭环、修复降级」（诊断/根因/报告仍真实执行，但不下发修复命令，最终报告明确标注「修复降级/不可修复」）。严禁架构阶段凭空承诺不可实现的修复。 |
| 来源引用 | 用户决策 Q-RE-03（原文）："CPU_HIGH / MAC_FLAPPING 四类都要在 REAL 设备上有真实 TP-Link 修复"；PM 缺口4（原文）："`tpl_cpu_rate_limit`（CoPP）与 `tpl_mac_port_security`（switchport port-security）是 Cisco 语法，在 TL-SG5428 上不可用"；现有代码：`resources/templates/tpl_cpu_rate_limit.yaml`（CoPP）、`resources/templates/tpl_mac_port_security.yaml`（port-security） |
| 优先级 | Must Have（带 RISK，可降级） |
| 备注 | 关联 RISK-RE-01；「等价命令是否存在」为事实核查项，转 GROUP_B 架构阶段核实后反馈 |

---

## 非功能需求（Non-Functional Requirements）

### REQ-RE-NFUNC-001 — 安全：凭据不硬编码明文

| 字段 | 内容 |
|------|------|
| ID | REQ-RE-NFUNC-001 |
| 描述 | REAL 设备凭据必须走既有密钥/环境变量机制（`DEVICE_<NAME>_PASSWORD` 环境变量或 DB Fernet 解密），不得新增任何明文密码。当前 `get_device_credentials` 的兜底硬编码 `admin123` 不得作为 REAL 生产设备的凭据来源。 |
| 来源引用 | 用户安全红线1（原文）："不硬编码任何明文密码；VPS/交换机凭据走既有密钥/环境变量机制（`DEVICE_<NAME>_PASSWORD` 或 DB Fernet 解密，`config_manager.py`）"；现有代码：`src/security/config_manager.py` 第 128-170 行（`get_device_credentials`：config.yaml → SQLite Fernet 解密 → 环境变量 → 兜底 `admin123`，第 161 行 `pwd or "admin123"`、第 170 行 fallback `admin123`）、`src/database/device_models.py` 第 78-96 行（`DeviceCredential.ssh_password_encrypted` 第 91-93 行 Fernet 密文） |
| 优先级 | Must Have（强制适用） |
| 备注 | — |

### REQ-RE-NFUNC-002 — 安全：真实端口写操作授权与可逆优先

| 字段 | 内容 |
|------|------|
| ID | REQ-RE-NFUNC-002 |
| 描述 | REAL 端口写操作是高风险生产写，写操作集合已确认（Q-RE-02）：`no shutdown`（默认可逆修复）+ `shutdown`（隔离场景，更高一级授权，不作为默认修复动作）；`description <desc>` 不纳入。必须满足：① 需用户单独授权并指定测试端口（已确认 `Gi1/0/2`，无关键业务）；② 优先「只读诊断 + 可逆修复（no shutdown）」；③ 写命令仅限用户确认的修复动作，作用于被授权端口；④ 默认不做 `copy running-config startup-config` 持久化；⑤ 每次写操作写入审计日志且不记录明文密码。 |
| 来源引用 | 用户决策 Q-RE-01（原文）："测试端口 = Gi1/0/2（当前 down 的空闲口，无关键业务）"；用户决策 Q-RE-02（原文）："no shutdown + shutdown 均允许；shutdown 属隔离场景需更高一级授权，不作为默认修复动作；description 默认不纳入"；用户安全红线2/3；现有代码：`src/tools/real_device_client.py` 第 1226-1238 行（`save()` 持久化能力，本需求明确不调用） |
| 优先级 | Must Have（强制适用） |
| 备注 | — |

### REQ-RE-NFUNC-003 — 可靠性：会话串行化与超时

| 字段 | 内容 |
|------|------|
| ID | REQ-RE-NFUNC-003 |
| 描述 | REAL 诊断/配置会话必须复用上一轮已实现的会话串行化门（`src/tools/real_session_gate.py`），避免与「连通性检测」「REAL 面板采集」等其他 REAL 会话并发冲突（TP-Link TL-SG5428 TELNET 仅 1 个活动会话）。会话必须在 finally 中关闭并设超时，单次诊断复用同一会话批量下发多条 show 命令。 |
| 来源引用 | 用户背景原文："工作流工具 REAL 分支已接入会话串行化门"；现有代码：`src/tools/switch_diag_tool.py` 第 266-267 行（`session_guard_by_access` 包裹）、第 294-298 行（finally 中 close 会话）、`src/tools/switch_config_tool.py` 第 165-166 行（`session_guard_by_access` 包裹）、`src/tools/real_session_gate.py`（会话串行化门实现） |
| 优先级 | Must Have |
| 备注 | — |

### REQ-RE-NFUNC-004 — 兼容性：不破坏 MOCK/SIMULATOR E2E 与 REAL 面板

| 字段 | 内容 |
|------|------|
| ID | REQ-RE-NFUNC-004 |
| 描述 | 为 REAL 打通 E2E 不得破坏：MOCK/SIMULATOR 现有 E2E 流程与测试（`tests/test_e2e_full.py`、`tests/test_simulator_e2e.py`）、上一轮已交付的 REAL 面板能力（`real_device_panel/` 与 `real_panel_*` 模块）、以及现有 REAL 设备的「心跳检测」「连通性检测」。本次为 REAL E2E 补齐能力，不修改 SIMULATOR/MOCK 分支行为。 |
| 来源引用 | 用户背景原文："上一轮「真实设备面板」（REAL_DEVICE_PANEL）已全部 APPROVED"、"设备工具层策略模式三后端：MOCK / SIMULATOR / REAL"；现有代码：`src/main.py` 第 79-80 行（MOCK 工具默认注入，保证 MOCK 路径不变）、`src/orchestration/node_handlers.py` 第 169-183 行（SIMULATOR 分支已有专属工具） |
| 优先级 | Must Have |
| 备注 | — |

---

## 超出范围（Out of Scope）

| 序号 | 排除项 | 说明 |
|------|--------|------|
| OS-02 | `copy running-config startup-config` 持久化 | 明确不做（安全红线），写操作仅当前 running-config 生效 |
| OS-04 | SNMP / NETCONF / RESTCONF 等非 CLI 采集 | REAL E2E 仅通过 SSH CLI 采集与配置 |
| OS-05 | 巡检（inspection）REAL 化 / 告警风暴处理 | 本次仅覆盖「模拟告警 → E2E 闭环」，不涉及巡检链路与告警去重/风暴治理 |

> 说明：OS-01「CPU_HIGH / MAC_FLAPPING 的 REAL 修复」与 OS-03「新增 TP-Link 版 CPU/MAC 修复模板」原为超出范围项，经用户确认（Q-RE-03「全部类型含修复」）已**纳入范围**（见 REQ-RE-FUNC-005 与 REQ-RE-FUNC-008），故从本表移除。

---

## 风险与假设（RISK / ASSUMPTION）

| 编号 | 风险等级 | 描述 | 影响 | 缓解/核实方式 |
|------|---------|------|------|--------------|
| RISK-RE-01 | 高 | CPU_HIGH / MAC_FLAPPING 的 TP-Link 真实修复命令存在性未知：当前 Cisco 模板（CoPP `policy-map`/`class-map`、`switchport port-security`）在 TL-SG5428 不可用，TL-SG5428 是否有等价 CLI（storm-control / 端口安全 / CPU 限速）未经核实 | 若无可实现等价命令，则 CPU_HIGH/MAC_FLAPPING 无法完成「真实修复」闭环，只能降级为「真实诊断 + 告警闭环、修复降级」 | 转 GROUP_B 架构阶段核实（见 REQ-RE-FUNC-008）；核实前架构/实现阶段不得承诺 CPU/MAC 修复可落地 |

---

## 开放问题清单（Q-RE-*）

| 编号 | 风险 | 问题 | 状态 | 最终决议 |
|------|------|------|------|---------|
| Q-RE-01 | 高 | 验证时允许对哪个真实端口做写操作？ | **RESOLVED** | 测试端口 = `Gi1/0/2`（当前 down 的空闲口，无关键业务） |
| Q-RE-02 | 高 | 修复动作集合是否允许含 `shutdown`？是否允许 `description <desc>` 额外写？ | **RESOLVED** | `no shutdown` + `shutdown` 均允许；`shutdown` 属隔离场景需更高一级授权，不作为默认修复动作；`description <desc>` 默认不纳入 |
| Q-RE-03 | 中 | 本次 REAL E2E 的告警类型范围？ | **RESOLVED** | 全部类型含修复：PORT_DOWN / PORT_SHUTDOWN / CPU_HIGH / MAC_FLAPPING 四类都要在 REAL 设备上有真实 TP-Link 修复（不再仅 PORT_DOWN） |
| Q-RE-04 | 中 | CPU_HIGH 告警阈值与判定标准用多少？ | 待确认 | 现有模拟告警硬编码 92%/阈值 80%（`alerts_router.py` 第 212 行），需确认 TL-SG5428 实际阈值 |
| Q-RE-05 | 中 | 凭据与环境变量确认 + FRP 隧道可达性 | 待确认 | 门控前确认凭据已就位、FRP 隧道可连通 |
| Q-RE-06 | 中 | 告警真实性达成口径 | 待确认 | 建议最小改动——调用侧传真实参数，自动回填交 GROUP_B |

---

## 与现有架构的对齐说明

> 下表仅标注「需求将影响哪些现有模块」，不涉及任何模块设计/技术选型（该部分属 GROUP_B 及之后）。

| 需求 ID | 影响的现有模块/文件（只读事实） | 变更性质（需求层约束） |
|---------|----------------------------------|------------------------|
| REQ-RE-FUNC-001 | `src/api/alerts_router.py`（第 23-29、212、239 行）、`src/models/alert.py`（`DeviceInfo` 第 30-38 行，无 frp 字段） | 告警信息需反映真实硬件 |
| REQ-RE-FUNC-002 | `src/orchestration/node_handlers.py`（第 430-451、483、490、1086-1093 行）、`src/tools/switch_diag_tool.py`、`src/tools/switch_config_tool.py`、`src/tools/real_device_client.py`（第 408-429、2088-2126 行） | REAL 需走 FRP 接入 |
| REQ-RE-FUNC-003 | `src/orchestration/node_handlers.py`（第 169-183、455-471 行）、`src/main.py`（第 79-80 行）、`src/tools/switch_diag_tool.py`（第 316-339 行）、`src/tools/switch_config_tool.py`（第 206-229 行） | REAL 需真实执行不落 Mock |
| REQ-RE-FUNC-004 | `src/orchestration/node_handlers.py`（第 48-61 行 DIAG_COMMAND_MAP）、`src/tools/real_panel_parsers.py` | REAL 诊断命令与解析映射 |
| REQ-RE-FUNC-005 | `resources/templates/tpl_*.yaml`、`src/orchestration/node_handlers.py`（第 1108-1116 行） | REAL 修复命令需 TP-Link 语法 |
| REQ-RE-FUNC-006 | `src/orchestration/node_handlers.py`（第 962-970 行）、`src/tools/real_panel_parsers.py` | 验证判定真实校准 |
| REQ-RE-FUNC-007 | `src/orchestration/state_graph_engine.py`、`src/orchestration/node_handlers.py` | 端到端闭环收敛 |
| REQ-RE-FUNC-008 | `resources/templates/tpl_cpu_rate_limit.yaml`、`tpl_mac_port_security.yaml`、`src/tools/real_device_client.py` | CPU/MAC 修复可行性核实与降级 |
| REQ-RE-NFUNC-001 | `src/security/config_manager.py`（第 128-170 行） | 凭据安全约束 |
| REQ-RE-NFUNC-002 | `src/orchestration/node_handlers.py`（execute_fix/assess_risk/human_approval）、`src/security/audit_logger.py` | 写操作授权与审计 |
| REQ-RE-NFUNC-003 | `src/tools/real_session_gate.py`、`src/tools/switch_diag_tool.py`、`src/tools/switch_config_tool.py` | 会话串行化复用 |
| REQ-RE-NFUNC-004 | 现有 MOCK/SIMULATOR 路径与 `real_device_panel/` | 兼容性约束（零破坏） |

---

*文档版本 0.2.0 | 状态 APPROVED | 生成时间 2026-09-05 | 作者 sub_agent_requirement_analyst*

<audit_log>
  <log time="2026-09-05T03:00:00Z" state="WRITE_FILES" action="file_write" result="SUCCESS" trace_id="inv-real-e2e-a-001" file_path="project_workspace/real_device_e2e/requirements/real_device_e2e_requirements_spec.md"/>
  <log time="2026-09-05T03:10:00Z" state="WRITE_FILES" action="file_update" result="SUCCESS" trace_id="inv-real-e2e-a-002" file_path="project_workspace/real_device_e2e/requirements/real_device_e2e_requirements_spec.md"/>
</audit_log>
