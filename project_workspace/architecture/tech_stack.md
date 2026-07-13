<file_header>
  <author_agent>sub_agent_system_architect</author_agent>
  <timestamp>2026-07-10T00:00:00Z</timestamp>
  <project_name>NetworkAgentDemo</project_name>
  <version>0.1.0</version>
  <input_files>
    <file>requirements/project_brief.md</file>
    <file>requirements/requirements_spec.md</file>
    <file>requirements/user_stories.md</file>
    <file>architecture/architecture_design.md</file>
    <file>architecture/module_design.md</file>
  </input_files>
  <phase>PHASE_03</phase>
  <status>APPROVED</status>
</file_header>

# 技术选型表 — NetworkAgentDemo

---

## 技术选型表

### 1. 运行时与核心语言

| 类别 | 选型 | 版本/版次 | Rationale | 关联 REQ-* | 风险 | Demo 策略 | 备注 |
|------|------|----------|-----------|-----------|------|-----------|------|
| 编程语言 | Python | >= 3.11 | REQ-NFUNC-012 要求 Linux 运行环境；LangChain/LangGraph 生态原生 Python；Netmiko/NAPALM 均为 Python 库；Python 3.11+ 提供更好的 asyncio 支持和性能优化 | REQ-NFUNC-012 | 无 | 真实实现 | Python 3.11 引入的 `TaskGroup` 可用于并发巡检 |
| 异步运行时 | asyncio (stdlib) | 3.11+ | FastAPI 基于 asyncio；APScheduler 支持 AsyncIOScheduler；巡检并发执行多设备诊断需要异步 I/O | REQ-FUNC-003, REQ-NFUNC-012 | 无 | 真实实现 | 无需额外安装，Python 标准库内置 |
| 包管理器 | pip + venv | latest | Python 标准方案；venv 创建隔离环境，确保依赖版本一致性 | REQ-NFUNC-012 | 依赖版本冲突（通过 requirements.txt 锁定） | 真实实现 | 建议使用 `pip-tools` 或 `poetry` 做依赖锁定 |

---

### 2. AI / LLM 相关

| 类别 | 选型 | 版本/版次 | Rationale | 关联 REQ-* | 风险 | Demo 策略 | 备注 |
|------|------|----------|-----------|-----------|------|-----------|------|
| LLM SDK | **openai** Python SDK | >= 1.0.0 | project_brief 第 11 行明确要求 "使用 openai Python SDK"；DeepSeek API 提供 OpenAI 兼容端点（`https://api.deepseek.com/v1`）；v1.0.0+ 引入新的 client API（`openai.OpenAI()`），更稳定 | REQ-NFUNC-013 | DeepSeek API 可用性依赖网络；openai SDK 大版本升级可能引入 breaking changes（已通过版本约束控制） | 真实 API 调用 | 注意：不是安装 `deepseek` 包，而是用 openai SDK 指向 DeepSeek base_url |
| LLM 模型 | **deepseek-chat** | latest (via API) | project_brief 第 11 行明确指定；temperature=0.1；DeepSeek Chat 在中文理解和结构化输出方面表现良好；API 成本远低于 GPT-4 | REQ-NFUNC-013, REQ-FUNC-010 | API 限流/配额耗尽；模型输出格式不稳定（通过 MOD-009 OutputValidator 缓解） | 真实 API 调用 | 需要有效的 DEEPSEEK_API_KEY 环境变量 |
| 状态机编排 | **LangGraph** | >= 0.2.0 | project_brief 第 17 行要求 "LangGraph 构建有限状态机"；原生支持 StateGraph + conditional edges + Interrupt 机制；与 LangChain Tool 生态无缝集成 | REQ-FUNC-006, REQ-FUNC-013 | LangGraph API 仍在快速迭代（0.2→0.3 可能有 breaking changes）；Interrupt 机制在异步模式下的行为需要验证 | 真实实现 | 安装 `langgraph` 包（注意与 `langchain` 版本兼容性） |
| LLM 框架基础 | **LangChain** | >= 0.3.0 | 为 Tool 封装提供 BaseTool 基类（REQ-FUNC-017~020）；提供 Chroma/RAG 集成（REQ-FUNC-019）；提供 Prompt Template 管理 | REQ-FUNC-017, REQ-FUNC-018, REQ-FUNC-019, REQ-FUNC-020 | LangChain 版本迭代快，API 变更频繁；与 LangGraph 版本存在耦合（LangGraph 依赖特定 LangChain 版本） | 真实实现 | 建议锁定 `langchain>=0.3.0,<0.4.0` 和 `langgraph>=0.2.0,<0.3.0` |
| 嵌入模型 | **text-embedding-3-small** | latest (via openai SDK) | 用于 Chroma 知识库文档向量化（REQ-FUNC-019）；通过 openai SDK 调用，与 DeepSeek 的 OpenAI 兼容端点统一；性价比高于 text-embedding-ada-002 | REQ-FUNC-019 | Embedding API 与 Chat API 可能不在同一 base_url（DeepSeek 是否提供 embedding 端点需要验证）；详情见 §嵌入模型备选说明 | 真实 API 调用 | 如果 DeepSeek 不提供 embedding 端点，需要使用 OpenAI 原生端点或本地模型 |
| LLM 输出校验 | **jsonschema** | >= 4.20 | JSON Schema 校验 LLM 输出的模板参数格式（MOD-009）；Python 生态标准库，成熟稳定；支持自定义 validator | REQ-NFUNC-001, REQ-NFUNC-002 | 无 | 真实实现 | 正则黑名单扫描（CLI 命令检测）使用 Python `re` 标准库 |

