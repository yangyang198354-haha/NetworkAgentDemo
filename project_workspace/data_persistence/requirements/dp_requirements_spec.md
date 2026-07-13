<file_header>
  <project_name>NetworkAgentDemo</project_name>
  <component>data_persistence</component>
  <phase>PHASE_DP_01 + PHASE_DP_02</phase>
  <group>GROUP_DP_A</group>
  <version>0.1.0</version>
  <status>DRAFT</status>
  <author>sub_agent_requirement_analyst</author>
  <created_at>2026-07-14T00:00:00Z</created_at>
  <invocation_id>GROUP_DP_A</invocation_id>
</file_header>

# 数据持久化修复 — 需求规格说明书

## 执行摘要

### 业务背景
NetworkAgentDemo 是一个 LangGraph 网络自动化 Agent，当前告警管理详情页面存在严重的数据持久化缺陷。关键工作流状态数据仅存储在内存（LangGraph MemorySaver、Python dict）中，服务器重启后全部丢失。（来源：`data_persistence/project_brief.md` "背景" 段）

### 需求总览
- **功能需求**：6 条（REQ-FUNC-001 ~ REQ-FUNC-006）
- **非功能需求**：5 条（REQ-NFUNC-001 ~ REQ-NFUNC-005）
- **推断性需求**：0 条（所有需求均有明确的 PM 项目概要或代码证据支撑）
- **用户故事**：6 条（US-001 ~ US-006），共 19 组验收标准

### 覆盖的 5 个已识别问题

| 问题编号 | 对应需求 | 简述 |
|---------|---------|------|
| 问题 1 | REQ-FUNC-001 | fix_plan 必须持久化到数据库 |
| 问题 2 | REQ-FUNC-002 | LLM 调用详情必须持久化到数据库 |
| 问题 3 | REQ-FUNC-003 | 告警详情 API 必须从数据库读取审批信息 |
| 问题 4 | REQ-FUNC-004 | ApprovalRepository 必须支持按 alert_id 查询 |
| 问题 5 | REQ-FUNC-005 | 工作流状态必须持久化到数据库 |
| 问题 3+4+5 | REQ-FUNC-006 | GET /api/alerts/{alert_id} 全部数据源切换为数据库 |

---

## 功能需求（Functional Requirements）

### REQ-FUNC-001：修复方案（fix_plan）必须持久化到数据库

| 字段 | 内容 |
|------|------|
| **ID** | REQ-FUNC-001 |
| **描述** | 系统应当将工作流生成的修复方案（fix_plan）持久化存储，确保服务器重启后 fix_plan 数据不丢失，且对低风险和高风险告警均有效。 |
| **来源引用** | `project_brief.md` "问题 1：修复方案 (fix_plan) 不持久化" — "fix_plan 仅存储在 LangGraph MemorySaver（纯内存 dict）"、"alerts 表无 fix_plan 列，无单独的 fix_plans 表"、"仅高风险告警的 fix_plan 截断存入 approvals.fix_plan，低风险告警完全不持久化"、"服务器重启后全部丢失"；`src/models/state.py:48` — `fix_plan: dict[str, Any]` 仅在 TypedDict 中定义（MemorySaver 范围）；`src/database/alert_models.py:23-49` — Alert 模型无 fix_plan 列；`src/orchestration/node_handlers.py:494-497` — 仅高风险告警的 fix_plan 部分内容写入 approvals.fix_plan（JSON 字段）。 |
| **优先级** | Must Have |
| **备注** | — |

### REQ-FUNC-002：LLM 调用详情必须持久化到数据库

| 字段 | 内容 |
|------|------|
| **ID** | REQ-FUNC-002 |
| **描述** | 系统应当将每次 LLM 调用的详情（端点、时间戳、耗时、token 用量、提示词摘要、响应摘要）持久化存储，使得服务器重启后 LLM 调用历史仍可查询。 |
| **来源引用** | `project_brief.md` "问题 2：LLM 调用详情 (LLM call logs) 不持久化" — "LLMService._llm_call_log 是纯 Python dict（`src/llm/llm_service.py:41`）"、"没有 llm_calls 数据库表"、"重启即丢失"；`src/llm/llm_service.py:41` — `self._llm_call_log: dict[str, list[dict]] = {}` 为进程内存字典；`src/llm/llm_service.py:170-183` — LLM 调用记录仅写入该内存字典，无任何磁盘写入；`src/api/alerts_router.py:112-116` — API 通过 `main_module.llm_service.get_llm_logs(alert_id)` 读取内存中的日志。 |
| **优先级** | Must Have |
| **备注** | — |

### REQ-FUNC-003：告警详情 API 必须从数据库读取审批信息

