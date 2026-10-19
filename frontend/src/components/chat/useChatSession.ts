// AI 对话会话状态机：滑出面板（ChatDock）使用。
// 负责会话加载、流式收发（delta/llm_*/tool/step 事件）、停止与重新生成。
import { useCallback, useEffect, useRef, useState } from 'react'
import { api, getModelOverride, streamUrls } from '../../api'
import { streamTracked } from '../../lib/aiTasks'
import { chatDock } from './chatDockSignal'
import type { ChatSessionMeta, ChatSessionMsg, LiveMsg, ProcessEvt } from '../../types'

export function useChatSession(sessionId: string | null, onSessionUpdated?: (s: ChatSessionMeta) => void) {
  const [messages, setMessages] = useState<(ChatSessionMsg | LiveMsg)[]>([])
  const [meta, setMeta] = useState<ChatSessionMeta | null>(null)
  const [loading, setLoading] = useState(false)
  const [streaming, setStreaming] = useState(false)
  const [error, setError] = useState('')
  const ctrlRef = useRef<{ abort: () => void } | null>(null)
  // 流式期间累积的 assistant 消息下标，delta/tool 事件都落在它身上
  const idxRef = useRef(-1)

  const load = useCallback(async () => {
    if (!sessionId) { setMessages([]); setMeta(null); return }
    setLoading(true); setError('')
    try {
      const s = await api.chatSession(sessionId)
      setMessages(s.messages)
      setMeta(s)
    } catch (e: any) {
      setError(e.message || '会话加载失败'); setMessages([]); setMeta(null)
    } finally {
      setLoading(false)
    }
  }, [sessionId])

  useEffect(() => { load() }, [load])
  // 卸载或切换会话时中断进行中的流
  useEffect(() => () => ctrlRef.current?.abort(), [sessionId])

  const stop = useCallback(() => {
    ctrlRef.current?.abort()
    setStreaming(false)
    // 中断后局部回答不落库，但保留在界面上，打上未保存标记由最终文案说明
    const i = idxRef.current
    if (i >= 0) setMessages((ms) => ms.map((m, k) => (k === i ? { ...m, content: m.content + '\n\n*（已停止，此段未保存）*' } : m)))
    idxRef.current = -1
  }, [])

  const send = useCallback((content: string, contextPaths: string[] = [], regenerate = false) => {
    if (!sessionId || streaming) return
    setError('')
    setMessages((ms) => {
      const next = regenerate
        ? ms.slice() // 回答已由后端回退，这里只挂一条空的 assistant 消息
        : [...ms, { role: 'user' as const, content, created_at: new Date().toISOString() }]
      idxRef.current = next.length
      return [...next, { role: 'assistant' as const, content: '', tool_steps: [], process: [] }]
    })
    setStreaming(true)
    const patchLast = (fn: (m: LiveMsg) => LiveMsg) =>
      setMessages((ms) => ms.map((m, k) => (k === idxRef.current ? fn(m) : m)))

    const ask = content.trim()
    ctrlRef.current = streamTracked(
      {
        title: ask ? `对话 · ${ask.slice(0, 16)}${ask.length > 16 ? '…' : ''}` : '对话 · 重新生成',
        kind: 'chat',
        foreground: () => chatDock.set(true),
      },
      streamUrls.chatTurn(sessionId),
      { content, context_paths: contextPaths, regenerate, stream: true, ...getModelOverride() },
      {
        onDelta: (text) => patchLast((m) => ({ ...m, content: m.content + text })),          // delta
        onDone: (evt) => {                                                                    // done
          patchLast(() => ({ ...(evt.message as ChatSessionMsg) }))
          if (evt.session) { setMeta(evt.session); onSessionUpdated?.(evt.session) }
          setStreaming(false); idxRef.current = -1
        },
        onError: (msg) => { setError(msg); setStreaming(false); idxRef.current = -1 },        // error
        onEvent: (evt) => {                                                                    // 调用过程
          if (evt.type === 'delta' || evt.type === 'done' || evt.type === 'error') return
          patchLast((m) => ({ ...m, process: [...(m.process || []), evt as ProcessEvt] }))
        },
      },
    )
  }, [sessionId, streaming, onSessionUpdated])

  return { messages, setMessages, meta, setMeta, loading, streaming, error, send, stop, reload: load }
}
