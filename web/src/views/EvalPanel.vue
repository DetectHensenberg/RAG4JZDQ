<template>
  <div class="eval-page">
    <!-- Header -->
    <header class="page-header">
      <div class="header-content">
        <h1 class="page-title">RAGAS 评估</h1>
        <p class="page-subtitle">检索增强生成质量评估 · Retrieve → Generate → Judge</p>
      </div>
    </header>

    <!-- Test Cases Input -->
    <section class="cases-section">
      <div class="section-header">
        <el-icon :size="18"><Edit /></el-icon>
        <span>测试用例</span>
        <span class="case-count">{{ cases.length }} 条</span>
      </div>
      <div class="cases-body">
        <div class="cases-config">
          <div class="config-field">
            <label class="field-label">集合</label>
            <el-select v-model="collection" style="width: 160px">
              <el-option v-for="c in collections" :key="c" :label="c" :value="c" />
            </el-select>
          </div>
          <div class="config-field">
            <label class="field-label">Top K</label>
            <el-input-number v-model="topK" :min="1" :max="20" style="width: 120px" />
          </div>
        </div>

        <div v-for="(c, i) in cases" :key="i" class="case-row">
          <div class="case-num">{{ i + 1 }}</div>
          <div class="case-fields">
            <el-input
              v-model="c.question"
              placeholder="输入测试问题..."
              class="case-q"
            />
            <el-input
              v-model="c.ground_truth"
              placeholder="参考答案（可选，用于 Context Recall）"
              class="case-gt"
            />
          </div>
          <button v-if="cases.length > 1" class="case-del" @click="cases.splice(i, 1)">×</button>
        </div>

        <div class="cases-actions">
          <button class="add-btn" @click="cases.push({ question: '', ground_truth: '' })">+ 添加用例</button>
          <button
            class="run-btn"
            @click="runEval"
            :disabled="!hasValidCase || running"
          >
            <el-icon :size="18"><Loading v-if="running" class="spin" /><VideoPlay v-else /></el-icon>
            <span>{{ running ? `评估中 (${progress}/${cases.length})...` : '运行评估' }}</span>
          </button>
        </div>
      </div>
    </section>

    <!-- Summary Dashboard -->
    <section v-if="summary" class="summary-section">
      <div class="section-header">
        <el-icon :size="18"><DataAnalysis /></el-icon>
        <span>评估总览</span>
        <span class="case-count">{{ summary.total_cases }} 条用例</span>
      </div>
      <div class="metrics-grid">
        <div
          v-for="m in metricCards"
          :key="m.key"
          class="metric-card"
          :class="m.level"
        >
          <div class="metric-label">{{ m.label }}</div>
          <div class="metric-value">{{ m.display }}</div>
          <div class="metric-bar">
            <div class="metric-fill" :style="{ width: m.pct + '%' }"></div>
          </div>
          <div class="metric-desc">{{ m.desc }}</div>
        </div>
      </div>
    </section>

    <!-- Per-case Results -->
    <section v-if="evalResults.length" class="results-section">
      <div class="section-header">
        <el-icon :size="18"><Document /></el-icon>
        <span>详细结果</span>
      </div>
      <div class="results-list">
        <details
          v-for="(r, i) in evalResults"
          :key="i"
          class="result-card"
        >
          <summary class="result-summary">
            <span class="result-q">{{ i + 1 }}. {{ r.question }}</span>
            <div class="result-badges">
              <span v-for="(sv, sk) in r.scores" :key="sk" class="badge" :class="scoreLevel(sv)">{{ metricShort(String(sk)) }} {{ fmtScore(sv) }}</span>
              <span class="badge latency-badge">{{ r.latency_ms }}ms</span>
            </div>
          </summary>
          <div class="result-detail">
            <!-- Answer -->
            <div class="detail-block">
              <div class="detail-label">生成答案</div>
              <div class="detail-text answer-text">{{ truncate(r.answer, 600) }}</div>
            </div>
            <!-- Ground truth -->
            <div v-if="r.ground_truth" class="detail-block">
              <div class="detail-label">参考答案</div>
              <div class="detail-text gt-text">{{ r.ground_truth }}</div>
            </div>
            <!-- Contexts -->
            <div class="detail-block">
              <div class="detail-label">检索上下文 ({{ r.contexts.length }})</div>
              <div v-for="(ctx, ci) in r.contexts" :key="ci" class="ctx-item">
                <span class="ctx-rank">[{{ ci + 1 }}]</span>
                <span class="ctx-source">{{ ctx.source?.split(/[/\\]/).pop() }}</span>
                <span class="ctx-score">{{ ctx.score }}</span>
                <div class="ctx-text">{{ truncate(ctx.text, 200) }}</div>
              </div>
            </div>
            <!-- Metric Scores -->
            <div class="detail-block">
              <div class="detail-label">RAGAS 指标</div>
              <div class="judge-grid">
                <div v-for="(sv, sk) in r.scores" :key="sk" class="judge-item">
                  <div class="judge-metric">{{ metricName(String(sk)) }}</div>
                  <div class="metric-value-inline" :class="scoreLevel(sv)">{{ fmtScore(sv) }}</div>
                </div>
              </div>
            </div>
          </div>
        </details>
      </div>
    </section>

    <!-- Empty State -->
    <section v-if="!summary && !running" class="empty-state">
      <div class="empty-icon">
        <el-icon :size="48"><TrendCharts /></el-icon>
      </div>
      <p class="empty-text">RAGAS 评估</p>
      <p class="empty-hint">输入测试问题，运行完整的 检索→生成→评判 流程</p>
      <div class="metric-explainer">
        <div class="exp-item"><strong>Context Precision</strong>：检索到的上下文是否与问题相关</div>
        <div class="exp-item"><strong>Faithfulness</strong>：生成答案是否忠于检索上下文</div>
        <div class="exp-item"><strong>Answer Relevancy</strong>：生成答案是否切题且完整</div>
        <div class="exp-item"><strong>Context Recall</strong>：上下文是否覆盖参考答案的要点（需提供参考答案）</div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { Edit, Loading, VideoPlay, Document, DataAnalysis, TrendCharts } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import api from '@/composables/useApi'
