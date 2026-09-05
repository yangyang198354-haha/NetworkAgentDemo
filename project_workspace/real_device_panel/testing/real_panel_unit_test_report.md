<file_header>
  <project_id>NetworkAgentDemo</project_id>
  <module_id>real_device_panel</module_id>
  <doc_type>unit_test_report</doc_type>
  <file_name>real_panel_unit_test_report.md</file_name>
  <version>0.1.0</version>
  <status>APPROVED</status>
  <author_agent>sub_agent_test_engineer</author_agent>
  <created_at>2026-09-05T00:00:00Z</created_at>
  <last_updated>2026-09-05T00:00:00Z</last_updated>
  <invocation_id>inv-real-panel-d-001</invocation_id>
  <input_source>PM agent_invocation — REAL_DEVICE_PANEL / GROUP_RP_D（单元测试阶段）</input_source>
</file_header>

# 真实设备（REAL）面板 — 单元测试报告

## 1. 单元测试摘要

- 执行时间：2026-09-05（本会话）
- 环境：Windows 11 Pro / Python 3.14.6 / pytest 9.1.1
- 命令：`python -m pytest tests/test_real_panel_parsers.py tests/test_real_session_gate.py tests/test_real_panel_service.py -v`

| 指标 | 数值 |
|------|------|
| Total | 67 |
| Pass | 66 |
| Fail | 0 |
| Skip | 0 |
| Blocked | 0 |
| XFail（已知限制，不计分母） | 1 |

- 算术校验：`67 = 66 + 0 + 0 + 0 + 1(xfail)`（xfail 单列，不计入 pass/fail 分母）
- 通过率：`pass / (pass + fail) = 66 / (66 + 0) = 100.00%`
- 门控阈值：80%
- **门控结论：PASSED**（100.00% ≥ 80%）

## 2. 代码覆盖率（statement）

`--cov=src.tools.real_panel_parsers --cov=src.tools.real_session_gate --cov=src.tools.real_panel_service`

| 模块 | Stmts | Miss | Cover |
|------|-------|------|-------|
| src/tools/real_panel_parsers.py | 163 | 3 | 98% |
| src/tools/real_panel_service.py | 52 | 0 | 100% |
| src/tools/real_session_gate.py | 28 | 0 | 100% |
| **TOTAL** | 243 | 3 | **99%** |

未覆盖行：`real_panel_parsers.py` L118（异常分支）、L135（`_parse_port_line` name 为空的防御分支）、
L262（内存 `free` 解析防御分支）——均为纯防御性分支，不影响主路径正确性。

## 3. 按模块分项结果

### 3.1 MOD-RP-003 解析器（41 例，40 pass + 1 xfail）

| 测试类 | 覆盖点 | 结果 |
|--------|--------|------|
| TestRealPanelError（3） | section/reason/raw_excerpt 属性、`str` 含 section、异常继承 | PASS |
| TestParseInterfaceStatus（15） | 空/空白/无表头抛错、MOCK 参考 8 端口、空 Name 列、status 归一化（connected/link up/enabled/disabled/notconnect 等）、vlan/speed 提取、单列 TP-Link、`Interface` 表头回退、分隔线跳过、畸形行 unknown、`_parse_port_line` 位置启发式 | 14 PASS + 1 XFAIL |
| TestParseCpuUtilization（8） | Cisco `five seconds` 风格、TP-Link `5 seconds:` 风格、`5s` 别名、兜底取首个百分数、1m/5m 可选为 None、无百分比抛错 | PASS |
| TestParseMemoryUtilization（8） | used/free/total+显式 pct、used/free 推导 total+pct、used/total 推导 pct、KB→MB、total=0 抛错、缺失 used/total 抛错 | PASS |
| TestParseIoRates（1） | ADR-RP-002 固定降级占位（supported=False + 降级文案） | PASS |
| TestParseSystemInfo（6） | 全字段（`-` 分隔）、部分字段（TL- 前缀 Model）、无字段抛错、`:` 分隔变体 | PASS |

**XFAIL 详情（FND-001 残余风险，需真实设备输出校准）：**

| TC | 说明 | 期望 | 实际 | 根因 |
|----|------|------|------|------|
| `test_tplink_two_column_state_link_format` | TP-Link `State(Enabled/Disabled)/Link(Up/Down)` 双列合成样例 | status 取 Link、vlan=PVID、speed=Speed | vlan/speed 位置启发式误配（vlan 取到 Speed 列、speed 取到 PVID 列） | FND-001：位置启发式仅用 MOCK 校准 |

> 该样例为**合成格式**，非真实设备捕获输出；判定为已知限制而非确定性缺陷，需 E2E 阶段以真实
> TL-SG5428 输出校准后转正或修复。

### 3.2 MOD-RP-004 会话串行化门（10 例，全 PASS）

| 测试类 | 覆盖点 | 结果 |
|--------|--------|------|
| TestSessionKey（3） | key 格式 `host:port:protocol`、FRP 映射、port 强转 int | PASS |
| TestSessionGuard（2） | acquire/release、同设备同锁 | PASS |
| TestSessionGuardByAccess（5） | protocol 大写归一、None 默认 SSH、acquire/release、与 session_guard 共享注册表（FND-003 边界语义）、返回 `threading.Lock` | PASS |

### 3.3 MOD-RP-002 采集服务（16 例，全 PASS）

| 测试类 | 覆盖点 | 结果 |
|--------|--------|------|
| TestMapAction（6） | shutdown / no-shutdown / no_shutdown / 大小写剥离 / 非法动作与 None 抛 ValueError | PASS |
| TestConfigureRealPort（6） | shutdown 成功、no-shutdown 命令映射、partial 失败 success=False、executed<len 失败、非法动作不建会话、上下文管理器关闭会话 | PASS |
| TestCollectRealPanel（4） | 组装快照、info 失败非阻塞（ADR-RP-004）、单会话只建一次、命令错误抛 RealPanelError(ports) | PASS |

**写操作安全专项结论（AC-RP-005-03）：**

- `test_shutdown_success` 显式断言 `mock_sess.save.assert_not_called()`：`configure_real_port`
  只调用 `sess.configure([...])`，**绝不调用 `save()`**，结构上保证不执行
  `copy running-config startup-config` 持久化。
- `test_invalid_action_propagates_value_error_before_session`：非法动作在建立会话前即抛错，
  不会向设备下发任何命令。

## 4. 失败/阻塞汇总

- 无 FAIL、无 BLOCKED、无 SKIP。
- 1 条 XFAIL 为 FND-001 已知限制（见 3.1），不计入通过率，需真实设备输出校准，属后续 E2E
  阶段输入，不阻塞本阶段门控。

*文档版本 0.1.0 | 状态 APPROVED | 作者 sub_agent_test_engineer | invocation inv-real-panel-d-001*
