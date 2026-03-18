<template>
  <div class="knowledge-page">
    <!-- Header -->
    <header class="page-header">
      <div class="header-content">
        <h1 class="page-title">知识库构建</h1>
        <p class="page-subtitle">选择文件夹，批量摄取文档到知识库</p>
      </div>
    </header>

    <!-- Config Section -->
    <section class="config-section">
      <div class="config-card">
        <div class="config-row">
          <div class="config-field">
            <label class="field-label">文件夹路径</label>
            <div class="field-input">
              <el-input
                v-model="folderPath"
                placeholder="D:\WorkSpace\知识库"
                :disabled="ingesting"
                class="path-input"
              >
                <template #prefix>
                  <el-icon><FolderOpened /></el-icon>
                </template>
                <template #append>
                  <button class="browse-btn" @click="browseFolder" :disabled="ingesting">
                    <el-icon :size="16"><FolderOpened /></el-icon>
                    <span>{{ browsing ? '...' : '浏览' }}</span>
                  </button>
                </template>
              </el-input>
            </div>
          </div>
          <div class="config-field config-field-small">
            <label class="field-label">集合</label>
            <el-input v-model="collection" :disabled="ingesting" class="collection-input" />
          </div>
          <button
            class="scan-btn"
            @click="scanFolder"
            :disabled="ingesting || !folderPath.trim()"
            :class="{ loading: scanning }"
          >
            <el-icon :size="18"><Search /></el-icon>
            <span>{{ scanning ? '扫描中...' : '扫描' }}</span>
          </button>
        </div>
        <div class="config-row config-row-options">
          <el-checkbox v-model="forceReingest" :disabled="ingesting" label="强制重入库 (覆盖已有文件)" />
          <el-checkbox v-model="skipLlm" :disabled="ingesting" label="跳过 LLM 优化 (加速批量入库)" />
        </div>
      </div>
    </section>

    <!-- Scanned Files Section -->
    <section v-if="files.length" class="files-section">
      <div class="section-header">
        <div class="section-title">
          <el-icon :size="18"><Document /></el-icon>
          <span>扫描结果</span>
          <span class="file-count">{{ files.length }} 个文件</span>
        </div>
        <div class="section-actions">
          <button
            v-if="!ingesting"
            class="action-btn action-btn-primary"
            @click="startIngest"
          >
            <el-icon :size="16"><Upload /></el-icon>
            <span>开始构建</span>
          </button>
          <button
            v-else
            class="action-btn action-btn-danger"
            @click="stopIngest"
          >
            <el-icon :size="16"><VideoPause /></el-icon>
            <span>停止</span>
          </button>
        </div>
      </div>

      <div class="files-grid">
        <div
          v-for="(file, i) in files"
          :key="i"
          class="file-item"
          :style="{ '--delay': i }"
        >
          <div class="file-icon">
            <el-icon :size="16"><Document /></el-icon>
          </div>
          <div class="file-info">
            <span class="file-name">{{ file.name }}</span>
            <span class="file-size">{{ formatSize(file.size) }}</span>
          </div>
        </div>
      </div>
    </section>

    <!-- Progress Section -->
    <section v-if="ingesting || logs.length" class="progress-section">
      <div class="section-header">
        <div class="section-title">
          <el-icon :size="18"><Loading v-if="ingesting" class="spin" /><Finished v-else /></el-icon>
          <span>{{ ingesting ? '构建进度' : '构建完成' }}</span>
        </div>
      </div>

      <!-- Progress Bar -->
      <div v-if="ingesting" class="progress-container">
        <div class="progress-bar">
          <div class="progress-fill" :style="{ width: progressPct + '%' }">
            <span class="progress-text">{{ progressPct }}%</span>
          </div>
        </div>
        <p class="progress-status">{{ progressText }}</p>
      </div>

      <!-- Result Summary -->
      <div v-if="!ingesting && logs.length" class="result-summary">
        <div class="result-item result-success">
          <el-icon :size="16"><CircleCheck /></el-icon>
          <span>成功 {{ resultCounts.success }}</span>
        </div>
        <div class="result-item result-failed">
          <el-icon :size="16"><CircleClose /></el-icon>
          <span>失败 {{ resultCounts.failed }}</span>
        </div>
        <div class="result-item result-skipped">
          <el-icon :size="16"><Remove /></el-icon>
          <span>跳过 {{ resultCounts.skipped }}</span>
        </div>
      </div>

      <!-- Logs -->
      <div class="logs-container">
        <div
          v-for="(log, i) in logs"
          :key="i"
          class="log-item"
          :class="getLogClass(log)"
        >
          <el-icon :size="14">
            <CircleCheck v-if="log.startsWith('✅')" />
            <Remove v-else-if="log.startsWith('⏭')" />
            <CircleClose v-else />
          </el-icon>
          <span>{{ log.replace(/^[✅⏭❌]\s*/, '') }}</span>
        </div>
      </div>
    </section>

    <!-- Empty State -->
    <section v-if="!files.length && !ingesting && !logs.length" class="empty-state">
      <div class="empty-icon">
        <el-icon :size="48"><FolderOpened /></el-icon>
      </div>
      <p class="empty-text">输入文件夹路径开始扫描</p>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { 
  FolderOpened, Folder, Search, Document, Upload, VideoPause, 
  Loading, Finished, CircleCheck, CircleClose, Remove 
} from '@element-plus/icons-vue'
import { useSSE } from '@/composables/useSSE'
import api from '@/composables/useApi'

