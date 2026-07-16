<file_header>
  <project_name>NetworkAgentDemo</project_name>
  <author_agent>sub_agent_system_architect</author_agent>
  <file_type>MODULE_DESIGN</file_type>
  <version>1.0.0</version>
  <status>APPROVED</status>
  <created_at>2026-07-16T00:00:00Z</created_at>
  <invocation_id>timeline-enhancement-phase-design</invocation_id>
  <description>Alert Detail Page Timeline Component Enhancement -- Module Design with Typed Interface Contracts</description>
</file_header>

# 告警详情页处理时间线组件增强 -- 模块设计文档

## 模块总览

| MOD-ID | 模块名 | 层级 | 职责 | 依赖模块 |
|--------|--------|------|------|----------|
| MOD-TL-001 | AlertTimeline 模型增强 | 安全与基础设施（DB） | 新增 sequence_number、duration_ms 列，提供 DB schema 迁移 | 无（基础设施层） |
| MOD-TL-002 | NodeHandlers._log_node() 增强 | 编排层 | 扩展日志方法：per-alert 计数器、status 参数、START 即写 DB | MOD-TL-003 |
| MOD-TL-003 | AlertRepository 增强 | 安全与基础设施（Repository） | 新增 update_timeline_entry 方法，startup schema 迁移 | MOD-TL-001 |
| MOD-TL-004 | API 响应格式扩展 | 触发层（API） | 无需代码变更：ORM 新列自动序列化，保证向后兼容 | MOD-TL-003 |
| MOD-TL-005 | 前端 Timeline 组件增强 | 前端（View） | 渲染 sequence_number、duration_ms、实时状态、智能轮询 | MOD-TL-007 |
| MOD-TL-006 | 前端自动刷新机制 | 前端（View） | 5 秒智能轮询 + 自动停止逻辑 | MOD-TL-007 |
| MOD-TL-007 | API 客户端增强 | 前端（Store） | 无需代码变更：新字段自动通过 JSON 解构传递 | 无 |

### 需求覆盖矩阵

| 需求 ID | 覆盖模块 | 覆盖方式 |
|---------|---------|---------|
| REQ-FUNC-001 | MOD-TL-001, MOD-TL-002, MOD-TL-005 | DB 列 + 应用计数器 + 前端渲染 |
| REQ-FUNC-002 | MOD-TL-001, MOD-TL-002, MOD-TL-005 | DB 列 + END 计算 + 前端渲染 |
| REQ-FUNC-003 | MOD-TL-002, MOD-TL-005 | _log_node status 参数 + 前端 color/tag 映射 |
| REQ-FUNC-004 | MOD-TL-002 | Per-alert 计数器确保无空位 |
| REQ-FUNC-005 | MOD-TL-002 | started_at/completed_at 差值计算 + 持久化 |
| REQ-FUNC-006 | MOD-TL-002, MOD-TL-003 | START INSERT + END UPDATE 双步持久化 |
| REQ-NFUNC-001 | MOD-TL-004 | ORM 加性序列化，现有字段不变 |
| REQ-NFUNC-002 | MOD-TL-001, MOD-TL-005 | NULLABLE 列 + 前端 fallback |
| REQ-NFUNC-003 | MOD-TL-005, MOD-TL-006 | 预计算 duration + Vue 3 增量渲染 + 条件轮询 |
| REQ-NFUNC-004 | MOD-TL-002 | Python datetime 差值精度 < 1ms |

**覆盖率**：10/10 = 100%

---

## 模块详情

---

### MOD-TL-001: AlertTimeline 模型增强（DB Schema 变更）

- **职责**: 在 `alert_timeline` 表中新增 `sequence_number` 和 `duration_ms` 两个可空列，为数据持久化提供存储结构。
- **覆盖需求**: REQ-FUNC-001, REQ-FUNC-002, REQ-NFUNC-002
- **文件位置**: `src/database/alert_models.py`（`AlertTimeline` 类）
- **变更类型**: 模型定义扩展 + DB schema 迁移（ALTER TABLE ADD COLUMN）

**公开接口契约:**

