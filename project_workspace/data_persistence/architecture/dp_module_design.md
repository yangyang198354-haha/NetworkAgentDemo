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

# 数据持久化修复 — 模块设计文档

---

## 模块总览

| MOD-ID | 模块名称 | 层级 | 变更类型 | 职责 | 依赖于 |
|--------|---------|------|---------|------|--------|
| MOD-DP-001 | Alert ORM Extension | 数据层 (ORM) | 修改 | alerts 表新增 workflow_state JSON 列 | Base (SQLAlchemy) |
| MOD-DP-002 | LLMCallLog ORM | 数据层 (ORM) | 新增 | llm_calls 表定义，每行一条 LLM 调用记录 | Base (SQLAlchemy) |
| MOD-DP-003 | LLMCallLogRepository | 数据层 (Repository) | 新增 | llm_calls 表的 CRUD 操作 | MOD-DP-002 |
| MOD-DP-004 | AlertRepository Extension | 数据层 (Repository) | 修改 | 新增 update_workflow_state、get_workflow_state 方法 | MOD-DP-001 |
| MOD-DP-005 | ApprovalRepository Extension | 数据层 (Repository) | 修改 | 新增 get_approvals_by_alert_id 方法 | MOD-WEB-003 (Approval) |
| MOD-DP-006 | NodeHandlers Extension | 编排层 | 修改 | 6 个节点处理器新增 DB 写操作 | MOD-DP-004 |
| MOD-DP-007 | LLMService Extension | LLM 层 | 修改 | _call_llm 中将日志双写至 DB | MOD-DP-003 |
| MOD-DP-008 | alerts_router Extension | API 层 | 修改 | GET /api/alerts/{id} 数据源全面切换为 DB | MOD-DP-004, MOD-DP-005, MOD-DP-003 |

---

## 新增/修改实体关系图（ER）

```
┌────────────────────────────────────────────────────────────────────┐
│                          alerts 表                                   │
│  (已有) id, alert_id, alert_type, severity, content, device_info,    │
│         source, status, created_at, updated_at                       │
│  ★新增★ workflow_state  JSON  DEFAULT NULL                          │
│                                                                      │
│  workflow_state JSON 结构:                                            │
│  {                                                                   │
│    "fix_plan": {"template_id":"...","description":"...",             │
│      "params":{...},"commands":["..."],"risk_hints":[...]},         │
│    "root_cause": "string",                                           │
│    "knowledge_refs": [{"doc_id":"...","content":"...",...}],        │
│    "diag_result": "string",                                          │
│    "exec_log": [{"command":"...","success":bool,...}],              │
│    "verify_result": {"verify_passed":bool,"before_state":"...",     │
│      "after_state":"...","comparison_notes":"..."},                  │
│    "final_report": "string",                                         │
│    "_completed": false                                               │
│  }                                                                   │
└───────────────────────────┬─────────────────────────────────────────┘
                            │ 1
                            │
                            │ * (FK: alert_id_fk -> alerts.alert_id)
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
        ▼                   ▼                   ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────────┐
│ alert_timeline│  │  approvals   │  │  ★新增★ llm_calls │
│  (已有, 不变) │  │  (已有, 不变) │  │                  │
│              │  │              │  │ id (PK)          │
│ id (PK)      │  │ id (PK)      │  │ alert_id_fk (FK) │
│ alert_id_fk  │  │ alert_id_fk  │  │ endpoint (VARCHAR)│
│ node_name    │  │ checkpoint_id│  │ timestamp (DT)   │
│ state_snap.. │  │ fix_plan     │  │ elapsed_s (FLOAT)│
│ started_at   │  │ risk_level   │  │ prompt_tokens    │
│ completed_at │  │ decision     │  │ completion_token │
│ status       │  │ decided_by   │  │ prompt_summary   │
│              │  │ decided_at   │  │ response_summary │
│              │  │ note         │  │ is_mock (BOOL)   │
│              │  │ created_at   │  │ created_at (DT)  │
└──────────────┘  └──────────────┘  └──────────────────┘
```

**关键关系：**
- `alerts.alert_id` (UUID, UNIQUE) 是中心键，`alert_timeline.alert_id_fk`、`approvals.alert_id_fk`、`llm_calls.alert_id_fk` 均通过外键引用它。
- 本次新增仅涉及 `alerts` 表的 1 个新列（`workflow_state`）和 `llm_calls` 表的创建。
- `alert_timeline` 和 `approvals` 表不做任何 Schema 变更。

