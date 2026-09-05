/**
 * MOD-WEB-F07: DevicesStore — Device CRUD, credential management, and simulator operations.
 * @extended REQ-FUNC-113, REQ-FUNC-114, REQ-FUNC-115, REQ-FUNC-121
 */

import { defineStore } from 'pinia'
import { ref } from 'vue'
import client from '@/api/client'

export const useDevicesStore = defineStore('devices', () => {
  const deviceList = ref<any[]>([])
  const currentDevice = ref<any | null>(null)
  const loading = ref(false)

  async function fetchDevices() {
    loading.value = true
    try {
      const resp: any = await client.get('/api/devices')
      deviceList.value = resp.devices || []
    } finally {
      loading.value = false
    }
  }

  async function createDevice(data: Record<string, any>) {
    const resp: any = await client.post('/api/devices', data)
    await fetchDevices()
    return resp
  }

  async function updateDevice(id: number, data: Record<string, any>) {
    const resp: any = await client.put(`/api/devices/${id}`, data)
    await fetchDevices()
    return resp
  }

  async function deleteDevice(id: number) {
    const resp: any = await client.delete(`/api/devices/${id}`)
    await fetchDevices()
    return resp
  }

  async function configureCredentials(deviceId: number, credData: Record<string, any>) {
    const resp: any = await client.put(`/api/devices/${deviceId}/credentials`, credData)
    return resp
  }

  async function fetchDiagnostics(deviceId: number) {
    const resp: any = await client.get(`/api/devices/${deviceId}/diagnostics`)
    return resp
  }

  // ── Simulator operations (REQ-FUNC-113, REQ-FUNC-114, REQ-FUNC-115, REQ-FUNC-121) ──

  async function startSimulator(deviceId: number, data?: Record<string, any>) {
    const resp: any = await client.post(`/api/devices/${deviceId}/simulator/start`, data || {})
    await fetchDevices()
    return resp
  }

  async function stopSimulator(deviceId: number) {
    const resp: any = await client.post(`/api/devices/${deviceId}/simulator/stop`)
    await fetchDevices()
    return resp
  }

  async function getSimulatorStatus(deviceId: number) {
    const resp: any = await client.get(`/api/devices/${deviceId}/simulator/status`)
    return resp
  }

  async function heartbeat(deviceId: number) {
    const resp: any = await client.post(`/api/devices/${deviceId}/heartbeat`)
    await fetchDevices()
    return resp
  }

  // ── REAL device: deep L7 connectivity probe (login + show system-info). ──
  // Uses a longer per-request timeout because a full TELNET/SSH session round-
  // trip (login → enable → show commands → parse) can take 20-40s, far beyond
  // the client's default 15s.
  async function checkConnectivity(deviceId: number) {
    const resp: any = await client.post(
      `/api/devices/${deviceId}/check_connectivity`, {}, { timeout: 120000 }
    )
    return resp
  }

  async function getDevicePorts(deviceId: number) {
    const resp: any = await client.get(`/api/devices/${deviceId}/ports`)
    return resp
  }

  async function configurePort(deviceId: number, portName: string, action: string, value?: string, timeoutMs?: number) {
    // encodeURIComponent: port names contain "/" (e.g., "Gi0/1"), which must be
    // escaped in the URL path so FastAPI correctly captures the full name.
    // timeoutMs 可选：SIMULATOR 不传（默认超时，向后兼容）；REAL 传 120000（长会话）。
    const resp: any = await client.post(`/api/devices/${deviceId}/ports/${encodeURIComponent(portName)}/config`, {
      action,
      value: value || null,
    }, timeoutMs ? { timeout: timeoutMs } : {})
    return resp
  }

  async function getDeviceSystem(deviceId: number) {
    const resp: any = await client.get(`/api/devices/${deviceId}/system`)
    return resp
  }

  // ── REAL device: panel aggregate read (single-session batch collection). ──
  // Same long per-request timeout as checkConnectivity: a full session round-trip
  // (login → enable → multiple show commands) can take 30-60s.
  async function getRealPanel(deviceId: number) {
    const resp: any = await client.get(`/api/devices/${deviceId}/real_panel`, { timeout: 120000 })
    return resp
  }

  return {
    deviceList, currentDevice, loading,
    fetchDevices, createDevice, updateDevice, deleteDevice,
    configureCredentials, fetchDiagnostics,
    startSimulator, stopSimulator, getSimulatorStatus,
    heartbeat, checkConnectivity, getDevicePorts, configurePort, getDeviceSystem,
    getRealPanel,
  }
})
