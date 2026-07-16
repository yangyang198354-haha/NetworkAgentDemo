<file_header>
  <project_name>NetworkAgentDemo</project_name>
  <author_agent>sub_agent_system_architect</author_agent>
  <file_type>TECH_STACK</file_type>
  <version>1.0.0</version>
  <status>APPROVED</status>
  <created_at>2026-07-16T00:00:00Z</created_at>
  <invocation_id>timeline-enhancement-phase-design</invocation_id>
  <description>Alert Detail Page Timeline Component Enhancement -- Technology Stack Selection</description>
</file_header>

# 告警详情页处理时间线组件增强 -- 技术选型表

## 技术选型表

### 后端技术（所有选型均为现有技术栈，零新增依赖）

| 类别 | 选型 | 版本/版次 | Rationale | 关联 REQ-* | 风险 | 备注 |
|------|------|----------|-----------|-----------|------|------|
| 编程语言 | Python | 3.11+ | 现有项目语言，无需引入新运行时 | REQ-NFUNC-001 | Low -- 版本已锁定 | 部署环境已安装 |
| Web 框架 | FastAPI | 0.x (现有) | 现有框架，其 `jsonable_encoder` 自动将 SQLAlchemy ORM 新列序列化为 JSON，确保 API 向后兼容（REQ-NFUNC-001） | REQ-NFUNC-001 | Low -- FastAPI 不会因 ORM 模型新增列而改变行为 | 无版本升级需求 |
| ORM | SQLAlchemy 2.0 | 2.0.x (现有) | 现有 ORM，`mapped_column` 声明式语法用于新增 `sequence_number` 和 `duration_ms` 列 | REQ-FUNC-001, REQ-FUNC-002, REQ-NFUNC-002 | Low -- 新增列为标准 ORM 操作 | 使用 `Mapped[Optional[int]]` 类型标注 |
| 数据库 | SQLite 3 (WAL 模式) | 3.x (现有) | 现有数据库，支持 ALTER TABLE ADD COLUMN（3.2.0+），WAL 模式支持并发读写以满足 START INSERT + END UPDATE 的两次写入 | REQ-FUNC-006, REQ-NFUNC-002 | Low -- ALTER TABLE ADD COLUMN 是 SQLite 成熟特性 | 迁移在应用启动时以幂等方式执行 |
| Schema 迁移 | 手动检测 + ALTER TABLE | N/A (自定义) | 不使用 Alembic 等重量级迁移工具（符合 Demo v0.2.0 的轻量级约定——项目已在 `Base.metadata.create_all()` 上构建，无迁移框架） | REQ-NFUNC-002 | Medium -- 需确保迁移幂等且在 `create_all()` 之前执行 | 见"风险汇总" #1 |
| 日期时间处理 | Python `datetime` (timezone.utc) | stdlib | 用于 `started_at`/`completed_at` 时间戳记录和 `duration_ms` 计算（`(end - start).total_milliseconds()`），精度满足 REQ-NFUNC-004 的 < 100ms 要求（实际精度 < 1ms） | REQ-FUNC-005, REQ-NFUNC-004 | Low -- stdlib 无外部依赖风险 | 已在使用，`node_handlers.py` L195 |
| 日志 | Loguru | 0.x (现有) | 现有日志框架，用于 debug 级别记录 timeline 增强行为 | -- | Low | 无变更 |

### 前端技术（所有选型均为现有技术栈，零新增依赖）

