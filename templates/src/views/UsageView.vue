<script setup>
// 用量統計：管理者看全部會員（依會員），會員只看自己（依金鑰）
import { computed, onMounted, ref, watch } from 'vue'
import StackedBars from '../components/StackedBars.vue'
import Pill from '../components/Pill.vue'
import { api } from '../api/client'
import { useAuth } from '../stores/auth'
import { toast } from '../stores/toast'
import { dayLabel, fmtInt, fmtTok, modelColor, pct } from '../composables/format'

const auth = useAuth()
const days = ref(14)
const userId = ref(0)
const modelId = ref(0)
const view = ref('chart')
const data = ref(null)
const members = ref([])
const models = ref([])

async function load() {
  const qs = new URLSearchParams({ days: days.value })
  if (modelId.value) qs.set('model_id', modelId.value)
  if (auth.isAdmin && userId.value) qs.set('user_id', userId.value)
  data.value = await api(`${auth.isAdmin ? '/api/usage' : '/api/me/usage'}?${qs}`)
}
onMounted(async () => {
  if (auth.isAdmin) {
    const [m, ms] = await Promise.all([api('/api/members'), api('/api/models')])
    members.value = m
    models.value = ms.models
  } else {
    models.value = await api('/api/me/models')
  }
  load()
})
watch([days, userId, modelId], load)

const labels = computed(() => (data.value?.dates || []).map(dayLabel))
const series = computed(() => (data.value?.series || []).map((s) => ({ key: s.model_id, name: s.name, color: modelColor(s.model_id), values: s.prompt.map((p, i) => p + s.completion[i]) })))
const totals = computed(() => data.value?.totals || { prompt_tokens: 0, completion_tokens: 0, requests: 0, errors: 0 })
const dayRows = computed(() => labels.value.map((label, i) => ({ label, vals: series.value.map((s) => s.values[i]), total: series.value.reduce((a, s) => a + s.values[i], 0) })).reverse())

async function exportCsv() {
  try {
    const res = await api(`/api/usage/export.csv?days=${days.value}`, { raw: true })
    const url = URL.createObjectURL(await res.blob())
    const a = Object.assign(document.createElement('a'), { href: url, download: `llmport-usage-${days.value}d.csv` })
    a.click()
    URL.revokeObjectURL(url)
  } catch (e) { toast(e.message) }
}
</script>

