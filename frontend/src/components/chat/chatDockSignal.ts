// AI 对话滑出面板的开关信号：ChatDock、TopBar、ChatConversation（引用事件）共用。
type Listener = () => void

const listeners = new Set<Listener>()
let dockOpen = false

function emit() {
  listeners.forEach((l) => l())
}

export const chatDock = {
  subscribe: (l: Listener) => {
    listeners.add(l)
    return () => { listeners.delete(l) }
  },
  get: () => dockOpen,
  set: (v: boolean) => { dockOpen = v; emit() },
  toggle: () => { dockOpen = !dockOpen; emit() },
}

/** 目录「引用本节」等场景：把 path#章节 引用塞进对话输入区并展开面板 */
export const CHAT_REFERENCE_EVENT = 'nl-chat-reference'

export function sendChatReference(ref: string) {
  window.dispatchEvent(new CustomEvent(CHAT_REFERENCE_EVENT, { detail: ref }))
  chatDock.set(true)
}

/** 行内文字引用（阅读器划选「加入对话」）的 wire 前缀，后端 chat_agent 按此注入选中原文 */
export const TEXT_REF_PREFIX = 'text:'

/** 阅读器划选「加入对话」：把选中文字打包成行内引用（text: + JSON）并展开面板 */
export function sendChatTextRef(text: string, source = '') {
  const t = text.trim()
  if (!t) return
  sendChatReference(TEXT_REF_PREFIX + JSON.stringify({ t, s: source }))
}
