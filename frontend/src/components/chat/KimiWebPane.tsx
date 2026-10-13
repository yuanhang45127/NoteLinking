// ChatDock 的「Kimi Code」标签页：iframe 嵌入本机 kimi web。
// kimi web 无 X-Frame-Options/CSP 限制，鉴权走 URL #token= 片段（无跨站 cookie 依赖），可iframe。
import { useCallback, useEffect, useState } from 'react'
import { api } from '../../api'
import type { KimiWebStatus } from '../../types'

export default function KimiWebPane() {
  const [st, setSt] = useState<KimiWebStatus | null>(null)
  const [err, setErr] = useState('')

  const refresh = useCallback(async () => {
    setErr('')
    try {
      setSt(await api.kimiWebStatus())
    } catch (e: any) {
      setErr(e.message || '检测失败')
    }
  }, [])

  useEffect(() => { refresh() }, [refresh])

  if (!st) {
    return <div className="empty-tip" style={{ height: '100%' }}>{err ? `⚠️ ${err}` : <span className="loading-dot" />}</div>
  }

  if (!st.running || !st.token) {
    return (
      <div className="kimi-pane-hint">
        <div className="big">未检测到 Kimi Code Web 服务</div>
        <div className="sub">在本机启动后点「重试」即可嵌入。建议先 cd 到笔记库目录再启动<br />（Kimi Code 的文件工具默认操作启动目录）：</div>
        <pre className="kimi-cmd">kimi web --no-open --port 58627</pre>
        {err && <div className="chat-error" style={{ padding: 0 }}>⚠️ {err}</div>}
        <div style={{ marginTop: 10 }}>
          <button className="btn primary small" onClick={refresh}>重试</button>
        </div>
      </div>
    )
  }

  return (
    <div className="kimi-pane">
      <iframe
        className="kimi-frame"
        src={`${st.url}/#token=${encodeURIComponent(st.token)}`}
        title="Kimi Code"
        allow="clipboard-read; clipboard-write"
      />
      <a className="kimi-open-ext" href={`${st.url}/#token=${encodeURIComponent(st.token)}`}
        target="_blank" rel="noreferrer" title="新窗口打开">↗</a>
    </div>
  )
}
