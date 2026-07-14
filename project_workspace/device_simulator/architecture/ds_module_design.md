<file_header>
  <project_id>NetworkAgentDemo</project_id>
  <module_id>device_simulator</module_id>
  <doc_type>module_design</doc_type>
  <file_name>ds_module_design.md</file_name>
  <version>0.1.0</version>
  <status>DRAFT</status>
  <author_agent>sub_agent_system_architect</author_agent>
  <created_at>2026-07-14T00:00:00Z</created_at>
  <last_updated>2026-07-14T00:00:00Z</last_updated>
  <invocation_id>inv-ds-group-b-001</invocation_id>
  <input_source>ds_requirements_spec.md (APPROVED), ds_user_stories.md (APPROVED), existing codebase analysis</input_source>
</file_header>

# 设备类型区分 — 模块设计文档

## 模块总览

| MOD-ID | 模块名 | 层级 | 文件路径 | 变更类型 | 职责 | 依赖于 |
|--------|--------|------|----------|----------|------|--------|
| MOD-DS-001 | DeviceType 枚举 | 数据模型 | `src/models/enums.py` | 扩展 | 定义 MOCK/SIMULATOR 设备类型枚举 | 无 |
| MOD-DS-002 | 扩展 Device ORM 模型 | 数据模型 | `src/database/device_models.py` | 扩展 | Device 表新增 device_type/simulator_port/simulator_status 三字段 | MOD-DS-001 |
| MOD-DS-003 | 模拟器 SSH 服务端 | 模拟器核心 | `src/simulator/ssh_server.py`（新） | 新增 | paramiko ServerInterface 封装，SSH 监听、认证、会话管理 | MOD-DS-004 |
| MOD-DS-004 | 模拟器状态管理器 | 模拟器核心 | `src/simulator/state_manager.py`（新） | 新增 | 维护端口/VLAN/CPU/内存/IO 等内存状态，提供读写接口 | 无 |
| MOD-DS-005 | 模拟器生命周期管理器 | 模拟器核心 | `src/simulator/lifecycle_manager.py`（新） | 新增 | 管理 SSH 服务启停、端口分配/释放、FastAPI lifespan 集成 | MOD-DS-002, MOD-DS-003 |
| MOD-DS-006 | SimulatorDiagTool | 工具层 | `src/tools/simulator_diag_tool.py`（新） | 新增 | 通过 SSH 客户端连接模拟器执行诊断命令 | MOD-DS-003（运行时）, paramiko |
| MOD-DS-007 | SimulatorConfigTool | 工具层 | `src/tools/simulator_config_tool.py`（新） | 新增 | 通过 SSH 客户端连接模拟器执行配置命令 | MOD-DS-003（运行时）, paramiko |
| MOD-DS-008 | SimulatorBackupTool | 工具层 | `src/tools/simulator_backup_tool.py`（新） | 新增 | 通过 SSH 客户端连接模拟器执行备份/回滚操作 | MOD-DS-003（运行时）, paramiko |
| MOD-DS-009 | 重构工具工厂函数 | 工具层 | 三个现有 `*_tool.py` 文件 | 修改 | device_type 参数化工厂分发（MOCK → Mock*Tool, SIMULATOR → Simulator*Tool） | MOD-DS-001, MOD-DS-006, MOD-DS-007, MOD-DS-008 |
| MOD-DS-010 | 扩展 Devices Router | API 层 | `src/api/devices_router.py` | 扩展 | Schema + 响应扩展，7 个新模拟器端点 | MOD-DS-002, MOD-DS-005, MOD-DS-004 |
| MOD-DS-011 | Workflow Node Handlers 适配 | 编排层 | `src/orchestration/node_handlers.py` | 修改 | 节点处理函数根据 device_type 动态创建/选择工具 | MOD-DS-009 |
| MOD-DS-012 | 巡检 CLI 适配 | 编排层 | `src/inspection_cli.py` | 修改 | 巡检根据设备 device_type 动态创建诊断工具 | MOD-DS-009, MOD-DS-002 |
| MOD-DS-013 | 前端 API Service 扩展 | 前端 | `webui/src/api/devices.ts` | 扩展 | 新增模拟器端点 TypeScript 类型和方法 | MOD-DS-010（API 契约） |
| MOD-DS-014 | 前端 Pinia Store 扩展 | 前端 | `webui/src/stores/devices.ts` | 扩展 | 新增 device_type 字段 + 模拟器操作 actions | MOD-DS-013 |
| MOD-DS-015 | 前端模拟器操作组件 | 前端 | `webui/src/views/devices/`（扩展现有+新增） | 新增+扩展 | 设备类型下拉、类型标签列、模拟器操作按钮、Drawer 面板 | MOD-DS-014, MOD-DS-001 |

---

## 模块详情

---

### MOD-DS-001: DeviceType 枚举

- **职责**: 定义设备类型的枚举常量，为所有模块提供类型安全的设备类型标识。
- **覆盖需求**: REQ-FUNC-101
- **覆盖用户故事**: US-001, US-002, US-008, US-009, US-014
- **变更文件**: `src/models/enums.py`（在现有 8 个枚举类之后追加）

- **公开接口契约**:
  ```
  IFC-DS-001-01: class DeviceType(str, Enum)
      Members:
          MOCK = "MOCK"       — Mock 设备，返回预设值的假设备
          SIMULATOR = "SIMULATOR" — 交换机模拟器，具备可交互 SSH 服务
      Usage: DeviceType("MOCK"), DeviceType.MOCK == "MOCK" (str Enum 继承)
  ```

- **依赖模块**: 无（基础枚举定义，无上游依赖）

- **外部依赖**: Python 标准库 `enum.Enum`（已有依赖）

- **设计说明**:
  - 继承 `str, Enum`（与现有 `AlertType`、`WorkflowStatus` 等风格一致），支持直接字符串比较和 JSON 序列化
  - 仅两个成员，未来可扩展 `TPLINK = "TPLINK"` 以支持真实设备（参见 ADR-DS-001）

---

### MOD-DS-002: 扩展 Device ORM 模型

- **职责**: 在现有 `Device` 表中新增 `device_type`、`simulator_port`、`simulator_status` 三个字段，支撑设备类型区分和模拟器元数据存储。
- **覆盖需求**: REQ-FUNC-102
- **覆盖用户故事**: US-001, US-004, US-013, US-015
- **变更文件**: `src/database/device_models.py`（`Device` 类，第 18-51 行之后追加三个 `mapped_column`）

