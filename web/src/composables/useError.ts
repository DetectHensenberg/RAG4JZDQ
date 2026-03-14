/**
 * Unified error handling composable.
 *
 * Provides a consistent way to handle API errors across all views,
 * with automatic user-facing messages via ElMessage.
 */

import { ElMessage } from 'element-plus'
import type { AxiosError } from 'axios'

interface ApiErrorBody {
  ok: boolean
  message?: string
}

/**
 * Extract a user-friendly message from an Axios error or generic Error.
 */
export function extractErrorMessage(err: unknown, fallback = '请求失败'): string {
  if (!err) return fallback

  // Axios error with response body
  const axiosErr = err as AxiosError<ApiErrorBody>
  if (axiosErr?.response?.data?.message) {
    return axiosErr.response.data.message
  }

  // HTTP status based messages
  if (axiosErr?.response?.status) {
    const status = axiosErr.response.status
    if (status === 401) return '未授权，请检查 API Key'
    if (status === 403) return '权限不足'
    if (status === 404) return '资源不存在'
    if (status >= 500) return '服务器内部错误'
  }

  // Generic Error
  if (err instanceof Error && err.message) {
    return err.message
  }

  return fallback
}

/**
 * Show an error toast and optionally log to console.
 */
export function showError(err: unknown, fallback = '操作失败'): void {
  const msg = extractErrorMessage(err, fallback)
  ElMessage.error(msg)
}

/**
 * Wrap an async function with unified error handling.
 * Returns a function that catches errors and displays them via ElMessage.
 */
export function withErrorHandling<T extends (...args: any[]) => Promise<any>>(
  fn: T,
  fallbackMessage = '操作失败',
): (...args: Parameters<T>) => Promise<ReturnType<T> | undefined> {
  return async (...args: Parameters<T>) => {
    try {
      return await fn(...args)
    } catch (err) {
      showError(err, fallbackMessage)
      return undefined
    }
  }
}
