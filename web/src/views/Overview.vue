<template>
  <div class="h-full overflow-auto p-6">
    <h2 class="text-2xl font-bold mb-2">📊 系统总览</h2>
    <p class="text-gray-400 mb-6">知识库数据统计概览</p>

    <el-row :gutter="16" class="mb-6" v-if="stats">
      <el-col :span="6">
        <el-card shadow="never">
          <el-statistic title="文档数" :value="stats.total_documents">
            <template #prefix><span class="text-lg">📄</span></template>
          </el-statistic>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never">
          <el-statistic title="分块数" :value="stats.total_chunks">
            <template #prefix><span class="text-lg">✂️</span></template>
          </el-statistic>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never">
          <el-statistic title="图片数" :value="stats.total_images">
            <template #prefix><span class="text-lg">🖼️</span></template>
          </el-statistic>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never">
          <el-statistic title="集合数" :value="stats.collections?.length || 0">
            <template #prefix><span class="text-lg">📁</span></template>
          </el-statistic>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="16" class="mb-6" v-if="stats">
      <el-col :span="8">
        <el-card shadow="never">
          <template #header>ChromaDB 存储</template>
          <p class="text-2xl font-bold">{{ stats.chroma_size }}</p>
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card shadow="never">
          <template #header>BM25 索引</template>
          <p class="text-2xl font-bold">{{ stats.bm25_size }}</p>
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card shadow="never">
          <template #header>图片存储</template>
          <p class="text-2xl font-bold">{{ stats.image_size }}</p>
        </el-card>
      </el-col>
    </el-row>

    <el-card shadow="never" v-if="stats">
      <template #header>集合列表</template>
      <el-tag v-for="c in stats.collections" :key="c" class="mr-2 mb-2" size="large">{{ c }}</el-tag>
    </el-card>

    <el-skeleton v-if="!stats" :rows="6" animated />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import api from '@/composables/useApi'

const stats = ref<any>(null)

onMounted(async () => {
  const { data } = await api.get('/system/stats')
  stats.value = data.data
})
</script>
