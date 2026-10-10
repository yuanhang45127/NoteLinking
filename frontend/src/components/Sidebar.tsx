import { useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { api } from '../api'
import { useApp } from '../store'
import {
  IconCaretDown, IconCheck, IconChevron, IconConcept, IconDoc, IconFolder,
  IconFolderOpen, IconGear, IconGraph, IconGrad, IconNote, IconPlus,
} from './Icons'
import type { TreeNode } from '../types'

export default function Sidebar() {
  const { topics, activeTopic, setActiveTopic, tree, refreshTopics, refreshTree, toast } = useApp()
  const [menuOpen, setMenuOpen] = useState(false)
  const [creating, setCreating] = useState(false)
  const [newTopic, setNewTopic] = useState('')
  const location = useLocation()
  const navigate = useNavigate()

  const isGraphPage = location.pathname.startsWith('/graph')
  const currentPath = new URLSearchParams(location.search).get('path') || ''

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
          <IconDoc size={17} /> <span>{activeTopic || '选择主题'}</span>
          <span className="caret"><IconCaretDown size={15} /></span>
        </button>
        {menuOpen && (
          <div className="topic-menu" onMouseLeave={() => setMenuOpen(false)}>
            {topics.map((t) => (
              <button key={t.path} className={t.name === activeTopic ? 'sel' : ''}
                onClick={() => { setActiveTopic(t.name); setMenuOpen(false) }}>
                {t.name === activeTopic ? <IconCheck size={15} /> : <span style={{ width: 15 }} />}
                {t.name}
                <span style={{ marginLeft: 'auto', color: 'var(--muted)', fontSize: 12 }}>{t.note_count}</span>
              </button>
            ))}
            {!topics.length && <div className="empty">还没有主题，先新建一个</div>}
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
