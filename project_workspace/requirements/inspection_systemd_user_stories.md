<file_header>
  <author_agent>sub_agent_requirement_analyst</author_agent>
  <timestamp>2026-07-10T00:00:00Z</timestamp>
  <project_name>NetworkAgentDemo</project_name>
  <version>0.2.0</version>
  <input_files>
    <file>PM agent_invocation (内嵌原始需求文本)</file>
  </input_files>
  <phase>PHASE_INSP_02</phase>
  <status>DRAFT</status>
</file_header>

# 巡检机制 systemd 重构 — 用户故事清单

---

## 用户角色地图（Actor x Feature Matrix）

| Actor | 巡检配置管理 | systemd 文件生成 | 状态监控 | 生命周期控制 | 手动触发 | 历史查询 | CLI 执行 |
|--------|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **运维人员 (Operator)** | US-INSP-001 | US-INSP-002 | US-INSP-003 | US-INSP-004, US-INSP-005 | US-INSP-006 | US-INSP-007 | — |
| **系统 (systemd)** | — | — | — | — | — | — | US-INSP-008 |

> 来源：PM agent_invocation —「用户明确提出的 7 项功能需求」

---

## 用户故事详情

---

### US-INSP-001: 通过 Web UI 配置巡检参数并持久化

- **用户故事**：As a 运维人员, I want to 在 Web UI 巡检配置页面上可视化地设置巡检周期、诊断超时、重试次数和重试间隔参数，点击保存后配置自动持久化到 SQLite 并同步到 systemd, so that 我不需要手动编辑 config.yaml 或登录服务器修改 systemd unit 文件，所有巡检参数在 Web 界面上集中管理且配置变更立即生效。
- **关联需求**：REQ-INSP-001, REQ-INSP-012, REQ-INSP-013
- **优先级**：P0 (Must Have)
- **故事点**：[待开发团队评估]
- **关联 API**：API-INSP-07 (GET /api/inspection/config), API-INSP-08 (PUT /api/inspection/config)

**验收标准：**

- **AC-INSP-001-01** — 配置表单加载当前值
  - Given 系统 SQLite 中已存储巡检配置：interval_minutes=10, timeout_seconds=30, retry_max=3, retry_backoff=5
  - When 运维人员打开 Web UI "巡检配置"页面
  - Then 表单各输入框应当预填当前 SQLite 中的存储值，每项配置旁标注说明文字和单位（如"分钟"、"秒"、"次"、"秒"）

- **AC-INSP-001-02** — 修改配置并保存成功
  - Given 运维人员将巡检间隔从 10 分钟改为 15 分钟，点击"保存配置"
  - When 后端接收 PUT /api/inspection/config 请求，校验参数合法
  - Then 系统应当：①将新配置写入 SQLite SystemConfig 表；②触发 systemd unit 文件重新生成（timer 的 OnUnitActiveSec 从 600 更新为 900）；③执行 systemctl daemon-reload；④若 timer 当前 active 则 restart

- **AC-INSP-001-03** — 表单输入校验
  - Given 运维人员在 interval_minutes 输入框中输入 0
  - When 点击"保存配置"
  - Then 前端表单校验应当阻止提交，显示"巡检间隔必须为正整数（分钟）"的红色错误提示；后端 API 同样执行校验，返回 422 Validation Error

- **AC-INSP-001-04** — retry_backoff 参数支持
  - Given v0.1.0 配置页面仅支持 interval_minutes、timeout_seconds、retry_max、polling_interval 四项
  - When v0.2.0 配置页面加载
  - Then 表单中 polling_interval 字段替换为 retry_backoff，运维人员可设置重试间隔秒数（默认值 5，范围 1-300）

- **AC-INSP-001-05** — 配置保存失败时回滚提示
  - Given systemd unit 文件写入因权限不足失败
  - When 运维人员点击"保存配置"
  - Then Web UI 应当显示"配置已保存至数据库，但 systemd 同步失败：权限不足。请检查 sudoers 配置后点击'重新同步'按钮重试"，同时提供"重新同步"按钮

