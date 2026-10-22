<script setup>
// 系統設定（系統監控右上角開的 modal）：左邊 1/4 是分類，右邊 3/4 是那一類的參數
import { computed, onMounted, reactive, ref } from 'vue'
import { api } from '../api/client'
import { toast } from '../stores/toast'

const SECTIONS = [
  { id: 'memory', label: '記憶體' },
  { id: 'limits', label: '新會員預設限制' },
  { id: 'login', label: '登入與紀錄' },
  { id: 'env', label: '部署設定' },
]
const section = ref('memory')
const data = ref(null)
const draft = reactive({})
const keys = ['metal_limit_gb', 'headroom_gb', 'default_quota_m', 'default_max_keys', 'retention_days', 'restore_on_boot', 'login_guard']
const SECTION_OF = { metal_limit_gb: 'memory', headroom_gb: 'memory', default_quota_m: 'limits', default_max_keys: 'limits', retention_days: 'login', restore_on_boot: 'login', login_guard: 'login' }

onMounted(async () => {
  data.value = await api('/api/settings')
  Object.assign(draft, data.value.values)
})
const changed = (k) => data.value && String(draft[k]) !== String(data.value.values[k])
const dirty = computed(() => keys.some(changed))
const dirtySections = computed(() => new Set(keys.filter(changed).map((k) => SECTION_OF[k])))
function reset() { Object.assign(draft, data.value.values) }
async function save() {
  const body = {}
  for (const k of keys) if (changed(k)) body[k] = typeof data.value.values[k] === 'boolean' ? draft[k] : Number(draft[k])
  try {
    data.value = await api('/api/settings', { method: 'PUT', body })
    Object.assign(draft, data.value.values)
    toast('已儲存系統設定')
  } catch (e) { toast(e.message) }
}
</script>

<template>
  <div v-if="data" class="settings">
    <nav class="settings-nav" aria-label="設定分類">
      <button v-for="s in SECTIONS" :key="s.id" :class="{ on: section === s.id }" @click="section = s.id">{{ s.label }}<i v-if="dirtySections.has(s.id)" class="dirty-dot" aria-label="有未儲存的變更"></i></button>
    </nav>
    <div class="settings-body">
      <div class="settings-scroll detail">
        <template v-if="section === 'memory'">
          <h3 class="settings-h">記憶體</h3>
          <div class="field"><label for="cf-limit">Metal 上限（GB）</label><input id="cf-limit" v-model="draft.metal_limit_gb" type="number" step="0.5" class="input num" :class="{ changed: changed('metal_limit_gb') }" /><span class="hint">預設 {{ data.defaults.metal_limit_gb }} GB。要讓 GPU 真的能用這麼多，還要 <code>sudo sysctl iogpu.wired_limit_mb={{ Math.round(draft.metal_limit_gb * 1024) }}</code>（重開機會還原，見 deploy/ 的 launchd 範本）。</span></div>
          <div class="field"><label for="cf-head">安全餘裕（GB）</label><input id="cf-head" v-model="draft.headroom_gb" type="number" step="0.5" min="0" class="input num" :class="{ changed: changed('headroom_gb') }" /><span class="hint">載入後實體記憶體至少要剩這麼多，避免 macOS 開始大量 swap。</span></div>
        </template>
        <template v-if="section === 'limits'">
          <h3 class="settings-h">新會員的預設限制</h3>
          <p class="t13 muted" style="margin: 0">建立會員時預先填入的數字，已經存在的會員不受影響。</p>
          <div class="field"><label for="cf-quota">每月 Token 上限（百萬）</label><input id="cf-quota" v-model="draft.default_quota_m" type="number" step="0.5" class="input num" :class="{ changed: changed('default_quota_m') }" /></div>
          <div class="field"><label for="cf-keys">每人最多幾把金鑰</label><input id="cf-keys" v-model="draft.default_max_keys" type="number" class="input num" :class="{ changed: changed('default_max_keys') }" /></div>
        </template>
        <template v-if="section === 'login'">
          <h3 class="settings-h">登入與紀錄</h3>
          <div class="field"><label class="switch" for="cf-guard"><input id="cf-guard" v-model="draft.login_guard" type="checkbox" />登入保護：同一個帳號連續失敗 5 次鎖 15 分鐘</label><span class="hint">會員也要從後台網域登入，所以不用只允許單一 email 的 Cloudflare Access；建議另外在 Cloudflare 對 /api/auth/login 限流。</span></div>
          <div class="field"><label for="cf-ret">請求紀錄保留（天）</label><input id="cf-ret" v-model="draft.retention_days" type="number" class="input num" :class="{ changed: changed('retention_days') }" /><span class="hint">每日彙總永久保留。</span></div>
          <div class="field"><label class="switch" for="cf-boot"><input id="cf-boot" v-model="draft.restore_on_boot" type="checkbox" />重新啟動後，自動載入關機前已載入的模型</label><span class="hint">預設關閉（只手動載入）。關閉時，停電或系統更新重開後 API 會一直回 503，直到有人登入後台載入。</span></div>
          <p class="t13 muted" style="margin: 0">帳號一律由管理者在「帳號管理」建立並給初始密碼，不開放自行註冊。</p>
        </template>
        <template v-if="section === 'env'">
          <h3 class="settings-h">部署設定</h3>
          <p class="t13 muted" style="margin: 0">這些在 <code>.env</code> 設定，改了要重啟 FastAPI，這裡只能看。</p>
          <dl class="kv">
            <div><dt>對外 API 網址</dt><dd class="mono t13">{{ data.env.public_api_base }}</dd></div>
            <div><dt>後台網域</dt><dd class="mono t13">{{ data.env.console_host || '未設定 CONSOLE_HOST' }}</dd></div>
            <div class="full"><dt>模型存放位置</dt><dd class="mono t13">{{ data.env.model_dir }}</dd></div>
            <div><dt>假 worker</dt><dd>{{ data.env.fake_workers ? '開啟（FAKE_WORKERS=true，開發用）' : '關閉' }}</dd></div>
          </dl>
        </template>
      </div>
      <div v-if="dirty" class="savebar"><span>有未儲存的變更</span><button class="btn btn-s btn-sm" @click="reset">捨棄</button><button class="btn btn-p btn-sm" @click="save">儲存</button></div>
    </div>
  </div>
  <div v-else class="loading-line">載入中…</div>
</template>
