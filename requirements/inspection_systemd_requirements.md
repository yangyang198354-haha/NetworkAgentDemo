<file_header>
  <author_agent>sub_agent_requirement_analyst</author_agent>
  <timestamp>2026-07-10T00:00:00Z</timestamp>
  <project_name>NetworkAgentDemo</project_name>
  <version>0.2.0</version>
  <input_files>
    <file>PM agent_invocation (内嵌原始需求文本)</file>
  </input_files>
  <phase>PHASE_INSP_01</phase>
  <status>DRAFT</status>
</file_header>

# 巡检机制 systemd 重构 — 需求规格说明书

---

## 执行摘要

### 业务背景
NetworkAgentDemo v0.1.0 已实现基于 APScheduler（Python BackgroundScheduler）的巡检调度机制，但存在以下缺陷：重启服务即丢失定时器状态、无法持久化状态、无法通过 systemd 管理巡检生命周期、配置分散在 config.yaml 中导致 Web UI 无法动态修改。v0.2.0 目标是将巡检调度引擎从 APScheduler 迁移至 Linux systemd timer + service 架构，实现 OS 级别的状态持久化、生命周期管理和 Web UI 全配置管理能力。

> 来源：PM agent_invocation —「项目背景」段 +「当前巡检机制使用 APScheduler...存在以下问题」段

### 需求总览
| 类别 | 数量 |
|------|------|
| 功能需求（REQ-INSP-*） | 17 条 |
| 非功能需求（REQ-INSP-NF-*） | 7 条 |
| [INFERRED] 推断性需求 | 0 条（PM 明确要求所有需求须有明确来源或代码证据） |
| 用户故事（US-INSP-*） | 8 条（见 inspection_systemd_user_stories.md） |

### 版本迁移影响范围
| v0.1.0 组件 | v0.2.0 变更 |
|-------------|------------|
| `src/trigger/inspection_scheduler.py` (MOD-002) | **弃用** APScheduler BackgroundScheduler；保留 `run_inspection_once()` 核心巡检逻辑，迁移至 CLI 入口 `src/inspection_cli.py` |
| `src/api/inspection_router.py` (MOD-WEB-001) | **增强** — 新增 systemd 状态查询 + 生命周期控制端点；配置写入增强为同步到 systemd unit 文件 |
| `src/database/inspection_models.py` (MOD-WEB-003) | **保留** — InspectionRecord 表结构已满足 v0.2.0 需求 |
| `src/database/repositories/inspection_repository.py` (MOD-WEB-004) | **增强** — 新增 systemd unit 文件生成逻辑；扩大配置项范围（增加 retry_backoff 等） |
| `src/security/config_manager.py` (MOD-016) | **保留** — 继续作为运行时配置源；DEFAULT_CONFIG 中增加 systemd 相关默认值 |
| `webui/src/views/inspection/InspectionConfigView.vue` | **增强** — 新增 systemd 状态面板 + start/stop/restart/enable/disable 按钮 + retry_backoff 配置字段 |
| `webui/src/views/inspection/InspectionHistoryView.vue` | **保留** — 基本满足 v0.2.0 巡检历史需求，微调字段对齐 |
| `webui/src/stores/inspection.ts` | **增强** — 新增 fetchStatus()、startService()、stopService()、restartService()、enableTimer()、disableTimer() actions |
| `config/config.yaml` | **弱化** — 巡检配置改为 SQLite 优先；config.yaml 仅作为初始默认值来源 |
| APScheduler 依赖 | **移除** — 不再需要 apscheduler Python 包 |

> 来源：PM agent_invocation —「现有代码分析摘要」段 +「与 v0.2.0 的关键差异识别」表格

---

## 功能需求（Functional Requirements）

### 1. 巡检配置管理（Inspection Configuration Management）

#### REQ-INSP-001: Web UI 巡检参数配置
| 字段 | 内容 |
|------|------|
| **ID** | REQ-INSP-001 |
| **描述** | 系统应当在 Web UI 巡检配置页面提供完整的巡检参数配置表单，运维人员可配置巡检周期（interval_minutes，单位分钟）、诊断超时（timeout_seconds，单位秒）、重试次数（retry_max）、重试间隔（retry_backoff，单位秒）四项参数，所有参数提供输入校验（正整数、合理范围）。 |
| **来源引用** | PM 用户需求第1项 —「Web UI 巡检配置页面：可配置巡检周期（interval）、诊断超时（timeout）、重试次数（retry）、重试间隔（retry_backoff）等参数」 |
| **优先级** | Must Have |
| **依赖模块** | MOD-WEB-001 (inspection_router.py), MOD-WEB-004 (inspection_repository.py), MOD-016 (config_manager.py), InspectionConfigView.vue, inspection.ts Pinia store |
| **备注** | v0.1.0 的 InspectionConfigView.vue 已支持 interval_minutes、timeout_seconds、retry_max、polling_interval 四项参数；v0.2.0 需将 polling_interval 替换为 retry_backoff，并新增表单校验 |

**验收标准：**
- **AC-INSP-001-01** — 配置表单展示当前值
  - Given 系统 SQLite 中已存储巡检配置：interval_minutes=10, timeout_seconds=30, retry_max=3, retry_backoff=5
  - When 运维人员打开 Web UI "巡检配置"页面
  - Then 表单各字段应当预填当前存储值，所有字段可编辑
- **AC-INSP-001-02** — 配置保存成功
  - Given 运维人员将巡检间隔修改为 15 分钟，其余参数不变
  - When 点击"保存配置"按钮
  - Then 系统应当将新配置写入 SQLite SystemConfig 表，触发 systemd unit 文件重新生成（见 REQ-INSP-002），Web UI 显示"配置已保存"成功提示
- **AC-INSP-001-03** — 参数合法性校验
  - Given 运维人员在 interval_minutes 输入框中输入 0 或负数
  - When 点击"保存配置"
  - Then 前端应当阻止提交并提示"巡检间隔必须为正整数（分钟）"，后端 API 同样执行校验并返回 422 错误

---

### 2. systemd Unit 文件管理（systemd Unit File Management）

#### REQ-INSP-002: 配置保存时自动生成 systemd Unit 文件
| 字段 | 内容 |
|------|------|
| **ID** | REQ-INSP-002 |
| **描述** | 系统应当在巡检配置保存（PUT /api/inspection/config）后，根据 SQLite 中的最新配置参数自动生成或更新 `/etc/systemd/system/networkagent-inspection.service` 和 `/etc/systemd/system/networkagent-inspection.timer` 两个 unit 文件。service 文件定义巡检 CLI 执行命令（`python3.11 -m src.inspection_cli run`）和运行环境（WorkingDirectory、User、Restart 策略）；timer 文件定义触发规则（OnUnitActiveSec=巡检间隔秒数）。 |
| **来源引用** | PM 用户需求第2项 —「systemd timer 管理：配置保存后自动生成/更新 systemd timer 和 service 文件」+ PM systemd 架构要求段 —「networkagent-inspection.timer → OnUnitActiveSec=间隔；networkagent-inspection.service → 调用 python -m src.inspection_cli run」 |
| **优先级** | Must Have |
| **依赖模块** | MOD-WEB-004 (inspection_repository.py), MOD-016 (config_manager.py) |
| **备注** | Unit 文件生成需使用模板化方式（非字符串拼接），确保格式正确；文件中不应硬编码绝对路径，使用项目安装路径变量 |

**验收标准：**
- **AC-INSP-002-01** — service 文件生成内容正确
  - Given SQLite 中巡检超时 timeout_seconds=30
  - When 运维人员通过 Web UI 保存巡检配置
  - Then 系统应当在 /etc/systemd/system/ 下生成 networkagent-inspection.service 文件，ExecStart 行为 `python3.11 -m src.inspection_cli run`，包含 TimeoutStopSec=30 和 Restart=on-failure 配置
- **AC-INSP-002-02** — timer 文件生成内容正确
  - Given SQLite 中巡检间隔 interval_minutes=10（即 600 秒）
  - When 运维人员保存配置
  - Then 系统应当生成 networkagent-inspection.timer 文件，OnUnitActiveSec=600，且 timer 的 Unit 段指向 networkagent-inspection.service
