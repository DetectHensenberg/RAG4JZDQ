<template>
  <div class="config-page">
    <!-- Header -->
    <header class="page-header">
      <div class="header-content">
        <h1 class="page-title">系统配置</h1>
        <p class="page-subtitle">管理 API Key、模型配置和系统参数</p>
      </div>
    </header>

    <!-- Loading State -->
    <div v-if="!config" class="loading-grid">
      <div v-for="i in 5" :key="i" class="skeleton-card">
        <div class="skeleton-line skeleton-title"></div>
        <div class="skeleton-line skeleton-field"></div>
        <div class="skeleton-line skeleton-field"></div>
      </div>
    </div>

    <!-- Config Form -->
    <div v-else class="config-grid">
      <!-- API Key Section -->
      <section class="config-section" style="--delay: 0">
        <div class="section-header">
          <el-icon :size="18"><Key /></el-icon>
          <span>API Key</span>
          <span v-if="apiKeyMasked" class="status-badge status-success">已配置</span>
          <span v-else class="status-badge status-warning">未配置</span>
        </div>
        <div class="section-body">
          <div v-if="apiKeyMasked" class="api-status">
            <el-icon :size="16"><CircleCheck /></el-icon>
            <span>{{ apiKeyMasked }}</span>
          </div>
          <div class="field-row">
            <label class="field-label">新 API Key</label>
            <el-input
              v-model="newApiKey"
              type="password"
              placeholder="输入新 Key（留空保持不变）"
              show-password
            />
          </div>
          <div class="field-actions">
            <button class="action-btn" @click="testConnection" :disabled="testing">
              <el-icon :size="16"><Connection v-if="!testing" /><Loading v-else class="spin" /></el-icon>
              <span>{{ testing ? '测试中...' : '测试连接' }}</span>
            </button>
            <span v-if="testResult" class="test-result" :class="testResult.ok ? 'success' : 'error'">
              {{ testResult.message }}
            </span>
          </div>
        </div>
      </section>

      <!-- LLM Config -->
      <section class="config-section" style="--delay: 1">
        <div class="section-header">
          <el-icon :size="18"><Cpu /></el-icon>
          <span>LLM 配置</span>
        </div>
        <div class="section-body">
          <div class="field-row">
            <label class="field-label">Provider</label>
            <el-select v-model="llmPreset" @change="onLlmPresetChange" class="w-full">
              <el-option v-for="p in llmPresets" :key="p.label" :label="p.label" :value="p.label" />
            </el-select>
          </div>
          <div class="field-row">
            <label class="field-label">模型</label>
            <el-select v-model="config.llm.model" filterable allow-create class="w-full">
              <el-option v-for="m in currentLlmModels" :key="m" :label="m" :value="m" />
            </el-select>
          </div>
          <div class="field-row">
            <label class="field-label">Base URL</label>
            <el-input v-model="config.llm.base_url" />
          </div>
          <div class="field-row-cols">
            <div class="field-col">
              <label class="field-label">Temperature</label>
              <div class="slider-field">
                <el-slider v-model="config.llm.temperature" :min="0" :max="2" :step="0.1" />
                <span class="slider-value">{{ config.llm.temperature }}</span>
              </div>
            </div>
            <div class="field-col">
              <label class="field-label">Max Tokens</label>
              <el-input-number v-model="config.llm.max_tokens" :min="256" :max="32768" :step="256" class="w-full" />
            </div>
          </div>
        </div>
      </section>

      <!-- Embedding Config -->
      <section class="config-section" style="--delay: 2">
        <div class="section-header">
          <el-icon :size="18"><DataAnalysis /></el-icon>
          <span>Embedding 配置</span>
        </div>
        <div class="section-body">
          <div class="field-row">
            <label class="field-label">Provider</label>
            <el-select v-model="embPreset" @change="onEmbPresetChange" class="w-full">
              <el-option v-for="p in embPresets" :key="p.label" :label="p.label" :value="p.label" />
            </el-select>
          </div>
          <div class="field-row">
            <label class="field-label">模型</label>
            <el-select v-model="config.embedding.model" filterable allow-create class="w-full">
              <el-option v-for="m in currentEmbModels" :key="m" :label="m" :value="m" />
            </el-select>
          </div>
          <div class="field-row">
            <label class="field-label">Base URL</label>
            <el-input v-model="config.embedding.base_url" />
          </div>
          <div class="field-row">
            <label class="field-label">向量维度</label>
            <el-input-number v-model="config.embedding.dimensions" :min="128" :max="4096" :step="128" class="w-full" />
          </div>
        </div>
      </section>

      <!-- Retrieval Config -->
      <section class="config-section" style="--delay: 3">
        <div class="section-header">
          <el-icon :size="18"><Search /></el-icon>
          <span>检索配置</span>
        </div>
        <div class="section-body">
          <div class="field-row-cols field-row-cols-3">
            <div class="field-col">
              <label class="field-label">Dense K</label>
              <el-input-number v-model="config.retrieval.dense_top_k" :min="1" :max="100" class="w-full" />
            </div>
            <div class="field-col">
              <label class="field-label">Sparse K</label>
              <el-input-number v-model="config.retrieval.sparse_top_k" :min="1" :max="100" class="w-full" />
            </div>
            <div class="field-col">
              <label class="field-label">Fusion K</label>
              <el-input-number v-model="config.retrieval.fusion_top_k" :min="1" :max="50" class="w-full" />
            </div>
          </div>
        </div>
      </section>

      <!-- Ingestion Config -->
      <section class="config-section" style="--delay: 4">
        <div class="section-header">
          <el-icon :size="18"><Upload /></el-icon>
          <span>摄取配置</span>
        </div>
        <div class="section-body">
          <div class="field-row-cols field-row-cols-3">
            <div class="field-col">
              <label class="field-label">分块大小</label>
              <el-input-number v-model="config.ingestion.chunk_size" :min="200" :max="5000" :step="100" class="w-full" />
            </div>
            <div class="field-col">
              <label class="field-label">分块重叠</label>
              <el-input-number v-model="config.ingestion.chunk_overlap" :min="0" :max="1000" :step="50" class="w-full" />
            </div>
            <div class="field-col">
              <label class="field-label">LLM 精炼</label>
              <div class="switch-field">
                <el-switch v-model="useLlmRefine" />
                <span class="switch-label">{{ useLlmRefine ? '启用' : '禁用' }}</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- Company Documents -->
      <section class="config-section company-docs-section" style="--delay: 5">
        <div class="section-header">
          <el-icon :size="18"><FolderOpened /></el-icon>
          <span>我司资料设置</span>
          <span v-if="companyDocs.length" class="status-badge status-success">{{ companyDocs.length }} 份文件</span>
          <span v-else class="status-badge status-warning">未导入</span>
        </div>
        <div class="section-body">
          <p class="section-desc">上传资格性响应文件PDF，系统将自动解析并提取各独立文件内容，用于标书编写时自动匹配填充。</p>
          
          <!-- Upload area -->
          <div class="upload-area" v-if="!importing">
            <input type="file" ref="companyDocInput" accept=".pdf" @change="onCompanyDocSelect" hidden />
            <button class="upload-btn" @click="($refs.companyDocInput as any).click()">
              <el-icon :size="20"><Upload /></el-icon>
              <span>上传资格性响应文件 PDF</span>
            </button>
          </div>
          <div v-else class="importing-box">
            <el-icon class="is-loading" :size="20"><Loading /></el-icon>
            <span>正在解析PDF，识别文件结构...</span>
          </div>

          <!-- Document list -->
          <div v-if="companyDocs.length" class="docs-list">
            <div class="docs-header">
              <span>已导入文件</span>
              <button class="clear-btn" @click="clearCompanyDocs" :disabled="clearingDocs">
                <el-icon :size="14"><Delete /></el-icon>
                <span>清空全部</span>
              </button>
            </div>
            <div class="docs-grid">
              <div v-for="doc in companyDocs" :key="doc.id" class="doc-card" @click="showDocDetail(doc)">
                <div class="doc-icon">
                  <el-icon :size="20"><Document /></el-icon>
                </div>
                <div class="doc-info">
                  <div class="doc-name">{{ doc.doc_name }}</div>
                  <div class="doc-meta">
                    <span class="doc-category">{{ categoryLabel(doc.category) }}</span>
                    <span v-if="doc.page_start">P{{ doc.page_start }}-{{ doc.page_end }}</span>
                  </div>
                </div>
                <button class="doc-delete" @click.stop="deleteDoc(doc.id)" title="删除">
                  <el-icon :size="14"><Close /></el-icon>
                </button>
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- Actions -->
      <div class="config-actions">
        <button class="save-btn" @click="saveConfig" :disabled="saving">
          <el-icon :size="18"><Check v-if="!saving" /><Loading v-else class="spin" /></el-icon>
          <span>{{ saving ? '保存中...' : '保存配置' }}</span>
        </button>
        <button class="reset-btn" @click="resetConfig">
          <el-icon :size="18"><RefreshRight /></el-icon>
          <span>重置为默认</span>
        </button>
      </div>

      <!-- Danger Zone -->
      <section class="danger-section">
        <div class="section-header">
          <el-icon :size="18"><Warning /></el-icon>
          <span>危险操作</span>
        </div>
        <div class="section-body">
          <div class="danger-item">
            <div class="danger-info">
              <span class="danger-title">清空所有数据</span>
              <span class="danger-desc">删除所有向量数据、BM25索引、图片和摄取历史，此操作不可恢复</span>
            </div>
            <button class="danger-btn" @click="confirmClearData" :disabled="clearing">
              <el-icon :size="16"><Delete v-if="!clearing" /><Loading v-else class="spin" /></el-icon>
              <span>{{ clearing ? '清空中...' : '清空数据' }}</span>
            </button>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { 
  Key, CircleCheck, Connection, Loading, Cpu, DataAnalysis, 
  Search, Upload, Check, RefreshRight, Delete, Warning,
  FolderOpened, Document, Close
} from '@element-plus/icons-vue'
import api from '@/composables/useApi'

