<file_header>
  <project_id>NetworkAgentDemo</project_id>
  <module_id>real_device_panel</module_id>
  <doc_type>test_plan</doc_type>
  <file_name>real_panel_test_plan.md</file_name>
  <version>0.1.0</version>
  <status>APPROVED</status>
  <author_agent>sub_agent_test_engineer</author_agent>
  <created_at>2026-09-05T00:00:00Z</created_at>
  <last_updated>2026-09-05T00:00:00Z</last_updated>
  <invocation_id>inv-real-panel-d-001</invocation_id>
  <input_source>PM agent_invocation — REAL_DEVICE_PANEL / GROUP_RP_D（测试阶段）</input_source>
</file_header>

# 真实设备（REAL）面板 — 测试计划

## 1. 测试目标

基于已 APPROVED 的需求（9 US + 19 AC）、架构（7 模块 + 11 IFC）与代码评审报告
（CRITICAL 0、MAJOR 3、MINOR 3），对 REAL_DEVICE_PANEL 的 GROUP_RP_D 阶段交付物
实施三级串行测试，验证：

1. TP-Link CLI 解析器（MOD-RP-003）五个 `parse_*` 纯函数与 `RealPanelError` 的正确性。
2. 会话串行化门（MOD-RP-004）`session_key` / `session_guard` / `session_guard_by_access` 语义。
3. 采集服务（MOD-RP-002）动作映射 `_map_action`、`collect_real_panel` 单会话批量采集、
   `configure_real_port` 写操作**不调 save**（AC-RP-005-03）。
4. API 端点（MOD-RP-001）`GET /real_panel` 与写端点 REAL 分支的鉴权/参数校验/错误转换/审计。
5. 写操作安全（REQ-RP-NFUNC-002）：前端二次确认 + 后端审计（operator + detail 无明文密码）。
6. 回归（NFUNC-003）：SIMULATOR 面板/心跳/连通性端点零破坏；前端构建零错误。

## 2. 测试范围

### 2.1 In-scope

| 被测对象 | 文件 | 测试级别 |
|---------|------|---------|
| CLI 输出解析器 | `src/tools/real_panel_parsers.py` | UNIT |
| 会话串行化门 | `src/tools/real_session_gate.py` | UNIT |
| REAL 面板采集服务 | `src/tools/real_panel_service.py` | UNIT |
| REAL 面板 API 端点 | `src/api/devices_router.py`（REAL 分支 + `_configure_real_port`） | INT |
| 工作流工具会话门包裹 | `src/tools/switch_diag_tool.py` / `switch_config_tool.py` | 回归 |
| 前端 store + 抽屉 | `webui/src/stores/devices.ts` / `views/devices/DevicesListView.vue` | 构建 + 静态核对 |
| 既有测试套件回归 | `tests/`（排除 e2e/slow） | 回归 |

### 2.2 Out-of-scope（声明）

- 不修改 `src/` 任何源码（D-001/D-002 由 `tests/conftest.py` 的 `sys.meta_path` 补丁在测试期修复）。
- 不执行对生产交换机（TL-SG5428）的真实写入，除非环境显式提供授权可达的真实设备。
- 不做 Vue 组件级自动化单测（本仓库无 `vitest`/`@vue/test-utils` 测试基建），前端 AC
  以「静态代码核对 + `npm run build` 零错误」覆盖。

## 3. 测试环境

| 项 | 值 |
|----|----|
| OS | Windows 11 Pro 10.0.26200 |
| Python | 3.14.6（`C:\Python314\python.exe`） |
| pytest | 9.1.1（plugins: anyio 4.14.1, langsmith 0.9.6, cov 7.1.0） |
| FastAPI / SQLAlchemy / Pydantic | 0.139.0 / 2.0.51 / 2.13.4 |
| Node / npm | v24.18.0 / 11.16.0（webui node_modules 已就绪） |
| 真实设备 | **无**（本会话无 TL-SG5428 设备接入，E2E 标 NOT_EXECUTED） |

## 4. 测试策略与门控阈值

| 阶段 | 触发条件 | 通过率阈值 | 通过率公式 |
|------|---------|-----------|-----------|
| 单元测试 | test_plan 批准后 | ≥ 80% | `pass / (pass + fail) × 100%`（skip/blocked/xfail 不计分母） |
| 集成测试 | 单元通过率 ≥ 80% | ≥ 90% | 同上 |
| E2E | 集成通过率 ≥ 90% | critical path 100% | 本环境无真实设备 → NOT_EXECUTED |

三个阶段严格串行；单元/集成均用 mock（monkeypatch `DeviceToolSession` / `_resolve_access` /
`AuditLogger` / `collect_real_panel` / `configure_real_port`），不依赖真实网络。

