/**
 * ResetPassword.jsx
 * Reads the reset token from the URL query string (?reset_token=...) and
 * lets the user set a new password.
 */

import { useState } from 'react'
import './ResetPassword.css'

export default function ResetPassword({ token, onShowLogin }) {
  const [form, setForm] = useState({ newPassword: '', confirmPassword: '' })
  const [done, setDone] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  function handleChange(e) {
    setForm((prev) => ({ ...prev, [e.target.name]: e.target.value }))
  }

  async function handleSubmit(e) {
    e.preventDefault()
    setError('')

    if (form.newPassword !== form.confirmPassword) {
      setError('Passwords do not match.')
      return
    }

    setLoading(true)
    try {
      const res = await fetch('/api/v1/auth/reset-password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token, new_password: form.newPassword }),
      })
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        if (Array.isArray(data.detail)) {
          throw new Error(data.detail.map((d) => d.msg).join('; '))
        }
        throw new Error(data.detail || `HTTP ${res.status}`)
      }
      setDone(true)
      // Remove the reset_token from the URL
      window.history.replaceState({}, '', window.location.pathname)
    } catch (err) {
      setError(err.message || 'Reset failed')
    } finally {
      setLoading(false)
    }
  }

  if (done) {
    return (
      <div className="rp-overlay">
        <div className="rp-card">
          <div className="rp-icon">✅</div>
          <h2 className="rp-title">Password reset!</h2>
          <p className="rp-subtitle">Your password has been updated. You can now sign in.</p>
          <button className="rp-btn" onClick={onShowLogin}>
            Sign in
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="rp-overlay">
      <div className="rp-card">
        <div className="rp-icon">🔒</div>
        <h2 className="rp-title">Set new password</h2>
        <p className="rp-subtitle">Choose a strong password for your account.</p>

        <form onSubmit={handleSubmit} className="rp-form">
          <label className="rp-label">
            New password
            <input
              className="rp-input"
              type="password"
              name="newPassword"
              value={form.newPassword}
              onChange={handleChange}
              autoComplete="new-password"
              required
              disabled={loading}
              placeholder="••••••••"
            />
            <span className="rp-hint-text">
              8+ chars · uppercase · lowercase · digit · special character
            </span>
          </label>

          <label className="rp-label">
            Confirm new password
            <input
              className="rp-input"
              type="password"
              name="confirmPassword"
              value={form.confirmPassword}
              onChange={handleChange}
              autoComplete="new-password"
              required
              disabled={loading}
              placeholder="••••••••"
            />
          </label>

          {error && <p className="rp-error">{error}</p>}

          <button className="rp-btn" type="submit" disabled={loading}>
            {loading ? 'Updating…' : 'Set password'}
          </button>
        </form>

        <p className="rp-footer">
          <button className="rp-link-btn" onClick={onShowLogin} disabled={loading}>
            ← Back to sign in
          </button>
        </p>
      </div>
    </div>
  )
}
