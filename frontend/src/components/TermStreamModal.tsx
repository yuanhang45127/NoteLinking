import { useEffect, useRef, useState } from 'react'
import { getModelOverride, streamSSE, streamUrls } from '../api'
import Modal from './Modal'

/** 概念解释流式生成弹窗：增量展示，落盘后回调 onDone(savedPath)。 */
export default function TermStreamModal({ path, term, contextBefore, contextAfter, regenerate, onClose, onDone }: {
  path: string
  term: string
  contextBefore: string
  contextAfter: string
  regenerate?: boolean
  onClose: () => void
  onDone: (savedPath: string) => void
}) {
  const [text, setText] = useState('')
  const [savedPath, setSavedPath] = useState('')
  const [err, setErr] = useState('')
  const ctrlRef = useRef<{ abort: () => void } | null>(null)
  const doneRef = useRef(onDone)
  doneRef.current = onDone

  useEffect(() => {
    ctrlRef.current = streamSSE(streamUrls.term, {
      path, term, stream: true, regenerate: !!regenerate,
      context_before: contextBefore, context_after: contextAfter,
      ...getModelOverride(),
    },
      (t) => setText((s) => s + t),
      (evt) => {
        if (evt?.saved_path) {
          setSavedPath(evt.saved_path)
          doneRef.current(evt.saved_path)
        } else {
          setErr('生成完成但保存失败，请重试')
        }
      },
      (msg) => setErr(msg))
    return () => ctrlRef.current?.abort()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <Modal
      title={`${regenerate ? '重新生成' : '生成'}概念解释 · ${term}`}
      onClose={() => { ctrlRef.current?.abort(); onClose() }}
      wide
      ops={
        <>
          {!err && <span style={{ marginRight: 'auto', fontSize: 13, color: 'var(--muted)' }}>
            {savedPath ? '已保存 ✓' : '流式生成中…'}
          </span>}
          <button className="btn" onClick={() => { ctrlRef.current?.abort(); onClose() }}>
            {savedPath ? '关闭' : '取消'}
          </button>
        </>
      }>
      {err && <div style={{ color: 'var(--err)', fontSize: 13, marginBottom: 8 }}>{err}</div>}
      <div className={`stream-box ${!text && !err ? 'loading-dot' : ''}`}>{text || ' '}</div>
    </Modal>
  )
}
