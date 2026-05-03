/**
 * Login.jsx
 * Full-featured sign-in form supporting:
 *  - Email or username + password login
 *  - Google OAuth (one-click)
 *  - Facebook OAuth (one-click)
 *  - Links to Register and Forgot Password views
 *  - Reads #oauth_token= hash fragment set by the OAuth callback redirect
 */

import { useEffect, useState } from 'react'
import './Login.css'

export default function Login({ onLogin, onShowRegister, onShowForgot }) {
  const [identifier, setIdentifier] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  // null = still loading; {google: bool, facebook: bool} once fetched
  const [providers, setProviders] = useState(null)

  // Fetch which OAuth providers are configured on this server
  useEffect(() => {
    fetch('/api/v1/auth/providers')
      .then((r) => r.json())
      .catch(() => ({ google: false, facebook: false }))
      .then(setProviders)
  }, [])

  // Handle OAuth token delivered via URL hash fragment (#oauth_token=...)
  // and OAuth errors delivered via query string (?oauth_error=...)
  useEffect(() => {
    const hash = window.location.hash
    if (hash.startsWith('#oauth_token=')) {
      const token = decodeURIComponent(hash.slice('#oauth_token='.length))
      window.location.hash = ''
      if (token) {
        sessionStorage.setItem('access_token', token)
        onLogin()
        return
      }
    }
    const params = new URLSearchParams(window.location.search)
    const oauthError = params.get('oauth_error')
    if (oauthError) {
      const messages = {
        csrf_invalid: 'Login cancelled or expired. Please try again.',
        no_email: 'Your social account did not share an email address.',
        token_exchange_failed: 'Could not complete social login. Please try again.',
        not_configured: 'Social login is not configured on this server.',
      }
      setError(messages[oauthError] || `Social login error: ${oauthError}`)
      const clean = window.location.pathname
      window.history.replaceState({}, '', clean)
    }
  }, [onLogin])

  async function handleSubmit(e) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const res = await fetch('/api/v1/auth/token', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email_or_username: identifier, password }),
      })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        throw new Error(body.detail || `HTTP ${res.status}`)
      }
      const { access_token } = await res.json()
      sessionStorage.setItem('access_token', access_token)
      onLogin()
    } catch (err) {
      setError(err.message || 'Login failed')
    } finally {
      setLoading(false)
    }
  }

  function handleOAuth(provider) {
    window.location.href = `/api/v1/auth/oauth/${provider}`
  }

  // Only show the OAuth section once we know which providers exist
  const showGoogle = providers?.google === true
  const showFacebook = providers?.facebook === true
  const showOAuthSection = showGoogle || showFacebook

  return (
    <div className="login-overlay">
      <div className="login-card">
        <div className="login-logo">🎧</div>
        <h2 className="login-title">Customer Support</h2>
        <p className="login-subtitle">Sign in to continue</p>

        {showOAuthSection && (
          <>
            <div className="login-oauth">
              {showGoogle && (
                <button
                  className="login-oauth-btn login-oauth-google"
                  type="button"
                  onClick={() => handleOAuth('google')}
                  disabled={loading}
                >
                  <span className="oauth-icon">G</span> Continue with Google
                </button>
              )}
              {showFacebook && (
                <button
                  className="login-oauth-btn login-oauth-facebook"
                  type="button"
                  onClick={() => handleOAuth('facebook')}
                  disabled={loading}
                >
                  <span className="oauth-icon">f</span> Continue with Facebook
                </button>
              )}
            </div>
            <div className="login-divider"><span>or</span></div>
          </>
        )}

        <form onSubmit={handleSubmit} className="login-form">
          <label className="login-label">
            Email or Username
            <input
              className="login-input"
              type="text"
              value={identifier}
              onChange={(e) => setIdentifier(e.target.value)}
              autoComplete="username"
              required
              disabled={loading}
              placeholder="you@example.com"
            />
          </label>

          <label className="login-label">
            Password
            <input
              className="login-input"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              required
              disabled={loading}
              placeholder="••••••••"
            />
          </label>

          <button
            type="button"
            className="login-link-btn"
            onClick={onShowForgot}
            disabled={loading}
          >
            Forgot password?
          </button>

          {error && <p className="login-error">{error}</p>}

          <button className="login-btn" type="submit" disabled={loading}>
            {loading ? 'Signing in…' : 'Sign in'}
          </button>
        </form>

        <p className="login-footer">
          Don't have an account?{' '}
          <button className="login-link-btn" onClick={onShowRegister} disabled={loading}>
            Create account
          </button>
        </p>
      </div>
    </div>
  )
}