---

### US-INSP-002: 配置保存后自动生成 systemd Unit 文件

- **用户故事**：As a 运维人员, I want to 在 Web UI 上保存巡检配置后，系统自动将最新参数渲染为 systemd timer 和 service unit 文件模板、写入 /etc/systemd/system/ 目录并执行 daemon-reload, so that 巡检配置变更能够自动翻译为 systemd 可识别的调度规则，无需我手动编写和维护 unit 文件，也避免配置不一致导致巡检行为异常。
- **关联需求**：REQ-INSP-002, REQ-INSP-003, REQ-INSP-013, REQ-INSP-015, REQ-INSP-016
- **优先级**：P0 (Must Have)
- **故事点**：[待开发团队评估]
- **关联 API**：API-INSP-08 (PUT /api/inspection/config)

**验收标准：**

- **AC-INSP-002-01** — 首次保存配置时创建 unit 文件
  - Given 系统中尚无 networkagent-inspection.timer 和 networkagent-inspection.service 文件，运维人员通过 Web UI 首次保存巡检配置（interval_minutes=10, timeout_seconds=30）
  - When 后端写入 SQLite 成功后触发 unit 文件生成
  - Then 系统应当在 /etc/systemd/system/ 下创建两个文件：networkagent-inspection.service（ExecStart=python3.11 -m src.inspection_cli run, TimeoutStopSec=30, Type=oneshot, Restart=on-failure）和 networkagent-inspection.timer（OnUnitActiveSec=600, Unit=networkagent-inspection.service, Persistent=true）；随后自动执行 systemctl daemon-reload

- **AC-INSP-002-02** — 配置变更时更新 unit 文件
  - Given 已有 unit 文件，interval_minutes=10（OnUnitActiveSec=600）
  - When 运维人员将巡检间隔改为 5 分钟并保存
  - Then timer 文件应当被覆写，OnUnitActiveSec 更新为 300；service 文件若未涉及变更字段则不覆写（保持已有内容）；随后 daemon-reload + 若 timer 为 active 则 restart

- **AC-INSP-002-03** — unit 文件格式正确、可被 systemd 识别
  - Given unit 文件已生成
  - When 运维人员手动执行 `systemd-analyze verify /etc/systemd/system/networkagent-inspection.service` 和 `networkagent-inspection.timer`
  - Then systemd 应当报告文件语法正确，无错误或警告

- **AC-INSP-002-04** — 生成失败时的错误处理
  - Given 运行 Web 进程的用户无 /etc/systemd/system/ 写入权限
  - When 系统尝试写入 unit 文件
  - Then 系统应当捕获 PermissionError，返回结构化错误信息（含失败原因和建议修复操作），SQLite 写入不回滚（保持数据变更），Web UI 显示错误提示 + "重新同步"按钮

- **AC-INSP-002-05** — 重复保存相同配置时幂等
  - Given unit 文件内容已与 SQLite 配置一致
  - When 运维人员再次点击"保存配置"（参数未实际变更）
  - Then 系统应当检测配置未变化，跳过 unit 文件写入和 daemon-reload，返回"配置无变更，跳过同步"提示

---

### US-INSP-003: 在 Web UI 查看巡检服务实时状态

- **用户故事**：As a 运维人员, I want to 在 Web UI 巡检配置页面上实时查看 systemd timer 和 service 的运行状态（active/inactive、enabled/disabled）、下次触发时间和最近一次巡检结果摘要, so that 我无需 SSH 登录服务器执行 `systemctl status` 命令，在浏览器中即可一目了然巡检服务的健康状况。
- **关联需求**：REQ-INSP-004, REQ-INSP-005
- **优先级**：P0 (Must Have)
- **故事点**：[待开发团队评估]
- **关联 API**：API-INSP-01 (GET /api/inspection/status)

**验收标准：**

