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
    <file>architecture/webui_architecture_design.md</file>
    <file>src/main.py</file>
  </input_files>
  <phase>PHASE_W04</phase>
  <status>APPROVED</status>
</file_header>

# Web 管理界面模块设计文档 — NetworkAgentDemo

---

## 模块总览

### 后端新增模块

| MOD-ID | 模块名 | 层级 | 职责 | 依赖于 |
|--------|--------|------|------|--------|
| MOD-WEB-001 | APIRouterLayer | Web 表现层 | 组织 8 个 APIRouter，将 32+ 个端点按功能域拆分，统一 JWT 依赖注入 | MOD-WEB-002, MOD-WEB-003, MOD-WEB-004, MOD-WEB-005, MOD-WEB-006, MOD-WEB-007, Existing MOD-002/003/004/006/008 |
| MOD-WEB-002 | AuthService | Web 表现层 | JWT Token 签发/验证、bcrypt 密码哈希/比对、admin 账号初始化 | MOD-WEB-003 |
| MOD-WEB-003 | DatabaseManager | 数据持久化层 | SQLAlchemy engine/session/Base 管理、Alembic 迁移配置、11 个 ORM Model 定义（6 个领域文件） | — |
| MOD-WEB-004 | DataAccessLayer | 数据持久化层 | 7 个 Repository 类，封装各数据实体的 SQLAlchemy CRUD 操作 | MOD-WEB-003 |
| MOD-WEB-005 | EncryptionService | 安全层 | AES 对称加密/解密（Fernet）、密钥生命周期管理 | — |
| MOD-WEB-006 | DashboardService | Web 表现层 | Dashboard 聚合统计查询（告警统计/修复成功率/趋势数据） | MOD-WEB-004 |
| MOD-WEB-007 | LogReaderService | Web 表现层 | 文件日志读取、关键词搜索、日志级别过滤、分页 | — |

### 现有模块增强点

| 现有 MOD-ID | 增强内容 | 触发需求 |
|-------------|---------|---------|
| MOD-002 (InspectionScheduler) | 设备列表从 SQLite 动态加载（替代硬编码）、手动触发巡检 API 集成 | REQ-WEBUI-FUNC-010, REQ-WEBUI-FUNC-014 |
| MOD-004 (AlertNormalizer) | 归一化后的 Alert 对象同步持久化到 SQLite alerts 表 | REQ-WEBUI-FUNC-001 |
| MOD-005 (NodeHandlers) | 各节点执行后写入 alert_timeline 表；审批节点持久化到 approvals 表 | REQ-WEBUI-FUNC-002, REQ-WEBUI-FUNC-009 |
| MOD-006 (LLMService) | API Key 优先从 EncryptionService 解密后的 SQLite 配置读取，若无则回退环境变量 | REQ-WEBUI-FUNC-020, REQ-WEBUI-NFUNC-005 |
| MOD-003 (StateGraphEngine) | get_pending_approvals() 增强返回审批详情（从 SQLite approvals 表关联 alerts 表） | REQ-WEBUI-FUNC-007 |

### 前端模块

| MOD-ID | 模块名 | 类型 | 职责 |
|--------|--------|------|------|
| MOD-WEB-F01 | AppShell | Layout 组件 | 侧边栏导航 + 顶部 Header + 面包屑 + 内容区 `<router-view>` |
| MOD-WEB-F02 | Router | 路由配置 | Vue Router 路由表（9 个一级路由 + 嵌套路由 + 全局前置守卫） |
| MOD-WEB-F03 | ApiClient | HTTP 客户端 | Axios 实例 + 请求拦截器（JWT 注入）+ 响应拦截器（401 处理） |
| MOD-WEB-F04 | AuthStore | Pinia Store | 认证状态（token、user、login/logout actions） |
| MOD-WEB-F05 | AlertsStore | Pinia Store | 告警列表/详情/筛选/模拟告警 actions |
| MOD-WEB-F06 | ApprovalsStore | Pinia Store | 待审批列表/审批决策/审批历史 actions |
| MOD-WEB-F07 | DevicesStore | Pinia Store | 设备 CRUD/凭据配置 actions |
| MOD-WEB-F08 | InspectionStore | Pinia Store | 巡检配置/手动触发/巡检历史 actions |
| MOD-WEB-F09 | KnowledgeStore | Pinia Store | 知识文档 CRUD/命令模板 CRUD/检索测试 actions |
| MOD-WEB-F10 | SystemStore | Pinia Store | 全局配置/日志查询/API Key 管理 actions |
| MOD-WEB-F11 | DashboardStore | Pinia Store | Dashboard 统计数据/系统健康状态 actions |
| MOD-WEB-F12 | DashboardView | 页面组件 | Dashboard 首页（统计卡片 + 图表 + 健康面板） |
| MOD-WEB-F13 | AlertsViewGroup | 页面组件组 | 告警列表/详情/模拟告警页面 |
| MOD-WEB-F14 | WorkflowViewGroup | 页面组件组 | 工作流拓扑图/节点 State 快照页面 |
| MOD-WEB-F15 | ApprovalsViewGroup | 页面组件组 | 待审批列表/审批详情/审批历史页面 |
| MOD-WEB-F16 | DevicesViewGroup | 页面组件组 | 设备列表/设备编辑/凭据配置/诊断记录页面 |
| MOD-WEB-F17 | InspectionViewGroup | 页面组件组 | 巡检配置/巡检历史页面 |
| MOD-WEB-F18 | KnowledgeViewGroup | 页面组件组 | 知识文档列表/文档编辑/命令模板列表/模板编辑/检索测试页面 |
| MOD-WEB-F19 | SystemViewGroup | 页面组件组 | 全局配置/API Key 配置/系统日志页面 |
| MOD-WEB-F20 | LoginView | 页面组件 | 登录页面（独立布局，不经过 AppShell） |

---

## 后端模块详情

---

### MOD-WEB-001: APIRouterLayer

- **职责**: 组织全部 Web UI 所需的 REST API 端点，按功能域拆分为 8 个 FastAPI APIRouter 子模块，统一挂载 JWT 认证依赖，统一 `/api` 前缀。在 `main.py` 中通过 `app.include_router()` 挂载，与现有 6 个端点共存。
- **覆盖需求**: REQ-WEBUI-FUNC-001~024, REQ-WEBUI-FUNC-025~026
- **关联用户故事**: US-WEBUI-001~018

- **公开接口契约（Router 注册）**:

  - **IFC-WEB-001-01**: `auth_router = APIRouter(prefix="/auth", tags=["Authentication"], dependencies=[])`
    - 排除 JWT 依赖（登录端点不需要认证）

  - **IFC-WEB-001-02**: `api_router = APIRouter(prefix="/api", dependencies=[Depends(get_current_user)])`
    - 所有 `/api/` 端点统一 JWT 保护
    - 子 Router 挂载到此 Router 下：
      - `alerts_router` — `/api/alerts`（REQ-WEBUI-FUNC-001~004）
      - `workflow_router` — `/api/workflow`（REQ-WEBUI-FUNC-005~006）
      - `approvals_router` — `/api/approvals`（REQ-WEBUI-FUNC-007~009）
      - `devices_router` — `/api/devices`（REQ-WEBUI-FUNC-010~012）
      - `inspection_router` — `/api/inspection`（REQ-WEBUI-FUNC-013~015）
      - `kb_router` — `/api/knowledge`（REQ-WEBUI-FUNC-016~018）
      - `config_router` — `/api/system`（REQ-WEBUI-FUNC-019~021）
      - `dashboard_router` — `/api/dashboard`（REQ-WEBUI-FUNC-022~024）

- **8 个 APIRouter 详细端点清单**:

