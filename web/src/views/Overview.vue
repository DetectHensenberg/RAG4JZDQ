<template>
  <div class="overview-page">
    <!-- Header -->
    <header class="page-header">
      <div class="header-content">
        <h1 class="page-title">系统总览</h1>
        <p class="page-subtitle">知识库数据统计概览</p>
      </div>
      <div class="header-actions">
        <button class="refresh-btn" @click="refreshStats" :disabled="loading">
          <el-icon :size="16"><Refresh /></el-icon>
          <span>刷新</span>
        </button>
      </div>
    </header>

    <!-- Loading State -->
    <div v-if="!stats && loading" class="loading-grid">
      <div v-for="i in 6" :key="i" class="skeleton-card">
        <div class="skeleton-line skeleton-title"></div>
        <div class="skeleton-line skeleton-value"></div>
      </div>
    </div>

    <!-- Stats Grid -->
    <div v-else-if="stats" class="stats-bento">
      <!-- Main Stats Row -->
      <div class="stat-card stat-documents" style="--delay: 0">
        <div class="stat-icon">
          <el-icon :size="24"><Document /></el-icon>
        </div>
        <div class="stat-content">
          <span class="stat-label">文档总数</span>
          <span class="stat-value">{{ formatNumber(stats.total_documents) }}</span>
        </div>
        <div class="stat-glow"></div>
      </div>

      <div class="stat-card stat-chunks" style="--delay: 1">
        <div class="stat-icon">
          <el-icon :size="24"><Grid /></el-icon>
        </div>
        <div class="stat-content">
          <span class="stat-label">分块数量</span>
          <span class="stat-value">{{ formatNumber(stats.total_chunks) }}</span>
        </div>
        <div class="stat-glow"></div>
      </div>

      <div class="stat-card stat-images" style="--delay: 2">
        <div class="stat-icon">
          <el-icon :size="24"><Picture /></el-icon>
        </div>
        <div class="stat-content">
          <span class="stat-label">图片资源</span>
          <span class="stat-value">{{ formatNumber(stats.total_images) }}</span>
        </div>
        <div class="stat-glow"></div>
      </div>

      <div class="stat-card stat-collections" style="--delay: 3">
        <div class="stat-icon">
          <el-icon :size="24"><Folder /></el-icon>
        </div>
        <div class="stat-content">
          <span class="stat-label">集合数量</span>
          <span class="stat-value">{{ stats.collections?.length || 0 }}</span>
        </div>
        <div class="stat-glow"></div>
      </div>

      <!-- Storage Cards -->
      <div class="storage-card" style="--delay: 4">
        <div class="storage-header">
          <el-icon :size="18"><Coin /></el-icon>
          <span>ChromaDB 向量存储</span>
        </div>
        <div class="storage-value">{{ stats.chroma_size || '0 B' }}</div>
        <div class="storage-bar">
          <div class="storage-fill" :style="{ width: '65%' }"></div>
        </div>
      </div>

      <div class="storage-card" style="--delay: 5">
        <div class="storage-header">
          <el-icon :size="18"><Search /></el-icon>
          <span>BM25 索引</span>
        </div>
        <div class="storage-value">{{ stats.bm25_size || '0 B' }}</div>
        <div class="storage-bar">
          <div class="storage-fill" :style="{ width: '45%' }"></div>
        </div>
      </div>

      <div class="storage-card" style="--delay: 6">
        <div class="storage-header">
          <el-icon :size="18"><PictureFilled /></el-icon>
          <span>图片存储</span>
        </div>
        <div class="storage-value">{{ stats.image_size || '0 B' }}</div>
        <div class="storage-bar">
          <div class="storage-fill" :style="{ width: '30%' }"></div>
        </div>
      </div>

      <!-- Collections Panel -->
      <div class="collections-panel" style="--delay: 7">
        <div class="panel-header">
          <el-icon :size="18"><FolderOpened /></el-icon>
          <span>集合列表</span>
          <span class="panel-count">{{ stats.collections?.length || 0 }} 个</span>
        </div>
        <div class="collections-grid">
          <div
            v-for="c in stats.collections"
            :key="c"
            class="collection-tag"
          >
            <el-icon :size="14"><Folder /></el-icon>
            <span>{{ c }}</span>
          </div>
          <div v-if="!stats.collections?.length" class="empty-collections">
            暂无集合
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { 
  Refresh, Document, Grid, Picture, Folder, 
  Coin, Search, PictureFilled, FolderOpened 
} from '@element-plus/icons-vue'
import { useCacheStore } from '@/stores/cache'
import type { SystemStats } from '@/types/api'