import type { ApiResponse, SystemStats } from '@/types/api'

interface EvalCase {
  question: string
  ground_truth: string
}

interface CaseResult {
  question: string
  ground_truth: string | null
  answer: string
  contexts: Array<{ source: string; text: string; score: number }>
  scores: Record<string, number>
  latency_ms: number
}

interface Summary {
  total_cases: number
  evaluator: string
  avg_scores: Record<string, number>
}

const collection = ref('default')
const collections = ref<string[]>(['default'])
const topK = ref(5)
const cases = ref<EvalCase[]>([{ question: '', ground_truth: '' }])
const running = ref(false)
const progress = ref(0)
const summary = ref<Summary | null>(null)
const evalResults = ref<CaseResult[]>([])

const hasValidCase = computed(() => cases.value.some(c => c.question.trim()))

function truncate(text: string, max: number): string {
  if (!text) return ''
  return text.length > max ? text.slice(0, max) + '…' : text
}

function fmtScore(v: number | null): string {
  if (v == null) return '—'
  return (v * 100).toFixed(0) + '%'
}

function scoreLevel(v: number | null): string {
  if (v == null) return 'na'
  if (v >= 0.8) return 'high'
  if (v >= 0.5) return 'mid'
  return 'low'
}

const METRIC_META: Record<string, { label: string; desc: string }> = {
  context_precision: { label: 'Context Precision', desc: '检索上下文与问题的相关性' },
  faithfulness: { label: 'Faithfulness', desc: '生成答案对上下文的忠实度' },
  answer_relevancy: { label: 'Answer Relevancy', desc: '生成答案与问题的切题程度' },
  context_recall: { label: 'Context Recall', desc: '上下文对参考答案的覆盖率' },
}

function metricName(key: string): string {
  return METRIC_META[key]?.label || key
}

