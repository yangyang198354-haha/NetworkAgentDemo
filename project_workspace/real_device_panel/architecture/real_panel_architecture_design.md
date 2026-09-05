<file_header>
  <project_id>NetworkAgentDemo</project_id>
  <module_id>real_device_panel</module_id>
  <doc_type>architecture_design</doc_type>
  <file_name>real_panel_architecture_design.md</file_name>
  <version>0.1.0</version>
  <status>APPROVED</status>
  <author_agent>sub_agent_system_architect</author_agent>
  <created_at>2026-09-05T00:00:00Z</created_at>
  <last_updated>2026-09-05T00:00:00Z</last_updated>
  <invocation_id>inv-real-panel-b-001</invocation_id>
  <input_source>PM agent_invocation — GROUP_RP_B 架构设计（基于 APPROVED 需求 inv-real-panel-a-002，REAL_DEVICE_PANEL）</input_source>
</file_header>

# 真实设备（REAL）面板 — 架构决策记录（ADR）

## 架构概览

- **架构风格**：模块化分层单体（Modular Layered Monolith）——在既有 FastAPI 单体进程内，新增一个轻量的「REAL 面板」垂直切片（API 端点 → 服务编排 → CLI 解析 → 会话串行化门），不改动既有分层模型，也不引入微服务边界。
- **选型依据摘要**：
  - 复用 `real_device_client.DeviceToolSession` + `_resolve_access`（FRP 穿透）作为唯一会话工厂（REQ-RP-NFUNC-004、REQ-RP-FUNC-007）。
  - 只读面板采用**单会话批量采集聚合端点**（REQ-RP-NFUNC-004「单会话批量下发多条 show 命令」、Q-RP-03）。
  - 端口写操作复用既有 `configure()` 路径（`configure` → `interface <name>` → `shutdown`/`no shutdown` → `exit`），**不调用 `save()`**（REQ-RP-FUNC-006）。
  - 会话并发通过 per-device `threading.Lock` 串行化门统一管理（REQ-RP-NFUNC-004、Q-RP-05）。
  - **零新增 Python/Node 依赖**：全部复用 FastAPI / real_device_client / Vue3 + Element Plus / AuditLogger / stdlib。

---

## 架构决策记录（ADRs）

---

### ADR-RP-001: 后端端点形式（裁决需求层开放项 Q-RP-04）

- **Status**: Accepted
- **Context**:
  - REQ-RP-FUNC-007 要求「为 REAL 提供面板数据获取能力（端口/CPU/内存/IO 降级 + 可选基本信息）」，并明确端点形式交由架构阶段（GROUP_B）裁决（Q-RP-04 RESOLVED）。
  - REQ-RP-NFUNC-003 约束「新增 REAL 面板不得破坏 SIMULATOR 面板行为、REAL 心跳/连通性端点、`/check_connectivity` 返回字段」。
  - REQ-RP-NFUNC-004 + Q-RP-03 约束「手动刷新 + 单会话批量采集（复用同一会话批量下发多条 show 命令，避免多次会话建立）」，且 Q-RP-05 明确「不做会话池」。
  - 现状：`devices_router.py` 第 660-732 行 `/ports`、`/system`、`/ports/{name}/config` 对非 SIMULATOR 返回「仅适用于模拟器设备」；真实会话建立需 20-40s（SSH 登录 30-60s，REQ-RP-NFUNC-001）。
- **Options**:
  - Option A: 扩展现有三个端点 `/ports`、`/system`、`/ports/{name}/config` 使其 `device_type == REAL` 时分支到 REAL 采集逻辑。
    - 优点: URL 统一、前端 store 方法（`getDevicePorts`/`getDeviceSystem`/`configurePort`）可直接复用、SIMULATOR 分支零改动（天然满足 NFUNC-003）。
    - 缺点: 一次完整面板刷新需 `/ports` + `/system` 两次 HTTP 请求 = 两次独立会话建立（各 20-40s），**违反 Q-RP-03/NFUNC-004「单会话批量采集、避免多次会话建立」**；而 Q-RP-05「不做会话池」又排除了后端跨请求复用会话的补救手段。
  - Option B: 新增 REAL 专用端点。
    - B1: 新增一个聚合只读端点 `GET /api/devices/{id}/real_panel`（单会话批量下发 `show interface status` + `show cpu-utilization` + `show memory-utilization` [+ `show system-info`]），写操作扩展现有 `POST /ports/{name}/config` 分支支持 REAL。
    - B2: 新增三个 REAL 专用端点 `/real/ports`、`/real/system`、`/real/ports/{name}/config`（读仍拆两个会话，不解决单会话问题）。
    - 优点(B1): 单会话批量采集满足 NFUNC-004；独立超时与响应 schema（含 IO 降级字段 `io.supported`）；不与 SIMULATOR 逻辑耦合；写操作复用既有 action 语义与前端 `configurePort` 方法。
    - 缺点(B1): 前端 store 需新增 1 个 `getRealPanel` 方法（抽屉 UI 结构仍复用 SIMULATOR 面板）。
