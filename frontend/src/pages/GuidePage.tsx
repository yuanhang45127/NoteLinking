import { useMemo, useState } from 'react'
import type { ReactElement } from 'react'
import { useNavigate } from 'react-router-dom'
import { useApp } from '../store'
import { chatDock } from '../components/chat/chatDockSignal'
import {
  IconBulb, IconChat, IconCheck, IconConcept, IconFilePdf, IconFolder,
  IconGear, IconGrad, IconNote, IconSpark,
} from '../components/Icons'

const LS_STEPS = 'nl-guide-steps'
const LS_SEEN = 'nl-guide-seen'

type StepAction = { label: string; to?: string; openChat?: boolean }

type Step = {
  id: string
  icon: (p: { size?: number }) => ReactElement
  title: string
  body: string
  bullets?: string[]
  actions: StepAction[]
}

const STEPS: Step[] = [
  {
    id: 'topic',
    icon: (p) => <IconFolder {...p} />,
    title: '新建你的第一个主题',
    body: '主题是笔记库的一级分类（高等数学、机器学习、考公……）。在左侧底部输入名称点「创建」即可；学习方向明确的话，直接点「✦ 架构」，AI 会先为这个主题写一份整体架构笔记，再一键按架构生成目录、逐篇生成笔记——从零开始也不慌。',
    bullets: ['主题就是一个普通文件夹，可随时改名、加图标', '「✦ 架构」是 AI 批量生成笔记的唯一入口，在新建主题那一行'],
    actions: [{ label: '去新建主题', to: '/notes' }],
  },
  {
    id: 'note',
    icon: (p) => <IconNote {...p} />,
    title: '攒下第一篇笔记',
    body: '三种方式，可以混着用：让 AI 生成（空主题页有「✦ 用 AI 生成第一篇笔记」，笔记阅读页也能 ✦ 续写本节）；导入 PDF 自动转文本笔记；或者干脆手动写——所有笔记都是普通的 .md 文件，Obsidian 可以直接打开同一文件夹。',
    bullets: ['公式用 LaTeX（$…$），阅读页 KaTeX 实时渲染', '顶部搜索框支持全文搜索，快捷键 n 直达笔记页'],
    actions: [{ label: '去笔记页', to: '/notes' }],
  },
  {
    id: 'read',
    icon: (p) => <IconBulb {...p} />,
    title: '边读边问，读到哪问到哪',
    body: '阅读页里划选任何文字会弹出菜单：「什么意思」「解释选段」「高亮」「加入对话」。解释选段由 AI 流式讲给你听，懂了之后还能一键把讲解存回笔记；「高亮」会记下原文和你的批注，右栏「我的批注」随时回看。',
    bullets: ['所有 AI 生成都能切到后台跑，右下角悬浮窗统一查看进度', '高亮以 sidecar 文件存储，不污染 md 正文'],
    actions: [{ label: '打开一篇笔记试试', to: '/notes' }],
  },
  {
    id: 'concept',
    icon: (p) => <IconConcept {...p} />,
    title: '概念双链，让知识长成网',
    body: '遇到陌生名词，划选后点「什么意思」，AI 会结合上下文生成概念文档，存进主题的 terms/ 目录。之后正文里这个词会自动变成紫色链接：悬浮看一句话解释，点击进概念页，顶部「返回出处」一键回到原笔记。',
    bullets: ['概念页之间也可以用 [[双链]] 互链', '知识图谱全部由双链自动生成，不用手动画'],
    actions: [{ label: '去笔记里划个词', to: '/notes' }, { label: '看看知识图谱', to: '/graph' }],
  },
  {
    id: 'chat',
    icon: (p) => <IconChat {...p} />,
    title: '随身 AI 助教',
    body: '右上角对话按钮（或按 c）打开 AI 对话面板，直接问 anything：「泰勒公式和拉格朗日余项什么关系？」「给我讲讲这篇文章的第三小节」。阅读页划选的「加入对话」会把原文引用塞进下一轮提问，AI 始终带着笔记上下文回答。',
    bullets: ['顶栏可随时切换 AI 模型，对所有 AI 功能生效', '备考页还有「助教模式」，回答直指考点'],
    actions: [{ label: '打开 AI 对话', openChat: true }],
  },
  {
    id: 'exam',
    icon: (p) => <IconGrad {...p} />,
    title: '出题自测，把「懂了」变成分数',
    body: '考试备考页（快捷键 e）：左侧勾选资料，告诉 AI「出 5 道选择题，难度中等」就能即席测验；也可以生成正式试卷——逐题作答、交卷判分（选择题自动判，简答题大模型评阅）、逐题解析。配套还有记忆闪卡、考点清单（标记掌握算覆盖度）和学习指南。',
    bullets: ['考点清单按重要度排序，覆盖度一目了然', '试卷和成绩都会保存，可反复重练'],
    actions: [{ label: '去考试备考', to: '/exam' }],
  },
  {
    id: 'papers',
    icon: (p) => <IconFilePdf {...p} />,
    title: '文献库（可选）',
    body: '做研究的话：arXiv 检索一键收录，Zotero 增量同步（PDF 走 arXiv 直下，不烧配额），阅读页内嵌分栏读 PDF，正文提取一键转成笔记——转出来的笔记和手写笔记同一套体系，可以直接进备考、进图谱。',
    actions: [{ label: '去文献库', to: '/papers' }],
  },
  {
    id: 'model',
    icon: (p) => <IconGear {...p} />,
    title: '接上你自己的 AI 模型',
    body: '设置 → AI 模型：填入任意 OpenAI 兼容接口（OpenAI / DeepSeek / Qwen / GLM / Kimi / OpenRouter / Ollama / LM Studio……）或 Anthropic、Gemini。可以配多家、设默认模型，顶栏随时切换——模型会过时，你的笔记库不会。',
    bullets: ['API Key 只存在你自己的服务器上', '配置 Kimi Code 后，还能在本机把 Kimi Code Agent 嵌进对话面板'],
    actions: [{ label: '去配置模型', to: '/settings?tab=model' }],
  },
]

