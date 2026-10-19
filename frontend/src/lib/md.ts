// Markdown 渲染：LaTeX(KaTeX) + [[双链]] + 目录/章节提取
import MarkdownIt from 'markdown-it'
import katexPlugin from '@vscode/markdown-it-katex'

export interface TocItem { id: string; text: string; level: number }

function escapeHtml(s: string) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
}

export const md = new MarkdownIt({ html: false, linkify: true, breaks: false })
md.use(katexPlugin as any)

// [[目标|别名]] → 概念链接（缺失概念由前端加 .missing）
md.inline.ruler.before('link', 'wikilink', (state, silent) => {
  const src: string = state.src
  const pos: number = state.pos
  if (src.charCodeAt(pos) !== 0x5b || src.charCodeAt(pos + 1) !== 0x5b) return false
  const end = src.indexOf(']]', pos + 2)
  if (end === -1) return false
  const inner = src.slice(pos + 2, end)
  if (/\n/.test(inner)) return false
  const [rawTarget, alias] = inner.split('|')
  const target = rawTarget.split('#')[0].trim()
  if (!target) return false
  if (!silent) {
    const label = (alias || rawTarget.split('#')[0]).trim()
    const token = state.push('html_inline', '', 0)
    token.content =
      `<a class="wikilink" data-target="${escapeHtml(target)}" data-label="${escapeHtml(label)}">${escapeHtml(label)}</a>`
  }
  ;(state as any).pos = end + 2
  return true
})

// 笔记内相对路径图片 → 库内资产接口（远程/绝对/data URI 不动）；env.noteDir 为笔记所在目录。
// <img> 请求带不了 X-Notebook-Token 头，站点令牌走 ?token= 查询参数（token_guard 支持）
md.renderer.rules.image = (tokens, idx, options, env, self) => {
  const token = tokens[idx]
  const src = token.attrGet('src') || ''
  const dir = (env as any)?.noteDir
  if (typeof dir === 'string' && src && !/^(https?:|data:|\/)/i.test(src)) {
    let rel = src.replace(/^\.\//, '')
    try { rel = decodeURIComponent(rel) } catch { /* markdown-it 编码前的原文，保持原样 */ }
    const full = dir ? `${dir}/${rel}` : rel
    const site = localStorage.getItem('nl-token') || ''
    token.attrSet('src', `/api/notes/asset?path=${encodeURIComponent(full)}&token=${encodeURIComponent(site)}`)
  }
  token.attrSet('alt', self.renderInlineAsText(token.children || [], options, env))
  return self.renderToken(tokens, idx, options)
}

/** 渲染 markdown → HTML（heading 加 id 供目录定位）；noteDir 传笔记所在目录以解析相对路径图片 */
export function renderMarkdown(content: string, noteDir?: string): string {
  let hIndex = 0
  const prevHeading = md.renderer.rules.heading_open
  md.renderer.rules.heading_open = (tokens, idx, options, env, self) => {
    const level = tokens[idx].tag
    const text = (tokens[idx + 1]?.content || '').replace(/\s+/g, ' ').trim()
    const id = `h-${++hIndex}`
    if (env) (env as any).toc = (env as any).toc || []
    ;((env as any).toc as TocItem[]).push({ id, text, level: Number(level[1]) })
    return `<${level} id="${id}">`
  }
  const env: any = { noteDir }
  const html = md.render(content, env)
  md.renderer.rules.heading_open = prevHeading || ((tokens, idx, options, _env, self) => self.renderToken(tokens, idx, options))
  lastToc = (env.toc || []).filter((t: TocItem) => t.level >= 2 && t.level <= 3)
  return html
}

export let lastToc: TocItem[] = []

/** 提取纯文本中的一级/二级章节（title → content） */
export function splitSections(body: string): { title: string; content: string }[] {
  const lines = body.split('\n')
  const sections: { title: string; content: string }[] = [{ title: '', content: '' }]
  for (const line of lines) {
    const m = line.match(/^##\s+(.+?)\s*$/)
    if (m) sections.push({ title: m[1], content: '' })
    else sections[sections.length - 1].content += line + '\n'
  }
  return sections.map((s) => ({ ...s, content: s.content.trim() }))
}

/** 取「一句话解释」等章节的纯文本 */
export function sectionText(body: string, title: string): string {
  const sec = splitSections(body).find((s) => s.title === title || s.title.startsWith(title))
  if (!sec) return ''
  return sec.content
    .replace(/```[\s\S]*?```/g, '')
    .replace(/\$\$[\s\S]*?\$\$/g, '')
    .replace(/[#>*`$]/g, '')
    .replace(/\[\[([^\]|]+)(\|([^\]]+))?\]\]/g, '$1')
    .trim()
}

/** 提取正文中的全部 [[双链]] 目标名 */
export function extractWikiTargets(text: string): string[] {
  const out: string[] = []
  const seen = new Set<string>()
  for (const m of text.matchAll(/\[\[([^\[\]]+?)\]\]/g)) {
    const t = m[1].split('|')[0].split('#')[0].trim()
    if (t && !seen.has(t)) { seen.add(t); out.push(t) }
  }
  return out
}

/** 剥掉 frontmatter 与一级标题，返回正文 */
export function stripFrontAndH1(content: string): string {
  let body = content
  const fm = body.match(/^---\r?\n[\s\S]*?\r?\n---\r?\n?/)
  if (fm) body = body.slice(fm[0].length)
  return body.replace(/^\s+/, '').replace(/^#\s+.+\r?\n+/, '')
}