- **Decision**: 采用 **Option B1（读聚合新端点 + 写扩展既有端点）**。
  - 读：新增 `GET /api/devices/{device_id}/real_panel`，单会话批量采集，一次返回 `{ports, cpu, memory, io, info?, collected_at}`。
  - 写：扩展现有 `POST /api/devices/{device_id}/ports/{name}/config`，在 `device_type == REAL` 时分支到 REAL 写路径（`configure(["interface <name>", "shutdown"|"no shutdown"])`），SIMULATOR 分支代码保持逐字不变。
  - 理由：Q-RP-03/NFUNC-004 的「单会话批量采集」是硬约束，Option A 的读路径必然产生两次会话建立，无法满足；「不做会话池」排除跨请求复用。写操作是单动作、无批量诉求，扩展现有 `/ports/{name}/config` 可最大化复用前端 `configurePort`（同一 encodeURIComponent 处理）且不破坏 SIMULATOR（NFUNC-003）。这是满足全部硬约束下的最小改动。
- **Consequences**:
  - 正向: 满足单会话批量采集（NFUNC-004/Q-RP-03）；SIMULATOR 读分支与 `configure_port` SIMULATOR 路径逐字不变（NFUNC-003）；REAL 读响应 schema 独立可扩展降级字段。
  - 负向: 前端 `devices.ts` 新增 1 个 store 方法；读端点响应形状与 SIMULATOR `/ports`+`/system` 拆分不同（引入轻微的非对称，由前端 REAL 抽屉封装吸收）。

---

### ADR-RP-002: IO 读写区块采集方案（裁决 REQ-RP-FUNC-010）

- **Status**: Accepted
- **Context**:
  - REQ-RP-FUNC-010 要求「保留『IO 读写』区块，不得直接丢弃」；真实设备无已验证的 IO CLI 命令，须寻找替代命令或降级展示。
  - AC-RP-009-01: 若架构确定可用的 IO 替代采集命令 → 展示替代数据；AC-RP-009-02: 若确无可用命令 → 保留区块 + 降级提示（如「该设备不支持 IO 采集」），不得隐藏或丢弃区块。
  - 已验证命令清单（REQ-RP-FUNC-009 来源）为 `show system-info`、`show ip ssh`、`show interface status`、`show cpu-utilization`、`show memory-utilization`、`show running-config`，其中**无**任何 IO 读/写速率命令。
- **Options**:
  - Option A: 采用替代命令 `show interface counters`（未验证）做两次采样差值推导速率（读/写 KB/s = Δbytes/Δt）。
    - 优点: 若可用则最贴近 SIMULATOR 的「IO 读/写 KB/s」语义。
    - 缺点: 命令**不在已验证列表**，存在「unknown command」失败风险；需在同会话内二次采样并 sleep 计时，显著增加单会话采集耗时（与 NFUNC-001 的 30-60s 预算冲突）；结果为推导值而非设备原生指标，[ESTIMATE] 置信度低。
  - Option B: 从已采集的 `show interface status` 推导 IO 速率。
    - 优点: 复用已采集命令，零额外命令。
    - 缺点: 该命令输出仅含 name/status/vlan/duplex/speed/type（见 `switch_diag_tool.py` MOCK_INTERFACE_STATUS），**不含任何 byte/rate 计数器**，无法推导 IO 速率，[ESTIMATE] 不可行。
  - Option C: 降级展示——后端 `io` 返回结构化占位 `{supported: false, read_kbps: null, write_kbps: null, message: "该设备不支持 IO 采集（无已验证 CLI 命令）"}`，前端始终渲染「IO 读」「IO 写」区块、当 `supported == false` 时显示降级文案；同时在解析模块预留 `parse_io_rates()` 钩子便于未来接入替代命令。
    - 优点: 确定性满足 AC-RP-009-02；零新增命令/依赖/耗时；区块永不丢失；预留钩子兼容 AC-RP-009-01 的未来扩展（不改 schema）。
    - 缺点: 本轮 IO 区块为降级占位，不提供真实速率数值。
