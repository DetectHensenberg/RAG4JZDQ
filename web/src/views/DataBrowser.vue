<template>
  <div class="browser-page">
    <!-- Header -->
    <header class="page-header">
      <div class="header-content">
        <h1 class="page-title">数据浏览</h1>
        <p class="page-subtitle">浏览已摄取文档及其分块</p>
      </div>
      <div class="header-actions">
        <button class="refresh-btn" @click="refreshDocuments" :disabled="loading">
          <el-icon :size="16"><Refresh v-if="!loading" /><Loading v-else class="spin" /></el-icon>
          <span>{{ loading ? '加载中...' : '刷新' }}</span>
        </button>
      </div>
    </header>

    <!-- Filter Bar -->
    <div class="filter-bar">
      <div class="filter-field">
        <label class="field-label">集合</label>
        <el-select v-model="collection" @change="loadDocuments" style="width: 180px">
          <el-option v-for="c in collections" :key="c" :label="c" :value="c" />
        </el-select>
      </div>
      <div class="result-count">
        <span class="count-value">{{ total }}</span>
        <span class="count-label">个文档</span>
      </div>
    </div>

    <!-- Loading State -->
    <div v-if="loading && !documents.length" class="loading-state">
      <div class="loading-spinner">
        <el-icon :size="32" class="spin"><Loading /></el-icon>
      </div>
      <p>加载数据中...</p>
    </div>

    <!-- Empty State -->
    <div v-else-if="!documents.length" class="empty-state">
      <div class="empty-icon">
        <el-icon :size="48"><Search /></el-icon>
      </div>
      <p class="empty-text">暂无文档数据</p>
      <p class="empty-hint">请先在知识库构建或摄取管理中添加文档</p>
    </div>

    <!-- Document List -->
    <div v-else class="document-list">
      <div
        v-for="(doc, i) in documents"
        :key="doc.source_path"
        class="document-card"
        :style="{ '--delay': i }"
      >
        <div class="doc-header" @click="toggleExpand(doc)">
          <div class="doc-main">
            <div class="doc-icon">
              <el-icon :size="18"><Document /></el-icon>
            </div>
            <div class="doc-info">
              <span class="doc-path">{{ doc.source_path }}</span>
              <span class="doc-meta">
                <span class="doc-time">{{ doc.created_at }}</span>
                <span v-if="doc.chunk_count" class="doc-chunks">{{ doc.chunk_count }} 分块</span>
              </span>
            </div>
          </div>
          <div class="doc-expand">
            <el-icon :size="16" :class="{ expanded: expandedDocs.has(doc.source_path) }">
              <ArrowRight />
            </el-icon>
          </div>
        </div>

        <!-- Expanded Chunks -->
        <div v-if="expandedDocs.has(doc.source_path)" class="doc-chunks">
          <div v-if="doc.chunks && doc.chunks.length" class="chunks-list">
            <div
              v-for="(chunk, ci) in doc.chunks"
              :key="chunk.chunk_id"
              class="chunk-item"
              :style="{ '--chunk-delay': ci }"
            >
              <div class="chunk-header">
                <span class="chunk-id">{{ chunk.chunk_id.slice(0, 8) }}</span>
                <span v-if="chunk.page" class="chunk-page">第 {{ chunk.page }} 页</span>
              </div>
              <div class="chunk-content">{{ truncate(chunk.content, 300) }}</div>
            </div>
          </div>
          <div v-else-if="loadingChunks === doc.source_path" class="chunks-loading">
            <el-icon :size="20" class="spin"><Loading /></el-icon>
            <span>加载分块中...</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Pagination -->
    <div v-if="total > pageSize" class="pagination-bar">
      <el-pagination
        v-model:current-page="page"
        :page-size="pageSize"
        :total="total"
        layout="prev, pager, next"
        @current-change="loadDocuments"
        background
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { Document, Refresh, Loading, Search, ArrowRight } from '@element-plus/icons-vue'
import { useCacheStore } from '@/stores/cache'
import api from '@/composables/useApi'
import type { ApiResponse, DocumentItem, DocumentListData, ChunkItem } from '@/types/api'

interface DocWithChunks extends DocumentItem {
  chunks?: ChunkItem[]
}

const cache = useCacheStore()

const collection = ref('default')
const documents = ref<DocWithChunks[]>([])
const loading = ref(false)
const page = ref(1)
const pageSize = 20
const total = ref(0)
const expandedDocs = ref<Set<string>>(new Set())
const loadingChunks = ref<string | null>(null)

// 使用缓存中的集合列表
const collections = computed(() => cache.collections)

function truncate(text: string, max: number): string {
  if (!text) return ''
  return text.length > max ? text.slice(0, max) + '...' : text
}

// 加载文档列表（使用缓存）
async function loadDocuments(force = false) {
  loading.value = true
  expandedDocs.value.clear()
  try {
    const result = await cache.loadDocuments(collection.value, page.value, pageSize, force)
    documents.value = result.items as DocWithChunks[]
    total.value = result.total
  } finally {
    loading.value = false
  }
}

// 强制刷新
async function refreshDocuments() {
  cache.clearDocumentsCache(collection.value)
  await loadDocuments(true)
}

async function toggleExpand(doc: DocWithChunks) {
  const path = doc.source_path
  if (expandedDocs.value.has(path)) {
    expandedDocs.value.delete(path)
  } else {
    expandedDocs.value.add(path)
    if (!doc.chunks) {
      loadingChunks.value = path
      try {
        const { data } = await api.get(`/data/chunks/${path}`, {
          params: { collection: collection.value },
        })
        if (data.ok) {
          doc.chunks = data.data
        }
      } finally {
        loadingChunks.value = null
      }
    }
  }
}

