<file_header>
  <project_id>NetworkAgentDemo</project_id>
  <module_id>real_device_panel</module_id>
  <doc_type>module_design</doc_type>
  <file_name>real_panel_module_design.md</file_name>
  <version>0.1.0</version>
  <status>APPROVED</status>
  <author_agent>sub_agent_system_architect</author_agent>
  <created_at>2026-09-05T00:00:00Z</created_at>
  <last_updated>2026-09-05T00:00:00Z</last_updated>
  <invocation_id>inv-real-panel-b-001</invocation_id>
  <input_source>PM agent_invocation — GROUP_RP_B 模块设计（基于 APPROVED 需求 inv-real-panel-a-002）</input_source>
</file_header>

# 真实设备（REAL）面板 — 模块设计

## 模块总览

| MOD-ID | 模块名 | 层级 | 职责 | 依赖于 |
|--------|--------|------|------|--------|
| MOD-RP-001 | REAL 面板 API 端点 | API 层 | 聚合读端点 + 写端点扩展，鉴权/参数校验/审计/错误转换 | MOD-RP-002, MOD-RP-007(复用), DeviceRepository, get_current_user |
| MOD-RP-002 | REAL 面板采集服务 | 服务层 | 单会话批量采集组装快照 + 端口写操作编排 | MOD-RP-003, MOD-RP-004, real_device_client.DeviceToolSession |
| MOD-RP-003 | TP-Link CLI 输出解析器 | 工具层 | 纯函数解析端口/CPU/内存/IO/基本信息 | 无（仅 stdlib re） |
| MOD-RP-004 | 会话串行化门 | 基础设施层 | per-device 会话锁，串行化面板/连通性/写/工作流 | real_device_client._resolve_access |
| MOD-RP-005 | 前端 REAL 面板抽屉 | 前端视图层 | 面板按钮、抽屉 UI、loading/超时反馈、二次确认、IO 降级 | MOD-RP-006 |
| MOD-RP-006 | 前端 DevicesStore 扩展 | 前端状态层 | getRealPanel（120s 超时）+ configurePort 可选超时 | axios client（`@/api/client`） |
| MOD-RP-007 | 审计接入（复用 MOD-015） | 复用（非新增） | 写操作审计记录，无明文密码 | src.security.audit_logger.AuditLogger |

---

## 模块详情

---

### MOD-RP-001: REAL 面板 API 端点

- **职责**: 在既有 `src/api/devices_router.py` 内新增 REAL 面板聚合只读端点，并扩展既有写端点使其分支支持 REAL；负责 JWT 鉴权（继承 `/api` 前缀依赖）、参数校验、调用服务层、审计写入、超时/错误转换为 HTTP 响应。**不**改动任何 SIMULATOR 分支逻辑与 `/check_connectivity` 返回字段（REQ-RP-NFUNC-003）。
- **覆盖需求**: REQ-RP-FUNC-006（写操作后端）、REQ-RP-FUNC-007（后端数据获取能力）、REQ-RP-NFUNC-002（审计）、REQ-RP-NFUNC-003（零变更约束）、REQ-RP-NFUNC-004（串行化入口）。
- **公开接口契约**:

  - **IFC-RP-001-01**: `GET /api/devices/{device_id}/real_panel`
    - 入参: `device_id: int`（路径），`db: Session`（Depends get_db），`current_user: User`（Depends get_current_user，路由级已注入，此处按需显式注入）
    - 出参: `200` → `RealPanelSnapshot`（见 MOD-RP-002 IFC-RP-002-01）；`404` → 设备不存在；`400` → 非 REAL 设备（返回 `{"device_id", "message": "/real_panel 仅适用于 REAL 真实设备"}`）；`502` → 采集失败（含 `message`）
    - 说明: 内部调用 `_decrypt_password()`（复用现有 helper）解密凭据；将 `MOD-RP-002.collect_real_panel()` 的异常转换为明确 HTTP 错误，不泄露密码。

  - **IFC-RP-001-02**: `POST /api/devices/{device_id}/ports/{port_name}/config`（扩展 REAL 分支）
    - 入参: `device_id: int`，`port_name: str`（已由前端 encodeURIComponent，可含 `/`），`body: PortConfigRequest`（`action: str` = `shutdown` | `no-shutdown`；`value: Optional[str]`），`current_user: User`
    - 出参: `200` → `{"device_id": int, "port_name": str, "action": str, "success": bool, "message": str, "audit_record_id": Optional[str]}`；`404`/`400` 同现有语义
    - 说明: `device_type == REAL` 时走 `MOD-RP-002.configure_real_port()`；执行后调用 `MOD-RP-007` 写审计；SIMULATOR 分支代码逐字不变（NFUNC-003）。

