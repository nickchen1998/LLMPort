<script setup>
// 測試台：用登入身分呼叫跟 /v1 一樣的流程（會員的用量算自己的），右邊是對應的程式碼
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import Icon from '../components/Icon.vue'
import Pill from '../components/Pill.vue'
import { api, errorMessage } from '../api/client'
import { useAuth } from '../stores/auth'
import { toast } from '../stores/toast'
import { copyText } from '../composables/format'

const auth = useAuth()
const models = ref([])
const base = ref('')
const ep = ref('chat')
const model = ref('')
const lang = ref('python')
const out = ref(null)
const running = ref(false)
const codeEl = ref(null)
let abort = null

const CAP_OF = { chat: 'chat', embed: 'embedding', dec: 'decision' }
const choices = computed(() => models.value.filter((m) => m.capabilities.includes(CAP_OF[ep.value])))
const m = computed(() => models.value.find((x) => x.id === model.value))
const hasCap = (cap) => models.value.some((x) => x.capabilities.includes(cap))
function ensureModel() {
  if (!choices.value.some((x) => x.id === model.value)) model.value = (choices.value.find((x) => x.loaded) || choices.value[0])?.id || ''
}
onMounted(async () => {
  const [list, cfg] = await Promise.all([api('/api/playground/models'), api('/api/public-config')])
  models.value = list.data
  base.value = cfg.public_api_base
  ensureModel()
})
onBeforeUnmount(() => abort?.abort())
watch(ep, () => { abort?.abort(); out.value = null; ensureModel(); if (ep.value === 'dec') lang.value = 'curl' })

const chat = reactive({ system: '你是 LLMPort 上的助理，用繁體中文簡潔回答。', user: '用三點說明在自己的 Mac mini 上部署模型的好處。', image: '', temperature: 0.7, maxTokens: 512 })
const embed = reactive({ input: 'Mac mini 的統一記憶體有多大？\n如何設定 Cloudflare Tunnel？' })
const dec = reactive({
  input: '訂單 #A1029 上週就扣款了，到現在還沒出貨，客服電話也打不通，請直接幫我退款！',
  questions: [
    { type: 'predicate', name: 'wants_refund', instructions: '使用者是否要求退款', options: '' },
    { type: 'choice', name: 'department', instructions: '這張單應該分給哪個部門', options: 'billing:帳務與退款, shipping:物流出貨, technical:技術問題, account:帳號登入' },
    { type: 'score', name: 'urgency', instructions: '這張單有多急', options: '低, 中, 高, 緊急' },
  ],
})
const parseOpts = (s) => (s || '').split(/[,，、]/).map((x) => x.trim()).filter(Boolean).map((x) => { const [v, d] = x.split(/[:：]/); return { value: v.trim(), description: (d || '').trim() } })

function chatBody(stream) {
  const content = chat.image ? [{ type: 'text', text: chat.user }, { type: 'image_url', image_url: { url: chat.image } }] : chat.user
  return { model: model.value, messages: [{ role: 'system', content: chat.system }, { role: 'user', content }], temperature: Number(chat.temperature), max_tokens: Number(chat.maxTokens), stream, ...(stream ? { stream_options: { include_usage: true } } : {}) }
}
const decBody = () => ({
  model: model.value, input: dec.input,
  questions: dec.questions.map((q) => {
    const o = { type: q.type, name: q.name || null, instructions: q.instructions }
    if (q.type === 'choice') o.choices = parseOpts(q.options).map((p) => (p.description ? p : { value: p.value }))
    if (q.type === 'score') o.levels = parseOpts(q.options).map((p) => ({ label: p.value }))
    return o
  }),
})
const embedBody = () => ({ model: model.value, input: embed.input.split('\n').map((s) => s.trim()).filter(Boolean) })

function onImage(e) {
  const file = e.target.files?.[0]
  if (!file) { chat.image = ''; return }
  const reader = new FileReader()
  reader.onload = () => { chat.image = reader.result }
  reader.readAsDataURL(file)
}