const config = ref<any>(null)
const apiKeyMasked = ref('')
const newApiKey = ref('')
const testing = ref(false)
const saving = ref(false)
const testResult = ref<{ ok: boolean; message: string } | null>(null)
const useLlmRefine = ref(false)
const clearing = ref(false)

// Company documents
const companyDocs = ref<any[]>([])
const importing = ref(false)
const clearingDocs = ref(false)
const companyDocInput = ref<HTMLInputElement | null>(null)

// Presets
const llmPresets = [
  { label: 'DashScope (千问)', provider: 'openai', base_url: 'https://dashscope.aliyuncs.com/compatible-mode/v1', models: ['qwen-plus', 'qwen-turbo', 'qwen-max', 'qwen-long'] },
  { label: 'OpenAI', provider: 'openai', base_url: 'https://api.openai.com/v1', models: ['gpt-4o', 'gpt-4o-mini', 'gpt-4-turbo', 'gpt-3.5-turbo'] },
  { label: 'DeepSeek', provider: 'deepseek', base_url: 'https://api.deepseek.com/v1', models: ['deepseek-chat', 'deepseek-reasoner'] },
  { label: 'Ollama', provider: 'ollama', base_url: 'http://localhost:11434/v1', models: ['llama3', 'qwen2', 'mistral'] },
  { label: '自定义', provider: 'openai', base_url: '', models: [] },
]
const embPresets = [
  { label: 'DashScope', provider: 'openai', base_url: 'https://dashscope.aliyuncs.com/compatible-mode/v1', models: ['text-embedding-v3', 'text-embedding-v2'] },
  { label: 'OpenAI', provider: 'openai', base_url: 'https://api.openai.com/v1', models: ['text-embedding-3-small', 'text-embedding-3-large'] },
  { label: 'Ollama', provider: 'ollama', base_url: 'http://localhost:11434/v1', models: ['nomic-embed-text'] },
  { label: '自定义', provider: 'openai', base_url: '', models: [] },
]

