<template>
  <div class="ingest-page">
    <!-- Header -->
    <header class="page-header">
      <div class="header-content">
        <h1 class="page-title">摄取管理</h1>
        <p class="page-subtitle">上传单个文件摄取，或管理已有文档</p>
      </div>
    </header>

    <!-- Upload Section -->
    <section class="upload-section">
      <div class="section-header">
        <el-icon :size="18"><Upload /></el-icon>
        <span>上传文件</span>
      </div>
      <div class="upload-body">
        <div class="collection-field">
          <label class="field-label">集合</label>
          <el-input v-model="collection" style="width: 140px" />
        </div>
        
        <el-upload
          :action="`/api/ingest/upload`"
          :data="{ collection }"
          :on-success="onUploadSuccess"
          :on-error="onUploadError"
          :before-upload="() => { uploading = true; return true }"
          accept=".pdf,.pptx,.docx,.md,.txt"
          :show-file-list="false"
          drag
          class="upload-dragger"
        >
          <div class="upload-content">
            <div class="upload-icon">
              <el-icon :size="32"><Upload /></el-icon>
            </div>
            <p class="upload-text">拖拽文件到此处，或点击上传</p>
            <p class="upload-hint">支持 PDF / PPTX / DOCX / MD / TXT</p>
          </div>
        </el-upload>

        <div v-if="uploadResult" class="upload-result" :class="uploadResult.ok ? 'success' : 'error'">
          <el-icon :size="16">
            <CircleCheck v-if="uploadResult.ok" />
            <CircleClose v-else />
          </el-icon>
          <span>{{ uploadResult.message }}</span>
        </div>
      </div>
    </section>

    <!-- Documents Section -->
    <section class="documents-section">
      <div class="section-header">
        <div class="section-title">
          <el-icon :size="18"><Document /></el-icon>
          <span>已摄取文档</span>
          <span class="doc-count">{{ documents.length }} 个</span>
        </div>
        <button class="refresh-btn" @click="refreshDocuments" :disabled="loading">
          <el-icon :size="16"><Refresh v-if="!loading" /><Loading v-else class="spin" /></el-icon>
        </button>
      </div>

      <!-- Loading State -->
      <div v-if="loading && !documents.length" class="loading-state">
        <div class="loading-spinner">
          <el-icon :size="24" class="spin"><Loading /></el-icon>
        </div>
        <p>加载中...</p>
      </div>

      <!-- Empty State -->
      <div v-else-if="!documents.length" class="empty-state">
        <div class="empty-icon">
          <el-icon :size="32"><Document /></el-icon>
        </div>
        <p>暂无已摄取文档</p>
      </div>

      <!-- Document List -->
      <div v-else class="document-list">
        <div
          v-for="(doc, i) in documents"
          :key="doc.source_path"
          class="document-item"
          :style="{ '--delay': i }"
        >
          <div class="doc-icon">
            <el-icon :size="18"><Document /></el-icon>
          </div>
          <div class="doc-info">
            <span class="doc-path">{{ doc.source_path }}</span>
            <span class="doc-time">{{ doc.created_at }}</span>
          </div>
          <button class="delete-btn" @click="confirmDelete(doc)">
            <el-icon :size="16"><Delete /></el-icon>
          </button>
        </div>
      </div>
    </section>

    <!-- Delete Confirm Dialog -->
    <el-dialog
      v-model="showDeleteConfirm"
      title="确认删除"
      width="360px"
      :close-on-click-modal="false"
    >
      <p class="confirm-text">确定要删除此文档吗？此操作不可撤销。</p>
      <template #footer>
        <div class="dialog-actions">
          <button class="cancel-btn" @click="showDeleteConfirm = false">取消</button>
          <button class="confirm-btn" @click="doDelete" :disabled="deleting">
            {{ deleting ? '删除中...' : '确认删除' }}
          </button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Upload, Document, Refresh, Loading, CircleCheck, CircleClose, Delete } from '@element-plus/icons-vue'
import { useCacheStore } from '@/stores/cache'
import api from '@/composables/useApi'

const cache = useCacheStore()

const collection = ref('default')
const uploading = ref(false)
const uploadResult = ref<{ ok: boolean; message: string } | null>(null)
const documents = ref<any[]>([])
const loading = ref(false)
const showDeleteConfirm = ref(false)
const deleting = ref(false)
const docToDelete = ref<any>(null)

