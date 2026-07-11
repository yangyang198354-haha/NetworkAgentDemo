/**
 * MOD-WEB-F08: InspectionStore — Inspection config, trigger, and history.
 */

import { defineStore } from 'pinia'
import { ref, reactive } from 'vue'
import client from '@/api/client'

export const useInspectionStore = defineStore('inspection', () => {
  const config = ref<Record<string, any>>({})
  const historyList = ref<any[]>([])
  const inspectionRunning = ref(false)
  const pagination = reactive({ page: 1, pageSize: 20, total: 0 })
  const loading = ref(false)

  async function fetchConfig() {
    const resp: any = await client.get('/api/inspection/config')
    config.value = resp.config || {}
    return resp
  }

  async function updateConfig(data: Record<string, any>) {
    const resp: any = await client.put('/api/inspection/config', data)
    await fetchConfig()
    return resp
  }

  async function triggerInspection() {
    inspectionRunning.value = true
    try {
      const resp: any = await client.post('/api/inspection/trigger')
      return resp
    } finally {
      inspectionRunning.value = false
    }
  }

  async function fetchHistory(filters: any = {}) {
    loading.value = true
    try {
      const params: any = { page: pagination.page, page_size: pagination.pageSize, ...filters }
      const resp: any = await client.get('/api/inspection/history', { params })
      historyList.value = resp.items || []
      pagination.total = resp.total || 0
    } finally {
      loading.value = false
    }
  }

  return { config, historyList, inspectionRunning, pagination, loading, fetchConfig, updateConfig, triggerInspection, fetchHistory }
})
