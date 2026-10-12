import { useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { api, getModelOverride, streamSSE, streamUrls } from '../api'
import { useApp } from '../store'
import {
  IconCaretDown, IconCheck, IconChevron, IconConcept, IconDoc, IconFolder,
  IconFolderOpen, IconGear, IconGraph, IconGrad, IconNote, IconPlus,
} from './Icons'
import Modal from './Modal'
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
  const [emojiOpen, setEmojiOpen] = useState(false)
  const [custom, setCustom] = useState('')
  const [archOpen, setArchOpen] = useState(false)
  const location = useLocation()
  const navigate = useNavigate()

  const isGraphPage = location.pathname.startsWith('/graph')
  const currentPath = new URLSearchParams(location.search).get('path') || ''
  const currentEmoji = topics.find((t) => t.name === activeTopic)?.emoji || ''

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
    if (!activeTopic) return
    try {
      await api.setTopicEmoji(activeTopic, emoji)
      await refreshTopics()
      setEmojiOpen(false); setCustom('')
      toast(emoji ? `「${activeTopic}」图标已设为 ${emoji}` : '图标已清除')
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
      <div className="nav-label">主题</div>
      <div className="topic-select">
        <button className={`topic-btn ${menuOpen ? 'open' : ''}`} onClick={() => setMenuOpen((v) => !v)}>
          <IconDoc size={17} />
          {currentEmoji && <span className="topic-emoji">{currentEmoji}</span>}
          <span>{activeTopic || '选择主题'}</span>
          <span className="caret"><IconCaretDown size={15} /></span>
        </button>
        {menuOpen && (
          <div className="topic-menu" onMouseLeave={() => setMenuOpen(false)}>
            {topics.map((t) => (
              <button key={t.path} className={t.name === activeTopic ? 'sel' : ''}
                onClick={() => { setActiveTopic(t.name); setMenuOpen(false) }}>
                {t.name === activeTopic ? <IconCheck size={15} /> : <span style={{ width: 15 }} />}
                {t.emoji && <span className="topic-emoji">{t.emoji}</span>}
                {t.name}
                <span style={{ marginLeft: 'auto', color: 'var(--muted)', fontSize: 12 }}>{t.note_count}</span>
              </button>
            ))}
            {!topics.length && <div className="empty">还没有主题，先新建一个</div>}
            <hr style={{ border: 0, borderTop: '1px solid var(--border)', margin: '6px 4px' }} />
            <button disabled={!activeTopic} onClick={() => { setEmojiOpen(true); setMenuOpen(false); setCustom('') }}>
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
        {activeTopic && <TreeFolder node={tree} topic={activeTopic} currentPath={currentPath} depth={0} />}
        {!activeTopic && <div className="side-hint">创建主题后，这里会显示对应主题的文件目录。</div>}
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

      {emojiOpen && (
        <Modal title={`「${activeTopic}」的图标`} onClose={() => setEmojiOpen(false)}
          ops={<button className="btn" onClick={() => setEmojiOpen(false)}>关闭</button>}>
          <div className="emoji-grid">
            {EMOJI_CHOICES.map((e) => (
              <button key={e} className={`emoji-cell ${currentEmoji === e ? 'sel' : ''}`}
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
          {currentEmoji && (
            <button className="btn text" style={{ marginTop: 12 }} onClick={() => pickEmoji('')}>清除当前图标</button>
          )}
        </Modal>
      )}
    </aside>
  )
}

function TreeFolder({ node, topic, currentPath, depth }: { node: TreeNode | null; topic: string; currentPath: string; depth: number }) {
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
        <TreeFolder key={child.path} node={child} topic={topic} currentPath={currentPath} depth={depth + 1} />
      ) : (
        <TreeLeaf key={child.path} node={child} currentPath={currentPath} />
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

function TreeLeaf({ node, currentPath }: { node: TreeNode; currentPath: string }) {
  const navigate = useNavigate()
  const { refreshTree, refreshTopics } = useApp()
  const isTerm = node.type === 'term'
  const active = currentPath === node.path

  const open = async () => {
    if (isTerm) navigate(`/concept?path=${encodeURIComponent(node.path)}`)
    else navigate(`/notes?path=${encodeURIComponent(node.path)}`)
  }

  return (
    <button className={`tree-row ${active ? 'active' : ''}`} onClick={open} title={node.path}>
      {isTerm
        ? <span className="icon-concept"><IconConcept size={15} /></span>
        : <span className="icon-note"><IconDoc size={15} /></span>}
      <span className="name">{node.name}{!isTerm && <span className="ext">.md</span>}</span>
      {isTerm && <span className="kind-tag">概念</span>}
    </button>
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
        {text || ' '}
      </div>
    </Modal>
  )
}
