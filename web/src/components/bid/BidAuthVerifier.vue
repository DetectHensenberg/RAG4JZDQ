<template>
  <div class="verifier-page">
    <!-- Hidden file input (must be outside v-for for ref to work) -->
    <input
      ref="fileInputRef"
      type="file"
      accept=".pdf,.docx,.doc"
      style="display:none"
      @change="handleFileSelect"
    />
    <!-- Messages Area -->
    <div ref="messagesRef" class="messages-area">
      <!-- Empty state -->
      <div v-if="!messages.length && !streaming" class="empty-state">
        <div class="empty-icon">
          <el-icon :size="32"><Document /></el-icon>
        </div>
        <h3>产品技术资料真伪性辨别</h3>
        <p>输入招标文件中的技术要求，我将帮您匹配产品、比对参数真伪</p>
      </div>

      <!-- Message list -->
      <div class="messages-list">
        <div v-for="(msg, i) in messages" :key="i" class="message" :class="msg.role">
          <div class="message-bubble">
            <!-- User text -->
            <div v-if="msg.role === 'user'" class="message-text">{{ msg.content }}</div>

            <!-- System/assistant text -->
            <template v-else-if="msg.type === 'text'">
              <div v-html="renderMd(msg.content)" class="message-content" />
            </template>

            <!-- Product cards -->
            <template v-else-if="msg.type === 'product-cards'">
              <div class="message-content">
                <p style="margin-bottom:12px">为您找到以下匹配产品，请点击选择：</p>
              </div>
              <div class="product-grid">
                <div
                  v-for="(p, j) in msg.products"
                  :key="j"
                  class="product-card"
                  :class="{ selected: selectedProduct?.index === j }"
                  @click="selectProduct(p, j)"
                >
                  <div class="card-score">{{ (p.score * 100).toFixed(0) }}%</div>
                  <div class="card-info">
                    <div class="card-title">{{ p.vendor || '未知厂家' }} {{ p.model || '' }}</div>
                    <div class="card-category">{{ p.category || '通用设备' }}</div>
                    <div class="card-text">{{ p.text?.slice(0, 120) }}...</div>
                    <div class="card-source">{{ p.source?.split(/[/\\]/).pop() }}</div>
                  </div>
                </div>
              </div>
            </template>

            <!-- Upload prompt -->
            <template v-else-if="msg.type === 'upload-prompt'">
              <div class="message-content">
                <p>已选定 <strong>{{ msg.productName }}</strong>，请上传厂家送审的技术资料（PDF/DOCX）：</p>
              </div>
              <div
                class="upload-zone"
                :class="{ dragover: isDragOver }"
                @dragover.prevent="isDragOver = true"
                @dragleave="isDragOver = false"
                @drop.prevent="handleFileDrop"
                @click="triggerFileInput"
              >
                <el-icon :size="32" style="color:var(--c-text-tertiary)"><UploadFilled /></el-icon>
                <p>拖拽文件到此处，或点击选择文件</p>
                <span>支持 PDF、DOCX 格式</span>
              </div>
            </template>

            <!-- Upload status -->
            <template v-else-if="msg.type === 'upload-status'">
              <div class="message-content">
                <p>{{ msg.content }}</p>
                <el-progress
                  v-if="msg.status === 'uploading'"
                  :percentage="msg.percent || 0"
                  :status="(msg.percent || 0) >= 90 ? 'success' : undefined"
                  :stroke-width="8"
                  :indeterminate="!msg.percent"
                  :duration="2"
                  style="margin-top:8px"
                />
              </div>
            </template>

            <!-- Extract result -->
            <template v-else-if="msg.type === 'extract-result'">
              <div class="message-content">
                <p>{{ msg.content }}</p>
              </div>
              <div v-for="(prod, pi) in msg.products" :key="pi" class="param-preview">
                <div class="param-preview-header">
                  {{ prod.vendor }} {{ prod.model }}
                  <el-tag size="small" type="info">{{ prod.category }}</el-tag>
                  <el-tag size="small">{{ prod.params?.length || 0 }} 项参数</el-tag>
                </div>
                <el-table :data="prod.params" size="small" stripe max-height="300">
                  <el-table-column prop="name" label="参数" width="160" />
                  <el-table-column prop="value" label="值" />
                  <el-table-column prop="unit" label="单位" width="80" />
                  <el-table-column prop="page" label="页码" width="70" />
                  <el-table-column prop="section" label="章节" width="120" />
                </el-table>
              </div>
            </template>

            <!-- Streaming compare -->
            <template v-else-if="msg.type === 'compare-stream'">
              <div v-html="renderMd(msg.content)" class="message-content" />
              <span v-if="streaming" class="cursor-blink" />
            </template>

            <!-- Compare report (done) -->
            <template v-else-if="msg.type === 'compare-report'">
              <div class="report-tabs">
                <button
                  class="report-tab"
                  :class="{ active: msg.viewMode !== 'table' }"
                  @click="msg.viewMode = 'markdown'"
                >Markdown 报告</button>
                <button
                  class="report-tab"
                  :class="{ active: msg.viewMode === 'table' }"
                  @click="msg.viewMode = 'table'"
                >结构化表格</button>
              </div>
              <div v-if="msg.viewMode !== 'table'" v-html="renderMd(msg.content)" class="message-content" />
              <div v-else class="struct-table-wrap">
                <el-table
                  :data="filteredTableData(msg.tableData || [])"
                  size="small"
                  stripe
                  :default-sort="{ prop: 'risk', order: 'descending' }"
                  max-height="500"
                >
                  <el-table-column prop="param" label="参数项" width="140" sortable />
                  <el-table-column prop="official" label="官方值" width="150" />
                  <el-table-column prop="vendor" label="送审值" width="150" />
                  <el-table-column prop="status" label="状态" width="90" sortable>
                    <template #default="{ row }">
                      <span :class="'status-' + row.status">{{ statusLabel(row.status) }}</span>
                    </template>
                  </el-table-column>
                  <el-table-column prop="risk" label="风险" width="80" sortable>
                    <template #default="{ row }">
                      <el-tag v-if="row.risk" :type="riskType(row.risk)" size="small">{{ riskLabel(row.risk) }}</el-tag>
                    </template>
                  </el-table-column>
                  <el-table-column prop="page" label="页码" width="70" sortable />
                  <el-table-column prop="section" label="章节" width="120" />
                  <el-table-column prop="note" label="说明" min-width="180" show-overflow-tooltip />
                </el-table>
                <div class="table-filters">
                  <el-checkbox-group v-model="tableStatusFilter" size="small">
                    <el-checkbox label="deviation">偏差</el-checkbox>
                    <el-checkbox label="missing">缺失</el-checkbox>
                    <el-checkbox label="added">新增</el-checkbox>
                    <el-checkbox label="match">一致</el-checkbox>
                  </el-checkbox-group>
                </div>
              </div>
              <div class="message-actions">
                <button class="action-btn" @click="copyContent(msg.content)">
                  <el-icon :size="14"><CopyDocument /></el-icon><span>复制</span>
                </button>
                <button class="action-btn" @click="resetWorkflow">
                  <el-icon :size="14"><RefreshRight /></el-icon><span>新建比对</span>
                </button>
              </div>
            </template>

            <!-- Fallback -->
            <template v-else>
              <div v-html="renderMd(msg.content || '')" class="message-content" />
            </template>
          </div>
        </div>
      </div>
    </div>

    <!-- Input Area -->
    <div class="input-area">
      <div class="input-container">
        <el-input
          v-model="inputText"
          type="textarea"
          :autosize="{ minRows: 1, maxRows: 4 }"
          :placeholder="inputPlaceholder"
          @keydown.enter.exact.prevent="handleSend"
          :disabled="inputDisabled"
          class="chat-input"
        />
        <div class="input-actions">
          <el-button
            v-if="!streaming"
            type="primary"
            @click="handleSend"
            :disabled="!inputText.trim() || inputDisabled"
            circle
          >
            <el-icon><Promotion /></el-icon>
          </el-button>
          <el-button v-else @click="stopStream" circle>
            <el-icon><VideoPause /></el-icon>
          </el-button>
        </div>
      </div>
      <div class="input-meta">
        <div class="meta-left">
          <span>{{ workflowStateLabel }}</span>
          <span class="meta-sep">·</span>
          <el-select v-model="collection" size="small" class="collection-select" :disabled="workflowState !== 'idle'">
            <el-option label="products（产品库）" value="products" />
            <el-option label="default（默认库）" value="default" />
          </el-select>
        </div>
        <div class="meta-actions">
          <button v-if="workflowState !== 'idle'" class="meta-btn danger" @click="resetWorkflow">重新开始</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import {
  Document, Promotion, VideoPause, CopyDocument,
  UploadFilled, RefreshRight,
} from '@element-plus/icons-vue'
import { useSSE } from '@/composables/useSSE'
import { renderMarkdown } from '@/utils/markdown'
import api from '@/composables/useApi'

