<file_header>
  <author_agent>sub_agent_system_architect</author_agent>
  <timestamp>2026-07-10T00:00:00Z</timestamp>
  <project_name>NetworkAgentDemo</project_name>
  <version>0.1.0</version>
  <input_files>
    <file>requirements/project_brief.md</file>
    <file>requirements/requirements_spec.md</file>
    <file>requirements/user_stories.md</file>
  </input_files>
  <phase>PHASE_03</phase>
  <status>APPROVED</status>
</file_header>

# 架构设计文档 — NetworkAgentDemo

---

## 架构概览

### 架构风格：模块化分层单体（Modular Layered Monolith）

本 Demo 项目采用**模块化分层单体**架构风格，将系统按职责划分为 5 个逻辑层次（触发层 / 编排层 / LLM与知识层 / 工具层 / 安全与基础设施层），在各层内部按模块边界进一步拆分。选型依据：

- **Demo 范围适配**：项目明确为 Demo，不涉及生产级高可用部署（OOS-004），单体架构降低了部署和调试复杂度。
- **模块边界清晰**：虽然部署为单体，但各层之间的接口通过契约隔离，未来可按需将工具层/知识层拆分为独立服务。
- **LangGraph 原生适配**：LangGraph 的 StateGraph 在单进程内运行时性能最优，微服务化会增加跨进程状态同步的复杂度。
- **关键 REQ-NFUNC-012**（Linux 运行环境）：单体部署简洁，无额外中间件依赖。

### 系统分层视图

```
┌─────────────────────────────────────────────────────┐
│                     触发层 (Trigger Layer)            │
│  MOD-001: WebhookReceiver │ MOD-002: InspectionScheduler │
│           (FastAPI HTTP POST)    (APScheduler)            │
└───────────────────────┬─────────────────────────────┘
                        │ 统一 Alert 对象
                        ▼
┌─────────────────────────────────────────────────────┐
│                编排层 (Orchestration Layer)            │
│  MOD-003: StateGraphEngine │ MOD-004: AlertNormalizer │
│  MOD-005: NodeHandlers（14 个节点实现）                 │
│           (LangGraph StateGraph + Interrupt)           │
└───────┬─────────────────────────────┬───────────────┘
        │                             │
        ▼                             ▼
┌───────────────────┐    ┌──────────────────────────┐
│ LLM 与知识层       │    │       工具层 (Tool Layer) │
│ MOD-006: LLMService│    │ MOD-010: SwitchConfigTool │
│ MOD-007: Template  │    │ MOD-011: SwitchDiagTool   │
│         Engine     │    │ MOD-012: BackupTool       │
│ MOD-008: RAGService│    │ MOD-013: KnowledgeBase    │
│ MOD-009: Output    │    │          Tool             │
│         Validator  │    │ (策略模式：Mock + TP-Link) │
└───────────────────┘    └──────────────────────────┘
        │                             │
        └──────────┬──────────────────┘
                   ▼
┌─────────────────────────────────────────────────────┐
│            安全与基础设施层 (Security & Infra Layer)   │
│  MOD-014: RiskAssessor │ MOD-015: AuditLogger        │
│  MOD-016: ConfigManager                               │
└─────────────────────────────────────────────────────┘
```

---

## 架构决策记录（ADRs）

---

### ADR-001: LangGraph 状态机架构 — 节点路由与条件边设计

- **Status**: Accepted
- **Context**:
  - REQ-FUNC-006 要求使用 LangGraph 构建有限状态机，按 "告警→诊断→修复→验证→闭环" 流程编排 14 个节点。
  - REQ-FUNC-013 要求在人工审批节点通过 LangGraph Interrupt 机制暂停/恢复状态机。
  - REQ-FUNC-012 要求风险评估后根据 need_human_approval 决定是否进入审批节点。
  - REQ-NFUNC-006 要求验证失败时触发回滚路径。
  - project_brief 第 39-48 行定义了 14 个节点的完整流转顺序。

- **Options**:
  - **Option A: 扁平顺序图 + 条件边（Flat Sequential Graph with Conditional Edges）**
    - 描述：将 14 个节点全部定义在单一 StateGraph 中，节点按主流程链式连接，在分支点（风险评估后、验证后）使用 `add_conditional_edges` 实现路径选择。LangGraph Interrupt 在"人工审批"节点前通过 `interrupt_before` 参数挂起。
    - 优点：简单直观，与 project_brief 中定义的节点流转顺序一一对应；LangGraph 原生支持条件边和 Interrupt，零额外抽象层；调试容易，状态在单张图中完全可见。
    - 缺点：图规模固定，新增节点需修改图定义；所有节点共享同一个 State schema，后续扩展可能需要 schema 迁移。
  - **Option B: 层次化子图（Hierarchical SubGraph）**
    - 描述：将诊断阶段（告警解析→校验→获取信息→SSH→诊断采集）、修复阶段（方案生成→风险评估→审批→备份→执行→验证）分别封装为子图（SubGraph），主图负责编排阶段间流转。
    - 优点：阶段逻辑内聚，子图可独立测试和复用；主图简洁，只关心阶段间的大粒度流转。
    - 缺点：LangGraph SubGraph 之间 State 透传机制复杂；Demo 规模下过度设计；子图边界处的条件路由不直观。
  - **Option C: 事件驱动状态机（Custom FSM without LangGraph）**
    - 描述：不使用 LangGraph，自行实现有限状态机，通过事件队列驱动节点执行，审批中断通过 Future/Promise 挂起。
    - 优点：不依赖 LangGraph 版本 API 稳定性；可完全自定义 Interrupt 机制。
    - 缺点：需要自行实现 LangGraph 已有的状态管理、条件路由、Interrupt 能力，大幅增加开发量；违背 project_brief 明确的 "使用 LangGraph" 技术要求。