- **AC-INSP-002-03** — 配置变更后更新 unit 文件
  - Given 已有 unit 文件，巡检间隔为 600 秒
  - When 运维人员将间隔改为 300 秒（5 分钟）并保存
  - Then 系统应当覆写 networkagent-inspection.timer 文件，OnUnitActiveSec 更新为 300，同时保留 service 文件不变（若 service 配置未变）
- **AC-INSP-002-04** — 文件写入权限不足时的错误处理
  - Given 运行 FastAPI 的进程用户无 /etc/systemd/system/ 目录写入权限
  - When 系统尝试生成 unit 文件
  - Then 系统应当返回明确错误信息"systemd unit 文件写入失败：权限不足，请以 root 或 sudo 权限运行"，配置保存操作回滚（不写入 SQLite 新配置），Web UI 显示错误提示

---

#### REQ-INSP-003: systemd daemon-reload 自动执行
| 字段 | 内容 |
|------|------|
| **ID** | REQ-INSP-003 |
| **描述** | 系统在生成或更新 systemd unit 文件后，应当自动执行 `systemctl daemon-reload` 命令使 systemd 识别文件变更，随后根据配置决定是否自动重启 timer（若 timer 此前为 active 状态则 restart，若为 inactive 则仅 reload 不启动）。 |
| **来源引用** | PM 用户需求第2项 —「配置保存后自动生成/更新 systemd timer 和 service 文件」— systemd 标准运维流程要求 unit 文件变更后必须执行 daemon-reload |
| **优先级** | Must Have |
| **依赖模块** | MOD-WEB-004 (inspection_repository.py) |
| **备注** | daemon-reload 需要 root 或 sudo 权限；若进程无权限需提供降级方案（见 REQ-INSP-NF-003） |

**验收标准：**
- **AC-INSP-003-01** — unit 文件变更后自动 reload
  - Given 系统刚写入新的 networkagent-inspection.timer 文件
  - When 写入操作成功完成
  - Then 系统应当自动执行 `systemctl daemon-reload`，执行成功后 systemd 识别到新的 timer 配置
- **AC-INSP-003-02** — reload 后自动重启活跃 timer
  - Given daemon-reload 执行成功，且 reload 前 networkagent-inspection.timer 状态为 active
  - When daemon-reload 完成
  - Then 系统应当自动执行 `systemctl restart networkagent-inspection.timer`，timer 以新间隔重新开始计时
- **AC-INSP-003-03** — 首次配置时不自动启动
  - Given 此前系统从未部署过巡检 unit 文件（timer 不存在），运维人员首次保存巡检配置
  - When daemon-reload 完成后检测到 timer 状态为 inactive
  - Then 系统不自动启动 timer（等待运维人员通过 Web UI 手动 enable + start，见 REQ-INSP-007、REQ-INSP-006）

---

### 3. 巡检状态查询（Inspection Status Query）

#### REQ-INSP-004: systemd Timer 状态查询 API
| 字段 | 内容 |
|------|------|
| **ID** | REQ-INSP-004 |
| **描述** | 系统应当提供后端 API 端点（GET /api/inspection/status），通过执行 `systemctl show networkagent-inspection.timer` 和 `systemctl show networkagent-inspection.service` 命令查询 systemd timer 和 service 的实时状态，返回结构化 JSON 数据，包含：timer ActiveState（active/inactive）、UnitFileState（enabled/disabled）、NextElapseUSRealtime（下次触发时间戳）、service ActiveState（active/inactive）、service SubState（running/dead/exited）。 |
| **来源引用** | PM 用户需求第3项 —「巡检状态查询：Web UI 可查看 systemd timer 状态（active/inactive/enabled/disabled）」+ PM systemd 架构要求段 |
| **优先级** | Must Have |
| **依赖模块** | MOD-WEB-001 (inspection_router.py) |
| **备注** | systemctl show 命令以 `Key=Value` 格式输出，需解析为标准 JSON；命令执行使用 subprocess.run，设置超时（5 秒）防止阻塞 |

**验收标准：**
- **AC-INSP-004-01** — timer 正常运行时状态查询
  - Given networkagent-inspection.timer 已 enable 且 active，service 上次运行成功（SubState=dead 表示一次性任务完成）
  - When 后端调用 GET /api/inspection/status
  - Then 返回 JSON 包含：`{"timer": {"active_state": "active", "unit_file_state": "enabled", "next_trigger": "2026-07-10T14:20:00+08:00"}, "service": {"active_state": "inactive", "sub_state": "dead"}, "last_inspection": {...}}`，HTTP 200
- **AC-INSP-004-02** — timer 未部署时状态查询
  - Given 系统中不存在 networkagent-inspection.timer 文件
  - When 调用 GET /api/inspection/status
  - Then 返回 JSON：`{"timer": {"active_state": "not-found", "unit_file_state": "not-found"}, "service": {"active_state": "not-found"}, "error": null}`，HTTP 200
- **AC-INSP-004-03** — systemctl 命令执行超时处理
  - Given 系统负载极高导致 systemctl show 响应超过 5 秒
  - When 调用 GET /api/inspection/status
  - Then 后端应当终止命令执行，返回 `{"error": "systemctl 命令执行超时", "timer": null, "service": null}`，HTTP 503，记录错误日志

---

#### REQ-INSP-005: Web UI 巡检状态面板
| 字段 | 内容 |
|------|------|
| **ID** | REQ-INSP-005 |
| **描述** | Web UI 巡检配置页面应当展示 systemd timer 和 service 的实时状态面板，包括：timer 运行状态（active/inactive 带绿/灰状态指示灯）、定时器启用状态（enabled/disabled）、下次触发时间、最近一次巡检执行时间和结果摘要。状态面板通过前端轮询（每 5 秒）调用 GET /api/inspection/status 自动刷新。 |
| **来源引用** | PM 用户需求第3项 —「巡检状态查询：Web UI 可查看 systemd timer 状态（active/inactive/enabled/disabled）」 |
| **优先级** | Must Have |
| **依赖模块** | InspectionConfigView.vue, inspection.ts Pinia store |
| **备注** | v0.1.0 的 InspectionConfigView.vue 无状态面板，需新增整个状态面板 UI 区域 |

**验收标准：**
- **AC-INSP-005-01** — 状态面板实时展示
  - Given networkagent-inspection.timer 状态为 active + enabled，下次触发时间为 3 分钟后
  - When 运维人员打开 Web UI "巡检配置"页面
  - Then 状态面板应当显示：timer 状态指示灯（绿色）、"运行中"文本标签、"已启用"标签、下次触发时间（如"2026-07-10 14:20:00"）、最近巡检时间及结果摘要
- **AC-INSP-005-02** — timer 停止时状态面板更新
  - Given timer 当前为 active 状态，状态面板显示绿色指示灯
  - When 运维人员通过控制按钮停止 timer（见 REQ-INSP-006），下一个轮询周期（5 秒内）
  - Then 状态面板应当更新：指示灯变为灰色、"已停止"文本标签、下次触发时间显示"无（已停止）"
- **AC-INSP-005-03** — systemd 不可用时的降级显示
  - Given 部署环境不支持 systemd（如开发环境 Windows/macOS）
  - When 运维人员打开巡检配置页面
  - Then 状态面板应当显示"当前环境不支持 systemd，巡检状态不可用"提示，控制按钮全部禁用

---

### 4. 巡检生命周期控制（Inspection Lifecycle Control）

#### REQ-INSP-006: systemd Service 生命周期控制 API
| 字段 | 内容 |
|------|------|
| **ID** | REQ-INSP-006 |
| **描述** | 系统应当提供后端 API 端点用于控制 networkagent-inspection.service 的生命周期：POST /api/inspection/start（systemctl start）、POST /api/inspection/stop（systemctl stop）、POST /api/inspection/restart（systemctl restart）。每个端点在执行 systemctl 命令后返回操作结果（成功/失败 + systemctl 输出）。stop 操作仅终止当前正在运行的巡检进程，不停止 timer（timer 仍会按间隔触发）。 |
| **来源引用** | PM 用户需求第4项 —「巡检控制：Web UI 可暂停（stop）、恢复（start）、重启（restart）、启用（enable）、禁用（disable）巡检服务」+ PM systemd 架构要求段 |
| **优先级** | Must Have |
| **依赖模块** | MOD-WEB-001 (inspection_router.py) |
| **备注** | start/stop/restart 操作需要 root 或 sudo 权限；需与 REQ-INSP-NF-003 权限方案协调 |

