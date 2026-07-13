<file_header>
  <author_agent>sub_agent_system_architect</author_agent>
  <timestamp>2026-07-10T00:00:00Z</timestamp>
  <project_name>NetworkAgentDemo</project_name>
  <version>0.1.0</version>
  <input_files>
    <file>requirements/project_brief.md</file>
    <file>requirements/requirements_spec.md</file>
    <file>requirements/user_stories.md</file>
    <file>architecture/architecture_design.md</file>
  </input_files>
  <phase>PHASE_03</phase>
  <status>APPROVED</status>
</file_header>

# 模块设计文档 — NetworkAgentDemo

---

## 模块总览

| MOD-ID | 模块名 | 层级 | 职责 | 依赖于 |
|--------|--------|------|------|--------|
| MOD-001 | WebhookReceiver | 触发层 | 接收 Mock Zabbix Webhook HTTP POST 请求，解析 Payload 并交给归一化层 | MOD-004 |
| MOD-002 | InspectionScheduler | 触发层 | 按可配置间隔定时触发巡检，对所有纳管设备执行健康检查 | MOD-004, MOD-011 |
| MOD-003 | StateGraphEngine | 编排层 | 定义 LangGraph StateGraph（14 节点 + 4 条件边），管理状态机生命周期和 Interrupt 检查点 | MOD-005 |
| MOD-004 | AlertNormalizer | 编排层 | 将 Webhook/巡检原始事件归一化为标准 Alert 对象，执行告警去重和时效性检查 | — |
| MOD-005 | NodeHandlers | 编排层 | 实现 LangGraph 全部 14 个节点的处理函数，调用下层模块完成具体业务逻辑 | MOD-006~015 |
| MOD-006 | LLMService | LLM 与知识层 | 封装 openai SDK 调用 DeepSeek API，提供 analyze_root_cause() 和 fill_template_params() 两个隔离端点 | — |
| MOD-007 | TemplateEngine | LLM 与知识层 | 确定性命令模板拼装引擎，接收 LLM 填充的参数值，使用 Jinja2 渲染 CLI 命令列表 | — |
| MOD-008 | RAGService | LLM 与知识层 | Chroma 向量库管理，执行语义检索，返回匹配的故障案例/预案/模板索引 | — |
| MOD-009 | OutputValidator | LLM 与知识层 | LLM 输出校验层：对 fill_template_params 输出执行 JSON Schema 校验 + CLI 命令黑名单扫描；对 analyze_root_cause 输出执行安全标记 | — |
| MOD-010 | SwitchConfigTool | 工具层 | 交换机配置下发工具（策略模式：MockImpl + TpLinkImpl），LangChain BaseTool 封装 | — |
| MOD-011 | SwitchDiagTool | 工具层 | 交换机诊断命令执行工具（策略模式：MockImpl + TpLinkImpl），LangChain BaseTool 封装 | — |
| MOD-012 | BackupTool | 工具层 | 配置备份与回滚工具（策略模式：MockImpl + TpLinkImpl），LangChain BaseTool 封装 | — |
| MOD-013 | KnowledgeBaseTool | 工具层 | RAG 知识库检索工具，LangChain BaseTool 封装，内部委托给 MOD-008 RAGService | MOD-008 |
| MOD-014 | RiskAssessor | 安全与基础设施层 | 修复方案风险评估，检测高风险操作模式（shutdown/VLAN 删除/重启），设置 need_human_approval 标志 | — |
| MOD-015 | AuditLogger | 安全与基础设施层 | 全链路操作日志与不可篡改审计追踪，追加写入结构化日志文件 | — |
| MOD-016 | ConfigManager | 安全与基础设施层 | 全局配置管理（巡检间隔、超时阈值、重试上限、告警 TTL、日志级别） | — |

---

## 系统分层架构图

