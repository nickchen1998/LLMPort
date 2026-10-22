<script setup>
// 金鑰清單（會員自己與管理者共用），撤銷要再按一次確認
import { computed, ref } from 'vue'
import { fmtTok, relTime } from '../composables/format'

const props = defineProps({ keys: Array, mine: Boolean, clickable: Boolean, selectedId: Number })
const emit = defineEmits(['revoke', 'open'])
const confirming = ref(null)
const active = computed(() => props.keys.filter((k) => !k.revoked_at))
const revoked = computed(() => props.keys.filter((k) => k.revoked_at))
function revoke(k) {
  confirming.value = null
  emit('revoke', k)
}
</script>

<template>
  <div class="keys">
    <div v-for="k in active" :key="k.id" class="keyrow" :class="{ click: clickable, on: clickable && k.id === selectedId }" :role="clickable ? 'button' : null" :tabindex="clickable ? 0 : null" @click="clickable && emit('open', k)" @keydown.enter="clickable && emit('open', k)">
      <div class="keyrow-main">
        <span class="strong">{{ k.name }} <span v-if="k.expired" class="cap cap-demo">已過期</span></span>
        <span class="mono t13">{{ k.masked }}</span>
        <span class="t12 muted">{{ k.expires_at ? k.expires_at + ' 到期' : '永不到期' }} · {{ k.last_used_at ? '最後使用 ' + relTime(k.last_used_at) : '尚未使用' }}</span>
        <span class="t12 muted">建立於 {{ k.created_at.slice(0, 10) }} · 本月 {{ fmtTok(k.month_tokens) }} tokens</span>
      </div>
      <div class="keyrow-side" @click.stop>
        <div v-if="confirming === k.id" class="confirm"><span class="t12">撤銷後立即失效，不能復原。</span><button class="btn btn-dp btn-xs" @click="revoke(k)">確認撤銷</button><button class="btn btn-s btn-xs" @click="confirming = null">取消</button></div>
        <button v-else class="btn btn-d btn-xs" @click="confirming = k.id">撤銷</button>
      </div>
    </div>
    <div v-if="!active.length" class="empty">{{ mine ? '你還沒有金鑰。按「建立 API Key」，替每個要串接的系統各建一把。' : '這位會員還沒有建立金鑰。' }}</div>
    <details v-if="revoked.length" class="revoked-list">
      <summary>已撤銷 {{ revoked.length }} 把</summary>
      <div class="keys">
        <div v-for="k in revoked" :key="k.id" class="keyrow revoked" :class="{ click: clickable, on: clickable && k.id === selectedId }" @click="clickable && emit('open', k)"><div class="keyrow-main"><span class="strong">{{ k.name }}</span><span class="mono t13">{{ k.masked }}</span></div><span class="t12 muted">撤銷於 {{ k.revoked_at.slice(0, 10) }}</span></div>
      </div>
    </details>
  </div>
</template>