// 监听集合变化
watch(collection, () => {
  page.value = 1
  loadDocuments()
})

onMounted(async () => {
  // 首次加载集合列表（如果缓存中没有）
  if (!cache.collectionsLoaded) {
    await cache.loadCollections()
  }
  // 设置默认集合
  if (cache.collections.length > 0 && !cache.collections.includes('default')) {
    collection.value = cache.collections[0]
  }
  loadDocuments()
})
</script>

<style scoped>
.browser-page {
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
  margin-bottom: var(--sp-5);
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

/* Filter Bar */
.filter-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--sp-4);
  background: var(--glass-bg);
  border: 1px solid var(--c-border);
  border-radius: var(--radius);
  margin-bottom: var(--sp-5);
  animation: sectionEnter 0.4s var(--ease);
}

@keyframes sectionEnter {
  from { opacity: 0; transform: translateY(16px); }
  to { opacity: 1; transform: translateY(0); }
}

.filter-field {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
}

.field-label {
  font-size: var(--fs-xs);
  color: var(--c-text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.3px;
}

.result-count {
  display: flex;
  align-items: baseline;
  gap: var(--sp-1);
}

.count-value {
  font-size: var(--fs-lg);
  font-weight: 600;
  color: var(--c-text-primary);
}

.count-label {
  font-size: var(--fs-sm);
  color: var(--c-text-tertiary);
}

/* Loading State */
.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--sp-8);
}

.loading-spinner {
  width: 64px;
  height: 64px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--c-text-tertiary);
  margin-bottom: var(--sp-4);
}

.loading-state p {
  font-size: var(--fs-sm);
  color: var(--c-text-tertiary);
  margin: 0;
}

/* Empty State */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--sp-8);
}

.empty-icon {
  width: 80px;
  height: 80px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--c-surface);
  border-radius: var(--radius);
  color: var(--c-text-tertiary);
  margin-bottom: var(--sp-4);
}

.empty-text {
  font-size: var(--fs-base);
  color: var(--c-text-secondary);
  margin: 0 0 var(--sp-2);
}

.empty-hint {
  font-size: var(--fs-sm);
  color: var(--c-text-tertiary);
  margin: 0;
}

/* Document List */
.document-list {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
}

.document-card {
  background: var(--glass-bg);
  border: 1px solid var(--c-border);
  border-radius: var(--radius);
  overflow: hidden;
  animation: docEnter 0.3s var(--ease) calc(var(--delay) * 0.03s) both;
  transition: all var(--duration) var(--ease);
}

@keyframes docEnter {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}

.document-card:hover {
  border-color: var(--c-border-hover);
}

.doc-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--sp-4);
  cursor: pointer;
  transition: background var(--duration) var(--ease);
}

.doc-header:hover {
  background: var(--c-surface);
}

.doc-main {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  flex: 1;
  min-width: 0;
}

.doc-icon {
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(59, 130, 246, 0.1);
  border-radius: var(--radius-sm);
  color: #60a5fa;
  flex-shrink: 0;
}

.doc-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.doc-path {
  font-size: var(--fs-sm);
  color: var(--c-text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.doc-meta {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  font-size: 11px;
  color: var(--c-text-tertiary);
}

.doc-chunks {
  background: rgba(59, 130, 246, 0.1);
  padding: 1px var(--sp-2);
  border-radius: var(--radius-xs);
  color: #60a5fa;
}

.doc-expand {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--c-text-tertiary);
  transition: transform var(--duration) var(--ease);
}

.doc-expand .expanded {
  transform: rotate(90deg);
}

/* Doc Chunks */
.doc-chunks {
  border-top: 1px solid var(--c-border);
  background: var(--c-surface);
}

.chunks-list {
  padding: var(--sp-3);
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
}

.chunk-item {
  padding: var(--sp-3);
  background: var(--glass-bg);
  border: 1px solid var(--c-border);
  border-radius: var(--radius-sm);
  animation: chunkEnter 0.25s var(--ease) calc(var(--chunk-delay) * 0.04s) both;
}

@keyframes chunkEnter {
  from { opacity: 0; transform: translateX(-8px); }
  to { opacity: 1; transform: translateX(0); }
}

.chunk-header {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  margin-bottom: var(--sp-2);
}

.chunk-id {
  font-size: 11px;
  font-family: monospace;
  color: var(--c-text-tertiary);
  background: var(--c-surface);
  padding: 2px var(--sp-2);
  border-radius: var(--radius-xs);
}

.chunk-page {
  font-size: 11px;
  color: #a78bfa;
}

.chunk-content {
  font-size: var(--fs-xs);
  color: var(--c-text-secondary);
  line-height: 1.6;
}

.chunks-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--sp-2);
  padding: var(--sp-6);
  color: var(--c-text-tertiary);
  font-size: var(--fs-sm);
}

/* Pagination */
.pagination-bar {
  display: flex;
  justify-content: center;
  padding: var(--sp-5) 0;
}

/* Spin Animation */
.spin {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

/* Responsive */
@media (max-width: 768px) {
  .page-header {
    flex-direction: column;
    gap: var(--sp-4);
  }
  
  .filter-bar {
    flex-direction: column;
    align-items: flex-start;
    gap: var(--sp-3);
  }
}
</style>
