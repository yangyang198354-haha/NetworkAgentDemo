<file_header>
  <author_agent>sub_agent_software_developer</author_agent>
  <timestamp>2026-07-10T00:30:00Z</timestamp>
  <project_name>NetworkAgentDemo</project_name>
  <version>0.1.0</version>
  <input_files>
    <file>architecture/module_design.md</file>
    <file>architecture/architecture_design.md</file>
    <file>architecture/tech_stack.md</file>
  </input_files>
  <phase>PHASE_05</phase>
  <status>DRAFT</status>
</file_header>

# 实现计划 — NetworkAgentDemo

---

## 实现概览

- **总模块数**: 16 个（MOD-001 ~ MOD-016）
- **总代码文件数**: 22 个（含 models、main.py、__init__.py）
- **策略模式抽象层**: 3 个 ABC + 3 个 MockImpl + 3 个 TpLinkImpl（预留）
- **LangGraph 节点**: 14 个 + 4 条件边
- **模板文件**: 6 个 Jinja2 模板（3 种告警类型 x 2 模板/每种）
- **知识库文档**: ~10 条 Mock 知识条目
- **实现顺序**: 拓扑排序，从底层无依赖模块开始，逐层向上

---

## 模块依赖图与拓扑排序

### 依赖图分析

```
层0（无依赖 — 10个模块）:
  MOD-004 (AlertNormalizer)
  MOD-006 (LLMService)
  MOD-007 (TemplateEngine)
  MOD-008 (RAGService)
  MOD-010 (SwitchConfigTool)
  MOD-011 (SwitchDiagTool)
  MOD-012 (BackupTool)
  MOD-014 (RiskAssessor)
  MOD-015 (AuditLogger)
  MOD-016 (ConfigManager)

层1（依赖层0 — 2个模块）:
  MOD-009 (OutputValidator)  → MOD-015
  MOD-013 (KnowledgeBaseTool) → MOD-008

层2（依赖层0+1 — 1个模块）:
  MOD-005 (NodeHandlers) → MOD-006,007,008,009,010,011,012,013,014,015

层3（依赖层0 — 2个模块）:
  MOD-001 (WebhookReceiver) → MOD-004
  MOD-002 (InspectionScheduler) → MOD-004, MOD-011, MOD-016

层4（依赖层2 — 1个模块）:
  MOD-003 (StateGraphEngine) → MOD-005
```

### 拓扑排序结果（实现顺序）

先决条件：数据模型层（Pydantic models）必须在所有模块之前实现。

| 序号 | MOD-ID | 模块名 | 文件路径 | 依赖前置模块 | 复杂度 |
|------|--------|--------|---------|------------|--------|
| 0 | — | 数据模型 | `src/models/` | — | M |
| 1 | MOD-016 | ConfigManager | `src/security/config_manager.py` | — | L |
| 2 | MOD-015 | AuditLogger | `src/security/audit_logger.py` | — | L |
| 3 | MOD-014 | RiskAssessor | `src/security/risk_assessor.py` | — | M |
| 4 | MOD-004 | AlertNormalizer | `src/orchestration/alert_normalizer.py` | — | M |
| 5 | MOD-006 | LLMService | `src/llm/llm_service.py` | — | M |
| 6 | MOD-007 | TemplateEngine | `src/llm/template_engine.py` | — | M |
| 7 | MOD-008 | RAGService | `src/llm/rag_service.py` | — | M |
| 8 | MOD-010 | SwitchConfigTool | `src/tools/switch_config_tool.py` | — | L |
| 9 | MOD-011 | SwitchDiagTool | `src/tools/switch_diag_tool.py` | — | M |
| 10 | MOD-012 | BackupTool | `src/tools/backup_tool.py` | — | L |
| 11 | MOD-009 | OutputValidator | `src/llm/output_validator.py` | MOD-015 | M |
| 12 | MOD-013 | KnowledgeBaseTool | `src/tools/knowledge_base_tool.py` | MOD-008 | L |
| 13 | MOD-005 | NodeHandlers | `src/orchestration/node_handlers.py` | MOD-006~015 | H |
| 14 | MOD-001 | WebhookReceiver | `src/trigger/webhook_receiver.py` | MOD-004 | M |
| 15 | MOD-002 | InspectionScheduler | `src/trigger/inspection_scheduler.py` | MOD-004, 011, 016 | M |
| 16 | MOD-003 | StateGraphEngine | `src/orchestration/state_graph_engine.py` | MOD-005 | H |
| — | — | 应用入口 + 配置 | `src/main.py` | MOD-001,002,003,016 | M |
| — | — | 模板文件 | `resources/templates/` | MOD-007 | L |
| — | — | 知识库种子数据 | `resources/knowledge/` | MOD-008 | L |
| — | — | 配置文件 | `config/config.yaml` | MOD-016 | L |

