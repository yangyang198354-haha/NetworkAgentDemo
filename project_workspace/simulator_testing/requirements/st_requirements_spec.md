<file_header
  author_agent="sub_agent_requirement_analyst"
  project_name="NetworkAgentDemo"
  file_type="SPECIFICATION"
  phase="SIMULATOR_TESTING"
  version="0.1.0"
  status="APPROVED"
  created_utc="2026-07-18T00:00:00Z"
/>

# Simulator Testing Requirements Specification

## 执行摘要

- **业务背景**：NetworkAgentDemo 项目在 `project_workspace/src/simulator/` 和 `project_workspace/src/tools/simulator_*.py` 中实现了一套完整的 Cisco-like 网络交换机模拟器，包含状态管理、SSH 服务器、CLI 命令解析、独立进程服务、生命周期管理以及三个工具层封装（诊断、配置、备份）。当前所有模块代码已完成，需要进行全面的自动化测试覆盖。
- **需求总览**：共 4 个单元测试文件 + 2 个 E2E 测试文件 + 1 个测试编排脚本，覆盖 7 个源模块（4 个核心模拟器模块 + 3 个工具模块）。功能需求 26 条，非功能需求 7 条。
- **推断性需求**：2 条（占总需求 6.1%），均已标注 [INFERRED]。

---

## 功能需求（Functional Requirements）

### 测试文件 1：`test_simulator_state_manager.py`

| 字段 | 内容 |
|------|------|
| ID | REQ-FUNC-001 |
| 描述 | 系统应当测试 `DeviceStateManager` 初始化后创建 8 个 GigabitEthernet 端口（Gi0/1 至 Gi0/8），并验证每个端口的默认状态（status, vlan, description）与 `_init_ports()` 定义一致。 |
| 来源引用 | `state_manager.py:131-154`（`_init_ports()` 方法定义 8 端口默认值） |
| 优先级 | Must Have |
| 备注 | |

| 字段 | 内容 |
|------|------|
| ID | REQ-FUNC-002 |
| 描述 | 系统应当测试 `PortState` 数据类的 `effective_status()` 方法：当 `enabled=True` 时返回原始 status；当 `enabled=False` 时返回 "administratively down"。 |
| 来源引用 | `state_manager.py:48-52`（`effective_status()` 方法） |
| 优先级 | Must Have |
| 备注 | |

| 字段 | 内容 |
|------|------|
| ID | REQ-FUNC-003 |
| 描述 | 系统应当测试 `DeviceStateManager.get_all_ports()` 返回 8 个 `PortState` 对象的列表，每个对象含有 name, status, vlan, duplex, speed, description, mac_address, enabled 字段。 |
| 来源引用 | `state_manager.py:158-160`（`get_all_ports()` 方法） |
| 优先级 | Must Have |
| 备注 | |

| 字段 | 内容 |
|------|------|
| ID | REQ-FUNC-004 |
| 描述 | 系统应当测试 `DeviceStateManager.get_port(name)` 对存在的端口返回 `PortState` 对象，对不存在的端口返回 `None`。 |
| 来源引用 | `state_manager.py:162-164`（`get_port()` 方法） |
| 优先级 | Must Have |
| 备注 | |

| 字段 | 内容 |
|------|------|
| ID | REQ-FUNC-005 |
| 描述 | 系统应当测试 `DeviceStateManager.get_up_ports()` 仅返回 `effective_status() == "up"` 的端口。 |
| 来源引用 | `state_manager.py:166-168`（`get_up_ports()` 方法） |
| 优先级 | Must Have |
| 备注 | |

| 字段 | 内容 |
|------|------|
| ID | REQ-FUNC-006 |
| 描述 | 系统应当测试 `DeviceStateManager.configure_port()` 四种操作：`shutdown`（设置 enabled=False）、`no-shutdown`（设置 enabled=True）、`set-vlan`（更新 vlan 值，校验范围 1-4094）、`set-description`（更新 description 字段）。每个操作需验证返回的 (success: bool, message: str) 元组。 |
| 来源引用 | `state_manager.py:172-209`（`configure_port()` 方法） |
| 优先级 | Must Have |
| 备注 | |

