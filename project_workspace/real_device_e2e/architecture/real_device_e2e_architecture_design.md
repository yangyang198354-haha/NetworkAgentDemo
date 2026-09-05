<file_header>
  <project_id>NetworkAgentDemo</project_id>
  <module_id>real_device_e2e</module_id>
  <doc_type>architecture_design</doc_type>
  <file_name>real_device_e2e_architecture_design.md</file_name>
  <version>0.2.0</version>
  <status>APPROVED</status>
  <author_agent>sub_agent_system_architect</author_agent>
  <created_at>2026-09-05T04:00:00Z</created_at>
  <last_updated>2026-09-05T04:00:00Z</last_updated>
  <invocation_id>inv-real-e2e-b-001</invocation_id>
  <input_source>PM agent_invocation — GROUP_B 架构设计（基于 APPROVED 需求 inv-real-e2e-a-002，REAL_DEVICE_E2E）</input_source>
</file_header>

# 真实设备（REAL）端到端工作流 — 架构决策记录（ADR）

## 架构概览

- **架构风格**：模块化分层单体（Modular Layered Monolith）——在既有 FastAPI 单体进程内，为「真实设备端到端闭环」补齐一个工作流层的 REAL 垂直切片，不改动 14 节点 LangGraph 图结构（`state_graph_engine.py` L62-76），不引入微服务边界。
- **选型依据摘要**：
  - REAL 接入上下文（FRP host/port/protocol）在**工作流节点内**解析，复用 `real_device_client._resolve_access`（L408-429）作为唯一 FRP 解析逻辑，回填到 `device_info`（REQ-RE-FUNC-002）。
  - REAL 工具选择走**工作流节点运行时按 device_type 分支**，补齐 `_get_*_tool_for_device` 的 REAL 分支，`main.py:79-80` 的 MOCK 默认注入保持不变（REQ-RE-FUNC-003、REQ-RE-NFUNC-004）。
  - REAL 诊断命令用 device_type 感知映射 + 复用 `real_panel_parsers.py` 结构化解析（REQ-RE-FUNC-004）。
  - CPU_HIGH / MAC_FLAPPING 修复走**双分支降级**：等价命令存在才补 TP-Link 模板，否则降级为「真实诊断 + 告警闭环、修复降级」（REQ-RE-FUNC-005/008、RISK-RE-01）。
  - REAL 验证从关键词匹配改为结构化解析（`parse_interface_status` 的 Status 列）（REQ-RE-FUNC-006）。
  - **零新增 Python/Node 依赖**：全部复用既有运行时、`real_device_client`、`real_panel_parsers`、`real_session_gate`、`AuditLogger`、stdlib。

---

## 架构决策记录（ADRs）

---

### ADR-RE-001（ADR-FRP）: REAL 接入 FRP 解析落点（裁决 REQ-RE-FUNC-002）

- **Status**: Accepted
- **Context**:
  - REQ-RE-FUNC-002 要求 `establish_ssh → collect_diag → execute_fix → verify_fix` 在 REAL 设备上通过 FRP 隧道（`frp_proxy_host=127.0.0.1`、`frp_proxy_port=6022` → 局域网 `192.168.31.220`，协议 SSH）真实到达交换机，而非用告警携带的默认 `device_ip`（如 `192.168.1.1`）直连默认 22 端口。
  - 现状缺口（只读事实）：`handle_collect_diag` L483 用 `device_ip = device_info.get("device_ip", "192.168.1.1")`；`handle_execute_fix` L870 / `handle_verify_result` L928 同理；`_extract_auth` L1086-1093 只取 `username/password/enable_password/port`，不设 `protocol`、不解析 FRP；`handle_get_device_info` L430-451 只回填 username/password 与默认 model/ip，不回填 frp/protocol；`src/models/alert.py` `DeviceInfo`（L30-38）无 frp 字段；`TpLinkSwitchDiagTool._run`（`switch_diag_tool.py` L260-271）与 `TpLinkSwitchConfigTool._run`（`switch_config_tool.py` L159-171）用 `_SshSession(device_ip, port, username, password)` 直连，仅取 auth.port/protocol，不解析 FRP。
  - FRP 数据源：`src/database/device_models.py` `Device` 表有 `connection_protocol`（L48-51）、`frp_proxy_host`（L52-55）、`frp_proxy_port`（L56-59）；`real_device_client._resolve_access(device)`（L408-429）已实现「frp_proxy_host/port 非空则走 FRP，否则 device_ip + cred.ssh_port」。
