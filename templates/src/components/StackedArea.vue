<script setup>
// 記憶體組成堆疊面積圖（GB），滑過顯示十字線與明細
import { computed, ref } from 'vue'
import { fmtGB } from '../composables/format'

const props = defineProps({ labels: Array, series: Array, yMax: Number, height: { type: Number, default: 240 } })
const W = 760, L = 40, R = 8, T = 12, B = 26
const H = computed(() => props.height)
const hover = ref(-1)
const svg = ref(null)
const n = computed(() => props.labels.length)
const x = (i) => L + (W - L - R) * (n.value <= 1 ? 0 : i / (n.value - 1))
const y = (v) => T + (H.value - T - B) * (1 - v / props.yMax)
const ticks = computed(() => [0, 1, 2, 3, 4].map((k) => (k * props.yMax) / 4))
const bands = computed(() => {
  const acc = new Array(n.value).fill(0)
  return props.series.map((s) => {
    const lo = acc.slice()
    s.values.forEach((v, i) => { acc[i] += v })
    const top = acc.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`)
    const bot = lo.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).reverse()
    return { key: s.key, color: s.color, area: `M${top.join(' L')} L${bot.join(' L')} Z`, line: `M${top.join(' L')}` }
  })
})
const totals = computed(() => props.labels.map((_, i) => props.series.reduce((a, s) => a + s.values[i], 0)))
function onMove(e) {
  if (!n.value) return
  const r = svg.value.getBoundingClientRect()
  const px = ((e.clientX - r.left) / r.width) * W
  hover.value = Math.max(0, Math.min(n.value - 1, Math.round(((px - L) / (W - L - R)) * (n.value - 1))))
}
const every = computed(() => Math.max(1, Math.round(n.value / 4)))
const tipStyle = computed(() => (hover.value < 0 ? {} : { left: Math.max(16, Math.min(84, (x(hover.value) / W) * 100)) + '%', top: Math.max(30, (y(totals.value[hover.value]) / H.value) * 100) + '%' }))
</script>

<template>
  <div class="chart">
    <svg ref="svg" :viewBox="`0 0 ${W} ${H}`" role="img" aria-label="記憶體組成堆疊面積圖" @mousemove="onMove" @mouseleave="hover = -1">
      <g class="ax">
        <g v-for="t in ticks" :key="t"><line class="gridl" :x1="L" :x2="W - R" :y1="y(t)" :y2="y(t)" /><text :x="L - 8" :y="y(t) + 4" text-anchor="end">{{ fmtGB(t) }}</text></g>
        <line class="base" :x1="L" :x2="W - R" :y1="y(0)" :y2="y(0)" />
        <template v-for="(lab, i) in labels" :key="'x' + i"><text v-if="(n - 1 - i) % every === 0" :x="x(i)" :y="H - 7" text-anchor="middle">{{ lab }}</text></template>
      </g>
      <g v-for="b in bands" :key="b.key"><path :d="b.area" :style="{ fill: b.color, fillOpacity: 0.78 }" /><path :d="b.line" fill="none" :style="{ stroke: b.color }" stroke-width="2" stroke-linejoin="round" /></g>
      <g v-if="hover >= 0"><line class="xhair" :x1="x(hover)" :x2="x(hover)" :y1="T" :y2="H - B" /><circle :cx="x(hover)" :cy="y(totals[hover])" r="4" style="fill: var(--fg); stroke: var(--card)" stroke-width="2" /></g>
    </svg>
    <div v-if="hover >= 0" class="tip" :style="tipStyle">
      <div class="strong">{{ labels[hover] }}</div>
      <div v-for="s in series.slice().reverse()" :key="s.key" class="tip-row"><i :style="{ background: s.color }"></i><span>{{ s.name }}</span><b>{{ fmtGB(s.values[hover]) }} GB</b></div>
      <div class="tip-row tip-total"><span>合計</span><b>{{ fmtGB(totals[hover]) }} GB</b></div>
    </div>
  </div>
</template>
