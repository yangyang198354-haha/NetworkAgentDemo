/**
 * MOD-WEB-F02: Router — Vue Router configuration with auth guard.
 * @module Router
 *
 * Route table with lazy-loaded views and beforeEach auth guard.
 */

import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

const routes: Array<RouteRecordRaw> = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/LoginView.vue'),
    meta: { requiresAuth: false, title: '登录' },
  },
  {
    path: '/',
    component: () => import('@/layout/AppShell.vue'),
    redirect: '/dashboard',
    meta: { requiresAuth: true },
    children: [
      {
        path: 'dashboard',
        name: 'Dashboard',
        component: () => import('@/views/dashboard/DashboardView.vue'),
        meta: { requiresAuth: true, title: 'Dashboard' },
      },
      {
        path: 'alerts',
        name: 'AlertsList',
        component: () => import('@/views/alerts/AlertsListView.vue'),
        meta: { requiresAuth: true, title: '告警管理' },
      },
      {
        path: 'alerts/simulate',
        name: 'AlertsSimulate',
        component: () => import('@/views/alerts/AlertsSimulateView.vue'),
        meta: { requiresAuth: true, title: '模拟告警' },
      },
      {
        path: 'alerts/:alertId',
        name: 'AlertsDetail',
        component: () => import('@/views/alerts/AlertsDetailView.vue'),
        meta: { requiresAuth: true, title: '告警详情' },
      },
      {
        path: 'workflow',
        name: 'WorkflowGraph',
        component: () => import('@/views/workflow/WorkflowGraphView.vue'),
        meta: { requiresAuth: true, title: '工作流可视化' },
      },
      {
        path: 'approvals/pending',
        name: 'ApprovalsPending',
        component: () => import('@/views/approvals/ApprovalsPendingView.vue'),
        meta: { requiresAuth: true, title: '待审批' },
      },
      {
        path: 'approvals/:checkpointId',
        name: 'ApprovalsDetail',
        component: () => import('@/views/approvals/ApprovalsDetailView.vue'),
        meta: { requiresAuth: true, title: '审批详情' },
      },
      {
        path: 'approvals/history',
        name: 'ApprovalsHistory',
        component: () => import('@/views/approvals/ApprovalsHistoryView.vue'),
        meta: { requiresAuth: true, title: '审批历史' },
      },
      {
        path: 'devices',
        name: 'DevicesList',
        component: () => import('@/views/devices/DevicesListView.vue'),
        meta: { requiresAuth: true, title: '设备管理' },
      },
      {
        path: 'inspection',
        name: 'InspectionConfig',
        component: () => import('@/views/inspection/InspectionConfigView.vue'),
        meta: { requiresAuth: true, title: '巡检配置' },
      },
      {
        path: 'inspection/history',
        name: 'InspectionHistory',
        component: () => import('@/views/inspection/InspectionHistoryView.vue'),
        meta: { requiresAuth: true, title: '巡检历史' },
      },
      {
        path: 'knowledge/documents',
        name: 'KnowledgeDocuments',
        component: () => import('@/views/knowledge/KnowledgeDocumentsView.vue'),
        meta: { requiresAuth: true, title: '知识文档' },
      },
      {
        path: 'knowledge/templates',
        name: 'KnowledgeTemplates',
        component: () => import('@/views/knowledge/KnowledgeTemplatesView.vue'),
        meta: { requiresAuth: true, title: '命令模板' },
      },
      {
        path: 'knowledge/test-retrieval',
        name: 'KnowledgeTestRetrieval',
        component: () => import('@/views/knowledge/KnowledgeTestRetrievalView.vue'),
        meta: { requiresAuth: true, title: '检索测试' },
      },
      {
        path: 'system/config',
        name: 'SystemConfig',
        component: () => import('@/views/system/SystemConfigView.vue'),
        meta: { requiresAuth: true, title: '系统配置' },
      },
      {
        path: 'system/logs',
        name: 'SystemLogs',
        component: () => import('@/views/system/SystemLogsView.vue'),
        meta: { requiresAuth: true, title: '系统日志' },
      },
    ],
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

// ── Global auth guard ──────────────────────────────────────

router.beforeEach((to, _from, next) => {
  if (to.meta.requiresAuth) {
    let token = ''
    try {
      const stored = localStorage.getItem('auth_token')
      if (stored) {
        token = JSON.parse(stored)
      }
    } catch {
      token = ''
    }

    if (!token) {
      next('/login')
    } else {
      next()
    }
  } else if (to.path === '/login') {
    // Already logged in → redirect to dashboard
    let token = ''
    try {
      const stored = localStorage.getItem('auth_token')
      if (stored) {
        token = JSON.parse(stored)
      }
    } catch {
      token = ''
    }
    if (token) {
      next('/dashboard')
    } else {
      next()
    }
  } else {
    next()
  }
})

export default router
