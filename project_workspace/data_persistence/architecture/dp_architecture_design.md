<file_header>
  <author_agent>sub_agent_system_architect</author_agent>
  <timestamp>2026-07-14T00:00:00Z</timestamp>
  <project_name>NetworkAgentDemo</project_name>
  <component>data_persistence</component>
  <phase>PHASE_DP_03 + PHASE_DP_04</phase>
  <group>GROUP_DP_B</group>
  <version>0.1.0</version>
  <status>DRAFT</status>
  <invocation_id>GROUP_DP_B</invocation_id>
  <input_files>
    <file>data_persistence/project_brief.md</file>
    <file>data_persistence/requirements/dp_requirements_spec.md</file>
    <file>data_persistence/requirements/dp_user_stories.md</file>
    <file>architecture/architecture_design.md</file>
  </input_files>
  <notes>
    输入文件 dp_requirements_spec.md 及 dp_user_stories.md 的 file_header 内 status 字段为 DRAFT，
    但 PM 调用指令中明确标注为"全部 APPROVED"，本架构设计以 PM 的显式批准为准进行。
  </notes>
</file_header>

# 数据持久化修复 — 架构设计文档

---

## 架构概览

### 变更类型：增量修复（Incremental Fix）

本架构设计是对现有 NetworkAgentDemo "模块化分层单体" 架构的**数据持久化层增量修复**，不改变系统整体架构风格、LangGraph 工作流节点逻辑、14 节点编排流程或前端代码。

**核心变更范围：**
- 数据库 Schema 层：alerts 表新增 `workflow_state` JSON 列，新增 `llm_calls` 表
- Repository 层：AlertRepository 新增工作流状态持久化方法，ApprovalRepository 新增 `get_approvals_by_alert_id`，新增 LLMCallLogRepository
- 编排层：NodeHandlers 各状态产生节点新增 DB 写操作，LLMService 将内存日志双写至 DB
- API 层：alerts_router 的 GET /api/alerts/{alert_id} 数据源从 MemorySaver/内存 dict 切换为数据库

**不变更范围（Out of Scope）：**
- LangGraph 工作流 14 个节点的业务逻辑与条件路由
- MemorySaver 的 Interrupt 机制（保留用于 LangGraph 工作流挂起/恢复）
- 前端 Vue 3 代码
- 现有 API 端点签名与响应结构

### 数据流变更概览

```
修复前（内存依赖）:
  NodeHandlers → MemorySaver (_active_states dict + LangGraph checkpointer)
                → LLMService._llm_call_log (process dict)
                → NodeHandlers._timeline_store (process dict)
  alerts_router → main_module.state_graph_engine.get_workflow_state() [MemorySaver]
                → main_module.llm_service.get_llm_logs() [dict]
                → main_module.node_handlers.get_timeline() [dict]

修复后（DB 为主，MemorySaver 保留用于 Interrupt）:
  NodeHandlers → AlertRepository.update_workflow_state() [SQLite alerts.workflow_state]
                → LLMCallLogRepository.create_log() [SQLite llm_calls]
                → AlertRepository.append_timeline_entry() [SQLite alert_timeline]
  LLMService   → LLMCallLogRepository.create_log() [SQLite llm_calls]
  alerts_router → AlertRepository (Alert + workflow_state) [SQLite]
                → ApprovalRepository.get_approvals_by_alert_id() [SQLite]
                → AlertRepository.get_alert_timeline() [SQLite]
                → LLMCallLogRepository.get_logs_by_alert_id() [SQLite]
  MemorySaver   → 仅用于 LangGraph Interrupt (不再被 API 读取路径使用)
```

### 关键 REQ-NFUNC 选型依据

| REQ-NFUNC | 约束内容 | 架构如何满足 |
|-----------|---------|-------------|
| REQ-NFUNC-001 | 数据一致性（DB值=内存值） | 各节点产生数据后立即写入 DB，write-through 策略 |
| REQ-NFUNC-002 | 重启可恢复 | 所有关键数据在 DB 中持久化，API 读路径仅依赖 DB |
| REQ-NFUNC-003 | 向后兼容（API 响应不变） | API 响应结构保持 `{alert, timeline, fix_plan, commands, llm_calls, approval}` |
| REQ-NFUNC-004 | 不引入新依赖 | 仅使用现有 SQLite + SQLAlchemy 2.0 + JSON 列 |
| REQ-NFUNC-005 | 不破坏现有表 | alerts 表新增列带 default=NULL，llm_calls 为独立新表 |

---

## 架构决策记录（ADRs）

---

### ADR-DP-001: 工作流状态字段的数据库 Schema 策略

- **Status**: Accepted
- **Context**:
  - REQ-FUNC-001 要求 fix_plan 持久化到数据库（覆盖所有告警，不限于高风险告警）。
  - REQ-FUNC-005 要求 root_cause、diag_result、exec_log、verify_result、final_report 五个字段持久化。
  - REQ-NFUNC-005 要求对 alerts 表修改通过新增列（带默认值）实现，不得修改或删除现有列。
  - REQ-NFUNC-004 要求使用现有 SQLite + SQLAlchemy 2.0 技术栈，不引入新数据库引擎。
  - 现有 `alerts` 表已有 9 列（id, alert_id, alert_type, severity, content, device_info, source, status + TimestampMixin 的 created_at/updated_at），不含上述 6 个字段中任何一个。
  - `src/models/state.py` 定义 NetworkAgentState 包含上述 6 个字段但无数据库映射（纯 TypedDict，仅限 MemorySaver 内存范围）。

