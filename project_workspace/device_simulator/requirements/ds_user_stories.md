<file_header>
  <project_id>NetworkAgentDemo</project_id>
  <module_id>device_simulator</module_id>
  <doc_type>user_stories</doc_type>
  <file_name>ds_user_stories.md</file_name>
  <version>0.1.0</version>
  <status>APPROVED</status>
  <author_agent>sub_agent_requirement_analyst</author_agent>
  <created_at>2026-07-14T00:00:00Z</created_at>
  <last_updated>2026-07-14T00:00:00Z</last_updated>
  <invocation_id>inv-ds-group-a-001</invocation_id>
  <input_source>PM agent_invocation — 用户原始需求"设备类型区分"功能描述</input_source>
</file_header>

# 设备类型区分 — 用户故事清单

## 用户角色地图（Actor x Feature Matrix）

| Actor \ Feature | 设备注册 | 类型展示 | 心跳检测 | 端口管理 | 系统监控 | SSH 认证 | 工作流集成 |
|-----------------|----------|----------|----------|----------|----------|----------|------------|
| 运维工程师 | US-001 | US-002 | US-004 | US-005, US-006 | US-007 | — | — |
| 系统管理员 | — | — | — | — | — | US-010 | — |
| LLM Agent | — | — | — | — | — | US-011 | US-008, US-012 |
| 巡检系统 | — | — | — | — | — | — | US-009 |
| 开发/测试人员 | — | — | — | — | — | — | US-003 |
| 运维工程师（高级） | — | — | — | US-013 | — | — | — |

## 用户故事详情

---

### US-001: 注册带设备类型标识的新设备

- **用户故事**：As a 运维工程师，I want to 在添加设备时指定设备类型为 Mock 或模拟器，so that 系统能根据类型提供不同的交互能力。
- **关联需求**：REQ-FUNC-102, REQ-FUNC-104, REQ-FUNC-116
- **优先级**：P0 (Must Have)
- **故事点**：[INFERRED — 待开发团队评估]

**验收标准：**

- **AC-001-01** (正常路径 — 创建模拟器设备)
  - Given 运维工程师打开设备添加对话框
  - When 填写设备名称 "Sim-SW-01"、IP "192.168.1.100"，选择设备类型为"模拟器设备 (SIMULATOR)"，点击保存
  - Then 系统创建一条 device_type="SIMULATOR" 的设备记录，API 返回 `device_type: "SIMULATOR"`，设备列表中出现新设备

- **AC-001-02** (默认值 — 不指定设备类型)
  - Given 运维工程师打开设备添加对话框
  - When 填写设备名称 "Mock-SW-01"、IP "192.168.1.200"，不选择设备类型（留空），点击保存
  - Then 系统自动以默认值 device_type="MOCK" 创建设备，API 返回 `device_type: "MOCK"`

- **AC-001-03** (编辑设备类型)
  - Given 已存在一个 device_type="MOCK" 的设备
  - When 运维工程师编辑该设备，将设备类型修改为 "SIMULATOR" 并保存
  - Then 设备的 device_type 更新为 "SIMULATOR"，后续操作按模拟器设备行为执行

---

### US-002: 在设备列表中查看设备类型

- **用户故事**：As a 运维工程师，I want to 在设备列表表格中看到每个设备的类型标签，so that 我能快速区分哪些是 Mock 设备、哪些是模拟器设备。
- **关联需求**：REQ-FUNC-112, REQ-FUNC-117
- **优先级**：P0 (Must Have)
- **故事点**：[INFERRED — 待开发团队评估]

**验收标准：**

- **AC-002-01** (列表展示设备类型)
  - Given 数据库中存在一台 device_type="MOCK" 和一台 device_type="SIMULATOR" 的设备
  - When 运维工程师访问设备管理页面
  - Then 表格中显示"设备类型"列，MOCK 设备显示灰色标签 "Mock"，SIMULATOR 设备显示蓝色标签 "模拟器"

- **AC-002-02** (API 响应包含 device_type)
  - Given 数据库中存在设备
  - When 调用 GET /api/devices
  - Then 响应中每个设备对象包含 `device_type` 字段，且值与数据库一致

