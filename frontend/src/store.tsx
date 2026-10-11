import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import { api } from './api'
import type { Settings, Topic, TreeNode } from './types'

interface Toast { id: number; text: string; kind: 'ok' | 'err' }

interface AppState {
  topics: Topic[]
  activeTopic: string
  setActiveTopic: (t: string) => void
  tree: TreeNode | null
  /** 当前 tree 属于哪个主题；与 activeTopic 不一致说明目录还在加载 */
  treeTopic: string
  refreshTree: () => Promise<void>
  refreshTopics: () => Promise<void>
  settings: Settings | null
  refreshSettings: () => Promise<void>
  toasts: Toast[]
  toast: (text: string, kind?: 'ok' | 'err') => void
}

const Ctx = createContext<AppState>(null as any)
export const useApp = () => useContext(Ctx)

export function AppProvider({ children }: { children: React.ReactNode }) {
  const [topics, setTopics] = useState<Topic[]>([])
  const [activeTopic, setActiveTopicState] = useState(
    () => localStorage.getItem('nl-topic') || '',
  )
  const [tree, setTree] = useState<TreeNode | null>(null)
  const [treeTopic, setTreeTopic] = useState('')
  const [settings, setSettings] = useState<Settings | null>(null)
  const [toasts, setToasts] = useState<Toast[]>([])

  const toast = useCallback((text: string, kind: 'ok' | 'err' = 'ok') => {
    const id = Date.now() + Math.random()
    setToasts((t) => [...t, { id, text, kind }])
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 3200)
  }, [])

  const refreshTopics = useCallback(async () => {
    try {
      const { topics } = await api.topics()
      setTopics(topics)
      setActiveTopicState((cur) => {
        if (cur && topics.some((t) => t.name === cur)) return cur
        const next = topics[0]?.name || ''
        localStorage.setItem('nl-topic', next)
        return next
      })
    } catch (e: any) {
      toast(`加载主题失败：${e.message}`, 'err')
    }
  }, [toast])

  const setActiveTopic = useCallback((t: string) => {
    setActiveTopicState(t)
    localStorage.setItem('nl-topic', t)
  }, [])

  const topicRef = useRef('')
  topicRef.current = activeTopic
  const refreshTree = useCallback(async () => {
    const topic = activeTopic
    if (!topic) { setTree(null); setTreeTopic(''); return }
    try {
      const t = await api.tree(topic)
      if (topicRef.current !== topic) return // 期间已切到别的主题，丢弃过期结果
      setTree(t)
      setTreeTopic(topic)
    } catch (e: any) {
      if (topicRef.current !== topic) return
      setTree(null)
      setTreeTopic('')
      toast(`加载目录失败：${e.message}`, 'err')
    }
  }, [activeTopic, toast])

  const refreshSettings = useCallback(async () => {
    try { setSettings(await api.settings()) } catch { /* 静默 */ }
  }, [])

  useEffect(() => { refreshTopics(); refreshSettings() }, [refreshTopics, refreshSettings])
  useEffect(() => { refreshTree() }, [refreshTree])

  const value = useMemo(
    () => ({
      topics, activeTopic, setActiveTopic, tree, treeTopic, refreshTree,
      refreshTopics, settings, refreshSettings, toasts, toast,
    }),
    [topics, activeTopic, setActiveTopic, tree, treeTopic, refreshTree, refreshTopics, settings, refreshSettings, toasts, toast],
  )
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}
