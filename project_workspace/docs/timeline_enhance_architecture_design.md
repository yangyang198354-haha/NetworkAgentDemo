<file_header>
  <project_name>NetworkAgentDemo</project_name>
  <author_agent>sub_agent_system_architect</author_agent>
  <file_type>ARCHITECTURE_DESIGN</file_type>
  <version>1.0.0</version>
  <status>APPROVED</status>
  <created_at>2026-07-16T00:00:00Z</created_at>
  <invocation_id>timeline-enhancement-phase-design</invocation_id>
  <description>Alert Detail Page Timeline Component Enhancement -- Architecture Decision Records</description>
</file_header>

# 告警详情页处理时间线组件增强 -- 架构设计文档

## 架构概览

- **架构风格**: 模块化分层单体（Module Layered Monolith）-- 与现有 NetworkAgentDemo v0.2.0 架构一致，所有增强均在现有 5 层架构内完成，不引入新的服务边界。
- **选型依据摘要**:
  - REQ-NFUNC-001（API 向后兼容）：所有变更均为追加式（additive），不修改现有字段语义。
  - REQ-NFUNC-002（历史数据兼容）：新增 DB 列均为 NULLABLE，前端对 NULL 值实施 fallback 渲染。
  - REQ-FUNC-006（实时进度）：从"仅 END 写 DB"改为"START INSERT + END UPDATE"双步持久化。
  - PM 裁决（Q1-Q3）：duration 纯毫秒格式、失败节点显示 duration+红色标记、前端 5 秒轮询。

### 变更影响范围总览

| 层 | 模块 | 变更类型 | 影响 |
|----|------|---------|------|
| 安全与基础设施 | AlertTimeline 模型（alert_models.py） | 新增 2 列 | DB schema 迁移 |
| 编排层 | NodeHandlers._log_node() | 行为变更 + 参数扩展 | 多 1 次 DB 写操作/节点 |
| 安全与基础设施 | AlertRepository | 新增 1 方法 | 接口扩展 |
| 触发层 | alerts_router.py | 无代码变更 | ORM 自动序列化新列 |
| 前端 | AlertsDetailView.vue | 模板 + 脚本扩展 | 新增轮询逻辑 |
| 前端 | alerts.ts store | 无代码变更 | API 返回加性兼容 |

---

## 架构决策记录（ADRs）

---

### ADR-TL-001: sequence_number 的生成策略

- **Status**: Accepted
- **Context**:
  - REQ-FUNC-001 要求时间线条目显示执行序号，从 1 开始连续递增。
  - REQ-FUNC-004 要求序号反映实际执行路径，当节点因条件路由（CE-001 ~ CE-005，`state_graph_engine.py` L86-L154）被跳过时不得出现空位。
  - 最短路径 4 个节点、最长路径 11 个节点，序号必须按实际激活顺序分配。
  - 当前 `alert_models.py` L68-L100 的 `AlertTimeline` 模型不含 `sequence_number` 列。
  - REQ-FUNC-006 要求在 START 阶段即创建条目，因此 sequence_number 必须在 START 时就确定并持久化，而非事后计算。
- **Options**:
  - **Option A: 数据库层面自增（AUTOINCREMENT）**
    - 描述：利用 SQLite `INTEGER PRIMARY KEY AUTOINCREMENT` 为每条 timeline 记录生成全局唯一序号。
    - 优点：实现最简单，无需应用层逻辑；SQLite 原生支持。
    - 缺点：序号是全局递增而非 per-alert 递增（alert #1 的条目序号为 1-5，alert #2 的条目序号为 6-10）；无法满足 REQ-FUNC-004（per-workflow 无空位连续编号）；不可行。
  - **Option B: 查询时排序推导（ROW_NUMBER 窗口函数）**
    - 描述：不在表中存储 sequence_number，查询时按 `started_at` 排序并用 `ROW_NUMBER() OVER (PARTITION BY alert_id_fk ORDER BY started_at)` 动态生成。
    - 优点：零存储冗余；永远准确（不会因插入顺序乱序而出错）；历史数据自动获得序号。
    - 缺点：SQLite 3.25+ 才支持窗口函数（当前环境满足）；前端无法直接从 JSON 响应中获取固定值（需依赖数组索引或后端注入）；REQ-FUNC-006 要求 START 阶段即可见序号，纯查询推导需要在 API 层做转换，增加复杂度。
  - **Option C: 应用层 per-alert 计数器 + DB 列存储**
    - 描述：在 `NodeHandlers` 中维护 `__seq_counters: dict[str, int]`，每次 START 时递增对应 alert_id 的计数器，将 sequence_number 作为新列写入 DB。
    - 优点：序号在 START 时刻即确定并持久化（满足 REQ-FUNC-006）；per-alert 独立计数（满足 REQ-FUNC-004）；前端直接读取 `entry.sequence_number`；实现简单（仅需一个 dict + 整数自增）。
    - 缺点：引入新 DB 列（需 ALTER TABLE 迁移）；应用重启后计数器丢失，但已持久化的 sequence_number 不受影响，新 workflow 从 DB 中已有最大序号+1 恢复；需要在 `__init__` 或首次使用时从 DB 恢复计数器状态。