| 类别 | 选型 | 版本/版次 | Rationale | 关联 REQ-* | 风险 | 备注 |
|------|------|----------|-----------|-----------|------|------|
| 前端框架 | Vue 3 (Composition API) | 3.x (现有) | 现有框架，其 Proxy-based 响应式系统可高效 diff 最多 14 个 `<el-timeline-item>` 的更新（满足 REQ-NFUNC-003 < 50ms 增量渲染） | REQ-NFUNC-003 | Low -- Vue 3 成熟稳定 | 已在使用 |
| UI 组件库 | Element Plus | 2.x (现有) | 现有组件库，`<el-timeline>` + `<el-timeline-item>` 已在使用，其 `color` prop 支持自定义节点颜色（COMPLETED=#67C23A, FAILED=#F56C6C, RUNNING=#409EFF） | REQ-FUNC-003 | Low -- 现有颜色映射已预留 FAILED 状态 | 已在 AlertsDetailView.vue L200 使用 |
| 类型系统 | TypeScript | 5.x (现有) | 现有类型系统，当前 store 使用 `any` 类型传递 API 响应，新字段自动兼容无需类型扩展 | REQ-NFUNC-001 | Low | 建议未来为 TimelineEntry 添加精确接口定义 |
| HTTP 客户端 | Axios | 1.x (现有) | 现有 HTTP 客户端，通过 `client.ts` 的响应拦截器自动解包 `response.data`，轮询请求复用现有 JWT 拦截器 | REQ-NFUNC-001 | Low -- 无变更 | `fetchAlertDetail` 返回完整响应 JSON |
| 状态管理 | Pinia | 2.x (现有) | 现有状态管理，`useAlertsStore().fetchAlertDetail()` 返回完整 API 响应（含 timeline 数组），轮询逻辑直接使用 | REQ-NFUNC-001 | Low | 无需新增 store action |
| 轮询 | `setInterval` / `clearInterval` | Web API (stdlib) | 浏览器原生 API，零依赖；PM 裁决 5 秒间隔；智能停止避免无效请求 | US-004, PM Q3 | Low -- 浏览器兼容性好 | 最大轮询 15 分钟后强制停止 |

### 候选方案对比（未采用的替代方案）

| 决策点 | 已选方案 | 候选方案 B | 候选方案 C | 不选 B/C 的理由 |
|--------|---------|-----------|-----------|----------------|
| sequence_number 生成 | 应用层 per-alert 计数器 + DB 列 | 查询时 ROW_NUMBER 推导 | DB 全局 AUTOINCREMENT | B: 无法在 START 阶段持久化序号；C: 序号非 per-alert，无法满足 REQ-FUNC-004 |
| duration_ms 存储 | 新增 INTEGER 列 | 存入 state_snapshot JSON | 纯实时计算 | B: 破坏 JSON 列职责单一性；C: 前端需额外计算逻辑 |
| status 判定 | _log_node 显式 status 参数 | 从 state["status"] 推断 | LangGraph wrapper 统一写 | B: 存在时序缺陷（state 尚未更新）；C: 架构侵入性过大 |
| DB 写入时机 | START INSERT + END UPDATE | 仅 END 写 DB | 内存+DB 混合 | B: 不满足 REQ-FUNC-006；C: 分层架构被破坏 |
| 前端刷新 | 智能轮询（5s，自动停止） | 无条件轮询 | 手动刷新按钮 | B: 浪费资源；C: 不满足 PM Q3 裁决 |

---

## 新增依赖分析

### 结论：本次增强不引入任何新的 Python 或 Node/JavaScript 依赖。

| 依赖类别 | 是否需要新增 | 说明 |
|---------|-------------|------|
| Python pip 包 | 否 | 所有功能（ORM 列新增、DB 迁移、datetime 计算、API 序列化）均基于现有依赖实现 |
| Node.js npm 包 | 否 | 所有功能（Vue 3 模板、Element Plus、setInterval、Axios）均基于现有依赖实现 |
| 系统级依赖 | 否 | SQLite WAL 模式、Python stdlib `datetime` 均为现有 |
| 第三方服务 | 否 | 无外部 API 调用（DeepSeek API 等 LLM 服务不在本次变更范围内） |