#### 嵌入模型备选说明

| 方案 | 端点 | 优势 | 劣势 | 决策 |
|------|------|------|------|------|
| text-embedding-3-small via openai SDK | `https://api.openai.com/v1` | 质量高、速度快 | 需要额外的 OpenAI API key；与 DeepSeek 不是同一厂商 | 首选（需额外配置 OPENAI_API_KEY） |
| DeepSeek Embedding（若有） | `https://api.deepseek.com/v1` | 与 LLM 调用使用同一 base_url 和 API key | 截至选型时 DeepSeek 未公开提供 embedding 模型 | 备选（待验证） |
| 本地嵌入模型（如 sentence-transformers） | 本地 | 无 API 成本、离线可用 | Demo 场景数据量极小，额外依赖过重；向量质量可能不如 OpenAI | 降级方案 |

> [ASSUMPTION] DeepSeek 是否提供 embedding API 端点需要在实施阶段验证。若不可用，使用 OpenAI text-embedding-3-small（需额外 API key），或降级为本地 sentence-transformers `all-MiniLM-L6-v2`。

---

### 3. Web 框架与 API

| 类别 | 选型 | 版本/版次 | Rationale | 关联 REQ-* | 风险 | Demo 策略 | 备注 |
|------|------|----------|-----------|-----------|------|-----------|------|
| Web 框架 | **FastAPI** | >= 0.110.0 | 轻量级高性能异步 Web 框架，适合 Webhook 接收端点（REQ-FUNC-001）；原生支持 Pydantic v2 请求体验证；自动生成 OpenAPI 文档便于 Demo 调试；与 asyncio 无缝集成 | REQ-FUNC-001, IFC-001 | 无 | 真实实现 | 使用 `uvicorn` 作为 ASGI 服务器 |
| ASGI 服务器 | **Uvicorn** | >= 0.27.0 | FastAPI 官方推荐的 ASGI 服务器；支持热重载（Demo 开发便利）；轻量无额外依赖 | REQ-FUNC-001 | 无 | 真实实现 | 开发模式使用 `--reload`，生产需配合 gunicorn |
| HTTP 客户端 | **httpx** | >= 0.26.0 | Mock Webhook 推送脚本（REQ-FUNC-002）需要 HTTP 客户端；支持 async/await；比 requests 更现代的 API | REQ-FUNC-002 | 无 | 真实实现 | Mock Webhook 脚本属于独立工具，不纳入模块体系 |
| 数据验证 | **Pydantic** | >= 2.5.0 | NetworkAgentState 类型定义（REQ-FUNC-004）；Alert Payload Schema 校验（IFC-001）；FastAPI 依赖 Pydantic；v2 性能大幅优于 v1 | REQ-FUNC-004, IFC-001 | Pydantic v1→v2 API 不兼容（已通过显式要求 v2 规避） | 真实实现 | 使用 `pydantic.BaseModel` 定义所有数据模型 |

