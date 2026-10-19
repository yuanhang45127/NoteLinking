import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api } from '../api'
import { useApp } from '../store'
import type { McpServer, Provider, Settings } from '../types'
import Modal from '../components/Modal'
import CallLogViewer from '../components/CallLogViewer'
import { IconDownload, IconEdit, IconFilePdf, IconPlus, IconTrash } from '../components/Icons'

const TABS = [
  { key: 'general', label: '通用' },
  { key: 'topics', label: '主题管理' },
  { key: 'reader', label: '阅读与高亮' },
  { key: 'model', label: 'AI 模型' },
  { key: 'web', label: '联网搜索' },
  { key: 'mcp', label: 'MCP 服务器' },
  { key: 'graph', label: '双链与图谱' },
  { key: 'kimi', label: 'Kimi Code' },
  { key: 'call-logs', label: '调用记录' },
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
        {tab === 'web' && <WebSearchPanel />}
        {tab === 'mcp' && <McpPanel />}
        {tab === 'graph' && <GraphPanel />}
        {tab === 'kimi' && <KimiPanel />}
        {tab === 'call-logs' && <CallLogViewer />}
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

/* ---------------- 联网搜索 ---------------- */
function WebSearchPanel() {
  const { settings, refreshSettings, toast } = useApp()
  const [ws, setWs] = useState<Settings['web_search']>(
    { enabled: false, provider: 'tavily', api_key: '', base_url: '', max_results: 5, mcp_server: '', mcp_tool: '' })
  const [dirty, setDirty] = useState(false)
  const [testing, setTesting] = useState(false)
  const [testTitles, setTestTitles] = useState<string[]>([])
  useEffect(() => {
    if (!settings?.web_search) return
    const w = settings.web_search
    setWs({ ...w, api_key: w.has_key ? MASK : '' })
  }, [settings])

  const save = async () => {
    try { await api.saveWebSearch(ws); await refreshSettings(); setDirty(false); toast('已保存') }
    catch (e: any) { toast(e.message, 'err') }
  }

  const test = async () => {
    setTesting(true)
    setTestTitles([])
    try {
      const r = await api.webSearch('NoteLink 笔记')
      setTestTitles(r.results.slice(0, 3).map((x) => x.title))
      if (!r.results.length) toast('搜索成功，但没有结果')
    } catch (e: any) { toast(e.message, 'err') }
    setTesting(false)
  }

  return (
    <div className="settings-card">
      <h3>联网搜索</h3>
      <div className="desc">
        开启后，AI 生成笔记、重新生成与备考助教对话里会出现「联网搜索」选项：勾选后 AI 会先检索网络再作答，适合获取最新信息。
        API Key 留空表示不修改。
      </div>
      <div className="setting-line" style={{ borderBottom: '1px solid var(--border)' }}>
        <div>
          <div className="sl-text">启用联网搜索</div>
          <div className="sl-sub">未开启时各处的「联网搜索」选项不会出现</div>
        </div>
        <Toggle checked={ws.enabled} onChange={(v) => { setWs({ ...ws, enabled: v }); setDirty(true) }} />
      </div>
      <div className="setting-line" style={{ borderBottom: '1px solid var(--border)' }}>
        <div>
          <div className="sl-text">搜索服务商</div>
          <div className="sl-sub">Tavily / Brave / Serper / DeepSeek 需申请 API Key；SearXNG 用自建实例、无需 Key；MCP 用「MCP 服务器」里配置的外部搜索工具</div>
        </div>
        <select className="select-input" value={ws.provider}
          onChange={(e) => { setWs({ ...ws, provider: e.target.value }); setDirty(true) }}>
          <option value="tavily">Tavily</option>
          <option value="brave">Brave</option>
          <option value="serper">Serper</option>
          <option value="deepseek">DeepSeek 搜索</option>
          <option value="searxng">SearXNG</option>
          <option value="kimi">Kimi（Kimi Code 订阅）</option>
          <option value="mcp">MCP 服务器</option>
        </select>
      </div>
      {ws.provider === 'mcp' && (
        <>
          <div className="setting-line" style={{ borderBottom: '1px solid var(--border)' }}>
            <div>
              <div className="sl-text">MCP 服务器 id</div>
              <div className="sl-sub">「设置 → MCP 服务器」里已配置并启用的服务器 id（在其「检测」结果旁查看）</div>
            </div>
            <input className="text-input" style={{ width: 240 }} value={ws.mcp_server || ''} placeholder="如 a1b2c3d4"
              onChange={(e) => { setWs({ ...ws, mcp_server: e.target.value }); setDirty(true) }} />
          </div>
          <div className="setting-line" style={{ borderBottom: '1px solid var(--border)' }}>
            <div>
              <div className="sl-text">搜索工具名</div>
              <div className="sl-sub">该 MCP 服务器提供的搜索工具（用「MCP 服务器」页的「检测」查看工具列表）</div>
            </div>
            <input className="text-input" style={{ width: 240 }} value={ws.mcp_tool || ''} placeholder="如 web_search"
              onChange={(e) => { setWs({ ...ws, mcp_tool: e.target.value }); setDirty(true) }} />
          </div>
        </>
      )}
      {ws.provider === 'kimi' && (
        <div className="setting-line" style={{ borderBottom: '1px solid var(--border)' }}>
          <div>
            <div className="sl-text">Kimi Code 凭证</div>
            <div className="sl-sub">无需 API Key：直接复用服务器上 Kimi Code 的登录凭证（本服务自动续期，需 Kimi Code 保持登录）</div>
          </div>
        </div>
      )}
      {ws.provider !== 'mcp' && ws.provider !== 'kimi' && (
        <div className="setting-line" style={{ borderBottom: '1px solid var(--border)' }}>
          <div>
            <div className="sl-text">API Key {ws.has_key && <span style={{ color: 'var(--ok)' }}>（已配置）</span>}</div>
            <div className="sl-sub">SearXNG 无需 Key；留空表示不修改</div>
          </div>
          <input className="text-input" style={{ width: 240 }} type="password" value={ws.api_key}
            placeholder={ws.has_key ? '••••••（未修改）' : '未配置'}
            onChange={(e) => { setWs({ ...ws, api_key: e.target.value }); setDirty(true) }} />
        </div>
      )}
      {ws.provider === 'searxng' && (
        <div className="setting-line" style={{ borderBottom: '1px solid var(--border)' }}>
          <div>
            <div className="sl-text">SearXNG 实例地址</div>
            <div className="sl-sub">自建或公共实例的 Base URL，如 https://searx.be</div>
          </div>
          <input className="text-input" style={{ width: 240 }} value={ws.base_url} placeholder="https://..."
            onChange={(e) => { setWs({ ...ws, base_url: e.target.value }); setDirty(true) }} />
        </div>
      )}
      <div className="setting-line" style={{ borderBottom: '1px solid var(--border)' }}>
        <div>
          <div className="sl-text">每次搜索返回结果数</div>
          <div className="sl-sub">1-20 条，越多越占用 AI 上下文</div>
        </div>
        <input className="text-input" style={{ width: 90 }} type="number" min={1} max={20} value={ws.max_results}
          onChange={(e) => { setWs({ ...ws, max_results: Math.max(1, Math.min(20, Number(e.target.value) || 5)) }); setDirty(true) }} />
      </div>
      <div className="setting-line">
        <div>
          <div className="sl-text">测试搜索</div>
          <div className="sl-sub">用示例关键词跑一次搜索，验证配置是否可用（未保存的改动不会生效，需先保存）</div>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 6 }}>
          <button className="btn small" disabled={testing} onClick={test}>
            {testing ? '搜索中...' : '测试搜索'}
          </button>
          {!!testTitles.length && (
            <div className="sl-sub" style={{ textAlign: 'right' }}>
              {testTitles.map((t) => <div key={t}>· {t}</div>)}
            </div>
          )}
        </div>
      </div>
      <SaveBar dirty={dirty} onSave={save} />
    </div>
  )
}

