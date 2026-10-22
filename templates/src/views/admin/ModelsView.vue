<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import Icon from '../../components/Icon.vue'
import Pill from '../../components/Pill.vue'
import ProjBar from '../../components/ProjBar.vue'
import { api } from '../../api/client'
import { useAuth } from '../../stores/auth'
import { toast } from '../../stores/toast'
import { CAP, DL, MS, fmtGB, modelColor, pct, relTime } from '../../composables/format'

const auth = useAuth()
const route = useRoute()
const router = useRouter()
const data = ref(null)
const members = ref([])
const selId = ref(Number(route.query.id) || null)
const panel = ref(route.query.action || null)
const tab = ref('runtime')
const adding = ref(false)
const busy = ref(false)
const log = ref('')
const confirmDelete = ref(false)
let timer = null

async function load() {
  data.value = await api('/api/models')
  if (!selId.value && data.value.models.length) selId.value = data.value.models[0].id
}
onMounted(async () => {
  await load()
  members.value = await api('/api/members').catch(() => [])
  timer = setInterval(load, 2000)
})
onBeforeUnmount(() => clearInterval(timer))

const m = computed(() => data.value?.models.find((x) => x.id === selId.value))
const rt = computed(() => m.value?.runtime || { status: 'unloaded' })
const budget = computed(() => data.value?.budget)
const runtimes = computed(() => Object.fromEntries((data.value?.models || []).map((x) => [x.id, x.runtime])))
const loadedCount = computed(() => (data.value?.models || []).filter((x) => x.runtime.status === 'loaded').length)
const check = computed(() => m.value?.load_check)
const metalClass = computed(() => { const r = budget.value ? budget.value.models_mb / budget.value.metal_limit_mb : 0; return r > 0.92 ? 'crit' : r > 0.8 ? 'warn' : '' })
const access = computed(() => members.value.map((u) => ({ u, on: u.model_ids.includes(selId.value) })))

function pick(x) {
  adding.value = false
  if (selId.value !== x.id) { panel.value = null; confirmDelete.value = false; log.value = '' }
  selId.value = x.id
  router.replace({ query: { id: x.id } })
}

async function act(fn, ok) {
  busy.value = true
  try {
    await fn()
    if (ok) toast(ok)
    panel.value = null
    await load()
  } catch (e) {
    toast(e.message)
  } finally {
    busy.value = false
  }
}
const doLoad = () => act(() => api(`/api/models/${m.value.id}/load`, { method: 'POST' }), `開始載入 ${m.value.api_name}`)
const doUnload = (mode) => act(() => api(`/api/models/${m.value.id}/unload?mode=${mode}`, { method: 'POST' }), `開始卸載 ${m.value.api_name}`)
const doDownload = () => act(() => api(`/api/models/${m.value.id}/download`, { method: 'POST' }), `開始下載 ${m.value.source_repo}`)
async function doDelete() {
  const name = m.value.api_name
  await act(() => api(`/api/models/${m.value.id}`, { method: 'DELETE' }), `已刪除 ${name}`)
  selId.value = data.value.models[0]?.id || null
  confirmDelete.value = false
}
async function showLog() { log.value = (await api(`/api/models/${m.value.id}/log`)).log || '（沒有 log）' }
function goUnload(id) { selId.value = id; panel.value = 'unload' }

// 設定分頁
const draft = reactive({})
const snap = (x) => ({ display_name: x.display_name, aliases: x.aliases.join(', '), context_length: x.context_length, default_max_tokens: x.default_max_tokens, concurrency: x.concurrency, queue_max: x.queue_max, est_weights_mb: x.est_weights_mb, est_kv_mb: x.est_kv_mb, note: x.note || '', is_enabled: x.is_enabled })
function reset() { if (m.value) Object.assign(draft, snap(m.value)) }
watch(selId, reset)
watch(() => data.value && !Object.keys(draft).length, (v) => v && reset())
const changed = (k) => m.value && String(draft[k]) !== String(snap(m.value)[k])
const dirty = computed(() => m.value && Object.keys(draft).some(changed))
async function save() {
  const body = { ...draft, aliases: draft.aliases.split(',').map((s) => s.trim()).filter(Boolean) }
  for (const k of ['context_length', 'default_max_tokens', 'concurrency', 'queue_max', 'est_weights_mb', 'est_kv_mb']) body[k] = Number(body[k])
  await act(() => api(`/api/models/${m.value.id}`, { method: 'PATCH', body }), '已儲存模型設定')
  reset()
}

