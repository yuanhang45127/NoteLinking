import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, getModelOverride, streamUrls } from '../api'
import { useApp } from '../store'
import type { ArxivResult, Paper, ZoteroCollection, ZoteroConfig, ZoteroSyncResult } from '../types'
import { IconTrash } from '../components/Icons'
import { streamTracked } from '../lib/aiTasks'

const STATUS: Record<string, { label: string }> = {
  unread: { label: '未读' },
  reading: { label: '在读' },
  done: { label: '已读' },
}
const STATUS_ORDER = ['unread', 'reading', 'done'] as const

export default function PapersPage() {
  const { activeTopic, refreshTree, toast } = useApp()
  const navigate = useNavigate()
  const [papers, setPapers] = useState<Paper[]>([])
  const [loading, setLoading] = useState(false)
  const [q, setQ] = useState('')
  const [results, setResults] = useState<ArxivResult[]>([])
  const [searching, setSearching] = useState(false)
  const [adding, setAdding] = useState('')
  const [filter, setFilter] = useState<'all' | 'unread' | 'reading' | 'done'>('all')
  const [textFilter, setTextFilter] = useState('')
  const [noteBusy, setNoteBusy] = useState('')
  const [pdfBusy, setPdfBusy] = useState('')
  // 读书笔记：书籍导入与按章梗概生成
  const [importBusy, setImportBusy] = useState(false)
  const [genProgress, setGenProgress] = useState<{ [id: string]: { done: number; total: number; label: string } }>({})
  const bookFileRef = useRef<HTMLInputElement>(null)
  // Zotero 同步
  const [zc, setZc] = useState<ZoteroConfig | null>(null)
  const [zCols, setZCols] = useState<ZoteroCollection[]>([])
  const [zBusy, setZBusy] = useState<'check' | 'sync' | ''>('')
  const [zResult, setZResult] = useState<ZoteroSyncResult | null>(null)

  useEffect(() => { api.zoteroConfig().then(setZc).catch(() => {}) }, [])

  const load = async () => {
    if (!activeTopic) { setPapers([]); return }
    setLoading(true)
    try { setPapers((await api.papers(activeTopic)).papers) }
    catch (e: any) { toast(e.message, 'err') }
    finally { setLoading(false) }
  }
  useEffect(() => { load() }, [activeTopic]) // eslint-disable-line

  const search = async () => {
    if (!q.trim() || !activeTopic) return
    setSearching(true); setResults([])
    try { setResults((await api.searchArxiv(q.trim(), 15)).results) }
    catch (e: any) { toast(e.message, 'err') }
    finally { setSearching(false) }
  }

  const collect = async (r: ArxivResult) => {
    if (!activeTopic) return
    setAdding(r.arxiv_id)
    try {
      await api.addPaper(activeTopic, r)
      toast(`已收录《${r.title.slice(0, 32)}…》`)
      await load()
    } catch (e: any) { toast(e.message, 'err') }
    finally { setAdding('') }
  }

  const cycleStatus = async (p: Paper) => {
    if (!activeTopic) return
    const next = STATUS_ORDER[(STATUS_ORDER.indexOf(p.status) + 1) % STATUS_ORDER.length]
    try { await api.updatePaper(activeTopic, p.id, { status: next }); await load() }
    catch (e: any) { toast(e.message, 'err') }
  }

  const remove = async (p: Paper) => {
    if (!activeTopic || !window.confirm(`确定从文献库移除《${p.title.slice(0, 40)}》？`)) return
    try { await api.deletePaper(activeTopic, p.id); await load() }
    catch (e: any) { toast(e.message, 'err') }
  }

  const genNote = async (p: Paper) => {
    if (!activeTopic) return
    setNoteBusy(p.id)
    try {
      // PDF 附件先就位（失败不阻塞笔记生成，只是笔记里不给内嵌入口）
      let pdfAttached = !!p.pdf_path
      if (!pdfAttached && p.arxiv_id) {
        try {
          await api.fetchPaperPdf(p.topic || activeTopic, p.id)
          pdfAttached = true
        } catch (e: any) { toast(`PDF 下载失败，笔记仍会生成：${e.message}`, 'err') }
      }
      const authors = p.authors.slice(0, 3).join(', ') + (p.authors.length > 3 ? ' 等' : '')
      const prompt = (
        `请根据以下论文信息撰写一篇中文「文献阅读笔记」，包括：研究问题与动机、方法概要、主要贡献、` +
        `局限与展望、与「${activeTopic}」主题的关联。目前只有元数据，请基于标题与摘要合理展开，` +
        `并在合适位置注明「精读全文后可补充」。\n\n` +
        `标题：${p.title}\n作者：${authors || '未知'}\n年份：${p.year}\n来源：${p.venue}\n` +
        `链接：${p.url}\n\n摘要：${p.abstract}`
      )
      const safeName = p.title.replace(/[\\/:*?"<>|]/g, ' ').trim().slice(0, 60)
      const title = `文献笔记 · ${safeName}`
      const { text } = await api.generateNote({ topic: activeTopic, prompt, title })
      // 组装落盘内容：置顶 + 论文关联写进 frontmatter，原文链接固定放正文开头
      const pdfUrl = `/api/papers/${encodeURIComponent(p.id)}/pdf?topic=${encodeURIComponent(p.topic || activeTopic)}`
      const yq = (s: string) => `'${s.replace(/'/g, "''")}'`
      const fm = [
        '---',
        `title: ${yq(title)}`,
        'generated: true',
        `created: '${new Date().toISOString().slice(0, 10)}'`,
        'pinned: true',
        `paper_id: ${p.id}`,
        `paper_topic: ${p.topic || activeTopic}`,
        `pdf_attached: ${pdfAttached}`,
        '---',
      ].join('\n')
      const meta =
        `> 🔗 [arXiv 页面](${p.url})` +
        (pdfAttached ? ` · 📄 [PDF 原文](${pdfUrl})（阅读页内可分栏对照）` : '') +
        '\n'
      const body = text.replace(/^#\s+[^\n]*\n+/, '') // 去掉模型自带的重复大标题
      const saved = await api.createNote(`${activeTopic}/文献/${safeName}.md`, `${fm}\n# ${title}\n\n${meta}\n${body.trim()}\n`)
      toast(pdfAttached ? '阅读笔记已生成，已置顶（附 PDF 原文）' : '阅读笔记已生成，已置顶')
      refreshTree()
      if (saved.path) navigate(`/notes?path=${encodeURIComponent(saved.path)}`)
    } catch (e: any) { toast(e.message, 'err') }
    finally { setNoteBusy('') }
  }

  // ---------- 读书笔记 ----------
  const importBook = async (file: File) => {
    if (!activeTopic) return
    setImportBusy(true)
    try {
      const r = await api.importBook(file, activeTopic)
      toast(`已导入《${r.book.title}》：解析出 ${r.chapters.length} 个章节` +
        (r.book.meta.chunked === false ? `（${r.book.meta.hint || '无章节书签，按整本处理'}）` : ''))
      await load()
    } catch (e: any) { toast(e.message, 'err') }
    finally { setImportBusy(false); if (bookFileRef.current) bookFileRef.current.value = '' }
  }

  const genBookNotes = (p: Paper) => {
    if (!p.book_id || genProgress[p.id]) return
    setGenProgress((s) => ({ ...s, [p.id]: { done: 0, total: 0, label: '准备中' } }))
    const clear = () => setGenProgress((s) => { const n = { ...s }; delete n[p.id]; return n })
    streamTracked(
      { title: `读书笔记 · ${p.title.slice(0, 14)}${p.title.length > 14 ? '…' : ''}`, kind: 'book', foreground: () => navigate('/papers') },
      streamUrls.bookNotes(p.book_id),
      { stream: true, ...getModelOverride() },
      {
        onDelta: () => { /* 章节正文不流式，进度靠事件 */ },
        onDone: (evt) => { // done
          clear()
          toast(`《读书笔记》已生成${evt.failed ? `（${evt.failed} 章梗概失败）` : ''}`)
          refreshTree()
          if (evt.path) navigate(`/notes?path=${encodeURIComponent(evt.path)}`)
        },
        onError: (msg) => { clear(); toast(msg, 'err') },
        onEvent: (evt) => {
          if (evt.type === 'start') setGenProgress((s) => ({ ...s, [p.id]: { done: 0, total: evt.total, label: '开始生成' } }))
          else if (evt.type === 'chapter_start') setGenProgress((s) => ({ ...s, [p.id]: { done: evt.index, total: evt.total, label: evt.title } }))
          else if (evt.type === 'chapter_done') setGenProgress((s) => ({ ...s, [p.id]: { done: evt.index + 1, total: evt.total, label: evt.title } }))
          else if (evt.type === 'chapter_error') setGenProgress((s) => ({ ...s, [p.id]: { done: evt.index + 1, total: evt.total, label: `${evt.title}（失败）` } }))
        },
      },
    )
  }

  const shown = papers.filter((p) =>
    (filter === 'all' || p.status === filter) &&
    (!textFilter.trim() ||
      (p.title + p.authors.join() + p.tags.join()).toLowerCase().includes(textFilter.trim().toLowerCase())))

  // ---------- Zotero 同步 ----------
  const saveZc = async () => {
    if (!zc) return null
    const saved = await api.saveZoteroConfig({
      user_id: zc.user_id, api_key: zc.api_key, base_url: zc.base_url,
      collection: zc.collection, collection_name: zc.collection_name,
      download_pdf: zc.download_pdf,
    })
    setZc(saved)
    return saved
  }

  const checkZotero = async () => {
    setZBusy('check')
    try {
      await saveZc()
      const s = await api.zoteroStatus()
      setZCols(s.collections)
      if (s.config.collection && !s.collections.some((c) => c.key === s.config.collection)) setZc(s.config)
      toast(s.collections.length ? `连接成功，共 ${s.collections.length} 个分类` : '连接成功（库中没有分类，将同步全部条目）')
    } catch (e: any) { toast(e.message, 'err') }
    finally { setZBusy('') }
  }

  const runSync = async () => {
    if (!activeTopic) return
    setZBusy('sync')
    try {
      await saveZc()
      const r = await api.zoteroSync({ topic: activeTopic })
      setZResult(r)
      await load()
      toast(`同步完成：新增 ${r.added} / 跳过 ${r.skipped}${r.pdf_downloaded ? ` / PDF ${r.pdf_downloaded}` : ''}${r.pdf_failed ? `（PDF 失败 ${r.pdf_failed}）` : ''}`, r.pdf_failed ? 'err' : 'ok')
    } catch (e: any) { toast(e.message, 'err') }
    finally { setZBusy('') }
  }

  // ---------- PDF 附件 ----------
  const fetchPdf = async (p: Paper) => {
    if (!activeTopic) return
    setPdfBusy(p.id)
    try {
      await api.fetchPaperPdf(activeTopic, p.id)
      toast('PDF 已下载')
      await load()
    } catch (e: any) { toast(e.message, 'err') }
    finally { setPdfBusy('') }
  }

  const importText = async (p: Paper) => {
    if (!activeTopic) return
    setPdfBusy(p.id)
    try {
      const note = await api.importPaperText(activeTopic, p.id)
      toast('全文笔记已导入')
      refreshTree()
      if (note.path) navigate(`/notes?path=${encodeURIComponent(note.path)}`)
    } catch (e: any) { toast(e.message, 'err') }
    finally { setPdfBusy('') }
  }

  return (
    <div className="papers-page">
      <div className="papers-inner">
        <div className="papers-head">
          <h2>文献库</h2>
          <span className="topic-hint">{activeTopic || '未选择主题'}</span>
          <span className="papers-count">{papers.length} 篇</span>
        </div>

        {!activeTopic && <div className="empty-tip"><div className="big">先在左侧选择一个主题</div></div>}

        {activeTopic && (
          <>
            <div className="settings-card">
              <h3>📖 导入书籍 · 读书笔记</h3>
              <div className="desc">
                上传整本 PDF 或 EPUB：解析章节 → AI 逐章生成内容梗概 → 生成《书名》读书笔记（每章梗概 + 你自己的笔记区）。
                PDF 优先按书签分章，无书签的书按整本处理。
              </div>
              <div className="papers-search">
                <input ref={bookFileRef} type="file" accept=".pdf,.epub" style={{ display: 'none' }}
                  onChange={(e) => { const f = e.target.files?.[0]; if (f) importBook(f) }} />
                <button className="btn primary" disabled={importBusy}
                  onClick={() => bookFileRef.current?.click()}>
                  {importBusy ? '解析中…' : '选择 PDF / EPUB 上传'}
                </button>
                <span className="sl-sub" style={{ margin: 0 }}>
                  导入到主题「{activeTopic}」，书目状态（在读/已读）与论文共用一套
                </span>
              </div>
            </div>

            <div className="settings-card">
              <h3>Zotero 同步</h3>
              <div className="desc">
                与桌面 Zotero 共存：桌面端正常收录，这里通过 Zotero Web API 增量拉取条目（去重跳过，不覆盖已有状态）。
                userID 与 API Key 在 zotero.org → Settings → Feeds/API 获取。
              </div>
              {zc && (
                <div className="zotero-form">
                  <input className="text-input" style={{ flex: 1, minWidth: 120 }} placeholder="Zotero userID（数字）"
                    value={zc.user_id} onChange={(e) => setZc({ ...zc, user_id: e.target.value })} />
                  <input className="text-input" style={{ flex: 1, minWidth: 160 }} type="password"
                    placeholder={zc.has_key ? 'API Key 已保存，留空不修改' : 'API Key（只读权限即可）'}
                    value={zc.api_key} onChange={(e) => setZc({ ...zc, api_key: e.target.value })} />
                  <select className="text-input" style={{ flex: 'none', maxWidth: 220 }}
                    value={zc.collection}
                    onChange={(e) => {
                      const c = zCols.find((x) => x.key === e.target.value)
                      setZc({ ...zc, collection: c?.key || '', collection_name: c?.name || '' })
                    }}>
                    <option value="">全部条目</option>
                    {zCols.map((c) => (
                      <option key={c.key} value={c.key}>{c.name}（{c.num_items}）</option>
                    ))}
                  </select>
                  <label className="check-row" style={{ flex: 'none', gap: 6, fontSize: 13 }}>
                    <input type="checkbox" checked={zc.download_pdf}
                      onChange={(e) => setZc({ ...zc, download_pdf: e.target.checked })} />
                    自动下载 arXiv PDF
                  </label>
                  <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                    <button className="btn" disabled={zBusy !== ''} onClick={checkZotero}>
                      {zBusy === 'check' ? '验证中…' : '保存并连接'}
                    </button>
                    <button className="btn primary" disabled={zBusy !== ''} onClick={runSync}
                      title={`增量同步到当前主题「${activeTopic}」`}>
                      {zBusy === 'sync' ? '同步中…' : `同步到「${activeTopic}」`}
                    </button>
                  </div>
                  {zResult && (
                    <div className="sl-sub">
                      上次同步 {zResult.synced_at.slice(0, 16).replace('T', ' ')}：拉取 {zResult.fetched}，
                      新增 {zResult.added}，跳过 {zResult.skipped}，PDF 下载 {zResult.pdf_downloaded}
                      {zResult.pdf_failed ? `，失败 ${zResult.pdf_failed}` : ''}（游标 v{zResult.last_version}）
                    </div>
                  )}
                </div>
              )}
            </div>

            <div className="settings-card">
              <h3>检索 arXiv 收录前沿论文</h3>
              <div className="desc">用英文关键词检索（如 legal AI、LLM agents、court judgment prediction），按提交时间倒序。</div>
              <div className="papers-search">
                <input className="text-input" style={{ flex: 1, minWidth: 0 }} placeholder="英文关键词，回车检索"
                  value={q} onChange={(e) => setQ(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && search()} />
                <button className="btn primary" disabled={searching || !q.trim()} onClick={search}>
                  {searching ? '检索中…' : '检索'}
                </button>
              </div>
              {!!results.length && (
                <div className="arxiv-results">
                  {results.map((r) => (
                    <div key={r.arxiv_id} className="arxiv-item">
                      <div className="arxiv-main">
                        <a className="arxiv-title" href={r.url} target="_blank" rel="noreferrer">{r.title}</a>
                        <div className="arxiv-meta">
                          {r.authors.slice(0, 3).join(', ')}{r.authors.length > 3 ? ' 等' : ''} · {r.year} · arXiv:{r.arxiv_id}
                        </div>
                        <div className="arxiv-abs">{r.abstract.slice(0, 160)}{r.abstract.length > 160 ? '…' : ''}</div>
                      </div>
                      <button className="btn small primary" disabled={adding === r.arxiv_id} onClick={() => collect(r)}>
                        {adding === r.arxiv_id ? '收录中…' : '收录'}
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="settings-card">
              <div className="papers-lib-head">
                <h3 style={{ margin: 0 }}>已收录</h3>
                <div className="papers-filters">
                  {(['all', 'unread', 'reading', 'done'] as const).map((f) => (
                    <button key={f} className={`chip-btn ${filter === f ? 'on' : ''}`} onClick={() => setFilter(f)}>
                      {f === 'all' ? '全部' : STATUS[f].label}
                    </button>
                  ))}
                  <input className="text-input" style={{ width: 160 }} placeholder="筛选标题/作者/标签"
                    value={textFilter} onChange={(e) => setTextFilter(e.target.value)} />
                </div>
              </div>
              {loading && <div className="sl-sub">加载中…</div>}
              {!loading && !shown.length && (
                <div className="sl-sub">还没有文献——用上面的检索收录一些前沿论文吧。</div>
              )}
              {shown.map((p) => (
                <div key={p.id} className="paper-row">
                  <button className={`status-chip ${p.status}`} title="点击切换：未读 → 在读 → 已读"
                    onClick={() => cycleStatus(p)}>{STATUS[p.status]?.label || p.status}</button>
                  <div className="paper-main">
                    {p.url
                      ? <a className="paper-title" href={p.url} target="_blank" rel="noreferrer">{p.title}</a>
                      : <span className="paper-title">{p.kind === 'book' ? `📖 ${p.title}` : p.title}</span>}
                    <div className="paper-meta">
                      {p.kind === 'book' && '书籍'}
                      {p.kind !== 'book' && p.authors.slice(0, 3).join(', ')}
                      {p.kind !== 'book' && p.authors.length > 3 ? ' 等' : ''}
                      {p.year && ` · ${p.year}`}{p.venue && ` · ${p.venue}`}
                      {p.arxiv_id && ` · arXiv:${p.arxiv_id}`}
                    </div>
                    {p.abstract && p.kind !== 'book' && (
                      <div className="paper-abs">{p.abstract.slice(0, 120)}{p.abstract.length > 120 ? '…' : ''}</div>
                    )}
                    {p.comment && <div className="paper-comment">💭 {p.comment}</div>}
                    {genProgress[p.id] && (
                      <div className="paper-comment">
                        ⏳ 生成梗概中 {genProgress[p.id].done}/{genProgress[p.id].total || '…'}
                        ：{genProgress[p.id].label}
                      </div>
                    )}
                    <div className="paper-acts">
                      {p.kind === 'book' ? (
                        <button className="btn text small" disabled={!p.book_id || !!genProgress[p.id]}
                          title="逐章生成内容梗概，落盘为《书名》读书笔记（每章梗概 + 自己的笔记区）"
                          onClick={() => genBookNotes(p)}>
                          {genProgress[p.id] ? '⏳ 生成中…' : '✦ 生成读书笔记'}
                        </button>
                      ) : (
                        <button className="btn text small" disabled={noteBusy === p.id}
                          title="按论文元数据生成阅读笔记，保存到主题的「文献」目录"
                          onClick={() => genNote(p)}>✦ 生成阅读笔记</button>
                      )}
                      {p.kind !== 'book' && (p.pdf_path ? (
                        <>
                          <a className="btn text small" href={`/api/papers/${encodeURIComponent(p.id)}/pdf?topic=${encodeURIComponent(activeTopic || '')}`}
                            target="_blank" rel="noreferrer">📄 打开 PDF</a>
                          <button className="btn text small" disabled={pdfBusy === p.id}
                            title="把 PDF 全文导入为主题「文献」目录下的笔记"
                            onClick={() => importText(p)}>📥 导入全文笔记</button>
                        </>
                      ) : p.arxiv_id ? (
                        <button className="btn text small" disabled={pdfBusy === p.id}
                          title="从 arxiv.org 下载 PDF 附件"
                          onClick={() => fetchPdf(p)}>📄 下载 PDF</button>
                      ) : null)}
                      <button className="btn text small" onClick={() => {
                        const c = window.prompt('这条文献的想法/批注：', p.comment || '')
                        if (c === null || !activeTopic) return
                        api.updatePaper(activeTopic, p.id, { comment: c })
                          .then(load).catch((e: any) => toast(e.message, 'err'))
                      }}>💭 想法</button>
                      <button className="btn text small danger" onClick={() => remove(p)}>
                        <IconTrash size={13} /> 移除
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  )
}
