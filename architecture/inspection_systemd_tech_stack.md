<file_header>
  <author_agent>sub_agent_system_architect</author_agent>
  <timestamp>2026-07-12T00:00:00Z</timestamp>
  <project_name>NetworkAgentDemo</project_name>
  <version>0.2.0</version>
  <input_files>
    <file>requirements/inspection_systemd_requirements.md</file>
    <file>requirements/inspection_systemd_user_stories.md</file>
    <file>architecture/inspection_systemd_architecture_design.md</file>
    <file>architecture/inspection_systemd_module_design.md</file>
    <file>architecture/tech_stack.md (v0.1.0 参考)</file>
  </input_files>
  <phase>PHASE_INSP_03</phase>
  <status>APPROVED</status>
</file_header>

# 巡检机制 systemd 重构 — 技术选型表

---

## 选型原则

v0.2.0 巡检机制 systemd 重构的技术选型遵循以下原则：

1. **最小新增依赖**：优先复用 v0.1.0 已有技术栈，仅因 APScheduler 废弃和 systemd 交互引入必要变更
2. **stdlib 优先**：systemd 交互通过 Python 标准库 `subprocess` 实现，不引入第三方 systemd 绑定库
3. **需求溯源**：每项技术选型必须关联具体的 REQ-INSP-* 或 REQ-INSP-NF-* 需求 ID
4. **PM 决策锚定**：所有选型与 PM 已确认的 6 项关键决策（Q-INSP-001 ~ Q-INSP-006）保持一致

---

## 一、v0.2.0 技术栈变更总览

### 新增依赖

| 类别 | 选型 | 版本 | 说明 |
|------|------|------|------|
| （无新增 Python 第三方依赖） | — | — | v0.2.0 巡检重构全部使用 Python 标准库和已有依赖 |

### 移除依赖

| 类别 | 选型 | 版本 | 移除原因 |
|------|------|------|---------|
| 任务调度 | **APScheduler** | >= 3.10.0（v0.1.0） | REQ-INSP-017: 调度引擎从 APScheduler 迁移至 systemd timer + service；PM Q-INSP-003/006 确认 |

### 复用依赖（v0.1.0 已有，v0.2.0 巡检模块继续使用）

| 类别 | 选型 | v0.1.0 版本 | v0.2.0 巡检用途 |
|------|------|-----------|---------------|
| 模板引擎 | **Jinja2** | >= 3.1 | systemd unit 文件模板渲染（MOD-INSP-001）；复用 MOD-007 已有的 Jinja2 环境 |
| 日志框架 | **loguru** | >= 0.7.0 | CLI 巡检进程日志输出（MOD-INSP-003）；Web 进程操作日志 |
| 数据验证 | **Pydantic** | >= 2.5.0 | systemctl 命令返回结果类型化（TimerStatus, ServiceStatus, SystemctlResult）；API 请求体验证 |
| Web 框架 | **FastAPI** | >= 0.110.0 | inspection_router 增强（6 个新端点 + 4 个增强端点） |
| ORM | **SQLAlchemy** | >= 2.0 | InspectionRecord 表 status 字段；配置读写 |
| 数据库 | **SQLite** | >= 3.35 | 巡检配置 + 历史记录 + 设备列表持久化；CLI 与 Web 进程数据共享 |
| 配置文件 | **PyYAML** | >= 6.0 | config.yaml 降级链（ConfigManager） |
| 环境变量 | **python-dotenv** | >= 1.0 | NETWORKAGENT_HOME 环境变量读取 |

---

## 二、技术选型详表

### 2.1 巡检调度引擎

