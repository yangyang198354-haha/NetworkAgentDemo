<file_header>
  <author_agent>sub_agent_requirement_analyst</author_agent>
  <timestamp>2026-07-10T00:00:00Z</timestamp>
  <project_name>NetworkAgentDemo</project_name>
  <version>0.1.0</version>
  <input_files>
    <file>requirements/requirements_spec.md</file>
    <file>requirements/user_stories.md</file>
    <file>architecture/architecture_design.md</file>
    <file>src/main.py</file>
  </input_files>
  <phase>PHASE_W01</phase>
  <status>APPROVED</status>
</file_header>

# Web 管理界面需求规格说明书 — NetworkAgentDemo

---

## 执行摘要

### 业务背景
NetworkAgentDemo 已完整实现基于 LangGraph 的网络交换机告警自动修复 Agent（16 个模块、14 节点工作流、6 个 REST API 端点），但现有系统仅通过 FastAPI Swagger 文档或 curl 命令行进行操作，缺乏友好的图形化管理界面。运维人员需要能够在浏览器中完成告警监控、工作流追踪、审批决策、设备管理、巡检配置、知识库维护和系统配置等全部日常操作，无需接触命令行或 Swagger UI。

> 来源：PM 任务说明 — “运维人员需要通过浏览器完成以下所有操作（不再依赖 Swagger/curl）”

### 需求总览
| 类别 | 数量 |
|------|------|
| 功能需求（REQ-WEBUI-FUNC-*） | 28 条 |
| 非功能需求（REQ-WEBUI-NFUNC-*） | 8 条 |
| 外部接口需求（新增 API 端点） | 32 个（新增）/ 6 个（增强现有） |
| [INFERRED] 推断性需求 | 3 条（占比 8.3%，未超 10% 阈值） |
| 用户故事（US-WEBUI-*） | 18 条（见 webui_user_stories.md） |

### 推断性需求列表
| ID | 描述 | 推断依据 |
|----|------|----------|
| REQ-WEBUI-FUNC-022 | Dashboard 图表类型（饼图/柱状图/趋势图） | PM 描述了"告警统计"但未指定图表类型；Web Dashboard 领域标准实践为饼图（分布）、柱状图（对比）、折线图（趋势） |
| REQ-WEBUI-NFUNC-003 | JWT Token 过期时间（24 小时） | PM 确认 JWT 认证方案但未指定过期策略；24 小时为单页应用常用实践 |
| REQ-WEBUI-NFUNC-007 | 设备凭据在 UI 中的掩码显示 | PM 提及"SSH 用户名/密码/端口"配置但未说明显示策略；安全最佳实践要求密码字段掩码 |

---

## 功能需求（Functional Requirements）

### 1. 告警管理（Alert Management）

#### REQ-WEBUI-FUNC-001: 告警列表查看与筛选
| 字段 | 内容 |
|------|------|
| **ID** | REQ-WEBUI-FUNC-001 |
| **描述** | Web 界面应当展示所有告警记录列表（包含 Webhook 被动触发和巡检主动触发的告警），支持按告警类型（MAC_FLAPPING / PORT_DOWN / CPU_HIGH）、严重级别（CRITICAL / MAJOR / MINOR / WARNING）、时间范围进行筛选，支持分页浏览。 |
| **来源引用** | PM 8大功能模块第1项 — “查看所有告警列表（Webhook 触发 + 巡检触发），支持按类型/严重级别/时间筛选” |
| **优先级** | Must Have |
| **备注** | 告警数据需从 SQLite 持久化存储中读取（替代现有 MemorySaver 内存存储） |

**验收标准：**
- **AC-W001-01** — 告警列表默认展示
  - Given 系统中存在多条已处理的告警记录（包含 Webhook 来源和巡检来源）
  - When 运维人员打开 Web 界面的"告警管理"页面
  - Then 系统应当以表格形式展示所有告警，每条记录包含：告警 ID、告警类型、严重级别、设备名称、触发来源（WEBHOOK / INSPECTION）、发生时间、当前状态（PROCESSING / CLOSED / FAILED / REJECTED），默认按时间倒序排列
- **AC-W001-02** — 按告警类型筛选
  - Given 告警列表包含多种类型的告警
  - When 运维人员在筛选条件中选择 alert_type = "PORT_DOWN"
  - Then 列表应当仅显示端口 Down 类型的告警记录，其他类型的告警隐藏
- **AC-W001-03** — 按时间范围筛选
  - Given 告警列表包含最近 7 天的记录
  - When 运维人员选择时间范围为"最近 24 小时"
  - Then 列表应当仅显示过去 24 小时内发生的告警
- **AC-W001-04** — 分页浏览
  - Given 告警记录总数超过单页显示上限（如 20 条）
  - When 运维人员点击"下一页"或输入页码跳转
  - Then 系统应当正确展示对应页的告警记录，并显示总记录数和当前页码

#### REQ-WEBUI-FUNC-002: 告警详情查看
| 字段 | 内容 |
|------|------|
| **ID** | REQ-WEBUI-FUNC-002 |
| **描述** | Web 界面应当支持点击任意告警记录查看其完整处理详情，包括告警原始内容、诊断结果（diag_result）、根因分析（root_cause）、修复方案（fix_plan）、执行日志（exec_log）、验证结果（verify_result）和最终报告（final_report），以时间线形式展示从告警接收到闭环的全流程。 |
| **来源引用** | PM 8大功能模块第1项 — “查看告警处理流程的实时状态（当前处于哪个节点、State 快照）” |
| **优先级** | Must Have |
| **备注** | 详情数据来源于 SQLite 持久化的告警处理记录 + LangGraph State 快照 |

**验收标准：**
- **AC-W002-01** — 告警详情时间线
  - Given 一条已完成全流程处理的 MAC 地址漂移告警（status=CLOSED）
  - When 运维人员在告警列表中点击该告警的"详情"按钮
  - Then 系统应当展示该告警的完整处理时间线，包含每个已执行节点的名称、执行时间、输入/输出摘要，以及最终报告（final_report）
- **AC-W002-02** — 进行中告警的实时状态
  - Given 一条正在处理中的告警（当前处于"人工审批"节点挂起）
  - When 运维人员查看该告警详情
  - Then 系统应当高亮显示当前正在执行的节点（"人工审批"），并展示该节点的 State 快照（含审批信息、修复方案摘要），同时显示已执行节点的历史

#### REQ-WEBUI-FUNC-003: 手动模拟发送告警
| 字段 | 内容 |
|------|------|
| **ID** | REQ-WEBUI-FUNC-003 |
| **描述** | Web 界面应当提供告警模拟表单，运维人员可通过下拉选择告警类型（MAC_FLAPPING / PORT_DOWN / CPU_HIGH）、设备名称、可选参数（接口名称、MAC 地址、CPU 利用率），点击发送按钮即可触发一次模拟告警处理流程（替代现有的 curl POST /alerts/simulate 操作）。 |
| **来源引用** | PM 8大功能模块第1项 — “手动模拟发送告警（替代 POST /alerts/simulate 的 curl 操作），提供表单选择告警类型和设备” |
| **优先级** | Must Have |
| **备注** | 表单中的设备列表应从 SQLite 设备表中动态加载（替代 main.py 硬编码的 default_devices） |

**验收标准：**
- **AC-W003-01** — 告警模拟表单选择
  - Given 系统中已纳管了 Core-SW-01 和 Access-SW-02 两台设备
  - When 运维人员打开"模拟告警"页面，选择 alert_type = "PORT_DOWN"、device_name = "Core-SW-01"、interface = "Gi0/1"
  - Then 设备下拉列表应当动态展示所有已纳管设备，点击"发送"后系统应当接受模拟告警并触发工作流
- **AC-W003-02** — 模拟发送成功反馈
  - Given 运维人员填写完模拟告警表单并点击"发送"
  - When 系统成功接收并触发工作流
  - Then 界面应当显示"模拟告警已发送"的成功提示，并展示新生成的 alert_id，同时在告警列表中可立即查看到该条新告警（status=PROCESSING）
- **AC-W003-03** — 参数校验
  - Given 运维人员在模拟告警表单中未选择设备名称
  - When 点击"发送"按钮
  - Then 系统应当在前端阻止提交并提示"请选择目标设备"，不发送无效请求到后端

#### REQ-WEBUI-FUNC-004: 告警处理流程实时状态追踪
| 字段 | 内容 |
|------|------|
| **ID** | REQ-WEBUI-FUNC-004 |
| **描述** | Web 界面应当在告警详情页中实时展示当前处理流程所处的 LangGraph 节点位置，通过前端轮询机制（每 3-5 秒）获取最新工作流状态，并以进度指示器标识已完成节点、当前节点和未执行节点。 |
| **来源引用** | PM 8大功能模块第1项 — “查看告警处理流程的实时状态（当前处于哪个节点、State 快照）” + PM 技术决策第5项 — “前端轮询（每 3-5 秒调用状态 API）” |
| **优先级** | Must Have |
| **备注** | 轮询间隔默认 3 秒，应在系统配置中可调整 |

**验收标准：**
- **AC-W004-01** — 节点进度指示
  - Given 一条告警处理流程已执行到"根因分析+知识库检索"节点
  - When 运维人员查看该告警的详情页面
  - Then 页面应当以进度条或步骤条形式展示 14 个节点，已完成的节点标记为"已完成"（绿色），当前节点标记为"进行中"（蓝色动画），未执行节点标记为"等待中"（灰色）
- **AC-W004-02** — 状态自动刷新
  - Given 告警详情页面已打开，当前工作流处于"人工审批"挂起状态
  - When 运维人员在另一个窗口提交审批决定（APPROVED），工作流恢复执行
  - Then 告警详情页面应当在下一个轮询周期（3-5 秒内）自动更新节点进度，将"人工审批"节点标记为已完成，并显示后续节点开始执行

---

### 2. 工作流可视化（Workflow Visualization）

#### REQ-WEBUI-FUNC-005: LangGraph 节点拓扑可视化
| 字段 | 内容 |
|------|------|
| **ID** | REQ-WEBUI-FUNC-005 |
| **描述** | Web 界面应当以图形化方式展示 LangGraph 的 14 节点状态流转拓扑结构，节点之间用有向连线表示流转方向，条件分支边（如风险评估后的审批/跳过分支、验证成功/失败分支）以不同颜色或标签区分。 |
| **来源引用** | PM 8大功能模块第2项 — “可视化展示 LangGraph 14 节点的状态流转图（节点拓扑 + 当前激活节点高亮）” |
| **优先级** | Should Have |
| **备注** | 拓扑结构数据从后端 API GET /api/workflow/graph 获取；前端渲染使用轻量级图形库 |

