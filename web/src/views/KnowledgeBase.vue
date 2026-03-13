<template>
  <div class="h-full overflow-auto p-6">
    <h2 class="text-2xl font-bold mb-2">📂 知识库构建</h2>
    <p class="text-gray-400 mb-6">选择文件夹，批量摄取文档到知识库</p>

    <!-- Config -->
    <el-card shadow="never" class="mb-6">
      <el-form :inline="true">
        <el-form-item label="文件夹路径">
          <el-input v-model="folderPath" placeholder="D:\WorkSpace\知识库" style="width: 400px" :disabled="ingesting" />
        </el-form-item>
        <el-form-item label="集合">
          <el-input v-model="collection" style="width: 120px" :disabled="ingesting" />
        </el-form-item>
        <el-form-item>
          <el-button @click="scanFolder" :loading="scanning" :disabled="ingesting">🔍 扫描</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- Scanned files -->
    <el-card v-if="files.length" shadow="never" class="mb-6">
      <template #header>
        <div class="flex justify-between items-center">
          <span>📄 扫描到 {{ files.length }} 个文件</span>
          <div class="flex gap-2">
            <el-button v-if="!ingesting" type="primary" @click="startIngest">🚀 开始构建</el-button>
            <el-button v-if="ingesting" type="danger" @click="stopIngest">⏹️ 停止</el-button>
          </div>
        </div>
      </template>
      <el-table :data="files" max-height="300" size="small">
        <el-table-column prop="name" label="文件名" />
        <el-table-column label="大小" width="100">
          <template #default="{ row }">{{ (row.size / 1024).toFixed(1) }} KB</template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- Progress -->
    <el-card v-if="ingesting || logs.length" shadow="never">
      <template #header>进度</template>
      <el-progress v-if="ingesting" :percentage="progressPct" :text-inside="true" :stroke-width="20" class="mb-4" />
      <p v-if="progressText" class="text-sm text-gray-500 mb-4">{{ progressText }}</p>
      <div class="max-h-60 overflow-auto space-y-1">
        <p v-for="(log, i) in logs" :key="i" class="text-sm" :class="log.startsWith('❌') ? 'text-red-500' : log.startsWith('⏭') ? 'text-gray-400' : 'text-green-600'">
          {{ log }}
        </p>
      </div>
      <div v-if="!ingesting && logs.length" class="mt-4 flex gap-4">
        <el-tag type="success">成功: {{ resultCounts.success }}</el-tag>
        <el-tag type="danger">失败: {{ resultCounts.failed }}</el-tag>
        <el-tag type="info">跳过: {{ resultCounts.skipped }}</el-tag>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useSSE } from '@/composables/useSSE'
import api from '@/composables/useApi'

const folderPath = ref('')
const collection = ref('default')
const files = ref<any[]>([])
const scanning = ref(false)
const ingesting = ref(false)
const progressPct = ref(0)
const progressText = ref('')
const logs = ref<string[]>([])
const taskId = ref('')
const resultCounts = ref({ success: 0, failed: 0, skipped: 0 })

const { stream, abort } = useSSE()

async function scanFolder() {
  if (!folderPath.value.trim()) return ElMessage.warning('请输入文件夹路径')
  scanning.value = true
  try {
    const { data } = await api.post('/knowledge/scan', { folder_path: folderPath.value })
    if (data.ok) {
      files.value = data.data.files
      ElMessage.success(`扫描到 ${data.data.total} 个文件`)
    } else {
      ElMessage.error(data.message)
    }
  } catch { ElMessage.error('扫描失败') }
  finally { scanning.value = false }
}

async function startIngest() {
  ingesting.value = true
  logs.value = []
  progressPct.value = 0
  resultCounts.value = { success: 0, failed: 0, skipped: 0 }

  try {
    const { data } = await api.post('/knowledge/ingest', {
      folder_path: folderPath.value,
      collection: collection.value,
    })
    if (!data.ok) { ElMessage.error(data.message); ingesting.value = false; return }
    taskId.value = data.data.task_id

    await stream(
      `/api/knowledge/progress/${taskId.value}`,
      {},
      (event) => {
        if (event.type === 'progress') {
          progressPct.value = Math.round((event.current / event.total) * 100)
          progressText.value = `[${event.current}/${event.total}] ${event.file}`
        } else if (event.type === 'file_done') {
          if (event.status === 'success') logs.value.push(`✅ ${event.file} — ${event.chunks} 分块`)
          else if (event.status === 'skipped') logs.value.push(`⏭️ ${event.file} — 已跳过`)
          else logs.value.push(`❌ ${event.file} — ${event.error || '失败'}`)
        } else if (event.type === 'done') {
          resultCounts.value = { success: event.success || 0, failed: event.failed || 0, skipped: event.skipped || 0 }
          progressPct.value = 100
          ingesting.value = false
        } else if (event.type === 'stopped') {
          logs.value.push(`⏹️ 已停止 (${event.completed}/${event.total})`)
          ingesting.value = false
        }
      },
      () => { ingesting.value = false },
      (err) => { ElMessage.error(err.message); ingesting.value = false },
    )
  } catch { ElMessage.error('启动失败'); ingesting.value = false }
}

async function stopIngest() {
  if (taskId.value) {
    await api.post(`/knowledge/stop/${taskId.value}`)
    ElMessage.info('已发送停止信号')
  }
}
</script>
