<file_header>
  <author_agent>sub_agent_software_developer</author_agent>
  <timestamp>2026-07-12T00:00:00Z</timestamp>
  <project_name>NetworkAgentDemo</project_name>
  <version>0.2.0</version>
  <input_files>
    <file>requirements/inspection_systemd_requirements.md</file>
    <file>requirements/inspection_systemd_user_stories.md</file>
    <file>architecture/inspection_systemd_architecture_design.md</file>
    <file>architecture/inspection_systemd_module_design.md</file>
    <file>architecture/inspection_systemd_tech_stack.md</file>
    <file>src/api/inspection_router.py (v0.1.0)</file>
    <file>src/database/inspection_models.py (v0.1.0)</file>
    <file>src/database/repositories/inspection_repository.py (v0.1.0)</file>
    <file>src/trigger/inspection_scheduler.py (v0.1.0)</file>
    <file>src/security/config_manager.py (v0.1.0)</file>
    <file>src/main.py (v0.1.0)</file>
    <file>requirements.txt (v0.1.0)</file>
    <file>webui/src/views/inspection/InspectionConfigView.vue (v0.1.0)</file>
    <file>webui/src/stores/inspection.ts (v0.1.0)</file>
  </input_files>
  <phase>PHASE_INSP_04</phase>
  <status>DRAFT</status>
</file_header>

# 巡检机制 systemd 重构 — 实现计划

---

## 实现概览

- **总模块数**: 7（MOD-INSP-001~003 新增 + MOD-WEB-001/003/004 增强 + main.py/requirements.txt 废弃）
- **总文件数**: 15（3 新增模块 + 2 Jinja2 模板 + 4 增强后端 + 1 废弃修改 + 1 依赖 + 2 前端 + 2 文档）
- **实现顺序**: 按拓扑排序（被依赖模块先实现），无循环依赖
- **编程语言**: Python 3.11 + TypeScript (Vue 3)
- **零新增 Python 依赖**: systemd 交互全部使用标准库 subprocess

---

## 模块实现计划（按拓扑顺序）

| 序号 | MOD-ID | 模块名 | 文件路径 | 依赖前置模块 | 复杂度 | 状态 |
|------|--------|--------|---------|------------|--------|------|
| 1 | MOD-WEB-003 | inspection_models (增强) | `src/database/inspection_models.py` | — | L | PLANNED |
| 2 | MOD-INSP-002 | systemctl_executor | `src/systemd/systemctl_executor.py` | — | M | PLANNED |
| 3 | MOD-WEB-004 | inspection_repository (增强) | `src/database/repositories/inspection_repository.py` | MOD-WEB-003 | M | PLANNED |
| 4 | MOD-INSP-001 | systemd_unit_manager | `src/systemd/systemd_unit_manager.py` | MOD-INSP-002, MOD-016 | M | PLANNED |
| 5 | — | Jinja2 模板文件 | `resources/templates/systemd/networkagent-inspection.service.j2` | — | L | PLANNED |
| 6 | — | Jinja2 模板文件 | `resources/templates/systemd/networkagent-inspection.timer.j2` | — | L | PLANNED |
| 7 | MOD-INSP-003 | inspection_cli | `src/inspection_cli.py` | MOD-WEB-003, MOD-WEB-004, MOD-016 | H | PLANNED |
| 8 | MOD-WEB-001 | inspection_router (增强) | `src/api/inspection_router.py` | MOD-INSP-001, MOD-INSP-002, MOD-WEB-004 | H | PLANNED |
| 9 | — | main.py (废弃 APScheduler) | `src/main.py` | MOD-WEB-001 | M | PLANNED |
| 10 | — | inspection_scheduler.py (标记废弃) | `src/trigger/inspection_scheduler.py` | — | L | PLANNED |
| 11 | — | requirements.txt (移除 apscheduler) | `requirements.txt` | — | L | PLANNED |
| 12 | MOD-INSP-006 | inspection.ts Pinia store (增强) | `webui/src/stores/inspection.ts` | — | M | PLANNED |
| 13 | MOD-INSP-006 | InspectionConfigView.vue (增强) | `webui/src/views/inspection/InspectionConfigView.vue` | MOD-INSP-006 store | H | PLANNED |

---

## 依赖图（有向图）

```
# Layer 0 (no deps)
MOD-WEB-003 (inspection_models) ────┐
MOD-INSP-002 (systemctl_executor) ──┤
                                    ▼
# Layer 1
MOD-WEB-004 (inspection_repository) ──┐
MOD-INSP-001 (systemd_unit_manager) ──┤
Jinja2 Templates (service.j2, timer.j2) ──┘
                                    ▼
# Layer 2
MOD-INSP-003 (inspection_cli) ────────┐
MOD-WEB-001 (inspection_router) ──────┤
                                    ▼
# Layer 3 (app-level)
main.py (APScheduler removal)
requirements.txt (apscheduler removal)

# Frontend (parallel)
inspection.ts Pinia store ──→ InspectionConfigView.vue

# ─── 无循环依赖，已验证 ───
```