const METRIC_SHORT: Record<string, string> = {
  context_precision: 'CP',
  faithfulness: 'F',
  answer_relevancy: 'AR',
  context_recall: 'CR',
}

function metricShort(key: string): string {
  return METRIC_SHORT[key] || key.slice(0, 3).toUpperCase()
}

const metricCards = computed(() => {
  if (!summary.value) return []
  const s = summary.value.avg_scores
  return Object.entries(s).map(([key, v]) => {
    const meta = METRIC_META[key]
    return {
      key,
      label: meta?.label || key,
      desc: meta?.desc || '',
      display: fmtScore(v),
      pct: v != null ? v * 100 : 0,
      level: scoreLevel(v),
    }
  })
})

async function loadCollections() {
  try {
    const { data } = await api.get<ApiResponse<SystemStats>>('/system/stats')
    if (data.ok && data.data) collections.value = data.data.collections || ['default']
  } catch { /* ignore */ }
}

async function runEval() {
  const validCases = cases.value.filter(c => c.question.trim())
  if (!validCases.length) return

  running.value = true
  progress.value = 0
  summary.value = null
  evalResults.value = []

  try {
    const { data } = await api.post('/eval/run', {
      cases: validCases.map(c => ({
        question: c.question.trim(),
        ground_truth: c.ground_truth.trim() || null,
      })),
      collection: collection.value,
      top_k: topK.value,
    }, { timeout: 300000 })

    if (data.ok && data.data) {
      summary.value = data.data.summary
      evalResults.value = data.data.results
      ElMessage.success(`评估完成：${data.data.summary.total_cases} 条用例`)
    } else {
      ElMessage.error(data.message || '评估失败')
    }
  } catch (e: any) {
    ElMessage.error(`评估请求失败: ${e.message}`)
  } finally {
    running.value = false
  }
}

onMounted(loadCollections)
</script>

<style scoped>
.eval-page {
  height: 100%;
  overflow: auto;
  padding: var(--sp-6);
  animation: pageEnter 0.5s var(--ease);
}
@keyframes pageEnter {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}

/* Header */
.page-header { margin-bottom: var(--sp-6); }
.page-title {
  font-size: var(--fs-xl);
  font-weight: 600;
  color: var(--c-text-primary);
  margin: 0 0 var(--sp-1);
  letter-spacing: -0.5px;
}
.page-subtitle {
  font-size: var(--fs-sm);
  color: var(--c-text-tertiary);
  margin: 0;
}

/* Shared section styles */
.cases-section, .summary-section, .results-section {
  background: var(--glass-bg);
  backdrop-filter: blur(var(--glass-blur));
  border: 1px solid var(--c-border);
  border-radius: var(--radius);
  margin-bottom: var(--sp-6);
  animation: sectionEnter 0.4s var(--ease);
}
@keyframes sectionEnter {
  from { opacity: 0; transform: translateY(16px); }
  to { opacity: 1; transform: translateY(0); }
}
.section-header {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  padding: var(--sp-4) var(--sp-5);
  background: var(--c-surface);
  border-bottom: 1px solid var(--c-border);
  font-size: var(--fs-sm);
  font-weight: 500;
  color: var(--c-text-primary);
}
.case-count {
  font-size: 11px;
  color: var(--c-text-tertiary);
  background: rgba(255,255,255,0.06);
  padding: 2px var(--sp-2);
  border-radius: var(--radius-xs);
  margin-left: var(--sp-1);
}

