<script setup>
// 會員帳號：建立（產生初始密碼）、上限、重設密碼、停用；金鑰只能看與撤銷
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import Icon from '../../components/Icon.vue'
import KeyRows from '../../components/KeyRows.vue'
import Pill from '../../components/Pill.vue'
import SecretBox from '../../components/SecretBox.vue'
import StackedBars from '../../components/StackedBars.vue'
import { api } from '../../api/client'
import { toast } from '../../stores/toast'
import { MS, dayLabel, fmtInt, fmtTime, fmtTok, modelColor, pct } from '../../composables/format'

const route = useRoute()
const router = useRouter()
const members = ref([])
const q = ref('')
const selId = ref(Number(route.query.id) || null)
const tab = ref('profile')
const creating = ref(false)
const secret = ref(null)
const keys = ref([])
const usage = ref(null)

async function loadList() {
  members.value = await api('/api/members')
  if (!selId.value && members.value.length) selId.value = members.value[0].id
}
onMounted(async () => {
  await loadList()
})
const list = computed(() => members.value.filter((x) => !q.value || [x.name, x.email, x.note || ''].some((s) => s.includes(q.value))))
const m = computed(() => members.value.find((x) => x.id === selId.value))
const ratio = (x) => (x.monthly_token_quota ? x.month_used / x.monthly_token_quota : 0)
const quotaClass = (x) => (ratio(x) > 0.9 ? 'crit' : ratio(x) > 0.75 ? 'warn' : '')

const draft = reactive({})
const snap = (x) => ({ name: x.name, email: x.email, note: x.note || '', is_active: x.is_active, quota_m: x.monthly_token_quota / 1e6, max_keys: x.max_keys })
function reset() { if (m.value) Object.assign(draft, snap(m.value)) }
const changed = (k) => m.value && String(draft[k]) !== String(snap(m.value)[k])
const dirty = computed(() => m.value && ['name', 'email', 'note', 'is_active', 'quota_m', 'max_keys'].some(changed))

async function loadDetail() {
  if (!selId.value) return
  reset()
  const [k, u] = await Promise.all([api(`/api/members/${selId.value}/keys`), api(`/api/members/${selId.value}/usage?days=14`)])
  keys.value = k
  usage.value = u
}
watch(selId, () => { tab.value = 'profile'; secret.value = null; loadDetail() })
watch(() => members.value.length, (n) => n && loadDetail())

function pick(x) { creating.value = false; selId.value = x.id; router.replace({ query: { id: x.id } }) }

async function save() {
  try {
    const body = { name: draft.name, email: draft.email, note: draft.note, is_active: draft.is_active, monthly_token_quota: Math.round(Number(draft.quota_m) * 1e6), max_keys: Number(draft.max_keys) }
    const saved = await api(`/api/members/${m.value.id}`, { method: 'PATCH', body })
    members.value = members.value.map((x) => (x.id === saved.id ? saved : x))
    reset()
    toast(`已儲存「${saved.name}」`)
  } catch (e) { toast(e.message) }
}
async function resetPassword() {
  try {
    const r = await api(`/api/members/${m.value.id}/reset-password`, { method: 'POST' })
    secret.value = { title: '已重設密碼', hint: `把這組臨時密碼交給 ${m.value.email}。它只顯示這一次，會員登入後必須修改。`, value: r.password }
  } catch (e) { toast(e.message) }
}
async function revoke(k) {
  try {
    await api(`/api/keys/${k.id}`, { method: 'DELETE' })
    toast(`已撤銷「${k.name}」，這把金鑰立即失效`)
    keys.value = await api(`/api/members/${selId.value}/keys`)
    await loadList()
  } catch (e) { toast(e.message) }
}

const nf = reactive({})
function startCreate() { Object.assign(nf, { name: '', email: '', note: '', quota_m: 5, max_keys: 10 }); creating.value = true }
const nfErr = computed(() => (!nf.name?.trim() ? '請填名稱' : !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(nf.email || '') ? '請填正確的 Email' : ''))
async function create() {
  if (nfErr.value) return
  try {
    const r = await api('/api/members', { method: 'POST', body: { name: nf.name.trim(), email: nf.email.trim(), note: nf.note, monthly_token_quota: Math.round(Number(nf.quota_m) * 1e6), max_keys: Number(nf.max_keys) } })
    await loadList()
    creating.value = false
    selId.value = r.member.id
    setTimeout(() => { secret.value = { title: '已建立會員帳號', hint: `把這組初始密碼交給 ${r.member.email}。它只顯示這一次，會員第一次登入必須修改。`, value: r.initial_password } }, 0)
  } catch (e) { toast(e.message) }
}

