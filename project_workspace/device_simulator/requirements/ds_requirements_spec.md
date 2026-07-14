<file_header>
  <project_id>NetworkAgentDemo</project_id>
  <module_id>device_simulator</module_id>
  <doc_type>requirements_spec</doc_type>
  <file_name>ds_requirements_spec.md</file_name>
  <version>0.1.0</version>
  <status>APPROVED</status>
  <author_agent>sub_agent_requirement_analyst</author_agent>
  <created_at>2026-07-14T00:00:00Z</created_at>
  <last_updated>2026-07-14T00:00:00Z</last_updated>
  <invocation_id>inv-ds-group-a-001</invocation_id>
  <input_source>PM agent_invocation — 用户原始需求"设备类型区分"功能描述</input_source>
</file_header>

# 设备类型区分 — 需求规格说明书

## 执行摘要

### 业务背景

NetworkAgentDemo 是一个 LangGraph 网络自动化运维 Agent（Demo v0.2.0），实现"告警→诊断→修复→验证→关闭"的自动化工作流。**当前所有告警模拟和 AI 巡检都只能基于 mock 设备——即返回预设值的假设备。**（来源引用：PM Agent 调用块"项目背景"）

用户要求在现有 Mock 设备之外，新增一种具备交互能力的"模拟器设备（Switch Simulator）"类型，该模拟器需在指定端口提供可交互的 SSH 服务，支持心跳检测、端口查看、端口配置、系统资源监控等功能，并完整适配当前的 LLM 智能运维 Demo 场景。

### 需求总览

| 类别 | 数量 |
|------|------|
| 功能需求（REQ-FUNC） | 21 |
| 非功能需求（REQ-NFUNC） | 5 |
| 用户故事（US） | 15 |
| 已确认推断项 [CONFIRMED] | 5 条（REQ-FUNC-111、REQ-FUNC-121、REQ-NFUNC-101、REQ-NFUNC-102、REQ-NFUNC-105）— 用户已确认所有决策 |
| 验收标准（AC） | 38 |

## 功能需求（Functional Requirements）

### REQ-FUNC-101 — DeviceType 枚举定义

| 字段 | 内容 |
|------|------|
| ID | REQ-FUNC-101 |
| 描述 | 系统应当在 `src/models/enums.py` 中新增 `DeviceType` 枚举类，包含两个成员：`MOCK`（Mock 设备，返回预设值的假设备）和 `SIMULATOR`（交换机模拟器，具备可交互的 SSH 服务）。 |
| 来源引用 | 用户输入原文："Mock 设备：纯粹假的设备，直接返回预设值"；"模拟器设备（Switch Simulator）：交换机模拟器，能够在指定端口模拟 SSH 服务响应" |
| 优先级 | Must Have |
| 备注 | — |

### REQ-FUNC-102 — Device 模型扩展 device_type 字段

| 字段 | 内容 |
|------|------|
| ID | REQ-FUNC-102 |
| 描述 | 系统应当在 `src/database/device_models.py` 的 `Device` 类中新增 `device_type` 字段（String 类型，长度建议 20），默认值 `"MOCK"`，可选值为 `"MOCK"` 或 `"SIMULATOR"`，并在数据库迁移后支持按 device_type 筛选设备。 |
| 来源引用 | 用户输入原文："目前没有 `device_type` 字段，需要新增以区分 Mock 设备和模拟器设备"；现有代码：`device_models.py` 第 18-51 行 `Device` 类定义（当前无 device_type 字段） |
| 优先级 | Must Have |
| 备注 | 默认值 `"MOCK"` 保证向后兼容：现有设备在新字段加入后自动归类为 MOCK 类型 |

### REQ-FUNC-103 — Mock 设备行为保持

| 字段 | 内容 |
|------|------|
| ID | REQ-FUNC-103 |
| 描述 | 系统应当保持现有 Mock 设备行为不变：所有工具（SwitchConfigTool、SwitchDiagTool、BackupTool）在 device_type=MOCK 时，继续使用现有的 `MockSwitchConfigTool`、`MockSwitchDiagTool`、`MockBackupTool` 实现，不连接真实网络设备，返回预设模拟数据。 |
| 来源引用 | 用户输入原文："Mock 设备：纯粹假的设备，直接返回预设值"、"用于软件单元测试和集成测试"；现有代码：`switch_config_tool.py` 第 70-115 行 MockSwitchConfigTool、`switch_diag_tool.py` 第 173-245 行 MockSwitchDiagTool、`backup_tool.py` 第 148-216 行 MockBackupTool |
| 优先级 | Must Have |
| 备注 | 此为兼容性约束，确保现有工作流不受影响 |

