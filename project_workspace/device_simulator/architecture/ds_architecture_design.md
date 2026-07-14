<file_header>
  <project_id>NetworkAgentDemo</project_id>
  <module_id>device_simulator</module_id>
  <doc_type>architecture_design</doc_type>
  <file_name>ds_architecture_design.md</file_name>
  <version>0.1.0</version>
  <status>DRAFT</status>
  <author_agent>sub_agent_system_architect</author_agent>
  <created_at>2026-07-14T00:00:00Z</created_at>
  <last_updated>2026-07-14T00:00:00Z</last_updated>
  <invocation_id>inv-ds-group-b-001</invocation_id>
  <input_source>ds_requirements_spec.md (APPROVED), ds_user_stories.md (APPROVED), PM confirmed decisions</input_source>
</file_header>

# 设备类型区分 — 架构设计文档

## 架构概览

### 架构风格

**模块化分层单体（Modular Layered Monolith）** — 与现有 NetworkAgentDemo v0.2.0 架构风格完全一致。所有新增模块在同一 FastAPI 进程中运行，通过 Python 模块导入与接口契约实现层间解耦。

### 选型依据摘要

| 关键决策 | 选择 | 核心依据 |
|----------|------|----------|
| 设备类型建模 | String 枚举 + ORM 字段 | REQ-NFUNC-103 向后兼容；REQ-FUNC-101 可扩展性 |
| SSH 服务实现 | paramiko ServerInterface 进程内 | REQ-NFUNC-101 性能（≤1s）；Demo 场景零额外进程 |
| 工具工厂策略 | 简单 if-else 分支 | Demo 阶段 KISS 原则；预留注册表迁移路径 |
| API 端点组织 | 在 devices_router.py 内扩展 | REQ-NFUNC-104 API 兼容；设备操作内聚性 |
| 工作流集成 | Workflow State 传递 device_type + 惰性创建 | 低内存占用；按需求隔离 |
| 前端交互 | Element Plus Drawer 内联抽屉 | PM 确认决策（Q-03） |

---

## 架构决策记录（ADRs）

---

### ADR-DS-001: DeviceType 枚举定义与 Device 模型扩展

- **Status**: Accepted
- **Context**:
  当前 `Device` ORM 模型（`src/database/device_models.py` 第 18-51 行）没有任何设备类型区分字段。所有设备在工具层被一律视为 Mock 设备（`main.py` 第 79-81 行硬编码 `use_mock=True`）。需求要求新增 `DeviceType` 枚举以区分 Mock 设备和模拟器设备（REQ-FUNC-101），并扩展 Device 表字段以支持模拟器的端口和状态管理（REQ-FUNC-102、REQ-FUNC-121）。现有 Mock 设备行为必须零变更（REQ-NFUNC-103），且 API 必须向后兼容——不传 device_type 时默认 MOCK（REQ-NFUNC-104）。

- **Options**:

  - **Option A: String 枚举类 + device_type 字段（String(20)）+ simulator_port（Integer）+ simulator_status（String(15)）**
    - 描述：在 `enums.py` 新增 `DeviceType(str, Enum)` 枚举（MOCK / SIMULATOR），在 Device 表新增三个字段——`device_type`（String, 默认 "MOCK"）、`simulator_port`（Integer, 可空）、`simulator_status`（String, 默认 "STOPPED"）。`simulator_port` 为 NULL 时表示未分配；仅当 device_type=SIMULATOR 时有效。
    - 优点：类型安全（Python Enum 校验）；工具层可通过 `DeviceType.MOCK` / `DeviceType.SIMULATOR` 进行类型安全分发；三字段设计清晰分离关注点；预留未来扩展新设备类型（如 TP-Link 真实设备）。
    - 缺点：新增 3 个列导致 DDL 变更；需确保 `Base.metadata.create_all()` 自动添加列（SQLite ALTER TABLE ADD COLUMN 行为）。
    - 风险：中 — SQLite 不支持 ALTER TABLE 添加带 NOT NULL 默认值列（需 ORM detect）。

  - **Option B: Boolean is_simulator 字段**
    - 描述：仅在 Device 表新增一个 `is_simulator` Boolean（默认 False）。不引入枚举，通过 Boolean 区分 Mock/Simulator。
    - 优点：实现最简单；SQLite DDL 变更风险最低（单列 Boolean 默认值）。
    - 缺点：缺乏类型安全（布尔值易误读）；无法扩展至第三种设备类型（如未来的真实 TP-Link）；模拟器端口和状态无处存放（需额外表或序列化 JSON 字段）；与需求 REQ-FUNC-101 明确要求"枚举类"不吻合。
    - 风险：高 — 架构不可扩展，未来新增 TP-Link 真实设备时需重构。

