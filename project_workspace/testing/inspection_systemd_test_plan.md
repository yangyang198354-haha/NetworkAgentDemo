<file_header>
  <author_agent>sub_agent_test_engineer</author_agent>
  <timestamp>2026-07-12T00:00:00Z</timestamp>
  <project_name>NetworkAgentDemo</project_name>
  <version>0.2.0</version>
  <input_files>
    <file>requirements/inspection_systemd_requirements.md</file>
    <file>requirements/inspection_systemd_user_stories.md</file>
    <file>architecture/inspection_systemd_module_design.md</file>
    <file>src/systemd/systemctl_executor.py</file>
    <file>src/systemd/systemd_unit_manager.py</file>
    <file>src/inspection_cli.py</file>
    <file>src/api/inspection_router.py</file>
    <file>src/database/inspection_models.py</file>
    <file>src/database/repositories/inspection_repository.py</file>
  </input_files>
  <phase>PHASE_INSP_04</phase>
  <status>APPROVED</status>
</file_header>

# 巡检机制 systemd 重构 -- 测试计划

---

## 1. 测试策略

### 1.1 测试目标

验证 NetworkAgentDemo v0.2.0 巡检机制 systemd 重构的所有功能需求（REQ-INSP-001 ~ REQ-INSP-017）和非功能需求（REQ-INSP-NF-001 ~ REQ-INSP-NF-007），确保代码质量达到以下门控标准：

| 测试阶段 | 通过率门控 | 说明 |
|---------|-----------|------|
| 单元测试 (UNIT) | >= 80% | 单函数/单类行为验证 |
| 集成测试 (INT) | >= 90% | 多模块协作验证 |
| E2E 测试 (E2E) | Critical Path 100% | 完整用户旅程验证 |

### 1.2 测试范围

**In-Scope：**
- MOD-INSP-001 (systemd_unit_manager): 所有 6 个 IFC 方法
- MOD-INSP-002 (systemctl_executor): 所有 9 个 IFC 方法
- MOD-INSP-003 (inspection_cli): 所有 3 个 IFC 方法 + CLI 入口
- MOD-WEB-001 (inspection_router): 6 个新增端点 + 4 个增强端点
- MOD-WEB-003 (inspection_models): status 字段枚举约束
- MOD-WEB-004 (inspection_repository): 5 个新增/增强方法
- 用户故事 US-INSP-001 ~ US-INSP-008: 全部 44 条验收标准

**Out-of-Scope：**
- 前端 Vue 3 组件 (InspectionConfigView.vue, inspection.ts Pinia store) -- 无浏览器测试环境
- 告警处理流程 (LangGraph 工作流) -- 不属于 v0.2.0 巡检调度重构范围
- systemd 真实环境部署验证 -- 开发环境 Windows，systemd 不可用
- APScheduler 迁移脚本执行 -- 为需求验证而非代码测试

### 1.3 测试环境

- OS: Windows 11 Pro (开发环境，systemd 不可用)
- Python: 3.11
- 测试框架: pytest >= 8.0
- 数据库: SQLite 内存模式 (通过现有 SessionLocal override)
- Mock 策略: systemctl 命令通过 `unittest.mock.patch` 模拟 `subprocess.run` 返回
- 覆盖率工具: pytest-cov

### 1.4 测试分类规则

| AC 特征 | 测试级别 | 判定标准 |
|---------|---------|---------|
| Given/When/Then 仅涉及单个函数/方法/类的行为 | UNIT | 单模块内可独立验证 |
| Given/When/Then 涉及两个或多个模块的协作 | INT | 需要多个真实模块交互 |
| Given/When/Then 描述完整的用户操作路径（Web API 请求-响应） | E2E | 从 HTTP 入口到数据持久化的全链路 |

### 1.5 覆盖率目标

| 测试级别 | 目标通过率 | 目标代码覆盖率 |
|---------|-----------|--------------|
| UNIT | >= 80% | >= 80% (行覆盖) |
| INT | >= 90% | >= 90% (行覆盖) |
| E2E | Critical Path 100% | Must Have 故事 100% 路径覆盖 |

---

## 2. 测试用例清单

### 2.1 单元测试用例 (TC-UNIT-*)

#### 2.1.1 MOD-INSP-002: systemctl_executor

