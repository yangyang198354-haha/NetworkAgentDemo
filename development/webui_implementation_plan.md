<file_header>
  <author_agent>sub_agent_software_developer</author_agent>
  <timestamp>2026-07-11T00:00:00Z</timestamp>
  <project_name>NetworkAgentDemo</project_name>
  <version>0.1.0</version>
  <input_files>
    <file>architecture/webui_architecture_design.md</file>
    <file>architecture/webui_module_design.md</file>
    <file>architecture/webui_tech_stack.md</file>
    <file>requirements/webui_requirements_spec.md</file>
    <file>requirements/webui_user_stories.md</file>
  </input_files>
  <phase>PHASE_W05</phase>
  <status>DRAFT</status>
</file_header>

# Web 管理界面实现计划 — NetworkAgentDemo

---

## 实现概览

- **总模块数**: 后端新增 7 个 (MOD-WEB-001 ~ 007) + 前端 20 个 (MOD-WEB-F01 ~ F20)
- **总代码文件数**: 后端约 35 个 Python 文件 + 前端约 30 个 Vue/TypeScript 文件
- **实现顺序**: 严格遵循拓扑排序，从基础设施层向表现层推进
- **架构**: 模块化分层单体 + Web 表现层垂直扩展

---

## 模块依赖拓扑排序

基于 module_design.md 依赖关系图，拓扑排序结果：

```
第1层（基础设施 — 无依赖）:
  MOD-WEB-003 (DatabaseManager)
  MOD-WEB-005 (EncryptionService)
  MOD-WEB-007 (LogReaderService)

第2层（数据访问与安全）:
  MOD-WEB-004 (DataAccessLayer) ← depends on MOD-WEB-003
  MOD-WEB-002 (AuthService) ← depends on MOD-WEB-003

第3层（业务聚合）:
  MOD-WEB-006 (DashboardService) ← depends on MOD-WEB-004

第4层（API 表现层）:
  MOD-WEB-001 (APIRouterLayer) ← depends on MOD-WEB-002/003/004/005/006/007 + 现有 MOD-002~006

第5层（入口改造）:
  main.py 增强 ← 挂载所有新 Router

第6层（前端 — 按依赖顺序）:
  MOD-WEB-F03 (ApiClient) → MOD-WEB-F04~F11 (Stores) → MOD-WEB-F02 (Router) →
  MOD-WEB-F01 (AppShell) → MOD-WEB-F12~F20 (Views)
```

---

## 模块实现计划（按拓扑顺序）

| 序号 | MOD-ID | 模块名 | 文件路径 | 依赖前置模块 | 复杂度 | 状态 |
|------|--------|--------|---------|------------|--------|------|
| 1 | MOD-WEB-003 | DatabaseManager | `src/database/` (8 files) | — | H | PLANNED |
| 2 | MOD-WEB-005 | EncryptionService | `src/services/encryption_service.py` | — | L | PLANNED |
| 3 | MOD-WEB-007 | LogReaderService | `src/services/log_reader_service.py` | — | M | PLANNED |
| 4 | MOD-WEB-004 | DataAccessLayer | `src/database/repositories/` (8 files) | MOD-WEB-003 | H | PLANNED |
| 5 | MOD-WEB-002 | AuthService | `src/services/auth_service.py` | MOD-WEB-003 | M | PLANNED |
| 6 | MOD-WEB-006 | DashboardService | `src/services/dashboard_service.py` | MOD-WEB-004 | M | PLANNED |
| 7 | MOD-WEB-001 | APIRouterLayer | `src/api/` (11 files) | MOD-WEB-002~007 + 现有模块 | H | PLANNED |
| 8 | — | main.py 改造 | `src/main.py` (修改) | MOD-WEB-001 | M | PLANNED |
| 9 | — | requirements.txt | `requirements.txt` (修改) | — | L | PLANNED |
| 10 | MOD-WEB-F03 | ApiClient | `webui/src/api/client.ts` | — | L | PLANNED |
| 11 | MOD-WEB-F04~F11 | Pinia Stores | `webui/src/stores/` (8 files) | MOD-WEB-F03 | M | PLANNED |
| 12 | MOD-WEB-F02 | Router | `webui/src/router/index.ts` | MOD-WEB-F04 | M | PLANNED |
| 13 | MOD-WEB-F01 | AppShell | `webui/src/layout/` (3 files) | MOD-WEB-F02/F04/F06 | M | PLANNED |
| 14 | MOD-WEB-F12~F20 | Page Views | `webui/src/views/` (16+ files) | MOD-WEB-F01~F11 | H | PLANNED |
| 15 | — | Frontend scaffolding | `webui/package.json` 等 (4 files) | — | L | PLANNED |

