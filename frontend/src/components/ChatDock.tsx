// 右侧悬浮 AI 对话抽屉：右缘常驻《《把手，点击滑出/收起；顶栏可新建、切换、删除对话。
// 开关状态在 chatDockSignal（模块级信号，useSyncExternalStore 订阅）。
import { useCallback, useEffect, useState, useSyncExternalStore } from 'react'
import { api } from '../api'
import ChatConversation from './chat/ChatConversation'
import { chatDock } from './chat/chatDockSignal'
import { IconClose } from './Icons'
import type { ChatSessionMeta } from '../types'

export default function ChatDock() {
  const open = useSyncExternalStore(chatDock.subscribe, chatDock.get)
  const [sessions, setSessions] = useState<ChatSessionMeta[]>([])
  const [activeId, setActiveId] = useState<string | null>(null)

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
          <span className="dock-title">AI 对话</span>
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
          <button className="bell" title="收起" onClick={() => chatDock.set(false)}><IconClose size={16} /></button>
        </div>
        <div className="dock-body">
          <ChatConversation sessionId={activeId} compact onSessionUpdated={refresh} />
        </div>
      </aside>
    </>
  )
}