**验收标准：**
- **AC-W005-01** — 静态拓扑图展示
  - Given 系统已编译 LangGraph StateGraph（14 节点 + 条件边）
  - When 运维人员打开"工作流可视化"页面
  - Then 页面应当以有向图形式展示全部 14 个节点，节点名称清晰可读，节点间连线标注流转条件（如"有效性校验通过"、"校验失败-直接关闭"、"need_human_approval=true"、"验证失败-触发回滚"等）
- **AC-W005-02** — 当前激活节点高亮
  - Given 系统中存在一条正在处理的告警（当前位于"执行修复"节点）
  - When 运维人员在该告警的详情页切换到"工作流视图"标签
  - Then 拓扑图中"执行修复"节点应当以高亮颜色（如橙色）闪烁标识，已执行节点标为绿色，未执行节点标为灰色
- **AC-W005-03** — 节点详情悬浮提示
  - Given 工作流拓扑图已展示
  - When 运维人员将鼠标悬停在任意节点上
  - Then 系统应当显示该节点的 Tooltip 信息：节点名称、描述、典型执行耗时

#### REQ-WEBUI-FUNC-006: 节点 State 快照查看
| 字段 | 内容 |
|------|------|
| **ID** | REQ-WEBUI-FUNC-006 |
| **描述** | Web 界面应当支持点击拓扑图中的任意节点（或从告警详情时间线中选择节点），查看该节点执行时的输入 State 快照和输出 State 快照（NetworkAgentState 各字段的 JSON 视图），便于运维人员深入理解每个节点的数据处理逻辑。 |
| **来源引用** | PM 8大功能模块第2项 — “查看每个节点的输入/输出 State 快照” + “支持 drill-down 查看节点详情” |
| **优先级** | Should Have |
| **备注** | State 快照数据来源于 LangGraph checkpoint 机制；对于未执行节点，仅显示字段定义（Schema），不显示实际值 |

**验收标准：**
- **AC-W006-01** — 已执行节点 State 查看
  - Given 一条告警处理流程已完成"采集诊断信息"节点
  - When 运维人员在工作流拓扑图中点击"采集诊断信息"节点
  - Then 系统应当以 JSON 格式展示该节点的输入 State（含 alert_id、alert_type、device_info）和输出 State（新增 diag_result 字段及其值），字段变更部分高亮显示（diff 视图）
- **AC-W006-02** — 未执行节点 Schema 查看
  - Given 工作流尚未到达"执行修复"节点
  - When 运维人员点击"执行修复"节点
  - Then 系统应当显示该节点的预期输入 Schema（NetworkAgentState 完整字段定义），并标注"当前尚未执行"

---

### 3. 人工审批操作（Manual Approval Operations）

#### REQ-WEBUI-FUNC-007: 待审批列表展示
| 字段 | 内容 |
|------|------|
| **ID** | REQ-WEBUI-FUNC-007 |
| **描述** | Web 界面应当展示所有处于 LangGraph Interrupt 挂起状态的待审批项列表，每条记录包含：告警 ID、告警类型、设备名称、风险等级、挂起时间、修复方案摘要（操作类型、影响范围），支持按挂起时间排序。此功能替代现有的 curl GET /approvals/pending 操作。 |
| **来源引用** | PM 8大功能模块第3项 — “待审批列表（替代 GET /approvals/pending 的 curl 操作）” |
| **优先级** | Must Have |
| **备注** | 待审批项列表应在首页或独立 Dashboard 中醒目展示（顶部 Badge 数量提示） |

**验收标准：**
- **AC-W007-01** — 待审批列表展示
  - Given 系统中有 2 条告警处理流程处于"人工审批"挂起状态（含 checkpoint_id）
  - When 运维人员打开"待审批"页面
  - Then 页面应当以列表形式展示所有待审批项，每条包含：alert_id、告警类型（如 PORT_DOWN）、设备名称、风险等级（HIGH/MEDIUM/LOW）、挂起时间（距当前的时长）、修复方案操作摘要
- **AC-W007-02** — 空状态提示
  - Given 当前没有任何待审批项
  - When 运维人员打开"待审批"页面
  - Then 页面应当显示"当前没有待审批项"的空状态提示，而非空白页面
- **AC-W007-03** — 导航栏待审批数量徽标
  - Given 系统中有 3 条待审批项
  - When 运维人员浏览任意页面
  - Then 导航栏的"审批"菜单项右上角应当显示红色徽标数字"3"

#### REQ-WEBUI-FUNC-008: 审批决策操作
| 字段 | 内容 |
|------|------|
| **ID** | REQ-WEBUI-FUNC-008 |
| **描述** | Web 界面应当支持运维人员点击待审批项进入审批详情页，查看告警完整信息和修复方案详细内容（根因分析、修复步骤、影响范围、风险等级），然后做出"批准"或"拒绝"的决策，并可填写审批备注。此功能替代现有的 curl POST /approvals/{id}/decide 操作。 |
| **来源引用** | PM 8大功能模块第3项 — “审批操作：查看修复方案详情后'批准'或'拒绝'（替代 POST /approvals/{id}/decide 的 curl 操作）” |
| **优先级** | Must Have |
| **备注** | 审批决策通过后端调用 LangGraph resume_workflow 恢复状态机执行 |

**验收标准：**
- **AC-W008-01** — 审批详情查看
  - Given 一条 PORT_DOWN 告警的处理流程在"人工审批"节点挂起，修复方案建议执行 `no shutdown` 操作
  - When 运维人员点击该待审批项进入详情页
  - Then 页面应当完整展示：告警描述（原始 alert_content）、诊断结果（diag_result JSON）、根因分析（root_cause 文本）、修复方案详细步骤（fix_plan）、风险等级（need_human_approval 标记为 true 的原因）、影响范围评估
- **AC-W008-02** — 批准操作
  - Given 运维人员查看修复方案后认为合理可行
  - When 运维人员点击"批准"按钮，并可选择填写审批备注（如"方案合理，允许执行"）
  - Then 系统应当提交 approval_status=APPROVED，界面显示"审批已提交"成功提示，状态机从"人工审批"节点恢复继续执行，该条审批项从待审批列表中移除
- **AC-W008-03** — 拒绝操作
  - Given 运维人员认为修复方案风险不可接受
  - When 运维人员点击"拒绝"按钮，并填写拒绝原因（如"该端口为关键业务端口，需人工现场确认后再处理"）
  - Then 系统应当提交 approval_status=REJECTED，界面显示"已拒绝"提示，告警状态更新为 REJECTED，该条审批项从待审批列表中移除
- **AC-W008-04** — 操作确认防误触
  - Given 运维人员点击了"批准"或"拒绝"按钮
  - When 系统尚未提交审批决定
  - Then 前端应当弹出二次确认对话框（"确认批准此修复方案？该操作将立即下发配置到设备 Core-SW-01"），防止误操作

#### REQ-WEBUI-FUNC-009: 审批历史记录
| 字段 | 内容 |
|------|------|
| **ID** | REQ-WEBUI-FUNC-009 |
| **描述** | Web 界面应当提供审批历史记录页面，展示所有已处理的审批决策（含已批准和已拒绝），每条记录包含：告警 ID、审批时间、审批人、审批决定（APPROVED/REJECTED）、审批备注、关联的修复方案摘要。支持按时间范围和审批决定筛选。 |
| **来源引用** | PM 8大功能模块第3项 — “审批历史记录（所有已处理的审批，含审批人、时间、决定、依据）” |
| **优先级** | Should Have |
| **备注** | 审批历史数据持久化至 SQLite，解决现有 MAJ-001 已知问题（审批历史内存存储、重启丢失） |

**验收标准：**
- **AC-W009-01** — 审批历史列表
  - Given 系统中已有 10 条已处理的审批记录（含批准和拒绝）
  - When 运维人员打开"审批历史"页面
  - Then 页面应当以列表形式展示所有历史审批，按审批时间倒序排列，每条包含：alert_id、告警类型、设备名称、审批时间、审批决定（批准/拒绝标签颜色区分）、审批备注
- **AC-W009-02** — 审批历史筛选
  - Given 审批历史包含批准和拒绝两种记录
  - When 运维人员筛选"仅显示已拒绝"
  - Then 列表应当仅展示审批决定为 REJECTED 的记录
- **AC-W009-03** — 审批历史持久化
  - Given 系统在运行期间处理了若干条审批
  - When 系统重启（FastAPI 进程重启）
  - Then 审批历史记录应当完整保留（从 SQLite 加载），不丢失任何记录（解决 MAJ-001 已知问题）

---

### 4. 设备管理（Device Management）

#### REQ-WEBUI-FUNC-010: 纳管设备 CRUD
| 字段 | 内容 |
|------|------|
| **ID** | REQ-WEBUI-FUNC-010 |
| **描述** | Web 界面应当提供纳管网络设备的完整 CRUD（创建、查看、编辑、删除）功能，支持管理设备的名称、IP 地址、设备型号、所属分组等基本信息。此功能替代 main.py 中硬编码的 default_devices 列表。 |
| **来源引用** | PM 8大功能模块第4项 — “纳管设备列表的 CRUD（替代 main.py 中硬编码的 default_devices）” |
| **优先级** | Must Have |
| **备注** | 设备信息持久化至 SQLite；删除设备前需检查是否有进行中的告警关联该设备 |

**验收标准：**
- **AC-W010-01** — 设备列表查看
  - Given 系统中已纳管 Core-SW-01 和 Access-SW-02 两台设备
  - When 运维人员打开"设备管理"页面
  - Then 页面应当以表格展示所有设备，列包含：设备名称、IP 地址、型号、状态（ONLINE/OFFLINE/UNKNOWN）、最近诊断时间、操作按钮（编辑/删除）
- **AC-W010-02** — 新增设备
  - Given 运维人员需要纳管一台新交换机
  - When 运维人员点击"添加设备"，填写设备名称="Dist-SW-03"、IP="192.168.1.3"、型号="TP-Link T2600G-28TS"
  - Then 系统应当保存设备信息，设备列表刷新后显示新设备，模拟告警表单中的设备下拉列表同步更新
- **AC-W010-03** — 编辑设备信息
  - Given 某设备 IP 地址发生变更
  - When 运维人员点击设备行的"编辑"按钮，修改 IP 地址并保存
  - Then 系统应当更新设备信息，后续工作流使用新 IP 地址连接该设备
