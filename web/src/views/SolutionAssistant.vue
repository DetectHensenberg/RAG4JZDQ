<template>
  <div class="solution-page">
    <!-- Header -->
    <div class="solution-header">
      <h2 class="solution-title">方案助手</h2>
      <div class="header-actions">
        <el-tag :type="statusTagType" size="default">{{ statusText }}</el-tag>
        <el-button
          v-if="session"
          text
          type="danger"
          @click="resetSession"
        >
          <el-icon><Delete /></el-icon>
          重新开始
        </el-button>
      </div>
    </div>

    <!-- Steps indicator -->
    <div class="steps-bar">
      <el-steps :active="currentStep" finish-status="success" simple>
        <el-step title="上传需求" />
        <el-step title="生成大纲" />
        <el-step title="生成内容" />
        <el-step title="导出方案" />
      </el-steps>
    </div>

    <!-- Body -->
    <div class="solution-body">
      <!-- Step 1: Upload & Parse -->
      <div v-if="currentStep === 0" class="step-content">
        <div class="upload-section">
          <h3>输入需求</h3>
          <div class="input-row">
            <el-input v-model="projectName" placeholder="项目名称" class="name-input" />
            <el-select v-model="projectType" placeholder="项目类型" class="type-select">
              <el-option label="系统集成" value="系统集成" />
              <el-option label="软件开发" value="软件开发" />
              <el-option label="网络安全" value="网络安全" />
              <el-option label="数据治理" value="数据治理" />
              <el-option label="云计算" value="云计算" />
              <el-option label="智慧城市" value="智慧城市" />
              <el-option label="其他" value="其他" />
            </el-select>
          </div>

          <el-tabs v-model="inputMode" class="input-tabs">
            <el-tab-pane label="上传文件" name="file">
              <el-upload
                ref="fileUpload"
                drag
                :auto-upload="false"
                :limit="1"
                accept=".pdf,.docx,.doc,.txt,.md"
                :on-change="handleFileChange"
              >
                <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
                <div class="el-upload__text">拖拽文件到此处，或 <em>点击上传</em></div>
                <template #tip>
                  <div class="el-upload__tip">支持 PDF / DOCX / TXT / MD 格式</div>
                </template>
              </el-upload>
            </el-tab-pane>
            <el-tab-pane label="粘贴文本" name="text">
              <el-input
                v-model="inputText"
                type="textarea"
                :rows="10"
                placeholder="粘贴需求/标书的文本内容..."
              />
            </el-tab-pane>
          </el-tabs>

          <!-- Optional template upload -->
          <div class="template-section">
            <h4>
              <el-icon><Document /></el-icon>
              方案模板（可选）
            </h4>
            <p class="template-tip">上传已有方案模板 Word 文件，大纲将沿用模板的目录结构</p>
            <el-upload
              ref="templateUpload"
              :auto-upload="false"
              :limit="1"
              accept=".docx,.doc"
              :on-change="handleTemplateChange"
            >
              <el-button type="default">
                <el-icon><FolderAdd /></el-icon>
                选择模板文件
              </el-button>
              <template #tip>
                <span class="el-upload__tip" style="margin-left: 8px">仅支持 .docx</span>
              </template>
            </el-upload>
          </div>

          <div class="action-bar">
            <el-button type="primary" :loading="parsing" @click="handleParse" size="large">
              <el-icon><MagicStick /></el-icon>
              解析需求
            </el-button>
          </div>
        </div>
      </div>

      <!-- Step 2: Outline -->
      <div v-if="currentStep === 1" class="step-content">
        <div class="outline-section">
          <div class="outline-header">
            <h3>方案大纲</h3>
            <div class="outline-actions">
              <el-button @click="currentStep = 0" text>
                <el-icon><Back /></el-icon>
                返回修改
              </el-button>
              <el-button
                type="primary"
                :loading="generatingOutline"
                @click="handleGenerateOutline"
              >
                <el-icon><MagicStick /></el-icon>
                {{ outline.length ? '重新生成' : '生成大纲' }}
              </el-button>
            </div>
          </div>

          <!-- Requirements preview -->
          <el-collapse class="req-collapse">
            <el-collapse-item title="已解析需求" :name="1">
              <div v-for="req in requirements" :key="req.id" class="req-item">
                <el-tag :type="reqTagType(req.category)" size="small">{{ req.category }}</el-tag>
                <span class="req-title">{{ req.title }}</span>
                <span class="req-desc">{{ req.description }}</span>
              </div>
            </el-collapse-item>
          </el-collapse>

          <!-- Outline tree -->
          <div v-if="outline.length > 0" class="outline-tree">
            <div
              v-for="(item, idx) in outline"
              :key="item.id"
              class="outline-item"
              :class="'level-' + item.level"
            >
              <span class="outline-num">{{ idx + 1 }}.</span>
              <el-input
                v-model="item.title"
                class="outline-title-input"
                size="default"
              />
              <el-tag size="small" type="info">L{{ item.level }}</el-tag>
            </div>
          </div>

          <div v-if="outline.length > 0" class="action-bar">
            <el-button @click="handleSaveOutline">保存修改</el-button>
            <el-button type="primary" @click="currentStep = 2" size="large">
              下一步：生成内容
              <el-icon><Right /></el-icon>
            </el-button>
          </div>
        </div>
      </div>

      <!-- Step 3: Content generation (SSE) -->
      <div v-if="currentStep === 2" class="step-content">
        <div class="generate-section">
          <div class="generate-header">
            <h3>方案内容生成</h3>
            <el-button @click="currentStep = 1" text>
              <el-icon><Back /></el-icon>
              返回修改大纲
            </el-button>
          </div>

          <div v-if="!generating && !generated" class="generate-start">
            <el-button type="primary" size="large" @click="handleGenerate">
              <el-icon><MagicStick /></el-icon>
              开始生成方案内容
            </el-button>
            <p class="generate-tip">将基于知识库检索素材，逐章节生成方案内容</p>
          </div>

          <!-- Progress -->
          <div v-if="generating" class="generate-progress">
            <el-progress
              :percentage="genProgress"
              :format="() => `${genCurrent}/${genTotal}`"
              :stroke-width="8"
              status="success"
            />
            <p class="gen-status">正在生成: {{ genCurrentTitle }}</p>
          </div>

          <!-- Generated content cards -->
          <div v-if="Object.keys(contentMap).length > 0" class="content-cards">
            <div
              v-for="item in outline"
              :key="item.id"
              class="content-card"
              :class="{ 'has-content': !!contentMap[item.id] }"
            >
              <div class="card-header" @click="toggleCard(item.id)">
                <span class="card-title">
                  <el-icon v-if="contentMap[item.id]" color="var(--el-color-success)"><CircleCheck /></el-icon>
                  <el-icon v-else color="var(--el-color-info)"><Loading /></el-icon>
                  {{ item.title }}
                </span>
                <el-icon><ArrowDown /></el-icon>
              </div>
              <div v-if="expandedCards.has(item.id) && contentMap[item.id]" class="card-body">
                <div class="markdown-content" v-html="renderMd(contentMap[item.id])"></div>
              </div>
            </div>
          </div>

          <div v-if="generated" class="action-bar">
            <el-button type="primary" @click="currentStep = 3" size="large">
              下一步：导出方案
              <el-icon><Right /></el-icon>
            </el-button>
          </div>
        </div>
      </div>

      <!-- Step 4: Export -->
      <div v-if="currentStep === 3" class="step-content">
        <div class="export-section">
          <div class="export-card">
            <el-icon :size="64" color="var(--el-color-primary)"><Document /></el-icon>
            <h3>{{ projectName || '技术方案' }}</h3>
            <p>共 {{ outline.length }} 个章节，{{ Object.keys(contentMap).length }} 个已生成内容</p>
            <el-button type="primary" size="large" :loading="exporting" @click="handleExport">
              <el-icon><Download /></el-icon>
              导出 Word 文档
            </el-button>
          </div>
          <div class="action-bar">
            <el-button @click="currentStep = 2" text>
              <el-icon><Back /></el-icon>
              返回查看内容
            </el-button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import {
  UploadFilled, MagicStick, Document, FolderAdd,
  Back, Right, Delete, ArrowDown, Download,
  CircleCheck, Loading,
} from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import api from '@/composables/useApi'
import { useSSE } from '@/composables/useSSE'
import { renderMarkdown } from '@/utils/markdown'