| TC-ID | 所属US | 关联AC | 级别 | 描述 | 前置条件 | 动作 | 预期结果 | 测试数据 | 备注 |
|-------|--------|--------|------|------|---------|------|---------|---------|------|
| TC-UNIT-001 | US-INSP-003 | AC-INSP-004-01 | UNIT | check_systemd_available 返回 available=true | mock os.path.exists=True, shutil.which 返回路径 | 调用 check_systemd_available() | SystemdAvailability(available=True) | mock /run/systemd/system 存在 | |
| TC-UNIT-002 | US-INSP-003 | AC-INSP-004-02 | UNIT | check_systemd_available 返回 available=false (目录不存在) | mock os.path.exists=False | 调用 check_systemd_available() | SystemdAvailability(available=False) | mock 目录不存在 | |
| TC-UNIT-003 | US-INSP-003 | AC-INSP-004-02 | UNIT | check_systemd_available 返回 available=false (which 失败) | mock os.path.exists=True, shutil.which=None | 调用 check_systemd_available() | SystemdAvailability(available=False) | mock which 返回 None | |
| TC-UNIT-004 | US-INSP-003 | AC-INSP-004-01 | UNIT | get_timer_status 正常解析 active+enabled 状态 | mock subprocess.run 返回 active/enabled 输出 | 调用 get_timer_status() | TimerStatus(active_state="active", unit_file_state="enabled", next_trigger 为有效 datetime) | mock systemctl show 输出 | |
| TC-UNIT-005 | US-INSP-003 | AC-INSP-004-02 | UNIT | get_timer_status 处理 unit 不存在 | mock subprocess.run 返回非0退出码 | 调用 get_timer_status() | TimerStatus(active_state="not-found", unit_file_state="not-found") | mock 非0返回码 | |
| TC-UNIT-006 | US-INSP-003 | AC-INSP-004-01 | UNIT | get_service_status 正常解析 running 状态 | mock subprocess.run 返回 service 输出 | 调用 get_service_status() | ServiceStatus(active_state="active", sub_state="running") | mock systemctl show 输出 | |
| TC-UNIT-007 | US-INSP-003 | AC-INSP-004-02 | UNIT | get_service_status 处理 unit 不存在 | mock subprocess.run 返回错误 | 调用 get_service_status() | ServiceStatus(active_state="not-found") | mock 异常 | |
| TC-UNIT-008 | US-INSP-004 | AC-INSP-006-01 | UNIT | start_service 返回成功结果 | mock subprocess.run 返回 returncode=0 | 调用 start_service() | SystemctlResult(success=True, action="start") | mock 成功 | |
| TC-UNIT-009 | US-INSP-004 | AC-INSP-006-02 | UNIT | stop_service 返回成功结果 | mock subprocess.run 返回 returncode=0 | 调用 stop_service() | SystemctlResult(success=True, action="stop") | mock 成功 | |
| TC-UNIT-010 | US-INSP-004 | AC-INSP-006-03 | UNIT | restart_service 返回成功结果 | mock subprocess.run 返回 returncode=0 | 调用 restart_service() | SystemctlResult(success=True, action="restart") | mock 成功 | |
| TC-UNIT-011 | US-INSP-005 | AC-INSP-007-01 | UNIT | enable_timer 正常启用 timer | mock get_timer_status 返回 inactive, subprocess.run 返回成功 | 调用 enable_timer() | SystemctlResult(success=True, action="enable") | mock 成功 | |
| TC-UNIT-012 | US-INSP-005 | AC-INSP-007-03 | UNIT | enable_timer 幂等处理 (已 enabled) | mock get_timer_status 返回 active+enabled | 调用 enable_timer() | SystemctlResult(success=True, message 含"无需操作") | 幂等检查 | |
| TC-UNIT-013 | US-INSP-005 | AC-INSP-007-02 | UNIT | disable_timer 正常禁用 timer | mock get_timer_status 返回 active+enabled, subprocess.run 返回成功 | 调用 disable_timer() | SystemctlResult(success=True, action="disable") | mock 成功 | |
| TC-UNIT-014 | US-INSP-005 | AC-INSP-005-05 | UNIT | disable_timer 幂等处理 (已 disabled) | mock get_timer_status 返回 disabled+inactive | 调用 disable_timer() | SystemctlResult(success=True, message 含"已处于禁用状态") | 幂等检查 | |
| TC-UNIT-015 | US-INSP-002 | AC-INSP-003-01 | UNIT | daemon_reload 返回成功结果 | mock subprocess.run 返回 returncode=0 | 调用 daemon_reload() | SystemctlResult(success=True, action="daemon-reload") | mock 成功 | |
| TC-UNIT-016 | US-INSP-004 | AC-INSP-006-04 | UNIT | systemctl 命令执行失败时抛出 SystemctlPermissionError | mock subprocess.run 返回 stderr 含 "Interactive authentication required" | 调用 start_service() | 抛出 SystemctlPermissionError | 权限错误 | |
| TC-UNIT-017 | US-INSP-003 | AC-INSP-004-03 | UNIT | systemctl show 超时时抛出 SystemctlTimeoutError | mock subprocess.run 抛出 TimeoutExpired | 调用 get_timer_status() | 抛出 SystemctlTimeoutError | 超时处理 | |
| TC-UNIT-018 | US-INSP-003 | AC-INSP-NF-006-01 | UNIT | systemd 不可用时 get_timer_status 返回 not-found | mock check_systemd_available 返回 False | 调用 get_timer_status() | TimerStatus(active_state="not-found") | 降级处理 | |
| TC-UNIT-019 | US-INSP-003 | AC-INSP-NF-006-01 | UNIT | systemd 不可用时 get_service_status 返回 not-found | mock check_systemd_available 返回 False | 调用 get_service_status() | ServiceStatus(active_state="not-found") | 降级处理 | |
| TC-UNIT-020 | US-INSP-004 | AC-INSP-NF-003-03 | UNIT | subprocess.run 使用 shell=False (命令注入防护) | 无 | 断言内部 subprocess.run 调用的 shell 参数 | shell=False | 安全验证 | |
| TC-UNIT-021 | US-INSP-003 | AC-INSP-NF-006-01 | UNIT | systemd 不可用时 _exec_systemctl 返回失败结果 | mock check_systemd_available 返回 False | 调用 _exec_systemctl("start", "unit") | SystemctlResult(success=False) | 降级处理 | |

