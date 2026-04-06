<template>
  <div class="material-page">
    <!-- Header -->
    <header class="page-header">
      <div class="header-content">
        <h1 class="page-title">资料助手</h1>
        <p class="page-subtitle">从在线资料库自动搜索、筛选并下载资料到本地</p>
      </div>
    </header>

    <!-- Config Section -->
    <section class="config-section">
      <div class="section-header">
        <el-icon :size="18"><Setting /></el-icon>
        <span>平台配置</span>
        <el-tag size="small" :type="configSaved ? 'success' : 'info'">
          {{ configSaved ? '已配置' : '未配置' }}
        </el-tag>
      </div>
      <div class="config-body">
        <div class="config-row">
          <div class="config-field">
            <label class="field-label">平台</label>
            <el-select v-model="selectedPlatform" style="width: 200px" @change="loadConfig">
              <el-option label="知网 (CNKI)" value="cnki" />
              <el-option label="知识星球" value="zsxq" />
              <el-option label="微信公众号" value="wechat" />
            </el-select>
          </div>
          <div class="config-field">
            <label class="field-label">用户名</label>
            <el-input v-model="configUsername" placeholder="输入用户名" size="default" />
          </div>
          <div class="config-field">
            <label class="field-label">密码</label>
            <el-input v-model="configPassword" type="password" placeholder="输入密码" size="default" show-password />
          </div>
          <button class="save-btn" @click="saveConfig" :disabled="!configUsername || !configPassword">
            <el-icon :size="14"><Check /></el-icon>
            <span>保存配置</span>
          </button>
        </div>
      </div>
    </section>

    <!-- Task Section -->
    <section class="task-section">
      <div class="section-header">
        <el-icon :size="18"><Download /></el-icon>
        <span>新建下载任务</span>
      </div>
      <div class="task-body">
        <div class="task-row">
          <div class="task-field" style="flex: 2">
            <label class="field-label">搜索关键词</label>
            <el-input
              v-model="keywords"
              placeholder="输入关键词，多个关键词用逗号分隔"
              size="default"
              @keyup.enter="startTask"
            />
          </div>
          <div class="task-field">
            <label class="field-label">最大下载数</label>
            <el-input-number v-model="maxResults" :min="1" :max="50" :step="5" size="default" />
          </div>
        </div>
        <div class="task-row">
          <div class="task-field" style="flex: 2">
            <label class="field-label">下载目录</label>
            <div class="dir-picker">
              <el-input v-model="destDir" placeholder="选择下载目录" size="default" readonly />
              <button class="browse-btn" @click="selectFolder">
                <el-icon :size="14"><FolderOpened /></el-icon>
                浏览
              </button>
            </div>
          </div>
          <div class="task-field" style="align-self: flex-end">
            <button
              class="start-btn"
              @click="startTask"
              :disabled="!keywords || !destDir || taskRunning"
            >
              <el-icon :size="16"><VideoPlay v-if="!taskRunning" /><Loading v-else class="spin" /></el-icon>
              <span>{{ taskRunning ? '执行中...' : '开始下载' }}</span>
            </button>
          </div>
        </div>
      </div>
    </section>

    <!-- Progress Section -->
    <section v-if="currentTask" class="progress-section">
      <div class="section-header">
        <el-icon :size="18"><Loading v-if="taskRunning" class="spin" /><CircleCheck v-else /></el-icon>
        <span>任务进度</span>
        <el-tag size="small" :type="statusTagType">{{ statusLabel }}</el-tag>
      </div>
      <div class="progress-body">
        <div class="progress-stats">
          <div class="stat-item">
            <span class="stat-value">{{ currentTask.total_found }}</span>
            <span class="stat-label">搜索到</span>
          </div>
          <div class="stat-item">
            <span class="stat-value">{{ currentTask.filtered_count }}</span>
            <span class="stat-label">筛选后</span>
          </div>
          <div class="stat-item success">
            <span class="stat-value">{{ currentTask.downloaded_count }}</span>
            <span class="stat-label">已下载</span>
          </div>
          <div class="stat-item error">
            <span class="stat-value">{{ currentTask.failed_count }}</span>
            <span class="stat-label">失败</span>
          </div>
        </div>
        <el-progress
          :percentage="Math.round(currentTask.progress_percent)"
          :status="progressStatus"
          :stroke-width="8"
        />
        <p class="progress-message">{{ currentTask.progress_message }}</p>

        <!-- Download Results -->
        <div v-if="currentTask.results?.length" class="results-list">
          <div class="results-header">下载结果</div>
          <div
            v-for="(r, i) in currentTask.results"
            :key="i"
            class="result-item"
            :class="r.status"
          >
            <el-icon :size="14">
              <CircleCheck v-if="r.status === 'success'" />
              <CircleClose v-else />
            </el-icon>
            <span class="result-title">{{ r.title }}</span>
            <span v-if="r.size" class="result-size">{{ formatSize(r.size) }}</span>
            <span v-if="r.error" class="result-error">{{ r.error }}</span>
          </div>
        </div>
      </div>
    </section>

    <!-- History Section -->
    <section class="history-section">
      <div class="section-header">
        <el-icon :size="18"><Clock /></el-icon>
        <span>历史任务</span>
        <span class="doc-count">{{ tasks.length }} 个</span>
        <div class="header-actions">
          <button class="refresh-btn" @click="loadTasks" :disabled="loadingTasks">
            <el-icon :size="16"><Refresh v-if="!loadingTasks" /><Loading v-else class="spin" /></el-icon>
          </button>
        </div>
      </div>

      <div v-if="!tasks.length" class="empty-state">
        <div class="empty-icon">
          <el-icon :size="32"><Download /></el-icon>
        </div>
        <p>暂无下载任务</p>
      </div>

      <div v-else class="task-list">
        <div
          v-for="(t, i) in tasks"
          :key="t.id"
          class="task-item"
          :style="{ '--delay': i }"
        >
          <div class="task-icon" :class="t.status">
            <el-icon :size="16">
              <CircleCheck v-if="t.status === 'completed'" />
              <CircleClose v-else-if="t.status === 'failed'" />
              <Loading v-else class="spin" />
            </el-icon>
          </div>
          <div class="task-info">
            <span class="task-keywords">{{ t.keywords?.join(', ') }}</span>
            <span class="task-meta">
              {{ t.platform }} · {{ t.downloaded_count }}/{{ t.filtered_count }} 文件
              · {{ formatTime(t.created_at) }}
            </span>
          </div>
          <button class="delete-btn" @click="deleteTask(t.id)">
            <el-icon :size="16"><Delete /></el-icon>
          </button>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import {
  Setting, Download, Check, FolderOpened, VideoPlay, Loading,
  CircleCheck, CircleClose, Delete, Clock, Refresh
} from '@element-plus/icons-vue'
import api from '@/composables/useApi'