// ── State ───────────────────────────────────────────────────────
const currentStep = ref(0)
const sessionId = ref<number | null>(null)
const session = computed(() => sessionId.value !== null)

// Step 1
const projectName = ref('')
const projectType = ref('')
const inputMode = ref('file')
const inputText = ref('')
const selectedFile = ref<File | null>(null)
const templateFile = ref<File | null>(null)
const parsing = ref(false)

// Step 2
const requirements = ref<any[]>([])
const outline = ref<any[]>([])
const generatingOutline = ref(false)

// Step 3
const generating = ref(false)
const generated = ref(false)
const genProgress = ref(0)
const genCurrent = ref(0)
const genTotal = ref(0)
const genCurrentTitle = ref('')
const contentMap = ref<Record<string, string>>({})
const expandedCards = ref(new Set<string>())

// Step 4
const exporting = ref(false)

const { stream, abort } = useSSE()

// ── Computed ────────────────────────────────────────────────────
const statusText = computed(() => {
  if (generating.value) return '生成中...'
  if (generated.value) return '已完成'
  if (outline.value.length > 0) return '大纲已就绪'
  if (requirements.value.length > 0) return '需求已解析'
  return '待输入'
})

const statusTagType = computed(() => {
  if (generating.value) return 'warning'
  if (generated.value) return 'success'
  if (outline.value.length > 0) return 'primary'
  return 'info'
})

