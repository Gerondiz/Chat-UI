import React from 'react'

interface SidebarProps {
  open: boolean
  onToggle: () => void
  page: string
  onPageChange: (page: string) => void
}

export default function Sidebar({ open, onToggle, page, onPageChange }: SidebarProps) {
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