- **依赖模块**: MOD-RP-002（服务调用）、MOD-RP-007（审计，复用 AuditLogger）、`DeviceRepository`、`get_current_user`。
- **外部依赖**: FastAPI `APIRouter` / `Depends` / `HTTPException`；`src.api.dependencies.get_db/get_current_user`；`src.database.repositories.device_repository.DeviceRepository`。

---

### MOD-RP-002: REAL 面板采集服务

- **职责**: 编排单会话批量采集（`show interface status` + `show cpu-utilization` + `show memory-utilization` [+ 可选 `show system-info`]）并组装 `RealPanelSnapshot`；编排端口写操作（`configure` 不 `save`）。会话在 `with DeviceToolSession(...)` 内建立、`finally` 关闭，外层套 `session_guard` 串行化门。
- **覆盖需求**: REQ-RP-FUNC-002/003/004/005/007/010（只读采集组装）、REQ-RP-FUNC-006（写操作）、REQ-RP-NFUNC-004（单会话 + 串行化）。
- **公开接口契约**:

  - **IFC-RP-002-01**: `collect_real_panel(device, username: str, password: str) -> RealPanelSnapshot`
    - 入参: `device`（ORM Device 对象，含 `connection_protocol`/`frp_proxy_*`）、`username: str`、`password: str`（已解密）
    - 出参: `RealPanelSnapshot` = `{device_id: int, ports: list[PortStatus], cpu: CpuUsage, memory: MemoryUsage, io: IoRates, info: Optional[DeviceInfo], collected_at: str(ISO8601)}`
    - 行为: 单会话内依次 `show interface status` → `parse_interface_status`；`show cpu-utilization` → `parse_cpu_utilization`；`show memory-utilization` → `parse_memory_utilization`；`io` 由 `parse_io_rates(None)` 生成降级占位（ADR-RP-002）；可选 `show system-info` → `parse_system_info`（失败容错置 `info=None`，不阻塞其余区块，ADR-RP-004）。任一命令 `_looks_like_error` 或解析失败 → 抛结构化 `RealPanelError`（含区块标识与原因）。

  - **IFC-RP-002-02**: `configure_real_port(device, username: str, password: str, port_name: str, action: str) -> PortWriteResult`
    - 入参: 同上 + `port_name: str`（如 `Gi0/1`）、`action: str`（`shutdown` | `no-shutdown`）
    - 出参: `PortWriteResult` = `{success: bool, message: str, output: str}`（`output` 为命令回显摘要，不含密码）
    - 行为: `with session_guard(device), DeviceToolSession(device, username, password) as sess:` → 将 `action` 映射为 CLI 命令（`shutdown` → `"shutdown"`，`no-shutdown` → `"no shutdown"`）→ `sess.configure(["interface " + port_name, cli_cmd])`；**绝不调用 `save()`**（AC-RP-005-03）。

- **依赖模块**: MOD-RP-003（解析）、MOD-RP-004（串行化门）、`src.tools.real_device_client`（`DeviceToolSession` / `_strip_echo_and_prompts` / `_looks_like_error`）。
- **外部依赖**: 无新增第三方依赖（仅 stdlib + real_device_client）。

---

### MOD-RP-003: TP-Link CLI 输出解析器

