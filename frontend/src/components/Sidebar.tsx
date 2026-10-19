import { useEffect, useMemo, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { api, getModelOverride, streamUrls } from '../api'
import { useApp } from '../store'
import { streamTracked } from '../lib/aiTasks'
import {
  IconBulb, IconCaretDown, IconCheck, IconChevron, IconConcept, IconDoc, IconFilePdf, IconFolder,
  IconFolderOpen, IconGear, IconGraph, IconGrad, IconNote, IconPlus,
} from './Icons'
import Modal from './Modal'
import ProcessTimeline from './ProcessTimeline'
import StreamMd from './StreamMd'
import type { PinnedNote, ProcessEvt, TreeNode } from '../types'

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
  // 置顶笔记（跨主题，显示在目录树上方；置顶的笔记不再出现在主题树里）
  const [pinned, setPinned] = useState<PinnedNote[]>([])
  // 收藏笔记（跨主题，显示在「置顶」区下方；收藏的笔记仍保留在主题树里）
  const [favList, setFavList] = useState<PinnedNote[]>([])
  // 单行 ⋮ 菜单
  const [rowMenu, setRowMenu] = useState<{ path: string; name: string; isTerm: boolean; pinned: boolean; fav: boolean; finished: boolean; x: number; y: number } | null>(null)
  // 按架构批量生成笔记
  const [genNotes, setGenNotes] = useState<{ topic: string; savePath: string } | null>(null)
  // 新建主题二级菜单「⬆ md」：选完 md 文件即创建主题并批量导入
  const importInputRef = useRef<HTMLInputElement>(null)
  const importTopicRef = useRef('')
  const [importing, setImporting] = useState(false)
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

  // 置顶 / 收藏列表跟随目录树刷新（生成/移动/删除笔记后都会 refreshTree）；
  // alive 守卫：tree 连续变化时丢弃过期响应，避免后到的旧数据覆盖新列表
  useEffect(() => {
    let alive = true
    api.pinned().then((r) => { if (alive) setPinned(r.pinned) }).catch(() => {})
    api.favorites().then((r) => { if (alive) setFavList(r.favorites) }).catch(() => {})
    return () => { alive = false }
  }, [tree])
  const pinnedPaths = useMemo(() => new Set(pinned.map((p) => p.path)), [pinned])
  const favPaths = useMemo(() => new Set(favList.map((f) => f.path)), [favList])
  // 已看完的笔记路径（树 + 置顶区都可能有）
  const finishedPaths = useMemo(() => {
    const s = new Set<string>()
    const walk = (n: TreeNode | null) => {
      if (!n?.children) return
      for (const c of n.children) {
        if (c.type === 'dir') walk(c)
        else if (c.finished) s.add(c.path)
      }
    }
    walk(tree)
    for (const p of pinned) if (p.finished) s.add(p.path)
    return s
  }, [tree, pinned])

  // 图标选择面板（锚定在主题按钮下方）：点面板外自动关闭
  const emojiPopRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!emojiFor) return
    const onDoc = (e: MouseEvent) => {
      if (!emojiPopRef.current?.contains(e.target as Node)) setEmojiFor(null)
    }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [emojiFor])

  // 新建主题输入态：点到别处或按 Esc 自动还原成「新建主题」按钮
  const createRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!creating) return
    const onDoc = (e: MouseEvent) => {
      if (!createRef.current?.contains(e.target as Node)) { setCreating(false); setNewTopic('') }
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { setCreating(false); setNewTopic('') }
    }
    document.addEventListener('mousedown', onDoc)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDoc)
      document.removeEventListener('keydown', onKey)
    }
  }, [creating])

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

  const openRowMenu = (path: string, name: string, isTerm: boolean, finished: boolean, e: React.MouseEvent) => {
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect()
    // 钳制在视口内：靠下的笔记菜单不溢出屏幕底部
    const x = Math.min(Math.max(8, rect.right - 150), window.innerWidth - 148)
    const y = Math.min(rect.bottom + 4, window.innerHeight - 150)
    setRowMenu({ path, name, isTerm, pinned: pinnedPaths.has(path), fav: favPaths.has(path), finished, x, y })
  }

  const togglePin = async (path: string) => {
    const next = !pinnedPaths.has(path)
    try {
      await api.setNotePin(path, next)
      setRowMenu(null)
      toast(next ? '已置顶，显示在目录顶部' : '已取消置顶')
      await refreshTree()
    } catch (e: any) { toast(e.message, 'err') }
  }

  const toggleFav = async (path: string) => {
    const next = !favPaths.has(path)
    try {
      await api.setNoteFav(path, next)
      setRowMenu(null)
      toast(next ? '已收藏' : '已取消收藏')
      await refreshTree()
    } catch (e: any) { toast(e.message, 'err') }
  }

  const toggleFinish = async (path: string) => {
    const cur = finishedPaths.has(path)
    try {
      await api.setNoteFinish(path, !cur)
      setRowMenu(null)
      toast(!cur ? '已标记看完 ✓' : '已取消「看完」标记')
      await refreshTree()
    } catch (e: any) { toast(e.message, 'err') }
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

  // 拖拽移动：把笔记拖到某个文件夹行上即移动进去
  const dropNoteInto = async (src: string, dstDir: string) => {
    const name = src.split('/').pop() || ''
    if (!name.toLowerCase().endsWith('.md')) return
    const dst = `${dstDir}/${name}`
    if (dst === src || src.split('/').slice(0, -1).join('/') === dstDir) return
    try {
      await api.moveNote(src, dst)
      toast(`已移动「${name.replace(/\.md$/i, '')}」到「${dstDir.split('/').pop()}」`)
      await refreshTree(); refreshTopics()
      if (currentPath === src) {
        navigate(`${dst.startsWith(`${activeTopic}/terms/`) ? '/concept' : '/notes'}?path=${encodeURIComponent(dst)}`)
      }
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

  // 创建主题后紧接着用 AI 生成整体架构（架构生成的唯一入口在新建主题流程）
  const createTopicWithArchitecture = async () => {
    const name = newTopic.trim()
    if (!name) return
    try {
      await api.createTopic(name)
      setCreating(false); setNewTopic('')
      await refreshTopics()
      setActiveTopic(name)
      setArchOpen(true)
      toast(`已创建主题「${name}」，正在生成整体架构…`)
    } catch (e: any) { toast(e.message, 'err') }
  }

  // 文件框必须与点击在同一用户手势内打开，否则 await 之后浏览器会拦截弹窗；
  // 所以先弹框选文件，选完再创建主题并上传——取消选择就什么都不发生
  const createTopicWithImport = () => {
    const name = newTopic.trim()
    if (!name) return
    importTopicRef.current = name
    importInputRef.current?.click()
  }

  const onImportFiles = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || [])
    e.target.value = ''
    const name = importTopicRef.current
    importTopicRef.current = ''
    if (!files.length || !name) return
    setImporting(true)
    try {
      try {
        await api.createTopic(name)
        await refreshTopics()
      } catch (err: any) {
        if (err.code !== 409) throw err  // 主题已存在时直接往里导
      }
      setActiveTopic(name)
      const res = await api.importMd(files, name)
      const bad = res.failed.length ? `，失败 ${res.failed.length} 个` : ''
      toast(`主题「${name}」已导入 ${res.imported.length} 篇笔记${bad}`, res.failed.length ? 'err' : 'ok')
      await refreshTree()
    } catch (err: any) { toast(err.message || '导入失败', 'err') }
    finally { setImporting(false) }
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
      <button className={`nav-item ${location.pathname.startsWith('/papers') ? 'active' : ''}`} onClick={() => navigate('/papers')}>
        <IconFilePdf /> 文献库
      </button>
      <button className={`nav-item ${location.pathname.startsWith('/exam') ? 'active' : ''}`} onClick={() => navigate('/exam')}>
        <IconGrad /> 考试备考
      </button>
      <button className={`nav-item ${location.pathname.startsWith('/settings') ? 'active' : ''}`} onClick={() => navigate('/settings')}>
        <IconGear /> 设置
      </button>
      <button className={`nav-item ${location.pathname.startsWith('/guide') ? 'active' : ''}`}
        title="新手引导：八步上手 NoteLink"
        onClick={() => navigate('/guide')}>
        <IconBulb /> 新手指引
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
        <button className={`topic-btn ${menuOpen ? 'open' : ''}`}
          onClick={() => { setEmojiFor(null); setMenuOpen((v) => !v) }}>
          {activeTopic ? (
            <span className={`topic-emoji emoji-editable ${currentEmoji ? '' : 'emoji-empty'}`} title="点击更换图标"
              onClick={(e) => { e.stopPropagation(); setMenuOpen(false); setCustom(''); setEmojiFor(activeTopic) }}>
              {currentEmoji || '🎨'}
            </span>
          ) : (
            <IconDoc size={17} />
          )}
          <span>{activeTopic || '选择主题'}</span>
          <span className="caret"><IconCaretDown size={15} /></span>
        </button>
        {menuOpen && (
          <div className="topic-menu" onMouseLeave={() => setMenuOpen(false)}>
            {[...topics].sort((a, b) => b.updated_at.localeCompare(a.updated_at)).map((t) => (
              <button key={t.path} className={t.name === activeTopic ? 'sel' : ''}
                onClick={() => { setActiveTopic(t.name); setMenuOpen(false) }}>
                {t.name === activeTopic ? <IconCheck size={15} /> : <span style={{ width: 15 }} />}
                {t.emoji && <span className="topic-emoji">{t.emoji}</span>}
                {t.name}
                <span style={{ marginLeft: 'auto', color: 'var(--muted)', fontSize: 12 }}>{t.note_count}</span>
              </button>
            ))}
            {!topics.length && <div className="empty">还没有主题，先新建一个</div>}
          </div>
        )}

        {/* 主题图标就地选择面板：点主题按钮上的图标直接弹出 */}
        {emojiFor && (
          <div className="emoji-pop" ref={emojiPopRef}>
            <div className="emoji-pop-title">「{emojiFor}」的图标</div>
            <div className="emoji-grid">
              {EMOJI_CHOICES.map((e) => (
                <button key={e} className={`emoji-cell ${emojiCurrent === e ? 'sel' : ''}`}
                  onClick={() => pickEmoji(e)}>{e}</button>
              ))}
            </div>
            <div style={{ display: 'flex', gap: 6, marginTop: 8 }}>
              <input className="text-input" style={{ flex: 1, minWidth: 0 }} placeholder="自定义 emoji"
                value={custom} maxLength={8} onChange={(e) => setCustom(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && custom.trim() && pickEmoji(custom.trim())} />
              <button className="btn primary small" disabled={!custom.trim()}
                onClick={() => pickEmoji(custom.trim())}>使用</button>
            </div>
            {emojiCurrent && (
              <button className="btn text" style={{ marginTop: 6 }} onClick={() => pickEmoji('')}>清除图标</button>
            )}
          </div>
        )}
      </div>

      <div className="tree">
        {!!pinned.length && (
          <div className="pin-section">
            <div className="pin-label">📌 置顶</div>
            {pinned.map((n) => (
              <div key={n.path} className={`tree-row-wrap ${currentPath === n.path ? 'active' : ''}`}>
                <button className={`tree-row ${n.finished ? 'finished' : ''}`} title={n.path}
                  onClick={() => navigate(`${n.type === 'term' ? '/concept' : '/notes'}?path=${encodeURIComponent(n.path)}`)}>
                  <span className={n.type === 'term' ? 'icon-concept' : 'icon-note'}>
                    {n.type === 'term' ? <IconConcept size={15} /> : <IconDoc size={15} />}
                  </span>
                  <span className="name">{n.title || n.name}</span>
                  {n.finished && <span className="finished-mark" title="已看完">✅</span>}
                  {n.topic !== activeTopic && <span className="pin-topic">{n.topic}</span>}
                </button>
                <button className="row-menu" title="更多操作"
                  onClick={(e) => { e.stopPropagation(); openRowMenu(n.path, n.name, n.type === 'term', !!n.finished, e) }}>
                  ⋮
                </button>
              </div>
            ))}
          </div>
        )}
        {!!favList.length && (
          <div className="pin-section">
            <div className="pin-label">⭐ 收藏</div>
            {favList.map((n) => (
              <div key={n.path} className={`tree-row-wrap ${currentPath === n.path ? 'active' : ''}`}>
                <button className={`tree-row ${n.finished ? 'finished' : ''}`} title={n.path}
                  onClick={() => navigate(`${n.type === 'term' ? '/concept' : '/notes'}?path=${encodeURIComponent(n.path)}`)}>
                  <span className={n.type === 'term' ? 'icon-concept' : 'icon-note'}>
                    {n.type === 'term' ? <IconConcept size={15} /> : <IconDoc size={15} />}
                  </span>
                  <span className="fav-mark" title="已收藏">⭐</span>
                  <span className="name">{n.title || n.name}</span>
                  {n.finished && <span className="finished-mark" title="已看完">✅</span>}
                  {n.topic !== activeTopic && <span className="pin-topic">{n.topic}</span>}
                </button>
                <button className="row-menu" title="更多操作"
                  onClick={(e) => { e.stopPropagation(); openRowMenu(n.path, n.name, n.type === 'term', !!n.finished, e) }}>
                  ⋮
                </button>
              </div>
            ))}
          </div>
        )}
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
            onDropNote={selectMode ? undefined : dropNoteInto}
            hidePaths={pinnedPaths}
            favPaths={favPaths}
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

      <input ref={importInputRef} type="file" multiple accept=".md,text/markdown,text/plain"
        style={{ display: 'none' }} onChange={onImportFiles} />

      <div className="side-footer" ref={createRef}>
        {!creating ? (
          <button className="quick-item" onClick={() => { setCreating(true); setNewTopic('') }}>
            <IconPlus size={16} /> 新建主题
          </button>
        ) : (
          <div style={{ display: 'flex', gap: 6 }}>
            <input className="text-input" style={{ flex: 1, minWidth: 0 }} autoFocus placeholder="主题名称"
              value={newTopic} onChange={(e) => setNewTopic(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && createTopic()} />
            <button className="btn primary small" onClick={createTopic}>创建</button>
            <button className="btn small" title="创建主题并用 AI 生成整体架构笔记"
              disabled={!newTopic.trim()} onClick={createTopicWithArchitecture}>✦ 架构</button>
            <button className="btn small" title="创建主题，并把选中的 .md 文件批量导入为主题笔记"
              disabled={!newTopic.trim() || importing} onClick={createTopicWithImport}>⬆ md</button>
          </div>
        )}
      </div>

      {archOpen && activeTopic && (
        <ArchitectureModal topic={activeTopic} onClose={() => setArchOpen(false)}
          onGenerateNotes={(sp) => { setArchOpen(false); setGenNotes({ topic: activeTopic, savePath: sp }) }} />
      )}

      {genNotes && (
        <GenerateNotesModal topic={genNotes.topic} savePath={genNotes.savePath} onClose={() => setGenNotes(null)} />
      )}

      {rowMenu && (
        <div className="row-menu-pop" style={{ left: rowMenu.x, top: rowMenu.y }}
          onMouseDown={(e) => e.stopPropagation()}
          onClick={(e) => e.stopPropagation()}>
          <button onClick={() => togglePin(rowMenu.path)}>
            {rowMenu.pinned ? '📍 取消置顶' : '📌 置顶'}
          </button>
          <button onClick={() => toggleFav(rowMenu.path)}>
            {rowMenu.fav ? '☆ 取消收藏' : '⭐ 收藏'}
          </button>
          <button onClick={() => toggleFinish(rowMenu.path)}>
            {rowMenu.finished ? '↩️ 取消看完' : '✅ 标记看完'}
          </button>
          <button onClick={() => renameNote(rowMenu.path, rowMenu.name)}>✏️ 重命名</button>
          <button className="danger" onClick={() => deleteNote(rowMenu.path, rowMenu.name)}>🗑 删除</button>
        </div>
      )}
    </aside>
  )
}

/** 目录子项排序：目录在前；笔记/概念按 updated_at 倒序（新的在前，缺省回退按名称），已看完的沉到底部。
 * 返回新数组，不修改传入的 children（props 不可变）。 */
function sortTree(children: TreeNode[]): TreeNode[] {
  return [...children].sort((a, b) => {
    const aDir = a.type === 'dir'
    const bDir = b.type === 'dir'
    if (aDir !== bDir) return aDir ? -1 : 1 // 目录在前
    const aFin = !!a.finished
    const bFin = !!b.finished
    if (aFin !== bFin) return aFin ? 1 : -1 // 已看完的笔记排最后
    const ta = a.updated_at || ''
    const tb = b.updated_at || ''
    if (ta !== tb) return ta < tb ? 1 : -1 // updated_at 倒序（新的在前）
    return a.name.localeCompare(b.name) // 无时间戳回退按名称
  })
}

function TreeFolder({ node, topic, currentPath, depth, selectMode, checked, onCheck, onMenu, onDropNote, hidePaths, favPaths }: {
  node: TreeNode | null
  topic: string
  currentPath: string
  depth: number
  selectMode: boolean
  checked: Set<string>
  onCheck: (path: string) => void
  onMenu: (path: string, name: string, isTerm: boolean, finished: boolean, e: React.MouseEvent) => void
  onDropNote?: (src: string, dstDir: string) => void
  hidePaths?: Set<string>
  favPaths?: Set<string>
}) {
  const [dropping, setDropping] = useState(false)
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
    sortTree(children.filter((child) => child.type === 'dir' || !hidePaths?.has(child.path))) // 置顶笔记只在顶部「置顶」区显示；其余按更新时间倒序、看完的沉底
      .map((child) =>
        child.type === 'dir' ? (
          <TreeFolder key={child.path} node={child} topic={topic} currentPath={currentPath} depth={depth + 1}
            selectMode={selectMode} checked={checked} onCheck={onCheck} onMenu={onMenu} onDropNote={onDropNote}
            hidePaths={hidePaths} favPaths={favPaths} />
        ) : child.type === 'file' ? (
          <TreeFile key={child.path} node={child} />
        ) : (
          <TreeLeaf key={child.path} node={child} currentPath={currentPath}
            selectMode={selectMode} checked={checked.has(child.path)} onCheck={onCheck} onMenu={onMenu}
            canDrag={!!onDropNote} favPaths={favPaths} />
        ),
      )

  if (depth === 0) {
    return <>{node?.children ? renderChildren(node.children) : null}</>
  }
  if (!node) return null

  const open = openMap[node.path] ?? true
  return (
    <div className="tree-folder">
      <button className={`tree-row ${dropping ? 'drop-hint' : ''}`} onClick={() => toggle(node.path)}
        onDragOver={(e) => {
          if (!onDropNote) return
          e.preventDefault()
          e.dataTransfer.dropEffect = 'move'
          setDropping(true)
        }}
        onDragLeave={() => setDropping(false)}
        onDrop={(e) => {
          e.preventDefault()
          setDropping(false)
          if (!onDropNote) return
          const src = e.dataTransfer.getData('text/nl-note') || e.dataTransfer.getData('text/plain')
          if (src) onDropNote(src, node.path)
        }}>
        <span className={`chev ${open ? 'open' : ''}`}><IconChevron size={13} /></span>
        {open ? <IconFolderOpen size={16} /> : <IconFolder size={16} />}
        <span className="name">{node.name}</span>
      </button>
      {open && node.children && <div className="tree-children">{renderChildren(node.children)}</div>}
    </div>
  )
}

function TreeFile({ node }: { node: TreeNode }) {
  // 库内图片/附件：点击经资产接口在新标签页打开（<img>/新标签带不了令牌头，走 ?token=）
  const open = () => {
    const site = localStorage.getItem('nl-token') || ''
    window.open(`/api/notes/asset?path=${encodeURIComponent(node.path)}&token=${encodeURIComponent(site)}`, '_blank')
  }
  return (
    <div className="tree-row-wrap">
      <button className="tree-row" onClick={open} title={`${node.path}（点击查看原图）`}>
        <span className="icon-note">🖼️</span>
        <span className="name">{node.name}</span>
      </button>
    </div>
  )
}

function TreeLeaf({ node, currentPath, selectMode, checked, onCheck, onMenu, canDrag, favPaths }: {
  node: TreeNode
  currentPath: string
  selectMode: boolean
  checked: boolean
  onCheck: (path: string) => void
  onMenu: (path: string, name: string, isTerm: boolean, finished: boolean, e: React.MouseEvent) => void
  canDrag?: boolean
  favPaths?: Set<string>
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
    <div className={`tree-row-wrap ${active ? 'active' : ''}`}
      draggable={!!canDrag}
      onDragStart={(e) => {
        if (!canDrag) return
        e.dataTransfer.setData('text/nl-note', node.path)
        e.dataTransfer.setData('text/plain', node.path)
        e.dataTransfer.effectAllowed = 'move'
      }}>
      <button className={`tree-row ${node.finished ? 'finished' : ''}`} onClick={open} title={node.path}>
        {isTerm
          ? <span className="icon-concept"><IconConcept size={15} /></span>
          : <span className="icon-note"><IconDoc size={15} /></span>}
        {favPaths?.has(node.path) && <span className="fav-mark" title="已收藏">⭐</span>}
        <span className="name">{node.name}{!isTerm && <span className="ext">.md</span>}</span>
        {node.finished && <span className="finished-mark" title="已看完">✅</span>}
        {isTerm && <span className="kind-tag">概念</span>}
      </button>
      <button className="row-menu" title="更多操作"
        onClick={(e) => { e.stopPropagation(); onMenu(node.path, node.name.replace(/\.md$/i, ''), isTerm, !!node.finished, e) }}>
        ⋮
      </button>
    </div>
  )
}

/* ---------------- 主题整体架构（流式生成） ---------------- */
function ArchitectureModal({ topic, onClose, onGenerateNotes }: {
  topic: string
  onClose: () => void
  onGenerateNotes?: (savePath: string) => void
}) {
  const [text, setText] = useState('')
  const [savedPath, setSavedPath] = useState('')
  const [err, setErr] = useState('')
  const [bg, setBg] = useState(false)
  const [proc, setProc] = useState<ProcessEvt[]>([])
  const ctrlRef = useRef<{ abort: () => void } | null>(null)
  const navigate = useNavigate()
  const { refreshTree, toast } = useApp()
  // 后台期间完成时暂存结果，回到前台再跳转（避免在用户看别的页面时突然切走）
  const pendingRef = useRef('')
  const bgRef = useRef(bg)
  bgRef.current = bg

  const foreground = () => {
    setBg(false)
    if (pendingRef.current) {
      const p = pendingRef.current
      pendingRef.current = ''
      navigate(`/notes?path=${encodeURIComponent(p)}`)
    }
  }

  // 按「建议知识架构」最小等级创建主题目录骨架（已存在目录跳过）
  const scaffoldDirs = async () => {
    try {
      const res = await api.scaffoldTopic(topic, savedPath)
      const n = (res.created || []).length
      const s = (res.skipped || []).length
      toast(n ? `已按架构生成 ${n} 个目录${s ? `，跳过已存在 ${s} 个` : ''}` : '没有需要新建的目录，均已存在')
      refreshTree()
    } catch (e: any) { toast(e.message, 'err') }
  }

  useEffect(() => {
    const t = streamTracked(
      { title: `生成整体架构 · ${topic}`, kind: 'note', foreground },
      streamUrls.topicArchitecture, {
        topic, stream: true, ...getModelOverride(),
      },
      {
        onDelta: (x) => setText((s) => s + x),
        onEvent: (evt) => {
          if (evt.type !== 'delta' && evt.type !== 'done' && evt.type !== 'error') {
            setProc((p) => [...p, evt])
          }
        },
        onDone: (evt) => {
          if (evt?.saved_path) {
            setSavedPath(evt.saved_path)
            refreshTree()
            if (bgRef.current) pendingRef.current = evt.saved_path
            else navigate(`/notes?path=${encodeURIComponent(evt.saved_path)}`)
          } else {
            setErr('生成完成但保存失败，请重试')
          }
        },
        onError: (msg) => setErr(msg),
        summarizeDone: (evt) => (evt?.saved_path ? `已保存：${evt.saved_path}` : undefined),
      })
    ctrlRef.current = t
    return () => t.abort()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [topic])

  if (bg) return null

  return (
    <Modal title={`生成整体架构 · ${topic}`} onClose={() => { ctrlRef.current?.abort(); onClose() }} wide
      ops={
        <>
          {!err && <span style={{ marginRight: 'auto', fontSize: 13, color: 'var(--muted)' }}>
            {savedPath ? '已保存 ✓ 正在打开…' : '流式生成中…'}
          </span>}
          {!savedPath && !err && <button className="btn" title="收起弹窗，生成继续在右下角悬浮窗里跑" onClick={() => setBg(true)}>后台</button>}
          <button className="btn" disabled={!savedPath} title="按「建议知识架构」的最小等级创建目录"
            onClick={scaffoldDirs}>按架构生成目录</button>
          <button className="btn" disabled={!savedPath} title="按提纲从最小等级逐篇用 AI 生成全部笔记"
            onClick={() => { const sp = savedPath; ctrlRef.current?.abort(); onClose(); onGenerateNotes?.(sp) }}>
            生成全部笔记</button>
          <button className="btn" onClick={() => { ctrlRef.current?.abort(); onClose() }}>
            {savedPath ? '关闭' : '取消'}
          </button>
        </>
      }>
      {err && <div style={{ color: 'var(--err)', fontSize: 13, marginBottom: 8 }}>{err}</div>}
      {savedPath && <div style={{ color: 'var(--ok)', fontSize: 13, marginBottom: 8 }}>已保存为笔记：{savedPath}</div>}
      <ProcessTimeline events={proc} running={!savedPath && !err} />
      <div className={`stream-box ${!text && !err ? 'loading-dot' : ''}`} style={{ maxHeight: 460, overflow: 'auto' }}>
        <StreamMd text={text} streaming={!savedPath && !err} />
      </div>
    </Modal>
  )
}

/* ---------------- 按架构批量生成笔记（进度） ---------------- */
type GenItem = { title: string; status: 'pending' | 'running' | 'done' | 'skip' | 'error'; msg?: string }

function GenerateNotesModal({ topic, savePath, onClose }: {
  topic: string
  savePath: string
  onClose: () => void
}) {
  const [items, setItems] = useState<GenItem[]>([])
  const [finished, setFinished] = useState(false)
  const [err, setErr] = useState('')
  const [bg, setBg] = useState(false)
  const ctrlRef = useRef<{ abort: () => void } | null>(null)
  const listRef = useRef<HTMLDivElement>(null)
  const { refreshTree, toast } = useApp()

  useEffect(() => {
    const t = streamTracked(
      { title: `批量生成笔记 · ${topic}`, kind: 'note', foreground: () => setBg(false) },
      streamUrls.topicGenerateNotes,
      { topic, save_path: savePath, ...getModelOverride() },
      {
        onDelta: () => { /* 批量模式不流式展示单篇正文，只看进度 */ },
        onDone: (evt) => {
          setFinished(true)
          refreshTree()
          toast(`笔记生成完成：成功 ${evt.created ?? 0} 篇${evt.failed ? `，失败 ${evt.failed} 篇` : ''}`)
        },
        onError: (msg) => { setErr(msg); toast(msg, 'err') },
        summarizeDone: (evt) => `成功 ${evt?.created ?? 0} 篇${evt?.failed ? `，失败 ${evt.failed} 篇` : ''}`,
        onEvent: (evt) => {
          if (evt.type === 'start') {
            setItems(Array.from({ length: evt.total }, () => ({ title: '', status: 'pending' as const })))
          } else if (evt.type === 'note_start') {
            setItems((s) => s.map((it, i) => (i === evt.index ? { title: evt.title, status: 'running' } : it)))
          } else if (evt.type === 'note_done') {
            setItems((s) => s.map((it, i) => (i === evt.index ? { ...it, status: 'done' } : it)))
          } else if (evt.type === 'note_skip') {
            setItems((s) => s.map((it, i) => (i === evt.index ? { ...it, status: 'skip', msg: evt.reason } : it)))
          } else if (evt.type === 'note_error') {
            setItems((s) => s.map((it, i) => (i === evt.index ? { ...it, status: 'error', msg: evt.message } : it)))
          }
        },
      })
    ctrlRef.current = t
    return () => t.abort()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight })
  }, [items])

  const doneCount = items.filter((i) => i.status === 'done' || i.status === 'skip' || i.status === 'error').length
  const icon: Record<GenItem['status'], string> = { pending: '·', running: '⏳', done: '✅', skip: '⏭', error: '❌' }

  if (bg) return null

  return (
    <Modal title={`按架构生成全部笔记 · ${topic}`} onClose={() => { ctrlRef.current?.abort(); onClose() }} wide
      ops={
        <>
          <span style={{ marginRight: 'auto', fontSize: 13, color: 'var(--muted)' }}>
            {err ? '已停止' : finished ? `全部完成（${items.length} 篇）` : `生成中 ${doneCount} / ${items.length || '…'}`}
          </span>
          {!finished && !err && <button className="btn" title="收起弹窗，生成继续在右下角悬浮窗里跑" onClick={() => setBg(true)}>后台</button>}
          <button className="btn" onClick={() => { ctrlRef.current?.abort(); onClose() }}>
            {finished ? '关闭' : '中止'}
          </button>
        </>
      }>
      <div className="stream-box" ref={listRef} style={{ maxHeight: 400 }}>
        {err && <div style={{ color: 'var(--err)', fontSize: 13 }}>{err}</div>}
        {items.map((it, i) => (
          <div key={i} style={{ display: 'flex', alignItems: 'baseline', gap: 8, padding: '3px 2px' }}>
            <span style={{ flex: 'none' }}>{icon[it.status]}</span>
            <span style={{ flex: 1, minWidth: 0 }}>
              {it.title || `第 ${i + 1} 篇`}
              {it.msg && <span style={{ color: 'var(--muted)', marginLeft: 8, fontSize: 12.5 }}>{it.msg}</span>}
            </span>
          </div>
        ))}
        {!err && !items.length && <div className="loading-dot">正在解析提纲…</div>}
      </div>
      <div className="rail-note" style={{ marginTop: 8 }}>
        笔记按提纲从最小等级逐篇生成，已存在的自动跳过；关闭窗口会中止后续生成，已完成的不受影响。
      </div>
    </Modal>
  )
}