### REQ-FUNC-104 — 模拟器设备注册

| 字段 | 内容 |
|------|------|
| ID | REQ-FUNC-104 |
| 描述 | 系统应当支持通过 API 创建 device_type=SIMULATOR 的设备，创建时需提供 device_name、device_ip、device_model、group_name 和 device_type，并在设备创建后自动初始化 SSH 凭据（可选，允许后续配置）。 |
| 来源引用 | 用户输入原文："在设备管理中增加两种设备类型的区分"；现有代码：`devices_router.py` 第 19-23 行 DeviceCreate schema（当前无 device_type）、第 75-85 行 create_device 端点 |
| 优先级 | Must Have |
| 备注 | — |

### REQ-FUNC-105 — 模拟器心跳检测

| 字段 | 内容 |
|------|------|
| ID | REQ-FUNC-105 |
| 描述 | 系统应当支持对 SIMULATOR 类型设备执行心跳检测，判断设备是否在线。心跳检测应包含 TCP 端口可达性探测（默认端口为设备配置的 SSH 端口，默认 22），并更新设备的 `status` 字段为 `"ONLINE"` 或 `"OFFLINE"`。 |
| 来源引用 | 用户输入原文："支持心跳检测，判断设备是否在线" |
| 优先级 | Must Have |
| 备注 | — |

### REQ-FUNC-106 — 模拟器 SSH 登录验证

| 字段 | 内容 |
|------|------|
| ID | REQ-FUNC-106 |
| 描述 | 模拟器设备应当在指定端口监听并接受 SSH 连接，支持用户名/密码认证方式。认证通过后返回模拟的交换机 CLI 提示符；认证失败时返回拒绝连接。SSH 凭据应从设备的 `DeviceCredential` 记录中读取（用户名、Fernet 加密密码、端口）。 |
| 来源引用 | 用户输入原文："支持 SSH 登录验证（用户名/密码认证）"；现有代码：`device_models.py` 第 54-78 行 DeviceCredential 类（ssh_username、ssh_password_encrypted、ssh_port） |
| 优先级 | Must Have |
| 备注 | 该功能需在模拟器进程中实现一个模拟 SSH 服务端 |

### REQ-FUNC-107 — 模拟器端口状态查看

| 字段 | 内容 |
|------|------|
| ID | REQ-FUNC-107 |
| 描述 | 模拟器设备应当支持查看交换机端口状态，包括每个端口的名称、状态（up/down/notconnect）、VLAN、双工模式（Duplex）、速率（Speed）、类型（Type）。返回格式应模拟真实交换机的 `show interface status` 命令输出。 |
| 来源引用 | 用户输入原文："支持查看交换机端口状态（up/down、速率、MAC 地址表等）" |
| 优先级 | Must Have |
| 备注 | — |

### REQ-FUNC-108 — 模拟器端口配置操作

| 字段 | 内容 |
|------|------|
| ID | REQ-FUNC-108 |
| 描述 | 模拟器设备应当支持对端口执行配置操作，至少包括：启用端口（no shutdown）、禁用端口（shutdown）、配置 VLAN（switchport access vlan N）、配置端口描述（description）。配置操作应返回模拟的成功/失败结果，且操作后端口状态应在后续查询中反映变更。 |
| 来源引用 | 用户输入原文："支持对端口进行配置操作（enable/disable、VLAN 等）" |
| 优先级 | Must Have |
| 备注 | 模拟器需维护内部状态以反映配置变更 |

### REQ-FUNC-109 — 模拟器 CPU/内存/IO 监控

| 字段 | 内容 |
|------|------|
| ID | REQ-FUNC-109 |
| 描述 | 模拟器设备应当支持查看 CPU 使用率、内存使用量、IO 使用情况。返回格式应模拟真实交换机的系统监控命令输出（如 `show processes cpu`、`show memory`、`show io`），包含模拟的百分比数值和进程列表。 |
| 来源引用 | 用户输入原文："支持查看 CPU、内存、IO 使用情况" |
| 优先级 | Should Have |
| 备注 | — |