const llmPreset = ref('自定义')
const embPreset = ref('自定义')

const currentLlmModels = computed(() => {
  const p = llmPresets.find(x => x.label === llmPreset.value)
  const models = p?.models || []
  if (config.value?.llm?.model && !models.includes(config.value.llm.model)) {
    return [config.value.llm.model, ...models]
  }
  return models
})

const currentEmbModels = computed(() => {
  const p = embPresets.find(x => x.label === embPreset.value)
  const models = p?.models || []
  if (config.value?.embedding?.model && !models.includes(config.value.embedding.model)) {
    return [config.value.embedding.model, ...models]
  }
  return models
})

function detectPreset(baseUrl: string, presets: typeof llmPresets) {
  for (const p of presets) {
    if (p.base_url && baseUrl?.includes(p.base_url)) return p.label
  }
  return '自定义'
}

function onLlmPresetChange(label: string) {
  const p = llmPresets.find(x => x.label === label)
  if (p && p.base_url && config.value) {
    config.value.llm.base_url = p.base_url
    config.value.llm.provider = p.provider
    if (p.models.length) config.value.llm.model = p.models[0]
  }
}

function onEmbPresetChange(label: string) {
  const p = embPresets.find(x => x.label === label)
  if (p && p.base_url && config.value) {
    config.value.embedding.base_url = p.base_url
    config.value.embedding.provider = p.provider
    if (p.models.length) config.value.embedding.model = p.models[0]
  }
}

