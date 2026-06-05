import React, { useState, useEffect, useRef, useCallback } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import SettingsPanel from '../components/SettingsPanel'
import * as api from '../api'
import { useChat } from '../hooks/useChat'
import { useProviders } from '../hooks/useProviders'
import type { Source, Metrics } from '../types'

const cleanThinking = (text: string): string =>
  text.replace(/^<think>/i, '').replace(/<\/think>$/i, '').trim()
const stripHtml = (text: string): string => text.replace(/<[^>]+>/g, '')

const PROVIDERS = [
  { id: 'ollama', label: 'Ollama' },
  { id: 'openai', label: 'LMStudio (OpenAI)' },
  { id: 'lmstudio', label: 'LMStudio (Native)' },
]

function formatTime(ts: number): string {
  const d = new Date(ts)
  const now = new Date()
  const pad = (n: number) => String(n).padStart(2, '0')
  const time = `${pad(d.getHours())}:${pad(d.getMinutes())}`
  if (d.getDate() === now.getDate() && d.getMonth() === now.getMonth()) return time
  return `${pad(d.getDate())}.${pad(d.getMonth() + 1)} ${time}`
}

function MetricsBar({ metrics }: { metrics: Metrics | null }) {
  if (!metrics) return null
  return (
    <div className="metrics-bar">
      ⏱ {metrics.time_sec}с · {metrics.tokens} токенов
      {typeof metrics.lm_tokens_per_sec === 'number' ? (
        <>
          {metrics.input_tokens ? <> · вход: {metrics.input_tokens}</> : null}
          {metrics.reasoning_tokens ? <> · размышления: {metrics.reasoning_tokens}</> : null}
          · {Number(metrics.lm_tokens_per_sec).toFixed(1)} ток/с
          {metrics.ttft ? <> · TTFT: {Number(metrics.ttft).toFixed(2)}с</> : null}
        </>
      ) : (
        metrics.output_tokens > 0 && (
          <> · {metrics.output_tokens} токенов за {metrics.output_time_sec}с ({metrics.tokens_per_sec} ток/с)</>
        )
      )}
    </div>
  )
}

function MessageBubble({ msg, showThinking, onCopy, onEdit, onRegenerate }:
  { msg: any; showThinking: boolean; onCopy: (c: string) => void; onEdit?: () => void; onRegenerate?: () => void }) {
  return (
    <div className={`message ${msg.role}`}>
      <div className="msg-bubble">
        {msg.role === 'assistant' && msg.thinking && showThinking && (
          <details className="thinking-block">
            <summary>🤔 Размышления модели</summary>
            <div className="thinking-content">{cleanThinking(msg.thinking)}</div>
          </details>
        )}
        <ReactMarkdown remarkPlugins={[remarkGfm]}>
          {stripHtml(msg.content)}
        </ReactMarkdown>
        <MetricsBar metrics={msg.metrics} />
        {msg.ts && <div className="msg-timestamp">{formatTime(msg.ts)}</div>}
      </div>
      <div className="msg-actions">
        <button className="msg-action-btn" onClick={() => onCopy(msg.content)} title="Копировать">📋</button>
        {msg.role === 'user' && onEdit && (
          <button className="msg-action-btn" onClick={onEdit} title="Редактировать">✏</button>
        )}
        {msg.role === 'assistant' && onRegenerate && (
          <button className="msg-action-btn" onClick={onRegenerate} title="Перегенерировать">🔄</button>
        )}
      </div>
    </div>
  )
}

interface ChatPageProps {
  sidebarOpen: boolean
  setSidebarOpen: (open: boolean) => void
}

