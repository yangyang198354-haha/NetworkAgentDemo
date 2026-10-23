# Project Profile — NetworkAgentDemo

> 由 pm-orchestrator 在无人值守模式下扫描仓库生成的**初稿**，尚未经用户确认，**不得据此启动 SDLC 流程**。
> 目标位置是 `.claude/agents/project_profile.md`，但生成时 `.claude/` 不可写，所以暂存在这里。请用户确认后移动过去，并把 status 改为 APPROVED。
> 每条事实后的 `〔出处〕` 为来源；"未知"/"待确认"项须用户补充后才能改为 APPROVED。
> 本文件不含任何密码、令牌、私钥（只写凭据存放位置）。

<file_header>
  <author_agent>pm-orchestrator(draft)</author_agent>
  <timestamp>2026-10-22T18:18:37+08:00</timestamp>
  <project_name>NetworkAgentDemo</project_name>
  <version>1.0.0</version>
  <status>DRAFT</status>
</file_header>

## P1. 项目概况
- 一句话描述：基于 LangGraph 的网络自动化 Agent（Demo v0.2.0），自动化"告警→诊断→修复→验证→关闭"流程，含 FastAPI 后端、Vue 3 Web UI 与 systemd 定时巡检 〔CLAUDE.md "Project Overview"〕
- 技术栈：

  | 层 | 技术 | 版本 |
  |---|---|---|
  | 语言 | Python | 3.11+（CI 矩阵 3.11 / 3.12）〔CLAUDE.md；.github/workflows/test.yml〕 |
  | 编排 | langgraph / langchain | >=0.2,<0.3 / >=0.3,<0.4 〔project_workspace/requirements.txt〕 |
  | Web | fastapi / uvicorn | >=0.110,<1.0 / >=0.27,<1.0 〔requirements.txt〕 |
  | 数据 | SQLAlchemy 2.0 + SQLite（WAL） | >=2.0,<3.0 〔requirements.txt；CLAUDE.md "Data layer"〕 |
  | LLM / RAG | DeepSeek API（chat，经 openai SDK）+ ChromaDB + OpenAI embeddings | openai>=1.30,<2；chromadb>=0.5,<0.6 〔requirements.txt；CLAUDE.md〕 |
  | 设备 | paramiko（模拟器 SSH + 真机回退链）；Windows OpenSSH → plink → paramiko 回退 | paramiko>=3.4,<4 〔requirements.txt；CLAUDE.md "Device tools"〕 |
  | 鉴权 | python-jose（JWT）、passlib[bcrypt]、cryptography | 〔requirements.txt〕 |
  | 前端 | Vue 3 + TypeScript + Vite 5 + Element Plus + ECharts + Pinia + Vue Router | vue ^3.4；vite ^5.4 〔project_workspace/webui/package.json〕 |
- 运行形态：单进程 Web 服务（FastAPI，端口 8001，模块化分层单体）+ CLI（`src.inspection_cli`，由 systemd timer 触发）〔CLAUDE.md "Architecture"〕
- 权威说明文档：`CLAUDE.md`（仓库根）；历史设计文档见 `project_workspace/{requirements,architecture,development,testing,deployment,docs}/` 〔git ls-files〕

## P2. 文档工作区
- `docs_root`: **待确认**。缺省值为 `project_workspace/{project_name}/`。
  - 现状：历史 SDLC 文档直接放在 `project_workspace/requirements/`、`architecture/` 等目录，文件名带特性前缀（如 `inspection_systemd_*`、`webui_*`）；部分特性用独立子目录（`project_workspace/real_device_e2e/`、`project_workspace/real_device_panel/`）〔git ls-files〕
  - 旧的 `project_workspace/phase_status.md`（PARTIAL_FLOW，非本套件格式）位于 `project_workspace/` 根，其文件头声明的路径却是 `project_workspace/NetworkAgentDemo/phase_status.md` 〔project_workspace/phase_status.md:1-10〕
  - 建议（待确认）：新需求使用 `project_workspace/{feature_name}/`（与 real_device_panel 先例一致），避免覆盖历史文档与旧 phase_status.md。
