import { useCallback, useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { api, getModelOverride, llmUrls, streamSSE } from '../api'
import { useApp } from '../store'
import type { NoteDetail, TreeNode } from '../types'
import ReaderView from '../components/ReaderView'
import Modal from '../components/Modal'
import StreamMd from '../components/StreamMd'

export default function NotesPage() {
  const { activeTopic, treeTopic, tree, refreshTree, refreshTopics, settings, toast } = useApp()
  const [params, setParams] = useSearchParams()
  const navigate = useNavigate()
  const path = params.get('path') || ''
  const genTopic = params.get('generate') || ''
  const [note, setNote] = useState<NoteDetail | null>(null)
  const [missing, setMissing] = useState(false)

  // 切换主题后，URL 里还挂着上一个主题的笔记路径 → 清掉，让页面回到当前主题
  const lastTopic = useRef(activeTopic)
  useEffect(() => {
    if (lastTopic.current === activeTopic) return
    lastTopic.current = activeTopic
    if (path) setParams({}, { replace: true })
  }, [activeTopic, path, setParams])

  // 目录与当前主题一致时，无选中笔记则自动打开第一篇
  useEffect(() => {
    if (path || !tree || treeTopic !== activeTopic) return
    const first = firstNote(tree)
    if (first) setParams({ path: first.path }, { replace: true })
  }, [path, tree, treeTopic, activeTopic, setParams])

  const load = useCallback(async () => {
    if (!path) { setNote(null); return }
    setMissing(false)
    try {
      setNote(await api.note(path))
    } catch {
      setMissing(true); setNote(null)
    }
  }, [path])

  useEffect(() => { load() }, [load])
  useEffect(() => { refreshTopics() /* 侧栏计数刷新，静默 */ }, [path]) // eslint-disable-line

  const reload = async () => { await load(); refreshTree() }

  // 各状态的内容主体（GenerateModal 在所有状态下都要挂载，放在最后统一渲染）
  let body: ReactNode
  if (missing) {
    body = (
      <div className="empty-tip">
        <div className="big">笔记不存在或已被删除</div>
        <button className="btn small" onClick={() => setParams({})}>回到主题首页</button>
      </div>
    )
  } else if (!activeTopic) {
    body = <div className="empty-tip"><div className="big">先在左侧新建或选择一个主题</div></div>
  } else if (treeTopic !== activeTopic) {
    // 刚切换主题，目录还在加载：短暂留白，避免误显示“还没有笔记”
    body = null
  } else if (!note) {
    body = (
      <div className="empty-tip">
        <div className="big">这个主题还没有笔记</div>
        <button className="btn primary" onClick={() => openAiGenerate(navigate, activeTopic)}>✦ 用 AI 生成第一篇笔记</button>
      </div>
    )
  } else {
    body = (
      <ReaderView
        key={note.path}
        note={note}
        settings={settings}
        reload={reload}
        onOpenConcept={(p) => navigate(`/concept?path=${encodeURIComponent(p)}`)}
        toast={toast}
      />
    )
  }

  return (
    <>
      {body}
      {genTopic && (
        <GenerateModal
          topic={genTopic}
          onClose={() => setParams(path ? { path } : {}, { replace: true })}
          onCreated={async (p) => {
            await Promise.all([refreshTree(), refreshTopics()])
            setParams({ path: p }, { replace: true })
            toast('笔记已生成并保存')
          }}
          toast={toast}
        />
      )}
    </>
  )
}

function firstNote(node: TreeNode | null): TreeNode | null {
  if (!node?.children) return null
  for (const c of node.children) {
    if (c.type === 'note') return c
    if (c.type === 'dir') {
      const inner = firstNote(c)
      if (inner) return inner
    }
  }
  return null
}

function openAiGenerate(navigate: any, topic: string) {
  navigate(`/notes?generate=${encodeURIComponent(topic)}`)
}

/* ---------- 首篇笔记 AI 生成弹窗（?generate=主题） ---------- */
function GenerateModal({ topic, onClose, onCreated, toast }: {
  topic: string
  onClose: () => void
  onCreated: (path: string) => void
  toast: (t: string, k?: 'ok' | 'err') => void
}) {
  const [title, setTitle] = useState('')
  const [prompt, setPrompt] = useState('')
  const [text, setText] = useState('')
  const [running, setRunning] = useState(false)
  const ctrlRef = useRef<{ abort: () => void } | null>(null)

  const safeTitle = title.trim().replace(/[\\/:*?"<>|]/g, ' ').trim()
  const canStart = !running && !!safeTitle && !!prompt.trim()

  const start = () => {
    if (!canStart) return
    setRunning(true); setText('')
    ctrlRef.current = streamSSE(llmUrls.generateNote, {
      topic, prompt: prompt.trim(), title: safeTitle, stream: true,
      save_path: `${topic}/${safeTitle}.md`,
      ...getModelOverride(),
    }, (t) => setText((s) => s + t),
      (evt) => {
        setRunning(false)
        if (evt?.saved_path) onCreated(evt.saved_path)
        else { toast('生成完成，但保存失败，请重试', 'err'); onClose() }
      },
      (msg) => { setRunning(false); toast(msg, 'err') })
  }

  return (
    <Modal title={`AI 生成笔记 · ${topic}`} onClose={() => { ctrlRef.current?.abort(); onClose() }} wide
      ops={
        <>
          {!running && !text && <button className="btn primary" style={{ marginRight: 'auto' }} disabled={!canStart} onClick={start}>开始生成</button>}
          {running && <span style={{ marginRight: 'auto', fontSize: 13, color: 'var(--muted)' }}>正在生成，请稍候…</span>}
          {text && !running && (
            <button className="btn primary" style={{ marginRight: 'auto' }} onClick={start}>重新生成</button>
          )}
          <button className="btn" onClick={() => { ctrlRef.current?.abort(); onClose() }}>关闭</button>
        </>
      }>
      <div style={{ display: 'flex', gap: 10 }}>
        <div className="form-row" style={{ flex: 1 }}>
          <label>笔记标题</label>
          <input className="text-input" placeholder="如：神经网络基础" value={title}
            disabled={running || !!text}
            onChange={(e) => setTitle(e.target.value)} />
        </div>
      </div>
      <div className="form-row">
        <label>生成要求（想涵盖的内容、深度、风格）</label>
        <textarea className="text-input" style={{ minHeight: 110 }}
          placeholder="如：面向初学者，讲清楚核心概念、 intuition 和一个带公式的例子，结尾给小结"
          value={prompt} disabled={running || !!text}
          onChange={(e) => setPrompt(e.target.value)} />
      </div>
      {(text || running) && (
        <div className={`stream-box ${running && !text ? 'loading-dot' : ''}`} style={{ marginTop: 6 }}>
          <StreamMd text={text} streaming={running} />
        </div>
      )}
    </Modal>
  )
}