---

## 各模块实现要点

### 0. 数据模型层（`src/models/`）

**文件清单**:
- `enums.py` — AlertType, AlertSeverity, AlertSource, WorkflowStatus, RiskLevel, ApprovalStatus, AuditEventType, DocType
- `alert.py` — AlertPayload, AlertReceipt, Alert, DeviceInfo, DeviceAuth, RawAlertEvent, RawInspectionEvent
- `state.py` — NetworkAgentState (TypedDict), PendingApproval, ApprovalDecision
- `fix_plan.py` — FixPlan, RootCauseResult, TemplateParams, TemplateMeta, TemplateDefinition, ConfigResult, DiagResult, BackupResult, RollbackResult, ExecRecord, VerifyResult, KnowledgeRef, KnowledgeDocument, KnowledgeBaseResult, RiskAssessment

**关键要点**:
- 使用 Pydantic BaseModel 定义所有数据类
- NetworkAgentState 使用 TypedDict (LangGraph compatibility)
- 所有枚举使用 Python Enum
- AlertPayload 严格遵循 IFC-001 Schema

---

### 1. MOD-016: ConfigManager

**接口实现**: IFC-016-01 (get), IFC-016-02 (set), IFC-016-03 (load_config), IFC-016-04 (get_device_credentials)

**关键要点**:
- `get(key)` 支持点号分隔的嵌套键（如 `"inspection.interval_minutes"`）
- 从 `config/config.yaml` 加载默认配置
- DeviceAuth 从配置文件 + 环境变量组合读取
- 线程安全的配置读写（使用 threading.Lock）

---

### 2. MOD-015: AuditLogger

**接口实现**: IFC-015-01 (log_node_execution), IFC-015-02 (log_audit_event), IFC-015-03 (query_by_alert_id), IFC-015-04 (get_pending_approvals)

**关键要点**:
- 使用 loguru 结构化日志
- 操作日志写入 `logs/operations_{date}.log`
- 审计日志追加写入 `logs/audit.log`（不可覆盖）
- 内存中维护 pending_approvals 列表（供 get_pending_approvals 查询）
- 日志格式: `{timestamp} | {alert_id} | {node_name} | {phase} | {state_summary_json} | duration={duration_ms}ms`

---

### 3. MOD-014: RiskAssessor

**接口实现**: IFC-014-01 (assess)

**关键要点**:
- 纯规则匹配引擎，无外部依赖
- 高风险模式匹配表: shutdown → HIGH, vlan delete → CRITICAL, reload → CRITICAL, router config → HIGH, spanning-tree → MEDIUM
- `need_human_approval` 判定: risk_level 为 HIGH/CRITICAL → true; MEDIUM + 多条修改命令 → true
- 正则匹配模板来自 module_design.md MOD-014 定义

---

### 4. MOD-004: AlertNormalizer

**接口实现**: IFC-004-01 (normalize_webhook_event), IFC-004-02 (normalize_inspection_event), IFC-004-03 (is_duplicate)

**关键要点**:
- 使用 `cachetools.TTLCache` 实现去重缓存（maxsize=100, ttl=900s）
- normalize_webhook_event: 将 AlertPayload 映射为标准 Alert
- normalize_inspection_event: 将 RawInspectionEvent 映射为标准 Alert（source=INSPECTION）
- 去重键: `alert_type + device_name` 组合
- 过期检查: alert_timestamp 超过 TTL（默认15分钟）标记为过期

---

### 5. MOD-006: LLMService

**接口实现**: IFC-006-01 (analyze_root_cause), IFC-006-02 (fill_template_params), IFC-006-03 (generate_report)

