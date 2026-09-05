<file_header>
  <project_id>NetworkAgentDemo</project_id>
  <module_id>real_device_panel</module_id>
  <doc_type>requirements_spec</doc_type>
  <file_name>real_panel_requirements_spec.md</file_name>
  <version>0.2.0</version>
  <status>APPROVED</status>
  <author_agent>sub_agent_requirement_analyst</author_agent>
  <created_at>2026-09-05T00:00:00Z</created_at>
  <last_updated>2026-09-05T02:00:00Z</last_updated>
  <invocation_id>inv-real-panel-a-002</invocation_id>
  <input_source>PM agent_invocation — 用户已确认决策（Q-RP-01~05 RESOLVED）定稿修订</input_source>
</file_header>

# 真实设备（REAL）面板 — 需求规格说明书

## 执行摘要

### 业务背景

NetworkAgentDemo 的 Web 设备管理页（`webui/src/views/devices/DevicesListView.vue`）中，SIMULATOR 设备已经具备一个「面板」功能（`REQ-FUNC-118`），通过 `el-drawer` 抽屉展示两类数据：
1. **端口状态**：端口表格（name / status / vlan / speed），每行提供「启用 / 禁用」按钮（`no-shutdown` / `shutdown`）；
2. **系统资源**：CPU(5s) %、内存 used/total MB、IO 读/写 KB/s（`el-progress` 进度条）。

数据来源于 store 方法 `getDevicePorts`、`getDeviceSystem`、`configurePort`（`webui/src/stores/devices.ts` 第 89-107 行），后端端点 `/api/devices/{id}/ports`、`/api/devices/{id}/system`、`/api/devices/{id}/ports/{name}/config`（`src/api/devices_router.py` 第 660-732 行）当前仅对 `device_type === 'SIMULATOR'` 生效，对 REAL 设备返回「请通过 switch_diag_tool 执行 show 命令」的提示。

REAL 设备在操作列目前仅有「心跳检测」「连通性检测」两个按钮（`DevicesListView.vue` 第 57-60 行），没有面板。REAL 设备连接链路已打通：真实 TP-Link TL-SG5428（SSH/Telnet/HTTP）通过 `src/tools/real_device_client.py`（commit 274bab7）实现，真实设备 CLI 已验证可用命令为 `show system-info`、`show ip ssh`、`show interface status`、`show cpu-utilization`、`show memory-utilization`、`show running-config`；配置端口用 `interface <name>` + `shutdown`/`no shutdown`，进入配置模式用 `configure`/`exit`（非 Cisco 的 `configure terminal`/`end`）。

本需求为 REAL 设备提供与 SIMULATOR 面板对应的面板能力。**信息范围、写操作开放程度、刷新策略、端点形式、会话复用边界等决策点（Q-RP-01~05）已经用户确认（详见「已确认决策」表），本版本据此定稿。**

### 需求总览

| 类别 | 数量 |
|------|------|
| 功能需求（REQ-RP-FUNC） | 10 |
| 非功能需求（REQ-RP-NFUNC） | 4 |
| 用户故事（US-RP） | 9 |
| 已确认决策（Q-RP，RESOLVED） | 5 |
| 验收标准（AC） | 见 user_stories.md |

### 核心结论（用户已确认）

1. **信息范围（Q-RP-01 已确认）**：尽量复刻 SIMULATOR 完整面板——**保留「IO 读写」区块**（真实设备无已验证 IO CLI 命令，需寻找替代命令或降级展示，不得直接丢弃）；基本信息区块（`show system-info`）**默认不纳入**，保留为 Should Have 待架构裁决（低成本增值项），不得作为 Must Have。
2. **端口写操作（Q-RP-02 已确认）**：**开放写操作**——REAL 面板端口提供「启用/禁用」按钮，每次写操作必须前端二次确认 + 写入审计日志（REQ-RP-NFUNC-002 强制适用）；写操作**不做** `copy running-config startup-config` 持久化。
3. **刷新策略（Q-RP-03 已确认）**：手动刷新 + 单会话批量采集（不做后台自动轮询）。
4. **端点形式（Q-RP-04 已确认）**：交由架构阶段（GROUP_B）裁决，本需求层不预设端点具体实现。
5. **会话复用（Q-RP-05 已确认）**：复用 `real_device_client.DeviceToolSession`，会话串行化（TL-SG5428 TELNET 仅 1 个活动会话），不做会话池。

