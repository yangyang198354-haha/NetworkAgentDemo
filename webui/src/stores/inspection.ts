/**
 * MOD-WEB-F08: InspectionStore — Inspection config, trigger, history, and systemd control.
 * @module InspectionStore
 * @version 0.2.0
 *
 * v0.2.0 enhancements (REQ-INSP-005, REQ-INSP-008):
 *   - New state: timerStatus, serviceStatus, systemdAvailable
 *   - New actions: fetchStatus, startService, stopService, restartService,
 *                  enableTimer, disableTimer
 *   - Enhanced: triggerInspection (409/503 handling), fetchHistory (+status filter)
 *   - Enhanced: updateConfig (retry_backoff_seconds instead of polling_interval_seconds)
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

  // ── v0.2.0: systemd status state ────────────────────────

  const timerStatus = ref<{
    activeState: string
    unitFileState: string
    nextTrigger: string | null
    lastTrigger: string | null
  } | null>(null)

  const serviceStatus = ref<{
    activeState: string
    subState: string
    lastResult: string
    lastExecution: string | null
  } | null>(null)

  const lastInspection = ref<Record<string, any> | null>(null)
  const systemdAvailable = ref<boolean>(false)

  // ── fetchConfig (v0.2.0: returns retry_backoff) ────────

  async function fetchConfig() {
    const resp: any = await client.get('/api/inspection/config')
    config.value = resp.config || {}
    return resp
  }

  // ── updateConfig (v0.2.0: retry_backoff_seconds) ───────

  async function updateConfig(data: Record<string, any>) {
    const resp: any = await client.put('/api/inspection/config', data)
    await fetchConfig()
    return resp
  }

  // ── fetchStatus [NEW v0.2.0] ────────────────────────────

  const statusError = ref(false)

  /**
   * Map snake_case API response to camelCase for UI consumption.
   * Backend returns snake_case keys; frontend components use camelCase.
   */
  function mapTimer(raw: any) {
    if (!raw) return null
    return {
      activeState: raw.active_state ?? '',
      unitFileState: raw.unit_file_state ?? '',
      nextTrigger: raw.next_trigger ?? null,
      lastTrigger: raw.last_trigger ?? null,
    }
  }

  function mapService(raw: any) {
    if (!raw) return null
    return {
      activeState: raw.active_state ?? '',
      subState: raw.sub_state ?? '',
      lastResult: raw.last_result ?? '',
      lastExecution: raw.last_execution ?? null,
    }
  }

  async function fetchStatus() {
    try {
      const resp: any = await client.get('/api/inspection/status')
      systemdAvailable.value = resp.systemd_available || false
      timerStatus.value = mapTimer(resp.timer)
      serviceStatus.value = mapService(resp.service)
      lastInspection.value = resp.last_inspection || null
      statusError.value = false
      return resp
    } catch {
      // Keep previous values on error — don't clear to null
      statusError.value = true
      return null
    }
  }

  // ── startService [NEW v0.2.0] ───────────────────────────

  async function startService() {
    const resp: any = await client.post('/api/inspection/start')
    return resp
  }

  // ── stopService [NEW v0.2.0] ────────────────────────────

  async function stopService() {
    const resp: any = await client.post('/api/inspection/stop')
    return resp
  }

  // ── restartService [NEW v0.2.0] ─────────────────────────

  async function restartService() {
    const resp: any = await client.post('/api/inspection/restart')
    return resp
  }

  // ── enableTimer [NEW v0.2.0] ────────────────────────────

  async function enableTimer() {
    const resp: any = await client.post('/api/inspection/enable')
    return resp
  }

  // ── disableTimer [NEW v0.2.0] ───────────────────────────

  async function disableTimer() {
    const resp: any = await client.post('/api/inspection/disable')
    return resp
  }

  // ── triggerInspection (enhanced v0.2.0) ─────────────────

  async function triggerInspection() {
    inspectionRunning.value = true
    try {
      const resp: any = await client.post('/api/inspection/trigger')
      return resp
    } finally {
      inspectionRunning.value = false
    }
  }

  // ── fetchHistory (v0.2.0: +status filter) ──────────────

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

  return {
    config,
    historyList,
    inspectionRunning,
    pagination,
    loading,
    // v0.2.0 systemd state
    timerStatus,
    serviceStatus,
    lastInspection,
    systemdAvailable,
    statusError,
    // actions
    fetchConfig,
    updateConfig,
    fetchStatus,
    startService,
    stopService,
    restartService,
    enableTimer,
    disableTimer,
    triggerInspection,
    fetchHistory,
  }
})
