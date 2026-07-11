<!--
  MOD-WEB-F13: AlertsListView — Alert list with filters and pagination.
  @covers REQ-WEBUI-FUNC-001
-->
<template>
  <div class="alerts-page">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>告警列表</span>
          <el-button type="primary" @click="$router.push('/alerts/simulate')">模拟告警</el-button>
        </div>
      </template>

      <!-- Filters -->
      <el-row :gutter="16" class="filter-row">
        <el-col :span="4">
          <el-select v-model="store.filters.alert_type" placeholder="告警类型" clearable @change="onFilterChange">
            <el-option label="MAC_FLAPPING" value="MAC_FLAPPING" />
            <el-option label="PORT_DOWN" value="PORT_DOWN" />
            <el-option label="CPU_HIGH" value="CPU_HIGH" />
          </el-select>
        </el-col>
        <el-col :span="4">
          <el-select v-model="store.filters.severity" placeholder="严重级别" clearable @change="onFilterChange">
            <el-option label="CRITICAL" value="CRITICAL" />
            <el-option label="MAJOR" value="MAJOR" />
            <el-option label="MINOR" value="MINOR" />
            <el-option label="WARNING" value="WARNING" />
          </el-select>
        </el-col>
        <el-col :span="4">
          <el-select v-model="store.filters.status" placeholder="状态" clearable @change="onFilterChange">
            <el-option label="PROCESSING" value="PROCESSING" />
            <el-option label="CLOSED" value="CLOSED" />
            <el-option label="FAILED" value="FAILED" />
            <el-option label="REJECTED" value="REJECTED" />
          </el-select>
        </el-col>
        <el-col :span="4">
          <el-select v-model="store.filters.source" placeholder="来源" clearable @change="onFilterChange">
            <el-option label="WEBHOOK" value="WEBHOOK" />
            <el-option label="INSPECTION" value="INSPECTION" />
            <el-option label="MOCK" value="MOCK" />
          </el-select>
        </el-col>
      </el-row>

      <!-- Table -->
      <el-table :data="store.alertList" v-loading="store.loading" stripe>
        <el-table-column prop="alert_id" label="告警ID" width="150" show-overflow-tooltip />
        <el-table-column prop="alert_type" label="类型" width="120">
          <template #default="{ row }">
            <el-tag :type="typeColor(row.alert_type)" size="small">{{ row.alert_type }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="severity" label="严重级别" width="100">
          <template #default="{ row }">
            <el-tag :type="severityColor(row.severity)" size="small">{{ row.severity }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="设备" width="120" show-overflow-tooltip>
          <template #default="{ row }">{{ row.device_info?.device_name || '-' }}</template>
        </el-table-column>
        <el-table-column prop="source" label="来源" width="100" />
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusColor(row.status)" size="small">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="content" label="描述" show-overflow-tooltip />
        <el-table-column prop="created_at" label="时间" width="180">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="80" fixed="right">
          <template #default="{ row }">
            <el-button text type="primary" @click="$router.push(`/alerts/${row.alert_id}`)">详情</el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- Pagination -->
      <el-pagination
        v-model:current-page="store.pagination.page"
        :page-size="store.pagination.pageSize"
        :total="store.pagination.total"
        layout="total, prev, pager, next"
        @current-change="store.fetchAlerts()"
        style="margin-top:16px; justify-content:flex-end"
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { useAlertsStore } from '@/stores/alerts'

const store = useAlertsStore()

onMounted(() => store.fetchAlerts())

function onFilterChange() { store.updateFilters({}); store.fetchAlerts() }
function typeColor(t: string) { return { MAC_FLAPPING: 'danger', PORT_DOWN: 'warning', CPU_HIGH: '' }[t] || '' }
function severityColor(s: string) { return { CRITICAL: 'danger', MAJOR: 'warning', MINOR: '', WARNING: 'info' }[s] || '' }
function statusColor(s: string) { return { PROCESSING: '', CLOSED: 'success', FAILED: 'danger', REJECTED: 'warning' }[s] || '' }
function formatTime(t: string) { return t ? new Date(t).toLocaleString('zh-CN') : '-' }
</script>

<style scoped>
.filter-row { margin-bottom: 16px; }
.card-header { display: flex; justify-content: space-between; align-items: center; }
</style>