```
IFC-TL-001-01: AlertTimeline.sequence_number
  类型: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=None)
  约束: NULLABLE（历史数据兼容），per-alert 从 1 递增，无空位
  默认: NULL
  语义: 告警 workflow 中该节点的实际执行序号

IFC-TL-001-02: AlertTimeline.duration_ms
  类型: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=None)
  约束: NULLABLE（历史数据兼容），非负整数，单位毫秒
  默认: NULL
  语义: 节点从 started_at 到 completed_at 的处理耗时

IFC-TL-001-03: DB Migration (schema upgrade)
  执行时机: 应用启动时（在 create_all() 之前）
  方法: 检测列是否存在，若不存在则 ALTER TABLE ADD COLUMN
  SQL模板:
    ALTER TABLE alert_timeline ADD COLUMN sequence_number INTEGER;
    ALTER TABLE alert_timeline ADD COLUMN duration_ms INTEGER;
```

**依赖模块**: 无（基础设施层，被 MOD-TL-002、MOD-TL-003 所依赖）

**外部依赖**: SQLAlchemy 2.0 ORM（已有），SQLite 3.x（已有）

**历史数据兼容（REQ-NFUNC-002）**:
- 已存在的行：`sequence_number` 和 `duration_ms` 自动填充为 NULL（ALTER TABLE ADD COLUMN 的默认行为）。
- API 序列化时 NULL 值被 JSON 序列化为 `null`（Python `None` -> JSON `null`）。
- 前端对 `null` / `undefined` 值实施 fallback 渲染（见 MOD-TL-005）。

---

### MOD-TL-002: NodeHandlers._log_node() 增强

- **职责**: 扩展 `_log_node()` 方法，支持 per-alert 序号计数器、显式 status 参数、START 阶段 DB 写入、END 阶段 DB 更新 + duration 计算。
- **覆盖需求**: REQ-FUNC-001, REQ-FUNC-002, REQ-FUNC-003, REQ-FUNC-004, REQ-FUNC-005, REQ-FUNC-006
- **文件位置**: `src/orchestration/node_handlers.py`（`NodeHandlers` 类）
- **变更类型**: 方法签名扩展 + 行为变更 + 新增实例属性

**公开接口契约:**

```
IFC-TL-002-01: _log_node(state, node_name, phase, duration_ms=0, status="COMPLETED")
  参数扩展:
    - status: str = "COMPLETED"  --  NEW，节点执行结果状态
      取值: "COMPLETED" | "FAILED"
      默认: "COMPLETED"（向后兼容，所有现有调用无需修改）
  行为变更:
    - START 阶段:
      1. 分配 sequence_number（见 IFC-TL-002-02）
      2. INSERT INTO alert_timeline (node_name, alert_id_fk, state_snapshot,
         started_at, status, sequence_number)
         VALUES (?, ?, ?, ?, 'RUNNING', ?)
      3. 将 DB 返回的 entry.id 存储到 _timeline_store[alert_id][-1]._db_id
    - END 阶段:
      1. 从 _timeline_store 找到匹配的 RUNNING entry，获取 _db_id
      2. 计算 duration_ms = (datetime.now(UTC) - started_at).total_milliseconds()
      3. UPDATE alert_timeline SET completed_at=?, duration_ms=?,
         status=?, state_snapshot=? WHERE id=?
  返回值: 无（void 方法，副作用为 DB 写入 + 内存更新）

IFC-TL-002-02: __seq_counters: dict[str, int]（新增实例属性）
  类型: Dict[str, int]
  键: alert_id (str)
  值: 当前已分配的最大 sequence_number (int)
  初始化: 空 dict {}，在首次使用时 lazy-initialize
  恢复策略: 首次为某 alert_id 分配序号时，查询 DB:
    SELECT COALESCE(MAX(sequence_number), 0) FROM alert_timeline
    WHERE alert_id_fk = ?;
  递增: __seq_counters[alert_id] += 1（原子操作，单进程安全）

IFC-TL-002-03: handle_analyze_root_cause 调用变更（唯一需要修改的 handler）
  位置: node_handlers.py L449
  变更前: self._log_node(state, node, "END")
  变更后: self._log_node(state, node, "END", status="FAILED")
  触发条件: LLM 调用异常（except Exception 分支）
  语义: 将 timeline 条目标记为 FAILED 而非默认 COMPLETED
```

**依赖模块**: MOD-TL-003（AlertRepository.append_timeline_entry + update_timeline_entry）

**内部依赖**:
- `src.database.base.SessionLocal`：获取 DB session（已有依赖）
- `src.database.repositories.alert_repository.AlertRepository`：调用 repository 方法（已有依赖）

