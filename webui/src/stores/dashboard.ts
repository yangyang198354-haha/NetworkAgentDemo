/**
 * MOD-WEB-F11: DashboardStore — Dashboard aggregated stats and health.
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import client from '@/api/client'

export const useDashboardStore = defineStore('dashboard', () => {
  const alertStats = ref<Record<string, any> | null>(null)
  const fixRate = ref<Record<string, any> | null>(null)
  const healthStatus = ref<Record<string, any> | null>(null)
  const loading = ref(false)

  async function fetchStats(timeFrom?: string, timeTo?: string) {
    loading.value = true
    try {
      const params: any = {}
      if (timeFrom) params.time_from = timeFrom
      if (timeTo) params.time_to = timeTo
      const resp: any = await client.get('/api/dashboard/stats', { params })
      alertStats.value = resp
      fixRate.value = {
        closed_count: resp.closed_count || 0,
        failed_count: resp.failed_count || 0,
        rejected_count: resp.rejected_count || 0,
        total_count: resp.total_count || 0,
        success_rate: resp.fix_success_rate || 0,
      }
    } finally {
      loading.value = false
    }
  }

  async function fetchFixRate(timeFrom?: string, timeTo?: string) {
    const resp: any = await client.get('/api/dashboard/stats', {
      params: { time_from: timeFrom, time_to: timeTo }
    })
    fixRate.value = {
      closed_count: resp.closed_count || 0,
      failed_count: resp.failed_count || 0,
      rejected_count: resp.rejected_count || 0,
      total_count: resp.total_count || 0,
      success_rate: resp.fix_success_rate || 0,
    }
    return resp
  }

  async function fetchHealthStatus() {
    const resp: any = await client.get('/api/dashboard/health')
    healthStatus.value = resp
    return resp
  }

  return { alertStats, fixRate, healthStatus, loading, fetchStats, fetchFixRate, fetchHealthStatus }
})
