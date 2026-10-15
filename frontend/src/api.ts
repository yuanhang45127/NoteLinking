// 后端 API 客户端 + SSE 流式工具
import type {
  Annotation, ArxivResult, BookMeta, ChatSession, ChatSessionMeta, Checklist, Exam, Goal, GraphData, ImportBookResult, KimiWebStatus, McpServer, NoteDetail, NoteLinkItem, Paper, PinnedNote, Provider, Settings,
  Topic, TreeNode, ZoteroCollection, ZoteroConfig, ZoteroSyncResult,
} from './types'

async function http<T>(url: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {}
  if (init?.body) headers['Content-Type'] = 'application/json'
  const token = localStorage.getItem('nl-token')
  if (token) headers['X-Notebook-Token'] = token
  const resp = await fetch(url, { ...init, headers: { ...headers, ...init?.headers } })
  if (!resp.ok) {
    let detail = `HTTP ${resp.status}`
    try {
      const data = await resp.json()
      detail = data.detail || detail
    } catch { /* ignore */ }
    const err = new Error(detail) as Error & { code?: number }
    err.code = resp.status
    throw err
  }
  return resp.json()
}

const post = <T>(url: string, body: unknown) =>
  http<T>(url, { method: 'POST', body: JSON.stringify(body) })
const put = <T>(url: string, body: unknown) =>
  http<T>(url, { method: 'PUT', body: JSON.stringify(body) })