- **Options**:
  - **Option A: alerts 表新增单个 `workflow_state` JSON 列**
    - 描述：在 alerts 表新增一个 `workflow_state` 列（SQLAlchemy JSON 类型，SQLite 存储为 TEXT），将 fix_plan、root_cause、diag_result、exec_log、verify_result、final_report 全部打包为单个 JSON 对象。如 `{"fix_plan": {...}, "root_cause": "...", "diag_result": "...", "exec_log": [...], "verify_result": {...}, "final_report": "..."}`。各节点执行后增量更新其负责的 key。
    - 优点：单个列、单次 ALTER TABLE、Schema 简洁；写入时可通过 `json_set`/`json_patch` 做增量更新；读取时一次 `SELECT` 即可获取全部工作流状态；不引入新表，不增加 JOIN 复杂度；符合 REQ-NFUNC-005（新增列带 default=NULL）。
    - 缺点：SQLite 的 JSON 函数不支持对 JSON 内部字段建索引（但在 Demo 数据量下不构成性能问题）；多个节点并发更新同一 JSON 列时存在竞态条件（需在 Repository 层用 `SELECT ... FOR UPDATE` 或应用层锁来保证）；JSON 文档体积随 exec_log 增长可能达到数十 KB（Demo 规模下可忽略）。
  - **Option B: 新建独立 `workflow_states` 表**
    - 描述：新建 `workflow_states(alert_id_fk, field_name, field_value JSON, updated_at)` 表，每个工作流状态字段作为一行独立存储。或设计为 `workflow_states(alert_id_fk, root_cause TEXT, diag_result TEXT, exec_log JSON, verify_result JSON, final_report TEXT, fix_plan JSON)` 宽表。
    - 优点：字段可独立建索引、独立查询；标准化关系模型，符合第三范式；宽表版本可对单个字段做类型约束（TEXT vs JSON）。
    - 缺点：需要 JOIN alerts 才能获取完整告警详情（增加 API 读路径复杂度）；宽表版本本质上是"把 alerts 表拆成两张表做 1:1 关联"——对于 1:1 关系是过度正规化；EAV 版本（field_name/filed_value）查询困难，需要在应用层重组 JSON 结构；新增表 + 外键约束增加了 Schema 维护成本。
  - **Option C: 为 6 个字段各新增独立列**
    - 描述：在 alerts 表上直接新增 6 列：`fix_plan JSON`、`root_cause TEXT`、`diag_result TEXT`、`exec_log JSON`、`verify_result JSON`、`final_report TEXT`。
    - 优点：每个字段独立可查询，类型明确，SQL 直观。
    - 缺点：6 次 ALTER TABLE（Demo 阶段用 `create_all` 规避这个问题，但语义上仍是对单表的大幅扩展）；alerts 表列数从 9 膨胀到 15，降低了表的内聚性；如果未来 NetworkAgentState 新增字段，需要再次 ALTER TABLE；6 个独立列的写入操作分布在 6 个不同节点处理器中，每个节点需要自己管理"写哪一列"的逻辑。

- **Decision**: 选择 **Option A（alerts 表新增单个 `workflow_state` JSON 列）**。

  理由：
  1. **Schema 变更最小化**：仅需 1 次 ALTER TABLE 新增 1 列（或首次运行时 `create_all` 新增列），最大化满足 REQ-NFUNC-005 的"最小侵入"原则。Option C 需要 6 次 ALTER TABLE（或等价的大幅模型修改），对现有表结构冲击更大。
  2. **写路径简洁**：每个节点处理器仅需调用 `repo.update_workflow_state(alert_id, {"root_cause": value})` 这样的增量更新接口，Repository 层统一处理 JSON 合并逻辑。Option B 要求节点处理器区分"插入"还是"更新"不同行/列。
  3. **读路径高效**：API 层一次 `SELECT workflow_state FROM alerts WHERE alert_id=?` 即可获取全部 6 个字段，无需 JOIN。满足 REQ-NFUNC-001 的数据一致性要求（单一数据源、原子读取）。
  4. **扩展性**：未来 NetworkAgentState 新增字段（如新增一个 `post_mortem_notes`）只需在 JSON 对象中新增 key，无需 ALTER TABLE。Option C 需要再次 ALTER TABLE。
  5. **Demo 规模适配**：SQLite 的 JSON 列在 Demo 数据量（单机、数十条告警）下查询性能完全足够。JSON 列不支持内部索引的缺点在 Demo 场景不构成实际问题。
  6. **竞态条件可控**：14 个 LangGraph 节点在单线程内**串行执行**（同步 StateGraph），不存在多个节点并发更新同一告警的 `workflow_state` 的场景。即使用 `threading.Thread` 启动工作流，每个 alert_id 也只有一个工作流线程在运行（thread_id 隔离）。

- **Consequences**:
  - **正向**：
    - 完整支撑 REQ-FUNC-001（fix_plan 持久化）和 REQ-FUNC-005（5 个工作流状态字段持久化），所有 6 个字段在单个 JSON 列中统一管理。
    - 满足 REQ-NFUNC-005（新增列，不破坏现有数据），`workflow_state` 默认值为 NULL，旧告警查询时 API 返回 null/空对象（US-001 AC-001-04、US-005 AC-005-03）。
    - Repository 层的 `update_workflow_state(alert_id, partial_update: dict)` 接口提供统一的增量写入语义（deep merge），各节点处理器无需关心底层存储格式。
  - **负向**：
    - SQLite 的 JSON 函数支持有限——`json_extract` 可读子字段，`json_set`/`json_replace` 可更新子字段，但复杂 JSON 操作（如向 exec_log 数组追加元素）需要在应用层做 read-modify-write 循环。
    - 单个 JSON 列意味着如果需要按 `root_cause` 内容做全文搜索，无法使用 SQLite FTS（Demo 范围无此需求）。
    - JSON 列的总大小随 exec_log 增长可能达到数十 KB，需在 Repository 层设置合理的大小上限（建议 1MB，[ESTIMATE] 基于 Demo 预期最多 20 条命令记录）。

---

### ADR-DP-002: LLM 调用日志的数据库 Schema 策略

