<file_header>
  <author_agent>sub_agent_software_developer</author_agent>
  <timestamp>2026-07-14T00:00:00Z</timestamp>
  <project_name>NetworkAgentDemo</project_name>
  <component>data_persistence</component>
  <phase>PHASE_DP_05 + PHASE_DP_06</phase>
  <group>GROUP_DP_C</group>
  <version>0.1.0</version>
  <status>DRAFT</status>
  <invocation_id>GROUP_DP_C</invocation_id>
  <input_files>
    <file>data_persistence/requirements/dp_requirements_spec.md</file>
    <file>data_persistence/requirements/dp_user_stories.md</file>
    <file>data_persistence/architecture/dp_architecture_design.md</file>
    <file>data_persistence/architecture/dp_module_design.md</file>
    <file>data_persistence/architecture/dp_tech_stack.md</file>
  </input_files>
</file_header>

# 数据持久化修复 — 实现计划

---

## 实现概览

- **总模块数**: 8 (MOD-DP-001 ~ MOD-DP-008)
- **总文件数**: 10 (2 新文件 + 7 修改文件 + 1 模型注册更新)
- **实现顺序**: 按拓扑排序，先实现 ORM 层和数据层，再实现编排层和 API 层
- **架构偏差**: 无

### 拓扑排序实现顺序

```
第1层 (ORM, 零依赖):
  MOD-DP-001: Alert ORM 扩展 (修改 alert_models.py)
  MOD-DP-002: LLMCallLog ORM (新建 llm_call_models.py)

第2层 (Repository, 依赖 ORM):
  MOD-DP-003: LLMCallLogRepository (新建 llm_call_repository.py)
  MOD-DP-004: AlertRepository 扩展 (修改 alert_repository.py)
  MOD-DP-005: ApprovalRepository 扩展 (修改 approval_repository.py)

第3层 (编排/LLM, 依赖 Repository):
  MOD-DP-006: NodeHandlers 扩展 (修改 node_handlers.py)
  MOD-DP-007: LLMService 扩展 (修改 llm_service.py)

第4层 (API, 依赖 Repository):
  MOD-DP-008: alerts_router 重构 (修改 alerts_router.py)

额外:
  模型注册: __init__.py 新增 LLMCallLog 导入
```

---

## 模块实现计划（按拓扑顺序）

| 序号 | MOD-ID | 模块名 | 文件路径 | 依赖前置模块 | 复杂度 | 状态 |
|------|--------|--------|---------|------------|--------|------|
| 1 | MOD-DP-001 | Alert ORM Extension | src/database/alert_models.py | — | L | PLANNED |
| 2 | MOD-DP-002 | LLMCallLog ORM | src/database/llm_call_models.py | — | L | PLANNED |
| 3 | MOD-DP-003 | LLMCallLogRepository | src/database/repositories/llm_call_repository.py | MOD-DP-002 | L | PLANNED |
| 4 | MOD-DP-004 | AlertRepository Extension | src/database/repositories/alert_repository.py | MOD-DP-001 | M | PLANNED |
| 5 | MOD-DP-005 | ApprovalRepository Extension | src/database/repositories/approval_repository.py | MOD-WEB-003 | L | PLANNED |
| 6 | MOD-DP-006 | NodeHandlers Extension | src/orchestration/node_handlers.py | MOD-DP-004 | M | PLANNED |
| 7 | MOD-DP-007 | LLMService Extension | src/llm/llm_service.py | MOD-DP-003 | M | PLANNED |
| 8 | MOD-DP-008 | alerts_router Refactor | src/api/alerts_router.py | MOD-DP-003, MOD-DP-004, MOD-DP-005 | H | PLANNED |
| E1 | — | Model Registration | src/database/__init__.py | MOD-DP-002 | L | PLANNED |

---

## 详细修改点（行级粒度）

### 1. MOD-DP-001: Alert ORM Extension

**文件**: `src/database/alert_models.py`
**操作**: 在 Alert 类的 `status` 列定义之后新增 `workflow_state` 列

```
位置: 第 49 行之后 (status 列定义结束处，空行之前)
新增:
    workflow_state: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSON, nullable=True, default=None,
        comment="工作流状态JSON: {fix_plan,root_cause,diag_result,exec_log,verify_result,final_report,_completed}"
    )

不变更: 所有现有列定义、AlertTimeline 类、Approval 关系、__repr__ 方法
```

### 2. MOD-DP-002: LLMCallLog ORM (新文件)

**文件**: `src/database/llm_call_models.py`
**操作**: 新建完整 LLMCallLog 类

