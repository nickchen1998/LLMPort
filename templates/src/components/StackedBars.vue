<script setup>
// 每日 token 堆疊長條圖：2px 間隔、頂端圓角、滑過顯示明細
import { computed, ref } from 'vue'
import { fmtTok } from '../composables/format'

const props = defineProps({ labels: Array, series: Array, height: { type: Number, default: 250 } })
const W = 760, L = 50, R = 8, T = 14, B = 26
const H = computed(() => props.height)
const hover = ref(-1)
const n = computed(() => props.labels.length || 1)
const totals = computed(() => props.labels.map((_, i) => props.series.reduce((a, s) => a + (s.values[i] || 0), 0)))
function niceStep(x) { const p = Math.pow(10, Math.floor(Math.log10(x))); const f = x / p; return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 2.5 ? 2.5 : f <= 5 ? 5 : 10) * p }
const step4 = computed(() => niceStep(Math.max(4, ...totals.value) / 4))
const max = computed(() => step4.value * 4)
const ticks = computed(() => [0, 1, 2, 3, 4].map((k) => k * step4.value))
const step = computed(() => (W - L - R) / n.value)
const bw = computed(() => Math.min(24, step.value * 0.62))
const cx = (i) => L + step.value * i + step.value / 2
const y = (v) => T + (H.value - T - B) * (1 - v / max.value)
const xEvery = computed(() => (n.value > 20 ? 5 : n.value > 10 ? 2 : 1))
const rect = (x, yy, w, h) => `M${x},${yy}h${w}v${h}h${-w}z`
const roundTop = (x, yy, w, h, r) => { r = Math.min(r, h, w / 2); return `M${x},${yy + h}V${yy + r}Q${x},${yy} ${x + r},${yy}H${x + w - r}Q${x + w},${yy} ${x + w},${yy + r}V${yy + h}Z` }
const bars = computed(() => props.labels.map((_, i) => {
  let acc = 0
  const vis = props.series.filter((s) => (s.values[i] || 0) > 0)
  const segs = vis.map((s, j) => {
    const v = s.values[i]
    const y0 = y(acc), y1 = y(acc + v)
    acc += v
    const top = j === vis.length - 1
    const yy = top ? y1 : Math.min(y0, y1 + 2)
    const h = Math.max(0, y0 - yy)
    const x = cx(i) - bw.value / 2
    return { k: s.key, color: s.color, d: top ? roundTop(x, yy, bw.value, h, 4) : rect(x, yy, bw.value, h) }
  })
  return { i, segs }
}))
const tipStyle = computed(() => {
  const i = hover.value
  if (i < 0) return {}
  return { left: Math.max(14, Math.min(86, (cx(i) / W) * 100)) + '%', top: Math.max(18, (y(totals.value[i]) / H.value) * 100) + '%' }
})
</script>

<template>
  <div class="chart">
    <svg :viewBox="`0 0 ${W} ${H}`" role="img" :aria-label="`每日 Token 堆疊長條圖，共 ${labels.length} 天`" @mouseleave="hover = -1">
      <g class="ax">
        <g v-for="t in ticks" :key="t"><line class="gridl" :x1="L" :x2="W - R" :y1="y(t)" :y2="y(t)" /><text :x="L - 8" :y="y(t) + 4" text-anchor="end">{{ fmtTok(t) }}</text></g>
        <line class="base" :x1="L" :x2="W - R" :y1="y(0)" :y2="y(0)" />
        <template v-for="(lab, i) in labels" :key="'x' + i"><text v-if="(labels.length - 1 - i) % xEvery === 0" :x="cx(i)" :y="H - 7" text-anchor="middle">{{ lab }}</text></template>
      </g>
      <g v-for="b in bars" :key="b.i" :style="{ opacity: hover < 0 || hover === b.i ? 1 : 0.4 }"><path v-for="s in b.segs" :key="s.k" :d="s.d" :style="{ fill: s.color }" /></g>
      <rect v-for="(lab, i) in labels" :key="'h' + i" :x="cx(i) - step / 2" :y="T" :width="step" :height="H - T - B" fill="transparent" @mouseenter="hover = i" @click="hover = i" />
    </svg>
    <div v-if="hover >= 0" class="tip" :style="tipStyle">
      <div class="strong">{{ labels[hover] }}</div>
      <div v-for="s in series" :key="s.key" class="tip-row"><i :style="{ background: s.color }"></i><span class="mono">{{ s.name }}</span><b>{{ fmtTok(s.values[hover] || 0) }}</b></div>
      <div class="tip-row tip-total"><span>合計</span><b>{{ fmtTok(totals[hover]) }}</b></div>
    </div>
  </div>
</template>