// 新增模型
const form = reactive({ source_repo: '', api_name: '', capabilities: ['chat'], engine: '', context_length: 32768, embedding_dims: null, start_download: true })
const canAdd = computed(() => /^[\w.-]+\/[\w.-]+$/.test(form.source_repo) && /^[a-z0-9][a-z0-9._-]*$/.test(form.api_name) && form.capabilities.length)
async function submitAdd() {
  const body = { ...form, engine: form.engine || null, embedding_dims: form.embedding_dims ? Number(form.embedding_dims) : null, context_length: Number(form.context_length) }
  try {
    const created = await api('/api/models', { method: 'POST', body })
    toast(form.start_download ? `已登記 ${created.api_name}，開始下載` : `已登記 ${created.api_name}`)
    adding.value = false
    await load()
    selId.value = created.id
  } catch (e) {
    toast(e.message)
  }
}
</script>

<template>
  <div v-if="data" class="page split">
    <section class="card">
      <div class="card-h"><h2>已登記的模型</h2><span class="t13 muted">{{ loadedCount }} 個已載入</span>
        <button v-if="auth.isSU" class="btn btn-s btn-sm ml-auto" @click="adding = true"><Icon n="plus" :s="15" />新增模型</button></div>
      <div v-if="data.fake_workers" class="notice notice-warn" style="margin-bottom: 10px">目前是開發模式（FAKE_WORKERS=true）：沒有模型檔的模型會用假 worker 載入，回覆與記憶體都是模擬的。</div>
      <div class="mlist">
        <button v-for="x in data.models" :key="x.id" class="mrow" :class="{ on: !adding && x.id === selId }" @click="pick(x)">
          <span class="sw" :style="{ background: modelColor(x.id) }"></span>
          <span class="mrow-main"><span class="mono strong ell">{{ x.api_name }}</span><span class="t12 muted ell">{{ x.source_repo }}</span>
            <span class="caps"><span v-for="c in x.capabilities" :key="c" class="cap">{{ CAP[c] }}</span><span v-if="x.download_status !== 'downloaded'" class="cap cap-demo">{{ DL[x.download_status] }}</span><span v-if="!x.is_enabled" class="cap">已停用</span></span></span>
          <span class="mrow-side"><Pill :c="MS[x.runtime.status].c" :t="MS[x.runtime.status].t" /><span class="num t12 muted">{{ x.runtime.mem_mb ? fmtGB(x.runtime.mem_mb) + ' GB' : '約 ' + fmtGB(x.est_mb) + ' GB' }}</span></span>
        </button>
        <div v-if="!data.models.length" class="empty">還沒有登記模型。執行 <code>poetry run python seed_models.py</code> 登記預設的三個模型。</div>
      </div>
      <div class="budget">
        <div class="row-between t13"><span class="muted">模型佔用 / Metal 上限</span><span class="num">{{ fmtGB(budget.models_mb) }} / {{ fmtGB(budget.metal_limit_mb) }} GB · 可再載入 {{ fmtGB(budget.can_load_mb) }} GB</span></div>
        <div class="meter" :class="metalClass"><i :style="{ width: pct(budget.models_mb / budget.metal_limit_mb) }"></i></div>
        <p class="t12 muted" style="margin: 0">只有手動載入與卸載：沒載入的模型被呼叫時，API 回 <code>503 model_not_loaded</code>，不會自動載入或擠掉其他模型。</p>
      </div>
    </section>

    <section v-if="adding" class="card detail">
      <div class="d-head"><h2>新增模型</h2><button class="btn btn-s btn-sm" @click="adding = false">取消</button></div>
      <p class="t13 ink2" style="margin: 0">登記 Hugging Face 上 MLX 格式的模型。下載完成後是「未載入」，按「載入」才會佔用記憶體。檔案放在 <code>{{ data.model_dir }}</code>。</p>
      <div class="form-grid">
        <div class="field full"><label for="add-repo">Hugging Face repo</label><input id="add-repo" v-model.trim="form.source_repo" class="input mono" placeholder="mlx-community/gemma-3-4b-it-qat-4bit" /><span class="hint">建議用 mlx-community 已轉好的 4-bit 或 8-bit 版本。需要授權的模型要在 .env 設 HF_TOKEN。</span></div>
        <div class="field"><label for="add-name">API 名稱</label><input id="add-name" v-model.trim="form.api_name" class="input mono" placeholder="gemma3-4b" /><span class="hint">呼叫時 model 欄位填這個；小寫英數與 - . _</span></div>
        <div class="field"><label for="add-engine">推論引擎</label><select id="add-engine" v-model="form.engine" class="input"><option value="">依能力自動判斷</option><option value="mlx-lm">mlx-lm（文字、決策）</option><option value="mlx-vlm">mlx-vlm（看圖）</option><option value="mlx-embeddings">mlx-embeddings（嵌入）</option></select></div>
        <div class="field full"><span class="flabel">能力</span><div class="checks-inline"><label v-for="(t, c) in CAP" :key="c"><input :id="'add-cap-' + c" v-model="form.capabilities" type="checkbox" :value="c" />{{ t }}</label></div><span class="hint">「決策」用對話模型的 token 機率計算，目前只支援 mlx-lm 引擎。</span></div>
        <div class="field"><label for="add-ctx">上下文長度</label><input id="add-ctx" v-model="form.context_length" type="number" class="input num" /></div>
        <div v-if="form.capabilities.includes('embedding')" class="field"><label for="add-dims">向量維度</label><input id="add-dims" v-model="form.embedding_dims" type="number" class="input num" placeholder="1024" /></div>
        <div class="field full"><label class="switch" for="add-dl"><input id="add-dl" v-model="form.start_download" type="checkbox" />登記後馬上開始下載</label></div>
      </div>
      <div class="ap-actions"><button class="btn btn-p btn-sm" :disabled="!canAdd" @click="submitAdd">{{ form.start_download ? '登記並下載' : '登記' }}</button><span v-if="!canAdd" class="t12 muted">填 repo、API 名稱，至少選一種能力。</span></div>
    </section>

    <section v-else-if="m" class="card detail">
      <div class="d-head">
        <div class="d-title"><span class="sw sw-lg" :style="{ background: modelColor(m.id) }"></span><div style="min-width: 0"><h2 class="mono ell">{{ m.api_name }}</h2><div class="t13 muted">{{ m.display_name }} · {{ m.quant || '—' }} · {{ m.engine }}</div></div></div>
        <div class="d-actions">
          <Pill :c="MS[rt.status].c" :t="MS[rt.status].t + (rt.fake && rt.status !== 'unloaded' ? '（假 worker）' : '')" />
          <button v-if="['unloaded', 'error'].includes(rt.status)" class="btn btn-p btn-sm" @click="panel = 'load'">載入</button>
          <button v-if="rt.status === 'loaded'" class="btn btn-s btn-sm" @click="panel = 'unload'">卸載</button>
          <button v-if="rt.status === 'loading'" class="btn btn-s btn-sm" :disabled="busy" @click="doUnload('now')">取消載入</button>
        </div>
      </div>
      <p v-if="m.note" class="t13 ink2" style="margin: 0">{{ m.note }}</p>

      <div v-if="rt.status === 'loading'" class="progress-box"><div class="t13">{{ rt.stage || '載入中' }}…</div><div class="meter"><i style="width: 100%; opacity: 0.5"></i></div></div>
      <div v-if="m.download_status === 'downloading'" class="progress-box"><div class="row-between t13"><span>從 Hugging Face 下載中</span><span class="num">{{ m.download_progress }}%</span></div><div class="meter"><i :style="{ width: m.download_progress + '%' }"></i></div></div>
      <div v-if="m.download_status === 'failed'" class="notice notice-crit">下載失敗：{{ m.download_error }}</div>
      <div v-if="rt.status === 'error'" class="notice notice-crit"><span>{{ rt.error }}</span><button class="btn btn-s btn-xs" @click="showLog">看 worker log</button></div>
      <pre v-if="log" class="code log-box">{{ log }}</pre>

      <div v-if="panel === 'load' && ['unloaded', 'error'].includes(rt.status) && check" class="action-panel">
        <div class="ap-h"><strong>載入 <span class="mono">{{ m.api_name }}</span></strong><button class="ib" aria-label="關閉" @click="panel = null"><Icon n="x" :s="16" /></button></div>
        <p class="t13 ink2" style="margin: 0">預估需要 <b class="num">{{ fmtGB(check.need_mb) }} GB</b>：權重 {{ fmtGB(m.est_weights_mb) }} GB，加上 KV 快取預留 {{ fmtGB(m.est_kv_mb) }} GB。<span v-if="check.fake">沒有模型檔，會用假 worker 載入。</span></p>
        <ProjBar :model-id="m.id" :need="check.need_mb" :budget="budget" :runtimes="runtimes" />
        <ul class="checklist">
          <li :class="check.files_ready || check.fake ? 'ok' : 'bad'"><Icon :n="check.files_ready || check.fake ? 'check' : 'x'" :s="15" /><span>模型檔：{{ check.files_ready ? '已下載' : check.fake ? '沒有，改用假 worker' : '還沒下載' }}</span></li>
          <li :class="check.metal_ok ? 'ok' : 'bad'"><Icon :n="check.metal_ok ? 'check' : 'x'" :s="15" /><span>Metal 上限：載入後模型共 <b class="num">{{ fmtGB(check.metal_after_mb) }}</b> / {{ fmtGB(check.metal_limit_mb) }} GB</span></li>
          <li :class="check.phys_ok ? 'ok' : 'bad'"><Icon :n="check.phys_ok ? 'check' : 'x'" :s="15" /><span>實體記憶體：載入後剩 <b class="num">{{ fmtGB(check.phys_left_mb) }}</b> GB，至少要留 {{ fmtGB(check.headroom_mb) }} GB</span></li>
        </ul>
        <div v-if="!check.ok" class="notice notice-crit">
          <span>{{ check.reason }}，不能載入。</span>
          <template v-if="check.suggest"><span>先卸載 <b class="mono">{{ check.suggest.api_name }}</b>（約釋放 {{ fmtGB(check.suggest.mem_mb) }} GB）就放得下。</span><button class="btn btn-s btn-xs" @click="goUnload(check.suggest.model_id)">前往卸載</button></template>
        </div>
        <div class="ap-actions"><button class="btn btn-p btn-sm" :disabled="!check.ok || busy" @click="doLoad">確認載入</button><button class="btn btn-s btn-sm" @click="panel = null">取消</button></div>
      </div>

      <div v-if="panel === 'unload' && rt.status === 'loaded'" class="action-panel">
        <div class="ap-h"><strong>卸載 <span class="mono">{{ m.api_name }}</span></strong><button class="ib" aria-label="關閉" @click="panel = null"><Icon n="x" :s="16" /></button></div>
        <p class="t13 ink2" style="margin: 0">會結束 worker 行程並釋放約 {{ fmtGB(rt.mem_mb) }} GB。之後呼叫這個模型會收到 <code>503 model_not_loaded</code>，直到再次載入。</p>
        <div v-if="rt.active || rt.waiting" class="notice notice-warn">目前有 {{ rt.active }} 個請求處理中、{{ rt.waiting }} 個排隊。</div>
        <div class="ap-actions">
          <button class="btn btn-dp btn-sm" :disabled="busy" @click="doUnload('drain')">{{ rt.active || rt.waiting ? '處理完再卸載' : '確認卸載' }}</button>
          <button v-if="rt.active || rt.waiting" class="btn btn-d btn-sm" :disabled="busy" @click="doUnload('now')">立即卸載（中斷請求）</button>
          <button class="btn btn-s btn-sm" @click="panel = null">取消</button>
        </div>
      </div>

      <div>
        <div class="tabs">
          <button class="tab" :class="{ on: tab === 'runtime' }" @click="tab = 'runtime'">執行狀態</button>
          <button class="tab" :class="{ on: tab === 'config' }" @click="tab = 'config'">設定</button>
          <button class="tab" :class="{ on: tab === 'access' }" @click="tab = 'access'">開放對象 <span class="count">{{ access.filter((a) => a.on).length }}</span></button>
        </div>

        <div v-if="tab === 'runtime'" class="detail">
          <dl class="kv">
            <div><dt>內部位址</dt><dd class="mono">{{ rt.port ? '127.0.0.1:' + rt.port : '—' }}</dd></div>
            <div><dt>行程</dt><dd class="mono">{{ rt.pid ? 'PID ' + rt.pid : '沒有執行' }}</dd></div>
            <div><dt>載入時間</dt><dd>{{ rt.loaded_at ? relTime(new Date(rt.loaded_at * 1000).toISOString()) : '—' }}</dd></div>
            <div><dt>記憶體（目前 / 峰值）</dt><dd class="num">{{ fmtGB(rt.mem_mb) }} / {{ fmtGB(rt.peak_mb) }} GB</dd></div>
            <div><dt>處理中 / 排隊</dt><dd class="num">{{ rt.active || 0 }} / {{ rt.waiting || 0 }}（同時 {{ m.concurrency }}、佇列上限 {{ m.queue_max }}）</dd></div>
            <div v-if="m.capabilities.includes('chat')"><dt>輸出速度</dt><dd class="num">{{ rt.status === 'loaded' && rt.tps ? rt.tps + ' tok/s' : '—' }}</dd></div>
            <div><dt>首字延遲</dt><dd class="num">{{ rt.status === 'loaded' && rt.ttft_ms ? rt.ttft_ms + ' ms' : '—' }}</dd></div>
            <div><dt>下載</dt><dd>{{ DL[m.download_status] }}{{ m.size_bytes ? ' · ' + fmtGB(m.size_bytes / 1048576) + ' GB' : '' }}</dd></div>
            <div class="full"><dt>本機路徑</dt><dd class="mono t13">{{ m.local_path || data.model_dir + '/' + m.source_repo.split('/')[1] }}</dd></div>
          </dl>
          <div v-if="rt.status === 'unloaded'" class="notice notice-info">這個模型沒有載入。會員呼叫它會收到 503，要由管理者在這裡按「載入」。</div>
          <div v-if="auth.isSU" class="ap-actions">
            <button v-if="['not_downloaded', 'failed'].includes(m.download_status)" class="btn btn-s btn-sm" :disabled="busy || rt.status !== 'unloaded'" @click="doDownload"><Icon n="download" :s="15" />從 Hugging Face 下載</button>
            <template v-if="rt.status === 'unloaded' && m.download_status !== 'downloading'">
              <button v-if="!confirmDelete" class="btn btn-d btn-sm" @click="confirmDelete = true">刪除模型</button>
              <template v-else><span class="t13">會刪除登記與模型資料夾，不能復原。</span><button class="btn btn-dp btn-sm" @click="doDelete">確認刪除</button><button class="btn btn-s btn-sm" @click="confirmDelete = false">取消</button></template>
            </template>
          </div>
        </div>

        <div v-if="tab === 'config'" class="detail">
          <div v-if="!auth.isSU" class="lock-note"><Icon n="lock" :s="15" />只有 Superuser 能修改模型設定；管理員可以載入與卸載。</div>
          <div class="form-grid">
            <div class="field"><label for="mc-alias">別名</label><input id="mc-alias" v-model="draft.aliases" class="input mono" :class="{ changed: changed('aliases') }" :readonly="!auth.isSU" placeholder="例如 gpt-4o-mini" /><span class="hint">讓只認 OpenAI 模型名稱的工具也能用，逗號分隔。</span></div>
            <div class="field"><label for="mc-name">顯示名稱</label><input id="mc-name" v-model="draft.display_name" class="input" :class="{ changed: changed('display_name') }" :readonly="!auth.isSU" /></div>
            <div class="field"><label for="mc-ctx">上下文長度</label><input id="mc-ctx" v-model="draft.context_length" type="number" class="input num" :class="{ changed: changed('context_length') }" :readonly="!auth.isSU" /><span class="hint">越長 KV 快取預留越多，下次載入才生效。</span></div>
            <div v-if="m.capabilities.includes('chat')" class="field"><label for="mc-max">預設 max_tokens</label><input id="mc-max" v-model="draft.default_max_tokens" type="number" class="input num" :class="{ changed: changed('default_max_tokens') }" :readonly="!auth.isSU" /></div>
            <div class="field"><label for="mc-w">權重估計（MB）</label><input id="mc-w" v-model="draft.est_weights_mb" type="number" class="input num" :class="{ changed: changed('est_weights_mb') }" :readonly="!auth.isSU" /></div>
            <div class="field"><label for="mc-kv">KV 快取預留（MB）</label><input id="mc-kv" v-model="draft.est_kv_mb" type="number" class="input num" :class="{ changed: changed('est_kv_mb') }" :readonly="!auth.isSU" /></div>
            <div class="field"><label for="mc-conc">同時處理數</label><input id="mc-conc" v-model="draft.concurrency" type="number" class="input num" min="1" max="8" :class="{ changed: changed('concurrency') }" :readonly="!auth.isSU" /><span class="hint">MLX 一次跑一個推論，先維持 1。</span></div>
            <div class="field"><label for="mc-queue">佇列上限</label><input id="mc-queue" v-model="draft.queue_max" type="number" class="input num" :class="{ changed: changed('queue_max') }" :readonly="!auth.isSU" /><span class="hint">排滿時回 503 model_busy。</span></div>
            <div class="field full"><label for="mc-note">備註</label><input id="mc-note" v-model="draft.note" class="input" :class="{ changed: changed('note') }" :readonly="!auth.isSU" /></div>
            <div class="field full"><label class="switch" for="mc-en"><input id="mc-en" v-model="draft.is_enabled" type="checkbox" :disabled="!auth.isSU" />{{ draft.is_enabled ? '啟用中' : '已停用：會員看不到、也不能呼叫' }}</label></div>
          </div>
          <div v-if="dirty && auth.isSU" class="savebar"><span>有未儲存的變更（別名與上下文長度以外的設定，下次載入才生效）</span><button class="btn btn-s btn-sm" @click="reset">捨棄</button><button class="btn btn-p btn-sm" @click="save">儲存</button></div>
        </div>

        <div v-if="tab === 'access'" class="detail">
          <p class="t13 muted" style="margin: 0">哪些會員可以呼叫這個模型。在「會員」頁的帳號與上限調整。</p>
          <div class="scroll-x"><table class="tbl"><thead><tr><th>會員</th><th>狀態</th><th>可用</th><th></th></tr></thead>
            <tbody><tr v-for="a in access" :key="a.u.id"><td>{{ a.u.name }} <span class="t12 muted">{{ a.u.email }}</span></td><td><Pill :c="a.u.is_active ? 'good' : 'idle'" :t="a.u.is_active ? '啟用中' : '已停用'" /></td><td>{{ a.on ? '可以' : '—' }}</td><td class="r"><RouterLink class="btn btn-g btn-xs" :to="{ path: '/members', query: { id: a.u.id } }">前往設定</RouterLink></td></tr></tbody></table></div>
          <div v-if="!access.length" class="empty">還沒有會員。</div>
        </div>
      </div>
    </section>
  </div>
  <div v-else class="loading-line">載入中…</div>
</template>