```
实现接口契约:
  IFC-DP-002-01: id (PK, autoincrement)
  IFC-DP-002-02: alert_id_fk (FK→alerts.alert_id, ON DELETE CASCADE, index)
  IFC-DP-002-03: endpoint (VARCHAR 50)
  IFC-DP-002-04: timestamp (DateTime, default=now UTC)
  IFC-DP-002-05: elapsed_s (Float, default=0.0)
  IFC-DP-002-06: prompt_tokens (Integer, default=0)
  IFC-DP-002-07: completion_tokens (Integer, default=0)
  IFC-DP-002-08: prompt_summary (Text, nullable)
  IFC-DP-002-09: response_summary (Text, nullable)
  IFC-DP-002-10: is_mock (Boolean, default=False)
  IFC-DP-002-11: created_at (DateTime, default=now UTC)

表级索引:
  __table_args__ = (
      Index("idx_llm_calls_alert", "alert_id_fk"),
      Index("idx_llm_calls_endpoint", "endpoint"),
  )
```

### 3. MOD-DP-003: LLMCallLogRepository (新文件)

**文件**: `src/database/repositories/llm_call_repository.py`
**操作**: 新建完整 Repository 类

```
实现接口契约:
  IFC-DP-003-01: create_log(db, log_data) -> LLMCallLog
    创建 LLMCallLog 实例，db.add() + db.commit() + db.refresh()，返回对象

  IFC-DP-003-02: get_logs_by_alert_id(db, alert_id) -> list[LLMCallLog]
    按 alert_id_fk 查询，按 timestamp 升序排列，返回 ORM 对象列表

  IFC-DP-003-03: get_logs_by_alert_id_as_dicts(db, alert_id) -> list[dict]
    调用 get_logs_by_alert_id，映射为字典:
    - endpoint → "endpoint"
    - timestamp → "HH:MM:SS" 格式
    - elapsed_s → "elapsed_s"
    - prompt_tokens → "prompt_tokens"
    - completion_tokens → "completion_tokens"
    - prompt_summary → "prompt"
    - response_summary → "response"
```

### 4. MOD-DP-004: AlertRepository Extension

**文件**: `src/database/repositories/alert_repository.py`
**操作**: 新增 2 个方法 + 1 个静态辅助函数

```
IFC-DP-004-01: update_workflow_state(db, alert_id, partial_update) -> Alert | None
  实现逻辑:
    1. self.get_alert_by_id(alert_id) → alert
    2. if alert is None: return None
    3. current = alert.workflow_state or {}
    4. merged = _deep_merge(current, partial_update)
    5. alert.workflow_state = merged
    6. alert.updated_at = datetime.now(timezone.utc)
    7. self.db.commit(); self.db.refresh(alert); return alert

IFC-DP-004-02: get_workflow_state(db, alert_id) -> dict | None
  实现逻辑:
    1. self.get_alert_by_id(alert_id) → alert
    2. return alert.workflow_state if alert else None

静态辅助函数:
  @staticmethod
  def _deep_merge(base: dict, update: dict) -> dict:
    深度合并: 嵌套 dict 递归合并, list/标量直接替换
```

**不变更**: 所有现有方法的签名和行为完全不变

### 5. MOD-DP-005: ApprovalRepository Extension

**文件**: `src/database/repositories/approval_repository.py`
**操作**: 新增 1 个方法

```
IFC-DP-005-01: get_approvals_by_alert_id(db, alert_id) -> list[Approval]
  实现逻辑:
    SELECT * FROM approvals WHERE alert_id_fk = ? ORDER BY created_at DESC
  返回: 按 created_at DESC 排序的 Approval 列表（空列表无结果）
```

### 6. MOD-DP-006: NodeHandlers Extension

**文件**: `src/orchestration/node_handlers.py`
**操作**: 6 个节点各新增 3-5 行 DB 写代码

```
★ 节点 1: handle_collect_diag (第 313 行之后，_log_node END 之前)
  写入: {"diag_result": combined_result}
  变量: alert_id = state.get("alert_id", "")

★ 节点 2: handle_analyze_root_cause (正常路径, 第 359 行之后，_log_node END 之前)
  写入: {"root_cause": root_cause, "knowledge_refs": knowledge_refs}
  注意: 异常路径 (L333-343) 不写入

★ 节点 3: handle_generate_fix_plan (第 445 行之后，_log_node END 之前)
  写入: {"fix_plan": fix_plan.model_dump()}

★ 节点 4: handle_execute_fix (第 637 行之后，_log_node END 之前)
  写入: {"exec_log": exec_log}

★ 节点 5: handle_verify_result (第 699 行之后，_log_node END 之前)
  写入: {"verify_result": verify.model_dump()}

★ 节点 6: handle_final_report (第 763 行之后，_log_node END 之前)
  写入: {"final_report": final_report, "_completed": True}
```

**通用模式（每个节点）**:
```python
try:
    from src.database.base import SessionLocal
    from src.database.repositories.alert_repository import AlertRepository
    db = SessionLocal()
    try:
        AlertRepository(db).update_workflow_state(alert_id, {...})
    finally:
        db.close()
except Exception as e:
    logger.warning(f"Failed to persist ... to DB: {e}")
```

### 7. MOD-DP-007: LLMService Extension

**文件**: `src/llm/llm_service.py`
**操作**: 构造函数新增参数 + _call_llm 新增 DB 双写