- **Decision**: 选择 **Option A**。字符串枚举 `DeviceType` 提供类型安全与可扩展性，三字段设计（device_type + simulator_port + simulator_status）将模拟器元数据与核心设备信息解耦。理由：
  1. REQ-FUNC-101 明确要求"枚举类"（`MOCK` 和 `SIMULATOR` 两个成员）；
  2. 未来 TP-Link 真实设备可作为 `DeviceType.TPLINK` 平滑扩展（Option B 做不到）；
  3. `simulator_port` 和 `simulator_status` 字段是 REQ-FUNC-121（独立可配置端口 + start/stop/status API）的直接数据支撑。

- **Consequences**:
  - **正向**：支撑 REQ-FUNC-101/102/121/104 全部需求；工具工厂可按枚举类型安全分发；API 响应可携带完整模拟器元数据。
  - **负向**：SQLite `ALTER TABLE ADD COLUMN` 需 ORM 层处理（已确认 Demo 项目使用 `Base.metadata.create_all()`，SQLAlchemy 2.0 对 SQLite 的 DDL 支持需验证）。若 `create_all()` 在新列上不支持默认值，需在应用层补偿默认值逻辑。

---

### ADR-DS-002: 模拟器 SSH 服务架构

- **Status**: Accepted
- **Context**:
  模拟器设备需在指定端口提供可交互的 SSH 服务（REQ-FUNC-106），支持用户名/密码认证、CLI 命令解析（show interface status、show processes cpu 等，覆盖 REQ-FUNC-107/108/109/110）。SSH 生命周期手动触发——用户通过 API start/stop（REQ-FUNC-121），删除设备时自动停止。Demo 场景要求单命令响应 ≤1s（REQ-NFUNC-101），并发支持 5 个 SSH 会话（REQ-NFUNC-105）。密码不得明文写入日志（REQ-NFUNC-102）。不涉及生产级 SSH 协议实现（OS-02）。

- **Options**:

  - **Option A: paramiko ServerInterface 进程内 SSH 服务**
    - 描述：利用 Python `paramiko.ServerInterface` 在 FastAPI 进程内为每台模拟器启动一个后台线程（`threading.Thread`），该线程在独立 TCP 端口上运行 SSH 监听循环。`paramiko.Transport` 接受连接，ServerInterface 子类处理认证（`check_auth_password`）和通道请求（`check_channel_request`）。每个 SSH 会话（channel）启动独立线程处理命令交互循环（read → parse → execute → write response）。模拟器内部状态（端口 up/down、VLAN、CPU、内存等）通过内存数据结构维护，状态修改立即反映到后续查询。
    - 优点：
      1. 零新增依赖——`paramiko` 已是 NetworkAgentDemo 的隐式依赖（TpLink*Tool 预留的 Netmiko 底层依赖 paramiko）；
      2. 进程内架构：与 FastAPI 共享加密服务（Fernet 密码解密），生命周期管理简单（FastAPI lifespan 事件统一启停）；
      3. 线程模型轻量：符合 Demo 场景（OS-05 单进程）；
      4. 丰富生态：paramiko 文档和社区成熟，ServerInterface API 接口清晰。
    - 缺点：
      1. GIL 限制——Python 线程在 CPU 密集场景下性能有限，但 SSH 命令解析为 I/O 密集型，影响极小；
      2. 端口管理需自行实现（端口分配、回收、冲突检测）；
      3. 非生产级：paramiko ServerInterface 不实现完整 SSH 协议协商（密钥交换算法有限），但对 Demo 场景足够（OS-02 明确豁免）。

  - **Option B: 独立子进程 + 轻量 SSH 守护进程（如 dropbear/OpenSSH chroot）**
    - 描述：每台模拟器在独立子进程中运行一个轻量级 SSH 服务器（如 Python `subprocess.Popen` 启动 dropbear），通过文件系统 chroot 隔离环境。命令解析通过 shell 脚本或自定义假 shell 实现。
    - 优点：操作系统级进程隔离；标准 SSH 协议兼容性（真实 SSH 客户端体验）。
    - 缺点：
      1. 引入外部二进制依赖（dropbear/OpenSSH），违反"零/最小化新增依赖"约束；
      2. 进程管理复杂（僵尸进程、信号处理、graceful shutdown）；
      3. 状态同步困难——模拟器内部状态（端口 up/down、VLAN 等）需通过 IPC（管道/文件）传递回 FastAPI 进程；
      4. 不符合 OS-05（不跨主机部署，单进程内足够）；
      5. Windows 开发环境不可用（dropbear 类 Unix 依赖）。
    - 风险：高 — 违反技术约束，复杂度远超 Demo 场景需求。

