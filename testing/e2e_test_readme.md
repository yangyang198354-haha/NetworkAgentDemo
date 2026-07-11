<file_header>
  <author_agent>main_agent_pm</author_agent>
  <timestamp>2026-07-11T00:00:00Z</timestamp>
  <project_name>NetworkAgentDemo</project_name>
  <version>0.2.0</version>
  <phase>PHASE_09</phase>
  <status>DRAFT</status>
</file_header>

# E2E 测试运行说明 — NetworkAgentDemo v0.2.0 Web UI

---

## 1. 前置依赖

测试使用 **pytest** + **httpx**，无需安装项目本身的 Python 依赖。

```bash
pip install pytest httpx
```

Python >= 3.8 即可。

---

## 2. 目标环境

测试针对**远程生产 VPS** 运行：

| 项目 | 值 |
|------|-----|
| URL | `http://47.109.197.217:8001` |
| 登录 | admin / admin |
| 协议 | HTTP（非 HTTPS） |

**不需要在本地启动任何服务**。测试直接向远程 VPS 发送 HTTP 请求。

---

## 3. 运行方式

### 3.1 默认运行（全部测试，16 个用例）

```bash
cd C:\Users\胖子熊\MyProject\AutoMaintain\project_workspace\NetworkAgentDemo
pytest tests/test_e2e_webui.py -v --tb=short
```

### 3.2 自定义目标 URL

```bash
BASE_URL=http://47.109.197.217:8001 pytest tests/test_e2e_webui.py -v
```

可替换为其他 IP 或端口。

### 3.3 跳过慢速测试（工作流轮询）

工作流轮询测试（TC-E2E-WEB-007）会等待最多 60 秒。如需快速验证：

```bash
pytest tests/test_e2e_webui.py -v -k "not workflow_polling" --tb=short
```

### 3.4 仅运行 P0 高优先级测试

```bash
pytest tests/test_e2e_webui.py -v -k "P0" --tb=short
```

但需要注意：pytest 的 `-k` 是按测试函数名匹配，这里的 P0/P1 标记在类名中。实际筛选方式：

```bash
# P0 类为：TestAuthLoginSuccess, TestAuthLoginFailure,
#          TestAuthUnauthenticated, TestAlertSimulate,
#          TestAlertList, TestAlertDetail,
#          TestApprovalPending, TestApprovalDecide,
#          TestDashboardHealth, TestDeviceList
pytest tests/test_e2e_webui.py -v --tb=short -k "Auth or Alert or Approval or DashboardHealth or DeviceList"
```

### 3.5 使用配置文件

也可通过 `pytest.ini` 或 `tox.ini` 持久化环境变量：

```ini
# pytest.ini
[pytest]
env =
    BASE_URL=http://47.109.197.217:8001
    WORKFLOW_MAX_WAIT=60
    WORKFLOW_POLL_INTERVAL=3
```

（需安装 `pytest-env` 插件）

---

## 4. 环境变量说明

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `BASE_URL` | `http://47.109.197.217:8001` | 目标服务地址 |
| `TEST_USERNAME` | `admin` | 登录用户名 |
| `TEST_PASSWORD` | `admin` | 登录密码 |
| `HTTP_TIMEOUT` | `30` | 单个 HTTP 请求超时（秒） |
| `WORKFLOW_POLL_INTERVAL` | `3` | 工作流状态轮询间隔（秒） |
| `WORKFLOW_MAX_WAIT` | `60` | 工作流完成最大等待时间（秒） |

---

## 5. 测试用例清单