- **职责**: 将 TP-Link 真实 CLI 文本输出解析为结构化字段；纯函数、无状态、不建会话、可直接单测；解析失败抛结构化异常而非返回伪造数据（REQ-RP-FUNC-009）。
- **覆盖需求**: REQ-RP-FUNC-002（端口）、REQ-RP-FUNC-003（CPU）、REQ-RP-FUNC-004（内存）、REQ-RP-FUNC-005（基本信息）、REQ-RP-FUNC-009（解析）、REQ-RP-FUNC-010（IO 降级占位）。
- **公开接口契约**（类型定义 + 解析函数）:

  - 类型定义（dataclass/typing）:
    - `PortStatus` = `{name: str, status: str, vlan: str, speed: str}`（status ∈ `up`/`down`/`notconnect` 等，speed 如 `1000`/`Auto`）
    - `CpuUsage` = `{cpu_5s: float, cpu_1m: Optional[float], cpu_5m: Optional[float]}`
    - `MemoryUsage` = `{used_mb: float, total_mb: float, usage_pct: float}`
    - `IoRates` = `{supported: bool, read_kbps: Optional[float], write_kbps: Optional[float], message: str}`
    - `DeviceInfo` = `{device_name: str, model: str, hardware_version: str, software_version: str}`
    - `RealPanelError(Exception)` = `{section: str, reason: str, raw_excerpt: str}`

  - **IFC-RP-003-01**: `parse_interface_status(text: str) -> list[PortStatus]`
    - 入参: `show interface status` 清洗后文本（`_strip_echo_and_prompts` 输出）
    - 出参: 端口列表（name/status/vlan/speed）；解析失败抛 `RealPanelError(section="ports")`

  - **IFC-RP-003-02**: `parse_cpu_utilization(text: str) -> CpuUsage`
    - 入参: `show cpu-utilization` 文本；出参: `cpu_5s`（必填）+ 可选 `cpu_1m`/`cpu_5m`；失败抛 `RealPanelError(section="cpu")`

  - **IFC-RP-003-03**: `parse_memory_utilization(text: str) -> MemoryUsage`
    - 入参: `show memory-utilization` 文本；出参: `used_mb`/`total_mb`/`usage_pct`（若命令仅返回 used/free/total，则 `usage_pct = used/total*100`）；失败抛 `RealPanelError(section="memory")`

  - **IFC-RP-003-04**: `parse_io_rates(text: Optional[str]) -> IoRates`
    - 入参: 预留的 IO 命令文本（本轮传 `None`）
    - 出参: `{supported: False, read_kbps: None, write_kbps: None, message: "该设备不支持 IO 采集（无已验证 CLI 命令）"}`（ADR-RP-002）；未来接入替代命令时返回 `supported=True` 并填充速率，不改契约

  - **IFC-RP-003-05**: `parse_system_info(text: str) -> DeviceInfo`
    - 入参: `show system-info` 文本；出参: `device_name`/`model`/`hardware_version`/`software_version`；复用/对齐 `real_device_client._parse_show_system_info` 的字段提取；失败抛 `RealPanelError(section="info")`

- **依赖模块**: 无（仅 stdlib `re`；可复用 `real_device_client._strip_echo_and_prompts`/`_looks_like_error` 作为前置清洗，不形成硬依赖）。
- **外部依赖**: 无。

---

### MOD-RP-004: 会话串行化门

- **职责**: 维护进程内 per-device 会话锁注册表（`{canonical_key → threading.Lock}`），以 `_resolve_access(device)` 解析出的 `(host, port, protocol)` 为规范 key，提供上下文管理器，保证同一物理设备同一时刻仅一个活动会话（TL-SG5428 TELNET 单会话限制，REQ-RP-NFUNC-004）。零新依赖。
- **覆盖需求**: REQ-RP-NFUNC-004（串行化）、Q-RP-05（复用 DeviceToolSession + 串行化，不做会话池）。
- **公开接口契约**:

  - **IFC-RP-004-01**: `session_key(device) -> str`
    - 入参: `device`（ORM Device 对象）；出参: `str`（`f"{host}:{port}:{protocol}"`，经 `_resolve_access` 解析，含 FRP 映射）

  - **IFC-RP-004-02**: `session_guard(device) -> ContextManager`
    - 入参: `device`；行为: 获取 `session_key(device)` 对应的 `threading.Lock` 并 `acquire`/`release`（`with session_guard(device):`）

  - **IFC-RP-004-03**: `session_guard_by_access(host: str, port: int, protocol: str) -> ContextManager`
    - 入参: 原始访问三元组；行为: 与 `session_guard` 共享同一锁注册表（key 相同则同一把锁）；供工作流工具（`TpLinkSwitchDiagTool`/`TpLinkSwitchConfigTool`）使用

