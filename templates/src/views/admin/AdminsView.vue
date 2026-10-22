<script setup>
// 後台帳號（Superuser 與管理員）、權限對照、操作紀錄；只有 Superuser 看得到
import { computed, onMounted, reactive, ref, watch } from 'vue'
import Icon from '../../components/Icon.vue'
import Pill from '../../components/Pill.vue'
import SecretBox from '../../components/SecretBox.vue'
import { api } from '../../api/client'
import { useAuth } from '../../stores/auth'
import { toast } from '../../stores/toast'
import { ROLE_LABEL, fmtTime } from '../../composables/format'

const auth = useAuth()
const tab = ref('list')
const admins = ref([])
const audit = ref([])
const secret = ref(null)
const af = reactive({ open: false, name: '', email: '', is_superuser: false })
const PERMS = [
  ['總覽、系統監控（記憶體、模型狀態）', true, true, false],
  ['載入、卸載模型', true, true, false],
  ['新增、刪除、下載模型，修改模型設定', true, false, false],
  ['所有會員的用量統計與請求紀錄', true, true, false],
  ['會員帳號：新增、調整上限與可用模型、重設密碼、停用', true, true, false],
  ['撤銷任何會員的 API Key（看不到完整金鑰）', true, true, false],
  ['後台帳號（含指定 Superuser）、操作紀錄', true, false, false],
  ['系統設定', true, false, false],
  ['自己的 API Key：建立、撤銷', false, false, true],
  ['自己的用量、請求紀錄、串接說明', false, false, true],
  ['測試台', true, true, true],
]

async function load() { admins.value = await api('/api/admins') }
onMounted(load)
watch(tab, async (t) => { if (t === 'audit') audit.value = await api('/api/audit') })
const suCount = computed(() => admins.value.filter((a) => a.role === 'superuser' && a.is_active).length)

async function patch(a, body, msg) {
  try {
    await api(`/api/admins/${a.id}`, { method: 'PATCH', body })
    toast(msg)
    await load()
  } catch (e) { toast(e.message) }
}
async function create() {
  try {
    const r = await api('/api/admins', { method: 'POST', body: { name: af.name.trim(), email: af.email.trim(), is_superuser: af.is_superuser } })
    secret.value = { title: `已建立「${r.admin.email}」`, hint: '初始密碼只顯示這一次，第一次登入後必須修改。', value: r.initial_password }
    Object.assign(af, { open: false, name: '', email: '', is_superuser: false })
    await load()
  } catch (e) { toast(e.message) }
}
</script>