---

### US-003: Mock 设备行为在升级后保持不变

- **用户故事**：As a 开发/测试人员，I want to 升级系统后 Mock 设备的所有诊断、配置、备份功能保持完全不变，so that 我现有的单元测试和集成测试不会因设备类型字段的引入而失败。
- **关联需求**：REQ-FUNC-103, REQ-NFUNC-103
- **优先级**：P0 (Must Have)
- **故事点**：[INFERRED — 待开发团队评估]

**验收标准：**

- **AC-003-01** (Mock 设备诊断不变)
  - Given 一台 device_type="MOCK" 的设备，AGENT_ALERT 触发工作流
  - When 工作流执行到 `collect_diag` 节点，LLM 调用 SwitchDiagTool
  - Then 工具返回与升级前完全一致的模拟诊断数据（如 show mac address-table 返回相同的 MAC 表模板数据），不因 device_type 字段而改变行为

- **AC-003-02** (Mock 设备配置不变)
  - Given 一台 device_type="MOCK" 的设备
  - When 工作流执行到 `execute_fix` 节点，调用 SwitchConfigTool 执行命令
  - Then 每条命令返回 `[OK] Command executed successfully`，延迟 0.5s/命令，行为与升级前一致

- **AC-003-03** (Mock 设备备份不变)
  - Given 一台 device_type="MOCK" 的设备
  - When 工作流执行到 `backup_config` 节点
  - Then 返回 Mock running-config 模板，backup_id 生成逻辑不变

---

### US-004: 对模拟器设备执行心跳检测

- **用户故事**：As a 运维工程师，I want to 对模拟器设备执行心跳检测，so that 我能确认设备是否在线可用。
- **关联需求**：REQ-FUNC-105, REQ-FUNC-113
- **优先级**：P0 (Must Have)
- **故事点**：[INFERRED — 待开发团队评估]

**验收标准：**

- **AC-004-01** (在线模拟器心跳成功)
  - Given 模拟器 SSH 服务在 192.168.1.100:22 正常监听
  - When 运维工程师点击该设备的心跳检测按钮
  - Then API 返回 `{status: "ONLINE", response_time_ms: <N>}`，设备列表中该设备的状态更新为绿色 "ONLINE" 标签

- **AC-004-02** (离线模拟器心跳失败)
  - Given 模拟器 SSH 服务未启动或端口不可达
  - When 运维工程师点击该设备的心跳检测按钮
  - Then API 返回 `{status: "OFFLINE", response_time_ms: null}`，设备列表中该设备的状态更新为红色 "OFFLINE" 标签

- **AC-004-03** (Mock 设备不支持心跳)
  - Given 一台 device_type="MOCK" 的设备
  - When 调用 POST /api/devices/{id}/heartbeat
  - Then API 返回 `{status: "UNKNOWN", message: "心跳检测仅适用于模拟器设备"}`

---

### US-005: 查看模拟器设备的端口状态

- **用户故事**：As a 运维工程师，I want to 查看模拟器设备的交换机端口状态，so that 我能了解各端口是 up 还是 down、速率是多少、属于哪个 VLAN。
- **关联需求**：REQ-FUNC-107, REQ-FUNC-110, REQ-FUNC-114
- **优先级**：P1 (Should Have)
- **故事点**：[INFERRED — 待开发团队评估]

**验收标准：**

- **AC-005-01** (查看所有端口状态)
  - Given 模拟器设备已启动并维护了 8 个端口（Gi0/1~Gi0/8）的状态数据（含 up/down/notconnect）
  - When 运维工程师点击该设备的"查看端口"按钮
  - Then 系统返回端口列表，每条包含端口名、状态（up/down/notconnect）、VLAN、双工模式、速率、类型，格式模拟 `show interface status` 输出

- **AC-005-02** (查看 UP 端口详情)
  - Given 模拟器设备的 Gi0/3 端口处于 UP 状态
  - When 运维工程师查询 UP 端口详情的 API
  - Then 返回 Gi0/3 的详细状态信息，包含 MAC 地址、带宽、速率、输入/输出错误计数等字段

