<file_header>
  <project_name>NetworkAgentDemo</project_name>
  <author_agent>sub_agent_requirement_analyst</author_agent>
  <file_type>USER_STORIES</file_type>
  <version>0.1.0</version>
  <status>DRAFT</status>
  <created_at>2026-07-16T00:00:00Z</created_at>
  <invocation_id>timeline-enhancement-phase-requirements</invocation_id>
  <description>Alert Detail Page Timeline Component Enhancement — User Stories</description>
</file_header>

# 告警详情页处理时间线（Timeline）组件增强 — 用户故事清单

## 用户角色地图（Actor × Feature Matrix）

| Actor（用户角色） | 序号显示 | 耗时显示 | 状态显示 | 实时进度 | 历史兼容 |
|---|---|---|---|---|---|
| **网络运维人员**（监控/排障） | US-001 | US-002 | US-003 | US-004 | US-005 |

> 说明：本次增强面向单一用户角色——通过网络自动化 Agent 进行告警处理的运维人员。该角色需要在告警详情页查看 workflow 的执行情况以便排障和性能分析。

---

## 用户故事详情

---

### US-001: 查看节点执行序号

- **用户故事**：As a 网络运维人员，I want to 在告警详情页的处理时间线中看到每个节点的执行序号，so that 我能清晰理解 LangGraph 工作流中各节点的实际执行顺序。
- **关联需求**：REQ-FUNC-001（序号显示）
- **优先级**：P0（Must Have）
- **故事点**：[INFERRED — 待开发团队评估]

**验收标准：**

- **AC-001-01**（正常路径 — 完整工作流）
  - Given 一个已完成的告警 workflow，其执行路径包含 8 个节点（receive_alert -> parse_alert -> validate_alert -> get_device_info -> establish_ssh -> collect_diag -> analyze_root_cause -> generate_fix_plan -> assess_risk -> backup_config -> execute_fix -> verify_fix -> finish_report 中的实际激活子集）
  - When 运维人员打开该告警的 "处理时间线" Tab
  - Then 每条时间线条目左侧显示一个从 1 开始、连续递增的序号，序号顺序与 `started_at` 时间戳升序一致

- **AC-001-02**（条件路由路径 — 跳过节点）
  - Given 一个因告警校验失败（is_valid=false）而提前终止的 workflow
  - When 运维人员查看其时间线
  - Then 时间线仅显示实际执行的 4 个节点（receive_alert, parse_alert, validate_alert, finish_report），序号分别为 1, 2, 3, 4，且序号之间无空位

- **AC-001-03**（进行中的工作流）
  - Given 一个正在执行中的 workflow，当前已完成 receive_alert 和 parse_alert，collect_diag 正在 RUNNING
  - When 运维人员刷新页面查看时间线
  - Then 已完成和运行中的条目均显示序号，运行中的条目序号在所有已完成条目之后连续排列

---

### US-002: 查看节点处理耗时

- **用户故事**：As a 网络运维人员，I want to 在告警详情页的处理时间线中看到每个节点消耗的处理时间，so that 我能快速定位 workflow 中的性能瓶颈节点。
- **关联需求**：REQ-FUNC-002（耗时显示）、REQ-FUNC-005（耗时准确计算）
- **优先级**：P0（Must Have）
- **故事点**：[INFERRED — 待开发团队评估]

**验收标准：**

- **AC-002-01**（已完成节点 — 显示耗时）
  - Given 一个已完成的告警 workflow，其中 analyze_root_cause 节点从 started_at 到 completed_at 耗时 2350 毫秒
  - When 运维人员查看该告警的时间线
  - Then analyze_root_cause 条目上显示耗时信息（如 "2.35s" 或 "2350ms"），且数值与数据库中 started_at 和 completed_at 的差值一致

- **AC-002-02**（运行中节点 — 不显示耗时或显示运行中标记）
  - Given 一个正在执行中的 workflow，collect_diag 节点的 completed_at 为 NULL
  - When 运维人员查看该告警的时间线
  - Then collect_diag 条目上不显示固定耗时值，而是显示 "(进行中)" 标记或不显示耗时信息

- **AC-002-03**（历史数据 — 无耗时字段的旧记录）
  - Given 一条在本次增强前创建的 timeline 记录，其 completed_at 和 duration_ms 均为 NULL
  - When 运维人员查看该告警的时间线
  - Then 该条目不显示耗时信息，或显示 "-"，且不会导致页面报错或组件渲染异常

---

### US-003: 查看节点执行成功/失败状态

- **用户故事**：As a 网络运维人员，I want to 在告警详情页的处理时间线中准确看到每个节点是执行成功还是失败，so that 我能第一时间识别 workflow 在哪个环节出了问题。
- **关联需求**：REQ-FUNC-003（成功/失败状态显示）
- **优先级**：P0（Must Have）
- **故事点**：[INFERRED — 待开发团队评估]

**验收标准：**

- **AC-003-01**（成功节点 — 绿色标识）
  - Given 一个正常完成的 workflow，所有节点均执行成功
  - When 运维人员查看该告警的时间线
  - Then 每个已完成条目的状态标签显示 "COMPLETED"，颜色为绿色（#67C23A），与当前 `AlertsDetailView.vue` L200 的 `timelineColor` 映射一致

- **AC-003-02**（失败节点 — 红色标识）
  - Given 一个因 LLM 根因分析异常而失败的 workflow（`node_handlers.py` L449-L455 设置了 `status="FAILED"`）
  - When 运维人员查看该告警的时间线
  - Then analyze_root_cause 条目的状态标签显示 "FAILED"，颜色为红色（#F56C6C），与当前 `AlertsDetailView.vue` L200 的 `timelineColor` 映射一致

