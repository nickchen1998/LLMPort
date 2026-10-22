<script setup>
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuth } from '../stores/auth'

const auth = useAuth()
const router = useRouter()
const route = useRoute()
const email = ref('')
const password = ref('')
const error = ref('')
const busy = ref(false)

async function submit() {
  error.value = ''
  busy.value = true
  try {
    const user = await auth.login(email.value.trim(), password.value)
    if (user.must_change_password) return router.push('/change-password')
    router.push(route.query.next || auth.home)
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="login-wrap">
    <form class="login-card" @submit.prevent="submit">
      <div class="login-brand">
        <img class="logo" src="/logo.png" width="40" height="40" alt="" />
        <div><div class="name">LLMPort</div><div class="t13 muted">本地模型與 API Key 管理</div></div>
      </div>
      <div class="field"><label for="login-email">Email</label><input id="login-email" v-model="email" class="input" type="email" autocomplete="username" required /></div>
      <div class="field"><label for="login-password">密碼</label><input id="login-password" v-model="password" class="input" type="password" autocomplete="current-password" required /></div>
      <div v-if="error" class="err">{{ error }}</div>
      <button class="btn btn-p" type="submit" :disabled="busy">{{ busy ? '登入中…' : '登入' }}</button>
      <p class="t12 muted" style="margin: 0">帳號由管理者建立。忘記密碼請找管理者重設。</p>
    </form>
  </div>
</template>