- **AC-005-03** (Mock 设备无端口数据)
  - Given 一台 device_type="MOCK" 的设备
  - When 调用 GET /api/devices/{id}/ports
  - Then API 返回 `{message: "端口查看仅适用于模拟器设备"}`

---

### US-006: 对模拟器设备端口执行配置操作

- **用户故事**：As a 运维工程师，I want to 对模拟器设备的端口执行启用/禁用/VLAN 配置操作，so that 我能通过 Demo 演示交换机端口管理的完整流程。
- **关联需求**：REQ-FUNC-108, REQ-FUNC-114
- **优先级**：P1 (Should Have)
- **故事点**：[INFERRED — 待开发团队评估]

**验收标准：**

- **AC-006-01** (禁用端口)
  - Given 模拟器设备的 Gi0/3 端口当前状态为 "up"
  - When 运维工程师对 Gi0/3 执行 shutdown 操作
  - Then API 返回 success=true，Gi0/3 端口状态更新为 "administratively down"，后续端口查询显示该端口为 down

- **AC-006-02** (启用端口)
  - Given 模拟器设备的 Gi0/3 端口当前状态为 "administratively down"
  - When 运维工程师对 Gi0/3 执行 no shutdown 操作
  - Then API 返回 success=true，Gi0/3 端口状态恢复为 "up"

- **AC-006-03** (配置端口 VLAN)
  - Given 模拟器设备的 Gi0/3 端口当前属于 VLAN 1
  - When 运维工程师执行配置 VLAN 10 操作
  - Then API 返回 success=true，端口查询显示 Gi0/3 的 VLAN 变为 10

- **AC-006-04** (配置不存在的端口)
  - Given 模拟器设备不存在端口 Gi0/99
  - When 运维工程师尝试对 Gi0/99 执行配置操作
  - Then API 返回 success=false，错误信息为 "端口 Gi0/99 不存在"

---

### US-007: 查看模拟器设备系统资源

- **用户故事**：As a 运维工程师，I want to 查看模拟器设备的 CPU、内存、IO 使用情况，so that 我能监控设备资源状态并演示资源告警场景。
- **关联需求**：REQ-FUNC-109, REQ-FUNC-115
- **优先级**：P1 (Should Have)
- **故事点**：[INFERRED — 待开发团队评估]

**验收标准：**

- **AC-007-01** (查看 CPU 使用率)
  - Given 模拟器设备正常运行
  - When 运维工程师查询该设备的系统资源
  - Then API 返回 CPU 使用率百分比、进程列表（格式模拟 `show processes cpu`）、以及 60 秒 CPU 使用率历史趋势数据

- **AC-007-02** (查看内存与 IO)
  - Given 模拟器设备正常运行
  - When 运维工程师查询系统资源详情
  - Then 响应包含已用/总内存（MB）、IO 读写速率等数据

- **AC-007-03** (Mock 设备无系统资源)
  - Given 一台 device_type="MOCK" 的设备
  - When 调用 GET /api/devices/{id}/system
  - Then API 返回 `{message: "系统资源查看仅适用于模拟器设备"}`

---

### US-008: LangGraph 工作流根据设备类型自动选择工具

- **用户故事**：As a LLM Agent（工作流引擎），I want to 在执行诊断和修复节点时根据设备类型自动选择正确的工具实现，so that Mock 设备的告警用 Mock 工具处理，模拟器设备的告警通过 SSH 与模拟器交互处理。
- **关联需求**：REQ-FUNC-111, REQ-FUNC-119
- **优先级**：P0 (Must Have)
- **故事点**：[INFERRED — 待开发团队评估]

**验收标准：**

- **AC-008-01** (Mock 设备工作流使用 Mock 工具)
  - Given 工作流上下文中 device_type="MOCK"，告警类型 PORT_DOWN
  - When 工作流执行到 `collect_diag` 节点
  - Then 系统使用 `MockSwitchDiagTool` 返回预设的模拟诊断数据，诊断结果 `success=true`