---

### 4. 定时调度

| 类别 | 选型 | 版本/版次 | Rationale | 关联 REQ-* | 风险 | Demo 策略 | 备注 |
|------|------|----------|-----------|-----------|------|-----------|------|
| 任务调度 | **APScheduler** | >= 3.10.0 | 主动巡检定时触发（REQ-FUNC-003）；支持 IntervalTrigger（按固定间隔触发）；支持 AsyncIOScheduler（与 FastAPI/asyncio 兼容）；支持持久化 job store | REQ-FUNC-003 | APScheduler 4.0 尚未稳定发布（3.x 继续维护） | 真实实现 | 巡检间隔默认 5 分钟，通过 MOD-016 ConfigManager 可配置 |
| 备选: schedule | — | — | 极简 API，但只支持同步函数，无法与 asyncio 集成 | — | — | 否决 | 巡检需要异步并发诊断多设备 |
| 备选: Celery | — | — | 功能强大但需要 Redis/RabbitMQ broker，部署复杂度远超 Demo 范围 | — | — | 否决 | Demo 阶段不引入消息队列（ADR-005 Option C） |

---

### 5. 网络设备交互（工具层）

| 类别 | 选型 | 版本/版次 | Rationale | 关联 REQ-* | 风险 | Demo 策略 | 备注 |
|------|------|----------|-----------|-----------|------|-----------|------|
| SSH 客户端 (TP-Link) | **Netmiko** | >= 4.0.0 | project_brief 第 32 行指定 SwitchDiagTool 使用 Netmiko；TP-Link 命令风格接近 Cisco IOS，Netmiko 的 `cisco_ios` 驱动直接兼容；支持 SSH 连接池和自动重连；成熟的异常处理（超时、认证失败） | REQ-FUNC-008, REQ-FUNC-018, REQ-NFUNC-014 | TP-Link 可能与 Cisco IOS 存在细微命令差异（如 `show mac address-table` 的输出格式）；Netmiko 的 TP-Link 特定驱动（`tplink_jetstream`）需要单独验证 | **Mock 实现**（Demo）<br>真实实现（后期） | Demo 阶段不调用 Netmiko；TpLinkSwitchDiagTool 预留 `_run()` 中使用 Netmiko |
| 配置管理 (TP-Link) | **NAPALM** | >= 4.0.0 | project_brief 第 31 行指定 SwitchConfigTool 使用 NAPALM；提供统一的配置管理接口（merge/commit/discard/rollback）；支持配置对比（compare_config）和备份（get_config）；与 Netmiko 网络驱动层互补 | REQ-FUNC-014, REQ-FUNC-017, REQ-NFUNC-014 | NAPALM 对 TP-Link 的官方支持有限（主要通过 community driver）；配置 merge 行为可能与预期不同 | **Mock 实现**（Demo）<br>真实实现（后期） | Demo 阶段不调用 NAPALM；TpLinkSwitchConfigTool 预留 `_run()` 中使用 NAPALM |
| 备选: Paramiko | — | — | Netmiko 基于 Paramiko，直接使用 Paramiko 更底层但失去 Netmiko 的设备驱动和自动处理 | — | — | 否决 | Netmiko 已提供足够的抽象层级 |
| 备选: Scrapli | — | — | 新一代网络自动化库，异步原生支持，但生态成熟度不如 Netmiko/NAPALM | — | — | 否决 | 技术栈一致性和 MVP 速度优先 |

---

### 6. 知识库 / RAG

