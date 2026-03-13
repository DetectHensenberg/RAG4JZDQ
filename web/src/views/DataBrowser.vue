<template>
  <div class="h-full overflow-auto p-6">
    <h2 class="text-2xl font-bold mb-2">🔍 数据浏览</h2>
    <p class="text-gray-400 mb-6">查看已摄取的文档和分块内容</p>

    <el-card shadow="never" class="mb-6">
      <el-form :inline="true">
        <el-form-item label="集合">
          <el-select v-model="collection" @change="loadDocuments">
            <el-option v-for="c in collections" :key="c.name" :label="`${c.name} (${c.count})`" :value="c.name" />
          </el-select>
        </el-form-item>
      </el-form>
    </el-card>

    <el-table :data="documents" v-loading="loading" stripe>
      <el-table-column type="expand">
        <template #default="{ row }">
          <div class="p-4">
            <el-button size="small" @click="loadChunks(row.file_hash)" :loading="chunksLoading">查看分块</el-button>
            <div v-if="chunks.length && currentHash === row.file_hash" class="mt-4 space-y-2">
              <div v-for="(chunk, i) in chunks" :key="i" class="p-3 bg-gray-50 rounded text-sm">
                <span class="text-gray-400 text-xs">{{ chunk.id }}</span>
                <p class="mt-1 whitespace-pre-wrap">{{ chunk.text }}</p>
              </div>
            </div>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="文件路径" prop="source_path" show-overflow-tooltip />
      <el-table-column label="状态" prop="status" width="80" />
      <el-table-column label="时间" prop="created_at" width="180" />
    </el-table>

    <el-pagination v-if="total > pageSize" class="mt-4" :current-page="page" :page-size="pageSize" :total="total"
      @current-change="(p: number) => { page = p; loadDocuments() }" layout="prev, pager, next" />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import api from '@/composables/useApi'

const collections = ref<any[]>([])
const collection = ref('default')
const documents = ref<any[]>([])
const loading = ref(false)
const page = ref(1)
const pageSize = 20
const total = ref(0)
const chunks = ref<any[]>([])
const chunksLoading = ref(false)
const currentHash = ref('')

async function loadCollections() {
  const { data } = await api.get('/data/collections')
  if (data.ok) collections.value = data.data
}

async function loadDocuments() {
  loading.value = true
  try {
    const { data } = await api.get(`/data/documents?collection=${collection.value}&page=${page.value}&size=${pageSize}`)
    if (data.ok) {
      documents.value = data.data.items
      total.value = data.data.total
    }
  } finally { loading.value = false }
}

async function loadChunks(fileHash: string) {
  chunksLoading.value = true
  currentHash.value = fileHash
  try {
    const { data } = await api.get(`/data/chunks/${fileHash}`)
    if (data.ok) chunks.value = data.data
  } finally { chunksLoading.value = false }
}

onMounted(async () => {
  await loadCollections()
  await loadDocuments()
})
</script>