---

## 模块详情

---

### MOD-DP-001: Alert ORM Extension（alerts 表扩展）

- **父模块**: `src/database/alert_models.py` (MOD-WEB-003)
- **变更类型**: 修改 -- 在现有 `Alert` 模型中新增 1 列
- **职责**: 为 `alerts` 表添加 `workflow_state` JSON 列，存储工作流生成的 6 个关键状态字段的完整内容
- **覆盖需求**: REQ-FUNC-001, REQ-FUNC-005
- **覆盖用户故事**: US-001, US-005

**修改内容：**

在 `Alert` 类中新增以下映射列（在 `status` 列定义之后）：

```
workflow_state: Mapped[Optional[dict[str, Any]]] = mapped_column(
    JSON, nullable=True, default=None,
    comment="工作流状态JSON: {fix_plan,root_cause,diag_result,exec_log,verify_result,final_report,_completed}"
)
```

**不变更内容：**
- `alert_id`、`alert_type`、`severity`、`content`、`device_info`、`source`、`status` 列定义完全不变
- `AlertTimeline` 模型不变
- `Approval` 关系不变（`approvals: Mapped[list["Approval"]]` 保持不变）

**现有数据兼容性：**
- `workflow_state` 默认值为 `NULL`，现有旧告警（数据持久化修复前创建的）的 `workflow_state` 为 NULL
- 读取时 Repository 方法返回 `None` 表示无工作流状态数据，API 层将 `None` 映射为相应字段的 null/空值

---

### MOD-DP-002: LLMCallLog ORM（llm_calls 表，新增）

- **文件位置**: `src/database/llm_call_models.py`（新文件）
- **变更类型**: 新增 -- 新建 ORM 模型
- **职责**: 定义 `llm_calls` 表结构，存储每次 LLM API 调用的详细记录
- **覆盖需求**: REQ-FUNC-002
- **覆盖用户故事**: US-002

**公开接口契约（SQLAlchemy ORM 模型定义）：**

```
IFC-DP-002-01: id — 主键
  Mapped[int], Integer, primary_key=True, autoincrement=True

IFC-DP-002-02: alert_id_fk — 关联告警，FK -> alerts.alert_id
  Mapped[str], String(36), ForeignKey("alerts.alert_id", ondelete="CASCADE"),
  nullable=False, index=True

IFC-DP-002-03: endpoint — LLM 调用端点标识
  Mapped[str], String(50), nullable=False,
  取值: "analyze_root_cause" | "fill_template_params" | "generate_report" | "mock"

IFC-DP-002-04: timestamp — 调用时间戳
  Mapped[datetime], DateTime, nullable=False,
  default=lambda: datetime.now(timezone.utc)

IFC-DP-002-05: elapsed_s — 调用耗时（秒）
  Mapped[float], Float, nullable=False, default=0.0

IFC-DP-002-06: prompt_tokens — prompt token 用量
  Mapped[int], Integer, nullable=False, default=0

IFC-DP-002-07: completion_tokens — completion token 用量
  Mapped[int], Integer, nullable=False, default=0

IFC-DP-002-08: prompt_summary — prompt 摘要（截断至 3000 字符）
  Mapped[Optional[str]], Text, nullable=True

IFC-DP-002-09: response_summary — response 摘要（截断至 3000 字符）
  Mapped[Optional[str]], Text, nullable=True

IFC-DP-002-10: is_mock — 是否为 Mock 调用
  Mapped[bool], Boolean, nullable=False, default=False

IFC-DP-002-11: created_at — 记录创建时间
  Mapped[datetime], DateTime, nullable=False,
  default=lambda: datetime.now(timezone.utc)
```

表级索引：
```
__table_args__ = (
    Index("idx_llm_calls_alert", "alert_id_fk"),
    Index("idx_llm_calls_endpoint", "endpoint"),
)
```

---

### MOD-DP-003: LLMCallLogRepository（新增）

