import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useEffect, useState } from 'react'
import Sidebar from './components/Sidebar'
import TopBar from './components/TopBar'
import { useApp } from './store'
import { api } from './api'
import { LogoMark } from './components/Icons'

export default function App() {
  const { toasts } = useApp()
  const location = useLocation()
  const navigate = useNavigate()
  const isGraph = location.pathname.startsWith('/graph')

  // 访问令牌校验：后端设置了 NOTEBOOK_TOKEN 时，401 → 显示令牌输入页
  const [authState, setAuthState] = useState<'checking' | 'ok' | 'need-token'>('checking')
  useEffect(() => {
    api.settings()
      .then(() => setAuthState('ok'))
      .catch((e: & { code?: number }) => setAuthState(e?.code === 401 ? 'need-token' : 'ok'))
  }, [])

  if (authState === 'checking') return null
  if (authState === 'need-token') return <TokenGate />

  // 快捷键：n 笔记 / g 图谱 / e 考试 / s 设置
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA' || (e.target as HTMLElement)?.isContentEditable) return
      const map: Record<string, string> = { n: '/notes', g: '/graph', e: '/exam', s: '/settings' }
      const to = map[e.key]
      if (to && !e.metaKey && !e.ctrlKey && !e.altKey) navigate(to)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [navigate])

  return (
    <div className="app">
      <Sidebar />
      <div className="main">
        <TopBar />
        <div className="page-scroll" style={isGraph ? { display: 'flex', flexDirection: 'column' } : undefined}>
          <Outlet />
        </div>
      </div>
      <div className="toast-wrap">
        {toasts.map((t) => (
          <div key={t.id} className={`toast ${t.kind}`}>{t.text}</div>
        ))}
      </div>
    </div>
  )
}

function TokenGate() {
  const [value, setValue] = useState('')
  const [err, setErr] = useState('')
  const submit = async () => {
    localStorage.setItem('nl-token', value.trim())
    try {
      await api.settings()
      window.location.reload()
    } catch {
      setErr('令牌不对，请重试')
      localStorage.removeItem('nl-token')
    }
  }
  return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'var(--side-bg)' }}>
      <div style={{ background: '#fff', border: '1px solid var(--border)', borderRadius: 18, padding: '36px 40px', width: 360, textAlign: 'center' }}>
        <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 12 }}><LogoMark size={40} /></div>
        <div style={{ fontSize: 18, fontWeight: 700, marginBottom: 6 }}>墨链 NoteLink</div>
        <div style={{ color: 'var(--muted)', fontSize: 13, marginBottom: 18 }}>此服务已开启访问保护，请输入访问令牌</div>
        <input
          className="text-input"
          style={{ width: '100%', textAlign: 'center' }}
          type="password"
          placeholder="访问令牌"
          value={value}
          autoFocus
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && submit()}
        />
        {err && <div style={{ color: 'var(--err)', fontSize: 12.5, marginTop: 8 }}>{err}</div>}
        <button className="btn primary" style={{ width: '100%', justifyContent: 'center', marginTop: 14 }} onClick={submit}>进入</button>
      </div>
    </div>
  )
}
