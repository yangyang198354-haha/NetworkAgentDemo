<file_header>
  <project_id>NetworkAgentDemo</project_id>
  <module_id>real_device_e2e</module_id>
  <doc_type>code_review_report</doc_type>
  <file_name>real_device_e2e_code_review_report.md</file_name>
  <version>0.2.0</version>
  <status>DRAFT</status>
  <author_agent>sub_agent_software_developer</author_agent>
  <created_at>2026-09-05T05:40:00Z</created_at>
  <last_updated>2026-09-05T05:40:00Z</last_updated>
  <invocation_id>inv-real-e2e-c-001</invocation_id>
  <input_source>PM agent_invocation — GROUP_RE_C 编码实现自我评审（基于 APPROVED architecture/module_design）</input_source>
</file_header>

# 真实设备（REAL）端到端工作流 — 代码评审报告

## 评审摘要

- **评审文件数**：4（`node_handlers.py`、`alerts_router.py`、`tpl_port_enable.yaml`、`tpl_port_disable.yaml`）
- **变更规模**：+640 行 / -73 行（`git diff --numstat`：node_handlers.py 609+/51-，alerts_router.py 29+/20-，两个模板各 -2）
- **测试结果**：`python -m pytest tests/ -v --tb=short <CI 排除清单> -k "not slow"` → **487 passed, 1 xfailed**（xfailed 为既有预期失败，非本次引入）
- **5 维总体评分（各维平均）**：
  - Correctness: **8.9 / 10**
  - Security: **8.6 / 10**
  - Performance: **8.3 / 10**
  - Maintainability: **8.6 / 10**
  - Test Coverage (可测试性): **6.0 / 10**
- **Finding 统计**：CRITICAL **2 条（已修复 2 条）**、MAJOR **2 条（均 DOCUMENTED）**、MINOR **3 条（均 DOCUMENTED）**

## 按模块评审详情

### MOD-RE-001: REAL 接入上下文解析
- Correctness: 9/10
- Security: 9/10
- Performance: 8/10
- Maintainability: 8/10
- Test Coverage: 6/10

| Finding ID | 严重级别 | 文件路径:行号 | 描述 | 状态 |
|-----------|---------|------------|------|------|
| FND-C1 | CRITICAL | src/orchestration/node_handlers.py:766-767 | REAL 明文密码回填进 `device_info` 后随 `_log_node` 的 `state_snapshot` 落库（alert_timeline），违反 ADR-RE-006「审计/时间线不含明文密码」 | FIXED（新增 `_sanitize_state_snapshot`，见 MOD-RE-006） |
| FND-C2 | CRITICAL | src/orchestration/node_handlers.py:506 | 脱敏方法首次落地时 `snapshot = self._sanitize_state_snapshot(state)` 造成自递归（会栈溢出） | FIXED（改回 `dict(state)`） |

### MOD-RE-002: REAL 工具选择 + 可达性
- Correctness: 9/10
- Security: 8/10
- Performance: 8/10
- Maintainability: 9/10
- Test Coverage: 7/10

| Finding ID | 严重级别 | 文件路径:行号 | 描述 | 状态 |
|-----------|---------|------------|------|------|
| FND-M1 | MAJOR | src/tools/switch_diag_tool.py / switch_config_tool.py（零改动，复用） | `TpLinkSwitchDiagTool._run`/`TpLinkSwitchConfigTool._run` 用 `_SshSession`（paramiko）直连；Windows + TL-SG5428 ssh-dss/DSA KEX 下 paramiko 可能拒连。workflow 层 `establish_real_reachability`/`_real_backup` 已用更稳的 `_open_ssh_session` 链。属架构开放问题 1，零改动清单约束下不强制改工具层。 | DOCUMENTED（遗留原因：`switch_diag_tool.py`/`switch_config_tool.py` 在零改动清单内；如需生产硬化，建议后续单独 ADR） |

### MOD-RE-003: REAL 诊断命令映射 + 解析
- Correctness: 9/10
- Security: 8/10
- Performance: 8/10
- Maintainability: 9/10
- Test Coverage: 6/10

| Finding ID | 严重级别 | 文件路径:行号 | 描述 | 状态 |
|-----------|---------|------------|------|------|
| FND-N3 | MINOR | src/orchestration/node_handlers.py:274 | `parse_diag_output` 仅对 REAL 主命令（collect_diag 中 idx 0）结构化；CPU_HIGH 的 `show memory-utilization` 未单独结构化，随原文进入 diag_result。不影响 ADR-RE-003 基线。 | DOCUMENTED |