const patch = <T>(url: string, body: unknown) =>
  http<T>(url, { method: 'PATCH', body: JSON.stringify(body) })
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
  renameTopic: (name: string, newName: string) =>
    patch<Topic>(`/api/topics/${encodeURIComponent(name)}`, { name: newName }),
  setTopicEmoji: (name: string, emoji: string) =>
    put<{ name: string; emoji: string }>(`/api/topics/${encodeURIComponent(name)}/emoji`, { emoji }),
  deleteTopic: (name: string, recursive = false) =>
    del<unknown>(`/api/topics/${encodeURIComponent(name)}?recursive=${recursive}`),
  // 文献库（Zotero 思路：检索收录 / 状态 / 标签 / 想法）
  papers: (topic: string) => http<{ papers: Paper[] }>(`/api/papers?${qs({ topic })}`),
  addPaper: (topic: string, paper: unknown) => post<Paper>(`/api/papers?${qs({ topic })}`, paper),
  updatePaper: (topic: string, id: string, patch: unknown) =>
    put<Paper>(`/api/papers/${encodeURIComponent(id)}?${qs({ topic })}`, patch),
  deletePaper: (topic: string, id: string) =>
    del<unknown>(`/api/papers/${encodeURIComponent(id)}?${qs({ topic })}`),
  searchArxiv: (q: string, max_results = 15) =>
    http<{ results: ArxivResult[] }>(`/api/papers/search-arxiv?${qs({ q, max_results })}`),
  // Zotero 同步
  zoteroConfig: () => http<ZoteroConfig>('/api/papers/zotero/config'),
  saveZoteroConfig: (cfg: Partial<ZoteroConfig>) =>
    put<ZoteroConfig>('/api/papers/zotero/config', cfg),
  zoteroStatus: () =>
    http<{ ok: boolean; collections: ZoteroCollection[]; config: ZoteroConfig }>('/api/papers/zotero/status'),
  zoteroSync: (body: { topic: string; download_pdf?: boolean }) =>
    post<ZoteroSyncResult>('/api/papers/zotero/sync', body),
  fetchPaperPdf: (topic: string, id: string) =>
    post<{ pdf_path: string; url: string }>(`/api/papers/${encodeURIComponent(id)}/fetch-pdf?${qs({ topic })}`, {}),
  importPaperText: (topic: string, id: string) =>
    post<NoteDetail>(`/api/papers/${encodeURIComponent(id)}/import-text?${qs({ topic })}`, {}),
  // 非流式生成笔记（用于文献阅读笔记等程序化调用）
  generateNote: (body: { topic: string; prompt: string; title?: string; save_path?: string }) =>
    post<{ text: string; saved_path?: string }>('/api/llm/generate-note', body),
  // 按整体架构「建议知识架构」生成主题目录骨架
  scaffoldTopic: (topic: string, savePath?: string) =>
    post<{ created: string[]; skipped: string[] }>('/api/llm/topic-architecture/scaffold', { topic, save_path: savePath || '' }),
  tree: (path = '') => http<TreeNode>(`/api/tree?${qs({ path })}`),

  // 模型列表（从服务商接口实时拉取）
  llmModels: (provider?: string) =>
    http<{ models: string[] }>(`/api/llm/models?${qs({ provider })}`),

  // 笔记
  note: (path: string) => http<NoteDetail>(`/api/notes?${qs({ path })}`),
  createNote: (path: string, content = '', overwrite = false) => post<NoteDetail>('/api/notes', { path, content, overwrite }),
  saveNote: (path: string, content: string) => put<NoteDetail>('/api/notes', { path, content }),
  pinned: () => http<{ pinned: PinnedNote[] }>('/api/pinned'),
  setNotePin: (path: string, pinned: boolean) => post<NoteDetail>('/api/notes/pin', { path, pinned }),
  setNoteFinish: (path: string, finished: boolean) => post<NoteDetail>('/api/notes/finish', { path, finished }),
  deleteNote: (path: string) => del<unknown>(`/api/notes?${qs({ path })}`),
  moveNote: (src: string, dst: string) => post<NoteDetail>('/api/notes/move', { src, dst }),
  batchNotes: (action: 'delete' | 'move', paths: string[], target?: string) =>
    post<{ ok: string[]; failed: { path: string; detail: string }[] }>('/api/notes/batch', { action, paths, target }),
  backlinks: (path: string) =>
    http<{ backlinks: NoteDetail['backlinks'] }>(`/api/notes/backlinks?${qs({ path })}`),
  search: (q: string, topic?: string) =>
    http<{ results: { path: string; name: string; title: string; snippet: string }[] }>(
      `/api/search?${qs({ q, topic })}`),
  resolveLink: (target: string, topic?: string) =>
    http<NoteDetail>(`/api/notes/resolve-link?${qs({ target, topic })}`),

  // 参考链接（frontmatter links）
  noteLinks: (path: string) => http<{ links: NoteLinkItem[] }>(`/api/notes/links?${qs({ path })}`),
  addNoteLink: (path: string, url: string, title = '', source = 'manual') =>
    post<{ links: NoteLinkItem[] }>('/api/notes/links', { path, url, title, source }),
  removeNoteLink: (path: string, url: string) =>
    post<{ links: NoteLinkItem[] }>('/api/notes/links/remove', { path, url }),

  // 联网搜索（服务商配置见 设置 → 联网搜索）
  webSearch: (q: string, maxResults?: number) =>
    http<{ provider: string; results: { title: string; url: string; snippet: string }[] }>(
      `/api/web/search?${qs({ q, max_results: maxResults })}`),
  webFetch: (url: string) => post<{ title: string; url: string; text: string }>('/api/web/fetch', { url }),

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
    post<NoteDetail & { is_new: boolean }>('/api/terms', { ...body, ...getModelOverride() }),
  resolveTerm: (name: string, topic?: string) =>
    http<{ found: boolean } & NoteDetail>(`/api/terms/resolve?${qs({ name, topic })}`),

  // 图谱
  graph: (topic?: string) => http<GraphData>(`/api/graph?${qs({ topic })}`),

  // AI 对话
  chatSessions: () => http<{ sessions: ChatSessionMeta[] }>('/api/chat/sessions'),
  chatSession: (id: string) => http<ChatSession>(`/api/chat/sessions/${encodeURIComponent(id)}`),
  createChatSession: (title = '') => post<ChatSession>('/api/chat/sessions', { title }),
  renameChatSession: (id: string, title: string) =>
    patch<ChatSession>(`/api/chat/sessions/${encodeURIComponent(id)}`, { title }),
  deleteChatSession: (id: string) => del<unknown>(`/api/chat/sessions/${encodeURIComponent(id)}`),

  // 笔记追加（对话存入 / AI 工具共用）
  appendToNote: (path: string, text: string, heading = '') =>
    post<NoteDetail>('/api/notes/append', { path, text, heading }),

  // 阅读进度（服务端记忆，打开笔记时定位到上次位置）
  getReadProgress: (path: string) =>
    http<{ ratio: number; heading: string; updated_at: string }>(`/api/notes/read-progress?${qs({ path })}`),
  saveReadProgress: (path: string, ratio: number, heading = '') =>
    put<{ ratio: number; heading: string; updated_at: string }>('/api/notes/read-progress', { path, ratio, heading }),

  // 考试
  generateExam: (body: { paths: string[]; types: string[]; count: number; difficulty: string; title?: string }) =>
    post<Exam>('/api/exams/generate', { ...body, ...getModelOverride() }),
  getExam: (id: string) => http<Exam>(`/api/exams/${id}`),
  submitAttempt: (id: string, answers: { question_id: string; answer: string }[]) =>
    post<Exam['attempts'] extends (infer T)[] | undefined ? T : never>(`/api/exams/${id}/attempts`, { answers, ...getModelOverride() }),
  checklist: (topic: string) => http<{ checklist: Checklist | null }>(`/api/exams/checklist?${qs({ topic })}`),
  generateChecklist: (paths: string[]) => post<Checklist>('/api/exams/checklist', { paths, ...getModelOverride() }),
  toggleChecklist: (topic: string, item_id: string, mastered: boolean) =>
    put<Checklist>(`/api/exams/checklist?${qs({ topic })}`, { item_id, mastered }),
  studyGuide: (paths: string[]) =>
    post<{ markdown: string; saved_path?: string }>('/api/llm/study-guide', { paths, ...getModelOverride() }),

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
    const headers: Record<string, string> = {}
    const token = localStorage.getItem('nl-token')
    if (token) headers['X-Notebook-Token'] = token
    const resp = await fetch('/api/import/pdf', { method: 'POST', body: form, headers })
    if (!resp.ok) {
      const data = await resp.json().catch(() => ({ detail: `HTTP ${resp.status}` }))
      throw new Error(data.detail || '导入失败')
    }
    return resp.json() as Promise<NoteDetail & { pages: number }>
  },

  // 读书笔记：书籍导入与梗概生成
  importBook: async (file: File, topic: string, title = '', author = '') => {
    const form = new FormData()
    form.append('file', file)
    form.append('topic', topic)
    if (title) form.append('title', title)
    if (author) form.append('author', author)
    const headers: Record<string, string> = {}
    const token = localStorage.getItem('nl-token')
    if (token) headers['X-Notebook-Token'] = token
    const resp = await fetch('/api/books/import', { method: 'POST', body: form, headers })
    if (!resp.ok) {
      const data = await resp.json().catch(() => ({ detail: `HTTP ${resp.status}` }))
      throw new Error(data.detail || '导入失败')
    }
    return resp.json() as Promise<ImportBookResult>
  },
  getBook: (id: string) =>
    http<{ book: BookMeta; fmt: string; chapters: { title: string; chars: number }[] }>(
      `/api/books/${encodeURIComponent(id)}`),
  getBookChapter: (id: string, index: number) =>
    http<{ title: string; html: string }>(
      `/api/books/${encodeURIComponent(id)}/chapter/${index}/html`),
  exportVaultUrl:
    '/api/export/vault' +
    (() => {
      const t = localStorage.getItem('nl-token')
      return t ? `?token=${encodeURIComponent(t)}` : ''
    })(),

  // 设置
  settings: () => http<Settings>('/api/settings'),
  saveProviders: (providers: Provider[]) =>
    put<Settings>('/api/settings/providers', { providers }),
  setActive: (provider_id: string) => put<Settings>('/api/settings/active', { provider_id }),
  saveHighlight: (highlight: Settings['highlight']) => put<Settings>('/api/settings/highlight', highlight),
  saveReader: (reader: Settings['reader']) => put<Settings>('/api/settings/reader', reader),
  saveGraph: (graph: Settings['graph']) => put<Settings>('/api/settings/graph', graph),
  saveKimiWeb: (kimi_web: Partial<Settings['kimi_web']>) => put<Settings>('/api/settings/kimi-web', kimi_web),
  saveWebSearch: (cfg: Partial<Settings['web_search']>) => put<Settings>('/api/settings/web-search', cfg),

  // 外部工具集成（本机 Kimi Code Web 探测）
  kimiWebStatus: () => http<KimiWebStatus>('/api/integrations/kimi-web'),

  // 外部 MCP 服务器（stdio）：列表含各 server 的工具与连接错误
  mcpServers: () =>
    http<{ servers: (McpServer & { tools: { name: string; description: string }[]; error: string })[] }>(
      '/api/mcp/servers'),
  mcpCall: (server: string, tool: string, args: Record<string, unknown> = {}) =>
    post<{ result: { content: { type: string; text: string }[]; isError: boolean } }>(
      '/api/mcp/call', { server, tool, arguments: args }),
  saveMcpServers: (servers: McpServer[]) =>
    put<Settings>('/api/settings/mcp-servers', { mcp_servers: servers }),

  // 账号（会话走 HttpOnly Cookie，无需手动携带）
  authStatus: () =>
    http<{ mode: 'open' | 'multi'; user: string | null; users: number; email_verify?: boolean }>('/api/auth/status'),
  login: (username: string, password: string) =>
    post<{ username: string }>('/api/auth/login', { username, password }),
  register: (username: string, password: string, email = '', code = '') =>
    post<{ username: string }>('/api/auth/register', {
      username, password, email, code,
    }),
  sendEmailCode: (email: string) =>
    post<{ sent: boolean; cooldown: number }>('/api/auth/email-code', { email }),
  logout: () => post<unknown>('/api/auth/logout', {}),
}

