<script setup>
import { computed, reactive, ref } from 'vue'
import Icon from '../../components/Icon.vue'
import { api } from '../../api/client'
import { useAuth } from '../../stores/auth'
import { toast } from '../../stores/toast'
import { passwordRules } from '../../composables/format'

const auth = useAuth()
const name = ref(auth.user?.name || '')
const pw = reactive({ cur: '', next: '', again: '' })
const rules = computed(() => passwordRules(pw.next, pw.again))
const pwOk = computed(() => pw.cur && rules.value.every((r) => r[1]))

async function saveName() {
  try {
    auth.user = await api('/api/me', { method: 'PATCH', body: { name: name.value.trim() } })
    toast('已更新顯示名稱')
  } catch (e) { toast(e.message) }
}
async function changePw() {
  try {
    await api('/api/auth/password', { method: 'POST', body: { current_password: pw.cur, new_password: pw.next } })
    Object.assign(pw, { cur: '', next: '', again: '' })
    toast('已變更密碼')
  } catch (e) { toast(e.message) }
}
</script>

<template>
  <div class="page" style="max-width: 820px">
    <section class="card detail">
      <div class="card-h" style="margin: 0"><h2>基本資料</h2></div>
      <div class="form-grid">
        <div class="field"><label for="ma-email">Email（登入帳號）</label><input id="ma-email" class="input" :value="auth.user?.email" readonly /><span class="hint">要換 Email 請找管理者。</span></div>
        <div class="field"><label for="ma-name">顯示名稱</label><input id="ma-name" v-model="name" class="input" /></div>
      </div>
      <div class="ap-actions"><button class="btn btn-s btn-sm" :disabled="!name.trim() || name.trim() === auth.user?.name" @click="saveName">儲存</button></div>
    </section>
    <section class="card detail">
      <div class="card-h" style="margin: 0"><h2>變更密碼</h2></div>
      <form class="form-grid" @submit.prevent="changePw">
        <div class="field full"><label for="ma-cur">目前密碼</label><input id="ma-cur" v-model="pw.cur" type="password" class="input" autocomplete="current-password" /></div>
        <div class="field"><label for="ma-new">新密碼</label><input id="ma-new" v-model="pw.next" type="password" class="input" autocomplete="new-password" /></div>
        <div class="field"><label for="ma-again">再輸入一次</label><input id="ma-again" v-model="pw.again" type="password" class="input" autocomplete="new-password" /></div>
        <ul class="checklist full" style="flex-direction: row; flex-wrap: wrap; gap: 6px 16px"><li v-for="r in rules" :key="r[0]" :class="r[1] ? 'ok' : 'bad'"><Icon :n="r[1] ? 'check' : 'x'" :s="15" />{{ r[0] }}</li></ul>
        <div class="ap-actions full"><button class="btn btn-p btn-sm" type="submit" :disabled="!pwOk">變更密碼</button></div>
      </form>
    </section>
  </div>
</template>