const folderPath = ref('')
const collection = ref('default')
const forceReingest = ref(false)
const skipLlm = ref(false)
const files = ref<any[]>([])
const scanning = ref(false)
const ingesting = ref(false)
const browsing = ref(false)
const progressPct = ref(0)
const progressText = ref('')
const logs = ref<string[]>([])
const taskId = ref('')
const resultCounts = ref({ success: 0, failed: 0, skipped: 0 })

const { stream, abort } = useSSE()

function formatSize(bytes: number): string {
  if (bytes >= 1024 * 1024) return (bytes / 1024 / 1024).toFixed(1) + ' MB'
  if (bytes >= 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return bytes + ' B'
}

function getLogClass(log: string): string {
  if (log.startsWith('✅')) return 'log-success'
  if (log.startsWith('⏭')) return 'log-skipped'
  return 'log-error'
}

async function browseFolder() {
  browsing.value = true
  try {
    const { data } = await api.post('/file-dialog/select-folder', {
      title: '选择知识库文件夹',
    })
    if (data.ok && data.data.path) {
      folderPath.value = data.data.path
    }
  } catch {
    ElMessage.error('打开文件夹对话框失败')
  } finally {
    browsing.value = false
  }
}

async function scanFolder() {
  if (!folderPath.value.trim()) return ElMessage.warning('请输入文件夹路径')
  scanning.value = true
  try {
    const { data } = await api.post('/knowledge/scan', { folder_path: folderPath.value })
    if (data.ok) {
      files.value = data.data.files
      ElMessage.success(`扫描到 ${data.data.total} 个文件`)
    } else {
      ElMessage.error(data.message)
    }
  } catch { ElMessage.error('扫描失败') }
  finally { scanning.value = false }
}

async function startIngest() {
  ingesting.value = true
  logs.value = []
  progressPct.value = 0
  resultCounts.value = { success: 0, failed: 0, skipped: 0 }

  try {
    const { data } = await api.post('/knowledge/ingest', {
      folder_path: folderPath.value,
      collection: collection.value,
      force: forceReingest.value,
      skip_llm_transform: skipLlm.value,
    })
    if (!data.ok) { ElMessage.error(data.message); ingesting.value = false; return }
    taskId.value = data.data.task_id

    await stream(
      `/api/knowledge/progress/${taskId.value}`,
      {},
      (event) => {
        if (event.type === 'heartbeat') {
          // Ignore heartbeat, just keeps connection alive
          return
        } else if (event.type === 'reconnect') {
          // Reconnected to running task, restore progress
          progressPct.value = Math.round((event.current / event.total) * 100)
          progressText.value = `[${event.current}/${event.total}] ${event.file} (已恢复连接)`
        } else if (event.type === 'progress') {
          progressPct.value = Math.round((event.current / event.total) * 100)
          progressText.value = `[${event.current}/${event.total}] ${event.file}`
        } else if (event.type === 'file_done') {
          if (event.status === 'success') logs.value.push(`✅ ${event.file} — ${event.chunks} 分块`)
          else if (event.status === 'skipped') logs.value.push(`⏭ ${event.file} — 已跳过`)
          else logs.value.push(`❌ ${event.file} — ${event.error || '失败'}`)
        } else if (event.type === 'done') {
          resultCounts.value = { success: event.success || 0, failed: event.failed || 0, skipped: event.skipped || 0 }
          progressPct.value = 100
          ingesting.value = false
        } else if (event.type === 'stopped') {
          logs.value.push(`⏹ 已停止 (${event.completed}/${event.total})`)
          ingesting.value = false
        } else if (event.type === 'error') {
          logs.value.push(`❌ 任务错误: ${event.message}`)
          ingesting.value = false
        }
      },
      () => { ingesting.value = false },
      (err) => { ElMessage.error(err.message); ingesting.value = false },
    )
  } catch { ElMessage.error('启动失败'); ingesting.value = false }
}

async function stopIngest() {
  if (taskId.value) {
    await api.post(`/knowledge/stop/${taskId.value}`)
    ElMessage.info('已发送停止信号')
  }
}
</script>

<style scoped>
.knowledge-page {
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

/* Config Section */
.config-section {
  margin-bottom: var(--sp-6);
}

.config-card {
  background: var(--glass-bg);
  backdrop-filter: blur(var(--glass-blur));
  border: 1px solid var(--c-border);
  border-radius: var(--radius);
  padding: var(--sp-5);
  animation: cardEnter 0.4s var(--ease);
}

@keyframes cardEnter {
  from { opacity: 0; transform: translateY(16px); }
  to { opacity: 1; transform: translateY(0); }
}

.config-row {
  display: flex;
  align-items: flex-end;
  gap: var(--sp-4);
}

.config-row-options {
  align-items: center;
  padding-top: var(--sp-3);
  gap: var(--sp-6);
}

.config-field {
  flex: 1;
}

.config-field-small {
  flex: 0 0 120px;
}

.field-label {
  display: block;
  font-size: var(--fs-xs);
  color: var(--c-text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.3px;
  margin-bottom: var(--sp-2);
}

/* Override Element Plus input append style */
.path-input :deep(.el-input-group__append) {
  background: transparent !important;
  border-color: rgba(255, 255, 255, 0.1) !important;
  padding: 0 !important;
  box-shadow: none !important;
}

.path-input :deep(.el-input__wrapper) {
  background: rgba(255, 255, 255, 0.03);
  border-color: rgba(255, 255, 255, 0.1);
  box-shadow: none;
}

.path-input :deep(.el-input__wrapper:hover) {
  border-color: rgba(255, 255, 255, 0.2);
}

.path-input :deep(.el-input__wrapper.is-focus) {
  border-color: var(--c-accent);
  box-shadow: 0 0 0 1px var(--c-accent);
}

.path-input :deep(.el-input__inner) {
  color: var(--c-text-primary);
}

.path-input :deep(.el-input__inner::placeholder) {
  color: var(--c-text-tertiary);
}

.scan-btn {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  padding: 0 var(--sp-5);
  height: var(--btn-h);
  background: var(--c-accent);
  border: none;
  border-radius: var(--radius-sm);
  color: #0a0a0a;
  font-size: var(--fs-sm);
  font-weight: 500;
  cursor: pointer;
  transition: all var(--duration) var(--ease);
  flex-shrink: 0;
}

.scan-btn:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(255,255,255,0.2);
}

.scan-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.scan-btn.loading {
  background: var(--c-text-tertiary);
}

.browse-btn {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  padding: 0 var(--sp-4);
  height: 100%;
  background: rgba(255, 255, 255, 0.05);
  border: none;
  border-left: 1px solid rgba(255, 255, 255, 0.1);
  color: var(--c-text-secondary);
  font-size: var(--fs-sm);
  font-weight: 500;
  cursor: pointer;
  transition: all var(--duration) var(--ease);
}

.browse-btn:hover:not(:disabled) {
  background: var(--c-accent);
  color: #0a0a0a;
  border-left-color: var(--c-accent);
}

.browse-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Files Section */
.files-section {
  margin-bottom: var(--sp-6);
  animation: cardEnter 0.4s var(--ease) 0.1s both;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--sp-4);
}

.section-title {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  font-size: var(--fs-sm);
  font-weight: 500;
  color: var(--c-text-primary);
}

.file-count {
  font-size: var(--fs-xs);
  color: var(--c-text-tertiary);
  background: var(--c-surface);
  padding: 2px var(--sp-2);
  border-radius: var(--radius-xs);
  margin-left: var(--sp-2);
}

.section-actions {
  display: flex;
  gap: var(--sp-2);
}

.action-btn {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  padding: 0 var(--sp-4);
  height: var(--btn-h);
  border-radius: var(--radius-sm);
  font-size: var(--fs-sm);
  cursor: pointer;
  transition: all var(--duration) var(--ease);
}

.action-btn-primary {
  background: var(--c-accent);
  border: none;
  color: #0a0a0a;
  font-weight: 500;
}

.action-btn-primary:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(255,255,255,0.2);
}

