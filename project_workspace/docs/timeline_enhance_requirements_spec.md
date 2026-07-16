<file_header>
  <project_name>NetworkAgentDemo</project_name>
  <author_agent>sub_agent_requirement_analyst</author_agent>
  <file_type>REQUIREMENTS_SPEC</file_type>
  <version>0.1.0</version>
  <status>DRAFT</status>
  <created_at>2026-07-16T00:00:00Z</created_at>
  <invocation_id>timeline-enhancement-phase-requirements</invocation_id>
  <description>Alert Detail Page Timeline Component Enhancement — Requirements Specification</description>
</file_header>

# 告警详情页处理时间线（Timeline）组件增强 — 需求规格说明书

## 执行摘要

- **业务背景**：NetworkAgentDemo (v0.2.0) 是一个 LangGraph 网络自动化 Agent，通过 14 节点状态机实现 "告警->诊断->修复->验证->关闭" 全流程自动化。当前 WebUI 告警详情页的 "处理时间线" Tab 已使用 Element Plus `<el-timeline>` 组件展示各节点执行情况，但缺少序号、耗时及精确的成功/失败状态，导致运维人员无法快速理解工作流的实际执行顺序、定位性能瓶颈和识别失败节点。
- **需求总览**：功能需求 6 条（REQ-FUNC-001 ~ REQ-FUNC-006），非功能需求 4 条（REQ-NFUNC-001 ~ REQ-NFUNC-004）。
- **推断性需求**：0 条。所有需求均有直接来源（用户原始需求或 PM 代码分析中的具体文件+行号）。

---

## 功能需求（Functional Requirements）

### REQ-FUNC-001: 时间线条目显示执行序号

| 字段 | 内容 |
|------|------|
| ID | REQ-FUNC-001 |
| 描述 | 系统应当在告警详情页的 "处理时间线" 中，为每条时间线条目显示其在本次 workflow 实际执行路径中的顺序编号（sequence_number），从 1 开始递增。 |
| 来源引用 | **用户原始需求**："显示 LangGraph 状态机节点跳转的序号（节点执行顺序）" |
| 优先级 | Must Have |
| 备注 | — |

**推理依据**：
1. 用户明确要求显示节点执行序号。`state_graph_engine.py` L85-L157 定义了 5 条条件边（CE-001 ~ CE-005），实际激活的节点集合取决于告警有效性、根因分析结果、风险评估结果、审批决定及备份结果，并非所有 14 个节点都执行。因此 sequence_number 必须反映"实际执行顺序"而非"预定义节点列表中的固定索引"。
2. 当前 `node_handlers.py` L192-L242（`_log_node` 方法）及 `alert_models.py` L68-L100（`AlertTimeline` 模型）均不含 `sequence_number` 字段。

---

### REQ-FUNC-002: 时间线条目显示处理耗时

| 字段 | 内容 |
|------|------|
| ID | REQ-FUNC-002 |
| 描述 | 系统应当在告警详情页的 "处理时间线" 中，为每条已完成的时间线条目显示其处理耗时（duration），以毫秒（ms）或合适的可读格式呈现。 |
| 来源引用 | **用户原始需求**："显示每个状态节点处理消耗的时间（duration）" |
| 优先级 | Must Have |
| 备注 | — |

**推理依据**：
1. 用户明确要求显示 duration。当前后端 `node_handlers.py` L221 已在内存中计算 `duration_ms`，并在 `_timeline_store` 中存储，但 `alert_models.py` L68-L100 的 `AlertTimeline` 表模型**缺少 `duration_ms` 列**，`_log_node` 方法 L233-L238 在持久化到 SQLite 时**未写入 duration_ms**。
2. 数据库持久化仅在 END 阶段执行（`node_handlers.py` L227-L241），前端通过 API 获取数据（`alerts_router.py` L75 调用 `repo.get_alert_timeline`），因此 duration 必须持久化到数据库才能在前端展示。

---

### REQ-FUNC-003: 时间线条目显示成功/失败状态

| 字段 | 内容 |
|------|------|
| ID | REQ-FUNC-003 |
| 描述 | 系统应当在告警详情页的 "处理时间线" 中，准确显示每个节点的处理结果是成功还是失败，状态值与实际 workflow 执行结果一致。 |
| 来源引用 | **用户原始需求**："显示每个状态节点的处理结果是成功还是失败（status）" |
| 优先级 | Must Have |
| 备注 | — |

**推理依据**：
1. 用户明确要求显示成功/失败状态。当前 `_log_node` 方法（`node_handlers.py` L219）在 END 阶段将内存中的 entry status 固定设为 `"COMPLETED"`，数据库持久化（L233-L238）也硬编码为 `"COMPLETED"`，完全不区分节点的实际执行结果。
2. 存在明确的失败场景未被反映：`node_handlers.py` L449-L455（`handle_analyze_root_cause`）在 LLM 调用失败时设置 `state["status"] = "FAILED"`，但该节点的 timeline entry 仍被标记为 `"COMPLETED"`。前端 `AlertsDetailView.vue` L200 的 `timelineColor` 和 L202 的 `timelineStatusTag` 已预留 `FAILED` 状态的颜色映射（`#F56C6C` / `'danger'`），但后端从未写入该状态。