- **Decision**: 采用 **Option C（降级展示 + 预留解析钩子）**。
  - 理由：已验证命令清单中确无可用 IO 速率命令（AC-RP-009-02 触发条件成立）；Option A/B 的可行性评估均为 LOW/不可行，且会破坏 NFUNC-001 的耗时预算。降级方案是唯一确定性满足「保留区块 + 不丢区块」且零风险的决策；`parse_io_rates()` 钩子与 `io.supported` 字段保证未来发现替代命令时无需改动响应 schema 即可接入（兼顾 AC-RP-009-01 精神）。
- **Consequences**:
  - 正向: 区块永远保留（AC-RP-009-02 确定性满足）；零新增依赖与耗时；schema 前向兼容（未来接入替代命令不改契约）。
  - 负向: 本轮不展示真实 IO 速率（真实设备无原生命令所致，属需求已确认的降级范围）；前端需按 `io.supported` 分支渲染降级文案。

---

### ADR-RP-003: 会话复用与串行化机制（裁决需求层开放项 Q-RP-05）

- **Status**: Accepted
- **Context**:
  - REQ-RP-NFUNC-004 要求「面板采集会话需与『连通性检测』『工作流执行』避免并发冲突；单次采集复用同一会话批量下发多条 show 命令；会话需在 finally 中关闭并设超时」。
  - Q-RP-05 RESOLVED: 复用 `real_device_client.DeviceToolSession`，会话串行化（TL-SG5428 TELNET 仅 1 个活动会话，`real_device_client.py` 第 1661-1663 行注释），**不做会话池**。
  - 现状：`check_connectivity` 端点（`devices_router.py` 471-541）通过 `real_device_client.check_connectivity()` 内部自建会话；工作流通过 `switch_diag_tool`/`switch_config_tool` 的 `_run` 直接 `_SshSession`/`_TelnetSession` 开会话；代码库现有 `threading.Lock` 仅用于单例/缓冲保护，无 per-device 会话锁。
- **Options**:
  - Option A: 复用 `DeviceToolSession` + 进程内 per-device 串行化锁（`threading.Lock` 注册表），面板/连通性/写操作/工作流统一在会话生命周期外包裹 `with session_guard(...)`。
    - 优点: 零新依赖（stdlib threading）；锁粒度按设备隔离（不同设备可并发采集）；单一机制覆盖四类会话；`DeviceToolSession` 已具备 finally-close 语义（`__exit__`）。
    - 缺点: 需在会话调用点显式包裹；串行化锁只在本进程内有效（多进程部署需另议，当前单进程 FastAPI 可接受）。
  - Option B: 会话队列（`queue.Queue` + 后台 worker）串行消费同一设备的会话请求。
    - 优点: 请求先到先服务、可排队等待而非立即失败。
    - 缺点: 引入后台线程与队列复杂度；面板为手动刷新、无高频并发诉求，队列收益低；与「不做会话池」的定位偏离（队列易被误读为会话复用）。
  - Option C: 串行上下文管理器封装在 `DeviceToolSession` 内部（`__enter__` 内自取锁）。
    - 优点: 调用方无感知。
    - 缺点: 无法覆盖 `check_connectivity()` 与工作流工具（它们不经 `DeviceToolSession`，直接 `_SshSession`/`_TelnetSession`），会留下串行化缺口。
