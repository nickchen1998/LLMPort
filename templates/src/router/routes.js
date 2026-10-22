// 側欄順序、圖示與誰能進（meta.roles）
const ADMINS = ['superuser', 'admin']
const EVERYONE = ['superuser', 'admin', 'member']

export const shellRoutes = [
  { path: '/dashboard', component: () => import('../views/admin/DashboardView.vue'), meta: { title: '總覽', icon: 'grid', roles: ADMINS } },
  { path: '/models', component: () => import('../views/admin/ModelsView.vue'), meta: { title: '模型', icon: 'chip', roles: ADMINS } },
  { path: '/members', component: () => import('../views/admin/MembersView.vue'), meta: { title: '會員', icon: 'users', roles: ADMINS } },
  { path: '/my', component: () => import('../views/member/MyHomeView.vue'), meta: { title: '我的總覽', icon: 'grid', roles: ['member'] } },
  { path: '/keys', component: () => import('../views/member/MyKeysView.vue'), meta: { title: 'API Keys', icon: 'key', roles: ['member'] } },
  { path: '/usage', component: () => import('../views/UsageView.vue'), meta: { title: '用量統計', icon: 'bars', roles: EVERYONE } },
  { path: '/requests', component: () => import('../views/RequestsView.vue'), meta: { title: '請求紀錄', icon: 'list', roles: EVERYONE } },
  { path: '/monitor', component: () => import('../views/admin/MonitorView.vue'), meta: { title: '系統監控', icon: 'pulse', roles: ADMINS } },
  { path: '/playground', component: () => import('../views/PlaygroundView.vue'), meta: { title: '測試台', icon: 'play', roles: EVERYONE } },
  { path: '/quickstart', component: () => import('../views/member/QuickstartView.vue'), meta: { title: '串接說明', icon: 'code', roles: ['member'] } },
  { path: '/account', component: () => import('../views/member/MyAccountView.vue'), meta: { title: '帳號設定', icon: 'user', roles: ['member'] } },
  { path: '/admins', component: () => import('../views/admin/AdminsView.vue'), meta: { title: '後台帳號', icon: 'shield', roles: ['superuser'], lock: true } },
  { path: '/settings', component: () => import('../views/admin/SettingsView.vue'), meta: { title: '系統設定', icon: 'gear', roles: ['superuser'], lock: true } },
]