---

## 各模块关键实现要点

### MOD-WEB-003 (DatabaseManager)
- **11 个 ORM Model** 按领域拆分为 6 个文件（auth/alert/approval/device/inspection/kb/config）
- `base.py`: `declarative_base()` + `TimestampMixin`（created_at/updated_at）
- SQLite WAL 模式 + 外键约束启用
- 数据库路径: `./data/webui.db`（与 `./data/chroma_db/` 隔离）
- `init_db()`: 调用 `Base.metadata.create_all()` 自动建表

### MOD-WEB-005 (EncryptionService)
- `cryptography.fernet` Fernet 对称加密
- 密钥优先级: 环境变量 `ENCRYPTION_KEY` > `./data/.encryption_key` 文件 > 自动生成
- `mask_sensitive()` 掩码函数: 默认前4后4字符可见

### MOD-WEB-004 (DataAccessLayer)
- 7 个 Repository 类封装 SQLAlchemy CRUD
- 分页统一使用 `PaginatedResult[offset, limit]`
- AlertRepository 支持多条件筛选（alert_type, severity, status, source, time_range）

### MOD-WEB-002 (AuthService)
- JWT: python-jose + HS256, 24h 过期
- bcrypt: passlib.hash.bcrypt, cost factor=12
- admin 初始化: 幂等，检查 users 表，不存在则创建

### MOD-WEB-001 (APIRouterLayer)
- 8 个 APIRouter + `dependencies.py`（get_db, get_current_user）
- `/auth/login` 排除 JWT 保护（`dependencies=[]`）
- 所有 `/api/*` 端点统一挂载前缀和 JWT 依赖

### main.py 改造
- **原代码零删除**，仅追加 `app.include_router()`
- lifespan 中追加: `init_db()` → `initialize()` (EncryptionService) → `init_admin_user()`
- 旧 `/alerts/simulate` 标记 deprecated

---

## 文件清单

### 后端新增文件（`src/` 目录）