**关键要点**:
- SDK 初始化: `openai.OpenAI(base_url="https://api.deepseek.com/v1", api_key=os.environ["DEEPSEEK_API_KEY"])`
- model="deepseek-chat", temperature=0.1
- 失败重试: 最多3次，指数退避（1s, 2s, 4s）
- 每次调用记录: 时间戳、endpoint、输入长度、输出长度、耗时
- fill_template_params 的 Prompt 要求输出纯 JSON
- analyze_root_cause 的 Prompt 要求输出 Markdown 结构化

---

### 6. MOD-007: TemplateEngine

**接口实现**: IFC-007-01 (render), IFC-007-02 (list_templates), IFC-007-03 (get_template)

**关键要点**:
- 使用 `jinja2.SandboxedEnvironment`（安全约束）
- 模板从 `resources/templates/` 目录加载（YAML 文件）
- render(): 将 params 字典渲染为 CLI 命令列表
- 典型模板: `interface {{ iface_name }}\n no shutdown\n description {{ desc }}`
- 模板参数 Schema: 定义每个模板期望的参数名和类型

---

### 7. MOD-008: RAGService

**接口实现**: IFC-008-01 (search), IFC-008-02 (index_documents), IFC-008-03 (get_template_by_id)

**关键要点**:
- Chroma 持久化路径: `./data/chroma_db/`
- 集合名称: `network_knowledge`
- 嵌入模型: `text-embedding-3-small` via openai SDK（降级: sentence-transformers all-MiniLM-L6-v2）
- search(): 语义搜索 + 元数据过滤（where={"alert_type": alert_type}）+ 相似度阈值 ≥ 0.6
- index_documents(): 从 `resources/knowledge/` 加载种子数据，批量写入 Chroma
- 种子数据: ~10条文档，覆盖 MAC_FLAPPING、PORT_DOWN、CPU_HIGH 三种告警类型

---

### 8. MOD-010: SwitchConfigTool

**接口实现**: IFC-010-01 (configure)

**关键要点**:
- 抽象基类: `AbstractSwitchConfigTool(BaseTool)`，声明 `_run(device_ip, commands, auth) -> ConfigResult`
- Mock 实现: `MockSwitchConfigTool`，所有命令返回 success=true，模拟延迟 0.5s/条
- TP-Link 实现（预留）: `TpLinkSwitchConfigTool`，继承 ABC，_run() 标记 `raise NotImplementedError("TP-Link SSH not implemented in Demo")`
- 策略工厂: `create_switch_config_tool(use_mock: bool = True) -> AbstractSwitchConfigTool`

---

### 9. MOD-011: SwitchDiagTool

**接口实现**: IFC-011-01 (diagnose)

**关键要点**:
- 抽象基类: `AbstractSwitchDiagTool(BaseTool)`，声明 `_run(device_ip, command, auth) -> DiagResult`
- Mock 实现: `MockSwitchDiagTool`，根据命令返回逼真模拟诊断数据：

  **MAC_FLAPPING + `show mac address-table`**:
  ```
  Mac Address Table
  Vlan    Mac Address       Type        Ports
  ----    -----------       --------    -----
     1    00:1A:2B:3C:4D:5E DYNAMIC     Gi0/1
     1    00:1A:2B:3C:4D:5E DYNAMIC     Gi0/2  ← MAC漂移! 同一MAC出现在不同端口
     1    00:2F:3A:4B:5C:6D DYNAMIC     Gi0/3
  ```

  **PORT_DOWN + `show interface Gi0/1`**:
  ```
  GigabitEthernet0/1 is down, line protocol is down (notconnect)
    Hardware is Gigabit Ethernet, address is 00:1A:2B:3C:4D:5E
    MTU 1500 bytes, BW 1000000 Kbit/sec
    Last input never, output never, output hang never
    Input errors: 0, CRC: 0, Frame: 0, Overrun: 0
  ```

  **CPU_HIGH + `show processes cpu`**:
  ```
  CPU utilization for five seconds: 92%/5%; one minute: 88%; five minutes: 75%
  PID Runtime(ms)   Invoked  uSecs  5Sec  1Min  5Min TTY Process
    1           0         1      0  0.00% 0.00% 0.00%   0 Chunk Manager
   47      452389   1234567    366 45.23% 42.18% 38.76%   0 IP Input
   89      234567    987654    237 23.45% 20.11% 18.92%   0 SNMP ENGINE
  ```

