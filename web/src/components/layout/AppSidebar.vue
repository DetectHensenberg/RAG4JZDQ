<template>
  <div class="sidebar">
    <!-- Brand -->
    <div class="brand">
      <div class="brand-mark">J</div>
      <div class="brand-text">
        <span class="brand-name">九洲 RAG</span>
        <span class="brand-sub">知识管理平台</span>
      </div>
    </div>

    <!-- Navigation -->
    <nav class="nav">
      <div class="nav-section-label">主功能</div>
      <router-link
        v-for="item in mainItems"
        :key="item.path"
        :to="item.path"
        class="nav-item"
        :class="{ active: currentRoute === item.path }"
      >
        <el-icon :size="16"><component :is="item.icon" /></el-icon>
        <span>{{ item.title }}</span>
      </router-link>

      <div class="nav-section-label">系统</div>
      <router-link
        v-for="item in systemItems"
        :key="item.path"
        :to="item.path"
        class="nav-item"
        :class="{ active: currentRoute === item.path }"
      >
        <el-icon :size="16"><component :is="item.icon" /></el-icon>
        <span>{{ item.title }}</span>
      </router-link>
    </nav>

    <!-- Footer -->
    <div class="sidebar-footer">
      <span>v1.0</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import {
  ChatDotRound,
  FolderOpened,
  DataAnalysis,
  Search,
  Download,
  TrendCharts,
  Setting,
} from '@element-plus/icons-vue'

const route = useRoute()
const currentRoute = computed(() => route.path)

const mainItems = [
  { path: '/', title: '知识问答', icon: ChatDotRound },
  { path: '/knowledge', title: '知识库构建', icon: FolderOpened },
  { path: '/browser', title: '数据浏览', icon: Search },
]

const systemItems = [
  { path: '/overview', title: '系统总览', icon: DataAnalysis },
  { path: '/ingest', title: '摄取管理', icon: Download },
  { path: '/eval', title: '评估面板', icon: TrendCharts },
  { path: '/config', title: '系统配置', icon: Setting },
]
</script>

<style scoped>
.sidebar {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: var(--sp-5) 0;
}

.brand {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  padding: 0 var(--sp-5) var(--sp-6);
}
.brand-mark {
  width: var(--sp-6);
  height: var(--sp-6);
  background: linear-gradient(135deg, rgba(255,255,255,0.15), rgba(255,255,255,0.05));
  border: 1px solid var(--c-border);
  border-radius: var(--radius-sm);
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 600;
  font-size: var(--fs-sm);
  color: var(--c-text-primary);
}
.brand-text {
  display: flex;
  flex-direction: column;
}
.brand-name {
  font-size: var(--fs-sm);
  font-weight: 500;
  color: var(--c-text-primary);
  letter-spacing: -0.3px;
}
.brand-sub {
  font-size: 11px;
  color: var(--c-text-tertiary);
  margin-top: 2px;
}

.nav {
  flex: 1;
  padding: 0 var(--sp-3);
}
.nav-section-label {
  font-size: 11px;
  font-weight: 500;
  color: var(--c-text-tertiary);
  text-transform: uppercase;
  letter-spacing: 1px;
  padding: var(--sp-5) var(--sp-3) var(--sp-2);
}
.nav-item {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  padding: 0 var(--sp-3);
  height: 38px;
  border-radius: var(--radius-sm);
  font-size: var(--fs-sm);
  color: var(--c-text-tertiary);
  text-decoration: none;
  transition: all var(--duration) var(--ease);
  margin-bottom: 2px;
}
.nav-item:hover {
  background: var(--c-surface-hover);
  color: var(--c-text-primary);
}
.nav-item.active {
  background: rgba(255,255,255,0.08);
  color: var(--c-text-primary);
  border: 1px solid var(--c-border);
}
.nav-item .el-icon {
  flex-shrink: 0;
  font-size: var(--icon-sm) !important;
  opacity: 0.6;
}
.nav-item:hover .el-icon,
.nav-item.active .el-icon {
  opacity: 1;
}

.sidebar-footer {
  padding: var(--sp-4) var(--sp-5) 0;
  border-top: 1px solid var(--c-border);
  font-size: 11px;
  color: var(--c-text-tertiary);
}
</style>
