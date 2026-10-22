<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import MemBar from '../../components/MemBar.vue'
import Pill from '../../components/Pill.vue'
import Spark from '../../components/Spark.vue'
import { api } from '../../api/client'
import { useSystem } from '../../stores/system'
import { CAP, MS, fmtDuration, fmtGB, fmtInt, fmtTime, fmtTok, modelColor, pct, stc } from '../../composables/format'

const system = useSystem()
const router = useRouter()
const data = ref(null)
let timer = null
async function load() { data.value = await api('/api/overview') }
onMounted(() => { load(); timer = setInterval(load, 10000) })
onBeforeUnmount(() => clearInterval(timer))

const b = computed(() => system.budget)
const models = computed(() => (data.value?.models || []).map((m) => ({ ...m, rt: system.runtimes[m.id] || m.runtime })))
const pressure = computed(() => ({ normal: { c: 'good', t: '正常' }, warn: { c: 'hold', t: '偏高' }, critical: { c: 'crit', t: '嚴重' } })[system.host?.pressure] || { c: 'idle', t: '—' })
const metalClass = computed(() => { const r = b.value ? b.value.models_mb / b.value.metal_limit_mb : 0; return r > 0.92 ? 'crit' : r > 0.8 ? 'warn' : '' })
const active = computed(() => Object.values(system.runtimes).reduce((a, r) => a + (r.status === 'loaded' ? r.active : 0), 0))
const waiting = computed(() => Object.values(system.runtimes).reduce((a, r) => a + (r.status === 'loaded' ? r.waiting : 0), 0))
const avgTps = computed(() => { const c = Object.values(system.runtimes).filter((r) => r.status === 'loaded' && r.tps > 0); return c.length ? (c.reduce((a, r) => a + r.tps, 0) / c.length).toFixed(1) : '—' })
const today = computed(() => data.value?.today || { prompt_tokens: 0, completion_tokens: 0, requests: 0, errors: 0 })
const go = (m, action) => router.push({ path: '/models', query: { id: m.id, action } })
</script>