- **AC-INSP-003-01** — 状态面板展示完整状态信息
  - Given networkagent-inspection.timer 状态为 active + enabled，下次触发时间为 2026-07-10 14:20:00，最近一次巡检于 14:10:00 完成（3 台设备，0 异常，SUCCESS）
  - When 运维人员打开 Web UI "巡检配置"页面
  - Then 状态面板应当显示：timer 状态指示灯（绿色圆圈 + "运行中"文字）、启用状态标签（蓝色 "已启用"）、下次触发时间（格式化为可读时间）、最近一次巡检记录摘要（时间、设备数、异常数、状态标签）

- **AC-INSP-003-02** — 状态面板数据自动刷新
  - Given 状态面板已展示 timer active 状态
  - When 运维人员在另一个浏览器 Tab 中通过控制按钮停止 timer（见 US-INSP-004），约 5 秒后
  - Then 当前 Tab 的状态面板应当自动更新（前端轮询 GET /api/inspection/status）：timer 指示灯变为灰色、"已停止"文字、下次触发时间显示"无（已停止）"

- **AC-INSP-003-03** — timer 未部署时的状态展示
  - Given 系统中从未保存过巡检配置（unit 文件不存在）
  - When 运维人员打开巡检配置页面
  - Then 状态面板应当显示："巡检定时器未部署"（timer active_state="not-found"），提示运维人员先保存巡检配置

- **AC-INSP-003-04** — systemd 不可用时的降级展示
  - Given 当前运行环境为 Windows（不支持 systemd）
  - When 运维人员打开巡检配置页面
  - Then 状态面板应当显示"当前环境不支持 systemd，定时巡检功能不可用。手动触发仍可使用。"的提示，所有 systemd 相关的状态指标和按钮置灰不可用

- **AC-INSP-003-05** — 最近巡检记录为空时的状态
  - Given timer 已部署但尚未触发过任何巡检（InspectionRecord 表为空）
  - When 状态面板查询最近巡检记录
  - Then "最近巡检"区域应当显示"暂无巡检记录"，不显示空数据或错误

---

### US-INSP-004: 从 Web UI 控制巡检服务的启动、停止和重启

- **用户故事**：As a 运维人员, I want to 在 Web UI 上通过按钮控制巡检服务的启动（start）、停止（stop）和重启（restart），操作时系统弹出二次确认防误触，操作完成后即时反馈结果并刷新状态面板, so that 我能够在不登录服务器的情况下灵活控制巡检服务的运行，如排查问题时暂停巡检、配置变更后重启让新参数生效。
- **关联需求**：REQ-INSP-006, REQ-INSP-008
- **优先级**：P0 (Must Have)
- **故事点**：[待开发团队评估]
- **关联 API**：API-INSP-02 (POST /api/inspection/start), API-INSP-03 (POST /api/inspection/stop), API-INSP-04 (POST /api/inspection/restart)

**验收标准：**

- **AC-INSP-004-01** — 启动巡检服务
  - Given networkagent-inspection.service 当前未运行（active_state=inactive），timer 已 enabled
  - When 运维人员点击"启动"按钮并在确认弹窗中确认
  - Then 系统应当 POST /api/inspection/start，后端执行 systemctl start；返回成功后按钮显示 Loading → 成功 Toast "巡检服务已启动" → 状态面板刷新显示 service active_state=active

- **AC-INSP-004-02** — 停止正在运行的巡检
  - Given service 正在执行一次巡检（active_state=active, sub_state=running）
  - When 运维人员点击"停止"按钮并确认
  - Then 系统应当 POST /api/inspection/stop，后端执行 systemctl stop 终止巡检进程；返回成功后状态面板更新，service active_state=inactive；此时 timer 状态不变（仍为 active + enabled），下次仍会按计划触发

- **AC-INSP-004-03** — 重启巡检服务
  - Given service 任意状态
  - When 运维人员点击"重启"按钮并确认
  - Then 系统应当 POST /api/inspection/restart，后端执行 systemctl restart；若当前有巡检在执行则先 stop 再 start，若未运行则直接 start；返回成功后状态面板刷新

