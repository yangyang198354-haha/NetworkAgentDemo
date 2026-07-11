/**
 * MOD-WEB-F10: SystemStore — System config, API key, and log queries.
 */

import { defineStore } from 'pinia'
import { ref, reactive } from 'vue'
import client from '@/api/client'

export const useSystemStore = defineStore('system', () => {
  const configs = ref<any[]>([])
  const logEntries = ref<any[]>([])
  const apiKeyConfigured = ref(false)
  const logPagination = reactive({ page: 1, pageSize: 100, total: 0 })
  const loading = ref(false)

  async function fetchConfigs() {
    const resp: any = await client.get('/api/system/config')
    configs.value = resp.configs || []
    apiKeyConfigured.value = configs.value.some((c: any) => c.config_key === 'llm.api_key_encrypted' && c.config_value !== '****' && c.config_value !== '')
  }

  async function updateConfigs(data: Record<string, any>) {
    const resp = await client.put('/api/system/config', data)
    await fetchConfigs()
    return resp
  }

  async function updateApiKey(key: string) {
    const resp = await client.put('/api/system/config/llm-api-key', { api_key: key })
    apiKeyConfigured.value = true
    return resp
  }

  async function testLlmConnection() {
    const resp: any = await client.post('/api/system/config/llm-test')
    return resp
  }

  async function fetchLogs(filters: any = {}) {
    loading.value = true
    try {
      const params: any = { page: logPagination.page, page_size: logPagination.pageSize, ...filters }
      const resp: any = await client.get('/api/system/logs', { params })
      logEntries.value = resp.entries || []
      logPagination.total = resp.total || 0
    } finally {
      loading.value = false
    }
  }

  return { configs, logEntries, apiKeyConfigured, logPagination, loading,
    fetchConfigs, updateConfigs, updateApiKey, testLlmConnection, fetchLogs }
})