| # | 文件路径 | MOD-ID | IFC 列表 | 行数预估 |
|---|---------|--------|---------|---------|
| 1 | `src/database/__init__.py` | MOD-WEB-003 | — | 30 |
| 2 | `src/database/base.py` | MOD-WEB-003 | IFC-WEB-003-01~04 | 80 |
| 3 | `src/database/auth_models.py` | MOD-WEB-003 | User Model | 40 |
| 4 | `src/database/alert_models.py` | MOD-WEB-003 | Alert, AlertTimeline Model | 90 |
| 5 | `src/database/approval_models.py` | MOD-WEB-003 | Approval Model | 70 |
| 6 | `src/database/device_models.py` | MOD-WEB-003 | Device, DeviceCredential Model | 80 |
| 7 | `src/database/inspection_models.py` | MOD-WEB-003 | InspectionRecord Model | 50 |
| 8 | `src/database/kb_models.py` | MOD-WEB-003 | KnowledgeDocument, CommandTemplate | 80 |
| 9 | `src/database/config_models.py` | MOD-WEB-003 | SystemConfig, AuditLog | 60 |
| 10 | `src/database/repositories/__init__.py` | MOD-WEB-004 | — | 20 |
| 11 | `src/database/repositories/alert_repository.py` | MOD-WEB-004 | AlertRepository IFCs | 120 |
| 12 | `src/database/repositories/approval_repository.py` | MOD-WEB-004 | ApprovalRepository IFCs | 80 |
| 13 | `src/database/repositories/device_repository.py` | MOD-WEB-004 | DeviceRepository IFCs | 120 |
| 14 | `src/database/repositories/inspection_repository.py` | MOD-WEB-004 | InspectionRepository IFCs | 80 |
| 15 | `src/database/repositories/knowledge_repository.py` | MOD-WEB-004 | KnowledgeRepository IFCs | 150 |
| 16 | `src/database/repositories/config_repository.py` | MOD-WEB-004 | ConfigRepository IFCs | 80 |
| 17 | `src/database/repositories/audit_log_repository.py` | MOD-WEB-004 | AuditLogRepository IFCs | 60 |
| 18 | `src/services/auth_service.py` | MOD-WEB-002 | IFC-WEB-002-01~05 | 100 |
| 19 | `src/services/encryption_service.py` | MOD-WEB-005 | IFC-WEB-005-01~05 | 80 |
| 20 | `src/services/dashboard_service.py` | MOD-WEB-006 | IFC-WEB-006-01~03 | 120 |
| 21 | `src/services/log_reader_service.py` | MOD-WEB-007 | IFC-WEB-007-01~02 | 100 |
| 22 | `src/api/__init__.py` | MOD-WEB-001 | — | 30 |
| 23 | `src/api/dependencies.py` | MOD-WEB-001 | get_db, get_current_user | 60 |
| 24 | `src/api/auth_router.py` | MOD-WEB-001 | IFC-WEB-001-01 | 50 |
| 25 | `src/api/alerts_router.py` | MOD-WEB-001 | 4 endpoints | 120 |
| 26 | `src/api/workflow_router.py` | MOD-WEB-001 | 3 endpoints | 80 |
| 27 | `src/api/approvals_router.py` | MOD-WEB-001 | 3 endpoints | 80 |
| 28 | `src/api/devices_router.py` | MOD-WEB-001 | 7 endpoints | 160 |
| 29 | `src/api/inspection_router.py` | MOD-WEB-001 | 4 endpoints | 90 |
| 30 | `src/api/kb_router.py` | MOD-WEB-001 | 11 endpoints | 200 |
| 31 | `src/api/config_router.py` | MOD-WEB-001 | 5 endpoints | 120 |
| 32 | `src/api/dashboard_router.py` | MOD-WEB-001 | 2 endpoints | 60 |

### 后端修改文件

| # | 文件路径 | 修改内容 | 行数变化 |
|---|---------|---------|---------|
| 33 | `src/main.py` | 追加 include_router + lifespan 增强 | +40 |
| 34 | `requirements.txt` | 追加 sqlalchemy, python-jose, passlib, cryptography 等 | +8 |

### 前端文件（`webui/` 目录）

