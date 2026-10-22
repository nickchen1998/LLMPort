<script setup>
// 載入前的預估：目前已載入的模型＋這個模型，對照 Metal 上限
import { computed } from 'vue'
import { fmtGB, modelColor } from '../composables/format'

const props = defineProps({ modelId: Number, need: Number, budget: Object, runtimes: Object })
const scale = computed(() => Math.max(props.budget.metal_limit_mb, props.budget.models_mb + props.need) * 1.04)
const segs = computed(() => Object.values(props.runtimes || {})
  .filter((rt) => ['loading', 'loaded', 'unloading'].includes(rt.status) && rt.model_id !== props.modelId && rt.mem_mb > 0)
  .map((rt) => ({ k: rt.model_id, w: (rt.mem_mb / scale.value) * 100, color: modelColor(rt.model_id) })))
const newW = computed(() => (props.need / scale.value) * 100)
const limitLeft = computed(() => (props.budget.metal_limit_mb / scale.value) * 100)
</script>

<template>
  <div class="proj-wrap">
    <div class="projbar" role="img" aria-label="載入後的模型記憶體預估">
      <div v-for="s in segs" :key="s.k" class="pb" :style="{ width: s.w + '%', background: s.color }"></div>
      <div class="pb pb-new" :style="{ width: newW + '%', background: modelColor(modelId) }"></div>
      <div class="pb-free"></div>
    </div>
    <div class="proj-limit" :style="{ left: limitLeft + '%' }"><span>Metal 上限 {{ fmtGB(budget.metal_limit_mb) }} GB</span></div>
  </div>
</template>
