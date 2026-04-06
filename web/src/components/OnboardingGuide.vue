<template>
  <Teleport to="body">
    <Transition name="onboard">
      <div v-if="visible" class="onboard-overlay" @click.self="maybeClose">
        <div class="onboard-card">
          <!-- Progress dots -->
          <div class="onboard-progress">
            <div
              v-for="i in totalSteps" :key="i"
              class="progress-dot"
              :class="{ active: i === currentStep, done: i < currentStep }"
            />
          </div>

          <!-- Step content -->
          <div class="onboard-body">
            <div class="step-icon">{{ currentStepData.icon }}</div>
            <h2 class="step-title">{{ currentStepData.title }}</h2>
            <p class="step-desc">{{ currentStepData.desc }}</p>

            <!-- Special content for step 1: API Key config -->
            <div v-if="currentStep === 1" class="step-action-hint">
              <div class="hint-box">
                <div class="hint-title">需要两个 API Key：</div>
                <div class="hint-item">
                  <span class="hint-label">① 模型 Key（LLM + 视觉）</span>
                  <span class="hint-url">https://coding.dashscope.aliyuncs.com/v1</span>
                </div>
                <div class="hint-item">
                  <span class="hint-label">② Embedding Key（打向量）</span>
                  <span class="hint-url">https://dashscope.aliyuncs.com/compatible-mode/v1</span>
                </div>
                <div class="hint-note">前往 <strong>百炼平台</strong> → API KEY 管理 → 新建 API KEY，分别申请两个 Key 填入系统配置。</div>
              </div>
            </div>

            <!-- Special: step 2 is optional -->
            <div v-if="currentStep === 2" class="step-optional-badge">
              <span>📁 可选步骤</span>
            </div>
          </div>

          <!-- Actions -->
          <div class="onboard-actions">
            <button
              v-if="currentStep > 1"
              class="btn-ghost"
              @click="currentStep--"
            >← 上一步</button>

            <div class="onboard-actions-right">
              <button
                v-if="currentStep < totalSteps"
                class="btn-ghost skip-btn"
                @click="skipToEnd"
              >跳过引导</button>

              <button
                v-if="currentStep === 1"
                class="btn-primary"
                @click="goToConfig"
              >前往配置页面 →</button>

              <button
                v-else-if="currentStep < totalSteps"
                class="btn-primary"
                @click="currentStep++"
              >下一步 →</button>

              <button
                v-else
                class="btn-primary"
                @click="finish"
              >开始使用 🚀</button>
            </div>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'

const STORAGE_KEY = 'jz_onboarding_done'
const router = useRouter()

const visible = ref(false)
const currentStep = ref(1)
const totalSteps = 5

const steps = [
  {
    icon: '🔑',
    title: '第一步：配置 API Key',
    desc: '本系统需要配置两个独立的 API Key，用于大模型对话和知识库向量化。请前往「系统配置」页面，分别填写「模型 Key」和「Embedding Key」并测试通过。',
  },
  {
    icon: '📚',
    title: '（可选）摄取知识库',
    desc: '前往「知识库构建」页面，上传 PDF、Word 等文档。系统会自动解析、切片并建立语义索引。有了知识库，后续的问答和标书助手能调用您私有的文档内容。',
  },
  {
    icon: '💬',
    title: '知识库智能问答',
    desc: '前往「知识库问答」页面，直接用自然语言提问。系统会在您的文档库中检索最相关的内容，结合大模型给出精准回答，并标注来源。',
  },
  {
    icon: '📄',
    title: '标书助手',
    desc: '前往「标书助手」，输入招标要求和条件，系统将自动从知识库中匹配您公司的资质文件，并协助智能生成响应性标书章节内容。',
  },
  {
    icon: '📊',
    title: '方案助手',
    desc: '前往「方案助手」，输入项目背景和需求，系统将结合您的知识库和模板，自动生成完整的技术方案文档，并支持分章节修改完善。',
  },
]

const currentStepData = computed(() => steps[currentStep.value - 1])

function maybeClose() {
  // Don't close on overlay click — user must actively complete or skip
}

function skipToEnd() {
  localStorage.setItem(STORAGE_KEY, '1')
  localStorage.removeItem('jz_onboarding_step')
  visible.value = false
}

function finish() {
  localStorage.setItem(STORAGE_KEY, '1')
  localStorage.removeItem('jz_onboarding_step')
  visible.value = false
}

function goToConfig() {
  // 导航到配置页，暴闭弹窗，记录进度为第 2 步
  currentStep.value = 2
  localStorage.setItem('jz_onboarding_step', '2')
  router.push('/config')
  visible.value = false
}

onMounted(() => {
  const done = localStorage.getItem(STORAGE_KEY)
  if (!done) {
    // 恢复上次关闭时保存的步骤
    const savedStep = Number(localStorage.getItem('jz_onboarding_step') || '1')
    currentStep.value = savedStep > 1 ? savedStep : 1
    visible.value = true
  }
})