// ── Methods ─────────────────────────────────────────────────────
function handleFileChange(file: any) {
  selectedFile.value = file.raw
}

function handleTemplateChange(file: any) {
  templateFile.value = file.raw
}

function reqTagType(cat: string) {
  const map: Record<string, string> = {
    functional: 'primary',
    non_functional: 'warning',
    constraint: 'danger',
    deliverable: 'success',
  }
  return (map[cat] || 'info') as any
}

function toggleCard(id: string) {
  if (expandedCards.value.has(id)) {
    expandedCards.value.delete(id)
  } else {
    expandedCards.value.add(id)
  }
}

function renderMd(text: string): string {
  try {
    return renderMarkdown(text)
  } catch {
    return text?.replace(/\n/g, '<br>') || ''
  }
}

async function handleParse() {
  if (inputMode.value === 'file' && !selectedFile.value) {
    ElMessage.warning('请选择需求文件')
    return
  }
  if (inputMode.value === 'text' && !inputText.value.trim()) {
    ElMessage.warning('请输入需求文本')
    return
  }

  parsing.value = true
  try {
    const formData = new FormData()
    if (inputMode.value === 'file' && selectedFile.value) {
      formData.append('file', selectedFile.value)
    }
    if (inputMode.value === 'text') {
      formData.append('text', inputText.value)
    }
    formData.append('project_name', projectName.value)
    formData.append('project_type', projectType.value)

    const { data } = await api.post('/solution/parse', formData)
    if (!data.ok) {
      ElMessage.error(data.message || '解析失败')
      return
    }

    sessionId.value = data.session_id
    requirements.value = data.requirements || []
    ElMessage.success(data.message)

    // Upload template if provided
    if (templateFile.value && sessionId.value) {
      const tplForm = new FormData()
      tplForm.append('file', templateFile.value)
      tplForm.append('session_id', String(sessionId.value))
      const { data: tplData } = await api.post('/solution/upload-template', tplForm)
      if (tplData.ok) {
        ElMessage.success(`模板解析成功: ${tplData.template_outline?.length || 0} 个章节`)
      }
    }

    currentStep.value = 1
  } catch (e: any) {
    ElMessage.error(e.message || '请求失败')
  } finally {
    parsing.value = false
  }
}