**验收标准：**
- **AC-INSP-006-01** — 启动巡检服务
  - Given networkagent-inspection.service 未在运行（active_state=inactive），timer 已 enabled
  - When 后端收到 POST /api/inspection/start 请求
  - Then 系统应当执行 `systemctl start networkagent-inspection.service`，返回 `{"result": "success", "action": "start", "message": "巡检服务已启动"}`，HTTP 200
- **AC-INSP-006-02** — 停止正在运行的巡检
  - Given networkagent-inspection.service 正在执行巡检（active_state=active, sub_state=running）
  - When 后端收到 POST /api/inspection/stop 请求
  - Then 系统应当执行 `systemctl stop networkagent-inspection.service`，终止当前巡检进程，返回 `{"result": "success", "action": "stop", "message": "巡检服务已停止"}`；timer 保持 active + enabled 状态不受影响
- **AC-INSP-006-03** — 重启巡检服务
  - Given service 任意状态
  - When 后端收到 POST /api/inspection/restart 请求
  - Then 系统应当执行 `systemctl restart networkagent-inspection.service`，返回操作结果
- **AC-INSP-006-04** — systemctl 命令执行失败处理
  - Given systemctl start 因权限不足执行失败（返回非 0 退出码）
  - When 后端收到 POST /api/inspection/start
  - Then 系统应当返回 `{"result": "failed", "action": "start", "message": "systemctl 执行失败：权限不足", "detail": "<stderr>"}`，HTTP 500

---

#### REQ-INSP-007: systemd Timer 启用/禁用 API
| 字段 | 内容 |
|------|------|
| **ID** | REQ-INSP-007 |
| **描述** | 系统应当提供后端 API 端点用于控制 networkagent-inspection.timer 的启用和禁用：POST /api/inspection/enable（systemctl enable + start timer）、POST /api/inspection/disable（systemctl disable + stop timer）。启用操作会设置 timer 开机自启并立即启动；禁用操作会停止 timer 并取消开机自启。 |
| **来源引用** | PM 用户需求第4项 —「启用（enable）、禁用（disable）巡检服务」 |
| **优先级** | Must Have |
| **依赖模块** | MOD-WEB-001 (inspection_router.py) |
| **备注** | enable/disable 与 start/stop 的区别：enable 操作的是 timer 而非 service；disable 后 timer 不再按计划触发，但可手动 start service 执行单次巡检 |

**验收标准：**
- **AC-INSP-007-01** — 启用巡检定时器
  - Given networkagent-inspection.timer 处于 disabled + inactive 状态
  - When 后端收到 POST /api/inspection/enable 请求
  - Then 系统应当执行 `systemctl enable networkagent-inspection.timer && systemctl start networkagent-inspection.timer`；返回 `{"result": "success", "action": "enable", "timer_active_state": "active", "timer_unit_file_state": "enabled"}`，HTTP 200
- **AC-INSP-007-02** — 禁用巡检定时器
  - Given timer 处于 enabled + active 状态
  - When 后端收到 POST /api/inspection/disable 请求
  - Then 系统应当执行 `systemctl stop networkagent-inspection.timer && systemctl disable networkagent-inspection.timer`；返回 `{"result": "success", "action": "disable", "timer_active_state": "inactive", "timer_unit_file_state": "disabled"}`；disable 后即使系统重启 timer 也不会自动启动
- **AC-INSP-007-03** — 已在目标状态时幂等处理
  - Given timer 已处于 enabled + active 状态
  - When 后端再次收到 POST /api/inspection/enable 请求
  - Then 系统应当检测到 timer 已启用，返回 `{"result": "success", "action": "enable", "message": "timer 已处于启用状态，无需操作"}`，不做重复操作

---

#### REQ-INSP-008: Web UI 巡检控制按钮
| 字段 | 内容 |
|------|------|
| **ID** | REQ-INSP-008 |
| **描述** | Web UI 巡检配置页面的状态面板区域应当提供巡检控制操作按钮组，包括：启动（start）、停止（stop）、重启（restart）、启用（enable）、禁用（disable）五个按钮。按钮的启用/禁用状态根据当前 timer/service 状态动态变化（如 timer 已 active 时"启动"按钮禁用、"停止"按钮可用；timer 已 disabled 时"启用"按钮可用、"禁用"按钮禁用）。点击按钮后调用对应后端 API（REQ-INSP-006、REQ-INSP-007），操作完成后自动刷新状态面板。 |
| **来源引用** | PM 用户需求第4项 —「Web UI 可暂停（stop）、恢复（start）、重启（restart）、启用（enable）、禁用（disable）巡检服务」 |
| **优先级** | Must Have |
| **依赖模块** | InspectionConfigView.vue, inspection.ts Pinia store |
| **备注** | v0.1.0 的 InspectionConfigView.vue 无控制按钮，需新增按钮组；所有按钮操作需二次确认弹窗防误触 |

**验收标准：**
- **AC-INSP-008-01** — 按钮状态动态切换
  - Given timer 当前 active + enabled
  - When 运维人员查看控制按钮区域
  - Then "启动"和"启用"按钮应当置灰（禁用状态），"停止"和"禁用"和"重启"按钮可用
- **AC-INSP-008-02** — 停止操作二次确认
  - Given 运维人员点击"停止"按钮
  - When 系统尚未执行停止操作
  - Then 前端应当弹出确认对话框"确认停止巡检服务？停止后定时巡检将暂停，但 timer 仍保持启用"，运维人员确认后执行 systemctl stop
- **AC-INSP-008-03** — 操作结果即时反馈
  - Given 运维人员点击"重启"按钮并确认
  - When 后端执行 systemctl restart 成功
  - Then 按钮区域应当短暂显示 Loading 状态，操作完成后弹出绿色 Toast "巡检服务已重启"，状态面板自动刷新显示新状态
- **AC-INSP-008-04** — 操作失败错误展示
  - Given 后端 systemctl restart 执行失败（如权限不足）
  - When 后端返回 500 错误
  - Then Web UI 应当弹出红色 Toast 显示具体失败原因（"重启失败：权限不足，请联系管理员"），按钮恢复操作前状态

---

### 5. 手动巡检触发（Manual Inspection Trigger）

#### REQ-INSP-009: 手动触发巡检（保留 v0.1.0 能力）
| 字段 | 内容 |
|------|------|
| **ID** | REQ-INSP-009 |
| **描述** | 系统应当保留手动触发一次巡检的功能（POST /api/inspection/trigger），运维人员通过 Web UI 按钮触发后，后端立即执行一次全量设备巡检（不依赖 systemd timer 定时触发）。手动巡检的执行逻辑与定时巡检完全相同（检查接口状态 + CPU 使用率），结果持久化至 SQLite InspectionRecord 表（trigger_mode=MANUAL）。 |
| **来源引用** | PM 用户需求第5项 —「手动触发：保留手动触发一次巡检的功能」+ PM 现有代码分析摘要 —「POST /api/inspection/trigger → 手动触发...返回 "巡检已触发"」 |
| **优先级** | Must Have |
| **依赖模块** | MOD-WEB-001 (inspection_router.py), MOD-002 (inspection_scheduler.py 的 run_inspection_once 逻辑迁移至 CLI), InspectionConfigView.vue |
| **备注** | v0.1.0 中手动触发在当前进程 daemon 线程中执行；v0.2.0 可选择通过 systemctl start 触发（推荐）或保留进程内执行；需与 REQ-INSP-014 CLI 入口共享巡检核心逻辑 |

**验收标准：**
- **AC-INSP-009-01** — 手动触发巡检成功
  - Given 系统中已纳管 2 台设备，当前无巡检在运行
  - When 运维人员点击 Web UI 上"手动触发巡检"按钮
  - Then 系统应当触发一次巡检（通过 systemctl start networkagent-inspection.service 或进程内调用），返回 `{"result": "success", "message": "巡检已触发", "trigger_mode": "MANUAL"}`，巡检结果持久化至 InspectionRecord 表
