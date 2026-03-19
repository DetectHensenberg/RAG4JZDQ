<template>
  <div class="chat-page">
    <!-- Messages -->
    <div ref="messagesRef" class="messages-area">
      <!-- Empty state -->
      <div v-if="!messages.length && !streaming" class="empty-state">
        <div class="empty-icon">
          <el-icon :size="32"><ChatDotRound /></el-icon>
        </div>
        <h3>智能知识助手</h3>
        <p>输入问题，基于知识库检索并生成专业回答</p>
      </div>

      <!-- Message list -->
      <div class="messages-list">
        <div v-for="(msg, i) in messages" :key="i" class="message" :class="msg.role">
          <div class="message-bubble">
            <div v-if="msg.role === 'user'" class="message-text">{{ msg.content }}</div>
            <template v-else>
              <div v-html="renderMd(msg.content)" class="message-content" @click="handleContentClick" />
              <div class="message-actions">
                <button class="action-btn" @click="saveAsMarkdown(msg.content, i)">
                  <el-icon :size="16"><Download /></el-icon>
                  <span>保存</span>
                </button>
                <button class="action-btn" @click="copyContent(msg.content)">
                  <el-icon :size="16"><CopyDocument /></el-icon>
                  <span>复制</span>
                </button>
              </div>
            </template>
          </div>
        </div>

        <!-- Streaming -->
        <div v-if="streaming" class="message assistant">
          <div class="message-bubble">
            <div v-html="renderMd(streamBuffer)" class="message-content" @click="handleContentClick" />
            <span class="cursor-blink" />
          </div>
        </div>
      </div>

      <!-- References -->
      <div v-if="references.length" class="references">
        <details>
          <summary class="ref-toggle">{{ references.length }} 个参考来源</summary>
          <div class="ref-list">
            <div v-for="(ref, i) in references" :key="i" class="ref-item">
              <span class="ref-source">{{ ref.source?.split(/[/\\]/).pop() }}</span>
              <span class="ref-score">{{ ref.score }}</span>
            </div>
          </div>
        </details>
      </div>

      <!-- Related Images -->
      <div v-if="images.length" class="related-images">
        <details open>
          <summary class="img-toggle">{{ images.length }} 张相关图片</summary>
          <div class="img-grid">
            <div v-for="(img, i) in images" :key="i" class="img-item">
              <div class="img-score-bar" :style="{ width: (img.relevance * 100) + '%' }"></div>
              <img 
                :src="`/api/data/images/${img.image_id}/raw`" 
                :alt="img.caption || img.image_id"
                class="img-thumb"
                @click="openImage(img)"
              />
              <div v-if="img.caption" class="img-caption">{{ img.caption }}</div>
              <div class="img-meta">
                <span class="img-source">{{ img.source?.split(/[/\\]/).pop() }}</span>
                <span class="img-relevance" :class="getRelevanceClass(img.relevance)">
                  {{ (img.relevance * 100).toFixed(0) }}% 相关
                </span>
              </div>
            </div>
          </div>
        </details>
      </div>
    </div>

    <!-- Input -->
    <div class="input-area">
      <div class="input-container">
        <el-input
          v-model="question"
          type="textarea"
          :autosize="{ minRows: 1, maxRows: 4 }"
          placeholder="输入问题..."
          @keydown.enter.exact.prevent="sendQuestion"
          :disabled="streaming"
          class="chat-input"
        />
        <div class="input-actions">
          <el-button
            v-if="!streaming"
            type="primary"
            @click="sendQuestion"
            :disabled="!question.trim()"
            circle
          >
            <el-icon><Promotion /></el-icon>
          </el-button>
          <el-button
            v-else
            @click="stopStream"
            circle
          >
            <el-icon><VideoPause /></el-icon>
          </el-button>
        </div>
      </div>
      <div class="input-meta">
        <span>{{ collection }} · Top {{ topK }}</span>
        <div class="meta-actions">
          <button @click="showSettings = true" class="meta-btn">设置</button>
          <button @click="clearHistory" class="meta-btn danger">清空</button>
        </div>
      </div>
    </div>

    <!-- Image Lightbox -->
    <Teleport to="body">
      <div v-if="lightboxSrc" class="lightbox-overlay" @click="lightboxSrc = ''">
        <img :src="lightboxSrc" class="lightbox-img" @click.stop />
        <button class="lightbox-close" @click="lightboxSrc = ''">&times;</button>
      </div>
    </Teleport>

    <!-- Settings -->
    <el-drawer v-model="showSettings" title="问答设置" size="320px" direction="rtl">
      <el-form label-position="top" class="settings-form">
        <el-form-item label="集合名称">
          <el-input v-model="collection" />
        </el-form-item>
        <el-form-item label="检索数量 (Top-K)">
          <el-slider v-model="topK" :min="1" :max="20" show-input />
        </el-form-item>
        <el-form-item label="最大 Token">
          <el-input-number v-model="maxTokens" :min="256" :max="16384" :step="256" class="w-full" />
        </el-form-item>
      </el-form>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick, onMounted, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { ChatDotRound, Promotion, VideoPause, Download, CopyDocument } from '@element-plus/icons-vue'