async function run() {
  if (!model.value) return
  abort?.abort()
  abort = new AbortController()
  running.value = true
  const t0 = performance.now()
  try {
    if (ep.value === 'chat') {
      out.value = { kind: 'chat', text: '', usage: null, ttft: null, done: false }
      const res = await fetch('/api/playground/chat/completions', { method: 'POST', signal: abort.signal, headers: { Authorization: `Bearer ${auth.token}`, 'Content-Type': 'application/json' }, body: JSON.stringify(chatBody(true)) })
      if (!res.ok) { const text = await res.text(); out.value = { kind: 'error', status: res.status, body: pretty(text) }; return }
      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buf = ''
      for (;;) {
        const { value, done } = await reader.read()
        if (done) break
        buf += decoder.decode(value, { stream: true })
        let idx
        while ((idx = buf.indexOf('\n\n')) >= 0) {
          const line = buf.slice(0, idx).trim()
          buf = buf.slice(idx + 2)
          if (!line.startsWith('data: ')) continue
          const payload = line.slice(6)
          if (payload === '[DONE]') continue
          const chunk = JSON.parse(payload)
          if (chunk.error) { out.value = { kind: 'error', status: 502, body: JSON.stringify(chunk, null, 2) }; return }
          const delta = chunk.choices?.[0]?.delta?.content
          if (delta) { if (out.value.ttft == null) out.value.ttft = Math.round(performance.now() - t0); out.value.text += delta }
          if (chunk.usage) out.value.usage = chunk.usage
        }
      }
      out.value.done = true
      out.value.ms = Math.round(performance.now() - t0)
    } else if (ep.value === 'embed') {
      const r = await api('/api/playground/embeddings', { method: 'POST', body: embedBody() })
      out.value = { kind: 'embed', data: r.data, usage: r.usage, ms: Math.round(performance.now() - t0) }
    } else {
      const r = await api('/api/playground/decisions', { method: 'POST', body: decBody() })
      out.value = { kind: 'dec', answers: r.answers, usage: r.usage, ms: Math.round(performance.now() - t0) }
    }
  } catch (e) {
    if (e.name === 'AbortError') return
    out.value = { kind: 'error', status: e.status || 0, body: e.body ? JSON.stringify(e.body, null, 2) : e.message }
  } finally {
    running.value = false
  }
}
function pretty(text) { try { return JSON.stringify(JSON.parse(text), null, 2) } catch { return text || errorMessage(null, 0) } }

const code = computed(() => {
  const B = base.value
  if (ep.value === 'chat') {
    const body = chatBody(true)
    if (chat.image) body.messages[1].content[1].image_url.url = 'data:image/jpeg;base64,...'
    if (lang.value === 'python') {
      return `from openai import OpenAI\n\nclient = OpenAI(base_url="${B}", api_key="sk-lp-...")\n\nstream = client.chat.completions.create(\n    model="${model.value}",\n    messages=${JSON.stringify(body.messages, null, 4).replace(/\n/g, '\n    ')},\n    temperature=${chat.temperature},\n    max_tokens=${chat.maxTokens},\n    stream=True,\n    stream_options={"include_usage": True},\n)\nfor chunk in stream:\n    if chunk.choices:\n        print(chunk.choices[0].delta.content or "", end="")\n    if chunk.usage:\n        print("\\n", chunk.usage)`
    }
    return `curl ${B}/chat/completions \\\n  -H "Authorization: Bearer $LLMPORT_KEY" \\\n  -H "Content-Type: application/json" \\\n  -d '${JSON.stringify(body, null, 2)}'`
  }
  if (ep.value === 'embed') {
    const body = embedBody()
    if (lang.value === 'python') return `from openai import OpenAI\n\nclient = OpenAI(base_url="${B}", api_key="sk-lp-...")\n\nresp = client.embeddings.create(\n    model="${model.value}",\n    input=${JSON.stringify(body.input, null, 4).replace(/\n/g, '\n    ')},\n)\nprint(len(resp.data), len(resp.data[0].embedding), resp.usage)`
    return `curl ${B}/embeddings \\\n  -H "Authorization: Bearer $LLMPORT_KEY" \\\n  -H "Content-Type: application/json" \\\n  -d '${JSON.stringify(body, null, 2)}'`
  }
  if (lang.value === 'python') return `import os, httpx\n\nresp = httpx.post(\n    "${B}/decisions",\n    headers={"Authorization": "Bearer " + os.environ["LLMPORT_KEY"]},\n    json=${JSON.stringify(decBody(), null, 4).replace(/\n/g, '\n    ')},\n)\nfor answer in resp.json()["answers"]:\n    print(answer)`
  return `curl ${B}/decisions \\\n  -H "Authorization: Bearer $LLMPORT_KEY" \\\n  -H "Content-Type: application/json" \\\n  -d '${JSON.stringify(decBody(), null, 2)}'`
})
async function copyCode() { toast((await copyText(code.value, codeEl.value)) ? '已複製到剪貼簿' : '已選取文字，請按 ⌘C 複製') }
const hit = (a, p) => (a.type === 'choice' ? p.value === a.choice : p.probability === Math.max(...a.probabilities.map((x) => x.probability)))
</script>

