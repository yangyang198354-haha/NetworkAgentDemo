<!--
  MOD-WEB-F19: SystemConfigView — Global config + LLM API Key management.
  @covers REQ-WEBUI-FUNC-019, REQ-WEBUI-FUNC-020
-->
<template>
  <div class="config-page">
    <el-row :gutter="20">
      <el-col :span="12">
        <el-card>
          <template #header><span>全局配置</span></template>
          <el-form label-width="160px" v-loading="loading">
            <el-form-item label="巡检间隔(分钟)">
              <el-input-number v-model="configForm.interval_minutes" :min="1" :max="1440" />
            </el-form-item>
            <el-form-item label="诊断超时(秒)">
              <el-input-number v-model="configForm.timeout_seconds" :min="5" :max="300" />
            </el-form-item>
            <el-form-item label="重试次数">
              <el-input-number v-model="configForm.retry_max" :min="0" :max="10" />
            </el-form-item>
            <el-form-item label="RAG相似度阈值">
              <el-input-number v-model="configForm.rag_threshold" :min="0" :max="1" :step="0.1" :precision="1" />
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
          <template #header><span>LLM API Key 配置</span></template>
          <div class="api-key-section">
            <p style="color:#909399">DeepSeek API Key 将以加密形式存储，不会明文显示。</p>
            <el-input v-model="apiKey" type="password" show-password placeholder="输入 DeepSeek API Key (sk-...)" style="margin-bottom:16px" />
            <el-button type="primary" :loading="savingKey" @click="handleSaveKey">保存 API Key</el-button>
            <el-button :loading="testing" @click="handleTestLLM" style="margin-left:16px">测试连接</el-button>
          </div>

          <el-divider />
          <div class="test-result" v-if="testResult">
            <el-tag :type="testResult.status === 'healthy' ? 'success' : 'danger'">
              {{ testResult.detail || testResult.status }}
            </el-tag>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { useSystemStore } from '@/stores/system'
import { ElMessage } from 'element-plus'

const store = useSystemStore()
const loading = ref(false)
const saving = ref(false)
const savingKey = ref(false)
const testing = ref(false)
const testResult = ref<any>(null)
const apiKey = ref('')

const configForm = reactive({
  interval_minutes: 5, timeout_seconds: 30, retry_max: 3,
  rag_threshold: 0.6, polling_interval: 3,
})

onMounted(async () => {
  loading.value = true
  try {
    await store.fetchConfigs()
    for (const c of store.configs) {
      if (c.masked) continue
      const v = parseInt(c.config_value)
      switch (c.config_key) {
        case 'inspection.interval_minutes': configForm.interval_minutes = v; break
        case 'diagnosis.timeout_seconds': configForm.timeout_seconds = v; break
        case 'diagnosis.retry_max': configForm.retry_max = v; break
        case 'rag.similarity_threshold': configForm.rag_threshold = parseFloat(c.config_value); break
        case 'ui.polling_interval_seconds': configForm.polling_interval = v; break
      }
    }
  } finally { loading.value = false }
})

async function handleSave() {
  saving.value = true
  try {
    await store.updateConfigs({
      inspection_interval_minutes: configForm.interval_minutes,
      diagnosis_timeout_seconds: configForm.timeout_seconds,
      diagnosis_retry_max: configForm.retry_max,
      rag_similarity_threshold: configForm.rag_threshold,
      polling_interval_seconds: configForm.polling_interval,
    })
    ElMessage.success('系统配置已更新')
  } finally { saving.value = false }
}

async function handleSaveKey() {
  if (!apiKey.value.trim()) return
  savingKey.value = true
  try {
    await store.updateApiKey(apiKey.value)
    ElMessage.success('API Key 已安全存储')
    apiKey.value = ''
  } finally { savingKey.value = false }
}

async function handleTestLLM() {
  testing.value = true
  testResult.value = null
  try {
    const resp = await store.testLlmConnection()
    testResult.value = resp
  } finally { testing.value = false }
}
</script>

<style scoped>
.api-key-section { padding: 8px 0; }
.test-result { margin-top: 12px; }
</style>