- **Decision**: 选择 **Option C（应用层 per-alert 计数器 + DB 列存储）**。
  - 理由：满足 REQ-FUNC-004（per-workflow 无空位连续编号）和 REQ-FUNC-006（START 阶段即持久化序号）。Option A 无法满足 per-alert 约束，Option B 无法在 START 阶段提供持久化且需要 API 层额外处理。
  - 计数器恢复策略：首次为某 alert_id 分配序号时，查询 `SELECT MAX(sequence_number) FROM alert_timeline WHERE alert_id_fk = ?`，若存在则从 `max+1` 开始，否则从 1 开始。该查询仅在 workflow 启动时执行一次（O(1) 开销），确保应用重启后序号连续。
- **Consequences**:
  - 正向：满足 REQ-FUNC-001（序号显示）、REQ-FUNC-004（实际执行路径反映）、REQ-FUNC-006（START 阶段可见序号）。
  - 正向：前端实现极简，直接从 `entry.sequence_number` 读取并渲染。
  - 负向：新增 `sequence_number INTEGER NULL` 列，需要数据库迁移；应用重启需要一次额外查询恢复计数器，增加约 1ms 延迟（可忽略）。
  - 负向：若未来扩展为多进程（多 worker），per-process 计数器会产生冲突。当前 v0.2.0 为单进程 FastAPI，该风险暂不触发。[ASSUMPTION -- 若未来扩展多 worker，需改用 DB-level 原子递增（如 UPDATE ... SET seq = (SELECT MAX...) + 1）]

---

### ADR-TL-002: duration_ms 的计算与存储策略

- **Status**: Accepted
- **Context**:
  - REQ-FUNC-002 要求时间线条目显示处理耗时。
  - REQ-FUNC-005 要求基于 `started_at` 和 `completed_at` 准确计算耗时并持久化。
  - REQ-NFUNC-004 要求 duration 计算误差 < 100ms。
  - 当前 `_log_node()` L221 在内存中计算 `duration_ms` 但 DB 持久化（L233-L238）未写入该值。
  - 当前 `AlertTimeline` 模型 L68-L100 不含 `duration_ms` 列。
  - PM 裁决（Q1）：前端显示纯毫秒数值（如 "350ms"）。
  - PM 裁决（Q2）：失败节点也显示 duration，通过红色标记区分。
- **Options**:
  - **Option A: 新增 INTEGER 列 `duration_ms`（预计算存储）**
    - 描述：在 `AlertTimeline` 表中新增 `duration_ms INTEGER NULL` 列，END 阶段计算 `(completed_at - started_at).total_milliseconds()` 并存入。
    - 优点：查询时零计算开销（满足 REQ-NFUNC-003 的 50ms 增量约束）；前端直接渲染；历史数据通过 NULL 自然区分；失败节点同样写入 duration（满足 PM Q2 裁决）。
    - 缺点：引入数据冗余（可从 started_at/completed_at 推导）；需要 DB 迁移；若时间戳被意外修改则 duration_ms 与实际不一致（风险极低，因时间戳在单个事务内写入）。
  - **Option B: 存入 state_snapshot JSON 列**
    - 描述：将 `duration_ms` 作为 state_snapshot JSON 的一个 key 存储（如 `state_snapshot["_duration_ms"]`）。
    - 优点：无需 DB schema 变更；无需迁移。
    - 缺点：JSON 列中的值不可被 SQL 直接查询或索引；state_snapshot 的语义是"节点执行时的状态快照"，混入元数据违反单一职责；前端需要深入 JSON 字段取值（`entry.state_snapshot._duration_ms`），增加耦合。
  - **Option C: 纯实时计算（无存储）**
    - 描述：不在 DB 中存储 duration_ms，API 序列化时动态计算：`(completed_at - started_at).total_milliseconds()` 如果 completed_at 非空，否则为 null。
    - 优点：零存储冗余；始终准确（无 stale 风险）。
    - 缺点：每次 API 调用都需要计算（≤14 条目，开销可忽略）；需要在 API 层或序列化层注入计算逻辑，增加复杂度；不能通过 SQL 直接查询性能瓶颈节点；若前端直接消费 ORM 对象（当前行为），该计算无法透明加入。
