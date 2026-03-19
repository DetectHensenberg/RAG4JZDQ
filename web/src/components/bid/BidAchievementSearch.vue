<template>
  <div class="achievement-page">
    <!-- Tab bar -->
    <div class="tab-bar">
      <button class="tab-btn" :class="{ active: tab === 'manage' }" @click="tab = 'manage'">
        <el-icon :size="14"><List /></el-icon><span>业绩管理</span>
      </button>
      <button class="tab-btn" :class="{ active: tab === 'search' }" @click="tab = 'search'">
        <el-icon :size="14"><Search /></el-icon><span>智能检索</span>
      </button>
    </div>

    <!-- ══════════ Tab 1: 业绩管理 ══════════ -->
    <div v-show="tab === 'manage'" class="tab-body manage-tab">
      <!-- Toolbar -->
      <div class="toolbar">
        <div class="filter-row">
          <el-input v-model="filters.keyword" placeholder="搜索项目名称/内容" :prefix-icon="Search" clearable size="default" class="filter-input" @keyup.enter="loadList" />
          <el-date-picker v-model="filterDateRange" type="daterange" range-separator="至" start-placeholder="签订起始" end-placeholder="签订截止" value-format="YYYY-MM-DD" size="default" class="filter-date" clearable />
          <el-input v-model.number="filters.min_amount" placeholder="最低金额(万)" size="default" class="filter-amount" clearable type="number" />
          <el-input v-model.number="filters.max_amount" placeholder="最高金额(万)" size="default" class="filter-amount" clearable type="number" />
          <el-button type="primary" size="default" @click="loadList">筛选</el-button>
        </div>
        <div class="action-row">
          <el-button type="primary" @click="openCreateDialog">新增业绩</el-button>
          <el-dropdown trigger="click" @command="handleImport">
            <el-button>批量导入 <el-icon class="el-icon--right"><ArrowDown /></el-icon></el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="excel">Excel / CSV 导入</el-dropdown-item>
                <el-dropdown-item command="pdf">合同 PDF 智能提取</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
          <input ref="importFileRef" type="file" style="display:none" @change="handleImportFile" />
        </div>
      </div>

      <!-- Table -->
      <el-table :data="tableData" stripe size="default" class="data-table" @sort-change="handleSortChange" v-loading="tableLoading">
        <el-table-column prop="project_name" label="项目名称" min-width="200" sortable="custom" show-overflow-tooltip />
        <el-table-column prop="amount" label="金额(万)" width="110" sortable="custom" align="right">
          <template #default="{ row }">{{ row.amount != null ? row.amount.toLocaleString() : '-' }}</template>
        </el-table-column>
        <el-table-column prop="sign_date" label="签订时间" width="120" sortable="custom" />
        <el-table-column prop="acceptance_date" label="验收时间" width="120" />
        <el-table-column prop="client_contact" label="联系人" width="100" />
        <el-table-column prop="tags" label="标签" width="160">
          <template #default="{ row }">
            <el-tag v-for="t in (row.tags || [])" :key="t" size="small" class="tag-item">{{ t }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="attachments" label="附件" width="70" align="center">
          <template #default="{ row }">
            <span v-if="row.attachments?.length">{{ row.attachments.length }}</span>
            <span v-else class="text-muted">-</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="openEditDialog(row)">编辑</el-button>
            <el-button link type="primary" size="small" @click="openAttDialog(row)">附件</el-button>
            <el-popconfirm title="确定删除此业绩记录？" @confirm="deleteRow(row.id)">
              <template #reference>
                <el-button link type="danger" size="small">删除</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>

      <!-- Pagination -->
      <div class="pagination-row">
        <el-pagination v-model:current-page="filters.page" v-model:page-size="filters.page_size" :total="totalCount" :page-sizes="[10, 20, 50]" layout="total, sizes, prev, pager, next" @size-change="loadList" @current-change="loadList" />
      </div>
    </div>

    <!-- ══════════ Tab 2: 智能检索 ══════════ -->
    <div v-show="tab === 'search'" class="tab-body search-tab">
      <div ref="searchMsgRef" class="search-messages">
        <div v-if="!searchMessages.length" class="empty-state">
          <el-icon :size="32" style="color:var(--c-text-tertiary)"><Search /></el-icon>
          <h3>智能业绩检索</h3>
          <p>用自然语言描述需求，如"近三年500万以上的智慧城市项目"</p>
        </div>
        <div class="messages-list">
          <div v-for="(msg, i) in searchMessages" :key="i" class="message" :class="msg.role">
            <div class="message-bubble">
              <div v-if="msg.role === 'user'" class="message-text">{{ msg.content }}</div>
              <template v-else-if="msg.type === 'results'">
                <div class="message-content"><p>{{ msg.content }}</p></div>
                <div class="result-cards">
                  <div v-for="(r, j) in msg.results" :key="j" class="result-card">
                    <div class="rc-header">
                      <span class="rc-name">{{ r.project_name }}</span>
                      <span class="rc-score" v-if="r.score">{{ (r.score * 100).toFixed(0) }}%</span>
                    </div>
                    <div class="rc-meta">
                      <span v-if="r.amount != null">{{ r.amount }}万</span>
                      <span v-if="r.sign_date">签订: {{ r.sign_date }}</span>
                      <span v-if="r.client_contact">{{ r.client_contact }}</span>
                    </div>
                    <div class="rc-content" v-if="r.project_content">{{ r.project_content.slice(0, 150) }}...</div>
                    <div class="rc-tags" v-if="r.tags?.length">
                      <el-tag v-for="t in r.tags" :key="t" size="small">{{ t }}</el-tag>
                    </div>
                    <div class="rc-actions">
                      <el-button link size="small" type="primary" @click="copySummary(r)">复制摘要</el-button>
                      <el-button link size="small" type="primary" v-if="r.attachments?.length" @click="openAttDialog(r)">附件({{ r.attachments.length }})</el-button>
                    </div>
                  </div>
                </div>
              </template>
              <template v-else>
                <div class="message-content"><p>{{ msg.content }}</p></div>
              </template>
            </div>
          </div>
        </div>
      </div>
      <div class="search-input-area">
        <div class="search-input-container">
          <el-input v-model="searchQuery" type="textarea" :autosize="{ minRows: 1, maxRows: 3 }" placeholder="输入业绩检索需求，如：近三年500万以上的安防项目" @keydown.enter.exact.prevent="doSearch" :disabled="searchLoading" />
          <el-button type="primary" circle :loading="searchLoading" @click="doSearch" :disabled="!searchQuery.trim()">
            <el-icon><Promotion /></el-icon>
          </el-button>
        </div>
      </div>
    </div>

    <!-- ══════════ 新增/编辑弹窗 ══════════ -->
    <el-dialog v-model="dialogVisible" :title="editingId ? '编辑业绩' : '新增业绩'" width="600px" destroy-on-close>
      <el-form :model="form" label-width="100px" label-position="top">
        <el-form-item label="项目名称" required>
          <el-input v-model="form.project_name" placeholder="项目名称" />
        </el-form-item>
        <el-form-item label="项目内容">
          <el-input v-model="form.project_content" type="textarea" :rows="3" placeholder="项目描述" />
        </el-form-item>
        <el-row :gutter="16">
          <el-col :span="8">
            <el-form-item label="合同金额(万)">
              <el-input v-model.number="form.amount" type="number" placeholder="金额" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="签订时间">
              <el-date-picker v-model="form.sign_date" type="date" value-format="YYYY-MM-DD" placeholder="选择日期" style="width:100%" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="验收时间">
              <el-date-picker v-model="form.acceptance_date" type="date" value-format="YYYY-MM-DD" placeholder="选择日期" style="width:100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="甲方联系人">
              <el-input v-model="form.client_contact" placeholder="联系人" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="联系方式">
              <el-input v-model="form.client_phone" placeholder="电话" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="标签">
          <el-select v-model="form.tags" multiple filterable allow-create default-first-option placeholder="输入后回车添加" style="width:100%">
            <el-option v-for="t in commonTags" :key="t" :label="t" :value="t" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="saveRecord" :loading="saving">{{ editingId ? '保存' : '创建' }}</el-button>
      </template>
    </el-dialog>

    <!-- ══════════ 附件弹窗 ══════════ -->
    <el-dialog v-model="attDialogVisible" title="附件管理" width="500px" destroy-on-close>
      <div v-if="attRecordId">
        <div class="att-upload">
          <el-upload :action="`/api/bid-achievement/${attRecordId}/attachments`" :headers="{ 'X-API-Key': 'dev' }" :on-success="onAttUploadSuccess" :on-error="onAttUploadError" :show-file-list="false">
            <el-button type="primary" size="small">上传附件</el-button>
          </el-upload>
        </div>
        <div v-if="attList.length" class="att-list">
          <div v-for="a in attList" :key="a.filename" class="att-item">
            <span class="att-name">{{ a.filename }}</span>
            <span class="att-size">{{ (a.size / 1024).toFixed(1) }} KB</span>
            <div class="att-item-actions">
              <el-button link size="small" type="primary" @click="downloadAtt(a.filename)">下载</el-button>
              <el-popconfirm title="删除此附件？" @confirm="deleteAtt(a.filename)">
                <template #reference>
                  <el-button link size="small" type="danger">删除</el-button>
                </template>
              </el-popconfirm>
            </div>
          </div>
        </div>
        <div v-else class="att-empty">暂无附件</div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, nextTick, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { List, Search, ArrowDown, Promotion } from '@element-plus/icons-vue'
import api from '@/composables/useApi'

// ── Types ───────────────────────────────────────────────────────

interface SearchMsg {
  role: 'user' | 'assistant'
  type: string
  content: string
  results?: any[]
}

// ── Common state ────────────────────────────────────────────────

const tab = ref<'manage' | 'search'>('manage')
const commonTags = ['智慧城市', '安防', '信息化', '集成', '软件开发', '运维', '网络', '数据中心']

// ── Tab 1: Manage state ─────────────────────────────────────────

const tableData = ref<any[]>([])
const tableLoading = ref(false)
const totalCount = ref(0)
const filterDateRange = ref<[string, string] | null>(null)

const filters = reactive({
  keyword: '',
  min_amount: null as number | null,
  max_amount: null as number | null,
  start_date: '',
  end_date: '',
  tags: [] as string[],
  page: 1,
  page_size: 20,
  sort_by: 'updated_at',
  sort_order: 'desc',
})

const dialogVisible = ref(false)
const editingId = ref<number | null>(null)
const saving = ref(false)
const form = reactive({
  project_name: '',
  project_content: '',
  amount: null as number | null,
  sign_date: '',
  acceptance_date: '',
  client_contact: '',
  client_phone: '',
  tags: [] as string[],
})

// Attachment dialog
const attDialogVisible = ref(false)
const attRecordId = ref<number | null>(null)
const attList = ref<{ filename: string; size: number }[]>([])

// Import
const importFileRef = ref<HTMLInputElement | null>(null)
const importMode = ref<'excel' | 'pdf'>('excel')

// ── Tab 2: Search state ─────────────────────────────────────────

const searchMessages = ref<SearchMsg[]>([])
const searchQuery = ref('')
const searchLoading = ref(false)
const searchMsgRef = ref<HTMLElement | null>(null)

// ── Tab 1: Methods ──────────────────────────────────────────────

async function loadList() {
  if (filterDateRange.value) {
    filters.start_date = filterDateRange.value[0]
    filters.end_date = filterDateRange.value[1]
  } else {
    filters.start_date = ''
    filters.end_date = ''
  }

  tableLoading.value = true
  try {
    const { data } = await api.post('/bid-achievement/list', { ...filters })
    if (data.ok) {
      tableData.value = data.data || []
      totalCount.value = data.total || 0
    } else {
      ElMessage.error(data.message || '加载失败')
    }
  } catch (e: any) {
    ElMessage.error(`加载失败: ${e.message}`)
  } finally {
    tableLoading.value = false
  }
}

function handleSortChange({ prop, order }: any) {
  if (prop && order) {
    filters.sort_by = prop
    filters.sort_order = order === 'ascending' ? 'asc' : 'desc'
  } else {
    filters.sort_by = 'updated_at'
    filters.sort_order = 'desc'
  }
  loadList()
}

function resetForm() {
  form.project_name = ''
  form.project_content = ''
  form.amount = null
  form.sign_date = ''
  form.acceptance_date = ''
  form.client_contact = ''
  form.client_phone = ''
  form.tags = []
}

function openCreateDialog() {
  editingId.value = null
  resetForm()
  dialogVisible.value = true
}

function openEditDialog(row: any) {
  editingId.value = row.id
  form.project_name = row.project_name || ''
  form.project_content = row.project_content || ''
  form.amount = row.amount
  form.sign_date = row.sign_date || ''
  form.acceptance_date = row.acceptance_date || ''
  form.client_contact = row.client_contact || ''
  form.client_phone = row.client_phone || ''
  form.tags = [...(row.tags || [])]
  dialogVisible.value = true
}

async function saveRecord() {
  if (!form.project_name.trim()) {
    ElMessage.warning('项目名称不能为空')
    return
  }
  saving.value = true
  try {
    if (editingId.value) {
      const { data } = await api.put(`/bid-achievement/${editingId.value}`, { ...form })
      if (data.ok) {
        ElMessage.success('更新成功')
        dialogVisible.value = false
        loadList()
      } else {
        ElMessage.error(data.message || '更新失败')
      }
    } else {
      const { data } = await api.post('/bid-achievement/create', { ...form })
      if (data.ok) {
        ElMessage.success('创建成功')
        dialogVisible.value = false
        loadList()
      } else {
        ElMessage.error(data.message || '创建失败')
      }
    }
  } catch (e: any) {
    ElMessage.error(e.message)
  } finally {
    saving.value = false
  }
}

async function deleteRow(id: number) {
  try {
    const { data } = await api.delete(`/bid-achievement/${id}`)
    if (data.ok) {
      ElMessage.success('已删除')
      loadList()
    } else {
      ElMessage.error(data.message || '删除失败')
    }
  } catch (e: any) {
    ElMessage.error(e.message)
  }
}

// ── Import ──────────────────────────────────────────────────────

function handleImport(cmd: string) {
  importMode.value = cmd as 'excel' | 'pdf'
  if (importFileRef.value) {
    importFileRef.value.accept = cmd === 'pdf' ? '.pdf' : '.csv,.xlsx,.xls'
    importFileRef.value.value = ''
    importFileRef.value.click()
  }
}

async function handleImportFile(e: Event) {
  const input = e.target as HTMLInputElement
  if (!input.files?.length) return
  const file = input.files[0]
  const fd = new FormData()
  fd.append('file', file)

  const endpoint = importMode.value === 'pdf' ? '/bid-achievement/import-pdf' : '/bid-achievement/import-excel'

  try {
    const { data } = await api.post(endpoint, fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 120000,
    })
    if (data.ok) {
      ElMessage.success(data.message || '导入成功')
      loadList()
    } else {
      ElMessage.error(data.message || '导入失败')
    }
  } catch (e: any) {
    ElMessage.error(`导入失败: ${e.message}`)
  }
}