async function loadConfig() {
  const { data } = await api.get('/config')
  config.value = data.data.config
  apiKeyMasked.value = data.data.api_key_masked
  llmPreset.value = detectPreset(config.value?.llm?.base_url, llmPresets)
  embPreset.value = detectPreset(config.value?.embedding?.base_url, embPresets)
  useLlmRefine.value = config.value?.ingestion?.chunk_refiner?.use_llm || false
}

async function saveConfig() {
  saving.value = true
  try {
    if (config.value.ingestion) {
      config.value.ingestion.chunk_refiner = { use_llm: useLlmRefine.value }
    }
    await api.put('/config', { config: config.value, api_key: newApiKey.value || undefined })
    ElMessage.success('配置已保存')
    newApiKey.value = ''
    await loadConfig()
  } catch {
    ElMessage.error('保存失败')
  } finally {
    saving.value = false
  }
}

async function testConnection() {
  testing.value = true
  testResult.value = null
  try {
    const { data } = await api.post('/config/test', {
      api_key: newApiKey.value || '',
      base_url: config.value?.llm?.base_url || '',
      model: config.value?.llm?.model || '',
    })
    testResult.value = data
  } catch {
    testResult.value = { ok: false, message: '请求失败' }
  } finally {
    testing.value = false
  }
}

async function resetConfig() {
  try {
    await api.put('/config', { config: {} })
    ElMessage.success('已重置')
    await loadConfig()
  } catch {
    ElMessage.error('重置失败')
  }
}

async function confirmClearData() {
  if (!confirm('确定要清空所有数据吗？此操作不可恢复！')) return
  
  clearing.value = true
  try {
    const { data } = await api.delete('/data-manage/clear-all')
    if (data.ok) {
      ElMessage.success('数据已清空')
    } else {
      ElMessage.error(data.message || '清空失败')
    }
  } catch {
    ElMessage.error('清空失败')
  } finally {
    clearing.value = false
  }
}

// ── Company Documents ───────────────────────────────────

const categoryLabels: Record<string, string> = {
  certificate: '资质证书',
  financial: '财务类',
  declaration: '声明承诺',
  license: '证照类',
  other: '其他',
}

function categoryLabel(cat: string) {
  return categoryLabels[cat] || cat
}

async function loadCompanyDocs() {
  try {
    const { data } = await api.get('/bid-document/company-docs')
    if (data.ok) {
      companyDocs.value = data.docs || []
    }
  } catch (e) {
    console.error('Load company docs failed:', e)
  }
}

async function onCompanyDocSelect(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (!file) return

  importing.value = true
  const formData = new FormData()
  formData.append('file', file)

  try {
    const { data } = await api.post('/bid-document/company-docs/import', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 180000,
    })
    if (data.ok) {
      companyDocs.value = data.docs || []
      ElMessage.success(data.message || `成功导入 ${data.docs?.length || 0} 个文件`)
    } else {
      ElMessage.error(data.message || '导入失败')
    }
  } catch (err: any) {
    ElMessage.error(err.message || '导入失败')
  } finally {
    importing.value = false
    if (companyDocInput.value) companyDocInput.value.value = ''
  }
}

async function deleteDoc(docId: number) {
  try {
    await ElMessageBox.confirm('确定删除此文件？', '确认删除', { type: 'warning' })
    const { data } = await api.delete(`/bid-document/company-docs/${docId}`)
    if (data.ok) {
      companyDocs.value = companyDocs.value.filter(d => d.id !== docId)
      ElMessage.success('已删除')
    } else {
      ElMessage.error(data.message || '删除失败')
    }
  } catch {
    // cancelled
  }
}

async function clearCompanyDocs() {
  try {
    await ElMessageBox.confirm('确定清空所有我司资料？', '确认清空', { type: 'warning' })
    clearingDocs.value = true
    // Delete one by one since there's no clear all API
    for (const doc of companyDocs.value) {
      await api.delete(`/bid-document/company-docs/${doc.id}`)
    }
    companyDocs.value = []
    ElMessage.success('已清空')
  } catch {
    // cancelled
  } finally {
    clearingDocs.value = false
  }
}