---

## 功能需求（Functional Requirements）

### REQ-RP-FUNC-001 — REAL 设备面板入口按钮

| 字段 | 内容 |
|------|------|
| ID | REQ-RP-FUNC-001 |
| 描述 | 前端设备列表操作列应当对 `device_type === 'REAL'` 的设备新增「面板」按钮，与 SIMULATOR 的「面板」按钮（`DevicesListView.vue` 第 66 行）并列，点击后打开 REAL 设备面板抽屉。REAL 设备原有的「心跳检测」「连通性检测」按钮保持不变。 |
| 来源引用 | 用户需求原文："SIMULATOR 设备已有一个「面板」功能，现在要为 REAL 设备也做对应面板"；现有代码：`DevicesListView.vue` 第 57-60 行（REAL 操作列仅心跳/连通性检测，无面板按钮）、第 66 行（SIMULATOR 面板按钮） |
| 优先级 | Must Have |
| 备注 | — |

### REQ-RP-FUNC-002 — REAL 设备端口状态查看

| 字段 | 内容 |
|------|------|
| ID | REQ-RP-FUNC-002 |
| 描述 | REAL 设备面板应当展示端口状态表格，字段至少包含端口名（name）、状态（status，up/down/notconnect）、VLAN、速率（speed）。数据来源为真实设备 `show interface status` 命令输出，需解析为结构化字段（见 REQ-RP-FUNC-009）。端口表格呈现与 SIMULATOR 面板的「端口状态」区块（`DevicesListView.vue` 第 151-167 行）保持一致。 |
| 来源引用 | 用户需求原文："真实设备 CLI 已验证可用命令：... `show interface status` ..."；现有代码：`DevicesListView.vue` 第 151-167 行（SIMULATOR 端口表格字段 name/status/vlan/speed）、`switch_diag_tool.py` 第 46-54 行（MOCK_INTERFACE_STATUS 参考格式） |
| 优先级 | Must Have |
| 备注 | TP-Link `show interface status` 实际输出格式与 Mock 参考格式可能不同，需按真实输出解析 |

### REQ-RP-FUNC-003 — REAL 设备 CPU 利用率查看

| 字段 | 内容 |
|------|------|
| ID | REQ-RP-FUNC-003 |
| 描述 | REAL 设备面板应当展示 CPU 利用率，至少包含 5 秒平均使用率百分比。数据来源为真实设备 `show cpu-utilization` 命令输出，需解析出 5s 值（若输出含 1min/5min 值一并解析可选）。呈现与 SIMULATOR 面板的「CPU (5s)」区块（`DevicesListView.vue` 第 181-185 行）保持一致（`el-progress` 进度条）。 |
| 来源引用 | 用户需求原文："真实设备 CLI 已验证可用命令：... `show cpu-utilization` ..."；现有代码：`DevicesListView.vue` 第 181-185 行（CPU 5s 进度条） |
| 优先级 | Must Have |
| 备注 | 注意 TP-Link `show cpu-utilization` 与 SIMULATOR 使用的 `show processes cpu`（Cisco 风格）命令名和输出格式不同 |

### REQ-RP-FUNC-004 — REAL 设备内存利用率查看