<template>
  <div class="pg">
    <section class="card pg-main">
      <div class="tabs" style="margin-bottom: 0">
        <button class="tab" :class="{ on: ep === 'chat' }" @click="ep = 'chat'">對話 · 視覺</button>
        <button v-if="hasCap('embedding')" class="tab" :class="{ on: ep === 'embed' }" @click="ep = 'embed'">嵌入</button>
        <button v-if="hasCap('decision')" class="tab" :class="{ on: ep === 'dec' }" @click="ep = 'dec'">決策</button>
      </div>
      <div class="field"><label for="pg-model">模型</label>
        <select id="pg-model" v-model="model" class="input"><option v-for="x in choices" :key="x.id" :value="x.id">{{ x.id }}{{ x.loaded ? '' : '（未載入）' }}</option></select>
        <span v-if="m && !m.loaded" class="hint">這個模型沒有載入，送出會收到 503 model_not_loaded。</span>
        <span v-if="!choices.length" class="hint">沒有可以用的模型，請找管理者開放。</span></div>

      <template v-if="ep === 'chat'">
        <div class="field"><label for="pg-sys">System</label><textarea id="pg-sys" v-model="chat.system" class="input" rows="2"></textarea></div>
        <div class="field"><label for="pg-user">User</label><textarea id="pg-user" v-model="chat.user" class="input" rows="3"></textarea></div>
        <div class="checks-inline">
          <label class="t13" for="pg-img">附圖片 <input id="pg-img" type="file" accept="image/*" :disabled="!m?.capabilities.includes('vision')" @change="onImage" /></label>
          <label class="t13" for="pg-temp">temperature <input id="pg-temp" v-model.number="chat.temperature" type="number" class="input input-sm num" style="width: 76px" step="0.1" min="0" max="2" /></label>
          <label class="t13" for="pg-max">max_tokens <input id="pg-max" v-model.number="chat.maxTokens" type="number" class="input input-sm num" style="width: 88px" /></label>
        </div>
        <span v-if="m && !m.capabilities.includes('vision')" class="hint">{{ m.id }} 不支援圖片。</span>
      </template>

      <template v-if="ep === 'embed'">
        <div class="field"><label for="pg-embed">input（一行一筆）</label><textarea id="pg-embed" v-model="embed.input" class="input" rows="4"></textarea></div>
      </template>

      <template v-if="ep === 'dec'">
        <div class="field"><label for="pg-dec">input</label><textarea id="pg-dec" v-model="dec.input" class="input" rows="3"></textarea><span class="hint">決策 API 不產生文字，只回每個問題的機率（OpenAI Decisions／Jev 類型）。</span></div>
        <div v-for="(q, i) in dec.questions" :key="i" class="q">
          <div class="q-h">
            <select :id="'qt' + i" v-model="q.type" class="input input-sm" aria-label="問題類型"><option value="predicate">predicate 是非</option><option value="choice">choice 選一個</option><option value="score">score 分級</option></select>
            <input :id="'qn' + i" v-model="q.name" class="input input-sm mono" aria-label="問題名稱" />
            <button class="ib" aria-label="刪除問題" @click="dec.questions.splice(i, 1)"><Icon n="x" :s="15" /></button>
          </div>
          <input :id="'qi' + i" v-model="q.instructions" class="input" placeholder="問題說明" aria-label="問題說明" />
          <input v-if="q.type !== 'predicate'" :id="'qo' + i" v-model="q.options" class="input" :placeholder="q.type === 'choice' ? '值:說明, 值:說明' : '由低到高：低, 中, 高'" :aria-label="q.type === 'choice' ? '選項' : '等級'" />
        </div>
        <div><button class="btn btn-s btn-sm" :disabled="dec.questions.length >= 10" @click="dec.questions.push({ type: 'predicate', name: 'q' + (dec.questions.length + 1), instructions: '', options: '' })"><Icon n="plus" :s="15" />新增問題</button></div>
      </template>

      <div class="ap-actions"><button class="btn btn-p" :disabled="running || !model" @click="run">{{ running ? '處理中…' : '送出' }}</button><span class="t12 muted">{{ auth.isMember ? '用你的帳號呼叫，會算進你的本月用量。' : '以後台身分呼叫，記在測試台，不算任何會員的配額。' }}</span></div>

      <div v-if="out" class="out" aria-live="polite">
        <template v-if="out.kind === 'error'"><Pill c="crit" :t="`HTTP ${out.status}`" /><pre class="code">{{ out.body }}</pre></template>
        <template v-if="out.kind === 'chat'">
          <div class="out-text">{{ out.text }}<span v-if="!out.done" class="caret"></span></div>
          <div class="usage-row"><span v-if="out.ttft != null">首字 <b>{{ out.ttft }} ms</b></span><template v-if="out.usage"><span>prompt_tokens <b>{{ out.usage.prompt_tokens }}</b></span><span>completion_tokens <b>{{ out.usage.completion_tokens }}</b></span></template><span v-if="out.done">耗時 <b>{{ out.ms }} ms</b></span></div>
        </template>
        <template v-if="out.kind === 'embed'">
          <div v-for="it in out.data" :key="it.index" class="ans"><div class="vec">[{{ it.index }}] [{{ it.embedding.slice(0, 6).map((v) => v.toFixed(4)).join(', ') }}, … 共 {{ it.embedding.length }} 維]</div></div>
          <div class="usage-row"><span>prompt_tokens <b>{{ out.usage.prompt_tokens }}</b></span><span>耗時 <b>{{ out.ms }} ms</b></span></div>
        </template>
        <template v-if="out.kind === 'dec'">
          <div v-for="(a, i) in out.answers" :key="i" class="ans">
            <div class="ans-h"><span class="mono strong">{{ a.name || '#' + (i + 1) }}</span><span class="cap">{{ a.type }}</span>
              <span v-if="a.type === 'choice'" class="t13">選 <b class="mono">{{ a.choice }}</b> · confidence {{ a.confidence.toFixed(2) }}</span>
              <span v-if="a.type === 'score'" class="t13">score <b class="num">{{ a.score.toFixed(2) }}</b> · confidence {{ a.confidence.toFixed(2) }}</span></div>
            <div v-if="a.type === 'predicate'" class="pbar-row hit"><span>是</span><span class="pbar"><i :style="{ width: a.probability * 100 + '%' }"></i></span><b>{{ a.probability.toFixed(2) }}</b></div>
            <template v-if="a.probabilities"><div v-for="p in a.probabilities" :key="String(p.value)" class="pbar-row" :class="{ hit: hit(a, p) }"><span class="ell">{{ p.label !== undefined ? p.value + ' · ' + p.label : p.value }}</span><span class="pbar"><i :style="{ width: p.probability * 100 + '%' }"></i></span><b>{{ p.probability.toFixed(2) }}</b></div></template>
          </div>
          <div class="usage-row"><span>input_tokens <b>{{ out.usage.input_tokens }}</b></span><span>output_tokens <b>0</b></span><span>耗時 <b>{{ out.ms }} ms</b></span></div>
        </template>
      </div>
    </section>
    <section class="card pg-code">
      <div class="card-h"><h2>呼叫方式</h2><div class="seg ml-auto" role="group" aria-label="語言"><button :class="{ on: lang === 'python' }" @click="lang = 'python'">Python</button><button :class="{ on: lang === 'curl' }" @click="lang = 'curl'">curl</button></div></div>
      <pre ref="codeEl" class="code">{{ code }}</pre>
      <div class="ap-actions"><button class="btn btn-s btn-sm" @click="copyCode"><Icon n="copy" :s="15" />複製</button><span class="t12 muted">{{ auth.isMember ? '把 sk-lp-... 換成你在 API Keys 建立的金鑰。' : '把金鑰換成會員自己的。' }}</span></div>
    </section>
  </div>
</template>