function showDocDetail(doc: any) {
  ElMessageBox.alert(doc.content?.slice(0, 500) || '(无内容)', doc.doc_name, {
    confirmButtonText: '关闭',
    customClass: 'doc-detail-dialog',
  })
}

onMounted(() => {
  loadConfig()
  loadCompanyDocs()
})
</script>

<style scoped>
.config-page {
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

/* Loading State */
.loading-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
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
  height: 16px;
  width: 40%;
  margin-bottom: var(--sp-4);
}

.skeleton-field {
  height: 40px;
  width: 100%;
  margin-bottom: var(--sp-2);
}

@keyframes skeletonPulse {
  0%, 100% { opacity: 0.6; }
  50% { opacity: 1; }
}

/* Config Grid */
.config-grid {
  display: flex;
  flex-direction: column;
  gap: var(--card-gap);
  max-width: 800px;
}

/* Config Section */
.config-section {
  background: var(--glass-bg);
  backdrop-filter: blur(var(--glass-blur));
  border: 1px solid var(--c-border);
  border-radius: var(--radius);
  overflow: hidden;
  animation: sectionEnter 0.4s var(--ease) calc(var(--delay) * 0.08s) both;
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

.status-badge {
  margin-left: auto;
  font-size: 11px;
  font-weight: 500;
  padding: 2px var(--sp-2);
  border-radius: var(--radius-xs);
}

.status-success {
  background: rgba(34, 197, 94, 0.15);
  color: #34d399;
}

.status-warning {
  background: rgba(245, 158, 11, 0.15);
  color: #fbbf24;
}

.section-body {
  padding: var(--sp-5);
}

/* Fields */
.field-row {
  margin-bottom: var(--sp-4);
}

.field-row:last-child {
  margin-bottom: 0;
}

.field-label {
  display: block;
  font-size: var(--fs-xs);
  color: var(--c-text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.3px;
  margin-bottom: var(--sp-2);
}

.field-row-cols {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--sp-4);
}

.field-row-cols-3 {
  grid-template-columns: repeat(3, 1fr);
}

.field-col {
  display: flex;
  flex-direction: column;
}

.w-full {
  width: 100%;
}

/* API Status */
.api-status {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  padding: var(--sp-3) var(--sp-4);
  background: rgba(34, 197, 94, 0.08);
  border: 1px solid rgba(34, 197, 94, 0.2);
  border-radius: var(--radius-sm);
  font-size: var(--fs-sm);
  color: #34d399;
  margin-bottom: var(--sp-4);
}

/* Field Actions */
.field-actions {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  margin-top: var(--sp-3);
}

.action-btn {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
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

.action-btn:hover:not(:disabled) {
  background: var(--c-surface-hover);
  border-color: var(--c-border-hover);
  color: var(--c-text-primary);
}

.action-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.test-result {
  font-size: var(--fs-sm);
}

.test-result.success {
  color: #34d399;
}

.test-result.error {
  color: #f87171;
}

/* Slider Field */
.slider-field {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
}

.slider-field .el-slider {
  flex: 1;
}

.slider-value {
  font-size: var(--fs-sm);
  color: var(--c-text-secondary);
  min-width: 32px;
  text-align: right;
  font-variant-numeric: tabular-nums;
}

/* Switch Field */
.switch-field {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  height: var(--input-h);
}

.switch-label {
  font-size: var(--fs-sm);
  color: var(--c-text-secondary);
}

/* Config Actions */
.config-actions {
  display: flex;
  gap: var(--sp-3);
  padding-top: var(--sp-4);
}

.save-btn {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  padding: 0 var(--sp-6);
  height: 44px;
  background: var(--c-accent);
  border: none;
  border-radius: var(--radius-sm);
  color: #0a0a0a;
  font-size: var(--fs-sm);
  font-weight: 500;
  cursor: pointer;
  transition: all var(--duration) var(--ease);
}

.save-btn:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(255,255,255,0.2);
}

.save-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.reset-btn {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  padding: 0 var(--sp-5);
  height: 44px;
  background: var(--glass-bg);
  border: 1px solid var(--c-border);
  border-radius: var(--radius-sm);
  color: var(--c-text-secondary);
  font-size: var(--fs-sm);
  cursor: pointer;
  transition: all var(--duration) var(--ease);
}

.reset-btn:hover {
  background: var(--c-surface-hover);
  border-color: var(--c-border-hover);
  color: var(--c-text-primary);
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
  .field-row-cols,
  .field-row-cols-3 {
    grid-template-columns: 1fr;
  }
  
  .config-actions {
    flex-direction: column;
  }
  
  .save-btn,
  .reset-btn {
    width: 100%;
    justify-content: center;
  }
}

/* Danger Section */
.danger-section {
  margin-top: var(--sp-6);
  background: rgba(239, 68, 68, 0.05);
  border: 1px solid rgba(239, 68, 68, 0.2);
  border-radius: var(--radius);
}

.danger-section .section-header {
  color: #ef4444;
  border-bottom-color: rgba(239, 68, 68, 0.2);
}

.danger-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--sp-4);
}