- **AC-W010-04** — 删除设备安全检查
  - Given 某设备当前有一条正在处理中的告警关联
  - When 运维人员尝试删除该设备
  - Then 系统应当提示"该设备有 1 条处理中的告警，无法删除"，拒绝删除操作
- **AC-W010-05** — 无关联告警时正常删除
  - Given 某设备无任何进行中的告警关联
  - When 运维人员点击删除并确认
  - Then 系统应当删除该设备记录，设备列表刷新

#### REQ-WEBUI-FUNC-011: 设备凭据配置
| 字段 | 内容 |
|------|------|
| **ID** | REQ-WEBUI-FUNC-011 |
| **描述** | Web 界面应当支持为每台纳管设备配置 SSH 连接凭据，包括 SSH 用户名、密码和端口号。密码字段在输入和展示时应做掩码处理，存储时加密（AES-256）。此功能替代 config.yaml 中 devices 段的手动编辑。 |
| **来源引用** | PM 8大功能模块第4项 — “设备凭据配置（SSH 用户名/密码/端口，替代 config.yaml 中 devices 段的手动编辑）” |
| **优先级** | Must Have |
| **备注** | 凭据加密存储至 SQLite；Demo 阶段使用平台内置密钥加密 |

**验收标准：**
- **AC-W011-01** — 凭据配置表单
  - Given 运维人员需要配置设备 Core-SW-01 的 SSH 凭据
  - When 运维人员在设备管理页面点击 Core-SW-01 的"凭据配置"按钮，输入 SSH 用户名="admin"、密码="****"、端口="22"，保存
  - Then 系统应当加密存储凭据，界面显示凭据已配置（密码字段显示为 ****），后续工作流使用该凭据建立 SSH 连接
- **AC-W011-02** — 密码字段掩码显示
  - Given 设备凭据已配置
  - When 运维人员打开凭据配置页面查看已有凭据
  - Then 密码字段应当以圆点（****）掩码显示 [INFERRED — 安全最佳实践，待 PM 确认是否需提供"显示密码"切换按钮]
- **AC-W011-03** — 未配置凭据的设备触发诊断时提示
  - Given 某设备未配置 SSH 凭据
  - When 系统尝试对该设备执行诊断操作
  - Then 系统应当在界面提示"设备 {name} 未配置 SSH 凭据，请先配置后再操作"

#### REQ-WEBUI-FUNC-012: 设备诊断结果查看
| 字段 | 内容 |
|------|------|
| **ID** | REQ-WEBUI-FUNC-012 |
| **描述** | Web 界面应当支持在设备详情页查看该设备最近一次诊断操作的原始输出结果（如 show interface、show mac address-table、show processes cpu 命令的 Mock 输出），以代码块形式展示，便于运维人员验证设备状态。 |
| **来源引用** | PM 8大功能模块第4项 — “设备诊断结果查看（最近一次诊断的原始输出）” |
| **优先级** | Should Have |
| **备注** | 诊断结果关联到具体告警的 diag_result 字段 |

**验收标准：**
- **AC-W012-01** — 最近诊断结果查看
  - Given 设备 Core-SW-01 最近因 PORT_DOWN 告警执行过一次诊断（show interface 命令）
  - When 运维人员在设备管理页面点击 Core-SW-01 的"诊断记录"
  - Then 系统应当以代码块格式展示最近一次诊断命令的原始输出文本、执行时间和关联告警 ID
- **AC-W012-02** — 无诊断记录时的提示
  - Given 某设备从未触发过诊断操作
  - When 运维人员查看该设备的诊断结果
  - Then 页面应当显示"该设备暂无诊断记录"

---

### 5. 巡检配置（Inspection Configuration）

#### REQ-WEBUI-FUNC-013: 巡检间隔配置
| 字段 | 内容 |
|------|------|
| **ID** | REQ-WEBUI-FUNC-013 |
| **描述** | Web 界面应当支持可视化配置主动巡检的触发间隔（分钟数），运维人员可在界面上修改间隔值并立即生效（更新 APScheduler 的 interval 参数）。此功能替代 config.yaml 中 inspection.interval_minutes 的手动编辑。 |
| **来源引用** | PM 8大功能模块第5项 — “巡检间隔时间配置（分钟数，替代 config.yaml 手动编辑）” |
| **优先级** | Should Have |
| **备注** | 修改后需重启调度器或动态更新 APScheduler 的 job interval |

**验收标准：**
- **AC-W013-01** — 巡检间隔查看与修改
  - Given 当前巡检间隔设置为 5 分钟
  - When 运维人员打开"巡检配置"页面，将间隔修改为 10 分钟并保存
  - Then 系统应当更新配置（写入 SQLite 配置表），APScheduler 的下一次巡检触发时间间隔变为 10 分钟，页面上显示"配置已更新，当前巡检间隔：10 分钟"
- **AC-W013-02** — 输入校验
  - Given 运维人员在巡检间隔输入框中输入 0 或负数
  - When 点击保存
  - Then 系统应当阻止提交并提示"巡检间隔必须为正整数（分钟）"

#### REQ-WEBUI-FUNC-014: 手动触发巡检
| 字段 | 内容 |
|------|------|
| **ID** | REQ-WEBUI-FUNC-014 |
| **描述** | Web 界面应当提供"手动触发巡检"按钮，运维人员点击后可立即对所有纳管设备执行一次完整的主动巡检（执行诊断命令、检测异常），巡检结果即时反馈在界面上。此功能解决现有系统"只能等定时器触发"的限制。 |
| **来源引用** | PM 8大功能模块第5项 — “手动触发一次巡检（替代目前只能等定时器触发）” |
| **优先级** | Must Have |
| **备注** | 手动触发的巡检与定时巡检使用相同的 InspectionScheduler 逻辑，但即时执行不受 interval 约束 |

**验收标准：**
- **AC-W014-01** — 手动触发巡检
  - Given 系统中已纳管 2 台设备，当前无定时巡检在运行
  - When 运维人员点击"手动触发巡检"按钮
  - Then 系统应当立即对所有纳管设备执行诊断命令，界面显示"巡检已触发"提示和进度（检查中...），巡检完成后展示结果摘要（检查设备数=2、发现异常数=X）
- **AC-W014-02** — 巡检进行中防重复触发
  - Given 一次手动巡检正在执行中
  - When 运维人员再次点击"手动触发巡检"
  - Then 系统应当提示"巡检任务正在执行中，请等待完成后再触发"，阻止重复触发
- **AC-W014-03** — 巡检结果自动生成告警
  - Given 手动巡检中检测到 Core-SW-01 的 Gi0/1 端口状态为 Down
  - When 巡检诊断完成
  - Then 系统应当自动生成一条 source=INSPECTION 的 PORT_DOWN 告警，进入 LangGraph 标准处理流程，同时在巡检结果摘要中展示

#### REQ-WEBUI-FUNC-015: 巡检历史记录
| 字段 | 内容 |
|------|------|
| **ID** | REQ-WEBUI-FUNC-015 |
| **描述** | Web 界面应当提供巡检历史记录页面，展示每次巡检（含定时触发和手动触发）的执行记录，每条记录包含：巡检时间、触发方式（SCHEDULED / MANUAL）、检查设备数、发现异常数、异常设备列表、处置结果摘要。支持按时间范围和触发方式筛选。 |
| **来源引用** | PM 8大功能模块第5项 — “巡检历史记录（每次巡检的时间、检查设备数、发现异常数、处置结果）” |
| **优先级** | Should Have |
| **备注** | 巡检历史持久化至 SQLite |

**验收标准：**
- **AC-W015-01** — 巡检历史列表
  - Given 系统运行期间已执行过 5 次定时巡检和 2 次手动巡检
  - When 运维人员打开"巡检历史"页面
  - Then 页面应当以列表形式展示所有巡检记录，按时间倒序排列，每条包含：巡检时间、触发方式标签（定时/手动）、检查设备数、发现异常数、处置结果（已修复数/待处理数）
- **AC-W015-02** — 巡检详情展开
  - Given 某次巡检发现了 2 台设备异常
  - When 运维人员点击该巡检记录的"详情"展开
  - Then 系统应当展示该次巡检的详细结果：每台设备的名称、诊断命令、诊断结果摘要、是否触发告警、生成的 alert_id

---

### 6. 知识库管理（Knowledge Base Management）

#### REQ-WEBUI-FUNC-016: 知识文档 CRUD
| 字段 | 内容 |
|------|------|
| **ID** | REQ-WEBUI-FUNC-016 |
| **描述** | Web 界面应当提供知识文档（故障案例和处置预案）的完整 CRUD 功能，运维人员可创建、编辑、删除知识文档，每条文档包含：标题、告警类型分类（MAC_FLAPPING / PORT_DOWN / CPU_HIGH）、文档内容（Markdown 格式）。此功能替代 seed_knowledge.json 文件的手动编辑。 |
| **来源引用** | PM 8大功能模块第6项 — “知识文档的 CRUD（替代 seed_knowledge.json 的手动编辑），支持按告警类型分类” |
| **优先级** | Should Have |
| **备注** | 文档创建/更新后需触发 Chroma 向量索引的重新 embedding；知识文档持久化至 SQLite（元数据+内容） |

**验收标准：**
- **AC-W016-01** — 知识文档列表
  - Given 系统中已有 5 条知识文档（覆盖 3 种告警类型）
  - When 运维人员打开"知识库管理"页面的"文档"标签
  - Then 页面应当展示所有知识文档列表，支持按告警类型筛选，每条显示：标题、告警类型标签、创建时间、更新时间
- **AC-W016-02** — 新增知识文档
  - Given 运维人员需要添加一条关于"端口 Err-Disable 自动恢复"的故障案例
  - When 运维人员点击"新建文档"，填写标题、选择告警类型="PORT_DOWN"、输入 Markdown 内容并保存
  - Then 系统应当保存文档（写入 SQLite），同时触发 Chroma 对该文档重新 embedding 并更新向量索引，RAG 检索可立即检索到新文档
- **AC-W016-03** — 编辑知识文档
  - Given 某条知识文档内容需要更新
  - When 运维人员点击"编辑"，修改内容后保存
  - Then 系统应当更新 SQLite 记录和 Chroma 向量索引
- **AC-W016-04** — 删除知识文档
  - Given 某条知识文档已过时
  - When 运维人员点击"删除"并确认
  - Then 系统应当从 SQLite 和 Chroma 中删除该文档，RAG 检索不再返回该文档

