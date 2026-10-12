import { useEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, getModelOverride, llmUrls, streamSSE } from '../api'
import { useApp } from '../store'
import type { Annotation, NoteDetail } from '../types'
import { applyHighlights, applyInlineComments, selectionInfo } from '../lib/highlight'
import { renderMarkdown, stripFrontAndH1 } from '../lib/md'
import type { TocItem } from '../lib/md'
import Modal from './Modal'
import StreamMd from './StreamMd'
import TermStreamModal from './TermStreamModal'
import {
  IconBulb, IconConcept, IconEdit, IconFilePdf, IconLink, IconList,
  IconRefresh, IconSpark, IconWand,
} from './Icons'

/**
 * 统一阅读器：笔记与概念文档共用同一个组件（概念就是存在 terms/ 下的 md 笔记）。
 *
 * 可选注入点：
 * - header：正文头部的额外内容（概念页的「返回出处」按钮）；
 * - railTop：右栏最上方追加的卡片（概念页的反向链接 / 图谱入口）；
 * - onRegen：提供时「重新生成」按钮改走该回调（概念页的按出处重新生成解释）。
 */
export default function ReaderView({ note, settings, reload, onOpenConcept, toast, header, railTop, onRegen }: {
  note: NoteDetail
  settings: ReturnType<typeof useApp>['settings']
  reload: () => Promise<void>
  onOpenConcept: (path: string) => void
  toast: (t: string, k?: 'ok' | 'err') => void
  header?: ReactNode
  railTop?: ReactNode
  onRegen?: () => void | Promise<void>
}) {
  const navigate = useNavigate()
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(note.content)
  const bodyRef = useRef<HTMLDivElement>(null)
  const wrapRef = useRef<HTMLDivElement>(null)
  const [toc, setToc] = useState<TocItem[]>([])
  const [curHeading, setCurHeading] = useState('')

  // 弹层
  const [sel, setSel] = useState<{ x: number; y: number; quote: string; prefix: string; suffix: string } | null>(null)
  const [hover, setHover] = useState<{ x: number; y: number; target: string; found: boolean; summary: string; path: string } | null>(null)
  const [annMenu, setAnnMenu] = useState<{ x: number; y: number; id: string; comment: string } | null>(null)
  const [askOpen, setAskOpen] = useState<{ quote: string; prefix: string; suffix: string; text: string; save: boolean; streaming: boolean } | null>(null)
  const [regenOpen, setRegenOpen] = useState(false)
  const [continueOpen, setContinueOpen] = useState(false)
  const [termGen, setTermGen] = useState<{ term: string; ctxBefore: string; ctxAfter: string; regenerate: boolean } | null>(null)
  const hoverTimer = useRef<number>()
  const hideTimer = useRef<number>()

  useEffect(() => { setDraft(note.content); setEditing(false) }, [note.path, note.content])

  /* ---------- 渲染 markdown + 自动概念链接 + 高亮 ---------- */
  const conceptNames = useMemo(
    () => (note.concept_refs || []).map((r) => r.name).sort((a, b) => b.length - a.length),
    [note],
  )

  useEffect(() => {
    const el = bodyRef.current
    if (!el || editing) return
    const html = renderMarkdown(stripFrontAndH1(note.content))
    const toc: TocItem[] = (renderMarkdown as any).lastToc
    el.innerHTML = html
    autoLinkConcepts(el, conceptNames)
    applyHighlights(el, note.annotations)
    applyInlineComments(el, note.annotations)
    // 目录：从渲染结果里收集 h2/h3
    const items: TocItem[] = []
    el.querySelectorAll('h2[id], h3[id]').forEach((h) => {
      items.push({ id: h.id, text: h.textContent || '', level: h.tagName === 'H2' ? 2 : 3 })
    })
    setToc(items)

    // 滚动高亮当前小节
    const onScroll = () => {
      let cur = ''
      el.querySelectorAll('h2[id], h3[id]').forEach((h) => {
        if ((h as HTMLElement).getBoundingClientRect().top < 140) cur = h.id
      })
      setCurHeading(cur)
    }
    const scroller = wrapRef.current?.closest('.page-scroll')
    scroller?.addEventListener('scroll', onScroll)
    return () => scroller?.removeEventListener('scroll', onScroll)
  }, [note, editing, conceptNames])

  /* ---------- 划选 → 弹窗 ---------- */
  const onMouseUp = (e: React.MouseEvent) => {
    if (!settings?.reader.selection_menu) return
    setAnnMenu(null)
    const el = bodyRef.current
    if (!el) return
    setTimeout(() => {
      const info = selectionInfo(el)
      if (!info) { setSel(null); return }
      const rect = window.getSelection()!.getRangeAt(0).getBoundingClientRect()
      const wrap = wrapRef.current!.getBoundingClientRect()
      setSel({
        x: rect.left + rect.width / 2 - wrap.left,
        y: rect.bottom - wrap.top + 8,
        quote: info.quote,
        prefix: info.prefix,
        suffix: info.suffix,
      })
    }, 0)
  }

  const doHighlight = async () => {
    if (!sel) return
    try {
      await api.addAnnotation({
        path: note.path, quote: sel.quote, prefix: sel.prefix, suffix: sel.suffix,
        comment: '', occurrence: 1,
      })
      setSel(null)
      window.getSelection()?.removeAllRanges()
      toast('已高亮，可在右栏「我的批注」查看')
      await reload()
    } catch (e: any) { toast(e.message, 'err') }
  }

  const doWhatMean = (termArg?: string, ctxBeforeArg?: string, ctxAfterArg?: string) => {
    const term = (termArg ?? sel?.quote ?? '').trim().slice(0, 40)
    if (!term) return
    const ctxBefore = (ctxBeforeArg ?? sel?.prefix ?? '').slice(-400)
    const ctxAfter = (ctxAfterArg ?? sel?.suffix ?? '').slice(0, 400)
    setSel(null)
    // 流式生成：弹窗内增量展示，落盘后由 onDone 打开概念页
    setTermGen({ term, ctxBefore, ctxAfter, regenerate: false })
  }

  const doExplain = () => {
    if (!sel) return
    setAskOpen({ quote: sel.quote, prefix: sel.prefix.slice(-600), suffix: sel.suffix.slice(0, 600), text: '', save: false, streaming: true })
    setSel(null)
    streamSSE(llmUrls.ask, {
      path: note.path, selected_text: sel.quote, question: '',
      context_before: sel.prefix.slice(-600), context_after: sel.suffix.slice(0, 600),
      stream: true, save_to_note: false, ...getModelOverride(),
    }, (t) => setAskOpen((s) => (s ? { ...s, text: s.text + t, streaming: true } : s)),
      (evt) => setAskOpen((s) => (s ? { ...s, streaming: false } : s)),
      (msg) => { setAskOpen((s) => (s ? { ...s, streaming: false } : s)); toast(msg, 'err') })
  }

  /* ---------- 概念悬浮卡 ---------- */
  const onOver = async (e: React.MouseEvent) => {
    const a = (e.target as HTMLElement).closest('a.wikilink') as HTMLElement | null
    if (!a) return
    const target = a.dataset.target!
    window.clearTimeout(hoverTimer.current)
    hoverTimer.current = window.setTimeout(async () => {
      const rect = a.getBoundingClientRect()
      const wrap = wrapRef.current!.getBoundingClientRect()
      try {
        const r = await api.resolveTerm(target, note.topic)
        setHover({
          x: rect.left + rect.width / 2 - wrap.left, y: rect.bottom - wrap.top + 8,
          target, found: r.found, path: r.found ? r.path : '',
          summary: r.found ? oneLine(r.content) : '该概念还没有解释文档，点击可自动生成。',
        })
      } catch {
        setHover({ x: rect.left + rect.width / 2 - wrap.left, y: rect.bottom - wrap.top + 8, target, found: false, summary: '', path: '' })
      }
    }, 260)
  }
  const onOut = (e: React.MouseEvent) => {
    const a = (e.target as HTMLElement).closest('a.wikilink')
    if (!a) return
    window.clearTimeout(hoverTimer.current)
    hideTimer.current = window.setTimeout(() => setHover(null), 220)
  }
  const onBodyClick = (e: React.MouseEvent) => {
    const a = (e.target as HTMLElement).closest('a.wikilink') as HTMLElement | null
    if (a) {
      e.preventDefault()
      const target = a.dataset.target!
      api.resolveTerm(target, note.topic).then((r) => {
        if (r.found) onOpenConcept(r.path)
        else doWhatMean(target)
      })
      return
    }
    const mark = (e.target as HTMLElement).closest('mark.hl-anchor') as HTMLElement | null
    if (mark) {
      const id = mark.dataset.annId!
      const ann = note.annotations.find((x) => x.id === id)
      const rect = mark.getBoundingClientRect()
      const wrap = wrapRef.current!.getBoundingClientRect()
      setAnnMenu({ x: rect.left - wrap.left, y: rect.bottom - wrap.top + 6, id, comment: ann?.comment || '' })
      setSel(null)
    } else {
      setAnnMenu(null)
    }
  }

  /* ---------- 批注操作 ---------- */
  const delAnn = async (id: string) => {
    try { await api.deleteAnnotation(note.path, id); setAnnMenu(null); await reload() } catch (e: any) { toast(e.message, 'err') }
  }
  const saveAnnComment = async () => {
    if (!annMenu) return
    try {
      await api.updateAnnotation(note.path, annMenu.id, { comment: annMenu.comment })
      setAnnMenu(null); await reload()
    } catch (e: any) { toast(e.message, 'err') }
  }

  const saveDraft = async () => {
    try {
      await api.saveNote(note.path, draft)
      toast('已保存')
      await reload()
    } catch (e: any) { toast(e.message, 'err') }
  }

  const scrollToAnn = (id: string) => {
    bodyRef.current?.querySelector(`mark[data-ann-id="${id}"]`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }
  const scrollToToc = (id: string) => {
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  const styleLabel = (s: string) => (s === 'font' ? '字体高亮' : '背景高亮')

  return (
    <div className="page-with-rail">
      <div className="reader" ref={wrapRef} style={{ position: 'relative' }}>
        {header}
        {/* 头部 */}
        <div className="note-head">
          <h1 className="note-title">{note.title}</h1>
          <div className="note-head-bar">
            <div className="note-meta">
              {note.frontmatter.generated && <span className="ai-badge"><IconSpark size={14} /> AI 生成</span>}
              {note.type === 'term' && <span className="tag">概念解释</span>}
              <span>更新于 {note.updated_at.replace('T', ' ')}</span>
              {!!note.backlinks.length && <span>· 被 {note.backlinks.length} 篇笔记引用</span>}
            </div>
            <div className="note-actions">
              <button className="btn" onClick={() => (onRegen ? onRegen() : setRegenOpen(true))}>
                <IconRefresh size={15} /> 重新生成
              </button>
              <button className="btn primary" onClick={() => setEditing((v) => !v)}>
                <IconEdit size={15} /> {editing ? '退出编辑' : '编辑 MD 源码'}
              </button>
            </div>
          </div>
        </div>

        {/* 正文 */}
        {editing ? (
          <div>
            <textarea className="text-input" style={{ width: '100%', minHeight: 480, lineHeight: 1.8 }}
              value={draft} onChange={(e) => setDraft(e.target.value)} />
            <div style={{ display: 'flex', gap: 10, marginTop: 12 }}>
              <button className="btn primary" onClick={saveDraft}>保存</button>
              <button className="btn" onClick={() => { setEditing(false); setDraft(note.content) }}>取消</button>
            </div>
          </div>
        ) : (
          <div
            ref={bodyRef}
            className="md-body"
            onMouseUp={onMouseUp}
            onMouseOver={onOver}
            onMouseOut={onOut}
            onClick={onBodyClick}
          />
        )}

        {/* 划选弹窗 */}
        {sel && (
          <div className="sel-popover" style={{ left: sel.x, top: sel.y, transform: 'translateX(-50%)' }}>
            <div className="hint">已选中 {sel.quote.length} 个字 · 上下文将一并发送给 AI</div>
            <div className="btns">
              <button className="btn primary" onClick={() => doWhatMean()}>什么意思</button>
              <button className="btn" onClick={doExplain}>解释选段</button>
              <button className="btn" onClick={doHighlight}>高亮</button>
            </div>
          </div>
        )}

        {/* 概念悬浮卡 */}
        {hover && (
          <div className="hover-card" style={{ left: hover.x, top: hover.y, transform: 'translateX(-50%)' }}
            onMouseEnter={() => window.clearTimeout(hideTimer.current)}
            onMouseLeave={() => setHover(null)}>
            <div className="hc-head">
              <IconConcept size={16} />
              {hover.target}
              <span className="hc-badge">概念</span>
            </div>
            {hover.found ? (
              <>
                <div className="hc-body">{hover.summary}</div>
                <div className="hc-link">
                  <button className="btn text" style={{ padding: 0 }} onClick={() => { setHover(null); onOpenConcept(hover.path) }}>
                    查看完整文档 →
                  </button>
                </div>
              </>
            ) : (
              <div className="hc-body hc-empty">
                {hover.summary}
                <div style={{ marginTop: 8 }}>
                  <button className="btn small primary" onClick={() => { setHover(null); doWhatMean(hover.target) }}>生成解释</button>
                </div>
              </div>
            )}
          </div>
        )}

        {/* 批注菜单 */}
        {annMenu && (
          <div className="hover-card" style={{ left: annMenu.x, top: annMenu.y, transform: 'translateX(-30%)', width: 280 }}>
            <div className="hc-head" style={{ fontSize: 13.5 }}>我的批注</div>
            <textarea className="text-input" style={{ width: '100%', marginTop: 8, minHeight: 64 }}
              placeholder="记录此刻的想法..."
              value={annMenu.comment}
              onChange={(e) => setAnnMenu({ ...annMenu, comment: e.target.value })} />
            <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
              <button className="btn small primary" onClick={saveAnnComment}>保存</button>
              <button className="btn small" onClick={() => setAnnMenu(null)}>取消</button>
              <button className="btn small" style={{ color: 'var(--err)', marginLeft: 'auto' }} onClick={() => delAnn(annMenu.id)}>删除</button>
            </div>
          </div>
        )}

        {/* 概念解释流式生成 */}
        {termGen && (
          <TermStreamModal
            path={note.path}
            term={termGen.term}
            contextBefore={termGen.ctxBefore}
            contextAfter={termGen.ctxAfter}
            regenerate={termGen.regenerate}
            onClose={() => setTermGen(null)}
            onDone={(p) => { setTermGen(null); onOpenConcept(p) }}
          />
        )}

        {/* 解释选段 */}
        {askOpen && (
          <Modal title="解释选段" onClose={() => setAskOpen(null)} wide
            ops={
              <>
                <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, color: 'var(--muted)', marginRight: 'auto' }}>
                  <input type="checkbox" checked={askOpen.save} disabled={askOpen.streaming}
                    onChange={(e) => setAskOpen({ ...askOpen, save: e.target.checked })} />
                  回答后把问答追加到笔记末尾
                </label>
                <button className="btn" onClick={() => setAskOpen(null)}>关闭</button>
                {!askOpen.streaming && askOpen.save && (
                  <button className="btn primary" onClick={async () => {
                    try {
                      await api.saveNote(note.path, `${note.content}\n\n## 问答记录\n\n**问：** ${askOpen.quote}\n\n**答：**\n\n${askOpen.text}\n`)
                      setAskOpen(null); toast('已保存到笔记'); await reload()
                    } catch (e: any) { toast(e.message, 'err') }
                  }}>保存到笔记</button>
                )}
              </>
            }>
            <blockquote className="context-quote" style={{ marginTop: 0 }}>
              <div className="q">{askOpen.quote}</div>
            </blockquote>
            <div className={`stream-box ${askOpen.streaming && !askOpen.text ? 'loading-dot' : ''}`}>
              <StreamMd text={askOpen.text} streaming={askOpen.streaming} />
            </div>
          </Modal>
        )}

        {/* 重新生成 */}
        {regenOpen && (
          <RegenModal note={note} onClose={() => setRegenOpen(false)} onDone={async () => { setRegenOpen(false); await reload() }} toast={toast} />
        )}

        {/* AI 续写本节 */}
        {continueOpen && (
          <ContinueModal note={note} onClose={() => setContinueOpen(false)} onDone={reload} toast={toast} />
        )}
      </div>

      {/* ---------------- 右栏 ---------------- */}
      <aside className="rail">
        {railTop}
        <div className="rail-card accent">
          <div className="rail-title"><IconBulb size={16} /> 我的批注 · 自动高亮</div>
          {note.annotations.length ? (
            [...note.annotations].reverse().slice(0, 5).map((a: Annotation) => (
              <div key={a.id} style={{ marginBottom: 12, cursor: 'pointer' }} onClick={() => scrollToAnn(a.id)}>
                <div className="anno-quote">{a.comment || `「${a.quote.slice(0, 50)}${a.quote.length > 50 ? '…' : ''}」`}</div>
                <div className="anno-meta">
                  <span className="swatch" style={{ background: a.color }} />
                  {styleLabel(a.style)} · {a.created_at.slice(5, 10)}
                </div>
              </div>
            ))
          ) : (
            <div className="rail-empty">阅读中划选文字即可高亮并记录想法。</div>
          )}
        </div>

        <div className="rail-card">
          <div className="rail-title"><IconLink size={16} /> 本文涉及的概念 · 双链</div>
          {note.concept_refs?.length ? (
            <>
              <div className="concept-chips">
                {note.concept_refs.map((r) => (
                  <button key={r.path} className="chip" onClick={() => onOpenConcept(r.path)}>
                    <IconConcept size={13} /> {r.name} <span className="n">×{r.count}</span>
                  </button>
                ))}
              </div>
              <div className="rail-note">概念由「什么意思」自动生成，点击可跳转</div>
            </>
          ) : (
            <div className="rail-empty">选中正文里的词组点「什么意思」，概念文档会出现在这里。</div>
          )}
        </div>

        <div className="rail-card">
          <div className="rail-title"><IconList size={16} /> 本页目录</div>
          {toc.length ? (
            <div className="toc-list">
              {toc.map((t) => (
                <button key={t.id} className={t.id === curHeading ? 'cur' : ''}
                  style={{ paddingLeft: t.level === 3 ? 20 : 8 }} onClick={() => scrollToToc(t.id)}>
                  {t.text}
                </button>
              ))}
            </div>
          ) : <div className="rail-empty">暂无小节标题</div>}
        </div>

        <div className="rail-card">
          <div className="rail-title">快捷操作</div>
          <button className="quick-item" onClick={() => document.getElementById('nl-pdf-input')?.click()}>
            <IconFilePdf size={17} /> 导入 PDF <small>自动转为文本笔记</small>
          </button>
          <button className="quick-item" onClick={() => setContinueOpen(true)}>
            <IconWand size={17} /> AI 续写本节内容
          </button>
          <input id="nl-pdf-input" type="file" accept="application/pdf" style={{ display: 'none' }}
            onChange={async (e) => {
              const f = e.target.files?.[0]
              e.target.value = ''
              if (!f) return
              try {
                toast('正在导入 PDF...')
                const created = await api.importPdf(f, note.topic, f.name.replace(/\.pdf$/i, ''))
                toast(`已导入：${created.name}（${created.pages} 页）`)
                await reload()
                navigate(`/notes?path=${encodeURIComponent(created.path)}`)
              } catch (e: any) { toast(e.message, 'err') }
            }} />
        </div>
      </aside>
    </div>
  )
}