- **Options**:
  - Option A: 工作流节点内解析——`handle_get_device_info`（或等价新步骤）按 `device_name` 从 DeviceRepository/DB 取 Device 对象，调用 `_resolve_access(device)` 得到 `(host, port, protocol)`，回填 `device_info`（`device_ip=host`、`port=port`、`protocol=protocol`、`frp_proxy_host/frp_proxy_port` 作为附加键）；`_extract_auth` 透传 `port` + `protocol`。
    - 优点: 工具层（TpLink*Tool）**零改动**（继续消费 `device_ip` + `auth.port` + `auth.protocol`，现签名不变）；复用 `_resolve_access` 避免在节点重写 FRP 逻辑（单一来源）；与 `_resolve_simulator_connection`（node_handlers L113-167）已有的「节点查 DB + 回填接入参数」模式一致；附带收益是 `session_guard_by_access(host,port,protocol)` 的 key 与面板 `session_key`（`_resolve_access` 结果）对齐，关闭 ADR-RP-003 开放问题。
    - 缺点: `handle_get_device_info` 需新增 DB 查询（`SessionLocal` + `DeviceRepository`）；REAL 接入字段需在 `device_info` dict 中承载（不改 `alert.DeviceInfo` pydantic 模型，避免破坏序列化）。
  - Option B: `_extract_auth` 内解析——把 FRP 解析下沉到 `_extract_auth`（L1086-1093）。
    - 优点: 调用点（collect_diag/execute_fix/verify_fix）改动最小，统一在 `_extract_auth` 一处补齐。
    - 缺点: `_extract_auth` 是 `@staticmethod`，仅接收 `device_info: dict`，无 DB Session、无 device_name 到 Device 的映射能力；FRP 数据在 DB 不在 dict 里，**无法独立完成解析**，仍需上游先查 DB 注入，本质退化为 Option A 的前置 + 自身只做透传。不满足「单一责任」。
  - Option C: 工具层 `TpLink*Tool._run` 内解析——工具拿到 FRP 后自行 `_resolve_access`。
    - 优点: 工具是最终建立会话的地方，解析点离使用点最近。
    - 缺点: `_run` 签名只收 `device_ip: str`（无 device 对象），要解析必须改签名（新增 device 对象或 device_name 参数）并引入 DB 依赖；工具层职责从「按给定 host/port/protocol 开会话」膨胀为「设备接入上下文解析」，破坏策略模式的单一职责；且三处 `_run`（diag/config）+ 工厂都要动，blast radius 最大。
  - Option D: 统一走 `DeviceToolSession._resolve_access`——工具改用 `DeviceToolSession(device, ...)`（其 `__init__` L2093-2094 已调 `_resolve_access`）。
    - 优点: FRP 解析 + 会话工厂 + 优先会话链（Windows OpenSSH→plink→paramiko，`_open_ssh_session` L2130-2168）一体化，单一来源最彻底。
    - 缺点: `DeviceToolSession` 需 device 对象，而 `_run` 只收 `device_ip: str`，仍需改工具签名 + 从 DB 取 Device；改动工具层 + 节点层两层，对 REQ-RE-NFUNC-004「零回归」风险最大；且当前 TpLink*Tool 用的是 `_SshSession`/`_TelnetSession` 直连（不是 `DeviceToolSession`），改为 DeviceToolSession 属会话实现替换，超出 FRP 定位。
- **Decision**: 采用 **Option A（工作流节点内解析 + 复用 `_resolve_access`）**。
  - 落点：`handle_get_device_info`（node_handlers L430-451）对 `device_type == "REAL"` 走新分支——按 `device_name` 经 `SessionLocal` + `DeviceRepository.list_devices()`（或新增 `get_by_name` 查询）取 Device 对象，调用 `real_device_client._resolve_access(device)` 得 `(host, port, protocol)`，回填 `device_info`：`device_ip=host`、`port=port`、`protocol=protocol`、`device_model=device.device_model or "TL-SG5428"`、`frp_proxy_host/frp_proxy_port` 作为附加键。`_extract_auth` 仅增加一行 `protocol=device_info.get("protocol")` 透传（`port` 已透传）。
  - data 从哪来：FRP/协议/真实型号均来自 `devices` 表（`DeviceRepository`），**不在** `alert.DeviceInfo` pydantic 模型加字段，而是以 `device_info` dict 附加键承载，避免改动告警序列化契约。
  - 理由：Option A 是唯一「工具零改动 + FRP 单一来源 + 复用既有 DB 查询模式」三者兼得的方案；Option B 无法独立完成（无 DB 能力），Option C/D 需改工具签名、引入工具层 DB 依赖与两层改动，违反 NFUNC-004 最小改动。复用 `_resolve_access` 而非重写，保留 Option D 的「单一来源」收益，却不触发工具层改动。