---

### 10. MOD-012: BackupTool

**接口实现**: IFC-012-01 (backup), IFC-012-02 (rollback)

**关键要点**:
- 抽象基类: `AbstractBackupTool(BaseTool)`，声明 `_run(device_ip, auth, operation, backup_id=None) -> BackupResult`
- Mock 实现: `MockBackupTool`
  - backup(): 返回模拟 running-config 文本 + UUID
  - rollback(): 返回 success（模拟回滚成功）
- TP-Link 实现（预留）: `TpLinkBackupTool`，继承 ABC

---

### 11. MOD-009: OutputValidator

**接口实现**: IFC-009-01 (validate_params), IFC-009-02 (sanitize_root_cause)

**关键要点**:
- validate_params():
  - Step 1: 解析 JSON（try json.loads）
  - Step 2: JSON Schema 校验（每个 key/value type 必须匹配 template_params_schema）
  - Step 3: CLI 黑名单正则扫描（对每个 string 值）
  - Step 4: 通过则返回纯净参数字典
  - 安全告警记录到 MOD-015 AuditLogger
- CLI 命令黑名单正则: `(interface\s+\S+|shutdown|no\s+shutdown|switchport|vlan\s+\d+|reload|configure\s+terminal|router\s+\w+|spanning-tree|write\s+memory|copy\s+running)`
- sanitize_root_cause(): 追加安全标记，检测 CLI 命令片段（warn 但不拒绝）

---

### 12. MOD-013: KnowledgeBaseTool

**接口实现**: IFC-013-01 (search)

**关键要点**:
- 封装为 LangChain BaseTool
- 委托给 MOD-008 RAGService.search()
- 输入: query + alert_type + top_k
- 返回: KnowledgeBaseResult { matches: list[KnowledgeRef], count: int }

---

### 13. MOD-005: NodeHandlers

**接口实现**: IFC-005-01 ~ IFC-005-14（14个节点函数）

**关键要点**:
- 每个节点函数签名: `(state: NetworkAgentState) -> dict[str, Any]`
- 节点函数之间通过 state 传递数据
- 调用下层模块完成具体业务
- 关键节点实现要点:
  - `handle_collect_diag`: 根据 alert_type 选择命令（MAC_FLAPPING → show mac address-table 等）
  - `handle_analyze_root_cause`: 调用 LLMService + RAGService
  - `handle_generate_fix_plan`: LLM填参 → OutputValidator校验 → TemplateEngine拼装
  - `handle_assess_risk`: 调用 RiskAssessor
  - `handle_human_approval`: Interrupt挂起点，检查 approval_status
  - `handle_backup_config`: 调用 BackupTool
  - `handle_execute_fix`: 逐条执行前幂等检查
  - `handle_verify_result`: 重新诊断 + 对比

---

### 14. MOD-001: WebhookReceiver

**接口实现**: IFC-001-01 (POST /webhook/alert), IFC-001-02 (start_server)

**关键要点**:
- FastAPI POST 端点，接收 AlertPayload JSON
- 调用 MOD-004.normalize_webhook_event()
- 返回 AlertReceipt
- start_server() 启动 Uvicorn

---

### 15. MOD-002: InspectionScheduler

**接口实现**: IFC-002-01 (start_scheduler), IFC-002-02 (stop_scheduler), IFC-002-03 (run_inspection_once)

**关键要点**:
- APScheduler IntervalTrigger，默认间隔 5 分钟
- 巡检逻辑: 对每个设备执行诊断命令 → 检测异常 → 创建 RawInspectionEvent → 调用 MOD-004.normalize_inspection_event()
- 使用 FastAPI lifespan 管理启停

---

### 16. MOD-003: StateGraphEngine

**接口实现**: IFC-003-01 (build_graph), IFC-003-02 (run_workflow), IFC-003-03 (resume_workflow), IFC-003-04 (get_pending_approvals), IFC-003-05 (get_workflow_state)

