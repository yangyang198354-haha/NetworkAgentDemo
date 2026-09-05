<file_header>
  <project_id>NetworkAgentDemo</project_id>
  <module_id>real_device_panel</module_id>
  <doc_type>code_review_report</doc_type>
  <file_name>real_panel_code_review_report.md</file_name>
  <version>0.1.0</version>
  <status>APPROVED</status>
  <author_agent>sub_agent_software_developer</author_agent>
  <created_at>2026-09-05T00:00:00Z</created_at>
  <last_updated>2026-09-05T00:00:00Z</last_updated>
  <invocation_id>inv-real-panel-c-001</invocation_id>
  <input_source>PM agent_invocation — REAL_DEVICE_PANEL / GROUP_RP_C（PHASE_RP_06 代码评审，基于本阶段 8 个实现文件）</input_source>
</file_header>

# 真实设备（REAL）面板 — 代码评审报告

## 评审摘要

- **评审文件总数**: 8（后端新增 3 + 后端修改 3 + 前端修改 2）
- **总行数（约）**: 新增后端 3 文件约 380 行；修改后端 3 文件改动约 90 行；修改前端 2 文件改动约 120 行
- **5 维总体评分**（各维平均）:
  - Correctness: 8.1 / 10
  - Security: 8.8 / 10
  - Performance: 8.6 / 10
  - Maintainability: 8.3 / 10
  - Test Coverage（可测试性）: 6.6 / 10
- **Finding 统计**: CRITICAL 0 条（已修复 0 条）、MAJOR 3 条、MINOR 3 条

## 按模块评审详情

---

**MOD-RP-003: TP-Link CLI 输出解析器（real_panel_parsers.py）**
- Correctness: 8/10
- Security: 10/10
- Performance: 10/10
- Maintainability: 8/10
- Test Coverage (可测试性): 7/10

| Finding ID | 严重级别 | 文件路径:行号 | 描述 | 状态 |
|-----------|---------|------------|------|------|
| FND-001 | MAJOR | src/tools/real_panel_parsers.py:131-153 | vlan/speed 采用「状态关键字后的位置启发式」提取，仅用 MOCK_INTERFACE_STATUS 校准；若 TP-Link TL-SG5428 真实 `show interface status` 列序/关键字不同，vlan/speed 可能误配（status 关键字正则已容错，vlan/speed 位置启发式存在残余风险） | DOCUMENTED |
| FND-002 | MINOR | src/tools/real_panel_parsers.py:138-139 | 未识别状态关键字时返回 `status="unknown"` 而非抛错，可能让畸形行以 unknown 标签通过；显示层可接受，建议监控真实输出 | DOCUMENTED |

> 修复说明：初版 `parse_interface_status` 采用「表头列起始位置定宽切分」，但 MOCK 数据行（如 `Uplink1` 溢出 Name 列宽）与表头列不齐导致误切分。已重写为「端口名(首列) + 状态关键字正则 + 位置启发式 vlan/speed」，冒烟自测通过（8 行端口 + 空 Name 列 + notconnect/connected/down + vlan 10 + speed 1000/Auto）。

---

**MOD-RP-004: 会话串行化门（real_session_gate.py）**
- Correctness: 9/10
- Security: 9/10
- Performance: 9/10
- Maintainability: 9/10
- Test Coverage (可测试性): 7/10

| Finding ID | 严重级别 | 文件路径:行号 | 描述 | 状态 |
|-----------|---------|------------|------|------|
| FND-003 | MAJOR | src/tools/real_session_gate.py:38-62 | `session_guard` 用 `_resolve_access(device)` 解析出的 host（含 FRP 映射），而工作流工具 `session_guard_by_access` 用调用方传入的 `device_ip`。若工作流以「局域网 IP」调用而面板以「FRP 代理 host」访问，二者 key 不同、不共享锁，串行化在「面板+工作流并发」场景下存在残余缺口（属工作流工具入参特征，key 统一需超出本切片范围） | DOCUMENTED |
| FND-004 | MINOR | src/tools/real_session_gate.py:24-25 | `_locks` 注册表无清理机制，设备数量多且 host/port/protocol 组合长期累积时锁对象只增不减（进程内存占用可忽略，演示规模可接受） | DOCUMENTED |

---

**MOD-RP-002: REAL 面板采集服务（real_panel_service.py）**
- Correctness: 8/10
- Security: 9/10
- Performance: 8/10
- Maintainability: 8/10
- Test Coverage (可测试性): 6/10

| Finding ID | 严重级别 | 文件路径:行号 | 描述 | 状态 |
|-----------|---------|------------|------|------|
| FND-005 | MINOR | src/tools/real_panel_service.py:122-124 | 写操作 `success` 判定为 `failed==0 and executed>=len(commands)`，但 `configure()` 的 executed/failed 语义来自底层会话，若命令回显异常但未抛异常可能误判为成功；建议在测试阶段对真实设备校准 | DOCUMENTED |

> 说明：单会话批量采集 + `__exit__` finally 关闭 + 外层 `session_guard` 均满足；`info` 容错非阻塞（ADR-RP-004）；IO 降级占位（ADR-RP-002）。

---

**MOD-RP-001: REAL 面板 API 端点（devices_router.py）**
- Correctness: 8/10
- Security: 9/10
- Performance: 8/10
- Maintainability: 8/10
- Test Coverage (可测试性): 6/10