- **依赖模块**: `src.tools.real_device_client._resolve_access`。
- **外部依赖**: 无（stdlib `threading`）。

---

### MOD-RP-005: 前端 REAL 面板抽屉

- **职责**: 在 `webui/src/views/devices/DevicesListView.vue` 新增 REAL「面板」按钮（与 SIMULATOR「面板」按钮并列，仅 `device_type === 'REAL'` 显示）、新增 REAL 面板 `el-drawer`（交互结构复用 SIMULATOR 抽屉）、loading/超时提示、写操作二次确认、IO 降级渲染。REAL 原有「心跳检测」「连通性检测」按钮与 SIMULATOR 面板行为保持不变（NFUNC-003）。
- **覆盖需求**: REQ-RP-FUNC-001（入口按钮）、REQ-RP-FUNC-002/003/004（端口/CPU/内存展示）、REQ-RP-FUNC-005（基本信息，容错）、REQ-RP-FUNC-006（写操作入口 + 二次确认）、REQ-RP-FUNC-008（抽屉）、REQ-RP-FUNC-010（IO 降级展示）、REQ-RP-NFUNC-001（loading/超时）、REQ-RP-NFUNC-002（二次确认）。
- **公开接口契约**（组件内方法，非跨模块 API）:

  - **IFC-RP-005-01**: `showRealPanel(row) -> void`
    - 入参: `row: any`（REAL 设备行）；行为: 打开抽屉 `realPanelVisible=true`、设置 `realPanelDevice=row`、立即调用 `loadRealPanel()`

  - **IFC-RP-005-02**: `loadRealPanel() -> Promise<void>`
    - 行为: 设置 `realPanelLoading=true` + `ElMessage` 提示「真实设备采集中（约 30-60s，请耐心等待）」+ 125s fail-safe 定时器；调用 `store.getRealPanel(deviceId)`；成功后填充 `realPanelData`（ports/cpu/memory/io/info）；失败/超时 `ElMessage.error` 并解除 loading（不永久挂起，AC-RP-007-01/02）

  - **IFC-RP-005-03**: `confirmRealPortAction(portName: string, action: string) -> Promise<void>`
    - 行为: `ElMessageBox.confirm`（文案明确「此操作将修改真实生产设备配置」+ 目标端口 + 动作 shutdown/no shutdown）→ 确认后调用 `store.configurePort(deviceId, portName, action, undefined, 120000)`（AC-RP-006-01）

  - **IFC-RP-005-04**: `renderIoBlock(io: IoRates) -> void`
    - 行为: 始终渲染「IO 读」「IO 写」两个 `sys-item`；`io.supported === false` 或 `read_kbps/write_kbps` 为 null 时显示 `io.message`（降级文案「该设备不支持 IO 采集」），**不隐藏区块**（AC-RP-009-02）

- **依赖模块**: MOD-RP-006（store 方法）。
- **外部依赖**: Vue 3 + Element Plus（`el-drawer`/`el-card`/`el-table`/`el-progress`/`el-empty`/`ElMessageBox`/`ElMessage`）。

---

### MOD-RP-006: 前端 DevicesStore 扩展

- **职责**: 在 `webui/src/stores/devices.ts` 新增 `getRealPanel`（长超时）并扩展 `configurePort` 支持可选超时，供 REAL 抽屉调用；不影响 SIMULATOR 现有调用（默认参数向后兼容）。
- **覆盖需求**: REQ-RP-FUNC-008（数据加载）、REQ-RP-NFUNC-001（长超时）。
- **公开接口契约**:

  - **IFC-RP-006-01**: `getRealPanel(deviceId: number) -> Promise<RealPanelSnapshot>`
    - 入参: `deviceId: number`；行为: `client.get('/api/devices/' + deviceId + '/real_panel', { timeout: 120000 })`；出参: `RealPanelSnapshot`（同后端 schema）

  - **IFC-RP-006-02**: `configurePort(deviceId: number, portName: string, action: string, value?: string, timeoutMs?: number) -> Promise<any>`
    - 入参: 现有四参数 + 可选 `timeoutMs`（默认 undefined → 客户端默认 15s，SIMULATOR 行为不变；REAL 传 `120000`）
    - 行为: `client.post('/api/devices/' + deviceId + '/ports/' + encodeURIComponent(portName) + '/config', { action, value: value || null }, timeoutMs ? { timeout: timeoutMs } : {})`