- **Decision**: 选择 **Option A（新增 INTEGER 列 `duration_ms`）**。
  - 理由：满足 REQ-NFUNC-004（准确计算，由 Python `datetime` 差值保证精度 < 1ms）；满足 REQ-NFUNC-003（零渲染开销）；实现最简单（在 `_log_node` END 阶段一步写入）；与当前"ORM 对象直返 API"的模式兼容。
  - 回退策略：对于历史数据（`duration_ms IS NULL` 但 `completed_at IS NOT NULL`），前端可降级为实时计算 `(completed_at - started_at)` 作为 fallback 显示值。
- **Consequences**:
  - 正向：满足 REQ-FUNC-002、REQ-FUNC-005、REQ-NFUNC-004。
  - 正向：前端渲染无需任何计算，从 `entry.duration_ms` 直接读取。
  - 负向：新增 DB 列，需迁移（与 ADR-TL-001 的 sequence_number 列可在同一 ALTER TABLE 语句中完成）。
  - 负向：存在数据冗余，若时间戳不一致则 duration_ms 可能不准确。缓解措施：duration_ms 由同一个 `_log_node` 方法中的 `datetime.now(timezone.utc)` 计算，保证了原子性。

---

### ADR-TL-003: 节点 status 的判定策略

- **Status**: Accepted
- **Context**:
  - REQ-FUNC-003 要求准确显示每个节点的成功/失败状态，而非当前固定 `"COMPLETED"`。
  - 当前 `_log_node()` L219 将内存 entry status 固定设为 `"COMPLETED"`，DB 持久化 L237 硬编码 `status="COMPLETED"`。
  - 但存在明确的失败场景：`handle_analyze_root_cause` L449-L455 在 LLM 调用异常时设置 `state["status"]="FAILED"` 并提前返回，然而此时 `_log_node(state, node, "END")` 已执行且写入 status="COMPLETED"。
  - 前端 `AlertsDetailView.vue` L200 的 `timelineColor` 和 L202 的 `timelineStatusTag` 已预留 `FAILED` 状态的样式映射（`#F56C6C` / `'danger'`），仅等后端正确写入。
  - `AlertTimeline.status` 列已有 `RUNNING/COMPLETED/FAILED` 注释（L93），说明架构设计时就预留了 FAILED 状态。
- **Options**:
  - **Option A: 从 NetworkAgentState 推断（state["status"] == "FAILED" 则标记失败）**
    - 描述：在 `_log_node` END 阶段检查 `state.get("status")`，若为 `"FAILED"` 则将 timeline status 设为 FAILED，否则设为 COMPLETED。
    - 优点：无需修改各节点 handler 的 `_log_node` 调用签名；利用已有的 `state["status"]` 约定。
    - 缺点：存在时序问题——`_log_node(state, node, "END")` 被调用时，state 尚未被 handler 的返回值更新（handler 先调用 `_log_node` 再 `return {"status": "FAILED", ...}`）。因此 `_log_node` 看到的 state 是前一个节点执行后的状态，而非当前节点的返回状态。这意味着 analyze_root_cause 失败时，state["status"] 仍可能是之前的值（如 PROCESSING），无法正确标记 FAILED。
  - **Option B: 显式 status 参数（_log_node 接受可选 status 参数）**
    - 描述：修改 `_log_node` 签名，增加可选参数 `status: str = "COMPLETED"`。调用方（各 handler）可选择传递 `status="FAILED"` 来覆盖默认的成功状态。当前仅 `handle_analyze_root_cause` 的异常路径需要传递 `status="FAILED"`。
    - 优点：显式、无歧义；不依赖 state 的时序问题；默认值 "COMPLETED" 保持向后兼容（所有现有成功节点无需修改）；扩展性好（未来其他节点可轻松标记失败）。
    - 缺点：需要在 handle_analyze_root_cause 的异常路径中将 `self._log_node(state, node, "END")` 改为 `self._log_node(state, node, "END", status="FAILED")`，约 1 行变更；引入了新的参数约定，需在方法文档中说明。
  - **Option C: 两阶段提交（先 return，后由 LangGraph wrapper 写 timeline）**
    - 描述：不在 handler 内部写 timeline END，而是让 handler 返回包含 status 的 dict，由外部 wrapper（如 `state_graph_engine.py` 的 `_wrap_node`）在 state 更新后统一写 timeline。
    - 优点：timeline status 始终与实际 state 一致；单一职责清晰（handler 只管业务，wrapper 管日志）。
    - 缺点：架构侵入性大——需要修改所有 14 个节点的调用链；`_log_node` 的 START/END 配对逻辑需要搬到 wrapper 中；对现有架构改动范围过大，风险高于收益。