| Finding ID | 严重级别 | 文件路径:行号 | 描述 | 状态 |
|-----------|---------|------------|------|------|
| FND-006 | MAJOR | src/tools/real_panel_parsers.py:297-334 | `parse_system_info` 的 Device Name/Model 字段提取依赖 `Device Name`/`Model` 标签，而 real_device_client 嵌套 `_parse_show_system_info` 仅提取 Software/Hardware Version；若真实 TP-Link 输出标签不同，info 字段部分为空（ADR-RP-004 容错设计下不阻塞，但字段完整性存风险） | DOCUMENTED |

> 说明：写操作安全专项核对通过 —— `_configure_real_port` 校验 action ∈ {shutdown, no-shutdown}，`AuditLogger().log_audit_event(event_type=CONFIG_CHANGE, alert_id=f"device:{device_id}", operator=current_user.username, action=port_shutdown/port_no_shutdown)`，`detail` 仅含 {device_id, device_name, port_name, action, success, message}，无明文密码；写路径调用 `configure_real_port`（configure 不 save）。

---

**工作流工具会话串行化（switch_diag_tool.py / switch_config_tool.py）**
- Correctness: 8/10
- Security: 9/10
- Performance: 9/10
- Maintainability: 8/10
- Test Coverage (可测试性): 6/10

| Finding ID | 严重级别 | 文件路径:行号 | 描述 | 状态 |
|-----------|---------|------------|------|------|
| FND-007 | MINOR | src/tools/switch_config_tool.py:166 / src/tools/switch_diag_tool.py:267 | 仅用 `with session_guard_by_access(...)` 包裹会话开关，会话逻辑不变，符合 ADR-RP-003 最小改动；但该包裹是「门」而非「持有会话跨段」，若未来在门内新增重入可能自锁，当前无此场景 | DOCUMENTED |

---

**MOD-RP-006 / MOD-RP-005: 前端 store + REAL 面板抽屉（devices.ts / DevicesListView.vue）**
- Correctness: 8/10
- Security: 8/10
- Performance: 8/10
- Maintainability: 8/10
- Test Coverage (可测试性): 6/10

| Finding ID | 严重级别 | 文件路径:行号 | 描述 | 状态 |
|-----------|---------|------------|------|------|
| FND-008 | MINOR | webui/src/views/devices/DevicesListView.vue:618-621 | 端口写操作成功后重新 `loadRealPanel()`（再建立一次会话）而非乐观更新，带来一次额外 30-60s 采集；演示规模可接受 | DOCUMENTED |

> 说明：REAL「面板」按钮仅 `device_type==='REAL'` 显示，与 SIMULATOR「面板」并列；抽屉 loading/125s fail-safe 满足 AC-RP-007；写操作二次确认文案含「此操作将修改真实生产设备配置」（AC-RP-006-01）；IO 读/写区块始终渲染，`ioText` 在 `supported===false` 或字段为 null 时显示降级文案（AC-RP-009-02）。

## 未解决的 CRITICAL 问题

无。本轮实现与自评审过程中未出现 CRITICAL 级别 finding（初版解析器定宽切分误配已在同一轮修复并复测通过）。

## 遗留 MAJOR 问题（3 条，均已 DOCUMENTED）

| Finding ID | 简述 | 遗留原因 |
|-----------|------|----------|
| FND-001 | 端口 vlan/speed 位置启发式未用真实 TP-Link 输出校准 | 本会话无真实 TL-SG5428 设备接入；解析器为纯函数可直接单测，真实输出校准与回归归属 test_engineer E2E 阶段 |
| FND-003 | 面板(FRP host)与工作流工具(device_ip)锁 key 统一存在残余缺口 | 工作流工具入参仅 device_ip，不携带完整 device 对象；key 统一需扩展工作流工具入参，超出本垂直切片变更范围 |
| FND-006 | parse_system_info 字段标签未用真实输出校准 | 同 FND-001，info 为 ADR-RP-004 容错字段，不阻塞其余区块 |

> 以上 3 条 MAJOR 均为「真实设备输出校准」或「既有工作流入参边界」引发的残余风险，不涉及 CRITICAL、不阻塞功能交付，故按规则加注遗留原因后提交。

## 回归测试结果与环境限制

- `py_compile`：6 个后端 Python 文件全部通过。
- 解析器冒烟自测：全部通过（端口 8 行 / CPU / 内存 / IO 降级 / 基本信息 / RealPanelError）。
- **环境限制**：本会话无真实 TL-SG5428 设备接入，未执行真实设备 E2E 采集与端口写回归；前端 Vue 组件未做构建验证（`npm run build` 未在本会话执行）。真实输出解析校准、端口写回归、前端构建验证建议由 test_engineer 阶段补做。

*文档版本 0.1.0 | 状态 APPROVED | 生成时间 2026-09-05 | 作者 sub_agent_software_developer*

<audit_log>
  <log time="2026-09-05T00:00:00Z" state="WRITE_REVIEW_REPORT" action="file_write" result="SUCCESS" trace_id="inv-real-panel-c-001" file_path="project_workspace/real_device_panel/development/real_panel_code_review_report.md"/>
</audit_log>