- **Decision**: 采用 **Option A（复用 DeviceToolSession + per-device `threading.Lock` 串行化门）**。
  - 具体机制：新增 `src/tools/real_session_gate.py`，维护 `{canonical_key → threading.Lock}` 注册表（以 `_resolve_access(device)` 解析出的 `(host, port, protocol)` 为规范 key），提供：
    - `session_guard(device)` —— 供面板读/写端点、`check_connectivity` 使用；
    - `session_guard_by_access(host, port, protocol)` —— 供工作流工具（`TpLinkSwitchDiagTool`/`TpLinkSwitchConfigTool`）使用。
  - 面板采集服务（`real_panel_service.py`）在 `with DeviceToolSession(...) as sess:` 外层再套 `with session_guard(device):`，单会话内批量 `show interface status` / `show cpu-utilization` / `show memory-utilization`（可选 `show system-info`），`finally` 关闭由 `DeviceToolSession.__exit__` 保证。
  - `check_connectivity` 端点将 `_l7_check(device, username, password)` 调用包裹 `session_guard(device)`；写操作端点同理。
  - 工作流工具在 REAL 分支的 `_SshSession`/`_TelnetSession` 开/关外包裹 `session_guard_by_access(host, port, protocol)`。
  - 理由：Option A 是唯一覆盖全部四类会话（面板/连通性/写/工作流）且零依赖、粒度正确的方案；Option C 覆盖不全，Option B 引入不必要的后台线程复杂度且偏离「不做会话池」。
- **Consequences**:
  - 正向: 满足 NFUNC-004 并发互斥；锁粒度 per-device，不同设备互不阻塞；零新依赖；`DeviceToolSession` 的 `__exit__` 保证 finally-close。
  - 负向: 同一设备的并发采集请求会串行阻塞（可接受，因面板为手动刷新）；多进程/多实例部署时进程内锁不跨实例（当前单进程 FastAPI，列为开放问题）。[ASSUMPTION — 工作流工具需额外接入 `session_guard_by_access`，其 FRP 映射 key 与面板 `_resolve_access` key 的完全对齐依赖实现校准，见开放问题。]

---

### ADR-RP-004: 基本信息区块纳入裁决（REQ-RP-FUNC-005，Should Have）

- **Status**: Accepted
- **Context**:
  - REQ-RP-FUNC-005 为 Should Have：默认不纳入，作为低成本增值项由架构阶段裁决，**不得作为 Must Have**。
  - 现有 `check_connectivity` 已解析 `show system-info` 的 `software_version` 与 `model`（`real_device_client.py` 第 2029-2036 行 `_parse_show_system_info`），并已回传 `device_model`/`software_version`（`devices_router.py` 528-540）。
  - 面板读端点已为只读采集建立单会话批量，追加一条 `show system-info` 仅增加约 1-2s。
- **Options**:
  - Option A: 纳入本轮实现（Should Have，容错非阻塞）。
    - 优点: 边际成本极低（同会话多一条 show + 复用 `_parse_show_system_info`）；操作员在写操作前可确认设备型号/版本，降低「误操作错误设备」的风险（与 NFUNC-002 安全目标协同）；AC-RP-004-01 可验收。
    - 缺点: 略微扩大本轮范围（`info` 区块的采集失败处理需额外考虑）。
  - Option B: 不纳入（严格 Must Have 范围）。
    - 优点: 范围最小、交付最聚焦。
    - 缺点: 放弃近乎零成本的增值项，且丢失「写操作前确认设备身份」的安全增益。
- **Decision**: 采用 **Option A（纳入本轮，作为容错 Should Have）**。
  - 理由：`_parse_show_system_info` 已存在且被 `check_connectivity` 验证；面板读端点已建立单会话批量，追加命令边际成本 ~1-2s；`info` 展示与 `/check_connectivity` 返回的 `device_model`/`software_version` 一致（AC-RP-004-01）。以「容错非阻塞」实现：`info` 采集/解析失败不阻塞端口/CPU/内存区块，`info` 字段可选返回，保持 Should Have 定位（不升级为 Must Have）。
- **Consequences**:
  - 正向: 低成本增值 + 写操作前的设备身份确认（安全协同）；AC-RP-004-01 可验收。
  - 负向: 前端抽屉多一个「基本信息」区块；需保证 `info` 失败不影响面板其余部分。[ASSUMPTION — PM 若坚持严格 Must Have 范围可在门控阶段否决，需回退 Option B。]

---

### ADR-RP-005: 写操作安全（REQ-RP-FUNC-006 + REQ-RP-NFUNC-002）