// ── Types ───────────────────────────────────────────────────────

interface BidMessage {
  role: 'user' | 'assistant' | 'system'
  type: string
  content: string
  products?: any[]
  productName?: string
  tableData?: any[]
  viewMode?: string
  status?: string
  percent?: number
}

type WorkflowState = 'idle' | 'searching' | 'product_list' | 'selected' | 'uploading' | 'extracting' | 'comparing' | 'done'

// ── State ───────────────────────────────────────────────────────

const messages = ref<BidMessage[]>([])
const inputText = ref('')
const streaming = ref(false)
const workflowState = ref<WorkflowState>('idle')
const messagesRef = ref<HTMLElement | null>(null)
const fileInputRef = ref<HTMLInputElement | null>(null)
const isDragOver = ref(false)
const collection = ref('products')
const tableStatusFilter = ref<string[]>(['deviation', 'missing', 'added', 'match'])

const selectedProduct = ref<{ data: any; index: number } | null>(null)
const officialParamId = ref<number | null>(null)
const vendorParamIds = ref<number[]>([])

const { stream, streamUpload, abort } = useSSE()
const uploadPercent = ref(0)
const uploadStageMsg = ref('')

// ── Computed ────────────────────────────────────────────────────

const inputPlaceholder = computed(() => {
  switch (workflowState.value) {
    case 'idle': return '输入招标文件中的技术要求，如：摄像头 分辨率1080P IP67'
    case 'product_list': return '点击上方产品卡片选择，或重新输入技术要求'
    case 'selected': return '请上传送审资料（拖拽或点击上方上传区域）'
    case 'uploading':
    case 'extracting':
    case 'comparing': return '处理中，请稍候...'
    case 'done': return '比对已完成，点击"新建比对"开始新的比对'
    default: return '输入技术要求...'
  }
})

