<file_header>
  <project_id>NetworkAgentDemo</project_id>
  <module_id>real_device_e2e</module_id>
  <doc_type>tech_stack</doc_type>
  <file_name>real_device_e2e_tech_stack.md</file_name>
  <version>0.2.0</version>
  <status>APPROVED</status>
  <author_agent>sub_agent_system_architect</author_agent>
  <created_at>2026-09-05T04:00:00Z</created_at>
  <last_updated>2026-09-05T04:00:00Z</last_updated>
  <invocation_id>inv-real-e2e-b-001</invocation_id>
  <input_source>PM agent_invocation — GROUP_B 技术选型（基于 APPROVED 需求 inv-real-e2e-a-002）</input_source>
</file_header>

# 真实设备（REAL）端到端工作流 — 技术选型表

> 核心约束：**零新增 Python/Node 依赖**。全部复用既有技术栈，本表每项均给出需求溯源、候选对比与风险说明。

## 技术选型表

| 类别 | 选型 | 版本/版次 | 候选对比 | Rationale | 关联 REQ-* | 风险 |
|------|------|----------|----------|-----------|-----------|------|
| 后端语言 | Python | 3.11+（既有） | Python（既有） vs Go/Node | 复用既有运行时与模块，零迁移成本 | REQ-RE-NFUNC-004 | Low |
| Web 框架 | FastAPI | 既有 | FastAPI（既有） vs Flask | 复用既有 `alerts_router`/`devices_router`，simulate 回填仅扩展既有端点 | REQ-RE-FUNC-001, REQ-RE-NFUNC-004 | Low |
| 工作流编排 | LangGraph `StateGraph`（同步 + MemorySaver） | 既有 | LangGraph（既有） vs 手写状态机 | 14 节点图结构不变（`state_graph_engine.py` L62-76），仅节点内补 REAL 分支 | REQ-RE-FUNC-007 | Low |
| FRP 接入解析 | `real_device_client._resolve_access`（L408-429） | 既有 | 复用 `_resolve_access` vs 节点内重写 FRP 逻辑 vs 工具层自解析 | 复用唯一 FRP 解析点，避免逻辑分散；节点负责取 DB 数据 + 调用它回填 | REQ-RE-FUNC-002 | Low（见 ADR-RE-001） |
| 设备会话客户端 | `real_device_client`（`DeviceToolSession`/`_SshSession`/`_TelnetSession`/`_open_ssh_session`/`_open_telnet_session`） | 既有 | 会话链 `_open_ssh_session`（OpenSSH→plink→paramiko） vs 直接 `_SshSession`（paramiko） | TpLink*Tool 现用 `_SshSession` 直连；建议实现阶段复用面板已验证的 `_open_ssh_session` 链以兼容 TL-SG5428 DSA KEX | REQ-RE-FUNC-002/003, REQ-RE-NFUNC-003 | Medium（DSA KEX，见风险 2） |
| CLI 输出解析 | 标准库 `re`（复用 `real_panel_parsers.py`） | 既有 | 复用 `real_panel_parsers` vs 新增解析正则 | 上一轮已实现 TL-SG5428 列式解析（`parse_interface_status` L90-145），零新解析代码 | REQ-RE-FUNC-004/006 | Low（真实输出已校准，见 ADR-RE-003） |
| 会话串行化 | 标准库 `threading.Lock`（复用 `real_session_gate`） | 既有 | 复用 `session_guard_by_access` vs 新锁机制 | TL-SG5428 TELNET 单会话；TpLink*Tool 已包裹 `session_guard_by_access`（switch_diag_tool L267、switch_config_tool L166） | REQ-RE-NFUNC-003 | Low（进程内有效） |
| 修复模板 | YAML 模板 + `TemplateEngine`（复用） | 既有 | 复用 `TemplateEngine.render` vs 硬编码命令 | 模板化确定性拼装；CPU/MAC 双分支降级（ADR-RE-004），PORT 模板去 description | REQ-RE-FUNC-005/008 | Medium（CPU/MAC 等价命令 [待核实]，见风险 1） |
| 凭据解密 | `ConfigManager.get_device_credentials` + `EncryptionService` | 既有 | 仅 env `DEVICE_<NAME>_PASSWORD` / DB Fernet vs 兜底 `admin123` | REAL 路径禁用 `admin123` 兜底（config_manager L161/L170），缺失即失败 | REQ-RE-NFUNC-001 | Low（见 ADR-RE-006） |
| 审计日志 | `AuditLogger`（MOD-015） | 既有 | 复用 `log_audit_event` vs 新日志表 | execute_fix 已有审计调用（node_handlers L887-898），`detail` 不含明文密码 | REQ-RE-NFUNC-002 | Low |
| 数据层 | SQLite + SQLAlchemy `DeviceRepository` | 既有 | 复用 `list_devices` vs 新增 `get_by_name` | FRP/协议/型号从 `devices` 表取（device_models L48-59）；不新增表/迁移 | REQ-RE-FUNC-002, REQ-RE-NFUNC-004 | Low（无新表/迁移） |

