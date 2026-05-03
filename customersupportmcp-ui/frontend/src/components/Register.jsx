/**
 * Register.jsx
 * New user registration form.
 * On success the backend returns a JWT, which is stored and onLogin() is called.
 */

import { useState } from 'react'
import './Register.css'

export default function Register({ onLogin, onShowLogin }) {
  const [form, setForm] = useState({
    email: '',
    password: '',
    confirmPassword: '',
    full_name: '',
    username: '',
  })
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  function handleChange(e) {
    setForm((prev) => ({ ...prev, [e.target.name]: e.target.value }))
  }

  async function handleSubmit(e) {
    e.preventDefault()
    setError('')

    if (form.password !== form.confirmPassword) {
      setError('Passwords do not match.')
      return
    }

    setLoading(true)
    try {
      const body = {
        email: form.email,
        password: form.password,
        full_name: form.full_name,
      }
      if (form.username.trim()) body.username = form.username.trim()

      const res = await fetch('/api/v1/auth/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })

      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        // FastAPI validation errors come as {detail: [{msg, loc}]}
        if (Array.isArray(data.detail)) {
          throw new Error(data.detail.map((d) => d.msg).join('; '))
        }
        throw new Error(data.detail || `HTTP ${res.status}`)
      }

      const { access_token } = await res.json()
      sessionStorage.setItem('access_token', access_token)
      onLogin()
    } catch (err) {
      setError(err.message || 'Registration failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="register-overlay">
      <div className="register-card">
        <div className="register-logo">🎧</div>
        <h2 className="register-title">Create account</h2>
        <p className="register-subtitle">Join Customer Support</p>

        <form onSubmit={handleSubmit} className="register-form">
          <label className="register-label">
            Full name
            <input
              className="register-input"
              type="text"
              name="full_name"
              value={form.full_name}
              onChange={handleChange}
              autoComplete="name"
              required
              disabled={loading}
              placeholder="Jane Smith"
            />
          </label>

          <label className="register-label">
            Email
            <input
              className="register-input"
              type="email"
              name="email"
              value={form.email}
              onChange={handleChange}
              autoComplete="email"
              required
              disabled={loading}
              placeholder="you@example.com"
            />
          </label>

          <label className="register-label">
            Username <span className="register-optional">(optional)</span>
            <input
              className="register-input"
              type="text"
              name="username"
              value={form.username}
              onChange={handleChange}
              autoComplete="username"
              disabled={loading}
              placeholder="jane_smith"
            />
          </label>

          <label className="register-label">
            Password
            <input
              className="register-input"
              type="password"
              name="password"
              value={form.password}
              onChange={handleChange}
              autoComplete="new-password"
              required
              disabled={loading}
              placeholder="••••••••"
            />
            <span className="register-hint-text">
              8+ chars · uppercase · lowercase · digit · special character
            </span>
          </label>

          <label className="register-label">
            Confirm password
            <input
              className="register-input"
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

          {error && <p className="register-error">{error}</p>}

          <button className="register-btn" type="submit" disabled={loading}>
            {loading ? 'Creating account…' : 'Create account'}
          </button>
        </form>

        <p className="register-footer">
          Already have an account?{' '}
          <button className="register-link-btn" onClick={onShowLogin} disabled={loading}>
            Sign in
          </button>
        </p>
      </div>
    </div>
  )
}
