<file_header>
  <author_agent>sub_agent_requirement_analyst</author_agent>
  <timestamp>2026-07-09T00:00:00Z</timestamp>
  <project_name>NetworkAgentDemo</project_name>
  <version>0.1.0</version>
  <input_files>
    <file>requirements/project_brief.md</file>
  </input_files>
  <phase>PHASE_02</phase>
  <status>APPROVED</status>
</file_header>

# 用户故事清单 — NetworkAgentDemo

---

## 用户角色地图（Actor X Feature Matrix）

| Actor | 被动告警（Webhook） | 主动巡检 | 人工审批 | 诊断分析 | 安全管控 | 审计追溯 |
|--------|:---:|:---:|:---:|:---:|:---:|:---:|
| **运维人员 (Operator)** | US-001, US-002, US-003 | US-004, US-005 | US-006, US-007 | US-008 | US-011 | US-010 |
| **审计人员 (Auditor)** | — | — | — | — | — | US-010 |

> 来源：project_brief.md 第3-5行 — “典型网络运维闭环 Agent 场景”

---

## 用户故事详情

---

### US-001: 被动接收 MAC 地址漂移告警并自动处置

- **用户故事**：As a 运维人员, I want to 当网管系统通过 Webhook 推送 MAC 地址漂移告警时，系统自动完成告警解析、诊断采集、根因分析、修复方案生成，并在高风险操作前暂停等待我审批后执行修复和验证, so that MAC 地址漂移故障能够快速、安全地被定位和修复，减少网络环路或安全风险。
- **关联需求**：REQ-FUNC-001, REQ-FUNC-002, REQ-FUNC-004, REQ-FUNC-005, REQ-FUNC-006, REQ-FUNC-007, REQ-FUNC-008, REQ-FUNC-009, REQ-FUNC-013, REQ-FUNC-015, REQ-FUNC-016, REQ-FUNC-018, REQ-FUNC-023
- **优先级**：P0 (Must Have)
- **故事点**：[INFERRED — 待开发团队评估]
- **触发模式**：被动告警触发
- **告警类型**：MAC 地址漂移 (MAC_FLAPPING)

**验收标准：**

- **AC-001-01** — 正常路径：MAC 漂移告警接入并完成诊断
  - Given 网管系统（Mock Webhook）模拟推送一条 MAC 地址漂移告警，包含设备 IP 和漂移的 MAC 地址信息
  - When 系统通过 Webhook 接口接收该告警
  - Then 系统应当成功解析告警，提取 alert_type="MAC_FLAPPING"、device_info 和 alert_content，状态机进入"告警解析"节点，且 alert_id 已分配

- **AC-001-02** — 诊断信息采集
  - Given 告警已成功解析且通过有效性校验（非重复、非过期），设备信息已获取
  - When 系统进入"采集诊断信息"节点
  - Then 系统应当通过 SwitchDiagTool 执行 show mac address-table 诊断命令，并将返回结果写入 diag_result 字段

- **AC-001-03** — 根因分析与修复方案生成
  - Given diag_result 包含 MAC 地址漂移相关数据（漂移的 MAC 地址在多个端口间切换）
  - When 系统进入"根因分析+知识库检索"节点并调用 LLM + RAG
  - Then 系统应当输出 root_cause（如"检测到 MAC X 在端口 Gi0/1 和 Gi0/2 之间漂移，疑似环路或端口安全配置缺失"），knowledge_refs 关联到相关预案，并生成对应的 fix_plan（匹配命令模板）

- **AC-001-04** — 完整闭环验证
  - Given fix_plan 已执行且验证通过
  - When 系统进入"生成报告+关闭告警"节点
  - Then 系统应当生成 final_report 包含 alert_id、root_cause、fix_plan、exec_log、verify_result，并将 status 设置为 CLOSED

- **AC-001-05** — 异常路径：重复告警过滤
  - Given 系统已有一条处理中的 MAC 地址漂移告警（alert_id 相同）
  - When 再次收到相同 alert_id 的重复告警
  - Then 系统应当在"告警有效性校验"节点识别重复，跳过该告警，不重复创建处理流程

---

### US-002: 被动接收端口 Down 告警并自动处置

