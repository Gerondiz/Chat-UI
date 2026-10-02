import { useState, useRef, useCallback, useEffect } from 'react'
import * as api from '../api'
import type { Message, ChatSettings, Source, Metrics, ChatSummary, AgentStep } from '../types'

const generateId = (): string => {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) return crypto.randomUUID()
  return `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
}

const SETTINGS_KEY = 'chat-ui.settings'

// Chat settings are shared by every chat rather than stored per chat, so they
// survive a page reload and a detour through the Collections page, both of
// which unmount the chat screen and rebuild this state from scratch.
const DEFAULT_SETTINGS: ChatSettings = {
  systemPrompt: '', temperature: 0.7, maxTokens: 4096, topP: 0.9,
}

const clampNum = (value: unknown, min: number, max: number, fallback: number): number => {
  const n = typeof value === 'number' ? value : Number(value)
  if (!Number.isFinite(n)) return fallback
  return Math.min(max, Math.max(min, n))
}

function loadSettings(): ChatSettings {
  try {
    const raw = localStorage.getItem(SETTINGS_KEY)
    if (!raw) return DEFAULT_SETTINGS
    const saved = JSON.parse(raw) ?? {}
    return {
      systemPrompt: typeof saved.systemPrompt === 'string' ? saved.systemPrompt : '',
      temperature: clampNum(saved.temperature, 0, 2, DEFAULT_SETTINGS.temperature),
      maxTokens: Math.round(clampNum(saved.maxTokens, 64, 32768, DEFAULT_SETTINGS.maxTokens)),
      topP: clampNum(saved.topP, 0, 1, DEFAULT_SETTINGS.topP),
    }
  } catch {
    return DEFAULT_SETTINGS
  }
}

export function useChat() {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [streaming, setStreaming] = useState(false)
  const [streamText, setStreamText] = useState('')
  const [streamThinking, setStreamThinking] = useState('')
  const [agentStep, setAgentStep] = useState<AgentStep | null>(null)
  const [showThinking, setShowThinking] = useState(true)
  const [error, setError] = useState('')
  const [sources, setSources] = useState<Source[]>([])
  const [metrics, setMetrics] = useState<Metrics | null>(null)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [contextUsed, setContextUsed] = useState(0)
  const [contextWindow, setContextWindow] = useState(0)
  const [mode, setMode] = useState('agent')
  const [collections, setCollections] = useState<{ name: string; count: number }[]>([])
  const [selectedCollection, setSelectedCollection] = useState('')
  const [settings, setSettings] = useState<ChatSettings>(loadSettings)

  const [chats, setChats] = useState<ChatSummary[]>([])
  const [activeChatId, setActiveChatId] = useState<number | null>(null)

  const sendChatIdRef = useRef<number | null>(null)
  const abortRef = useRef<(() => void) | null>(null)
  const messagesRef = useRef(messages)
  messagesRef.current = messages
  const activeChatIdRef = useRef(activeChatId)
  activeChatIdRef.current = activeChatId

  useEffect(() => { api.getChats().then(setChats).catch(() => {}) }, [])

  useEffect(() => {
    try { localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings)) } catch { /* private mode */ }
  }, [settings])

  const ensureChat = useCallback(async () => {
    if (activeChatIdRef.current) return activeChatIdRef.current
    const chat = await api.createChat()
    setActiveChatId(chat.id)
    setChats(prev => [{ id: chat.id, title: chat.title, message_count: 0, created_at: '', updated_at: '' }, ...prev])
    return chat.id
  }, [])

  const saveMessages = useCallback(async () => {
    const chatId = activeChatIdRef.current
    if (!chatId) return
    const msgs = messagesRef.current
    if (msgs.length === 0) return
    try {
      await api.saveChatMessages(chatId, msgs)
      const updated = await api.getChats()
      setChats(updated)
      const title = msgs[0]?.content?.slice(0, 60) || 'Новый чат'
      if (msgs.length > 0) {
        api.renameChat(chatId, title).catch(() => {})
      }
    } catch { /* ignore */ }
  }, [])

  const selectChat = useCallback(async (chatId: number) => {
    // NOTE: an in-flight request is intentionally NOT aborted here. Switching
    // chats used to cancel it, which discarded the answer permanently: onDone
    // never fired, so the reply was never saved. It now keeps running in the
    // background and is persisted to its own chat when it completes.
    if (activeChatIdRef.current && messagesRef.current.length > 0) {
      await saveMessages()
    }
    setActiveChatId(chatId)
    setStreamText('')
    setStreamThinking('')
    setStreaming(false)
    setLoading(false)
    setError('')
    setSources([])
    setMetrics(null)
    setEditingId(null)
    setInput('')
    setContextUsed(0)
    setContextWindow(0)

    const msgs = await api.getChatMessages(chatId)
    setMessages(msgs)
  }, [saveMessages])

  const createNewChat = useCallback(async () => {
    // See selectChat: the running request keeps streaming into its own chat.
    if (activeChatIdRef.current && messagesRef.current.length > 0) {
      await saveMessages()
    }
    setActiveChatId(null)
    setMessages([])
    setStreamText('')
    setStreamThinking('')
    setStreaming(false)
    setLoading(false)
    setError('')
    setSources([])
    setMetrics(null)
    setEditingId(null)
    setInput('')
    setContextUsed(0)
    setContextWindow(0)
  }, [saveMessages])

  const deleteChat = useCallback(async (chatId: number) => {
    await api.deleteChat(chatId)
    setChats(prev => prev.filter(c => c.id !== chatId))
    if (activeChatIdRef.current === chatId) {
      createNewChat()
    }
  }, [createNewChat])

  const handleStop = useCallback(() => {
    if (abortRef.current) {
      abortRef.current()
      abortRef.current = null
    }
    sendChatIdRef.current = null
    setStreaming(false)
    setLoading(false)
  }, [])

  const doSend = useCallback(async (baseMessages: Message[], text: string) => {
    if (!text || loading) return
    setInput('')
    setError('')
    setMetrics(null)
    setEditingId(null)

    const chatId = await ensureChat()

    const userMsg: Message = { role: 'user', content: text, id: generateId(), ts: Date.now() }
    const updated = [...baseMessages, userMsg]
    setMessages(updated)

    if (abortRef.current) abortRef.current()
    sendChatIdRef.current = chatId
    setLoading(true)
    setStreaming(true)
    setStreamText('')
    setStreamThinking('')
    setAgentStep(null)
    setSources([])

    // Auto-title from first user message
    if (updated.length <= 2) {
      const title = text.slice(0, 60)
      api.renameChat(chatId, title).catch(() => {})
      setChats(prev => prev.map(c => c.id === chatId ? { ...c, title } : c))
    }

    abortRef.current = api.chatStream(
      updated,
      { settings, mode, collection: selectedCollection, reasoning: showThinking },
      (token: string) => {
        if (activeChatIdRef.current !== chatId) return
        setStreamText((prev) => prev + token)
      },
      (thinking: string, isEnd: boolean) => {
        if (activeChatIdRef.current !== chatId) return
        if (isEnd) {
          setStreamThinking((prev) => prev)
        } else if (thinking) {
          setStreamThinking((prev) => prev + thinking)
        }
      },
      (full: string, thinking: string, srcs: Source[], met: Metrics | null) => {
        const newMsg: Message = {
          role: 'assistant', content: full,
          thinking: thinking || '', metrics: met || null,
          id: generateId(), ts: Date.now(),
        }

        // The user may have switched to another chat while this was running.
        // In that case only persist the result; touching the UI would paint
        // the answer into the wrong conversation.
        if (activeChatIdRef.current !== chatId) {
          const result = [...updated, newMsg]
          api.saveChatMessages(chatId, result).catch(() => {})
          const title = updated[0]?.content?.slice(0, 60) || 'Новый чат'
          api.renameChat(chatId, title).catch(() => {})
          api.getChats().then(setChats).catch(() => {})
          if (sendChatIdRef.current === chatId) sendChatIdRef.current = null
          return
        }

        setStreaming(false)
        setLoading(false)
        setStreamText('')
        setStreamThinking('')
        setAgentStep(null)
        setMessages((prev) => {
          const result = [...prev, newMsg]
          // Save after every response
          api.saveChatMessages(chatId, result).catch(() => {})
          return result
        })
        setSources(srcs || [])
        setMetrics(met || null)
        if (met) {
          setContextUsed((met.input_tokens || 0) + (met.tokens || 0))
          // The window the backend actually enforced, since the server clamps
          // the request to what the model was loaded with.
          setContextWindow(met.context_length || 0)
        }
        // Refresh chat list
        api.getChats().then(setChats).catch(() => {})
        if (sendChatIdRef.current === chatId) sendChatIdRef.current = null
      },
      (err: string) => {
        // Same split: surface the error only if its chat is still on screen.
        if (sendChatIdRef.current === chatId) sendChatIdRef.current = null
        if (activeChatIdRef.current !== chatId) return
        setStreaming(false)
        setLoading(false)
        setAgentStep(null)
        setError(err)
      },
      (step: AgentStep) => {
        if (activeChatIdRef.current !== chatId) return
        setAgentStep(step)
      },
      () => {
        // Intermediate agent turn was discarded: clear its text.
        if (activeChatIdRef.current !== chatId) return
        setStreamText('')
        setStreamThinking('')
      },
    )
  }, [loading, settings, mode, selectedCollection, showThinking, ensureChat])

  const handleSend = useCallback(async () => {
    const text = input.trim()
    if (!text || loading) return
    if (editingId) {
      const editIdx = messages.findIndex(m => m.id === editingId)
      if (editIdx !== -1) {
        await doSend(messages.slice(0, editIdx), text)
        return
      }
      setEditingId(null)
    }
    await doSend(messages, text)
  }, [input, loading, editingId, messages, doSend])

  const handleEdit = useCallback((msgId: string) => {
    if (loading) return
    const msg = messages.find(m => m.id === msgId)
    if (!msg) return
    setEditingId(msgId)
    setInput(msg.content)
  }, [loading, messages])

  const handleRegenerate = useCallback(async (msgId: string) => {
    if (loading) return
    if (abortRef.current) abortRef.current()
    setEditingId(null)
    const msgIdx = messages.findIndex(m => m.id === msgId)
    if (msgIdx === -1) return
    const baseMessages = messages.slice(0, msgIdx)
    setMessages(baseMessages)
    const lastUser = [...baseMessages].reverse().find(m => m.role === 'user') as Message | undefined
    if (!lastUser) return
    await doSend(baseMessages, lastUser.content)
  }, [loading, messages, doSend])

  const handleRetry = useCallback(async () => {
    if (loading) return
    setError('')
    if (messages.length === 0) return
    const lastMsg = messages[messages.length - 1]
    if (lastMsg.role !== 'user') return
    await doSend(messages.slice(0, -1), lastMsg.content)
  }, [loading, messages, doSend])

  const handleNewChat = useCallback(() => {
    createNewChat()
  }, [createNewChat])

  const handleCopy = useCallback(async (content: string) => {
    try { await navigator.clipboard.writeText(content) } catch { /* ignore */ }
  }, [])

  const cancelEdit = useCallback(() => {
    setEditingId(null)
    setInput('')
  }, [])

  return {
    messages, input, setInput,
    loading, streaming, streamText, streamThinking, agentStep,
    showThinking, setShowThinking,
    error, sources, metrics, editingId, contextUsed, contextWindow,
    mode, setMode, collections, setCollections,
    selectedCollection, setSelectedCollection,
    settings, setSettings,
    handleSend, handleEdit, handleRegenerate, handleRetry, handleCopy,
    handleStop, handleNewChat, doSend, cancelEdit,
    chats, activeChatId, selectChat, deleteChat,
  }
}