#### REQ-WEBUI-FUNC-017: 命令模板 CRUD
| 字段 | 内容 |
|------|------|
| **ID** | REQ-WEBUI-FUNC-017 |
| **描述** | Web 界面应当提供命令模板的完整 CRUD 功能，运维人员可创建、编辑、删除交换机命令模板（YAML 格式），每条模板包含：模板名称、适用告警类型、命令模板内容（含参数占位符 {{param}}）、参数列表定义。此功能替代 resources/templates/ 目录下 YAML 文件的手动编辑。 |
| **来源引用** | PM 8大功能模块第6项 — “命令模板的 CRUD（替代 resources/templates/ 目录下手动编辑 YAML 文件）” |
| **优先级** | Should Have |
| **备注** | 模板创建/更新后需同步更新 TemplateEngine 的模板缓存（内存重载）和 Chroma 索引（用于 RAG 匹配） |

**验收标准：**
- **AC-W017-01** — 命令模板列表
  - Given 系统中已有 6 个预置命令模板（端口启用、端口禁用、MAC 端口安全等）
  - When 运维人员打开"知识库管理"页面的"模板"标签
  - Then 页面应当展示所有模板列表，每条显示：模板名称、适用告警类型、参数数量、更新时间
- **AC-W017-02** — 新增命令模板
  - Given 运维人员需要添加一个新的 VLAN 配置模板
  - When 运维人员点击"新建模板"，以 YAML 编辑模式填写模板名称="VLAN 创建"、告警类型="PORT_DOWN"、命令模板内容（含 {{vlan_id}} 和 {{vlan_name}} 参数占位符）、参数定义列表，保存
  - Then 系统应当保存模板到 SQLite，更新 TemplateEngine 缓存和 Chroma 索引
- **AC-W017-03** — 模板语法校验
  - Given 运维人员在编辑命令模板时，YAML 格式存在语法错误（如缩进不一致）
  - When 点击"保存"
  - Then 系统应当在前端/后端进行 YAML 格式校验，提示具体的语法错误位置，阻止保存

#### REQ-WEBUI-FUNC-018: 知识库检索测试界面
| 字段 | 内容 |
|------|------|
| **ID** | REQ-WEBUI-FUNC-018 |
| **描述** | Web 界面应当提供知识库检索测试工具，运维人员可输入测试查询文本，选择告警类型过滤，系统执行 RAG 检索并返回匹配结果列表，每条结果显示：文档标题、匹配内容摘要、相似度分数。此功能便于运维人员验证知识库的检索质量和覆盖度。 |
| **来源引用** | PM 8大功能模块第6项 — “知识库检索测试界面（输入查询文本，查看 RAG 检索返回的匹配结果和相似度分数）” |
| **优先级** | Could Have |
| **备注** | 该功能属于调试/验证工具，Demo 阶段提供但非核心路径 |

**验收标准：**
- **AC-W018-01** — RAG 检索测试
  - Given 知识库中包含 MAC 地址漂移的故障案例文档
  - When 运维人员在检索测试界面输入查询文本="交换机 MAC 地址在多个端口间漂移导致环路"，选择告警类型="MAC_FLAPPING"
  - Then 系统应当执行 RAG 检索，返回 Top-K 匹配结果，每条结果包含：文档标题、内容摘要（高亮匹配关键词）、相似度分数（如 0.85），按分数降序排列
- **AC-W018-02** — 无匹配结果的处理
  - Given 运维人员输入的知识库中不存在的查询文本
  - When RAG 检索返回的相似度分数全部低于阈值（0.6）
  - Then 系统应当显示"未找到相似文档（所有结果相似度 < 0.6），建议扩充知识库"的提示

---

### 7. 系统配置（System Configuration）

#### REQ-WEBUI-FUNC-019: 全局配置可视化编辑
| 字段 | 内容 |
|------|------|
| **ID** | REQ-WEBUI-FUNC-019 |
| **描述** | Web 界面应当提供全局系统配置的可视化编辑表单，覆盖以下配置项：巡检间隔（分钟）、诊断命令超时时间（秒）、命令执行重试次数、RAG 相似度阈值、前端轮询间隔（秒）。配置修改后立即生效或提示需要重启生效。此功能替代 config.yaml 文件的手动编辑。 |
| **来源引用** | PM 8大功能模块第7项 — “全局配置的可视化编辑（替代 config.yaml 的手动编辑），包括：巡检间隔、诊断超时、重试次数、RAG 相似度阈值等” |
| **优先级** | Must Have |
| **备注** | 配置持久化至 SQLite 配置表；部分配置修改需重启 APScheduler 或重载 RAGService |

**验收标准：**
- **AC-W019-01** — 配置表单展示
  - Given 系统当前配置为：巡检间隔=5分钟、诊断超时=30秒、重试次数=3、RAG相似度阈值=0.6、轮询间隔=3秒
  - When 运维人员打开"系统配置"页面
  - Then 页面应当以表单形式展示所有可配置项及其当前值，每项附带说明文字
- **AC-W019-02** — 配置修改与生效反馈
  - Given 运维人员将诊断超时从 30 秒修改为 60 秒
  - When 点击"保存配置"
  - Then 系统应当更新 SQLite 配置表，并明确提示"诊断超时已更新为 60 秒，新配置立即生效"（或"需要重启服务后生效"），确保运维人员了解生效时机
- **AC-W019-03** — 配置值合法性校验
  - Given 运维人员在重试次数输入框中输入 -1
  - When 点击保存
  - Then 系统应当阻止保存并提示"重试次数必须为非负整数"

#### REQ-WEBUI-FUNC-020: LLM API Key 安全配置
| 字段 | 内容 |
|------|------|
| **ID** | REQ-WEBUI-FUNC-020 |
| **描述** | Web 界面应当提供 DeepSeek API Key 的安全配置功能，支持输入、修改和删除 API Key。API Key 在界面上掩码显示，传输使用 HTTPS（生产环境），存储使用 AES-256 加密，不允许明文展示完整 Key。 |
| **来源引用** | PM 8大功能模块第7项 — “LLM API Key 配置（DeepSeek API Key 的安全输入和存储）” |
| **优先级** | Must Have |
| **备注** | 与 REQ-WEBUI-NFUNC-005 关联 — API Key 加密存储要求 |

**验收标准：**
- **AC-W020-01** — API Key 安全输入
  - Given 运维人员首次配置 DeepSeek API Key
  - When 运维人员在系统配置页面输入 API Key="sk-xxxxxxxxxxxxxxxx"并保存
  - Then 输入框中字符以掩码（****）显示（不显示明文），系统将 Key 加密后存储至 SQLite，保存成功提示"API Key 已安全存储"
- **AC-W020-02** — API Key 掩码查看与修改
  - Given API Key 已配置
  - When 运维人员再次打开 API Key 配置项
  - Then 输入框中显示占位符（如 sk-****...****xxxx 前4后4可识别），不显示完整 Key；运维人员可输入新 Key 覆盖旧值
- **AC-W020-03** — LLM 连接测试
  - Given 运维人员配置了新的 API Key
  - When 运维人员点击"测试连接"按钮
  - Then 系统应当使用该 Key 调用 DeepSeek API 进行连接测试，返回测试结果（"连接成功"或"连接失败：{错误原因}"），不消耗实际推理 token

#### REQ-WEBUI-FUNC-021: 日志查看
| 字段 | 内容 |
|------|------|
| **ID** | REQ-WEBUI-FUNC-021 |
| **描述** | Web 界面应当提供运维日志和审计日志的在线查看功能，支持按日志级别（INFO/WARNING/ERROR）、时间范围和关键词进行搜索过滤，以分页列表展示日志条目。此功能避免运维人员需要直接登录服务器查看日志文件。 |
| **来源引用** | PM 8大功能模块第7项 — “日志查看（Web 界面读取和搜索审计日志文件）” |
| **优先级** | Should Have |
| **备注** | Demo 阶段读取文件日志（operations.log + audit.log）；生产化后可升级为 SQLite 日志存储 |

**验收标准：**
- **AC-W021-01** — 日志列表查看
  - Given 系统运行期间产生了若干条操作日志
  - When 运维人员打开"系统日志"页面
  - Then 页面应当以列表形式展示日志条目，按时间倒序排列，每条显示：时间戳、级别（颜色标签区分）、模块名称、日志内容摘要
- **AC-W021-02** — 按级别筛选
  - Given 日志中包含 INFO、WARNING、ERROR 三种级别
  - When 运维人员筛选"仅显示 ERROR"
  - Then 列表应当仅展示 ERROR 级别的日志条目
- **AC-W021-03** — 关键词搜索
  - Given 运维人员需要查找与设备 Core-SW-01 相关的所有日志
  - When 运维人员在搜索框中输入"Core-SW-01"并搜索
  - Then 系统应当返回日志内容中包含"Core-SW-01"的所有条目，匹配关键词高亮显示
- **AC-W021-04** — 大日志文件性能
  - Given 日志文件较大（> 10MB）
  - When 运维人员浏览日志
  - Then 系统应当采用分页加载（每次加载 100 条），避免前端卡顿或超时

---

### 8. Dashboard 仪表盘

#### REQ-WEBUI-FUNC-022: 告警统计图表
| 字段 | 内容 |
|------|------|
| **ID** | REQ-WEBUI-FUNC-022 |
| **描述** | Web 界面首页 Dashboard 应当展示告警数据的统计图表，包括：按告警类型分布（饼图或环形图）、按严重级别分布（柱状图）、按时间段趋势（折线图，展示最近 7 天/30 天告警数量变化）。图表支持时间范围切换。 |
| **来源引用** | PM 8大功能模块第8项 — “告警统计（按类型分布饼图/按严重级别柱状图/按时间段趋势图）” |
| **优先级** | Should Have |
| **备注** | [INFERRED — requires PM confirmation] 图表类型（饼图/柱状图/折线图）为 Web Dashboard 领域标准实践，PM 原文仅描述统计维度未指定具体图表形式；若 PM 有特定图表需求请确认 |

**验收标准：**
- **AC-W022-01** — 告警类型分布饼图
  - Given 系统中有 MAC_FLAPPING 告警 10 条、PORT_DOWN 告警 25 条、CPU_HIGH 告警 5 条
  - When 运维人员打开 Dashboard 页面
  - Then 页面应当以饼图展示各告警类型的数量占比，每块标注类型名称、数量和百分比