- **Decision**: 选择 **Option A（扁平顺序图 + 条件边）**。

  理由：
  1. **需求对齐**：14 个节点的定义在 project_brief 第 47-48 行已明确列出，扁平图直接映射，无歧义（REQ-FUNC-006）。
  2. **条件边支持**：LangGraph `add_conditional_edges` 原生支持以下分支决策：
     - 告警有效性校验 → 无效则跳至 `final_report` 直接结束（REQ-FUNC-005）
     - 风险评估 → `need_human_approval=true` 进入 `human_approval`，否则跳过（REQ-FUNC-012, REQ-NFUNC-003）
     - 结果验证 → 失败则进入 `rollback` 路径，成功则进入 `final_report`（REQ-NFUNC-006）
     - 备份配置 → 备份失败直接标记 FAILED 并跳过修复（REQ-NFUNC-005）
  3. **Interrupt 机制**：LangGraph `interrupt_before=["human_approval"]` 精确满足 REQ-FUNC-013 的审批中断需求，审批恢复后自动从 `human_approval` 节点的出口边继续执行（US-007 AC-007-02）。
  4. **Demo 适配性**：Option B 的子图设计在 14 节点规模下过度抽象，增加调试难度。Option C 违背技术约束。

- **Consequences**:
  - **正向**：
    - 完整支撑 REQ-FUNC-006（状态机编排）、REQ-FUNC-012（风险评估路由）、REQ-FUNC-013（Interrupt 中断/恢复）、REQ-NFUNC-003（高风险审批路由）、REQ-NFUNC-006（验证失败回滚路由）。
    - 节点实现（MOD-005 NodeHandlers）可以专注单一职责，每个节点对应一个 Python 函数。
    - LangGraph 自带的 State 追踪和调试工具可直接用于 Demo 演示。
  - **负向**：
    - 14 个节点 + 4 个条件边的图定义文件较长（预计 200+ 行），维护时需确保边定义不遗漏。
    - 未来如果节点数增长至 20+，需考虑重构为层次化子图（当前 Demo 范围无此风险）。

---

### ADR-002: Mock 层抽象设计 — 策略模式与 TP-Link 预留接口

- **Status**: Accepted
- **Context**:
  - REQ-FUNC-017（SwitchConfigTool）、REQ-FUNC-018（SwitchDiagTool）、REQ-FUNC-020（BackupTool）在 Demo 阶段均为 Mock 实现，但必须预留 TP-Link 交换机的真实 SSH/CLI 适配层。
  - REQ-NFUNC-014 要求 Mock 与真实实现的接口签名一致性。
  - project_brief 第 13 行明确 "TP-Link 通常用 SSH/CLI，命令风格接近 Cisco IOS"。
  - project_brief 第 18 行明确 "工具层：全部 Mock 实现，但预留 TP-Link 交换机真实接口"。
  - IFC-003 已定义 4 个工具的逻辑接口签名，但未规定实现层面的抽象方式（开放问题 Q-003 交由 GROUP_B 决策）。

- **Options**:
  - **Option A: 策略模式（Strategy Pattern）+ 抽象基类**
    - 描述：每个工具定义抽象基类（AbstractTool），声明标准接口方法；提供 `MockToolImpl`（返回模拟数据）和 `TpLinkToolImpl`（通过 Netmiko/NAPALM 走真实 SSH/CLI）两个策略实现。运行时通过工厂函数或配置决定使用哪个策略。
    - 优点：接口契约由抽象基类强制约束（Python ABC），Mock 与真实实现签名一致有编译期/加载期保证；新增厂商支持只需增加新的策略类而不修改调用方；符合 LangChain BaseTool 的继承体系。
    - 缺点：额外抽象层增加 Demo 阶段的代码量（每个工具需要 1 个 ABC + 2 个实现类）。
  - **Option B: 适配器模式（Adapter Pattern）**
    - 描述：工具对外暴露统一接口，内部持有 `_driver: MockDriver | TpLinkDriver` 适配器对象，根据配置选择适配器，方法调用委托给适配器。
    - 优点：与 Option A 类似的结构分离；适配器可以跨工具共享（如 SSH 连接适配器被 Diag 和 Config 工具共用）。
    - 缺点：共享适配器状态（如 SSH session）增加耦合；不如策略模式直观——每个工具的 Mock 数据逻辑完全不同，共享的 Mock Driver 反而需要内部分支判断工具类型。
  - **Option C: 简单条件分支（if-else within Tool）**
    - 描述：在工具的 `_run()` 方法内通过 `if self.use_mock: return mock_data else: real_ssh_call()` 分支实现切换。
    - 优点：实现最简单，零额外类定义。
    - 缺点：Mock 逻辑和真实逻辑混在一个文件，违反单一职责原则；接口签名一致性无强制保证，依赖开发人员自律；不符合 "预留接口" 的设计意图——这不是接口预留，是代码分支。