| Router 文件 | 包含端点 | 数量 |
|------------|---------|------|
| `src/api/auth_router.py` | POST `/auth/login`, POST `/auth/logout` | 2 |
| `src/api/alerts_router.py` | GET `/api/alerts`, GET `/api/alerts/{alert_id}`, GET `/api/alerts/{alert_id}/workflow`, POST `/api/alerts/simulate` | 4 |
| `src/api/workflow_router.py` | GET `/api/workflow/graph`, GET `/api/workflow/{checkpoint_id}/nodes/{node_name}`, GET `/api/workflow/{checkpoint_id}/state` | 3 |
| `src/api/approvals_router.py` | GET `/api/approvals/pending`, POST `/api/approvals/{checkpoint_id}/decide`, GET `/api/approvals/history` | 3 |
| `src/api/devices_router.py` | GET/POST `/api/devices`, GET/PUT/DELETE `/api/devices/{device_id}`, PUT `/api/devices/{device_id}/credentials`, GET `/api/devices/{device_id}/diagnostics` | 7 |
| `src/api/inspection_router.py` | GET/PUT `/api/inspection/config`, POST `/api/inspection/trigger`, GET `/api/inspection/history` | 4 |
| `src/api/kb_router.py` | CRUD `/api/knowledge/documents` (5), CRUD `/api/knowledge/templates` (5), POST `/api/knowledge/test-retrieval` | 11 |
| `src/api/config_router.py` | GET/PUT `/api/system/config`, PUT `/api/system/config/llm-api-key`, POST `/api/system/config/llm-test`, GET `/api/system/logs` | 5 |
| `src/api/dashboard_router.py` | GET `/api/dashboard/stats`, GET `/api/dashboard/health` | 2 |
| **合计** | | **41 端点**（含现有增强在内） |

- **依赖模块**:
  - MOD-WEB-002 AuthService（JWT 验证依赖注入 `get_current_user`）
  - MOD-WEB-003 DatabaseManager（DB session 依赖注入 `get_db`）
  - MOD-WEB-004 DataAccessLayer（CRUD 操作委托）
  - MOD-WEB-005 EncryptionService（凭据加密/解密）
  - MOD-WEB-006 DashboardService（聚合统计）
  - MOD-WEB-007 LogReaderService（文件日志查询）
  - 现有 MOD-002, MOD-003, MOD-004, MOD-006, MOD-008（业务逻辑层调用）

- **外部依赖**: FastAPI, Pydantic

- **依赖注入（dependencies.py）设计**:
  - `get_db() → Session`: FastAPI `Depends` 生成器，yield SQLAlchemy Session，请求结束后自动 close
  - `get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) → User`: 从 JWT Token 解析 `sub`（username），在 SQLite users 表中查询用户，不存在则 401

- **向后兼容保证**:
  - 现有 `main.py` 中的 6 个端点（`/webhook/alert`、`/alerts/simulate`、`/approvals/pending`、`/approvals/{id}/decide`、`/workflow/{id}/state`、`/health`）**完全不动**，仅追加 `app.include_router(auth_router)` 和 `app.include_router(api_router)` 两行
  - D10 废弃路径：旧 `POST /alerts/simulate` 保留但标记 `deprecated=True`，响应中增加 `"warning": "This endpoint is deprecated, use POST /api/alerts/simulate instead"`
  - PM 决策：Web UI 上线后可移除旧端点

---

### MOD-WEB-002: AuthService

- **职责**: JWT Token 生命周期管理（签发/验证/过期检查）+ 密码安全处理（bcrypt 哈希/比对）+ admin 账号初始化策略。
- **覆盖需求**: REQ-WEBUI-FUNC-025, REQ-WEBUI-FUNC-026, REQ-WEBUI-NFUNC-003, REQ-WEBUI-NFUNC-004
- **关联用户故事**: US-WEBUI-017

- **公开接口契约**:
  - **IFC-WEB-002-01**: `authenticate(username: str, password: str, db: Session) → str | None`
    - 输入: 明文用户名和密码
    - 输出: 验证成功返回 JWT access_token 字符串，失败返回 None
    - 内部步骤: 查询 users 表 → passlib.verify(password, password_hash) → 成功则 jwt.encode()
    - JWT Payload: `{"sub": username, "exp": now + 86400, "iat": now, "type": "access"}`

  - **IFC-WEB-002-02**: `get_user_from_token(token: str, db: Session) → User | None`
    - 输入: JWT Token 字符串
    - 输出: 验证成功返回 SQLAlchemy User 对象，过期/无效返回 None
    - 内部步骤: jwt.decode() → 检查 exp → 查询 users 表 by username

  - **IFC-WEB-002-03**: `init_admin_user(db: Session) → None`
    - 系统启动时调用，检查 users 表中是否有 username="admin" 的记录
    - 若不存在：从 `ADMIN_PASSWORD` 环境变量读取密码（若未设则用 `admin`），bcrypt 哈希后写入
    - 若存在：跳过（幂等操作）

  - **IFC-WEB-002-04**: `hash_password(password: str) → str`
    - bcrypt 哈希，cost factor = 12，返回 `$2b$12$...` 格式

  - **IFC-WEB-002-05**: `verify_password(password: str, password_hash: str) → bool`
    - bcrypt 比对

- **JWT 配置常量**:
  - `SECRET_KEY`: 从环境变量 `JWT_SECRET_KEY` 读取，若未设置则随机生成 32 字节（启动时 logger 输出）
  - `ALGORITHM`: `"HS256"`
  - `ACCESS_TOKEN_EXPIRE_SECONDS`: `86400`（24 小时，PM 决策 D7）

- **依赖模块**: MOD-WEB-003 DatabaseManager（users 表查询）

- **外部依赖**: python-jose (jwt), passlib[bcrypt]

---

### MOD-WEB-003: DatabaseManager

- **职责**: SQLAlchemy 核心基础设施——创建 engine、管理 session factory、定义 declarative Base、配置 Alembic 迁移环境。包含全部 11 个 ORM Model 的声明式定义（按领域拆分 6 个文件）。
- **覆盖需求**: PM 决策 D2（SQLite + SQLAlchemy ORM）
- **关联用户故事**: 全部 Web UI 故事（数据持久化基础）

- **公开接口契约**:
  - **IFC-WEB-003-01**: `create_engine(db_path: str = "./data/webui.db") → Engine`
    - SQLite engine，配置：`connect_args={"check_same_thread": False}`、WAL 模式 pragma、外键约束启用

  - **IFC-WEB-003-02**: `get_session_factory(engine: Engine) → sessionmaker`
    - 返回配置好的 sessionmaker（`autocommit=False`, `autoflush=False`）

  - **IFC-WEB-003-03**: `init_db(engine: Engine) → None`
    - 调用 `Base.metadata.create_all(engine)` 自动建表（开发阶段）
    - 若启用 Alembic，则改为运行迁移脚本而非 create_all

  - **IFC-WEB-003-04**: `get_db() → Generator[Session, None, None]`
    - FastAPI `Depends` 使用的生成器，yield session 并在 finally 中 close

- **SQLAlchemy 配置参数**:
  - 数据库文件路径: `./data/webui.db`（与 Chroma 的 `./data/chroma_db/` 路径隔离）
  - SQLite pragma: `PRAGMA journal_mode=WAL`（提升并发读性能）、`PRAGMA foreign_keys=ON`（启用外键约束）
  - 连接池: 单进程 Demo 使用 `NullPool` 或 `StaticPool`（SQLite 不支持连接池并发写）