- **依赖模块**: `@/api/client`（axios 实例）。
- **外部依赖**: Pinia `defineStore`。

---

### MOD-RP-007: 审计接入（复用 MOD-015 AuditLogger）

- **职责**: 为 REAL 端口写操作写入不可篡改审计日志，操作人来自 `get_current_user`，`detail` 不含明文密码（AC-RP-006-02）。**复用现有 `src/security/audit_logger.py` 单例，不新增模块、不新增表。**
- **覆盖需求**: REQ-RP-NFUNC-002（审计）、REQ-RP-FUNC-006（写操作审计）。
- **公开接口契约**（复用现有，非新增）:

  - **IFC-RP-007-01**（复用 IFC-015-02）: `AuditLogger.log_audit_event(event_type: str, alert_id: str, operator: str, action: str, detail: dict) -> str`
    - 调用约定: `event_type = AuditEventType.CONFIG_CHANGE`；`alert_id = f"device:{device_id}"`（合成设备标识，见 ADR-RP-005）；`operator = current_user.username`；`action = "port_shutdown" | "port_no_shutdown"`；`detail = {device_id, device_name, port_name, action, success, message}`（**不含** `password`/`ssh_password_encrypted`）
    - 出参: `audit_record_id: str`（回填到写端点响应 `audit_record_id`）

- **依赖模块**: `src.security.audit_logger.AuditLogger`、`src.models.enums.AuditEventType`。
- **外部依赖**: 无。

---

## 依赖关系图（文本格式，无循环依赖，已验证）

```
MOD-RP-005 (前端 REAL 抽屉)
   └─→ MOD-RP-006 (DevicesStore 扩展)                    [调用 getRealPanel / configurePort]
           └─→ HTTP /api/devices/* (MOD-RP-001 端点)
                   └─→ MOD-RP-002 (采集服务)              [collect_real_panel / configure_real_port]
                           ├─→ MOD-RP-003 (CLI 解析器)     [parse_* 纯函数]
                           ├─→ MOD-RP-004 (串行化门)       [session_guard]
                           │       └─→ real_device_client._resolve_access
                           └─→ real_device_client.DeviceToolSession
                   └─→ MOD-RP-007 (审计，复用 AuditLogger)  [log_audit_event]
```

- 依赖方向单向：前端 → store → HTTP → 服务 → 解析/串行化/会话工厂。解析器（MOD-RP-003）与串行化门（MOD-RP-004）为叶节点，无回边，**无循环依赖**。

---

## 需求覆盖追溯矩阵（REQ-RP-FUNC-001~010 100% 覆盖）

| 需求 ID | 覆盖模块 |
|---------|----------|
| REQ-RP-FUNC-001 | MOD-RP-005 |
| REQ-RP-FUNC-002 | MOD-RP-001, MOD-RP-002, MOD-RP-003, MOD-RP-005 |
| REQ-RP-FUNC-003 | MOD-RP-001, MOD-RP-002, MOD-RP-003, MOD-RP-005 |
| REQ-RP-FUNC-004 | MOD-RP-001, MOD-RP-002, MOD-RP-003, MOD-RP-005 |
| REQ-RP-FUNC-005 | MOD-RP-001, MOD-RP-002, MOD-RP-003, MOD-RP-005 |
| REQ-RP-FUNC-006 | MOD-RP-001, MOD-RP-002, MOD-RP-005, MOD-RP-007 |
| REQ-RP-FUNC-007 | MOD-RP-001, MOD-RP-002 |
| REQ-RP-FUNC-008 | MOD-RP-005, MOD-RP-006 |
| REQ-RP-FUNC-009 | MOD-RP-003 |
| REQ-RP-FUNC-010 | MOD-RP-002, MOD-RP-003, MOD-RP-005 |