- **Decision**: 选择 **Option A（策略模式 + 抽象基类）**。

  理由：
  1. **接口签名一致性保证**：ABC 强制子类实现完全相同的方法签名，满足 REQ-NFUNC-014 的核心要求。PM 在后续阶段替换为 TP-Link 真实实现时，只需编写 `TpLinkSwitchConfigTool` 继承同一 ABC，无需修改 MOD-005 NodeHandlers 中的任何调用代码。
  2. **符合 LangChain Tool 生态**：每个策略类继承 `langchain_core.tools.BaseTool`，可无缝集成到 LangChain Agent/Graph 中，与 REQ-FUNC-017 ~ REQ-FUNC-020 定义的 "标准 LangChain Tool" 要求一致。
  3. **TP-Link Cisco IOS 风格适配**：`TpLinkSwitchConfigTool` 策略类的命令执行逻辑使用 Netmiko（SSH）+ NAPALM（配置管理），TP-Link 的 Cisco IOS 风格命令（如 `show running-config`、`interface Gi0/1`、`no shutdown`）与这两个库的原生 Cisco IOS 驱动兼容（project_brief 第 13 行）。
  4. **Option C 不满足设计规范**：project_brief 要求 "预留接口"，Option C 的 if-else 分支不是接口预留，是逻辑内嵌，否决。

- **Consequences**:
  - **正向**：
    - 完整支撑 REQ-NFUNC-014（接口预留）、REQ-FUNC-017~020（4 个工具的封装）、REQ-FUNC-008（SSH 连接预留）。
    - 4 个工具的 ABC 定义构成系统的 Tool Layer 接口契约（在 module_design.md 中详细声明）。
    - 未来新增工具类型时，复用同一套策略模式模板即可。
  - **负向**：
    - Demo 代码量约增加 30%（每个工具多 1 个 ABC + 1 个 Mock 实现类），但这是 "预留接口" 的设计代价。
    - Python ABC 在运行时通过 `__subclasshook__` 或显式 `ABCMeta` 检查，如果 Mock 实现的方法签名与 ABC 不一致，会在实例化时报错而非编译期捕获。

---

### ADR-003: LLM 调用安全架构 — 路由隔离与输出校验

- **Status**: Accepted
- **Context**:
  - REQ-NFUNC-001（CRITICAL）要求从机制层面禁止 LLM 自由生成设备配置命令。
  - REQ-NFUNC-002（CRITICAL）要求 LLM 输出仅限于模板参数值。
  - REQ-FUNC-010 要求 LLM 用于根因分析（需要自由文本推理能力）。
  - REQ-FUNC-011 要求 LLM 仅填充模板参数，不生成命令。
  - 这里存在一个关键架构矛盾：同一 LLM 实例在不同场景下，有时需要开放文本生成能力（根因分析），有时需要严格约束输出（参数填充）。架构必须隔离这两种调用路径。
  - US-008 AC-008-05 要求对 LLM 输出做合规校验，拒绝包含 CLI 命令的输出。
  - US-011 AC-011-03 要求 "命令拼装应当由非 LLM 的确定性代码完成（模板引擎）"。

- **Options**:
  - **Option A: 场景路由隔离 + 输出校验层（Routed Prompt + Output Validation Layer）**
    - 描述：LLMService（MOD-006）提供两个独立调用端点——`analyze_root_cause()`（自由推理，输出 Markdown 格式的 root_cause）和 `fill_template_params()`（严格约束，Prompt 要求输出纯 JSON，仅包含参数键值对）。每个端点的输出经过 OutputValidator（MOD-009）校验：自由推理端点做敏感性扫描（不过滤命令，因为它不生成命令，只做风险标记），参数填充端点做严格 Schema 校验（JSON Schema 验证，拒绝任何包含命令语法的输出）。校验通过的参数交给 TemplateEngine（MOD-007）做确定性命令拼装。
    - 优点：同一 LLM 实例、不同 Prompt 模板、不同校验策略，精确满足根因分析（开放）和参数填充（约束）两种场景需求；OutputValidator 作为安全闸门，满足 REQ-NFUNC-001/002 的 "机制层面" 要求；两个调用路径的代码隔离，降低 Prompt 注入风险。
    - 缺点：需要维护两套 Prompt 模板和两套校验规则。
  - **Option B: 单一 LLM 调用 + 后置黑名单过滤**
    - 描述：所有 LLM 调用使用同一 Prompt 模板，让 LLM 同时输出根因分析和修复参数。执行前用正则表达式扫描输出，过滤掉匹配 CLI 命令模式的内容。
    - 优点：调用链路简单，单次 LLM 请求完成所有推理。
    - 缺点：黑名单过滤不可靠——CLI 命令变体无限，正则无法穷举；LLM 可能将命令嵌入自然语言文本中绕过滤；不满足 "机制层面" 保障（REQ-NFUNC-001）：黑名单是被动防御，不是主动隔离。**严重不符合安全底线**。
  - **Option C: LLM 仅做根因分析 + 纯规则修复匹配**
    - 描述：LLM 仅用于根因分析（自由文本），修复方案完全由 RAG + 规则匹配决定，LLM 不参与修复方案生成的任何环节。
    - 优点：最大程度减少 LLM 接触修复方案的路径，安全风险最低。
    - 缺点：失去了 project_brief 中 "LLM 灵活推理" 在修复方案生成中的价值——LLM 可以根据根因分析结果智能选择最合适的模板和参数值（如根据上下文选择 `no shutdown` vs `shutdown` + 重配置）；纯规则匹配在面对微妙故障时缺乏灵活性。