#### 2.1.2 MOD-INSP-001: systemd_unit_manager

| TC-ID | 所属US | 关联AC | 级别 | 描述 | 前置条件 | 动作 | 预期结果 | 测试数据 | 备注 |
|-------|--------|--------|------|------|---------|------|---------|---------|------|
| TC-UNIT-030 | US-INSP-002 | AC-INSP-002-01 | UNIT | generate_service_unit 渲染正确 | config dict 含 timeout_seconds=30 | 调用 generate_service_unit(config) | 返回字符串含 "Type=oneshot", "ExecStart=python3.11 -m src.inspection_cli run", "TimeoutStopSec=30" | Jinja2 模板渲染 | |
| TC-UNIT-031 | US-INSP-002 | AC-INSP-002-02 | UNIT | generate_timer_unit 渲染正确 (interval_minutes=10) | config dict 含 interval_minutes=10 | 调用 generate_timer_unit(config) | 返回字符串含 "OnUnitActiveSec=600", "Unit=networkagent-inspection.service", "Persistent=true" | 分钟转秒 | |
| TC-UNIT-032 | US-INSP-002 | AC-INSP-002-03 | UNIT | generate_timer_unit 渲染正确 (interval_minutes=5) | config dict 含 interval_minutes=5 | 调用 generate_timer_unit(config) | 返回字符串含 "OnUnitActiveSec=300" | 分钟转秒 | |
| TC-UNIT-033 | US-INSP-002 | AC-INSP-002-03 | UNIT | generate_service_unit 使用默认值 | config dict 为空 | 调用 generate_service_unit({}) | 返回含 timeout_stop_sec=30, restart_sec=30 | 默认值 | |
| TC-UNIT-034 | US-INSP-002 | AC-INSP-002-04 | UNIT | write_unit_files 目录不存在时返回失败 | mock SYSTEMD_DIR.exists=False | 调用 write_unit_files("svc", "tmr") | WriteResult(success=False, error 含"not found") | 错误处理 | |
| TC-UNIT-035 | US-INSP-002 | AC-INSP-002-04 | UNIT | write_unit_files PermissionError 处理 | mock 写入抛出 PermissionError | 调用 write_unit_files("svc", "tmr") | WriteResult(success=False, error 含"权限不足") | 权限错误 | |
| TC-UNIT-036 | US-INSP-002 | AC-INSP-002-05 | UNIT | write_unit_files 幂等跳过 (内容未变) | mock 文件已存在且内容一致 | 调用 write_unit_files("svc", "tmr") | WriteResult(success=True, files_written=[]) | 幂等检查 | |
| TC-UNIT-037 | US-INSP-002 | AC-INSP-002-05 | UNIT | is_config_changed 返回 False (配置未变) | mock 文件存在且生成内容一致 | 调用 is_config_changed(new_config) | False | 幂等检查 | |
| TC-UNIT-038 | US-INSP-002 | AC-INSP-002-04 | UNIT | is_config_changed 返回 True (文件不存在) | mock 文件不存在 | 调用 is_config_changed(new_config) | True | 变更检测 | |
| TC-UNIT-039 | US-INSP-002 | AC-INSP-003-01 | UNIT | sync_config_to_systemd 完整链路 (成功) | mock 所有步骤成功 | 调用 sync_config_to_systemd(config) | SyncResult(success=True, actions 含 daemon-reload) | 全链路 | |
| TC-UNIT-040 | US-INSP-002 | AC-INSP-003-03 | UNIT | sync_config_to_systemd timer inactive 时不 restart | mock timer active_state=inactive | 调用 sync_config_to_systemd(config) | SyncResult(success=True, timer_was_active=False) | 首次部署 | |
| TC-UNIT-041 | US-INSP-002 | AC-INSP-003-02 | UNIT | sync_config_to_systemd timer active 时 restart | mock timer active_state=active | 调用 sync_config_to_systemd(config) | SyncResult(success=True, timer_was_active=True) | active 重载 | |
| TC-UNIT-042 | US-INSP-002 | AC-INSP-002-05 | UNIT | sync_config_to_systemd 幂等跳过 (配置未变) | mock is_config_changed 返回 False | 调用 sync_config_to_systemd(config) | SyncResult(success=True, actions 含"skipped") | 幂等跳过 | |
| TC-UNIT-043 | US-INSP-002 | AC-INSP-002-04 | UNIT | sync_config_to_systemd systemd 不可用时返回失败 | mock check_systemd_available 返回 False | 调用 sync_config_to_systemd(config) | SyncResult(success=False, error 含"不可用") | 降级处理 | |
| TC-UNIT-044 | US-INSP-002 | AC-INSP-002-04 | UNIT | sync_config_to_systemd 模板渲染失败 | mock generate_service_unit 抛出 ValueError | 调用 sync_config_to_systemd(config) | SyncResult(success=False, error 含"渲染失败") | 错误处理 | |
| TC-UNIT-045 | US-INSP-002 | AC-INSP-002-04 | UNIT | sync_config_to_systemd write_unit_files 失败 | mock write_unit_files 返回失败 | 调用 sync_config_to_systemd(config) | SyncResult(success=False, error=write_result.error) | 错误处理 | |
| TC-UNIT-046 | US-INSP-002 | AC-INSP-003-01 | UNIT | sync_config_to_systemd daemon-reload 失败 | mock daemon_reload 返回失败 | 调用 sync_config_to_systemd(config) | SyncResult(success=False, error 含"daemon-reload 失败") | 错误处理 | |
| TC-UNIT-047 | US-INSP-002 | AC-INSP-002-01 | UNIT | verify_unit_files systemd 不可用时跳过并返回 success | mock check_systemd_available=False | 调用 verify_unit_files() | VerifyResult(success=True) | 降级处理 | |
| TC-UNIT-048 | US-INSP-002 | AC-INSP-002-01 | UNIT | verify_unit_files 文件不存在时报告错误 | mock 文件不存在 | 调用 verify_unit_files() | VerifyResult(success=False, errors 非空) | 错误处理 | |