// ── Attachments ─────────────────────────────────────────────────

async function openAttDialog(row: any) {
  attRecordId.value = row.id
  attDialogVisible.value = true
  await loadAttachments()
}

async function loadAttachments() {
  if (!attRecordId.value) return
  try {
    const { data } = await api.get(`/bid-achievement/${attRecordId.value}/attachments`)
    attList.value = data.ok ? (data.data || []) : []
  } catch {
    attList.value = []
  }
}

function onAttUploadSuccess() {
  ElMessage.success('附件上传成功')
  loadAttachments()
  loadList()
}

function onAttUploadError() {
  ElMessage.error('附件上传失败')
}

function downloadAtt(filename: string) {
  window.open(`/api/bid-achievement/${attRecordId.value}/attachments/${encodeURIComponent(filename)}`, '_blank')
}

async function deleteAtt(filename: string) {
  try {
    const { data } = await api.delete(`/bid-achievement/${attRecordId.value}/attachments/${encodeURIComponent(filename)}`)
    if (data.ok) {
      ElMessage.success('附件已删除')
      loadAttachments()
      loadList()
    } else {
      ElMessage.error(data.message || '删除失败')
    }
  } catch (e: any) {
    ElMessage.error(e.message)
  }
}

// ── Tab 2: Search methods ───────────────────────────────────────

