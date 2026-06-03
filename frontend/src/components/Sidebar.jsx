import React from 'react'

export default function Sidebar({
  open, onToggle, page, onPageChange,
}) {
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
    </aside>
  )
}