## 5. 测试用例与 19 AC 的映射矩阵

测试文件（均落 `tests/`）：

- `tests/test_real_panel_parsers.py`（41 例，UNIT）
- `tests/test_real_session_gate.py`（10 例，UNIT）
- `tests/test_real_panel_service.py`（16 例，UNIT）
- `tests/test_real_panel_api.py`（15 例，INT）

| AC | 级别 | 覆盖方式（测试用例/验证手段） |
|----|------|------------------------------|
| AC-RP-001-01 面板按钮仅 REAL 显示 | 前端 | 静态核对 `DevicesListView.vue` L57-68（`v-if="device_type==='REAL'"` 与 SIMULATOR 分支并列）+ `npm run build` 零错误 |
| AC-RP-001-02 点击打开抽屉并加载 | 前端 | 静态核对 `showRealPanel`/`loadRealPanel`（L570-575）+ 构建 |
| AC-RP-002-01 端口表格 name/status/vlan/speed | UNIT | `test_real_panel_parsers.py::TestParseInterfaceStatus`（mock 参考格式 8 端口、单列 TP-Link、vlan/speed 提取、空列、状态归一化） |
| AC-RP-002-02 离线/凭据错误显示错误 | INT+前端 | `test_real_panel_api.py::TestGetRealPanel`（400/502）+ 前端 `ElMessage.error` 静态核对 |
| AC-RP-003-01 CPU 5s 使用率 | UNIT | `TestParseCpuUtilization`（five seconds / 5 seconds / 5s / 兜底百分数） |
| AC-RP-003-02 内存 used/total/usage_pct | UNIT | `TestParseMemoryUtilization`（used/free/total、KB→MB、pct 推导、total=0 抛错） |
| AC-RP-004-01 基本信息（Should Have） | UNIT | `TestParseSystemInfo`（全字段/部分字段/无字段抛错/冒号变体） |
| AC-RP-005-01 禁用（shutdown） | UNIT+INT | `TestConfigureRealPort.test_shutdown_success` + `TestConfigureRealPortApi`（action 校验） |
| AC-RP-005-02 启用（no shutdown） | UNIT | `TestConfigureRealPort.test_no_shutdown_maps_command`、`TestMapAction` |
| AC-RP-005-03 写操作不持久化 | UNIT | `TestConfigureRealPort.test_shutdown_success` 断言 `save` 未被调用 |
| AC-RP-005-04 写失败反馈 | UNIT+INT | `TestConfigureRealPort.test_partial_failure_returns_false` + `TestConfigureRealPortApi.test_write_failure_502` |
| AC-RP-006-01 写操作二次确认 | 前端 | 静态核对 `confirmRealPortAction`（L606-617）文案含「此操作将修改真实生产设备配置」+ 构建 |
| AC-RP-006-02 审计（operator + detail 无密码） | INT | `TestConfigureRealPortApi.test_success_audits_with_operator_and_no_password` / `test_no_shutdown_audit_action` |
| AC-RP-007-01 loading 提示 | 前端 | 静态核对 `loadRealPanel`（L577-585）「约 30-60s」+ 构建 |
| AC-RP-007-02 超时/失败解除 loading | 前端 | 静态核对 125s fail-safe + `finally` 解除 loading（L587-603）+ 构建 |
| AC-RP-008-01 模拟器面板不变 | 回归 | 既有 SIMULATOR 测试套件全绿 + `TestSimulatorPathRegression` |
| AC-RP-008-02 心跳/连通性端点不变 | 回归 | 全量回归 484 passed + `test_ports_endpoint_real_returns_simulator_only_message` |
| AC-RP-009-01 IO 替代数据 | UNIT | `TestParseIoRates.test_always_unsupported_placeholder`（ADR-RP-002 降级占位） |
| AC-RP-009-02 设备不支持时降级不丢区块 | UNIT+前端 | `TestParseIoRates` + `ioText` 静态核对（`supported===false` 显示降级文案） |

## 6. 环境限制声明

1. **无真实 TL-SG5428 设备**：E2E 真实采集与端口写回归标 NOT_EXECUTED，不虚构通过率。
2. **解析器 vlan/speed 位置启发式（FND-001）**：本环境无真实设备输出样例，TP-Link
   `State(Enabled/Disabled)/Link(Up/Down)` 双列格式为**合成样例**，相关测试以 `xfail`
   记录残余风险，需真实设备输出校准后转正。
3. **前端无组件级测试基建**：前端 AC 以静态核对 + `npm run build` 覆盖，如实标注，不冒充自动化单测。

*文档版本 0.1.0 | 状态 DRAFT | 作者 sub_agent_test_engineer | invocation inv-real-panel-d-001*