- **用户故事**：As a 运维人员, I want to 当网管系统通过 Webhook 推送端口 Down 告警时，系统自动诊断端口状态、分析 Down 原因、生成修复方案，并对高风险端口操作进行审批后执行修复, so that 关键端口 Down 故障能够得到及时诊断和安全恢复，减少业务中断时间。
- **关联需求**：REQ-FUNC-001, REQ-FUNC-002, REQ-FUNC-004, REQ-FUNC-005, REQ-FUNC-006, REQ-FUNC-007, REQ-FUNC-008, REQ-FUNC-009, REQ-FUNC-013, REQ-FUNC-015, REQ-FUNC-016, REQ-FUNC-018, REQ-FUNC-024
- **优先级**：P0 (Must Have)
- **故事点**：[INFERRED — 待开发团队评估]
- **触发模式**：被动告警触发
- **告警类型**：端口 Down (PORT_DOWN)

**验收标准：**

- **AC-002-01** — 正常路径：端口 Down 告警接入
  - Given 网管系统模拟推送一条端口 Down 告警，包含设备 IP、接口名称（如 Gi0/1）和 Down 状态
  - When 系统通过 Webhook 接收该告警
  - Then 系统应当解析告警，alert_type="PORT_DOWN"，device_info 中包含 interface_name

- **AC-002-02** — 端口诊断数据采集
  - Given 告警已解析，目标设备 SSH 连接已建立
  - When 系统执行 SwitchDiagTool 的 show interface 诊断命令
  - Then 系统应当获取目标端口的详细信息（状态、错误计数、最近变更时间等），写入 diag_result

- **AC-002-03** — 根因诊断（管理性 Down vs 故障 Down）
  - Given diag_result 显示端口状态为 "administratively down"
  - When LLM 进行根因分析
  - Then root_cause 应当识别端口为管理性关闭，区别于链路故障导致的 Down，fix_plan 建议 "no shutdown" 操作

- **AC-002-04** — 高风险端口操作触发审批
  - Given fix_plan 包含端口 "shutdown" 或 "no shutdown" 操作
  - When 系统进入"风险评估"节点
  - Then need_human_approval 应当被设置为 true（端口操作属于高风险类别），状态机在"人工审批"节点暂停

- **AC-002-05** — 异常路径：SSH 连接失败
  - Given 设备信息已获取但目标设备 SSH 不可达
  - When 系统尝试"建立SSH连接"节点
  - Then 系统应当在超时重试上限后标记连接失败，在 exec_log 中记录错误，并将 status 设置为 FAILED 且不执行后续修复

---

### US-003: 被动接收 CPU 利用率过高告警并自动处置

- **用户故事**：As a 运维人员, I want to 当网管系统推送 CPU 利用率过高告警时，系统自动采集设备进程信息、分析 CPU 过载根因、通过模板化方案进行修复，并在需要设备重启等高风险操作时获得我的审批, so that CPU 过载问题能够被快速定位（异常进程或流量攻击）并安全处理，避免设备性能持续劣化。
- **关联需求**：REQ-FUNC-001, REQ-FUNC-002, REQ-FUNC-004, REQ-FUNC-005, REQ-FUNC-006, REQ-FUNC-007, REQ-FUNC-008, REQ-FUNC-009, REQ-FUNC-013, REQ-FUNC-015, REQ-FUNC-016, REQ-FUNC-018, REQ-FUNC-025
- **优先级**：P1 (Should Have)
- **故事点**：[INFERRED — 待开发团队评估]
- **触发模式**：被动告警触发
- **告警类型**：CPU 利用率过高 (CPU_HIGH)

**验收标准：**

- **AC-003-01** — 正常路径：CPU 过高告警接入
  - Given 网管系统模拟推送一条 CPU 利用率过高告警，CPU 利用率 95%，超过阈值 85%
  - When 系统通过 Webhook 接收该告警
  - Then 系统应当解析告警，alert_type="CPU_HIGH"，alert_content 包含当前 CPU 利用率数值

- **AC-003-02** — CPU 诊断数据采集
  - Given 告警已解析且设备 SSH 连接已建立
  - When 系统执行 SwitchDiagTool 的 show processes cpu 诊断命令
  - Then 系统应当获取 CPU 各进程占用详情（Top 进程列表），写入 diag_result

