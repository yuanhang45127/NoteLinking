import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api, getModelOverride, llmUrls, streamSSE, streamUrls } from '../api'
import { useApp } from '../store'
import type { Attempt, ChatMsg, Checklist, Exam, Goal, Question, TreeNode } from '../types'
import Modal from '../components/Modal'
import { renderMarkdown } from '../lib/md'
import {
  IconCard, IconCheck, IconConcept, IconDoc, IconFilePdf, IconList,
  IconSend, IconSpark, IconWand,
} from '../components/Icons'

const TYPE_LABEL: Record<string, string> = { mcq: '选择题', short: '简答题', flashcard: '闪卡' }

export default function ExamPage() {
  const { activeTopic, tree, refreshTree, toast } = useApp()
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [goals, setGoals] = useState<Goal[]>([])
  const [checklist, setChecklist] = useState<Checklist | null>(null)
  const [messages, setMessages] = useState<ChatMsg[]>([
    { role: 'assistant', content: '你好，我是 AI 助教。勾选左侧资料后，可以让我出题、划重点，也可以直接提问。' },
  ])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [quiz, setQuiz] = useState<{ exam: Exam; label: string } | null>(null)
  const [cards, setCards] = useState<Question[] | null>(null)
  const [guideOpen, setGuideOpen] = useState<string | null>(null)
  const [checklistOpen, setChecklistOpen] = useState(false)
  const [quizModal, setQuizModal] = useState<null | 'smart' | 'mock'>(null)
  const [genState, setGenState] = useState<{ label: string; text: string } | null>(null)
  const chatEnd = useRef<HTMLDivElement>(null)

  const allNotes = useMemo(() => {
    const out: TreeNode[] = []
    const walk = (n: TreeNode | null) => {
      if (!n?.children) return
      for (const c of n.children) {
        if (c.type === 'note' || c.type === 'term') out.push(c)
        else if (c.type === 'dir') walk(c)
      }
    }
    walk(tree)
    return out
  }, [tree])

  const selectedPaths = useMemo(() => allNotes.filter((n) => selected.has(n.path)).map((n) => n.path), [allNotes, selected])

  useEffect(() => {
    // 默认全选（上限 8 篇）
    setSelected(new Set(allNotes.slice(0, 8).map((n) => n.path)))
  }, [tree]) // eslint-disable-line

  const loadGoals = useCallback(async () => {
    try { setGoals((await api.goals()).goals) } catch { /* ignore */ }
  }, [])
  const loadChecklist = useCallback(async () => {
    if (!activeTopic) return
    try { setChecklist((await api.checklist(activeTopic)).checklist) } catch { /* ignore */ }
  }, [activeTopic])
  useEffect(() => { loadGoals(); loadChecklist() }, [loadGoals, loadChecklist])
  useEffect(() => { chatEnd.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages])

  const toggle = (path: string) => {
    setSelected((s) => {
      const next = new Set(s)
      next.has(path) ? next.delete(path) : next.add(path)
      return next
    })
  }

  /* ---------- 出题 / 生成（全部流式） ---------- */
  const generate = (opts: { types: string[]; count: number; difficulty: string; label: string }) => {
    if (!selectedPaths.length) { toast('请先勾选至少一份资料', 'err'); return }
    setBusy(true)
    setGenState({ label: opts.label, text: '' })
    streamSSE(streamUrls.examGenerate, {
      paths: selectedPaths, types: opts.types, count: opts.count,
      difficulty: opts.difficulty, stream: true, ...getModelOverride(),
    },
      (t) => setGenState((s) => (s ? { ...s, text: s.text + t } : s)),
      async (evt) => {
        setGenState(null); setBusy(false)
        if (!evt?.exam_id) { toast('生成失败，请重试', 'err'); return }
        const exam: Exam = await api.getExam(evt.exam_id)
        setMessages((m) => [...m, {
          role: 'assistant',
          content: `好的，已基于${exam.scope.titles.slice(0, 3).map((t) => `《${t}》`).join('')}生成 ${exam.questions.length} 道题（${opts.types.map((t) => TYPE_LABEL[t] || t).join('、')}，难度 ${opts.difficulty}）。`,
          quizExamId: exam.id, quizSummary: exam.title,
        }])
        setQuiz({ exam, label: opts.label })
      },
      (msg) => { setGenState(null); setBusy(false); toast(msg, 'err') })
  }

  const send = async () => {
    const text = input.trim()
    if (!text || busy) return
    setInput('')
    setMessages((m) => [...m, { role: 'user', content: text }])

    // 出图意图 → 直接生成
    const count = Number(text.match(/(\d+)\s*(道|题)/)?.[1] || 0)
    const isQuiz = /出题|测验|考考|题目|试卷/.test(text)
    if (isQuiz && selectedPaths.length) {
      const types = /闪卡|卡片/.test(text) ? ['flashcard'] : /简答|填空/.test(text) ? ['short'] : ['mcq', 'short']
      await generate({ types, count: count || 5, difficulty: /难|hard/.test(text) ? 'hard' : /简单|easy/.test(text) ? 'easy' : 'medium', label: '随堂测验' })
      return
    }

    if (!selectedPaths.length) { toast('请先勾选资料', 'err'); return }
    setBusy(true)
    setMessages((m) => [...m, { role: 'assistant', content: '' }])
    streamSSE(llmUrls.tutorChat, { paths: selectedPaths, messages: [...messages, { role: 'user', content: text }].slice(-10).map((x) => ({ role: x.role, content: x.content })), stream: true, ...getModelOverride() },
      (t) => setMessages((m) => { const c = [...m]; c[c.length - 1] = { ...c[c.length - 1], content: c[c.length - 1].content + t }; return c }),
      () => setBusy(false),
      (msg) => { setBusy(false); toast(msg, 'err') })
  }

  const quickChecklist = () => {
    if (!selectedPaths.length) { toast('请先勾选资料', 'err'); return }
    setBusy(true)
    setGenState({ label: '考点清单', text: '' })
    streamSSE(streamUrls.checklist, { paths: selectedPaths, stream: true, ...getModelOverride() },
      (t) => setGenState((s) => (s ? { ...s, text: s.text + t } : s)),
      (evt) => {
        setGenState(null); setBusy(false)
        if (evt?.checklist) { setChecklist(evt.checklist); setChecklistOpen(true) }
        else toast('生成失败，请重试', 'err')
      },
      (msg) => { setGenState(null); setBusy(false); toast(msg, 'err') })
  }

  const quickGuide = () => {
    if (!selectedPaths.length) { toast('请先勾选资料', 'err'); return }
    setBusy(true)
    setGenState({ label: '学习指南', text: '' })
    streamSSE(streamUrls.studyGuide, { paths: selectedPaths, stream: true, ...getModelOverride() },
      (t) => setGenState((s) => (s ? { ...s, text: s.text + t } : s)),
      (evt) => {
        setGenState(null); setBusy(false)
        if (evt?.markdown) setGuideOpen(evt.markdown)
        else toast('生成失败，请重试', 'err')
      },
      (msg) => { setGenState(null); setBusy(false); toast(msg, 'err') })
  }

  const openFlashcards = () => {
    if (!selectedPaths.length) { toast('请先勾选资料', 'err'); return }
    setBusy(true)
    setGenState({ label: '记忆闪卡', text: '' })
    streamSSE(streamUrls.examGenerate, {
      paths: selectedPaths, types: ['flashcard'], count: 8,
      difficulty: 'medium', stream: true, ...getModelOverride(),
    },
      (t) => setGenState((s) => (s ? { ...s, text: s.text + t } : s)),
      async (evt) => {
        setGenState(null); setBusy(false)
        if (!evt?.exam_id) { toast('生成失败，请重试', 'err'); return }
        const exam: Exam = await api.getExam(evt.exam_id)
        setCards(exam.questions.filter((q) => q.type === 'flashcard'))
      },
      (msg) => { setGenState(null); setBusy(false); toast(msg, 'err') })
  }

  const masteredCount = checklist?.items.filter((i) => i.mastered).length ?? 0
  const coverage = checklist?.items.length ? Math.round((masteredCount / checklist.items.length) * 100) : 0
  const weak = checklist?.items.filter((i) => !i.mastered).slice(0, 3).map((i) => i.point.slice(0, 6)).join('、')

  return (
    <div className="exam-layout">
      {/* 左：资料与目标 */}
      <div className="exam-col-side">
        <div className="exam-card">
          <div className="card-head-row">
            <h4>资料来源</h4>
            <span className="count">已选 {selected.size} / {allNotes.length}</span>
          </div>
          <div style={{ maxHeight: 300, overflow: 'auto' }}>
            {allNotes.map((n) => (
              <label key={n.path} className="check-row" style={{ cursor: 'pointer' }}>
                <input type="checkbox" checked={selected.has(n.path)} onChange={() => toggle(n.path)} />
                {n.type === 'term' ? <IconConcept size={15} className="icon-concept" /> : <IconDoc size={15} className="icon-note" />}
                <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{n.title}</span>
              </label>
            ))}
            {!allNotes.length && <div className="rail-empty">这个主题还没有资料</div>}
          </div>
          <hr style={{ border: 0, borderTop: '1px solid var(--border)', margin: '12px 0' }} />
          <label className="dashed-btn" style={{ cursor: 'pointer' }}>
            <IconFilePdf size={17} /> 导入 PDF · 自动转文本
            <input type="file" accept="application/pdf" style={{ display: 'none' }}
              onChange={async (e) => {
                const f = e.target.files?.[0]
                e.target.value = ''
                if (!f || !activeTopic) return
                try {
                  toast('正在导入并转换 PDF...')
                  const created = await api.importPdf(f, activeTopic, f.name.replace(/\.pdf$/i, ''))
                  toast(`已导入：${created.name}`)
                  await refreshTree()
                  setSelected((s) => new Set([...s, created.path]))
                } catch (e: any) { toast(e.message, 'err') }
              }} />
          </label>
        </div>

        <div className="exam-card">
          <GoalPanel goals={goals} activeTopic={activeTopic} reload={loadGoals} />
        </div>

        {checklist && (
          <div className="coverage-box">
            <div className="cb-title">考点覆盖度</div>
            <div className="progress"><div style={{ width: `${coverage}%` }} /></div>
            <div className="cb-meta">
              已掌握 {coverage}%{weak ? ` · 薄弱环节：${weak}` : ''}
            </div>
            <button className="btn text" style={{ padding: '6px 0 0' }} onClick={() => setChecklistOpen(true)}>查看完整考点清单 →</button>
          </div>
        )}
      </div>

      {/* 中：AI 助教 + 测验 */}
      <div className="exam-col-main">
        <div className="exam-card" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <IconSpark size={17} style={{ color: 'var(--primary)' }} />
          <b>AI 助教</b>
          <span style={{ color: 'var(--muted)', fontSize: 13 }}>已加载 {selected.size} 份资料</span>
        </div>

        <div className="exam-card" style={{ minHeight: 200 }}>
          {messages.map((m, i) => (
            <div key={i} className={`msg ${m.role === 'user' ? 'user' : 'ai'}`}>
              <div className="m-avatar">{m.role === 'user' ? '刘' : <IconWand size={16} />}</div>
              <div className="bubble">
                {m.content || <span className="loading-dot" />}
                {m.quizExamId && (
                  <div className="quick-btns">
                    <button className="btn small primary" onClick={() => { if (m.quizExamId) startQuizById(m.quizExamId, setQuiz, toast, '随堂测验') }}>开始测验</button>
                    <button className="btn small" disabled={busy} onClick={() => generate({ types: ['short'], count: 5, difficulty: 'medium', label: '随堂测验' })}>换成简答题</button>
                    <button className="btn small" disabled={busy} onClick={() => generate({ types: ['mcq', 'short'], count: 8, difficulty: 'hard', label: '随堂测验' })}>出得更难</button>
                  </div>
                )}
              </div>
            </div>
          ))}
          <div ref={chatEnd} />
        </div>

        {quiz && <QuizRunner key={quiz.exam.id} exam={quiz.exam} label={quiz.label} onClose={() => setQuiz(null)} toast={toast} />}

        <div className="chat-input-row">
          <input placeholder="向 AI 提问，或让它出题、划重点、生成学习指南..." value={input}
            onChange={(e) => setInput(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && send()} />
          <button className="btn primary" onClick={send} disabled={busy || !input.trim()}><IconSend size={16} /></button>
        </div>
      </div>

      {/* 右：备考工具 */}
      <div className="exam-col-tools">
        <button className="tool-card" onClick={() => setQuizModal('smart')} disabled={busy}>
          <span className="t-ic"><IconList size={17} /></span>
          <span><span className="t-name">智能测验</span><span className="t-desc" style={{ display: 'block' }}>按资料自动出题</span></span>
        </button>
        <button className="tool-card" onClick={openFlashcards} disabled={busy}>
          <span className="t-ic"><IconCard size={17} /></span>
          <span><span className="t-name">记忆闪卡</span><span className="t-desc" style={{ display: 'block' }}>概念正反面速记</span></span>
        </button>
        <button className="tool-card" onClick={quickChecklist} disabled={busy}>
          <span className="t-ic"><IconCheck size={17} /></span>
          <span><span className="t-name">考点清单</span><span className="t-desc" style={{ display: 'block' }}>按重要度排序</span></span>
        </button>
        <button className="tool-card" onClick={() => setQuizModal('mock')} disabled={busy}>
          <span className="t-ic"><IconDoc size={17} /></span>
          <span><span className="t-name">模拟试卷</span><span className="t-desc" style={{ display: 'block' }}>限时整卷练习</span></span>
        </button>
        <button className="tool-card" onClick={quickGuide} disabled={busy}>
          <span className="t-ic"><IconSpark size={17} /></span>
          <span><span className="t-name">学习指南</span><span className="t-desc" style={{ display: 'block' }}>一键汇总重点</span></span>
        </button>
        <div className="tools-note">所有备考内容均由已勾选的资料与概念文档生成。</div>
      </div>

      {/* 弹窗 */}
      {genState && (
        <Modal title={`正在生成 · ${genState.label}`} onClose={() => setGenState(null)} wide
          ops={<span style={{ marginRight: 'auto', fontSize: 13, color: 'var(--muted)' }}>流式生成中…</span>}>
          <div className={`stream-box ${!genState.text ? 'loading-dot' : ''}`} style={{ maxHeight: 420, overflow: 'auto' }}>
            {genState.text || ' '}
          </div>
          <div className="rail-note" style={{ marginTop: 8 }}>
            上面是模型的原始输出（出卷/清单为 JSON），仅作进度展示；完成后自动解析并打开。
          </div>
        </Modal>
      )}

      {quizModal && (
        <QuizModal mode={quizModal} onClose={() => setQuizModal(null)} onGenerate={async (opts) => {
          setQuizModal(null)
          await generate({ ...opts, label: quizModal === 'mock' ? '模拟试卷' : '随堂测验' })
        }} />
      )}

      {cards && <Flashcards questions={cards} onClose={() => setCards(null)} />}

      {checklistOpen && checklist && (
        <Modal title="考点清单 · 按重要度排序" onClose={() => setChecklistOpen(false)} wide
          ops={<button className="btn" onClick={() => setChecklistOpen(false)}>关闭</button>}>
          {checklist.items.map((it) => (
            <div key={it.id} className="setting-line" style={{ borderBottom: '1px solid var(--border)' }}>
              <div>
                <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                  <span className="tag" style={it.importance === '高' ? {} : { background: '#f1f2f6', color: 'var(--muted)' }}>{it.importance}</span>
                  <b style={{ fontSize: 14 }}>{it.point}</b>
                </div>
                <div className="sl-sub">{it.suggestion}</div>
              </div>
              <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, color: 'var(--muted)' }}>
                <input type="checkbox" checked={it.mastered} onChange={async (e) => {
                  try {
                    setChecklist(await api.toggleChecklist(checklist.topic, it.id, e.target.checked))
                  } catch (e: any) { toast(e.message, 'err') }
                }} />
                已掌握
              </label>
            </div>
          ))}
        </Modal>
      )}

      {guideOpen && (
        <Modal title="备考学习指南" onClose={() => setGuideOpen(null)} wide
          ops={
            <>
              <button className="btn primary" style={{ marginRight: 'auto' }} onClick={async () => {
                try {
                  await api.createNote(`${activeTopic}/_备考/学习指南-${new Date().toISOString().slice(0, 10)}.md`, guideOpen)
                  toast('已保存为笔记'); refreshTree(); setGuideOpen(null)
                } catch (e: any) { toast(e.message, 'err') }
              }}>保存为笔记</button>
              <button className="btn" onClick={() => setGuideOpen(null)}>关闭</button>
            </>
          }>
          <div className="md-body" style={{ fontSize: 14 }} dangerouslySetInnerHTML={{ __html: renderMarkdown(guideOpen) }} />
        </Modal>
      )}
    </div>
  )

  async function startQuizById(id: string, setQuiz: any, toast: any, label: string) {
    try { setQuiz({ exam: await api.getExam(id), label }) } catch (e: any) { toast(e.message, 'err') }
  }
}