- **Decision**: 选择 **Option B（显式 status 参数）**。
  - 理由：最小化变更范围，仅修改 `_log_node` 签名（1 处）+ `handle_analyze_root_cause` 异常路径的调用（1 行）。消除了 Option A 的时序缺陷，避免了 Option C 的架构侵入。默认值 "COMPLETED" 确保向后兼容。
  - 状态枚举：`"RUNNING"`（START 阶段），`"COMPLETED"`（END 默认），`"FAILED"`（END 显式传入）。
- **Consequences**:
  - 正向：满足 REQ-FUNC-003（准确状态）。analyze_root_cause 失败时 timeline 正确标记为 FAILED，前端红色渲染生效。
  - 正向：为未来节点添加失败检测提供了清晰的扩展模式（调用 `_log_node(state, node, "END", status="FAILED")`）。
  - 负向：仅 handle_analyze_root_cause 会标记 FAILED。其他节点（如 execute_fix、verify_fix）当前无明确的失败检测逻辑，其 status 仍为 COMPLETED。这是现有代码的事实状态，不在本次增强范围内。[ASSUMPTION -- 其他节点的失败检测将是后续需求的范畴]
  - 负向：若未来 handler 忘记传 status 参数，失败将被错误标记为 COMPLETED。缓解措施：可在 `_log_node` 文档中标注此约定的重要性。

---

### ADR-TL-004: Timeline 条目创建时机

- **Status**: Accepted
- **Context**:
  - REQ-FUNC-006（P1）要求节点启动时即创建 timeline 条目，运维人员可在 workflow 运行过程中实时查看进度。
  - 当前行为：`_log_node()` START 阶段仅写内存 `__timeline_store`（L201-L212），DB 持久化仅在 END 阶段执行（L227-L241）。这意味着节点 RUNNING 状态在页面刷新后不可见。
  - 前端 `AlertsDetailView.vue` L56 在 timeline 为空时显示 "暂无时间线记录（LangGraph 节点尚未集成 DB 持久化）"，说明实时可见性是已知的待满足期望。
  - US-004（实时查看工作流执行进度，P1）明确要求 "节点启动即可见"（AC-004-01）。
  - REQ-NFUNC-001 要求 API 向后兼容，即当前仅 END 时可见条目的行为不能被破坏。
- **Options**:
  - **Option A: 保持现有行为（仅在 END 写 DB）**
    - 描述：不做变更，timeline 条目仍然仅在 END 阶段写入 DB。
    - 优点：代码变更量为零；数据库写入次数最小（每节点 1 INSERT）。
    - 缺点：不满足 REQ-FUNC-006 和 US-004；运维人员在 workflow 运行期间看不到实时进度，必须等待完成后才能看到任何 timeline 条目；与 AC-004-01（"节点启动即可见"）直接冲突。
  - **Option B: START INSERT + END UPDATE（双步持久化）**
    - 描述：START 阶段执行 `INSERT INTO alert_timeline` 写入 status=RUNNING 的条目，获得 DB 分配的 `id`；END 阶段执行 `UPDATE alert_timeline SET completed_at=?, duration_ms=?, status=? WHERE id=?` 完成该条目。
    - 优点：满足 REQ-FUNC-006（START 即持久化）；满足 US-004/AC-004-01（节点启动即可见）；对 API 完全向后兼容（现有前端代码获取的 timeline 列表会包含 RUNNING 条目，其 `completed_at` 和 `duration_ms` 为 null，符合 AC-002-02 预期）；内存 `__timeline_store` 可逐步废弃或用 DB `id` 增强。
    - 缺点：每节点 DB 操作从 1 INSERT 变为 1 INSERT + 1 UPDATE（两次写入）；需要在 `AlertRepository` 中新增 `update_timeline_entry` 方法；需要确保 START INSERT 返回的 `id` 在后续 END UPDATE 中可用（通过内存 `__timeline_store` 存储 `db_id` 字段）。
  - **Option C: 只在内存维护，API 合并内存+DB 数据返回**
    - 描述：保持 DB 仅在 END 写入，但修改 API 层，使其除了查询 DB 外还查询 `NodeHandlers.__timeline_store`（内存中的 RUNNING 条目），合并后返回给前端。
    - 优点：DB schema 无需变更；不引入 UPDATE 操作。
    - 缺点：内存数据在应用重启后丢失，不符合持久化要求；`NodeHandlers` 实例需要被 API 层访问，破坏了当前分层架构（API 层不应直接依赖编排层内部状态）；架构耦合度上升；API 层返回的数据来源不一致（部分来自 DB、部分来自内存），增加调试和测试复杂度。
