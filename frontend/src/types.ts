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
  children?: TreeNode[]
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
