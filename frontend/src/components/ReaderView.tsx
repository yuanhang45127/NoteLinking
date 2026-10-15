import { useEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, getModelOverride, llmUrls } from '../api'
import { useApp } from '../store'
import type { Annotation, NoteDetail, NoteLinkItem } from '../types'
import { applyHighlights, applyInlineComments, selectionInfo } from '../lib/highlight'
import { applySelectionEdit, deleteSectionAt } from '../lib/contentEdit'
import { sendChatReference, sendChatTextRef } from './chat/chatDockSignal'
import { streamTracked } from '../lib/aiTasks'
import { renderMarkdown, stripFrontAndH1 } from '../lib/md'
import type { TocItem } from '../lib/md'
import Modal from './Modal'
import BookPane from './BookPane'
import StreamMd from './StreamMd'
import TermStreamModal from './TermStreamModal'
import VoiceNote from './VoiceNote'
import {
  IconBulb, IconConcept, IconFilePdf, IconLink, IconList,
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
  const { refreshTree, setActiveTopic } = useApp()
  const bodyRef = useRef<HTMLDivElement>(null)
  const wrapRef = useRef<HTMLDivElement>(null)
  const [toc, setToc] = useState<TocItem[]>([])
  const [curHeading, setCurHeading] = useState('')

  // 文献笔记：frontmatter 带 paper_id + pdf_attached 时可分栏展示论文 PDF 原文
  const fm = note.frontmatter || {}
  // AI 生成的笔记锁定手动编辑（后端在 editable 字段里给出判定，editable 键显式优先于 generated）
  const locked = note.editable === false
  const hasPdf = !!fm.paper_id && fm.pdf_attached !== undefined && fm.pdf_attached !== false
  const pdfUrl = hasPdf
    ? `/api/papers/${encodeURIComponent(fm.paper_id)}/pdf?topic=${encodeURIComponent(fm.paper_topic || note.topic)}`
    : ''
  const [pdfOpen, setPdfOpen] = useState(hasPdf)
  // 读书笔记：frontmatter 带 book_id 时可分栏展示原书（EPUB 章节渲染 / PDF 直读）
  const hasBook = !!fm.book_id
  const [bookOpen, setBookOpen] = useState(false)
  // 「看完」标记（frontmatter finished）
  const isFinished = !!(note.frontmatter && note.frontmatter.finished)
  const toggleFinished = async () => {
    try {
      await api.setNoteFinish(note.path, !isFinished)
      toast(isFinished ? '已取消「看完」标记' : '已标记看完 ✓')
      await reload()
      refreshTree() // 同步侧边栏 ✅ 与置顶区状态
    } catch (e: any) { toast(e.message, 'err') }
  }

  // 弹层
  const [sel, setSel] = useState<{ x: number; y: number; quote: string; prefix: string; suffix: string } | null>(null)
  const [hover, setHover] = useState<{ x: number; y: number; up: boolean; target: string; kind: 'term' | 'note'; found: boolean; summary: string; path: string } | null>(null)
  const [annMenu, setAnnMenu] = useState<{ x: number; y: number; id: string; comment: string; quote: string; created_at?: string; mode: 'view' | 'edit' } | null>(null)
  const [regenOpen, setRegenOpen] = useState(false)
  const [continueOpen, setContinueOpen] = useState(false)
  const [voiceOpen, setVoiceOpen] = useState(false)
  const [editOpen, setEditOpen] = useState(false)
  const [termGen, setTermGen] = useState<{ term: string; ctxBefore: string; ctxAfter: string; regenerate: boolean } | null>(null)
  // 划选直接修改：编辑态时保存待写入的新文本
  const [selEdit, setSelEdit] = useState<string | null>(null)
  const hoverTimer = useRef<number>()
  const hideTimer = useRef<number>()

  useEffect(() => { setPdfOpen(hasPdf) }, [note.path, hasPdf]) // 切换笔记时重置 PDF 面板

  /* ---------- 渲染 markdown + 自动概念链接 + 高亮 ---------- */
  const conceptNames = useMemo(
    () => (note.concept_refs || []).map((r) => r.name).sort((a, b) => b.length - a.length),
    [note],
  )

  useEffect(() => {
    const el = bodyRef.current
    if (!el) return
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
  }, [note, conceptNames])

  /* ---------- 阅读进度：服务端记忆，打开时定位到上次位置，滚动时节流回写 ---------- */
  const restoredPathRef = useRef('')
  const lastSavedRef = useRef(NaN)
  useEffect(() => {
    const path = note.path
    const scrollerEl = () => wrapRef.current?.closest('.page-scroll') as HTMLElement | null
    const curHeadingId = () => {
      let cur = ''
      bodyRef.current?.querySelectorAll('h2[id], h3[id]').forEach((h) => {
        if ((h as HTMLElement).getBoundingClientRect().top < 140) cur = h.id
      })
      return cur
    }
    const save = (el: HTMLElement | null) => {
      if (!el) return
      const max = el.scrollHeight - el.clientHeight
      if (max <= 0) return
      const ratio = Math.min(1, Math.max(0, el.scrollTop / max))
      if (Math.abs(ratio - lastSavedRef.current) < 0.005) return
      lastSavedRef.current = ratio
      api.saveReadProgress(path, ratio, curHeadingId()).catch(() => { /* 进度保存失败不打扰阅读 */ })
    }

    // 恢复：每篇笔记打开时拉一次（切换/重开都生效，不用本地缓存）
    if (restoredPathRef.current !== path) {
      restoredPathRef.current = path
      lastSavedRef.current = NaN
      let cancelled = false
      ;(async () => {
        try {
          const pos = await api.getReadProgress(path)
          const el = scrollerEl()
          if (cancelled || !el || !(pos.ratio > 0.02)) return
          const apply = () => { el.scrollTop = pos.ratio * (el.scrollHeight - el.clientHeight) }
          apply()
          // 图片/KaTeX 异步撑开页面后各校准一次
          window.setTimeout(() => { if (!cancelled) apply() }, 400)
          window.setTimeout(() => { if (!cancelled) apply() }, 1000)
        } catch { /* 拉不到就不定位 */ }
      })()
    }

    // 回写：滚动停止 800ms 后保存；切换笔记/卸载时最后落一次
    let timer = 0
    const onScroll = () => { window.clearTimeout(timer); timer = window.setTimeout(() => save(scrollerEl()), 800) }
    const el = scrollerEl()
    el?.addEventListener('scroll', onScroll)
    return () => {
      window.clearTimeout(timer)
      el?.removeEventListener('scroll', onScroll)
      save(el)
    }
  }, [note.path])

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

  /* 划选「加入对话」：选中原文作为行内引用进入 AI 对话面板（chips），随下一轮提问注入 */
  const addSelToChat = () => {
    if (!sel) return
    sendChatTextRef(sel.quote, note.title || note.path)
    setSel(null)
    window.getSelection()?.removeAllRanges()
    toast('已加入 AI 对话引用，直接在面板里提问即可')
  }

  /* ---------- 概念悬浮卡 ---------- */
  /** 打开一篇普通笔记（跨主题双链跳转时顺带切换左侧主题） */
  const openNote = (p: string) => {
    const topic = p.split('/')[0]
    if (topic && topic !== note.topic) setActiveTopic(topic)
    navigate(`/notes?path=${encodeURIComponent(p)}`)
  }
  const onOver = async (e: React.MouseEvent) => {
    const a = (e.target as HTMLElement).closest('a.wikilink') as HTMLElement | null
    if (!a) return
    const target = a.dataset.target!
    window.clearTimeout(hoverTimer.current)
    hoverTimer.current = window.setTimeout(async () => {
      const rect = a.getBoundingClientRect()
      const wrap = wrapRef.current!.getBoundingClientRect()
      // 悬浮卡宽 340px：水平方向钳制在阅读器内，避免溢出被滚动容器裁切/压到侧栏
      const half = 340 / 2 + 12
      const x = Math.min(Math.max(rect.left + rect.width / 2 - wrap.left, half), Math.max(half, wrap.width - half))
      let y = rect.bottom - wrap.top + 8
      let up = false
      // 底部空间不足时翻转到链接上方
      if (y + 220 > wrap.height) { up = true; y = rect.top - wrap.top - 8 }
      const pos = { x, y, up }
      try {
        const r = await api.resolveTerm(target, note.topic)
        if (r.found) {
          setHover({ ...pos, target, kind: 'term', found: true, path: r.path, summary: oneLine(r.content) })
          return
        }
      } catch { /* 接着按笔记解析 */ }
      try {
        const n = await api.resolveLink(target, note.topic)
        setHover({ ...pos, target, kind: n.type === 'term' ? 'term' : 'note', found: true, path: n.path, summary: oneLine(n.content) })
      } catch {
        setHover({ ...pos, target, kind: 'term', found: false, summary: '没有同名笔记或概念文档，点击可生成解释。', path: '' })
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
      // 先按概念词条解析，再按普通笔记解析（Obsidian 式笔记间双链），都没有才引导生成概念
      api.resolveTerm(target, note.topic)
        .catch(() => ({ found: false, path: '' }))
        .then(async (r) => {
          if (r.found) { onOpenConcept(r.path); return }
          try {
            const n = await api.resolveLink(target, note.topic)
            if (n.type === 'term') onOpenConcept(n.path)
            else openNote(n.path)
          } catch {
            doWhatMean(target)
          }
        })
      return
    }
    const mark = (e.target as HTMLElement).closest('mark.hl-anchor') as HTMLElement | null
    if (mark) {
      const id = mark.dataset.annId!
      const ann = note.annotations.find((x) => x.id === id)
      const rect = mark.getBoundingClientRect()
      const wrap = wrapRef.current!.getBoundingClientRect()
      setAnnMenu({
        x: rect.left - wrap.left, y: rect.bottom - wrap.top + 6, id,
        comment: ann?.comment || '', quote: ann?.quote || '',
        created_at: ann?.created_at, mode: 'view',
      })
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
      setAnnMenu({ ...annMenu, mode: 'view' })
      await reload()
    } catch (e: any) { toast(e.message, 'err') }
  }

  /* ---------- 划选直接修改 / 删除（取代编辑 MD 源码） ---------- */
  const persistContent = async (next: string | null, okMsg: string) => {
    if (next === null) { toast('选区跨结构或不在正文中，无法定位，请缩小选择范围', 'err'); return false }
    try {
      await api.saveNote(note.path, next)
      toast(okMsg)
      setSel(null); setSelEdit(null)
      await reload()
      return true
    } catch (e: any) { toast(e.message, 'err'); return false }
  }
  const deleteSelection = async () => {
    if (!sel) return
    if (!window.confirm(`删除选中的 ${sel.quote.length} 个字？`)) return
    await persistContent(applySelectionEdit(note.content, sel, ''), '已删除选中内容')
  }
  const saveSelectionEdit = async () => {
    if (!sel || selEdit === null) return
    if (!selEdit.trim()) { await persistContent(applySelectionEdit(note.content, sel, ''), '内容已清空') ; return }
    await persistContent(applySelectionEdit(note.content, sel, selEdit), '已修改')
  }
  // 高亮弹卡：删除画线对应的原文（连同该批注）
  const delAnnContent = async () => {
    if (!annMenu) return
    const ann = note.annotations.find((x) => x.id === annMenu.id)
    if (!ann) return
    if (!window.confirm('删除高亮对应的原文？该批注会一并移除。')) return
    const next = applySelectionEdit(note.content, { quote: ann.quote, prefix: ann.prefix, suffix: ann.suffix }, '')
    if (next === null) { toast('没能在正文中定位该段内容', 'err'); return }
    try {
      await api.saveNote(note.path, next)
      await api.deleteAnnotation(note.path, ann.id)
      setAnnMenu(null)
      await reload()
      toast('已删除对应内容')
    } catch (e: any) { toast(e.message, 'err') }
  }

  const scrollToAnn = (id: string) => {
    bodyRef.current?.querySelector(`mark[data-ann-id="${id}"]`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }
  const scrollToToc = (id: string) => {
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }
  // 目录操作：删除整节 / 引用为 AI chunk
  const deleteTocSection = async (t: TocItem, order: number) => {
    if (!window.confirm(`删除「${t.text}」整节（标题与内容）？此操作会写入笔记源码。`)) return
    const next = deleteSectionAt(note.content, order)
    if (next === null) { toast('没能在正文中定位该章节', 'err'); return }
    try {
      await api.saveNote(note.path, next)
      toast('已删除该章节')
      await reload()
    } catch (e: any) { toast(e.message, 'err') }
  }

  const styleLabel = (s: string) => (s === 'font' ? '字体高亮' : '背景高亮')

  return (
    <div className={`page-with-rail ${pdfOpen && hasPdf ? 'with-pdf' : ''}`}>
      <div className="reader" ref={wrapRef} style={{ position: 'relative' }}>
        {header}
        {/* 头部 */}
        <div className="note-head">
          <h1 className="note-title">{note.title}</h1>
          <div className="note-head-bar">
            <div className="note-meta">
              {locked ? (
                <span className="ai-badge" title="AI 生成的笔记不可手动编辑，可整篇「重新生成」">
                  <IconSpark size={14} /> AI 生成 · 不可编辑
                </span>
              ) : note.frontmatter.generated && (
                <span className="ai-badge"><IconSpark size={14} /> AI 生成</span>
              )}
              {note.type === 'term' && <span className="tag">概念解释</span>}
              {isFinished && <span className="tag finish-badge">✅ 已看完</span>}
              <span>更新于 {note.updated_at.replace('T', ' ')}</span>
              {!!note.backlinks.length && <span>· 被 {note.backlinks.length} 篇笔记引用</span>}
            </div>
            <div className="note-actions">
              {!locked && (
                <button className="btn" title="说话实时转文字，追加到当前章节"
                  onClick={() => setVoiceOpen(true)}>
                  🎙 语音速记
                </button>
              )}
              <button className={`btn ${isFinished ? 'done' : ''}`}
                title={isFinished ? '点击取消「已看完」标记' : '这篇笔记看完了，标记一下'}
                onClick={toggleFinished}>
                {isFinished ? '✅ 已看完' : '标记看完'}
              </button>
              {hasPdf && (
                <button className="btn" title="分栏展示论文 PDF 原文，与笔记对照阅读"
                  onClick={() => setPdfOpen((v) => !v)}>
                  <IconFilePdf size={15} /> {pdfOpen ? '收起原文' : 'PDF 原文'}
                </button>
              )}
              {hasBook && (
                <button className="btn" title="分栏展示原书内容（EPUB 按章节渲染 / PDF 直读），边读边写笔记"
                  onClick={() => setBookOpen((v) => !v)}>
                  📖 {bookOpen ? '收起原书' : '原书对照'}
                </button>
              )}
              {!locked && (
                <button className="btn" title="编辑 Markdown 源码"
                  onClick={() => setEditOpen(true)}>
                  ✏️ 编辑
                </button>
              )}
              <button className="btn" onClick={() => (onRegen ? onRegen() : setRegenOpen(true))}>
                <IconRefresh size={15} /> 重新生成
              </button>
            </div>
          </div>
        </div>

        {/* 参考链接（frontmatter links，可折叠） */}
        <NoteLinks note={note} reload={reload} toast={toast} />

        {/* 正文 */}
        <div
          ref={bodyRef}
          className="md-body"
          onMouseUp={onMouseUp}
          onMouseOver={onOver}
          onMouseOut={onOut}
          onClick={onBodyClick}
        />

        {/* 划选弹窗 */}
        {sel && (
          <div className="sel-popover" style={{ left: sel.x, top: sel.y, transform: 'translateX(-50%)' }}>
            {selEdit !== null ? (
              <>
                <div className="hint">直接修改选中的内容</div>
                <textarea className="text-input" style={{ width: 260, minHeight: 60, marginTop: 6 }} autoFocus
                  value={selEdit} onChange={(e) => setSelEdit(e.target.value)} />
                <div className="btns" style={{ marginTop: 8 }}>
                  <button className="btn primary small" onClick={saveSelectionEdit}>保存修改</button>
                  <button className="btn small" onClick={() => setSelEdit(null)}>取消</button>
                </div>
              </>
            ) : (
              <>
                <div className="hint">已选中 {sel.quote.length} 个字 · 上下文将一并发送给 AI</div>
                <div className="btns">
                  <button className="btn primary" onClick={() => doWhatMean()}>什么意思</button>
                  <button className="btn" onClick={doHighlight}>高亮</button>
                  <button className="btn" onClick={addSelToChat}>加入对话</button>
                  {!locked && <button className="btn" onClick={() => setSelEdit(sel.quote)}>修改</button>}
                  {!locked && <button className="btn" style={{ color: 'var(--err)' }} onClick={deleteSelection}>删除</button>}
                </div>
              </>
            )}
          </div>
        )}

        {/* 概念悬浮卡 */}
        {hover && (
          <div className="hover-card" style={{ left: hover.x, top: hover.y, transform: `translateX(-50%)${hover.up ? ' translateY(-100%)' : ''}` }}
            onMouseEnter={() => window.clearTimeout(hideTimer.current)}
            onMouseLeave={() => setHover(null)}>
            <div className="hc-head">
              {hover.kind === 'note' ? <IconLink size={16} /> : <IconConcept size={16} />}
              {hover.target}
              <span className="hc-badge">{hover.kind === 'note' ? '笔记' : '概念'}</span>
            </div>
            {hover.found ? (
              <>
                <div className="hc-body">{hover.summary}</div>
                <div className="hc-link">
                  <button className="btn text" style={{ padding: 0 }} onClick={() => { setHover(null); if (hover.kind === 'note') openNote(hover.path); else onOpenConcept(hover.path) }}>
                    {hover.kind === 'note' ? '打开笔记 →' : '查看完整文档 →'}
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

        {/* 批注弹卡：点高亮直接显示批注信息，编辑时切换输入态 */}
        {annMenu && (
          <div className="hover-card" style={{ left: annMenu.x, top: annMenu.y, transform: 'translateX(-30%)', width: 300 }}>
            <div className="hc-head" style={{ fontSize: 13.5 }}>我的批注</div>
            {annMenu.quote && (
              <div className="ann-quote">「{annMenu.quote.length > 80 ? annMenu.quote.slice(0, 80) + '…' : annMenu.quote}」</div>
            )}
            {annMenu.mode === 'view' ? (
              <>
                {annMenu.comment
                  ? <div className="ann-comment">{annMenu.comment}</div>
                  : <div className="ann-comment empty">这条高亮还没有批注</div>}
                <div style={{ display: 'flex', gap: 6, marginTop: 10, alignItems: 'center', flexWrap: 'wrap' }}>
                  <button className="btn small primary" onClick={() => setAnnMenu({ ...annMenu, mode: 'edit' })}>
                    {annMenu.comment ? '编辑批注' : '写批注'}
                  </button>
                  {!locked && (
                    <button className="btn small" title="把画线对应的原文从笔记中删除" onClick={delAnnContent}>删除内容</button>
                  )}
                  <button className="btn small" style={{ color: 'var(--err)', marginLeft: 'auto' }} onClick={() => delAnn(annMenu.id)}>删除批注</button>
                </div>
                {annMenu.created_at && <div className="ann-time">{annMenu.created_at.replace('T', ' ')} 创建</div>}
              </>
            ) : (
              <>
                <textarea className="text-input" style={{ width: '100%', marginTop: 8, minHeight: 64 }}
                  placeholder="记录此刻的想法..." autoFocus
                  value={annMenu.comment}
                  onChange={(e) => setAnnMenu({ ...annMenu, comment: e.target.value })} />
                <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
                  <button className="btn small primary" onClick={saveAnnComment}>保存</button>
                  <button className="btn small" onClick={() => setAnnMenu({ ...annMenu, mode: 'view' })}>取消</button>
                  <button className="btn small" style={{ color: 'var(--err)', marginLeft: 'auto' }} onClick={() => delAnn(annMenu.id)}>删除</button>
                </div>
              </>
            )}
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

        {/* 语音速记 */}
        {voiceOpen && (
          <VoiceNote
            path={note.path}
            content={note.content}
            sectionTitle={toc.find((t) => t.id === curHeading)?.text || toc[0]?.text || null}
            onSaved={reload}
            onClose={() => setVoiceOpen(false)}
            toast={toast}
          />
        )}

        {/* 重新生成 */}
        {regenOpen && (
          <RegenModal note={note} settings={settings} onClose={() => setRegenOpen(false)} onDone={async () => { setRegenOpen(false); await reload() }} toast={toast} />
        )}

        {/* 编辑 Markdown 源码（仅未锁定笔记） */}
        {editOpen && (
          <SourceEditModal note={note} onClose={() => setEditOpen(false)} onDone={async () => { setEditOpen(false); await reload() }} toast={toast} />
        )}

        {/* AI 续写本节 */}
        {continueOpen && (
          <ContinueModal note={note} onClose={() => setContinueOpen(false)} onDone={reload} toast={toast} />
        )}
      </div>

      {/* 文献笔记的 PDF 原文分栏 */}
      {pdfOpen && hasPdf && (
        <div className="pdf-pane">
          <div className="pdf-pane-head">
            <span className="pdf-pane-title"><IconFilePdf size={15} /> 论文原文</span>
            <a className="btn text small" href={pdfUrl} target="_blank" rel="noreferrer">新窗口打开</a>
            <button className="btn text small" onClick={() => setPdfOpen(false)}>收起</button>
          </div>
          <iframe className="pdf-frame" src={pdfUrl} title="论文 PDF" />
        </div>
      )}

      {/* 读书笔记的原书对照分栏 */}
      {bookOpen && hasBook && (
        <BookPane bookId={fm.book_id} fmt={fm.book_fmt || 'epub'} onClose={() => setBookOpen(false)} />
      )}

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
              {toc.map((t, i) => (
                <div key={t.id} className={`toc-row ${t.id === curHeading ? 'cur' : ''}`}
                  style={{ paddingLeft: t.level === 3 ? 20 : 8 }}>
                  <button className="toc-text" onClick={() => scrollToToc(t.id)}>{t.text}</button>
                  <span className="toc-ops">
                    <button title="在 AI 对话中引用本节（chunk）"
                      onClick={() => { sendChatReference(`${note.path}#${t.text}`); toast('已加入 AI 对话引用') }}>💬</button>
                    {!locked && <button title="删除本节（标题与内容）" onClick={() => deleteTocSection(t, i)}>🗑</button>}
                  </span>
                </div>
              ))}
            </div>
          ) : <div className="rail-empty">暂无小节标题</div>}
        </div>

        <div className="rail-card">
          <div className="rail-title">快捷操作</div>
          <button className="quick-item" onClick={() => document.getElementById('nl-pdf-input')?.click()}>
            <IconFilePdf size={17} /> 导入 PDF <small>自动转为文本笔记</small>
          </button>
          {!locked && (
            <button className="quick-item" onClick={() => setContinueOpen(true)}>
              <IconWand size={17} /> AI 续写本节内容
            </button>
          )}
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

/* ---------- 参考链接卡（frontmatter links） ---------- */
function NoteLinks({ note, reload, toast }: { note: NoteDetail; reload: () => Promise<void>; toast: (t: string, k?: 'ok' | 'err') => void }) {
  const links: NoteLinkItem[] = (note.frontmatter?.links as NoteLinkItem[] | undefined) || []
  const [open, setOpen] = useState(false)
  const [url, setUrl] = useState('')
  const [title, setTitle] = useState('')
  const [adding, setAdding] = useState(false)

  const sourceLabel = (s?: string) => (s === 'web_search' ? '联网' : s === 'ai' ? 'AI' : '手动')

  const add = async () => {
    const u = url.trim()
    if (!u) return
    setAdding(true)
    try {
      let t = title.trim()
      if (!t) {
        // 标题留空：先抓取网页标题，失败回退为域名
        try { t = (await api.webFetch(u)).title || '' } catch { /* 回退 host */ }
        if (!t) { try { t = new URL(u).host } catch { t = u } }
      }
      await api.addNoteLink(note.path, u, t)
      setUrl(''); setTitle('')
      toast('已添加参考链接')
      await reload()
    } catch (e: any) { toast(e.message, 'err') }
    setAdding(false)
  }

  const remove = async (u: string) => {
    try { await api.removeNoteLink(note.path, u); await reload() }
    catch (e: any) { toast(e.message, 'err') }
  }

  if (!links.length && !open) return null

  return (
    <div className="note-links">
      <button className="nl-head" onClick={() => setOpen((v) => !v)}
        title={open ? '收起参考链接' : '展开参考链接'}>
        <IconLink size={14} /> 参考链接{links.length ? ` (${links.length})` : ''}
        <span className="nl-caret">{open ? '▾' : '▸'}</span>
      </button>
      {open && (
        <div className="nl-body">
          {links.map((l) => (
            <div key={l.url} className="nl-row">
              <button className="nl-link" title={l.url}
                onClick={() => window.open(l.url, '_blank', 'noopener')}>
                🔗 {l.title || l.url}
              </button>
              <span className="nl-src">{sourceLabel(l.source)}</span>
              <button className="nl-del" title="删除该链接" onClick={() => remove(l.url)}>✕</button>
            </div>
          ))}
          {!links.length && <div className="rail-empty">还没有参考链接，在下面添加。</div>}
          <div className="nl-add">
            <input className="text-input" placeholder="链接地址 https://..." value={url}
              disabled={adding} onChange={(e) => setUrl(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && add()} />
            <input className="text-input" placeholder="标题（留空自动获取）" value={title}
              disabled={adding} onChange={(e) => setTitle(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && add()} />
            <button className="btn small primary" disabled={adding || !url.trim()} onClick={add}>
              {adding ? '获取中...' : '添加'}
            </button>
          </div>
        </div>
      )}
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

/* ---------- 编辑 Markdown 源码弹窗（AI 生成笔记锁定，不提供入口） ---------- */
function SourceEditModal({ note, onClose, onDone, toast }: { note: NoteDetail; onClose: () => void; onDone: () => void; toast: any }) {
  const [text, setText] = useState(note.content)
  const dirty = text !== note.content
  return (
    <Modal title={`编辑源码 · ${note.title}`} onClose={onClose} wide
      ops={
        <>
          <button className="btn primary" style={{ marginRight: 'auto' }} disabled={!dirty}
            onClick={async () => {
              try {
                await api.saveNote(note.path, text)
                toast('已保存')
                onDone()
              } catch (e: any) { toast(e.message, 'err') }
            }}>保存</button>
          <button className="btn" onClick={onClose}>取消</button>
        </>
      }>
      <textarea className="text-input" style={{ width: '100%', minHeight: 440, fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace', fontSize: 13, lineHeight: 1.65 }}
        value={text} onChange={(e) => setText(e.target.value)} autoFocus />
    </Modal>
  )
}

/* ---------- 重新生成弹窗 ---------- */
function RegenModal({ note, settings, onClose, onDone, toast }: { note: NoteDetail; settings: ReturnType<typeof useApp>['settings']; onClose: () => void; onDone: () => void; toast: any }) {
  const [prompt, setPrompt] = useState(`请围绕「${note.title}」重写本篇笔记：结构更清晰，保留原文的公式与概念链接。`)
  const [text, setText] = useState('')
  const [running, setRunning] = useState(false)
  const [bg, setBg] = useState(false)
  const [useWeb, setUseWeb] = useState(false)
  const ctrlRef = useRef<{ abort: () => void } | null>(null)
  const start = () => {
    setRunning(true); setText('')
    ctrlRef.current = streamTracked(
      { title: `重写笔记 · ${note.title}`, kind: 'note', foreground: () => setBg(false) },
      llmUrls.generateNote, {
        topic: note.topic, prompt, title: note.title, stream: true,
        use_web: useWeb,
        ...getModelOverride(),
      },
      {
        onDelta: (t) => setText((s) => s + t),
        onDone: () => setRunning(false),
        onError: (msg) => { setRunning(false); toast(msg, 'err') },
      })
  }
  if (bg) return null
  return (
    <Modal title="重新生成笔记" onClose={() => { ctrlRef.current?.abort(); onClose() }} wide
      ops={
        <>
          {!running && !text && <button className="btn primary" style={{ marginRight: 'auto' }} onClick={start}>开始生成</button>}
          {running && <button className="btn" style={{ marginRight: 'auto' }} title="收起弹窗，生成继续在右下角悬浮窗里跑" onClick={() => setBg(true)}>后台</button>}
          {text && (
            <button className="btn primary" disabled={running} style={{ marginRight: 'auto' }} onClick={async () => {
              try {
                const { stripFrontAndH1 } = await import('../lib/md')
                // 重新生成属于 AI 整篇替换：走覆盖创建，绕开生成笔记的编辑锁
                await api.createNote(note.path, note.content.startsWith('---')
                  ? note.content.slice(0, note.content.indexOf('---', 3) + 4) + '\n\n' + text + '\n'
                  : `# ${note.title}\n\n` + text + '\n', true)
                toast('已替换正文'); onDone()
              } catch (e: any) { toast(e.message, 'err') }
            }}>应用并保存</button>
          )}
          <button className="btn" onClick={() => { ctrlRef.current?.abort(); onClose() }}>关闭</button>
        </>
      }>
      <div className="form-row">
        <label>生成要求（上下文将一并发送给 AI）</label>
        <textarea className="text-input" value={prompt} onChange={(e) => setPrompt(e.target.value)} />
      </div>
      {settings?.web_search?.enabled && (
        <label className="check-row" style={{ cursor: 'pointer', marginBottom: 10 }}>
          <input type="checkbox" checked={useWeb} disabled={running}
            onChange={(e) => setUseWeb(e.target.checked)} />
          联网搜索
          <span style={{ color: 'var(--muted)', fontSize: 12.5 }}>允许 AI 检索网络获取最新信息</span>
        </label>
      )}
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
  const [bg, setBg] = useState(false)
  const ctrlRef = useRef<{ abort: () => void } | null>(null)
  useEffect(() => {
    const tail = note.content.slice(-1500)
    const t = streamTracked(
      { title: `续写笔记 · ${note.title}`, kind: 'note', foreground: () => setBg(false) },
      llmUrls.chat, {
        messages: [
          { role: 'system', content: '你是学习笔记作者。根据笔记已有内容自然续写，输出 Markdown 正文，公式用 LaTeX，不要重复已有内容。' },
          { role: 'user', content: `请续写笔记《${note.title}》的下一节内容。已有内容结尾如下：\n\n...${tail}` },
        ],
        stream: true, ...getModelOverride(),
      },
      {
        onDelta: (x) => setText((s) => s + x),
        onDone: () => setRunning(false),
        onError: (msg) => { setRunning(false); toast(msg, 'err') },
      })
    ctrlRef.current = t
    return () => t.abort()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  if (bg) return null
  return (
    <Modal title="AI 续写本节内容" onClose={() => { ctrlRef.current?.abort(); onClose() }} wide
      ops={
        <>
          <button className="btn primary" style={{ marginRight: 'auto' }} disabled={running || !text}
            onClick={async () => {
              try {
                await api.saveNote(note.path, `${note.content}\n\n${text}\n`)
                toast('已追加到笔记'); onDone(); onClose()
              } catch (e: any) { toast(e.message, 'err') }
            }}>追加到笔记</button>
          {running && <button className="btn" title="收起弹窗，生成继续在右下角悬浮窗里跑" onClick={() => setBg(true)}>后台</button>}
          <button className="btn" onClick={() => { ctrlRef.current?.abort(); onClose() }}>关闭</button>
        </>
      }>
      <div className={`stream-box ${running && !text ? 'loading-dot' : ''}`}>
        <StreamMd text={text} streaming={running} />
      </div>
    </Modal>
  )
}