- **Consequences**:
  - 正向: 满足 REQ-RE-FUNC-002（REAL 经 FRP 到达）；工具层与 `session_guard_by_access` key 对齐面板 `session_key`（关闭 ADR-RP-003 开放问题）；`alert.DeviceInfo` 模型不动（序列化契约稳定）。
  - 负向: `handle_get_device_info` 增加 DB 查询路径（REAL 才触发，MOCK/SIMULATOR 走原路径零影响）；[实现校准] TpLink*Tool 目前用 `_SshSession`（paramiko fallback）直连，对 TL-SG5428 的 DSA KEX 在 Windows 上可能被拒（`real_device_client.py` L380-382 注释），建议实现阶段优先复用 `_open_ssh_session`/`_open_telnet_session`（面板已验证）会话链，本 ADR 不强制改工具（见开放问题 1）。

---

### ADR-RE-002（ADR-TOOL）: REAL 工具选择落点（裁决 REQ-RE-FUNC-003）

- **Status**: Accepted
- **Context**:
  - REQ-RE-FUNC-003 要求 `device_type == "REAL"` 时诊断/配置节点必须选真实 `TpLinkSwitchDiagTool`/`TpLinkSwitchConfigTool`，不落 Mock；`establish_ssh` 也应真实校验可达性。
  - 现状缺口：`_get_diag_tool_for_device`/`_get_config_tool_for_device`（node_handlers L169-183）只对 `device_type == "SIMULATOR"` 分支，其余（含 REAL）返回注入的 `self.switch_diag_tool`/`self.switch_config_tool`；`_execute_single_command`（L1140-1177）也只分支 SIMULATOR；`main.py:79-80` 用 `create_switch_*_tool(use_mock=True)` 默认注入 Mock；`handle_establish_ssh`（L455-471）仅打印 Mock 日志。
  - 工厂已支持 REAL：`create_switch_diag_tool`（switch_diag_tool L316-339）与 `create_switch_config_tool`（switch_config_tool L206-229）`device_type == "REAL"` 已返回 TpLink 工具。
- **Options**:
  - Option A: 工厂按 device_type 注入——`main.py` 启动时按 device_type 预建多实例并注入 NodeHandlers。
    - 优点: 工具实例在启动期确定，节点层零分支。
    - 缺点: `device_type` 是**每告警运行时**决定的（告警携带），非启动期全局量；单例 `NodeHandlers` 无法按告警动态换注入实例，除非维护 `{device_type → tool}` 注册表 + 节点查找，本质仍是运行时分支，只是挪到工厂层；且无法覆盖 `_execute_single_command` 的 SIMULATOR 分支语义。不解决 `main.py:79-80` 的 MOCK 默认与「REAL 告警必须真实执行」之间的矛盾（单实例只能有一个 device_type）。
  - Option B: 工作流节点运行时按 device_type 分支——扩展 `_get_diag_tool_for_device`/`_get_config_tool_for_device`（及 `_execute_single_command`）增加 `device_type == "REAL"` 分支，返回 `create_switch_diag_tool(device_type="REAL")` / `create_switch_config_tool(device_type="REAL")`（或直接 `TpLinkSwitchDiagTool()`/`TpLinkSwitchConfigTool()`，与现有 SIMULATOR 分支直接 import 的写法一致）。
    - 优点: 与既有 SIMULATOR 分支模式完全同构；`main.py:79-80` 的 MOCK 注入保持不动 → MOCK 告警路径零回归（NFUNC-004）；REAL 告警在节点运行时被真实工具覆盖，天然满足「REAL 不落 Mock」；工厂的 REAL 分支被复用（单一策略点）。
    - 缺点: 每次 REAL 告警在节点内 new 一个 TpLink*Tool 实例（轻量、无状态，与 SIMULATOR 分支 `SimulatorDiagTool()` 同开销，可接受）。
- **Decision**: 采用 **Option B（运行时按 device_type 分支，复用工厂 REAL 分支）**。
  - 落点：`_get_diag_tool_for_device`/`_get_config_tool_for_device`/`_get_backup_tool_for_device`（L169-191）与 `_execute_single_command`（L1140-1177）新增 `elif device_type == "REAL": return create_switch_diag_tool(device_type="REAL")` 等分支（或直接 `TpLink*Tool()`）；`handle_establish_ssh` 对 REAL 走「解析后接入上下文的可达性校验（TCP + 协议握手）」而非仅 Mock 日志。
  - 对 `main.py:79-80` 的回应：**不改** `use_mock=True` 默认注入——它仍作为 MOCK/SIMULATOR 与「未匹配 device_type」的兜底，保证 NFUNC-004 零回归；REAL 由运行时分支覆盖，无需在启动期引入多实例注入。
  - 理由：`device_type` 是运行时量，Option A 无法在启动期静态注入单实例下满足「REAL 真实执行 + MOCK 默认不变」；Option B 复用既有 SIMULATOR 分支模式 + 工厂 REAL 分支，是最小改动且严格不破坏 MOCK 路径。
