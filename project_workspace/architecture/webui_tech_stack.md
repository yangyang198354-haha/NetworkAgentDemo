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
    <file>architecture/webui_module_design.md</file>
    <file>src/main.py</file>
  </input_files>
  <phase>PHASE_W04</phase>
  <status>APPROVED</status>
</file_header>

# Web 管理界面技术选型表 — NetworkAgentDemo

---

## 选型总述

本文档定义 NetworkAgentDemo Web 管理界面特性（PHASE_W04）引入的全部新增技术栈，分为三大类：
1. **前端技术栈**：Vue 3 SPA 生态（8 个 npm 依赖）
2. **后端新增依赖**：Python Web UI 所需的 6 个新 PyPI 包
3. **开发与生产环境配置**：Vite / FastAPI 的双模式运行方案

所有选型已与现有 `tech_stack.md` 中定义的技术栈做兼容性交叉检查，确保无版本冲突。

---

## 1. 前端技术栈

### 1.1 核心框架与构建工具

| 类别 | 选型 | 版本/版次 | Rationale | 关联 REQ-* | 风险 | 备注 |
|------|------|----------|-----------|-----------|------|------|
| 前端框架 | **Vue 3** | >= 3.4 (Composition API) | PM 决策 D3 明确要求 Vue 3；Composition API 提供更好的 TypeScript 支持和逻辑复用（composables）；`<script setup>` 语法糖降低模板代码量；Vue 3.4+ 的响应式系统性能优化（`shallowRef`、`triggerRef`）有利于 Dashboard 图表渲染 | PM 决策 D3; REQ-WEBUI-NFUNC-001 | 无（Vue 3 生态成熟稳定） | 使用 `create-vue` 脚手架初始化项目 |
| 构建工具 | **Vite** | >= 5.4 | PM 决策 D3 明确要求 Vite；ESBuild 原生打包，开发冷启动 < 1s；原生支持 Vue SFC、TypeScript、CSS Pre-processors；代码分割基于 Rollup，Tree Shaking 自动去除未使用代码；HMR 即时热更新 | PM 决策 D3; REQ-WEBUI-NFUNC-001 | Vite 6.x 可能引入 breaking changes（当前 5.x 稳定，锁定大版本） | Vite dev server 端口 5173（开发） |
| 状态管理 | **Pinia** | >= 2.1 | Vue 3 官方推荐的状态管理库（替代 Vuex）；TypeScript 原生支持；DevTools 集成；模块化 Store 设计天然支持 7 个 Store 的拆分（Auth/Alerts/Approvals/Devices/Inspection/Knowledge/System/Dashboard）；`$patch` 批量更新优化 Dashboard 轮询性能 | REQ-WEBUI-FUNC-001~024 | 无（Pinia 是 Vue 生态标准） | 不引入 Vuex（已进入维护模式） |
| 路由 | **Vue Router** | >= 4.3 | Vue 3 官方路由库；支持懒加载（`() => import()`）与 Vite 代码分割协同；`beforeEach` 全局前置守卫实现未登录拦截；嵌套路由支持侧边栏子菜单（审批管理/知识库管理） | REQ-WEBUI-FUNC-025 AC-W025-04; REQ-WEBUI-FUNC-027 | 无 | 路由模式: `createWebHistory()`（HTML5 History API，生产环境需 FastAPI SPA fallback） |
| HTTP 客户端 | **Axios** | >= 1.7 | Promise-based HTTP 客户端，比 `fetch` 提供更好的拦截器机制；请求拦截器统一注入 JWT Token；响应拦截器统一处理 401 和错误提示；支持请求取消（AbortController）用于页面切换时取消未完成请求 | REQ-WEBUI-FUNC-025; REQ-WEBUI-NFUNC-003 | 无 | 不引入 `ofetch` 或 `ky`（团队已有 Axios 经验） |

### 1.2 UI 组件库与图表