function scrollSearchBottom() {
  nextTick(() => {
    if (searchMsgRef.value) {
      searchMsgRef.value.scrollTop = searchMsgRef.value.scrollHeight
    }
  })
}

async function doSearch() {
  const q = searchQuery.value.trim()
  if (!q || searchLoading.value) return

  searchMessages.value.push({ role: 'user', type: 'text', content: q })
  searchQuery.value = ''
  searchLoading.value = true
  scrollSearchBottom()

  try {
    const { data } = await api.post('/bid-achievement/search', { query: q, top_k: 10 })
    if (data.ok && data.data?.length) {
      searchMessages.value.push({
        role: 'assistant',
        type: 'results',
        content: `找到 ${data.data.length} 条匹配业绩：`,
        results: data.data,
      })
    } else {
      searchMessages.value.push({
        role: 'assistant',
        type: 'text',
        content: data.message || '未找到匹配的业绩记录，请尝试调整关键词。',
      })
    }
  } catch (e: any) {
    searchMessages.value.push({
      role: 'assistant',
      type: 'text',
      content: `检索失败: ${e.message}`,
    })
  } finally {
    searchLoading.value = false
    scrollSearchBottom()
  }
}

function copySummary(r: any) {
  const text = [
    `项目名称：${r.project_name}`,
    r.project_content ? `项目内容：${r.project_content}` : '',
    r.amount != null ? `合同金额：${r.amount}万元` : '',
    r.sign_date ? `签订时间：${r.sign_date}` : '',
    r.acceptance_date ? `验收时间：${r.acceptance_date}` : '',
    r.client_contact ? `甲方联系人：${r.client_contact}` : '',
    r.client_phone ? `联系方式：${r.client_phone}` : '',
  ].filter(Boolean).join('\n')

  navigator.clipboard.writeText(text).then(() => {
    ElMessage.success('已复制摘要')
  }).catch(() => ElMessage.error('复制失败'))
}

