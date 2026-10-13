import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useCallback, useEffect, useState } from 'react'
import Sidebar from './components/Sidebar'
import TopBar from './components/TopBar'
import ChatDock from './components/ChatDock'
import LoginGate from './components/LoginGate'
import AiTaskFloat from './components/AiTaskFloat'
import { useApp } from './store'
import { api } from './api'
import { chatDock } from './components/chat/chatDockSignal'
import { AUTH_GATE_EVENT } from './components/authGateSignal'
import { LogoMark } from './components/Icons'

type Gate = 'checking' | 'login' | 'token' | 'ok'

export default function App() {
  const { toasts, setUser, setAuthReady } = useApp()
  const [gate, setGate] = useState<Gate>('checking')
  const location = useLocation()
  const navigate = useNavigate()
  const isGraph = location.pathname.startsWith('/graph')
  // 窄屏下侧边栏抽屉的开关（宽屏由 CSS 忽略，常驻显示）
  const [sidebarOpen, setSidebarOpen] = useState(false)

  // 路由变化后自动收起抽屉
  useEffect(() => {
    setSidebarOpen(false)
  }, [location.pathname, location.search])

  const proceed = useCallback(() => {
    setAuthReady(true)
    setGate('ok')
  }, [setAuthReady])

  // 鉴权检查（两道门，按顺序）：
  // 1. 账号门：多用户模式下未登录 → 登录/注册页；
  // 2. 部署令牌门：后端设置了 NOTEBOOK_TOKEN 且未提供 → 令牌输入页。
  // 单人开放模式（还没人注册）直接放行，与旧版行为一致。
  useEffect(() => {
    let cancelled = false
    api.authStatus()
      .then(async (s) => {
        if (cancelled) return
        if (s.mode === 'multi' && !s.user) { setGate('login'); return }
        setUser(s.user)
        try {
          await api.settings()
          if (!cancelled) proceed()
        } catch (e: any) {
          if (!cancelled) setGate(e?.code === 401 ? 'token' : 'ok')
        }
      })
      .catch(() => { if (!cancelled) proceed() }) // 后端不可达：照常进入，由页面自行提示
    return () => { cancelled = true }
  }, [proceed, setUser])

  // 快捷键：n 笔记 / g 图谱 / e 考试 / s 设置 / c AI 对话面板
  // 注意：必须放在条件 return 之前，否则 hooks 顺序会随 gate 变化（React #310）
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA' || (e.target as HTMLElement)?.isContentEditable) return
      if (e.key === 'c' && !e.metaKey && !e.ctrlKey && !e.altKey) { chatDock.toggle(); return }
      const map: Record<string, string> = { n: '/notes', g: '/graph', e: '/exam', s: '/settings' }
      const to = map[e.key]
      if (to && !e.metaKey && !e.ctrlKey && !e.altKey) navigate(to)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [navigate])

  // 顶栏「注册 / 登录」入口（单人开放模式）：事件驱动打开认证门
  useEffect(() => {
    const onOpen = () => setGate('login')
    window.addEventListener(AUTH_GATE_EVENT, onOpen)
    return () => window.removeEventListener(AUTH_GATE_EVENT, onOpen)
  }, [])

  if (gate === 'checking') return null
  if (gate === 'login') {
    return (
      <LoginGate
        onOk={(u) => { setUser(u); proceed() }}
      />
    )
  }
  if (gate === 'token') return <TokenGate onOk={proceed} />

  return (
    <div className={`app${sidebarOpen ? ' sidebar-open' : ''}`}>
      <Sidebar />
      <div className="sidebar-backdrop" onClick={() => setSidebarOpen(false)} />
      <div className="main">
        <TopBar onToggleSidebar={() => setSidebarOpen((v) => !v)} />
        <div className="page-scroll" style={isGraph ? { display: 'flex', flexDirection: 'column' } : undefined}>
          <Outlet />
        </div>
      </div>
      <ChatDock />
      <AiTaskFloat />
      <div className="toast-wrap">
        {toasts.map((t) => (
          <div key={t.id} className={`toast ${t.kind}`}>{t.text}</div>
        ))}
      </div>
    </div>
  )
}

function TokenGate({ onOk }: { onOk: () => void }) {
  const [value, setValue] = useState('')
  const [err, setErr] = useState('')
  const submit = async () => {
    localStorage.setItem('nl-token', value.trim())
    try {
      await api.settings()
      onOk()
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
