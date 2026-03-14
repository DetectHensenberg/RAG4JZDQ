/**
 * SSE (Server-Sent Events) composable for streaming API responses.
 */
export function useSSE() {
  let controller: AbortController | null = null

  async function stream(
    url: string,
    body: Record<string, any>,
    onEvent: (event: { type: string; [key: string]: any }) => void,
    onDone?: () => void,
    onError?: (err: Error) => void,
  ) {
    controller = new AbortController()

    try {
      // Use POST if body has content, otherwise GET
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
    }
  }

  function abort() {
    controller?.abort()
    controller = null
  }

  return { stream, abort }
}