- **Model 文件拆分结构**:
  ```
  src/database/
    __init__.py         # 统一导出所有 Model + Base + get_db
    base.py             # Base = declarative_base(), TimestampMixin
    auth_models.py      # User
    alert_models.py     # Alert, AlertTimeline
    approval_models.py  # Approval
    device_models.py    # Device, DeviceCredential
    inspection_models.py # InspectionRecord
    kb_models.py        # KnowledgeDocument, CommandTemplate
    config_models.py    # SystemConfig, AuditLog
  ```

- **依赖模块**: 无（基础设施层最底层）

- **外部依赖**: SQLAlchemy, Alembic（可选：开发阶段可用 `Base.metadata.create_all()` 替代）

---

### MOD-WEB-003 (续): 数据模型详细设计 — 11 个 SQLAlchemy Model

#### 1. User（users 表）
| 字段 | SQLAlchemy 类型 | 约束 | 说明 |
|------|----------------|------|------|
| `id` | Integer | PK, autoincrement | 自增主键 |
| `username` | String(50) | UNIQUE, NOT NULL, INDEX | 用户名（Demo 仅 `admin`） |
| `password_hash` | String(128) | NOT NULL | bcrypt 哈希值（`$2b$12$...`） |
| `created_at` | DateTime | NOT NULL, default=utcnow | 创建时间 |
| `updated_at` | DateTime | NOT NULL, default=utcnow, onupdate=utcnow | 更新时间 |

#### 2. Alert（alerts 表）
| 字段 | SQLAlchemy 类型 | 约束 | 说明 |
|------|----------------|------|------|
| `id` | Integer | PK, autoincrement | 自增主键 |
| `alert_id` | String(36) | UNIQUE, NOT NULL, INDEX | UUID 格式的告警唯一标识 |
| `alert_type` | String(20) | NOT NULL, INDEX | MAC_FLAPPING / PORT_DOWN / CPU_HIGH |
| `severity` | String(10) | NOT NULL | CRITICAL / MAJOR / MINOR / WARNING |
| `content` | Text | NOT NULL | 告警描述文本 |
| `device_info` | JSON | NOT NULL | 设备信息 JSON（device_name, device_ip, device_model, interface_name, mac_address, cpu_percent） |
| `source` | String(15) | NOT NULL, INDEX | WEBHOOK / INSPECTION / MOCK |
| `status` | String(15) | NOT NULL, INDEX, default='PROCESSING' | PROCESSING / CLOSED / FAILED / REJECTED |
| `created_at` | DateTime | NOT NULL, default=utcnow, INDEX | 告警发生时间 |
| `updated_at` | DateTime | NOT NULL, default=utcnow, onupdate=utcnow | 最后更新时间 |
| **关系** | `timeline: list[AlertTimeline]` | back_populates="alert" | 一对多：告警 → 时间线 |
| **关系** | `approvals: list[Approval]` | back_populates="alert" | 一对多：告警 → 审批记录 |

#### 3. AlertTimeline（alert_timeline 表）
| 字段 | SQLAlchemy 类型 | 约束 | 说明 |
|------|----------------|------|------|
| `id` | Integer | PK, autoincrement | 自增主键 |
| `alert_id_fk` | String(36) | FK(→alerts.alert_id), NOT NULL, INDEX | 关联告警 |
| `node_name` | String(50) | NOT NULL | 节点名称（如 `collect_diag`, `human_approval`） |
| `state_snapshot` | JSON | NOT NULL | 节点执行时的 NetworkAgentState 快照 |
| `started_at` | DateTime | NOT NULL | 节点开始执行时间 |
| `completed_at` | DateTime | NULLABLE | 节点完成时间（进行中为 NULL） |
| `status` | String(15) | NOT NULL, default='RUNNING' | RUNNING / COMPLETED / FAILED |
| **关系** | `alert: Alert` | back_populates="timeline" | 多对一：时间线 → 告警 |

#### 4. Approval（approvals 表）
| 字段 | SQLAlchemy 类型 | 约束 | 说明 |
|------|----------------|------|------|
| `id` | Integer | PK, autoincrement | 自增主键 |
| `alert_id_fk` | String(36) | FK(→alerts.alert_id), NOT NULL, INDEX | 关联告警 |
| `checkpoint_id` | String(64) | UNIQUE, NOT NULL | LangGraph Interrupt checkpoint ID |
| `fix_plan` | JSON | NOT NULL | 修复方案完整内容（template_id, params, commands, risk_hints） |
| `risk_level` | String(10) | NOT NULL | LOW / MEDIUM / HIGH / CRITICAL |
| `decision` | String(10) | NULLABLE, INDEX | PENDING / APPROVED / REJECTED |
| `decided_by` | String(50) | NULLABLE | 审批人（Demo 固定为 admin） |
| `decided_at` | DateTime | NULLABLE | 审批时间 |
| `note` | Text | NULLABLE | 审批备注（拒绝原因等） |
| `created_at` | DateTime | NOT NULL, default=utcnow | 审批挂起时间 |
| **关系** | `alert: Alert` | back_populates="approvals" | 多对一：审批 → 告警 |

**索引**: 复合索引 `(alert_id_fk, decision)` 用于待审批列表和审批历史查询。

#### 5. Device（devices 表）
| 字段 | SQLAlchemy 类型 | 约束 | 说明 |
|------|----------------|------|------|
| `id` | Integer | PK, autoincrement | 自增主键 |
| `device_name` | String(50) | UNIQUE, NOT NULL, INDEX | 设备名称（如 Core-SW-01） |
| `device_ip` | String(15) | NOT NULL | IPv4 地址 |
| `device_model` | String(50) | NULLABLE | 设备型号（如 TP-Link T2600G-28TS） |
| `group_name` | String(50) | NULLABLE | 所属分组（Demo 可选） |
| `status` | String(15) | NULLABLE, default='UNKNOWN' | ONLINE / OFFLINE / UNKNOWN |
| `last_diag_at` | DateTime | NULLABLE | 最近一次诊断时间 |
| `created_at` | DateTime | NOT NULL, default=utcnow | 纳管时间 |
| `updated_at` | DateTime | NOT NULL, default=utcnow, onupdate=utcnow | 最后更新时间 |
| **关系** | `credential: DeviceCredential` | back_populates="device", uselist=False | 一对一：设备 → 凭据 |

#### 6. DeviceCredential（device_credentials 表）
| 字段 | SQLAlchemy 类型 | 约束 | 说明 |
|------|----------------|------|------|
| `id` | Integer | PK, autoincrement | 自增主键 |
| `device_id` | Integer | FK(→devices.id), UNIQUE, NOT NULL | 关联设备（一对一） |
| `ssh_username` | String(50) | NOT NULL | SSH 用户名 |
| `ssh_password_encrypted` | String(512) | NOT NULL | AES 加密后的密码（Fernet token） |
| `ssh_port` | Integer | NOT NULL, default=22 | SSH 端口 |
| `created_at` | DateTime | NOT NULL, default=utcnow | 凭据配置时间 |
| `updated_at` | DateTime | NOT NULL, default=utcnow, onupdate=utcnow | 最后更新时间 |
| **关系** | `device: Device` | back_populates="credential" | 一对一：凭据 → 设备 |

**安全约束**: `ssh_password_encrypted` 字段在 API 响应中始终返回 `"****"` 掩码，永远不返回密文（防止离线暴力破解 Fernet token）。

