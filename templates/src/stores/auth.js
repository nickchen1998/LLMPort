import { defineStore } from 'pinia'
import { api } from '../api/client'

const KEY = 'llmport_token'
const read = () => { try { return localStorage.getItem(KEY) || '' } catch { return '' } }
const write = (v) => { try { v ? localStorage.setItem(KEY, v) : localStorage.removeItem(KEY) } catch { /* 私密視窗 */ } }

export const useAuth = defineStore('auth', {
  state: () => ({ token: read(), user: null }),
  getters: {
    role: (s) => s.user?.role,
    isAdmin: (s) => ['superuser', 'admin'].includes(s.user?.role),
    isSU: (s) => s.user?.role === 'superuser',
    isMember: (s) => s.user?.role === 'member',
    home: () => '/dashboard',
  },
  actions: {
    async login(email, password) {
      const data = await api('/api/auth/login', { method: 'POST', form: { username: email, password } })
      this.token = data.access_token
      this.user = data.user
      write(this.token)
      return data.user
    },
    async fetchMe() {
      if (!this.token) return null
      this.user = await api('/api/auth/me')
      return this.user
    },
    logout() {
      this.token = ''
      this.user = null
      write('')
    },
  },
})
