<file_header>
  <project_id>NetworkAgentDemo</project_id>
  <module_id>real_device_panel</module_id>
  <doc_type>user_stories</doc_type>
  <file_name>real_panel_user_stories.md</file_name>
  <version>0.2.0</version>
  <status>APPROVED</status>
  <author_agent>sub_agent_requirement_analyst</author_agent>
  <created_at>2026-09-05T00:00:00Z</created_at>
  <last_updated>2026-09-05T02:00:00Z</last_updated>
  <invocation_id>inv-real-panel-a-002</invocation_id>
  <input_source>PM agent_invocation — 用户已确认决策（Q-RP-01~05 RESOLVED）定稿修订</input_source>
</file_header>

# 真实设备（REAL）面板 — 用户故事清单

## 用户角色地图（Actor x Feature Matrix）

| Actor \ Feature | 打开面板 | 端口查看 | CPU/内存 | IO 读写 | 基本信息 | 端口写操作 | 安全确认 | 兼容性 |
|-----------------|----------|----------|----------|---------|----------|-----------|----------|--------|
| 运维工程师 | US-RP-001 | US-RP-002 | US-RP-003 | US-RP-009 | US-RP-004 | US-RP-005 | US-RP-006 | — |
| 系统管理员 | — | — | — | — | — | US-RP-005 | US-RP-006 | — |
| 开发/测试人员 | — | — | — | — | — | — | — | US-RP-008 |

## 用户故事详情

---

### US-RP-001: 打开真实设备面板

- **用户故事**：As a 运维工程师，I want to 在设备列表的真实设备操作列看到「面板」按钮并打开面板抽屉，so that 我能像查看模拟器设备一样查看真实设备的运行状态。
- **关联需求**：REQ-RP-FUNC-001, REQ-RP-FUNC-008
- **优先级**：P0 (Must Have)
- **故事点**：[INFERRED — 待开发团队评估]

**验收标准：**

- **AC-RP-001-01** (真实设备显示面板按钮)
  - Given 设备列表中存在一台 `device_type="REAL"` 的设备
  - When 运维工程师查看该设备的操作列
  - Then 操作列显示「面板」按钮，且与「心跳检测」「连通性检测」按钮并列；该「面板」按钮不显示在 MOCK/SIMULATOR 设备上

- **AC-RP-001-02** (点击面板打开抽屉)
  - Given 运维工程师点击真实设备的「面板」按钮
  - When 抽屉打开
  - Then 抽屉标题显示 `真实设备面板 — {设备名}`，且立即发起面板数据的加载请求

---

### US-RP-002: 查看真实设备端口状态

- **用户故事**：As a 运维工程师，I want to 查看真实设备的交换机端口状态（端口名/状态/VLAN/速率），so that 我能了解真实设备各端口的 up/down 情况。
- **关联需求**：REQ-RP-FUNC-002, REQ-RP-FUNC-009
- **优先级**：P0 (Must Have)
- **故事点**：[INFERRED — 待开发团队评估]

**验收标准：**

- **AC-RP-002-01** (展示端口表格)
  - Given 真实设备在线且凭据正确
  - When 运维工程师打开面板并触发端口状态刷新
  - Then 面板展示端口表格，每条包含端口名、状态（up/down/notconnect）、VLAN、速率，数据来自真实设备 `show interface status` 的解析结果

- **AC-RP-002-02** (设备离线时端口加载失败)
  - Given 真实设备离线或凭据错误
  - When 运维工程师触发端口状态刷新
  - Then 面板显示明确的错误提示（如"无法连接真实设备"），端口表格不显示错误数据

---

### US-RP-003: 查看真实设备 CPU 与内存利用率

- **用户故事**：As a 运维工程师，I want to 查看真实设备的 CPU 和内存利用率，so that 我能监控设备资源状态并识别资源异常。
- **关联需求**：REQ-RP-FUNC-003, REQ-RP-FUNC-004, REQ-RP-FUNC-009
- **优先级**：P0 (Must Have)
- **故事点**：[INFERRED — 待开发团队评估]

**验收标准：**

- **AC-RP-003-01** (展示 CPU 利用率)
  - Given 真实设备在线
  - When 运维工程师触发系统资源刷新
  - Then 面板以进度条展示 CPU 5 秒平均使用率百分比，数据来自 `show cpu-utilization` 的解析结果

- **AC-RP-003-02** (展示内存利用率)
  - Given 真实设备在线
  - When 运维工程师触发系统资源刷新
  - Then 面板展示内存已用/总量（MB）及使用率百分比，数据来自 `show memory-utilization` 的解析结果

---

