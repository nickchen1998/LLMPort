// 呼叫後台 API：自動帶 JWT；401 時登出回登入頁。錯誤訊息整理成一句可以直接顯示的中文（/v1 錯誤則是英文原文）。
import { useAuth } from '../stores/auth'

export class ApiError extends Error {
  constructor(status, message, body) {
    super(message)
    this.status = status
    this.body = body
  }
}

export function errorMessage(data, status) {
  if (!data) return `發生錯誤（HTTP ${status}）`
  if (typeof data === 'string') return data
  if (typeof data.detail === 'string') return data.detail
  if (Array.isArray(data.detail)) return data.detail.map((d) => d.msg).join('；')
  if (data.error?.message) return data.error.message
  return `發生錯誤（HTTP ${status}）`
}

export async function api(path, { method = 'GET', body, form, raw = false } = {}) {
  const auth = useAuth()
  const headers = {}
  if (auth.token) headers.Authorization = `Bearer ${auth.token}`
  let payload
  if (form) {
    payload = new URLSearchParams(form)
    headers['Content-Type'] = 'application/x-www-form-urlencoded'
  } else if (body !== undefined) {
    payload = JSON.stringify(body)
    headers['Content-Type'] = 'application/json'
  }
  const res = await fetch(path, { method, headers, body: payload })
  if (res.status === 401 && auth.token && !path.startsWith('/api/auth/login')) {
    auth.logout()
    window.location.assign('/login')
    throw new ApiError(401, '請重新登入')
  }
  if (raw) return res
  const text = await res.text()
  let data = null
  try {
    data = text ? JSON.parse(text) : null
  } catch {
    data = text
  }
  if (!res.ok) throw new ApiError(res.status, errorMessage(data, res.status), data)
  return data
}