- **Decision**: 选择 **Option A（场景路由隔离 + 输出校验层）**。

  理由：
  1. **安全机制保障**：Option A 从架构层面隔离了 "自由推理" 和 "受约束填充" 两条 LLM 调用路径，配合 OutputValidator 的 JSON Schema 严格校验，满足 REQ-NFUNC-001/002 的 CRITICAL 要求。
  2. **确定性兜底**：LLM 输出的参数值通过 OutputValidator 校验后，由 TemplateEngine（MOD-007，纯确定性代码，Jinja2 模板引擎）完成命令拼装。这满足了 US-011 AC-011-03 "命令拼装应当由非 LLM 的确定性代码完成"。
  3. **黑名单方案不可行**：Option B 依赖正则黑名单，无法应对 LLM 输出变体。交换机 CLI 命令的合法组合近乎无限，黑名单必然存在漏网。**本 Agent 明确拒绝 Option B**。
  4. **Option C 过度保守**：失去 LLM 在修复方案选择中的智能价值，不符合 project_brief 第 8 行 "LLM 灵活推理" 的设计原则。

- **Consequences**:
  - **正向**：
    - 完整支撑 REQ-NFUNC-001（禁止 LLM 自由生成）、REQ-NFUNC-002（LLM 仅填参数）、REQ-FUNC-010（LLM 根因分析）、REQ-FUNC-011（模板匹配修复方案生成）。
    - US-008 AC-008-05 的合规校验由 MOD-009 OutputValidator 强制执行。
    - US-011 AC-011-02 的 CLI 命令检测由 MOD-009 的 `fill_template_params` 校验路径执行。
    - 未来如果 DeepSeek 模型行为变化导致输出格式偏离预期，只需调整 Prompt 模板或校验 Schema，不影响核心流程。
  - **负向**：
    - 两条调用路径 = 两套 Prompt 模板需要维护和调优。
    - JSON Schema 校验可能因 LLM 输出格式微小偏差（如多了个逗号、引号不匹配）导致拒绝合法参数，需要 Prompt 工程中强调严格的 JSON 输出格式。
    - 如果 LLM 在 `fill_template_params` 端点仍然尝试生成命令（虽然 Prompt 已严格约束），MOD-009 的 JSON Schema 校验会拒绝（因为 JSON 中不应出现命令字符串），但需要确保 Schema 定义的参数值类型限定为简单类型（string/number/boolean），不接收嵌套对象或自由文本。

---

### ADR-004: 配置安全架构 — 备份 / 回滚 / 幂等设计

- **Status**: Accepted
- **Context**:
  - REQ-NFUNC-005（Must Have）要求在任何配置修改前自动备份 running-config。
  - REQ-NFUNC-006（Must Have）要求修复失败或验证未通过时自动回滚。
  - REQ-NFUNC-008（Should Have）要求幂等设计，同一修复方案多次执行不导致配置叠加。
  - US-009 AC-009-02 要求备份失败时阻止修复执行（安全底线）。
  - US-009 AC-009-03 要求验证失败时触发回滚。
  - project_brief 第 52-55 行定义安全与可靠性要求。

- **Options**:
  - **Option A: 快照备份 + 全量恢复（Snapshot + Full Restore）**
    - 描述：执行修复前通过 BackupTool 拉取设备完整 running-config 作为快照存入 `config_backup`。回滚时将该快照完整写回设备（全量覆盖）。幂等性通过 "修复前检查当前配置是否已是目标状态" 实现（如：端口已经是 up 则跳过 `no shutdown`）。
    - 优点：备份=快照，回滚=全量覆盖，逻辑简单可靠；running-config 是设备的标准配置表示，恢复后状态确定；满足 REQ-NFUNC-008 的幂等要求（修复前做目标状态检查）。
    - 缺点：对于大型配置，全量备份和恢复的数据量大；回滚是全量覆盖（不是 diff），会丢失备份后到回滚前的其他合法配置变更（Demo 阶段影响小）。
  - **Option B: 命令级日志 + 逐条回滚（Command Log + Reverse Playback）**
    - 描述：记录每一条下发的配置命令及其逆命令（如 `shutdown` 的逆命令为 `no shutdown`）。回滚时按逆序执行逆命令。备份仅用于灾难恢复。
    - 优点：回滚粒度精细，只撤销本次修复的变更，不影响其他配置。
    - 缺点：并非所有命令都有安全的逆命令（如 `reload` 无法逆转）；逆命令执行过程可能引入新故障；命令间的依赖关系（如先删 VLAN 再删 SVI）使逆序执行未必安全。实现复杂度远高于 Demo 承载范围。
  - **Option C: 无备份，仅记录变更（Audit-only, No Rollback）**
    - 描述：不执行自动备份和回滚，仅记录所有下发的命令作为审计日志。回滚由运维人员手动执行。
    - 优点：实现最简单。
    - 缺点：直接违反 REQ-NFUNC-005（配置修改前必须备份）、REQ-NFUNC-006（自动回滚）、US-009 全部验收标准。**不可接受**。