**关键要点**:
- 同步 StateGraph（非 async）
- 14 节点 + 4 条件边 + interrupt_before=["human_approval"]
- MemorySaver 作为 checkpointer
- 节点定义:
  - receive_alert → parse_alert → validate_alert
  - CE-001: is_valid → get_device_info / final_report
  - get_device_info → establish_ssh → collect_diag → analyze_root_cause
  - generate_fix_plan → assess_risk
  - CE-002: need_human_approval → human_approval / backup_config
  - human_approval [INTERRUPT]
  - backup_config → CE-003: backup_success → execute_fix / final_report
  - execute_fix → verify_result
  - CE-004: verify_passed → final_report / execute_fix（回滚路径）
  - final_report

---

## 架构偏差记录

| 偏差ID | 偏差描述 | 原 ADR 决策 | 偏差原因 |
|--------|---------|------------|---------|
| — | 无架构偏差 | — | 所有实现严格遵循 architecture_design.md 的 ADR 决策和 module_design.md 的接口契约 |

---

## Mock 数据样本定义

### Mock SwitchDiagTool 诊断数据（3 种告警类型）

**MAC_FLAPPING（MAC 地址漂移）**:
- 诊断命令: `show mac address-table`
- 模拟输出: 包含同一 MAC 地址 00:1A:2B:3C:4D:5E 出现在 Gi0/1 和 Gi0/2 两个端口
- 诊断命令: `show logging`
- 模拟输出: 包含 MAC flapping 相关的 syslog 消息

**PORT_DOWN（端口 Down）**:
- 诊断命令: `show interface {iface}`
- 模拟输出: 接口状态为 down, line protocol down (notconnect)
- 诊断命令: `show interface status`
- 模拟输出: 所有接口状态列表，目标接口 marked as down

**CPU_HIGH（CPU 利用率过高）**:
- 诊断命令: `show processes cpu`
- 模拟输出: 5秒CPU利用率 92%，IP Input 进程消耗 45% CPU
- 诊断命令: `show processes cpu history`
- 模拟输出: CPU 历史趋势图

### Mock BackupTool 备份数据
- 模拟 running-config: 包含 200 行典型 TP-Link / Cisco IOS 风格配置
- backup_id: UUID v4 格式

---

## 文件清单汇总

```
src/
├── __init__.py
├── main.py                           # FastAPI 入口 + LangGraph 集成
├── models/
│   ├── __init__.py
│   ├── enums.py                      # 8 个枚举类型
│   ├── alert.py                      # 6 个数据类
│   ├── state.py                      # NetworkAgentState TypedDict
│   └── fix_plan.py                   # 12 个数据类
├── trigger/
│   ├── __init__.py
│   ├── webhook_receiver.py           # MOD-001
│   └── inspection_scheduler.py       # MOD-002
├── orchestration/
│   ├── __init__.py
│   ├── alert_normalizer.py           # MOD-004
│   ├── state_graph_engine.py         # MOD-003
│   └── node_handlers.py              # MOD-005
├── llm/
│   ├── __init__.py
│   ├── llm_service.py                # MOD-006
│   ├── template_engine.py            # MOD-007
│   ├── rag_service.py                # MOD-008
│   └── output_validator.py           # MOD-009
├── tools/
│   ├── __init__.py
│   ├── switch_config_tool.py          # MOD-010
│   ├── switch_diag_tool.py            # MOD-011
│   ├── backup_tool.py                 # MOD-012
│   └── knowledge_base_tool.py         # MOD-013
└── security/
    ├── __init__.py
    ├── risk_assessor.py               # MOD-014
    ├── audit_logger.py                # MOD-015
    └── config_manager.py              # MOD-016

resources/
├── templates/
│   ├── tpl_port_enable.yaml
│   ├── tpl_port_disable.yaml
│   ├── tpl_mac_port_security.yaml
│   ├── tpl_mac_clear.yaml
│   ├── tpl_cpu_rate_limit.yaml
│   └── tpl_cpu_process_restart.yaml
└── knowledge/
    └── seed_knowledge.json

config/
└── config.yaml

data/
└── chroma_db/

logs/
├── .gitkeep
├── operations_2026-07-10.log
└── audit.log
```