/** 把正文纯文本中出现的概念名包成 wikilink（跳过代码/公式/已有链接） */
function autoLinkConcepts(el: HTMLElement, names: string[]) {
  if (!names.length) return
  const escaped = names.map((n) => n.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))
  const re = new RegExp(`(${escaped.join('|')})`, 'g')
  const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT, {
    acceptNode: (node) => {
      const p = node.parentElement
      if (!p) return NodeFilter.FILTER_REJECT
      if (p.closest('pre, code, .katex, a, mark, style, script, h1')) return NodeFilter.FILTER_REJECT
      return NodeFilter.FILTER_ACCEPT
    },
  })
  const targets: Text[] = []
  let n: Node | null
  while ((n = walker.nextNode())) targets.push(n as Text)
  for (const node of targets) {
    const text = node.textContent || ''
    if (!re.test(text)) { re.lastIndex = 0; continue }
    re.lastIndex = 0
    const frag = document.createDocumentFragment()
    let last = 0
    for (const m of text.matchAll(re)) {
      const i = m.index!
      if (i > last) frag.appendChild(document.createTextNode(text.slice(last, i)))
      const a = document.createElement('a')
      a.className = 'wikilink'
      a.dataset.target = m[1]
      a.textContent = m[1]
      frag.appendChild(a)
      last = i + m[1].length
    }
    if (last < text.length) frag.appendChild(document.createTextNode(text.slice(last)))
    node.parentNode?.replaceChild(frag, node)
  }
}