```
┌──────────────────────────────────────────────────────────────────────┐
│                        触发层 (Trigger Layer)                         │
│                                                                      │
│  ┌─────────────────────────┐    ┌──────────────────────────────┐    │
│  │   MOD-001                │    │   MOD-002                     │    │
│  │   WebhookReceiver        │    │   InspectionScheduler         │    │
│  │   ─────────────────────  │    │   ─────────────────────────── │    │
│  │   POST /webhook/alert    │    │   APScheduler (interval=5min) │    │
│  │   → RawAlertEvent        │    │   → RawInspectionEvent[]      │    │
│  └───────────┬──────────────┘    └──────────────┬───────────────┘    │
│              │                                  │                     │
└──────────────┼──────────────────────────────────┼─────────────────────┘
               │                                  │
               ▼                                  ▼
┌──────────────────────────────────────────────────────────────────────┐
│                      编排层 (Orchestration Layer)                     │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │   MOD-004: AlertNormalizer                                    │   │
│  │   ───────────────────────────────────                        │   │
│  │   normalize(RawEvent) → Alert (去重 + 时效性检查)              │   │
│  │   → 标准 Alert 对象                                           │   │
│  └───────────────────────────┬──────────────────────────────────┘   │
│                              │                                       │
│                              ▼                                       │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │   MOD-003: StateGraphEngine (LangGraph)                       │   │
│  │   ─────────────────────────────────────────                  │   │
│  │   StateGraph(NetworkAgentState)                               │   │
│  │   Nodes: 14  |  CondEdges: 4  |  Interrupt: human_approval   │   │
│  └───────────────────────────┬──────────────────────────────────┘   │
│                              │                                       │
│                              ▼                                       │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │   MOD-005: NodeHandlers (14 个节点实现函数)                    │   │
│  │   ──────────────────────────────────────────                  │   │
│  │   每个节点函数: fn(NetworkAgentState) → NetworkAgentState      │   │
│  │   调用 MOD-006~015 完成具体业务                               │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                      │
└──────────────┬─────────────────────────────┬─────────────────────────┘
               │                             │
               ▼                             ▼
┌──────────────────────────────┐  ┌────────────────────────────────────┐
│  LLM 与知识层                 │  │  工具层 (Tool Layer)                │
│                              │  │                                    │
│  ┌────────────────────────┐  │  │  ┌──────────────────────────────┐ │
│  │ MOD-006: LLMService    │  │  │  │ MOD-010: SwitchConfigTool    │ │
│  │ openai SDK → DeepSeek  │  │  │  │ ┌──────────────────────────┐ │ │
│  │ analyze_root_cause()   │  │  │  │ │ AbstractSwitchConfigTool │ │ │
│  │ fill_template_params() │  │  │  │ │  ├─ MockConfigImpl       │ │ │
│  └───────────┬────────────┘  │  │  │ │  └─ TpLinkConfigImpl     │ │ │
│              │               │  │  │ └──────────────────────────┘ │ │
│              ▼               │  │  └──────────────────────────────┘ │
│  ┌────────────────────────┐  │  │                                    │
│  │ MOD-009: OutputValidator│  │  │  ┌──────────────────────────────┐ │
│  │ JSON Schema + CLI Scan │  │  │  │ MOD-011: SwitchDiagTool      │ │
│  └────────────────────────┘  │  │  │ ┌──────────────────────────┐ │ │
│                              │  │  │ │ AbstractSwitchDiagTool    │ │ │
│  ┌────────────────────────┐  │  │  │ │  ├─ MockDiagImpl         │ │ │
│  │ MOD-007: TemplateEngine │  │  │  │ │  └─ TpLinkDiagImpl       │ │ │
│  │ Jinja2 模板渲染         │  │  │  │ └──────────────────────────┘ │ │
│  │ render(template, params)│  │  │  └──────────────────────────────┘ │
│  │ → CLI 命令列表          │  │  │                                    │
│  └────────────────────────┘  │  │  ┌──────────────────────────────┐ │
│                              │  │  │ MOD-012: BackupTool          │ │
│  ┌────────────────────────┐  │  │  │ ┌──────────────────────────┐ │ │
│  │ MOD-008: RAGService    │  │  │  │ │ AbstractBackupTool        │ │ │
│  │ Chroma 向量库           │  │  │  │ │  ├─ MockBackupImpl       │ │ │
│  │ 语义检索 + 元数据过滤   │  │  │  │ │  └─ TpLinkBackupImpl     │ │ │
│  └────────────────────────┘  │  │  │ └──────────────────────────┘ │ │
│                              │  │  └──────────────────────────────┘ │
│                              │  │                                    │
│                              │  │  ┌──────────────────────────────┐ │
│                              │  │  │ MOD-013: KnowledgeBaseTool   │ │
│                              │  │  │ LangChain Tool → MOD-008     │ │
│                              │  │  └──────────────────────────────┘ │
│                              │  │                                    │
└──────────────────────────────┘  └────────────────────────────────────┘
               │                             │
               └──────────┬──────────────────┘
                          ▼
┌──────────────────────────────────────────────────────────────────────┐
│                  安全与基础设施层 (Security & Infra Layer)             │
│                                                                      │
│  ┌──────────────────┐  ┌──────────────────┐  ┌───────────────────┐  │
│  │ MOD-014           │  │ MOD-015           │  │ MOD-016            │  │
│  │ RiskAssessor      │  │ AuditLogger       │  │ ConfigManager      │  │
│  │ ────────────────  │  │ ────────────────  │  │ ────────────────   │  │
│  │ assess(fix_plan)  │  │ log(node, state)  │  │ get/set 全局配置   │  │
│  │ → risk_level +    │  │ → 追加写入审计    │  │ 巡检间隔/超时/重试  │  │
│  │   need_approval   │  │    日志文件       │  │ 阈值               │  │
│  └──────────────────┘  └──────────────────┘  └───────────────────┘  │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 模块详情

---

### MOD-001: WebhookReceiver

- **职责**: 通过 FastAPI 暴露 HTTP POST 端点，接收 Mock Zabbix 格式的告警推送，解析请求体并将原始事件传递给 AlertNormalizer。
- **覆盖需求**: REQ-FUNC-001, REQ-FUNC-002, IFC-001
- **关联用户故事**: US-001, US-002, US-003

- **公开接口契约**:
  - **IFC-001-01**: `POST /webhook/alert`
    - 输入: `payload: AlertPayload`（符合 IFC-001 Schema 的 JSON body）
    - 返回: `AlertReceipt { alert_id: str, status: "ACCEPTED" | "DUPLICATE" | "EXPIRED" }`
    - 错误: `HTTP 400`（Schema 校验失败）, `HTTP 503`（内部队列满）

  - **IFC-001-02**: `start_server(host: str, port: int) → None`
    - 启动 FastAPI/Uvicorn 服务

- **依赖模块**: MOD-004 AlertNormalizer（调用 `normalize_webhook_event`）

- **外部依赖**: FastAPI, Uvicorn, Pydantic

- **Demo 策略**: 真实实现。Mock Webhook 推送脚本作为独立工具提供（不属于模块体系）。

---

### MOD-002: InspectionScheduler

- **职责**: 基于 APScheduler 实现定时巡检触发，按可配置间隔对所有纳管设备执行健康检查（通过 SwitchDiagTool 执行诊断命令），检测异常时生成巡检事件并传递给 AlertNormalizer。
- **覆盖需求**: REQ-FUNC-003
- **关联用户故事**: US-004, US-005

- **公开接口契约**:
  - **IFC-002-01**: `start_scheduler(interval_minutes: int, device_list: list[DeviceInfo]) → str`
    - 启动定时巡检，返回 job_id
  - **IFC-002-02**: `stop_scheduler(job_id: str) → None`
    - 停止巡检任务
  - **IFC-002-03**: `run_inspection_once(device_list: list[DeviceInfo]) → list[RawInspectionEvent]`
    - 手动触发一次巡检，返回检测到的异常事件列表

- **依赖模块**:
  - MOD-004 AlertNormalizer（`normalize_inspection_event`）
  - MOD-011 SwitchDiagTool（执行 `show interface`, `show processes cpu` 诊断）
  - MOD-016 ConfigManager（读取巡检间隔/阈值配置）

- **外部依赖**: APScheduler

- **Demo 策略**: 真实实现，间隔默认 5 分钟，通过 ConfigManager 可配置。

---

### MOD-003: StateGraphEngine

- **职责**: 定义并管理 LangGraph StateGraph（14 节点 + 4 条件边 + 1 Interrupt 点），负责状态机实例化、节点路由、条件边决策、Interrupt 检查点保存/恢复、以及调试追踪。
- **覆盖需求**: REQ-FUNC-006, REQ-FUNC-013
- **关联用户故事**: US-001~US-011（全部）

- **公开接口契约**:
  - **IFC-003-01**: `build_graph() → CompiledStateGraph`
    - 构建并编译 StateGraph，返回可执行图对象。定义以下节点和边：

  - **IFC-003-02**: `run_workflow(alert: Alert) → NetworkAgentState`
    - 以标准 Alert 为输入启动状态机，同步执行直到完成或 Interrupt，返回最终 State

  - **IFC-003-03**: `resume_workflow(checkpoint_id: str, approval_decision: ApprovalDecision) → NetworkAgentState`
    - 从 Interrupt 检查点恢复执行，传入审批决定（APPROVED/REJECTED）

  - **IFC-003-04**: `get_pending_approvals() → list[PendingApproval]`
    - 查询所有处于 Interrupt 挂起状态的审批项列表

  - **IFC-003-05**: `get_workflow_state(checkpoint_id: str) → NetworkAgentState | None`
    - 查询指定检查点的当前 State 快照

- **StateGraph 节点定义（14 个）**:

| 序号 | 节点名称 | NodeHandler 函数 | 说明 |
|------|---------|-----------------|------|
| 1 | `receive_alert` | `handle_receive_alert` | 接收标准 Alert 对象，初始化 State |
| 2 | `parse_alert` | `handle_parse_alert` | 解析告警字段，填充 alert_type/content/device_info |
| 3 | `validate_alert` | `handle_validate_alert` | 告警去重 + 时效性检查，设置 is_valid 标志 |
| 4 | `get_device_info` | `handle_get_device_info` | 查询设备信息库，获取 IP/型号/凭据 |
| 5 | `establish_ssh` | `handle_establish_ssh` | 建立 SSH 连接（Mock 阶段验证凭据格式） |
| 6 | `collect_diag` | `handle_collect_diag` | 调用 SwitchDiagTool 执行诊断命令，写入 diag_result |
| 7 | `analyze_root_cause` | `handle_analyze_root_cause` | 调用 LLMService + RAGService 分析根因 |
| 8 | `generate_fix_plan` | `handle_generate_fix_plan` | 模板匹配 + LLM 参数填充 + TemplateEngine 拼装 |
| 9 | `assess_risk` | `handle_assess_risk` | 调用 RiskAssessor 评估风险等级 |
| 10 | `human_approval` | `handle_human_approval` | Interrupt 挂起点，等待/接收审批决定 |
| 11 | `backup_config` | `handle_backup_config` | 调用 BackupTool 备份 running-config |
| 12 | `execute_fix` | `handle_execute_fix` | 调用 SwitchConfigTool 下发修复命令 |
| 13 | `verify_result` | `handle_verify_result` | 重新诊断，对比修复前后状态 |
| 14 | `final_report` | `handle_final_report` | 调用 LLM 生成处理报告，设置 status=CLOSED |

- **条件边定义（4 个）**:

| 条件边 | 来源节点 | 条件函数 | 路径 |
|--------|---------|---------|------|
| CE-001 | `validate_alert` | `route_after_validate` | `is_valid=true` → `get_device_info`; `false` → `final_report` |
| CE-002 | `assess_risk` | `route_after_risk` | `need_human_approval=true` → `human_approval`; `false` → `backup_config` |
| CE-003 | `backup_config` | `route_after_backup` | `backup_success=true` → `execute_fix`; `false` → `final_report` |
| CE-004 | `verify_result` | `route_after_verify` | `verify_passed=true` → `final_report`; `false` → `execute_fix`（先回滚再标记失败） |

- **Interrupt 配置**: `interrupt_before=["human_approval"]`，在进入 human_approval 节点前挂起，等待外部 `resume_workflow()` 调用。

- **依赖模块**: MOD-005 NodeHandlers（所有节点实现函数）

- **外部依赖**: LangGraph, LangChain

- **Demo 策略**: 真实实现，完整 14 节点 + Interrupt。

---

### MOD-004: AlertNormalizer

- **职责**: 将来自 Webhook 和巡检的原始事件归一化为统一的 `Alert` 对象，并执行去重（基于 alert_id 或 device+type 组合）和时效性检查（超过 TTL 的旧告警标记为过期）。
- **覆盖需求**: REQ-FUNC-001, REQ-FUNC-003, REQ-FUNC-004, REQ-FUNC-005
- **关联用户故事**: US-001, US-002, US-003, US-004, US-005

- **公开接口契约**:
  - **IFC-004-01**: `normalize_webhook_event(payload: AlertPayload) → Alert | None`
    - 输入: IFC-001 Schema 的 JSON Payload（Pydantic 校验）
    - 返回: 归一化的标准 Alert 对象，若去重或过期则返回 None
  - **IFC-004-02**: `normalize_inspection_event(event: RawInspectionEvent) → Alert | None`
    - 输入: 巡检检测到的异常事件
    - 返回: 归一化的标准 Alert 对象，source 字段标记为 `INSPECTION`
  - **IFC-004-03**: `is_duplicate(alert: Alert) → bool`
    - 检查告警是否已在近期处理中或已处理完成（缓存 100 条，TTL=15 min）

- **Alert 数据结构**:
  ```
  Alert {
    alert_id: str (UUID)
    alert_type: "MAC_FLAPPING" | "PORT_DOWN" | "CPU_HIGH"
    alert_severity: "CRITICAL" | "MAJOR" | "MINOR" | "WARNING"
    alert_content: str
    alert_timestamp: datetime (ISO8601)
    device_info: DeviceInfo {
      device_name: str
      device_ip: str
      device_model: str | None
      interface_name: str | None
      mac_address: str | None
      cpu_percent: float | None
    }
    source: "ZABBIX" | "MOCK" | "INSPECTION"
  }
  ```

- **依赖模块**: 无（最底层模块）

- **外部依赖**: Pydantic

- **Demo 策略**: 真实实现。去重缓存使用内存 dict + TTL（Python `cachetools.TTLCache`）。

---

### MOD-005: NodeHandlers

- **职责**: 实现 LangGraph 全部 14 个节点的处理函数，每个函数接收 `NetworkAgentState` 并返回更新后的 `NetworkAgentState`。作为编排层的业务逻辑承载者，协调调用下层模块（LLMService、TemplateEngine、RAGService、各 Tool 模块、RiskAssessor、AuditLogger）。
- **覆盖需求**: REQ-FUNC-005 ~ REQ-FUNC-016, REQ-FUNC-023 ~ REQ-FUNC-025
- **关联用户故事**: US-001~US-009, US-011

- **公开接口契约**:
  - **IFC-005-01** ~ **IFC-005-14**: 14 个节点处理函数，统一签名为 `(state: NetworkAgentState) → dict[str, Any]`（返回 State 的部分更新字段）。

  核心节点函数签名：

  - **IFC-005-06**: `handle_collect_diag(state: NetworkAgentState) → dict`
    - 调用 MOD-011 SwitchDiagTool 执行诊断命令
    - 根据 `alert_type` 选择命令: MAC_FLAPPING → `show mac address-table`; PORT_DOWN → `show interface {iface}`; CPU_HIGH → `show processes cpu`
    - 写入 `diag_result: str`

  - **IFC-005-07**: `handle_analyze_root_cause(state: NetworkAgentState) → dict`
    - 调用 MOD-006 LLMService.analyze_root_cause(alert_content, diag_result)
    - 调用 MOD-008 RAGService.search(diag_result, alert_type) 获取 knowledge_refs
    - 写入 `root_cause: str` 和 `knowledge_refs: list[KnowledgeRef]`

  - **IFC-005-08**: `handle_generate_fix_plan(state: NetworkAgentState) → dict`
    - 从 RAG 检索结果中匹配命令模板
    - 调用 MOD-006 LLMService.fill_template_params(template, root_cause, diag_result)
    - 调用 MOD-009 OutputValidator.validate_params(params, template)
    - 调用 MOD-007 TemplateEngine.render(template, validated_params) → CLI 命令列表
    - 写入 `fix_plan: FixPlan { template_id, params, commands, risk_hints }`

  - **IFC-005-09**: `handle_assess_risk(state: NetworkAgentState) → dict`
    - 调用 MOD-014 RiskAssessor.assess(fix_plan)
    - 写入 `need_human_approval: bool` 和 `risk_level: str`

  - **IFC-005-10**: `handle_human_approval(state: NetworkAgentState) → dict`
    - Interrupt 挂起点，由 LangGraph 框架处理
    - 恢复后写入 `approval_status: "APPROVED" | "REJECTED"`

  - **IFC-005-11**: `handle_backup_config(state: NetworkAgentState) → dict`
    - 调用 MOD-012 BackupTool.backup(device_ip, auth)
    - 写入 `config_backup: str`

  - **IFC-005-12**: `handle_execute_fix(state: NetworkAgentState) → dict`
    - 调用 MOD-010 SwitchConfigTool.configure(device_ip, commands, auth)
    - 逐条执行前做幂等检查（当前状态是否已是目标状态）
    - 写入 `exec_log: list[ExecRecord]`

  - **IFC-005-13**: `handle_verify_result(state: NetworkAgentState) → dict`
    - 调用 MOD-011 SwitchDiagTool 重新执行诊断
    - 对比修复前后状态变化
    - 写入 `verify_result: VerifyResult`

- **依赖模块**: MOD-006, MOD-007, MOD-008, MOD-009, MOD-010, MOD-011, MOD-012, MOD-013, MOD-014, MOD-015

- **外部依赖**: 无（纯协调层）

- **Demo 策略**: 真实实现，所有 14 个节点函数完整实现。

---

### MOD-006: LLMService

- **职责**: 封装 openai Python SDK，提供两个隔离的 LLM 调用端点。管理 Prompt 模板、API 密钥、重试逻辑和调用日志。严格遵守 `temperature=0.1`、`model=deepseek-chat`、`base_url=https://api.deepseek.com/v1` 的约束。
- **覆盖需求**: REQ-FUNC-010, REQ-FUNC-011, REQ-NFUNC-013
- **关联用户故事**: US-008, US-011