<template>
  <div class="page">
    <section class="card hero">
      <div class="hero-l">
        <div class="eyebrow">可再載入的模型記憶體</div>
        <div class="hero-num num">{{ b ? fmtGB(b.can_load_mb) : '—' }}<span>GB</span></div>
        <p class="t13 muted" style="margin: 0">已扣掉 {{ b ? fmtGB(b.headroom_mb) : '—' }} GB 安全餘裕。載入模型時，預估需要的記憶體超過這個數字就會被擋下。</p>
        <div class="hero-meta"><Pill :c="pressure.c" :t="'記憶體壓力 ' + pressure.t" /><span v-if="system.host" class="t13 muted num">Swap {{ fmtGB(system.host.swap_used_mb) }} GB</span></div>
      </div>
      <div v-if="b" class="hero-r">
        <div class="row-between"><span class="label">統一記憶體 {{ fmtGB(b.total_mb) }} GB</span><span class="t13 muted num">已用 {{ fmtGB(b.system_mb + b.models_mb) }} GB</span></div>
        <MemBar :budget="b" :runtimes="system.runtimes" />
        <div class="row-between" style="margin-top: 14px"><span class="label">模型佔用 / Metal 上限</span><span class="t13 num">{{ fmtGB(b.models_mb) }} / {{ fmtGB(b.metal_limit_mb) }} GB</span></div>
        <div class="meter" :class="metalClass"><i :style="{ width: pct(b.models_mb / b.metal_limit_mb) }"></i></div>
        <p class="t12 muted" style="margin: 0">Metal 上限是 GPU 能鎖定的記憶體（<code>iogpu.wired_limit_mb</code>），在系統設定調整。</p>
      </div>
      <div v-else class="hero-r loading-line">連線中…</div>
    </section>

    <section class="tiles">
      <div class="card tile"><div class="label">今日 Token</div><div class="tile-v num">{{ fmtTok(today.prompt_tokens + today.completion_tokens) }}</div><div class="t12 muted">輸入 {{ fmtTok(today.prompt_tokens) }} · 輸出 {{ fmtTok(today.completion_tokens) }}</div><Spark v-if="data" :values="data.spark" /><div class="t12 muted">近 14 天，今天到目前為止</div></div>
      <div class="card tile"><div class="label">今日請求</div><div class="tile-v num">{{ fmtInt(today.requests) }}</div><div class="t12 muted">錯誤 {{ today.errors }} 筆<span v-if="today.requests">（{{ ((today.errors / today.requests) * 100).toFixed(1) }}%）</span></div></div>
      <div class="card tile"><div class="label">處理中 / 排隊</div><div class="tile-v num">{{ active }}<small>/ {{ waiting }}</small></div><div class="t12 muted">每個模型一次處理一個生成請求，其餘排隊</div></div>
      <div class="card tile"><div class="label">平均輸出速度</div><div class="tile-v num">{{ avgTps }}<small>tok/s</small></div><div class="t12 muted">已載入的對話模型</div></div>
    </section>

    <section class="grid-2">
      <div class="card">
        <div class="card-h"><h2>模型</h2><RouterLink to="/models" class="btn btn-g btn-sm ml-auto">管理模型</RouterLink></div>
        <div v-for="m in models" :key="m.id" class="mstat">
          <span class="sw" :style="{ background: modelColor(m.id) }"></span>
          <div class="mstat-main"><span class="mono strong ell">{{ m.api_name }}</span><span class="caps"><span v-for="c in m.capabilities" :key="c" class="cap">{{ CAP[c] }}</span><span v-if="m.rt.fake && m.rt.status !== 'unloaded'" class="cap cap-demo">假 worker</span></span></div>
          <div class="mstat-num num t13">{{ m.rt.mem_mb ? fmtGB(m.rt.mem_mb) + ' GB' : '—' }}<div class="t12 muted">{{ m.rt.status === 'loaded' && m.rt.tps ? m.rt.tps + ' tok/s' : '' }}</div></div>
          <Pill :c="MS[m.rt.status].c" :t="MS[m.rt.status].t" />
          <button class="btn btn-s btn-xs" :disabled="!['loaded', 'unloaded', 'error'].includes(m.rt.status)" @click="go(m, m.rt.status === 'loaded' ? 'unload' : 'load')">{{ m.rt.status === 'loaded' ? '卸載' : '載入' }}</button>
        </div>
        <div v-if="data && !models.length" class="empty">還沒有登記模型。執行 <code>poetry run python seed_models.py</code>，或在模型頁新增。</div>
      </div>
      <div class="card">
        <div class="card-h"><h2>最近請求</h2><RouterLink to="/requests" class="btn btn-g btn-sm ml-auto">全部紀錄</RouterLink></div>
        <div class="scroll-x">
          <table class="tbl">
            <thead><tr><th>時間</th><th>會員</th><th>模型</th><th>端點</th><th>狀態</th><th class="r">Token</th><th class="r">總時間</th></tr></thead>
            <tbody>
              <tr v-for="r in data?.recent || []" :key="r.id"><td class="num muted">{{ fmtTime(r.created_at) }}</td><td>{{ r.user_name || '（未知金鑰）' }}</td><td class="mono t12">{{ r.model || '—' }}</td><td class="mono t12">{{ r.endpoint }}</td><td><Pill :c="stc(r.status_code)" :t="String(r.status_code)" /></td><td class="r">{{ r.status_code < 400 ? fmtInt(r.prompt_tokens + r.completion_tokens) : '—' }}</td><td class="r">{{ fmtDuration(r.duration_ms) }}</td></tr>
            </tbody>
          </table>
        </div>
        <div v-if="data && !data.recent.length" class="empty">還沒有請求。</div>
      </div>
    </section>
  </div>
</template>