- **Consequences**:
  - 正向: 满足 REQ-RE-FUNC-003；MOCK/SIMULATOR 路径零回归（NFUNC-004）；工厂 REAL 分支得到复用。
  - 负向: REAL 告警每次在节点内实例化工具（可接受，无状态）；`establish_ssh` 的 REAL 可达性校验需接入 `_resolve_access` 后的 host/port/protocol（依赖 ADR-RE-001 回填）。

---

### ADR-RE-003（ADR-CMDMAP）: REAL 诊断命令映射与解析（裁决 REQ-RE-FUNC-004）

- **Status**: Accepted
- **Context**:
  - REQ-RE-FUNC-004 要求 REAL 设备诊断用已校准 TL-SG5428 命令（`show interface status`、`show cpu-utilization`、`show memory-utilization`、`show system-info`），非 Cisco/Mock 命令（`show mac address-table`、`show processes cpu`、`show processes cpu history`、`show logging`）；输出用 `real_panel_parsers.py` 结构化解析，失败返回明确错误。
  - 现状缺口：`DIAG_COMMAND_MAP`（node_handlers L48-61）为 Cisco/Mock 命令，**缺 `PORT_SHUTDOWN` 键**；CPU_HIGH → `show processes cpu`/`show processes cpu history`（TL-SG5428 无）；MAC_FLAPPING → `show mac address-table`/`show logging`（Cisco 风格，未验证 TL-SG5428 等价）；Mock 命令表（switch_diag_tool L178-187）。
  - 已有解析能力：`real_panel_parsers.parse_interface_status`（L90-145，含 TL-SG5428 列式 `_parse_real_speed_port_line` L173-189）、`parse_cpu_utilization`（L230）、`parse_memory_utilization`（L276）、`parse_system_info`（L343）。
- **Options**:
  - Option A: 引入 device_type 感知的命令解析函数——新增 `get_diag_commands(alert_type, device_type)`，REAL 走 TP-Link 命令集，MOCK/SIMULATOR 走原 `DIAG_COMMAND_MAP`（逐字不变）。
    - 优点: MOCK/SIMULATOR 映射零改动（NFUNC-004）；REAL 命令集集中、可单独测试；`DIAG_COMMAND_MAP` 作为默认值保留（向后兼容）。
    - 缺点: 新增一个解析函数（而非原地改 dict）。
  - Option B: 原地改 `DIAG_COMMAND_MAP` 为「双键」或全局替换命令。
    - 优点: 单一 dict。
    - 缺点: 会把 MOCK/SIMULATOR 也改成 TP-Link 命令，破坏 `MockSwitchDiagTool._MOCK_RESPONSES` 与 SIMULATOR 工具（它们认 Cisco 风格命令），违反 NFUNC-004；无法表达「同一 alert_type 在不同 device_type 用不同命令」。
- **Decision**: 采用 **Option A（device_type 感知映射 + 复用 real_panel_parsers）**。
  - REAL 命令集（已校准，来自 REQ-RE-FUNC-004）：
    - `PORT_DOWN` → `["show interface status"]`
    - `PORT_SHUTDOWN` → `["show interface status"]`（补齐缺失键）
    - `CPU_HIGH` → `["show cpu-utilization", "show memory-utilization"]`（只读；`show processes cpu` 不可用）
    - `MAC_FLAPPING` → `["show interface status", "show mac address-table"]`（只读；探测已核实 TL-SG5428 用**空格版** `show mac address-table` 可用，返回 MAC/VLAN/Port/Type/Aging 表；**连字符版** `show mac-address-table` 报 "Invalid parameter"）
  - 解析落点：collect_diag/verify_fix 对 REAL 调用 `parse_interface_status`/`parse_cpu_utilization`/`parse_memory_utilization` 将原始文本转结构化，供 analyze_root_cause/verify 使用；解析抛 `RealPanelError` 时**返回明确错误而非错误数据**（AC-RE-002-02）。
  - 理由：Option A 是唯一能同时满足「REAL 用 TP-Link 命令 + MOCK/SIMULATOR 命令零改动」的方案；Option B 会把 Cisco 命令替换传染到 MOCK/SIMULATOR，破坏 NFUNC-004。
