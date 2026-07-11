/**
 * MOD-WEB-F04: AuthStore — Authentication state management.
 * @module Pinia Auth Store
 *
 * Manages JWT token, user info, login/logout actions.
 * Token persisted in localStorage for page refresh survival.
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import client from '@/api/client'

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(null)
  const user = ref<{ username: string } | null>(null)

  const isAuthenticated = computed(() => !!token.value)

  // Restore from localStorage on init
  function _loadFromStorage() {
    try {
      const storedToken = localStorage.getItem('auth_token')
      const storedUser = localStorage.getItem('auth_user')
      if (storedToken) {
        token.value = JSON.parse(storedToken)
      }
      if (storedUser) {
        user.value = JSON.parse(storedUser)
      }
    } catch {
      token.value = null
      user.value = null
    }
  }

  async function login(username: string, password: string) {
    const formData = new URLSearchParams()
    formData.append('username', username)
    formData.append('password', password)

    const resp: any = await client.post('/auth/login', formData, {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    })

    token.value = resp.access_token
    user.value = { username }

    localStorage.setItem('auth_token', JSON.stringify(resp.access_token))
    localStorage.setItem('auth_user', JSON.stringify({ username }))

    return resp
  }

  function logout() {
    token.value = null
    user.value = null
    localStorage.removeItem('auth_token')
    localStorage.removeItem('auth_user')
  }

  function checkAuth() {
    _loadFromStorage()
  }

  // Initialize on store creation
  _loadFromStorage()

  return { token, user, isAuthenticated, login, logout, checkAuth }
})
