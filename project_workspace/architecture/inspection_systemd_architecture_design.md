<file_header>
  <author_agent>sub_agent_system_architect</author_agent>
  <timestamp>2026-07-12T00:00:00Z</timestamp>
  <project_name>NetworkAgentDemo</project_name>
  <version>0.2.0</version>
  <input_files>
    <file>requirements/inspection_systemd_requirements.md</file>
    <file>requirements/inspection_systemd_user_stories.md</file>
    <file>architecture/architecture_design.md (v0.1.0 参考)</file>
    <file>architecture/module_design.md (v0.1.0 参考)</file>
    <file>architecture/tech_stack.md (v0.1.0 参考)</file>
  </input_files>
  <phase>PHASE_INSP_03</phase>
  <status>APPROVED</status>
</file_header>

# 巡检机制 systemd 重构 — 架构设计文档

---

## 架构概览

### 重构范围与边界

v0.2.0 巡检机制重构的核心目标是将巡检调度引擎从 APScheduler（Python BackgroundScheduler）迁移至 Linux systemd timer + service 架构。本次重构严格限定于**巡检调度机制**，不涉及告警处理流程（LangGraph 工作流）、设备 SSH 连接方式、Web UI 其他功能模块的变更。

### 架构风格：模块化分层单体（保持 v0.1.0 风格）

v0.2.0 保持 v0.1.0 的**模块化分层单体**架构风格不变。巡检相关变更为：

- **触发层**：MOD-002 (InspectionScheduler) 废弃 APScheduler，替换为 systemd timer + service + CLI 入口
- **安全与基础设施层**：新增 systemd 交互模块（systemd_unit_manager、systemctl_executor）
- **Web 层**：MOD-WEB-001 (inspection_router) 增强 6 个新端点
- **数据层**：MOD-WEB-004 (inspection_repository) 增强配置项和 unit 文件生成触发

### 关键架构决策速览

| ADR ID | 决策主题 | 选择方案 | 触发需求 |
|--------|---------|---------|---------|
| ADR-INSP-001 | 巡检调度引擎 | systemd timer + service | REQ-INSP-014~017, REQ-INSP-NF-004 |
| ADR-INSP-002 | systemctl 权限管理 | sudoers (/etc/sudoers.d/networkagent) | REQ-INSP-NF-003, PM Q-INSP-001/002 |
| ADR-INSP-003 | Unit 文件生成方式 | Jinja2 模板引擎 | REQ-INSP-002, REQ-INSP-015/016 |
| ADR-INSP-004 | CLI 巡检入口模块设计 | 独立进程（systemd service 调用） | REQ-INSP-014, REQ-INSP-NF-004, PM Q-INSP-003 |
| ADR-INSP-005 | systemd 状态查询实现 | systemctl show + 子进程解析 | REQ-INSP-004, REQ-INSP-005 |
| ADR-INSP-006 | 配置 SQLite → systemd 同步 | 实时同步（配置保存时立即同步） | REQ-INSP-002, REQ-INSP-003, REQ-INSP-013 |

---

## 架构决策记录（ADRs）

---

### ADR-INSP-001: systemd timer/service 进程隔离架构

- **Status**: Accepted
- **Context**:
  - v0.1.0 使用 APScheduler BackgroundScheduler 在 Web 进程内执行定时巡检，存在以下问题：
    - 重启 Web 服务即丢失定时器状态（内存态 job store），不符合 REQ-INSP-NF-004（进程隔离）要求
    - 无法通过 systemd 管理巡检生命周期（start/stop/restart/enable/disable），不符合 REQ-INSP-006/007
    - 巡检进程与 Web 进程耦合，巡检 CPU/内存消耗影响 Web API 响应
  - REQ-INSP-014 要求提供独立的 CLI 巡检执行入口 `python3.11 -m src.inspection_cli run`
  - REQ-INSP-015/016 定义了 systemd service 和 timer unit 文件模板
  - REQ-INSP-017 要求废弃 APScheduler 调度器
  - REQ-INSP-NF-001 要求 timer 触发精度 ≤5 秒（AccuracySec=1s）
  - REQ-INSP-NF-002 要求 service 故障自动恢复（Restart=on-failure）
  - REQ-INSP-NF-004 要求巡检进程与 Web 进程完全隔离
  - REQ-INSP-NF-007 要求巡检日志输出至 systemd journal
  - PM 已确认 Q-INSP-003（手动触发统一用 systemctl start）、Q-INSP-006（无需迁移 APScheduler job_id 机制）

- **Options**:
  - **Option A: systemd timer + service（推荐方案）**
    - 描述：定义一个 systemd timer unit（networkagent-inspection.timer，OnUnitActiveSec=巡检间隔秒数，Persistent=true）和一个 oneshot service unit（networkagent-inspection.service，ExecStart=python3.11 -m src.inspection_cli run）。timer 按间隔触发 service 执行巡检 CLI。Web 进程通过 sudo systemctl 命令管理 timer/service 生命周期。
    - 优点：OS 级持久化调度，重启不丢失；进程完全隔离（独立 PID 空间），满足 REQ-INSP-NF-004；systemd 原生支持 enable/disable/start/stop/restart，直接满足 REQ-INSP-006/007；日志自动集成 journald（REQ-INSP-NF-007）；Persistent=true 支持系统重启后补偿执行；Restart=on-failure 满足 REQ-INSP-NF-002；AccuracySec=1s 满足 REQ-INSP-NF-001；Type=oneshot 契合一次性巡检任务语义；多组巡检策略可通过多组 timer+service 扩展（PM Q-INSP-006）。
    - 缺点：强依赖 Linux systemd，Windows/macOS 开发环境不可用（PM Q-INSP-003 已决策不做进程内降级，报错即可）；需要配置 sudoers 权限（另见 ADR-INSP-002）；timer 的最小精度受 systemd 限制（默认 1 分钟，需 AccuracySec 调优）。
  - **Option B: 保持 APScheduler（v0.1.0 现状）**
    - 描述：继续使用 APScheduler BackgroundScheduler 在 Web 进程内以 daemon 线程运行定时巡检。通过 APScheduler 的 SQLAlchemyJobStore 将 job 持久化到 SQLite 实现重启恢复。
    - 优点：跨平台兼容（Windows/macOS/Linux）；纯 Python 实现，无需 OS 级配置；v0.1.0 已有成熟实现，改动最小。
    - 缺点：巡检与 Web 进程不隔离，违反 REQ-INSP-NF-004；APScheduler SQLAlchemyJobStore 的持久化可靠性不如 systemd（job 状态更新存在竞态窗口）；无法通过 systemctl 管理巡检生命周期，不满足 REQ-INSP-006/007；缺少 journald 级别的日志集成（REQ-INSP-NF-007）；PM 已明确要求迁移至 systemd（REQ-INSP-017），保持 APScheduler 违反核心需求。
  - **Option C: cron + 独立脚本**
    - 描述：使用 Linux cron 定时触发独立 Python 脚本执行巡检。Web 进程通过编辑 crontab 管理巡检计划。
    - 优点：比 systemd 更轻量；跨 Linux 发行版通用；进程隔离良好（cron 触发独立进程）。
    - 缺点：cron 最小精度为 1 分钟，不满足 REQ-INSP-NF-001 的 ±5 秒精度要求；cron 无原生 enable/disable 机制（需要注释/取消注释 crontab 行）；无 on-failure 自动重启能力（不满足 REQ-INSP-NF-002）；缺少 Persistent=true 等效机制（系统关机期间的巡检不会补偿）；crontab 编辑容易出错且难以通过 API 管理；PM 明确要求 systemd 架构（REQ-INSP-015/016 定义了 systemd unit 文件模板）。

