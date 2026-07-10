<file_header>
  <author_agent>sub_agent_requirement_analyst</author_agent>
  <timestamp>2026-07-09T00:00:00Z</timestamp>
  <project_name>NetworkAgentDemo</project_name>
  <version>0.1.0</version>
  <input_files>
    <file>requirements/project_brief.md</file>
  </input_files>
  <phase>PHASE_01</phase>
  <status>APPROVED</status>
</file_header>

# 需求规格说明书 — NetworkAgentDemo

---

## 执行摘要

### 业务背景
本项目是基于 LangChain + LangGraph 的交换机巡检与故障自愈 Agent Demo，旨在演示典型网络运维闭环 Agent 场景：被动接收网管告警（模拟 Zabbix Webhook）+ 主动定期巡检，通过 LLM 推理完成故障诊断，最终根据模板化方案自动下发配置修复。核心设计原则为“模板化操作兜底 + LLM 灵活推理”，绝对禁止 LLM 自由生成设备配置命令以避免生产事故。

> 来源：project_brief.md 第3-8行（项目背景 + 核心设计原则）

### 需求总览
| 类别 | 数量 |
|------|------|
| 功能需求（REQ-FUNC-*） | 25 条 |
| 非功能需求（REQ-NFUNC-*） | 14 条 |
| 外部接口需求（IFC-*） | 3 条 |
| [INFERRED] 推断性需求 | 2 条（占比 5.1%，未超 10% 阈值） |
| 用户故事（US-*） | 11 条 |

### 推断性需求列表
| ID | 描述 | 推断依据 |
|----|------|----------|
| REQ-FUNC-005 | 告警有效性校验（去重、时效性检查） | 原文未明确提及校验细节，但“告警有效性校验”节点已列出，校验内容为合理推断 |
| REQ-NFUNC-014 | 诊断命令执行的超时时间（30s） | 原文要求“超时重试”但未指定具体超时值，Demo 场景下 30s 为合理推断 |

---

## 功能需求（Functional Requirements）

### 1. 触发层（Trigger Layer）

#### REQ-FUNC-001: Webhook 告警接收
| 字段 | 内容 |
|------|------|
| **ID** | REQ-FUNC-001 |
| **描述** | 系统应当通过 Webhook 接口接收网管系统（如 Zabbix）推送的设备告警，解析告警 Payload 并触发后续处理流程。 |
| **来源引用** | project_brief.md 第23-24行 — “触发层：对接网管系统，通过 Webhook 接收告警” |
| **优先级** | Must Have |
| **备注** | 无 |

#### REQ-FUNC-002: Mock 网管告警推送脚本
| 字段 | 内容 |
|------|------|
| **ID** | REQ-FUNC-002 |
| **描述** | 系统应当提供 Mock Webhook 脚本，能够模拟 Zabbix 格式的告警推送，以支持 Demo 场景下无需真实网管系统的独立运行。 |
| **来源引用** | project_brief.md 第16行 — “触发层：Mock Webhook（脚本模拟 Zabbix 告警推送）” |
| **优先级** | Must Have |
| **备注** | Demo 范围：Mock 实现 |

#### REQ-FUNC-003: 主动巡检定时触发
| 字段 | 内容 |
|------|------|
| **ID** | REQ-FUNC-003 |
| **描述** | 系统应当支持定时触发主动巡检任务，按可配置的时间间隔自动发起设备状态检查，检测异常后进入诊断修复流程。 |
| **来源引用** | project_brief.md 第23-24行 — “支持定时触发主动巡检” |
| **优先级** | Should Have |
| **备注** | 无 |

#### REQ-FUNC-004: 告警解析
| 字段 | 内容 |
|------|------|
| **ID** | REQ-FUNC-004 |
| **描述** | 系统应当解析接收到的告警数据，提取告警 ID（alert_id）、告警类型（alert_type）、告警内容（alert_content）、设备信息（device_info）等关键字段，填入 NetworkAgentState。 |
| **来源引用** | project_brief.md 第39-44行 — “告警解析”节点 + “NetworkAgentState(TypedDict)，字段包括：alert_id, alert_type, alert_content, device_info...” |
| **优先级** | Must Have |
| **备注** | 无 |

#### REQ-FUNC-005: 告警有效性校验
| 字段 | 内容 |
|------|------|
| **ID** | REQ-FUNC-005 |
| **描述** | 系统应当对解析后的告警进行有效性校验，包括告警去重（避免重复处理同一条告警）和时效性检查（忽略过期告警）。 |
| **来源引用** | project_brief.md 第47行 — “告警有效性校验”节点 |
| **优先级** | Must Have |
| **备注** | [INFERRED — requires PM confirmation] 原文仅列出节点名称，去重与时效性检查的具体逻辑为合理推断 |