- **Consequences**:
  - 正向: 满足 REQ-RE-FUNC-004 与 AC-RE-002-02；MOCK/SIMULATOR 命令映射零回归；结构化解析复用上一轮 `real_panel_parsers`（无新解析代码）。
  - 负向: 新增 `get_diag_commands` 解析函数；MAC_FLAPPING 的 REAL 只读诊断命令受限于「未验证 MAC 表命令」，本轮以 `show interface status` 为基线（配合 ADR-RE-004 的降级语义）。

---

### ADR-RE-004（ADR-FIXTPL）: 四类告警修复模板与 CPU/MAC 双分支降级（裁决 REQ-RE-FUNC-005/008 + RISK-RE-01）

- **Status**: Accepted
- **Context**:
  - REQ-RE-FUNC-005 要求四类告警（PORT_DOWN/PORT_SHUTDOWN/CPU_HIGH/MAC_FLAPPING）在 REAL 上都有 TP-Link 可用修复模板；`description <desc>` 默认不纳入（Q-RE-02）。
  - REQ-RE-FUNC-008 + RISK-RE-01：CPU_HIGH/MAC_FLAPPING 的 TP-Link 真实修复命令存在性未知；当前 Cisco 模板 `tpl_cpu_rate_limit.yaml`（CoPP `policy-map`/`class-map`）与 `tpl_mac_port_security.yaml`（`switchport port-security`）在 TL-SG5428 不可用；若无等价命令 → 降级为「真实诊断 + 告警闭环、修复降级」，严禁凭空承诺。
  - 现状：`_get_default_template`（node_handlers L1108-1116）将 CPU_HIGH → `TPL-CPU-RATE-LIMIT`、MAC_FLAPPING → `TPL-MAC-PORT-SECURITY`（Cisco 不可用）；`tpl_port_enable.yaml`/`tpl_port_disable.yaml` 模板含 `description {{ desc }}` 行（Q-RE-02 要求不纳入）。
- **Options**:
  - Option A: 双分支能力裁决（修复能力注册表 + 降级）——按 `device_type`/`alert_type` 裁决「可修复 FIXABLE / 降级 DEGRADED」，默认 CPU_HIGH/MAC_FLAPPING 在 REAL 下为 DEGRADED，待只读探测核实等价命令后升为 FIXABLE。
    - 优点: 确定性满足「不凭空承诺不可实现修复」；`_get_default_template` 不再对 REAL CPU/MAC 返回 Cisco 模板；降级路径（commands=[] + 报告标注）结构化、可测试；等价命令核实后仅改注册表 + 补模板即可升级，不改契约。
    - 缺点: 需新增一个能力裁决点 + 降级 FixPlan 构造；等价命令候选未核实前 CPU/MAC 无法「真实修复」闭环（属需求已确认的 RISK 范围）。
  - Option B: 直接补 TP-Link 模板并写死为已确认能力。
    - 优点: 表面满足「四类都有 TP-Link 修复」。
    - 缺点: 候选命令（storm-control / 端口安全 / CPU 限速）**未经真实设备核实**，写死即违反 REQ-RE-FUNC-008「严禁架构阶段凭空承诺」与 RISK-RE-01 缓解要求，可能下发出 `unknown command` 甚至误操作生产端口。不可接受。
- **Decision**: 采用 **Option A（双分支能力裁决，默认 CPU/MAC 降级）**。
  - PORT 类（已可用，REQ-RE-FUNC-005）：
    - PORT_DOWN → `TPL-PORT-ENABLE`（`configure` → `interface <port>` → `no shutdown` → `exit`）；模板**删除** `description {{ desc }}` 行（Q-RE-02）。
    - PORT_SHUTDOWN → `TPL-PORT-DISABLE`（`configure` → `interface <port>` → `shutdown` → `exit`）；属隔离场景、更高授权、**不作默认修复动作**（REQ-RE-NFUNC-002）；模板同样删除 `description` 行。
  - CPU_HIGH / MAC_FLAPPING（双分支已定稿 → DEGRADED）：
    - **只读探测结论（2026-09-05，用户已授权）**：TL-SG5428 接口级命令集（`interface gigabitEthernet 1/0/2` → `?`）与全局级（`configure` → `?`）枚举后**无 `port-security`**（`port` 为 "Port isolation" 端口隔离，非端口安全）、**无 CoPP/`policy-map`/`class-map`**、**无 CPU 保护命令**、**无 `storm-control`**；仅 `bandwidth`（端口限速，非 CPU 保护）与 `loopback-detection`（环路检测，非 CPU/MAC 修复）。故 **CPU_HIGH / MAC_FLAPPING 均无可核实的 TP-Link 等价修复命令**，据实判定 **DEGRADED**（REQ-RE-FUNC-008 / RISK-RE-01 缓解落地）。
    - **降级语义（最终）**：`generate_fix_plan` 对 REAL 下 CPU_HIGH/MAC_FLAPPING 产出 `FixPlan(commands=[], description="修复降级：该告警类型在 TL-SG5428 无已核实 CLI 修复能力")`，`execute_fix` **不下发任何命令**，`finish_report` 明确标注「修复降级/不可修复」；诊断/根因/报告仍真实执行。
  - 能力裁决实现载体：`resolve_fix_capability(alert_type, device_type) -> FIXABLE | DEGRADED`，REAL 下为**固定常量注册表**：PORT_DOWN/PORT_SHUTDOWN = FIXABLE；CPU_HIGH/MAC_FLAPPING = DEGRADED（探测已核实无等价命令，无需运行时升级）。
  - 理由：Option B 把「待核实候选」当「已确认能力」写死，直接违反 REQ-RE-FUNC-008 硬约束与 RISK-RE-01 缓解要求；Option A 以「能力注册表 + 降级」把不确定性结构化收口，且降级路径不触碰生产端口（无写命令），符合 REQ-RE-NFUNC-002 可逆/安全优先。
