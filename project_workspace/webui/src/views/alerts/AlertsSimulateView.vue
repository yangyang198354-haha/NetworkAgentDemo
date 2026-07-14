<!--
  MOD-WEB-F13: AlertsSimulateView — Alert simulation form.
  @covers REQ-WEBUI-FUNC-003
-->
<template>
  <div class="simulate-page">
    <el-card>
      <template #header><span>模拟告警发送</span></template>
      <el-form :model="form" :rules="rules" ref="formRef" label-width="120px" style="max-width:600px">
        <el-form-item label="来源" prop="source">
          <el-radio-group v-model="form.source">
            <el-radio value="MOCK">MOCK（模拟器触发）</el-radio>
            <el-radio value="WEBHOOK">WEBHOOK（模拟 Zabbix 推送）</el-radio>
          </el-radio-group>
        </el-form-item>

        <el-form-item label="告警类型" prop="alert_type">
          <el-select v-model="form.alert_type" style="width:100%">
            <el-option label="端口Down (PORT_DOWN)" value="PORT_DOWN" />
            <el-option label="MAC地址漂移 (MAC_FLAPPING)" value="MAC_FLAPPING" />
            <el-option label="CPU利用率过高 (CPU_HIGH)" value="CPU_HIGH" />
            <el-option label="端口安全隔离 ⚠️ (PORT_SHUTDOWN)" value="PORT_SHUTDOWN" />
          </el-select>
        </el-form-item>

        <el-form-item label="设备名称" prop="device_name">
          <el-select v-model="form.device_name" style="width:100%" filterable allow-create>
            <el-option v-for="d in devices" :key="d.device_name" :label="d.device_name" :value="d.device_name" />
          </el-select>
        </el-form-item>

        <el-form-item label="设备IP" prop="device_ip">
          <el-input v-model="form.device_ip" placeholder="192.168.1.1" />
        </el-form-item>

        <el-form-item label="接口名称" v-if="form.alert_type === 'PORT_DOWN' || form.alert_type === 'PORT_SHUTDOWN'">
          <el-input v-model="form.interface" placeholder="Gi0/1" />
        </el-form-item>

        <el-form-item label="MAC地址" v-if="form.alert_type === 'MAC_FLAPPING'">
          <el-input v-model="form.mac_address" placeholder="00:1A:2B:3C:4D:5E" />
        </el-form-item>

        <el-form-item label="CPU利用率" v-if="form.alert_type === 'CPU_HIGH'">
          <el-input-number v-model="form.cpu_percent" :min="0" :max="100" />
        </el-form-item>

        <el-form-item>
          <el-button type="primary" :loading="sending" @click="handleSend">发送模拟告警</el-button>
        </el-form-item>
      </el-form>

      <el-alert v-if="result" :title="result" type="success" show-icon :closable="false" style="margin-top:16px" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { useAlertsStore } from '@/stores/alerts'
import { useDevicesStore } from '@/stores/devices'

const alertsStore = useAlertsStore()
const devicesStore = useDevicesStore()
const devices = ref<any[]>([])
const sending = ref(false)
const result = ref('')
const formRef = ref()

const form = reactive({
  source: 'MOCK',
  alert_type: 'PORT_DOWN',
  device_name: 'Core-SW-01',
  device_ip: '192.168.1.1',
  interface: 'Gi0/1',
  mac_address: '',
  cpu_percent: 92 as number | null,
})

const rules = {
  alert_type: [{ required: true, message: '请选择告警类型', trigger: 'change' }],
  device_name: [{ required: true, message: '请输入设备名称', trigger: 'blur' }],
  device_ip: [{ required: true, message: '请输入设备IP', trigger: 'blur' }],
}

onMounted(async () => {
  try { await devicesStore.fetchDevices(); devices.value = devicesStore.deviceList } catch { /* use defaults */ }
})

async function handleSend() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return

  sending.value = true
  result.value = ''
  try {
    if (form.source === 'WEBHOOK') {
      // POST /webhook/alert — Zabbix-format payload
      const resp: any = await alertsStore.sendWebhook({
        alert_name: `[Webhook] ${form.alert_type} on ${form.device_name}`,
        alert_type: form.alert_type,
        alert_severity: 'MAJOR',
        alert_host: form.device_name,
        alert_ip: form.device_ip,
        alert_time: new Date().toISOString(),
        alert_description: getWebhookDescription(),
        alert_interface: form.interface || undefined,
        alert_mac: form.mac_address || undefined,
        alert_cpu: form.cpu_percent || undefined,
        event_id: `WEB-${Date.now()}`,
      })
      result.value = `Webhook 已发送！alert_id: ${resp.alert_id}, source: WEBHOOK`
    } else {
      // POST /api/alerts/simulate
      const resp: any = await alertsStore.simulateAlert({
        alert_type: form.alert_type,
        device_name: form.device_name,
        device_ip: form.device_ip,
        interface: form.interface || undefined,
        mac_address: form.mac_address || undefined,
        cpu_percent: form.cpu_percent || undefined,
      })
      result.value = `模拟告警已发送！alert_id: ${resp.alert_id}, source: MOCK`
    }
  } catch {
    // Error handled by interceptor
  } finally {
    sending.value = false
  }
}

function getWebhookDescription(): string {
  const map: Record<string, string> = {
    PORT_DOWN: `接口 ${form.interface || 'Gi0/1'} 在设备 ${form.device_name} 上状态变更为 down`,
    MAC_FLAPPING: `MAC地址 00:1A:2B:3C:4D:5E 在设备 ${form.device_name} 的VLAN 1内发生漂移`,
    CPU_HIGH: `设备 ${form.device_name} 的CPU利用率在5秒内达到92%，超过告警阈值80%`,
    PORT_SHUTDOWN: `接口 ${form.interface || 'Gi0/1'} 在设备 ${form.device_name} 上检测到安全威胁，需要紧急隔离`,
  }
  return map[form.alert_type] || `Webhook alert: ${form.alert_type} on ${form.device_name}`
}
</script>
