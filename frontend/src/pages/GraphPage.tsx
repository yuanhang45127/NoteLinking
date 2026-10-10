import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import {
  forceCenter, forceCollide, forceLink, forceManyBody, forceSimulation,
  type Simulation, type SimulationNodeDatum,
} from 'd3-force'
import { api } from '../api'
import { useApp } from '../store'
import type { GraphData, GraphNode } from '../types'
import { IconConcept, IconDoc, IconLink, IconList } from '../components/Icons'

interface SimNode extends SimulationNodeDatum {
  id: string; label: string; name: string; type: 'note' | 'term' | 'missing'; topic: string; path: string; degree: number
  fx?: number | null; fy?: number | null
}
interface SimLink { source: string | SimNode; target: string | SimNode }

const COLORS: Record<string, { fill: string; stroke: string; text: string }> = {
  note: { fill: '#e3edff', stroke: '#5b8ff0', text: '#3c4150' },
  term: { fill: '#efeafe', stroke: '#7b5cf0', text: '#5b3fd6' },
  missing: { fill: '#f2f3f6', stroke: '#b8bcc8', text: '#8a8f9a' },
}

export default function GraphPage() {
  const { activeTopic, settings, toast } = useApp()
  const [params, setParams] = useSearchParams()
  const navigate = useNavigate()
  const [data, setData] = useState<GraphData | null>(null)
  const [filter, setFilter] = useState<'all' | 'note' | 'term'>(settings?.graph.default_filter || 'all')
  const [selected, setSelected] = useState<SimNode | null>(null)
  const [desc, setDesc] = useState('')
  const [refs, setRefs] = useState<{ title: string; path: string; type: string }[]>([])
  const [zoom, setZoom] = useState(1)
  const [pan, setPan] = useState({ x: 0, y: 0 })
  const svgRef = useRef<SVGSVGElement>(null)
  const wrapRef = useRef<HTMLDivElement>(null)
  const simRef = useRef<Simulation<SimNode, SimLink> | null>(null)
  const nodesRef = useRef<SimNode[]>([])
  const linksRef = useRef<SimLink[]>([])
  const [, forceRender] = useState(0)
  const dragRef = useRef<{ node: SimNode | null; panning: boolean; sx: number; sy: number; ox: number; oy: number }>({ node: null, panning: false, sx: 0, sy: 0, ox: 0, oy: 0 })
  const lastClick = useRef(0)

  useEffect(() => { if (settings?.graph.default_filter) setFilter(settings.graph.default_filter) }, [settings])

  const load = useCallback(async () => {
    try {
      setData(await api.graph(activeTopic || undefined))
    } catch (e: any) { toast(e.message, 'err') }
  }, [activeTopic, toast])
  useEffect(() => { load() }, [load])

  // 构建模拟
  useEffect(() => {
    if (!data) return
    const showMissing = settings?.graph.show_missing ?? true
    const visible = data.nodes.filter((n) => {
      if (filter === 'all') return showMissing || n.type !== 'missing'
      if (filter === 'note') return n.type === 'note'
      return n.type === 'term'
    })
    const idSet = new Set(visible.map((n) => n.id))
    const edges = data.edges.filter((e) => idSet.has(e.source) && idSet.has(e.target))

    const saved = loadPositions(activeTopic)
    const W = 900, H = 620
    const nodes: SimNode[] = visible.map((n, i) => {
      const p = saved[n.id]
      return {
        ...n,
        x: p?.x ?? W / 2 + Math.cos((i / Math.max(visible.length, 1)) * Math.PI * 2) * 230,
        y: p?.y ?? H / 2 + Math.sin((i / Math.max(visible.length, 1)) * Math.PI * 2) * 200,
        fx: p ? p.x : null, fy: p ? p.y : null,
      }
    })
    const links: SimLink[] = edges.map((e) => ({ source: e.source, target: e.target }))

    nodesRef.current = nodes
    linksRef.current = links
    simRef.current?.stop()
    const sim = forceSimulation<SimNode, SimLink>(nodes)
      .force('link', forceLink<SimNode, SimLink>(links).id((d) => d.id).distance(130).strength(0.5))
      .force('charge', forceManyBody().strength(-420))
      .force('center', forceCenter(W / 2, H / 2))
      .force('collide', forceCollide<SimNode>((d) => radius(d) + 16))
      .alpha(1)
      .on('tick', () => forceRender((v) => v + 1))
    simRef.current = sim
    // 固定位置（保存过布局的）在 alpha 衰减后释放，保持用户布局
    return () => { sim.stop() }
  }, [data, filter, settings])

  // 打开指定节点（从概念页「打开图谱」跳转）
  useEffect(() => {
    const target = params.get('node')
    if (!target || !data) return
    const n = nodesRef.current.find((x) => x.id === target || x.path === target || x.id === `missing:${target}`)
    if (n) selectNode(n)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, params])

  const radius = (n: SimNode) => Math.min(14 + n.degree * 3.2, 44)

  const nodeColor = (n: SimNode) => COLORS[n.type] || COLORS.missing

  const savePositions = () => {
    const map: Record<string, { x: number; y: number }> = {}
    nodesRef.current.forEach((n) => { map[n.id] = { x: n.x ?? 0, y: n.y ?? 0 } })
    localStorage.setItem(`nl-graph-${activeTopic}`, JSON.stringify(map))
  }

  function loadPositions(topic: string): Record<string, { x: number; y: number }> {
    try { return JSON.parse(localStorage.getItem(`nl-graph-${topic}`) || '{}') } catch { return {} }
  }

  const selectNode = async (n: SimNode) => {
    setSelected(n); setRefs([]); setDesc('')
    if (n.type === 'missing' || !n.path) return
    try {
      const note = await api.note(n.path)
      const body = note.content.replace(/^---[\s\S]*?---/, '').replace(/^#[^\n]*\n/, '')
      const plain = body.replace(/[#>*`$]|\[\[|\]\]/g, '').replace(/\s+/g, ' ').trim()
      setDesc(plain.slice(0, 90) + (plain.length > 90 ? '…' : ''))
      setRefs(note.backlinks.map((b) => ({ title: b.title, path: b.path, type: b.type })))
    } catch { /* ignore */ }
  }

  /* ---------- 交互 ---------- */
  const toSvg = (e: React.MouseEvent) => {
    const rect = svgRef.current!.getBoundingClientRect()
    return { x: (e.clientX - rect.left) / zoom - pan.x, y: (e.clientY - rect.top) / zoom - pan.y }
  }
  const onMouseDown = (e: React.MouseEvent) => {
    const t = e.target as HTMLElement
    const g = t.closest('g.g-node') as SVGGElement | null
    if (g) {
      const node = nodesRef.current.find((n) => n.id === g.dataset.id)
      if (node) {
        const now = Date.now()
        if (now - lastClick.current < 320 && node.path) {
          // 双击 → 打开文档
          navigate(node.type === 'term' ? `/concept?path=${encodeURIComponent(node.path)}` : `/notes?path=${encodeURIComponent(node.path)}`)
          return
        }
        lastClick.current = now
        dragRef.current = { node, panning: false, sx: e.clientX, sy: e.clientY, ox: 0, oy: 0 }
        selectNode(node)
        simRef.current?.alphaTarget(0.15).restart()
        return
      }
    }
    dragRef.current = { node: null, panning: true, sx: e.clientX, sy: e.clientY, ox: pan.x, oy: pan.y }
    svgRef.current?.classList.add('panning')
  }
  const onMouseMove = (e: React.MouseEvent) => {
    const d = dragRef.current
    if (d.node) {
      const p = toSvg(e)
      d.node.fx = p.x; d.node.fy = p.y
    } else if (d.panning) {
      setPan({ x: d.ox + (e.clientX - d.sx) / zoom, y: d.oy + (e.clientY - d.sy) / zoom })
    }
  }
  const onMouseUp = () => {
    const d = dragRef.current
    if (d.node) { d.node.fx = null; d.node.fy = null; simRef.current?.alphaTarget(0); savePositions() }
    dragRef.current = { node: null, panning: false, sx: 0, sy: 0, ox: 0, oy: 0 }
    svgRef.current?.classList.remove('panning')
  }
  const onWheel = (e: React.WheelEvent) => {
    e.preventDefault()
    setZoom((z) => Math.min(2.6, Math.max(0.35, z * (e.deltaY < 0 ? 1.12 : 0.89))))
  }

  const stats = useMemo(() => {
    if (!data) return { nodes: 0, edges: 0, terms: 0 }
    return {
      nodes: data.nodes.filter((n) => n.type !== 'missing').length,
      edges: data.edges.length,
      terms: data.nodes.filter((n) => n.type === 'term').length,
    }
  }, [data])

  return (
    <div className="graph-layout">
      <div className="graph-main">
        <div className="graph-toolbar">
          {([['all', '全部'], ['note', '笔记'], ['term', '概念']] as const).map(([k, label]) => (
            <button key={k} className={`filter-chip ${filter === k ? 'active' : ''}`} onClick={() => { setFilter(k); setSelected(null) }}>{label}</button>
          ))}
          <div className="zoom-box">
            力导向自动布局
            <div className="zoom-btns">
              <button onClick={() => setZoom((z) => Math.max(0.35, z - 0.2))}>−</button>
              <button onClick={() => setZoom((z) => Math.min(2.6, z + 0.2))}>＋</button>
            </div>
          </div>
        </div>
        <div className="graph-canvas" ref={wrapRef}>
          <svg ref={svgRef} onMouseDown={onMouseDown} onMouseMove={onMouseMove} onMouseUp={onMouseUp} onMouseLeave={onMouseUp} onWheel={onWheel}>
            <g transform={`scale(${zoom}) translate(${pan.x},${pan.y})`}>
              {linksRef.current.map((l, i) => {
                const s = l.source as SimNode, t = l.target as SimNode
                if (!s?.x || !t?.x) return null
                return <line key={i} className="g-edge" x1={s.x} y1={s.y} x2={t.x} y2={t.y} />
              })}
              {nodesRef.current.map((n) => {
                const c = nodeColor(n)
                const r = radius(n)
                return (
                  <g key={n.id} className="g-node" data-id={n.id} transform={`translate(${n.x ?? 0},${n.y ?? 0})`}
                    style={{ cursor: 'pointer' }}>
                    <circle r={r} fill={c.fill} stroke={c.stroke} strokeDasharray={n.type === 'missing' ? '4 3' : undefined} />
                    {n.degree >= 4 && (
                      <g transform={`translate(${r * 0.72},${-r * 0.72})`}>
                        <circle r={9} fill={c.stroke} />
                        <text textAnchor="middle" dy="3.2" style={{ fontSize: 10, fill: '#fff', fontWeight: 700 }}>{n.degree}</text>
                      </g>
                    )}
                    <text textAnchor="middle" y={r + 16} className={n.type === 'term' ? 'purple' : ''}>
                      {n.label.length > 8 ? n.label.slice(0, 8) + '…' : n.label}
                    </text>
                  </g>
                )
              })}
            </g>
          </svg>
          <div className="graph-legend">
            <span><span className="legend-dot" style={{ background: '#5b8ff0' }} />笔记</span>
            <span><span className="legend-dot" style={{ background: '#7b5cf0' }} />概念</span>
            <span style={{ color: 'var(--muted)' }}>圆越大，链接越多</span>
          </div>
        </div>
      </div>

      <aside className="graph-rail">
        {selected ? (
          <div className="detail-card">
            <span className="tag">{selected.type === 'term' ? '概念' : selected.type === 'missing' ? '待创建' : '笔记'}</span>
            <h2 style={{ fontSize: 21, margin: '10px 0 6px' }}>{selected.label}</h2>
            <div style={{ color: 'var(--muted)', fontSize: 13 }}>
              连接 {selected.degree} 个节点{refs.length ? ` · 被 ${refs.length} 篇笔记引用` : ''}
            </div>
            <div className="dc-desc">{desc || (selected.type === 'missing' ? '该概念被引用但还没有文档，去笔记里选中它点「什么意思」即可生成。' : '')}</div>
            <div className="dc-btns">
              {selected.path && (
                <button className="btn primary" onClick={() => navigate(selected.type === 'term'
                  ? `/concept?path=${encodeURIComponent(selected.path)}`
                  : `/notes?path=${encodeURIComponent(selected.path)}`)}>
                  打开文档
                </button>
              )}
              {!!refs.length && (
                <button className="btn" onClick={() => {
                  const first = refs[0]
                  navigate(first.type === 'term' ? `/concept?path=${encodeURIComponent(first.path)}` : `/notes?path=${encodeURIComponent(first.path)}`)
                }}>查看引用</button>
              )}
              {selected.type === 'missing' && (
                <button className="btn primary" onClick={() => {
                  navigate('/notes')
                  toast('在笔记中选中该词并点「什么意思」即可生成概念')
                }}>去生成</button>
              )}
            </div>
            <div className="dc-hint">双击节点可跳到对应笔记；拖动节点可调整布局，布局自动保存。</div>
            {!!refs.length && (
              <div style={{ marginTop: 14 }}>
                <div className="rail-title" style={{ fontSize: 13 }}><IconList size={14} /> 引用列表</div>
                {refs.slice(0, 6).map((r) => (
                  <button key={r.path} className="backlink-item" onClick={() =>
                    navigate(r.type === 'term' ? `/concept?path=${encodeURIComponent(r.path)}` : `/notes?path=${encodeURIComponent(r.path)}`)}>
                    <div className="t">
                      {r.type === 'term' ? <span className="concept-ic"><IconConcept size={13} /></span> : <IconDoc size={13} />}
                      {r.title}
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>
        ) : (
          <div className="detail-card" style={{ color: 'var(--muted)', fontSize: 13.5, lineHeight: 1.8 }}>
            点击节点查看详情；双击跳转文档；拖拽调整布局（自动保存）。
          </div>
        )}

        <div className="rail-card" style={{ marginTop: 16 }}>
          <div className="rail-title"><IconLink size={16} /> 图谱统计 {activeTopic && `· ${activeTopic}`}</div>
          <div className="stat-grid">
            <div className="stat-cell"><div className="v">{stats.nodes}</div><div className="k">节点</div></div>
            <div className="stat-cell"><div className="v purple">{stats.edges}</div><div className="k">双链</div></div>
            <div className="stat-cell"><div className="v green">{stats.terms}</div><div className="k">概念文档</div></div>
          </div>
        </div>
      </aside>
    </div>
  )
}