### 2. Agent 编排层（Orchestration Layer）

#### REQ-FUNC-006: LangGraph 状态机编排
| 字段 | 内容 |
|------|------|
| **ID** | REQ-FUNC-006 |
| **描述** | 系统应当使用 LangGraph 构建有限状态机，按预定义节点流转顺序执行 "告警→诊断→修复→验证→闭环" 的完整运维流程，所有节点状态通过 NetworkAgentState(TypedDict) 管理。 |
| **来源引用** | project_brief.md 第17行 — “Agent 编排层：完整实现 LangGraph 状态机（含所有节点 + Interrupt 人工审批）” + 第39-48行 — LangGraph 状态机定义 |
| **优先级** | Must Have |
| **备注** | 无 |

#### REQ-FUNC-007: 获取设备信息
| 字段 | 内容 |
|------|------|
| **ID** | REQ-FUNC-007 |
| **描述** | 系统应当根据告警中携带的设备标识（device_info），从设备信息库中查询目标设备的 IP 地址、型号、管理凭据等连接所需信息。 |
| **来源引用** | project_brief.md 第47行 — “获取设备信息”节点 |
| **优先级** | Must Have |
| **备注** | 无 |

#### REQ-FUNC-008: 建立 SSH 连接
| 字段 | 内容 |
|------|------|
| **ID** | REQ-FUNC-008 |
| **描述** | 系统应当使用设备信息建立到目标网络设备的 SSH 连接，为后续诊断命令执行和配置下发提供通道。 |
| **来源引用** | project_brief.md 第47行 — “建立SSH连接”节点 |
| **优先级** | Must Have |
| **备注** | Demo 阶段工具层为 Mock 实现，真实 SSH 连接将在接入 TP-Link 交换机后启用 |

#### REQ-FUNC-009: 采集诊断信息
| 字段 | 内容 |
|------|------|
| **ID** | REQ-FUNC-009 |
| **描述** | 系统应当通过 SSH 连接在目标设备上执行诊断命令（如 show interface、show mac address-table、show processes cpu），采集设备实时状态数据，写入 diag_result 字段。 |
| **来源引用** | project_brief.md 第47行 — “采集诊断信息”节点 + 第32行 — “SwitchDiagTool：诊断命令执行” |
| **优先级** | Must Have |
| **备注** | 无 |

#### REQ-FUNC-010: LLM 根因分析 + 知识库检索
| 字段 | 内容 |
|------|------|
| **ID** | REQ-FUNC-010 |
| **描述** | 系统应当将采集到的诊断信息（diag_result）结合告警内容发送给 LLM 进行故障根因推理，同时通过 RAG 知识库检索匹配已知故障案例和处理预案，输出 root_cause 和 knowledge_refs。 |
| **来源引用** | project_brief.md 第47行 — “根因分析+知识库检索”节点 + 第33行 — “KnowledgeBaseTool：RAG 知识库检索” |
| **优先级** | Must Have |
| **备注** | 无 |

#### REQ-FUNC-011: 生成修复方案（模板匹配）
| 字段 | 内容 |
|------|------|
| **ID** | REQ-FUNC-011 |
| **描述** | 系统应当基于根因分析结果（root_cause），从预沉淀的命令模板库中匹配对应的修复方案模板，LLM 仅负责填充模板中的参数（如接口名称、VLAN ID），禁止自由生成设备配置命令。修复方案写入 fix_plan 字段。 |
| **来源引用** | project_brief.md 第8行 — “模板化操作兜底 + LLM 灵活推理，绝对禁止 LLM 自由生成设备配置命令” + 第47行 — “生成修复方案”节点 |
| **优先级** | Must Have |
| **备注** | 无 |

#### REQ-FUNC-012: 风险评估
| 字段 | 内容 |
|------|------|
| **ID** | REQ-FUNC-012 |
| **描述** | 系统应当对即将执行的修复方案进行风险评估，判断方案中是否包含高风险操作（如端口 shutdown、VLAN 删除、设备重启等），并设置 need_human_approval 标志。 |
| **来源引用** | project_brief.md 第47行 — “风险评估”节点 + 第53行 — “高风险必审批：端口 shutdown、VLAN 删除等强制人工审批” |
| **优先级** | Must Have |
| **备注** | 无 |