- **公开接口契约**:
  - **IFC-006-01**: `analyze_root_cause(alert_content: str, diag_result: str) → RootCauseResult`
    - 端点: 根因分析（自由推理）
    - Prompt: 包含告警内容 + 诊断数据 + 输出格式约束（Markdown 结构化）
    - 返回: `RootCauseResult { description: str, possible_causes: list[str], suggested_direction: str }`
    - temperature: 0.1

  - **IFC-006-02**: `fill_template_params(template_id: str, template_description: str, root_cause: str, diag_result: str, device_info: DeviceInfo) → TemplateParams`
    - 端点: 模板参数填充（严格约束）
    - Prompt: 要求输出纯 JSON，仅包含模板参数键值对
    - 返回: `TemplateParams { params: dict[str, str|int|float] }`（原始 JSON 字符串由 MOD-009 校验后解析）
    - temperature: 0.1

  - **IFC-006-03**: `generate_report(alert_id: str, root_cause: str, fix_plan: FixPlan, exec_log: list[ExecRecord], verify_result: VerifyResult) → str`
    - 端点: 报告生成
    - 返回: Markdown 格式的最终处理报告

- **内部约束**:
  - SDK: `openai.OpenAI(base_url="https://api.deepseek.com/v1", api_key=os.environ["DEEPSEEK_API_KEY"])`
  - 每次调用记录: 时间戳、endpoint、输入长度、输出长度、耗时、token 用量
  - 失败重试: 最多 3 次，指数退避（1s, 2s, 4s）