- **Status**: Accepted
- **Context**:
  - REQ-FUNC-002 要求 LLM 调用详情（endpoint、timestamp、elapsed_s、prompt_tokens、completion_tokens、prompt 摘要、response 摘要）持久化到数据库。
  - REQ-NFUNC-005 允许新建独立表（"新增表独立创建"）。
  - 现有 `LLMService._llm_call_log` 为进程内存字典（`dict[str, list[dict]]`），结构为 `{alert_id: [{endpoint, timestamp, elapsed_s, prompt_tokens, completion_tokens, prompt, response}, ...]}`。
  - `src/llm/llm_service.py:170-183` 记录了 LLM 调用的完整字段结构。
  - 每个告警的工作流最多触发 3 次 LLM 调用（analyze_root_cause、fill_template_params、generate_report），但也可能因重试产生更多记录（最多 3 次重试 × 3 个端点 = 9 次）。
  - US-002 AC-002-01 要求 "可通过 alert_id 关联到对应的告警"。

- **Options**:
  - **Option A: 新建独立 `llm_calls` 表（关系表）**
    - 描述：新建 `llm_calls` 表，每行一条 LLM 调用记录。Schema：`id (PK), alert_id_fk (FK→alerts.alert_id), endpoint (VARCHAR), timestamp (DATETIME), elapsed_s (FLOAT), prompt_tokens (INT), completion_tokens (INT), prompt_summary (TEXT), response_summary (TEXT), is_mock (BOOLEAN)`。通过 `alert_id_fk` 关联告警。LLMService 每次调用完成后写入一行。
    - 优点：关系模型自然——一次 LLM 调用 = 一行记录，语义清晰；可独立查询、过滤（按 endpoint、时间范围、token 用量排序）；支持聚合统计（如"过去 24 小时总 token 消耗"）；符合 REQ-NFUNC-005 的"新表独立创建"策略；与现有 `alert_timeline` 表的设计风格一致（一事件一行）。
    - 缺点：需要新建 ORM 模型和 Repository 类（LLMCallLog、LLMCallLogRepository），增加代码量；读取时需要 JOIN 或二次查询（先查 alerts，再查 llm_calls）。
  - **Option B: 将 LLM 日志嵌入 alerts 表的 JSON 列中**
    - 描述：将 LLM 调用记录作为数组嵌入 `alerts.workflow_state` JSON 的 `llm_calls` key 中。LLMService 不直接写 DB，而是将日志传递给 NodeHandlers，由 NodeHandlers 在更新 workflow_state 时一并写入。
    - 优点：不引入新表；LLM 日志与工作流状态在同一个 JSON 文档中，读取告警详情时一次查询即可获取全部数据（包括 LLM 日志）。
    - 缺点：LLM 日志与工作流状态的关注点不同（日志是事件流，状态是快照），混合存储违反单一职责原则；更新 LLM 日志需要 read-modify-write 整个 workflow_state JSON，增加写入复杂度和数据损坏风险；无法独立查询 LLM 日志（如"列出所有 LLM 调用"），必须先 JOIN alerts 再解析 JSON；多次 LLM 调用时，workflow_state JSON 体积膨胀，影响读写性能。
  - **Option C: 复用 `alert_timeline` 表存储 LLM 日志**
    - 描述：将 LLM 调用记录作为特殊的 timeline 条目（`node_name="llm_call"`）写入现有 `alert_timeline` 表，LLM 调用详情序列化到 `state_snapshot` JSON 列。
    - 优点：复用现有表结构，零新表。
    - 缺点：混淆了"工作流节点执行"和"LLM API 调用"两种不同粒度的事件；`alert_timeline` 的 `state_snapshot` JSON 字段设计为存储 NetworkAgentState 快照，强行塞入 LLM 调用记录破坏数据语义；查询 LLM 日志时需要 `WHERE node_name='llm_call'`，与其他 timeline 条目混在一起，语义不清晰。

- **Decision**: 选择 **Option A（新建独立 `llm_calls` 表）**。

  理由：
  1. **语义清晰性**：LLM 调用日志是独立于工作流状态的审计/调试数据，拥有自己的生命周期和查询模式（REQ-FUNC-002 明确要求 "LLM 调用历史仍可查询"）。独立表是表达这种独立性的正确方式。
  2. **查询灵活性**：独立表支持按 `endpoint`、`elapsed_s`、`prompt_tokens` 等字段排序/过滤/聚合——这些查询在 JSON 嵌入方案（Option B）中需要解析每行 JSON，在 Option C 中需要与工作流 timeline 条目混查。US-002 验收标准要求开发人员能够"追溯历史告警处理过程中的 LLM 行为"，独立表最能支撑这一需求。
  3. **写入路径分离**：LLMService 调用 `LLMCallLogRepository.create_log()` 直接写入 `llm_calls` 表，与 NodeHandlers 更新 `alerts.workflow_state` 的路径解耦。这避免了 Option B 中"LLMService → NodeHandlers → AlertRepository" 的跨层传递。
  4. **一致性保证**：即使在 LLM 调用成功但工作流后续失败的情况下，LLM 调用记录已安全写入独立表，不会因工作流状态回滚而丢失（这对调试非常重要——失败的调用也需要记录）。
  5. **扩展性**：未来如需按 `endpoint` 统计 DeepSeek API 调用成本或按时间范围导出日志，独立表可直接支持 `SELECT SUM(prompt_tokens + completion_tokens) FROM llm_calls WHERE created_at > ?` 这类聚合查询。

- **Consequences**:
  - **正向**：
    - 完整支撑 REQ-FUNC-002（LLM 调用日志持久化），US-002 全部 4 条验收标准可通过独立表实现。
    - LLMCallLogRepository 提供 `get_logs_by_alert_id(alert_id) -> list[LLMCallLog]` 接口，API 层可直接调用，与现有 `get_alert_timeline` 风格一致。
    - 支持 Mock 模式标识（`is_mock` 列），满足 US-002 AC-002-04（区分真实调用与模拟调用）。
  - **负向**：
    - 新增 ORM 模型（LLMCallLog）+ Repository（LLMCallLogRepository），增加约 80-100 行代码。
    - API 读路径需要两次查询：先查 alerts 获取基本信息和 workflow_state，再查 llm_calls 获取 LLM 日志。在 Demo 数据量下，两次毫秒级 SQLite 查询的性能影响可忽略（[ESTIMATE] < 5ms 总额外延迟）。

---

### ADR-DP-003: 数据同步时机策略 — 工作流状态与 LLM 日志的写入时机

