import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'chat',
      component: () => import('@/views/ChatView.vue'),
      meta: { title: '知识库问答', icon: 'ChatDotRound' },
    },
    {
      path: '/bid',
      name: 'bid',
      component: () => import('@/views/BidAssistant.vue'),
      meta: { title: '标书助手', icon: 'Document' },
    },
    {
      path: '/solution',
      name: 'solution',
      component: () => import('@/views/SolutionAssistant.vue'),
      meta: { title: '方案助手', icon: 'EditPen' },
    },
    {
      path: '/knowledge',
      name: 'knowledge',
      component: () => import('@/views/KnowledgeBase.vue'),
      meta: { title: '知识库构建', icon: 'FolderOpened' },
    },
    {
      path: '/overview',
      name: 'overview',
      component: () => import('@/views/Overview.vue'),
      meta: { title: '系统总览', icon: 'DataAnalysis' },
    },
    {
      path: '/browser',
      name: 'browser',
      component: () => import('@/views/DataBrowser.vue'),
      meta: { title: '数据浏览', icon: 'Search' },
    },
    {
      path: '/ingest',
      name: 'ingest',
      component: () => import('@/views/IngestManager.vue'),
      meta: { title: '摄取管理', icon: 'Download' },
    },
    {
      path: '/eval',
      name: 'eval',
      component: () => import('@/views/EvalPanel.vue'),
      meta: { title: '评估面板', icon: 'TrendCharts' },
    },
    {
      path: '/config',
      name: 'config',
      component: () => import('@/views/SystemConfig.vue'),
      meta: { title: '系统配置', icon: 'Setting' },
    },
  ],
})

router.beforeEach((to) => {
  document.title = `${to.meta.title || '九洲 RAG'} - 九洲 RAG 管理平台`
})

export default router
