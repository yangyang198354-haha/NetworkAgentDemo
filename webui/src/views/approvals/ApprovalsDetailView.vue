<!--
  MOD-WEB-F15: ApprovalsDetailView — Approval decision page.
  @covers REQ-WEBUI-FUNC-008
-->
<template>
  <div class="approval-detail" v-loading="loading">
    <el-card v-if="item">
      <template #header><span>审批详情 — {{ item.checkpoint_id?.substring(0, 8) }}...</span></template>

      <el-descriptions :column="2" border>
        <el-descriptions-item label="告警ID">{{ item.alert_id }}</el-descriptions-item>
        <el-descriptions-item label="风险等级">
          <el-tag :type="riskColor(item.risk_level)">{{ item.risk_level }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="挂起时间">{{ formatTime(item.created_at) }}</el-descriptions-item>
        <el-descriptions-item label="当前决策">{{ item.decision || 'PENDING' }}</el-descriptions-item>
      </el-descriptions>

      <el-divider />
      <h3>修复方案</h3>
      <pre class="fix-plan-json">{{ JSON.stringify(item.fix_plan, null, 2) }}</pre>

      <el-divider />

      <div class="decision-actions" v-if="item.decision === 'PENDING' || !item.decision">
        <el-input v-model="note" type="textarea" :rows="3" placeholder="审批备注（可选）" style="margin-bottom:16px" />
        <el-button type="success" @click="showConfirm('APPROVED')">
          <el-icon><Check /></el-icon> 批准
        </el-button>
        <el-button type="danger" @click="showConfirm('REJECTED')">
          <el-icon><Close /></el-icon> 拒绝
        </el-button>
      </div>
      <el-result v-else icon="success" title="已处理" :sub-title="`审批结果: ${item.decision}`" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useApprovalsStore } from '@/stores/approvals'
import { ElMessageBox, ElMessage } from 'element-plus'

const route = useRoute()
const router = useRouter()
const store = useApprovalsStore()

const item = ref<any>(null)
const note = ref('')
const loading = ref(false)

onMounted(async () => {
  loading.value = true
  try {
    await store.fetchPendingApprovals()
    item.value = store.pendingList.find(p => p.checkpoint_id === route.params.checkpointId as string)
  } finally {
    loading.value = false
  }
})

function showConfirm(decision: string) {
  const msg = decision === 'APPROVED' ? '确认批准此修复方案？该操作将下发配置到设备。' : '确认拒绝此修复方案？'
  ElMessageBox.confirm(msg, '请确认', { confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning' })
    .then(async () => {
      await store.submitDecision(route.params.checkpointId as string, decision, note.value)
      ElMessage.success('审批已提交')
      router.push('/approvals/pending')
    })
    .catch(() => {})
}

function riskColor(r: string) { return { LOW: 'info', MEDIUM: 'warning', HIGH: 'danger', CRITICAL: 'danger' }[r] || '' }
function formatTime(t: string) { return t ? new Date(t).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' }) : '-' }
</script>

<style scoped>
.fix-plan-json {
  background: #f5f7fa;
  padding: 16px;
  border-radius: 4px;
  font-size: 13px;
  max-height: 400px;
  overflow-y: auto;
}
.decision-actions {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 12px;
}
</style>