| 类别 | 选型 | 版本/版次 | Rationale | 关联 REQ-* | 风险 | Demo 策略 | 备注 |
|------|------|----------|-----------|-----------|------|-----------|------|
| 向量数据库 | **Chroma** | >= 0.5.0 | 本地嵌入式向量库，零部署依赖（ADR-006 选型）；LangChain 原生集成（`langchain-chroma`）；支持元数据过滤（`where={"alert_type": ...}`）；持久化到磁盘 | REQ-FUNC-019 | Chroma 嵌入式模式使用 SQLite，Linux 与 Windows 行为差异需验证 | 真实 Chroma 运行（但知识条目为 Mock 示例数据） | 使用 `chromadb` 包 + `langchain-chroma` 集成 |
| 备选: FAISS | — | — | 性能在百万级向量下优于 Chroma，但 Demo 数据量极小无优势；索引管理比 Chroma 繁琐（ADR-006 Option B） | — | — | 否决 | 见 ADR-006 详细对比 |
| 备选: 纯关键词匹配 | — | — | 无额外依赖，但不支持语义搜索（ADR-006 Option C） | — | — | 否决 | 不满足 RAG 技术内涵 |
| LangChain 检索 | **langchain-chroma** | >= 0.1.0 | LangChain 官方的 Chroma 集成包；提供 `Chroma.as_retriever()` 标准接口；支持 MMR（最大边际相关性）检索减少冗余 | REQ-FUNC-019 | 版本与 langchain 主包和 chromadb 的兼容性需要验证 | 真实实现 | 注意依赖版本对齐 |

---

### 7. 模板引擎与命令生成

| 类别 | 选型 | 版本/版次 | Rationale | 关联 REQ-* | 风险 | Demo 策略 | 备注 |
|------|------|----------|-----------|-----------|------|-----------|------|
| 模板引擎 | **Jinja2** | >= 3.1 | 确定性命令模板渲染（MOD-007）；Python 生态最成熟的模板引擎；TP-Link Cisco IOS 风格命令模板天然适配 Jinja2 变量替换语法（`{{ iface_name }}`）；与 Flask/FastAPI 无直接依赖关系 | REQ-FUNC-021, REQ-NFUNC-001, REQ-NFUNC-002 | Jinja2 本身可执行任意 Python 表达式（需通过 SandboxedEnvironment 限制） | 真实实现 | 命令模板存储在 `resources/templates/`，YAML 格式，Jinja2 字符串 |
| 模板存储格式 | **YAML** | >= 6.0 (PyYAML) | 人可读、支持多行字符串（适合命令模板）；支持注释；与 MOD-016 ConfigManager 一致 | REQ-FUNC-021 | YAML 缩进敏感，编辑时可能引入格式错误 | 真实实现 | 每个模板文件一个 YAML 文档 |

---

### 8. 日志与审计

| 类别 | 选型 | 版本/版次 | Rationale | 关联 REQ-* | 风险 | Demo 策略 | 备注 |
|------|------|----------|-----------|-----------|------|-----------|------|
| 日志框架 | **loguru** | >= 0.7.0 | 全链路操作日志 + 审计追踪（REQ-NFUNC-010, REQ-NFUNC-011）；比标准 logging 模块 API 更友好（零配置可用）；原生支持结构化日志（`log.bind(alert_id=...)`）；支持文件轮转和保留策略 | REQ-NFUNC-010, REQ-NFUNC-011 | loguru 使用 `pickle` 序列化某些内部对象，在极端情况下可能有安全性考虑（但 Demo 环境可控） | 真实实现 | 操作日志与审计日志分开文件：`operations_{date}.log` 和 `audit.log` |
| 备选: logging (stdlib) | — | — | Python 标准库，零额外依赖；但配置繁琐，结构化日志需要额外处理 | — | — | 否决 | loguru 的开发效率远优于标准 logging |
| 备选: structlog | — | — | 结构化日志领域最佳，但 Demo 规模下 loguru 更简洁 | — | — | 否决 | loguru 满足 Demo 需求 |

