import React, { useState } from 'react'
import type { ChatSummary } from '../types'

interface SidebarProps {
  open: boolean
  onToggle: () => void
  page: string
  onPageChange: (page: string) => void
  chats: ChatSummary[]
  activeChatId: number | null
  onSelectChat: (id: number) => void
  onNewChat: () => void
  onDeleteChat: (id: number) => void
}

export default function Sidebar({ open, onToggle, page, onPageChange, chats, activeChatId, onSelectChat, onNewChat, onDeleteChat }: SidebarProps) {
  const [deleting, setDeleting] = useState<number | null>(null)

  const handleDelete = (e: React.MouseEvent, chatId: number) => {
    e.stopPropagation()
    if (deleting === chatId) {
      onDeleteChat(chatId)
      setDeleting(null)
    } else {
      setDeleting(chatId)
      setTimeout(() => setDeleting(null), 3000)
    }
  }

  return (
    <aside className={`sidebar ${open ? '' : 'closed'}`}>
      <div className="sidebar-header">
        <h1>Chat-UI</h1>
      </div>

      <div className="sidebar-section">
        <button
          className={`nav-item ${page === 'chat' ? 'active' : ''}`}
          onClick={() => onPageChange('chat')}
        >
          💬 Чат
        </button>
        <button
          className={`nav-item ${page === 'collections' ? 'active' : ''}`}
          onClick={() => onPageChange('collections')}
        >
          📚 Коллекции
        </button>
      </div>

      {page === 'chat' && (
        <div className="sidebar-section chat-list-section">
          <div className="chat-list-header">
            <span className="chat-list-label">История</span>
            <button className="new-chat-btn" onClick={onNewChat} title="Новый чат">+</button>
          </div>
          <div className="chat-list">
            {chats.length === 0 && (
              <div className="chat-list-empty">Нет сохранённых чатов</div>
            )}
            {chats.map(chat => (
              <div
                key={chat.id}
                className={`chat-list-item ${activeChatId === chat.id ? 'active' : ''}`}
                onClick={() => onSelectChat(chat.id)}
              >
                <div className="chat-list-item-title">{chat.title}</div>
                <div className="chat-list-item-meta">
                  {chat.message_count} сообщ.
                </div>
                <button
                  className={`chat-delete-btn ${deleting === chat.id ? 'confirm' : ''}`}
                  onClick={(e) => handleDelete(e, chat.id)}
                  title={deleting === chat.id ? 'Нажмите ещё раз для подтверждения' : 'Удалить чат'}
                >
                  {deleting === chat.id ? '✓' : '✕'}
                </button>
              </div>
            ))}
          </div>
        </div>
      )}
    </aside>
  )
}
