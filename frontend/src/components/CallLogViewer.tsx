// 设置 → 调用记录：浏览历史调用会话（AI 功能留下的模型 / 工具调用过程），
// 点开条目用 ProcessTimeline 还原当时的完整调用过程。
import { useCallback, useEffect, useRef, useState } from 'react'
import { fetchCallLog, fetchCallLogs } from '../api'
import type { CallLogEntry, CallLogRecord } from '../types'
import ProcessTimeline from './ProcessTimeline'

const PAGE_SIZE = 50

/** 本地时间：2026/10/15 14:30:05 */
function fmtTime(iso: string): string {
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString('zh-CN', { hour12: false })
}

export default function CallLogViewer() {
  const [entries, setEntries] = useState<CallLogEntry[]>([])
  const [q, setQ] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [hasMore, setHasMore] = useState(false)
  const [openId, setOpenId] = useState('')
  const [detail, setDetail] = useState<CallLogRecord | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailError, setDetailError] = useState('')
  const timer = useRef(0)
  // 请求序号：只应用最新一次请求的响应，在途的过期响应一律丢弃（防竞态）
  const loadSeq = useRef(0)
  const detailSeq = useRef(0)

  const load = useCallback(async (offset: number) => {
    const seq = ++loadSeq.current
    setLoading(true)
    try {
      const { entries: page } = await fetchCallLogs({ limit: PAGE_SIZE, offset, q })
      if (seq !== loadSeq.current) return
      setEntries((prev) => (offset === 0 ? page : [...prev, ...page]))
      setHasMore(page.length === PAGE_SIZE)
      setError('')
    } catch (e: any) {
      if (seq !== loadSeq.current) return
      setError(e.message || '加载失败')
    } finally {
      if (seq === loadSeq.current) setLoading(false)
    }
  }, [q])

  // 搜索词变化即重新拉取（防抖 250ms，同顶栏搜索）
  useEffect(() => {
    window.clearTimeout(timer.current)
    timer.current = window.setTimeout(() => { load(0) }, q ? 250 : 0)
    return () => window.clearTimeout(timer.current)
  }, [load])

  const toggle = async (entry: CallLogEntry) => {
    // 折叠：作废在途请求，避免其响应落到已收起的行上
    if (openId === entry.id) {
      detailSeq.current++
      setOpenId('')
      setDetail(null)
      return
    }
    const seq = ++detailSeq.current
    setOpenId(entry.id)
    setDetail(null)
    setDetailError('')
    setDetailLoading(true)
    try {
      const record = await fetchCallLog(entry.id)
      if (seq !== detailSeq.current) return
      setDetail(record)
    } catch (e: any) {
      if (seq !== detailSeq.current) return
      setDetailError(e.message || '加载详情失败')
    } finally {
      if (seq === detailSeq.current) setDetailLoading(false)
    }
  }

  return (
    <div className="settings-card">
      <h3>调用记录</h3>
      <div className="desc">
        AI 功能（生成笔记、AI 对话、考点清单、概念文档等）发起的每次调用都会记录在这里：
        用了哪些模型、调了哪些工具、分几步完成。点击条目可查看完整调用过程。
      </div>

      <div className="call-log-toolbar">
        <input className="text-input" style={{ maxWidth: 300 }} placeholder="搜索流程或用途…"
          value={q} onChange={(e) => setQ(e.target.value)} />
        {q && <button className="btn small text" onClick={() => setQ('')}>清空</button>}
      </div>

      {error && (
        <div className="sl-sub" style={{ color: 'var(--err)' }}>
          {error}
          <button className="btn small text" style={{ marginLeft: 8 }} onClick={() => load(0)}>重试</button>
        </div>
      )}

      {!loading && !entries.length && !error && (
        <div className="call-log-empty">
          <div className="big">暂无调用记录</div>
          <div className="sub">
            {q ? '没有找到匹配的记录，换个关键词试试' : '使用 AI 功能后，调用记录会自动出现在这里'}
          </div>
        </div>
      )}

      {!!entries.length && (
        <div className="call-log-list">
          {entries.map((e) => (
            <div key={e.id} className={`call-log-item ${openId === e.id ? 'open' : ''}`}>
              <button type="button" className="call-log-row" onClick={() => toggle(e)}>
                <span className="cl-time">{fmtTime(e.ts)}</span>
                <span className="cl-flow">{e.flow}</span>
                <span className="cl-purpose" title={e.purpose}>{e.purpose}</span>
                <span className="cl-badges">
                  <span className="tag ghost">模型 {e.llm_calls}</span>
                  <span className="tag ghost">工具 {e.tool_calls}</span>
                  <span className="tag ghost">步骤 {e.steps}</span>
                </span>
                <span className="cl-models" title={e.models.join(' · ')}>{e.models.join(' · ')}</span>
                <span className={`cl-arrow ${openId === e.id ? 'open' : ''}`}>▾</span>
              </button>
              {openId === e.id && (
                <div className="call-log-detail">
                  {detailLoading && <div className="sl-sub">加载中…</div>}
                  {detailError && <div className="sl-sub" style={{ color: 'var(--err)' }}>{detailError}</div>}
                  {detail && <ProcessTimeline events={detail.events} />}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {loading && <div className="sl-sub" style={{ marginTop: 10 }}>加载中…</div>}

      {hasMore && !loading && (
        <button className="btn" style={{ marginTop: 12 }} onClick={() => load(entries.length)}>加载更多</button>
      )}
    </div>
  )
}
