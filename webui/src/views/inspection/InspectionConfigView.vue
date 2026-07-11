<!--
  MOD-WEB-F17: InspectionConfigView — Inspection interval config + manual trigger.
  @covers REQ-WEBUI-FUNC-013, REQ-WEBUI-FUNC-014
-->
<template>
  <div class="inspection-page">
    <el-row :gutter="20">
      <el-col :span="12">
        <el-card>
          <template #header><span>巡检配置</span></template>
          <el-form label-width="140px" v-loading="loading">
            <el-form-item label="巡检间隔(分钟)">
              <el-input-number v-model="configForm.interval_minutes" :min="1" :max="1440" />
            </el-form-item>
            <el-form-item label="诊断超时(秒)">
              <el-input-number v-model="configForm.timeout_seconds" :min="5" :max="300" />
            </el-form-item>
            <el-form-item label="重试次数">
              <el-input-number v-model="configForm.retry_max" :min="0" :max="10" />
            </el-form-item>
            <el-form-item label="轮询间隔(秒)">
              <el-input-number v-model="configForm.polling_interval" :min="1" :max="60" />
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
          <el-button type="text" @click="$router.push('/inspection/history')" style="margin-left:16px">
            查看巡检历史 &rarr;
          </el-button>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref, onMounted } from 'vue'
import { useInspectionStore } from '@/stores/inspection'
import { ElMessage } from 'element-plus'

const store = useInspectionStore()
const loading = ref(false)
const saving = ref(false)

const configForm = reactive({
  interval_minutes: 5,
  timeout_seconds: 30,
  retry_max: 3,
  polling_interval: 3,
})

onMounted(async () => {
  loading.value = true
  try {
    await store.fetchConfig()
    const c = store.config
    configForm.interval_minutes = parseInt(c['inspection.interval_minutes'] || '5')
    configForm.timeout_seconds = parseInt(c['diagnosis.timeout_seconds'] || '30')
    configForm.retry_max = parseInt(c['diagnosis.retry_max'] || '3')
    configForm.polling_interval = parseInt(c['ui.polling_interval_seconds'] || '3')
  } finally {
    loading.value = false
  }
})

async function handleSave() {
  saving.value = true
  try {
    await store.updateConfig({
      inspection_interval_minutes: configForm.interval_minutes,
      diagnosis_timeout_seconds: configForm.timeout_seconds,
      diagnosis_retry_max: configForm.retry_max,
      polling_interval_seconds: configForm.polling_interval,
    })
    ElMessage.success('巡检配置已更新')
  } finally {
    saving.value = false
  }
}

async function handleTrigger() {
  try {
    await store.triggerInspection()
    ElMessage.success('巡检已触发')
  } catch {
    // Error handled by interceptor
  }
}
</script>