#### 2.1.3 MOD-WEB-003: inspection_models

| TC-ID | 所属US | 关联AC | 级别 | 描述 | 前置条件 | 动作 | 预期结果 | 测试数据 | 备注 |
|-------|--------|--------|------|------|---------|------|---------|---------|------|
| TC-UNIT-060 | US-INSP-007 | AC-INSP-010-01 | UNIT | InspectionRecord status 字段默认值为 SUCCESS | 无 | 创建 InspectionRecord 实例 | record.status == "SUCCESS" | 默认值验证 | |
| TC-UNIT-061 | US-INSP-007 | AC-INSP-010-01 | UNIT | InspectionRecord status 接受 SUCCESS/PARTIAL/FAILED | 无 | 分别设置 status | 三种值均被接受 | 枚举约束 | |
| TC-UNIT-062 | US-INSP-007 | AC-INSP-010-03 | UNIT | InspectionRecord status 拒绝非法值 | 无 | 设置 status="INVALID_LONG_STRING_EXCEEDING_15_CHARS" | 预期抛出 ValueError 或截断 | 长度约束 (VARCHAR 15) | |

#### 2.1.4 MOD-INSP-003: inspection_cli

| TC-ID | 所属US | 关联AC | 级别 | 描述 | 前置条件 | 动作 | 预期结果 | 测试数据 | 备注 |
|-------|--------|--------|------|------|---------|------|---------|---------|------|
| TC-UNIT-070 | US-INSP-008 | AC-INSP-014-01 | UNIT | CLIExitCode 枚举值正确 | 无 | 访问 CLIExitCode.SUCCESS/PARTIAL/FAILURE | 值分别为 0/1/2 | 枚举定义 | |
| TC-UNIT-071 | US-INSP-008 | AC-INSP-014-01 | UNIT | load_inspection_config 从 SQLite 读取配置 | mock repo.get_config 返回数据 | 调用 load_inspection_config() | 返回 dict 含 interval_minutes 等 4 个键 | SQLite 优先 | |
| TC-UNIT-072 | US-INSP-001 | AC-INSP-012-01 | UNIT | load_inspection_config SQLite 优先于 config.yaml | mock SQLite 返回 interval_minutes=15, config.yaml 有 interval_minutes=5 | 调用 load_inspection_config() | interval_minutes=15 | 优先级验证 | |
| TC-UNIT-073 | US-INSP-001 | AC-INSP-012-02 | UNIT | load_inspection_config SQLite 无值时降级到 config.yaml | mock repo.get_config 返回空, config.yaml 有默认值 | 调用 load_inspection_config() | 返回 config.yaml 的默认值 | 降级链 | |
| TC-UNIT-074 | US-INSP-008 | AC-INSP-014-03 | UNIT | load_device_list 返回设备列表 | mock Device 表有 2 条记录 | 调用 load_device_list() | 返回 2 个 dict, 含 device_name/device_ip/device_model | 设备查询 | |
| TC-UNIT-075 | US-INSP-008 | AC-INSP-014-03 | UNIT | load_device_list 无 DB session 时返回空列表 | db_session=None | 调用 load_device_list() | 返回 [] | 空异常处理 | |
| TC-UNIT-076 | US-INSP-008 | AC-INSP-014-01 | UNIT | CLI run 方法空设备列表返回 SUCCESS | mock 无设备 | 调用 cli.run() | CLIExitCode.SUCCESS | 空设备处理 | |