- **Decision**: 选择 **Option A**。paramiko ServerInterface 进程内方案是 Demo 场景下的最优解。理由：
  1. **零新增依赖**——paramiko 已通过 Netmiko 间接存在于项目依赖中（`TpLinkSwitchConfigTool` 等预留实现引 Netmiko，Netmiko 依赖 paramiko）；
  2. **性能满足**——线程模型处理 ≤5 并发、单命令 ≤1s（REQ-NFUNC-101/105），I/O 密集型场景 GIL 不构成瓶颈；
  3. **架构简洁**——生命周期由 FastAPI lifespan 统一管理，删除设备可立即停止监听线程并释放端口（REQ-FUNC-121 自动停止要求）；
  4. **OS-02 豁免**——Demo 场景明确不要求完整 SSH 协议实现，paramiko ServerInterface 的认证+shell 通道足以达标。

- **Consequences**:
  - **正向**：支撑 REQ-FUNC-106/107/108/109/110（全部模拟器 SSH 交互功能）；满足 REQ-NFUNC-101 性能阈值（线程 I/O 延迟可控）；满足 REQ-NFUNC-105 并发能力（paramiko Transport 天然支持多通道）。
  - **负向**：
    1. 每台模拟器占用一条 TCP 端口 + 一条监听线程（需在 `simulator_port` 字段中记录，停服时释放）；
    2. paramiko 的 `Transport.start_server()` 是阻塞调用，需通过 `threading.Thread(daemon=True)` 包装，确保主进程退出时线程可被回收；
    3. `daemon=True` 线程在进程退出时被强制终止——需在 FastAPI shutdown 事件中显式调用 `transport.close()` 和 `thread.join(timeout=2)` 实现优雅关闭。

---

### ADR-DS-003: 工具工厂策略重构

- **Status**: Accepted
- **Context**:
  现有三个工具工厂函数均接受 `use_mock: bool` 参数（`switch_config_tool.py` 第 153 行、`switch_diag_tool.py` 第 284 行、`backup_tool.py` 第 255 行），二选一返回 Mock*Tool 或 TpLink*Tool（后者抛出 `NotImplementedError`）。需求 REQ-FUNC-111 要求将参数从 `use_mock: bool` 扩展为 `device_type: str`，以支持三种设备类型（MOCK → Mock*Tool、SIMULATOR → Simulator*Tool、未来 TPLINK → TpLink*Tool）。REQ-FUNC-103 约束 Mock 设备行为零变更。PM 确认：三种工具的模拟器实现 **均通过 SSH 与模拟器交互**，不复用 Mock 实现（INF-01）。