#### REQ-FUNC-013: 人工审批中断与恢复
| 字段 | 内容 |
|------|------|
| **ID** | REQ-FUNC-013 |
| **描述** | 当 need_human_approval = true 时，系统应当通过 LangGraph Interrupt 机制暂停状态机流转，等待运维人员审批（approval_status 设为 APPROVED 或 REJECTED）。审批通过后自动从断点恢复执行；审批拒绝则终止流程并记录。 |
| **来源引用** | project_brief.md 第17行 — “含 Interrupt 人工审批” + 第47行 — “人工审批”节点 + 第43行 — “approval_status”字段 |
| **优先级** | Must Have |
| **备注** | 无 |

#### REQ-FUNC-014: 执行修复
| 字段 | 内容 |
|------|------|
| **ID** | REQ-FUNC-014 |
| **描述** | 系统应当将经审批的修复方案（fix_plan）通过 SwitchConfigTool 下发到目标设备执行，执行过程记录在 exec_log 中，支持命令逐条下发与结果追踪。 |
| **来源引用** | project_brief.md 第47行 — “执行修复”节点 + 第31行 — “SwitchConfigTool：配置下发” |
| **优先级** | Must Have |
| **备注** | 无 |

#### REQ-FUNC-015: 结果验证
| 字段 | 内容 |
|------|------|
| **ID** | REQ-FUNC-015 |
| **描述** | 系统应当在修复执行后重新执行诊断命令，对比修复前后的设备状态，验证修复是否生效，结果写入 verify_result。 |
| **来源引用** | project_brief.md 第47行 — “结果验证”节点 |
| **优先级** | Must Have |
| **备注** | 无 |

#### REQ-FUNC-016: 生成报告 + 关闭告警
| 字段 | 内容 |
|------|------|
| **ID** | REQ-FUNC-016 |
| **描述** | 系统应当在修复验证通过后，汇总全流程信息（alert_id、root_cause、fix_plan、exec_log、verify_result）生成处理报告（final_report），并设置 status 为 CLOSED 以关闭告警。 |
| **来源引用** | project_brief.md 第47行 — “生成报告+关闭告警”节点 + 第43-44行 — “final_report, status”字段 |
| **优先级** | Must Have |
| **备注** | 无 |

### 3. 工具层（Tool Layer）

#### REQ-FUNC-017: SwitchConfigTool — 配置下发
| 字段 | 内容 |
|------|------|
| **ID** | REQ-FUNC-017 |
| **描述** | 系统应当封装交换机配置下发为标准 LangChain Tool，接口预留 NAPALM 适配层，Demo 阶段提供 Mock 实现，但接口签名应与真实 NAPALM 调用兼容，便于后续接入 TP-Link 交换机。 |
| **来源引用** | project_brief.md 第31行 — “SwitchConfigTool：配置下发（NAPALM）” + 第18行 — “工具层：全部 Mock 实现，但预留 TP-Link 交换机真实接口” |
| **优先级** | Must Have |
| **备注** | Demo：Mock 实现；预留 TP-Link SSH/CLI 接口 |

#### REQ-FUNC-018: SwitchDiagTool — 诊断命令执行
| 字段 | 内容 |
|------|------|
| **ID** | REQ-FUNC-018 |
| **描述** | 系统应当封装交换机诊断命令执行为标准 LangChain Tool，接口预留 Netmiko 适配层，Demo 阶段提供 Mock 实现。支持执行 show 类诊断命令并返回结构化输出。 |
| **来源引用** | project_brief.md 第32行 — “SwitchDiagTool：诊断命令执行（Netmiko）” + 第18行 — “工具层：全部 Mock 实现” |
| **优先级** | Must Have |
| **备注** | Demo：Mock 实现；预留 TP-Link SSH/CLI 接口 |

#### REQ-FUNC-019: KnowledgeBaseTool — RAG 知识库检索
| 字段 | 内容 |
|------|------|
| **ID** | REQ-FUNC-019 |
| **描述** | 系统应当封装 RAG 知识库检索为标准 LangChain Tool，支持根据告警类型和诊断结果检索匹配的历史故障案例、厂商命令模板和处理预案。 |
| **来源引用** | project_brief.md 第33行 — “KnowledgeBaseTool：RAG 知识库检索” |
| **优先级** | Must Have |
| **备注** | 无 |

#### REQ-FUNC-020: BackupTool — 配置备份与回滚
| 字段 | 内容 |
|------|------|
| **ID** | REQ-FUNC-020 |
| **描述** | 系统应当封装配置备份与回滚为标准 LangChain Tool，在执行修复前自动备份设备 running-config（config_backup 字段），修复失败时支持基于备份配置的自动回滚。 |
| **来源引用** | project_brief.md 第34行 — “BackupTool：配置备份与回滚” + 第52行 — “配置必备份：修改前自动备份 running-config” |
| **优先级** | Must Have |
| **备注** | Demo：Mock 实现 |

