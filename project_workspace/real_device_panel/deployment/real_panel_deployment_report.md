<file_header>
  <project_id>NetworkAgentDemo</project_id>
  <module_id>real_device_panel</module_id>
  <doc_type>deployment_report</doc_type>
  <file_name>real_panel_deployment_report.md</file_name>
  <version>0.2.0</version>
  <status>COMPLETED</status>
  <author_agent>sub_agent_devops_engineer</author_agent>
  <created_at>2026-09-05T03:20:00Z</created_at>
  <last_updated>2026-09-05T07:00:00Z</last_updated>
  <invocation_id>inv-real-panel-e-002</invocation_id>
  <input_source>PM agent_invocation — REAL_DEVICE_PANEL / GROUP_RP_E（部署执行 + 部署后真实交换机验收）</input_source>
</file_header>

# 生产部署报告 — 真实设备（REAL）面板（REAL_DEVICE_PANEL）

> **状态**: COMPLETED。生产部署已执行、服务已重启、健康检查通过，并在部署后
> 对真实 TL-SG5428 交换机完成读端点 E2E 验收。部署采用 SSH 密钥免密（无明文密码）。

## 1. 执行摘要

| 项 | 结果 |
|----|------|
| 部署目标 | Alibaba Cloud ECS（47.109.197.217），`/opt/NetworkAgentDemo/project_workspace`，端口 8001 |
| 部署方式 | `git fetch origin master` + `reset --hard origin/master`（代码仓库为准） |
| 部署版本 | 提交 `ea699bd`（fix: handle real TL-SG5428 memory/port CLI output），叠加 `8a50b21`（REAL panel 功能） |
| 前端构建 | 成功（18.19s，0 错误，产物 `assets/DevicesListView-BdmcUF8G.js`） |
| 后端编译/导入 | `py_compile` 6 文件通过；`import real_panel_parsers/real_panel_service/real_session_gate` 通过 |
| 服务状态 | `networkagent.service` active，`/health` HTTP 200 `status=healthy` `version=0.2.0` |
| 真实交换机 E2E | `GET /api/devices/3/real_panel` HTTP 200，完整快照（见 §4） |
| 部署结论 | **成功** |

## 2. 部署步骤执行记录（对齐 deployment_plan DEPLOY-001~011）

| 步骤 | 命令/动作 | 结果 |
|------|-----------|------|
| DEPLOY-001 预检 | `whoami`/`uname`/`systemctl show networkagent -p WorkingDirectory` | `WorkingDirectory=/opt/NetworkAgentDemo/project_workspace` 确认 |
| DEPLOY-002 备份 | `cp -a /opt/NetworkAgentDemo /opt/NetworkAgentDemo.backup.<ts>` | BACKUP_OK |
| DEPLOY-003/004/005 git 同步 | `git fetch origin master && git reset --hard origin/master` | HEAD → `ea699bd`，GIT_SYNC_OK |
| DEPLOY-006 前端构建 | `npm run build` | BUILD_OK，dist/index.html 生成 |
| DEPLOY-007 后端编译/导入 | `py_compile` + `import` | PY_COMPILE_OK / IMPORT_OK |
| DEPLOY-008 重启 | `systemctl restart networkagent` | active |
| DEPLOY-009 健康 | `curl :8001/health` | HTTP 200 healthy（首次 curl 因 uvicorn ~8s 启动窗口 rc=7，重试通过） |
| DEPLOY-010/011 端点+日志 | SPA `/` 200；`journalctl` 无 Error/Critical/Traceback | 通过 |

> 注：DEPLOY-009 首次 `curl` 返回 rc=7，属重启后 uvicorn 启动约 8s 的窗口期（脚本仅 sleep 6s），
> 非应用故障；单独重试即返回 200 healthy v0.2.0。已确认服务实际健康。

## 3. 部署后验证清单（V1~V17）

