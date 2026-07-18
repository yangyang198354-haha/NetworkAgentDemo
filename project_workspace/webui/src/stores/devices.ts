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

  async function getDevicePorts(deviceId: number) {
    const resp: any = await client.get(`/api/devices/${deviceId}/ports`)
    return resp
  }

  async function configurePort(deviceId: number, portName: string, action: string, value?: string) {
    // encodeURIComponent: port names contain "/" (e.g., "Gi0/1"), which must be
    // escaped in the URL path so FastAPI correctly captures the full name.
    const resp: any = await client.post(`/api/devices/${deviceId}/ports/${encodeURIComponent(portName)}/config`, {
      action,
      value: value || null,
    })
    return resp
  }

  async function getDeviceSystem(deviceId: number) {
    const resp: any = await client.get(`/api/devices/${deviceId}/system`)
    return resp
  }

  return {
    deviceList, currentDevice, loading,
    fetchDevices, createDevice, updateDevice, deleteDevice,
    configureCredentials, fetchDiagnostics,
    startSimulator, stopSimulator, getSimulatorStatus,
    heartbeat, getDevicePorts, configurePort, getDeviceSystem,
  }
})
