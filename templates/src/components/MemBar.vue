<script setup>
// 統一記憶體組成：macOS 與其他程式、各模型、未使用
import { computed } from 'vue'
import { fmtGB, modelColor } from '../composables/format'

const props = defineProps({ budget: Object, runtimes: Object })
const segs = computed(() => {
  const b = props.budget
  if (!b) return []
  const arr = [{ k: 'sys', name: 'macOS 與其他程式', v: b.system_mb, color: 'var(--sysmem)' }]
  for (const rt of Object.values(props.runtimes || {})) {
    if (['loading', 'loaded', 'unloading'].includes(rt.status) && rt.mem_mb > 0) {
      arr.push({ k: rt.model_id, name: rt.api_name + (rt.fake ? '（假）' : ''), v: rt.mem_mb, color: modelColor(rt.model_id), grow: rt.status !== 'loaded', mono: true })
    }
  }
  const used = arr.reduce((a, s) => a + s.v, 0)
  arr.push({ k: 'free', name: '未使用', v: Math.max(0, b.total_mb - used), free: true })
  return arr.map((s) => ({ ...s, w: (s.v / b.total_mb) * 100 }))
})
const aria = computed(() => '統一記憶體組成：' + segs.value.map((s) => `${s.name} ${fmtGB(s.v)} GB`).join('、'))
</script>

<template>
  <div class="membar" role="img" :aria-label="aria">
    <div v-for="s in segs" :key="s.k" class="mseg" :class="{ free: s.free, grow: s.grow }" :style="{ width: s.w + '%', background: s.free ? null : s.color }"></div>
  </div>
  <div class="legend">
    <span v-for="s in segs" :key="s.k" class="lg"><i :class="{ free: s.free }" :style="{ background: s.free ? null : s.color }"></i><span :class="{ mono: s.mono }">{{ s.name }}</span><b>{{ fmtGB(s.v) }} GB</b></span>
  </div>
</template>