.danger-info {
  display: flex;
  flex-direction: column;
  gap: var(--sp-1);
}

.danger-title {
  font-size: var(--fs-sm);
  font-weight: 500;
  color: var(--c-text-primary);
}

.danger-desc {
  font-size: var(--fs-xs);
  color: var(--c-text-tertiary);
}

.danger-btn {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  padding: 0 var(--sp-4);
  height: 36px;
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.3);
  border-radius: var(--radius-sm);
  color: #ef4444;
  font-size: var(--fs-sm);
  font-weight: 500;
  cursor: pointer;
  transition: all var(--duration) var(--ease);
}

.danger-btn:hover:not(:disabled) {
  background: rgba(239, 68, 68, 0.2);
  border-color: rgba(239, 68, 68, 0.5);
}

.danger-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Company Documents Section */
.company-docs-section .section-body {
  padding: var(--sp-5);
}

.section-desc {
  font-size: var(--fs-sm);
  color: var(--c-text-tertiary);
  margin: 0 0 var(--sp-4);
}

.upload-area {
  margin-bottom: var(--sp-4);
}

.upload-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--sp-2);
  width: 100%;
  height: 80px;
  background: var(--c-surface);
  border: 2px dashed var(--c-border);
  border-radius: var(--radius);
  color: var(--c-text-secondary);
  font-size: var(--fs-sm);
  cursor: pointer;
  transition: all var(--duration) var(--ease);
}

.upload-btn:hover {
  background: var(--c-surface-hover);
  border-color: var(--c-accent);
  color: var(--c-accent);
}

.importing-box {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--sp-3);
  height: 80px;
  background: var(--c-surface);
  border-radius: var(--radius);
  color: var(--c-text-secondary);
  font-size: var(--fs-sm);
}

.docs-list {
  margin-top: var(--sp-4);
}

.docs-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--sp-3);
  font-size: var(--fs-sm);
  color: var(--c-text-secondary);
}

.clear-btn {
  display: flex;
  align-items: center;
  gap: var(--sp-1);
  padding: 4px var(--sp-2);
  background: transparent;
  border: none;
  border-radius: var(--radius-xs);
  color: var(--c-text-tertiary);
  font-size: var(--fs-xs);
  cursor: pointer;
  transition: all var(--duration) var(--ease);
}

.clear-btn:hover:not(:disabled) {
  background: rgba(239, 68, 68, 0.1);
  color: #ef4444;
}

.clear-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.docs-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: var(--sp-3);
}

.doc-card {
  display: flex;
  align-items: flex-start;
  gap: var(--sp-3);
  padding: var(--sp-3);
  background: var(--c-surface);
  border: 1px solid var(--c-border);
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: all var(--duration) var(--ease);
}

.doc-card:hover {
  background: var(--c-surface-hover);
  border-color: var(--c-border-hover);
}

.doc-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  background: var(--glass-bg);
  border-radius: var(--radius-xs);
  color: var(--c-accent);
  flex-shrink: 0;
}

.doc-info {
  flex: 1;
  min-width: 0;
}

.doc-name {
  font-size: var(--fs-sm);
  font-weight: 500;
  color: var(--c-text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.doc-meta {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  margin-top: var(--sp-1);
  font-size: var(--fs-xs);
  color: var(--c-text-tertiary);
}

.doc-category {
  padding: 1px var(--sp-1);
  background: var(--glass-bg);
  border-radius: 2px;
}

.doc-delete {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  background: transparent;
  border: none;
  border-radius: var(--radius-xs);
  color: var(--c-text-tertiary);
  cursor: pointer;
  opacity: 0;
  transition: all var(--duration) var(--ease);
}

.doc-card:hover .doc-delete {
  opacity: 1;
}

.doc-delete:hover {
  background: rgba(239, 68, 68, 0.1);
  color: #ef4444;
}
</style>
