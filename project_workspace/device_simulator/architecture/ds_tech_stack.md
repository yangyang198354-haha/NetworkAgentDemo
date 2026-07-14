<file_header>
  <project_id>NetworkAgentDemo</project_id>
  <module_id>device_simulator</module_id>
  <doc_type>tech_stack</doc_type>
  <file_name>ds_tech_stack.md</file_name>
  <version>0.1.0</version>
  <status>DRAFT</status>
  <author_agent>sub_agent_system_architect</author_agent>
  <created_at>2026-07-14T00:00:00Z</created_at>
  <last_updated>2026-07-14T00:00:00Z</last_updated>
  <invocation_id>inv-ds-group-b-001</invocation_id>
  <input_source>ds_requirements_spec.md (APPROVED), requirements.txt (existing deps), PM technical constraints</input_source>
</file_header>

# 设备类型区分 — 技术选型文档

## 技术选型表

| 类别 | 选型 | 版本/版次 | Rationale | 关联 REQ-* | 风险 | 备注 |
|------|------|----------|-----------|-----------|------|------|
| 编程语言 | Python | 3.11+ | 现有项目语言；类型提示 (TypedDict, str\|None) 良好支撑状态管理 | REQ-NFUNC-103 | Low | 复用现有 |
| Web 框架 | FastAPI | >=0.110.0 | 现有框架；APIRouter 扩展自然、Pydantic v2 schema 校验、JWT 依赖注入复用 | REQ-FUNC-112, REQ-NFUNC-104 | Low | 复用现有 |
| SSH 服务端库 | **paramiko** | >=3.4.0 | Python 生态最成熟的 SSH 协议实现；`ServerInterface` + `Transport` 提供进程内 SSH 服务能力；项目通过 Netmiko 间接依赖 (TP-Link 预留)；PM 技术约束明确允许 | REQ-FUNC-106, REQ-NFUNC-101, REQ-NFUNC-105 | **Medium** | **新增依赖**（见候选对比），需从隐式依赖提升为显式 |
| SSH 客户端库 | **paramiko** (SSHClient) | >=3.4.0 (同上) | `SSHClient.connect()` + `exec_command()` 提供 SSE 命令执行通道；与 ServerInterface 同库减少依赖面 | REQ-FUNC-107, REQ-FUNC-108, REQ-FUNC-109, REQ-NFUNC-101 | Low | 复用上述新增依赖 |
| 加密 | cryptography (Fernet) | >=42.0.0 | 现有依赖；模拟器密码加密存储复用现有 `EncryptionService.encrypt/decrypt` | REQ-NFUNC-102 | Low | 复用现有 |
| ORM | SQLAlchemy 2.0 | >=2.0.0 | 现有依赖；`mapped_column` + `Base.metadata.create_all()` 支持 DDL 自动迁移 | REQ-FUNC-102, REQ-NFUNC-103, REQ-NFUNC-104 | Medium | 复用现有；SQLite ADD COLUMN 行为需验证 |
| 数据库 | SQLite (WAL 模式) | 3.35+ | 现有数据层；`device_type` 等新列通过 `ALTER TABLE ADD COLUMN` 自动追加；Demo 项目无迁移工具 (OS-06) | REQ-FUNC-102 | Low | 复用现有 |
| 前端框架 | Vue 3 + TypeScript | 3.x | 现有前端；Composition API + `<script setup>` 语法 | REQ-FUNC-116, REQ-FUNC-117, REQ-FUNC-118 | Low | 复用现有 |
| UI 组件库 | Element Plus | 2.x | 现有 UI；`el-drawer` (模拟器操作面板)、`el-table` (设备列表+端口列表)、`el-tag` (类型标签)、`el-progress` (系统资源) | REQ-FUNC-116, REQ-FUNC-117, REQ-FUNC-118 | Low | 复用现有；PM 确认 Q-03 内联抽屉 |
| 状态管理 | Pinia | 2.x | 现有状态管理；`defineStore` 扩展 devicesStore | REQ-FUNC-116, REQ-FUNC-117, REQ-FUNC-118 | Low | 复用现有 |
| HTTP 客户端 (前端) | axios | 1.x | 现有 HTTP 库；新增 7 个模拟器 API 方法 | REQ-FUNC-113, REQ-FUNC-114, REQ-FUNC-115 | Low | 复用现有 |
| 日志 | loguru | >=0.7.0 | 现有日志；模拟器事件日志 + SSH 访问日志 (REQ-NFUNC-102 明文过滤) | REQ-NFUNC-102 | Low | 复用现有 |
| 并发模型 | threading (标准库) | Python 3.11 内置 | 每台模拟器 1 条监听线程；每个 SSH 会话 1 条交互线程；`daemon=True` 确保进程退出可回收 | REQ-NFUNC-105 | Low | 标准库，零新增 |
| 端口管理 | socket (标准库) | Python 3.11 内置 | TCP 端口可用性检测 (bind-test 法)；心跳 TCP connect 探测 | REQ-FUNC-105, REQ-FUNC-121 | Low | 标准库，零新增 |
| 测试框架 | pytest | >=8.0.0 | 现有测试框架；Mock*Tool 回归测试 + Simulator*Tool 单元测试 | REQ-NFUNC-103 | Low | 复用现有 |