- **Decision**: 选择 **Option A（systemd timer + service）**。

  理由：
  1. **需求直接对齐**：Option A 精确满足所有 v0.2.0 巡检需求——OS 级持久化（REQ-INSP-NF-004）、生命周期管理（REQ-INSP-006/007）、日志集成（REQ-INSP-NF-007）、故障恢复（REQ-INSP-NF-002）、触发精度（REQ-INSP-NF-001）。
  2. **PM 决策锚定**：PM 已通过 Q-INSP-003（手动触发用 systemctl start）、Q-INSP-006（多组策略用多组 timer+service）确认 systemd 方案方向，Option B/C 与 PM 决策方向矛盾。
  3. **进程隔离价值**：Option A 的进程隔离解决了 v0.1.0 最核心的痛点——Web 重启丢失巡检状态、巡检负载影响 Web 响应。两个进程仅通过 SQLite 共享数据，耦合度最低。
  4. **Option B 否决**：保持 APScheduler 无法实现 REQ-INSP-NF-004 进程隔离，且 PM 已通过 REQ-INSP-017 明确要求废弃 APScheduler。
  5. **Option C 否决**：cron 精度（1 分钟）不满足 REQ-INSP-NF-001（±5 秒），且 PM 在 REQ-INSP-015/016 中已明确指定 systemd unit 文件模板，选择 cron 违反架构要求。

- **Consequences**:
  - **正向**：
    - 完整支撑 REQ-INSP-006（service 生命周期控制）、REQ-INSP-007（timer 启用/禁用）、REQ-INSP-014（CLI 入口）、REQ-INSP-015/016（unit 文件定义）、REQ-INSP-017（APScheduler 废弃）、REQ-INSP-NF-001（触发精度）、REQ-INSP-NF-002（故障恢复）、REQ-INSP-NF-004（进程隔离）、REQ-INSP-NF-007（journald 日志）。
    - US-INSP-008 的 7 条验收标准（AC-INSP-008-01 至 07）全部由 systemd timer + service 原生支撑。
    - systemd 作为 Linux 标准组件，无需安装额外依赖，运维人员可直接使用 `systemctl status`、`journalctl -u` 等标准命令。
  - **负向**：
    - 强依赖 Linux systemd，开发环境（Windows/macOS）无法运行定时巡检功能。PM 已通过 Q-INSP-003 确认不做进程内降级，开发环境需报错"请先配置巡检服务"。
    - 需要配置 sudoers 权限，增加了部署步骤（另见 ADR-INSP-002）。
    - systemd 学习曲线：开发者需要理解 timer/service unit 文件语法、systemctl 命令体系、journald 日志查询。

---

### ADR-INSP-002: systemctl 权限管理方案

- **Status**: Accepted
- **Context**:
  - REQ-INSP-NF-003（Must Have，强制等级 HIGH）要求 Web 进程调用 systemctl 命令（daemon-reload, start, stop, restart, enable, disable, show）时需要 root 或 sudo 权限。
  - PM 已确认 Q-INSP-001：选择 sudoers 方案（/etc/sudoers.d/networkagent），授权 Web 进程用户免密码执行特定 systemctl 命令。
  - PM 已确认 Q-INSP-002：Web 进程和巡检 service 统一使用 **networkagent** 用户。
  - REQ-INSP-NF-003 的 AC-INSP-NF-003-03 要求命令注入防护（subprocess.run 使用 shell=False + 参数列表形式）。
  - 部署环境为 Alibaba Cloud ECS (47.109.197.217)，运行 Linux + systemd。

- **Options**:
  - **Option A: sudoers 精确命令白名单（/etc/sudoers.d/networkagent）— PM 已确认**
    - 描述：在 `/etc/sudoers.d/networkagent` 文件中配置 `networkagent ALL=(root) NOPASSWD: /usr/bin/systemctl * networkagent-inspection.*`，授权 networkagent 用户免密码执行针对 networkagent-inspection 相关 unit 的 systemctl 命令。Web 进程使用 `sudo systemctl <action> networkagent-inspection.<unit>` 调用。
    - 优点：权限控制精确——仅授权特定 unit 的 systemctl 操作，无法操作其他系统服务；不需要密码交互，适合 API 调用场景；sudoers 是 Linux 标准权限管理机制，运维人员熟悉；部署简单，一个配置文件即可；满足 REQ-INSP-NF-003 AC-INSP-NF-003-01 的验收标准。
    - 缺点：sudoers 配置需要 root 权限初始化（一次性部署操作）；sudoers 语法错误可能导致 sudo 完全不可用（需用 visudo 校验）；命令白名单模式（`networkagent-inspection.*`）需要确保 systemctl 参数中不出现非预期的 glob 匹配。
  - **Option B: polkit（PolicyKit）规则**
    - 描述：通过 polkit 定义 JavaScript 规则文件（`/etc/polkit-1/rules.d/50-networkagent.rules`），授权 networkagent 用户执行 `org.freedesktop.systemd1.manage-units` action。
    - 优点：比 sudoers 更细粒度——可以控制到特定 unit 文件的特定 action（如只允许 start/stop，不允许 enable/disable）；polkit 规则支持条件判断（如时间限制、登录会话限制）。
    - 缺点：polkit 规则编写复杂度高于 sudoers（需要理解 D-Bus action 命名空间）；调试困难——polkit 拒绝访问时的错误信息不如 sudo 直观；ECS 默认镜像可能未预装 polkit 或规则目录；v0.2.0 Demo 阶段权限需求简单（只需 systemctl 基本操作），polkit 过度设计。
  - **Option C: Web 进程以 root 用户运行**
    - 描述：FastAPI Web 进程直接以 root 用户运行，无需任何权限配置即可调用 systemctl。
    - 优点：零权限配置，最简单。
    - 缺点：严重违反最小权限原则（least privilege）；Web 进程被攻破将导致整个服务器被控制；REQ-INSP-NF-003 的验收标准明确要求"未配置权限时返回友好错误"——这要求 Web 进程以非 root 运行；**不可接受的安全实践**。

