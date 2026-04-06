<template>
  <div class="app-shell">
    <aside class="app-sidebar">
      <AppSidebar />
    </aside>
    <main class="app-main">
      <router-view v-slot="{ Component }">
        <keep-alive>
          <component :is="Component" />
        </keep-alive>
      </router-view>
    </main>
    <!-- 新手引导：首次使用自动弹出 -->
    <OnboardingGuide />
  </div>
</template>

<script setup lang="ts">
import AppSidebar from '@/components/layout/AppSidebar.vue'
import OnboardingGuide from '@/components/OnboardingGuide.vue'
</script>

<style scoped>
.app-shell {
  display: flex;
  height: 100vh;
  background: var(--c-bg);
}
.app-sidebar {
  width: var(--sidebar-w);
  min-width: var(--sidebar-w);
  background: var(--c-bg-elevated);
  border-right: 1px solid var(--c-border);
  display: flex;
  flex-direction: column;
}
.app-main {
  flex: 1;
  overflow: hidden;
  background: var(--c-bg);
}

@media (max-width: 768px) {
  .app-sidebar {
    width: 60px;
    min-width: 60px;
  }
}
</style>