| 字段 | 内容 |
|------|------|
| ID | REQ-RP-FUNC-004 |
| 描述 | REAL 设备面板应当展示内存使用情况，包含已用/总量（MB）及使用率百分比。数据来源为真实设备 `show memory-utilization` 命令输出。呈现与 SIMULATOR 面板的「内存」区块（`DevicesListView.vue` 第 186-191 行）保持一致。 |
| 来源引用 | 用户需求原文："真实设备 CLI 已验证可用命令：... `show memory-utilization` ..."；现有代码：`DevicesListView.vue` 第 186-191 行（内存 used/total MB + usage_pct） |
| 优先级 | Must Have |
| 备注 | 若 `show memory-utilization` 仅返回 used/free/total，则百分比由 used/total 计算 |

### REQ-RP-FUNC-005 — REAL 设备基本信息查看 [已确认：默认不纳入，作为低成本增值项待架构裁决]

| 字段 | 内容 |
|------|------|
| ID | REQ-RP-FUNC-005 |
| 描述 | REAL 设备面板可选地展示设备基本信息（设备名、型号、硬件版本、软件版本、MAC 地址），数据来源为 `show system-info` 命令输出（`check_connectivity` 已解析 `software_version` 与 `model`，见 `real_device_client.py` 第 2029-2036 行）。此区块为 SIMULATOR 面板没有、而 REAL 面板可额外提供的增值信息。**默认不纳入面板范围，作为低成本增值项保留为 Should Have，由架构阶段（GROUP_B）裁决是否纳入，不得作为 Must Have。** |
| 来源引用 | 用户确认决策 Q-RP-01："基本信息区块（`show system-info`）默认不纳入（simulator 面板没有此区块），可保留为 Should Have 待架构裁决（低成本增值项），但不得作为 Must Have"；现有代码：`real_device_client.py` 第 2029-2036 行（`_parse_show_system_info` 解析 Software/Hardware Version、Device Name）、`devices_router.py` 第 528-540 行（连通性检测已回传 device_model/software_version） |
| 优先级 | Should Have |
| 备注 | 已确认决策 Q-RP-01（RESOLVED）；默认不纳入，非 Must Have |

### REQ-RP-FUNC-006 — REAL 设备端口启用/禁用写操作 [已确认开放]

| 字段 | 内容 |
|------|------|
| ID | REQ-RP-FUNC-006 |
| 描述 | REAL 设备面板**确认开放**端口「启用（no shutdown）/ 禁用（shutdown）」写操作。技术上通过真实设备 CLI 下发：`configure` 进入配置模式 → `interface <name>` 进入端口 → `shutdown` 或 `no shutdown` → `exit` 退出（非 Cisco 的 `configure terminal`/`end`）。每次写操作必须满足：前端**二次确认** + 写入**审计日志**（REQ-RP-NFUNC-002 强制适用）。写操作**不做** `copy running-config startup-config` 持久化。这是对**生产设备的写操作**，风险等级远高于 SIMULATOR 面板写操作。 |
| 来源引用 | 用户确认决策 Q-RP-02："开放写操作——REAL 面板端口提供「启用/禁用」按钮，但每次写操作必须前端二次确认 + 写入审计日志（REQ-RP-NFUNC-002 适用）。写操作不做 copy running-config startup-config 持久化"；用户需求原文："配置端口用 `interface <name>` + `shutdown`/`no shutdown`，进入配置模式用 `configure`/`exit`"；现有代码：`switch_config_tool.py` 第 123-196 行（`TpLinkSwitchConfigTool` 的 `configure` 路径）、`real_device_client.py` 第 1193-1238 行（`configure`/`save` 实现） |
| 优先级 | Must Have |
| 备注 | 已确认决策 Q-RP-02（RESOLVED）；REQ-RP-NFUNC-002 强制适用；不做 `copy running-config startup-config` 持久化 |

### REQ-RP-FUNC-007 — 后端 REAL 面板数据获取能力