export default function ChatPage({ sidebarOpen, setSidebarOpen }: ChatPageProps) {
  const {
    messages, input, setInput,
    loading, streaming, streamText, streamThinking,
    showThinking, setShowThinking,
    error, sources, metrics, editingId, contextUsed,
    mode, setMode, collections, setCollections,
    selectedCollection, setSelectedCollection,
    settings, setSettings,
    handleSend, handleEdit, handleRegenerate, handleRetry, handleCopy,
    handleStop, handleNewChat,
  } = useChat()

  const {
    providerName, providerOnline, chatModel, chatModels,
    loadProviderInfo, handleSwitchProvider, handleSelectModel,
  } = useProviders()

  const msgEndRef = useRef<HTMLDivElement>(null)
  const msgContainerRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const [showSettings, setShowSettings] = useState(false)
  const [userScrolledUp, setUserScrolledUp] = useState(false)

  const scrollToBottom = useCallback(() => {
    if (!userScrolledUp) msgEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [userScrolledUp])

  const handleScroll = useCallback(() => {
    const el = msgContainerRef.current
    if (!el) return
    setUserScrolledUp(el.scrollHeight - el.scrollTop - el.clientHeight > 60)
  }, [])

  useEffect(() => { loadProviderInfo() }, [loadProviderInfo])
  useEffect(() => {
    api.getCollections().then((data) => {
      if (data.collections) setCollections(data.collections)
    }).catch(() => {})
  }, [setCollections])
  useEffect(() => { scrollToBottom() }, [messages, streamText, scrollToBottom])

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Escape' && editingId) { setEditingId(null); setInput(''); return }
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend() }
  }

  const providerLabel = PROVIDERS.find(p => p.id === providerName)?.label || providerName

  return (
    <div className="chat-page">
      {/* Header */}
      <div className="chat-header">
        <button className="menu-btn" onClick={() => setSidebarOpen(!sidebarOpen)}>☰</button>
        <div className="chat-status">
          <span className={`status-dot ${providerOnline ? 'online' : 'offline'}`} />
          <span className="status-text">{providerLabel}{chatModel ? ` · ${chatModel}` : ''}</span>
        </div>
        <div className="chat-header-controls">
          <div className="provider-select-group">
            <select className="header-select" value={providerName}
              onChange={(e) => handleSwitchProvider(e.target.value)}>
              {PROVIDERS.map(p => <option key={p.id} value={p.id}>{p.label}</option>)}
            </select>
            {chatModels.length > 0 && (
              <select className="header-select" value={chatModel}
                onChange={(e) => handleSelectModel(e.target.value)}>
                {chatModels.map(m => <option key={m} value={m}>{m}</option>)}
              </select>
            )}
          </div>
          <div className="mode-toggle">
            {(['chat', 'rag', 'agent'] as const).map(m => (
              <button key={m} className={`mode-btn ${mode === m ? 'active' : ''}`}
                onClick={() => setMode(m)}>
                {m === 'chat' ? 'Чат' : m === 'rag' ? '+RAG' : 'Агент'}
              </button>
            ))}
          </div>
          {(mode === 'rag' || mode === 'agent') && (
            <select className="rag-select" value={selectedCollection}
              onChange={(e) => setSelectedCollection(e.target.value)}>
              <option value="">— выберите коллекцию —</option>
              {collections.map(c => (
                <option key={c.name} value={c.name}>{c.name} ({c.count} док.)</option>
              ))}
            </select>
          )}
          <button className="settings-btn" onClick={() => setShowSettings(true)}>⚙</button>
          <button className="settings-btn" onClick={handleNewChat}>✨</button>
        </div>
      </div>

      {/* Messages */}
      <div className="messages" ref={msgContainerRef} onScroll={handleScroll}>
        {messages.length === 0 && !streaming && (
          <div style={{ textAlign: 'center', color: 'var(--text2)', marginTop: 60, fontSize: 14 }}>
            <div style={{ fontSize: 40, marginBottom: 12 }}>💬</div>
            <div>Начните диалог с моделью</div>
            {!providerOnline && (
              <div style={{ marginTop: 8, color: 'var(--red)' }}>⚠ Провайдер недоступен</div>
            )}
            {mode === 'rag' && !selectedCollection && (
              <div style={{ marginTop: 8, color: 'var(--accent)' }}>⚠ Выбран RAG без коллекции</div>
            )}
          </div>
        )}

        {messages.map((msg) => (
          <MessageBubble key={msg.id} msg={msg} showThinking={showThinking}
            onCopy={handleCopy}
            onEdit={msg.role === 'user' ? () => handleEdit(msg.id) : undefined}
            onRegenerate={msg.role === 'assistant' ? () => handleRegenerate(msg.id) : undefined}
          />
        ))}

        {streaming && (
          <div className="message assistant">
            <div className="msg-bubble">
              {streamThinking && showThinking && (
                <details className="thinking-block">
                  <summary>🤔 Размышления модели</summary>
                  <div className="thinking-content">{cleanThinking(streamThinking)}</div>
                </details>
              )}
              {streamText ? (
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{stripHtml(streamText)}</ReactMarkdown>
              ) : (
                <div className="typing"><span /><span /><span /></div>
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
                  <div key={i} className="source-item"><strong>{s.filename}</strong> — {s.content}</div>
                ))}
              </details>
            </div>
          </div>
        )}

        {error && (
          <div className="message assistant">
            <div className="msg-bubble" style={{ background: 'var(--red)', color: '#fff' }}>❌ {error}</div>
            <div className="msg-actions" style={{ opacity: 1 }}>
              <button className="msg-action-btn" onClick={handleRetry} title="Повторить">🔄 Повторить</button>
            </div>
          </div>
        )}

        <div ref={msgEndRef} />
      </div>

      {/* Context bar */}
      {contextUsed > 0 && (
        <div className="context-bar">
          <div className="context-bar-fill"
            style={{ width: `${Math.min(100, (contextUsed / settings.contextLength) * 100)}%` }} />
          <span className="context-bar-text">
            Контекст: {contextUsed.toLocaleString()} / {settings.contextLength.toLocaleString()} токенов ({((contextUsed / settings.contextLength) * 100).toFixed(1)}%)
          </span>
        </div>
      )}

      {/* Input */}
      <div className="input-area">
        <div className="input-row">
          <button className={`think-toggle ${showThinking ? 'active' : ''}`}
            onClick={() => setShowThinking(!showThinking)}
            title={showThinking ? 'Скрыть размышления' : 'Показать размышления'}>🧠</button>
          <div className="input-wrap">
            {editingId && (
              <div className="edit-indicator">
                ✏ Редактирование
                <button className="edit-cancel-btn" onClick={() => { setEditingId(null); setInput('') }}>Отмена</button>
              </div>
            )}
            <textarea ref={inputRef} value={input} onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={editingId ? 'Редактирование...' : 'Введите сообщение...'}
              rows={1} disabled={loading} style={loading ? { opacity: 0.5 } : {}} />
          </div>
          {streaming ? (
            <button className="stop-btn" onClick={handleStop}>⏹</button>
          ) : (
            <button className="send-btn" onClick={handleSend} disabled={loading || !input.trim()}>➤</button>
          )}
        </div>
      </div>

      {showSettings && (
        <SettingsPanel settings={settings} onChange={setSettings} onClose={() => setShowSettings(false)} />
      )}
    </div>
  )
}
