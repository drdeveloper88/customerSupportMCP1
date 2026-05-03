/**
 * apiClient.js
 * Base HTTP client — centralises fetch configuration, error handling,
 * and response parsing for all API calls in the application.
 */

const API_BASE = '/api/v1'

/** Retrieve the stored JWT access token (set after login). */
export function getStoredToken() {
  return sessionStorage.getItem('access_token')
}

/** Persist an access token for the current browser session. */
export function setStoredToken(token) {
  sessionStorage.setItem('access_token', token)
}

/** Remove the stored token (logout). */
export function clearStoredToken() {
  sessionStorage.removeItem('access_token')
}

/**
 * Perform a fetch request and resolve to parsed JSON.
 * Automatically attaches the stored JWT as a Bearer token.
 * Throws a structured error on non-2xx responses.
 *
 * @param {string} path   - Relative path, e.g. '/orders/CUST-001'
 * @param {RequestInit} [options] - Fetch options
 * @returns {Promise<unknown>}
 */
async function request(path, options = {}) {
  const url = `${API_BASE}${path}`
  const token = getStoredToken()

  const response = await fetch(url, {
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
    ...options,
  })

  if (!response.ok) {
    let errorMessage = `HTTP ${response.status} – ${response.statusText}`
    try {
      const body = await response.json()
      if (Array.isArray(body.detail)) {
        // Pydantic validation errors — flatten to readable string
        errorMessage = body.detail.map((e) => e.msg).join(', ')
      } else {
        errorMessage = body.detail || body.error || errorMessage
      }
    } catch {
      // Non-JSON error body; use the HTTP status text
    }
    const error = new Error(errorMessage)
    error.status = response.status
    throw error
  }

  return response.json()
}

/**
 * Convenience wrappers around the base request function.
 */
export const apiClient = {
  get:    (path, options) => request(path, { method: 'GET',    ...options }),
  post:   (path, body, options) =>
    request(path, { method: 'POST', body: JSON.stringify(body), ...options }),
  put:    (path, body, options) =>
    request(path, { method: 'PUT',  body: JSON.stringify(body), ...options }),
  patch:  (path, body, options) =>
    request(path, { method: 'PATCH', body: JSON.stringify(body), ...options }),
  delete: (path, options) => request(path, { method: 'DELETE', ...options }),

  /**
   * Revoke the current JWT on the server then clear it from storage.
   * Clears the local token regardless of whether the server call succeeds.
   */
  async logout() {
    try {
      await request('/auth/logout', { method: 'POST', body: JSON.stringify({}) })
    } catch {
      // Server-side revocation is best-effort; always clear client token
    }
    clearStoredToken()
  },
}
