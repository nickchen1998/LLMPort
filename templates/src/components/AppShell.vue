<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterView, useRoute, useRouter } from 'vue-router'
import AccountSettings from './AccountSettings.vue'
import Icon from './Icon.vue'
import Modal from './Modal.vue'
import { api } from '../api/client'
import { shellRoutes } from '../router/routes'
import { useAuth } from '../stores/auth'
import { useSystem } from '../stores/system'
import { toastState } from '../stores/toast'
import { ROLE_LABEL, fmtTok } from '../composables/format'

const auth = useAuth()
const system = useSystem()
const route = useRoute()
const router = useRouter()
const nav = computed(() => shellRoutes.filter((r) => r.meta.roles.includes(auth.role)))
const groups = computed(() => [
  { title: '服務中心', items: nav.value.filter((r) => r.meta.group !== 'manage') },
  { title: '管理中心', items: nav.value.filter((r) => r.meta.group === 'manage') },
].filter((g) => g.items.length))
const title = computed(() => route.meta.title || '')
const summary = ref(null)
const menu = ref(false)
const modal = ref(null)
function open(name) { menu.value = false; modal.value = name }

async function loadSummary() {
  if (auth.isMember) summary.value = await api('/api/me/summary').catch(() => null)
}
onMounted(() => {
  if (auth.isAdmin) system.connect()
  loadSummary()
})
watch(() => route.path, loadSummary)
onBeforeUnmount(() => system.disconnect())

function logout() {
  modal.value = null
  system.disconnect()
  auth.logout()
  router.push('/login')
}
</script>

<template>
  <div class="shell">
    <aside class="side">
      <div class="side-in">
        <div class="brand">
          <img class="logo" src="/logo.png" width="32" height="32" alt="" />
          <div><div class="brand-name">LLMPort</div><div class="brand-sub">Mac mini · MLX</div></div>
        </div>
        <nav class="nav" aria-label="頁面">
          <template v-for="g in groups" :key="g.title">
            <div class="nav-group">{{ g.title }}</div>
            <RouterLink v-for="r in g.items" :key="r.path" :to="r.path" class="nav-i" active-class="on">
              <Icon :n="r.meta.icon" /><span>{{ r.meta.title }}</span><Icon v-if="r.meta.lock" n="lock" :s="13" class="nav-lock" />
            </RouterLink>
          </template>
        </nav>
        <div class="me">
          <button class="me-btn" :aria-expanded="menu" aria-haspopup="menu" @click="menu = !menu">
            <span class="avatar">{{ (auth.user?.name || '?').slice(0, 1) }}</span>
            <span class="me-t"><span class="me-name ell">{{ auth.user?.email }}</span><span class="t12 side-muted">{{ ROLE_LABEL[auth.role] }}</span></span>
          </button>
          <div v-if="menu" class="me-menu" role="menu">
            <button role="menuitem" @click="open('account')"><Icon n="user" :s="16" />帳號設定</button>
            <button role="menuitem" @click="open('logout')"><Icon n="logout" :s="16" />登出</button>
          </div>
        </div>
      </div>
    </aside>
    <main class="main">
      <header class="top">
        <div class="top-l"><h1 class="top-title">{{ title }}</h1></div>
        <div id="page-actions" class="top-r"></div>
        <div v-if="summary" class="top-r">
          <RouterLink to="/dashboard" class="chip-btn"><Icon n="bars" :s="14" /><span class="num">本月 {{ fmtTok(summary.month_used) }} / {{ summary.monthly_token_quota ? fmtTok(summary.monthly_token_quota) : '不限' }}</span></RouterLink>
        </div>
      </header>
      <div class="content"><RouterView /></div>
    </main>
    <div v-if="toastState.text" class="toast" role="status">{{ toastState.text }}</div>
    <div v-if="menu" class="me-mask" @click="menu = false"></div>
    <Modal v-if="modal === 'account'" title="帳號設定" @close="modal = null"><AccountSettings /></Modal>
    <Modal v-if="modal === 'logout'" title="登出" width="400px" @close="modal = null">
      <p class="t13 ink2" style="margin: 0 0 16px">確定要登出 {{ auth.user?.email }} 嗎？</p>
      <div class="ap-actions" style="justify-content: flex-end"><button class="btn btn-s btn-sm" @click="modal = null">取消</button><button class="btn btn-dp btn-sm" @click="logout">登出</button></div>
    </Modal>
  </div>
</template>

<style scoped>
a.nav-i, a.chip-btn { text-decoration: none; }
</style>