| # | 文件路径 | MOD-ID | 行数预估 |
|---|---------|--------|---------|
| 35 | `webui/package.json` | — | 30 |
| 36 | `webui/vite.config.ts` | — | 30 |
| 37 | `webui/index.html` | — | 20 |
| 38 | `webui/tsconfig.json` | — | 30 |
| 39 | `webui/src/main.ts` | — | 20 |
| 40 | `webui/src/App.vue` | — | 10 |
| 41 | `webui/src/api/client.ts` | MOD-WEB-F03 | 60 |
| 42 | `webui/src/router/index.ts` | MOD-WEB-F02 | 120 |
| 43 | `webui/src/stores/auth.ts` | MOD-WEB-F04 | 50 |
| 44 | `webui/src/stores/alerts.ts` | MOD-WEB-F05 | 60 |
| 45 | `webui/src/stores/approvals.ts` | MOD-WEB-F06 | 60 |
| 46 | `webui/src/stores/devices.ts` | MOD-WEB-F07 | 70 |
| 47 | `webui/src/stores/inspection.ts` | MOD-WEB-F08 | 50 |
| 48 | `webui/src/stores/knowledge.ts` | MOD-WEB-F09 | 80 |
| 49 | `webui/src/stores/system.ts` | MOD-WEB-F10 | 60 |
| 50 | `webui/src/stores/dashboard.ts` | MOD-WEB-F11 | 50 |
| 51 | `webui/src/layout/AppShell.vue` | MOD-WEB-F01 | 80 |
| 52 | `webui/src/layout/SidebarNav.vue` | MOD-WEB-F01 | 80 |
| 53 | `webui/src/layout/AppHeader.vue` | MOD-WEB-F01 | 50 |
| 54 | `webui/src/views/LoginView.vue` | MOD-WEB-F20 | 80 |
| 55 | `webui/src/views/dashboard/DashboardView.vue` | MOD-WEB-F12 | 150 |
| 56 | `webui/src/views/alerts/AlertsListView.vue` | MOD-WEB-F13 | 120 |
| 57 | `webui/src/views/alerts/AlertsDetailView.vue` | MOD-WEB-F13 | 150 |
| 58 | `webui/src/views/alerts/AlertsSimulateView.vue` | MOD-WEB-F13 | 100 |
| 59 | `webui/src/views/workflow/WorkflowGraphView.vue` | MOD-WEB-F14 | 100 |
| 60 | `webui/src/views/approvals/ApprovalsPendingView.vue` | MOD-WEB-F15 | 100 |
| 61 | `webui/src/views/approvals/ApprovalsDetailView.vue` | MOD-WEB-F15 | 120 |
| 62 | `webui/src/views/approvals/ApprovalsHistoryView.vue` | MOD-WEB-F15 | 80 |
| 63 | `webui/src/views/devices/DevicesListView.vue` | MOD-WEB-F16 | 180 |
| 64 | `webui/src/views/inspection/InspectionConfigView.vue` | MOD-WEB-F17 | 100 |
| 65 | `webui/src/views/inspection/InspectionHistoryView.vue` | MOD-WEB-F17 | 80 |
| 66 | `webui/src/views/knowledge/KnowledgeDocumentsView.vue` | MOD-WEB-F18 | 150 |
| 67 | `webui/src/views/knowledge/KnowledgeTemplatesView.vue` | MOD-WEB-F18 | 150 |
| 68 | `webui/src/views/knowledge/KnowledgeTestRetrievalView.vue` | MOD-WEB-F18 | 80 |
| 69 | `webui/src/views/system/SystemConfigView.vue` | MOD-WEB-F19 | 120 |
| 70 | `webui/src/views/system/SystemLogsView.vue` | MOD-WEB-F19 | 100 |

---

## 架构偏差记录

无架构偏差。所有实现严格遵循 module_design.md 接口契约和 architecture_design.md ADR 决策。

---

## 现有模块增强策略

| 现有文件 | 增强方式 | 兼容性保证 |
|---------|---------|-----------|
| `src/main.py` | 仅追加 `app.include_router()`，origin code untouched | Git diff 可验证零删除 |
| `src/trigger/inspection_scheduler.py` | lifespan 中添加设备种子数据逻辑 | 向后兼容 |
| `src/orchestration/alert_normalizer.py` | 追加 SQLite 持久化调用 | 写入失败不阻塞 |
| `src/orchestration/node_handlers.py` | 追加 timeline 写入调用 | 写入失败不阻塞 |
| `src/llm/llm_service.py` | API Key 来源优先级调整 | 回退环境变量兼容 |
| `src/orchestration/state_graph_engine.py` | get_pending_approvals() 增强 | 返回字段为超集 |

---

## 风险与缓解

| 风险 | 缓解措施 |
|------|---------|
| SQLite 并发写锁 | WAL 模式 + 写操作 timeout=5 |
| 文件数量多（70+） | 严格按拓扑顺序分批实现，每批验证后提交 |
| 前后端接口契约不一致 | 后端 API 严格按照 module_design.md 端点契约实现 |
| 现有模块改造破坏兼容性 | 所有改造仅追加代码，不删除原有逻辑 |