- **Decision**: 选择 **Option A（sudoers 精确命令白名单）**。

  理由：
  1. **PM 决策锚定**：PM 已通过 Q-INSP-001 明确选择 sudoers 方案，Q-INSP-002 明确使用 networkagent 用户。架构决策必须服从 PM 的最终裁决。
  2. **需求对齐**：Option A 精确满足 REQ-INSP-NF-003 的全部验收标准——正确配置后命令成功（AC-INSP-NF-003-01）、未配置时友好报错（AC-INSP-NF-003-02）、命令注入防护通过 subprocess.run(shell=False) 实现（AC-INSP-NF-003-03）。
  3. **安全与简洁平衡**：sudoers 白名单模式在安全性和实现复杂度之间取得平衡。仅授权 `networkagent-inspection.*` 相关的 systemctl 操作，不能操作其他系统服务。Option B (polkit) 的复杂度远超 Demo 需求。Option C (root) 违反安全底线，直接否决。
  4. **运维友好**：sudoers 是 Linux 运维人员的基本技能，文档和社区支持丰富。部署脚本中一条 `echo '...' > /etc/sudoers.d/networkagent` 即可完成配置。

- **Consequences**:
  - **正向**：
    - 完整支撑 REQ-INSP-NF-003（权限管理）的全部验收标准。
    - Web 进程以非特权用户（networkagent）运行，遵循最小权限原则。
    - systemctl_executor 模块（MOD-INSP-002）封装 sudo+systemctl 调用逻辑，上层模块无需关心权限细节。
  - **负向**：
    - 部署时需要 root 权限执行一次性 sudoers 配置（`visudo -c -f /etc/sudoers.d/networkagent` 语法校验 + 部署）。
    - systemctl_executor 需要在命令前加 `sudo` 前缀，命令构建逻辑需处理 sudo 的特殊行为（如 SUDO_ASKPASS、环境变量继承）。
    - 如果运维人员错误配置 sudoers（如 glob 匹配过宽），可能引入安全风险。需在文档中明确推荐的 sudoers 配置格式。

---

### ADR-INSP-003: Unit 文件生成方式

- **Status**: Accepted
- **Context**:
  - REQ-INSP-002 要求配置保存时自动生成 `/etc/systemd/system/networkagent-inspection.service` 和 `.timer` 两个 unit 文件。
  - REQ-INSP-013 要求 SQLite 配置变更后同步至 systemd unit 文件（interval_minutes → OnUnitActiveSec，timeout_seconds → TimeoutStopSec）。
  - REQ-INSP-015/016 定义了 service 和 timer unit 文件的关键配置项和模板结构。
  - US-INSP-002 AC-INSP-002-03 要求生成的 unit 文件可通过 `systemd-analyze verify` 语法校验。
  - PM 已确认 Q-INSP-004：WorkingDirectory 从环境变量 `NETWORKAGENT_HOME` 读取。
  - PM 已确认 Q-INSP-005：Demo 阶段暂不配置 MemoryLimit/CPUQuota 资源限制。
  - v0.1.0 的 MOD-007 (TemplateEngine) 已使用 Jinja2 渲染 CLI 命令模板，团队熟悉 Jinja2 语法。

- **Options**:
  - **Option A: Jinja2 模板引擎（推荐方案）**
    - 描述：将 systemd unit 文件定义为 Jinja2 模板（`.service.j2` 和 `.timer.j2`），模板中通过 `{{ working_directory }}`、`{{ timeout_seconds }}`、`{{ on_unit_active_sec }}`、`{{ user }}` 等变量占位。渲染引擎读取 SQLite 配置和环境变量，填充模板变量，输出完整的 unit 文件内容。模板文件存放在项目 `resources/templates/systemd/` 目录。
    - 优点：模板与数据分离——unit 文件结构在模板中清晰定义，配置值从 SQLite 动态注入；Jinja2 条件渲染支持可选配置段（如 `{% if memory_limit %}MemoryLimit={{ memory_limit }}{% endif %}`，为未来扩展预留）；与 v0.1.0 MOD-007 使用同一模板引擎，技术栈一致；生成的 unit 文件内容可通过单元测试验证（渲染后对比预期输出）；模板语法简单，systemd unit 文件的 INI 格式与 Jinja2 的 `{{ }}` 语法无冲突。
    - 缺点：需要管理两套模板文件（service.j2 + timer.j2），增加维护负担；Jinja2 默认环境可能对 systemd unit 文件中的 `%` 符号（如 `%i`、`%n` 等 systemd 说明符）产生误解析——需要使用 `{% raw %}...{% endraw %}` 包裹或配置 Jinja2 的 `block_start_string`/`variable_start_string`；渲染错误（如变量缺失）只能在文件写入后通过 `systemd-analyze verify` 发现。
  - **Option B: Python 字符串拼接（f-string / format）**
    - 描述：在 Python 代码中使用 f-string 或多行字符串的 `.format()` 方法直接构建 unit 文件内容，将配置值嵌入字符串中。
    - 优点：零额外依赖，实现最简单；代码中即可看到完整 unit 文件内容，无需切换模板文件。
    - 缺点：模板内容与代码耦合——unit 文件结构散落在 Python 字符串中，修改 unit 配置项需要改代码；多行字符串处理 systemd unit 文件的缩进和换行容易出错；缺少模板的变量校验机制，变量缺失可能导致畸形的 unit 文件；不符合 REQ-INSP-002 备注中"需使用模板化方式（非字符串拼接）"的明确要求。**需求文档已明确排除此方案**。
  - **Option C: 配置管理工具（Ansible template / systemd-firstboot）**
    - 描述：使用 Ansible 的 `template` 模块或 `systemd-firstboot` 命令生成 unit 文件。
    - 优点：Ansible 模板功能强大，支持条件、循环、变量继承；systemd-firstboot 是 systemd 官方工具。
    - 缺点：引入 Ansible 依赖使得 Demo 部署复杂度剧增（需要安装 Ansible + 维护 playbook）；systemd-firstboot 主要用于系统首次启动时的初始化配置，不适合运行时动态生成；Web 进程内嵌 Ansible 调用不符合轻量级 Demo 定位；过度设计。