---

## 技术风险汇总

### High
- 无。当前设计未引入 High 级技术风险（零新依赖 + 复用已验证会话/解析/串行化能力）。

### Medium
1. **CPU_HIGH / MAC_FLAPPING 等价修复命令未核实**（REQ-RE-FUNC-008 / RISK-RE-01）
   - 风险：候选命令（storm-control / 端口安全 / loopback-detection / CPU 限速）**未经真实 TL-SG5428 核实**，若直接写死模板可能下发出 `unknown command` 甚至误操作生产端口。
   - 缓解：ADR-RE-004 双分支——默认 DEGRADED（不下发命令），仅经用户授权**只读探测**核实后经 `resolve_fix_capability` 注册表升为 FIXABLE；核实前不写死任何候选命令。
2. **TpLink*Tool 会话链 DSA 兼容性**（REQ-RE-FUNC-002/003, REQ-RE-NFUNC-003）
   - 风险：`TpLinkSwitchDiagTool._run`（switch_diag_tool L270）/`TpLinkSwitchConfigTool._run`（switch_config_tool L169）用 `_SshSession`（paramiko fallback）直连，paramiko 可能拒绝 TL-SG5428 的 ssh-dss/DSA KEX（`real_device_client.py` L380-382 注释），导致 Windows 上 REAL 会话建立失败。
   - 缓解：实现阶段优先复用面板已验证的 `_open_ssh_session`/`_open_telnet_session`（Windows OpenSSH→plink→paramiko 链，L2130-2168）；本架构不强制工具层改动（开放问题 1）。

### Low
1. **会话串行化进程内有效**（REQ-RE-NFUNC-003）：`threading.Lock` 仅单进程内互斥，多实例部署不跨实例；当前单进程 FastAPI 可接受。
2. **`handle_get_device_info` 新增 DB 查询**（REQ-RE-FUNC-002）：仅 REAL 触发，MOCK/SIMULATOR 走原路径；查询失败返回明确错误而非落 Mock。
3. **CPU_HIGH 阈值未定**（Q-RE-04）：`alerts_router.py` L212 硬编码 92%/80%，影响验证口径与告警回填文案。

---

## 依赖新增/变更声明

- **新增第三方 Python 依赖：无。**
- **新增第三方 Node/npm 依赖：无。**
- **新增后端文件：无**（全部为在既有 `node_handlers.py`/`alerts_router.py` 内加分支/函数；可选新增 2 个 TP-Link 模板 YAML，视只读探测核实结果而定）。
- **修改后端文件**：`node_handlers.py`（REAL 分支）、`alerts_router.py`（simulate 回填）、`tpl_port_enable.yaml`/`tpl_port_disable.yaml`（去 description 行）。
- **零改动**：`main.py`（MOCK 注入不变）、`switch_diag_tool.py`/`switch_config_tool.py`（工厂与 `_run` 复用）、`real_device_client.py`/`real_panel_parsers.py`/`real_session_gate.py`（复用）、`src/models/alert.py`（不加 frp 字段）。

---

*文档版本 0.2.0 | 状态 APPROVED | 生成时间 2026-09-05 | 作者 sub_agent_system_architect*

<audit_log>
  <log time="2026-09-05T04:00:00Z" state="WRITE_FILES" action="file_write" result="SUCCESS" trace_id="inv-real-e2e-b-001" file_path="project_workspace/real_device_e2e/architecture/real_device_e2e_tech_stack.md"/>
</audit_log>