---

### MOD-TL-003: AlertRepository 增强

- **职责**: 新增 `update_timeline_entry` 方法支持 END 阶段的状态更新；在应用启动时执行 schema 迁移。
- **覆盖需求**: REQ-FUNC-006（支撑 START INSERT + END UPDATE），REQ-NFUNC-002（支撑历史数据兼容）
- **文件位置**: `src/database/repositories/alert_repository.py`（`AlertRepository` 类）
- **变更类型**: 新增方法 + 可选新增迁移辅助函数

**公开接口契约:**

```
IFC-TL-003-01: update_timeline_entry(entry_id: int, updates: dict) -> AlertTimeline | None
  参数:
    - entry_id: int -- 要更新的 AlertTimeline 记录的 DB 主键 id
    - updates: dict -- 要更新的字段，可包含:
        * completed_at: datetime
        * duration_ms: int
        * status: str ("COMPLETED" | "FAILED")
        * state_snapshot: dict
  返回值:
    - 成功: 更新后的 AlertTimeline ORM 对象
    - 失败（entry_id 不存在）: None
  实现:
    1. db.execute(select(AlertTimeline).where(AlertTimeline.id == entry_id))
    2. 若 entry is None -> return None
    3. for key, value in updates.items(): setattr(entry, key, value)
    4. db.commit(); db.refresh(entry); return entry

IFC-TL-003-02: append_timeline_entry(alert_id: str, entry_data: dict) -> AlertTimeline
  【不变更】现有签名和实现保持不变。
  调用方变更: entry_data 中新增可选字段:
    - sequence_number: int | None（由 MOD-TL-002 在 START 阶段传入）
  行为不变: INSERT 新行并返回 ORM 对象（调用方从返回值获取 .id）

IFC-TL-003-03: get_alert_timeline(alert_id: str) -> list[AlertTimeline]
  【不变更】现有签名和实现保持不变。
  返回的 ORM 对象自动包含新列（sequence_number、duration_ms），
  历史数据对应字段为 None。

IFC-TL-003-04: ensure_timeline_columns()（新增静态/模块级函数）
  职责: 在应用启动时检测并添加缺失的 DB 列
  位置: alert_repository.py 模块级别或 base.py init_db()
  实现:
    1. 查询 PRAGMA table_info('alert_timeline')
    2. 若 'sequence_number' 不在列名中:
       db.execute(text("ALTER TABLE alert_timeline ADD COLUMN sequence_number INTEGER"))
    3. 若 'duration_ms' 不在列名中:
       db.execute(text("ALTER TABLE alert_timeline ADD COLUMN duration_ms INTEGER"))
  执行时机: base.py 中 create_all() 之前调用
  幂等性: 多次执行安全（检测列是否存在再添加）
```

**依赖模块**: MOD-TL-001（AlertTimeline 模型，列定义来源）

**外部依赖**: SQLAlchemy 2.0 `text()` for raw SQL migration

---

### MOD-TL-004: API 响应格式扩展

- **职责**: 确保 `GET /api/alerts/{alert_id}` 返回的 timeline 数组包含新字段（sequence_number、duration_ms），且不破坏现有响应格式。
- **覆盖需求**: REQ-NFUNC-001（API 向后兼容）
- **文件位置**: `src/api/alerts_router.py`（`get_alert_detail` 函数）
- **变更类型**: **无需代码变更**

**公开接口契约:**