- `docs_layout`: nested（建议，与 real_device_e2e/ 先例一致；待确认）
- 是否入库: 是（历史文档均已入 git）〔git ls-files〕

## P3. 代码布局
- `code_mode`: in-repo
- 代码目录：

  | 组件 | 目录 | 语言 |
  |---|---|---|
  | 后端 | `project_workspace/src/`（api, database, llm, models, orchestration, security, services, simulator, systemd, tools, trigger） | Python |
  | 前端 | `project_workspace/webui/src/` | TypeScript / Vue |
  | 配置 | `project_workspace/config/config.yaml` | YAML |
  | 模板/资源 | `project_workspace/resources/templates/`（修复模板 YAML、systemd unit `.j2`）、`resources/knowledge/` | YAML / Jinja2 / JSON |
  〔ls project_workspace/src；git ls-files resources〕
- 测试位置约定：

  | 组件 | 新测试放在 | 命名 | 测试基类/框架 |
  |---|---|---|---|
  | 后端 | `project_workspace/tests/` | `test_{feature}_{unit,integration,e2e}.py`（从现有文件推断） | pytest + pytest-asyncio；markers `slow`、`e2e`（`--strict-markers`）〔pytest.ini〕 |
  | 前端 | 未知（仓库中未发现前端测试） | — | — |
- 不可修改的目录 / 约定：
  - `project_workspace/webui/node_modules/`、`webui/dist/`、`auto-imports.d.ts`、`components.d.ts`（生成产物，已 gitignore）〔.gitignore〕
  - **不得为修测试导入而改 `src/`**：已知源码缺陷 D-001、D-002 由 `tests/conftest.py` 的 `sys.meta_path` 钩子在测试时打补丁 〔CLAUDE.md "Testing"；tests/conftest.py:4-8〕
  - `.github/workflows/test.yml` 在仓库根与 `project_workspace/.github/workflows/` 各有一份（目前内容一致）；GitHub 只执行仓库根那份 〔diff 无差异〕

## P4. 命令（全部在开发机/CI 上运行，严禁连生产）
| 用途 | 工作目录 | 命令 | 备注 |
|---|---|---|---|
| 环境准备 | project_workspace | `pip install -r requirements.txt`；`cp .env.example .env` | 本次扫描环境**未安装 pytest 等依赖**（`ModuleNotFoundError: pytest`），按协议不安装 〔CLAUDE.md；实测〕 |
| 静态检查 / 编译检查 | project_workspace/webui | `npm run build`（包含 vite 构建；没有独立的 lint/type-check 脚本） | 后端没有 lint 配置（未发现 ruff/flake8/mypy/pyproject）〔package.json；git ls-files〕 |
| 单元测试 | project_workspace | `python -m pytest tests/ -v --tb=short --ignore=tests/test_e2e_webui.py --ignore=tests/test_e2e_full.py --ignore=tests/test_inspection_systemd_e2e.py --ignore=tests/test_e2e_inspection_config_refactor.py --ignore=tests/test_simulator_e2e.py --ignore=tests/test_simulator_tools_e2e.py -k "not slow"` | 即 CI unit job；分层机制 = 文件名 + marker 〔CLAUDE.md；test.yml〕 |
| 集成测试 | project_workspace | `python -m pytest tests/test_integration.py tests/test_*_integration.py -v` | 推断（已包含在上面的单元命令中）；**待确认** |
| E2E 测试 | project_workspace | `python -m pytest tests/test_e2e_full.py -v -k "not slow"`（`BASE_URL` 指向目标服务） | CI 中 `BASE_URL` 默认指向**生产 VPS**。按协议 §L-4，子代理不得对生产运行；可连的非生产目标**未知**（本地 `python src/main.py` 起服务？）〔test.yml e2e job〕 |
| 全量回归 | project_workspace | `python -m pytest tests/ -v --tb=short`（去掉 `--ignore` 后会包含需要远端 VPS/模拟器的 e2e 文件） | 耗时未知 |
| 构建 | project_workspace/webui | `npm run build` → `webui/dist/` | 〔CLAUDE.md〕 |
| 启动服务 | project_workspace | `python src/main.py` | 〔CLAUDE.md〕 |
- 已知既有失败 / 基线来源：未知（没有基线文件；以改动前实跑为准）。已知源码缺陷 D-001/D-002 由 conftest 处理。
- 缺依赖时的处理：如实标 BLOCKED，不安装