### 4. 资源层（Resource Layer）

#### REQ-FUNC-021: 命令模板管理
| 字段 | 内容 |
|------|------|
| **ID** | REQ-FUNC-021 |
| **描述** | 系统应当预沉淀各厂商交换机命令模板（含 TP-Link Cisco IOS 风格命令），模板中定义参数占位符，LLM 仅能选取和填充模板参数，绝对禁止自由生成设备配置命令。 |
| **来源引用** | project_brief.md 第36-37行 — “资源层：预沉淀各厂商交换机命令模板、故障处理预案” + 第51行 — “命令模板化：LLM 只能填参数，禁止自由生成命令” |
| **优先级** | Must Have |
| **备注** | 无 |

#### REQ-FUNC-022: 故障处理预案
| 字段 | 内容 |
|------|------|
| **ID** | REQ-FUNC-022 |
| **描述** | 系统应当在资源层预沉淀常见网络故障的处理预案，将故障特征与修复方案模板建立映射关系，供根因分析阶段检索和匹配合适的修复模板。 |
| **来源引用** | project_brief.md 第36-37行 — “预沉淀各厂商交换机命令模板、故障处理预案” |
| **优先级** | Must Have |
| **备注** | 无 |

### 5. 告警类型覆盖

#### REQ-FUNC-023: MAC 地址漂移告警处理
| 字段 | 内容 |
|------|------|
| **ID** | REQ-FUNC-023 |
| **描述** | 系统应当支持 MAC 地址漂移（MAC Flapping）告警的完整闭环处理：从告警接入、诊断（show mac address-table）、根因分析、修复方案生成，到人工审批、执行与验证、报告关闭。 |
| **来源引用** | project_brief.md 第20行 — “告警类型覆盖：MAC 地址漂移” + 第58-59行 — “典型场景：MAC 地址漂移完整闭环” |
| **优先级** | Must Have |
| **备注** | Demo 核心场景 |

#### REQ-FUNC-024: 端口 Down 告警处理
| 字段 | 内容 |
|------|------|
| **ID** | REQ-FUNC-024 |
| **描述** | 系统应当支持端口 Down（Interface Down）告警的完整闭环处理：从告警接入、诊断（show interface）、根因分析、修复方案生成，到人工审批、执行与验证、报告关闭。 |
| **来源引用** | project_brief.md 第20行 — “告警类型覆盖：端口 Down” |
| **优先级** | Must Have |
| **备注** | Demo 场景 |

#### REQ-FUNC-025: CPU 利用率过高告警处理
| 字段 | 内容 |
|------|------|
| **ID** | REQ-FUNC-025 |
| **描述** | 系统应当支持 CPU 利用率过高（CPU Utilization High）告警的完整闭环处理：从告警接入、诊断（show processes cpu）、根因分析、修复方案生成，到人工审批、执行与验证、报告关闭。 |
| **来源引用** | project_brief.md 第20行 — “告警类型覆盖：CPU 利用率过高” |
| **优先级** | Should Have |
| **备注** | Demo 场景 |

---

## 非功能需求（Non-Functional Requirements）

### 1. 安全合规（Security & Compliance）

#### REQ-NFUNC-001: 禁止 LLM 自由生成设备配置命令
| 字段 | 内容 |
|------|------|
| **ID** | REQ-NFUNC-001 |
| **描述** | 系统应当从机制层面确保 LLM 不能自由生成设备配置命令，所有配置操作必须基于预定义命令模板，LLM 仅负责从模板库中选择匹配模板并填充参数。 |
| **来源引用** | project_brief.md 第8行 — “绝对禁止 LLM 自由生成设备配置命令，避免生产事故” + 第51行 — “命令模板化：LLM 只能填参数，禁止自由生成命令” |
| **优先级** | Must Have |
| **强制等级** | CRITICAL |

#### REQ-NFUNC-002: LLM 仅填充模板参数
| 字段 | 内容 |
|------|------|
| **ID** | REQ-NFUNC-002 |
| **描述** | 系统应当确保 LLM 的输出仅限于模板参数值（如接口名称、VLAN ID、描述文本），不得包含完整的 CLI 命令语法或配置语句。 |
| **来源引用** | project_brief.md 第51行 — “LLM 只能填参数，禁止自由生成命令” |
| **优先级** | Must Have |
| **强制等级** | CRITICAL |

