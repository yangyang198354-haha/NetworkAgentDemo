<file_header>
  <project_id>NetworkAgentDemo</project_id>
  <module_id>real_device_e2e</module_id>
  <doc_type>user_stories</doc_type>
  <file_name>real_device_e2e_user_stories.md</file_name>
  <version>0.2.0</version>
  <status>APPROVED</status>
  <author_agent>sub_agent_requirement_analyst</author_agent>
  <created_at>2026-09-05T03:00:00Z</created_at>
  <last_updated>2026-09-05T03:10:00Z</last_updated>
  <invocation_id>inv-real-e2e-a-002</invocation_id>
  <input_source>PM agent_invocation — 用户已确认决策（Q-RE-01/02/03 RESOLVED）定稿修订</input_source>
</file_header>

# 真实设备（REAL）端到端工作流 — 用户故事清单

## 用户角色地图（Actor x Feature Matrix）

| Actor \ Feature | 模拟告警 | 真实诊断 | 真实修复 | 真实验证收敛 | 写操作授权 | 凭据安全 | 兼容性 |
|-----------------|----------|----------|----------|--------------|-----------|----------|--------|
| 运维工程师 | US-RE-001 | US-RE-002 | US-RE-003 | US-RE-004 | US-RE-005 | — | — |
| 安全/系统管理员 | — | — | — | — | US-RE-005 | US-RE-006 | — |
| 开发/测试人员 | — | — | — | — | — | — | US-RE-007 |

## 用户故事详情

---

### US-RE-001: 发出符合真实硬件信息的模拟告警

- **用户故事**：As a 运维工程师，I want to 发出反映真实设备硬件的模拟告警（真实端口命名、真实型号、真实接入地址），so that 后续诊断/修复作用于真实 TP-Link TL-SG5428 而非 MOCK 假设备。
- **关联需求**：REQ-RE-FUNC-001
- **优先级**：P0 (Must Have)
- **故事点**：[INFERRED — 待开发团队评估]

**验收标准：**

- **AC-RE-001-01** (告警端口/型号符合真实硬件)
  - Given 运维工程师发起 PORT_DOWN 或 PORT_SHUTDOWN 模拟告警
  - When 告警被创建并进入工作流
  - Then 告警接口字段使用真实 TP-Link 端口命名（如 `Gi1/0/1` 而非 `Gi0/1`），设备型号为 `TL-SG5428`（而非 `TP-Link T2600G-28TS`）

- **AC-RE-001-02** (告警接入地址反映真实链路)
  - Given 运维工程师发起针对 REAL 设备的模拟告警
  - When 告警被创建
  - Then 告警设备接入地址反映真实 FRP/局域网地址（`frp_proxy_host=127.0.0.1`、`frp_proxy_port=6022` → `192.168.31.220`），而非默认 `192.168.1.1`

---

### US-RE-002: 通过 REAL 接入真实诊断设备状态

- **用户故事**：As a 运维工程师，I want to 让 AI agent 通过 FRP 隧道真实连接交换机并执行 `show interface status` 等诊断命令，so that 诊断结果来自真实设备而非 Mock 假数据。
- **关联需求**：REQ-RE-FUNC-002, REQ-RE-FUNC-003, REQ-RE-FUNC-004
- **优先级**：P0 (Must Have)
- **故事点**：[INFERRED — 待开发团队评估]

**验收标准：**

- **AC-RE-002-01** (establish_ssh/collect_diag 走真实接入)
  - Given REAL 设备的 FRP 隧道（127.0.0.1:6022）可达且凭据正确
  - When 工作流进入 establish_ssh → collect_diag 节点
  - Then 诊断会话通过 FRP 隧道真实连接到交换机，执行的是真实 TL-SG5428 命令（`show interface status` 等），而非直连默认 IP 或返回 Mock 数据

- **AC-RE-002-02** (诊断输出解析为结构化结果)
  - Given 真实 `show interface status` 输出返回
  - When collect_diag/analyze_root_cause 解析输出
  - Then 输出被解析为结构化结果（端口名/状态/速率等），解析失败时返回明确错误而非错误数据；不使用 Cisco/Mock 命令（`show processes cpu`/`show logging`/`show mac address-table`）

---

### US-RE-003: 下发真实修复命令（覆盖四类告警）

- **用户故事**：As a 运维工程师，I want to 让 execute_fix 在真实设备上下发 TP-Link 语法的修复命令序列（PORT_DOWN→`no shutdown`、PORT_SHUTDOWN→`shutdown`，CPU_HIGH/MAC_FLAPPING 用 TP-Link 等价命令），so that 四类告警的真实端口/资源故障被真实修复。
- **关联需求**：REQ-RE-FUNC-005, REQ-RE-FUNC-008, REQ-RE-NFUNC-002
- **优先级**：P0 (Must Have)
- **故事点**：[INFERRED — 待开发团队评估]

