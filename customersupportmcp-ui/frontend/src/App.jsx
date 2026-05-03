import { useState } from 'react'
import Chat from './components/Chat'
import Sidebar from './components/Sidebar'
import Dashboard from './components/Dashboard'
import { CUSTOMERS } from './constants'

export default function App() {
  const [customerId, setCustomerId] = useState(CUSTOMERS[0])
  const [view, setView] = useState('chat')   // 'chat' | 'dashboard'

  return (
    <div className="app">
      <header className="app-header">
        <div className="header-left">
          <span className="header-logo">🎧</span>
          <h1>Customer Support</h1>
          <span className="header-badge">MCP · AI</span>
        </div>

        <nav className="header-nav">
          <button
            className={`nav-tab${view === 'chat' ? ' active' : ''}`}
            onClick={() => setView('chat')}
          >
            💬 Chat
          </button>
          <button
            className={`nav-tab${view === 'dashboard' ? ' active' : ''}`}
            onClick={() => setView('dashboard')}
          >
            📊 Analytics
          </button>
        </nav>

        <div className="header-right">
          {view === 'chat' && (
            <>
              <span className="header-label">Customer:</span>
              <select
                value={customerId}
                onChange={(e) => setCustomerId(e.target.value)}
                className="customer-select"
              >
                {CUSTOMERS.map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
            </>
          )}
        </div>
      </header>

      <main className="app-main">
        {view === 'chat' ? (
          <>
            <Chat customerId={customerId} />
            <Sidebar customerId={customerId} />
          </>
        ) : (
          <Dashboard />
        )}
      </main>
    </div>
  )
}