#### 7. InspectionRecord（inspection_records 表）
| 字段 | SQLAlchemy 类型 | 约束 | 说明 |
|------|----------------|------|------|
| `id` | Integer | PK, autoincrement | 自增主键 |
| `trigger_mode` | String(15) | NOT NULL, INDEX | SCHEDULED / MANUAL |
| `started_at` | DateTime | NOT NULL | 巡检开始时间 |
| `completed_at` | DateTime | NULLABLE | 巡检完成时间 |
| `total_devices` | Integer | NOT NULL | 检查设备总数 |
| `anomaly_count` | Integer | NOT NULL, default=0 | 发现异常数 |
| `details` | JSON | NOT NULL | 巡检详情（每台设备的诊断结果和告警信息） |
| **索引** | `(trigger_mode, started_at)` | 复合索引 | 按触发方式和时间筛选 |

#### 8. KnowledgeDocument（knowledge_documents 表）
| 字段 | SQLAlchemy 类型 | 约束 | 说明 |
|------|----------------|------|------|
| `id` | Integer | PK, autoincrement | 自增主键 |
| `title` | String(200) | NOT NULL | 文档标题 |
| `alert_type` | String(20) | NOT NULL, INDEX | 告警类型分类（MAC_FLAPPING / PORT_DOWN / CPU_HIGH） |
| `content` | Text | NOT NULL | 文档内容（Markdown 格式） |
| `embedding_id` | String(64) | NULLABLE | Chroma 中的 embedding 文档 ID（用于同步删除） |
| `created_at` | DateTime | NOT NULL, default=utcnow | 创建时间 |
| `updated_at` | DateTime | NOT NULL, default=utcnow, onupdate=utcnow | 更新时间 |

#### 9. CommandTemplate（command_templates 表）
| 字段 | SQLAlchemy 类型 | 约束 | 说明 |
|------|----------------|------|------|
| `id` | Integer | PK, autoincrement | 自增主键 |
| `name` | String(100) | NOT NULL, INDEX | 模板名称（如 "端口启用"） |
| `alert_type` | String(20) | NOT NULL, INDEX | 适用告警类型 |
| `yaml_content` | Text | NOT NULL | YAML 格式的模板内容（含 Jinja2 变量 `{{param}}`) |
| `parameters` | JSON | NOT NULL | 参数定义列表 `[{"name": "iface_name", "type": "string", "required": true}]` |
| `embedding_id` | String(64) | NULLABLE | Chroma 中的 embedding 模板 ID |
| `created_at` | DateTime | NOT NULL, default=utcnow | 创建时间 |
| `updated_at` | DateTime | NOT NULL, default=utcnow, onupdate=utcnow | 更新时间 |

#### 10. SystemConfig（system_config 表）
| 字段 | SQLAlchemy 类型 | 约束 | 说明 |
|------|----------------|------|------|
| `id` | Integer | PK, autoincrement | 自增主键 |
| `config_key` | String(100) | UNIQUE, NOT NULL, INDEX | 配置键（如 `inspection.interval_minutes`） |
| `config_value` | Text | NOT NULL | 配置值（所有值以字符串存储，使用时类型转换） |
| `updated_at` | DateTime | NOT NULL, default=utcnow, onupdate=utcnow | 最后更新时间 |

**预置配置项**:
| config_key | 默认值 | 说明 |
|-----------|--------|------|
| `inspection.interval_minutes` | `"5"` | 巡检间隔（分钟） |
| `diagnosis.timeout_seconds` | `"30"` | 诊断命令超时（秒） |
| `diagnosis.retry_max` | `"3"` | 命令重试上限 |
| `rag.similarity_threshold` | `"0.6"` | RAG 相似度阈值 |
| `ui.polling_interval_seconds` | `"3"` | 前端轮询间隔（秒） |
| `llm.api_key_encrypted` | — | DeepSeek API Key（加密存储，由 EncryptionService 管理） |

#### 11. AuditLog（audit_logs 表）
| 字段 | SQLAlchemy 类型 | 约束 | 说明 |
|------|----------------|------|------|
| `id` | Integer | PK, autoincrement | 自增主键 |
| `timestamp` | DateTime | NOT NULL, INDEX | 日志时间戳 |
| `level` | String(10) | NOT NULL, INDEX | INFO / WARNING / ERROR |
| `module` | String(50) | NOT NULL | 来源模块（如 `LLMService`, `StateGraphEngine`） |
| `message` | Text | NOT NULL | 日志消息内容 |
| `details` | JSON | NULLABLE | 附加详情 JSON |

**索引**: 复合索引 `(timestamp, level)` 用于按时间+级别筛选查询。

---

### MOD-WEB-004: DataAccessLayer

- **职责**: 封装 7 个 Repository 类，提供各数据实体对 SQLite 的 CRUD 操作。Repository 层隔离 API Router 与 SQLAlchemy ORM 细节，API Router 只调用 Repository 方法而不直接操作 Session。
- **覆盖需求**: REQ-WEBUI-FUNC-001, 002, 003, 007, 008, 009, 010, 011, 012, 013, 015, 016, 017, 019, 020, 021
- **关联用户故事**: US-WEBUI-001, 002, 004, 005, 006, 007, 008, 009, 010, 011, 013, 014, 015

- **7 个 Repository 及其核心接口**:

  - **AlertRepository**:
    - `list_alerts(filters: AlertFilter, page: int, page_size: int) → PaginatedResult[Alert]`
    - `get_alert_by_id(alert_id: str) → Alert | None`
    - `get_alert_timeline(alert_id: str) → list[AlertTimeline]`
    - `create_alert(alert_data: AlertCreate) → Alert`
    - `update_alert_status(alert_id: str, status: str) → Alert`
    - `append_timeline_entry(alert_id: str, entry: TimelineCreate) → AlertTimeline`

  - **ApprovalRepository**:
    - `list_pending_approvals() → list[Approval]`
    - `get_approval_by_checkpoint(checkpoint_id: str) → Approval | None`
    - `create_approval(approval_data: ApprovalCreate) → Approval`
    - `update_approval_decision(checkpoint_id: str, decision: str, decided_by: str, note: str) → Approval`
    - `list_approval_history(filters: ApprovalFilter, page: int, page_size: int) → PaginatedResult[Approval]`

  - **DeviceRepository**:
    - `list_devices() → list[Device]`
    - `get_device_by_id(device_id: int) → Device | None`
    - `create_device(device_data: DeviceCreate) → Device`
    - `update_device(device_id: int, device_data: DeviceUpdate) → Device`
    - `delete_device(device_id: int) → bool`（检查是否有进行中告警关联）
    - `get_device_active_alert_count(device_id: int) → int`
    - `upsert_credentials(device_id: int, cred_data: CredentialCreate) → DeviceCredential`
    - `get_device_diagnostics(device_id: int) → list[dict]`

  - **InspectionRepository**:
    - `get_config() → dict`（从 system_config 表读取巡检相关配置）
    - `update_config(config: InspectionConfig) → dict`
    - `create_record(record: InspectionRecordCreate) → InspectionRecord`
    - `update_record(record_id: int, updates: dict) → InspectionRecord`
    - `list_history(filters: InspectionFilter, page: int, page_size: int) → PaginatedResult[InspectionRecord]`

  - **KnowledgeRepository**:
    - `list_documents(alert_type: str | None, page: int, page_size: int) → PaginatedResult[KnowledgeDocument]`
    - `get_document(doc_id: int) → KnowledgeDocument | None`
    - `create_document(doc: KnowledgeDocumentCreate) → KnowledgeDocument`
    - `update_document(doc_id: int, doc: KnowledgeDocumentUpdate) → KnowledgeDocument`
    - `delete_document(doc_id: int) → bool`
    - `list_templates(alert_type: str | None) → list[CommandTemplate]`
    - `get_template(template_id: int) → CommandTemplate | None`
    - `create_template(template: TemplateCreate) → CommandTemplate`
    - `update_template(template_id: int, template: TemplateUpdate) → CommandTemplate`
    - `delete_template(template_id: int) → bool`

  - **ConfigRepository**:
    - `get_all_configs() → list[SystemConfig]`
    - `get_config(key: str) → SystemConfig | None`
    - `upsert_config(key: str, value: str) → SystemConfig`
    - `get_llm_api_key_encrypted() → str | None`
    - `set_llm_api_key_encrypted(encrypted_token: str) → None`

  - **AuditLogRepository**:
    - `create_log(entry: AuditLogCreate) → AuditLog`
    - `search_logs(filters: LogFilter, page: int, page_size: int) → PaginatedResult[AuditLog]`