#### 2.1.5 MOD-WEB-004: inspection_repository

| TC-ID | 所属US | 关联AC | 级别 | 描述 | 前置条件 | 动作 | 预期结果 | 测试数据 | 备注 |
|-------|--------|--------|------|------|---------|------|---------|---------|------|
| TC-UNIT-080 | US-INSP-001 | AC-INSP-001-01 | UNIT | get_config 返回 4 个配置键 | 数据库中无配置记录 | 调用 get_config() | 返回 dict 含 diagnosis.retry_backoff 等 4 个键，值为 "" | 新配置键 | |
| TC-UNIT-081 | US-INSP-001 | AC-INSP-001-02 | UNIT | update_config 写入新配置键 | body 含 retry_backoff_seconds=10 | 调用 update_config({"diagnosis.retry_backoff": "10"}) | get_config 返回 retry_backoff="10" | upsert 逻辑 | |
| TC-UNIT-082 | US-INSP-001 | AC-INSP-012-03 | UNIT | update_config 更新已有配置键 | body 含 retry_backoff_seconds=15 | update_config 后再 get_config | retry_backoff 值为 "15" | 更新逻辑 | |
| TC-UNIT-083 | US-INSP-006 | AC-INSP-009-01 | UNIT | create_record 创建 InspectionRecord | record_data 含完整字段 | 调用 create_record(data) | 返回 InspectionRecord 实例, status 默认 SUCCESS | 记录创建 | |
| TC-UNIT-084 | US-INSP-007 | AC-INSP-011-01 | UNIT | get_latest_inspection 返回最近记录 | 表中有多条记录 | 调用 get_latest_inspection() | 返回 completed_at 最晚的记录 dict | 降序取首 | |
| TC-UNIT-085 | US-INSP-007 | AC-INSP-011-01 | UNIT | get_latest_inspection 无记录时返回 None | 表中无记录 | 调用 get_latest_inspection() | None | 空处理 | |
| TC-UNIT-086 | US-INSP-006 | AC-INSP-009-01 | UNIT | get_devices_for_inspection 返回设备列表 | Device 表有记录 | 调用 get_devices_for_inspection() | 返回 list[dict] 含 device_name/device_ip/device_model | 设备查询 | |
| TC-UNIT-087 | US-INSP-007 | AC-INSP-007-02 | UNIT | list_history 按 trigger_mode 筛选 | 表中有 SCHEDULED 和 MANUAL 记录 | 调用 list_history(trigger_mode="MANUAL") | items 全为 MANUAL | 触发方式筛选 | |
| TC-UNIT-088 | US-INSP-007 | AC-INSP-007-03 | UNIT | list_history 按 status 筛选 | 表中有 SUCCESS/PARTIAL/FAILED | 调用 list_history(status="FAILED") | items 全为 FAILED | 状态筛选 | |
| TC-UNIT-089 | US-INSP-007 | AC-INSP-007-01 | UNIT | list_history 分页 | 表中有 25 条记录 | 调用 list_history(page=2, page_size=10) | page=2, 返回 10 条 | 分页 | |

### 2.2 集成测试用例 (TC-INT-*)