#### REQ-NFUNC-003: 高风险操作强制人工审批
| 字段 | 内容 |
|------|------|
| **ID** | REQ-NFUNC-003 |
| **描述** | 系统应当对高风险操作（包括但不限于：端口 shutdown、VLAN 删除、设备重启、路由协议变更）强制触发人工审批流程，未经审批通过不得下发执行。 |
| **来源引用** | project_brief.md 第53行 — “高风险必审批：端口 shutdown、VLAN 删除等强制人工审批” |
| **优先级** | Must Have |
| **强制等级** | CRITICAL |

#### REQ-NFUNC-004: 最小权限账号
| 字段 | 内容 |
|------|------|
| **ID** | REQ-NFUNC-004 |
| **描述** | 系统连接网络设备应当使用最小权限账号，仅授予诊断和修复所需的最小命令集权限，禁止使用 root/administrator 全权限账号。 |
| **来源引用** | project_brief.md 第54行 — “最小权限账号” |
| **优先级** | Must Have |
| **强制等级** | HIGH |

### 2. 可靠性（Reliability）

#### REQ-NFUNC-005: 配置修改前自动备份
| 字段 | 内容 |
|------|------|
| **ID** | REQ-NFUNC-005 |
| **描述** | 系统应当在任何配置修改操作执行前，自动备份目标设备的 running-config 到 config_backup 字段，备份成功后才允许继续执行修复。 |
| **来源引用** | project_brief.md 第52行 — “配置必备份：修改前自动备份 running-config” |
| **优先级** | Must Have |
| **备注** | 无 |

#### REQ-NFUNC-006: 自动回滚
| 字段 | 内容 |
|------|------|
| **ID** | REQ-NFUNC-006 |
| **描述** | 当修复执行失败或结果验证未通过时，系统应当自动基于 config_backup 执行配置回滚，将设备恢复到修复前的状态。 |
| **来源引用** | project_brief.md 第55行 — “自动回滚” |
| **优先级** | Must Have |
| **备注** | 无 |

#### REQ-NFUNC-007: 超时重试
| 字段 | 内容 |
|------|------|
| **ID** | REQ-NFUNC-007 |
| **描述** | 系统应当对网络操作（SSH 连接、命令执行、配置下发）设置超时机制，超时后自动重试，重试上限可配置，超过上限则标记失败并触发回滚或告警升级。 |
| **来源引用** | project_brief.md 第55行 — “超时重试” |
| **优先级** | Must Have |
| **备注** | 无 |

#### REQ-NFUNC-008: 幂等设计
| 字段 | 内容 |
|------|------|
| **ID** | REQ-NFUNC-008 |
| **描述** | 系统的修复执行应当支持幂等操作，同一修复方案多次执行不会导致配置重复叠加或设备状态异常。 |
| **来源引用** | project_brief.md 第55行 — “幂等设计” |
| **优先级** | Should Have |
| **备注** | 无 |

#### REQ-NFUNC-009: 灰度执行（可选）
| 字段 | 内容 |
|------|------|
| **ID** | REQ-NFUNC-009 |
| **描述** | 对于影响范围较大的修复操作，系统宜支持灰度执行策略，先在低风险设备或非关键端口上验证修复方案，确认无误后再扩大执行范围。 |
| **来源引用** | project_brief.md 第55行 — “灰度执行” |
| **优先级** | Could Have |
| **备注** | Demo 阶段不强制实现 |

### 3. 可观测性（Observability）

#### REQ-NFUNC-010: 全链路操作日志
| 字段 | 内容 |
|------|------|
| **ID** | REQ-NFUNC-010 |
| **描述** | 系统应当记录全链路操作日志，覆盖从告警接收到报告关闭的每一步操作，日志内容包括时间戳、节点名称、输入数据、输出数据、异常信息。 |
| **来源引用** | project_brief.md 第56行 — “全链路日志与操作审计” |
| **优先级** | Must Have |
| **备注** | 无 |

#### REQ-NFUNC-011: 操作审计追踪
| 字段 | 内容 |
|------|------|
| **ID** | REQ-NFUNC-011 |
| **描述** | 系统应当对关键操作（特别是配置下发和人工审批决策）生成不可篡改的审计追踪记录，包括操作人（或系统标识）、操作时间、操作内容和结果。 |
| **来源引用** | project_brief.md 第56行 — “全链路日志与操作审计” |
| **优先级** | Must Have |
| **备注** | 无 |

### 4. 平台与接口约束