| 类别 | 选型 | 版本/版次 | Rationale | 关联 REQ-* | 风险 | 备注 |
|------|------|----------|-----------|-----------|------|------|
| UI 组件库 | **Element Plus** | >= 2.7 | PM 决策 D3 明确要求 Element Plus；Vue 3 原生支持；提供本项目所需全部组件：el-table（表格）、el-form（表单）、el-pagination（分页）、el-dialog（弹窗）、el-menu（侧边栏）、el-breadcrumb（面包屑）、el-tabs（标签页）、el-timeline（时间线）、el-tag（状态标签）、el-badge（徽标）、el-progress（进度条）、el-input show-password（密码显示/隐藏）、v-loading（加载指令）、ElMessage（Toast 通知） | PM 决策 D3; REQ-WEBUI-FUNC-001, 003, 007, 010, 011, 027, 028; REQ-WEBUI-NFUNC-007, 008 | Element Plus 大版本升级（2.x→3.x）可能有 breaking CSS 变更（锁定 2.x） | 全局注册或按需导入（推荐 `unplugin-vue-components` 自动按需导入） |
| 图表库 | **ECharts** | >= 5.5 | PM 决策 D6 要求 "饼图/柱状图/折线图"；ECharts 是 Apache 开源项目，社区最活跃的 Web 图表库；原生支持饼图（pie）、柱状图（bar）、折线图（line）、环形图（pie + radius）、仪表盘（gauge）；Canvas 渲染性能优于 SVG（Dashboard 多图表场景）；`vue-echarts` 提供 Vue 3 组件封装 | PM 决策 D6; REQ-WEBUI-FUNC-022, 023 | ECharts 完整包 ~1MB (gzipped ~300KB)，按需导入（仅注册 pie/bar/line/gauge 四种图表类型）可降低到 ~200KB gzipped | 备选: Chart.js（功能较弱，无原生 gauge）；AntV G2（学习曲线陡） |
| 图表 Vue 封装 | **vue-echarts** | >= 6.6 | ECharts 的 Vue 3 官方封装组件；支持 `option` 响应式绑定；自动处理 chart resize（`resize-observer`）；`loading` prop 显示加载动画 | REQ-WEBUI-FUNC-022 | 依赖 `echarts` 和 `resize-detector` | 也可直接使用 ECharts 实例（`echarts.init()`），但 `vue-echarts` 减少模板代码 |
| CSS 预处理 | **Sass/SCSS** | >= 1.70 (sass 包) | Element Plus 使用 SCSS 变量系统，可通过覆盖 SCSS 变量定制主题色；Vite 原生支持 SCSS（`css.preprocessorOptions`）；Demo 阶段使用 Element Plus 默认主题，SCSS 预装以备定制 | — | 如果需要深度定制主题，Element Plus 的 SCSS 变量覆盖需要准确的变量路径 | 也可使用 CSS Variables（Element Plus 2.x 已支持 CSS 变量主题） |

### 1.3 开发辅助工具

| 类别 | 选型 | 版本/版次 | Rationale | 关联 REQ-* | 风险 | 备注 |
|------|------|----------|-----------|-----------|------|------|
| 类型支持 | **TypeScript** | >= 5.4 | Vue 3 + Vite 对 TypeScript 的一等支持；Pinia/Vue Router/Axios 均有完整 TS 类型定义；API 响应数据的类型定义保证前后端接口契约一致性 | — | 无 | 严格模式 (`strict: true`)，但 Demo 阶段不做强制 CI 类型检查 |
| 图标库 | **@element-plus/icons-vue** | >= 2.3 | Element Plus 官方图标集；提供侧边栏菜单所需全部图标（HomeFilled、Bell、Share、Check、Monitor、Refresh、Notebook、Setting 等）；与 Element Plus 组件无缝集成（`el-icon` 组件） | REQ-WEBUI-FUNC-027 | 无 | 不引入额外的图标库（FontAwesome 等），减少依赖 |
| 代码格式化 | **Prettier** | >= 3.2 | Vue 3 官方推荐格式化工具；支持 .vue SFC 的 template/script/style 三段格式化 | — | 无 | 可选（Demo 阶段非强制 CI 检查） |
| 代码检查 | **ESLint** | >= 8.57 | + `eslint-plugin-vue` >= 9.20；Vue 3 官方推荐 Lint 工具；检测未使用变量、props 类型缺失、v-for key 缺失等常见问题 | REQ-WEBUI-NFUNC-006 | 无 | 可选（Demo 阶段非强制 CI 检查） |