- **Decision**: 选择 **Option A（Jinja2 模板引擎）**。

  理由：
  1. **需求明确要求**：REQ-INSP-002 备注中明确要求"Unit 文件生成需使用模板化方式（非字符串拼接），确保格式正确"。Option B 直接违反此要求，不可选。
  2. **技术栈一致性**：v0.1.0 已使用 Jinja2 作为命令模板引擎（MOD-007 TemplateEngine），团队熟悉 Jinja2 语法。复用同一技术栈降低学习成本和维护负担。
  3. **可测试性**：模板渲染是纯函数（输入：模板 + 变量 → 输出：文本），易于单元测试。每个模板变量组合都可以通过 pytest 参数化测试验证输出正确性。
  4. **扩展性**：Jinja2 的条件渲染支持未来扩展（如 PM 后续决定启用 MemoryLimit/CPUQuota，只需在模板中加 `{% if %}` 段落，不修改渲染引擎代码）。
  5. **systemd 说明符处理**：Jinja2 对 `%` 符号的误解析风险可通过以下方式消除——systemd unit 文件的 `%i`、`%n` 等说明符在当前需求中不需要使用（WorkingDirectory 和 User 直接填写具体值），若未来需要可在模板中使用 `{% raw %}` 包裹或自定义 Jinja2 分隔符。

- **Consequences**:
  - **正向**：
    - 完整支撑 REQ-INSP-002（unit 文件生成）、REQ-INSP-013（配置同步）、REQ-INSP-015/016（unit 文件定义）、US-INSP-002 AC-INSP-002-03（systemd-analyze verify 语法校验）。
    - MOD-INSP-001 (systemd_unit_manager) 可封装 `render_service_template(config) → str` 和 `render_timer_template(config) → str` 两个纯函数，测试友好。
    - 模板文件存放在 `resources/templates/systemd/`，与 v0.1.0 的 `resources/templates/` 目录结构一致。
  - **负向**：
    - 需要额外处理 Jinja2 对 systemd 说明符（`%i`、`%n`、`%N` 等）的兼容性。当前设计不需要这些说明符，但需在模板文件中添加注释提醒未来维护者。
    - Jinja2 版本需要与 v0.1.0 的 MOD-007 保持一致（Jinja2 >= 3.1），需验证依赖兼容性。

---

### ADR-INSP-004: CLI 巡检入口模块设计

- **Status**: Accepted
- **Context**:
  - REQ-INSP-014 要求提供独立的 CLI 巡检执行入口 `python3.11 -m src.inspection_cli run`，供 systemd service 调用。
  - REQ-INSP-017 要求从 inspection_scheduler.py 中提取 `run_inspection_once()` 核心逻辑并迁移至 CLI 模块。
  - REQ-INSP-NF-004 要求巡检进程与 Web 进程完全隔离（独立 PID、独立内存空间、独立生命周期）。
  - REQ-INSP-NF-005 要求 CLI 不监听任何网络端口。
  - PM 已确认 Q-INSP-003：手动触发统一用 `systemctl start networkagent-inspection.service`；systemd 不可用时不做进程内降级，报错"请先配置巡检服务"。
  - US-INSP-008 AC-INSP-008-02 要求 CLI 进程独立于 Web 进程（Web 重启不影响正在执行的巡检）。

- **Options**:
  - **Option A: 独立 Python 模块 + systemd service 调用（推荐方案）**
    - 描述：创建 `src/inspection_cli.py` 作为独立的 Python 模块（含 `__main__` 入口），实现 `python3.11 -m src.inspection_cli run` 命令。systemd service 的 ExecStart 直接调用此 CLI 命令。CLI 进程独立于 Web 进程运行：从 SQLite 加载设备列表和配置 → 执行全量巡检 → 结果持久化至 InspectionRecord → 以退出码退出。Web 进程中的手动触发（POST /api/inspection/trigger）通过 `systemctl start networkagent-inspection.service` 间接触发（PM Q-INSP-003）。
    - 优点：进程完全隔离——独立 PID、独立内存空间，完全满足 REQ-INSP-NF-004；Web 进程重启对 CLI 零影响（US-INSP-008 AC-INSP-008-02）；CLI 不导入 FastAPI/uvicorn 依赖，启动快、内存占用小；手动触发与定时触发使用完全相同的执行路径（都是 systemctl start service），行为一致；CLI 的退出码机制（0/1/2）可直接映射到 systemd service 的 Result（success/failure），满足 REQ-INSP-NF-002 的 Restart=on-failure 逻辑。
    - 缺点：手动触发比 v0.1.0 的进程内 daemon 线程方式增加了一次 systemd + subprocess 的调度开销（约 200ms）；systemd 不可用时（开发环境）无法手动触发（PM Q-INSP-003 已确认接受此限制）；CLI 与 Web 进程通过 SQLite 共享数据，需要注意 SQLite 并发写入时的 WAL 模式配置。
  - **Option B: Web 进程子进程（subprocess.Popen 调用 CLI）**
    - 描述：CLI 代码独立为模块，但手动触发时 Web 进程通过 `subprocess.Popen(['python3.11', '-m', 'src.inspection_cli', 'run'])` 启动子进程执行巡检。定时触发仍由 systemd service 调用。
    - 优点：手动触发仍然可用（不依赖 systemd）；开发环境（Windows）可以通过子进程方式触发巡检；CLI 代码独立模块，可单独测试。
    - 缺点：手动触发和定时触发的执行路径不一致（subprocess vs systemd），行为可能有微妙差异（如环境变量、工作目录、进程组）；子进程仍与 Web 进程共享父进程资源限制（如 cgroup），不是完全隔离；PM Q-INSP-003 已明确决策"手动触发统一用 systemctl start"——此方案与 PM 决策矛盾；REQ-INSP-NF-006 原本要求的"systemd 不可用时降级为进程内子进程"已被 PM Q-INSP-003 否决。
  - **Option C: Web 进程内线程/协程（v0.1.0 方式）**
    - 描述：保持 v0.1.0 的模式——手动触发在 Web 进程的 daemon 线程中调用 `run_inspection_once()`。
    - 优点：无进程调度开销，触发即时；开发环境完全可用。
    - 缺点：巡检与 Web 进程不隔离，违反 REQ-INSP-NF-004；PM Q-INSP-003 明确否决此方案（"不做进程内降级"）；REQ-INSP-017 要求废弃 APScheduler，此方案本质是保留旧架构；**不可接受**。