| 类别 | 选型 | 版本/版次 | Rationale | 关联 REQ-* | 风险 | 备注 |
|------|------|----------|-----------|-----------|------|------|
| 调度引擎 | **systemd timer + service** | systemd >= 219（RHEL7/CentOS7 基线） | OS 级持久化调度，重启不丢失状态；进程隔离（REQ-INSP-NF-004）；原生支持 enable/disable/start/stop/restart（REQ-INSP-006/007）；日志集成 journald（REQ-INSP-NF-007）；Persistent=true 支持系统重启补偿执行；Restart=on-failure 故障自动恢复（REQ-INSP-NF-002）；AccuracySec=1s 高精度触发（REQ-INSP-NF-001）。PM Q-INSP-003/006 确认采用此方案。 | REQ-INSP-006, REQ-INSP-007, REQ-INSP-014~017, REQ-INSP-NF-001/002/004/007 | 强依赖 Linux systemd，Windows/macOS 开发环境不可用（PM Q-INSP-003 决策不做进程内降级）；定时触发的最小间隔受 OnUnitActiveSec 精度限制；systemd 版本差异可能导致 unit 文件配置项行为细微不同 | Demo 部署于 Alibaba Cloud ECS (CentOS/RHEL)，systemd >= 219 满足要求 |
| 备选: APScheduler | **已废弃** | 3.10.0（v0.1.0） | v0.1.0 方案，存在 Web 重启丢失状态、无法进程隔离、无法 systemd 生命周期管理等缺陷。REQ-INSP-017 明确要求废弃。 | — | — | 已从 requirements.txt 移除 |

### 2.2 systemd 交互

| 类别 | 选型 | 版本/版次 | Rationale | 关联 REQ-* | 风险 | 备注 |
|------|------|----------|-----------|-----------|------|------|
| systemctl 调用 | **Python subprocess.run()** | stdlib (Python 3.11+) | 零额外依赖；`shell=False` + 参数列表形式防命令注入（REQ-INSP-NF-003 AC-INSP-NF-003-03）；`timeout=5` 超时控制（AC-INSP-004-03）；`capture_output=True` 捕获 stdout/stderr；`systemctl show --property=` 精确获取所需字段，`Key=Value` 格式解析简单 | REQ-INSP-004, REQ-INSP-006, REQ-INSP-007, REQ-INSP-NF-003 | subprocess fork 开销（每次状态查询 fork 2 次子进程）；sudo 环境变量继承问题（部分环境 sudo 默认不继承 PATH）；subprocess 的 shell=False 无法防止逻辑层面的命令拼接错误（需代码审查确保参数列表构建正确） | MOD-INSP-002 封装所有 systemctl 命令调用，上层模块不直接使用 subprocess |
| systemd 环境检测 | **os.path.exists() + shutil.which()** | stdlib | 检查 `/run/systemd/system` 路径 + `which systemctl` 验证 systemd 可用性（REQ-INSP-NF-006）；零额外依赖 | REQ-INSP-NF-006 | `/run/systemd/system` 是 systemd 的标准运行时目录，非 systemd 系统（WSL1、Docker 未启用 systemd）中不存在 | PM Q-INSP-003 否决了进程内降级策略，环境检测主要用于 Web UI 友好提示 |
| 权限管理 | **sudoers (/etc/sudoers.d/networkagent)** | Linux 标准 | PM Q-INSP-001 确认；精确命令白名单（`networkagent-inspection.*`）；免密码执行；运维人员熟悉的配置方式 | REQ-INSP-NF-003 | sudoers 语法错误可能导致 sudo 不可用（需用 `visudo -c` 校验）；glob 匹配模式需确保不会意外匹配其他 unit 文件 | PM Q-INSP-002 确认运行用户为 networkagent |
| Unit 文件生成 | **Jinja2 模板引擎** | >= 3.1（复用 v0.1.0 MOD-007） | 模板与数据分离；条件渲染支持可选配置段；与 v0.1.0 命令模板引擎技术栈一致；模板文件可独立版本管理和单元测试；满足 REQ-INSP-002 的"模板化方式"要求 | REQ-INSP-002, REQ-INSP-015, REQ-INSP-016 | Jinja2 对 `%` 符号的误解析（systemd 说明符 `%i`/`%n` 等）——当前模板不使用这些说明符；Jinja2 版本需与 v0.1.0 的 MOD-007 保持兼容 | 模板文件存放于 `resources/templates/systemd/` |
| 语法校验 | **systemd-analyze verify** | systemd 自带 | 验证生成的 unit 文件语法正确性（US-INSP-002 AC-INSP-002-03）；systemd 官方工具，输出格式稳定 | REQ-INSP-002 (AC-INSP-002-03) | systemd-analyze 需要完整的 unit 文件上下文（如 Requires/After 引用的 unit 需存在）；verify 仅检查语法不验证运行逻辑 | 通过 MOD-INSP-002 执行 `sudo systemd-analyze verify` |

