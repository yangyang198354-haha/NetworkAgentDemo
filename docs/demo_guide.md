<file_header>
  <author_agent>devops_engineer</author_agent>
  <timestamp>2026-07-10T10:00:00Z</timestamp>
  <project_name>NetworkAgentDemo</project_name>
  <version>0.1.0</version>
  <phase>PHASE_11</phase>
  <status>APPROVED</status>
</file_header>

# NetworkAgentDemo 命令行运行指南

---

## 1. 环境要求

| 项目 | 版本 | 说明 |
|------|------|------|
| Python | 3.11+ | `python3.11`，勿用系统默认 3.6 |
| Git | 2.x | 拉取代码 |
| 磁盘 | > 2GB | venv + 依赖 ~1.5GB |
| 网络 | 出方向 | pip install + DeepSeek API |

---

## 2. 本地开发运行

### 2.1 克隆并安装

```bash
git clone https://github.com/yangyang198354-haha/NetworkAgentDemo.git
cd NetworkAgentDemo
python3.11 -m venv venv
source venv/bin/activate        # Linux/Mac
# venv\Scripts\activate         # Windows

pip install --upgrade pip
pip install -r requirements.txt
```

### 2.2 配置 API Key

```bash
cp .env.example .env
```

编辑 `.env`：
```ini
DEEPSEEK_API_KEY=sk-your-deepseek-api-key
OPENAI_API_KEY=sk-your-openai-api-key    # 可选
```

> 不配置 Key 会进入 Mock 降级模式，LLM 返回预设分析文本，不影响流程。

### 2.3 启动服务

```bash
# 开发模式（前台运行，修改代码自动重载）
python -m uvicorn src.main:app --host 0.0.0.0 --port 8001 --reload

# 生产模式（后台运行）
nohup python -m uvicorn src.main:app --host 0.0.0.0 --port 8001 > /tmp/networkagent.log 2>&1 &
```

启动日志：
```
INFO | Configuration loaded from ./config/config.yaml
INFO | TemplateEngine loaded 6 templates
INFO | RAGService indexed 10 documents
INFO | Building LangGraph StateGraph (14 nodes, 4 conditional edges)
INFO | LangGraph StateGraph compiled successfully
INFO | InspectionScheduler started: interval=5min
INFO | NetworkAgentDemo is ready!
```

### 2.4 验证

```bash
curl http://localhost:8001/health
# → {"status":"healthy","service":"NetworkAgentDemo","components":{"langgraph":true,"rag":true,"scheduler":true}}
```

---

## 3. 触发工作流

### 3.1 三种告警类型

| 类型 | 参数值 | 风险等级 | 审批 | 说明 |
|------|--------|----------|------|------|
| 端口 Down | `PORT_DOWN` | LOW | ❌ 自动执行 | 接口 down → no shutdown |
| CPU 过高 | `CPU_HIGH` | MEDIUM | ❌ 自动执行 | CPU 92% → 限速策略 |
| MAC 漂移 | `MAC_FLAPPING` | **HIGH** | ✅ 需审批 | VLAN 操作 → 端口安全 |

### 3.2 发送模拟告警

```bash
# ─── 端口 Down（自动执行，无需审批）───
curl -X POST "http://localhost:8001/alerts/simulate" \
  -H "Content-Type: application/json" \
  -d '{"alert_type":"PORT_DOWN","device_name":"Core-SW-01","device_ip":"192.168.1.1","interface":"Gi0/1"}'

# ─── CPU 过高（自动执行，无需审批）───
curl -X POST "http://localhost:8001/alerts/simulate" \
  -H "Content-Type: application/json" \
  -d '{"alert_type":"CPU_HIGH","device_name":"Core-SW-01","device_ip":"192.168.1.1"}'

# ─── MAC 漂移（高风险，触发审批）───
curl -X POST "http://localhost:8001/alerts/simulate" \
  -H "Content-Type: application/json" \
  -d '{"alert_type":"MAC_FLAPPING","device_name":"Core-SW-01","device_ip":"192.168.1.1","interface":"Gi0/1"}'
```