/* ---------------- 备考目标 ---------------- */
function GoalPanel({ goals, activeTopic, reload }: { goals: Goal[]; activeTopic: string; reload: () => void }) {
  const { toast } = useApp()
  const [adding, setAdding] = useState(false)
  const [title, setTitle] = useState('')
  const [date, setDate] = useState('')
  const add = async () => {
    if (!title.trim()) return
    try { await api.addGoal(title.trim(), date, activeTopic); setTitle(''); setDate(''); setAdding(false); reload() }
    catch (e: any) { toast(e.message, 'err') }
  }
  return (
    <>
      <h4>备考目标</h4>
      {goals.map((g, i) => (
        <div key={g.id} className={`goal-item ${i === 0 ? 'cur' : ''}`}>
          <IconDoc size={14} /> {g.title}
          {g.date && <span className="date">{g.date}</span>}
          <button className="del" onClick={async () => { try { await api.deleteGoal(g.id); reload() } catch (e: any) { toast(e.message, 'err') } }}>×</button>
        </div>
      ))}
      {!goals.length && <div className="rail-empty" style={{ marginBottom: 8 }}>添加一个考试日期，倒计时备考。</div>}
      {!adding ? (
        <button className="btn text" style={{ padding: '4px 0' }} onClick={() => setAdding(true)}>＋ 添加目标</button>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <input className="text-input" style={{ width: '100%' }} placeholder="如：机器学习期末" value={title} onChange={(e) => setTitle(e.target.value)} />
          <input className="text-input" style={{ width: '100%' }} placeholder="日期，如 6 月 28 日" value={date} onChange={(e) => setDate(e.target.value)} />
          <div style={{ display: 'flex', gap: 8 }}>
            <button className="btn small primary" onClick={add}>添加</button>
            <button className="btn small" onClick={() => setAdding(false)}>取消</button>
          </div>
        </div>
      )}
    </>
  )
}

