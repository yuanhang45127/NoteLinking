import { useEffect, useMemo, useRef, useState } from 'react'
import { renderMarkdown } from '../lib/md'

const RENDER_INTERVAL = 250 // 流式期间最多每 250ms 全量重解析一次，避免每个 token 都渲染

function escapeHtml(s: string) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

/**
 * 流式输出的实时 Markdown 渲染：
 * streaming 期间节流重解析（尾帧必渲染），结束后做一次最终渲染。
 */
export default function StreamMd({ text, streaming = false }: { text: string; streaming?: boolean }) {
  const [shown, setShown] = useState(text)
  const lastRender = useRef(0)

  useEffect(() => {
    if (!streaming) { setShown(text); return }
    const elapsed = Date.now() - lastRender.current
    if (elapsed >= RENDER_INTERVAL) {
      lastRender.current = Date.now()
      setShown(text)
      return
    }
    const timer = window.setTimeout(() => {
      lastRender.current = Date.now()
      setShown(text)
    }, RENDER_INTERVAL - elapsed)
    return () => window.clearTimeout(timer)
  }, [text, streaming])

  const html = useMemo(() => {
    if (!shown) return ''
    try {
      return renderMarkdown(shown)
    } catch {
      // 半截 LaTeX / 未闭合代码块等极端情况下退回纯文本，保证不白屏
      return `<p>${escapeHtml(shown)}</p>`
    }
  }, [shown])

  return <div className="md-body stream-md" dangerouslySetInnerHTML={{ __html: html || '&nbsp;' }} />
}