- **AC-INSP-009-02** — 巡检进行中防重复触发
  - Given 一次手动巡检正在执行中（service active_state=running）
  - When 运维人员再次点击"手动触发巡检"
  - Then 系统应当检测到巡检已在进行，返回 `{"result": "rejected", "message": "巡检正在执行中，请等待完成后再触发"}`，HTTP 409
- **AC-INSP-009-03** — 手动触发不受 timer disable 影响
  - Given networkagent-inspection.timer 处于 disabled 状态
  - When 运维人员点击"手动触发巡检"
  - Then 系统应当正常执行巡检（手动触发不依赖 timer 状态），结果正常持久化

---

### 6. 巡检历史（Inspection History）

#### REQ-INSP-010: 巡检结果持久化至 SQLite
| 字段 | 内容 |
|------|------|
| **ID** | REQ-INSP-010 |
| **描述** | 系统应当在每次巡检执行完成后（无论定时触发还是手动触发），将巡检结果持久化至 SQLite InspectionRecord 表，记录字段包括：触发方式（trigger_mode: SCHEDULED / MANUAL）、开始时间（started_at）、完成时间（completed_at）、检查设备总数（total_devices）、发现异常数（anomaly_count）、巡检状态（status: SUCCESS / PARTIAL / FAILED）、详细信息（details: JSON，含每台设备的诊断摘要）。持久化操作在巡检 CLI 进程内部完成，不与 Web 进程耦合。 |
| **来源引用** | PM 用户需求第6项 —「巡检历史：每次巡检结果持久化 SQLite（时间、设备数、异常数、状态）」+ PM 现有代码分析 —「InspectionRecord 表: id, trigger_mode, started_at, completed_at, total_devices, anomaly_count, details(JSON)」 |
| **优先级** | Must Have |
| **依赖模块** | MOD-WEB-003 (inspection_models.py), MOD-WEB-004 (inspection_repository.py), CLI 入口 (src/inspection_cli.py) |
| **备注** | 现有 InspectionRecord 表结构已满足 v0.2.0 需求；需新增 status 字段（SUCCESS/PARTIAL/FAILED）以支持巡检结果状态标识 |

**验收标准：**
- **AC-INSP-010-01** — 定时巡检结果持久化
  - Given systemd timer 触发一次定时巡检（SCHEDULED 模式），巡检了 3 台设备，发现 1 台异常
  - When 巡检 CLI 进程执行完成
  - Then SQLite InspectionRecord 表中应当新增一条记录：trigger_mode=SCHEDULED, total_devices=3, anomaly_count=1, status=PARTIAL, started_at 和 completed_at 记录实际时间，details JSON 包含每台设备的诊断结果
- **AC-INSP-010-02** — 手动巡检结果持久化
  - Given 运维人员手动触发一次巡检（MANUAL 模式），所有设备正常
  - When 巡检完成
  - Then InspectionRecord 新增记录：trigger_mode=MANUAL, total_devices=2, anomaly_count=0, status=SUCCESS
- **AC-INSP-010-03** — 巡检执行异常时的错误记录
  - Given 巡检过程中 CLI 进程崩溃或设备全部不可达
  - When 巡检异常终止
  - Then InspectionRecord 中 status=FAILED，details 中记录错误原因和已检查的部分结果（如有），completed_at 记录异常终止时间

---

#### REQ-INSP-011: 巡检历史查询 API 与 Web UI 展示
| 字段 | 内容 |
|------|------|
| **ID** | REQ-INSP-011 |
| **描述** | 系统应当提供巡检历史查询 API（GET /api/inspection/history），支持分页和按触发方式（trigger_mode=SCHEDULED/MANUAL）筛选；Web UI 巡检历史页面以表格展示历史记录，每条显示触发方式标签、检查设备数、异常数、状态、开始时间、完成时间，支持按触发方式筛选和分页。 |
| **来源引用** | PM 用户需求第6项 —「巡检历史」+ PM 现有代码分析 —「GET /api/inspection/history → 分页巡检历史（支持 trigger_mode 筛选）」+「InspectionHistoryView.vue 基本满足 v0.2.0 巡检历史需求」 |
| **优先级** | Must Have |
| **依赖模块** | MOD-WEB-001 (inspection_router.py), MOD-WEB-004 (inspection_repository.py), InspectionHistoryView.vue |
| **备注** | v0.1.0 已有完整的分页历史查询实现，v0.2.0 仅需新增 status 列展示 + 微调字段对齐 |

**验收标准：**
- **AC-INSP-011-01** — 历史列表分页展示
  - Given 系统中有 25 条巡检历史记录
  - When 运维人员打开 Web UI "巡检历史"页面
  - Then 页面应当展示第 1 页记录（默认每页 10 条），每条包含：触发方式标签（定时/手动，颜色区分）、检查设备数、异常数、状态标签（SUCCESS 绿色/ PARTIAL 黄色/ FAILED 红色）、开始时间、完成时间、耗时
- **AC-INSP-011-02** — 按触发方式筛选
  - Given 历史包含 15 条 SCHEDULED 和 10 条 MANUAL 记录
  - When 运维人员在筛选下拉中选择 trigger_mode="MANUAL"
  - Then 列表应当仅展示 10 条手动触发的历史记录
- **AC-INSP-011-03** — 详情展开
  - Given 某次巡检 details JSON 包含每台设备的诊断结果
  - When 运维人员点击该记录的"详情"展开按钮
  - Then 系统应当展示该次巡检的详细结果：每台设备名称、诊断命令、诊断结果摘要、是否触发告警

---

### 7. 配置持久化与同步（Configuration Persistence & Sync）

#### REQ-INSP-012: 巡检参数 SQLite 持久化
| 字段 | 内容 |
|------|------|
| **ID** | REQ-INSP-012 |
| **描述** | 系统应当将巡检配置参数（interval_minutes, timeout_seconds, retry_max, retry_backoff）持久化存储至 SQLite SystemConfig 表（config_key / config_value 键值对模型）。配置的读取优先级为：SQLite > config.yaml 默认值。所有配置变更通过 API（PUT /api/inspection/config）完成，不得要求运维人员手动编辑 config.yaml。 |
| **来源引用** | PM 用户需求第7项 —「配置持久化：巡检参数存储 SQLite」+ PM 技术约束 —「后端使用 FastAPI + SQLAlchemy + SQLite」+ PM 现有代码分析 —「获取巡检配置：从 SQLite SystemConfig 表读取」 |
| **优先级** | Must Have |
| **依赖模块** | MOD-WEB-004 (inspection_repository.py), MOD-016 (config_manager.py) |
| **备注** | v0.1.0 已实现 SQLite 读写巡检配置（get_config / update_config），v0.2.0 需要：①将 config_manager 的 polling_interval_seconds 替换为 retry_backoff；②与 config.yaml 的降级链保持兼容 |

**验收标准：**
- **AC-INSP-012-01** — SQLite 优先读取
  - Given SQLite SystemConfig 表中已存储 interval_minutes=15, config.yaml 中 inspection.interval_minutes=5
  - When 系统启动并读取巡检配置
  - Then 应当返回 interval_minutes=15（SQLite 值优先于 config.yaml）
- **AC-INSP-012-02** — SQLite 无值时降级到 config.yaml
  - Given SQLite SystemConfig 表中不存在 timeout_seconds 配置键
  - When 系统读取 timeout_seconds
  - Then 应当返回 config.yaml 中的默认值 timeout_seconds=30
- **AC-INSP-012-03** — 配置更新写入 SQLite
  - Given 运维人员通过 Web UI 将 retry_max 从 3 改为 5
  - When 配置保存成功
  - Then SQLite SystemConfig 表中 retry_max 的值应当更新为 5，后续读取返回 5

---

#### REQ-INSP-013: 配置同步至 systemd Unit 文件
| 字段 | 内容 |
|------|------|
| **ID** | REQ-INSP-013 |
| **描述** | 当 SQLite 中的巡检配置保存成功后，系统应当将 interval_minutes 同步为 systemd timer 文件的 OnUnitActiveSec 值（分钟转秒），将 timeout_seconds 同步为 systemd service 文件的 TimeoutStopSec 值。同步过程为：读取 SQLite 最新配置 → 生成 unit 文件内容（模板渲染）→ 写入 /etc/systemd/system/ 路径 → 执行 daemon-reload → 若 timer 当前 active 则 restart。 |
| **来源引用** | PM 用户需求第7项 —「同步到 systemd 配置」+ PM systemd 架构要求 —「OnUnitActiveSec=间隔」 |
| **优先级** | Must Have |
| **依赖模块** | MOD-WEB-004 (inspection_repository.py), REQ-INSP-002, REQ-INSP-003 |
| **备注** | 此为 REQ-INSP-002 和 REQ-INSP-003 的组合编排，确保 SQLite 到 systemd 的配置一致性 |