const inputDisabled = computed(() =>
  ['uploading', 'extracting', 'comparing', 'selected'].includes(workflowState.value)
)

const workflowStateLabel = computed(() => {
  const labels: Record<string, string> = {
    idle: '就绪 · 请输入招标技术要求',
    searching: '正在检索产品...',
    product_list: '请选择匹配的产品',
    selected: '请上传送审资料',
    uploading: '正在上传并分析...',
    extracting: '正在提取参数...',
    comparing: '正在比对参数...',
    done: '比对完成',
  }
  return labels[workflowState.value] || ''
})

// ── Helpers ─────────────────────────────────────────────────────

function renderMd(text: string): string {
  return renderMarkdown(text || '')
}

function scrollToBottom() {
  nextTick(() => {
    if (messagesRef.value) {
      messagesRef.value.scrollTop = messagesRef.value.scrollHeight
    }
  })
}

function addMsg(msg: Partial<BidMessage> & { role: BidMessage['role']; type: string }) {
  messages.value.push({ content: '', ...msg } as BidMessage)
  scrollToBottom()
}

function statusLabel(s: string): string {
  const m: Record<string, string> = { match: '✅ 一致', deviation: '⚠️ 偏差', missing: '❌ 缺失', added: '➕ 新增' }
  return m[s] || s
}

function riskLabel(r: string): string {
  const m: Record<string, string> = { high: '高', medium: '中', low: '低' }
  return m[r] || r
}

function riskType(r: string): 'danger' | 'warning' | 'info' | '' {
  const m: Record<string, any> = { high: 'danger', medium: 'warning', low: 'info' }
  return m[r] || ''
}

function filteredTableData(data: any[]): any[] {
  if (!data) return []
  return data.filter((r: any) => tableStatusFilter.value.includes(r.status))
}

function copyContent(content: string) {
  navigator.clipboard.writeText(content).then(() => {
    ElMessage.success('已复制到剪贴板')
  }).catch(() => ElMessage.error('复制失败'))
}

// ── Step 1: Search ──────────────────────────────────────────────

async function handleSend() {
  const q = inputText.value.trim()
  if (!q || inputDisabled.value) return

  if (workflowState.value === 'idle' || workflowState.value === 'product_list') {
    addMsg({ role: 'user', type: 'text', content: q })
    inputText.value = ''
    await doSearch(q)
  }
}

