<!--
  MOD-WEB-F18: KnowledgeTemplatesView — Command template CRUD.
  @covers REQ-WEBUI-FUNC-017
-->
<template>
  <div class="templates-page">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>命令模板</span>
          <el-button type="primary" @click="showAddDialog">新建模板</el-button>
        </div>
      </template>

      <el-select v-model="filterAlertType" placeholder="告警类型筛选" clearable @change="onFilter"
        style="width:180px;margin-bottom:16px">
        <el-option label="MAC_FLAPPING" value="MAC_FLAPPING" />
        <el-option label="PORT_DOWN" value="PORT_DOWN" />
        <el-option label="CPU_HIGH" value="CPU_HIGH" />
      </el-select>

      <el-table :data="store.templateList" stripe>
        <el-table-column prop="name" label="模板名称" show-overflow-tooltip />
        <el-table-column prop="alert_type" label="告警类型" width="120">
          <template #default="{ row }"><el-tag size="small">{{ row.alert_type }}</el-tag></template>
        </el-table-column>
        <el-table-column prop="updated_at" label="更新时间" width="180">
          <template #default="{ row }">{{ formatTime(row.updated_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <el-button text type="primary" @click="showEditDialog(row)">编辑</el-button>
            <el-button text type="danger" @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- Template dialog -->
    <el-dialog v-model="dialogVisible" :title="isEdit ? '编辑模板' : '新建模板'" width="700px">
      <el-form :model="tmplForm" ref="tmplFormRef" label-width="100px">
        <el-form-item label="模板名称" prop="name">
          <el-input v-model="tmplForm.name" />
        </el-form-item>
        <el-form-item label="告警类型" prop="alert_type">
          <el-select v-model="tmplForm.alert_type" style="width:100%">
            <el-option label="MAC_FLAPPING" value="MAC_FLAPPING" />
            <el-option label="PORT_DOWN" value="PORT_DOWN" />
            <el-option label="CPU_HIGH" value="CPU_HIGH" />
          </el-select>
        </el-form-item>
        <el-form-item label="YAML内容" prop="yaml_content">
          <el-input v-model="tmplForm.yaml_content" type="textarea" :rows="12" placeholder="请输入YAML格式模板内容" />
        </el-form-item>
        <el-form-item label="参数(JSON)">
          <el-input v-model="tmplForm.parameters_json" type="textarea" :rows="4"
            placeholder='[{"name":"param1","type":"string","required":true}]' />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSave">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { useKnowledgeStore } from '@/stores/knowledge'
import { ElMessageBox, ElMessage } from 'element-plus'

const store = useKnowledgeStore()
const dialogVisible = ref(false)
const isEdit = ref(false)
const editingId = ref<number | null>(null)
const filterAlertType = ref('')
const tmplFormRef = ref()

const tmplForm = reactive({
  name: '', alert_type: 'PORT_DOWN', yaml_content: '', parameters_json: '[]',
})

onMounted(() => store.fetchTemplates())

function showAddDialog() {
  isEdit.value = false; editingId.value = null
  Object.assign(tmplForm, { name: '', alert_type: 'PORT_DOWN', yaml_content: '', parameters_json: '[]' })
  dialogVisible.value = true
}

function showEditDialog(row: any) {
  isEdit.value = true; editingId.value = row.id
  Object.assign(tmplForm, {
    name: row.name, alert_type: row.alert_type,
    yaml_content: row.yaml_content,
    parameters_json: JSON.stringify(row.parameters || [], null, 2),
  })
  dialogVisible.value = true
}

async function handleSave() {
  let params = []
  try { params = JSON.parse(tmplForm.parameters_json) } catch { params = [] }
  const data = {
    name: tmplForm.name, alert_type: tmplForm.alert_type,
    yaml_content: tmplForm.yaml_content, parameters: params,
  }
  if (isEdit.value && editingId.value) {
    await store.updateTemplate(editingId.value, data)
  } else {
    await store.createTemplate(data)
  }
  dialogVisible.value = false
  ElMessage.success(isEdit.value ? '模板已更新' : '模板已创建')
}

async function handleDelete(row: any) {
  try {
    await ElMessageBox.confirm(`确认删除模板 "${row.name}"？`, '确认删除', { type: 'warning' })
    await store.deleteTemplate(row.id)
    ElMessage.success('模板已删除')
  } catch { /* cancelled */ }
}

function onFilter() { store.fetchTemplates(filterAlertType.value || undefined) }
function formatTime(t: string) { return t ? new Date(t).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' }) : '-' }
</script>

<style scoped>
.card-header { display: flex; justify-content: space-between; align-items: center; }
</style>
