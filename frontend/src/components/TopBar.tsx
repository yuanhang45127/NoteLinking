import { useEffect, useRef, useState, useSyncExternalStore } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { api, getModelOverride, setModelOverride } from '../api'
import { useApp } from '../store'
import { IconBell, IconChat, IconSearch } from './Icons'
import { chatDock } from './chat/chatDockSignal'
import { openAuthGate } from './authGateSignal'
import type { Provider } from '../types'

export default function TopBar({ onToggleSidebar }: { onToggleSidebar?: () => void }) {
  const { activeTopic, topics } = useApp()
  const dockOpen = useSyncExternalStore(chatDock.subscribe, chatDock.get)
  const location = useLocation()
  const navigate = useNavigate()
  const params = new URLSearchParams(location.search)
  const path = params.get('path') || ''
  const topicEmoji = (name: string) => topics.find((t) => t.name === name)?.emoji || ''
  const label = (name: string) => {
    const e = topicEmoji(name)
    return e ? `${e} ${name}` : name
  }

  const parts: { label: string; to?: string; cur?: boolean }[] = []
  const stripMd = (s: string) => s.replace(/\.md$/i, '')  // 面包屑里不显示 .md 后缀
  if (location.pathname.startsWith('/notes') || location.pathname === '/') {
    parts.push({ label: '笔记' })
    if (path) {
      const segs = path.split('/')
      segs.forEach((seg, i) => {
        if (i === segs.length - 1) parts.push({ label: stripMd(seg), cur: true })
        else if (i === 0) parts.push({ label: label(stripMd(seg)) })
        else parts.push({ label: stripMd(seg) })
      })
    } else if (activeTopic) parts.push({ label: label(activeTopic) })
  } else if (location.pathname.startsWith('/concept')) {
    parts.push({ label: '笔记', to: '/notes' })
    if (path) {
      const segs = path.split('/')
      parts.push({ label: label(stripMd(segs[0])) })
      parts.push({ label: stripMd(segs[segs.length - 1]), cur: true })
    }
  } else if (location.pathname.startsWith('/graph')) {
    parts.push({ label: '知识图谱' })
    if (activeTopic) parts.push({ label: label(activeTopic), cur: true })
  } else if (location.pathname.startsWith('/exam')) {
    parts.push({ label: '考试备考' })
    if (activeTopic) parts.push({ label: label(activeTopic), cur: true })
  } else if (location.pathname.startsWith('/settings')) {
    parts.push({ label: '设置' })
    const tab = params.get('tab')
    const names: Record<string, string> = { general: '通用', topics: '主题管理', reader: '阅读与高亮', model: 'AI 模型', graph: '双链与图谱', io: '导入与导出' }
    if (tab && names[tab]) parts.push({ label: names[tab], cur: true })
  } else if (location.pathname.startsWith('/guide')) {
    parts.push({ label: '新手指引' })
  }

  return (
    <header className="topbar">
      <button
        className="sidebar-toggle"
        aria-label="打开导航"
        title="打开导航"
        onClick={onToggleSidebar}
      >
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
          <path d="M4 6h16M4 12h16M4 18h16" />
        </svg>
      </button>
      <nav className="crumb">
        {parts.map((p, i) => (
          <span key={i} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            {i > 0 && <span className="sep">/</span>}
            {p.to ? (
              <a onClick={(e) => { e.preventDefault(); navigate(p.to!) }} href={p.to}>{p.label}</a>
            ) : (
              <span className={p.cur ? 'cur' : ''}>{p.label}</span>
            )}
          </span>
        ))}
      </nav>
      <div className="spacer" />
      <button
        className="bell"
        title={dockOpen ? '收起 AI 对话' : 'AI 对话（侧边面板）'}
        onClick={() => chatDock.toggle()}
      >
        <IconChat />
      </button>
      <ModelPicker />
      <SearchBox />
      <button className="bell" title="通知"><IconBell /><span className="dot" /></button>
      <UserMenu />
    </header>
  )
}

