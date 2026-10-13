// 右下角 AI 任务悬浮窗：FAB + 可展开面板，统一查看正在运行的流式生成。
// 任务由各流式界面经 streamTracked 登记（aiTasks.ts）；「前台」调任务自带的 foreground。
import { useEffect, useReducer, useState } from 'react'
import { clearFinished, removeTask, useAiTasks } from '../lib/aiTasks'
import type { AiTask } from '../lib/aiTasks'

const STATUS_ICON: Record<AiTask['status'], string> = {
  running: '⏳', done: '✓', error: '✗', stopped: '⏹',
}

function fmtDur(ms: number): string {
  const s = Math.max(0, Math.floor(ms / 1000))
  const m = Math.floor(s / 60)
  return m ? `${m}:${String(s % 60).padStart(2, '0')}` : `${s}s`
}

export default function AiTaskFloat() {
  const tasks = useAiTasks()
  const [open, setOpen] = useState(false)
  // 运行中每秒刷新一次计时；面板打开时即使有已结束任务也保持计时可见
  const [, tick] = useReducer((x: number) => x + 1, 0)
  const running = tasks.filter((t) => t.status === 'running').length
  useEffect(() => {
    if (!running) return
    const t = window.setInterval(tick, 1000)
    return () => window.clearInterval(t)
  }, [running])

  if (!tasks.length) return null
  const now = Date.now()

  return (
    <>
      <button className="ai-task-fab" title="AI 任务" onClick={() => setOpen((v) => !v)}>
        ⚡
        {running > 0 && <span className="ai-task-badge">{running}</span>}
      </button>
      {open && (
        <div className="ai-task-panel">
          <div className="ai-task-head">
            <b>AI 任务</b>
            <span className="ai-task-sub">{running ? `${running} 个在跑` : '没有正在运行的任务'}</span>
            <button className="btn text" onClick={clearFinished}>清空已完成</button>
            <button className="btn text" onClick={() => setOpen(false)}>收起</button>
          </div>
          <div className="ai-task-list">
            {tasks.map((t) => (
              <div key={t.id} className={`ai-task-row st-${t.status}`}>
                <span className="at-icon">{STATUS_ICON[t.status]}</span>
                <span className="at-main">
                  <span className="at-title" title={t.title}>{t.title}</span>
                  <span className="at-meta">
                    {fmtDur((t.status === 'running' ? now : t.updatedAt) - t.startedAt)} · {t.chars} 字
                    {t.note && <em className="at-note" title={t.note}> · {t.note}</em>}
                  </span>
                </span>
                <span className="at-ops">
                  {t.status === 'running' && (
                    <button className="btn text" title="停止生成" onClick={t.stop}>停止</button>
                  )}
                  {t.foreground && (
                    <button className="btn text" title="回到发起界面" onClick={t.foreground}>前台</button>
                  )}
                  {t.status !== 'running' && (
                    <button className="at-x" title="移除" onClick={() => removeTask(t.id)}>×</button>
                  )}
                </span>
              </div>
            ))}
          </div>
          <div className="ai-task-foot">生成中切走页面会停止该页面的任务；对话与侧边栏任务不受影响。</div>
        </div>
      )}
    </>
  )
}