```
IFC-TL-004-01: GET /api/alerts/{alert_id} -> Response JSON
  【不变更】路由路径、HTTP 方法、请求参数均不变。
  timeline 字段的序列化行为:
    - 现有字段 (id, alert_id_fk, node_name, state_snapshot, started_at,
      completed_at, status): 语义和类型不变
    - 新增字段 (sequence_number, duration_ms): 由 SQLAlchemy ORM 自动序列化
    - 旧记录: sequence_number=null, duration_ms=null
      在 JSON 中表示为: "sequence_number": null, "duration_ms": null
  JSON 响应示例（新+旧记录混合）:
    {
      "alert": {...},
      "timeline": [
        {
          "id": 1,
          "node_name": "receive_alert",
          "status": "COMPLETED",
          "started_at": "2026-07-15T10:00:00Z",
          "completed_at": "2026-07-15T10:00:01Z",
          "sequence_number": 1,       // NEW — 增强后记录
          "duration_ms": 350,         // NEW — 增强后记录
          ...
        },
        {
          "id": 2,
          "node_name": "parse_alert",
          "status": "RUNNING",
          "started_at": "2026-07-15T10:00:01Z",
          "completed_at": null,
          "sequence_number": 2,       // NEW — RUNNING 也有序号
          "duration_ms": null,        // NEW — RUNNING 无 duration
          ...
        },
        {
          "id": 0,
          "node_name": "old_node",
          "status": "COMPLETED",
          "started_at": "2026-07-14T08:00:00Z",
          "completed_at": "2026-07-14T08:00:02Z",
          "sequence_number": null,    // NEW — 历史记录为 null
          "duration_ms": null,        // NEW — 历史记录为 null
          ...
        }
      ],
      ...
    }

IFC-TL-004-02: 向后兼容验证清单
  [x] 现有前端代码 entry.node_name 取值不变
  [x] 现有前端代码 entry.status 取值不变
  [x] 现有前端代码 entry.started_at 取值不变
  [x] 现有前端代码 entry.completed_at 取值不变
  [x] 现有前端代码 entry.state_snapshot 取值不变
  [x] 新字段的 JSON key 不与任何现有 key 冲突
  [x] 新字段在旧记录中为 null，不会导致 JSON 解析错误
```

**依赖模块**: MOD-TL-003（AlertRepository.get_alert_timeline 返回的 ORM 对象）

**实现说明**: 当前 `alerts_router.py` L75 调用 `repo.get_alert_timeline(alert_id)` 返回 `list[AlertTimeline]` ORM 对象，L143-L150 直接放入返回 dict。FastAPI 使用 `jsonable_encoder` 将 ORM 对象转换为 dict，新列会自动出现在输出中。因此 MOD-TL-004 **无需任何代码变更**即可满足 REQ-NFUNC-001。

---

### MOD-TL-005: 前端 Timeline 组件增强

- **职责**: 在告警详情页的"处理时间线" Tab 中渲染新增的序列号、耗时字段，并保持对历史数据的 fallback 展示。同时实现智能轮询逻辑。
- **覆盖需求**: REQ-FUNC-001, REQ-FUNC-002, REQ-FUNC-003, REQ-NFUNC-002, REQ-NFUNC-003, US-004
- **文件位置**: `webui/src/views/alerts/AlertsDetailView.vue`
- **变更类型**: 模板扩展 + 脚本扩展（新增函数 + 生命周期钩子）

**公开接口契约:**

