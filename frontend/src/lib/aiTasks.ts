// 全局 AI 任务登记处：所有流式生成（streamSSE）在这里登记，右下角悬浮窗统一展示。
// 组件持有返回的 { abort }（= 停止）；「后台」= 弹窗隐藏但保持挂载，流继续跑。
import { useSyncExternalStore } from 'react'
import { streamSSE } from '../api'

export type AiTaskStatus = 'running' | 'done' | 'error' | 'stopped'

export interface AiTask {
  id: string
  title: string
  /** 分类标识（chat / term / note / exam / tutor / book …），便于以后按类筛选 */
  kind: string
  status: AiTaskStatus
  startedAt: number
  /** 最近一次状态/字数变化时间 */
  updatedAt: number
  /** 已流式输出的字符数（进度感） */
  chars: number
  /** 结束摘要：保存路径 / 错误信息 */
  note?: string
  /** 回到发起界面（弹窗恢复显示 / 面板展开 / 跳回页面） */
  foreground?: () => void
  stop: () => void
}

type TaskInit = Pick<AiTask, 'title' | 'kind'> & Partial<Pick<AiTask, 'foreground'>>

const tasks = new Map<string, AiTask>()
const listeners = new Set<() => void>()
let seq = 0
// useSyncExternalStore 要求 getSnapshot 返回稳定引用：仅在 emit() 后重算
let dirty = true
let cache: AiTask[] = []

function emit() {
  dirty = true
  listeners.forEach((l) => l())
}

function snapshot(): AiTask[] {
  if (dirty) {
    cache = [...tasks.values()].sort((a, b) => b.startedAt - a.startedAt)
    dirty = false
  }
  return cache
}

const subscribe = (l: () => void) => {
  listeners.add(l)
  return () => { listeners.delete(l) }
}

export function useAiTasks(): AiTask[] {
  return useSyncExternalStore(subscribe, snapshot, snapshot)
}

export function removeTask(id: string) {
  if (tasks.delete(id)) emit()
}

export function clearFinished() {
  let changed = false
  for (const [id, t] of tasks) {
    if (t.status !== 'running') { tasks.delete(id); changed = true }
  }
  if (changed) emit()
}

function patch(id: string, p: Partial<AiTask>) {
  const t = tasks.get(id)
  if (!t) return
  tasks.set(id, { ...t, ...p, updatedAt: Date.now() })
  emit()
}

/* ------------------------------------------------------------------ 流式包装 */

interface TrackedCb {
  onDelta?: (text: string) => void
  onDone?: (evt: any) => void
  onError?: (msg: string) => void
  onEvent?: (evt: any) => void
  /** abort 之后调用（外部停止 / 组件卸载清理都走这里），用于同步本地 running 状态 */
  onStop?: () => void
  /** done 时的登记摘要（如 已保存：路径） */
  summarizeDone?: (evt: any) => string | undefined
}

/** 以任务方式跑一条 SSE 流：自动登记、累计字数、更新状态；返回的 abort = 停止。 */
export function streamTracked(init: TaskInit, url: string, body: unknown, cb: TrackedCb = {}): {
  abort: () => void
  taskId: string
} {
  let settled = false
  let innerAbort: () => void = () => {}
  const stop = () => {
    if (settled) return
    settled = true
    innerAbort()
    patch(taskId, { status: 'stopped' })
    cb.onStop?.()
  }
  const taskId = (() => {
    seq += 1
    const id = `t${seq}`
    tasks.set(id, {
      id, title: init.title, kind: init.kind, status: 'running',
      startedAt: Date.now(), updatedAt: Date.now(), chars: 0,
      foreground: init.foreground, stop,
    })
    emit()
    return id
  })()

  const ctrl = streamSSE(url, body,
    (text) => {
      const t = tasks.get(taskId)
      if (t) patch(taskId, { chars: t.chars + text.length })
      cb.onDelta?.(text)
    },
    (evt) => { settled = true; patch(taskId, { status: 'done', note: cb.summarizeDone?.(evt) }); cb.onDone?.(evt) },
    (msg) => { settled = true; patch(taskId, { status: 'error', note: msg }); cb.onError?.(msg) },
    cb.onEvent ? (evt) => cb.onEvent!(evt) : undefined)
  innerAbort = ctrl.abort
  return { abort: stop, taskId }
}