// ── Lifecycle ───────────────────────────────────────────────────

onMounted(() => {
  loadList()
})
</script>

<style scoped>
.achievement-page {
  display: flex;
  flex-direction: column;
  height: 100%;
}

/* Tab bar */
.tab-bar {
  display: flex;
  gap: var(--sp-1);
  padding: var(--sp-3) var(--sp-5);
  border-bottom: 1px solid var(--c-border);
  flex-shrink: 0;
}
.tab-btn {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  padding: var(--sp-2) var(--sp-4);
  background: transparent;
  border: 1px solid transparent;
  border-radius: var(--radius-sm);
  color: var(--c-text-tertiary);
  cursor: pointer;
  font-size: var(--fs-sm);
  transition: all 0.15s;
}
.tab-btn:hover { color: var(--c-text-primary); }
.tab-btn.active {
  color: var(--c-text-primary);
  background: rgba(255,255,255,0.06);
  border-color: var(--c-border);
}

/* Tab body */
.tab-body {
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

/* ── Manage tab ── */
.toolbar {
  padding: var(--sp-4) var(--sp-5);
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
  flex-shrink: 0;
}
.filter-row {
  display: flex;
  gap: var(--sp-2);
  flex-wrap: wrap;
  align-items: center;
}
.filter-input { width: 220px; }
.filter-date { width: 260px; }
.filter-amount { width: 130px; }
.action-row {
  display: flex;
  gap: var(--sp-2);
}
.data-table {
  flex: 1;
  margin: 0 var(--sp-5);
  overflow: auto;
}
.tag-item { margin-right: 4px; }
.text-muted { color: var(--c-text-tertiary); }
.pagination-row {
  padding: var(--sp-3) var(--sp-5);
  display: flex;
  justify-content: flex-end;
  flex-shrink: 0;
}

/* ── Search tab ── */
.search-tab {
  display: flex;
  flex-direction: column;
}
.search-messages {
  flex: 1;
  overflow-y: auto;
  padding: var(--sp-6) var(--sp-5);
}
.messages-list {
  max-width: 794px;
  margin: 0 auto;
}
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 50%;
  text-align: center;
}
.empty-state h3 {
  font-size: var(--fs-lg);
  font-weight: 600;
  color: var(--c-text-primary);
  margin: var(--sp-3) 0 var(--sp-1);
}
.empty-state p {
  font-size: var(--fs-sm);
  color: var(--c-text-tertiary);
  margin: 0;
}