const cache = useCacheStore()

// 使用缓存中的数据
const stats = computed<SystemStats | null>(() => cache.systemStats)
const loading = computed(() => cache.statsLoading)

function formatNumber(n: number): string {
  if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M'
  if (n >= 1000) return (n / 1000).toFixed(1) + 'K'
  return String(n)
}

// 刷新按钮强制重新加载
async function refreshStats() {
  await cache.loadStats(true)
}

// 首次进入时加载数据（如果缓存中没有）
onMounted(() => {
  if (!cache.statsLoaded) {
    cache.loadStats()
  }
})
</script>

<style scoped>
.overview-page {
  height: 100%;
  overflow: auto;
  padding: var(--sp-6);
  animation: pageEnter 0.5s var(--ease);
}

@keyframes pageEnter {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}

/* Header */
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: var(--sp-6);
}

.page-title {
  font-size: var(--fs-xl);
  font-weight: 600;
  color: var(--c-text-primary);
  margin: 0 0 var(--sp-1);
  letter-spacing: -0.5px;
}

.page-subtitle {
  font-size: var(--fs-sm);
  color: var(--c-text-tertiary);
  margin: 0;
}

.refresh-btn {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  padding: var(--sp-2) var(--sp-4);
  background: var(--glass-bg);
  border: 1px solid var(--c-border);
  border-radius: var(--radius-sm);
  color: var(--c-text-secondary);
  font-size: var(--fs-sm);
  cursor: pointer;
  transition: all var(--duration) var(--ease);
}

.refresh-btn:hover:not(:disabled) {
  background: var(--c-surface-hover);
  border-color: var(--c-border-hover);
  color: var(--c-text-primary);
}

.refresh-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Loading Skeleton */
.loading-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--card-gap);
}

.skeleton-card {
  background: var(--glass-bg);
  border: 1px solid var(--c-border);
  border-radius: var(--radius);
  padding: var(--sp-5);
  animation: skeletonPulse 1.5s ease-in-out infinite;
}

.skeleton-line {
  background: var(--c-surface);
  border-radius: var(--radius-xs);
}

.skeleton-title {
  height: 12px;
  width: 60%;
  margin-bottom: var(--sp-3);
}

.skeleton-value {
  height: 32px;
  width: 40%;
}

@keyframes skeletonPulse {
  0%, 100% { opacity: 0.6; }
  50% { opacity: 1; }
}

/* Stats Bento Grid */
.stats-bento {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  grid-template-rows: auto auto auto;
  gap: var(--card-gap);
}

/* Stat Cards */
.stat-card {
  position: relative;
  display: flex;
  align-items: center;
  gap: var(--sp-4);
  padding: var(--sp-5);
  background: var(--glass-bg);
  backdrop-filter: blur(var(--glass-blur));
  -webkit-backdrop-filter: blur(var(--glass-blur));
  border: 1px solid var(--c-border);
  border-radius: var(--radius);
  overflow: hidden;
  transition: all var(--duration) var(--ease);
  animation: cardEnter 0.4s var(--ease) calc(var(--delay) * 0.08s) both;
}

@keyframes cardEnter {
  from { opacity: 0; transform: translateY(16px) scale(0.96); }
  to { opacity: 1; transform: translateY(0) scale(1); }
}

.stat-card:hover {
  border-color: var(--c-border-hover);
  transform: translateY(-2px);
  box-shadow: var(--glow-hover);
}

.stat-icon {
  width: 48px;
  height: 48px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--c-surface);
  border-radius: var(--radius-sm);
  color: var(--c-text-secondary);
  flex-shrink: 0;
}