- **公开接口契约**:
  ```
  IFC-DS-002-01: Device 表新增字段
      device_type: Mapped[str] = mapped_column(
          String(20), nullable=False, default="MOCK",
          comment="设备类型: MOCK / SIMULATOR"
      )
      simulator_port: Mapped[Optional[int]] = mapped_column(
          Integer, nullable=True, default=None,
          comment="模拟器 SSH 监听端口 (仅 SIMULATOR 有效)"
      )
      simulator_status: Mapped[Optional[str]] = mapped_column(
          String(15), nullable=True, default="STOPPED",
          comment="模拟器状态: RUNNING / STOPPED / ERROR"
      )

  IFC-DS-002-02: DeviceRepository 新增查询方法（建议，非强制接口）
      get_devices_by_type(db, device_type: str) → list[Device]
      update_simulator_status(db, device_id, status, port) → Device
  ```

- **依赖模块**: MOD-DS-001（DeviceType 枚举值用于校验和默认值）
- **外部依赖**: SQLAlchemy 2.0 `mapped_column`、`String`、`Integer`（已有依赖）

- **设计说明**:
  - `device_type` 默认 `"MOCK"` 保证向后兼容（REQ-NFUNC-103）——现有设备自动归类为 MOCK
  - `simulator_port` 和 `simulator_status` 对 MOCK 设备为 NULL/无关值，仅当 `device_type="SIMULATOR"` 时有意义
  - `Base.metadata.create_all()` 会在 SQLite 中自动执行 `ALTER TABLE ADD COLUMN`（SQLAlchemy 2.0 + SQLite 3.35+ 支持），详见 ADR-DS-001 Consequences

---

### MOD-DS-003: 模拟器 SSH 服务端

- **职责**: 基于 `paramiko.ServerInterface` 实现进程内 SSH 服务端，在指定 TCP 端口监听并接受 SSH 客户端连接，提供用户名/密码认证和 CLI 命令交互循环。
- **覆盖需求**: REQ-FUNC-106, REQ-FUNC-107, REQ-FUNC-108, REQ-FUNC-109, REQ-FUNC-110
- **覆盖用户故事**: US-004, US-005, US-006, US-007, US-010, US-011, US-012, US-013
- **新增文件**: `src/simulator/ssh_server.py`

- **公开接口契约**:
  ```
  IFC-DS-003-01: class SimulatorSSHServer
      __init__(state_manager: DeviceStateManager, host_key_path: Optional[str] = None)
          → 初始化 SSH 服务端实例，绑定状态管理器；host_key 默认自动生成临时 RSA key

      start(host: str, port: int, username: str, password: str) → threading.Thread
          → 在指定 host:port 启动 SSH 监听（阻塞调用，返回 daemon 线程）
          → 认证凭据: username/password（从 DeviceCredential 解密后传入）
          → 异常: PortConflictError (端口被占用), BindError (host 不可达)

      stop(timeout: float = 3.0) → None
          → 停止 SSH 监听，关闭所有活跃会话，释放端口，join 线程
          → timeout 秒后强制关闭

      active_session_count: int (property)
          → 当前活跃 SSH 会话数

  IFC-DS-003-02: class SimulatorServerInterface(paramiko.ServerInterface)
      check_auth_password(username: str, password: str) → int
          → 认证检查：比对内存中的凭据，成功返回 paramiko.AUTH_SUCCESSFUL，失败返回 paramiko.AUTH_FAILED
          → 密码比对后立即丢弃明文（不在任何日志中记录，REQ-NFUNC-102）

      check_channel_request(kind: str, chanid: int) → int
          → 仅允许 "session" 类型通道

  IFC-DS-003-03: class SimulatorSSHSession
      __init__(channel: paramiko.Channel, state_manager: DeviceStateManager)
          → 管理单个 SSH 会话的命令交互循环

      run() → None
          → 主循环: 发送 CLI 提示符 → 读取命令 → 解析/执行 → 写回响应
          → 支持的命令集见 IFC-DS-004-01
  ```

- **依赖模块**: MOD-DS-004（DeviceStateManager — 命令执行时查询/修改设备状态）
- **外部依赖**: `paramiko`（SSH 协议实现 —— Transport, ServerInterface, RSAKey, Channel。需确认项目依赖中已包含 paramiko，如未显式声明则新增）

- **设计说明**:
  - 线程模型：每台模拟器 = 1 个监听线程（`SimulatorSSHServer.start()`），每个 SSH 会话 = 1 个交互线程（`SimulatorSSHSession.run()`），最大会话数 = 5（REQ-NFUNC-105）
  - 命令执行时间目标 ≤1s（REQ-NFUNC-101），通过直接内存查询 MOD-DS-004 达成（无 I/O 开销）
  - 密码在 `check_auth_password` 中比对后不存储、不记录（REQ-NFUNC-102）
  - `stop()` 调用 `transport.close()` + `thread.join(timeout)`，确保端口释放（REQ-FUNC-121 删除时自动停止要求）

---

### MOD-DS-004: 模拟器状态管理器

- **职责**: 维护单台模拟器设备的运行时状态（端口列表、VLAN、CPU、内存、IO），提供命令解析和状态读写的纯内存数据结构。**注意：这是一个纯数据+逻辑模块，不包含 I/O 或网络操作。**
- **覆盖需求**: REQ-FUNC-107, REQ-FUNC-108, REQ-FUNC-109, REQ-FUNC-110
- **覆盖用户故事**: US-005, US-006, US-007
- **新增文件**: `src/simulator/state_manager.py`

