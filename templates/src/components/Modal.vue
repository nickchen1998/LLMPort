<script setup>
// 畫面中央的對話框：點背景或按 Esc 關閉
import { onBeforeUnmount, onMounted } from 'vue'
import Icon from './Icon.vue'

defineProps({ title: String, width: { type: String, default: '520px' } })
const emit = defineEmits(['close'])
const onKey = (e) => { if (e.key === 'Escape') emit('close') }
onMounted(() => document.addEventListener('keydown', onKey))
onBeforeUnmount(() => document.removeEventListener('keydown', onKey))
</script>

<template>
  <Teleport to="body">
    <div class="modal-bg" @click.self="emit('close')">
      <div class="modal" role="dialog" aria-modal="true" :aria-label="title" :style="{ width: `min(${width}, 100%)` }">
        <div class="modal-h"><h2>{{ title }}</h2><button class="ib" aria-label="關閉" @click="emit('close')"><Icon n="x" :s="16" /></button></div>
        <div class="modal-b"><slot /></div>
      </div>
    </div>
  </Teleport>
</template>