---

## 候选方案对比（关键决策项）

### 选型 1: SSH 服务端实现库

**需求锚定**: REQ-FUNC-106 (SSH 登录认证)、REQ-NFUNC-101 (单命令 ≤1s)、REQ-NFUNC-105 (5 并发会话)

| 维度 | 候选 A: paramiko | 候选 B: 纯 socket 自研 | 候选 C: asyncssh |
|------|-------------------|------------------------|-------------------|
| **SSH 协议完整性** | ServerInterface 覆盖认证+shell 通道，协议层成熟 | 需手动实现 SSH 握手、密钥交换、认证协议——工作量极大 (~5000+ 行协议代码) | 与 paramiko 相当的 SSH 协议实现，纯 async/await |
| **学习/维护成本** | 文档完善、社区成熟、Demo 场景够用 | 极高——协议细节易出错 (OS-02 虽豁免但协议正确性仍需保证) | 与 paramiko 同级，但生态略小 |
| **与现有架构匹配** | 同步阻塞 API，需 threading 包装 | 同步，但基础协议工作量远超 Demo 范围 | 纯异步 API，与 FastAPI 事件循环匹配但需重构 NodeHandlers |
| **依赖增量** | 新增 1 个 pip 包 (~2MB) | 零新增 (标准库) | 新增 1 个 pip 包 |
| **性能满足度** | 满足 (线程 I/O 模型对于 ≤5 并发绰绰有余) | 可满足但开发成本过高 | 满足，但引入 async 传染 (async/await 需穿透 NodeHandlers) |
| **PM 约束匹配** | "可考虑 paramiko 复用现有依赖" — 明确放行 | 虽有标准库优势，但技术风险过高 | 未在 PM 约束中提及 |

**决策**: **paramiko** (Candidate A)。纯 socket 自研 SSH 协议的工作量远超 Demo 场景的合理范围，且引入不必要的协议层 bug 风险。asyncssh 的 async/await 模型会"传染"NodeHandlers 和 Workflow 引擎（当前为同步 `StateGraph`），强制改造的范围过大。

### 选型 2: 模拟器前端操作面板

**需求锚定**: REQ-FUNC-118 (模拟器操作按钮和面板)、PM Q-03 确认 (内联弹窗/抽屉)

| 维度 | 候选 A: Element Plus Drawer | 候选 B: Element Plus Dialog (Modal) | 候选 C: 表格行内展开 (Expand) |
|------|------------------------------|--------------------------------------|-------------------------------|
| **上下文保持** | 优——右侧滑出，设备列表持续可见 | 差——全屏遮罩阻断列表视野 | 优——行内展开，但拉长行破坏表格可读性 |
| **内容承载量** | 中——30~50% 宽度，适合端口列表表格+系统监控面板 | 中——可自定义宽度，但全屏遮罩体验不佳 | 差——8 端口+系统数据展开会严重拉长行 |
| **操作便利性** | 中——Drawer 内可嵌套按钮/表单/确认弹窗 | 低——Modal 堆叠体验差 (操作 → 确认 → 结果三层 Modal) | 高——行内操作不离开表格 |
| **PM 确认** | **已确认** (Q-03) | 未确认 | 未确认 |
| **Element Plus 支持** | 内置 `<el-drawer>` | 内置 `<el-dialog>` (已有使用) | 内置 `type="expand"` |

**决策**: **Element Plus Drawer** (Candidate A)，已有 PM 明确确认 (Q-03)。

### 选型 3: 工具工厂分发策略

**需求锚定**: REQ-FUNC-111 (工厂策略扩展)、REQ-FUNC-103 (Mock 零变更)

| 维度 | 候选 A: 简单 if-else (KISS) | 候选 B: 策略注册表 |
|------|------------------------------|---------------------|
| **代码变更量** | 3 个工厂函数各 ~8 行变更 | 每个工具模块新增注册表 + 装饰器 (~15 行/模块) |
| **扩展性** | OCP 违反——加类型需改工厂 | OCP 合规——注册即可 |
| **Demo 适配度** | 高——仅有 2 种活跃类型 (MOCK/SIMULATOR) | 低——为 2 种类型建立注册表是过度设计 |
| **调试难度** | 低——单步调试直接进入分支 | 中——dict lookup + 间接实例化 |
| **迁移路径** | 若类型 ≥4 种，重构为注册表 (≤1h 工时) | 无需迁移 (但当前阶段维护成本 > 收益) |

**决策**: **简单 if-else** (Candidate A)。Demo 阶段 KISS 原则优先，迁移路径明确（ADR-DS-003）。

---

## 新增 vs 复用依赖标注

### 新增依赖（需修改 requirements.txt）