// ── 配置 ────────────────────────────────────────────────────
const selectedPlatform = ref('cnki')
const configUsername = ref('')
const configPassword = ref('')
const configSaved = ref(false)

async function loadConfig() {
  try {
    const { data } = await api.get(`/material/config/${selectedPlatform.value}`)
    if (data.ok) {
      configUsername.value = data.data.username || ''
      configSaved.value = data.data.has_password
    }
  } catch { /* ignore */ }
}

async function saveConfig() {
  try {
    const { data } = await api.post('/material/config', {
      platform: selectedPlatform.value,
      username: configUsername.value,
      password: configPassword.value,
    })
    if (data.ok) {
      ElMessage.success('配置已保存')
      configSaved.value = true
      configPassword.value = ''
    } else {
      ElMessage.error(data.message)
    }
  } catch {
    ElMessage.error('保存失败')
  }
}

// ── 任务 ────────────────────────────────────────────────────
const keywords = ref('')
const maxResults = ref(20)
const destDir = ref('')
const taskRunning = ref(false)
const currentTask = ref<any>(null)
const tasks = ref<any[]>([])
const loadingTasks = ref(false)
let sseSource: EventSource | null = null

async function selectFolder() {
  try {
    const { data } = await api.post('/file-dialog/select-folder', {
      title: '选择资料下载目录',
    })
    if (data.ok && data.data?.path) {
      destDir.value = data.data.path
    }
  } catch {
    ElMessage.error('无法打开文件夹选择器')
  }
}