## P5. 质量判定
- FULL_FLOW `gate_mode`: threshold — unit_pass 0.80 / integration_pass 0.90 / critical_path 1.00 / coverage_min 无（套件缺省，待确认）
- INCREMENTAL `gate_mode`: baseline — 零新增失败（套件缺省）
- `inferred_max`: 0.20（套件缺省）

## P6. 开发约定
- 数据迁移方式：**不使用 Alembic**（虽然在 requirements.txt 中）。启动时执行 `Base.metadata.create_all()`，增量列通过 `init_db` 中**幂等的 PRAGMA 检测 + `ALTER TABLE ADD COLUMN`** 辅助函数完成（如 `ensure_timeline_columns`、`_ensure_real_device_columns`），失败只记 warning 〔src/database/base.py:92-117〕
- 鉴权与权限模型：`/api/*` 需要 JWT（`/auth/login` 签发，`Authorization: Bearer`）；旧端点 `/webhook/alert`、`/approvals/*`、`/workflow/{id}/state`、`/health` 无鉴权 〔CLAUDE.md "API surface"〕；角色/权限细分未知
- 代码风格 / lint 规则：未发现配置（未知）
- 依赖管理：`requirements.txt` 使用版本区间（非精确 pin），无锁文件；前端 `package-lock.json` 被 gitignore 〔requirements.txt；.gitignore〕
- 其他必须遵守的约定：
  - 配置走 `config/config.yaml` + `ConfigManager`，环境变量优先（模式 `DEVICE_{NAME}_PASSWORD`）〔CLAUDE.md〕
  - 设备工具采用策略模式三后端：Mock（`use_mock=True`，CI/演示用）、TP-Link 真机客户端、本地模拟器 〔CLAUDE.md〕
  - LangGraph 用同步 `StateGraph` + `MemorySaver`，在后台线程执行；`interrupt_before=["human_approval"]` 〔CLAUDE.md〕
  - systemd 调用一律 `subprocess.run(..., shell=False)` 〔CLAUDE.md "systemd inspection"〕
  - 凭据存放位置：`project_workspace/.env`（键名见 `.env.example`：`DEEPSEEK_API_KEY`、`OPENAI_API_KEY`、`CONFIG_PATH`；部署文档另提到 JWT/加密密钥写入目标机 `.env`）〔.env.example；deployment/deployment_plan.md:131-150〕

## P7. 环境、CI 与部署
- 环境：

  | 环境 | 存在 | 访问方式（不含口令） | 部署需用户确认 | 备注 |
  |---|---|---|---|---|
  | dev/local | 是 | 本地 `python src/main.py`（端口 8001） | 否 | 历史部署文档显示开发机为 Windows（plink/pscp、`C:\...` 路径）〔real_panel_deployment_plan.md:23,150〕 |
  | staging | **未知**（未发现） | — | — | — |
  | production | 是 | 阿里云 ECS 47.109.197.217，SSH 用户 root（密钥认证，密钥在开发者本机 `~/.ssh/`）〔CLAUDE.md；verify_vps_cpu_mac_deploy.py〕 | **是** | 与 GenPlatform 共机 |