async function handleGenerateOutline() {
  if (!sessionId.value) return
  generatingOutline.value = true
  try {
    const { data } = await api.post('/solution/outline', { session_id: sessionId.value })
    if (!data.ok) {
      ElMessage.error(data.message || '大纲生成失败')
      return
    }
    outline.value = data.outline || []
    ElMessage.success(`生成 ${outline.value.length} 个章节大纲`)
  } catch (e: any) {
    ElMessage.error(e.message || '请求失败')
  } finally {
    generatingOutline.value = false
  }
}

async function handleSaveOutline() {
  if (!sessionId.value) return
  try {
    const { data } = await api.put('/solution/outline', {
      session_id: sessionId.value,
      outline: outline.value,
    })
    if (data.ok) {
      ElMessage.success('大纲已保存')
    }
  } catch (e: any) {
    ElMessage.error(e.message || '保存失败')
  }
}

async function handleGenerate() {
  if (!sessionId.value) return
  generating.value = true
  generated.value = false
  contentMap.value = {}
  genProgress.value = 0

  await stream(
    '/api/solution/generate',
    { session_id: sessionId.value },
    (event) => {
      if (event.type === 'progress') {
        genCurrent.value = event.current
        genTotal.value = event.total
        genCurrentTitle.value = event.section_title || ''
        genProgress.value = Math.round((event.current / event.total) * 100)
      } else if (event.type === 'section') {
        contentMap.value[event.section_id] = event.content || ''
        expandedCards.value.add(event.section_id)
      } else if (event.type === 'done') {
        if (event.content) {
          contentMap.value = { ...contentMap.value, ...event.content }
        }
        generated.value = true
        generating.value = false
      } else if (event.type === 'error') {
        ElMessage.error(event.message || '生成出错')
      }
    },
    () => {
      generating.value = false
      if (Object.keys(contentMap.value).length > 0) {
        generated.value = true
      }
    },
    (err) => {
      generating.value = false
      ElMessage.error(`生成失败: ${err.message}`)
    },
  )
}