import { useSSE } from '@/composables/useSSE'
import { renderMarkdown, renderMermaidInContainer } from '@/utils/markdown'
import { saveAs } from 'file-saver'
import api from '@/composables/useApi'

interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
}

const messages = ref<ChatMessage[]>([])
const question = ref('')
const streaming = ref(false)
const streamBuffer = ref('')
const references = ref<any[]>([])
const images = ref<any[]>([])
const messagesRef = ref<HTMLElement | null>(null)
const showSettings = ref(false)

const collection = ref('default')
const topK = ref(5)
const maxTokens = ref(4096)

const { stream, abort } = useSSE()
const lightboxSrc = ref('')

function renderMd(text: string): string {
  return renderMarkdown(text || '')
}

async function triggerMermaid() {
  await nextTick()
  if (messagesRef.value) {
    await renderMermaidInContainer(messagesRef.value)
  }
  // Retry after delay — Vue may not have finished all DOM updates on first nextTick
  setTimeout(async () => {
    if (messagesRef.value) {
      await renderMermaidInContainer(messagesRef.value)
    }
  }, 800)
}

function saveAsMarkdown(content: string, idx: number) {
  const blob = new Blob([content], { type: 'text/markdown;charset=utf-8' })
  const ts = new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-')
  saveAs(blob, `回答-${idx + 1}-${ts}.md`)
  ElMessage.success('已保存为 Markdown 文件')
}

function copyContent(content: string) {
  navigator.clipboard.writeText(content).then(() => {
    ElMessage.success('已复制到剪贴板')
  }).catch(() => {
    ElMessage.error('复制失败')
  })
}

function scrollToBottom() {
  nextTick(() => {
    if (messagesRef.value) {
      messagesRef.value.scrollTop = messagesRef.value.scrollHeight
    }
  })
}

async function sendQuestion() {
  const q = question.value.trim()
  if (!q || streaming.value) return

  messages.value.push({ role: 'user', content: q })
  question.value = ''
  streaming.value = true
  streamBuffer.value = ''
  references.value = []
  images.value = []
  scrollToBottom()

  await stream(
    '/api/chat/stream',
    { question: q, collection: collection.value, top_k: topK.value, max_tokens: maxTokens.value },
    (event) => {
      if (event.type === 'token') {
        streamBuffer.value += event.content
        scrollToBottom()
      } else if (event.type === 'references') {
        references.value = event.data || []
      } else if (event.type === 'images') {
        console.log('[DEBUG] images event received:', event.data?.length, 'images')
        images.value = event.data || []
      } else if (event.type === 'done') {
        console.log('[DEBUG] done event, images.length =', images.value.length)
        messages.value.push({ role: 'assistant', content: event.answer || streamBuffer.value })
        streamBuffer.value = ''
        streaming.value = false
        scrollToBottom()
        triggerMermaid()
      } else if (event.type === 'error') {
        ElMessage.error(event.message || '生成失败')
        streaming.value = false
      }
    },
    () => {
      if (streaming.value && streamBuffer.value) {
        messages.value.push({ role: 'assistant', content: streamBuffer.value })
        streamBuffer.value = ''
      }
      streaming.value = false
    },
    (err) => {
      ElMessage.error(`请求失败: ${err.message}`)
      streaming.value = false
    },
  )
}

