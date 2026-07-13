<file_header>
  <project_name>NetworkAgentDemo</project_name>
  <component>data_persistence</component>
  <phase>PHASE_DP_01 + PHASE_DP_02</phase>
  <group>GROUP_DP_A</group>
  <version>0.1.0</version>
  <status>DRAFT</status>
  <author>sub_agent_requirement_analyst</author>
  <created_at>2026-07-14T00:00:00Z</created_at>
  <invocation_id>GROUP_DP_A</invocation_id>
</file_header>

# 数据持久化修复 — 用户故事清单

## 用户角色地图（Actor x Feature Matrix）

| Actor | fix_plan 持久化 | LLM 日志持久化 | 审批数据读取 | 审批查询方法 | 工作流状态持久化 | API 兼容性 |
|-------|:---:|:---:|:---:|:---:|:---:|:---:|
| 系统运维人员 | US-001 | US-002 | US-003 | — | US-005 | — |
| 开发调试人员 | — | US-002 | US-003 | US-004 | US-005 | — |
| 前端开发/API 消费者 | — | — | US-003 | — | — | US-006 |

---

## 用户故事详情

---

### US-001：修复方案（fix_plan）持久化存储

- **用户故事**：As a 系统运维人员，I want 工作流生成的修复方案被持久化存储到数据库，so that 服务器重启后我仍能查看所有告警（包括低风险告警）的修复方案内容。
- **关联需求**：REQ-FUNC-001
- **优先级**：Must Have
- **故事点**：[INFERRED — 待开发团队评估]

**验收标准：**

- **AC-001-01**
  - Given 系统收到一个新的网络告警并开始处理
  - When 工作流执行 generate_fix_plan 节点并生成修复方案
  - Then fix_plan 的完整内容（template_id、description、params、commands）被写入数据库持久化存储

- **AC-001-02**
  - Given 一个已处理的告警，其 fix_plan 已持久化到数据库
  - When 服务器重启后，运维人员通过 Web UI 请求该告警的详情（GET /api/alerts/{alert_id}）
  - Then API 响应中包含完整的 fix_plan 字段，数据来源于数据库而非内存

- **AC-001-03**
  - Given 一个低风险告警（risk_level=LOW，无需人工审批）的工作流生成了 fix_plan
  - When fix_plan 被持久化
  - Then 该低风险告警的 fix_plan 与高风险告警一样被完整存储，服务器重启后仍可检索

- **AC-001-04**
  - Given 数据库中存在一条在数据持久化修复前创建的告警记录（无 fix_plan 数据）
  - When 运维人员通过 GET /api/alerts/{alert_id} 请求该旧告警的详情
  - Then API 响应中 fix_plan 字段返回 null 或空对象，不产生错误，不破坏整体响应结构

---

### US-002：LLM 调用详情持久化存储

- **用户故事**：As a 开发调试人员，I want 每次 LLM 调用的详细记录被持久化存储，so that 在服务器重启后我仍能追溯历史告警处理过程中的 LLM 行为，便于问题排查和成本统计。
- **关联需求**：REQ-FUNC-002
- **优先级**：Must Have
- **故事点**：[INFERRED — 待开发团队评估]

**验收标准：**

- **AC-002-01**
  - Given 一个告警的工作流触发了多次 LLM 调用（如 analyze_root_cause、fill_template_params、generate_report）
  - When 每次 LLM 调用完成（DeepSeek API 返回响应或 Mock 模式返回）
  - Then 该次调用的记录（包含 endpoint、timestamp、elapsed_s、prompt_tokens、completion_tokens、prompt 摘要、response 摘要）被写入数据库持久化存储，且可通过 alert_id 关联到对应的告警

- **AC-002-02**
  - Given 多轮 LLM 调用记录已持久化到数据库
  - When 开发人员通过 GET /api/alerts/{alert_id} 请求告警详情
  - Then API 响应中 llm_calls 字段包含该告警关联的所有 LLM 调用记录，数据来源于数据库而非 LLMService._llm_call_log 内存字典