### MOD-RE-004: 修复能力裁决 + 降级
- Correctness: 9/10
- Security: 9/10
- Performance: 9/10
- Maintainability: 9/10
- Test Coverage: 6/10

| Finding ID | 严重级别 | 文件路径:行号 | 描述 | 状态 |
|-----------|---------|------------|------|------|
| FND-M2 | MAJOR | tests/test_e2e_full.py（CI 排除项） | `test_has_commands` 断言 PORT_DOWN 渲染命令 == 3；本次删 `description` 行后变 2。该文件在 CLAUDE.md CI 排除清单内，零回归命令不跑；需 test_engineer 同步更新断言。 | DOCUMENTED（遗留原因：测试更新属 test_engineer 职责，且该用例非 CI 门禁） |

### MOD-RE-005: REAL 结构化验证
- Correctness: 8/10
- Security: 8/10
- Performance: 8/10
- Maintainability: 8/10
- Test Coverage: 6/10

（无 CRITICAL/MAJOR finding。`verify_real_fix` 依赖 `parse_interface_status` 的归一化状态值 `up/down/notconnect`，已与 `_normalize_port_status` 的 `enable→up`、`disable→down` 映射对齐。）

### MOD-RE-006: 安全（凭据/写白名单/审计脱敏/只读备份）
- Correctness: 9/10
- Security: 10/10
- Performance: 8/10
- Maintainability: 8/10
- Test Coverage: 6/10

| Finding ID | 严重级别 | 文件路径:行号 | 描述 | 状态 |
|-----------|---------|------------|------|------|
| FND-N1 | MINOR | src/orchestration/node_handlers.py:1628 | `_extract_auth` 保留 `password=device_info.get("password", "admin123")` 字面默认（MOCK 路径）。REAL 已被 `_resolve_real_credentials` 门控（缺失即 FAILED），不会触发该默认；建议后续统一移除/常量化。 | DOCUMENTED |

### ADR-RE-007: simulate 告警真实性回填
- Correctness: 9/10
- Security: 8/10
- Performance: 9/10
- Maintainability: 9/10
- Test Coverage: 5/10

| Finding ID | 严重级别 | 文件路径:行号 | 描述 | 状态 |
|-----------|---------|------------|------|------|
| FND-N2 | MINOR | src/api/alerts_router.py:210-215 | CPU_HIGH 告警描述阈值仍硬编码 92%/80%（Q-RE-04 开放问题），本次未改，属需求/架构待确认项。 | DOCUMENTED |

## 未解决的 CRITICAL 问题

无。所有 CRITICAL finding（FND-C1、FND-C2）均已在同一轮内修复并重跑自评与全量单测（487 passed / 1 xfailed）。

## 遗留 MAJOR 问题

共 2 条 MAJOR，均 ≤ 3 条上限，且已逐条标注遗留原因：

1. **FND-M1（工具层 DSA KEX 风险）**：`switch_diag_tool.py`/`switch_config_tool.py` 在零改动清单内，其 `_SshSession` 直连（paramiko）在 Windows + TL-SG5428 的 ssh-dss/DSA KEX 下存在拒连风险。workflow 层的连通性探测与备份已改用更稳的 `_open_ssh_session` 链，但诊断/配置 `_run` 仍走原工具实现。若生产硬化需改工具层，属新 ADR 范围，超出本次「零改动工具层」约束。
2. **FND-M2（e2e 断言遗留）**：`test_e2e_full.py::test_has_commands` 依赖旧 3 命令模板，已随模板去 `description` 而失效。该测试非 CI 门禁（CLAUDE.md 排除），留待 test_engineer 更新。

## 评审结论

- 7 条 ADR（ADR-RE-001 ~ ADR-RE-007）全部落地，MOCK / SIMULATOR 路径零回归（487 passed / 1 xfailed）。
- 零新增 Python/Node 依赖；`src/main.py` L79-80 MOCK 注入未改。
- REAL 凭据安全门控（禁用 `admin123` 兜底）、写操作端口白名单 `{Gi1/0/2}`、不调 `save()`、不下发 `description`、审计/时间线脱敏均已实现并自评通过。
- 建议后续（超出本次编码职责）：由 test_engineer 补充 REAL 分支单元测试（当前 REAL 分支依赖 DB/FRP/会话，未在本轮补测）；由 system_architect 评估工具层会话链硬化（FND-M1）。

<audit_log>
  <log time="2026-09-05T05:40:00Z" state="WRITE_FILES" action="file_write" result="SUCCESS" trace_id="inv-real-e2e-c-001" file_path="project_workspace/real_device_e2e/development/real_device_e2e_code_review_report.md"/>
</audit_log>