| 字段 | 内容 |
|------|------|
| ID | REQ-RP-FUNC-007 |
| 描述 | 后端应当为 REAL 设备提供面板数据获取能力，覆盖「端口状态、CPU 利用率、内存利用率、IO 读写（降级展示）」四类只读数据（以及可选的基本信息）。数据获取应当复用 `real_device_client` 现有会话工厂（`DeviceToolSession` / `check_connectivity`），凭据从 `DeviceCredential` 解密读取。当前 `/api/devices/{id}/ports`、`/system`、`/ports/{name}/config` 三个端点对 REAL 返回「仅适用于模拟器设备」（`devices_router.py` 第 666-668、691-695、715-722 行），需为 REAL 扩展或新增对应能力。 |
| 来源引用 | 现有代码：`devices_router.py` 第 660-732 行（端口/系统端点对 REAL 返回不适用提示）、第 471-541 行（`/check_connectivity` 已实现 REAL 会话登录 + 凭据解密）、`real_device_client.py` 第 2088-2126 行（`DeviceToolSession`）、第 398-429 行（`_resolve_access` FRP 代理解析） |
| 优先级 | Must Have |
| 备注 | 具体端点形式（扩展现有 `/ports` `/system` 端点使其分支 REAL，还是新增 REAL 专用端点）交由架构阶段（GROUP_B）裁决。已确认决策 Q-RP-04（RESOLVED），本需求层仅约束「必须提供 REAL 面板数据获取能力」，不预设端点命名 |

### REQ-RP-FUNC-008 — 前端 REAL 面板抽屉

| 字段 | 内容 |
|------|------|
| ID | REQ-RP-FUNC-008 |
| 描述 | 前端应当新增 REAL 面板抽屉（`el-drawer`），交互模式复用 SIMULATOR 面板抽屉（`DevicesListView.vue` 第 139-204 行），但数据来源为 REAL 后端端点。抽屉内区块结构与已确认的信息范围一致（端口状态、CPU、内存、IO 读写降级展示，以及可选的基本信息、已确认开放的写操作）。抽屉需提供显式的「刷新」入口和加载中/超时/失败反馈（见 REQ-RP-NFUNC-001）。 |
| 来源引用 | 现有代码：`DevicesListView.vue` 第 139-204 行（SIMULATOR 面板抽屉）、第 435-479 行（`showSimulatorPanel`/`loadPorts`/`loadSystem`/`portAction`）、`devices.ts` 第 89-107 行（store 方法） |
| 优先级 | Must Have |
| 备注 | — |

### REQ-RP-FUNC-009 — TP-Link CLI 输出解析

| 字段 | 内容 |
|------|------|
| ID | REQ-RP-FUNC-009 |
| 描述 | 后端应当将真实设备的 `show interface status`、`show cpu-utilization`、`show memory-utilization`（以及可选基本信息的 `show system-info`）原始文本输出解析为结构化字段（端口表：name/status/vlan/speed；CPU：5s 百分比；内存：used/total MB + 百分比）。解析需基于 TP-Link 真实输出格式（非 Mock 模板），解析失败时返回明确错误而非错误数据。 |
| 来源引用 | 现有代码：`real_device_client.py` 第 1978-1994 行（`_strip_echo_and_prompts` 输出清洗）、第 1964-1975 行（`_looks_like_error` 命令错误识别）、第 2029-2036 行（`show system-info` 解析示例）；`switch_diag_tool.py` 第 245-306 行（`TpLinkSwitchDiagTool` 返回原始文本） |
| 优先级 | Must Have |
| 备注 | 具体字段映射依赖真实输出样例，实现阶段需以真实设备输出为基准校准 |

### REQ-RP-FUNC-010 — REAL 设备 IO 读写速率展示（降级展示 / 替代命令待架构裁决）

