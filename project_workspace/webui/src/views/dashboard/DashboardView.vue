<!--
  MOD-WEB-F12: DashboardView — Main dashboard with stats, charts, health panel.
  @covers REQ-WEBUI-FUNC-022, REQ-WEBUI-FUNC-023, REQ-WEBUI-FUNC-024
-->
<template>
  <div class="dashboard" v-loading="store.loading">
    <!-- Stat cards -->
    <el-row :gutter="20" class="stat-row">
      <el-col :span="6">
        <el-card shadow="hover">
          <div class="stat-card">
            <div class="stat-value">{{ store.alertStats?.total_count || 0 }}</div>
            <div class="stat-label">总告警数</div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover">
          <div class="stat-card">
            <div class="stat-value" style="color:#409EFF">{{ store.alertStats?.today_count || 0 }}</div>
            <div class="stat-label">今日告警</div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover">
          <div class="stat-card">
            <div class="stat-value" style="color:#E6A23C">{{ store.alertStats?.pending_approval_count || 0 }}</div>
            <div class="stat-label">待审批</div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover">
          <div class="stat-card">
            <div class="stat-value" style="color:#67C23A">{{ store.fixRate?.success_rate || 0 }}%</div>
            <div class="stat-label">修复成功率</div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- Charts row -->
    <el-row :gutter="20" class="chart-row">
      <el-col :span="12">
        <el-card>
          <template #header><span>告警类型分布</span></template>
          <v-chart :option="typePieOption" style="height:300px" autoresize />
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card>
          <template #header><span>告警严重级别</span></template>
          <v-chart :option="severityBarOption" style="height:300px" autoresize />
        </el-card>
      </el-col>
    </el-row>

    <!-- Fix rate chart -->
    <el-row :gutter="20" class="chart-row">
      <el-col :span="24">
        <el-card>
          <template #header><span>修复成功率分布</span></template>
          <v-chart :option="fixRatePieOption" style="height:300px" autoresize />
        </el-card>
      </el-col>
    </el-row>

    <!-- Health panel -->
    <el-row :gutter="20" class="chart-row">
      <el-col :span="24">
        <el-card>
          <template #header><span>系统健康状态</span></template>
          <div class="health-panel">
            <el-tag v-for="(val, key) in store.healthStatus" :key="key"
              :type="val?.status === 'healthy' ? 'success' : 'danger'" size="large" class="health-tag">
              {{ key }}: {{ val?.detail || val?.status }}
            </el-tag>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted } from 'vue'
import { use } from 'echarts/core'
import { PieChart, BarChart, LineChart } from 'echarts/charts'
import { TitleComponent, TooltipComponent, LegendComponent, GridComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import VChart from 'vue-echarts'
import { useDashboardStore } from '@/stores/dashboard'

use([PieChart, BarChart, LineChart, TitleComponent, TooltipComponent, LegendComponent, GridComponent, CanvasRenderer])

const store = useDashboardStore()
let healthInterval: any = null

onMounted(async () => {
  await store.fetchStats()
  await store.fetchHealthStatus()
  healthInterval = setInterval(() => store.fetchHealthStatus(), 3000)
})

onUnmounted(() => {
  if (healthInterval) clearInterval(healthInterval)
})

const typePieOption = computed(() => ({
  tooltip: { trigger: 'item' },
  legend: { bottom: 0 },
  series: [{
    type: 'pie',
    radius: ['40%', '70%'],
    data: (store.alertStats?.by_type || []).map((t: any) => ({ name: t.type, value: t.count })),
  }],
}))

const severityBarOption = computed(() => ({
  tooltip: { trigger: 'axis' },
  xAxis: { type: 'category', data: (store.alertStats?.by_severity || []).map((s: any) => s.severity) },
  yAxis: { type: 'value' },
  series: [{
    type: 'bar',
    data: (store.alertStats?.by_severity || []).map((s: any) => s.count),
  }],
}))

const fixRatePieOption = computed(() => ({
  tooltip: { trigger: 'item' },
  legend: { bottom: 0 },
  series: [{
    type: 'pie',
    radius: '70%',
    data: [
      { name: '成功', value: store.fixRate?.closed_count || 0, itemStyle: { color: '#67C23A' } },
      { name: '失败', value: store.fixRate?.failed_count || 0, itemStyle: { color: '#F56C6C' } },
      { name: '拒绝', value: store.fixRate?.rejected_count || 0, itemStyle: { color: '#E6A23C' } },
    ],
  }],
}))
</script>

<style scoped>
.stat-row {
  margin-bottom: 20px;
}
.stat-card {
  text-align: center;
  padding: 10px 0;
}
.stat-value {
  font-size: 32px;
  font-weight: bold;
  color: #303133;
}
.stat-label {
  font-size: 14px;
  color: #909399;
  margin-top: 8px;
}
.chart-row {
  margin-bottom: 20px;
}
.health-panel {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
}
.health-tag {
  font-size: 14px;
  padding: 8px 16px;
}
</style>