- **AC-003-03** — LLM 区分异常进程与流量过载
  - Given diag_result 显示某个非系统进程（如 SNMP polling）占用 CPU 超过 40%
  - When LLM 进行根因分析
  - Then root_cause 应当识别出异常进程及其影响，fix_plan 建议限制或调整该进程的配置参数

- **AC-003-04** — 非高风险操作自动执行
  - Given fix_plan 仅涉及调整进程参数（非端口操作、非设备重启、非 VLAN 删除）
  - When 系统进入"风险评估"节点
  - Then need_human_approval 应当被设置为 false，状态机跳过"人工审批"节点直接进入执行

- **AC-003-05** — 异常路径：CPU 利用率持续未恢复
  - Given 修复方案已执行但 verify_result 显示 CPU 利用率仍高于阈值
  - When 系统进入"结果验证"节点并判断修复未生效
  - Then 系统应当在 final_report 中标记修复未完全生效，建议人工介入，status 设置为 FAILED

---

### US-004: 主动巡检发现端口异常并触发诊断修复

- **用户故事**：As a 运维人员, I want to 系统按照可配置的时间间隔主动巡检交换机端口状态，当检测到端口异常（Down 或错误计数过高）时自动触发诊断和修复流程, so that 即使网管系统未及时推送告警，端口问题也能被主动发现和处置，实现预防性运维。
- **关联需求**：REQ-FUNC-003, REQ-FUNC-004, REQ-FUNC-006, REQ-FUNC-007, REQ-FUNC-008, REQ-FUNC-009, REQ-FUNC-013, REQ-FUNC-015, REQ-FUNC-016, REQ-FUNC-018, REQ-FUNC-024
- **优先级**：P1 (Should Have)
- **故事点**：[INFERRED — 待开发团队评估]
- **触发模式**：主动巡检触发
- **告警类型**：端口 Down (PORT_DOWN)

**验收标准：**

- **AC-004-01** — 定时巡检触发并检测端口异常
  - Given 系统配置了主动巡检间隔（如每 5 分钟）
  - When 定时器触发巡检任务，系统对所有纳管设备执行 show interface 诊断
  - Then 系统应当检测到状态为 Down 或错误计数超过正常阈值（如 CRC Error > 100）的端口，生成一条内部 PORT_DOWN 告警（source=INSPECTION）

- **AC-004-02** — 巡检告警进入标准诊断流程
  - Given 巡检检测到端口异常并生成了内部告警
  - When 告警进入 LangGraph 状态机
  - Then 流程应当从"告警解析"节点开始，与被动 Webhook 触发的流程执行相同的诊断→修复→验证→闭环步骤

- **AC-004-03** — 巡检报告记录
  - Given 一次巡检周期完成
  - When 所有设备的诊断命令执行完毕
  - Then 系统应当输出巡检摘要（检查设备数、发现异常数、处置结果），写入日志

- **AC-004-04** — 异常路径：巡检中设备不可达
  - Given 巡检任务中某台设备 SSH 不可达
  - When SwitchDiagTool 执行超时
  - Then 系统应当将该设备标记为 UNREACHABLE，记录到巡检日志，不影响其他设备的巡检流程

---

### US-005: 主动巡检发现 CPU 过载并触发诊断修复

- **用户故事**：As a 运维人员, I want to 系统在定时巡检中检测交换机 CPU 利用率状态，当超过阈值时自动采集进程详情并分析根因，必要时触发修复, so that CPU 性能问题能够被主动发现而非等到业务受影响后被动响应。
- **关联需求**：REQ-FUNC-003, REQ-FUNC-004, REQ-FUNC-006, REQ-FUNC-007, REQ-FUNC-008, REQ-FUNC-009, REQ-FUNC-013, REQ-FUNC-015, REQ-FUNC-016, REQ-FUNC-018, REQ-FUNC-025
- **优先级**：P2 (Could Have)
- **故事点**：[INFERRED — 待开发团队评估]
- **触发模式**：主动巡检触发
- **告警类型**：CPU 利用率过高 (CPU_HIGH)

**验收标准：**

