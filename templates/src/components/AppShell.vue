<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterView, useRoute, useRouter } from 'vue-router'
import Icon from './Icon.vue'
import { api } from '../api/client'
import { shellRoutes } from '../router/routes'
import { useAuth } from '../stores/auth'
import { useSystem } from '../stores/system'
import { toastState } from '../stores/toast'
import { ROLE_LABEL, fmtGB, fmtTok } from '../composables/format'

const auth = useAuth()
const system = useSystem()
const route = useRoute()
const router = useRouter()
const nav = computed(() => shellRoutes.filter((r) => r.meta.roles.includes(auth.role)))
const title = computed(() => route.meta.title || '')
const summary = ref(null)

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
  system.disconnect()
  auth.logout()
  router.push('/login')
}
const tunnelText = computed(() => ({ connected: 'Tunnel 已連線', down: 'Tunnel 中斷', unknown: 'Tunnel 未設定' })[system.tunnel])
</script>

<template>
  <div class="shell">
    <aside class="side">
      <div class="side-in">
        <div class="brand">
          <svg class="logo" viewBox="0 0 32 32" aria-hidden="true"><rect x="2" y="2" width="28" height="28" rx="8" style="fill: var(--sun)" /><path d="M9 9v14h6M18 23V9h4a4 4 0 0 1 0 8h-4" fill="none" style="stroke: var(--on-sun)" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round" /></svg>
          <div><div class="brand-name">LLMPort</div><div class="brand-sub">Mac mini · MLX</div></div>
        </div>
        <nav class="nav" aria-label="頁面">
          <div class="nav-group">{{ auth.isMember ? '我的' : '後台' }}</div>
          <RouterLink v-for="r in nav" :key="r.path" :to="r.path" class="nav-i" active-class="on">
            <Icon :n="r.meta.icon" /><span>{{ r.meta.title }}</span><Icon v-if="r.meta.lock" n="lock" :s="13" class="nav-lock" />
          </RouterLink>
        </nav>
        <div class="me">
          <div class="me-row"><span class="avatar">{{ (auth.user?.name || '?').slice(0, 1) }}</span><div style="min-width: 0"><div class="me-name ell">{{ auth.user?.email }}</div><div class="t12 side-muted">{{ ROLE_LABEL[auth.role] }}</div></div></div>
          <button class="seg-dark-btn nav-i" @click="logout"><Icon n="logout" :s="16" /><span>登出</span></button>
        </div>
      </div>
    </aside>
    <main class="main">
      <header class="top">
        <div class="top-l"><h1 class="top-title">{{ title }}</h1></div>
        <div v-if="auth.isAdmin" class="top-r">
          <RouterLink to="/monitor" class="chip-btn"><span class="dot" :class="system.tunnel === 'connected' ? 'dot-good' : ''" :style="system.tunnel === 'connected' ? null : 'background: var(--axis)'"></span>{{ tunnelText }}</RouterLink>
          <RouterLink v-if="system.budget" to="/dashboard" class="chip-btn"><Icon n="chip" :s="14" /><span class="num">模型 {{ fmtGB(system.budget.models_mb) }} / {{ fmtGB(system.budget.metal_limit_mb) }} GB</span></RouterLink>
        </div>
        <div v-else-if="summary" class="top-r">
          <RouterLink to="/my" class="chip-btn"><Icon n="bars" :s="14" /><span class="num">本月 {{ fmtTok(summary.month_used) }} / {{ summary.monthly_token_quota ? fmtTok(summary.monthly_token_quota) : '不限' }}</span></RouterLink>
        </div>
      </header>
      <div class="content"><RouterView /></div>
    </main>
    <div v-if="toastState.text" class="toast" role="status">{{ toastState.text }}</div>
  </div>
</template>

<style scoped>
a.nav-i, a.chip-btn { text-decoration: none; }
.seg-dark-btn { color: var(--side-fg); }
</style>
