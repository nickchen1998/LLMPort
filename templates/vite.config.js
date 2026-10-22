import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 開發時 /api 與 /v1 代理到 FastAPI（預設 http://127.0.0.1:8080，可用 VITE_API_TARGET 調整）
const target = process.env.VITE_API_TARGET || 'http://127.0.0.1:8080'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target, changeOrigin: true },
      '/v1': { target, changeOrigin: true },
    },
  },
})
