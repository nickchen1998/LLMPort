<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import Pill from '../../components/Pill.vue'
import Spark from '../../components/Spark.vue'
import StackedArea from '../../components/StackedArea.vue'
import { api } from '../../api/client'
import { useSystem } from '../../stores/system'
import { MS, fmtGB, modelColor } from '../../composables/format'

const system = useSystem()
const history = ref([])
const cpu = ref([])
const gpu = ref([])
let timer = null
async function loadHistory() { history.value = await api('/api/system/history') }
onMounted(() => { loadHistory(); timer = setInterval(loadHistory, 10000) })
onBeforeUnmount(() => clearInterval(timer))
watch(() => system.snap?.ts, () => {
  const h = system.host
  if (!h) return
  cpu.value = [...cpu.value, h.cpu_percent].slice(-30)
  if (h.gpu_percent != null) gpu.value = [...gpu.value, h.gpu_percent].slice(-30)
})

const names = computed(() => Object.fromEntries(Object.values(system.runtimes).map((r) => [r.model_id, r.api_name])))
const pad = (n) => String(n).padStart(2, '0')
const labels = computed(() => history.value.map((p) => { const d = new Date(p.ts * 1000); return `${pad(d.getHours())}:${pad(d.getMinutes())}` }))
const series = computed(() => {
  const ids = [...new Set(history.value.flatMap((p) => Object.keys(p.models).map(Number)))].sort((a, b) => a - b)
  return [{ key: 'sys', name: 'macOS 與其他程式', color: 'var(--sysmem)', values: history.value.map((p) => p.system_mb) }]
    .concat(ids.map((id) => ({ key: id, name: names.value[id] || `模型 ${id}`, color: modelColor(id), values: history.value.map((p) => p.models[id] || 0) })))
})
const pressure = computed(() => ({ normal: { c: 'good', t: '正常' }, warn: { c: 'hold', t: '偏高' }, critical: { c: 'crit', t: '嚴重' } })[system.host?.pressure] || { c: 'idle', t: '—' })
const tunnel = computed(() => ({ connected: { c: 'good', t: '已連線' }, down: { c: 'crit', t: '中斷' }, unknown: { c: 'idle', t: '未設定' } })[system.tunnel])
const workers = computed(() => Object.values(system.runtimes).sort((a, b) => a.model_id - b.model_id))
</script>

<template>
  <div class="page">
    <section class="tiles">
      <div class="card tile"><div class="label">CPU</div><div class="tile-v num">{{ system.host ? Math.round(system.host.cpu_percent) : '—' }}<small>%</small></div><Spark v-if="cpu.length > 1" :values="cpu" /><div class="t12 muted">psutil，每 2 秒</div></div>
      <div class="card tile"><div class="label">GPU</div><div class="tile-v num">{{ system.host?.gpu_percent ?? '—' }}<small v-if="system.host?.gpu_percent != null">%</small></div><Spark v-if="gpu.length > 1" :values="gpu" /><div class="t12 muted">{{ system.host?.gpu_percent == null ? '安裝 macmon 後才有（brew install macmon）' : 'macmon（不需要 sudo）' }}</div></div>
      <div class="card tile"><div class="label">記憶體壓力</div><div class="tile-v"><Pill :c="pressure.c" :t="pressure.t" /></div><div v-if="system.budget" class="t12 muted num">可用 {{ fmtGB(system.budget.available_mb) }} GB · Swap {{ fmtGB(system.host.swap_used_mb) }} GB</div></div>
      <div class="card tile"><div class="label">Cloudflare Tunnel</div><div class="tile-v"><Pill :c="tunnel.c" :t="tunnel.t" /></div><div class="t12 muted">{{ system.tunnel === 'unknown' ? '設定 CLOUDFLARED_METRICS_URL 後才會檢查' : 'cloudflared metrics 的 /ready' }}</div></div>
    </section>
    <section class="card">
      <div class="card-h"><h2>統一記憶體組成</h2><span class="t13 muted">近 15 分鐘，每 10 秒一點，單位 GB</span></div>
      <template v-if="history.length > 1 && system.budget">
        <div class="legend" style="margin-bottom: 8px"><span v-for="s in series" :key="s.key" class="lg"><i :style="{ background: s.color }"></i><span :class="{ mono: s.key !== 'sys' }">{{ s.name }}</span><b>{{ fmtGB(s.values[s.values.length - 1]) }} GB</b></span></div>
        <StackedArea :labels="labels" :series="series" :y-max="system.budget.total_mb" />
      </template>
      <div v-else class="empty">剛啟動，累積幾個取樣點之後就會出現圖表。</div>
    </section>
    <section class="grid-2">
      <div class="card">
        <div class="card-h"><h2>模型 worker</h2></div>
        <div class="scroll-x"><table class="tbl"><thead><tr><th>模型</th><th>狀態</th><th class="r">處理中</th><th class="r">排隊</th><th class="r">速度</th><th class="r">記憶體</th></tr></thead>
          <tbody><tr v-for="r in workers" :key="r.model_id"><td class="mono t12"><span class="sw" :style="{ background: modelColor(r.model_id), marginRight: '6px' }"></span>{{ r.api_name || r.model_id }}</td><td><Pill :c="MS[r.status].c" :t="MS[r.status].t" /></td><td class="r">{{ r.status === 'loaded' ? r.active : '—' }}</td><td class="r">{{ r.status === 'loaded' ? r.waiting : '—' }}</td><td class="r">{{ r.tps ? r.tps + ' tok/s' : '—' }}</td><td class="r">{{ r.mem_mb ? fmtGB(r.mem_mb) + ' GB' : '—' }}</td></tr></tbody></table></div>
        <div v-if="!workers.length" class="empty">還沒有載入過任何模型。</div>
      </div>
      <div class="card">
        <div class="card-h"><h2>服務</h2></div>
        <div class="mstat" style="grid-template-columns: minmax(0, 1fr) auto"><div class="mstat-main"><span class="strong">FastAPI（uvicorn）</span><span class="t12 muted">即時推播 {{ system.connected ? '連線中' : '中斷' }}</span></div><Pill :c="system.connected ? 'good' : 'crit'" :t="system.connected ? '正常' : '中斷'" /></div>
        <div class="mstat" style="grid-template-columns: minmax(0, 1fr) auto"><div class="mstat-main"><span class="strong">cloudflared</span><span class="t12 muted">對外連線</span></div><Pill :c="tunnel.c" :t="tunnel.t" /></div>
        <div v-for="r in workers" :key="r.model_id" class="mstat" style="grid-template-columns: minmax(0, 1fr) auto"><div class="mstat-main"><span class="strong mono" style="font-size: 12.5px">worker · {{ r.api_name }}</span><span class="t12 muted">{{ r.pid ? `127.0.0.1:${r.port} · PID ${r.pid}${r.fake ? ' · 假 worker' : ''}` : '沒有執行' }}</span></div><Pill :c="MS[r.status].c" :t="MS[r.status].t" /></div>
      </div>
    </section>
  </div>
</template>