- **依赖模块**: 无

- **外部依赖**: openai Python SDK, DeepSeek API

- **Demo 策略**: 真实 API 调用。

---

### MOD-007: TemplateEngine

- **职责**: 确定性命令模板拼装引擎。接收 LLM 填充并经 OutputValidator 校验的参数值，使用 Jinja2 模板引擎将参数渲染为目标交换机的 CLI 命令列表。**完全不含任何 LLM 代码**，100% 确定性执行。
- **覆盖需求**: REQ-FUNC-011, REQ-FUNC-021, REQ-NFUNC-001, REQ-NFUNC-002
- **关联用户故事**: US-011

- **公开接口契约**:
  - **IFC-007-01**: `render(template_id: str, params: dict[str, Any]) → list[str]`
    - 输入: 模板 ID + 校验后的参数字典
    - 输出: CLI 命令列表，如 `["interface Gi0/1", "no shutdown", "description Auto-recovered by Agent"]`
    - 错误: `TemplateNotFoundError`（模板 ID 不存在）, `ParamMissingError`（必需参数缺失）

  - **IFC-007-02**: `list_templates(alert_type: str | None) → list[TemplateMeta]`
    - 列出指定告警类型关联的所有模板元数据（ID, 描述, 参数列表, 风险等级）

  - **IFC-007-03**: `get_template(template_id: str) → TemplateDefinition`
    - 获取模板完整定义（Jinja2 模板字符串 + 参数 Schema + 风险标注）

- **模板示例（TP-Link Cisco IOS 风格）**:

  模板 ID: `TPL-PORT-ENABLE`
  ```
  interface {{ iface_name }}
   no shutdown
   description {{ desc }}
  ```

  模板 ID: `TPL-MAC-PORT-SECURITY`
  ```
  interface {{ iface_name }}
   switchport port-security
   switchport port-security maximum {{ max_mac }}
   switchport port-security violation {{ violation_mode }}
  ```

- **依赖模块**: 无

- **外部依赖**: Jinja2

- **Demo 策略**: 真实实现，模板存储在 `resources/templates/` 目录下的 JSON/YAML 文件中。

---

### MOD-008: RAGService

- **职责**: Chroma 向量数据库管理，包括文档嵌入、索引持久化、语义检索和元数据过滤。存储故障案例、处理预案和命令模板索引作为可检索的知识条目。
- **覆盖需求**: REQ-FUNC-019, REQ-FUNC-021, REQ-FUNC-022
- **关联用户故事**: US-008

- **公开接口契约**:
  - **IFC-008-01**: `search(query: str, alert_type: str, top_k: int = 5) → list[KnowledgeRef]`
    - 语义搜索 + 元数据过滤（where={"alert_type": alert_type}）
    - 相似度阈值过滤（默认 ≥ 0.6）
    - 返回: `KnowledgeRef { doc_id, title, content, relevance_score, template_id }`

  - **IFC-008-02**: `index_documents(documents: list[KnowledgeDocument]) → int`
    - 将知识文档向量化并写入 Chroma 索引
    - 返回成功索引的文档数

  - **IFC-008-03**: `get_template_by_id(template_id: str) → KnowledgeDocument | None`
    - 通过模板 ID 精确查找命令模板文档

- **Chroma 配置**:
  - 持久化路径: `./data/chroma_db/`
  - 集合名称: `network_knowledge`
  - 嵌入模型: `text-embedding-3-small`（通过 openai SDK）
  - 元数据字段: `alert_type`, `doc_type`（"case" | "plan" | "template"）, `template_id`

- **依赖模块**: 无

- **外部依赖**: Chroma, langchain-chroma, openai SDK（embedding）

- **Demo 策略**: Mock 实现（内嵌 3 种告警类型的示例知识条目，~10 条文档），但 Chroma 真实运行。嵌入模型使用真实 API 调用。

---

### MOD-009: OutputValidator

- **职责**: LLM 输出安全校验层。对 `fill_template_params` 端点输出执行 JSON Schema 严格校验 + CLI 命令黑名单正则扫描。对 `analyze_root_cause` 端点的输出执行安全标记。**任何校验失败的 LLM 输出不得进入执行层**。
- **覆盖需求**: REQ-NFUNC-001, REQ-NFUNC-002
- **关联用户故事**: US-008 AC-008-05, US-011 AC-011-02

- **公开接口契约**:
  - **IFC-009-01**: `validate_params(raw_output: str, template_params_schema: dict) → dict[str, Any]`
    - 步骤 1: 尝试解析为 JSON，失败则 `raise ValidationError("LLM output is not valid JSON")`
    - 步骤 2: JSON Schema 校验（每个 key 必须在 template_params_schema 中定义，value 类型必须匹配）
    - 步骤 3: CLI 命令黑名单扫描（对每个 string 类型的参数值做正则匹配，检测是否包含 `interface`, `shutdown`, `no shutdown`, `vlan`, `reload`, `configure`, `router`, `switchport` 等命令关键词）
    - 步骤 4: 通过则返回纯净的参数字典
    - 安全告警: 若步骤 3 命中，记录 `SECURITY_ALERT: LLM attempted to inject CLI command in parameter` 到 MOD-015 AuditLogger

  - **IFC-009-02**: `sanitize_root_cause(raw_output: str) → str`
    - 对根因分析输出做安全标记（在输出末尾追加 `[SECURITY: This analysis was generated by LLM, review before acting]`）
    - 检测是否包含 CLI 命令片段，若包含则标记为 `SECURITY_WARNING` 但不拒绝（根因分析中引用诊断命令是合理的）
    - 返回净化后的文本

- **CLI 命令黑名单正则（非穷举，核心模式）**:
  ```
  (interface\s+\S+|shutdown|no\s+shutdown|switchport|vlan\s+\d+|reload|configure\s+terminal|router\s+\w+|spanning-tree|write\s+memory|copy\s+running)
  ```

- **依赖模块**: MOD-015 AuditLogger（记录安全告警）

- **外部依赖**: jsonschema (Python)

- **Demo 策略**: 真实实现。

---

### MOD-010: SwitchConfigTool

- **职责**: 交换机配置下发工具，封装为 LangChain BaseTool。采用策略模式，提供 Mock 和 TP-Link 两种实现，共享相同接口签名。
- **覆盖需求**: REQ-FUNC-014, REQ-FUNC-017, REQ-NFUNC-014
- **关联用户故事**: US-006, US-007

- **公开接口契约**:

  **抽象基类**:
  ```python
  class AbstractSwitchConfigTool(BaseTool):
      name = "switch_config"
      description = "Execute configuration commands on network switch"

      @abstractmethod
      def _run(self, device_ip: str, commands: list[str], auth: DeviceAuth) -> ConfigResult:
          """Execute configuration commands and return result."""
  ```

  - **IFC-010-01**: `configure(device_ip: str, commands: list[str], auth: DeviceAuth) → ConfigResult`
    - 输入: device_ip（目标设备 IP）、commands（CLI 命令列表，每条一行）、auth（凭据）
    - 返回: `ConfigResult { success: bool, output: str, error: str | None, commands_executed: int, commands_failed: int }`

  **Mock 实现（DEMO）**: `MockSwitchConfigTool`
  - 不真实连接交换机
  - 返回模拟执行结果（所有命令 success=true）
  - 模拟延迟 0.5s/条命令

  **TP-Link 实现（预留）**: `TpLinkSwitchConfigTool`
  - 通过 Netmiko SSH 连接 TP-Link 交换机
  - 使用 NAPALM 管理配置会话（merge/commit/discard）
  - TP-Link Cisco IOS 风格命令兼容（直接下发）

- **依赖模块**: 无

- **外部依赖**: LangChain BaseTool, Netmiko（TpLink 实现）, NAPALM（TpLink 实现）

- **Demo 策略**: Mock 实现（MockSwitchConfigTool），TpLinkSwitchConfigTool 接口预留待后续阶段启用。

---

### MOD-011: SwitchDiagTool