/* ---------------- 测验弹窗参数 ---------------- */
function QuizModal({ mode, onClose, onGenerate }: { mode: 'smart' | 'mock'; onClose: () => void; onGenerate: (o: { types: string[]; count: number; difficulty: string }) => void }) {
  const [types, setTypes] = useState<string[]>(mode === 'mock' ? ['mcq', 'short'] : ['mcq', 'short'])
  const [count, setCount] = useState(mode === 'mock' ? 15 : 5)
  const [difficulty, setDifficulty] = useState('medium')
  return (
    <Modal title={mode === 'mock' ? '模拟试卷' : '智能测验'} onClose={onClose}
      ops={<>
        <button className="btn" onClick={onClose}>取消</button>
        <button className="btn primary" onClick={() => onGenerate({ types, count, difficulty })}>生成</button>
      </>}>
      <div className="form-row">
        <label>题型（可多选）</label>
        <div style={{ display: 'flex', gap: 10 }}>
          {(['mcq', 'short', 'flashcard'] as const).map((t) => (
            <label key={t} className="check-row" style={{ border: '1px solid var(--border)', borderRadius: 10, padding: '8px 12px' }}>
              <input type="checkbox" checked={types.includes(t)} disabled={mode === 'mock' && t === 'flashcard'}
                onChange={(e) => setTypes((s) => e.target.checked ? [...s, t] : s.filter((x) => x !== t))} />
              {TYPE_LABEL[t]}
            </label>
          ))}
        </div>
      </div>
      <div className="form-row">
        <label>题目数量</label>
        <input className="text-input" type="number" min={3} max={30} value={count}
          onChange={(e) => setCount(Math.max(3, Math.min(30, Number(e.target.value) || 5)))} />
      </div>
      <div className="form-row">
        <label>难度</label>
        <select className="select-input" style={{ width: '100%' }} value={difficulty} onChange={(e) => setDifficulty(e.target.value)}>
          <option value="easy">简单</option>
          <option value="medium">中等</option>
          <option value="hard">困难</option>
        </select>
      </div>
    </Modal>
  )
}

