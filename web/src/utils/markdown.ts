import DOMPurify from 'dompurify'
import MarkdownIt from 'markdown-it'

// PlantUML code is rendered via backend API (Kroki)
const PLANTUML_RENDER_ENDPOINT = '/api/plantuml/render'

const md = new MarkdownIt({
  html: true,
  linkify: true,
  typographer: true,
})

// DOMPurify allow-list for XSS protection
const ALLOWED_TAGS = [
  'p', 'br', 'strong', 'em', 'b', 'i', 'u', 's', 'del',
  'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
  'ul', 'ol', 'li', 'blockquote', 'hr',
  'pre', 'code', 'span', 'div',
  'table', 'thead', 'tbody', 'tr', 'th', 'td',
  'a', 'img', 'sup', 'sub',
]
const ALLOWED_ATTR = ['class', 'id', 'href', 'target', 'rel', 'src', 'alt', 'width', 'height', 'style']

function sanitize(html: string): string {
  return DOMPurify.sanitize(html, { ALLOWED_TAGS, ALLOWED_ATTR, ALLOW_DATA_ATTR: false }) as string
}

/**
 * Global store for PlantUML source code keyed by placeholder ID.
 */
const plantumlStore = new Map<string, string>()
const mermaidStore = new Map<string, string>()
let plantumlPlaceholderId = 0
let mermaidPlaceholderId = 0

/**
 * Render markdown text to HTML.
 * PlantUML code blocks are extracted and replaced with placeholder divs.
 * The PlantUML source is stored in a JS map for async rendering.
 */
export function renderMarkdown(text: string): string {
  // Pre-process: convert image reference placeholders to inline images
  // Matches [IMAGE: id], [id] where id looks like a hex image reference (e.g. fdb32762_s2_1)
  text = text.replace(
    /\[IMAGE:\s*([a-f0-9_]+(?:_s\d+_\d+)?)\]/gi,
    '<img src="/api/data/images/$1/raw" alt="$1" class="inline-ref-img" />'
  )
  // Also match bare [hex_id] patterns that look like image refs (8+ hex chars with underscores)
  text = text.replace(
    /\[([a-f0-9]{6,}_s\d+_\d+)\]/gi,
    '<img src="/api/data/images/$1/raw" alt="$1" class="inline-ref-img" />'
  )

  // Pre-process: wrap bare @startuml...@enduml blocks in ```plantuml fences
  // Skip if already fenced (```plantuml present) to avoid double-wrapping
  if (!text.includes('```plantuml')) {
    text = text.replace(
      /(?:^|\n)(@startuml[\s\S]*?@enduml)/g,
      '\n```plantuml\n$1\n```\n'
    )
  }

  // Pre-process: wrap bare mermaid syntax in code fences
  // Captures: keyword line + all subsequent lines that look like mermaid nodes/edges
  const MERMAID_KEYWORDS = /^(graph|flowchart)\s+(LR|RL|TB|TD|BT)\s*$/m
  if (MERMAID_BARE_BLOCK.test(text)) {
    text = text.replace(MERMAID_BARE_BLOCK, (match) => {
      return '\n```mermaid\n' + match.trim() + '\n```\n'
    })
  } else if (MERMAID_KEYWORDS.test(text)) {
    // Fallback: find keyword line + following indented/node lines until blank line
    text = text.replace(
      /^((graph|flowchart)\s+(?:LR|RL|TB|TD|BT)\s*\n(?:[ \t]*\S[^\n]*\n)*)/m,
      '```mermaid\n$1```\n'
    )
  }

  // Match PlantUML and Mermaid fenced code blocks: ```plantuml ... ``` or ```mermaid ... ```
  const FENCE = /```(plantuml|mermaid)\s*\n([\s\S]*?)```/g
  const parts: string[] = []
  let lastIndex = 0
  let match: RegExpExecArray | null

  while ((match = FENCE.exec(text)) !== null) {
    // Render the markdown text before this block
    if (match.index > lastIndex) {
      parts.push(sanitize(md.render(text.slice(lastIndex, match.index))))
    }
    const lang = match[1]
    const code = match[2].trim()
    if (lang === 'plantuml') {
      const id = `plantuml-ph-${++plantumlPlaceholderId}`
      plantumlStore.set(id, code)
      parts.push(`<div class="plantuml-block" id="${id}"><div class="plantuml-loading">图表渲染中…</div></div>`)
    } else {
      const id = `mermaid-ph-${++mermaidPlaceholderId}`
      mermaidStore.set(id, code)
      parts.push(`<div class="mermaid-block" id="${id}"><div class="mermaid-loading">图表渲染中…</div></div>`)
    }
    lastIndex = match.index + match[0].length
  }

  // Render any remaining text after the last block
  if (lastIndex < text.length) {
    parts.push(sanitize(md.render(text.slice(lastIndex))))
  }

  // If no diagram blocks found, just render normally
  if (parts.length === 0) {
    return sanitize(md.render(text))
  }

  return parts.join('')
}