- **职责**: 交换机诊断命令执行工具，封装为 LangChain BaseTool。采用策略模式，提供 Mock（返回模拟诊断数据）和 TP-Link（真实 SSH 执行）两种实现。
- **覆盖需求**: REQ-FUNC-008, REQ-FUNC-009, REQ-FUNC-018, REQ-NFUNC-014
- **关联用户故事**: US-001, US-002, US-003, US-004, US-005

- **公开接口契约**:

  **抽象基类**:
  ```python
  class AbstractSwitchDiagTool(BaseTool):
      name = "switch_diag"
      description = "Execute diagnostic commands on network switch and return output"

      @abstractmethod
      def _run(self, device_ip: str, command: str, auth: DeviceAuth) -> DiagResult:
          """Execute a diagnostic command and return structured output."""
  ```

  - **IFC-011-01**: `diagnose(device_ip: str, command: str, auth: DeviceAuth) → DiagResult`
    - 输入: device_ip（目标设备 IP）、command（单条 show 命令）、auth（凭据）
    - 返回: `DiagResult { success: bool, output: str, error: str | None, execution_time_ms: int }`

  **Mock 实现（DEMO）**: `MockSwitchDiagTool`
  - 根据 `command` 和 `alert_type` 返回预定义的模拟诊断数据
  - MAC_FLAPPING + `show mac address-table` → 返回模拟 MAC 表（含漂移信息）
  - PORT_DOWN + `show interface Gi0/1` → 返回模拟接口状态
  - CPU_HIGH + `show processes cpu` → 返回模拟进程列表

  **TP-Link 实现（预留）**: `TpLinkSwitchDiagTool`
  - 通过 Netmiko SSH 连接执行 `show` 命令
  - 原始输出解析为结构化数据

- **依赖模块**: 无

- **外部依赖**: LangChain BaseTool, Netmiko（TpLink 实现）

- **Demo 策略**: Mock 实现（MockSwitchDiagTool），TpLinkSwitchDiagTool 接口预留。

---

### MOD-012: BackupTool

- **职责**: 配置备份与回滚工具，封装为 LangChain BaseTool。采用策略模式，提供 Mock 和 TP-Link 两种实现。支持 BACKUP（拉取 running-config 快照）和 ROLLBACK（基于备份配置恢复设备）。
- **覆盖需求**: REQ-FUNC-020, REQ-NFUNC-005, REQ-NFUNC-006
- **关联用户故事**: US-009

- **公开接口契约**:

  **抽象基类**:
  ```python
  class AbstractBackupTool(BaseTool):
      name = "config_backup"
      description = "Backup or rollback device running configuration"

      @abstractmethod
      def _run(self, device_ip: str, auth: DeviceAuth, operation: str, backup_id: str | None = None) -> BackupResult:
          """Perform backup or rollback operation."""
  ```

  - **IFC-012-01**: `backup(device_ip: str, auth: DeviceAuth) → BackupResult`
    - 输入: device_ip、auth
    - 返回: `BackupResult { success: bool, backup_id: str (UUID), config: str | None, error: str | None }`

  - **IFC-012-02**: `rollback(device_ip: str, backup_id: str, auth: DeviceAuth) → RollbackResult`
    - 输入: device_ip、backup_id、auth
    - 返回: `RollbackResult { success: bool, output: str, error: str | None }`

  **Mock 实现（DEMO）**: `MockBackupTool`
  - backup: 返回模拟 running-config 文本和 UUID
  - rollback: 返回 success（模拟回滚成功）

  **TP-Link 实现（预留）**: `TpLinkBackupTool`
  - backup: SSH 执行 `show running-config`，保存完整输出
  - rollback: 将备份配置通过 SSH 逐行写回设备

- **依赖模块**: 无

- **外部依赖**: LangChain BaseTool, Netmiko（TpLink 实现）

- **Demo 策略**: Mock 实现（MockBackupTool），TpLinkBackupTool 接口预留。

---

### MOD-013: KnowledgeBaseTool

- **职责**: RAG 知识库检索工具，封装为 LangChain BaseTool。接收查询和告警类型，委托给 MOD-008 RAGService 执行语义检索，返回匹配的知识条目。
- **覆盖需求**: REQ-FUNC-019
- **关联用户故事**: US-008

- **公开接口契约**:
  - **IFC-013-01**: `search(query: str, alert_type: str, top_k: int = 5) → KnowledgeBaseResult`
    - 输入: query（自然语言检索描述）、alert_type（元数据过滤）、top_k
    - 返回: `KnowledgeBaseResult { matches: list[KnowledgeRef], count: int }`
    - 其中 `KnowledgeRef { doc_id: str, title: str, content: str, relevance: float, template_id: str | None }`

- **依赖模块**: MOD-008 RAGService（委托调用 `RAGService.search()`）

- **外部依赖**: LangChain BaseTool

- **Demo 策略**: Mock 实现（内嵌静态知识条目），但内部调用 MOD-008 RAGService 的真实 Chroma 检索。

---

### MOD-014: RiskAssessor

- **职责**: 修复方案风险评估引擎。接收 FixPlan，检查其中包含的命令模式是否匹配高风险操作（端口 shutdown/VLAN 删除/设备重启/路由变更），设置风险等级和是否需要人工审批。
- **覆盖需求**: REQ-FUNC-012, REQ-NFUNC-003
- **关联用户故事**: US-006

- **公开接口契约**:
  - **IFC-014-01**: `assess(fix_plan: FixPlan) → RiskAssessment`
    - 输入: FixPlan（包含 template_id, params, commands）
    - 返回: `RiskAssessment { risk_level: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL", need_human_approval: bool, risk_reasons: list[str], matched_high_risk_patterns: list[str] }`

- **高风险操作模式（强制匹配规则）**:

| 模式 | 风险等级 | 触发阈值 |
|------|---------|---------|
| 端口 shutdown / no shutdown | HIGH | 1 条 |
| VLAN 删除（`no vlan`） | CRITICAL | 1 条 |
| 设备重启（`reload` / `reboot`） | CRITICAL | 1 条 |
| 路由协议变更（`router ospf` / `router bgp`） | HIGH | 1 条 |
| spanning-tree 修改 | MEDIUM | 1 条 |
| 配置写存（`write memory` / `copy running`） | LOW | 任意 |

- **need_human_approval 判定规则**:
  - `risk_level in ["HIGH", "CRITICAL"]` → need_human_approval = true (REQ-NFUNC-003)
  - `risk_level == "MEDIUM"` 且包含多条修改命令 → need_human_approval = true
  - `risk_level == "LOW"` → need_human_approval = false

- **依赖模块**: 无

- **外部依赖**: 无（纯规则匹配）

- **Demo 策略**: 真实实现。

---

### MOD-015: AuditLogger

- **职责**: 全链路操作日志与不可篡改审计追踪。每个节点执行前后记录状态快照、时间戳、执行结果。关键操作（配置下发、人工审批）生成不可篡改的审计记录（追加写入日志文件）。
- **覆盖需求**: REQ-NFUNC-010, REQ-NFUNC-011
- **关联用户故事**: US-010

- **公开接口契约**:
  - **IFC-015-01**: `log_node_execution(alert_id: str, node_name: str, phase: "START" | "END", state_summary: dict, duration_ms: int | None = None) → None`
    - 记录节点执行事件
    - 日志格式: `{timestamp} | {alert_id} | {node_name} | {phase} | {state_summary_json} | duration={duration_ms}ms`

  - **IFC-015-02**: `log_audit_event(event_type: str, alert_id: str, operator: str, action: str, detail: dict) → str`
    - 记录不可篡改审计事件
    - 返回: audit_record_id（用于后续检索）
    - 审计类型: `CONFIG_CHANGE`, `APPROVAL_DECISION`, `ROLLBACK`, `SECURITY_ALERT`

  - **IFC-015-03**: `query_by_alert_id(alert_id: str) → list[AuditRecord]`
    - 按告警 ID 查询全链路审计记录

  - **IFC-015-04**: `get_pending_approvals() → list[PendingApproval]`
    - 查询所有审批挂起中的记录（供 MOD-003 的 `get_pending_approvals()` 委托调用）