<template>
  <div class="page">
    <div class="filters">
      <div class="seg" role="group" aria-label="期間"><button v-for="p in [7, 14, 30, 90]" :key="p" :class="{ on: days === p }" @click="days = p">近 {{ p }} 天</button></div>
      <select v-if="auth.isAdmin" id="usage-member" v-model.number="userId" class="input input-sm" aria-label="會員"><option :value="0">全部帳號</option><option v-for="x in members" :key="x.id" :value="x.id">{{ x.name }}</option></select>
      <select id="usage-model" v-model.number="modelId" class="input input-sm" aria-label="模型"><option :value="0">全部模型</option><option v-for="x in models" :key="x.id" :value="x.id">{{ x.api_name }}</option></select>
      <button v-if="auth.isAdmin" class="btn btn-s btn-sm ml-auto" @click="exportCsv">匯出 CSV</button>
    </div>
    <section class="tiles">
      <div class="card tile"><div class="label">Token 合計</div><div class="tile-v num">{{ fmtTok(totals.prompt_tokens + totals.completion_tokens) }}</div><div class="t12 muted">近 {{ days }} 天</div></div>
      <div class="card tile"><div class="label">輸入 Token</div><div class="tile-v num">{{ fmtTok(totals.prompt_tokens) }}</div><div class="t12 muted">含圖片換算與嵌入</div></div>
      <div class="card tile"><div class="label">輸出 Token</div><div class="tile-v num">{{ fmtTok(totals.completion_tokens) }}</div><div class="t12 muted">嵌入與決策沒有輸出 token</div></div>
      <div class="card tile"><div class="label">請求數</div><div class="tile-v num">{{ fmtInt(totals.requests) }}</div><div class="t12 muted">其中錯誤 {{ fmtInt(totals.errors) }} 筆</div></div>
    </section>
    <section class="card">
      <div class="card-h"><h2>每日 Token（依模型）</h2>
        <div class="seg ml-auto" role="group" aria-label="檢視方式"><button :class="{ on: view === 'chart' }" @click="view = 'chart'">圖表</button><button :class="{ on: view === 'table' }" @click="view = 'table'">表格</button></div></div>
      <template v-if="series.length">
        <template v-if="view === 'chart'">
          <div class="legend" style="margin-bottom: 8px"><span v-for="s in series" :key="s.key" class="lg"><i :style="{ background: s.color }"></i><span class="mono">{{ s.name }}</span></span></div>
          <StackedBars :labels="labels" :series="series" />
        </template>
        <div v-else class="scroll-x" style="max-height: 340px; overflow-y: auto"><table class="tbl"><thead><tr><th>日期</th><th v-for="s in series" :key="s.key" class="r mono">{{ s.name }}</th><th class="r">合計</th></tr></thead>
          <tbody><tr v-for="d in dayRows" :key="d.label"><td class="num">{{ d.label }}</td><td v-for="(v, j) in d.vals" :key="j" class="r">{{ fmtTok(v) }}</td><td class="r strong">{{ fmtTok(d.total) }}</td></tr></tbody></table></div>
      </template>
      <div v-else class="empty">這段期間沒有用量。</div>
    </section>
    <section v-if="auth.isAdmin && data" class="card">
      <div class="card-h"><h2>依帳號</h2><span class="t13 muted">近 {{ days }} 天</span></div>
      <div class="scroll-x"><table class="tbl">
        <thead><tr><th>帳號</th><th class="r">請求</th><th class="r">輸入</th><th class="r">輸出</th><th class="r">合計</th><th>本月配額</th></tr></thead>
        <tbody><tr v-for="r in data.by_user" :key="r.user_id">
          <td><span class="strong">{{ r.name }}</span> <span v-if="r.is_admin" class="cap">測試台</span> <Pill v-if="!r.is_active" c="idle" t="已停用" /></td>
          <td class="r">{{ fmtInt(r.requests) }}</td><td class="r">{{ fmtTok(r.prompt_tokens) }}</td><td class="r">{{ fmtTok(r.completion_tokens) }}</td><td class="r strong">{{ fmtTok(r.prompt_tokens + r.completion_tokens) }}</td>
          <td><div v-if="!r.is_admin" style="display: flex; align-items: center; gap: 8px"><span class="meter meter-sm" :class="r.monthly_token_quota && r.month_used / r.monthly_token_quota > 0.9 ? 'crit' : ''"><i :style="{ width: pct(r.monthly_token_quota ? r.month_used / r.monthly_token_quota : 0) }"></i></span><span class="t12 muted num">{{ r.monthly_token_quota ? ((r.month_used / r.monthly_token_quota) * 100).toFixed(0) + '%' : '不限' }}</span></div></td>
        </tr></tbody>
      </table></div>
      <div v-if="!data.by_user.length" class="empty">這段期間沒有用量。</div>
    </section>
    <section v-if="!auth.isAdmin && data" class="card">
      <div class="card-h"><h2>依金鑰</h2><span class="t13 muted">近 {{ days }} 天</span></div>
      <div class="scroll-x"><table class="tbl"><thead><tr><th>金鑰</th><th class="r">請求</th><th class="r">輸入</th><th class="r">輸出</th><th class="r">合計</th></tr></thead>
        <tbody><tr v-for="r in data.by_key" :key="r.api_key_id"><td><span class="strong">{{ r.name }}</span> <span class="mono t12 muted">{{ r.masked }}</span> <span v-if="r.revoked" class="cap">已撤銷</span></td><td class="r">{{ fmtInt(r.requests) }}</td><td class="r">{{ fmtTok(r.prompt_tokens) }}</td><td class="r">{{ fmtTok(r.completion_tokens) }}</td><td class="r strong">{{ fmtTok(r.prompt_tokens + r.completion_tokens) }}</td></tr></tbody></table></div>
      <div v-if="!data.by_key.length" class="empty">這段期間沒有用量。</div>
    </section>
  </div>
</template>
