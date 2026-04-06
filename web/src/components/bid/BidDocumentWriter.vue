<template>
  <div class="doc-writer">
    <!-- Steps bar -->
    <div class="steps-bar">
      <el-steps :active="step" finish-status="success" simple>
        <el-step title="上传招标文件" />
        <el-step title="条款识别" />
        <el-step title="大纲编辑" />
        <el-step title="内容填充" />
        <el-step title="水印配置" />
        <el-step title="导出文档" />
      </el-steps>
    </div>

    <!-- ══════════ Step 0: Upload tender ══════════ -->
    <div v-if="step === 0" class="step-body">
      <div class="step-center">
        <div class="step-icon"><el-icon :size="40"><Document /></el-icon></div>
        <h3>上传招标文件</h3>
        <p>上传招标文件（PDF/DOCX），系统将自动识别商务文件条款要求</p>
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
        <input ref="tenderInputEl" type="file" accept=".pdf,.docx,.doc" style="display:none" @change="onSelectTender" />
        <div v-if="tenderFile" class="file-info">
          <el-icon><Document /></el-icon>
          <span>{{ tenderFile.name }}</span>
          <el-button link type="danger" size="small" @click="tenderFile = null">移除</el-button>
        </div>
        <el-button type="primary" :disabled="!tenderFile" :loading="uploading" @click="uploadTender" style="margin-top:var(--sp-4)">
          {{ uploading ? '正在上传...' : '上传并识别条款' }}
        </el-button>
      </div>
    </div>

    <!-- ══════════ Step 1: Clause review ══════════ -->
    <div v-if="step === 1" class="step-body clauses-step">
      <div class="clauses-header">
        <div>
          <h3>商务文件条款</h3>
          <p v-if="!extracting">共识别到 <strong>{{ clauses.length }}</strong> 条商务文件要求</p>
          <p v-else>正在解析招标文件...</p>
        </div>
        <div class="clauses-actions">
          <el-button size="small" @click="step = 0">上一步</el-button>
          <el-button type="primary" size="small" :loading="generatingOutline" :disabled="!clauses.length || extracting" @click="generateOutline">
            {{ generatingOutline ? '正在生成大纲...' : '生成大纲' }}
          </el-button>
        </div>
      </div>
      <div v-if="extracting" class="extracting-box">
        <div class="ai-pulse-ring"></div>
        <el-icon class="is-loading" :size="32"><Loading /></el-icon>
        <div class="extracting-info">
          <h4>AI 正在分析招标文件</h4>
          <p>正在识别商务文件条款，云端模型处理中，请耐心等待...</p>
          <span class="elapsed-time">已用时 {{ elapsedTime }} 秒</span>
        </div>
      </div>
      <div v-if="generatingOutline && step === 1" class="extracting-box">
        <div class="ai-pulse-ring"></div>
        <el-icon class="is-loading" :size="32"><Loading /></el-icon>
        <div class="extracting-info">
          <h4>AI 正在生成商务文件大纲</h4>
          <p>基于条款分析结果，云端模型生成中，请耐心等待...</p>
          <span class="elapsed-time">已用时 {{ elapsedTime }} 秒</span>
        </div>
      </div>
      <el-table v-else :data="clauses" stripe size="small" class="clauses-table" max-height="450">
        <el-table-column type="selection" width="40" />
        <el-table-column prop="id" label="#" width="50" />
        <el-table-column prop="title" label="条款标题" width="180" />
        <el-table-column prop="description" label="具体要求" min-width="300" show-overflow-tooltip />
        <el-table-column prop="category" label="分类" width="100">
          <template #default="{ row }">
            <el-tag size="small" :type="categoryType(row.category)">{{ categoryLabel(row.category) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="required" label="必须" width="70" align="center">
          <template #default="{ row }">
            <el-icon v-if="row.required" style="color:#4ade80"><Check /></el-icon>
            <span v-else style="color:var(--c-text-tertiary)">-</span>
          </template>
        </el-table-column>
        <el-table-column prop="source_page" label="来源" width="80" />
      </el-table>
    </div>

    <!-- ══════════ Step 2: Outline editor ══════════ -->
    <div v-if="step === 2" class="step-body outline-step">
      <div class="outline-header">
        <div>
          <h3>商务文件大纲</h3>
          <p>可拖拽调整章节顺序，勾选需要填充的章节</p>
        </div>
        <div class="outline-actions">
          <el-button size="small" @click="step = 1">上一步</el-button>
          <el-button type="primary" size="small" :disabled="!outline.length" @click="startFill">
            开始填充
          </el-button>
        </div>
      </div>
      <div class="outline-list">
        <div
          v-for="(item, idx) in outline"
          :key="item.id"
          class="outline-item"
          :class="{ 'level-2': item.level === 2 }"
          draggable="true"
          @dragstart="onDragStart(idx)"
          @dragover.prevent
          @drop="onDrop(idx)"
        >
          <el-icon class="drag-handle"><Rank /></el-icon>
          <el-checkbox v-model="item.selected" />
          <span class="outline-id">{{ item.id }}</span>
          <span class="outline-title">{{ item.title }}</span>
          <el-tag v-if="item.has_material" size="small" type="success">已匹配</el-tag>
          <el-tag v-else size="small" type="info">待补充</el-tag>
        </div>
      </div>
    </div>

    <!-- ══════════ Step 3: Content fill ══════════ -->
    <div v-if="step === 3" class="step-body fill-step">
      <div class="fill-header">
        <div>
          <h3>内容填充</h3>
          <p v-if="filling">正在填充第 {{ fillProgress.current }} / {{ fillProgress.total }} 章节：{{ fillProgress.title }}</p>
          <p v-else>填充完成，可预览和编辑内容</p>
        </div>
        <div class="fill-actions">
          <el-button size="small" @click="step = 2" :disabled="filling">上一步</el-button>
          <el-button type="primary" size="small" :disabled="filling" @click="step = 4">
            配置水印
          </el-button>
        </div>
      </div>
      <div class="fill-form">
        <el-form :inline="true" size="small">
          <el-form-item label="项目名称">
            <el-input v-model="projectName" placeholder="输入项目名称" style="width:200px" />
          </el-form-item>
          <el-form-item label="项目编号">
            <el-input v-model="projectCode" placeholder="输入项目编号" style="width:200px" />
          </el-form-item>
        </el-form>
      </div>
      <div class="fill-content">
        <div v-for="item in outline" :key="item.id" class="content-section">
          <div class="section-header" :class="{ 'level-2': item.level === 2 }">
            <span class="section-id">{{ item.id }}</span>
            <span class="section-title">{{ item.title }}</span>
          </div>
          <el-input
            v-model="contentMap[item.id]"
            type="textarea"
            :autosize="{ minRows: 2, maxRows: 8 }"
            :placeholder="filling ? '填充中...' : '章节内容'"
          />
        </div>
      </div>
    </div>

    <!-- ══════════ Step 4: Watermark config ══════════ -->
    <div v-if="step === 4" class="step-body watermark-step">
      <div class="watermark-header">
        <div>
          <h3>水印配置</h3>
          <p>为证照材料添加项目专用水印</p>
        </div>
        <div class="watermark-actions">
          <el-button size="small" @click="step = 3">上一步</el-button>
          <el-button type="primary" size="small" @click="step = 5">
            跳过，直接导出
          </el-button>
        </div>
      </div>
      <div class="watermark-form">
        <el-form size="small">
          <el-form-item label="项目编号">
            <el-input v-model="projectCode" placeholder="输入项目编号" style="width:300px" />
          </el-form-item>
          <el-form-item label="水印文字">
            <span class="watermark-preview">仅限于 {{ projectCode || 'XXX' }} 项目投标使用</span>
          </el-form-item>
        </el-form>
      </div>
      <div class="materials-section">
        <h4>选择需要添加水印的材料</h4>
        <el-table :data="materials" stripe size="small" max-height="300" @selection-change="onMaterialSelect">
          <el-table-column type="selection" width="40" />
          <el-table-column prop="name" label="材料名称" min-width="200" />
          <el-table-column prop="category" label="分类" width="100">
            <template #default="{ row }">
              <el-tag size="small">{{ categoryLabel(row.category) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="file_path" label="文件" width="150">
            <template #default="{ row }">
              <span v-if="row.file_path" class="file-badge">有文件</span>
              <span v-else style="color:var(--c-text-tertiary)">无文件</span>
            </template>
          </el-table-column>
        </el-table>
        <el-button
          type="primary"
          size="small"
          :disabled="!selectedMaterials.length || !projectCode"
          :loading="watermarking"
          @click="addWatermarks"
          style="margin-top:var(--sp-3)"
        >
          {{ watermarking ? '添加中...' : '添加水印' }}
        </el-button>
      </div>
    </div>

    <!-- ══════════ Step 5: Export ══════════ -->
    <div v-if="step === 5" class="step-body export-step">
      <div class="step-center">
        <div class="step-icon success"><el-icon :size="40"><Check /></el-icon></div>
        <h3>商务文件编写完成</h3>
        <p>点击下方按钮导出 Word 文档</p>
        <el-button type="primary" size="large" :loading="exporting" @click="exportDocument">
          {{ exporting ? '正在生成...' : '导出 Word 文档' }}
        </el-button>
        <el-button size="large" @click="resetAll" style="margin-top:var(--sp-3)">
          重新开始
        </el-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import {
  Document, UploadFilled, Check, Loading, Rank,
} from '@element-plus/icons-vue'
import api from '@/composables/useApi'

// ── State ───────────────────────────────────────────────────────

const step = ref(0)
const sessionId = ref<number | null>(null)

// Step 0
const tenderFile = ref<File | null>(null)
const isDragTender = ref(false)
const uploading = ref(false)
const tenderInputEl = ref<HTMLInputElement | null>(null)

// Step 1
const extracting = ref(false)
const clauses = ref<any[]>([])

// Step 2
const outline = ref<any[]>([])
const dragIdx = ref<number | null>(null)
const generatingOutline = ref(false)

// Step 3
const filling = ref(false)
const fillProgress = reactive({ current: 0, total: 0, title: '' })
const projectName = ref('')
const projectCode = ref('')
const contentMap = ref<Record<string, string>>({})

// Step 4
const materials = ref<any[]>([])
const selectedMaterials = ref<any[]>([])
const watermarking = ref(false)

// Step 5
const exporting = ref(false)

// Timer for AI waiting
const elapsedTime = ref(0)
let timerInterval: ReturnType<typeof setInterval> | null = null

const startTimer = () => {
  elapsedTime.value = 0
  timerInterval = setInterval(() => { elapsedTime.value++ }, 1000)
}
const stopTimer = () => {
  if (timerInterval) { clearInterval(timerInterval); timerInterval = null }
}
onUnmounted(() => stopTimer())

// ── Helpers ─────────────────────────────────────────────────────

const categoryLabel = (cat: string) => {
  const map: Record<string, string> = {
    certificate: '资质证书',
    financial: '财务报表',
    declaration: '声明函',
    license: '证照',
    performance: '业绩',
    introduction: '公司介绍',
    other: '其他',
  }
  return map[cat] || cat
}

const categoryType = (cat: string) => {
  const map: Record<string, string> = {
    certificate: 'success',
    financial: 'warning',
    declaration: 'info',
    license: '',
    performance: 'danger',
  }
  return map[cat] || ''
}

// ── Step 0: Upload ──────────────────────────────────────────────

const onDropTender = (e: DragEvent) => {
  isDragTender.value = false
  const files = e.dataTransfer?.files
  if (files?.length) {
    tenderFile.value = files[0]
  }
}

const onSelectTender = (e: Event) => {
  const input = e.target as HTMLInputElement
  if (input.files?.length) {
    tenderFile.value = input.files[0]
  }
}

const uploadTender = async () => {
  if (!tenderFile.value) return
  uploading.value = true
  try {
    const formData = new FormData()
    formData.append('file', tenderFile.value)
    const { data } = await api.post('/bid-document/upload', formData)
    if (data.ok) {
      sessionId.value = data.session_id
      ElMessage.success('上传成功')
      step.value = 1
      extractClauses()
    } else {
      ElMessage.error(data.message || '上传失败')
    }
  } catch (e: any) {
    ElMessage.error(e.message || '上传失败')
  } finally {
    uploading.value = false
  }
}

// ── Step 1: Extract clauses ─────────────────────────────────────

const extractClauses = async () => {
  if (!sessionId.value) return
  extracting.value = true
  clauses.value = []
  startTimer()

  try {
    const { data } = await api.post('/bid-document/extract', { session_id: sessionId.value }, { timeout: 0 })
    console.log('[BidDoc] extract response:', JSON.stringify(data).slice(0, 500))
    if (data.ok) {
      clauses.value = data.clauses || []
      console.log('[BidDoc] clauses set:', clauses.value.length)
      ElMessage.success(data.message || '条款提取成功')
      step.value = 1
    } else {
      ElMessage.error(data.message || '条款提取失败')
    }
  } catch (e: any) {
    console.error('[BidDoc] extract error:', e)
    ElMessage.error(e.message || '条款提取失败')
  } finally {
    extracting.value = false
    stopTimer()
  }
}

const fetchSession = async () => {
  if (!sessionId.value) return
  try {
    const { data } = await api.get(`/bid-document/sessions/${sessionId.value}`)
    if (data.ok && data.data) {
      clauses.value = data.data.clauses || []
      outline.value = (data.data.outline || []).map((item: any) => ({ ...item, selected: true }))
      contentMap.value = data.data.content || {}
      projectName.value = data.data.project_name || ''
      projectCode.value = data.data.project_code || ''
    }
  } catch (e) {
    console.error('Fetch session failed:', e)
  }
}

// ── Step 2: Generate outline ────────────────────────────────────

const generateOutline = async () => {
  if (!sessionId.value) return
  generatingOutline.value = true
  startTimer()
  try {
    const { data } = await api.post('/bid-document/outline', { session_id: sessionId.value }, { timeout: 0 })
    if (data.ok) {
      outline.value = (data.outline || []).map((item: any) => ({ ...item, selected: true }))
      step.value = 2
      ElMessage.success(`大纲生成成功，共 ${outline.value.length} 个章节`)
    } else {
      ElMessage.error(data.message || '大纲生成失败')
    }
  } catch (e: any) {
    ElMessage.error(e.message || '大纲生成失败')
  } finally {
    generatingOutline.value = false
    stopTimer()
  }
}

const onDragStart = (idx: number) => {
  dragIdx.value = idx
}

const onDrop = (targetIdx: number) => {
  if (dragIdx.value === null || dragIdx.value === targetIdx) return
  const item = outline.value.splice(dragIdx.value, 1)[0]
  outline.value.splice(targetIdx, 0, item)
  dragIdx.value = null
}

// ── Step 3: Fill content ────────────────────────────────────────

const startFill = async () => {
  if (!sessionId.value) return
  
  // Update outline first
  await api.put('/bid-document/outline', {
    session_id: sessionId.value,
    outline: outline.value.filter(item => item.selected),
  })
  
  step.value = 3
  filling.value = true
  fillProgress.current = 0
  fillProgress.total = outline.value.filter(item => item.selected).length
  
  try {
    await api.post('/bid-document/fill', {
      session_id: sessionId.value,
      project_name: projectName.value,
      project_code: projectCode.value,
    })
    
    // For SSE, we need to handle streaming - simplified for now
    await fetchSession()
  } catch (e: any) {
    ElMessage.error(e.message || '内容填充失败')
  } finally {
    filling.value = false
  }
}

// ── Step 4: Watermark ───────────────────────────────────────────

const loadMaterials = async () => {
  try {
    const { data } = await api.get('/bid-document/materials')
    if (data.ok) {
      materials.value = data.records || []
    }
  } catch (e) {
    console.error('Load materials failed:', e)
  }
}

const onMaterialSelect = (selection: any[]) => {
  selectedMaterials.value = selection
}

const addWatermarks = async () => {
  if (!selectedMaterials.value.length || !projectCode.value) return
  watermarking.value = true
  try {
    const { data } = await api.post('/bid-document/watermark', {
      material_ids: selectedMaterials.value.map(m => m.id),
      project_code: projectCode.value,
    })
    if (data.ok) {
      ElMessage.success('水印添加成功')
      step.value = 5
    } else {
      ElMessage.error(data.message || '水印添加失败')
    }
  } catch (e: any) {
    ElMessage.error(e.message || '水印添加失败')
  } finally {
    watermarking.value = false
  }
}

// ── Step 5: Export ──────────────────────────────────────────────

const exportDocument = async () => {
  if (!sessionId.value) return
  exporting.value = true
  try {
    const response = await fetch(`/api/bid-document/export`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-API-Key': 'dev' },
      body: JSON.stringify({ session_id: sessionId.value, format: 'docx' }),
    })
    
    if (response.ok) {
      const blob = await response.blob()
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `商务文件_${projectName.value || sessionId.value}.docx`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      window.URL.revokeObjectURL(url)
      ElMessage.success('导出成功')
    } else {
      ElMessage.error('导出失败')
    }
  } catch (e: any) {
    ElMessage.error(e.message || '导出失败')
  } finally {
    exporting.value = false
  }
}

const resetAll = () => {
  step.value = 0
  sessionId.value = null
  tenderFile.value = null
  clauses.value = []
  outline.value = []
  contentMap.value = {}
  projectName.value = ''
  projectCode.value = ''
  materials.value = []
  selectedMaterials.value = []
}

// ── Lifecycle ───────────────────────────────────────────────────

onMounted(() => {
  loadMaterials()
})
</script>

<style scoped>
.doc-writer {
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
.step-icon.success {
  background: rgba(74, 222, 128, 0.15);
  color: #4ade80;
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

/* ── Clauses step ── */
.clauses-step { padding: var(--sp-4) var(--sp-6); }
.clauses-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: var(--sp-4);
}
.clauses-header h3 {
  font-size: var(--fs-base);
  font-weight: 600;
  color: var(--c-text-primary);
  margin: 0 0 var(--sp-1);
}
.clauses-header p {
  font-size: var(--fs-sm);
  color: var(--c-text-tertiary);
  margin: 0;
}
.clauses-actions { display: flex; gap: var(--sp-2); flex-shrink: 0; }
.clauses-table { flex: 1; }

.extracting-box {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--sp-4);
  padding: var(--sp-10) var(--sp-8);
  color: var(--c-text-tertiary);
  position: relative;
}
.extracting-info {
  text-align: center;
}
.extracting-info h4 {
  font-size: var(--fs-base);
  font-weight: 600;
  color: var(--c-text-primary);
  margin: 0 0 var(--sp-2);
}
.extracting-info p {
  font-size: var(--fs-sm);
  color: var(--c-text-tertiary);
  margin: 0 0 var(--sp-2);
}
.elapsed-time {
  font-size: var(--fs-xs);
  color: var(--c-accent);
  font-variant-numeric: tabular-nums;
  animation: fade-pulse 2s ease-in-out infinite;
}
.ai-pulse-ring {
  position: absolute;
  width: 80px;
  height: 80px;
  border-radius: 50%;
  border: 2px solid var(--c-accent);
  opacity: 0;
  animation: pulse-ring 2s ease-out infinite;
}
@keyframes pulse-ring {
  0% { transform: scale(0.6); opacity: 0.6; }
  100% { transform: scale(1.8); opacity: 0; }
}
@keyframes fade-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

/* ── Outline step ── */
.outline-step { padding: var(--sp-4) var(--sp-6); }
.outline-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: var(--sp-4);
}
.outline-header h3 {
  font-size: var(--fs-base);
  font-weight: 600;
  color: var(--c-text-primary);
  margin: 0 0 var(--sp-1);
}
.outline-header p {
  font-size: var(--fs-sm);
  color: var(--c-text-tertiary);
  margin: 0;
}
.outline-actions { display: flex; gap: var(--sp-2); flex-shrink: 0; }

.outline-list {
  flex: 1;
  overflow-y: auto;
  border: 1px solid var(--c-border);
  border-radius: var(--radius-sm);
  background: var(--glass-bg);
}
.outline-item {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  padding: var(--sp-3) var(--sp-4);
  border-bottom: 1px solid var(--c-border);
  cursor: grab;
  transition: background 0.15s;
}
.outline-item:hover {
  background: rgba(255,255,255,0.04);
}
.outline-item.level-2 {
  padding-left: var(--sp-8);
}
.drag-handle {
  color: var(--c-text-tertiary);
  cursor: grab;
}
.outline-id {
  font-size: var(--fs-sm);
  color: var(--c-text-tertiary);
  min-width: 40px;
}
.outline-title {
  flex: 1;
  font-size: var(--fs-sm);
  color: var(--c-text-primary);
}

/* ── Fill step ── */
.fill-step { padding: var(--sp-4) var(--sp-6); }
.fill-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: var(--sp-4);
}
.fill-header h3 {
  font-size: var(--fs-base);
  font-weight: 600;
  color: var(--c-text-primary);
  margin: 0 0 var(--sp-1);
}
.fill-header p {
  font-size: var(--fs-sm);
  color: var(--c-text-tertiary);
  margin: 0;
}
.fill-actions { display: flex; gap: var(--sp-2); flex-shrink: 0; }
.fill-form {
  margin-bottom: var(--sp-4);
  padding: var(--sp-3);
  background: rgba(255,255,255,0.02);
  border: 1px solid var(--c-border);
  border-radius: var(--radius-sm);
}
.fill-content {
  flex: 1;
  overflow-y: auto;
}
.content-section {
  margin-bottom: var(--sp-4);
}
.section-header {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  margin-bottom: var(--sp-2);
  font-weight: 600;
  color: var(--c-text-primary);
}
.section-header.level-2 {
  padding-left: var(--sp-4);
  font-weight: 500;
  font-size: var(--fs-sm);
}
.section-id {
  color: var(--c-text-tertiary);
}

/* ── Watermark step ── */
.watermark-step { padding: var(--sp-4) var(--sp-6); }
.watermark-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: var(--sp-4);
}
.watermark-header h3 {
  font-size: var(--fs-base);
  font-weight: 600;
  color: var(--c-text-primary);
  margin: 0 0 var(--sp-1);
}
.watermark-header p {
  font-size: var(--fs-sm);
  color: var(--c-text-tertiary);
  margin: 0;
}
.watermark-actions { display: flex; gap: var(--sp-2); flex-shrink: 0; }
.watermark-form {
  margin-bottom: var(--sp-4);
  padding: var(--sp-4);
  background: rgba(255,255,255,0.02);
  border: 1px solid var(--c-border);
  border-radius: var(--radius-sm);
}
.watermark-preview {
  color: var(--c-text-tertiary);
  font-style: italic;
}
.materials-section h4 {
  font-size: var(--fs-sm);
  font-weight: 600;
  color: var(--c-text-primary);
  margin: 0 0 var(--sp-3);
}
.file-badge {
  display: inline-block;
  padding: 2px 8px;
  background: rgba(74, 222, 128, 0.15);
  color: #4ade80;
  border-radius: var(--radius-sm);
  font-size: 11px;
}

/* ── Export step ── */
.export-step { }
</style>