---

## 2. 后端新增依赖

### 2.1 数据持久化

| 类别 | 选型 | 版本/版次 | Rationale | 关联 REQ-* | 风险 | 备注 |
|------|------|----------|-----------|-----------|------|------|
| ORM 框架 | **SQLAlchemy** | >= 2.0 | PM 决策 D2 明确要求 SQLAlchemy ORM；Python 生态最成熟的 ORM，声明式模型定义（`declarative_base`）、关系映射（`relationship`/`back_populates`）、参数化查询防 SQL 注入。2.0 版本支持原生 asyncio（虽然 Web UI 使用同步模式） | PM 决策 D2; REQ-WEBUI-FUNC-001, 009, 010, 013, 015, 016, 019; REQ-WEBUI-NFUNC-006 | SQLAlchemy 2.0 与 1.4 API 有差异（`session.query()` → `select()` 2.0 style）；现有项目若间接依赖 1.x 版本可能需要升级（已验证：现有项目未使用 SQLAlchemy） | 使用 2.0 style（`select()` + `session.execute()`），性能更好且为未来方向 |
| 数据库驱动 | **sqlite3** (Python stdlib) | — | Python 标准库内置 SQLite 驱动；SQLAlchemy 通过 `pysqlite` dialect 直接调用；零额外安装；SQLite 文件数据库与 Chroma 使用的 SQLite 持久化共享同一格式（需注意路径隔离） | PM 决策 D2 | SQLite 并发写锁（WAL 模式缓解）；外键默认不启用（需 pragma 开启） | 不引入 aiosqlite（Web UI 使用同步模式） |
| 数据库迁移 | **Alembic** | >= 1.13 | SQLAlchemy 官方迁移工具；`--autogenerate` 从 Model 变更自动生成迁移脚本；支持 upgrade/downgrade 版本回滚；Demo 阶段的 Schema 变更可追溯 | PM 决策 D2（ADR-WEB-002） | 学习曲线（Alembic 的 env.py 配置和 autogenerate 的检测限制） | [ASSUMPTION] Demo 阶段如 PM 同意，可先用 `Base.metadata.create_all()` 自动建表，Defer Alembic；见 ADR-WEB-002 |

### 2.2 认证与安全

| 类别 | 选型 | 版本/版次 | Rationale | 关联 REQ-* | 风险 | 备注 |
|------|------|----------|-----------|-----------|------|------|
| JWT 库 | **python-jose** | >= 3.3 | FastAPI 官方文档推荐的 JWT 实现；支持 HS256/RS256 签名算法；`jwt.encode()`/`jwt.decode()` API 简洁；轻量依赖（仅依赖 `cryptography` 和 `ecdsa`）；支持 `exp`/`iat`/`sub` 标准 claims | PM 决策 D4, D7; REQ-WEBUI-FUNC-025; REQ-WEBUI-NFUNC-003 | python-jose 更新频率较低，但对 JWT 标准（RFC 7519）的覆盖已足够稳定 | 备选: PyJWT（API 相似但社区稍小）；不着手 `authlib`（功能过重） |
| 密码哈希 | **passlib[bcrypt]** | >= 1.7 | FastAPI 官方文档推荐的密码哈希库；`passlib.hash.bcrypt` 封装了 bcrypt 算法（自动 salt、可配置 rounds）；`verify()` 方法自动从哈希中提取 salt 比对 | PM 决策 D4; REQ-WEBUI-NFUNC-004 | passlib 已进入 "maintenance-only" 模式（不再新增功能），但 bcrypt 算法稳定不变，维护模式不影响安全使用 | 如果不需要 passlib 的额外算法，也可直接使用 `bcrypt` 包；但 passlib 的 API 更简洁 |
| 对称加密 | **cryptography** (fernet) | >= 42.0 | `cryptography.fernet` 提供高级安全加密 API：AES-128-CBC + HMAC-SHA256 认证加密 + 时间戳防重放；开发者无需管理 IV/填充/密钥派生；`Fernet.generate_key()` 生成随机密钥；`Fernet(key).encrypt()`/`decrypt()` 一步完成 | REQ-WEBUI-NFUNC-005; REQ-WEBUI-FUNC-011, 020 | Fernet 使用 AES-128（非 AES-256），安全级别足够（2^128 密钥空间）；若 PM 严格要求 AES-256，需切换为 `cryptography.hazmat` 的 AES-256-GCM 手写封装 [ASSUMPTION — 待 PM 确认，见 ADR-WEB-006] | `cryptography` 包同时也是 `python-jose` 的依赖，不增加额外安装 |

