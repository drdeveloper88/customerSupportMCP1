/**
 * apiClient.js
 * Base HTTP client — centralises fetch configuration, error handling,
 * and response parsing for all API calls in the application.
 */

const API_BASE = '/api/v1'

/**
 * Perform a fetch request and resolve to parsed JSON.
 * Throws a structured error on non-2xx responses.
 *
 * @param {string} path   - Relative path, e.g. '/v1/orders/CUST-001'
 * @param {RequestInit} [options] - Fetch options
 * @returns {Promise<unknown>}
 */
async function request(path, options = {}) {
  const url = `${API_BASE}${path}`

  const response = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
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
  delete: (path, options) => request(path, { method: 'DELETE', ...options }),
}
