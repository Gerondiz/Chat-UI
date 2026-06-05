import React, { useState } from 'react'
import Sidebar from './components/Sidebar'
import ChatPage from './pages/ChatPage'
import CollectionsPage from './pages/CollectionsPage'
import './App.css'

export default function App() {
  const [page, setPage] = useState('chat')
  const [sidebarOpen, setSidebarOpen] = useState(true)

  if (page !== 'chat') {
    return (
      <div className="app">
        <Sidebar
          open={sidebarOpen}
          onToggle={() => setSidebarOpen(!sidebarOpen)}
          page={page}
          onPageChange={setPage}
          chats={[]}
          activeChatId={null}
          onSelectChat={() => {}}
          onNewChat={() => {}}
          onDeleteChat={() => {}}
        />
        <main className="main">
          <CollectionsPage />
        </main>
      </div>
    )
  }

  return (
    <div className="app">
      <ChatPage
        sidebarOpen={sidebarOpen}
        setSidebarOpen={setSidebarOpen}
        page={page}
        onPageChange={setPage}
      />
    </div>
  )
}