- **公开接口契约**:
  ```
  IFC-DS-004-01: class DeviceStateManager
      __init__(device_name: str, num_ports: int = 8)
          → 初始化设备状态：8 个端口（Gi0/1~Gi0/8），默认状态混合 up/down/notconnect
          → CPU/内存初始化为随机基准值（30-50% CPU, 60-70% 内存）

      # ── 命令分发 ──
      execute_command(command: str) → str
          → 解析命令字符串，路由到对应处理函数，返回模拟的 CLI 输出文本
          → 支持的命令集:
            - show interface status          → 端口状态列表 (REQ-FUNC-107)
            - show interface {iface}         → 单端口详情 (REQ-FUNC-110)
            - show processes cpu             → CPU 进程列表 (REQ-FUNC-109)
            - show processes cpu history     → CPU 历史趋势 (REQ-FUNC-109)
            - show memory                    → 内存使用 (REQ-FUNC-109)
            - show io                        → IO 读写速率 (REQ-FUNC-109)
            - show running-config            → 模拟 running-config (REQ-FUNC-108 备份)
            - configure terminal             → 进入配置模式（返回提示符切换）
            - interface {iface}              → 进入接口配置模式
            - shutdown / no shutdown         → 端口禁用/启用 (REQ-FUNC-108)
            - switchport access vlan {N}     → VLAN 配置 (REQ-FUNC-108)
            - description {text}             → 端口描述 (REQ-FUNC-108)
            - exit                           → 退出配置模式
          → 不匹配的命令: 返回 "Invalid input detected at '^' marker"

      # ── 端口状态读写 ──
      get_all_ports() → list[PortState]
          → 返回全部 8 个端口的状态列表
          → PortState: {name, status (up/down/notconnect), vlan, duplex, speed, type, description}

      get_port(port_name: str) → PortState | None
          → 根据端口名查找，不存在返回 None (REQ-FUNC-108 错误处理)

      set_port_status(port_name: str, status: str) → bool
          → 更新端口状态（如 shutdown → "administratively down", no shutdown → "up"）

      set_port_vlan(port_name: str, vlan_id: int) → bool
          → 更新端口 VLAN (access port)

      set_port_description(port_name: str, desc: str) → bool
          → 更新端口描述

      # ── 系统资源 ──
      get_cpu_usage() → CPUStats
          → 返回: {usage_percent, processes: list[ProcessInfo], history_60s: list[int]}
          → 数值为动态随机生成，每次查询变化（模拟真实设备波动，Q-02 确认）

      get_memory_usage() → MemoryStats
          → 返回: {total_mb, used_mb, free_mb, usage_percent}

      get_io_stats() → IOStats
          → 返回: {read_kbps, write_kbps, read_iops, write_iops}

      get_running_config() → str
          → 根据当前端口状态/VLAN 动态生成 running-config 文本（不同于 Mock 静态模板）

      # ── 状态快照（供 API 端点直接查询）──
      get_system_snapshot() → dict
          → 返回 CPU + Memory + IO 的综合快照（供 GET /api/devices/{id}/system 使用）
  ```

- **依赖模块**: 无（纯内存数据结构，零外部依赖）
- **外部依赖**: Python 标准库 `random`, `dataclasses`, `re`（命令解析）

- **设计说明**:
  - 单模拟器对应单 `DeviceStateManager` 实例；实例生命周期与 SSH 服务生命周期一致（MOD-DS-005 管理）
  - 命令解析采用两层匹配：先精确匹配固定命令名，再前缀匹配（如 `show interface Gi0/1` 匹配 `show interface {iface}` 模板）
  - `get_running_config()` 动态生成确保"修复→验证"闭环一致性（REQ-FUNC-111 INF-01）——端口被 shutdown 后再查 running-config 能反映 `shutdown` 行

---

### MOD-DS-005: 模拟器生命周期管理器

- **职责**: 管理所有模拟器 SSH 服务的全局生命周期——启动/停止/状态查询、端口分配/释放、设备删除时的自动清理、FastAPI lifespan 集成。作为 MOD-DS-003（SSH 服务端）和 MOD-DS-010（API 端点）之间的协调层。
- **覆盖需求**: REQ-FUNC-121
- **覆盖用户故事**: US-013
- **新增文件**: `src/simulator/lifecycle_manager.py`

- **公开接口契约**:
  ```
  IFC-DS-005-01: class SimulatorLifecycleManager (Singleton)
      # ── 生命周期操作 ──
      start_simulator(device_id: int, device_name: str, host: str, port: int,
                      username: str, password: str) → StartResult
          → 创建 DeviceStateManager → 创建 SimulatorSSHServer → 启动监听线程
          → 返回: {success, simulator_status: "RUNNING", port, error?}
          → 异常: PortConflictError (端口已被占用), AlreadyRunningError (已启动)

      stop_simulator(device_id: int, timeout: float = 3.0) → StopResult
          → 查找设备对应的 SSH 服务 → stop() → 清理线程/状态
          → 返回: {success, simulator_status: "STOPPED", error?}
          → 若设备未运行: 返回 success=true（幂等性）

      get_simulator_status(device_id: int) → StatusResult
          → 返回: {simulator_status: "RUNNING"|"STOPPED"|"ERROR", port, active_sessions, uptime_seconds?}

      get_state_manager(device_id: int) → DeviceStateManager | None
          → 获取设备的状态管理器实例（供 API 端点查询端口/系统数据）

      # ── 端口管理 ──
      allocate_port(device_id: int, preferred_port: Optional[int] = None) → int
          → 分配一个未被占用的 TCP 端口（若 preferred_port 可用则优先使用，否则自动分配 2200-2300 范围）

      release_port(device_id: int) → None
          → 释放设备占用的端口

      # ── 清理操作 ──
      cleanup_device(device_id: int) → None
          → stop_simulator + release_port + 清理内存状态
          → 设备删除时调用 (REQ-FUNC-121 自动停止要求)

      shutdown_all(timeout: float = 5.0) → None
          → 停止所有运行中的模拟器，释放所有端口
          → FastAPI shutdown 事件中调用
  ```

- **依赖模块**:
  - MOD-DS-002（通过 DeviceRepository 读取设备信息和凭据）
  - MOD-DS-003（创建和管理 SimulatorSSHServer 实例）
  - MOD-DS-004（创建 DeviceStateManager 实例）

- **外部依赖**: Python 标准库 `threading`, `socket`（端口可用性检测）

- **设计说明**:
  - 单例模式：通过 `SimulatorLifecycleManager()` 获取全局唯一实例（与现有 `ConfigManager()`、`AuditLogger()` 风格一致）
  - 内部维护 `dict[int, _SimulatorContext]`（device_id → {server, state_manager, thread, port}）
  - 端口分配范围 2200-2300（避开系统端口 0-1023 和常见应用端口）
  - `cleanup_device` 在 `delete_device` API 端点中调用（ADM-DS-004 设计）

---

### MOD-DS-006: SimulatorDiagTool

