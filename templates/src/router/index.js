import { createRouter, createWebHistory } from 'vue-router'
import { useAuth } from '../stores/auth'
import AppShell from '../components/AppShell.vue'
import { shellRoutes } from './routes'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', component: () => import('../views/LoginView.vue'), meta: { public: true } },
    { path: '/change-password', component: () => import('../views/ChangePasswordView.vue') },
    { path: '/', component: AppShell, children: [{ path: '', redirect: () => useAuth().home }, ...shellRoutes] },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

router.beforeEach(async (to) => {
  const auth = useAuth()
  if (to.meta.public) return true
  if (!auth.token) return { path: '/login', query: to.fullPath !== '/' ? { next: to.fullPath } : {} }
  if (!auth.user) {
    try {
      await auth.fetchMe()
    } catch {
      auth.logout()
      return '/login'
    }
  }
  if (auth.user.must_change_password && to.path !== '/change-password') return '/change-password'
  if (to.meta.roles && !to.meta.roles.includes(auth.role)) return auth.home
  return true
})

export default router