- **文件位置**: `src/database/repositories/llm_call_repository.py`（新文件）
- **变更类型**: 新增
- **职责**: 提供 `llm_calls` 表的 CRUD 操作，支持按 alert_id 查询 LLM 调用日志和创建新日志
- **覆盖需求**: REQ-FUNC-002
- **覆盖用户故事**: US-002
- **依赖模块**: MOD-DP-002

**公开接口契约：**

```
IFC-DP-003-01: create_log(db: Session, log_data: dict) -> LLMCallLog
  描述: 创建并持久化一条 LLM 调用日志记录。
  输入:
    - db: SQLAlchemy Session（由调用方提供）
    - log_data: dict，必须包含字段:
      alert_id_fk (str), endpoint (str), elapsed_s (float),
      prompt_tokens (int), completion_tokens (int)
      可选字段:
      prompt_summary (str|null), response_summary (str|null),
      is_mock (bool, 默认 false), timestamp (datetime, 默认 now)
  返回: 已持久化并 refresh 的 LLMCallLog ORM 对象
  异常: 无显式异常（DB 写入失败时异常向上传播）
  关联需求: REQ-FUNC-002, US-002 AC-002-01
  备注: 写入后执行 db.commit() + db.refresh()

IFC-DP-003-02: get_logs_by_alert_id(db: Session, alert_id: str) -> list[LLMCallLog]
  描述: 按 alert_id 查询所有关联的 LLM 调用日志，按 timestamp 升序排列。
  输入:
    - db: SQLAlchemy Session
    - alert_id: str — alerts.alert_id 的值
  返回: list[LLMCallLog] — 可能为空列表
  异常: 无（查询无结果时返回空列表）
  关联需求: REQ-FUNC-002, US-002 AC-002-02, AC-002-03

IFC-DP-003-03: get_logs_by_alert_id_as_dicts(db: Session, alert_id: str) -> list[dict]
  描述: 同 get_logs_by_alert_id，但返回适合 JSON 序列化的字典列表。
  输入:
    - db: SQLAlchemy Session
    - alert_id: str
  返回: list[dict] — 每条记录的字典表示:
    {"endpoint": str, "timestamp": str (HH:MM:SS), "elapsed_s": float,
     "prompt_tokens": int, "completion_tokens": int,
     "prompt": str, "response": str}
  关联需求: REQ-FUNC-006, US-006 AC-006-02
  备注: timestamp 序列化为 "HH:MM:SS" 格式字符串（与现有 API 行为一致）；
        prompt_summary -> "prompt", response_summary -> "response"（映射到 API 字段名）
```

---

### MOD-DP-004: AlertRepository Extension（扩展）

- **父模块**: `src/database/repositories/alert_repository.py` (MOD-WEB-004)
- **变更类型**: 修改 -- 在现有 `AlertRepository` 中新增 2 个方法
- **职责**: 提供工作流状态的持久化读/写和 JSON 增量合并能力
- **覆盖需求**: REQ-FUNC-001, REQ-FUNC-005
- **覆盖用户故事**: US-001, US-005
- **依赖模块**: MOD-DP-001

**新增公开接口契约：**

```
IFC-DP-004-01: update_workflow_state(db: Session, alert_id: str, partial_update: dict) -> Alert | None
  描述: 对指定告警的 workflow_state JSON 列执行增量更新（deep merge）。
       读取当前 workflow_state 值，将 partial_update 深度合并，写回。
       若当前值为 NULL，以 partial_update 为初始值。
  输入:
    - db: SQLAlchemy Session
    - alert_id: str — 告警 UUID
    - partial_update: dict — 需合并的键值对
      例: {"root_cause": "...", "knowledge_refs": [...]}
      例: {"fix_plan": {...}}
      例: {"final_report": "...", "_completed": true}
  返回: 更新后的 Alert ORM 对象，alert_id 不存在则返回 None
  合并策略:
    - 嵌套 dict 递归合并（deep merge）
    - list 直接替换（不追加）
    - 标量值（str/int/bool/float）直接替换
  实现逻辑:
    1. alert = get_alert_by_id(alert_id)
    2. if alert is None: return None
    3. current = alert.workflow_state or {}
    4. merged = _deep_merge(current, partial_update)
    5. alert.workflow_state = merged
    6. alert.updated_at = datetime.now(timezone.utc)
    7. db.commit(); db.refresh(alert); return alert
  线程安全: LangGraph 节点单线程串行执行，同一 alert_id 只有一个线程写入
  关联需求: REQ-FUNC-001 (fix_plan 写入), REQ-FUNC-005 (工作流状态写入)

IFC-DP-004-02: get_workflow_state(db: Session, alert_id: str) -> dict | None
  描述: 获取指定告警的 workflow_state JSON 列值。
  输入:
    - db: SQLAlchemy Session
    - alert_id: str
  返回: dict — workflow_state 的完整字典；列值为 NULL 或 alert 不存在则返回 None
  关联需求: REQ-FUNC-006 (API 从 DB 读取工作流状态)
```