- **Status**: Accepted
- **Context**:
  - REQ-NFUNC-001 要求 "工作流状态写入数据库后，能通过数据库查询读回与写入时完全一致的数据"。
  - REQ-NFUNC-002 要求 "所有关键数据在服务器进程重启后不丢失"。
  - NetworkAgentState 的 6 个关键字段由不同的 LangGraph 节点在不同时间点生成：
    - `diag_result` 由 `collect_diag` 节点生成（第 6 个节点）
    - `root_cause` 由 `analyze_root_cause` 节点生成（第 7 个节点）
    - `fix_plan` 由 `generate_fix_plan` 节点生成（第 8 个节点）
    - `exec_log` 由 `execute_fix` 节点生成（第 12 个节点）
    - `verify_result` 由 `verify_result` 节点生成（第 13 个节点）
    - `final_report` 由 `final_report` 节点生成（第 14 个节点）
  - LLM 调用可能发生在 `analyze_root_cause`、`generate_fix_plan`（内部调用 `fill_template_params`）、`final_report`（内部调用 `generate_report`）三个阶段。
  - 现有代码中，NodeHandlers 的 `_log_node` 方法已经在各节点结束时尝试写 timeline 到 DB（`src/orchestration/node_handlers.py:140-153`），`handle_final_report` 也已做 status 同步（L752-762）。这些是"即时写"的已有模式。

- **Options**:
  - **Option A: 逐节点即时写入（Write-at-Source）**
    - 描述：每个节点处理器在生成其负责的状态数据后，立即调用 Repository 将该数据写入 DB。例如：`collect_diag` 节点完成后立即写入 `diag_result` 到 `alerts.workflow_state`；`_call_llm` 完成后立即写入 `llm_calls` 表。工作流最终同步 `final_report` 和 `status`。
    - 优点：最大程度的数据安全性——即使后续节点崩溃，已完成节点的数据已持久化；符合 REQ-NFUNC-001（写入后立即可读）；与现有 NodeHandlers 中的即时写模式一致（timeline 写入、approval 写入、status 同步）；工作流执行过程中可通过 API 查询已完成的中间状态。
    - 缺点：DB 写入次数多（最坏情况 14 个节点 × 1 次写 = 14 次写操作）；每个节点需要管理自己的"写什么"逻辑，增加了节点处理器的耦合度。
  - **Option B: 工作流结束时批量写入（Batch-at-End）**
    - 描述：所有工作流状态数据暂存在 NetworkAgentState（即 MemorySaver）中，只在 `finish_report` 节点中一次性将所有 6 个字段 + LLM 调用日志批量写入 DB。
    - 优点：DB 写入次数最少（1 次批量写），写入逻辑集中在 finish_report 节点；事务性更强（全部成功或全部失败，不存在部分持久化状态）。
    - 缺点：**严重违反 REQ-NFUNC-002**——如果工作流在 finish_report 之前崩溃（例如 LLM 调用异常、进程被 kill、服务器断电），所有中间状态全部丢失；工作流运行期间 API 无法查询到任何中间状态数据；与现有"即时写模式"（timeline 写入在 `_log_node` 中）不一致。
  - **Option C: 混合策略（Hybrid — 即时写 + 最终确认）**
    - 描述：区分"写入时机" — 每条数据在其生成节点立即写入 DB（即时写），但引入一个 `workflow_state._completed` 标记，由 `finish_report` 节点最终设置为 `true`。API 读取时优先返回 DB 数据，但对于 `_completed=false` 的告警，部分字段可能尚未生成（返回 null）。LLM 日志在每次 `_call_llm` 后立即写入 `llm_calls` 表。
    - 优点：工作流崩溃时已完成的节点数据已持久化（满足 REQ-NFUNC-002 的核心诉求）；API 可区分"未生成"（字段为 null）与"已生成但未持久化"（不存在的情况）；LLM 日志的即时写入满足开发调试需求（即使工作流失败，LLM 调用记录也已保存）。
    - 缺点：写入操作分散在多个节点中，增加了每个节点的代码量和耦合；`workflow_state` JSON 的增量更新需要在 Repository 层实现 read-modify-write 逻辑。

- **Decision**: 选择 **Option A（逐节点即时写入）**，并采纳 Option C 的 `_completed` 标记作为补充。

  理由：
  1. **数据安全性优先**：REQ-NFUNC-002 是 Must Have 非功能需求，要求"不依赖 MemorySaver 作为唯一数据源"。Option A 确保每个字段在生成后立即有 DB 副本，工作流在任何节点崩溃时已持久化的数据不丢失。Option B 在崩溃场景下会丢失所有数据，直接违反 REQ-NFUNC-002。
  2. **与现有模式对齐**：NodeHandlers 中已有即时写模式——`_log_node` 在节点结束时写 timeline（L139-153）、`handle_assess_risk` 在风险评估后写 approval（L489-506）、`handle_final_report` 在结束时同步 status（L752-762）。将工作流状态字段的写入集成到这个已有模式中是自然的扩展，而非引入新的写策略。
  3. **增量写入粒度**：每个节点只写自己生成的数据，不写其他字段。例如：
     - `collect_diag` 节点：写入 `{"diag_result": value}`
     - `analyze_root_cause` 节点：写入 `{"root_cause": value, "knowledge_refs": value}`
     - `generate_fix_plan` 节点：写入 `{"fix_plan": value}`
     - `execute_fix` 节点：写入 `{"exec_log": value}`
     - `verify_result` 节点：写入 `{"verify_result": value}`
     - `finish_report` 节点：写入 `{"final_report": value, "_completed": true}` + status 同步
  4. **LLM 日志独立写入**：`LLMService._call_llm` 在调用完成后立即通过 `LLMCallLogRepository.create_log()` 写入 `llm_calls` 表。即使 LLM 调用触发了异常导致节点标记为 FAILED，该次调用的日志已安全保存——这对调试至关重要。
  5. **写入性能可接受**：每个节点 1 次额外的 SQLite UPDATE 操作，延迟 < 1ms（SQLite WAL 模式，本地磁盘），对工作流总延迟的影响可忽略（[ESTIMATE] < 15ms 总额外开销，相比 LLM API 调用的 2-10 秒延迟）。

