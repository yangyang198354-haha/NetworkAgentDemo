# Web UI 告警详情页增强需求规格说明书

<!--
  file_path: docs/webui_detail_requirements.md
  file_type: REQUIREMENTS
  author_agent: main_agent_pm
  created_at: 2026-07-11T04:00:00Z
  version: 1.0
  status: DRAFT
  project: NetworkAgentDemo v0.2.0
  covers: REQ-WEBUI-FUNC-002 (告警详情查看)
-->

---

## 1. 概述

### 1.1 背景

`GET /api/alerts/{alert_id}` 返回 5 个数据块（`alert`、`timeline`、`fix_plan`、`commands`、`llm_calls`），但前端 `AlertsDetailView.vue` 当前只展示了 `alert`（基本信息）和 `timeline`（时间线），其余 3 个数据块被丢弃未使用。

### 1.2 目标

将告警详情页从单卡片布局重构为 **Tab 切换布局**，完整展示 API 返回的所有数据，提升操作人员的可观测性。

### 1.3 范围

- **改前端**：仅修改 `webui/src/views/alerts/AlertsDetailView.vue`
- **不改后端**：`src/api/alerts_router.py` 已返回所有需要的数据，无需变更
- **不改 Store**：`webui/src/stores/alerts.ts` 的 `fetchAlertDetail` 已返回完整响应对象

### 1.4 技术约束

| 项目 | 值 |
|------|-----|
| 框架 | Vue 3 (Composition API + `<script setup>`) |
| UI 库 | Element Plus |
| 状态管理 | Pinia |
| 语言 | TypeScript |
| 目标文件 | `webui/src/views/alerts/AlertsDetailView.vue` |

---

## 2. 现状与缺口分析

### 2.1 API 返回结构（已有的完整数据）

```json
{
  "alert":     { "alert_id", "alert_type", "severity", "content", "device_info", "status", "source", "created_at" },
  "timeline":  [{"node_name", "state_snapshot", "started_at", "completed_at", "status"}],
  "fix_plan":  {"template_id", "description", "params": {"iface_name":"Gi0/1"}},
  "commands":  ["interface Gi0/1", "no shutdown", "description Gi0/1"],
  "llm_calls": [{"endpoint","elapsed_s","prompt_tokens","completion_tokens","prompt","response"}]
}
```

### 2.2 当前组件消费缺口

| API 字段 | 当前是否使用 | 缺失 |
|----------|-------------|------|
| `alert` | 使用（el-descriptions） | 无 |
| `timeline` | 使用（el-timeline） | 无 |
| `fix_plan` | **未使用** | 修复方案模板、参数、CLI 命令均未展示 |
| `commands` | **未使用** | CLI 命令列表完全不可见 |
| `llm_calls` | **未使用** | LLM 调用记录（端点、Token 消耗、Prompt/Response）不可见 |

---

## 3. 功能需求

### REQ-DETAIL-001: Tab 布局重构

将当前单一 `el-card` 改为 `el-tabs` 布局，包含 5 个 Tab 面板：

```
┌─────────────────────────────────────────────────┐
│  告警详情 — {alert_id 前8位}...    [状态标签]    │
├─────────────────────────────────────────────────┤
│ [基本信息] [处理时间线] [修复方案] [LLM调用详情] [审批信息] │
├─────────────────────────────────────────────────┤
│                                                 │
│           (当前激活 Tab 的内容区)                 │
│                                                 │
└─────────────────────────────────────────────────┘
```

**验收标准：**
- GIVEN 用户进入告警详情页 WHEN 页面加载完成 THEN 默认激活"基本信息"Tab
- GIVEN 用户点击任意 Tab WHEN Tab 切换 THEN 对应内容正确渲染
- GIVEN API 返回各字段为 null/空数组 WHEN 渲染对应 Tab THEN 显示"暂无数据"空状态（el-empty）

---

### REQ-DETAIL-002: 基本信息 Tab

保留现有 `el-descriptions` 组件，字段保持不变。

