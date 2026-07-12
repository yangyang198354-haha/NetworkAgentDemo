<!--
  MOD-WEB-F19: SystemLogsView — System log viewer with search and filtering.
  @covers REQ-WEBUI-FUNC-021
-->
<template>
  <div class="logs-page">
    <el-card>
      <template #header><span>系统日志</span></template>

      <el-row :gutter="16" class="filter-row">
        <el-col :span="3">
          <el-select v-model="filterLevel" placeholder="日志级别" clearable @change="handleSearch">
            <el-option label="INFO" value="INFO" />
            <el-option label="WARNING" value="WARNING" />
            <el-option label="ERROR" value="ERROR" />
          </el-select>
        </el-col>
        <el-col :span="6">
          <el-input v-model="filterKeyword" placeholder="搜索关键词..." clearable @keyup.enter="handleSearch" />
        </el-col>
        <el-col :span="3">
          <el-button type="primary" @click="handleSearch">搜索</el-button>
        </el-col>
      </el-row>

      <el-table :data="store.logEntries" v-loading="store.loading" stripe max-height="500">
        <el-table-column prop="timestamp" label="时间" width="180">
          <template #default="{ row }">{{ formatTime(row.timestamp) }}</template>
        </el-table-column>
        <el-table-column prop="level" label="级别" width="80">
          <template #default="{ row }">
            <el-tag :type="levelColor(row.level)" size="small">{{ row.level }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="module" label="模块" width="140" show-overflow-tooltip />
        <el-table-column prop="message" label="消息" show-overflow-tooltip />
      </el-table>

      <el-pagination v-model:current-page="store.logPagination.page" :page-size="store.logPagination.pageSize"
        :total="store.logPagination.total" layout="total, prev, pager, next"
        @current-change="handleSearch"
        style="margin-top:16px; justify-content:flex-end" />

      <el-empty v-if="!store.loading && store.logEntries.length === 0" description="暂无日志记录" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useSystemStore } from '@/stores/system'

const store = useSystemStore()
const filterLevel = ref('')
const filterKeyword = ref('')

onMounted(() => store.fetchLogs())

function handleSearch() {
  const filters: any = {}
  if (filterLevel.value) filters.level = filterLevel.value
  if (filterKeyword.value) filters.keyword = filterKeyword.value
  store.fetchLogs(filters)
}

function levelColor(l: string) { return { INFO: '', WARNING: 'warning', ERROR: 'danger' }[l] || '' }
function formatTime(t: string) { return t ? new Date(t + 'Z').toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' }) : '-' }
</script>

<style scoped>
.filter-row { margin-bottom: 16px; }
</style>