```
IFC-TL-005-01: Timeline 条目渲染模板（模板变更）
  位置: <el-timeline-item> 内部
  当前渲染:
    <strong>{{ entry.node_name }}</strong>
    <el-tag :type="timelineStatusTag(entry.status)" size="small">
      {{ entry.status }}
    </el-tag>
    <p v-if="entry.completed_at">完成时间: {{ formatTime(entry.completed_at) }}</p>
  增强后渲染:
    <span class="tl-seq">{{ formatSeq(entry.sequence_number) }}</span>
    <strong>{{ entry.node_name }}</strong>
    <el-tag :type="timelineStatusTag(entry.status)" size="small">
      {{ entry.status }}
    </el-tag>
    <span class="tl-duration" :style="{ color: durationColor(entry) }">
      {{ formatDuration(entry) }}
    </span>
    <p v-if="entry.completed_at" style="color:#909399;font-size:12px">
      完成时间: {{ formatTime(entry.completed_at) }}
    </p>

IFC-TL-005-02: formatSeq(seq: number | null | undefined) -> string
  输入: sequence_number 字段值
  输出:
    - 若 seq 为有效正整数: "#{seq}"（如 "#1", "#3"）
    - 若 seq 为 null / undefined / 0: "-"
  用途: timeline 条目左侧序号展示

IFC-TL-005-03: formatDuration(entry: object) -> string
  输入: timeline entry 对象（含 duration_ms, status, completed_at, started_at）
  输出:
    - 若 entry.duration_ms 为有效非负整数: "{duration_ms}ms"（如 "350ms"）
    - 若 entry.duration_ms 为 null 但 completed_at 非空（历史数据回退）:
      计算 (new Date(completed_at) - new Date(started_at)) 并格式化为 "{N}ms"
    - 若 entry.status === 'RUNNING': "(进行中)"
    - 其他: "-"
  符合 PM 裁决 Q1（纯毫秒数值）和 Q2（失败节点也显示 duration）

IFC-TL-005-04: durationColor(entry: object) -> string
  输入: timeline entry 对象
  输出:
    - 若 entry.status === 'FAILED': '#F56C6C'（红色，PM Q2 裁决）
    - 若 entry.status === 'RUNNING': '#909399'（灰色）
    - 默认（COMPLETED）: '#67C23A'（绿色，或继承默认色）

IFC-TL-005-05: fetchTimelineData()（新增函数）
  职责: 从 API 获取最新数据并更新 timeline 响应式变量
  实现:
    1. const resp = await store.fetchAlertDetail(route.params.alertId)
    2. timeline.value = resp.timeline || []
    3. alert.value = resp.alert  // 同步更新 alert.status 用于停止判断

IFC-TL-005-06: shouldStopPolling() -> boolean
  职责: 判断轮询终止条件
  终止条件（双重条件）:
    1. alert.value.status in ['CLOSED', 'FAILED', 'REJECTED'] AND
    2. timeline.value.every(e => e.status !== 'RUNNING')
  安全阀: 若轮询启动超过 15 分钟（180 次 * 5s），强制停止

IFC-TL-005-07: 生命周期钩子变更
  onMounted:
    1. 现有: fetchTimelineData()（首次加载，替代原有的内联逻辑）
    2. pollTimer = setInterval(() => {
         if (shouldStopPolling()) { clearInterval(pollTimer); return; }
         fetchTimelineData();
       }, 5000)
  onUnmounted:
    1. if (pollTimer) clearInterval(pollTimer)（新增）

IFC-TL-005-08: 历史数据兼容（REQ-NFUNC-002）
  - sequence_number 为 null -> formatSeq 返回 "-"
  - duration_ms 为 null 且 completed_at 为 null -> formatDuration 返回 "-"
  - duration_ms 为 null 但 completed_at 非空 -> formatDuration 实时计算 fallback
  - 所有 null 字段的处理均不抛出异常（使用可选链 ?. 和 if 守卫）
```

**依赖模块**: MOD-TL-007（通过 `useAlertsStore().fetchAlertDetail()` 获取数据）

**外部依赖**: Element Plus `<el-timeline>` / `<el-timeline-item>`（已有），Vue 3 Composition API（已有）

**前端渲染性能分析（REQ-NFUNC-003）**:
- 新增 DOM 节点: 每条 timeline 条目增加 1 个 `<span>`（序号）+ 1 个 `<span>`（耗时），共 2 个轻量节点。
- 最坏情况（14 条条目）: 28 个新增 DOM 节点，Vue 3 基于 Proxy 的增量 diff 更新耗时 < 10ms。
- 轮询更新: `timeline.value = resp.timeline` 触发整个数组替换，Vue 3 使用 `key`（`:key="entry.id"`）复用 DOM，仅更新文本内容（序列号因已持久化不变，耗时因已完成不变，仅 RUNNING -> COMPLETED 切换时状态标签更新）。
- 结论: 满足 < 50ms 增量渲染约束。

---

### MOD-TL-006: 前端自动刷新机制

- **职责**: 实现智能轮询逻辑——workflow 活跃时每 5 秒刷新 timeline 数据，完成后自动停止。
- **覆盖需求**: US-004（实时进度），PM Q3 裁决（5 秒轮询）
- **文件位置**: `webui/src/views/alerts/AlertsDetailView.vue`（与 MOD-TL-005 同文件）
- **变更类型**: 脚本逻辑（已在 MOD-TL-005 的接口契约中完整描述，此处为独立模块归纳）

**说明**: MOD-TL-006 与 MOD-TL-005 共享同一文件（`AlertsDetailView.vue`），但职责独立——MOD-TL-005 负责渲染层，MOD-TL-006 负责数据刷新层。两者在实现上耦合于同一个 Vue 组件，但在架构上属于不同的关注点。

**公开接口契约（归纳自 MOD-TL-005）:**

