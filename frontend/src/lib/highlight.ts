// 高亮标注：把 annotations 锚定渲染到渲染后的 DOM 上
import type { Annotation } from '../types'

interface TextIndex {
  text: string
  nodes: Text[]
  starts: number[]
}

function buildIndex(root: HTMLElement): TextIndex {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT)
  const nodes: Text[] = []
  const starts: number[] = []
  let text = ''
  let n: Node | null
  while ((n = walker.nextNode())) {
    const t = n as Text
    if (!t.textContent) continue
    if (!(t.parentElement?.closest('pre, code, .katex, style, script'))) {
      starts.push(text.length)
      text += t.textContent
      nodes.push(t)
    }
  }
  return { text, nodes, starts }
}

function locate(index: TextIndex, globalStart: number, globalEnd: number) {
  const { nodes, starts } = index
  let si = nodes.length - 1
  for (let i = 0; i < nodes.length; i++) {
    if (starts[i] <= globalStart && (i === nodes.length - 1 || starts[i + 1] > globalStart)) { si = i; break }
  }
  let ei = si
  for (let i = si; i < nodes.length; i++) {
    if (starts[i] < globalEnd) ei = i
    else break
  }
  const range = document.createRange()
  range.setStart(nodes[si], globalStart - starts[si])
  range.setEnd(nodes[ei], Math.min(globalEnd - starts[ei], nodes[ei].length))
  return range
}

function unwrapMarks(root: HTMLElement) {
  root.querySelectorAll('mark.hl-anchor').forEach((mark) => {
    const parent = mark.parentNode
    if (!parent) return
    while (mark.firstChild) parent.insertBefore(mark.firstChild, mark)
    parent.removeChild(mark)
    parent.normalize()
  })
}

/** 在 root 内渲染全部高亮；返回 mark 元素列表（供绑定点击）。 */
export function applyHighlights(root: HTMLElement, annotations: Annotation[]): HTMLElement[] {
  unwrapMarks(root)
  if (!annotations.length) return []
  const index = buildIndex(root)
  const marks: HTMLElement[] = []
  for (const ann of annotations) {
    const quote = ann.quote
    if (!quote.trim()) continue
    let idx = -1
    let from = 0
    for (;;) {
      const found = index.text.indexOf(quote, from)
      if (found === -1) break
      const prefixOk = !ann.prefix || index.text.slice(Math.max(0, found - ann.prefix.length), found).endsWith(ann.prefix)
      const suffixOk = !ann.suffix || index.text.slice(found + quote.length, found + quote.length + ann.suffix.length).startsWith(ann.suffix)
      if (prefixOk && suffixOk) { idx = found; break }
      from = found + 1
    }
    if (idx === -1) idx = index.text.indexOf(quote)
    if (idx === -1) continue
    const range = locate(index, idx, idx + quote.length)
    if (range.collapsed) continue
    const mark = document.createElement('mark')
    mark.className = `hl-anchor ${ann.style === 'font' ? 'hl-font' : 'hl-bg'}`
    mark.style.setProperty('--hl', ann.color)
    mark.dataset.annId = ann.id
    try {
      mark.appendChild(range.extractContents())
      range.insertNode(mark)
      marks.push(mark)
    } catch { /* 跨边界等异常时跳过 */ }
  }
  return marks
}

/** 求选区在 root 文本索引中的 [start, end) 与前后文。 */
export function selectionInfo(root: HTMLElement) {
  const sel = window.getSelection()
  if (!sel || sel.isCollapsed || sel.rangeCount === 0) return null
  const range = sel.getRangeAt(0)
  if (!root.contains(range.commonAncestorContainer)) return null
  const text = sel.toString().replace(/\s+/g, ' ').trim()
  if (!text) return null
  const index = buildIndex(root)
  // 用「先出现位置」近似定位（高亮锚点主要靠 quote+prefix/suffix，不依赖精确 offset）
  const probe = text.slice(0, 60)
  const idx = index.text.indexOf(probe)
  if (idx === -1) return { quote: text, prefix: '', suffix: '', occurrence: 1 }
  const selIdx = index.text.indexOf(text, Math.max(0, idx - 200))
  const start = selIdx >= 0 ? selIdx : idx
  return {
    quote: text,
    prefix: index.text.slice(Math.max(0, start - 40), start),
    suffix: index.text.slice(start + text.length, start + text.length + 40),
    occurrence: 1,
  }
}