### 2.3 文件处理与静态服务

| 类别 | 选型 | 版本/版次 | Rationale | 关联 REQ-* | 风险 | 备注 |
|------|------|----------|-----------|-----------|------|------|
| 静态文件服务 | **aiofiles** | >= 23.0 | FastAPI `StaticFiles` 使用 aiofiles 提供异步文件读取；用于生产环境挂载 Vue 构建产物 `dist/` 目录；异步 I/O 避免阻塞 FastAPI 事件循环 | PM 决策 D1, D3 | 无 | FastAPI 安装时自动包含，无需显式安装 |
| 文件上传 | **python-multipart** | >= 0.0.6 | FastAPI 表单解析需要（登录表单 `application/x-www-form-urlencoded` 通过 `OAuth2PasswordRequestForm` 解析） | REQ-WEBUI-FUNC-025 | 无 | 仅用于 `/auth/login` 的 OAuth2 表单格式 |

---

## 3. 前端 npm 依赖完整清单 (package.json)

```json
{
  "dependencies": {
    "vue": "^3.4.0",
    "vue-router": "^4.3.0",
    "pinia": "^2.1.0",
    "axios": "^1.7.0",
    "element-plus": "^2.7.0",
    "@element-plus/icons-vue": "^2.3.0",
    "echarts": "^5.5.0",
    "vue-echarts": "^6.6.0"
  },
  "devDependencies": {
    "@vitejs/plugin-vue": "^5.0.0",
    "vite": "^5.4.0",
    "typescript": "^5.4.0",
    "sass": "^1.70.0",
    "unplugin-vue-components": "^0.26.0",
    "unplugin-auto-import": "^0.17.0"
  }
}
```

**总计**: 8 个运行时依赖 + 6 个开发依赖 = 14 个 npm 包。

**按需导入优化**: 使用 `unplugin-vue-components` 自动按需导入 Element Plus 组件和图标，`unplugin-auto-import` 自动导入 Vue Composition API（`ref`, `computed`, `watch` 等），减少手动 import 和 Tree Shaking 后打包体积（预计 Dashboard 页面入口 chunk < 150KB gzipped）。

---

## 4. 后端 PyPI 新增依赖 (requirements_webui.txt)

```
# 数据持久化
sqlalchemy>=2.0.0,<3.0.0
alembic>=1.13.0,<2.0.0

# 认证与安全
python-jose[cryptography]>=3.3.0,<4.0.0
passlib[bcrypt]>=1.7.0,<2.0.0
cryptography>=42.0.0,<44.0.0

# 静态文件服务
aiofiles>=23.0.0,<24.0.0
python-multipart>=0.0.6,<1.0.0
```

**总计**: 6 个新 PyPI 包（其中 `cryptography` 和 `aiofiles` 可能已作为现有依赖的传递依赖存在，不会新增安装）。

---

## 5. 与现有技术栈的兼容性检查

### 5.1 无版本冲突保证