**验收标准：**

- **AC-RE-003-01** (下发 TP-Link 语法的可逆修复)
  - Given 用户已授权对测试端口 `Gi1/0/2` 执行写操作，且 PORT_DOWN 修复动作为 `no shutdown`
  - When execute_fix 节点下发修复命令
  - Then 命令序列为 TP-Link 可用语法（`configure` → `interface <port>` → `no shutdown` → `exit`），不包含 Cisco 语法（`control-plane`/`policy-map`/`switchport port-security`），且不执行 `copy running-config startup-config` 持久化

- **AC-RE-003-02** (写操作可审计且不泄露明文密码)
  - Given 修复命令下发完成（成功或失败）
  - When 写入审计日志
  - Then 审计日志记录设备/端口/动作/结果/时间，且不记录明文密码

- **AC-RE-003-03** (CPU_HIGH/MAC_FLAPPING 用 TP-Link 等价命令或降级)
  - Given 架构阶段（GROUP_B）已核实 TL-SG5428 的 CPU 限速/端口安全等价命令是否存在
  - When execute_fix 处理 CPU_HIGH 或 MAC_FLAPPING 告警
  - Then 若存在等价命令则下发 TP-Link 等价修复命令；若不存在等价命令则降级为「真实诊断 + 告警闭环、修复降级」，并在最终报告中明确标注，不得下发 Cisco 语法命令

---

### US-RE-004: 验证修复并收敛关闭

- **用户故事**：As a 运维工程师，I want to 让 verify_fix 重新诊断对比修复前后状态并基于真实输出判定通过，so that 工作流收敛到 finish_report 并关闭告警。
- **关联需求**：REQ-RE-FUNC-006, REQ-RE-FUNC-007
- **优先级**：P0 (Must Have)
- **故事点**：[INFERRED — 待开发团队评估]

**验收标准：**

- **AC-RE-004-01** (基于真实输出判定修复前后)
  - Given 修复已执行，真实 `show interface status` 的 Status 列在修复前为 down/Disable、修复后为 up/Enable
  - When verify_fix 重新诊断并对比
  - Then 判定逻辑基于真实输出格式（Enable/Disable 或 up/down）判定通过，而非 Cisco 关键词 `down`/`notconnect`

- **AC-RE-004-02** (工作流收敛关闭)
  - Given 验证判定通过
  - When 工作流进入 finish_report 节点
  - Then 告警状态置为 CLOSED，完整链路（告警→诊断→修复→验证→关闭）在 REAL 设备上端到端跑通

---

### US-RE-005: 真实端口写操作授权与可逆优先

- **用户故事**：As a 安全/系统管理员，I want to 在真实端口写操作前进行单独授权并指定无关键业务的测试端口（`Gi1/0/2`），so that 高风险生产写操作可逆、可控、可追溯。
- **关联需求**：REQ-RE-NFUNC-002
- **优先级**：P0 (Must Have)
- **故事点**：[INFERRED — 待开发团队评估]

**验收标准：**

- **AC-RE-005-01** (写操作需单独授权并指定测试端口)
  - Given 用户已指定测试端口 `Gi1/0/2`（down 空闲口，无关键业务）并单独授权
  - When execute_fix 对该端口下发写命令
  - Then 写命令仅限用户确认的修复动作，且作用于 `Gi1/0/2`，不作用于未授权端口

- **AC-RE-005-02** (可逆优先，shutdown 需更高授权)
  - Given 写操作集合已确认为 `no shutdown`（默认可逆修复）+ `shutdown`（隔离，更高授权）
  - When 需下发 `shutdown`（隔离场景）
  - Then `shutdown` 需更高一级授权，且不作为默认修复动作；`description <desc>` 不纳入

---

### US-RE-006: 凭据安全（不硬编码明文）

- **用户故事**：As a 安全/系统管理员，I want to 真实交换机凭据通过既有密钥/环境变量机制（`DEVICE_<NAME>_PASSWORD` 或 DB Fernet 解密）提供，so that 生产凭据不被硬编码或明文落盘。
- **关联需求**：REQ-RE-NFUNC-001
- **优先级**：P0 (Must Have)
- **故事点**：[INFERRED — 待开发团队评估]

**验收标准：**

- **AC-RE-006-01** (凭据来源为既有机制)
  - Given 真实交换机 admin 密码已通过 `DEVICE_TL-SG5428-核心交换机_PASSWORD` 环境变量或 DB Fernet 密文提供
  - When 工作流建立 REAL 接入会话
  - Then 凭据从该既有机制读取，不使用 `get_device_credentials` 的兜底明文 `admin123`，且不新增任何明文密码

