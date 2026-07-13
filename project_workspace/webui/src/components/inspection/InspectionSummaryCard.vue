<!--
  MOD-005: InspectionSummaryCard — Inline inspection execution summary.
  @implements IFC-005-01, IFC-005-02
  @depends none (pure display component, receives data via Props)
  @author sub_agent_software_developer
  @covers REQ-FUNC-002, US-002
-->
<template>
  <el-card class="summary-card" v-loading="loading">
    <template #header>
      <span>最近巡检摘要</span>
    </template>

    <el-table v-if="records.length > 0" :data="records" stripe size="small">
      <el-table-column prop="trigger_mode" label="触发模式" width="100">
        <template #default="{ row }">
          <el-tag :type="row.trigger_mode === 'MANUAL' ? 'warning' : ''" size="small">
            {{ row.trigger_mode === 'MANUAL' ? '手动' : '定时' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="started_at" label="开始时间" width="180">
        <template #default="{ row }">{{ formatTime(row.started_at) }}</template>
      </el-table-column>
      <el-table-column prop="completed_at" label="结束时间" width="180">
        <template #default="{ row }">{{ formatTime(row.completed_at) }}</template>
      </el-table-column>
      <el-table-column prop="status" label="状态" width="100">
        <template #default="{ row }">
          <el-tag v-if="row.status" :type="statusTagType(row.status)" size="small">
            {{ row.status }}
          </el-tag>
          <span v-else>-</span>
        </template>
      </el-table-column>
      <el-table-column label="异常/总数" width="100">
        <template #default="{ row }">
          {{ row.anomaly_count ?? '-' }} / {{ row.total_devices ?? '-' }}
        </template>
      </el-table-column>
    </el-table>

    <el-empty v-else description="暂无巡检记录" :image-size="80" />
  </el-card>
</template>

<script setup lang="ts">
interface Props {
  records: any[]
  loading: boolean
}

defineProps<Props>()

function formatTime(t: string | null): string {
  if (!t) return '-'
  const fixed = /[Zz]$|[+-]\d{2}:\d{2}$/.test(t) ? t : t + 'Z'
  return new Date(fixed).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' })
}

function statusTagType(status: string): string {
  switch (status) {
    case 'SUCCESS': return 'success'
    case 'PARTIAL': return 'warning'
    case 'FAILED': return 'danger'
    default: return 'info'
  }
}
</script>

<style scoped>
.summary-card {
  margin-top: 20px;
}
</style>