- **Consequences**:
  - **正向**：
    - 满足 REQ-NFUNC-002（重启可恢复）——服务器在任何节点后重启，已完成节点的数据已在 DB 中。
    - 满足 REQ-NFUNC-001（数据一致性）——写入后立即可通过 DB 查询到与内存中一致的值。
    - 工作流执行过程中 API 可查询中间状态（如 `diag_result` 已生成但 `fix_plan` 尚未生成时，API 返回 diag_result 有值、fix_plan 为 null），提升可观测性。
    - `_completed` 标记允许 API 和前端区分"工作流已完成"与"工作流执行中但部分数据已生成"。
  - **负向**：
    - 每个状态产生节点增加 2-5 行 DB 写代码，增加节点处理器的代码量（总共约 +30 行）。
    - DB 写入次数随节点数线性增长。对 SQLite 的 WAL 模式而言，单线程顺序写入的性能影响微乎其微，但理论上增加了磁盘 I/O 次数。
    - `alerts.workflow_state` JSON 列的增量更新需要 Repository 层实现 "读取当前 JSON → deep merge 新值 → 写回" 的 read-modify-write 循环。

---

### ADR-DP-004: 告警详情 API 的读取策略

- **Status**: Accepted
- **Context**:
  - REQ-FUNC-003 要求 GET /api/alerts/{alert_id} 从数据库（approvals 表）读取审批信息，而非 MemorySaver。
  - REQ-FUNC-006 要求该接口的 fix_plan、commands、approval、llm_calls、root_cause、diag_result、exec_log、verify_result、final_report 全部从数据库读取。
  - REQ-NFUNC-003 要求 API 响应字段名/结构和 HTTP 状态码语义不变。
  - 当前实现（`src/api/alerts_router.py:66-129`）从三个不可靠来源读取数据：
    1. MemorySaver（`state_graph_engine.get_workflow_state(alert_id)` L84）→ fix_plan、commands、approval 信息
    2. NodeHandlers 内存时间线（`node_handlers.get_timeline(alert_id)` L107）→ timeline
    3. LLMService 内存日志（`llm_service.get_llm_logs(alert_id)` L115）→ llm_calls
  - 仅 Alert 基本信息（L70）和 DB timeline（L74）来自数据库。
  - API 响应结构为 `{"alert", "timeline", "fix_plan", "commands", "llm_calls", "approval"}`（L122-129）。

- **Options**:
  - **Option A: 数据库为主，MemorySaver 为 Fallback（DB-Primary with Fallback）**
    - 描述：API 优先从数据库读取所有数据。对于数据库中不存在的数据（如旧告警无 workflow_state、或工作流正在执行中某些字段尚未写入），fallback 到 MemorySaver。LLM 日志优先查 llm_calls 表，fallback 到 LLMService._llm_call_log。
    - 优点：最大化数据可用性——新建/运行中的告警可能仅有 MemorySaver 数据，旧告警仅有 DB 数据，此策略两种场景均覆盖；过渡平滑，不产生行为断裂；向后兼容性好（REQ-NFUNC-003）。
    - 缺点：代码中存在两个读路径（DB + MemorySaver），增加维护复杂度；fallback 逻辑可能掩盖"数据应该已写入 DB 但未写入"的 bug。
  - **Option B: 纯数据库读取（DB-Only）**
    - 描述：API 的所有数据 100% 从数据库读取。移除 `import sys; main_module = sys.modules.get("src.main")` 的 MemorySaver 访问路径。如果数据不在 DB 中，返回 null/空值而不是尝试从 MemorySaver 获取。
    - 优点：单一数据源，代码简洁，不依赖进程内状态；真正满足 REQ-NFUNC-002（MemorySaver 不可用时 API 仍正常工作）；消除了"不同来源数据可能不一致"的问题。
    - 缺点：对于正在执行中的工作流（部分字段尚未写入 DB），API 返回的中间状态数据不完整（仅有已写入的字段）；`approval` 字段在审批 PENDING 时可能 DB 中有记录但尚未包含 `decision` 信息——不过这实际上是预期行为。
  - **Option C: 数据库 + 缓存层（DB + Cache）**
    - 描述：引入应用层缓存（如 Python `functools.lru_cache` 或 dict），API 读路径为"查缓存 → 未命中则查 DB → 写入缓存"。缓存 TTL 短（如 5 秒），工作流写入 DB 时主动失效缓存。
    - 优点：减少 DB 查询次数（相同告警的重复请求走缓存）。
    - 缺点：Demo 场景下 Web UI 的请求频率极低（运维人员手动刷新页面），缓存收益约等于零；缓存一致性维护（写入时失效）增加复杂度；违反"Demo 可接受，不引入额外复杂度"的设计原则。

- **Decision**: 选择 **Option B（纯数据库读取）**。

  理由：
  1. **需求本质对齐**：REQ-FUNC-006 明确要求 "全部从数据库读取，不再依赖 LangGraph MemorySaver 内存状态或 Python 进程内 dict"。Option B 是唯一完全满足此要求的方案——Option A 保留了 MemorySaver 读路径，本质上未完成数据源切换。
  2. **代码简化**：移除 `src/api/alerts_router.py` 中 try-except 包裹的 `import sys; main_module = ...` 整个代码块（约 47 行，L80-117），消除了对 `src.main` 模块的运行时耦合。API 路由仅依赖 Repository 层和 FastAPI 的 `Depends(get_db)`。
  3. **重启安全性**：Option B 确保服务器重启后 API 的行为完全一致——重启前已持久化的数据可读，未持久化的数据（旧实现中仅在 MemorySaver）统一返回 null。这比 Option A 的 "有时有数据有时没有" 行为更加确定和可测试。
  4. **内存泄漏消除**：移除对 `_active_states` dict 和 `_llm_call_log` dict 的依赖后，这些内存结构可以作为纯运行时缓存而非唯一数据源，降低长期运行的内存压力。
  5. **风险可控**：对于"工作流正在执行中，部分字段尚未写入 DB"的场景，API 返回 null 是明确定义的语义——前端在 US-005 AC-005-03 和 US-005 AC-005-04 中已预期 "尚未生成的字段在 API 响应中返回 null 或空值"。
  6. **Option A 的过渡价值有限**：在 ADR-DP-003（即时写入）策略下，每个节点执行后数据立即可在 DB 中查到。MemorySaver 中不存在"DB 中没有但 MemorySaver 中有"的额外数据——因为所有数据写入都是 write-through。因此 Fallback 的实用价值极低。