- **Decision**: 选择 **Option A（独立 Python 模块 + systemd service 调用）**。

  理由：
  1. **PM 决策锚定**：PM Q-INSP-003 明确要求"手动触发统一用 systemctl start networkagent-inspection.service；systemd 不可用时报错'请先配置巡检服务'，不做进程内降级"。Option A 完全符合此决策。Option B/C 与 PM 决策矛盾，直接否决。
  2. **进程隔离需求**：REQ-INSP-NF-004（Must Have，HIGH）要求巡检进程与 Web 进程完全隔离。Option A 通过 systemd service 启动独立进程，天然满足此项需求。Option B 的子进程虽然 PID 不同，但仍不是完全的 OS 级进程隔离。
  3. **执行路径一致性**：Option A 中手动触发和定时触发都通过 systemctl start service 执行，CLI 进程的运行环境（WorkingDirectory、User、Environment）完全一致，消除了双路径行为差异的风险。
  4. **退出码语义**：CLI 的退出码（0=全部正常，1=部分异常，2=执行失败）可直接映射到 systemd service 的 success/failure 判定，Restart=on-failure 仅对退出码非 0 触发重试。这是 systemd oneshot service 的标准使用模式。

- **Consequences**:
  - **正向**：
    - 完整支撑 REQ-INSP-014（CLI 入口）、REQ-INSP-017（APScheduler 废弃）、REQ-INSP-NF-004（进程隔离）、REQ-INSP-NF-005（端口兼容）。
    - 手动触发与定时触发共享同一 CLI 执行路径，保证行为一致性，降低测试和维护成本。
    - CLI 不导入 Web 依赖，启动快速（< 1 秒），内存占用小（仅需 SQLAlchemy + 诊断工具）。
  - **负向**：
    - 开发环境（Windows/macOS）无法手动触发巡检——PM Q-INSP-003 已确认接受此限制。
    - 手动触发的响应时间比 v0.1.0 的进程内 daemon 线程方式慢约 200ms（systemctl 调度开销）——Demo 场景可接受。
    - CLI 与 Web 通过 SQLite 共享数据，需确保 SQLite 配置 `PRAGMA journal_mode=WAL` 以支持并发读写。

---

### ADR-INSP-005: systemd 状态查询实现

- **Status**: Accepted
- **Context**:
  - REQ-INSP-004 要求提供 GET /api/inspection/status API，查询 systemd timer 和 service 的实时状态（ActiveState、UnitFileState、NextElapseUSRealtime、SubState 等）。
  - REQ-INSP-005 要求 Web UI 状态面板每 5 秒轮询该 API 自动刷新状态。
  - API 需在 5 秒内返回（AC-INSP-004-03），超时返回 HTTP 503。
  - 需要查询的信息分布在 timer 和 service 两个 unit 上，需要两次 systemd 查询。
  - REQ-INSP-NF-003 要求命令执行使用 subprocess.run(shell=False) 防注入。

- **Options**:
  - **Option A: systemctl show + subprocess 解析（推荐方案）**
    - 描述：后端通过 `subprocess.run(['sudo', 'systemctl', 'show', 'networkagent-inspection.timer', '--property=ActiveState,UnitFileState,NextElapseUSRealtime'], capture_output=True, timeout=5)` 执行命令，解析 `Key=Value` 格式的标准输出，构建 JSON 响应。对 service 同理执行第二条命令获取 ActiveState、SubState、Result、ExecMainExitTimestamp 等属性。
    - 优点：零额外 Python 依赖——仅使用标准库 subprocess；systemctl show 的 `--property=` 参数可精确指定需要的字段，避免解析大量无关输出；`Key=Value` 格式解析极其简单（按行 split('=')），不存在 JSON/XML 解析兼容性问题；`NextElapseUSRealtime` 输出为 systemd 标准时间戳格式（Unix 微秒），可直接转换；超时控制通过 subprocess.run(timeout=5) 原生支持。
    - 缺点：每次状态查询 fork 两次子进程（timer + service 各一次），在高频轮询（5 秒）场景下有轻微 CPU 开销——Demo 场景可忽略；systemctl show 的输出格式依赖于 systemd 版本（字段名在不同版本间基本稳定，风险低）；需要通过 sudo 执行（ADR-INSP-002 已解决权限问题）；`NextElapseUSRealtime` 在 timer 为 inactive 时输出 0，需要在解析层做特殊处理。
  - **Option B: D-Bus API（pydbus / dasbus）**
    - 描述：通过 Python D-Bus 绑定（如 pydbus 或 dasbus）直接调用 systemd 的 D-Bus API（`org.freedesktop.systemd1.Manager.GetUnit()` → `org.freedesktop.systemd1.Unit.GetAll()`），获取 timer/service 的完整属性字典。
    - 优点：无需 fork 子进程，性能优于 subprocess；属性访问类型安全（D-Bus 接口定义了每个属性的类型）；可以实时监听状态变化信号（PropertiesChanged），实现 push 模式而非轮询。
    - 缺点：需要安装额外的 Python D-Bus 绑定（pydbus 或 dasbus），增加依赖；D-Bus 权限管理比 sudoers 更复杂——需要配置 D-Bus policy 允许 networkagent 用户访问 systemd 的 D-Bus 接口；D-Bus API 在不同 systemd 版本间可能有细微差异；`NextElapseUSRealtime` 等 timer 特有属性的 D-Bus 路径需要查文档确认；Demo 规模下 D-Bus 方案的复杂度价值比不高。
  - **Option C: pyinotify 监听 systemd 状态文件**
    - 描述：使用 pyinotify 监听 systemd 的状态文件（如 `/run/systemd/units/` 或 `/sys/fs/cgroup/systemd/`），通过文件变更事件更新内存缓存，API 查询直接返回缓存值。
    - 优点：API 响应极快（内存缓存读取）；不需要每次查询执行系统命令。
    - 缺点：systemd 的状态文件路径和格式是内部实现细节，不同版本间可能变化，不保证稳定；需要维护缓存一致性和失效策略；pyinotify 已多年未更新（最后发布 2015 年），Python 3.11 兼容性存疑；实现复杂度远超需求；**不适合 Demo 场景**。