- **日志文件路径**:
  - 操作日志: `./logs/operations_{date}.log`
  - 审计日志: `./logs/audit.log`（永久追加，不可删除）

- **依赖模块**: 无

- **外部依赖**: loguru

- **Demo 策略**: 真实实现。使用 loguru 结构化日志 + 文件追加写入。

---

### MOD-016: ConfigManager

- **职责**: 全局配置管理，提供运行时配置的读取和动态更新。管理巡检间隔、诊断超时、重试上限、告警 TTL、日志级别等参数。
- **覆盖需求**: REQ-NFUNC-004, REQ-NFUNC-007, REQ-NFUNC-012
- **关联用户故事**: 基础设施

- **公开接口契约**:
  - **IFC-016-01**: `get(key: str) → Any`
    - 读取配置值，支持点号分隔的嵌套 key（如 `"inspection.interval_minutes"`）

  - **IFC-016-02**: `set(key: str, value: Any) → None`
    - 动态更新配置值（运行时生效）

  - **IFC-016-03**: `load_config(file_path: str) → None`
    - 从配置文件加载（YAML/JSON 格式）

  - **IFC-016-04**: `get_device_credentials(device_name: str) → DeviceAuth | None`
    - 查询设备凭据（满足 REQ-NFUNC-004 最小权限账号）

- **默认配置项**:

| 配置键 | 默认值 | 说明 |
|--------|--------|------|
| `inspection.interval_minutes` | 5 | 巡检间隔（Q-001，可配置） |
| `diagnosis.timeout_seconds` | 30 | 诊断命令超时（REQ-NFUNC-014） |
| `diagnosis.retry_max` | 3 | 命令重试上限（REQ-NFUNC-007） |
| `diagnosis.retry_backoff_base` | 1.0 | 重试退避基数（秒） |
| `alert.ttl_minutes` | 15 | 告警去重 TTL |
| `alert.dedup_cache_size` | 100 | 去重缓存最大条数 |
| `rag.similarity_threshold` | 0.6 | RAG 相似度过滤阈值 |
| `logging.level` | INFO | 日志级别 |
| `logging.audit_enabled` | true | 审计日志开关 |

- **依赖模块**: 无

- **外部依赖**: PyYAML

- **Demo 策略**: 真实实现。配置文件存储在 `config/config.yaml`。

---

## 数据流图: NetworkAgentState 在节点间的传递路径

```
                        ┌──────────────────┐
                        │  AlertNormalizer  │
                        │  (MOD-004)        │
                        │  → 标准 Alert 对象 │
                        └────────┬─────────┘
                                 │
                                 ▼
┌──────────────────────────────────────────────────────────────────────┐
│                     NetworkAgentState (TypedDict)                     │
│                                                                      │
│  ┌─────────────┐   ┌──────────────┐   ┌────────────────┐            │
│  │ alert_id    │   │ alert_type   │   │ alert_content  │            │
│  │ device_info │   │ diag_commands│   │ diag_result    │            │
│  │ root_cause  │   │ knowledge_   │   │ fix_plan       │            │
│  │             │   │ refs         │   │                │            │
│  │ need_human_ │   │ approval_    │   │ exec_log       │            │
│  │ approval    │   │ status       │   │                │            │
│  │ config_     │   │ verify_      │   │ final_report   │            │
│  │ backup      │   │ result       │   │                │            │
│  │ status      │   │              │   │                │            │
│  └─────────────┘   └──────────────┘   └────────────────┘            │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
    ┌─────────────────────────────────────────────────────────────┐
    │                    节点数据流                                 │
    │                                                              │
    │  receive_alert → parse_alert → validate_alert               │
    │       │              │              │                        │
    │       ▼              ▼              ▼                        │
    │  alert_id       alert_type      is_valid (bool)              │
    │  (空→填充)      alert_content   (新增)                       │
    │                 device_info                                  │
    │       │              │              │                        │
    │       └──────────────┴──────────────┘                        │
    │                     │                                        │
    │        ┌────────────┴────────────┐                           │
    │        │  is_valid=True          │  is_valid=False           │
    │        ▼                         ▼                           │
    │  get_device_info            final_report                     │
    │       │                    (status=EXPIRED)                  │
    │  device_info 补全                                              │
    │       │                                                      │
    │  establish_ssh → collect_diag → analyze_root_cause          │
    │       │              │                │                      │
    │  (ssh_session)   diag_result    root_cause                   │
    │  (Mock: 无)      (填充)         knowledge_refs               │
    │                                                              │
    │  generate_fix_plan → assess_risk                            │
    │       │                   │                                  │
    │  fix_plan             need_human_approval                    │
    │  (commands)           risk_level                             │
    │       │                   │                                  │
    │       │    ┌──────────────┴──────────────┐                   │
    │       │    │ need_approval=true          │ need=false        │
    │       │    ▼                             ▼                   │
    │       │  human_approval              backup_config           │
    │       │  (INTERRUPT)                     │                   │
    │       │  approval_status           config_backup            │
    │       │       │                        │                    │
    │       │       ├── APPROVED ────────────┘                    │
    │       │       ├── REJECTED → final_report (REJECTED)        │
    │       │       │                                              │
    │       └───────┴──────────→ execute_fix                      │
    │                                │                             │
    │                           exec_log                           │
    │                                │                             │
    │                          verify_result                       │
    │                                │                             │
    │                    ┌───────────┴──────────┐                  │
    │                    │ verify_passed=true    │ false            │
    │                    ▼                       ▼                  │
    │              final_report            rollback                 │
    │              status=CLOSED           + final_report           │
    │                                      status=FAILED            │
    └─────────────────────────────────────────────────────────────┘
```

### State 字段的生命周期

| State 字段 | 写入节点 | 读取节点 | 类型 |
|-----------|---------|---------|------|
| `alert_id` | receive_alert | 全部 | str (UUID) |
| `alert_type` | parse_alert | collect_diag, analyze_root_cause, generate_fix_plan, final_report | enum |
| `alert_content` | parse_alert | analyze_root_cause, final_report | str |
| `device_info` | parse_alert, get_device_info | establish_ssh, collect_diag, execute_fix, backup_config | DeviceInfo |
| `diag_commands` | collect_diag | — | list[str] |
| `diag_result` | collect_diag | analyze_root_cause, generate_fix_plan, final_report | str |
| `root_cause` | analyze_root_cause | generate_fix_plan, final_report | str |
| `knowledge_refs` | analyze_root_cause | generate_fix_plan, final_report | list[KnowledgeRef] |
| `fix_plan` | generate_fix_plan | assess_risk, human_approval, execute_fix, final_report | FixPlan |
| `need_human_approval` | assess_risk | CE-002 | bool |
| `risk_level` | assess_risk | human_approval, final_report | str |
| `approval_status` | human_approval | CE-after-approval | enum (PENDING/APPROVED/REJECTED) |
| `exec_log` | execute_fix, rollback | verify_result, final_report | list[ExecRecord] |
| `config_backup` | backup_config | rollback, final_report | str |
| `verify_result` | verify_result | CE-004, final_report | VerifyResult |
| `final_report` | final_report | — | str |
| `status` | final_report | — | enum (ACTIVE/CLOSED/FAILED/REJECTED/EXPIRED) |

---

## 模块间调用时序图

### 时序图 1: MAC 地址漂移完整闭环（被动 Webhook 触发）

