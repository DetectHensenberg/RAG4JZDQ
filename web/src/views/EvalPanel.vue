<template>
  <div class="h-full overflow-auto p-6">
    <h2 class="text-2xl font-bold mb-2">📏 评估面板</h2>
    <p class="text-gray-400 mb-6">输入测试查询，评估检索质量</p>

    <el-card shadow="never" class="mb-6">
      <el-form label-position="top">
        <el-form-item label="测试查询（每行一个）">
          <el-input v-model="queriesText" type="textarea" :rows="5" placeholder="输入测试问题，每行一个" />
        </el-form-item>
        <el-form-item label="集合">
          <el-input v-model="collection" style="width: 200px" />
        </el-form-item>
        <el-button type="primary" @click="runEval" :loading="running">🚀 运行评估</el-button>
      </el-form>
    </el-card>

    <el-card v-if="results.length" shadow="never">
      <template #header>评估结果 ({{ results.length }} 条)</template>
      <el-table :data="results" stripe>
        <el-table-column label="查询" prop="query" show-overflow-tooltip />
        <el-table-column label="命中数" prop="hits" width="80" />
        <el-table-column label="Top 来源">
          <template #default="{ row }">
            <span v-for="(s, i) in row.top_sources" :key="i" class="text-xs mr-2">
              {{ s.split(/[/\\]/).pop() }}
              <span class="text-gray-400">({{ row.top_scores[i] }})</span>
            </span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import api from '@/composables/useApi'

const queriesText = ref('')
const collection = ref('default')
const running = ref(false)
const results = ref<any[]>([])

async function runEval() {
  const queries = queriesText.value.split('\n').map(q => q.trim()).filter(Boolean)
  if (!queries.length) return ElMessage.warning('请输入至少一个查询')
  running.value = true
  results.value = []
  try {
    const { data } = await api.post('/eval/run', { queries, collection: collection.value })
    if (data.ok) {
      results.value = data.data.results
      ElMessage.success(`评估完成: ${data.data.total_queries} 条`)
    } else {
      ElMessage.error(data.message)
    }
  } catch { ElMessage.error('评估失败') }
  finally { running.value = false }
}
</script>