#### REQ-NFUNC-012: 目标操作系统 Linux
| 字段 | 内容 |
|------|------|
| **ID** | REQ-NFUNC-012 |
| **描述** | 系统的运行环境目标操作系统为 Linux，所有依赖组件和工具链应当兼容 Linux 环境。 |
| **来源引用** | project_brief.md 第12行 — “目标操作系统：Linux” |
| **优先级** | Must Have |
| **备注** | 无 |

#### REQ-NFUNC-013: LLM 调用约束（DeepSeek API）
| 字段 | 内容 |
|------|------|
| **ID** | REQ-NFUNC-013 |
| **描述** | 系统的 LLM 调用应当使用 openai Python SDK，base_url 指向 DeepSeek API 端点，模型指定为 deepseek-chat。 |
| **来源引用** | project_brief.md 第11行 — “LLM：使用 openai Python SDK，base_url 指向 DeepSeek API，模型使用 deepseek-chat” |
| **优先级** | Must Have |
| **备注** | 无 |

#### REQ-NFUNC-014: TP-Link 交换机接口预留
| 字段 | 内容 |
|------|------|
| **ID** | REQ-NFUNC-014 |
| **描述** | 系统的工具层 Mock 实现应当预留 TP-Link 交换机的真实接口适配层，TP-Link 通过 SSH/CLI 协议管理，命令风格接近 Cisco IOS。Demo 阶段以 Mock 方式返回模拟数据，接口签名需与真实实现一致。 |
| **来源引用** | project_brief.md 第13行 — “后期会用真实 TP-Link 交换机替换 Mock 层（TP-Link 通常用 SSH/CLI，命令风格接近 Cisco IOS）” + 第18行 — “工具层：全部 Mock 实现，但预留 TP-Link 交换机真实接口” |
| **优先级** | Must Have |
| **备注** | [INFERRED — requires PM confirmation] 接口签名一致性要求在原文中为隐含约束，明确为合理推断 |

---

## 外部接口需求（External Interface Requirements）

### IFC-001: Webhook 告警 Payload Schema

| 字段 | 内容 |
|------|------|
| **接口名称** | Alert Webhook Payload |
| **协议** | HTTP POST (JSON) |
| **来源** | project_brief.md 第16行 — “Mock Webhook（脚本模拟 Zabbix 告警推送）” + 第23行 — “通过 Webhook 接收告警” |
| **Schema** |  |

```json
{
  "alert_id": "string (UUID)",
  "alert_type": "string (enum: MAC_FLAPPING | PORT_DOWN | CPU_HIGH)",
  "alert_severity": "string (enum: CRITICAL | MAJOR | MINOR | WARNING)",
  "alert_content": "string (human-readable description)",
  "alert_timestamp": "string (ISO8601)",
  "device_info": {
    "device_name": "string",
    "device_ip": "string",
    "device_model": "string (optional)",
    "interface_name": "string (optional, for PORT_DOWN)",
    "mac_address": "string (optional, for MAC_FLAPPING)",
    "cpu_percent": "number (optional, for CPU_HIGH)"
  },
  "source": "string (enum: ZABBIX | MOCK)"
}
```

### IFC-002: LLM API 调用契约

| 字段 | 内容 |
|------|------|
| **接口名称** | DeepSeek Chat Completion API |
| **协议** | OpenAI-compatible Chat Completions API (HTTP POST) |
| **来源** | project_brief.md 第11行 — “使用 openai Python SDK，base_url 指向 DeepSeek API，模型使用 deepseek-chat” |
| **约束** |  |

| 参数 | 值 |
|------|-----|
| SDK | openai Python SDK |
| base_url | DeepSeek API 端点（如 `https://api.deepseek.com/v1`） |
| model | `deepseek-chat` |
| temperature | 0.1（需求分析阶段确定性优先） |
| 调用场景 | 告警解析、根因分析、模板参数填充、报告摘要生成 |

### IFC-003: 工具层接口签名

| 工具名称 | 输入参数 | 输出 |
|----------|---------|------|
| SwitchConfigTool | `device_ip: str, commands: list[str], auth: dict` | `{success: bool, output: str, error: str|null}` |
| SwitchDiagTool | `device_ip: str, command: str, auth: dict` | `{success: bool, output: str, error: str|null}` |
| KnowledgeBaseTool | `query: str, alert_type: str` | `{matches: list[{title, content, relevance}], count: int}` |
| BackupTool | `device_ip: str, auth: dict, operation: enum(BACKUP|ROLLBACK)` | `{success: bool, backup_id: str, config: str|null, error: str|null}` |