- **AC-W022-02** — 告警趋势折线图
  - Given 最近 7 天每天都有不同数量的告警
  - When 运维人员将统计时间范围切换为"最近 7 天"
  - Then 折线图应当以天为粒度展示 7 天的告警数量变化趋势，X 轴为日期、Y 轴为告警数量
- **AC-W022-03** — 空数据展示
  - Given 系统刚启动，尚无任何告警记录
  - When 运维人员打开 Dashboard
  - Then 统计图表区域应当显示"暂无告警数据"的空状态占位图，而非空白图表

#### REQ-WEBUI-FUNC-023: 修复成功率统计
| 字段 | 内容 |
|------|------|
| **ID** | REQ-WEBUI-FUNC-023 |
| **描述** | Web 界面 Dashboard 应当展示修复成功率统计，以环形图或百分比数字展示：修复成功（status=CLOSED）、修复失败（status=FAILED）、审批拒绝（status=REJECTED）三类结果的比例，并显示总处理告警数。 |
| **来源引用** | PM 8大功能模块第8项 — “修复成功率（成功/失败/审批拒绝的比例）” |
| **优先级** | Should Have |
| **备注** | 统计基于 SQLite 中持久化的告警最终状态 |

**验收标准：**
- **AC-W023-01** — 修复成功率环形图
  - Given 系统中总计 40 条告警：30 条成功修复（CLOSED）、5 条修复失败（FAILED）、5 条审批拒绝（REJECTED）
  - When 运维人员查看 Dashboard 的"修复成功率"区域
  - Then 环形图应当展示：成功 75%（绿色）、失败 12.5%（红色）、拒绝 12.5%（橙色），中心显示总处理数=40
- **AC-W023-02** — 可点击下钻
  - Given 修复成功率环形图中"失败"扇区显示 5 条
  - When 运维人员点击"失败"扇区
  - Then 系统应当跳转至告警列表页面，自动筛选 status=FAILED，展示这 5 条失败告警的详情

#### REQ-WEBUI-FUNC-024: 系统健康状态面板
| 字段 | 内容 |
|------|------|
| **ID** | REQ-WEBUI-FUNC-024 |
| **描述** | Web 界面 Dashboard 应当展示系统各组件的实时健康状态，包括：LangGraph 引擎状态（是否正常编译）、RAG 服务状态（Chroma 是否可用、知识库文档数）、巡检调度器状态（是否正在运行）、LLM 连接状态（DeepSeek API 是否可达）。每个组件以绿/黄/红状态指示灯标识。 |
| **来源引用** | PM 8大功能模块第8项 — “系统健康状态（各组件状态：LangGraph 引擎、RAG 服务、巡检调度器、LLM 连接）” |
| **优先级** | Must Have |
| **备注** | 健康数据通过轮询 GET /api/dashboard/health 获取（复用现有 /health 端点的扩展版本） |

**验收标准：**
- **AC-W024-01** — 组件状态指示灯
  - Given 所有系统组件运行正常（LangGraph 已编译、Chroma 可用、巡检调度器运行中、LLM 连接正常）
  - When 运维人员查看 Dashboard 的健康状态面板
  - Then 4 个组件指示灯应当全部为绿色，每个指示灯下方标注组件名称和简要状态描述（如"LangGraph 引擎：已编译，14 节点"）
- **AC-W024-02** — 组件异常告警
  - Given LLM 服务（DeepSeek API）不可达
  - When 系统轮询检测到 LLM 连接失败
  - Then Dashboard 上 LLM 连接指示灯应当变为红色，显示"LLM 连接：不可达 — API 超时"，同时可展示最后一次成功连接的时间
- **AC-W024-03** — 状态自动刷新
  - Given Dashboard 页面已打开
  - When 巡检调度器因配置变更被重启（短暂不可用）
  - Then 页面上"巡检调度器"指示灯应当在下一个轮询周期内从绿色暂时变为黄色（重启中），待重启完成后恢复绿色

---

### 9. 认证与会话管理

#### REQ-WEBUI-FUNC-025: 用户登录与 JWT 认证
| 字段 | 内容 |
|------|------|
| **ID** | REQ-WEBUI-FUNC-025 |
| **描述** | Web 界面应当提供登录页面，运维人员输入 admin 账号和密码进行身份认证。认证成功后后端返回 JWT Token，前端存储 Token 并在后续所有 API 请求中携带（Authorization: Bearer <token>）。Token 过期后自动跳转至登录页面。 |
| **来源引用** | PM 技术决策第4项 — “JWT Token 认证，内置一个 admin 账号” |
| **优先级** | Must Have |
| **备注** | Demo 阶段仅内置一个 admin 账号（账号密码在系统首次启动时初始化或通过环境变量配置） |

**验收标准：**
- **AC-W025-01** — 登录成功
  - Given 运维人员知道 admin 账号的密码
  - When 在登录页面输入正确的用户名和密码，点击"登录"
  - Then 系统应当返回 JWT Token，前端跳转至 Dashboard 首页，导航栏显示当前登录用户="admin"
- **AC-W025-02** — 登录失败
  - Given 运维人员输入错误的密码
  - When 点击"登录"
  - Then 系统应当返回 401 错误，页面显示"用户名或密码错误"提示，不泄露是用户名错误还是密码错误
- **AC-W025-03** — Token 过期自动跳转
  - Given 运维人员的 JWT Token 已过期
  - When 前端发起任意 API 请求收到 401 响应
  - Then 前端应当清除本地 Token，自动跳转至登录页面，并提示"登录已过期，请重新登录"
- **AC-W025-04** — 未登录访问保护
  - Given 用户未登录（无有效 Token）
  - When 尝试直接访问 Dashboard 或任意功能页面的 URL
  - Then 前端路由守卫应当拦截并重定向至登录页面

#### REQ-WEBUI-FUNC-026: 用户登出
| 字段 | 内容 |
|------|------|
| **ID** | REQ-WEBUI-FUNC-026 |
| **描述** | Web 界面应当提供登出功能，运维人员点击"退出登录"后，前端清除本地 JWT Token，跳转至登录页面。 |
| **来源引用** | PM 技术决策第4项 — “JWT Token 认证”（登出为标准认证流程的必要组成部分） |
| **优先级** | Must Have |
| **备注** | Demo 阶段无服务端 Token 黑名单机制（登出为纯前端操作） |

**验收标准：**
- **AC-W026-01** — 正常登出
  - Given 运维人员已登录系统
  - When 运维人员点击导航栏右上角的"退出登录"按钮
  - Then 前端应当清除 localStorage/sessionStorage 中的 JWT Token，跳转至登录页面，登出后无法通过浏览器后退按钮回到已登录页面

---

### 10. 导航与全局布局

#### REQ-WEBUI-FUNC-027: 全局导航菜单
| 字段 | 内容 |
|------|------|
| **ID** | REQ-WEBUI-FUNC-027 |
| **描述** | Web 界面应当提供全局侧边栏导航菜单，包含所有功能模块的入口：Dashboard（首页）、告警管理、工作流可视化、待审批、设备管理、巡检配置、知识库管理、系统配置。当前激活的菜单项高亮，待审批菜单项显示待处理数量徽标。 |
| **来源引用** | PM 8大功能模块（所有模块需要一致的导航入口） |
| **优先级** | Must Have |
| **备注** | 菜单结构映射 PM 定义的 8 大功能模块 |

**验收标准：**
- **AC-W027-01** — 侧边栏导航展示
  - Given 运维人员已登录系统
  - When 登录后进入主界面
  - Then 左侧应当展示固定的侧边栏菜单，包含：Dashboard、告警管理、工作流可视化、审批管理（含待审批/审批历史子菜单）、设备管理、巡检配置、知识库管理（含文档/模板子菜单）、系统配置（含全局配置/日志子菜单）
- **AC-W027-02** — 菜单折叠
  - Given 运维人员需要更大的内容查看空间
  - When 点击侧边栏折叠按钮
  - Then 侧边栏应当折叠为仅显示图标的窄栏，鼠标悬停时展开完整菜单文字

#### REQ-WEBUI-FUNC-028: 全局面包屑导航
| 字段 | 内容 |
|------|------|
| **ID** | REQ-WEBUI-FUNC-028 |
| **描述** | Web 界面应当在页面顶部提供面包屑导航，展示当前页面的层级路径（如：首页 > 告警管理 > 告警详情），运维人员可点击面包屑任意层级快速返回上级页面。 |
| **来源引用** | PM 8大功能模块（Web UI 通用交互模式） |
| **优先级** | Should Have |
| **备注** | 面包屑为标准 Web 应用导航辅助工具，提升深层页面的导航效率 |

**验收标准：**
- **AC-W028-01** — 面包屑路径展示
  - Given 运维人员当前位于"Core-SW-01 的 PORT_DOWN 告警详情"页面
  - When 查看页面顶部
  - Then 面包屑应当显示：Dashboard > 告警管理 > 告警详情（Core-SW-01/PORT_DOWN），当前页面项不可点击
- **AC-W028-02** — 面包屑点击返回
  - Given 运维人员在告警详情页面
  - When 点击面包屑中的"告警管理"
  - Then 系统应当导航回告警列表页面，保留之前的筛选条件状态

---

## 非功能需求（Non-Functional Requirements）

### 1. 前端性能

#### REQ-WEBUI-NFUNC-001: 页面加载性能
| 字段 | 内容 |
|------|------|
| **ID** | REQ-WEBUI-NFUNC-001 |
| **描述** | Web 界面的首页（Dashboard）首次加载时间（含静态资源加载和首次 API 数据获取）应当不超过 3 秒（在 10Mbps 网络环境下），后续页面切换（SPA 路由跳转）不超过 1 秒。 |
| **来源引用** | PM 非功能需求标注 — “前端性能（页面加载 < 3s）” |
| **优先级** | Must Have |
| **备注** | 首次加载时间指 DOMContentLoaded + 首个 API 响应完成；静态资源使用 Vite 构建优化（代码分割、Tree Shaking） |

**验收标准：**
- **AC-WNF-001-01** — Dashboard 首次加载 < 3s
  - Given 运维人员首次打开 Web 界面（浏览器无缓存）
  - When 输入 URL 并访问
  - Then 从页面开始加载到 Dashboard 所有图表和数据渲染完成的总耗时应当 ≤ 3 秒
- **AC-WNF-001-02** — SPA 页面切换 < 1s
  - Given Dashboard 页面已加载完成
  - When 运维人员点击导航菜单切换到"告警管理"页面
  - Then 页面切换和告警列表数据加载总耗时应当 ≤ 1 秒

