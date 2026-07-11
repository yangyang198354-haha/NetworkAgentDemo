<file_header>
  <author_agent>sub_agent_system_architect</author_agent>
  <timestamp>2026-07-11T00:00:00Z</timestamp>
  <project_name>NetworkAgentDemo</project_name>
  <version>0.1.0</version>
  <input_files>
    <file>requirements/webui_requirements_spec.md</file>
    <file>requirements/webui_user_stories.md</file>
    <file>architecture/architecture_design.md</file>
    <file>architecture/module_design.md</file>
    <file>architecture/tech_stack.md</file>
    <file>src/main.py</file>
  </input_files>
  <phase>PHASE_W03</phase>
  <status>APPROVED</status>
</file_header>

# Web 管理界面架构设计文档 — NetworkAgentDemo

---

## 架构概览

### 架构风格扩增：模块化分层单体 + Web 表现层

现有 NetworkAgentDemo 采用**模块化分层单体**架构（见 architecture_design.md ADR-001 补充说明），包含 5 个逻辑层次（触发层/编排层/LLM与知识层/工具层/安全与基础设施层）。本设计在现有架构基础上**垂直扩展一层 Web 表现层**，同时在数据层引入 SQLite 持久化，形成以下 6 层架构：

```
┌─────────────────────────────────────────────────────────────────────────┐
│                   Web 表现层 (Presentation Layer) — NEW                  │
│                                                                         │
│  ┌──────────────────────┐  ┌──────────────────────────────────────────┐ │
│  │  Vue 3 SPA (前端)     │  │  FastAPI APIRouter Layer (后端)          │ │
│  │  ─────────────────── │  │  ─────────────────────────────────────  │ │
│  │  • 8 功能模块页面     │  │  • 8 个 APIRouter（auth/alerts/         │ │
│  │  • 全局导航+面包屑    │  │    workflow/approvals/devices/           │ │
│  │  • Pinia 状态管理     │  │    inspection/knowledge/system/dashboard)│ │
│  │  • Axios HTTP 客户端  │  │  • JWT 依赖注入保护                      │ │
│  │  • Element Plus UI    │  │  • 32 个新增端点 + 6 个增强端点          │ │
│  │  • ECharts 图表       │  │  • 保持现有 6 个端点不变                  │ │
│  └──────────────────────┘  └──────────────────────────────────────────┘ │
│                                                                         │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │ HTTP REST (JWT Bearer Token)
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│        现有 5 层架构（触发层 / 编排层 / LLM与知识层 / 工具层 / 安全层）    │
│                        (MOD-001 ~ MOD-016，保持兼容)                      │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                   数据持久化层 (Persistence Layer) — NEW                  │
│                                                                         │
│  ┌──────────────────────┐  ┌──────────────────────────────────────────┐ │
│  │  SQLite + SQLAlchemy │  │  LangGraph MemorySaver (Checkpoint)      │ │
│  │  ─────────────────── │  │  ─────────────────────────────────────  │ │
│  │  • 11 个数据实体     │  │  • 保持不变（PM 决策 D9）                 │ │
│  │  • ORM 映射          │  │  • 工作流 State 快照不入 SQLite           │ │
│  │  • Alembic 迁移      │  │                                          │ │
│  └──────────────────────┘  └──────────────────────────────────────────┘ │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 关键架构决策摘要

| 决策点 | 选型 | 依据需求 |
|--------|------|---------|
| 整体风格 | 垂直扩展 Web 表现层，不改动现有 5 层 | REQ-WEBUI-FUNC-001~028，PM 决策 D1（保持现有 6 端点） |
| 前端 | Vue 3 + Vite + Element Plus + Pinia + ECharts | PM 决策 D3、D6；REQ-WEBUI-NFUNC-001（< 3s 加载）、REQ-WEBUI-NFUNC-002（Chrome/Edge） |
| API 组织 | FastAPI APIRouter 按模块拆分（8 个 Router） | PM 决策 D1；REQ-WEBUI-FUNC-001~028 对应 32 个 API 端点 |
| 数据持久化 | SQLite + SQLAlchemy ORM + Alembic 迁移 | PM 决策 D2；REQ-WEBUI-FUNC-001（告警持久化）、REQ-WEBUI-FUNC-009（审批历史持久化）等 |
| 认证 | JWT (python-jose) + bcrypt (passlib)，24h 过期，无 Refresh Token | PM 决策 D4、D7；REQ-WEBUI-FUNC-025、REQ-WEBUI-NFUNC-003、REQ-WEBUI-NFUNC-004 |
| 静态文件 | 开发: Vite proxy → FastAPI；生产: FastAPI mount dist/ | PM 决策 D3；REQ-WEBUI-NFUNC-001 |
| 加密 | passlib[bcrypt] + cryptography.fernet (AES-256) | REQ-WEBUI-NFUNC-004、REQ-WEBUI-NFUNC-005 |
| LangGraph Checkpoint | MemorySaver 保持不变 | PM 决策 D9 |

---

## 架构决策记录（ADRs）

---

### ADR-WEB-001: FastAPI API 层架构 — 如何组织新增 32 个端点

- **Status**: Accepted
- **Context**:
  - 现有 `src/main.py` 中 6 个端点（`/webhook/alert`、`/alerts/simulate`、`/approvals/pending`、`/approvals/{id}/decide`、`/workflow/{id}/state`、`/health`）直接挂在 `app` 实例上。
  - 需要新增 32 个 `/api/` 前缀下的端点，覆盖认证、告警管理、工作流可视化、审批管理、设备管理、巡检管理、知识库管理、系统配置、Dashboard 共 9 个功能域（REQ-WEBUI-FUNC-001~024、REQ-WEBUI-FUNC-025~026）。
  - PM 决策 D1 明确 "FastAPI 扩展，保持现有 6 个端点 + 新增 32 个 `/api/` 端点，单进程部署，端口 8000"。
  - PM 决策 D10 明确 "废弃 POST /alerts/simulate（query params），统一用 POST /api/alerts/simulate（JSON Body）"。
  - 现有端点必须保持向后兼容，不能破坏任何已有功能。
  - 所有 `/api/` 端点（除 `/auth/login`）需要 JWT 认证保护（REQ-WEBUI-FUNC-025）。

- **Options**:
  - **Option A: 单文件全部挂在 main.py（Monolithic main.py）**
    - 描述：将 32 个新端点全部定义在 `src/main.py` 中，与现有 6 个端点混在一起，直接挂在 `app` 上。JWT 依赖作为函数参数在每个端点中重复添加。
    - 优点：无需新建任何文件，所有端点在一处可见；部署路径最简单（只需 uvicorn main:app）。
    - 缺点：`main.py` 会从当前约 330 行膨胀到 1200+ 行，严重违反单一职责原则；9 个功能域的端点混杂在一起，调试和维护困难；JWT 依赖注入需要每个端点函数重复声明 `Depends(get_current_user)`；无法对端点分组做统一的前缀、标签、响应模型管理。
  - **Option B: APIRouter 按功能模块拆分（Modular APIRouters）**
    - 描述：在 `src/api/` 目录下创建 8 个 APIRouter 模块文件（`auth_router.py`、`alerts_router.py`、`workflow_router.py`、`approvals_router.py`、`devices_router.py`、`inspection_router.py`、`kb_router.py`、`config_router.py`、`dashboard_router.py`），每个 Router 负责各自功能域的端点。在 `main.py` 中通过 `app.include_router()` 挂载，统一加上 `/api` 前缀。JWT 依赖注入在 `dependencies.py` 中集中定义，各 Router 复用。
    - 优点：每个 Router 文件专注单一功能域，代码量可控（每个约 100~200 行）；统一的 `/api` 前缀和 JWT 保护可以集中管理；FastAPI 原生 `APIRouter` 支持 tags、prefix、dependencies 参数，可声明式配置；现有 6 个端点保持原样，新旧端点共存无冲突；OpenAPI 文档自动按 tag 分组展示。
    - 缺点：需要约 10 个额外文件；需要合理设计 Router 之间的共享依赖（如数据库 session、当前用户对象）。
  - **Option C: Django-style App 目录结构**
    - 描述：按 Django 的 app 惯例，每个功能域一个子包目录（如 `src/alerts/`）内含 `router.py`、`schemas.py`、`service.py`、`repository.py`。
    - 优点：功能域完全内聚，便于未来拆分为微服务。
    - 缺点：目录层级深（`src/alerts/router.py`），在 32 个端点的 Demo 规模下过度设计；FastAPI 社区主流实践是扁平 APIRouter 文件，Django-style 不符合 FastAPI 惯例；会增加开发者理解成本。

- **Decision**: 选择 **Option B（APIRouter 按功能模块拆分）**。

  理由：
  1. **FastAPI 原生推荐方案**：FastAPI 官方文档和社区最佳实践均推荐使用 `APIRouter` 组织大型应用。`APIRouter(prefix="/api", dependencies=[Depends(get_current_user)])` 可一次性为所有端点统一挂载前缀和认证依赖。
  2. **向后兼容保证**：现有 6 个端点定义在 `app` 上（路由：`/webhook/alert`、`/alerts/simulate`、`/approvals/pending`、`/approvals/{id}/decide`、`/workflow/{id}/state`、`/health`），新的 APIRouter 挂载在 `/api` 前缀下（路由：`/api/alerts`、`/api/auth/login` 等），URL 空间完全不冲突（REQ-WEBUI-FUNC-001~028，PM 决策 D1）。
  3. **按需求域对齐**：8 个 APIRouter 直接映射 PM 定义的 8 大功能模块 + 认证，需求追踪清晰。例如 `REQ-WEBUI-FUNC-001~004` 对应 `alerts_router.py`，`REQ-WEBUI-FUNC-010~012` 对应 `devices_router.py`。
  4. **Option C 过度设计**：Django-style 目录结构在 Demo 规模下引入不必要的目录层级，且与 FastAPI 社区的扁平模块传统不一致。
  5. **D10 废弃路径处理**：旧 `POST /alerts/simulate` 端点保留在 `main.py` 上但标记为 deprecated，新 `POST /api/alerts/simulate` 通过 `alerts_router.py` 暴露，满足 PM 决策 D10。

- **Consequences**:
  - **正向**：
    - 完整支撑 REQ-WEBUI-FUNC-001~028 覆盖的 32 个 API 端点契约（详见 webui_requirements_spec.md "外部接口需求" 节）。
    - JWT 认证对 `/api/` 端点统一生效，`/auth/login` 通过 `dependencies=[]` 排除（REQ-WEBUI-FUNC-025）。
    - 现有 6 个端点完全不受影响（URL 空间隔离，`main.py` 中改动仅限于添加 `app.include_router()` 调用）。
    - OpenAPI 文档自动按功能域 tag 分组，Swagger UI 可读性大幅提升。
  - **负向**：
    - 新增 `src/api/` 目录和约 10 个 Python 文件，代码库文件数增加。但对于 32 个端点的规模而言，这是合理且必要的组织成本。
    - APIRouter 之间的共享逻辑（如 `get_db` session 依赖、`get_current_user` 认证依赖）需要提取到 `src/api/dependencies.py`，防止循环导入。

---

### ADR-WEB-002: SQLAlchemy 数据模型设计 — 11 个数据实体的 ORM 映射

- **Status**: Accepted
- **Context**:
  - webui_requirements_spec.md "数据持久化需求" 节定义了 11 个数据实体：`users`、`alerts`、`alert_timeline`、`approvals`、`devices`、`device_credentials`、`inspection_records`、`knowledge_documents`、`command_templates`、`system_config`、`audit_logs`。
  - PM 决策 D2 明确 "SQLite + SQLAlchemy ORM"。
  - PM 决策 D9 明确 "LangGraph checkpoint 保持 MemorySaver（不混入 SQLite），与告警业务数据分离存储"。
  - 现有系统（main.py）使用硬编码 `default_devices` 列表和内存存储（REQ-WEBUI-FUNC-010 要求替代为 SQLite CRUD）。
  - 现有审批功能存在已知问题 MAJ-001（审批历史内存存储、重启丢失），需要 SQLite 持久化解决（REQ-WEBUI-FUNC-009）。
  - 现有 Chroma RAG 知识库的文档元数据需要与 SQLite 中的知识文档记录同步（REQ-WEBUI-FUNC-016）。
  - 需要支持 Alembic 数据库迁移以管理 Schema 演进。

- **Options**:
  - **Option A: 单文件 models.py 全部定义**
    - 描述：所有 11 个 SQLAlchemy Model 类定义在单个 `src/database/models.py` 文件中，使用一个共享的 `declarative_base()`。
    - 优点：所有模型集中一处，方便查看全局表关系；较少文件管理开销。
    - 缺点：`models.py` 预计 400+ 行，违反单一职责；11 个 Model 的导入路径单一，任何模块即使只需要 User Model 也要导入整个 models.py；代码审查时需要在一个大文件中定位；当模型数量增长时难以维护。
  - **Option B: 按领域拆分（Domain-split Model Files）**
    - 描述：按业务领域将模型拆分为 6 个文件：`base.py`（共享 `declarative_base()`）、`auth_models.py`（User）、`alert_models.py`（Alert、AlertTimeline）、`approval_models.py`（Approval）、`device_models.py`（Device、DeviceCredential）、`inspection_models.py`（InspectionRecord）、`kb_models.py`（KnowledgeDocument、CommandTemplate）、`config_models.py`（SystemConfig、AuditLog）。所有文件共享同一个 `Base`，通过 `__init__.py` 统一导出。
    - 优点：每个文件专注单一领域，符合单一职责；导入时可以精确引用（`from src.database.models.alert_models import Alert`）；代码审查和合并冲突风险低；新增加实体只需新增一个领域文件。
    - 缺点：跨领域的外键关系（如 `Alert.device_id → Device.id`）需要跨文件 import，可能引入循环引用风险（通过字符串引用 `"Device"` 解决）；文件数量较多（约 8 个模型文件）。
  - **Option C: 声明式混合（Declarative Mixin Pattern）**
    - 描述：使用 SQLAlchemy Mixin 类封装通用字段（如 `TimestampMixin` 提供 `created_at`/`updated_at`、`IDMixin` 提供自增主键），各 Model 通过多重继承组合 Mixin。
    - 优点：通用字段 DRY（Don't Repeat Yourself），`created_at`/`updated_at` 等字段定义一次。
    - 缺点：Mixin 继承层次在 11 个实体的 Demo 规模下引入不必要的抽象复杂度；SQLAlchemy Mixin 的 `__tablename__` 等声明式属性继承需要注意 MRO；不如 Option B 直观。

- **Decision**: 选择 **Option B（按领域拆分 Model 文件）+ 适度使用 TimestampMixin**。

  理由：
  1. **业务领域对齐**：6 个模型文件直接映射 webui_requirements_spec.md 中定义的 6 个功能领域（认证/告警/审批/设备/巡检/知识库/配置），与 PM 8 大功能模块保持一致的逻辑分组。例如 `REQ-WEBUI-FUNC-001~004`（告警管理）对应 `alert_models.py`；`REQ-WEBUI-FUNC-010~012`（设备管理）对应 `device_models.py`。
  2. **循环引用可控**：跨文件外键关系使用 SQLAlchemy 字符串引用（如 `ForeignKey("devices.id")` 而非 `ForeignKey(Device.id)`），避免 Python import 层面的循环依赖。这是 SQLAlchemy 官方推荐的跨模块外键模式。
  3. **适度 DRY**：使用一个轻量的 `TimestampMixin`（`created_at`、`updated_at`）放在 `base.py` 中，避免在 11 个 Model 中重复定义相同字段。但不过度使用 Mixin（不引入 IDMixin、StatusMixin 等），保持每个 Model 的字段定义清晰可见。
  4. **Alembic 集成必要性**：Demo 阶段 Schema 变更频繁（如调整字段类型、新增索引、添加列），Alembic 的自动生成迁移（`--autogenerate`）可以追踪所有 Model 变更并生成迁移脚本，避免手动维护 SQL DDL。建议保留 Alembic 但初期使用简化配置（`alembic.ini` + 单个 `env.py`）。
  5. **Option C 过度抽象**：在 11 个实体的 Demo 规模下，深度使用 Mixin 带来的继承层次不利于代码阅读者快速理解表结构。11 个实体的字段重复（`created_at`/`updated_at` 出现约 8 次）在 Option B + TimestampMixin 下已经得到控制。

- **Consequences**:
  - **正向**：
    - 完整支撑 11 个数据实体的 SQLite 持久化需求（REQ-WEBUI-FUNC-001 告警持久化、REQ-WEBUI-FUNC-009 审批历史持久化、REQ-WEBUI-FUNC-010 设备持久化、REQ-WEBUI-FUNC-013 巡检配置持久化、REQ-WEBUI-FUNC-016 知识文档持久化、REQ-WEBUI-FUNC-019 系统配置持久化）。
    - 解决现有 MAJ-001 已知问题（审批历史内存存储、重启丢失）。
    - 告警业务数据（alerts、alert_timeline、approvals）与 LangGraph MemorySaver checkpoint 完全隔离存储，满足 PM 决策 D9。
    - Alembic 支持增量 Schema 迁移，Demo 阶段的表结构调整可追溯、可回滚。
  - **负向**：
    - SQLite 不支持并发写操作（单写锁），如果 Web UI 多个请求同时写入告警数据可能触发 `database is locked` 错误。缓解措施：SQLAlchemy 配置 `connect_args={"check_same_thread": False}` + `poolclass=StaticPool`（单线程 FastAPI 下使用单连接）；或使用 WAL 模式（`PRAGMA journal_mode=WAL`）提升并发读性能。
    - SQLite 文件存储在单一路径，需要与 Chroma 的 SQLite 持久化文件分开放置以防冲突。设计建议：业务数据库路径 `./data/webui.db`，Chroma 数据库路径 `./data/chroma_db/`（现有路径保持不变）。

---

### ADR-WEB-003: JWT 认证中间件架构

- **Status**: Accepted
- **Context**:
  - PM 决策 D4 明确 "JWT Token 认证，内置 admin:admin 账号，bcrypt 密码哈希"。
  - PM 决策 D7 明确 "24 小时过期，无 Refresh Token"。
  - REQ-WEBUI-FUNC-025 要求登录页面，成功后返回 JWT Token，前端在所有后续 API 请求中携带。
  - REQ-WEBUI-FUNC-026 要求登出功能（纯前端清除 Token，Demo 阶段无服务端黑名单）。
  - REQ-WEBUI-NFUNC-003 要求 Token 过期后后端返回 401，前端自动跳转登录页面。
  - REQ-WEBUI-NFUNC-004 要求密码使用 bcrypt 哈希存储（不存明文）。
  - FastAPI 使用 `Depends` 依赖注入实现认证保护，这是 FastAPI 的标准认证模式。
  - 所有 `/api/` 端点（除 `/auth/login`）需要 JWT 保护；现有 6 个端点（`/webhook/alert`、`/alerts/simulate`、`/approvals/pending` 等）不在此次 JWT 保护范围内（它们是现有功能接口，Webhook 回调不应要求 JWT）。

- **Options**:
  - **Option A: FastAPI OAuth2PasswordBearer + python-jose 手写**
    - 描述：使用 FastAPI 内置的 `OAuth2PasswordBearer` 提取 Bearer Token，通过 `python-jose` 库（Python 的 JWT 实现）进行 Token 的签发（`jwt.encode`）和验证（`jwt.decode`）。`get_current_user` 作为 FastAPI `Depends` 依赖函数，在需要保护的端点中注入。密码哈希使用 `passlib[bcrypt]`（python-jose 和 passlib 是 FastAPI 官方文档推荐的组合）。
    - 优点：最小化依赖（python-jose + passlib，两个轻量库）；完全控制 Token 的 payload 结构（sub、exp、iat）、签名算法（HS256）、过期逻辑；FastAPI 官方教程直接使用此方案，社区资料丰富；`OAuth2PasswordBearer` 自动集成到 OpenAPI 文档的 Authorize 按钮。
    - 缺点：需要手写 Token 过期检查、401 错误响应格式；如果有 Token 刷新需求需要自行扩展。
  - **Option B: fastapi-jwt-auth 库（或 fastapi-users）**
    - 描述：使用第三方库 `fastapi-jwt-auth` 提供开箱即用的 JWT 认证，包括 Token 生成、验证、刷新、黑名单等高级功能。
    - 优点：功能丰富（内置 refresh token、token 黑名单）。
    - 缺点：`fastapi-jwt-auth` 库已长期未维护（最后更新 2022 年），存在安全补丁缺失风险；PM 决策 D7 明确无 Refresh Token，该库的核心高级功能在本项目中不被需要；引入未维护的第三方依赖不符合安全最佳实践。
  - **Option C: 全局 Starlette Middleware**
    - 描述：编写一个 Starlette `BaseHTTPMiddleware`，在请求到达路由处理函数之前拦截所有 `/api/` 路径的请求，从 Header 中提取 Token 并验证。验证失败直接返回 401，验证成功将用户信息注入 `request.state`。
    - 优点：认证逻辑对所有 `/api/` 端点自动生效，无需每个端点显式声明 `Depends`；中间件级别的拦截在路由匹配之前完成。
    - 缺点：中间件对路径前缀的匹配是字符串级别的，无法像 FastAPI `Depends` 那样灵活地对特定端点排除认证（如 `/auth/login` 需要排除）；中间件中抛出的 HTTPException 处理方式与 FastAPI 异常处理器不一致；无法利用 FastAPI 的依赖注入系统（如无法在中间件中注入数据库 session 来查询用户）；不符合 FastAPI 社区的主流认证模式。

- **Decision**: 选择 **Option A（FastAPI OAuth2PasswordBearer + python-jose 手写）**。

  理由：
  1. **FastAPI 官方推荐方案**：FastAPI 官方文档 "Security" 章节直接使用 `OAuth2PasswordBearer` + `python-jose` + `passlib[bcrypt]` 作为 JWT 认证教程，这是社区验证过的最稳定、最简方案。
  2. **需求精确匹配**：PM 决策 D4（admin 单账号、bcrypt 哈希）、D7（24 小时过期、无 Refresh Token）、REQ-WEBUI-FUNC-025~026（登录/登出）的认证需求非常基础，Option A 完全覆盖，无需引入高级库的复杂功能。
  3. **Depends 注入灵活**：8 个 APIRouter 可在 Router 级别统一声明 `dependencies=[Depends(get_current_user)]`，`/auth/login` 通过 `dependencies=[]` 显式排除。中间件（Option C）难以做到这种细粒度的路径排除。
  4. **admin 账号初始化策略**：系统首次启动时，检查 SQLite `users` 表中是否存在 `admin` 用户——若不存在，从环境变量 `ADMIN_PASSWORD` 读取初始密码（若未设置则使用默认密码 `admin`），通过 `passlib.hash.bcrypt` 哈希后写入数据库。这满足 REQ-WEBUI-NFUNC-004（密码哈希存储）和 PM 决策 D4（内置 admin 账号）。[ASSUMPTION — 默认初始密码 `admin` 的安全性需 PM 确认，生产环境应强制通过环境变量设置]
  5. **Option B 已废弃**：`fastapi-jwt-auth` 库维护停滞，存在安全和兼容性风险，不予采用。

- **Consequences**:
  - **正向**：
    - 完整支撑 REQ-WEBUI-FUNC-025（JWT 登录认证）、REQ-WEBUI-FUNC-026（登出）、REQ-WEBUI-NFUNC-003（24 小时过期）、REQ-WEBUI-NFUNC-004（bcrypt 密码哈希）。
    - Token 验证在 `Depends` 层完成，无效/过期 Token 在到达业务逻辑前被拦截，减少无效数据库查询。
    - OpenAPI 文档中 `/api/` 所有受保护端点自动显示挂锁图标，支持 "Authorize" 按钮直接填写 Token 测试。
  - **负向**：
    - Token 无服务端失效机制（Demo 阶段无黑名单），登出后 Token 在有效期内仍可被重用。风险可接受：Demo 阶段单用户本地部署，Token 泄露风险极低；PM 决策明确 Demo 阶段不引入 Refresh Token / 黑名单复杂度（OOS-WEB-004）。
    - python-jose 和 passlib 两个额外依赖，但均为轻量库，无传递依赖膨胀风险。

---

### ADR-WEB-004: 前端应用架构 — Vue 3 组件树与路由设计

- **Status**: Accepted
- **Context**:
  - PM 决策 D3 明确 "Vue 3 + Vite + Element Plus"。
  - 18 条用户故事（US-WEBUI-001~018）覆盖 8 大功能模块 + 认证 + 全局导航（REQ-WEBUI-FUNC-027~028）。
  - REQ-WEBUI-NFUNC-007 要求桌面端优先（>= 1280px），采用侧边栏 + 内容区布局。
  - REQ-WEBUI-NFUNC-001 要求 Dashboard 首次加载 < 3s，SPA 路由跳转 < 1s。
  - REQ-WEBUI-NFUNC-008 要求所有异步操作有 Loading 状态和操作反馈。
  - 需要前端路由守卫确保未登录用户无法访问任何功能页面（REQ-WEBUI-FUNC-025 AC-W025-04）。
  - 需要前端管理 JWT Token 存储和自动过期跳转（REQ-WEBUI-NFUNC-003 AC-WNF-003-01）。
  - PM 决策 D5 明确 "前端轮询（默认 3 秒间隔）" 用于实时状态更新。

- **Options**:
  - **Option A: 标准 Vue 3 SPA 结构（views/ + components/ 分层）**
    - 描述：采用 Vue 3 社区标准目录结构——`src/views/` 存放页面级组件（每个路由对应一个 view），`src/components/` 存放可复用组件（分为 `common/` 通用 UI 组件和 `layout/` 布局组件），`src/stores/` 存放 Pinia 状态管理，`src/router/` 存放 Vue Router 配置，`src/api/` 存放 Axios 实例和 API 调用封装。
    - 优点：符合 Vue 3 官方文档推荐和社区主流实践；views 与 components 的职责分离清晰（页面 vs 复用组件）；新开发者（或 LLM coding agent）能够快速定位代码位置；Vite 的代码分割基于路由懒加载天然支持，满足 `REQ-WEBUI-NFUNC-001` 的 < 3s 首次加载要求。
    - 缺点：当 views 数量增长时，`views/` 目录可能变得扁平拥挤（8 个功能模块 → 预计 15~20 个 view 文件）。
  - **Option B: Feature-based 目录结构**
    - 描述：按功能模块组织目录——`src/features/alerts/` 内含 `AlertsList.vue`、`AlertsDetail.vue`、`alertsStore.js`、`alertsApi.js` 等，每个 feature 是一个自包含的垂直切片。
    - 优点：功能模块高度内聚，便于未来拆分为微前端；同一 feature 的组件、状态、API 调用放在一起，减少跨目录跳转。
    - 缺点：共享的通用组件（如 DataTable、SearchBar）难以归属；跨 feature 的状态共享需要额外协调；Demo 规模下（8 个功能模块、18 个 story）过度设计；不符合 Vue 3 官方脚手架（`create-vue`）的默认布局，初始搭建时间更长。
  - **Option C: Atomic Design 组件分层**
    - 描述：按 Atom/Molecule/Organism/Template/Page 5 层组件分类组织所有 Vue 组件，严格遵循 Atomic Design 方法论。
    - 优点：组件复用率最大化；设计语言一致性高。
    - 缺点：Demo 项目组件数量有限（预计 ~30 个 .vue 文件），强制 5 层分类导致大量空层或单组件层；Element Plus 已经提供了 Atom 和 Molecule 级别的组件库，我们的组件主要是 Organism（组合业务组件）和 Page 级别；方法论开销远大于收益。

- **Decision**: 选择 **Option A（标准 Vue 3 SPA 结构）+ 适度使用 Feature-based 子目录**。

  理由：
  1. **Vue 社区标准**：`create-vue` 脚手架生成的默认结构就是 `views/` + `components/` + `stores/` + `router/`。Zero learning curve for any Vue developer.
  2. **路由懒加载天然支持**：Vite 对 `() => import('@/views/alerts/AlertsList.vue')` 自动进行代码分割，每个 view 及其依赖打包为独立 chunk。首次访问 Dashboard 只需加载 Dashboard chunk（~50KB gzipped），满足 REQ-WEBUI-NFUNC-001 的 < 3s 加载要求。
  3. **Flattening 缓解**：在 `views/` 下按功能模块建子目录（`views/alerts/`、`views/devices/` 等），避免 20+ 个 view 文件扁平堆积。在 `components/` 下按用途分 `common/` 和 `layout/`。这种 "适度 Feature-based" 方案是 Vue 社区的演化共识。
  4. **路由表设计（9 个一级路由 + 嵌套路由）**：顶级 `/login` 路由不经过布局组件，其他路由共享 `AppLayout`（侧边栏 + Header + 面包屑），满足 REQ-WEBUI-FUNC-027~028 的全局导航需求。路由守卫 `beforeEach` 检查 Pinia auth store 中的 Token 有效性，未登录重定向 `/login`，满足 REQ-WEBUI-FUNC-025 AC-W025-04。
  5. **Option B 和 C 在 Demo 规模下过度设计**：18 条 User Story、预计 15~20 个页面，Feature-based 和 Atomic Design 的目录层级引入不必要的认知开销。

- **Consequences**:
  - **正向**：
    - 完整支撑 REQ-WEBUI-FUNC-001~028 全部 28 条功能需求的 Web 界面实现。
    - 路由守卫确保 REQ-WEBUI-FUNC-025（未登录拦截）和 REQ-WEBUI-NFUNC-003（Token 过期自动跳转）。
    - Pinia 状态管理提供 7 个 Store（auth、alerts、approvals、devices、inspection、knowledge、system），前端数据流清晰可控。
    - Axios 拦截器统一注入 JWT Token（`Authorization: Bearer {token}`）和处理 401 响应（清除 Token + 重定向登录页）。
    - Vite 构建的代码分割 + Tree Shaking 确保 Dashboard 首次加载满足 REQ-WEBUI-NFUNC-001 < 3s。
  - **负向**：
    - 前端项目初始搭建需要配置 Vue Router、Pinia、Axios 拦截器、Element Plus 全局注册，一次性配置成本约 2~3 小时。
    - 如果 Demo 后需要扩展至 50+ 页面，当前的 views/ 扁平子目录可能需要重构为 Feature-based（但 Demo 阶段无此风险）。

---

### ADR-WEB-005: 前端静态文件托管策略

- **Status**: Accepted
- **Context**:
  - PM 决策 D3 要求 "Vue 3 + Vite + Element Plus" 前端框架。
  - PM 决策 D1 要求 "FastAPI 扩展，单进程部署，端口 8000"。
  - REQ-WEBUI-NFUNC-001 要求页面加载 < 3s（影响静态资源加载方式）。
  - Demo 规模：单机部署，无 CDN，无负载均衡。
  - 环境分离需求：开发时需要热重载（HMR），生产时需要最小化构建产物。
  - 前后端在同一项目中，版本需要同步部署。

- **Options**:
  - **Option A: 开发 Vite dev server proxy → 生产 FastAPI 挂载静态文件**
    - 描述：开发阶段，Vite dev server 运行在 `localhost:5173`，通过 `vite.config.ts` 的 `server.proxy` 将 `/api/*` 和 `/webhook/*` 请求代理到 FastAPI `localhost:8000`。前端开发者获得 HMR（热模块替换）即时反馈。生产阶段，`npm run build` 生成 `dist/` 目录，FastAPI 通过 `app.mount("/", StaticFiles(directory="dist", html=True))` 将 SPA 静态文件直接挂载到根路径；API 路由通过 `/api/*` 前缀与静态文件路径空间无冲突。
    - 优点：开发体验最佳（Vite HMR < 1s 反馈）；生产部署极简（无需 Nginx，FastAPI 单进程同时服务 API 和静态文件）；前后端同一端口（8000），避免 CORS 跨域问题；SPA fallback 由 `html=True` 自动处理（所有非 API 路径返回 index.html）。
    - 缺点：FastAPI 的 StaticFiles 中间件使用 `aiofiles`，对于大量并发静态资源请求不如 Nginx 高效。但 Demo 单用户场景此差异可忽略。
  - **Option B: Nginx 反向代理统一入口**
    - 描述：Nginx 监听 80 端口，`location /api/` 代理到 FastAPI 8000，`location /` 指向 Vue 构建产物 `dist/` 目录。开发阶段同样使用 Nginx 或保留 Vite proxy。
    - 优点：生产级方案（Nginx 静态文件性能 > FastAPI StaticFiles，支持 gzip_static、缓存头、限流等）；前端和后端可以独立部署和扩容。
    - 缺点：Demo 需要额外安装和配置 Nginx，增加部署步骤（OOS-WEB-003 注释了 "Demo 不引入 Docker"；虽然 Nginx 不是 Docker，但额外系统依赖违背 Demo 简化原则）；开发阶段仍需 Vite proxy 或额外 Nginx 配置；前后端分离端口增加了 CORS 管理需求。
  - **Option C: 前后端完全分离部署**
    - 描述：前端部署到独立静态服务器（如 Vercel / GitHub Pages / nginx 独立服务器），后端 FastAPI 单独运行。通过 CORS 配置允许跨域请求。
    - 优点：前后端独立发布和回滚；前端可上 CDN 加速。
    - 缺点：Demo 不需要独立发布策略；引入跨域 CORS 安全配置复杂度；增加部署节点数（两个独立服务），与 Demo 单机简化原则相悖。

- **Decision**: 选择 **Option A（开发 Vite dev server proxy → 生产 FastAPI 挂载静态文件）**。

  理由：
  1. **Demo 极简部署**：PM 决策 D1 明确 "单进程部署，端口 8000"。Option A 天然满足——一个 `uvicorn` 进程同时服务 API（`/api/*`、`/webhook/alert`）和前端静态文件（`/`），运维人员只需 `python src/main.py` 一条命令。
  2. **零 CORS 配置**：前后端同域同端口，浏览器不会触发 CORS 预检请求，前端 `axios.post('/api/alerts')` 直接可用。开发阶段通过 Vite proxy 也实现了同域效果。满足 REQ-WEBUI-NFUNC-006（安全输入校验）的隐含同源策略优势。
  3. **SPA Fallback**：FastAPI `StaticFiles(html=True)` 参数自动将非文件路径（如 `/alerts`、`/devices`）的请求 fallback 到 `index.html`，由 Vue Router 接管客户端路由。无需额外配置 `@app.middleware` 或 Nginx `try_files`。
  4. **开发/生产一致性**：开发时的 Vite proxy 配置（`/api` → 8000）与生产时的同端口部署保持了相同的 URL 结构（`/api/*`），前端代码无需根据环境切换 `baseURL`。
  5. **Option B 增加部署负担**：Nginx 安装和配置在 Demo 中是额外的操作步骤，且 Agent 后续部署到 Alibaba Cloud VPS 时增加一个系统服务依赖，与 Demo 简化原则相悖。如果后续生产化需要 Nginx，从 Option A 迁移到 Option B 的改动极小（仅需移除 `app.mount` 并配置 Nginx）。

- **Consequences**:
  - **正向**：
    - 完整支撑 PM 决策 D1（单进程 8000 端口部署）、PM 决策 D3（Vite 构建产物托管）。
    - 开发体验满足现代前端 HMR 标准（< 1s 热更新）。
    - 无 CORS 问题（同源部署），降低前端开发调试复杂度。
    - SPA fallback 自动处理，无需额外中间件。
  - **负向**：
    - FastAPI `StaticFiles` 不支持 gzip 预压缩（`dist/` 中的 `.gz` 文件不会自动服务）。缓解：Vite 构建关闭 gzip 生成（`build.target` 设 `es2015`，现代浏览器原生解压），或使用 `aiofiles` 的 `Content-Encoding` header 手动处理（Demo 阶段文件小，不必要）。
    - 首次部署时需要先执行 `npm run build` 生成 `dist/` 目录，再启动 FastAPI。建议在 `main.py` 的 lifespan 启动阶段检查 `dist/index.html` 是否存在，不存在则 logger.warning 提示，但不阻止启动（允许纯 API 模式运行）。

---

### ADR-WEB-006: 敏感数据加密架构 — 密码 + API Key 存储安全

- **Status**: Accepted
- **Context**:
  - REQ-WEBUI-NFUNC-004（Must Have）要求 admin 密码使用 bcrypt 或 argon2 哈希存储，不存明文。
  - REQ-WEBUI-NFUNC-005（Must Have）要求 DeepSeek API Key 在 SQLite 中加密存储（AES-256），禁止明文。
  - REQ-WEBUI-FUNC-011 要求设备 SSH 凭据密码加密存储（AES-256）。
  - REQ-WEBUI-FUNC-020 要求 API Key 在界面上掩码显示，传输安全。
  - PM 决策 D4 和 D8 确认 bcrypt 和密码显示/隐藏切换。
  - PM 决策 D9 未涉及加密方案的选型，此处需由架构师决策。
  - 加密密钥管理：Demo 阶段从环境变量 `ENCRYPTION_KEY` 获取，若未设置则在首次启动时随机生成并输出至控制台（或持久化至本地文件 `./data/.encryption_key`）。加密密钥不得硬编码在源代码中。
  - 现有系统（MOD-006 LLMService）的 DEEPSEEK_API_KEY 当前通过环境变量直接读取。Web UI 新增后，API Key 将存储在 SQLite（加密）中，LLMService 需改为从加密存储中解密获取。

- **Options**:
  - **Option A: Python cryptography 库手写（Primitives-level）**
    - 描述：使用 `cryptography` 库的底层原语——`Cipher(algorithms.AES(...), modes.CBC(...))` 手动实现 AES-256-CBC 加密/解密，自行管理 IV（初始化向量）生成、PKCS7 填充、HMAC 完整性校验。bcrypt 通过 `cryptography` 或直接使用 `bcrypt` 包实现。
    - 优点：完全控制加密实现的每个细节；不需要额外的依赖。
    - 缺点：密码学原语的使用极易出错——错误的 IV 管理（如固定 IV）、错误的填充实现、忘记 HMAC 认证等都可能产生安全漏洞；需要自行处理密钥派生（从 ENCRYPTION_KEY 字符串到 256-bit AES 密钥需要 KDF）；代码量较大且难以审查。
  - **Option B: passlib[bcrypt] + cryptography.fernet（High-level API）**
    - 描述：bcrypt 密码哈希使用 `passlib[bcrypt]`（FastAPI 官方推荐，简单安全的 API：`hash(password)` / `verify(password, hash)`）。对称加密使用 `cryptography.fernet.Fernet`，这是一个高级加密 API，自动处理 AES-128-CBC（Fernet 规范）、HMAC-SHA256 认证、IV 生成、PKCS7 填充、时间戳防重放。调用方只需 `Fernet(key).encrypt(data)` / `Fernet(key).decrypt(data)`。密钥管理：从环境变量 `ENCRYPTION_KEY` 读取 32 字节 URL-safe base64 编码的密钥，若未设置则调用 `Fernet.generate_key()` 生成并持久化。
    - 优点：`passlib[bcrypt]` 是社区验证最充分的 Python bcrypt 实现，FastAPI 官方文档直接推荐；`cryptography.fernet` 提供 "安全默认" 的加密 API，无法误用（API 设计限制了 IV/填充/HMAC 的暴露）；加密输出为标准 Fernet token（Base64 编码，包含版本号 + 时间戳 + IV + 密文 + HMAC），自动防篡改和一定程度的防重放。
    - 缺点：Fernet 使用 AES-128（而非需求文档提到的 AES-256）。说明：Fernet 的 128-bit 密钥在计算安全级别上已经满足 NIST 标准（AES-128 目前被认为与 AES-256 等效抵抗暴力破解，因为 2^128 的密钥空间在量子计算前不可行）。如果 PM 严格要求 AES-256，需要使用 `cryptography` 的 `MultiFernet` 或自定义 `Cipher` 封装。
  - **Option C: 平台密钥管理（Cloud KMS / Vault）**
    - 描述：使用外部密钥管理服务（如阿里云 KMS、HashiCorp Vault）托管加密密钥，应用层通过 SDK 调用加密/解密 API，密钥本身不接触应用服务器。
    - 优点：最高安全级别；密钥轮换、审计、权限控制由平台提供。
    - 缺点：Demo 阶段引入外部 KMS 服务大幅增加部署复杂度（需要额外的云服务账号、网络配置、SDK 集成）；违背 Demo 单机自包含原则；如果网络不通则整个加密解密链路不可用。

- **Decision**: 选择 **Option B（passlib[bcrypt] + cryptography.fernet）**。

  理由：
  1. **安全默认优于手工实现**：`cryptography.fernet` 的 API 设计遵循 "安全默认"（secure-by-default）原则——开发者无法接触到 IV、填充、HMAC 等易错细节，只需 `encrypt(plaintext) → token` 和 `decrypt(token) → plaintext`。Option A 的手工 AES-256-CBC 实现在密码学上极易出错（如 CBC 模式下固定 IV 导致确定性加密泄漏明文模式），Demo 阶段不应承担此风险。
  2. **passlib 是 FastAPI 生态标准**：REQ-WEBUI-NFUNC-004 要求 bcrypt，`passlib[bcrypt]` 的 `hash()` 自动处理 salt 生成（`$2b$12$...` 中的 12 为 cost factor），`verify()` 自动从哈希中提取 salt 进行比对。API 极简且安全。
  3. **AES-128 vs AES-256 的权衡说明**：需求文档 REQ-WEBUI-NFUNC-005 提到 "AES-256"，但 `cryptography.fernet` 实现的是 AES-128-CBC + HMAC-SHA256。从安全角度，AES-128 密钥空间（2^128）在经典和量子计算模型下均足够安全（NIST SP 800-57 将 AES-128 归类为 "至少到 2030 年后仍安全"）。如果 PM 坚持 AES-256 要求，可通过 `cryptography.hazmat.primitives` 的 `MultiFernet` 或自定义 `AES-256-GCM` 实现来满足，但会增加实现复杂度。[ASSUMPTION — AES-128（Fernet）的安全级别是否满足 PM 的 "AES-256" 要求需要确认。若不满足，架构可切换为 `cryptography` 的 AES-256-GCM 原语 + 手写封装，但优先推荐 Fernet 的安全简易方案]
  4. **密钥管理策略**：
     - 优先级 1：环境变量 `ENCRYPTION_KEY`（32 字节 URL-safe base64）。生产部署时运维人员通过 `.env` 或系统环境变量注入。
     - 优先级 2：若未设置环境变量，系统首次启动时调用 `Fernet.generate_key()` 随机生成密钥，写入本地文件 `./data/.encryption_key`（仅 owner 可读 `chmod 600`），并在控制台 logger.warning 输出 "Encryption key generated and saved to ./data/.encryption_key. Keep this file secure."。后续启动从该文件加载。
     - 反模式：**绝不将密钥硬编码在源代码中**（REQ-WEBUI-NFUNC-005 要求）——代码审查扫描 `Fernet(` 调用时硬编码的字符串应被标记为安全违规。
  5. **LLMService 改造**：新增的 `EncryptionService` 模块（MOD-WEB-005）提供 `encrypt(value: str) -> str` 和 `decrypt(token: str) -> str` 接口。LLMService 在启动时检查 SQLite 中是否有加密存储的 API Key（通过 `system_config` 表），若有则解密使用；若无则回退到环境变量 `DEEPSEEK_API_KEY`（向后兼容现有部署）。这实现了从环境变量到加密数据库的平滑过渡。

- **Consequences**:
  - **正向**：
    - 完整支撑 REQ-WEBUI-NFUNC-004（bcrypt 密码哈希）、REQ-WEBUI-NFUNC-005（API Key 加密存储）、REQ-WEBUI-FUNC-011（设备凭据密码加密）、REQ-WEBUI-FUNC-020（API Key 安全配置）。
    - `cryptography.fernet` 的 token 格式自带版本号和时间戳，可以实现轻量的密钥轮换（通过 `MultiFernet` 同时支持旧密钥解密和新密钥加密）。
    - `passlib[bcrypt]` 的 cost factor 可配置（默认 12 rounds），可根据硬件性能调整哈希强度。
  - **负向**：
    - Fernet 使用 AES-128 而非 AES-256，如果 PM 严格要求 AES-256，需要升级为自定义 AES-256-GCM 实现。[ASSUMPTION — 待 PM 确认]
    - 密钥文件 `./data/.encryption_key` 如果丢失，所有加密数据（数据库中的 API Key 和设备密码）将不可解密，等同于数据丢失。缓解：在部署文档中明确标注此文件的备份重要性；或建议生产部署时仅使用环境变量方案。
    - `cryptography` 和 `passlib` 两个新依赖，但均为 Python 安全领域标准库，无安全风险。

---

## 需求到模块覆盖矩阵

### 功能需求 → 前端组件 + 后端模块 映射

| REQ ID | 需求描述（摘要） | 前端组件（Vue） | 后端模块（FastAPI） |
|--------|---------------|----------------|-------------------|
| REQ-WEBUI-FUNC-001 | 告警列表查看与筛选 | AlertsListView | alerts_router (GET /api/alerts) |
| REQ-WEBUI-FUNC-002 | 告警详情查看 | AlertsDetailView | alerts_router (GET /api/alerts/{id}) |
| REQ-WEBUI-FUNC-003 | 手动模拟发送告警 | AlertsSimulateView | alerts_router (POST /api/alerts/simulate) |
| REQ-WEBUI-FUNC-004 | 告警处理流程实时状态追踪 | AlertsDetailView (WorkflowTab) | alerts_router (GET /api/alerts/{id}/workflow) |
| REQ-WEBUI-FUNC-005 | LangGraph 节点拓扑可视化 | WorkflowGraphView | workflow_router (GET /api/workflow/graph) |
| REQ-WEBUI-FUNC-006 | 节点 State 快照查看 | WorkflowNodeDetail | workflow_router (GET /api/workflow/{id}/nodes/{name}) |
| REQ-WEBUI-FUNC-007 | 待审批列表展示 | ApprovalsPendingView | approvals_router (GET /api/approvals/pending) |
| REQ-WEBUI-FUNC-008 | 审批决策操作 | ApprovalsDetailView | approvals_router (POST /api/approvals/{id}/decide) |
| REQ-WEBUI-FUNC-009 | 审批历史记录 | ApprovalsHistoryView | approvals_router (GET /api/approvals/history) |
| REQ-WEBUI-FUNC-010 | 纳管设备 CRUD | DevicesListView, DevicesEditDialog | devices_router (CRUD: GET/POST/PUT/DELETE /api/devices) |
| REQ-WEBUI-FUNC-011 | 设备凭据配置 | DeviceCredentialsDialog | devices_router (PUT /api/devices/{id}/credentials) |
| REQ-WEBUI-FUNC-012 | 设备诊断结果查看 | DeviceDiagnosticsView | devices_router (GET /api/devices/{id}/diagnostics) |
| REQ-WEBUI-FUNC-013 | 巡检间隔配置 | InspectionConfigView | inspection_router (GET/PUT /api/inspection/config) |
| REQ-WEBUI-FUNC-014 | 手动触发巡检 | InspectionConfigView | inspection_router (POST /api/inspection/trigger) |
| REQ-WEBUI-FUNC-015 | 巡检历史记录 | InspectionHistoryView | inspection_router (GET /api/inspection/history) |
| REQ-WEBUI-FUNC-016 | 知识文档 CRUD | KnowledgeDocumentsView | kb_router (CRUD: GET/POST/PUT/DELETE /api/knowledge/documents) |
| REQ-WEBUI-FUNC-017 | 命令模板 CRUD | KnowledgeTemplatesView | kb_router (CRUD: GET/POST/PUT/DELETE /api/knowledge/templates) |
| REQ-WEBUI-FUNC-018 | 知识库检索测试界面 | KnowledgeTestRetrievalView | kb_router (POST /api/knowledge/test-retrieval) |
| REQ-WEBUI-FUNC-019 | 全局配置可视化编辑 | SystemConfigView | config_router (GET/PUT /api/system/config) |
| REQ-WEBUI-FUNC-020 | LLM API Key 安全配置 | SystemConfigView (LLMTab) | config_router (PUT /api/system/config/llm-api-key, POST /api/system/config/llm-test) |
| REQ-WEBUI-FUNC-021 | 日志查看 | SystemLogsView | config_router (GET /api/system/logs) |
| REQ-WEBUI-FUNC-022 | 告警统计图表 [INFERRED] | DashboardView (AlertStatsCharts) | dashboard_router (GET /api/dashboard/stats) |
| REQ-WEBUI-FUNC-023 | 修复成功率统计 | DashboardView (FixRateChart) | dashboard_router (GET /api/dashboard/stats) |
| REQ-WEBUI-FUNC-024 | 系统健康状态面板 | DashboardView (HealthPanel) | dashboard_router (GET /api/dashboard/health) |
| REQ-WEBUI-FUNC-025 | 用户登录与 JWT 认证 | LoginView | auth_router (POST /auth/login) + AuthService |
| REQ-WEBUI-FUNC-026 | 用户登出 | AppShell (LogoutButton) | auth_router (POST /auth/logout, 预留) |
| REQ-WEBUI-FUNC-027 | 全局导航菜单 | AppShell (SidebarNav) | — (纯前端) |
| REQ-WEBUI-FUNC-028 | 全局面包屑导航 | AppShell (BreadcrumbNav) | — (纯前端) |

### 非功能需求 → 架构决策 映射

| REQ ID | 需求描述（摘要） | 关联 ADR | 覆盖方式 |
|--------|---------------|---------|---------|
| REQ-WEBUI-NFUNC-001 | 页面加载 < 3s | ADR-WEB-004, ADR-WEB-005 | Vite 代码分割 + 路由懒加载 + FastAPI 本地静态文件服务 |
| REQ-WEBUI-NFUNC-002 | 浏览器兼容性 Chrome/Edge | ADR-WEB-004 | Vue 3 + Element Plus 官方支持 Chrome >= 90、Edge >= 90 |
| REQ-WEBUI-NFUNC-003 | JWT Token 过期 (24h) | ADR-WEB-003 | python-jose 签发 `exp` claim，Depends 层验证过期 |
| REQ-WEBUI-NFUNC-004 | 密码 bcrypt 哈希 | ADR-WEB-006 | passlib[bcrypt] 哈希存储 + 验证 |
| REQ-WEBUI-NFUNC-005 | API Key AES 加密存储 | ADR-WEB-006 | cryptography.fernet AES-128-CBC + HMAC-SHA256 |
| REQ-WEBUI-NFUNC-006 | XSS / SQL 注入防护 | ADR-WEB-001, ADR-WEB-002 | Vue 3 模板自动转义、Element Plus 表单校验、SQLAlchemy 参数化查询 |
| REQ-WEBUI-NFUNC-007 | 桌面端布局 >= 1280px | ADR-WEB-004 | Element Plus Layout + 侧边栏 220px 固定 |
| REQ-WEBUI-NFUNC-008 | Loading 与操作反馈 | ADR-WEB-004 | Element Plus v-loading 指令 + ElMessage/ElNotification |

---

## 开放问题

| 编号 | 问题 | 关联 ADR | 状态 |
|------|------|---------|------|
| Q-WEB-ARCH-001 | [ASSUMPTION] AES-128（Fernet）的安全级别是否满足 PM 的 "AES-256" 要求？Fernet 使用 AES-128-CBC + HMAC-SHA256，若 PM 严格要求 AES-256，需切换为自定义 AES-256-GCM 实现 | ADR-WEB-006 | 待 PM 确认 |
| Q-WEB-ARCH-002 | [ASSUMPTION] admin 默认初始密码 `admin` 是否可接受？建议生产环境通过 `ADMIN_PASSWORD` 环境变量强制设置 | ADR-WEB-003 | 待 PM 确认 |
| Q-WEB-ARCH-003 | [ASSUMPTION] 加密密钥文件 `.encryption_key` 的存储位置和权限策略是否需要额外指导？ | ADR-WEB-006 | 待 PM 确认 |
| Q-WEB-ARCH-004 | [ASSUMPTION] Alembic 迁移是否必须？Demo 阶段可通过 `Base.metadata.create_all()` 自动建表简化流程，但会失去 Schema 版本管理 | ADR-WEB-002 | 待 PM 确认 |
| Q-WEB-ARCH-005 | [ASSUMPTION] 旧端点 `POST /alerts/simulate`（query params）保留标记为 deprecated 并在 Web UI 上线后移除，时间线是否可接受？ | ADR-WEB-001 | 待 PM 确认 |
| Q-WEB-ARCH-006 | [ASSUMPTION] ECharts 5.x 为图表库选型（见 webui_tech_stack.md），是否满足 PM 的图表需求？ECharts 是 Apache 开源项目，支持所有要求的图表类型 | ADR-WEB-004 | 待 PM 确认 |
