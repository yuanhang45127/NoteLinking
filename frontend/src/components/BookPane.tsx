// 原书对照分栏：读书笔记右侧并排展示原书内容。
// PDF 书：iframe 直读原文件；EPUB：按章节拉净化 HTML 渲染（上一章/下一章 + 章节跳转）。
import { useEffect, useState } from 'react'
import { api } from '../api'
import { IconClose } from './Icons'

export default function BookPane({ bookId, fmt, onClose }: {
  bookId: string
  fmt: string
  onClose: () => void
}) {
  const isPdf = fmt === 'pdf'
  const [chapters, setChapters] = useState<{ title: string; chars: number }[]>([])
  const [idx, setIdx] = useState(0)
  const [html, setHtml] = useState('')
  const [loading, setLoading] = useState(false)
  const [err, setErr] = useState('')

  useEffect(() => {
    api.getBook(bookId).then((r) => setChapters(r.chapters)).catch((e) => setErr(e.message))
  }, [bookId])

  useEffect(() => {
    if (isPdf) return
    setLoading(true); setErr('')
    api.getBookChapter(bookId, idx)
      .then((r) => setHtml(r.html))
      .catch((e) => setErr(e.message))
      .finally(() => setLoading(false))
  }, [bookId, idx, isPdf])

  return (
    <div className="pdf-pane">
      <div className="pdf-pane-head">
        <span className="pdf-pane-title">📖 原书对照</span>
        {!isPdf && chapters.length > 0 && (
          <>
            <select className="select-input" style={{ fontSize: 12.5, padding: '3px 6px', maxWidth: 200 }}
              value={idx} onChange={(e) => setIdx(Number(e.target.value))}>
              {chapters.map((c, i) => <option key={i} value={i}>{i + 1}. {c.title}</option>)}
            </select>
            <button className="btn text small" disabled={idx <= 0} onClick={() => setIdx((i) => Math.max(0, i - 1))}>上一章</button>
            <button className="btn text small" disabled={idx >= chapters.length - 1}
              onClick={() => setIdx((i) => Math.min(chapters.length - 1, i + 1))}>下一章</button>
          </>
        )}
        <span style={{ flex: 1 }} />
        {isPdf && (
          <a className="btn text small" href={`/api/books/${encodeURIComponent(bookId)}/file`}
            target="_blank" rel="noreferrer">新窗口打开</a>
        )}
        <button className="btn text small" onClick={onClose}>收起</button>
        <button className="bell" title="关闭" onClick={onClose}><IconClose size={15} /></button>
      </div>
      {isPdf ? (
        <iframe className="pdf-frame" src={`/api/books/${encodeURIComponent(bookId)}/file`} title="原书 PDF" />
      ) : (
        <div className="book-frame">
          {loading && <div className="empty-tip"><span className="loading-dot" /></div>}
          {err && <div className="empty-tip">{err}</div>}
          {!loading && !err && (
            <div className="book-content" dangerouslySetInnerHTML={{ __html: html }} />
          )}
        </div>
      )}
    </div>
  )
}
