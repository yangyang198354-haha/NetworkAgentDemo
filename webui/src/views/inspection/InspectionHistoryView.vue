<!--
  MOD-WEB-F17: InspectionHistoryView — Inspection history list.
  @covers REQ-WEBUI-FUNC-015
-->
<template>
  <div class="history-page">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>巡检历史</span>
          <el-button @click="$router.push('/inspection')">&larr; 返回巡检配置</el-button>
        </div>
      </template>

      <el-select v-model="filterMode" placeholder="触发方式" clearable @change="onFilter" style="width:160px;margin-bottom:16px">
        <el-option label="定时" value="SCHEDULED" />
        <el-option label="手动" value="MANUAL" />
      </el-select>

      <el-table :data="store.historyList" v-loading="store.loading" stripe>
        <el-table-column prop="trigger_mode" label="触发方式" width="100">
          <template #default="{ row }">
            <el-tag :type="row.trigger_mode === 'MANUAL' ? 'warning' : ''" size="small">
              {{ row.trigger_mode === 'MANUAL' ? '手动' : '定时' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="total_devices" label="检查设备数" width="120" />
        <el-table-column prop="anomaly_count" label="发现异常数" width="120" />
        <el-table-column prop="started_at" label="开始时间" width="180">
          <template #default="{ row }">{{ formatTime(row.started_at) }}</template>
        </el-table-column>
        <el-table-column prop="completed_at" label="完成时间" width="180">
          <template #default="{ row }">{{ formatTime(row.completed_at) }}</template>
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
import { useInspectionStore } from '@/stores/inspection'

const store = useInspectionStore()
const filterMode = ref('')

onMounted(() => store.fetchHistory())
function onFilter() { store.fetchHistory(filterMode.value ? { trigger_mode: filterMode.value } : {}) }
function formatTime(t: string) { return t ? new Date(t).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' }) : '-' }
</script>

<style scoped>
.card-header { display: flex; justify-content: space-between; align-items: center; }
</style>
