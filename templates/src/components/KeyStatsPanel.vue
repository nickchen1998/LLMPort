<script setup>
// 單一金鑰的資訊與用量統計（金鑰管理右側）
import { computed, onMounted, ref, watch } from 'vue'
import Pill from './Pill.vue'
import StackedBars from './StackedBars.vue'
import { api } from '../api/client'
import { dayLabel, fmtDuration, fmtInt, fmtTime, fmtTok, modelColor, relTime, stc } from '../composables/format'

const props = defineProps({ apiKey: Object })
const days = ref(14)
const usage = ref(null)
const requests = ref([])

async function load() {
  const id = props.apiKey.id
  const [u, r] = await Promise.all([api(`/api/me/usage?days=${days.value}&api_key_id=${id}`), api(`/api/me/requests?api_key_id=${id}&limit=10`)])
  usage.value = u
  requests.value = r
}
onMounted(load)
watch(days, load)

const labels = computed(() => (usage.value?.dates || []).map(dayLabel))
const series = computed(() => (usage.value?.series || []).map((s) => ({ key: s.model_id, name: s.name, color: modelColor(s.model_id), values: s.prompt.map((p, i) => p + s.completion[i]) })))
const totals = computed(() => usage.value?.totals || { prompt_tokens: 0, completion_tokens: 0, requests: 0, errors: 0 })
const k = computed(() => props.apiKey)
</script>

<template>
  <section class="card detail scroll-y">
      <div class="d-head"><div style="min-width: 0"><h2 class="ell">{{ k.name }}</h2><div class="t13 muted mono">{{ k.masked }}</div></div></div>
      <dl class="kv">
        <div><dt>狀態</dt><dd><Pill :c="k.revoked_at ? 'idle' : k.expired ? 'hold' : 'good'" :t="k.revoked_at ? '已撤銷' : k.expired ? '已過期' : '可以使用'" /></dd></div>
        <div><dt>建立 / 到期</dt><dd class="t13">{{ k.created_at.slice(0, 10) }} / {{ k.expires_at || '不到期' }}</dd></div>
        <div><dt>最後使用</dt><dd class="t13">{{ relTime(k.last_used_at) }}</dd></div>
      </dl>

      <div class="row-between" style="align-items: center">
        <span class="strong">用量</span>
        <div class="seg" role="group" aria-label="期間"><button v-for="p in [7, 14, 30, 90]" :key="p" :class="{ on: days === p }" @click="days = p">近 {{ p }} 天</button></div>
      </div>
      <div class="tiles" style="grid-template-columns: repeat(2, minmax(0, 1fr))">
        <div class="card tile"><div class="label">Token 合計</div><div class="tile-v num">{{ fmtTok(totals.prompt_tokens + totals.completion_tokens) }}</div></div>
        <div class="card tile"><div class="label">輸入 / 輸出</div><div class="tile-v num" style="font-size: 21.5px">{{ fmtTok(totals.prompt_tokens) }} <small>/ {{ fmtTok(totals.completion_tokens) }}</small></div></div>
        <div class="card tile"><div class="label">請求數</div><div class="tile-v num">{{ fmtInt(totals.requests) }}</div></div>
        <div class="card tile"><div class="label">錯誤</div><div class="tile-v num">{{ fmtInt(totals.errors) }}</div></div>
      </div>
      <template v-if="series.length">
        <div class="legend"><span v-for="s in series" :key="s.key" class="lg"><i :style="{ background: s.color }"></i><span class="mono">{{ s.name }}</span></span></div>
        <StackedBars :labels="labels" :series="series" :height="200" />
      </template>
      <div v-else-if="usage" class="empty">這段期間沒有用量。</div>

      <div class="strong">最近請求</div>
      <div class="scroll-x"><table class="tbl"><thead><tr><th>時間</th><th>模型</th><th>端點</th><th>狀態</th><th class="r">Token</th><th class="r">總時間</th></tr></thead>
        <tbody><tr v-for="r in requests" :key="r.id"><td class="num muted">{{ fmtTime(r.created_at) }}</td><td class="mono t12">{{ r.model || '—' }}</td><td class="mono t12">{{ r.endpoint }}</td><td><Pill :c="stc(r.status_code)" :t="String(r.status_code)" /></td><td class="r">{{ r.status_code < 400 ? fmtInt(r.prompt_tokens + r.completion_tokens) : '—' }}</td><td class="r">{{ fmtDuration(r.duration_ms) }}</td></tr></tbody></table></div>
      <div v-if="!requests.length" class="empty">這把金鑰還沒有請求。</div>
  </section>
</template>