- **Decision**: 选择 **Option A（快照备份 + 全量恢复）**。

  理由：
  1. **安全底线对齐**：满足 REQ-NFUNC-005（修改前备份）、REQ-NFUNC-006（失败时回滚）、US-009 全部验收标准。
  2. **Demo 场景适配**：Demo 阶段设备为单台，配置规模小，全量 running-config 快照的体积可忽略（通常 < 100KB）。
  3. **幂等实现**：在 NodeHandlers 的 "执行修复" 节点（REQ-FUNC-014 对应节点）中，执行每条命令前先检查目标状态是否已满足。例如：下发 `no shutdown` 前先通过 SwitchDiagTool 检查端口是否已是 up 状态，若是则跳过。这满足 REQ-NFUNC-008（Should Have）的幂等要求。
  4. **回滚的安全保障**：回滚时使用备份的 running-config 全量覆盖，是唯一能保证设备回到已知状态的方式。Option B 的逐条逆命令在真实网络设备上存在不确定性风险。

- **Consequences**:
  - **正向**：
    - 完整支撑 REQ-NFUNC-005（备份）、REQ-NFUNC-006（回滚）、REQ-NFUNC-008（幂等检查）、US-009 全部 5 条验收标准。
    - BackupTool 接口简洁：`backup(device_ip, auth) -> BackupResult` 和 `rollback(device_ip, backup_id, auth) -> RollbackResult`。
  - **负向**：
    - 回滚是全量覆盖，如果备份后回滚前设备上发生了其他合法的配置变更，回滚会将其一并抹除。Demo 阶段设备专用于测试，此风险可接受；未来生产化需升级为 diff-based 回滚。
    - 幂等检查（修复前检查目标状态）需要额外的 SwitchDiagTool 调用，增加了修复节点的执行时间（每个命令大约多 1-2 秒）。Demo 场景可接受。

---

### ADR-005: 双触发模式 — Webhook + 定时巡检的统一入口设计

- **Status**: Accepted
- **Context**:
  - REQ-FUNC-001 要求通过 Webhook 接收被动告警。
  - REQ-FUNC-003 要求支持定时触发主动巡检。
  - REQ-FUNC-004 要求将告警解析为统一的 NetworkAgentState。
  - US-004 AC-004-02 要求巡检发现的异常 "与被动 Webhook 触发的流程执行相同的诊断→修复→验证→闭环步骤"。
  - US-005 AC-005-03 要求巡检与被动告警的去重（同一设备同类型告警不重复创建流程）。
  - project_brief 第 23-24 行定义触发层的两种触发方式。

- **Options**:
  - **Option A: 告警归一化层（Alert Normalization Layer）**
    - 描述：Webhook 接收和定时巡检分别产生原始事件数据，统一经过 AlertNormalizer（MOD-004）转换为标准 `Alert` 对象（包含 alert_id, alert_type, alert_content, device_info, source 字段）。标准 `Alert` 对象作为 LangGraph StateGraph 的唯一入口输入。告警去重由 AlertNormalizer 维护的近期告警缓存处理。
    - 优点：两种触发源的差异被封装在归一化层之前，编排层完全不感知告警来源；满足 US-004 AC-004-02 "执行相同的诊断→修复→验证→闭环步骤"；去重逻辑集中在 AlertNormalizer，同时处理 Webhook 重复推送和巡检重复发现的场景（US-005 AC-005-03）。
    - 缺点：AlertNormalizer 成为单点——如果其去重缓存失效，可能重复触发处理；需要定义巡检事件到标准 Alert 的映射规则。
  - **Option B: 双入口 + 中间汇聚（Dual Entry + Mid-flow Convergence）**
    - 描述：Webhook 和巡检各有一个独立的 LangGraph 入口节点（`webhook_entry` 和 `inspection_entry`），各自做完前置处理后，汇聚到同一个 `diagnose` 节点。去重在各自入口节点内部独立处理。
    - 优点：入口节点可以根据触发源特性做差异化预处理（如巡检可以批量处理多设备结果）。
    - 缺点：LangGraph 图有两个入口点，增加了图定义的复杂度；去重逻辑重复实现两次（Webhook 入口和巡检入口各一套）；当新增第三个触发源时，需要新增第三个入口点和第三套去重逻辑。
  - **Option C: 消息队列统一（Message Queue Unification）**
    - 描述：Webhook 和巡检都将原始事件写入消息队列（如 Redis Stream），由一个独立的 Worker 从队列消费事件并进入 LangGraph 流程。
    - 优点：触发源与处理完全解耦；天然支持背压和削峰。
    - 缺点：引入额外的中间件依赖（Redis），增加 Demo 部署复杂度；LangGraph 的 Interrupt 机制（REQ-FUNC-013）在 Worker 消费模式下需要额外的状态同步方案；超出 Demo 范围策略（project_brief 第 15-20 行未提及消息队列）。

