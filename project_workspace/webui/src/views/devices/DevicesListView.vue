<!--
  MOD-WEB-F16: DevicesListView — Device CRUD with credential configuration.
  @covers REQ-WEBUI-FUNC-010, REQ-WEBUI-FUNC-011
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
        <el-table-column prop="device_model" label="型号" width="180" />
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.status === 'ONLINE' ? 'success' : 'info'" size="small">{{ row.status || 'UNKNOWN' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="last_diag_at" label="最近诊断" width="170">
          <template #default="{ row }">{{ formatTime(row.last_diag_at) }}</template>
        </el-table-column>
        <el-table-column label="凭据" width="100">
          <template #default="{ row }">
            <el-tag :type="row.credential ? 'success' : 'warning'" size="small">
              {{ row.credential ? '已配置' : '未配置' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="280" fixed="right">
          <template #default="{ row }">
            <el-button text type="primary" @click="showEditDialog(row)">编辑</el-button>
            <el-button text type="warning" @click="showCredentialDialog(row)">凭据配置</el-button>
            <el-button text type="danger" @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- Add/Edit dialog -->
    <el-dialog v-model="dialogVisible" :title="isEdit ? '编辑设备' : '添加设备'" width="500px">
      <el-form :model="deviceForm" :rules="deviceRules" ref="deviceFormRef" label-width="100px">
        <el-form-item label="设备名称" prop="device_name">
          <el-input v-model="deviceForm.device_name" />
        </el-form-item>
        <el-form-item label="IP地址" prop="device_ip">
          <el-input v-model="deviceForm.device_ip" />
        </el-form-item>
        <el-form-item label="设备型号">
          <el-input v-model="deviceForm.device_model" />
        </el-form-item>
        <el-form-item label="所属分组">
          <el-input v-model="deviceForm.group_name" />
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
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { useDevicesStore } from '@/stores/devices'
import { ElMessageBox, ElMessage } from 'element-plus'

const store = useDevicesStore()
const dialogVisible = ref(false)
const credDialogVisible = ref(false)
const isEdit = ref(false)
const editingId = ref<number | null>(null)
const credDeviceId = ref<number | null>(null)
const deviceFormRef = ref()
const credFormRef = ref()

const deviceForm = reactive({ device_name: '', device_ip: '', device_model: '', group_name: '' })
const credForm = reactive({ ssh_username: 'admin', ssh_password: '', ssh_port: 22 })

const deviceRules = {
  device_name: [{ required: true, message: '请输入设备名称', trigger: 'blur' }],
  device_ip: [{ required: true, message: '请输入IP地址', trigger: 'blur' }],
}

onMounted(() => store.fetchDevices())

function showAddDialog() {
  isEdit.value = false; editingId.value = null
  Object.assign(deviceForm, { device_name: '', device_ip: '', device_model: '', group_name: '' })
  dialogVisible.value = true
}

function showEditDialog(row: any) {
  isEdit.value = true; editingId.value = row.id
  Object.assign(deviceForm, {
    device_name: row.device_name, device_ip: row.device_ip,
    device_model: row.device_model, group_name: row.group_name,
  })
  dialogVisible.value = true
}

async function handleSave() {
  const valid = await deviceFormRef.value?.validate().catch(() => false)
  if (!valid) return
  if (isEdit.value && editingId.value) {
    await store.updateDevice(editingId.value, { ...deviceForm })
  } else {
    await store.createDevice({ ...deviceForm })
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
  Object.assign(credForm, { ssh_username: 'admin', ssh_password: '', ssh_port: 22 })
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

function formatTime(t: string) {
  if (!t) return '-'
  const fixed = /[Zz]$|[+-]\d{2}:\d{2}$/.test(t) ? t : t + 'Z'
  return new Date(fixed).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' })
}
</script>

<style scoped>
.card-header { display: flex; justify-content: space-between; align-items: center; }
</style>
