// 后端 API 客户端 + SSE 流式工具
import type {
  Annotation, Checklist, Exam, Goal, GraphData, NoteDetail, Provider, Settings,
  Topic, TreeNode,
} from './types'

async function http<T>(url: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(url, {
    headers: init?.body ? { 'Content-Type': 'application/json' } : undefined,
    ...init,
  })
  if (!resp.ok) {
    let detail = `HTTP ${resp.status}`
    try {
      const data = await resp.json()
      detail = data.detail || detail
    } catch { /* ignore */ }
    throw new Error(detail)
  }
  return resp.json()
}

const post = <T>(url: string, body: unknown) =>
  http<T>(url, { method: 'POST', body: JSON.stringify(body) })
const put = <T>(url: string, body: unknown) =>
  http<T>(url, { method: 'PUT', body: JSON.stringify(body) })
const del = <T>(url: string) => http<T>(url, { method: 'DELETE' })
const qs = (params: Record<string, string | number | undefined>) => {
  const u = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== '') u.set(k, String(v))
  return u.toString()
}

export const api = {
  // 主题 / 树
  topics: () => http<{ topics: Topic[] }>('/api/topics'),
  createTopic: (name: string) => post<Topic>('/api/topics', { name }),
  tree: (path = '') => http<TreeNode>(`/api/tree?${qs({ path })}`),

  // 笔记
  note: (path: string) => http<NoteDetail>(`/api/notes?${qs({ path })}`),
  createNote: (path: string, content = '') => post<NoteDetail>('/api/notes', { path, content }),
  saveNote: (path: string, content: string) => put<NoteDetail>('/api/notes', { path, content }),
  deleteNote: (path: string) => del<unknown>(`/api/notes?${qs({ path })}`),
  backlinks: (path: string) =>
    http<{ backlinks: NoteDetail['backlinks'] }>(`/api/notes/backlinks?${qs({ path })}`),
  search: (q: string, topic?: string) =>
    http<{ results: { path: string; name: string; title: string; snippet: string }[] }>(
      `/api/search?${qs({ q, topic })}`),
  resolveLink: (target: string, topic?: string) =>
    http<NoteDetail>(`/api/notes/resolve-link?${qs({ target, topic })}`),

  // 高亮
  annotations: (path: string) =>
    http<{ annotations: Annotation[] }>(`/api/annotations?${qs({ path })}`),
  addAnnotation: (body: Partial<Annotation> & { path: string; quote: string }) =>
    post<Annotation>('/api/annotations', body),
  updateAnnotation: (path: string, id: string, patch: Partial<Annotation>) =>
    put<Annotation>(`/api/annotations/${id}?${qs({ path })}`, patch),
  deleteAnnotation: (path: string, id: string) =>
    del<unknown>(`/api/annotations/${id}?${qs({ path })}`),

  // 词条
  createTerm: (body: { path: string; term: string; context_before?: string; context_after?: string; regenerate?: boolean }) =>
    post<NoteDetail & { is_new: boolean }>('/api/terms', body),
  resolveTerm: (name: string, topic?: string) =>
    http<{ found: boolean } & NoteDetail>(`/api/terms/resolve?${qs({ name, topic })}`),

  // 图谱
  graph: (topic?: string) => http<GraphData>(`/api/graph?${qs({ topic })}`),

  // 考试
  generateExam: (body: { paths: string[]; types: string[]; count: number; difficulty: string; title?: string }) =>
    post<Exam>('/api/exams/generate', body),
  getExam: (id: string) => http<Exam>(`/api/exams/${id}`),
  submitAttempt: (id: string, answers: { question_id: string; answer: string }[]) =>
    post<Exam['attempts'] extends (infer T)[] | undefined ? T : never>(`/api/exams/${id}/attempts`, { answers }),
  checklist: (topic: string) => http<{ checklist: Checklist | null }>(`/api/exams/checklist?${qs({ topic })}`),
  generateChecklist: (paths: string[]) => post<Checklist>('/api/exams/checklist', { paths }),
  toggleChecklist: (topic: string, item_id: string, mastered: boolean) =>
    put<Checklist>(`/api/exams/checklist?${qs({ topic })}`, { item_id, mastered }),
  studyGuide: (paths: string[]) =>
    post<{ markdown: string; saved_path?: string }>('/api/llm/study-guide', { paths }),

  // 备考目标
  goals: () => http<{ goals: Goal[] }>('/api/goals'),
  addGoal: (title: string, date: string, topic: string) => post<Goal>('/api/goals', { title, date, topic }),
  deleteGoal: (id: string) => del<unknown>(`/api/goals/${id}`),

  // 导入 / 导出
  importPdf: async (file: File, topic: string, name: string) => {
    const form = new FormData()
    form.append('file', file)
    form.append('topic', topic)
    form.append('name', name)
    const resp = await fetch('/api/import/pdf', { method: 'POST', body: form })
    if (!resp.ok) {
      const data = await resp.json().catch(() => ({ detail: `HTTP ${resp.status}` }))
      throw new Error(data.detail || '导入失败')
    }
    return resp.json() as Promise<NoteDetail & { pages: number }>
  },
  exportVaultUrl: '/api/export/vault',

  // 设置
  settings: () => http<Settings>('/api/settings'),
  saveProviders: (providers: Provider[]) =>
    put<Settings>('/api/settings/providers', { providers }),
  setActive: (provider_id: string) => put<Settings>('/api/settings/active', { provider_id }),
  saveHighlight: (highlight: Settings['highlight']) => put<Settings>('/api/settings/highlight', highlight),
  saveReader: (reader: Settings['reader']) => put<Settings>('/api/settings/reader', reader),
  saveGraph: (graph: Settings['graph']) => put<Settings>('/api/settings/graph', graph),
}

/** POST 并解析 SSE 流：onDelta 收增量文本，onDone 收结束事件。返回可中断控制器。 */
export function streamSSE(
  url: string,
  body: unknown,
  onDelta: (text: string) => void,
  onDone?: (evt: any) => void,
  onError?: (msg: string) => void,
): { abort: () => void } {
  const ctrl = new AbortController()
  ;(async () => {
    try {
      const resp = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
        signal: ctrl.signal,
      })
      if (!resp.ok || !resp.body) {
        const text = await resp.text().catch(() => '')
        let msg = `HTTP ${resp.status}`
        try { msg = JSON.parse(text).detail || msg } catch { /* keep */ }
        onError?.(msg)
        return
      }
      const reader = resp.body.getReader()
      const dec = new TextDecoder()
      let buf = ''
      for (;;) {
        const { done, value } = await reader.read()
        if (done) break
        buf += dec.decode(value, { stream: true })
        const parts = buf.split('\n\n')
        buf = parts.pop() || ''
        for (const raw of parts) {
          const line = raw.trim()
          if (!line.startsWith('data:')) continue
          try {
            const evt = JSON.parse(line.slice(5).trim())
            if (evt.type === 'delta') onDelta(evt.text)
            else if (evt.type === 'done') onDone?.(evt)
            else if (evt.type === 'error') onError?.(evt.message || '生成失败')
          } catch { /* 跳过不完整块 */ }
        }
      }
    } catch (e: any) {
      if (e.name !== 'AbortError') onError?.(e.message || String(e))
    }
  })()
  return { abort: () => ctrl.abort() }
}

export const llmUrls = {
  chat: '/api/llm/chat',
  generateNote: '/api/llm/generate-note',
  ask: '/api/llm/ask',
  tutorChat: '/api/llm/tutor-chat',
}