- **Options**:

  - **Option A: 策略注册表模式（Strategy Registry）**
    - 描述：在每个工具模块中维护一个 `_TOOL_REGISTRY: dict[str, type[Abstract*Tool]]`，工厂函数通过 `device_type` 键查找并实例化对应类。新增工具类型时仅需向注册表注册（Decorator 或显式 dict insert）。
    - 优点：符合开闭原则（对扩展开放，对修改关闭）；注册表一目了然，方便新增设备类型；解耦工厂逻辑与工具类定义。
    - 缺点：Demo 阶段仅有 2 种活跃类型（MOCK + SIMULATOR），注册表模式是"过度设计"（YAGNI）；引入 dict 查找间接层，增加调试难度；TP-Link 工具仍抛 `NotImplementedError`，注册意义不大。
    - 风险：低 — 过度工程化，但对 Demo 项目影响有限。

  - **Option B: 简单 if-else 分支**
    - 描述：修改工厂函数签名为 `create_*_tool(device_type: str = "MOCK")`，内部用 if-elif-else 分支分发。MOCK → Mock*Tool、SIMULATOR → Simulator*Tool、else → 抛出 `ValueError(f"Unknown device_type: {device_type}")`。TP-Link 分支保留（else 分支或显式 elif），但工厂不再自动路由到 TpLink*Tool。
    - 优点：实现最简单，代码变更量最小（修改 3 个工厂函数的签名 + 内部逻辑）；调用方代码变更直观可预测；符合 Demo 项目 KISS 原则；Mock 行为零变更（REQ-NFUNC-103 自然满足）。
    - 缺点：新增设备类型需修改工厂函数（违反 OCP），但 Demo 阶段扩展频率低；if-elif 链随类型增加会变长，但预期 ≤4 种类型（MOCK/SIMULATOR/TPLINK/未来）。
    - 风险：低 — 未来 TP-Link 启用时需再次修改工厂函数，但 Demo 项目演进时此为最小代价。

  - **Option C: 保留 `use_mock: bool`，新增 `simulator_mode: bool` 参数**
    - 描述：在保留 `use_mock` 的基础上新增 `simulator_mode` 参数，通过两个 Boolean 组合判断。此方案在分析阶段已被明确否决（因两个 Boolean 组合语义混乱，且 PM 确认三种工具均通过 SSH 交互）。
    - 此方案出于完整性列示，但已被 REQ-FUNC-111 的 INF-01 确认决策否决。

- **Decision**: 选择 **Option B**。简单 if-else 分支是 Demo 阶段的最优策略。理由：
  1. **KISS 原则**——Demo 项目仅需支持 2 种活跃类型 + 1 种预留类型，if-else 足够清晰；
  2. **变更量最小**——3 个工厂函数各修改 ~8 行代码，不需要新文件或装饰器基础设施；
  3. **向后兼容**——参数默认值 `"MOCK"` 确保现有调用方（`main.py` 第 79-81 行、`inspection_cli.py` 第 385 行）仅需将 `use_mock=True` 改为 `device_type="MOCK"`；
  4. **迁移路径清晰**——未来若设备类型超过 4 种，可重构为 Option A 注册表模式，当前 if-else 逻辑可直接映射为 dict lookup。

- **Consequences**:
  - **正向**：支撑 REQ-FUNC-103/111/119（工具选择全部需求）；Mock 工具行为完全不变（仅分发路径从 `if use_mock` 变为 `if device_type == "MOCK"`）；Simulator*Tool 可独立实现，无耦合。
  - **负向**：
    1. 工厂函数不再是"纯新增"（每次加类型需改 if-else），但 Demo 阶段可接受；
    2. 若未来 `device_type` 值不规范（如大小写），需在工厂函数入口做 `.upper()` 标准化或有额外的枚举校验层。
  - **迁移注意**：所有调用 `create_*_tool(use_mock=True)` 的代码需改为 `create_*_tool(device_type="MOCK")`——涉及 `main.py`（3 处）、`inspection_cli.py`（1 处）、`node_handlers.py`（需动态传入 device_type）。

---

### ADR-DS-004: API 端点扩展

- **Status**: Accepted
- **Context**:
  `devices_router.py` 现有 7 个端点（list、create、get、update、delete、credentials upsert、diagnostics）。需求要求：(a) 现有 endpoints 响应新增 `device_type` 字段（REQ-FUNC-112）；(b) 新增 7 个模拟器专用端点——heartbeat（REQ-FUNC-113）、ports（REQ-FUNC-114）、ports/{name}/config（REQ-FUNC-114）、system（REQ-FUNC-115）、simulator/start、simulator/stop、simulator/status（REQ-FUNC-121）。所有 `/api/*` 端点需 JWT 保护（REQ-NFUNC-102）。API 向后兼容——`DeviceCreate` 的 `device_type` 为可选字段（REQ-NFUNC-104、US-015）。