- **Decision**: 选择 **Option A（systemctl show + subprocess 解析）**。

  理由：
  1. **零额外依赖**：Option A 仅使用 Python 标准库 `subprocess`，与 ADR-INSP-002 的 systemctl_executor 模块（MOD-INSP-002）技术栈一致。不引入新的第三方依赖。
  2. **实现简洁**：`systemctl show --property=` 精确获取所需字段，`Key=Value` 格式解析只需 `dict(line.split('=', 1) for line in output.strip().split('\n'))` 一行逻辑。Option B 的 D-Bus API 调用链复杂（需要理解 D-Bus 对象路径、接口名、属性名），Option C 的 inotify 方案依赖 systemd 内部不稳定的文件格式。
  3. **性能可接受**：5 秒轮询间隔下，每次 fork 两个子进程执行 systemctl show 的总耗时通常 < 50ms（Demo 环境的 systemd 查询极快），CPU 开销可忽略。Option B 的性能优势在 Demo 场景下无意义。
  4. **systemd 兼容性**：`systemctl show --property=` 是 systemd 长期稳定的公共接口，比 D-Bus API 路径和内部状态文件格式更不可能在版本升级中变化。

- **Consequences**:
  - **正向**：
    - 完整支撑 REQ-INSP-004（状态查询 API）、REQ-INSP-005（Web UI 状态面板）、US-INSP-003 全部验收标准。
    - systemctl_executor（MOD-INSP-002）封装 systemctl show 命令，提供 `get_timer_status()` 和 `get_service_status()` 两个方法，返回 Pydantic 模型。
    - 解析逻辑可单元测试（mock subprocess.run 的输出为固定文本）。
  - **负向**：
    - 每次状态查询 fork 两次子进程。在前端 5 秒轮询 + 后端多用户并发场景下，需要考虑 systemctl_executor 内部的短时缓存（如 2 秒 TTL 内存缓存），避免同一秒内多次查询重复 fork。[ASSUMPTION — 缓存策略可在实施阶段根据实际性能数据决定是否引入]
    - `NextElapseUSRealtime` 在 timer inactive 时值为 0，需在解析层转换为 `None`（表示"无计划触发时间"）。
    - systemctl show 通过 sudo 执行，需要确保 sudoers 配置涵盖 `systemctl show` 子命令。（ADR-INSP-002 的 sudoers 配置使用 `systemctl * networkagent-inspection.*` glob，已覆盖 show 子命令。）

---

### ADR-INSP-006: 巡检配置 SQLite → systemd 同步策略

- **Status**: Accepted
- **Context**:
  - REQ-INSP-002 要求配置保存后自动生成 systemd unit 文件。
  - REQ-INSP-003 要求 unit 文件变更后自动执行 daemon-reload + 条件重启 timer。
  - REQ-INSP-012 要求巡检参数 SQLite 持久化，读取优先级 SQLite > config.yaml。
  - REQ-INSP-013 要求 SQLite 配置变更后同步至 systemd unit 文件（interval_minutes → OnUnitActiveSec，timeout_seconds → TimeoutStopSec）。
  - US-INSP-001 AC-INSP-001-02 要求保存配置后 systemd 同步立即生效。
  - US-INSP-002 AC-INSP-002-02 要求配置变更时更新 unit 文件。
  - AC-INSP-013-01 描述了完整的同步链路：更新 SQLite → 生成 unit 文件 → daemon-reload → 若 timer active 则 restart。

- **Options**:
  - **Option A: 实时同步（配置保存时立即同步）— 推荐方案**
    - 描述：运维人员通过 PUT /api/inspection/config 保存配置时，后端按以下顺序执行同步链路：① 校验参数合法性 → ② 写入 SQLite SystemConfig 表 → ③ 读取最新配置 → ④ 调用 MOD-INSP-001 (systemd_unit_manager) 渲染 Jinja2 模板生成 unit 文件内容 → ⑤ 写入 `/etc/systemd/system/` → ⑥ 执行 `systemctl daemon-reload` → ⑦ 若 timer 当前 active 则 `systemctl restart networkagent-inspection.timer` → ⑧ 返回操作结果给 Web UI。若步骤⑤/⑥/⑦中任意步骤失败，SQLite 写入不回滚（保持配置数据），返回部分成功状态并提示运维人员重试 systemd 同步。
    - 优点：配置保存后 systemd 立即生效，满足 US-INSP-001 AC-INSP-001-02 的用户预期；同步链路在单次 API 请求中完成，没有异步状态不一致窗口；错误反馈及时——若 systemd 同步失败，运维人员在同一 Web UI 操作中即可看到错误提示和重试建议；实现简单，不需要定时同步任务或消息队列。
    - 缺点：API 响应时间包含 systemd 操作耗时（daemon-reload 通常 < 100ms，restart timer < 50ms），总延迟约 +150ms——Demo 场景可忽略；若 systemd 同步失败，API 返回部分成功（SQLite 已更新但 systemd 未同步），运维人员需要通过"重新同步"按钮手动重试；`systemctl daemon-reload` 和 `systemctl restart timer` 需要 sudo 权限（ADR-INSP-002 已解决）。
  - **Option B: 延迟批量同步（定时任务定期巡检配置差异）**
    - 描述：配置保存时仅写入 SQLite，不触发 systemd 同步。由独立的定时同步任务（如每 30 秒运行一次）扫描 SQLite 配置与 systemd unit 文件的差异，发现不一致时执行同步。
    - 优点：API 响应不受 systemd 操作影响，配置保存即时返回；批量同步可以减少 systemd 操作的频率（合并多次配置变更）。
    - 缺点：配置保存到 systemd 生效之间存在最长 30 秒延迟，违反 US-INSP-001 AC-INSP-001-02"配置变更立即生效"的用户预期；需要额外的定时同步机制（在 Web 进程中增加一个后台任务），增加复杂度；配置不一致窗口期可能出现"Web UI 显示已保存但 systemd 仍用旧配置执行巡检"的混淆状态；同步失败时运维人员无法在配置保存的上下文中立即感知，需要额外的告警通知机制。
  - **Option C: 事件驱动异步同步（Web 进程发事件，后台 Worker 同步）**
    - 描述：配置保存后，Web 进程向内部消息队列（如 asyncio.Queue 或 Redis Stream）发送同步事件，后台 Worker 消费事件执行 systemd 同步。
    - 优点：API 响应与 systemd 操作异步解耦；Worker 可以控制同步并发（避免多个配置保存同时操作 systemd）。
    - 缺点：引入消息队列或 Worker 线程增加系统复杂度；异步同步的失败处理和重试逻辑复杂（需要死信队列或重试策略）；Demo 规模下单进程架构引入消息队列属于过度设计；用户无法在 API 响应中知道 systemd 同步是否成功。

