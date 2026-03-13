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
            <div v-else v-html="renderMd(msg.content)" class="message-content" />
          </div>
        </div>

        <!-- Streaming -->
        <div v-if="streaming" class="message assistant">
          <div class="message-bubble">
            <div v-html="renderMd(streamBuffer)" class="message-content" />
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
import { ref, nextTick, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { ChatDotRound, Promotion, VideoPause } from '@element-plus/icons-vue'
import { useSSE } from '@/composables/useSSE'
import { renderMarkdown } from '@/utils/markdown'
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
const messagesRef = ref<HTMLElement | null>(null)
const showSettings = ref(false)

const collection = ref('default')
const topK = ref(5)
const maxTokens = ref(4096)

const { stream, abort } = useSSE()

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

async function sendQuestion() {
  const q = question.value.trim()
  if (!q || streaming.value) return

  messages.value.push({ role: 'user', content: q })
  question.value = ''
  streaming.value = true
  streamBuffer.value = ''
  references.value = []
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
      } else if (event.type === 'done') {
        messages.value.push({ role: 'assistant', content: event.answer || streamBuffer.value })
        streamBuffer.value = ''
        streaming.value = false
        scrollToBottom()
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
    ElMessage.success('已清空')
  } catch {
    ElMessage.error('清空失败')
  }
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

onMounted(loadHistory)
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
  max-width: 720px;
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
  max-width: 520px;
}
.message.assistant .message-bubble {
  background: var(--glass-bg);
  border: 1px solid var(--c-border);
  border-radius: var(--radius) var(--radius) var(--radius) var(--sp-1);
  max-width: 640px;
  backdrop-filter: blur(var(--glass-blur));
  -webkit-backdrop-filter: blur(var(--glass-blur));
}
.message-bubble { padding: var(--sp-3) var(--sp-4); }
.message-text {
  font-size: var(--fs-sm);
  line-height: var(--lh-normal);
  white-space: pre-wrap;
}
.message-content {
  font-size: var(--fs-sm);
  line-height: 1.7;
}
.message-content :deep(p) { margin: 0 0 var(--sp-2); }
.message-content :deep(p:last-child) { margin: 0; }
.message-content :deep(pre) {
  background: rgba(255,255,255,0.04);
  border: 1px solid var(--c-border);
  padding: var(--sp-3) var(--sp-4);
  border-radius: var(--radius-sm);
  overflow-x: auto;
  font-size: var(--fs-xs);
  margin: var(--sp-2) 0;
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
  width: 100%;
  margin: var(--sp-2) 0;
  font-size: var(--fs-xs);
}
.message-content :deep(th),
.message-content :deep(td) {
  border: 1px solid var(--c-border);
  padding: var(--sp-2) var(--sp-3);
}
.message-content :deep(th) {
  background: rgba(255,255,255,0.04);
  font-weight: 500;
}
.message-content :deep(h1),
.message-content :deep(h2),
.message-content :deep(h3) {
  margin: var(--sp-4) 0 var(--sp-2);
  font-weight: 600;
  line-height: var(--lh-tight);
}
.message-content :deep(h1) { font-size: var(--fs-lg); }
.message-content :deep(h2) { font-size: var(--fs-base); }
.message-content :deep(h3) { font-size: var(--fs-sm); }
.message-content :deep(ul),
.message-content :deep(ol) {
  padding-left: var(--sp-5);
  margin: var(--sp-1) 0;
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
  max-width: 720px;
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
  max-width: 720px;
  margin: 0 auto;
  display: flex;
  gap: var(--sp-3);
  align-items: flex-end;
}
.chat-input { flex: 1; }
.input-actions { flex-shrink: 0; padding-bottom: 2px; }
.input-meta {
  max-width: 720px;
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
</style>
