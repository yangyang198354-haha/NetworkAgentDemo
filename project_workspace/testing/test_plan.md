<file_header>
  <author_agent>sub_agent_test_engineer</author_agent>
  <timestamp>2026-07-10T01:30:00Z</timestamp>
  <project_name>NetworkAgentDemo</project_name>
  <version>0.1.0</version>
  <input_files>
    <file>requirements/user_stories.md</file>
    <file>requirements/requirements_spec.md</file>
    <file>architecture/architecture_design.md</file>
    <file>architecture/module_design.md</file>
    <file>development/implementation_plan.md</file>
    <file>src/ (28 Python source files, read-only)</file>
  </input_files>
  <phase>PHASE_07</phase>
  <status>APPROVED</status>
</file_header>

# 测试计划 — NetworkAgentDemo

---

## 1. 测试策略

### 1.1 测试目标

验证 NetworkAgentDemo 系统的 16 个模块（MOD-001 ~ MOD-016）在 Demo 阶段满足以下质量标准：

- **单元测试**：验证每个模块的独立逻辑正确性，通过率目标 >= 80%
- **集成测试**：验证模块间协作（LangGraph 节点链、工具层调用链），通过率目标 >= 90%
- **E2E 测试**：验证完整用户旅程（Webhook → 诊断 → 审批 → 修复 → 验证 → 报告），Critical Path 覆盖率 100%

### 1.2 测试范围（In-Scope）

| 范围 | 说明 |
|------|------|
| 数据模型层 | MOD models: enums, alert, state, fix_plan — Pydantic 校验、序列化正确性 |
| 安全与基础设施层 | MOD-014 RiskAssessor, MOD-015 AuditLogger, MOD-016 ConfigManager |
| LLM 与知识层 | MOD-006 LLMService (Mock mode), MOD-007 TemplateEngine, MOD-008 RAGService, MOD-009 OutputValidator |
| 工具层 | MOD-010 SwitchConfigTool (Mock), MOD-011 SwitchDiagTool (Mock), MOD-012 BackupTool (Mock), MOD-013 KnowledgeBaseTool |
| 编排层 | MOD-003 StateGraphEngine (14 节点 + 4 条件边), MOD-004 AlertNormalizer, MOD-005 NodeHandlers |
| 触发层 | MOD-001 WebhookReceiver, MOD-002 InspectionScheduler |
| 用户故事覆盖 | US-001 ~ US-011 (全部), 49 组 AC (Given/When/Then) |
| Mock 工具层验证 | Mock 返回正确的模拟诊断数据格式 (switch_diag_tool) |
| OutputValidator 安全关键路径 | CLI 注入检测 100% 测试覆盖 |

### 1.3 超出范围（Out-of-Scope）

| 排除项 | 原因 |
|--------|------|
| 真实 DeepSeek API 调用 | Demo 阶段 LLMService 在无 API key 时使用 Mock fallback |
| 真实 TP-Link 交换机连接 | Demo 阶段工具层全部 Mock，TpLinkImpl 仅验证抛出 NotImplementedError |
| Chroma 向量库真实运行 | 依赖 text-embedding-3-small API，Demo 阶段使用 fallback 内存检索 |
| FastAPI 端点 HTTP 测试 | 需要启动 Uvicorn 服务器，Demo 阶段通过 LangGraph 直接调用工作流 |
| APScheduler 定时触发 | 单元测试中通过直接调用 run_inspection_once() 验证，不测试定时器 |

### 1.4 测试环境

| 项目 | 值 |
|------|-----|
| 操作系统 | Windows 11 Pro (Linux 目标环境模拟通过 POSIX 路径兼容) |
| Python 版本 | 3.14.6 |
| 测试框架 | pytest >= 9.1.1 |
| 覆盖率工具 | pytest-cov >= 7.1.0 |
| Mock 策略 | 所有外部依赖 Mock (LLM API, SSH, 交换机命令执行) |
| 特殊说明 | 工具层 Mock 无需 netmiko/NAPALM；LLMService 无 API key 时自动 Mock |

---

## 2. 测试用例清单

### 2.1 测试用例分类规则

| 测试级别 | 分类规则 | 示例 |
|---------|---------|------|
| UNIT | 仅涉及单个函数/方法/类的行为，无跨模块依赖 | 数据模型校验、RiskAssessor 规则匹配、OutputValidator 正则扫描 |
| INT | 涉及两个或多个模块的协作 | NodeHandlers 调用工具层、StateGraphEngine 运行多节点工作流 |
| E2E | 描述完整的用户操作路径（从入口到出口） | Webhook→诊断→审批→修复→验证→报告完整闭环 |