### 依赖论证
- **DB Schema 迁移**：使用原生 SQL `ALTER TABLE ADD COLUMN`（SQLite 3.2.0+ 内置），无需 Alembic 或 sqlite-utils。理由：项目现有风格为 `Base.metadata.create_all()` 式自动建表（`base.py`），引入 Alembic 会带入约 5 个传递依赖（alembic, Mako, MarkupSafe, python-dateutil, python-editor），不符合 Demo 轻量级定位。
- **duration 计算**：Python `datetime` stdlib 已满足 REQ-NFUNC-004 的精度要求（`total_milliseconds()` 返回 float，截断为 int 后精度 < 1ms），无需 `arrow`、`pendulum` 等第三方时间库。
- **前端轮询**：`setInterval` 是浏览器 Web API 标准，无需引入 `vue-use` 的 `useIntervalFn` 等封装（减少 1 个 npm 依赖）。

---

## 技术风险汇总

### Risk #1: Schema 迁移在应用启动时执行 -- 风险等级: Medium

| 维度 | 内容 |
|------|------|
| 风险描述 | 在 `base.py` 的 `init_db()` 中通过 `PRAGMA table_info` 检测 + `ALTER TABLE ADD COLUMN` 执行迁移。若检测逻辑有误（如列名拼写错误），可能导致重复添加列（SQLite 报错）或在 `create_all()` 之后执行（新表已有列，ALTER 报错）。 |
| 影响范围 | 应用启动失败（后端不可用），影响所有 Web UI 功能。 |
| 关联需求 | REQ-FUNC-001, REQ-FUNC-002, REQ-NFUNC-002 |
| 缓解措施 | 1. 迁移代码包装在 try-except 中，失败时记录 warning 但不阻止启动（列已存在场景）。2. 使用 `IF NOT EXISTS` 式检测（`PRAGMA table_info` 返回列名列表，检查 `'sequence_number' in columns`）。3. 在单元测试中验证迁移幂等性（连续两次启动均成功）。4. 若迁移失败，`create_all()` 会创建含新列的表（全新部署场景），功能不受影响。 |
| 概率 | Low（SQLite ALTER TABLE ADD COLUMN 是成熟功能；`PRAGMA table_info` 检测列名简单可靠） |

### Risk #2: START INSERT 后应用崩溃遗留 RUNNING 孤儿记录 -- 风险等级: Low

| 维度 | 内容 |
|------|------|
| 风险描述 | ADR-TL-004 选择 START INSERT + END UPDATE 方案。若应用在 INSERT 后、UPDATE 前崩溃，DB 中遗留 `status=RUNNING` 但永远不会被更新的"孤儿"记录。 |
| 影响范围 | 仅影响正在执行的 workflow。前端时间线可能显示 "RUNNING" 条目但无法变为终态。 |
| 关联需求 | REQ-FUNC-006, US-004 |
| 缓解措施 | 1. 前端超时判断：若 `status=RUNNING` 且 `started_at` 超过 30 分钟，显示 "(异常中断)"。2. `finish_report` 节点可添加清理逻辑：将当前 alert 所有 RUNNING 条目批量标记为 FAILED（可选增强）。3. 应用重启后新 workflow 不受影响（旧的 RUNNING 记录自然过期）。 |
| 概率 | Low（应用崩溃概率极低；Python/LangGraph 进程在正常运维下稳定运行） |

### Risk #3: sequence_number 在单进程内的计数器一致性 -- 风险等级: Low

| 维度 | 内容 |
|------|------|
| 风险描述 | ADR-TL-001 选择应用层 per-alert 计数器（`__seq_counters` dict）。在单进程 FastAPI 中安全，但若未来扩展为多 worker（如 `uvicorn --workers 4`），多个进程各自维护计数器，可能导致同一 alert 的条目序号重复或乱序。 |
| 影响范围 | 仅在未来多 worker 部署时触发；当前 v0.2.0 为单 worker。 |
| 关联需求 | REQ-FUNC-004 |
| 缓解措施 | 1. 当前不做额外处理（单进程安全）。2. 已标注 [ASSUMPTION] 待 PM 确认。3. 若未来扩展多 worker，可改用 DB 层原子自增：`INSERT INTO alert_timeline (..., sequence_number) VALUES (..., (SELECT COALESCE(MAX(sequence_number), 0) + 1 FROM alert_timeline WHERE alert_id_fk = ?))`，或在 Redis 中维护计数器。 |
| 概率 | Low（当前为单 worker，暂无扩展计划） |