async function doSearch(query: string) {
  workflowState.value = 'searching'
  addMsg({ role: 'assistant', type: 'text', content: '正在从产品知识库中检索匹配产品...' })
  scrollToBottom()

  try {
    const { data } = await api.post('/bid/search', { query, top_k: 10, collection: collection.value })
    messages.value.pop()

    if (data.ok && data.data?.length) {
      workflowState.value = 'product_list'
      addMsg({ role: 'assistant', type: 'product-cards', products: data.data })
    } else {
      workflowState.value = 'idle'
      addMsg({
        role: 'assistant', type: 'text',
        content: data.message || '未找到匹配产品。产品知识库可能为空，请先通过"摄取管理"上传产品资料到 `products` 集合，或调整技术要求重试。',
      })
    }
  } catch (e: any) {
    messages.value.pop()
    workflowState.value = 'idle'
    addMsg({ role: 'assistant', type: 'text', content: `检索失败: ${e.message}` })
  }
}

// ── Step 2: Select Product ──────────────────────────────────────

function selectProduct(product: any, index: number) {
  if (workflowState.value !== 'product_list') return
  selectedProduct.value = { data: product, index }
  workflowState.value = 'selected'

  const name = `${product.vendor || '未知厂家'} ${product.model || ''}`.trim()
  addMsg({ role: 'assistant', type: 'upload-prompt', productName: name })
}

// ── Step 3: Upload File ─────────────────────────────────────────

function triggerFileInput() {
  fileInputRef.value?.click()
}

function handleFileSelect(e: Event) {
  const input = e.target as HTMLInputElement
  if (input.files?.length) {
    uploadFile(input.files[0])
  }
}

function handleFileDrop(e: DragEvent) {
  isDragOver.value = false
  const file = e.dataTransfer?.files?.[0]
  if (file) uploadFile(file)
}

async function uploadFile(file: File) {
  const ext = file.name.split('.').pop()?.toLowerCase()
  if (!['pdf', 'docx', 'doc'].includes(ext || '')) {
    ElMessage.error('仅支持 PDF/DOCX 格式')
    return
  }

  workflowState.value = 'uploading'
  uploadPercent.value = 0
  uploadStageMsg.value = `正在上传并分析 "${file.name}"...`
  addMsg({ role: 'system', type: 'upload-status', content: uploadStageMsg.value, status: 'uploading', percent: 0 })
  scrollToBottom()

  const formData = new FormData()
  formData.append('file', file)
  formData.append('doc_type', 'vendor')
  formData.append('collection', collection.value)
  if (selectedProduct.value?.data) {
    const p = selectedProduct.value.data
    if (p.vendor) formData.append('product_vendor', p.vendor)
    if (p.model) formData.append('product_model', p.model)
    if (p.category) formData.append('product_category', p.category)
  }

  // Find the upload-status message index for live updates
  const statusIdx = messages.value.length - 1

  await streamUpload(
    '/api/bid/upload',
    formData,
    (event) => {
      if (event.type === 'progress') {
        // Update the existing upload-status message in-place
        uploadPercent.value = event.percent || 0
        uploadStageMsg.value = event.message || ''
        if (statusIdx >= 0 && messages.value[statusIdx]?.type === 'upload-status') {
          messages.value[statusIdx].content = event.message
          messages.value[statusIdx].percent = event.percent || 0
        }
        scrollToBottom()
      } else if (event.type === 'done') {
        // Remove upload-status message
        if (statusIdx >= 0 && messages.value[statusIdx]?.type === 'upload-status') {
          messages.value.splice(statusIdx, 1)
        }

        if (event.ok && event.data?.length) {
          vendorParamIds.value = event.vendor_param_ids || []
          workflowState.value = 'extracting'
          addMsg({
            role: 'assistant', type: 'extract-result',
            content: event.message || '参数提取完成',
            products: event.data,
          })
          nextTick().then(() => {
            scrollToBottom()
            startComparison()
          })
        } else {
          workflowState.value = 'selected'
          addMsg({ role: 'assistant', type: 'text', content: event.message || '未能提取到参数，请检查文件内容' })
        }
      } else if (event.type === 'error') {
        if (statusIdx >= 0 && messages.value[statusIdx]?.type === 'upload-status') {
          messages.value.splice(statusIdx, 1)
        }
        workflowState.value = 'selected'
        addMsg({ role: 'assistant', type: 'text', content: event.message || '上传处理失败' })
      }
    },
    undefined,
    (err) => {
      if (statusIdx >= 0 && messages.value[statusIdx]?.type === 'upload-status') {
        messages.value.splice(statusIdx, 1)
      }
      workflowState.value = 'selected'
      addMsg({ role: 'assistant', type: 'text', content: `上传失败: ${err.message}` })
    },
  )
}