.stat-content {
  display: flex;
  flex-direction: column;
  gap: var(--sp-1);
}

.stat-label {
  font-size: var(--fs-xs);
  color: var(--c-text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.stat-value {
  font-size: var(--fs-2xl);
  font-weight: 600;
  color: var(--c-text-primary);
  letter-spacing: -1px;
  line-height: 1;
}

.stat-glow {
  position: absolute;
  top: 0;
  right: 0;
  width: 100px;
  height: 100px;
  background: radial-gradient(circle, rgba(255,255,255,0.03) 0%, transparent 70%);
  pointer-events: none;
}

/* Special Card Colors */
.stat-documents .stat-icon { background: rgba(59, 130, 246, 0.1); color: #60a5fa; }
.stat-chunks .stat-icon { background: rgba(16, 185, 129, 0.1); color: #34d399; }
.stat-images .stat-icon { background: rgba(249, 115, 22, 0.1); color: #fb923c; }
.stat-collections .stat-icon { background: rgba(139, 92, 246, 0.1); color: #a78bfa; }

/* Storage Cards */
.storage-card {
  padding: var(--sp-5);
  background: var(--glass-bg);
  backdrop-filter: blur(var(--glass-blur));
  border: 1px solid var(--c-border);
  border-radius: var(--radius);
  animation: cardEnter 0.4s var(--ease) calc(var(--delay) * 0.08s) both;
  transition: all var(--duration) var(--ease);
}

.storage-card:hover {
  border-color: var(--c-border-hover);
}

.storage-header {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  font-size: var(--fs-xs);
  color: var(--c-text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.3px;
  margin-bottom: var(--sp-3);
}

.storage-value {
  font-size: var(--fs-lg);
  font-weight: 500;
  color: var(--c-text-primary);
  margin-bottom: var(--sp-3);
}

.storage-bar {
  height: 4px;
  background: var(--c-surface);
  border-radius: 2px;
  overflow: hidden;
}

.storage-fill {
  height: 100%;
  background: linear-gradient(90deg, rgba(255,255,255,0.3), rgba(255,255,255,0.7));
  border-radius: 2px;
  transition: width 0.6s var(--ease);
}

/* Collections Panel */
.collections-panel {
  grid-column: span 2;
  padding: var(--sp-5);
  background: var(--glass-bg);
  backdrop-filter: blur(var(--glass-blur));
  border: 1px solid var(--c-border);
  border-radius: var(--radius);
  animation: cardEnter 0.4s var(--ease) calc(var(--delay) * 0.08s) both;
}

.panel-header {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  font-size: var(--fs-xs);
  color: var(--c-text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.3px;
  margin-bottom: var(--sp-4);
}

.panel-count {
  margin-left: auto;
  font-size: 11px;
  color: var(--c-text-tertiary);
  background: var(--c-surface);
  padding: 2px var(--sp-2);
  border-radius: var(--radius-xs);
}

.collections-grid {
  display: flex;
  flex-wrap: wrap;
  gap: var(--sp-2);
}

.collection-tag {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  padding: var(--sp-2) var(--sp-3);
  background: var(--c-surface);
  border: 1px solid var(--c-border);
  border-radius: var(--radius-sm);
  font-size: var(--fs-sm);
  color: var(--c-text-secondary);
  transition: all var(--duration) var(--ease);
}

.collection-tag:hover {
  background: var(--c-surface-hover);
  border-color: var(--c-border-hover);
  color: var(--c-text-primary);
}

.empty-collections {
  font-size: var(--fs-sm);
  color: var(--c-text-tertiary);
  padding: var(--sp-3);
}

/* Responsive */
@media (max-width: 1024px) {
  .stats-bento {
    grid-template-columns: repeat(2, 1fr);
  }
  .collections-panel {
    grid-column: span 2;
  }
}

@media (max-width: 640px) {
  .stats-bento {
    grid-template-columns: 1fr;
  }
  .collections-panel {
    grid-column: span 1;
  }
  .page-header {
    flex-direction: column;
    gap: var(--sp-4);
  }
}
</style>