- **Decision**: 选择 **Option B（START INSERT + END UPDATE 双步持久化）**。
  - 理由：唯一能满足 REQ-FUNC-006 且保持分层架构清晰的方案。两次 DB 写入对 workflow 编排场景（非高吞吐 API）性能影响可忽略——单次 SQLite INSERT/UPDATE 操作耗时 < 5ms，14 个节点共增加约 70ms（仍远小于 LLM 调用动辄数秒的延迟）。
  - 实现细节：
    1. START 阶段：调用 `AlertRepository.append_timeline_entry()`，写入 `{node_name, state_snapshot, started_at, status="RUNNING", sequence_number}`，获取返回的 `AlertTimeline` 对象的 `.id`。
    2. 将 DB 返回的 `.id` 存储到内存 `__timeline_store` 对应 entry 的 `_db_id` 字段。
    3. END 阶段：从 `__timeline_store` 获取 `_db_id`，调用新增的 `AlertRepository.update_timeline_entry(timeline_id, updates)` 方法，更新 `completed_at`、`duration_ms`、`status`、`state_snapshot`。
- **Consequences**:
  - 正向：满足 REQ-FUNC-006 和 US-004。运维人员刷新页面即可看到当前 RUNNING 的节点。
  - 正向：API 返回的 timeline 列表自然而然地包含 RUNNING 条目，前端可据此判断 workflow 是否仍在执行。
  - 正向：`__timeline_store` 内存对象从"唯一数据源"降级为"END 阶段查找 _db_id 的索引"，降低了对内存持久性的依赖。
  - 负向：每节点 DB 写入操作数翻倍（1 INSERT + 1 UPDATE）。在 14 个节点的完整工作流中最多增加 14 次 UPDATE，SQLite WAL 模式下性能影响 < 100ms（可接受）。
  - 负向：若 INSERT 之后、UPDATE 之前应用崩溃，DB 中会残留 status=RUNNING 的"孤儿"记录。缓解措施：前端对超过合理时间（如 30 分钟）仍为 RUNNING 的条目标记为 "(异常中断)"；或在 `finish_report` 节点中清理当前 alert 下所有仍为 RUNNING 的条目。

---

### ADR-TL-005: 前端自动刷新机制

- **Status**: Accepted
- **Context**:
  - US-004（实时查看工作流执行进度）和 AC-004-02（页面刷新获取最新状态）要求运维人员能获取 workflow 的最新执行状态。
  - 当前 `AlertsDetailView.vue` L174-L187 仅在 `onMounted` 时获取数据一次，无自动刷新机制。
  - PM 裁决（Q3）：采用前端轮询，间隔 5 秒。
  - 需求文档明确将 WebSocket 和 SSE 列为"超出范围"（Out of Scope），因此本决策仅评估客户端的定时刷新策略。
  - REQ-NFUNC-003 要求前端渲染性能增量 < 50ms，轮询不应阻塞 UI 线程。