```
MOD-001          MOD-004         MOD-003          MOD-005          MOD-006       MOD-007     MOD-008/013    MOD-011        MOD-014      MOD-010        MOD-012        MOD-015
WebhookReceiver AlertNormalizer StateGraphEngine NodeHandlers     LLMService  TemplateEngine RAGService   SwitchDiagTool RiskAssessor SwitchConfigTool BackupTool   AuditLogger
    │                │               │                │                │            │            │              │             │             │              │
    │ POST /webhook  │               │                │                │            │            │              │             │             │              │
    │ with Zabbix    │               │                │                │            │            │              │             │             │              │
    │ payload        │               │                │                │            │            │              │             │             │              │
    │───────────────>│               │                │                │            │            │              │             │             │              │
    │                │ normalize()   │                │                │            │            │              │             │             │              │
    │                │ dedup check   │                │                │            │            │              │             │             │              │
    │                │──────────────>│                │                │            │            │              │             │             │              │
    │   ACCEPTED     │               │ run_workflow() │                │            │            │              │             │             │              │
    │<───────────────│               │──────────────>│                │            │            │              │             │             │              │
    │                │               │  (nodes 1-3)   │                │            │            │              │             │             │              │
    │                │               │  parse_alert   │                │            │            │              │             │             │              │
    │                │               │  validate_alert│                │            │            │              │             │             │              │
    │                │               │                │                │            │            │              │             │             │              │
    │                │               │                │ get_device_info│            │            │              │             │             │              │
    │                │               │                │ (from CMDB)    │            │            │              │             │             │              │
    │                │               │                │                │            │            │              │             │             │              │
    │                │               │                │ establish_ssh  │            │            │              │             │             │              │
    │                │               │                │ (Mock: 格式校验)│            │            │              │             │             │              │
    │                │               │                │                │            │            │              │             │             │              │
    │                │               │                │ collect_diag ─────────────────────────────────>│              │             │             │              │
    │                │               │                │                │            │            │diagnose()    │             │             │              │
    │                │               │                │                │            │            │"show mac     │             │             │              │
    │                │               │                │                │            │            │address-table"│             │             │              │
    │                │               │                │ diag_result <─────────────────────────────────│              │             │             │              │
    │                │               │                │ (MAC漂移数据)   │            │            │              │             │             │              │
    │                │               │                │                │            │            │              │             │             │              │
    │                │               │                │ analyze_root_cause                           │              │             │             │              │
    │                │               │                │──────────────>│            │            │              │             │             │              │
    │                │               │                │ analyze()     │            │            │              │             │             │              │
    │                │               │                │<──────────────│            │            │              │             │             │              │
    │                │               │                │ root_cause    │            │            │              │             │             │              │
    │                │               │                │               │            │            │              │             │             │              │
    │                │               │                │────────────────────────────────────────────>│              │             │             │              │
    │                │               │                │ RAG search()  │            │            │search()      │             │             │              │
    │                │               │                │<────────────────────────────────────────────│              │             │             │              │
    │                │               │                │ knowledge_refs│            │            │              │             │             │              │
    │                │               │                │               │            │            │              │             │             │              │
    │                │               │                │ generate_fix_plan                           │              │             │             │              │
    │                │               │                │──────────────>│            │            │              │             │             │              │
    │                │               │                │ fill_params() │            │            │              │             │             │              │
    │                │               │                │<──────────────│            │            │              │             │             │              │
    │                │               │                │ params JSON   │            │            │              │             │             │              │
    │                │               │                │               │            │            │              │             │             │              │
    │                │               │                │───────────────────────────>│            │              │             │             │              │
    │                │               │                │ render(template, params)   │            │              │             │             │              │
    │                │               │                │<───────────────────────────│            │              │             │             │              │
    │                │               │                │ CLI commands  │            │            │              │             │             │              │
    │                │               │                │               │            │            │              │             │             │              │
    │                │               │                │ assess_risk ──────────────────────────────────────────────────────>│             │              │
    │                │               │                │<────────────────────────────────────────────────────────────────────│             │              │
    │                │               │                │ need_human_approval=true, risk_level=HIGH                          │             │              │
    │                │               │                │                │            │            │              │             │             │              │
    │                │               │  ┌─ INTERRUPT ─┐               │            │            │              │             │             │              │
    │                │               │  │ 等待审批...  │               │            │            │              │             │             │              │
    │                │               │  └─────────────┘               │            │            │              │             │             │              │
    │                │               │                │                │            │            │              │             │             │              │
    │                │               │ resume_workflow(APPROVED)      │            │            │              │             │             │              │
    │                │               │──────────────>│                │            │            │              │             │             │              │
    │                │               │                │ human_approval │            │            │              │             │             │              │
    │                │               │                │ approval_status=APPROVED     │            │              │             │             │              │
    │                │               │                │                │            │            │              │             │             │              │
    │                │               │                │ backup_config ──────────────────────────────────────────────────────────────────────────>│              │
    │                │               │                │                │            │            │              │             │             │backup()      │
    │                │               │                │ config_backup <──────────────────────────────────────────────────────────────────────────│              │
    │                │               │                │                │            │            │              │             │             │              │
    │                │               │                │ execute_fix ─────────────────────────────────────────────────────────────>│             │              │
    │                │               │                │                │            │            │              │             │configure()  │              │
    │                │               │                │ exec_log <───────────────────────────────────────────────────────────────│             │              │
    │                │               │                │                │            │            │              │             │             │              │
    │                │               │                │ verify_result ────────────────────────────────>│              │             │             │              │
    │                │               │                │ verify_result <────────────────────────────────│              │             │             │              │
    │                │               │                │ (passed)       │            │            │              │             │             │              │
    │                │               │                │                │            │            │              │             │             │              │
    │                │               │                │ final_report ──────────────>│            │              │             │             │              │
    │                │               │                │ final_report <──────────────│            │              │             │             │              │
    │                │               │                │ status=CLOSED  │            │            │              │             │             │              │
    │                │               │                │                │            │            │              │             │             │              │
    │                │               │                │───────────────────────────────────────────────────────────────────────────────────────────────────>│
    │                │               │                │ log all nodes  │            │            │              │             │             │              │
    └────────────────┴───────────────┴────────────────┴────────────────┴────────────┴────────────┴──────────────┴─────────────┴─────────────┴──────────────┴──────────────┘
```

### 时序图 2: 人工审批中断/恢复详细流程

```
MOD-003              MOD-005            MOD-014           LangGraph Runtime        External Approver        MOD-015
StateGraphEngine     NodeHandlers       RiskAssessor      (Checkpointer)                                 AuditLogger
    │                    │                   │                    │                       │                    │
    │                    │ assess_risk()     │                    │                       │                    │
    │                    │──────────────────>│                    │                       │                    │
    │                    │ RiskAssessment    │                    │                       │                    │
    │                    │<──────────────────│                    │                       │                    │
    │                    │ (need_approval=true, risk=HIGH)        │                       │                    │
    │                    │                   │                    │                       │                    │
    │  CE-002: need_approval=true → human_approval               │                       │                    │
    │                    │                   │                    │                       │                    │
    │  interrupt_before=["human_approval"]                        │                       │                    │
    │───────────────────────────────────────────────────────────>│                       │                    │
    │                    │                   │  save checkpoint   │                       │                    │
    │                    │                   │  (persist State)   │                       │                    │
    │                    │                   │<───────────────────│                       │                    │
    │                    │                   │                    │                       │                    │
    │  return Interrupt(checkpoint_id)       │                    │                       │                    │
    │<───────────────────────────────────────────────────────────│                       │                    │
    │                    │                   │                    │                       │                    │
    │  ┌──────────────────────────────────────────────────────────────────────────────────────────────────┐│
    │  │ 外部审批交互（不在 LangGraph 运行时内）                                                            ││
    │  │                                                                                                  ││
    │  │  呈现审批信息:                                                                                    ││
    │  │  ┌─────────────────────────────────────────────────────┐                                         ││
    │  │  │ Alert: MAC_FLAPPING on Core-SW-01                    │                                         ││
    │  │  │ Root Cause: MAC漂移检测，疑似环路或端口安全配置缺失     │                                         ││
    │  │  │ Fix Plan:                                          │                                         ││
    │  │  │   1. interface Gi0/1                                │                                         ││
    │  │  │   2. switchport port-security                       │                                         ││
    │  │  │   3. switchport port-security maximum 2             │                                         ││
    │  │  │ Risk Level: HIGH                                    │                                         ││
    │  │  │                                                    │                                         ││
    │  │  │ [APPROVE]  [REJECT]                                │                                         ││
    │  │  └─────────────────────────────────────────────────────┘                                         ││
    │  │                                                                                                  ││
    │  │                                      运维人员审阅后点击 APPROVE                                    ││
    │  │                                                                                                  ││
    │  └──────────────────────────────────────────────────────────────────────────────────────────────────┘│
    │                    │                   │                    │                       │                    │
    │  resume_workflow(checkpoint_id, APPROVED)                   │                       │                    │
    │───────────────────────────────────────────────────────────>│                       │                    │
    │                    │                   │  load checkpoint   │                       │                    │
    │                    │                   │  restore State     │                       │                    │
    │                    │                   │<───────────────────│                       │                    │
    │                    │                   │                    │                       │                    │
    │                    │ human_approval()  │                    │                       │                    │
    │                    │ (设置 approval_status=APPROVED)        │                       │                    │
    │                    │──────────────────────────────────────────────────────────────────────────────────>│
    │                    │                   │                    │                       │  log_audit_event│
    │                    │                   │                    │                       │  (APPROVAL)     │
    │                    │                   │                    │                       │<─────────────────│
    │                    │                   │                    │                       │                    │
    │                    │ 继续执行 backup_config → execute_fix → verify_result → final_report              │
    │                    │                   │                    │                       │                    │
    │                    │                   │                    │                       │                    │
    │  ── 如果运维人员点击 REJECT ──────────────────────────────────────────────────────────────────────────│
    │                    │                   │                    │                       │                    │
    │  resume_workflow(checkpoint_id, REJECTED)                   │                       │                    │
    │───────────────────────────────────────────────────────────>│                       │                    │
    │                    │ human_approval()  │                    │                       │                    │
    │                    │ approval_status=REJECTED               │                       │                    │
    │                    │ → 跳转到 final_report (status=REJECTED)│                       │                    │
    │                    │──────────────────────────────────────────────────────────────────────────────────>│
    │                    │                   │                    │                       │  log_audit_event│
    │                    │                   │                    │                       │  (REJECTED)     │
    └────────────────────┴───────────────────┴────────────────────┴───────────────────────┴────────────────────┘
```