- **AC-INSP-004-04** — 按钮状态动态变化
  - Given timer 已 enable 且 active，service 当前 inactive
  - When 运维人员查看控制按钮
  - Then "启动"按钮可用（蓝色）,"停止"按钮置灰（service 已停止无需再停）,"重启"按钮可用（橙色）,"启用"按钮置灰（timer 已启用）,"禁用"按钮可用（红色）

- **AC-INSP-004-05** — 操作确认弹窗防误触
  - Given 运维人员点击"停止"按钮
  - When 系统弹出确认对话框
  - Then 对话框应当显示："确认停止巡检服务？停止后当前正在执行的巡检将被中断，但定时器（timer）仍保持启用，下次到达触发时间时仍会自动启动巡检。"，提供"确认停止"和"取消"两个按钮

- **AC-INSP-004-06** — systemctl 执行失败的处理
  - Given sudoers 未正确配置导致 systemctl 命令权限不足
  - When 运维人员点击"重启"按钮
  - Then 后端返回 500 错误，Web UI 应当弹出红色 Toast 显示具体错误信息："重启失败：systemctl 权限不足，请检查 /etc/sudoers.d/networkagent 配置"，按钮状态保持不变（不错误地显示为"已重启"）

---

### US-INSP-005: 从 Web UI 启用和禁用巡检定时器

- **用户故事**：As a 运维人员, I want to 在 Web UI 上通过按钮启用（enable）或禁用（disable）巡检定时器，启用后 timer 开始按计划触发巡检且系统重启后自动恢复，禁用后 timer 停止触发且开机不自启, so that 我能够灵活控制巡检计划——在系统维护窗口期间禁用巡检避免误告警，维护完成后一键恢复计划运行。
- **关联需求**：REQ-INSP-007, REQ-INSP-008
- **优先级**：P0 (Must Have)
- **故事点**：[待开发团队评估]
- **关联 API**：API-INSP-05 (POST /api/inspection/enable), API-INSP-06 (POST /api/inspection/disable)

**验收标准：**

- **AC-INSP-005-01** — 启用巡检定时器
  - Given networkagent-inspection.timer 处于 disabled + inactive 状态
  - When 运维人员点击"启用"按钮并在确认弹窗中确认
  - Then 系统应当 POST /api/inspection/enable，后端依次执行 systemctl enable networkagent-inspection.timer → systemctl start networkagent-inspection.timer；返回成功后状态面板更新：timer 指示灯变绿、"已启用"标签显示；系统重启后 timer 将自动启动

- **AC-INSP-005-02** — 禁用巡检定时器
  - Given timer 处于 enabled + active 状态
  - When 运维人员点击"禁用"按钮并在确认弹窗中确认
  - Then 系统应当 POST /api/inspection/disable，后端依次执行 systemctl stop networkagent-inspection.timer → systemctl disable networkagent-inspection.timer；返回成功后状态面板更新：timer 指示灯变灰、"已禁用"标签显示；禁用后即使系统重启 timer 也不会自动启动

- **AC-INSP-005-03** — 禁用定时器后手动触发仍可用
  - Given timer 已被禁用（disabled + inactive）
  - When 运维人员点击"手动触发巡检"按钮
  - Then 手动巡检应当正常执行（不依赖 timer 状态），巡检结果正常持久化（见 US-INSP-006）

- **AC-INSP-005-04** — 启用/禁用的二次确认
  - Given 运维人员点击"禁用"按钮
  - When 系统弹出确认对话框
  - Then 对话框应当显示："确认禁用巡检定时器？禁用后定时巡检将停止触发，且系统重启后不会自动恢复。您仍然可以手动触发巡检。'禁用'后需手动点击'启用'才能恢复定时巡检。"

- **AC-INSP-005-05** — 已在目标状态时的幂等提示
  - Given timer 已处于 disabled 状态
  - When 运维人员再次点击"禁用"按钮
  - Then 系统应当检测到 timer 已禁用，返回"定时器已处于禁用状态，无需操作"，不重复执行 systemctl 命令