async function startTask() {
  if (!keywords.value || !destDir.value) {
    ElMessage.warning('请填写关键词和选择下载目录')
    return
  }

  taskRunning.value = true
  const keywordList = keywords.value.split(/[,，]/).map(k => k.trim()).filter(Boolean)

  try {
    const { data } = await api.post('/material/task', {
      platform: selectedPlatform.value,
      keywords: keywordList,
      dest_dir: destDir.value,
      max_results: maxResults.value,
    })

    if (data.ok) {
      currentTask.value = data.data
      ElMessage.success('任务已创建')
      // 开启 SSE 进度监听
      startProgressSSE(data.data.id)
    } else {
      ElMessage.error(data.message)
      taskRunning.value = false
    }
  } catch {
    ElMessage.error('创建任务失败')
    taskRunning.value = false
  }
}

function startProgressSSE(taskId: string) {
  if (sseSource) sseSource.close()

  sseSource = new EventSource(`/api/material/task/${taskId}/progress`)
  sseSource.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data)
      if (data.error) {
        ElMessage.error(data.error)
        stopSSE()
        return
      }
      currentTask.value = data

      if (['completed', 'failed', 'cancelled'].includes(data.status)) {
        stopSSE()
        loadTasks()
      }
    } catch { /* ignore parse errors */ }
  }
  sseSource.onerror = () => stopSSE()
}

function stopSSE() {
  taskRunning.value = false
  if (sseSource) {
    sseSource.close()
    sseSource = null
  }
}

async function loadTasks() {
  loadingTasks.value = true
  try {
    const { data } = await api.get('/material/tasks?limit=20')
    if (data.ok) {
      tasks.value = data.data
    }
  } finally {
    loadingTasks.value = false
  }
}

async function deleteTask(taskId: string) {
  try {
    const { data } = await api.delete(`/material/task/${taskId}`)
    if (data.ok) {
      ElMessage.success('已删除')
      loadTasks()
    }
  } catch {
    ElMessage.error('删除失败')
  }
}

// ── 计算属性 ────────────────────────────────────────────────
const statusLabel = computed(() => {
  const map: Record<string, string> = {
    pending: '等待中', logging_in: '登录中', searching: '搜索中',
    filtering: '筛选中', downloading: '下载中',
    completed: '已完成', failed: '失败', cancelled: '已取消',
  }
  return map[currentTask.value?.status] || currentTask.value?.status || ''
})

const statusTagType = computed(() => {
  const s = currentTask.value?.status
  if (s === 'completed') return 'success'
  if (s === 'failed') return 'danger'
  if (['downloading', 'searching', 'filtering'].includes(s)) return 'warning'
  return 'info'
})

const progressStatus = computed(() => {
  const s = currentTask.value?.status
  if (s === 'completed') return 'success'
  if (s === 'failed') return 'exception'
  return undefined
})

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function formatTime(ts: number): string {
  if (!ts) return ''
  return new Date(ts * 1000).toLocaleString('zh-CN', {
    month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit',
  })
}

onMounted(() => {
  loadConfig()
  loadTasks()
})

onUnmounted(() => stopSSE())
</script>