**验收标准：**
- **AC-INSP-013-01** — SQLite → systemd 同步链路
  - Given SQLite 中 interval_minutes=10, timeout_seconds=60
  - When 运维人员保存配置
  - Then 系统应当：①更新 SQLite；②生成 timer 文件含 OnUnitActiveSec=600；③生成 service 文件含 TimeoutStopSec=60；④执行 daemon-reload；⑤若 timer 为 active 则 restart
- **AC-INSP-013-02** — 同步失败不影响 SQLite 数据一致性
  - Given SQLite 更新成功但 systemd unit 文件写入失败（权限不足）
  - When 同步过程异常
  - Then 系统应当返回部分成功状态：SQLite 配置已更新，但 systemd 同步失败（含错误原因），提示运维人员手动处理权限问题后可通过"重新同步"按钮重试，SQLite 数据不回滚

---

### 8. CLI 巡检入口（CLI Inspection Entry Point）

#### REQ-INSP-014: CLI 巡检执行入口
| 字段 | 内容 |
|------|------|
| **ID** | REQ-INSP-014 |
| **描述** | 系统应当提供独立的 CLI 巡检执行入口 `python3.11 -m src.inspection_cli run`，供 systemd service 调用。CLI 入口应当：①从 SQLite 加载设备列表和巡检配置；②按 `run_inspection_once()` 逻辑执行全量设备巡检（接口状态 + CPU 检查）；③将巡检结果持久化至 SQLite InspectionRecord 表（trigger_mode=SCHEDULED）；④在标准输出记录巡检摘要日志；⑤以适当的退出码退出（0=全部正常，1=部分异常，2=执行失败）。 |
| **来源引用** | PM 技术约束 —「CLI 入口: python3.11 -m src.inspection_cli run」+ PM systemd 架构要求 —「networkagent-inspection.service → 调用 python -m src.inspection_cli run」+ PM 现有代码分析 —「run_inspection_once(device_list) → 手动全量巡检」 |
| **优先级** | Must Have |
| **依赖模块** | MOD-002 (inspection_scheduler.py 的 run_inspection_once 逻辑), MOD-WEB-003, MOD-WEB-004, MOD-016 |
| **备注** | CLI 入口代码从 inspection_scheduler.py 的 run_inspection_once 方法提取并重构为独立模块；CLI 进程与 Web 进程完全隔离，通过 SQLite 共享数据 |

**验收标准：**
- **AC-INSP-014-01** — CLI 正常执行并退出
  - Given SQLite 中已纳管 2 台设备，巡检间隔配置为 10 分钟
  - When 在终端执行 `python3.11 -m src.inspection_cli run`
  - Then 进程应当：①从 SQLite 加载设备列表和配置；②对每台设备执行 SSH 诊断（接口状态 + CPU）；③将结果写入 InspectionRecord（trigger_mode=SCHEDULED）；④stdout 输出巡检摘要；⑤以退出码 0 退出（若所有设备正常）
- **AC-INSP-014-02** — CLI 部分异常退出
  - Given 2 台设备中 1 台 CPU 超阈值
  - When CLI 执行巡检
  - Then 进程以退出码 1 退出，InspectionRecord 中 anomaly_count=1, status=PARTIAL
- **AC-INSP-014-03** — CLI 执行失败退出
  - Given SQLite 数据库文件损坏不可读
  - When CLI 尝试加载配置
  - Then 进程应当以退出码 2 退出，stderr 输出错误原因，不产生孤立的 InspectionRecord
- **AC-INSP-014-04** — CLI 运行环境依赖
  - Given systemd service 文件指定 WorkingDirectory 为项目根目录
  - When systemd 触发 `python3.11 -m src.inspection_cli run`
  - Then CLI 进程应当能正确找到 SQLite 数据库文件和 Python 依赖包，不依赖 Web 进程的运行状态

---

### 9. systemd Unit 文件定义与模板

#### REQ-INSP-015: networkagent-inspection.service Unit 文件定义
| 字段 | 内容 |
|------|------|
| **ID** | REQ-INSP-015 |
| **描述** | 系统应当定义 `networkagent-inspection.service` systemd service unit 文件模板，包含以下关键配置：Description=NetworkAgent Inspection Service、ExecStart=python3.11 -m src.inspection_cli run、WorkingDirectory=%i（项目根目录）、User=%i（运行用户）、Type=oneshot（一次性任务）、Restart=on-failure、RestartSec=30、TimeoutStopSec=%s（从配置读取）、StandardOutput=journal、StandardError=journal。 |
| **来源引用** | PM systemd 架构要求 —「networkagent-inspection.service → 调用 python -m src.inspection_cli run」+ PM 技术约束 —「目标部署环境: Alibaba Cloud ECS (47.109.197.217)，使用 systemd」 |
| **优先级** | Must Have |
| **依赖模块** | REQ-INSP-002 (unit 文件生成) |
| **备注** | Type=oneshot 适合一次性巡检任务；RemainAfterExit=yes 可让 service 在任务完成后保持 active 状态便于状态查询；WorkingDirectory 和 User 从部署配置中获取 |

**验收标准：**
- **AC-INSP-015-01** — service 文件模板完整
  - Given 项目部署在 /opt/networkagent/，运行用户为 networkagent
  - When 系统生成 service 文件
  - Then networkagent-inspection.service 应当包含：`[Unit] Description=NetworkAgent Inspection Service`、`[Service] Type=oneshot`、`ExecStart=python3.11 -m src.inspection_cli run`、`WorkingDirectory=/opt/networkagent`、`User=networkagent`、`Restart=on-failure`、`StandardOutput=journal`、`StandardError=journal`
- **AC-INSP-015-02** — TimeoutStopSec 与巡检超时配置一致
  - Given SQLite 中 timeout_seconds=60
  - When 生成 service 文件
  - Then 应当包含 `TimeoutStopSec=60`

---

#### REQ-INSP-016: networkagent-inspection.timer Unit 文件定义
| 字段 | 内容 |
|------|------|
| **ID** | REQ-INSP-016 |
| **描述** | 系统应当定义 `networkagent-inspection.timer` systemd timer unit 文件模板，包含以下关键配置：Description=NetworkAgent Inspection Timer、OnUnitActiveSec=%s（从 interval_minutes 转换的秒数）、Unit=networkagent-inspection.service、Persistent=true（系统启动后补偿执行错过的巡检）、AccuracySec=1s（高精度触发）。 |
| **来源引用** | PM systemd 架构要求 —「networkagent-inspection.timer → 定时触发（OnUnitActiveSec=间隔）」+ PM 技术约束 —「systemd timer 名称: networkagent-inspection.timer」 |
| **优先级** | Must Have |
| **依赖模块** | REQ-INSP-002 (unit 文件生成) |
| **备注** | Persistent=true 确保系统因维护关机后重启能立即补跑一次巡检；OnUnitActiveSec 为相对计时（上次激活后 N 秒），非固定时间点 |

**验收标准：**
- **AC-INSP-016-01** — timer 文件模板完整
  - Given 巡检间隔 interval_minutes=10（即 600 秒）
  - When 系统生成 timer 文件
  - Then networkagent-inspection.timer 应当包含：`[Unit] Description=NetworkAgent Inspection Timer`、`[Timer] OnUnitActiveSec=600`、`Unit=networkagent-inspection.service`、`Persistent=true`、`AccuracySec=1s`、`[Install] WantedBy=timers.target`
- **AC-INSP-016-02** — Persistent=true 行为验证
  - Given timer 设置了 Persistent=true，系统在计划巡检时间处于关机状态
  - When 系统重新开机后
  - Then systemd 应当在开机后立即触发一次巡检（补偿关机期间错过的执行），之后恢复按 OnUnitActiveSec 间隔正常执行

---

### 10. 迁移与废弃（Migration & Decommission）