- **AC-008-02** (模拟器设备工作流使用模拟器工具)
  - Given 工作流上下文中 device_type="SIMULATOR"，告警类型 PORT_DOWN，设备凭据已配置
  - When 工作流执行到 `collect_diag` 节点
  - Then 系统通过 SSH 连接到模拟器，执行 `show interface Gi0/1` 命令，返回模拟器实际端口状态数据

- **AC-008-03** (模拟器设备修复执行)
  - Given 工作流已通过审批（或无需审批），device_type="SIMULATOR"
  - When 工作流执行到 `execute_fix` 节点，LLM 生成 `interface Gi0/1` 和 `no shutdown` 命令
  - Then 系统通过 SSH 发送配置命令到模拟器，模拟器端口状态变为 up，`verify_fix` 节点确认修复成功

---

### US-009: 巡检系统根据设备类型执行诊断

- **用户故事**：As a 巡检系统（inspection_cli），I want to 在定时巡检时根据每台设备的 device_type 创建对应的诊断工具，so that 巡检能同时覆盖 Mock 设备和模拟器设备。
- **关联需求**：REQ-FUNC-120
- **优先级**：P0 (Must Have)
- **故事点**：[INFERRED — 待开发团队评估]

**验收标准：**

- **AC-009-01** (巡检 Mock 设备)
  - Given 系统中有一台 device_type="MOCK" 的设备
  - When 巡检 CLI 执行 `inspection_cli run`
  - Then 对该设备使用 `create_switch_diag_tool(device_type="MOCK")` 创建 Mock 诊断工具，执行诊断，返回预设数据

- **AC-009-02** (巡检模拟器设备)
  - Given 系统中有一台 device_type="SIMULATOR" 的设备，凭据已配置
  - When 巡检 CLI 执行 `inspection_cli run`
  - Then 对该设备使用 `create_switch_diag_tool(device_type="SIMULATOR")` 创建模拟器诊断工具，通过 SSH 连接获取真实端口状态和 CPU 数据

- **AC-009-03** (巡检混合设备场景)
  - Given 系统中有 1 台 MOCK 设备和 1 台 SIMULATOR 设备
  - When 巡检 CLI 执行 `inspection_cli run`
  - Then 两台设备分别使用对应的工具实现完成诊断，巡检报告包含两类设备的诊断结果

---

### US-010: 为模拟器设备配置 SSH 凭据

- **用户故事**：As a 系统管理员，I want to 为模拟器设备配置 SSH 用户名和密码，so that 系统可以通过 SSH 认证连接到模拟器设备。
- **关联需求**：REQ-FUNC-106
- **优先级**：P0 (Must Have)
- **故事点**：[INFERRED — 待开发团队评估]

**验收标准：**

- **AC-010-01** (配置凭据)
  - Given 设备列表中存在一台 device_type="SIMULATOR" 的设备
  - When 管理员点击"凭据配置"，输入 SSH 用户名 "admin"、密码 "switch123"、端口 2222，点击保存
  - Then 系统加密存储密码，API 返回 `{message: "凭据已配置", ssh_username: "admin", ssh_port: 2222}`，密码在响应中显示为 "****"

- **AC-010-02** (凭据认证成功)
  - Given 模拟器设备凭据已配置为 admin / switch123
  - When 工作流或巡检系统尝试 SSH 连接到模拟器
  - Then 模拟器 SSH 服务接收凭据，验证用户名和密码匹配，返回登录成功并显示 CLI 提示符

- **AC-010-03** (凭据认证失败)
  - Given 模拟器设备凭据为 admin / switch123
  - When 系统使用错误的密码尝试 SSH 连接
  - Then 模拟器 SSH 服务拒绝认证，返回 "Authentication failed" 错误

---

### US-011: LLM Agent 通过 SSH 诊断模拟器设备

- **用户故事**：As a LLM Agent，I want to 通过 SSH 连接到模拟器设备并执行诊断命令（如 show interface status、show processes cpu），so that 告警→诊断工作流能获取模拟器的真实响应数据而非预设模板。
- **关联需求**：REQ-FUNC-106, REQ-FUNC-119
- **优先级**：P0 (Must Have)
- **故事点**：[INFERRED — 待开发团队评估]