#### REQ-WEBUI-NFUNC-002: 浏览器兼容性
| 字段 | 内容 |
|------|------|
| **ID** | REQ-WEBUI-NFUNC-002 |
| **描述** | Web 界面应当兼容以下桌面浏览器的最新两个主要版本：Google Chrome（>= 90）、Microsoft Edge（>= 90）。Demo 阶段不要求兼容 Safari 或 Firefox。 |
| **来源引用** | PM 非功能需求标注 — “浏览器兼容性（Chrome/Edge）” |
| **优先级** | Must Have |
| **备注** | Vue 3 + Element Plus 官方支持 Chrome 和 Edge 最新版；Demo 阶段不要求 IE 或移动端浏览器 |

**验收标准：**
- **AC-WNF-002-01** — Chrome 兼容
  - Given 运维人员使用 Chrome 90+ 浏览器
  - When 访问 Web 界面的所有功能页面
  - Then 所有页面布局正常、交互功能正常、图表正常渲染、无控制台 JavaScript 错误
- **AC-WNF-002-02** — Edge 兼容
  - Given 运维人员使用 Edge 90+ 浏览器
  - When 访问 Web 界面的所有功能页面
  - Then 同上验收标准

### 2. 安全性

#### REQ-WEBUI-NFUNC-003: JWT Token 过期策略
| 字段 | 内容 |
|------|------|
| **ID** | REQ-WEBUI-NFUNC-003 |
| **描述** | 系统签发的 JWT Token 应当设置合理的过期时间，Token 过期后前端必须重新登录获取新 Token。Demo 阶段 Token 过期时间建议为 24 小时，不支持 Token 刷新（refresh token）机制。 |
| **来源引用** | PM 技术决策第4项 — “JWT Token 认证” + PM 非功能需求标注 — “JWT 过期策略” |
| **优先级** | Must Have |
| **备注** | [INFERRED — requires PM confirmation] 24 小时过期时间为单页应用常用实践，PM 未指定具体过期时长，请确认是否合适 |

**验收标准：**
- **AC-WNF-003-01** — Token 过期失效
  - Given 运维人员的 JWT Token 签发于 24 小时前
  - When 运维人员发起任意受保护的 API 请求
  - Then 后端应当返回 401 Unauthorized，前端检测到后清除 Token 并重定向至登录页面
- **AC-WNF-003-02** — 有效 Token 正常访问
  - Given 运维人员的 JWT Token 签发于 1 小时前（未过期）
  - When 运维人员发起任意受保护的 API 请求
  - Then 后端应当正常处理请求并返回数据

#### REQ-WEBUI-NFUNC-004: 密码安全策略
| 字段 | 内容 |
|------|------|
| **ID** | REQ-WEBUI-NFUNC-004 |
| **描述** | admin 账号密码应当使用 bcrypt 或 argon2 哈希算法存储（不存储明文），登录时哈希比对。前端传输密码时通过 HTTPS POST Body 发送（Demo 阶段若使用 HTTP，接受明文传输但标记安全风险）。 |
| **来源引用** | PM 技术决策第4项 — “JWT Token 认证，内置一个 admin 账号”（密码安全为认证系统的标准安全要求） |
| **优先级** | Must Have |
| **备注** | Demo 阶段 admin 初始密码可通过环境变量 ADMIN_PASSWORD 设置或首次启动时随机生成并输出到控制台 |

**验收标准：**
- **AC-WNF-004-01** — 密码哈希存储
  - Given 系统首次初始化 admin 账号
  - When 密码写入 SQLite 用户表
  - Then 存储的密码字段应当是 bcrypt 哈希值（如 `$2b$12$...`），而非明文密码
- **AC-WNF-004-02** — 密码验证
  - Given admin 密码的 bcrypt 哈希已存储
  - When 运维人员使用正确密码登录
  - Then 系统应当通过哈希比对验证成功，返回 JWT Token

#### REQ-WEBUI-NFUNC-005: API Key 加密存储
| 字段 | 内容 |
|------|------|
| **ID** | REQ-WEBUI-NFUNC-005 |
| **描述** | DeepSeek API Key 在 SQLite 中必须加密存储（AES-256-CBC 或类似对称加密算法），禁止明文存储。加密密钥从环境变量或平台密钥管理获取，不得硬编码在源代码中。 |
| **来源引用** | PM 非功能需求标注 — “API Key 加密存储” |
| **优先级** | Must Have |
| **备注** | Demo 阶段加密密钥可从环境变量 ENCRYPTION_KEY 读取，若未设置则在首次启动时随机生成并存储 |

**验收标准：**
- **AC-WNF-005-01** — API Key 加密存储验证
  - Given 运维人员配置了 DeepSeek API Key="sk-abc123"
  - When Key 写入 SQLite 数据库
  - Then 数据库中的 api_key 字段应当存储为 AES-256 加密后的密文（Base64 编码），直接查看数据库无法获取明文 Key
- **AC-WNF-005-02** — API Key 解密使用
  - Given API Key 已加密存储
  - When LLMService 需要调用 DeepSeek API
  - Then 系统应当使用加密密钥解密后使用，解密失败时记录安全告警日志并返回 LLM 不可用状态

#### REQ-WEBUI-NFUNC-006: 输入校验与 XSS 防护
| 字段 | 内容 |
|------|------|
| **ID** | REQ-WEBUI-NFUNC-006 |
| **描述** | Web 界面所有用户输入点（表单、URL 参数、文件上传）必须在前端和后端进行双重校验和净化，防止 XSS 跨站脚本攻击和 SQL 注入。前端使用 Vue 3 模板自动转义 + Element Plus 表单校验；后端使用 FastAPI 类型校验 + 输入净化。 |
| **来源引用** | Web 安全标准实践（所有用户输入必须校验） |
| **优先级** | Must Have |
| **备注** | Vue 3 默认对 `{{ }}` 插值进行 HTML 转义，已提供基础 XSS 防护 |

**验收标准：**
- **AC-WNF-006-01** — XSS 注入防护
  - Given 运维人员在模拟告警的设备名称输入框中输入 `<script>alert('XSS')</script>`
  - When 提交表单并在告警列表中查看
  - Then 页面应当展示转义后的文本（`&lt;script&gt;alert('XSS')&lt;/script&gt;`），不执行脚本
- **AC-WNF-006-02** — SQL 注入防护
  - Given 攻击者在告警筛选参数中注入 SQL 语句
  - When 请求发送至后端 API
  - Then SQLAlchemy ORM 的参数化查询应当阻止 SQL 注入，返回正常查询结果或空结果

### 3. 用户体验

#### REQ-WEBUI-NFUNC-007: 响应式布局（桌面端优先）
| 字段 | 内容 |
|------|------|
| **ID** | REQ-WEBUI-NFUNC-007 |
| **描述** | Web 界面的布局应当针对桌面端（屏幕宽度 >= 1280px）优化，采用侧边栏 + 内容区的经典管理后台布局。侧边栏宽度固定（约 220px），内容区自适应填充剩余宽度。Demo 阶段不要求平板或移动端适配。 |
| **来源引用** | PM 非功能需求标注 — “响应式设计（桌面端优先）” + PM Demo 范围边界 — “Demo 阶段不要求移动端适配” |
| **优先级** | Must Have |
| **备注** | 桌面端优先意味着保证 1280px-1920px 分辨率下完美显示；低于 1280px 时侧边栏可折叠但非必需 |

**验收标准：**
- **AC-WNF-007-01** — 1280px 分辨率完整显示
  - Given 运维人员使用 1280×720 分辨率的显示器
  - When 打开 Web 界面所有页面
  - Then 所有页面布局正常，无水平滚动条，表格、图表、表单在可视区域内完整显示
- **AC-WNF-007-02** — 1920px 分辨率友好
  - Given 运维人员使用 1920×1080 分辨率的显示器
  - When 打开 Dashboard 页面
  - Then 图表和统计卡片应当充分利用屏幕宽度合理排列（如告警统计图表 2 列布局），不出现大片空白区域

#### REQ-WEBUI-NFUNC-008: 操作反馈与加载状态
| 字段 | 内容 |
|------|------|
| **ID** | REQ-WEBUI-NFUNC-008 |
| **描述** | Web 界面的所有异步操作（数据加载、表单提交、审批决策等）应当提供明确的加载状态指示（Loading 动画或骨架屏）、操作成功的反馈提示（Toast 通知）和操作失败的友好错误信息。 |
| **来源引用** | Web UI 用户体验标准实践 |
| **优先级** | Must Have |
| **备注** | Element Plus 内置 Loading 指令、Message 组件和骨架屏组件可直接用于满足此需求 |

**验收标准：**
- **AC-WNF-008-01** — 数据加载 Loading 指示
  - Given 运维人员打开告警列表页面
  - When 后端 API 正在查询并返回数据（网络延迟 500ms）
  - Then 页面应当显示 Loading 动画或骨架屏占位，避免空白页面导致的"系统无响应"错觉
- **AC-WNF-008-02** — 操作成功反馈
  - Given 运维人员成功提交了一个审批决定（APPROVED）
  - When 后端返回成功响应
  - Then 页面右上角应当弹出绿色 Toast 通知"审批已提交"，3 秒后自动消失
- **AC-WNF-008-03** — 操作失败反馈
  - Given 运维人员尝试删除一台仍有进行中告警的设备
  - When 后端返回操作失败
  - Then 页面应当弹出红色 Toast 通知显示具体失败原因（"该设备有 1 条处理中的告警，无法删除"）

---

## 外部接口需求（External Interface Requirements）

### 新增 API 端点契约

以下列出 Web UI 所需的新增 REST API 端点，所有端点挂载在现有 FastAPI 应用（端口 8000）上。标注 `[NEW]` 为全新端点，`[ENHANCED]` 为在现有端点基础上增强返回数据。

#### 认证

| 接口编号 | HTTP 方法 | 路径 | 说明 | 类型 |
|---------|----------|------|------|------|
| API-AUTH-01 | POST | `/auth/login` | 用户登录，返回 JWT Token | [NEW] |
| API-AUTH-02 | POST | `/auth/logout` | 用户登出（Demo 阶段前端清除 Token 即可，后端端点预留） | [NEW] |