- **AC-002-03**
  - Given 服务器发生了重启，LLMService._llm_call_log 内存字典内容已丢失
  - When 开发人员请求一个在重启前已处理完成的告警的详情
  - Then 该告警的 LLM 调用记录仍然完整可查，所有数据从数据库加载

- **AC-002-04**
  - Given 一个告警在 Mock 模式下处理（无 DEEPSEEK_API_KEY，LLM 使用 _mock_response）
  - When LLM mock 调用完成
  - Then Mock 调用的记录同样被持久化，endpoint 字段标识为 mock，便于区分真实调用与模拟调用

---

### US-003：告警详情 API 从数据库读取审批信息

- **用户故事**：As a 系统运维人员，I want 告警详情页面展示的审批信息来源于数据库（approvals 表），so that 审批记录准确反映实际数据库中存储的决策结果，而非临时的内存状态。
- **关联需求**：REQ-FUNC-003
- **优先级**：Must Have
- **故事点**：[INFERRED — 待开发团队评估]

**验收标准：**

- **AC-003-01**
  - Given 数据库中 approvals 表存在一条已完成审批决策的记录（decision=APPROVED 或 REJECTED）
  - When GET /api/alerts/{alert_id} 被调用
  - Then API 响应的 approval 字段包括 need_human_approval、approval_status、risk_level、decision、decided_by、decided_at、note，且所有值均从 approvals 表查询，不使用 MemorySaver 中的 state

- **AC-003-02**
  - Given 一个被拒绝的告警（decision=REJECTED），审批人在拒绝时填写了备注原因
  - When 运维人员查看该告警详情
  - Then API 响应中 approval.note 字段展示审批人填写的拒绝原因，approval.decision 为 "REJECTED"，approval.decided_at 为实际审批时间

- **AC-003-03**
  - Given 系统中存在多个告警，每个告警有各自独立的审批记录
  - When 分别请求不同告警的详情
  - Then 每个告警返回的 approval 信息仅对应该告警自身的审批记录，不会出现跨告警的审批数据混淆

- **AC-003-04**
  - Given 某告警不需要人工审批（need_human_approval=false，风险等级为 LOW）
  - When GET /api/alerts/{alert_id} 被调用
  - Then API 响应的 approval 字段返回空对象或明确标识无审批需求（如 approval_status="NOT_REQUIRED"），不产生错误

---

### US-004：ApprovalRepository 支持按 alert_id 查询审批记录

- **用户故事**：As a 开发调试人员（或 API 消费者），I want 能够通过 alert_id 查询关联的所有审批记录，so that 告警详情 API 可以直接从数据库获取审批数据，无需依赖 MemorySaver。
- **关联需求**：REQ-FUNC-004
- **优先级**：Must Have
- **故事点**：[INFERRED — 待开发团队评估]

**验收标准：**

- **AC-004-01**
  - Given approvals 表中存在一条或多条 alert_id_fk 等于指定 alert_id 的审批记录
  - When ApprovalRepository 调用 get_approvals_by_alert_id(alert_id)
  - Then 返回包含所有匹配审批记录的列表，每条记录包含完整的 Approval 对象属性（checkpoint_id, fix_plan, risk_level, decision, decided_by, decided_at, note, created_at）

- **AC-004-02**
  - Given approvals 表中不存在任何 alert_id_fk 等于指定 alert_id 的审批记录
  - When ApprovalRepository 调用 get_approvals_by_alert_id(alert_id)
  - Then 返回空列表，不抛出异常

- **AC-004-03**
  - Given 系统中有多个告警各有审批记录
  - When 调用 get_approvals_by_alert_id("alert-A") 
  - Then 只返回 alert_id_fk 严格等于 "alert-A" 的审批记录，不包含其他告警的审批记录

- **AC-004-04**
  - Given 新方法 get_approvals_by_alert_id 已实现
  - When 告警详情 API（GET /api/alerts/{alert_id}）构建 approval 响应字段
  - Then 该 API 通过 ApprovalRepository 的新方法查询审批数据，不再通过 sys.modules 获取 main_module 后访问 state_graph_engine.get_workflow_state()