- **AC-005-01** — 巡检检测 CPU 超阈值
  - Given 系统定时器触发巡检，巡检包含 show processes cpu 诊断命令
  - When 某设备 CPU 5 分钟平均利用率超过配置的阈值（如 85%）
  - Then 系统应当生成一条内部 CPU_HIGH 告警，触发诊断处理流程

- **AC-005-02** — 巡检 CPU 正常则跳过
  - Given 巡检中某设备 CPU 利用率在正常范围内
  - When 诊断结果显示 CPU 利用率低于阈值
  - Then 系统应当记录"正常"状态，不触发告警处理流程，继续巡检下一台设备

- **AC-005-03** — 巡检与被动告警的去重
  - Given 系统正在处理一条被动 Webhook 触发的 CPU_HIGH 告警（同一设备）
  - When 巡检任务检测到同一设备 CPU 仍然过高
  - Then 系统应当在"告警有效性校验"节点识别已有处理中的同设备同类型告警，不再重复创建流程

---

### US-006: 高风险修复方案人工审批

- **用户故事**：As a 运维人员, I want to 当系统生成的修复方案包含高风险操作时，流程自动暂停并提交给我审批，我能够查看修复方案的详细内容（操作类型、影响范围、风险等级）后做出"批准"或"拒绝"的决定, so that 关键设备上的高风险变更始终在我可控范围内，避免自动化误操作引发生产事故。
- **关联需求**：REQ-FUNC-011, REQ-FUNC-012, REQ-FUNC-013, REQ-FUNC-014, REQ-FUNC-017, REQ-NFUNC-003
- **优先级**：P0 (Must Have)
- **故事点**：[INFERRED — 待开发团队评估]

**验收标准：**

- **AC-006-01** — 高风险方案暂停并提交审批
  - Given 修复方案 fix_plan 经过风险评估，need_human_approval 被设置为 true
  - When 状态机进入"人工审批"节点
  - Then 系统应当通过 LangGraph Interrupt 暂停状态机，向运维人员呈现审批信息（包含：告警描述、根因分析、修复方案详细步骤、风险等级），等待审批输入

- **AC-006-02** — 运维人员批准修复方案
  - Given 状态机处于"人工审批"节点等待中，运维人员审阅修复方案后认为合理
  - When 运维人员输入审批决定 "APPROVED"
  - Then 系统应当将 approval_status 设为 APPROVED，状态机从"人工审批"节点恢复，继续进入"备份配置"节点

- **AC-006-03** — 运维人员拒绝修复方案
  - Given 运维人员审阅修复方案后认为风险不可接受或方案不合理
  - When 运维人员输入审批决定 "REJECTED"
  - Then 系统应当将 approval_status 设为 REJECTED，状态机终止处理流程，在 final_report 中记录拒绝原因和审批人，status 设为 REJECTED

- **AC-006-04** — 非高风险方案自动跳过审批
  - Given fix_plan 的风险评估结果 need_human_approval = false（如仅调整日志级别、查询类操作）
  - When 状态机从"风险评估"节点流转
  - Then 系统应当跳过"人工审批"节点，直接进入"备份配置"节点执行修复

- **AC-006-05** — 端口 shutdown 操作必须审批
  - Given fix_plan 中包含 "shutdown" 命令（关闭某个接口）
  - When 风险评估节点检测到 shutdown 操作
  - Then need_human_approval 必须为 true，无论其他因素

- **AC-006-06** — VLAN 删除操作必须审批
  - Given fix_plan 中包含 VLAN 删除命令（如 "no vlan 100"）
  - When 风险评估节点检测到 VLAN 删除操作
  - Then need_human_approval 必须为 true，无论其他因素

---

### US-007: 人工审批期间流程挂起与审批后自动恢复

- **用户故事**：As a 运维人员, I want to 在审批决策期间，系统安全地挂起处理流程（不超时自动执行、不丢失上下文状态），待我做出审批决定后自动从中断点无缝恢复执行, so that 我不需要担心审批响应时间影响系统稳定性，也不会因为审批延迟导致流程状态混乱或数据丢失。
- **关联需求**：REQ-FUNC-013, REQ-FUNC-014, REQ-FUNC-017
- **优先级**：P0 (Must Have)
- **故事点**：[INFERRED — 待开发团队评估]

**验收标准：**

