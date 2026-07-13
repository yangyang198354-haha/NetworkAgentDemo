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
</file_header>

# 数据持久化修复 -- 技术选型确认

---

## 技术选型表

| 类别 | 选型 | 版本/版次 | Rationale | 关联 REQ-* | 风险 | 备注 |
|------|------|----------|-----------|-----------|------|------|
| 编程语言 | Python | 3.11+ | 现有项目已使用，REQ-NFUNC-004 要求不引入新依赖 | REQ-NFUNC-004 | 无 | 不变更 |
| Web 框架 | FastAPI | 现有版本 | 现有项目已使用，API 层仅修改路由函数内部逻辑 | REQ-NFUNC-003, REQ-NFUNC-004 | 无 | 不变更 |
| 数据库引擎 | SQLite | 3.x (系统自带) | 现有项目已使用，REQ-NFUNC-004 明确"不引入新数据库引擎" | REQ-NFUNC-004 | SQLite JSON 函数有限但满足 Demo 需求 | WAL 模式 + FK ON，现有配置不变 |
| ORM 框架 | SQLAlchemy | 2.0 (现有) | 现有项目已使用，支持 JSON 列类型，支持 create_all() 自动建表 | REQ-NFUNC-004, REQ-NFUNC-005 | JSON 类型在 SQLite 后端存储为 TEXT，序列化由 SA 自动处理 | 不变更版本 |
| 数据库迁移 | 无（Base.metadata.create_all） | N/A | Demo 使用 create_all() 自动建表，超出范围第 4 条明确不引入 Alembic | REQ-NFUNC-004, REQ-NFUNC-005 | 已有数据库新增列需手动 ALTER TABLE 或重建--Demo 可接受 | 建议 init_db() 中检测列是否存在 |
| JSON 序列化 | Python json + SQLAlchemy JSON | 标准库 + 现有 | SA JSON 列自动处理序列化；dict 序列化使用标准 json | REQ-NFUNC-001, REQ-NFUNC-004 | Pydantic model_dump() 可能产生非 JSON 兼容值 | 建议使用 model_dump(mode='json') |
| LangGraph | 现有版本 | 现有 | MemorySaver 保留用于 Interrupt，不更换 checkpointer | REQ-NFUNC-002 | 无 | 不变更 |
| LLM API | DeepSeek API (openai SDK) | 现有 | LLMService 调用逻辑不变，仅新增 DB 双写 | REQ-FUNC-002, REQ-NFUNC-004 | 无 | 不变更 |
| 前端框架 | Vue 3 + Element Plus | 现有 | 前端代码无需任何修改（向后兼容） | REQ-NFUNC-003 | 无 | 不变更 |
| 测试框架 | pytest | 现有 | 新增模块需编写对应单元测试 | REQ-FUNC-001~006 | 无 | 测试编写在后续实现阶段进行 |

---

## 技术风险汇总

### 高风险（High）

**无。** 本次修复不引入新的外部依赖，不更换现有技术栈组件，所有技术选型均为现有项目的延续。

### 中风险（Medium）

| 编号 | 风险描述 | 关联技术 | 关联 REQ | 缓解措施 |
|------|---------|---------|---------|---------|
| MR-001 | SQLite JSON 列增量更新需 read-modify-write，并发更新可能丢失数据 | SQLite JSON, AlertRepository | REQ-NFUNC-001 | LangGraph 节点单线程串行执行，同一 alert_id 只有一个工作流线程。若未来引入并发需加应用层锁。当前 Demo 无需处理 |
| MR-002 | create_all() 对已有表不自动添加新列，workflow_state 列可能缺失 | SQLAlchemy, SQLite | REQ-NFUNC-005 | Demo 可接受方案：删除 webui.db 重建或手动 ALTER TABLE。实现时建议在 init_db() 中检测列是否存在并自动添加 |
| MR-003 | Pydantic model_dump() 可能产生非 JSON 兼容值（如 datetime），写入 JSON 列时可能报错 | Pydantic, SQLAlchemy JSON | REQ-NFUNC-001 | 使用 model_dump(mode='json') 确保 JSON 兼容类型。现有 FixPlan.model_dump() 已在用，需验证 JSON 列中的行为 |

### 低风险（Low）

| 编号 | 风险描述 | 关联技术 | 缓解措施 |
|------|---------|---------|---------|
| LR-001 | prompt_summary/response_summary 截断 3000 字符可能在关键字中间截断 | SQLite TEXT | 截断逻辑与现有 LLMService._llm_call_log 一致（L181-182），行为不变 |
| LR-002 | SessionLocal() 独立创建/关闭，短时间内可能大量连接创建/销毁 | SQLAlchemy Session | SQLite WAL 模式下连接开销极低；14 个节点 Session 创建总延迟 <100ms，可忽略 |
| LR-003 | llm_calls 表随告警数量线性增长 | SQLite 存储 | Demo 告警量小（数十条/天）。生产化时需日志归档策略--不在 Demo 范围 |

---

## 不引入的新依赖清单

根据 REQ-NFUNC-004 要求，以下技术**明确不引入**：

| 排除项 | 排除原因 |
|--------|---------|
| Redis | 非必需--LangGraph Interrupt 由 MemorySaver 处理，无缓存需求 |
| 消息队列 (RabbitMQ/Kafka/Redis Stream) | 非必需--工作流为同步执行，无异步削峰需求 |
| 新数据库引擎 (PostgreSQL/MySQL/MongoDB) | REQ-NFUNC-004 明确约束--SQLite 满足 Demo 全部需求 |
| Alembic (数据库迁移工具) | 超出范围第 4 条明确排除--Demo 使用 create_all() |
| Celery / 任务队列 | 非必需--工作流在 threading.Thread 中执行 |
| LangGraph SqliteSaver | 超出范围第 2 条保留 MemorySaver 用于 Interrupt |
| 缓存库 (cachetools/redis-py) | 非必需--纯 DB 读取策略无需额外缓存层 |

---

## 技术兼容性矩阵

| 变更点 | 影响现有功能？ | 影响现有测试？ | 影响前端？ | 影响部署？ |
|--------|:---:|:---:|:---:|:---:|
| alerts 表 +workflow_state 列 (default=NULL) | 否--NULL 默认值对现有查询透明 | 否--现有测试不依赖此列 | 否 | 仅需 create_all() 或 ALTER TABLE |
| 新建 llm_calls 表 | 否--独立新表，不影响现有查询 | 否--新表不影响旧测试 | 否 | create_all() 自动创建 |
| NodeHandlers 新增 DB 写操作 | 否--try-except 包裹，失败仅 log warning | 可能--需 mock SessionLocal 或使用内存 SQLite | 否 | 否 |
| LLMService 新增 llm_log_repo 参数 | 否--可选参数默认 None，未传入时行为不变 | 否--默认行为不变 | 否 | 否 |
| alerts_router 数据源切换为 DB | 否--API 响应结构完全不变 | 是--需更新 API 测试的 mock 策略 | 否--响应字段名/结构不变 | 否 |
</file_path>
