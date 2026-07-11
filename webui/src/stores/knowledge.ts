/**
 * MOD-WEB-F09: KnowledgeStore — Knowledge documents, templates, retrieval test.
 */

import { defineStore } from 'pinia'
import { ref, reactive } from 'vue'
import client from '@/api/client'

export const useKnowledgeStore = defineStore('knowledge', () => {
  const documentList = ref<any[]>([])
  const templateList = ref<any[]>([])
  const retrievalResults = ref<any[]>([])
  const docPagination = reactive({ page: 1, pageSize: 20, total: 0 })
  const loading = ref(false)

  // Document actions
  async function fetchDocuments(alertType?: string) {
    loading.value = true
    try {
      const params: any = { page: docPagination.page, page_size: docPagination.pageSize }
      if (alertType) params.alert_type = alertType
      const resp: any = await client.get('/api/knowledge/documents', { params })
      documentList.value = resp.items || []
      docPagination.total = resp.total || 0
    } finally {
      loading.value = false
    }
  }

  async function createDocument(data: Record<string, any>) {
    const resp = await client.post('/api/knowledge/documents', data)
    await fetchDocuments()
    return resp
  }

  async function updateDocument(id: number, data: Record<string, any>) {
    const resp = await client.put(`/api/knowledge/documents/${id}`, data)
    await fetchDocuments()
    return resp
  }

  async function deleteDocument(id: number) {
    const resp = await client.delete(`/api/knowledge/documents/${id}`)
    await fetchDocuments()
    return resp
  }

  // Template actions
  async function fetchTemplates(alertType?: string) {
    const params: any = {}
    if (alertType) params.alert_type = alertType
    const resp: any = await client.get('/api/knowledge/templates', { params })
    templateList.value = resp.templates || []
    return resp
  }

  async function createTemplate(data: Record<string, any>) {
    const resp = await client.post('/api/knowledge/templates', data)
    await fetchTemplates()
    return resp
  }

  async function updateTemplate(id: number, data: Record<string, any>) {
    const resp = await client.put(`/api/knowledge/templates/${id}`, data)
    await fetchTemplates()
    return resp
  }

  async function deleteTemplate(id: number) {
    const resp = await client.delete(`/api/knowledge/templates/${id}`)
    await fetchTemplates()
    return resp
  }

  // Retrieval test
  async function testRetrieval(query: string, alertType?: string, topK: number = 5) {
    const resp: any = await client.post('/api/knowledge/test-retrieval', { query, alert_type: alertType, top_k: topK })
    retrievalResults.value = resp.results || []
    return resp
  }

  return { documentList, templateList, retrievalResults, docPagination, loading,
    fetchDocuments, createDocument, updateDocument, deleteDocument,
    fetchTemplates, createTemplate, updateTemplate, deleteTemplate, testRetrieval }
})
