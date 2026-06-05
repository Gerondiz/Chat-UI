import { useState, useRef, useCallback, useEffect } from 'react'
import * as api from '../api'
import type { Message, ChatSettings, Source, Metrics, ChatSummary } from '../types'

const generateId = (): string => {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) return crypto.randomUUID()
  return `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
}

export function useChat() {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [streaming, setStreaming] = useState(false)
  const [streamText, setStreamText] = useState('')
  const [streamThinking, setStreamThinking] = useState('')
  const [showThinking, setShowThinking] = useState(true)
  const [error, setError] = useState('')
  const [sources, setSources] = useState<Source[]>([])
  const [metrics, setMetrics] = useState<Metrics | null>(null)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [contextUsed, setContextUsed] = useState(0)
  const [mode, setMode] = useState('agent')
  const [collections, setCollections] = useState<{ name: string; count: number }[]>([])
  const [selectedCollection, setSelectedCollection] = useState('')
  const [settings, setSettings] = useState<ChatSettings>({
    systemPrompt: '', temperature: 0.7, maxTokens: 4096, topP: 0.9, contextLength: 131072,
  })

  const [chats, setChats] = useState<ChatSummary[]>([])
  const [activeChatId, setActiveChatId] = useState<number | null>(null)

  const abortRef = useRef<(() => void) | null>(null)
  const messagesRef = useRef(messages)
  messagesRef.current = messages
  const activeChatIdRef = useRef(activeChatId)
  activeChatIdRef.current = activeChatId

  useEffect(() => { api.getChats().then(setChats).catch(() => {}) }, [])

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
    if (abortRef.current) abortRef.current()
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

    const msgs = await api.getChatMessages(chatId)
    setMessages(msgs)
  }, [saveMessages])

  const createNewChat = useCallback(async () => {
    if (abortRef.current) abortRef.current()
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
    setLoading(true)
    setStreaming(true)
    setStreamText('')
    setStreamThinking('')
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
        setStreamText((prev) => prev + token)
      },
      (thinking: string, isEnd: boolean) => {
        if (isEnd) {
          setStreamThinking((prev) => prev)
        } else if (thinking) {
          setStreamThinking((prev) => prev + thinking)
        }
      },
      (full: string, thinking: string, srcs: Source[], met: Metrics | null) => {
        setStreaming(false)
        setLoading(false)
        setStreamText('')
        setStreamThinking('')
        setMessages((prev) => {
          const newMsg: Message = {
            role: 'assistant', content: full,
            thinking: thinking || '', metrics: met || null,
            id: generateId(), ts: Date.now(),
          }
          const result = [...prev, newMsg]
          // Save after every response
          api.saveChatMessages(chatId, result).catch(() => {})
          return result
        })
        setSources(srcs || [])
        setMetrics(met || null)
        if (met) {
          const inp = met.input_tokens || 0
          if (inp > 0) setContextUsed(inp + (met.tokens || 0))
        }
        // Refresh chat list
        api.getChats().then(setChats).catch(() => {})
      },
      (err: string) => {
        setStreaming(false)
        setLoading(false)
        setError(err)
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
    loading, streaming, streamText, streamThinking,
    showThinking, setShowThinking,
    error, sources, metrics, editingId, contextUsed,
    mode, setMode, collections, setCollections,
    selectedCollection, setSelectedCollection,
    settings, setSettings,
    handleSend, handleEdit, handleRegenerate, handleRetry, handleCopy,
    handleStop, handleNewChat, doSend, cancelEdit,
    chats, activeChatId, selectChat, deleteChat,
  }
}