- **Consequences**:
  - **正向**：
    - 完整满足 REQ-FUNC-003（审批信息从 DB 读取）、REQ-FUNC-006（全部数据源切换为 DB）。
    - API 代码简化约 47 行（移除 MemorySaver/dict 读路径），降低维护成本。
    - 消除对 `src.main` 模块的循环引用风险（当前通过 `sys.modules` 运行时访问，是一个脆弱的耦合模式）。
    - API 在任何进程生命周期阶段（启动中、运行中、重启后）行为一致，仅依赖 DB 连接。
  - **负向**：
    - 对于正在执行中的工作流，API 返回的数据可能不完整（如 diag_result 已写入但 root_cause 尚未写入）。这是预期行为，前端需在 AC-005-03 和 AC-005-04 的指导下处理 null 值——前端代码无需修改（向后兼容）。
    - 如果工作流线程与 API 请求之间存在时间窗口竞争（工作流刚完成但 DB 写入尚未 commit），可能在极少数情况下返回不完整数据。缓解措施：NodeHandlers 的 DB 写入使用 `db.commit()` 同步提交，确保 API 请求到达时数据已可见。

---

### ADR-DP-005: MemorySaver 在新架构中的角色定位

- **Status**: Accepted
- **Context**:
  - REQ-NFUNC-002 要求 "不依赖 LangGraph MemorySaver 的临时内存或任何进程内数据结构作为唯一数据源"。
  - MemorySaver 当前承担两个角色：(1) LangGraph 的 checkpointer（支持 Interrupt 挂起/恢复），(2) 工作流状态的主要查询源（`get_workflow_state` 被 API 和内部逻辑调用）。
  - LangGraph 的 `interrupt_before=["human_approval"]` 机制依赖 checkpointer 来保存挂起时的状态并在恢复时重建——这是 LangGraph 框架的内置能力，无法在不重写 Interrupt 逻辑的情况下移除。
  - `state_graph_engine.py:44` 定义 `self._checkpointer = MemorySaver()`，`L48` 定义 `self._active_states: dict[str, NetworkAgentState] = {}` 作为缓存。
  - 超出范围声明：requirements_spec.md "超出范围" 第 2 条明确 "MemorySaver 继续用于 LangGraph 的 Interrupt 机制（工作流挂起/恢复），但不再作为工作流状态的唯一数据源"。

- **Options**:
  - **Option A: 保留 MemorySaver 仅用于 Interrupt，移除所有读路径依赖**
    - 描述：MemorySaver 保留为 LangGraph 的 checkpointer（`workflow.compile(checkpointer=self._checkpointer, interrupt_before=[...])`），继续支撑 Interrupt 机制。但 API 层、内部查询逻辑、`_active_states` 缓存等**不再**将其作为数据查询源。`get_workflow_state` 方法标记为 Deprecated（或重命名为 `_get_checkpoint_state` 仅供内部调试使用）。`_active_states` 缓存可以保留为优化（减少频繁的 checkpoint 查询），但不再作为 API 的数据来源。
    - 优点：最小变更——不触碰 LangGraph 的编译和执行逻辑；Interrupt 机制无需重写；满足 REQ-NFUNC-002（DB 是唯一数据源）；代码改动集中在 API 层（移除 MemorySaver 读路径）。
    - 缺点：系统中同时存在两个状态存储（DB + MemorySaver），增加了概念上的冗余；MemorySaver 中的状态在重启后丢失，但 Interrupt 挂起的审批如果恰好在重启时发生，审批状态会丢失——这其实是当前已存在的问题，不在本次修复范围内。
  - **Option B: 完全替换 MemorySaver 为 SQLite-backed Checkpointer**
    - 描述：实现一个自定义的 LangGraph `BaseCheckpointSaver`，底层使用 SQLite 存储 checkpoint 数据。这样 checkpointer 本身就是持久化的，无需单独的 DB 写路径。
    - 优点：单一持久化方案，消除 MemorySaver 的冗余；checkpoint 数据也持久化（重启后 Interrupt 挂起的审批不会丢失）。
    - 缺点：**工作量极大**——需要实现 LangGraph 的 `BaseCheckpointSaver` 接口（`get_tuple`、`put`、`list` 等），其内部使用 `CheckpointTuple` 等复杂数据结构序列化；LangGraph checkpoint 的序列化格式是框架内部实现细节，API 稳定性无保证；引入复杂度和 bug 风险远超过 Demo 的收益；超出本次数据持久化修复的范围（本次聚焦于 6 个具体需求，不是重建 checkpointer）。
  - **Option C: 保留 MemorySaver 全部功能，不做任何变更**
    - 描述：MemorySaver 继续作为主要数据源，DB 仅作为"额外备份"。API 读路径保持现状（MemorySaver 优先）。
    - 优点：零代码变更。
    - 缺点：**违反 REQ-FUNC-006**（API 必须从 DB 读取）和 **REQ-NFUNC-002**（不依赖 MemorySaver 作为唯一数据源）；不解决任何已识别的问题 1-5。