// ── Step 4: Compare ─────────────────────────────────────────────

async function startComparison() {
  if (!vendorParamIds.value.length) {
    addMsg({ role: 'assistant', type: 'text', content: '无法比对：未提取到送审参数' })
    workflowState.value = 'done'
    return
  }

  // Try to find existing official params
  try {
    const { data } = await api.get('/bid/params', { params: { doc_type: 'official', limit: 50 } })
    if (data.ok && data.data?.length) {
      officialParamId.value = data.data[0].id
    }
  } catch { /* ignore */ }

  // If no official params, auto-extract from knowledge base
  if (!officialParamId.value && selectedProduct.value?.data) {
    const p = selectedProduct.value.data
    const productName = `${p.vendor || ''} ${p.model || ''}`.trim()
    addMsg({ role: 'system', type: 'upload-status', content: `正在从知识库提取 "${productName}" 的官方参数...`, status: 'uploading' })
    scrollToBottom()

    try {
      const { data } = await api.post('/bid/extract-official', {
        query: productName || p.source || '',
        vendor: p.vendor || '',
        model: p.model || '',
        category: p.category || '',
        collection: collection.value,
      }, { timeout: 300000 })
      messages.value.pop()

      if (data.ok && data.official_param_ids?.length) {
        officialParamId.value = data.official_param_ids[0]
        addMsg({ role: 'assistant', type: 'text', content: `已从知识库自动提取官方参数（${data.message}）` })
      }
    } catch (e: any) {
      messages.value.pop()
    }
  }

  if (!officialParamId.value) {
    addMsg({
      role: 'assistant', type: 'text',
      content: '⚠️ 无法从知识库提取官方参数，请先通过知识库构建页面上传官方产品资料。\n\n已提取的送审参数已保存，可在官方数据就绪后重新比对。',
    })
    workflowState.value = 'done'
    return
  }

  workflowState.value = 'comparing'
  streaming.value = true

  const streamIdx = messages.value.length
  addMsg({ role: 'assistant', type: 'compare-stream', content: '' })

  await stream(
    '/api/bid/compare',
    { official_id: officialParamId.value, vendor_id: vendorParamIds.value[0] },
    (event) => {
      if (event.type === 'token') {
        messages.value[streamIdx].content += event.content
        scrollToBottom()
      } else if (event.type === 'done') {
        messages.value[streamIdx] = {
          role: 'assistant',
          type: 'compare-report',
          content: event.answer || messages.value[streamIdx].content,
          tableData: event.table_data || [],
          viewMode: 'markdown',
        }
        streaming.value = false
        workflowState.value = 'done'
        scrollToBottom()
      } else if (event.type === 'error') {
        messages.value[streamIdx].content += `\n\n**错误**: ${event.message}`
        streaming.value = false
        workflowState.value = 'done'
      }
    },
    () => { streaming.value = false },
    (err) => {
      ElMessage.error(`比对失败: ${err.message}`)
      streaming.value = false
      workflowState.value = 'done'
    },
  )
}

function stopStream() {
  abort()
  streaming.value = false
  workflowState.value = 'done'
}

// ── Reset ───────────────────────────────────────────────────────

function resetWorkflow() {
  messages.value = []
  inputText.value = ''
  streaming.value = false
  workflowState.value = 'idle'
  selectedProduct.value = null
  officialParamId.value = null
  vendorParamIds.value = []
}
</script>

<style scoped>
.verifier-page {
  display: flex;
  flex-direction: column;
  height: 100%;
}

/* Messages area */
.messages-area {
  flex: 1;
  overflow-y: auto;
  padding: var(--sp-6) var(--page-padding);
}
.messages-list {
  max-width: 794px;
  margin: 0 auto;
}