**API-AUTH-01 请求/响应 Schema：**
```json
// Request
{
  "username": "string (admin)",
  "password": "string"
}
// Response 200
{
  "access_token": "string (JWT)",
  "token_type": "bearer",
  "expires_in": 86400
}
// Response 401
{
  "detail": "用户名或密码错误"
}
```

#### 告警管理

| 接口编号 | HTTP 方法 | 路径 | 说明 | 类型 |
|---------|----------|------|------|------|
| API-ALERT-01 | GET | `/api/alerts` | 告警列表（分页+筛选） | [NEW] |
| API-ALERT-02 | GET | `/api/alerts/{alert_id}` | 告警详情（含时间线） | [NEW] |
| API-ALERT-03 | GET | `/api/alerts/{alert_id}/workflow` | 告警关联的工作流状态 | [NEW] |
| API-ALERT-04 | POST | `/api/alerts/simulate` | 模拟告警（增强版） | [ENHANCED] |

**API-ALERT-01 查询参数：**
- `alert_type` (optional): MAC_FLAPPING | PORT_DOWN | CPU_HIGH
- `severity` (optional): CRITICAL | MAJOR | MINOR | WARNING
- `status` (optional): PROCESSING | CLOSED | FAILED | REJECTED
- `source` (optional): WEBHOOK | INSPECTION | MOCK
- `time_from` (optional): ISO8601 datetime
- `time_to` (optional): ISO8601 datetime
- `page` (default=1): int
- `page_size` (default=20): int

**API-ALERT-04 请求 Body（增强版，替代原有 query params）：**
```json
{
  "alert_type": "PORT_DOWN",
  "device_name": "Core-SW-01",
  "device_ip": "192.168.1.1",
  "interface": "Gi0/1",
  "mac_address": null,
  "cpu_percent": null
}
```

#### 工作流可视化

| 接口编号 | HTTP 方法 | 路径 | 说明 | 类型 |
|---------|----------|------|------|------|
| API-WF-01 | GET | `/api/workflow/graph` | LangGraph 节点拓扑结构 | [NEW] |
| API-WF-02 | GET | `/api/workflow/{checkpoint_id}/nodes/{node_name}` | 节点 State 快照 | [NEW] |
| API-WF-03 | GET | `/api/workflow/{checkpoint_id}/state` | 工作流当前状态（增强版） | [ENHANCED] |

#### 审批管理

| 接口编号 | HTTP 方法 | 路径 | 说明 | 类型 |
|---------|----------|------|------|------|
| API-APPR-01 | GET | `/api/approvals/pending` | 待审批列表（增强版） | [ENHANCED] |
| API-APPR-02 | POST | `/api/approvals/{checkpoint_id}/decide` | 审批决定（已有） | 现有 |
| API-APPR-03 | GET | `/api/approvals/history` | 审批历史（分页+筛选） | [NEW] |

#### 设备管理

| 接口编号 | HTTP 方法 | 路径 | 说明 | 类型 |
|---------|----------|------|------|------|
| API-DEV-01 | GET | `/api/devices` | 设备列表 | [NEW] |
| API-DEV-02 | POST | `/api/devices` | 添加设备 | [NEW] |
| API-DEV-03 | GET | `/api/devices/{device_id}` | 设备详情 | [NEW] |
| API-DEV-04 | PUT | `/api/devices/{device_id}` | 更新设备信息 | [NEW] |
| API-DEV-05 | DELETE | `/api/devices/{device_id}` | 删除设备 | [NEW] |
| API-DEV-06 | PUT | `/api/devices/{device_id}/credentials` | 配置设备 SSH 凭据 | [NEW] |
| API-DEV-07 | GET | `/api/devices/{device_id}/diagnostics` | 设备最近诊断结果 | [NEW] |

**API-DEV-02 请求 Body：**
```json
{
  "device_name": "string",
  "device_ip": "string (IPv4)",
  "device_model": "string (optional)",
  "group": "string (optional)"
}
```

**API-DEV-06 请求 Body：**
```json
{
  "ssh_username": "string",
  "ssh_password": "string",
  "ssh_port": 22
}
```
> 密码字段在响应中始终返回 `"****"`，不返回明文。

#### 巡检管理

| 接口编号 | HTTP 方法 | 路径 | 说明 | 类型 |
|---------|----------|------|------|------|
| API-INSP-01 | GET | `/api/inspection/config` | 巡检配置 | [NEW] |
| API-INSP-02 | PUT | `/api/inspection/config` | 更新巡检配置 | [NEW] |
| API-INSP-03 | POST | `/api/inspection/trigger` | 手动触发巡检 | [NEW] |
| API-INSP-04 | GET | `/api/inspection/history` | 巡检历史（分页+筛选） | [NEW] |

#### 知识库管理

| 接口编号 | HTTP 方法 | 路径 | 说明 | 类型 |
|---------|----------|------|------|------|
| API-KB-01 | GET | `/api/knowledge/documents` | 知识文档列表（分页+按类型筛选） | [NEW] |
| API-KB-02 | POST | `/api/knowledge/documents` | 创建知识文档 | [NEW] |
| API-KB-03 | GET | `/api/knowledge/documents/{doc_id}` | 文档详情 | [NEW] |
| API-KB-04 | PUT | `/api/knowledge/documents/{doc_id}` | 更新知识文档 | [NEW] |
| API-KB-05 | DELETE | `/api/knowledge/documents/{doc_id}` | 删除知识文档 | [NEW] |
| API-KB-06 | GET | `/api/knowledge/templates` | 命令模板列表 | [NEW] |
| API-KB-07 | POST | `/api/knowledge/templates` | 创建命令模板 | [NEW] |
| API-KB-08 | GET | `/api/knowledge/templates/{template_id}` | 模板详情 | [NEW] |
| API-KB-09 | PUT | `/api/knowledge/templates/{template_id}` | 更新命令模板 | [NEW] |
| API-KB-10 | DELETE | `/api/knowledge/templates/{template_id}` | 删除命令模板 | [NEW] |
| API-KB-11 | POST | `/api/knowledge/test-retrieval` | RAG 检索测试 | [NEW] |

**API-KB-11 请求/响应 Schema：**
```json
// Request
{
  "query": "string (测试查询文本)",
  "alert_type": "MAC_FLAPPING (optional filter)",
  "top_k": 5
}
// Response 200
{
  "results": [
    {
      "doc_id": "string",
      "title": "string",
      "content_snippet": "string (匹配片段，关键词高亮标记)",
      "similarity_score": 0.85,
      "alert_type": "MAC_FLAPPING"
    }
  ],
  "total_indexed": 10,
  "query_time_ms": 45
}
```

#### 系统配置

| 接口编号 | HTTP 方法 | 路径 | 说明 | 类型 |
|---------|----------|------|------|------|
| API-CFG-01 | GET | `/api/system/config` | 全局配置 | [NEW] |
| API-CFG-02 | PUT | `/api/system/config` | 更新全局配置 | [NEW] |
| API-CFG-03 | PUT | `/api/system/config/llm-api-key` | 配置 LLM API Key | [NEW] |
| API-CFG-04 | POST | `/api/system/config/llm-test` | 测试 LLM 连接 | [NEW] |
| API-CFG-05 | GET | `/api/system/logs` | 查看/搜索日志 | [NEW] |

**API-CFG-05 查询参数：**
- `level` (optional): INFO | WARNING | ERROR
- `keyword` (optional): string (搜索关键词)
- `time_from` (optional): ISO8601
- `time_to` (optional): ISO8601
- `page` (default=1): int
- `page_size` (default=100): int

#### Dashboard

| 接口编号 | HTTP 方法 | 路径 | 说明 | 类型 |
|---------|----------|------|------|------|
| API-DASH-01 | GET | `/api/dashboard/stats` | 告警统计数据 | [NEW] |
| API-DASH-02 | GET | `/api/dashboard/health` | 系统健康状态（增强版） | [ENHANCED] |

---

### 与现有 API 端点的关系

| 现有端点 | 处理方式 | 说明 |
|---------|---------|------|
| `POST /webhook/alert` | 保持不变 | Webhook 接收继续使用 |
| `POST /alerts/simulate` | 增强 | 新增 `/api/alerts/simulate`，接受 JSON Body 参数；原有端点保留兼容或废弃 |
| `GET /approvals/pending` | 增强 | 改为 `/api/approvals/pending`，返回更丰富的审批信息（含修复方案摘要） |
| `POST /approvals/{id}/decide` | 增强 | 路径改为 `/api/approvals/{id}/decide`，支持审批备注字段 |
| `GET /workflow/{id}/state` | 增强 | 路径改为 `/api/workflow/{id}/state`，返回更详细的 State 快照 |
| `GET /health` | 增强 | 路径改为 `/api/dashboard/health`，增加 LLM 连接测试和知识库文档数 |

> 所有新 API 端点均挂载在 `/api/` 前缀下，与现有端点共存于同一 FastAPI app 实例（端口 8000）。前端静态文件由 FastAPI 托管（生产模式）或 Vite dev server 独立运行（开发模式）。

---

## Demo 范围边界

### Demo 范围内（In Scope）

| 功能模块 | 实现策略 | 说明 |
|---------|---------|------|
| 告警管理 | **真实实现** | 完整的列表、筛选、详情、模拟告警功能；告警数据持久化至 SQLite |
| 工作流可视化 | **真实实现** | 14 节点拓扑图 + 当前激活节点高亮 + State 快照查看 |
| 人工审批操作 | **真实实现** | 待审批列表 + 审批详情 + 批准/拒绝操作 + 审批历史（解决 MAJ-001） |
| 设备管理 | **真实实现** | 设备 CRUD + 凭据配置（加密存储）+ 诊断结果查看 |
| 巡检配置 | **真实实现** | 间隔配置 + 手动触发 + 巡检历史持久化 |
| 知识库管理 | **真实实现** | 文档 CRUD + 模板 CRUD + 检索测试 + Chroma 索引同步 |
| 系统配置 | **真实实现** | 全局配置编辑 + API Key 加密存储 + 日志查看 |
| Dashboard | **真实实现** | 告警统计图表 + 修复成功率 + 系统健康面板 |
| 认证登录 | **真实实现** | JWT 认证 + admin 单账号 + 登录/登出 |
| 数据库 | **真实实现** | SQLite + SQLAlchemy ORM，持久化所有 Web UI 相关数据 |
| 前端 | **真实实现** | Vue 3 + Vite + Element Plus，静态文件由 FastAPI 托管 |

### Demo 范围外（Out of Scope）