- **Consequences**:
  - 正向: 满足 REQ-RE-FUNC-005（PORT 类 TP-Link 可用、去 description）、REQ-RE-FUNC-008（双分支、不凭空承诺）、REQ-RE-NFUNC-002（shutdown 更高授权、description 不纳入）；降级路径不下发命令，生产安全。
  - 负向: CPU_HIGH/MAC_FLAPPING 已核实无等价命令，**最终判定 DEGRADED**（真实诊断 + 告警闭环、修复降级），报告标注「修复降级/不可修复」；候选清单经只读探测定稿（开放问题 3 已 RESOLVED）。

---

### ADR-RE-005（ADR-VERIFY）: REAL 验证判定结构化（裁决 REQ-RE-FUNC-006）

- **Status**: Accepted
- **Context**:
  - REQ-RE-FUNC-006 要求 `verify_fix` 基于真实 TL-SG5428 `show interface status` 的 Status 列（Enable/Disable 或 up/down）判定，而非 Cisco 关键词 `["down","notconnect"]`；可复用 `real_panel_parsers.parse_interface_status`。
  - 现状缺口：`handle_verify_result`（L920-999）用 `alert_keywords`（L962-966）对裸文本做关键词匹配（PORT_DOWN → ["down","notconnect"]、CPU_HIGH → ["92%","CPU utilization.*high"]），且 `MAC_FLAPPING` 关键词与 `PORT_SHUTDOWN` 缺失；`commands[:1]`（L943）只重跑首条命令。
- **Options**:
  - Option A: 结构化验证——REAL 下用 `parse_interface_status` 解析 before/after 输出，按目标端口的 Status 字段判定（down→up / up→down），CPU/MAC 按对应分支口径。
    - 优点: 判定基于真实 Status 列，满足 AC-RE-004-01；解析复用 `real_panel_parsers`；MOCK/SIMULATOR 保留原关键词逻辑（NFUNC-004）。
    - 缺点: 需新增结构化比较函数 + 目标端口定位（从 `device_info.interface_name`）。
  - Option B: 仅扩关键词清单（新增 "enable"/"disable"）继续关键词匹配。
    - 优点: 改动最小。
    - 缺点: 关键词匹配对 TP-Link 列式输出脆弱（`parse_interface_status` 已实现列式解析，弃用属倒退）；无法精确定位「目标端口」的修复前后状态（可能误判其它端口），违反 REQ-RE-FUNC-006 与 AC-RE-004-01。
- **Decision**: 采用 **Option A（结构化验证，复用 parse_interface_status）**。
  - 判定口径：
    - PORT_DOWN：`parse_interface_status` 定位 `interface_name` 端口，before Status ∈ {down, notconnect} → after Status == up ⇒ 通过。
    - PORT_SHUTDOWN：before Status == up → after Status ∈ {down} ⇒ 通过（隔离成功语义）。
    - CPU_HIGH：`parse_cpu_utilization` 取 before/after `cpu_5s`，after 低于阈值 ⇒ 通过（阈值见 Q-RE-04 待确认）；若 DEGRADED（无修复）则 verify 返回「不可修复」而非通过。
    - MAC_FLAPPING：本轮无已验证 MAC 表命令，若 DEGRADED 则 verify 返回「不可修复」；若有只读命令则按对应解析器比较（【待核实】）。
  - 落点：新增 `verify_real_fix(alert_type, before_text, after_text, target_port) -> VerifyResult`；`handle_verify_result` 对 REAL 走此函数，MOCK/SIMULATOR 保留 L962-970 原关键词逻辑逐字不变。
  - 理由：Option A 精准定位目标端口、基于真实 Status 列，是唯一满足 REQ-RE-FUNC-006/AC-RE-004-01 且复用上一轮解析器的方案；Option B 是关键词匹配的脆弱变体，属倒退。
