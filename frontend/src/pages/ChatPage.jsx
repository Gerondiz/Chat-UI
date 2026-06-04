import React, { useState, useRef, useEffect, useCallback } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import SettingsPanel from '../components/SettingsPanel'
import * as api from '../api'

const DEFAULT_SETTINGS = {
  systemPrompt: '',
  temperature: 0.7,
  maxTokens: 4096,
  topP: 0.9,
}

const PROVIDERS = [
  { id: 'ollama', label: 'Ollama' },
  // { id: 'openai', label: 'LMStudio (OpenAI)' },
  { id: 'lmstudio', label: 'LMStudio (Native)' },
]

export default function ChatPage({ sidebarOpen, setSidebarOpen }) {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [streaming, setStreaming] = useState(false)
  const [streamText, setStreamText] = useState('')
  const [streamThinking, setStreamThinking] = useState('')
  const [showThinking, setShowThinking] = useState(true)
  const [error, setError] = useState('')
  const [mode, setMode] = useState('chat')
  const [collections, setCollections] = useState([])
  const [selectedCollection, setSelectedCollection] = useState('')
  const [showSettings, setShowSettings] = useState(false)
  const [settings, setSettings] = useState(DEFAULT_SETTINGS)
  const [sources, setSources] = useState([])
  const [metrics, setMetrics] = useState(null)

  const [providerName, setProviderName] = useState('ollama')
  const [providerOnline, setProviderOnline] = useState(false)
  const [chatModel, setChatModel] = useState('')
  const [embeddingModel, setEmbeddingModel] = useState('')
  const [chatModels, setChatModels] = useState([])
  const [embeddingModels, setEmbeddingModels] = useState([])

  const msgEndRef = useRef(null)
  const msgContainerRef = useRef(null)
  const inputRef = useRef(null)
  const abortRef = useRef(null)
  const [userScrolledUp, setUserScrolledUp] = useState(false)

  const scrollToBottom = useCallback(() => {
    if (!userScrolledUp) {
      msgEndRef.current?.scrollIntoView({ behavior: 'smooth' })
    }
  }, [userScrolledUp])

  const handleScroll = useCallback(() => {
    const el = msgContainerRef.current
    if (!el) return
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 60
    setUserScrolledUp(!atBottom)
  }, [])

  useEffect(() => {
    api.getCollections().then((data) => {
      if (data.collections) setCollections(data.collections)
    }).catch(() => {})
  }, [])

  useEffect(() => {
    scrollToBottom()
  }, [messages, streamText, scrollToBottom])

  useEffect(() => {
    loadProviderInfo()
  }, [])

  const loadProviderInfo = async () => {
    try {
      const cfg = await api.getProvider()
      setProviderName(cfg.name)
      setChatModel(cfg.chat_model)
      setEmbeddingModel(cfg.embedding_model)
      const st = await api.getProviderStatus()
      setProviderOnline(st.online)
      setChatModels(st.chat_models || [])
      setEmbeddingModels(st.embedding_models || [])
    } catch (_) {}
  }

  const handleSwitchProvider = async (name) => {
    try {
      setProviderOnline(false)
      setChatModels([])
      setChatModel('')
      const cfg = await api.switchProvider(name)
      setProviderName(cfg.name)
      setChatModel(cfg.chat_model)
      setEmbeddingModel(cfg.embedding_model)
      const st = await api.getProviderStatus()
      setProviderOnline(st.online)
      setChatModels(st.chat_models || [])
      setEmbeddingModels(st.embedding_models || [])
    } catch (e) {
      setError('Ошибка переключения провайдера: ' + e.message)
    }
  }

  const handleSelectModel = async (model) => {
    setChatModel(model)
    try {
      const cfg = await api.getProvider()
      cfg.chat_model = model
      await api.updateProviderConfig(cfg)
      const st = await api.getProviderStatus()
      setProviderOnline(st.online)
    } catch (_) {}
  }

  const handleStop = () => {
    if (abortRef.current) {
      abortRef.current()
      abortRef.current = null
    }
    setStreaming(false)
    setLoading(false)
  }

  const handleSend = async () => {
    const text = input.trim()
    if (!text || loading) return
    setInput('')
    setError('')
    setMetrics(null)

    const userMsg = { role: 'user', content: text }
    const updated = [...messages, userMsg]
    setMessages(updated)

    if (abortRef.current) abortRef.current()
    setLoading(true)
    setStreaming(true)
    setStreamText('')
    setStreamThinking('')
    setSources([])
    setUserScrolledUp(false)

    abortRef.current = api.chatStream(
      updated,
      {
        systemPrompt: settings.systemPrompt,
        mode,
        collection: selectedCollection,
        temperature: settings.temperature,
        maxTokens: settings.maxTokens,
        topP: settings.topP,
        reasoning: showThinking,
      },
      (token) => {
        setStreamText((prev) => prev + token)
      },
      (thinking, isEnd) => {
        if (isEnd) {
          setStreamThinking((prev) => prev)
        } else if (thinking) {
          setStreamThinking((prev) => prev + thinking)
        }
      },
      (full, thinking, srcs, met) => {
        setStreaming(false)
        setLoading(false)
        setStreamText('')
        setStreamThinking('')
        setMessages((prev) => [
          ...prev,
          {
            role: 'assistant',
            content: full,
            thinking: thinking || '',
            metrics: met || null,
          },
        ])
        setSources(srcs || [])
        setMetrics(met || null)
      },
      (err) => {
        setStreaming(false)
        setLoading(false)
        setError(err)
      },
    )
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const handleNewChat = () => {
    if (abortRef.current) abortRef.current()
    setMessages([])
    setStreamText('')
    setStreamThinking('')
    setStreaming(false)
    setLoading(false)
    setError('')
    setSources([])
    setMetrics(null)
  }

  const providerLabel = PROVIDERS.find(p => p.id === providerName)?.label || providerName

  return (
    <div className="chat-page">
      <div className="chat-header">
        <button className="menu-btn" onClick={() => setSidebarOpen(!sidebarOpen)}>
          ☰
        </button>
        <div className="chat-status">
          <span className={`status-dot ${providerOnline ? 'online' : 'offline'}`} />
          <span className="status-text">
            {providerLabel}
            {chatModel ? ` · ${chatModel}` : ''}
          </span>
        </div>
        <div className="chat-header-controls">
          <div className="provider-select-group">
            <select
              className="header-select"
              value={providerName}
              onChange={(e) => handleSwitchProvider(e.target.value)}
            >
              {PROVIDERS.map(p => (
                <option key={p.id} value={p.id}>{p.label}</option>
              ))}
            </select>
            {chatModels.length > 0 && (
              <select
                className="header-select"
                value={chatModel}
                onChange={(e) => handleSelectModel(e.target.value)}
              >
                {chatModels.map(m => (
                  <option key={m} value={m}>{m}</option>
                ))}
              </select>
            )}
          </div>
          <div className="mode-toggle">
            <button
              className={`mode-btn ${mode === 'chat' ? 'active' : ''}`}
              onClick={() => setMode('chat')}
            >
              Чат
            </button>
            <button
              className={`mode-btn ${mode === 'rag' ? 'active' : ''}`}
              onClick={() => setMode('rag')}
            >
              +RAG
            </button>
          </div>
          {mode === 'rag' && (
            <select
              className="rag-select"
              value={selectedCollection}
              onChange={(e) => setSelectedCollection(e.target.value)}
            >
              <option value="">— выберите коллекцию —</option>
              {collections.map((c) => (
                <option key={c.name} value={c.name}>
                  {c.name} ({c.count} док.)
                </option>
              ))}
            </select>
          )}
          <button className="settings-btn" onClick={() => setShowSettings(true)}>
            ⚙
          </button>
          <button className="settings-btn" onClick={handleNewChat}>
            ✨
          </button>
        </div>
      </div>

      <div className="messages" ref={msgContainerRef} onScroll={handleScroll}>
        {messages.length === 0 && !streaming && (
          <div
            style={{
              textAlign: 'center',
              color: 'var(--text2)',
              marginTop: 60,
              fontSize: 14,
            }}
          >
            <div style={{ fontSize: 40, marginBottom: 12 }}>💬</div>
            <div>Начните диалог с моделью</div>
            {!providerOnline && (
              <div style={{ marginTop: 8, color: 'var(--red)' }}>
                ⚠ Провайдер недоступен. Выберите другой или проверьте подключение.
              </div>
            )}
            {mode === 'rag' && !selectedCollection && (
              <div style={{ marginTop: 8, color: 'var(--accent)' }}>
                ⚠ Выбран режим RAG, но не выбрана коллекция
              </div>
            )}
          </div>
        )}

        {messages.map((msg, i) => (
          <div key={i} className={`message ${msg.role}`}>
            <div className="msg-bubble">
              {msg.thinking && showThinking && (
                <details className="thinking-block">
                  <summary>🤔 Размышления модели</summary>
                  <div className="thinking-content">
                    {msg.thinking.replace(/<\/?think>/g, '')}
                  </div>
                </details>
              )}
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {msg.content}
              </ReactMarkdown>
              {msg.metrics && (
                <div className="metrics-bar">
                  ⏱ {msg.metrics.time_sec}с · {msg.metrics.tokens} токенов
                  {msg.metrics.lm_tokens_per_sec ? (
                    <>
                      {msg.metrics.input_tokens > 0 && <> · вход: {msg.metrics.input_tokens}</>}
                      {msg.metrics.reasoning_tokens > 0 && <> · размышления: {msg.metrics.reasoning_tokens}</>}
                      · {Number(msg.metrics.lm_tokens_per_sec).toFixed(1)} ток/с
                      {msg.metrics.ttft > 0 && <> · TTFT: {Number(msg.metrics.ttft).toFixed(2)}с</>}
                    </>
                  ) : (
                    msg.metrics.output_tokens > 0 && (
                      <> · {msg.metrics.output_tokens} токенов за {msg.metrics.output_time_sec}с ({msg.metrics.tokens_per_sec} ток/с)</>
                    )
                  )}
                </div>
              )}
            </div>
          </div>
        ))}

        {streaming && (
          <div className="message assistant">
            <div className="msg-bubble">
              {streamThinking && showThinking && (
                <details className="thinking-block">
                  <summary>🤔 Размышления модели</summary>
                  <div className="thinking-content">
                    {streamThinking}
                  </div>
                </details>
              )}
              {streamText ? (
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {streamText}
                </ReactMarkdown>
              ) : (
                <div className="typing">
                  <span /><span /><span />
                </div>
              )}
            </div>
          </div>
        )}

        {sources.length > 0 && (
          <div className="message assistant" style={{ paddingTop: 0 }}>
            <div className="sources-block">
              <details>
                <summary>📄 Источники ({sources.length})</summary>
                {sources.map((s, i) => (
                  <div key={i} className="source-item">
                    <strong>{s.filename}</strong> — {s.content}
                  </div>
                ))}
              </details>
            </div>
          </div>
        )}

        {error && (
          <div className="message assistant">
            <div className="msg-bubble" style={{ background: 'var(--red)', color: '#fff' }}>
              ❌ {error}
            </div>
          </div>
        )}

        <div ref={msgEndRef} />
      </div>

      <div className="input-area">
        <div className="input-row">
          <button
            className={`think-toggle ${showThinking ? 'active' : ''}`}
            onClick={() => setShowThinking(!showThinking)}
            title={showThinking ? 'Скрыть размышления' : 'Показать размышления'}
          >
            🧠
          </button>
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Введите сообщение..."
            rows={1}
            disabled={loading}
            style={loading ? { opacity: 0.5 } : {}}
          />
          {streaming ? (
            <button className="stop-btn" onClick={handleStop}>
              ⏹
            </button>
          ) : (
            <button
              className="send-btn"
              onClick={handleSend}
              disabled={loading || !input.trim()}
            >
              ➤
            </button>
          )}
        </div>
      </div>

      {showSettings && (
        <SettingsPanel
          settings={settings}
          onChange={setSettings}
          onClose={() => setShowSettings(false)}
        />
      )}
    </div>
  )
}