| 字段 | 内容 |
|------|------|
| ID | REQ-RP-FUNC-010 |
| 描述 | REAL 设备面板应当**保留「IO 读写」区块**（对应 SIMULATOR 面板的「IO 读/写 KB/s」区块），不得直接丢弃。因真实设备目前无已验证的 IO 读/写 CLI 命令，该区块须：① 寻找替代 CLI 命令采集 IO 读/写速率；② 若真实设备确实无可用 IO 命令，则降级展示（如显示「该设备不支持 IO 采集」或从其它已可用命令推导的降级方案），不得直接丢弃该区块。具体替代命令由架构阶段（GROUP_B）裁决。 |
| 来源引用 | 用户确认决策 Q-RP-01："尽量复刻 simulator 完整面板——保留「IO 读写」区块（simulator 面板有 IO，真实设备无已验证的 IO CLI 命令，故 IO 区块需寻找替代命令或降级展示，不得直接丢弃）"；现有代码：`DevicesListView.vue` 第 192-199 行（SIMULATOR「IO 读/写」区块） |
| 优先级 | Must Have |
| 备注 | 降级展示/替代命令待架构裁决（GROUP_B）；本需求仅约束「保留区块 + 降级展示」，不预设具体 IO 采集命令 |

---

## 非功能需求（Non-Functional Requirements）

### REQ-RP-NFUNC-001 — 性能：采集延迟与加载反馈

| 字段 | 内容 |
|------|------|
| ID | REQ-RP-NFUNC-001 |
| 描述 | 真实设备 SSH 会话建立约 20-40s（L7 登录 30-60s），面板单次刷新应有可预期的耗时反馈：前端请求需使用长超时（参考 `checkConnectivity` 的 `timeout: 120000`，`devices.ts` 第 82-87 行），刷新过程中展示 loading 与「约 30-60s」的预期提示，失败时明确报错。刷新策略已确认（Q-RP-03）：**手动刷新 + 单会话批量采集，不做后台自动轮询**。 |
| 来源引用 | 用户确认决策 Q-RP-03："手动刷新 + 单会话批量采集（不做后台自动轮询）"；现有代码：`DevicesListView.vue` 第 400-433 行（连通性检测的 30-60s 提示 + 125s fail-safe）、`devices.ts` 第 82-87 行（`checkConnectivity` timeout 120000） |
| 优先级 | Must Have |
| 备注 | — |

### REQ-RP-NFUNC-002 — 安全：写操作二次确认与审计

| 字段 | 内容 |
|------|------|
| ID | REQ-RP-NFUNC-002 |
| 描述 | REAL 端口写操作已确认开放（REQ-RP-FUNC-006），本需求**强制适用**：每次启用/禁用前必须在前端进行**二次确认**（明确提示「此操作将修改真实生产设备配置」及目标端口与动作），执行结果与操作人写入审计日志（复用现有 AuditLogger）。写操作**不做** `copy running-config startup-config` 持久化（已确认，避免误持久化生产配置）。 |
| 来源引用 | 用户确认决策 Q-RP-02："每次写操作必须前端二次确认 + 写入审计日志（REQ-RP-NFUNC-002 适用）。写操作不做 copy running-config startup-config 持久化"；现有安全体系：`config/config.yaml` + `AuditLogger`（CLAUDE.md 安全与基础设施层）、`switch_config_tool.py` 第 189-196 行、`real_device_client.py` 第 1226-1238 行（`save()` 持久化） |
| 优先级 | Must Have（强制适用） |
| 备注 | 已确认决策 Q-RP-02（RESOLVED） |

### REQ-RP-NFUNC-003 — 兼容性：不影响 SIMULATOR 面板与现有 REAL 端点

| 字段 | 内容 |
|------|------|
| ID | REQ-RP-NFUNC-003 |
| 描述 | 新增 REAL 面板不得破坏：SIMULATOR 面板现有行为、REAL 设备的「心跳检测」「连通性检测」端点、`/check_connectivity` 的返回字段。REAL 面板为新增能力，不修改现有 SIMULATOR 分支逻辑。 |
| 来源引用 | 现有代码：`devices_router.py` 第 411-464 行（心跳）、第 471-541 行（连通性检测）、`DevicesListView.vue` 第 61-67 行（SIMULATOR 按钮组） |
| 优先级 | Must Have |
| 备注 | — |

