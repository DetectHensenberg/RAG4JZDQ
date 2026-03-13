<template>
  <div class="h-full overflow-auto p-6">
    <h2 class="text-2xl font-bold mb-2">📥 摄取管理</h2>
    <p class="text-gray-400 mb-6">上传单个文件摄取，或管理已有文档</p>

    <!-- Upload -->
    <el-card shadow="never" class="mb-6">
      <template #header><span class="font-bold">上传文件</span></template>
      <el-form :inline="true">
        <el-form-item label="集合">
          <el-input v-model="collection" style="width: 120px" />
        </el-form-item>
      </el-form>
      <el-upload
        :action="`/api/ingest/upload`"
        :data="{ collection }"
        :on-success="onUploadSuccess"
        :on-error="onUploadError"
        :before-upload="() => { uploading = true; return true }"
        accept=".pdf,.pptx,.docx,.md,.txt"
        :show-file-list="true"
        drag
      >
        <el-icon class="text-4xl text-gray-400 mb-2"><Upload /></el-icon>
        <div class="text-gray-500">拖拽文件到此处，或点击上传</div>
        <div class="text-gray-400 text-xs mt-1">支持 PDF / PPTX / DOCX / MD / TXT</div>
      </el-upload>
      <div v-if="uploadResult" class="mt-4">
        <el-alert :type="uploadResult.ok ? 'success' : 'error'" :title="uploadResult.message" :closable="false" />
      </div>
    </el-card>

    <!-- Document list -->
    <el-card shadow="never">
      <template #header>
        <div class="flex justify-between items-center">
          <span class="font-bold">已摄取文档</span>
          <el-button size="small" @click="loadDocuments" :loading="loading">刷新</el-button>
        </div>
      </template>
      <el-table :data="documents" v-loading="loading" stripe size="small">
        <el-table-column label="文件路径" prop="source_path" show-overflow-tooltip />
        <el-table-column label="时间" prop="created_at" width="180" />
        <el-table-column label="操作" width="80">
          <template #default="{ row }">
            <el-popconfirm title="确定删除？" @confirm="deleteDoc(row)">
              <template #reference>
                <el-button type="danger" link size="small">删除</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Upload } from '@element-plus/icons-vue'
import api from '@/composables/useApi'

const collection = ref('default')
const uploading = ref(false)
const uploadResult = ref<{ ok: boolean; message: string } | null>(null)
const documents = ref<any[]>([])
const loading = ref(false)

function onUploadSuccess(response: any) {
  uploading.value = false
  if (response.ok) {
    const d = response.data
    uploadResult.value = { ok: true, message: d.skipped ? '文件已存在，已跳过' : `摄取成功: ${d.chunks} 分块` }
    loadDocuments()
  } else {
    uploadResult.value = { ok: false, message: response.message || '摄取失败' }
  }
}

function onUploadError() {
  uploading.value = false
  uploadResult.value = { ok: false, message: '上传失败' }
}

async function loadDocuments() {
  loading.value = true
  try {
    const { data } = await api.get(`/data/documents?collection=${collection.value}&size=100`)
    if (data.ok) documents.value = data.data.items
  } finally { loading.value = false }
}

async function deleteDoc(row: any) {
  try {
    const { data } = await api.delete('/ingest/document', {
      data: { source_path: row.source_path, collection: collection.value, source_hash: row.file_hash },
    })
    if (data.ok) {
      ElMessage.success('已删除')
      loadDocuments()
    } else {
      ElMessage.error(data.message)
    }
  } catch { ElMessage.error('删除失败') }
}

onMounted(loadDocuments)
</script>