| 现有依赖 | 现有版本范围 | 新增依赖 | 新增版本范围 | 冲突检查 |
|---------|------------|---------|------------|---------|
| Python | >= 3.11 | SQLAlchemy 2.0 | Python >= 3.7 | 兼容（SQLAlchemy 2.0 支持 Python 3.7+） |
| FastAPI | >= 0.110.0 | aiofiles | >= 23.0 | 兼容（FastAPI `StaticFiles` 原生支持 aiofiles） |
| Pydantic | >= 2.5.0 | SQLAlchemy 2.0 | — | 兼容（SQLAlchemy 不依赖 Pydantic；如需 Pydantic ↔ SQLAlchemy 桥接可使用 `sqlalchemy.ext.hybrid` 或手动转换） |
| Jinja2 | >= 3.1 | — | — | 不受影响（Jinja2 用于现有 MOD-007 TemplateEngine，与 Web UI 无关） |
| LangChain | >= 0.3.0 | — | — | 不受影响（Web UI 不引入新的 LangChain 依赖） |
| LangGraph | >= 0.2.0 | — | — | 不受影响（现有 LangGraph 继续使用 MemorySaver，不混入 SQLite per PM 决策 D9） |
| Chroma | >= 0.5.0 | — | — | 不受影响（Chroma 使用的 SQLite 文件路径 `./data/chroma_db/` 与 Web UI 的业务 SQLite 路径 `./data/webui.db` 完全隔离 per PM 决策 D9） |
| loguru | >= 0.7.0 | — | — | 不受影响（MOD-WEB-007 LogReaderService 读取 loguru 输出的文件，不依赖 loguru） |

### 5.2 潜在兼容性关注点

| 关注点 | 详情 | 风险等级 | 缓解措施 |
|--------|------|---------|---------|
| SQLAlchemy 2.0 vs Pandas/NumPy | 现有项目未使用 Pandas，无冲突 | Low | 无需处理 |
| `cryptography` 版本 | 现有 `python-jose[cryptography]` 和新增 `cryptography>=42.0` 可能共享同一安装 | Low | pip 的依赖解析器自动选择兼容版本；`cryptography` 向后兼容良好 |
| Chroma 的 SQLite 与 SQLAlchemy 的 SQLite | 两个组件使用不同的数据库文件，不存在表冲突 | Low | 路径隔离：`./data/webui.db` vs `./data/chroma_db/chroma.sqlite3` |
| FastAPI lifespan 与 SQLAlchemy engine 生命周期 | engine 必须在 lifespan `startup` 中创建、`shutdown` 中 dispose | Medium | 在 lifespan 中调用 `DatabaseManager.create_engine()` → `init_db()` → `AuthService.init_admin_user()` 的启动链 |

---

## 6. 开发与生产环境配置对照

### 6.1 开发环境

| 配置项 | 前端 | 后端 | 说明 |
|--------|------|------|------|
| 运行端口 | Vite dev server: **5173** | Uvicorn: **8000** | Vite 代理 `/api/*` 和 `/auth/*` 到 8000 |
| 跨域处理 | Vite proxy（`vite.config.ts` `server.proxy`） | 无需 CORS 中间件（同源代理） | 避免 CORS 预检请求 |
| 热更新 | Vite HMR（< 1s） | Uvicorn `--reload`（文件变更自动重启） | 前后端均可热重载 |
| 静态文件 | Vite 内存服务 | 不托管（N/A） | 开发时不经过 FastAPI StaticFiles |
| 数据库 | `./data/webui.db` | `./data/webui.db` | 前端不直接访问数据库 |
| 前端启动命令 | `npm run dev` | — | Vite 默认打开 `http://localhost:5173` |
| 后端启动命令 | — | `python src/main.py` | 或 `uvicorn src.main:app --reload --port 8000` |

**Vite 代理配置 (vite.config.ts)**:
```
server: {
  port: 5173,
  proxy: {
    '/api': 'http://localhost:8000',
    '/auth': 'http://localhost:8000',
    '/webhook': 'http://localhost:8000',   // 如需要调试 Webhook
    '/approvals': 'http://localhost:8000',  // 兼容旧端点（过渡期）
    '/workflow': 'http://localhost:8000',   // 兼容旧端点（过渡期）
    '/health': 'http://localhost:8000',
  }
}
```

