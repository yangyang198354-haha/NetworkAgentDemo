<file_header>
  <project_name>NetworkAgentDemo</project_name>
  <author_agent>sub_agent_software_developer</author_agent>
  <file_type>IMPLEMENTATION_PLAN</file_type>
  <version>1.0.0</version>
  <status>DRAFT</status>
  <created_at>2026-07-16T00:00:00Z</created_at>
  <invocation_id>timeline-enhancement-phase-implementation</invocation_id>
  <description>Alert Detail Page Timeline Component Enhancement — Implementation Plan</description>
</file_header>

# 告警详情页处理时间线组件增强 — 实现计划

## 实现概览

- **总模块数**: 7 (4 个需代码变更，3 个零变更验证)
- **总文件数**: 4 个源文件修改，0 个新文件
- **实现顺序**: 按拓扑排序（DB 层 → Repository 层 → 编排层 → 前端）

## 模块实现计划（按拓扑顺序）

| 序号 | MOD-ID | 模块名 | 文件路径 | 依赖前置模块 | 复杂度 | 状态 |
|------|--------|--------|---------|------------|--------|------|
| 1 | MOD-TL-001 | AlertTimeline 模型增强 | `src/database/alert_models.py` | — | L | DONE |
| 2 | MOD-TL-003 | AlertRepository 增强 | `src/database/repositories/alert_repository.py` | MOD-TL-001 | M | DONE |
| 3 | MOD-TL-002 | NodeHandlers._log_node() 增强 | `src/orchestration/node_handlers.py` | MOD-TL-003 | H | DONE |
| 4 | MOD-TL-004 | API 响应格式扩展 | `src/api/alerts_router.py` | MOD-TL-003 | L | N/A (零变更) |
| 5 | MOD-TL-007 | API 客户端增强 | `webui/src/stores/alerts.ts` | MOD-TL-004 | L | N/A (零变更) |
| 6 | MOD-TL-005 | 前端 Timeline 组件增强 | `webui/src/views/alerts/AlertsDetailView.vue` | MOD-TL-007 | M | DONE |
| 7 | MOD-TL-006 | 前端自动刷新机制 | `webui/src/views/alerts/AlertsDetailView.vue` | MOD-TL-007 | M | DONE |

## 文件变更清单

| 文件 | 变更类型 | 变更行数（估算） | 说明 |
|------|---------|---------------|------|
| `src/database/alert_models.py` | 修改 | +8 行 | 新增 sequence_number、duration_ms 两个 NULLABLE 列 |
| `src/database/repositories/alert_repository.py` | 修改 | +65 行 | 新增 update_timeline_entry 方法、ensure_timeline_columns 模块级函数 |
| `src/database/base.py` | 修改 | +7 行 | 在 init_db 中调用 ensure_timeline_columns |
| `src/orchestration/node_handlers.py` | 修改 | +90/-30 行 | _log_node 双步持久化重写、status 参数、__seq_counters |
| `webui/src/views/alerts/AlertsDetailView.vue` | 修改 | +65/-10 行 | 模板增强、formatSeq/formatDuration/durationColor 函数、智能轮询 |

## 模块依赖图

```
MOD-TL-001 (AlertTimeline Model)
    ^
    |
MOD-TL-003 (AlertRepository)
    ^
    |
MOD-TL-002 (NodeHandlers._log_node)

MOD-TL-004 (API Router) — 零变更
    ^
    |
MOD-TL-007 (alerts.ts Store) — 零变更
    ^
    |
MOD-TL-005 + MOD-TL-006 (AlertsDetailView.vue)
```

依赖方向全部自下而上，无循环依赖。

## 关键实现决策

1. **sequence_number 生成 (ADR-TL-001)**: 应用层 per-alert 计数器，首次使用时从 DB 查询 MAX(sequence_number) 恢复。
2. **duration_ms 计算 (ADR-TL-002)**: END 阶段基于 started_at_dt 和当前时间计算，精度 < 1ms。
3. **status 判定 (ADR-TL-003)**: _log_node 接受显式 status 参数，默认 "COMPLETED"，handle_analyze_root_cause 异常路径传 "FAILED"。
4. **DB 写入时机 (ADR-TL-004)**: START 阶段 INSERT + END 阶段 UPDATE 双步持久化。
5. **前端刷新 (ADR-TL-005)**: 智能轮询（5s 间隔），alert 终态 + 无 RUNNING 条目时自动停止，最大 15 分钟强制停止。

## 架构偏差记录

无架构偏差。所有实现严格遵循 architecture_design.md 中的 5 个 ADR 和 module_design.md 中的 24 个 IFC 契约。

## 验证结果

回归测试：291 passed, 1 skipped, 1 deselected（预存在的 config 测试失败，与本次变更无关）。无新增失败。

## 遗留事项

1. handle_analyze_root_cause 之外的节点（如 execute_fix、verify_fix）当前无失败检测逻辑，其 timeline status 仍为 COMPLETED。此属于后续需求范畴（ADR-TL-003 Consequences 已标注）。
2. 多 worker 场景的 sequence_number 原子性未处理（当前为单进程，ADR-TL-001 Consequences 已标注）。