/* ---------------- 账号菜单 ---------------- */
function UserMenu() {
  const { user, authReady } = useApp()
  const [open, setOpen] = useState(false)
  const boxRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (!boxRef.current?.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [])

  // 鉴权检查完成前不渲染；之后一直显示（登录用户=退出入口，开放模式=注册/登录入口）
  if (!authReady) return null
  const isDefault = !user || user === 'default' // 单人开放模式：数据在默认账户
  const initial = isDefault ? '·' : (Array.from(user)[0] || '?')

  const logout = async () => {
    try { await api.logout() } catch { /* 会话可能已过期 */ }
    window.location.reload()
  }

  return (
    <div style={{ position: 'relative' }} ref={boxRef}>
      <button
        className={`avatar ${isDefault ? 'anon' : ''}`}
        style={{ border: 'none', cursor: 'pointer', padding: 0 }}
        title={isDefault ? '单人开放模式 · 点击注册账号' : `${user} · 账号`}
        onClick={() => setOpen((v) => !v)}
      >
        {initial}
      </button>
      {open && (
        <div className="sel-popover" style={{ right: 0, top: 'calc(100% + 8px)', minWidth: 180 }}>
          {isDefault ? (
            <>
              <div className="hint" style={{ marginBottom: 10 }}>
                <div style={{ fontWeight: 600, color: 'var(--text)', fontSize: 13 }}>单人开放模式</div>
                <div style={{ marginTop: 2 }}>数据存于默认账户；注册后进入多用户隔离</div>
              </div>
              <button className="btn primary" style={{ width: '100%', justifyContent: 'center' }}
                onClick={() => { setOpen(false); openAuthGate() }}>
                注册 / 登录
              </button>
            </>
          ) : (
            <>
              <div className="hint" style={{ marginBottom: 10 }}>
                <div style={{ fontWeight: 600, color: 'var(--text)', fontSize: 13 }}>{user}</div>
                <div style={{ marginTop: 2 }}>数据与此账号隔离存储</div>
              </div>
              <button className="btn" style={{ width: '100%', justifyContent: 'center' }} onClick={logout}>退出登录</button>
            </>
          )}
        </div>
      )}
    </div>
  )
}

/* ---------------- 全局模型选择器 ---------------- */
function ModelPicker() {
  const { settings } = useApp()
  const [, setVer] = useState(0) // 选择后强制刷新显示
  const providers = (settings?.providers || []).filter(
    (p: Provider) => (p.models && p.models.length) || p.model,
  )
  if (!providers.length) return null

  const cur = getModelOverride()
  const curValue = cur.model ? `${cur.provider || ''}::${cur.model}` : ''

  const options: { value: string; label: string; group?: string }[] = []
  for (const p of providers) {
    const g = p.name || p.id
    const seen = new Set<string>()
    if (p.model) { seen.add(p.model); options.push({ value: `${p.id}::${p.model}`, label: `${p.model}（默认）`, group: g }) }
    for (const m of p.models || []) {
      if (seen.has(m)) continue
      seen.add(m)
      options.push({ value: `${p.id}::${m}`, label: m, group: g })
    }
  }
  // 当前选择可能来自已被删除的服务商/模型，仍要显示出来避免 select 跳回默认
  if (curValue && !options.some((o) => o.value === curValue)) {
    options.unshift({ value: curValue, label: cur.model! })
  }
  const curLabel = curValue ? (options.find((o) => o.value === curValue)?.label || cur.model!) : '默认模型'

  return (
    <select
      className="select-input model-picker"
      title={curValue ? `选择 AI 模型（对所有 AI 功能生效）\n当前：${curLabel}` : '选择 AI 模型（对所有 AI 功能生效）'}
      value={curValue}
      onChange={(e) => {
        const v = e.target.value
        if (!v) setModelOverride('', '')
        else {
          const idx = v.indexOf('::')
          setModelOverride(v.slice(0, idx), v.slice(idx + 2))
        }
        setVer((x) => x + 1)
      }}
    >
      <option value="">默认模型</option>
      {options.map((o) => (
        <option key={o.value} value={o.value}>{o.group ? `${o.group} · ${o.label}` : o.label}</option>
      ))}
    </select>
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