### REQ-FUNC-110 — 模拟器 UP 端口详情查看

| 字段 | 内容 |
|------|------|
| ID | REQ-FUNC-110 |
| 描述 | 模拟器设备应当支持查看所有 UP（启用）状态的端口的详细速率、MAC 地址等状态信息。返回格式应模拟 `show interface {iface}` 的详细输出，包含带宽、MAC 地址、错误统计等字段。 |
| 来源引用 | 用户输入原文："支持查看各 UP 端口的速率、MAC 地址等状态信息" |
| 优先级 | Should Have |
| 备注 | — |

### REQ-FUNC-111 — 工具工厂策略扩展

| 字段 | 内容 |
|------|------|
| ID | REQ-FUNC-111 |
| 描述 | 系统应当将三个工具工厂函数（`create_switch_config_tool`、`create_switch_diag_tool`、`create_backup_tool`）从当前的 `use_mock: bool` 参数扩展为接受 `device_type: str` 参数。当 device_type=MOCK 时返回对应的 Mock 实现；当 device_type=SIMULATOR 时，**三个工具均**返回通过 SSH 与模拟器交互的新实现 [CONFIRMED — PM 确认: 不复用 Mock 实现，确保"诊断→修复→验证"闭环一致性]。 |
| 来源引用 | 用户输入原文："工具工厂策略扩展（根据 device_type 选择实现）"；现有代码：`switch_config_tool.py` 第 153-158 行、`switch_diag_tool.py` 第 284-289 行、`backup_tool.py` 第 255-260 行工厂函数（均仅接受 use_mock: bool） |
| 优先级 | Must Have |
| 备注 | — |

### REQ-FUNC-112 — API：设备类型字段支持

| 字段 | 内容 |
|------|------|
| ID | REQ-FUNC-112 |
| 描述 | 系统应当在以下 API 端点中增加 `device_type` 字段的支持：(a) DeviceCreate schema — 新增可选 `device_type` 字段，默认 `"MOCK"`；(b) DeviceUpdate schema — 新增可选 `device_type` 字段；(c) GET /api/devices 列表响应 — 每个设备对象包含 `device_type` 字段；(d) GET /api/devices/{id} 详情响应 — 包含 `device_type` 字段。 |
| 来源引用 | 用户输入原文："设备类型字段 + 模拟器专用端点"；现有代码：`devices_router.py` 第 19-31 行 DeviceCreate/DeviceUpdate schemas（当前无 device_type），第 42-70 行 list_devices 响应构建 |
| 优先级 | Must Have |
| 备注 | `device_type` 在创建时为可选参数，不传则默认 `"MOCK"`，保持向后兼容 |

### REQ-FUNC-113 — API：模拟器心跳端点

| 字段 | 内容 |
|------|------|
| ID | REQ-FUNC-113 |
| 描述 | 系统应当新增 API 端点 `POST /api/devices/{device_id}/heartbeat`，对指定 SIMULATOR 设备执行心跳检测（TCP 端口连接测试），返回设备在线状态 `{device_id, status: "ONLINE"|"OFFLINE", response_time_ms}`，并更新数据库中的设备状态。对于 device_type=MOCK 的设备，直接返回 `status: "UNKNOWN"` 并给出提示。 |
| 来源引用 | 用户输入原文："模拟器专用端点"、"支持心跳检测"；现有代码：`devices_router.py` 第 1-167 行（现有 7 个端点，需扩展） |
| 优先级 | Must Have |
| 备注 | — |

### REQ-FUNC-114 — API：模拟器端口操作端点

| 字段 | 内容 |
|------|------|
| ID | REQ-FUNC-114 |
| 描述 | 系统应当新增 API 端点 `GET /api/devices/{device_id}/ports` 查看模拟器的端口状态列表，以及 `POST /api/devices/{device_id}/ports/{port_name}/config` 对指定端口执行配置操作（enable/disable/set-vlan）。对于 device_type=MOCK 的设备，返回合适的错误提示。 |
| 来源引用 | 用户输入原文："支持查看交换机端口状态"、"支持对端口进行配置操作"；现有代码：`devices_router.py` |
| 优先级 | Should Have |
| 备注 | — |