---

### 9. 配置管理

| 类别 | 选型 | 版本/版次 | Rationale | 关联 REQ-* | 风险 | Demo 策略 | 备注 |
|------|------|----------|-----------|-----------|------|-----------|------|
| 配置文件解析 | **PyYAML** | >= 6.0 | MOD-016 ConfigManager 的配置文件格式；人可读性好；支持层次化配置；命令模板也使用 YAML 存储（一致性） | REQ-NFUNC-004, REQ-NFUNC-007 | YAML 1.1 vs 1.2 规范差异（PyYAML 遵循 1.1，`Yes`/`No` 被解析为 bool） | 真实实现 | 配置文件：`config/config.yaml`；注意避免 YAML 歧义值 |
| 环境变量 | **python-dotenv** | >= 1.0 | 管理敏感配置（API keys、设备凭据）；`.env` 文件不提交版本控制；12-factor app 最佳实践 | REQ-NFUNC-004 | `.env` 文件泄露风险（通过 .gitignore 控制） | 真实实现 | DEEPSEEK_API_KEY, OPENAI_API_KEY 通过环境变量注入 |

---

### 10. 测试与调试

| 类别 | 选型 | 版本/版次 | Rationale | 关联 REQ-* | 风险 | Demo 策略 | 备注 |
|------|------|----------|-----------|-----------|------|-----------|------|
| 测试框架 | **pytest** | >= 8.0 | Python 生态标准测试框架；支持 async 测试（pytest-asyncio）；Mock 工具层便于单元测试 | — | 无 | 真实实现 | Demo 阶段建议覆盖关键路径（MAC 漂移完整闭环）的集成测试 |
| LangGraph 调试 | **LangGraph Studio** | latest | 可视化状态机节点流转和 State 变化；调试条件边路由和 Interrupt 行为；Demo 演示效果好 | REQ-FUNC-006 | 需要 LangSmith 账户（免费层级可用） | 可选 | 非必需，但强烈推荐用于 Demo 演示 |

---

## 技术风险汇总

### 高风险 (High)

| 编号 | 风险描述 | 影响模块 | 缓解措施 |
|------|---------|---------|---------|
| RISK-001 | **DeepSeek API 不提供 Embedding 端点**：Chroma 需要 embedding 模型生成文档向量，若 DeepSeek 无此端点需切换到 OpenAI API 或本地模型 | MOD-008, MOD-013 | 设计 embedding_provider 抽象层，支持切换 OpenAI / DeepSeek / 本地 sentence-transformers；默认使用 OpenAI text-embedding-3-small 作为首选 |
| RISK-002 | **LLM 输出格式不稳定**：DeepSeek-chat 在 `fill_template_params` 端点可能不严格遵守 JSON Schema 约束，导致 OutputValidator 频繁拒绝 | MOD-006, MOD-009 | Prompt 工程强化（Few-shot 示例 + `response_format` 参数）；OutputValidator 增加格式修复层（尝试自动修复常见 JSON 错误如尾部逗号、未闭合引号）；降级方案：拒绝后重试 1 次 |
| RISK-003 | **LangGraph Interrupt 机制在异步环境中行为不确定**：LangGraph 官方文档对 async Interrupt 的支持仍有演进 | MOD-003 | Demo 阶段使用同步 StateGraph 执行（非 async）；在 FastAPI 的线程池中运行 LangGraph（`run_in_executor`） |

### 中风险 (Medium)

| 编号 | 风险描述 | 影响模块 | 缓解措施 |
|------|---------|---------|---------|
| RISK-004 | **LangChain/LangGraph/Chroma 版本兼容性**：三个包的版本矩阵复杂，可能出现在特定版本组合下的 bug | MOD-003, MOD-008 | 使用 `requirements.txt` 精确锁定版本；在 CI 中做版本兼容性测试；关注各包的 changelog |
| RISK-005 | **TP-Link 交换机命令与 Cisco IOS 存在差异**：某些命令的输出格式或参数名可能不一致，导致真实实现时的适配成本 | MOD-010, MOD-011 | 策略模式隔离（Mock 和 TpLink 实现独立）；预留 device_model 字段用于驱动选择；初期验证 TP-Link 特定型号的命令集 |
| RISK-006 | **Jinja2 沙箱安全性**：默认 Jinja2 环境可执行任意 Python 表达式，如果模板文件被恶意篡改可能导致代码注入 | MOD-007 | 使用 `SandboxedEnvironment` 限制模板能力；模板文件只读权限；Git 版本控制 + diff 审查 |