**复用现有方法（不变更签名）：**
- `get_alert_by_id(alert_id)` — 已有，IFC-WEB-004-02
- `get_alert_timeline(alert_id)` — 已有，IFC-WEB-004-03
- `update_alert_status(alert_id, status)` — 已有，IFC-WEB-004-06
- `list_alerts(...)`、`create_alert(...)`、`append_timeline_entry(...)`、`list_by_inspection_record(...)` — 已有，不变

---

### MOD-DP-005: ApprovalRepository Extension（扩展）

- **父模块**: `src/database/repositories/approval_repository.py` (MOD-WEB-004)
- **变更类型**: 修改 -- 在现有 `ApprovalRepository` 中新增 1 个方法
- **职责**: 提供按 alert_id 查询审批记录的能力
- **覆盖需求**: REQ-FUNC-004
- **覆盖用户故事**: US-004
- **依赖模块**: MOD-WEB-003 (Approval ORM)

**新增公开接口契约：**

```
IFC-DP-005-01: get_approvals_by_alert_id(db: Session, alert_id: str) -> list[Approval]
  描述: 按告警的 alert_id 查询其所有关联审批记录，按 created_at 降序排列。
  输入:
    - db: SQLAlchemy Session
    - alert_id: str — 对应 approvals.alert_id_fk
  返回: list[Approval] — 该告警的所有审批记录（可能为空列表）
  异常: 无（查询无结果时返回空列表，不抛出异常）
  查询: SELECT * FROM approvals WHERE alert_id_fk = ? ORDER BY created_at DESC
  关联需求: REQ-FUNC-004, US-004 AC-004-01, AC-004-02, AC-004-03
  备注: 返回完整 Approval 对象（checkpoint_id, fix_plan, risk_level,
        decision, decided_by, decided_at, note, created_at）
```

**复用现有方法（不变更）：**
- `list_pending_approvals()`、`get_approval_by_checkpoint()`、`create_approval()`、`update_approval_decision()`、`list_approval_history()` — 全部已有，签名和行为不变

---

### MOD-DP-006: NodeHandlers Extension（工作流节点处理器扩展）

- **父模块**: `src/orchestration/node_handlers.py` (MOD-005)
- **变更类型**: 修改 -- 在 6 个状态产生节点中新增 DB 写操作
- **职责**: 在每次工作流节点生成状态数据后，立即将数据持久化到 alerts.workflow_state
- **覆盖需求**: REQ-FUNC-001, REQ-FUNC-005
- **覆盖用户故事**: US-001, US-005
- **依赖模块**: MOD-DP-004

**修改清单：6 个节点各新增 DB 写操作**

以下每个变更均在节点处理器返回 `dict[str, Any]` 之前执行：