- **职责**: 实现 `AbstractSwitchDiagTool` 的 SIMULATOR 变体——通过 SSH 客户端连接到模拟器 SSH 服务（MOD-DS-003），发送 `show` 命令并返回诊断结果。
- **覆盖需求**: REQ-FUNC-111（工具工厂策略 — SIMULATOR 分支）, REQ-FUNC-119（工作流诊断工具选择）
- **覆盖用户故事**: US-008, US-011
- **新增文件**: `src/tools/simulator_diag_tool.py`

- **公开接口契约**:
  ```
  IFC-DS-006-01: class SimulatorSwitchDiagTool(AbstractSwitchDiagTool)
      name: str = "switch_diag"
      description: str = "Execute diagnostic commands on switch simulator via SSH"

      _run(device_ip: str, command: str, auth: DeviceAuth) → DiagResult
          → 1. 使用 paramiko.SSHClient 连接模拟器 (device_ip:port)
          → 2. 通过 auth.username / auth.password 认证
          → 3. 发送 command，读取响应 (超时 5s)
          → 4. 断开连接，返回 DiagResult {success, output, execution_time_ms}
          → 连接失败: DiagResult(success=False, error="SSH connection failed: {reason}")
          → 命令超时: DiagResult(success=False, error="命令执行超时")
          → 注意: SSH 密码在日志中以 [REDACTED] 替换 (REQ-NFUNC-102)
  ```

- **依赖模块**:
  - MOD-DS-003（运行时依赖 — SSH 服务端必须已启动）
  - `AbstractSwitchDiagTool`（继承自现有 `switch_diag_tool.py` 抽象基类）

- **外部依赖**: `paramiko.SSHClient`（SSH 客户端），`time`（延迟/超时计算）

- **设计说明**:
  - 每次 `_run()` 调用独立建立/断开 SSH 连接（短连接模式），符合 Demo 场景（工作流节点调用频率低，秒级间隔）
  - 若未来需要高频调用，可引入 SSH 连接池（`paramiko.Transport` 复用），但 Demo 场景不需要
  - 超时设置：连接超时 3s + 命令执行超时 5s（参考 AC-011-02）

---

### MOD-DS-007: SimulatorConfigTool

- **职责**: 实现 `AbstractSwitchConfigTool` 的 SIMULATOR 变体——通过 SSH 客户端进入配置模式，执行配置命令序列，返回执行结果。
- **覆盖需求**: REQ-FUNC-111, REQ-FUNC-119
- **覆盖用户故事**: US-008, US-012
- **新增文件**: `src/tools/simulator_config_tool.py`

- **公开接口契约**:
  ```
  IFC-DS-007-01: class SimulatorSwitchConfigTool(AbstractSwitchConfigTool)
      name: str = "switch_config"
      description: str = "Execute configuration commands on switch simulator via SSH"

      _run(device_ip: str, commands: list[str], auth: DeviceAuth) → ConfigResult
          → 1. SSH 连接模拟器
          → 2. 发送 "configure terminal" 进入配置模式
          → 3. 逐条发送 commands（含 interface/sub-command），每条约 0.5s 模拟延迟
          → 4. 收集每条的 [OK] 或错误响应
          → 5. 发送 "exit" / "end" 退出
          → 6. 返回 ConfigResult {success, output, commands_executed, commands_failed}
  ```

- **依赖模块**:
  - MOD-DS-003（运行时依赖）
  - `AbstractSwitchConfigTool`（继承自现有 `switch_config_tool.py`）

- **外部依赖**: `paramiko.SSHClient`

- **设计说明**:
  - 配置命令是批量执行：`interface Gi0/1` + `shutdown` 作为两条独立命令发送（中间需等待提示符变化）
  - 模拟延迟 0.5s/条（与 MockSwitchConfigTool 第 90 行 `time.sleep(0.5)` 保持一致的技术基线，REQ-NFUNC-101 参考）
  - 配置变更持久化在 MOD-DS-004 的 DeviceStateManager 内存中（进程重启后重置，符合 Demo 定位）

---

### MOD-DS-008: SimulatorBackupTool

- **职责**: 实现 `AbstractBackupTool` 的 SIMULATOR 变体——通过 SSH 获取模拟器的 running-config（动态生成，反映当前端口/VLAN 状态），支持备份和回滚操作。
- **覆盖需求**: REQ-FUNC-111, REQ-FUNC-119
- **覆盖用户故事**: US-008
- **新增文件**: `src/tools/simulator_backup_tool.py`

- **公开接口契约**:
  ```
  IFC-DS-008-01: class SimulatorBackupTool(AbstractBackupTool)
      name: str = "config_backup"
      description: str = "Backup or rollback switch simulator configuration via SSH"

      _run(device_ip: str, auth: DeviceAuth, operation: str,
           backup_id: Optional[str] = None) → BackupResult | RollbackResult
          → backup: SSH 连接 → 执行 "show running-config" → 返回动态生成的配置文本
          → rollback: 使用内存中的备份存储恢复（与 MockBackupTool 模式一致）
  ```

- **依赖模块**:
  - MOD-DS-003（运行时依赖）
  - `AbstractBackupTool`（继承自现有 `backup_tool.py`）

- **外部依赖**: `paramiko.SSHClient`, `uuid`

- **设计说明**:
  - `show running-config` 返回由 MOD-DS-004 动态生成的配置（而非 Mock 的静态模板），反映实际端口/VLAN 状态
  - 回滚实现与 MockBackupTool 格式一致（基于 backup_id 从内存存储中恢复），便于两种类型统一处理

---

### MOD-DS-009: 重构工具工厂函数

- **职责**: 将三个现有工厂函数的参数从 `use_mock: bool` 改为 `device_type: str`，通过简单 if-else 分支分发到正确的实现类。
- **覆盖需求**: REQ-FUNC-103, REQ-FUNC-111
- **覆盖用户故事**: US-003, US-008, US-009
- **变更文件**:
  - `src/tools/switch_config_tool.py`（第 153-158 行 `create_switch_config_tool`）
  - `src/tools/switch_diag_tool.py`（第 284-289 行 `create_switch_diag_tool`）
  - `src/tools/backup_tool.py`（第 255-260 行 `create_backup_tool`）