| 序号 | 包名 | 版本 | 用途 | 影响范围 | 理由 |
|------|------|------|------|----------|------|
| 1 | **paramiko** | >=3.4.0,<4.0.0 | SSH 服务端 (ServerInterface) + SSH 客户端 (SSHClient) | MOD-DS-003, MOD-DS-006, MOD-DS-007, MOD-DS-008 | 唯一新增依赖；PM 技术约束明确允许；TP-Link 预留的 Netmiko 已依赖 paramiko，项目未来必然需要 |

### 复用依赖（无变更）

| 包名 | 复用模块 | 备注 |
|------|----------|------|
| fastapi, uvicorn | MOD-DS-010 | API 端点扩展（7 个新端点 + Schema 扩展） |
| sqlalchemy | MOD-DS-002 | ORM 模型扩展（3 个新字段） |
| cryptography (Fernet) | MOD-DS-005, MOD-DS-010 | 密码加解密复用 `EncryptionService` |
| loguru | MOD-DS-003, MOD-DS-005 | SSH 事件日志 + 生命周期日志 |
| pydantic | MOD-DS-010 | Schema 校验复用 Pydantic v2 |
| python-jose | MOD-DS-010 | JWT 认证复用现有中间件 |
| Vue 3, Element Plus, Pinia, axios | MOD-DS-013, MOD-DS-014, MOD-DS-015 | 前端全栈复用 |
| threading, socket, enum, random | 标准库 | 零新增（Python 3.11+ 内置） |

---

## 技术风险汇总

| 风险编号 | 风险描述 | 等级 | 触发条件 | 影响 | 缓解措施 | 关联 REQ |
|----------|----------|------|----------|------|----------|----------|
| RSK-01 | paramiko 新增依赖引入版本兼容性问题 | **Medium** | paramiko 与现有 cryptography 版本不兼容 | SSH 服务无法启动，所有 SIMULATOR 功能不可用 | ① 在 requirements.txt 中锁定兼容版本范围 (>=3.4.0,<4.0.0)；② CI 中增加 paramiko 导入冒烟测试 | REQ-FUNC-106 |
| RSK-02 | SQLite `ALTER TABLE ADD COLUMN` 行为在 create_all() 时的不确定性 | **Medium** | SQLAlchemy 对 SQLite ADD COLUMN + DEFAULT 的处理与预期不符 | 现有设备记录的 `device_type` 为 NULL 而非 "MOCK" | ① 数据库初始化后执行补偿脚本 `UPDATE devices SET device_type='MOCK' WHERE device_type IS NULL`；② 应用层 DeviceRepository 读取时做 `or "MOCK"` 兜底；③ 手工验证 SQLAlchemy 2.0 + SQLite 的 `server_default` 行为 | REQ-FUNC-102, REQ-NFUNC-103 |
| RSK-03 | daemon 线程在 FastAPI 进程退出时未优雅释放端口 | **Low** | `threading.Thread(daemon=True)` + 进程收到 SIGTERM | 端口残留 (TIME_WAIT)，重启后端口仍被占用数秒 | ① FastAPI shutdown 事件中遍历 LifecycleManager 调用 `shutdown_all()`；② `transport.close()` 后 `time.sleep(0.5)` 等待 socket 释放；③ 端口分配时检测 `SO_REUSEADDR` | REQ-FUNC-121 |
| RSK-04 | 5 并发 SSH 会话下的线程安全 | **Low** | 多个 SimulatorSSHSession 同时读写 DeviceStateManager | 端口状态/VLAN 数据出现竞态条件 | ① DeviceStateManager 的 `set_port_status` / `set_port_vlan` 等方法加 `threading.Lock`；② 读操作（`get_all_ports`）不加锁（读取一致快照） | REQ-NFUNC-105 |
| RSK-05 | Workflow State (MemorySaver) 与新 device_type 字段的兼容性 | **Low** | 升级前持久化的旧 state 不含 `device_type` 字段 | 工作流恢复时 `state["device_type"]` 抛 KeyError | ① 所有读取处使用 `state.get("device_type", "MOCK")` 兜底；② 升级说明中标注：存量工作流将按 MOCK 类型继续执行 (行为不变，REQ-NFUNC-103) | REQ-FUNC-119, REQ-NFUNC-103 |
| RSK-06 | 前端 Drawer 内端口配置操作的响应延迟用户体验 | **Low** | 模拟器 SSH 连接建立慢 (>1s) | Drawer 内操作按钮点击后延迟感知明显 | ① UI 层使用 `el-button` 的 `loading` 状态提供即时反馈；② 操作成功后局部刷新端口行而非整页刷新 | REQ-NFUNC-101 |

---

*文档版本 0.1.0 | 状态 DRAFT | 生成时间 2026-07-14 | 作者 sub_agent_system_architect*

<audit_log>
  <log time="2026-07-14T00:00:00Z" state="WRITE_FILES" action="file_write" result="SUCCESS" trace_id="inv-ds-group-b-001" file_path="project_workspace/device_simulator/architecture/ds_tech_stack.md"/>
</audit_log>