// Regex: bare mermaid block = keyword line followed by node/edge lines until blank line
const MERMAID_BARE_BLOCK = /(?:^|\n)((graph|flowchart)\s+(?:LR|RL|TB|TD|BT)\b[^\n]*\n(?:[ \t]*[A-Za-z\[({].*\n)*)/m

/**
 * Scan a container for all unrendered plantuml-block placeholders and render them.
 * Calls backend API to render PlantUML code to SVG.
 */
// Lazy-loaded mermaid instance
let mermaidReady: Promise<typeof import('mermaid')['default']> | null = null

function getMermaid(): Promise<typeof import('mermaid')['default']> {
  if (!mermaidReady) {
    mermaidReady = import('mermaid').then((m) => {
      m.default.initialize({
        startOnLoad: false,
        theme: 'dark',
        securityLevel: 'loose',
        fontFamily: 'inherit',
      })
      return m.default
    })
  }
  return mermaidReady
}

// Mermaid keyword pattern for detecting bare mermaid in <code> blocks
const MERMAID_CODE_PATTERN = /^(graph|flowchart|sequenceDiagram|classDiagram|stateDiagram|gantt|pie|erDiagram)\b/

export async function renderMermaidInContainer(container: HTMLElement): Promise<void> {
  // Handle plantuml-block
  const blocks = container.querySelectorAll<HTMLElement>('.plantuml-block:not(.plantuml-rendered)')
  
  for (const el of blocks) {
    const code = plantumlStore.get(el.id)
    if (!code) continue
    
    try {
      const resp = await fetch(PLANTUML_RENDER_ENDPOINT, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code, format: 'svg' }),
      })
      
      if (!resp.ok) {
        throw new Error(`Render failed: ${resp.status}`)
      }
      
      const svg = await resp.text()
      el.innerHTML = svg
      el.classList.add('plantuml-rendered')
    } catch (e) {
      console.warn('PlantUML render failed:', e)
      el.innerHTML = `<pre class="plantuml-error"><code>${escapeHtml(code)}</code></pre>`
      el.classList.add('plantuml-rendered')
    }
  }
  
  // Post-detect: scan <pre><code> blocks for plantuml/mermaid that wasn't fenced
  const codeBlocks = container.querySelectorAll<HTMLElement>('pre > code')
  for (const codeEl of codeBlocks) {
    const text = codeEl.textContent?.trim() || ''
    if (text.startsWith('@startuml')) {
      const pre = codeEl.parentElement!
      const id = `plantuml-ph-${++plantumlPlaceholderId}`
      plantumlStore.set(id, text)
      const div = document.createElement('div')
      div.className = 'plantuml-block'
      div.id = id
      div.innerHTML = '<div class="plantuml-loading">图表渲染中…</div>'
      pre.replaceWith(div)
      continue
    }
    if (MERMAID_CODE_PATTERN.test(text)) {
      const pre = codeEl.parentElement!
      const id = `mermaid-post-${++mermaidPlaceholderId}`
      mermaidStore.set(id, text)
      const div = document.createElement('div')
      div.className = 'mermaid-block'
      div.id = id
      div.innerHTML = '<div class="mermaid-loading">图表渲染中…</div>'
      pre.replaceWith(div)
    }
  }

  // Re-query: post-detect may have created new plantuml-block elements
  const postBlocks = container.querySelectorAll<HTMLElement>('.plantuml-block:not(.plantuml-rendered)')
  for (const el of postBlocks) {
    const code = plantumlStore.get(el.id)
    if (!code) continue
    try {
      const resp = await fetch(PLANTUML_RENDER_ENDPOINT, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code, format: 'svg' }),
      })
      if (!resp.ok) throw new Error(`Render failed: ${resp.status}`)
      const svg = await resp.text()
      el.innerHTML = svg
      el.classList.add('plantuml-rendered')
    } catch (e) {
      console.warn('PlantUML post-detect render failed:', e)
      el.innerHTML = `<pre class="plantuml-error"><code>${escapeHtml(code)}</code></pre>`
      el.classList.add('plantuml-rendered')
    }
  }

  // Handle mermaid-block: render via mermaid.js
  const mermaidBlocks = container.querySelectorAll<HTMLElement>('.mermaid-block:not(.mermaid-rendered)')
  for (const el of mermaidBlocks) {
    const code = mermaidStore.get(el.id)
    if (!code) continue
    el.classList.add('mermaid-rendered')
    try {
      const mermaid = await getMermaid()
      const uniqueId = `mmd-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
      const { svg } = await mermaid.render(uniqueId, code)
      el.innerHTML = svg
    } catch (e) {
      console.warn('Mermaid render failed:', e)
      el.innerHTML = `<pre class="mermaid-error"><code>${escapeHtml(code)}</code></pre>`
    }
  }
}

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;')
}
