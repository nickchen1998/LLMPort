<script setup>
// 會員自己的金鑰：建立（只顯示一次）、撤銷；範圍不能超過管理者給的上限
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import Icon from '../../components/Icon.vue'
import KeyRows from '../../components/KeyRows.vue'
import SecretBox from '../../components/SecretBox.vue'
import { api } from '../../api/client'
import { toast } from '../../stores/toast'
import { addDays } from '../../composables/format'

const router = useRouter()
const keys = ref([])
const summary = ref(null)
const newKey = ref(null)
const kf = reactive({ open: false, name: '', scope: 'all', model_ids: [], rpm: '', expiry: 'none', date: addDays(90) })

async function load() {
  const [k, s] = await Promise.all([api('/api/me/keys'), api('/api/me/summary')])
  keys.value = k
  summary.value = s
}
onMounted(load)
const active = computed(() => keys.value.filter((k) => !k.revoked_at))
const full = computed(() => summary.value && active.value.length >= summary.value.max_keys)
const rpmErr = computed(() => (kf.rpm !== '' && summary.value && Number(kf.rpm) > summary.value.rpm_limit ? `最多 ${summary.value.rpm_limit} 次，這是管理者給你的上限` : ''))
const canCreate = computed(() => kf.name.trim() && !rpmErr.value && !full.value && (kf.scope === 'all' || kf.model_ids.length))

function open() {
  Object.assign(kf, { open: true, name: '', scope: 'all', model_ids: summary.value.models.map((m) => m.id), rpm: '', expiry: 'none', date: addDays(90) })
  newKey.value = null
}
async function create() {
  const expires_on = kf.expiry === 'none' ? null : kf.expiry === 'd30' ? addDays(30) : kf.expiry === 'd90' ? addDays(90) : kf.date
  try {
    const r = await api('/api/me/keys', { method: 'POST', body: { name: kf.name.trim(), model_ids: kf.scope === 'custom' ? kf.model_ids : null, rpm_limit: kf.rpm !== '' ? Number(kf.rpm) : null, expires_on } })
    newKey.value = { name: r.name, key: r.key }
    kf.open = false
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
  <div v-if="summary" class="page" style="max-width: 1000px">
    <section class="card detail">
      <div class="d-head">
        <div><h2>我的 API Keys</h2><div class="t13 muted">{{ active.length }} / {{ summary.max_keys }} 把 · 每個要串接的系統各用一把，外洩時只要撤銷那一把</div></div>
        <button v-if="!kf.open" class="btn btn-p btn-sm" :disabled="full" @click="open"><Icon n="plus" :s="15" />建立 API Key</button>
      </div>
      <div v-if="full && !kf.open" class="notice notice-warn">已經有 {{ summary.max_keys }} 把有效金鑰，達到上限。請先撤銷不用的金鑰，或請管理者調高上限。</div>
      <SecretBox v-if="newKey" :title="`已建立「${newKey.name}」`" hint="完整金鑰只會顯示這一次，管理者也看不到。請現在複製，貼到你的系統設定裡。" :value="newKey.key" @close="newKey = null">
        <button class="btn btn-g btn-sm" @click="router.push('/quickstart')">看串接說明</button>
      </SecretBox>
      <form v-if="kf.open" class="action-panel" @submit.prevent="create">
        <div class="ap-h"><strong>建立 API Key</strong><button type="button" class="ib" aria-label="關閉" @click="kf.open = false"><Icon n="x" :s="16" /></button></div>
        <div class="form-grid">
          <div class="field"><label for="mk-name">名稱</label><input id="mk-name" v-model="kf.name" class="input" placeholder="用在哪個系統，例如 Open WebUI" /></div>
          <div class="field"><label for="mk-rpm">每分鐘請求數</label><input id="mk-rpm" v-model="kf.rpm" type="number" class="input num" min="1" :max="summary.rpm_limit" :placeholder="'不填就是上限 ' + summary.rpm_limit" /><span v-if="rpmErr" class="hint" style="color: var(--crit-text)">{{ rpmErr }}</span></div>
          <div class="field full"><span class="flabel">可用模型</span>
            <div class="checks-inline"><label><input id="mk-scope-a" v-model="kf.scope" type="radio" value="all" />我可用的全部模型</label><label><input id="mk-scope-c" v-model="kf.scope" type="radio" value="custom" />只限部分模型</label></div>
            <div v-if="kf.scope === 'custom'" class="checks-inline"><label v-for="x in summary.models" :key="x.id"><input :id="'mk-m-' + x.id" v-model="kf.model_ids" type="checkbox" :value="x.id" /><span class="mono t13">{{ x.api_name }}</span></label></div>
            <span class="hint">只開放這個系統需要的模型，金鑰外洩時影響比較小。</span></div>
          <div class="field"><label for="mk-exp">到期</label><select id="mk-exp" v-model="kf.expiry" class="input"><option value="none">不到期</option><option value="d30">30 天後</option><option value="d90">90 天後</option><option value="date">指定日期</option></select></div>
          <div v-if="kf.expiry === 'date'" class="field"><label for="mk-date">到期日</label><input id="mk-date" v-model="kf.date" type="date" class="input" /></div>
        </div>
        <div class="ap-actions"><button class="btn btn-p btn-sm" type="submit" :disabled="!canCreate">建立並顯示金鑰</button><button type="button" class="btn btn-s btn-sm" @click="kf.open = false">取消</button></div>
      </form>
      <KeyRows :keys="keys" mine @revoke="revoke" />
    </section>
  </div>
  <div v-else class="loading-line">載入中…</div>
</template>