// 外部可调用：重新弹出引导
defineExpose({ show: () => { currentStep.value = 1; localStorage.removeItem('jz_onboarding_step'); visible.value = true } })
</script>

<style scoped>
.onboard-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.75);
  backdrop-filter: blur(6px);
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--sp-4);
}

.onboard-card {
  background: var(--c-bg, #0e1117);
  border: 1px solid var(--c-border, rgba(255,255,255,0.08));
  border-radius: calc(var(--radius, 8px) * 2);
  padding: var(--sp-8, 32px);
  width: 100%;
  max-width: 520px;
  box-shadow: 0 24px 80px rgba(0, 0, 0, 0.6);
}

/* Progress dots */
.onboard-progress {
  display: flex;
  gap: 8px;
  justify-content: center;
  margin-bottom: var(--sp-8, 32px);
}

.progress-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: rgba(255,255,255,0.12);
  transition: all 0.3s ease;
}

.progress-dot.active {
  background: var(--c-accent, #e5e5e5);
  width: 24px;
  border-radius: 4px;
}

.progress-dot.done {
  background: rgba(34, 197, 94, 0.6);
}

/* Body */
.onboard-body {
  text-align: center;
  margin-bottom: var(--sp-8, 32px);
}

.step-icon {
  font-size: 40px;
  margin-bottom: var(--sp-4, 16px);
  line-height: 1;
}

.step-title {
  font-size: 20px;
  font-weight: 600;
  color: var(--c-text-primary, #f5f5f5);
  margin: 0 0 var(--sp-3, 12px);
  letter-spacing: -0.3px;
}

.step-desc {
  font-size: 14px;
  color: var(--c-text-secondary, rgba(255,255,255,0.6));
  line-height: 1.7;
  margin: 0;
}

/* Special hint content */
.step-action-hint {
  margin-top: var(--sp-5, 20px);
  text-align: left;
}

.hint-box {
  background: rgba(255,255,255,0.03);
  border: 1px solid var(--c-border, rgba(255,255,255,0.08));
  border-radius: var(--radius, 8px);
  padding: var(--sp-4, 16px);
  font-size: 12px;
}

.hint-title {
  font-weight: 600;
  color: var(--c-text-primary, #f5f5f5);
  margin-bottom: var(--sp-3, 12px);
}

.hint-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--sp-2, 8px) 0;
  border-bottom: 1px solid var(--c-border, rgba(255,255,255,0.05));
}

.hint-item:last-of-type {
  border-bottom: none;
}

.hint-label {
  color: var(--c-text-primary, #f5f5f5);
  font-weight: 500;
}

.hint-url {
  font-family: monospace;
  font-size: 10px;
  color: var(--c-text-tertiary, rgba(255,255,255,0.35));
}

.hint-note {
  margin-top: var(--sp-3, 12px);
  color: var(--c-text-tertiary, rgba(255,255,255,0.4));
  line-height: 1.6;
}

/* Optional badge */
.step-optional-badge {
  display: inline-block;
  margin-top: var(--sp-4, 16px);
  padding: 4px 12px;
  background: rgba(245, 158, 11, 0.12);
  border: 1px solid rgba(245, 158, 11, 0.3);
  border-radius: 20px;
  font-size: 12px;
  color: #fbbf24;
}

/* Actions */
.onboard-actions {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: var(--sp-3, 12px);
}

.onboard-actions-right {
  display: flex;
  gap: var(--sp-2, 8px);
  align-items: center;
  margin-left: auto;
}

.btn-ghost {
  background: transparent;
  border: 1px solid rgba(255,255,255,0.12);
  border-radius: 8px;
  color: rgba(255,255,255,0.5);
  font-size: 13px;
  padding: 0 16px;
  height: 38px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.btn-ghost:hover {
  border-color: rgba(255,255,255,0.25);
  color: rgba(255,255,255,0.8);
}

.skip-btn {
  font-size: 12px;
  padding: 0 12px;
}

.btn-primary {
  background: var(--c-accent, #e5e5e5);
  border: none;
  border-radius: 8px;
  color: #0a0a0a;
  font-size: 13px;
  font-weight: 500;
  padding: 0 20px;
  height: 38px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.btn-primary:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 16px rgba(255,255,255,0.2);
}

/* Transition */
.onboard-enter-active,
.onboard-leave-active {
  transition: opacity 0.3s ease;
}

.onboard-enter-active .onboard-card,
.onboard-leave-active .onboard-card {
  transition: transform 0.3s ease;
}

.onboard-enter-from,
.onboard-leave-to {
  opacity: 0;
}

.onboard-enter-from .onboard-card {
  transform: translateY(20px) scale(0.97);
}

.onboard-leave-to .onboard-card {
  transform: translateY(10px) scale(0.98);
}
</style>