- **Decision**: 选择 **Option A（告警归一化层）**。

  理由：
  1. **需求精确匹配**：US-004 AC-004-02 明确要求巡检告警 "与被动 Webhook 触发的流程执行相同的...步骤"，归一化后的统一入口天然保证这一点。
  2. **去重集中化**：REQ-FUNC-005 的告警去重和 US-005 AC-005-03 的巡检/被动告警去重，在 AlertNormalizer 中统一实现，避免两套去重逻辑的不一致风险。
  3. **Demo 简洁性**：Option A 仅需 1 个归一化模块 + 2 个触发适配器，不引入额外中间件。Option C 的消息队列架构超出 Demo 范围且引入额外运维复杂度。
  4. **扩展性**：未来新增第三种触发源（如 SNMP Trap），只需新增对应的触发适配器并归一化为标准 Alert，编排层零改动。

- **Consequences**:
  - **正向**：
    - 完整支撑 REQ-FUNC-001（Webhook 接收）、REQ-FUNC-003（定时巡检）、REQ-FUNC-004（告警解析）、REQ-FUNC-005（去重检查）。
    - LangGraph 图只有唯一入口 `receive_alert` 节点，图定义简洁。
    - 巡检告警的 `source` 字段标记为 `INSPECTION`，方便审计区分（US-004 AC-004-01）。
  - **负向**：
    - AlertNormalizer 的去重缓存大小和过期策略需要谨慎设计（建议缓存 100 条最近告警，TTL = 巡检间隔 × 3 = 15 分钟），[ASSUMPTION — 缓存策略参数待 PM 确认]。
    - 巡检批量处理多设备时，AlertNormalizer 需要为每台异常设备生成独立的 Alert 对象，串行进入 StateGraph——这意味着如果 10 台设备同时异常，第 10 台需要等待前 9 台处理完毕。Demo 阶段设备数少，此限制可接受。

---

### ADR-006: 知识库架构 — 本地向量库选型 + RAG 链路设计

- **Status**: Accepted
- **Context**:
  - REQ-FUNC-019 要求封装 RAG 知识库检索为标准 Tool，支持按告警类型和诊断结果检索故障案例和预案。
  - REQ-FUNC-022 要求预沉淀故障处理预案，将故障特征与修复方案模板建立映射。
  - REQ-FUNC-021 要求预沉淀命令模板，LLM 仅能选取和填充模板参数。
  - US-008 AC-008-02 要求 RAG 检索返回匹配的故障案例、处理预案和相关命令模板。
  - Demo 范围：资源层命令模板库为真实实现，故障预案库为 Mock 实现（内嵌 3 种告警类型的示例预案）。
  - project_brief 第 36-37 行定义 "预沉淀各厂商交换机命令模板、故障处理预案"。

- **Options**:
  - **Option A: Chroma 本地向量库 + LangChain Embeddings + JSON 文档存储**
    - 描述：使用 Chroma 作为本地向量数据库，通过 LangChain 的 `text-embedding-3-small` 模型（或 DeepSeek Embedding）将故障案例/预案/命令模板的描述文本向量化存入 Chroma。检索时执行语义相似度搜索，返回 Top-K 匹配结果。原始文档（预案全文、命令模板）存放在本地 JSON 文件中，Chroma 存储向量索引 + 元数据（指向 JSON 文件的文档 ID）。
    - 优点：Chroma 是 LangChain 生态原生支持的向量库，零额外部署依赖（嵌入式运行）；语义搜索比关键词匹配更能处理故障描述的变体表述；本地运行满足 Demo 独立部署需求；向量索引持久化到磁盘，重启不丢失。
    - 缺点：Demo 数据量极小（3 类告警 × 每类 2-3 条预案 = ~10 条文档），语义搜索的优势不明显；向量模型（text-embedding-3-small）需要额外的 API 调用成本。
  - **Option B: FAISS 本地向量索引 + LangChain Embeddings**
    - 描述：使用 FAISS（Facebook AI Similarity Search）构建本地向量索引，通过 LangChain Embeddings 生成文档向量，检索时执行 L2/余弦相似度搜索。
    - 优点：FAISS 在百万级向量规模下性能最优，纯内存/磁盘索引，速度快。
    - 缺点：FAISS 的索引文件管理比 Chroma 更底层（需要手动处理索引持久化和更新）；LangChain 与 Chroma 的集成更成熟（自动处理元数据过滤、文档 upsert）；Demo 数据量极小，FAISS 的性能优势完全体现不出；FAISS 不支持元数据过滤的 SQL 风格查询。
  - **Option C: 简单关键词匹配 + JSON 文件（No Vector DB）**
    - 描述：不使用向量数据库，将故障案例和命令模板存储在 JSON 文件中，通过告警类型（`alert_type`）做精准匹配 + 关键词模糊搜索。
    - 优点：零额外依赖，实现极其简单；Demo 数据量下精准匹配足够。
    - 缺点：不支持语义级别的相似搜索——如果故障描述使用了不同的措辞（如 "端口反复up/down" vs "链路抖动"），关键词匹配可能失败；无法体现 project_brief 中 "RAG 知识库检索" 的技术内涵；未来知识条目增长到 100+ 时，关键词匹配的召回率会急剧下降。

