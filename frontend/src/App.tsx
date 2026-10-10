import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useEffect } from 'react'
import Sidebar from './components/Sidebar'
import TopBar from './components/TopBar'
import { useApp } from './store'

export default function App() {
  const { toasts } = useApp()
  const location = useLocation()
  const navigate = useNavigate()
  const isGraph = location.pathname.startsWith('/graph')

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
