<!--
  MOD-WEB-F18: KnowledgeTestRetrievalView — RAG retrieval test.
  @covers REQ-WEBUI-FUNC-018
-->
<template>
  <div class="retrieval-page">
    <el-card>
      <template #header><span>知识库检索测试</span></template>

      <el-row :gutter="16" style="margin-bottom:16px">
        <el-col :span="8">
          <el-input v-model="query" placeholder="输入查询文本..." />
        </el-col>
        <el-col :span="4">
          <el-select v-model="alertType" placeholder="告警类型" clearable>
            <el-option label="MAC_FLAPPING" value="MAC_FLAPPING" />
            <el-option label="PORT_DOWN" value="PORT_DOWN" />
            <el-option label="CPU_HIGH" value="CPU_HIGH" />
          </el-select>
        </el-col>
        <el-col :span="2">
          <el-input-number v-model="topK" :min="1" :max="20" />
        </el-col>
        <el-col :span="4">
          <el-button type="primary" :loading="searching" @click="handleSearch">检索</el-button>
        </el-col>
      </el-row>

      <el-table :data="store.retrievalResults" stripe>
        <el-table-column prop="title" label="文档标题" />
        <el-table-column prop="content_snippet" label="内容摘要" show-overflow-tooltip width="300" />
        <el-table-column label="相似度" width="140">
          <template #default="{ row }">
            <el-progress :percentage="Math.round((row.similarity_score || row.relevance_score || 0) * 100)"
              :color="scoreColor(row.similarity_score || row.relevance_score || 0)" />
          </template>
        </el-table-column>
      </el-table>

      <el-empty v-if="!searching && store.retrievalResults.length === 0 && searched"
        description="未找到相似文档，建议扩充知识库" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useKnowledgeStore } from '@/stores/knowledge'

const store = useKnowledgeStore()
const query = ref('')
const alertType = ref('')
const topK = ref(5)
const searching = ref(false)
const searched = ref(false)

async function handleSearch() {
  if (!query.value.trim()) return
  searching.value = true
  searched.value = true
  try {
    await store.testRetrieval(query.value, alertType.value || undefined, topK.value)
  } finally {
    searching.value = false
  }
}

function scoreColor(score: number) {
  if (score >= 0.8) return '#67C23A'
  if (score >= 0.6) return '#E6A23C'
  return '#F56C6C'
}
</script>