### Risk #4: 轮询对服务器负载的影响 -- 风险等级: Low

| 维度 | 内容 |
|------|------|
| 风险描述 | 前端每 5 秒轮询一次 `GET /api/alerts/{alert_id}`，若多个运维人员同时查看不同活跃 workflow，可能增加服务器 QPS（每秒请求数）。 |
| 影响范围 | 后端（FastAPI + SQLite 读操作）。 |
| 关联需求 | US-004（实时进度），REQ-NFUNC-003（前端性能） |
| 缓解措施 | 1. 智能停止：workflow 完成后轮询自动停止，已完成 workflow 零额外请求。2. 单用户通常只查看一个详情页，实际 QPS = 1 用户 x (1 请求/5s) = 0.2 QPS，远低于 FastAPI + SQLite WAL 的承载能力（轻松处理 100+ QPS）。3. SQLite WAL 模式下读操作不阻塞写操作，轮询 GET 请求不影响 workflow 的 DB 写入。 |
| 概率 | Very Low（实际负载极低） |

### Risk #5: 前端对历史数据的 fallback 渲染不完整 -- 风险等级: Low

| 维度 | 内容 |
|------|------|
| 风险描述 | 旧 timeline 记录的 `sequence_number` 和 `duration_ms` 均为 NULL。若前端 formatSeq/formatDuration 函数对 null 值的处理不完善，可能导致显示 "null" 或 "undefined" 字符串，或触发 JS 运行时异常。 |
| 影响范围 | 仅影响历史数据（增强前创建的 timeline 记录）的展示 |
| 关联需求 | REQ-NFUNC-002 |
| 缓解措施 | 1. formatSeq: 使用 `if (seq == null \|\| seq === 0) return '-'` 守卫。2. formatDuration: 多层 fallback——duration_ms 有效 -> 显示 "Nms"；duration_ms 无效但 completed_at 有效 -> 前端实时计算 fallback；都无效 -> "-"。3. 在 AC-005-01 和 AC-005-03 中定义验收标准，通过 E2E 测试验证。 |
| 概率 | Low（JavaScript 对 null 的字符串拼接/模板字面量输出为 "null"，不会抛异常；Vue 3 模板中 `{{ null }}` 渲染为空字符串，天然安全） |

---

## 环境与配置

| 配置项 | 值 | 说明 |
|--------|-----|------|
| 新增环境变量 | 无 | 本次增强无需新增任何环境变量 |
| 新增配置文件项 | 无 | 本次增强无需修改 `config/config.yaml` |
| 数据库迁移 | 自动（应用启动时） | 在 `init_db()` 中检测并添加缺失列 |
| 前端构建 | 无需特殊配置 | `npm run build` 现有流程不变 |

---

## 兼容性矩阵

| 维度 | 状态 | 说明 |
|------|------|------|
| 与现有 API 兼容 | 完全兼容 | 新字段以追加方式出现，现有字段不变（REQ-NFUNC-001） |
| 与历史 DB 数据兼容 | 完全兼容 | 新增列为 NULLABLE，旧行自动填充 NULL（REQ-NFUNC-002） |
| 与现有前端兼容 | 完全兼容 | 现有代码不引用新字段，新字段不影响旧渲染逻辑 |
| 与现有测试兼容 | 需验证 | 现有测试不涉及 sequence_number/duration_ms 断言，应无破坏性影响；建议为新功能编写独立测试 |
| 与 LangGraph workflow 兼容 | 完全兼容 | `_log_node` 签名变更向后兼容（默认参数），workflow 节点逻辑不变 |
</file_header>