- **Decision**: 选择 **Option A（保留 MemorySaver 仅用于 Interrupt，移除所有 API/查询读路径依赖）**。

  理由：
  1. **需求范围精确对齐**：超出范围声明第 2 条明确将 "更换 MemorySaver 为其他 checkpointer" 排除在外，同时确认 "MemorySaver 继续用于 LangGraph 的 Interrupt 机制"。Option A 是最精确满足此边界的方案。
  2. **风险最小化**：Option A 不触碰 LangGraph 编译/执行核心逻辑（`build_graph`、`run_workflow`、`resume_workflow`、条件边路由函数），仅修改 API 层和内部状态查询路径。LangGraph 的 Interrupt 机制是系统的关键路径（审批中断），任何对其的修改都可能引入难以调试的 bug。
  3. **分离关注点**：MemorySaver = 工作流运行时引擎（LangGraph 的 checkpointer），SQLite = 持久数据存储（应用层的数据源）。两者职责不同，不应混淆。Option B 试图用 SQLite 替代 MemorySaver 的运行时 checkpointer 角色，是 layer violation——把持久化存储用于运行时状态机驱动。
  4. **已知限制可接受**：重启时 MemorySaver 中 Interrupt 挂起的审批状态会丢失——这是当前系统已存在的限制，不在本次修复范围内（本次修复聚焦于已完成的告警数据可查询）。如未来需要 Interrupt 持久化，可考虑 LangGraph 的 `SqliteSaver`（langgraph 官方提供，已可用但本次不引入）。

- **Consequences**:
  - **正向**：
    - 完整满足 REQ-NFUNC-002（DB 是持久化数据的唯一数据源，MemorySaver 仅用于运行时 Interrupt）。
    - API 层代码简化（移除对 `state_graph_engine.get_workflow_state()` 的依赖）。
    - `StateGraphEngine.get_workflow_state()` 方法可标记为内部方法（仅供测试/调试使用），降低其作为公共接口的语义债务。
  - **负向**：
    - `_active_states` 缓存和 `get_workflow_state` 方法仍然存在（保留用于 LangGraph 内部查询和调试），但不再作为 API 数据源——这可能造成"还有一个状态查询方法"的困惑。通过在 `get_workflow_state` 的 docstring 中添加 Deprecation 说明来缓解。
    - Interrupt 挂起的审批在重启后丢失（已存在的问题），本次修复未解决。如需解决，可能引入 langgraph 的 `SqliteSaver` 作为 checkpointer（超出本次范围）。

---

### ADR-DP-006: 向后兼容策略 — API 响应格式保持

- **Status**: Accepted
- **Context**:
  - REQ-NFUNC-003 要求 "GET /api/alerts/{alert_id} 接口的响应字段名、字段结构和 HTTP 状态码语义不因数据源切换而改变，现有前端代码无需修改即可正常工作"。
  - 当前 API 响应结构（`src/api/alerts_router.py:122-129`）：`{"alert": Alert ORM object, "timeline": list, "fix_plan": dict|null, "commands": list, "llm_calls": list, "approval": dict|null}`。
  - US-006 AC-006-01 要求 "响应的顶层 JSON 结构保持为六个字段全部存在，字段名不变"。
  - `alert` 字段当前返回的是 SQLAlchemy ORM 对象，FastAPI 通过 `response_model`（本接口未定义显式 response_model，依赖默认 JSON 序列化）将其序列化为 JSON。
  - `timeline` 字段当前优先返回内存时间线（`memory_timeline`），仅在无内存数据时 fallback 到 DB 时间线（`timeline`，L120）。
  - 前端 Vue 3 组件（AlertsListView.vue、AlertDetail 相关组件）依赖这些字段名。

- **Options**:
  - **Option A: 精确保持 API 响应结构（Exact Preservation）**
    - 描述：API 响应保持完全相同的 JSON 结构——顶层 6 个字段名不变，每个字段内部的子结构也不变。数据源切换为 DB，但序列化后的 JSON 与从 MemorySaver 读取时的格式完全一致。`commands` 字段从 `fix_plan.commands`（JSON 列中提取）生成，保持为字符串数组。`approval` 字段通过查询 approvals 表后映射为现有格式。
    - 优点：前端零改动，满足 REQ-NFUNC-003 和 US-006 全部验收标准；API 消费者（前端、测试脚本）无需感知数据源变更；回滚风险低——如果 DB 读取出问题，可以快速切回旧代码路径。
    - 缺点：API 响应结构与 DB Schema 之间需要映射层（如 `fix_plan` JSON → 提取 `commands` 为顶层字段）；如果 DB 中的数据结构与 MemorySaver 中的有细微差异（如 datetime 序列化格式），需要在映射层做格式化处理。
  - **Option B: 渐进增强（Progressive Enhancement）**
    - 描述：在保持基本响应结构一致的前提下，小幅优化 API 响应——如增加 `workflow_state` 嵌套对象包含 root_cause/diag_result 等新字段，同时保留旧字段作为兼容。通过 API 版本号或 HTTP Header 区分新旧格式。
    - 优点：可以利用持久化修复的机会改善 API 设计（如将分散的字段整合为 `workflow_state` 对象）。
    - 缺点：需要前端配合升级（即使旧字段兼容，前端也需要选择性使用新字段）；增加 API 版本管理复杂度；违反 REQ-NFUNC-003 的精神（"现有前端代码无需修改即可正常工作"意味着前端不应感知到任何格式变化，包括新增可选字段可能导致的 UI 适配需求）；Demo 项目引入 API 版本管理是过度设计。

- **Decision**: 选择 **Option A（精确保持 API 响应结构）**。

  理由：
  1. **需求硬约束**：REQ-NFUNC-003 是 Must Have 非功能需求，US-006 的 4 条验收标准全部围绕"响应结构不变"。Option A 是唯一直接满足所有验收标准的方案。
  2. **前端稳定性优先**：Demo 项目的前后端往往由同一团队在紧张时间线下开发。任何 API 格式变更都可能需要前端联调——即使新增可选字段也可能触发 Vue 组件的响应式更新逻辑。Option A 将前端变更风险降为零。
  3. **映射层可自测**：API 响应格式与 DB Schema 之间的映射逻辑集中在 `get_alert_detail` 函数内，可以通过单元测试精确验证"给定 DB 数据 → 产生正确 JSON 响应"。
  4. **回滚安全**：如果持久化修复引入线上问题，可以快速回滚至旧代码——因为 API 接口签名未变，前端和 API 消费者不受影响。