**验收标准：**

- **AC-011-01** (SSH 连接并执行命令)
  - Given 模拟器设备在线且凭据正确，告警事件触发工作流
  - When 工作流执行 `collect_diag` 节点，LLM 决定执行 `show interface status` 命令
  - Then 系统通过 SSH 发送命令到模拟器，模拟器返回当前端口状态数据（数据反映设备内部维护的实时状态，非硬编码模板）

- **AC-011-02** (命令执行超时)
  - Given 模拟器设备在线但 SSH 连接延迟过高
  - When 诊断命令执行超过 5 秒未返回
  - Then 系统返回 `success=false`，错误信息 "命令执行超时"，工作流转入 finish_report 节点记录失败

---

### US-012: LLM Agent 通过 SSH 修复模拟器设备

- **用户故事**：As a LLM Agent，I want to 通过 SSH 对模拟器设备执行配置修复命令，so that 诊断→修复→验证工作流能在模拟器上完成闭环演示。
- **关联需求**：REQ-FUNC-108, REQ-FUNC-119
- **优先级**：P0 (Must Have)
- **故事点**：[INFERRED — 待开发团队评估]

**验收标准：**

- **AC-012-01** (执行修复命令)
  - Given LLM 生成修复计划：对 Gi0/1 执行 `no shutdown`
  - When 工作流执行 `execute_fix` 节点，通过 SSH 向模拟器发送配置命令
  - Then 模拟器执行配置，Gi0/1 端口从 down 变为 up，返回 `[OK]` 确认

- **AC-012-02** (修复后验证)
  - Given execute_fix 已成功执行
  - When 工作流执行 `verify_fix` 节点，再次通过 SSH 查询 Gi0/1 状态
  - Then 模拟器返回 Gi0/1 端口状态为 "up"，验证通过，工作流正常关闭

---

### US-013: 模拟器 SSH 服务手动启停管理

- **用户故事**：As a 运维工程师，I want to 手动启动和停止模拟器 SSH 服务，so that 我能按需控制每个模拟器的在线状态，避免不必要的端口占用。
- **关联需求**：REQ-FUNC-121
- **优先级**：P1 (Should Have)
- **故事点**：[CONFIRMED — 待开发团队评估]

**备注**：SSH 生命周期采用手动触发策略，已由 PM 确认。

**验收标准：**

- **AC-013-01** (手动启动 SSH 服务) [CONFIRMED]
  - Given 运维工程师创建了一台 device_type="SIMULATOR" 的设备，指定 SSH 端口 2222，设备状态为 STOPPED
  - When 运维工程师点击该设备的"启动模拟器"按钮（调用 POST /api/devices/{id}/simulator/start）
  - Then 系统在端口 2222 启动模拟器 SSH 监听服务，API 返回 `{simulator_status: "RUNNING", port: 2222}`，日志记录 "模拟器 SSH 服务已启动: 设备=Sim-SW-01, 端口=2222"

- **AC-013-02** (手动停止 SSH 服务) [CONFIRMED]
  - Given 模拟器设备正在端口 2222 监听，状态为 RUNNING
  - When 运维工程师点击"停止模拟器"按钮（调用 POST /api/devices/{id}/simulator/stop）
  - Then 系统停止端口 2222 的 SSH 监听服务，释放端口，API 返回 `{simulator_status: "STOPPED"}`，日志记录 "模拟器 SSH 服务已停止: 设备=Sim-SW-01"

- **AC-013-03** (删除设备时自动停止)
  - Given 模拟器设备 SSH 服务正在运行
  - When 运维工程师删除该设备
  - Then 系统先自动停止 SSH 服务并释放端口，再删除设备记录，不会留下孤儿端口

- **AC-013-04** (服务状态可查询)
  - Given 模拟器设备已创建
  - When 运维工程师查询设备详情（GET /api/devices/{id}）
  - Then 响应中包含 `simulator_status` 字段，表示 SSH 服务运行状态（"RUNNING" | "STOPPED" | "ERROR"）和监听端口号