- **Status**: Accepted
- **Context**:
  - REQ-RP-FUNC-006 已确认开放端口「启用（no shutdown）/禁用（shutdown）」写操作；每次写操作强制前端二次确认 + 审计日志（NFUNC-002 强制适用）；**不做 `copy running-config startup-config` 持久化**（AC-RP-005-03）。
  - 这是对生产设备的写操作，风险远高于 SIMULATOR 写操作。
  - 现有 `DeviceToolSession.configure(commands)` 仅进入 config 模式执行命令并退出，**不调用 `save()`**；`save()`（`copy running-config startup-config`）是独立方法（`real_device_client.py` 第 1226-1238 行），`DeviceToolSession` 亦未暴露 `save()`。
  - `/api/*` 路由已由 `api_router` 统一注入 `Depends(get_current_user)`（`src/api/__init__.py` 第 26 行），`AuditLogger` 为单例（`src/security/audit_logger.py`），`AuditEventType.CONFIG_CHANGE` 已定义。
- **Options**:
  - Option A: 前端二次确认（`ElMessageBox.confirm` 明确「此操作将修改真实生产设备配置」+ 目标端口 + 动作）+ 后端审计（`AuditLogger.log_audit_event`，操作人来自 `get_current_user`）+ 写路径仅用 `configure()` 不调 `save()`。
    - 优点: 三重防护（前端确认、后端审计、不持久化）完整覆盖 NFUNC-002；复用现有 AuditLogger 与 `get_current_user`，零新依赖；`configure()` 天然不持久化。
    - 缺点: 写端点需新增 `get_current_user` 注入与审计调用；`AuditLogger.log_audit_event` 需以 `alert_id` 承载非告警场景的设备标识（用合成 `device:{id}`）。
  - Option B: 仅后端审计 + 前端简单确认，写路径调用 `save()` 持久化。
    - 优点: 实现更少。
    - 缺点: **违反** Q-RP-02「不做持久化」与 AC-RP-005-03（需求层已 APPROVED，不可推翻）；审计缺少操作人/二次确认语义。
- **Decision**: 采用 **Option A**。
  - 前端（MOD-RP-005）：点击启用/禁用 → `ElMessageBox.confirm`（文案明确「此操作将修改真实生产设备配置」+ 目标端口 + 动作 shutdown/no shutdown）→ 确认后调用 store。
  - 后端（MOD-RP-001）：写端点注入 `current_user: User = Depends(get_current_user)`；在 `session_guard(device)` 内调用 `DeviceToolSession.configure(["interface <name>", "shutdown"|"no shutdown"])`；**绝不调用 `save()`**；执行后调用 `AuditLogger().log_audit_event(event_type=AuditEventType.CONFIG_CHANGE, alert_id=f"device:{device_id}", operator=current_user.username, action=f"port_{action}", detail={device_id, device_name, port_name, action, success, message, timestamp})`，`detail` 不含明文密码。
  - 理由：Option A 是唯一完整满足「二次确认 + 审计 + 不持久化」三重已确认约束的方案；`configure()`（不 `save()`）从结构上保证 AC-RP-005-03。
- **Consequences**:
  - 正向: NFUNC-002 全覆盖；不持久化由 `configure()` 结构保证（`DeviceToolSession` 无 `save()` 暴露）；审计不含明文密码（AC-RP-006-02）。
  - 负向: 写端点新增审计依赖；`alert_id` 复用为设备标识需在审计查询侧兼容说明（记为开放问题）。

---

### ADR-RP-006: CLI 输出解析器模块定位与错误处理（REQ-RP-FUNC-009）

- **Status**: Accepted
- **Context**:
  - REQ-RP-FUNC-009 要求将 `show interface status`/`show cpu-utilization`/`show memory-utilization`（可选 `show system-info`）原始文本解析为结构化字段；解析需基于 TP-Link 真实输出（非 Mock 模板）；解析失败返回明确错误而非错误数据。
  - 现有清洗工具 `_strip_echo_and_prompts`（`real_device_client.py` 1978-1994）与错误识别 `_looks_like_error`（1964-1975）可复用。
- **Options**:
  - Option A: 新增独立纯函数解析模块 `src/tools/real_panel_parsers.py`（无状态、仅依赖 `re` + 复用清洗函数）。
    - 优点: 职责单一、易单测、不改动 2100+ 行的 `real_device_client.py`；解析失败可统一抛 `ParseError` 由服务层转为明确错误。
    - 缺点: 新增一个文件（符合需求层「新增解析模块」的变更预期）。
  - Option B: 解析函数直接塞进 `real_device_client.py`。
    - 优点: 少一个文件。
    - 缺点: 继续膨胀既有大文件，职责混杂，单测定位难，不符合单一职责。
