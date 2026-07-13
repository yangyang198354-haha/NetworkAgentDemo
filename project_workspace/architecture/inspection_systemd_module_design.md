<file_header>
  <author_agent>sub_agent_system_architect</author_agent>
  <timestamp>2026-07-12T00:00:00Z</timestamp>
  <project_name>NetworkAgentDemo</project_name>
  <version>0.2.0</version>
  <input_files>
    <file>requirements/inspection_systemd_requirements.md</file>
    <file>requirements/inspection_systemd_user_stories.md</file>
    <file>architecture/inspection_systemd_architecture_design.md</file>
    <file>architecture/module_design.md (v0.1.0 参考)</file>
    <file>src/trigger/inspection_scheduler.py (v0.1.0 重构源)</file>
    <file>src/api/inspection_router.py (v0.1.0 增强源)</file>
    <file>src/database/inspection_models.py (v0.1.0 增强源)</file>
    <file>src/database/repositories/inspection_repository.py (v0.1.0 增强源)</file>
  </input_files>
  <phase>PHASE_INSP_03</phase>
  <status>APPROVED</status>
</file_header>

# 巡检机制 systemd 重构 — 模块设计文档

---

## 模块总览

### v0.2.0 新增模块

| MOD-ID | 模块名 | 层级 | 职责 | 依赖于 |
|--------|--------|------|------|--------|
| MOD-INSP-001 | systemd_unit_manager | 安全与基础设施层 | 使用 Jinja2 模板生成 systemd unit 文件，写入 /etc/systemd/system/，执行 daemon-reload | MOD-INSP-002, MOD-016 |
| MOD-INSP-002 | systemctl_executor | 安全与基础设施层 | 封装 sudo systemctl 命令调用，提供类型化的 status/start/stop/restart/enable/disable 操作 | — (subprocess) |
| MOD-INSP-003 | inspection_cli | 触发层 | CLI 巡检入口（python3.11 -m src.inspection_cli run），加载设备列表和配置，执行全量巡检，持久化结果 | MOD-WEB-004, MOD-WEB-003, MOD-016, MOD-011 |

### v0.2.0 变更模块

| MOD-ID | 模块名 | 变更类型 | 变更说明 |
|--------|--------|---------|---------|
| MOD-WEB-001 | inspection_router | **增强** | 新增 6 个端点（status/start/stop/restart/enable/disable）；增强 config/trigger/history 端点 |
| MOD-WEB-004 | inspection_repository | **增强** | 扩大配置项（新增 retry_backoff）；新增 unit 文件生成触发方法 |
| MOD-WEB-003 | inspection_models | **增强** | InspectionRecord 新增 status 字段（SUCCESS/PARTIAL/FAILED） |
| MOD-INSP-006 | Web UI 前端组件 | **增强** | InspectionConfigView.vue 新增状态面板 + 控制按钮；inspection.ts Pinia store 扩展 |

### v0.2.0 废弃模块

| MOD-ID | 模块名 | 废弃说明 |
|--------|--------|---------|
| MOD-002 | InspectionScheduler（APScheduler 部分） | start_scheduler()/stop_scheduler() 废弃；run_inspection_once() 逻辑迁移至 MOD-INSP-003 |

---

## 系统分层架构图（v0.2.0 巡检部分）

