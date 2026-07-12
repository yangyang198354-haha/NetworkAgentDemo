<!--
  MOD-WEB-F15: ApprovalsHistoryView — Approval history list.
  @covers REQ-WEBUI-FUNC-009
-->
<template>
  <div class="history-page">
    <el-card>
      <template #header><span>审批历史</span></template>

      <el-select v-model="filterDecision" placeholder="审批决定" clearable @change="onFilter" style="width:160px;margin-bottom:16px">
        <el-option label="APPROVED" value="APPROVED" />
        <el-option label="REJECTED" value="REJECTED" />
      </el-select>

      <el-table :data="store.historyList" v-loading="store.loading" stripe>
        <el-table-column prop="alert_id_fk" label="告警ID" width="150" show-overflow-tooltip />
        <el-table-column prop="decision" label="决定" width="100">
          <template #default="{ row }">
            <el-tag :type="row.decision === 'APPROVED' ? 'success' : 'danger'" size="small">{{ row.decision }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="risk_level" label="风险等级" width="100" />
        <el-table-column prop="note" label="备注" show-overflow-tooltip />
        <el-table-column prop="decided_by" label="审批人" width="100" />
        <el-table-column prop="decided_at" label="审批时间" width="180">
          <template #default="{ row }">{{ formatTime(row.decided_at) }}</template>
        </el-table-column>
      </el-table>

      <el-pagination v-model:current-page="store.pagination.page" :page-size="store.pagination.pageSize"
        :total="store.pagination.total" layout="total, prev, pager, next" @current-change="store.fetchHistory()"
        style="margin-top:16px; justify-content:flex-end" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useApprovalsStore } from '@/stores/approvals'

const store = useApprovalsStore()
const filterDecision = ref('')

onMounted(() => store.fetchHistory())
function onFilter() { store.fetchHistory(filterDecision.value ? { decision: filterDecision.value } : {}) }
function formatTime(t: string) {
  if (!t) return '-'
  const fixed = /[Zz]$|[+-]\d{2}:\d{2}$/.test(t) ? t : t + 'Z'
  return new Date(fixed).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' })
}
</script>
