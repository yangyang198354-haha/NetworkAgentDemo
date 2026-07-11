<!--
  MOD-WEB-F01: AppShell — Global layout with sidebar + header + content area.
  @covers REQ-WEBUI-FUNC-027, REQ-WEBUI-FUNC-028, REQ-WEBUI-NFUNC-007
-->
<template>
  <el-container class="app-shell">
    <!-- Sidebar -->
    <el-aside :width="isCollapsed ? '64px' : '220px'" class="app-sidebar">
      <SidebarNav :collapsed="isCollapsed" />
    </el-aside>

    <!-- Main area -->
    <el-container>
      <el-header class="app-header">
        <AppHeader :collapsed="isCollapsed" @toggle="toggleSidebar" />
      </el-header>
      <el-main class="app-main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import SidebarNav from './SidebarNav.vue'
import AppHeader from './AppHeader.vue'

const isCollapsed = ref(false)

function toggleSidebar() {
  isCollapsed.value = !isCollapsed.value
}
</script>

<style scoped>
.app-shell {
  height: 100vh;
}

.app-sidebar {
  background-color: #304156;
  overflow-x: hidden;
  transition: width 0.3s;
}

.app-header {
  background: #fff;
  border-bottom: 1px solid #e6e6e6;
  display: flex;
  align-items: center;
  padding: 0 20px;
  height: 56px;
}

.app-main {
  background: #f0f2f5;
  min-height: calc(100vh - 56px);
  padding: 20px;
}
</style>
