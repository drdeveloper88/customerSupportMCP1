import { useEffect, useState } from 'react'
import Chat from './components/Chat'
import Dashboard from './components/Dashboard'
import EmailVerification from './components/EmailVerification'
import ForgotPassword from './components/ForgotPassword'
import Login from './components/Login'
import Profile from './components/Profile'
import Register from './components/Register'
import ResetPassword from './components/ResetPassword'
import Sidebar from './components/Sidebar'
import { apiClient, getStoredToken } from './api/apiClient'
import { CUSTOMERS } from './constants'

export default function App() {
  const [authenticated, setAuthenticated] = useState(() => !!getStoredToken())
  const [customerId, setCustomerId] = useState(CUSTOMERS[0])
  const [view, setView] = useState('chat')   // 'chat' | 'dashboard'
  const [showProfile, setShowProfile] = useState(false)
  // auth sub-view when not authenticated: 'login' | 'register' | 'forgot' | 'reset' | 'verify'
  const [authView, setAuthView] = useState('login')
  const [resetToken, setResetToken] = useState(null)
  const [verifyToken, setVerifyToken] = useState(null)

  // On mount: detect OAuth token in hash OR password-reset / email-verify token in query string
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const rt = params.get('reset_token')
    const vt = params.get('verify_token')
    if (rt) {
      setResetToken(rt)
      setAuthView('reset')
      window.history.replaceState({}, '', window.location.pathname)
    } else if (vt) {
      setVerifyToken(vt)
      setAuthView('verify')
      window.history.replaceState({}, '', window.location.pathname)
    }
  }, [])

  function handleLogin() {
    setAuthenticated(true)
    setAuthView('login')
  }

  async function handleLogout() {
    await apiClient.logout()
    setAuthenticated(false)
    setAuthView('login')
  }

  if (!authenticated) {
    if (authView === 'register') {
      return (
        <Register
          onLogin={handleLogin}
          onShowLogin={() => setAuthView('login')}
        />
      )
    }
    if (authView === 'forgot') {
      return <ForgotPassword onShowLogin={() => setAuthView('login')} />
    }
    if (authView === 'reset') {
      return (
        <ResetPassword
          token={resetToken}
          onShowLogin={() => setAuthView('login')}
        />
      )
    }
    if (authView === 'verify') {
      return (
        <EmailVerification
          token={verifyToken}
          onVerified={handleLogin}
          onShowLogin={() => setAuthView('login')}
        />
      )
    }
    return (
      <Login
        onLogin={handleLogin}
        onShowRegister={() => setAuthView('register')}
        onShowForgot={() => setAuthView('forgot')}
      />
    )
  }

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
          <button
            className="nav-tab"
            onClick={() => setShowProfile(true)}
            title="My account"
            style={{ marginLeft: '0.5rem' }}
          >
            👤 Account
          </button>
          <button
            className="nav-tab"
            onClick={handleLogout}
            title="Sign out"
            style={{ marginLeft: '0.25rem' }}
          >
            🚪 Sign out
          </button>
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

      {showProfile && <Profile onClose={() => setShowProfile(false)} />}
    </div>
  )
}
