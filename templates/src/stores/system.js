// 管理者頁面共用的即時狀態：EventSource 接 /api/system/stream（每 2 秒一次）
import { defineStore } from 'pinia'
import { useAuth } from './auth'

export const useSystem = defineStore('system', {
  state: () => ({ snap: null, connected: false, es: null }),
  getters: {
    budget: (s) => s.snap?.budget,
    host: (s) => s.snap?.host,
    runtimes: (s) => s.snap?.models || {},
    tunnel: (s) => s.snap?.tunnel || 'unknown',
  },
  actions: {
    connect() {
      const auth = useAuth()
      if (this.es || !auth.token || !auth.isAdmin) return
      const es = new EventSource(`/api/system/stream?token=${encodeURIComponent(auth.token)}`)
      es.onmessage = (e) => {
        try { this.snap = JSON.parse(e.data); this.connected = true } catch { /* 忽略 */ }
      }
      es.onerror = () => { this.connected = false }
      this.es = es
    },
    disconnect() {
      this.es?.close()
      this.es = null
      this.connected = false
    },
  },
})