const SHORTCUTS: [string, string][] = [
  ['n', '笔记'], ['g', '知识图谱'], ['e', '考试备考'], ['s', '设置'], ['c', 'AI 对话面板'],
]

function loadDone(): string[] {
  try { return JSON.parse(localStorage.getItem(LS_STEPS) || '[]') } catch { return [] }
}

export default function GuidePage() {
  const navigate = useNavigate()
  const { toast } = useApp()
  const [done, setDone] = useState<string[]>(loadDone)
  const doneSet = useMemo(() => new Set(done), [done])

  const toggle = (id: string) => {
    setDone((s) => {
      const next = s.includes(id) ? s.filter((x) => x !== id) : [...s, id]
      localStorage.setItem(LS_STEPS, JSON.stringify(next))
      return next
    })
  }

  const run = (a: StepAction) => {
    if (a.openChat) { chatDock.set(true); return }
    if (a.to) navigate(a.to)
  }

  const jump = (id: string) => {
    document.getElementById(`guide-${id}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  const finish = () => {
    localStorage.setItem(LS_STEPS, JSON.stringify(STEPS.map((s) => s.id)))
    localStorage.setItem(LS_SEEN, '1')
    toast('已完成新手引导，开始你的学习吧 🎉')
    navigate('/notes')
  }

  const allDone = done.length >= STEPS.length

  return (
    <div className="settings-layout guide-layout">
      <nav className="settings-nav guide-nav">
        <div className="guide-progress">
          <div className="gp-num">{done.length} / {STEPS.length}</div>
          <div className="gp-label">已完成</div>
          <div className="gp-bar"><i style={{ width: `${(done.length / STEPS.length) * 100}%` }} /></div>
        </div>
        {STEPS.map((s, i) => (
          <button key={s.id} className={`nav-item ${doneSet.has(s.id) ? 'done' : ''}`}
            onClick={() => jump(s.id)}>
            {doneSet.has(s.id) ? <IconCheck size={14} /> : <span className="gn">{i + 1}</span>}
            {s.title}
          </button>
        ))}
      </nav>

      <div className="settings-panel">
        <section className="settings-card guide-hero">
          <div className="gh-badge"><IconSpark size={15} /> 新手指引</div>
          <h2>从零开始，享受 AI 学习</h2>
          <p>
            墨链 NoteLink 是一个基于 Markdown 文件的开源 AI 笔记系统：数据就是你的笔记文件夹（Obsidian 兼容），AI 负责生成、讲解与陪练。跟着下面 8 步走一遍，十分钟上手；每步做完可以勾掉，进度会自动保存在本机。
          </p>
        </section>

        {STEPS.map((s, i) => (
          <section key={s.id} id={`guide-${s.id}`} className={`settings-card guide-step ${doneSet.has(s.id) ? 'done' : ''}`}>
            <div className="gs-head">
              <span className="gs-num">{i + 1}</span>
              <span className="gs-icon">{s.icon({ size: 19 })}</span>
              <h3>{s.title}</h3>
              <button className={`btn small ${doneSet.has(s.id) ? 'done' : ''}`} onClick={() => toggle(s.id)}>
                {doneSet.has(s.id) ? '✓ 已完成' : '标记完成'}
              </button>
            </div>
            <p className="gs-body">{s.body}</p>
            {!!s.bullets?.length && (
              <ul className="gs-bullets">
                {s.bullets.map((b, j) => <li key={j}>{b}</li>)}
              </ul>
            )}
            {!!s.actions.length && (
              <div className="gs-actions">
                {s.actions.map((a) => (
                  <button key={a.label} className="btn small" onClick={() => run(a)}>{a.label} →</button>
                ))}
              </div>
            )}
          </section>
        ))}

        <section className="settings-card">
          <h3>快捷键速查</h3>
          <p className="desc">在任意页面（输入框外）按下面的键即可跳转。</p>
          <div className="guide-keys">
            {SHORTCUTS.map(([k, label]) => (
              <div key={k} className="gk-row">
                <span className="kbd">{k}</span>
                <span>{label}</span>
              </div>
            ))}
          </div>
        </section>

        <section className="settings-card guide-finish">
          <div>
            <h3>{allDone ? '全部完成，恭喜！' : '差不多了'}</h3>
            <p className="desc">
              {allDone
                ? '基础功能都过了一遍。学习路上随时可以在左侧「新手指引」回到这一页。'
                : '不着急全做完，先去用用看——侧边栏随时能找回这一页。'}
            </p>
          </div>
          <button className="btn primary" onClick={finish}>{allDone ? '开始我的学习 →' : '完成引导，开始用 →'}</button>
        </section>
      </div>
    </div>
  )
}

// GuideWelcome 也用到这个 key，导出保持一致
export { LS_SEEN as GUIDE_SEEN_KEY }