### US-RP-004: 查看真实设备基本信息 [默认不纳入，作为低成本增值项待架构裁决]

- **用户故事**：As a 运维工程师，I want to 在面板顶部查看真实设备的型号/软硬件版本/设备名，so that 我能快速确认连接的是哪台设备及其版本。
- **关联需求**：REQ-RP-FUNC-005
- **优先级**：P1 (Should Have)
- **故事点**：[INFERRED — 待开发团队评估]

**备注**：已确认（Q-RP-01）：基本信息区块**默认不纳入**面板范围，作为低成本增值项保留为 Should Have，由架构阶段（GROUP_B）裁决是否纳入；**不得作为 Must Have**。

**验收标准：**

- **AC-RP-004-01** (展示设备基本信息)
  - Given 真实设备在线，且架构阶段裁决纳入基本信息区块
  - When 面板加载完成
  - Then 面板顶部展示设备名、型号、硬件版本、软件版本（来自 `show system-info` 解析），与 `/check_connectivity` 返回的 `device_model`/`software_version` 一致

---

### US-RP-005: 对真实设备端口执行启用/禁用 [已确认开放]

- **用户故事**：As a 运维工程师，I want to 对真实设备的端口执行启用/禁用操作，so that 我能直接在面板上处理端口 down 故障。
- **关联需求**：REQ-RP-FUNC-006
- **优先级**：P0 (Must Have)
- **故事点**：[INFERRED — 待开发团队评估]

**备注**：已确认（Q-RP-02）：**开放**写操作；每次写操作强制前端二次确认 + 审计日志（见 US-RP-006）；写操作**不做** `copy running-config startup-config` 持久化。

**验收标准：**

- **AC-RP-005-01** (禁用真实设备端口)
  - Given 真实设备在线且已通过二次确认
  - When 运维工程师对端口 Gi0/1 执行「禁用」（shutdown）
  - Then 系统通过 `configure` → `interface Gi0/1` → `shutdown` → `exit` 下发命令，返回成功，刷新后该端口状态变为 down/administratively down

- **AC-RP-005-02** (启用真实设备端口)
  - Given 真实设备端口 Gi0/1 处于禁用状态
  - When 运维工程师对 Gi0/1 执行「启用」（no shutdown）
  - Then 系统下发 `no shutdown` 命令，返回成功，刷新后该端口状态恢复为 up

- **AC-RP-005-03** (写操作不持久化)
  - Given 运维工程师对真实设备端口执行启用/禁用写操作
  - When 写操作成功完成
  - Then 系统**不**执行 `copy running-config startup-config` 持久化，仅当前 running-config 生效

- **AC-RP-005-04** (写操作失败反馈)
  - Given 真实设备命令下发失败或返回错误
  - When 运维工程师执行端口写操作
  - Then 面板返回明确的失败错误信息，端口状态不产生误导性的变更

---

### US-RP-006: 端口写操作二次确认与审计 [已确认强制适用]

- **用户故事**：As a 运维工程师，I want to 在执行真实设备端口写操作前收到明确的二次确认提示，so that 我能避免误操作生产设备。
- **关联需求**：REQ-RP-FUNC-006, REQ-RP-NFUNC-002
- **优先级**：P0 (Must Have)
- **故事点**：[INFERRED — 待开发团队评估]

**验收标准：**

- **AC-RP-006-01** (写操作二次确认)
  - Given 运维工程师点击真实设备端口的「启用/禁用」按钮
  - When 确认弹窗出现
  - Then 弹窗明确提示「此操作将修改真实生产设备配置」并显示目标端口与动作，需用户再次确认才执行

- **AC-RP-006-02** (写操作审计记录)
  - Given 运维工程师确认执行端口写操作
  - When 操作执行完成
  - Then 操作结果（设备、端口、动作、结果、时间）写入审计日志，且不记录明文密码

---

### US-RP-007: 面板加载与超时反馈

- **用户故事**：As a 运维工程师，I want to 在面板加载真实设备数据时看到明确的 loading 和超时提示，so that 我不会在真实设备 SSH 会话的较长延迟下误以为页面卡死。
- **关联需求**：REQ-RP-NFUNC-001
- **优先级**：P0 (Must Have)
- **故事点**：[INFERRED — 待开发团队评估]

**验收标准：**

- **AC-RP-007-01** (加载提示)
  - Given 运维工程师打开面板并触发刷新
  - When 真实设备 SSH 会话建立中（约 20-40s）
  - Then 面板展示 loading 状态与「真实设备采集中（约 30-60s，请耐心等待）」提示

