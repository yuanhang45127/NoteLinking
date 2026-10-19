// 全局 AI 任务登记处：所有流式生成（streamSSE）在这里登记，右下角悬浮窗统一展示。
// 组件持有返回的 { abort }（= 停止）；「后台」= 弹窗隐藏但保持挂载，流继续跑。
import { useSyncExternalStore } from 'react'
import { cancelAiTask, listAiTasks, startAiTask, streamSSE, type AiTaskInfo } from '../api'
import type { ProcessEvt } from '../types'

export type AiTaskStatus = 'running' | 'done' | 'error' | 'stopped'

/** 过程事件缓冲上限（防止超长任务把内存吃爆；只存过程，不含 delta） */
const MAX_PROC_EVENTS = 600

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
  /** 调用过程事件（llm_start / tool / step …），悬浮窗展开可见 */
  events: ProcessEvt[]
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

/** 把一条过程事件挂到任务上（delta/done/error 不算过程）。 */
function pushEvent(id: string, evt: any) {
  const t = tasks.get(id)
  if (!t || !evt || evt.type === 'delta' || evt.type === 'done' || evt.type === 'error') return
  const events = [...t.events, evt as ProcessEvt]
  patch(id, { events: events.length > MAX_PROC_EVENTS ? events.slice(-MAX_PROC_EVENTS) : events })
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
      startedAt: Date.now(), updatedAt: Date.now(), chars: 0, events: [],
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
    (evt) => { pushEvent(taskId, evt); cb.onEvent?.(evt) })
  innerAbort = ctrl.abort
  return { abort: stop, taskId }
}

/* ------------------------------------------------ 服务端托管任务（刷新页面后可恢复） */

function addTask(init: TaskInit, stop: () => void): string {
  seq += 1
  const id = `t${seq}`
  tasks.set(id, {
    id, title: init.title, kind: init.kind, status: 'running',
    startedAt: Date.now(), updatedAt: Date.now(), chars: 0, events: [],
    foreground: init.foreground, stop,
  })
  emit()
  return id
}

/**
 * 服务端托管的后台任务：生成在服务器协程里运行并缓冲事件，
 * 页面刷新后由 restoreAiTasks 重连（悬浮条恢复、进度继续推进）。
 * cb 语义与 streamTracked 完全一致；重连回放时 onDelta 会从零补发全量增量。
 */
export function streamTrackedDetached(init: TaskInit, op: string, payload: unknown, cb: TrackedCb = {}): {
  abort: () => void
  taskId: string
} {
  let settled = false
  let serverId = ''
  let innerAbort: () => void = () => {}
  const stop = () => {
    if (settled) return
    settled = true
    innerAbort()
    if (serverId) cancelAiTask(serverId)
    patch(taskId, { status: 'stopped' })
    cb.onStop?.()
  }
  const taskId = addTask(init, stop)
  ;(async () => {
    try {
      const info = await startAiTask(init.title, init.kind, op, payload)
      if (settled) { cancelAiTask(info.id); return }
      serverId = info.id
      innerAbort = streamSSE(
        `/api/ai-tasks/${encodeURIComponent(info.id)}/events`, {},
        (text) => { const t = tasks.get(taskId); if (t) patch(taskId, { chars: t.chars + text.length }); cb.onDelta?.(text) },
        (evt) => { settled = true; patch(taskId, { status: 'done', note: cb.summarizeDone?.(evt) }); cb.onDone?.(evt) },
        (msg) => { settled = true; patch(taskId, { status: 'error', note: msg }); cb.onError?.(msg) },
        (evt) => { pushEvent(taskId, evt); cb.onEvent?.(evt) },
      ).abort
    } catch (e: any) {
      settled = true
      patch(taskId, { status: 'error', note: e.message || String(e) })
      cb.onError?.(e.message || String(e))
    }
  })()
  return { abort: stop, taskId }
}

let restoreRan = false

/** 应用启动/登录后调用：把服务器上仍在运行（或刚完成）的后台任务挂回悬浮窗并重连事件流。 */
export async function restoreAiTasks(handlers: { onDone?: (evt: any) => void } = {}) {
  if (restoreRan) return
  let list: AiTaskInfo[] = []
  try {
    list = await listAiTasks()
    restoreRan = true
  } catch { return } // 未登录等场景：等下次 proceed 再试
  for (const t of list) {
    const key = `s${t.id}`
    if (tasks.has(key)) continue
    const startedAt = t.created_at * 1000
    if (t.status !== 'running' && Date.now() - startedAt > 5 * 60_000) continue
    const stop = () => { cancelAiTask(t.id); patch(key, { status: 'stopped' }) }
    tasks.set(key, {
      id: key, title: t.title, kind: t.kind,
      status: t.status as AiTaskStatus,
      startedAt, updatedAt: Date.now(), chars: t.chars, events: [],
      note: t.status !== 'running'
        ? (t.result?.saved_path ? `已保存：${t.result.saved_path}` : (t.error || '已结束'))
        : undefined,
      stop,
    })
    emit()
    if (t.status !== 'running') continue
    streamSSE(`/api/ai-tasks/${encodeURIComponent(t.id)}/events`, {},
      (text) => { const x = tasks.get(key); if (x) patch(key, { chars: x.chars + text.length }) },
      (evt) => { patch(key, { status: 'done', note: evt?.saved_path ? `已保存：${evt.saved_path}` : '已完成' }); handlers.onDone?.(evt) },
      (msg) => patch(key, { status: 'error', note: msg }),
      (evt) => {
        pushEvent(key, evt)
        if ((evt.type === 'note_start' || evt.type === 'note_done') && evt.total) {
          patch(key, { note: `${evt.title || ''}（${(evt.index ?? 0) + (evt.type === 'note_done' ? 1 : 0)}/${evt.total}）` })
        }
      })
  }
}