function stopStream() {
  abort()
  if (streamBuffer.value) {
    messages.value.push({ role: 'assistant', content: streamBuffer.value })
    streamBuffer.value = ''
  }
  streaming.value = false
}

async function clearHistory() {
  try {
    await api.delete('/chat/history')
    messages.value = []
    references.value = []
    images.value = []
    ElMessage.success('已清空')
  } catch {
    ElMessage.error('清空失败')
  }
}

function openImage(img: any) {
  lightboxSrc.value = `/api/data/images/${img.image_id}/raw`
}

function handleContentClick(e: MouseEvent) {
  const target = e.target as HTMLElement
  if (target.tagName === 'IMG') {
    lightboxSrc.value = (target as HTMLImageElement).src
  }
}

function getRelevanceClass(relevance: number): string {
  if (relevance >= 0.7) return 'high'
  if (relevance >= 0.4) return 'medium'
  return 'low'
}

async function loadHistory() {
  try {
    const { data } = await api.get('/chat/history?limit=20')
    if (data.ok && data.data) {
      for (const entry of data.data) {
        messages.value.push({ role: 'user', content: entry.question })
        messages.value.push({ role: 'assistant', content: entry.answer })
      }
      scrollToBottom()
    }
  } catch {
    // ignore
  }
}

onMounted(async () => {
  await loadHistory()
  triggerMermaid()
})

watch(() => messages.value.length, () => triggerMermaid())
</script>

<style scoped>
.chat-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--c-bg);
}

.messages-area {
  flex: 1;
  overflow-y: auto;
  padding: var(--sp-8) var(--page-padding);
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
  line-height: var(--lh-tight);
  color: var(--c-text-primary);
  margin: 0 0 var(--sp-2);
}
.empty-state p {
  font-size: var(--fs-sm);
  color: var(--c-text-tertiary);
  line-height: var(--lh-normal);
  margin: 0;
  max-width: 360px;
}