返回值：
```json
{
  "message": "Simulated alert accepted",
  "alert_id": "ALT-20260710-143052-a1b2c3d4",
  "alert_type": "PORT_DOWN"
}
```

### 3.3 通过 Webhook 发送（标准方式）

```bash
curl -X POST "http://localhost:8001/webhook/alert" \
  -H "Content-Type: application/json" \
  -d '{
    "source": "zabbix",
    "alert_type": "PORT_DOWN",
    "alert_severity": "MAJOR",
    "alert_content": "Interface Gi0/1 on Core-SW-01 is down. Link protocol is down (notconnect).",
    "device_name": "Core-SW-01",
    "device_ip": "192.168.1.1",
    "interface_name": "Gi0/1",
    "alert_timestamp": "2026-07-10T14:30:00+08:00"
  }'
```

---

## 4. 观测工作流全过程

### 4.1 实时日志跟踪

**终端 1** — 启动服务：
```bash
python -m uvicorn src.main:app --host 0.0.0.0 --port 8001
```

**终端 2** — 发送告警后，终端 1 会输出完整的 14 节点执行日志：

```
2026-07-10 14:30:52.123 | INFO | Node START: receive_alert         [ALT-...d4]
2026-07-10 14:30:52.125 | INFO | Node END:   receive_alert → 0.002s
2026-07-10 14:30:52.126 | INFO | Node START: parse_alert
2026-07-10 14:30:52.128 | INFO | AlertNormalizer: normalized alert → PORT_DOWN on Core-SW-01
2026-07-10 14:30:52.129 | INFO | Node END:   parse_alert → 0.003s
2026-07-10 14:30:52.130 | INFO | Node START: validate_alert
2026-07-10 14:30:52.131 | DEBUG | CE-001: is_valid=True → get_device_info
2026-07-10 14:30:52.132 | INFO | Node START: get_device_info
2026-07-10 14:30:52.133 | INFO | ConfigManager: found device Core-SW-01 (192.168.1.1)
2026-07-10 14:30:52.134 | INFO | Node START: establish_ssh
2026-07-10 14:30:52.135 | INFO | SSH: validating credentials for Core-SW-01 (Mock mode)
2026-07-10 14:30:52.136 | INFO | Node START: collect_diag
2026-07-10 14:30:52.137 | INFO | SwitchDiagTool: executing diagnosis for PORT_DOWN on Core-SW-01
2026-07-10 14:30:52.138 | INFO |   → show interface Gi0/1 status       (0.34s)
2026-07-10 14:30:52.479 | INFO |   → show interface Gi0/1 detail       (0.28s)
2026-07-10 14:30:52.760 | INFO |   → show logging | include Gi0/1      (0.21s)
2026-07-10 14:30:52.971 | INFO | Node START: analyze_root_cause
2026-07-10 14:30:53.210 | INFO | RAGService: retrieved 3 relevant docs for PORT_DOWN
2026-07-10 14:30:54.850 | INFO | LLMService: DeepSeek root_cause completed (856 tokens)
2026-07-10 14:30:54.851 | INFO | Node START: generate_fix_plan
2026-07-10 14:30:55.120 | INFO | LLMService: fill_template_params → TPL-PORT-ENABLE
2026-07-10 14:30:55.320 | INFO | OutputValidator: params validated successfully (3 params)
2026-07-10 14:30:55.321 | INFO | TemplateEngine: rendered TPL-PORT-ENABLE → 5 CLI commands
2026-07-10 14:30:55.322 | INFO | Node START: assess_risk
2026-07-10 14:30:55.323 | INFO | RiskAssessor: risk_level=LOW, reasons=[]
2026-07-10 14:30:55.323 | DEBUG | CE-002: need_human_approval=False → backup_config
2026-07-10 14:30:55.324 | INFO | Node START: backup_config
2026-07-10 14:30:55.450 | INFO | BackupTool: backup created → BKP-20260710-... (101 lines)
2026-07-10 14:30:55.451 | DEBUG | CE-003: backup_success=True → execute_fix
2026-07-10 14:30:55.452 | INFO | Node START: execute_fix
2026-07-10 14:30:55.453 | INFO | SwitchConfigTool: executing 5 commands on Core-SW-01
2026-07-10 14:30:55.953 | INFO |   ✓ configure terminal          (0.10s) success
2026-07-10 14:30:56.053 | INFO |   ✓ interface Gi0/1             (0.10s) success
2026-07-10 14:30:56.153 | INFO |   ✓ no shutdown                 (0.10s) success
2026-07-10 14:30:56.253 | INFO |   ✓ description Auto-recovered   (0.10s) success
2026-07-10 14:30:56.353 | INFO |   ✓ end                          (0.10s) success
2026-07-10 14:30:56.354 | INFO | Node START: verify_fix
2026-07-10 14:30:56.680 | INFO | SwitchDiagTool: post-fix verification → Gi0/1 is up
2026-07-10 14:30:56.681 | INFO | verify_result: verify_passed=True
2026-07-10 14:30:56.681 | INFO | Node START: finish_report
2026-07-10 14:30:57.120 | INFO | LLMService: report generated (420 tokens)
2026-07-10 14:30:57.121 | INFO | Workflow completed: ALT-...d4 → status=CLOSED
```

