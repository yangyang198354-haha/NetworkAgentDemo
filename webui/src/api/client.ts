/**
 * MOD-WEB-F03: ApiClient — Axios HTTP client with JWT interceptors.
 * @module ApiClient
 *
 * Features:
 * - baseURL: '/' (same-origin deployment)
 * - Request interceptor: injects Authorization: Bearer {token}
 * - Response interceptor: 401 → clear token + redirect to /login
 * - Timeout: 15 seconds
 */

import axios, { type AxiosInstance, type AxiosResponse } from 'axios'
import { ElMessage } from 'element-plus'

const client: AxiosInstance = axios.create({
  baseURL: '/',
  timeout: 15000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// ── Request interceptor: inject JWT token ──────────────────

client.interceptors.request.use(
  (config) => {
    // Try Pinia store first; fallback to localStorage
    let token = ''
    try {
      const stored = localStorage.getItem('auth_token')
      if (stored) {
        token = JSON.parse(stored)
      }
    } catch {
      token = ''
    }

    if (token && config.headers) {
      config.headers['Authorization'] = `Bearer ${token}`
    }
    return config
  },
  (error) => Promise.reject(error)
)

// ── Response interceptor: handle 401 + errors ─────────────

client.interceptors.response.use(
  (response: AxiosResponse) => {
    return response.data
  },
  (error) => {
    if (error.response) {
      const status = error.response.status
      const detail = error.response.data?.detail || '请求失败'

      if (status === 401) {
        localStorage.removeItem('auth_token')
        localStorage.removeItem('auth_user')
        ElMessage.error('登录已过期，请重新登录')
        // Redirect using window.location (outside of router context)
        window.location.href = '/login?expired=true'
      } else if (status === 403) {
        ElMessage.error('没有权限执行此操作')
      } else if (status >= 500) {
        ElMessage.error('服务器错误，请稍后重试')
      } else {
        ElMessage.error(detail)
      }
    } else if (error.request) {
      ElMessage.error('网络请求失败，请检查网络连接')
    } else {
      ElMessage.error(error.message || '请求异常')
    }
    return Promise.reject(error)
  }
)

export default client