- **依赖模块**: MOD-WEB-003 DatabaseManager（Session 注入）

- **外部依赖**: SQLAlchemy

---

### MOD-WEB-005: EncryptionService

- **职责**: 使用 `cryptography.fernet` 提供对称加密/解密服务，管理加密密钥生命周期。负责 API Key 和设备凭据密码的加密存储和解密使用。
- **覆盖需求**: REQ-WEBUI-NFUNC-005, REQ-WEBUI-FUNC-011, REQ-WEBUI-FUNC-020
- **关联用户故事**: US-WEBUI-007, US-WEBUI-014

- **公开接口契约**:
  - **IFC-WEB-005-01**: `initialize() → None`
    - 从环境变量 `ENCRYPTION_KEY` 加载密钥 → 若未设置，从文件 `./data/.encryption_key` 加载 → 若文件也不存在，生成新密钥写入文件
    - 初始化 Fernet 实例

  - **IFC-WEB-005-02**: `encrypt(plaintext: str) → str`
    - 输入: 明文字符串
    - 输出: Fernet token（Base64 编码的加密数据）
    - 对空字符串返回空字符串（不加密）

  - **IFC-WEB-005-03**: `decrypt(token: str) → str`
    - 输入: Fernet token
    - 输出: 明文原始字符串
    - 若 token 为空字符串，返回空字符串

  - **IFC-WEB-005-04**: `mask_sensitive(value: str, visible_prefix: int = 4, visible_suffix: int = 4) → str`
    - 输入: 敏感字符串（如 API Key `sk-abc123def456`）
    - 输出: 掩码字符串（如 `sk-a****f456`）

  - **IFC-WEB-005-05**: `get_key_status() → str`
    - 返回密钥状态: `"ENV"`（从环境变量加载）、`"FILE"`（从文件加载）、`"GENERATED"`（新生成）

- **依赖模块**: 无（独立安全组件）

- **外部依赖**: cryptography (fernet)

---

### MOD-WEB-006: DashboardService

- **职责**: Dashboard 聚合统计查询服务。从 SQLite 数据库中查询告警统计数据、修复成功率趋势、系统健康指标，返回结构化数据供 dashboard_router 使用。
- **覆盖需求**: REQ-WEBUI-FUNC-022, REQ-WEBUI-FUNC-023, REQ-WEBUI-FUNC-024
- **关联用户故事**: US-WEBUI-016

- **公开接口契约**:
  - **IFC-WEB-006-01**: `get_alert_stats(time_from: datetime | None, time_to: datetime | None) → AlertStats`
    - 返回告警统计数据（用于图表渲染）:
      - `by_type`: `[{"type": "PORT_DOWN", "count": 25}, ...]`（饼图数据）
      - `by_severity`: `[{"severity": "MAJOR", "count": 30}, ...]`（柱状图数据）
      - `trend`: `[{"date": "2026-07-01", "count": 5}, ...]`（折线图数据，按天聚合）
      - `total_count`: int, `today_count`: int, `pending_approval_count`: int, `fix_success_rate`: float

  - **IFC-WEB-006-02**: `get_fix_success_rate(time_from: datetime | None, time_to: datetime | None) → FixRateStats`
    - 返回修复成功率:
      - `closed_count`: int（修复成功）
      - `failed_count`: int（修复失败）
      - `rejected_count`: int（审批拒绝）
      - `total_count`: int

  - **IFC-WEB-006-03**: `get_health_status() → HealthStatus`
    - 返回系统健康状态:
      - `langgraph`: `{"status": "healthy", "detail": "14 nodes compiled"}`
      - `rag`: `{"status": "healthy", "detail": "Chroma OK, 10 documents"}`
      - `scheduler`: `{"status": "healthy", "detail": "Running, interval=5min"}`
      - `llm`: `{"status": "healthy", "detail": "DeepSeek API reachable"}` 或 `{"status": "error", "detail": "401 Unauthorized"}`
    - LLM 连接测试: 向 DeepSeek API 发起一次轻量级调用（如 models list API），成功则 "healthy"，失败则 "error"

- **依赖模块**: MOD-WEB-004 DataAccessLayer（AlertRepository 聚合查询）

- **外部依赖**: 无

---

### MOD-WEB-007: LogReaderService

- **职责**: 读取文件系统上的 `operations.log` 和 `audit.log` 日志文件，支持按级别、关键词、时间范围过滤和分页返回。Demo 阶段读取文件日志。
- **覆盖需求**: REQ-WEBUI-FUNC-021
- **关联用户故事**: US-WEBUI-015

- **公开接口契约**:
  - **IFC-WEB-007-01**: `read_logs(source: str, level: str | None, keyword: str | None, time_from: datetime | None, time_to: datetime | None, page: int, page_size: int) → PaginatedLogResult`
    - 输入: source = `"operations"` | `"audit"`; 过滤条件; 分页参数
    - 输出: `PaginatedLogResult { entries: list[LogEntry], total: int, page: int, page_size: int }`
    - `LogEntry { timestamp: datetime, level: str, module: str, message: str, details: dict | None }`
    - 关键词搜索: 对 `message` 字段做子串匹配（不区分大小写）
    - 大文件优化: 从文件尾部倒序读取（`seek` + 反向读取），只解析需要的页数；单次最多返回 500 条

  - **IFC-WEB-007-02**: `get_log_sources() → list[str]`
    - 返回可用的日志源列表: `["operations", "audit"]`

- **日志文件路径**:
  - 操作日志: `./logs/operations_{date}.log`（loguru 按日期轮转）
  - 审计日志: `./logs/audit.log`

- **依赖模块**: 无

- **外部依赖**: 无（Python stdlib `os`, `re`, `datetime`）

---

## 前端模块详情

---

### MOD-WEB-F01: AppShell（布局组件）

- **职责**: 提供 Web 界面的全局布局框架——左侧固定侧边栏导航、顶部 Header（含用户信息和退出按钮）、页面顶部面包屑导航、中央 `<router-view>` 内容区。
- **覆盖需求**: REQ-WEBUI-FUNC-027, REQ-WEBUI-FUNC-028, REQ-WEBUI-NFUNC-007, REQ-WEBUI-NFUNC-008
- **关联用户故事**: US-WEBUI-017, US-WEBUI-018

- **组件结构**:
  ```
  AppShell.vue
  ├── SidebarNav.vue        # 侧边栏导航菜单（8 个功能模块 + 徽标）
  │   ├── 菜单项: Dashboard / 告警管理 / 工作流可视化 / 审批管理(子菜单: 待审批/审批历史)
  │   │         设备管理 / 巡检配置 / 知识库管理(子菜单: 文档/模板) / 系统配置(子菜单: 全局配置/日志)
  │   └── 审批徽标: 从 ApprovalsStore 获取 pending_count
  ├── AppHeader.vue         # 顶部 Header
  │   ├── 折叠按钮（侧边栏展开/折叠切换）
  │   ├── 面包屑: BreadcrumbNav.vue
  │   └── 用户区: 当前用户名 "admin" + "退出登录" 按钮
  └── <router-view />       # 内容区（Element Plus el-main）
  ```