| 需求 ID | 覆盖方式 |
|---------|----------|
| REQ-RP-NFUNC-001 | MOD-RP-005（loading/超时）, MOD-RP-006（120s 超时）, ADR-RP-007 |
| REQ-RP-NFUNC-002 | MOD-RP-001（审计）, MOD-RP-005（二次确认）, MOD-RP-007（审计复用）, ADR-RP-005 |
| REQ-RP-NFUNC-003 | ADR-RP-001（端点形式）, 变更范围「零变更清单」 |
| REQ-RP-NFUNC-004 | MOD-RP-002（单会话 + finally）, MOD-RP-004（串行化门）, ADR-RP-003 |

---

## 变更范围清单

### 后端（新增）
| 文件 | 变更 | 关联模块 |
|------|------|----------|
| `src/tools/real_panel_parsers.py` | 新增：CLI 输出纯函数解析器 | MOD-RP-003 |
| `src/tools/real_panel_service.py` | 新增：单会话批量采集 + 写操作编排 | MOD-RP-002 |
| `src/tools/real_session_gate.py` | 新增：per-device 会话串行化门 | MOD-RP-004 |

### 后端（修改）
| 文件 | 变更 | 关联模块 |
|------|------|----------|
| `src/api/devices_router.py` | 新增 `GET /{device_id}/real_panel`；`configure_device_port` 新增 REAL 分支；`device_check_connectivity` 的 `_l7_check` 调用包裹 `session_guard` | MOD-RP-001 |
| `src/tools/switch_diag_tool.py` | `TpLinkSwitchDiagTool._run` REAL 分支会话开/关包裹 `session_guard_by_access`（仅串行化，不改会话逻辑） | ADR-RP-003（NFUNC-004 工作流互斥） |
| `src/tools/switch_config_tool.py` | `TpLinkSwitchConfigTool._run` REAL 分支会话开/关包裹 `session_guard_by_access`（同上） | ADR-RP-003 |

### 前端（修改）
| 文件 | 变更 | 关联模块 |
|------|------|----------|
| `webui/src/views/devices/DevicesListView.vue` | 新增 REAL「面板」按钮 + REAL 抽屉 + loading/二次确认/IO 降级 | MOD-RP-005 |
| `webui/src/stores/devices.ts` | 新增 `getRealPanel` + `configurePort` 可选超时参数 | MOD-RP-006 |

### 零变更（NFUNC-003 约束清单）
| 文件/能力 | 说明 |
|-----------|------|
| `webui/src/views/devices/DevicesListView.vue` SIMULATOR 面板分支 | 第 139-204 行抽屉、`showSimulatorPanel`/`loadPorts`/`loadSystem`/`portAction` 逐字不变 |
| `src/api/devices_router.py` SIMULATOR 分支（`get_device_ports`/`get_device_system`/`configure_device_port` SIMULATOR 路径） | 不修改现有 SIMULATOR 逻辑 |
| `src/api/devices_router.py` `/heartbeat`、`/check_connectivity` 返回字段 | 字段与行为不变（仅 `check_connectivity` 内部包裹串行化门，返回 schema 不变） |
| `src/tools/real_device_client.py` | 零改动（只读复用 `DeviceToolSession`/`_resolve_access`/`_parse_show_system_info`/清洗函数） |
| `src/security/audit_logger.py`、`src/models/enums.py` | 复用，零改动 |
| `tests/conftest.py`（D-001/D-002 sys.meta_path 补丁） | 不依赖修改 `src/` 修测试导入；架构不引入需要修改 src 的导入修复 |

### 依赖约束
- **零新增 Python/Node 依赖**：全部复用 `real_device_client`、FastAPI、Vue3 + Element Plus、`AuditLogger`、stdlib `threading`/`re`。
- **不得改 `src/` 修测试导入**（D-001/D-002）：新增模块为全新文件，不影响 `tests/conftest.py` 的 `sys.meta_path` 补丁机制。

---

*文档版本 0.1.0 | 状态 APPROVED | 生成时间 2026-09-05 | 作者 sub_agent_system_architect*

<audit_log>
  <log time="2026-09-05T00:00:00Z" state="WRITE_FILES" action="file_write" result="SUCCESS" trace_id="inv-real-panel-b-001" file_path="project_workspace/real_device_panel/architecture/real_panel_module_design.md"/>
</audit_log>