### 6.2 生产环境 (Demo 部署)

| 配置项 | 部署方式 | 说明 |
|--------|---------|------|
| 运行端口 | Uvicorn: **8000**（唯一端口） | 单进程满足 PM 决策 D1 |
| 前端构建 | `npm run build` → `dist/` | Vite 生产构建（代码压缩 + Tree Shaking + 代码分割） |
| 静态文件托管 | FastAPI `app.mount("/", StaticFiles(directory="dist", html=True))` | SPA fallback 自动处理 |
| API 端点 | `/api/*`、`/auth/*`、`/webhook/alert`（保留旧端点） | 与静态文件路径空间不冲突 |
| 跨域处理 | 无需 | 前后端同域同端口（`http://localhost:8000`） |
| 启动命令 | `python src/main.py` | 一条命令启动全部服务 |
| 数据库 | `./data/webui.db` | 与 `config/config.yaml` 同级目录 |

### 6.3 生产构建产物大小预估

| 构件 | 预计大小 (gzipped) | 包含内容 |
|------|-------------------|---------|
| `index.html` | < 1 KB | SPA 入口 HTML |
| `vendor-vue.js` | ~50 KB | Vue 3 runtime + router + pinia |
| `vendor-element.js` | ~120 KB | Element Plus 按需导入的组件 |
| `vendor-echarts.js` | ~200 KB | ECharts 按需导入（pie/bar/line/gauge） |
| `dashboard.js` | ~30 KB | Dashboard 页面组件 + DashboardStore |
| `alerts.js` | ~40 KB | 告警管理页面组 |
| 其他页面 chunks | ~80 KB | 其余 6 个功能模块页面 |
| **总计** | ~**520 KB** | Dashboard 首次加载仅需 vendor-vue + vendor-element + vendor-echarts + dashboard ≈ 400 KB gzipped，在 10Mbps 网络下加载 < 0.5s，满足 REQ-WEBUI-NFUNC-001（< 3s）要求 |

---

## 7. 技术风险汇总

### 高风险 (High)

| 编号 | 风险描述 | 影响范围 | 缓解措施 |
|------|---------|---------|---------|
| RISK-WEB-001 | **Element Plus 2.x → 3.x 升级**：若 Element Plus 发布 3.x 大版本，可能引入 CSS 类名变更或组件 API breaking changes | 全部前端页面 | 锁定 `"element-plus": "^2.7.0"`（`^` 限制大版本不自动升级）；关注 Element Plus changelog |
| RISK-WEB-002 | **SQLite 并发写锁**：Web UI 多个请求同时写入（如告警接收 + 审批提交 + 巡检记录），SQLite 单写锁可能触发 "database is locked" | MOD-WEB-003, MOD-WEB-004 | WAL 模式（允许并发读，写入串行化）；写操作加 `timeout=5` 等待锁；Demo 单用户场景下并发写概率极低 |

### 中风险 (Medium)

| 编号 | 风险描述 | 影响范围 | 缓解措施 |
|------|---------|---------|---------|
| RISK-WEB-003 | **python-jose 与 cryptography 版本不兼容**：`python-jose[cryptography]` 依赖 `cryptography` 特定版本，若新增的 `cryptography>=42.0` 产生冲突 | MOD-WEB-002 AuthService | pip 依赖解析器自动选择兼容版本；`python-jose>=3.3` 已支持 `cryptography>=41.0`；`cryptography` 向后兼容 |
| RISK-WEB-004 | **ECharts 完整包体积过大**：完整 ECharts 导入 ~1MB (gzipped ~300KB)，可能影响 Dashboard 首次加载 | DashboardView | 按需导入（仅注册 pie/bar/line/gauge），降低到 ~200KB gzipped；图表组件懒加载（Dashboard 页面 onMounted 时动态 `import('echarts')`） |
| RISK-WEB-005 | **Vite build 产物与 FastAPI StaticFiles 的 base 路径不一致**：若 `vite.config.ts` 中 `base` 配置为 `/` 而 FastAPI 挂载在 `/app/`，会导致资源 404 | 生产部署 | `base: '/'` + FastAPI `app.mount("/", ...)`，确保一致 |