**UI 元素清单：**

| 元素 | 组件 | 数据源 |
|------|------|--------|
| 告警ID | `el-descriptions-item` | `alert.alert_id` |
| 告警类型 | `el-descriptions-item` + `el-tag` | `alert.alert_type` |
| 严重级别 | `el-descriptions-item` | `alert.severity` |
| 来源 | `el-descriptions-item` | `alert.source` |
| 设备名称 | `el-descriptions-item` | `alert.device_info.device_name` |
| 设备IP | `el-descriptions-item` | `alert.device_info.device_ip` |
| 发生时间 | `el-descriptions-item` (span=2) | `alert.created_at` |
| 告警内容 | `el-descriptions-item` (span=2) | `alert.content` |

**验收标准：**
- GIVEN 告警数据完整 WHEN 渲染基本信息 Tab THEN 8 个字段全部展示，与当前行为一致

---

### REQ-DETAIL-003: 处理时间线 Tab

保留现有 `el-timeline` 组件，逻辑不变。

**UI 元素清单：**

| 元素 | 组件 | 数据源 |
|------|------|--------|
| 时间线条目 | `el-timeline` + `el-timeline-item` | `timeline[]` |
| 节点名称 | `<strong>` 文本 | `entry.node_name` |
| 状态标签 | `el-tag` (颜色映射) | `entry.status` |
| 开始时间 | `timestamp` 属性 | `entry.started_at` |
| 完成时间 | `<p>` 文本 | `entry.completed_at` |
| 空状态 | `el-empty` | 当 `timeline.length === 0` |

**验收标准：**
- GIVEN timeline 有数据 WHEN 渲染处理时间线 Tab THEN 展示时间线列表
- GIVEN timeline 为空 WHEN 渲染处理时间线 Tab THEN 展示 `el-empty` 提示"暂无时间线记录"

---

### REQ-DETAIL-004: 修复方案 Tab （新增）

**UI 元素清单：**

| 区域 | 元素 | 组件 | 数据源 |
|------|------|------|--------|
| 头部 | 模板ID | `el-descriptions-item` | `fix_plan.template_id` |
| 头部 | 描述 | `el-descriptions-item` | `fix_plan.description` |
| 参数表 | 参数名 | `el-table-column` prop="key" | `Object.keys(fix_plan.params)` |
| 参数表 | 参数值 | `el-table-column` prop="value" | `Object.values(fix_plan.params)` |
| CLI命令 | 命令块 | `<pre><code>` 包裹 | `commands[]` 逐行渲染 |
| 空状态 | - | `el-empty` | 当 `fix_plan === null` |

**布局示意：**

```
┌─ 修复方案 ─────────────────────────────────────┐
│  模板ID:  tpl_port_disable                     │
│  描述:    端口禁用修复模板                       │
│                                                │
│  ┌─ 参数列表 ──────────────────────────────┐   │
│  │ 参数名          │ 参数值                │   │
│  │ iface_name      │ Gi0/1                 │   │
│  └──────────────────────────────────────────┘   │
│                                                │
│  CLI 命令序列:                                  │
│  ┌──────────────────────────────────────────┐  │
│  │ interface Gi0/1                           │  │
│  │ no shutdown                               │  │
│  │ description Gi0/1                         │  │
│  └──────────────────────────────────────────┘  │
└────────────────────────────────────────────────┘
```

**验收标准：**
- GIVEN `fix_plan` 不为 null WHEN 渲染修复方案 Tab THEN 展示模板ID、描述、参数表
- GIVEN `commands` 不为空 WHEN 渲染修复方案 Tab THEN 以 `<pre><code>` 展示命令列表
- GIVEN `fix_plan` 为 null WHEN 渲染修复方案 Tab THEN 展示 `el-empty` 提示"暂无修复方案"
- GIVEN `fix_plan.params` 为空对象 WHEN 渲染修复方案 Tab THEN 参数表显示"无参数"

---