- 部署方式（**待确认，历史做法不一致**）：
  - 最近一次（real_device_panel）：目标机上 `git fetch origin master && git reset --hard origin/master` + `systemctl restart networkagent` 〔real_device_panel/deployment/real_panel_deployment_report.md:25,39,42〕
  - 更早：`git pull origin master`，或用 `pscp` 逐文件上传 〔deployment/deployment_plan.md:80-84；real_panel_deployment_plan.md:150-191〕
- 允许的部署策略：recreate（单机单进程，stop/restart systemd 服务）；没有支持 rolling/blue-green/canary 的基础设施 〔从部署文档推断〕
- 构建产物管理：无制品库；前端在目标机上 `npm run build` 〔deployment/deployment_plan.md:163〕
- 运行单元与"改什么需重启什么"：
  - `networkagent.service`（uvicorn `src.main:app`，端口 8001，`EnvironmentFile=.env`）——后端、前端 dist、配置改动后需 `systemctl restart networkagent` 〔deployment/deployment_plan.md:180-215〕
  - `networkagent-inspection.service` + `.timer`（巡检 CLI，由 `src/systemd/systemd_unit_manager.py` 从 `resources/templates/systemd/*.j2` 生成）——unit 模板改动需 `daemon-reload` 〔git ls-files resources〕
  - 前端改动需在目标机重新 `npm run build`
- 目标机上必须保留的本地状态：`.env`、`data/`（`webui.db` SQLite、chroma_db）、`logs/`、`/etc/systemd/system/networkagent*.{service,timer}`（均未入库或已 gitignore）〔.gitignore；deployment_plan.md〕
- 目标机目录：**待确认**——`systemctl show` 记录到的是 `WorkingDirectory=/opt/NetworkAgentDemo/project_workspace` 〔real_panel_deployment_report.md:37；verify_vps_cpu_mac_deploy.py `WS`〕，而旧计划写的是 `/opt/NetworkAgentDemo` 〔deployment_plan.md:191〕
- 回滚方式偏好：未知。历史做法：部署前 `cp -r /opt/NetworkAgentDemo /opt/NetworkAgentDemo.backup.<ts>`，回滚 = stop → 恢复备份目录 → start 〔real_panel_deployment_report.md:97；deployment_plan.md:63〕
- 部署后验证：`GET http://<host>:8001/health`（期望 200 healthy v0.2.0）、`systemctl is-active networkagent`、`journalctl -u networkagent` 〔real_panel_deployment_report.md:53〕；只读核验脚本先例：仓库根的 `verify_vps_cpu_mac_deploy.py`
- CI 系统与配置文件：GitHub Actions `.github/workflows/test.yml`（unit job：push/PR 到 master/main 时运行；e2e job：仅 `workflow_dispatch`，`BASE_URL` 取 secret `VPS_URL`）〔test.yml〕
- 部署相关配置文件：`resources/templates/systemd/networkagent-inspection.{service,timer}.j2`；`networkagent.service` 未入库（只存在于目标机和 deployment_plan.md 中）

## P8. 禁用项（门控时任一出现即 FAIL）
| 禁用的技术 / 操作 | 原因 |
|---|---|
| 触碰生产机 80（nginx）/ 8000（gunicorn+uvicorn）端口及 GenPlatform 服务 | 与 GenPlatform 共机，会导致其停机 〔real_panel_deployment_plan.md:92-99〕 |
| `pkill -f gunicorn` 等按名称模糊杀进程 | 会误杀 GenPlatform backend 〔real_panel_deployment_plan.md:97〕 |
| 为修测试导入问题修改 `src/`（D-001/D-002） | 已由 conftest 钩子处理 〔CLAUDE.md〕 |
| 重新引入 APScheduler | v0.2.0 已改为 systemd timer（REQ-INSP-017）〔requirements.txt 注释；CLAUDE.md〕 |
| 部署后验证/测试中对**真实交换机**执行写操作（未经授权） | 历史计划要求"部署后验证不得擅自写生产端口" 〔real_panel_deployment_plan.md:81〕 |
| `subprocess` 用 `shell=True` 调 systemctl | 约定 `shell=False` 〔CLAUDE.md〕（是否列为禁用项待确认） |
| 其他 | **待用户补充**（如：是否禁止在生产上 `git reset --hard`、是否禁止引入 Alembic） |