/* Messages */
.message { margin-bottom: var(--sp-4); }
.message.user { display: flex; justify-content: flex-end; }
.message.user .message-bubble {
  background: rgba(255,255,255,0.08);
  border: 1px solid rgba(255,255,255,0.12);
  border-radius: var(--radius) var(--radius) var(--sp-1) var(--radius);
  max-width: 600px;
}
.message.assistant .message-bubble {
  background: var(--glass-bg);
  border: 1px solid var(--c-border);
  border-radius: var(--radius) var(--radius) var(--radius) var(--sp-1);
  width: 100%;
  backdrop-filter: blur(var(--glass-blur));
}
.message-bubble { padding: var(--sp-3) var(--sp-4); }
.message-text { font-size: var(--fs-sm); white-space: pre-wrap; }
.message-content { font-size: var(--fs-sm); color: var(--c-text-secondary); }
.message-content p { margin: 0 0 var(--sp-2); }

/* Result cards */
.result-cards {
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
  margin-top: var(--sp-3);
}
.result-card {
  background: rgba(255,255,255,0.03);
  border: 1px solid var(--c-border);
  border-radius: var(--radius-sm);
  padding: var(--sp-3) var(--sp-4);
  transition: all 0.15s;
}
.result-card:hover {
  border-color: var(--c-border-hover);
  background: rgba(255,255,255,0.05);
}
.rc-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--sp-2);
}
.rc-name {
  font-weight: 600;
  font-size: var(--fs-sm);
  color: var(--c-text-primary);
}
.rc-score {
  background: rgba(74,222,128,0.15);
  color: #4ade80;
  padding: 2px var(--sp-2);
  border-radius: var(--radius-sm);
  font-size: 11px;
  font-weight: 600;
}
.rc-meta {
  display: flex;
  gap: var(--sp-3);
  font-size: var(--fs-xs);
  color: var(--c-text-tertiary);
  margin-bottom: var(--sp-2);
}
.rc-content {
  font-size: var(--fs-xs);
  color: var(--c-text-secondary);
  line-height: 1.5;
  margin-bottom: var(--sp-2);
}
.rc-tags {
  display: flex;
  gap: 4px;
  margin-bottom: var(--sp-2);
}
.rc-actions {
  display: flex;
  gap: var(--sp-3);
  padding-top: var(--sp-2);
  border-top: 1px solid var(--c-border);
}

/* Search input */
.search-input-area {
  border-top: 1px solid var(--c-border);
  background: var(--c-bg-elevated);
  padding: var(--sp-4) var(--sp-5);
  flex-shrink: 0;
}
.search-input-container {
  max-width: 794px;
  margin: 0 auto;
  display: flex;
  gap: var(--sp-3);
  align-items: flex-end;
}

/* Attachment dialog */
.att-upload { margin-bottom: var(--sp-4); }
.att-list {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
}
.att-item {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  padding: var(--sp-2) var(--sp-3);
  background: rgba(255,255,255,0.03);
  border: 1px solid var(--c-border);
  border-radius: var(--radius-sm);
}
.att-name { flex: 1; font-size: var(--fs-sm); }
.att-size { font-size: var(--fs-xs); color: var(--c-text-tertiary); }
.att-item-actions { display: flex; gap: var(--sp-2); }
.att-empty {
  text-align: center;
  padding: var(--sp-6);
  color: var(--c-text-tertiary);
  font-size: var(--fs-sm);
}
</style>
