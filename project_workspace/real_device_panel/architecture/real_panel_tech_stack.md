<file_header>
  <project_id>NetworkAgentDemo</project_id>
  <module_id>real_device_panel</module_id>
  <doc_type>tech_stack</doc_type>
  <file_name>real_panel_tech_stack.md</file_name>
  <version>0.1.0</version>
  <status>APPROVED</status>
  <author_agent>sub_agent_system_architect</author_agent>
  <created_at>2026-09-05T00:00:00Z</created_at>
  <last_updated>2026-09-05T00:00:00Z</last_updated>
  <invocation_id>inv-real-panel-b-001</invocation_id>
  <input_source>PM agent_invocation — GROUP_RP_B 技术选型（基于 APPROVED 需求 inv-real-panel-a-002）</input_source>
</file_header>

# 真实设备（REAL）面板 — 技术选型表

> 核心约束：**零新增 Python/Node 依赖**。全部复用既有技术栈，本表每项均给出需求溯源与风险说明。

## 技术选型表

| 类别 | 选型 | 版本/版次 | Rationale | 关联 REQ-* | 风险 | 备注 |
|------|------|----------|-----------|-----------|------|------|
| 后端语言 | Python | 3.11+（既有） | 复用既有后端运行时，零新依赖 | REQ-RP-NFUNC-003 | Low | 无变更 |
| Web 框架 | FastAPI | 既有 | 聚合读端点 + 写端点扩展直接挂载于既有 `devices_router`；`/api/*` 前缀已统一注入 JWT 鉴权 | REQ-RP-FUNC-007, REQ-RP-NFUNC-002, REQ-RP-NFUNC-003 | Low | 复用 `APIRouter`/`Depends`/`HTTPException` |
| 设备会话客户端 | `real_device_client`（`DeviceToolSession`/`_resolve_access`/`_open_ssh_session`/`_open_telnet_session`/`_strip_echo_and_prompts`/`_looks_like_error`） | 既有（commit 274bab7 后） | 复用已验证的 FRP 穿透 + SSH(OpenSSH→plink→paramiko)/TELNET(raw socket→plink) 会话链；`DeviceToolSession` 提供 `show`/`configure` 且不暴露 `save()`，结构保证「不持久化」 | REQ-RP-FUNC-007, REQ-RP-FUNC-006, REQ-RP-NFUNC-004 | Medium（真实设备会话 20-40s 建立、TELNET 单会话） | 会话串行化由新增门（MOD-RP-004）管理 |
| CLI 输出解析 | 标准库 `re`（纯函数模块 `real_panel_parsers.py`） | stdlib | TP-Link 文本 → 结构化字段，零第三方解析依赖；纯函数可单测；解析失败抛结构化异常 | REQ-RP-FUNC-002/003/004/005/009/010 | Medium（真实输出格式需校准） | 复用 `_strip_echo_and_prompts` 做前置清洗 |
| 会话串行化 | 标准库 `threading.Lock`（per-device 注册表） | stdlib | TL-SG5428 TELNET 仅 1 活动会话；per-device 锁覆盖面板/连通性/写/工作流，零新依赖 | REQ-RP-NFUNC-004 | Low（进程内有效，多实例需另议） | 见 ADR-RP-003 |
| 审计日志 | `AuditLogger`（MOD-015） | 既有 | 复用单例 + `log_audit_event` + `AuditEventType.CONFIG_CHANGE`；操作人来自 `get_current_user`，不记录明文密码 | REQ-RP-NFUNC-002, REQ-RP-FUNC-006 | Low（`alert_id` 复用为设备标识） | 见 ADR-RP-005 |
| 凭据解密 | `EncryptionService`（`_decrypt_password` helper） | 既有 | 复用 `devices_router.py` 现有解密路径，密码不出现在日志/响应 | REQ-RP-FUNC-007, REQ-RP-NFUNC-002 | Low | 无变更 |
| 鉴权 | `get_current_user`（JWT） | 既有 | 写端点显式注入 `get_current_user` 获取操作人，供审计使用 | REQ-RP-NFUNC-002 | Low | 路由级已注入，端点按需显式注入 |
| 前端框架 | Vue 3 + TypeScript + Vite | 既有 | 复用既有 REAL 抽屉 UI 结构（SIMULATOR 抽屉为模板） | REQ-RP-FUNC-001/008 | Low | 无变更 |
| 前端 UI 库 | Element Plus（`el-drawer`/`el-card`/`el-table`/`el-progress`/`el-empty`/`ElMessageBox`/`ElMessage`） | 既有 | 端口表格/进度条/抽屉/二次确认/降级提示均复用既有组件 | REQ-RP-FUNC-002/003/004/008/010, REQ-RP-NFUNC-001/002 | Low | 二次确认用 `ElMessageBox.confirm` |
| 状态管理 | Pinia `defineStore`（`devices.ts`） | 既有 | 新增 `getRealPanel` + `configurePort` 可选超时，向后兼容 SIMULATOR 调用 | REQ-RP-FUNC-008, REQ-RP-NFUNC-001 | Low | 见 MOD-RP-006 |
| HTTP 客户端 | axios（`@/api/client`） | 既有 | 复用 `{ timeout: 120000 }` 长超时（对齐 `checkConnectivity`） | REQ-RP-NFUNC-001 | Low | 无变更 |
| 数据层 | SQLite + SQLAlchemy `DeviceRepository` | 既有 | 面板只读 + 写操作不新增表；设备凭据/状态读取复用既有仓库 | REQ-RP-NFUNC-003 | Low | 无新表/迁移 |

