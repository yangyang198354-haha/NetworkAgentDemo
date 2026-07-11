<!--
  MOD-WEB-F15: ApprovalsPendingView — Pending approval list.
  @covers REQ-WEBUI-FUNC-007
-->
<template>
  <div class="approvals-page">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>待审批列表</span>
          <el-badge v-if="store.pendingCount > 0" :value="store.pendingCount" type="danger" />
        </div>
      </template>

      <el-table :data="store.pendingList" v-loading="store.loading" stripe>
        <el-table-column prop="alert_id" label="告警ID" width="150" show-overflow-tooltip />
        <el-table-column label="风险等级" width="100">
          <template #default="{ row }">
            <el-tag :type="riskColor(row.risk_level)" size="small">{{ row.risk_level }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="修复方案" show-overflow-tooltip width="240">
          <template #default="{ row }">
            {{ row.fix_plan?.description || row.fix_plan?.template_id || '-' }}
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="挂起时间" width="180">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <el-button text type="primary" @click="$router.push(`/approvals/${row.checkpoint_id}`)">审批</el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-empty v-if="!store.loading && store.pendingList.length === 0" description="当前没有待审批项" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { useApprovalsStore } from '@/stores/approvals'

const store = useApprovalsStore()

onMounted(() => store.fetchPendingApprovals())

function riskColor(r: string) { return { LOW: 'info', MEDIUM: 'warning', HIGH: 'danger', CRITICAL: 'danger' }[r] || '' }
function formatTime(t: string) { return t ? new Date(t).toLocaleString('zh-CN') : '-' }
</script>

<style scoped>
.card-header { display: flex; align-items: center; gap: 12px; }
</style>