### 4.2 命令行逐节点跟踪

```bash
# 发送告警后立刻查状态
ALERT_ID="ALT-20260710-143052-a1b2c3d4"

# 查看当前工作流状态
curl -s "http://localhost:8001/workflow/${ALERT_ID}/state" | python -m json.tool
```

输出示例（执行中）：
```json
{
  "alert_id": "ALT-20260710-143052-a1b2c3d4",
  "alert_type": "PORT_DOWN",
  "status": "ACTIVE",
  "device_info": {"device_name": "Core-SW-01", "device_ip": "192.168.1.1"},
  "is_valid": true,
  "diag_data": {
    "show interface Gi0/1 status": "Gi0/1  down    down    ...",
    "show interface Gi0/1 detail": "Hardware is Gigabit Ethernet, ..."
  }
}
```

### 4.3 使用 Swagger UI

浏览器打开 **http://localhost:8001/docs**：

1. `POST /alerts/simulate` → 点 "Try it out" → 选 `PORT_DOWN` → Execute
2. `GET /workflow/{checkpoint_id}/state` → 输入返回的 `alert_id` → 查看状态
3. `GET /approvals/pending` → 查看是否有挂起的审批
4. `POST /approvals/{checkpoint_id}/decide` → 批准/拒绝

---

## 5. 审批流程（仅高风险操作）

### 5.1 流程图

```
收到告警 → 诊断 → 分析 → 生成方案 → 风险评估
                                          │
                          ┌───────────────┴───────────────┐
                          │                               │
                     risk=LOW/MEDIUM                 risk=HIGH
                     (端口Down, CPU高)            (MAC漂移,VLAN变更)
                          │                               │
                          ▼                               ▼
                    自动执行修复                    ⏸️ Interrupt 挂起
                          │                               │
                          │                      GET /approvals/pending
                          │                               │
                          │                      POST ../decide
                          │                         ├─ APPROVED → 继续
                          │                         └─ REJECTED → 关闭
                          │                               │
                          ▼                               ▼
                    验证 → 报告 → END              报告(REJECTED) → END
```

### 5.2 操作命令

```bash
# 1. 发送 MAC 漂移告警（触发审批）
curl -X POST "http://localhost:8001/alerts/simulate" \
  -H "Content-Type: application/json" \
  -d '{"alert_type":"MAC_FLAPPING","device_name":"Core-SW-01","device_ip":"192.168.1.1","interface":"Gi0/1"}'

# 返回 alert_id，例如 ALT-20260710-150000-x1y2z3w4

# 2. 查看挂起的审批
curl http://localhost:8001/approvals/pending | python -m json.tool
```

