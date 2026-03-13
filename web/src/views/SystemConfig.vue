<template>
  <div class="h-full overflow-auto p-6">
    <h2 class="text-2xl font-bold mb-2">⚙️ 系统配置</h2>
    <p class="text-gray-400 mb-6">管理 API Key、模型配置和系统参数</p>

    <el-form v-if="config" label-width="120px" class="max-w-3xl">
      <!-- API Key -->
      <el-card shadow="never" class="mb-6">
        <template #header><span class="font-bold">🔑 API Key</span></template>
        <el-alert v-if="apiKeyMasked" :title="`当前: ${apiKeyMasked}`" type="success" :closable="false" class="mb-4" />
        <el-alert v-else title="未配置 API Key" type="warning" :closable="false" class="mb-4" />
        <el-form-item label="API Key">
          <el-input v-model="newApiKey" type="password" placeholder="输入新 Key（留空保持不变）" show-password />
        </el-form-item>
        <el-form-item>
          <el-button @click="testConnection" :loading="testing">🔄 测试连接</el-button>
          <span v-if="testResult" :class="testResult.ok ? 'text-green-600' : 'text-red-500'" class="ml-3">
            {{ testResult.message }}
          </span>
        </el-form-item>
      </el-card>

      <!-- LLM -->
      <el-card shadow="never" class="mb-6">
        <template #header><span class="font-bold">🤖 LLM 配置</span></template>
        <el-form-item label="Provider">
          <el-select v-model="llmPreset" @change="onLlmPresetChange" class="w-full">
            <el-option v-for="p in llmPresets" :key="p.label" :label="p.label" :value="p.label" />
          </el-select>
        </el-form-item>
        <el-form-item label="模型">
          <el-select v-model="config.llm.model" filterable allow-create class="w-full">
            <el-option v-for="m in currentLlmModels" :key="m" :label="m" :value="m" />
          </el-select>
        </el-form-item>
        <el-form-item label="Base URL">
          <el-input v-model="config.llm.base_url" />
        </el-form-item>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="Temperature">
              <el-slider v-model="config.llm.temperature" :min="0" :max="2" :step="0.1" show-input />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="Max Tokens">
              <el-input-number v-model="config.llm.max_tokens" :min="256" :max="32768" :step="256" />
            </el-form-item>
          </el-col>
        </el-row>
      </el-card>

      <!-- Embedding -->
      <el-card shadow="never" class="mb-6">
        <template #header><span class="font-bold">📐 Embedding 配置</span></template>
        <el-form-item label="Provider">
          <el-select v-model="embPreset" @change="onEmbPresetChange" class="w-full">
            <el-option v-for="p in embPresets" :key="p.label" :label="p.label" :value="p.label" />
          </el-select>
        </el-form-item>
        <el-form-item label="模型">
          <el-select v-model="config.embedding.model" filterable allow-create class="w-full">
            <el-option v-for="m in currentEmbModels" :key="m" :label="m" :value="m" />
          </el-select>
        </el-form-item>
        <el-form-item label="Base URL">
          <el-input v-model="config.embedding.base_url" />
        </el-form-item>
        <el-form-item label="向量维度">
          <el-input-number v-model="config.embedding.dimensions" :min="128" :max="4096" :step="128" />
        </el-form-item>
      </el-card>

      <!-- Retrieval -->
      <el-card shadow="never" class="mb-6">
        <template #header><span class="font-bold">🔍 检索配置</span></template>
        <el-row :gutter="16">
          <el-col :span="8">
            <el-form-item label="Dense K">
              <el-input-number v-model="config.retrieval.dense_top_k" :min="1" :max="100" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="Sparse K">
              <el-input-number v-model="config.retrieval.sparse_top_k" :min="1" :max="100" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="Fusion K">
              <el-input-number v-model="config.retrieval.fusion_top_k" :min="1" :max="50" />
            </el-form-item>
          </el-col>
        </el-row>
      </el-card>

      <!-- Ingestion -->
      <el-card shadow="never" class="mb-6">
        <template #header><span class="font-bold">📥 摄取配置</span></template>
        <el-row :gutter="16">
          <el-col :span="8">
            <el-form-item label="分块大小">
              <el-input-number v-model="config.ingestion.chunk_size" :min="200" :max="5000" :step="100" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="分块重叠">
              <el-input-number v-model="config.ingestion.chunk_overlap" :min="0" :max="1000" :step="50" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="LLM精炼">
              <el-switch v-model="useLlmRefine" />
            </el-form-item>
          </el-col>
        </el-row>
      </el-card>

      <!-- Actions -->
      <div class="flex gap-4">
        <el-button type="primary" size="large" @click="saveConfig" :loading="saving">💾 保存配置</el-button>
        <el-button size="large" @click="resetConfig">🔄 重置为默认</el-button>
      </div>
    </el-form>

    <el-skeleton v-else :rows="10" animated />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import api from '@/composables/useApi'

const config = ref<any>(null)
const apiKeyMasked = ref('')
const newApiKey = ref('')
const testing = ref(false)
const saving = ref(false)
const testResult = ref<{ ok: boolean; message: string } | null>(null)
const useLlmRefine = ref(false)

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
    // Load example config as reset target
    await api.put('/config', { config: {} })
    ElMessage.success('已重置')
    await loadConfig()
  } catch {
    ElMessage.error('重置失败')
  }
}

onMounted(loadConfig)
</script>
