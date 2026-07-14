<!--
  MOD-WEB-F01: SidebarNav — Sidebar navigation menu with approval badge.
  @covers REQ-WEBUI-FUNC-027
-->
<template>
  <div class="sidebar-logo">
    <span v-if="!collapsed" class="logo-text">NetworkAgent</span>
    <span v-else class="logo-text-short">NA</span>
  </div>

  <el-menu
    :default-active="activeRoute"
    router
    background-color="#304156"
    text-color="#bfcbd9"
    active-text-color="#409EFF"
    :collapse="collapsed"
  >
    <el-menu-item index="/dashboard">
      <el-icon><HomeFilled /></el-icon>
      <span>Dashboard</span>
    </el-menu-item>

    <el-menu-item index="/alerts">
      <el-icon><Bell /></el-icon>
      <span>告警管理</span>
    </el-menu-item>

    <el-menu-item index="/workflow">
      <el-icon><Share /></el-icon>
      <span>工作流可视化</span>
    </el-menu-item>

    <el-sub-menu index="approvals-sub">
      <template #title>
        <el-icon><Check /></el-icon>
        <span>审批管理</span>
        <el-badge v-if="approvalsStore.pendingCount > 0" :value="approvalsStore.pendingCount" class="approval-badge" />
      </template>
      <el-menu-item index="/approvals/pending">待审批</el-menu-item>
      <el-menu-item index="/approvals/history">审批历史</el-menu-item>
    </el-sub-menu>

    <el-menu-item index="/devices">
      <el-icon><Monitor /></el-icon>
      <span>设备管理</span>
    </el-menu-item>

    <el-sub-menu index="inspection-sub">
      <template #title>
        <el-icon><Refresh /></el-icon>
        <span>AI 巡检</span>
      </template>
      <el-menu-item index="/inspection/config">
        <el-icon><Setting /></el-icon>
        <span>巡检配置</span>
      </el-menu-item>
      <el-menu-item index="/inspection/history">
        <el-icon><Document /></el-icon>
        <span>巡检记录</span>
      </el-menu-item>
      <el-menu-item index="/inspection/manual">
        <el-icon><VideoPlay /></el-icon>
        <span>手动巡检</span>
      </el-menu-item>
    </el-sub-menu>

    <el-sub-menu index="knowledge-sub">
      <template #title>
        <el-icon><Notebook /></el-icon>
        <span>知识库管理</span>
      </template>
      <el-menu-item index="/knowledge/documents">文档</el-menu-item>
      <el-menu-item index="/knowledge/templates">模板</el-menu-item>
    </el-sub-menu>

    <el-sub-menu index="system-sub">
      <template #title>
        <el-icon><Setting /></el-icon>
        <span>系统配置</span>
      </template>
      <el-menu-item index="/system/config">全局配置</el-menu-item>
      <el-menu-item index="/system/logs">系统日志</el-menu-item>
    </el-sub-menu>
  </el-menu>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useApprovalsStore } from '@/stores/approvals'

defineProps<{ collapsed: boolean }>()

const route = useRoute()
const approvalsStore = useApprovalsStore()

const activeRoute = computed(() => route.path)

onMounted(() => {
  approvalsStore.fetchPendingApprovals()
})
</script>

<style scoped>
.sidebar-logo {
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 18px;
  font-weight: bold;
  border-bottom: 1px solid rgba(255,255,255,0.1);
}

.logo-text-short {
  font-size: 16px;
}

.approval-badge {
  margin-left: 8px;
}

.el-menu {
  border-right: none;
}
</style>
