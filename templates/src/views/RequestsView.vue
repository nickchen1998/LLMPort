<script setup>
// 請求紀錄：管理者看全部、會員只看自己；預設不保存提示詞與回應內容
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import Pill from '../components/Pill.vue'
import { api } from '../api/client'
import { useAuth } from '../stores/auth'
import { ENDPOINTS, fmtDuration, fmtInt, fmtTime, stc } from '../composables/format'

const auth = useAuth()
const rows = ref([])
const status = ref('')
const modelId = ref(0)
const endpoint = ref('')
const open = ref(null)
const models = ref([])
const live = ref(true)
let timer = null

async function load() {
  const qs = new URLSearchParams({ limit: 150 })
  if (status.value) qs.set('status', status.value)
  if (auth.isAdmin) {
    if (modelId.value) qs.set('model_id', modelId.value)
    if (endpoint.value) qs.set('endpoint', endpoint.value)
  }
  rows.value = await api(`${auth.isAdmin ? '/api/requests' : '/api/me/requests'}?${qs}`)
}
onMounted(async () => {
  models.value = auth.isAdmin ? (await api('/api/models')).models : await api('/api/me/models')
  load()
  timer = setInterval(() => live.value && load(), 5000)
})
onBeforeUnmount(() => clearInterval(timer))
watch([status, modelId, endpoint], load)
const visible = (r) => auth.isAdmin || ((!modelId.value || r.model_id === modelId.value) && (!endpoint.value || r.endpoint === endpoint.value))
</script>

<template>
  <div class="page">
    <div class="filters">
      <div class="seg" role="group" aria-label="狀態"><button :class="{ on: !status }" @click="status = ''">全部</button><button :class="{ on: status === 'ok' }" @click="status = 'ok'">成功</button><button :class="{ on: status === 'error' }" @click="status = 'error'">錯誤</button></div>
      <select id="req-model" v-model.number="modelId" class="input input-sm" aria-label="模型"><option :value="0">全部模型</option><option v-for="x in models" :key="x.id" :value="x.id">{{ x.api_name }}</option></select>
      <select id="req-ep" v-model="endpoint" class="input input-sm" aria-label="端點"><option value="">全部端點</option><option v-for="e in ENDPOINTS" :key="e" :value="e">{{ e }}</option></select>
      <label class="switch t13 ml-auto" for="req-live"><input id="req-live" v-model="live" type="checkbox" />每 5 秒更新</label>
    </div>
    <section class="card" style="padding: 6px 8px">
      <div class="scroll-x"><table class="tbl">
        <thead><tr><th>時間</th><th>{{ auth.isAdmin ? '帳號 · 金鑰' : '金鑰' }}</th><th>模型</th><th>端點</th><th>狀態</th><th class="r">輸入</th><th class="r">輸出</th><th class="r">首字</th><th class="r">總時間</th></tr></thead>
        <tbody>
          <template v-for="r in rows" :key="r.id">
            <tr v-if="visible(r)" class="click" :class="{ opened: open === r.id }" @click="open = open === r.id ? null : r.id">
              <td class="num muted">{{ fmtTime(r.created_at) }}</td>
              <td v-if="auth.isAdmin"><span class="strong">{{ r.user_name || '（未知金鑰）' }}</span> <span class="t12 muted">· {{ r.key_name || '—' }}</span></td>
              <td v-else><span class="strong">{{ r.key_name || '—' }}</span></td>
              <td class="mono t12">{{ r.model || '—' }}</td>
              <td class="mono t12">{{ r.endpoint }}<span v-if="r.has_image" class="cap" style="margin-left: 6px">含圖片</span></td>
              <td><Pill :c="stc(r.status_code)" :t="String(r.status_code)" /></td>
              <td class="r">{{ r.prompt_tokens ? fmtInt(r.prompt_tokens) : '—' }}</td><td class="r">{{ r.completion_tokens ? fmtInt(r.completion_tokens) : '—' }}</td>
              <td class="r">{{ fmtDuration(r.ttft_ms) }}</td><td class="r">{{ fmtDuration(r.duration_ms) }}</td>
            </tr>
            <tr v-if="open === r.id && visible(r)"><td colspan="9" class="wrap" style="background: var(--soft)">
              <dl class="kv" style="padding: 6px 4px">
                <div><dt>request_id</dt><dd class="mono t13">{{ r.request_id }}</dd></div>
                <div><dt>金鑰</dt><dd class="mono t13">{{ r.key_masked || (r.source === 'playground' ? '（測試台，登入身分）' : '—') }}</dd></div>
                <div><dt>錯誤代碼</dt><dd class="mono t13">{{ r.error_code || '—' }}</dd></div>
                <div><dt>串流</dt><dd>{{ r.stream ? '是' : '否' }}</dd></div>
                <div><dt>來源國家（CF-IPCountry）</dt><dd>{{ r.client_country || '—' }}</dd></div>
                <div><dt>來源</dt><dd>{{ r.source === 'playground' ? '測試台' : 'API' }}</dd></div>
              </dl>
            </td></tr>
          </template>
        </tbody>
      </table></div>
      <div v-if="!rows.length" class="empty" style="margin: 10px">沒有符合條件的請求。</div>
    </section>
  </div>
</template>