- **Decision**: 选择 **Option A（实时同步）**。

  理由：
  1. **用户预期对齐**：US-INSP-001 AC-INSP-001-02 明确要求"保存配置后 systemd 同步立即生效"，US-INSP-002 AC-INSP-002-02 要求"配置变更时更新 unit 文件"。Option A 是唯一满足"立即生效"需求的方案。
  2. **实现简单**：Option A 在单次 API 请求的同步流程中完成全链路，不需要额外的定时任务、消息队列或后台 Worker。Demo 规模下同步链路清晰可靠。
  3. **错误处理直观**：同步失败时，同一 API 响应中返回部分成功状态和错误原因，运维人员可立即感知并采取行动。Option B/C 的异步模式会使错误反馈延迟到同步任务的下一次执行。
  4. **性能可接受**：systemd daemon-reload + restart timer 的总耗时通常在 200ms 以内，增加到配置保存 API 的响应延迟中是可接受的。如果未来性能成为瓶颈，可以将步骤⑥⑦改为 `asyncio.to_thread()` 异步执行并立即返回 HTTP 202，但 Demo 阶段不需要。

- **Consequences**:
  - **正向**：
    - 完整支撑 REQ-INSP-002（unit 文件生成）、REQ-INSP-003（daemon-reload）、REQ-INSP-012（SQLite 持久化）、REQ-INSP-013（配置同步）、US-INSP-001 AC-INSP-001-02（立即生效）、US-INSP-002 AC-INSP-002-02（配置变更更新 unit 文件）。
    - 同步链路的每个步骤都可以独立单元测试——SQLite 写入、模板渲染、文件写入、systemctl 命令执行各自可 mock。
  - **负向**：
    - 同步失败的"部分成功"状态需要 Web UI 展示清晰的错误提示和"重新同步"按钮（US-INSP-001 AC-INSP-001-05）。
    - `systemctl daemon-reload` 会通知 systemd 重新加载所有 unit 文件——如果服务器上有大量其他 unit 文件，可能导致短暂的性能抖动。但 Demo 环境仅少量 unit 文件，此风险可忽略。
    - 配置保存操作的幂等性需要处理（US-INSP-002 AC-INSP-002-05）：如果配置值与当前 unit 文件内容一致，应跳过 unit 文件写入和 daemon-reload。需要在 systemd_unit_manager 中实现配置值对比逻辑。

---

## 架构变更影响分析

### v0.1.0 模块变更矩阵

| v0.1.0 模块 | v0.2.0 变更类型 | 变更说明 |
|-------------|----------------|---------|
| MOD-002 (InspectionScheduler) | **废弃 APScheduler** | start_scheduler()/stop_scheduler() 废弃；run_inspection_once() 逻辑迁移至 MOD-INSP-003 (inspection_cli) |
| MOD-WEB-001 (inspection_router) | **增强** | 新增 6 个端点（status/start/stop/restart/enable/disable）；增强 config/trigger/history 端点 |
| MOD-WEB-003 (inspection_models) | **增强** | InspectionRecord 新增 status 字段（SUCCESS/PARTIAL/FAILED） |
| MOD-WEB-004 (inspection_repository) | **增强** | 新增 retry_backoff 配置项；新增 unit 文件生成触发逻辑 |
| MOD-016 (ConfigManager) | **增强** | DEFAULT_CONFIG 增加 systemd 相关默认值；增加 NETWORKAGENT_HOME 环境变量读取 |
| MOD-015 (AuditLogger) | **保留** | 不变——systemd 操作日志通过 journald 记录，应用层审计日志仍由 MOD-015 负责 |
| MOD-007 (TemplateEngine) | **复用** | Jinja2 模板引擎同时用于 CLI 命令模板和 systemd unit 文件模板 |

### v0.2.0 新增模块

| MOD-ID | 模块名 | 层级 | 职责 |
|--------|--------|------|------|
| MOD-INSP-001 | systemd_unit_manager | 安全与基础设施层 | 生成、写入、验证 unit 文件，执行 daemon-reload |
| MOD-INSP-002 | systemctl_executor | 安全与基础设施层 | 封装 systemctl 命令调用，含权限检查和错误处理 |
| MOD-INSP-003 | inspection_cli | 触发层 | CLI 巡检入口，从 SQLite 加载配置，执行全量巡检，结果持久化 |

### 废弃项

| 组件 | 废弃原因 |
|------|---------|
| APScheduler Python 包 | 替换为 systemd timer + service（REQ-INSP-017） |
| inspection_scheduler.py 调度逻辑 | start_scheduler()/stop_scheduler() 废弃；run_inspection_once() 迁移至 CLI |
| main.py 中的 APScheduler 初始化 | Web 进程不再承载调度逻辑 |

---

## 需求到模块覆盖矩阵（v0.2.0 巡检部分）