### 拓扑排序结果

```
1. MOD-WEB-003 → inspection_models.py (底层，无依赖)
2. MOD-INSP-002 → systemctl_executor.py (底层，无依赖)
3. MOD-WEB-004 → inspection_repository.py (依赖 MOD-WEB-003)
4. Jinja2 Templates → service.j2, timer.j2 (被 MOD-INSP-001 依赖)
5. MOD-INSP-001 → systemd_unit_manager.py (依赖 MOD-INSP-002, MOD-016)
6. MOD-INSP-003 → inspection_cli.py (依赖 MOD-WEB-003/004, MOD-016)
7. MOD-WEB-001 → inspection_router.py (依赖 MOD-INSP-001/002, MOD-WEB-004)
8. src/main.py (移除 APScheduler)
9. src/trigger/inspection_scheduler.py (标记废弃)
10. requirements.txt (移除 apscheduler)
11. webui/src/stores/inspection.ts (前端 store)
12. webui/src/views/inspection/InspectionConfigView.vue (前端视图)
```

---

## 架构偏差记录

无架构偏差。所有实现严格遵循 `inspection_systemd_module_design.md` 中的接口契约（IFC-INSP-* 和 IFC-WEB-*）以及 `inspection_systemd_architecture_design.md` 中的 ADR 决策。

---

## 各模块实现要点

### 1. MOD-WEB-003 (inspection_models.py 增强)
- **变更**: InspectionRecord 表新增 `status` 字段 (String(15), SUCCESS/PARTIAL/FAILED)
- **IFC**: 无独立接口契约（数据模型字段增加）
- **兼容性**: 新增列添加默认值 `SUCCESS`，历史数据不受影响

### 2. MOD-INSP-002 (systemctl_executor.py)
- **新增文件**: `src/systemd/systemctl_executor.py`
- **IFC**: IFC-INSP-002-01~09（9 个接口方法）
- **Pydantic 模型**: TimerStatus, ServiceStatus, SystemctlResult, SystemdAvailability
- **特征**: 所有 systemctl 调用使用 `subprocess.run(shell=False)`, 参数列表形式

### 3. MOD-WEB-004 (inspection_repository.py 增强)
- **变更**: get_config() 增加 retry_backoff; 新增 get_device_list(), get_latest_inspection()
- **变更**: list_history() 增加 status 筛选参数
- **IFC**: IFC-WEB-004-01~07

### 4. Jinja2 模板文件
- **新增**: `resources/templates/systemd/networkagent-inspection.service.j2`
- **新增**: `resources/templates/systemd/networkagent-inspection.timer.j2`
- **模板变量**: working_directory, user, python_bin, timeout_stop_sec, on_unit_active_sec 等
- **遵循**: ADR-INSP-003 (Jinja2 模板引擎); PM Q-INSP-004 (WorkingDirectory 从 NETWORKAGENT_HOME 读取); PM Q-INSP-005 (Demo 无 MemoryLimit/CPUQuota)

### 5. MOD-INSP-001 (systemd_unit_manager.py)
- **新增文件**: `src/systemd/systemd_unit_manager.py`
- **IFC**: IFC-INSP-001-01~06（6 个接口方法）
- **特征**: Jinja2 模板渲染 + 文件写入 + daemon-reload + 幂等检查

### 6. MOD-INSP-003 (inspection_cli.py)
- **新增文件**: `src/inspection_cli.py`
- **IFC**: IFC-INSP-003-01~03（3 个接口方法 / CLI 入口）
- **特征**: 从 inspection_scheduler.py 迁移 run_inspection_once() 核心逻辑
- **CLI**: `python3.11 -m src.inspection_cli run`
- **退出码**: 0=SUCCESS, 1=PARTIAL, 2=FAILURE

### 7. MOD-WEB-001 (inspection_router.py 增强)
- **新增端点**: 6个 (status/start/stop/restart/enable/disable)
- **增强端点**: 4个 (config/trigger/history)
- **IFC**: IFC-WEB-001-05~10
- **触发变更**: POST /api/inspection/trigger 改为通过 MOD-INSP-002.start_service() 触发

### 8. main.py (APScheduler 废弃)
- **移除**: inspection_scheduler.start_scheduler() 调用
- **移除**: inspection_scheduler.stop_scheduler() 调用
- **移除**: default_devices 硬编码列表
- **移除**: inspection_scheduler 实例创建
- **保留**: inspection_scheduler 导入（inspection_router.py 可能仍有引用 — 实际 router 不再引用）

### 9. requirements.txt
- **移除**: apscheduler>=3.10.0,<4.0.0

### 10. 前端变更
- **inspection.ts**: 新增 fetchStatus/startService/stopService/restartService/enableTimer/disableTimer; 新增 timerStatus/serviceStatus/systemdAvailable state
- **InspectionConfigView.vue**: 新增状态面板 + 控制按钮组 + polling_interval 替换为 retry_backoff