/* ---------------- 外部 MCP 服务器 ---------------- */
function McpPanel() {
  const { settings, refreshSettings, toast } = useApp()
  const [servers, setServers] = useState<McpServer[]>([])
  const [dirty, setDirty] = useState(false)
  const [probe, setProbe] = useState<Record<number, { tools?: number; error?: string }>>({})
  const [busy, setBusy] = useState<number>(-1)
  const [form, setForm] = useState({ name: '', command: '', args: '', env: '' })

  useEffect(() => {
    if (settings) setServers(settings.mcp_servers || [])
  }, [settings])

  const save = async () => {
    try {
      await api.saveMcpServers(servers)
      await refreshSettings()
      setDirty(false)
      setProbe({})
      toast('已保存')
    } catch (e: any) { toast(e.message, 'err') }
  }

  const update = (i: number, patch: Partial<McpServer>) => {
    setServers((ss) => ss.map((s, j) => (j === i ? { ...s, ...patch } : s)))
    setDirty(true)
  }

  const add = () => {
    const command = form.command.trim()
    if (!command) { toast('请填写启动命令', 'err'); return }
    const env: Record<string, string> = {}
    for (const line of form.env.split('\n')) {
      const idx = line.indexOf('=')
      if (idx > 0) env[line.slice(0, idx).trim()] = line.slice(idx + 1).trim()
    }
    setServers((ss) => [...ss, {
      id: `mcp-${Date.now().toString(36)}`,
      name: form.name.trim() || command,
      command,
      args: form.args.split(',').map((a) => a.trim()).filter(Boolean),
      env,
      enabled: true,
    }])
    setForm({ name: '', command: '', args: '', env: '' })
    setDirty(true)
  }

  /** 检测连接：先保存（后端只认已保存的配置），再拉工具列表 */
  const test = async (i: number) => {
    setBusy(i)
    try {
      if (dirty) await save()
      const r = await api.mcpServers()
      const s = servers[i]
      const entry = r.servers.find((x) => x.command === s.command && x.name === s.name)
      if (!entry) setProbe((p) => ({ ...p, [i]: { error: '未在已保存的服务器里找到该项，请检查后重试' } }))
      else if (entry.error) setProbe((p) => ({ ...p, [i]: { error: entry.error } }))
      else setProbe((p) => ({ ...p, [i]: { tools: entry.tools.length } }))
    } catch (e: any) {
      setProbe((p) => ({ ...p, [i]: { error: e.message } }))
    }
    setBusy(-1)
  }

  return (
    <div className="settings-card">
      <h3>MCP 服务器</h3>
      <div className="desc">
        连接外部 stdio MCP server（如 web search MCP），供联网搜索与 AI 对话使用。
        命令在 NoteLink 后端所在机器上执行，请只添加可信的服务器。
      </div>

      {servers.map((s, i) => (
        <div className="setting-line" key={s.id || i} style={{ borderBottom: '1px solid var(--border)' }}>
          <div style={{ minWidth: 0 }}>
            <div className="sl-text">
              {s.name || s.command}
              <span className="tag" style={{ marginLeft: 8 }}>{s.enabled ? '已启用' : '已停用'}</span>
            </div>
            <div className="sl-sub" title={`${s.command} ${(s.args || []).join(' ')}`.trim()}
              style={{ maxWidth: 340, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {s.command}{(s.args || []).length ? ` ${s.args.join(' ')}` : ''}
            </div>
            {probe[i]?.error && <div className="sl-sub" style={{ color: 'var(--err)' }}>{probe[i].error}</div>}
            {probe[i]?.tools !== undefined && (
              <div className="sl-sub" style={{ color: 'var(--ok)' }}>连接成功：{probe[i].tools} 个工具</div>
            )}
          </div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', flex: 'none' }}>
            <Toggle checked={s.enabled} onChange={(v) => update(i, { enabled: v })} />
            <button className="btn small" disabled={busy === i} onClick={() => test(i)}>
              {busy === i ? '检测中…' : '检测'}
            </button>
            <button className="btn small" style={{ color: 'var(--err)' }}
              onClick={() => { setServers((ss) => ss.filter((_, j) => j !== i)); setDirty(true) }}>
              <IconTrash size={14} />
            </button>
          </div>
        </div>
      ))}
      {!servers.length && <div className="sl-sub">还没有配置 MCP 服务器。</div>}

      <div className="field-label">添加服务器</div>
      <div className="provider-grid">
        <div>
          <label>名称（可选，缺省用命令）</label>
          <input className="text-input" value={form.name} placeholder="如 web search"
            onChange={(e) => setForm({ ...form, name: e.target.value })} />
        </div>
        <div>
          <label>启动命令 *</label>
          <input className="text-input" value={form.command} placeholder="如 npx、uvx、python 或可执行文件路径"
            onChange={(e) => setForm({ ...form, command: e.target.value })} />
        </div>
        <div>
          <label>参数（逗号分隔）</label>
          <input className="text-input" value={form.args} placeholder="-y, some-search-mcp"
            onChange={(e) => setForm({ ...form, args: e.target.value })} />
        </div>
      </div>
      <div style={{ marginTop: 10, maxWidth: 520 }}>
        <label style={{ fontSize: 12, color: 'var(--muted)', display: 'block', marginBottom: 5 }}>
          环境变量（每行 KEY=VALUE；含 KEY/TOKEN 的值保存后打码）
        </label>
        <textarea className="text-input" style={{ width: '100%', minHeight: 72 }} value={form.env}
          placeholder={'API_KEY=sk-...\nHTTPS_PROXY=http://127.0.0.1:7890'}
          onChange={(e) => setForm({ ...form, env: e.target.value })} />
      </div>
      <button className="btn" style={{ marginTop: 10 }} onClick={add}><IconPlus size={15} /> 添加服务器</button>

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

/* ---------------- Kimi Code Web 嵌入 ---------------- */
function KimiPanel() {
  const { settings, refreshSettings, toast } = useApp()
  const [kw, setKw] = useState<Settings['kimi_web']>({ enabled: false, port: 58627 })
  const [dirty, setDirty] = useState(false)
  const [status, setStatus] = useState<string>('')
  useEffect(() => { if (settings) setKw(settings.kimi_web || { enabled: false, port: 58627 }) }, [settings])

  const save = async () => {
    try { await api.saveKimiWeb(kw); await refreshSettings(); setDirty(false); toast('已保存') }
    catch (e: any) { toast(e.message, 'err') }
  }

  const probe = async () => {
    setStatus('检测中…')
    try {
      const r = await api.kimiWebStatus()
      setStatus(r.running ? `已连接：${r.url}` : '未检测到 kimi web 服务')
    } catch (e: any) { setStatus(`检测失败：${e.message}`) }
  }

  return (
    <div className="settings-card">
      <h3>Kimi Code 集成</h3>
      <div className="desc">
        在右侧 AI 对话抽屉里嵌入本机 <code>kimi web</code> 服务：直接用 Kimi Code 的完整 Agent（检索、文件、MCP 工具）
        操作笔记库。启动：<code>kimi web --no-open --port 58627</code>（建议先 cd 到笔记库目录）。
      </div>
      <div className="setting-line" style={{ borderBottom: '1px solid var(--border)' }}>
        <div>
          <div className="sl-text">启用嵌入</div>
          <div className="sl-sub">开启后侧边对话出现「Kimi Code」标签；仅建议单人本地部署——任何能登录本服务的人都会获得本机 Kimi Code 的访问</div>
        </div>
        <Toggle checked={kw.enabled} onChange={(v) => { setKw({ ...kw, enabled: v }); setDirty(true) }} />
      </div>
      <div className="setting-line">
        <div>
          <div className="sl-text">kimi web 端口</div>
          <div className="sl-sub">默认 58627；端口被占用时 kimi web 自动 +1，NoteLink 会依次探测</div>
        </div>
        <input className="text-input" style={{ width: 110 }} type="number" value={kw.port}
          onChange={(e) => { setKw({ ...kw, port: Number(e.target.value) || 58627 }); setDirty(true) }} />
      </div>
      {status && <div className="rail-note" style={{ marginTop: 6 }}>{status}</div>}
      <SaveBar dirty={dirty} onSave={save} />
      <button className="btn small" style={{ marginLeft: 8 }} onClick={probe}>检测连接</button>
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
