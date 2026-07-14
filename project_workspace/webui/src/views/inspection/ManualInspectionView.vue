<!--
  MOD-WEB-MANUAL-001: ManualInspectionView — Manual inspection trigger page.
  @module MOD-WEB-MANUAL-001
  @implements REQ-FUNC-008
  @depends MOD-WEB-ROUTER-001
  @author sub_agent_software_developer

  v0.2.0-unified: Extracted from InspectionConfigView.vue as standalone page.
  Provides manual trigger button, execution status, and recent inspection summary.
-->
<template>
  <div class="manual-inspection">
    <h2>手动巡检</h2>

    <!-- Trigger area -->
    <el-card class="trigger-card">
      <template #header>
        <span>触发巡检</span>
      </template>
      <p style="color: #909399; margin-bottom: 16px">
        对全部纳管设备立即执行一次完整巡检操作。发现异常将自动创建告警并触发 LangGraph 修复工作流。
      </p>
      <el-button
        type="primary"
        :loading="triggering"
        :disabled="triggering || store.inspectionRunning"
        @click="handleTrigger"
      >
        {{ triggering || store.inspectionRunning ? '正在执行中...' : '立即执行巡检' }}
      </el-button>
      <el-button link @click="$router.push('/inspection/history')" style="margin-left: 16px">
        查看巡检历史 &rarr;
      </el-button>
    </el-card>

    <!-- Status alert (if running) -->
    <el-alert
      v-if="store.inspectionRunning"
      title="巡检执行中"
      type="info"
      :closable="false"
      show-icon
      style="margin-top: 16px"
    >
      巡检正在后台执行，结果将在完成后自动显示。
    </el-alert>

    <!-- Execution result -->
    <el-alert
      v-if="lastResult"
      :title="lastResult.title"
      :type="lastResult.type"
      :closable="true"
      show-icon
      style="margin-top: 16px"
      @close="lastResult = null"
    >
      {{ lastResult.message }}
    </el-alert>

    <!-- systemd Status Panel -->
    <el-card class="status-panel" style="margin-top: 20px" v-loading="statusLoading">
      <template #header>
        <div style="display: flex; align-items: center; gap: 8px">
          <span>巡检服务状态</span>
          <el-tag v-if="store.timerStatus" :type="timerActive ? 'success' : 'info'" size="small">
            {{ timerActive ? '运行中' : '已停止' }}
          </el-tag>
          <el-tag v-if="!store.systemdAvailable" type="warning" size="small">systemd 不可用</el-tag>
          <el-tag v-if="store.statusError" type="danger" size="small">刷新失败</el-tag>
        </div>
      </template>

      <el-descriptions :column="2" border size="small">
        <el-descriptions-item label="定时器状态">
          {{ store.timerStatus?.activeState || '-' }}
        </el-descriptions-item>
        <el-descriptions-item label="服务状态">
          {{ store.serviceStatus?.activeState || '-' }} / {{ store.serviceStatus?.subState || '-' }}
        </el-descriptions-item>
        <el-descriptions-item label="上次巡检时间">
          {{ store.lastInspection?.completed_at ? formatTime(store.lastInspection.completed_at) : '暂无记录' }}
        </el-descriptions-item>
        <el-descriptions-item label="上次巡检状态">
          <el-tag v-if="store.lastInspection" :type="statusTagType(store.lastInspection.status)" size="small">
            {{ store.lastInspection.status }}
          </el-tag>
          <span v-else>-</span>
        </el-descriptions-item>
      </el-descriptions>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useInspectionStore } from '@/stores/inspection'
import { ElMessage } from 'element-plus'

const store = useInspectionStore()
const triggering = ref(false)
const statusLoading = ref(false)

const lastResult = ref<{ title: string; type: string; message: string } | null>(null)

const timerActive = computed(() =>
  store.timerStatus?.activeState === 'active'
)

onMounted(async () => {
  statusLoading.value = true
  try {
    await store.fetchStatus()
  } finally {
    statusLoading.value = false
  }
})

async function handleTrigger() {
  triggering.value = true
  lastResult.value = null
  try {
    await store.triggerInspection()
    ElMessage.success('巡检已触发，正在后台执行')
    lastResult.value = {
      title: '触发成功',
      type: 'success',
      message: '巡检已触发，正在对所有纳管设备执行巡检。结果将在完成后自动显示。',
    }
    await store.fetchStatus()
  } catch (e: any) {
    const detail = e?.response?.data?.detail
    lastResult.value = {
      title: '触发失败',
      type: 'error',
      message: detail || '巡检触发失败，请稍后重试',
    }
    ElMessage.error(detail || '巡检触发失败')
  } finally {
    triggering.value = false
  }
}

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
.manual-inspection {
  padding: 4px;
}

.trigger-card {
  margin-bottom: 0;
}

.status-panel {
  margin-bottom: 0;
}

</style>