---

### US-INSP-006: 手动触发一次巡检

- **用户故事**：As a 运维人员, I want to 在 Web UI 上点击"手动触发巡检"按钮即可立即对所有纳管设备执行一次完整的巡检检查（接口状态 + CPU 使用率），巡检结果自动持久化到历史记录, so that 在系统维护后我可以立即验证设备状态、或在 timer 未触发时主动发起检查，无需等待定时器到点。
- **关联需求**：REQ-INSP-009
- **优先级**：P0 (Must Have)
- **故事点**：[待开发团队评估]
- **关联 API**：API-INSP-09 (POST /api/inspection/trigger)

**验收标准：**

- **AC-INSP-006-01** — 手动触发巡检成功
  - Given 系统中已纳管 Core-SW-01 和 Access-SW-02 两台设备，当前无巡检在执行
  - When 运维人员点击"手动触发巡检"按钮
  - Then 系统应当触发一次全量巡检，返回"巡检已触发"提示；巡检完成后，InspectionRecord 表中新增一条记录：trigger_mode=MANUAL, total_devices=2, status=SUCCESS 或 PARTIAL 或 FAILED（取决于实际结果）

- **AC-INSP-006-02** — 巡检进行中防重复触发
  - Given 一次手动巡检正在执行中（service active_state=running 或进程内巡检进行中）
  - When 运维人员再次点击"手动触发巡检"
  - Then 系统应当检测到巡检已在运行，返回"巡检正在执行中，请等待完成后再触发"，HTTP 409 Conflict，Web UI 显示黄色警告 Toast

- **AC-INSP-006-03** — 手动触发不受 timer 状态影响
  - Given networkagent-inspection.timer 处于 disabled + inactive 状态（定时巡检已禁用）
  - When 运维人员点击"手动触发巡检"
  - Then 巡检应当正常执行（手动触发独立于 timer），结果正常持久化至 InspectionRecord（trigger_mode=MANUAL）

- **AC-INSP-006-04** — 手动触发在 systemd 不可用时降级
  - Given 当前环境不支持 systemd（如 Windows 开发环境）
  - When 运维人员点击"手动触发巡检"
  - Then 系统应当绕过 systemctl，直接在当前进程或子进程中执行巡检逻辑（python -m src.inspection_cli run），结果正常持久化，Web UI 提示"巡检已触发（非 systemd 模式）"

- **AC-INSP-006-05** — 手动触发后历史记录即时刷新
  - Given 手动巡检刚刚完成
  - When 运维人员切换到"巡检历史"页面
  - Then 最新一条记录应当出现在列表顶部，trigger_mode 标签显示为"手动"（蓝色），展示该次巡检的设备和异常统计

---

### US-INSP-007: 查看巡检历史记录

- **用户故事**：As a 运维人员, I want to 在 Web UI 巡检历史页面查看所有历史巡检记录（含定时触发和手动触发），支持按触发方式筛选和分页浏览，每条记录展示巡检时间、触发方式、检查设备数、异常数、执行状态和耗时, so that 我能够追踪巡检任务的执行情况、了解设备健康趋势、快速定位异常巡检记录进行深入分析。
- **关联需求**：REQ-INSP-010, REQ-INSP-011
- **优先级**：P0 (Must Have)
- **故事点**：[待开发团队评估]
- **关联 API**：API-INSP-10 (GET /api/inspection/history)

**验收标准：**

- **AC-INSP-007-01** — 历史列表分页展示
  - Given 系统中已产生 25 条巡检历史记录（含 SCHEDULED 和 MANUAL）
  - When 运维人员打开 Web UI "巡检历史"页面
  - Then 页面应当以表格展示第 1 页记录（默认每页 10 条），按 completed_at 倒序排列，每条记录展示：触发方式标签（"定时"灰色 / "手动"蓝色）、检查设备数、异常数（异常 >0 时红色高亮）、状态标签（SUCCESS 绿色 / PARTIAL 黄色 / FAILED 红色）、开始时间、完成时间、耗时（completed_at - started_at）

