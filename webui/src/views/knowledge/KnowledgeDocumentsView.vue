<!--
  MOD-WEB-F18: KnowledgeDocumentsView — Knowledge document CRUD.
  @covers REQ-WEBUI-FUNC-016
-->
<template>
  <div class="kb-docs-page">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>知识文档</span>
          <el-button type="primary" @click="showAddDialog">新建文档</el-button>
        </div>
      </template>

      <el-select v-model="filterAlertType" placeholder="告警类型筛选" clearable @change="onFilter"
        style="width:180px;margin-bottom:16px">
        <el-option label="MAC_FLAPPING" value="MAC_FLAPPING" />
        <el-option label="PORT_DOWN" value="PORT_DOWN" />
        <el-option label="CPU_HIGH" value="CPU_HIGH" />
      </el-select>

      <el-table :data="store.documentList" v-loading="store.loading" stripe>
        <el-table-column prop="title" label="标题" show-overflow-tooltip />
        <el-table-column prop="alert_type" label="告警类型" width="120">
          <template #default="{ row }"><el-tag size="small">{{ row.alert_type }}</el-tag></template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="180">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <el-button text type="primary" @click="showEditDialog(row)">编辑</el-button>
            <el-button text type="danger" @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-pagination v-model:current-page="store.docPagination.page" :page-size="store.docPagination.pageSize"
        :total="store.docPagination.total" layout="total, prev, pager, next" @current-change="store.fetchDocuments()"
        style="margin-top:16px; justify-content:flex-end" />
    </el-card>

    <!-- Document dialog -->
    <el-dialog v-model="dialogVisible" :title="isEdit ? '编辑文档' : '新建文档'" width="700px">
      <el-form :model="docForm" ref="docFormRef" label-width="100px">
        <el-form-item label="标题" prop="title">
          <el-input v-model="docForm.title" />
        </el-form-item>
        <el-form-item label="告警类型" prop="alert_type">
          <el-select v-model="docForm.alert_type" style="width:100%">
            <el-option label="MAC_FLAPPING" value="MAC_FLAPPING" />
            <el-option label="PORT_DOWN" value="PORT_DOWN" />
            <el-option label="CPU_HIGH" value="CPU_HIGH" />
          </el-select>
        </el-form-item>
        <el-form-item label="内容(Markdown)" prop="content">
          <el-input v-model="docForm.content" type="textarea" :rows="12" />
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
const docFormRef = ref()

const docForm = reactive({ title: '', alert_type: 'PORT_DOWN', content: '' })

onMounted(() => store.fetchDocuments())

function showAddDialog() {
  isEdit.value = false; editingId.value = null
  Object.assign(docForm, { title: '', alert_type: 'PORT_DOWN', content: '' })
  dialogVisible.value = true
}

function showEditDialog(row: any) {
  isEdit.value = true; editingId.value = row.id
  Object.assign(docForm, { title: row.title, alert_type: row.alert_type, content: row.content })
  dialogVisible.value = true
}

async function handleSave() {
  if (isEdit.value && editingId.value) {
    await store.updateDocument(editingId.value, { ...docForm })
  } else {
    await store.createDocument({ ...docForm })
  }
  dialogVisible.value = false
  ElMessage.success(isEdit.value ? '文档已更新' : '文档已创建')
}

async function handleDelete(row: any) {
  try {
    await ElMessageBox.confirm(`确认删除文档 "${row.title}"？`, '确认删除', { type: 'warning' })
    await store.deleteDocument(row.id)
    ElMessage.success('文档已删除')
  } catch { /* cancelled */ }
}

function onFilter() { store.fetchDocuments(filterAlertType.value || undefined) }
function formatTime(t: string) {
  if (!t) return '-'
  const fixed = /[Zz]$|[+-]\d{2}:\d{2}$/.test(t) ? t : t + 'Z'
  return new Date(fixed).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' })
}
</script>

<style scoped>
.card-header { display: flex; justify-content: space-between; align-items: center; }
</style>