- **Consequences**:
  - 正向: 满足 REQ-RE-FUNC-006 与 AC-RE-004-01；MOCK/SIMULATOR 验证逻辑零回归；验证可回填结构化 before/after 状态到报告。
  - 负向: 新增 `verify_real_fix` 比较函数；CPU_HIGH 阈值、MAC 只读命令仍受 Q-RE-04/[待核实] 约束。

---

### ADR-RE-006（ADR-SEC）: 凭据与写操作安全（裁决 REQ-RE-NFUNC-001/002/003）

- **Status**: Accepted
- **Context**:
  - REQ-RE-NFUNC-001: REAL 凭据走 `DEVICE_<NAME>_PASSWORD` 环境变量 / DB Fernet 解密，**禁用** `get_device_credentials` 兜底 `admin123`（config_manager L161 `pwd or "admin123"`、L170 fallback `admin123`）。
  - REQ-RE-NFUNC-002: REAL 写操作需单独授权 + 指定测试端口 `Gi1/0/2`；`no shutdown` 默认可逆、`shutdown` 更高授权不作默认；`description` 不纳入；不调 `save()`（`real_device_client.save()` L1226-1238）；审计不落明文密码。
  - REQ-RE-NFUNC-003: 会话复用 `real_session_gate` 串行化 + finally 关闭 + 超时（TpLink*Tool 已包裹 `session_guard_by_access`，switch_diag_tool L266-267、switch_config_tool L165-166）。
- **Options**:
  - Option A: REAL 凭据强制走 env/DB Fernet，缺失即失败；写操作走「授权端口白名单 + 审计 + 不 save」。
    - 优点: 满足 NFUNC-001/002 全部硬约束；REAL 路径不触碰 `admin123`；写操作结构上不持久化。
    - 缺点: 需在 REAL 接入解析点显式校验凭据来源并拒绝兜底。
  - Option B: 沿用 `get_device_credentials` 现有兜底逻辑。
    - 优点: 零改动。
    - 缺点: 违反 REQ-RE-NFUNC-001（`admin123` 兜底不得作为 REAL 生产凭据来源）与 AC-RE-006-01，不可接受。
- **Decision**: 采用 **Option A**。
  - 凭据（REQ-RE-NFUNC-001）：REAL 接入解析（ADR-RE-001）读取凭据时，仅接受 `DEVICE_<NAME>_PASSWORD` 环境变量或 DB Fernet 解密结果；若两者均无，则 `establish_ssh`/`collect_diag` 返回明确错误「REAL 凭据未配置，禁止使用 admin123 兜底」，工作流 FAILED 而非落 Mock/admin123。
  - 写操作（REQ-RE-NFUNC-002）：`execute_fix` 对 REAL 下发前校验目标端口 ∈ 授权白名单（默认 `{Gi1/0/2}`）；`shutdown` 动作要求 `assess_risk` 触发 `human_approval` 更高授权（沿用既有 Interrupt 流程），不作默认修复动作；**不调用 `save()`**、**不下发 `description <desc>`**；审计日志（`AuditLogger.log_audit_event`，复用 execute_fix L887-898 已有调用）`detail` 仅含 device/port/action/success/message，不含 password。
  - 会话（REQ-RE-NFUNC-003）：复用 `real_session_gate`（session_guard_by_access）+ TpLink*Tool 既有 finally 关闭；单次诊断同会话批量多条 show。
  - 理由：Option B 直接违反 NFUNC-001 强制项；Option A 是唯一满足三条安全红线的方案。
- **Consequences**:
  - 正向: NFUNC-001/002/003 全覆盖；REAL 无 admin123 兜底、无持久化、无明文密码入审计。
  - 负向: REAL 凭据缺失将导致工作流失败（符合安全优先）；`shutdown` 需二次审批，增加交互（符合更高授权约束）。

---

### ADR-RE-007（ADR-ALERT）: 模拟告警真实性回填（裁决 REQ-RE-FUNC-001）