- **侧边栏规格**:
  - 展开宽度: 220px（满足 REQ-WEBUI-NFUNC-007 桌面端布局要求）
  - 折叠宽度: 64px（仅显示图标）
  - 使用 Element Plus `el-menu` 组件，`router` 模式（菜单 index 对应路由 path）
  - 待审批 Badge: `el-badge` 组件，数据绑定 `approvalsStore.pendingCount`

- **依赖模块**: MOD-WEB-F02 (Router), MOD-WEB-F04 (AuthStore), MOD-WEB-F06 (ApprovalsStore)

---

### MOD-WEB-F02: Router（路由配置）

- **职责**: Vue Router 路由表定义，包含全局前置守卫（`beforeEach`）实现未登录拦截和 Token 过期跳转。
- **覆盖需求**: REQ-WEBUI-FUNC-025 AC-W025-04, REQ-WEBUI-FUNC-027, REQ-WEBUI-NFUNC-003 AC-WNF-003-01
- **关联用户故事**: US-WEBUI-017, US-WEBUI-018

- **路由表设计**:

| 路径 | 组件 | 元数据 | 说明 |
|------|------|--------|------|
| `/login` | LoginView | `{ requiresAuth: false }` | 登录页，独立布局 |
| `/` | AppShell (redirect `/dashboard`) | `{ requiresAuth: true }` | 根路径重定向 |
| `/dashboard` | DashboardView | `{ requiresAuth: true, title: "Dashboard" }` | 仪表盘 |
| `/alerts` | AlertsListView | `{ requiresAuth: true, title: "告警管理" }` | 告警列表 |
| `/alerts/simulate` | AlertsSimulateView | `{ requiresAuth: true, title: "模拟告警" }` | 模拟告警 |
| `/alerts/:alertId` | AlertsDetailView | `{ requiresAuth: true, title: "告警详情" }` | 告警详情 + 工作流视图 |
| `/workflow` | WorkflowGraphView | `{ requiresAuth: true, title: "工作流可视化" }` | 全局拓扑图 |
| `/approvals/pending` | ApprovalsPendingView | `{ requiresAuth: true, title: "待审批" }` | 待审批列表 |
| `/approvals/:checkpointId` | ApprovalsDetailView | `{ requiresAuth: true, title: "审批详情" }` | 审批详情页 |
| `/approvals/history` | ApprovalsHistoryView | `{ requiresAuth: true, title: "审批历史" }` | 审批历史 |
| `/devices` | DevicesListView | `{ requiresAuth: true, title: "设备管理" }` | 设备列表 |
| `/inspection` | InspectionConfigView | `{ requiresAuth: true, title: "巡检配置" }` | 巡检配置 |
| `/inspection/history` | InspectionHistoryView | `{ requiresAuth: true, title: "巡检历史" }` | 巡检历史 |
| `/knowledge/documents` | KnowledgeDocumentsView | `{ requiresAuth: true, title: "知识文档" }` | 知识文档管理 |
| `/knowledge/templates` | KnowledgeTemplatesView | `{ requiresAuth: true, title: "命令模板" }` | 命令模板管理 |
| `/knowledge/test-retrieval` | KnowledgeTestRetrievalView | `{ requiresAuth: true, title: "检索测试" }` | RAG 检索测试 |
| `/system/config` | SystemConfigView | `{ requiresAuth: true, title: "系统配置" }` | 全局配置 |
| `/system/logs` | SystemLogsView | `{ requiresAuth: true, title: "系统日志" }` | 日志查看 |

- **全局前置守卫逻辑**:
  ```
  router.beforeEach((to, from, next) => {
    const authStore = useAuthStore()
    if (to.meta.requiresAuth && !authStore.isAuthenticated) {
      next('/login')  // 未登录拦截
    } else if (to.path === '/login' && authStore.isAuthenticated) {
      next('/dashboard')  // 已登录再访问 /login 自动跳转
    } else {
      next()
    }
  })
  ```

- **路由懒加载**: 所有页面组件使用 `() => import('@/views/...')` 动态导入，Vite 自动代码分割

- **依赖模块**: MOD-WEB-F01 (AppShell), MOD-WEB-F04 (AuthStore)

---

### MOD-WEB-F03: ApiClient（HTTP 客户端）

- **职责**: 封装 Axios 实例，提供统一的 HTTP 请求基础设施——Base URL 配置、JWT Token 自动注入、401 响应拦截与自动登出、统一错误处理。
- **覆盖需求**: REQ-WEBUI-FUNC-025, REQ-WEBUI-NFUNC-003, REQ-WEBUI-NFUNC-006
- **关联用户故事**: US-WEBUI-017

- **Axios 实例配置**:
  - `baseURL`: `/`（同源部署，无需绝对 URL）
  - `timeout`: `15000`（15 秒，覆盖最慢的 LLM 测试连接 API）
  - 请求拦截器: 从 Pinia AuthStore（或 localStorage）读取 token，注入 `Authorization: Bearer {token}`
  - 响应拦截器:
    - 2xx: 直接返回 `response.data`
    - 401: 清除 AuthStore token → 重定向 `/login?expired=true`
    - 其他错误: `ElMessage.error(response.data.detail || '请求失败')`

- **依赖模块**: MOD-WEB-F04 (AuthStore), MOD-WEB-F02 (Router)

- **外部依赖**: axios

---

### MOD-WEB-F04 ~ F11: Pinia Stores（状态管理）

#### AuthStore（MOD-WEB-F04）
- **State**: `token: string | null`, `user: { username: string } | null`
- **Getters**: `isAuthenticated: bool`
- **Actions**: `login(username, password)`, `logout()`, `checkAuth()`（页面刷新时从 localStorage 恢复 token）
- **持久化**: token 存储到 `localStorage`（Demo 阶段不使用 session cookie，支持页面刷新后保持登录）

#### AlertsStore（MOD-WEB-F05）
- **State**: `alertList: Alert[]`, `currentAlert: Alert | null`, `filters: AlertFilter`, `pagination`, `loading`
- **Actions**: `fetchAlerts()`, `fetchAlertDetail(alertId)`, `simulateAlert(data)`, `updateFilters(filters)`

#### ApprovalsStore（MOD-WEB-F06）
- **State**: `pendingList: Approval[]`, `pendingCount: number`, `historyList: Approval[]`, `currentApproval: Approval | null`
- **Actions**: `fetchPendingApprovals()`, `fetchApprovalDetail(checkpointId)`, `submitDecision(checkpointId, decision, note)`, `fetchHistory(filters)`

#### DevicesStore（MOD-WEB-F07）
- **State**: `deviceList: Device[]`, `currentDevice: Device | null`
- **Actions**: `fetchDevices()`, `createDevice(data)`, `updateDevice(id, data)`, `deleteDevice(id)`, `configureCredentials(deviceId, credData)`, `fetchDiagnostics(deviceId)`

#### InspectionStore（MOD-WEB-F08）
- **State**: `config: InspectionConfig`, `historyList: InspectionRecord[]`, `inspectionRunning: boolean`
- **Actions**: `fetchConfig()`, `updateConfig(data)`, `triggerInspection()`, `fetchHistory(filters)`

#### KnowledgeStore（MOD-WEB-F09）
- **State**: `documentList: KnowledgeDocument[]`, `templateList: CommandTemplate[]`, `retrievalResults: RetrievalResult[]`
- **Actions**: `fetchDocuments(alertType?)`, `createDocument(data)`, `updateDocument(id, data)`, `deleteDocument(id)`, `fetchTemplates(alertType?)`, `createTemplate(data)`, `updateTemplate(id, data)`, `deleteTemplate(id)`, `testRetrieval(query, alertType?, topK)`

