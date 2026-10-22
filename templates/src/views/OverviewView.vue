<script setup>
// 總覽（每個帳號都看自己的）：系統現在有哪些模型可以用、本月用量趨勢
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import Pill from '../components/Pill.vue'
import StackedBars from '../components/StackedBars.vue'
import { api } from '../api/client'
import { CAP, dayLabel, fmtInt, fmtTok, modelColor, pct } from '../composables/format'

const summary = ref(null)
const usage = ref(null)
const error = ref('')
let timer = null

async function load() {
  try {
    const days = new Date().getDate()
    const [s, u] = await Promise.all([api('/api/me/summary'), api(`/api/me/usage?days=${days}`)])
    summary.value = s
    usage.value = u
    error.value = ''
  } catch (e) {
    error.value = e.message
  }
}
onMounted(() => { load(); timer = setInterval(load, 15000) })
onBeforeUnmount(() => clearInterval(timer))

const models = computed(() => [...(summary.value?.models || [])].sort((a, b) => Number(b.available) - Number(a.available) || a.id - b.id))
const availableCount = computed(() => models.value.filter((m) => m.available).length)
const ratio = computed(() => (summary.value?.monthly_token_quota ? summary.value.month_used / summary.value.monthly_token_quota : 0))
const labels = computed(() => (usage.value?.dates || []).map(dayLabel))
const series = computed(() => (usage.value?.series || []).map((s) => ({ key: s.model_id, name: s.name, color: modelColor(s.model_id), values: s.prompt.map((p, i) => p + s.completion[i]) })))
const totals = computed(() => usage.value?.totals || { prompt_tokens: 0, completion_tokens: 0, requests: 0, errors: 0 })
const monthLabel = `${new Date().getMonth() + 1} 月`
</script>

<template>
  <div v-if="summary && usage" class="page fill">
    <section class="tiles tiles-3">
      <div class="card tile">
        <div class="label">本月用量</div>
        <div class="tile-v num">{{ fmtTok(summary.month_used) }}<small>/ {{ summary.monthly_token_quota ? fmtTok(summary.monthly_token_quota) : '不限' }}</small></div>
        <div v-if="summary.monthly_token_quota" class="meter" :class="ratio > 0.9 ? 'crit' : ratio > 0.75 ? 'warn' : ''" style="margin-top: 6px"><i :style="{ width: pct(ratio) }"></i></div>
        <div v-else class="t12 muted">所有金鑰合計，每月 1 日歸零</div>
      </div>
      <div class="card tile"><div class="label">今日 Token</div><div class="tile-v num">{{ fmtTok(summary.today.prompt_tokens + summary.today.completion_tokens) }}</div><div class="t12 muted">輸入 {{ fmtTok(summary.today.prompt_tokens) }} · 輸出 {{ fmtTok(summary.today.completion_tokens) }}</div></div>
      <div class="card tile"><div class="label">本月請求</div><div class="tile-v num">{{ fmtInt(totals.requests) }}</div><div class="t12 muted">其中錯誤 {{ fmtInt(totals.errors) }} 筆</div></div>
    </section>

    <div class="split two grow">
      <section class="card col-card">
        <div class="card-h"><h2>系統模型</h2><span class="t13 muted">{{ availableCount }} 個可以使用</span></div>
        <div class="scroll">
          <div v-for="x in models" :key="x.id" class="mstat" style="grid-template-columns: auto minmax(0, 1fr) auto">
            <span class="sw" :style="{ background: modelColor(x.id) }"></span>
            <div class="mstat-main">
              <span class="mono strong ell">{{ x.api_name }}</span>
              <span class="caps"><span v-for="c in x.capabilities" :key="c" class="cap">{{ CAP[c] }}</span></span>
              <span class="t12 muted">{{ x.available ? x.display_name : '目前沒有載入，現在呼叫會回 503' }}</span>
            </div>
            <Pill :c="x.available ? 'good' : 'idle'" :t="x.available ? '可以使用' : '暫停中'" />
          </div>
          <div v-if="!models.length" class="empty">系統還沒有登記任何模型。</div>
        </div>
      </section>

      <section class="card col-card">
        <div class="card-h"><h2>{{ monthLabel }}用量趨勢</h2><span class="t13 muted">每日 Token，依模型</span></div>
        <template v-if="series.length">
          <div class="legend" style="margin-bottom: 8px"><span v-for="s in series" :key="s.key" class="lg"><i :style="{ background: s.color }"></i><span class="mono">{{ s.name }}</span></span></div>
          <StackedBars class="grow" fill :labels="labels" :series="series" />
        </template>
        <div v-else class="empty">這個月還沒有用量。到「金鑰管理」建立金鑰，或用「請求測試」試打一次。</div>
      </section>
    </div>
  </div>
  <div v-else-if="error" class="notice notice-crit">讀取總覽失敗：{{ error }}</div>
  <div v-else class="loading-line">載入中…</div>
</template>