async function handleExport() {
  if (!sessionId.value) return
  exporting.value = true
  try {
    const response = await api.post(
      '/solution/export',
      { session_id: sessionId.value },
      { responseType: 'blob' },
    )
    const blob = new Blob([response.data])
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${projectName.value || '技术方案'}.docx`
    a.click()
    URL.revokeObjectURL(url)
    ElMessage.success('方案导出成功')
  } catch (e: any) {
    ElMessage.error(e.message || '导出失败')
  } finally {
    exporting.value = false
  }
}

function resetSession() {
  abort()
  sessionId.value = null
  currentStep.value = 0
  requirements.value = []
  outline.value = []
  contentMap.value = {}
  generating.value = false
  generated.value = false
  selectedFile.value = null
  templateFile.value = null
  inputText.value = ''
}
</script>

<style scoped>
.solution-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--c-bg);
}

/* Header */
.solution-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--sp-4) var(--page-padding);
  border-bottom: 1px solid var(--c-border);
  background: var(--c-bg-elevated);
  flex-shrink: 0;
}
.solution-title {
  font-size: var(--fs-lg);
  font-weight: 700;
  color: var(--c-text-primary);
  margin: 0;
}
.header-actions {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
}

/* Steps */
.steps-bar {
  padding: var(--sp-4) var(--page-padding);
  border-bottom: 1px solid var(--c-border);
  background: var(--c-bg-elevated);
  flex-shrink: 0;
}

/* Body */
.solution-body {
  flex: 1;
  overflow-y: auto;
  padding: var(--sp-5) var(--page-padding);
}

.step-content {
  max-width: 960px;
  margin: 0 auto;
}

/* Upload section */
.upload-section h3, .outline-section h3 {
  font-size: var(--fs-base);
  font-weight: 600;
  color: var(--c-text-primary);
  margin: 0 0 var(--sp-4);
}
.input-row {
  display: flex;
  gap: var(--sp-3);
  margin-bottom: var(--sp-4);
}
.name-input { flex: 1; }
.type-select { min-width: 140px; }

.input-tabs {
  margin-bottom: var(--sp-4);
}

/* Template */
.template-section {
  margin-top: var(--sp-4);
  padding: var(--sp-4);
  border: 1px dashed var(--c-border);
  border-radius: var(--radius-lg);
  background: var(--c-bg-soft);
}
.template-section h4 {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  margin: 0 0 var(--sp-2);
  font-size: var(--fs-sm);
  font-weight: 600;
}
.template-tip {
  font-size: var(--fs-xs);
  color: var(--c-text-tertiary);
  margin: 0 0 var(--sp-3);
}

/* Action bar */
.action-bar {
  display: flex;
  justify-content: flex-end;
  gap: var(--sp-3);
  margin-top: var(--sp-5);
  padding-top: var(--sp-4);
  border-top: 1px solid var(--c-border);
}

/* Outline */
.outline-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--sp-4);
}
.outline-actions {
  display: flex;
  gap: var(--sp-2);
}

.req-collapse {
  margin-bottom: var(--sp-4);
}
.req-item {
  display: flex;
  align-items: baseline;
  gap: var(--sp-2);
  padding: var(--sp-1) 0;
  font-size: var(--fs-sm);
}
.req-title { font-weight: 600; }
.req-desc {
  color: var(--c-text-tertiary);
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.outline-tree {
  border: 1px solid var(--c-border);
  border-radius: var(--radius-lg);
  overflow: hidden;
}
.outline-item {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  padding: var(--sp-2) var(--sp-3);
  border-bottom: 1px solid var(--c-border);
}
.outline-item:last-child { border-bottom: none; }
.outline-item.level-2 { padding-left: calc(var(--sp-3) + 20px); }
.outline-item.level-3 { padding-left: calc(var(--sp-3) + 40px); }
.outline-num {
  color: var(--c-text-tertiary);
  font-size: var(--fs-sm);
  min-width: 24px;
}
.outline-title-input { flex: 1; }

/* Generate */
.generate-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--sp-4);
}
.generate-start {
  text-align: center;
  padding: var(--sp-8) 0;
}
.generate-tip {
  margin-top: var(--sp-3);
  color: var(--c-text-tertiary);
  font-size: var(--fs-sm);
}
.generate-progress {
  margin-bottom: var(--sp-5);
}
.gen-status {
  margin-top: var(--sp-2);
  color: var(--c-text-secondary);
  font-size: var(--fs-sm);
}

/* Content cards */
.content-cards {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
}
.content-card {
  border: 1px solid var(--c-border);
  border-radius: var(--radius-md);
  overflow: hidden;
}
.content-card.has-content {
  border-color: var(--el-color-success-light-5);
}
.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--sp-3);
  cursor: pointer;
  background: var(--c-bg-soft);
}
.card-header:hover { background: var(--c-bg-mute); }
.card-title {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  font-weight: 600;
  font-size: var(--fs-sm);
}
.card-body {
  padding: var(--sp-4);
  border-top: 1px solid var(--c-border);
  font-size: var(--fs-sm);
  line-height: 1.8;
}

/* Export */
.export-section {
  text-align: center;
  padding: var(--sp-8) 0;
}
.export-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--sp-4);
  padding: var(--sp-8);
  border: 1px solid var(--c-border);
  border-radius: var(--radius-lg);
  background: var(--c-bg-elevated);
  max-width: 400px;
  margin: 0 auto;
}
.export-card h3 {
  font-size: var(--fs-lg);
  margin: 0;
}
.export-card p {
  color: var(--c-text-tertiary);
  font-size: var(--fs-sm);
  margin: 0;
}
</style>