| TC-ID | 所属US | 关联AC | 级别 | 描述 | 前置条件 | 动作 | 预期结果 | 测试数据 | 备注 |
|-------|--------|--------|------|------|---------|------|---------|---------|------|
| TC-INT-100 | US-INSP-002 | AC-INSP-002-01 | INT | SystemdUnitManager + SystemctlExecutor 完整同步链路 | mock subprocess 成功 | manager.sync_config_to_systemd(config) | SyncResult(success=True), template rendered, files written, daemon-reload called | config={interval_minutes:10, timeout_seconds:30} | 模块协作 |
| TC-INT-101 | US-INSP-003 | AC-INSP-003-01 | INT | inspection_router GET /status 返回完整状态 (systemd 可用) | mock systemctl show 输出 | FastAPI TestClient GET /api/inspection/status | 200, InspectionStatusResponse 含 timer+service+last_inspection | mock 可用环境 | |
| TC-INT-102 | US-INSP-003 | AC-INSP-NF-006-02 | INT | inspection_router GET /status 降级返回 (systemd 不可用) | mock check_systemd_available=False | FastAPI TestClient GET /api/inspection/status | 200, systemd_available=False, timer=None, service=None | mock 不可用 | |
| TC-INT-103 | US-INSP-004 | AC-INSP-004-01 | INT | inspection_router POST /start 成功启动 | mock start_service 成功 | FastAPI TestClient POST /api/inspection/start | 200, result="success", action="start" | mock 成功 | |
| TC-INT-104 | US-INSP-004 | AC-INSP-004-02 | INT | inspection_router POST /stop 成功停止 | mock stop_service 成功 | FastAPI TestClient POST /api/inspection/stop | 200, result="success", action="stop" | mock 成功 | |
| TC-INT-105 | US-INSP-004 | AC-INSP-004-03 | INT | inspection_router POST /restart 成功重启 | mock restart_service 成功 | FastAPI TestClient POST /api/inspection/restart | 200, result="success", action="restart" | mock 成功 | |
| TC-INT-106 | US-INSP-005 | AC-INSP-005-01 | INT | inspection_router POST /enable 成功启用 | mock enable_timer 成功 | FastAPI TestClient POST /api/inspection/enable | 200, result="success", action="enable" | mock 成功 | |
| TC-INT-107 | US-INSP-005 | AC-INSP-005-02 | INT | inspection_router POST /disable 成功禁用 | mock disable_timer 成功 | FastAPI TestClient POST /api/inspection/disable | 200, result="success", action="disable" | mock 成功 | |
| TC-INT-108 | US-INSP-001 | AC-INSP-001-02 | INT | inspection_router PUT /config 保存配置+systemd同步 | mock repo 写入成功 + sync 成功 | FastAPI TestClient PUT /api/inspection/config | 200, systemd_sync="success", config 含 retry_backoff | body 含 retry_backoff_seconds=10 | |
| TC-INT-109 | US-INSP-001 | AC-INSP-001-05 | INT | inspection_router PUT /config systemd 同步失败时返回部分成功 | mock sync 失败 | FastAPI TestClient PUT /api/inspection/config | 200, systemd_sync="failed", systemd_error 含具体错误 | 部分成功处理 | |
| TC-INT-110 | US-INSP-006 | AC-INSP-006-01 | INT | inspection_router POST /trigger 成功触发巡检 | mock start_service 成功 | FastAPI TestClient POST /api/inspection/trigger | 200, result="success", trigger_mode="MANUAL" | systemd 可用 | |
| TC-INT-111 | US-INSP-006 | AC-INSP-006-02 | INT | inspection_router POST /trigger 巡检进行中返回 409 | mock get_service_status sub_state=running | FastAPI TestClient POST /api/inspection/trigger | 409, detail 含"正在执行中" | 防重复触发 | |
| TC-INT-112 | US-INSP-006 | AC-INSP-NF-006-03 | INT | inspection_router POST /trigger systemd 不可用返回 503 | mock check_systemd_available=False | FastAPI TestClient POST /api/inspection/trigger | 503, detail 含"不支持 systemd" | 不可用降级 | |
| TC-INT-113 | US-INSP-004 | AC-INSP-NF-006-02 | INT | inspection_router POST /start systemd 不可用返回 503 | mock check_systemd_available=False | FastAPI TestClient POST /api/inspection/start | 503 | 不可用降级 | |
| TC-INT-114 | US-INSP-007 | AC-INSP-007-01 | INT | inspection_router GET /history 分页查询 | 表中有记录 | FastAPI TestClient GET /api/inspection/history?page=1&page_size=10 | 200, items/ total/ page/ page_size | 分页 | |
| TC-INT-115 | US-INSP-007 | AC-INSP-007-02 | INT | inspection_router GET /history 按 trigger_mode 筛选 | 表中有不同类型记录 | FastAPI TestClient GET /api/inspection/history?trigger_mode=SCHEDULED | 200, items 全为 SCHEDULED | 筛选 | |
| TC-INT-116 | US-INSP-007 | AC-INSP-007-03 | INT | inspection_router GET /history 按 status 筛选 | 表中有不同状态 | FastAPI TestClient GET /api/inspection/history?status=SUCCESS | 200, items 全为 SUCCESS | 状态筛选 | |
| TC-INT-117 | US-INSP-001 | AC-INSP-001-01 | INT | inspection_router GET /config 返回含 retry_backoff | 已配置 retry_backoff=10 | FastAPI TestClient GET /api/inspection/config | 200, config.diagnosis.retry_backoff="10" | 配置读取 | |
| TC-INT-118 | US-INSP-001 | AC-INSP-001-03 | INT | inspection_router PUT /config 参数校验 (负值) | body 含 interval_minutes=-1 | FastAPI TestClient PUT /api/inspection/config | 422 Validation Error | 参数校验 | |
| TC-INT-119 | US-INSP-008 | AC-INSP-014-01 | INT | inspection_cli run 完整执行流程 (mock devices) | mock DB 有 2 设备, mock diag 成功 | 调用 cli.run() | CLIExitCode.SUCCESS, InspectionRecord 创建 | 全链路 | |
| TC-INT-120 | US-INSP-008 | AC-INSP-014-02 | INT | inspection_cli run 部分异常返回 PARTIAL | mock 1 设备 CPU 超标 | 调用 cli.run() | CLIExitCode.PARTIAL, anomaly_count>0 | 部分异常 | |