<style scoped>
.material-page {
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
.page-header { margin-bottom: var(--sp-6); }
.page-title {
  font-size: var(--fs-xl); font-weight: 600;
  color: var(--c-text-primary); margin: 0 0 var(--sp-1);
  letter-spacing: -0.5px;
}
.page-subtitle {
  font-size: var(--fs-sm); color: var(--c-text-tertiary); margin: 0;
}

/* Sections */
.config-section, .task-section, .progress-section, .history-section {
  background: var(--glass-bg);
  backdrop-filter: blur(var(--glass-blur));
  border: 1px solid var(--c-border);
  border-radius: var(--radius);
  margin-bottom: var(--sp-5);
  animation: sectionEnter 0.4s var(--ease);
}

@keyframes sectionEnter {
  from { opacity: 0; transform: translateY(16px); }
  to { opacity: 1; transform: translateY(0); }
}

.section-header {
  display: flex; align-items: center; gap: var(--sp-2);
  padding: var(--sp-4) var(--sp-5);
  background: var(--c-surface);
  border-bottom: 1px solid var(--c-border);
  font-size: var(--fs-sm); font-weight: 500;
  color: var(--c-text-primary);
}

.config-body, .task-body, .progress-body {
  padding: var(--sp-5);
}

/* Config & Task rows */
.config-row, .task-row {
  display: flex; align-items: flex-end; gap: var(--sp-4);
  flex-wrap: wrap;
}
.task-row + .task-row { margin-top: var(--sp-4); }

.config-field, .task-field {
  flex: 1; min-width: 180px;
}

.field-label {
  display: block; font-size: var(--fs-xs);
  color: var(--c-text-tertiary); margin-bottom: var(--sp-1);
  text-transform: uppercase; letter-spacing: 0.3px;
}

/* Buttons */
.save-btn, .start-btn {
  display: flex; align-items: center; gap: var(--sp-1);
  padding: 0 var(--sp-4); height: 32px;
  border-radius: var(--radius-sm); font-size: var(--fs-sm);
  cursor: pointer; transition: all var(--duration) var(--ease);
  border: none; white-space: nowrap;
}
.save-btn {
  background: rgba(59,130,246,0.15); color: #60a5fa;
  border: 1px solid rgba(59,130,246,0.3);
}
.save-btn:hover:not(:disabled) {
  background: rgba(59,130,246,0.25);
}
.start-btn {
  background: linear-gradient(135deg, #3b82f6, #8b5cf6);
  color: white; padding: 0 var(--sp-5); height: 36px;
  font-weight: 500;
}
.start-btn:hover:not(:disabled) {
  filter: brightness(1.1); transform: translateY(-1px);
}
.start-btn:disabled, .save-btn:disabled {
  opacity: 0.4; cursor: not-allowed;
}

.dir-picker {
  display: flex; gap: var(--sp-2);
}
.browse-btn {
  display: flex; align-items: center; gap: 4px;
  padding: 0 var(--sp-3); height: 32px;
  background: var(--glass-bg); border: 1px solid var(--c-border);
  border-radius: var(--radius-sm); color: var(--c-text-secondary);
  font-size: var(--fs-xs); cursor: pointer;
  transition: all var(--duration) var(--ease); white-space: nowrap;
}
.browse-btn:hover {
  background: var(--c-surface-hover); border-color: var(--c-border-hover);
  color: var(--c-text-primary);
}

/* Progress */
.progress-stats {
  display: flex; gap: var(--sp-4); margin-bottom: var(--sp-4);
}
.stat-item {
  display: flex; flex-direction: column; align-items: center;
  padding: var(--sp-3) var(--sp-4);
  background: var(--c-surface); border: 1px solid var(--c-border);
  border-radius: var(--radius-sm); min-width: 80px;
}
.stat-value {
  font-size: var(--fs-lg); font-weight: 600; color: var(--c-text-primary);
}
.stat-item.success .stat-value { color: #34d399; }
.stat-item.error .stat-value { color: #f87171; }
.stat-label {
  font-size: 11px; color: var(--c-text-tertiary); margin-top: 2px;
}
.progress-message {
  font-size: var(--fs-sm); color: var(--c-text-secondary);
  margin: var(--sp-3) 0 0;
}

/* Results */
.results-list {
  margin-top: var(--sp-4);
  max-height: 300px; overflow-y: auto;
}
.results-header {
  font-size: var(--fs-xs); color: var(--c-text-tertiary);
  margin-bottom: var(--sp-2); text-transform: uppercase;
  letter-spacing: 0.5px;
}
.result-item {
  display: flex; align-items: center; gap: var(--sp-2);
  padding: var(--sp-2) var(--sp-3);
  font-size: var(--fs-sm); border-radius: var(--radius-sm);
  margin-bottom: 2px;
}
.result-item.success { color: #34d399; background: rgba(34,197,94,0.05); }
.result-item.failed { color: #f87171; background: rgba(239,68,68,0.05); }
.result-title {
  flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  color: var(--c-text-primary);
}
.result-size { font-size: 11px; color: var(--c-text-tertiary); }
.result-error { font-size: 11px; color: #f87171; }

/* History */
.header-actions { margin-left: auto; }
.doc-count {
  font-size: 11px; color: var(--c-text-tertiary);
  background: var(--c-surface); padding: 2px var(--sp-2);
  border-radius: var(--radius-xs); margin-left: var(--sp-2);
}
.empty-state {
  display: flex; flex-direction: column; align-items: center;
  padding: var(--sp-8);
}
.empty-icon {
  width: 64px; height: 64px; display: flex; align-items: center;
  justify-content: center; background: var(--c-surface);
  border-radius: var(--radius); color: var(--c-text-tertiary);
  margin-bottom: var(--sp-3);
}
.empty-state p { font-size: var(--fs-sm); color: var(--c-text-tertiary); margin: 0; }

.task-list { padding: var(--sp-3); max-height: 400px; overflow-y: auto; }
.task-item {
  display: flex; align-items: center; gap: var(--sp-3);
  padding: var(--sp-3); background: var(--c-surface);
  border: 1px solid var(--c-border); border-radius: var(--radius-sm);
  margin-bottom: var(--sp-2); transition: all var(--duration) var(--ease);
  animation: docEnter 0.3s var(--ease) calc(var(--delay) * 0.03s) both;
}
.task-item:hover {
  background: var(--c-surface-hover); border-color: var(--c-border-hover);
}
@keyframes docEnter {
  from { opacity: 0; transform: translateX(-8px); }
  to { opacity: 1; transform: translateX(0); }
}

.task-icon {
  width: 36px; height: 36px; display: flex; align-items: center;
  justify-content: center; border-radius: var(--radius-xs); flex-shrink: 0;
}
.task-icon.completed { background: rgba(34,197,94,0.1); color: #34d399; }
.task-icon.failed { background: rgba(239,68,68,0.1); color: #f87171; }
.task-icon:not(.completed):not(.failed) { background: rgba(59,130,246,0.1); color: #60a5fa; }

.task-info { flex: 1; min-width: 0; }
.task-keywords {
  display: block; font-size: var(--fs-sm); color: var(--c-text-primary);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.task-meta {
  display: block; font-size: 11px; color: var(--c-text-tertiary); margin-top: 2px;
}

.delete-btn {
  display: flex; align-items: center; justify-content: center;
  width: 32px; height: 32px; background: transparent;
  border: 1px solid transparent; border-radius: var(--radius-xs);
  color: var(--c-text-tertiary); cursor: pointer;
  transition: all var(--duration) var(--ease); flex-shrink: 0;
}
.delete-btn:hover {
  background: rgba(239,68,68,0.1); border-color: rgba(239,68,68,0.3);
  color: #f87171;
}
.refresh-btn {
  display: flex; align-items: center; justify-content: center;
  width: 32px; height: 32px; background: var(--glass-bg);
  border: 1px solid var(--c-border); border-radius: var(--radius-xs);
  color: var(--c-text-secondary); cursor: pointer;
  transition: all var(--duration) var(--ease);
}
.refresh-btn:hover:not(:disabled) {
  background: var(--c-surface-hover); border-color: var(--c-border-hover);
  color: var(--c-text-primary);
}
.refresh-btn:disabled { opacity: 0.5; cursor: not-allowed; }

/* Spin */
.spin { animation: spin 1s linear infinite; }
@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
</style>