| 字段 | 内容 |
|------|------|
| **ID** | REQ-FUNC-003 |
| **描述** | 系统应当修改 GET /api/alerts/{alert_id} 接口，使其从 approvals 数据库表读取审批信息，而非从 LangGraph MemorySaver 内存中读取。 |
| **来源引用** | `project_brief.md` "问题 3：审批信息不被 API 读取" — "告警详情 API (`GET /api/alerts/{alert_id}`) 从 MemorySaver 读取审批信息（`src/api/alerts_router.py:94-99`）"、"从未查询 approvals 表，导致数据库中的审批记录不可见"；`src/api/alerts_router.py:94-99` — `approval_info = {"need_human_approval": state.get("need_human_approval", False), "approval_status": state.get("approval_status", "NOT_REQUIRED"), "risk_level": state.get("risk_level", "LOW")}` 全部从 MemorySaver 的 state 对象读取；`src/database/approval_models.py:26-58` — approvals 表已有 fix_plan(JSON), risk_level, decision, decided_by, decided_at, note 等字段，具备持久化审批数据的完整结构。 |
| **优先级** | Must Have |
| **备注** | — |

### REQ-FUNC-004：ApprovalRepository 必须支持按 alert_id 查询

| 字段 | 内容 |
|------|------|
| **ID** | REQ-FUNC-004 |
| **描述** | 系统应当在 ApprovalRepository 中新增按 alert_id 查询审批记录的方法，以支持告警详情 API 从数据库获取关联审批数据。 |
| **来源引用** | `project_brief.md` "问题 4：ApprovalRepository 缺少按 alert_id 查询的方法" — "只有 get_approval_by_checkpoint() 方法（`src/database/repositories/approval_repository.py:39`）"、"无 get_approvals_by_alert_id() 方法"；`src/database/repositories/approval_repository.py:26-108` — 完整 ApprovalRepository 仅提供了 list_pending_approvals（L28）、get_approval_by_checkpoint（L39）、create_approval（L46）、update_approval_decision（L56）、list_approval_history（L76）五个方法，缺少按 alert_id 的查询方法。 |
| **优先级** | Must Have |
| **备注** | — |

### REQ-FUNC-005：工作流状态必须持久化到数据库

| 字段 | 内容 |
|------|------|
| **ID** | REQ-FUNC-005 |
| **描述** | 系统应当将工作流执行过程中产生的关键状态字段（root_cause、diag_result、exec_log、verify_result、final_report）持久化存储，替代当前仅依赖 MemorySaver 内存存储的方式。 |
| **来源引用** | `project_brief.md` "问题 5：工作流状态完全内存化" — "root_cause, diag_result, exec_log, verify_result, final_report 等均只在 MemorySaver 中"、"无对应的数据库列或表（`src/models/state.py` 定义的字段没有持久化映射）"、"告警详情 API 尝试从 MemorySaver 读取这些字段（`src/api/alerts_router.py:84-87`）"；`src/models/state.py:41` — `diag_result: str`；`src/models/state.py:44` — `root_cause: str`；`src/models/state.py:62` — `exec_log: list[dict[str, Any]]`；`src/models/state.py:65` — `verify_result: dict[str, Any]`；`src/models/state.py:68` — `final_report: str`，以上字段均仅在 TypedDict 中声明，无数据库映射；`src/database/alert_models.py:23-49` — alerts 表无上述任一字段对应的列。 |
| **优先级** | Must Have |
| **备注** | — |

### REQ-FUNC-006：GET /api/alerts/{alert_id} 接口数据源全面切换为数据库

| 字段 | 内容 |
|------|------|
| **ID** | REQ-FUNC-006 |
| **描述** | 系统应当修改 GET /api/alerts/{alert_id} 接口，使其返回的 fix_plan、commands、approval、llm_calls、root_cause、diag_result、exec_log、verify_result、final_report 字段全部从数据库读取，不再依赖 LangGraph MemorySaver 内存状态或 Python 进程内 dict。 |
| **来源引用** | `project_brief.md` "约束 — 3. 向后兼容：不破坏现有 API 契约，GET /api/alerts/{alert_id} 返回的字段名/结构不变"；`src/api/alerts_router.py:66-129` — 整个 get_alert_detail 函数当前从三个不可靠来源读取数据：(1) MemorySaver 的 get_workflow_state (L84-87)，(2) NodeHandlers 内存时间线 get_timeline (L104-109)，(3) LLMService 内存日志 get_llm_logs (L112-116)，仅有 Alert 基本信息 (L70) 和 DB 时间线 (L74) 来自数据库。 |
| **优先级** | Must Have |
| **备注** | 本需求为 REQ-FUNC-001 至 REQ-FUNC-005 在 API 层面的整合需求，确保所有持久化数据通过 API 可访问。 |

---

## 非功能需求（Non-Functional Requirements）

### REQ-NFUNC-001：数据一致性