- **Consequences**:
  - **正向**：
    - 完整满足 REQ-NFUNC-003 和 US-006 全部 4 条验收标准。
    - API 响应结构稳定，前端代码无需任何修改。
    - 映射逻辑集中、可测试。
  - **负向**：
    - `get_alert_detail` 函数需要实现从 Repository 返回数据到 API 响应 JSON 的映射逻辑（约 50-60 行），代码量比旧实现略增。
    - 如果未来决定优化 API 结构（如引入 `workflow_state` 嵌套对象），需要同时维护旧格式的兼容映射——但 Demo 阶段无此预期。

---

## 需求覆盖矩阵（ADRs → REQs）

| ADR ID | 决策标题 | 覆盖 REQ-FUNC | 覆盖 REQ-NFUNC |
|--------|---------|--------------|---------------|
| ADR-DP-001 | 工作流状态 Schema：单 JSON 列 | REQ-FUNC-001, REQ-FUNC-005 | REQ-NFUNC-004, REQ-NFUNC-005 |
| ADR-DP-002 | LLM 日志 Schema：独立 llm_calls 表 | REQ-FUNC-002 | REQ-NFUNC-004, REQ-NFUNC-005 |
| ADR-DP-003 | 同步时机：逐节点即时写入 | REQ-FUNC-001, REQ-FUNC-002, REQ-FUNC-005 | REQ-NFUNC-001, REQ-NFUNC-002 |
| ADR-DP-004 | API 读策略：纯数据库 | REQ-FUNC-003, REQ-FUNC-006 | REQ-NFUNC-003 |
| ADR-DP-005 | MemorySaver：仅 Interrupt | REQ-FUNC-006 | REQ-NFUNC-002 |
| ADR-DP-006 | 向后兼容：精确保持 | REQ-FUNC-006 | REQ-NFUNC-003 |

---

## 模块依赖关系图

```
                    ┌──────────────────────────┐
                    │   MOD-DP-008: alerts_router │  (修改 — API 层)
                    │   GET /api/alerts/{id}     │
                    └──────────┬───────┬─────────┘
                               │       │
                    ┌──────────┘       └──────────┐
                    ▼                              ▼
  ┌────────────────────────────┐   ┌──────────────────────────────┐
  │ MOD-DP-004: AlertRepository│   │ MOD-DP-005: ApprovalRepository│
  │ (扩展: update_workflow_    │   │ (扩展: get_approvals_by_     │
  │  state, get 工作流状态)     │   │  alert_id)                   │
  └────────────┬───────────────┘   └──────────────┬───────────────┘
               │                                  │
               ▼                                  ▼
  ┌────────────────────────────┐   ┌──────────────────────────────┐
  │ MOD-DP-001: Alert ORM      │   │ MOD-WEB-003: Approval ORM    │
  │ (扩展: +workflow_state)    │   │ (不变, 已有 alert_id_fk)      │
  └────────────────────────────┘   └──────────────────────────────┘

  ┌────────────────────────────┐
  │ MOD-DP-003: LLMCallLogRepo │◄──── MOD-DP-007: LLMService (修改)
  │ (新增: create_log,         │     每次 _call_llm 后调用 create_log
  │  get_logs_by_alert_id)     │
  └────────────┬───────────────┘
               │
               ▼
  ┌────────────────────────────┐
  │ MOD-DP-002: LLMCallLog ORM │
  │ (新增: llm_calls 表)       │
  └────────────────────────────┘

  ┌────────────────────────────┐
  │ MOD-DP-006: NodeHandlers   │──── 修改 — 编排层
  │ (扩展: 6 个节点新增 DB 写) │
  └────────────┬───────────────┘
               │ 调用
               ▼
  ┌────────────────────────────┐
  │ MOD-DP-004: AlertRepository│ ── 已在上方列出
  └────────────────────────────┘
```

**依赖关系（文本格式，已验证无循环依赖）：**
- MOD-DP-008 → MOD-DP-004, MOD-DP-005, MOD-DP-003（API 读路径调用 Repositories）
- MOD-DP-006 → MOD-DP-004（NodeHandlers 写路径调用 AlertRepository）
- MOD-DP-007 → MOD-DP-003（LLMService 写路径调用 LLMCallLogRepository）
- MOD-DP-004 → MOD-DP-001（AlertRepository 依赖 Alert ORM）
- MOD-DP-005 → MOD-WEB-003（ApprovalRepository 依赖 Approval ORM，已有关系）
- MOD-DP-003 → MOD-DP-002（LLMCallLogRepository 依赖 LLMCallLog ORM）

**无循环依赖。** 依赖方向均为：API层/编排层 → Repository层 → ORM层，属于标准分层架构的依赖方向。

---

## 开放问题

| 编号 | 问题 | 状态 |
|------|------|------|
| Q-DP-001 | [ASSUMPTION] alerts.workflow_state JSON 列的最大体积限制建议设为 1MB（基于 Demo 预期最多 20 条 exec_log 记录，每条约 500 字节），SQLite 默认单字段上限为 1GB，1MB 是应用层软限制 | 待 PM 确认 |
| Q-DP-002 | [ASSUMPTION] 输入文件 dp_requirements_spec.md 和 dp_user_stories.md 的 file_header 中 status=DRAFT，但 PM 调用指令明确标注为 APPROVED。本架构设计以 PM 显式批准为准进行了处理 | 待 PM 确认文件状态是否需要更新 |
| Q-DP-003 | [ASSUMPTION] NodeHandlers 中新增的 DB 写操作使用 `SessionLocal()` 新建 session（与现有 _log_node L141, assess_risk L491 模式一致），而非通过依赖注入传递 session。优点是不改变 NodeHandlers 构造函数签名 | 待 PM 确认 |
| Q-DP-004 | [ASSUMPTION] LLMService 新增对 LLMCallLogRepository 的依赖通过构造函数注入（`__init__(self, ..., llm_log_repo=None)`），默认值为 None 时 fallback 到纯内存日志（向后兼容） | 待 PM 确认 |
</file_path>
