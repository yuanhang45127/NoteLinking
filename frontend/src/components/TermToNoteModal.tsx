import { useEffect, useRef, useState } from 'react'
import { getModelOverride } from '../api'
import { streamTracked } from '../lib/aiTasks'
import Modal from './Modal'
import StreamMd from './StreamMd'

/** 概念转完整笔记弹窗：从概念出发流式生成深入讲解（具体解释 + 用处），落盘后回调 onDone(savedPath)。「后台」收起继续跑。 */
export default function TermToNoteModal({ path, term, onClose, onDone }: {
  path: string
  term: string
  onClose: () => void
  onDone: (savedPath: string) => void
}) {
  const [text, setText] = useState('')
  const [savedPath, setSavedPath] = useState('')
  const [err, setErr] = useState('')
  const [bg, setBg] = useState(false)
  const ctrlRef = useRef<{ abort: () => void } | null>(null)
  const doneRef = useRef(onDone)
  doneRef.current = onDone
  // 后台期间完成时暂存结果，回到前台再交付（避免在用户看别的页面时突然跳转）
  const pendingRef = useRef('')
  const bgRef = useRef(bg)
  bgRef.current = bg

  const foreground = () => {
    setBg(false)
    if (pendingRef.current) { const p = pendingRef.current; pendingRef.current = ''; doneRef.current(p) }
  }

  useEffect(() => {
    const t = streamTracked(
      { title: `转为笔记 · ${term}`, kind: 'term', foreground },
      '/api/terms/to-note/stream', {
        path, ...getModelOverride(),
      },
      {
        onDelta: (x) => setText((s) => s + x),
        onDone: (evt) => {
          if (evt?.saved_path) {
            setSavedPath(evt.saved_path)
            if (bgRef.current) pendingRef.current = evt.saved_path
            else doneRef.current(evt.saved_path)
          } else {
            setErr('生成完成但保存失败，请重试')
          }
        },
        onError: (msg) => setErr(msg),
        summarizeDone: (evt) => (evt?.saved_path ? `已保存：${evt.saved_path}` : undefined),
      })
    ctrlRef.current = t
    return () => t.abort()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  if (bg) return null

  return (
    <Modal
      title={`转为完整笔记 · ${term}`}
      onClose={() => { ctrlRef.current?.abort(); onClose() }}
      wide
      ops={
        <>
          {!err && <span style={{ marginRight: 'auto', fontSize: 13, color: 'var(--muted)' }}>
            {savedPath ? '已保存 ✓' : '流式生成中…'}
          </span>}
          <button className="btn" title="收起弹窗，生成继续在右下角悬浮窗里跑" onClick={() => setBg(true)}>后台</button>
          <button className="btn" onClick={() => { ctrlRef.current?.abort(); onClose() }}>
            {savedPath ? '关闭' : '取消'}
          </button>
        </>
      }>
      {err && <div style={{ color: 'var(--err)', fontSize: 13, marginBottom: 8 }}>{err}</div>}
      <div className={`stream-box ${!text && !err ? 'loading-dot' : ''}`}>
        <StreamMd text={text} streaming={!savedPath && !err} />
      </div>
    </Modal>
  )
}