function onUploadSuccess(response: any) {
  uploading.value = false
  if (response.ok) {
    const d = response.data
    uploadResult.value = { ok: true, message: d.skipped ? '文件已存在，已跳过' : `摄取成功: ${d.chunks} 分块` }
    // 上传成功后清除缓存并重新加载
    cache.clearDocumentsCache(collection.value)
    loadDocuments(true)
  } else {
    uploadResult.value = { ok: false, message: response.message || '摄取失败' }
  }
}

function onUploadError() {
  uploading.value = false
  uploadResult.value = { ok: false, message: '上传失败' }
}

async function loadDocuments(force = false) {
  loading.value = true
  try {
    const result = await cache.loadDocuments(collection.value, 1, 100, force)
    documents.value = result.items
  } finally { loading.value = false }
}

// 强制刷新
async function refreshDocuments() {
  cache.clearDocumentsCache(collection.value)
  await loadDocuments(true)
}

function confirmDelete(doc: any) {
  docToDelete.value = doc
  showDeleteConfirm.value = true
}

async function doDelete() {
  if (!docToDelete.value) return
  deleting.value = true
  try {
    const { data } = await api.delete('/ingest/document', {
      data: { 
        source_path: docToDelete.value.source_path, 
        collection: collection.value, 
        source_hash: docToDelete.value.file_hash 
      },
    })
    if (data.ok) {
      ElMessage.success('已删除')
      showDeleteConfirm.value = false
      // 删除后清除缓存并重新加载
      cache.clearDocumentsCache(collection.value)
      loadDocuments(true)
    } else {
      ElMessage.error(data.message)
    }
  } catch { 
    ElMessage.error('删除失败') 
  } finally {
    deleting.value = false
  }
}

onMounted(() => {
  // 首次加载时使用缓存
  loadDocuments()
})
</script>

<style scoped>
.ingest-page {
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

/* Upload Section */
.upload-section {
  background: var(--glass-bg);
  backdrop-filter: blur(var(--glass-blur));
  border: 1px solid var(--c-border);
  border-radius: var(--radius);
  margin-bottom: var(--sp-6);
  animation: sectionEnter 0.4s var(--ease);
}

@keyframes sectionEnter {
  from { opacity: 0; transform: translateY(16px); }
  to { opacity: 1; transform: translateY(0); }
}

.section-header {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  padding: var(--sp-4) var(--sp-5);
  background: var(--c-surface);
  border-bottom: 1px solid var(--c-border);
  font-size: var(--fs-sm);
  font-weight: 500;
  color: var(--c-text-primary);
}

.upload-body {
  padding: var(--sp-5);
}

.collection-field {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  margin-bottom: var(--sp-4);
}

.field-label {
  font-size: var(--fs-xs);
  color: var(--c-text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.3px;
}

/* Upload Dragger */
.upload-dragger {
  width: 100%;
}

.upload-dragger :deep(.el-upload-dragger) {
  width: 100%;
  height: auto;
  min-height: 160px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--c-surface);
  border: 2px dashed var(--c-border);
  border-radius: var(--radius);
  transition: all var(--duration) var(--ease);
}

.upload-dragger :deep(.el-upload-dragger:hover) {
  border-color: var(--c-border-hover);
  background: var(--c-surface-hover);
}

.upload-content {
  text-align: center;
  padding: var(--sp-6);
}

.upload-icon {
  width: 64px;
  height: 64px;
  margin: 0 auto var(--sp-4);
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(59, 130, 246, 0.1);
  border-radius: var(--radius);
  color: #60a5fa;
}

.upload-text {
  font-size: var(--fs-sm);
  color: var(--c-text-secondary);
  margin: 0 0 var(--sp-2);
}

.upload-hint {
  font-size: var(--fs-xs);
  color: var(--c-text-tertiary);
  margin: 0;
}

/* Upload Result */
.upload-result {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  padding: var(--sp-3) var(--sp-4);
  margin-top: var(--sp-4);
  border-radius: var(--radius-sm);
  font-size: var(--fs-sm);
}

.upload-result.success {
  background: rgba(34, 197, 94, 0.08);
  border: 1px solid rgba(34, 197, 94, 0.2);
  color: #34d399;
}

.upload-result.error {
  background: rgba(239, 68, 68, 0.08);
  border: 1px solid rgba(239, 68, 68, 0.2);
  color: #f87171;
}

/* Documents Section */
.documents-section {
  background: var(--glass-bg);
  backdrop-filter: blur(var(--glass-blur));
  border: 1px solid var(--c-border);
  border-radius: var(--radius);
  animation: sectionEnter 0.4s var(--ease) 0.1s both;
}

.section-title {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
}

.doc-count {
  font-size: 11px;
  color: var(--c-text-tertiary);
  background: var(--c-surface);
  padding: 2px var(--sp-2);
  border-radius: var(--radius-xs);
  margin-left: var(--sp-2);
}

.refresh-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  background: var(--glass-bg);
  border: 1px solid var(--c-border);
  border-radius: var(--radius-xs);
  color: var(--c-text-secondary);
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

/* Loading State */
.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--sp-8);
}

