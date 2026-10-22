<script setup>
// 會員自己的金鑰：建立（只顯示一次）、撤銷；範圍不能超過管理者給的上限
import { computed, onMounted, reactive, ref } from 'vue'
import Icon from '../../components/Icon.vue'
import KeyRows from '../../components/KeyRows.vue'
import KeyStatsPanel from '../../components/KeyStatsPanel.vue'
import SecretBox from '../../components/SecretBox.vue'
import { api } from '../../api/client'
import { toast } from '../../stores/toast'
import { addDays, fmtTok } from '../../composables/format'

const keys = ref([])
const summary = ref(null)
const newKey = ref(null)
const loadError = ref('')
const selId = ref(null)
const selected = computed(() => keys.value.find((k) => k.id === selId.value))
const kf = reactive({ open: false, name: '', expiry: 'none', date: addDays(90) })

async function load() {
  try {
    const [k, s] = await Promise.all([api('/api/me/keys'), api('/api/me/summary')])
    keys.value = k
    summary.value = s
    loadError.value = ''
    if (!k.some((x) => x.id === selId.value)) selId.value = (k.find((x) => !x.revoked_at) || k[0])?.id ?? null
  } catch (e) {
    loadError.value = e.message
  }
}
onMounted(load)
const active = computed(() => keys.value.filter((k) => !k.revoked_at))
const full = computed(() => summary.value && active.value.length >= summary.value.max_keys)
const canCreate = computed(() => kf.name.trim() && !full.value)

function open() {
  Object.assign(kf, { open: true, name: '', expiry: 'none', date: addDays(90) })
  newKey.value = null
}
async function create() {
  const expires_on = kf.expiry === 'none' ? null : kf.expiry === 'd30' ? addDays(30) : kf.expiry === 'd90' ? addDays(90) : kf.date
  try {
    const r = await api('/api/me/keys', { method: 'POST', body: { name: kf.name.trim(), expires_on } })
    newKey.value = { name: r.name, key: r.key }
    kf.open = false
    selId.value = r.id
    await load()
  } catch (e) { toast(e.message) }
}
async function revoke(k) {
  try {
    await api(`/api/me/keys/${k.id}`, { method: 'DELETE' })
    toast(`已撤銷「${k.name}」，這把金鑰立即失效`)
    await load()
  } catch (e) { toast(e.message) }
}
</script>

<template>
  <div v-if="summary" class="page split two">
    <section class="card col-card">
      <div class="d-head">
        <div><h2>我的 API Keys</h2><div class="t13 muted">{{ active.length }} / {{ summary.max_keys }} 把 · 本月共 {{ fmtTok(summary.month_used) }}{{ summary.monthly_token_quota ? ' / ' + fmtTok(summary.monthly_token_quota) : '' }} tokens</div></div>
        <button v-if="!kf.open" class="btn btn-p btn-sm" :disabled="full" @click="open"><Icon n="plus" :s="15" />建立 API Key</button>
      </div>
      <div class="scroll detail" style="margin-top: 12px">
      <div v-if="full && !kf.open" class="notice notice-warn">已經有 {{ summary.max_keys }} 把有效金鑰，達到上限。請先撤銷不用的金鑰，或請管理者調高上限。</div>
      <SecretBox v-if="newKey" :title="`已建立「${newKey.name}」`" hint="完整金鑰只會顯示這一次，管理者也看不到。請現在複製，貼到你的系統設定裡。" :value="newKey.key" @close="newKey = null" />
      <form v-if="kf.open" class="action-panel" @submit.prevent="create">
        <div class="ap-h"><strong>建立 API Key</strong><button type="button" class="ib" aria-label="關閉" @click="kf.open = false"><Icon n="x" :s="16" /></button></div>
        <div class="form-grid">
          <div class="field"><label for="mk-name">名稱</label><input id="mk-name" v-model="kf.name" class="input" placeholder="用在哪個系統，例如 Open WebUI" /></div>
          <div class="field"><label for="mk-exp">到期</label><select id="mk-exp" v-model="kf.expiry" class="input"><option value="none">不到期</option><option value="d30">30 天後</option><option value="d90">90 天後</option><option value="date">指定日期</option></select></div>
          <div v-if="kf.expiry === 'date'" class="field"><label for="mk-date">到期日</label><input id="mk-date" v-model="kf.date" type="date" class="input" /></div>
        </div>
        <div class="ap-actions"><button class="btn btn-p btn-sm" type="submit" :disabled="!canCreate">建立並顯示金鑰</button><button type="button" class="btn btn-s btn-sm" @click="kf.open = false">取消</button></div>
      </form>
      <KeyRows :keys="keys" mine clickable :selected-id="selId" @revoke="revoke" @open="selId = $event.id" />
      </div>
    </section>
    <KeyStatsPanel v-if="selected" :key="selected.id" :api-key="selected" />
    <section v-else class="card"><div class="empty">建立金鑰後，點選金鑰就會在這裡顯示它的用量統計。</div></section>
  </div>
  <div v-else-if="loadError" class="notice notice-crit">讀取金鑰失敗：{{ loadError }}</div>
  <div v-else class="loading-line">載入中…</div>
</template>
