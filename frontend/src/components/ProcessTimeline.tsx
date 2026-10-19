// 「调用过程」时间线：把每次大模型调用、工具调用、辅助步骤实时摊开展示
// （对齐 DeepSeek Harness 的过程视图）。数据来自后端 SSE 过程事件
// （llm_start / llm_done / tool / step，协议见 backend app/services/process.py）。
import { useMemo } from 'react'
import type { ProcessEvt } from '../types'

export const TOOL_LABEL: Record<string, string> = {
  list_topics: '列出主题', search_notes: '搜索笔记', list_sections: '读章节目录',
  read_note: '读取笔记', create_note: '新建笔记', append_to_note: '追加内容',
  move_note: '移动笔记', web_search: '联网搜索', fetch_webpage: '抓取网页',
  mcp_tool: 'MCP 工具', add_note_link: '添加参考链接',
}

interface Item {
  key: string
  kind: 'llm' | 'tool' | 'step' | 'note'
  icon: string
  title: string
  meta?: string
  running: boolean
  ok?: boolean
  detail?: { label: string; text: string }[]
}

function modelLabel(ev: ProcessEvt): string {
  const m = ev.model || ''
  const p = ev.provider || ''
  return [p, m].filter(Boolean).join(' · ') || '模型'
}

export default function ProcessTimeline({ events, running }: {
  events: ProcessEvt[]
  running?: boolean
}) {
  const items = useMemo<Item[]>(() => {
    const list: Item[] = []
    const findOpen = (kind: Item['kind'], match: (it: Item) => boolean) =>
      [...list].reverse().find((it) => it.kind === kind && it.running && match(it))
    for (const ev of events) {
      if (ev.type === 'llm_start') {
        list.push({
          key: `llm-${ev.seq}-${list.length}`, kind: 'llm', icon: '✨', running: true,
          title: `${ev.purpose || '调用模型'} · ${modelLabel(ev)}`,
          detail: [{ label: '输入', text: `约 ${ev.prompt_chars ?? '?'} 字符` }],
        })
      } else if (ev.type === 'llm_done') {
        const it = findOpen('llm', (x) => ev.seq === undefined || x.key.includes(`-${ev.seq}-`))
        if (it) {
          it.running = false
          it.meta = `${ev.elapsed ?? '?'}s · 输出 ${ev.chars ?? '?'} 字`
        }
      } else if (ev.type === 'tool') {
        if (ev.status === 'start') {
          list.push({
            key: `tool-${ev.name}-${list.length}`, kind: 'tool', icon: '🔧', running: true,
            title: TOOL_LABEL[ev.name] || ev.name,
            detail: [{ label: '参数', text: JSON.stringify(ev.args ?? {}, null, 2) }],
          })
        } else {
          const it = findOpen('tool', (x) => x.title === (TOOL_LABEL[ev.name] || ev.name))
          if (it) {
            it.running = false
            it.ok = ev.ok !== false
            it.meta = ev.summary || ''
            if (ev.result) it.detail!.push({ label: '结果', text: ev.result })
          } else {
            list.push({
              key: `tool-${ev.name}-${list.length}`, kind: 'tool', icon: ev.ok !== false ? '🔧' : '⚠️',
              running: false, ok: ev.ok !== false,
              title: TOOL_LABEL[ev.name] || ev.name, meta: ev.summary || '',
              detail: [
                { label: '参数', text: JSON.stringify(ev.args ?? {}, null, 2) },
                ...(ev.result ? [{ label: '结果', text: ev.result }] : []),
              ],
            })
          }
        }
      } else if (ev.type === 'step') {
        const open = findOpen('step', (x) => x.title === ev.label)
        if (open && ev.status === 'done') {
          open.running = false
          open.ok = true
          if (ev.detail) open.meta = ev.detail
        } else if (!open) {
          list.push({
            key: `step-${ev.name}-${list.length}`, kind: 'step', icon: '·', running: ev.status === 'start',
            title: ev.label || ev.name, meta: ev.status === 'done' ? ev.detail : undefined,
          })
        }
      } else if (ev.type === 'note_start') {
        list.push({
          key: `note-${ev.index}-${list.length}`, kind: 'note', icon: '📝', running: true,
          title: `生成《${ev.title}》`,
          meta: ev.total ? `${(ev.index ?? 0) + 1}/${ev.total}` : undefined,
        })
      } else if (ev.type === 'note_done') {
        const it = findOpen('note', (x) => x.title === `生成《${ev.title}》`)
        if (it) { it.running = false; it.ok = true; it.meta = `已保存：${ev.path || ''}` }
      } else if (ev.type === 'note_skip') {
        list.push({
          key: `skip-${ev.index}-${list.length}`, kind: 'note', icon: '⏭', running: false, ok: true,
          title: `跳过《${ev.title}》`, meta: ev.reason,
        })
      } else if (ev.type === 'note_error') {
        const it = findOpen('note', (x) => x.title === `生成《${ev.title}》`)
        if (it) { it.running = false; it.ok = false; it.meta = ev.message }
        else list.push({ key: `nerr-${ev.index}-${list.length}`, kind: 'note', icon: '⚠️', running: false, ok: false, title: `《${ev.title}》失败`, meta: ev.message })
      }
    }
    return list
  }, [events])

  if (!items.length) return null
  return (
    <div className="proc-timeline" data-running={running ? '1' : undefined}>
      <div className="proc-head">调用过程</div>
      <div className="proc-list">
        {items.map((it) => (
          <details key={it.key} className={`proc-item k-${it.kind} ${it.running ? 'running' : ''} ${it.ok === false ? 'err' : ''}`}>
            <summary>
              <span className="p-icon">{it.running ? <span className="loading-dot" /> : it.icon}</span>
              <span className="p-title">{it.title}</span>
              {it.meta && <span className="p-meta">{it.meta}</span>}
            </summary>
            {it.detail?.map((d, i) => (
              <div key={i} className="p-detail">
                <span className="p-dlabel">{d.label}</span>
                <pre>{d.text}</pre>
              </div>
            ))}
          </details>
        ))}
      </div>
    </div>
  )
}
