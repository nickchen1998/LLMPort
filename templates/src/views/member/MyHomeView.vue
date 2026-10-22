<script setup>
import { computed, onMounted, ref } from 'vue'
import Pill from '../../components/Pill.vue'
import { api } from '../../api/client'
import { CAP, fmtInt, fmtTime, fmtTok, modelColor, pct, relTime, stc } from '../../composables/format'

const s = ref(null)
const keys = ref([])
const recent = ref([])
onMounted(async () => {
  const [summary, k, r] = await Promise.all([api('/api/me/summary'), api('/api/me/keys'), api('/api/me/requests?limit=6')])
  s.value = summary
  keys.value = k.filter((x) => !x.revoked_at)
  recent.value = r
})
const ratio = computed(() => (s.value?.monthly_token_quota ? s.value.month_used / s.value.monthly_token_quota : 0))
const projected = computed(() => {
  if (!s.value) return 0
  const now = new Date()
  const days = new Date(now.getFullYear(), now.getMonth() + 1, 0).getDate()
  const elapsed = now.getDate() - 1 + now.getHours() / 24
  return elapsed > 0.5 ? (s.value.month_used / elapsed) * days : s.value.month_used
})
</script>

<template>
  <div v-if="s" class="page">
    <section class="card hero">
      <div class="hero-l">
        <div class="eyebrow">本月用量</div>
        <div class="hero-num num">{{ fmtTok(s.month_used) }}<span>/ {{ s.monthly_token_quota ? fmtTok(s.monthly_token_quota) : '不限' }}</span></div>
        <div v-if="s.monthly_token_quota" class="meter" :class="ratio > 0.9 ? 'crit' : ratio > 0.75 ? 'warn' : ''"><i :style="{ width: pct(ratio) }"></i></div>
        <p class="t13 muted" style="margin: 0">所有金鑰合計，每月 1 日歸零。照目前的速度，月底大約用到 {{ fmtTok(projected) }}。用完之後呼叫會回 429，請找管理者調整上限。</p>
      </div>
      <div class="hero-r">
        <div class="label">你可以使用的模型</div>
        <div v-for="x in s.models" :key="x.id" class="mstat" style="grid-template-columns: auto minmax(0, 1fr) auto">
          <span class="sw" :style="{ background: modelColor(x.id) }"></span>
          <div class="mstat-main"><span class="mono strong ell">{{ x.api_name }}</span><span class="caps"><span v-for="c in x.capabilities" :key="c" class="cap">{{ CAP[c] }}</span></span><span v-if="!x.available" class="t12 muted">管理者目前沒有載入，現在呼叫會回 503</span></div>
          <Pill :c="x.available ? 'good' : 'idle'" :t="x.available ? '可以使用' : '暫停中'" />
        </div>
        <div v-if="!s.models.length" class="empty">管理者還沒有開放模型給你。</div>
        <p class="t12 muted" style="margin: 0">模型的載入與卸載由管理者負責；需要其他模型請找管理者開放。</p>
      </div>
    </section>
    <section class="tiles">
      <div class="card tile"><div class="label">今日 Token</div><div class="tile-v num">{{ fmtTok(s.today.prompt_tokens + s.today.completion_tokens) }}</div><div class="t12 muted">輸入 {{ fmtTok(s.today.prompt_tokens) }} · 輸出 {{ fmtTok(s.today.completion_tokens) }}</div></div>
      <div class="card tile"><div class="label">今日請求</div><div class="tile-v num">{{ fmtInt(s.today.requests) }}</div><div class="t12 muted">其中錯誤 {{ s.today.errors }} 筆</div></div>
      <div class="card tile"><div class="label">有效金鑰</div><div class="tile-v num">{{ s.active_keys }}<small>/ {{ s.max_keys }}</small></div><div class="t12 muted">每個系統各用一把</div></div>
      <div class="card tile"><div class="label">每分鐘請求上限</div><div class="tile-v num">{{ s.rpm_limit }}<small>次</small></div><div class="t12 muted">每把金鑰各自計算，由管理者設定</div></div>
    </section>
    <section class="grid-2">
      <div class="card">
        <div class="card-h"><h2>我的金鑰</h2><RouterLink to="/keys" class="btn btn-g btn-sm ml-auto">管理金鑰</RouterLink></div>
        <div v-for="k in keys" :key="k.id" class="mstat" style="grid-template-columns: minmax(0, 1fr) auto">
          <div class="mstat-main"><span class="strong">{{ k.name }}</span><span class="mono t12 muted">{{ k.masked }}</span></div>
          <div class="mstat-num t13 num">本月 {{ fmtTok(k.month_tokens) }}<div class="t12 muted">最後使用 {{ relTime(k.last_used_at) }}</div></div>
        </div>
        <div v-if="!keys.length" class="empty">還沒有金鑰。<RouterLink to="/keys">建立第一把</RouterLink></div>
      </div>
      <div class="card">
        <div class="card-h"><h2>最近請求</h2><RouterLink to="/requests" class="btn btn-g btn-sm ml-auto">全部紀錄</RouterLink></div>
        <div class="scroll-x"><table class="tbl"><thead><tr><th>時間</th><th>金鑰</th><th>模型</th><th>狀態</th><th class="r">Token</th></tr></thead>
          <tbody><tr v-for="r in recent" :key="r.id"><td class="num muted">{{ fmtTime(r.created_at) }}</td><td>{{ r.key_name || '—' }}</td><td class="mono t12">{{ r.model }}</td><td><Pill :c="stc(r.status_code)" :t="String(r.status_code)" /></td><td class="r">{{ r.status_code < 400 ? fmtInt(r.prompt_tokens + r.completion_tokens) : '—' }}</td></tr></tbody></table></div>
        <div v-if="!recent.length" class="empty">最近沒有請求。</div>
      </div>
    </section>
  </div>
  <div v-else class="loading-line">載入中…</div>
</template>