/* Empty state */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 60%;
  text-align: center;
}
.empty-icon {
  width: var(--sp-8);
  height: var(--sp-8);
  border-radius: var(--radius);
  background: var(--c-accent-muted);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--c-text-tertiary);
  margin-bottom: var(--sp-4);
}
.empty-state h3 {
  font-size: var(--fs-lg);
  font-weight: 600;
  color: var(--c-text-primary);
  margin: 0 0 var(--sp-2);
}
.empty-state p {
  font-size: var(--fs-sm);
  color: var(--c-text-tertiary);
  margin: 0;
  max-width: 400px;
}

/* Message bubbles */
.message { margin-bottom: var(--sp-5); }
.message.user { display: flex; justify-content: flex-end; }
.message.user .message-bubble {
  background: rgba(255,255,255,0.08);
  border: 1px solid rgba(255,255,255,0.12);
  color: var(--c-text-primary);
  border-radius: var(--radius) var(--radius) var(--sp-1) var(--radius);
  max-width: 600px;
}
.message.assistant .message-bubble,
.message.system .message-bubble {
  background: var(--glass-bg);
  border: 1px solid var(--c-border);
  border-radius: var(--radius) var(--radius) var(--radius) var(--sp-1);
  width: 100%;
  backdrop-filter: blur(var(--glass-blur));
  -webkit-backdrop-filter: blur(var(--glass-blur));
}
.message-bubble { padding: var(--sp-4) var(--sp-5); }
.message-text {
  font-size: var(--fs-sm);
  line-height: var(--lh-normal);
  white-space: pre-wrap;
}
.message-content {
  font-size: 16px;
  line-height: 1.8;
}
.message-content :deep(p) { margin: 0 0 var(--sp-3); }
.message-content :deep(p:last-child) { margin: 0; }
.message-content :deep(strong) { color: var(--c-text-primary); }
.message-content :deep(table) {
  border-collapse: collapse;
  width: auto;
  max-width: 100%;
  margin: var(--sp-3) 0;
  font-size: 14px;
  display: block;
  overflow-x: auto;
}
.message-content :deep(th),
.message-content :deep(td) {
  border: 1px solid var(--c-border);
  padding: var(--sp-2) var(--sp-3);
  white-space: nowrap;
}
.message-content :deep(th) {
  background: rgba(255,255,255,0.06);
  font-weight: 600;
}
.message-content :deep(h2),
.message-content :deep(h3) {
  margin: var(--sp-4) 0 var(--sp-2);
  font-weight: 600;
}
.message-content :deep(h2) { font-size: var(--fs-lg); }
.message-content :deep(h3) { font-size: 17px; }
.message-content :deep(ul),
.message-content :deep(ol) { padding-left: 2em; margin: var(--sp-2) 0; }
.message-content :deep(li) { margin-bottom: var(--sp-1); }
.message-content :deep(code) {
  background: rgba(255,255,255,0.06);
  padding: 1px var(--sp-1);
  border-radius: var(--sp-1);
  font-size: 0.9em;
}

