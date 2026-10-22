<script setup>
// 帳號管理：會員（管理員以上）、管理者帳號與操作紀錄（Superuser）、權限對照
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AdminsView from './AdminsView.vue'
import MembersView from './MembersView.vue'
import { useAuth } from '../../stores/auth'

const auth = useAuth()
const route = useRoute()
const router = useRouter()
const tabs = computed(() => [
  { id: 'members', label: '會員' },
  ...(auth.isSU ? [{ id: 'admins', label: '管理者' }] : []),
  { id: 'perm', label: '權限對照' },
  ...(auth.isSU ? [{ id: 'audit', label: '操作紀錄' }] : []),
])
const tab = ref(tabs.value.some((t) => t.id === route.query.tab) ? route.query.tab : 'members')
watch(tab, (t) => router.replace({ query: t === 'members' ? { id: route.query.id } : { tab: t } }))
const section = computed(() => ({ admins: 'list', perm: 'perm', audit: 'audit' })[tab.value])
</script>

<template>
  <div class="page fill">
    <div class="tabs" style="margin-bottom: 0">
      <button v-for="t in tabs" :key="t.id" class="tab" :class="{ on: tab === t.id }" @click="tab = t.id">{{ t.label }}</button>
    </div>
    <MembersView v-if="tab === 'members'" class="grow" />
    <section v-else class="card scroll-y grow"><AdminsView :section="section" /></section>
  </div>
</template>