- **Status**: Accepted
- **Context**:
  - REQ-RE-FUNC-001 要求模拟告警反映真实硬件（真实端口 `Gi1/0/x`、真实型号 `TL-SG5428`、真实 FRP/局域网地址），而非 MOCK 假端口/假型号/默认 IP。
  - 现状：`alerts_router.py` `SimulateAlertRequest`（L23-29）`interface` 默认 `Gi0/1`、`device_ip` 默认 `192.168.1.1`；L239 `device_model` 硬编码 `"TP-Link T2600G-28TS"`；L212 CPU_HIGH 描述硬编码 `92%...80%`；L219-230 已按 device_name 查 DB 得 `device_type`。
  - 边界口径（Q-RE-06 建议最小改动：调用侧传真实参数，自动回填交 GROUP_B）。
- **Options**:
  - Option A: simulate 端点按 device_name 回填真实元数据——复用 L219-230 已查到的 Device 记录，回填 `device_ip`（FRP/局域网）、`device_model`（真实型号）、`interface`（真实端口），调用侧未传时自动补全。
    - 优点: 告警真实性自动保证（AC-RE-001-01/02）；与 L219-230 现有 DB 查询合并，改动集中。
    - 缺点: 需扩展 simulate 的 Device 查询回填逻辑；CPU_HIGH 阈值描述仍受 Q-RE-04 约束。
  - Option B: 仅靠调用侧传真实参数，后端零回填。
    - 优点: 后端零改动。
    - 缺点: 告警真实性依赖调用方自觉，易误发假参数（违背 AC-RE-001-01/02 的「告警接口字段使用真实命名」验收）；`device_ip` 默认 `192.168.1.1` 仍会落入告警。
- **Decision**: 采用 **Option A（simulate 端点按 device_name 回填真实元数据，调用侧传参优先）**。
  - 落点：`alerts_router.simulate_alert` 在 L219-230 已取得的 Device 记录基础上，若 `body.device_type` 解析为 REAL，则用 `device.device_model`、`device.device_ip`/`frp_proxy_*` 回填 `DeviceInfo`；`interface` 未显式传入时用真实端口（默认测试端口 `Gi1/0/2`，Q-RE-01）；调用侧显式传参优先于回填（保持测试灵活性）。
  - 理由：Option A 让「告警真实性」由后端确定性保证（对齐 AC-RE-001-01/02），同时保留调用侧覆盖能力；Option B 把正确性责任完全外推给调用方，且默认假参数仍在，不满足验收。
- **Consequences**:
  - 正向: 满足 REQ-RE-FUNC-001 与 AC-RE-001-01/02；与 ADR-RE-001 的 FRP 回填形成闭环（告警真实 → 接入真实）。
  - 负向: simulate 端点需扩展 Device 回填；CPU_HIGH 的百分比/阈值描述仍依赖 Q-RE-04 确认。

---

## 开放问题

1. **[实现校准 — 会话链]** TpLink*Tool（`switch_diag_tool.py` L270、`switch_config_tool.py` L169）当前用 `_SshSession`（paramiko fallback）直连，对 TL-SG5428 的 ssh-dss/DSA KEX 在 Windows 可能被拒。建议实现阶段复用面板已验证的 `_open_ssh_session`/`_open_telnet_session` 会话链（`real_device_client.py` L2130-2168，Windows OpenSSH→plink→paramiko），但不强制（本 ADR 不预设工具层改动）。
2. **[RESOLVED — 已只读探测核实]** MAC_FLAPPING 的 TL-SG5428 只读 MAC 表命令 = 空格版 `show mac address-table`（连字符版 `show mac-address-table` 报 Invalid parameter）；REAL MAC 诊断命令定为 `["show interface status", "show mac address-table"]`。
3. **[RESOLVED — 已只读探测核实]** CPU_HIGH/MAC_FLAPPING 的 TP-Link 等价修复命令**不存在**（无 port-security / 无 CoPP / 无 storm-control / 无 CPU 保护命令，仅 `bandwidth` 端口限速 + `loopback-detection` 环路检测）。据此 CPU_HIGH/MAC_FLAPPING 在 REAL 下定稿为「真实诊断 + 告警闭环、修复降级」（DEGRADED）。
4. **[Q-RE-04 待确认]** CPU_HIGH 判定阈值与告警描述（`alerts_router.py` L212 硬编码 92%/80%）待确认，影响 ADR-RE-005 的 CPU 验证口径与 ADR-RE-007 的回填文案。

---

*文档版本 0.2.0 | 状态 APPROVED | 生成时间 2026-09-05 | 作者 sub_agent_system_architect*

<audit_log>
  <log time="2026-09-05T04:00:00Z" state="WRITE_FILES" action="file_write" result="SUCCESS" trace_id="inv-real-e2e-b-001" file_path="project_workspace/real_device_e2e/architecture/real_device_e2e_architecture_design.md"/>
</audit_log>