#### REQ-INSP-017: APScheduler 调度器废弃
| 字段 | 内容 |
|------|------|
| **ID** | REQ-INSP-017 |
| **描述** | 系统应当废弃 v0.1.0 中基于 APScheduler BackgroundScheduler 的巡检调度机制（src/trigger/inspection_scheduler.py 中的 start_scheduler() 和 stop_scheduler() 方法），将其替换为 systemd timer + service 方案。废弃过程中：①保留 run_inspection_once() 核心巡检逻辑并迁移至 CLI 模块（src/inspection_cli.py）；②从 FastAPI 应用启动流程中移除 APScheduler 初始化代码；③从 Python 依赖中移除 apscheduler 包。 |
| **来源引用** | PM 项目背景 —「当前巡检机制使用 APScheduler...存在以下问题：重启服务即丢失定时器状态、无法持久化状态、无法通过 systemd 管理巡检生命周期」+ PM v0.1.0 vs v0.2.0 差异表 —「调度引擎：APScheduler → systemd timer + service」 |
| **优先级** | Must Have |
| **依赖模块** | MOD-002 (inspection_scheduler.py 废弃), src/main.py（移除 APScheduler 初始化）, requirements.txt（移除依赖） |
| **备注** | 废弃 APScheduler 意味着 Web 进程不再承载定时调度逻辑；Web 进程仅负责配置管理、状态查询和手动触发 |

**验收标准：**
- **AC-INSP-017-01** — Web 进程启动不初始化 APScheduler
  - Given 系统升级至 v0.2.0
  - When FastAPI 应用启动（main.py）
  - Then 启动日志中不应出现 APScheduler 初始化相关日志，BackgroundScheduler 不再被实例化，start_scheduler() 不再被调用
- **AC-INSP-017-02** — 巡检核心逻辑迁移至 CLI
  - Given 原 inspection_scheduler.py 中的 run_inspection_once() 方法
  - When 查看 src/inspection_cli.py 模块
  - Then 该模块应当包含等价的巡检核心逻辑（设备列表加载、凭据获取、逐设备诊断、结果持久化），且可独立于 Web 进程运行
- **AC-INSP-017-03** — apscheduler 依赖移除
  - Given 项目 requirements.txt 或 pyproject.toml
  - When 检查依赖列表
  - Then 不应包含 apscheduler 相关依赖项，pip install 不会安装该包

---

## 非功能需求（Non-Functional Requirements）

### 1. 可靠性与容错（Reliability & Fault Tolerance）

#### REQ-INSP-NF-001: systemd Timer 触发精度
| 字段 | 内容 |
|------|------|
| **ID** | REQ-INSP-NF-001 |
| **描述** | systemd timer 的巡检触发间隔偏差应当控制在 ±5 秒以内（通过 AccuracySec=1s 参数），确保定时巡检按配置的间隔稳定触发。 |
| **来源引用** | PM systemd 架构要求 —「OnUnitActiveSec=间隔」— systemd timer 默认精度 1 分钟，需显式设置 AccuracySec=1s 满足巡检精度要求 |
| **优先级** | Should Have |
| **强制等级** | MEDIUM |

**验收标准：**
- **AC-INSP-NF-001-01** — 触发间隔偏差 ≤ 5 秒
  - Given interval_minutes=5（即 300 秒），timer 已 active
  - When 观察连续 10 次 timer 触发的时间间隔
  - Then 每次实际间隔与 300 秒的偏差应当 ≤ 5 秒

---

#### REQ-INSP-NF-002: systemd Service 故障自动恢复
| 字段 | 内容 |
|------|------|
| **ID** | REQ-INSP-NF-002 |
| **描述** | systemd service 文件应当配置 Restart=on-failure 和 RestartSec=30，当巡检 CLI 进程因异常退出（退出码非 0）时，systemd 应当在 30 秒后自动重启巡检任务一次。注意 Type=oneshot 任务不适用 Restart=always（会无限重试），采用 on-failure 策略确保异常时有一次自动恢复机会。 |
| **来源引用** | systemd 最佳实践 + PM 技术约束 —「目标部署环境使用 systemd」— service 的 on-failure 重启策略为 systemd 标准可靠性机制 |
| **优先级** | Should Have |
| **强制等级** | MEDIUM |

**验收标准：**
- **AC-INSP-NF-002-01** — 异常退出后自动重启
  - Given CLI 进程因未捕获异常以退出码 2 退出
  - When systemd 检测到 service 失败（Result=failure）
  - Then systemd 应当在 30 秒后自动重新启动 service 一次（ExecStart 重新执行），若再次失败则不再重试（oneshot + on-failure 特性）
- **AC-INSP-NF-002-02** — 正常退出不重启
  - Given CLI 进程正常完成巡检以退出码 0 退出
  - When service 完成（Result=success）
  - Then systemd 不触发 restart，等待下一次 timer 触发

---

### 2. 安全与权限（Security & Permissions）

#### REQ-INSP-NF-003: systemctl 命令执行权限管理
| 字段 | 内容 |
|------|------|
| **ID** | REQ-INSP-NF-003 |
| **描述** | Web 进程调用 systemctl 命令（daemon-reload, start, stop, restart, enable, disable, show）需要 root 或 sudo 权限。系统应当：①支持通过 sudoers 配置（/etc/sudoers.d/networkagent）授权 Web 进程运行用户免密码执行特定 systemctl 命令；②若未配置权限，后端 API 返回明确错误提示而非静默失败；③systemctl 命令执行使用 subprocess.run 并设置 shell=False 防止命令注入。 |
| **来源引用** | PM 技术约束 —「目标部署环境: Alibaba Cloud ECS (47.109.197.217)，使用 systemd」— 生产部署中 Web 进程通常以非 root 用户运行，需配置 sudoers 授权 |
| **优先级** | Must Have |
| **强制等级** | HIGH |

**验收标准：**
- **AC-INSP-NF-003-01** — 正确配置 sudoers 后命令执行成功
  - Given /etc/sudoers.d/networkagent 中配置了 `networkagent ALL=(root) NOPASSWD: /usr/bin/systemctl * networkagent-inspection.*`
  - When Web 进程以 networkagent 用户执行 `sudo systemctl start networkagent-inspection.timer`
  - Then 命令应当成功执行，不需要密码交互
- **AC-INSP-NF-003-02** — 未配置 sudoers 时返回友好错误
  - Given sudoers 中未配置 systemctl 授权
  - When Web 进程尝试执行 systemctl 命令
  - Then 系统应当捕获 PermissionError 或非 0 退出码，返回结构化错误 `{"error": "systemctl 权限不足，请配置 sudoers: /etc/sudoers.d/networkagent"}`
- **AC-INSP-NF-003-03** — 命令注入防护
  - Given 攻击者尝试在 API 参数中注入恶意 systemctl 命令
  - When 后端执行 systemctl
  - Then subprocess.run 使用 `shell=False` + 参数列表形式（非字符串拼接），额外参数被安全拒绝

---

### 3. 进程隔离（Process Isolation）

#### REQ-INSP-NF-004: 巡检进程与 Web 进程隔离
| 字段 | 内容 |
|------|------|
| **ID** | REQ-INSP-NF-004 |
| **描述** | 巡检 CLI 进程应当通过 systemd service 独立运行，与 FastAPI Web 进程完全隔离：①巡检 CPU/内存消耗不影响 Web API 响应；②Web 进程重启不中断正在执行的巡检任务；③巡检进程崩溃不导致 Web 服务中断。两个进程仅通过 SQLite 数据库共享数据（巡检结果、配置）。 |
| **来源引用** | PM systemd 架构要求 —「networkagent-inspection.service → 调用 python -m src.inspection_cli run」+ PM 项目背景 —「重启服务即丢失定时器状态」问题需通过进程隔离解决 |
| **优先级** | Must Have |
| **强制等级** | HIGH |

**验收标准：**
- **AC-INSP-NF-004-01** — Web 重启不影响巡检
  - Given 一次 SCHEDULED 巡检正在执行中（CLI 进程运行中）
  - When 运维人员重启 FastAPI Web 服务（systemctl restart networkagent-web 或手动杀进程）
  - Then 巡检 CLI 进程应当继续执行不受影响，巡检结果正常写入 SQLite，Web 重启后能查询到该次巡检记录
