import { useEffect, useMemo, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { api, getModelOverride, streamSSE, streamUrls } from '../api'
import { useApp } from '../store'
import {
  IconCaretDown, IconCheck, IconChevron, IconConcept, IconDoc, IconFolder,
  IconFolderOpen, IconGear, IconGraph, IconGrad, IconNote, IconPlus,
} from './Icons'
import Modal from './Modal'
import StreamMd from './StreamMd'
import type { TreeNode } from '../types'

const EMOJI_CHOICES = [
  '📚', '📖', '📝', '✏️', '🧮', '🔢', '🧠', '💡',
  '🧪', '🔬', '🔭', '🌍', '🌌', '⚛️', '🧬', '🩺',
  '⚖️', '🏛️', '💼', '📈', '📊', '🗺️', '🎨', '🎵',
  '💻', '🤖', '⚙️', '🛠️', '🚀', '🎯', '🏆', '🧩',
  '🌱', '🌿', '🌾', '🌊', '🏔️', '⭐', '🌙', '🔥',
  '❄️', '🐧', '🦋', '♟️', '🎮', '🎬', '🔶', '✨',
]

export default function Sidebar() {
  const { topics, activeTopic, setActiveTopic, tree, refreshTopics, refreshTree, toast } = useApp()
  const [menuOpen, setMenuOpen] = useState(false)
  const [creating, setCreating] = useState(false)
  const [newTopic, setNewTopic] = useState('')
  // 图标编辑面板面向的主题（null = 关闭）；点主题旁的图标直接唤起
  const [emojiFor, setEmojiFor] = useState<string | null>(null)
  const [custom, setCustom] = useState('')
  const [archOpen, setArchOpen] = useState(false)
  // 多选批量操作
  const [selectMode, setSelectMode] = useState(false)
  const [checked, setChecked] = useState<Set<string>>(new Set())
  const [moving, setMoving] = useState(false)
  // 单行 ⋮ 菜单
  const [rowMenu, setRowMenu] = useState<{ path: string; name: string; isTerm: boolean; x: number; y: number } | null>(null)
  const location = useLocation()
  const navigate = useNavigate()

  const isGraphPage = location.pathname.startsWith('/graph')
  const currentPath = new URLSearchParams(location.search).get('path') || ''
  const currentEmoji = topics.find((t) => t.name === activeTopic)?.emoji || ''
  const emojiCurrent = topics.find((t) => t.name === emojiFor)?.emoji || ''

  // 收集树里全部笔记/概念路径（全选用）
  const allPaths = useMemo(() => {
    const out: string[] = []
    const walk = (n: TreeNode | null) => {
      if (!n?.children) return
      for (const c of n.children) {
        if (c.type === 'note' || c.type === 'term') out.push(c.path)
        else if (c.type === 'dir') walk(c)
      }
    }
    walk(tree)
    return out
  }, [tree])

  useEffect(() => {
    if (!rowMenu) return
    const close = () => setRowMenu(null)
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [rowMenu])

  const toggleCheck = (path: string) => {
    setChecked((s) => {
      const next = new Set(s)
      next.has(path) ? next.delete(path) : next.add(path)
      return next
    })
  }

  const exitSelect = () => { setSelectMode(false); setChecked(new Set()); setMoving(false) }

  const afterDelete = (deleted: string[]) => {
    if (currentPath && deleted.includes(currentPath)) navigate('/notes')
  }

  const openRowMenu = (path: string, name: string, isTerm: boolean, e: React.MouseEvent) => {
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect()
    setRowMenu({ path, name, isTerm, x: Math.max(8, rect.right - 150), y: rect.bottom + 4 })
  }

  const renameNote = async (path: string, name: string) => {
    const input = window.prompt('重命名为：', name.replace(/\.md$/i, ''))
    if (!input) return
    const clean = input.trim().replace(/[\\/:*?"<>|]/g, ' ').trim()
    if (!clean) return
    const dst = path.split('/').slice(0, -1).concat(`${clean}.md`).join('/')
    try {
      await api.moveNote(path, dst)
      setRowMenu(null)
      toast('已重命名')
      await refreshTree(); refreshTopics()
      if (currentPath === path) {
        navigate(`${path.startsWith(`${activeTopic}/terms/`) ? '/concept' : '/notes'}?path=${encodeURIComponent(dst)}`)
      }
    } catch (e: any) { toast(e.message, 'err') }
  }

  const deleteNote = async (path: string, name: string) => {
    if (!window.confirm(`确定删除「${name}」？此操作不可恢复。`)) return
    try {
      await api.deleteNote(path)
      setRowMenu(null)
      toast('已删除')
      await refreshTree(); refreshTopics()
      afterDelete([path])
    } catch (e: any) { toast(e.message, 'err') }
  }

  const batchDelete = async () => {
    if (!checked.size) return
    if (!window.confirm(`批量删除选中的 ${checked.size} 项？此操作不可恢复。`)) return
    try {
      const res = await api.batchNotes('delete', [...checked])
      toast(`已删除 ${res.ok.length} 项${res.failed.length ? `，失败 ${res.failed.length} 项` : ''}`, res.failed.length ? 'err' : 'ok')
      afterDelete(res.ok)
      exitSelect()
      await refreshTree(); refreshTopics()
    } catch (e: any) { toast(e.message, 'err') }
  }

  const batchMove = async (target: string) => {
    try {
      const res = await api.batchNotes('move', [...checked], target)
      toast(`已移动 ${res.ok.length} 项到「${target}」${res.failed.length ? `，失败 ${res.failed.length} 项` : ''}`, res.failed.length ? 'err' : 'ok')
      afterDelete(res.ok)
      exitSelect()
      await refreshTree(); refreshTopics()
    } catch (e: any) { toast(e.message, 'err') }
  }

  const createTopic = async () => {
    const name = newTopic.trim()
    if (!name) return
    try {
      await api.createTopic(name)
      setCreating(false); setNewTopic('')
      await refreshTopics()
      setActiveTopic(name)
      toast(`已创建主题「${name}」`)
    } catch (e: any) { toast(e.message, 'err') }
  }

  const pickEmoji = async (emoji: string) => {
    if (!emojiFor) return
    try {
      await api.setTopicEmoji(emojiFor, emoji)
      await refreshTopics()
      setEmojiFor(null); setCustom('')
      toast(emoji ? `「${emojiFor}」图标已设为 ${emoji}` : '图标已清除')
    } catch (e: any) { toast(e.message, 'err') }
  }

  return (
    <aside className="sidebar">
      <div className="logo">
        <svg width="30" height="30" viewBox="0 0 32 32" fill="none">
          <path d="M5 27V5l11 9L27 5v22h-5.4V14.8L16 19.6l-5.6-4.8V27z" fill="#5457e5" />
          <circle cx="16" cy="19.6" r="2.1" fill="#8f92f2" />
        </svg>
        <div className="logo-name">墨链<em>NoteLink</em></div>
      </div>

      <div className="nav-label">功能</div>
      <button className={`nav-item ${location.pathname.startsWith('/notes') || location.pathname === '/' || location.pathname.startsWith('/concept') ? 'active' : ''}`}
        onClick={() => navigate('/notes')}>
        <IconNote /> 笔记
      </button>
      <button className={`nav-item ${location.pathname.startsWith('/graph') ? 'active' : ''}`} onClick={() => navigate('/graph')}>
        <IconGraph /> 知识图谱
      </button>
      <button className={`nav-item ${location.pathname.startsWith('/exam') ? 'active' : ''}`} onClick={() => navigate('/exam')}>
        <IconGrad /> 考试备考
      </button>
      <button className={`nav-item ${location.pathname.startsWith('/settings') ? 'active' : ''}`} onClick={() => navigate('/settings')}>
        <IconGear /> 设置
      </button>

      <hr className="side-divider" />
      <div className="nav-label" style={{ display: 'flex', alignItems: 'center' }}>
        主题
        {activeTopic && (
          <button className={`mini-toggle ${selectMode ? 'on' : ''}`}
            title="多选笔记，进行批量删除或移动"
            onClick={() => { setRowMenu(null); selectMode ? exitSelect() : setSelectMode(true) }}>
            {selectMode ? '退出多选' : '多选'}
          </button>
        )}
      </div>
      <div className="topic-select">
        <button className={`topic-btn ${menuOpen ? 'open' : ''}`} onClick={() => setMenuOpen((v) => !v)}>
          {currentEmoji
            ? <span className="topic-emoji emoji-editable" title="点击更换图标"
                onClick={(e) => { e.stopPropagation(); setMenuOpen(false); setCustom(''); setEmojiFor(activeTopic) }}>
                {currentEmoji}
              </span>
            : <IconDoc size={17} />}
          <span>{activeTopic || '选择主题'}</span>
          <span className="caret"><IconCaretDown size={15} /></span>
        </button>
        {menuOpen && (
          <div className="topic-menu" onMouseLeave={() => setMenuOpen(false)}>
            {topics.map((t) => (
              <button key={t.path} className={t.name === activeTopic ? 'sel' : ''}
                onClick={() => { setActiveTopic(t.name); setMenuOpen(false) }}>
                {t.name === activeTopic ? <IconCheck size={15} /> : <span style={{ width: 15 }} />}
                <span className={`topic-emoji emoji-editable ${t.emoji ? '' : 'emoji-empty'}`}
                  title={t.emoji ? '点击更换此主题图标' : '点击设置图标'}
                  onClick={(e) => { e.stopPropagation(); setMenuOpen(false); setCustom(''); setEmojiFor(t.name) }}>
                  {t.emoji || '🎨'}
                </span>
                {t.name}
                <span style={{ marginLeft: 'auto', color: 'var(--muted)', fontSize: 12 }}>{t.note_count}</span>
              </button>
            ))}
            {!topics.length && <div className="empty">还没有主题，先新建一个</div>}
            <hr style={{ border: 0, borderTop: '1px solid var(--border)', margin: '6px 4px' }} />
            <button disabled={!activeTopic} onClick={() => { setEmojiFor(activeTopic); setMenuOpen(false); setCustom('') }}>
              <span style={{ width: 15 }} />
              {currentEmoji ? '更换图标' : '选择图标'} 🎨
            </button>
            <button disabled={!activeTopic} onClick={() => { setMenuOpen(false); setArchOpen(true) }}>
              <span style={{ width: 15 }} />
              生成整体架构 ✦
            </button>
          </div>
        )}
      </div>

      <div className="tree">
        {activeTopic && (
          <TreeFolder
            node={tree}
            topic={activeTopic}
            currentPath={currentPath}
            depth={0}
            selectMode={selectMode}
            checked={checked}
            onCheck={toggleCheck}
            onMenu={openRowMenu}
          />
        )}
        {!activeTopic && <div className="side-hint">创建主题后，这里会显示对应主题的文件目录。</div>}

        {selectMode && (
          <div className="batch-bar">
            <div className="bb-head">
              <label className="check-row" style={{ cursor: 'pointer', gap: 6 }}>
                <input type="checkbox" checked={false}
                  onChange={() => setChecked(new Set(allPaths))} />
                全选
              </label>
              <span className="count">已选 {checked.size} / {allPaths.length}</span>
            </div>
            {moving ? (
              <div className="bb-actions">
                <span style={{ fontSize: 12.5, color: 'var(--muted)' }}>移动到：</span>
                {topics.filter((t) => t.name !== activeTopic).map((t) => (
                  <button key={t.path} className="btn small" onClick={() => batchMove(t.name)}>
                    {t.emoji}{t.name}
                  </button>
                ))}
                {!topics.filter((t) => t.name !== activeTopic).length && (
                  <span style={{ fontSize: 12.5, color: 'var(--muted)' }}>没有其他主题</span>
                )}
                <button className="btn small text" style={{ marginLeft: 'auto' }} onClick={() => setMoving(false)}>收起</button>
              </div>
            ) : (
              <div className="bb-actions">
                <button className="btn small" disabled={!checked.size} onClick={() => setMoving(true)}>移动</button>
                <button className="btn small danger" disabled={!checked.size} onClick={batchDelete}>删除</button>
                <button className="btn small text" style={{ marginLeft: 'auto' }} onClick={exitSelect}>取消</button>
              </div>
            )}
          </div>
        )}
      </div>

      {isGraphPage && (
        <div className="side-hint">图谱由双链自动生成，随笔记与概念文档实时更新。</div>
      )}

      <div className="side-footer">
        {!creating ? (
          <button className="quick-item" onClick={() => { setCreating(true); setNewTopic('') }}>
            <IconPlus size={16} /> 新建主题
          </button>
        ) : (
          <div style={{ display: 'flex', gap: 6 }}>
            <input className="text-input" style={{ flex: 1, minWidth: 0 }} autoFocus placeholder="主题名称"
              value={newTopic} onChange={(e) => setNewTopic(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && createTopic()} />
            <button className="btn primary small" onClick={createTopic}>确定</button>
          </div>
        )}
      </div>

      {archOpen && activeTopic && (
        <ArchitectureModal topic={activeTopic} onClose={() => setArchOpen(false)} />
      )}

      {rowMenu && (
        <div className="row-menu-pop" style={{ left: rowMenu.x, top: rowMenu.y }}
          onClick={(e) => e.stopPropagation()}>
          <button onClick={() => renameNote(rowMenu.path, rowMenu.name)}>✏️ 重命名</button>
          <button className="danger" onClick={() => deleteNote(rowMenu.path, rowMenu.name)}>🗑 删除</button>
        </div>
      )}

      {emojiFor && (
        <Modal title={`「${emojiFor}」的图标`} onClose={() => setEmojiFor(null)}
          ops={<button className="btn" onClick={() => setEmojiFor(null)}>关闭</button>}>
          <div className="emoji-grid">
            {EMOJI_CHOICES.map((e) => (
              <button key={e} className={`emoji-cell ${emojiCurrent === e ? 'sel' : ''}`}
                onClick={() => pickEmoji(e)}>{e}</button>
            ))}
          </div>
          <div className="field-label">自定义（粘贴任意 emoji）</div>
          <div style={{ display: 'flex', gap: 8 }}>
            <input className="text-input" style={{ flex: 1 }} placeholder="如 🧫"
              value={custom} maxLength={8} onChange={(e) => setCustom(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && custom.trim() && pickEmoji(custom.trim())} />
            <button className="btn primary" disabled={!custom.trim()} onClick={() => pickEmoji(custom.trim())}>使用</button>
          </div>
          {emojiCurrent && (
            <button className="btn text" style={{ marginTop: 12 }} onClick={() => pickEmoji('')}>清除当前图标</button>
          )}
        </Modal>
      )}
    </aside>
  )
}

function TreeFolder({ node, topic, currentPath, depth, selectMode, checked, onCheck, onMenu }: {
  node: TreeNode | null
  topic: string
  currentPath: string
  depth: number
  selectMode: boolean
  checked: Set<string>
  onCheck: (path: string) => void
  onMenu: (path: string, name: string, isTerm: boolean, e: React.MouseEvent) => void
}) {
  const [openMap, setOpenMap] = useState<Record<string, boolean>>(() => {
    try { return JSON.parse(localStorage.getItem('nl-tree-open') || '{}') } catch { return {} }
  })
  const toggle = (path: string) => {
    setOpenMap((m) => {
      const next = { ...m, [path]: !m[path] }
      localStorage.setItem('nl-tree-open', JSON.stringify(next))
      return next
    })
  }
  const renderChildren = (children: TreeNode[]) =>
    children.map((child) =>
      child.type === 'dir' ? (
        <TreeFolder key={child.path} node={child} topic={topic} currentPath={currentPath} depth={depth + 1}
          selectMode={selectMode} checked={checked} onCheck={onCheck} onMenu={onMenu} />
      ) : (
        <TreeLeaf key={child.path} node={child} currentPath={currentPath}
          selectMode={selectMode} checked={checked.has(child.path)} onCheck={onCheck} onMenu={onMenu} />
      ),
    )

  if (depth === 0) {
    return <>{node?.children ? renderChildren(node.children) : null}</>
  }
  if (!node) return null

  const open = openMap[node.path] ?? true
  return (
    <div className="tree-folder">
      <button className="tree-row" onClick={() => toggle(node.path)}>
        <span className={`chev ${open ? 'open' : ''}`}><IconChevron size={13} /></span>
        {open ? <IconFolderOpen size={16} /> : <IconFolder size={16} />}
        <span className="name">{node.name}</span>
      </button>
      {open && node.children && <div className="tree-children">{renderChildren(node.children)}</div>}
    </div>
  )
}

function TreeLeaf({ node, currentPath, selectMode, checked, onCheck, onMenu }: {
  node: TreeNode
  currentPath: string
  selectMode: boolean
  checked: boolean
  onCheck: (path: string) => void
  onMenu: (path: string, name: string, isTerm: boolean, e: React.MouseEvent) => void
}) {
  const navigate = useNavigate()
  const isTerm = node.type === 'term'
  const active = currentPath === node.path

  if (selectMode) {
    return (
      <div className={`tree-row selectable ${checked ? 'checked' : ''}`}>
        <input type="checkbox" checked={checked} onChange={() => onCheck(node.path)} />
        {isTerm
          ? <span className="icon-concept"><IconConcept size={15} /></span>
          : <span className="icon-note"><IconDoc size={15} /></span>}
        <span className="name" onClick={() => onCheck(node.path)} style={{ cursor: 'pointer' }}>
          {node.name}{!isTerm && <span className="ext">.md</span>}
        </span>
        {isTerm && <span className="kind-tag">概念</span>}
      </div>
    )
  }

  const open = () => {
    if (isTerm) navigate(`/concept?path=${encodeURIComponent(node.path)}`)
    else navigate(`/notes?path=${encodeURIComponent(node.path)}`)
  }

  return (
    <div className={`tree-row-wrap ${active ? 'active' : ''}`}>
      <button className="tree-row" onClick={open} title={node.path}>
        {isTerm
          ? <span className="icon-concept"><IconConcept size={15} /></span>
          : <span className="icon-note"><IconDoc size={15} /></span>}
        <span className="name">{node.name}{!isTerm && <span className="ext">.md</span>}</span>
        {isTerm && <span className="kind-tag">概念</span>}
      </button>
      <button className="row-menu" title="更多操作"
        onClick={(e) => { e.stopPropagation(); onMenu(node.path, node.name.replace(/\.md$/i, ''), isTerm, e) }}>
        ⋮
      </button>
    </div>
  )
}

/* ---------------- 主题整体架构（流式生成） ---------------- */
function ArchitectureModal({ topic, onClose }: { topic: string; onClose: () => void }) {
  const [text, setText] = useState('')
  const [savedPath, setSavedPath] = useState('')
  const [err, setErr] = useState('')
  const ctrlRef = useRef<{ abort: () => void } | null>(null)
  const navigate = useNavigate()
  const { refreshTree } = useApp()

  useEffect(() => {
    ctrlRef.current = streamSSE(streamUrls.topicArchitecture, {
      topic, stream: true, ...getModelOverride(),
    },
      (t) => setText((s) => s + t),
      (evt) => {
        if (evt?.saved_path) {
          setSavedPath(evt.saved_path)
          refreshTree()
          navigate(`/notes?path=${encodeURIComponent(evt.saved_path)}`)
        } else {
          setErr('生成完成但保存失败，请重试')
        }
      },
      (msg) => setErr(msg))
    return () => ctrlRef.current?.abort()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [topic])

  return (
    <Modal title={`生成整体架构 · ${topic}`} onClose={() => { ctrlRef.current?.abort(); onClose() }} wide
      ops={
        <>
          {!err && <span style={{ marginRight: 'auto', fontSize: 13, color: 'var(--muted)' }}>
            {savedPath ? '已保存 ✓ 正在打开…' : '流式生成中…'}
          </span>}
          <button className="btn" onClick={() => { ctrlRef.current?.abort(); onClose() }}>
            {savedPath ? '关闭' : '取消'}
          </button>
        </>
      }>
      {err && <div style={{ color: 'var(--err)', fontSize: 13, marginBottom: 8 }}>{err}</div>}
      {savedPath && <div style={{ color: 'var(--ok)', fontSize: 13, marginBottom: 8 }}>已保存为笔记：{savedPath}</div>}
      <div className={`stream-box ${!text && !err ? 'loading-dot' : ''}`} style={{ maxHeight: 460, overflow: 'auto' }}>
        <StreamMd text={text} streaming={!savedPath && !err} />
      </div>
    </Modal>
  )
}
