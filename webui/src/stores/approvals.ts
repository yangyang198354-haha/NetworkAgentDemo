/**
 * MOD-WEB-F06: ApprovalsStore — Approval pending/history state.
 */

import { defineStore } from 'pinia'
import { ref, reactive } from 'vue'
import client from '@/api/client'

export const useApprovalsStore = defineStore('approvals', () => {
  const pendingList = ref<any[]>([])
  const pendingCount = ref(0)
  const historyList = ref<any[]>([])
  const currentApproval = ref<any | null>(null)
  const pagination = reactive({ page: 1, pageSize: 20, total: 0 })
  const loading = ref(false)

  async function fetchPendingApprovals() {
    loading.value = true
    try {
      const resp: any = await client.get('/api/approvals/pending')
      pendingList.value = resp.pending || []
      pendingCount.value = resp.count || 0
    } finally {
      loading.value = false
    }
  }

  async function fetchApprovalDetail(checkpointId: string) {
    const resp: any = await client.get(`/api/approvals/${checkpointId}/detail`)
    currentApproval.value = resp
    return resp
  }

  async function submitDecision(checkpointId: string, decision: string, note: string = '') {
    const resp: any = await client.post(`/api/approvals/${checkpointId}/decide`, { decision, note })
    await fetchPendingApprovals()
    return resp
  }

  async function fetchHistory(filters: any = {}) {
    loading.value = true
    try {
      const params: any = { page: pagination.page, page_size: pagination.pageSize, ...filters }
      const resp: any = await client.get('/api/approvals/history', { params })
      historyList.value = resp.items || []
      pagination.total = resp.total || 0
    } finally {
      loading.value = false
    }
  }

  return { pendingList, pendingCount, historyList, currentApproval, pagination, loading,
    fetchPendingApprovals, fetchApprovalDetail, submitDecision, fetchHistory }
})