- **Decision**: 选择 **Option A（Chroma 本地向量库 + LangChain Embeddings）**。

  理由：
  1. **LangChain 生态原生集成**：Chroma 通过 `langchain_chroma.Chroma` 直接与 LangChain Document/Retriever 体系对接，KnowledgeBaseTool（MOD-013）作为 LangChain Tool 实现时无需适配代码。
  2. **语义搜索能力**：尽管 Demo 数据量小，但语义搜索支持 "MAC 地址漂移" 与 "MAC flapping"、"端口 Down" 与 "链路中断" 等多表述匹配，满足 US-008 AC-008-02 的 RAG 检索要求。
  3. **元数据过滤**：Chroma 的 `where` 子句支持按 `alert_type` 做预过滤（如只检索 MAC_FLAPPING 相关的案例），提升检索精准度。
  4. **持久化**：Chroma 的嵌入式模式支持磁盘持久化，重启后知识库无需重建索引。
  5. **扩展路径**：如果 Demo 后需要升级到生产级，Chroma 有 Server 模式（客户端/服务端分离）可供升级。FAISS（Option B）的索引管理在增量更新场景下比 Chroma 更繁琐。Option C 的关键词匹配方案在知识条目增长后不可持续。

- **Consequences**:
  - **正向**：
    - 完整支撑 REQ-FUNC-019（RAG 知识库检索）、REQ-FUNC-021（命令模板管理）、REQ-FUNC-022（故障处理预案）、US-008 AC-008-02（RAG 检索返回匹配案例）。
    - 命令模板通过元数据与告警类型关联，检索响应时间 < 100ms（嵌入式 Chroma，小数据量）。
  - **负向**：
    - 增加了 text-embedding-3-small 的 API 调用成本（Demo 阶段知识条目少，一次索引即可，成本可忽略）。
    - Chroma 嵌入式模式在 Windows 和 Linux 下的 SQLite 行为可能有差异（REQ-NFUNC-012 要求 Linux，需在 Linux 上验证 Chroma 的持久化路径）。
    - 初始知识条目（~10 条）的语义多样性低，可能导致 "噪音匹配"（检索到不相关的条目），需要通过 `alert_type` 元数据过滤和相似度阈值（建议 ≥ 0.6）来缓解。[ASSUMPTION — 相似度阈值待 PM 确认]

---

## 需求到模块覆盖矩阵