```
┌──────────────────────────────────────────────────────────────────────┐
│                      触发层 (Trigger Layer)                           │
│                                                                      │
│  ┌─────────────────────────┐    ┌──────────────────────────────┐    │
│  │   MOD-001 (保留)          │    │   MOD-INSP-003 (新增)          │    │
│  │   WebhookReceiver        │    │   inspection_cli               │    │
│  │   POST /webhook/alert    │    │   ───────────────────────────  │    │
│  │                          │    │   python -m src.inspection_cli │    │
│  │                          │    │   run                          │    │
│  │                          │    │   → InspectionRecord (SQLite)  │    │
│  └──────────────────────────┘    └──────────────┬───────────────┘    │
│                                                  │                    │
│                                           systemd timer 触发          │
│                                           systemctl start (手动)      │
│                                                  │                    │
└──────────────────────────────────────────────────┼────────────────────┘
                                                   │
┌──────────────────────────────────────────────────┼────────────────────┐
│                 编排层 (Orchestration Layer)       │                    │
│  MOD-003~005 (LangGraph + AlertNormalizer + NodeHandlers)            │
│  [v0.2.0 本层不变 — 巡检告警通过 AlertNormalizer 进入已有工作流]        │
└──────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────┐
│                     Web API 层 (FastAPI on :8000)                     │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │   MOD-WEB-001: inspection_router (增强)                       │   │
│  │   ───────────────────────────────────────                     │   │
│  │   [NEW]  GET    /api/inspection/status   → 状态查询            │   │
│  │   [NEW]  POST   /api/inspection/start    → 启动 service        │   │
│  │   [NEW]  POST   /api/inspection/stop     → 停止 service        │   │
│  │   [NEW]  POST   /api/inspection/restart  → 重启 service        │   │
│  │   [NEW]  POST   /api/inspection/enable   → 启用 timer          │   │
│  │   [NEW]  POST   /api/inspection/disable  → 禁用 timer          │   │
│  │   [ENH]  GET    /api/inspection/config   → 返回 +retry_backoff │   │
│  │   [ENH]  PUT    /api/inspection/config   → 保存 + unit 文件同步 │   │
│  │   [ENH]  POST   /api/inspection/trigger  → systemctl start     │   │
│  │   [ENH]  GET    /api/inspection/history  → +status 筛选        │   │
│  └───────────────────────────┬──────────────────────────────────┘   │
│                              │                                       │
└──────────────────────────────┼───────────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│               安全与基础设施层 (Security & Infra Layer)                │
│                                                                      │
│  ┌────────────────────────────┐  ┌──────────────────────────────┐   │
│  │ MOD-INSP-001 (新增)         │  │ MOD-INSP-002 (新增)           │   │
│  │ systemd_unit_manager       │  │ systemctl_executor            │   │
│  │ ──────────────────────     │  │ ────────────────────────      │   │
│  │ generate_service_unit()    │  │ get_timer_status()            │   │
│  │ generate_timer_unit()      │  │ get_service_status()          │   │
│  │ write_unit_files()         │  │ start_service()               │   │
│  │ daemon_reload()            │  │ stop_service()                │   │
│  │ verify_units()             │  │ restart_service()             │   │
│  │                            │  │ enable_timer()                │   │
│  │ depends: MOD-INSP-002,     │  │ disable_timer()               │   │
│  │          MOD-016           │  │ daemon_reload()               │   │
│  │                            │  │ check_systemd_available()     │   │
│  │                            │  │ depends: (subprocess only)    │   │
│  └────────────────────────────┘  └──────────────────────────────┘   │
│                                                                      │
│  ┌────────────────────────────┐  ┌──────────────────────────────┐   │
│  │ MOD-016 (增强)              │  │ MOD-015 (保留)                 │   │
│  │ ConfigManager              │  │ AuditLogger                   │   │
│  │ + NETWORKAGENT_HOME 读取   │  │ (systemd 操作审计委托 journald) │   │
│  │ + systemd 默认配置项       │  │                              │   │
│  └────────────────────────────┘  └──────────────────────────────┘   │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────┐
│                      数据层 (Data Layer)                              │
│                                                                      │
│  ┌────────────────────────────┐  ┌──────────────────────────────┐   │
│  │ MOD-WEB-003 (增强)          │  │ MOD-WEB-004 (增强)             │   │
│  │ inspection_models          │  │ inspection_repository          │   │
│  │ + status 字段              │  │ + retry_backoff 配置项         │   │
│  │ (SUCCESS/PARTIAL/FAILED)   │  │ + trigger_unit_file_sync()     │   │
│  └────────────────────────────┘  └──────────────────────────────┘   │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 模块详情

---

### MOD-INSP-001: systemd_unit_manager

- **ID**: MOD-INSP-001
- **层级**: 安全与基础设施层
- **职责**: 使用 Jinja2 模板引擎生成 systemd service 和 timer unit 文件内容，写入 `/etc/systemd/system/` 目录，验证语法，执行 daemon-reload，并根据 timer 状态决定是否 restart。封装 systemd unit 文件的完整生命周期管理——生成、写入、验证、重载。

- **覆盖需求**: REQ-INSP-002, REQ-INSP-003, REQ-INSP-013, REQ-INSP-015, REQ-INSP-016, REQ-INSP-NF-001, REQ-INSP-NF-002
- **关联用户故事**: US-INSP-002, US-INSP-008

- **Pydantic 数据模型**:

  ```python
  # 本模块无对外 Pydantic 模型
  # 内部使用的模板变量数据结构：
  class UnitTemplateVars:
      """systemd unit 文件模板渲染变量"""
      working_directory: str          # NETWORKAGENT_HOME 环境变量值
      user: str                       # networkagent
      python_bin: str                 # python3.11
      timeout_stop_sec: int           # 从 SQLite timeout_seconds 读取
      on_unit_active_sec: int         # 从 SQLite interval_minutes 转换（分钟→秒）
      restart_sec: int                # 固定 30s
      accuracy_sec: int               # 固定 1s
      description: str                # 固定值
  ```

- **公开接口契约**:

  - **IFC-INSP-001-01**: `generate_service_unit(config: dict) → str`
    - 输入: 巡检配置字典（含 timeout_seconds、working_directory、user 等键）
    - 返回: 完整的 networkagent-inspection.service unit 文件内容（str）
    - 实现: 从 `resources/templates/systemd/networkagent-inspection.service.j2` 加载 Jinja2 模板，用输入配置渲染
    - 错误: `ValueError`（必需配置缺失）, `TemplateError`（渲染失败）

  - **IFC-INSP-001-02**: `generate_timer_unit(config: dict) → str`
    - 输入: 巡检配置字典（含 interval_minutes 等键）
    - 返回: 完整的 networkagent-inspection.timer unit 文件内容（str）
    - 实现: 从 `resources/templates/systemd/networkagent-inspection.timer.j2` 加载 Jinja2 模板渲染
    - 错误: `ValueError`, `TemplateError`

  - **IFC-INSP-001-03**: `write_unit_files(service_content: str, timer_content: str) → WriteResult`
    - 输入: 两个 unit 文件的完整文本内容
    - 返回: `WriteResult { success: bool, files_written: list[str], error: str | None }`
    - 实现: 将内容写入 `/etc/systemd/system/networkagent-inspection.service` 和 `.timer`；写入前检查目录权限；覆写已有文件
    - 错误: `PermissionError`（目录无写权限 → 转换为友好错误消息）

  - **IFC-INSP-001-04**: `verify_unit_files() → VerifyResult`
    - 输入: 无（验证已写入的 unit 文件）
    - 返回: `VerifyResult { success: bool, errors: list[str] }`
    - 实现: 通过 MOD-INSP-002 执行 `systemd-analyze verify /etc/systemd/system/networkagent-inspection.service` 和 `.timer`
    - 错误: 验证失败返回 errors 列表

  - **IFC-INSP-001-05**: `sync_config_to_systemd(config: dict) → SyncResult`
    - 输入: 巡检配置字典
    - 返回: `SyncResult { success: bool, actions_performed: list[str], error: str | None, timer_was_active: bool }`
    - 实现: 编排完整的同步链路——① 渲染 service + timer 模板 → ② 写入 unit 文件 → ③ 执行 daemon-reload → ④ 若 timer 当前 active 则 restart timer → ⑤ 返回同步摘要
    - 错误: 各步骤的错误分别捕获并汇总在 SyncResult 中；SQLite 数据不受影响（不回滚）

  - **IFC-INSP-001-06**: `is_config_changed(new_config: dict) → bool`
    - 输入: 新配置字典
    - 返回: True 表示配置与当前 unit 文件不一致，需要同步
    - 实现: 读取当前 unit 文件内容，提取关键参数（OnUnitActiveSec、TimeoutStopSec），与新配置对比
    - 用途: 实现 US-INSP-002 AC-INSP-002-05 的幂等检查

- **依赖模块**:
  - MOD-INSP-002 (systemctl_executor) — 执行 daemon-reload、restart timer、systemd-analyze verify
  - MOD-016 (ConfigManager) — 读取 NETWORKAGENT_HOME 环境变量

- **外部依赖**: Jinja2, Python pathlib/os

- **模板文件路径**:
  - `resources/templates/systemd/networkagent-inspection.service.j2` — service unit 模板
  - `resources/templates/systemd/networkagent-inspection.timer.j2` — timer unit 模板

- **关键流程**:
  1. **配置保存 → systemd 同步链路**（由 MOD-WEB-001 调用）：
     ```
     PUT /api/inspection/config
       → MOD-WEB-004 update_config() → SQLite 写入成功
       → MOD-INSP-001 sync_config_to_systemd(config)
         → generate_service_unit(config)
         → generate_timer_unit(config)
         → write_unit_files(service, timer)
         → MOD-INSP-002 daemon_reload()
         → MOD-INSP-002 get_timer_status() 检查 timer 是否 active
         → 若 active: MOD-INSP-002 restart_timer()
         → 返回 SyncResult
     ```
  2. **幂等检查流程**：
     ```
     is_config_changed(new_config)
       → 读取现有 unit 文件
       → 正则提取 OnUnitActiveSec= 值
       → 对比 new_config.interval_minutes * 60
       → 同样对比 TimeoutStopSec
       → 返回是否一致
     ```

- **与 v0.1.0 兼容性**:
  - 复用 v0.1.0 的 MOD-007 (TemplateEngine) 用到的 Jinja2 库，保持相同的 Jinja2 版本
  - 模板文件存放在独立的 `resources/templates/systemd/` 目录，不影响现有 `resources/templates/` 中的 CLI 命令模板

---

### MOD-INSP-002: systemctl_executor

- **ID**: MOD-INSP-002
- **层级**: 安全与基础设施层（最底层 — 仅依赖 Python subprocess 标准库）
- **职责**: 封装所有 `sudo systemctl` 命令调用，提供类型化的操作接口。统一处理：sudo 前缀、命令超时、退出码检查、stderr 捕获、systemd 不可用检测。确保所有 systemctl 调用使用 `subprocess.run(shell=False, list args)` 防命令注入。

- **覆盖需求**: REQ-INSP-004, REQ-INSP-006, REQ-INSP-007, REQ-INSP-NF-003, REQ-INSP-NF-006
- **关联用户故事**: US-INSP-003, US-INSP-004, US-INSP-005

- **Pydantic 数据模型**:

  ```python
  class TimerStatus(BaseModel):
      """networkagent-inspection.timer 状态快照"""
      active_state: str           # "active" | "inactive" | "not-found"
      unit_file_state: str        # "enabled" | "disabled" | "not-found"
      next_trigger: datetime | None  # UTC datetime 或 None（无计划）
      last_trigger: datetime | None


  class ServiceStatus(BaseModel):
      """networkagent-inspection.service 状态快照"""
      active_state: str           # "active" | "inactive" | "not-found"
      sub_state: str              # "running" | "dead" | "exited" | "failed"
      last_result: str            # "success" | "failure" | "not-found"
      last_execution: datetime | None


  class SystemctlResult(BaseModel):
      """systemctl 命令执行结果"""
      success: bool
      action: str                 # "start" | "stop" | "restart" | "enable" | "disable" | "daemon-reload" | "show"
      message: str
      detail: str | None = None   # stderr 内容（失败时）


  class SystemdAvailability(BaseModel):
      """systemd 环境检测结果"""
      available: bool
      reason: str | None = None   # 不可用原因
  ```

- **公开接口契约**:

  - **IFC-INSP-002-01**: `check_systemd_available() → SystemdAvailability`
    - 输入: 无
    - 返回: `SystemdAvailability { available: bool, reason: str | None }`
    - 实现: 检查 `/run/systemd/system` 路径是否存在；执行 `which systemctl` 验证命令可用
    - 用途: REQ-INSP-NF-006 环境检测（虽然 PM Q-INSP-003 否决了进程内降级，但环境检测仍用于 Web UI 显示提示）

  - **IFC-INSP-002-02**: `get_timer_status() → TimerStatus`
    - 输入: 无
    - 返回: `TimerStatus` Pydantic 模型
    - 实现: 执行 `sudo systemctl show networkagent-inspection.timer --property=ActiveState,UnitFileState,NextElapseUSRealtime,LastTriggerUSec`；解析 Key=Value 输出；NextElapseUSRealtime 为 0 时映射为 None
    - 错误: 超时（5 秒）→ `SystemctlTimeoutError`; unit 不存在 → active_state="not-found"

  - **IFC-INSP-002-03**: `get_service_status() → ServiceStatus`
    - 输入: 无
    - 返回: `ServiceStatus` Pydantic 模型
    - 实现: 执行 `sudo systemctl show networkagent-inspection.service --property=ActiveState,SubState,Result,ExecMainExitTimestamp`；解析输出
    - 错误: 同上

  - **IFC-INSP-002-04**: `start_service() → SystemctlResult`
    - 输入: 无
    - 返回: `SystemctlResult { action="start", ... }`
    - 实现: 执行 `sudo systemctl start networkagent-inspection.service`
    - 错误: 权限不足 → `SystemctlPermissionError`；服务已在运行 → 仍返回 success（systemctl start 对已运行服务是幂等的）

  - **IFC-INSP-002-05**: `stop_service() → SystemctlResult`
    - 输入: 无
    - 返回: `SystemctlResult { action="stop", ... }`
    - 实现: 执行 `sudo systemctl stop networkagent-inspection.service`
    - 注意: 此操作仅停止 service 进程，不影响 timer（timer 保持定时触发）——满足 REQ-INSP-006 要求

  - **IFC-INSP-002-06**: `restart_service() → SystemctlResult`
    - 输入: 无
    - 返回: `SystemctlResult { action="restart", ... }`
    - 实现: 执行 `sudo systemctl restart networkagent-inspection.service`

  - **IFC-INSP-002-07**: `enable_timer() → SystemctlResult`
    - 输入: 无
    - 返回: `SystemctlResult { action="enable", ... }`
    - 实现: 执行 `sudo systemctl enable networkagent-inspection.timer && sudo systemctl start networkagent-inspection.timer`
    - 幂等: 若 timer 已 enabled+active，返回提示"已处于启用状态"

  - **IFC-INSP-002-08**: `disable_timer() → SystemctlResult`
    - 输入: 无
    - 返回: `SystemctlResult { action="disable", ... }`
    - 实现: 执行 `sudo systemctl stop networkagent-inspection.timer && sudo systemctl disable networkagent-inspection.timer`
    - 幂等: 若 timer 已 disabled，返回提示"已处于禁用状态"

  - **IFC-INSP-002-09**: `daemon_reload() → SystemctlResult`
    - 输入: 无
    - 返回: `SystemctlResult { action="daemon-reload", ... }`
    - 实现: 执行 `sudo systemctl daemon-reload`

- **内部实现约束**:
  - 所有 systemctl 命令使用 `subprocess.run(['sudo', 'systemctl', ...], capture_output=True, text=True, timeout=5, shell=False)`
  - 命令参数以 `list` 形式传递，绝不使用字符串拼接
  - 默认超时 5 秒，可通过构造参数覆盖
  - 退出码检查: returncode != 0 时解析 stderr 判断错误类型（权限不足 / unit 不存在 / 其他）
  - 日志: 每次命令执行记录 INFO 级别日志（命令 + 退出码 + 耗时）

- **异常类型定义**:
  - `SystemctlPermissionError`: sudo 权限不足（stderr 含 "Interactive authentication required" 或 "not allowed"）
  - `SystemctlTimeoutError`: 命令执行超时
  - `SystemdNotAvailableError`: systemd 不可用
  - `SystemctlCommandError`: 其他 systemctl 执行错误

- **依赖模块**: 无（仅依赖 Python `subprocess` + `shutil` 标准库）

- **外部依赖**: Python subprocess, shutil (which), os.path

- **权限依赖**:
  - 需要 `/etc/sudoers.d/networkagent` 中配置：
    ```
    networkagent ALL=(root) NOPASSWD: /usr/bin/systemctl * networkagent-inspection.*
    networkagent ALL=(root) NOPASSWD: /usr/bin/systemd-analyze verify /etc/systemd/system/networkagent-inspection.*
    ```

---

### MOD-INSP-003: inspection_cli

- **ID**: MOD-INSP-003
- **层级**: 触发层（独立进程，不依赖 Web 进程）
- **职责**: CLI 巡检执行入口，以独立 Python 进程运行（`python3.11 -m src.inspection_cli run`）。从 SQLite 加载纳管设备列表和巡检配置，按 `run_inspection_once()` 逻辑执行全量设备巡检（接口状态 + CPU 检查），将结果持久化至 SQLite InspectionRecord 表。通过退出码反映执行结果。

- **覆盖需求**: REQ-INSP-010, REQ-INSP-014, REQ-INSP-017
- **关联用户故事**: US-INSP-008

- **Pydantic 数据模型**:

  ```python
  class CLIExitCode(enum.IntEnum):
      """CLI 退出码枚举"""
      SUCCESS = 0         # 全部设备正常
      PARTIAL = 1         # 部分设备异常
      FAILURE = 2         # 执行失败（系统错误）


  class InspectionSummary(BaseModel):
      """巡检执行摘要"""
      trigger_mode: str           # "SCHEDULED" | "MANUAL"
      started_at: datetime
      completed_at: datetime
      total_devices: int
      anomaly_count: int
      status: str                 # "SUCCESS" | "PARTIAL" | "FAILED"
      details: dict               # 每设备诊断结果
  ```

- **CLI 入口定义**:

  - **命令**: `python3.11 -m src.inspection_cli run`
  - **`__main__.py`** 或 **模块级入口**: 在 `src/inspection_cli.py` 中定义 `if __name__ == "__main__"` 或使用 `__main__.py` 支持 `-m` 调用
  - **参数**: 当前版本无额外参数；未来可通过 argparse 扩展（如 `--device-filter`、`--verbose`）

- **公开接口契约**:

  - **IFC-INSP-003-01**: `run() → CLIExitCode`
    - 输入: 无（从 SQLite 和 ConfigManager 读取）
    - 返回: `CLIExitCode` 枚举值（进程以此值调用 `sys.exit()`）
    - 实现流程:
      1. 初始化 SQLAlchemy Session（连接 SQLite）
      2. 从 MOD-WEB-004 读取设备列表（Device 表）
      3. 从 MOD-WEB-004 读取巡检配置（SystemConfig 表）
      4. 遍历每台设备，调用 MOD-011 (SwitchDiagTool) 执行诊断
      5. 对诊断结果分析异常（接口 down、CPU 超阈值）
      6. 构造 InspectionSummary
      7. 通过 MOD-WEB-004 持久化 InspectionRecord
      8. stdout 打印巡检摘要日志
      9. 以对应退出码调用 `sys.exit()`
    - 错误处理:
      - SQLite 不可访问 → exit(2), stderr 输出错误原因
      - 设备列表为空 → exit(0), stdout 输出"No devices configured"
      - 诊断工具异常 → 记录该设备为 FAILED，继续处理其他设备，最终 exit(1)
    - 超时控制: 单设备诊断默认超时 30 秒（从配置读取 timeout_seconds）

  - **IFC-INSP-003-02**: `load_inspection_config() → dict`
    - 输入: 无
    - 返回: 巡检配置字典（interval_minutes, timeout_seconds, retry_max, retry_backoff）
    - 实现: 从 SQLite SystemConfig 表读取，无值时降级到 ConfigManager 的 config.yaml 默认值
    - 优先级: SQLite > config.yaml > DEFAULT_CONFIG 硬编码值

  - **IFC-INSP-003-03**: `load_device_list() → list[DeviceInfo]`
    - 输入: 无
    - 返回: 纳管设备列表（DeviceInfo Pydantic 模型）
    - 实现: 从 SQLite Device 表查询所有启用设备
    - 返回空列表时不报错（调用方处理）

- **依赖模块**:
  - MOD-WEB-004 (inspection_repository) — 读取配置、设备列表；写入 InspectionRecord
  - MOD-WEB-003 (inspection_models) — InspectionRecord 数据模型
  - MOD-016 (ConfigManager) — 读取配置降级链默认值
  - MOD-011 (SwitchDiagTool) — 执行设备诊断命令

- **外部依赖**: Python sys, argparse (未来), loguru (日志)

- **与 v0.1.0 MOD-002 的关系**:
  - **迁移自**: `inspection_scheduler.py` 中的 `run_inspection_once()` 方法
  - **核心逻辑保留**: 设备遍历、诊断命令选择（MAC_FLAPPING/PORT_DOWN/CPU_HIGH）、异常检测逻辑
  - **移除的逻辑**: APScheduler 调度（start_scheduler/stop_scheduler）、Web 进程内线程管理
  - **新增的逻辑**: CLI 退出码映射、独立 SQLAlchemy Session 管理、stdout/stderr 日志输出

- **日志输出规范**:
  - stdout: 巡检摘要信息（JSON 格式或结构化文本）
  - stderr: 错误和警告
  - journald: systemd.service 配置了 `StandardOutput=journal` + `StandardError=journal`，所有输出自动进入 journald

---

### MOD-WEB-001: inspection_router（增强）

- **ID**: MOD-WEB-001
- **层级**: Web API 层
- **变更类型**: 增强（保留 v0.1.0 的 4 个端点，新增 6 个，增强 4 个）
- **职责**: 提供巡检管理相关的全部 REST API 端点，包括配置管理、状态查询（新增）、生命周期控制（新增）、手动触发（增强）、历史查询（增强）。

- **覆盖需求**: REQ-INSP-001, REQ-INSP-004, REQ-INSP-006, REQ-INSP-007, REQ-INSP-009, REQ-INSP-011
- **关联用户故事**: US-INSP-001, US-INSP-003, US-INSP-004, US-INSP-005, US-INSP-006, US-INSP-007

- **Pydantic 数据模型（新增/变更）**:

  ```python
  # 新增：配置更新请求体（增强）
  class InspectionConfigUpdate(BaseModel):
      inspection_interval_minutes: Optional[int] = Field(None, ge=1, le=1440)
      diagnosis_timeout_seconds: Optional[int] = Field(None, ge=1, le=600)
      diagnosis_retry_max: Optional[int] = Field(None, ge=0, le=10)
      retry_backoff_seconds: Optional[int] = Field(None, ge=1, le=300)   # [NEW] 替换 polling_interval_seconds


  # 新增：状态查询响应
  class InspectionStatusResponse(BaseModel):
      timer: TimerStatus | None
      service: ServiceStatus | None
      last_inspection: dict | None
      systemd_available: bool
      message: str | None


  # 新增：控制操作响应
  class InspectionActionResponse(BaseModel):
      result: str          # "success" | "failed" | "rejected"
      action: str          # "start" | "stop" | "restart" | "enable" | "disable"
      message: str
      detail: str | None
      service_state: dict | None
  ```

- **新增 API 端点**:

  | 端点 | HTTP 方法 | 路径 | 对应 IFC | 说明 |
  |------|----------|------|---------|------|
  | API-INSP-01 | GET | `/api/inspection/status` | IFC-WEB-001-05 | 查询 systemd timer + service 实时状态 |
  | API-INSP-02 | POST | `/api/inspection/start` | IFC-WEB-001-06 | systemctl start service |
  | API-INSP-03 | POST | `/api/inspection/stop` | IFC-WEB-001-07 | systemctl stop service |
  | API-INSP-04 | POST | `/api/inspection/restart` | IFC-WEB-001-08 | systemctl restart service |
  | API-INSP-05 | POST | `/api/inspection/enable` | IFC-WEB-001-09 | systemctl enable + start timer |
  | API-INSP-06 | POST | `/api/inspection/disable` | IFC-WEB-001-10 | systemctl stop + disable timer |

- **增强现有 API 端点**:

  | 端点 | 变更说明 |
  |------|---------|
  | GET /api/inspection/config | 返回字段增加 `retry_backoff_seconds`（替换 `polling_interval_seconds`）；增加 `systemd_sync_status` 字段 |
  | PUT /api/inspection/config | 入参增加 `retry_backoff_seconds`；新增字段校验（正整数 1-300）；保存成功后自动调用 MOD-INSP-001.sync_config_to_systemd() |
  | POST /api/inspection/trigger | 改为通过 MOD-INSP-002.start_service() 触发（systemctl start）；增加 systemd 可用性检查；systemd 不可用时返回 503 错误"请先配置巡检服务" |
  | GET /api/inspection/history | 查询参数增加 `status: Optional[str]` 筛选（SUCCESS/PARTIAL/FAILED）；返回字段增加 `status` |

- **新增接口契约详情**:

  - **IFC-WEB-001-05**: `GET /api/inspection/status`
    - 处理逻辑:
      1. 调用 MOD-INSP-002.check_systemd_available()
      2. 若 systemd 可用: 调用 get_timer_status() + get_service_status() + 查询最近一次 InspectionRecord
      3. 若 systemd 不可用: 返回 systemd_available=false + message（不执行 systemctl 命令）
      4. 组装 InspectionStatusResponse 返回
    - 响应 200: 见 REQ-INSP-004 API 契约
    - 超时保护: MOD-INSP-002 内部设置 systemctl show 超时 5 秒

  - **IFC-WEB-001-06**: `POST /api/inspection/start`
    - 处理逻辑: ① systemd 可用性检查 → ② 调用 MOD-INSP-002.start_service() → ③ 返回 InspectionActionResponse
    - 错误: 503（systemd 不可用）、500（systemctl 执行失败）

  - **IFC-WEB-001-07**: `POST /api/inspection/stop`
    - 处理逻辑: 同 start，调用 MOD-INSP-002.stop_service()
    - 注意: stop 仅停止 service 进程，不停止 timer（符合 REQ-INSP-006 要求）

  - **IFC-WEB-001-08**: `POST /api/inspection/restart`
    - 处理逻辑: 同 start，调用 MOD-INSP-002.restart_service()

  - **IFC-WEB-001-09**: `POST /api/inspection/enable`
    - 处理逻辑: ① systemd 可用性检查 → ② 调用 MOD-INSP-002.enable_timer() → ③ 返回结果含 timer 新状态
    - 幂等: 若 timer 已 enabled+active，返回 message="timer 已处于启用状态"

  - **IFC-WEB-001-10**: `POST /api/inspection/disable`
    - 处理逻辑: ① systemd 可用性检查 → ② 调用 MOD-INSP-002.disable_timer() → ③ 返回结果
    - 幂等: 若 timer 已 disabled，返回 message="timer 已处于禁用状态"

- **增强端点变更详情**:

  - **PUT /api/inspection/config（增强）**:
    - 变更: 配置保存成功后的同步链路
    - 新增步骤:
      5. 调用 MOD-INSP-001.sync_config_to_systemd(config)
      6. 若 systemd 同步成功: 返回 `{"message": "配置已保存并同步到 systemd", "config": ..., "systemd_sync": "success"}`
      7. 若 systemd 同步失败: 返回 `{"message": "配置已保存但 systemd 同步失败", "config": ..., "systemd_sync": "failed", "systemd_error": "..."}`, HTTP 200（非 500，因为 SQLite 写入成功）
    - 参数校验增强: retry_backoff_seconds 范围 1-300，正整数

  - **POST /api/inspection/trigger（增强）**:
    - 变更: v0.1.0 在 Web 进程 daemon 线程中执行 → v0.2.0 通过 systemctl start service 触发
    - 新逻辑:
      1. 调用 MOD-INSP-002.check_systemd_available()
      2. 若不可用: 返回 503 `{"error": "systemd_not_available", "message": "请先配置巡检服务"}`（PM Q-INSP-003 决策）
      3. 若可用: 调用 MOD-INSP-002.get_service_status() 检查是否已在运行
      4. 若已在运行 (active_state=running): 返回 409 `{"result": "rejected", "message": "巡检正在执行中，请等待完成后再触发"}`
      5. 否则: 调用 MOD-INSP-002.start_service() → 返回 `{"result": "success", "message": "巡检已触发", "trigger_mode": "MANUAL"}`

  - **GET /api/inspection/history（增强）**:
    - 新增查询参数: `status: Optional[str]`（SUCCESS/PARTIAL/FAILED）
    - Repository 层增加按 status 筛选逻辑
    - 返回字段: items 中每条记录增加 `status` 字段和 `duration_seconds`（completed_at - started_at）

- **依赖模块**:
  - MOD-INSP-001 (systemd_unit_manager) — 配置同步链路
  - MOD-INSP-002 (systemctl_executor) — 所有 systemctl 操作
  - MOD-WEB-004 (inspection_repository) — 配置和历史数据读写
  - MOD-016 (ConfigManager) — 配置降级链

- **与 v0.1.0 兼容性**:
  - 保留 v0.1.0 的所有 4 个端点路径和方法（GET/PUT config, POST trigger, GET history），已有前端调用无需改动 URL
  - 新增端点为 v0.2.0 独有，不影响 v0.1.0 前端功能
  - trigger 端点的响应格式兼容 v0.1.0（`{"message": "..."}` 键保留）

---

### MOD-WEB-004: inspection_repository（增强）

- **ID**: MOD-WEB-004
- **层级**: 数据层
- **变更类型**: 增强（保留 v0.1.0 全部方法，新增配置项和同步触发方法）
- **职责**: 巡检配置和历史的 SQLite 数据访问层。v0.2.0 增强：扩大配置项范围（新增 retry_backoff），新增 unit 文件生成触发方法 `trigger_unit_file_sync()`。

- **覆盖需求**: REQ-INSP-001, REQ-INSP-002, REQ-INSP-010, REQ-INSP-011, REQ-INSP-012, REQ-INSP-013
- **关联用户故事**: US-INSP-001, US-INSP-002, US-INSP-007

- **配置项变更**:

  | 配置键 | v0.1.0 | v0.2.0 | 变更说明 |
  |--------|--------|--------|---------|
  | `inspection.interval_minutes` | 保留 | 保留 | 不变 |
  | `diagnosis.timeout_seconds` | 保留 | 保留 | 不变 |
  | `diagnosis.retry_max` | 保留 | 保留 | 不变 |
  | `ui.polling_interval_seconds` | 存在 | **移除** | 替换为 retry_backoff |
  | `diagnosis.retry_backoff` | 不存在 | **新增** | 重试间隔（秒），默认 5，范围 1-300 |

- **新增/增强方法**:

  - **IFC-WEB-004-01 (增强)**: `get_config() → dict`
    - 变更: 配置键列表增加 `diagnosis.retry_backoff`；移除 `ui.polling_interval_seconds`
    - 返回: `{"inspection.interval_minutes": "10", "diagnosis.timeout_seconds": "30", "diagnosis.retry_max": "3", "diagnosis.retry_backoff": "5"}`

  - **IFC-WEB-004-02 (增强)**: `update_config(config_values: dict) → dict`
    - 变更: 接收的 config_values 可包含 `diagnosis.retry_backoff`
    - 不变: upsert 逻辑不变（存在则更新，不存在则插入 SystemConfig 行）

  - **IFC-WEB-004-05 (新增)**: `get_devices_for_inspection() → list[dict]`
    - 输入: 无（查询 SQLite Device 表）
    - 返回: 纳管设备列表，每条含 device_name, device_ip, device_model
    - 用途: MOD-INSP-003 (inspection_cli) 加载设备列表
    - [ASSUMPTION] Device 表结构已在 v0.1.0 中定义，此方法仅提供查询封装

  - **IFC-WEB-004-06 (新增)**: `get_latest_inspection() → dict | None`
    - 输入: 无
    - 返回: 最近一次巡检记录摘要（record_id, trigger_mode, total_devices, anomaly_count, status, completed_at）
    - 用途: GET /api/inspection/status 的 last_inspection 字段
    - 实现: `SELECT * FROM inspection_records ORDER BY completed_at DESC LIMIT 1`

  - **IFC-WEB-004-07 (增强)**: `list_history(trigger_mode=None, status=None, page=1, page_size=20) → dict`
    - 变更: 新增 status 查询参数支持按状态筛选；返回 items 中增加 status 字段
    - 筛选逻辑: 若 status 非空，添加 `WHERE status = :status` 条件

- **依赖模块**: MOD-WEB-003 (inspection_models)

- **外部依赖**: SQLAlchemy

- **迁移说明**:
  - v0.1.0 已存储的 `ui.polling_interval_seconds` 键在 SystemConfig 表中保留（不删除），但 v0.2.0 代码不再读取
  - 新增 `diagnosis.retry_backoff` 键在首次保存时自动创建（upsert 逻辑）
  - InspectionRecord 表新增的 `status` 字段需要 ALTER TABLE 或通过 SQLAlchemy migrate 添加（v0.1.0 表中无此列）

---

### MOD-WEB-003: inspection_models（增强）

- **ID**: MOD-WEB-003
- **层级**: 数据层
- **变更类型**: 增强（InspectionRecord 表新增 status 字段）
- **职责**: InspectionRecord 数据模型定义

- **覆盖需求**: REQ-INSP-010
- **关联用户故事**: US-INSP-007, US-INSP-008

- **模型变更**:

  ```python
  # InspectionRecord 新增字段
  status: Mapped[str] = mapped_column(
      String(15), nullable=False, default="SUCCESS",
      comment="SUCCESS / PARTIAL / FAILED"
  )
  ```

- **status 枚举**:
  - `SUCCESS`: 全部设备检查正常（anomaly_count = 0）
  - `PARTIAL`: 部分设备异常（anomaly_count > 0 但巡检流程完成）
  - `FAILED`: 巡检执行失败（系统级错误，如 SQLite 不可读、所有设备不可达）

- **迁移注意事项**:
  - v0.1.0 的 InspectionRecord 表无 status 列，需要数据库迁移
  - 现有历史记录的 status 可根据 anomaly_count 推断：anomaly_count=0 → SUCCESS; >0 → PARTIAL
  - 推荐使用 SQLAlchemy Alembic 做自动迁移，或部署脚本中执行 `ALTER TABLE inspection_records ADD COLUMN status VARCHAR(15) DEFAULT 'SUCCESS'`

---

### MOD-INSP-006: Web UI 前端组件变更

- **ID**: MOD-INSP-006
- **层级**: 前端展示层
- **变更类型**: 增强（Vue 3 + Element Plus + Pinia）
- **职责**: 巡检管理页面的前端 UI 变更——InspectionConfigView.vue 新增状态面板和控制按钮，inspection.ts Pinia store 扩展 actions。

- **覆盖需求**: REQ-INSP-001, REQ-INSP-005, REQ-INSP-008
- **关联用户故事**: US-INSP-001, US-INSP-003, US-INSP-004, US-INSP-005, US-INSP-006

- **InspectionConfigView.vue 变更**:

  | 区域 | 变更类型 | 说明 |
  |------|---------|------|
  | 配置表单 | **增强** | polling_interval → retry_backoff 字段替换；新增表单校验（正整数范围） |
  | 状态面板 | **新增** | systemd timer + service 状态指示灯、状态文本、下次触发时间、最近巡检摘要 |
  | 控制按钮组 | **新增** | start/stop/restart/enable/disable 五个按钮，按当前状态动态启用/禁用 |
  | 手动触发按钮 | **保留** | 保留现有按钮，增强错误处理（409 冲突、503 不可用） |
  | 保存按钮 | **增强** | 保存后显示 systemd 同步结果提示（成功绿色 / 失败黄色 + 重新同步按钮） |

- **状态面板交互规格**:
  - 前端轮询: 每 5 秒调用 GET /api/inspection/status（使用 `setInterval` 或 `usePolling` composable）
  - 组件挂载时立即查询一次（`onMounted`）
  - 组件卸载时清除轮询定时器（`onUnmounted`）
  - systemd 不可用时: 状态面板显示灰色问号指示灯 + "当前环境不支持 systemd，定时巡检功能不可用"
  - timer 未部署时: 显示"巡检定时器未部署，请保存巡检配置"

- **控制按钮交互规格**:
  - 按钮启用/禁用逻辑（基于 status 返回值）:

    | 当前 timer 状态 | start | stop | restart | enable | disable |
    |----------------|-------|------|---------|--------|---------|
    | active + enabled | 禁用 | 可用 | 可用 | 禁用 | 可用 |
    | active + disabled | 禁用 | 可用 | 可用 | 可用 | 禁用 |
    | inactive + enabled | 可用 | 禁用 | 可用 | 禁用 | 可用 |
    | inactive + disabled | 可用 | 禁用 | 可用 | 可用 | 禁用 |
    | not-found | 禁用 | 禁用 | 禁用 | 禁用 | 禁用 |

  - 所有控制按钮点击后弹出二次确认对话框（Element Plus `ElMessageBox.confirm`）
  - 操作执行中按钮显示 Loading 状态
  - 操作完成后: Toast 提示结果（绿色 `ElMessage.success` / 红色 `ElMessage.error`），自动刷新状态面板

- **inspection.ts Pinia Store 扩展**:

  | Action | 类型 | 说明 |
  |--------|------|------|
  | `fetchConfig()` | 保留 | 获取巡检配置（返回增加 retry_backoff） |
  | `updateConfig(payload)` | **增强** | 保存配置（入参增加 retry_backoff_seconds） |
  | `fetchStatus()` | **新增** | 调用 GET /api/inspection/status |
  | `startService()` | **新增** | 调用 POST /api/inspection/start |
  | `stopService()` | **新增** | 调用 POST /api/inspection/stop |
  | `restartService()` | **新增** | 调用 POST /api/inspection/restart |
  | `enableTimer()` | **新增** | 调用 POST /api/inspection/enable |
  | `disableTimer()` | **新增** | 调用 POST /api/inspection/disable |
  | `triggerInspection()` | **增强** | 错误处理增强（409/503 响应） |
  | `fetchHistory(params)` | **增强** | 查询参数增加 status 筛选 |

- **状态管理（Pinia State 新增字段）**:

  ```typescript
  interface InspectionState {
    // ...v0.1.0 现有字段
    timerStatus: {
      activeState: string;
      unitFileState: string;
      nextTrigger: string | null;
    } | null;
    serviceStatus: {
      activeState: string;
      subState: string;
      lastResult: string;
    } | null;
    systemdAvailable: boolean;
    statusPollingTimer: ReturnType<typeof setInterval> | null;
  }
  ```

---

## 依赖关系图（v0.2.0 巡检模块 + 现有模块）

```
# Web API 层 → 基础设施层
MOD-WEB-001 (inspection_router) ──→ MOD-INSP-001 (systemd_unit_manager)  [IFC-INSP-001-05 sync_config_to_systemd]
MOD-WEB-001 (inspection_router) ──→ MOD-INSP-002 (systemctl_executor)    [IFC-INSP-002-02~08 状态查询+生命周期控制]
MOD-WEB-001 (inspection_router) ──→ MOD-WEB-004 (inspection_repository)  [现有 IFC-WEB-004-01/02/07]
MOD-WEB-001 (inspection_router) ──→ MOD-016 (ConfigManager)              [现有依赖]

