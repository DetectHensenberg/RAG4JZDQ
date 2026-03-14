/**
 * Shared TypeScript interfaces for API request/response types.
 * Mirrors the Pydantic models in api/models.py.
 */

// ---------------------------------------------------------------------------
// Generic response wrapper
// ---------------------------------------------------------------------------

export interface ApiResponse<T = unknown> {
  ok: boolean
  message?: string
  data?: T
}

// ---------------------------------------------------------------------------
// System overview
// ---------------------------------------------------------------------------

export interface SystemStats {
  collections: string[]
  total_documents: number
  total_chunks: number
  total_images: number
  chroma_size: string
  bm25_size: string
  image_size: string
}

// ---------------------------------------------------------------------------
// Data browser
// ---------------------------------------------------------------------------

export interface DocumentItem {
  file_hash: string
  source_path: string
  collection: string
  status: 'success' | 'failed'
  created_at: string
  chunk_count?: number
}

export interface DocumentListData {
  items: DocumentItem[]
  total: number
}

export interface ChunkItem {
  id: string
  chunk_id: string
  text: string
  content: string
  page?: number
}

// ---------------------------------------------------------------------------
// Knowledge base / Ingestion
// ---------------------------------------------------------------------------

export interface ScannedFile {
  path: string
  name: string
  size: number
}

export interface ScanResult {
  files: ScannedFile[]
  total: number
}

export interface IngestStartResult {
  task_id: string
  total_files: number
}

export interface UploadResult {
  chunks: number
  images: number
  skipped: boolean
}

// ---------------------------------------------------------------------------
// Chat
// ---------------------------------------------------------------------------

export interface ChatReference {
  source: string
  score: number
  text: string
}

export interface ChatHistoryEntry {
  id: number
  question: string
  answer: string
  references: ChatReference[]
  created_at: string
}

// ---------------------------------------------------------------------------
// Evaluation
// ---------------------------------------------------------------------------

export interface EvalHit {
  query: string
  hits: number
  top_sources: string[]
  top_scores: number[]
}

export interface EvalResult {
  results: EvalHit[]
  total_queries: number
}

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------

export interface ConfigData {
  config: Record<string, any>
  api_key_masked: string
  has_api_key: boolean
}

export interface ConnectionTestResult {
  ok: boolean
  message: string
}

// ---------------------------------------------------------------------------
// Collection
// ---------------------------------------------------------------------------

export interface CollectionInfo {
  name: string
  count: number
}