function oneLine(content: string): string {
  const m = content.match(/##\s*一句话解释\s*\n+([\s\S]*?)(?=\n##|$)/)
  let t = (m ? m[1] : content).trim()
  t = t.replace(/^#\s+.+\n/, '').replace(/[#>*`]/g, '').replace(/\s*\n\s*/g, ' ')
  return t.length > 90 ? t.slice(0, 90) + '…' : t
}

/* ---------- 重新生成弹窗 ---------- */
function RegenModal({ note, onClose, onDone, toast }: { note: NoteDetail; onClose: () => void; onDone: () => void; toast: any }) {
  const [prompt, setPrompt] = useState(`请围绕「${note.title}」重写本篇笔记：结构更清晰，保留原文的公式与概念链接。`)
  const [text, setText] = useState('')
  const [running, setRunning] = useState(false)
  const start = () => {
    setRunning(true); setText('')
    streamSSE(llmUrls.generateNote, {
      topic: note.topic, prompt, title: note.title, stream: true, ...getModelOverride(),
    }, (t) => setText((s) => s + t),
      () => setRunning(false),
      (msg) => { setRunning(false); toast(msg, 'err') })
  }
  return (
    <Modal title="重新生成笔记" onClose={onClose} wide
      ops={
        <>
          {!running && !text && <button className="btn primary" style={{ marginRight: 'auto' }} onClick={start}>开始生成</button>}
          {text && (
            <button className="btn primary" disabled={running} style={{ marginRight: 'auto' }} onClick={async () => {
              try {
                const { stripFrontAndH1 } = await import('../lib/md')
                await api.saveNote(note.path, note.content.startsWith('---')
                  ? note.content.slice(0, note.content.indexOf('---', 3) + 4) + '\n\n' + text + '\n'
                  : `# ${note.title}\n\n` + text + '\n')
                toast('已替换正文'); onDone()
              } catch (e: any) { toast(e.message, 'err') }
            }}>应用并保存</button>
          )}
          <button className="btn" onClick={onClose}>关闭</button>
        </>
      }>
      <div className="form-row">
        <label>生成要求（上下文将一并发送给 AI）</label>
        <textarea className="text-input" value={prompt} onChange={(e) => setPrompt(e.target.value)} />
      </div>
      {(text || running) && (
        <div className={`stream-box ${running && !text ? 'loading-dot' : ''}`} style={{ marginTop: 6 }}>
          <StreamMd text={text} streaming={running} />
        </div>
      )}
    </Modal>
  )
}

/* ---------- AI 续写弹窗 ---------- */
function ContinueModal({ note, onClose, onDone, toast }: { note: NoteDetail; onClose: () => void; onDone: () => void; toast: any }) {
  const [text, setText] = useState('')
  const [running, setRunning] = useState(true)
  useEffect(() => {
    const tail = note.content.slice(-1500)
    const ctrl = streamSSE(llmUrls.chat, {
      messages: [
        { role: 'system', content: '你是学习笔记作者。根据笔记已有内容自然续写，输出 Markdown 正文，公式用 LaTeX，不要重复已有内容。' },
        { role: 'user', content: `请续写笔记《${note.title}》的下一节内容。已有内容结尾如下：\n\n...${tail}` },
      ],
      stream: true, ...getModelOverride(),
    }, (t) => setText((s) => s + t),
      () => setRunning(false),
      (msg) => { setRunning(false); toast(msg, 'err') })
    return () => ctrl.abort()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  return (
    <Modal title="AI 续写本节内容" onClose={onClose} wide
      ops={
        <>
          <button className="btn primary" style={{ marginRight: 'auto' }} disabled={running || !text}
            onClick={async () => {
              try {
                await api.saveNote(note.path, `${note.content}\n\n${text}\n`)
                toast('已追加到笔记'); onDone(); onClose()
              } catch (e: any) { toast(e.message, 'err') }
            }}>追加到笔记</button>
          <button className="btn" onClick={onClose}>关闭</button>
        </>
      }>
      <div className={`stream-box ${running && !text ? 'loading-dot' : ''}`}>
        <StreamMd text={text} streaming={running} />
      </div>
    </Modal>
  )
}