| 类 | 测试函数 | 优先级 | 耗时 | 说明 |
|----|---------|--------|------|------|
| TestAuthLoginSuccess | test_login_returns_token | P0 | <1s | 登录获取 JWT |
| TestAuthLoginSuccess | test_token_grants_access_to_protected_endpoint | P0 | <1s | Token 访问受保护 API |
| TestAuthLoginFailure | test_login_wrong_password_returns_401 | P0 | <1s | 错误密码登录 |
| TestAuthLoginFailure | test_login_wrong_username_returns_401 | P0 | <1s | 不存在用户登录 |
| TestAuthUnauthenticated | test_alerts_without_token_returns_401_or_403 | P0 | <1s | 无 Token 访问告警 API |
| TestAuthUnauthenticated | test_devices_without_token_returns_401_or_403 | P0 | <1s | 无 Token 访问设备 API |
| TestAlertSimulate | test_simulate_port_down_alert | P0 | <2s | 模拟 PORT_DOWN 告警 |
| TestAlertSimulate | test_simulate_mac_flapping_alert | P0 | <2s | 模拟 MAC_FLAPPING 告警 |
| TestAlertSimulate | test_simulate_cpu_high_alert | P0 | <2s | 模拟 CPU_HIGH 告警 |
| TestAlertSimulate | test_simulate_invalid_alert_type_returns_400 | P0 | <2s | 无效告警类型 |
| TestAlertList | test_list_all_alerts | P0 | <2s | 告警列表 |
| TestAlertList | test_filter_by_alert_type | P0 | <2s | 按类型筛选告警 |
| TestAlertList | test_pagination | P0 | <2s | 分页查询 |
| TestAlertDetail | test_get_alert_detail | P0 | <5s | 告警详情含 timeline |
| TestAlertDetail | test_get_nonexistent_alert_returns_404 | P0 | <2s | 不存在的告警 |
| **TestWorkflowPolling** | **test_workflow_completes_within_timeout** | **P0** | **~60s** | **工作流轮询直到完成** |
| TestWorkflowPolling | test_workflow_timeline_grows | P0 | ~10s | 验证 timeline 增长 |
| TestWorkflowGraph | test_get_workflow_graph | P1 | <2s | 工作流拓扑图 |
| TestApprovalPending | test_get_pending_approvals | P0 | <2s | 待审批列表 |
| TestApprovalPending | test_pending_approval_structure | P0 | <2s | 审批项字段验证 |
| TestApprovalDecide | test_approve_pending_approval | P0 | <5s | 批准审批 |
| TestApprovalDecide | test_invalid_decision_returns_400 | P0 | <2s | 无效决策参数 |
| TestApprovalDecide | test_get_approval_history | P0 | <2s | 审批历史 |
| TestDashboardHealth | test_dashboard_health_endpoint | P0 | <2s | Dashboard 健康 |
| TestDashboardHealth | test_public_health_endpoint | P0 | <2s | 公开 /health 端点 |
| TestDashboardStats | test_get_dashboard_stats | P1 | <2s | Dashboard 统计 |
| TestDeviceList | test_list_devices | P0 | <2s | 设备列表 |
| TestDeviceList | test_device_structure | P0 | <2s | 设备结构验证 |
| TestDeviceCRUD | test_create_read_update_delete_device | P1 | <10s | 设备 CRUD 闭环 |
| TestKnowledgeBase | test_list_documents | P1 | <2s | 知识文档列表 |
| TestKnowledgeBase | test_list_templates | P1 | <2s | 命令模板列表 |
| TestKnowledgeBase | test_retrieval_test | P1 | <5s | RAG 检索测试 |
| TestSystemConfig | test_get_system_config | P1 | <2s | 系统配置读取 |
| TestSystemConfig | test_llm_api_key_is_masked | P1 | <2s | API Key 掩码验证 |
| TestSystemConfig | test_get_inspection_config | P1 | <2s | 巡检配置读取 |

| 总计 | **34 个测试函数** | P0: 25, P1: 9 | max ~120s（含两个慢测试） |

---

## 6. 预期结果

### 正常情况（所有组件正常）

```
34 passed, 1 skipped in ~90s
```

- `TestApprovalDecide.test_approve_pending_approval` 可能 skip（若无待审批项）
- `TestWorkflowPolling.test_workflow_completes_within_timeout` 是耗时最长的测试

### 可能出现的临时失败

| 现象 | 原因 | 动作 |
|------|------|------|
| Workflow 轮询超时 | 工作流因 LLM API 不可达或其他原因卡住 | 检查 VPS 上的 LangGraph 状态和 LLM 配置 |
| 审批测试 Skip | 当前没有任何待审批项 | 正常，触发 PORT_DOWN 告警后可能产生待审批项 |
| 设备 CRUD 409 | 上次测试未清理干净 | 测试代码内置重试逻辑处理冲突 |
| 知识库检索返回空 | Chroma 未初始化或 seed 数据未加载 | 不影响测试通过（测试只验证 API 可用性） |

---

## 7. 测试约束

1. **不对生产数据做破坏性操作**：设备 CRUD 测试创建测试设备后立即删除；审批测试仅在存在待审批项时执行
2. **不删除告警历史**：模拟告警产生的工作流数据保留在 SQLite 中
3. **使用唯一命名**：测试设备使用 `E2E-TEST-DEV-01` 前缀，避免与真实设备冲突
4. **Token 会话复用**：`token` 和 `token_headers` 是 session-scoped 的 fixture，一个测试会话只登录一次

---

## 8. 故障排查

### 8.1 全部返回 503 或连接失败

```
FAILED ... httpx.ConnectError: [Errno 11001] getaddrinfo failed
```

检查：
- VPS 是否在运行：`curl http://47.109.197.217:8001/health`
- 网络是否可达：`ping 47.109.197.217`

### 8.2 全部返回 401

检查 admin 密码是否正确：`curl -X POST http://47.109.197.217:8001/auth/login -d "username=admin&password=admin"`

### 8.3 工作流总是超时

检查 VPS 上的 LLM 连接：
```bash
ssh root@47.109.197.217 "journalctl -u networkagent -n 50 | grep -i 'workflow\|error\|exception'"
```

### 8.4 device CRUD 返回 503

加密服务未初始化。检查 `ENCRYPTION_KEY` 环境变量是否在 VPS 上设置。
