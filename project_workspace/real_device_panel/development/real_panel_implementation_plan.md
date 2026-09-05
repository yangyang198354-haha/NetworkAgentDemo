<file_header>
  <project_id>NetworkAgentDemo</project_id>
  <module_id>real_device_panel</module_id>
  <doc_type>implementation_plan</doc_type>
  <file_name>real_panel_implementation_plan.md</file_name>
  <version>0.1.0</version>
  <status>APPROVED</status>
  <author_agent>sub_agent_software_developer</author_agent>
  <created_at>2026-09-05T00:00:00Z</created_at>
  <last_updated>2026-09-05T00:00:00Z</last_updated>
  <invocation_id>inv-real-panel-c-001</invocation_id>
  <input_source>PM agent_invocation — REAL_DEVICE_PANEL / GROUP_RP_C（PHASE_RP_05 实现计划与编码，基于 APPROVED module_design inv-real-panel-b-001 与 architecture_design）</input_source>
</file_header>

# 真实设备（REAL）面板 — 实现计划

## 实现概览

- **总模块数**: 7（MOD-RP-001 ~ MOD-RP-007，其中 MOD-RP-007 复用现有 AuditLogger，不新增文件）
- **总文件数**: 8（新增 3，修改 5）
- **实现顺序**: 按模块依赖图拓扑排序（叶节点优先），无循环依赖
- **实现状态**: 全部完成，`py_compile` 通过，解析器冒烟自测通过

## 模块实现计划（按拓扑顺序）

| 序号 | MOD-ID | 模块名 | 文件路径 | 依赖前置模块 | 复杂度 | 状态 |
|------|--------|--------|---------|------------|--------|------|
| 1 | MOD-RP-004 | 会话串行化门 | `src/tools/real_session_gate.py`（新增） | real_device_client._resolve_access | L | DONE |
| 2 | MOD-RP-003 | TP-Link CLI 输出解析器 | `src/tools/real_panel_parsers.py`（新增） | 无（仅 stdlib re） | M | DONE |
| 3 | MOD-RP-002 | REAL 面板采集服务 | `src/tools/real_panel_service.py`（新增） | MOD-RP-003, MOD-RP-004, DeviceToolSession | M | DONE |
| 4 | MOD-RP-001 | REAL 面板 API 端点 | `src/api/devices_router.py`（修改） | MOD-RP-002, MOD-RP-007, DeviceRepository, get_current_user | M | DONE |
| 5 | ADR-RP-003 | 工作流工具会话串行化 | `src/tools/switch_diag_tool.py`、`src/tools/switch_config_tool.py`（修改） | MOD-RP-004 | L | DONE |
| 6 | MOD-RP-006 | 前端 DevicesStore 扩展 | `webui/src/stores/devices.ts`（修改） | `@/api/client` | L | DONE |
| 7 | MOD-RP-005 | 前端 REAL 面板抽屉 | `webui/src/views/devices/DevicesListView.vue`（修改） | MOD-RP-006 | M | DONE |

> MOD-RP-007（审计接入）复用 `src/security/audit_logger.AuditLogger`，不新增文件，在 MOD-RP-001 的 `_configure_real_port` 中落地。

## 关键实现决策

### IFC 落地点

| IFC | 落地点 | 说明 |
|-----|--------|------|
| IFC-RP-001-01 | `devices_router.get_real_panel` (`GET /{device_id}/real_panel`) | 单会话批量采集，异常转 404/400/502，不泄露密码 |
| IFC-RP-001-02 | `devices_router.configure_device_port` REAL 分支 + `_configure_real_port` | 写操作 + 审计；SIMULATOR 分支逐字不变 |
| IFC-RP-002-01 | `real_panel_service.collect_real_panel` | 单会话批量采集，io 降级占位，info 容错 |
| IFC-RP-002-02 | `real_panel_service.configure_real_port` | `configure(["interface <name>", cli_cmd])`，绝不 save |
| IFC-RP-003-01~05 | `real_panel_parsers.parse_*` 五个纯函数 | 解析失败抛 RealPanelError |
| IFC-RP-004-01~03 | `real_session_gate.session_key` / `session_guard` / `session_guard_by_access` | 共享同一锁注册表 |
| IFC-RP-005-01~04 | `DevicesListView.vue` 方法 `showRealPanel`/`loadRealPanel`/`confirmRealPortAction`/`ioText` | 二次确认 + IO 降级始终渲染 |
| IFC-RP-006-01~02 | `devices.ts` 的 `getRealPanel` / `configurePort(可选 timeoutMs)` | 120s 长超时 + 可选超时向后兼容 |
| IFC-RP-007-01 | `devices_router._configure_real_port` 内 `AuditLogger().log_audit_event(...)` | `event_type=CONFIG_CHANGE`、`alert_id=f"device:{id}"`、`operator=current_user.username`、detail 无明文密码 |