### REQ-DETAIL-005: LLM调用详情 Tab （新增）

**UI 元素清单：**

| 元素 | 组件 | 数据源 |
|------|------|--------|
| 调用记录卡片 | `el-card` (v-for 遍历) | `llm_calls[]` |
| 端点名称 | 卡片 header | `call.endpoint` |
| 耗时 | 文本 `{{ call.elapsed_s }}s` | `call.elapsed_s` |
| Token 消耗 | 文本 `{{ call.prompt_tokens }} → {{ call.completion_tokens }}` | prompt_tokens, completion_tokens |
| Prompt 折叠面板 | `el-collapse` > `el-collapse-item` title="Prompt" | `call.prompt` |
| Response 折叠面板 | `el-collapse` > `el-collapse-item` title="Response" | `call.response` |
| 空状态 | `el-empty` | 当 `llm_calls.length === 0` |

**布局示意：**

```
┌─ LLM 调用详情 ────────────────────────────────────┐
│  ┌─ 调用 #1: DeepSeek-V3 ────────────────────┐   │
│  │  耗时: 2.3s    Token: 1,200 → 380         │   │
│  │  ┌▶ Prompt                          [展开] ┐  │   │
│  │  └────────────────────────────────────────┘  │   │
│  │  ┌▶ Response                        [展开] ┐  │   │
│  │  └────────────────────────────────────────┘  │   │
│  └──────────────────────────────────────────────┘   │
│                                                    │
│  ┌─ 调用 #2: DeepSeek-V3 ────────────────────┐   │
│  │  耗时: 1.1s    Token: 800 → 150           │   │
│  │  ...                                       │   │
│  └──────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────┘
```

**验收标准：**
- GIVEN `llm_calls` 有 N 条记录 WHEN 渲染 LLM调用详情 Tab THEN 展示 N 张 `el-card`
- GIVEN 用户点击 Prompt 折叠项 WHEN 展开 THEN 以 `<pre>` 格式显示完整 Prompt 原文
- GIVEN 用户点击 Response 折叠项 WHEN 展开 THEN 以 `<pre>` 格式显示完整 Response 原文
- GIVEN `llm_calls` 为空 WHEN 渲染 LLM调用详情 Tab THEN 展示 `el-empty` 提示"暂无LLM调用记录"

---

### REQ-DETAIL-006: 审批信息 Tab （新增）

审批信息从 `alert` 字段推断，无独立 API 数据源。

**推断规则：**

| 条件 | 风险等级 | 是否需要审批 | 审批状态 |
|------|---------|-------------|---------|
| `alert.severity === 'CRITICAL'` | 高 | 是 | 见下方状态映射 |
| `alert.severity === 'MAJOR'` | 中 | 是 | 见下方状态映射 |
| `alert.severity === 'MINOR'` 或 `'WARNING'` | 低 | 否 | N/A |
| `alert.severity === 'INFO'` | 无 | 否 | N/A |

**审批状态映射（基于 alert.status）：**

| alert.status | 审批状态显示 |
|-------------|------------|
| `PENDING` | 待审批 |
| `PROCESSING` | 已批准（执行中） |
| `CLOSED` | 已批准（已关闭） |
| `REJECTED` | 已拒绝 |
| `FAILED` | 已批准（执行失败） |

**UI 元素清单：**

| 元素 | 组件 | 数据源 |
|------|------|--------|
| 风险等级 | `el-tag` (颜色映射) | 根据 `alert.severity` 推断 |
| 是否需要审批 | `el-tag` (是/否) | 根据风险等级推断 |
| 审批状态 | `el-tag` (颜色映射) | 根据 `alert.status` 推断 |
| 说明文字 | `<p>` 文本 | 静态说明 |

**布局示意：**

```
┌─ 审批信息 ─────────────────────────────────────┐
│  风险等级:    [高]  (el-tag type="danger")      │
│  是否需要审批: [是]  (el-tag type="warning")     │
│  审批状态:    [已批准] (el-tag type="success")   │
│                                                │
│  说明: 审批状态根据告警当前状态自动推断，       │
│  Demo 版本暂不支持在线审批操作。                │
└────────────────────────────────────────────────┘
```