```
★ 节点 1: handle_collect_diag (IFC-005-06) -- 第 6 个节点
  新增写入字段: diag_result
  写入时机: self._log_node(state, node, "END") 之前
  写入调用:
    AlertRepository(db).update_workflow_state(alert_id, {"diag_result": value})
  异常处理: DB 写入失败仅 log warning，不阻塞工作流
  关联需求: REQ-FUNC-005 (diag_result 持久化)

★ 节点 2: handle_analyze_root_cause (IFC-005-07) -- 第 7 个节点
  新增写入字段: root_cause, knowledge_refs
  写入时机: self._log_node(state, node, "END") 之前
  写入调用:
    AlertRepository(db).update_workflow_state(alert_id, {
        "root_cause": value, "knowledge_refs": value
    })
  关联需求: REQ-FUNC-005 (root_cause 持久化)

★ 节点 3: handle_generate_fix_plan (IFC-005-08) -- 第 8 个节点
  新增写入字段: fix_plan
  写入时机: self._log_node(state, node, "END") 之前
  写入调用:
    AlertRepository(db).update_workflow_state(alert_id, {"fix_plan": fix_plan_dict})
  关联需求: REQ-FUNC-001 (fix_plan 持久化), US-001 AC-001-01
  备注: 覆盖所有告警（低风险+高风险），弥补了仅高风险告警在 approvals.fix_plan 中有部分数据的缺陷

★ 节点 4: handle_execute_fix (IFC-005-12) -- 第 12 个节点
  新增写入字段: exec_log
  写入时机: self._log_node(state, node, "END") 之前
  写入调用:
    AlertRepository(db).update_workflow_state(alert_id, {"exec_log": exec_log_list})
  关联需求: REQ-FUNC-005 (exec_log 持久化), US-005 AC-005-05

★ 节点 5: handle_verify_result (IFC-005-13) -- 第 13 个节点
  新增写入字段: verify_result
  写入时机: self._log_node(state, node, "END") 之前
  写入调用:
    AlertRepository(db).update_workflow_state(alert_id, {"verify_result": verify_result_dict})
  关联需求: REQ-FUNC-005 (verify_result 持久化)

★ 节点 6: handle_final_report (IFC-005-14) -- 第 14 个节点
  新增写入字段: final_report, _completed=true
  写入时机: 在现有的 status 同步之后、self._log_node(state, node, "END") 之前
  写入调用:
    AlertRepository(db).update_workflow_state(alert_id, {
        "final_report": value, "_completed": True
    })
  关联需求: REQ-FUNC-005 (final_report 持久化)
  备注: _completed=true 标志着工作流状态写入已完成
```

**不变更的节点（8 个）：**
- `handle_receive_alert`、`handle_parse_alert`、`handle_validate_alert` -- 不产生需持久化的关键状态
- `handle_get_device_info`、`handle_establish_ssh` -- 不产生新的关键状态数据
- `handle_assess_risk` -- 已有 approval 持久化逻辑，本次不新增
- `handle_human_approval` -- 审批状态已有 approvals 表管理
- `handle_backup_config` -- config_backup/backup_id 不在 REQ-FUNC-005 范围内

**DB Session 管理策略：**
- 每个节点使用独立的 `SessionLocal()` 实例（与现有 `_log_node` L141、`handle_assess_risk` L491 保持一致）
- 每次写入后立即 `db.commit()` + `db.close()`
- 不通过 NodeHandlers 构造函数注入 Session，保持构造函数签名不变

---

### MOD-DP-007: LLMService Extension（LLM 服务扩展）

- **父模块**: `src/llm/llm_service.py` (MOD-006)
- **变更类型**: 修改 -- `_call_llm` 方法中新增 DB 双写逻辑
- **职责**: 在每次 LLM 调用完成后，除了写入内存 `_llm_call_log` dict，同时写入 `llm_calls` 数据库表
- **覆盖需求**: REQ-FUNC-002
- **覆盖用户故事**: US-002
- **依赖模块**: MOD-DP-003

**修改内容：**

```
★ 构造函数新增可选参数:
  llm_log_repo: Optional[LLMCallLogRepository] = None
  若为 None，DB 双写功能禁用（向后兼容）

★ _call_llm 方法修改（在现有内存日志写入代码之后新增 DB 双写）:
  现有代码（保持不变）:
    if self._current_context:
        ctx = self._current_context
        if ctx not in self._llm_call_log:
            self._llm_call_log[ctx] = []
        self._llm_call_log[ctx].append({...})  # 内存日志

  新增代码:
    if self._llm_log_repo is not None and self._current_context:
        try:
            from src.database.base import SessionLocal
            db = SessionLocal()
            try:
                self._llm_log_repo.create_log(db, {
                    "alert_id_fk": self._current_context,
                    "endpoint": endpoint,
                    "elapsed_s": round(elapsed, 2),
                    "prompt_tokens": usage.prompt_tokens if usage else 0,
                    "completion_tokens": usage.completion_tokens if usage else 0,
                    "prompt_summary": prompt[:3000] if prompt else "",
                    "response_summary": output[:3000] if output else "",
                    "is_mock": False,
                })
            finally:
                db.close()
        except Exception as e:
            logger.warning(f"Failed to persist LLM call log to DB: {e}")

  Mock 调用分支 (self._client is None) 同样新增 DB 双写，is_mock=True
```