### 2.3 CLI 巡检入口

| 类别 | 选型 | 版本/版次 | Rationale | 关联 REQ-* | 风险 | 备注 |
|------|------|----------|-----------|-----------|------|------|
| CLI 入口 | **Python `-m` 模块调用** | Python 3.11 stdlib | `python3.11 -m src.inspection_cli run` 作为 systemd service 的 ExecStart；`__main__` 入口支持 `-m` 调用；sys.exit() 返回退出码映射 systemd service Result | REQ-INSP-014 | Python 模块路径需要正确的 PYTHONPATH 或 WorkingDirectory 设置；`-m` 调用需要 `__main__.py` 或模块级 `if __name__ == "__main__"` | PM 技术约束明确指定 `python3.11 -m src.inspection_cli run` |
| 参数解析 | **argparse** | stdlib | 处理 CLI 子命令（`run`）；未来可扩展（如 `--device-filter`）；零额外依赖 | REQ-INSP-014 | 当前仅 `run` 子命令，argparse 能力未充分利用——但为未来扩展预留接口成本极低 | Demo 阶段最小化使用 |
| 日志框架 | **loguru** | >= 0.7.0（复用 v0.1.0） | CLI 进程日志；stdout → journald（REQ-INSP-NF-007）；支持结构化日志；比标准 logging 更简洁的 API | REQ-INSP-NF-007 | loguru 与 multiprocessing 的兼容性在 Windows 上偶有问题——但 CLI 仅在 Linux systemd 下运行 | systemd service 配置 StandardOutput=journal 自动将 stdout 导入 journald |

### 2.4 数据层

| 类别 | 选型 | 版本/版次 | Rationale | 关联 REQ-* | 风险 | 备注 |
|------|------|----------|-----------|-----------|------|------|
| ORM | **SQLAlchemy** | >= 2.0（复用 v0.1.0） | InspectionRecord 模型定义 + SystemConfig K-V 读写 + Device 查询；v0.2.0 仅增加 status 列，不改变 ORM 核心使用方式 | REQ-INSP-010, REQ-INSP-012 | SQLAlchemy 2.0 的新式查询语法（select()）已在 v0.1.0 中使用，v0.2.0 保持一致 | 注意 CLI 进程和 Web 进程各自持有独立的 SQLAlchemy Session |
| 数据库 | **SQLite** | >= 3.35（复用 v0.1.0） | 巡检配置 + 历史记录 + 设备列表持久化；CLI 与 Web 进程通过 SQLite 文件共享数据（唯一耦合点）；零部署依赖 | REQ-INSP-010, REQ-INSP-012, REQ-INSP-NF-004 | CLI 和 Web 进程并发写 SQLite——需要 WAL 模式（`PRAGMA journal_mode=WAL`）支持并发读写；SQLite 文件锁定在极端并发场景下可能成为瓶颈——Demo 场景（单 CLI + 单 Web）无此风险 | [ASSUMPTION] v0.1.0 可能已开启 WAL，需在 v0.2.0 部署时确认 |
| 数据验证 | **Pydantic** | >= 2.5.0（复用 v0.1.0） | TimerStatus/ServiceStatus/SystemctlResult 类型化；API 请求体校验（InspectionConfigUpdate）；FastAPI 依赖 Pydantic v2 | REQ-INSP-001 (AC-INSP-001-03) | Pydantic v1→v2 不兼容，v0.1.0 已使用 v2，无迁移风险 | 所有 systemd 相关返回数据使用 Pydantic BaseModel 定义 |

### 2.5 Web API 层