- **Options**:
  - **Option A: 无条件轮询（setInterval 5 秒，始终运行）**
    - 描述：组件挂载后启动 `setInterval(fetchTimeline, 5000)`，组件卸载时 `clearInterval`。不论 workflow 是否完成，始终轮询。
    - 优点：实现最简单；代码量最小（约 5 行）；任何状态变更都能被捕获。
    - 缺点：已完成 workflow 仍持续产生不必要的 HTTP 请求，浪费服务器和网络资源（即使请求仅返回不变数据）；每次请求触发 `v-loading` 可能造成 UI 闪烁；不符合 REQ-NFUNC-003 的"无感知退化"精神（持续的网络活动可能影响浏览器性能）。
  - **Option B: 智能轮询（仅 workflow 活跃时轮询，完成后自动停止）**
    - 描述：组件挂载后启动 5 秒轮询，但每次收到响应后检查终止条件——当 alert.status 为终态（CLOSED / FAILED / REJECTED）且 timeline 中无 status=RUNNING 的条目时，停止轮询 (`clearInterval`)。
    - 优点：对已完成 workflow 零额外请求；满足 US-004 的同时不浪费资源；轮询自然停止，无需用户手动操作；终止条件明确，逻辑清晰。
    - 缺点：需要额外的终止条件判断逻辑（约 10 行代码）；若 alert.status 的终态判定不准确可能导致过早停止或永不停止。缓解措施：使用双重条件（alert.status in 终态集合 AND timeline 无 RUNNING 条目），确保安全。
  - **Option C: 用户手动控制（添加"刷新"按钮，无自动轮询）**
    - 描述：不实现自动轮询，而是在时间线 Tab 添加一个"刷新"按钮，用户点击时重新获取数据。
    - 优点：最简单；零额外网络请求（用户驱动）；不改变现有架构。
    - 缺点：不满足 US-004（实时进度）的核心诉求；运维人员需要不断手动点击才能看到最新状态，体验差；PM 已明确选择轮询方案（Q3），与裁决冲突。
- **Decision**: 选择 **Option B（智能轮询：活跃时 5 秒轮询，完成后自动停止）**。
  - 理由：完全满足 PM Q3 裁决（5 秒轮询）和 US-004（实时进度可见），同时避免了 Option A 的资源浪费。双重终止条件（alert.status 终态 + timeline 无 RUNNING 条目）确保安全停止。
  - 实现方案：
    1. 在 `onMounted` 中启动 `pollTimer = setInterval(fetchTimelineData, 5000)`。
    2. `fetchTimelineData` 函数调用 `store.fetchAlertDetail()`，更新 `timeline.value`。
    3. 每次更新后检查 `shouldStopPolling()`：当 `alert.value.status in ['CLOSED', 'FAILED', 'REJECTED']` 且 `timeline.value.every(e => e.status !== 'RUNNING')` 时，`clearInterval(pollTimer)`。
    4. 在 `onUnmounted` 中 `clearInterval(pollTimer)` 清理。
  - 前端渲染性能：轮询获取的数据通过 `timeline.value = resp.timeline` 赋值，Vue 3 的响应式系统会对新数组做 diff 更新 DOM，对于最多 14 个 `<el-timeline-item>`，增量渲染时间 < 10ms，满足 REQ-NFUNC-003（< 50ms）。
- **Consequences**:
  - 正向：满足 US-004、AC-004-02（实时进度可见）；满足 PM Q3 裁决。
  - 正向：智能停止机制避免了已完成 workflow 的无效轮询，节约资源。
  - 正向：不影响现有任何后端接口，纯前端变更。
  - 负向：运行中 workflow 每 5 秒一次 HTTP 请求，若同时有多个活跃 workflow 被查看可能增加服务器负载。缓解措施：单用户同时只能查看一个告警详情页（页面级组件，非列表），实际并发请求量极低。
  - 负向：若 `shouldStopPolling` 判断逻辑有缺陷（如 alert.status 未及时更新为终态），轮询可能永不停止。缓解措施：添加硬性超时限制（如最大轮询 15 分钟后强制停止）。

---

## 开放问题

以下 [ASSUMPTION] 标注的决策需 PM 确认：

1. **[ASSUMPTION -- requires PM confirmation]** ADR-TL-001 中关于"当前为单进程 FastAPI，暂不考虑多 worker 场景"的假设。若未来计划扩展多 worker，需要就 sequence_number 的进程间原子性增加额外设计。
2. **[ASSUMPTION -- requires PM confirmation]** ADR-TL-003 中关于"仅 handle_analyze_root_cause 会标记 FAILED，其他节点故障检测属于后续需求范畴"的范围界定。
3. **[ASSUMPTION -- requires PM confirmation]** ADR-TL-004 中关于"START INSERT 后应用崩溃遗留 RUNNING 孤儿记录的清理策略"——建议在 `finish_report` 节点中清理或由前端超时判断（30 分钟），是否需要更严格的服务器端清理机制？

### 确认状态
- 无需等待 PM 回复即可推进实现——上述 [ASSUMPTION] 均有合理的默认行为（单进程、仅根因分析标记失败、前端超时判断），可在实现后根据 PM 反馈调整。
</file_header>