| 编号 | 排除项 | 依据 |
|------|-------|------|
| OOS-WEB-001 | 多用户 RBAC（角色权限管理） | PM Demo 范围边界 — “Demo 阶段不要求多用户 RBAC” |
| OOS-WEB-002 | 移动端/平板响应式适配 | PM Demo 范围边界 — “移动端适配、国际化、SSO 集成为 Demo 范围外” |
| OOS-WEB-003 | 国际化（i18n / 多语言界面） | PM Demo 范围边界 |
| OOS-WEB-004 | SSO / LDAP / OAuth 集成 | PM Demo 范围边界 |
| OOS-WEB-005 | WebSocket 实时推送 | PM 技术决策第5项 — 采用前端轮询替代 WebSocket |
| OOS-WEB-006 | 暗色模式（Dark Mode）主题 | PM 未提及，Demo 阶段使用 Element Plus 默认主题 |
| OOS-WEB-007 | 操作日志导出（CSV/Excel） | PM 未提及 |
| OOS-WEB-008 | 告警通知（邮件/短信/Webhook 外发） | PM 未提及 |
| OOS-WEB-009 | 多 Tab 页面操作同步 | Demo 阶段不要求 |
| OOS-WEB-010 | 在线升级/热更新 | Demo 阶段不要求 |

---

## 数据持久化需求（供架构师参考）

以下列出 Web UI 需要持久化到 SQLite 的数据实体及其关键字段（表结构设计由 GROUP_WEBUI_B 架构师负责）：

| 数据实体 | 关键字段 | 说明 |
|---------|---------|------|
| **users** | id, username, password_hash, created_at | 用户表（Demo 仅 admin 单用户） |
| **alerts** | id, alert_id, alert_type, severity, content, device_info(JSON), source, status, created_at, updated_at | 告警主表（替代 MemorySaver） |
| **alert_timeline** | id, alert_id, node_name, state_snapshot(JSON), started_at, completed_at, status | 告警处理时间线（每个节点的执行记录） |
| **approvals** | id, alert_id, checkpoint_id, fix_plan(JSON), risk_level, decision, decider, decided_at, note | 审批记录（解决 MAJ-001） |
| **devices** | id, device_name, device_ip, device_model, group_name, status, created_at, updated_at | 设备信息（替代 main.py 硬编码） |
| **device_credentials** | id, device_id, ssh_username, ssh_password_encrypted, ssh_port | 设备凭据（加密存储） |
| **inspection_records** | id, trigger_mode, started_at, completed_at, total_devices, anomaly_count, details(JSON) | 巡检历史 |
| **knowledge_documents** | id, title, alert_type, content, embedding_id, created_at, updated_at | 知识文档 |
| **command_templates** | id, name, alert_type, yaml_content, parameters(JSON), created_at, updated_at | 命令模板 |
| **system_config** | id, config_key, config_value, updated_at | 系统配置键值对 |
| **audit_logs** | id, timestamp, level, module, message, details(JSON) | 审计/操作日志（可选：替代文件日志） |

> 以上为需求层的逻辑数据实体定义，具体 SQLAlchemy Model 设计和表关系由架构师在 module_design.md 中细化。

---

## 需求追踪矩阵

| 需求 ID | 需求描述（摘要） | 来源（PM 8大功能模块） | 关联用户故事 |
|---------|---------------|---------------------|------------|
| REQ-WEBUI-FUNC-001 | 告警列表查看与筛选 | 模块1 — 告警管理 | US-WEBUI-001 |
| REQ-WEBUI-FUNC-002 | 告警详情查看 | 模块1 — 告警管理 | US-WEBUI-001 |
| REQ-WEBUI-FUNC-003 | 手动模拟发送告警 | 模块1 — 告警管理 | US-WEBUI-002 |
| REQ-WEBUI-FUNC-004 | 告警处理流程实时状态追踪 | 模块1 — 告警管理 | US-WEBUI-003 |
| REQ-WEBUI-FUNC-005 | LangGraph 节点拓扑可视化 | 模块2 — 工作流可视化 | US-WEBUI-003 |
| REQ-WEBUI-FUNC-006 | 节点 State 快照查看 | 模块2 — 工作流可视化 | US-WEBUI-003 |
| REQ-WEBUI-FUNC-007 | 待审批列表展示 | 模块3 — 人工审批操作 | US-WEBUI-004 |
| REQ-WEBUI-FUNC-008 | 审批决策操作 | 模块3 — 人工审批操作 | US-WEBUI-004 |
| REQ-WEBUI-FUNC-009 | 审批历史记录 | 模块3 — 人工审批操作 | US-WEBUI-005 |
| REQ-WEBUI-FUNC-010 | 纳管设备 CRUD | 模块4 — 设备管理 | US-WEBUI-006 |
| REQ-WEBUI-FUNC-011 | 设备凭据配置 | 模块4 — 设备管理 | US-WEBUI-007 |
| REQ-WEBUI-FUNC-012 | 设备诊断结果查看 | 模块4 — 设备管理 | US-WEBUI-006 |
| REQ-WEBUI-FUNC-013 | 巡检间隔配置 | 模块5 — 巡检配置 | US-WEBUI-008 |
| REQ-WEBUI-FUNC-014 | 手动触发巡检 | 模块5 — 巡检配置 | US-WEBUI-008 |
| REQ-WEBUI-FUNC-015 | 巡检历史记录 | 模块5 — 巡检配置 | US-WEBUI-009 |
| REQ-WEBUI-FUNC-016 | 知识文档 CRUD | 模块6 — 知识库管理 | US-WEBUI-010 |
| REQ-WEBUI-FUNC-017 | 命令模板 CRUD | 模块6 — 知识库管理 | US-WEBUI-011 |
| REQ-WEBUI-FUNC-018 | 知识库检索测试界面 | 模块6 — 知识库管理 | US-WEBUI-012 |
| REQ-WEBUI-FUNC-019 | 全局配置可视化编辑 | 模块7 — 系统配置 | US-WEBUI-013 |
| REQ-WEBUI-FUNC-020 | LLM API Key 安全配置 | 模块7 — 系统配置 | US-WEBUI-014 |
| REQ-WEBUI-FUNC-021 | 日志查看 | 模块7 — 系统配置 | US-WEBUI-015 |
| REQ-WEBUI-FUNC-022 | 告警统计图表 [INFERRED] | 模块8 — Dashboard 仪表盘 | US-WEBUI-016 |
| REQ-WEBUI-FUNC-023 | 修复成功率统计 | 模块8 — Dashboard 仪表盘 | US-WEBUI-016 |
| REQ-WEBUI-FUNC-024 | 系统健康状态面板 | 模块8 — Dashboard 仪表盘 | US-WEBUI-016 |
| REQ-WEBUI-FUNC-025 | 用户登录与 JWT 认证 | PM 技术决策第4项 | US-WEBUI-017 |
| REQ-WEBUI-FUNC-026 | 用户登出 | PM 技术决策第4项 | US-WEBUI-017 |
| REQ-WEBUI-FUNC-027 | 全局导航菜单 | PM 8大功能模块（全局） | US-WEBUI-018 |
| REQ-WEBUI-FUNC-028 | 全局面包屑导航 | PM 8大功能模块（全局） | US-WEBUI-018 |
| REQ-WEBUI-NFUNC-001 | 页面加载性能 | PM 非功能需求 | US-WEBUI-018 |
| REQ-WEBUI-NFUNC-002 | 浏览器兼容性 | PM 非功能需求 | US-WEBUI-018 |
| REQ-WEBUI-NFUNC-003 | JWT Token 过期策略 [INFERRED] | PM 非功能需求 | US-WEBUI-017 |
| REQ-WEBUI-NFUNC-004 | 密码安全策略 | PM 技术决策第4项 | US-WEBUI-017 |
| REQ-WEBUI-NFUNC-005 | API Key 加密存储 | PM 非功能需求 | US-WEBUI-014 |
| REQ-WEBUI-NFUNC-006 | 输入校验与 XSS 防护 | Web 安全标准 | US-WEBUI-018 |
| REQ-WEBUI-NFUNC-007 | 响应式布局（桌面端优先） | PM 非功能需求 | US-WEBUI-018 |
| REQ-WEBUI-NFUNC-008 | 操作反馈与加载状态 | Web UI 标准实践 | US-WEBUI-018 |

---

## 待确认推断项

| ID | 内容 | 建议 PM 关注 |
|----|------|------------|
| REQ-WEBUI-FUNC-022 | Dashboard 图表类型：饼图（类型分布）、柱状图（严重级别）、折线图（时间趋势） | PM 原文描述了统计维度但未指定图表形式；柱状图+饼图+折线图是 Dashboard 标准搭配，请确认是否合适 |
| REQ-WEBUI-NFUNC-003 | JWT Token 过期时间 24 小时，无 Refresh Token 机制 | PM 未指定过期时间，24 小时为单页应用常用实践；Demo 阶段不引入 Refresh Token 复杂性，请确认 |
| REQ-WEBUI-NFUNC-007 | 设备凭据密码在 UI 中掩码显示（****），后端不返回明文 | PM 描述了凭据配置但未说明展示策略；密码掩码是安全最佳实践，请确认是否需要"显示/隐藏"切换按钮 |

---

## 开放问题

| 编号 | 问题 | 建议 | 状态 |
|------|------|------|------|
| Q-WEB-001 | admin 初始密码如何设置？ | 建议通过环境变量 `ADMIN_PASSWORD` 设置；若未设置则在首次启动时随机生成并输出到控制台 | 待 PM 确认 |
| Q-WEB-002 | 告警数据从 MemorySaver 迁移至 SQLite 时，是否需要保留现有 LangGraph checkpoint 机制？ | 建议 LangGraph checkpoint 继续使用 MemorySaver（工作流状态管理），告警业务数据（列表、详情、历史）独立存储至 SQLite，两者不冲突 | 待 PM 确认 |
| Q-WEB-003 | 前端构建产物（dist/）在 FastAPI 中的托管路径和挂载方式？ | 建议开发阶段 Vite dev server（端口 5173）代理到 FastAPI（端口 8000）；生产阶段 FastAPI 挂载静态文件到根路径 `/` | 交由 GROUP_WEBUI_B 架构师决策 |
| Q-WEB-004 | 现有 `/alerts/simulate` 端点（query params 风格）是否需要保留向后兼容？ | 建议废弃旧端点，Web UI 使用新端点 `POST /api/alerts/simulate`（JSON Body 风格），但保留旧端点至 Web UI 上线完毕 | 待 PM 确认 |
