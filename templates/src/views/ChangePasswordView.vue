<script setup>
// 管理者建立或重設帳號後，第一次登入要先改密碼
import { computed, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import Icon from '../components/Icon.vue'
import { api } from '../api/client'
import { useAuth } from '../stores/auth'
import { passwordRules } from '../composables/format'

const auth = useAuth()
const router = useRouter()
const pw = reactive({ cur: '', next: '', again: '' })
const error = ref('')
const rules = computed(() => passwordRules(pw.next, pw.again))
const ok = computed(() => pw.cur && rules.value.every((r) => r[1]))

async function submit() {
  error.value = ''
  try {
    auth.user = await api('/api/auth/password', { method: 'POST', body: { current_password: pw.cur, new_password: pw.next } })
    router.push(auth.home)
  } catch (e) {
    error.value = e.message
  }
}
</script>

<template>
  <div class="login-wrap">
    <form class="login-card" @submit.prevent="submit">
      <div><div class="strong" style="font-size: 19.5px">設定新密碼</div><p class="t13 muted" style="margin: 4px 0 0">{{ auth.user?.email }} 第一次登入，請把管理者給的密碼換成自己的。</p></div>
      <div class="field"><label for="cp-cur">目前密碼</label><input id="cp-cur" v-model="pw.cur" class="input" type="password" autocomplete="current-password" /></div>
      <div class="field"><label for="cp-new">新密碼</label><input id="cp-new" v-model="pw.next" class="input" type="password" autocomplete="new-password" /></div>
      <div class="field"><label for="cp-again">再輸入一次</label><input id="cp-again" v-model="pw.again" class="input" type="password" autocomplete="new-password" /></div>
      <ul class="checklist" style="flex-direction: row; flex-wrap: wrap; gap: 6px 14px"><li v-for="r in rules" :key="r[0]" :class="r[1] ? 'ok' : 'bad'"><Icon :n="r[1] ? 'check' : 'x'" :s="15" />{{ r[0] }}</li></ul>
      <div v-if="error" class="err">{{ error }}</div>
      <button class="btn btn-p" type="submit" :disabled="!ok">儲存新密碼</button>
      <button class="link-btn t13" type="button" @click="auth.logout(); router.push('/login')">登出</button>
    </form>
  </div>
</template>