- **AC-INSP-007-02** — 按触发方式筛选
  - Given 25 条记录中 15 条为 SCHEDULED、10 条为 MANUAL
  - When 运维人员在筛选下拉中选择 trigger_mode="MANUAL"
  - Then 列表应当仅展示 10 条手动触发的记录，总记录数和页码更新

- **AC-INSP-007-03** — 按状态筛选
  - Given 记录包含 SUCCESS、PARTIAL、FAILED 三种状态
  - When 运维人员在筛选下拉中选择 status="FAILED"
  - Then 列表应当仅展示执行失败的记录，帮助运维人员快速定位问题巡检

- **AC-INSP-007-04** — 详情展开查看每台设备结果
  - Given 某次巡检 details JSON 中包含每台纳管设备的诊断摘要
  - When 运维人员点击该记录的"详情"展开按钮
  - Then 展开区域应当以子表格形式展示每台设备的巡检结果：设备名称、诊断命令（如 show interface / show processes cpu）、诊断结果摘要（正常/异常/不可达）、异常详情（如有）

- **AC-INSP-007-05** — 空历史状态
  - Given 系统中从未执行过任何巡检（InspectionRecord 表为空）
  - When 运维人员打开巡检历史页面
  - Then 页面应当显示"暂无巡检记录"的空状态占位图，提示"保存巡检配置并启用定时器后，系统将自动开始记录巡检历史"

- **AC-INSP-007-06** — 巡检历史数据在 Web 重启后保留
  - Given 系统中已有若干巡检历史记录存储于 SQLite
  - When FastAPI Web 服务重启
  - Then 巡检历史页面应当能够正常加载所有历史记录，数据完整不丢失（对比 v0.1.0 APScheduler 内存态重启丢失的问题）

---

### US-INSP-008: systemd 定时触发 CLI 巡检进程

- **用户故事**：As a 系统 (systemd), I want to 按照 networkagent-inspection.timer 中定义的 OnUnitActiveSec 间隔，定时触发 networkagent-inspection.service 执行 `python3.11 -m src.inspection_cli run` 命令，CLI 进程独立于 Web 进程运行并将巡检结果写入 SQLite, so that 巡检调度不依赖 Web 应用进程的存活状态，Web 服务重启不影响巡检计划，巡检进程崩溃不影响 Web 服务，实现真正的进程级隔离和 OS 级持久化调度。
- **关联需求**：REQ-INSP-014, REQ-INSP-015, REQ-INSP-016, REQ-INSP-017, REQ-INSP-NF-001, REQ-INSP-NF-002, REQ-INSP-NF-004
- **优先级**：P0 (Must Have)
- **故事点**：[待开发团队评估]
- **关联 API**：无（systemd 原生调度，非 API 驱动）

**验收标准：**

- **AC-INSP-008-01** — systemd timer 按间隔触发巡检
  - Given networkagent-inspection.timer 已 enabled + active，interval_minutes=5（OnUnitActiveSec=300）
  - When timer 到达触发时间点
  - Then systemd 应当启动 networkagent-inspection.service，执行 ExecStart 命令（python3.11 -m src.inspection_cli run）；CLI 进程对 SQLite 中所有纳管设备执行接口状态 + CPU 检查，将结果写入 InspectionRecord 表（trigger_mode=SCHEDULED），以退出码 0/1/2 退出

- **AC-INSP-008-02** — CLI 进程独立于 Web 进程
  - Given Web 进程（FastAPI）正在运行，systemd timer 触发了一次巡检
  - When 运维人员通过 `systemctl restart` 重启 Web 服务
  - Then 巡检 CLI 进程应当继续执行不受影响（独立 PID、独立进程空间），巡检结果正常写入 SQLite；Web 重启完成后通过 API 可查询到该次巡检记录