- **公开接口契约**:
  ```
  IFC-DS-009-01: create_switch_config_tool(device_type: str = "MOCK") → AbstractSwitchConfigTool
      分支逻辑:
        device_type == "MOCK"       → MockSwitchConfigTool()  [行为零变更, REQ-FUNC-103]
        device_type == "SIMULATOR"  → SimulatorSwitchConfigTool()
        device_type == "TPLINK"     → TpLinkSwitchConfigTool() [预留, 抛出 NotImplementedError]
        else                        → raise ValueError(f"Unknown device_type: {device_type}")

  IFC-DS-009-02: create_switch_diag_tool(device_type: str = "MOCK") → AbstractSwitchDiagTool
      分支逻辑: 同上模式，SIMULATOR → SimulatorSwitchDiagTool()

  IFC-DS-009-03: create_backup_tool(device_type: str = "MOCK") → AbstractBackupTool
      分支逻辑: 同上模式，SIMULATOR → SimulatorBackupTool()
  ```

- **依赖模块**:
  - MOD-DS-001（DeviceType 枚举值 "MOCK" / "SIMULATOR"）
  - MOD-DS-006（SimulatorSwitchDiagTool 类）
  - MOD-DS-007（SimulatorSwitchConfigTool 类）
  - MOD-DS-008（SimulatorBackupTool 类）

- **外部依赖**: 无新增

- **设计说明**:
  - 参数默认值 `"MOCK"` 确保向后兼容（未传 device_type 的调用方自动使用 Mock 工具）
  - 工厂函数签名变更影响所有调用方：`main.py`（3 处）、`inspection_cli.py`（1 处）、`node_handlers.py`（4 处）
  - 目前 `TPLINK` 分支保留（路由到 TpLink*Tool，内部仍抛 `NotImplementedError`），确保现有 TpLink*Tool 类代码不被删除

---

### MOD-DS-010: 扩展 Devices Router

- **职责**: 扩展设备 API 端点——Schemas 新增 device_type 字段 + 现有端点响应新增 device_type/simulator 字段 + 新增 7 个模拟器专用端点（heartbeat、ports、ports/config、system、simulator/start、simulator/stop、simulator/status）。
- **覆盖需求**: REQ-FUNC-104, REQ-FUNC-105, REQ-FUNC-112, REQ-FUNC-113, REQ-FUNC-114, REQ-FUNC-115, REQ-FUNC-121
- **覆盖用户故事**: US-001, US-002, US-004, US-005, US-006, US-007, US-013, US-015
- **变更文件**: `src/api/devices_router.py`（扩展，~167 行 → ~400 行）

- **公开接口契约**:
  ```
  # ── Schema 扩展 ──
  IFC-DS-010-01: DeviceCreate 扩展
      + device_type: Optional[str] = "MOCK"       (新增可选字段, REQ-FUNC-112a)
      + simulator_port: Optional[int] = None       (新增可选字段, REQ-FUNC-104)

  IFC-DS-010-02: DeviceUpdate 扩展
      + device_type: Optional[str] = None          (新增可选字段, REQ-FUNC-112b)

  # ── 响应扩展 ──
  IFC-DS-010-03: list_devices / get_device 响应新增字段
      + device_type: str                           (REQ-FUNC-112c/112d)
      + simulator_port: Optional[int]
      + simulator_status: Optional[str]

  # ── 新增端点 ──
  IFC-DS-010-04: POST /api/devices/{device_id}/heartbeat
      → 仅 SIMULATOR: TCP 连接测试 → {status: "ONLINE"|"OFFLINE", response_time_ms}
      → MOCK 设备: {status: "UNKNOWN", message: "心跳检测仅适用于模拟器设备"}
      (REQ-FUNC-113, US-004)

  IFC-DS-010-05: GET /api/devices/{device_id}/ports
      → 仅 SIMULATOR: 从 MOD-DS-004 获取端口列表 → list[PortState]
      → MOCK 设备: {message: "端口查看仅适用于模拟器设备"}
      (REQ-FUNC-114, US-005)

  IFC-DS-010-06: POST /api/devices/{device_id}/ports/{port_name}/config
      Body: {action: "enable"|"disable"|"set-vlan", vlan_id?: int}
      → 仅 SIMULATOR: 调用 MOD-DS-004 端口操作 → {success, message}
      → MOCK 设备/端口不存在: 相应错误
      (REQ-FUNC-114, US-006)

  IFC-DS-010-07: GET /api/devices/{device_id}/system
      → 仅 SIMULATOR: 从 MOD-DS-004 获取系统快照 → {cpu, memory, io}
      → MOCK 设备: {message: "系统资源查看仅适用于模拟器设备"}
      (REQ-FUNC-115, US-007)

  IFC-DS-010-08: POST /api/devices/{device_id}/simulator/start
      → 1. 解密设备凭据 → 2. 调用 MOD-DS-005.start_simulator()
      → 返回: {simulator_status: "RUNNING", port: N}
      (REQ-FUNC-121, US-013 AC-013-01)

  IFC-DS-010-09: POST /api/devices/{device_id}/simulator/stop
      → 调用 MOD-DS-005.stop_simulator()
      → 返回: {simulator_status: "STOPPED"}
      (REQ-FUNC-121, US-013 AC-013-02)

  IFC-DS-010-10: GET /api/devices/{device_id}/simulator/status
      → 调用 MOD-DS-005.get_simulator_status()
      → 返回: {simulator_status, port, active_sessions}
      (REQ-FUNC-121, US-013 AC-013-04)
  ```

- **依赖模块**:
  - MOD-DS-002（Device + DeviceCredential ORM，通过 DeviceRepository）
  - MOD-DS-005（SimulatorLifecycleManager — start/stop/status/cleanup）
  - MOD-DS-004（DeviceStateManager — ports/system 查询）

- **外部依赖**: FastAPI `APIRouter`, `Depends`, Pydantic `BaseModel`（已有依赖）

- **设计说明**:
  - 所有新增端点均受 JWT 保护（通过 FastAPI `Depends(get_current_user)` 依赖注入，与现有端点一致）
  - 新增内部辅助函数 `_require_simulator(device_id, db)` → 校验设备存在且 device_type=SIMULATOR → 否则返回 400
  - `delete_device` 端点修改：删除前调用 `MOD-DS-005.cleanup_device(device_id)`（REQ-FUNC-121 AC-013-03）
  - `upsert_credentials` 端点不变（模拟器凭据存储沿用现有 Fernet 加密机制，REQ-NFUNC-102）

---