### REQ-RP-NFUNC-004 — 可靠性：会话串行化与超时

| 字段 | 内容 |
|------|------|
| ID | REQ-RP-NFUNC-004 |
| 描述 | 真实设备会话并发有限（TP-Link TL-SG5428 TELNET 仅允许 1 个活动会话，`real_device_client.py` 第 1661-1663 行注释），面板采集会话需与「连通性检测」「工作流执行」避免并发冲突。单次面板采集复用同一会话批量下发多条 show 命令（避免多次会话建立），会话需在 finally 中关闭并设超时。 |
| 来源引用 | 用户确认决策 Q-RP-05："复用 `real_device_client.DeviceToolSession`，会话串行化（TL-SG5428 TELNET 仅 1 个活动会话），不做会话池"；现有代码：`real_device_client.py` 第 1661-1663 行（TELNET 单会话限制）、第 2088-2126 行（`DeviceToolSession` 上下文管理器）、`switch_diag_tool.py` 第 282-295 行（finally 中 close 会话） |
| 优先级 | Must Have |
| 备注 | 已确认决策 Q-RP-03 / Q-RP-05（RESOLVED）：手动刷新 + 单会话批量采集；复用 `DeviceToolSession`，会话串行化，不做会话池 |

---

## 超出范围（Out of Scope）

| 序号 | 排除项 | 说明 |
|------|--------|------|
| OS-02 | 端口 VLAN / description 变更 | 真实设备面板本需求仅涉及「启用/禁用」写操作（已确认开放），不开放 VLAN 变更、端口描述等更复杂的配置写操作。来源：用户需求仅提到 `shutdown`/`no shutdown`。 |
| OS-03 | 自动轮询 / 后台刷新 | 已确认（Q-RP-03）：手动刷新 + 单会话批量采集，不引入后台定时轮询。 |
| OS-04 | SNMP / NETCONF / RESTCONF 采集 | REAL 面板仅通过 SSH/Telnet CLI 采集，不引入其他网管协议。来源：现有 REAL 连接链路为 SSH/Telnet/HTTP CLI。 |
| OS-05 | 面板数据持久化缓存 | 默认不做面板数据落盘缓存，每次刷新实时采集（除非用户确认）。来源：Demo 定位，实时采集保证数据真实性。 |

> 说明：OS-01「IO 读写速率展示」原为超出范围项，经用户确认（Q-RP-01）已**纳入范围**（见 REQ-RP-FUNC-010），故从本表移除。

---

## 已确认决策（RESOLVED）

| 编号 | 风险 | 问题 | 最终决议（用户已确认） |
|------|------|------|------------------------|
| Q-RP-01 | 低 | REAL 面板信息范围：是否在端口状态/CPU/内存之外，增加「设备基本信息」区块（`show system-info`）？IO 读/写区块无真实 CLI 命令如何处理？ | **RESOLVED**：尽量复刻 SIMULATOR 完整面板——保留「IO 读写」区块（需寻找替代命令或降级展示，不得直接丢弃）；基本信息区块（`show system-info`）默认不纳入，可保留为 Should Have 待架构裁决（低成本增值项），不得作为 Must Have。 |
| Q-RP-02 | **高** | 是否对 REAL 设备开放端口「启用/禁用」写操作？若开放，是否执行 `copy running-config startup-config` 持久化？ | **RESOLVED**：开放写操作——REAL 面板端口提供「启用/禁用」按钮，每次写操作必须前端二次确认 + 写入审计日志（REQ-RP-NFUNC-002 适用）；写操作不做 `copy running-config startup-config` 持久化。 |
| Q-RP-03 | 中 | 面板刷新策略：手动刷新还是自动轮询？单次刷新是否用同一会话批量采集？ | **RESOLVED**：手动刷新 + 单会话批量采集（不做后台自动轮询）。 |
| Q-RP-04 | 中 | 后端端点形式：扩展现有 `/ports`、`/system` 端点使其分支支持 REAL，还是新增 REAL 专用端点？ | **RESOLVED**：交由架构阶段（GROUP_B）裁决（扩展现有 `/api/devices/{id}/ports`、`/system`、`/ports/{name}/config` 使其分支支持 REAL，或新增 REAL 专用端点）。 |
| Q-RP-05 | 中 | 会话复用边界：确认复用 `real_device_client.DeviceToolSession`；串行化策略？ | **RESOLVED**：复用 `real_device_client.DeviceToolSession`，会话串行化（TL-SG5428 TELNET 仅 1 个活动会话），不做会话池。 |

