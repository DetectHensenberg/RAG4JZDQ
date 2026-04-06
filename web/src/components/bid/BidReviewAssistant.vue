<template>
  <div class="review-page">
    <!-- Steps bar -->
    <div class="steps-bar">
      <el-steps :active="step" finish-status="success" simple>
        <el-step title="上传招标文件" />
        <el-step title="确认废标项清单" />
        <el-step title="上传投标文件" />
        <el-step title="审查报告" />
      </el-steps>
    </div>

    <!-- ══════════ Step 0: Upload tender ══════════ -->
    <div v-if="step === 0" class="step-body">
      <div class="step-center">
        <div class="step-icon"><el-icon :size="40"><Document /></el-icon></div>
        <h3>上传招标文件</h3>
        <p>上传招标文件（PDF/DOC/DOCX），支持多个文件，系统将自动合并提取文本并识别废标项</p>
        <div
          class="upload-zone"
          :class="{ dragover: isDragTender }"
          @dragover.prevent="isDragTender = true"
          @dragleave="isDragTender = false"
          @drop.prevent="onDropTender"
          @click="tenderInputEl?.click()"
        >
          <el-icon :size="32" style="color:var(--c-text-tertiary)"><UploadFilled /></el-icon>
          <p>拖拽招标文件到此处，或点击选择</p>
          <span>支持 PDF、DOCX 格式</span>
        </div>
        <input ref="tenderInputEl" type="file" accept=".pdf,.docx,.doc" multiple style="display:none" @change="onSelectTender" />
        <div v-for="(f, idx) in tenderFiles" :key="idx" class="file-info">
          <el-icon><Document /></el-icon>
          <span>附件：{{ f.name }}</span>
          <el-button link type="danger" size="small" @click="tenderFiles.splice(idx, 1)">移除</el-button>
        </div>
        <el-button type="primary" :disabled="!tenderFiles.length" :loading="parsing" @click="parseTender" style="margin-top:var(--sp-4)">
          {{ parsing ? '正在解析...' : '上传并识别废标项' }}
        </el-button>
      </div>
    </div>

    <!-- ══════════ Step 1: Confirm items ══════════ -->
    <div v-if="step === 1" class="step-body items-step">
      <div class="items-header">
        <div>
          <h3>废标项清单</h3>
          <p>共识别到 <strong>{{ disqualItems.length }}</strong> 条废标项，您可以编辑、删除或新增条目</p>
        </div>
        <div class="items-actions">
          <el-button size="small" @click="addItem">新增废标项</el-button>
          <el-button type="primary" size="small" :disabled="!disqualItems.length" @click="step = 2">确认清单，下一步</el-button>
        </div>
      </div>
      <el-table :data="disqualItems" stripe size="small" class="items-table" max-height="500">
        <el-table-column prop="category" label="类型" width="100">
          <template #default="{ row }">
            <el-select v-model="row.category" size="small" style="width:90px">
              <el-option v-for="c in categories" :key="c" :label="c" :value="c" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column prop="requirement" label="要求描述" min-width="300">
          <template #default="{ row }">
            <el-input v-model="row.requirement" size="small" type="textarea" :autosize="{ minRows: 1, maxRows: 3 }" />
          </template>
        </el-table-column>
        <el-table-column prop="source_section" label="来源" width="180">
          <template #default="{ row }">
            <div class="source-cell">
              <span v-if="row.source_page" class="source-page">P{{ row.source_page }}</span>
              <el-input v-model="row.source_section" size="small" placeholder="章节" />
            </div>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="70" align="center">
          <template #default="{ $index }">
            <el-button link type="danger" size="small" @click="disqualItems.splice($index, 1)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="step-nav">
        <el-button @click="step = 0">上一步</el-button>
      </div>
    </div>

    <!-- ══════════ Step 2: Upload bid ══════════ -->
    <div v-if="step === 2" class="step-body">
      <div class="step-center">
        <div class="step-icon"><el-icon :size="40"><Tickets /></el-icon></div>
        <h3>上传投标文件</h3>
        <p>上传投标文件（PDF/DOC/DOCX），支持多个文件，系统将合并后对照废标项逐一核查</p>
        <div
          class="upload-zone"
          :class="{ dragover: isDragBid }"
          @dragover.prevent="isDragBid = true"
          @dragleave="isDragBid = false"
          @drop.prevent="onDropBid"
          @click="bidInputEl?.click()"
        >
          <el-icon :size="32" style="color:var(--c-text-tertiary)"><UploadFilled /></el-icon>
          <p>拖拽投标文件到此处，或点击选择</p>
          <span>支持 PDF、DOCX 格式</span>
        </div>
        <input ref="bidInputEl" type="file" accept=".pdf,.docx,.doc" multiple style="display:none" @change="onSelectBid" />
        <div v-for="(f, idx) in bidFiles" :key="idx" class="file-info">
          <el-icon><Document /></el-icon>
          <span>附件：{{ f.name }}</span>
          <el-button link type="danger" size="small" @click="bidFiles.splice(idx, 1)">移除</el-button>
        </div>
        <el-button type="primary" :disabled="!bidFiles.length" :loading="checking" @click="parseBidAndCheck" style="margin-top:var(--sp-4)">
          {{ checking ? '正在审查...' : '上传并开始审查' }}
        </el-button>
      </div>
      <div class="step-nav">
        <el-button @click="step = 1">上一步</el-button>
      </div>
    </div>

    <!-- ══════════ Step 3: Review report ══════════ -->
    <div v-if="step === 3" class="step-body report-step">
      <div class="report-header">
        <h3>废标项审查报告</h3>
        <div class="report-tabs-bar">
          <button class="rpt-tab" :class="{ active: reportView === 'markdown' }" @click="reportView = 'markdown'">Markdown 报告</button>
          <button class="rpt-tab" :class="{ active: reportView === 'table' }" @click="reportView = 'table'">结构化表格</button>
        </div>
      </div>
      <div class="report-body" ref="reportBodyRef">
        <!-- Loading state -->
        <div v-if="streaming && !reportContent" class="report-loading">
          <div class="loading-spinner" />
          <div class="loading-text">
            <h4>正在审查中，请耐心等待…</h4>
            <p>AI 正在对照 {{ disqualItems.length }} 条废标项逐一核查投标文件，大约需要 1-2 分钟</p>
          </div>
        </div>
        <!-- Markdown view -->
        <div v-if="reportView === 'markdown'" v-html="renderedReport" class="report-md" />
        <!-- Table view -->
        <div v-else class="report-table-wrap">
          <el-table :data="filteredReportTable" stripe size="small" :default-sort="{ prop: 'risk', order: 'descending' }" max-height="500">
            <el-table-column prop="category" label="类型" width="90" sortable />
            <el-table-column prop="requirement" label="废标项要求" min-width="200" show-overflow-tooltip />
            <el-table-column prop="status" label="响应状态" width="110" sortable>
              <template #default="{ row }">
                <span :class="'st-' + row.status">{{ statusLabel(row.status) }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="risk" label="风险" width="80" sortable>
              <template #default="{ row }">
                <el-tag :type="riskType(row.risk)" size="small">{{ riskLabel(row.risk) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="detail" label="详细说明" min-width="200" show-overflow-tooltip />
          </el-table>
          <div class="table-filters">
            <el-checkbox-group v-model="statusFilter" size="small">
              <el-checkbox label="responded">已响应</el-checkbox>
              <el-checkbox label="incomplete">不完整</el-checkbox>
              <el-checkbox label="missing">缺失</el-checkbox>
            </el-checkbox-group>
          </div>
        </div>
        <span v-if="streaming && reportContent" class="cursor-blink" />
      </div>
      <div class="report-actions">
        <el-button @click="copyReport"><el-icon :size="14"><CopyDocument /></el-icon> 复制报告</el-button>
        <el-button type="primary" @click="resetAll"><el-icon :size="14"><RefreshRight /></el-icon> 重新审查</el-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import {
  Document, UploadFilled, Tickets, CopyDocument, RefreshRight,
} from '@element-plus/icons-vue'
import { useSSE } from '@/composables/useSSE'
import { renderMarkdown } from '@/utils/markdown'
import api from '@/composables/useApi'

// ── State ───────────────────────────────────────────────────────

const step = ref(0)
const categories = ['符合性', '资格性', '实质性', '★号', '其他']

// Step 0
const tenderFiles = ref<File[]>([])
const isDragTender = ref(false)
const parsing = ref(false)
const tenderText = ref('')
const pageBoundaries = ref<number[][]>([])

// Step 1
const disqualItems = ref<any[]>([])

// Step 2
const bidFiles = ref<File[]>([])
const isDragBid = ref(false)
const checking = ref(false)
const bidText = ref('')

// Template refs
const tenderInputEl = ref<HTMLInputElement | null>(null)
const bidInputEl = ref<HTMLInputElement | null>(null)

// Step 3
const reportView = ref<'markdown' | 'table'>('markdown')
const reportContent = ref('')
const reportTableData = ref<any[]>([])
const streaming = ref(false)
const statusFilter = ref(['responded', 'incomplete', 'missing'])
const reportBodyRef = ref<HTMLElement | null>(null)

const { stream, abort } = useSSE()

// ── Computed ────────────────────────────────────────────────────

const renderedReport = computed(() => renderMarkdown(reportContent.value || ''))

const filteredReportTable = computed(() =>
  reportTableData.value.filter(r => statusFilter.value.includes(r.status))
)

// ── Helpers ─────────────────────────────────────────────────────

function statusLabel(s: string): string {
  const m: Record<string, string> = { responded: '✅ 已响应', incomplete: '⚠️ 不完整', missing: '❌ 缺失' }
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

function scrollReportBottom() {
  nextTick(() => {
    if (reportBodyRef.value) reportBodyRef.value.scrollTop = reportBodyRef.value.scrollHeight
  })
}

// ── Step 0: Tender upload ───────────────────────────────────────

function onSelectTender(e: Event) {
  const input = e.target as HTMLInputElement
  if (input.files?.length) {
    tenderFiles.value.push(...Array.from(input.files))
    input.value = ''  // allow re-selecting same files
  }
}

function onDropTender(e: DragEvent) {
  isDragTender.value = false
  const files = e.dataTransfer?.files
  if (files?.length) tenderFiles.value.push(...Array.from(files))
}

async function parseTender() {
  if (!tenderFiles.value.length) return
  parsing.value = true
  try {
    const fd = new FormData()
    for (const f of tenderFiles.value) fd.append('files', f)
    const { data } = await api.post('/bid-review/parse-tender', fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 120000,
    })
    if (!data.ok) { ElMessage.error(data.message || '解析失败'); return }
    tenderText.value = data.data.text
    pageBoundaries.value = data.data.page_boundaries || []
    const pageInfo = data.data.page_count ? `（${data.data.page_count}页）` : ''
    ElMessage.success(`已提取 ${data.data.char_count} 字${pageInfo}`)

    // Identify items (LLM refinement can take 1-2 min)
    const { data: idData } = await api.post('/bid-review/identify-items', {
      text: tenderText.value,
      page_boundaries: pageBoundaries.value,
    }, { timeout: 180000 })
    if (idData.ok && idData.data?.length) {
      disqualItems.value = idData.data
      ElMessage.success(`识别到 ${idData.data.length} 条废标项`)
      step.value = 1
    } else {
      ElMessage.warning(idData.message || '未识别到废标项，请检查文件内容')
    }
  } catch (e: any) {
    ElMessage.error(`解析失败: ${e.message}`)
  } finally {
    parsing.value = false
  }
}

// ── Step 1: Add item ────────────────────────────────────────────

function addItem() {
  disqualItems.value.push({
    id: Math.random().toString(36).slice(2, 10),
    category: '其他',
    requirement: '',
    source_section: '',
    source_page: 0,
    original_text: '',
  })
}

// ── Step 2: Bid upload + check ──────────────────────────────────

function onSelectBid(e: Event) {
  const input = e.target as HTMLInputElement
  if (input.files?.length) {
    bidFiles.value.push(...Array.from(input.files))
    input.value = ''  // allow re-selecting same files
  }
}

function onDropBid(e: DragEvent) {
  isDragBid.value = false
  const files = e.dataTransfer?.files
  if (files?.length) bidFiles.value.push(...Array.from(files))
}

async function parseBidAndCheck() {
  if (!bidFiles.value.length) return
  checking.value = true
  try {
    // Parse bid
    const fd = new FormData()
    for (const f of bidFiles.value) fd.append('files', f)
    const { data } = await api.post('/bid-review/parse-bid', fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 120000,
    })
    if (!data.ok) { ElMessage.error(data.message || '解析失败'); checking.value = false; return }
    bidText.value = data.data.text

    // Move to report step and start streaming
    step.value = 3
    streaming.value = true
    reportContent.value = ''
    reportTableData.value = []

    await stream(
      '/api/bid-review/check',
      { items: disqualItems.value, bid_text: bidText.value },
      (event) => {
        if (event.type === 'token') {
          reportContent.value += event.content
          scrollReportBottom()
        } else if (event.type === 'done') {
          reportContent.value = event.answer || reportContent.value
          reportTableData.value = event.table_data || []
          streaming.value = false
          scrollReportBottom()
        } else if (event.type === 'error') {
          reportContent.value += `\n\n**错误**: ${event.message}`
          streaming.value = false
        }
      },
      () => { streaming.value = false },
      (err) => {
        ElMessage.error(`审查失败: ${err.message}`)
        streaming.value = false
      },
    )
  } catch (e: any) {
    ElMessage.error(`审查失败: ${e.message}`)
  } finally {
    checking.value = false
  }
}

// ── Step 3: Actions ─────────────────────────────────────────────

function copyReport() {
  navigator.clipboard.writeText(reportContent.value).then(() => {
    ElMessage.success('已复制报告到剪贴板')
  }).catch(() => ElMessage.error('复制失败'))
}

function resetAll() {
  abort()
  step.value = 0
  tenderFiles.value = []
  tenderText.value = ''
  pageBoundaries.value = []
  disqualItems.value = []
  bidFiles.value = []
  bidText.value = ''
  reportContent.value = ''
  reportTableData.value = []
  streaming.value = false
  reportView.value = 'markdown'
}
</script>

<style scoped>
.review-page {
  display: flex;
  flex-direction: column;
  height: 100%;
}

/* Steps bar */
.steps-bar {
  padding: var(--sp-4) var(--sp-6);
  border-bottom: 1px solid var(--c-border);
  flex-shrink: 0;
}

/* Step body */
.step-body {
  flex: 1;
  overflow-y: auto;
  padding: var(--sp-6);
  display: flex;
  flex-direction: column;
}

/* Centered step content */
.step-center {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  flex: 1;
  text-align: center;
  max-width: 500px;
  margin: 0 auto;
}
.step-icon {
  width: 72px;
  height: 72px;
  border-radius: var(--radius);
  background: var(--c-accent-muted);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--c-text-tertiary);
  margin-bottom: var(--sp-4);
}
.step-center h3 {
  font-size: var(--fs-lg);
  font-weight: 600;
  color: var(--c-text-primary);
  margin: 0 0 var(--sp-2);
}
.step-center p {
  font-size: var(--fs-sm);
  color: var(--c-text-tertiary);
  margin: 0 0 var(--sp-5);
  max-width: 400px;
}

/* Upload zone */
.upload-zone {
  border: 2px dashed var(--c-border);
  border-radius: var(--radius);
  padding: var(--sp-6) var(--sp-8);
  text-align: center;
  cursor: pointer;
  transition: all 0.2s;
  width: 100%;
}
.upload-zone:hover,
.upload-zone.dragover {
  border-color: var(--c-accent);
  background: rgba(74,222,128,0.04);
}
.upload-zone p { margin: var(--sp-2) 0 0; font-size: var(--fs-sm); color: var(--c-text-secondary); }
.upload-zone span { font-size: var(--fs-xs); color: var(--c-text-tertiary); }

/* File info */
.file-info {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  margin-top: var(--sp-3);
  padding: var(--sp-2) var(--sp-3);
  background: rgba(255,255,255,0.04);
  border: 1px solid var(--c-border);
  border-radius: var(--radius-sm);
  font-size: var(--fs-sm);
  color: var(--c-text-secondary);
}

/* Step navigation */
.step-nav {
  padding-top: var(--sp-4);
  display: flex;
  justify-content: flex-start;
}

/* ── Items step ── */
.items-step { padding: var(--sp-4) var(--sp-6); }
.items-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: var(--sp-4);
}
.items-header h3 {
  font-size: var(--fs-base);
  font-weight: 600;
  color: var(--c-text-primary);
  margin: 0 0 var(--sp-1);
}
.items-header p {
  font-size: var(--fs-sm);
  color: var(--c-text-tertiary);
  margin: 0;
}
.items-actions { display: flex; gap: var(--sp-2); flex-shrink: 0; }
.items-table { flex: 1; }