### MOD-DS-011: Workflow Node Handlers 适配

- **职责**: 修改 `NodeHandlers` 类，使其接收工具工厂函数引用（而非预创建的工具实例），各节点处理函数在运行时根据 state 中的 `device_type` 动态创建正确的工具实现。
- **覆盖需求**: REQ-FUNC-119
- **覆盖用户故事**: US-008
- **变更文件**: `src/orchestration/node_handlers.py` + `src/main.py`（NodeHandlers 构造调用）+ `src/models/state.py`（NetworkAgentState 新增字段）

- **公开接口契约**:
  ```
  IFC-DS-011-01: NodeHandlers 构造函数变更
      原:
        NodeHandlers(switch_config_tool=..., switch_diag_tool=..., backup_tool=..., ...)
      新:
        NodeHandlers(
            create_config_tool: Callable[[str], AbstractSwitchConfigTool],
            create_diag_tool: Callable[[str], AbstractSwitchDiagTool],
            create_backup_tool: Callable[[str], AbstractBackupTool],
            ...
        )

  IFC-DS-011-02: 节点内部工具获取模式
      def _collect_diag_node(self, state: NetworkAgentState):
          device_type = state.get("device_type", "MOCK")
          diag_tool = self.create_diag_tool(device_type)
          result = diag_tool._run(device_ip, command, auth)
          # ... 其余逻辑不变

  IFC-DS-011-03: NetworkAgentState 新增字段
      + device_type: str  (TypedDict 新增 key, 默认 "MOCK")

  IFC-DS-011-04: main.py 工具初始化变更
      原:
        switch_diag_tool = create_switch_diag_tool(use_mock=True)
        node_handlers = NodeHandlers(switch_diag_tool=switch_diag_tool, ...)
      新:
        node_handlers = NodeHandlers(
            create_diag_tool=create_switch_diag_tool,
            create_config_tool=create_switch_config_tool,
            create_backup_tool=create_backup_tool,
            ...
        )
  ```

- **依赖模块**: MOD-DS-009（三个工厂函数引用）
- **外部依赖**: 无新增

- **设计说明**:
  - `device_type` 写入 state 的时机：`get_device_info` 节点从数据库查询设备记录，将 `device_type` 写入 state
  - 存量工作流（MemorySaver 中持久化的旧 state）读取时用 `state.get("device_type", "MOCK")` 兜底（ADR-DS-005）
  - 涉及修改的节点：`establish_ssh`、`collect_diag`、`execute_fix`、`backup_config`（共 4 个节点）
  - `verify_fix` 节点也需适配（REQ-FUNC-119 虽未显式列举，但修复验证逻辑一致性需要）

---

### MOD-DS-012: 巡检 CLI 适配

- **职责**: 将巡检 CLI 中硬编码的 `create_switch_diag_tool(use_mock=True)`（`inspection_cli.py` 第 385 行）替换为根据设备 `device_type` 动态创建诊断工具。
- **覆盖需求**: REQ-FUNC-120
- **覆盖用户故事**: US-009
- **变更文件**: `src/inspection_cli.py`（第 384-385 行附近 `_inspect_device` 方法）

- **公开接口契约**:
  ```
  IFC-DS-012-01: _inspect_device 方法变更
      原:
        diag_tool = create_switch_diag_tool(use_mock=True)
      新:
        device_type = device.get("device_type", "MOCK")
        diag_tool = create_switch_diag_tool(device_type=device_type)
        # 若 device_type == "SIMULATOR": 需传入 auth（从设备凭据中获取）
  ```

- **依赖模块**:
  - MOD-DS-009（`create_switch_diag_tool` 工厂函数）
  - MOD-DS-002（通过 DeviceRepository 查询设备 device_type 字段）

- **外部依赖**: 无新增

- **设计说明**:
  - 巡检加载设备列表时（`_load_device_list` 方法），需在查询中 join `device_credentials` 表，并将 `device_type` 和凭据信息一并加载到设备 dict 中
  - SIMULATOR 设备的诊断需要 `DeviceAuth` 对象（含 decrypted password），需要在 `_inspect_device` 中通过 `encryption_service.decrypt()` 解密密码后才能创建 SSH 连接

---

### MOD-DS-013: 前端 API Service 扩展

- **职责**: 在前端 API service 层新增模拟器端点对应的 TypeScript 方法和类型定义。
- **覆盖需求**: REQ-FUNC-113, REQ-FUNC-114, REQ-FUNC-115, REQ-FUNC-121（API 消费端）
- **覆盖用户故事**: US-004, US-005, US-006, US-007, US-013
- **变更文件**: `webui/src/api/devices.ts`（扩展现有 devices API service）

- **公开接口契约**:
  ```
  IFC-DS-013-01: 新增类型定义
      interface DeviceType = 'MOCK' | 'SIMULATOR'
      interface SimulatorStatus = 'RUNNING' | 'STOPPED' | 'ERROR'
      interface PortState {
          name: string; status: string; vlan: number;
          duplex: string; speed: string; type: string; description?: string
      }
      interface SystemSnapshot { cpu: {...}; memory: {...}; io: {...} }

  IFC-DS-013-02: 新增 API 方法
      deviceHeartbeat(deviceId: number) → Promise<{status, response_time_ms}>
      getDevicePorts(deviceId: number) → Promise<PortState[]>
      configureDevicePort(deviceId: number, portName: string, action: string, vlanId?: number) → Promise<{success, message}>
      getDeviceSystem(deviceId: number) → Promise<SystemSnapshot>
      startSimulator(deviceId: number) → Promise<{simulator_status, port}>
      stopSimulator(deviceId: number) → Promise<{simulator_status}>
      getSimulatorStatus(deviceId: number) → Promise<{simulator_status, port, active_sessions}>
  ```

- **依赖模块**: MOD-DS-010（API 端点契约——URL 路径、请求/响应格式）
- **外部依赖**: `axios`（已有 HTTP 客户端）

---

### MOD-DS-014: 前端 Pinia Store 扩展

- **职责**: 扩展 `devicesStore`，新增 device_type 相关字段和模拟器操作 actions（心跳、端口查看、系统监控、启停）。
- **覆盖需求**: REQ-FUNC-116, REQ-FUNC-117, REQ-FUNC-118（前端状态管理层）
- **覆盖用户故事**: US-001, US-002, US-004, US-005, US-006, US-007, US-013
- **变更文件**: `webui/src/stores/devices.ts`（扩展现有 Pinia store）

