<!--
  MOD-WEB-F17: InspectionConfigView — Inspection config + systemd status + manual trigger.
  @covers REQ-INSP-001, REQ-INSP-005, REQ-INSP-008

  v0.2.0 enhancements (REQ-INSP-005, REQ-INSP-008):
    - New systemd status panel (timer/service state indicators + polling)
    - New control button group (start/stop/restart/enable/disable)
    - polling_interval → retry_backoff field replacement
    - systemd unavailable degraded display
-->
<template>
  <div class="inspection-page">
    <!-- v0.2.0: systemd Status Panel (REQ-INSP-005) -->
    <el-alert v-if="!store.systemdAvailable" type="info" show-icon :closable="false"
      title="当前环境不支持 systemd，定时巡检功能不可用。手动触发仍可使用。"
      style="margin-bottom:20px" />

    <el-card v-if="store.systemdAvailable" class="status-panel" v-loading="statusLoading">
      <template #header>
        <div class="card-header">
          <span>巡检服务状态</span>
          <el-tag :type="timerActive ? 'success' : 'info'" size="small">
            {{ timerActive ? '运行中' : '已停止' }}
          </el-tag>
          <el-tag :type="timerEnabled ? 'primary' : 'warning'" size="small" style="margin-left:8px">
            {{ timerEnabled ? '已启用' : '已禁用' }}
          </el-tag>
        </div>
      </template>

      <el-descriptions :column="3" border size="small">
        <el-descriptions-item label="定时器状态">
          <span class="status-dot" :class="timerActive ? 'dot-active' : 'dot-inactive'"></span>
          {{ store.timerStatus?.activeState || '-' }}
        </el-descriptions-item>
        <el-descriptions-item label="服务状态">
          {{ store.serviceStatus?.activeState || '-' }} / {{ store.serviceStatus?.subState || '-' }}
        </el-descriptions-item>
        <el-descriptions-item label="下次触发">
          {{ store.timerStatus?.nextTrigger ? formatTime(store.timerStatus.nextTrigger) : '无（已停止）' }}
        </el-descriptions-item>
        <el-descriptions-item label="最近巡检时间">
          {{ store.lastInspection?.completed_at ? formatTime(store.lastInspection.completed_at) : '暂无巡检记录' }}
        </el-descriptions-item>
        <el-descriptions-item label="最近巡检状态">
          <el-tag v-if="store.lastInspection" :type="statusTagType(store.lastInspection.status)" size="small">
            {{ store.lastInspection.status }}
          </el-tag>
          <span v-else>-</span>
        </el-descriptions-item>
        <el-descriptions-item label="异常 / 设备数">
          <span v-if="store.lastInspection">
            {{ store.lastInspection.anomaly_count }} / {{ store.lastInspection.total_devices }}
          </span>
          <span v-else>-</span>
        </el-descriptions-item>
      </el-descriptions>

      <!-- v0.2.0: Control Button Group — always enabled, backend validates -->
      <div class="control-buttons" style="margin-top:16px;display:flex;gap:8px;flex-wrap:wrap">
        <el-button type="success" :loading="actionLoading === 'enable'"
          @click="confirmAction('enable')">
          ⏰ 启用定时巡检
        </el-button>
        <el-button type="danger" :loading="actionLoading === 'disable'"
          @click="confirmAction('disable')">
          ⏸ 停止定时巡检
        </el-button>
      </div>
    </el-card>

    <el-row :gutter="20" style="margin-top:20px">
      <!-- v0.2.0: Configuration Form (polling_interval → retry_backoff) -->
      <el-col :span="12">
        <el-card>
          <template #header><span>巡检配置</span></template>
          <el-form label-width="150px" v-loading="loading">
            <el-form-item label="巡检间隔(分钟)">
              <el-input-number v-model="configForm.interval_minutes" :min="1" :max="1440" />
            </el-form-item>
            <el-form-item label="诊断超时(秒)">
              <el-input-number v-model="configForm.timeout_seconds" :min="5" :max="600" />
            </el-form-item>
            <el-form-item label="重试次数">
              <el-input-number v-model="configForm.retry_max" :min="0" :max="10" />
            </el-form-item>
            <!-- v0.2.0: polling_interval → retry_backoff -->
            <el-form-item label="重试间隔(秒)">
              <el-input-number v-model="configForm.retry_backoff" :min="1" :max="300" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="saving" @click="handleSave">保存配置</el-button>
            </el-form-item>
          </el-form>
        </el-card>
      </el-col>

      <el-col :span="12">
        <el-card>
          <template #header><span>手动触发巡检</span></template>
          <p style="color:#909399;margin-bottom:16px">对所有纳管设备立即执行一次完整的巡检操作。</p>
          <el-button type="primary" :loading="store.inspectionRunning" :disabled="store.inspectionRunning"
            @click="handleTrigger">
            {{ store.inspectionRunning ? '巡检执行中...' : '手动触发巡检' }}
          </el-button>
          <el-button link @click="$router.push('/inspection/history')" style="margin-left:16px">
            查看巡检历史 &rarr;
          </el-button>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref, computed, onMounted, onUnmounted } from 'vue'
import { useInspectionStore } from '@/stores/inspection'
import { ElMessage, ElMessageBox } from 'element-plus'

const store = useInspectionStore()
const loading = ref(false)
const saving = ref(false)
const statusLoading = ref(false)
const actionLoading = ref<string | null>(null)