### 硬约束落地核对

| 硬约束 | 落地位置 | 结果 |
|--------|----------|------|
| 写操作安全（前端二次确认 + 后端审计 + 不 save） | 前端 `confirmRealPortAction` ElMessageBox.confirm；后端 `_configure_real_port` AuditLogger；服务层 `configure_real_port` 不调用 save | 满足 |
| 单会话批量采集 | `collect_real_panel` 单 `with DeviceToolSession(...)` 内依次下发多条 show，`__exit__` finally 关闭 | 满足 |
| 会话串行化（面板/连通性/写/工作流） | `collect_real_panel`/`configure_real_port`/`device_check_connectivity` 套 `session_guard`；`switch_diag_tool`/`switch_config_tool` 套 `session_guard_by_access` | 满足 |
| IO 降级（后端 `io.supported=false` + 前端始终渲染 IO） | 后端 `parse_io_rates(None)` → `IoRates(supported=False)`；前端 `ioText` 始终渲染 IO 读/写 | 满足 |
| 零新增依赖 | 仅 stdlib + 既有 real_device_client/FastAPI/Vue3/AuditLogger | 满足 |
| 不改 src/ 修测试导入（D-001/D-002） | 新增为全新文件，未触碰 tests/conftest.py 补丁机制 | 满足 |
| SIMULATOR 分支零变更 | `configure_device_port`/`get_device_ports`/`get_device_system` SIMULATOR 路径及前端 SIMULATOR 面板分支未改动 | 满足 |
| 解析失败抛 RealPanelError 不返回伪造数据 | 五个 parser 均失败抛结构化异常 | 满足 |
| 真实接口以实际代码为准 | 已核对 real_device_client 实际签名（见偏差记录） | 满足 |

## 自测说明

- `python -m py_compile` 对 6 个后端 Python 文件全部通过。
- 解析器冒烟自测（进程内断言）覆盖：
  - `parse_interface_status`（8 行 MOCK_INTERFACE_STATUS，含空 Name 列、notconnect/connected/down、vlan 10、speed 1000/Auto）
  - `parse_cpu_utilization`（5s/1m/5m 三值）
  - `parse_memory_utilization`（used/total/usage_pct）
  - `parse_io_rates`（supported=False 降级）
  - `parse_system_info`（device_name/model/hardware_version/software_version）
  - `RealPanelError`（无表头时抛 ports 异常）
  - 结果：全部通过（ALL SMOKE TESTS PASSED）。
- 未在真实 TL-SG5428 设备上做 E2E 采集/写操作（本会话无真实设备接入）；真实输出校准与回归测试归属 test_engineer 阶段（见 code_review_report 遗留 MAJOR）。

## 架构偏差记录

| 偏差ID | 偏差描述 | 原架构假设 | 偏差原因 |
|--------|----------|-----------|----------|
| DEV-RP-001 | `real_device_client._parse_show_system_info` 为 `check_connectivity` 内部嵌套函数（line 2029），非模块级可复用函数 | MOD-RP-003 设计文档假设「复用/对齐 `real_device_client._parse_show_system_info`」可直接 import | 以实际代码为准：解析器改为在 `real_panel_parsers.parse_system_info` 内自实现等价字段提取（Device Name / Hardware Version / Software Version / Model），不 import 嵌套函数；功能等价、不改动 real_device_client（NFUNC-003） |
| DEV-RP-002 | `DeviceToolSession` 仅暴露 `show(command)` 与 `configure(commands)`，无 `save()` 方法 | 架构 ADR-RP-005 要求「绝不调用 save()」 | 实际代码未暴露 save，结构上天然满足 AC-RP-005-03；实现未调用任何持久化命令 |

*文档版本 0.1.0 | 状态 DRAFT | 生成时间 2026-09-05 | 作者 sub_agent_software_developer*

<audit_log>
  <log time="2026-09-05T00:00:00Z" state="WRITE_FILES" action="file_write" result="SUCCESS" trace_id="inv-real-panel-c-001" file_path="project_workspace/real_device_panel/development/real_panel_implementation_plan.md"/>
</audit_log>
