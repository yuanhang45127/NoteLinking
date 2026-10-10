import { useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { api } from '../api'
import { useApp } from '../store'
import { IconBell, IconSearch } from './Icons'

export default function TopBar() {
  const { activeTopic } = useApp()
  const location = useLocation()
  const navigate = useNavigate()
  const params = new URLSearchParams(location.search)
  const path = params.get('path') || ''

  const parts: { label: string; to?: string }[] = []
  if (location.pathname.startsWith('/notes') || location.pathname === '/') {
    parts.push({ label: '笔记' })
    if (path) {
      const segs = path.split('/')
      segs.forEach((seg, i) => {
        if (i === segs.length - 1) parts.push({ label: seg })
        else if (i === 0) parts.push({ label: seg })
        else parts.push({ label: seg })
      })
    } else if (activeTopic) parts.push({ label: activeTopic })
  } else if (location.pathname.startsWith('/concept')) {
    parts.push({ label: '笔记', to: '/notes' })
    if (path) {
      const segs = path.split('/')
      parts.push({ label: segs.slice(1, -1).filter((s) => s !== 'terms').join(' / ') || segs[0] })
      parts.push({ label: segs[segs.length - 1], cur: true } as any)
    }
  } else if (location.pathname.startsWith('/graph')) {
    parts.push({ label: '知识图谱' })
    if (activeTopic) parts.push({ label: activeTopic, cur: true } as any)
  } else if (location.pathname.startsWith('/exam')) {
    parts.push({ label: '考试备考' })
    if (activeTopic) parts.push({ label: activeTopic, cur: true } as any)
  } else if (location.pathname.startsWith('/settings')) {
    parts.push({ label: '设置' })
    const tab = params.get('tab')
    const names: Record<string, string> = { general: '通用', reader: '阅读与高亮', model: 'AI 模型', graph: '双链与图谱', io: '导入与导出' }
    if (tab && names[tab]) parts.push({ label: names[tab], cur: true } as any)
  }

  return (
    <header className="topbar">
      <nav className="crumb">
        {parts.map((p, i) => (
          <span key={i} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            {i > 0 && <span className="sep">/</span>}
            {p.to ? (
              <a onClick={(e) => { e.preventDefault(); navigate(p.to!) }} href={p.to}>{p.label}</a>
            ) : (
              <span className={'cur' in p && (p as any).cur ? 'cur' : ''}>{p.label}</span>
            )}
          </span>
        ))}
      </nav>
      <div className="spacer" />
      <SearchBox />
      <button className="bell" title="通知"><IconBell /><span className="dot" /></button>
      <div className="avatar" title="刘">刘</div>
    </header>
  )
}

function SearchBox() {
  const { activeTopic } = useApp()
  const [q, setQ] = useState('')
  const [results, setResults] = useState<{ path: string; title: string; snippet: string }[]>([])
  const [open, setOpen] = useState(false)
  const navigate = useNavigate()
  const boxRef = useRef<HTMLDivElement>(null)
  const timer = useRef<number>()

  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (!boxRef.current?.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [])

  const onChange = (v: string) => {
    setQ(v)
    window.clearTimeout(timer.current)
    if (!v.trim()) { setOpen(false); setResults([]); return }
    timer.current = window.setTimeout(async () => {
      try {
        const { results } = await api.search(v, activeTopic)
        setResults(results.slice(0, 10))
        setOpen(true)
      } catch { /* ignore */ }
    }, 250)
  }

  const jump = async (r: { path: string }) => {
    setOpen(false); setQ('')
    try {
      const note = await api.resolveLink(r.path.split('/').pop()!.replace(/\.md$/, ''), activeTopic)
        .catch(() => null)
      if (note?.type === 'term') navigate(`/concept?path=${encodeURIComponent(r.path)}`)
      else navigate(`/notes?path=${encodeURIComponent(r.path)}`)
    } catch {
      navigate(`/notes?path=${encodeURIComponent(r.path)}`)
    }
  }

  return (
    <div className="search" ref={boxRef}>
      <span className="s-icon"><IconSearch size={16} /></span>
      <input placeholder="搜索笔记、概念..." value={q} onChange={(e) => onChange(e.target.value)}
        onFocus={() => results.length && setOpen(true)} />
      {open && (
        <div className="search-results">
          {results.map((r) => (
            <button key={r.path} className="sr" onClick={() => jump(r)}>
              <div className="t">{r.title}</div>
              <div className="s">{r.snippet}</div>
            </button>
          ))}
          {!results.length && <div className="none">没有匹配的笔记</div>}
        </div>
      )}
    </div>
  )
}