/* Messages */
.message { margin-bottom: var(--sp-5); }
.message.user { display: flex; justify-content: flex-end; }
.message.user .message-bubble {
  background: rgba(255,255,255,0.08);
  border: 1px solid rgba(255,255,255,0.12);
  color: var(--c-text-primary);
  border-radius: var(--radius) var(--radius) var(--sp-1) var(--radius);
  max-width: 600px;
}
.message.assistant .message-bubble {
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
.message-content :deep(p) { margin: 0 0 var(--sp-3); text-indent: 2em; }
.message-content :deep(p:last-child) { margin: 0; }
.message-content :deep(pre) {
  background: rgba(255,255,255,0.04);
  border: 1px solid var(--c-border);
  padding: var(--sp-3) var(--sp-4);
  border-radius: var(--radius-sm);
  overflow-x: auto;
  font-size: var(--fs-sm);
  margin: var(--sp-3) 0;
}
.message-content :deep(code) {
  background: rgba(255,255,255,0.06);
  padding: 1px var(--sp-1);
  border-radius: var(--sp-1);
  font-size: 0.9em;
}
.message-content :deep(pre code) { background: none; padding: 0; }
.message-content :deep(table) {
  border-collapse: collapse;
  width: auto;
  max-width: 100%;
  margin: var(--sp-3) 0;
  font-size: 15px;
  display: block;
  overflow-x: auto;
  white-space: nowrap;
}
.message-content :deep(th),
.message-content :deep(td) {
  border: 1px solid var(--c-border);
  padding: var(--sp-2) var(--sp-4);
  text-indent: 0;
  white-space: normal;
  min-width: 80px;
}
.message-content :deep(th) {
  background: rgba(255,255,255,0.06);
  font-weight: 600;
  white-space: nowrap;
}
.message-content :deep(td) {
  vertical-align: top;
}
.message-content :deep(blockquote) { text-indent: 0; margin: var(--sp-3) 0; padding-left: 1em; border-left: 3px solid var(--c-border-hover); }
.message-content :deep(blockquote p) { text-indent: 0; }
.message-content :deep(h1),
.message-content :deep(h2),
.message-content :deep(h3) {
  margin: var(--sp-4) 0 var(--sp-2);
  font-weight: 600;
  line-height: var(--lh-tight);
}
.message-content :deep(h1) { font-size: var(--fs-xl); text-indent: 0; }
.message-content :deep(h2) { font-size: var(--fs-lg); text-indent: 0; }
.message-content :deep(h3) { font-size: 17px; text-indent: 0; }
.message-content :deep(ul),
.message-content :deep(ol) {
  padding-left: 2em;
  margin: var(--sp-2) 0;
  text-indent: 0;
}
.message-content :deep(li) {
  text-indent: 0;
  margin-bottom: var(--sp-1);
}

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

/* PlantUML / Diagrams */
.message-content :deep(.plantuml-block),
.message-content :deep(.mermaid-block) {
  margin: var(--sp-3) 0;
  padding: var(--sp-4);
  background: rgba(255,255,255,0.02);
  border: 1px solid var(--c-border);
  border-radius: var(--radius);
  overflow-x: auto;
  text-align: center;
}
.message-content :deep(.plantuml-block svg),
.message-content :deep(.mermaid-block svg) {
  max-width: 100%;
  height: auto;
}
.message-content :deep(.plantuml-loading),
.message-content :deep(.mermaid-loading) {
  color: var(--c-text-tertiary);
  font-size: var(--fs-xs);
  padding: var(--sp-4);
}
.message-content :deep(.plantuml-error),
.message-content :deep(.mermaid-error) {
  background: rgba(255,100,100,0.06);
  border: 1px solid rgba(255,100,100,0.15);
  color: var(--c-text-secondary);
}

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

/* References */
.references {
  max-width: 794px;
  margin: var(--sp-2) auto 0;
}
.ref-toggle {
  font-size: var(--fs-xs);
  color: var(--c-text-tertiary);
  cursor: pointer;
  padding: var(--sp-2) 0;
  user-select: none;
}
.ref-toggle:hover { color: var(--c-text-secondary); }
.ref-list { padding: var(--sp-2) 0; }
.ref-item {
  display: flex;
  justify-content: space-between;
  padding: var(--sp-2) var(--sp-3);
  background: var(--c-surface);
  border: 1px solid var(--c-border-subtle);
  border-radius: var(--radius-sm);
  margin-bottom: var(--sp-1);
  font-size: var(--fs-xs);
}
.ref-source { color: var(--c-text-secondary); }
.ref-score { color: var(--c-text-tertiary); font-variant-numeric: tabular-nums; }

/* Input */
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
.meta-actions { display: flex; gap: var(--sp-3); }
.meta-btn {
  background: none;
  border: none;
  font-size: var(--fs-xs);
  color: var(--c-text-tertiary);
  cursor: pointer;
  padding: 0;
  transition: color 0.15s;
}
.meta-btn:hover { color: var(--c-text-primary); }
.meta-btn.danger:hover { color: var(--c-danger); }

/* Related Images */
.related-images {
  max-width: 794px;
  margin: var(--sp-3) auto 0;
}
.img-toggle {
  font-size: var(--fs-xs);
  color: var(--c-text-tertiary);
  cursor: pointer;
  padding: var(--sp-2) 0;
  user-select: none;
}
.img-toggle:hover { color: var(--c-text-secondary); }
.img-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: var(--sp-3);
  padding: var(--sp-3) 0;
}
.img-item {
  background: var(--c-surface);
  border: 1px solid var(--c-border);
  border-radius: var(--radius);
  overflow: hidden;
  transition: transform 0.2s, border-color 0.2s;
  position: relative;
}
.img-item:hover {
  transform: translateY(-2px);
  border-color: var(--c-border-hover);
}
.img-score-bar {
  position: absolute;
  top: 0;
  left: 0;
  height: 3px;
  background: linear-gradient(90deg, var(--c-accent), var(--c-success));
  opacity: 0.8;
}
.img-thumb {
  width: 100%;
  height: 140px;
  object-fit: cover;
  cursor: pointer;
  transition: opacity 0.2s;
}
.img-thumb:hover { opacity: 0.85; }
.img-caption {
  padding: var(--sp-2) var(--sp-3);
  font-size: var(--fs-xs);
  color: var(--c-text-secondary);
  line-height: var(--lh-tight);
  border-top: 1px solid var(--c-border-subtle);
}
.img-meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--sp-2) var(--sp-3);
  font-size: 11px;
  background: rgba(255,255,255,0.02);
}
.img-source {
  color: var(--c-text-tertiary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
  margin-right: var(--sp-2);
}
.img-relevance {
  font-weight: 500;
  flex-shrink: 0;
}
.img-relevance.high { color: #4ade80; }
.img-relevance.medium { color: #fbbf24; }
.img-relevance.low { color: var(--c-text-tertiary); }

/* Image in markdown content - clickable */
.message-content :deep(img) {
  cursor: zoom-in;
  max-width: 100%;
  border-radius: var(--radius-sm);
  transition: opacity 0.2s;
}
.message-content :deep(img:hover) {
  opacity: 0.85;
}
.message-content :deep(img.inline-ref-img) {
  display: block;
  max-width: 480px;
  margin: var(--sp-3) auto;
  border: 1px solid var(--c-border);
  border-radius: var(--radius);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
}
/* Mermaid block styling */
.message-content :deep(.mermaid-block) {
  margin: var(--sp-3) 0;
  padding: var(--sp-4);
  background: rgba(255,255,255,0.02);
  border: 1px solid var(--c-border);
  border-radius: var(--radius);
  overflow-x: auto;
  text-align: center;
}
.message-content :deep(.mermaid-block svg) {
  max-width: 100%;
  height: auto;
}
.message-content :deep(.mermaid-loading) {
  color: var(--c-text-tertiary);
  font-size: var(--fs-xs);
  padding: var(--sp-4);
}
</style>

<style>
/* Lightbox - global scope (Teleport to body) */
.lightbox-overlay {
  position: fixed;
  inset: 0;
  z-index: 9999;
  background: rgba(0, 0, 0, 0.85);
  backdrop-filter: blur(8px);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: zoom-out;
  animation: lightbox-in 0.2s ease;
}
@keyframes lightbox-in {
  from { opacity: 0; }
  to { opacity: 1; }
}
.lightbox-img {
  max-width: 90vw;
  max-height: 90vh;
  object-fit: contain;
  border-radius: 8px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5);
  cursor: default;
}
.lightbox-close {
  position: absolute;
  top: 16px;
  right: 24px;
  background: rgba(255, 255, 255, 0.1);
  border: 1px solid rgba(255, 255, 255, 0.2);
  color: #fff;
  font-size: 28px;
  width: 40px;
  height: 40px;
  border-radius: 50%;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
  line-height: 1;
}
.lightbox-close:hover {
  background: rgba(255, 255, 255, 0.2);
  transform: scale(1.1);
}
</style>
