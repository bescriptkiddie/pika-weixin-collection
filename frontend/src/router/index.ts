// ─────────────────────────────────────────────────────────────────────────────
// 路由配置
// 定义 URL 路径和页面组件的对应关系。
// 使用 Hash 模式（URL 中带 #），无需服务器配置，适合本地静态部署。
// ─────────────────────────────────────────────────────────────────────────────

import { createRouter, createWebHashHistory } from 'vue-router'
import FeedView from '@/views/FeedView.vue'
import ConfigView from '@/views/ConfigView.vue'
import LogView from '@/views/LogView.vue'
import StatsView from '@/views/StatsView.vue'
import UnifiedContentView from '@/views/UnifiedContentView.vue'
import SourcesView from '@/views/SourcesView.vue'
import ContentLoopView from '@/views/ContentLoopView.vue'

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    {
      path: '/',
      name: 'home',
      component: UnifiedContentView,
    },
    {
      path: '/feed',
      name: 'feed',
      component: FeedView,
    },
    {
      path: '/sources',
      name: 'sources',
      component: SourcesView,
    },
    {
      path: '/loop',
      name: 'content-loop',
      component: ContentLoopView,
    },
    {
      path: '/stats',
      name: 'stats',
      component: StatsView,
    },
    {
      path: '/config',
      name: 'config',
      component: ConfigView,
    },
    {
      path: '/logs',
      name: 'logs',
      component: LogView,
    },
  ],
})

export default router
