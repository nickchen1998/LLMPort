<script setup>
// 只顯示一次的完整金鑰或初始密碼
import { ref } from 'vue'
import Icon from './Icon.vue'
import { copyText } from '../composables/format'
import { toast } from '../stores/toast'

const props = defineProps({ title: String, hint: String, value: String, done: { type: String, default: '我已保存' } })
const emit = defineEmits(['close'])
const el = ref(null)
async function copy() {
  toast((await copyText(props.value, el.value)) ? '已複製到剪貼簿' : '已選取文字，請按 ⌘C 複製')
}
</script>

<template>
  <div class="newkey">
    <div class="strong">{{ title }}</div>
    <p class="t13" style="margin: 0">{{ hint }}</p>
    <div class="keybox"><code ref="el" class="mono">{{ value }}</code><button class="btn btn-s btn-sm" @click="copy"><Icon n="copy" :s="15" />複製</button></div>
    <div class="ap-actions"><button class="btn btn-g btn-sm" @click="emit('close')">{{ done }}</button><slot /></div>
  </div>
</template>