---

### REQ-FUNC-004: 序号反映实际执行路径

| 字段 | 内容 |
|------|------|
| ID | REQ-FUNC-004 |
| 描述 | 系统应当确保 sequence_number 反映每次 workflow 调用的实际节点激活顺序，而非 14 个节点的预定义固定列表。当节点因条件路由被跳过时，sequence_number 不得出现空位。 |
| 来源引用 | **PM 分析**："LangGraph workflow 有 14 个节点但并非全部都会执行（取决于条件路由），sequence_number 需要反映实际执行顺序而非预定义列表"；证据：`state_graph_engine.py` L86-L153 定义了 5 条条件边 |
| 优先级 | Must Have |
| 备注 | — |

**推理依据**：
- `state_graph_engine.py` L86-L93：`validate_alert` 条件路由（is_valid=false -> 跳过 get_device_info ~ verify_fix，直接到 finish_report）
- `state_graph_engine.py` L101-L108：`analyze_root_cause` 条件路由（status=FAILED -> 跳过 generate_fix_plan ~ verify_fix）
- `state_graph_engine.py` L113-L120：`assess_risk` 条件路由（不需要审批 -> 跳过 human_approval）
- `state_graph_engine.py` L147-L154：`human_approval` 条件路由（REJECTED -> 跳过 backup_config ~ verify_fix）
- `state_graph_engine.py` L124-L131：`backup_config` 条件路由（备份失败 -> 跳过 execute_fix ~ verify_fix）

不同路径的激活节点数差异显著，最短路径仅 4 个节点（receive_alert -> parse_alert -> validate_alert -> finish_report），最长路径可达 11 个节点。

---

### REQ-FUNC-005: 处理耗时准确计算

| 字段 | 内容 |
|------|------|
| ID | REQ-FUNC-005 |
| 描述 | 系统应当基于节点的 `started_at` 和 `completed_at` 时间戳准确计算每个节点的处理耗时，并持久化存储该值。 |
| 来源引用 | **PM 分析**："当前 duration_ms 只在内存中计算但未持久化到数据库"；证据：`node_handlers.py` L221（内存写入）vs L233-L238（DB 写入缺少 duration_ms） |
| 优先级 | Must Have |
| 备注 | 关联 REQ-FUNC-002，是该需求的实现前提。 |

**推理依据**：
- `node_handlers.py` L206-L212（START 阶段）：记录 `started_at` 时间戳
- `node_handlers.py` L218-L222（END 阶段）：在内存中计算 `duration_ms`，更新 `completed_at`
- `node_handlers.py` L233-L238（DB 持久化）：未写入 `duration_ms` 字段
- `alert_models.py` L88-L89：`completed_at` 字段存在（`DateTime, nullable=True`），可作为 duration 计算依据
- 数据准确性要求：若 `started_at` 和 `completed_at` 都非空，duration 应等于两者差值；若 `completed_at` 为空（节点仍在运行），duration 应标记为不可用。

---

### REQ-FUNC-006: 节点启动时即创建时间线条目

| 字段 | 内容 |
|------|------|
| ID | REQ-FUNC-006 |
| 描述 | 系统应当在每个 LangGraph 节点开始执行时就创建时间线条目（status=RUNNING），以便运维人员在 workflow 运行过程中实时查看进度。 |
| 来源引用 | **PM 分析**："DB 持久化仅在 END 阶段执行，START 时只写内存"；证据：`node_handlers.py` L201-L212（START 仅写内存 `_timeline_store`）、L227-L241（DB 写入仅在 END 阶段） |
| 优先级 | Should Have |
| 备注 | 当前前端 `AlertsDetailView.vue` L56 在 timeline 为空时显示 "暂无时间线记录（LangGraph 节点尚未集成 DB 持久化）"，说明实时进度可见性是已知的用户期望。 |

---

## 非功能需求（Non-Functional Requirements）

### REQ-NFUNC-001: API 向后兼容 — 不破坏现有响应格式

| 字段 | 内容 |
|------|------|
| ID | REQ-NFUNC-001 |
| 描述 | 系统应当在现有 API 端点（`GET /api/alerts/{alert_id}` 和 `GET /api/alerts/{alert_id}/workflow`）的返回结构中**追加**新字段（sequence_number、duration_ms），不得删除或修改已有字段的名称、类型和语义，确保现有前端消费者不做任何改动即可继续正常工作。 |
| 来源引用 | **PM 要求**："需要向后兼容：现有 API 返回格式不能破坏性变更"；证据：`alerts_router.py` L143-L150 返回 `alert, timeline, fix_plan, commands, llm_calls, approval`；`AlertsDetailView.vue` L177-L183 解构 `resp.timeline` 等多个字段 |
| 优先级 | Must Have |
| 备注 | — |