const chart = computed(() => {
  if (!usage.value) return null
  return { labels: usage.value.dates.map(dayLabel), series: usage.value.series.map((s) => ({ key: s.model_id, name: s.name, color: modelColor(s.model_id), values: s.prompt.map((p, i) => p + s.completion[i]) })) }
})
</script>

<template>
  <div class="page split two">
    <section class="card col-card">
      <div class="card-h"><h2>會員</h2><span class="t13 muted">{{ members.length }} 位 · 登入後自己管理 API Key</span></div>
      <div class="toolbar"><input id="member-search" v-model="q" class="input" placeholder="搜尋名稱、Email 或備註" aria-label="搜尋會員" /><button class="btn btn-p btn-sm" @click="startCreate"><Icon n="plus" :s="15" />新增會員</button></div>
      <div class="mlist scroll">
        <button v-for="x in list" :key="x.id" class="mrow" :class="{ on: !creating && x.id === selId }" @click="pick(x)">
          <span class="avatar-sm">{{ x.name.slice(0, 1) }}</span>
          <span class="mrow-main"><span class="strong ell">{{ x.name }}</span><span class="t12 muted ell">{{ x.email }}</span></span>
          <span class="mrow-side">
            <Pill v-if="!x.is_active" c="idle" t="已停用" />
            <span class="t12 muted num">{{ x.active_keys }} 把金鑰 · {{ fmtTok(x.month_used) }} / {{ x.monthly_token_quota ? fmtTok(x.monthly_token_quota) : '不限' }}</span>
            <span class="meter meter-sm" :class="quotaClass(x)"><i :style="{ width: pct(ratio(x)) }"></i></span>
          </span>
        </button>
        <div v-if="!members.length" class="empty">還沒有會員。按「新增會員」建立第一位。</div>
        <div v-else-if="!list.length" class="empty">找不到符合「{{ q }}」的會員。</div>
      </div>
    </section>

    <section v-if="creating" class="card detail scroll-y">
      <div class="d-head"><h2>新增會員</h2><button class="btn btn-s btn-sm" @click="creating = false">取消</button></div>
      <p class="t13 ink2" style="margin: 0">建立後系統產生一組初始密碼，交給會員登入。會員第一次登入要改密碼，之後自己建立 API Key。</p>
      <form class="form-grid" @submit.prevent="create">
        <div class="field"><label for="nm-name">名稱</label><input id="nm-name" v-model="nf.name" class="input" placeholder="人名或團隊名稱" /></div>
        <div class="field"><label for="nm-email">Email（登入帳號）</label><input id="nm-email" v-model.trim="nf.email" type="email" class="input" placeholder="name@example.com" /></div>
        <div class="field full"><label for="nm-note">備註</label><input id="nm-note" v-model="nf.note" class="input" placeholder="只有管理者看得到" /></div>
        <div class="field"><label for="nm-quota">每月 Token 上限（百萬）</label><input id="nm-quota" v-model="nf.quota_m" type="number" class="input num" min="0" step="0.5" /><span class="hint">所有金鑰合計，0 表示不限。</span></div>
        <div class="field"><label for="nm-maxkeys">最多幾把金鑰</label><input id="nm-maxkeys" v-model="nf.max_keys" type="number" class="input num" min="1" max="50" /></div>
        <div class="ap-actions full"><button class="btn btn-p btn-sm" type="submit" :disabled="!!nfErr">建立會員並產生初始密碼</button><span v-if="nfErr" class="t12 muted">{{ nfErr }}</span></div>
      </form>
    </section>

    <section v-else-if="m" class="card detail scroll-y">
      <div class="d-head">
        <div class="d-title"><span class="avatar-lg">{{ m.name.slice(0, 1) }}</span><div style="min-width: 0"><h2 class="ell">{{ m.name }}</h2><div class="t13 muted ell">{{ m.email }} · 最後登入 {{ m.last_login_at ? fmtTime(m.last_login_at) : '尚未登入' }}</div></div></div>
        <Pill :c="m.is_active ? 'good' : 'idle'" :t="m.is_active ? '啟用中' : '已停用'" />
      </div>
      <SecretBox v-if="secret" :title="secret.title" :hint="secret.hint" :value="secret.value" done="我已交給會員" @close="secret = null" />
      <div>
        <div class="tabs">
          <button class="tab" :class="{ on: tab === 'profile' }" @click="tab = 'profile'">帳號與上限</button>
          <button class="tab" :class="{ on: tab === 'keys' }" @click="tab = 'keys'">API Keys <span class="count">{{ m.active_keys }}</span></button>
          <button class="tab" :class="{ on: tab === 'usage' }" @click="tab = 'usage'">用量</button>
        </div>

        <div v-if="tab === 'profile'" class="detail">
          <div class="form-grid">
            <div class="field"><label for="mp-name">名稱</label><input id="mp-name" v-model="draft.name" class="input" :class="{ changed: changed('name') }" /></div>
            <div class="field"><label for="mp-email">Email（登入帳號）</label><input id="mp-email" v-model.trim="draft.email" type="email" class="input" :class="{ changed: changed('email') }" /></div>
            <div class="field full"><label for="mp-note">備註</label><input id="mp-note" v-model="draft.note" class="input" :class="{ changed: changed('note') }" /><span class="hint">只有管理者看得到。</span></div>
            <div class="field"><label for="mp-quota">每月 Token 上限（百萬）</label><input id="mp-quota" v-model="draft.quota_m" type="number" class="input num" min="0" step="0.5" :class="{ changed: changed('quota_m') }" /><span class="hint">本月已用 {{ fmtTok(m.month_used) }}。用完回 429 insufficient_quota。</span></div>
            <div class="field"><label for="mp-maxkeys">最多幾把金鑰</label><input id="mp-maxkeys" v-model="draft.max_keys" type="number" class="input num" min="1" max="50" :class="{ changed: changed('max_keys') }" /><span class="hint">目前 {{ m.active_keys }} 把有效。</span></div>
            <div class="field full"><label class="switch" for="mp-status"><input id="mp-status" v-model="draft.is_active" type="checkbox" />{{ draft.is_active ? '啟用中' : '已停用：不能登入，所有金鑰暫停，呼叫回 403' }}</label></div>
          </div>
          <div class="row-between" style="align-items: center"><span class="t13 muted">會員忘記密碼時，由管理者重設並產生臨時密碼。</span><button class="btn btn-s btn-sm" @click="resetPassword">重設密碼</button></div>
          <div v-if="dirty" class="savebar"><span>有未儲存的變更</span><button class="btn btn-s btn-sm" @click="reset">捨棄</button><button class="btn btn-p btn-sm" @click="save">儲存</button></div>
        </div>

        <div v-if="tab === 'keys'" class="detail">
          <div class="notice notice-info">金鑰由會員登入後自己建立。完整金鑰只有會員在建立當下看得到；管理者可以看用量，撤銷外洩或不再使用的金鑰。</div>
          <div v-if="!m.is_active" class="notice notice-warn">這位會員已停用，下面的金鑰都暫停使用。</div>
          <KeyRows :keys="keys" @revoke="revoke" />
        </div>

        <div v-if="tab === 'usage' && usage" class="detail">
          <div><div class="row-between"><span class="label">本月用量</span><span class="t13 num">{{ fmtTok(usage.month_used) }} / {{ m.monthly_token_quota ? fmtTok(m.monthly_token_quota) : '不限' }}</span></div>
            <div class="meter" :class="quotaClass(m)" style="margin-top: 6px"><i :style="{ width: pct(ratio(m)) }"></i></div></div>
          <template v-if="chart.series.length">
            <div class="legend"><span v-for="s in chart.series" :key="s.key" class="lg"><i :style="{ background: s.color }"></i><span class="mono">{{ s.name }}</span></span></div>
            <StackedBars :labels="chart.labels" :series="chart.series" :height="210" />
          </template>
          <div v-else class="empty">這位會員近 14 天沒有用量。</div>
          <div v-if="usage.month_by_key.length" class="scroll-x"><table class="tbl"><thead><tr><th>金鑰（本月）</th><th class="r">請求</th><th class="r">輸入</th><th class="r">輸出</th><th class="r">合計</th></tr></thead>
            <tbody><tr v-for="r in usage.month_by_key" :key="r.api_key_id"><td><span class="strong">{{ r.name }}</span> <span class="mono t12 muted">{{ r.masked }}</span></td><td class="r">{{ fmtInt(r.requests) }}</td><td class="r">{{ fmtTok(r.prompt_tokens) }}</td><td class="r">{{ fmtTok(r.completion_tokens) }}</td><td class="r strong">{{ fmtTok(r.prompt_tokens + r.completion_tokens) }}</td></tr></tbody></table></div>
        </div>
      </div>
    </section>
  </div>
</template>