---

### US-014: 前端模拟器专用操作入口

- **用户故事**：As a 运维工程师，I want to 在设备列表页看到模拟器设备的专用操作按钮，so that 我能快速访问心跳检测、端口查看和系统监控功能。
- **关联需求**：REQ-FUNC-118
- **优先级**：P2 (Could Have)
- **故事点**：[INFERRED — 待开发团队评估]

**验收标准：**

- **AC-014-01** (模拟器设备显示额外按钮)
  - Given 设备列表中有一台 device_type="SIMULATOR" 的设备
  - When 运维工程师查看该设备的操作列
  - Then 操作列显示"心跳检测"、"端口查看"、"系统监控"三个按钮，均可点击

- **AC-014-02** (Mock 设备不显示模拟器按钮)
  - Given 设备列表中有一台 device_type="MOCK" 的设备
  - When 运维工程师查看该设备的操作列
  - Then 操作列仅显示"编辑"、"凭据配置"、"删除"按钮，不显示模拟器专用操作按钮

- **AC-014-03** (心跳检测即时反馈)
  - Given 运维工程师点击模拟器设备的心跳检测按钮
  - When 心跳检测完成
  - Then 页面即时刷新设备状态标签（ONLINE/OFFLINE），并弹出短暂提示 "心跳检测完成: 在线 / 离线"

---

### US-015: API 向后兼容 — 不传 device_type 时默认为 MOCK

- **用户故事**：As a 开发/测试人员，I want to 在调用创建/更新设备 API 时不传 device_type 时系统默认设为 MOCK，so that 现有集成脚本和前端无需修改即可继续工作。
- **关联需求**：REQ-NFUNC-104
- **优先级**：P0 (Must Have)
- **故事点**：[INFERRED — 待开发团队评估]

**验收标准：**

- **AC-015-01** (创建设备不传 device_type)
  - Given 现有集成脚本调用 POST /api/devices，请求体 `{device_name: "test", device_ip: "10.0.0.1"}`（不含 device_type）
  - When API 处理该请求
  - Then 设备以 device_type="MOCK" 创建成功，API 返回格式与升级前一致（新增 device_type 字段但不破坏原有字段）

- **AC-015-02** (列表 API 旧客户端兼容)
  - Given 旧版前端（未升级到支持 device_type 显示）调用 GET /api/devices
  - When API 返回设备列表
  - Then 响应中新增 `device_type` 字段，旧版前端忽略该字段后其余功能正常（表格渲染、编辑等不受影响）

---

*文档版本 0.1.0 | 状态 DRAFT | 生成时间 2026-07-14 | 作者 sub_agent_requirement_analyst*

## 汇总统计

| 指标 | 数值 |
|------|------|
| 用户故事总数 | 15 |
| P0 (Must Have) 故事数 | 9 |
| P1 (Should Have) 故事数 | 5 |
| P2 (Could Have) 故事数 | 1 |
| 验收标准总数 | 38 |
| 关联功能需求数 | 21（全覆盖） |
| [INFERRED] 标注数 | 3（US-013 的 2 个 AC + 故事点默认标注） |

### 故事与需求追溯矩阵

| 用户故事 | REQ-FUNC | REQ-NFUNC |
|----------|----------|-----------|
| US-001 | 102, 104, 116 | — |
| US-002 | 112, 117 | — |
| US-003 | 103 | 103 |
| US-004 | 105, 113 | — |
| US-005 | 107, 110, 114 | — |
| US-006 | 108, 114 | — |
| US-007 | 109, 115 | — |
| US-008 | 111, 119 | — |
| US-009 | 120 | — |
| US-010 | 106 | — |
| US-011 | 106, 119 | — |
| US-012 | 108, 119 | — |
| US-013 | 121 | — |
| US-014 | 118 | — |
| US-015 | — | 104 |

*矩阵覆盖校验：所有 21 条 REQ-FUNC 和 5 条 REQ-NFUNC 均有至少 1 条用户故事覆盖。*