/* Cases Input */
.cases-body { padding: var(--sp-5); }
.cases-config {
  display: flex;
  gap: var(--sp-4);
  margin-bottom: var(--sp-4);
}
.config-field {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
}
.field-label {
  font-size: var(--fs-xs);
  color: var(--c-text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.3px;
}
.case-row {
  display: flex;
  align-items: flex-start;
  gap: var(--sp-3);
  margin-bottom: var(--sp-3);
}
.case-num {
  width: 28px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(59,130,246,0.12);
  border-radius: var(--radius-xs);
  font-size: var(--fs-sm);
  font-weight: 600;
  color: #60a5fa;
  flex-shrink: 0;
}
.case-fields {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
}
.case-del {
  width: 28px;
  height: 32px;
  background: rgba(255,100,100,0.08);
  border: 1px solid rgba(255,100,100,0.15);
  border-radius: var(--radius-xs);
  color: #f87171;
  font-size: 16px;
  cursor: pointer;
  transition: all 0.15s;
}
.case-del:hover {
  background: rgba(255,100,100,0.15);
  border-color: rgba(255,100,100,0.3);
}
.cases-actions {
  display: flex;
  align-items: center;
  gap: var(--sp-4);
  margin-top: var(--sp-2);
}
.add-btn {
  background: rgba(255,255,255,0.05);
  border: 1px dashed var(--c-border);
  border-radius: var(--radius-sm);
  color: var(--c-text-secondary);
  font-size: var(--fs-sm);
  padding: var(--sp-2) var(--sp-4);
  cursor: pointer;
  transition: all 0.15s;
}
.add-btn:hover {
  background: rgba(255,255,255,0.08);
  border-color: var(--c-border-hover);
  color: var(--c-text-primary);
}
.run-btn {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  padding: 0 var(--sp-6);
  height: 40px;
  background: var(--c-accent);
  border: none;
  border-radius: var(--radius-sm);
  color: #0a0a0a;
  font-size: var(--fs-sm);
  font-weight: 500;
  cursor: pointer;
  transition: all var(--duration) var(--ease);
}
.run-btn:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(255,255,255,0.2);
}
.run-btn:disabled { opacity: 0.5; cursor: not-allowed; }