| 字段 | 内容 |
|------|------|
| **ID** | REQ-NFUNC-001 |
| **描述** | 系统应当确保工作流状态写入数据库后，能通过数据库查询读回与写入时完全一致的数据，不得出现数据库存储值与内存状态值不一致的情况。 |
| **来源引用** | `project_brief.md` "约束 — 1. 数据一致性：工作流状态必须与数据库状态一致（写DB后要能从DB读回相同数据）"。 |
| **优先级** | Must Have |
| **备注** | — |

### REQ-NFUNC-002：服务器重启后可恢复

| 字段 | 内容 |
|------|------|
| **ID** | REQ-NFUNC-002 |
| **描述** | 系统应当确保所有关键数据在服务器进程重启后不丢失，不依赖 LangGraph MemorySaver 的临时内存或任何进程内数据结构作为唯一数据源。 |
| **来源引用** | `project_brief.md` "约束 — 2. 可持久化：所有关键数据需能在服务器重启后恢复，不依赖 LangGraph MemorySaver 的临时内存"。 |
| **优先级** | Must Have |
| **备注** | — |

### REQ-NFUNC-003：向后兼容

| 字段 | 内容 |
|------|------|
| **ID** | REQ-NFUNC-003 |
| **描述** | 系统应当确保 GET /api/alerts/{alert_id} 接口的响应字段名、字段结构和 HTTP 状态码语义不因数据源切换而改变，现有前端代码无需修改即可正常工作。 |
| **来源引用** | `project_brief.md` "约束 — 3. 向后兼容：不可破坏现有 API 契约，GET /api/alerts/{alert_id} 返回的字段名/结构不变"；`src/api/alerts_router.py:122-129` — 当前 API 返回结构为 `{"alert", "timeline", "fix_plan", "commands", "llm_calls", "approval"}`。 |
| **优先级** | Must Have |
| **备注** | — |

### REQ-NFUNC-004：不引入新依赖

| 字段 | 内容 |
|------|------|
| **ID** | REQ-NFUNC-004 |
| **描述** | 系统应当使用现有的 SQLite + SQLAlchemy 2.0 技术栈实现持久化，不得引入新的外部依赖（如 Redis、消息队列、新数据库引擎）。 |
| **来源引用** | `project_brief.md` "约束 — 5. Demo 可接受：SQLite + SQLAlchemy 2.0，不引入新依赖（如 Redis、消息队列）"。 |
| **优先级** | Must Have |
| **备注** | — |

### REQ-NFUNC-005：现有表结构不可破坏

| 字段 | 内容 |
|------|------|
| **ID** | REQ-NFUNC-005 |
| **描述** | 系统应当确保对 alerts 表和 approvals 表的任何修改均通过新增列（带默认值）或新增独立表的方式实现，不得删除或修改现有列定义，不得破坏已有数据。 |
| **来源引用** | `project_brief.md` "约束 — 5. 现有表结构不可破坏：alerts 表已有数据，approvals 表已有数据，新增列用 default 值，新增表独立创建"；`src/database/alert_models.py:18-49` — Alert 模型现有 7 列（id, alert_id, alert_type, severity, content, device_info, source, status + 继承自 TimestampMixin 的 created_at/updated_at）；`src/database/approval_models.py:18-65` — Approval 模型现有 10 列。 |
| **优先级** | Must Have |
| **备注** | — |

---

## 超出范围（Out of Scope）

以下内容明确排除在本需求范围之外：

1. **修改 LangGraph 工作流节点逻辑**：本需求仅涉及数据持久化层的修复，不改变 14 个节点的业务逻辑或条件路由逻辑。（来源：`project_brief.md` 问题描述仅涉及持久化缺陷）
2. **更换 MemorySaver 为其他 checkpointer**：MemorySaver 继续用于 LangGraph 的 Interrupt 机制（工作流挂起/恢复），但不再作为工作流状态的唯一数据源。（来源：推导自约束 2 "不依赖 LangGraph MemorySaver 的临时内存"，但 Interrupt 机制仍需 MemorySaver）
3. **新增 API 端点**：不新增 API 端点，仅修复现有端点的数据读取来源。
4. **引入数据库迁移工具（如 Alembic）**：按 Demo 可接受标准，使用 SQLAlchemy `Base.metadata.create_all()` 创建新表，新增列采用手动 ALTER TABLE 或在 ORM 模型中声明 default 值。
5. **修改前端代码**：前端代码不需要任何修改（向后兼容约束）。

---

## 待确认推断项

本次分析无 [INFERRED] 标注的确定性需求。所有 6 条功能需求和 5 条非功能需求均有明确的项目概要引用和代码行号证据支撑，无需 PM 额外确认。

---

## 开放问题

无。5 个已识别问题均清晰、可操作，代码证据完整。