- **AC-INSP-NF-004-02** — 巡检崩溃不影响 Web
  - Given 巡检 CLI 进程因 OOM 被系统终止
  - When CLI 进程异常退出
  - Then FastAPI Web 服务应当正常运行不受影响，GET /api/inspection/status 正确反映 service 状态为 "failed"，GET /api/inspection/history 返回 CLI 崩溃前的部分记录（如有）

---

### 4. 兼容性（Compatibility）

#### REQ-INSP-NF-005: GenPlatform 端口兼容性
| 字段 | 内容 |
|------|------|
| **ID** | REQ-INSP-NF-005 |
| **描述** | 巡检机制的 systemd 重构不得占用或冲突 80/8000 端口。巡检 CLI 进程不监听任何网络端口（纯命令行执行）；Web UI 巡检管理功能复用现有 FastAPI 8000 端口；systemd timer/service 为操作系统级组件不涉及端口。 |
| **来源引用** | PM 技术约束 —「必须兼容 GenPlatform（不碰 80/8000 端口）」 |
| **优先级** | Must Have |
| **强制等级** | HIGH |

**验收标准：**
- **AC-INSP-NF-005-01** — 巡检 CLI 不监听端口
  - Given 巡检 CLI 进程正在执行 `python3.11 -m src.inspection_cli run`
  - When 检查该进程的网络端口占用
  - Then 巡检进程不应监听任何 TCP/UDP 端口，所有网络操作仅为向设备发起 SSH 连接（出站）
- **AC-INSP-NF-005-02** — systemd unit 文件不绑定端口
  - Given networkagent-inspection.service 和 networkagent-inspection.timer 已部署
  - When 检查 unit 文件内容
  - Then 不包含任何端口绑定或网络监听相关配置

---

#### REQ-INSP-NF-006: systemd 不可用时的降级策略
| 字段 | 内容 |
|------|------|
| **ID** | REQ-INSP-NF-006 |
| **描述** | 系统应当检测部署环境是否支持 systemd（通过 `which systemctl` 或检查 `/run/systemd/system` 路径）。若检测到不支持 systemd（如开发环境 Windows/macOS、Docker 容器未启用 systemd），系统应当：①Web UI 巡检状态面板显示"当前环境不支持 systemd，巡检管理功能不可用"；②所有 systemctl 相关 API 返回功能不可用状态码（HTTP 503）；③手动触发巡检（REQ-INSP-009）仍可正常使用（绕过 systemd 直接调用 CLI 逻辑）。 |
| **来源引用** | PM 技术约束 —「目标部署环境: Alibaba Cloud ECS」— 开发环境可能不支持 systemd，需降级处理以保证开发体验 |
| **优先级** | Should Have |
| **强制等级** | MEDIUM |

**验收标准：**
- **AC-INSP-NF-006-01** — 不支持 systemd 时状态面板降级
  - Given 当前运行环境为 Windows（不支持 systemd）
  - When 运维人员打开 Web UI 巡检配置页面
  - Then 状态面板显示"当前环境不支持 systemd，定时巡检功能不可用。您仍可手动触发巡检。"，系统状态指示灯显示为灰色+问号，控制按钮全部禁用
- **AC-INSP-NF-006-02** — 不支持 systemd 时 API 降级
  - Given 环境不支持 systemd
  - When 调用 GET /api/inspection/status
  - Then 返回 `{"error": "systemd_not_available", "message": "当前环境不支持 systemd", "manual_trigger_available": true}`，HTTP 200（非 500 错误，因为这不是系统异常而是环境限制）
- **AC-INSP-NF-006-03** — 手动触发不受影响
  - Given 环境不支持 systemd
  - When 运维人员点击"手动触发巡检"
  - Then 系统应当绕过 systemd，直接在 Web 进程子进程中执行巡检逻辑（或通过 subprocess 调用 python -m src.inspection_cli run），巡检结果正常持久化

---

### 5. 可观测性（Observability）

#### REQ-INSP-NF-007: systemd Service 日志集成
| 字段 | 内容 |
|------|------|
| **ID** | REQ-INSP-NF-007 |
| **描述** | networkagent-inspection.service 的标准输出和标准错误应当输出至 systemd journal（配置 StandardOutput=journal + StandardError=journal），运维人员可通过 `journalctl -u networkagent-inspection.service` 查看巡检 CLI 进程的完整日志，含每次巡检的设备检查详情和异常信息。 |
| **来源引用** | PM systemd 架构要求 — systemd service StandardOutput/StandardError 配置 + systemd 标准运维实践 |
| **优先级** | Should Have |
| **强制等级** | MEDIUM |

**验收标准：**
- **AC-INSP-NF-007-01** — journalctl 可查看巡检日志
  - Given networkagent-inspection.service 已执行过 3 次巡检
  - When 运维人员执行 `journalctl -u networkagent-inspection.service --no-pager`
  - Then 应当输出包含每次巡检的标准输出日志：设备列表、逐设备诊断命令和结果、异常设备汇总、巡检完成摘要
- **AC-INSP-NF-007-02** — 错误日志记录
  - Given 某次巡检中某设备 SSH 连接失败
  - When 查看 journalctl 输出
  - Then 日志中应当包含 ERROR 级别信息，记录设备名称、连接失败原因、时间戳

---

## 外部接口需求（新增 API 端点契约）

以下列出 v0.2.0 巡检 systemd 重构所需的新增和增强 REST API 端点。所有端点挂载在现有 FastAPI 应用（端口 8000），路径前缀 `/api/inspection/`。

### 新增 API 端点

| 接口编号 | HTTP 方法 | 路径 | 说明 | 类型 |
|---------|----------|------|------|------|
| API-INSP-01 | GET | `/api/inspection/status` | 查询 systemd timer + service 状态 | [NEW] |
| API-INSP-02 | POST | `/api/inspection/start` | systemctl start service | [NEW] |
| API-INSP-03 | POST | `/api/inspection/stop` | systemctl stop service | [NEW] |
| API-INSP-04 | POST | `/api/inspection/restart` | systemctl restart service | [NEW] |
| API-INSP-05 | POST | `/api/inspection/enable` | systemctl enable + start timer | [NEW] |
| API-INSP-06 | POST | `/api/inspection/disable` | systemctl stop + disable timer | [NEW] |

### 增强现有 API 端点

| 接口编号 | HTTP 方法 | 路径 | 变更说明 | 类型 |
|---------|----------|------|---------|------|
| API-INSP-07 | GET | `/api/inspection/config` | 返回字段增加 retry_backoff（替换 polling_interval_seconds）；同时返回 systemd 同步状态 | [ENHANCED] |
| API-INSP-08 | PUT | `/api/inspection/config` | 新增入参 retry_backoff；保存成功后自动触发 systemd unit 文件生成 + daemon-reload | [ENHANCED] |
| API-INSP-09 | POST | `/api/inspection/trigger` | 手动触发可通过 systemctl start 替代进程内 daemon 线程执行（可选模式） | [ENHANCED] |
| API-INSP-10 | GET | `/api/inspection/history` | 返回字段增加 status（SUCCESS/PARTIAL/FAILED）；支持按 status 筛选 | [ENHANCED] |

### API 端点详细契约

**API-INSP-01: GET /api/inspection/status**

响应 200:
```json
{
  "timer": {
    "active_state": "active",
    "unit_file_state": "enabled",
    "next_trigger": "2026-07-10T14:20:00+08:00",
    "last_trigger": "2026-07-10T14:10:00+08:00"
  },
  "service": {
    "active_state": "inactive",
    "sub_state": "dead",
    "last_result": "success",
    "last_execution": "2026-07-10T14:10:05+08:00"
  },
  "last_inspection": {
    "record_id": 42,
    "trigger_mode": "SCHEDULED",
    "total_devices": 3,
    "anomaly_count": 0,
    "status": "SUCCESS",
    "completed_at": "2026-07-10T14:10:35+08:00"
  },
  "systemd_available": true
}
```

systemd 不可用时响应 200:
```json
{
  "timer": null,
  "service": null,
  "last_inspection": { ... },
  "systemd_available": false,
  "message": "当前环境不支持 systemd，定时巡检功能不可用。手动触发仍可使用。"
}
```

**API-INSP-02~06 请求/响应模式（以 start 为例）:**