### 2.3 E2E 测试用例 (TC-E2E-*)

| TC-ID | 所属US | 关联AC | 级别 | 描述 | 前置条件 | 动作 | 预期结果 | 测试数据 | 备注 |
|-------|--------|--------|------|------|---------|------|---------|---------|------|
| TC-E2E-200 | US-INSP-001 | AC-INSP-001-01~05 | E2E | 巡检配置管理完整用户旅程 | FastAPI App + test DB | GET config → PUT config (修改) → GET config 验证 | 配置读写一致，systemd 同步触发 | test DB 内存模式 | Critical Path |
| TC-E2E-201 | US-INSP-002 | AC-INSP-002-01~05 | E2E | systemd unit 文件生成完整流程 | mock systemctl | PUT config → 验证 unit 文件生成 (template → write → daemon-reload) | unit 文件正确生成，sync 链完成 | Jinja2 模板 | Critical Path |
| TC-E2E-202 | US-INSP-003 | AC-INSP-003-01~05 | E2E | 巡检状态查询完整用户旅程 | FastAPI App + mock systemctl | GET /status (可用) → GET /status (不可用) | 两种场景均返回正确响应 | mock 两种环境 | Critical Path |
| TC-E2E-203 | US-INSP-004 | AC-INSP-004-01~06 | E2E | 巡检服务生命周期控制完整旅程 | FastAPI App + mock systemctl | start → status验证 → stop → status验证 → restart → status验证 | 每步操作成功，状态正确反映 | mock 命令成功/失败 | Critical Path |
| TC-E2E-204 | US-INSP-005 | AC-INSP-005-01~05 | E2E | Timer 启用/禁用完整旅程 | FastAPI App + mock systemctl | enable → status验证 → disable → status验证 → enable幂等 | 操作正确，幂等检查生效 | mock 状态切换 | Critical Path |
| TC-E2E-205 | US-INSP-006 | AC-INSP-006-01~05 | E2E | 手动触发巡检完整旅程 | FastAPI App + mock systemctl | trigger → history验证 → trigger(重复)409 → trigger(不可用)503 | 触发成功/防重/降级正确处理 | mock 三种场景 | Critical Path |
| TC-E2E-206 | US-INSP-007 | AC-INSP-007-01~06 | E2E | 巡检历史查询完整旅程 | FastAPI App + 多条历史记录 | GET history → 分页 → trigger_mode筛选 → status筛选 → 详情查看 | 全部筛选和分页正确 | 预置 25 条记录 | Critical Path |
| TC-E2E-207 | US-INSP-008 | AC-INSP-008-01~07 | E2E | systemd 定时触发 CLI 巡检完整旅程 | mock CLI 执行环境 | mock timer 触发 → CLI run → SQLite 写入 → 验证 InspectionRecord | CLI 正确执行，记录持久化，退出码正确 | 2 设备场景 | Critical Path |
| TC-E2E-208 | US-INSP-001~008 | ALL ACs | E2E | 跨用户故事完整流程: 配置→同步→状态→控制→触发→历史 | FastAPI App | 顺序执行所有端点的典型操作 | 全流程无错误，数据一致性验证 | 全模块 | Critical Path (Must Have 全链路) |

---

## 3. 不可测试项