- **公开接口契约**:
  ```
  IFC-DS-014-01: State 扩展
      + selectedDevicePorts: PortState[] | null     (当前查看的设备端口列表)
      + selectedDeviceSystem: SystemSnapshot | null  (当前查看的设备系统资源)
      + simulatorStatuses: Record<number, SimulatorStatus>  (设备ID → 模拟器状态缓存)

  IFC-DS-014-02: Actions 扩展
      + fetchDevicePorts(deviceId: number) → Promise<void>
      + configurePort(deviceId: number, portName: string, action: string, vlanId?: number) → Promise<boolean>
      + fetchDeviceSystem(deviceId: number) → Promise<void>
      + heartbeatDevice(deviceId: number) → Promise<{status, response_time_ms}>
      + startSimulator(deviceId: number) → Promise<boolean>
      + stopSimulator(deviceId: number) → Promise<boolean>
      + refreshSimulatorStatus(deviceId: number) → Promise<void>
  ```

- **依赖模块**: MOD-DS-013（API Service 方法）
- **外部依赖**: `pinia`（已有状态管理库）

---

### MOD-DS-015: 前端模拟器操作组件

- **职责**: 在设备列表页面新增设备类型下拉选择器、设备类型标签列、模拟器专用操作按钮，以及模拟器操作 Drawer（端口查看 + 系统监控）。
- **覆盖需求**: REQ-FUNC-116, REQ-FUNC-117, REQ-FUNC-118
- **覆盖用户故事**: US-001, US-002, US-014
- **变更文件**:
  - `webui/src/views/devices/DevicesListView.vue`（扩展模板 + 逻辑）
  - `webui/src/views/devices/SimulatorPortsDrawer.vue`（新增）
  - `webui/src/views/devices/SimulatorSystemDrawer.vue`（新增）

- **公开接口契约**:
  ```
  IFC-DS-015-01: DevicesListView.vue 模板扩展
      + 设备添加/编辑对话框: device_type 下拉选择器
          <el-select v-model="deviceForm.device_type">
            <el-option label="Mock 设备 (MOCK)" value="MOCK" />
            <el-option label="模拟器设备 (SIMULATOR)" value="SIMULATOR" />
          </el-select>

      + 设备表格新增列: "设备类型"（<el-table-column prop="device_type">）
          <el-tag :type="row.device_type==='SIMULATOR'?'primary':'info'">
            {{ row.device_type==='SIMULATOR'?'模拟器':'Mock' }}
          </el-tag>

      + 设备表格操作列扩展（仅 SIMULATOR 行显示）:
          v-if="row.device_type === 'SIMULATOR'"
            <el-button @click="handleHeartbeat(row)">心跳检测</el-button>
            <el-button @click="openPortsDrawer(row)">端口查看</el-button>
            <el-button @click="openSystemDrawer(row)">系统监控</el-button>
            <el-button @click="toggleSimulator(row)">
              {{ simulatorRunning(row.id) ? '停止' : '启动' }}
            </el-button>

  IFC-DS-015-02: SimulatorPortsDrawer.vue（新增组件）
      Props: { deviceId: number, deviceName: string }
      Template: <el-drawer> 内嵌 <el-table> 展示端口列表
      每行端口可操作: 启用/禁用/VLAN 配置按钮

  IFC-DS-015-03: SimulatorSystemDrawer.vue（新增组件）
      Props: { deviceId: number, deviceName: string }
      Template: <el-drawer> 内嵌 CPU/内存/IO 数据面板
      使用 Element Plus <el-progress> 展示使用率，<el-table> 展示进程列表
  ```

- **依赖模块**:
  - MOD-DS-014（Pinia store — 数据和 actions）
  - MOD-DS-001（DeviceType 枚举值 — 前端常量 `MOCK` / `SIMULATOR`）

- **外部依赖**: Vue 3, Element Plus (`el-drawer`, `el-table`, `el-tag`, `el-select`, `el-progress`, `el-button`)

- **设计说明**:
  - 模拟器启动/停止按钮使用切换式交互：状态 RUNNING → 显示"停止"，状态 STOPPED → 显示"启动"
  - 心跳检测按钮点击后即时更新设备状态列（乐观更新 + API 确认）
  - Drawer 内端口配置操作（enable/disable/set-vlan）通过 `el-popconfirm` 二次确认防止误操作
  - 所有模拟器专用按钮仅在 `row.device_type === 'SIMULATOR'` 时渲染（v-if），MOCK 行不显示

---

## 依赖关系图（文本格式）

```
# === 数据模型层 ===
MOD-DS-001 (DeviceType Enum)  [无依赖 — 基础枚举]

MOD-DS-002 (Device ORM)  →  MOD-DS-001
  理由: Device.device_type 字段引用 DeviceType 枚举值

# === 模拟器核心层 ===
MOD-DS-004 (State Manager)  [无依赖 — 纯内存数据结构]

MOD-DS-003 (SSH Server)  →  MOD-DS-004
  理由: SSH 命令处理时调用 DeviceStateManager.execute_command()

MOD-DS-005 (Lifecycle Manager)  →  MOD-DS-002, MOD-DS-003, MOD-DS-004
  理由: 通过 DeviceRepository 读取设备/凭据 (MOD-DS-002);
        创建 SimulatorSSHServer 实例 (MOD-DS-003);
        创建 DeviceStateManager 实例 (MOD-DS-004)

# === 工具层 ===
MOD-DS-006 (SimulatorDiagTool)  →  MOD-DS-003 [运行时], AbstractSwitchDiagTool
  理由: 通过 paramiko SSHClient 连接 MOD-DS-003 的服务端口

MOD-DS-007 (SimulatorConfigTool)  →  MOD-DS-003 [运行时], AbstractSwitchConfigTool
  理由: 同上 (SSH 配置命令通道)

MOD-DS-008 (SimulatorBackupTool)  →  MOD-DS-003 [运行时], AbstractBackupTool
  理由: 同上 (SSH 备份/回滚通道)

MOD-DS-009 (Tool Factories)  →  MOD-DS-001, MOD-DS-006, MOD-DS-007, MOD-DS-008
  理由: DeviceType 枚举值分发 (MOD-DS-001);
        SIMULATOR 分支实例化对应工具类 (MOD-DS-006/007/008)

# === API 层 ===
MOD-DS-010 (Devices Router)  →  MOD-DS-002, MOD-DS-005, MOD-DS-004
  理由: DeviceRepository CRUD (MOD-DS-002);
        LifecycleManager start/stop/status (MOD-DS-005);
        DeviceStateManager ports/system 查询 (MOD-DS-004)

# === 编排层 ===
MOD-DS-011 (Node Handlers)  →  MOD-DS-009
  理由: 通过工厂函数引用动态创建工具 (MOD-DS-009)

MOD-DS-012 (Inspection CLI)  →  MOD-DS-009, MOD-DS-002
  理由: 工厂函数动态创建诊断工具 (MOD-DS-009);
        DeviceRepository 查询 device_type (MOD-DS-002)

# === 前端层 ===
MOD-DS-013 (Frontend API Service)  →  MOD-DS-010 [API 契约]
  理由: TypeScript 方法调用后端 API 端点

MOD-DS-014 (Pinia Store)  →  MOD-DS-013
  理由: Store actions 调用 API Service 方法

MOD-DS-015 (Frontend Components)  →  MOD-DS-014, MOD-DS-001
  理由: 组件从 Store 获取数据 (MOD-DS-014);
        组件中使用 DeviceType 常量 (MOD-DS-001)
```