> 来源：project_brief.md 第30-34行 — “工具层：所有外部系统交互封装成 LangChain 标准 Tool”
> 备注：以上为逻辑接口签名，具体实现签名由 GROUP_B 在 module_design.md 中细化。

---

## Demo 范围边界表

| 层次 | 组件 | Demo 实现策略 | 说明 |
|------|------|-------------|------|
| **触发层** | Webhook 告警接收 | **Mock 实现** | 通过脚本模拟 Zabbix 格式的 HTTP POST 推送，内嵌 3 种告警类型（MAC 漂移、端口 Down、CPU 过高）的样本数据 |
| **触发层** | 主动巡检定时器 | **真实实现** | 基于标准调度库的定时触发（APScheduler 或类似方案） |
| **编排层** | LangGraph 状态机 | **真实实现** | 完整实现所有 14 个节点的状态流转，含 Interrupt 人工审批机制 |
| **编排层** | LLM 故障诊断 | **真实 API 调用** | 通过 openai SDK 调用 DeepSeek deepseek-chat 模型进行根因分析 |
| **编排层** | 人工审批流程 | **真实实现** | 通过 LangGraph Interrupt 暂停/恢复实现，审批接口通过 CLI 或简单 Web 界面模拟 |
| **工具层** | SwitchConfigTool | **Mock 实现** | 不真实连接交换机，返回模拟执行结果；**预留 TP-Link SSH/CLI 接口**（接口签名与 NAPALM 兼容） |
| **工具层** | SwitchDiagTool | **Mock 实现** | 返回对应告警类型的模拟诊断数据；**预留 TP-Link SSH/CLI 接口**（接口签名与 Netmiko 兼容） |
| **工具层** | KnowledgeBaseTool | **Mock 实现** | 内嵌少量示例知识条目（MAC 漂移、端口 Down、CPU 过高的故障案例和预案） |
| **工具层** | BackupTool | **Mock 实现** | 模拟配置备份（返回模拟 running-config 文本）和回滚操作；**预留 TP-Link SSH/CLI 接口** |
| **资源层** | 命令模板库 | **真实实现** | 预定义 JSON/YAML 格式的 TP-Link（Cisco IOS 风格）命令模板，含参数占位符 |
| **资源层** | 故障预案库 | **Mock 实现** | 内嵌 3 种告警类型的示例预案，作为 RAG 知识库的数据源 |
| **报告** | 处理报告生成 | **真实实现** | 由 LLM 汇总全流程数据生成结构化报告 |

> 来源：project_brief.md 第15-20行 — “Demo 范围策略”

---

## 需求追踪矩阵