| 项 | 验证内容 | 结果 |
|----|----------|------|
| V1 | `/health` + `systemctl is-active` | ✅ HTTP 200 healthy v0.2.0；active |
| V2 | 8001 监听 | ✅ 服务 active 且 /health 200（间接确认监听） |
| V3 | REAL 面板对 SIMULATOR 语义（400） | ⏭ 本轮未单独 curl（读语义由单测覆盖） |
| V4 | REAL 面板对 REAL 语义（200/502） | ✅ HTTP 200 完整快照（见 §4） |
| V5~V9 | SIMULATOR/心跳/连通性/ports 零回归 | ✅ 487 本地单测 + 服务重启零回归（SIMULATOR 分支零变更） |
| V10~V13 | 写操作安全专项（前端二次确认+审计+不 save+无明文） | ✅ 静态核对 + 单测覆盖（本轮未执行真实写） |
| V14 | 前端构建产物 | ✅ dist/index.html + DevicesListView-*.js 生成 |
| V15 | SPA 首页 | ✅ HTTP 200 |
| V16 | 日志无 ERROR | ✅ 无 Error/Critical/Traceback |
| V17 | GenPlatform 未受影响 | ⏭ 未检查（部署仅操作 networkagent.service 与 8001） |

> 写操作安全专项（V10~V13）：本轮与部署计划一致，**不执行任何真实 enable/disable 写测试**；
> 仅以「前端二次确认 + AuditLogger(CONFIG_CHANGE, operator=current_user.username, detail 无明文) +
> configure 不调 save()」的代码路径 + 单测覆盖验收。

## 4. 真实交换机 E2E 验收结果（部署后）

`GET /api/devices/3/real_panel`（真实 TL-SG5428，FRP 隧道 SSH 127.0.0.1:6022 → 192.168.31.220）：

| 区块 | 结果 |
|------|------|
| HTTP | 200 |
| ports | 22 端口：Gi1/0/1 `up`/`1000M`，其余 21 端口 `down`（vlan 空、speed 空）——真实列式 Port/Status/Speed/Duplex/FlowCtrl/Active-Medium 正确解析 |
| cpu | `cpu_5s=9.0`（真实百分比） |
| memory | `used_mb=null`/`total_mb=null`/`usage_pct=80.0`（仅百分比降级路径，设备不提供 MB 分解） |
| io | `supported=false`（本轮降级占位，ADR-RP-002） |
| info | device_name=TL-SG5428 / model=TL-SG5428 / hardware_version=TL-SG5428 2.0 / software_version=1.1.3 Build 20170926 Rel.67375 |

## 5. E2E 暴露并修复的解析缺陷

部署后真实交换机验收暴露出 3 个解析器缺陷（`real_panel_parsers.py`），均已修复、
重部署、复验通过：

| 缺陷 | 现象 | 修复 | 提交 |
|------|------|------|------|
| 内存解析 502 | `show memory-utilization` 仅返回裸 `80%`（无 used/total MB），面板 HTTP 502 | `MemoryUsage.used_mb/total_mb` 置 Optional；新增仅百分比降级路径 | `ea699bd` |
| 端口 VLAN 误配 | `show interface status` 无 VLAN 列，`1000M` 被误读为 VLAN | 表头识别 `real_speed_fmt` 分支 + `_parse_real_speed_port_line` | `ea699bd` |
| 分页尾行误判 | `Press any key to continue (Q to quit)` 被解析为端口 `Press` | `_PAGER_RE` 跳过 | `ea699bd` |

对应单测新增 3 例（`test_real_panel_parsers.py` 共 44 例，全量 487 passed / 1 xfailed / 0 failed）。

## 6. 回滚说明

- 备份：`/opt/NetworkAgentDemo.backup.<ts>`（DEPLOY-002 自动生成）。
- 回滚命令（如需）：`systemctl stop networkagent && rm -rf /opt/NetworkAgentDemo && mv /opt/NetworkAgentDemo.backup.<ts> /opt/NetworkAgentDemo && systemctl start networkagent`。
- 本次未触发回滚（部署与验收均成功）。

## 7. 遗留问题与后续

| 项 | 状态 | 说明 |
|----|------|------|
| FND-001 端口 vlan/speed 真实校准 | **已解决** | `ea699bd` 真实列式分支，E2E 验证通过 |
| FND-006 parse_system_info 标签校准 | **已验证** | info 区块字段与真实 `show system-info` 一致 |
| 真实端口写回归（shutdown/no shutdown） | **未执行** | 需用户单独授权 + 指定测试端口；本轮仅读验收 |
| IO 采集 | 降级占位 | ADR-RP-002，无已验证 IO CLI 命令 |

*文档版本 0.2.0 | 状态 COMPLETED | 作者 sub_agent_devops_engineer | invocation inv-real-panel-e-002*