| REQ ID | 描述（摘要） | 覆盖模块 | 覆盖方式 |
|--------|-------------|---------|---------|
| REQ-INSP-001 | Web UI 巡检参数配置 | MOD-WEB-001, MOD-WEB-004, MOD-016 | API + Repository + ConfigManager |
| REQ-INSP-002 | 配置保存时自动生成 unit 文件 | MOD-INSP-001, MOD-WEB-004 | Jinja2 模板渲染 + 文件写入 |
| REQ-INSP-003 | systemd daemon-reload 自动执行 | MOD-INSP-001, MOD-INSP-002 | systemctl_executor 执行 daemon-reload |
| REQ-INSP-004 | systemd timer 状态查询 API | MOD-WEB-001, MOD-INSP-002 | systemctl show + 解析 |
| REQ-INSP-005 | Web UI 巡检状态面板 | MOD-INSP-006 (前端) | Vue 组件 + Pinia store |
| REQ-INSP-006 | systemd service 生命周期控制 API | MOD-WEB-001, MOD-INSP-002 | systemctl start/stop/restart |
| REQ-INSP-007 | systemd timer 启用/禁用 API | MOD-WEB-001, MOD-INSP-002 | systemctl enable/disable |
| REQ-INSP-008 | Web UI 巡检控制按钮 | MOD-INSP-006 (前端) | Vue 组件 + Pinia store |
| REQ-INSP-009 | 手动触发巡检（保留） | MOD-WEB-001, MOD-INSP-002 | systemctl start service |
| REQ-INSP-010 | 巡检结果持久化 SQLite | MOD-INSP-003, MOD-WEB-003, MOD-WEB-004 | CLI 写入 InspectionRecord |
| REQ-INSP-011 | 巡检历史查询与展示 | MOD-WEB-001, MOD-WEB-004, MOD-INSP-006 | API + Repository + Vue 组件 |
| REQ-INSP-012 | 巡检参数 SQLite 持久化 | MOD-WEB-004, MOD-016 | SystemConfig 表读写 |
| REQ-INSP-013 | 配置同步至 systemd unit 文件 | MOD-INSP-001, MOD-WEB-004 | 实时同步链路 |
| REQ-INSP-014 | CLI 巡检执行入口 | MOD-INSP-003 | python -m src.inspection_cli run |
| REQ-INSP-015 | service unit 文件定义 | MOD-INSP-001 | Jinja2 模板 |
| REQ-INSP-016 | timer unit 文件定义 | MOD-INSP-001 | Jinja2 模板 |
| REQ-INSP-017 | APScheduler 调度器废弃 | MOD-002（废弃）, main.py | 移除初始化代码和依赖 |
| REQ-INSP-NF-001 | timer 触发精度 | MOD-INSP-001 | AccuracySec=1s 模板参数 |
| REQ-INSP-NF-002 | service 故障自动恢复 | MOD-INSP-001 | Restart=on-failure 模板参数 |
| REQ-INSP-NF-003 | systemctl 权限管理 | MOD-INSP-002 | sudoers + subprocess(shell=False) |
| REQ-INSP-NF-004 | 进程隔离 | MOD-INSP-003 | systemd service 独立进程 |
| REQ-INSP-NF-005 | 端口兼容性 | MOD-INSP-003 | CLI 不监听端口 |
| REQ-INSP-NF-006 | systemd 不可用时降级 | MOD-INSP-002, MOD-WEB-001 | [PM Q-INSP-003 已否决降级策略，改为报错] |
| REQ-INSP-NF-007 | journald 日志集成 | MOD-INSP-001 | StandardOutput/Error=journal 模板参数 |

---

## 依赖关系图（v0.2.0 巡检相关模块）

```
# Web 层 → 基础设施层
MOD-WEB-001 (inspection_router) ──→ MOD-INSP-001 (systemd_unit_manager)  [IFC-INSP-001-01/02]
MOD-WEB-001 (inspection_router) ──→ MOD-INSP-002 (systemctl_executor)    [IFC-INSP-002-01~06]
MOD-WEB-001 (inspection_router) ──→ MOD-WEB-004 (inspection_repository)  [现有依赖]
MOD-WEB-001 (inspection_router) ──→ MOD-016 (ConfigManager)              [现有依赖]

# 基础设施层内部
MOD-INSP-001 (systemd_unit_manager) ──→ MOD-INSP-002 (systemctl_executor)  [IFC-INSP-002-06 daemon-reload]
MOD-INSP-001 (systemd_unit_manager) ──→ MOD-016 (ConfigManager)            [读取 NETWORKAGENT_HOME]
MOD-INSP-002 (systemctl_executor) ──→ (无依赖，最底层 — subprocess)

# CLI 层
MOD-INSP-003 (inspection_cli) ──→ MOD-WEB-004 (inspection_repository)     [读写配置和记录]
MOD-INSP-003 (inspection_cli) ──→ MOD-WEB-003 (inspection_models)         [InspectionRecord 模型]
MOD-INSP-003 (inspection_cli) ──→ MOD-016 (ConfigManager)                 [读取配置]
MOD-INSP-003 (inspection_cli) ──→ MOD-011 (SwitchDiagTool)                [执行诊断 — 现有依赖]

# 数据层
MOD-WEB-004 (inspection_repository) ──→ MOD-WEB-003 (inspection_models)   [现有依赖]

# ─── 验证：无循环依赖 ───
# BFS 遍历确认所有路径单向无环:
# MOD-WEB-001 → MOD-INSP-001 → MOD-INSP-002 → (终点)
# MOD-WEB-001 → MOD-INSP-001 → MOD-016 → (终点)
# MOD-WEB-001 → MOD-INSP-002 → (终点)
# MOD-WEB-001 → MOD-WEB-004 → MOD-WEB-003 → (终点)
# MOD-INSP-003 → MOD-WEB-004 → MOD-WEB-003 → (终点)
# MOD-INSP-003 → MOD-016 → (终点)
# MOD-INSP-003 → MOD-011 → (终点)
# 全部路径收敛至终端节点，无环。
```

---

## 开放问题

| 编号 | 问题 | 状态 |
|------|------|------|
| Q-ARCH-INSP-001 | [ASSUMPTION] systemctl_executor 内部是否需要短时缓存（如 2 秒 TTL）以减少高频轮询时的 systemctl show 调用次数 | 待 PM 确认——可根据实施阶段实际性能数据决定 |
| Q-ARCH-INSP-002 | [ASSUMPTION] SQLite WAL 模式是否已开启——CLI 进程和 Web 进程需要并发读写 SQLite，WAL 模式是前提条件 | 待实施阶段验证——若 v0.1.0 未开启 WAL，需在 v0.2.0 部署时开启 |
| Q-ARCH-INSP-003 | [ASSUMPTION] sudoers 配置中的 glob 模式 `networkagent-inspection.*` 是否足够精确——是否可能匹配到非预期的 unit 文件 | 低风险——除非系统中存在其他以 networkagent-inspection 开头的 unit 文件 |
| Q-ARCH-INSP-004 | [ASSUMPTION] Jinja2 渲染 systemd unit 文件时不需要处理 `%i`/`%n` 等 systemd 说明符——当前模板设计中 WorkingDirectory 和 User 直接填写具体值 | 如未来需要这些说明符，需在模板中使用 `{% raw %}` 包裹 |
</file_header>