#### SystemStore（MOD-WEB-F10）
- **State**: `configs: SystemConfig[]`, `logEntries: LogEntry[]`, `apiKeyConfigured: boolean`
- **Actions**: `fetchConfigs()`, `updateConfigs(data)`, `updateApiKey(key)`, `testLlmConnection()`, `fetchLogs(filters)`

#### DashboardStore（MOD-WEB-F11）
- **State**: `alertStats: AlertStats | null`, `fixRate: FixRateStats | null`, `healthStatus: HealthStatus | null`, `loading: boolean`
- **Actions**: `fetchStats(timeRange?)`, `fetchFixRate(timeRange?)`, `fetchHealthStatus()`
- **轮询**: `fetchHealthStatus()` 每 3 秒自动调用（通过 `setInterval` 在 DashboardView `onMounted` 中启动，`onUnmounted` 中清除）

---

### MOD-WEB-F12 ~ F20: 页面视图组件（Views）

每个 View 组件的职责、对应的 API 调用、包含的主要 Element Plus 组件如下：

| View 组件 | 主要 Element Plus 组件 | 对应的 API 调用 |
|-----------|----------------------|----------------|
| **DashboardView** | el-card, el-row/el-col, v-chart (ECharts), el-tag (健康指示灯) | GET /api/dashboard/stats, GET /api/dashboard/health |
| **AlertsListView** | el-table, el-pagination, el-select (筛选), el-date-picker | GET /api/alerts |
| **AlertsDetailView** | el-timeline, el-descriptions, el-tabs (详情/工作流视图) | GET /api/alerts/{id}, GET /api/alerts/{id}/workflow |
| **AlertsSimulateView** | el-form, el-select, el-input, el-button | POST /api/alerts/simulate |
| **WorkflowGraphView** | v-chart (ECharts graph 类型), el-drawer (State 快照) | GET /api/workflow/graph |
| **ApprovalsPendingView** | el-table, el-badge, el-tag (风险等级) | GET /api/approvals/pending |
| **ApprovalsDetailView** | el-descriptions, el-button (批准/拒绝), el-dialog (二次确认), el-input (备注) | GET /api/approvals/pending, POST /api/approvals/{id}/decide |
| **ApprovalsHistoryView** | el-table, el-pagination, el-select (筛选) | GET /api/approvals/history |
| **DevicesListView** | el-table, el-button (新增/编辑/删除), el-dialog (表单弹窗) | CRUD /api/devices |
| **DeviceCredentialsDialog** | el-dialog, el-form, el-input (密码 type=password, show-password) | PUT /api/devices/{id}/credentials |
| **InspectionConfigView** | el-form, el-input-number, el-button (手动触发), el-tag (状态) | GET/PUT /api/inspection/config, POST /api/inspection/trigger |
| **InspectionHistoryView** | el-table, el-pagination, el-tag (触发方式) | GET /api/inspection/history |
| **KnowledgeDocumentsView** | el-table, el-button (新增/编辑/删除), el-dialog (Markdown 编辑器) | CRUD /api/knowledge/documents |
| **KnowledgeTemplatesView** | el-table, el-dialog (YAML 编辑器 + 语法校验) | CRUD /api/knowledge/templates |
| **KnowledgeTestRetrievalView** | el-input (查询文本), el-select (告警类型), el-table (结果), el-progress (相似度可视化) | POST /api/knowledge/test-retrieval |
| **SystemConfigView** | el-form, el-input-number, el-input (password for API Key), el-button (测试连接) | GET/PUT /api/system/config, PUT /api/system/config/llm-api-key, POST /api/system/config/llm-test |
| **SystemLogsView** | el-table, el-pagination, el-select (级别筛选), el-input (关键词搜索) | GET /api/system/logs |
| **LoginView** | el-card, el-form, el-input (用户名/密码), el-button, el-alert (错误提示) | POST /auth/login |

**密码显示/隐藏**: 所有密码输入框使用 Element Plus `el-input` 的 `show-password` 属性，提供眼睛图标的显示/隐藏切换按钮（满足 PM 决策 D8）。

**图表渲染**: DashboardView 中所有图表使用 ECharts 5.x，通过 `vue-echarts` 包装组件或直接使用 `echarts.init()`。饼图（告警类型分布）、柱状图（严重级别）、折线图（时间趋势）、环形图（修复成功率）均使用 ECharts 原生图表类型。

---

## API 端点与模块的映射关系

| API 端点组 | HTTP 方法 + 路径 | 处理 Router | 委托 Service | 数据源（Repository） |
|-----------|-----------------|------------|-------------|---------------------|
| **认证** | POST /auth/login | auth_router | AuthService | User (read) |
| **认证** | POST /auth/logout | auth_router | — (前端清除) | — |
| **告警** | GET /api/alerts | alerts_router | — | AlertRepository.list_alerts() |
| **告警** | GET /api/alerts/{id} | alerts_router | — | AlertRepository.get_alert_by_id() |
| **告警** | GET /api/alerts/{id}/workflow | alerts_router | StateGraphEngine.get_workflow_state() | AlertTimeline (read) |
| **告警** | POST /api/alerts/simulate | alerts_router | AlertNormalizer + StateGraphEngine | AlertRepository.create_alert() |
| **工作流** | GET /api/workflow/graph | workflow_router | StateGraphEngine.build_graph() | — |
| **工作流** | GET /api/workflow/{id}/nodes/{name} | workflow_router | StateGraphEngine.get_workflow_state() | — |
| **工作流** | GET /api/workflow/{id}/state | workflow_router | StateGraphEngine.get_workflow_state() | — |
| **审批** | GET /api/approvals/pending | approvals_router | StateGraphEngine.get_pending_approvals() | ApprovalRepository.list_pending() |
| **审批** | POST /api/approvals/{id}/decide | approvals_router | StateGraphEngine.resume_workflow() | ApprovalRepository.update_decision() |
| **审批** | GET /api/approvals/history | approvals_router | — | ApprovalRepository.list_history() |
| **设备** | GET /api/devices | devices_router | — | DeviceRepository.list_devices() |
| **设备** | POST /api/devices | devices_router | — | DeviceRepository.create_device() |
| **设备** | GET /api/devices/{id} | devices_router | — | DeviceRepository.get_device_by_id() |
| **设备** | PUT /api/devices/{id} | devices_router | — | DeviceRepository.update_device() |
| **设备** | DELETE /api/devices/{id} | devices_router | — | DeviceRepository.delete_device() |
| **设备凭据** | PUT /api/devices/{id}/credentials | devices_router | EncryptionService | DeviceRepository.upsert_credentials() |
| **设备诊断** | GET /api/devices/{id}/diagnostics | devices_router | — | DeviceRepository.get_device_diagnostics() |
| **巡检** | GET /api/inspection/config | inspection_router | — | InspectionRepository.get_config() |
| **巡检** | PUT /api/inspection/config | inspection_router | InspectionScheduler.reschedule() | InspectionRepository.update_config() |
| **巡检** | POST /api/inspection/trigger | inspection_router | InspectionScheduler.run_inspection_once() | InspectionRepository.create_record() |
| **巡检** | GET /api/inspection/history | inspection_router | — | InspectionRepository.list_history() |
| **知识库文档** | CRUD /api/knowledge/documents | kb_router | RAGService.reindex() | KnowledgeRepository (document CRUD) |
| **知识库模板** | CRUD /api/knowledge/templates | kb_router | TemplateEngine.reload() + RAGService.reindex() | KnowledgeRepository (template CRUD) |
| **检索测试** | POST /api/knowledge/test-retrieval | kb_router | RAGService.search() | — |
| **系统配置** | GET /api/system/config | config_router | — | ConfigRepository.get_all_configs() |
| **系统配置** | PUT /api/system/config | config_router | 各服务热重载 | ConfigRepository.upsert_config() |
| **API Key** | PUT /api/system/config/llm-api-key | config_router | EncryptionService + LLMService.update_key() | ConfigRepository.set_llm_api_key_encrypted() |
| **LLM 测试** | POST /api/system/config/llm-test | config_router | LLMService.test_connection() | — |
| **日志** | GET /api/system/logs | config_router | LogReaderService.read_logs() | — (文件系统) |
| **Dashboard** | GET /api/dashboard/stats | dashboard_router | DashboardService | AlertRepository + SystemConfig |
| **Dashboard** | GET /api/dashboard/health | dashboard_router | DashboardService | 各组件实时状态检查 |