- **AC-INSP-008-03** — 巡检失败时的退出码与日志
  - Given CLI 进程在执行过程中因设备全部不可达导致巡检异常
  - When CLI 进程完成执行
  - Then 进程应当以退出码 1（部分异常）或 2（执行失败）退出；systemd 记录 Result=failure；journalctl -u networkagent-inspection.service 输出中包含异常详情；InspectionRecord 中 status=FAILED

- **AC-INSP-008-04** — systemd service 的 on-failure 自动重试
  - Given service Type=oneshot + Restart=on-failure + RestartSec=30
  - When CLI 进程以非 0 退出码退出
  - Then systemd 应当在 30 秒后自动重新启动 service 执行一次（仅重试一次；oneshot + on-failure 特性）；若第二次仍失败则不再重试，等待下一次 timer 触发

- **AC-INSP-008-05** — Persistent=true 补偿执行
  - Given timer 设置了 Persistent=true，系统在计划巡检时间处于关机状态
  - When 系统重新开机
  - Then systemd 应当在开机后立即触发一次巡检（补偿关机期间错过的执行），然后恢复按 OnUnitActiveSec 间隔正常计划执行

- **AC-INSP-008-06** — systemd 日志可追溯
  - Given timer 已触发过多次巡检
  - When 运维人员执行 `journalctl -u networkagent-inspection.service -n 50 --no-pager`
  - Then 应当看到每次巡检的完整日志：开始时间戳、设备列表加载、逐设备诊断输出、异常设备汇总、巡检完成摘要、退出码

- **AC-INSP-008-07** — APScheduler 确认已废弃
  - Given 系统已升级至 v0.2.0
  - When 检查 FastAPI 应用启动日志和 Python 进程的线程列表
  - Then 不应出现 APScheduler BackgroundScheduler 线程，start_scheduler() 不再被调用，apscheduler Python 包已从依赖中移除

---

## 用户故事优先级总览

| 优先级 | 用户故事 | 核心价值 | 关联需求数 | 说明 |
|--------|---------|---------|-----------|------|
| **P0** | US-INSP-001 | Web UI 配置巡检参数并持久化 | 3 | 配置管理入口，所有后续功能的前置条件 |
| **P0** | US-INSP-002 | 配置保存后自动生成 systemd unit 文件 | 5 | systemd 架构核心链路：SQLite → unit file → daemon-reload |
| **P0** | US-INSP-003 | Web UI 查看巡检服务实时状态 | 2 | 可观测性基础，替代 SSH systemctl status |
| **P0** | US-INSP-004 | Web UI 控制巡检服务启动/停止/重启 | 2 | 运维控制核心能力 |
| **P0** | US-INSP-005 | Web UI 启用/禁用巡检定时器 | 2 | 巡检计划控制，维护窗口管理 |
| **P0** | US-INSP-006 | 手动触发一次巡检 | 1 | 日常运维高频操作，保留 v0.1.0 能力 |
| **P0** | US-INSP-007 | 查看巡检历史记录 | 2 | 巡检结果追溯和趋势分析 |
| **P0** | US-INSP-008 | systemd 定时触发 CLI 巡检进程 | 7 | v0.2.0 架构核心：进程隔离 + OS 级持久化调度 |

> 所有 8 条用户故事均为 P0（Must Have），因为每一条都是 v0.2.0 systemd 重构不可或缺的核心能力。

---

## 覆盖矩阵（Coverage Matrix）

