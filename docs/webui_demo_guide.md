<file_header>
  <author_agent>main_agent_pm</author_agent>
  <timestamp>2026-07-11T00:00:00Z</timestamp>
  <project_name>NetworkAgentDemo</project_name>
  <version>0.2.0</version>
  <status>APPROVED</status>
</file_header>

# NetworkAgentDemo v0.2.0 — Web 版操作演示指南

---

## 目录

1. [登录与概览](#1-登录与概览)
2. [告警管理](#2-告警管理)
3. [工作流可视化（核心）](#3-工作流可视化核心)
4. [人工审批操作](#4-人工审批操作)
5. [设备管理](#5-设备管理)
6. [巡检管理](#6-巡检管理)
7. [知识库管理](#7-知识库管理)
8. [系统配置](#8-系统配置)
9. [端到端演示脚本](#9-端到端演示脚本)

---

## 1. 登录与概览

### 1.1 打开系统

1. 在浏览器中打开 **http://47.109.197.217:8001/**
2. 系统自动跳转到登录页面
3. 输入凭据：

| 字段 | 值 |
|------|-----|
| 用户名 | `admin` |
| 密码 | `admin` |

![登录页面](screenshots/01_login_page.png)

> **内部机制**：前端通过 `POST /auth/login` 发送用户名密码，后端使用 bcrypt（passlib, cost factor=12）验证密码哈希，成功后返回 JWT Token（HS256 签名, 24小时过期）。Token 存储在浏览器 localStorage 中，后续所有 `/api/` 请求通过 Axios 拦截器自动注入 `Authorization: Bearer {token}` 头。

4. 登录成功后进入 **Dashboard 仪表盘**

![Dashboard仪表盘](screenshots/02_dashboard.png)

### 1.2 Dashboard 指标卡片含义

Dashboard 包含以下信息区域：

| 指标卡片 | 数据来源 | 含义 |
|---------|---------|------|
| **告警总数** | `alerts` 表 COUNT | 系统中所有告警记录总数 |
| **今日告警** | `alerts` 表 当日 COUNT | 今天 00:00 至今触发的告警数 |
| **待审批数** | `approvals` 表 `decision=PENDING` COUNT | 当前等待人工审批的高风险操作数 |
| **修复成功率** | `alerts` 表 `status=CLOSED / total` | 自动修复的成功率百分比 |

**图表区域**（基于 ECharts 5.x 渲染）：

| 图表 | 内容 |
|------|------|
| 饼图 | 告警类型分布（PORT_DOWN / CPU_HIGH / MAC_FLAPPING） |
| 柱状图 | 按严重级别统计（CRITICAL / MAJOR / MINOR / WARNING） |
| 折线图 | 每日告警趋势（近 7 天，按天聚合） |
| 环形图 | 修复成功率概览 |

**健康状态面板**：

| 组件 | 正常状态 | 含义 |
|------|---------|------|
| LangGraph | 绿色 `healthy` | 14 节点状态机已编译并运行 |
| RAG | 绿色 `healthy` | Chroma 向量库正常工作，N 篇文档已索引 |
| Scheduler | 绿色 `healthy` | APScheduler 定时巡检正在运行 |
| LLM | 绿色 `healthy` 或 红色 `error` | DeepSeek API 连通性（每 3 秒健康检查） |

> **后台运行**：系统启动后，APScheduler 每 **5 分钟**自动对 Core-SW-01 和 Access-SW-02 执行诊断巡检。由于 Mock 诊断数据包含异常（down 接口、高 CPU），每轮巡检都会持续产生告警。你打开 Dashboard 时应该已经能看到若干条自动出现的告警记录。

![Dashboard健康面板](screenshots/02b_health_panel.png)

---

## 2. 告警管理

### 2.1 查看告警列表

1. 点击左侧导航栏 **"告警管理"**
2. 进入告警列表页，表格展示所有告警记录

![告警列表](screenshots/03_alert_list.png)

**表格列说明**：

| 列名 | 示例值 | 说明 |
|------|--------|------|
| 告警 ID | `ALT-20260711-143052-a1b2c3d4` | UUID 格式唯一标识 |
| 告警类型 | `PORT_DOWN` / `CPU_HIGH` / `MAC_FLAPPING` | 三种预定义告警类型 |
| 严重级别 | `MAJOR` / `WARNING` | 来自告警源或系统推断 |
| 设备名称 | `Core-SW-01` | 告警目标设备 |
| 触发来源 | `INSPECTION` / `WEBHOOK` / `MOCK` | 巡检/Webhook 推送/手动模拟 |
| 发生时间 | `2026-07-11 14:30:52` | 告警时间戳 |
| 状态 | `CLOSED` / `PROCESSING` / `FAILED` | 工作流最终状态 |

**筛选操作**：

1. 使用顶部的**筛选栏**，选择 `alert_type = PORT_DOWN`，列表只显示端口 Down 告警
2. 使用**时间范围选择器**，选择"最近 24 小时"，过滤历史告警
3. 点击列标题可按该列排序
4. 底部分页器支持翻页浏览（每页 20 条）

> **为什么能看到告警**：后台巡检每 5 分钟自动运行一次，Mock 数据中 Core-SW-01 的 Gi0/1 接口状态为 `down`，CPU 利用率为 92%（超过阈值），因此巡检会持续产生 PORT_DOWN 和 CPU_HIGH 告警。每轮产生的告警条目不同（有去重机制，同一设备同一类型在 15 分钟内不重复产生）。

### 2.2 手动模拟发送告警

除了等待巡检自动产生告警，你还可以手动触发任意类型的告警来演示完整流程。

1. 点击左侧 **"告警管理"** > **"模拟告警"** 子菜单（或告警列表页顶部的"模拟告警"按钮）
2. 进入模拟告警表单

![模拟告警表单](screenshots/04_simulate_alert.png)

**操作步骤**：

1. **选择告警类型**：从下拉框选择 `MAC_FLAPPING`（MAC 地址漂移）—— 这是唯一会触发人工审批的高风险类型
2. **选择目标设备**：下拉框动态加载 SQLite 中所有纳管设备，选择 `Core-SW-01`
3. **填写可选参数**：
   - 接口名称：`Gi0/1`
   - MAC 地址：`00:1A:2B:3C:4D:5E`（可选）
   - VLAN ID：`1`（可选）
4. 点击 **"发送模拟告警"** 按钮

![模拟发送成功](screenshots/04b_simulate_success.png)

**系统响应**：

- 前端收到成功响应，显示绿色提示：`模拟告警已发送 | Alert ID: ALT-20260711-xxxxxx`
- 新告警以 `status=PROCESSING` 出现在告警列表第一条
- 告警立即进入 14 节点 LangGraph 状态机开始流转

> **内部发生了什么**：
> 1. 前端 `POST /api/alerts/simulate`（JSON Body）
> 2. 后端 `AlertNormalizer` 将表单数据转化为标准 `Alert` 对象（含 alert_type、device_info、source=MOCK）
> 3. `AlertRepository.create_alert()` 写入 SQLite `alerts` 表（status=PROCESSING）
> 4. `StateGraphEngine.run_workflow(alert)` 启动 LangGraph 工作流
> 5. 14 节点依次执行，每个节点完成后 `AlertRepository.append_timeline_entry()` 写入 `alert_timeline` 表
> 6. 当到达 `assess_risk` 节点后，RiskAssessor 判定 `need_human_approval=True`（风险等级 HIGH）
> 7. LangGraph 在 `human_approval` 节点前通过 `interrupt_before` 挂起
> 8. 审批记录写入 SQLite `approvals` 表（decision=PENDING）

### 2.3 查看告警详情 — 跟随状态机流转

1. 在告警列表中，点击任意一条告警行（或点击"详情"按钮）
2. 进入**告警详情页**

![告警详情页面](screenshots/05_alert_detail.png)

**详情页包含以下 Tab 页**：

#### Tab 1: 基本信息

| 信息组 | 字段 |
|--------|------|
| 告警概要 | alert_id, alert_type, severity, source, status, 发生时间 |
| 设备信息 | device_name, device_ip, device_model, interface_name |
| 告警内容 | 原始告警描述文本 |

#### Tab 2: 处理时间线（核心）

以 **Element Plus Timeline（el-timeline）** 组件展示 14 个节点的执行过程：

```
● 14:30:52.123  receive_alert       ── 接收告警，生成 alert_id
● 14:30:52.126  parse_alert         ── 解析告警字段，提取设备信息
● 14:30:52.130  validate_alert      ── 时效性检查（15分钟TTL）→ is_valid=true
● 14:30:52.132  get_device_info     ── 查询设备库，获取IP/型号/凭据
● 14:30:52.134  establish_ssh       ── [Mock] SSH 连接验证通过
● 14:30:52.137  collect_diag        ── 执行诊断命令（show mac address-table, show logging）
● 14:30:53.210  analyze_root_cause  ── LLM + RAG 根因分析
● 14:30:55.120  generate_fix_plan   ── LLM填参 → OutputValidator校验 → TemplateEngine拼装
● 14:30:55.322  assess_risk         ── RiskAssessor判定 risk_level=HIGH
◉ 14:30:55.323  human_approval      ── ⏸️ 等待人工审批... (当前节点，蓝色高亮)
○               backup_config       ── 等待中
○               execute_fix         ── 等待中
○               verify_result       ── 等待中
○               final_report        ── 等待中
```

每个节点展开可查看该节点的 **State 快照**（节点执行时的 `NetworkAgentState` 字段值）：

![节点State快照](screenshots/05b_node_state.png)

**页面每 3 秒自动轮询** `GET /api/alerts/{alert_id}/workflow`，当工作流推进到新节点时，时间线自动更新，无需手动刷新。

#### Tab 3: 最终报告

当告警处理完成（status=CLOSED）后，此 Tab 展示 LLM 生成的完整处理报告（Markdown 格式），包含：处理摘要、根因分析结论、修复方案、执行记录、验证结果。

---

## 3. 工作流可视化（核心）

### 3.1 查看 14 节点 LangGraph 状态机流转图

1. 点击左侧导航栏 **"工作流可视化"**
2. 进入全局拓扑图页面

![工作流拓扑图](screenshots/06_workflow_graph.png)

页面展示一张 **有向图**（基于 ECharts graph 类型渲染），包含：

- **14 个矩形节点** — 每个 LangGraph 节点
- **有向连线（边）** — 表示流转方向
- **4 条条件边** — 以不同颜色虚线标识，标注决策条件
- **当前激活告警高亮** — 如果有正在处理的告警，对应路径的节点高亮

> **图数据来源**：`GET /api/workflow/graph` 返回 LangGraph StateGraph 的完整拓扑结构（节点列表 + 边列表 + 条件边定义），前端使用 ECharts 的 `graph` 类型（layout: "none"，手动指定节点坐标以保持 14 节点的清晰层级排列）渲染。

### 3.2 每个节点的含义

| 序号 | 节点名称 | 阶段 | 职责 | 写入 State 字段 |
|------|---------|------|------|----------------|
| 1 | **receive_alert** | 接收 | 接收标准 Alert 对象，初始化 State | `alert_id`, `status=ACTIVE` |
| 2 | **parse_alert** | 解析 | 解析告警字段，提取告警类型/内容/设备信息 | `alert_type`, `alert_content`, `alert_timestamp`, `device_info` |
| 3 | **validate_alert** | 校验 | 告警时效性检查（TTL 15分钟）+ 内容完整性校验 | `is_valid` |
| 4 | **get_device_info** | 信息获取 | 从设备库查询 IP/型号/SSH 凭据，补充 device_info | `device_info` (enhanced) |
| 5 | **establish_ssh** | 连接 | [Mock] 验证 SSH 凭据格式，建立连接 | 无新增字段 |
| 6 | **collect_diag** | 诊断 | 根据告警类型选择诊断命令并执行（如 show interface status） | `diag_commands`, `diag_result` |
| 7 | **analyze_root_cause** | 分析 | LLM（DeepSeek）分析根因 + RAG（Chroma）检索相关知识 | `root_cause`, `knowledge_refs` |
| 8 | **generate_fix_plan** | 方案生成 | LLM 填充模板参数 → OutputValidator 安全校验 → TemplateEngine 确定性拼装命令 | `fix_plan` |
| 9 | **assess_risk** | 风险评估 | RiskAssessor 评估操作风险等级（LOW/MEDIUM/HIGH） | `need_human_approval`, `risk_level` |
| 10 | **human_approval** | 审批 | LangGraph Interrupt 挂起点，等待人工审批决策 | `approval_status` |
| 11 | **backup_config** | 备份 | BackupTool 备份设备 running-config 快照 | `config_backup`, `backup_id` |
| 12 | **execute_fix** | 执行 | SwitchConfigTool 逐条下发 CLI 命令（含幂等检查） | `exec_log` |
| 13 | **verify_result** | 验证 | 重新诊断，对比修复前后状态差异 | `verify_result` |
| 14 | **final_report** | 报告 | LLM 生成处理报告，设置最终状态 | `final_report`, `status` |

### 3.3 四条条件边的决策逻辑

```
                         ┌──────────────────────┐
                         │  3. validate_alert    │
                         └──────────┬───────────┘
                                    │
                         CE-001: is_valid?
                         ┌─────────┴─────────┐
                    true │                   │ false/expired
                         ▼                   ▼
              ┌──────────────────┐   ┌──────────────────┐
              │ 4. get_device_info│   │ 14. final_report  │
              └──────────────────┘   │   (status=EXPIRED) │
                                     └──────────────────┘

                         ┌──────────────────────┐
                         │  9. assess_risk       │
                         └──────────┬───────────┘
                                    │
                         CE-002: need_human_approval?
                         ┌─────────┴──────────┐
                    true │                    │ false
                         ▼                    ▼
              ┌──────────────────┐   ┌──────────────────┐
              │ 10. human_approval│   │ 11. backup_config │
              │   (Interrupt)     │   └──────────────────┘
              └──────────────────┘

                         ┌──────────────────────┐
                         │ 11. backup_config     │
                         └──────────┬───────────┘
                                    │
                         CE-003: backup_success?
                         ┌─────────┴──────────┐
                    true │                    │ false
                         ▼                    ▼
              ┌──────────────────┐   ┌──────────────────┐
              │ 12. execute_fix   │   │ 14. final_report  │
              └──────────────────┘   │   (status=FAILED)  │
                                     └──────────────────┘

                         ┌──────────────────────┐
                         │ 13. verify_result     │
                         └──────────┬───────────┘
                                    │
                         CE-004: verify_passed?
                         ┌─────────┴──────────┐
                    true │                    │ false
                         ▼                    ▼
              ┌──────────────────┐   ┌──────────────────┐
              │ 14. final_report  │   │    回滚 (rollback) │
              │ (status=CLOSED)   │   │  → final_report   │
              └──────────────────┘   └──────────────────┘
```

| 条件边 | 判断节点 | 判断字段 | true 路由 | false 路由 | 触发场景 |
|--------|---------|---------|-----------|------------|---------|
| **CE-001** | validate_alert | `is_valid` | get_device_info | final_report (status=EXPIRED) | 告警超过 15 分钟 TTL 或内容为空 |
| **CE-002** | assess_risk | `need_human_approval` | human_approval (Interrupt) | backup_config (跳过审批) | PORT_DOWN(LOW)/CPU_HIGH(MEDIUM)→跳过；MAC_FLAPPING(HIGH)→挂起 |
| **CE-003** | backup_config | `backup_success` | execute_fix | final_report (status=FAILED) | SSH 连接失败或设备不支持配置备份 |
| **CE-004** | verify_result | `verify_passed` | final_report (status=CLOSED) | 回滚 → final_report | 修复后诊断仍检测到异常 |

### 3.4 重点：理解状态机变化 — NetworkAgentState 时序说明

以下以一个 **PORT_DOWN 告警**（低风险，自动执行）为例，展示 `NetworkAgentState` 在 14 个节点间如何逐步填充字段：

```
时间轴 (状态字段填充过程)
═══════════════════════════════════════════════════════════════════════

T0: 告警触发前
    State = {}   (空字典)

T1: receive_alert 执行后
    State = {
      "alert_id": "ALT-20260711-143052-a1b2c3d4",
      "status": "ACTIVE"
    }
    → alert_id 由系统生成 (UUID4)，status 初始化为 ACTIVE

T2: parse_alert 执行后
    State += {
      "alert_type": "PORT_DOWN",
      "alert_content": "Interface Gi0/1 on Core-SW-01 is down...",
      "alert_timestamp": "2026-07-11T14:30:00+08:00",
      "device_info": {
        "device_name": "Core-SW-01",
        "device_ip": "192.168.1.1",
        "interface_name": "Gi0/1"
      }
    }
    → 从原始告警中解析出结构化字段

T3: validate_alert 执行后
    State += {
      "is_valid": true
    }
    → 时效性检查通过（告警时间距今 < 15 分钟），内容长度 > 5 字符
    → 条件边 CE-001 判断 is_valid=true → 进入 get_device_info

T4: get_device_info 执行后
    State.device_info += {
      "device_model": "TP-Link T2600G-28TS",
      "username": "admin",
      "password": "admin123"
    }
    → 从 ConfigManager 查询设备库，补充型号和 SSH 凭据

T5: establish_ssh 执行后
    State = 无变化
    → [Mock 模式] 仅验证凭据格式非空，不真实建立 SSH 连接

T6: collect_diag 执行后
    State += {
      "diag_commands": ["show interface status", "show logging"],
      "diag_result": "--- show interface Gi0/1 ---\nGi0/1  down  down  ...\n..."
    }
    → 根据 alert_type=PORT_DOWN，选择诊断命令（见 DIAG_COMMAND_MAP）
    → SwitchDiagTool 以 Mock 模式返回预设诊断文本

T7: analyze_root_cause 执行后
    State += {
      "root_cause": "接口 Gi0/1 物理层故障，链路协议 down (notconnect)。\n可能原因:\n- 物理线缆断开或松动\n- 对端设备端口 shutdown\n- SFP 模块故障\n建议方向: 首先检查物理连接，尝试 no shutdown 恢复。",
      "knowledge_refs": [
        {"doc_id": "DOC-001", "title": "端口Down故障处理案例", "relevance_score": 0.89},
        {"doc_id": "DOC-003", "title": "交换机接口排障指南", "relevance_score": 0.76}
      ]
    }
    → LLMService.analyze_root_cause() 调用 DeepSeek，传入 alert_content + diag_result
    → RAGService.search() 从 Chroma 向量库检索相关故障案例（相似度 ≥ 0.6）
    → OutputValidator.sanitize_root_cause() 做安全标记（不通过滤命令，仅标记风险）

T8: generate_fix_plan 执行后
    State += {
      "fix_plan": {
        "template_id": "TPL-PORT-ENABLE",
        "params": {"iface_name": "Gi0/1"},
        "commands": [
          "configure terminal",
          "interface Gi0/1",
          "no shutdown",
          "description Auto-recovered by NetworkAgent",
          "end"
        ],
        "risk_hints": ["接口状态变更"],
        "description": "端口启用 — 对 down 状态的接口执行 no shutdown"
      }
    }
    → 安全流程三阶段：
      1. LLM fill_template_params() → 返回 {"iface_name": "Gi0/1"}（纯 JSON）
      2. OutputValidator.validate_params() → 校验 JSON Schema（拒绝任何含 CLI 命令的输出）
      3. TemplateEngine.render() → Jinja2 确定性拼装为 CLI 命令列表（非 LLM 生成）

T9: assess_risk 执行后
    State += {
      "need_human_approval": false,
      "risk_level": "LOW"
    }
    → RiskAssessor 检查 fix_plan.commands，未匹配到高危关键词模式
      （VLAN、port-security、reload 等），判定为 LOW
    → 条件边 CE-002 判断 need_human_approval=false → 跳过 human_approval → 进入 backup_config

T10: human_approval — 跳过（CE-002 路由到 backup_config）

T11: backup_config 执行后
    State += {
      "config_backup": "!running-config\nhostname Core-SW-01\n...",
      "backup_id": "BKP-20260711-143055-a1b2"
    }
    → BackupTool 以 Mock 模式返回预设 running-config 文本（~100 行）
    → 条件边 CE-003 判断 backup_success=true → 进入 execute_fix

T12: execute_fix 执行后
    State += {
      "exec_log": [
        {"command": "configure terminal",     "success": true, "output": "...", "execution_time_ms": 100},
        {"command": "interface Gi0/1",        "success": true, "output": "...", "execution_time_ms": 100},
        {"command": "no shutdown",            "success": true, "output": "...", "execution_time_ms": 100},
        {"command": "description Auto-...",   "success": true, "output": "...", "execution_time_ms": 100},
        {"command": "end",                    "success": true, "output": "...", "execution_time_ms": 100}
      ]
    }
    → SwitchConfigTool 逐条下发命令（Mock 模式全部返回 success）
    → 每条命令执行前做幂等检查，执行后写 AuditLogger

T13: verify_result 执行后
    State += {
      "verify_result": {
        "verify_passed": true,
        "before_state": "...Gi0/1  down  down...",
        "after_state": "...Gi0/1  up  up...",
        "comparison_notes": "Before had issue: True, After has issue: False"
      }
    }
    → 重新执行 diagnostics 获取 after_state，与 T6 的 diag_result (before) 对比
    → 关键词检测: before 含 "down" → after 不含 "down" → verify_passed=true
    → 条件边 CE-004 判断 verify_passed=true → 进入 final_report

T14: final_report 执行后
    State += {
      "final_report": "# 告警处理报告\n\n**告警ID**: ALT-20260711-143052-a1b2c3d4\n...",
      "status": "CLOSED"
    }
    → LLMService.generate_report() 生成 Markdown 格式报告
    → status 设置为 CLOSED
    → 完整 State 写入 alert_timeline 表（最终快照）

═══════════════════════════════════════════════════════════════════════
最终 State 包含了从 T1 到 T14 累积的全部 22 个字段。
工作流总耗时约 4-5 秒（Mock 模式下，真实 SSH 模式会显著更长）。
```

> **对于 MAC_FLAPPING 告警（高风险）**，T9 之后路径不同：
> - T9: `need_human_approval=true`, `risk_level=HIGH`
> - CE-002 → T10: `human_approval` 节点 Interrupt 挂起，状态机暂停
> - 等待用户在 Web UI 审批（见第 4 章）
> - 审批通过后，LangGraph resume → `approval_status=APPROVED` → 进入 T11 backup_config
> - 审批拒绝后 → `approval_status=REJECTED` → 跳过 T11-T13 → T14 final_report (status=REJECTED)

### 3.5 点击节点查看 State 快照

1. 在工作流拓扑图中，点击任意节点（如 `analyze_root_cause`）
2. 右侧弹出 **el-drawer** 面板，展示该节点的完整 State 快照

![节点详情弹窗](screenshots/06b_node_detail.png)

> **数据来源**：`GET /api/workflow/{checkpoint_id}/nodes/{node_name}`，从 LangGraph MemorySaver checkpoint 或 `alert_timeline` 表中读取该节点执行时的状态快照。

---

## 4. 人工审批操作

### 4.1 查看待审批列表

1. 点击左侧导航栏 **"审批管理"** > **"待审批"**
2. 进入待审批列表

![待审批列表](screenshots/07_approval_pending.png)

**表格列说明**：

| 列名 | 示例值 | 说明 |
|------|--------|------|
| 告警 ID | `ALT-20260711-150000-x1y2z3w4` | 触发审批的告警 |
| 告警类型 | `MAC_FLAPPING` | 仅高风险类型会出现在此 |
| 设备名称 | `Core-SW-01` | 目标设备 |
| 修复摘要 | `在接口 Gi0/1 启用 port-security，限制MAC学习数量为2` | 修复方案简述 |
| 风险等级 | `HIGH`（红色标签） | RiskAssessor 评估结果 |
| 挂起时间 | `2026-07-11 15:00:00` | 审批挂起时刻 |

> **侧边栏徽标**：当存在待审批项时，左侧导航栏"审批管理"菜单旁会显示红色数字徽标（Badge），实时反映 `pending_count`。数据每 3 秒通过 `GET /api/approvals/pending` 轮询更新。

### 4.2 高危操作触发人工审批的机制

只有 **MAC_FLAPPING**（MAC 地址漂移）告警会触发人工审批。原因：

| 告警类型 | 修复方案 | 涉及命令 | 风险等级 | 审批 |
|---------|---------|---------|---------|------|
| PORT_DOWN | no shutdown | interface + no shutdown | LOW | 自动执行 |
| CPU_HIGH | CPU 限速 | rate-limit 策略 | MEDIUM | 自动执行 |
| **MAC_FLAPPING** | 端口安全 | **switchport port-security** | **HIGH** | **需审批** |

> **RiskAssessor 判定逻辑**：扫描 `fix_plan.commands` 列表中的命令，匹配高危关键词模式（正则）：
> - 匹配到 `VLAN` + `switchport` → HIGH
> - 匹配到 `port-security` → HIGH
> - 匹配到 `reload` / `erase` → CRITICAL
> - 匹配到 `no shutdown` / `rate-limit` → LOW/MEDIUM
>
> 若匹配到 HIGH 或 CRITICAL，`need_human_approval=true`，LangGraph 在 `human_approval` 节点前 `interrupt_before` 挂起。

### 4.3 批准 / 拒绝操作

1. 在待审批列表中，点击任意待审批行
2. 进入**审批详情页**

![审批详情](screenshots/08_approval_detail.png)

**详情页展示**：

- 告警完整内容（原始 MAC_FLAPPING 描述）
- 诊断结果摘要
- 根因分析结论
- 修复方案详情（含完整 CLI 命令列表）
- 风险原因列表（RiskAssessor 匹配到的高危模式）

**操作步骤**：

1. 审阅修复方案
2. 在决策区域：
   - 点击 **"批准执行"**（绿色按钮）→ 弹出二次确认框 → 输入备注（可选，如"方案合理，允许执行"）→ 确认
   - 或点击 **"拒绝"**（红色按钮）→ 弹出二次确认框 → 输入拒绝原因（必填，如"涉及核心交换机，人工处理更安全"）
3. 提交审批决定

![审批决定](screenshots/08b_approval_decision.png)

**系统响应**：

- 前端显示操作结果提示
- 如果批准：待审批列表自动刷新，该项消失，进入"审批历史"
- 如果拒绝：同样消失，进入"审批历史"标记为 REJECTED

> **批准后的内部流程**：
> 1. `POST /api/approvals/{checkpoint_id}/decide {"decision": "APPROVED", "operator": "admin"}`
> 2. `ApprovalRepository.update_approval_decision()` 更新 SQLite `approvals` 表（decision=APPROVED, decided_at=now）
> 3. `StateGraphEngine.resume_workflow(checkpoint_id, approval_status="APPROVED")` 恢复 LangGraph
> 4. LangGraph 从 `human_approval` 节点恢复，节点收到 `approval_status=APPROVED`
> 5. 条件边 CE-002 在 resume 后继续执行 → `backup_config` → `execute_fix` → `verify_result` → `final_report`
> 6. 审计日志记录审批决策事件（AuditEventType.APPROVAL_DECISION）

> **拒绝后的内部流程**：
> 1. 同批准步骤 1-2，但 decision=REJECTED
> 2. `resume_workflow(approval_status="REJECTED")`
> 3. `human_approval` 节点检测到 REJECTED → 设置 `approval_status=REJECTED`
> 4. 条件边 CE-002 在 REJECTED 后路由到 → 跳过 T11-T13 → T14 `final_report` (status=REJECTED)

### 4.4 理解 Interrupt 挂起 → 恢复的机制

```
LangGraph Interrupt 生命周期（以 MAC_FLAPPING 为例）

  ┌─────────────────────────────────────────────────────────────┐
  │                     LangGraph StateGraph                     │
  │                                                             │
  │  ... → assess_risk → ┌─────────────────┐                    │
  │                      │ CE-002: need_    │                    │
  │                      │ human_approval?  │                    │
  │                      └───┬─────────┬───┘                    │
  │                          │ true    │ false                  │
  │                          ▼         ▼                        │
  │              ╔═══════════════╗  backup_config               │
  │              ║ human_approval║      │                       │
  │              ║               ║      ▼                       │
  │              ║  interrupt_   ║  execute_fix → ...           │
  │              ║  before       ║                              │
  │              ╚═══════╤═══════╝                              │
  │                      │                                      │
  │              ┌───────┴───────┐                               │
  │              │ StateGraph    │                               │
  │              │ 被挂起 (pause)│                               │
  │              │ Checkpoint    │                               │
  │              │ 已保存        │                               │
  │              └───────────────┘                               │
  └─────────────────────┬───────────────────────────────────────┘
                        │
                        │  等待外部信号...
                        │
  ┌─────────────────────┴───────────────────────────────────────┐
  │              外部世界 (Web UI / API)                         │
  │                                                             │
  │  GET /api/approvals/pending                                 │
  │  → 发现 checkpoint_id = "ALT-...-x1y2z3w4"                  │
  │  → 展示审批详情给用户                                        │
  │                                                             │
  │  用户做出审批决定:                                            │
  │  POST /api/approvals/{checkpoint_id}/decide                  │
  │  → {"decision": "APPROVED", "operator": "admin"}             │
  │  → StateGraphEngine.resume_workflow(checkpoint_id)           │
  └─────────────────────┬───────────────────────────────────────┘
                        │
                        │  resume 信号
                        ▼
  ┌─────────────────────────────────────────────────────────────┐
  │                  LangGraph StateGraph (resume)               │
  │                                                             │
  │  ╔═══════════════╗                                          │
  │  ║ human_approval║ ── 恢复执行 ──→ approval_status          │
  │  ║ (恢复执行)     ║                = APPROVED               │
  │  ╚═══════╤═══════╝                                          │
  │          │                                                  │
  │          ▼                                                  │
  │  backup_config → execute_fix → verify_result → final_report │
  │                                                             │
  │  最终 status = CLOSED（审批通过） 或 REJECTED（审批拒绝）      │
  └─────────────────────────────────────────────────────────────┘
```

> **关键概念**：
> - `interrupt_before=["human_approval"]` — LangGraph 在进入 `human_approval` 节点**之前**挂起，这意味着节点尚未执行，State 中尚没有 `approval_status` 字段
> - `resume_workflow(checkpoint_id, extra_state)` — 恢复时将审批结果（APPROVED/REJECTED）作为额外 State 注入，`human_approval` 节点从 State 中读取 `approval_status` 来决定后续行为
> - **Checkpoint** — LangGraph MemorySaver 在每次节点执行后自动保存 State 快照（checkpoint），Interrupt 挂起时的 checkpoint 包含了前 9 个节点的完整 State。恢复时从该 checkpoint 继续，无需重新执行前序节点。

### 4.5 查看审批历史

1. 点击左侧 **"审批管理"** > **"审批历史"**
2. 进入历史列表，展示所有已处理的审批记录

![审批历史](screenshots/09_approval_history.png)

**筛选项**：按决策结果（APPROVED / REJECTED）、时间范围筛选。每行显示审批决策时间、操作人和备注。

---

## 5. 设备管理

### 5.1 查看纳管设备列表

1. 点击左侧导航栏 **"设备管理"**
2. 进入设备列表页

![设备列表](screenshots/10_device_list.png)

**表格列说明**：

| 列名 | 示例值 | 说明 |
|------|--------|------|
| 设备名称 | `Core-SW-01` | 唯一标识 |
| IP 地址 | `192.168.1.1` | 管理 IP |
| 型号 | `TP-Link T2600G-28TS` | 设备型号 |
| 状态 | `ONLINE` / `OFFLINE` / `UNKNOWN` | 当前连接状态 |
| 最近诊断 | `2026-07-11 14:30` | 最近一次诊断时间 |
| 纳管时间 | `2026-07-10 09:00` | 设备入网时间 |

> **默认设备**：系统首次启动时，若 SQLite `devices` 表为空，自动插入 2 台种子设备：
> - Core-SW-01（192.168.1.1）
> - Access-SW-02（192.168.1.2）
>
> 巡检调度器在每次巡检时，从 SQLite `devices` 表动态加载设备列表（替代旧版硬编码）。

### 5.2 设备 CRUD 操作

**新增设备**：

1. 点击 **"新增设备"** 按钮
2. 弹出 **el-dialog** 表单
3. 填写：设备名称、IP 地址、型号（可选）、分组（可选）
4. 点击"保存"

![新增设备](screenshots/10b_add_device.png)

**编辑设备**：

1. 在列表中点击某行的"编辑"按钮
2. 修改设备信息
3. 保存

**删除设备**：

1. 点击某行的"删除"按钮
2. 系统检查是否有进行中的告警关联该设备
   - 若有 → 提示无法删除，先处理进行中告警
   - 若无 → 二次确认后删除

### 5.3 设备凭据配置

1. 在设备列表中点击某行的 **"凭据配置"** 按钮
2. 弹出凭据配置弹窗

![凭据配置](screenshots/10c_credentials.png)

**配置项**：

| 字段 | 说明 | 安全措施 |
|------|------|---------|
| SSH 用户名 | 默认 `admin` | 明文存储 |
| SSH 密码 | 交换机登录密码 | **AES-128-CBC + HMAC-SHA256 加密存储**（cryptography.fernet），UI 掩码显示 `****` |
| SSH 端口 | 默认 `22` | 明文存储 |
| Enable 密码 | 特权模式密码（可选） | AES 加密存储，UI 掩码显示 |

> **密码安全**：
> - 所有密码在存储前通过 `EncryptionService.encrypt()` 加密为 Fernet token
> - API 响应中密码字段永远返回 `"****"` 掩码（不返回密文，防止离线暴力破解）
> - UI 输入框使用 Element Plus `show-password` 属性，提供眼睛图标切换显示/隐藏

### 5.4 查看设备诊断记录

1. 在设备列表中点击某行的 **"诊断记录"** 按钮
2. 查看该设备的历史诊断命令和输出结果

---

## 6. 巡检管理

### 6.1 查看巡检配置

1. 点击左侧导航栏 **"巡检配置"**
2. 进入巡检配置页

![巡检配置](screenshots/11_inspection_config.png)

**配置项**：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| 巡检间隔 | `5` 分钟 | 定时巡检的执行周期 |
| 诊断超时 | `30` 秒 | 单条诊断命令的超时时间 |
| 重试上限 | `3` 次 | 命令失败后重试次数 |
| 当前状态 | 运行中 / 已停止 | APScheduler 运行状态 |

**修改配置**：

1. 修改间隔数值（例如改为 `10` 分钟）
2. 点击"保存"
3. 后端调用 `InspectionScheduler.reschedule()` 热更新定时器，无需重启服务

> **内部机制**：巡检配置存储在 SQLite `system_config` 表中（config_key=`inspection.interval_minutes`）。配置修改后，APScheduler 移除旧 job 并添加新 job。

### 6.2 手动触发巡检

1. 在巡检配置页，点击 **"手动触发巡检"** 按钮
2. 系统立即执行一轮全设备诊断

![手动触发巡检](screenshots/11b_manual_inspection.png)

**执行流程**：

1. 后端 `POST /api/inspection/trigger` 被调用
2. `InspectionScheduler.run_inspection_once()` 立即执行（不等定时器）
3. 对 SQLite `devices` 表中每台设备：
   - 执行诊断命令
   - 检查是否有异常（端口 down、CPU 高、MAC 漂移）
   - 发现异常 → 生成 `Alert` 对象（source=INSPECTION）→ 进入 LangGraph 工作流
4. 巡检结果写入 `inspection_records` 表
5. 前端轮询得到完成状态，显示 `巡检完成，发现 N 个异常`

### 6.3 查看巡检历史记录

1. 点击左侧 **"巡检配置"** > **"巡检历史"**
2. 进入历史列表

![巡检历史](screenshots/12_inspection_history.png)

**表格列说明**：

| 列名 | 示例值 | 说明 |
|------|--------|------|
| 触发方式 | `SCHEDULED` / `MANUAL` | 定时触发或手动触发 |
| 开始时间 | `2026-07-11 14:30:00` | 巡检开始时间 |
| 完成时间 | `2026-07-11 14:30:15` | 巡检完成时间 |
| 检查设备数 | `2` | 本轮巡检的设备总数 |
| 发现异常数 | `2` | 产生告警的设备数 |
| 详情 | 可展开 | 每台设备的诊断结果和告警信息 |

---

## 7. 知识库管理

### 7.1 查看知识文档列表

1. 点击左侧导航栏 **"知识库管理"** > **"知识文档"**
2. 进入文档管理页

![知识文档](screenshots/13_knowledge_documents.png)

**表格列说明**：

| 列名 | 示例值 | 说明 |
|------|--------|------|
| 标题 | `端口Down故障处理案例` | 文档标题 |
| 告警类型 | `PORT_DOWN` | 关联的告警类型 |
| 创建时间 | `2026-07-10 09:00` | 创建时间 |
| 最后更新 | `2026-07-10 09:00` | 最后修改时间 |

**文档 CRUD**：

1. 点击"新增文档" → 弹出 **el-dialog**（含 Markdown 编辑器）→ 填写标题、选择告警类型、撰写 Markdown 内容
2. 保存后，RAGService 自动将新文档向量化（embedding）写入 Chroma 索引
3. 编辑/删除操作同理，RAGService 同步更新 Chroma 索引

> **知识文档用途**：当 `analyze_root_cause` 节点执行时，RAGService.search() 从 Chroma 向量库中检索与当前诊断结果语义相似的故障案例和预案，返回作为 LLM 根因分析的参考上下文（knowledge_refs）。

### 7.2 知识检索测试

1. 点击左侧 **"知识库管理"** > **"检索测试"**
2. 进入检索测试页面

![检索测试](screenshots/14_retrieval_test.png)

**操作步骤**：

1. 在查询文本框输入故障描述，例如：`交换机接口反复 up/down，日志显示 link flap`
2. 选择告警类型过滤：`PORT_DOWN`（可选，不选则全库检索）
3. 设置 Top-K：`5`（返回前 5 个匹配结果）
4. 点击 **"测试检索"**

**结果展示**：

| 结果列 | 说明 |
|--------|------|
| 文档标题 | 匹配的知识文档标题 |
| 相似度 | 语义相似度分数（0.0-1.0），以 el-progress 进度条可视化 |
| 内容摘要 | 匹配文档的前 200 字符摘要 |
| 关联模板 | 文档关联的命令模板 ID（如有） |

> **后端流程**：`POST /api/knowledge/test-retrieval` → `RAGService.search(query, alert_type, top_k)` → Chroma 向量相似度搜索 → 返回 Top-K 结果（含 similarity score）。

### 7.3 命令模板查看

1. 点击左侧 **"知识库管理"** > **"命令模板"**
2. 进入模板管理页

![命令模板](screenshots/15_command_templates.png)

**预置模板清单**：

| 模板 ID | 名称 | 适用告警类型 | 命令数 | 风险 |
|---------|------|-------------|--------|------|
| TPL-PORT-ENABLE | 端口启用 | PORT_DOWN | 5 | LOW |
| TPL-PORT-DISABLE | 端口关闭 | PORT_DOWN | 4 | LOW |
| TPL-MAC-PORT-SECURITY | MAC 端口安全 | MAC_FLAPPING | 6 | **HIGH** |
| TPL-MAC-CLEAR | MAC 地址清理 | MAC_FLAPPING | 3 | MEDIUM |
| TPL-CPU-RATE-LIMIT | CPU 限速 | CPU_HIGH | 4 | MEDIUM |
| TPL-CPU-PROCESS-RESTART | 进程重启 | CPU_HIGH | 3 | HIGH |

**模板内容格式**（YAML + Jinja2）：

```yaml
template_id: TPL-PORT-ENABLE
description: "端口启用 — 对 down 状态的接口执行 no shutdown"
alert_type: PORT_DOWN
risk_level: LOW
params_schema:
  iface_name: string
risk_hints:
  - "接口状态变更"
jinja2_template: |
  configure terminal
  interface {{ iface_name }}
  no shutdown
  description Auto-recovered by NetworkAgent
  end
```

> **安全机制回顾**：LLM 不直接生成命令。LLM 仅填充 Jinja2 变量（如 `iface_name=Gi0/1`），通过 OutputValidator 校验后，由 TemplateEngine 做确定性命令拼装。这从根本上杜绝了 LLM 幻觉导致危险命令注入的风险。

---

## 8. 系统配置

### 8.1 全局配置查看

1. 点击左侧导航栏 **"系统配置"** > **"全局配置"**
2. 进入配置编辑页

![全局配置](screenshots/16_system_config.png)

**可配置项**：

| 配置键 | 默认值 | 说明 |
|--------|--------|------|
| `inspection.interval_minutes` | `5` | 巡检间隔（分钟） |
| `diagnosis.timeout_seconds` | `30` | 诊断命令超时（秒） |
| `diagnosis.retry_max` | `3` | 命令重试上限 |
| `rag.similarity_threshold` | `0.6` | RAG 相似度阈值 |
| `ui.polling_interval_seconds` | `3` | 前端轮询间隔（秒） |

**修改操作**：

1. 修改任意配置值
2. 点击"保存"
3. 后端热重载配置（巡检间隔 → APScheduler 重新调度；其他配置 → 对应模块读取新值）

### 8.2 LLM API Key 配置

在全局配置页的 **"LLM API Key"** Tab：

1. 输入 DeepSeek API Key（格式：`sk-xxxxxxxx`）
2. 点击"保存"
3. 系统通过 `EncryptionService.encrypt()` 加密后存入 `system_config` 表
4. 点击 **"测试连接"** → 发起一次轻量级 DeepSeek API 调用验证连通性

![API Key配置](screenshots/16b_api_key.png)

> **安全设计**：
> - API Key 以 AES-128-CBC（Fernet）加密存储，绝不存明文
> - UI 上以 `sk-a****f456` 格式掩码显示（`mask_sensitive()` 函数）
> - 加密密钥来源优先级：环境变量 `ENCRYPTION_KEY` > 本地文件 `./data/.encryption_key` > 首次启动自动生成

### 8.3 日志查看

1. 点击左侧 **"系统配置"** > **"系统日志"**
2. 进入日志查看页

![系统日志](screenshots/17_system_logs.png)

**功能**：

| 功能 | 说明 |
|------|------|
| 日志源切换 | `operations`（操作日志）或 `audit`（审计日志） |
| 级别筛选 | INFO / WARNING / ERROR |
| 关键词搜索 | 对 `message` 字段做子串匹配（不区分大小写） |
| 时间范围 | 按日期范围过滤日志 |
| 分页 | 从文件尾部倒序读取，单次最多 500 条 |

> **后端实现**：`LogReaderService.read_logs()` 从文件系统读取 `./logs/operations_{date}.log` 和 `./logs/audit.log`，支持反向读取以优化大文件性能。

---

## 9. 端到端演示脚本

以下是一份完整的现场演示脚本，覆盖"从登录到修复闭环"的全流程，预计耗时 **8-10 分钟**。

---

### 场景设定

你正在向运维团队演示 NetworkAgentDemo：展示系统如何自动发现故障、智能诊断、生成修复方案、在必要时请求人工审批，最终完成修复闭环。

---

### 第 1 步：登录（30 秒）

```
操作：打开 http://47.109.197.217:8001/
     → 输入 admin / admin
     → 点击"登录"
展示点：JWT 认证、bcrypt 密码哈希、24小时过期
```

### 第 2 步：Dashboard 概览（1 分钟）

```
操作：登录后自动进入 Dashboard
展示点：
  - "告警总数"卡片 — 由于巡检已在后台运行，应该有数字 > 0
  - 饼图 — 告警类型分布（PORT_DOWN 和 CPU_HIGH 应占多数）
  - 健康面板 — 4 个组件全绿（healthy）
讲解：
  "系统后台每5分钟自动巡检 Core-SW-01 和 Access-SW-02，
   Mock 数据中包含异常，所以巡检会持续产生告警。
   你现在看到的就是系统自动发现并处理的告警统计。"
```

### 第 3 步：查看告警列表（1 分钟）

```
操作：点击左侧"告警管理"
展示点：
  - 表格展示所有告警，来源有 INSPECTION（巡检触发）
  - 大部分 status=CLOSED（已自动修复）
  - 使用筛选器切换 alert_type
讲解：
  "每个告警都经过了 14 个节点的 LangGraph 状态机处理。
   对于 PORT_DOWN 和 CPU_HIGH，系统全自动执行修复，
   从诊断到命令下发，无需人工干预。"
```

### 第 4 步：模拟高风险告警 — MAC_FLAPPING（1 分钟）

```
操作：点击"模拟告警"子菜单
     → 告警类型选择 MAC_FLAPPING
     → 设备选择 Core-SW-01
     → 接口输入 Gi0/1
     → 点击"发送模拟告警"
展示点：
  - 成功提示，显示 alert_id
  - 返回告警列表，新告警出现在第一条，status=PROCESSING
讲解：
  "MAC 地址漂移是高风险告警类型。
   修复方案涉及 switchport port-security 配置，
   系统会自动挂起等待审批，不会盲目执行。"
```

### 第 5 步：查看告警详情 — 观察状态机流转（1.5 分钟）

```
操作：点击刚创建的 MAC_FLAPPING 告警
     → 进入详情页
     → 切换到"处理时间线" Tab
展示点：
  - 时间线展示 1-9 号节点已全部完成（绿色）
  - 第 10 号节点 human_approval 高亮蓝色，标记"等待人工审批..."
  - 点击任意已完成节点（如 analyze_root_cause）查看 State 快照
讲解：
  "这是 LangGraph 14 节点状态机的实时视图。
   前 9 个节点已经自动完成：接收告警 → 解析 → 校验 → 获取设备信息 →
   SSH 连接 → 诊断采集 → LLM 根因分析 → 修复方案生成 → 风险评估。
   风险评估判定为 HIGH，所以第 10 个节点 human_approval 被 Interrupt 挂起。"
```

### 第 6 步：工作流拓扑图展示（1 分钟）

```
操作：点击左侧"工作流可视化"
展示点：
  - 全局 14 节点有向拓扑图，4 条条件边清晰可见
  - 当前有一条告警在处理中（如已选中），对应路径节点高亮
讲解：
  "这是完整的 LangGraph StateGraph 拓扑。
   4 条条件边的决策逻辑：
   CE-001：告警过期/无效 → 直接结束
   CE-002：低中风险 → 自动执行；高风险 → 挂起审批
   CE-003：备份失败 → 阻止修复，安全底线
   CE-004：验证失败 → 自动回滚"
```

### 第 7 步：人工审批（1.5 分钟）

```
操作：点击左侧"审批管理" → "待审批"
     → 应该看到刚才模拟的 MAC_FLAPPING 审批项
     → 点击进入审批详情
展示点：
  - 告警完整内容、诊断结果、根因分析
  - 修复方案完整 CLI 命令列表（6 条 port-security 命令）
  - 风险等级 HIGH，风险原因列表
操作：点击"批准执行"
     → 输入备注"方案合理，允许执行"
     → 确认
展示点：
  - 成功提示
  - 待审批列表变为空
讲解：
  "审批通过后，LangGraph 从 Interrupt 挂起点恢复。
   系统将继续执行：备份配置 → 下发命令 → 验证修复 → 生成报告。"
```

### 第 8 步：验证修复闭环（1 分钟）

```
操作：返回告警列表 → 刷新 → 找到 MAC_FLAPPING 告警
     → 查看状态已变为 CLOSED
     → 点击进入详情 → "处理时间线" Tab
展示点：
  - 14 个节点全部标记为绿色（已完成）
  - 第 11-14 号节点（backup_config, execute_fix, verify_result, final_report）已执行
  - 展开 final_report 节点查看 LLM 生成的 Markdown 报告
讲解：
  "从告警触达到修复闭环，整个过程在 1 分钟内完成。
   所有操作有审计日志，配置变更前有自动备份，
   验证失败会自动回滚 — 安全底线全覆盖。"
```

### 第 9 步：总结（30 秒）

```
快速回顾展示过的功能模块：
  - 设备管理（2 台纳管设备，支持 CRUD + 凭据配置）
  - 巡检管理（5 分钟定时巡检 + 手动触发 + 历史记录）
  - 知识库（6 个命令模板 + 故障案例文档 + RAG 检索）
  - 系统配置（全局参数 + 日志查看）
讲解：
  "NetworkAgentDemo 基于 LangGraph 构建了 14 节点智能运维状态机，
   实现了从告警发现到修复闭环的全自动化流程。
   高危操作保留人工审批节点，确保安全与效率的平衡。"
```

---

### 演示时间线总览

| 步骤 | 内容 | 耗时 | 累计 |
|------|------|------|------|
| 1 | 登录 | 30s | 0:30 |
| 2 | Dashboard 概览 | 1min | 1:30 |
| 3 | 告警列表 | 1min | 2:30 |
| 4 | 模拟 MAC_FLAPPING 告警 | 1min | 3:30 |
| 5 | 告警详情 + 状态机时间线 | 1.5min | 5:00 |
| 6 | 工作流拓扑图 | 1min | 6:00 |
| 7 | 人工审批 | 1.5min | 7:30 |
| 8 | 修复闭环验证 | 1min | 8:30 |
| 9 | 总结 | 30s | 9:00 |

---

## 附 A. 常见问题

**Q: 为什么 Dashboard 页面的"待审批数"始终为 0？**

A: 只有 MAC_FLAPPING 类型告警才会触发审批。巡检自动产生的 PORT_DOWN 和 CPU_HIGH 告警风险等级为 LOW/MEDIUM，全自动执行，不进入审批。你需要通过"模拟告警"页面手动发送一条 MAC_FLAPPING 告警来触发审批流程。

**Q: 告警处理非常快（几秒以内），来不及看到状态变化怎么办？**

A: Mock 模式下所有工具调用（SSH、诊断、命令下发）均为模拟返回，耗时极短。你可以通过以下方式观察：
- 在告警详情页的"处理时间线"Tab 查看已完成节点的历史时间线
- 查看系统日志（"系统配置" > "系统日志"）中的 `Node START/END` 日志
- 在"工作流可视化"页面查看全局图

**Q: MAC_FLAPPING 模拟告警发送后，审批列表为空？**

A: 检查两点：
1. 告警是否仍在处理中（status=PROCESSING）？LangGraph 需要 2-3 秒执行前 9 个节点才能到达 `human_approval` 节点
2. RiskAssessor 是否正确匹配了高危模式？查看系统日志确认 `risk_level=HIGH` 和 `need_human_approval=True`

**Q: 页面数据没有实时更新？**

A: 前端采用 3 秒轮询机制（可配置）。等待一个轮询周期（3 秒）后数据会自动刷新。你也可手动刷新浏览器页面。

**Q: 如何修改 admin 密码？**

A: 当前 v0.2.0 版本为 Demo，暂未提供 Web UI 修改密码功能。你可以通过直接操作 SQLite `users` 表或设置 `ADMIN_PASSWORD` 环境变量在系统启动时初始化新密码。
