import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import { useApp } from '../store'
import type { NoteDetail } from '../types'
import { extractWikiTargets, renderMarkdown, splitSections, stripFrontAndH1 } from '../lib/md'
import Modal from '../components/Modal'
import { IconArrowLeft, IconBulb, IconConcept, IconDoc, IconGraph, IconLink, IconRefresh } from '../components/Icons'

export default function ConceptPage() {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const path = params.get('path') || ''
  const { activeTopic, refreshTree, toast } = useApp()
  const [note, setNote] = useState<NoteDetail | null>(null)
  const [backlinks, setBacklinks] = useState<NoteDetail['backlinks']>([])
  const [missing, setMissing] = useState(false)

  const load = useCallback(async () => {
    if (!path) { setMissing(true); return }
    try {
      const n = await api.note(path)
      setNote(n)
      setBacklinks(n.backlinks)
    } catch { setMissing(true) }
  }, [path])

  useEffect(() => { load() }, [load])

  if (missing) return <div className="empty-tip"><div className="big">概念文档不存在</div></div>
  if (!note) return <div className="empty-tip">加载中...</div>

  const fm = note.frontmatter || {}
  const originPath: string = fm.origin_path || ''
  const originName: string = typeof fm.origin === 'string' ? fm.origin.replace(/^\[\[|\]\]$/g, '') : ''
  const originSection: string = fm.origin_section || ''
  const contextQuote: string = fm.context_quote || ''

  const body = stripFrontAndH1(note.content)
  const sections = splitSections(body)
  const get = (title: string) => sections.find((s) => s.title === title || s.title.startsWith(title))?.content || ''
  const oneLine = get('一句话解释')
  const inContext = get('在当前上下文中的含义')
  const math = get('数学形式')
  const others = sections.filter((s) => !['一句话解释', '在当前上下文中的含义', '数学形式'].includes(s.title) && s.title)

  // 相关概念 = 正文双链（去掉自己与出处）
  const relConcepts = extractWikiTargets(body).filter((t) => t !== note.name && t !== originName)

  const regen = async () => {
    if (!originPath) { toast('该概念缺少出处笔记，无法自动重新生成', 'err'); return }
    try {
      toast('正在重新生成解释...')
      await api.createTerm({ path: originPath, term: note.name, regenerate: true })
      toast('已重新生成')
      await load(); refreshTree()
    } catch (e: any) { toast(e.message, 'err') }
  }

  return (
    <div className="page-with-rail">
      <div className="reader">
        {originPath ? (
          <button className="back-origin" onClick={() => navigate(`/notes?path=${encodeURIComponent(originPath)}`)}>
            <IconArrowLeft size={16} /> 返回出处：{originName}{originSection ? ` · ${originSection}` : ''}
          </button>
        ) : originName && (
          <button className="back-origin" onClick={() => navigate('/notes')}><IconArrowLeft size={16} /> 返回笔记</button>
        )}

        <h1 className="note-title">{note.title}</h1>
        <div className="tag-row">
          <span className="tag">概念解释</span>
          <span className="tag ghost">AI 生成</span>
          <span className="sep-info">由「什么意思」创建 · 被 {backlinks.length} 篇笔记引用</span>
        </div>

        {oneLine && (
          <div className="callout">
            <IconBulb size={19} />
            <div>
              <div style={{ fontWeight: 700, marginBottom: 4 }}>一句话解释</div>
              {renderInline(oneLine)}
            </div>
          </div>
        )}

        {contextQuote && (
          <>
            <h2 style={{ fontSize: 19, margin: '22px 0 10px' }}>结合你读到的上下文</h2>
            <blockquote className="context-quote">
              <div className="q">「......{contextQuote.slice(0, 160)}{contextQuote.length > 160 ? '......' : ''}」</div>
              <div className="src">—— {originName}{originSection ? ` · ${originSection}` : ''}</div>
            </blockquote>
          </>
        )}

        {inContext && <MdBlock content={inContext} />}

        {math && (
          <>
            <h2 style={{ fontSize: 19, margin: '22px 0 10px' }}>数学形式</h2>
            <MdBlock content={math} />
          </>
        )}

        {others.map((s) => (
          <div key={s.title}>
            <h2 style={{ fontSize: 19, margin: '22px 0 10px' }}>{s.title}</h2>
            <MdBlock content={s.content} />
          </div>
        ))}

        {!!relConcepts.length && (
          <>
            <h2 style={{ fontSize: 19, margin: '24px 0 4px' }}>相关概念 · 双链</h2>
            <div className="rel-chips">
              {relConcepts.map((t) => (
                <button key={t} className="rel-chip" onClick={() => jumpConcept(t, note.topic, navigate)}>
                  <IconLink size={15} /> {t}
                </button>
              ))}
            </div>
          </>
        )}

        <div className="term-footer">
          <span>这条解释有帮助吗？</span>
          <button className="btn text" onClick={regen}><IconRefresh size={14} /> 重新生成</button>
          <button className="btn text" onClick={() => navigate(`/notes?path=${encodeURIComponent(note.path)}`)}>
            <IconDoc size={14} /> 编辑文档
          </button>
        </div>
      </div>

      <aside className="rail">
        <div className="rail-card">
          <div className="rail-title"><IconArrowLeft size={16} style={{ transform: 'rotate(180deg)' } as any} /> 反向链接 · 被这些笔记引用</div>
          {backlinks.length ? backlinks.map((b) => (
            <button key={b.path} className="backlink-item"
              onClick={() => navigate(b.type === 'term' ? `/concept?path=${encodeURIComponent(b.path)}` : `/notes?path=${encodeURIComponent(b.path)}`)}>
              <div className="t">
                {b.type === 'term' ? <span className="concept-ic"><IconConcept size={14} /></span> : <IconDoc size={14} />}
                {b.title}
              </div>
              {b.snippet && <div className="s">...{b.snippet.slice(0, 46)}</div>}
            </button>
          )) : <div className="rail-empty">还没有笔记引用这个概念。</div>}
        </div>

        <div className="rail-card purple">
          <div className="rail-title"><IconGraph size={16} /> 在知识图谱中查看</div>
          <div style={{ fontSize: 13, color: '#4a4f66', lineHeight: 1.7 }}>
            该概念的双链关系已自动同步到图谱。
          </div>
          <div style={{ marginTop: 12 }}>
            <button className="btn small primary" onClick={() => navigate(`/graph?node=${encodeURIComponent(note.path.replace(/\.md$/, ''))}`)}>
              打开图谱 →
            </button>
          </div>
        </div>
      </aside>
    </div>
  )
}

function renderInline(text: string) {
  return <span>{text}</span>
}

function MdBlock({ content }: { content: string }) {
  return <div className="md-body" style={{ fontSize: 14.5 }} dangerouslySetInnerHTML={{ __html: renderMarkdown(content) }} />
}

/** 相关概念跳转：优先概念文档，否则笔记 */
export async function jumpConcept(target: string, topic: string, navigate: any) {
  try {
    const r = await api.resolveTerm(target, topic)
    if (r.found) { navigate(`/concept?path=${encodeURIComponent(r.path)}`); return }
  } catch { /* fallthrough */ }
  try {
    const n = await api.resolveLink(target, topic)
    navigate(n.type === 'term' ? `/concept?path=${encodeURIComponent(n.path)}` : `/notes?path=${encodeURIComponent(n.path)}`)
  } catch {
    navigate('/notes')
  }
}
