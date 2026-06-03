import React, { useState } from 'react'
import Sidebar from './components/Sidebar'
import ChatPage from './pages/ChatPage'
import CollectionsPage from './pages/CollectionsPage'
import './App.css'

export default function App() {
  const [page, setPage] = useState('chat')
  const [sidebarOpen, setSidebarOpen] = useState(true)

  return (
    <div className="app">
      <Sidebar
        open={sidebarOpen}
        onToggle={() => setSidebarOpen(!sidebarOpen)}
        page={page}
        onPageChange={setPage}
      />
      <main className="main">
        {page === 'chat' && (
          <ChatPage
            sidebarOpen={sidebarOpen}
            setSidebarOpen={setSidebarOpen}
          />
        )}
        {page === 'collections' && <CollectionsPage />}
      </main>
    </div>
  )
}