### REQ-FUNC-115 — API：模拟器系统状态端点

| 字段 | 内容 |
|------|------|
| ID | REQ-FUNC-115 |
| 描述 | 系统应当新增 API 端点 `GET /api/devices/{device_id}/system`，用于查看模拟器设备的 CPU、内存、IO 使用情况。对于 device_type=MOCK 的设备，返回合适的错误提示。 |
| 来源引用 | 用户输入原文："支持查看 CPU、内存、IO 使用情况" |
| 优先级 | Should Have |
| 备注 | — |

### REQ-FUNC-116 — 前端：设备类型选择器

| 字段 | 内容 |
|------|------|
| ID | REQ-FUNC-116 |
| 描述 | 前端设备添加/编辑对话框（`DevicesListView.vue`）应当新增 `device_type` 下拉选择字段，选项为"Mock 设备 (MOCK)"和"模拟器设备 (SIMULATOR)"。添加设备时默认为 MOCK。编辑时显示当前设备的类型。 |
| 来源引用 | 用户输入原文："前端 UI 适配"；现有代码：`DevicesListView.vue` 第 45-63 行设备编辑对话框（当前表单字段为 device_name、device_ip、device_model、group_name，无 device_type） |
| 优先级 | Must Have |
| 备注 | — |

### REQ-FUNC-117 — 前端：设备类型展示列

| 字段 | 内容 |
|------|------|
| ID | REQ-FUNC-117 |
| 描述 | 前端设备列表表格应当新增"设备类型"列，以标签形式展示 MOCK 或 SIMULATOR，通过不同颜色区分（如 MOCK 为灰色 info 标签，SIMULATOR 为蓝色 primary 标签）。 |
| 来源引用 | 用户输入原文："前端 UI 适配"；现有代码：`DevicesListView.vue` 第 15-41 行设备表格（当前列为 device_name、device_ip、device_model、status、last_diag_at、凭据、操作） |
| 优先级 | Must Have |
| 备注 | — |

### REQ-FUNC-118 — 前端：模拟器操作面板

| 字段 | 内容 |
|------|------|
| ID | REQ-FUNC-118 |
| 描述 | 前端设备列表操作列应当为 SIMULATOR 类型设备增加额外的操作按钮，至少包括：(a) 心跳检测按钮（触发心跳检测）；(b) 查看端口按钮（跳转或弹窗展示端口状态）；(c) 系统监控按钮（展示 CPU/内存/IO）。MOCK 类型设备不展示这些按钮，或置灰不可用。 |
| 来源引用 | 用户输入原文："前端 UI 适配"、"所有功能需要适配当前 LLM 智能运维 Demo 场景"；现有代码：`DevicesListView.vue` 第 34-40 行操作列（当前按钮：编辑、凭据配置、删除） |
| 优先级 | Should Have |
| 备注 | — |

### REQ-FUNC-119 — Workflow：基于设备类型的工具选择

| 字段 | 内容 |
|------|------|
| ID | REQ-FUNC-119 |
| 描述 | LangGraph 工作流在执行 `establish_ssh`、`collect_diag`、`execute_fix`、`backup_config` 节点时，应当根据当前工作流上下文中设备的 `device_type` 字段自动选择正确的工具实现：(a) MOCK → 现有 Mock*Tool 实现；(b) SIMULATOR → 与模拟器 SSH 服务交互的新实现。 |
| 来源引用 | 用户输入原文："Workflow 集成适配"、"工作流需要能根据设备类型自动选择正确的工具实现"；现有代码：`main.py` 第 79-98 行工具初始化与 NodeHandlers 注入、`node_handlers.py` 第 76-94 行工具接收参数、第 302-303/620-621/715-716/910-911 行工具实际调用点 |
| 优先级 | Must Have |
| 备注 | 需在 workflow state 中传递 device_type，在节点处理函数中动态选择工具 |

### REQ-FUNC-120 — 巡检 CLI：设备类型感知诊断

