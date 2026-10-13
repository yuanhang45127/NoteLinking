// 与后端 docs/API.md 对应的类型定义
export interface Topic {
  name: string
  path: string
  emoji?: string
  note_count: number
  term_count: number
  updated_at: string
}

export interface TreeNode {
  name: string
  path: string
  type: 'dir' | 'note' | 'term' | 'file'
  title?: string
  finished?: boolean
  children?: TreeNode[]
}

/** 置顶笔记（侧边栏顶部「置顶」区，跨主题） */
export interface PinnedNote {
  path: string
  name: string
  title: string
  topic: string
  type: 'note' | 'term'
  finished?: boolean
  updated_at: string
}

export interface Annotation {
  id: string
  quote: string
  prefix: string
  suffix: string
  occurrence: number
  color: string
  style: 'background' | 'font'
  comment: string
  created_at: string
  updated_at: string
}

export interface Backlink {
  path: string
  id: string
  name: string
  title: string
  type: 'note' | 'term'
  topic: string
  snippet: string
}

export interface ConceptRef {
  name: string
  path: string
  count: number
}

export interface NoteDetail {
  path: string
  name: string
  topic: string
  title: string
  type: 'note' | 'term'
  frontmatter: Record<string, any>
  editable: boolean
  content: string
  updated_at: string
  size: number
  annotations: Annotation[]
  backlinks: Backlink[]
  concept_refs: ConceptRef[]
}

export interface Provider {
  id: string
  type: 'openai' | 'anthropic' | 'gemini'
  name: string
  base_url: string
  api_key: string
  model: string
  models?: string[]
  has_key?: boolean
}

export interface Settings {
  providers: Provider[]
  active_provider: string
  highlight: { color: string; style: 'background' | 'font' }
  reader: { selection_menu: boolean; auto_concept: boolean; context_scope: string }
  graph: { default_filter: 'all' | 'note' | 'term'; show_missing: boolean }
  exam: { default_count: number; types: string[]; difficulty: string }
  language: string
  supported_types?: string[]
}

export interface GraphNode {
  id: string
  label: string
  name: string
  type: 'note' | 'term' | 'missing'
  topic: string
  path: string
  degree: number
}

export interface GraphEdge {
  source: string
  source_name: string
  target: string
  target_name: string
}

export interface GraphData {
  topic: string
  generated_at: string
  nodes: GraphNode[]
  edges: GraphEdge[]
}

export interface Question {
  id: string
  type: 'mcq' | 'short' | 'flashcard'
  question?: string
  options?: string[]
  answer?: string
  reference_answer?: string
  explanation?: string
  front?: string
  back?: string
}

export interface AttemptAnswer {
  question_id: string
  type: string
  answer: string
  correct?: boolean
  score: number | null
  reference?: string
  feedback?: string
}

export interface Attempt {
  id: string
  submitted_at: string
  answers: AttemptAnswer[]
  total_score: number | null
}

export interface Exam {
  id: string
  title: string
  created_at: string
  scope: { paths: string[]; titles: string[] }
  settings: { types: string[]; count: number; difficulty: string; language: string }
  questions: Question[]
  attempts?: Attempt[]
}

export interface Goal {
  id: string
  title: string
  date: string
  topic: string
}

export interface ChecklistItem {
  id: string
  point: string
  importance: string
  suggestion: string
  mastered: boolean
}

export interface Checklist {
  topic: string
  scope: { paths: string[]; titles: string[] }
  items: ChecklistItem[]
  created_at: string
}

export interface ChatMsg {
  role: 'user' | 'assistant' | 'system'
  content: string
  quizExamId?: string
  quizSummary?: string
}

// ---- AI 对话 ----
export interface ChatToolStep {
  name: string
  args: Record<string, any>
  summary: string
  ok: boolean
  /** 流式中刚发起、还没返回结果的步骤 */
  running?: boolean
}

export interface ChatSessionMsg {
  role: 'user' | 'assistant' | 'system'
  content: string
  created_at?: string
  tool_steps?: ChatToolStep[]
}

export interface ChatSessionMeta {
  id: string
  title: string
  created_at: string
  updated_at: string
  message_count: number
}

export interface ChatSession extends ChatSessionMeta {
  messages: ChatSessionMsg[]
}

export type PaperStatus = 'unread' | 'reading' | 'done'

export interface Paper {
  id: string
  topic: string
  /** paper | book（读书笔记的书目） */
  kind?: 'paper' | 'book'
  book_id?: string
  title: string
  authors: string[]
  year: string
  venue: string
  abstract: string
  doi: string
  arxiv_id: string
  url: string
  pdf: string
  tags: string[]
  status: PaperStatus
  comment: string
  added_at: string
  pdf_path?: string
  pdf_downloaded_at?: string
}

export interface ZoteroConfig {
  user_id: string
  api_key: string
  collection: string
  collection_name: string
  base_url: string
  download_pdf: boolean
  has_key?: boolean
}

export interface ZoteroCollection {
  key: string
  name: string
  num_items: number
}

// ---- 读书笔记 ----
export interface BookMeta {
  id: string
  title: string
  author: string
  topic: string
  created_at: string
  meta: { chunked?: boolean; hint?: string; pages?: number }
}

export interface ImportBookResult {
  book: BookMeta
  chapters: { title: string; chars: number }[]
  paper: Paper | null
}

export interface ZoteroSyncResult {
  topic: string
  fetched: number
  added: number
  skipped: number
  pdf_downloaded: number
  pdf_failed: number
  last_version: number
  synced_at: string
}

export interface ArxivResult {
  title: string
  authors: string[]
  year: string
  venue: string
  abstract: string
  arxiv_id: string
  url: string
  pdf: string
  published: string
  categories: string[]
}