---

## 依赖关系图（文本格式）

### 后端模块依赖

```
# Web 表现层内部
MOD-WEB-001 (APIRouterLayer) ──→ MOD-WEB-002 (AuthService)       [IFC-WEB-002-01/02]
MOD-WEB-001 (APIRouterLayer) ──→ MOD-WEB-003 (DatabaseManager)   [IFC-WEB-003-04: get_db]
MOD-WEB-001 (APIRouterLayer) ──→ MOD-WEB-004 (DataAccessLayer)   [各 Repository 接口]
MOD-WEB-001 (APIRouterLayer) ──→ MOD-WEB-005 (EncryptionService) [IFC-WEB-005-02/03]
MOD-WEB-001 (APIRouterLayer) ──→ MOD-WEB-006 (DashboardService)  [IFC-WEB-006-01/02/03]
MOD-WEB-001 (APIRouterLayer) ──→ MOD-WEB-007 (LogReaderService)  [IFC-WEB-007-01]

# Web 表现层 → 现有系统
MOD-WEB-001 (APIRouterLayer) ──→ MOD-002 (InspectionScheduler)   [trigger inspection]
MOD-WEB-001 (APIRouterLayer) ──→ MOD-003 (StateGraphEngine)      [workflow state]
MOD-WEB-001 (APIRouterLayer) ──→ MOD-004 (AlertNormalizer)       [alert creation]
MOD-WEB-001 (APIRouterLayer) ──→ MOD-006 (LLMService)            [test connection]
MOD-WEB-001 (APIRouterLayer) ──→ MOD-008 (RAGService)            [reindex, test retrieval]

# 认证服务
MOD-WEB-002 (AuthService) ──→ MOD-WEB-003 (DatabaseManager)      [User table query]

# 数据访问层
MOD-WEB-004 (DataAccessLayer) ──→ MOD-WEB-003 (DatabaseManager)  [Session 注入]

# Dashboard 服务
MOD-WEB-006 (DashboardService) ──→ MOD-WEB-004 (DataAccessLayer) [AlertRepository]

# 基础设施层（无依赖）
MOD-WEB-003 (DatabaseManager) ──→ (无依赖，最底层)
MOD-WEB-005 (EncryptionService) ──→ (无依赖，独立安全组件)
MOD-WEB-007 (LogReaderService) ──→ (无依赖，文件系统)

# 现有模块增强
MOD-002 (InspectionScheduler) ──→ MOD-WEB-004 (DataAccessLayer)  [DeviceRepository 动态加载设备列表]
MOD-004 (AlertNormalizer) ──→ MOD-WEB-004 (DataAccessLayer)      [AlertRepository 持久化 Alert]
MOD-005 (NodeHandlers) ──→ MOD-WEB-004 (DataAccessLayer)         [AlertTimeline/Approval 持久化]
MOD-006 (LLMService) ──→ MOD-WEB-005 (EncryptionService)         [解密 API Key]

# ─── 验证：无循环依赖 ───
# 所有数据流从 Web 表现层 → 现有业务层 → 数据持久化层，单向流动。
# MOD-WEB-003 为最底层基础设施，不依赖任何其他模块。
# 现有模块对 MOD-WEB-004/005 的依赖是新增的向下依赖，不产生环。
```

### 前端模块依赖

```
# 布局
MOD-WEB-F01 (AppShell) ──→ MOD-WEB-F02 (Router)         [<router-view>]
MOD-WEB-F01 (AppShell) ──→ MOD-WEB-F04 (AuthStore)      [用户信息, 登出]
MOD-WEB-F01 (AppShell) ──→ MOD-WEB-F06 (ApprovalsStore) [待审批计数]

# 路由
MOD-WEB-F02 (Router) ──→ MOD-WEB-F04 (AuthStore)        [beforeEach 检查认证状态]

# HTTP 客户端
MOD-WEB-F03 (ApiClient) ──→ MOD-WEB-F04 (AuthStore)     [请求拦截器读取 token]

# Stores → ApiClient（所有 Store 通过 ApiClient 发起请求）
MOD-WEB-F04 (AuthStore) ──→ MOD-WEB-F03 (ApiClient)
MOD-WEB-F05 (AlertsStore) ──→ MOD-WEB-F03 (ApiClient)
MOD-WEB-F06 (ApprovalsStore) ──→ MOD-WEB-F03 (ApiClient)
MOD-WEB-F07 (DevicesStore) ──→ MOD-WEB-F03 (ApiClient)
MOD-WEB-F08 (InspectionStore) ──→ MOD-WEB-F03 (ApiClient)
MOD-WEB-F09 (KnowledgeStore) ──→ MOD-WEB-F03 (ApiClient)
MOD-WEB-F10 (SystemStore) ──→ MOD-WEB-F03 (ApiClient)
MOD-WEB-F11 (DashboardStore) ──→ MOD-WEB-F03 (ApiClient)

# Views → Stores（所有 View 从对应 Store 读取状态和调用 actions）
MOD-WEB-F12 ~ F20 (各 View) ──→ MOD-WEB-F04 ~ F11 (各 Store)

# ─── 验证：无循环依赖 ───
# 数据流：View → Store → ApiClient → Backend
# 所有依赖为单向：View 依赖 Store，Store 依赖 ApiClient，ApiClient 不依赖任何 Store（从 localStorage 降级读取 token）
```

---

## 现有模块改造影响最小化保证

| 改造点 | 影响范围 | 风险控制 |
|--------|---------|---------|
| `main.py` 新增 `app.include_router()` | 仅追加 2 行代码，原有 6 个端点函数体不变 | 可通过 git diff 验证——原代码零删除 |
| MOD-002 InspectionScheduler 设备列表来源变更 | `default_devices` 硬编码 → `DeviceRepository.list_devices()` 动态加载 | lifespan 启动时若 SQLite 中无设备，自动插入原有 2 台默认设备（Core-SW-01, Access-SW-02）作为种子数据，保证向后兼容 |
| MOD-004 AlertNormalizer 新增 SQLite 写入 | 在 `normalize_*()` 方法末尾追加 `AlertRepository.create_alert()` 调用 | 写入失败不阻塞工作流触发（catch log + 继续），告警数据异步补录 |
| MOD-005 NodeHandlers 各节点新增 timeline 写入 | 每个节点处理函数首尾追加 `AlertRepository.append_timeline_entry()` | 写入失败不阻塞节点继续执行 |
| MOD-006 LLMService API Key 来源优先级 | 1. EncryptionService 解密 SQLite 配置；2. 环境变量 `DEEPSEEK_API_KEY`（fallback） | 向后兼容——如果 SQLite 中无配置，回退到现有环境变量方式 |
| MOD-003 StateGraphEngine 审批数据增强 | `get_pending_approvals()` 返回结构从内存状态扩展为关联 SQLite approvals 表 | 现有调用方（`GET /approvals/pending`）的返回字段是兼容的超集，不破坏现有 API 契约 |
