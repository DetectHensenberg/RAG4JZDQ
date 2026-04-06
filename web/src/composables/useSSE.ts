/**
 * SSE (Server-Sent Events) composable for streaming API responses.
 * 
 * Features:
 * - Heartbeat detection to detect stale connections
 * - Auto-reconnect on connection loss
 * - Page visibility handling to recover from background/sleep
 */
export function useSSE() {
  let controller: AbortController | null = null
  let heartbeatTimer: ReturnType<typeof setTimeout> | null = null
  let lastEventTime = 0
  let isStreaming = false
  let reconnectAttempts = 0
  
  const HEARTBEAT_TIMEOUT = 180000  // 180s without events = stale (LLM calls can take 60-120s)
  const MAX_RECONNECT_ATTEMPTS = 3
  const RECONNECT_DELAY = 2000  // 2s between reconnects

  function clearHeartbeat() {
    if (heartbeatTimer) {
      clearTimeout(heartbeatTimer)
      heartbeatTimer = null
    }
  }

  function resetHeartbeat(onStale: () => void) {
    clearHeartbeat()
    lastEventTime = Date.now()
    heartbeatTimer = setTimeout(() => {
      if (isStreaming && Date.now() - lastEventTime > HEARTBEAT_TIMEOUT) {
        console.warn('[SSE] Connection stale, triggering reconnect')
        onStale()
      }
    }, HEARTBEAT_TIMEOUT + 1000)
  }

  async function stream(
    url: string,
    body: Record<string, any>,
    onEvent: (event: { type: string; [key: string]: any }) => void,
    onDone?: () => void,
    onError?: (err: Error) => void,
  ) {
    isStreaming = true
    reconnectAttempts = 0
    
    // Handle page visibility changes
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible' && isStreaming) {
        // Page became visible, check if connection is stale
        if (Date.now() - lastEventTime > HEARTBEAT_TIMEOUT) {
          console.warn('[SSE] Page resumed, connection may be stale')
          // The heartbeat timer will handle reconnection
        }
      }
    }
    document.addEventListener('visibilitychange', handleVisibilityChange)

    async function doStream(): Promise<boolean> {
      controller = new AbortController()

      try {
        const hasBody = body && Object.keys(body).length > 0
        const resp = await fetch(url, {
          method: hasBody ? 'POST' : 'GET',
          headers: {
            'Accept': 'text/event-stream',
            ...(hasBody ? { 'Content-Type': 'application/json' } : {}),
          },
          body: hasBody ? JSON.stringify(body) : undefined,
          signal: controller.signal,
        })

        if (!resp.ok) {
          throw new Error(`HTTP ${resp.status}`)
        }

        const reader = resp.body?.getReader()
        if (!reader) throw new Error('No response body')

        const decoder = new TextDecoder()
        let buffer = ''
        
        // Start heartbeat monitoring
        resetHeartbeat(() => {
          controller?.abort()
        })

        while (true) {
          const { done, value } = await reader.read()
          if (done) break

          // Reset heartbeat on any data received
          resetHeartbeat(() => {
            controller?.abort()
          })

          buffer += decoder.decode(value, { stream: true })
          const lines = buffer.split('\n')
          buffer = lines.pop() || ''

          for (const line of lines) {
            if (line.startsWith('data: ')) {
              try {
                const data = JSON.parse(line.slice(6))
                onEvent(data)
                
                // Check for terminal events
                if (data.type === 'done' || data.type === 'stopped' || data.type === 'error') {
                  isStreaming = false
                }
              } catch {
                // skip malformed JSON
              }
            }
          }
        }

        return true  // Stream completed normally
      } catch (err: any) {
        if (err.name === 'AbortError') {
          // Check if this was a heartbeat-triggered abort (for reconnect)
          if (isStreaming && reconnectAttempts < MAX_RECONNECT_ATTEMPTS) {
            return false  // Signal to retry
          }
        }
        throw err
      }
    }

    try {
      let completed = await doStream()
      
      // Retry loop for stale connection recovery
      while (!completed && isStreaming && reconnectAttempts < MAX_RECONNECT_ATTEMPTS) {
        reconnectAttempts++
        console.log(`[SSE] Reconnecting (attempt ${reconnectAttempts}/${MAX_RECONNECT_ATTEMPTS})...`)
        await new Promise(r => setTimeout(r, RECONNECT_DELAY))
        completed = await doStream()
      }

      if (isStreaming && !completed) {
        throw new Error('Connection lost after max reconnect attempts')
      }

      onDone?.()
    } catch (err: any) {
      if (err.name !== 'AbortError') {
        onError?.(err)
      }
    } finally {
      isStreaming = false
      clearHeartbeat()
      document.removeEventListener('visibilitychange', handleVisibilityChange)
    }
  }

  /**
   * Stream SSE from an endpoint that accepts FormData (e.g. file upload).
   * Similar to `stream()` but sends FormData instead of JSON.
   */
  async function streamUpload(
    url: string,
    formData: FormData,
    onEvent: (event: { type: string; [key: string]: any }) => void,
    onDone?: () => void,
    onError?: (err: Error) => void,
  ) {
    isStreaming = true
    reconnectAttempts = 0
    controller = new AbortController()

    try {
      const resp = await fetch(url, {
        method: 'POST',
        headers: { 'Accept': 'text/event-stream' },
        body: formData,
        signal: controller.signal,
      })

      if (!resp.ok) throw new Error(`HTTP ${resp.status}`)

      const reader = resp.body?.getReader()
      if (!reader) throw new Error('No response body')

      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6))
              onEvent(data)
              if (data.type === 'done' || data.type === 'error') {
                isStreaming = false
              }
            } catch {
              // skip malformed JSON
            }
          }
        }
      }

      onDone?.()
    } catch (err: any) {
      if (err.name !== 'AbortError') {
        onError?.(err)
      }
    } finally {
      isStreaming = false
    }
  }

  function abort() {
    isStreaming = false
    clearHeartbeat()
    controller?.abort()
    controller = null
  }

  return { stream, streamUpload, abort }
}