---

## 依赖关系图（文本格式）

```
# 触发层 → 编排层
MOD-001 (WebhookReceiver) ──→ MOD-004 (AlertNormalizer)  [IFC-004-01]
MOD-002 (InspectionScheduler) ──→ MOD-004 (AlertNormalizer)  [IFC-004-02]
MOD-002 (InspectionScheduler) ──→ MOD-011 (SwitchDiagTool)  [IFC-011-01]
MOD-002 (InspectionScheduler) ──→ MOD-016 (ConfigManager)  [IFC-016-01]

# 编排层内部
MOD-004 (AlertNormalizer) ──→ (无依赖，最底层)
MOD-003 (StateGraphEngine) ──→ MOD-005 (NodeHandlers)  [IFC-005-01~14]

# 编排层 → LLM 与知识层
MOD-005 (NodeHandlers) ──→ MOD-006 (LLMService)  [IFC-006-01, 02, 03]
MOD-005 (NodeHandlers) ──→ MOD-007 (TemplateEngine)  [IFC-007-01]
MOD-005 (NodeHandlers) ──→ MOD-008 (RAGService)  [IFC-008-01]
MOD-005 (NodeHandlers) ──→ MOD-009 (OutputValidator)  [IFC-009-01]

# 编排层 → 工具层
MOD-005 (NodeHandlers) ──→ MOD-010 (SwitchConfigTool)  [IFC-010-01]
MOD-005 (NodeHandlers) ──→ MOD-011 (SwitchDiagTool)  [IFC-011-01]
MOD-005 (NodeHandlers) ──→ MOD-012 (BackupTool)  [IFC-012-01, 02]
MOD-005 (NodeHandlers) ──→ MOD-013 (KnowledgeBaseTool)  [IFC-013-01]

# 编排层 → 安全与基础设施层
MOD-005 (NodeHandlers) ──→ MOD-014 (RiskAssessor)  [IFC-014-01]
MOD-005 (NodeHandlers) ──→ MOD-015 (AuditLogger)  [IFC-015-01]

# 工具层内部
MOD-013 (KnowledgeBaseTool) ──→ MOD-008 (RAGService)  [IFC-008-01]

# LLM 与知识层内部
MOD-009 (OutputValidator) ──→ MOD-015 (AuditLogger)  [安全告警记录]

# 安全与基础设施层
MOD-016 (ConfigManager) ──→ (无依赖，最底层)

# ─── 验证：无循环依赖 ───
# BFS 遍历确认所有路径单向无环:
# MOD-001 → MOD-004 → (终点)
# MOD-002 → MOD-004 → (终点)
# MOD-002 → MOD-011 → (终点)
# MOD-002 → MOD-016 → (终点)
# MOD-003 → MOD-005 → MOD-006/007/008/009/010/011/012/013/014/015 → (终点)
# MOD-013 → MOD-008 → (终点)
# MOD-009 → MOD-015 → (终点)
# 全部路径收敛至终端节点，无环。
```

---

## 需求到模块详细映射

| REQ ID | 映射模块 | 关键接口 |
|--------|---------|---------|
| REQ-FUNC-001 | MOD-001, MOD-004 | IFC-001-01, IFC-004-01 |
| REQ-FUNC-002 | MOD-001 | IFC-001-01（Mock 脚本作为独立工具） |
| REQ-FUNC-003 | MOD-002, MOD-016 | IFC-002-01, IFC-016-01 |
| REQ-FUNC-004 | MOD-004 | IFC-004-01, IFC-004-02 |
| REQ-FUNC-005 | MOD-005 (validate_alert) | IFC-005-03 |
| REQ-FUNC-006 | MOD-003 | IFC-003-01 |
| REQ-FUNC-007 | MOD-005 (get_device_info) | IFC-005-04 |
| REQ-FUNC-008 | MOD-010, MOD-011 | IFC-010-01, IFC-011-01 |
| REQ-FUNC-009 | MOD-011, MOD-005 (collect_diag) | IFC-011-01, IFC-005-06 |
| REQ-FUNC-010 | MOD-005 (analyze_root_cause), MOD-006, MOD-008 | IFC-005-07, IFC-006-01, IFC-008-01 |
| REQ-FUNC-011 | MOD-005 (generate_fix_plan), MOD-006, MOD-007, MOD-009 | IFC-005-08, IFC-006-02, IFC-007-01, IFC-009-01 |
| REQ-FUNC-012 | MOD-014 | IFC-014-01 |
| REQ-FUNC-013 | MOD-003, MOD-005 (human_approval) | IFC-003-03, IFC-003-04, IFC-005-10 |
| REQ-FUNC-014 | MOD-010, MOD-005 (execute_fix) | IFC-010-01, IFC-005-12 |
| REQ-FUNC-015 | MOD-011, MOD-005 (verify_result) | IFC-011-01, IFC-005-13 |
| REQ-FUNC-016 | MOD-005 (final_report), MOD-006 | IFC-005-14, IFC-006-03 |
| REQ-FUNC-017 | MOD-010 | IFC-010-01 |
| REQ-FUNC-018 | MOD-011 | IFC-011-01 |
| REQ-FUNC-019 | MOD-013, MOD-008 | IFC-013-01, IFC-008-01 |
| REQ-FUNC-020 | MOD-012 | IFC-012-01, IFC-012-02 |
| REQ-FUNC-021 | MOD-007, MOD-008 | IFC-007-02, IFC-007-03, IFC-008-03 |
| REQ-FUNC-022 | MOD-008 | IFC-008-02 |
| REQ-FUNC-023 | MOD-003, MOD-005 (全链路 14 节点) | 全链路节点覆盖 |
| REQ-FUNC-024 | MOD-003, MOD-005 (全链路 14 节点) | 全链路节点覆盖 |
| REQ-FUNC-025 | MOD-003, MOD-005 (全链路 14 节点) | 全链路节点覆盖 |

（非功能需求覆盖请参见 architecture_design.md 中的需求到模块覆盖矩阵）
