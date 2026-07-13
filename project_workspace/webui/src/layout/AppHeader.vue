<!--
  MOD-WEB-F01: AppHeader — Top header with collapse button, breadcrumb, and user area.
  @covers REQ-WEBUI-FUNC-028
-->
<template>
  <div class="header-left">
    <el-button text @click="$emit('toggle')">
      <el-icon :size="20"><Fold v-if="!collapsed" /><Expand v-else /></el-icon>
    </el-button>
    <el-breadcrumb separator="/" class="header-breadcrumb">
      <el-breadcrumb-item :to="{ path: '/dashboard' }">首页</el-breadcrumb-item>
      <el-breadcrumb-item v-for="(item, idx) in breadcrumbs" :key="idx">
        {{ item }}
      </el-breadcrumb-item>
    </el-breadcrumb>
  </div>

  <div class="header-right">
    <span class="user-info">
      <el-icon><User /></el-icon>
      {{ authStore.user?.username || 'admin' }}
    </span>
    <el-button text @click="handleLogout">
      <el-icon><SwitchButton /></el-icon>
      退出登录
    </el-button>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

defineProps<{ collapsed: boolean }>()
defineEmits<{ (e: 'toggle'): void }>()

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

const breadcrumbs = computed(() => {
  const meta = route.meta
  const titles: string[] = []
  if (meta.title && typeof meta.title === 'string') {
    titles.push(meta.title)
  }
  return titles
})

function handleLogout() {
  authStore.logout()
  router.push('/login')
}
</script>

<style scoped>
.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
  flex: 1;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 16px;
}

.header-breadcrumb {
  margin-left: 12px;
}

.user-info {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 14px;
  color: #606266;
}
</style>