```json
// Request: 无 Body
// Response 200:
{
  "result": "success",
  "action": "start",
  "message": "巡检服务已启动",
  "service_state": {
    "active_state": "active",
    "sub_state": "running"
  }
}
// Response 500:
{
  "result": "failed",
  "action": "start",
  "message": "systemctl 执行失败：权限不足",
  "detail": "Interactive authentication required."
}
```

---

## 与现有系统的集成点

| 集成点 | v0.1.0 现状 | v0.2.0 变更 | 影响 |
|--------|------------|------------|------|
| **Web → Scheduler** | FastAPI startup 初始化 APScheduler | 移除初始化逻辑，改为 systemd unit 文件部署 | 低风险：Web 进程不再持有调度器引用 |
| **Web → systemctl** | 不存在 | 新增 subprocess 调用 systemctl 命令 | 中风险：需配置 sudoers 权限 |
| **CLI → SQLite** | run_inspection_once() 写入 InspectionRecord | 相同逻辑迁移至 CLI 模块 | 低风险：数据表结构不变 |
| **API → SQLite** | inspection_repository 读写 SystemConfig | 增强：增加 retry_backoff 配置项 + systemd unit 文件生成 | 低风险：扩展现有 repository 方法 |
| **Config → SQLite** | config_manager 从 YAML + SQLite 读取 | 保持降级链：SQLite > config.yaml > DEFAULT_CONFIG | 低风险：仅增加配置键 |
| **Web UI → API** | 仅 config + trigger + history | 增强：新增 status/start/stop/restart/enable/disable | 中风险：需新增 Pinia store actions 和 Vue 组件 |

---

## 超出范围（Out of Scope）

以下内容明确不在 v0.2.0 巡检 systemd 重构范围内：

| 编号 | 排除项 | 依据 |
|------|-------|------|
| OOS-INSP-001 | 巡检告警处理流程变更（LangGraph 工作流） | PM 任务聚焦巡检调度机制，不涉及告警处理流程修改 |
| OOS-INSP-002 | 设备 SSH 连接方式变更 | 保持 v0.1.0 的 Mock 实现和接口预留策略 |
| OOS-INSP-003 | 新增告警类型 | 不超出 v0.1.0 已定义的 MAC_FLAPPING / PORT_DOWN / CPU_HIGH |
| OOS-INSP-004 | 多节点分布式巡检 | PM 未提及；v0.2.0 仍为单机部署 |
| OOS-INSP-005 | 巡检通知（邮件/企业微信/钉钉） | PM 未提及 |
| OOS-INSP-006 | systemd 以外的调度系统支持（如 cron、Kubernetes CronJob） | PM 明确要求 systemd timer + service 架构 |
| OOS-INSP-007 | Web UI 其他功能模块的变更 | 仅涉及巡检配置/控制/历史页面；告警管理、设备管理、知识库管理等不在此范围 |
| OOS-INSP-008 | config.yaml 文件格式变更 | config.yaml 保持现有格式，仅弱化其优先级 |

---

## 需求追踪矩阵

| 需求 ID | 需求描述（摘要） | 来源（PM 用户需求项） | 关联用户故事 | 关联 API |
|---------|---------------|---------------------|------------|---------|
| REQ-INSP-001 | Web UI 巡检参数配置 | 用户需求第1项 | US-INSP-001 | API-INSP-07, API-INSP-08 |
| REQ-INSP-002 | 配置保存时自动生成 systemd unit 文件 | 用户需求第2项 | US-INSP-002 | API-INSP-08 |
| REQ-INSP-003 | systemd daemon-reload 自动执行 | 用户需求第2项（派生） | US-INSP-002 | API-INSP-08 |
| REQ-INSP-004 | systemd timer 状态查询 API | 用户需求第3项 | US-INSP-003 | API-INSP-01 |
| REQ-INSP-005 | Web UI 巡检状态面板 | 用户需求第3项 | US-INSP-003 | API-INSP-01 |
| REQ-INSP-006 | systemd service 生命周期控制 API | 用户需求第4项 | US-INSP-004 | API-INSP-02~04 |
| REQ-INSP-007 | systemd timer 启用/禁用 API | 用户需求第4项 | US-INSP-005 | API-INSP-05, API-INSP-06 |
| REQ-INSP-008 | Web UI 巡检控制按钮 | 用户需求第4项 | US-INSP-004, US-INSP-005 | API-INSP-02~06 |
| REQ-INSP-009 | 手动触发巡检（保留） | 用户需求第5项 | US-INSP-006 | API-INSP-09 |
| REQ-INSP-010 | 巡检结果持久化 SQLite | 用户需求第6项 | US-INSP-007 | — (CLI 内部) |
| REQ-INSP-011 | 巡检历史查询与展示 | 用户需求第6项 | US-INSP-007 | API-INSP-10 |
| REQ-INSP-012 | 巡检参数 SQLite 持久化 | 用户需求第7项 | US-INSP-001 | API-INSP-07, API-INSP-08 |
| REQ-INSP-013 | 配置同步至 systemd unit 文件 | 用户需求第7项 | US-INSP-002 | API-INSP-08 |
| REQ-INSP-014 | CLI 巡检执行入口 | 技术约束 — CLI 入口 | US-INSP-008 | — (systemd 调用) |
| REQ-INSP-015 | service unit 文件定义 | systemd 架构要求 | US-INSP-002, US-INSP-008 | — (REQ-INSP-002 生成) |
| REQ-INSP-016 | timer unit 文件定义 | systemd 架构要求 | US-INSP-002, US-INSP-008 | — (REQ-INSP-002 生成) |
| REQ-INSP-017 | APScheduler 调度器废弃 | 项目背景 + 差异表 | US-INSP-008 | — (架构变更) |
| REQ-INSP-NF-001 | systemd timer 触发精度 | systemd 架构要求 | US-INSP-008 | — |
| REQ-INSP-NF-002 | service 故障自动恢复 | systemd 最佳实践 | US-INSP-008 | — |
| REQ-INSP-NF-003 | systemctl 权限管理 | 技术约束 — ECS 部署 | US-INSP-004, US-INSP-005 | API-INSP-02~06 |
| REQ-INSP-NF-004 | 巡检与 Web 进程隔离 | systemd 架构要求 | US-INSP-008 | — |
| REQ-INSP-NF-005 | GenPlatform 端口兼容性 | 技术约束 | US-INSP-008 | — |
| REQ-INSP-NF-006 | systemd 不可用时降级 | 技术约束（开发环境） | US-INSP-003, US-INSP-006 | API-INSP-01 |
| REQ-INSP-NF-007 | service 日志集成 journald | systemd 标准实践 | US-INSP-008 | — |

---

## 开放问题

| 编号 | 问题 | 建议 | 状态 |
|------|------|------|------|
| Q-INSP-001 | systemctl 权限方案选择：sudoers 还是 polkit？ | 建议使用 sudoers（/etc/sudoers.d/networkagent），配置简单且 ECS 环境通用 | 待 PM 确认 |
| Q-INSP-002 | Web 进程运行用户是否与巡检 service 用户一致？ | 建议统一使用 networkagent 用户；若 Web 以 root 运行则可直接调用 systemctl | 待 PM 确认 |
| Q-INSP-003 | 手动触发巡检（REQ-INSP-009）在 systemd 环境下是通过 systemctl start 还是进程内子进程执行？ | 建议：systemd 可用时通过 systemctl start（进程隔离最优），systemd 不可用时降级为进程内子进程（开发体验最优） | 待 PM 确认 |
| Q-INSP-004 | systemd unit 文件的项目根路径（WorkingDirectory）从何处读取？ | 建议从环境变量 `NETWORKAGENT_HOME` 或 config.yaml 的 `app.root_path` 读取 | 待 PM 确认 |
| Q-INSP-005 | 是否需要在 systemd unit 文件中配置 MemoryLimit / CPUQuota 资源限制？ | Demo 阶段不强制；若需展示生产级特性，建议 MemoryLimit=512M、CPUQuota=50% | 待 PM 确认 |
| Q-INSP-006 | v0.1.0 中 APScheduler 的 job_id 机制是否需要迁移至 systemd 对应方案？ | systemd 不直接支持多 job；若后续需要多组巡检策略，可通过多组 timer+service 实现 | 待 PM 确认 |
