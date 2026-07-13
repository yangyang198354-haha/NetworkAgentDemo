# 数据持久化修复项目概要

## 项目名称
NetworkAgentDemo 数据持久化修复（Data Persistence Fix）

## 背景
NetworkAgentDemo 是一个 LangGraph 网络自动化 Agent，当前告警管理详情页面存在严重的数据持久化缺陷。关键工作流状态数据仅存储在内存（LangGraph MemorySaver、Python dict）中，服务器重启后全部丢失。

## 已识别的问题

经过深入代码审查，发现以下 5 个数据持久化问题：

### 问题 1：修复方案 (fix_plan) 不持久化
- fix_plan 仅存储在 LangGraph MemorySaver（纯内存 dict）
- `alerts` 表无 fix_plan 列，无单独的 fix_plans 表
- 仅高风险告警的 fix_plan 截断存入 approvals.fix_plan，低风险告警完全不持久化
- 服务器重启后全部丢失

### 问题 2：LLM 调用详情 (LLM call logs) 不持久化
- LLMService._llm_call_log 是纯 Python dict（`src/llm/llm_service.py:41`）
- 没有 llm_calls 数据库表
- 重启即丢失

### 问题 3：审批信息不被 API 读取
- 审批数据虽持久化到 approvals 表
- 但告警详情 API (`GET /api/alerts/{alert_id}`) 从 MemorySaver 读取审批信息（`src/api/alerts_router.py:94-99`）
- 从未查询 approvals 表，导致数据库中的审批记录不可见

### 问题 4：ApprovalRepository 缺少按 alert_id 查询的方法
- 只有 get_approval_by_checkpoint() 方法（`src/database/repositories/approval_repository.py:39`）
- 无 get_approvals_by_alert_id() 方法

### 问题 5：工作流状态完全内存化
- root_cause, diag_result, exec_log, verify_result, final_report 等均只在 MemorySaver 中
- 无对应的数据库列或表（`src/models/state.py` 定义的字段没有持久化映射）
- 告警详情 API 尝试从 MemorySaver 读取这些字段（`src/api/alerts_router.py:84-87`）

## 核心文件位置（project_workspace/ 下）

- `src/database/alert_models.py` — Alert ORM 模型（alerts 表仅有基本字段，缺少工作流状态字段）
- `src/database/approval_models.py` — Approval ORM 模型（已有 approvals 表，但未被 API 使用）
- `src/database/repositories/alert_repository.py` — Alert 仓库（缺少工作流状态持久化方法）
- `src/database/repositories/approval_repository.py` — Approval 仓库（缺少 get_approvals_by_alert_id()）
- `src/api/alerts_router.py` — 告警 API 路由（GET /api/alerts/{alert_id} 第66-129行从内存读取，而非数据库）
- `src/orchestration/state_graph_engine.py` — StateGraph 引擎（MemorySaver 定义在第44行）
- `src/orchestration/node_handlers.py` — 工作流节点处理器（执行过程中产生所有工作流中间状态）
- `src/llm/llm_service.py` — LLM 服务（_llm_call_log 在第41行，纯内存字典）
- `src/models/state.py` — NetworkAgentState TypedDict（定义了所有工作流状态字段但未持久化）

## 目标与约束

1. **数据一致性**：工作流状态与数据库状态一致
2. **可持久化**：所有关键数据重启后不丢失
3. **向后兼容**：不破坏现有 API 契约
4. **测试覆盖**：确保修改有充分的测试验证
5. **Demo 可接受**：SQLite 存储，不引入新依赖