/* ---------------- 测验执行 ---------------- */
function QuizRunner({ exam, label, onClose, toast }: { exam: Exam; label: string; onClose: () => void; toast: any }) {
  const questions = exam.questions.filter((q) => q.type !== 'flashcard')
  const [idx, setIdx] = useState(0)
  const [answers, setAnswers] = useState<Record<string, string>>({})
  const [showAnalysis, setShowAnalysis] = useState<Record<string, boolean>>({})
  const [result, setResult] = useState<Attempt | null>(null)
  const [submitting, setSubmitting] = useState(false)
  // 流式评卷：简答题完成一题显示一题
  const [grading, setGrading] = useState<{ total: number; rows: Record<string, { score?: number | null; feedback?: string }> } | null>(null)

  if (!questions.length) return null
  const q = questions[idx]
  const isLast = idx === questions.length - 1
  const answeredCount = questions.filter((x) => answers[x.id] !== undefined && answers[x.id] !== '').length

  const submit = () => {
    setSubmitting(true)
    const shortQs = questions.filter((x) => x.type === 'short')
    setGrading({ total: shortQs.length, rows: {} })
    streamSSE(streamUrls.attempt(exam.id), {
      answers: questions.map((x) => ({ question_id: x.id, answer: answers[x.id] || '' })),
    },
      () => { /* 评卷事件走 onEvent */ },
      (evt) => {
        setGrading(null); setSubmitting(false)
        if (evt?.attempt) setResult(evt.attempt as Attempt)
        else toast('评卷失败，请重试', 'err')
      },
      (msg) => { setGrading(null); setSubmitting(false); toast(msg, 'err') },
      (evt) => {
        if (evt?.type === 'grade') {
          setGrading((g) => (g ? {
            total: g.total,
            rows: { ...g.rows, [evt.question_id]: { score: evt.score, feedback: evt.feedback } },
          } : g))
        }
      })
  }

  if (result) {
    return (
      <div className="quiz-card">
        <div className="quiz-head">
          <span className="q-title">{label} · 已完成</span>
          <span className="tag">总分 {result.total_score ?? '—'}</span>
        </div>
        <div style={{ marginTop: 10 }}>
          {result.answers.map((a, i) => {
            const q0 = questions.find((x) => x.id === a.question_id)
            return (
              <div key={a.question_id} style={{ borderBottom: '1px solid var(--border)', padding: '12px 0' }}>
                <div style={{ display: 'flex', gap: 8, alignItems: 'flex-start' }}>
                  <span className="tag" style={a.type === 'mcq' ? (a.correct ? { background: '#e5f6ee', color: 'var(--ok)' } : { background: '#fdeaee', color: 'var(--err)' }) : {}}>{a.type === 'mcq' ? (a.correct ? '正确' : '错误') : `${a.score ?? '—'} 分`}</span>
                  <div style={{ flex: 1 }}>
                    <b style={{ fontSize: 14 }}>{i + 1}. {q0?.question || q0?.front}</b>
                    <div style={{ color: 'var(--muted)', fontSize: 13, marginTop: 4 }}>
                      你的回答：{a.answer || '（未作答）'}
                      {a.reference && <> · 参考：{a.type === 'mcq' ? `${a.reference}. ${q0?.options?.[('ABCD'.indexOf(String(a.reference)))] || ''}` : a.reference.slice(0, 60)}</>}
                    </div>
                    {a.feedback && <div className="quiz-analysis" style={{ marginTop: 8 }}>{a.feedback}</div>}
                  </div>
                </div>
              </div>
            )
          })}
        </div>
        <div className="quiz-nav">
          <button className="btn text" onClick={onClose}>← 返回备考</button>
          <button className="btn primary" onClick={onClose}>完成</button>
        </div>
      </div>
    )
  }

  return (
    <div className="quiz-card">
      <div className="quiz-progress">
        <span className="q-title">{label} · 第 {idx + 1} / {questions.length} 题</span>
        <span className="tag" style={{ marginLeft: 'auto' }}>{TYPE_LABEL[q.type] || q.type}</span>
      </div>
      <div className="progress purple" style={{ marginTop: 8 }}><div style={{ width: `${((idx + 1) / questions.length) * 100}%` }} /></div>

      <div className="quiz-q">{q.question}</div>

      {q.type === 'mcq' && q.options?.map((opt, i) => {
        const key = 'ABCD'[i]
        return (
          <button key={i} className={`quiz-option ${answers[q.id] === key ? 'selected' : ''}`}
            onClick={() => setAnswers((a) => ({ ...a, [q.id]: key }))}>
            <span className="opt-key">{key}</span> · {opt}
            {answers[q.id] === key && <span className="picked">已选</span>}
          </button>
        )
      })}

      {q.type === 'short' && (
        <textarea className="text-input" style={{ width: '100%', minHeight: 110 }}
          placeholder="写下你的回答..." value={answers[q.id] || ''}
          onChange={(e) => setAnswers((a) => ({ ...a, [q.id]: e.target.value }))} />
      )}

      {showAnalysis[q.id] && (
        <div className="quiz-analysis">
          {q.type === 'mcq' && q.answer && <><b>答案：{q.answer}</b> · </>}
          {q.explanation || q.reference_answer || '暂无解析'}
        </div>
      )}

      {grading && (
        <div className="quiz-analysis" style={{ marginTop: 12 }}>
          <b>AI 评卷中…</b>
          <span style={{ marginLeft: 8, color: 'var(--muted)' }}>
            {Object.keys(grading.rows).length}/{grading.total} 已完成
          </span>
          <div style={{ marginTop: 6, display: 'flex', flexDirection: 'column', gap: 4 }}>
            {questions.filter((x) => x.type === 'short').map((x) => {
              const g = grading.rows[x.id]
              return (
                <div key={x.id} style={{ fontSize: 13, color: g ? 'var(--text)' : 'var(--muted)' }}>
                  {g ? `✅ ${(x.question || '').slice(0, 24)}… → ${g.score ?? '?'} 分` : `⏳ ${(x.question || '').slice(0, 24)}…`}
                </div>
              )
            })}
          </div>
        </div>
      )}

      <div className="quiz-nav">
        <button className="btn text" disabled={idx === 0} onClick={() => setIdx((i) => i - 1)}>← 上一题</button>
        <button className="btn text" onClick={() => setShowAnalysis((s) => ({ ...s, [q.id]: !s[q.id] }))}>
          {showAnalysis[q.id] ? '收起解析' : '查看解析'}
        </button>
        {isLast ? (
          <button className="btn primary" disabled={submitting} onClick={submit}>
            {submitting ? (grading ? '评卷中…' : '提交中…') : `交卷（已答 ${answeredCount}/${questions.length}）`}
          </button>
        ) : (
          <button className="btn primary" onClick={() => setIdx((i) => i + 1)}>下一题 →</button>
        )}
      </div>
    </div>
  )
}