.action-btn-danger {
  background: rgba(239,68,68,0.1);
  border: 1px solid rgba(239,68,68,0.3);
  color: var(--c-danger);
}

.action-btn-danger:hover {
  background: rgba(239,68,68,0.15);
  border-color: rgba(239,68,68,0.5);
}

/* Files Grid */
.files-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: var(--sp-2);
  max-height: 300px;
  overflow-y: auto;
  padding: var(--sp-3);
  background: var(--glass-bg);
  border: 1px solid var(--c-border);
  border-radius: var(--radius);
}

.file-item {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  padding: var(--sp-3);
  background: var(--c-surface);
  border: 1px solid var(--c-border);
  border-radius: var(--radius-sm);
  transition: all var(--duration) var(--ease);
  animation: fileEnter 0.3s var(--ease) calc(var(--delay) * 0.02s) both;
}

@keyframes fileEnter {
  from { opacity: 0; transform: translateX(-8px); }
  to { opacity: 1; transform: translateX(0); }
}

.file-item:hover {
  background: var(--c-surface-hover);
  border-color: var(--c-border-hover);
}

.file-icon {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(59, 130, 246, 0.1);
  border-radius: var(--radius-xs);
  color: #60a5fa;
  flex-shrink: 0;
}

.file-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.file-name {
  font-size: var(--fs-sm);
  color: var(--c-text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.file-size {
  font-size: 11px;
  color: var(--c-text-tertiary);
}

/* Progress Section */
.progress-section {
  animation: cardEnter 0.4s var(--ease) 0.2s both;
}

.progress-container {
  margin-bottom: var(--sp-4);
}

.progress-bar {
  height: 8px;
  background: var(--c-surface);
  border-radius: 4px;
  overflow: hidden;
  margin-bottom: var(--sp-2);
}

.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, rgba(255,255,255,0.4), rgba(255,255,255,0.9));
  border-radius: 4px;
  transition: width 0.3s var(--ease);
  position: relative;
}