| 字段 | 内容 |
|------|------|
| ID | REQ-FUNC-007 |
| 描述 | 系统应当测试 `configure_port()` 对无效端口名返回 `(False, "端口 XXX 不存在")`；对无效 VLAN ID（如 0, 4095, 非数字字符串）返回错误结果。 |
| 来源引用 | `state_manager.py:178-209`（`configure_port()` 中的错误分支） |
| 优先级 | Must Have |
| 备注 | |

| 字段 | 内容 |
|------|------|
| ID | REQ-FUNC-008 |
| 描述 | 系统应当测试 `get_cpu()` 返回 dict 包含 cpu_5s, cpu_1m, cpu_5m (float) 和 processes (list[dict])，且 CPU 值在 1.0-100.0 范围内。 |
| 来源引用 | `state_manager.py:213-243`（`get_cpu()` 方法） |
| 优先级 | Must Have |
| 备注 | |

| 字段 | 内容 |
|------|------|
| ID | REQ-FUNC-009 |
| 描述 | 系统应当测试 `get_memory_io()` 返回 dict 包含 memory_total_mb, memory_used_mb, memory_free_mb, memory_usage_pct, io_read_kbps, io_write_kbps，且数值在合理范围内。 |
| 来源引用 | `state_manager.py:245-260`（`get_memory_io()` 方法） |
| 优先级 | Must Have |
| 备注 | |

| 字段 | 内容 |
|------|------|
| ID | REQ-FUNC-010 |
| 描述 | 系统应当测试 `get_running_config()` 生成包含 hostname、VLAN 声明和所有 8 个接口的 running-config 文本，并正确反映端口 shutdown/enabled 状态。 |
| 来源引用 | `state_manager.py:264-294`（`get_running_config()` 方法） |
| 优先级 | Must Have |
| 备注 | |

### 测试文件 2：`test_simulator_ssh_server.py`

| 字段 | 内容 |
|------|------|
| ID | REQ-FUNC-011 |
| 描述 | 系统应当测试 `SimulatorCLI`（CLI 解析器），直接实例化进行单元测试（不依赖 paramiko），覆盖用户 EXEC 模式下所有 show 子命令：`show interface status`、`show interface <iface>`、`show processes cpu`、`show processes cpu history`、`show memory`、`show io`、`show mac address-table`、`show running-config`、`show logging`、`show version`。 |
| 来源引用 | `ssh_server.py:103-128`（`_exec_user_mode()` 方法）及 `213-261`（`_handle_show()` 路由表） |
| 优先级 | Must Have |
| 备注 | |

| 字段 | 内容 |
|------|------|
| ID | REQ-FUNC-012 |
| 描述 | 系统应当测试 `SimulatorCLI` 的 `configure terminal` 命令进入配置模式（`in_config_mode` 变为 True），以及 `exit`/`end` 退出配置模式回到 EXEC 模式。 |
| 来源引用 | `ssh_server.py:111-115`（configure terminal 进入）及 `135-142`（exit/end 退出） |
| 优先级 | Must Have |
| 备注 | |

| 字段 | 内容 |
|------|------|
| ID | REQ-FUNC-013 |
| 描述 | 系统应当测试 `SimulatorCLI` 的 `interface <iface>` 命令进入接口子模式（`current_interface` 被设置），以及 `exit` 从接口子模式退出到配置模式。 |
| 来源引用 | `ssh_server.py:145-151`（interface 命令）及 `135-142`（exit 退出接口子模式） |
| 优先级 | Must Have |
| 备注 | |

| 字段 | 内容 |
|------|------|
| ID | REQ-FUNC-014 |
| 描述 | 系统应当测试 `SimulatorCLI` 接口子模式下的所有配置命令：`shutdown`、`no shutdown`、`switchport access vlan <id>`、`switchport mode access`、`description <text>`，并验证命令执行后 `DeviceStateManager` 的状态变更。 |
| 来源引用 | `ssh_server.py:170-209`（`_exec_interface_mode()` 方法） |
| 优先级 | Must Have |
| 备注 | |