### 2.2 单元测试用例 (TC-UNIT)

| TC-ID | 所属 US | 关联 AC | 描述 | 前置条件 | 动作 | 预期结果 |
|-------|--------|--------|------|---------|------|---------|
| TC-UNIT-001 | US-001 | AC-001-01 | AlertPayload Pydantic 校验 | — | 构造合法 AlertPayload | 校验通过，字段值正确 |
| TC-UNIT-002 | US-001 | AC-001-01 | AlertPayload 必填字段校验 | — | 构造最小字段 AlertPayload | 可选字段为 None |
| TC-UNIT-003 | US-001 | AC-001-01 | Alert 对象构造 | — | 构造 Alert 对象 | alert_id 为 36 字符 UUID |
| TC-UNIT-004 | US-001 | AC-001-01 | AlertReceipt 状态 | — | 构造 AlertReceipt(status="ACCEPTED") | 状态字段正确 |
| TC-UNIT-005 | US-001 | AC-001-02 | FixPlan 数据模型 | — | 构造 FixPlan 含 commands | commands 列表正确存储 |
| TC-UNIT-006 | US-001 | AC-001-02 | ConfigResult 数据模型 | — | 构造 ConfigResult(success=True) | 字段值正确 |
| TC-UNIT-007 | US-001 | AC-001-02 | DiagResult 数据模型 | — | 构造 DiagResult 含 execution_time_ms | execution_time_ms > 0 |
| TC-UNIT-008 | US-006 | AC-006-02 | RiskAssessment 数据模型 | — | 构造 RiskAssessment(need_human_approval=True) | need_human_approval=True, risk_level="HIGH" |
| TC-UNIT-009 | — | — | 枚举类型值 | — | 检查 AlertType 枚举值 | MAC_FLAPPING/PORT_DOWN/CPU_HIGH 正确 |
| TC-UNIT-010 | — | — | 枚举类型 WorkflowStatus | — | 检查 WorkflowStatus 值 | ACTIVE/CLOSED/FAILED/REJECTED/EXPIRED 正确 |
| TC-UNIT-011 | US-001 | AC-001-01 | AlertNormalizer 归一化 Webhook 事件 | AlertNormalizer 实例 | normalize_webhook_event(MAC_FLAPPING payload) | 返回 Alert，类型=MAC_FLAPPING |
| TC-UNIT-012 | US-001 | AC-001-05 | AlertNormalizer 过期告警 | 过期 payload (2020年) | normalize_webhook_event | 返回 None |
| TC-UNIT-013 | US-001 | AC-001-05 | AlertNormalizer 重复检测 | 同一 payload 两次 | normalize_webhook_event 两次 | 第一次返回 Alert，第二次返回 None |
| TC-UNIT-014 | US-004 | AC-004-01 | AlertNormalizer 巡检事件 | RawInspectionEvent | normalize_inspection_event | 返回 Alert，source=INSPECTION |
| TC-UNIT-015 | US-002 | AC-002-01 | AlertNormalizer 中文类型映射 | alert_type="端口 DOWN" | normalize_webhook_event | alert_type=PORT_DOWN |
| TC-UNIT-016 | US-011 | AC-011-02 | OutputValidator 正常参数校验 | 合法 JSON + schema | validate_params | 返回校验通过的参数字典 |
| TC-UNIT-017 | US-011 | AC-011-02 | OutputValidator CLI 注入检测 (shutdown) | 参数值含 "no shutdown" | validate_params | ValidationError with SECURITY_ALERT |
| TC-UNIT-018 | US-011 | AC-011-02 | OutputValidator 非法 JSON | 输入非 JSON 字符串 | validate_params | ValidationError "not valid JSON" |
| TC-UNIT-019 | US-011 | AC-011-02 | OutputValidator 未知参数检测 | JSON 含 schema 外 key | validate_params | ValidationError "Unknown parameter" |
| TC-UNIT-020 | US-011 | AC-011-02 | OutputValidator 类型不匹配 | 参数值类型与 schema 不符 | validate_params | ValidationError "Type mismatch" |
| TC-UNIT-021 | US-008 | AC-008-05 | OutputValidator Markdown JSON 解析 | JSON 包裹在 ```json 中 | validate_params | 正确解析 JSON |
| TC-UNIT-022 | US-008 | AC-008-05 | OutputValidator 尾部逗号修复 | JSON 含尾部逗号 | validate_params | 修复后解析成功 |
| TC-UNIT-023 | US-008 | AC-008-05 | OutputValidator sanitize_root_cause 标记 | 根因分析文本 | sanitize_root_cause | 输出含 SECURITY: 标记 |
| TC-UNIT-024 | US-008 | AC-008-05 | OutputValidator 重复标记防护 | 已含 SECURITY: 的文本 | sanitize_root_cause | 不重复追加 |
| TC-UNIT-025 | US-011 | AC-011-02 | OutputValidator CLI 黑名单 reload | 参数含 "reload" | validate_params | ValidationError with SECURITY_ALERT |
| TC-UNIT-026 | US-011 | AC-011-02 | OutputValidator CLI 黑名单 shutdown | 参数含 "需要执行 shutdown" | validate_params | ValidationError with SECURITY_ALERT |
| TC-UNIT-027 | US-006 | AC-006-04 | RiskAssessor 低风险无审批 | commands=["description test"] | assess | risk_level=LOW, need_approval=False |
| TC-UNIT-028 | US-006 | AC-006-05 | RiskAssessor shutdown 高风检 | commands=["shutdown"] | assess | risk_level=HIGH, need_approval=True |
| TC-UNIT-029 | US-006 | AC-006-05 | RiskAssessor no shutdown 高风险 | commands=["no shutdown"] | assess | risk_level=HIGH, need_approval=True |
| TC-UNIT-030 | US-006 | AC-006-06 | RiskAssessor VLAN 删除 CRITICAL | commands=["no vlan 100"] | assess | risk_level=CRITICAL, need_approval=True |
| TC-UNIT-031 | US-006 | AC-006-05 | RiskAssessor reload CRITICAL | commands=["reload"] | assess | risk_level=CRITICAL, need_approval=True |
| TC-UNIT-032 | US-006 | AC-006-05 | RiskAssessor OSPF 路由 HIGH | commands=["router ospf 1"] | assess | risk_level=HIGH, need_approval=True |
| TC-UNIT-033 | US-006 | AC-006-04 | RiskAssessor spanning-tree MEDIUM | commands=["spanning-tree vlan 1"] | assess | risk_level=MEDIUM, need_approval=False (单命令) |
| TC-UNIT-034 | US-006 | AC-006-04 | RiskAssessor 多 MEDIUM 命令触发审批 | 两条 spanning-tree 命令 | assess | need_approval=True |
| TC-UNIT-035 | US-006 | AC-006-04 | RiskAssessor write memory LOW | commands=["write memory"] | assess | risk_level=LOW |
| TC-UNIT-036 | US-006 | — | RiskAssessor 空命令 LOW | commands=[] | assess | risk_level=LOW |
| TC-UNIT-037 | US-006 | — | RiskAssessor 多等级取最高 | shutdown(HIGH)+spanning(MEDIUM)+write(LOW) | assess | risk_level=HIGH |
| TC-UNIT-038 | US-006 | — | RiskAssessor risk_hints 传递 | fix_plan 含 risk_hints | assess | risk_reasons 含 hints 内容 |
| TC-UNIT-039 | — | — | ConfigManager get 嵌套 key | — | get("inspection.interval_minutes") | 返回 5 |
| TC-UNIT-040 | — | — | ConfigManager get 缺失 key | — | get("nonexistent") | 返回 None |
| TC-UNIT-041 | — | — | ConfigManager set+get | — | set(key, val); get(key) | 返回 set 的值 |
| TC-UNIT-042 | — | — | ConfigManager set 新 key | — | set("new.nested", val) | 创建嵌套结构 |
| TC-UNIT-043 | — | — | ConfigManager 默认配置完整性 | — | 检查 DEFAULT_CONFIG keys | inspection/diagnosis/alert/rag/logging/server 存在 |
| TC-UNIT-044 | — | — | ConfigManager 设备凭据 (不存在) | — | get_device_credentials("NonExistent") | 返回 None |
| TC-UNIT-045 | — | — | ConfigManager deep_merge | base+override | _deep_merge | 保留原有 key，覆盖交集 key |
| TC-UNIT-046 | US-006 | AC-006-01 | SwitchConfigTool 单命令执行 | Mock ConfigTool | _run(ip, ["cmd"]) | success=True, executed=1 |
| TC-UNIT-047 | US-006 | AC-006-02 | SwitchConfigTool 多命令执行 | Mock ConfigTool | _run(ip, [c1,c2,c3]) | success=True, executed=3 |
| TC-UNIT-048 | US-006 | — | SwitchConfigTool 空命令列表 | Mock ConfigTool | _run(ip, []) | success=True, executed=0 |
| TC-UNIT-049 | US-006 | — | SwitchConfigTool interface 输出 | Mock ConfigTool | cmd="interface Gi0/1" | output 含 "Entering interface.." |
| TC-UNIT-050 | US-006 | AC-006-05 | SwitchConfigTool no shutdown 输出 | Mock ConfigTool | cmd="no shutdown" | output 含 "Interface enabled" |
| TC-UNIT-051 | US-006 | AC-006-05 | SwitchConfigTool shutdown 输出 | Mock ConfigTool | cmd="shutdown" | output 含 "Interface disabled" |
| TC-UNIT-052 | — | — | SwitchConfigTool 工厂 Mock | use_mock=True | create_switch_config_tool | 返回 MockSwitchConfigTool |
| TC-UNIT-053 | — | — | SwitchConfigTool 工厂 TpLink | use_mock=False | create_switch_config_tool | 返回 TpLinkSwitchConfigTool |
| TC-UNIT-054 | — | — | TpLinkConfigTool NotImplemented | TpLink ConfigTool | _run() | 抛出 NotImplementedError |
| TC-UNIT-055 | US-001 | AC-001-02 | SwitchDiagTool MAC 表 | Mock DiagTool | diagnose("show mac address-table") | 含 00:1A:2B:3C:4D:5E 和 WARNING/flapping |
| TC-UNIT-056 | US-002 | AC-002-02 | SwitchDiagTool 接口详情 | Mock DiagTool | diagnose("show interface Gi0/1") | 含 GigabitEthernet 和 down 状态 |
| TC-UNIT-057 | US-004 | AC-004-01 | SwitchDiagTool 接口状态列表 | Mock DiagTool | diagnose("show interface status") | 含 Gi0/1 到 Gi0/8 |
| TC-UNIT-058 | US-003 | AC-003-02 | SwitchDiagTool CPU 进程 | Mock DiagTool | diagnose("show processes cpu") | 含 CPU utilization 和 IP Input |
| TC-UNIT-059 | US-005 | AC-005-01 | SwitchDiagTool CPU 历史 | Mock DiagTool | diagnose("show processes cpu history") | 含 CPU% 图表 |
| TC-UNIT-060 | US-001 | AC-001-02 | SwitchDiagTool 系统日志 | Mock DiagTool | diagnose("show logging") | 含 Syslog 或 MACFLAP |
| TC-UNIT-061 | — | — | SwitchDiagTool 未知命令 | Mock DiagTool | diagnose("show unknown") | success=True, 通用输出 |
| TC-UNIT-062 | — | — | SwitchDiagTool 执行时间 | Mock DiagTool | diagnose(any command) | execution_time_ms >= 0 |
| TC-UNIT-063 | — | — | SwitchDiagTool 工厂 Mock | use_mock=True | create_switch_diag_tool | MockSwitchDiagTool |
| TC-UNIT-064 | — | — | TpLinkDiagTool NotImplemented | TpLink DiagTool | diagnose() | NotImplementedError |
| TC-UNIT-065 | US-009 | AC-009-01 | BackupTool backup 成功 | Mock BackupTool | _run(ip, auth, "backup") | success=True, config 非空 |
| TC-UNIT-066 | US-009 | AC-009-01 | BackupTool backup ID 唯一 | Mock BackupTool | backup 两次 | backup_id 不同 |
| TC-UNIT-067 | US-009 | AC-009-03 | BackupTool rollback 成功 | Mock BackupTool, 先 backup | rollback(backup_id) | RollbackResult.success=True |
| TC-UNIT-068 | US-009 | AC-009-02 | BackupTool rollback 无 ID | Mock BackupTool | rollback(backup_id=None) | success=False, "required" |
| TC-UNIT-069 | US-009 | — | BackupTool rollback 未知 ID | Mock BackupTool | rollback("nonexistent") | success=False, "not found" |
| TC-UNIT-070 | — | — | BackupTool 工厂 Mock | use_mock=True | create_backup_tool | MockBackupTool |
| TC-UNIT-071 | — | — | TpLinkBackupTool NotImplemented | TpLink BackupTool | backup() | NotImplementedError |

### 2.3 集成测试用例 (TC-INT)

| TC-ID | 所属 US | 关联 AC | 描述 | 集成边界 | 前置条件 | 动作 | 预期结果 |
|-------|--------|--------|------|---------|---------|------|---------|
| TC-INT-001 | US-001 | AC-001-01 | validate_alert 通过有效告警 | MOD-005 ↔ MOD-016 | 含有效 alert_content 的 State | handle_validate_alert | is_valid=True |
| TC-INT-002 | US-001 | AC-001-05 | validate_alert 拒绝空内容 | MOD-005 ↔ MOD-016 | alert_content 为空白 | handle_validate_alert | is_valid=False |
| TC-INT-003 | US-001 | AC-001-01 | parse_alert 提取字段 | MOD-005 ↔ State | MAC_FLAPPING State | handle_parse_alert | alert_type=MAC_FLAPPING |
| TC-INT-004 | US-001 | AC-001-04 | receive_alert 初始化 State | MOD-005 | 含 alert_id 的 State | handle_receive_alert | status=ACTIVE |
| TC-INT-005 | US-001 | AC-001-02 | get_device_info 补充信息 | MOD-005 ↔ MOD-016 | 含 device_name 的 State | handle_get_device_info | device_model 已填充 |
| TC-INT-006 | US-001 | AC-001-02 | establish_ssh Mock 通过 | MOD-005 | 含 device_info 凭据 | handle_establish_ssh | 无异常 |
| TC-INT-007 | US-001 | AC-001-02 | collect_diag MAC_FLAPPING | MOD-005 ↔ MOD-011 | MAC_FLAPPING State | handle_collect_diag | diag_result 含 MAC 表数据 |
| TC-INT-008 | US-002 | AC-002-02 | collect_diag PORT_DOWN | MOD-005 ↔ MOD-011 | PORT_DOWN State | handle_collect_diag | diag_result 含接口数据 |
| TC-INT-009 | US-008 | AC-008-01 | analyze_root_cause 产生输出 | MOD-005 ↔ MOD-006 ↔ MOD-009 | diag_result 已填充 | handle_analyze_root_cause | root_cause 非空, 含 SECURITY: 标记 |
| TC-INT-010 | US-008 | AC-008-03 | generate_fix_plan MAC_FLAPPING | MOD-005 ↔ MOD-006 ↔ MOD-007 ↔ MOD-009 | State 含 root_cause | handle_generate_fix_plan | fix_plan 含 commands |
| TC-INT-011 | US-006 | AC-006-05 | assess_risk 高风险方案 | MOD-005 ↔ MOD-014 | fix_plan 含 shutdown | handle_assess_risk | need_human_approval=True |
| TC-INT-012 | US-006 | AC-006-04 | assess_risk 低风险方案 | MOD-005 ↔ MOD-014 | fix_plan 含 write memory | handle_assess_risk | need_human_approval=False |
| TC-INT-013 | US-007 | AC-007-01 | human_approval PENDING 注册 | MOD-005 ↔ MOD-015 | approval_status=PENDING | handle_human_approval | 保持 PENDING, 注册审批项 |
| TC-INT-014 | US-007 | AC-007-02 | human_approval APPROVED 日志 | MOD-005 ↔ MOD-015 | approval_status=APPROVED | handle_human_approval | 记录 AUDIT 事件 |
| TC-INT-015 | US-009 | AC-009-01 | backup_config 备份成功 | MOD-005 ↔ MOD-012 | State 含 device_info | handle_backup_config | config_backup 非空, _backup_success=True |
| TC-INT-016 | US-006 | AC-006-02 | execute_fix 多命令执行 | MOD-005 ↔ MOD-010 | fix_plan 含 3 条命令 | handle_execute_fix | exec_log 含 3 条记录 |
| TC-INT-017 | US-001 | AC-001-04 | verify_result 修复后验证 | MOD-005 ↔ MOD-011 | State 含 diag_result | handle_verify_result | verify_result 含 before/after 状态 |
| TC-INT-018 | US-001 | AC-001-04 | final_report 成功闭环 | MOD-005 ↔ MOD-006 | 所有字段填充完毕 | handle_final_report | status=CLOSED, final_report 非空 |
| TC-INT-019 | US-007 | AC-007-03 | final_report 审批拒绝 | MOD-005 | approval_status=REJECTED | handle_final_report | status=REJECTED |
| TC-INT-020 | US-001 | AC-001-05 | final_report 无效告警 | MOD-005 | is_valid=False | handle_final_report | status=EXPIRED |
| TC-INT-021 | — | — | StateGraphEngine build_graph | MOD-003 ↔ MOD-005 | NodeHandlers 注入 | build_graph | 返回编译后的 StateGraph |
| TC-INT-022 | US-001 | AC-001-01~04 | MAC 漂移完整工作流 | MOD-003 ↔ MOD-005 ↔ 全部工具 | MAC_FLAPPING Alert | run_workflow | state 含 status |
| TC-INT-023 | US-002 | AC-002-01~04 | PORT_DOWN 完整工作流 | MOD-003 ↔ MOD-005 ↔ 全部工具 | PORT_DOWN Alert | run_workflow | state 含 status |
| TC-INT-024 | US-003 | AC-003-01~04 | CPU_HIGH 完整工作流 | MOD-003 ↔ MOD-005 ↔ 全部工具 | CPU_HIGH Alert | run_workflow | state 含 status |
| TC-INT-025 | US-001 | AC-001-02 | 工作流产生 diag_result | MOD-003 ↔ MOD-005 ↔ MOD-011 | PORT_DOWN Alert | run_workflow | diag_result 非空 |
| TC-INT-026 | US-008 | AC-008-01 | 工作流产生 root_cause | MOD-003 ↔ MOD-005 ↔ MOD-006 | PORT_DOWN Alert | run_workflow | root_cause 存在 |
| TC-INT-027 | US-001 | AC-001-04 | 工作流状态持久化 | MOD-003 ↔ MemorySaver | PORT_DOWN Alert | run_workflow → get_workflow_state | state 可查询 |
| TC-INT-028 | US-007 | AC-007-04 | 初始无挂起审批 | MOD-003 ↔ MOD-015 | 新引擎实例 | get_pending_approvals | 返回空列表 |
| TC-INT-029 | US-006 | AC-006-01 | 高风险方案路由至审批 | MOD-003 ↔ MOD-005 ↔ MOD-014 | PORT_DOWN Alert | run_workflow | 状态机执行至 human_approval |
| TC-INT-030 | US-007 | AC-007-02 | 审批通过后恢复 | MOD-003 ↔ MOD-005 | 审批决定 APPROVED | resume_workflow(APPROVED) | 流程继续执行 |
| TC-INT-031 | US-007 | AC-007-02 | ApprovalDecision 数据模型 | — | 构造 APPROVED 决定 | ApprovalDecision | decision="APPROVED" |

### 2.4 E2E 测试用例 (TC-E2E)

| TC-ID | 所属 US | 关联 AC | 描述 | 用户旅程 | 前置条件 | 预期结果 |
|-------|--------|--------|------|---------|---------|---------|
| TC-E2E-001 | US-001 | AC-001-01~04 | MAC 漂移完整闭环 (Webhook) | Webhook接收→解析→校验→获取设备→SSH→诊断→根因分析→方案生成→风险评估→审批→备份→修复→验证→报告 | Mock MAC_FLAPPING Alert | 工作流完成，status 含 CLOSED/ACTIVE |
| TC-E2E-002 | US-002 | AC-002-01~05 | 端口 Down 完整闭环 (Webhook) | 同上全链路 | Mock PORT_DOWN Alert | 工作流完成 |
| TC-E2E-003 | US-003 | AC-003-01~05 | CPU 过高完整闭环 (Webhook) | 同上全链路 | Mock CPU_HIGH Alert | 工作流完成 |
| TC-E2E-004 | US-006+007 | AC-006-01~06, AC-007-01~04 | 人工审批中断/恢复完整闭环 | 诊断→评估→Interrupt 挂起→运维审批→从断点恢复→修复→验证→报告 | PORT_DOWN Alert (触发高风险审批) | Interrupt 正确挂起 |
| TC-E2E-005 | US-006+007 | AC-007-02 | 审批 APPROVED 恢复执行 | 挂起→APPROVED→恢复→备份→修复→验证→报告 | resume_workflow(APPROVED) | 流程从备份节点继续 |
| TC-E2E-006 | US-001 | AC-001-04 | 诊断数据在 E2E 流程中产生 | 接收→诊断 | MAC_FLAPPING Alert | diag_result 在 State 中填充 |
| TC-E2E-007 | US-008 | AC-008-01 | 根因分析在 E2E 流程中产生 | 接收→诊断→根因分析 | PORT_DOWN Alert | root_cause 在 State 中填充 |
| TC-E2E-008 | US-001 | AC-001-04 | E2E 工作流状态可查询 | 完整闭环后 | get_workflow_state(alert_id) | 返回完整 State |
| TC-E2E-009 | US-006+007 | AC-007-03 | 审批拒绝后优雅终止 | 挂起→REJECTED→终止 | resume_workflow(REJECTED) | 流程终止，不进入修复 |

---

## 3. 不可测试项

| AC-ID | 原因 |
|-------|------|
| [NOT_TESTABLE — 无 API key 时 LLM 真实调用行为] AC-008-01, AC-008-02, AC-008-03 | LLMService 无 DEEPSEEK_API_KEY 时使用 Mock fallback，仅验证 Mock 模式下的接口契约和输出结构。真实 LLM 调用质量需在有 API key 的集成环境验证 |
| [NOT_TESTABLE — Chroma 向量库依赖 embedding API] AC-008-02 | RAGService 的 Chroma search() 在无 embedding API key 时使用 fallback 关键词匹配，语义检索精度需在有 embedding API 的生产环境验证 |
| [NOT_TESTABLE — 真实 SSH 连接] AC-002-05, AC-004-04 | TpLink 工具实现抛出 NotImplementedError，SSH 连接失败处理逻辑仅通过 Mock 模拟验证 |
| [NOT_TESTABLE — 定时器行为] AC-004-01, AC-005-01 | APScheduler 定时触发行为需长时间运行验证，Demo 阶段通过直接调用 run_inspection_once() 验证巡检逻辑 |
| [NOT_TESTABLE — 不可篡改审计日志] AC-010-02 | 审计日志文件 "不可篡改" 属性需在 Linux 文件权限控制下验证，Demo 阶段仅验证日志格式和内容完整性 |

---

## 4. 需求覆盖矩阵

| US-ID | 优先级 | AC 数量 | 测试用例数 | 覆盖状态 |
|-------|--------|---------|-----------|---------|
| US-001 | P0 | 5 | TC-UNIT-001~007,011~013,055,060; TC-INT-001~008,017~020,022,025,027; TC-E2E-001,006,008 | COVERED |
| US-002 | P0 | 5 | TC-UNIT-015,056; TC-INT-008,023; TC-E2E-002 | COVERED |
| US-003 | P1 | 5 | TC-UNIT-058; TC-INT-024; TC-E2E-003 | COVERED |
| US-004 | P1 | 4 | TC-UNIT-014,057; TC-INT-023 | COVERED |
| US-005 | P2 | 3 | TC-UNIT-059; TC-INT-024 | COVERED |
| US-006 | P0 | 6 | TC-UNIT-008,027~038,046~051; TC-INT-011,012,016,029; TC-E2E-004,005,009 | COVERED |
| US-007 | P0 | 4 | TC-INT-013,014,019,028,030,031; TC-E2E-004,005,009 | COVERED |
| US-008 | P0 | 5 | TC-UNIT-021~024; TC-INT-009,010,026; TC-E2E-007 | COVERED |
| US-009 | P0 | 5 | TC-UNIT-065~069; TC-INT-015 | COVERED |
| US-010 | P1 | 3 | [PARTIAL — 审计日志格式验证在单元测试中通过 AuditLogger 间接覆盖] | PARTIAL |
| US-011 | P0 | 4 | TC-UNIT-016~020,025,026; TC-INT-010 | COVERED |

---

## 5. 覆盖率目标

| 指标 | 目标 | 验证方法 |
|------|------|---------|
| 单元测试通过率 | >= 80% | pytest pass/(pass+fail) |
| 集成测试通过率 | >= 90% | pytest pass/(pass+fail) |
| E2E Critical Path 覆盖率 (Must Have 故事) | 100% | US-001, US-002, US-006, US-007, US-008, US-009, US-011 全部 E2E 覆盖 |
| OutputValidator CLI 注入检测 | 100% | 黑名单正则全模式覆盖 (shutdown, reload, vlan, interface, router, configure) |
| Mock 工具层诊断数据格式 | 3/3 告警类型 | MAC_FLAPPING, PORT_DOWN, CPU_HIGH 各至少 1 个诊断数据验证 |