| 需求 ID | 需求描述（摘要） | 来源章节 | 关联用户故事 |
|---------|---------------|---------|------------|
| REQ-FUNC-001 | Webhook 告警接收 | 架构分层—触发层 | US-001, US-002, US-003 |
| REQ-FUNC-002 | Mock 网管告警推送脚本 | Demo 范围策略—触发层 | US-001, US-002, US-003 |
| REQ-FUNC-003 | 主动巡检定时触发 | 架构分层—触发层 | US-004, US-005 |
| REQ-FUNC-004 | 告警解析 | LangGraph 状态机 | US-001, US-002, US-003, US-004, US-005 |
| REQ-FUNC-005 | 告警有效性校验 [INFERRED] | LangGraph 状态机 | US-001, US-002, US-003 |
| REQ-FUNC-006 | LangGraph 状态机编排 | Demo 范围策略 + LangGraph 状态机 | US-001~US-011 |
| REQ-FUNC-007 | 获取设备信息 | LangGraph 状态机 | US-001, US-002, US-003 |
| REQ-FUNC-008 | 建立 SSH 连接 | LangGraph 状态机 | US-001~US-005 |
| REQ-FUNC-009 | 采集诊断信息 | LangGraph 状态机 + 工具层 | US-001, US-002, US-003 |
| REQ-FUNC-010 | LLM 根因分析+知识库检索 | LangGraph 状态机 + 工具层 | US-008 |
| REQ-FUNC-011 | 生成修复方案（模板匹配） | 核心设计原则 + LangGraph 状态机 | US-006, US-008, US-011 |
| REQ-FUNC-012 | 风险评估 | LangGraph 状态机 + 安全与可靠性 | US-006 |
| REQ-FUNC-013 | 人工审批中断与恢复 | Demo 范围策略 + LangGraph 状态机 | US-006, US-007 |
| REQ-FUNC-014 | 执行修复 | LangGraph 状态机 + 工具层 | US-006, US-007 |
| REQ-FUNC-015 | 结果验证 | LangGraph 状态机 | US-001~US-005 |
| REQ-FUNC-016 | 生成报告+关闭告警 | LangGraph 状态机 | US-001~US-005 |
| REQ-FUNC-017 | SwitchConfigTool | 工具层 | US-006, US-007 |
| REQ-FUNC-018 | SwitchDiagTool | 工具层 | US-001~US-005 |
| REQ-FUNC-019 | KnowledgeBaseTool | 工具层 | US-008 |
| REQ-FUNC-020 | BackupTool | 工具层 | US-009 |
| REQ-FUNC-021 | 命令模板管理 | 资源层 + 安全与可靠性 | US-011 |
| REQ-FUNC-022 | 故障处理预案 | 资源层 | US-008 |
| REQ-FUNC-023 | MAC 地址漂移告警处理 | Demo 范围策略 + 典型场景 | US-001 |
| REQ-FUNC-024 | 端口 Down 告警处理 | Demo 范围策略 | US-002, US-004 |
| REQ-FUNC-025 | CPU 利用率过高告警处理 | Demo 范围策略 | US-003, US-005 |
| REQ-NFUNC-001 | 禁止 LLM 自由生成命令 | 核心设计原则 + 安全与可靠性 | US-011 |
| REQ-NFUNC-002 | LLM 仅填充模板参数 | 安全与可靠性 | US-011 |
| REQ-NFUNC-003 | 高风险操作强制人工审批 | 安全与可靠性 | US-006 |
| REQ-NFUNC-004 | 最小权限账号 | 安全与可靠性 | 基础设施 |
| REQ-NFUNC-005 | 配置修改前自动备份 | 安全与可靠性 | US-009 |
| REQ-NFUNC-006 | 自动回滚 | 安全与可靠性 | US-009 |
| REQ-NFUNC-007 | 超时重试 | 安全与可靠性 | 基础设施 |
| REQ-NFUNC-008 | 幂等设计 | 安全与可靠性 | 基础设施 |
| REQ-NFUNC-009 | 灰度执行 | 安全与可靠性 | 基础设施 |
| REQ-NFUNC-010 | 全链路操作日志 | 安全与可靠性 | US-010 |
| REQ-NFUNC-011 | 操作审计追踪 | 安全与可靠性 | US-010 |
| REQ-NFUNC-012 | 目标操作系统 Linux | 技术约束 | 基础设施 |
| REQ-NFUNC-013 | LLM API 约束 | 技术约束 | US-008 |
| REQ-NFUNC-014 | TP-Link 接口预留 [INFERRED] | 技术约束 + Demo 范围策略 | 基础设施 |

---

## 超出范围（Out of Scope）

以下内容明确不在本 Demo 范围内：

| 编号 | 排除项 | 依据 |
|------|-------|------|
| OOS-001 | 真实 Zabbix/网管系统对接 | project_brief.md — Demo 使用 Mock Webhook |
| OOS-002 | 真实物理交换机操作 | project_brief.md — 工具层全 Mock；TP-Link 预留接口待后续阶段接入 |
| OOS-003 | 多厂商交换机适配（除 TP-Link 外） | project_brief.md — 仅提及 TP-Link |
| OOS-004 | 生产级高可用部署 | project_brief.md — Demo 项目，未提及 HA 要求 |
| OOS-005 | 多租户或多用户权限管理 | project_brief.md — 未提及 |
| OOS-006 | 移动端审批界面 | project_brief.md — 审批通过 CLI/简单 Web 界面模拟 |

---

## 待确认推断项

| ID | 内容 | 建议 PM 关注 |
|----|------|------------|
| REQ-FUNC-005 | 告警有效性校验包含去重和时效性检查 | 原文仅列出节点名称，请确认校验范围是否合理 |
| REQ-NFUNC-014 | TP-Link 接口签名的 Mock 与真实实现一致性要求 | 原文隐含此约束，请确认是否需要明确接口契约 |

---

## 开放问题

| 编号 | 问题 | 状态 |
|------|------|------|
| Q-001 | 主动巡检的时间间隔是多少？（原文未指定，Demo 阶段建议默认 5 分钟） | 待 PM 确认 |
| Q-002 | 人工审批超时策略？（若运维人员长时间未响应审批，系统应如何处理） | 待 PM 确认 |
| Q-003 | Mock 层中 TP-Link 接口预留的具体形式？（抽象接口类 / 策略模式 / 依赖注入）— 此为 GROUP_B 决策范围 | 交由 GROUP_B |