| 类别 | 选型 | 版本/版次 | Rationale | 关联 REQ-* | 风险 | 备注 |
|------|------|----------|-----------|-----------|------|------|
| Web 框架 | **FastAPI** | >= 0.110.0（复用 v0.1.0） | 巡检 API 挂载在现有 FastAPI 应用（:8000）；新增 6 个端点 + 增强 4 个端点；Pydantic v2 原生支持；自动 OpenAPI 文档 | REQ-INSP-004, REQ-INSP-006, REQ-INSP-007, REQ-INSP-009, REQ-INSP-011 | 无新增风险 | 巡检端点复用现有的 APIRouter + Depends(get_db) 模式 |
| ASGI 服务器 | **Uvicorn** | >= 0.27.0（复用 v0.1.0） | 保持不变 | — | 无 | — |
| 配置管理 | **PyYAML + python-dotenv** | >= 6.0 / >= 1.0（复用 v0.1.0） | ConfigManager 降级链：SQLite > config.yaml > DEFAULT_CONFIG；NETWORKAGENT_HOME 从环境变量读取（PM Q-INSP-004） | REQ-INSP-012, PM Q-INSP-004 | 无新增风险 | v0.2.0 新增 `systemd.working_directory` 等默认配置项 |

### 2.6 前端组件

| 类别 | 选型 | 版本/版次 | Rationale | 关联 REQ-* | 风险 | 备注 |
|------|------|----------|-----------|-----------|------|------|
| 前端框架 | **Vue 3** | >= 3.4（复用 v0.1.0） | InspectionConfigView.vue 增强（状态面板 + 控制按钮组）；InspectionHistoryView.vue 微调；Composition API | REQ-INSP-005, REQ-INSP-008 | 无新增风险 | — |
| UI 组件库 | **Element Plus** | >= 2.5（复用 v0.1.0） | 状态指示灯（el-tag + 颜色）、确认弹窗（ElMessageBox.confirm）、Toast 提示（ElMessage）、表单校验（el-form rules） | REQ-INSP-005, REQ-INSP-008 | 无新增风险 | — |
| 状态管理 | **Pinia** | >= 2.1（复用 v0.1.0） | inspection.ts store 扩展：新增 6 个 actions（fetchStatus, startService, stopService, restartService, enableTimer, disableTimer）；新增 systemd 状态字段 | REQ-INSP-005, REQ-INSP-008 | 无新增风险 | — |
| 前端轮询 | **setInterval / usePolling** | 浏览器 API | 每 5 秒轮询 GET /api/inspection/status（REQ-INSP-005 AC-INSP-005-02）；组件生命周期管理（onMounted/onUnmounted） | REQ-INSP-005 | 轮询频率 5s 对后端压力可忽略；若未来需要减少轮询，可迁移到 WebSocket push 模式 | 当前不使用 WebSocket——需求文档未要求实时 push |

---

## 三、v0.2.0 完整 Python 依赖变更

### 移除

```
# 以下依赖从 requirements.txt 中移除:
apscheduler>=3.10.0,<4.0.0
```

### 保持不变（全部复用 v0.1.0）

```
# AI / LLM
openai>=1.30.0,<2.0.0
langchain>=0.3.0,<0.4.0
langgraph>=0.2.0,<0.3.0
langchain-chroma>=0.1.0,<0.2.0
langchain-community>=0.3.0,<0.4.0

# Web
fastapi>=0.110.0,<1.0.0
uvicorn>=0.27.0,<1.0.0
httpx>=0.26.0,<1.0.0

# 数据
pydantic>=2.5.0,<3.0.0
pyyaml>=6.0,<7.0.0
python-dotenv>=1.0.0,<2.0.0

# 向量数据库
chromadb>=0.5.0,<0.6.0

# 模板 — v0.2.0 巡检模块复用
jinja2>=3.1.0,<4.0.0

# 网络设备（后期启用）
# netmiko>=4.0.0,<5.0.0
# napalm>=4.0.0,<5.0.0

# 校验
jsonschema>=4.20.0,<5.0.0

# 日志 — v0.2.0 巡检 CLI 复用
loguru>=0.7.0,<1.0.0

# 测试
pytest>=8.0.0,<9.0.0
pytest-asyncio>=0.23.0,<1.0.0
```

