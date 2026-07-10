# Project Brief — NetworkAgentDemo

## 项目背景
基于 LangChain + LangGraph 的交换机巡检与故障自愈 Agent Demo 项目。
典型网络运维闭环 Agent 场景：被动接收网管告警 + 主动定期巡检，通过 LLM 推理完成故障诊断，最终自动下发配置修复。

## 核心设计原则
"模板化操作兜底 + LLM 灵活推理"，绝对禁止 LLM 自由生成设备配置命令，避免生产事故。

## 技术约束
- LLM：使用 openai Python SDK，base_url 指向 DeepSeek API，模型使用 deepseek-chat
- 目标操作系统：Linux
- 后期会用真实 TP-Link 交换机替换 Mock 层（TP-Link 通常用 SSH/CLI，命令风格接近 Cisco IOS）

## Demo 范围策略
- 触发层：Mock Webhook（脚本模拟 Zabbix 告警推送）
- Agent 编排层：完整实现 LangGraph 状态机（含所有节点 + Interrupt 人工审批）
- 工具层：全部 Mock 实现，但预留 TP-Link 交换机真实接口
- LLM 调用：真实 API 调用 DeepSeek
- 告警类型覆盖：MAC 地址漂移、端口 Down、CPU 利用率过高

## 架构分层
### 触发层
对接网管系统，通过 Webhook 接收告警；支持定时触发主动巡检。

### Agent 编排层
LangGraph 构建有限状态机，告警→诊断→修复→验证→闭环。

### 工具层
所有外部系统交互封装成 LangChain 标准 Tool：
- SwitchConfigTool：配置下发（NAPALM）
- SwitchDiagTool：诊断命令执行（Netmiko）
- KnowledgeBaseTool：RAG 知识库检索
- BackupTool：配置备份与回滚

### 资源层
预沉淀各厂商交换机命令模板、故障处理预案。

## LangGraph 状态机
全局状态 NetworkAgentState(TypedDict)，字段包括：
alert_id, alert_type, alert_content, device_info, diag_commands, diag_result,
root_cause, knowledge_refs, fix_plan, need_human_approval, approval_status,
exec_log, config_backup, verify_result, final_report, status

节点流转：
接收告警 → 告警解析 → 告警有效性校验 → 获取设备信息 → 建立SSH连接 →
采集诊断信息 → 根因分析+知识库检索 → 生成修复方案 → 风险评估 →
人工审批 → 备份配置 → 执行修复 → 结果验证 → 生成报告+关闭告警

## 安全与可靠性要求
- 命令模板化：LLM 只能填参数，禁止自由生成命令
- 配置必备份：修改前自动备份 running-config
- 高风险必审批：端口 shutdown、VLAN 删除等强制人工审批
- 最小权限账号
- 自动回滚、超时重试、幂等设计、灰度执行
- 全链路日志与操作审计

## 典型场景：MAC 地址漂移完整闭环
告警接入 → 自动诊断 → 根因分析(LLM+RAG) → 生成修复方案(模板匹配) → 人工审批 → 执行与验证 → 生成报告关闭告警