- **AC-007-01** — LangGraph Interrupt 挂起状态保持
  - Given 状态机在"人工审批"节点被 Interrupt 暂停
  - When 运维人员超过 10 分钟未做出审批（长时间未响应）
  - Then 系统应当保持 NetworkAgentState 全部字段不变（包括 alert_id、diag_result、root_cause、fix_plan），不自动超时执行也不丢失任何上下文数据

- **AC-007-02** — 审批通过后从断点恢复
  - Given 状态机在"人工审批"节点暂停，approval_status 原为 PENDING
  - When 运维人员输入 APPROVED，approval_status 更新为 APPROVED
  - Then 状态机应当从"人工审批"节点之后的下一个节点（"备份配置"）继续执行，流程上下文（State）完整保留

- **AC-007-03** — 审批拒绝后流程优雅终止
  - Given 状态机在"人工审批"节点暂停
  - When 运维人员输入 REJECTED
  - Then 状态机应当终止执行（不进入"备份配置"和"执行修复"节点），在 final_report 中记录审批结果，status = REJECTED，且已采集的诊断数据和根因分析结果被保留供后续审计

- **AC-007-04** — 审批挂起期间系统状态可查询
  - Given 至少有一条告警处理流程处于"人工审批"挂起状态
  - When 运维人员查询当前系统状态
  - Then 系统应当能够返回所有挂起中的审批项列表（含 alert_id、告警类型、设备名称、挂起时间、待审批的修复方案摘要）

---

### US-008: LLM 辅助故障根因诊断与修复方案生成

- **用户故事**：As a 运维人员, I want to 系统将采集到的设备诊断数据发送给 LLM（DeepSeek）结合 RAG 知识库进行智能分析，自动推断故障根因并匹配最佳的修复方案模板, so that 即使面对复杂故障场景，我也能获得 AI 辅助的高质量诊断建议，减少人工排查时间和误判风险。
- **关联需求**：REQ-FUNC-010, REQ-FUNC-011, REQ-FUNC-019, REQ-FUNC-022, REQ-NFUNC-013
- **优先级**：P0 (Must Have)
- **故事点**：[INFERRED — 待开发团队评估]

**验收标准：**

- **AC-008-01** — LLM 基于诊断数据进行根因推理
  - Given 系统已采集 diag_result（包含设备诊断命令输出），且告警类型为 MAC_FLAPPING
  - When 系统调用 LLM（deepseek-chat 通过 openai SDK + DeepSeek base_url）进行根因分析，Prompt 中包含告警内容和诊断数据
  - Then LLM 应当返回结构化的 root_cause（包含：故障描述、可能原因列表（按概率排序）、建议的修复方向）

- **AC-008-02** — RAG 知识库检索匹配历史案例
  - Given diag_result 与根因分析请求
  - When 系统通过 KnowledgeBaseTool 执行 RAG 检索，查询与当前故障特征匹配的历史案例
  - Then 系统应当返回 knowledge_refs 列表，包含匹配的故障案例标题、处理预案摘要和相关命令模板引用

- **AC-008-03** — LLM 仅填充模板参数（安全约束）
  - Given 知识库已匹配到对应的修复命令模板（如端口启用模板：`interface {iface_name}\n no shutdown\n description {desc}`）
  - When LLM 生成 fix_plan
  - Then LLM 输出应当仅包含模板参数值（如 `{iface_name: "Gi0/1", desc: "Auto-recovered by Agent"}`），绝对不得包含完整的 CLI 命令语法或新增模板中不存在的命令

- **AC-008-04** — LLM 调用失败时的降级处理
  - Given LLM API（DeepSeek）不可用或返回错误
  - When 根因分析步骤调用 LLM 失败
  - Then 系统应当记录 LLM 调用异常日志，尝试基于纯 RAG 匹配结果生成 fix_plan（不依赖 LLM），若 RAG 也无匹配则标记 status = FAILED 并提示人工介入

- **AC-008-05** — LLM 输出合规性校验
  - Given LLM 返回的根因分析和参数填充结果
  - When 系统将 LLM 输出写入 root_cause 和 fix_plan 之前
  - Then 系统应当对 LLM 输出进行校验：确认 fix_plan 中不包含模板外的命令字符串，若检测到违规内容则拒绝写入并记录安全告警

---

### US-009: 配置自动备份与失败回滚