- **Options**:

  - **Option A: 在 devices_router.py 内扩展（Co-located）**
    - 描述：直接在 `devices_router.py` 中新增 7 个模拟器端点，DeviceCreate/DeviceUpdate schemas 新增 `device_type` 字段（Optional, 默认 "MOCK"），list_devices/get_device 响应构建中增加 `device_type`、`simulator_port`、`simulator_status` 字段。现有 7 个端点逻辑最小变更。
    - 优点：设备操作内聚性最强（所有 /api/devices/* 端点在同一个文件中）；JWT 保护复用现有 FastAPI 依赖注入；DeviceRepository 扩展也集中在同一文件；前端只需一个 API service 模块。
    - 缺点：`devices_router.py` 行数将从 ~167 行增长至 ~400 行；模拟器端点逻辑与 CRUD 逻辑在一个文件中，边界稍模糊；单一文件修改冲突风险增加（多人协作时需要串行）。
    - 风险：低 — 当前 21 个端点总量仍在单文件可维护范围内（参考 FastAPI 大型路由实践，400 行以内仍属健康）。

  - **Option B: 独立 simulator_router.py**
    - 描述：在 `src/api/` 下新建 `simulator_router.py`，前缀 `/api/devices/{device_id}/simulator`，包含全部模拟器专用端点。`devices_router.py` 仅做 schema 和响应扩展（device_type 字段），不新增端点。
    - 优点：关注点分离清晰——设备 CRUD vs 模拟器运维；文件更小、更易独立测试；未来若移除模拟器功能，仅需删除 `simulator_router.py`。
    - 缺点：跨文件依赖——simulator 端点需要 DeviceRepository 访问设备和凭据；路由注册需在 `main.py` 中额外引入 `simulator_router`；URL 前缀嵌套（`/api/devices/{device_id}/simulator/...` 与 `/api/devices/{device_id}/...` 在两个文件），路由阅读不直观。
    - 风险：低 — 跨文件引用合理，但与现有架构风格不一致（当前 8 个 API router 各管一个独立域名空间，而非按子资源拆分）。

- **Decision**: 选择 **Option A**。在 `devices_router.py` 内扩展方案更适合 Demo 场景。理由：
  1. **设备操作内聚**——心跳、端口查看、系统监控、模拟器启停均为设备的**操作**（而非独立资源），与设备 CRUD 天然属于同一 API 域；
  2. **schema 复用**——DeviceCreate/DeviceUpdate 扩展在同一个文件中，避免跨越文件的 schema 同步问题；
  3. **JWT 依赖注入复用**——`devices_router` 已绑定 `get_db` 依赖，新增端点自动继承；
  4. **现有架构一致性**——项目现有 8 个 router 均按业务领域（devices/alerts/workflow/approvals...）拆分，而非按操作类型。

- **Consequences**:
  - **正向**：支撑 REQ-FUNC-104/112/113/114/115/121 全部 API 需求；API 向后兼容（REQ-NFUNC-104）自然实现（DeviceCreate.device_type 为 Optional[str] = "MOCK"）。
  - **负向**：`devices_router.py` 从 ~167 行增至 ~400 行，需注意代码分区（用注释分隔 CRUD 区、模拟器操作区、Schema 定义区）；模拟器端点需对非 SIMULATOR 设备统一返回 400 错误（需新增一个 `_require_simulator` 辅助函数，避免重复校验逻辑）。

---

### ADR-DS-005: LangGraph Workflow 集成

- **Status**: Accepted
- **Context**:
  LangGraph 工作流在执行 `establish_ssh`、`collect_diag`、`execute_fix`、`backup_config` 节点时需根据设备的 `device_type` 选择正确的工具实现（REQ-FUNC-119）。巡检 CLI 同样需根据设备类型创建诊断工具（REQ-FUNC-120）。现有架构中，工具在 `main.py` 第 79-81 行全局初始化（硬编码 `use_mock=True`），`NodeHandlers` 构造函数接收工具实例（第 86-98 行），并在各节点处理函数中直接调用（`node_handlers.py` 第 302-303、620-621、715-716、910-911 行）。工作流 State（`NetworkAgentState` TypedDict）当前不含 `device_type` 字段。

- **Options**:

  - **Option A: Workflow State 传递 device_type + 惰性工具创建（Per-Workflow Lazy）**
    - 描述：在 `NetworkAgentState` 中新增 `device_type: str` 字段。工作流触发时（`receive_alert` → `get_device_info` 节点），从数据库查询设备记录的 `device_type` 并写入 state。后续节点（`collect_diag`、`execute_fix`、`backup_config`）的处理函数中，根据 `state["device_type"]` 动态调用 `create_*_tool(device_type=...)` 创建对应工具实例。`main.py` 中的全局工具初始化改为"默认工厂引用"，不再预先创建具体实例。`NodeHandlers` 改为接收工厂函数引用而非工具实例。
    - 优点：每个工作流实例使用正确的工具实现（完全解耦）；低内存占用（工具实例短生命周期，不常驻）；`device_type` 在 state 中全局可见，便于日志和审计（REQ-NFUNC-102 可记录"使用工具: SimulatorDiagTool"）。
    - 缺点：每个节点可能创建新工具实例（虽然有 overhead 但极小——Mock*Tool 无状态，Simulator*Tool 的 SSH 连接需连接池管理）；修改 `NetworkAgentState` 增加状态字段；需确认 LangGraph checkpointer（MemorySaver）对新增字段的兼容性。
    - 风险：中 — `NetworkAgentState` 变更可能影响现有工作流的 checkpointer 回溯兼容性。

  - **Option B: 全局预创建所有工具变体 + 运行时选择（Globally Pre-created）**
    - 描述：在 `main.py` 启动时预创建所有工具变体——`mock_diag_tool`、`simulator_diag_tool`、`mock_config_tool`、`simulator_config_tool`、`mock_backup_tool`、`simulator_backup_tool`。`NodeHandlers` 接收一个 `tool_selector(device_type, tool_name)` 函数，节点处理函数调用 `tool_selector(state["device_type"], "diag")` 获取正确的工具实例。
    - 优点：避免每次节点执行时创建新实例（性能开销最小）；工具实例常驻内存，生命周期清晰。
    - 缺点：Simulator*Tool 的 SSH 连接无法常驻（SSH 会话有超时，每台模拟器不同端口/凭据），预创建工具实例无法绑定特定 SSH 连接——仍需在运行时注入设备上下文（device_ip、auth）。这意味着 Simulator*Tool 在创建时不能建立连接，连接必须在 `_run()` 中按需建立，与 Option A 等价。
    - 风险：低 — 如果不强制预创建 SSH 连接，两种方案在 Simulator*Tool 行为上无本质差异。

- **Decision**: 选择 **Option A**。惰性创建方案在语义上更干净，且与 Simulator*Tool 的按需 SSH 连接模式天然一致。理由：
  1. Simulator*Tool 建立 SSH 连接需要**运行时参数**（device_ip、ssh_port、username、password），这些参数只有在工作流执行到具体节点时才从 state 中获取，预创建工具实例没有优势；
  2. `device_type` 写入 `NetworkAgentState` 后，可以在审计日志中记录每个节点使用的工具类型（REQ-NFUNC-102 合规需求）；
  3. `NodeHandlers` 的构造函数改动最小——改为接收三个工厂函数引用（`create_switch_diag_tool`、`create_switch_config_tool`、`create_backup_tool`），原工具实例参数改为工厂引用。

- **Consequences**:
  - **正向**：支撑 REQ-FUNC-119/120（工作流 + 巡检自动工具选择）；审计可追溯"节点 X 使用 SimulatorDiagTool 诊断设备 Y"（REQ-NFUNC-102）。
  - **负向**：
    1. `NetworkAgentState` TypedDict 新增 `device_type` 需兼容现有 MemorySaver 存储的旧 state（旧 state 不含该字段，读取时需 `state.get("device_type", "MOCK")` 兜底）；
    2. 每个节点可能创建新工具实例（每次 `create_*_tool()` 调用约 ~1ms Python 对象构造开销），对整体工作流延迟（秒级 LLM 推理主导）可忽略；
    3. Simulator*Tool 的 SSH 连接管理需配套（连接池/超时/复用），详见 MOD-DS-005。

---

### ADR-DS-006: 前端组件设计

- **Status**: Accepted
- **Context**:
  前端设备管理页面（`DevicesListView.vue`）需新增设备类型选择器（REQ-FUNC-116）、设备类型表格列（REQ-FUNC-117）、模拟器专用操作按钮（REQ-FUNC-118）。PM 确认（Q-03）：模拟器操作面板使用**内联弹窗/抽屉**交互方式。前端技术栈为 Vue 3 + Element Plus + TypeScript + Pinia（见 CLAUDE.md）。

- **Options**:

  - **Option A: Element Plus Drawer 内联抽屉 [CONFIRMED]**
    - 描述：为 SIMULATOR 设备提供"端口查看"、"系统监控"操作按钮，点击后在当前页面右侧滑出 Element Plus `<el-drawer>` 组件，内部渲染端口列表表格（带操作按钮）或系统资源图表/数据。心跳检测按钮直接触发 API 并即时刷新表格状态列。
    - 优点：体验流畅——Drawer 不阻断用户对设备列表的视野（对比 Modal 弹窗覆盖全屏）；组件复用——`<el-drawer>` 是 Element Plus 标准组件，支持 title、size、direction 等丰富配置；可嵌套多层（端口抽屉内可弹出端口配置小窗）；适合数据密集型展示（端口列表表格、CPU 趋势图表）。
    - 缺点：Drawer 宽度受限于屏幕（默认 30%），多端口或多图表场景可能需要更大空间（Element Plus Drawer 支持 `size="500px"` 或百分比，可配置）。

  - **Option B: 独立路由页面（Full Page Navigation）**
    - 描述：点击模拟器操作按钮后，通过 Vue Router 跳转到独立页面（如 `/devices/{id}/ports`、`/devices/{id}/system`），每个页面独立加载。
    - 优点：完全独立的页面布局空间（无 Drawer 宽度限制）；可通过 URL 直接访问和分享；页面级缓存和状态管理更独立。
    - 缺点：页面跳转导致设备列表上下文丢失；用户体验碎片化（每次操作需要前进/后退导航）；实现成本高（3+ 个新页面 + 路由配置 + 面包屑导航）；PM 已确认使用内联交互。

  - **Option C: 表格行内展开（Expandable Row）**
    - 描述：利用 `<el-table>` 的 `type="expand"` 属性，将端口数据和系统监控内联展开在设备表格行下方。
    - 优点：零额外组件——完全在表格内；信息密度高（所有设备数据一页可见）。
    - 缺点：端口列表（8+ 行）和系统监控（图表）展开后会严重拉长表格行，导致横向扫描断裂；心跳检测、start/stop 等操作按钮无处放置；不适合操作密集型面板。

- **Decision**: 选择 **Option A**（Element Plus Drawer）。此方案已由 PM 确认（Q-03 决策："内联弹窗/抽屉"）。理由：
  1. PM 直接确认——不需要重新评估；
  2. Drawer 在"不离开上下文 + 足够展示空间 + 可操作"三个维度上达到最优平衡；
  3. Element Plus Drawer 与现有 UI 体系一致（项目已使用 el-dialog、el-table、el-tag 等）；
  4. Pinia store 扩展后，Drawer 内的数据获取和状态管理均通过 store action 完成，与现有模式一致。

- **Consequences**:
  - **正向**：支撑 REQ-FUNC-116/117/118 全部前端需求；用户体验连贯（列表 + Drawer 无页面跳转）；实现成本可控。
  - **负向**：
    1. 需新增 2 个 Pinia store action：`fetchDevicePorts(deviceId)`、`fetchDeviceSystem(deviceId)`，以及对应的 API service 方法；
    2. Drawer 内的端口配置操作（enable/disable/set-vlan）需额外处理 optimistic UI 更新或操作后刷新逻辑；
    3. 模拟器 start/stop 按钮需与 Drawer 内的状态联动（如 STOPPED 状态下端口查看数据不可用，应显示提示）。

---

## 开放问题

| 编号 | 描述 | 状态 |
|------|------|------|
| — | 本架构设计文档中无 `[ASSUMPTION]` 标注项。所有决策均基于已 APPROVED 的需求条目和 PM 确认的 8 项决策（INF-01~05、Q-01~03）。 | 无开放项 |

---

*文档版本 0.1.0 | 状态 DRAFT | 生成时间 2026-07-14 | 作者 sub_agent_system_architect*

<audit_log>
  <log time="2026-07-14T00:00:00Z" state="WRITE_FILES" action="file_write" result="SUCCESS" trace_id="inv-ds-group-b-001" file_path="project_workspace/device_simulator/architecture/ds_architecture_design.md"/>
</audit_log>
