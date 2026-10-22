<script setup>
import { computed, onMounted, ref } from 'vue'
import Icon from '../../components/Icon.vue'
import Pill from '../../components/Pill.vue'
import { api } from '../../api/client'
import { toast } from '../../stores/toast'
import { CAP, copyText } from '../../composables/format'

const base = ref('')
const models = ref([])
const baseEl = ref(null)
onMounted(async () => {
  const [cfg, ms] = await Promise.all([api('/api/public-config'), api('/api/me/models')])
  base.value = cfg.public_api_base
  models.value = ms
})
const epOf = (x) => (x.capabilities.includes('embedding') ? '/v1/embeddings' : '/v1/chat/completions' + (x.capabilities.includes('decision') ? '、/v1/decisions' : ''))
const chatModel = computed(() => (models.value.find((x) => x.capabilities.includes('chat')) || { api_name: 'qwen3-4b' }).api_name)
const py = computed(() => `from openai import OpenAI\n\nclient = OpenAI(\n    base_url="${base.value}",\n    api_key="sk-lp-...",   # 在 API Keys 建立的金鑰\n)\n\nresp = client.chat.completions.create(\n    model="${chatModel.value}",\n    messages=[{"role": "user", "content": "你好"}],\n)\nprint(resp.choices[0].message.content)\nprint(resp.usage)`)
const curl = computed(() => `# 列出這把金鑰能用的模型\ncurl ${base.value}/models \\\n  -H "Authorization: Bearer $LLMPORT_KEY"`)
const ERRS = [
  ['401', 'invalid_api_key', '金鑰打錯，或已經撤銷'],
  ['403', 'key_disabled', '金鑰過期，或帳號被停用'],
  ['404', 'model_not_found', 'model 名稱打錯，或這把金鑰沒有開放這個模型'],
  ['429', 'rate_limit_exceeded', '超過這把金鑰的每分鐘請求數，稍等再試'],
  ['429', 'insufficient_quota', '本月用量用完，請找管理者'],
  ['503', 'model_not_loaded', '模型暫停中（管理者沒有載入），請找管理者'],
  ['524', '—', '非串流的回答超過約 100 秒，長回答請用 stream=True'],
]
async function copyBase() { toast((await copyText(base.value, baseEl.value)) ? '已複製到剪貼簿' : '已選取文字，請按 ⌘C 複製') }
</script>

<template>
  <div class="page prose" style="max-width: 960px">
    <p class="lead">LLMPort 的 API 跟 OpenAI 相容。你的系統如果已經能接 OpenAI，只要換掉網址和金鑰。</p>
    <section class="card detail">
      <div class="label">API 網址（base_url）</div>
      <div class="keybox"><code ref="baseEl">{{ base }}</code><button class="btn btn-s btn-sm" @click="copyBase"><Icon n="copy" :s="15" />複製</button></div>
      <ol>
        <li>到「API Keys」建立一把金鑰，每個系統各用一把。</li>
        <li>在你的系統把 OpenAI 的 base_url 換成上面的網址，api_key 換成剛建立的金鑰。</li>
        <li>model 欄位填下表的名稱。</li>
      </ol>
    </section>
    <h2>你可以使用的模型</h2>
    <div class="scroll-x"><table class="tbl"><thead><tr><th>model</th><th>能力</th><th>端點</th><th>現在</th></tr></thead>
      <tbody><tr v-for="x in models" :key="x.id"><td class="mono">{{ x.api_name }}</td><td><span class="caps"><span v-for="c in x.capabilities" :key="c" class="cap">{{ CAP[c] }}</span></span></td><td class="mono t12">{{ epOf(x) }}</td><td><Pill :c="x.available ? 'good' : 'idle'" :t="x.available ? '可以使用' : '暫停中'" /></td></tr></tbody></table></div>
    <div v-if="!models.length" class="empty">管理者還沒有開放模型給你。</div>
    <h2>範例</h2>
    <pre class="code">{{ py }}</pre>
    <pre class="code">{{ curl }}</pre>
    <h2>常見錯誤</h2>
    <div class="scroll-x"><table class="tbl"><thead><tr><th>HTTP</th><th>code</th><th>怎麼辦</th></tr></thead>
      <tbody><tr v-for="e in ERRS" :key="e[1] + e[0]"><td class="num">{{ e[0] }}</td><td class="mono t13">{{ e[1] }}</td><td class="wrap t13">{{ e[2] }}</td></tr></tbody></table></div>
    <div><RouterLink to="/playground" class="btn btn-s btn-sm"><Icon n="play" :s="15" />到測試台試試看</RouterLink></div>
  </div>
</template>
