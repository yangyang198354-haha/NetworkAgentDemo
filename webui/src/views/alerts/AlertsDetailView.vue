<!--
  MOD-WEB-F13: AlertsDetailView — 5-Tab alert detail (aligned with REST API).
  @covers REQ-WEBUI-FUNC-002, REQ-WEBUI-FUNC-004
  @covers REQ-DETAIL-001 ~ REQ-DETAIL-006
-->
<template>
  <div class="alert-detail" v-loading="loading">
    <!-- Header -->
    <el-card v-if="alert">
      <template #header>
        <div class="card-header">
          <span>告警详情 — {{ alert.alert_id?.substring(0, 8) }}...</span>
          <el-tag :type="statusColor(alert.status)">{{ alert.status }}</el-tag>
        </div>
      </template>

      <!-- 5-Tab Layout -->
      <el-tabs v-model="activeTab" type="border-card">
        <!-- Tab 1: 基本信息 -->
        <el-tab-pane label="基本信息" name="basic">
          <el-descriptions :column="2" border>
            <el-descriptions-item label="告警ID">{{ alert.alert_id }}</el-descriptions-item>
            <el-descriptions-item label="告警类型">
              <el-tag size="small">{{ alert.alert_type }}</el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="严重级别">{{ alert.severity }}</el-descriptions-item>
            <el-descriptions-item label="来源">{{ alert.source }}</el-descriptions-item>
            <el-descriptions-item label="设备名称">{{ alert.device_info?.device_name }}</el-descriptions-item>
            <el-descriptions-item label="设备IP">{{ alert.device_info?.device_ip }}</el-descriptions-item>
            <el-descriptions-item label="接口">{{ alert.device_info?.interface_name || '-' }}</el-descriptions-item>
            <el-descriptions-item label="MAC地址">{{ alert.device_info?.mac_address || '-' }}</el-descriptions-item>
            <el-descriptions-item label="发生时间" :span="2">{{ formatTime(alert.created_at) }}</el-descriptions-item>
            <el-descriptions-item label="更新时间" :span="2">{{ formatTime(alert.updated_at) }}</el-descriptions-item>
            <el-descriptions-item label="告警内容" :span="2">{{ alert.content }}</el-descriptions-item>
          </el-descriptions>
        </el-tab-pane>

        <!-- Tab 2: 处理时间线 -->
        <el-tab-pane label="处理时间线" name="timeline">
          <el-timeline v-if="timeline.length > 0">
            <el-timeline-item
              v-for="entry in timeline"
              :key="entry.id"
              :timestamp="formatTime(entry.started_at)"
              :color="timelineColor(entry.status)"
            >
              <strong>{{ entry.node_name }}</strong>
              <el-tag :type="timelineStatusTag(entry.status)" size="small" style="margin-left:8px">
                {{ entry.status }}
              </el-tag>
              <p v-if="entry.completed_at" style="color:#909399;font-size:12px">
                完成时间: {{ formatTime(entry.completed_at) }}
              </p>
            </el-timeline-item>
          </el-timeline>
          <el-empty v-else description="暂无时间线记录（LangGraph 节点尚未集成 DB 持久化）" />
        </el-tab-pane>

        <!-- Tab 3: 修复方案 -->
        <el-tab-pane label="修复方案" name="fixplan">
          <template v-if="fixPlan">
            <el-descriptions :column="1" border style="margin-bottom:16px">
              <el-descriptions-item label="模板ID">
                <el-tag type="warning">{{ fixPlan.template_id }}</el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="描述">{{ fixPlan.description }}</el-descriptions-item>
            </el-descriptions>

            <h4 style="margin: 12px 0 8px">参数列表</h4>
            <el-table :data="paramsTable" border size="small" style="margin-bottom:16px" v-if="paramsTable.length > 0">
              <el-table-column prop="key" label="参数名" width="180" />
              <el-table-column prop="value" label="参数值" />
            </el-table>
            <el-empty v-else description="无参数" :image-size="40" />

            <h4 style="margin: 12px 0 8px">CLI 修复命令</h4>
            <template v-if="commands.length > 0">
              <pre class="cli-block"><code>{{ commands.join('\n') }}</code></pre>
            </template>
            <el-empty v-else description="无CLI命令" :image-size="40" />
          </template>
          <el-empty v-else description="暂无修复方案" />
        </el-tab-pane>

        <!-- Tab 4: LLM 调用详情 -->
        <el-tab-pane label="LLM调用详情" name="llm">
          <template v-if="llmCalls.length > 0">
            <el-card
              v-for="(call, idx) in llmCalls"
              :key="idx"
              style="margin-bottom:12px"
              shadow="hover"
            >
              <template #header>
                <div class="llm-header">
                  <span><strong>调用 #{{ idx + 1 }}:</strong> {{ call.endpoint }}</span>
                  <span style="color:#909399;font-size:13px">
                    ⏱ {{ call.elapsed_s }}s &nbsp;|&nbsp;
                    📊 {{ call.prompt_tokens }} → {{ call.completion_tokens }} tokens
                  </span>
                </div>
              </template>

              <el-collapse>
                <el-collapse-item title="📤 Prompt (点击展开)" :name="'prompt-'+idx">
                  <pre class="llm-text">{{ call.prompt }}</pre>
                </el-collapse-item>
                <el-collapse-item title="📥 Response (点击展开)" :name="'resp-'+idx">
                  <pre class="llm-text">{{ call.response }}</pre>
                </el-collapse-item>
              </el-collapse>
            </el-card>
          </template>
          <el-empty v-else description="暂无LLM调用记录" />
        </el-tab-pane>

        <!-- Tab 5: 审批信息 -->
        <el-tab-pane label="审批信息" name="approval">
          <el-descriptions :column="1" border>
            <el-descriptions-item label="风险等级">
              <el-tag :type="riskLevelColor(inferredRiskLevel)" size="large">
                {{ inferredRiskLevel }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="是否需要审批">
              <el-tag :type="approval.need_human_approval ? 'warning' : 'success'" size="large">
                {{ approval.need_human_approval ? '是 ⚠️' : '否（自动执行）✅' }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="审批状态">
              <el-tag :type="approvalStatusColor(approval.approval_status)" size="large">
                {{ approvalStatusText(approval.approval_status) }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="风险等级">
              <el-tag :type="riskLevelColor(approval.risk_level)" size="large">
                {{ approval.risk_level }}
              </el-tag>
            </el-descriptions-item>
          </el-descriptions>
          <el-alert
            v-if="!approval"
            title="审批数据不可用"
            type="warning"
            :closable="false" show-icon
            style="margin-top:12px"
            description="LangGraph 状态不可用，无法获取审批信息。"
          />
        </el-tab-pane>
      </el-tabs>
    </el-card>

    <!-- No alert found -->
    <el-empty v-else description="告警不存在" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useAlertsStore } from '@/stores/alerts'

const route = useRoute()
const store = useAlertsStore()
const alert = ref<any>(null)
const timeline = ref<any[]>([])
const fixPlan = ref<any>(null)
const commands = ref<string[]>([])
const llmCalls = ref<any[]>([])
const approval = ref<any>({ need_human_approval: false, approval_status: 'UNKNOWN', risk_level: 'N/A' })
const loading = ref(false)
const activeTab = ref('basic')

onMounted(async () => {
  loading.value = true
  try {
    const resp: any = await store.fetchAlertDetail(route.params.alertId as string)
    alert.value = resp.alert
    timeline.value = resp.timeline || []
    fixPlan.value = resp.fix_plan || null
    commands.value = resp.commands || []
    llmCalls.value = resp.llm_calls || []
    approval.value = resp.approval || { need_human_approval: false, approval_status: 'UNKNOWN', risk_level: 'N/A' }
  } finally {
    loading.value = false
  }
})

// ── Params table for Tab 3 ──
const paramsTable = computed(() => {
  if (!fixPlan.value?.params) return []
  return Object.entries(fixPlan.value.params).map(([key, value]) => ({ key, value }))
})

// ── Color / text helpers ──
function statusColor(s: string) {
  return { PROCESSING: '', CLOSED: 'success', FAILED: 'danger', REJECTED: 'warning' }[s] || ''
}
function timelineColor(s: string) {
  return { COMPLETED: '#67C23A', RUNNING: '#409EFF', FAILED: '#F56C6C' }[s] || '#909399'
}
function timelineStatusTag(s: string) {
  return { COMPLETED: 'success', RUNNING: '', FAILED: 'danger' }[s] || 'info'
}
function riskLevelColor(level: string) {
  return { 'CRITICAL': 'danger', 'HIGH': 'danger', 'MEDIUM': 'warning', 'LOW': 'success', 'N/A': 'info' }[level] || 'info'
}
function approvalStatusColor(status: string) {
  return { 'APPROVED': 'success', 'NOT_REQUIRED': 'success', 'PENDING': 'warning', 'REJECTED': 'danger', 'UNKNOWN': 'info' }[status] || 'info'
}
function approvalStatusText(status: string) {
  return {
    'PENDING': '待审批',
    'APPROVED': '已批准',
    'REJECTED': '已拒绝',
    'NOT_REQUIRED': '无需审批（自动执行）',
    'UNKNOWN': '未知',
  }[status] || status
}
function formatTime(t: string) {
  return t ? new Date(t + 'Z').toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' }) : '-'
}
</script>

<style scoped>
.card-header { display: flex; justify-content: space-between; align-items: center; }
.llm-header { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px; }
.cli-block {
  background: #1e293b; color: #e2e8f0; padding: 16px; border-radius: 8px;
  overflow-x: auto; font-family: 'Fira Code', 'Cascadia Code', Consolas, monospace;
  font-size: 13px; line-height: 1.6; white-space: pre; margin: 0;
}
.llm-text {
  background: #f8f9fa; color: #1a1a2e; padding: 12px; border-radius: 6px;
  overflow-x: auto; font-size: 12px; line-height: 1.5; white-space: pre-wrap;
  word-break: break-word; max-height: 400px; overflow-y: auto; margin: 0;
}
@media (prefers-color-scheme: dark) {
  .llm-text { background: #1e293b; color: #e2e8f0; }
}
</style>