---

### US-005：工作流状态完整持久化

- **用户故事**：As a 系统运维人员，I want 工作流执行过程中产生的 root_cause、diag_result、exec_log、verify_result、final_report 等关键状态数据被持久化存储，so that 服务器重启后我仍能查看完整的告警处理历史。
- **关联需求**：REQ-FUNC-005
- **优先级**：Must Have
- **故事点**：[INFERRED — 待开发团队评估]

**验收标准：**

- **AC-005-01**
  - Given 一个告警的工作流完整执行结束（finish_report 节点完成）
  - When 工作流结束时
  - Then root_cause、diag_result、exec_log、verify_result、final_report 五个字段的全部内容被写入数据库，且与内存中的 NetworkAgentState 值一致

- **AC-005-02**
  - Given 服务器发生了重启，MemorySaver 中所有工作流状态已丢失
  - When 运维人员通过 GET /api/alerts/{alert_id} 请求一个已处理完成的告警详情
  - Then API 响应中包含 root_cause、diag_result、exec_log、verify_result、final_report 字段，数据来源于数据库

- **AC-005-03**
  - Given 一个正在处理中的告警，其工作流尚未执行到 collect_diag 节点 [INFERRED — requires PM confirmation]
  - When 运维人员通过 GET /api/alerts/{alert_id} 请求该告警详情
  - Then 尚未生成的字段（如 diag_result、root_cause、exec_log）在 API 响应中返回 null 或空值，不产生错误

- **AC-005-04**
  - Given 一个工作流在 analyze_root_cause 节点执行失败（LLM 调用异常），后续节点未执行 [INFERRED — requires PM confirmation]
  - When 运维人员请求该告警详情
  - Then API 响应中仅返回已成功生成的状态字段（如 diag_result），未生成的字段（如 fix_plan、exec_log）返回 null 或空值

- **AC-005-05**
  - Given exec_log 是一个命令执行记录的列表（字典数组）
  - When exec_log 被持久化到数据库
  - Then 每条记录的 command、success、output、error、execution_time_ms、was_idempotent_skip 字段完整保留，列表顺序与内存中一致

---

### US-006：告警详情 API 保持向后兼容

- **用户故事**：As a 前端开发人员（API 消费者），I want GET /api/alerts/{alert_id} 接口在数据源切换为数据库后保持完全相同的响应结构和字段名，so that 现有前端代码无需任何修改即可正常工作。
- **关联需求**：REQ-FUNC-006、REQ-NFUNC-003
- **优先级**：Must Have
- **故事点**：[INFERRED — 待开发团队评估]

**验收标准：**

- **AC-006-01**
  - Given 数据持久化修复已完成（API 数据源从内存切换为数据库）
  - When 前端调用 GET /api/alerts/{alert_id}
  - Then 响应的顶层 JSON 结构保持为 `{"alert", "timeline", "fix_plan", "commands", "llm_calls", "approval"}`，六个字段全部存在，字段名不变

- **AC-006-02**
  - Given 数据持久化修复已完成
  - When 前端请求一个存在且已处理完成的告警（alert_id 有效）
  - Then API 返回 HTTP 200，响应中 fix_plan 字段包含 template_id、description、params；commands 字段为字符串数组；llm_calls 字段为对象数组（含 endpoint、timestamp、elapsed_s 等）；approval 字段包含 need_human_approval、approval_status、risk_level

- **AC-006-03**
  - Given 数据持久化修复已完成
  - When 前端请求一个不存在的 alert_id
  - Then API 返回 HTTP 404，响应体为 `{"detail": "告警不存在"}`，与修复前的行为完全一致

- **AC-006-04**
  - Given 数据库连接正常但某告警在数据库中没有任何审批记录（尚未生成或不需要审批）
  - When GET /api/alerts/{alert_id} 被调用
  - Then API 仍返回 HTTP 200，approval 字段返回 null 或空对象，不因缺少审批记录而返回 500 或异常响应