---

### US-RE-007: 会话串行化与不破坏现有能力

- **用户故事**：As a 开发/测试人员，I want to 本次 REAL E2E 能力复用会话串行化门且不破坏 MOCK/SIMULATOR E2E 与 REAL 面板，so that 现有功能与测试不回归。
- **关联需求**：REQ-RE-NFUNC-003, REQ-RE-NFUNC-004
- **优先级**：P0 (Must Have)
- **故事点**：[INFERRED — 待开发团队评估]

**验收标准：**

- **AC-RE-007-01** (REAL 会话串行化)
  - Given 工作流 REAL 诊断/配置会话与「连通性检测」「REAL 面板采集」可能并发
  - When 任一 REAL 会话建立
  - Then 会话通过 `real_session_gate` 串行化（避免 TL-SG5428 TELNET 单会话冲突），并在 finally 中关闭、设超时

- **AC-RE-007-02** (MOCK/SIMULATOR 与 REAL 面板不回归)
  - Given 本次 REAL E2E 能力已交付
  - When 运维工程师分别触发 MOCK 告警、SIMULATOR E2E、REAL 面板心跳/连通性检测
  - Then 三者行为与升级前一致，不受 REAL E2E 补齐影响

---

### US-RE-008: CPU_HIGH/MAC_FLAPPING 真实修复可行性核实与降级

- **用户故事**：As a 运维工程师，I want to 在架构阶段核实 TL-SG5428 对 CPU 限速/端口安全的等价 CLI 能力，so that CPU_HIGH/MAC_FLAPPING 的修复要么用真实 TP-Link 等价命令落地，要么如实降级为「真实诊断 + 告警闭环」，不凭空承诺不可实现的修复。
- **关联需求**：REQ-RE-FUNC-008
- **优先级**：P0 (Must Have)
- **故事点**：[INFERRED — 待开发团队评估]

**验收标准：**

- **AC-RE-008-01** (核实等价命令是否存在)
  - Given 架构阶段（GROUP_B）对 TL-SG5428 的 CPU 限速 / 端口安全 / 风暴抑制等能力进行核实
  - When 核实结论产出
  - Then 明确 CPU_HIGH / MAC_FLAPPING 是否存在 TP-Link 等价修复命令，并据实写入架构决策（有则补模板，无则降级）

- **AC-RE-008-02** (无等价命令时如实降级)
  - Given TL-SG5428 无 CPU 限速/端口安全等价命令
  - When execute_fix 处理 CPU_HIGH 或 MAC_FLAPPING
  - Then 不下发任何 Cisco 语法命令，走「真实诊断 + 告警闭环、修复降级」，最终报告明确标注「修复降级/不可修复」

---

*文档版本 0.2.0 | 状态 APPROVED | 生成时间 2026-09-05 | 作者 sub_agent_requirement_analyst*

## 汇总统计

| 指标 | 数值 |
|------|------|
| 用户故事总数 | 8 |
| P0 (Must Have) 故事数 | 8 |
| P1 (Should Have) 故事数 | 0 |
| P2 (Could Have) 故事数 | 0 |
| 验收标准组数 | 17 |
| 关联功能需求数 | 8（全覆盖） |
| [INFERRED] 标注数 | 8（故事点默认标注，待开发团队评估） |

### 故事与需求追溯矩阵

| 用户故事 | REQ-RE-FUNC | REQ-RE-NFUNC |
|----------|-------------|--------------|
| US-RE-001 | 001 | — |
| US-RE-002 | 002, 003, 004 | — |
| US-RE-003 | 005, 008 | 002 |
| US-RE-004 | 006, 007 | — |
| US-RE-005 | — | 002 |
| US-RE-006 | — | 001 |
| US-RE-007 | — | 003, 004 |
| US-RE-008 | 008 | — |

*矩阵覆盖校验：所有 8 条 REQ-RE-FUNC 均有至少 1 条用户故事覆盖；4 条 REQ-RE-NFUNC 中 001/002/003/004 均已被覆盖。*

<audit_log>
  <log time="2026-09-05T03:00:00Z" state="WRITE_FILES" action="file_write" result="SUCCESS" trace_id="inv-real-e2e-a-001" file_path="project_workspace/real_device_e2e/requirements/real_device_e2e_user_stories.md"/>
  <log time="2026-09-05T03:10:00Z" state="WRITE_FILES" action="file_update" result="SUCCESS" trace_id="inv-real-e2e-a-002" file_path="project_workspace/real_device_e2e/requirements/real_device_e2e_user_stories.md"/>
</audit_log>