### 低风险 (Low)

| 编号 | 风险描述 | 影响范围 | 缓解措施 |
|------|---------|---------|---------|
| RISK-WEB-006 | **passlib 维护模式**：passlib 已进入 maintenance-only 状态，不新增功能 | AuthService | bcrypt 算法稳定（自 1999 年），passlib 的封装 API 不变；如需替换可迁移到 `bcrypt` 直接包 |
| RISK-WEB-007 | **vue-echarts 的 resize 监听**：`vue-echarts` 依赖 `resize-detector` 做图表自适应，在侧边栏折叠/展开时可能触发多次无意义 resize | DashboardView | 使用 `debounce` 延迟 resize 回调（默认 100ms），减少重绘 |
| RISK-WEB-008 | **unplugin-vue-components 解析失败**：若组件名称不符合 Element Plus 的命名规范，自动导入可能遗漏 | 开发体验 | 保留手动 import 作为 fallback；`unplugin-vue-components` 的 `resolvers` 配置 `ElementPlusResolver` 覆盖标准组件 |

---

## 8. Demo 实现策略汇总（Web UI 新增部分）

| 层次 | 组件 | Demo 策略 | 对应模块 |
|------|------|-----------|---------|
| 前端框架 | Vue 3 SPA | **真实实现** (Vite + Element Plus + Pinia + Vue Router + Axios + ECharts) | MOD-WEB-F01 ~ F20 |
| 后端 API | 8 个 APIRouter | **真实实现** (FastAPI APIRouter，32 个新增端点，6 个现有端点不变) | MOD-WEB-001 |
| 认证 | JWT 登录/验证 | **真实实现** (python-jose + passlib[bcrypt]，admin 单账号) | MOD-WEB-002 |
| 数据库 | SQLite + SQLAlchemy | **真实实现** (11 个数据实体，WAL 模式，Alembic 可选) | MOD-WEB-003, MOD-WEB-004 |
| 加密 | API Key / 设备凭据加密 | **真实实现** (cryptography.fernet，密钥从 ENCRYPTION_KEY 环境变量或文件) | MOD-WEB-005 |
| Dashboard 统计 | 聚合查询 + 健康检查 | **真实实现** (SQLite 聚合查询 + LLM 连接测试) | MOD-WEB-006 |
| 日志查看 | 文件日志读取 | **真实实现** (Python 文件 I/O + 倒序分页) | MOD-WEB-007 |
| 前端静态托管 | 生产: FastAPI mount dist/ | **真实实现** (开发: Vite proxy; 生产: StaticFiles html=True) | ADR-WEB-005 |
| LangGraph Checkpoint | MemorySaver | **保持不变** (PM 决策 D9) | 现有 MOD-003 |
| 现有 6 个端点 | 不动 | **保持不变** (废弃 POST /alerts/simulate 标记 deprecated) | 现有 main.py |

---

## 9. 开发环境首次搭建步骤

```
# 1. 后端依赖安装
cd project_workspace/NetworkAgentDemo
pip install -r requirements_webui.txt

# 2. 前端依赖安装
cd webui/
npm install

# 3. 初始化数据库（首次运行自动建表）
python src/main.py
# → DatabaseManager 自动创建 ./data/webui.db + 11 张表
# → AuthService 自动创建 admin 用户（密码从 ADMIN_PASSWORD 或默认 admin）
# → 启动 FastAPI 在 8000 端口

# 4. 启动前端开发服务器（新终端）
cd webui/
npm run dev
# → Vite 启动在 5173 端口，自动代理 /api/* 到 8000

# 5. 浏览器访问
# → http://localhost:5173
# → 登录页 → admin / admin → Dashboard 首页
```
