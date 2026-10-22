// 數字、時間與狀態用語集中在這裡
export const CAP = { chat: '對話', vision: '視覺', embedding: '嵌入', decision: '決策' }
export const ROLE_LABEL = { superuser: 'Superuser', admin: '管理員', member: '會員' }
export const MS = {
  loaded: { t: '已載入', c: 'good' },
  loading: { t: '載入中', c: 'warn' },
  unloading: { t: '卸載中', c: 'warn' },
  unloaded: { t: '未載入', c: 'idle' },
  error: { t: '錯誤', c: 'crit' },
}
export const DL = { not_downloaded: '未下載', downloading: '下載中', downloaded: '已下載', failed: '下載失敗' }
export const ENDPOINTS = ['chat/completions', 'embeddings', 'decisions']

export const fmtGB = (mb) => ((mb || 0) / 1024).toFixed(1)
export const fmtInt = (v) => Math.round(v || 0).toLocaleString('en-US')
export const pct = (r) => (Math.max(0, Math.min(1, r || 0)) * 100).toFixed(1) + '%'
export function fmtTok(v) {
  v = v || 0
  if (v >= 1e9) return (v / 1e9).toFixed(2) + 'B'
  if (v >= 1e6) return (v / 1e6).toFixed(v >= 1e7 ? 1 : 2) + 'M'
  if (v >= 1e3) return (v / 1e3).toFixed(v >= 1e4 ? 0 : 1) + 'K'
  return String(Math.round(v))
}
export const modelColor = (id) => `var(--s${((Math.max(1, id || 1) - 1) % 4) + 1})`
export const stc = (s) => (s < 300 ? 'good' : s >= 500 ? 'crit' : 'hold')

const pad = (n) => String(n).padStart(2, '0')
export function fmtTime(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  const today = new Date()
  const hms = `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
  return d.toDateString() === today.toDateString() ? hms : `${d.getMonth() + 1}/${d.getDate()} ${hms.slice(0, 5)}`
}
export function relTime(iso) {
  if (!iso) return '尚未使用'
  const sec = (Date.now() - new Date(iso).getTime()) / 1000
  if (sec < 60) return '剛剛'
  if (sec < 3600) return `${Math.floor(sec / 60)} 分鐘前`
  if (sec < 86400) return `${Math.floor(sec / 3600)} 小時前`
  return fmtTime(iso)
}
export const dayLabel = (iso) => { const d = new Date(iso + 'T00:00:00'); return `${d.getMonth() + 1}/${d.getDate()}` }
export const fmtDuration = (ms) => (ms == null ? '—' : ms >= 1000 ? (ms / 1000).toFixed(1) + ' s' : Math.round(ms) + ' ms')
export function addDays(n) {
  const d = new Date()
  d.setDate(d.getDate() + n)
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

// 密碼規則與後端一致：至少 16 碼、大小寫、數字、特殊符號
export const passwordRules = (pw, again) => [
  ['至少 16 碼', pw.length >= 16],
  ['大寫字母', /[A-Z]/.test(pw)],
  ['小寫字母', /[a-z]/.test(pw)],
  ['數字', /\d/.test(pw)],
  ['特殊符號', /[^A-Za-z0-9]/.test(pw)],
  ['兩次輸入相同', !!pw && pw === again],
]

export async function copyText(text, el) {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    if (el) {
      const r = document.createRange()
      r.selectNodeContents(el)
      const s = getSelection()
      s.removeAllRanges()
      s.addRange(r)
    }
    return false
  }
}