.loading-spinner {
  width: 48px;
  height: 48px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--c-text-tertiary);
  margin-bottom: var(--sp-3);
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
  width: 64px;
  height: 64px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--c-surface);
  border-radius: var(--radius);
  color: var(--c-text-tertiary);
  margin-bottom: var(--sp-3);
}

.empty-state p {
  font-size: var(--fs-sm);
  color: var(--c-text-tertiary);
  margin: 0;
}

/* Document List */
.document-list {
  padding: var(--sp-3);
  max-height: 400px;
  overflow-y: auto;
}

.document-item {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  padding: var(--sp-3);
  background: var(--c-surface);
  border: 1px solid var(--c-border);
  border-radius: var(--radius-sm);
  margin-bottom: var(--sp-2);
  transition: all var(--duration) var(--ease);
  animation: docEnter 0.3s var(--ease) calc(var(--delay) * 0.03s) both;
}

@keyframes docEnter {
  from { opacity: 0; transform: translateX(-8px); }
  to { opacity: 1; transform: translateX(0); }
}

.document-item:hover {
  background: var(--c-surface-hover);
  border-color: var(--c-border-hover);
}

.document-item:last-child {
  margin-bottom: 0;
}

.doc-icon {
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(59, 130, 246, 0.1);
  border-radius: var(--radius-xs);
  color: #60a5fa;
  flex-shrink: 0;
}

.doc-info {
  flex: 1;
  min-width: 0;
}

.doc-path {
  display: block;
  font-size: var(--fs-sm);
  color: var(--c-text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.doc-time {
  display: block;
  font-size: 11px;
  color: var(--c-text-tertiary);
  margin-top: 2px;
}

.delete-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  background: transparent;
  border: 1px solid transparent;
  border-radius: var(--radius-xs);
  color: var(--c-text-tertiary);
  cursor: pointer;
  transition: all var(--duration) var(--ease);
  flex-shrink: 0;
}

.delete-btn:hover {
  background: rgba(239, 68, 68, 0.1);
  border-color: rgba(239, 68, 68, 0.3);
  color: #f87171;
}

/* Dialog */
.confirm-text {
  font-size: var(--fs-sm);
  color: var(--c-text-secondary);
  margin: 0;
}

.dialog-actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--sp-3);
}

.cancel-btn {
  padding: 0 var(--sp-4);
  height: var(--btn-h);
  background: var(--glass-bg);
  border: 1px solid var(--c-border);
  border-radius: var(--radius-sm);
  color: var(--c-text-secondary);
  font-size: var(--fs-sm);
  cursor: pointer;
  transition: all var(--duration) var(--ease);
}

.cancel-btn:hover {
  background: var(--c-surface-hover);
  border-color: var(--c-border-hover);
  color: var(--c-text-primary);
}

.confirm-btn {
  padding: 0 var(--sp-4);
  height: var(--btn-h);
  background: rgba(239, 68, 68, 0.9);
  border: none;
  border-radius: var(--radius-sm);
  color: white;
  font-size: var(--fs-sm);
  cursor: pointer;
  transition: all var(--duration) var(--ease);
}

.confirm-btn:hover:not(:disabled) {
  background: rgba(239, 68, 68, 1);
}

.confirm-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Spin Animation */
.spin {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
</style>