| 字段 | 内容 |
|------|------|
| ID | REQ-FUNC-015 |
| 描述 | 系统应当测试 `SimulatorCLI` 的错误处理：无效命令返回 `"% Unknown command: ..."`、无效接口名返回 `"% Invalid interface: ..."`、配置模式下无效输入返回 `"% Invalid input detected at '^' marker."`。 |
| 来源引用 | `ssh_server.py:128`, `148-149`, `168`, `209`（各错误返回语句） |
| 优先级 | Must Have |
| 备注 | |

| 字段 | 内容 |
|------|------|
| ID | REQ-FUNC-016 |
| 描述 | 系统应当测试 `SimulatorCLI` 的 `prompt` 属性在用户模式、配置模式、接口子模式下分别返回正确的 CLI 提示符字符串。 |
| 来源引用 | `ssh_server.py:78-85`（`prompt` 属性） |
| 优先级 | Should Have |
| 备注 | |

| 字段 | 内容 |
|------|------|
| ID | REQ-FUNC-017 |
| 描述 | 系统应当测试 `SimulatorSSHServer` 的公开 API：`start(host, port, username, password)` 启动服务器、`stop()` 停止服务器、`is_running` 状态属性、`host` 和 `port` 属性。 |
| 来源引用 | `ssh_server.py:637-738`（`SimulatorSSHServer` 类） |
| 优先级 | Should Have |
| 备注 | 此测试依赖 paramiko 进行实际 SSH 连接（类似集成测试）。若希望纯单元测试，可考虑 Mock paramiko Transport。[INFERRED — requires PM confirmation] |

### 测试文件 3：`test_simulator_service.py`

| 字段 | 内容 |
|------|------|
| ID | REQ-FUNC-018 |
| 描述 | 系统应当测试 `SimulatorService` 的 HTTP 管理 API 端点，使用 `_ManagementHandler` 直接发送 HTTP 请求或通过单元测试方式验证 5 个端点：`GET /health`（返回 status, device_name, ssh_port, ssh_running, uptime_seconds）、`GET /status`（返回 device_name, cpu, memory, io）、`GET /ports`（返回 ports 列表和 up_ports_detail）、`POST /ports/{name}/config`（配置端口并返回 success/message）、`POST /shutdown`（触发关机）。 |
| 来源引用 | `simulator_service.py:96-204`（5 个 handler 方法） |
| 优先级 | Must Have |
| 备注 | |

| 字段 | 内容 |
|------|------|
| ID | REQ-FUNC-019 |
| 描述 | 系统应当测试 `_ManagementHandler` 对无效路由返回 HTTP 404，对缺少 state_manager 时返回 HTTP 500。 |
| 来源引用 | `simulator_service.py:106`, `116`, `139`, `164`, `177`（错误分支） |
| 优先级 | Should Have |
| 备注 | |

| 字段 | 内容 |
|------|------|
| ID | REQ-FUNC-020 |
| 描述 | 系统应当测试 `_ManagementHandler.do_OPTIONS()` 返回 CORS 预检头（Access-Control-Allow-Origin, Allow-Methods, Allow-Headers）。 |
| 来源引用 | `simulator_service.py:118-124`（`do_OPTIONS()` 方法） |
| 优先级 | Could Have |
| 备注 | |

### 测试文件 4：`test_simulator_lifecycle_manager.py`

| 字段 | 内容 |
|------|------|
| ID | REQ-FUNC-021 |
| 描述 | 系统应当测试 `SimulatorLifecycleManager.allocate_ports()` 当无实例运行时返回 (2222, 9222) 配对端口；当指定 preferred_ssh 时若可用则返回配对端口；端口被占用时自动偏移到下一可用端口。 |
| 来源引用 | `lifecycle_manager.py:82-109`（`allocate_ports()` 方法） |
| 优先级 | Must Have |
| 备注 | |

| 字段 | 内容 |
|------|------|
| ID | REQ-FUNC-022 |
| 描述 | 系统应当测试 `SimulatorLifecycleManager.check_port_used()` 对空闲端口返回 False，对已占用端口返回 True。 |
| 来源引用 | `lifecycle_manager.py:70-80`（`check_port_used()` 静态方法） |
| 优先级 | Must Have |
| 备注 | |