| 字段 | 内容 |
|------|------|
| ID | REQ-FUNC-120 |
| 描述 | 巡检 CLI（`inspection_cli.py`）在执行设备诊断时，应当根据设备的 `device_type` 创建对应的诊断工具实例：(a) MOCK → `create_switch_diag_tool(device_type="MOCK")`；(b) SIMULATOR → `create_switch_diag_tool(device_type="SIMULATOR")`，需要传入设备凭据以建立 SSH 连接。 |
| 来源引用 | 用户输入原文："Workflow 集成适配"（巡检是 workflow 的一部分）；现有代码：`inspection_cli.py` 第 384-385 行 `create_switch_diag_tool(use_mock=True)` 硬编码 |
| 优先级 | Must Have |
| 备注 | — |

### REQ-FUNC-121 — 模拟器 SSH 服务生命周期管理 [CONFIRMED]

| 字段 | 内容 |
|------|------|
| ID | REQ-FUNC-121 |
| 描述 | 模拟器的 SSH 服务应当采用**手动触发**策略：(a) 设备创建后，SSH 服务默认不启动，需用户通过 API 端点 `POST /api/devices/{device_id}/simulator/start` 手动启动，启动时在设备配置的端口上开始监听；(b) 用户可通过 `POST /api/devices/{device_id}/simulator/stop` 停止 SSH 服务；(c) 设备删除时自动停止对应的 SSH 监听服务并释放端口；(d) 服务状态可通过 `GET /api/devices/{device_id}/simulator/status` 查询（返回 RUNNING / STOPPED / ERROR）。每台模拟器占用独立可配置 TCP 端口 [CONFIRMED — PM 确认: 手动触发策略，独立端口，start/stop API]。 |
| 来源引用 | 用户输入原文："能够在指定端口模拟 SSH 服务响应"；PM 确认决策：手动触发 + 独立端口 + start/stop API |
| 优先级 | Should Have |
| 备注 | — |

## 非功能需求（Non-Functional Requirements）

### REQ-NFUNC-101 — 性能：模拟器响应延迟

| 字段 | 内容 |
|------|------|
| ID | REQ-NFUNC-101 |
| 描述 | 模拟器设备对 SSH 命令的响应延迟不应严重劣化 Demo 体验。单条命令响应时间 ≤1s [CONFIRMED]，心跳检测响应时间 ≤3s [CONFIRMED]。 |
| 来源引用 | 用户输入原文："所有功能需要适配当前 LLM 智能运维 Demo 场景"（Demo 场景对响应速度有隐式要求）；现有代码：`switch_config_tool.py` 第 90 行 `time.sleep(0.5)` 定义了当前 Mock 延迟基线 |
| 优先级 | Should Have |
| 备注 | 具体阈值已由 PM 确认 |

### REQ-NFUNC-102 — 安全：模拟器凭据处理

| 字段 | 内容 |
|------|------|
| ID | REQ-NFUNC-102 |
| 描述 | 模拟器 SSH 服务在认证过程中接收的用户名/密码不得以明文写入日志文件或审计记录 [CONFIRMED]。密码在传输后仅用于内存中的认证比对，不得持久化到模拟器进程外。API 端点（心跳、端口操作等）应当受 JWT 认证保护，与现有 `/api/*` 路由安全策略一致。 |
| 来源引用 | 用户输入：无显式安全需求；基于现有安全体系推导：`device_models.py` 第 67 行 Fernet AES 加密存储密码、`main.py` 中 JWT 中间件保护 `/api/*` 路由 |
| 优先级 | Must Have |
| 备注 | 凭据落盘加密锚定于现有 Fernet 加密模式；明文日志禁写已由 PM 确认 |

### REQ-NFUNC-103 — 兼容性：现有 Mock 行为零变更

| 字段 | 内容 |
|------|------|
| ID | REQ-NFUNC-103 |
| 描述 | 引入 device_type 字段和模拟器设备后，所有现有 Mock 设备的工作流行为、API 响应格式、数据库记录必须保持完全不变。新增字段 `device_type` 需设置默认值 `"MOCK"`，确保已有设备在字段新增后自动归类为 MOCK 并保持原有功能。 |
| 来源引用 | 用户输入原文："用于软件单元测试和集成测试"（Mock 设备的原有用途不得破坏）、"不涉及真实网络协议"（Mock 设备行为边界）；现有代码：工具工厂函数 `use_mock=True` 默认值（`main.py` 第 79-81 行） |
| 优先级 | Must Have |
| 备注 | 核心兼容性约束 |