**循环依赖检查**: 已对所有 15 个模块的依赖关系进行拓扑排序验证，**无循环依赖**。依赖方向严格遵循分层架构（数据模型 → 核心 → 工具 → API → 编排 | 前端层独立）。

---

## REQ-FUNC 覆盖追溯表

| REQ-FUNC | 描述摘要 | 覆盖模块 | 覆盖状态 |
|----------|----------|----------|----------|
| REQ-FUNC-101 | DeviceType 枚举定义 | MOD-DS-001 | 完全覆盖 |
| REQ-FUNC-102 | Device 模型扩展 device_type 字段 | MOD-DS-002 | 完全覆盖 |
| REQ-FUNC-103 | Mock 设备行为保持 | MOD-DS-009 | 完全覆盖 |
| REQ-FUNC-104 | 模拟器设备注册 | MOD-DS-010 | 完全覆盖 |
| REQ-FUNC-105 | 模拟器心跳检测 | MOD-DS-010 | 完全覆盖 |
| REQ-FUNC-106 | 模拟器 SSH 登录验证 | MOD-DS-003 | 完全覆盖 |
| REQ-FUNC-107 | 模拟器端口状态查看 | MOD-DS-003, MOD-DS-004 | 完全覆盖 |
| REQ-FUNC-108 | 模拟器端口配置操作 | MOD-DS-003, MOD-DS-004 | 完全覆盖 |
| REQ-FUNC-109 | 模拟器 CPU/内存/IO 监控 | MOD-DS-003, MOD-DS-004 | 完全覆盖 |
| REQ-FUNC-110 | 模拟器 UP 端口详情查看 | MOD-DS-003, MOD-DS-004 | 完全覆盖 |
| REQ-FUNC-111 | 工具工厂策略扩展 | MOD-DS-009, MOD-DS-006, MOD-DS-007, MOD-DS-008 | 完全覆盖 |
| REQ-FUNC-112 | API 设备类型字段支持 | MOD-DS-010 | 完全覆盖 |
| REQ-FUNC-113 | API 模拟器心跳端点 | MOD-DS-010 | 完全覆盖 |
| REQ-FUNC-114 | API 模拟器端口操作端点 | MOD-DS-010 | 完全覆盖 |
| REQ-FUNC-115 | API 模拟器系统状态端点 | MOD-DS-010 | 完全覆盖 |
| REQ-FUNC-116 | 前端设备类型选择器 | MOD-DS-015 | 完全覆盖 |
| REQ-FUNC-117 | 前端设备类型展示列 | MOD-DS-015 | 完全覆盖 |
| REQ-FUNC-118 | 前端模拟器操作面板 | MOD-DS-015 | 完全覆盖 |
| REQ-FUNC-119 | Workflow 基于设备类型工具选择 | MOD-DS-011, MOD-DS-009 | 完全覆盖 |
| REQ-FUNC-120 | 巡检 CLI 设备类型感知诊断 | MOD-DS-012, MOD-DS-009 | 完全覆盖 |
| REQ-FUNC-121 | 模拟器 SSH 生命周期管理 | MOD-DS-005, MOD-DS-010 | 完全覆盖 |

**覆盖统计**: 21/21 REQ-FUNC 全部覆盖（100%）。每个需求条目均被至少一个模块完整支撑。

---

## REQ-NFUNC 覆盖追溯表

| REQ-NFUNC | 描述摘要 | 相关 ADR | 覆盖机制 |
|-----------|----------|----------|----------|
| REQ-NFUNC-101 | 性能：单命令 ≤1s，心跳 ≤3s | ADR-DS-002 | MOD-DS-003 内存查询无 I/O；MOD-DS-004 纯 CPU 计算；心跳为 TCP connect 探测 |
| REQ-NFUNC-102 | 安全：明文日志禁写，JWT 保护 | ADR-DS-002, ADR-DS-004 | MOD-DS-003 密码比对后丢弃；所有新增端点复用 JWT 依赖注入 |
| REQ-NFUNC-103 | 兼容性：Mock 行为零变更 | ADR-DS-001, ADR-DS-003 | MOD-DS-009 默认参数 "MOCK"；Mock*Tool 类代码零修改 |
| REQ-NFUNC-104 | 兼容性：API 向后兼容 | ADR-DS-004 | DeviceCreate.device_type Optional + 默认 "MOCK"；响应仅新增字段不移除 |
| REQ-NFUNC-105 | 可靠性：5 并发 SSH 会话 | ADR-DS-002 | MOD-DS-003 线程模型 + 最大会话数计数器 (Semaphore) |

**覆盖统计**: 5/5 REQ-NFUNC 全部覆盖（100%）。

---

*文档版本 0.1.0 | 状态 DRAFT | 生成时间 2026-07-14 | 作者 sub_agent_system_architect*

<audit_log>
  <log time="2026-07-14T00:00:00Z" state="WRITE_FILES" action="file_write" result="SUCCESS" trace_id="inv-ds-group-b-001" file_path="project_workspace/device_simulator/architecture/ds_module_design.md"/>
</audit_log>