输出：
```json
[{
  "checkpoint_id": "ALT-20260710-150000-x1y2z3w4",
  "alert_id": "ALT-20260710-150000-x1y2z3w4",
  "alert_type": "MAC_FLAPPING",
  "alert_content": "MAC地址 00:1A:2B:3C:4D:5E 在设备 Core-SW-01 的VLAN 1内发生漂移...",
  "device_name": "Core-SW-01",
  "fix_plan_summary": "在接口 Gi0/1 启用 port-security，限制MAC学习数量为2",
  "risk_level": "HIGH",
  "risk_reasons": ["VLAN操作可能影响二层网络", "switchport配置变更涉及安全策略"]
}]
```

```bash
# 3. 做出审批决定
CHECKPOINT="ALT-20260710-150000-x1y2z3w4"

# 批准
curl -X POST "http://localhost:8001/approvals/${CHECKPOINT}/decide" \
  -H "Content-Type: application/json" \
  -d '{"decision":"APPROVED","operator":"admin","reason":"方案合理，允许执行"}'

# 或拒绝
curl -X POST "http://localhost:8001/approvals/${CHECKPOINT}/decide" \
  -H "Content-Type: application/json" \
  -d '{"decision":"REJECTED","operator":"admin","reason":"涉及核心交换机，人工处理更安全"}'

# 4. 查看最终状态
curl -s "http://localhost:8001/workflow/${CHECKPOINT}/state" | python -m json.tool | grep status
# → "status": "CLOSED"  或  "status": "REJECTED"
```

---

## 6. 定时巡检

服务启动后自动开始，默认每 **5 分钟**巡检一次。日志中可观测：

```
INFO | InspectionScheduler: periodic inspection triggered
INFO |   → checking Core-SW-01 (192.168.1.1)
INFO |   → show interface status → Gi0/1 is up (normal)
INFO |   → checking Access-SW-02 (192.168.1.2)
INFO |   → show processes cpu → 15% (normal)
INFO | InspectionScheduler: inspection complete, 0 alerts generated
```

修改巡检间隔：编辑 `config/config.yaml` → `inspection.interval_minutes`。

---

## 7. 运行测试

```bash
# 全部测试（106 个）
python -m pytest tests/ -v

# 只看某个模块
python -m pytest tests/test_tools.py -v
python -m pytest tests/test_integration.py -v

# 带覆盖率
python -m pytest tests/ -v --cov=src --cov-report=term-missing
```

---

## 8. VPS 生产环境

生产环境已部署在 **http://47.109.197.217:8001**，上述所有命令只需替换 `localhost` 为 `47.109.197.217`。

```bash
# 远程触发（示例）
curl -X POST "http://47.109.197.217:8001/alerts/simulate" \
  -H "Content-Type: application/json" \
  -d '{"alert_type":"PORT_DOWN","device_name":"Core-SW-01","device_ip":"192.168.1.1","interface":"Gi0/1"}'

# 远程日志
ssh root@47.109.197.217 'journalctl -u networkagent -f'
```

---

## 9. 故障排查

| 问题 | 检查 |
|------|------|
| 服务启动失败 | `ss -tlnp \| grep 8001` 检查端口是否被占用 |
| 端口被占用 | 改用其他端口：`--port 8002`，同时修改 `config.yaml` |
| LLM 返回 Mock 文本 | `DEEPSEEK_API_KEY` 未配置或无效，查 `.env` |
| ChromaDB 警告 | sqlite3 版本低，自动降级为内存模式，Demo 可忽略 |
| MAC 漂移不触发审批 | 确认 `RiskAssessor` 命中了 VLAN/switching 正则 |
| 审批列表为空 | MAC 漂移才需审批，PORT_DOWN 和 CPU_HIGH 自动通过 |