### REQ-NFUNC-104 — 兼容性：API 向后兼容

| 字段 | 内容 |
|------|------|
| ID | REQ-NFUNC-104 |
| 描述 | 所有现有 API 端点（`/api/devices` 系列）的请求和响应格式必须保持向后兼容：(a) `DeviceCreate` 的 `device_type` 为可选字段，不传默认 `"MOCK"`；(b) `GET /api/devices` 响应中新增 `device_type` 字段但不移除任何现有字段；(c) 现有前端未升级时仍可正常工作。 |
| 来源引用 | 用户输入：无显式兼容性要求；基于"Demo 场景"和现有代码结构推断；现有代码：`devices_router.py` 第 19-31 行 schemas（作为兼容基线） |
| 优先级 | Must Have |
| 备注 | — |

### REQ-NFUNC-105 — 可靠性：模拟器并发能力 [CONFIRMED]

| 字段 | 内容 |
|------|------|
| ID | REQ-NFUNC-105 |
| 描述 | Demo 场景下，模拟器 SSH 服务应支持至少同时处理 5 个并发 SSH 会话连接，不出现连接拒绝或数据混乱。当超过最大连接数时，应拒绝新连接并返回明确错误信息。 |
| 来源引用 | PM 确认决策：并发上限 = 5 [CONFIRMED] |
| 优先级 | Should Have |
| 备注 | — |

## 超出范围（Out of Scope）

以下功能明确排除在本需求范围之外：

| 序号 | 排除项 | 说明 |
|------|--------|------|
| OS-01 | TP-Link 真实设备集成 | `TpLinkSwitchConfigTool`、`TpLinkSwitchDiagTool`、`TpLinkBackupTool` 的 Netmiko 真实 SSH 实现保持 `NotImplementedError` 抛出状态，不属于本需求范围。来源：用户输入中只提到 Mock 设备和模拟器设备，未提 TP-Link。 |
| OS-02 | 生产级 SSH Server | 模拟器 SSH 服务仅满足 Demo 场景的功能验证需求，不实现完整的 SSH 协议（如密钥交换算法协商、会话复用、SFTP 子系统等）。来源：用户输入原文"交换机模拟器"定位为 Demo 用途。 |
| OS-03 | SNMP / NETCONF / RESTCONF 协议 | 模拟器仅通过 SSH CLI 方式交互，不支持其他网络管理协议。来源：用户输入中未提及。 |
| OS-04 | 模拟器设备的 VLAN 间路由 | 模拟器仅支持端口级 VLAN 配置（access port），不模拟三层 VLAN 间路由（SVI）功能。来源：用户输入原文"配置操作（enable/disable、VLAN 等）"未明确要求三层路由。 |
| OS-05 | 多设备分布式部署 | 模拟器进程仅在 NetworkAgentDemo 同一进程中运行，不支持跨主机部署。来源：Demo 项目定位。 |
| OS-06 | 数据库迁移工具（Alembic） | `device_type` 字段通过 ORM `create_all()` 自动同步，Demo 阶段不引入 Alembic 迁移。来源：现有架构使用 `Base.metadata.create_all()`，CLAUDE.md 明确标注 "no Alembic migrations in demo"。 |

## 已确认项（所有推断由 PM 确认通过）

| 编号 | 涉及需求 ID | 原推断内容 | 确认决策 | 风险等级 |
|------|------------|----------|----------|----------|
| INF-01 | REQ-FUNC-111 | config 和 backup 工具的模拟器实现策略 | **通过 SSH 与模拟器交互**，不复用 Mock 实现，确保闭环一致性 | 中 → 已消除 |
| INF-02 | REQ-FUNC-121 | SSH 服务生命周期管理策略 | **手动触发**策略，增加 start/stop API 端点；删除设备时自动停止 | 高 → 已消除 |
| INF-03 | REQ-NFUNC-105 | 模拟器并发连接数上限 | **5 个**并发会话 | 低 → 已消除 |
| INF-04 | REQ-NFUNC-101 | 性能阈值具体数值 | **单命令 ≤1s**、**心跳 ≤3s** | 低 → 已消除 |
| INF-05 | REQ-NFUNC-102 | 明文日志禁写约束 | **禁止**明文密码写入日志 | 低 → 已消除 |

