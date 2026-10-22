<script setup>
import { computed } from 'vue'

const props = defineProps({ values: { type: Array, default: () => [] }, w: { type: Number, default: 132 }, h: { type: Number, default: 30 } })
const pts = computed(() => {
  const v = props.values.length > 1 ? props.values : [0, 0]
  const mx = Math.max(...v)
  const mn = Math.min(...v)
  return v.map((x, i) => [3 + (i * (props.w - 6)) / (v.length - 1), props.h - 4 - ((x - mn) / (mx - mn || 1)) * (props.h - 8)])
})
</script>

<template>
  <svg class="spark" :viewBox="`0 0 ${w} ${h}`" :width="w" :height="h" aria-hidden="true">
    <polyline :points="pts.map((p) => p.join(',')).join(' ')" class="spark-l" />
    <circle :cx="pts[pts.length - 1][0]" :cy="pts[pts.length - 1][1]" r="3.5" class="spark-d" />
  </svg>
</template>