<template>
  <div class="page">
    <section class="card">
      <div class="tabs">
        <button class="tab" :class="{ on: tab === 'list' }" @click="tab = 'list'">後台帳號 <span class="count">{{ admins.length }}</span></button>
        <button class="tab" :class="{ on: tab === 'perm' }" @click="tab = 'perm'">權限對照</button>
        <button class="tab" :class="{ on: tab === 'audit' }" @click="tab = 'audit'">操作紀錄</button>
      </div>

      <div v-if="tab === 'list'" class="detail">
        <p class="t13 ink2" style="margin: 0">這裡是管理者帳號（Superuser 與管理員），會員帳號在「會員」頁建立。第一個 Superuser 用 <code>poetry run python create_superuser.py</code> 建立，至少要保留一位 Superuser。</p>
        <SecretBox v-if="secret" :title="secret.title" :hint="secret.hint" :value="secret.value" @close="secret = null" />
        <div class="scroll-x">
          <table class="tbl">
            <thead><tr><th>帳號</th><th>角色</th><th>最後登入</th><th>狀態</th><th></th></tr></thead>
            <tbody>
              <tr v-for="a in admins" :key="a.id">
                <td><span class="strong">{{ a.name }}</span> <span class="t12 muted">{{ a.email }}</span><span v-if="a.id === auth.user?.id" class="cap" style="margin-left: 6px">你</span></td>
                <td><span class="cap" :style="a.role === 'superuser' ? 'background: var(--accent); color: var(--accent-fg)' : ''">{{ ROLE_LABEL[a.role] }}</span></td>
                <td class="t13 muted">{{ a.last_login_at ? fmtTime(a.last_login_at) : '尚未登入' }}</td>
                <td><Pill :c="a.is_active ? 'good' : 'idle'" :t="a.is_active ? '啟用中' : '已停用'" /></td>
                <td class="r"><div style="display: inline-flex; gap: 6px">
                  <button class="btn btn-s btn-xs" :disabled="a.role === 'superuser' && suCount <= 1" @click="patch(a, { is_superuser: a.role !== 'superuser' }, a.role === 'superuser' ? '已改為管理員' : '已設為 Superuser')">{{ a.role === 'superuser' ? '改為管理員' : '設為 Superuser' }}</button>
                  <button class="btn btn-s btn-xs" :disabled="a.id === auth.user?.id" @click="patch(a, { is_active: !a.is_active }, a.is_active ? '已停用' : '已啟用')">{{ a.is_active ? '停用' : '啟用' }}</button>
                </div></td>
              </tr>
            </tbody>
          </table>
        </div>
        <p v-if="suCount <= 1" class="t12 muted" style="margin: 0">目前只有一位 Superuser，所以不能把他改成管理員或停用。</p>
        <div v-if="!af.open"><button class="btn btn-p btn-sm" @click="af.open = true"><Icon n="plus" :s="15" />新增後台帳號</button></div>
        <form v-else class="action-panel" @submit.prevent="create">
          <div class="ap-h"><strong>新增後台帳號</strong><button type="button" class="ib" aria-label="關閉" @click="af.open = false"><Icon n="x" :s="16" /></button></div>
          <div class="form-grid">
            <div class="field"><label for="af-name">名稱</label><input id="af-name" v-model="af.name" class="input" required /></div>
            <div class="field"><label for="af-email">Email</label><input id="af-email" v-model="af.email" type="email" class="input" required /></div>
            <div class="field full"><span class="flabel">角色</span><div class="checks-inline"><label><input id="af-r-a" v-model="af.is_superuser" type="radio" :value="false" />管理員</label><label><input id="af-r-s" v-model="af.is_superuser" type="radio" :value="true" />Superuser</label></div></div>
          </div>
          <div class="ap-actions"><button class="btn btn-p btn-sm" type="submit" :disabled="!af.name.trim() || !af.email.trim()">建立並產生初始密碼</button></div>
        </form>
      </div>

      <div v-if="tab === 'perm'" class="detail">
        <p class="t13 ink2" style="margin: 0">模型管理只給管理者，會員完全看不到。</p>
        <div class="scroll-x"><table class="tbl"><thead><tr><th>功能</th><th>Superuser</th><th>管理員</th><th>會員</th></tr></thead>
          <tbody><tr v-for="p in PERMS" :key="p[0]"><td class="wrap">{{ p[0] }}</td><td>{{ p[1] ? '可以' : '—' }}</td><td>{{ p[2] ? '可以' : '—' }}</td><td>{{ p[3] ? '可以' : '—' }}</td></tr></tbody></table></div>
      </div>

      <div v-if="tab === 'audit'" class="detail">
        <div class="scroll-x"><table class="tbl"><thead><tr><th>時間</th><th>操作者</th><th>操作</th><th>對象</th></tr></thead>
          <tbody><tr v-for="e in audit" :key="e.id"><td class="muted t13">{{ fmtTime(e.created_at) }}</td><td class="mono t13">{{ e.actor }}</td><td>{{ e.action }}</td><td class="t13 wrap">{{ e.target }}</td></tr></tbody></table></div>
        <div v-if="!audit.length" class="empty">還沒有操作紀錄。</div>
      </div>
    </section>
  </div>
</template>
