<file_header>
  <project_id>NetworkAgentDemo</project_id>
  <module_id>real_device_panel</module_id>
  <doc_type>e2e_test_report</doc_type>
  <file_name>real_panel_e2e_test_report.md</file_name>
  <version>0.2.0</version>
  <status>EXECUTED</status>
  <author_agent>sub_agent_test_engineer</author_agent>
  <created_at>2026-09-05T00:00:00Z</created_at>
  <last_updated>2026-09-05T07:00:00Z</last_updated>
  <invocation_id>inv-real-panel-d-002</invocation_id>
  <input_source>PM agent_invocation — REAL_DEVICE_PANEL / GROUP_RP_D（部署后真实交换机 E2E 验收）</input_source>
</file_header>

# 真实设备（REAL）面板 — E2E 测试报告

## 1. E2E 测试摘要

| 指标 | 数值 |
|------|------|
| 真实采集（读端点） | 1/1 PASS |
| 端口写回归（shutdown/no shutdown） | 0/0（未授权执行，NOT_EXECUTED） |
| 前端构建 | PASS（0 错误） |
| **执行状态** | **EXECUTED** |

- 前置门控：单元 100.00%（≥80%）、集成 100.00%（≥90%）通过。
- 结论：**在部署后生产环境（47.109.197.217）经 FRP 隧道连真实 TL-SG5428 完成读端点 E2E 验收，
  `GET /api/devices/3/real_panel` 返回 HTTP 200 完整快照。端口写回归本轮未执行（需用户单独授权）。**

## 2. 执行环境

| 项 | 值 |
|----|----|
| 后端 | 47.109.197.217:8001（`networkagent.service`，v0.2.0） |
| 真实设备 | TL-SG5428（device_id=3），SSH 经 FRP 隧道 127.0.0.1:6022 → 192.168.31.220 |
| 采集路径 | `DeviceToolSession` 单会话批量采集（ADR-RP-003 会话串行化） |
| 版本 | 提交 `ea699bd`（含 3 个解析缺陷修复） |

## 3. 读端点 E2E 结果（真实采集）

`GET /api/devices/3/real_panel` → **HTTP 200**

| 区块 | 断言 | 结果 |
|------|------|------|
| ports | 22 端口，Gi1/0/1 `up`/`speed=1000M`，其余 `down`；vlan 空（真实无 VLAN 列） | ✅ PASS |
| cpu | `cpu_5s=9.0`（真实百分比） | ✅ PASS |
| memory | `usage_pct=80.0`，`used_mb/total_mb=null`（仅百分比降级，不抛错） | ✅ PASS |
| io | `supported=false`（降级占位，ADR-RP-002） | ✅ PASS |
| info | device_name=TL-SG5428 / model=TL-SG5428 / hardware=TL-SG5428 2.0 / software=1.1.3 Build 20170926 | ✅ PASS |

## 4. E2E 暴露并修复的缺陷（回归记录）

| 缺陷 | 现象 | 修复 | 状态 |
|------|------|------|------|
| 内存解析 502 | `show memory-utilization` 仅返回 `80%`，面板 502 | 仅百分比降级路径 + Optional used/total | ✅ 已修复复验 |
| 端口 VLAN 误配 | 无 VLAN 列时 `1000M` 被当 VLAN | `real_speed_fmt` 列式分支 | ✅ 已修复复验 |
| 分页尾行误判 | `Press any key to continue` 被解析为端口 | `_PAGER_RE` 跳过 | ✅ 已修复复验 |

单测：`tests/test_real_panel_parsers.py` 44 例（含新增 3 例）；全量回归 487 passed / 1 xfailed / 0 failed。

## 5. 未执行项（需单独授权）

- **真实端口写回归**：`configure → interface <name> → shutdown/no shutdown → exit` 未执行。
  对生产设备的写操作需用户明确授权 + 指定测试端口，本轮仅完成读端点验收与写操作安全专项静态核对（V10~V13）。
- **IO 采集**：无已验证 IO CLI 命令，维持 `supported=false` 降级占位（ADR-RP-002）。

## 6. Critical Path 覆盖率

- 关键路径（Must Have 故事）读端点用例：**1/1 通过**（真实采集快照）。
- 写操作关键路径：安全专项以静态核对 + 单测覆盖，未执行真实写（如实标注）。

## 7. 前端构建验证

| 项 | 结果 |
|----|------|
| `npm run build` | 成功（18.19s，0 错误） |
| DevicesListView 产物 | `assets/DevicesListView-BdmcUF8G.js`（21.26 kB）正常生成 |
| REAL 面板内存展示 | 无 MB 分解时回退「使用率 80%（设备未提供 MB 分解）」 |

*文档版本 0.2.0 | 状态 EXECUTED | 作者 sub_agent_test_engineer | invocation inv-real-panel-d-002*
