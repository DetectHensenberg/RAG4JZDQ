<template>
  <div class="bid-page">
    <!-- Top bar: title + requirement selector -->
    <div class="bid-header">
      <h2 class="bid-title">标书助手</h2>
      <el-select v-model="activeModule" class="module-select" size="default">
        <el-option
          v-for="m in modules"
          :key="m.key"
          :label="m.label"
          :value="m.key"
          :disabled="m.disabled"
        >
          <div class="module-option">
            <span class="module-option-label">{{ m.label }}</span>
            <el-tag v-if="m.disabled" size="small" type="info" class="module-tag">开发中</el-tag>
          </div>
        </el-option>
      </el-select>
    </div>

    <!-- Sub-view area -->
    <div class="bid-body">
      <BidAuthVerifier v-if="activeModule === 'auth-verify'" />
      <BidAchievementSearch v-else-if="activeModule === 'achievement'" />
      <BidDocumentWriter v-else-if="activeModule === 'document-writer'" />
      <BidReviewAssistant v-else-if="activeModule === 'review'" />
      <div v-else class="coming-soon">
        <el-icon :size="48" style="color:var(--c-text-tertiary)"><SetUp /></el-icon>
        <h3>{{ currentModuleLabel }} — 开发中</h3>
        <p>该功能模块正在开发中，敬请期待</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { SetUp } from '@element-plus/icons-vue'
import BidAuthVerifier from '@/components/bid/BidAuthVerifier.vue'
import BidAchievementSearch from '@/components/bid/BidAchievementSearch.vue'
import BidDocumentWriter from '@/components/bid/BidDocumentWriter.vue'
import BidReviewAssistant from '@/components/bid/BidReviewAssistant.vue'

interface BidModule {
  key: string
  label: string
  disabled?: boolean
}

const modules: BidModule[] = [
  { key: 'auth-verify', label: '需求1：产品技术资料真伪性辨别助手' },
  { key: 'achievement', label: '需求2：业绩库智能检索助手' },
  { key: 'document-writer', label: '需求3：标书商务文件编写助手' },
  { key: 'review',      label: '需求4：标书智能化审查助手' },
]

const activeModule = ref('auth-verify')

const currentModuleLabel = computed(() =>
  modules.find(m => m.key === activeModule.value)?.label || ''
)
</script>

<style scoped>
.bid-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--c-bg);
}

/* Header */
.bid-header {
  display: flex;
  align-items: center;
  gap: var(--sp-4);
  padding: var(--sp-4) var(--page-padding);
  border-bottom: 1px solid var(--c-border);
  background: var(--c-bg-elevated);
  flex-shrink: 0;
}
.bid-title {
  font-size: var(--fs-lg);
  font-weight: 700;
  color: var(--c-text-primary);
  margin: 0;
  white-space: nowrap;
}
.module-select {
  min-width: 320px;
}

/* Module option in dropdown */
.module-option {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--sp-3);
  width: 100%;
}
.module-option-label {
  flex: 1;
}
.module-tag {
  flex-shrink: 0;
}

/* Body */
.bid-body {
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

/* Coming soon placeholder */
.coming-soon {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  gap: var(--sp-3);
}
.coming-soon h3 {
  font-size: var(--fs-base);
  font-weight: 600;
  color: var(--c-text-secondary);
  margin: 0;
}
.coming-soon p {
  font-size: var(--fs-sm);
  color: var(--c-text-tertiary);
  margin: 0;
}
</style>