## 已解决问题

| 编号 | 原问题 | 确认决策 |
|------|------|----------|
| Q-01 | 端口分配策略 | **每台模拟器独立 TCP 端口**，端口号可配置 |
| Q-02 | CPU/内存/IO 数据生成策略 | **动态随机值**，模拟真实设备波动 |
| Q-03 | 前端模拟器操作面板交互方式 | **内联弹窗/抽屉**，在当前设备列表页以内联方式交互 |

## 与现有架构的对齐说明

| 需求 ID | 影响的现有模块/文件 | 变更类型 |
|---------|---------------------|----------|
| REQ-FUNC-101 | `src/models/enums.py`（第 1-78 行） | 新增枚举类 |
| REQ-FUNC-102 | `src/database/device_models.py`（第 18-51 行 Device 类） | 新增字段 |
| REQ-FUNC-103 | `src/tools/switch_config_tool.py`、`switch_diag_tool.py`、`backup_tool.py` | 零变更（行为保持） |
| REQ-FUNC-104 | `src/api/devices_router.py`（第 19-23 行 DeviceCreate、第 75-85 行 create_device） | schema + 端点扩展 |
| REQ-FUNC-105 | `src/api/devices_router.py` | 新增端点 |
| REQ-FUNC-106 | 新增模块（模拟器 SSH 服务） | 新模块 |
| REQ-FUNC-107 | 新增模块（模拟器 SSH 服务） | 新模块 |
| REQ-FUNC-108 | 新增模块（模拟器 SSH 服务） | 新模块 |
| REQ-FUNC-109 | 新增模块（模拟器 SSH 服务） | 新模块 |
| REQ-FUNC-110 | 新增模块（模拟器 SSH 服务） | 新模块 |
| REQ-FUNC-111 | `src/tools/switch_config_tool.py`（第 153-158 行）、`switch_diag_tool.py`（第 284-289 行）、`backup_tool.py`（第 255-260 行） | 工厂函数签名扩展 |
| REQ-FUNC-112 | `src/api/devices_router.py`（schemas + 端点） | schema + 响应扩展 |
| REQ-FUNC-113 | `src/api/devices_router.py` | 新增端点 |
| REQ-FUNC-114 | `src/api/devices_router.py` | 新增端点 |
| REQ-FUNC-115 | `src/api/devices_router.py` | 新增端点 |
| REQ-FUNC-116 | `webui/src/views/devices/DevicesListView.vue`（第 45-63 行） | 新增表单字段 |
| REQ-FUNC-117 | `webui/src/views/devices/DevicesListView.vue`（第 15-41 行） | 新增表格列 |
| REQ-FUNC-118 | `webui/src/views/devices/DevicesListView.vue`（第 34-40 行） | 新增操作按钮 |
| REQ-FUNC-119 | `src/main.py`（第 79-98 行）、`src/orchestration/node_handlers.py`（第 76-94 行、第 302-303 行、第 620-621 行、第 715-716 行、第 910-911 行） | 工具选择逻辑变更 |
| REQ-FUNC-120 | `src/inspection_cli.py`（第 384-385 行） | 硬编码替换为动态选择 |
| REQ-FUNC-121 | `src/api/devices_router.py`（新增 start/stop/status 端点）<br>新增模块（模拟器生命周期管理） | 新增端点 + 新模块 |

---

*文档版本 0.1.0 | 状态 DRAFT | 生成时间 2026-07-14 | 作者 sub_agent_requirement_analyst*

<audit_log>
  <log time="2026-07-14T00:00:00Z" state="WRITE_FILES" action="file_write" result="SUCCESS" trace_id="inv-ds-group-a-001" file_path="project_workspace/device_simulator/requirements/ds_requirements_spec.md"/>
  <log time="2026-07-14T00:00:00Z" state="WRITE_FILES" action="file_write" result="SUCCESS" trace_id="inv-ds-group-a-001" file_path="project_workspace/device_simulator/requirements/ds_user_stories.md"/>
</audit_log>