/* Product cards */
.product-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: var(--sp-3);
  margin-top: var(--sp-2);
}
.product-card {
  background: rgba(255,255,255,0.03);
  border: 1px solid var(--c-border);
  border-radius: var(--radius);
  padding: var(--sp-3) var(--sp-4);
  cursor: pointer;
  transition: all 0.2s;
  position: relative;
}
.product-card:hover {
  border-color: var(--c-border-hover);
  background: rgba(255,255,255,0.06);
  transform: translateY(-2px);
}
.product-card.selected {
  border-color: var(--c-accent);
  background: rgba(74,222,128,0.06);
}
.card-score {
  position: absolute;
  top: var(--sp-2);
  right: var(--sp-2);
  background: rgba(74,222,128,0.15);
  color: #4ade80;
  padding: 2px var(--sp-2);
  border-radius: var(--radius-sm);
  font-size: 11px;
  font-weight: 600;
}
.card-info { padding-right: 40px; }
.card-title {
  font-weight: 600;
  font-size: var(--fs-sm);
  color: var(--c-text-primary);
  margin-bottom: var(--sp-1);
}
.card-category {
  font-size: var(--fs-xs);
  color: var(--c-text-tertiary);
  margin-bottom: var(--sp-2);
}
.card-text {
  font-size: var(--fs-xs);
  color: var(--c-text-secondary);
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.card-source {
  font-size: 11px;
  color: var(--c-text-tertiary);
  margin-top: var(--sp-2);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* Upload zone */
.upload-zone {
  border: 2px dashed var(--c-border);
  border-radius: var(--radius);
  padding: var(--sp-6) var(--sp-4);
  text-align: center;
  cursor: pointer;
  transition: all 0.2s;
  margin-top: var(--sp-3);
}
.upload-zone:hover,
.upload-zone.dragover {
  border-color: var(--c-accent);
  background: rgba(74,222,128,0.04);
}
.upload-zone p {
  margin: var(--sp-2) 0 0;
  font-size: var(--fs-sm);
  color: var(--c-text-secondary);
}
.upload-zone span {
  font-size: var(--fs-xs);
  color: var(--c-text-tertiary);
}

/* Param preview */
.param-preview {
  margin-top: var(--sp-3);
  border: 1px solid var(--c-border);
  border-radius: var(--radius-sm);
  overflow: hidden;
}
.param-preview-header {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  padding: var(--sp-2) var(--sp-3);
  background: rgba(255,255,255,0.03);
  font-size: var(--fs-sm);
  font-weight: 600;
  color: var(--c-text-primary);
}

/* Report tabs */
.report-tabs {
  display: flex;
  gap: var(--sp-1);
  margin-bottom: var(--sp-3);
}
.report-tab {
  background: rgba(255,255,255,0.04);
  border: 1px solid var(--c-border);
  border-radius: var(--radius-sm);
  padding: var(--sp-2) var(--sp-3);
  font-size: var(--fs-xs);
  color: var(--c-text-secondary);
  cursor: pointer;
  transition: all 0.15s;
}
.report-tab:hover { color: var(--c-text-primary); }
.report-tab.active {
  background: rgba(255,255,255,0.1);
  color: var(--c-text-primary);
  border-color: rgba(255,255,255,0.2);
}

/* Structured table */
.struct-table-wrap { overflow-x: auto; }
.table-filters {
  padding: var(--sp-2) 0;
  display: flex;
  gap: var(--sp-3);
  font-size: var(--fs-xs);
}

/* Status labels */
.status-match { color: #4ade80; }
.status-deviation { color: #fbbf24; }
.status-missing { color: #f87171; }
.status-added { color: #60a5fa; }

/* Message actions */
.message-actions {
  display: flex;
  gap: var(--sp-2);
  justify-content: flex-end;
  padding-top: var(--sp-3);
  margin-top: var(--sp-3);
}
.action-btn {
  background: rgba(255,255,255,0.05);
  border: 1px solid var(--c-border);
  border-radius: var(--radius-sm);
  color: var(--c-text-secondary);
  cursor: pointer;
  padding: var(--sp-2) var(--sp-3);
  display: flex;
  align-items: center;
  gap: var(--sp-1);
  font-size: var(--fs-xs);
  transition: all 0.2s;
}
.action-btn:hover {
  color: var(--c-text-primary);
  background: rgba(255,255,255,0.1);
  border-color: rgba(255,255,255,0.2);
}

/* Cursor blink */
.cursor-blink {
  display: inline-block;
  width: 2px;
  height: var(--sp-4);
  background: var(--c-text-tertiary);
  margin-left: 2px;
  vertical-align: text-bottom;
  animation: blink 1s step-end infinite;
}
@keyframes blink { 50% { opacity: 0; } }

/* Input area */
.input-area {
  border-top: 1px solid var(--c-border);
  background: var(--c-bg-elevated);
  padding: var(--sp-4) var(--page-padding);
}
.input-container {
  max-width: 794px;
  margin: 0 auto;
  display: flex;
  gap: var(--sp-3);
  align-items: flex-end;
}
.chat-input { flex: 1; }
.input-actions { flex-shrink: 0; padding-bottom: 2px; }
.input-meta {
  max-width: 794px;
  margin: var(--sp-2) auto 0;
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: var(--fs-xs);
  color: var(--c-text-tertiary);
}
.meta-left {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
}
.meta-sep { opacity: 0.4; }
.meta-actions { display: flex; gap: var(--sp-3); }
.collection-select { width: 160px; }
.collection-select :deep(.el-input__inner) { font-size: var(--fs-xs); }
.meta-btn {
  background: none;
  border: none;
  font-size: var(--fs-xs);
  color: var(--c-text-tertiary);
  cursor: pointer;
  transition: color 0.15s;
}
.meta-btn:hover { color: var(--c-text-primary); }
.meta-btn.danger:hover { color: var(--c-danger); }
</style>