# 基础设施层内部
MOD-INSP-001 (systemd_unit_manager) ──→ MOD-INSP-002 (systemctl_executor)  [IFC-INSP-002-09 daemon_reload]
MOD-INSP-001 (systemd_unit_manager) ──→ MOD-016 (ConfigManager)            [读取 NETWORKAGENT_HOME]

# CLI 层 → 数据层 + 工具层
MOD-INSP-003 (inspection_cli) ──→ MOD-WEB-004 (inspection_repository)     [IFC-WEB-004-01/05/06]
MOD-INSP-003 (inspection_cli) ──→ MOD-WEB-003 (inspection_models)         [InspectionRecord 模型]
MOD-INSP-003 (inspection_cli) ──→ MOD-016 (ConfigManager)                  [配置降级链]
MOD-INSP-003 (inspection_cli) ──→ MOD-011 (SwitchDiagTool)                 [现有 IFC-011-01]

# 数据层内部
MOD-WEB-004 (inspection_repository) ──→ MOD-WEB-003 (inspection_models)   [现有依赖]

# ─── 无循环依赖，已验证 ───
# MOD-WEB-001 → MOD-INSP-001 → MOD-INSP-002 → (终点, subprocess)
# MOD-WEB-001 → MOD-INSP-001 → MOD-016 → (终点)
# MOD-WEB-001 → MOD-INSP-002 → (终点)
# MOD-WEB-001 → MOD-WEB-004 → MOD-WEB-003 → (终点)
# MOD-INSP-003 → MOD-WEB-004 → MOD-WEB-003 → (终点)
# MOD-INSP-003 → MOD-016 → (终点)
# MOD-INSP-003 → MOD-011 → (终点)
# 所有路径收敛至终端节点（subprocess / SQLite / ConfigManager / SwitchDiagTool），无环。
```

---

## 与 v0.1.0 模块的兼容性说明

### 共用模块（不变）

以下 v0.1.0 模块在 v0.2.0 中保持不变，巡检模块正常依赖它们：

| MOD-ID | 模块名 | v0.2.0 巡检模块依赖关系 |
|--------|--------|------------------------|
| MOD-011 | SwitchDiagTool | MOD-INSP-003 调用 `diagnose()` 执行诊断 |
| MOD-016 | ConfigManager | MOD-INSP-001/003 读取 NETWORKAGENT_HOME 和配置降级链 |
| MOD-015 | AuditLogger | 不变——应用层审计日志仍由 MOD-015 负责；systemd 操作审计委托 journald |

### 数据表兼容性

| 表名 | v0.1.0 | v0.2.0 变更 | 兼容性 |
|------|--------|------------|--------|
| `inspection_records` | 6 列 | 新增 `status` 列 (VARCHAR 15) | v0.1.0 历史数据可读——status 默认值 SUCCESS |
| `system_config` | K-V 表 | 新增 `diagnosis.retry_backoff` 键 | v0.1.0 的 `ui.polling_interval_seconds` 保留不删 |
| `devices` | 不变 | 不变 | 完全兼容 |

### API 兼容性

| v0.1.0 API | v0.2.0 兼容性 |
|-----------|--------------|
| GET /api/inspection/config | 兼容——返回增加 retry_backoff 字段（前端忽略额外字段） |
| PUT /api/inspection/config | 兼容——可选字段新增，旧前端不传则使用默认值 |
| POST /api/inspection/trigger | **行为变更**——v0.1.0 进程内执行 → v0.2.0 systemctl start；响应格式保持兼容 |
| GET /api/inspection/history | 兼容——返回增加 status 字段（前端忽略额外字段） |
</file_header>