/* Metrics Dashboard */
.metrics-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--sp-4);
  padding: var(--sp-5);
}
.metric-card {
  background: var(--c-surface);
  border: 1px solid var(--c-border);
  border-radius: var(--radius);
  padding: var(--sp-4);
  text-align: center;
  transition: all 0.2s;
}
.metric-card.high { border-color: rgba(52,211,153,0.3); }
.metric-card.mid { border-color: rgba(251,191,36,0.3); }
.metric-card.low { border-color: rgba(248,113,113,0.3); }
.metric-label {
  font-size: var(--fs-xs);
  color: var(--c-text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: var(--sp-2);
}
.metric-value {
  font-size: 28px;
  font-weight: 700;
  margin-bottom: var(--sp-3);
  font-variant-numeric: tabular-nums;
}
.metric-card.high .metric-value { color: #34d399; }
.metric-card.mid .metric-value { color: #fbbf24; }
.metric-card.low .metric-value { color: #f87171; }
.metric-card.na .metric-value { color: var(--c-text-tertiary); }
.metric-bar {
  height: 4px;
  background: rgba(255,255,255,0.06);
  border-radius: 2px;
  overflow: hidden;
  margin-bottom: var(--sp-2);
}
.metric-fill {
  height: 100%;
  border-radius: 2px;
  transition: width 0.6s var(--ease);
}
.metric-card.high .metric-fill { background: linear-gradient(90deg, #34d399, #22d3ee); }
.metric-card.mid .metric-fill { background: linear-gradient(90deg, #fbbf24, #fb923c); }
.metric-card.low .metric-fill { background: linear-gradient(90deg, #f87171, #ef4444); }
.metric-desc {
  font-size: 11px;
  color: var(--c-text-tertiary);
  line-height: 1.4;
}

/* Results */
.results-list {
  padding: var(--sp-3);
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
}
.result-card {
  background: var(--c-surface);
  border: 1px solid var(--c-border);
  border-radius: var(--radius-sm);
  transition: all 0.2s;
}
.result-card[open] { border-color: var(--c-border-hover); }
.result-summary {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--sp-3) var(--sp-4);
  cursor: pointer;
  user-select: none;
  gap: var(--sp-3);
}
.result-summary:hover { background: rgba(255,255,255,0.02); }
.result-q {
  font-size: var(--fs-sm);
  color: var(--c-text-primary);
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.result-badges {
  display: flex;
  gap: var(--sp-1);
  flex-shrink: 0;
}
.badge {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 10px;
  font-variant-numeric: tabular-nums;
}
.badge.high { background: rgba(52,211,153,0.15); color: #34d399; }
.badge.mid { background: rgba(251,191,36,0.15); color: #fbbf24; }
.badge.low { background: rgba(248,113,113,0.15); color: #f87171; }
.badge.na { background: rgba(255,255,255,0.05); color: var(--c-text-tertiary); }
.latency-badge { background: rgba(255,255,255,0.05); color: var(--c-text-tertiary); }

/* Detail */
.result-detail {
  padding: 0 var(--sp-4) var(--sp-4);
  border-top: 1px solid var(--c-border);
}
.detail-block {
  margin-top: var(--sp-4);
}
.detail-label {
  font-size: var(--fs-xs);
  font-weight: 600;
  color: var(--c-text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.3px;
  margin-bottom: var(--sp-2);
}
.detail-text {
  font-size: var(--fs-xs);
  line-height: 1.7;
  color: var(--c-text-secondary);
  background: rgba(255,255,255,0.02);
  border: 1px solid var(--c-border);
  border-radius: var(--radius-sm);
  padding: var(--sp-3);
  white-space: pre-wrap;
}
.answer-text { border-left: 3px solid #60a5fa; }
.gt-text { border-left: 3px solid #a78bfa; }

/* Context items */
.ctx-item {
  padding: var(--sp-2) var(--sp-3);
  background: rgba(255,255,255,0.02);
  border: 1px solid var(--c-border);
  border-radius: var(--radius-xs);
  margin-bottom: var(--sp-2);
  font-size: var(--fs-xs);
}
.ctx-rank { color: #60a5fa; font-weight: 600; margin-right: var(--sp-2); }
.ctx-source { color: var(--c-text-secondary); }
.ctx-score { float: right; color: var(--c-text-tertiary); font-family: monospace; }
.ctx-text {
  color: var(--c-text-tertiary);
  margin-top: var(--sp-1);
  line-height: 1.5;
}

/* Judge grid */
.judge-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--sp-3);
}
.judge-item {
  background: rgba(255,255,255,0.02);
  border: 1px solid var(--c-border);
  border-radius: var(--radius-xs);
  padding: var(--sp-3);
}
.judge-metric {
  font-size: 11px;
  font-weight: 600;
  color: var(--c-text-secondary);
  margin-bottom: var(--sp-1);
}
.judge-reasoning {
  font-size: var(--fs-xs);
  color: var(--c-text-tertiary);
  line-height: 1.5;
}
.metric-value-inline {
  font-size: var(--fs-lg);
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}
.metric-value-inline.high { color: #34d399; }
.metric-value-inline.mid { color: #fbbf24; }
.metric-value-inline.low { color: #f87171; }
.metric-value-inline.na { color: var(--c-text-tertiary); }

/* Empty State */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--sp-8);
  animation: sectionEnter 0.4s var(--ease);
}
.empty-icon {
  width: 80px;
  height: 80px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--c-surface);
  border-radius: var(--radius);
  color: var(--c-text-tertiary);
  margin-bottom: var(--sp-4);
}
.empty-text {
  font-size: var(--fs-lg);
  font-weight: 600;
  color: var(--c-text-secondary);
  margin: 0 0 var(--sp-2);
}
.empty-hint {
  font-size: var(--fs-sm);
  color: var(--c-text-tertiary);
  margin: 0 0 var(--sp-5);
}
.metric-explainer {
  max-width: 480px;
  text-align: left;
}
.exp-item {
  font-size: var(--fs-xs);
  color: var(--c-text-tertiary);
  line-height: 1.8;
  padding: var(--sp-1) 0;
}
.exp-item strong {
  color: var(--c-text-secondary);
}

/* Spin */
.spin { animation: spin 1s linear infinite; }
@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

/* Responsive */
@media (max-width: 768px) {
  .metrics-grid { grid-template-columns: repeat(2, 1fr); }
  .cases-config { flex-direction: column; align-items: flex-start; }
  .judge-grid { grid-template-columns: 1fr; }
}
</style>
