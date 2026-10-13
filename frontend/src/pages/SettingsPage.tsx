import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api } from '../api'
import { useApp } from '../store'
import type { Provider, Settings } from '../types'
import Modal from '../components/Modal'
import { IconDownload, IconEdit, IconFilePdf, IconPlus, IconTrash } from '../components/Icons'

const TABS = [
  { key: 'general', label: '通用' },
  { key: 'topics', label: '主题管理' },
  { key: 'reader', label: '阅读与高亮' },
  { key: 'model', label: 'AI 模型' },
  { key: 'graph', label: '双链与图谱' },
  { key: 'io', label: '导入与导出' },
]

const PRESET_COLORS = ['#fef08a', '#86efac', '#7dd3fc', '#f9a8d4', '#c4b5fd']
const MASK = '••••••'

export default function SettingsPage() {
  const [params, setParams] = useSearchParams()
  const tab = params.get('tab') || 'reader'
  return (
    <div className="settings-layout">
      <nav className="settings-nav">
        {TABS.map((t) => (
          <button key={t.key} className={`nav-item ${tab === t.key ? 'active' : ''}`}
            onClick={() => setParams({ tab: t.key })}>{t.label}</button>
        ))}
      </nav>
      <div className="settings-panel">
        {tab === 'reader' && <ReaderPanel />}
        {tab === 'model' && <ModelPanel />}
        {tab === 'graph' && <GraphPanel />}
        {tab === 'io' && <IoPanel />}
        {tab === 'general' && <GeneralPanel />}
        {tab === 'topics' && <TopicsPanel />}
      </div>
    </div>
  )
}

/* ---------------- 阅读与高亮 ---------------- */
function ReaderPanel() {
  const { settings, refreshSettings, toast } = useApp()
  const [hl, setHl] = useState<Settings['highlight']>({ color: '#fef08a', style: 'background' })
  const [reader, setReader] = useState<Settings['reader']>({ selection_menu: true, auto_concept: true, context_scope: 'section' })
  const [annInline, setAnnInline] = useState(() => localStorage.getItem('nl-ann-inline') !== '0')
  const [dirty, setDirty] = useState(false)

  useEffect(() => {
    if (!settings) return
    setHl(settings.highlight)
    setReader(settings.reader)
  }, [settings])

  const update = (patch: Partial<Settings['highlight']> | Partial<Settings['reader']>, kind: 'hl' | 'rd') => {
    if (kind === 'hl') setHl((s) => ({ ...s, ...patch }))
    else setReader((s) => ({ ...s, ...patch }))
    setDirty(true)
  }

  const save = async () => {
    try {
      await api.saveHighlight(hl)
      await api.saveReader(reader)
      await refreshSettings()
      setDirty(false)
      toast('设置已保存')
    } catch (e: any) { toast(e.message, 'err') }
  }

  const sampleStyle: React.CSSProperties = hl.style === 'font'
    ? { color: hl.color, fontWeight: 700 }
    : { background: `color-mix(in srgb, ${hl.color} 62%, white)`, borderRadius: 3, padding: '1px 2px' }

  return (
    <>
      <div className="settings-card">
        <h3>高亮样式</h3>
        <div className="desc">阅读时写下的想法与批注，会按此样式在笔记中自动高亮</div>
        <div className="field-label">高亮颜色</div>
        <div className="color-row">
          {PRESET_COLORS.map((c) => (
            <button key={c} className={`color-dot ${hl.color === c ? 'sel' : ''}`} style={{ background: c }}
              onClick={() => update({ color: c }, 'hl')} />
          ))}
        </div>
        <div className="field-label">高亮方式</div>
        <div className="style-cards">
          <button className={`style-card ${hl.style === 'background' ? 'sel' : ''}`} onClick={() => update({ style: 'background' }, 'hl')}>
            <span className="radio" /> 背景高亮
            <span className="sample" style={{ background: `color-mix(in srgb, ${hl.color} 62%, white)`, borderRadius: 3, padding: '1px 4px' }}>示例文字</span>
          </button>
          <button className={`style-card ${hl.style === 'font' ? 'sel' : ''}`} onClick={() => update({ style: 'font' }, 'hl')}>
            <span className="radio" /> 字体高亮
            <span className="sample" style={{ color: hl.color, fontWeight: 700 }}>示例文字</span>
          </button>
        </div>
      </div>

      <div className="settings-card">
        <h3>实时预览</h3>
        <div className="preview-box" style={{ marginTop: 10 }}>
          训练前先确定损失函数。
          <span style={sampleStyle}>我的理解：前向传播负责"算答案"，反向传播负责"改错"，两者交替直到收敛。</span>
          两者交替直到收敛。
        </div>
      </div>

      <div className="settings-card">
        <h3>批注显示</h3>
        <div className="setting-line">
          <div>
            <div className="sl-text">在笔记正文中显示高亮批注的内容</div>
            <div className="sl-sub">开启后，写有想法的高亮会在原文后面内联显示批注卡片；重新打开笔记后生效</div>
          </div>
          <Toggle checked={annInline} onChange={(v) => {
            setAnnInline(v)
            localStorage.setItem('nl-ann-inline', v ? '1' : '0')
          }} />
        </div>
      </div>

      <div className="settings-card">
        <h3>选段提问与概念文档</h3>
        <div className="setting-line" style={{ borderBottom: '1px solid var(--border)' }}>
          <div>
            <div className="sl-text">选中文字时弹出菜单（什么意思 / 高亮）</div>
          </div>
          <Toggle checked={reader.selection_menu} onChange={(v) => update({ selection_menu: v }, 'rd')} />
        </div>
        <div className="setting-line">
          <div>
            <div className="sl-text">「什么意思」的结果自动生成概念文档，并加入双链与图谱</div>
          </div>
          <Toggle checked={reader.auto_concept} onChange={(v) => update({ auto_concept: v }, 'rd')} />
        </div>
        <div className="setting-line" style={{ borderTop: '1px solid var(--border)' }}>
          <div className="sl-text">默认携带上下文范围</div>
          <select className="select-input" value={reader.context_scope}
            onChange={(e) => update({ context_scope: e.target.value }, 'rd')}>
            <option value="sentence">当前句子</option>
            <option value="section">当前小节</option>
            <option value="note">整篇笔记</option>
          </select>
        </div>
      </div>

      <SaveBar dirty={dirty} onSave={save} />
    </>
  )
}