### 低风险 (Low)

| 编号 | 风险描述 | 影响模块 | 缓解措施 |
|------|---------|---------|---------|
| RISK-007 | **Chroma SQLite 持久化在不同 Linux 发行版的兼容性**：文件锁行为可能导致并发访问问题 | MOD-008 | Demo 单进程运行不存在并发问题；Chroma 文档化的 Linux 支持良好 |
| RISK-008 | **APScheduler 在 FastAPI 生命周期管理中的优雅启停**：scheduler 需要随应用启动和关闭 | MOD-002 | FastAPI lifespan context manager 中管理 scheduler 启动/关闭 |
| RISK-009 | **Python 3.11 中 `TaskGroup` 异常传播行为**：子任务异常可能导致其他任务被取消 | MOD-002 | 巡检任务中使用 `asyncio.gather(return_exceptions=True)` 代替 TaskGroup；单个设备诊断失败不影响其他设备 |

---

## 依赖版本锁定建议 (requirements.txt 草案)

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

# 模板
jinja2>=3.1.0,<4.0.0

# 调度
apscheduler>=3.10.0,<4.0.0

# 网络设备（后期启用）
# netmiko>=4.0.0,<5.0.0
# napalm>=4.0.0,<5.0.0

# 校验
jsonschema>=4.20.0,<5.0.0

# 日志
loguru>=0.7.0,<1.0.0

# 测试
pytest>=8.0.0,<9.0.0
pytest-asyncio>=0.23.0,<1.0.0
```

---

## Demo 实现策略汇总

| 层次 | 组件 | Demo 策略 | 对应模块 |
|------|------|-----------|---------|
| 触发层 | Webhook 端点 | **真实实现** (FastAPI + Uvicorn) | MOD-001 |
| 触发层 | Mock 告警推送脚本 | **真实实现** (httpx + 内嵌样本数据) | 独立工具 |
| 触发层 | 定时巡检调度 | **真实实现** (APScheduler) | MOD-002 |
| 编排层 | LangGraph 状态机 | **真实实现** (14 节点 + 4 条件边 + Interrupt) | MOD-003 |
| 编排层 | 告警归一化 + 去重 | **真实实现** | MOD-004 |
| 编排层 | 14 个节点处理函数 | **真实实现** | MOD-005 |
| LLM 层 | DeepSeek API 调用 | **真实 API 调用** | MOD-006 |
| LLM 层 | 命令模板引擎 | **真实实现** (Jinja2 + YAML 模板) | MOD-007 |
| LLM 层 | RAG 知识库 | **真实 Chroma 运行**（知识条目为 Mock 示例数据） | MOD-008 |
| LLM 层 | LLM 输出校验 | **真实实现** (jsonschema + 正则) | MOD-009 |
| 工具层 | SwitchConfigTool | **Mock 实现**（预留 TP-Link 策略类） | MOD-010 |
| 工具层 | SwitchDiagTool | **Mock 实现**（预留 TP-Link 策略类） | MOD-011 |
| 工具层 | BackupTool | **Mock 实现**（预留 TP-Link 策略类） | MOD-012 |
| 工具层 | KnowledgeBaseTool | **真实实现**（委托 MOD-008） | MOD-013 |
| 安全层 | 风险评估 | **真实实现**（规则引擎） | MOD-014 |
| 安全层 | 审计日志 | **真实实现** (loguru) | MOD-015 |
| 基础设施 | 配置管理 | **真实实现** (PyYAML + dotenv) | MOD-016 |
