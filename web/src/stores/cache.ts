/**
 * 全局数据缓存 Store
 * 
 * 避免重复请求：首次加载后数据保存在内存中，
 * 页面切换时直接从缓存读取，无需重新请求后端。
 * 用户可手动点击"刷新"按钮强制更新。
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '@/composables/useApi'
import type { ApiResponse, SystemStats, DocumentItem, DocumentListData } from '@/types/api'

export const useCacheStore = defineStore('cache', () => {
  // 系统统计数据
  const systemStats = ref<SystemStats | null>(null)
  const statsLoading = ref(false)
  const statsLoaded = ref(false)

  // 文档数据缓存 (按 collection 缓存)
  const documentsCache = ref<Map<string, {
    items: DocumentItem[]
    total: number
    loaded: boolean
  }>>(new Map())

  // 集合列表
  const collections = ref<string[]>(['default'])
  const collectionsLoaded = ref(false)

  /**
   * 加载系统统计数据（仅首次加载，除非强制刷新）
   */
  async function loadStats(force = false): Promise<SystemStats | null> {
    if (statsLoaded.value && !force && systemStats.value) {
      return systemStats.value
    }

    statsLoading.value = true
    try {
      const { data } = await api.get<ApiResponse<SystemStats>>('/system/stats')
      if (data.ok && data.data) {
        systemStats.value = data.data
        statsLoaded.value = true
        // 同时更新集合列表
        if (data.data.collections?.length) {
          collections.value = data.data.collections
          collectionsLoaded.value = true
        }
      }
    } finally {
      statsLoading.value = false
    }
    return systemStats.value
  }

  /**
   * 获取集合列表（优先从缓存读取）
   */
  async function loadCollections(force = false): Promise<string[]> {
    if (collectionsLoaded.value && !force) {
      return collections.value
    }
    await loadStats(force)
    return collections.value
  }

  /**
   * 加载文档列表（按 collection 缓存）
   */
  async function loadDocuments(
    collection: string,
    page: number = 1,
    size: number = 20,
    force = false
  ): Promise<{ items: DocumentItem[]; total: number }> {
    const cacheKey = collection
    
    // 对于分页数据，只在第一页时检查缓存
    if (page === 1 && !force) {
      const cached = documentsCache.value.get(cacheKey)
      if (cached?.loaded) {
        return { items: cached.items, total: cached.total }
      }
    }

    const { data } = await api.get<ApiResponse<DocumentListData>>('/data/documents', {
      params: { collection, page, size },
    })

    if (data.ok && data.data) {
      const result = { items: data.data.items, total: data.data.total }
      
      // 仅缓存第一页数据
      if (page === 1) {
        documentsCache.value.set(cacheKey, {
          items: result.items,
          total: result.total,
          loaded: true,
        })
      }
      return result
    }

    return { items: [], total: 0 }
  }

  /**
   * 清除所有缓存（用于强制刷新）
   */
  function clearCache() {
    systemStats.value = null
    statsLoaded.value = false
    documentsCache.value.clear()
    collections.value = ['default']
    collectionsLoaded.value = false
  }

  /**
   * 清除指定集合的文档缓存
   */
  function clearDocumentsCache(collection?: string) {
    if (collection) {
      documentsCache.value.delete(collection)
    } else {
      documentsCache.value.clear()
    }
  }

  return {
    // State
    systemStats,
    statsLoading,
    statsLoaded,
    collections,
    collectionsLoaded,
    
    // Actions
    loadStats,
    loadCollections,
    loadDocuments,
    clearCache,
    clearDocumentsCache,
  }
})