```
IFC-TL-006-01: pollTimer 管理
  类型: ReturnType<typeof setInterval> | null
  初始化: null
  启动: onMounted 中 setInterval(..., 5000)
  停止条件: shouldStopPolling() 返回 true 或组件卸载
  清理: onUnmounted 中 clearInterval(pollTimer)

IFC-TL-006-02: 轮询间隔
  值: 5000 (ms) — 固定 5 秒，来自 PM Q3 裁决
  不可配置: 硬编码常量（非用户可调参数）

IFC-TL-006-03: 最大轮询时间
  值: 900000 (ms) = 15 分钟 = 180 次轮询
  用途: 安全阀，防止 shouldStopPolling 逻辑缺陷导致无限轮询
```

**依赖模块**: MOD-TL-007（store.fetchAlertDetail）

**注意事项**:
- 轮询仅在告警详情页处于激活状态时运行（Tab 切换不停止，路由离开时 `onUnmounted` 清理）。
- 每次轮询请求独立，不排队（不等待上一次请求完成）。
- 轮询失败（网络错误）时静默处理（不弹出错误提示，避免每 5 秒弹一次错误）。

---

### MOD-TL-007: API 客户端增强（alerts.ts Store）

- **职责**: 确保前端 store 的 `fetchAlertDetail` 方法能正确将 API 返回的新字段传递给视图组件。
- **覆盖需求**: REQ-NFUNC-001（API 向后兼容的客户端侧验证）
- **文件位置**: `webui/src/stores/alerts.ts`
- **变更类型**: **无需代码变更**

**公开接口契约:**

```
IFC-TL-007-01: fetchAlertDetail(alertId: string) -> Promise<any>
  【不变更】
  当前实现:
    async function fetchAlertDetail(alertId: string) {
      const resp: any = await client.get(`/api/alerts/${alertId}`)
      currentAlert.value = resp.alert
      return resp  // 包含 alert, timeline, fix_plan, commands, llm_calls, approval
    }
  返回的 resp.timeline 中的每个 entry 将自动包含新字段:
    - entry.sequence_number: number | null
    - entry.duration_ms: number | null
  TypeScript 类型标注: 当前使用 `any` 类型，无需更新类型定义（新字段自动通过）。
  若未来加强类型安全: 可扩展 TimelineEntry 接口（可选，非本次必须）。
```

**依赖模块**: 无（基础设施层，API client `@/api/client`，已有依赖）

---

## 依赖关系图（文本格式）

```
MOD-TL-001 (AlertTimeline Model)
    ↑ 被依赖
MOD-TL-003 (AlertRepository)
    ↑ 被依赖
MOD-TL-002 (NodeHandlers._log_node)
    （无向上依赖）

MOD-TL-003 (AlertRepository)
    ↑ 被依赖
MOD-TL-004 (API Router) — 无需变更，ORM 自动序列化
    ↑ 被调用
MOD-TL-005 (前端 Timeline 组件)
    ↑ 调用
MOD-TL-007 (alerts.ts Store) — 无需变更
    ↑ 调用
MOD-TL-006 (前端自动刷新) — 与 MOD-TL-005 同文件

依赖方向（全部自下而上，无循环依赖）:
  MOD-TL-001 ← MOD-TL-003 ← MOD-TL-002（后端依赖链）
  MOD-TL-003 → MOD-TL-004 → MOD-TL-007 → MOD-TL-005（数据流，单向）
  MOD-TL-006 ← MOD-TL-005（同组件内方法调用，非模块间循环）
```

**循环依赖验证结果**: 无循环依赖。所有依赖方向为单向自底向上（DB 层 -> Repository 层 -> 编排层 -> API 层 -> 前端），符合分层架构原则。

---

## 实现顺序建议

| 顺序 | 模块 | 理由 |
|------|------|------|
| 1 | MOD-TL-001 | DB Schema 变更必须先完成，后续模块依赖新列 |
| 2 | MOD-TL-003 | Repository 方法扩展（update_timeline_entry + 迁移），为 MOD-TL-002 提供支撑 |
| 3 | MOD-TL-002 | 核心逻辑变更，依赖 MOD-TL-001 和 MOD-TL-003 |
| 4 | MOD-TL-004 | 验证（非变更），确认 API 序列化正确 |
| 5 | MOD-TL-007 | 验证（非变更），确认 store 正确传递新字段 |
| 6 | MOD-TL-005 + MOD-TL-006 | 前端变更，依赖后端 API 完成 |

</file_header>