## P9. 版本控制与远程操作权限
- 分支策略：单分支 `master`（远端 `origin/master`），未见特性分支 〔git branch -a；git log〕；**待确认**
- 谁执行 commit / push：**未知** → 按协议缺省：子代理不执行，由主会话在用户确认后执行。`.claude/settings.json` 已对 `git push`、`ssh`、`scp` 设置 ask 权限 〔.claude/settings.json〕
- 子代理是否可 ssh / 部署：否（缺省）；E2 授权后 devops 可执行 P7 中的部署命令（待确认）
- 提交前必须通过的检查：未知；建议 = P4 的单元测试命令（与 CI unit job 相同）
- 提交信息风格：Conventional Commits（`fix(scope): …`、`feat(scope): …`、`refactor(scope): …`）〔git log --oneline〕

## P10. 额外必读（PM 填入 required_reading）
| Agent | 额外文件 |
|---|---|
| 所有 agent | `CLAUDE.md` |
| test-engineer | `project_workspace/pytest.ini`、`project_workspace/tests/conftest.py`、`project_workspace/testing/e2e_test_readme.md` |
| devops-engineer | `.github/workflows/test.yml`、`project_workspace/real_device_panel/deployment/real_panel_deployment_plan.md`（含 GenPlatform 共机禁区）、`project_workspace/real_device_panel/deployment/real_panel_deployment_report.md` |
| software-developer | `project_workspace/src/database/base.py`（迁移约定） |

（`.claude/skills/` 不存在，没有项目 skill。）

---

## 待用户确认的关键未知项
1. **工作区布局**：新需求的文档根用 `project_workspace/{feature_name}/`（nested）可以吗？旧的 `project_workspace/phase_status.md` 是否保留为历史、不由新流程接管？
2. **测试命令**：集成测试是否有单独的命令/目录？E2E 可以连哪个**非生产**目标（本地起服务？模拟器？）——CI 的 e2e job 默认指向生产 VPS。有没有已知既有失败的基线？
3. **环境与部署**：是否只有 local + production（没有 staging）？生产部署的标准方式是 `git fetch + reset --hard` 还是 `git pull`？目标机工作目录到底是 `/opt/NetworkAgentDemo` 还是 `/opt/NetworkAgentDemo/project_workspace`？回滚偏好是什么？
4. **禁用项**：P8 表格是否完整？是否禁止在生产上 `git reset --hard`、禁止引入 Alembic？
5. **commit / push**：由谁执行？是否允许直推 master？


## 沙箱试运行建议（2026-10-22，非用户确认；请逐项核对，确认后把 status 改为 APPROVED）
> 以下是沙箱测试时为跑通流程采用的选择，供确认时参考；基线数字来自测试机，换机器后以实跑为准。
- docs_root = `project_workspace/{project_name}/`（采纳初稿建议，与 real_device_e2e 先例一致），docs_layout = nested；不要改动 `project_workspace/` 根下的历史文档和旧 phase_status.md。
- 测试命令以 CI 为准（P4 单元命令，在 `project_workspace/` 下运行）；基线（2026-10-22 实跑）：561 passed, 1 xfailed。E2E 测试默认连生产，子代理不得运行。
- 只有 local + production（ECS），没有 staging；部署方式按 P7 推断（git pull + 重启服务），本次测试不授权部署。
- 没有迁移工具：新增列不会自动加到已有 SQLite 表，涉及表结构变更时必须在设计中写明处理方式。
- commit/push 由主会话在用户确认后执行；子代理不执行。
- 禁用项按 P8 确认。