/* ---------------- 闪卡 ---------------- */
function Flashcards({ questions, onClose }: { questions: Question[]; onClose: () => void }) {
  const [idx, setIdx] = useState(0)
  const [flipped, setFlipped] = useState(false)
  const q = questions[idx]
  return (
    <Modal title={`记忆闪卡 · ${idx + 1} / ${questions.length}`} onClose={onClose} wide
      ops={<>
        <button className="btn" disabled={idx === 0} onClick={() => { setIdx((i) => i - 1); setFlipped(false) }}>← 上一张</button>
        <button className="btn" onClick={() => setFlipped((f) => !f)}>翻转</button>
        <button className="btn primary" disabled={idx === questions.length - 1} onClick={() => { setIdx((i) => i + 1); setFlipped(false) }}>下一张 →</button>
      </>}>
      <div className={`flashcard-box ${flipped ? 'flipped' : ''}`} onClick={() => setFlipped((f) => !f)}>
        <div className="flashcard-inner">
          <div className="flashcard-face">{q.front || q.question}</div>
          <div className="flashcard-face back">{q.back}</div>
        </div>
      </div>
      <div style={{ textAlign: 'center', color: 'var(--muted)', fontSize: 12.5 }}>点击卡片翻转查看答案</div>
    </Modal>
  )
}