- **AC-003-03**（进行中节点 — 蓝色标识）
  - Given 一个正在执行的 workflow
  - When 运维人员查看时间线
  - Then 当前正在执行（未完成）的节点状态显示 "RUNNING"，颜色为蓝色（#409EFF），保持与现有行为一致（`AlertsDetailView.vue` L200）

---

### US-004: 实时查看工作流执行进度

- **用户故事**：As a 网络运维人员，I want to 在 workflow 执行过程中刷新页面即可看到最新的 timeline 条目和实时状态，so that 我能掌握工作流的实时进度而不必等待 workflow 完全结束。
- **关联需求**：REQ-FUNC-006（节点启动时即创建时间线条目）
- **优先级**：P1（Should Have）
- **故事点**：[INFERRED — 待开发团队评估]

**验收标准：**

- **AC-004-01**（节点启动即可见）
  - Given 一个已触发的告警 workflow，parse_alert 节点刚刚开始执行
  - When 运维人员刷新告警详情页
  - Then 时间线中显示 receive_alert（COMPLETED）和 parse_alert（RUNNING）两条条目，parse_alert 的 status=RUNNING 且无 completed_at 显示

- **AC-004-02**（页面刷新获取最新状态）
  - Given 一个正在执行的 workflow，运维人员在 30 秒前看到了 3 条 timeline 条目（2 个 COMPLETED + 1 个 RUNNING）
  - When 运维人员再次手动刷新页面
  - Then 时间线数据从数据库重新加载，展示最新的条目集合，之前 RUNNING 的条目可能已变为 COMPLETED，且新增了后续节点的条目

- **AC-004-03**（历史 workflow 无 RUNNING 条目残留）
  - Given 一个已完成超过 1 小时的 workflow
  - When 运维人员查看其时间线
  - Then 所有条目的 status 均为终态（COMPLETED 或 FAILED），不存在 status=RUNNING 的条目

---

### US-005: 查看历史告警的时间线

- **用户故事**：As a 网络运维人员，I want to 查看本次增强之前产生的历史告警的时间线，页面不会因新增字段缺失而报错，so that 我能正常回顾所有历史告警的处理过程。
- **关联需求**：REQ-NFUNC-001（API 向后兼容）、REQ-NFUNC-002（历史数据兼容）
- **优先级**：P0（Must Have）
- **故事点**：[INFERRED — 待开发团队评估]

**验收标准：**

- **AC-005-01**（旧记录正常展示）
  - Given 一条在本次增强前创建的 timeline 记录，其数据库中不存在 sequence_number 和 duration_ms 列（或值为 NULL）
  - When 运维人员打开该告警的详情页并切换到 "处理时间线" Tab
  - Then 时间线条目正常展示 node_name 和 status，序号和耗时区域显示 "-" 或为空，页面无 JavaScript 控制台错误

- **AC-005-02**（API 响应格式兼容）
  - Given 前端使用与增强前相同的 API 调用方式（`GET /api/alerts/{alert_id}`）
  - When 该 API 返回的 timeline 数组中包含新增字段（sequence_number, duration_ms）
  - Then 前端现有代码（不依赖新字段的逻辑）继续正常工作，`AlertsDetailView.vue` 中的 `v-for="entry in timeline"` 遍历、`entry.node_name`、`entry.status`、`entry.started_at`、`entry.completed_at` 的取值均不受新字段影响

- **AC-005-03**（新旧记录混合列表）
  - Given 某告警有 5 条 timeline 记录，其中前 3 条为增强前创建（无 sequence_number 和 duration_ms），后 2 条为增强后创建（有完整新字段）
  - When 运维人员查看该告警的时间线
  - Then 所有 5 条记录均正常展示，旧记录的新字段显示 fallback 值，新记录显示完整的序号和耗时信息，两者在同一列表中视觉连贯

---

## 优先级汇总

| 优先级 | 用户故事 | 说明 |
|---|---|---|
| P0 (Must Have) | US-001, US-002, US-003, US-005 | 核心功能（序号、耗时、状态）+ 向后兼容 |
| P1 (Should Have) | US-004 | 实时进度可见（节点启动即入库） |

## 故事依赖关系

```
US-005（历史兼容）← 所有故事的基础前提
      │
      ├─→ US-001（序号显示）← 依赖后端存储 sequence_number
      ├─→ US-002（耗时显示）← 依赖后端存储 duration_ms（REQ-FUNC-005）
      ├─→ US-003（状态显示）← 依赖后端准确写入 status（非固定 COMPLETED）
      └─→ US-004（实时进度）← 依赖 REQ-FUNC-006（START 阶段即入库）
```

## 推断性内容说明

| 条目 | 推断内容 | 理由 |
|---|---|---|
| US-001~US-005 故事点 | 标记为 `[INFERRED — 待开发团队评估]` | 故事点估算需要架构师/开发团队根据实际实现复杂度评估，需求分析师不负责工程量估算 |
| AC-002-01 耗时格式 | "2.35s" 或 "2350ms" | 展示格式 PM 未指定，已在 `requirements_spec.md` 开放问题 Q1 中提出，此处仅作为验收标准的示例格式 |

所有其他验收标准均直接锚定至用户原始需求、PM 代码分析或现有代码行为（如 `AlertsDetailView.vue` 中已有的颜色映射和字段取值）。