| AC-ID | 原因 |
|-------|------|
| AC-INSP-005-01 ~ AC-INSP-005-03 | Web UI 前端组件 (InspectionConfigView.vue) -- 无浏览器测试环境 |
| AC-INSP-008-01 ~ AC-INSP-008-04 | Web UI 前端按钮交互 -- 无浏览器测试环境 |
| AC-INSP-NF-001-01 | systemd timer 触发精度偏差 -- 需要真实 Linux systemd 环境持续运行 10 个周期 |
| AC-INSP-NF-002-01 | systemd service on-failure 自动重启 -- 需要真实 systemd 环境验证 systemd 层行为 |
| AC-INSP-NF-002-02 | 正常退出不重启 -- 同上，systemd 层行为 |
| AC-INSP-NF-003-01 | sudoers 配置正确后命令执行成功 -- 需要真实 Linux root/sudo 环境 |
| AC-INSP-NF-003-02 | 未配置 sudoers 返回友好错误 -- 已通过代码逻辑 mock 测试 (TC-INT-112 等) |
| AC-INSP-NF-004-01 | Web 重启不影响巡检 -- 需要真实多进程环境 |
| AC-INSP-NF-004-02 | 巡检崩溃不影响 Web -- 需要真实多进程环境 |
| AC-INSP-NF-005-01 | 巡检 CLI 不监听端口 -- 可通过代码审查验证 (CLI 无端口绑定代码) |
| AC-INSP-NF-005-02 | systemd unit 文件不绑定端口 -- 已通过模板内容测试覆盖 (TC-UNIT-030) |
| AC-INSP-NF-006-01 | 不支持 systemd 时状态面板降级 -- Web UI 前端组件 |
| AC-INSP-NF-007-01 | journalctl 可查看巡检日志 -- 需要真实 systemd journald 环境 |
| AC-INSP-NF-007-02 | 错误日志记录 -- 同上 |
| AC-INSP-016-02 | Persistent=true 行为验证 -- 需要真实 systemd 环境 + 系统重启 |
| AC-INSP-017-01 | Web 进程启动不初始化 APScheduler -- 需要检查 main.py 启动逻辑 |
| AC-INSP-017-02 | 巡检核心逻辑迁移至 CLI -- 已通过 CLI 测试覆盖 |
| AC-INSP-017-03 | apscheduler 依赖移除 -- 需要检查 requirements.txt |

---

## 4. 需求覆盖矩阵

| US-ID | 故事名称 | AC 总数 | 可测试 AC | 不可测试 AC | UNIT TC | INT TC | E2E TC |
|-------|---------|---------|-----------|------------|---------|--------|--------|
| US-INSP-001 | Web UI 配置巡检参数并持久化 | 5 | 4 | 1 (前端) | 6 | 4 | 1 |
| US-INSP-002 | 配置保存后自动生成 systemd unit 文件 | 5 | 5 | 0 | 19 | 1 | 1 |
| US-INSP-003 | Web UI 查看巡检服务实时状态 | 5 | 4 | 1 (前端) | 10 | 2 | 1 |
| US-INSP-004 | Web UI 控制巡检服务启动/停止/重启 | 6 | 5 | 1 (前端) | 6 | 3 | 1 |
| US-INSP-005 | Web UI 启用/禁用巡检定时器 | 5 | 4 | 1 (前端) | 4 | 2 | 1 |
| US-INSP-006 | 手动触发一次巡检 | 5 | 4 | 1 (前端) | 1 | 3 | 1 |
| US-INSP-007 | 查看巡检历史记录 | 6 | 5 | 1 (前端) | 9 | 3 | 1 |
| US-INSP-008 | systemd 定时触发 CLI 巡检进程 | 7 | 3 | 4 (systemd环境) | 7 | 2 | 1 |
| **总计** | | **44** | **34** | **10** | **62** | **20** | **8** |

---

## 5. 测试代码文件清单

| 文件路径 | 测试对象 | 测试级别 | 预计 TC 数 |
|---------|---------|---------|-----------|
| `tests/test_inspection_systemd_models.py` | MOD-WEB-003 inspection_models | UNIT | 3 |
| `tests/test_inspection_systemd_repository.py` | MOD-WEB-004 inspection_repository | UNIT | 10 |
| `tests/test_inspection_systemd_executor.py` | MOD-INSP-002 systemctl_executor | UNIT | 21 |
| `tests/test_inspection_systemd_unit_manager.py` | MOD-INSP-001 systemd_unit_manager | UNIT | 19 |
| `tests/test_inspection_systemd_cli.py` | MOD-INSP-003 inspection_cli | UNIT | 7 |
| `tests/test_inspection_systemd_integration.py` | MOD-WEB-001 + MOD-INSP-001/002 协作 | INT | 20 |
| `tests/test_inspection_systemd_e2e.py` | 全链路 E2E | E2E | 8 |

---

## 6. 门控条件回顾

| 阶段 | 门控条件 | 判定 |
|------|---------|------|
| 单元测试 | pass / (pass + fail) >= 80% | 满足后方可进入集成测试 |
| 集成测试 | pass / (pass + fail) >= 90% | 满足后方可进入 E2E 测试 |
| E2E 测试 | Critical Path (Must Have 故事) 覆盖率 100% | 所有 TC-E2E-200~208 必须执行且至少一个完成 |

</file_header>