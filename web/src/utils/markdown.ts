import MarkdownIt from 'markdown-it'

const md = new MarkdownIt({
  html: false,
  linkify: true,
  typographer: true,
})

export function renderMarkdown(text: string): string {
  return md.render(text)
}

/**
 * Extract mermaid code blocks from markdown text.
 * Returns { html, mermaidBlocks } where html has placeholders for mermaid.
 */
export function renderWithMermaid(text: string): { html: string; mermaidBlocks: string[] } {
  const mermaidBlocks: string[] = []
  const placeholder = (i: number) => `<div class="mermaid-placeholder" data-index="${i}"></div>`

  // Replace ```mermaid ... ``` with placeholders
  const processed = text.replace(/```mermaid\s*\n([\s\S]*?)```/g, (_match, code) => {
    mermaidBlocks.push(code.trim())
    return placeholder(mermaidBlocks.length - 1)
  })

  return { html: md.render(processed), mermaidBlocks }
}