---

## 技术风险汇总

### High
- 无。当前设计未引入 High 级技术风险（零新依赖 + 复用已验证会话链）。

### Medium
1. **真实 CLI 输出格式未校准**（REQ-RP-FUNC-009）
   - 风险：`show interface status`/`show cpu-utilization`/`show memory-utilization` 的 TP-Link 真实输出与 Mock 模板差异较大，解析正则可能失配。
   - 缓解：解析器为纯函数模块（MOD-RP-003），实现阶段以真实 TL-SG5428 输出为基准校准；解析失败抛 `RealPanelError` 并返回明确错误而非错误数据（不伪造）。
2. **写操作退出层级未校准**（REQ-RP-FUNC-006）
   - 风险：`configure → interface <name> → shutdown/no shutdown → exit` 的单次 `exit` 是否回到 enable 模式需真机验证；`DeviceToolSession.configure()` 仅发送一次 `exit`。
   - 缓解：`configure()` 为既有已验证路径（`TpLinkSwitchConfigTool`/`configure_ssh` 使用）；实现阶段校准；无论成败 `finally` 关闭会话。
3. **真实设备会话建立耗时**（REQ-RP-NFUNC-001）
   - 风险：SSH 20-40s / L7 30-60s，若超时配置不当面板加载失败。
   - 缓解：`getRealPanel` 使用 `{ timeout: 120000 }` + 前端 30-60s 提示 + 125s fail-safe（对齐 `checkConnectivity` 既有模式）。

### Low
1. **会话串行化进程内有效**（REQ-RP-NFUNC-004）：`threading.Lock` 仅单进程内互斥，多实例/多进程部署不跨实例；当前单进程 FastAPI 可接受（开放问题）。
2. **审计 `alert_id` 复用**（REQ-RP-NFUNC-002）：面板写操作无告警上下文，`alert_id` 承载合成设备标识 `device:{id}`，审计查询侧需兼容。
3. **工作流工具 FRP key 对齐**（REQ-RP-NFUNC-004）：工作流工具以 `device_ip` 开会话，其 `session_guard_by_access` key 与面板 `_resolve_access` key 在 FRP 场景可能不完全一致，需实现校准（开放问题）。

---

## 依赖新增/变更声明

- **新增第三方 Python 依赖：无。**
- **新增第三方 Node/npm 依赖：无。**
- **新增后端文件**：`real_panel_parsers.py`、`real_panel_service.py`、`real_session_gate.py`（均为 stdlib + 既有模块复用）。
- **修改后端文件**：`devices_router.py`（新增/扩展端点）、`switch_diag_tool.py`、`switch_config_tool.py`（仅包裹串行化门）。
- **修改前端文件**：`DevicesListView.vue`、`devices.ts`。

---

*文档版本 0.1.0 | 状态 APPROVED | 生成时间 2026-09-05 | 作者 sub_agent_system_architect*

<audit_log>
  <log time="2026-09-05T00:00:00Z" state="WRITE_FILES" action="file_write" result="SUCCESS" trace_id="inv-real-panel-b-001" file_path="project_workspace/real_device_panel/architecture/real_panel_tech_stack.md"/>
</audit_log>
