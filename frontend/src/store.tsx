import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { api } from './api'
import type { Settings, Topic, TreeNode } from './types'

interface Toast { id: number; text: string; kind: 'ok' | 'err' }

interface AppState {
  topics: Topic[]
  activeTopic: string
  setActiveTopic: (t: string) => void
  tree: TreeNode | null
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

  const refreshTree = useCallback(async () => {
    if (!activeTopic) { setTree(null); return }
    try {
      setTree(await api.tree(activeTopic))
    } catch (e: any) {
      setTree(null)
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
      topics, activeTopic, setActiveTopic, tree, refreshTree,
      refreshTopics, settings, refreshSettings, toasts, toast,
    }),
    [topics, activeTopic, setActiveTopic, tree, refreshTree, refreshTopics, settings, refreshSettings, toasts, toast],
  )
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}
