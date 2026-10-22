// 側欄順序、圖示與誰能進（meta.roles）；meta.group 'manage' 放在「管理中心」，其餘在「服務中心」
const ADMINS = ['superuser', 'admin']
const EVERYONE = ['superuser', 'admin', 'member']

export const shellRoutes = [
  { path: '/dashboard', component: () => import('../views/OverviewView.vue'), meta: { title: '總覽', icon: 'grid', roles: EVERYONE } },
  { path: '/keys', component: () => import('../views/member/MyKeysView.vue'), meta: { title: '金鑰管理', icon: 'key', roles: EVERYONE } },
  { path: '/requests', component: () => import('../views/RequestsView.vue'), meta: { title: '請求紀錄', icon: 'list', roles: EVERYONE } },
  { path: '/playground', component: () => import('../views/PlaygroundView.vue'), meta: { title: '請求測試', icon: 'play', roles: EVERYONE } },
  { path: '/models', component: () => import('../views/admin/ModelsView.vue'), meta: { group: 'manage', title: '模型管理', icon: 'chip', roles: ADMINS, lock: true } },
  { path: '/accounts', component: () => import('../views/admin/AccountsView.vue'), meta: { group: 'manage', title: '帳號管理', icon: 'users', roles: ADMINS, lock: true } },
  { path: '/usage', component: () => import('../views/AllUsageView.vue'), meta: { group: 'manage', title: '用量統計', icon: 'bars', roles: ADMINS, lock: true } },
  { path: '/monitor', component: () => import('../views/admin/MonitorView.vue'), meta: { group: 'manage', title: '系統監控', icon: 'pulse', roles: ADMINS, lock: true } },
]
