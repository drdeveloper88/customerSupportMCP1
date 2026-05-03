/**
 * EmailVerification.jsx
 * Handles two cases:
 *  1. URL contains ?verify_token=... — auto-verifies and shows result.
 *  2. User is logged in but not verified — prompts to check email or resend.
 */

import { useEffect, useState } from 'react'
import { apiClient } from '../api/apiClient'
import './EmailVerification.css'

export default function EmailVerification({ token, onVerified, onShowLogin }) {
  const [status, setStatus] = useState(token ? 'verifying' : 'pending')
  // 'verifying' | 'success' | 'error' | 'pending' | 'resent'
  const [message, setMessage] = useState('')
  const [resending, setResending] = useState(false)

  useEffect(() => {
    if (!token) return
    async function verify() {
      try {
        const res = await apiClient.get(`/auth/verify-email?token=${encodeURIComponent(token)}`)
        setStatus('success')
        setMessage(res.detail || 'Your email has been verified!')
      } catch (err) {
        setStatus('error')
        setMessage(err.message || 'This verification link is invalid or has expired.')
      }
    }
    verify()
  }, [token])

  async function handleResend() {
    setResending(true)
    try {
      await apiClient.post('/auth/resend-verification', {})
      setStatus('resent')
    } catch {
      setStatus('resent') // Always show same message to prevent enumeration
    } finally {
      setResending(false)
    }
  }

  return (
    <div className="ev-overlay">
      <div className="ev-card">
        <div className="ev-icon">
          {status === 'verifying' && '⏳'}
          {status === 'success' && '✅'}
          {status === 'error' && '❌'}
          {status === 'pending' && '📧'}
          {status === 'resent' && '📬'}
        </div>

        {status === 'verifying' && (
          <>
            <h2 className="ev-title">Verifying your email…</h2>
            <p className="ev-subtitle">Please wait a moment.</p>
          </>
        )}

        {status === 'success' && (
          <>
            <h2 className="ev-title">Email verified!</h2>
            <p className="ev-subtitle">{message}</p>
            <button className="ev-btn" onClick={onVerified || onShowLogin}>
              Continue to app
            </button>
          </>
        )}

        {status === 'error' && (
          <>
            <h2 className="ev-title">Verification failed</h2>
            <p className="ev-subtitle ev-error">{message}</p>
            <button className="ev-btn ev-btn-secondary" onClick={handleResend} disabled={resending}>
              {resending ? 'Sending…' : 'Request new link'}
            </button>
            <button className="ev-link" onClick={onShowLogin}>
              Back to sign in
            </button>
          </>
        )}

        {status === 'pending' && (
          <>
            <h2 className="ev-title">Check your inbox</h2>
            <p className="ev-subtitle">
              We sent a verification link to your email address. Click the link to
              activate your account.
            </p>
            <p className="ev-hint">
              Didn&apos;t receive it? Check your spam folder or request a new link.
            </p>
            <button className="ev-btn" onClick={handleResend} disabled={resending}>
              {resending ? 'Sending…' : 'Resend verification email'}
            </button>
            <button className="ev-link" onClick={onShowLogin}>
              Back to sign in
            </button>
          </>
        )}

        {status === 'resent' && (
          <>
            <h2 className="ev-title">Verification email sent</h2>
            <p className="ev-subtitle">
              A new verification link has been sent. Please check your inbox (and
              spam folder).
            </p>
            <button className="ev-link" onClick={onShowLogin}>
              Back to sign in
            </button>
          </>
        )}
      </div>
    </div>
  )
}
