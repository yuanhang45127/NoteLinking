// AI 对话核心组件：消息流 + 工具调用步骤 + 划选存入 + 输入区（@引用 / 拖拽笔记）。
// 右侧滑出面板（ChatDock）使用，compact 模式收窄留白。
import { useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { api } from '../../api'
import { useApp } from '../../store'
import type { ChatSessionMeta, ChatToolStep } from '../../types'
import { listHeadings } from '../../lib/contentEdit'
import { CHAT_REFERENCE_EVENT, TEXT_REF_PREFIX, chatDock } from './chatDockSignal'
import StreamMd from '../StreamMd'
import SaveToNoteModal from './SaveToNoteModal'
import { useChatSession } from './useChatSession'

const TOOL_LABEL: Record<string, string> = {
  list_topics: '列出主题', search_notes: '搜索笔记', read_note: '读取笔记',
  create_note: '新建笔记', append_to_note: '追加内容', move_note: '移动笔记',
}

const SUGGESTIONS = [
  '帮我看看库里的主题，给 AI4EDA 定一份学习路线',
  '把「EDA 三巨头」整理成一篇新笔记放进 AI4EDA',
  '读一下「01 求职战役总览」，总结本周该做的事',
]

interface Mention { query: string; results: { path: string; title: string }[] }
interface MentionNote { path: string; title: string; sections: string[] }

/** 上下文 chip 的展示文案：text: 行内文字引用显示预览，其余按 路径#章节 */
function describeContext(ref: string): { icon: string; label: ReactNode; title: string } {
  if (ref.startsWith(TEXT_REF_PREFIX)) {
    try {
      const d = JSON.parse(ref.slice(TEXT_REF_PREFIX.length))
      const t = String(d.t || '')
      const s = String(d.s || '')
      return {
        icon: '📎',
        label: `“${t.slice(0, 12)}${t.length > 12 ? '…' : ''}” · ${t.length} 字`,
        title: (s ? `来自《${s}》\n` : '') + t,
      }
    } catch { /* 解析失败退回按原文展示 */ }
  }
  const hash = ref.indexOf('#')
  const base = (hash >= 0 ? ref.slice(0, hash) : ref).split('/').pop()?.replace(/\.md$/i, '') || ref
  const sec = hash >= 0 ? ref.slice(hash + 1) : ''
  return { icon: '📄', label: <>{base}{sec && <span className="ctx-sec"> · {sec}</span>}</>, title: ref }
}

export default function ChatConversation({ sessionId, compact, onSessionUpdated }: {
  sessionId: string | null
  compact?: boolean
  onSessionUpdated?: (s: ChatSessionMeta) => void
}) {
  const { toast } = useApp()
  const { messages, loading, streaming, error, send, stop } = useChatSession(sessionId, onSessionUpdated)
  const [input, setInput] = useState('')
  const [contexts, setContexts] = useState<string[]>([])
  const [dragOver, setDragOver] = useState(false)
  const [mention, setMention] = useState<Mention | null>(null)
  // @ 二级选择：先选笔记，再选「整篇」或某个章节（chunk）
  const [mentionNote, setMentionNote] = useState<MentionNote | null>(null)
  const [selPop, setSelPop] = useState<{ x: number; y: number; text: string } | null>(null)
  const [saveTarget, setSaveTarget] = useState<{ content: string; title?: string } | null>(null)

  const taRef = useRef<HTMLTextAreaElement>(null)
  const endRef = useRef<HTMLDivElement>(null)
  const bodyRef = useRef<HTMLDivElement>(null)
  const mentionTimer = useRef<number>()

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' }) }, [messages, streaming])
  // 切换会话时清空输入与引用；但从「无会话」进入首个会话时保留引用
  // （目录引用等入口会先加上下文、后由面板建好会话）
  const prevSidRef = useRef<string | null>(null)
  useEffect(() => {
    const prev = prevSidRef.current
    prevSidRef.current = sessionId
    setInput(''); setMention(null); setMentionNote(null)
    if (prev !== null && prev !== sessionId) setContexts([])
  }, [sessionId])

  // 目录「引用本节」等入口：接收 path#章节 引用，加入上下文并展开面板
  useEffect(() => {
    const onRef = (e: Event) => {
      const ref = (e as CustomEvent).detail as string
      if (!ref) return
      setContexts((c) => (c.includes(ref) ? c : [...c, ref]))
      setMention(null); setMentionNote(null)
    }
    window.addEventListener(CHAT_REFERENCE_EVENT, onRef)
    return () => window.removeEventListener(CHAT_REFERENCE_EVENT, onRef)
  }, [])

  /* ---------- 输入与 @ 引用 ---------- */
  const autoGrow = () => {
    const ta = taRef.current
    if (!ta) return
    ta.style.height = 'auto'
    ta.style.height = Math.min(ta.scrollHeight, compact ? 100 : 170) + 'px'
  }

  const onInputChange = (v: string) => {
    setInput(v); autoGrow()
    const at = v.lastIndexOf('@')
    if (at >= 0) {
      // @ 查询词到空白/常用标点为止，避免把后面的正文一并当关键词
      let tail = v.slice(at + 1)
      const stop = tail.search(/[\s，。；、,;:：]/)
      if (stop >= 0) tail = tail.slice(0, stop)
      if (tail.length <= 30) {
        setMention({ query: tail, results: [] })
        window.clearTimeout(mentionTimer.current)
        mentionTimer.current = window.setTimeout(async () => {
          try {
            const r = await api.search(tail.trim() || ' ')
            setMention({ query: tail, results: tail.trim() ? r.results.slice(0, 8) : r.results.slice(0, 6) })
          } catch { setMention(null) }
        }, 220)
        return
      }
    }
    setMention(null)
  }

  const addContextRef = (ref: string) => {
    setContexts((c) => (c.includes(ref) ? c : [...c, ref]))
    setMention(null); setMentionNote(null)
    taRef.current?.focus()
  }

  const pickMention = async (path: string, title: string) => {
    // 二级选择：笔记有章节（chunk）时先选「整篇 / 某章节」
    try {
      const n = await api.note(path)
      const uniq = [...new Set(listHeadings(n.content).map((h) => h.title))]
      if (uniq.length > 0) { setMentionNote({ path, title, sections: uniq }); return }
    } catch { /* 拉不到章节就整篇引用 */ }
    addContextRef(path)
  }

  const takeDroppedNote = (e: React.DragEvent) => {
    const path = e.dataTransfer.getData('text/nl-note') || e.dataTransfer.getData('text/plain')
    if (path && /\.md$/i.test(path)) setContexts((c) => (c.includes(path) ? c : [...c, path]))
    else if (path) toast('只能拖入 .md 笔记', 'err')
  }

  const doSend = () => {
    if (!sessionId || streaming || !input.trim()) return
    send(input.trim(), contexts)
    setInput('')
    setContexts([])
    if (taRef.current) taRef.current.style.height = 'auto'
  }

  /* ---------- 划选 → 存入笔记 ---------- */
  const onMouseUp = () => {
    const sel = window.getSelection()
    const text = sel?.toString().trim() || ''
    const host = bodyRef.current
    if (!sel || sel.isCollapsed || text.length < 2 || !host
      || !host.contains(sel!.getRangeAt(0).commonAncestorContainer)) {
      setSelPop(null); return
    }
    const rect = sel!.getRangeAt(0).getBoundingClientRect()
    const wrap = host.getBoundingClientRect()
    setSelPop({ x: rect.left + rect.width / 2 - wrap.left, y: rect.top - wrap.top - 6, text })
  }

  const copyText = async (t: string) => {
    try { await navigator.clipboard.writeText(t); toast('已复制') }
    catch { toast('复制失败', 'err') }
  }

  const lastAssistantIdx = (() => {
    for (let i = messages.length - 1; i >= 0; i--) if (messages[i].role === 'assistant') return i
    return -1
  })()

  if (!sessionId) {
    return <div className="empty-tip" style={{ height: '100%' }}><div className="big">新建或选择一个对话开始</div></div>
  }

  return (
    <div className={`chat-conversation ${compact ? 'compact' : ''}`}>
      <div className="chat-messages" ref={bodyRef} onMouseUp={onMouseUp}>
        {loading && <div className="empty-tip"><span className="loading-dot" /></div>}
        {!loading && messages.length === 0 && (
          <div className="chat-welcome">
            <div className="big">开始对话</div>
            <div className="sub">可以让我读写笔记库：查资料、整理、新建笔记…<br />
              输入 <b>@</b> 或把左侧笔记拖进来可引用上下文</div>
            <div className="chat-suggests">
              {SUGGESTIONS.map((s) => (
                <button key={s} className="chat-suggest" onClick={() => { setInput(s); taRef.current?.focus() }}>{s}</button>
              ))}
            </div>
          </div>
        )}

        {messages.map((m, i) =>
          m.role === 'user' ? (
            <div key={i} className="msg user"><div className="bubble">{m.content}</div></div>
          ) : (
            <div key={i} className="msg ai">
              <div className="bubble">
                {(m.tool_steps?.length || 0) > 0 && <ToolSteps steps={m.tool_steps!} />}
                {m.content
                  ? <StreamMd text={m.content} streaming={streaming && i === messages.length - 1} />
                  : (streaming && i === messages.length - 1 ? <span className="loading-dot" /> : null)}
                {!streaming && m.content && (
                  <div className="chat-msg-ops">
                    <button className="btn text" onClick={() => copyText(m.content)}>复制</button>
                    <button className="btn text" onClick={() => setSaveTarget({ content: m.content, title: m.note_title })}>存为笔记</button>
                    {i === lastAssistantIdx && (
                      <button className="btn text" onClick={() => send('', [], true)} disabled={streaming}>重新生成</button>
                    )}
                  </div>
                )}
              </div>
            </div>
          ),
        )}
        <div ref={endRef} />
      </div>

      {selPop && (
        <div className="sel-popover" style={{ left: selPop.x, top: selPop.y, transform: 'translateX(-50%)' }}>
          <div className="hint">已选中 {selPop.text.length} 个字</div>
          <div className="btns">
            <button className="btn primary small" onClick={() => { setSaveTarget({ content: selPop.text }); setSelPop(null) }}>存入笔记</button>
            <button className="btn small" onClick={() => { copyText(selPop.text); setSelPop(null) }}>复制</button>
          </div>
        </div>
      )}

      <div
        className={`chat-composer ${dragOver ? 'drag-over' : ''}`}
        onDragOver={(e) => {
          if (e.dataTransfer.types.includes('text/nl-note') || e.dataTransfer.types.includes('text/plain')) {
            e.preventDefault(); setDragOver(true)
          }
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => { e.preventDefault(); setDragOver(false); takeDroppedNote(e) }}
      >
        {error && <div className="chat-error">⚠️ {error}</div>}
        {contexts.length > 0 && (
          <div className="chat-contexts">
            {contexts.map((p) => {
              const d = describeContext(p)
              return (
                <span key={p} className="ctx-chip" title={d.title}>
                  <span className="ctx-chip-text">{d.icon} {d.label}</span>
                  <button className="ctx-chip-x" title="移除引用" onClick={() => setContexts((c) => c.filter((x) => x !== p))}>×</button>
                </span>
              )
            })}
          </div>
        )}
        <div className="chat-input-row">
          <textarea
            ref={taRef}
            rows={1}
            placeholder={streaming ? '回答中…' : '输入问题，@ 引用笔记，或直接把笔记拖进来…'}
            value={input}
            onChange={(e) => onInputChange(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Escape') { setMention(null); setMentionNote(null); return }
              if (e.key === 'Enter' && !e.shiftKey && !mention && !mentionNote) { e.preventDefault(); doSend() }
            }}
          />
          {streaming
            ? <button className="btn" onClick={stop}>■ 停止</button>
            : <button className="btn primary" disabled={!input.trim()} onClick={doSend}>发送</button>}
        </div>
        {mentionNote ? (
          <div className="mention-pop">
            <div className="mention-empty">引用《{mentionNote.title}》的哪一部分？</div>
            <button className="mention-item" onClick={() => addContextRef(mentionNote.path)}>
              <span className="name">整篇笔记</span>
            </button>
            {mentionNote.sections.map((s) => (
              <button key={s} className="mention-item" onClick={() => addContextRef(`${mentionNote.path}#${s}`)}>
                <span className="name">💬 {s}</span>
                <span className="path">仅注入该章节（chunk）</span>
              </button>
            ))}
          </div>
        ) : mention && (
          <div className="mention-pop">
            {mention.results.length === 0
              ? <div className="mention-empty">{mention.query.trim() ? '没有匹配的笔记' : '输入关键词搜索，或继续输入…'}</div>
              : mention.results.map((r) => (
                <button key={r.path} className="mention-item" onClick={() => pickMention(r.path, r.title)}>
                  <span className="name">{r.title}</span>
                  <span className="path">{r.path}</span>
                </button>
              ))}
          </div>
        )}
      </div>

      {saveTarget !== null && (
        <SaveToNoteModal content={saveTarget.content} suggestedTitle={saveTarget.title}
          onClose={() => setSaveTarget(null)} toast={toast} />
      )}
    </div>
  )
}

function ToolSteps({ steps }: { steps: ChatToolStep[] }) {
  return (
    <div className="tool-steps">
      {steps.map((s, i) => (
        <details key={i} className={`tool-step ${s.running ? 'running' : ''} ${s.ok ? '' : 'err'}`}>
          <summary>
            <span className="t-icon">{s.running ? '⏳' : s.ok ? '🔧' : '⚠️'}</span>
            <span className="t-name">{TOOL_LABEL[s.name] || s.name}</span>
            {s.summary && <span className="t-summary">{s.summary}</span>}
          </summary>
          <pre>{JSON.stringify(s.args, null, 2)}</pre>
        </details>
      ))}
    </div>
  )
}