| 维度 | 覆盖项 | 对应故事 |
|------|-------|---------|
| **PM 用户需求第1项** | Web UI 巡检配置页面 | US-INSP-001 |
| **PM 用户需求第2项** | systemd timer 管理（自动生成 unit 文件） | US-INSP-002 |
| **PM 用户需求第3项** | 巡检状态查询 | US-INSP-003 |
| **PM 用户需求第4项** | 巡检控制（start/stop/restart/enable/disable） | US-INSP-004, US-INSP-005 |
| **PM 用户需求第5项** | 手动触发巡检 | US-INSP-006 |
| **PM 用户需求第6项** | 巡检历史持久化与查询 | US-INSP-007 |
| **PM 用户需求第7项** | 配置持久化与 systemd 同步 | US-INSP-001, US-INSP-002 |
| **systemd 架构** | systemd timer + service 进程隔离 | US-INSP-008 |
| **systemd 架构** | CLI 入口 python -m src.inspection_cli run | US-INSP-008 |
| **技术约束** | GenPlatform 端口兼容（不碰 80/8000） | US-INSP-008 |
| **技术约束** | Alibaba Cloud ECS + systemd 部署 | US-INSP-002, US-INSP-008 |
| **技术约束** | 后端 FastAPI + SQLAlchemy + SQLite | US-INSP-001, US-INSP-007 |
| **技术约束** | 前端 Vue 3 + Element Plus + Pinia | US-INSP-001, US-INSP-003, US-INSP-004, US-INSP-005, US-INSP-006, US-INSP-007 |
| **迁移** | APScheduler → systemd 废弃 | US-INSP-008 |
| **非功能** | 进程隔离（巡检 vs Web） | US-INSP-008 |
| **非功能** | systemd 不可用时降级 | US-INSP-003, US-INSP-006 |
| **非功能** | systemctl 权限管理（sudoers） | US-INSP-004, US-INSP-005 |
| **非功能** | journald 日志集成 | US-INSP-008 |
| **非功能** | timer 触发精度（AccuracySec） | US-INSP-008 |
| **非功能** | service 故障自动恢复（Restart=on-failure） | US-INSP-008 |

---

## 后端 API 需求映射

| 用户故事 | 需要新增的 API 端点 | 需要增强的现有 API 端点 |
|---------|-------------------|---------------------|
| US-INSP-001 | — | GET /api/inspection/config（返回增加 retry_backoff）; PUT /api/inspection/config（入参增加 retry_backoff，保存后触发 systemd 同步） |
| US-INSP-002 | — | PUT /api/inspection/config（增强：unit 文件生成 + daemon-reload） |
| US-INSP-003 | GET /api/inspection/status | — |
| US-INSP-004 | POST /api/inspection/start; POST /api/inspection/stop; POST /api/inspection/restart | — |
| US-INSP-005 | POST /api/inspection/enable; POST /api/inspection/disable | — |
| US-INSP-006 | — | POST /api/inspection/trigger（增强：可通过 systemctl start 或在进程内子进程执行） |
| US-INSP-007 | — | GET /api/inspection/history（返回增加 status 字段，支持按 status 筛选） |
| US-INSP-008 | —（systemd 原生调用，不通过 API） | — |

---

## 前端组件变更映射

| 用户故事 | Vue 组件 | Pinia Store Action | 变更类型 |
|---------|---------|-------------------|---------|
| US-INSP-001 | InspectionConfigView.vue | fetchConfig(), updateConfig() | **增强**：新增 retry_backoff 字段，替换 polling_interval |
| US-INSP-002 | InspectionConfigView.vue（状态提示） | updateConfig() | **增强**：保存后显示 systemd 同步结果提示 |
| US-INSP-003 | InspectionConfigView.vue（状态面板） | fetchStatus() | **新增**：状态面板 UI + fetchStatus() action + 前端轮询 |
| US-INSP-004 | InspectionConfigView.vue（控制按钮） | startService(), stopService(), restartService() | **新增**：三个控制按钮 + 对应 Pinia actions |
| US-INSP-005 | InspectionConfigView.vue（控制按钮） | enableTimer(), disableTimer() | **新增**：两个控制按钮 + 对应 Pinia actions |
| US-INSP-006 | InspectionConfigView.vue（手动触发按钮） | triggerInspection() | **保留**：已有按钮和 action，增强错误处理和状态反馈 |
| US-INSP-007 | InspectionHistoryView.vue | fetchHistory() | **保留**：基本满足需求，微调新增 status 列展示 |
| US-INSP-008 | — | — | 无前端变更（systemd 层变更） |