**颜色映射：**
- 风险等级: CRITICAL→`danger`(红), MAJOR→`warning`(橙), MINOR/WARNING→`info`(蓝), INFO→`success`(绿)
- 审批状态: 已批准→`success`(绿), 待审批→`warning`(橙), 已拒绝→`danger`(红), 已批准(失败)→`info`(蓝)

**验收标准：**
- GIVEN `alert.severity === 'CRITICAL'` WHEN 渲染审批信息 Tab THEN 风险等级显示"高"(红色)、需要审批"是"
- GIVEN `alert.status === 'CLOSED'` WHEN 渲染审批信息 Tab THEN 审批状态显示"已批准（已关闭）"

---

## 4. 数据流

```
alerts_router.py                    alerts.ts                      AlertsDetailView.vue
─────────────────                   ─────────                      ────────────────────
GET /{alert_id}                     fetchAlertDetail()             
  ↓                                   ↓                            onMounted →
  return {                           return resp                   const resp = await store.fetchAlertDetail(id)
    alert,         ───────────────→   (full object)                alert    = resp.alert        → Tab 1 基本信息
    timeline,      ───────────────→                               timeline = resp.timeline     → Tab 2 处理时间线
    fix_plan,      ───────────────→                               fixPlan  = resp.fix_plan     → Tab 3 修复方案
    commands,      ───────────────→                               commands = resp.commands     → Tab 3 CLI命令
    llm_calls      ───────────────→                               llmCalls = resp.llm_calls   → Tab 4 LLM调用详情
  }                                                               (alert    → Tab 5 审批信息推断)
```

Store 层 (`alerts.ts`) **不需要修改**，`fetchAlertDetail` 已返回完整响应对象。

---

## 5. 非功能需求

| 编号 | 描述 |
|------|------|
| NFR-001 | LLM 调用的 Prompt/Response 原文可能很长（数千 Token），必须用折叠面板（el-collapse）避免页面过长 |
| NFR-002 | CLI 命令块使用 `<pre><code>` 保持等宽字体和保留换行格式 |
| NFR-003 | 所有 Tab 的数据为 null/undefined/空数组时，显示 `el-empty` 而非空白区域 |
| NFR-004 | Tab 切换不触发额外 API 请求（所有数据在 `onMounted` 时一次性加载） |
| NFR-005 | 组件整体加载状态（`v-loading`）保持不变，包裹整个 `el-tabs` |
| NFR-006 | 保持现有 `statusColor`、`timelineColor`、`timelineStatusTag`、`formatTime` 工具函数不变 |

---

## 6. 变更影响范围

| 文件 | 操作 | 说明 |
|------|------|------|
| `webui/src/views/alerts/AlertsDetailView.vue` | **修改** | 重构为 Tab 布局，新增 3 个 Tab 面板 |
| `webui/src/stores/alerts.ts` | **不改** | fetchAlertDetail 已返回完整数据 |
| `src/api/alerts_router.py` | **不改** | API 已返回所有字段 |
| 其他文件 | **不改** | 无影响 |

---

## 7. 待确认事项

| 编号 | 问题 | 建议默认值 |
|------|------|----------|
| Q-001 | "审批信息"Tab 是否需要保留？当前 API 无独立审批数据，全部从 `alert.severity` 和 `alert.status` 推断 | 保留，标注"Demo版本推断值" |
| Q-002 | 修复方案为 null 时，是隐藏整个 Tab 还是显示"暂无数据"？ | 显示"暂无数据"（保持 Tab 数量一致） |
| Q-003 | `commands` 为空数组但 `fix_plan` 不为 null 时，CLI 命令区域如何展示？ | 显示"无CLI命令" |

---

**文档状态:** DRAFT — 等待用户确认后进入实现阶段