- **用户故事**：As a 运维人员, I want to 系统在执行任何配置修改之前自动备份设备 running-config，并且在修复失败或验证未通过时能够自动基于备份配置执行回滚, so that 无论修复操作结果如何，设备配置始终可恢复，不会因自动化操作留下不可逆的错误配置。
- **关联需求**：REQ-FUNC-020, REQ-NFUNC-005, REQ-NFUNC-006
- **优先级**：P0 (Must Have)
- **故事点**：[INFERRED — 待开发团队评估]

**验收标准：**

- **AC-009-01** — 修复前自动备份配置
  - Given 人工审批已通过（或无需审批），状态机即将进入"执行修复"节点
  - When 系统进入"备份配置"节点
  - Then 系统应当通过 BackupTool 执行 BACKUP 操作，将设备 running-config 保存到 config_backup 字段，备份成功后才允许进入"执行修复"

- **AC-009-02** — 备份失败阻止修复执行
  - Given 系统尝试备份配置
  - When BackupTool 返回失败（如设备不可达、权限不足）
  - Then 系统应当阻止后续修复执行，将 status 设为 FAILED，在 exec_log 和 final_report 中明确记录"备份失败，修复未执行"

- **AC-009-03** — 修复失败自动回滚
  - Given 修复方案已执行完毕，但结果验证未通过（verify_result 显示故障仍未解决或引入新问题）
  - When 系统判断需要回滚
  - Then 系统应当通过 BackupTool 执行 ROLLBACK 操作，将 config_backup 中的配置恢复到设备，回滚结果记录在 exec_log 中

- **AC-009-04** — 回滚成功后的状态
  - Given 自动回滚已成功执行
  - When 设备配置已恢复到修复前状态
  - Then 系统应当在 final_report 中记录"修复失败，已回滚"，status = FAILED，保留完整的诊断、修复、回滚全链路日志

- **AC-009-05** — 修复成功则保留备份
  - Given 修复执行成功且验证通过
  - When 系统进入"生成报告+关闭告警"
  - Then config_backup 应当保留（作为变更前配置的快照），供后续审计或手动回滚参考

---

### US-010: 全链路操作审计日志查看

- **用户故事**：As a 运维审计人员, I want to 查看系统从告警接收、诊断分析、修复执行到结果验证的全链路操作日志，日志包含每个步骤的时间戳、操作内容、输入输出数据和执行结果, so that 我能够追溯每一次自动化运维操作的完整过程，满足安全审计和合规要求。
- **关联需求**：REQ-NFUNC-010, REQ-NFUNC-011
- **优先级**：P1 (Should Have)
- **故事点**：[INFERRED — 待开发团队评估]

**验收标准：**

- **AC-010-01** — 按告警 ID 查询全链路日志
  - Given 系统已处理过多条告警，每条告警有唯一的 alert_id
  - When 审计人员按 alert_id 查询操作日志
  - Then 系统应当返回该告警从"接收告警"到"生成报告+关闭告警"的所有节点执行记录，每条记录包含：时间戳（ISO8601）、节点名称、输入数据摘要、输出数据摘要、执行耗时、执行结果（SUCCESS/FAILED）

- **AC-010-02** — 关键操作不可篡改审计记录
  - Given 系统执行了一次配置下发操作（SwitchConfigTool）
  - When 审计人员查看该操作的审计记录
  - Then 记录中应当包含：操作时间、目标设备 IP、下发的配置命令列表（含参数值）、操作结果、触发该操作的告警 ID，该记录应当以不可篡改的方式留存（如追加写入日志文件）

- **AC-010-03** — 人工审批决策审计
  - Given 某次处理流程触发了人工审批
  - When 审计人员查看该审批记录
  - Then 记录中应当包含：审批请求时间、审批决策时间、审批人标识、审批决定（APPROVED/REJECTED）、审批依据（运维人员看到的修复方案内容），以证明审批链路完整

---

### US-011: 命令模板化安全管控