/* ---------------- AI 模型 ---------------- */
function ModelPanel() {
  const { settings, refreshSettings, toast } = useApp()
  const [providers, setProviders] = useState<Provider[]>([])
  const [active, setActive] = useState('')
  const [dirty, setDirty] = useState(false)
  const [testing, setTesting] = useState('')
  const [fetching, setFetching] = useState('')
  const [manual, setManual] = useState<Record<number, string>>({})

  useEffect(() => {
    if (!settings) return
    setProviders(settings.providers.map((p) => ({ ...p, api_key: p.has_key ? MASK : '' })))
    setActive(settings.active_provider)
  }, [settings])

  const update = (i: number, patch: Partial<Provider>) => {
    setProviders((ps) => ps.map((p, j) => (j === i ? { ...p, ...patch } : p)))
    setDirty(true)
  }

  const save = async () => {
    try {
      await api.saveProviders(providers)
      if (active) await api.setActive(active)
      await refreshSettings()
      setDirty(false)
      toast('模型配置已保存')
    } catch (e: any) { toast(e.message, 'err') }
  }

  /** 从服务商接口实时拉取可用模型列表（未保存的配置会先自动保存） */
  const fetchModels = async (i: number) => {
    const p = providers[i]
    setFetching(p.id)
    try {
      await api.saveProviders(providers)
      const { models } = await api.llmModels(p.id)
      const next = providers.map((q, j) => (j === i ? { ...q, models } : q))
      setProviders(next)
      await api.saveProviders(next)
      await refreshSettings()
      setDirty(false)
      toast(`已拉取 ${models.length} 个模型`)
    } catch (e: any) { toast(e.message, 'err') }
    setFetching('')
  }

  const test = async (p: Provider) => {
    setTesting(p.id)
    try {
      await save()
      const headers: Record<string, string> = { 'Content-Type': 'application/json' }
      const token = localStorage.getItem('nl-token')
      if (token) headers['X-Notebook-Token'] = token
      const resp = await fetch('/api/llm/chat', {
        method: 'POST', headers,
        body: JSON.stringify({ messages: [{ role: 'user', content: '回复"OK"' }], provider: p.id }),
      })
      if (resp.ok) toast(`「${p.name || p.id}」连接成功`)
      else {
        const data = await resp.json().catch(() => ({}))
        toast(`连接失败：${data.detail || resp.status}`, 'err')
      }
    } catch (e: any) { toast(e.message, 'err') }
    setTesting('')
  }

  return (
    <div className="settings-card">
      <h3>AI 模型</h3>
      <div className="desc">
        支持所有主流接口：OpenAI 兼容（DeepSeek / Qwen / GLM / Kimi / OpenRouter / Ollama…）、Anthropic、Gemini。
        API Key 留空表示保持不变。
      </div>

      {providers.map((p, i) => (
        <div key={i} className="provider-card">
          <div className="provider-grid">
            <div>
              <label>名称</label>
              <input className="text-input" value={p.name} placeholder="如 DeepSeek"
                onChange={(e) => update(i, { name: e.target.value })} />
            </div>
            <div>
              <label>接口类型</label>
              <select className="select-input" style={{ width: '100%' }} value={p.type}
                onChange={(e) => update(i, { type: e.target.value as Provider['type'] })}>
                <option value="openai">OpenAI 兼容</option>
                <option value="anthropic">Anthropic</option>
                <option value="gemini">Gemini</option>
              </select>
            </div>
            <div>
              <label>Base URL（OpenAI 兼容时必填）</label>
              <input className="text-input" value={p.base_url} placeholder="https://api.deepseek.com/v1"
                onChange={(e) => update(i, { base_url: e.target.value })} />
            </div>
            <div>
              <label>API Key {p.has_key && <span style={{ color: 'var(--ok)' }}>（已配置）</span>}</label>
              <input className="text-input" type="password" value={p.api_key} placeholder={p.has_key ? '••••••（未修改）' : 'sk-...'}
                onChange={(e) => update(i, { api_key: e.target.value })} />
            </div>
            <div>
              <label>默认模型</label>
              <input className="text-input" value={p.model} placeholder="deepseek-chat"
                list={`models-dl-${p.id}`}
                onChange={(e) => update(i, { model: e.target.value })} />
              <datalist id={`models-dl-${p.id}`}>
                {(p.models || []).map((m) => <option key={m} value={m} />)}
              </datalist>
            </div>
            <div>
              <label>操作</label>
              <div style={{ display: 'flex', gap: 8 }}>
                <button className="btn small" disabled={testing === p.id} onClick={() => test(p)}>
                  {testing === p.id ? '测试中...' : '测试连接'}
                </button>
                <button className="btn small" style={{ color: 'var(--err)' }}
                  onClick={() => { setProviders((ps) => ps.filter((_, j) => j !== i)); setDirty(true) }}>
                  <IconTrash size={14} />
                </button>
              </div>
            </div>
          </div>

          {/* 可用模型列表：拉取后顶部选择器即可切换所有模型 */}
          <div style={{ marginTop: 10 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <label style={{ fontSize: 13, color: 'var(--muted)' }}>
                可用模型{p.models?.length ? `（${p.models.length}）` : ''}
              </label>
              <button className="btn small" disabled={fetching === p.id} onClick={() => fetchModels(i)}>
                {fetching === p.id ? '拉取中...' : p.models?.length ? '重新拉取' : '拉取模型列表'}
              </button>
            </div>
            {!!p.models?.length && (
              <div className="model-chips">
                {p.models.map((m) => (
                  <span key={m} className={`chip ${p.model === m ? 'cur' : ''}`}>
                    {m}
                    <button title="移除" onClick={() => update(i, { models: p.models!.filter((x) => x !== m) })}>×</button>
                  </span>
                ))}
              </div>
            )}
            <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
              <input className="text-input" style={{ maxWidth: 260 }} placeholder="手动添加模型名，如 gpt-5.4"
                value={manual[i] || ''}
                onChange={(e) => setManual((s) => ({ ...s, [i]: e.target.value }))}
                onKeyDown={(e) => {
                  const v = (manual[i] || '').trim()
                  if (e.key === 'Enter' && v && !p.models?.includes(v)) {
                    update(i, { models: [...(p.models || []), v] }); setManual((s) => ({ ...s, [i]: '' }))
                  }
                }} />
              <button className="btn small" disabled={!(manual[i] || '').trim()} onClick={() => {
                const v = (manual[i] || '').trim()
                if (v && !p.models?.includes(v)) { update(i, { models: [...(p.models || []), v] }); setManual((s) => ({ ...s, [i]: '' })) }
              }}>添加</button>
            </div>
            <div style={{ fontSize: 12, color: 'var(--muted)', marginTop: 6 }}>
              拉取的列表会出现在顶栏「模型选择器」里，随时为所有 AI 功能切换模型。
            </div>
          </div>
          <label className="check-row" style={{ marginTop: 8 }}>
            <input type="radio" name="active-provider" checked={active === p.id}
              onChange={() => { setActive(p.id); setDirty(true) }} />
            设为默认模型
          </label>
        </div>
      ))}

      <button className="btn" onClick={() => {
        setProviders((ps) => [...ps, { id: `provider-${Date.now()}`, type: 'openai', name: '', base_url: '', api_key: '', model: '' }])
        setDirty(true)
      }}><IconPlus size={15} /> 添加服务商</button>

      <SaveBar dirty={dirty} onSave={save} />
    </div>
  )
}

/* ---------------- 双链与图谱 ---------------- */
function GraphPanel() {
  const { settings, refreshSettings, toast } = useApp()
  const [g, setG] = useState<Settings['graph']>({ default_filter: 'all', show_missing: true })
  const [dirty, setDirty] = useState(false)
  useEffect(() => { if (settings) setG(settings.graph) }, [settings])

  const save = async () => {
    try { await api.saveGraph(g); await refreshSettings(); setDirty(false); toast('已保存') }
    catch (e: any) { toast(e.message, 'err') }
  }

  return (
    <div className="settings-card">
      <h3>双链与图谱</h3>
      <div className="desc">知识图谱由全库 [[双链]] 与概念文档自动生成，无需手动维护。</div>
      <div className="setting-line" style={{ borderBottom: '1px solid var(--border)' }}>
        <div className="sl-text">默认筛选</div>
        <select className="select-input" value={g.default_filter} onChange={(e) => { setG({ ...g, default_filter: e.target.value as any }); setDirty(true) }}>
          <option value="all">全部</option>
          <option value="note">笔记</option>
          <option value="term">概念</option>
        </select>
      </div>
      <div className="setting-line">
        <div>
          <div className="sl-text">显示悬空链接节点</div>
          <div className="sl-sub">写了 [[链接]] 但还没创建文档的概念，以虚线节点出现在图谱中</div>
        </div>
        <Toggle checked={g.show_missing} onChange={(v) => { setG({ ...g, show_missing: v }); setDirty(true) }} />
      </div>
      <SaveBar dirty={dirty} onSave={save} />
    </div>
  )
}

/* ---------------- 导入与导出 ---------------- */
function IoPanel() {
  const { activeTopic, refreshTree, toast } = useApp()
  return (
    <div className="settings-card">
      <h3>导入与导出</h3>
      <div className="desc">笔记的底层就是 Markdown 文件，随时可迁移、可备份。</div>
      <div className="setting-line" style={{ borderBottom: '1px solid var(--border)' }}>
        <div>
          <div className="sl-text">导入 PDF（自动转文本笔记）</div>
          <div className="sl-sub">导入到主题「{activeTopic || '（先选择主题）'}」，扫描件暂不支持</div>
        </div>
        <label className="btn" style={{ cursor: 'pointer' }}>
          <IconFilePdf size={15} /> 选择 PDF
          <input type="file" accept="application/pdf" style={{ display: 'none' }}
            onChange={async (e) => {
              const f = e.target.files?.[0]
              e.target.value = ''
              if (!f) return
              if (!activeTopic) { toast('请先在左侧选择主题', 'err'); return }
              try {
                const created = await api.importPdf(f, activeTopic, f.name.replace(/\.pdf$/i, ''))
                toast(`已导入：${created.name}（${created.pages} 页）`)
                refreshTree()
              } catch (e: any) { toast(e.message, 'err') }
            }} />
        </label>
      </div>
      <div className="setting-line">
        <div>
          <div className="sl-text">导出全部笔记（zip）</div>
          <div className="sl-sub">按主题打包全部 Markdown 文件</div>
        </div>
        <a className="btn" href={api.exportVaultUrl} download>
          <IconDownload size={15} /> 导出
        </a>
      </div>
    </div>
  )
}

/* ---------------- 通用 ---------------- */
function GeneralPanel() {
  const { topics } = useApp()
  return (
    <div className="settings-card">
      <h3>通用</h3>
      <div className="setting-line" style={{ borderBottom: '1px solid var(--border)' }}>
        <div className="sl-text">界面语言</div>
        <select className="select-input" defaultValue="zh">
          <option value="zh">简体中文</option>
        </select>
      </div>
      <div className="setting-line" style={{ borderBottom: '1px solid var(--border)' }}>
        <div className="sl-text">笔记存储</div>
        <div className="sl-sub">本地 Markdown 文件库（data/vault），共 {topics.length} 个主题</div>
      </div>
      <div className="setting-line">
        <div>
          <div className="sl-text">快捷键</div>
          <div className="sl-sub">n 笔记 · g 图谱 · e 考试 · s 设置</div>
        </div>
      </div>
    </div>
  )
}

/* ---------------- 主题管理 ---------------- */
function TopicsPanel() {
  const { topics, activeTopic, setActiveTopic, refreshTopics, refreshTree, toast } = useApp()
  const [busy, setBusy] = useState('')

  const remove = async (name: string, count: number) => {
    const tip = count > 0
      ? `主题「${name}」下有 ${count} 篇内容，其中的全部笔记与概念文档都将一并删除，不可恢复！确定删除？`
      : `确定删除主题「${name}」？`
    if (!window.confirm(tip)) return
    setBusy(name)
    try {
      await api.deleteTopic(name, true)
      toast(`已删除主题「${name}」`)
      if (activeTopic === name) {
        setActiveTopic(topics.find((t) => t.name !== name)?.name || '')
      }
      await refreshTopics()
      refreshTree()
    } catch (e: any) { toast(e.message, 'err') }
    finally { setBusy('') }
  }

  const rename = async (name: string) => {
    const input = window.prompt('重命名主题为：', name)
    if (!input) return
    const clean = input.trim().replace(/[\\/:*?"<>|]/g, ' ').trim()
    if (!clean || clean === name) return
    setBusy(name)
    try {
      await api.renameTopic(name, clean)
      toast(`已改名「${name}」→「${clean}」`)
      if (activeTopic === name) setActiveTopic(clean)
      await refreshTopics()
      refreshTree()
    } catch (e: any) { toast(e.message, 'err') }
    finally { setBusy('') }
  }

  return (
    <div className="settings-card">
      <h3>主题管理</h3>
      <div className="sl-sub" style={{ marginBottom: 14 }}>
        删除主题会一并删除其中的全部笔记与概念文档，操作不可恢复。
      </div>
      {topics.map((t) => (
        <div className="setting-line" key={t.path} style={{ borderBottom: '1px solid var(--border)' }}>
          <div>
            <div className="sl-text">
              {t.emoji ? `${t.emoji} ` : ''}{t.name}
              {t.name === activeTopic && <span className="tag" style={{ marginLeft: 8 }}>当前</span>}
            </div>
            <div className="sl-sub">{t.note_count} 篇内容</div>
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button className="btn small" disabled={busy === t.name}
              onClick={() => rename(t.name)}>
              <IconEdit size={14} /> 改名
            </button>
            <button className="btn small danger" disabled={busy === t.name}
              onClick={() => remove(t.name, t.note_count)}>
              <IconTrash size={14} /> 删除
            </button>
          </div>
        </div>
      ))}
      {!topics.length && <div className="sl-sub">还没有主题。</div>}
    </div>
  )
}

/* ---------------- 小组件 ---------------- */
function Toggle({ checked, onChange }: { checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="toggle">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      <span className="track" />
    </label>
  )
}

function SaveBar({ dirty, onSave }: { dirty: boolean; onSave: () => void }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
      <button className="btn primary" disabled={!dirty} onClick={onSave}>保存设置</button>
    </div>
  )
}