---

## 与现有架构的对齐说明

| 需求 ID | 影响的现有模块/文件 | 变更类型 |
|---------|---------------------|----------|
| REQ-RP-FUNC-001 | `webui/src/views/devices/DevicesListView.vue`（第 57-60 行 REAL 操作列） | 新增按钮 |
| REQ-RP-FUNC-002 | `webui/src/views/devices/DevicesListView.vue`（端口区块） | 新增/复用抽屉 |
| REQ-RP-FUNC-003 | `webui/src/views/devices/DevicesListView.vue`（CPU 区块） | 新增/复用抽屉 |
| REQ-RP-FUNC-004 | `webui/src/views/devices/DevicesListView.vue`（内存区块） | 新增/复用抽屉 |
| REQ-RP-FUNC-005 | `real_device_client.py`（`show system-info` 解析） | 复用解析逻辑 |
| REQ-RP-FUNC-006 | `switch_config_tool.py`（`TpLinkSwitchConfigTool`） / `real_device_client.py`（`configure`） | 复用配置下发能力 |
| REQ-RP-FUNC-007 | `src/api/devices_router.py`（第 660-732 行现有端点） | 扩展或新增端点（形式交 GROUP_B 裁决） |
| REQ-RP-FUNC-008 | `webui/src/views/devices/DevicesListView.vue`、`webui/src/stores/devices.ts` | 新增抽屉 + store 方法 |
| REQ-RP-FUNC-009 | 新增解析模块（或扩展 `real_device_client.py`） | 新模块/扩展 |
| REQ-RP-FUNC-010 | `webui/src/views/devices/DevicesListView.vue`（第 192-199 行 IO 读写区块） | 新增/复用抽屉（降级展示，替代命令交 GROUP_B 裁决） |
| REQ-RP-NFUNC-001 | `webui/src/stores/devices.ts`（超时配置）、`DevicesListView.vue`（loading 反馈） | 配置 + UI |
| REQ-RP-NFUNC-002 | 前端二次确认 + `AuditLogger` | UI + 审计接入 |
| REQ-RP-NFUNC-003 | 现有 SIMULATOR/REAL 端点 | 零变更（约束） |
| REQ-RP-NFUNC-004 | `real_device_client.py`（会话工厂） | 复用 + 串行化约束 |

---

*文档版本 0.2.0 | 状态 APPROVED | 生成时间 2026-09-05 | 作者 sub_agent_requirement_analyst*

<audit_log>
  <log time="2026-09-05T00:00:00Z" state="WRITE_FILES" action="file_write" result="SUCCESS" trace_id="inv-real-panel-a-001" file_path="project_workspace/real_device_panel/requirements/real_panel_requirements_spec.md"/>
  <log time="2026-09-05T00:00:00Z" state="WRITE_FILES" action="file_write" result="SUCCESS" trace_id="inv-real-panel-a-001" file_path="project_workspace/real_device_panel/requirements/real_panel_user_stories.md"/>
  <log time="2026-09-05T02:00:00Z" state="WRITE_FILES" action="file_update" result="SUCCESS" trace_id="inv-real-panel-a-002" file_path="project_workspace/real_device_panel/requirements/real_panel_requirements_spec.md"/>
</audit_log>