**不变更内容：**
- `_llm_call_log` 内存字典保留（用于 DB 不可用时的 fallback）
- `get_llm_logs(alert_id)` 方法保留（向后兼容，但 API 层不再调用 -- 见 MOD-DP-008）
- `analyze_root_cause`、`fill_template_params`、`generate_report` 三个公共端点的方法签名不变

---

### MOD-DP-008: alerts_router Extension（告警 API 路由扩展）

- **父模块**: `src/api/alerts_router.py` (MOD-WEB-001)
- **变更类型**: 修改 -- `GET /api/alerts/{alert_id}` 函数重构数据读取逻辑
- **职责**: 将告警详情 API 的全部数据源从 MemorySaver/内存 dict 切换为数据库
- **覆盖需求**: REQ-FUNC-003, REQ-FUNC-006
- **覆盖用户故事**: US-003, US-006
- **依赖模块**: MOD-DP-004 (AlertRepository), MOD-DP-005 (ApprovalRepository), MOD-DP-003 (LLMCallLogRepository)

**公开接口契约（API 端点，签名和响应结构不变）：**

```
IFC-DP-008-01: GET /api/alerts/{alert_id} (重构)
  描述: 返回告警详情，全部数据从 SQLite 数据库读取。
  输入参数（不变）:
    - alert_id: str (路径参数)
    - db: Session = Depends(get_db) (FastAPI 依赖注入)
  响应结构（不变 -- 6 个顶层字段）:
    {
      "alert": Alert ORM 对象,
      "timeline": list[AlertTimeline ORM 对象],
      "fix_plan": dict | null,
      "commands": list[str],
      "llm_calls": list[dict],
      "approval": dict | null
    }
  HTTP 状态码（不变）:
    - 200: 成功返回告警详情
    - 404: 告警不存在 ({"detail": "告警不存在"})

  数据来源映射（变更部分）:
    "alert":     AlertRepository.get_alert_by_id(alert_id)  [已有，不变]
    "timeline":  AlertRepository.get_alert_timeline(alert_id)  [已有，不变]
    "fix_plan":  alert.workflow_state["fix_plan"] (若 workflow_state 存在且含 fix_plan)
    "commands":  alert.workflow_state["fix_plan"]["commands"] (若 fix_plan 存在)
    "llm_calls": LLMCallLogRepository.get_logs_by_alert_id_as_dicts(db, alert_id)
    "approval":  ApprovalRepository.get_approvals_by_alert_id(db, alert_id)
                 -> 取最新一条 -> 映射为:
                 {
                   "need_human_approval": approval is not None,
                   "approval_status": approval.decision or "NOT_REQUIRED",
                   "risk_level": approval.risk_level or "LOW",
                   "decision": approval.decision,
                   "decided_by": approval.decided_by,
                   "decided_at": approval.decided_at.isoformat() if approval.decided_at else null,
                   "note": approval.note or ""
                 }
                 若无审批记录 -> approval = null

  移除代码（约 47 行）:
    - "import sys; main_module = sys.modules.get('src.main')" 块
    - MemorySaver 读取 fix_plan 的 try-except 块
    - NodeHandlers 内存时间线读取块
    - LLMService 内存日志读取块
    - effective_timeline 合并逻辑

  新增代码（约 50-60 行）:
    - Approval 查询 + 映射逻辑
    - workflow_state JSON 解析 + fix_plan/commands 提取
    - LLMCallLogRepository 查询

  关联需求: REQ-FUNC-003, REQ-FUNC-006, US-003, US-006
```

**API 读路径变更示意图：**

```
修复前:
  GET /api/alerts/{alert_id}
    |-- AlertRepository.get_alert_by_id()        -> alert (DB)
    |-- AlertRepository.get_alert_timeline()     -> timeline (DB)
    |-- state_graph_engine.get_workflow_state()  -> fix_plan, approval (MemorySaver)
    |-- node_handlers.get_timeline()             -> memory_timeline (dict)
    +-- llm_service.get_llm_logs()               -> llm_calls (dict)

修复后:
  GET /api/alerts/{alert_id}
    |-- AlertRepository.get_alert_by_id()                        -> alert (DB)
    |-- AlertRepository.get_alert_timeline()                     -> timeline (DB)
    |-- alert.workflow_state (JSON 列)                           -> fix_plan, commands (DB)
    |-- ApprovalRepository.get_approvals_by_alert_id()           -> approval (DB)
    +-- LLMCallLogRepository.get_logs_by_alert_id_as_dicts()     -> llm_calls (DB)
```