/** 全局模型选择（TopBar 切换）：nl-model = { provider, model }；provider 为空表示跟随默认服务商。 */
export function getModelOverride(): { provider?: string; model?: string } {
  try {
    const v = JSON.parse(localStorage.getItem('nl-model') || 'null')
    if (v && typeof v.model === 'string' && v.model) {
      return { provider: v.provider || undefined, model: v.model }
    }
  } catch { /* ignore */ }
  return {}
}

export function setModelOverride(provider: string, model: string) {
  if (model) localStorage.setItem('nl-model', JSON.stringify({ provider, model }))
  else localStorage.removeItem('nl-model')
}

/** POST 并解析 SSE 流：onDelta 收增量文本，onDone 收结束事件，onEvent 收全部原始事件。
 * 返回可中断控制器。 */export function streamSSE(
  url: string,
  body: unknown,
  onDelta: (text: string) => void,
  onDone?: (evt: any) => void,
  onError?: (msg: string) => void,
  onEvent?: (evt: any) => void,
): { abort: () => void } {
  const ctrl = new AbortController()
  ;(async () => {
    try {
      const headers: Record<string, string> = { 'Content-Type': 'application/json' }
      const token = localStorage.getItem('nl-token')
      if (token) headers['X-Notebook-Token'] = token
      const resp = await fetch(url, {
        method: 'POST',
        headers,
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
            onEvent?.(evt)
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
  tutorChat: '/api/llm/tutor-chat',
}

/** 流式生成接口（SSE，协议同 llmUrls：delta/done/error） */
export const streamUrls = {
  term: '/api/terms/stream',
  examGenerate: '/api/exams/generate/stream',
  attempt: (examId: string) => `/api/exams/${encodeURIComponent(examId)}/attempts/stream`,
  checklist: '/api/exams/checklist/stream',
  studyGuide: '/api/llm/study-guide/stream',
  topicArchitecture: '/api/llm/topic-architecture/stream',
  topicGenerateNotes: '/api/llm/topic-architecture/generate-notes/stream',
  chatTurn: (sessionId: string) => `/api/chat/sessions/${encodeURIComponent(sessionId)}/turn`,
  bookNotes: (bookId: string) => `/api/books/${encodeURIComponent(bookId)}/notes/stream`,
}
