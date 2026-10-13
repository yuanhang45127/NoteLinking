// 右侧悬浮 AI 对话抽屉：右缘常驻《《把手，点击滑出/收起；顶栏可新建、切换、删除对话。
// 开启 Kimi Code 集成后顶栏多出「Kimi Code」标签：iframe 嵌入本机 kimi web（KimiWebPane）。
// 开关状态在 chatDockSignal（模块级信号，useSyncExternalStore 订阅）。
import { useCallback, useEffect, useState, useSyncExternalStore } from 'react'
import { api } from '../api'
import ChatConversation from './chat/ChatConversation'
import KimiWebPane from './chat/KimiWebPane'
import { chatDock } from './chat/chatDockSignal'
import { IconClose } from './Icons'
import type { ChatSessionMeta } from '../types'

export default function ChatDock() {
  const open = useSyncExternalStore(chatDock.subscribe, chatDock.get)
  const [sessions, setSessions] = useState<ChatSessionMeta[]>([])
  const [activeId, setActiveId] = useState<string | null>(null)
  const [tab, setTab] = useState<'chat' | 'kimi'>('chat')
  const [kimiOn, setKimiOn] = useState(false)

  const refresh = useCallback(async () => {
    try {
      const r = await api.chatSessions()
      setSessions(r.sessions)
      setActiveId((cur) => (cur && r.sessions.some((s) => s.id === cur) ? cur : r.sessions[0]?.id || null))
    } catch { /* 面板场景静默 */ }
  }, [])

  // 挂载即预取会话列表：让 activeId 在首次引用/展开前就稳定，
  // 避免「null → 首个会话」的切换触发对话组件清空刚加入的引用上下文
  useEffect(() => { refresh() }, [refresh])

  // 探测是否开启 Kimi Code 集成（决定 Kimi 标签是否显示）
  useEffect(() => {
    ;(async () => {
      try { setKimiOn((await api.kimiWebStatus()).enabled) } catch { /* 面板场景静默 */ }
    })()
  }, [])

  // 展开时若库里还没有任何会话，自动建一个，保证面板开箱可聊
  useEffect(() => {
    if (!open || activeId) return
    ;(async () => {
      try {
        const r = await api.chatSessions()
        if (r.sessions.length === 0) {
          const s = await api.createChatSession()
          await refresh()
          setActiveId(s.id)
        } else {
          setActiveId(r.sessions[0].id)
        }
      } catch { /* ignore */ }
    })()
  }, [open, activeId, refresh])

  const newSession = async () => {
    try {
      const s = await api.createChatSession()
      await refresh()
      setActiveId(s.id)
    } catch { /* ignore */ }
  }

  // 删除（关闭）当前对话：确认后删除，自动切到剩余最近对话；全删光则由挂载逻辑补一个空白会话
  const removeSession = async () => {
    if (!activeId) return
    if (!window.confirm('删除这个对话？聊天记录不可恢复。')) return
    try {
      await api.deleteChatSession(activeId)
      setActiveId(null)
      await refresh()
    } catch { /* ignore */ }
  }

  return (
    <>
      <button
        className={`chat-dock-handle ${open ? 'open' : ''}`}
        title={open ? '收起 AI 对话' : 'AI 对话'}
        onClick={() => chatDock.toggle()}
      >
        {open ? '》》' : '《《'}
      </button>
      <aside className={`chat-dock ${open ? 'open' : ''}`} aria-hidden={!open}>
        <div className="dock-head">
          {kimiOn ? (
            <div className="dock-tabs" role="tablist">
              <button role="tab" className={tab === 'chat' ? 'cur' : ''} onClick={() => setTab('chat')}>AI 对话</button>
              <button role="tab" className={tab === 'kimi' ? 'cur' : ''} onClick={() => setTab('kimi')}>Kimi Code</button>
            </div>
          ) : (
            <span className="dock-title">AI 对话</span>
          )}
          {tab === 'chat' && (
            <>
              <select
                className="select-input dock-sessions"
                value={activeId || ''}
                onChange={(e) => setActiveId(e.target.value || null)}
              >
                {sessions.length === 0 && <option value="">（还没有对话）</option>}
                {sessions.map((s) => <option key={s.id} value={s.id}>{s.title}</option>)}
              </select>
              <button className="bell" title="新对话" onClick={newSession}>＋</button>
              <button className="bell" title="删除当前对话" disabled={!activeId} onClick={removeSession}>🗑</button>
            </>
          )}
          <button className="bell" title="收起" onClick={() => chatDock.set(false)}><IconClose size={16} /></button>
        </div>
        {/* 两页都保持挂载（display 切换），切到 Kimi Code 不打断进行中的对话流 */}
        <div className="dock-body">
          <div className="dock-tab-page" style={tab === 'chat' ? undefined : { display: 'none' }}>
            <ChatConversation sessionId={activeId} compact onSessionUpdated={refresh} />
          </div>
          {kimiOn && (
            <div className="dock-tab-page" style={tab === 'kimi' ? undefined : { display: 'none' }}>
              <KimiWebPane />
            </div>
          )}
        </div>
      </aside>
    </>
  )
}