.progress-text {
  position: absolute;
  right: var(--sp-2);
  top: 50%;
  transform: translateY(-50%);
  font-size: 10px;
  color: #0a0a0a;
  font-weight: 600;
}

.progress-status {
  font-size: var(--fs-xs);
  color: var(--c-text-tertiary);
  margin: 0;
}

/* Result Summary */
.result-summary {
  display: flex;
  gap: var(--sp-4);
  margin-bottom: var(--sp-4);
  padding: var(--sp-4);
  background: var(--glass-bg);
  border: 1px solid var(--c-border);
  border-radius: var(--radius-sm);
}

.result-item {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  font-size: var(--fs-sm);
}

.result-success { color: #34d399; }
.result-failed { color: #f87171; }
.result-skipped { color: var(--c-text-tertiary); }

/* Logs */
.logs-container {
  max-height: 200px;
  overflow-y: auto;
  padding: var(--sp-3);
  background: var(--glass-bg);
  border: 1px solid var(--c-border);
  border-radius: var(--radius-sm);
}

.log-item {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  padding: var(--sp-2) 0;
  font-size: var(--fs-xs);
  border-bottom: 1px solid var(--c-border);
}

.log-item:last-child {
  border-bottom: none;
}

.log-success { color: #34d399; }
.log-skipped { color: var(--c-text-tertiary); }
.log-error { color: #f87171; }

/* Empty State */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--sp-8);
  animation: cardEnter 0.4s var(--ease);
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
  font-size: var(--fs-sm);
  color: var(--c-text-tertiary);
  margin: 0;
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
  .config-row {
    flex-direction: column;
    align-items: stretch;
  }
  
  .config-field-small {
    flex: 1;
  }
  
  .scan-btn {
    width: 100%;
    justify-content: center;
  }
  
  .section-header {
    flex-direction: column;
    align-items: flex-start;
    gap: var(--sp-3);
  }
  
  .result-summary {
    flex-direction: column;
    gap: var(--sp-2);
  }
}
</style>