// Polling timer for status (REQ-INSP-005: 5-second interval)
let statusPollingTimer: ReturnType<typeof setInterval> | null = null

const configForm = reactive({
  interval_minutes: 5,
  timeout_seconds: 30,
  retry_max: 3,
  retry_backoff: 5,  // v0.2.0: replaces polling_interval
})

// ── Computed: button enable/disable logic (REQ-INSP-008) ──

const timerActive = computed(() =>
  store.timerStatus?.activeState === 'active'
)
const timerEnabled = computed(() =>
  store.timerStatus?.unitFileState === 'enabled'
)

// Buttons always enabled — backend returns error if action invalid

// ── Lifecycle ─────────────────────────────────────────────

onMounted(async () => {
  loading.value = true
  try {
    await store.fetchConfig()
    const c = store.config
    configForm.interval_minutes = parseInt(c['inspection.interval_minutes'] || '5')
    configForm.timeout_seconds = parseInt(c['diagnosis.timeout_seconds'] || '30')
    configForm.retry_max = parseInt(c['diagnosis.retry_max'] || '3')
    configForm.retry_backoff = parseInt(c['diagnosis.retry_backoff'] || '5')
  } finally {
    loading.value = false
  }

  // Initial status fetch + start polling (REQ-INSP-005: 5s interval)
  await refreshStatus()
  statusPollingTimer = setInterval(refreshStatus, 5000)
})

onUnmounted(() => {
  if (statusPollingTimer) {
    clearInterval(statusPollingTimer)
    statusPollingTimer = null
  }
})

async function refreshStatus() {
  statusLoading.value = true
  try {
    await store.fetchStatus()
  } finally {
    statusLoading.value = false
  }
}

// ── Save config ───────────────────────────────────────────

async function handleSave() {
  saving.value = true
  try {
    const resp = await store.updateConfig({
      inspection_interval_minutes: configForm.interval_minutes,
      diagnosis_timeout_seconds: configForm.timeout_seconds,
      diagnosis_retry_max: configForm.retry_max,
      retry_backoff_seconds: configForm.retry_backoff,
    })
    const syncStatus = resp.systemd_sync
    if (syncStatus === 'failed') {
      ElMessage.warning('配置已保存至数据库，但 systemd 同步失败：' + (resp.systemd_error || '未知错误'))
    } else {
      ElMessage.success('巡检配置已更新' + (syncStatus === 'success' ? '并同步到 systemd' : ''))
    }
    // Refresh status after config save
    await refreshStatus()
  } finally {
    saving.value = false
  }
}

// ── Manual trigger ────────────────────────────────────────

async function handleTrigger() {
  try {
    await store.triggerInspection()
    ElMessage.success('巡检已触发')
    await refreshStatus()
  } catch (e: any) {
    // Error handled by Axios interceptor, but also show specific message
    const detail = e?.response?.data?.detail
    if (detail) {
      ElMessage.error(detail)
    }
  }
}

// ── Control button actions with confirmation ──────────────

const confirmMessages: Record<string, { title: string; message: string }> = {
  start: {
    title: '确认启动巡检服务？',
    message: '将立即执行一次巡检操作。'
  },
  stop: {
    title: '确认停止巡检服务？',
    message: '停止后正在执行的巡检将被中断，但定时器（timer）仍保持启用，下次仍会按计划触发。'
  },
  restart: {
    title: '确认重启巡检服务？',
    message: '若当前有巡检在执行则先停止再重新启动。'
  },
  enable: {
    title: '确认启用巡检定时器？',
    message: '启用后定时器将开始按计划触发巡检，且系统重启后自动恢复。'
  },
  disable: {
    title: '确认禁用巡检定时器？',
    message: '禁用后定时巡检将停止触发，且系统重启后不会自动恢复。您仍然可以手动触发巡检。'
  }
}

async function confirmAction(action: string) {
  const msg = confirmMessages[action]
  if (!msg) return

  try {
    await ElMessageBox.confirm(msg.message, msg.title, {
      confirmButtonText: '确认',
      cancelButtonText: '取消',
      type: action === 'stop' || action === 'disable' ? 'warning' : 'info'
    })
  } catch {
    return // User cancelled
  }

  await executeAction(action)
}

async function executeAction(action: string) {
  actionLoading.value = action
  try {
    let resp: any
    switch (action) {
      case 'start': resp = await store.startService(); break
      case 'stop': resp = await store.stopService(); break
      case 'restart': resp = await store.restartService(); break
      case 'enable': resp = await store.enableTimer(); break
      case 'disable': resp = await store.disableTimer(); break
    }
    ElMessage.success(resp?.message || `${action} 操作成功`)
    // Refresh status immediately after action
    await refreshStatus()
  } catch (e: any) {
    const detail = e?.response?.data?.detail
    ElMessage.error(detail || `${action} 操作失败`)
  } finally {
    actionLoading.value = null
  }
}

// ── Helpers ───────────────────────────────────────────────

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
.inspection-page {
  padding: 4px;
}

.status-panel {
  margin-bottom: 0;
}

.card-header {
  display: flex;
  align-items: center;
  gap: 8px;
}

.status-dot {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  margin-right: 6px;
  vertical-align: middle;
}

.dot-active {
  background-color: #67c23a;
  box-shadow: 0 0 4px #67c23a;
}

.dot-inactive {
  background-color: #c0c4cc;
}

.control-buttons .el-button {
  min-width: 100px;
}
</style>