---

### REQ-NFUNC-002: 历史数据兼容 — 旧 timeline 记录不报错

| 字段 | 内容 |
|------|------|
| ID | REQ-NFUNC-002 |
| 描述 | 系统应当确保在增强之前创建的 timeline 记录（不含 sequence_number、duration_ms 字段，或这些字段为 NULL）在查询和展示时不会导致后端异常或前端 JavaScript 错误。 |
| 来源引用 | **PM 要求**："向后兼容现有数据：未增强前创建的 timeline 记录不应报错"；证据：`alert_models.py` L68-L100（现有 AlertTimeline 模型不含 sequence_number 和 duration_ms 列） |
| 优先级 | Must Have |
| 备注 | 包含两个层面：(a) 数据库层面——新增列需设置 DEFAULT 值或允许 NULL，已存在的行自动填充默认值；(b) 前端层面——当这些字段缺失或为 null 时，组件应有合理的 fallback 展示（如隐藏序号、显示 "-"）。 |

---

### REQ-NFUNC-003: 前端渲染性能

| 字段 | 内容 |
|------|------|
| ID | REQ-NFUNC-003 |
| 描述 | 系统应当确保在时间线新增 sequence_number 和 duration 字段后，前端 timeline 组件（Element Plus `<el-timeline>`）的渲染时间不出现可感知的退化。单次 workflow 最多 14 个节点，增强后页面加载时间增量应不超过 50ms。 |
| 来源引用 | **PM 要求**："性能（前端渲染）"；证据：`AlertsDetailView.vue` L41-L54 使用 `v-for` 遍历 `timeline` 数组渲染 `<el-timeline-item>`，单个 alert 的 timeline 条目数最多等于实际执行的节点数（≤14） |
| 优先级 | Should Have |
| 备注 | — |

---

### REQ-NFUNC-004: 数据准确性 — Duration 计算

| 字段 | 内容 |
|------|------|
| ID | REQ-NFUNC-004 |
| 描述 | 系统应当确保 timeline entry 的 duration_ms 值与 `started_at` 和 `completed_at` 时间戳之间的差值一致，误差不超过 100ms。对于 `completed_at` 为 NULL 的条目（节点仍在运行），duration_ms 应为 NULL 或明确标记为不可用。 |
| 来源引用 | 推导自 REQ-FUNC-005；**PM 分析**："当前不计算或存储 duration"；证据：`alert_repository.py` L164-L173 的 `append_timeline_entry` 仅按传入 dict 创建记录，不做 duration 计算 |
| 优先级 | Must Have |
| 备注 | — |

---

## 超出范围（Out of Scope）

以下功能明确不在本次增强范围内：

1. **工作流可视化流程图**：本次仅增强现有 timeline 组件（列表式条目），不涉及 DAG 图或流程图形式的节点关系可视化。
2. **节点执行日志详情展开**：不涉及在 timeline 条目中内嵌节点执行的详细日志、LLM prompt/response 等内容（该内容在 "LLM调用详情" Tab 中已有独立展示）。
3. **Timeline 导出功能**：不涉及将时间线导出为 PDF、CSV 或其他格式。
4. **多告警对比时间线**：不涉及同时展示多个告警的时间线进行横向对比。
5. **实时 WebSocket 推送**：不涉及通过 WebSocket 实时推送 timeline 更新（继续使用现有的轮询/Ajax 刷新机制）。

---

## 待确认推断项

（无）—— 所有 10 条需求均直接锚定至用户原始需求或 PM 提供的代码分析证据（具体文件+行号），无止推断性需求。

---

## 开放问题

以下问题需 PM 进一步澄清后纳入需求：

1. **Q1 — Duration 显示格式**：duration_ms 在前端应以何种格式展示？候选方案：(a) 纯毫秒数值（如 "350ms"），(b) 自适应格式（<1s 显示 ms，>=1s 显示 "1.2s"），(c) 带单位的精确值（如 "350 毫秒"）。当前用户需求仅描述 "消耗的时间（duration）"，未指定格式。

2. **Q2 — 失败节点的 Duration 语义**：当节点因异常而失败时（如 LLM 调用超时），其 duration 是否仍应显示？若显示，应如何与成功节点的 duration 区分（如用不同颜色或附加 "（异常中断）" 标记）？

3. **Q3 — RUNNING 状态的实时刷新策略**：对于正在执行的 workflow，前端是否需要自动刷新 timeline（如每 5 秒轮询一次），还是仅依赖用户手动刷新页面？当前 `AlertsDetailView.vue` 仅在 `onMounted` 时获取数据一次（L174-L187）。