| 字段 | 内容 |
|------|------|
| ID | REQ-FUNC-023 |
| 描述 | 系统应当测试 `SimulatorLifecycleManager.start_simulator()` 成功启动一个模拟器进程并返回 (True, message, ssh_port, mgmt_port)，以及 `stop_simulator()` 成功停止并释放端口。 |
| 来源引用 | `lifecycle_manager.py:165-291`（`start_simulator()` 和 `stop_simulator()` 方法） |
| 优先级 | Must Have |
| 备注 | |

| 字段 | 内容 |
|------|------|
| ID | REQ-FUNC-024 |
| 描述 | 系统应当测试 `SimulatorLifecycleManager.heartbeat()` 对运行中的模拟器 SSH 端口返回 (True, response_time_ms)，对不可达端口返回 (False, None)。 |
| 来源引用 | `lifecycle_manager.py:113-122`（`heartbeat()` 静态方法） |
| 优先级 | Should Have |
| 备注 | |

### 测试文件 5：`test_simulator_e2e.py`（E2E）

| 字段 | 内容 |
|------|------|
| ID | REQ-FUNC-025 |
| 描述 | 系统应当测试完整的 SSH 会话流程：使用 `SimulatorLifecycleManager` 启动模拟器进程，通过 paramiko SSHClient 连接到模拟器 SSH 端口，执行系列 show 命令（show version, show interface status, show running-config），执行配置命令（configure terminal → hostname → interface → shutdown → no shutdown → end），验证 running-config 反映变更，最后断开连接并清理进程。 |
| 来源引用 | `ssh_server.py`（SSH 协议层）、`state_manager.py`（状态管理）、`lifecycle_manager.py`（生命周期管理）的完整交互链路 |
| 优先级 | Must Have |
| 备注 | 标记 `@pytest.mark.e2e` |

### 测试文件 6：`test_simulator_tools_e2e.py`（E2E）

| 字段 | 内容 |
|------|------|
| ID | REQ-FUNC-026 |
| 描述 | 系统应当测试三个工具类对真实运行模拟器进程的端到端交互：(a) `SimulatorDiagTool` 通过 SSH exec channel 执行诊断命令并返回 `DiagResult`；(b) `SimulatorConfigTool` 通过 SSH shell channel 发送配置命令并返回 `ConfigResult`；(c) `SimulatorBackupTool` 执行备份（获取 running-config）和回滚（恢复之前备份的配置）。 |
| 来源引用 | `simulator_diag_tool.py:45-149`（`_run` + `_ssh_exec`）、`simulator_config_tool.py:42-179`（`_run` + `_read_channel`）、`simulator_backup_tool.py:57-217`（`_do_backup` + `_do_rollback`） |
| 优先级 | Must Have |
| 备注 | 标记 `@pytest.mark.e2e` |

---

## 非功能需求（Non-Functional Requirements）

| 字段 | 内容 |
|------|------|
| ID | REQ-NFUNC-001 |
| 描述 | 所有单元测试文件应当使用 `pytest` 框架，测试类使用 `class TestXxx:` 命名，测试方法使用 `test_xxx` 命名，符合项目 `tests/` 目录下的现有模式。 |
| 来源引用 | `project_workspace/tests/test_config_manager.py:10-71`（现有 TestConfigManager 类模式） |
| 优先级 | Must Have |
| 备注 | |

| 字段 | 内容 |
|------|------|
| ID | REQ-NFUNC-002 |
| 描述 | E2E 测试文件必须标记 `@pytest.mark.e2e`，以便 CI pipeline 的单元测试作业能够通过 `-k "not e2e"` 排除。 |
| 来源引用 | `project_workspace/CLAUDE.md: "E2E tests only on workflow_dispatch"` — CI 中仅在工作流手动触发时运行 E2E |
| 优先级 | Must Have |
| 备注 | 标记为 `@pytest.mark.e2e`（类级别或函数级别） |