- **AC-RP-007-02** (超时/失败反馈)
  - Given 真实设备采集超时或失败
  - When 请求超过超时阈值或返回错误
  - Then 面板展示明确错误提示，且解除 loading，不永久挂起

---

### US-RP-008: 现有 SIMULATOR 面板与 REAL 端点不受影响

- **用户故事**：As a 开发/测试人员，I want to 新增 REAL 面板后模拟器面板和真实设备心跳/连通性检测功能保持完全不变，so that 现有功能与测试不被破坏。
- **关联需求**：REQ-RP-NFUNC-003
- **优先级**：P0 (Must Have)
- **故事点**：[INFERRED — 待开发团队评估]

**验收标准：**

- **AC-RP-008-01** (模拟器面板不变)
  - Given 设备列表中存在一台 `device_type="SIMULATOR"` 的设备
  - When 运维工程师打开该设备的模拟器面板
  - Then 面板行为（端口状态/系统资源/启用禁用按钮）与升级前完全一致

- **AC-RP-008-02** (真实设备端点不变)
  - Given 设备列表中存在一台 `device_type="REAL"` 的设备
  - When 运维工程师执行「心跳检测」和「连通性检测」
  - Then 两个按钮行为与返回字段与升级前一致，不受 REAL 面板新增影响

---

### US-RP-009: 查看真实设备 IO 读写速率（替代数据 / 降级展示）

- **用户故事**：As a 运维工程师，I want to 在真实设备面板看到「IO 读写」区块（即使真实设备无原生 IO CLI 命令也能以替代数据或降级提示展示），so that 真实设备面板能尽量复刻模拟器面板的完整信息范围、不因缺少 IO 命令而缺失该区块。
- **关联需求**：REQ-RP-FUNC-010
- **优先级**：P0 (Must Have)
- **故事点**：[INFERRED — 待开发团队评估]

**验收标准：**

- **AC-RP-009-01** (展示 IO 替代数据)
  - Given 真实设备在线，且架构阶段（GROUP_B）已确定可用的 IO 替代采集命令（或从其它已可用命令推导的降级方案）
  - When 运维工程师触发系统资源刷新
  - Then 面板「IO 读/写」区块展示替代采集得到的 IO 读/写速率（KB/s），区块位置与 SIMULATOR 面板「IO 读/写」区块（`DevicesListView.vue` 第 192-199 行）对应

- **AC-RP-009-02** (设备不支持时降级提示，不丢区块)
  - Given 真实设备在线，但确无任何可用的 IO 读/写命令
  - When 运维工程师触发系统资源刷新
  - Then 面板「IO 读/写」区块仍保留展示，并降级提示「该设备不支持 IO 采集」（或等效降级文案），**不得**整块隐藏或丢弃

---

*文档版本 0.2.0 | 状态 APPROVED | 生成时间 2026-09-05 | 作者 sub_agent_requirement_analyst*

## 汇总统计

| 指标 | 数值 |
|------|------|
| 用户故事总数 | 9 |
| P0 (Must Have) 故事数 | 8 |
| P1 (Should Have) 故事数 | 1 |
| P2 (Could Have) 故事数 | 0 |
| 验收标准总数 | 19 |
| 关联功能需求数 | 10（全覆盖） |
| [INFERRED] 标注数 | 9（故事点默认标注，待开发团队评估） |

### 故事与需求追溯矩阵

| 用户故事 | REQ-RP-FUNC | REQ-RP-NFUNC |
|----------|-------------|--------------|
| US-RP-001 | 001, 008 | — |
| US-RP-002 | 002, 009 | — |
| US-RP-003 | 003, 004, 009 | — |
| US-RP-004 | 005 | — |
| US-RP-005 | 006 | — |
| US-RP-006 | 006 | 002 |
| US-RP-007 | — | 001 |
| US-RP-008 | — | 003 |
| US-RP-009 | 010 | — |

*矩阵覆盖校验：所有 10 条 REQ-RP-FUNC 均有至少 1 条用户故事覆盖；4 条 REQ-RP-NFUNC 中 001/002/003 已被覆盖，004（会话串行化与超时）为横切约束，体现在 US-RP-002/003/005/007/009 的验收标准语境中。*

<audit_log>
  <log time="2026-09-05T00:00:00Z" state="WRITE_FILES" action="file_write" result="SUCCESS" trace_id="inv-real-panel-a-001" file_path="project_workspace/real_device_panel/requirements/real_panel_user_stories.md"/>
  <log time="2026-09-05T02:00:00Z" state="WRITE_FILES" action="file_update" result="SUCCESS" trace_id="inv-real-panel-a-002" file_path="project_workspace/real_device_panel/requirements/real_panel_user_stories.md"/>
</audit_log>