/* Source cell with page badge */
.source-cell {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
}
.source-page {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 32px;
  height: 22px;
  padding: 0 6px;
  border-radius: var(--radius-sm);
  background: rgba(74,222,128,0.15);
  color: #4ade80;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.5px;
}

/* ── Report step ── */
.report-step { padding: var(--sp-4) var(--sp-6); }
.report-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--sp-4);
  flex-shrink: 0;
}
.report-header h3 {
  font-size: var(--fs-base);
  font-weight: 600;
  color: var(--c-text-primary);
  margin: 0;
}
.report-tabs-bar { display: flex; gap: var(--sp-1); }
.rpt-tab {
  background: rgba(255,255,255,0.04);
  border: 1px solid var(--c-border);
  border-radius: var(--radius-sm);
  padding: var(--sp-2) var(--sp-3);
  font-size: var(--fs-xs);
  color: var(--c-text-secondary);
  cursor: pointer;
  transition: all 0.15s;
}
.rpt-tab:hover { color: var(--c-text-primary); }
.rpt-tab.active {
  background: rgba(255,255,255,0.1);
  color: var(--c-text-primary);
  border-color: rgba(255,255,255,0.2);
}

.report-body {
  flex: 1;
  overflow-y: auto;
  border: 1px solid var(--c-border);
  border-radius: var(--radius-sm);
  padding: var(--sp-4) var(--sp-5);
  background: var(--glass-bg);
  backdrop-filter: blur(var(--glass-blur));
}
.report-md {
  font-size: 15px;
  line-height: 1.8;
}
.report-md :deep(p) { margin: 0 0 var(--sp-3); }
.report-md :deep(strong) { color: var(--c-text-primary); }
.report-md :deep(table) {
  border-collapse: collapse;
  width: auto;
  max-width: 100%;
  margin: var(--sp-3) 0;
  font-size: 13px;
  display: block;
  overflow-x: auto;
}
.report-md :deep(th),
.report-md :deep(td) {
  border: 1px solid var(--c-border);
  padding: var(--sp-2) var(--sp-3);
  white-space: nowrap;
}
.report-md :deep(th) { background: rgba(255,255,255,0.06); font-weight: 600; }
.report-md :deep(h2),
.report-md :deep(h3) { margin: var(--sp-4) 0 var(--sp-2); font-weight: 600; }
.report-md :deep(h2) { font-size: var(--fs-lg); }
.report-md :deep(h3) { font-size: 16px; }
.report-md :deep(ul),
.report-md :deep(ol) { padding-left: 2em; margin: var(--sp-2) 0; }

.report-table-wrap { overflow-x: auto; }
.table-filters {
  padding: var(--sp-2) 0;
  display: flex;
  gap: var(--sp-3);
  font-size: var(--fs-xs);
}

/* Status */
.st-responded { color: #4ade80; }
.st-incomplete { color: #fbbf24; }
.st-missing { color: #f87171; }

.report-actions {
  display: flex;
  gap: var(--sp-3);
  justify-content: flex-end;
  padding-top: var(--sp-4);
  flex-shrink: 0;
}

/* Loading state */
.report-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 20px;
  gap: 20px;
  animation: fadeIn 0.3s ease;
}
.loading-spinner {
  width: 40px;
  height: 40px;
  border: 3px solid var(--c-border);
  border-top-color: #4ade80;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
.loading-text {
  text-align: center;
}
.loading-text h4 {
  font-size: var(--fs-base);
  font-weight: 600;
  color: var(--c-text-primary);
  margin: 0 0 var(--sp-2);
}
.loading-text p {
  font-size: var(--fs-sm);
  color: var(--c-text-tertiary);
  margin: 0;
}
@keyframes spin { to { transform: rotate(360deg); } }
@keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }

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
</style>