- **用户故事**：As a 运维人员, I want to 所有交换机配置操作必须基于预定义的命令模板执行，LLM 仅能选择模板和填充参数而不能生成 CLI 命令, so that 系统在任何情况下都不会向设备下发未经审核的自由格式命令，从根本上避免 LLM 幻觉产生的配置错误导致生产事故。
- **关联需求**：REQ-FUNC-011, REQ-FUNC-021, REQ-NFUNC-001, REQ-NFUNC-002
- **优先级**：P0 (Must Have)
- **故事点**：[INFERRED — 待开发团队评估]

**验收标准：**

- **AC-011-01** — 命令模板库可查询
  - Given 系统预置的命令模板库包含 TP-Link（Cisco IOS 风格）交换机常用操作模板
  - When 修复方案生成阶段查询匹配的模板
  - Then 系统应当返回与故障类型匹配的命令模板列表（如 MAC 漂移对应端口安全配置模板、端口 Down 对应接口启用模板、CPU 过高对应进程管理模板），每个模板明确定义可填充的参数占位符

- **AC-011-02** — LLM 输出不包含 CLI 命令
  - Given LLM 被要求生成 fix_plan 的参数填充结果
  - When 系统对 LLM 输出进行校验
  - Then 若 LLM 输出中包含模板参数占位符之外的 CLI 命令字符串（如 "interface Gi0/1"、"no shutdown"、"switchport mode access" 等），系统应当拒绝该输出，记录安全告警，并回退到仅使用 RAG 匹配的方案

- **AC-011-03** — 模板参数填充与命令拼装分离
  - Given LLM 返回了参数填充结果（如 `{iface_name: "Gi0/1", action: "enable"}`）
  - When 系统准备执行修复
  - Then 命令拼装应当由非 LLM 的确定性代码完成（模板引擎），将参数值填入模板生成最终 CLI 命令列表，确保没有 LLM 自由生成的内容进入执行层

- **AC-011-04** — 未知告警类型的降级
  - Given 系统收到一种未在模板库中预置修复模板的告警类型
  - When 修复方案生成阶段无法匹配到合适的命令模板
  - Then 系统应当在 root_cause 和 fix_plan 中标记"无匹配模板"，建议人工介入，不生成任何设备配置命令，status = FAILED

---

## 用户故事优先级总览

| 优先级 | 用户故事 | 触发模式 | 告警类型 | 说明 |
|--------|---------|---------|---------|------|
| **P0** | US-001 | 被动 Webhook | MAC 地址漂移 | Demo 核心场景，MAC 漂移完整闭环 |
| **P0** | US-002 | 被动 Webhook | 端口 Down | 高频故障类型，必须覆盖 |
| **P0** | US-006 | — | 高风险审批 | 安全底线，无审批不执行高风险操作 |
| **P0** | US-007 | — | 审批中断/恢复 | LangGraph Interrupt 核心机制 |
| **P0** | US-008 | — | LLM 诊断 | LLM + RAG 核心能力 |
| **P0** | US-009 | — | 备份回滚 | 安全底线，无备份不执行变更 |
| **P0** | US-011 | — | 模板化管控 | 安全底线，禁止 LLM 自由生成命令 |
| **P1** | US-003 | 被动 Webhook | CPU 利用率过高 | Demo 场景，次于 P0 但必须具备 |
| **P1** | US-004 | 主动巡检 | 端口 Down | 巡检能力验证，预防性运维价值高 |
| **P1** | US-010 | — | 审计日志 | 可观测性需求，支持审计追溯 |
| **P2** | US-005 | 主动巡检 | CPU 利用率过高 | Demo 扩展场景，优先级最低 |

---

## 覆盖矩阵（Coverage Matrix）

| 维度 | 覆盖项 | 对应故事 |
|------|-------|---------|
| **告警类型** | MAC 地址漂移 | US-001 |
| **告警类型** | 端口 Down | US-002, US-004 |
| **告警类型** | CPU 利用率过高 | US-003, US-005 |
| **触发模式** | 被动 Webhook 触发 | US-001, US-002, US-003 |
| **触发模式** | 主动巡检触发 | US-004, US-005 |
| **关键流程** | 人工审批中断 | US-006 |
| **关键流程** | 审批恢复执行 | US-007 |
| **关键流程** | LLM 根因诊断 | US-008 |
| **关键流程** | 配置备份与回滚 | US-009 |
| **关键流程** | 审计日志 | US-010 |
| **关键流程** | 命令模板安全管控 | US-011 |
