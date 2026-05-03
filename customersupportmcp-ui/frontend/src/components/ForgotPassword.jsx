/**
 * ForgotPassword.jsx
 * Requests a password-reset email.
 * The backend always returns 202 (no email enumeration).
 */

import { useState } from 'react'
import './ForgotPassword.css'

export default function ForgotPassword({ onShowLogin }) {
  const [email, setEmail] = useState('')
  const [sent, setSent] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const res = await fetch('/api/v1/auth/forgot-password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email }),
      })
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        throw new Error(data.detail || `HTTP ${res.status}`)
      }
      setSent(true)
    } catch (err) {
      setError(err.message || 'Request failed')
    } finally {
      setLoading(false)
    }
  }

  if (sent) {
    return (
      <div className="fp-overlay">
        <div className="fp-card">
          <div className="fp-icon">📧</div>
          <h2 className="fp-title">Check your email</h2>
          <p className="fp-subtitle">
            If <strong>{email}</strong> is registered, you'll receive a reset link shortly.
          </p>
          <button className="fp-btn" onClick={onShowLogin}>
            Back to sign in
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="fp-overlay">
      <div className="fp-card">
        <div className="fp-icon">🔑</div>
        <h2 className="fp-title">Forgot password?</h2>
        <p className="fp-subtitle">
          Enter your email and we'll send a reset link.
        </p>

        <form onSubmit={handleSubmit} className="fp-form">
          <label className="fp-label">
            Email
            <input
              className="fp-input"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="email"
              required
              disabled={loading}
              placeholder="you@example.com"
            />
          </label>

          {error && <p className="fp-error">{error}</p>}

          <button className="fp-btn" type="submit" disabled={loading}>
            {loading ? 'Sending…' : 'Send reset link'}
          </button>
        </form>

        <p className="fp-footer">
          <button className="fp-link-btn" onClick={onShowLogin} disabled={loading}>
            ← Back to sign in
          </button>
        </p>
      </div>
    </div>
  )
}