| REQ ID | 描述（摘要） | 覆盖模块 | 覆盖方式 |
|--------|-------------|---------|---------|
| REQ-FUNC-001 | Webhook 告警接收 | MOD-001 WebhookReceiver, MOD-004 AlertNormalizer | MOD-001 接收 HTTP POST，MOD-004 解析为标准 Alert |
| REQ-FUNC-002 | Mock 网管告警推送脚本 | MOD-001 WebhookReceiver | Mock Webhook 脚本作为独立工具，不纳入模块体系 |
| REQ-FUNC-003 | 主动巡检定时触发 | MOD-002 InspectionScheduler | APScheduler 定时触发，检测阈值可配置 |
| REQ-FUNC-004 | 告警解析 | MOD-004 AlertNormalizer | 提取 alert_id/type/content/device_info |
| REQ-FUNC-005 | 告警有效性校验（去重+时效性） | MOD-005 NodeHandlers (validate_alert node) | 内置去重缓存 + 时效性检查 |
| REQ-FUNC-006 | LangGraph 状态机编排 | MOD-003 StateGraphEngine | 定义 14 节点 + 4 条件边 + Interrupt |
| REQ-FUNC-007 | 获取设备信息 | MOD-005 NodeHandlers (get_device_info node) | 从设备信息库查询 |
| REQ-FUNC-008 | 建立 SSH 连接 | MOD-010 SwitchConfigTool, MOD-011 SwitchDiagTool | 策略模式预留 TP-Link SSH |
| REQ-FUNC-009 | 采集诊断信息 | MOD-011 SwitchDiagTool | Mock 返回模拟诊断数据 |
| REQ-FUNC-010 | LLM 根因分析+知识库检索 | MOD-005 (analyze_root_cause node), MOD-006 LLMService, MOD-008 RAGService | LLM 推理 + Chroma RAG 检索 |
| REQ-FUNC-011 | 生成修复方案（模板匹配） | MOD-005 (generate_fix_plan node), MOD-007 TemplateEngine | 模板匹配 + LLM 填参 + 确定性拼装 |
| REQ-FUNC-012 | 风险评估 | MOD-014 RiskAssessor | 高风险操作模式匹配 |
| REQ-FUNC-013 | 人工审批中断与恢复 | MOD-003 StateGraphEngine (Interrupt), MOD-005 (human_approval node) | LangGraph interrupt_before |
| REQ-FUNC-014 | 执行修复 | MOD-010 SwitchConfigTool | 命令逐条下发 |
| REQ-FUNC-015 | 结果验证 | MOD-005 (verify_result node), MOD-011 SwitchDiagTool | 修复前后诊断对比 |
| REQ-FUNC-016 | 生成报告+关闭告警 | MOD-005 (final_report node), MOD-006 LLMService | LLM 汇总生成结构化报告 |
| REQ-FUNC-017 | SwitchConfigTool — 配置下发 | MOD-010 SwitchConfigTool | 策略模式：Mock + TpLink 实现 |
| REQ-FUNC-018 | SwitchDiagTool — 诊断命令执行 | MOD-011 SwitchDiagTool | 策略模式：Mock + TpLink 实现 |
| REQ-FUNC-019 | KnowledgeBaseTool — RAG 检索 | MOD-013 KnowledgeBaseTool | Chroma 向量检索 + LangChain Retriever |
| REQ-FUNC-020 | BackupTool — 配置备份回滚 | MOD-012 BackupTool | 策略模式：Mock + TpLink 实现 |
| REQ-FUNC-021 | 命令模板管理 | MOD-007 TemplateEngine, MOD-008 RAGService | Jinja2 模板 + Chroma 元数据索引 |
| REQ-FUNC-022 | 故障处理预案 | MOD-008 RAGService | Chroma 文档库存储预案 |
| REQ-FUNC-023 | MAC 地址漂移告警处理 | MOD-003, MOD-005, MOD-006, MOD-007, MOD-008, MOD-010~015 | 全链路编排覆盖 |
| REQ-FUNC-024 | 端口 Down 告警处理 | MOD-003, MOD-005, MOD-006, MOD-007, MOD-008, MOD-010~015 | 全链路编排覆盖 |
| REQ-FUNC-025 | CPU 利用率过高告警处理 | MOD-003, MOD-005, MOD-006, MOD-007, MOD-008, MOD-010~015 | 全链路编排覆盖 |
| REQ-NFUNC-001 | 禁止 LLM 自由生成命令 | MOD-006 LLMService, MOD-007 TemplateEngine, MOD-009 OutputValidator | 路由隔离 + 模板引擎 + 输出校验 |
| REQ-NFUNC-002 | LLM 仅填充模板参数 | MOD-006 LLMService (fill_template_params), MOD-009 OutputValidator | JSON Schema 约束输出 |
| REQ-NFUNC-003 | 高风险操作强制审批 | MOD-014 RiskAssessor, MOD-003 (Interrupt) | 风险标识 + Interrupt 挂起 |
| REQ-NFUNC-004 | 最小权限账号 | MOD-016 ConfigManager | 凭据配置中约束权限等级 |
| REQ-NFUNC-005 | 配置修改前自动备份 | MOD-012 BackupTool, MOD-005 (backup_config node) | 修复前强制备份检查 |
| REQ-NFUNC-006 | 自动回滚 | MOD-012 BackupTool, MOD-005 (rollback node) | 验证失败触发回滚 |
| REQ-NFUNC-007 | 超时重试 | MOD-010, MOD-011 | 工具层超时装饰器 + 重试逻辑 |
| REQ-NFUNC-008 | 幂等设计 | MOD-005 (execute_fix node) | 修复前目标状态检查 |
| REQ-NFUNC-009 | 灰度执行（可选） | — | Demo 不实现（Could Have） |
| REQ-NFUNC-010 | 全链路操作日志 | MOD-015 AuditLogger | 每个节点执行前后记录 |
| REQ-NFUNC-011 | 操作审计追踪 | MOD-015 AuditLogger | 追加写入不可篡改日志 |
| REQ-NFUNC-012 | 目标操作系统 Linux | 全部模块 | Python 3.11+ 兼容 Linux |
| REQ-NFUNC-013 | LLM API 约束 (DeepSeek) | MOD-006 LLMService | openai SDK + deepseek-chat |
| REQ-NFUNC-014 | TP-Link 接口预留 | MOD-010~013（策略模式 ABC） | 抽象基类 + Mock/TpLink 双实现 |

---

## 开放问题

| 编号 | 问题 | 状态 |
|------|------|------|
| Q-ARCH-001 | [ASSUMPTION] AlertNormalizer 去重缓存策略：建议缓存 100 条最近告警，TTL = 巡检间隔 × 3 = 15 分钟 | 待 PM 确认 |
| Q-ARCH-002 | [ASSUMPTION] Chroma RAG 相似度阈值建议设为 0.6（低于阈值的检索结果丢弃） | 待 PM 确认 |
| Q-ARCH-003 | [ASSUMPTION] 诊断命令超时默认 30s（REQ-NFUNC-014 推断），重试上限默认 3 次 | 已在 requirements_spec 中标注，待 PM 确认 |
| Q-ARCH-004 | [ASSUMPTION] 巡检间隔默认 5 分钟，通过 MOD-016 ConfigManager 可配置 | 已在 requirements_spec Q-001 中标识，待 PM 确认 |
| Q-ARCH-005 | [ASSUMPTION] 人工审批无超时限制（US-007 AC-007-01），系统无限期保持 State | 已在 requirements_spec Q-002 中标识，已体现在 ADR-001 |