---

## 依赖关系图（文本格式）

```
MOD-DP-008 (alerts_router)
  |-- -> MOD-DP-004 (AlertRepository)          [get_alert_by_id, get_alert_timeline]
  |-- -> MOD-DP-005 (ApprovalRepository)       [get_approvals_by_alert_id]
  +-- -> MOD-DP-003 (LLMCallLogRepository)     [get_logs_by_alert_id_as_dicts]

MOD-DP-006 (NodeHandlers)
  +-- -> MOD-DP-004 (AlertRepository)          [update_workflow_state]

MOD-DP-007 (LLMService)
  +-- -> MOD-DP-003 (LLMCallLogRepository)     [create_log]

MOD-DP-004 (AlertRepository)
  +-- -> MOD-DP-001 (Alert ORM)                [Alert.workflow_state]

MOD-DP-005 (ApprovalRepository)
  +-- -> MOD-WEB-003 (Approval ORM)            [已有关系，不变]

MOD-DP-003 (LLMCallLogRepository)
  +-- -> MOD-DP-002 (LLMCallLog ORM)           [LLMCallLog 表操作]

MOD-DP-001 (Alert ORM)                         [依赖 Base, TimestampMixin -- 已有]
MOD-DP-002 (LLMCallLog ORM)                    [依赖 Base -- 已有]
```

**循环依赖检查：无循环依赖。** 所有边方向为：编排/API 层 -> Repository 层 -> ORM 层。

---

## 需求到模块覆盖矩阵

| REQ ID | 需求描述 | 覆盖模块 | 覆盖方式 |
|--------|---------|---------|---------|
| REQ-FUNC-001 | fix_plan 持久化到数据库 | MOD-DP-001 (+workflow_state), MOD-DP-006 (handle_generate_fix_plan), MOD-DP-004 (update_workflow_state) | generate_fix_plan 节点后将 fix_plan 写入 alerts.workflow_state |
| REQ-FUNC-002 | LLM 调用详情持久化到数据库 | MOD-DP-002 (llm_calls), MOD-DP-003 (LLMCallLogRepo), MOD-DP-007 (LLMService) | 每次 _call_llm 后双写至 llm_calls 表 |
| REQ-FUNC-003 | API 从 DB 读取审批信息 | MOD-DP-008 (alerts_router), MOD-DP-005 (get_approvals_by_alert_id) | API 调用 ApprovalRepository 替代 MemorySaver |
| REQ-FUNC-004 | ApprovalRepository 支持 get_approvals_by_alert_id | MOD-DP-005 (ApprovalRepository) | 新增 IFC-DP-005-01 方法 |
| REQ-FUNC-005 | 工作流状态持久化（5字段） | MOD-DP-001 (+workflow_state), MOD-DP-006 (6节点写), MOD-DP-004 (update_workflow_state) | 各节点写自己负责的字段到 alerts.workflow_state |
| REQ-FUNC-006 | GET /api/alerts/{alert_id} 全面切换为 DB | MOD-DP-008 (alerts_router) | 移除 MemorySaver/dict 读路径，6 个字段全从 DB 读取 |

| REQ-NFUNC | 非功能需求 | 覆盖方式 |
|-----------|-----------|---------|
| REQ-NFUNC-001 | 数据一致性 | write-through 即时写入策略 (ADR-DP-003) |
| REQ-NFUNC-002 | 重启可恢复 | DB 为唯一持久化数据源 (ADR-DP-004) |
| REQ-NFUNC-003 | 向后兼容 | API 6 个字段名和结构不变 (ADR-DP-006) |
| REQ-NFUNC-004 | 不引入新依赖 | 仅使用 SQLite + SQLAlchemy 2.0 + JSON 列 |
| REQ-NFUNC-005 | 不破坏现有表 | alerts +1 列 (default=NULL)，llm_calls 独立新表 |
</file_path>