| 字段 | 内容 |
|------|------|
| ID | REQ-NFUNC-003 |
| 描述 | 耗时较长的测试（如涉及端口分配范围扫描、进程启动等待的测试）需标记 `@pytest.mark.slow`，以便 CI 中可通过 `-k "not slow"` 排除。 |
| 来源引用 | `project_workspace/CLAUDE.md: "pytest markers: slow (deselect with -k 'not slow'), e2e"` |
| 优先级 | Must Have |
| 备注 | 具体标记范围：启动实际模拟器进程的测试、心跳超时测试 [INFERRED — requires PM confirmation on which specific tests to mark as slow] |

| 字段 | 内容 |
|------|------|
| ID | REQ-NFUNC-004 |
| 描述 | 测试文件应当遵循项目现有 import 约定：通过 `from src.simulator.xxx import Xxx` 导入被测模块，确保 `project_workspace` 在 `sys.path` 上（由 `conftest.py` 保证）。 |
| 来源引用 | `project_workspace/tests/conftest.py:18-20`（`_project_root` 插入 `sys.path`） |
| 优先级 | Must Have |
| 备注 | |

| 字段 | 内容 |
|------|------|
| ID | REQ-NFUNC-005 |
| 描述 | 测试执行脚本 `run_simulator_tests.sh` 应当执行以下步骤顺序：(1) 仅运行单元测试（排除 e2e 和 slow），(2) 运行 E2E 测试，(3) 报告所有结果。任意步骤失败应报告非零退出码。 |
| 来源引用 | PM 的调用指令：`Goal: 100% pass rate for all new tests` 和两步执行要求 |
| 优先级 | Must Have |
| 备注 | |

| 字段 | 内容 |
|------|------|
| ID | REQ-NFUNC-006 |
| 描述 | SSH 服务器单元测试（`test_simulator_ssh_server.py`）应当直接测试 `SimulatorCLI` 类（CLI 解析器），避免依赖 paramiko 库进行 SSH 连接，以保持单元测试的隔离性和执行速度。 |
| 来源引用 | PM 指令："For SSH server tests, consider mocking paramiko or testing the CLI parser directly" |
| 优先级 | Must Have |
| 备注 | |

| 字段 | 内容 |
|------|------|
| ID | REQ-NFUNC-007 |
| 描述 | E2E 测试应当使用 `SimulatorLifecycleManager` 管理模拟器进程生命周期（测试前启动、测试后清理），确保不遗留孤立进程。 |
| 来源引用 | PM 指令："use SimulatorLifecycleManager to start a real simulator process, run tests against it, then clean up" |
| 优先级 | Must Have |
| 备注 | |

---

## 超出范围（Out of Scope）

- 对 `src/tools/switch_diag_tool.py`、`src/tools/switch_config_tool.py`、`src/tools/backup_tool.py` 中抽象基类的独立测试（已有 `test_tools.py` 覆盖）
- 对 `simulator_service.py` 中 `main()` CLI 入口函数的独立测试（仅通过 E2E 覆盖）
- 性能基准测试（benchmark）
- 安全渗透测试
- 代码覆盖率报告（coverage.py 集成）

---

## 待确认推断项

以下条目标注了 `[INFERRED]`，需 PM 确认后转为确定性需求：

1. **REQ-FUNC-017（`SimulatorSSHServer` 公开 API 的 paramiko 依赖）**：建议 SSH 服务器公开 API 测试使用 mock paramiko Transport 或仅保留为 CLI 解析器单元测试覆盖。PM 需确认是否需要实际 SSR 连接测试。
2. **REQ-NFUNC-003（slow 标记范围）**：建议将 `test_simulator_lifecycle_manager.py` 中的进程启动等待测试标记为 `@pytest.mark.slow`。PM 需确认标记范围。

---

## 开放问题

1. 模拟器进程启动的超时时间在某些 CI 环境下可能不足（默认 10 秒）。是否需要可配置的超时时间？
2. `run_simulator_tests.sh` 应为 Bash 脚本（Linux target）还是跨平台的 Python 脚本？当前 PM 指定 `.sh`，推测目标为 Linux 环境。
3. `SimulatorBackupTool` 的 rollback 测试需要先执行配置变更，是否允许 E2E 测试中对真实模拟器进程做状态变更（可能影响后续测试的隔离性）？
