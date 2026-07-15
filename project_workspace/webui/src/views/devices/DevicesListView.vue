<!--
  MOD-WEB-F16: DevicesListView — Device CRUD with simulator operations.
  @covers REQ-WEBUI-FUNC-010, REQ-WEBUI-FUNC-011
  @extended REQ-FUNC-116, REQ-FUNC-117, REQ-FUNC-118 (device_simulator)
-->
<template>
  <div class="devices-page">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>设备管理</span>
          <el-button type="primary" @click="showAddDialog">添加设备</el-button>
        </div>
      </template>

      <el-table :data="store.deviceList" v-loading="store.loading" stripe>
        <el-table-column prop="device_name" label="设备名称" width="140" />
        <el-table-column prop="device_ip" label="IP地址" width="140" />
        <el-table-column label="设备类型" width="100">
          <template #default="{ row }">
            <el-tag :type="row.device_type === 'SIMULATOR' ? '' : 'info'" size="small"
              :color="row.device_type === 'SIMULATOR' ? '#409EFF' : undefined"
              :style="row.device_type === 'SIMULATOR' ? { color: '#fff' } : {}">
              {{ row.device_type === 'SIMULATOR' ? '模拟器' : 'Mock' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="device_model" label="型号" width="140" />
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.status)" size="small">{{ row.status || 'UNKNOWN' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="模拟器" width="90" v-if="hasSimulators">
          <template #default="{ row }">
            <el-tag v-if="row.device_type === 'SIMULATOR'"
              :type="row.simulator_status === 'RUNNING' ? 'success' : 'warning'" size="small">
              {{ row.simulator_status === 'RUNNING' ? '运行中' : '已停止' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="心跳延时" width="100">
          <template #default="{ row }">
            <span v-if="heartbeatLatency[row.id] !== undefined" :style="{ color: heartbeatLatency[row.id] < 10 ? '#67C23A' : heartbeatLatency[row.id] < 50 ? '#E6A23C' : '#F56C6C' }">
              {{ heartbeatLatency[row.id] }}ms
            </span>
            <span v-else style="color: #909399;">-</span>
          </template>
        </el-table-column>
        <el-table-column label="凭据" width="80">
          <template #default="{ row }">
            <el-tag :type="row.credential ? 'success' : 'warning'" size="small">
              {{ row.credential ? '已配置' : '未配置' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="400" fixed="right">
          <template #default="{ row }">
            <el-button text type="primary" @click="showEditDialog(row)">编辑</el-button>
            <el-button text type="warning" @click="showCredentialDialog(row)">凭据</el-button>
            <template v-if="row.device_type === 'SIMULATOR'">
              <el-button v-if="row.simulator_status !== 'RUNNING'"
                text type="success" @click="handleStartSimulator(row)">启动</el-button>
              <el-button v-else
                text type="danger" @click="handleStopSimulator(row)">停止</el-button>
              <el-button text type="primary" @click="showSimulatorPanel(row)">面板</el-button>
            </template>
            <el-button text type="danger" @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- Add/Edit dialog -->
    <el-dialog v-model="dialogVisible" :title="isEdit ? '编辑设备' : '添加设备'" width="520px">
      <el-form :model="deviceForm" :rules="deviceRules" ref="deviceFormRef" label-width="100px">
        <el-form-item label="设备名称" prop="device_name">
          <el-input v-model="deviceForm.device_name" />
        </el-form-item>
        <el-form-item label="IP地址" prop="device_ip">
          <el-input v-model="deviceForm.device_ip" />
        </el-form-item>
        <el-form-item label="设备类型" prop="device_type">
          <el-select v-model="deviceForm.device_type" style="width: 100%">
            <el-option label="Mock 设备 (MOCK)" value="MOCK" />
            <el-option label="模拟器设备 (SIMULATOR)" value="SIMULATOR" />
          </el-select>
        </el-form-item>
        <el-form-item label="设备型号">
          <el-input v-model="deviceForm.device_model" />
        </el-form-item>
        <el-form-item label="所属分组">
          <el-input v-model="deviceForm.group_name" />
        </el-form-item>
        <el-form-item v-if="deviceForm.device_type === 'SIMULATOR'" label="SSH端口">
          <el-input-number v-model="deviceForm.simulator_port" :min="1" :max="65535" placeholder="自动分配" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSave">保存</el-button>
      </template>
    </el-dialog>

    <!-- Credential dialog -->
    <el-dialog v-model="credDialogVisible" title="凭据配置" width="500px">
      <el-form :model="credForm" ref="credFormRef" label-width="120px">
        <el-form-item label="SSH用户名" prop="ssh_username">
          <el-input v-model="credForm.ssh_username" />
        </el-form-item>
        <el-form-item label="SSH密码" prop="ssh_password">
          <el-input v-model="credForm.ssh_password" type="password" show-password />
        </el-form-item>
        <el-form-item label="SSH端口">
          <el-input-number v-model="credForm.ssh_port" :min="1" :max="65535" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="credDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleCredentialSave">保存凭据</el-button>
      </template>
    </el-dialog>

    <!-- Simulator Panel Drawer (REQ-FUNC-118) -->
    <el-drawer v-model="simPanelVisible" :title="`模拟器面板 — ${simPanelDevice?.device_name || ''}`"
      size="480px" direction="rtl">
      <template v-if="simPanelDevice">
        <!-- Port Status -->
        <el-card shadow="never" class="sim-section">
          <template #header>
            <div class="section-header">
              <span>端口状态</span>
              <el-button size="small" type="primary" @click="loadPorts" :loading="portsLoading">刷新</el-button>
            </div>
          </template>
          <el-table :data="portsData" size="small" max-height="300" v-if="portsData.length">
            <el-table-column prop="name" label="端口" width="72" />
            <el-table-column prop="status" label="状态" width="90">
              <template #default="{ row }">
                <el-tag :type="row.status === 'up' ? 'success' : row.status.includes('admin') ? 'warning' : 'info'"
                  size="small">{{ row.status }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="vlan" label="VLAN" width="55" />
            <el-table-column prop="speed" label="速率" width="55" />
            <el-table-column label="操作" width="110">
              <template #default="{ row }">
                <el-button text size="small" type="primary" @click="portAction(row.name, 'no-shutdown')">启用</el-button>
                <el-button text size="small" type="danger" @click="portAction(row.name, 'shutdown')">禁用</el-button>
              </template>
            </el-table-column>
          </el-table>
          <el-empty v-else description="请先启动模拟器" :image-size="60" />
        </el-card>

        <!-- System Resources -->
        <el-card shadow="never" class="sim-section">
          <template #header>
            <div class="section-header">
              <span>系统资源</span>
              <el-button size="small" type="primary" @click="loadSystem" :loading="sysLoading">刷新</el-button>
            </div>
          </template>
          <div v-if="sysData" class="sys-grid">
            <div class="sys-item">
              <span class="sys-label">CPU (5s)</span>
              <el-progress :percentage="sysData.cpu?.cpu_5s || 0" :color="cpuColor(sysData.cpu?.cpu_5s)"
                :stroke-width="14" />
              <span class="sys-value">{{ sysData.cpu?.cpu_5s }}%</span>
            </div>
            <div class="sys-item">
              <span class="sys-label">内存</span>
              <el-progress :percentage="sysData.memory?.usage_pct || 0" :color="cpuColor(sysData.memory?.usage_pct)"
                :stroke-width="14" />
              <span class="sys-value">{{ sysData.memory?.used_mb }} / {{ sysData.memory?.total_mb }} MB</span>
            </div>
            <div class="sys-item">
              <span class="sys-label">IO 读</span>
              <span class="sys-value">{{ sysData.io?.read_kbps }} KB/s</span>
            </div>
            <div class="sys-item">
              <span class="sys-label">IO 写</span>
              <span class="sys-value">{{ sysData.io?.write_kbps }} KB/s</span>
            </div>
          </div>
          <el-empty v-else description="请先启动模拟器" :image-size="60" />
        </el-card>
      </template>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { useDevicesStore } from '@/stores/devices'
import { ElMessageBox, ElMessage } from 'element-plus'

const store = useDevicesStore()

// ── Dialogs ────────────────────────────────────────────
const dialogVisible = ref(false)
const credDialogVisible = ref(false)
const isEdit = ref(false)
const editingId = ref<number | null>(null)
const credDeviceId = ref<number | null>(null)
const deviceFormRef = ref()
const credFormRef = ref()

const deviceForm = reactive({
  device_name: '', device_ip: '', device_model: '', group_name: '',
  device_type: 'MOCK', simulator_port: null as number | null,
})
const credForm = reactive({ ssh_username: 'admin', ssh_password: '', ssh_port: 22 })

const deviceRules = {
  device_name: [{ required: true, message: '请输入设备名称', trigger: 'blur' }],
  device_ip: [{ required: true, message: '请输入IP地址', trigger: 'blur' }],
}

// ── Simulator Panel ────────────────────────────────────
const simPanelVisible = ref(false)
const simPanelDevice = ref<any>(null)
const portsData = ref<any[]>([])
const sysData = ref<any>(null)
const portsLoading = ref(false)
const sysLoading = ref(false)

const hasSimulators = computed(() =>
  store.deviceList.some((d: any) => d.device_type === 'SIMULATOR')
)

  // ── Heartbeat Latency ──────────────────────────────────
  const heartbeatLatency = reactive<Record<number, number>>({})

  async function refreshHeartbeats() {
    for (const d of store.deviceList) {
      if (d.device_type === 'SIMULATOR' && d.simulator_status === 'RUNNING') {
        try {
          const resp = await store.heartbeat(d.id)
          if (resp.response_time_ms !== null && resp.response_time_ms !== undefined) {
            heartbeatLatency[d.id] = resp.response_time_ms
          }
        } catch { /* ignore */ }
      }
    }
  }

  onMounted(async () => {
    await store.fetchDevices()
    await refreshHeartbeats()
  })

// ── Device CRUD ────────────────────────────────────────
function showAddDialog() {
  isEdit.value = false; editingId.value = null
  Object.assign(deviceForm, {
    device_name: '', device_ip: '', device_model: '', group_name: '',
    device_type: 'MOCK', simulator_port: null,
  })
  dialogVisible.value = true
}

function showEditDialog(row: any) {
  isEdit.value = true; editingId.value = row.id
  Object.assign(deviceForm, {
    device_name: row.device_name, device_ip: row.device_ip,
    device_model: row.device_model, group_name: row.group_name,
    device_type: row.device_type || 'MOCK',
    simulator_port: row.simulator_port || null,
  })
  dialogVisible.value = true
}

async function handleSave() {
  const valid = await deviceFormRef.value?.validate().catch(() => false)
  if (!valid) return
  const payload: any = { ...deviceForm }
  if (payload.device_type !== 'SIMULATOR') payload.simulator_port = null
  if (isEdit.value && editingId.value) {
    await store.updateDevice(editingId.value, payload)
  } else {
    await store.createDevice(payload)
  }
  dialogVisible.value = false
  ElMessage.success(isEdit.value ? '设备已更新' : '设备已添加')
}

async function handleDelete(row: any) {
  try {
    await ElMessageBox.confirm(`确认删除设备 ${row.device_name}？`, '确认删除', { type: 'warning' })
    await store.deleteDevice(row.id)
    ElMessage.success('设备已删除')
  } catch { /* cancelled */ }
}

function showCredentialDialog(row: any) {
  credDeviceId.value = row.id
  Object.assign(credForm, { ssh_username: 'admin', ssh_password: '', ssh_port: row.simulator_port || 22 })
  credDialogVisible.value = true
}

async function handleCredentialSave() {
  if (!credDeviceId.value) return
  await store.configureCredentials(credDeviceId.value, {
    ssh_username: credForm.ssh_username,
    ssh_password: credForm.ssh_password,
    ssh_port: credForm.ssh_port,
  })
  credDialogVisible.value = false
  ElMessage.success('凭据已配置')
}

// ── Simulator Operations ───────────────────────────────

async function handleStartSimulator(row: any) {
  try {
    const resp = await store.startSimulator(row.id, { port: row.simulator_port || 0 })
    ElMessage.success(resp.message || '模拟器已启动')
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '启动失败')
  }
}

async function handleStopSimulator(row: any) {
  try {
    const resp = await store.stopSimulator(row.id)
    ElMessage.success(resp.message || '模拟器已停止')
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '停止失败')
  }
}

async function handleHeartbeat(row: any) {
  try {
    const resp = await store.heartbeat(row.id)
    const statusText = resp.status === 'ONLINE' ? '在线' : '离线'
    const ms = resp.response_time_ms ? ` (${resp.response_time_ms}ms)` : ''
    ElMessage.info(`心跳检测: ${statusText}${ms}`)
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '心跳检测失败')
  }
}

function showSimulatorPanel(row: any) {
  simPanelDevice.value = row
  simPanelVisible.value = true
  loadPorts()
  loadSystem()
}

async function loadPorts() {
  if (!simPanelDevice.value) return
  portsLoading.value = true
  try {
    const resp = await store.getDevicePorts(simPanelDevice.value.id)
    portsData.value = resp.ports || []
  } catch (e: any) {
    portsData.value = []
    ElMessage.error(e?.response?.data?.detail || '无法加载端口数据')
  } finally {
    portsLoading.value = false
  }
}

async function loadSystem() {
  if (!simPanelDevice.value) return
  sysLoading.value = true
  try {
    const resp = await store.getDeviceSystem(simPanelDevice.value.id)
    sysData.value = resp
  } catch (e: any) {
    sysData.value = null
    ElMessage.error(e?.response?.data?.detail || '无法加载系统资源')
  } finally {
    sysLoading.value = false
  }
}

async function portAction(portName: string, action: string) {
  if (!simPanelDevice.value) return
  try {
    const resp = await store.configurePort(simPanelDevice.value.id, portName, action)
    ElMessage.success(resp.message || `${action} ${portName} 成功`)
    loadPorts()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || `${action} 失败`)
  }
}

// ── Helpers ────────────────────────────────────────────

function statusTagType(status: string): string {
  if (status === 'ONLINE') return 'success'
  if (status === 'OFFLINE') return 'danger'
  return 'info'
}

function cpuColor(value: number | undefined): string {
  if (!value) return '#67C23A'
  if (value > 90) return '#F56C6C'
  if (value > 70) return '#E6A23C'
  return '#67C23A'
}

function formatTime(t: string) {
  if (!t) return '-'
  const fixed = /[Zz]$|[+-]\d{2}:\d{2}$/.test(t) ? t : t + 'Z'
  return new Date(fixed).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' })
}
</script>

<style scoped>
.card-header { display: flex; justify-content: space-between; align-items: center; }
.sim-section { margin-bottom: 16px; }
.section-header { display: flex; justify-content: space-between; align-items: center; }
.sys-grid { display: flex; flex-direction: column; gap: 12px; }
.sys-item { display: flex; flex-direction: column; gap: 4px; }
.sys-label { font-size: 13px; color: #606266; }
.sys-value { font-size: 13px; color: #303133; margin-top: 2px; }
</style>
