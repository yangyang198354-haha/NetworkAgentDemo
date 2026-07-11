/**
 * MOD-WEB-F07: DevicesStore — Device CRUD and credential management.
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

  return { deviceList, currentDevice, loading, fetchDevices, createDevice, updateDevice, deleteDevice, configureCredentials, fetchDiagnostics }
})