```
修改 1: 构造函数 (第 36 行)
  新增: llm_log_repo: Optional[Any] = None
  赋值: self._llm_log_repo = llm_log_repo

修改 2: _call_llm Mock 分支 (第 145-147 行)
  改动: 将 return self._mock_response(...) 改为先赋值 output = self._mock_response(...)
  新增: DB 双写 (is_mock=True)，然后 return output

修改 3: _call_llm 正常分支 (第 184 行之后)
  在内存日志写入代码 (L170-183) 之后，return output (L185) 之前
  新增: DB 双写 (is_mock=False)
```

**DB 双写通用模式**:
```python
if self._llm_log_repo is not None and self._current_context:
    try:
        from src.database.base import SessionLocal
        db = SessionLocal()
        try:
            self._llm_log_repo.create_log(db, {
                "alert_id_fk": self._current_context,
                "endpoint": endpoint,
                "elapsed_s": round(elapsed, 2),
                "prompt_tokens": ...,
                "completion_tokens": ...,
                "prompt_summary": prompt[:3000] if prompt else "",
                "response_summary": output[:3000] if output else "",
                "is_mock": False/True,
            })
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"Failed to persist LLM call log to DB: {e}")
```

### 8. MOD-DP-008: alerts_router Refactor

**文件**: `src/api/alerts_router.py`
**操作**: 重构 `get_alert_detail` (第 66-129 行)

```
移除: 整个 "import sys; main_module = ..." 代码块 (L76-117, 约 42 行)
  具体移除:
    - L76-101: MemorySaver 读取 fix_plan/approval 的 try-except 块
    - L103-109: NodeHandlers 内存时间线读取块
    - L111-117: LLMService 内存日志读取块
    - L119-120: effective_timeline 合并逻辑

新增 (替代原 L76-120):
  1. fix_plan/commands 提取:
     wf_state = alert.workflow_state
     if wf_state: fix_plan = wf_state.get("fix_plan")...

  2. approval 查询:
     ApprovalRepository(db).get_approvals_by_alert_id(alert_id)
     → 取最新一条 → 映射为 {need_human_approval, approval_status, risk_level, ...}

  3. llm_calls 查询:
     LLMCallLogRepository(db).get_logs_by_alert_id_as_dicts(alert_id)

  4. timeline: 直接使用 repo.get_alert_timeline(alert_id)（无需 fallback）

API 响应结构精确不变: {"alert", "timeline", "fix_plan", "commands", "llm_calls", "approval"}
```

### E1: 模型注册

**文件**: `src/database/__init__.py`
**操作**: 新增 LLMCallLog 导入

```
新增行:
  from .llm_call_models import LLMCallLog
__all__ 中新增:
  "LLMCallLog"
```

---

## 架构偏差记录

无架构偏差。所有实现严格遵循 dp_architecture_design.md 中的 6 个 ADR 决策和 dp_module_design.md 中的 8 个模块定义及 13 个 IFC 接口契约。

## 依赖图验证

```
MOD-DP-008 (alerts_router)
  |-- -> MOD-DP-004 (AlertRepository)
  |-- -> MOD-DP-005 (ApprovalRepository)
  +-- -> MOD-DP-003 (LLMCallLogRepository)

MOD-DP-006 (NodeHandlers)
  +-- -> MOD-DP-004 (AlertRepository)

MOD-DP-007 (LLMService)
  +-- -> MOD-DP-003 (LLMCallLogRepository)

MOD-DP-004 (AlertRepository)
  +-- -> MOD-DP-001 (Alert.workflow_state)

MOD-DP-005 (ApprovalRepository)
  +-- -> MOD-WEB-003 (Approval)  [已有]

MOD-DP-003 (LLMCallLogRepository)
  +-- -> MOD-DP-002 (LLMCallLog)

MOD-DP-001, MOD-DP-002 → 零依赖 (仅依赖 Base/TimestampMixin)
```

**循环依赖检查**: 无。所有边方向为 API/编排层 → Repository 层 → ORM 层。

## 实现的 IFC 契约清单

| IFC-ID | 描述 | 所在模块 | 文件 |
|--------|------|---------|------|
| IFC-DP-002-01~11 | LLMCallLog 11 个字段定义 | MOD-DP-002 | llm_call_models.py |
| IFC-DP-003-01 | create_log | MOD-DP-003 | llm_call_repository.py |
| IFC-DP-003-02 | get_logs_by_alert_id | MOD-DP-003 | llm_call_repository.py |
| IFC-DP-003-03 | get_logs_by_alert_id_as_dicts | MOD-DP-003 | llm_call_repository.py |
| IFC-DP-004-01 | update_workflow_state | MOD-DP-004 | alert_repository.py |
| IFC-DP-004-02 | get_workflow_state | MOD-DP-004 | alert_repository.py |
| IFC-DP-005-01 | get_approvals_by_alert_id | MOD-DP-005 | approval_repository.py |
| IFC-DP-007-01 | _call_llm DB 双写 | MOD-DP-007 | llm_service.py |
| IFC-DP-008-01 | GET /api/alerts/{alert_id} 重构 | MOD-DP-008 | alerts_router.py |
</file_content>