- **Decision**: 采用 **Option A（新增 `real_panel_parsers.py` 纯函数模块）**。
  - 理由：REQ-RP-FUNC-009 明确「新增解析模块（或扩展 real_device_client.py）」，独立模块职责清晰、可单测；解析基于真实输出，实现阶段以真实设备输出校准（需求备注已要求）；解析失败抛结构化异常，不返回伪造数据。
- **Consequences**:
  - 正向: 解析逻辑独立可测；失败路径清晰（`ParseError` → 服务层 → 端点明确错误）。
  - 负向: 新增一个后端文件；字段映射依赖真实输出样例，需开发阶段校准（列为实现前置条件）。

---

### ADR-RP-007: 前端采集超时与加载反馈（REQ-RP-NFUNC-001）

- **Status**: Accepted
- **Context**:
  - REQ-RP-NFUNC-001: 真实设备 SSH 会话建立约 20-40s（L7 30-60s），前端需长超时 + loading +「约 30-60s」预期提示 + 失败明确报错；刷新策略为手动刷新 + 单会话批量采集（Q-RP-03）。
  - 现状参考：`checkConnectivity` 使用 `timeout: 120000`（`devices.ts` 82-87），`DevicesListView.vue` 400-433 已有「30-60s」提示 + 125s fail-safe 模式。
- **Options**:
  - Option A: 复用 `checkConnectivity` 的超时模式——新增 `getRealPanel`（`{timeout: 120000}`）+ 前端 REAL 抽屉 loading/提示/fail-safe（125s）。
    - 优点: 与既有 `checkConnectivity` 交互一致，用户心智统一；复用 axios timeout 参数，零新依赖。
    - 缺点: 需为 REAL 面板新增 loading 状态与 fail-safe 定时器。
  - Option B: 默认 15s 超时 + 简单 spinner。
    - 优点: 实现最少。
    - 缺点: 真实会话 20-40s 会必然触发 15s 超时，面板无法加载（违反 NFUNC-001 与 AC-RP-007-01/02）。
- **Decision**: 采用 **Option A**。
  - 理由：真实会话建立时长远超默认 15s，Option B 必然失败；Option A 直接复用已验证的 `checkConnectivity` 超时/提示/fail-safe 模式，满足 AC-RP-007-01（loading + 30-60s 提示）与 AC-RP-007-02（超时/失败解除 loading 不永久挂起）。
- **Consequences**:
  - 正向: 满足 NFUNC-001 全部验收标准；与既有交互一致。
  - 负向: 前端 REAL 抽屉新增 loading/超时状态管理（有限的前端增量）。

---

## 开放问题

1. **[ASSUMPTION — requires PM confirmation]** ADR-RP-004 将 REQ-RP-FUNC-005 基本信息区块纳入本轮（Should Have 容错实现）。若 PM 坚持严格 Must Have 范围，需回退为不纳入。
2. **[ASSUMPTION — requires PM confirmation]** ADR-RP-003 中「工作流工具接入 `session_guard_by_access`」会修改 `switch_diag_tool.py`/`switch_config_tool.py`（仅包裹串行化门，不改会话逻辑）。工作流工具当前以 `device_ip`+auth 开会话，其 FRP 映射 key 与面板 `_resolve_access` key 的完全对齐需实现阶段校准（FRP 场景下可能仍存细微并发窗口）。
3. **[ASSUMPTION — 实现校准]** REQ-RP-FUNC-009 的字段映射（`show interface status`/`show cpu-utilization`/`show memory-utilization` 真实输出格式）与写操作 `configure → interface → shutdown/no shutdown → exit` 的退出层级（单次 `exit` 是否回到 enable 模式）需以真实 TL-SG5428 输出为基准校准。
4. **[开放问题]** `AuditLogger.log_audit_event` 的 `alert_id` 字段在本场景承载合成设备标识 `device:{id}`，非告警 ID；后续审计查询侧需兼容该约定。

---

*文档版本 0.1.0 | 状态 APPROVED | 生成时间 2026-09-05 | 作者 sub_agent_system_architect*

<audit_log>
  <log time="2026-09-05T00:00:00Z" state="WRITE_FILES" action="file_write" result="SUCCESS" trace_id="inv-real-panel-b-001" file_path="project_workspace/real_device_panel/architecture/real_panel_architecture_design.md"/>
</audit_log>
