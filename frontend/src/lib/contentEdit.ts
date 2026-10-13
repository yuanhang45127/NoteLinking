// 划选内容直接编辑：把渲染层选区映射回 Markdown 源文做定位与替换。
// 锚定策略与高亮一致（quote + 前后文），多出处时用前后文消歧，跨结构选区明确报不支持。
export interface SelSpan {
  quote: string
  prefix?: string
  suffix?: string
}

const MD_NOISE = /[#*_`~[\]()!|>]+/g

function norm(s: string): string {
  return s.replace(/\s+/g, '').replace(MD_NOISE, '').toLowerCase()
}

function escapeRx(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

/** 在源码中定位选区引文，返回 [start, end)；定位不到返回 null。 */
export function locateInSource(content: string, sel: SelSpan): [number, number] | null {
  const quote = sel.quote.trim()
  if (!quote) return null

  // 1) 精确匹配：列出全部出现位置
  const hits: number[] = []
  let i = content.indexOf(quote)
  while (i !== -1) {
    hits.push(i)
    i = content.indexOf(quote, i + 1)
  }
  if (hits.length === 1) return [hits[0], hits[0] + quote.length]
  if (hits.length > 1) {
    // 多出处：用前后文消歧（去掉空白与 Markdown 标记后比对尾巴/开头）
    for (const h of hits) {
      const before = content.slice(Math.max(0, h - 60), h)
      const after = content.slice(h + quote.length, h + quote.length + 60)
      const okPrefix = !sel.prefix || norm(before).endsWith(norm(sel.prefix).slice(-30))
      const okSuffix = !sel.suffix || norm(after).startsWith(norm(sel.suffix).slice(0, 30))
      if ((sel.prefix || sel.suffix) && (okPrefix || okSuffix)) return [h, h + quote.length]
    }
    return [hits[0], hits[0] + quote.length]
  }

  // 2) 精确匹配失败 → 空白弹性正则（渲染时换行/多空格被归一化的情况）
  const parts = quote.split(/\s+/).filter(Boolean)
  if (parts.length > 1) {
    const m = new RegExp(parts.map(escapeRx).join('\\s+')).exec(content)
    if (m) return [m.index, m.index + m[0].length]
  }
  return null
}

/** 把选区替换为 replacement（空串即删除）；返回新内容，定位失败返回 null。 */
export function applySelectionEdit(content: string, sel: SelSpan, replacement: string): string | null {
  const span = locateInSource(content, sel)
  if (!span) return null
  return content.slice(0, span[0]) + replacement + content.slice(span[1])
}

// ---------------------------------------------------------------- 章节（chunk）操作
export interface HeadingRef {
  title: string
  level: number
  /** 源码中的行号（0 基） */
  line: number
}

/** 列出源码中的 ##/### 标题（跳过代码围栏内），按文档顺序，与渲染目录一一对应。 */
export function listHeadings(content: string): HeadingRef[] {
  const out: HeadingRef[] = []
  const lines = content.split('\n')
  let inCode = false
  lines.forEach((line, i) => {
    if (/^\s*```/.test(line)) { inCode = !inCode; return }
    if (inCode) return
    const m = /^(#{2,3})\s+(.+?)\s*#*\s*$/.exec(line)
    if (m) out.push({ level: m[1].length, title: m[2].trim(), line: i })
  })
  return out
}

/** 删除第 order 个（0 基，按目录顺序）章节：标题行到下一个同级/更高级标题之前。 */
export function deleteSectionAt(content: string, order: number): string | null {
  const heads = listHeadings(content)
  const h = heads[order]
  if (!h) return null
  const lines = content.split('\n')
  let end = lines.length
  for (let k = order + 1; k < heads.length; k++) {
    if (heads[k].level <= h.level) { end = heads[k].line; break }
  }
  // 顺带收紧删除区间尾部的空行
  let e = end
  while (e - 1 > h.line && lines[e - 1].trim() === '') e--
  return [...lines.slice(0, h.line), ...lines.slice(e)].join('\n')
}

/** 把一段文字插入指定章节（按标题首个匹配）末尾；找不到章节返回 null。 */
export function insertIntoSection(content: string, title: string, text: string): string | null {
  const heads = listHeadings(content)
  const idx = heads.findIndex((h) => h.title === title.trim())
  if (idx === -1) return null
  const h = heads[idx]
  const lines = content.split('\n')
  let end = lines.length
  for (let k = idx + 1; k < heads.length; k++) {
    if (heads[k].level <= h.level) { end = heads[k].line; break }
  }
  let e = end
  while (e - 1 > h.line && lines[e - 1].trim() === '') e--
  return [...lines.slice(0, e), '', text.trim(), ''].concat(lines.slice(e)).join('\n')
}
