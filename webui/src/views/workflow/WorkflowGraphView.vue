<!--
  MOD-WEB-F14: WorkflowGraphView — LangGraph 14-node topology visualization.
  @covers REQ-WEBUI-FUNC-005, REQ-WEBUI-FUNC-006
-->
<template>
  <div class="workflow-page" v-loading="loading">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>LangGraph 工作流拓扑 (14 节点)</span>
          <el-select v-model="selectedAlertId" placeholder="选择告警查看活跃节点" clearable style="width:260px">
            <el-option v-for="a in alerts" :key="a.alert_id" :label="`${a.alert_id?.substring(0,8)}... (${a.alert_type})`"
              :value="a.alert_id" />
          </el-select>
        </div>
      </template>
      <v-chart :option="graphOption" style="height:600px" autoresize />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { use } from 'echarts/core'
import { GraphChart } from 'echarts/charts'
import { TitleComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import VChart from 'vue-echarts'
import client from '@/api/client'

use([GraphChart, TitleComponent, TooltipComponent, CanvasRenderer])

const nodes = ref<any[]>([])
const edges = ref<any[]>([])
const loading = ref(false)
const selectedAlertId = ref('')
const alerts = ref<any[]>([])

onMounted(async () => {
  loading.value = true
  try {
    const resp: any = await client.get('/api/workflow/graph')
    nodes.value = resp.nodes || []
    edges.value = resp.edges || []
  } finally {
    loading.value = false
  }
})

const graphOption = computed(() => ({
  tooltip: {},
  series: [{
    type: 'graph',
    layout: 'force',
    force: { repulsion: 500, edgeLength: [120, 240] },
    roam: true,
    draggable: true,
    label: { show: true, fontSize: 11 },
    data: nodes.value.map(n => ({
      name: n.id,
      label: { show: true, formatter: n.label || n.id },
    })),
    links: edges.value.map(e => ({
      source: e.source,
      target: e.target,
      label: { show: true, formatter: e.label || '' },
    })),
  }],
}))
</script>

<style scoped>
.card-header { display: flex; justify-content: space-between; align-items: center; }
</style>
