/**
 * MOD-WEB-F05: AlertsStore — Alert list, detail, and simulation state.
 */

import { defineStore } from 'pinia'
import { ref, reactive } from 'vue'
import client from '@/api/client'

export interface Alert {
  alert_id: string
  alert_type: string
  severity: string
  content: string
  device_info: Record<string, any>
  source: string
  status: string
  created_at: string
  updated_at: string
}

export interface AlertFilter {
  alert_type: string | null
  severity: string | null
  status: string | null
  source: string | null
}

export const useAlertsStore = defineStore('alerts', () => {
  const alertList = ref<Alert[]>([])
  const currentAlert = ref<Alert | null>(null)
  const filters = reactive<AlertFilter>({
    alert_type: null,
    severity: null,
    status: null,
    source: null,
  })
  const pagination = reactive({ page: 1, pageSize: 20, total: 0 })
  const loading = ref(false)

  async function fetchAlerts() {
    loading.value = true
    try {
      const params: any = { page: pagination.page, page_size: pagination.pageSize }
      if (filters.alert_type) params.alert_type = filters.alert_type
      if (filters.severity) params.severity = filters.severity
      if (filters.status) params.status = filters.status
      if (filters.source) params.source = filters.source
      const resp: any = await client.get('/api/alerts', { params })
      alertList.value = resp.items || []
      pagination.total = resp.total || 0
    } finally {
      loading.value = false
    }
  }

  async function fetchAlertDetail(alertId: string) {
    const resp: any = await client.get(`/api/alerts/${alertId}`)
    currentAlert.value = resp.alert
    return resp
  }

  async function simulateAlert(data: Record<string, any>) {
    const resp: any = await client.post('/api/alerts/simulate', data)
    return resp
  }

  function updateFilters(newFilters: Partial<AlertFilter>) {
    Object.assign(filters, newFilters)
    pagination.page = 1
  }

  return { alertList, currentAlert, filters, pagination, loading, fetchAlerts, fetchAlertDetail, simulateAlert, updateFilters }
})
