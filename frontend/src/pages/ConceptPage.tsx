import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import { useApp } from '../store'
import type { NoteDetail } from '../types'
import ReaderView from '../components/ReaderView'
import TermStreamModal from '../components/TermStreamModal'
import { IconArrowLeft, IconConcept, IconDoc, IconGraph } from '../components/Icons'

/**
 * 概念页：概念文档就是存在 terms/ 下的普通 md 笔记，与笔记共用同一个
 * ReaderView（划选弹窗 / 高亮 / 批注 / 悬浮卡 / 编辑完全一致）。
 * 概念特有的部分作为注入点传入：返回出处、按出处重新生成、反链与图谱卡片。
 */
export default function ConceptPage() {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const path = params.get('path') || ''
  const { settings, refreshTree, toast } = useApp()
  const [note, setNote] = useState<NoteDetail | null>(null)
  const [missing, setMissing] = useState(false)
  const [regenOpen, setRegenOpen] = useState(false)

  const load = useCallback(async () => {
    if (!path) { setMissing(true); return }
    try {
      setNote(await api.note(path))
    } catch { setMissing(true) }
  }, [path])

  useEffect(() => { load() }, [load])

  const reload = useCallback(async () => { await load(); refreshTree() }, [load, refreshTree])

  if (missing) return <div className="empty-tip"><div className="big">概念文档不存在</div></div>
  if (!note) return <div className="empty-tip">加载中...</div>

  const fm = note.frontmatter || {}
  const originPath: string = fm.origin_path || ''
  const originName: string = typeof fm.origin === 'string' ? fm.origin.replace(/^\[\[|\]\]$/g, '') : ''
  const originSection: string = fm.origin_section || ''

  // 重新生成：流式生成解释（按出处），完成后留在当前页刷新
  const openRegen = () => {
    if (!originPath) { toast('该概念缺少出处笔记，无法自动重新生成', 'err'); return }
    setRegenOpen(true)
  }

  return (
    <>
      <ReaderView
        key={note.path}
        note={note}
        settings={settings}
        reload={reload}
        onOpenConcept={(p) => navigate(`/concept?path=${encodeURIComponent(p)}`)}
        toast={toast}
        header={
          (originPath || originName) ? (
            <button className="back-origin"
              onClick={() => navigate(originPath ? `/notes?path=${encodeURIComponent(originPath)}` : '/notes')}>
              <IconArrowLeft size={16} /> 返回出处：{originName}{originSection ? ` · ${originSection}` : ''}
            </button>
          ) : null
        }
        onRegen={openRegen}
        railTop={
        <>
          <div className="rail-card">
            <div className="rail-title">
              <IconArrowLeft size={16} style={{ transform: 'rotate(180deg)' } as any} /> 反向链接 · 被这些笔记引用
            </div>
            {note.backlinks.length ? note.backlinks.map((b) => (
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
        </>
        }
      />
      {regenOpen && (
        <TermStreamModal
          path={originPath}
          term={note.name}
          contextBefore=""
          contextAfter=""
          regenerate
          onClose={() => setRegenOpen(false)}
          onDone={() => { setRegenOpen(false); reload() }}
        />
      )}
    </>
  )
}