---

## 四、部署环境依赖（OS 层）

以下为 v0.2.0 巡检功能在目标部署环境（Alibaba Cloud ECS, Linux）中需要的 OS 层组件。这些不是 Python 依赖。

| 类别 | 组件 | 版本要求 | 用途 | 关联 REQ-* | 备注 |
|------|------|---------|------|-----------|------|
| 初始化系统 | **systemd** | >= 219 | timer + service 调度引擎；journald 日志 | REQ-INSP-014, REQ-INSP-NF-004 | Alibaba Cloud ECS (CentOS 7+) 默认 systemd >= 219 |
| systemd 工具 | **systemctl** | (随 systemd) | 状态查询、生命周期控制、daemon-reload | REQ-INSP-004, REQ-INSP-006, REQ-INSP-007 | 需要配置 sudoers 权限 |
| systemd 工具 | **systemd-analyze** | (随 systemd) | unit 文件语法校验 | REQ-INSP-002 (AC-INSP-002-03) | /usr/bin/systemd-analyze |
| sudo | **sudo** | (标准) | Web 进程以 networkagent 用户免密码执行 systemctl | REQ-INSP-NF-003 | sudoers 配置: /etc/sudoers.d/networkagent |
| Python | **Python 3.11** | >= 3.11 | CLI 巡检进程运行环境；Web 进程运行环境 | REQ-INSP-014 | 目标 ECS 已安装 |
| 环境变量 | **NETWORKAGENT_HOME** | — | systemd unit 文件 WorkingDirectory 来源 | PM Q-INSP-004 | 部署时在 /etc/environment 或 .bashrc 中设置 |
| systemd unit 路径 | **/etc/systemd/system/** | — | unit 文件写入目标 | REQ-INSP-002 | 需要 networkagent 用户有写权限（通过 sudo） |

---

## 五、技术风险汇总

### 高风险 (High)

| 编号 | 风险描述 | 影响模块 | 缓解措施 |
|------|---------|---------|---------|
| RISK-INSP-001 | **systemd 不可用时巡检功能完全不可用**：PM Q-INSP-003 否决了进程内降级策略，开发环境（Windows/macOS）无法使用定时巡检和手动触发。开发者需要 Linux 环境或远程 ECS 调试 | MOD-INSP-002, MOD-INSP-003, MOD-WEB-001 | Web UI 状态面板显示"当前环境不支持 systemd，定时巡检功能不可用"；手动触发返回 503 并提示"请先配置巡检服务"；建议开发者使用 WSL2 或远程 ECS 进行巡检功能开发调试 |
| RISK-INSP-002 | **sudoers 配置错误导致 systemctl 操作失败**：sudoers 语法错误可能使 sudo 完全不可用；glob 匹配模式过宽可能授权非预期的 systemctl 操作 | MOD-INSP-002 | 部署脚本中使用 `visudo -c -f /etc/sudoers.d/networkagent` 做语法校验；sudoers 配置使用精确的 unit 名称 glob（`networkagent-inspection.*`）；文档中提供推荐的 sudoers 配置模板 |

### 中风险 (Medium)

| 编号 | 风险描述 | 影响模块 | 缓解措施 |
|------|---------|---------|---------|
| RISK-INSP-003 | **SQLite 并发写冲突**：CLI 进程（巡检结果写入）和 Web 进程（配置读写、历史查询）可能同时访问 SQLite | MOD-WEB-004, MOD-INSP-003 | 确保 SQLite 开启 WAL 模式（`PRAGMA journal_mode=WAL`）；SQLAlchemy Session 使用短生命周期（读写后立即 close）；Demo 场景下单 CLI + 单 Web 并发度低，风险可控 |
| RISK-INSP-004 | **systemctl show 输出格式在不同 systemd 版本间的差异**：`NextElapseUSRealtime` 等属性名和值格式可能在 systemd 版本升级中变化 | MOD-INSP-002 | systemd 的 D-Bus 属性名（如 ActiveState、SubState）是稳定公共接口，版本间极少变化；解析时对意外值做防御处理（未知值记录 WARNING 日志但不崩溃） |
| RISK-INSP-005 | **Jinja2 模板变量缺失导致 unit 文件格式错误**：如果 SQLite 配置缺失必需值，模板渲染可能产生不完整的 unit 文件 | MOD-INSP-001 | 模板渲染前校验所有必需变量已填充；渲染后执行 `systemd-analyze verify` 语法校验；写入前检查内容不为空 |

### 低风险 (Low)

| 编号 | 风险描述 | 影响模块 | 缓解措施 |
|------|---------|---------|---------|
| RISK-INSP-006 | **systemd timer 触发的 CLI 进程因 Python 环境问题启动失败**：ExecStart 中的 `python3.11` 路径在不同 Linux 发行版可能不同（如 `/usr/bin/python3.11` vs `/usr/local/bin/python3.11`） | MOD-INSP-003, MOD-INSP-001 | systemd service 文件使用 `python3.11` 命令名（依赖 PATH 解析），WorkingDirectory 通过 NETWORKAGENT_HOME 环境变量指定；部署文档中明确要求 Python 3.11 在 PATH 中可用 |
| RISK-INSP-007 | **v0.1.0 InspectionRecord 表无 status 列导致 v0.2.0 CLI 写入失败** | MOD-WEB-003, MOD-INSP-003 | 部署脚本执行 `ALTER TABLE inspection_records ADD COLUMN status VARCHAR(15) DEFAULT 'SUCCESS'`；或使用 SQLAlchemy Alembic 自动迁移；历史记录的 status 根据 anomaly_count 推断 |
| RISK-INSP-008 | **前端轮询（5 秒间隔）在后端多用户场景下的性能影响**：每个轮询请求触发 2 次 systemctl show（timer + service），即 2 次 subprocess fork | MOD-INSP-002, MOD-WEB-001 | Demo 场景下单用户，无性能瓶颈；若未来需要优化，可在 systemctl_executor 内部增加 2 秒 TTL 内存缓存 |

---

## 六、v0.1.0 → v0.2.0 Demo 策略变更汇总

| 层次 | 组件 | v0.1.0 Demo 策略 | v0.2.0 Demo 策略 | 变更说明 |
|------|------|-----------------|-----------------|---------|
| 触发层 | 定时巡检调度 | **APScheduler** 真实实现 | **systemd timer + service** 真实实现 | APScheduler 废弃，迁移至 systemd |
| 触发层 | CLI 巡检入口 | 不存在（Web 进程内 daemon 线程） | **MOD-INSP-003** 真实实现 | 从 inspection_scheduler.py 提取 run_inspection_once() |
| 基础设施 | systemd 交互 | 不存在 | **MOD-INSP-001 + MOD-INSP-002** 真实实现 | Jinja2 模板 + subprocess 调用 systemctl |
| Web 层 | 巡检状态查询 | 不存在 | **GET /api/inspection/status** 真实实现 | systemctl show 解析 |
| Web 层 | 巡检生命周期控制 | 不存在 | **POST start/stop/restart/enable/disable** 真实实现 | systemctl 命令封装 |
| Web 层 | 巡检配置管理 | GET/PUT /api/inspection/config | **增强** — 新增 retry_backoff + systemd 同步 | 同步链路: SQLite → Jinja2 → unit 文件 → daemon-reload |
| Web 层 | 手动触发巡检 | POST /api/inspection/trigger（进程内线程） | **增强** — systemctl start service | PM Q-INSP-003 决策 |
| Web 层 | 巡检历史 | GET /api/inspection/history | **增强** — 新增 status 筛选 + status 列 | 数据表增加 status 字段 |
| 前端 | 巡检配置页面 | 配置表单 | **增强** — 新增状态面板 + 控制按钮组 + 5s 轮询 | Vue 3 组件增强 |
| 数据 | InspectionRecord | 6 列（无 status） | **增强** — 新增 status 列 | ALTER TABLE 迁移 |
| 数据 | SystemConfig | 4 个巡检配置键 | **增强** — polling_interval 替换为 retry_backoff | 键值表 upsert |
</file_header>