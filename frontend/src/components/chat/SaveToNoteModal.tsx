// 把对话内容存入笔记：追加到已有笔记（可搜索）或新建一篇。
// 「存为笔记」（整条回答）与「存入笔记」（圈选片段）共用。
import { useEffect, useRef, useState } from 'react'
import { api } from '../../api'
import { useApp } from '../../store'
import Modal from '../Modal'

export default function SaveToNoteModal({ content, onClose, toast }: {
  content: string
  onClose: () => void
  toast: (t: string, k?: 'ok' | 'err') => void
}) {
  const { topics } = useApp()
  const [mode, setMode] = useState<'append' | 'create'>('append')
  const [busy, setBusy] = useState(false)

  // 追加模式
  const [q, setQ] = useState('')
  const [results, setResults] = useState<{ path: string; title: string }[]>([])
  const [target, setTarget] = useState<{ path: string; title: string } | null>(null)
  const [heading, setHeading] = useState('')

  // 新建模式
  const [title, setTitle] = useState('')
  const [topic, setTopic] = useState(topics[0]?.name || '')

  const searchRef = useRef<number>()
  useEffect(() => {
    window.clearTimeout(searchRef.current)
    if (!q.trim()) { setResults([]); return }
    searchRef.current = window.setTimeout(async () => {
      try {
        const r = await api.search(q.trim())
        setResults(r.results.slice(0, 8))
      } catch { setResults([]) }
    }, 250)
    return () => window.clearTimeout(searchRef.current)
  }, [q])

  const submit = async () => {
    setBusy(true)
    const stamped = `> 摘自 AI 对话 · ${new Date().toLocaleDateString('zh-CN')}\n\n${content.trim()}\n`
    try {
      if (mode === 'append') {
        if (!target) return
        await api.appendToNote(target.path, stamped, heading.trim())
        toast(`已存入「${target.title}」`)
      } else {
        const t = title.trim() || 'AI 对话笔记'
        const path = `${topic}/${t}.md`
        await api.createNote(path, `# ${t}\n\n${stamped}`)
        toast(`已创建「${t}」`)
      }
      onClose()
    } catch (e: any) {
      toast(e.message || '保存失败', 'err')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal title="存入笔记" onClose={onClose} wide
      ops={
        <>
          <button className="btn" onClick={onClose}>取消</button>
          <button className="btn primary" disabled={busy || (mode === 'append' ? !target : !topic || !title.trim())}
            onClick={submit}>
            {busy ? '保存中…' : mode === 'append' ? '追加到笔记' : '新建笔记'}
          </button>
        </>
      }>
      <div className="save-tabs">
        <button className={`save-tab ${mode === 'append' ? 'active' : ''}`} onClick={() => setMode('append')}>追加到已有笔记</button>
        <button className={`save-tab ${mode === 'create' ? 'active' : ''}`} onClick={() => setMode('create')}>新建笔记</button>
      </div>

      {mode === 'append' ? (
        <>
          <input className="text-input" style={{ width: '100%', marginTop: 12 }} placeholder="搜索笔记标题或内容…"
            value={q} autoFocus onChange={(e) => { setQ(e.target.value); setTarget(null) }} />
          {target && (
            <div className="hint" style={{ marginTop: 8 }}>将存入：<b>{target.title}</b>（{target.path}）</div>
          )}
          {!target && results.length > 0 && (
            <div className="save-results">
              {results.map((r) => (
                <button key={r.path} className="save-result" onClick={() => { setTarget(r); setQ(r.title) }}>
                  <span className="name">{r.title}</span>
                  <span className="path">{r.path}</span>
                </button>
              ))}
            </div>
          )}
          <input className="text-input" style={{ width: '100%', marginTop: 10 }} placeholder="小节标题（可选，如「AI 补充」）"
            value={heading} onChange={(e) => setHeading(e.target.value)} />
        </>
      ) : (
        <>
          <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
            <select className="select-input" value={topic} onChange={(e) => setTopic(e.target.value)}>
              {topics.map((t) => <option key={t.name} value={t.name}>{t.emoji ? `${t.emoji} ` : ''}{t.name}</option>)}
            </select>
            <input className="text-input" style={{ flex: 1 }} placeholder="笔记标题" value={title} autoFocus
              onChange={(e) => setTitle(e.target.value)} />
          </div>
          <div className="hint" style={{ marginTop: 8 }}>
            将新建 <b>{topic}/{title.trim() || 'AI 对话笔记'}.md</b>（已存在同名笔记时会提示）
          </div>
        </>
      )}

      <div className="save-preview">{content.length > 400 ? content.slice(0, 400) + '…' : content}</div>
    </Modal>
  )
}
