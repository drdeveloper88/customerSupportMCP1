/**
 * Profile.jsx
 * User account management: view profile, update display name/username,
 * change password, resend email verification.
 */

import { useEffect, useState } from 'react'
import { apiClient } from '../api/apiClient'
import './Profile.css'

export default function Profile({ onClose }) {
  const [user, setUser] = useState(null)
  const [loadError, setLoadError] = useState('')

  // Profile update form
  const [fullName, setFullName] = useState('')
  const [username, setUsername] = useState('')
  const [profileMsg, setProfileMsg] = useState('')
  const [profileErr, setProfileErr] = useState('')
  const [profileSaving, setProfileSaving] = useState(false)

  // Change password form
  const [oldPassword, setOldPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [pwMsg, setPwMsg] = useState('')
  const [pwErr, setPwErr] = useState('')
  const [pwSaving, setPwSaving] = useState(false)

  // Email verification
  const [verifyMsg, setVerifyMsg] = useState('')
  const [verifySending, setVerifySending] = useState(false)

  useEffect(() => {
    async function loadProfile() {
      try {
        const data = await apiClient.get('/auth/me')
        setUser(data)
        setFullName(data.full_name || '')
        setUsername(data.username || '')
      } catch (err) {
        setLoadError(err.message || 'Failed to load profile.')
      }
    }
    loadProfile()
  }, [])

  async function handleProfileUpdate(e) {
    e.preventDefault()
    setProfileMsg('')
    setProfileErr('')
    setProfileSaving(true)
    try {
      const updated = await apiClient.put('/auth/me', {
        full_name: fullName || undefined,
        username: username || undefined,
      })
      setUser(updated)
      setProfileMsg('Profile updated successfully.')
    } catch (err) {
      setProfileErr(err.message || 'Failed to update profile.')
    } finally {
      setProfileSaving(false)
    }
  }

  async function handleChangePassword(e) {
    e.preventDefault()
    setPwMsg('')
    setPwErr('')
    if (newPassword !== confirmPassword) {
      setPwErr('New passwords do not match.')
      return
    }
    setPwSaving(true)
    try {
      await apiClient.post('/auth/change-password', {
        old_password: oldPassword,
        new_password: newPassword,
      })
      setPwMsg('Password changed successfully.')
      setOldPassword('')
      setNewPassword('')
      setConfirmPassword('')
    } catch (err) {
      setPwErr(err.message || 'Failed to change password.')
    } finally {
      setPwSaving(false)
    }
  }

  async function handleResendVerification() {
    setVerifyMsg('')
    setVerifySending(true)
    try {
      await apiClient.post('/auth/resend-verification', {})
      setVerifyMsg('Verification email sent — check your inbox.')
    } catch {
      setVerifyMsg('Verification email sent — check your inbox.')
    } finally {
      setVerifySending(false)
    }
  }

  const passwordRequirements =
    'At least 8 characters with uppercase, lowercase, number, and special character.'

  return (
    <div className="profile-overlay" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="profile-panel">
        <div className="profile-header">
          <h2 className="profile-title">👤 My Account</h2>
          <button className="profile-close" onClick={onClose} title="Close">✕</button>
        </div>

        {loadError && <p className="profile-error">{loadError}</p>}

        {user && (
          <>
            {/* ── Account summary ── */}
            <div className="profile-summary">
              <div className="profile-avatar">{(user.full_name || user.email)[0].toUpperCase()}</div>
              <div>
                <p className="profile-name">{user.full_name || '(no name set)'}</p>
                <p className="profile-email">{user.email}</p>
                <span className={`profile-badge ${user.is_verified ? 'verified' : 'unverified'}`}>
                  {user.is_verified ? '✓ Email verified' : '⚠ Email unverified'}
                </span>
                {user.oauth_provider && (
                  <span className="profile-badge oauth">
                    via {user.oauth_provider}
                  </span>
                )}
              </div>
            </div>

            {/* ── Resend verification ── */}
            {!user.is_verified && (
              <div className="profile-section">
                <h3 className="profile-section-title">Email Verification</h3>
                <p className="profile-hint">
                  Verify your email address to secure your account.
                </p>
                {verifyMsg && <p className="profile-success">{verifyMsg}</p>}
                <button
                  className="profile-btn profile-btn-secondary"
                  onClick={handleResendVerification}
                  disabled={verifySending}
                >
                  {verifySending ? 'Sending…' : 'Resend verification email'}
                </button>
              </div>
            )}

            {/* ── Update profile ── */}
            <div className="profile-section">
              <h3 className="profile-section-title">Profile Information</h3>
              <form onSubmit={handleProfileUpdate} className="profile-form">
                <label className="profile-label">
                  Full name
                  <input
                    className="profile-input"
                    type="text"
                    value={fullName}
                    onChange={(e) => setFullName(e.target.value)}
                    maxLength={200}
                    placeholder="Your display name"
                  />
                </label>
                <label className="profile-label">
                  Username (optional)
                  <input
                    className="profile-input"
                    type="text"
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    maxLength={64}
                    placeholder="username"
                  />
                </label>
                {profileMsg && <p className="profile-success">{profileMsg}</p>}
                {profileErr && <p className="profile-error">{profileErr}</p>}
                <button className="profile-btn" type="submit" disabled={profileSaving}>
                  {profileSaving ? 'Saving…' : 'Save changes'}
                </button>
              </form>
            </div>

            {/* ── Change password ── */}
            {!user.oauth_provider && (
              <div className="profile-section">
                <h3 className="profile-section-title">Change Password</h3>
                <form onSubmit={handleChangePassword} className="profile-form">
                  <label className="profile-label">
                    Current password
                    <input
                      className="profile-input"
                      type="password"
                      value={oldPassword}
                      onChange={(e) => setOldPassword(e.target.value)}
                      required
                      autoComplete="current-password"
                    />
                  </label>
                  <label className="profile-label">
                    New password
                    <input
                      className="profile-input"
                      type="password"
                      value={newPassword}
                      onChange={(e) => setNewPassword(e.target.value)}
                      required
                      minLength={8}
                      autoComplete="new-password"
                    />
                  </label>
                  <label className="profile-label">
                    Confirm new password
                    <input
                      className="profile-input"
                      type="password"
                      value={confirmPassword}
                      onChange={(e) => setConfirmPassword(e.target.value)}
                      required
                      minLength={8}
                      autoComplete="new-password"
                    />
                  </label>
                  <p className="profile-hint">{passwordRequirements}</p>
                  {pwMsg && <p className="profile-success">{pwMsg}</p>}
                  {pwErr && <p className="profile-error">{pwErr}</p>}
                  <button className="profile-btn" type="submit" disabled={pwSaving}>
                    {pwSaving ? 'Updating…' : 'Update password'}
                  </button>
                </form>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
